from __future__ import annotations

import calendar
import json
import re
from datetime import date, timedelta

from app.core.llm import LLMClient
from app.knowledge.ontology import Ontology
from app.schemas import SubGoal

CURRENCY_WORDS = {
    "dollar": "USD",
    "dollars": "USD",
    "usd": "USD",
    "rupee": "PKR",
    "rupees": "PKR",
    "pkr": "PKR",
    "euro": "EUR",
    "euros": "EUR",
    "eur": "EUR",
    "pound": "GBP",
    "pounds": "GBP",
    "gbp": "GBP",
    "yen": "JPY",
    "jpy": "JPY",
    "inr": "INR",
    "aed": "AED",
    "dirham": "AED",
    "dirhams": "AED",
    "aud": "AUD",
    "australian dollar": "AUD",
    "australian dollars": "AUD",
    "cad": "CAD",
    "canadian dollar": "CAD",
    "canadian dollars": "CAD",
    "chf": "CHF",
    "swiss franc": "CHF",
    "swiss francs": "CHF",
    "sar": "SAR",
    "riyal": "SAR",
    "riyals": "SAR",
    "saudi riyal": "SAR",
    "saudi riyals": "SAR",
    "cny": "CNY",
    "yuan": "CNY",
    "rmb": "CNY",
    "try": "TRY",
    "lira": "TRY",
    "sgd": "SGD",
    "singapore dollar": "SGD",
    "singapore dollars": "SGD",
}

COUNTRY_CODES = {
    "pakistan": "PK",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "us": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "japan": "JP",
    "germany": "DE",
    "france": "FR",
    "india": "IN",
    "china": "CN",
    "canada": "CA",
    "australia": "AU",
    "united arab emirates": "AE",
    "uae": "AE",
    "saudi arabia": "SA",
    "turkey": "TR",
    "italy": "IT",
    "spain": "ES",
}

COUNTRY_NAMES = sorted(COUNTRY_CODES, key=len, reverse=True)
CURRENCY_CODES = sorted(set(CURRENCY_WORDS.values()))

WEATHER_WORDS = re.compile(r"\b(weather|temperature|forecast|rain|raining|hot|cold|climate)\b", re.I)
HOLIDAY_WORDS = re.compile(r"\b(holiday|holidays|public holiday|national holiday)\b", re.I)
COUNTRY_WORDS = re.compile(r"\b(population|capital|country|nation|facts?)\b", re.I)
RESEARCH_WORDS = re.compile(
    r"\b(paper|papers|research|arxiv|study|studies|literature|publications?)\b", re.I
)
DOCUMENT_WORDS = re.compile(r"\b(document|uploaded|file|pdf|docx|according to the)\b", re.I)
SQL_WORDS = re.compile(
    r"\b(students?|enrol(?:l)?(?:ed|ment)?|courses?|gpa|university|database|sql|faculty|programs?)\b",
    re.I,
)
NEWS_WORDS = re.compile(r"\b(news|headlines?|current events)\b", re.I)
CRYPTO_WORDS = re.compile(
    r"\b(crypto(?:currency)?|bitcoin|btc|ethereum|eth|solana|sol|dogecoin|doge|"
    r"cardano|ripple|xrp|polkadot|litecoin|ltc|bnb|binancecoin)\b",
    re.I,
)
TV_WORDS = re.compile(r"\b(tv|television)\b|\b(tv|television)\s+(show|shows|series)\b", re.I)
BOOK_WORDS = re.compile(r"\b(books?|novels?)\b", re.I)
TRANSLATE_WORDS = re.compile(r"\b(translate|translation|translated)\b", re.I)
TIME_WORDS = re.compile(
    r"\b(what time|current time|local time|time is it|time in|timezone|clock)\b", re.I
)
SUN_WORDS = re.compile(
    r"\b(sunrise|sunset|solar noon|day length|daylight|golden hour)\b", re.I
)
RECIPE_WORDS = re.compile(r"\b(recipes?|cook|cooking|bake|baking|dish)\b", re.I)
SPORTS_WORDS = re.compile(
    r"\b(nba|nfl|mlb|nhl|epl|ipl|psl|premier league|cricket|scores?|scoreboard|"
    r"match result|game result|who won)\b",
    re.I,
)

