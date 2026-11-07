from __future__ import annotations

from scripts.check_bundle_budget import main


def test_static_bundle_within_budget() -> None:
    assert main() == 0
