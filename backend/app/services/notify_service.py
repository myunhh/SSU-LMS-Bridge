# backend/app/services/notify_service.py
# 이메일 알림 서비스 — 마감 임박 과제 / 신규 공지 알림 (#9)
# ──────────────────────────────────────────────────────────────────────────────
# 범위: **이메일(SMTP) 알림만** 구현한다. 실제 푸시(FCM/웹푸시)는 프론트
# service worker 까지 필요해 이 단계 범위 밖이다 (settings.jsx '푸시'·'데스크탑'
# 칩은 계속 비활성). 데스크탑 알림도 마찬가지.
#
# 구성:
#   - 순수 로직 (네트워크/시간 부작용 없음, 테스트 용이):
#       · upcoming_deadlines() — due_at 이 now ~ now+N시간 이내인 미제출 과제 추림
#       · new_notices()        — 기준 시각(직전 스캔) 이후 게시된 신규 공지 추림
#       · render_digest()      — 위 결과를 사람이 읽을 이메일 본문(평문)으로 조립
#   - 부작용 함수:
#       · send_email()         — SMTP 발송. 미설정(빈값/placeholder)이면 no-op +
#                                로그만 (Notion/Obsidian 의 is_configured 가드와
#                                동일 정책 — 예외를 밖으로 던지지 않는다).
#
# main.py 의 APScheduler IntervalTrigger job(scan_and_notify)이 주기적으로
# '마감 임박/신규 공지 스캔 → 발송'을 수행한다. SMTP 미설정이면 job 등록 자체를
# 건너뛴다 (session_refresh job 등록 패턴 참고).
# ──────────────────────────────────────────────────────────────────────────────
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate

from app.config import is_configured, settings
from app.logger import logger


# ──────────────────────────────────────────────────────────────────────────────
# 시간 파싱 헬퍼
# ──────────────────────────────────────────────────────────────────────────────
def _parse_iso(value: str | None) -> datetime | None:
    """Canvas ISO8601 문자열(예: '2026-06-15T14:00:00Z')을 aware datetime 으로.

    'Z' 접미사를 '+00:00' 으로 치환해 fromisoformat 이 받게 한다(models.py 동일 정책).
    naive(타임존 없음) 값은 UTC 로 간주한다. 파싱 불가면 None.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _now() -> datetime:
    """현재 시각(UTC aware). 테스트에서 monkeypatch 하기 쉽게 분리."""
    return datetime.now(UTC)


# ──────────────────────────────────────────────────────────────────────────────
# 순수 로직 — 알림 대상 계산
# ──────────────────────────────────────────────────────────────────────────────
def upcoming_deadlines(
    assignments: list,
    *,
    within_hours: int = 24,
    now: datetime | None = None,
) -> list[dict]:
    """due_at 이 now ~ now+within_hours 이내인 **미제출** 과제만 추린다.

    경계값 규칙(중복 알림/조기 알림 방지):
      · 이미 마감(due < now)된 과제는 제외한다(>= now 만 통과).
      · 정확히 now+within_hours 인 과제는 **포함**한다(<= 경계).
      · submitted=True 인 과제는 제외한다.
      · due_at 이 없거나 파싱 불가면 제외한다.

    입력 항목은 dict(과제 payload, sync.py 의 assign_payload) 또는 Assignment
    모델 모두 받는다 — getattr/[] 양쪽을 _field 로 흡수한다. 반환은 알림 본문
    조립용 정규화 dict(title/course_name/due/hours_left) 리스트(마감 임박순).
    """
    ref = now or _now()
    deadline = ref + timedelta(hours=within_hours)
    out: list[dict] = []
    for a in assignments:
        if _field(a, "submitted", False):
            continue
        due_raw = _field(a, "due", None) or _field(a, "due_at", None)
        due = _parse_iso(due_raw)
        if due is None:
            continue
        if due < ref or due > deadline:
            continue
        out.append({
            "title": _field(a, "title", "") or "무제",
            "course_name": _field(a, "course_name", "") or "",
            "due": due_raw,
            "hours_left": (due - ref).total_seconds() / 3600.0,
        })
    out.sort(key=lambda x: x["hours_left"])
    return out


def new_notices(
    notices: list,
    *,
    since: datetime | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """기준 시각(since, 직전 스캔 시각) 이후 게시된 신규 공지만 추린다.

    경계값 규칙:
      · since 가 None 이면(최초 스캔) 신규 판정 기준이 없으므로 빈 리스트 —
        기존에 쌓인 공지 전체를 첫 스캔에 폭발적으로 발송하는 사고를 막는다.
      · posted_at == since 인 공지는 제외한다(> since 만 통과 — since 시점에
        이미 본 것으로 간주, 중복 발송 방지).
      · 미래 시각(posted_at > now)인 공지는 시계 오차/오류로 보고 제외한다.
      · posted_at 이 없거나 파싱 불가면 제외한다.

    입력 항목은 dict(공지 payload) 또는 Notice 모델 모두 받는다.
    반환은 정규화 dict(title/course_name/date) 리스트(최신순).
    """
    if since is None:
        return []
    ref = now or _now()
    out: list[dict] = []
    for n in notices:
        date_raw = _field(n, "date", None) or _field(n, "posted_at", None)
        posted = _parse_iso(date_raw)
        if posted is None:
            continue
        if posted <= since or posted > ref:
            continue
        out.append({
            "title": _field(n, "title", "") or "무제",
            "course_name": _field(n, "course_name", "") or "",
            "date": date_raw,
        })
    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return out


def _field(obj, key: str, default=None):
    """dict 와 Pydantic 모델(속성 접근)을 동일하게 흡수하는 필드 추출 헬퍼."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _with_course_name(items: list, name_map: dict) -> list[dict]:
    """course_id 만 가진 항목(Assignment/Notice 모델 또는 dict)에 과목명을 채운다.

    upcoming_deadlines/new_notices 가 정규화 dict 에서 course_name 을 읽어
    render_digest 의 '[과목]' 접두를 채울 수 있게, 모델/ dict 를 dict 로 풀어
    name_map(course_id→과목명) 으로 course_name 을 주입한다. course_id 가
    맵에 없으면(폐강/매핑 누락) 빈 문자열로 둔다 — 제목만 표시되며 크래시 없음.
    이미 course_name 이 채워진 항목은 그대로 보존한다.
    """
    out: list[dict] = []
    for it in items:
        base = it if isinstance(it, dict) else it.model_dump()
        if not base.get("course_name"):
            base = {**base, "course_name": name_map.get(_field(it, "course_id"), "")}
        out.append(base)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 이메일 본문 조립 (순수)
