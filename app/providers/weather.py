from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

from app.providers.http_base import HTTPProvider


class WeatherProvider(HTTPProvider):
    def _target_date(self, params: dict[str, Any]) -> date:
        value = params.get("date")
        if isinstance(value, str) and value:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                pass
        return date.today() + timedelta(days=1)

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        coordinates = params.get("coordinates") or {}
        if not isinstance(coordinates, dict) or "latitude" not in coordinates:
            raise ValueError("coordinates with latitude and longitude are required")
        payload = await self.get_json(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": coordinates["latitude"],
                "longitude": coordinates["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 7,
            },
        )
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        target = self._target_date(params)
        if str(target) in dates:
            index = dates.index(str(target))
        elif dates:
            index = min(1, len(dates) - 1)
        else:
            raise ValueError("provider returned no daily forecast")
        temp_max = float(daily["temperature_2m_max"][index])
        temp_min = float(daily["temperature_2m_min"][index])
        precip = daily.get("precipitation_probability_max") or [None] * len(dates)
        return {
            "forecast": {
                "temperature": temp_max,
                "temp_max": temp_max,
                "temp_min": temp_min,
                "precipitation_probability": precip[index],
                "date": dates[index],
                "timezone": payload.get("timezone", "auto"),
                "location": coordinates.get("display_name", ""),
                "unit": "C",
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        coordinates = params.get("coordinates") or {}
        if not isinstance(coordinates, dict):
            raise ValueError("coordinates are required")
        location = str(coordinates.get("display_name", "")).split(",")[0] or "Selected location"
        digest = hashlib.sha256(location.lower().encode("utf-8")).digest()
        temp_max = round(24 + (digest[0] / 255) * 14, 1)
        temp_min = round(temp_max - (6 + (digest[1] / 255) * 5), 1)
        precip = int((digest[2] / 255) * 60)
        target = self._target_date(params)
        return {
            "forecast": {
                "temperature": temp_max,
                "temp_max": temp_max,
                "temp_min": temp_min,
                "precipitation_probability": precip,
                "date": str(target),
                "timezone": "Asia/Karachi",
                "location": location,
                "unit": "C",
            }
        }


class MockWeatherFahrenheitProvider(WeatherProvider):
    @staticmethod
    def _to_fahrenheit(value: float) -> float:
        return round((value * 9 / 5) + 32, 1)

    @staticmethod
    def _convert(payload: dict[str, Any]) -> dict[str, Any]:
        forecast = dict(payload["forecast"])
        forecast["temperature"] = MockWeatherFahrenheitProvider._to_fahrenheit(
            float(forecast["temperature"])
        )
        forecast["temp_max"] = MockWeatherFahrenheitProvider._to_fahrenheit(
            float(forecast["temp_max"])
        )
        forecast["temp_min"] = MockWeatherFahrenheitProvider._to_fahrenheit(
            float(forecast["temp_min"])
        )
        forecast["unit"] = "F"
        return {"forecast": forecast}

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._convert(await super().execute(params))

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._convert(await super().offline(params))
