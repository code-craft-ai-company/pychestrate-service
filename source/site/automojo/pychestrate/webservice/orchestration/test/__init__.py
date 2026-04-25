"""
.. module:: orchestration.test
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Test orchestration plane — catalog, orchestrator, live-run view.

.. moduleauthor:: Automation Mojo LLC

Sub-packages:

- ``orchestration.test.catalog`` — test-suite registry
  (``6-test-catalog``).
- ``orchestration.test`` (this package itself) —
  :class:`TestOrchestrator` (``6-test-orchestration``).
- ``orchestration.test.live`` — live-run-view SSE relay
  (``6-live-run-view``).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.test.errors import (
    CapabilityMismatchError,
    DispatchFailedError,
    TestOrchestrationError,
    TestRunNotFoundError,
)
from automojo.pychestrate.webservice.orchestration.test.factories.testbase_runner import (
    TestbaseRunnerKind,
)
from automojo.pychestrate.webservice.orchestration.test.models import (
    TestRun,
    TestRunState,
)
from automojo.pychestrate.webservice.orchestration.test.orchestrator import (
    TestOrchestrator,
    TriggerRunOutcome,
    TriggerRunRequest,
)


def register_builtin_extensions() -> None:
    """
        Register Phase-3 Layer-6 in-tree factories:
        :class:`TestbaseRunnerKind` under ``test_runner_kind`` and
        :class:`TestbaseProjectImporter` under
        ``test_catalog_importer``.
    """
    from automojo.pychestrate.webservice.orchestration.test.catalog.factories.testbase_project import (
        TestbaseProjectImporter,
    )
    register_factory_implementation(implementation=TestbaseRunnerKind)
    register_factory_implementation(implementation=TestbaseProjectImporter)
    return