# ──────────────────────────────────────────────────────────────────────────────
def render_digest(deadlines: list[dict], notices: list[dict]) -> tuple[str, str] | None:
    """알림 대상 → (제목, 본문) 평문 이메일. 보낼 게 없으면 None.

    sync 후 호출되든 주기 스캔으로 호출되든 동일한 형식을 쓴다.
    """
    if not deadlines and not notices:
        return None

    parts: list[str] = []
    if deadlines:
        parts.append(f"■ 마감 임박 과제 {len(deadlines)}건")
        for d in deadlines:
            h = max(0, round(d["hours_left"]))
            course = f"[{d['course_name']}] " if d["course_name"] else ""
            parts.append(f"  · {course}{d['title']} — 약 {h}시간 후 마감 (마감 {d['due']})")
        parts.append("")
    if notices:
        parts.append(f"■ 새 공지사항 {len(notices)}건")
        for n in notices:
            course = f"[{n['course_name']}] " if n["course_name"] else ""
            parts.append(f"  · {course}{n['title']} ({n['date']})")
        parts.append("")

    n_dl, n_no = len(deadlines), len(notices)
    if n_dl and n_no:
        subject = f"[LMS] 마감 임박 {n_dl}건 · 새 공지 {n_no}건"
    elif n_dl:
        subject = f"[LMS] 마감 임박 과제 {n_dl}건"
    else:
        subject = f"[LMS] 새 공지사항 {n_no}건"

    parts.append("— SSU LMS Bridge 자동 알림")
    return subject, "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# 발송 (부작용)
# ──────────────────────────────────────────────────────────────────────────────
def smtp_configured() -> bool:
    """SMTP 발송에 필요한 최소 설정이 채워졌는지 (placeholder/빈값 제외).

    호스트·발신·수신 주소가 모두 있어야 발송 가능. 인증(user/password)은 일부
    내부 릴레이에선 생략될 수 있어 필수 조건에서 제외한다(있으면 login 시도).
    """
    return is_configured(
        settings.smtp_host,
        settings.notify_from,
        settings.notify_to,
    )


def send_email(subject: str, body: str) -> bool:
    """SMTP 로 평문 이메일 발송. 미설정이면 no-op(로그만), 성공 시 True.

    Notion/Obsidian 의 is_configured 가드와 동일하게, 미설정·발송 실패를
    **예외로 밖에 던지지 않는다** — 알림은 부가 기능이라 본 흐름(sync/스케줄러)을
    깨면 안 된다. 발송했으면 True, 미설정/실패면 False.
    """
    if not smtp_configured():
        logger.info("[Notify] SMTP 미설정 → 이메일 발송 건너뜀")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.notify_from
    # NOTIFY_TO 는 콤마 구분 다중 수신 허용
    recipients = [r.strip() for r in str(settings.notify_to).split(",") if r.strip()]
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            # STARTTLS 지원 서버면 평문 협상 후 암호화로 승급 (587 일반)
            try:
                smtp.starttls()
            except smtplib.SMTPException:
                # TLS 미지원(내부 릴레이 등)면 평문 그대로 진행
                logger.debug("[Notify] STARTTLS 미지원 — 평문 발송")
            if is_configured(settings.smtp_user, settings.smtp_password):
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg, to_addrs=recipients)
    except Exception as e:
        # 발송 실패도 본 흐름을 막지 않는다 (로그만)
        logger.warning(f"[Notify] 이메일 발송 실패: {e}")
        return False

    logger.info(f"[Notify] 이메일 발송 완료 → {len(recipients)}명: {subject}")
    return True


