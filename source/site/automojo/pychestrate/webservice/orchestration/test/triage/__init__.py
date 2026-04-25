"""
.. module:: orchestration.test.triage
    :synopsis: 6-triage-bug-linking — failure classification + tracker linking.

Public surface:

* :class:`TriageCase`, :class:`TriageCaseLedger`,
  :class:`TriageClass` — persistence + enum.
* :class:`TriageCaseView`, :class:`TriageSignals` — IO shapes.
* :func:`open_case`, :func:`reclassify_case`,
  :func:`link_ticket`, :func:`get_case`,
  :func:`list_cases_for_run`, :func:`compute_stack_signature`.
* :class:`BugTrackerDriverProtocol` factory contract +
  reference :class:`NullBugTrackerDriver`.
* :class:`TriageClassifierProtocol` factory contract +
  reference :class:`InfraFlakeClassifier`.
* :class:`TriageEventTopics`.
* Errors: :class:`TriageError`, :class:`TriageCaseNotFoundError`,
  :class:`TriageClassifierNotFoundError`,
  :class:`TriageStackSignatureInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.test.triage.errors import (
    TriageCaseNotFoundError,
    TriageClassifierNotFoundError,
    TriageError,
    TriageStackSignatureInvalidError,
)
from automojo.pychestrate.webservice.orchestration.test.triage.events import (
    TriageEventTopics,
)
from automojo.pychestrate.webservice.orchestration.test.triage.factories.classifier_protocol import (
    TriageClassifierDecision,
    TriageClassifierProtocol,
)
from automojo.pychestrate.webservice.orchestration.test.triage.factories.infra_flake_classifier import (
    InfraFlakeClassifier,
)
from automojo.pychestrate.webservice.orchestration.test.triage.factories.null_tracker_driver import (
    NullBugTrackerDriver,
)
from automojo.pychestrate.webservice.orchestration.test.triage.factories.tracker_protocol import (
    BugTrackerDriverProtocol,
    TrackerLink,
)
from automojo.pychestrate.webservice.orchestration.test.triage.models import (
    TriageCase,
    TriageCaseLedger,
    TriageClass,
)
from automojo.pychestrate.webservice.orchestration.test.triage.service import (
    TriageCaseView,
    TriageSignals,
    compute_stack_signature,
    get_case,
    link_ticket,
    list_cases_for_run,
    open_case,
    reclassify_case,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree triage classifier + tracker driver
        reference implementations.
    """
    register_factory_implementation(implementation=InfraFlakeClassifier)
    register_factory_implementation(implementation=NullBugTrackerDriver)
    return
