from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

POKEMON_FIXTURES = {
    "pikachu": {
        "name": "pikachu",
        "id": 25,
        "types": ["electric"],
        "height": 4,
        "weight": 60,
        "sprite": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png",
    },
    "charizard": {
        "name": "charizard",
        "id": 6,
        "types": ["fire", "flying"],
        "height": 17,
        "weight": 905,
        "sprite": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/6.png",
    },
    "bulbasaur": {
        "name": "bulbasaur",
        "id": 1,
        "types": ["grass", "poison"],
        "height": 7,
        "weight": 69,
        "sprite": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/1.png",
    },
    "squirtle": {
        "name": "squirtle",
        "id": 7,
        "types": ["water"],
        "height": 5,
        "weight": 90,
        "sprite": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/7.png",
    },
}


class PokeAPIProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip().lower()
        if not name:
            raise ValueError("name is required")
        payload = await self.get_json(f"https://pokeapi.co/api/v2/pokemon/{name}")
        if not isinstance(payload, dict):
            raise ValueError("invalid pokemon response")
        types = [
            (entry.get("type") or {}).get("name", "")
            for entry in payload.get("types", [])
            if isinstance(entry, dict)
        ]
        types = [t for t in types if t]
        sprites = payload.get("sprites") or {}
        return {
            "pokemon": {
                "name": payload.get("name", name),
                "id": payload.get("id"),
                "types": types,
                "height": payload.get("height"),
                "weight": payload.get("weight"),
                "sprite": sprites.get("front_default"),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip().lower()
        if not name:
            raise ValueError("name is required")
        fixture = POKEMON_FIXTURES.get(name, {
            "name": name,
            "id": 0,
            "types": ["unknown"],
            "height": 0,
            "weight": 0,
            "sprite": "",
        })
        return {"pokemon": dict(fixture)}
