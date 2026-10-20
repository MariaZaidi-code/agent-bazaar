from __future__ import annotations

from datetime import date
from typing import Any

from app.providers.http_base import HTTPProvider

USD_RATES = {
    "USD": 1.0,
    "PKR": 278.50,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 149.50,
    "INR": 83.20,
    "AED": 3.6725,
    "CAD": 1.36,
    "AUD": 1.52,
    "CNY": 7.24,
    "SAR": 3.75,
    "TRY": 32.10,
    "SGD": 1.34,
    "CHF": 0.88,
}


class CurrencyProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        amount = float(params.get("amount", 0))
        source = str(params.get("from_currency", "")).upper()
        target = str(params.get("to_currency", "")).upper()
        if amount <= 0:
            raise ValueError("amount must be positive")
        if len(source) != 3 or len(target) != 3:
            raise ValueError("currency codes must be three letters")
        if source == target:
            return {
                "conversion": {
                    "amount": round(amount, 2),
                    "currency": target,
                    "rate": 1.0,
                    "from": source,
                    "to": target,
                    "date": str(date.today()),
                    "source": "identity",
                }
            }
        try:
            payload = await self.get_json(
                "https://api.frankfurter.app/latest",
                params={"amount": amount, "from": source, "to": target},
            )
            rate = float(payload["rates"][target]) / amount
            return {
                "conversion": {
                    "amount": round(float(payload["rates"][target]), 2),
                    "currency": target,
                    "rate": round(rate, 6),
                    "from": source,
                    "to": target,
                    "date": payload.get("date", str(date.today())),
                    "source": "frankfurter",
                }
            }
        except Exception:
            payload = await self.get_json(f"https://open.er-api.com/v6/latest/{source}")
            rates = payload.get("rates") or {}
            if target not in rates:
                raise ValueError(f"no rate available for {source} to {target}") from None
            rate = float(rates[target])
            return {
                "conversion": {
                    "amount": round(amount * rate, 2),
                    "currency": target,
                    "rate": round(rate, 6),
                    "from": source,
                    "to": target,
                    "date": str(payload.get("time_last_update_utc", date.today()))[:16],
                    "source": "open-er-api fallback",
                }
            }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        amount = float(params.get("amount", 0))
        source = str(params.get("from_currency", "")).upper()
        target = str(params.get("to_currency", "")).upper()
        if amount <= 0:
            raise ValueError("amount must be positive")
        if source not in USD_RATES or target not in USD_RATES:
            raise ValueError(f"offline fixture has no rate for {source} or {target}")
        rate = USD_RATES[target] / USD_RATES[source]
        return {
            "conversion": {
                "amount": round(amount * rate, 2),
                "currency": target,
                "rate": round(rate, 6),
                "from": source,
                "to": target,
                "date": str(date.today()),
                "source": "offline fixture",
            }
        }
