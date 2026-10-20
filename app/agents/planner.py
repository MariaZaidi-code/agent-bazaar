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
            "country facts, public holidays, research papers, the sample university "
            "database, or an uploaded document."
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
