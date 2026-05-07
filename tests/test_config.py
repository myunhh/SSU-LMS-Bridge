"""
tests/test_config.py
──────────────────────────────────────────────────────────────
설정(config.py) 단위 테스트.
"""

from __future__ import annotations

import os

import pytest


def test_settings_loads_from_env(monkeypatch):
    """환경 변수에서 설정을 정상적으로 읽어오는지 확인."""
    monkeypatch.setenv("LMS_USERNAME", "20231234")
    monkeypatch.setenv("LMS_PASSWORD", "secret123")
    monkeypatch.setenv("LMS_BASE_URL", "https://lms.ssu.ac.kr")
    monkeypatch.setenv("LMS_LOGIN_TYPE", "xn-sso-dir-sso")

    # Settings 는 모듈 레벨에 싱글턴이므로 직접 인스턴스 생성으로 테스트
    from pydantic_settings import BaseSettings

    from lms_bridge.config import Settings

    s = Settings(
        lms_username="20231234",
        lms_password="secret123",
    )

    assert s.lms_username == "20231234"
    assert s.lms_base_url == "https://lms.ssu.ac.kr"
    assert s.lms_login_type == "xn-sso-dir-sso"


def test_login_url_property():
    """login_url 프로퍼티가 올바른 URL 을 생성하는지 확인."""
    from lms_bridge.config import Settings

    s = Settings(
        lms_username="u",
        lms_password="p",
        lms_base_url="https://lms.ssu.ac.kr",
        lms_login_type="xn-sso-dir-sso",
    )
    assert s.login_url == "https://lms.ssu.ac.kr/login?type=xn-sso-dir-sso"


def test_invalid_log_level_raises():
    """잘못된 log_level 은 ValidationError 를 발생시켜야 한다."""
    from pydantic import ValidationError

    from lms_bridge.config import Settings

    with pytest.raises(ValidationError):
        Settings(lms_username="u", lms_password="p", log_level="VERBOSE")


def test_invalid_login_type_raises():
    """잘못된 lms_login_type 은 ValidationError 를 발생시켜야 한다."""
    from pydantic import ValidationError

    from lms_bridge.config import Settings

    with pytest.raises(ValidationError):
        Settings(lms_username="u", lms_password="p", lms_login_type="unknown")
