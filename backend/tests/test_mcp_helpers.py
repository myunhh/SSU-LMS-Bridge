"""mcp_client/{notion,obsidian}_server.py 의 헬퍼 함수 단위 테스트.

내부 함수지만 query_notices / query_assignments / write_file 같은 tool 의
정확성이 이 헬퍼들에 의해 결정되므로 핵심 회귀 보호 지점.
"""
from app.mcp_client.notion_server import (
    _checkbox,
    _date,
    _number,
    _select,
    _title,
)
from app.mcp_client.obsidian_server import _is_text_mime


# ── Notion property 추출 ─────────────────────────────────────

def test_title_concatenates_plain_text_pieces():
    prop = {"type": "title", "title": [
        {"plain_text": "안녕 "},
        {"plain_text": "세상"},
    ]}
    assert _title(prop) == "안녕 세상"


def test_title_returns_empty_for_none_or_wrong_type():
    assert _title(None) == ""
    assert _title({"type": "rich_text"}) == ""
    assert _title({"type": "title", "title": []}) == ""


def test_select_returns_name():
    assert _select({"type": "select", "select": {"name": "운영체제"}}) == "운영체제"


def test_select_handles_null_value():
    """Notion 에서 미설정 select 는 {"select": None}."""
    assert _select({"type": "select", "select": None}) == ""
    assert _select(None) == ""
    assert _select({"type": "date"}) == ""


def test_date_returns_start_only_not_end():
    prop = {"type": "date", "date": {"start": "2026-05-21", "end": "2026-05-25"}}
    assert _date(prop) == "2026-05-21"


def test_date_handles_null():
    assert _date({"type": "date", "date": None}) == ""
    assert _date(None) == ""


def test_checkbox_returns_bool():
    assert _checkbox({"type": "checkbox", "checkbox": True}) is True
    assert _checkbox({"type": "checkbox", "checkbox": False}) is False


def test_checkbox_default_when_missing():
    assert _checkbox(None) is False
    assert _checkbox(None, default=True) is True
    assert _checkbox({"type": "title"}, default=True) is True


def test_number_returns_value_or_none():
    assert _number({"type": "number", "number": 30}) == 30
    assert _number({"type": "number", "number": 0}) == 0
    assert _number({"type": "number", "number": None}) is None
    assert _number(None) is None
    assert _number({"type": "select"}) is None


# ── Obsidian mime 추론 (write_file binary 처리의 핵심) ───────

def test_is_text_mime_for_text_prefix():
    assert _is_text_mime("text/markdown") is True
    assert _is_text_mime("text/plain") is True
    assert _is_text_mime("text/html") is True


def test_is_text_mime_for_structured_text_formats():
    assert _is_text_mime("application/json") is True
    assert _is_text_mime("application/xml") is True
    assert _is_text_mime("application/yaml") is True


def test_is_text_mime_for_binary_returns_false():
    """이 케이스가 False 여야 vault_service.py 의 base64 인코딩 흐름이 정상 디코드된다."""
    assert _is_text_mime("application/octet-stream") is False
    assert _is_text_mime("application/pdf") is False
    assert _is_text_mime("image/png") is False
    assert _is_text_mime("image/jpeg") is False
