"""Shared bootstrap for scripts: put src on sys.path and expose settings."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_bazaar.config import ensure_directories, get_settings, load_settings  # noqa: E402

__all__ = ["ROOT", "ensure_directories", "get_settings", "load_settings"]
