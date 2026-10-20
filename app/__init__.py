"""Agent Bazaar application package.

The knowledge layer lives in ``src/agent_bazaar`` and is not installed in some
setups, so the source directory is added to ``sys.path`` here to keep
``import agent_bazaar`` working for ``python run.py`` and for the tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

__version__ = "0.1.0"
