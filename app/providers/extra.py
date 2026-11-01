from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.providers.http_base import HTTPProvider


class OpenAlexProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json("https://api.openalex.org/works", params={"search": query, "per_page": 5})
        if not isinstance(payload, dict):
            raise ValueError("invalid OpenAlex response")
        works = payload.get("results") or []
        items = []
        for w in works[:5]:
            if not isinstance(w, dict):
                continue
            items.append(
                {"title": w.get("title", ""), "year": w.get("publication_year"), "cited_by": w.get("cited_by_count", 0)}
            )
        return {"works": items}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"works": [{"title": "Offline OpenAlex work", "year": 2024, "cited_by": 10}]}


class SemanticScholarProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "limit": 5, "fields": "title,year,citationCount"},
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid Semantic Scholar response")
        papers = payload.get("data") or []
        items = [
            {"title": p.get("title", ""), "year": p.get("year"), "citations": p.get("citationCount", 0)}
            for p in papers
            if isinstance(p, dict)
        ]
        return {"papers": items}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"papers": [{"title": "Offline paper", "year": 2024, "citations": 5}]}


class GitHubProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json("https://api.github.com/search/repositories", params={"q": query, "per_page": 5})
        if not isinstance(payload, dict):
            raise ValueError("invalid GitHub response")
        items = payload.get("items") or []
        repos = [
            {
                "name": r.get("full_name", ""),
                "stars": r.get("stargazers_count", 0),
                "description": (r.get("description") or "")[:120],
            }
            for r in items
            if isinstance(r, dict)
        ]
        return {"repositories": repos}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"repositories": [{"name": "offline/repo", "stars": 100, "description": "offline"}]}


class StackExchangeProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json(
            "https://api.stackexchange.com/2.3/search",
            params={"intitle": query, "site": "stackoverflow", "pagesize": 5},
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid StackExchange response")
        items = payload.get("items") or []
        questions = [
            {"title": q.get("title", ""), "score": q.get("score", 0), "link": q.get("link", "")}
            for q in items
            if isinstance(q, dict)
        ]
        return {"questions": questions}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"questions": [{"title": "Offline question", "score": 10, "link": ""}]}


class OpenFoodFactsProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        barcode = str(params.get("barcode", "")).strip()
        if not barcode:
            raise ValueError("barcode is required")
        payload = await self.get_json(f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json")
        if not isinstance(payload, dict):
            raise ValueError("invalid Open Food Facts response")
        product = payload.get("product") or {}
        return {
            "product": {
                "name": product.get("product_name", ""),
                "brand": product.get("brands", ""),
                "categories": product.get("categories", ""),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"product": {"name": "Offline product", "brand": "Brand", "categories": "Food"}}


class LanguageToolProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", "")).strip()
        if not text:
            raise ValueError("text is required")
        payload = await self.get_json(
            "https://api.languagetool.org/v2/check", params={"text": text, "language": "en-US"}
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid LanguageTool response")
        matches = payload.get("matches") or []
        issues = [
            {"message": m.get("message", ""), "offset": m.get("offset", 0)} for m in matches if isinstance(m, dict)
        ]
        return {"issues": issues, "language": payload.get("language", {}).get("name", "")}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"issues": [], "language": "English (US)"}


class QRCodeProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", "")).strip()
        if not text:
            raise ValueError("text is required")
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={text}"
        return {"qr_url": url, "text": text}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", "offline")).strip() or "offline"
        return {"qr_url": "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=offline", "text": text}


class IpApiProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        ip = str(params.get("ip", "")).strip()
        url = f"http://ip-api.com/json/{ip}" if ip else "http://ip-api.com/json/"
        payload = await self.get_json(url)
        if not isinstance(payload, dict):
            raise ValueError("invalid IP API response")
        return {
            "location": {
                "country": payload.get("country", ""),
                "region": payload.get("regionName", ""),
                "city": payload.get("city", ""),
                "lat": payload.get("lat"),
                "lon": payload.get("lon"),
                "timezone": payload.get("timezone", ""),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "location": {
                "country": "Pakistan",
                "region": "Punjab",
                "city": "Lahore",
                "lat": 31.5,
                "lon": 74.3,
                "timezone": "Asia/Karachi",
            }
        }


class OpenElevationProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        lat = params.get("latitude")
        lon = params.get("longitude")
        if lat is None or lon is None:
            raise ValueError("latitude and longitude are required")
        payload = await self.get_json(
            "https://api.open-elevation.com/api/v1/lookup", params={"locations": f"{lat},{lon}"}
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid elevation response")
        results = payload.get("results") or []
        elev = results[0].get("elevation") if results and isinstance(results[0], dict) else None
        return {"elevation": elev, "latitude": lat, "longitude": lon}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "elevation": 217.0,
            "latitude": params.get("latitude", 31.5),
            "longitude": params.get("longitude", 74.3),
        }


class CoinDeskProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://api.coindesk.com/v1/bpi/currentprice.json")
        if not isinstance(payload, dict):
            raise ValueError("invalid CoinDesk response")
        bpi = payload.get("bpi") or {}
        usd = bpi.get("USD") or {}
        return {
            "bitcoin": {
                "currency": "USD",
                "rate": usd.get("rate", ""),
                "rate_float": usd.get("rate_float"),
                "updated": (payload.get("time") or {}).get("updated", ""),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"bitcoin": {"currency": "USD", "rate": "67,000.00", "rate_float": 67000.0, "updated": "Oct 30, 2026"}}


class MetalsProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://api.metals.live/v1/spot")
        if not isinstance(payload, list):
            raise ValueError("invalid metals response")
        spot = {}
        for item in payload:
            if isinstance(item, dict):
                spot.update(item)
        return {"metals": spot}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"metals": {"gold": 2400.0, "silver": 29.0}}


class RedditProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        subreddit = str(params.get("subreddit", "python")).strip() or "python"
        payload = await self.get_json(
            f"https://www.reddit.com/r/{subreddit}/hot.json",
            params={"limit": 5},
            headers={"Accept": "application/json"},
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid Reddit response")
        children = ((payload.get("data") or {}).get("children")) or []
        posts = []
        for c in children[:5]:
            d = c.get("data") if isinstance(c, dict) else None
            if not isinstance(d, dict):
                continue
            posts.append({"title": d.get("title", ""), "score": d.get("score", 0), "url": d.get("url", "")})
        return {"posts": posts}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"posts": [{"title": "Offline post", "score": 100, "url": ""}]}


class OpenAQProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        city = str(params.get("city", "")).strip()
        payload = await self.get_json(
            "https://api.openaq.org/v2/locations", params={"city": city, "limit": 5} if city else {"limit": 5}
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid OpenAQ response")
        results = payload.get("results") or []
        locs = [
            {"name": r.get("name", ""), "city": r.get("city", ""), "country": r.get("country", "")}
            for r in results
            if isinstance(r, dict)
        ]
        return {"locations": locs}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"locations": [{"name": "Offline station", "city": "Lahore", "country": "PK"}]}


class PubChemProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("compound", "")).strip()
        if not name:
            raise ValueError("compound is required")
        payload = await self.get_json(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/JSON")
        if not isinstance(payload, dict):
            raise ValueError("invalid PubChem response")
        props = (payload.get("PC_Compounds") or [{}])[0].get("props") or []
        return {"compound": {"name": name, "properties_count": len(props)}}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "compound": {
                "name": params.get("compound", "water"),
                "properties_count": 10,
            }
        }


class OpenFDAProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        drug = str(params.get("drug", "")).strip()
        if not drug:
            raise ValueError("drug is required")
        payload = await self.get_json(
            "https://api.fda.gov/drug/label.json", params={"search": f"openfda.brand_name:{drug}", "limit": 3}
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid OpenFDA response")
        results = payload.get("results") or []
        labels = [
            {
                "brand": (r.get("openfda") or {}).get("brand_name", [""])[0]
                if isinstance(r.get("openfda"), dict)
                else "",
                "purpose": (r.get("purpose") or [""])[0] if isinstance(r.get("purpose"), list) else "",
            }
            for r in results
            if isinstance(r, dict)
        ]
        return {"labels": labels}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"labels": [{"brand": "OfflineMed", "purpose": "offline"}]}


class NasaEonetProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        category = str(params.get("category", "")).strip()
        try:
            limit = int(params.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))
        api_params: dict[str, Any] = {"limit": limit}
        if category:
            api_params["category"] = category
        payload = await self.get_json("https://eonet.gsfc.nasa.gov/api/v3/events", params=api_params)
        if not isinstance(payload, dict):
            raise ValueError("invalid EONET response")
        events = payload.get("events") or []
        items = []
        for event in events[:limit]:
            if not isinstance(event, dict):
                continue
            categories = event.get("categories") or []
            category_name = ""
            if categories and isinstance(categories[0], dict):
                category_name = categories[0].get("title", "")
            geometry = event.get("geometry") or []
            date = ""
            if geometry and isinstance(geometry[-1], dict):
                date = geometry[-1].get("date", "")
            items.append(
                {
                    "title": event.get("title", ""),
                    "category": category_name,
                    "date": date,
                    "link": event.get("link", ""),
                }
            )
        return {"events": items}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "events": [
                {
                    "title": "Offline wildfire event",
                    "category": "wildfires",
                    "date": "2026-10-01T00:00:00Z",
                    "link": "https://eonet.gsfc.nasa.gov/",
                }
            ]
        }


class NoaaAlertsProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        state = str(params.get("state", "CA")).strip().upper() or "CA"
        payload = await self.get_json("https://api.weather.gov/alerts/active", params={"area": state})
        if not isinstance(payload, dict):
            raise ValueError("invalid NOAA alerts response")
        features = payload.get("features") or []
        items = []
        for feature in features[:15]:
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            items.append(
                {
                    "event": props.get("event", ""),
                    "headline": props.get("headline", ""),
                    "severity": props.get("severity", ""),
                    "area": props.get("areaDesc", ""),
                    "expires": props.get("expires", ""),
                }
            )
        return {"alerts": items}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "alerts": [
                {
                    "event": "Heat Advisory",
                    "headline": "Heat Advisory in effect",
                    "severity": "Moderate",
                    "area": "California",
                    "expires": "2026-10-02T00:00:00-07:00",
                }
            ]
        }


class NoaaTidesProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        station = str(params.get("station", "8454000")).strip() or "8454000"
        date_value = str(params.get("date", "")).strip()
        if not date_value:
            date_value = datetime.now(UTC).date().isoformat()
        compact = date_value.replace("-", "")
        payload = await self.get_json(
            "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
            params={
                "product": "predictions",
                "application": "AgentBazaar",
                "begin_date": compact,
                "end_date": compact,
                "datum": "MLLW",
                "station": station,
                "time_zone": "lst_ldt",
                "units": "english",
                "interval": "hilo",
                "format": "json",
            },
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid NOAA tides response")
        predictions = payload.get("predictions") or []
        items = []
        for pred in predictions:
            if not isinstance(pred, dict):
                continue
            items.append(
                {
                    "time": pred.get("t", ""),
                    "height": pred.get("v", ""),
                    "type": pred.get("type", ""),
                }
            )
        return {"tides": items}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "tides": [
                {"time": "2026-10-30 06:12", "height": "3.24", "type": "H"},
                {"time": "2026-10-30 12:45", "height": "0.71", "type": "L"},
            ]
        }


class ExchangerateProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        base = str(params.get("base", "USD")).strip().upper() or "USD"
        target = str(params.get("target", "EUR")).strip().upper() or "EUR"
        payload = await self.get_json(f"https://open.er-api.com/v6/latest/{base}")
        if not isinstance(payload, dict):
            raise ValueError("invalid exchange rate response")
        rates = payload.get("rates") or {}
        if target not in rates:
            raise ValueError(f"no rate for {target}")
        return {
            "rate": {
                "base": base,
                "target": target,
                "rate": float(rates[target]),
                "date": str(payload.get("time_last_update_utc", "")),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        base = str(params.get("base", "USD")).strip().upper() or "USD"
        target = str(params.get("target", "EUR")).strip().upper() or "EUR"
        return {
            "rate": {
                "base": base,
                "target": target,
                "rate": 0.92,
                "date": "2026-10-20T00:00:00+00:00",
            }
        }


class LibreTranslateProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", "")).strip()
        if not text:
            raise ValueError("text is required")
        source = str(params.get("source", "auto")).strip() or "auto"
        target = str(params.get("target", "es")).strip() or "es"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=True) as client:
            response = await client.post(
                "https://libretranslate.com/translate",
                json={"q": text, "source": source, "target": target, "format": "text"},
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("invalid LibreTranslate response")
        translated = payload.get("translatedText", "")
        return {
            "translation": {
                "text": text,
                "source": source,
                "target": target,
                "translated": translated,
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", "")).strip()
        if not text:
            raise ValueError("text is required")
        source = str(params.get("source", "en")).strip() or "en"
        target = str(params.get("target", "es")).strip() or "es"
        return {
            "translation": {
                "text": text,
                "source": source,
                "target": target,
                "translated": f"[{target}] {text}",
            }
        }


class MastodonProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = int(params.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))
        payload = await self.get_json("https://mastodon.social/api/v1/timelines/public", params={"limit": limit})
        if not isinstance(payload, list):
            raise ValueError("invalid Mastodon response")
        items = []
        for post in payload[:limit]:
            if not isinstance(post, dict):
                continue
            account = post.get("account") or {}
            content = str(post.get("content", ""))
            items.append(
                {
                    "content": content[:200],
                    "account": account.get("acct", "") if isinstance(account, dict) else "",
                    "created_at": post.get("created_at", ""),
                    "url": post.get("url", ""),
                }
            )
        return {"posts": items}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "posts": [
                {
                    "content": "Offline post from the fediverse",
                    "account": "agentbazaar",
                    "created_at": "2026-10-01T12:00:00.000Z",
                    "url": "https://mastodon.social/@agentbazaar/1",
                }
            ]
        }


class TheSportsDBProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        sport = str(params.get("sport", "Soccer")).strip() or "Soccer"
        date_value = str(params.get("date", "")).strip()
        if date_value:
            payload = await self.get_json(
                "https://www.thesportsdb.com/api/v1/json/3/eventsday.php",
                params={"d": date_value, "s": sport},
            )
        else:
            payload = await self.get_json(
                "https://www.thesportsdb.com/api/v1/json/3/searchevents.php",
                params={"e": sport},
            )
        if not isinstance(payload, dict):
            raise ValueError("invalid TheSportsDB response")
        events = payload.get("events") or payload.get("event") or []
        if not isinstance(events, list):
            events = []
        items = []
        for event in events[:15]:
            if not isinstance(event, dict):
                continue
            items.append(
                {
                    "event": event.get("strEvent", ""),
                    "sport": event.get("strSport", sport),
                    "league": event.get("strLeague", ""),
                    "date": event.get("dateEvent", ""),
                    "home": event.get("strHomeTeam", ""),
                    "away": event.get("strAwayTeam", ""),
                }
            )
        return {"events": items}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "events": [
                {
                    "event": "Offline Derby",
                    "sport": "Soccer",
                    "league": "Premier League",
                    "date": "2026-10-30",
                    "home": "Team A",
                    "away": "Team B",
                }
            ]
        }


class UpcItemDbProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        upc = str(params.get("barcode") or params.get("upc") or "").strip()
        if not upc:
            raise ValueError("barcode is required")
        payload = await self.get_json("https://api.upcitemdb.com/prod/trial/lookup", params={"upc": upc})
        if not isinstance(payload, dict):
            raise ValueError("invalid UPC Item DB response")
        items = payload.get("items") or []
        if not items or not isinstance(items[0], dict):
            raise ValueError(f"no product found for {upc}")
        item = items[0]
        return {
            "product": {
                "title": item.get("title", ""),
                "brand": item.get("brand", ""),
                "category": item.get("category", ""),
                "upc": item.get("upc", upc),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        upc = str(params.get("barcode") or params.get("upc") or "012345678905").strip()
        return {
            "product": {
                "title": "Offline product",
                "brand": "Brand",
                "category": "Grocery",
                "upc": upc,
            }
        }


class IsGdProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        url = str(params.get("url", "")).strip()
        if not url:
            raise ValueError("url is required")
        payload = await self.get_json("https://is.gd/create.php", params={"format": "json", "url": url})
        if not isinstance(payload, dict):
            raise ValueError("invalid is.gd response")
        short = payload.get("shorturl") or payload.get("shortUrl") or ""
        if not short:
            raise ValueError("is.gd did not return a short url")
        return {"short_url": {"original": url, "short": short}}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        url = str(params.get("url", "https://example.com")).strip() or "https://example.com"
        return {"short_url": {"original": url, "short": "https://is.gd/example"}}


class NasaMarsProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        rover = str(params.get("rover", "curiosity")).strip().lower() or "curiosity"
        try:
            sol = int(params.get("sol", 1000))
        except (TypeError, ValueError):
            sol = 1000
        payload = await self.get_json(
            f"https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/photos",
            params={"sol": sol, "api_key": "DEMO_KEY"},
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid Mars Rover response")
        photos = payload.get("photos") or []
        items = []
        for photo in photos[:8]:
            if not isinstance(photo, dict):
                continue
            camera = photo.get("camera") or {}
            rover_info = photo.get("rover") or {}
            items.append(
                {
                    "img_src": photo.get("img_src", ""),
                    "earth_date": photo.get("earth_date", ""),
                    "rover": rover_info.get("name", rover) if isinstance(rover_info, dict) else rover,
                    "camera": camera.get("name", "") if isinstance(camera, dict) else "",
                }
            )
        return {"photos": items}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        rover = str(params.get("rover", "curiosity")).strip() or "curiosity"
        return {
            "photos": [
                {
                    "img_src": "https://mars.nasa.gov/msl-raw-images/...jpg",
                    "earth_date": "2026-10-01",
                    "rover": rover,
                    "camera": "FHAZ",
                }
            ]
        }
