from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

from fair_offline_assessor import Assessor
from fair_offline_assessor.models import AssessmentResult, MetricResult

from fair_assessment_proxy.plugins.fuji import cell_for
from fair_assessment_proxy.reporting import (
    CELLS,
    serialize_guidance,
    serialize_result,
)

FUJI_VERSION = "3.5.1"


def _outcome(earned: float, maximum: float) -> str:
    if earned <= 0:
        return "fail"
    return "pass" if earned >= maximum else "partial"


def _points(metric: MetricResult) -> tuple[float, float] | None:
    score = metric.score
    if score is None or not score.complete or not score.maximum:
        return None
    return score.observed_earned, score.maximum


def cells_from_metrics(metrics: Iterable[MetricResult]) -> dict[str, str]:
    totals: dict[str, tuple[float, float]] = {}
    for metric in metrics:
        cell = cell_for(metric.id)
        points = _points(metric)
        if cell in CELLS and points:
            earned, maximum = totals.get(cell, (0.0, 0.0))
            totals[cell] = (earned + points[0], maximum + points[1])
    return {
        cell: _outcome(*totals[cell]) if cell in totals else "indeterminate"
        for cell in CELLS
    }


def _guidance(result: AssessmentResult) -> list[dict[str, Any]]:
    names = {item["metric_identifier"]: item["metric_name"] for item in result.raw}
    entries = []
    for metric in result.metrics:
        points = _points(metric)
        outcome = _outcome(*points) if points else "indeterminate"
        messages = [
            test.message
            for test in result.tests
            if test.metric == metric.id and test.outcome != "pass"
        ]
        entries.append(
            {
                "assessor": "offline",
                "cell": cell_for(metric.id),
                "test": metric.id,
                "description": names.get(metric.id),
                "outcome": outcome,
                "message": None
                if outcome == "pass"
                else "; ".join(dict.fromkeys(messages)) or None,
                "guidance": None,
            }
        )
    return [serialize_guidance(entry) for entry in entries]


def _fuji_input(metadata: dict[str, Any]) -> dict[str, Any]:
    # F-UJI does not accept the DataCite API envelope.
    data = metadata.get("data")
    if isinstance(data, dict) and isinstance(data.get("attributes"), dict):
        return {
            "metadata": {**data["attributes"], "agency": "datacite"},
            "metadata_format": "datacite-json",
        }
    return {"metadata": metadata}


def assess_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Assess FAIR characteristics that can be observed without network access."""
    result = Assessor("FUJI", version=FUJI_VERSION).assess(**_fuji_input(metadata))
    row = SimpleNamespace(
        assessor="offline",
        assessor_version=result.profile.version,
        **cells_from_metrics(result.metrics),
    )
    return {
        **serialize_result(
            row, raw=result.model_dump(mode="json"), guidance=_guidance(result)
        ),
        "profile_ref": f"{result.profile.id}@{result.profile.version}",
    }
