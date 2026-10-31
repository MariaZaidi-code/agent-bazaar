from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

LEAGUE_PATHS = {
    "nfl": "football/nfl",
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "epl": "soccer/eng.1",
    "premier-league": "soccer/eng.1",
    "premier league": "soccer/eng.1",
    "soccer": "soccer/eng.1",
    "football": "soccer/eng.1",
    "cricket": "cricket/8039",
    "ipl": "cricket/8039",
    "psl": "cricket/8039",
}

OFFLINE_SCORES = {
    "football/nfl": (
        "Kansas City Chiefs",
        "Buffalo Bills",
        27,
        24,
        "Final",
        "NFL",
    ),
    "basketball/nba": (
        "Boston Celtics",
        "New York Knicks",
        112,
        105,
        "Final",
        "NBA",
    ),
    "baseball/mlb": (
        "New York Yankees",
        "Boston Red Sox",
        6,
        4,
        "Final",
        "MLB",
    ),
    "hockey/nhl": (
        "Toronto Maple Leafs",
        "Montreal Canadiens",
        3,
        2,
        "Final",
        "NHL",
    ),
    "soccer/eng.1": (
        "Arsenal",
        "Chelsea",
        2,
        1,
        "Full time",
        "Premier League",
    ),
    "cricket/8039": (
        "Pakistan",
        "India",
        168,
        164,
        "Completed",
        "Cricket",
    ),
}


def _score(value: Any) -> int:
    text = str(value or "0").strip()
    try:
        return int(float(text))
    except ValueError:
        return 0


class EspnScoresProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        league = str(params.get("league", "")).strip().lower()
        path = LEAGUE_PATHS.get(league, league if "/" in league else "soccer/eng.1")
        payload = await self.get_json(
            f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
        )
        scores = []
        for event in (payload.get("events") or [])[:5]:
            competitions = event.get("competitions") or [{}]
            competition = competitions[0]
            competitors = competition.get("competitors") or []
            home = next(
                (item for item in competitors if item.get("homeAway") == "home"),
                competitors[0] if competitors else {},
            )
            away = next(
                (item for item in competitors if item.get("homeAway") == "away"),
                competitors[1] if len(competitors) > 1 else {},
            )
            status = (
                ((competition.get("status") or {}).get("type") or {}).get("description")
                or ((event.get("status") or {}).get("type") or {}).get("description")
                or ""
            )
            scores.append(
                {
                    "league": path.rsplit("/", 1)[-1].upper(),
                    "home_team": str((home.get("team") or {}).get("displayName") or ""),
                    "away_team": str((away.get("team") or {}).get("displayName") or ""),
                    "home_score": _score(home.get("score")),
                    "away_score": _score(away.get("score")),
                    "status": str(status),
                    "date": str(event.get("date") or ""),
                }
            )
        if not scores:
            raise ValueError(f"ESPN returned no scores for {path}")
        return {"scores": scores}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        league = str(params.get("league", "")).strip().lower()
        path = LEAGUE_PATHS.get(league, league if "/" in league else "soccer/eng.1")
        fixture = OFFLINE_SCORES.get(path, OFFLINE_SCORES["soccer/eng.1"])
        return {
            "scores": [
                {
                    "league": fixture[5],
                    "home_team": fixture[0],
                    "away_team": fixture[1],
                    "home_score": fixture[2],
                    "away_score": fixture[3],
                    "status": fixture[4],
                    "date": "2026-10-20T18:00:00Z",
                }
            ]
        }
