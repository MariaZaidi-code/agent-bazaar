"""Unit families, units and deterministic conversions.

Single source of truth for units: the knowledge graph triples are generated from
this registry by ``units_graph()`` so code and graph can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph, Literal
from rdflib.namespace import RDF, RDFS

from agent_bazaar.ontology.ns import AB, unit_iri


@dataclass(frozen=True)
class UnitDef:
    local_name: str
    symbol: str
    family: str
    factor: float = 1.0
    offset: float = 0.0
    convertible: bool = True


UNIT_FAMILIES: dict[str, dict[str, object]] = {
    "TemperatureUnit": {
        "label": "Temperature",
        "canonical": "Celsius",
        "units": [
            UnitDef("Celsius", "C", "TemperatureUnit", factor=1.0, offset=0.0),
            UnitDef("Fahrenheit", "F", "TemperatureUnit", factor=5.0 / 9.0, offset=-32.0),
            UnitDef("Kelvin", "K", "TemperatureUnit", factor=1.0, offset=-273.15),
        ],
    },
    "LengthUnit": {
        "label": "Length",
        "canonical": "Metre",
        "units": [
            UnitDef("Metre", "m", "LengthUnit", factor=1.0),
            UnitDef("Kilometre", "km", "LengthUnit", factor=1000.0),
            UnitDef("Centimetre", "cm", "LengthUnit", factor=0.01),
            UnitDef("Mile", "mi", "LengthUnit", factor=1609.344),
            UnitDef("Foot", "ft", "LengthUnit", factor=0.3048),
        ],
    },
    "DurationUnit": {
        "label": "Duration",
        "canonical": "Second",
        "units": [
            UnitDef("Second", "s", "DurationUnit", factor=1.0),
            UnitDef("Millisecond", "ms", "DurationUnit", factor=0.001),
            UnitDef("Minute", "min", "DurationUnit", factor=60.0),
            UnitDef("Hour", "h", "DurationUnit", factor=3600.0),
            UnitDef("Day", "d", "DurationUnit", factor=86400.0),
        ],
    },
    "SpeedUnit": {
        "label": "Speed",
        "canonical": "MetrePerSecond",
        "units": [
            UnitDef("MetrePerSecond", "m/s", "SpeedUnit", factor=1.0),
            UnitDef("KilometrePerHour", "km/h", "SpeedUnit", factor=1.0 / 3.6),
            UnitDef("MilePerHour", "mph", "SpeedUnit", factor=0.44704),
            UnitDef("Knot", "kn", "SpeedUnit", factor=0.514444),
        ],
    },
    "MassUnit": {
        "label": "Mass",
        "canonical": "Kilogram",
        "units": [
            UnitDef("Kilogram", "kg", "MassUnit", factor=1.0),
            UnitDef("Gram", "g", "MassUnit", factor=0.001),
            UnitDef("Pound", "lb", "MassUnit", factor=0.45359237),
        ],
    },
    "PressureUnit": {
        "label": "Pressure",
        "canonical": "Hectopascal",
        "units": [
            UnitDef("Hectopascal", "hPa", "PressureUnit", factor=1.0),
            UnitDef("Pascal", "Pa", "PressureUnit", factor=0.01),
            UnitDef("Kilopascal", "kPa", "PressureUnit", factor=10.0),
            UnitDef("Millibar", "mbar", "PressureUnit", factor=1.0),
        ],
    },
    "PrecipitationUnit": {
        "label": "Precipitation depth",
        "canonical": "Millimetre",
        "units": [
            UnitDef("Millimetre", "mm", "PrecipitationUnit", factor=1.0),
            UnitDef("Inch", "in", "PrecipitationUnit", factor=25.4),
        ],
    },
    "PercentageUnit": {
        "label": "Percentage",
        "canonical": "Percent",
        "units": [UnitDef("Percent", "%", "PercentageUnit", factor=1.0)],
    },
    "AngleUnit": {
        "label": "Angle",
        "canonical": "Degree",
        "units": [
            UnitDef("Degree", "deg", "AngleUnit", factor=1.0),
            UnitDef("Radian", "rad", "AngleUnit", factor=57.29577951308232),
        ],
    },
    "AreaUnit": {
        "label": "Area",
        "canonical": "SquareKilometre",
        "units": [
            UnitDef("SquareKilometre", "km2", "AreaUnit", factor=1.0),
            UnitDef("SquareMetre", "m2", "AreaUnit", factor=1e-6),
            UnitDef("SquareMile", "mi2", "AreaUnit", factor=2.589988110336),
        ],
    },
    "CountUnit": {
        "label": "Count",
        "canonical": "Count",
        "units": [UnitDef("Count", "count", "CountUnit", factor=1.0)],
    },
    "RatingUnit": {
        "label": "Rating",
        "canonical": "Star",
        "units": [
            UnitDef("Star", "star", "RatingUnit", factor=1.0, convertible=False),
            UnitDef("Score", "score", "RatingUnit", factor=1.0, convertible=False),
        ],
    },
    "DataSizeUnit": {
        "label": "Data size",
        "canonical": "Byte",
        "units": [
            UnitDef("Byte", "B", "DataSizeUnit", factor=1.0),
            UnitDef("Kilobyte", "KB", "DataSizeUnit", factor=1024.0),
            UnitDef("Megabyte", "MB", "DataSizeUnit", factor=1024.0**2),
            UnitDef("Gigabyte", "GB", "DataSizeUnit", factor=1024.0**3),
        ],
    },
    "FrequencyUnit": {
        "label": "Frequency",
        "canonical": "Hertz",
        "units": [
            UnitDef("Hertz", "Hz", "FrequencyUnit", factor=1.0),
            UnitDef("Kilohertz", "kHz", "FrequencyUnit", factor=1000.0),
            UnitDef("Megahertz", "MHz", "FrequencyUnit", factor=1_000_000.0),
        ],
    },
    "CurrencyUnit": {
        "label": "Currency",
        "canonical": "USD",
        "units": [
            UnitDef("USD", "USD", "CurrencyUnit", convertible=False),
            UnitDef("EUR", "EUR", "CurrencyUnit", convertible=False),
            UnitDef("GBP", "GBP", "CurrencyUnit", convertible=False),
            UnitDef("PKR", "PKR", "CurrencyUnit", convertible=False),
            UnitDef("JPY", "JPY", "CurrencyUnit", convertible=False),
        ],
    },
}

_UNIT_INDEX: dict[str, UnitDef] = {}
for _family, _spec in UNIT_FAMILIES.items():
    for _unit in _spec["units"]:  # type: ignore[union-attr]
        _UNIT_INDEX[_unit.local_name] = _unit


def unit_def(unit_name_or_iri: str) -> UnitDef | None:
    name = unit_name_or_iri.rsplit("#", 1)[-1]
    return _UNIT_INDEX.get(name)


def family_of(unit_name_or_iri: str) -> str | None:
    definition = unit_def(unit_name_or_iri)
    return definition.family if definition else None


def units_in_family(family: str) -> list[UnitDef]:
    spec = UNIT_FAMILIES.get(family)
    return list(spec["units"]) if spec else []  # type: ignore[arg-type]


def compatible_units(a: str, b: str) -> bool:
    return family_of(a) is not None and family_of(a) == family_of(b)


def _to_canonical(unit_name: str, value: float) -> float:
    definition = unit_def(unit_name)
    if definition is None:
        raise ValueError(f"unknown unit {unit_name!r}")
    if not definition.convertible:
        raise ValueError(f"unit {unit_name!r} is not convertible without a live rate")
    return (value + definition.offset) * definition.factor


def _from_canonical(unit_name: str, value: float) -> float:
    definition = unit_def(unit_name)
    if definition is None:
        raise ValueError(f"unknown unit {unit_name!r}")
    return value / definition.factor - definition.offset


def convert(value: float, from_unit: str, to_unit: str) -> float:
    if family_of(from_unit) != family_of(to_unit):
        raise ValueError(f"incompatible unit families: {from_unit!r} vs {to_unit!r}")
    if from_unit == to_unit:
        return value
    canonical = _to_canonical(from_unit, value)
    return _from_canonical(to_unit, canonical)


def units_graph() -> Graph:
    graph = Graph()
    for family_name, spec in UNIT_FAMILIES.items():
        family_iri = AB[family_name]
        graph.add((family_iri, RDF.type, AB.UnitFamily))
        graph.add((family_iri, RDFS.label, Literal(str(spec["label"]))))
        graph.add((family_iri, AB.familyCode, Literal(family_name)))
        for definition in spec["units"]:  # type: ignore[union-attr]
            iri = unit_iri(definition.local_name)  # type: ignore[union-attr]
            graph.add((iri, RDF.type, AB.Unit))
            graph.add((iri, RDFS.label, Literal(definition.local_name)))  # type: ignore[union-attr]
            graph.add((iri, AB.unitSymbol, Literal(definition.symbol)))  # type: ignore[union-attr]
            graph.add((iri, AB.unitOfFamily, family_iri))
    return graph
