from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.providers.http_base import HTTPProvider

COIN_IDS = {
    "bitcoin": "bitcoin",
    "btc": "bitcoin",
    "ethereum": "ethereum",
    "eth": "ethereum",
    "solana": "solana",
    "sol": "solana",
    "dogecoin": "dogecoin",
    "doge": "dogecoin",
    "cardano": "cardano",
    "ripple": "ripple",
    "xrp": "ripple",
    "polkadot": "polkadot",
    "litecoin": "litecoin",
    "ltc": "litecoin",
    "binancecoin": "binancecoin",
    "bnb": "binancecoin",
}

OFFLINE_PRICES = {
    "bitcoin": {"usd": (67250.0, 1_325_000_000_000.0), "eur": (61900.0, 1_219_000_000_000.0)},
    "ethereum": {"usd": (3280.0, 394_000_000_000.0), "eur": (3020.0, 363_000_000_000.0)},
    "solana": {"usd": (154.0, 71_000_000_000.0), "eur": (142.0, 65_000_000_000.0)},
    "dogecoin": {"usd": (0.16, 23_000_000_000.0), "eur": (0.15, 21_000_000_000.0)},
    "cardano": {"usd": (0.62, 22_000_000_000.0), "eur": (0.57, 20_000_000_000.0)},
    "ripple": {"usd": (0.54, 30_000_000_000.0), "eur": (0.50, 27_000_000_000.0)},
    "polkadot": {"usd": (7.1, 10_000_000_000.0), "eur": (6.5, 9_000_000_000.0)},
    "litecoin": {"usd": (84.0, 6_300_000_000.0), "eur": (77.0, 5_800_000_000.0)},
    "binancecoin": {"usd": (590.0, 87_000_000_000.0), "eur": (544.0, 80_000_000_000.0)},
}


class CoinGeckoProvider(HTTPProvider):
    min_interval_seconds = 1.0

    @staticmethod
    def _asset(params: dict[str, Any]) -> str:
        asset = str(params.get("asset", "")).strip().lower()
        if not asset:
            raise ValueError("asset is required")
        return COIN_IDS.get(asset, asset)

    @staticmethod
    def _currency(params: dict[str, Any]) -> str:
        return str(params.get("currency", "usd")).strip().lower() or "usd"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        asset = self._asset(params)
        currency = self._currency(params)
        payload = await self.get_json(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": asset,
                "vs_currencies": currency,
                "include_market_cap": "true",
                "include_last_updated_at": "true",
            },
        )
        row = payload.get(asset) or {}
        if currency not in row:
            raise ValueError(f"CoinGecko has no {currency} price for {asset}")
        timestamp = row.get("last_updated_at")
        last_updated = (
            datetime.fromtimestamp(float(timestamp), UTC).isoformat()
            if timestamp
            else datetime.now(UTC).isoformat()
        )
        return {
            "price": {
                "asset": asset,
                "currency": currency.upper(),
                "price": float(row[currency]),
                "market_cap": float(row.get(f"{currency}_market_cap") or 0.0),
                "last_updated": last_updated,
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        asset = self._asset(params)
        currency = self._currency(params)
        prices = OFFLINE_PRICES.get(asset)
        if prices is None or currency not in prices:
            raise ValueError(f"offline fixture has no {currency} price for {asset}")
        price, market_cap = prices[currency]
        return {
            "price": {
                "asset": asset,
                "currency": currency.upper(),
                "price": price,
                "market_cap": market_cap,
                "last_updated": "2026-10-20T12:00:00+00:00",
            }
        }
