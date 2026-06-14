# backend/app/services/vault_service.py
# Obsidian Vault 동기화 서비스 — 공지/과제를 markdown 노트로 push.
# (SSU 강의자료 파일은 LTI 뷰어 뒤라 다운로드 범위 밖 — Obsidian 엔 공지/과제만 저장한다.)
# perform_sync(routes/sync.py)가 Obsidian MCP 가 설정된 경우에만 호출한다.
import hashlib
import json

from loguru import logger

from app.config import settings
from app.mcp_client.base import MCPClientBase

# manifest 는 루트 .cache/ 아래 절대경로로 고정 (uvicorn 실행 CWD 와 무관)
MANIFEST_PATH = settings.root_dir / ".cache" / "vault_manifest.json"


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict):
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_segment(s: str) -> str:
    """경로 segment 새니타이즈 — '/'·'\\' 치환, 선행 '.' 제거, 빈 값은 '무제' 대체.

    제목에 '/' 가 있으면 의도치 않은 하위 폴더·경로 탈출이 생긴다
    (obsidian_server._vault_url 은 빈 segment 만 거르지 '/' 포함 segment 는 분해함).
    """
    cleaned = (s or "").replace("/", "_").replace("\\", "_").strip()
    cleaned = cleaned.lstrip(".").strip()
    return cleaned or "무제"


def _notice_markdown(n: dict) -> str:
    """공지 dict → 결정적 markdown (동일 입력→동일 바이트, manifest 해시 skip 용)."""
    lines = [
        f"# {n.get('title', '무제')}",
        "",
        f"- 과목: {n.get('course_name', '')}",
        f"- 날짜: {n.get('date', '') or ''}",
        f"- 고정: {'예' if n.get('pinned') else '아니오'}",
        f"- 읽음: {'아니오' if n.get('unread', True) else '예'}",
        "",
        (n.get("text") or "").strip(),
        "",
    ]
    return "\n".join(lines)


def _assignment_markdown(a: dict) -> str:
    """과제 dict → 결정적 markdown (동일 입력→동일 바이트, manifest 해시 skip 용)."""
    lines = [
        f"# {a.get('title', '무제')}",
        "",
        f"- 과목: {a.get('course_name', '')}",
        f"- 마감일: {a.get('due', '') or ''}",
        f"- 유형: {a.get('type', '기타')}",
        f"- 배점: {a.get('weight', 0)}",
        f"- 제출완료: {'예' if a.get('submitted') else '아니오'}",
        "",
        (a.get("text") or "").strip(),
        "",
    ]
    return "\n".join(lines)


def _materials_markdown(course_name: str, items: list) -> str:
    """한 과목의 강의자료 메타 → 주차별 목록 markdown (결정적, manifest 해시 skip 용).

    SSU 강의 파일/영상 본문은 LTI 뷰어 뒤라 받지 못하므로, 주차(module_name)별로
    제목·유형·LMS 바로가기 딥링크(url)를 모은 인덱스 노트를 만든다. 사용자는
    Obsidian 에서 주차별 자료를 보고 링크를 눌러 LMS 에서 연다.
    """
    lines = [
        f"# {course_name} 강의자료",
        "",
        "> 주차별 강의자료 목록입니다. 파일·영상 본문은 링크(LMS 뷰어)에서 열립니다.",
        "",
    ]
    # 주차(module_name)별 그룹 — 입력(모듈) 순서를 보존한다.
    by_module: dict[str, list] = {}
    order: list[str] = []
    for it in items:
        mod = it.get("module_name") or "기타"
        if mod not in by_module:
            by_module[mod] = []
            order.append(mod)
        by_module[mod].append(it)

    for mod in order:
        lines.append(f"## {mod}")
        for it in sorted(by_module[mod], key=lambda x: x.get("position", 0)):
            title = it.get("title") or "무제"
            url = it.get("url") or ""
            typ = it.get("type") or "자료"
            lines.append(f"- [{title}]({url}) · {typ}" if url else f"- {title} · {typ}")
        lines.append("")
    return "\n".join(lines)


async def sync_obsidian(
    notices: list,
    assignments: list,
    obsidian_mcp_url: str,
    auth_code: str,
    materials: list | None = None,
) -> dict:
    """공지/과제/강의자료를 Obsidian Vault 에 markdown 노트로 push (단일 SSE 세션).

    경로:
      - 공지/{과목}/{제목}.md · 과제/{과목}/{제목}.md (항목당 1파일)
      - 강의자료/{과목}.md (과목당 1파일 — 주차별 자료 목록 + LMS 딥링크)
    manifest(sha256) 로 변경 없는 노트는 건너뛴다(skipped). 개별 노트 실패는
    허용하고 failed 로 집계한다 (sync_notion 과 동일 정책 — 전체 중단 안 함).
    """
    mcp = MCPClientBase(
        server_url=obsidian_mcp_url,
        headers={"Authorization": f"Bearer {auth_code}"},
    )

    manifest = load_manifest()
    saved = skipped = failed = 0

    # (폴더, 항목, markdown 생성기) 묶음으로 공지/과제를 동일 루프로 처리
    groups = [
        ("공지", notices, _notice_markdown),
        ("과제", assignments, _assignment_markdown),
    ]

    # 단일 SSE 세션으로 전체 push 처리 — 항목마다 재연결하지 않는다.
    async with mcp.session() as s:
        for folder, items, render in groups:
            for item in items:
                course = _safe_segment(item.get("course_name", ""))
                title = _safe_segment(item.get("title", ""))
                rel_path = f"{folder}/{course}/{title}.md"
                md = render(item)
                digest = sha256(md.encode("utf-8"))

                # 변경 없음 → skip
                if manifest.get(rel_path) == digest:
                    skipped += 1
                    continue

                try:
                    result = await mcp.call_tool_in(s, "write_file", {
                        "relative_path": rel_path,
                        "content": md,
                        "mime_type": "text/markdown",
                        "encoding": "utf-8",
                    })
                except Exception as e:
                    logger.warning(f"[Obsidian] 저장 실패 ({rel_path}): {e}")
                    failed += 1
                    continue

                if result == "saved":
                    manifest[rel_path] = digest
                    saved += 1
                else:
                    failed += 1

        # 강의자료 — 과목당 1파일(주차별 목록). 과목별로 묶어 '강의자료/{과목}.md' 로 저장.
        by_course: dict[str, list] = {}
        course_order: list[str] = []
        for m in materials or []:
            cn = m.get("course_name", "") or "무제"
            if cn not in by_course:
                by_course[cn] = []
                course_order.append(cn)
            by_course[cn].append(m)

        for cn in course_order:
            rel_path = f"강의자료/{_safe_segment(cn)}.md"
            md = _materials_markdown(cn, by_course[cn])
            digest = sha256(md.encode("utf-8"))
            if manifest.get(rel_path) == digest:
                skipped += 1
                continue
            try:
                result = await mcp.call_tool_in(s, "write_file", {
                    "relative_path": rel_path,
                    "content": md,
                    "mime_type": "text/markdown",
                    "encoding": "utf-8",
                })
            except Exception as e:
                logger.warning(f"[Obsidian] 저장 실패 ({rel_path}): {e}")
                failed += 1
                continue
            if result == "saved":
                manifest[rel_path] = digest
                saved += 1
            else:
                failed += 1

    save_manifest(manifest)
    logger.info(f"[Obsidian] 저장 {saved}건 · 변경없음 {skipped}건 · 실패 {failed}건")
    return {"saved": saved, "skipped": skipped, "failed": failed}
