"""
.. module:: extensions.phase6_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Layer-6 (orchestration) extensions
               and construct the live :class:`TestOrchestrator`.

.. moduleauthor:: Code Craft AI LLC

Layer 6 hosts the orchestration plane — test, build, infra. M1
of ``6-test-catalog`` + ``6-test-orchestration`` registers two
factories: :class:`TestbaseRunnerKind` under ``test_runner_kind``
and :class:`TestbaseProjectImporter` under
``test_catalog_importer``. ``6-live-run-view`` is a singleton
service object — no factory protocol — so the live hub is
constructed and held inside the request layer rather than the
extension registry.

PR p19f adds the ``TestOrchestrator`` construction step. PR p19g
swaps the dispatcher's reference :class:`InMemoryTransport` for
the production :class:`LongPollTransport` so signed envelopes
queue up for the remote pod-client to pull via ``GET
/api/v1/clients/{client_id}/dispatches:next``. Tests can still pass
an explicit :class:`InMemoryTransport` through
:class:`Phase6BootstrapConfig` to keep call-recording semantics.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.agents.factories.long_poll_transport import (
    LongPollTransport,
)
from ccai.pychestrate.webservice.clients.restapi.v1 import (
    client_dispatch_routes,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    JobDispatcher,
)
from ccai.pychestrate.webservice.jobs.dispatch.transport_adapter import (
    ClientTransportProtocol,
    InMemoryTransport,
)
from ccai.pychestrate.webservice.jobs.results import (
    SharedResultsBackend,
)
from ccai.pychestrate.webservice.orchestration.test.live.bus_bridge import (
    LiveRunBusBridge,
)
from ccai.pychestrate.webservice.orchestration.test.live.hub import (
    LiveRunHub,
)
from ccai.pychestrate.webservice.orchestration.test.orchestrator import (
    TestOrchestrator,
)
from ccai.pychestrate.webservice.orchestration.test.restapi.v1 import (
    test_runs_routes,
)
from ccai.pychestrate.webservice.runs.restapi.v1 import (
    artifacts_routes,
    runs_events_routes,
)

from ccai.pychestrate.webservice.orchestration.build import (
    register_builtin_extensions as build_orch_register,
)
from ccai.pychestrate.webservice.orchestration.build import (
    service as build_service,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts import (
    register_builtin_extensions as build_artifacts_register,
)
from ccai.pychestrate.webservice.orchestration.rpa import (
    register_builtin_extensions as rpa_orch_register,
)
from ccai.pychestrate.webservice.orchestration.rpa import (
    service as rpa_service,
)
from ccai.pychestrate.webservice.orchestration.infra.drift import (
    register_builtin_extensions as drift_detection_register,
)
from ccai.pychestrate.webservice.orchestration.infra.environment import (
    register_builtin_extensions as environment_registry_register,
)
from ccai.pychestrate.webservice.orchestration.infra.guards import (
    register_builtin_extensions as blast_radius_guards_register,
)
from ccai.pychestrate.webservice.orchestration.infra.runs import (
    register_builtin_extensions as infra_runs_register,
)
from ccai.pychestrate.webservice.orchestration.infra.runs import (
    service as infra_runs_service,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    register_builtin_extensions as pipeline_definition_register,
)
from ccai.pychestrate.webservice.orchestration.pipelines.execution.orchestrator import (
    PipelineOrchestrator,
    set_active_pipeline_orchestrator,
)
from ccai.pychestrate.webservice.orchestration.pipelines.sharding import (
    register_builtin_extensions as sharding_register,
)
from ccai.pychestrate.webservice.orchestration.source import (
    register_builtin_extensions as source_integrations_register,
)
from ccai.pychestrate.webservice.orchestration.test import (
    register_builtin_extensions as test_orch_register,
)
from ccai.pychestrate.webservice.orchestration.test.artifact_browser import (
    register_builtin_extensions as artifact_browser_register,
)
from ccai.pychestrate.webservice.orchestration.test.compare import (
    register_builtin_extensions as compare_register,
)
from ccai.pychestrate.webservice.orchestration.test.flake import (
    register_builtin_extensions as flake_register,
)
from ccai.pychestrate.webservice.orchestration.test.triage import (
    register_builtin_extensions as triage_register,
)

# Side-effect imports so Layer-6 model tables attach to the metadata.
from ccai.pychestrate.webservice.orchestration.build import models as _build_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.build.artifacts import models as _build_artifacts_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.rpa import models as _rpa_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.infra.drift import models as _drift_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.infra.environment import models as _environment_registry_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.infra.guards import models as _guards_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.infra.runs import models as _infra_runs_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.pipelines.definition import models as _pipeline_definition_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.pipelines.sharding import models as _sharding_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.source import models as _source_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.test import models as _test_run_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.test.catalog import models as _test_catalog_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.test.compare import models as _test_compare_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.test.flake import models as _test_flake_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.test.triage import models as _test_triage_models  # noqa: F401


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
        :param transport: Optional dispatcher transport override.
                          Production defaults to
                          :class:`LongPollTransport` (PR p19g); tests
                          pass an explicit :class:`InMemoryTransport`
                          to keep call-recording semantics.
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
    rpa_orch_register()
    environment_registry_register()
    infra_runs_register()
    drift_detection_register()
    blast_radius_guards_register()
    _publish_result_presign_seams()
    return


def _publish_result_presign_seams() -> None:
    """
        Publish the :class:`SharedResultsBackend` and the HMAC
        signing secret on the presigned-result-upload route's
        module-level seams (PR p19l).

        Runs in both the register-only and the live bootstrap
        paths so ``POST /api/v1/runs/{run_id}/artifacts:presign``
        and ``PUT .../_local-upload`` are wired the moment their
        routes attach. The signing secret comes from
        ``PYCHESTRATE_RESULT_PRESIGN_SECRET`` or -- when unset -- a
        per-process random secret.

        :returns: None.
    """
    backend = SharedResultsBackend(backend_driver="local-test")
    artifacts_routes.set_shared_results_backend(backend=backend)

    secret = artifacts_routes.resolve_presign_signing_secret_from_environment()
    artifacts_routes.set_presign_signing_secret(secret=secret)

    logger.info("phase6.bootstrap.result_presign_seams_published")
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
        transport = LongPollTransport()

    # Publish the active long-poll transport on the client-pull
    # route seam so ``GET /api/v1/clients/{client_id}/dispatches:next``
    # can dequeue the same records the dispatcher enqueues. When the
    # transport is anything other than a LongPollTransport (e.g. the
    # InMemoryTransport used in tests), we leave the seam alone --
    # the route then answers 503 which is the documented "not
    # configured" behaviour.
    if isinstance(transport, LongPollTransport):
        client_dispatch_routes.set_active_long_poll_transport(
            transport=transport,
        )

    dispatcher = JobDispatcher(transport=transport)
    orchestrator = TestOrchestrator(
        dispatcher=dispatcher,
        results_backend=config.results_backend,
    )

    test_runs_routes.set_active_test_orchestrator(orchestrator=orchestrator)

    # Publish the SAME JobDispatcher on the build service's seam so a
    # triggered build dispatches a ``job_kind=build`` envelope into the
    # identical long-poll queue test runs already land in. The build
    # service shares the dispatcher's transport -- there is one queue.
    build_service.set_active_job_dispatcher(dispatcher=dispatcher)
    build_service.set_active_results_backend(
        backend=config.results_backend,
    )

    # Publish the SAME JobDispatcher on the infra-runs service's seam
    # so a triggered provisioning run dispatches a
    # ``job_kind=provision`` envelope into the identical long-poll
    # queue test + build runs already land in. There is one queue.
    infra_runs_service.set_active_job_dispatcher(dispatcher=dispatcher)
    infra_runs_service.set_active_results_backend(
        backend=config.results_backend,
    )

    # Publish the SAME JobDispatcher on the RPA service's seam so a
    # triggered RPA job dispatches a ``job_kind=rpa`` envelope into
    # the same long-poll queue. There is one queue.
    rpa_service.set_active_job_dispatcher(dispatcher=dispatcher)
    rpa_service.set_active_results_backend(
        backend=config.results_backend,
    )

    # Construct the PipelineOrchestrator (6-pipeline-execution PR
    # p20q). It walks a pipeline definition's stage DAG and dispatches
    # each eligible stage's job through the SAME build / test /
    # provision dispatch handles wired above -- it coordinates, it does
    # not re-implement job dispatch. The orchestrator subscribes to the
    # run-state machine's terminal bus topics so a stage-job terminal
    # event re-drives the DAG walk; the bus subscriber needs its own
    # session, hence the session factory.
    pipeline_orchestrator = PipelineOrchestrator(
        session_factory=config.session_factory,
        test_orchestrator=orchestrator,
        build_service_module=build_service,
        infra_service_module=infra_runs_service,
        rpa_service_module=rpa_service,
    )
    pipeline_orchestrator.attach_bus_subscribers()
    set_active_pipeline_orchestrator(orchestrator=pipeline_orchestrator)

    logger.info(
        "phase6.bootstrap.test_orchestrator_ready transport=%s",
        transport.transport_name(),
    )
    logger.info(
        "phase6.bootstrap.pipeline_orchestrator_ready",
    )
    logger.info(
        "phase6.bootstrap.build_dispatch_wired transport=%s",
        transport.transport_name(),
    )
    logger.info(
        "phase6.bootstrap.provision_dispatch_wired transport=%s",
        transport.transport_name(),
    )

    rtnval = Phase6BootstrapResult(
        orchestrator=orchestrator,
        dispatcher=dispatcher,
        transport=transport,
    )
    return rtnval


def bootstrap_live_run_view() -> LiveRunBusBridge:
    """
        Construct the ``6-live-run-view`` singletons and publish the
        bus bridge on the SSE route's module seam.

        ``6-live-run-view`` is a singleton service object -- no
        factory protocol -- so the :class:`LiveRunHub` is constructed
        here and held inside the request layer. A
        :class:`LiveRunBusBridge` is wrapped around the hub and
        attached to the in-process bus so run-state-change + progress
        events forward onto the hub relays the SSE route streams.

        Idempotent at the bus level: :meth:`LiveRunBusBridge.attach`
        no-ops on a second call so re-running the bootstrap does not
        double-subscribe.

        :returns: The constructed :class:`LiveRunBusBridge`.
    """
    hub = LiveRunHub()
    bridge = LiveRunBusBridge(hub=hub)
    bridge.attach()

    runs_events_routes.set_active_live_run_bridge(bridge=bridge)

    logger.info("phase6.bootstrap.live_run_view_ready")

    rtnval = bridge
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

    # The live-run-view bridge needs no db session -- it is a pure
    # in-process pub/sub bridge -- so construct it unconditionally
    # so the SSE route is wired even in register-only mode.
    bootstrap_live_run_view()

    if config.session_factory is None:
        rtnval = Phase6BootstrapResult(
            orchestrator=None,
            dispatcher=None,
            transport=None,
        )
        return rtnval

    rtnval = _build_test_orchestrator(config=config)
    return rtnval
