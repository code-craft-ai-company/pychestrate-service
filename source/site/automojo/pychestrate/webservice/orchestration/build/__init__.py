"""
.. module:: orchestration.build
    :synopsis: 6-build-orchestration — build-run state engine.

Public surface:

* :class:`BuildRun`, :class:`BuildToolchainSnapshot`,
  :class:`BuildCacheScope`, :class:`BuildRunState` —
  persistence rows + enum.
* :class:`ReproSnapshot`, :class:`BuildRunView`,
  :class:`BuildRunInputs`, :class:`BuildToolchainEntry`,
  :class:`BuildTriggerAspects` — IO shapes.
* :func:`compute_repro_digest`, :func:`trigger_run`,
  :func:`apply_run_terminal`, :func:`get_build_run`,
  :func:`list_build_runs_for_project`.
* :class:`BuildRunnerKindProtocol` factory contract +
  reference :class:`MakefileRunnerKind`.
* :class:`BuildEventTopics`.
* Errors: :class:`BuildError`, :class:`BuildRunNotFoundError`,
  :class:`BuildRunnerKindUnknownError`,
  :class:`BuildInputsInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.build.errors import (
    BuildError,
    BuildInputsInvalidError,
    BuildRunNotFoundError,
    BuildRunnerKindUnknownError,
    BuildSourceIntegrationUnknownError,
)
from automojo.pychestrate.webservice.orchestration.build.events import (
    BuildEventTopics,
)
from automojo.pychestrate.webservice.orchestration.build.factories.makefile_runner_kind import (
    MakefileRunnerKind,
)
from automojo.pychestrate.webservice.orchestration.build.factories.runner_protocol import (
    BuildRunnerKindProtocol,
)
from automojo.pychestrate.webservice.orchestration.build.models import (
    BuildCacheScope,
    BuildRun,
    BuildRunState,
    BuildToolchainSnapshot,
)
from automojo.pychestrate.webservice.orchestration.build.repro_snapshot import (
    BuildToolchainEntry,
    ReproSnapshot,
    compute_repro_digest,
)
from automojo.pychestrate.webservice.orchestration.build.service import (
    BuildRunInputs,
    BuildRunView,
    BuildTriggerAspects,
    apply_run_terminal,
    get_build_run,
    list_build_runs_for_project,
    trigger_run,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`MakefileRunnerKind` reference.
    """
    register_factory_implementation(implementation=MakefileRunnerKind)
    return
