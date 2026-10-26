from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_bazaar_auditor.claims import Claim  # noqa: E402
from agent_bazaar_auditor.enums import ClaimLabel, ClaimType  # noqa: E402
from agent_bazaar_auditor.tools import build_catalog  # noqa: E402
from agent_bazaar_auditor.utils import stable_id  # noqa: E402

DATA_DIR = ROOT / "data"

REAL_VERIFIED = [
    "61759eb13ddc",
    "9f7258cdeb71",
    "6d14b5e61e58",
    "95d0ce9af742",
    "bb858cac0d1a",
    "0dde82d62e88",
    "22d7bcd49681",
    "0ecbf0269f4f",
    "57d7a3361d83",
    "c9253ce1108b",
    "3ca0964f01f9",
    "a7b4400d7638",
    "61db25052b12",
    "cbd3df9374cd",
    "a8b05cdc5c2d",
    "62a5f124f1de",
    "bc5e15aadfcc",
    "7de8cb3562ae",
    "e6b72c1ed7fc",
    "eb70f4b95aa7",
    "bedeb3426cdc",
    "c29c442ad5f0",
    "95df0a5191ee",
    "620b7e568395",
    "edfff245a094",
    "b1d27ccc5ae9",
    "05dab54a15fd",
    "20a785e03b70",
    "6779ab2b0ab1",
    "7d8812cfb455",
    "402a93e2995a",
    "812f0b01c868",
]

REAL_SUPPORTED_DOC_ONLY = [
    "189c01e3a534",
    "80d1ca588ca4",
    "8440a0054a15",
    "a75f5b098d9c",
]

REAL_SUPPORTED_OUTAGE = [
    "c037e67c6a75",
    "6185c3978cab",
    "eaee41c992b8",
    "b2d8fa5f898d",
]


def find_claim(catalog, claim_id: str):
    for tool in catalog.values():
        for claim in tool.claims:
            if claim.id == claim_id:
                return tool, claim
    raise KeyError(claim_id)


def seeded_claim(
    tool_id: str,
    text: str,
    claim_type: ClaimType,
    *,
    field_path: str | None = None,
    expected_type: str | None = None,
    expected_unit: str | None = None,
    expected_limit: int | None = None,
    probeable: bool = False,
) -> Claim:
    return Claim(
        id=stable_id("seeded", tool_id, text),
        tool_id=tool_id,
        text=text,
        claim_type=claim_type,
        field_path=field_path,
        expected_type=expected_type,
        expected_unit=expected_unit,
        expected_limit=expected_limit,
        probeable=probeable,
        source_text=text,
        metadata={"seeded": True},
    )


