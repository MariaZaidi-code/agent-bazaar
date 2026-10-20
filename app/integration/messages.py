"""Pure conversions between the app schemas and the knowledge-layer schemas.

The Client/Provider/Interface layer (``app.schemas``) and the knowledge layer
(``agent_bazaar``) describe the same things with different vocabularies:

* the app addresses a field by ``field_name`` and types it with
  ``ConceptSpec``; the knowledge layer addresses it by ``field_path`` and types
  it with ``FieldSpec`` and ``FieldMapping``;
* the app's correction carries the ``original_concept``, the knowledge layer's
  correction only carries the corrected concept;
* the app's concepts and units follow the local fallback ontology, the
  knowledge layer follows the RDF ontology in the knowledge graph.

Every helper below is side-effect free: it never touches the graph, the Mapper
or the disk. The alias tables live in :mod:`app.integration.canonical`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from agent_bazaar.messages.schema import CorrectionSubmit, FieldMapping, FieldSpec, MapResult
from app.integration.canonical import canonical_concept, canonical_unit
from app.schemas import ConceptSpec, CorrectionRequest, CorrectionResult, MapResultMessage

_UNSAFE_TOKEN = re.compile(r"[^A-Za-z0-9_]+")


def local_name(reference: str | None) -> str:
    """Return the local part of an IRI, a prefixed name or a plain concept name."""
    text = str(reference or "").strip()
    for separator in ("#", "/"):
        if separator in text:
            text = text.rsplit(separator, 1)[-1]
            break
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    return text


def field_name_from_path(path: str | None) -> str:
    """Return the field name encoded in a knowledge-layer field path."""
    return str(path or "").rsplit(".", 1)[-1]


def build_field_path(direction: str, name: str) -> str:
    """Build the knowledge-layer field path of a listed field.

    Listings submitted through the app carry no HTTP endpoint, so the path uses
    the ``{direction}.{name}`` convention of the knowledge layer without the
    ``{method}:{endpoint}`` part used by the ingestion layer.
    """
    token = _UNSAFE_TOKEN.sub("_", str(name or "").strip()).strip("_")
    return f"{direction}.{token or 'field'}"


def direction_of(path: str | None) -> str:
    """Return the direction encoded in a knowledge-layer field path."""
    return "input" if str(path or "").startswith("input.") else "output"


def field_type_for(declared: str | None, concept_data_type: str | None) -> str:
    """Translate an app datatype into a knowledge-layer field type.

    The app types a structured payload as ``object`` while the knowledge layer
    types the same field with the data type of the concept it maps to. Scalar
    datatypes are kept as they are so the Mapper can still reject a field
    whose type contradicts the concept.
    """
    text = str(declared or "").strip().lower()
    if text in ("", "object", "array"):
        return str(concept_data_type or "string")
    if text == "number":
        return "float"
    return text


def to_concept_specs(
    fields: Sequence[FieldMapping],
    *,
    direction: str | None = None,
    data_types: Mapping[str, str] | None = None,
) -> list[ConceptSpec]:
    """Convert knowledge-layer field mappings into app-level concept specs.

    ``direction`` keeps only the inputs or only the outputs. ``data_types``
    maps a concept name to its knowledge-layer data type and defaults to
    ``string`` for concepts that are not in the map.
    """
    specs: list[ConceptSpec] = []
    for field in fields:
        field_direction = str(getattr(field, "direction", "") or "") or direction_of(field.field_path)
        if direction is not None and field_direction != direction:
            continue
        concept = canonical_concept(local_name(getattr(field, "concept", "")))
        unit = canonical_unit(getattr(field, "unit", None))
        specs.append(
            ConceptSpec(
                concept=concept,
                name=field_name_from_path(field.field_path),
                unit=unit,
                datatype=(data_types or {}).get(concept, "string"),
                required=True,
            )
        )
    return specs


def to_canonical_specs(concepts: Sequence[ConceptSpec]) -> list[ConceptSpec]:
    """Rewrite app concept specs with the canonical concept and unit names."""
    return [
        ConceptSpec(
            concept=canonical_concept(concept.concept),
            name=concept.name,
            unit=canonical_unit(concept.unit),
            datatype=concept.datatype,
            required=concept.required,
            description=concept.description,
        )
        for concept in concepts
    ]


def concept_specs_to_field_specs(
    concepts: Sequence[ConceptSpec],
    *,
    direction: str = "output",
    data_types: Mapping[str, str] | None = None,
) -> list[FieldSpec]:
    """Convert app-level concept specs into knowledge-layer field specs.

    The concept of the app spec is kept in the description of the field so the
    Mapper can use the declared type as a hint. ``data_types`` maps a concept
    name to its knowledge-layer data type and is used for the fields the app
    types as a structured payload.
    """
    specs: list[FieldSpec] = []
    used: set[str] = set()
    for concept in concepts:
        name = concept.name or concept.concept
        path = build_field_path(direction, name)
        if path in used:
            suffix = 2
            while f"{path}-{suffix}" in used:
                suffix += 1
            path = f"{path}-{suffix}"
        used.add(path)
        canonical = canonical_concept(concept.concept)
        description = " ".join(part for part in (concept.description, concept.concept) if part)
        specs.append(
            FieldSpec(
                field_path=path,
                name=name,
                type=field_type_for(concept.datatype, (data_types or {}).get(canonical)),
                description=description,
                direction=direction,
                required=concept.required,
            )
        )
    return specs


def to_map_result_message(
    result: MapResult,
    tool_id: str,
    violations: list[str],
    *,
    data_types: Mapping[str, str] | None = None,
    extra_inputs: Sequence[ConceptSpec] = (),
    extra_outputs: Sequence[ConceptSpec] = (),
) -> MapResultMessage:
    """Translate a knowledge-layer mapping result into the app's map result.

    ``accepted`` is false as soon as one violation was reported. ``staged``
    keeps the contract of the stub Mapper: an accepted submission is recorded
    in the staging ledger of the adapter and can be inspected with
    ``staged()``. The extra inputs and outputs carry the fields whose concept
    is external to the knowledge layer and therefore could not be mapped.
    """
    accepted = not violations
    return MapResultMessage(
        sender="mapper",
        recipient="client",
        correlation_id=result.correlation_id,
        tool_id=tool_id,
        inputs=[
            *to_concept_specs(result.mappings, direction="input", data_types=data_types),
            *extra_inputs,
        ],
        outputs=[
            *to_concept_specs(result.mappings, direction="output", data_types=data_types),
            *extra_outputs,
        ],
        violations=list(violations),
        accepted=accepted,
        staged=accepted,
    )


def to_correction_result(
    correction_id: str,
    accepted: bool,
    staged: bool,
    violations: list[str],
    message: str,
) -> CorrectionResult:
    """Build the app's correction result from a knowledge-layer decision."""
    return CorrectionResult(
        correction_id=correction_id,
        accepted=accepted,
        staged=staged,
        violations=list(violations),
        message=message,
    )


def correction_request_to_submit(
    request: CorrectionRequest,
    *,
    field_path: str | None = None,
) -> CorrectionSubmit:
    """Translate an app correction request into a knowledge-layer submission.

    The app addresses a field by ``field_name`` while the knowledge layer
    addresses it by ``field_path``. The caller resolves the path from the tool
    record and passes it in; when no path can be resolved the ``field_name`` is
    used verbatim as the ``field_path``, which keeps the correction routable
    and lets the Mapper reject it when the field is unknown.

    The knowledge layer has no notion of the ``original_concept``, so it is
    appended to the note to keep the information available to the Mapper and
    to the auditors.
    """
    note = request.note
    if request.original_concept:
        note = f"{note} (original concept: {request.original_concept})".strip()
    return CorrectionSubmit(
        tool_id=request.tool_id,
        field_path=str(field_path or request.field_name),
        corrected_concept=canonical_concept(request.corrected_concept),
        corrected_unit=canonical_unit(request.corrected_unit),
        note=note,
    )
