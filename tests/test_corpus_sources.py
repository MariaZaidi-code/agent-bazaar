"""Tests for the acquisition sources, the corpus manifest and the probe set."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DATA_DIR = REPO_ROOT / "data"
SPECS_DIR = DATA_DIR / "specs"
OVERRIDES_PATH = DATA_DIR / "overrides" / "pricing.yaml"
PROBE_SET_PATH = SPECS_DIR / "probe_set.json"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

fetch_specs = importlib.import_module("fetch_specs")

from agent_bazaar.ingestion.listing_metadata import (  # noqa: E402
    apply_override,
    extract_listing_metadata,
    load_override,
)
from agent_bazaar.ingestion.sources import (  # noqa: E402
    APIS_GURU_LIST_URL,
    ApisGuruSource,
    LocalUploadSource,
    SourceError,
    SpecSource,
)

MANIFEST_V2_FIELDS = (
    "pricing_tier",
    "access_requirement",
    "price_amount",
    "price_currency",
    "rate_limit_policy",
    "probe_budget_per_minute",
    "licence",
    "terms_url",
    "doc_quality",
    "operation_count",
    "deprecated_operations",
    "source",
    "selection_rule_version",
    "licence_reviewed_at",
)

CURATED_CAPABILITIES = (
    "GeocodeLocation",
    "GetWeatherForecast",
    "ConvertCurrency",
    "GetCountryFacts",
    "GetPublicHolidays",
    "SearchResearchPapers",
)


def free_keyless_document() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Open Weather",
            "version": "1.2.0",
            "description": "Free weather service for open use. 60 requests per minute.",
            "license": {"name": "CC0-1.0", "url": "https://creativecommons.org/publicdomain/zero/1.0/"},
            "termsOfService": "https://weather.example/terms",
        },
        "paths": {
            "/v1/forecast": {
                "get": {
                    "operationId": "getForecast",
                    "summary": "Forecast for a coordinate pair.",
                    "parameters": [
                        {
                            "name": "latitude",
                            "in": "query",
                            "schema": {"type": "number"},
                            "description": "Latitude in degrees.",
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "temperature": {"type": "number", "description": "Air temperature."}
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }


def paid_api_key_document() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Paid Weather",
            "version": "2.0.0",
            "description": "Paid plan with a subscription of 49 usd per month. An API key is required.",
        },
        "components": {
            "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}}
        },
        "security": [{"ApiKeyAuth": []}],
        "paths": {
            "/v2/forecast": {
                "get": {
                    "operationId": "getForecast",
                    "summary": "Forecast for a coordinate pair.",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }


def unknown_tier_document() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Silent Service", "version": "0.9.0", "description": "A service that says nothing."},
        "paths": {
            "/things": {
                "get": {
                    "operationId": "listThings",
                    "summary": "List things.",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }


def unknown_tier_keyed_document() -> dict:
    document = unknown_tier_document()
    document["components"] = {
        "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}}
    }
    document["security"] = [{"ApiKeyAuth": []}]
    return document


def write_spec(directory: Path, name: str, document: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_sources_satisfy_the_source_protocol() -> None:
    apis_guru = ApisGuruSource()
    local = LocalUploadSource(SPECS_DIR)

    assert isinstance(apis_guru, SpecSource)
    assert isinstance(local, SpecSource)
    for source in (apis_guru, local):
        assert source.name
        assert source.source_id
        assert source.licence_policy
        assert source.provenance()["source"] == source.source_id
        assert source.provenance()["licence_policy"] == source.licence_policy


def test_apis_guru_source_uses_the_preferred_version_without_network() -> None:
    listing = {
        "weather.example.com:1.0.0": {
            "preferred": "1.0.0",
            "versions": {
                "1.0.0": {
                    "swaggerUrl": "https://example.com/v1/swagger.json",
                    "openapiVer": "3.0.0",
                    "info": {"title": "Weather", "x-apisguru-categories": ["weather", "Data"]},
                },
                "0.9.0": {
                    "swaggerUrl": "https://example.com/v0/swagger.json",
                    "openapiVer": "2.0",
                    "info": {"title": "Weather", "x-apisguru-categories": ["weather"]},
                },
            },
        }
    }
    spec_bytes = json.dumps(free_keyless_document()).encode("utf-8")
    calls: list[str] = []

    def opener(url: str) -> bytes:
        calls.append(url)
        if url == APIS_GURU_LIST_URL:
            return json.dumps(listing).encode("utf-8")
        return spec_bytes

    source = ApisGuruSource(opener=opener)
    entries = source.list_candidates()

    assert entries == [
        {
            "key": "weather.example.com:1.0.0",
            "title": "Weather",
            "categories": ["weather", "data"],
            "provider": "",
            "version": "3.0.0",
            "url": "https://example.com/v1/swagger.json",
        }
    ]
    assert source.fetch(entries[0]) == spec_bytes
    assert calls == [APIS_GURU_LIST_URL, "https://example.com/v1/swagger.json"]
    assert source.list_candidates() == entries


def test_apis_guru_source_rejects_payloads_that_are_not_openapi() -> None:
    source = ApisGuruSource(opener=lambda url: b'{"name": "widget"}')

    with pytest.raises(SourceError):
        source.fetch({"url": "https://example.com/spec.json"})

    source.max_bytes = 10
    with pytest.raises(SourceError):
        source.fetch({"url": "https://example.com/spec.json"})


def test_local_upload_source_lists_and_fetches_submitted_specifications(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    write_spec(uploads, "zeta.json", free_keyless_document())
    write_spec(uploads, "alpha.json", paid_api_key_document())
    (uploads / "notes.txt").write_text("not a specification", encoding="utf-8")
    (uploads / "manifest.json").write_text("[]", encoding="utf-8")

    source = LocalUploadSource(uploads)
    candidates = source.list_candidates()

    assert [entry["key"] for entry in candidates] == ["alpha", "zeta"]
    assert candidates[0]["title"] == "Paid Weather"
    assert candidates[0]["version"] == "2.0.0"
    assert source.fetch(candidates[0]) == json.dumps(paid_api_key_document()).encode("utf-8")
    assert source.provenance()["source"] == "local-upload"

    with pytest.raises(SourceError):
        source.fetch({"path": str(uploads / "missing.json")})


def test_manifest_v2_entry_captures_the_commercial_facts() -> None:
    document = free_keyless_document()
    metadata = extract_listing_metadata(document, tool_id="open-weather")
    entry = fetch_specs.manifest_entry(
        {"key": "weather.example.com:1.0.0", "title": "Open Weather", "categories": ["weather"]},
        "open-weather.json",
        512,
        "existing",
        metadata,
        "apis-guru",
    )

    for field in MANIFEST_V2_FIELDS:
        assert field in entry
    assert entry["manifest_version"] == 2
    assert entry["pricing_tier"] == "free"
    assert entry["access_requirement"] == "keyless"
    assert entry["rate_limit_policy"] == "60 requests per minute"
    assert entry["probe_budget_per_minute"] == 60
    assert entry["licence"] == "CC0-1.0"
    assert entry["terms_url"] == "https://weather.example/terms"
    assert entry["operation_count"] == 1
    assert entry["deprecated_operations"] == 0
    assert entry["doc_quality"] > 0.0
    assert entry["source"] == "apis-guru"
    assert entry["selection_rule_version"] == fetch_specs.SELECTION_RULE_VERSION
    assert entry["licence_reviewed_at"] == ""


def test_manifest_v2_entry_captures_paid_api_key_and_unknown_documents() -> None:
    paid = extract_listing_metadata(paid_api_key_document(), tool_id="paid-weather")
    unknown = extract_listing_metadata(unknown_tier_document(), tool_id="silent-service")
    keyed = extract_listing_metadata(unknown_tier_keyed_document(), tool_id="silent-keyed")

    assert (paid.pricing_tier, paid.access_requirement) == ("paid", "paid_key")
    assert (unknown.pricing_tier, unknown.access_requirement) == ("unknown", "keyless")
    assert (keyed.pricing_tier, keyed.access_requirement) == ("unknown", "api_key")
    assert paid.price_amount == 49.0
    assert paid.price_currency == "USD"


def test_terms_url_falls_back_to_the_terms_of_service_without_a_licence_url() -> None:
    document = free_keyless_document()
    document["info"]["license"] = {"name": "CC0-1.0"}

    metadata = extract_listing_metadata(document, tool_id="open-weather")

    assert metadata.licence == "CC0-1.0"
    assert metadata.terms_url == "https://weather.example/terms"


def test_curated_override_wins_over_the_extracted_metadata(tmp_path: Path) -> None:
    overrides_path = tmp_path / "pricing.yaml"
    overrides_path.write_text(
        "tools:\n"
        "  open-weather:\n"
        "    pricing_tier: paid\n"
        "    access_requirement: api_key\n"
        "    licence: Provider-Terms-1.0\n"
        "    terms_url: https://weather.example/licence\n"
        "    reviewer: reviewer@example\n"
        "    checked_at: '2026-10-20'\n"
        "    note: checked against the provider terms page\n",
        encoding="utf-8",
    )
    overrides = load_override(overrides_path)
    metadata = extract_listing_metadata(free_keyless_document(), tool_id="open-weather")
    overridden = apply_override(metadata, overrides["open-weather"])

    assert metadata.pricing_tier == "free"
    assert overridden.pricing_tier == "paid"
    assert overridden.access_requirement == "api_key"
    assert overridden.licence == "Provider-Terms-1.0"
    assert overridden.terms_url == "https://weather.example/licence"
    assert overridden.provenance["override"]["reviewer"] == "reviewer@example"
    assert fetch_specs.licence_reviewed_at(overrides["open-weather"]) == "2026-10-20"


def test_curated_override_file_covers_the_live_providers() -> None:
    overrides = load_override(OVERRIDES_PATH)

    assert set(overrides) >= {
        "open-meteo-forecast",
        "frankfurter-currency",
        "nominatim-geocode",
        "restcountries-facts",
        "nager-holidays",
        "arxiv-search",
        "university-sql",
        "document-qa",
        "ideal-postcodes-co-uk",
        "citycontext-com",
        "iptwist-com",
    }
    for tool_id, entry in overrides.items():
        assert entry["pricing_tier"] in {"free", "freemium", "paid", "unknown"}, tool_id
        assert entry["access_requirement"] in {"keyless", "api_key", "paid_key"}, tool_id
        assert "licence" in entry
        assert "terms_url" in entry
        assert "reviewer" in entry
        assert "checked_at" in entry
        assert "note" in entry
    for tool_id in (
        "open-meteo-forecast",
        "frankfurter-currency",
        "nominatim-geocode",
        "restcountries-facts",
        "nager-holidays",
        "arxiv-search",
        "university-sql",
        "document-qa",
    ):
        assert overrides[tool_id]["pricing_tier"] == "free", tool_id
        assert overrides[tool_id]["access_requirement"] == "keyless", tool_id
    assert overrides["ideal-postcodes-co-uk"]["pricing_tier"] == "freemium"
    assert overrides["ideal-postcodes-co-uk"]["access_requirement"] == "paid_key"
    assert overrides["citycontext-com"]["pricing_tier"] == "free"
    assert overrides["citycontext-com"]["access_requirement"] == "api_key"
    assert overrides["iptwist-com"]["pricing_tier"] == "unknown"
    assert overrides["iptwist-com"]["access_requirement"] == "api_key"
    assert overrides["nominatim-geocode"]["licence"] == "ODbL"
    assert overrides["arxiv-search"]["licence"] == "CC0-1.0"
    assert overrides["restcountries-facts"]["licence"] == "unknown"
    assert overrides["university-sql"]["licence"] == "unknown"
    assert overrides["document-qa"]["licence"] == "unknown"


def test_refresh_diff_reports_added_removed_changed_and_version_changes() -> None:
    previous = [
        {"file": "kept.json", "version": "1.0.0", "spec_version": "1.0.0", "licence": "MIT", "pricing_tier": "free"},
        {"file": "gone.json", "version": "2.0.0", "spec_version": "2.0.0", "licence": "AGPLv3"},
    ]
    current = [
        {
            "file": "kept.json",
            "version": "1.1.0",
            "spec_version": "1.1.0",
            "licence": "Apache-2.0",
            "pricing_tier": "free",
        },
        {"file": "new.json", "version": "3.0.0", "spec_version": "3.0.0"},
    ]

    diff = fetch_specs.diff_manifests(previous, current)

    assert diff["added"] == ["new.json"]
    assert diff["removed"] == ["gone.json"]
    assert diff["changed"]["kept.json"]["licence"] == {"before": "MIT", "after": "Apache-2.0"}
    assert diff["changed"]["kept.json"]["version"] == {"before": "1.0.0", "after": "1.1.0"}
    assert diff["version_changed"]["kept.json"]["version"] == {"before": "1.0.0", "after": "1.1.0"}
    assert diff["version_changed"]["kept.json"]["spec_version"] == {"before": "1.0.0", "after": "1.1.0"}
    assert diff["counts"] == {
        "added": 1,
        "removed": 1,
        "changed": 1,
        "version_changed": 1,
        "previous": 2,
        "current": 2,
    }


def test_metadata_only_rebuilds_the_manifest_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs = tmp_path / "specs"
    write_spec(specs, "open-weather.json", free_keyless_document())
    write_spec(specs, "paid-weather.json", paid_api_key_document())
    write_spec(specs, "silent-service.json", unknown_tier_document())

    monkeypatch.setattr(
        sys,
        "argv",
        ["fetch_specs.py", "--out", str(specs), "--metadata-only", "--seed-files", "0"],
    )

    assert fetch_specs.main() == 0

    manifest = json.loads((specs / "manifest.json").read_text(encoding="utf-8"))
    by_file = {entry["file"]: entry for entry in manifest}
    assert set(by_file) == {"open-weather.json", "paid-weather.json", "silent-service.json"}
    for entry in manifest:
        for field in MANIFEST_V2_FIELDS:
            assert field in entry
    assert by_file["open-weather.json"]["pricing_tier"] == "free"
    assert by_file["open-weather.json"]["access_requirement"] == "keyless"
    assert by_file["paid-weather.json"]["pricing_tier"] == "paid"
    assert by_file["paid-weather.json"]["access_requirement"] == "paid_key"
    assert by_file["silent-service.json"]["pricing_tier"] == "unknown"


def test_refresh_writes_the_diff_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs = tmp_path / "specs"
    write_spec(specs, "open-weather.json", free_keyless_document())
    write_spec(specs, "silent-service.json", unknown_tier_document())
    previous = [
        {"file": "open-weather.json", "version": "1.0.0", "licence": "MIT"},
        {"file": "removed.json", "version": "1.0.0"},
    ]
    (specs / "manifest.json").write_text(json.dumps(previous), encoding="utf-8")
    report_path = tmp_path / "logs" / "corpus_refresh.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fetch_specs.py",
            "--out",
            str(specs),
            "--refresh",
            "--seed-files",
            "0",
            "--report",
            str(report_path),
        ],
    )

    assert fetch_specs.main() == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["counts"]["added"] == 1
    assert report["counts"]["removed"] == 1
    assert report["added"] == ["silent-service.json"]
    assert report["removed"] == ["removed.json"]
    assert "open-weather.json" in report["changed"]
    assert report["manifest_version"] == 2
    assert report["selection_rule_version"] == fetch_specs.SELECTION_RULE_VERSION


def test_seed_selection_prefers_keyless_and_free_tools() -> None:
    manifest = [
        {
            "file": "keyed.json",
            "title": "Keyed weather",
            "categories": ["weather"],
            "bytes": 100,
            "access_requirement": "api_key",
            "pricing_tier": "free",
        },
        {
            "file": "keyless.json",
            "title": "Keyless weather city forecast",
            "categories": ["weather", "location"],
            "bytes": 200,
            "access_requirement": "keyless",
            "pricing_tier": "free",
        },
        {
            "file": "keyless-paid.json",
            "title": "Keyless weather city forecast",
            "categories": ["weather", "location"],
            "bytes": 150,
            "access_requirement": "keyless",
            "pricing_tier": "paid",
        },
    ]

    chosen = fetch_specs.select_seed_files(manifest, 2, lambda entry: True, preferred_files=["keyed.json"])
    files = [entry["file"] for entry, _ in chosen]

    assert files == ["keyless.json", "keyless-paid.json"]
    assert "keyless + free tier" in chosen[0][1]
    assert "keyless" in chosen[1][1]


def corpus_directory() -> Path:
    """Return the full generated corpus when present, else the committed seed."""
    if (SPECS_DIR / "manifest.json").exists():
        return SPECS_DIR
    return SPECS_DIR / "seed"


def keyless_corpus_tools() -> set[str]:
    """Return the corpus tools the extraction rules classify as keyless."""
    overrides = load_override(OVERRIDES_PATH)
    keyless: set[str] = set()
    directory = corpus_directory()
    for path in sorted(directory.glob("*.json")):
        if path.name in {"manifest.json", "probe_set.json"}:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(document, dict) or ("openapi" not in document and "swagger" not in document):
            continue
        metadata = extract_listing_metadata(document, tool_id=path.stem)
        override = overrides.get(path.stem)
        if override:
            metadata = apply_override(metadata, override)
        if metadata.access_requirement == "keyless":
            keyless.add(path.stem)
    return keyless


def test_probe_set_file_is_valid_and_holds_keyless_tools() -> None:
    payload = json.loads(PROBE_SET_PATH.read_text(encoding="utf-8"))

    assert set(payload) >= {"selection_rule", "selected_at", "tools"}
    assert isinstance(payload["selection_rule"], str) and payload["selection_rule"]
    assert isinstance(payload["selected_at"], str) and payload["selected_at"]
    # The proposal asks for 12 to 15 keyless tools; the corpus holds fewer, so the
    # selection rule states the shortfall instead of the set claiming a full count.
    assert len(payload["tools"]) <= 15

    for tool in payload["tools"]:
        assert set(tool) == {"tool_id", "file", "capability_hint", "reason"}
        assert tool["capability_hint"] in CURATED_CAPABILITIES or tool["capability_hint"] == ""
        assert tool["reason"].strip()
        path = SPECS_DIR / tool["file"]
        if not path.exists():
            path = SPECS_DIR / "seed" / tool["file"]
        if not path.exists():
            pytest.skip(f"corpus document missing: {tool['file']}")
        document = json.loads(path.read_text(encoding="utf-8"))
        metadata = extract_listing_metadata(document, tool_id=tool["tool_id"])
        assert metadata.access_requirement == "keyless", tool["tool_id"]


def test_probe_set_holds_every_keyless_corpus_tool_and_nothing_else() -> None:
    if not (SPECS_DIR / "manifest.json").exists():
        pytest.skip("the full generated corpus is required for the probe-set equality check")
    payload = json.loads(PROBE_SET_PATH.read_text(encoding="utf-8"))
    selected = {tool["tool_id"] for tool in payload["tools"]}

    assert selected == keyless_corpus_tools()


def test_probe_set_states_the_shortfall_against_the_proposal() -> None:
    payload = json.loads(PROBE_SET_PATH.read_text(encoding="utf-8"))
    rule = payload["selection_rule"]

    assert "shortfall" in rule
    assert f"{len(payload['tools'])} of the 12 to 15" in rule
    for tool_id in (
        "ideal-postcodes-co-uk",
        "geodatasource-com",
        "interzoid-com-getzipinfo",
        "nexmo-com-pricing",
        "europeana-eu",
    ):
        assert tool_id in rule, tool_id


def test_required_api_key_parameter_makes_the_access_requirement_api_key() -> None:
    document = free_keyless_document()
    document["paths"]["/v1/forecast"]["get"]["parameters"].append(
        {"name": "api_key", "in": "query", "required": True, "schema": {"type": "string"}}
    )

    metadata = extract_listing_metadata(document, tool_id="open-weather")

    assert metadata.pricing_tier == "free"
    assert metadata.access_requirement == "api_key"
    assert any("api_key" in item for item in metadata.access_evidence)


def test_credential_parameter_referenced_from_components_parameters_is_detected() -> None:
    document = free_keyless_document()
    document["components"] = {
        "parameters": {
            "ApiKeyParameter": {
                "name": "api_key",
                "in": "query",
                "required": True,
                "description": "The API key of the caller.",
                "schema": {"type": "string"},
            }
        }
    }
    document["paths"]["/v1/forecast"]["get"]["parameters"].append({"$ref": "#/components/parameters/ApiKeyParameter"})

    metadata = extract_listing_metadata(document, tool_id="open-weather")

    assert metadata.access_requirement == "api_key"
    assert any("api_key" in item for item in metadata.access_evidence)


def test_required_parameter_named_key_is_treated_as_a_credential() -> None:
    document = free_keyless_document()
    document["paths"]["/v1/forecast"]["get"]["parameters"].append(
        {"name": "key", "in": "query", "required": True, "schema": {"type": "string"}}
    )

    metadata = extract_listing_metadata(document, tool_id="open-weather")

    assert metadata.access_requirement == "api_key"
    assert any("key" in item for item in metadata.access_evidence)


def test_prose_that_requires_an_api_key_makes_the_access_requirement_api_key() -> None:
    document = free_keyless_document()
    document["info"]["description"] = "This service requires an API key before it can be called."

    metadata = extract_listing_metadata(document, tool_id="open-weather")

    assert metadata.pricing_tier == "unknown"
    assert metadata.access_requirement == "api_key"
    assert any("prose" in item for item in metadata.access_evidence)


def test_googleapis_host_is_treated_as_requiring_a_key() -> None:
    document = free_keyless_document()
    document["servers"] = [{"url": "https://civicinfo.googleapis.com/v1"}]

    metadata = extract_listing_metadata(document, tool_id="open-weather")

    assert metadata.access_requirement == "api_key"
    assert any("googleapis.com" in item for item in metadata.access_evidence)


def test_dollar_amount_is_detected_as_a_price_in_usd() -> None:
    document = free_keyless_document()
    document["info"]["description"] = "The premium plan costs $49 per month."

    metadata = extract_listing_metadata(document, tool_id="open-weather")

    assert metadata.price_amount == 49.0
    assert metadata.price_currency == "USD"


def test_terms_of_service_wins_over_the_licence_url_for_the_terms_url() -> None:
    document = free_keyless_document()
    document["info"]["license"] = {
        "name": "CC0-1.0",
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
    }
    document["info"]["termsOfService"] = "https://weather.example/terms"

    metadata = extract_listing_metadata(document, tool_id="open-weather")

    assert metadata.licence == "CC0-1.0"
    assert metadata.terms_url == "https://weather.example/terms"


def test_corpus_manifest_agrees_with_the_corrected_access_rules() -> None:
    directory = corpus_directory()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    by_file = {entry["file"]: entry for entry in manifest}
    corrected = {
        "ideal-postcodes-co-uk.json": ("freemium", "paid_key"),
        "geodatasource-com.json": ("unknown", "api_key"),
        "interzoid-com-getzipinfo.json": ("unknown", "api_key"),
        "nexmo-com-pricing.json": ("unknown", "api_key"),
        "europeana-eu.json": ("unknown", "api_key"),
        "staging-ecotaco-com.json": ("unknown", "api_key"),
        "googleapis-com-civicinfo.json": ("unknown", "api_key"),
        "citycontext-com.json": ("free", "api_key"),
        "nytimes-com-geo-api.json": ("free", "api_key"),
        "gisgraphy-com.json": ("free", "api_key"),
        "iptwist-com.json": ("unknown", "api_key"),
        "miataru-com.json": ("unknown", "keyless"),
        "oceandrivers-com.json": ("unknown", "keyless"),
        "deutschebahn-com-fahrplan.json": ("free", "keyless"),
    }

    for file_name, (tier, access) in corrected.items():
        entry = by_file.get(file_name)
        if entry is None:
            assert directory != SPECS_DIR, f"full corpus manifest is missing {file_name}"
            continue
        assert (entry["pricing_tier"], entry["access_requirement"]) == (tier, access), file_name


def test_corpus_manifest_is_in_sync_with_the_extraction_rules() -> None:
    directory = corpus_directory()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    overrides = load_override(OVERRIDES_PATH)

    for entry in manifest:
        tool_id = entry["file"][: -len(".json")]
        document = json.loads((directory / entry["file"]).read_text(encoding="utf-8"))
        metadata = extract_listing_metadata(document, tool_id=tool_id)
        override = overrides.get(tool_id)
        if override:
            metadata = apply_override(metadata, override)
        assert entry["pricing_tier"] == metadata.pricing_tier, entry["file"]
        assert entry["access_requirement"] == metadata.access_requirement, entry["file"]
        assert entry["licence"] == metadata.licence, entry["file"]
        assert entry["terms_url"] == metadata.terms_url, entry["file"]