def build_claim_dataset(catalog) -> dict:
    items: list[dict] = []
    notes = {
        "61759eb13ddc": "Real unit claim; fixture probe agrees.",
        "bb858cac0d1a": "Real response-shape claim.",
    }
    for index, claim_id in enumerate(REAL_VERIFIED, start=1):
        tool, claim = find_claim(catalog, claim_id)
        items.append(
            {
                "id": f"cv-real-verified-{index:02d}",
                "tool_id": tool.tool_id,
                "claim": claim.to_dict(),
                "documentation": None,
                "mock_behavior": "normal",
                "mock_options": {},
                "ground_truth_label": ClaimLabel.VERIFIED.value,
                "seeded": False,
                "focus": "real",
                "rationale": notes.get(claim_id, "Real documentation claim with a probeable deterministic check."),
            }
        )
    for index, claim_id in enumerate(REAL_SUPPORTED_DOC_ONLY, start=1):
        tool, claim = find_claim(catalog, claim_id)
        items.append(
            {
                "id": f"cv-real-supported-doc-{index:02d}",
                "tool_id": tool.tool_id,
                "claim": claim.to_dict(),
                "documentation": None,
                "mock_behavior": "normal",
                "mock_options": {},
                "ground_truth_label": ClaimLabel.SUPPORTED.value,
                "seeded": False,
                "focus": "not_probeable",
                "rationale": "Documentation supports the claim but the claim is not testable with a safe live call.",
            }
        )
    for index, claim_id in enumerate(REAL_SUPPORTED_OUTAGE, start=1):
        tool, claim = find_claim(catalog, claim_id)
        items.append(
            {
                "id": f"cv-real-supported-outage-{index:02d}",
                "tool_id": tool.tool_id,
                "claim": claim.to_dict(),
                "documentation": None,
                "mock_behavior": "outage",
                "mock_options": {},
                "ground_truth_label": ClaimLabel.SUPPORTED.value,
                "seeded": False,
                "focus": "probe_error",
                "rationale": "Documentation supports the claim, but the controlled outage makes the probe inconclusive.",
            }
        )

    contradicted = [
        (
            "open-meteo",
            "The current temperature is returned in degrees Fahrenheit.",
            ClaimType.UNIT,
            "current.temperature_2m",
            "number",
            "fahrenheit",
            None,
            True,
            ["Open-Meteo returns the field `temperature_2m` in degrees Fahrenheit."],
            "Subtle wrong-unit claim: the documentation was seeded to support Fahrenheit, while the API returns Celsius.",
        ),
        (
            "open-meteo",
            "Forecasts are available up to 30 days.",
            ClaimType.LIMIT,
            None,
            "number",
            None,
            30,
            True,
            ["Forecasts are available up to 30 days."],
            "Wrong-limit claim: the safe probe request returns 16 daily entries.",
        ),
        (
            "frankfurter",
            "An API key is required to access exchange rates.",
            ClaimType.AUTHENTICATION,
            None,
            "boolean",
            None,
            None,
            True,
            ["An API key is required for this endpoint."],
            "False authentication claim: the keyless probe succeeds.",
        ),
        (
            "frankfurter",
            "The response returns `rates` as a JSON array.",
            ClaimType.OUTPUT_FIELD,
            "rates",
            "array",
            None,
            None,
            True,
            ["The response includes `rates` as a JSON array."],
            "Wrong response-shape claim: the probe returns an object, not an array.",
        ),
        (
            "nominatim",
            "Latitude and longitude are returned as numbers.",
            ClaimType.OUTPUT_FIELD,
            "lat",
            "number",
            None,
            None,
            True,
            ["Each result includes `lat` and `lon` as numbers in decimal degrees."],
            "Wrong-type claim: the real API returns coordinate strings.",
        ),
        (
            "rest-countries",
            "Population is returned as a string.",
            ClaimType.OUTPUT_FIELD,
            "population",
            "string",
            None,
            None,
            True,
            ["The response includes `population` as a string."],
            "Wrong-type claim: the probe returns a JSON number.",
        ),
        (
            "nager-date",
            "Each holiday always includes a date field.",
            ClaimType.OUTPUT_FIELD,
            "date",
            "present",
            None,
            None,
            True,
            None,
            "Field-removal scenario: the documentation supports the claim, but the provider removes the date field.",
        ),
        (
            "open-meteo",
            "Wind speed is returned in metres per second.",
            ClaimType.UNIT,
            "current.wind_speed_10m",
            "number",
            "m",
            None,
            True,
            ["The field `wind_speed_10m` is returned in metres per second."],
            "Subtle wrong-unit claim: the probe reports km/h.",
        ),
        (
            "ipify",
            "An API key is required to retrieve the public IP address.",
            ClaimType.AUTHENTICATION,
            None,
            "boolean",
            None,
            None,
            True,
            ["An API key is required for this endpoint."],
            "False authentication claim: the keyless probe succeeds.",
        ),
        (
            "coingecko",
            "The response includes `bitcoin.eur` with the price in euros.",
            ClaimType.OUTPUT_FIELD,
            "bitcoin.eur",
            "number",
            None,
            None,
            True,
            ["The response includes `bitcoin.eur` with the price in euros."],
            "Missing-field claim: the free probe requests USD and has no EUR field.",
        ),
    ]
    for index, row in enumerate(contradicted, start=1):
        (
            tool_id,
            text,
            claim_type,
            field_path,
            expected_type,
            expected_unit,
            expected_limit,
            probeable,
            documentation,
            rationale,
        ) = row
        claim = seeded_claim(
            tool_id,
            text,
            claim_type,
            field_path=field_path,
            expected_type=expected_type,
            expected_unit=expected_unit,
            expected_limit=expected_limit,
            probeable=probeable,
        )
        items.append(
            {
                "id": f"cv-seeded-contradicted-{index:02d}",
                "tool_id": tool_id,
                "claim": claim.to_dict(),
                "documentation": documentation,
                "mock_behavior": "remove_field" if tool_id == "nager-date" else "normal",
                "mock_options": {"field_path": "date"} if tool_id == "nager-date" else {},
                "ground_truth_label": ClaimLabel.CONTRADICTED.value,
                "seeded": True,
                "focus": "seeded_false_claim",
                "rationale": rationale,
            }
        )

    unsupported = [
        (
            "open-meteo",
            "Forecasts are 99% accurate.",
            ClaimType.AVAILABILITY,
            "Accuracy is not stated in the supplied documentation and cannot be tested by a safe call.",
        ),
        (
            "open-meteo",
            "Weather data refreshes every ten seconds.",
            ClaimType.AVAILABILITY,
            "No evidence is supplied for the refresh interval.",
        ),
        (
            "frankfurter",
            "Exchange rates are updated every hour.",
            ClaimType.AVAILABILITY,
            "The documentation does not state an hourly update schedule.",
        ),
        (
            "nominatim",
            "Batch geocoding supports 1000 addresses per request.",
            ClaimType.LIMIT,
            "The documentation is silent and the claim is excluded from probing to respect usage limits.",
        ),
        (
            "rest-countries",
            "Country records are updated every day at midnight.",
            ClaimType.AVAILABILITY,
            "No update-time evidence exists in the supplied documentation.",
        ),
        (
            "nager-date",
            "The holiday calendar covers every country in the world.",
            ClaimType.BEHAVIOUR,
            "Coverage of every country is not evidenced and cannot be checked by one safe call.",
        ),
        (
            "arxiv",
            "Search results are ranked by citation count.",
            ClaimType.BEHAVIOUR,
            "Citation-ranked ordering is not documented and is not tested by the live probe.",
        ),
        (
            "dog-ceo",
            "Images load in under 100 milliseconds worldwide.",
            ClaimType.AVAILABILITY,
            "Latency claims are not probeable with one controlled request.",
        ),
        (
            "cat-fact",
            "Every fact has been reviewed by a veterinarian.",
            ClaimType.BEHAVIOUR,
            "No evidence of expert review is supplied.",
        ),
        (
            "worldtime",
            "The service has 99.99% uptime.",
            ClaimType.AVAILABILITY,
            "Uptime is not testable from a single probe and no evidence is supplied.",
        ),
    ]
    for index, (tool_id, text, claim_type, rationale) in enumerate(unsupported, start=1):
        claim = seeded_claim(tool_id, text, claim_type, probeable=False)
        items.append(
            {
                "id": f"cv-seeded-unsupported-{index:02d}",
                "tool_id": tool_id,
                "claim": claim.to_dict(),
                "documentation": [],
                "mock_behavior": "normal",
                "mock_options": {},
                "ground_truth_label": ClaimLabel.UNSUPPORTED.value,
                "seeded": True,
                "focus": "seeded_no_evidence",
                "rationale": rationale,
            }
        )

    counts: dict[str, int] = {}
    for item in items:
        label = item["ground_truth_label"]
        counts[label] = counts.get(label, 0) + 1
    return {
        "schema_version": 1,
        "name": "Agent Bazaar claim-verification evaluation set",
        "version": "1.0",
        "created_for": "Auditor and Monitoring Lead (Qaim Hussnain)",
        "notes": [
            "40 real claims and 20 seeded claims.",
            "Seeded claims measure detection ability, not real-world prevalence.",
            "Documentation overrides are frozen for reproducibility.",
            "Outage items produce probe-error evidence; the decision table labels them Supported when docs support the claim.",
        ],
        "counts": counts,
        "items": items,
    }


