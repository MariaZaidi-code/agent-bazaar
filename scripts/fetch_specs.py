"""Fetch public OpenAPI specifications into data/specs and record their metadata.

Deterministic: same seed and list give the same corpus. A small "seed" subset is
copied to data/specs/seed and committed as the offline demo corpus.

Manifest v2 adds the commercial, access and documentation facts of every
specification (pricing tier, access requirement, licence, rate limit policy,
documentation quality). The facts are extracted from the document with the
deterministic rules of ``agent_bazaar.ingestion.listing_metadata`` and are then
corrected by the curated overrides in ``data/overrides/pricing.yaml``, so a human
review always wins over a rule.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from agent_bazaar.config import ensure_directories
from agent_bazaar.ingestion.listing_metadata import (
    ListingMetadata,
    apply_override,
    extract_listing_metadata,
    load_override,
)
from agent_bazaar.ingestion.sources import APIS_GURU_LIST_URL, ApisGuruSource, LocalUploadSource, SpecSource

LIST_URL = APIS_GURU_LIST_URL
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERRIDES = REPO_ROOT / "data" / "overrides" / "pricing.yaml"
REFRESH_REPORT_NAME = "corpus_refresh.json"
MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 2
SELECTION_RULE_VERSION = "seed-selection-v2"
SEED_TIERS = ("free", "unknown")
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
    response = ApisGuruSource(timeout=timeout).opener(url)
    payload = json.loads(response.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def candidate_entries(listing: dict) -> list[dict]:
    return ApisGuruSource.entries_from_listing(listing)


def select_entries(entries: list[dict], limit: int, rng: random.Random) -> list[dict]:
    priority = [e for e in entries if PRIORITY_CATEGORIES.intersection(e["categories"])]
    rest = [e for e in entries if e not in priority]
    rng.shuffle(priority)
    rng.shuffle(rest)
    half = max(1, limit // 2)
    selection = priority[:half] + rest[: limit - min(half, len(priority))]
    return sorted(selection, key=lambda item: item["key"])


def download(url: str, destination: Path, timeout: int) -> int:
    content = ApisGuruSource(timeout=timeout).fetch({"url": url})
    destination.write_text(content.decode("utf-8", errors="replace"), encoding="utf-8")
    return len(content)


def read_manifest(path: Path) -> list[dict]:
    """Read a manifest file and return its entries."""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = payload.get("entries") or []
    if not isinstance(payload, list):
        return []
    return [entry for entry in payload if isinstance(entry, dict)]


def write_manifest(path: Path, manifest: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def licence_reviewed_at(override: dict | None) -> str:
    """Return the review date of a curated override, empty while nobody reviewed it."""
    if not override:
        return ""
    if not str(override.get("reviewer") or "").strip():
        return ""
    return str(override.get("checked_at") or "").strip()


def listing_metadata(document: dict, tool_id: str, overrides: dict[str, dict]) -> ListingMetadata:
    """Extract the listing metadata of a document and apply the curated override."""
    metadata = extract_listing_metadata(document, tool_id=tool_id)
    override = overrides.get(tool_id)
    if override:
        metadata = apply_override(metadata, override)
    return metadata


def safe_listing_metadata(content: bytes, tool_id: str, overrides: dict[str, dict]) -> ListingMetadata:
    """Extract listing metadata without ever failing the corpus build."""
    try:
        document = json.loads(content.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        document = None
    if not isinstance(document, dict):
        return ListingMetadata(
            tool_id=tool_id,
            provenance={"method": "deterministic_rules", "source": "unreadable_document"},
        )
    return listing_metadata(document, tool_id, overrides)


def manifest_entry(
    base: dict,
    file_name: str,
    size: int,
    status: str,
    metadata: ListingMetadata,
    source_id: str,
    selection_rule_version: str = SELECTION_RULE_VERSION,
    reviewed_at: str = "",
) -> dict:
    """Build one manifest v2 entry."""
    return {
        **base,
        "file": file_name,
        "bytes": size,
        "status": status,
        "manifest_version": MANIFEST_VERSION,
        "pricing_tier": metadata.pricing_tier,
        "access_requirement": metadata.access_requirement,
        "price_amount": metadata.price_amount,
        "price_currency": metadata.price_currency,
        "rate_limit_policy": metadata.rate_limit_policy,
        "probe_budget_per_minute": metadata.probe_budget_per_minute,
        "licence": metadata.licence,
        "terms_url": metadata.terms_url,
        "doc_quality": metadata.doc_quality,
        "operation_count": metadata.operation_count,
        "deprecated_operations": metadata.deprecated_operations,
        "spec_version": metadata.spec_version,
        "source": source_id,
        "selection_rule_version": selection_rule_version,
        "licence_reviewed_at": reviewed_at,
    }


def base_entry(entry: dict, document: dict | None = None) -> dict:
    """Return the descriptive fields of a manifest entry."""
    info = document.get("info") if isinstance(document, dict) and isinstance(document.get("info"), dict) else {}
    return {
        "key": entry.get("key") or (info or {}).get("title") or "",
        "title": entry.get("title") or (info or {}).get("title") or "",
        "categories": entry.get("categories") or [],
        "provider": entry.get("provider") or "",
        "version": entry.get("version") or (info or {}).get("version") or "",
        "url": entry.get("url") or "",
    }


def seed_keyword_score(entry: dict) -> tuple[int, list[str]]:
    """Score a candidate by the demo keywords of its title and categories."""
    haystack = " ".join(
        [str(entry.get("title") or ""), " ".join(entry.get("categories") or [])]
    ).lower()
    matched = [word for word in SEED_KEYWORD_WEIGHTS if word in haystack]
    return sum(SEED_KEYWORD_WEIGHTS[word] for word in matched), matched


def seed_preference(entry: dict) -> int:
    """Rank a candidate for the seed corpus: keyless and free first."""
    access = str(entry.get("access_requirement") or "unknown")
    tier = str(entry.get("pricing_tier") or "unknown")
    if access != "keyless":
        return 2
    return 0 if tier in SEED_TIERS else 1


def seed_reason(entry: dict, score: int, matched: list[str], preferred: bool) -> str:
    """Explain why a specification was picked for the committed seed corpus."""
    access = str(entry.get("access_requirement") or "unknown")
    tier = str(entry.get("pricing_tier") or "unknown")
    keywords = ", ".join(matched) if matched else "no keyword match"
    preference = seed_preference(entry)
    if preference == 0:
        parts = [f"keyless + {tier} tier"]
    elif preference == 1:
        parts = [f"fallback, keyless but {tier} tier"]
    else:
        parts = [f"fallback, {access} + {tier} tier"]
    if preferred:
        parts.append("preferred seed file")
    parts.append(f"keyword score {score} ({keywords})")
    return "; ".join(parts)


def select_seed_files(
    manifest: list[dict],
    count: int,
    has_outputs: Callable[[dict], bool],
    preferred_files: list[str] | None = None,
) -> list[tuple[dict, str]]:
    """Choose the committed seed corpus, preferring keyless and free tools.

    A candidate is preferred when it is keyless and its pricing tier is free or
    unknown; every other candidate is only a fallback. The returned reason is
    written into the manifest so the choice can be reviewed later.
    """
    preferred = list(preferred_files) if preferred_files is not None else list(SEED_PREFERRED_FILES)
    order = {name: index for index, name in enumerate(preferred)}
    eligible = [entry for entry in manifest if has_outputs(entry)]

    def rank(entry: dict) -> tuple:
        score, _ = seed_keyword_score(entry)
        file_name = str(entry.get("file"))
        return (
            seed_preference(entry),
            order.get(file_name, len(order)),
            -score,
            int(entry.get("bytes") or 0),
            file_name,
        )

    chosen: list[tuple[dict, str]] = []
    for entry in sorted(eligible, key=rank):
        if len(chosen) >= count:
            break
        file_name = str(entry.get("file"))
        if any(str(chosen_entry.get("file")) == file_name for chosen_entry, _ in chosen):
            continue
        score, matched = seed_keyword_score(entry)
        is_preferred = file_name in order
        chosen.append((entry, seed_reason(entry, score, matched, is_preferred)))
    return chosen


def diff_manifests(previous: list[dict], current: list[dict]) -> dict:
    """Compare two manifests and report added, removed and changed entries."""
    previous_by_file = {str(entry.get("file")): entry for entry in previous}
    current_by_file = {str(entry.get("file")): entry for entry in current}
    shared = sorted(set(previous_by_file) & set(current_by_file))
    added = sorted(set(current_by_file) - set(previous_by_file))
    removed = sorted(set(previous_by_file) - set(current_by_file))
    changed: dict[str, dict] = {}
    version_changed: dict[str, dict] = {}
    for file_name in shared:
        old = previous_by_file[file_name]
        new = current_by_file[file_name]
        field_changes = {
            key: {"before": old.get(key), "after": new.get(key)}
            for key in sorted(set(old) | set(new))
            if old.get(key) != new.get(key)
        }
        if field_changes:
            changed[file_name] = field_changes
        versions = {
            "version": {"before": old.get("version", ""), "after": new.get("version", "")},
            "spec_version": {"before": old.get("spec_version", ""), "after": new.get("spec_version", "")},
        }
        differing = {key: value for key, value in versions.items() if value["before"] != value["after"]}
        if differing:
            version_changed[file_name] = differing
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "version_changed": version_changed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "version_changed": len(version_changed),
            "previous": len(previous_by_file),
            "current": len(current_by_file),
        },
    }


def build_source(args: argparse.Namespace) -> SpecSource:
    if args.source == "local":
        local_dir = args.local_dir or (args.out / "uploads")
        return LocalUploadSource(local_dir, timeout=args.timeout)
    return ApisGuruSource(timeout=args.timeout)


def outputs_available(entry: dict, out_dir: Path, settings: Any) -> bool:
    """Report whether a specification declares at least one output field."""
    from agent_bazaar.ingestion.models import flatten_fields
    from agent_bazaar.ingestion.utility import IngestionUtility

    try:
        fields = flatten_fields(IngestionUtility(settings.ingestion).ingest(out_dir / str(entry.get("file"))))
    except Exception:
        return False
    return any(field.direction == "output" for field in fields)


def rebuild_manifest(
    out_dir: Path,
    overrides: dict[str, dict],
    source_id: str,
    previous: list[dict],
) -> list[dict]:
    """Recompute the manifest of an already downloaded corpus."""
    previous_by_file = {str(entry.get("file")): entry for entry in previous}
    manifest: list[dict] = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name == MANIFEST_NAME:
            continue
        content = path.read_bytes()
        try:
            document = json.loads(content.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            document = {}
        if not isinstance(document, dict):
            document = {}
        tool_id = path.stem
        if "openapi" not in document and "swagger" not in document:
            continue
        metadata = listing_metadata(document, tool_id, overrides)
        base = base_entry(previous_by_file.get(path.name, {}), document)
        manifest.append(
            manifest_entry(
                base,
                path.name,
                path.stat().st_size,
                str(previous_by_file.get(path.name, {}).get("status") or "existing"),
                metadata,
                source_id,
                reviewed_at=licence_reviewed_at(overrides.get(tool_id)),
            )
        )
    return manifest


def rebuild_seed_manifest(
    seed_dir: Path,
    overrides: dict[str, dict],
    source_id: str,
    previous: list[dict],
    reasons: dict[str, str],
) -> list[dict]:
    """Recompute the manifest of the committed seed corpus."""
    if not seed_dir.exists():
        return []
    previous_by_file = {str(entry.get("file")): entry for entry in previous}
    seed_manifest: list[dict] = []
    for path in sorted(seed_dir.glob("*.json")):
        if path.name == MANIFEST_NAME:
            continue
        content = path.read_bytes()
        try:
            document = json.loads(content.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            document = {}
        if not isinstance(document, dict):
            document = {}
        tool_id = path.stem
        metadata = listing_metadata(document, tool_id, overrides)
        base = base_entry(previous_by_file.get(path.name, {}), document)
        entry = manifest_entry(
            base,
            path.name,
            path.stat().st_size,
            str(previous_by_file.get(path.name, {}).get("status") or "existing"),
            metadata,
            source_id,
            reviewed_at=licence_reviewed_at(overrides.get(tool_id)),
        )
        entry["seed"] = True
        entry["seed_reason"] = reasons.get(path.name, "carried over from the previous seed corpus")
        seed_manifest.append(entry)
    return seed_manifest


def annotate_seed(manifest: list[dict], seed_dir: Path, reasons: dict[str, str]) -> None:
    """Record in the manifest which entries belong to the committed seed corpus."""
    seed_files = set()
    if seed_dir.exists():
        seed_files = {path.name for path in seed_dir.glob("*.json") if path.name != MANIFEST_NAME}
    for entry in manifest:
        file_name = str(entry.get("file"))
        if file_name not in seed_files:
            continue
        entry["seed"] = True
        entry["seed_reason"] = reasons.get(file_name, "carried over from the previous seed corpus")


def relative_to_repo(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def refresh_report(
    previous: list[dict],
    current: list[dict],
    manifest_path: Path,
    overrides_path: Path,
    source_id: str,
) -> dict:
    """Build the refresh report that records what changed since the last manifest."""
    diff = diff_manifests(previous, current)
    previous_version = next(
        (int(entry.get("manifest_version")) for entry in previous if entry.get("manifest_version")),
        1,
    )
    return {
        "manifest_version": MANIFEST_VERSION,
        "previous_manifest_version": previous_version,
        "selection_rule_version": SELECTION_RULE_VERSION,
        "source": source_id,
        "manifest_path": relative_to_repo(manifest_path),
        "overrides": relative_to_repo(overrides_path),
        "counts": diff["counts"],
        "added": diff["added"],
        "removed": diff["removed"],
        "changed": diff["changed"],
        "version_changed": diff["version_changed"],
    }


def main() -> int:
    settings = ensure_directories()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--seed-files",
        type=int,
        default=8,
        help="copies of the smallest specs kept as the committed seed corpus",
    )
    parser.add_argument("--out", type=Path, default=settings.paths.specs_dir)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="recompute the manifest and write the diff against the previous one",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="re-extract metadata for downloaded specs without network access",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=DEFAULT_OVERRIDES,
        help="curated pricing and licence overrides",
    )
    parser.add_argument("--source", choices=("apis-guru", "local"), default="apis-guru")
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=None,
        help="directory of provider-submitted specifications",
    )
    parser.add_argument("--report", type=Path, default=None, help="path of the refresh report")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    overrides = load_override(args.overrides)
    source = build_source(args)
    source_id = source.source_id
    manifest_path = args.out / MANIFEST_NAME
    previous = read_manifest(manifest_path)

    if args.metadata_only or args.refresh:
        manifest = rebuild_manifest(args.out, overrides, source_id, previous)

        def has_outputs(entry: dict) -> bool:
            return outputs_available(entry, args.out, settings)

        chosen = select_seed_files(manifest, args.seed_files, has_outputs)
        reasons = {str(entry.get("file")): reason for entry, reason in chosen}
        seed_dir = args.out / "seed"
        previous_seed = read_manifest(seed_dir / MANIFEST_NAME)
        seed_manifest = rebuild_seed_manifest(seed_dir, overrides, source_id, previous_seed, reasons)
        annotate_seed(manifest, seed_dir, reasons)
        write_manifest(manifest_path, manifest)
        if seed_dir.exists():
            write_manifest(seed_dir / MANIFEST_NAME, seed_manifest)
        print(f"corpus: {len(manifest)} specs in {args.out} (metadata only)")
        if args.refresh:
            report_path = args.report or (settings.paths.out_dir / "logs" / REFRESH_REPORT_NAME)
            report = refresh_report(previous, manifest, manifest_path, args.overrides, source_id)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
            counts = report["counts"]
            print(
                f"refresh report: {report_path} "
                f"(+{counts['added']} -{counts['removed']} ~{counts['changed']} "
                f"v{counts['version_changed']})"
            )
        return 0

    if args.source == "apis-guru":
        listing = fetch_json(LIST_URL, args.timeout)
        entries = candidate_entries(listing)
        rng = random.Random(args.seed)
        selection = select_entries(entries, args.limit, rng)
    else:
        entries = source.list_candidates()
        selection = entries[: args.limit]

    manifest: list[dict] = []
    skipped: list[dict] = []
    for entry in selection:
        file_name = str(entry.get("file") or (slugify(entry["key"]) + ".json"))
        destination = args.out / file_name
        if destination.exists() and not args.force:
            content = destination.read_bytes()
            size = destination.stat().st_size
            status = "existing"
        else:
            try:
                content = source.fetch(entry)
                destination.write_text(content.decode("utf-8", errors="replace"), encoding="utf-8")
                size = len(content)
                status = "downloaded"
            except Exception as exc:
                skipped.append({**entry, "error": str(exc)})
                continue
        tool_id = Path(file_name).stem
        metadata = safe_listing_metadata(content, tool_id, overrides)
        manifest.append(
            manifest_entry(
                base_entry(entry),
                file_name,
                size,
                status,
                metadata,
                source_id,
                reviewed_at=licence_reviewed_at(overrides.get(tool_id)),
            )
        )

    seed_manifest: list[dict] = []
    if args.seed_files and args.out.name != "seed":
        seed_dir = args.out / "seed"
        seed_dir.mkdir(exist_ok=True)

        def has_outputs(entry: dict) -> bool:
            return outputs_available(entry, args.out, settings)

        chosen = select_seed_files(manifest, args.seed_files, has_outputs)
        reasons = {str(entry.get("file")): reason for entry, reason in chosen}
        for stale in seed_dir.glob("*.json"):
            if stale.name != MANIFEST_NAME and stale.name not in reasons:
                stale.unlink()
        for entry, reason in chosen:
            source_path = args.out / str(entry.get("file"))
            if not source_path.exists():
                continue
            shutil.copy2(source_path, seed_dir / str(entry.get("file")))
            seed_manifest.append({**entry, "seed": True, "seed_reason": reason})
        annotate_seed(manifest, seed_dir, reasons)

    write_manifest(manifest_path, manifest)
    print(f"corpus: {len(manifest)} specs in {args.out} ({len(skipped)} skipped)")
    if args.seed_files and args.out.name != "seed":
        write_manifest(args.out / "seed" / MANIFEST_NAME, seed_manifest)
        print(f"seed corpus: {len(seed_manifest)} specs in {args.out / 'seed'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
