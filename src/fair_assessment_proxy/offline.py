import re
from typing import Any
from urllib.parse import urlparse

from fair_assessment_proxy.reporting import (
    CELLS,
    PARENTS,
    combine,
    scores_for,
    serialize_guidance,
)


OFFLINE_ASSESSOR_VERSION = "1"

FIELD_ALIASES = {
    "identifier": {"id", "identifier", "identifiers", "doi"},
    "title": {"name", "title", "titles"},
    "description": {"abstract", "description", "descriptions"},
    "creator": {"author", "authors", "creator", "creators"},
    "publisher": {"publisher"},
    "date": {
        "created",
        "date",
        "datecreated",
        "datemodified",
        "datepublished",
        "dates",
        "issued",
        "modified",
        "publicationyear",
    },
    "keywords": {"keyword", "keywords", "subject", "subjects"},
    "license": {"license", "rights", "rightslist"},
    "relations": {
        "citation",
        "haspart",
        "ispartof",
        "relatedidentifier",
        "relatedidentifiers",
        "relatedresource",
        "relatedresources",
        "relation",
        "relations",
        "sameas",
        "subjectof",
    },
    "provenance": {
        "fundingreference",
        "fundingreferences",
        "history",
        "provenance",
        "wasgeneratedby",
    },
    "standard": {
        "conformsto",
        "metadatastandard",
        "schemaversion",
    },
    "context": {"context"},
    "type": {"type"},
}

QUALIFIED_RELATIONS = {
    "citation",
    "haspart",
    "ispartof",
    "sameas",
    "subjectof",
}

DESCRIPTIONS = {
    "f1": "Metadata contains a globally unique identifier.",
    "f2": "Metadata contains enough descriptive fields for discovery and reuse.",
    "f3": "The data identifier is included in the metadata.",
    "f4": "The resource is registered or indexed in a searchable service.",
    "a1": "Access conditions are derived from the A1 refinements.",
    "a1_1": "The resource can be retrieved using an open standard protocol.",
    "a1_2": "The access protocol supports authentication and authorization.",
    "a2": "Metadata remains accessible if the data is no longer available.",
    "i1": "Metadata uses a formal, machine-readable representation.",
    "i2": "Metadata uses vocabularies that follow FAIR principles.",
    "i3": "Metadata contains qualified references to related resources.",
    "r1": "Reuse information is derived from the R1 refinements.",
    "r1_1": "Metadata contains a clear data usage licence.",
    "r1_2": "Metadata contains provenance information.",
    "r1_3": "Metadata identifies a community standard or schema.",
}

UNMEASURED_MESSAGES = {
    "f4": "Search-engine or registry indexing cannot be verified offline.",
    "a1_1": "Protocol retrieval cannot be verified without accessing the resource.",
    "a1_2": "Authentication behavior cannot be verified without accessing the service.",
    "a2": "Long-term metadata availability cannot be verified from one metadata record.",
    "i2": "Vocabulary FAIRness requires checking external vocabulary services.",
}


def _key_name(key: Any) -> str:
    value = str(key).strip().casefold().lstrip("@")
    value = re.split(r"[/#:]", value)[-1]
    return re.sub(r"[^a-z0-9]", "", value)


def _root(metadata: dict[str, Any]) -> dict[str, Any]:
    data = metadata.get("data")
    if isinstance(data, dict) and isinstance(data.get("attributes"), dict):
        root = dict(data["attributes"])
        if data.get("id") and not any(
            _key_name(key) in FIELD_ALIASES["identifier"] for key in root
        ):
            root["identifier"] = data["id"]
        return root

    graph = metadata.get("@graph")
    if isinstance(graph, list):
        nodes = [node for node in graph if isinstance(node, dict)]
        if nodes:
            root = nodes[0]
            for node in nodes:
                types = _texts(node.get("@type"))
                if any("dataset" in value.casefold() for value in types):
                    root = node
                    break
            root = dict(root)
            if "@context" not in root and "@context" in metadata:
                root["@context"] = metadata["@context"]
            return root

    return metadata


def _field_items(root: dict[str, Any], field: str) -> list[tuple[str, Any]]:
    aliases = FIELD_ALIASES[field]
    return [
        (_key_name(key), value)
        for key, value in root.items()
        if _key_name(key) in aliases and _present(value)
    ]


def _values(root: dict[str, Any], field: str) -> list[Any]:
    return [value for _, value in _field_items(root, field)]


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, dict):
        return [text for nested in value.values() for text in _texts(nested)]
    if isinstance(value, (list, tuple, set)):
        return [text for nested in value for text in _texts(nested)]
    return []


def _field_texts(root: dict[str, Any], field: str) -> list[str]:
    return [text for value in _values(root, field) for text in _texts(value)]


def _http_url(value: str) -> bool:
    candidate = value.strip()
    if any(character.isspace() for character in candidate):
        return False
    try:
        parsed = urlparse(candidate)
        _ = parsed.port  # Accessing the property validates the port.
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def _global_identifier(value: str) -> bool:
    candidate = value.strip()
    lowered = candidate.casefold()
    if re.fullmatch(r"(?:doi:|https?://doi\.org/)?10\.\d{4,9}/\S+", lowered):
        return True
    if lowered.startswith(("ark:/", "hdl:", "urn:", "uuid:")):
        return True
    return _http_url(candidate)


