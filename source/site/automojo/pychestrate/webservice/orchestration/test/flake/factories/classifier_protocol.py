"""
.. module:: orchestration.test.flake.factories.classifier_protocol
    :synopsis: ``flake_classifier`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)
from automojo.pychestrate.webservice.orchestration.test.flake.models import (
    FlakeClass,
)


@dataclass(frozen=True)
class FlakeWindowConfig:
    """
        Lookback configuration declared by a classifier.

        :param max_window_size: Maximum number of recent samples
                                the classifier wants surfaced.
        :param min_samples: Minimum number of samples below
                            which the classifier MUST return
                            ``insufficient_data``.
    """
    max_window_size: int
    min_samples: int


@dataclass(frozen=True)
class FlakeClassificationDecision:
    """
        Classifier output. Pure value — no DB row.

        :param classification: Resolved :class:`FlakeClass`.
        :param rationale_tag: Stable, human-readable label that
                              ops can grep on.
    """
    classification: FlakeClass
    rationale_tag: str


class FlakeClassifierProtocol(FactoryProtocolBase):
    """
        Contract for ``flake_classifier`` extensions. Classifiers
        are pure functions over a per-test history window; the
        framework owns the registry, scheduling, and ledger.
    """

    factory_protocol_name: str = "flake_classifier"
    protocol_schema_version: int = 1

    @classmethod
    def classifier_name(cls) -> str:
        """
            Stable identifier the
            :func:`classify_for_test_case` service uses to
            persist alongside the classification.
        """
        raise NotImplementedError("Subclasses must implement classifier_name")

    @classmethod
    def classifier_version(cls) -> str:
        """
            Semver string. Bumped whenever the implementation's
            decision surface changes in a way that would warrant
            re-classifying historical rows.
        """
        raise NotImplementedError("Subclasses must implement classifier_version")

    @classmethod
    def window_config(cls) -> FlakeWindowConfig:
        """
            Return the classifier's window preferences.
        """
        raise NotImplementedError("Subclasses must implement window_config")

    @classmethod
    def classify(
            cls,
            *,
            history  # TestHistoryWindow — avoid circular import
        ) -> FlakeClassificationDecision:
        """
            Pure function over ``history`` → decision.
        """
        raise NotImplementedError("Subclasses must implement classify")
