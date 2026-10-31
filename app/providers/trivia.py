from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

TRIVIA_FIXTURE = {
    "question": "What is the capital of France?",
    "answer": "Paris",
    "category": "Geography",
    "difficulty": "easy",
}


class TriviaProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://opentdb.com/api.php", params={"amount": 1})
        if not isinstance(payload, dict):
            raise ValueError("invalid trivia response")
        results = payload.get("results") or []
        if not results or not isinstance(results[0], dict):
            raise ValueError("no trivia results")
        item = results[0]
        return {
            "question": str(item.get("question", "")),
            "answer": str(item.get("correct_answer", "")),
            "category": str(item.get("category", "")),
            "difficulty": str(item.get("difficulty", "")),
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return dict(TRIVIA_FIXTURE)
