"""
.. module:: orchestration.infra.drift
    :synopsis: 6-drift-detection — periodic drift checks on environments.

Public surface:

* :class:`DriftSchedule`, :class:`DriftRun`,
  :class:`DriftTickLedger`, :class:`DriftRunState`,
  :class:`DriftTriggerKind` — persistence + enums.
* :class:`DriftScheduleView`, :class:`DriftRunView`,
  :class:`DriftReport`, :class:`DriftTickResult` — IO shapes.
* :func:`set_schedule`, :func:`get_schedule`,
  :func:`disable_schedule`, :func:`run_now`,
  :func:`record_tick`, :func:`ingest_report`,
  :func:`get_drift_run`,
  :func:`list_drift_runs_for_environment`.
* :class:`DriftCheckerProtocol` factory contract +
  reference :class:`TerraformDriftChecker`.
* :class:`DriftEventTopics`.
* Errors: :class:`DriftError`,
  :class:`DriftScheduleNotFoundError`,
  :class:`DriftRunNotFoundError`,
  :class:`DriftCheckerUnknownError`,
  :class:`DriftScheduleInvalidError`,
  :class:`DriftTickAlreadyRecordedError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.infra.drift.errors import (
    DriftCheckerUnknownError,
    DriftError,
    DriftRunNotFoundError,
    DriftScheduleInvalidError,
    DriftScheduleNotFoundError,
    DriftTickAlreadyRecordedError,
)
from automojo.pychestrate.webservice.orchestration.infra.drift.events import (
    DriftEventTopics,
)
from automojo.pychestrate.webservice.orchestration.infra.drift.factories.checker_protocol import (
    DriftCheckerProtocol,
)
from automojo.pychestrate.webservice.orchestration.infra.drift.factories.terraform_checker import (
    TerraformDriftChecker,
)
from automojo.pychestrate.webservice.orchestration.infra.drift.models import (
    DriftRun,
    DriftRunState,
    DriftSchedule,
    DriftTickLedger,
    DriftTriggerKind,
)
from automojo.pychestrate.webservice.orchestration.infra.drift.service import (
    DriftReport,
    DriftRunView,
    DriftScheduleView,
    DriftTickResult,
    disable_schedule,
    get_drift_run,
    get_schedule,
    ingest_report,
    list_drift_runs_for_environment,
    record_tick,
    run_now,
    set_schedule,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`TerraformDriftChecker`
        reference.
    """
    register_factory_implementation(implementation=TerraformDriftChecker)
    return
