from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.providers.http_base import HTTPProvider


class TheMealDBProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("recipe_query", "")).strip()
        if not query:
            raise ValueError("recipe_query is required")
        payload = await self.get_json(
            "https://www.themealdb.com/api/json/v1/1/search.php",
            params={"s": query},
        )
        meals = []
        for meal in (payload.get("meals") or [])[:5]:
            ingredients = []
            for index in range(1, 21):
                ingredient = str(meal.get(f"strIngredient{index}") or "").strip()
                measure = str(meal.get(f"strMeasure{index}") or "").strip()
                if ingredient:
                    ingredients.append(f"{measure} {ingredient}".strip())
            meals.append(
                {
                    "name": str(meal.get("strMeal") or ""),
                    "category": str(meal.get("strCategory") or ""),
                    "area": str(meal.get("strArea") or ""),
                    "instructions": str(meal.get("strInstructions") or "")[:1200],
                    "ingredients": ingredients,
                    "image": str(meal.get("strMealThumb") or ""),
                    "source": str(meal.get("strSource") or meal.get("strYoutube") or ""),
                }
            )
        if not meals:
            raise ValueError(f"TheMealDB returned no recipes for {query}")
        return {"meals": meals}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("recipe_query", "")).strip()
        if not query:
            raise ValueError("recipe_query is required")
        return {
            "meals": [
                {
                    "name": f"Offline {query.title()} Bowl",
                    "category": "Vegetarian",
                    "area": "International",
                    "instructions": (
                        f"Offline fixture recipe for {query}. Combine the ingredients, "
                        "cook until tender and season to taste."
                    ),
                    "ingredients": ["1 cup main ingredient", "1 tablespoon oil", "Salt to taste"],
                    "image": f"https://www.themealdb.com/images/search/{quote(query)}.jpg",
                    "source": f"https://www.themealdb.com/search.php?s={quote(query)}",
                }
            ]
        }
