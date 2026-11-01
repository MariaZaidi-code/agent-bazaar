from __future__ import annotations

import json
from typing import Any

from app.schemas import ToolSpec
from app.providers.generic import DISCOVERED_CONFIG, GenericHttpProvider


CURATED_APIS: list[dict[str, Any]] = [
    {
        "id": "hipolabs-universities",
        "name": "Hipolabs Universities",
        "provider_id": "generic",
        "description": "Search universities by country or name.",
        "capability": "GetUniversityList",
        "base_url": "https://universities.hipolabs.com",
        "path": "/search",
        "params": ["country", "name"],
        "category": "education",
    },
    {
        "id": "randomuser-profile",
        "name": "Random User Generator",
        "provider_id": "generic",
        "description": "Generate random user profiles.",
        "capability": "GetRandomUser",
        "base_url": "https://randomuser.me",
        "path": "/api/",
        "params": ["results", "gender", "nat"],
        "category": "people",
    },
    {
        "id": "quotable-quote",
        "name": "Quotable Random Quote",
        "provider_id": "generic",
        "description": "Fetch a random inspirational quote.",
        "capability": "GetQuote",
        "base_url": "https://api.quotable.io",
        "path": "/random",
        "params": ["tags", "author"],
        "category": "content",
    },
]


def sync_discovered(settings, graph, providers) -> list[str]:
    added: list[str] = []
    records = json.loads(settings.tools_file.read_text(encoding="utf-8"))
    existing_ids = {str(record.get("id")) for record in records}
    for candidate in CURATED_APIS:
        tool_id = str(candidate["id"])
        if tool_id in existing_ids or graph.get(tool_id) is not None:
            continue
        config = {
            "base_url": candidate["base_url"],
            "path": candidate["path"],
            "params": candidate.get("params", []),
        }
        DISCOVERED_CONFIG[tool_id] = config
        spec = ToolSpec(
            id=tool_id,
            name=str(candidate["name"]),
            provider_id="generic",
            description=str(candidate.get("description", "")),
            capability=str(candidate.get("capability", "GenericLookup")),
            tags=["discovered"],
            execution="live",
            is_executable=True,
        )
        records.append(spec.model_dump(mode="json"))
        existing_ids.add(tool_id)
        graph.add(spec)
        provider = GenericHttpProvider(spec, settings, providers.cache)
        providers.register(provider)
        added.append(tool_id)
    settings.tools_file.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return added
