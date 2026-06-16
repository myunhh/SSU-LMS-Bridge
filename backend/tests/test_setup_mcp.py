"""setup_mcp — 환경변수 유무에 따른 mount/skip 분기 검증.

상시 마운트(토큰 없음): LMS / Study / Grades (/mcp/lms, /mcp/study, /mcp/grades).
게이트 마운트: Materials(강의자료 RAG)·Obsidian 은 obsidian_mcp_auth_code 설정 시,
Notion 은 token+root 설정 시. 마운트 순서는 setup.py 정의 순서를 따른다:
  lms → study → grades → materials(obs) → notion → obsidian(obs).

특히 fix(mcp) 554f550 회귀 방지:
  obsidian_vault_path 가 빈 문자열이어도 obsidian_mcp_auth_code 만 있으면 마운트한다.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.mcp_client.setup import setup_mcp


def _settings(notion_token="", notion_root="", obs_auth="", obs_vault="",
              obs_base_url="http://localhost:27124"):
    return SimpleNamespace(
        notion_token=notion_token,
        notion_root_page_id=notion_root,
        obsidian_mcp_auth_code=obs_auth,
        obsidian_vault_path=obs_vault,
        obsidian_base_url=obs_base_url,
        session_cache_abspath="/abs/session_state.json",
        lms_mcp_url="http://localhost:8000/mcp/lms/sse",
        study_mcp_url="http://localhost:8000/mcp/study/sse",
        grades_mcp_url="http://localhost:8000/mcp/grades/sse",
        materials_mcp_url="http://localhost:8000/mcp/materials/sse",
        notion_mcp_url="http://localhost:8000/mcp/notion/sse",
        obsidian_mcp_url="http://localhost:8000/mcp/obsidian/sse",
    )


def _patch_all():
    """모든 서버 팩토리 + build_mcp_sse_app 패치 묶음."""
    return patch.multiple(
        "app.mcp_client.setup",
        create_lms_mcp_server=MagicMock(),
        create_study_mcp_server=MagicMock(),
        create_grades_mcp_server=MagicMock(),
        create_materials_mcp_server=MagicMock(),
        create_notion_mcp_server=MagicMock(),
        create_obsidian_mcp_server=MagicMock(),
        build_mcp_sse_app=MagicMock(side_effect=lambda s, p: f"app:{p}"),
    )


def _mounted(app):
    return [c.args[0] for c in app.mount.call_args_list]


def test_no_env_mounts_lms_study_grades_only():
    """토큰 전무 → 상시 MCP(lms/study/grades)만. Notion/Obsidian/Materials skip."""
    app = MagicMock()
    with _patch_all():
        setup_mcp(app, _settings())
    assert _mounted(app) == ["/mcp/lms", "/mcp/study", "/mcp/grades"]


def test_lms_grades_session_file_passed():
    """create_lms/grades 는 session_file 로, study 는 인자 없이 호출."""
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server") as cl, \
         patch("app.mcp_client.setup.create_study_mcp_server") as cs, \
         patch("app.mcp_client.setup.create_grades_mcp_server") as cg, \
         patch("app.mcp_client.setup.create_materials_mcp_server"), \
         patch("app.mcp_client.setup.create_notion_mcp_server"), \
         patch("app.mcp_client.setup.create_obsidian_mcp_server"), \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings())
    cl.assert_called_once_with(session_file="/abs/session_state.json")
    cs.assert_called_once_with()
    cg.assert_called_once_with(session_file="/abs/session_state.json")


def test_notion_only_when_both_keys_present():
    app = MagicMock()
    with _patch_all():
        setup_mcp(app, _settings(notion_token="t", notion_root="r"))
    # obsidian 미설정 → materials/obsidian skip. notion 추가.
    assert _mounted(app) == ["/mcp/lms", "/mcp/study", "/mcp/grades", "/mcp/notion"]


def test_notion_skipped_with_placeholder_values():
    """'xxxx' placeholder 는 미설정 취급 — Notion skip(상시 3개만)."""
    app = MagicMock()
    with _patch_all():
        setup_mcp(app, _settings(notion_token="secret_xxxx", notion_root="xxxx"))
    assert _mounted(app) == ["/mcp/lms", "/mcp/study", "/mcp/grades"]


def test_obsidian_mounts_materials_too_even_with_empty_vault_path():
    """🔴 fix(mcp) 554f550: auth_code 만 있고 vault_path='' 여도 Obsidian 마운트.
    Obsidian 설정 시 강의자료 RAG(Materials) MCP 도 함께 마운트된다.
    """
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server"), \
         patch("app.mcp_client.setup.create_study_mcp_server"), \
         patch("app.mcp_client.setup.create_grades_mcp_server"), \
         patch("app.mcp_client.setup.create_materials_mcp_server") as cm, \
         patch("app.mcp_client.setup.create_obsidian_mcp_server") as co, \
         patch("app.mcp_client.setup.create_notion_mcp_server") as cn, \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(
            obs_auth="code", obs_vault="", obs_base_url="http://localhost:27123",
        ))
    co.assert_called_once_with(auth_code="code", vault_path="", base_url="http://localhost:27123")
    cm.assert_called_once_with(auth_code="code", base_url="http://localhost:27123", vault_path="")
    cn.assert_not_called()
    assert _mounted(app) == ["/mcp/lms", "/mcp/study", "/mcp/grades", "/mcp/materials", "/mcp/obsidian"]


def test_obsidian_and_materials_skipped_without_auth_code():
    """auth_code 없으면 vault_path 있어도 Materials/Obsidian 둘 다 skip."""
    app = MagicMock()
    with _patch_all():
        setup_mcp(app, _settings(obs_auth="", obs_vault="some/path"))
    assert _mounted(app) == ["/mcp/lms", "/mcp/study", "/mcp/grades"]


def test_obsidian_skipped_with_placeholder_auth_code():
    app = MagicMock()
    with _patch_all():
        setup_mcp(app, _settings(obs_auth="xxxx"))
    assert _mounted(app) == ["/mcp/lms", "/mcp/study", "/mcp/grades"]


def test_all_mcp_servers_mounted():
    """상시(lms/study/grades) + Materials + Notion + Obsidian 전부 마운트."""
    app = MagicMock()
    with _patch_all():
        setup_mcp(app, _settings(notion_token="t", notion_root="r", obs_auth="c"))
    assert _mounted(app) == [
        "/mcp/lms", "/mcp/study", "/mcp/grades", "/mcp/materials", "/mcp/notion", "/mcp/obsidian",
    ]