CRYPTO_ASSETS = {
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
    "bnb": "binancecoin",
    "binancecoin": "binancecoin",
}

TIMEZONES = {
    "utc": "Etc/UTC",
    "gmt": "Etc/UTC",
    "karachi": "Asia/Karachi",
    "lahore": "Asia/Karachi",
    "islamabad": "Asia/Karachi",
    "pakistan": "Asia/Karachi",
    "tokyo": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "london": "Europe/London",
    "uk": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "sydney": "Australia/Sydney",
    "dubai": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "delhi": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
    "india": "Asia/Kolkata",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "singapore": "Asia/Singapore",
    "toronto": "America/Toronto",
    "chicago": "America/Chicago",
}

LANGUAGES = {
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

SPORTS_LEAGUES = {
    "nba": "NBA",
    "nfl": "NFL",
    "mlb": "MLB",
    "nhl": "NHL",
    "epl": "EPL",
    "premier league": "EPL",
    "soccer": "EPL",
    "football": "EPL",
    "ipl": "IPL",
    "psl": "PSL",
    "cricket": "Cricket",
}


class TaskPlanner:
    def __init__(self, ontology: Ontology, llm: LLMClient) -> None:
        self.ontology = ontology
        self.llm = llm

    async def decompose(
        self, task: str, correlation_id: str = ""
    ) -> tuple[list[SubGoal], list[str]]:
        cleaned = " ".join(task.split())
        if not cleaned:
            raise ValueError("Task is empty")
        subgoals = self._deterministic(cleaned)
        warnings: list[str] = []
        if subgoals:
            return subgoals, warnings
        if self.llm.enabled:
            llm_subgoals = await self._llm_plan(cleaned)
            if llm_subgoals:
                warnings.append("Plan produced by the optional LLM planner.")
                return llm_subgoals, warnings
            warnings.append("LLM planner returned no valid plan; deterministic planner found none.")
        raise ValueError(
            "I could not decompose this task. Try asking about weather, currency, "
            "country facts, public holidays, research papers, news, crypto prices, "
            "TV shows, books, translation, current time, sunrise or sunset, recipes, "
            "sports scores, the sample university database, or an uploaded document."
        )

    def _deterministic(self, task: str) -> list[SubGoal]:
        lowered = task.lower()
        subgoals: list[SubGoal] = []
        weather_location = self._location(task) if WEATHER_WORDS.search(task) else None
        if weather_location:
            geocode_id = "g1"
            weather_date = self._date(lowered)
            subgoals.append(
                SubGoal(
                    id=geocode_id,
                    capability="GeocodeLocation",
                    description=f"Geocode the location {weather_location} to latitude and longitude.",
                    intent="location lookup",
                    slots={"location": weather_location},
                    branch="weather",
                )
            )
            subgoals.append(
                SubGoal(
                    id="g2",
                    capability="GetWeatherForecast",
                    description=(
                        f"Weather forecast and temperature for {weather_location} on {weather_date}."
                    ),
                    intent="weather forecast",
                    slots={"date": weather_date, "location": weather_location},
                    depends_on=[geocode_id],
                    branch="weather",
                )
            )
        if NEWS_WORDS.search(task):
            topic = self._news_query(task)
            if topic:
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="SearchNews",
                        description=f"Recent news stories about {topic}.",
                        intent="news search",
                        slots={"news_query": topic},
                        branch="news",
                    )
                )
        if CRYPTO_WORDS.search(task):
            asset = self._crypto_asset(task)
            if asset:
                currency = self._requested_currency(task)
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="GetCryptoPrice",
                        description=f"Current price of {asset} in {currency}.",
                        intent="crypto price",
                        slots={"asset": asset, "currency": currency},
                        branch="crypto",
                    )
                )
        if TV_WORDS.search(task):
            show_query = self._show_query(task)
            if show_query:
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="SearchTVShows",
                        description=f"Television shows matching {show_query}.",
                        intent="television search",
                        slots={"show_query": show_query},
                        branch="tv",
                    )
                )
        if BOOK_WORDS.search(task):
            book_query = self._book_query(task)
            if book_query:
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="SearchBooks",
                        description=f"Books matching {book_query}.",
                        intent="book search",
                        slots={"book_query": book_query},
                        branch="books",
                    )
                )
        if TRANSLATE_WORDS.search(task):
            translation = self._translation(task)
            if translation:
                text, source, target = translation
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="TranslateText",
                        description=f"Translate {text} from {source} to {target}.",
                        intent="translation",
                        slots={
                            "text": text,
                            "source_language": source,
                            "target_language": target,
                        },
                        branch="translation",
                    )
                )
        if TIME_WORDS.search(task):
            timezone = self._timezone(task)
            if timezone:
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="GetCurrentTime",
                        description=f"Current local time in {timezone}.",
                        intent="current time",
                        slots={"timezone": timezone},
                        branch="time",
                    )
                )
        if SUN_WORDS.search(task):
            sun_location = self._sun_location(task)
            if sun_location:
                geocode_id = f"g{len(subgoals) + 1}"
                subgoals.append(
                    SubGoal(
                        id=geocode_id,
                        capability="GeocodeLocation",
                        description=f"Geocode {sun_location} for solar times.",
                        intent="location lookup",
                        slots={"location": sun_location},
                        branch="sun",
                    )
                )
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="GetSunTimes",
                        description=f"Sunrise and sunset times for {sun_location}.",
                        intent="solar times",
                        slots={"date": self._sun_date(lowered)},
                        depends_on=[geocode_id],
                        branch="sun",
                    )
                )
        if RECIPE_WORDS.search(task):
            recipe_query = self._recipe_query(task)
            if recipe_query:
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="SearchRecipes",
                        description=f"Recipes for {recipe_query}.",
                        intent="recipe search",
                        slots={"recipe_query": recipe_query},
                        branch="recipes",
                    )
                )
        if SPORTS_WORDS.search(task):
            league = self._sports_league(task)
            if league:
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="GetSportsScores",
                        description=f"Latest {league} scores.",
                        intent="sports scores",
                        slots={"league": league},
                        branch="sports",
                    )
                )
        currency = self._currency(task)
        if currency:
            amount, source, target = currency
            subgoals.append(
                SubGoal(
                    id=f"g{len(subgoals) + 1}",
                    capability="ConvertCurrency",
                    description=(
                        f"Convert {amount:g} {source} to {target} using the current exchange rate."
                    ),
                    intent="currency conversion",
                    slots={
                        "amount": amount,
                        "from_currency": source,
                        "to_currency": target,
                    },
                    branch="currency",
                )
            )
        if HOLIDAY_WORDS.search(task):
            country = self._country(task, default="Pakistan")
            year = self._year(task)
            code = COUNTRY_CODES.get(country.lower(), country.upper()[:2])
            subgoals.append(
                SubGoal(
                    id=f"g{len(subgoals) + 1}",
                    capability="GetPublicHolidays",
                    description=f"Public holidays in {country} for the year {year}.",
                    intent="public holidays",
                    slots={"country_code": code, "year": year, "country": country},
                    branch="holidays",
                )
            )
        if COUNTRY_WORDS.search(task) and not HOLIDAY_WORDS.search(task):
            country = self._country(task, default="")
            if country:
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="GetCountryFacts",
                        description=f"Country facts, population and capital of {country}.",
                        intent="country facts",
                        slots={"country": country},
                        branch="country",
                    )
                )
        if RESEARCH_WORDS.search(task) and not DOCUMENT_WORDS.search(task):
            topic = self._research_topic(task)
            if topic:
                subgoals.append(
                    SubGoal(
                        id=f"g{len(subgoals) + 1}",
                        capability="SearchResearchPapers",
                        description=f"Recent research papers about {topic}.",
                        intent="research search",
                        slots={"query": topic},
                        branch="research",
                    )
                )
        if SQL_WORDS.search(task):
            subgoals.append(
                SubGoal(
                    id=f"g{len(subgoals) + 1}",
                    capability="QueryStructuredData",
                    description=f"Answer this question using the read-only university database: {task}",
                    intent="database query",
                    slots={"question": task},
                    branch="database",
                )
            )
        if DOCUMENT_WORDS.search(task):
            subgoals.append(
                SubGoal(
                    id=f"g{len(subgoals) + 1}",
                    capability="AnswerFromDocument",
                    description=f"Answer this question from the uploaded document: {task}",
                    intent="document question answering",
                    slots={"question": task},
                    branch="document",
                )
            )
        return subgoals

    def _location(self, task: str) -> str | None:
        pattern = re.compile(
            r"(?:weather|temperature|forecast|rain|hot|cold)[^.!?]{0,60}?"
            r"\b(?:in|for|at)\s+([A-Za-z][A-Za-z .'\-]{1,45})",
            re.I,
        )
        match = pattern.search(task)
        if not match:
            return None
        location = match.group(1)
        location = re.split(
            r"\b(?:tomorrow|today|tonight|next week|this week|this weekend|on\s+\w+|and|please)\b",
            location,
            maxsplit=1,
            flags=re.I,
        )[0]
        location = location.strip(" ,.;")
        if not location:
            return None
        return location

    def _currency(self, task: str) -> tuple[float, str, str] | None:
        code_pattern = "|".join(
            [re.escape(code) for code in CURRENCY_CODES]
            + [re.escape(word) for word in sorted(CURRENCY_WORDS, key=len, reverse=True)]
        )
        pattern = re.compile(
            rf"(\d[\d,]*(?:\.\d+)?)\s*({code_pattern})\s*(?:to|into|in)\s*({code_pattern})",
            re.I,
        )
        match = pattern.search(task)
        if not match:
            return None
        amount = float(match.group(1).replace(",", ""))
        source = CURRENCY_WORDS.get(match.group(2).lower(), match.group(2).upper())
        target = CURRENCY_WORDS.get(match.group(3).lower(), match.group(3).upper())
        return amount, source, target

    @staticmethod
    def _subject(value: str) -> str:
        return value.strip(" \t\r\n.,;:!?\"'()[]")

    def _news_query(self, task: str) -> str | None:
        patterns = (
            r"(?:news|headlines?)\s+(?:about|on|regarding|for)\s+(.+)",
            r"(?:current events)\s+(?:in|about|on)\s+(.+)",
            r"(?:latest|recent|today'?s?|breaking)\s+(.+?)\s+(?:news|headlines?)\b",
            r"(?:search|find|get|show me)\s+(?:the\s+)?(?:latest\s+)?(?:news|headlines?)\s*"
            r"(?:about|on|regarding|for)?\s*(.*)",
        )
        for pattern in patterns:
            match = re.search(pattern, task, re.I)
            if match:
                query = self._subject(match.group(1))
                if query:
                    return query
        return None

    @staticmethod
    def _crypto_asset(task: str) -> str | None:
        found: list[tuple[int, str]] = []
        for name, asset in CRYPTO_ASSETS.items():
            match = re.search(rf"\b{re.escape(name)}\b", task, re.I)
            if match:
                found.append((match.start(), asset))
        return min(found)[1] if found else None

    @staticmethod
    def _requested_currency(task: str) -> str:
        found: list[tuple[int, str]] = []
        for word, code in CURRENCY_WORDS.items():
            match = re.search(rf"\b{re.escape(word)}\b", task, re.I)
            if match:
                found.append((match.start(), code))
        if found:
            return min(found)[1]
        match = re.search(r"\b([A-Z]{3})\b", task)
        if match and match.group(1) in CURRENCY_CODES:
            return match.group(1)
        return "USD"

    def _show_query(self, task: str) -> str | None:
        patterns = (
            r"(?:tv|television)\s+(?:show|shows|series|programs?)\s+"
            r"(?:about|like|called|named|on|for)?\s*(.+)",
            r"(?:show|shows|series)\s+(?:about|like|called|named)\s+(.+)",
            r"(?:search|find|recommend)\s+(?:for\s+)?(?:a\s+)?(?:tv\s+)?"
            r"(?:show|shows|series)\s+(?:like|about|called|named)?\s*(.+)",
        )
        for pattern in patterns:
            match = re.search(pattern, task, re.I)
            if match:
                query = self._subject(match.group(1))
                if query:
                    return query
        return None

    def _book_query(self, task: str) -> str | None:
        if re.search(
            r"\bbook\s+(?:a|an|the)\s+(?:flight|hotel|table|ticket|room|taxi|ride)\b",
            task,
            re.I,
        ):
            return None
        patterns = (
            r"(?:books?|novels?)\s+(?:about|on|by|called|named|from)\s+(.+)",
            r"(?:search|find|recommend|read|looking for)\s+(?:for\s+)?(?:a\s+)?(?:new\s+)?"
            r"(?:book|books|novel|novels)\s+(?:about|on|by|called|named)?\s*(.+)",
            r"(.+?)\s+(?:books?|novels?)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, task, re.I)
            if match:
                query = self._subject(match.group(1))
                if query:
                    return query
        return None

    def _translation(self, task: str) -> tuple[str, str, str] | None:
        pattern = re.compile(
            r"translate\s+(?:the\s+)?(?:phrase|word|text|sentence)?\s*[\"']?(.+?)[\"']?\s+"
            r"(?:from\s+([A-Za-z]+)\s+)?(?:to|into)\s+([A-Za-z]+)\s*[.!?]*$",
            re.I,
        )
        match = pattern.search(task)
        if not match:
            return None
        text = self._subject(match.group(1))
        source = (match.group(2) or "English").lower()
        target = match.group(3).lower()
        if not text or target not in LANGUAGES:
            return None
        if match.group(2) and source not in LANGUAGES:
            return None
        return text, LANGUAGES.get(source, "en"), LANGUAGES[target]

    @staticmethod
    def _timezone(task: str) -> str | None:
        explicit = re.search(r"\b([A-Za-z]+/[A-Za-z_]+)\b", task)
        if explicit:
            return explicit.group(1)
        lowered = task.lower()
        for name in sorted(TIMEZONES, key=len, reverse=True):
            if re.search(rf"\b{re.escape(name)}\b", lowered):
                return TIMEZONES[name]
        return None

    def _sun_location(self, task: str) -> str | None:
        pattern = re.compile(
            r"(?:sunrise|sunset|solar noon|day length|daylight|golden hour)"
            r"[^.!?]{0,60}?\b(?:in|for|at)\s+([A-Za-z][A-Za-z .'\-]{1,45})",
            re.I,
        )
        match = pattern.search(task)
        if not match:
            return None
        location = re.split(
            r"\b(?:tomorrow|today|tonight|next week|this week|on\s+\w+|and|please)\b",
            match.group(1),
            maxsplit=1,
            flags=re.I,
        )[0]
        location = self._subject(location)
        return location or None

    @staticmethod
    def _sun_date(lowered_task: str) -> str:
        if "tomorrow" in lowered_task:
            target = date.today() + timedelta(days=1)
        elif "next week" in lowered_task:
            target = date.today() + timedelta(days=7)
        else:
            target = date.today()
        return target.isoformat()

    def _recipe_query(self, task: str) -> str | None:
        patterns = (
            r"(?:recipes?)\s+(?:for|of|about)?\s*(.+)",
            r"how\s+(?:do|to)\s+(?:i\s+)?(?:cook|make|bake)\s+(.+)",
            r"(?:search|find)\s+(?:for\s+)?(?:a\s+)?recipes?\s+(?:for|of)?\s*(.+)",
            r"(?:cook|cooking|bake|baking)\s+(.+)",
            r"(.+?)\s+recipes?\b",
        )
        for pattern in patterns:
            match = re.search(pattern, task, re.I)
            if match:
                query = self._subject(match.group(1))
                if query:
                    return query
        return None

    @staticmethod
    def _sports_league(task: str) -> str | None:
        for name in sorted(SPORTS_LEAGUES, key=len, reverse=True):
            if re.search(rf"\b{re.escape(name)}\b", task, re.I):
                return SPORTS_LEAGUES[name]
        return "EPL" if re.search(r"\bsports scores?\b", task, re.I) else None

    def _country(self, task: str, default: str) -> str:
        lowered = task.lower()
        for name in COUNTRY_NAMES:
            if re.search(rf"\b{re.escape(name)}\b", lowered):
                return name.title() if len(name) > 3 else name.upper()
        match = re.search(r"\b([A-Z]{2})\b", task)
        if match and match.group(1) in COUNTRY_CODES.values():
            return match.group(1)
        phrase = re.search(
            r"(?:population|capital|facts?|country)\s+(?:of|about)\s+([A-Z][A-Za-z .'-]{1,40})",
            task,
        )
        if phrase:
            return phrase.group(1).strip(" ,.;")
        return default

    @staticmethod
    def _year(task: str) -> int:
        match = re.search(r"\b(20\d{2})\b", task)
        return int(match.group(1)) if match else date.today().year

    @staticmethod
    def _date(lowered_task: str) -> str:
        if "today" in lowered_task:
            target = date.today()
        elif "next week" in lowered_task:
            target = date.today() + timedelta(days=7)
        else:
            target = date.today() + timedelta(days=1)
        return target.isoformat()

    @staticmethod
    def _research_topic(task: str) -> str | None:
        match = re.search(
            r"(?:papers?|publications?|research|studies|study|literature)\s+(?:on|about|into|for)\s+(.+)",
            task,
            re.I,
        )
        if match:
            topic = re.split(r"\band\b|[,;]", match.group(1), maxsplit=1)[0].strip()
            if topic:
                return topic.strip(" .")
        match = re.search(r"(?:arxiv|search)\s+(?:for\s+)?(.+)", task, re.I)
        if match:
            return match.group(1).strip(" .")
        return None

    async def _llm_plan(self, task: str) -> list[SubGoal]:
        capabilities = {
            name: {
                "description": data.get("description", ""),
                "inputs": data.get("inputs", []),
                "outputs": data.get("outputs", []),
            }
            for name, data in self.ontology.capabilities.items()
        }
        system = (
            "You are the planning component of Agent Bazaar. Decompose the developer task "
            "into the smallest number of sub-goals that use the available ontology "
            "capabilities. Return JSON only."
        )
        prompt = (
            f"Task: {task}\n\nAvailable capabilities:\n"
            f"{json.dumps(capabilities, indent=2)}\n\n"
            "Return {\"subgoals\": [{\"capability\": str, \"description\": str, "
            "\"intent\": str, \"slots\": {}, \"depends_on\": []}]}. "
            "Use ids g1, g2, ... in order. A dependent sub-goal lists earlier ids in "
            "depends_on. Slots must contain user-provided values only."
        )
        result = await self.llm.complete(prompt, system=system, json_mode=True, max_tokens=700)
        if not result.ok:
            return []
        payload = self.llm.parse_json_object(result.text)
        if not payload or not isinstance(payload.get("subgoals"), list):
            return []
        planned: list[SubGoal] = []
        for index, item in enumerate(payload["subgoals"], start=1):
            if not isinstance(item, dict):
                return []
            capability = str(item.get("capability", ""))
            if capability not in self.ontology.capabilities:
                return []
            slots = item.get("slots") if isinstance(item.get("slots"), dict) else {}
            depends_on = item.get("depends_on") if isinstance(item.get("depends_on"), list) else []
            planned.append(
                SubGoal(
                    id=f"g{index}",
                    capability=capability,
                    description=str(item.get("description") or capability),
                    intent=str(item.get("intent") or capability),
                    slots={str(key): value for key, value in slots.items()},
                    depends_on=[str(value) for value in depends_on],
                    branch=str(item.get("branch") or f"branch{index}"),
                )
            )
        return planned


def month_name(number: int) -> str:
    return calendar.month_name[number]
