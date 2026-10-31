from __future__ import annotations

from typing import Any

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
        return {"compound": name, "properties_count": len(props)}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"compound": params.get("compound", "water"), "properties_count": 10}


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


