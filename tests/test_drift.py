from __future__ import annotations

from pathlib import Path

from agent_bazaar_auditor.auditor import Auditor
from agent_bazaar_auditor.config import Settings
from agent_bazaar_auditor.mocks.provider import MockProvider


def _auditor(tmp_path: Path, mode: str = "full") -> Auditor:
    settings = Settings(
        outputs_dir=tmp_path / "outputs",
        cache_dir=tmp_path / "cache",
        live=False,
        drift_mode=mode,
    )
    return Auditor(settings=settings, persist=False)


def test_nested_rename_is_detected(tmp_path: Path) -> None:
    auditor = _auditor(tmp_path)
    definition = auditor.definitions["usgs-earthquake"]
    provider = MockProvider("usgs-earthquake", definition, behavior="normal", seed=11)
    auditor.harness.set_provider("usgs-earthquake", provider)
    baseline = auditor.probe("usgs-earthquake")
    auditor.monitor.check("usgs-earthquake", baseline, definition, probe_round=0, establish_if_missing=True)
    provider.configure("rename_field", field_path="properties.mag", new_name="magnitude")
    probe = auditor.probe("usgs-earthquake")
    check = auditor.monitor.check("usgs-earthquake", probe, definition, probe_round=1)
    assert check.detected
    assert any(alert.field_path == "properties.mag" for alert in check.alerts)


def test_garbage_200_requires_embedding_detector(tmp_path: Path) -> None:
    full = _auditor(tmp_path / "full")
    rule_only = _auditor(tmp_path / "rule", mode="rule_only")
    for auditor in (full, rule_only):
        provider = MockProvider("nominatim", auditor.definitions["nominatim"], behavior="normal", seed=12)
        auditor.harness.set_provider("nominatim", provider)
        baseline = auditor.probe("nominatim")
        auditor.monitor.check("nominatim", baseline, auditor.definitions["nominatim"], establish_if_missing=True)
        provider.configure("garbage_200")
        probe = auditor.probe("nominatim")
        check = auditor.monitor.check("nominatim", probe, auditor.definitions["nominatim"], probe_round=1)
        if auditor is rule_only:
            assert not check.detected
        else:
            assert check.detected
            assert "embedding" in check.detectors


def test_clean_payload_has_no_false_alarm(tmp_path: Path) -> None:
    auditor = _auditor(tmp_path)
    definition = auditor.definitions["open-meteo"]
    baseline = auditor.probe("open-meteo")
    auditor.monitor.check("open-meteo", baseline, definition, establish_if_missing=True)
    check = auditor.monitor.check("open-meteo", baseline, definition, probe_round=1)
    assert not check.detected
    assert check.alerts == []


def test_persist_false_keeps_baseline_in_memory(tmp_path: Path) -> None:
    auditor = _auditor(tmp_path)
    definition = auditor.definitions["open-meteo"]
    provider = MockProvider("open-meteo", definition, behavior="normal", seed=13)
    auditor.harness.set_provider("open-meteo", provider)
    baseline = auditor.probe("open-meteo")
    auditor.monitor.check("open-meteo", baseline, definition, establish_if_missing=True)
    provider.configure("dishonest")
    probe = auditor.probe("open-meteo")
    check = auditor.monitor.check("open-meteo", probe, definition, probe_round=1)
    assert check.detected
    assert not (tmp_path / "outputs" / "baselines.json").exists()
