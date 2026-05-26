"""setup_mcp — 환경변수 유무에 따른 mount/skip 분기 검증.

특히 fix(mcp) 554f550 의 회귀 방지:
    obsidian_vault_path 가 빈 문자열이어도 obsidian_mcp_auth_code 만 있으면 마운트한다.
    (README §6-A: vault_path 는 vault 내부 상대 경로 → 보통 빈 문자열이 정상)
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.mcp_client.setup import setup_mcp


def _settings(notion_token="", notion_root="", obs_auth="", obs_vault=""):
    return SimpleNamespace(
        notion_token=notion_token,
        notion_root_page_id=notion_root,
        obsidian_mcp_auth_code=obs_auth,
        obsidian_vault_path=obs_vault,
        notion_mcp_url="http://localhost:8000/mcp/notion/sse",
        obsidian_mcp_url="http://localhost:8000/mcp/obsidian/sse",
    )


def test_no_env_mounts_nothing():
    app = MagicMock()
    setup_mcp(app, _settings())
    app.mount.assert_not_called()


def test_notion_only_when_both_keys_present():
    app = MagicMock()
    with patch("app.mcp_client.setup.create_notion_mcp_server") as cn, \
         patch("app.mcp_client.setup.create_obsidian_mcp_server") as co, \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(notion_token="t", notion_root="r"))

    cn.assert_called_once_with(token="t", root_page_id="r")
    co.assert_not_called()
    app.mount.assert_called_once_with("/mcp/notion", "app:/mcp/notion")


def test_notion_skipped_if_only_token_no_root():
    """Notion 은 token 과 root_page_id 둘 다 필요."""
    app = MagicMock()
    with patch("app.mcp_client.setup.create_notion_mcp_server") as cn:
        setup_mcp(app, _settings(notion_token="t", notion_root=""))
    cn.assert_not_called()


def test_obsidian_mounted_even_with_empty_vault_path():
    """🔴 fix(mcp) 554f550 회귀 방지:
    auth_code 만 있고 vault_path='' 여도 Obsidian MCP 가 마운트되어야 한다.
    """
    app = MagicMock()
    with patch("app.mcp_client.setup.create_obsidian_mcp_server") as co, \
         patch("app.mcp_client.setup.create_notion_mcp_server") as cn, \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(obs_auth="code", obs_vault=""))

    co.assert_called_once_with(auth_code="code", vault_path="")
    cn.assert_not_called()
    app.mount.assert_called_once_with("/mcp/obsidian", "app:/mcp/obsidian")


def test_obsidian_skipped_without_auth_code_even_with_vault_path():
    """역방향: auth_code 가 비어 있으면 vault_path 가 있어도 skip."""
    app = MagicMock()
    with patch("app.mcp_client.setup.create_obsidian_mcp_server") as co:
        setup_mcp(app, _settings(obs_auth="", obs_vault="some/path"))
    co.assert_not_called()
    app.mount.assert_not_called()


def test_both_mcp_servers_mounted():
    app = MagicMock()
    with patch("app.mcp_client.setup.create_notion_mcp_server"), \
         patch("app.mcp_client.setup.create_obsidian_mcp_server"), \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(
            notion_token="t", notion_root="r", obs_auth="c",
        ))

    mounted_prefixes = [c.args[0] for c in app.mount.call_args_list]
    assert mounted_prefixes == ["/mcp/notion", "/mcp/obsidian"]
