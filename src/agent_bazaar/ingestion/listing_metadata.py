"""Deterministic extraction of commercial, access and documentation metadata.

The proposal states that a provider's terms, rate limits and pricing must be
checked before the tool is used (Proposal Section 4). OpenAPI documents carry
that information in prose, in ``info`` blocks and in the security schemes, so
this module extracts it deterministically.

Three rules matter:

* Absence of evidence never means "free". A specification that says nothing
  about pricing becomes ``unknown``, not ``free``.
* Auth requirements come from the security schemes, not from prose.
* Documentation quality is measured from the specification itself so the score
  is reproducible for every corpus member.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PricingTier = Literal["free", "freemium", "paid", "unknown"]
AccessRequirement = Literal["keyless", "api_key", "paid_key"]

TIER_ORDER: tuple[str, ...] = ("free", "freemium", "paid", "unknown")

PRICING_TIER_VALUES: tuple[str, ...] = TIER_ORDER
ACCESS_REQUIREMENT_VALUES: tuple[str, ...] = ("keyless", "api_key", "paid_key")

_FREE_PATTERNS = (
    r"free\s+(?:tier|plan|api|for\s+use|of\s+use)",
    r"\bfree\b(?![^.\n]{0,40}\b(?:trial\s+only|for\s+\d+\s+days)\b)",
    r"no\s+(?:api\s+)?key\s+required",
    r"without\s+(?:an\s+)?(?:api\s+)?key",
    r"free\s+for\s+(?:non-?commercial|personal|testing|evaluation)",
    r"open\s+data",
    r"completely\s+free",
    r"no\s+charge",
)
_PAID_PATTERNS = (
    r"paid\s+(?:plan|tier|subscription|api|request)",
    r"pricing\s+plan",
    r"subscription\s+(?:required|plan|tier)",
    r"premium\s+(?:plan|tier|request|support)",
    r"per\s+month",
    r"per\s+1[,.]?000\s+requests",
    r"\$\s?\d",
    r"€\s?\d",
    r"£\s?\d",
    r"usd\s+\d",
    r"eur\s+\d",
    r"credits?\s+required",
    r"requires?\s+(?:a\s+)?(?:paid|commercial|subscription)",
    r"price\s+plan",
)
_FREEMIUM_PATTERNS = (
    r"free\s+tier[^\n.]{0,80}paid",
    r"freemium",
    r"free\s+plan[^\n.]{0,80}(?:paid|premium)",
    r"free\s+requests?[^\n.]{0,60}paid",
    r"free\s+balance",
    r"free\s+test\s+balance",
)
_QUOTA_PATTERNS = (
    r"(\d[\d,.]*)\s*requests?\s*per\s*(second|minute|hour|day|month)",
    r"rate\s*limit(?:s|ing)?\s*(?:of|is|:)?\s*(\d[\d,.]*)",
    r"(\d[\d,.]*)\s*calls?\s*per\s*(second|minute|hour|day|month)",
    r"(\d[\d,.]*)\s*(?:free\s+)?requests?\s*per\s*day",
)
_PRICE_PATTERNS = (
    r"(\d[\d.,]*)\s*(usd|eur|gbp|jpy|inr|aed|pkr)\b",
    r"(usd|eur|gbp|jpy|inr|aed|pkr)\s*(\d[\d.,]*)",
    r"\$\s?(\d[\d.,]*)",
    r"€\s?(\d[\d.,]*)",
    r"£\s?(\d[\d.,]*)",
    r"¥\s?(\d[\d.,]*)",
    r"₹\s?(\d[\d.,]*)",
)
_PRICE_SYMBOL_CURRENCIES = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
_CREDENTIAL_PARAMETER_NAMES = {
    "api_key",
    "apikey",
    "api-key",
    "x-api-key",
    "api_secret",
    "apisecret",
    "api-secret",
    "access_token",
    "access-token",
    "auth_token",
    "auth-token",
    "authorization",
    "subscription_key",
    "subscriptionkey",
    "subscription-key",
    "app_key",
    "appkey",
    "application_key",
    "client_secret",
    "client-secret",
    "consumer_key",
    "consumer-key",
    "oauth_token",
    "oauth-token",
    "token",
    "secret",
    "wskey",
    "ws_key",
    "license",
    "licence",
    "key",
    "api-key-value",
}
_CREDENTIAL_PARAMETER_HINTS = (
    "api key",
    "apikey",
    "access token",
    "auth token",
    "bearer",
    "credential",
    "licence key",
    "license key",
    "subscription key",
    "wskey",
)
_STRONG_CREDENTIAL_NAMES = {
    "api_key",
    "apikey",
    "api-key",
    "x-api-key",
    "api_secret",
    "apisecret",
    "access_token",
    "auth_token",
    "oauth_token",
    "client_secret",
    "subscription_key",
    "app_key",
    "application_key",
    "wskey",
    "license",
    "licence",
}
_AUTH_PROSE_PATTERNS = (
    r"(?:requires?|needs?|must (?:provide|have|include))\s+(?:an?\s+)?(?:api\s+)?(?:key|token|credential)",
    r"(?:api\s+)?(?:key|token)\s+(?:is\s+)?(?:required|needed|mandatory)",
    r"you\s+(?:need|require)\s+(?:an?\s+)?(?:api\s+)?(?:key|token)",
    r"(?:register|sign up|sign-up)[^.\n]{0,40}(?:for|to get)\s+(?:an?\s+)?(?:api\s+)?key",
    r"authentication token",
    r"application key",
    r"bearer token",
)
_PLATFORM_HOSTS = (
    "googleapis.com",
    "azure.com",
    "azure-api.net",
    "amazonaws.com",
    "digitalocean.com",
    "twilio.com",
    "sendgrid.net",
    "mailgun.org",
    "stripe.com",
    "shopify.com",
    "slack.com",
    "dropboxapi.com",
    "github.com",
    "openai.com",
)
_PERIOD_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "month": 2592000,
}

_KEY_TYPE_HINTS = ("apikey", "api_key", "bearer", "oauth", "authorization", "token")


class ListingMetadata(BaseModel):
    """Commercial, access and documentation facts of one listing."""

    model_config = ConfigDict(extra="allow")

    tool_id: str
    pricing_tier: PricingTier = "unknown"
    access_requirement: AccessRequirement = "unknown"  # type: ignore[assignment]
    price_amount: float | None = None
    price_currency: str = ""
    rate_limit_policy: str = ""
    probe_budget_per_minute: int | None = None
    licence: str = ""
    terms_url: str = ""
    spec_version: str = ""
    deprecated_operations: int = 0
    operation_count: int = 0
    has_examples: bool = False
    doc_quality: float = 0.0
    doc_sub_scores: dict[str, float] = Field(default_factory=dict)
    tier_evidence: list[str] = Field(default_factory=list)
    access_evidence: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_keyless(self) -> bool:
        return self.access_requirement == "keyless"

    @property
    def tier_confirmed(self) -> bool:
        return self.pricing_tier != "unknown"


def _matches(text: str, patterns: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            hits.append(match.group(0).strip())
    return hits


def _text_blob(document: dict[str, Any]) -> str:
    parts: list[str] = []
    info = document.get("info")
    if isinstance(info, dict):
        for key in ("title", "description", "summary", "termsOfService", "x-apisguru-themes", "x-themes"):
            value = info.get(key)
            if isinstance(value, str):
                parts.append(value)
        for value in (info.get("x-themes") or []):
            if isinstance(value, str):
                parts.append(value)
    for key in ("description", "summary"):
        value = document.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def _security_schemes(document: dict[str, Any]) -> dict[str, Any]:
    schemes: dict[str, Any] = {}
    components = document.get("components")
    if isinstance(components, dict) and isinstance(components.get("securitySchemes"), dict):
        schemes.update(components["securitySchemes"])
    if isinstance(document.get("securityDefinitions"), dict):
        schemes.update(document["securityDefinitions"])
    return schemes


def _has_security(document: dict[str, Any]) -> bool:
    if _security_schemes(document):
        return True
    security = document.get("security")
    return bool(isinstance(security, list) and security)


def _auth_kind(schemes: dict[str, Any]) -> str:
    kinds: list[str] = []
    for scheme in schemes.values():
        if not isinstance(scheme, dict):
            continue
        scheme_type = str(scheme.get("type", "")).lower()
        scheme_name = str(scheme.get("name", "")).lower()
        if scheme_type in ("apikey", "http", "oauth2", "openidconnect", "mutualtls"):
            kinds.append(scheme_type)
        if scheme_type == "http" and scheme.get("scheme", "").lower() == "bearer":
            kinds.append("bearer")
        if scheme_name:
            kinds.append(scheme_name)
    return " ".join(kinds)


def _resolve_parameter(document: dict[str, Any], parameter: Any) -> dict[str, Any]:
    """Resolve a local $ref parameter into its definition."""
    if not isinstance(parameter, dict):
        return {}
    reference = parameter.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return parameter
    node: Any = document
    for part in reference[2:].split("/"):
        if not isinstance(node, dict):
            return parameter
        node = node.get(part)
    if isinstance(node, dict):
        merged = dict(node)
        merged.update({k: v for k, v in parameter.items() if k != "$ref"})
        return merged
    return parameter


def _credential_parameters(document: dict[str, Any]) -> list[str]:
    """Required parameters that carry a credential instead of data."""
    found: list[str] = []
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return found
    for operations in paths.values():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue
            parameters = list(operation.get("parameters") or [])
            body = operation.get("requestBody")
            if isinstance(body, dict):
                for content in (body.get("content") or {}).values():
                    if isinstance(content, dict) and isinstance(content.get("schema"), dict):
                        properties = content["schema"].get("properties")
                        if isinstance(properties, dict):
                            for name, prop in properties.items():
                                if not isinstance(prop, dict):
                                    continue
                                if _is_credential_parameter(name, str(prop.get("description", "")), False):
                                    found.append(f"{name} (request body)")
            for parameter in parameters:
                resolved = _resolve_parameter(document, parameter)
                if not resolved:
                    continue
                name = str(resolved.get("name", ""))
                description = str(resolved.get("description", ""))
                required = bool(resolved.get("required"))
                if _is_credential_parameter(name, description, required):
                    found.append(name or str(resolved.get("$ref", "parameter")))
    return sorted(set(found))


def _is_credential_parameter(name: str, description: str, required: bool) -> bool:
    """A credential only makes the tool keyed when it must be supplied.

    An optional ``api_key`` parameter means "you may pass a key", not "a key is
    needed", so the listing stays keyless for live probing.
    """
    lowered = name.strip().lower()
    described = any(hint in description.lower() for hint in _CREDENTIAL_PARAMETER_HINTS)
    if required and lowered in _CREDENTIAL_PARAMETER_NAMES:
        return True
    if required and described:
        return True
    if lowered in _STRONG_CREDENTIAL_NAMES and described:
        return True
    return False


def _auth_prose(text: str) -> list[str]:
    return _matches(text, _AUTH_PROSE_PATTERNS)


def _platform_host(document: dict[str, Any], servers: str) -> str:
    haystack = f"{servers} {str(document.get('host', ''))}".lower()
    for host in _PLATFORM_HOSTS:
        if host in haystack:
            return host
    return ""


def _operation_count(document: dict[str, Any]) -> tuple[int, int]:
    total = 0
    deprecated = 0
    paths = document.get("paths")
    if isinstance(paths, dict):
        for operations in paths.values():
            if not isinstance(operations, dict):
                continue
            for method, operation in operations.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}:
                    continue
                total += 1
                if isinstance(operation, dict) and operation.get("deprecated"):
                    deprecated += 1
    return total, deprecated


def _has_examples(document: dict[str, Any]) -> bool:
    text = json.dumps(document.get("paths", {}), ensure_ascii=False)
    return '"example"' in text or '"examples"' in text


def _responses_have_schemas(document: dict[str, Any]) -> bool:
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return False
    for operations in paths.values():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses")
            if not isinstance(responses, dict):
                continue
            for response in responses.values():
                if isinstance(response, dict) and response.get("content"):
                    return True
                if isinstance(response, dict) and response.get("schema"):
                    return True
    return False


def _field_description_coverage(document: dict[str, Any]) -> tuple[int, int]:
    described = 0
    total = 0
    components = document.get("components")
    schemas = components.get("schemas") if isinstance(components, dict) else None
    if not isinstance(schemas, dict):
        definitions = document.get("definitions")
        schemas = definitions if isinstance(definitions, dict) else {}
    for schema in schemas.values():
        if not isinstance(schema, dict):
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        for prop in properties.values():
            if not isinstance(prop, dict):
                continue
            total += 1
            if str(prop.get("description", "")).strip():
                described += 1
    return described, total


def _typed_io_ratio(document: dict[str, Any]) -> float:
    typed = 0
    total = 0
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return 0.0
    for operations in paths.values():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters") or []:
                if not isinstance(parameter, dict):
                    continue
                total += 1
                if parameter.get("schema") or parameter.get("type"):
                    typed += 1
            body = operation.get("requestBody")
            if isinstance(body, dict):
                total += 1
                if body.get("content") or body.get("schema"):
                    typed += 1
    if total == 0:
        return 0.0
    return round(typed / total, 4)


def _doc_quality(document: dict[str, Any], info: dict[str, Any]) -> tuple[float, dict[str, float]]:
    description = str(info.get("description", "") or "")
    described_fields, total_fields = _field_description_coverage(document)
    operation_count, deprecated = _operation_count(document)
    sub_scores: dict[str, float] = {}

    sub_scores["description"] = min(1.0, len(description.strip()) / 400)
    sub_scores["field_descriptions"] = round(described_fields / total_fields, 4) if total_fields else 0.0
    sub_scores["typed_io"] = _typed_io_ratio(document)
    sub_scores["response_schemas"] = 1.0 if _responses_have_schemas(document) else 0.0
    sub_scores["examples"] = 1.0 if _has_examples(document) else 0.0
    sub_scores["not_deprecated"] = 1.0 if deprecated == 0 else 0.0
    sub_scores["breadth"] = min(1.0, operation_count / 10) if operation_count else 0.0
    weights = {
        "description": 0.25,
        "field_descriptions": 0.2,
        "typed_io": 0.15,
        "response_schemas": 0.15,
        "examples": 0.05,
        "not_deprecated": 0.05,
        "breadth": 0.15,
    }
    quality = round(sum(sub_scores[key] * weights[key] for key in weights), 4)
    return quality, sub_scores


def _detect_tier(text: str) -> tuple[PricingTier, list[str]]:
    free_hits = _matches(text, _FREE_PATTERNS)
    paid_hits = _matches(text, _PAID_PATTERNS)
    freemium_hits = _matches(text, _FREEMIUM_PATTERNS)
    evidence: list[str] = []
    if freemium_hits:
        evidence.extend(hit[:80] for hit in freemium_hits[:2])
        return "freemium", evidence
    if free_hits and paid_hits:
        evidence.extend(hit[:80] for hit in free_hits[:1] + paid_hits[:1])
        return "freemium", evidence
    if paid_hits:
        evidence.extend(hit[:80] for hit in paid_hits[:2])
        return "paid", evidence
    if free_hits:
        evidence.extend(hit[:80] for hit in free_hits[:2])
        return "free", evidence
    return "unknown", ["no pricing statement found"]


def _detect_price(text: str) -> tuple[float | None, str]:
    for pattern in _PRICE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        groups = [group for group in match.groups() if group]
        if len(groups) == 2:
            number, currency = groups
        else:
            number, currency = groups[0], ""
        if currency.lower() in {"usd", "eur", "gbp", "jpy", "inr", "aed", "pkr"}:
            try:
                return float(number.replace(",", "")), currency.upper()
            except ValueError:
                return None, ""
        try:
            amount = float(number.replace(",", ""))
        except ValueError:
            continue
        symbol = match.group(0).strip()[:1]
        return amount, _PRICE_SYMBOL_CURRENCIES.get(symbol, "")
    return None, ""


def _detect_quota(text: str) -> tuple[str, int | None]:
    for pattern in _QUOTA_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        groups = match.groups()
        number_text = groups[0]
        period = next((group for group in groups[1:] if group), None)
        try:
            value = float(str(number_text).replace(",", ""))
        except ValueError:
            continue
        policy = f"{int(value) if value.is_integer() else value} requests per {period or 'day'}"
        per_minute: int | None = None
        if period:
            seconds = _PERIOD_SECONDS.get(period.lower())
            if seconds:
                per_minute = int(round(value * 60 / seconds))
                per_minute = max(1, per_minute)
        return policy, per_minute
    return "", None


def _licence_of(info: dict[str, Any]) -> tuple[str, str]:
    licence = info.get("license")
    licence_url = ""
    if isinstance(licence, dict):
        name = str(licence.get("name", "")).strip()
        licence_url = str(licence.get("url", "")).strip()
        return name, licence_url
    if isinstance(licence, str):
        return licence.strip(), ""
    return "", ""


def _terms_url_of(info: dict[str, Any], licence_url: str) -> str:
    terms = str(info.get("termsOfService", "") or "").strip()
    return terms or licence_url


def extract_listing_metadata(document: dict[str, Any], tool_id: str = "") -> ListingMetadata:
    """Extract commercial, access and documentation facts from an OpenAPI document."""
    info = document.get("info") if isinstance(document.get("info"), dict) else {}
    text = _text_blob(document)
    schemes = _security_schemes(document)
    kind = _auth_kind(schemes)
    credentials = _credential_parameters(document)
    auth_prose = _auth_prose(text)

    tier, tier_evidence = _detect_tier(text)
    access_evidence: list[str] = []
    if schemes:
        access_evidence.append(f"security schemes: {', '.join(sorted(schemes))}")
    elif _has_security(document):
        access_evidence.append("global security requirement declared")
    if credentials:
        access_evidence.append(f"credential parameters: {', '.join(credentials[:5])}")
    if auth_prose:
        access_evidence.append(f"authentication stated in prose: {auth_prose[0][:60]}")

    platform = _platform_host(document, _server_urls(document))
    if platform:
        access_evidence.append(f"platform API on {platform}")

    paid_tier = tier in ("paid", "freemium")
    if kind and any(hint in kind for hint in _KEY_TYPE_HINTS):
        access: AccessRequirement = "paid_key" if paid_tier else "api_key"
    elif credentials or auth_prose:
        access = "paid_key" if paid_tier and (credentials or auth_prose) else "api_key"
    elif schemes or _has_security(document):
        access = "api_key"
    elif platform:
        access = "api_key"
    else:
        access = "keyless"
        access_evidence.append("no security scheme, credential parameter or platform rule matched")

    price_amount, price_currency = _detect_price(text)
    rate_limit_policy, probe_budget = _detect_quota(text)
    licence, licence_url = _licence_of(info)
    operation_count, deprecated = _operation_count(document)
    quality, sub_scores = _doc_quality(document, info)

    return ListingMetadata(
        tool_id=tool_id,
        pricing_tier=tier,
        access_requirement=access,
        price_amount=price_amount,
        price_currency=price_currency,
        rate_limit_policy=rate_limit_policy,
        probe_budget_per_minute=probe_budget,
        licence=licence,
        terms_url=_terms_url_of(info, licence_url),
        spec_version=str(info.get("version", "") or ""),
        deprecated_operations=deprecated,
        operation_count=operation_count,
        has_examples=sub_scores.get("examples", 0.0) > 0,
        doc_quality=quality,
        doc_sub_scores=sub_scores,
        tier_evidence=tier_evidence,
        access_evidence=access_evidence,
        provenance={
            "method": "deterministic_rules",
            "source": "openapi_document",
        },
    )


def _server_urls(document: dict[str, Any]) -> str:
    parts: list[str] = []
    for server in document.get("servers") or []:
        if isinstance(server, dict) and server.get("url"):
            parts.append(str(server["url"]))
    base_path = document.get("basePath")
    if isinstance(base_path, str):
        parts.append(base_path)
    return " ".join(parts)


def load_override(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load curated overrides that win over extracted values."""
    source = Path(path)
    if not source.exists():
        return {}
    payload = yaml_load(source)
    if not isinstance(payload, dict):
        return {}
    entries = payload.get("tools", payload)
    return {str(key): dict(value) for key, value in entries.items()} if isinstance(entries, dict) else {}


def yaml_load(path: Path) -> Any:
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - PyYAML is a dependency
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def apply_override(metadata: ListingMetadata, override: dict[str, Any]) -> ListingMetadata:
    """Apply a curated override on top of the extracted metadata."""
    if not override:
        return metadata
    updates: dict[str, Any] = {}
    for field in (
        "pricing_tier",
        "access_requirement",
        "price_amount",
        "price_currency",
        "rate_limit_policy",
        "probe_budget_per_minute",
        "licence",
        "terms_url",
    ):
        if field in override and override[field] is not None:
            updates[field] = override[field]
    provenance = dict(metadata.provenance)
    provenance["override"] = {
        "reviewer": override.get("reviewer", ""),
        "checked_at": override.get("checked_at", ""),
        "note": override.get("note", ""),
    }
    updates["provenance"] = provenance
    return metadata.model_copy(update=updates)
