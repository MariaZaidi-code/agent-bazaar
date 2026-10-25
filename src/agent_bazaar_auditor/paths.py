from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("ABA_DATA_DIR", PROJECT_ROOT / "data"))
OUTPUTS_DIR = Path(os.environ.get("ABA_OUTPUT_DIR", PROJECT_ROOT / "outputs"))
CACHE_DIR = Path(os.environ.get("ABA_CACHE_DIR", PROJECT_ROOT / ".cache"))
DOCS_DIR = PROJECT_ROOT / "docs"


def ensure_directories() -> None:
    for directory in (OUTPUTS_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
