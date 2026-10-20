"""Fetch about 100 public OpenAPI specifications from APIs.guru into data/specs.

Deterministic: same seed and list give the same corpus. A small "seed" subset is
copied to data/specs/seed and committed as the offline demo corpus.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from pathlib import Path

import requests

import _bootstrap  # noqa: F401
from agent_bazaar.config import ensure_directories, get_settings

LIST_URL = "https://api.apis.guru/v2/list.json"
PRIORITY_CATEGORIES = {
    "weather",
    "location",
    "geocoding",
    "maps",
    "currency",
    "finance",
    "government",
    "open_data",
    "data",
    "geography",
}
MAX_SPEC_BYTES = 1_500_000
SEED_KEYWORD_WEIGHTS = {
    "weather": 6,
    "forecast": 6,
    "climate": 5,
    "ocean": 4,
    "geo": 5,
    "location": 5,
    "city": 5,
    "postcode": 5,
    "postal": 5,
    "zip": 5,
    "address": 4,
    "country": 4,
    "currency": 5,
    "exchange": 5,
    "money": 3,
    "price": 2,
    "holiday": 4,
    "time": 2,
    "date": 2,
    "elevation": 4,
}
SEED_PREFERRED_FILES = [
    "citycontext-com.json",
    "gisgraphy-com.json",
    "ideal-postcodes-co-uk.json",
    "interzoid-com-getzipinfo.json",
    "miataru-com.json",
    "nytimes-com-geo-api.json",
    "iptwist-com.json",
    "deutschebahn-com-fahrplan.json",
]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def fetch_json(url: str, timeout: int) -> dict:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "agent-bazaar-corpus/0.1"})
    response.raise_for_status()
    return response.json()


def candidate_entries(listing: dict) -> list[dict]:
    entries = []
    for key, entry in listing.items():
        preferred = entry.get("preferred")
        version = (entry.get("versions") or {}).get(preferred or "", {})
        url = version.get("swaggerUrl")
        info = version.get("info") or {}
        if not url:
            continue
        entries.append(
            {
                "key": key,
                "title": info.get("title") or key,
                "categories": [str(c).lower() for c in (info.get("x-apisguru-categories") or [])],
                "provider": info.get("x-apisguru-provider-name") or "",
                "version": version.get("openapiVer") or preferred or "",
                "url": url,
            }
        )
    return sorted(entries, key=lambda item: item["key"])


def select_entries(entries: list[dict], limit: int, rng: random.Random) -> list[dict]:
    priority = [e for e in entries if PRIORITY_CATEGORIES.intersection(e["categories"])]
    rest = [e for e in entries if e not in priority]
    rng.shuffle(priority)
    rng.shuffle(rest)
    half = max(1, limit // 2)
    selection = priority[:half] + rest[: limit - min(half, len(priority))]
    return sorted(selection, key=lambda item: item["key"])


def download(url: str, destination: Path, timeout: int) -> int:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "agent-bazaar-corpus/0.1"})
    response.raise_for_status()
    content = response.content
    if len(content) > MAX_SPEC_BYTES:
        raise ValueError(f"spec too large ({len(content)} bytes)")
    body = content.decode("utf-8", errors="replace")
    if '"openapi"' not in body[:2000] and '"swagger"' not in body[:2000]:
        raise ValueError("not an OpenAPI document")
    destination.write_text(body, encoding="utf-8")
    return len(content)


def main() -> int:
    settings = ensure_directories()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed-files", type=int, default=8, help="copies of the smallest specs kept as the committed seed corpus")
    parser.add_argument("--out", type=Path, default=settings.paths.specs_dir)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    listing = fetch_json(LIST_URL, args.timeout)
    entries = candidate_entries(listing)
    rng = random.Random(args.seed)
    selection = select_entries(entries, args.limit, rng)

    manifest: list[dict] = []
    skipped: list[dict] = []
    for entry in selection:
        filename = slugify(entry["key"]) + ".json"
        destination = args.out / filename
        if destination.exists() and not args.force:
            size = destination.stat().st_size
            manifest.append({**entry, "file": filename, "bytes": size, "status": "existing"})
            continue
        try:
            size = download(entry["url"], destination, args.timeout)
            manifest.append({**entry, "file": filename, "bytes": size, "status": "downloaded"})
        except Exception as exc:
            skipped.append({**entry, "error": str(exc)})

    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"corpus: {len(manifest)} specs in {args.out} ({len(skipped)} skipped)")

    if args.seed_files and args.out.name != "seed":
        seed_dir = args.out / "seed"
        seed_dir.mkdir(exist_ok=True)
        def seed_score(entry: dict) -> tuple[int, int]:
            haystack = " ".join(
                [str(entry.get("title") or ""), " ".join(entry.get("categories") or [])]
            ).lower()
            score = sum(weight for word, weight in SEED_KEYWORD_WEIGHTS.items() if word in haystack)
            return (-score, entry.get("bytes", 0))

        def has_outputs(entry: dict) -> bool:
            from agent_bazaar.ingestion.models import flatten_fields
            from agent_bazaar.ingestion.utility import IngestionUtility

            try:
                fields = flatten_fields(IngestionUtility(settings.ingestion).ingest(args.out / entry["file"]))
            except Exception:
                return False
            return any(field.direction == "output" for field in fields)

        ranked = sorted(manifest, key=seed_score)
        by_file = {entry["file"]: entry for entry in manifest}
        chosen = [by_file[name] for name in SEED_PREFERRED_FILES if name in by_file]
        chosen = [entry for entry in chosen if has_outputs(entry)][: args.seed_files]
        for entry in ranked:
            if len(chosen) >= args.seed_files:
                break
            if entry in chosen or not has_outputs(entry):
                continue
            chosen.append(entry)
        for stale in seed_dir.glob("*.json"):
            if stale.name != "manifest.json" and stale.name not in {entry["file"] for entry in chosen}:
                stale.unlink()
        seed_manifest = []
        for entry in chosen:
            source = args.out / entry["file"]
            if not source.exists():
                continue
            shutil.copy2(source, seed_dir / entry["file"])
            seed_manifest.append(entry)
        (seed_dir / "manifest.json").write_text(json.dumps(seed_manifest, indent=1), encoding="utf-8")
        print(f"seed corpus: {len(seed_manifest)} specs in {seed_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
