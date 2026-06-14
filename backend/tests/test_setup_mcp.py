"""setup_mcp — 환경변수 유무에 따른 mount/skip 분기 검증.

특히 fix(mcp) 554f550 의 회귀 방지:
    obsidian_vault_path 가 빈 문자열이어도 obsidian_mcp_auth_code 만 있으면 마운트한다.
    (README §6-A: vault_path 는 vault 내부 상대 경로 → 보통 빈 문자열이 정상)

LMS / Study MCP 는 토큰 설정이 없으므로 항상 마운트된다(/mcp/lms, /mcp/study) —
아래 테스트는 모두 둘이 추가로 마운트됨을 전제로, 패치 시 create_lms_mcp_server /
create_study_mcp_server 도 함께 patch 한다.
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
        notion_mcp_url="http://localhost:8000/mcp/notion/sse",
        obsidian_mcp_url="http://localhost:8000/mcp/obsidian/sse",
    )


def test_no_env_mounts_lms_and_study_only():
    """토큰이 전무해도 LMS / Study MCP 는 항상 마운트된다. Notion/Obsidian 은 skip.

    create_lms_mcp_server 가 session_file=str(session_cache_abspath) 로,
    create_study_mcp_server 가 인자 없이 호출되는지도 검증.
    """
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server") as cl, \
         patch("app.mcp_client.setup.create_study_mcp_server") as cs, \
         patch("app.mcp_client.setup.create_notion_mcp_server") as cn, \
         patch("app.mcp_client.setup.create_obsidian_mcp_server") as co, \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings())

    cl.assert_called_once_with(session_file="/abs/session_state.json")
    cs.assert_called_once_with()
    cn.assert_not_called()
    co.assert_not_called()
    mounted_prefixes = [c.args[0] for c in app.mount.call_args_list]
    assert mounted_prefixes == ["/mcp/lms", "/mcp/study"]


def test_notion_only_when_both_keys_present():
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server"), \
         patch("app.mcp_client.setup.create_study_mcp_server"), \
         patch("app.mcp_client.setup.create_notion_mcp_server") as cn, \
         patch("app.mcp_client.setup.create_obsidian_mcp_server") as co, \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(notion_token="t", notion_root="r"))

    cn.assert_called_once_with(token="t", root_page_id="r")
    co.assert_not_called()
    # LMS / Study 는 항상 마운트되므로 Notion 과 함께 3개.
    mounted_prefixes = [c.args[0] for c in app.mount.call_args_list]
    assert mounted_prefixes == ["/mcp/lms", "/mcp/study", "/mcp/notion"]


def test_notion_skipped_if_only_token_no_root():
    """Notion 은 token 과 root_page_id 둘 다 필요."""
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server"), \
         patch("app.mcp_client.setup.create_study_mcp_server"), \
         patch("app.mcp_client.setup.create_notion_mcp_server") as cn:
        setup_mcp(app, _settings(notion_token="t", notion_root=""))
    cn.assert_not_called()


def test_notion_skipped_with_placeholder_values():
    """.env.example 견본값('xxxx' 포함)은 미설정 취급 — 마운트 금지.

    routes/sync.py · routes/connectors.py 와 동일한 config.is_configured 규칙.
    truthiness 만 검사하면 예제 .env 를 그대로 복사한 환경에서 가짜 토큰으로
    Notion MCP 가 마운트돼 LLM 채팅에 notion__* tool 이 노출되는 불일치가 생긴다.
    (LMS 는 별개로 항상 마운트된다.)
    """
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server"), \
         patch("app.mcp_client.setup.create_study_mcp_server"), \
         patch("app.mcp_client.setup.create_notion_mcp_server") as cn, \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(notion_token="secret_xxxx", notion_root="xxxx"))
    cn.assert_not_called()
    mounted_prefixes = [c.args[0] for c in app.mount.call_args_list]
    assert mounted_prefixes == ["/mcp/lms", "/mcp/study"]


def test_obsidian_mounted_even_with_empty_vault_path():
    """🔴 fix(mcp) 554f550 회귀 방지:
    auth_code 만 있고 vault_path='' 여도 Obsidian MCP 가 마운트되어야 한다.
    base_url 은 settings.obsidian_base_url 이 그대로 전달되어야 한다
    (상태 핑 routes/connectors.py 와 실제 MCP 도구 호출 URL 일치 보장).
    """
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server"), \
         patch("app.mcp_client.setup.create_study_mcp_server"), \
         patch("app.mcp_client.setup.create_obsidian_mcp_server") as co, \
         patch("app.mcp_client.setup.create_notion_mcp_server") as cn, \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(
            obs_auth="code", obs_vault="", obs_base_url="http://localhost:27123",
        ))

    co.assert_called_once_with(
        auth_code="code", vault_path="", base_url="http://localhost:27123",
    )
    cn.assert_not_called()
    # LMS / Study 는 항상 마운트되므로 Obsidian 과 함께 3개.
    mounted_prefixes = [c.args[0] for c in app.mount.call_args_list]
    assert mounted_prefixes == ["/mcp/lms", "/mcp/study", "/mcp/obsidian"]


def test_obsidian_skipped_without_auth_code_even_with_vault_path():
    """역방향: auth_code 가 비어 있으면 vault_path 가 있어도 skip(LMS 만 마운트)."""
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server"), \
         patch("app.mcp_client.setup.create_study_mcp_server"), \
         patch("app.mcp_client.setup.create_obsidian_mcp_server") as co, \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(obs_auth="", obs_vault="some/path"))
    co.assert_not_called()
    mounted_prefixes = [c.args[0] for c in app.mount.call_args_list]
    assert mounted_prefixes == ["/mcp/lms", "/mcp/study"]


def test_obsidian_skipped_with_placeholder_auth_code():
    """placeholder('xxxx') auth_code 도 미설정 취급 — 마운트 금지(LMS 만 마운트)."""
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server"), \
         patch("app.mcp_client.setup.create_study_mcp_server"), \
         patch("app.mcp_client.setup.create_obsidian_mcp_server") as co, \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(obs_auth="xxxx"))
    co.assert_not_called()
    mounted_prefixes = [c.args[0] for c in app.mount.call_args_list]
    assert mounted_prefixes == ["/mcp/lms", "/mcp/study"]


def test_all_mcp_servers_mounted():
    """LMS · Study(무조건) + Notion + Obsidian 넷 다 마운트되는 경우."""
    app = MagicMock()
    with patch("app.mcp_client.setup.create_lms_mcp_server"), \
         patch("app.mcp_client.setup.create_study_mcp_server"), \
         patch("app.mcp_client.setup.create_notion_mcp_server"), \
         patch("app.mcp_client.setup.create_obsidian_mcp_server"), \
         patch("app.mcp_client.setup.build_mcp_sse_app", side_effect=lambda s, p: f"app:{p}"):
        setup_mcp(app, _settings(
            notion_token="t", notion_root="r", obs_auth="c",
        ))

    mounted_prefixes = [c.args[0] for c in app.mount.call_args_list]
    assert mounted_prefixes == ["/mcp/lms", "/mcp/study", "/mcp/notion", "/mcp/obsidian"]
