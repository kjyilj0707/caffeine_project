"""개발용: 앱(localhost:8501)을 휴대폰 크기(390×844)로 캡처 — ~/.venvs/work/bin/python scripts/phone_shot.py 출력폴더 [페이지...]"""
import sys
from playwright.sync_api import sync_playwright

out, pages = sys.argv[1], sys.argv[2:] or [""]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                        has_touch=True, color_scheme="light")
    pg = ctx.new_page()
    for name in pages:
        pg.goto(f"http://localhost:8501/{name}")
        pg.wait_for_selector('[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"]', timeout=30000)
        pg.wait_for_timeout(2500)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=f"{out}/s_{name or 'home'}.png")
        print("saved", name or "home")
    b.close()
