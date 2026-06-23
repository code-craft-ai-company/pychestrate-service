"""
.. module:: test_p20j_build_dispatch_wiring_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for wiring build-run dispatch through the job
               transport (PR p20j).

.. moduleauthor:: Code Craft AI LLC

Covers the server-side build-dispatch wiring:

* ``trigger_run`` builds + signs a ``job_kind=build`` JobEnvelope and
  dispatches it through the wired :class:`JobDispatcher`; the dispatch
  attempt is recorded and the signed envelope's signature verifies.
* The :class:`BuildRun` flips ``PENDING -> RUNNING`` and the run-state
  machine row reaches ``dispatching``.
* No eligible candidate => :class:`BuildDispatchFailedError` and the
  BuildRun lands ``FAILED``.
* No dispatcher wired => :class:`BuildDispatchUnavailableError`.
* The envelope ``job_kind`` discriminator is backward compatible: an
  envelope minted without ``job_kind`` parses back as ``test``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime, timedelta, timezone
from typing import Tuple

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.jobs.dispatch.models import (
    DispatchAttempt,
    DispatchAttemptStatus,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    ENVELOPE_SCHEMA_VERSION,
    EnvelopeSignerBootstrapConfig,
    JOB_KIND_BUILD,
    JOB_KIND_TEST,
    install_envelope_signer,
    verify as verify_envelope,
)
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.jobs.envelope.canonical import (
    dict_to_envelope,
    envelope_to_dict,
)
from ccai.pychestrate.webservice.jobs.run.state import (
    RunState,
    get_snapshot as get_run_state_snapshot,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
)
from ccai.pychestrate.webservice.orchestration.build import (
    register_builtin_extensions as build_register,
    service as build_service,
)
from ccai.pychestrate.webservice.orchestration.build.errors import (
    BuildDispatchFailedError,
    BuildDispatchUnavailableError,
)
from ccai.pychestrate.webservice.orchestration.build.models import (
    BuildRunState,
)

# Side-effect imports so the Layer-5 + build model tables attach to the
# shared Phase-1 metadata before ``create_all`` runs in the fixture.
from ccai.pychestrate.webservice.orchestration.build import models as _build_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000020a0"


def _prepare_runtime() -> None:
    """
        Reset cross-test globals + register the build runner kind,
        the dispatch strategy, and an ephemeral envelope signing key.

        :returns: None.
    """
    reset_registry_for_testing()
    reset_event_bus()
    envelope_signer.reset_for_testing()
    build_service.set_active_job_dispatcher(dispatcher=None)
    build_service.set_active_results_backend(backend=None)
    dispatch_register()
    build_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev",
                file_path=None,
                env_var=None,
                key_id="test-build-dispatch-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    return


def _build_inputs() -> build_service.BuildRunInputs:
    """
        A valid Makefile build-run input payload.

        :returns: :class:`BuildRunInputs`.
    """
    rtnval = build_service.BuildRunInputs(
        runner_kind="makefile",
        runner_inputs={"targets": ["all"], "branch": "main"},
        input_files={"Makefile": "d" * 64},
        env={"CC": "gcc"},
    )
    return rtnval


def _one_candidate() -> Tuple[DispatchCandidate, ...]:
    """
        A single eligible dispatch candidate.

        :returns: One-element tuple of :class:`DispatchCandidate`.
    """
    rtnval = (
        DispatchCandidate(
            client_id="11111111-1111-4000-8000-0000000020a1",
            pod_id="22222222-2222-4000-8000-0000000020a2",
            capability_tags=tuple(),
            inflight_dispatch_count=0,
            last_dispatched_at_iso="",
        ),
    )
    return rtnval


def test_trigger_run_dispatches_build_envelope_and_records_attempt():
    """
    **Feature: 6-build-orchestration PR p20j**
    **Property: trigger_run builds + signs a job_kind=build envelope,
    dispatches it through the wired JobDispatcher, records the
    dispatch attempt, and the signed envelope's signature verifies.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    dispatcher = JobDispatcher(transport=transport)
    build_service.set_active_job_dispatcher(dispatcher=dispatcher)

    aspects = build_service.BuildTriggerAspects(
        candidates=_one_candidate(),
        project_slug="proj-slug",
    )
    view = build_service.trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_build_inputs(),
        aspects=aspects,
    )

    testbase.assert_equal(view.state, BuildRunState.RUNNING)
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

    # The transport received exactly one signed build envelope; its
    # signature verifies and its job_kind is "build".
    transmitted = transport.calls()
    testbase.assert_equal(len(transmitted), 1)
    signed = transmitted[0].signed
    testbase.assert_equal(signed.envelope.job_kind, JOB_KIND_BUILD)
    verification = verify_envelope(signed=signed)
    testbase.assert_equal(verification.valid, True)

    # The build-spec payload rode in the envelope params section.
    params = signed.envelope.params
    testbase.assert_equal(params["runner_kind"], "makefile")
    testbase.assert_equal(params["runner_inputs"]["targets"], ["all"])
    return


