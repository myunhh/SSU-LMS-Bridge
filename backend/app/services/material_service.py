# backend/app/services/material_service.py
# 강의자료 '원본 파일'(PPT/PDF/문서 등) 다운로드 → Obsidian 저장.
# ──────────────────────────────────────────────────────────────────────────────
# perform_sync(routes/sync.py)가 download_files=True + Obsidian 설정 시 호출한다.
#
# 동작 원리(검증됨):
#   1) 강의자료 항목(ExternalTool=LearningX lecture_attendance)을 LTI 런치하면
#      `learningx/api/v1/courses/{cid}/attendance_items/{view_id}` 응답의
#      item_content_data 에 {content_id, content_type, file_name} 이 들어온다.
#   2) commons 다운로드 URL 로 '원본 파일'을 그대로 받는다(쿠키만 필요, Bearer 불필요):
#        https://commons.ssu.ac.kr/index.php?module=xn_media_content2013
#          &act=dispXn_media_content2013DownloadContent&content_id={content_id}
#   3) movie/스트리밍/외부 유튜브 링크·80MB 초과(녹화영상)는 교안이 아니므로 건너뛴다.
#
# ⚠️ 출석 보호: content_id 를 알아내려면 LTI 를 1회 런치해야 하고 그때 진도/출결이
#    기록될 수 있다. 그래서 항목별 판정(content_id 포함)을 매니페스트에 캐시해
#    **항목당 평생 1번만** 런치한다. 이미 Obsidian 에 파일이 있으면(최초 동기화 시
#    수동 배치로 받아둔 것 포함) 런치 없이 건너뛴다.
# ──────────────────────────────────────────────────────────────────────────────
import asyncio
import base64
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import settings
from app.logger import logger
from app.mcp_client.base import MCPClientBase

# 매니페스트 — 루트 .cache/ 아래 절대경로 (uvicorn CWD 무관, vault_manifest 와 동일 정책)
MANIFEST_PATH = settings.root_dir / ".cache" / "material_files_manifest.json"

DL_TMPL = ("https://commons.ssu.ac.kr/index.php?module=xn_media_content2013"
           "&act=dispXn_media_content2013DownloadContent&content_id={cid}")
# 다운로드 불가(스트리밍/외부) content_type — 진짜 영상/녹화/외부링크
VIDEO_TYPES = {"movie", "video", "external_video", "youtube", "zoom", "vimeo"}
# 80MB 초과는 녹화영상(보강/실습 동영상)이 file 타입으로 등록된 것 — 교안 아님.
SIZE_CAP = 80 * 1024 * 1024
MIN_SIZE = 10 * 1024  # 10KB 미만은 embed/에러 페이지(첨부 아님)
MAGIC_EXT = {b"%PDF": ".pdf", b"PK\x03\x04": ".pptx"}


# ── 매니페스트 ────────────────────────────────────────────────────────────────
def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── 순수 헬퍼 (오프라인 테스트 대상) ──────────────────────────────────────────
def _safe(s: str) -> str:
    """경로 segment 새니타이즈 — '/'·'\\' 치환, 선행 '.' 제거, 빈 값은 '무제'.

    수동 배치(_download_files.py)와 동일 규칙이라 이미 받아둔 파일의 stem 과 일치한다.
    """
    return (re.sub(r"[/\\]", "_", s or "").strip().lstrip(".")) or "무제"


def _stem(module_name: str, title: str) -> str:
    """파일명 stem(확장자 제외) — '{주차}_{제목}'. 중복/기존파일 판정 키."""
    return f"{_safe(module_name)}_{_safe(title)}"


def _ext_of(file_name: str, head: bytes) -> str:
    """원본 확장자 결정 — file_name 우선, 없으면 매직바이트(.pdf/.pptx), 그래도 모르면 .bin."""
    if file_name and "." in file_name:
        return "." + file_name.rsplit(".", 1)[1].lower()
    return MAGIC_EXT.get(head[:4], ".bin")


def _is_video_bytes(head: bytes) -> bool:
    """MP4/MOV(ISO BMFF) 매직 — offset 4 의 'ftyp'. 확장자 없는 녹화영상 판별."""
    return head[4:8] == b"ftyp"


def classify_content(content_data: dict) -> tuple[str, str | None]:
    """attendance_items.item_content_data → (판정, content_id).

    판정: "file"(다운로드 시도) | "video"(스트리밍) | "external"(content_id 없음).
    실제 다운로드 가부(대용량/매직)는 내려받기 단계에서 한 번 더 거른다.
    """
    cid = content_data.get("content_id")
    ctype = (content_data.get("content_type") or "").lower()
    if not cid:
        return "external", None
    if ctype in VIDEO_TYPES:
        return "video", cid
    return "file", cid


