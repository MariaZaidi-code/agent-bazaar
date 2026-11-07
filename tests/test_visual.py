from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
pytest.importorskip("PIL")

from PIL import Image, ImageChops  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASELINES = ROOT / "tests" / "visual" / "baselines"
ACTUALS = ROOT / "tests" / "visual" / "actual"

PAGES = [
    ("dashboard-wide", "/dashboard", 1280, 800),
    ("marketplace-wide", "/marketplace", 1280, 800),
    ("monitor-wide", "/monitor", 1280, 800),
    ("library-wide", "/library", 1280, 800),
    ("help-wide", "/help", 1280, 800),
    ("settings-wide", "/settings", 1280, 800),
    ("dashboard-narrow", "/dashboard", 390, 844),
]

DIFF_LIMIT = 0.006


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for(url: str, timeout: float = 40.0) -> None:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.4)
    raise RuntimeError("visual test server did not start")


@pytest.fixture(scope="module")
def live_server() -> str:
    if os.environ.get("RUN_VISUAL") != "1":
        pytest.skip("set RUN_VISUAL=1 to run Playwright visual regression snapshots")
    port = _free_port()
    runtime = tempfile.mkdtemp(prefix="ab-visual-")
    env = os.environ.copy()
    env.update(
        {
            "AB_RUNTIME_DIR": runtime,
            "AB_OFFLINE_MODE": "true",
            "AB_SCHEDULER_ENABLED": "false",
            "AB_LLM_PROVIDER": "none",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for(base_url)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _compare(actual: Path, baseline: Path) -> float:
    with Image.open(actual) as actual_image, Image.open(baseline) as baseline_image:
        left = actual_image.convert("RGB")
        right = baseline_image.convert("RGB")
        if left.size != right.size:
            return 1.0
        difference = ImageChops.difference(left, right).convert("L")
        histogram = difference.histogram()
        changed = sum(histogram[13:])
        return changed / float(left.size[0] * left.size[1])


def test_visual_regression(live_server: str) -> None:
    update = os.environ.get("UPDATE_VISUAL") == "1"
    BASELINES.mkdir(parents=True, exist_ok=True)
    ACTUALS.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    with sync_playwright() as playwright:
        channel = os.environ.get("PLAYWRIGHT_CHANNEL", "chrome") or None
        browser = playwright.chromium.launch(channel=channel)
        for name, path, width, height in PAGES:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                color_scheme="dark",
                device_scale_factor=1,
                is_mobile=width < 600,
                has_touch=width < 600,
            )
            page = context.new_page()
            page.add_init_script(
                "localStorage.setItem('agent-bazaar-theme','dark');"
                "localStorage.setItem('agent-bazaar-contrast','off');"
            )
            page.goto(f"{live_server}{path}", wait_until="load", timeout=45000)
            page.emulate_media(reduced_motion="reduce")
            page.add_style_tag(
                content="*,*::before,*::after{animation:none!important;transition:none!important;}"
            )
            page.wait_for_timeout(1800)
            actual = ACTUALS / f"{name}.png"
            page.screenshot(path=str(actual), full_page=False)
            context.close()
            baseline = BASELINES / f"{name}.png"
            if update:
                baseline.write_bytes(actual.read_bytes())
                continue
            if not baseline.exists():
                failures.append(f"{name}: missing baseline (run with UPDATE_VISUAL=1)")
                continue
            ratio = _compare(actual, baseline)
            if ratio > DIFF_LIMIT:
                failures.append(f"{name}: {ratio:.3%} pixels changed (limit {DIFF_LIMIT:.1%})")
        browser.close()
    assert not failures, "Visual snapshots changed:\n" + "\n".join(failures)
