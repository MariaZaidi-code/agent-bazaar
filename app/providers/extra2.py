from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid as uuidlib
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree

from app.providers.base import BaseProvider
from app.providers.http_base import HTTPProvider

DISPOSABLE_DOMAINS = {
    "10minutemail.com",
    "guerrillamail.com",
    "mailinator.com",
    "tempmail.com",
    "throwawaymail.com",
    "yopmail.com",
}

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class WikidataProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "format": "json",
                "limit": 5,
            },
        )
        results = payload.get("search") or []
        return {
            "results": [
                {
                    "id": item.get("id", ""),
                    "label": item.get("label", ""),
                    "description": item.get("description", ""),
                    "url": item.get("concepturi", ""),
                }
                for item in results
                if isinstance(item, dict)
            ]
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "results": [
                {
                    "id": "Q42",
                    "label": "Douglas Adams",
                    "description": "English writer and humorist",
                    "url": "https://www.wikidata.org/wiki/Q42",
                }
            ]
        }


class WikivoyageProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        place = str(params.get("place", "")).strip()
        if not place:
            raise ValueError("place is required")
        payload = await self.get_json(
            f"https://en.wikivoyage.org/api/rest_v1/page/summary/{quote(place, safe='')}"
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid Wikivoyage response")
        return {
            "guide": {
                "title": payload.get("title", place),
                "extract": payload.get("extract", ""),
                "url": (payload.get("content_urls") or {}).get("desktop", {}).get("page", ""),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        place = str(params.get("place", "Paris")).strip() or "Paris"
        return {
            "guide": {
                "title": place.title(),
                "extract": f"An offline travel guide summary for {place.title()}.",
                "url": "https://en.wikivoyage.org/",
            }
        }


class YahooFinanceProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        symbol = str(params.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        payload = await self.get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}",
            params={"range": "1d", "interval": "1d"},
        )
        results = ((payload.get("chart") or {}).get("result") or []) if isinstance(payload, dict) else []
        if not results:
            raise ValueError("no quote returned")
        meta = results[0].get("meta") or {}
        return {
            "quote": {
                "symbol": meta.get("symbol", symbol),
                "price": meta.get("regularMarketPrice"),
                "currency": meta.get("currency", ""),
                "exchange": meta.get("exchangeName", ""),
                "previous_close": meta.get("chartPreviousClose", meta.get("previousClose")),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        symbol = str(params.get("symbol", "AAPL")).strip().upper() or "AAPL"
        return {
            "quote": {
                "symbol": symbol,
                "price": 190.25,
                "currency": "USD",
                "exchange": "Offline Exchange",
                "previous_close": 188.1,
            }
        }


class RssFeedProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        feed_url = str(params.get("feed_url", "")).strip() or "https://feeds.bbci.co.uk/news/rss.xml"
        if not feed_url.startswith(("http://", "https://")):
            raise ValueError("feed_url must start with http:// or https://")
        text = await self.get_text(feed_url)
        root = ElementTree.fromstring(text)
        items = []
        for node in root.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag not in {"item", "entry"}:
                continue
            values = {child.tag.rsplit("}", 1)[-1]: (child.text or "") for child in node}
            link = values.get("link", "")
            if not link:
                link_node = node.find("{http://www.w3.org/2005/Atom}link")
                link = link_node.get("href", "") if link_node is not None else ""
            items.append(
                {
                    "title": values.get("title", ""),
                    "link": link,
                    "published": values.get("pubDate", values.get("published", "")),
                    "summary": values.get("description", values.get("summary", "")),
                }
            )
            if len(items) >= 10:
                break
        return {"items": items}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "items": [
                {
                    "title": "Offline headline",
                    "link": "https://example.com/offline",
                    "published": "2026-10-01T00:00:00Z",
                    "summary": "A deterministic offline news item.",
                }
            ]
        }


class DbpediaProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        title = str(params.get("title", "")).strip()
        if not title:
            raise ValueError("title is required")
        payload = await self.get_json(
            f"https://dbpedia.org/data/{quote(title.replace(' ', '_'), safe='')}.json"
        )
        if not isinstance(payload, dict) or not payload:
            raise ValueError("invalid DBpedia response")
        resource_url = next(iter(payload))
        data = payload[resource_url] or {}
        abstracts = data.get("http://dbpedia.org/ontology/abstract") or []
        abstract = ""
        for entry in abstracts:
            if isinstance(entry, dict) and entry.get("lang") == "en":
                abstract = entry.get("value", "")
                break
        return {
            "summary": {
                "title": title,
                "abstract": abstract,
                "url": resource_url.replace("dbpedia.org/data/", "dbpedia.org/page/"),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        title = str(params.get("title", "Ada Lovelace")).strip() or "Ada Lovelace"
        return {
            "summary": {
                "title": title,
                "abstract": f"An offline DBpedia abstract for {title}.",
                "url": "https://dbpedia.org/page/Ada_Lovelace",
            }
        }


class IssLocationProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://api.open-notify.org/iss-now.json")
        position = (payload.get("iss_position") or {}) if isinstance(payload, dict) else {}
        return {
            "position": {
                "latitude": float(position.get("latitude", 0)),
                "longitude": float(position.get("longitude", 0)),
                "timestamp": int(payload.get("timestamp", 0)),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"position": {"latitude": 0.0, "longitude": 0.0, "timestamp": 1_790_000_000}}


class OpenMeteoAirProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("latitude") is None or params.get("longitude") is None:
            raise ValueError("latitude and longitude are required")
        latitude = float(params["latitude"])
        longitude = float(params["longitude"])
        payload = await self.get_json(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "pm2_5,pm10,ozone,european_aqi",
            },
        )
        current = payload.get("current") or {}
        return {
            "air_quality": {
                "pm2_5": current.get("pm2_5"),
                "pm10": current.get("pm10"),
                "ozone": current.get("ozone"),
                "european_aqi": current.get("european_aqi"),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "air_quality": {"pm2_5": 8.5, "pm10": 15.0, "ozone": 42.0, "european_aqi": 22}
        }


class OpenMeteoMarineProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("latitude") is None or params.get("longitude") is None:
            raise ValueError("latitude and longitude are required")
        latitude = float(params["latitude"])
        longitude = float(params["longitude"])
        payload = await self.get_json(
            "https://marine-api.open-meteo.com/v1/marine",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "wave_height,wave_direction,wave_period",
            },
        )
        current = payload.get("current") or {}
        return {
            "marine": {
                "wave_height": current.get("wave_height"),
                "wave_direction": current.get("wave_direction"),
                "wave_period": current.get("wave_period"),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"marine": {"wave_height": 1.2, "wave_direction": 180, "wave_period": 6.5}}


class EmailValidateProvider(BaseProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        email = str(params.get("email", "")).strip()
        if not email:
            raise ValueError("email is required")
        domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
        syntax_ok = bool(EMAIL_PATTERN.match(email))
        disposable = domain in DISPOSABLE_DOMAINS
        if not syntax_ok:
            reason = "The address does not look like a valid email."
        elif disposable:
            reason = "The domain is a known disposable email provider."
        else:
            reason = "The address looks valid."
        return {
            "validation": {
                "email": email,
                "valid": syntax_ok and not disposable,
                "disposable": disposable,
                "reason": reason,
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self.execute(params)


class PasswordToolsProvider(BaseProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        password = str(params.get("password", ""))
        if not password:
            raise ValueError("password is required")
        classes = sum(
            bool(pattern.search(password))
            for pattern in (
                re.compile(r"[a-z]"),
                re.compile(r"[A-Z]"),
                re.compile(r"\d"),
                re.compile(r"[^A-Za-z0-9]"),
            )
        )
        score = min(4, len(password) // 4 + classes)
        label = ["very weak", "weak", "fair", "strong", "very strong"][score]
        suggestions = []
        if len(password) < 12:
            suggestions.append("Use at least 12 characters.")
        if classes < 3:
            suggestions.append("Mix upper case, lower case, numbers and symbols.")
        if password.lower() in {"password", "letmein", "qwerty", "123456"}:
            suggestions.append("Avoid common passwords.")
        return {
            "password": {
                "score": score,
                "label": label,
                "suggestions": suggestions,
                "sha256": hashlib.sha256(password.encode("utf-8")).hexdigest(),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self.execute(params)


class UuidProvider(BaseProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            count = int(params.get("count", 1))
        except (TypeError, ValueError):
            count = 1
        count = max(1, min(count, 20))
        return {"uuids": [str(uuidlib.uuid4()) for _ in range(count)]}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"uuids": ["00000000-0000-4000-8000-000000000000"]}


class DataTransformProvider(BaseProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        raw = params.get("data")
        if raw is None or str(raw).strip() == "":
            raise ValueError("data is required")
        text = str(raw)
        fmt = str(params.get("format", "")).strip().lower()
        if not fmt:
            fmt = "csv" if "," in text.splitlines()[0] and not text.lstrip().startswith("[") else "json"
        if fmt == "csv":
            rows = [dict(row) for row in csv.DictReader(io.StringIO(text))]
        elif fmt == "json":
            parsed = json.loads(text)
            rows = parsed if isinstance(parsed, list) else [parsed]
            if not all(isinstance(row, dict) for row in rows):
                raise ValueError("JSON data must be an object or a list of objects")
        else:
            raise ValueError("format must be json or csv")
        rows = rows[:100]
        columns = list(rows[0].keys()) if rows else []
        return {"table": {"rows": rows, "columns": columns, "row_count": len(rows), "format": fmt}}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "table": {
                "rows": [{"name": "offline", "value": "1"}],
                "columns": ["name", "value"],
                "row_count": 1,
                "format": "json",
            }
        }


class IpifyProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://api.ipify.org", params={"format": "json"})
        return {"ip": str(payload.get("ip", "")) if isinstance(payload, dict) else ""}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"ip": "203.0.113.10"}


class ZenQuotesProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://zenquotes.io/api/random")
        item = payload[0] if isinstance(payload, list) and payload else {}
        if not isinstance(item, dict):
            raise ValueError("invalid ZenQuotes response")
        return {"quote": {"text": item.get("q", ""), "author": item.get("a", "")}}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "quote": {
                "text": "Simplicity is the soul of efficiency.",
                "author": "Austin Freeman",
            }
        }


class LaunchLibraryProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = int(params.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))
        payload = await self.get_json(
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/",
            params={"limit": limit, "mode": "list"},
        )
        results = payload.get("results") or [] if isinstance(payload, dict) else []
        launches = []
        for item in results:
            if not isinstance(item, dict):
                continue
            status = item.get("status") or {}
            provider = item.get("launch_service_provider") or {}
            launches.append(
                {
                    "name": item.get("name", ""),
                    "status": status.get("abbrev", status.get("name", "")),
                    "net": item.get("net", ""),
                    "provider": provider.get("name", ""),
                }
            )
        return {"launches": launches}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "launches": [
                {
                    "name": "Offline Demo Launch",
                    "status": "Go",
                    "net": "2026-11-01T12:00:00Z",
                    "provider": "Agent Bazaar Space",
                }
            ]
        }


class WorldBankProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        country = str(params.get("country", "")).strip().upper()
        if not country:
            raise ValueError("country is required")
        indicator = str(params.get("indicator", "SP.POP.TOTL")).strip() or "SP.POP.TOTL"
        payload = await self.get_json(
            f"https://api.worldbank.org/v2/country/{quote(country, safe='')}/indicator/"
            f"{quote(indicator, safe='')}",
            params={"format": "json", "per_page": 5},
        )
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        values = [
            {"year": row.get("date", ""), "value": row.get("value")}
            for row in rows or []
            if isinstance(row, dict)
        ]
        return {
            "indicator_data": {
                "country": country,
                "indicator": indicator,
                "values": values,
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "indicator_data": {
                "country": str(params.get("country", "PAK")).upper(),
                "indicator": str(params.get("indicator", "SP.POP.TOTL")),
                "values": [{"year": "2025", "value": 250_000_000}],
            }
        }


class DictionaryProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        word = str(params.get("word", "")).strip()
        if not word:
            raise ValueError("word is required")
        payload = await self.get_json(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word, safe='')}"
        )
        entries = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            for meaning in item.get("meanings") or []:
                definitions = meaning.get("definitions") or []
                definition = definitions[0] if definitions else {}
                entries.append(
                    {
                        "word": item.get("word", word),
                        "part_of_speech": meaning.get("partOfSpeech", ""),
                        "definition": definition.get("definition", ""),
                        "example": definition.get("example", ""),
                    }
                )
        return {"entries": entries[:5]}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        word = str(params.get("word", "bazaar")).strip() or "bazaar"
        return {
            "entries": [
                {
                    "word": word,
                    "part_of_speech": "noun",
                    "definition": "A market in a Middle Eastern or Asian country.",
                    "example": "The agent browsed the bazaar for tools.",
                }
            ]
        }


class CoinCapProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        asset = str(params.get("asset", "")).strip().lower()
        if not asset:
            raise ValueError("asset is required")
        payload = await self.get_json(f"https://api.coincap.io/v2/assets/{quote(asset, safe='')}")
        data = payload.get("data") or {} if isinstance(payload, dict) else {}
        return {
            "asset": {
                "id": data.get("id", asset),
                "price_usd": float(data.get("priceUsd", 0) or 0),
                "change_24h": float(data.get("changePercent24Hr", 0) or 0),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        asset = str(params.get("asset", "bitcoin")).strip().lower() or "bitcoin"
        return {"asset": {"id": asset, "price_usd": 50_000.0, "change_24h": 1.5}}
