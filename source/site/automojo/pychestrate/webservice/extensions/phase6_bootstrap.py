"""
.. module:: extensions.phase6_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Layer-6 (orchestration) extensions.

.. moduleauthor:: Automation Mojo LLC

Layer 6 hosts the orchestration plane — test, build, infra. M1
of ``6-test-catalog`` + ``6-test-orchestration`` registers two
factories: :class:`TestbaseRunnerKind` under ``test_runner_kind``
and :class:`TestbaseProjectImporter` under
``test_catalog_importer``. ``6-live-run-view`` is a singleton
service object — no factory protocol — so the live hub is
constructed and held inside the request layer rather than the
extension registry.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.orchestration.build import (
    register_builtin_extensions as build_orch_register,
)
from automojo.pychestrate.webservice.orchestration.build.artifacts import (
    register_builtin_extensions as build_artifacts_register,
)
from automojo.pychestrate.webservice.orchestration.infra.drift import (
    register_builtin_extensions as drift_detection_register,
)
from automojo.pychestrate.webservice.orchestration.infra.environment import (
    register_builtin_extensions as environment_registry_register,
)
from automojo.pychestrate.webservice.orchestration.infra.guards import (
    register_builtin_extensions as blast_radius_guards_register,
)
from automojo.pychestrate.webservice.orchestration.infra.runs import (
    register_builtin_extensions as infra_runs_register,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition import (
    register_builtin_extensions as pipeline_definition_register,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding import (
    register_builtin_extensions as sharding_register,
)
from automojo.pychestrate.webservice.orchestration.source import (
    register_builtin_extensions as source_integrations_register,
)
from automojo.pychestrate.webservice.orchestration.test import (
    register_builtin_extensions as test_orch_register,
)
from automojo.pychestrate.webservice.orchestration.test.artifact_browser import (
    register_builtin_extensions as artifact_browser_register,
)
from automojo.pychestrate.webservice.orchestration.test.compare import (
    register_builtin_extensions as compare_register,
)
from automojo.pychestrate.webservice.orchestration.test.flake import (
    register_builtin_extensions as flake_register,
)
from automojo.pychestrate.webservice.orchestration.test.triage import (
    register_builtin_extensions as triage_register,
)

# Side-effect imports so Layer-6 model tables attach to the metadata.
from automojo.pychestrate.webservice.orchestration.build import models as _build_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.build.artifacts import models as _build_artifacts_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.infra.drift import models as _drift_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.infra.environment import models as _environment_registry_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.infra.guards import models as _guards_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.infra.runs import models as _infra_runs_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.pipelines.definition import models as _pipeline_definition_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.pipelines.sharding import models as _sharding_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.source import models as _source_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test import models as _test_run_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test.catalog import models as _test_catalog_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test.compare import models as _test_compare_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test.flake import models as _test_flake_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test.triage import models as _test_triage_models  # noqa: F401


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class Phase6BootstrapConfig:
    """
        Operator-supplied Phase-6 bootstrap configuration.
    """
    session_factory: Optional[SessionFactory]


def register_phase6_builtin_extensions() -> None:
    """
        Register Layer-6 in-tree factory implementations.
    """
    test_orch_register()
    sharding_register()
    flake_register()
    artifact_browser_register()
    triage_register()
    compare_register()
    pipeline_definition_register()
    source_integrations_register()
    build_orch_register()
    build_artifacts_register()
    environment_registry_register()
    infra_runs_register()
    drift_detection_register()
    blast_radius_guards_register()
    return


def bootstrap_phase6_runtime(*, config: Phase6BootstrapConfig) -> None:
    """
        Layer-6 runtime bootstrap. M1 only registers extensions;
        future M2 work (live-run hub bus subscriber wiring) extends
        this function.
    """
    register_phase6_builtin_extensions()
    _ = config
    return
