"""이메일 알림 서비스 테스트 (#9) — 전부 오프라인.

검증 항목
---------
- upcoming_deadlines: now~now+N시간 경계값, 미제출 필터, dict/모델 양쪽 입력
- new_notices: since 기준 diff, since=None 폭주 방지, 미래/경계 제외
- render_digest: 빈 입력 None, 제목/본문 조립
- smtp_configured / send_email: 미설정 no-op(예외 금지), smtplib monkeypatch 발송

네트워크/실제 SMTP 호출 없음 — smtplib.SMTP 를 가짜로 대체한다.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.config import settings
from app.services import notify_service

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    """aware datetime → Canvas 스타일 'Z' 접미 ISO 문자열."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── upcoming_deadlines 경계값 ────────────────────────────────


def test_deadline_within_window_included():
    a = [{"title": "과제A", "due": _iso(NOW + timedelta(hours=5)), "submitted": False}]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert len(out) == 1
    assert out[0]["title"] == "과제A"
    assert 4.9 < out[0]["hours_left"] < 5.1


def test_deadline_exactly_at_now_boundary_included():
    """due == now 는 포함(>= now)."""
    a = [{"title": "지금마감", "due": _iso(NOW), "submitted": False}]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert len(out) == 1


def test_deadline_exactly_at_upper_boundary_included():
    """due == now+N 은 포함(<= 경계)."""
    a = [{"title": "경계", "due": _iso(NOW + timedelta(hours=24)), "submitted": False}]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert len(out) == 1


def test_deadline_just_past_upper_boundary_excluded():
    a = [{"title": "초과", "due": _iso(NOW + timedelta(hours=24, minutes=1)), "submitted": False}]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert out == []


def test_already_past_due_excluded():
    a = [{"title": "이미마감", "due": _iso(NOW - timedelta(hours=1)), "submitted": False}]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert out == []


def test_submitted_assignment_excluded():
    a = [{"title": "제출함", "due": _iso(NOW + timedelta(hours=2)), "submitted": True}]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert out == []


def test_missing_or_invalid_due_excluded():
    a = [
        {"title": "due없음", "due": None, "submitted": False},
        {"title": "파싱불가", "due": "not-a-date", "submitted": False},
    ]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert out == []


def test_deadlines_sorted_by_urgency():
    a = [
        {"title": "늦은", "due": _iso(NOW + timedelta(hours=10)), "submitted": False},
        {"title": "급한", "due": _iso(NOW + timedelta(hours=2)), "submitted": False},
    ]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert [o["title"] for o in out] == ["급한", "늦은"]


def test_deadlines_accept_pydantic_model():
    """dict 뿐 아니라 Assignment 모델(due_at/submitted 속성)도 받는다."""
    from app.models import Assignment

    a = [Assignment(
        id=1, course_id=10, title="모델과제",
        due_at=_iso(NOW + timedelta(hours=3)), submitted=False,
    )]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert len(out) == 1 and out[0]["title"] == "모델과제"


def test_naive_due_treated_as_utc():
    """타임존 없는 due 문자열도 UTC 로 간주해 파싱(크래시 없이 비교)."""
    a = [{"title": "naive", "due": "2026-06-13T15:00:00", "submitted": False}]
    out = notify_service.upcoming_deadlines(a, within_hours=24, now=NOW)
    assert len(out) == 1


# ── new_notices ──────────────────────────────────────────────


def test_new_notices_since_none_returns_empty():
    """최초 스캔(since=None)은 빈 리스트 — 누적 공지 폭주 방지."""
    n = [{"title": "공지", "date": _iso(NOW - timedelta(hours=1))}]
    assert notify_service.new_notices(n, since=None, now=NOW) == []


def test_new_notices_after_since_included():
    since = NOW - timedelta(hours=2)
    n = [
        {"title": "신규", "date": _iso(NOW - timedelta(hours=1))},
        {"title": "오래된", "date": _iso(NOW - timedelta(hours=5))},
    ]
    out = notify_service.new_notices(n, since=since, now=NOW)
    assert [o["title"] for o in out] == ["신규"]


