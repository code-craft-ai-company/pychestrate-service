"""
.. module:: orchestration.test.flake.factories.window_ratio_classifier
    :synopsis: WindowRatioClassifier — reference flake classifier.

Decision rules (M1):

* < ``min_samples`` rows  → ``insufficient_data``.
* All recent samples PASS → ``stable``.
* No PASS in the recent ``broken_window`` rows → ``broken``.
* >= ``flaky_transition_min`` PASS↔FAIL transitions in the
  window → ``flaky``.
* Otherwise → ``intermittent``.

The window size, broken window length, and transition threshold
are class attributes so subclasses (or test-only overrides) can
shift the thresholds without copying the algorithm.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.orchestration.test.flake.factories.classifier_protocol import (
    FlakeClassificationDecision,
    FlakeClassifierProtocol,
    FlakeWindowConfig,
)
from automojo.pychestrate.webservice.orchestration.test.flake.models import (
    FlakeClass,
    Outcome,
)


WINDOW_RATIO_CLASSIFIER_NAME: str = "window-ratio"
WINDOW_RATIO_CLASSIFIER_VERSION: str = "1.0.0"


class WindowRatioClassifier(FlakeClassifierProtocol):
    """
        Reference window-ratio classifier.
    """

    factory_protocol_name: str = "flake_classifier"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    MAX_WINDOW_SIZE: int = 20
    MIN_SAMPLES: int = 3
    BROKEN_WINDOW: int = 5
    FLAKY_TRANSITION_MIN: int = 2

    @classmethod
    def classifier_name(cls) -> str:
        rtnval = WINDOW_RATIO_CLASSIFIER_NAME
        return rtnval

    @classmethod
    def classifier_version(cls) -> str:
        rtnval = WINDOW_RATIO_CLASSIFIER_VERSION
        return rtnval

    @classmethod
    def window_config(cls) -> FlakeWindowConfig:
        rtnval = FlakeWindowConfig(
            max_window_size=cls.MAX_WINDOW_SIZE,
            min_samples=cls.MIN_SAMPLES,
        )
        return rtnval

    @classmethod
    def classify(
            cls,
            *,
            history
        ) -> FlakeClassificationDecision:
        samples = list(history.outcomes)
        sample_count = len(samples)
        if sample_count < cls.MIN_SAMPLES:
            rtnval = FlakeClassificationDecision(
                classification=FlakeClass.INSUFFICIENT_DATA,
                rationale_tag="below-min-samples",
            )
            return rtnval

        # Samples are newest-first; the broken-window check uses
        # the most recent ``BROKEN_WINDOW`` rows.
        recent = samples[: cls.BROKEN_WINDOW]
        all_pass_in_window = all(
            sample.outcome == Outcome.PASS for sample in samples
        )
        if all_pass_in_window is True:
            rtnval = FlakeClassificationDecision(
                classification=FlakeClass.STABLE,
                rationale_tag="all-pass-in-window",
            )
            return rtnval

        any_pass_recent = any(
            sample.outcome == Outcome.PASS for sample in recent
        )
        if any_pass_recent is False:
            rtnval = FlakeClassificationDecision(
                classification=FlakeClass.BROKEN,
                rationale_tag="no-pass-in-broken-window",
            )
            return rtnval

        transitions = 0
        previous_status: str = ""
        for sample in samples:
            current_status = "pass" if sample.outcome == Outcome.PASS else "fail"
            if previous_status != "" and current_status != previous_status:
                transitions = transitions + 1
            previous_status = current_status
        if transitions >= cls.FLAKY_TRANSITION_MIN:
            rtnval = FlakeClassificationDecision(
                classification=FlakeClass.FLAKY,
                rationale_tag="transitions-{}".format(transitions),
            )
            return rtnval

        rtnval = FlakeClassificationDecision(
            classification=FlakeClass.INTERMITTENT,
            rationale_tag="single-fail-tail",
        )
        return rtnval