def build_drift_dataset() -> dict:
    scenarios = [
        {
            "id": "drift-01",
            "tool_id": "open-meteo",
            "behavior": "rename_field",
            "options": {"field_path": "current.temperature_2m", "new_name": "temperature"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Mapped temperature field renamed from temperature_2m to temperature.",
        },
        {
            "id": "drift-02",
            "tool_id": "rest-countries",
            "behavior": "rename_field",
            "options": {"field_path": "population", "new_name": "pop"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Population field renamed to pop.",
        },
        {
            "id": "drift-03",
            "tool_id": "usgs-earthquake",
            "behavior": "rename_field",
            "options": {"field_path": "properties.mag", "new_name": "magnitude"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Nested magnitude field renamed.",
        },
        {
            "id": "drift-04",
            "tool_id": "dog-ceo",
            "behavior": "rename_field",
            "options": {"field_path": "message", "new_name": "image_url"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Image URL field renamed.",
        },
        {
            "id": "drift-05",
            "tool_id": "nager-date",
            "behavior": "remove_field",
            "options": {"field_path": "date"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Holiday date field removed.",
        },
        {
            "id": "drift-06",
            "tool_id": "open-library",
            "behavior": "remove_field",
            "options": {"field_path": "docs"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Search results array removed.",
        },
        {
            "id": "drift-07",
            "tool_id": "open-meteo",
            "behavior": "remove_field",
            "options": {"field_path": "current.wind_speed_10m"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Wind speed field removed.",
        },
        {
            "id": "drift-08",
            "tool_id": "arxiv",
            "behavior": "remove_field",
            "options": {"field_path": "feed.entry.title"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Entry title removed from the Atom response.",
        },
        {
            "id": "drift-09",
            "tool_id": "cat-fact",
            "behavior": "type_change",
            "options": {"field_path": "length", "replacement": "not-a-number"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Fact length changes from number to text.",
        },
        {
            "id": "drift-10",
            "tool_id": "coingecko",
            "behavior": "type_change",
            "options": {"field_path": "bitcoin.usd", "replacement": "price unavailable"},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Cryptocurrency price changes from number to text.",
        },
        {
            "id": "drift-11",
            "tool_id": "open-meteo",
            "behavior": "unit_change",
            "options": {
                "field_path": "current.temperature_2m",
                "unit_path": "current_units.temperature_2m",
                "from_unit": "celsius",
                "to_unit": "fahrenheit",
            },
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Temperature silently switches from Celsius to Fahrenheit.",
        },
        {
            "id": "drift-12",
            "tool_id": "open-meteo",
            "behavior": "unit_change",
            "options": {
                "field_path": "current.wind_speed_10m",
                "unit_path": "current_units.wind_speed_10m",
                "from_unit": "km",
                "to_unit": "m",
            },
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Wind speed unit and value change from km/h to m/s-scale metres.",
        },
        {
            "id": "drift-13",
            "tool_id": "open-meteo",
            "behavior": "garbage_200",
            "options": {},
            "expected_detector": "embedding",
            "expected_round": 1,
            "description": "HTTP 200 response keeps mapped fields but is filled with unrelated garbage structure.",
        },
        {
            "id": "drift-14",
            "tool_id": "nominatim",
            "behavior": "garbage_200",
            "options": {},
            "expected_detector": "embedding",
            "expected_round": 1,
            "description": "Geocoding response polluted with garbage fields.",
        },
        {
            "id": "drift-15",
            "tool_id": "rest-countries",
            "behavior": "garbage_200",
            "options": {},
            "expected_detector": "embedding",
            "expected_round": 1,
            "description": "Country response polluted with garbage fields.",
        },
        {
            "id": "drift-16",
            "tool_id": "ipify",
            "behavior": "outage",
            "options": {},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Provider returns HTTP 503 on demand.",
        },
        {
            "id": "drift-17",
            "tool_id": "worldtime",
            "behavior": "outage",
            "options": {},
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Time provider goes offline.",
        },
        {
            "id": "drift-18",
            "tool_id": "joke-api",
            "behavior": "flapping",
            "options": {"fail_on_calls": [2]},
            "expected_detector": "rule",
            "expected_round": 2,
            "description": "Provider alternates between success and failure.",
        },
        {
            "id": "drift-19",
            "tool_id": "datamuse",
            "behavior": "flapping",
            "options": {"fail_on_calls": [2]},
            "expected_detector": "rule",
            "expected_round": 2,
            "description": "Word service flaps on its second call after injection.",
        },
        {
            "id": "drift-20",
            "tool_id": "open-meteo",
            "behavior": "dishonest",
            "options": {
                "field_path": "current.temperature_2m",
                "unit_path": "current_units.temperature_2m",
                "from_unit": "celsius",
                "to_unit": "fahrenheit",
            },
            "expected_detector": "rule",
            "expected_round": 1,
            "description": "Dishonest provider advertises Celsius-quality data but silently serves Fahrenheit values.",
        },
    ]
    return {
        "schema_version": 1,
        "name": "Agent Bazaar injected drift evaluation set",
        "version": "1.0",
        "notes": [
            "20 injected changes across rename, remove, type, unit, garbage, outage, flapping and dishonest behaviours.",
            "Detection is evaluated after a normal baseline probe.",
            "Garbage 200 cases are expected to be missed by rule checks and caught by embedding drift.",
            "Flapping uses fail_on_calls [2], so detection is expected on the second post-injection probe.",
        ],
        "scenarios": scenarios,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog()
    claim_dataset = build_claim_dataset(catalog)
    drift_dataset = build_drift_dataset()
    (DATA_DIR / "seeded_claims.json").write_text(
        json.dumps(claim_dataset, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (DATA_DIR / "drift_scenarios.json").write_text(
        json.dumps(drift_dataset, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(claim_dataset['items'])} claim items and {len(drift_dataset['scenarios'])} drift scenarios")
    print("claim label counts", claim_dataset["counts"])


if __name__ == "__main__":
    main()
