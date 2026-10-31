from __future__ import annotations

from agent_bazaar_auditor.enums import ProbeSource
from agent_bazaar_auditor.probes.definitions import build_probe_definitions
from agent_bazaar_auditor.probes.http import HttpTransport
from agent_bazaar_auditor.probes.models import ProbeResult, validate_payload


def test_fifteen_keyless_probe_definitions() -> None:
    definitions = build_probe_definitions()
    assert len(definitions) == 15
    assert all(definition.endpoint.startswith("https://") for definition in definitions.values())
    assert all("API_KEY" not in definition.endpoint and "api_key" not in definition.params for definition in definitions.values())


def test_open_meteo_fixture_validates() -> None:
    definition = build_probe_definitions()["open-meteo"]
    probe = ProbeResult(
        tool_id="open-meteo",
        ok=True,
        status_code=200,
        payload=definition.fixture,
        source=ProbeSource.FIXTURE,
    )
    validation = validate_payload(definition, probe.payload)
    assert validation.ok
    assert validation.checked_fields >= 3


def test_validation_detects_missing_field() -> None:
    definition = build_probe_definitions()["frankfurter"]
    payload = {"amount": 1.0, "base": "USD"}
    validation = validate_payload(definition, payload)
    assert not validation.ok
    assert any(issue.path == "rates" for issue in validation.issues)


def test_probe_definition_serializes_safe_input() -> None:
    definition = build_probe_definitions()["nominatim"]
    data = definition.to_dict()
    assert data["tool_id"] == "nominatim"
    assert data["params"]["q"] == "Lahore"
    assert data["probeable"] is True


def test_http_transport_retries_transient_status(monkeypatch) -> None:
    import urllib.request

    attempts: list[str] = []

    class FakeResponse:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

        def geturl(self) -> str:
            return "https://example.test/data"

    def fake_urlopen(request, timeout):
        attempts.append(request.full_url)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                503,
                "busy",
                {"Retry-After": "0"},
                None,
            )
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    transport = HttpTransport(retries=1, backoff_seconds=0.0, sleep=lambda delay: None)
    response = transport.get("https://example.test/data")
    assert response.status_code == 200
    assert len(attempts) == 2