# ── IO (테스트에서 monkeypatch 하는 경계) ─────────────────────────────────────
async def _resolve_content_data(ctx, html_url: str) -> dict:
    """강의자료 LTI 를 런치해 attendance_items 응답의 item_content_data 를 회수.

    ⚠️ 이 호출이 진도/출결을 기록할 수 있다 — 호출자는 매니페스트/기존파일로
    이미 처리한 항목은 여기까지 오지 않게 막아야 한다.
    """
    pg = await ctx.new_page()
    box: dict = {}

    async def on_resp(r):
        if "attendance_items/" in r.url and r.request.method == "GET":
            try:
                box["d"] = await r.json()
            except Exception:
                pass

    pg.on("response", lambda r: asyncio.create_task(on_resp(r)))
    try:
        await pg.goto(html_url, wait_until="networkidle", timeout=40000)
        await pg.wait_for_timeout(6000)
    except Exception as e:
        logger.debug(f"[자료] LTI 런치 실패({html_url}): {e!r}")
    finally:
        await pg.close()
    return (box.get("d") or {}).get("item_content_data") or {}


async def _download_original(hc: httpx.AsyncClient, content_id: str) -> tuple[str, bytes | None]:
    """commons 원본 파일 다운로드. content-length 선검사로 대용량은 본문을 안 읽는다.

    반환: ("ok", body) | ("big", None) | ("reject", None)
    """
    async with hc.stream("GET", DL_TMPL.format(cid=content_id)) as r:
        disp = r.headers.get("content-disposition", "").lower()
        clen = int(r.headers.get("content-length") or 0)
        if r.status_code != 200 or "attachment" not in disp:
            return "reject", None          # 첨부 응답 아님 → embed/외부 링크
        if clen > SIZE_CAP:
            return "big", None             # 80MB 초과 → 녹화영상, 본문 안 읽음
        body = await r.aread()
    if len(body) < MIN_SIZE:
        return "reject", None
    if len(body) > SIZE_CAP or _is_video_bytes(body):
        return "big", None                 # content-length 부재 시 본문 기준 재확인 + 영상 매직
    return "ok", body