def test_new_notices_equal_since_excluded():
    """posted == since 는 제외(> since 만 통과)."""
    since = NOW - timedelta(hours=2)
    n = [{"title": "경계", "date": _iso(since)}]
    assert notify_service.new_notices(n, since=since, now=NOW) == []


def test_new_notices_future_excluded():
    """미래 시각 공지(시계 오차)는 제외."""
    since = NOW - timedelta(hours=2)
    n = [{"title": "미래", "date": _iso(NOW + timedelta(hours=1))}]
    assert notify_service.new_notices(n, since=since, now=NOW) == []


def test_new_notices_accept_pydantic_model():
    from app.models import Notice

    since = NOW - timedelta(hours=2)
    n = [Notice(id=1, course_id=10, title="모델공지", posted_at=_iso(NOW - timedelta(hours=1)))]
    out = notify_service.new_notices(n, since=since, now=NOW)
    assert len(out) == 1 and out[0]["title"] == "모델공지"


# ── render_digest ────────────────────────────────────────────


def test_render_digest_empty_returns_none():
    assert notify_service.render_digest([], []) is None


def test_render_digest_deadlines_only():
    dl = [{"title": "과제A", "course_name": "고급프로그래밍", "due": "2026-06-13T17:00:00Z", "hours_left": 5.0}]
    subject, body = notify_service.render_digest(dl, [])
    assert "마감 임박" in subject
    assert "과제A" in body and "고급프로그래밍" in body


def test_render_digest_both():
    dl = [{"title": "과제A", "course_name": "", "due": "x", "hours_left": 1.0}]
    no = [{"title": "새공지", "course_name": "DB", "date": "2026-06-13T10:00:00Z"}]
    subject, body = notify_service.render_digest(dl, no)
    assert "마감 임박" in subject and "새 공지" in subject
    assert "새공지" in body


# ── smtp_configured / send_email ─────────────────────────────


@pytest.fixture(autouse=True)
def smtp_unset(monkeypatch):
    """기본은 SMTP 미설정 상태로 격리 (실제 .env 값과 분리)."""
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")
    monkeypatch.setattr(settings, "notify_from", "")
    monkeypatch.setattr(settings, "notify_to", "")


def _configure_smtp(monkeypatch, **over):
    monkeypatch.setattr(settings, "smtp_host", over.get("host", "smtp.example.com"))
    monkeypatch.setattr(settings, "smtp_port", over.get("port", 587))
    monkeypatch.setattr(settings, "smtp_user", over.get("user", "bot@example.com"))
    monkeypatch.setattr(settings, "smtp_password", over.get("password", "pw"))
    monkeypatch.setattr(settings, "notify_from", over.get("notify_from", "bot@example.com"))
    monkeypatch.setattr(settings, "notify_to", over.get("notify_to", "me@example.com"))


def test_smtp_configured_false_when_unset():
    assert notify_service.smtp_configured() is False


def test_smtp_configured_false_for_placeholder(monkeypatch):
    _configure_smtp(monkeypatch, host="smtp_xxxx")
    assert notify_service.smtp_configured() is False


def test_smtp_configured_true_when_set(monkeypatch):
    _configure_smtp(monkeypatch)
    assert notify_service.smtp_configured() is True


def test_send_email_noop_when_unconfigured():
    """미설정이면 발송하지 않고 False — 예외를 던지지 않는다."""
    assert notify_service.send_email("제목", "본문") is False


class _FakeSMTP:
    """smtplib.SMTP 대역 — 호출을 기록한다 (네트워크 없음)."""
    instances: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = None
        self.sent = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg, to_addrs=None):
        self.sent.append((msg, to_addrs))


