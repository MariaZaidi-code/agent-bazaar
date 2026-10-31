from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

COINGECKO_FIXTURES = {
    "bitcoin": {"name": "bitcoin", "price": 65000.0, "market_cap": 1_280_000_000_000.0, "change_24h": 2.34},
    "ethereum": {"name": "ethereum", "price": 3200.0, "market_cap": 385_000_000_000.0, "change_24h": -1.12},
    "solana": {"name": "solana", "price": 145.0, "market_cap": 68_000_000_000.0, "change_24h": 4.56},
    "dogecoin": {"name": "dogecoin", "price": 0.12, "market_cap": 17_000_000_000.0, "change_24h": 0.78},
    "cardano": {"name": "cardano", "price": 0.45, "market_cap": 16_000_000_000.0, "change_24h": -0.33},
}


class CoinGeckoProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        coin = str(params.get("coin", "")).strip().lower()
        if not coin:
            raise ValueError("coin is required")
        vs = str(params.get("vs", "usd")).strip().lower() or "usd"
        payload = await self.get_json(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": coin,
                "vs_currencies": vs,
                "include_market_cap": "true",
                "include_24hr_change": "true",
            },
        )
        data = payload.get(coin) if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not data:
            raise ValueError(f"no price data for {coin}")
        price_key = vs
        market_cap_key = f"{vs}_market_cap"
        change_key = f"{vs}_24h_change"
        if price_key not in data:
            raise ValueError(f"no price data for {coin} in {vs}")
        return {
            "crypto": {
                "name": coin,
                "price": data.get(price_key),
                "market_cap": data.get(market_cap_key),
                "change_24h": data.get(change_key),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        coin = str(params.get("coin", "")).strip().lower()
        if not coin:
            raise ValueError("coin is required")
        fixture = COINGECKO_FIXTURES.get(coin, {
            "name": coin,
            "price": 100.0,
            "market_cap": 1_000_000_000.0,
            "change_24h": 1.0,
        })
        return {
            "crypto": {
                "name": fixture["name"],
                "price": fixture["price"],
                "market_cap": fixture["market_cap"],
                "change_24h": fixture["change_24h"],
            }
        }
