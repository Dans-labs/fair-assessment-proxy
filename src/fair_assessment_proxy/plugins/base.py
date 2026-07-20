from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from fair_assessment_proxy.models import AssessmentMode, AssessorResult


@dataclass
class AssessmentContext:
    pid: str
    mode: AssessmentMode


class AssessorPlugin(ABC):
    """
    Interface that every FAIR assessment backend must implement.
    """

    def __init__(self, assessor_id: str, config: dict[str, Any]):
        self.assessor_id = assessor_id
        self.config = config
        self.name = config.get("name", assessor_id)

    @abstractmethod
    async def assess(self, context: AssessmentContext) -> AssessorResult:
        """
        Run the assessment backend and return a standard result object.
        """
        raise NotImplementedError

    def is_enabled(self) -> bool:
        return bool(self.config.get("enabled", False))
