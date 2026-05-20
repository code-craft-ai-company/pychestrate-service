"""
.. module:: test_p20l_provisioning_dispatch_wiring_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for wiring provisioning-run dispatch through the
               job transport (PR p20l).

.. moduleauthor:: Automation Mojo LLC

Covers the server-side provisioning-dispatch wiring:

* ``trigger_run`` builds + signs a ``job_kind=provision`` JobEnvelope
  and dispatches it through the wired :class:`JobDispatcher`; the
  dispatch attempt is recorded and the signed envelope's signature
  verifies.
* The :class:`InfraRun` flips ``PENDING -> RUNNING`` and the run-state
  machine row reaches ``dispatching``.
* No eligible candidate => :class:`InfraDispatchFailedError` and the
  InfraRun lands ``FAILED``.
* No dispatcher wired => :class:`InfraDispatchUnavailableError`.
* The envelope ``job_kind`` discriminator is backward compatible: an
  envelope minted without ``job_kind`` parses back as ``test``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Tuple

from automojo import testbase

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.jobs.dispatch import (
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from automojo.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from automojo.pychestrate.webservice.jobs.dispatch.models import (
    DispatchAttempt,
    DispatchAttemptStatus,
)
from automojo.pychestrate.webservice.jobs.envelope import (
    ENVELOPE_SCHEMA_VERSION,
    EnvelopeSignerBootstrapConfig,
    JOB_KIND_PROVISION,
    JOB_KIND_TEST,
    install_envelope_signer,
    verify as verify_envelope,
)
from automojo.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from automojo.pychestrate.webservice.jobs.envelope.canonical import (
    dict_to_envelope,
    envelope_to_dict,
)
from automojo.pychestrate.webservice.jobs.run.state import (
    RunState,
    get_snapshot as get_run_state_snapshot,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
)
from automojo.pychestrate.webservice.orchestration.infra.environment import (
    EnvironmentDeclareInputs,
    declare_environment,
    register_builtin_extensions as environment_register,
)
from automojo.pychestrate.webservice.orchestration.infra.runs import (
    InfraAction,
    InfraDispatchFailedError,
    InfraDispatchUnavailableError,
    InfraRunInputs,
    InfraRunState,
    InfraTriggerAspects,
    register_builtin_extensions as infra_runs_register,
    set_active_job_dispatcher,
    set_active_results_backend,
    trigger_run,
    list_infra_runs_for_environment,
)

# Side-effect imports so the Layer-5 + infra model tables attach to the
# shared Phase-1 metadata before ``create_all`` runs in the fixture.
from automojo.pychestrate.webservice.orchestration.infra.runs import models as _infra_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.infra.environment import models as _env_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000020c0"


def _prepare_runtime() -> None:
    """
        Reset cross-test globals + register the infra driver, the
        dispatch strategy, and an ephemeral envelope signing key.

        :returns: None.
    """
    reset_registry_for_testing()
    reset_event_bus()
    envelope_signer.reset_for_testing()
    set_active_job_dispatcher(dispatcher=None)
    set_active_results_backend(backend=None)
    dispatch_register()
    environment_register()
    infra_runs_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev",
                file_path=None,
                env_var=None,
                key_id="test-provision-dispatch-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    return


def _declare_environment(*, session) -> str:
    """
        Declare a k8s-cluster environment and return its id.

        :param session: Active SQLAlchemy session.

        :returns: Environment UUID string.
    """
    view = declare_environment(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=EnvironmentDeclareInputs(
            name="prod-east",
            kind_name="k8s-cluster",
            attrs={
                "cluster_id": "cluster-001",
                "region": "us-east-1",
                "api_endpoint": "https://api.example.com",
            },
        ),
    )
    rtnval = view.environment_id
    return rtnval


def _provision_inputs(*, environment_id: str) -> InfraRunInputs:
    """
        A valid terraform provisioning input payload.

        :param environment_id: Bound environment id.

        :returns: :class:`InfraRunInputs`.
    """
    rtnval = InfraRunInputs(
        environment_id=environment_id,
        driver_name="terraform",
        action=InfraAction.PLAN,
        driver_inputs={
            "working_directory": "/repo/infra",
            "var_file": "prod.tfvars",
            "backend_config": {"bucket": "tfstate"},
            "parallelism": 4,
        },
    )
    return rtnval


def _one_candidate() -> Tuple[DispatchCandidate, ...]:
    """
        A single eligible dispatch candidate.

        :returns: One-element tuple of :class:`DispatchCandidate`.
    """
    rtnval = (
        DispatchCandidate(
            client_id="11111111-1111-4000-8000-0000000020c1",
            pod_id="22222222-2222-4000-8000-0000000020c2",
            capability_tags=tuple(),
            inflight_dispatch_count=0,
            last_dispatched_at_iso="",
        ),
    )
    return rtnval


def test_trigger_run_dispatches_provision_envelope_and_records_attempt():
    """
    **Feature: 6-infra-orchestration PR p20l**
    **Property: trigger_run builds + signs a job_kind=provision
    envelope, dispatches it through the wired JobDispatcher, records
    the dispatch attempt, and the signed envelope's signature
    verifies.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    dispatcher = JobDispatcher(transport=transport)
    set_active_job_dispatcher(dispatcher=dispatcher)
    env_id = _declare_environment(session=session)

    aspects = InfraTriggerAspects(
        candidates=_one_candidate(),
        project_slug="prod-east",
    )
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_provision_inputs(environment_id=env_id),
        aspects=aspects,
    )

    testbase.assert_equal(view.state, InfraRunState.RUNNING)
    testbase.assert_equal(view.dispatch_attempt_id is not None, True)

    attempt = (
        session.query(DispatchAttempt)
        .filter(DispatchAttempt.run_id == view.run_id)
        .first()
    )
    testbase.assert_equal(attempt is not None, True)
    testbase.assert_equal(
        attempt.status, DispatchAttemptStatus.TRANSMITTED,
    )

    # The transport received exactly one signed provision envelope;
    # its signature verifies and its job_kind is "provision".
    transmitted = transport.calls()
    testbase.assert_equal(len(transmitted), 1)
    signed = transmitted[0].signed
    testbase.assert_equal(signed.envelope.job_kind, JOB_KIND_PROVISION)
    verification = verify_envelope(signed=signed)
    testbase.assert_equal(verification.valid, True)

    # The provision-spec payload rode in the envelope params section.
    params = signed.envelope.params
    testbase.assert_equal(params["environment_id"], env_id)
    testbase.assert_equal(params["action"], "plan")
    testbase.assert_equal(params["driver_name"], "terraform")
    testbase.assert_equal(
        params["driver_inputs"]["working_directory"], "/repo/infra",
    )
    return


