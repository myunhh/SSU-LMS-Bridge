# backend/app/adapter/materials.py
# 주차별 강의 자료 메타 조회 — 파일/영상 본문은 LTI 뷰어 뒤라 메타만 수집
"""주차별 강의 자료 메타 조회.

모듈(주차) 아이템의 제목·유형·딥링크(url) 메타를 수집한다. SSU 강의 파일/영상은
LearningX LTI(ExternalTool, lecture_attendance) 뒤에 있어 본문 다운로드는 범위 밖이라
**메타(주차·제목·유형·LMS 딥링크)** 까지 수집한다. vault_service.sync_obsidian 이 이
메타를 '강의자료/{과목}.md' 의 주차별 목록 + 바로가기 링크로 Obsidian 에 저장한다.
"""
import asyncio

from app.logger import logger

from ..models import Material
from .canvas_client import CanvasClient
from .notices import is_session_unauthorized

# 과목별 자료 동시 조회 상한 (httpx.AsyncClient 동시 요청 안전 — assignments.py 와 동일)
_MATERIAL_CONCURRENCY = 5

# Canvas 모듈 아이템 type → 사용자 친화 한글 라벨.
# SSU 강의자료는 대부분 ExternalTool(LearningX LTI 강의 뷰어)로 들어온다.
MATERIAL_TYPE_LABELS = {
    "ExternalTool": "강의자료",
    "File": "파일",
    "Page": "페이지",
    "Video": "영상",
    "Assignment": "과제",
    "Discussion": "토론",
    "Quiz": "퀴즈",
    "ExternalUrl": "링크",
    "SubHeader": "구분",
}


def material_type_label(item_type: str | None) -> str:
    """모듈 아이템 type 을 한글 라벨로. 미등록 type 은 원문 그대로."""
    return MATERIAL_TYPE_LABELS.get(item_type or "", item_type or "자료")


async def list_materials(client: CanvasClient, course_id: int) -> list[Material]:
    try:
        modules = await client.get_all_pages(
            f"/courses/{course_id}/modules",
            params={"per_page": 100},
            use_canvas=True,
        )
    except Exception as e:
        # Canvas(쿠키)와 LearningX(Bearer)는 인증이 독립적이므로 401 이어도 폴백 시도.
        # LearningX 호출마저 실패하면 그 예외가 그대로 전파된다 (401 → 전역 핸들러).
        logger.debug(f"과목 {course_id} 모듈 목록 Canvas 실패 → LearningX 폴백: {e!r}")
        modules = await client.get(
            f"/courses/{course_id}/modules",
            params={"per_page": 100},
        )

    if not isinstance(modules, list):
        modules = modules.get("data", modules.get("modules", []))

    results = []
    for mod in modules:
        mod_id = mod.get("id")
        mod_name = mod.get("name", "")

        try:
            items = await client.get_all_pages(
                f"/courses/{course_id}/modules/{mod_id}/items",
                params={"per_page": 100},
                use_canvas=True,
            )
        except Exception as e:
            logger.debug(f"과목 {course_id} 모듈 {mod_id} 아이템 Canvas 실패 → LearningX 폴백: {e!r}")
            try:
                items = await client.get(
                    f"/courses/{course_id}/modules/{mod_id}/items",
                    params={"per_page": 100},
                )
            except Exception as e2:
                if is_session_unauthorized(e2):
                    raise  # 두 호스트 모두 401 → 세션 만료. 전역 핸들러(→ '재로그인 필요')로 전파
                logger.debug(f"과목 {course_id} 모듈 {mod_id} 아이템 조회 실패, 건너뜀: {e2!r}")
                continue

        if not isinstance(items, list):
            items = items.get("data", [])

        for item in items:
            results.append(Material(
                id=item.get("id", 0),
                course_id=course_id,
                module_name=mod_name,
                title=item.get("title", ""),
                item_type=item.get("type", ""),
                # ⚠️ Canvas 모듈 아이템의 `url` 은 API 엔드포인트(JSON)라 사용자 링크로 부적합.
                #    사용자용 딥링크인 html_url → external_url 을 우선한다.
                url=item.get("html_url") or item.get("external_url") or item.get("url"),
                position=item.get("position", 0),
            ))

    return results


async def list_all_materials(client: CanvasClient, course_ids: list[int]) -> list[Material]:
    """전 과목의 주차별 강의자료 메타를 병렬 수집 (assignments.list_all_deadlines 패턴).

    과목별 list_materials 를 gather(return_exceptions=True)로 병렬 호출하되,
    세션 만료(401)만 골라 re-raise 해 401 전파 정책을 유지한다. 한 과목 실패는
    로그 후 skip(부분 결과 허용). 반환은 (course_id, module position, item position)
    순으로 정렬해 주차/순서가 보존되게 한다.
    """
    sem = asyncio.Semaphore(_MATERIAL_CONCURRENCY)

    async def _fetch(cid: int) -> list[Material]:
        async with sem:
            return await list_materials(client, cid)

    results = await asyncio.gather(
        *(_fetch(cid) for cid in course_ids), return_exceptions=True
    )

    all_materials: list[Material] = []
    for cid, result in zip(course_ids, results, strict=True):
        if isinstance(result, BaseException):
            if is_session_unauthorized(result):
                raise result
            logger.warning(f"과목 {cid} 강의자료 조회 실패, 건너뜀: {result!r}")
            continue
        all_materials.extend(result)
    return all_materials
