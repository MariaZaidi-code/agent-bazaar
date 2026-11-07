# Lighthouse and frontend quality report

Date: 2026-11-07
Lighthouse: 13.6.0, Chrome headless, local uvicorn server on port 8799.

## Scores

| Page | Performance | Accessibility | Best practices | SEO | Agentic browsing |
|---|---:|---:|---:|---:|---:|
| `/dashboard` | 93 | 100 | 100 | 100 | 100 |
| `/marketplace` | 95 | 100 | 100 | 100 | 100 |
| `/documents` | 95 | 100 | 100 | 100 | 100 |
| `/help` | 94 | 100 | 100 | 100 | 100 |
| `/settings` | 94 | 100 | 100 | 100 | 100 |

The plan target was accessibility >= 95; every audited page scores 100.

## What changed for the audit

- Raised the dark-theme `--faint` token from `#73767d` to `#90949c` so small
  metadata text passes WCAG AA contrast (previously 3.91:1, now above 4.5:1).
- Added `meta description` to `index.html` and `share.html`.
- Fixed heading order on the marketplace scoring card (`h3` -> `h2`).
- Removed `role="button"` from tool cards that contain their own buttons;
  cards keep `tabindex="0"`, `aria-haspopup="dialog"` and Enter/Space handling.
- Added `role="img"` plus an accessible summary table for the usage chart.
- Made the command palette full-screen on narrow viewports.

## Remaining performance deductions

The remaining points come from development delivery rather than application
logic:

- `unminified-css` / `unminified-javascript`
- `unused-css-rules` / `unused-javascript` (single-page shell loads all views)
- `cache-insight` / `render-blocking-insight` (uvicorn static files, no CDN)

A production build that minifies assets and serves them with long-lived cache
headers would address these. They do not affect accessibility or behavior.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8799
& "C:\Users\U S\AppData\Roaming\npm\lighthouse.cmd" http://127.0.0.1:8799/dashboard `
  --output=json --output-path=outputs/lh-dashboard.json `
  --chrome-flags="--headless=new" --quiet
```

## Frontend test suite

| Check | Command | Result |
|---|---|---|
| Vitest utilities | `& "C:\Program Files\nodejs\npm.cmd" test` | 14 passed |
| Playwright visual snapshots | `$env:RUN_VISUAL="1"; .\.venv\Scripts\python.exe -m pytest tests/test_visual.py` | 7 snapshots match |
| Bundle budget | `.\.venv\Scripts\python.exe scripts\check_bundle_budget.py` | CSS 207 KB raw / 31 KB gzip; JS 240 KB raw / 54 KB gzip |
| Python suite | `.\.venv\Scripts\python.exe -m pytest` | 264 passed, 3 skipped |

Visual baselines live in `tests/visual/baselines`. Refresh them with
`$env:UPDATE_VISUAL="1"` when the UI intentionally changes. The default Python
run skips the browser test unless `RUN_VISUAL=1` is set.