def test_trigger_run_advances_run_state_to_dispatching():
    """
    **Feature: 6-infra-orchestration PR p20l**
    **Property: trigger_run drives the run-state machine through
    PENDING -> DISPATCHING for the provisioning run.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())
    set_active_job_dispatcher(dispatcher=dispatcher)
    env_id = _declare_environment(session=session)

    aspects = InfraTriggerAspects(
        candidates=_one_candidate(),
        project_slug="prod-east",
    )
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_provision_inputs(environment_id=env_id),
        aspects=aspects,
    )

    testbase.assert_equal(view.run_state, RunState.DISPATCHING.value)

    snapshot = get_run_state_snapshot(
        db_session=session, run_id=view.run_id,
    )
    testbase.assert_equal(snapshot.state, RunState.DISPATCHING)
    return


def test_trigger_run_no_eligible_pod_fails_provisioning():
    """
    **Feature: 6-infra-orchestration PR p20l**
    **Property: trigger_run with no candidates raises
    InfraDispatchFailedError and leaves the InfraRun FAILED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())
    set_active_job_dispatcher(dispatcher=dispatcher)
    env_id = _declare_environment(session=session)

    aspects = InfraTriggerAspects(
        candidates=tuple(),
        project_slug="prod-east",
    )
    raised = False
    try:
        trigger_run(
            db_session=session,
            project_id=PROJECT_UUID,
            inputs=_provision_inputs(environment_id=env_id),
            aspects=aspects,
        )
    except InfraDispatchFailedError:
        raised = True
    testbase.assert_equal(raised, True)

    runs = list_infra_runs_for_environment(
        db_session=session, environment_id=env_id,
    )
    testbase.assert_equal(len(runs), 1)
    testbase.assert_equal(runs[0].state, InfraRunState.FAILED)
    return


def test_trigger_run_without_dispatcher_raises_unavailable():
    """
    **Feature: 6-infra-orchestration PR p20l**
    **Property: trigger_run raises InfraDispatchUnavailableError
    when no JobDispatcher has been wired.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    # Deliberately leave the dispatcher seam unset.

    aspects = InfraTriggerAspects(
        candidates=_one_candidate(),
        project_slug="prod-east",
    )
    raised = False
    try:
        trigger_run(
            db_session=session,
            project_id=PROJECT_UUID,
            inputs=_provision_inputs(environment_id=env_id),
            aspects=aspects,
        )
    except InfraDispatchUnavailableError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_envelope_job_kind_defaults_to_test_for_backward_compat():
    """
    **Feature: 5-job-envelope PR p20l**
    **Property: an envelope dict minted WITHOUT a job_kind field
    parses back cleanly with job_kind == "test" -- existing test
    envelopes still validate.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    dispatcher = JobDispatcher(transport=transport)
    set_active_job_dispatcher(dispatcher=dispatcher)
    env_id = _declare_environment(session=session)

    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_provision_inputs(environment_id=env_id),
        aspects=InfraTriggerAspects(
            candidates=_one_candidate(),
            project_slug="prod-east",
        ),
    )
    signed = transport.calls()[0].signed
    envelope_dict = envelope_to_dict(envelope=signed.envelope)

    # Drop job_kind entirely -- simulate a pre-discriminator envelope.
    del envelope_dict["job_kind"]
    rehydrated = dict_to_envelope(candidate=envelope_dict)
    testbase.assert_equal(rehydrated.job_kind, JOB_KIND_TEST)
    testbase.assert_equal(rehydrated.schema_version, ENVELOPE_SCHEMA_VERSION)
    # The provisioning run still triggered successfully -- sanity guard.
    testbase.assert_equal(view.state, InfraRunState.RUNNING)
    return
