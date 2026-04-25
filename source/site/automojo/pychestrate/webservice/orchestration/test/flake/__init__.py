"""
.. module:: orchestration.test.flake
    :synopsis: 6-flake-tracking — per-test outcome ingest + classification.

Public surface:

* :class:`TestOutcome`, :class:`FlakeClassification`,
  :class:`FlakeQuarantineLedger`, :class:`Outcome`,
  :class:`FlakeClass`, :class:`QuarantineAction` — persistence
  rows + enums.
* :class:`OutcomeSample`, :class:`TestHistoryWindow`,
  :class:`FlakeClassificationView` — IO shapes.
* :func:`record_outcome`, :func:`classify_for_test_case`,
  :func:`set_quarantine`, :func:`clear_quarantine`,
  :func:`list_history_for_test_case`,
  :func:`get_classification`.
* :class:`FlakeClassifierProtocol` factory contract +
  reference :class:`WindowRatioClassifier`.
* :class:`FlakeEventTopics`.
* Errors: :class:`FlakeError`,
  :class:`FlakeClassificationNotFoundError`,
  :class:`FlakeClassifierNotFoundError`,
  :class:`OutcomeIdentityInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.test.flake.errors import (
    FlakeClassificationNotFoundError,
    FlakeClassifierNotFoundError,
    FlakeError,
    OutcomeIdentityInvalidError,
)
from automojo.pychestrate.webservice.orchestration.test.flake.events import (
    FlakeEventTopics,
)
from automojo.pychestrate.webservice.orchestration.test.flake.factories.classifier_protocol import (
    FlakeClassifierProtocol,
    FlakeClassificationDecision,
    FlakeWindowConfig,
)
from automojo.pychestrate.webservice.orchestration.test.flake.factories.window_ratio_classifier import (
    WindowRatioClassifier,
)
from automojo.pychestrate.webservice.orchestration.test.flake.models import (
    FlakeClass,
    FlakeClassification,
    FlakeQuarantineLedger,
    Outcome,
    QuarantineAction,
    TestOutcome,
)
from automojo.pychestrate.webservice.orchestration.test.flake.service import (
    FlakeClassificationView,
    OutcomeSample,
    TestHistoryWindow,
    classify_for_test_case,
    clear_quarantine,
    get_classification,
    list_history_for_test_case,
    record_outcome,
    set_quarantine,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`WindowRatioClassifier` reference
        implementation.
    """
    register_factory_implementation(implementation=WindowRatioClassifier)
    return