# ──────────────────────────────────────────────────────────────────────────────
# 스캔 + 발송 오케스트레이션 (APScheduler job 본체)
# ──────────────────────────────────────────────────────────────────────────────
# 직전 스캔 시각을 프로세스 메모리에 보관 — new_notices 의 'since' 기준.
# (재시작 시 None 으로 초기화되어 최초 스캔은 공지를 보내지 않는다 — 폭주 방지)
_state: dict = {"last_scan_at": None}


async def scan_and_notify() -> dict:
    """LMS 데이터를 수집해 마감 임박/신규 공지를 계산하고 이메일로 발송.

    APScheduler IntervalTrigger job 본체. SMTP 미설정이면 애초에 job 이 등록되지
    않으므로 여기까진 오지 않지만, 방어적으로 한 번 더 확인한다. 세션 파일이 없거나
    (미로그인) 세션이 만료됐으면 조용히 건너뛴다 — 알림은 부가 기능이라 예외를
    밖으로 던지지 않는다(스케줄러가 죽지 않게).

    반환은 관측/테스트용 요약 dict.
    """
    # 지연 import — 무거운 어댑터/Playwright 의존을 모듈 로드 시점에서 분리
    # (test_notify_service.py 가 이 함수를 건드리지 않고 순수 로직만 검증 가능).
    from app.adapter.assignments import list_all_deadlines
    from app.adapter.auth import SSULMSAuthPlaywright
    from app.adapter.canvas_client import CanvasClient
    from app.adapter.courses import list_courses
    from app.adapter.notices import list_all_notices

    if not smtp_configured():
        logger.debug("[Notify] SMTP 미설정 → 스캔 건너뜀")
        return {"skipped": "unconfigured"}

    path = settings.session_cache_abspath
    if not path.exists():
        logger.debug("[Notify] 세션 파일 없음(미로그인) → 스캔 건너뜀")
        return {"skipped": "no_session"}

    # 동기화 진행 중이면 스캔을 양보한다 — load_session(Playwright)이 세션 파일을
    # 다시 쓰므로, sync 와 동시에 돌면 세션 파일 동시 쓰기가 발생한다(#5).
    # run_scheduled_session_refresh 와 동일 정책. 순환 import(sync→notify_service)를
    # 피하려 함수 내부에서 지연 import 한다(lms.py 의 sync_routes 참조 패턴).
    from app.api.routes import sync as sync_routes

    if sync_routes.is_sync_running():
        logger.info("[Notify] 동기화 진행 중 → 스캔 건너뜀 (세션 파일 동시 쓰기 회피)")
        return {"skipped": "sync_running"}

    auth = SSULMSAuthPlaywright(
        session_file=str(path),
        headless=settings.playwright_headless,
    )
    try:
        ok = await auth.load_session()
    except Exception:
        logger.warning("[Notify] 세션 검증 중 오류 → 스캔 건너뜀")
        return {"skipped": "session_error"}
    if not ok:
        logger.info("[Notify] 세션 만료 → 스캔 건너뜀 (재로그인 필요)")
        return {"skipped": "session_expired"}

    try:
        async with CanvasClient(session_file=str(path)) as client:
            # list_courses 로 강의 목록을 한 번에 받아 {id: name} 맵을 만든다.
            # course_id 만 가진 Assignment/Notice 모델을 디제스트로 넘기기 전에
            # 과목명을 채워 render_digest 의 '[과목]' 접두가 비지 않게 하기 위함이다.
            # (모델에는 course_name 필드가 없어 _field 가 ''로 폴백하던 갭 보정.)
            courses = await list_courses(client)
            name_map = {c.id: c.name for c in courses}
            course_ids = list(name_map.keys())
            assignments = await list_all_deadlines(client, course_ids)
            notices = await list_all_notices(client, course_ids)
    except Exception:
        logger.exception("[Notify] LMS 데이터 수집 실패 → 스캔 건너뜀")
        return {"skipped": "collect_error"}

    now = _now()
    deadlines = upcoming_deadlines(
        _with_course_name(assignments, name_map),
        within_hours=settings.notify_deadline_hours,
        now=now,
    )
    fresh = new_notices(
        _with_course_name(notices, name_map), since=_state["last_scan_at"], now=now
    )
    _state["last_scan_at"] = now

    digest = render_digest(deadlines, fresh)
    sent = False
    if digest:
        subject, body = digest
        sent = send_email(subject, body)
    else:
        logger.info("[Notify] 알림 대상 없음")

    return {
        "deadlines": len(deadlines),
        "new_notices": len(fresh),
        "sent": sent,
    }
