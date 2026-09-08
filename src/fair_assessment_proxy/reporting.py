CELLS = (
    "f1",
    "f2",
    "f3",
    "f4",
    "a1",
    "a1_1",
    "a1_2",
    "a2",
    "i1",
    "i2",
    "i3",
    "r1",
    "r1_1",
    "r1_2",
    "r1_3",
)

PRINCIPLE_CELLS = {
    "f": ("f1", "f2", "f3", "f4"),
    "a": ("a1", "a1_1", "a1_2", "a2"),
    "i": ("i1", "i2", "i3"),
    "r": ("r1", "r1_1", "r1_2", "r1_3"),
}

DERIVED = {"a1", "r1"}
PARENTS = {
    "a1": ("a1_1", "a1_2"),
    "r1": ("r1_1", "r1_2", "r1_3"),
}
POINTS = {"pass": 100.0, "partial": 50.0, "fail": 0.0}
_RAW_MISSING = object()


def outcome_value(value):
    value = getattr(value, "value", value)
    return value if value in POINTS else "indeterminate"


def cells_for(row):
    cells = {cell: outcome_value(getattr(row, cell)) for cell in CELLS}

    for parent, refinements in PARENTS.items():
        cells[parent] = combine([cells[cell] for cell in refinements])

    return cells


def scores_for(cells):
    scores = {}
    scored = {}

    for principle, members in PRINCIPLE_CELLS.items():
        points = [
            POINTS[cells[cell]]
            for cell in members
            if cell not in DERIVED and cells[cell] != "indeterminate"
        ]
        scores[principle] = round(sum(points) / len(points), 1) if points else None
        scored[principle] = len(points)

    available = [score for score in scores.values() if score is not None]
    scores["overall"] = (
        round(sum(available) / len(available), 1) if available else None
    )
    scored["overall"] = sum(scored.values())

    return scores, scored


def combine(outcomes):
    measured = [outcome for outcome in outcomes if outcome != "indeterminate"]

    if not measured:
        return "indeterminate"
    if all(outcome == "pass" for outcome in measured):
        return "pass"
    if any(outcome == "fail" for outcome in measured):
        return "fail"
    return "partial"


def serialize_result(row, raw=_RAW_MISSING):
    cells = cells_for(row)
    scores, scored = scores_for(cells)
    result = {
        "assessor": row.assessor,
        "status": "completed",
        "assessor_version": row.assessor_version,
        "profile_ref": None,
        "error": None,
        "cells": cells,
        "scores": scores,
        "scored": scored,
        "derived": sorted(DERIVED),
        "unmapped": [],
    }

    if raw is not _RAW_MISSING:
        result["raw"] = raw

    return result
