"""
.. module:: orchestration.test.triage.factories.infra_flake_classifier
    :synopsis: InfraFlakeClassifier — reference triage classifier.

The reference classifier maps :class:`TriageSignals` to the M1
class set:

* ``infra_flake`` when ``signals.flake_class == "flaky"`` and
  the failure was not present in the prior known-issue
  signature cache.
* ``known_issue`` when ``signals.has_known_signature is True``.
* ``new_bug`` when the failure has a non-empty
  ``stack_signature_sha256`` and no known-issue match.
* ``other`` otherwise.

The thresholds and the signature-cache lookup are M2 — M1 honors
the ``has_known_signature`` boolean the caller already
populated.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.orchestration.test.triage.factories.classifier_protocol import (
    TriageClassifierDecision,
    TriageClassifierProtocol,
)
from ccai.pychestrate.webservice.orchestration.test.triage.models import (
    TriageClass,
)


INFRA_FLAKE_CLASSIFIER_NAME: str = "infra-flake"


class InfraFlakeClassifier(TriageClassifierProtocol):
    """
        Reference triage classifier.
    """

    factory_protocol_name: str = "triage_classifier"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def classifier_name(cls) -> str:
        rtnval = INFRA_FLAKE_CLASSIFIER_NAME
        return rtnval

    @classmethod
    def classify(cls, *, signals) -> TriageClassifierDecision:
        if signals.has_known_signature is True:
            rtnval = TriageClassifierDecision(
                classification=TriageClass.KNOWN_ISSUE,
                confidence=0.85,
                rationale="signature matches a known known-issue cache hit",
            )
            return rtnval

        flake_class = (signals.flake_class or "").lower()
        if flake_class == "flaky":
            rtnval = TriageClassifierDecision(
                classification=TriageClass.INFRA_FLAKE,
                confidence=0.7,
                rationale="flake-tracking classified the test as flaky",
            )
            return rtnval

        if (
            signals.stack_signature_sha256 is not None
            and len(signals.stack_signature_sha256) > 0
        ):
            rtnval = TriageClassifierDecision(
                classification=TriageClass.NEW_BUG,
                confidence=0.5,
                rationale="non-empty stack signature with no known-issue match",
            )
            return rtnval

        rtnval = TriageClassifierDecision(
            classification=TriageClass.OTHER,
            confidence=0.2,
            rationale="no signal matched the M1 rules",
        )
        return rtnval