def test_trigger_run_advances_run_state_to_dispatching():
    """
    **Feature: 6-build-orchestration PR p20j**
    **Property: trigger_run drives the run-state machine through
    PENDING -> DISPATCHING for the build run.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())
    build_service.set_active_job_dispatcher(dispatcher=dispatcher)

    aspects = build_service.BuildTriggerAspects(
        candidates=_one_candidate(),
        project_slug="proj-slug",
    )
    view = build_service.trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_build_inputs(),
        aspects=aspects,
    )

    testbase.assert_equal(view.run_state, RunState.DISPATCHING.value)

    snapshot = get_run_state_snapshot(
        db_session=session, run_id=view.run_id,
    )
    testbase.assert_equal(snapshot.state, RunState.DISPATCHING)
    return


def test_trigger_run_no_eligible_pod_fails_build():
    """
    **Feature: 6-build-orchestration PR p20j**
    **Property: trigger_run with no candidates raises
    BuildDispatchFailedError and leaves the BuildRun FAILED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    dispatcher = JobDispatcher(transport=InMemoryTransport())
    build_service.set_active_job_dispatcher(dispatcher=dispatcher)

    aspects = build_service.BuildTriggerAspects(
        candidates=tuple(),
        project_slug="proj-slug",
    )
    raised = False
    try:
        build_service.trigger_run(
            db_session=session,
            project_id=PROJECT_UUID,
            inputs=_build_inputs(),
            aspects=aspects,
        )
    except BuildDispatchFailedError:
        raised = True
    testbase.assert_equal(raised, True)

    runs = build_service.list_build_runs_for_project(
        db_session=session, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(len(runs), 1)
    testbase.assert_equal(runs[0].state, BuildRunState.FAILED)
    return


def test_trigger_run_without_dispatcher_raises_unavailable():
    """
    **Feature: 6-build-orchestration PR p20j**
    **Property: trigger_run raises BuildDispatchUnavailableError
    when no JobDispatcher has been wired.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    # Deliberately leave the dispatcher seam unset.

    aspects = build_service.BuildTriggerAspects(
        candidates=_one_candidate(),
        project_slug="proj-slug",
    )
    raised = False
    try:
        build_service.trigger_run(
            db_session=session,
            project_id=PROJECT_UUID,
            inputs=_build_inputs(),
            aspects=aspects,
        )
    except BuildDispatchUnavailableError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_envelope_job_kind_defaults_to_test_for_backward_compat():
    """
    **Feature: 5-job-envelope PR p20j**
    **Property: an envelope dict minted WITHOUT a job_kind field
    parses back cleanly with job_kind == "test" -- existing test
    envelopes still validate.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    transport = InMemoryTransport()
    dispatcher = JobDispatcher(transport=dispatcher_transport_or(transport))
    build_service.set_active_job_dispatcher(dispatcher=dispatcher)

    view = build_service.trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_build_inputs(),
        aspects=build_service.BuildTriggerAspects(
            candidates=_one_candidate(),
            project_slug="proj-slug",
        ),
    )
    signed = transport.calls()[0].signed
    envelope_dict = envelope_to_dict(envelope=signed.envelope)

    # Drop job_kind entirely -- simulate a pre-discriminator envelope.
    del envelope_dict["job_kind"]
    rehydrated = dict_to_envelope(candidate=envelope_dict)
    testbase.assert_equal(rehydrated.job_kind, JOB_KIND_TEST)
    testbase.assert_equal(rehydrated.schema_version, ENVELOPE_SCHEMA_VERSION)
    # The build run still triggered successfully -- sanity guard.
    testbase.assert_equal(view.state, BuildRunState.RUNNING)
    return


def dispatcher_transport_or(transport: InMemoryTransport) -> InMemoryTransport:
    """
        Identity helper -- keeps the construction expression in
        :func:`test_envelope_job_kind_defaults_to_test_for_backward_compat`
        free of an inlined call per the project style guide.

        :param transport: The transport to return.

        :returns: The same transport.
    """
    rtnval = transport
    return rtnval
