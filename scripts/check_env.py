"""
scripts/check_env.py
──────────────────────────────────────────────────────────────
개발 환경 사전 점검 스크립트.
필수 도구 버전 및 설정 파일 존재 여부를 확인한다.

실행: python scripts/check_env.py
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "✅" if ok else "❌"
    line = f"  {status}  {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return ok


def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return ""


def main() -> None:
    print("\n" + "=" * 55)
    print("  LMS-Bridge 개발 환경 점검")
    print("=" * 55)

    all_ok = True

    # Python 버전
    major, minor = sys.version_info[:2]
    ok = major == 3 and minor >= 11
    all_ok &= check(f"Python {major}.{minor}", ok, "3.11+ 필요")

    # 필수 CLI 도구
    for tool, cmd in [("uv", ["uv", "--version"]), ("git", ["git", "--version"])]:
        v = run(cmd)
        ok = bool(v)
        all_ok &= check(tool, ok, v.split("\n")[0] if v else "not found")

    # 필수 Python 패키지
    print("\n  [패키지]")
    for pkg in ["playwright", "pydantic", "pydantic_settings", "loguru", "typer", "mcp"]:
        try:
            mod = importlib.import_module(pkg)
            ver = getattr(mod, "__version__", "installed")
            all_ok &= check(pkg, True, ver)
        except ImportError:
            all_ok &= check(pkg, False, "not installed")

    # Playwright 브라우저
    print("\n  [Playwright]")
    chromium_path = shutil.which("chromium") or run(
        ["python", "-c", "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium; print(b.executable_path)"]
    )
    # 간단히 playwright 패키지만 확인
    try:
        import playwright
        all_ok &= check("playwright 패키지", True, playwright.__version__)
    except ImportError:
        all_ok &= check("playwright 패키지", False, "pip install playwright 필요")

    # .env 파일
    print("\n  [설정 파일]")
    env_exists = Path(".env").exists()
    all_ok &= check(".env 파일", env_exists, ".env.example 을 복사해서 만드세요" if not env_exists else "")
    all_ok &= check(".env.example", Path(".env.example").exists())
    all_ok &= check(".gitignore", Path(".gitignore").exists())

    print("\n" + "=" * 55)
    if all_ok:
        print("  🎉  모든 환경 점검 통과! 개발 시작 가능합니다.")
    else:
        print("  ⚠️   일부 항목이 누락되었습니다. 위 내용을 확인해주세요.")
    print("=" * 55 + "\n")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