def _richness(root: dict[str, Any]) -> tuple[str, str]:
    fields = ("title", "description", "creator", "publisher", "date", "keywords")
    present = [field for field in fields if _values(root, field)]
    count = len(present)
    outcome = "pass" if count >= 5 else "partial" if count >= 3 else "fail"
    return outcome, f"Found {count} of 6 core descriptive field groups."


def _formal_representation(root: dict[str, Any]) -> tuple[str, str]:
    declared = bool(
        _values(root, "context")
        or _values(root, "standard")
        or any(":" in str(key) or str(key).startswith("http") for key in root)
    )
    if declared:
        return "pass", "A metadata context, schema, or namespace is declared."
    return "partial", "The JSON is machine-readable but declares no context or schema."


def _qualified_relations(root: dict[str, Any]) -> tuple[str, str]:
    items = _field_items(root, "relations")
    if not items:
        return "fail", "No related-resource references were found."

    inherently_qualified = any(key in QUALIFIED_RELATIONS for key, _ in items)
    relation_types = {
        "relationtype",
        "relationship",
        "relationshiptype",
    }
    explicitly_qualified = any(
        isinstance(value, dict)
        and any(_key_name(key) in relation_types for key in value)
        or isinstance(value, list)
        and any(
            isinstance(item, dict)
            and any(_key_name(key) in relation_types for key in item)
            for item in value
        )
        for _, value in items
    )
    if inherently_qualified or explicitly_qualified:
        return "pass", "Found a related resource with a declared relationship."
    return "partial", "Related resources are present without relationship types."


def _license(root: dict[str, Any]) -> tuple[str, str]:
    values = _field_texts(root, "license")
    if not values:
        return "fail", "No licence information was found."
    if any(_http_url(value) for value in values):
        return "pass", "Found a licence URL; its contents were not verified offline."
    return "partial", "Licence text is present without a parseable HTTP(S) URL."


def _provenance(root: dict[str, Any]) -> tuple[str, str]:
    if _values(root, "provenance"):
        return "pass", "Explicit provenance information is present."

    creator = bool(_values(root, "creator"))
    publisher = bool(_values(root, "publisher"))
    date = bool(_values(root, "date"))
    if creator and publisher and date:
        return "pass", "Creator, publisher, and date provenance are present."
    if creator and (publisher or date):
        return "partial", "Some creator, publisher, or date provenance is missing."
    return "fail", "Insufficient provenance information was found."


def _standard(root: dict[str, Any]) -> tuple[str, str]:
    if _values(root, "standard"):
        return "pass", "A metadata standard or schema is declared."
    if _values(root, "context") or _values(root, "type"):
        return "partial", "A metadata context or type is present without conformsTo."
    return "fail", "No metadata standard or schema was declared."


def _guidance(cells: dict[str, str], messages: dict[str, str]) -> list[dict[str, Any]]:
    entries = []
    for cell in CELLS:
        outcome = cells[cell]
        message = messages.get(cell) or UNMEASURED_MESSAGES.get(cell)
        suggestion = None
        if outcome in {"fail", "partial"}:
            suggestion = f"Improve metadata for {cell.upper()}: {DESCRIPTIONS[cell]}"
        entries.append(
            {
                "assessor": "offline",
                "cell": cell,
                "test": f"offline:{cell}",
                "description": DESCRIPTIONS[cell],
                "outcome": outcome,
                "message": message,
                "guidance": suggestion,
            }
        )
    return [serialize_guidance(entry) for entry in entries]


def assess_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Assess FAIR characteristics that can be observed without network access."""
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a JSON object")

    root = _root(metadata)
    identifier_values = _field_texts(root, "identifier")
    f1 = (
        "pass"
        if any(_global_identifier(value) for value in identifier_values)
        else "partial"
        if identifier_values
        else "fail"
    )
    f1_message = (
        "Found a globally unique identifier."
        if f1 == "pass"
        else "Found only a local identifier."
        if f1 == "partial"
        else "No identifier was found."
    )
    f2, f2_message = _richness(root)
    f3 = "pass" if identifier_values else "fail"
    i1, i1_message = _formal_representation(root)
    i3, i3_message = _qualified_relations(root)
    r1_1, r1_1_message = _license(root)
    r1_2, r1_2_message = _provenance(root)
    r1_3, r1_3_message = _standard(root)

    cells = dict.fromkeys(CELLS, "indeterminate")
    cells.update(
        {
            "f1": f1,
            "f2": f2,
            "f3": f3,
            "i1": i1,
            "i3": i3,
            "r1_1": r1_1,
            "r1_2": r1_2,
            "r1_3": r1_3,
        }
    )
    for parent, children in PARENTS.items():
        cells[parent] = combine([cells[child] for child in children])

    scores, scored = scores_for(cells)
    messages = {
        "f1": f1_message,
        "f2": f2_message,
        "f3": (
            "The identifier is included in the metadata."
            if f3 == "pass"
            else "The metadata does not include a data identifier."
        ),
        "i1": i1_message,
        "i3": i3_message,
        "r1_1": r1_1_message,
        "r1_2": r1_2_message,
        "r1_3": r1_3_message,
        "a1": "No accessibility refinements are measurable offline.",
        "r1": "Derived from the licence, provenance, and standards checks.",
    }

    return {
        "assessor": "offline",
        "status": "completed",
        "assessor_version": OFFLINE_ASSESSOR_VERSION,
        "profile_ref": None,
        "error": None,
        "cells": cells,
        "scores": scores,
        "scored": scored,
        "derived": sorted(PARENTS),
        "unmapped": [],
        "guidance": _guidance(cells, messages),
    }
