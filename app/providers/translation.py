from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

LANGUAGE_CODES = {
    "english": "en",
    "en": "en",
    "urdu": "ur",
    "ur": "ur",
    "french": "fr",
    "fr": "fr",
    "spanish": "es",
    "es": "es",
    "german": "de",
    "de": "de",
    "arabic": "ar",
    "ar": "ar",
    "hindi": "hi",
    "hi": "hi",
    "chinese": "zh",
    "zh": "zh",
    "portuguese": "pt",
    "pt": "pt",
    "italian": "it",
    "it": "it",
    "turkish": "tr",
    "tr": "tr",
}

OFFLINE_TRANSLATIONS = {
    ("en", "ur"): {
        "hello": "ہیلو",
        "good morning": "صبح بخیر",
        "thank you": "شکریہ",
        "how are you": "آپ کیسے ہیں؟",
        "book": "کتاب",
    },
    ("en", "fr"): {
        "hello": "bonjour",
        "good morning": "bonjour",
        "thank you": "merci",
        "how are you": "comment allez-vous",
        "book": "livre",
    },
    ("en", "es"): {
        "hello": "hola",
        "good morning": "buenos días",
        "thank you": "gracias",
        "how are you": "¿cómo estás?",
        "book": "libro",
    },
}


def normalize_language(value: Any) -> str:
    text = str(value or "").strip().lower()
    return LANGUAGE_CODES.get(text, text[:5])


class MyMemoryProvider(HTTPProvider):
    min_interval_seconds = 1.0

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", "")).strip()
        source = normalize_language(params.get("source_language", "en"))
        target = normalize_language(params.get("target_language", "ur"))
        if not text:
            raise ValueError("text is required")
        if not source or not target:
            raise ValueError("source_language and target_language are required")
        payload = await self.get_json(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": f"{source}|{target}"},
        )
        response = payload.get("responseData") or {}
        translated = str(response.get("translatedText") or "").strip()
        if not translated:
            raise ValueError(f"MyMemory returned no translation for {text}")
        return {
            "translation": {
                "text": translated,
                "source_language": source,
                "target_language": target,
                "match": round(float(payload.get("match") or response.get("match") or 0.0), 3),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", "")).strip()
        source = normalize_language(params.get("source_language", "en"))
        target = normalize_language(params.get("target_language", "ur"))
        if not text:
            raise ValueError("text is required")
        if not source or not target:
            raise ValueError("source_language and target_language are required")
        translations = OFFLINE_TRANSLATIONS.get((source, target), {})
        translated = translations.get(text.lower(), f"[{target}] {text}")
        return {
            "translation": {
                "text": translated,
                "source_language": source,
                "target_language": target,
                "match": 1.0 if text.lower() in translations else 0.4,
            }
        }
