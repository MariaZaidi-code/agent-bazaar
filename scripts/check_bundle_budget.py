from __future__ import annotations

import gzip
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "web" / "static"

BUDGETS = {
    "css_raw": 240_000,
    "css_gzip": 40_000,
    "js_raw": 300_000,
    "js_gzip": 65_000,
    "file_raw": 180_000,
}


def measure(pattern: str) -> tuple[int, int]:
    files = sorted(STATIC.glob(pattern))
    raw = sum(path.stat().st_size for path in files)
    compressed = sum(len(gzip.compress(path.read_bytes(), compresslevel=9)) for path in files)
    return raw, compressed


def main() -> int:
    failures: list[str] = []
    css_raw, css_gzip = measure("*.css")
    js_raw, js_gzip = measure("*.js")
    checks = {
        "css_raw": (css_raw, f"CSS raw {css_raw} > {BUDGETS['css_raw']}"),
        "css_gzip": (css_gzip, f"CSS gzip {css_gzip} > {BUDGETS['css_gzip']}"),
        "js_raw": (js_raw, f"JS raw {js_raw} > {BUDGETS['js_raw']}"),
        "js_gzip": (js_gzip, f"JS gzip {js_gzip} > {BUDGETS['js_gzip']}"),
    }
    for key, (value, message) in checks.items():
        if value > BUDGETS[key]:
            failures.append(message)
    for path in [*STATIC.glob("*.css"), *STATIC.glob("*.js")]:
        if path.stat().st_size > BUDGETS["file_raw"]:
            failures.append(f"{path.name} {path.stat().st_size} > {BUDGETS['file_raw']}")
    print(
        f"CSS {css_raw} B raw / {css_gzip} B gzip; JS {js_raw} B raw / {js_gzip} B gzip"
    )
    if failures:
        for failure in failures:
            print(f"BUDGET FAIL: {failure}", file=sys.stderr)
        return 1
    print("Bundle budget OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
