from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

MEAL_FIXTURES = [
    {
        "name": "Chicken Tikka Masala",
        "category": "Chicken",
        "area": "Indian",
        "instructions": "Marinate chicken, grill, simmer in spiced tomato sauce.",
        "thumbnail": "https://www.themealdb.com/images/media/meals/1.jpg",
    },
    {
        "name": "Beef and Mustard Pie",
        "category": "Beef",
        "area": "British",
        "instructions": "Cook beef filling, top with pastry, bake until golden.",
        "thumbnail": "https://www.themealdb.com/images/media/meals/2.jpg",
    },
    {
        "name": "Vegetable Paella",
        "category": "Vegetarian",
        "area": "Spanish",
        "instructions": "Saute vegetables, add rice and stock, simmer.",
        "thumbnail": "https://www.themealdb.com/images/media/meals/3.jpg",
    },
    {
        "name": "Sushi",
        "category": "Seafood",
        "area": "Japanese",
        "instructions": "Prepare sushi rice, slice fish, roll with nori.",
        "thumbnail": "https://www.themealdb.com/images/media/meals/4.jpg",
    },
]


class TheMealDBProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json(
            "https://www.themealdb.com/api/json/v1/1/search.php",
            params={"s": query},
        )
        raw = payload.get("meals") if isinstance(payload, dict) else None
        if not raw:
            raise ValueError(f"no recipes found for {query}")
        meals = []
        for item in raw:
            meals.append(
                {
                    "name": item.get("strMeal", ""),
                    "category": item.get("strCategory", ""),
                    "area": item.get("strArea", ""),
                    "instructions": item.get("strInstructions", ""),
                    "thumbnail": item.get("strMealThumb", ""),
                }
            )
        return {"meals": meals}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        return {"meals": [dict(meal) for meal in MEAL_FIXTURES]}
