"""
.. module:: extensions.phase6_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Layer-6 (orchestration) extensions
               and construct the live :class:`TestOrchestrator`.

.. moduleauthor:: Automation Mojo LLC

Layer 6 hosts the orchestration plane — test, build, infra. M1
of ``6-test-catalog`` + ``6-test-orchestration`` registers two
factories: :class:`TestbaseRunnerKind` under ``test_runner_kind``
and :class:`TestbaseProjectImporter` under
``test_catalog_importer``. ``6-live-run-view`` is a singleton
service object — no factory protocol — so the live hub is
constructed and held inside the request layer rather than the
extension registry.

PR p19f adds the ``TestOrchestrator`` construction step. The
trigger-run REST route (``POST /api/v1/projects/{project_id}/
test-runs``, PR p19d) reads a module-level seam
``ACTIVE_TEST_ORCHESTRATOR`` and answers 503 when it is ``None``.
:func:`bootstrap_phase6_runtime` now constructs the orchestrator
with its dependencies (a :class:`JobDispatcher` over the
:class:`InMemoryTransport` reference adapter; the real client
transport lands with PR G) and publishes it on the route seam so
the endpoint can answer real requests.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.jobs.dispatch import (
    JobDispatcher,
)
from automojo.pychestrate.webservice.jobs.dispatch.transport_adapter import (
    ClientTransportProtocol,
    InMemoryTransport,
)
from automojo.pychestrate.webservice.jobs.results import (
    SharedResultsBackend,
)
from automojo.pychestrate.webservice.orchestration.test.orchestrator import (
    TestOrchestrator,
)
from automojo.pychestrate.webservice.orchestration.test.restapi.v1 import (
    test_runs_routes,
)

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


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase6BootstrapConfig:
    """
        Operator-supplied Phase-6 bootstrap configuration.

        :param session_factory: Session factory used by the
                                orchestration plane. When ``None``
                                the bootstrap runs the
                                extension-registration path only
                                (matching the register-only callsite
                                used by ``register_service_extensions``)
                                -- the orchestrator construction step
                                is skipped because trigger_run needs a
                                real session at request time anyway.
        :param transport: Optional dispatcher transport override. M1
                          defaults to :class:`InMemoryTransport`; the
                          real client transport lands with PR G.
        :param results_backend: Optional shared-results backend
                                override; defaults to the
                                ``local-test`` backend the orchestrator
                                constructs on its own when ``None``.
    """
    session_factory: Optional[SessionFactory]
    transport: Optional[ClientTransportProtocol] = None
    results_backend: Optional[SharedResultsBackend] = None


@dataclass(frozen=True)
class Phase6BootstrapResult:
    """
        Return value from :func:`bootstrap_phase6_runtime` carrying
        the constructed singletons so callers can keep a reference
        for diagnostics / tests.

        :param orchestrator: The active :class:`TestOrchestrator` or
                             ``None`` when the bootstrap ran in
                             register-only mode (no session factory).
        :param dispatcher: The :class:`JobDispatcher` the orchestrator
                           was constructed with.
        :param transport: The :class:`ClientTransportProtocol` the
                          dispatcher was constructed with.
    """
    orchestrator: Optional[TestOrchestrator]
    dispatcher: Optional[JobDispatcher]
    transport: Optional[ClientTransportProtocol]


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


def _build_test_orchestrator(
        *, config: Phase6BootstrapConfig
    ) -> Phase6BootstrapResult:
    """
        Construct the :class:`TestOrchestrator` with its
        dependencies and publish it on the trigger-run route's
        module-level seam.

        :param config: Caller-supplied
                       :class:`Phase6BootstrapConfig`.

        :returns: :class:`Phase6BootstrapResult` carrying the
                  constructed singletons.
    """
    transport = config.transport
    if transport is None:
        transport = InMemoryTransport()

    dispatcher = JobDispatcher(transport=transport)
    orchestrator = TestOrchestrator(
        dispatcher=dispatcher,
        results_backend=config.results_backend,
    )

    test_runs_routes.set_active_test_orchestrator(orchestrator=orchestrator)

    logger.info(
        "phase6.bootstrap.test_orchestrator_ready transport=%s",
        transport.transport_name(),
    )

    rtnval = Phase6BootstrapResult(
        orchestrator=orchestrator,
        dispatcher=dispatcher,
        transport=transport,
    )
    return rtnval


def bootstrap_phase6_runtime(
        *, config: Phase6BootstrapConfig
    ) -> Phase6BootstrapResult:
    """
        Layer-6 runtime bootstrap.

        Registers the in-tree Layer-6 factory implementations and,
        when a session factory is supplied, constructs the live
        :class:`TestOrchestrator` and publishes it on the
        trigger-run route's ``ACTIVE_TEST_ORCHESTRATOR`` seam.

        When ``config.session_factory`` is ``None``, the
        orchestrator construction is skipped -- this matches the
        register-only callsite used by ``register_service_extensions``
        which only needs the factories on the registry. The runtime
        bootstrap path passes a real session factory so the
        orchestrator is wired and the trigger-run REST endpoint
        stops returning 503.

        :param config: Caller-supplied
                       :class:`Phase6BootstrapConfig`.

        :returns: :class:`Phase6BootstrapResult` carrying the
                  constructed orchestrator + dispatcher + transport
                  (each ``None`` in register-only mode).
    """
    register_phase6_builtin_extensions()

    if config.session_factory is None:
        rtnval = Phase6BootstrapResult(
            orchestrator=None,
            dispatcher=None,
            transport=None,
        )
        return rtnval

    rtnval = _build_test_orchestrator(config=config)
    return rtnval
