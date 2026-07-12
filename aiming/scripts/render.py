#!/usr/bin/env python3
"""
에이밍 AIMing · 슬라이드 렌더링 스크립트
HTML 파일을 받아 각 .slide 요소를 PNG로 저장합니다.

사용법:
  python render.py <input.html> [output_dir]

예:
  python render.py episodes/ep01_line/ep01.html episodes/ep01_line/out/
"""
import asyncio
import os
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright가 설치되어 있지 않습니다.")
    print("설치: pip install playwright && playwright install chromium")
    sys.exit(1)


async def render(html_path: str, out_dir: str):
    html_abs = os.path.abspath(html_path)
    if not os.path.exists(html_abs):
        print(f"파일이 없습니다: {html_abs}")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1080, "height": 1350},
            device_scale_factor=2,  # 2x retina
        )
        page = await context.new_page()
        await page.goto(f"file://{html_abs}")
        # 폰트 로딩 대기
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)

        # 모든 .slide 요소 찾기
        slides = await page.query_selector_all(".slide")
        if not slides:
            print("⚠️  .slide 요소를 찾을 수 없습니다.")
            await browser.close()
            return

        for i, slide in enumerate(slides, 1):
            out_path = os.path.join(out_dir, f"slide_{i:02d}.png")
            await slide.screenshot(path=out_path)
            print(f"✓ {out_path}")

        await browser.close()
        print(f"\n총 {len(slides)}장 렌더링 완료.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    html_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(html_path) or ".", "out"
    )

    asyncio.run(render(html_path, out_dir))


if __name__ == "__main__":
    main()
