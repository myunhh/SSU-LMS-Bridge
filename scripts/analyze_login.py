"""
scripts/analyze_login.py
──────────────────────────────────────────────────────────────
LMS 로그인 페이지 구조 분석 스크립트.
실제 auth.py 구현 전에 폼 필드, 리다이렉트, 쿠키를 파악한다.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright


LMS_BASE = "https://lms.ssu.ac.kr"
LOGIN_URL = f"{LMS_BASE}/login?type=xn-sso-dir-sso"


async def analyze() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"\n[1] 로그인 페이지 접속: {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)

        print(f"    현재 URL: {page.url}")
        print(f"    타이틀  : {await page.title()}")

        # 폼 인풋 필드 분석
        print("\n[2] Input 필드 분석")
        inputs = await page.query_selector_all("input")
        for inp in inputs:
            name = await inp.get_attribute("name") or ""
            id_ = await inp.get_attribute("id") or ""
            type_ = await inp.get_attribute("type") or ""
            placeholder = await inp.get_attribute("placeholder") or ""
            print(f"    input: name={name!r:20} id={id_!r:20} type={type_!r:10} placeholder={placeholder!r}")

        # 버튼 분석
        print("\n[3] 버튼 분석")
        buttons = await page.query_selector_all("button, input[type=submit], input[type=button]")
        for btn in buttons:
            text = (await btn.inner_text()).strip() if await btn.inner_text() else ""
            type_ = await btn.get_attribute("type") or ""
            id_ = await btn.get_attribute("id") or ""
            cls = await btn.get_attribute("class") or ""
            print(f"    button: text={text!r:20} type={type_!r:10} id={id_!r:20} class={cls[:40]!r}")

        # 폼 action 분석
        print("\n[4] Form 태그 분석")
        forms = await page.query_selector_all("form")
        for form in forms:
            action = await form.get_attribute("action") or ""
            method = await form.get_attribute("method") or ""
            id_ = await form.get_attribute("id") or ""
            print(f"    form: action={action!r} method={method!r} id={id_!r}")

        # 현재 쿠키
        print("\n[5] 현재 쿠키 (로그인 전)")
        cookies = await context.cookies()
        for c in cookies:
            print(f"    {c['name']} = {c['value'][:30]}... (domain={c['domain']})")

        # iframe 확인
        print("\n[6] iframe 확인")
        frames = page.frames
        for frame in frames:
            print(f"    frame url: {frame.url}")

        # 페이지 HTML 일부 저장
        html = await page.content()
        with open(".cache/login_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n[7] HTML 저장됨: .cache/login_page.html ({len(html):,} bytes)")

        await browser.close()
        print("\n분석 완료!")


if __name__ == "__main__":
    import pathlib
    pathlib.Path(".cache").mkdir(exist_ok=True)
    asyncio.run(analyze())
