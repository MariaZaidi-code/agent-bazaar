from __future__ import annotations

from pathlib import Path

from agent_bazaar_auditor.cli import main


def test_catalog_and_verify_commands(capsys, tmp_path: Path) -> None:
    assert main(["catalog", "--json"]) == 0
    catalog = capsys.readouterr().out
    assert "open-meteo" in catalog
    assert "frankfurter" in catalog

    assert main(["verify", "frankfurter", "--no-persist", "--output-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "Verified" in output
    assert "Coverage" in output


def test_probe_command_is_machine_readable(capsys) -> None:
    assert main(["probe", "ipify", "--json"]) == 0
    output = capsys.readouterr().out
    assert '"tool_id": "ipify"' in output
    assert '"source": "fixture"' in output