def test_send_email_uses_smtplib(monkeypatch):
    _FakeSMTP.instances = []
    _configure_smtp(monkeypatch, notify_to="a@example.com, b@example.com")
    monkeypatch.setattr(notify_service.smtplib, "SMTP", _FakeSMTP)

    ok = notify_service.send_email("[LMS] 테스트", "본문 라인")
    assert ok is True
    assert len(_FakeSMTP.instances) == 1
    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp.example.com" and smtp.port == 587
    assert smtp.started_tls is True
    assert smtp.logged_in == ("bot@example.com", "pw")
    # 다중 수신자가 콤마 분리돼 전달됐는지
    assert len(smtp.sent) == 1
    _msg, to_addrs = smtp.sent[0]
    assert to_addrs == ["a@example.com", "b@example.com"]
    assert _msg["Subject"] == "[LMS] 테스트"


def test_send_email_skips_login_without_credentials(monkeypatch):
    """user/password 가 없으면 login 시도 없이 발송 (내부 릴레이 시나리오)."""
    _FakeSMTP.instances = []
    _configure_smtp(monkeypatch, user="", password="")
    monkeypatch.setattr(notify_service.smtplib, "SMTP", _FakeSMTP)

    ok = notify_service.send_email("제목", "본문")
    assert ok is True
    assert _FakeSMTP.instances[0].logged_in is None


def test_send_email_failure_returns_false_no_raise(monkeypatch):
    """발송 중 예외가 나도 False 만 반환(본 흐름 보호) — 밖으로 던지지 않는다."""
    _configure_smtp(monkeypatch)

    class _BoomSMTP(_FakeSMTP):
        def send_message(self, msg, to_addrs=None):
            raise OSError("connection refused")

    monkeypatch.setattr(notify_service.smtplib, "SMTP", _BoomSMTP)
    assert notify_service.send_email("제목", "본문") is False


def test_starttls_unsupported_still_sends(monkeypatch):
    """STARTTLS 미지원 서버여도 평문으로 계속 진행한다."""
    _FakeSMTP.instances = []
    _configure_smtp(monkeypatch)

    class _NoTLS(_FakeSMTP):
        def starttls(self):
            raise notify_service.smtplib.SMTPException("not supported")

    monkeypatch.setattr(notify_service.smtplib, "SMTP", _NoTLS)
    assert notify_service.send_email("제목", "본문") is True
    assert _FakeSMTP.instances[0].sent  # 발송은 됐다


# ── scan_and_notify: 진행 중 sync 에 양보 (#5) ───────────────


async def test_scan_skips_when_sync_running(monkeypatch, tmp_path):
    """동기화 진행 중이면 스캔을 양보한다 — 세션 파일 동시 쓰기 회피(#5).

    run_scheduled_session_refresh 와 동일 정책. SMTP 설정·세션 파일 존재 등
    선행 가드를 모두 통과시킨 뒤, sync 진행 플래그만 켜고 스캔이 즉시 빠지는지 본다.
    Playwright(load_session)는 한 번도 호출되면 안 된다(가드가 그 앞에서 차단).
    """
    import json
    from datetime import datetime

    from app.adapter.auth import SSULMSAuthPlaywright
    from app.api.routes import sync as sync_routes

    # SMTP 설정 + 세션 파일 격리(test_session_refresh_job 패턴)
    _configure_smtp(monkeypatch)
    monkeypatch.setattr(settings, "session_cache_path", str(tmp_path / "session_state.json"))
    path = settings.session_cache_abspath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"saved_at": datetime.now().isoformat(), "user_info": {"name": "테스트"}}),
        encoding="utf-8",
    )

    # load_session 이 불리면 테스트 실패 — 가드가 그 앞에서 막아야 한다.
    called = {"load": 0}

    async def _spy_load(self, *a, **k):
        called["load"] += 1
        return True

    monkeypatch.setattr(SSULMSAuthPlaywright, "load_session", _spy_load)

    sync_routes._state["running"] = True
    try:
        result = await notify_service.scan_and_notify()
    finally:
        sync_routes._state["running"] = False

    assert result == {"skipped": "sync_running"}
    assert called["load"] == 0  # Playwright 세션 검증까지 가지 않았다
