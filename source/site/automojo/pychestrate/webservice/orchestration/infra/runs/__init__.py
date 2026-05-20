"""
.. module:: orchestration.infra.runs
    :synopsis: 6-infra-orchestration — infra-run state engine.

Public surface:

* :class:`InfraRun`, :class:`InfraAction`,
  :class:`InfraRunState` — persistence row + enums.
* :class:`InfraRunInputs`, :class:`InfraRunView`,
  :class:`InfraTriggerAspects`, :class:`PlanSummary`,
  :class:`ResourceOp`, :class:`ResourceOpKind` — IO shapes.
* :func:`trigger_run`, :func:`apply_run_terminal`,
  :func:`record_plan_summary`, :func:`get_infra_run`,
  :func:`list_infra_runs_for_environment`.
* :class:`InfraToolDriverProtocol` factory contract +
  reference :class:`TerraformInfraDriver`.
* :class:`InfraEventTopics`.
* Errors: :class:`InfraError`, :class:`InfraRunNotFoundError`,
  :class:`InfraDriverUnknownError`,
  :class:`InfraInputsInvalidError`,
  :class:`InfraEnvironmentStateError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.errors import (
    InfraDispatchFailedError,
    InfraDispatchUnavailableError,
    InfraDriverUnknownError,
    InfraEnvironmentStateError,
    InfraError,
    InfraInputsInvalidError,
    InfraRunNotFoundError,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.events import (
    InfraEventTopics,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.factories.driver_protocol import (
    InfraToolDriverProtocol,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.factories.terraform_driver import (
    TerraformInfraDriver,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.models import (
    InfraAction,
    InfraRun,
    InfraRunState,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.service import (
    InfraRunInputs,
    InfraRunView,
    InfraTriggerAspects,
    PlanSummary,
    ResourceOp,
    ResourceOpKind,
    apply_run_terminal,
    get_infra_run,
    list_infra_runs_for_environment,
    list_infra_runs_for_project,
    record_plan_summary,
    set_active_job_dispatcher,
    set_active_results_backend,
    trigger_run,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`TerraformInfraDriver` reference.
    """
    register_factory_implementation(implementation=TerraformInfraDriver)
    return