@asynccontextmanager
async def _playwright_context(storage: dict):
    """헤드리스 Chromium 컨텍스트(세션 쿠키 주입)를 yield. 테스트에서 monkeypatch 경계."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.playwright_headless)
        try:
            yield await browser.new_context(storage_state=storage, ignore_https_errors=True)
        finally:
            await browser.close()


async def _existing_stems(course_folder: str) -> set[str]:
    """Obsidian 의 '강의자료/{과목}/' 폴더에 이미 있는 파일 stem 집합(확장자 무관).

    최초 동기화 때 수동 배치로 받아둔 파일을 LTI 런치 없이 건너뛰기 위함.
    Obsidian Local REST API 를 직접 조회(연결 실패 시 빈 집합 → 매니페스트로만 판정).
    """
    base = settings.obsidian_base_url.rstrip("/")
    vpath = settings.obsidian_vault_path.strip("/")
    rel = f"강의자료/{course_folder}/"
    full = f"{vpath}/{rel}" if vpath else rel
    headers = {"Authorization": f"Bearer {settings.obsidian_mcp_auth_code}"}
    verify = "localhost" not in base and "127.0.0.1" not in base
    try:
        async with httpx.AsyncClient(verify=verify, timeout=10) as hc:
            r = await hc.get(f"{base}/vault/{quote(full)}", headers=headers)
            if r.status_code == 200:
                return {f.rsplit(".", 1)[0] for f in r.json().get("files", []) if "." in f}
    except Exception as e:
        logger.debug(f"[자료] 기존 파일 조회 실패({course_folder}): {e!r}")
    return set()


# ── 오케스트레이터 ────────────────────────────────────────────────────────────
async def download_material_files(
    materials: list,
    name_map: dict,
    session_file: str,
    obsidian_mcp_url: str,
    auth_code: str,
) -> dict:
    """강의자료 원본 파일을 받아 Obsidian('강의자료/{과목}/{주차}_{제목}.{확장자}')에 저장.

    materials: app.models.Material 리스트(ExternalTool 항목만 대상).
    반환: {saved, exists, video, external, big, failed} 집계.
    """
    items = [
        (name_map.get(m.course_id, ""), m.course_id, m.id, m.module_name, m.title, m.url)
        for m in materials
        if m.item_type == "ExternalTool" and m.url
    ]
    counts = {"saved": 0, "exists": 0, "video": 0, "external": 0, "big": 0, "failed": 0}
    if not items:
        return counts

    raw = json.loads(Path(session_file).read_text(encoding="utf-8"))
    storage = {"cookies": raw.get("cookies", []), "origins": raw.get("origins", [])}
    jar = httpx.Cookies()
    for ck in raw.get("cookies", []):
        try:
            jar.set(ck["name"], ck["value"], domain=ck.get("domain", "").lstrip("."),
                    path=ck.get("path", "/"))
        except Exception:
            pass

    manifest = load_manifest()
    stem_cache: dict[str, set[str]] = {}
    obs_headers = {"Authorization": f"Bearer {auth_code}"}
    mcp = MCPClientBase(server_url=obsidian_mcp_url, headers=obs_headers)

    async with _playwright_context(storage) as ctx, \
            mcp.session() as s, \
            httpx.AsyncClient(verify=False, timeout=90, cookies=jar,
                              follow_redirects=True) as hc:
        for cn, cid, iid, mn, title, hurl in items:
            key = f"{cid}:{iid}"
            cfolder = _safe(cn)
            stem = _stem(mn, title)

            # 1) 매니페스트 hit — 이미 판정된 항목
            entry = manifest.get(key)
            if entry:
                status = entry.get("status")
                if status == "file":
                    # 파일이 Obsidian 에서 지워졌으면 캐시된 content_id 로 재다운(런치 없음)
                    if cfolder not in stem_cache:
                        stem_cache[cfolder] = await _existing_stems(cfolder)
                    if stem in stem_cache[cfolder]:
                        counts["exists"] += 1
                        continue
                    ok = await _save_one(mcp, s, hc, entry.get("content_id"),
                                         entry.get("file_name", ""), cfolder, stem)
                    counts[ok] += 1
                    if ok == "saved":
                        stem_cache[cfolder].add(stem)
                    continue
                # video/external/big — 다운로드 불가로 확정된 항목, 런치 안 함
                counts[status if status in counts else "external"] += 1
                continue

            # 2) 기존 파일 존재 → LTI 런치 없이 건너뜀(출석 보호), 매니페스트 시드
            if cfolder not in stem_cache:
                stem_cache[cfolder] = await _existing_stems(cfolder)
            if stem in stem_cache[cfolder]:
                manifest[key] = {"status": "file", "preexisting": True}
                counts["exists"] += 1
                continue

            # 3) 신규 항목 — LTI 런치(최초 1회)로 content_id 해석 후 다운로드
            try:
                content_data = await _resolve_content_data(ctx, hurl)
            except Exception as e:
                logger.warning(f"[자료] 해석 실패({title[:24]}): {e!r}")
                counts["failed"] += 1
                continue
            verdict, content_id = classify_content(content_data)
            file_name = content_data.get("file_name") or ""

            if verdict == "external":
                manifest[key] = {"status": "external"}
                counts["external"] += 1
                continue
            if verdict == "video":
                manifest[key] = {"status": "video", "content_id": content_id}
                counts["video"] += 1
                continue

            # file 후보 — 실제 다운로드
            try:
                dl, body = await _download_original(hc, content_id)
            except Exception as e:
                logger.warning(f"[자료] 다운로드 실패({title[:24]}): {e!r}")
                counts["failed"] += 1
                continue
            if dl == "big":
                manifest[key] = {"status": "big", "content_id": content_id}
                counts["big"] += 1
                continue
            if dl != "ok" or not body:
                manifest[key] = {"status": "external", "content_id": content_id}
                counts["external"] += 1
                continue

            # 저장 — file_name(예: '….pptx')으로 확장자 보존(docx/xlsx/ipynb 구분).
            res = await _write_file(mcp, s, body, file_name, cfolder, stem)
            if res == "saved":
                manifest[key] = {"status": "file", "content_id": content_id,
                                 "file_name": file_name, "ext": _ext_of(file_name, body)}
                stem_cache[cfolder].add(stem)
                counts["saved"] += 1
            else:
                counts["failed"] += 1

    save_manifest(manifest)
    logger.info(
        f"[자료] 원본 다운로드 — 신규 {counts['saved']} · 기존 {counts['exists']} · "
        f"영상 {counts['video']} · 외부 {counts['external']} · 대용량 {counts['big']} · "
        f"실패 {counts['failed']}"
    )
    return counts


async def _save_one(mcp, s, hc, content_id, file_name, cfolder, stem) -> str:
    """캐시된 content_id 로 재다운로드 후 저장 — 반환은 counts 키('saved'|'big'|'failed'|'external')."""
    if not content_id:
        return "failed"
    try:
        dl, body = await _download_original(hc, content_id)
    except Exception:
        return "failed"
    if dl == "big":
        return "big"
    if dl != "ok" or not body:
        return "external"
    return "saved" if await _write_file(mcp, s, body, file_name, cfolder, stem) == "saved" else "failed"


async def _write_file(mcp, s, body: bytes, file_name: str, cfolder: str, stem: str) -> str:
    ext = _ext_of(file_name, body)
    rel = f"강의자료/{cfolder}/{stem}{ext}"
    return await mcp.call_tool_in(s, "write_file", {
        "relative_path": rel,
        "content": base64.b64encode(body).decode(),
        "mime_type": "application/octet-stream",
        "encoding": "base64",
    })
