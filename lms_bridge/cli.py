"""
lms_bridge/cli.py
──────────────────────────────────────────────────────────────
통합 CLI 진입점.

사용 예:
    lms-bridge --help
    lms-bridge sync
    lms-bridge mcp
    lms-bridge status
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from lms_bridge import __version__

app = typer.Typer(
    name="lms-bridge",
    help="숭실대 LMS ↔ MCP / Notion / Obsidian Vault 통합 브릿지",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]lms-bridge[/bold cyan] v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(  # noqa: FBT001
        False,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="버전을 출력하고 종료합니다.",
    ),
) -> None:
    pass


@app.command()
def status() -> None:
    """현재 설정 및 환경을 확인합니다."""
    from lms_bridge.config import settings

    console.print(
        Panel(
            Text.assemble(
                ("LMS URL:      ", "bold"), (settings.lms_base_url, "cyan"), "\n",
                ("Login Type:   ", "bold"), (settings.lms_login_type, "cyan"), "\n",
                ("Vault Path:   ", "bold"), (str(settings.obsidian_vault_path), "cyan"), "\n",
                ("Session Cache:", "bold"), (" " + str(settings.session_cache_path), "cyan"), "\n",
                ("Log Level:    ", "bold"), (settings.log_level, "cyan"), "\n",
                ("Headless:     ", "bold"), (str(settings.playwright_headless), "cyan"),
            ),
            title="[bold cyan]LMS-Bridge 설정 상태[/bold cyan]",
            border_style="cyan",
        )
    )


@app.command()
def sync(
    course_id: str = typer.Option("", "--course", "-c", help="특정 과목 ID (생략 시 전체)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="실제 동기화 없이 실행 계획만 출력"),
) -> None:
    """LMS 데이터를 Notion / Obsidian Vault 에 동기화합니다. [dim](Phase 3-4에서 구현)[/dim]"""
    console.print("[yellow]sync 명령어는 Phase 3-4 에서 구현됩니다.[/yellow]")


@app.command()
def mcp() -> None:
    """MCP 서버를 stdio 모드로 실행합니다. [dim](Phase 2에서 구현)[/dim]"""
    console.print("[yellow]mcp 명령어는 Phase 2 에서 구현됩니다.[/yellow]")


@app.command()
def login() -> None:
    """LMS SSO 로그인을 수행하고 세션을 캐시합니다. [dim](Phase 1-B에서 구현)[/dim]"""
    console.print("[yellow]login 명령어는 Phase 1-B 에서 구현됩니다.[/yellow]")


if __name__ == "__main__":
    app()
