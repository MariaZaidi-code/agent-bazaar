from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "app" / "web" / "static" / "pwa" / "screenshots"


def capture(base_url: str) -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        wide = browser.new_context(viewport={"width": 1280, "height": 800}, color_scheme="dark")
        page = wide.new_page()
        page.goto(f"{base_url}/dashboard", wait_until="commit")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(TARGET / "wide-dashboard.png"), full_page=False)
        wide.close()

        narrow = browser.new_context(
            viewport={"width": 390, "height": 844},
            color_scheme="dark",
            is_mobile=True,
            has_touch=True,
            device_scale_factor=1,
        )
        page = narrow.new_page()
        page.goto(f"{base_url}/marketplace", wait_until="commit")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(TARGET / "narrow-marketplace.png"), full_page=False)
        narrow.close()
        browser.close()
    print(f"Wrote screenshots to {TARGET}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8799")
    capture(parser.parse_args().base_url)
