from __future__ import annotations

from datetime import date
from typing import Any

from app.providers.http_base import HTTPProvider

HOLIDAY_FIXTURES = {
    "PK": [
        ("2026-02-05", "Kashmir Solidarity Day", "یوم یکجہتی کشمیر"),
        ("2026-03-23", "Pakistan Day", "یوم پاکستان"),
        ("2026-05-01", "Labour Day", "یوم مزدور"),
        ("2026-08-14", "Independence Day", "یوم آزادی"),
        ("2026-12-25", "Christmas Day", "کرسمس"),
    ],
    "US": [
        ("2026-01-01", "New Year's Day", "New Year's Day"),
        ("2026-07-04", "Independence Day", "Independence Day"),
        ("2026-11-26", "Thanksgiving Day", "Thanksgiving Day"),
        ("2026-12-25", "Christmas Day", "Christmas Day"),
    ],
    "GB": [
        ("2026-01-01", "New Year's Day", "New Year's Day"),
        ("2026-04-03", "Good Friday", "Good Friday"),
        ("2026-12-25", "Christmas Day", "Christmas Day"),
        ("2026-12-28", "Boxing Day", "Boxing Day"),
    ],
    "JP": [
        ("2026-01-01", "New Year's Day", "元日"),
        ("2026-02-11", "National Foundation Day", "建国記念の日"),
        ("2026-05-03", "Constitution Memorial Day", "憲法記念日"),
        ("2026-11-03", "Culture Day", "文化の日"),
    ],
    "DE": [
        ("2026-01-01", "New Year's Day", "Neujahr"),
        ("2026-10-03", "German Unity Day", "Tag der Deutschen Einheit"),
        ("2026-12-25", "Christmas Day", "Erster Weihnachtstag"),
    ],
}


class HolidaysProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        country_code = str(params.get("country_code", "")).upper()
        year = int(params.get("year", date.today().year))
        if len(country_code) != 2:
            raise ValueError("country_code must be two letters")
        payload = await self.get_json(
            f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"
        )
        holidays = [
            {
                "date": item.get("date", ""),
                "name": item.get("name", ""),
                "local_name": item.get("localName", item.get("name", "")),
                "country_code": item.get("countryCode", country_code),
            }
            for item in payload
        ]
        return {"holidays": holidays}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        country_code = str(params.get("country_code", "")).upper()
        year = int(params.get("year", date.today().year))
        if len(country_code) != 2:
            raise ValueError("country_code must be two letters")
        rows = HOLIDAY_FIXTURES.get(country_code)
        if rows is None:
            rows = [
                (f"{year}-01-01", "New Year's Day", "New Year's Day"),
                (f"{year}-12-25", "Christmas Day", "Christmas Day"),
            ]
        holidays = [
            {
                "date": item[0].replace("2026", str(year)),
                "name": item[1],
                "local_name": item[2],
                "country_code": country_code,
            }
            for item in rows
        ]
        return {"holidays": holidays}
