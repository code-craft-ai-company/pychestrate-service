"""
.. module:: orchestration.test.triage.factories.classifier_protocol
    :synopsis: ``triage_classifier`` factory contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)
from ccai.pychestrate.webservice.orchestration.test.triage.models import (
    TriageClass,
)


@dataclass(frozen=True)
class TriageClassifierDecision:
    """
        Classifier output. Pure value — no DB row.

        :param classification: Resolved :class:`TriageClass`.
        :param confidence: 0..1; higher = stronger.
        :param rationale: Human-readable rationale.
    """
    classification: TriageClass
    confidence: float
    rationale: str


class TriageClassifierProtocol(FactoryProtocolBase):
    """
        Contract for ``triage_classifier`` extensions. A
        classifier consumes :class:`TriageSignals` (frozen
        dataclass) and produces a :class:`TriageClassifierDecision`.
    """

    factory_protocol_name: str = "triage_classifier"
    protocol_schema_version: int = 1

    @classmethod
    def classifier_name(cls) -> str:
        raise NotImplementedError("Subclasses must implement classifier_name")

    @classmethod
    def classify(
            cls,
            *,
            signals  # TriageSignals — avoid circular import
        ) -> TriageClassifierDecision:
        raise NotImplementedError("Subclasses must implement classify")
