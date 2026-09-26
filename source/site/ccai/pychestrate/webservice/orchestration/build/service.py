"""
.. module:: orchestration.build.service
    :synopsis: Build-orchestration facade — trigger / mirror / read.

Ships:

* :func:`trigger_run` — resolve runner kind → validate inputs
  → compute repro digest → persist BuildRun + toolchain
  snapshots → build + sign a ``job_kind=build`` JobEnvelope →
  dispatch it through the wired :class:`JobDispatcher` so it
  queues for an enrolled client → drive the run-state machine
  through ``PENDING → DISPATCHING → DISPATCHED``. Emits
  ``entity.build.run_triggered`` then ``run_dispatched``.
* :func:`apply_run_terminal` — mirror a Layer-5 outcome onto
  the BuildRun (``layer5_run_id``, ``finished_at``,
  ``state``); emits STATE_CHANGED + COMPLETED / FAILED /
  CANCELLED as appropriate.
* :func:`get_build_run` / :func:`list_build_runs_for_project`.
* :func:`set_active_job_dispatcher` /
  :func:`set_active_results_backend` — module seams the Phase-6
  bootstrap publishes so the build service dispatches through
  the SAME long-poll queue test runs already use.

The client-side build-runner executor is a separate
``pychestrate-client`` PR; until it lands a dispatched build
envelope sits in the client's long-poll queue unconsumed --
the server side (this module) is complete.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.public_endpoint import run_forwarding_info, service_issuer
from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    DispatchRequestInputs,
    JobDispatcher,
)
from ccai.pychestrate.webservice.jobs.dispatch.errors import (
    DispatchError,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    JOB_KIND_BUILD,
    JobDeadline,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    JobSourceRef,
)
from ccai.pychestrate.webservice.jobs.results import (
    SharedResultsBackend,
)
from ccai.pychestrate.webservice.jobs.run.state import (
    RunEvent,
    RunNotFoundError as RunStateNotFoundError,
    create_run as create_run_state,
    get_snapshot as get_run_state_snapshot,
    transition as transition_run_state,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.orchestration.build import repository
from ccai.pychestrate.webservice.orchestration.build.errors import (
    BuildDispatchFailedError,
    BuildDispatchUnavailableError,
    BuildInputsInvalidError,
    BuildRunNotFoundError,
    BuildRunnerKindUnknownError,
    BuildSourceIntegrationUnknownError,
)
from ccai.pychestrate.webservice.orchestration.build.events import (
    BuildEventTopics,
)
from ccai.pychestrate.webservice.orchestration.build.factories.runner_protocol import (
    BuildRunnerKindProtocol,
)
from ccai.pychestrate.webservice.orchestration.build.models import (
    BuildRun,
    BuildRunState,
    BuildToolchainSnapshot,
)
from ccai.pychestrate.webservice.orchestration.build.repro_snapshot import (
    BuildToolchainEntry,
    ReproSnapshot,
    compute_repro_digest,
)
from ccai.pychestrate.webservice.orchestration.source import (
    service as source_service,
)
from ccai.pychestrate.webservice.orchestration.source.errors import (
    ScmConfigNotFoundError,
)


BUILD_RUNNER_KIND_PROTOCOL: str = "build_runner_kind"
LIST_BUILD_RUNS_DEFAULT_LIMIT: int = 50
TERMINAL_STATES: Tuple[BuildRunState, ...] = (
    BuildRunState.COMPLETED,
    BuildRunState.FAILED,
    BuildRunState.CANCELLED,
)
BUILD_JOB_TYPE_PREFIX: str = "build-"
# Reserved annotations key the resolved source reference is mirrored
# under so the build read / list routes can echo the ``source`` block.
BUILD_SOURCE_ANNOTATION_KEY: str = "__source_integration__"
DEFAULT_BUILD_SOFT_DEADLINE_SECONDS: int = 1800
DEFAULT_BUILD_HARD_DEADLINE_SECONDS: int = 3600

_LOGGER = logging.getLogger("pychestrate.builds.service")


# ---------------------------------------------------------------------------
# Bootstrap-published seams
# ---------------------------------------------------------------------------
#
# The Phase-6 bootstrap constructs a single :class:`JobDispatcher` (over the
# production :class:`LongPollTransport`) and publishes it here so build
# dispatches land in the SAME long-poll queue enrolled clients already poll
# for test runs.

ACTIVE_JOB_DISPATCHER: Optional[JobDispatcher] = None
ACTIVE_RESULTS_BACKEND: Optional[SharedResultsBackend] = None


def set_active_job_dispatcher(*, dispatcher: Optional[JobDispatcher]) -> None:
    """
        Publish the process-wide :class:`JobDispatcher` the build
        service dispatches build job envelopes through.

        :param dispatcher: The dispatcher constructed by the Phase-6
                           bootstrap, or ``None`` to clear the seam.

        :returns: None.
    """
    global ACTIVE_JOB_DISPATCHER
    ACTIVE_JOB_DISPATCHER = dispatcher
    return


def set_active_results_backend(
        *,
        backend: Optional[SharedResultsBackend]
    ) -> None:
    """
        Publish the shared results backend the build service
        allocates build result-tree prefixes against.

        :param backend: Shared results backend, or ``None`` to clear
                        the seam (a ``local-test`` backend is then
                        constructed on demand).

        :returns: None.
    """
    global ACTIVE_RESULTS_BACKEND
    ACTIVE_RESULTS_BACKEND = backend
    return


@dataclass(frozen=True)
class BuildRunInputs:
    """
        Caller-supplied build-run inputs.

        :param runner_kind: Stable runner-kind identifier
                            (``"makefile"`` for the M1
                            reference).
        :param runner_inputs: Free-form input dict consumed by
                              the runner kind.
        :param input_files: ``{path: content_sha256}`` —
                            material in the repro digest.
        :param toolchain: Tuple of :class:`BuildToolchainEntry`.
        :param env: ``{key: value}`` — material in the repro
                    digest.
        :param annotations: Free-form metadata persisted on
                            the BuildRun.
        :param source_integration_id: Optional UUID of a registered
                                      ``source-integration``. When
                                      supplied, the build service
                                      resolves it into the structured
                                      ``source`` block of the build
                                      job envelope. ``None`` leaves
                                      the envelope without a
                                      ``source`` block -- the client
                                      falls back to its
                                      ``runner_inputs.git_url``
                                      convention.
    """
    runner_kind: str
    runner_inputs: Mapping[str, Any] = field(default_factory=dict)
    input_files: Mapping[str, str] = field(default_factory=dict)
    toolchain: Tuple[BuildToolchainEntry, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    annotations: Mapping[str, Any] = field(default_factory=dict)
    source_integration_id: Optional[str] = None


@dataclass(frozen=True)
class BuildTriggerAspects:
    """
        Caller-tunable trigger knobs.

        :param actor_id: Optional actor UUID persisted on the
                         row.
        :param pipeline_run_id: Optional pipeline-run id when
                                the trigger came from
                                6-pipeline-definition.
        :param pipeline_step_run_id: Optional pipeline-step-run
                                     id (peer to the above).
        :param candidates: Eligible dispatch candidates the
                           dispatcher picks the target client/pod
                           from. The REST route builds these from
                           the project's enrolled, REGISTERED pods
                           (the same capability-based selection the
                           test orchestrator uses). An empty tuple
                           means "no eligible pod" and yields a
                           :class:`BuildDispatchFailedError`.
        :param project_slug: Project slug, sanitized into the
                             results-backend prefix.
        :param issuer: Service DNS-name + release string stamped
                       on the build job envelope; ``None`` uses
                       :func:`public_endpoint.service_issuer`.
        :param soft_deadline_seconds: Build soft deadline relative
                                      to trigger time.
        :param hard_deadline_seconds: Build hard deadline relative
                                      to trigger time.
    """
    actor_id: Optional[str] = None
    pipeline_run_id: Optional[str] = None
    pipeline_step_run_id: Optional[str] = None
    candidates: Sequence[DispatchCandidate] = field(default_factory=tuple)
    project_slug: str = ""
    issuer: Optional[str] = None
    soft_deadline_seconds: int = DEFAULT_BUILD_SOFT_DEADLINE_SECONDS
    hard_deadline_seconds: int = DEFAULT_BUILD_HARD_DEADLINE_SECONDS


@dataclass(frozen=True)
class BuildToolchainSnapshotView:
    """
        Caller-facing toolchain row.
    """
    toolchain_key: str
    version: str
    fingerprint_sha256: str


@dataclass(frozen=True)
class BuildRunView:
    """
        Caller-facing read-model.
    """
    run_id: str
    project_id: str
    runner_kind: str
    repro_digest_sha256: str
    state: BuildRunState
    layer5_run_id: Optional[str]
    pipeline_run_id: Optional[str]
    pipeline_step_run_id: Optional[str]
    actor_id: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    final_state_reason: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    annotations: Mapping[str, Any] = field(default_factory=dict)
    toolchain: Tuple[BuildToolchainSnapshotView, ...] = ()
    run_state: Optional[str] = None
    dispatch_attempt_id: Optional[str] = None
    envelope_id: Optional[str] = None
    source: Optional[Dict[str, Any]] = None


def trigger_run(
        *,
        db_session: DbSession,
        project_id: str,
        inputs: BuildRunInputs,
        aspects: Optional[BuildTriggerAspects] = None
    ) -> BuildRunView:
    """
        Resolve the runner kind, validate inputs, compute the
        repro digest, persist a BuildRun + toolchain snapshots,
        then build + sign a ``job_kind=build`` JobEnvelope and
        dispatch it through the wired :class:`JobDispatcher` so
        the build job queues for an enrolled client.

        On a successful dispatch the run-state machine drives the
        run through ``PENDING → DISPATCHING → DISPATCHED`` and the
        :class:`BuildRun` row flips to ``RUNNING`` -- i.e. the same
        "dispatched to a client over the wire" state test runs
        reach. Emits :data:`BuildEventTopics.TRIGGERED` then
        :data:`BuildEventTopics.DISPATCHED`.

        :raises: BuildRunnerKindUnknownError when ``runner_kind``
                 has no registered factory.
        :raises: BuildInputsInvalidError when the runner kind's
                 ``validate_inputs`` rejects the payload.
        :raises: BuildDispatchUnavailableError when no
                 :class:`JobDispatcher` is wired.
        :raises: BuildDispatchFailedError when the dispatcher
                 rejects the job (no eligible pod, transport
                 failure, ...).
    """
    if inputs.runner_kind is None or len(inputs.runner_kind) == 0:
        err_lines = ["BuildRunInputs.runner_kind must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise BuildInputsInvalidError(err_msg) from None

    runner_cls = _resolve_runner(runner_kind=inputs.runner_kind)
    ok, issues = runner_cls.validate_inputs(inputs=inputs.runner_inputs)
    if ok is False:
        err_lines = [
            "Build runner '{}' rejected inputs: {} issue(s).".format(
                inputs.runner_kind, len(issues),
            ),
        ]
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise BuildInputsInvalidError(err_msg) from None

    # Resolve the registered source-integration -- if one was named --
    # before any row is persisted so an unknown id fails the trigger
    # cleanly. ``None`` leaves the envelope without a structured
    # ``source`` block (client falls back to runner_inputs.git_url).
    source_ref = _resolve_source_reference(
        db_session=db_session,
        source_integration_id=inputs.source_integration_id,
    )

    snapshot = ReproSnapshot(
        input_files=dict(inputs.input_files),
        toolchain=tuple(inputs.toolchain),
        env=dict(inputs.env),
    )
    digest = compute_repro_digest(snapshot=snapshot)

    effective = aspects or BuildTriggerAspects()
    now = utc_now()

    # The resolved source reference is persisted on the BuildRun
    # ``annotations`` under a reserved key so it round-trips through
    # the read / list routes -- the envelope ``source`` block is the
    # authoritative copy, this is the durable mirror for diagnostics.
    persisted_annotations = dict(inputs.annotations)
    if source_ref is not None:
        persisted_annotations[BUILD_SOURCE_ANNOTATION_KEY] = {
            "kind": source_ref.kind,
            "url": source_ref.url,
            "ref": source_ref.ref,
            "integration_id": source_ref.integration_id,
            "credentials_ref": source_ref.credentials_ref,
        }

    run_row = repository.insert_build_run(
        db_session=db_session,
        project_id=project_id,
        runner_kind=inputs.runner_kind,
        repro_digest_sha256=digest,
        actor_id=effective.actor_id,
        pipeline_run_id=effective.pipeline_run_id,
        pipeline_step_run_id=effective.pipeline_step_run_id,
        inputs=dict(inputs.runner_inputs),
        annotations=persisted_annotations,
        started_at=now,
    )
    for entry in inputs.toolchain:
        repository.insert_toolchain_snapshot_row(
            db_session=db_session,
            run_id=str(run_row.run_id),
            toolchain_key=entry.key,
            version=entry.version,
            fingerprint_sha256=entry.fingerprint_sha256,
        )

    run_id = str(run_row.run_id)
    job_type = BUILD_JOB_TYPE_PREFIX + inputs.runner_kind

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=BuildEventTopics.TRIGGERED,
            payload={
                "run_id": run_id,
                "project_id": project_id,
                "runner_kind": inputs.runner_kind,
                "repro_digest_sha256": digest,
                "pipeline_run_id": effective.pipeline_run_id,
                "pipeline_step_run_id": effective.pipeline_step_run_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    # Run-state machine: create the run + advance to DISPATCHING
    # before the dispatcher's own commit so the audit trail reflects
    # the trigger phase distinctly -- exactly as the test
    # orchestrator does.
    create_run_state(
        db_session=db_session,
        run_id=run_id,
        project_id=project_id,
        job_type=job_type,
    )
    transition_run_state(
        db_session=db_session,
        run_id=run_id,
        event=RunEvent.DISPATCH_STARTED,
        actor="system:build-orchestrator",
        reason="runner_kind={}".format(inputs.runner_kind),
    )

    dispatch_outcome = _dispatch_build_job(
        db_session=db_session,
        run_id=run_id,
        project_id=project_id,
        job_type=job_type,
        digest=digest,
        inputs=inputs,
        aspects=effective,
        triggered_at=now,
        source_ref=source_ref,
    )

    # Happy path: the build job envelope is queued for the target
    # client. The BuildRun row flips PENDING -> RUNNING (dispatched +
    # executing on a client); the run-state machine row stays at
    # DISPATCHING -- the dispatch-receipt path advances it onward,
    # exactly as it does for test runs. ``layer5_run_id`` records the
    # dispatch attempt id.
    run_row.state = BuildRunState.RUNNING
    run_row.layer5_run_id = dispatch_outcome.attempt_id
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=BuildEventTopics.DISPATCHED,
            payload={
                "run_id": run_id,
                "project_id": project_id,
                "runner_kind": inputs.runner_kind,
                "dispatch_attempt_id": dispatch_outcome.attempt_id,
                "envelope_id": dispatch_outcome.envelope_id,
                "client_id": dispatch_outcome.client_id,
                "pod_id": dispatch_outcome.pod_id,
                "transport": dispatch_outcome.transport_name,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    _LOGGER.info(
        "pychestrate.builds.dispatched run_id=%s envelope_id=%s"
        " client_id=%s pod_id=%s transport=%s",
        run_id,
        dispatch_outcome.envelope_id,
        dispatch_outcome.client_id,
        dispatch_outcome.pod_id,
        dispatch_outcome.transport_name,
    )

    rtnval = get_build_run(db_session=db_session, run_id=run_id)
    return rtnval


def _dispatch_build_job(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        job_type: str,
        digest: str,
        inputs: BuildRunInputs,
        aspects: BuildTriggerAspects,
        triggered_at: datetime,
        source_ref: Optional[JobSourceRef] = None
    ):
    """
        Build a signed ``job_kind=build`` JobEnvelope describing the
        build job and dispatch it through the wired
        :class:`JobDispatcher`.

        The build job envelope's ``params`` section carries the
        build-spec payload: the runner kind, the runner inputs, the
        repro digest, the toolchain, and the env / input-file
        material. A future ``pychestrate-client`` build-runner
        executor consumes this payload.

        On dispatch failure the run-state machine is driven to
        ``DISPATCH_FAILED`` and the BuildRun row to ``FAILED`` so the
        failure is durably recorded before the error surfaces.

        :param db_session: Active SQLAlchemy session.
        :param run_id: BuildRun UUID (also the run-state run id).
        :param project_id: Owning project UUID.
        :param job_type: ``build-<runner_kind>`` job-type string.
        :param digest: Repro digest stamped into the build spec.
        :param inputs: Caller-supplied :class:`BuildRunInputs`.
        :param aspects: Effective :class:`BuildTriggerAspects`.
        :param triggered_at: Trigger timestamp (deadline anchor).
        :param source_ref: Optional resolved :class:`JobSourceRef`
                            embedded as the envelope ``source`` block.

        :returns: The :class:`DispatchOutcome`.
        :raises: BuildDispatchUnavailableError, BuildDispatchFailedError.
    """
    dispatcher = ACTIVE_JOB_DISPATCHER
    if dispatcher is None:
        _fail_build_run(
            db_session=db_session,
            run_id=run_id,
            reason="job dispatcher not wired",
        )
        err_lines = ["Build dispatch failed -- no JobDispatcher is wired."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append(
            "HINT: bootstrap_phase6_runtime publishes the dispatcher"
            " via set_active_job_dispatcher().")
        err_msg = os.linesep.join(err_lines)
        raise BuildDispatchUnavailableError(err_msg) from None

    backend = ACTIVE_RESULTS_BACKEND
    if backend is None:
        backend = SharedResultsBackend(backend_driver="local-test")
    allocation = backend.allocate(
        db_session=db_session,
        run_id=run_id,
        project_id=project_id,
        project_slug=aspects.project_slug,
        job_type=job_type,
    )

    build_spec: Dict[str, Any] = {
        "runner_kind": inputs.runner_kind,
        "runner_inputs": dict(inputs.runner_inputs),
        "repro_digest_sha256": digest,
        "input_files": dict(inputs.input_files),
        "env": dict(inputs.env),
        "toolchain": [
            {
                "key": entry.key,
                "version": entry.version,
                "fingerprint_sha256": entry.fingerprint_sha256,
            }
            for entry in inputs.toolchain
        ],
    }

    soft_deadline = triggered_at + timedelta(
        seconds=aspects.soft_deadline_seconds,
    )
    hard_deadline = triggered_at + timedelta(
        seconds=aspects.hard_deadline_seconds,
    )

    pipeline_ref: Optional[JobPipelineRef] = None
    if aspects.pipeline_run_id is not None:
        pipeline_ref = JobPipelineRef(
            pipeline_id=aspects.pipeline_run_id,
            instance_id=run_id,
        )

    # When a source integration resolved, its default ref drives the
    # envelope branch; the caller's runner_inputs.branch still wins
    # when it was set explicitly so a one-off branch override holds.
    default_branch = "main"
    if source_ref is not None:
        default_branch = source_ref.ref
    branch = str(inputs.runner_inputs.get("branch", default_branch))

    dispatch_inputs = DispatchRequestInputs(
        run_id=run_id,
        project_id=project_id,
        job_id=run_id,
        job_name="build:{}".format(inputs.runner_kind),
        job_type=job_type,
        job_kind=JOB_KIND_BUILD,
        issuer=aspects.issuer or service_issuer(),
        refs=JobRefs(
            branch=branch,
            build=str(inputs.runner_inputs.get("build", "")),
            flavor=str(inputs.runner_inputs.get("flavor", "")),
            release=str(inputs.runner_inputs.get("release", "")),
            commit_sha=str(inputs.runner_inputs.get("commit_sha", "0" * 40)),
        ),
        source=source_ref,
        params=build_spec,
        scoped_secrets=tuple(),
        results=JobResultsLocator(
            backend_key_prefix=allocation.backend_key_prefix,
            backend_driver=allocation.backend_driver,
        ),
        forwarding=run_forwarding_info(run_id=run_id),
        deadline=JobDeadline(
            soft_deadline_at=soft_deadline,
            hard_deadline_at=hard_deadline,
        ),
        pipeline=pipeline_ref,
        extension_claims={},
        candidates=tuple(aspects.candidates),
    )

    try:
        rtnval = dispatcher.dispatch(
            db_session=db_session,
            inputs=dispatch_inputs,
        )
    except DispatchError as xcpt:
        _fail_build_run(
            db_session=db_session,
            run_id=run_id,
            reason="dispatch failed: {}".format(str(xcpt)),
        )
        err_lines = ["Build dispatch failed."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_lines)
        raise BuildDispatchFailedError(err_msg) from xcpt

    return rtnval


def _resolve_source_reference(
        *,
        db_session: DbSession,
        source_integration_id: Optional[str]
    ) -> Optional[JobSourceRef]:
    """
        Resolve a caller-supplied ``source_integration_id`` into the
        structured :class:`JobSourceRef` the build job envelope
        carries. Returns ``None`` when no integration was named so
        the envelope carries no ``source`` block and the client falls
        back to its ``runner_inputs.git_url`` convention.

        :param db_session: Active SQLAlchemy session.
        :param source_integration_id: Optional registered
                                      source-integration UUID.

        :returns: :class:`JobSourceRef` or ``None``.
        :raises: BuildSourceIntegrationUnknownError when the id
                 resolves to no registered source integration.
    """
    if source_integration_id is None or len(source_integration_id) == 0:
        rtnval = None
        return rtnval

    try:
        view = source_service.resolve_source_reference(
            db_session=db_session,
            integration_id=source_integration_id,
        )
    except ScmConfigNotFoundError as xcpt:
        err_lines = ["Build trigger named an unknown source integration."]
        err_lines.append("SOURCE_INTEGRATION_ID: {}".format(
            source_integration_id,
        ))
        err_lines.append("DETAIL: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_lines)
        raise BuildSourceIntegrationUnknownError(err_msg) from xcpt

    rtnval = JobSourceRef(
        kind=view.kind,
        url=view.url,
        ref=view.ref,
        integration_id=view.integration_id,
        credentials_ref=view.credentials_ref,
    )
    return rtnval


def _fail_build_run(
        *,
        db_session: DbSession,
        run_id: str,
        reason: str
    ) -> None:
    """
        Durably record a dispatch failure: drive the run-state
        machine to ``DISPATCH_FAILED`` and flip the BuildRun row to
        ``FAILED`` with ``final_state_reason``. Best-effort -- a
        secondary failure here is swallowed so the original dispatch
        error is what the caller sees.

        :param db_session: Active SQLAlchemy session.
        :param run_id: BuildRun UUID.
        :param reason: Human-readable failure reason.

        :returns: None.
    """
    try:
        transition_run_state(
            db_session=db_session,
            run_id=run_id,
            event=RunEvent.DISPATCH_ABORTED,
            actor="system:build-orchestrator",
            reason=reason,
        )
    except Exception:
        _LOGGER.warning(
            "pychestrate.builds.dispatch_fail.run_state_transition_skipped"
            " run_id=%s", run_id,
        )

    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is not None and row.state not in TERMINAL_STATES:
        row.state = BuildRunState.FAILED
        row.finished_at = utc_now()
        row.final_state_reason = reason
        db_session.flush()
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=BuildEventTopics.FAILED,
                payload={
                    "run_id": run_id,
                    "project_id": str(row.project_id),
                    "state": BuildRunState.FAILED.value,
                    "reason": reason,
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()
    return


def apply_run_terminal(
        *,
        db_session: DbSession,
        run_id: str,
        final_state: BuildRunState,
        layer5_run_id: Optional[str] = None,
        reason: str = ""
    ) -> BuildRunView:
    """
        Mirror a Layer-5 outcome onto a build run. Idempotent
        on already-terminal rows. Emits STATE_CHANGED on every
        call and the kind-specific COMPLETED / FAILED /
        CANCELLED topic.

        :raises: BuildRunNotFoundError on miss.
        :raises: BuildInputsInvalidError when ``final_state``
                 is not in the M1 terminal set.
    """
    if final_state not in TERMINAL_STATES:
        err_lines = ["apply_run_terminal requires a terminal build state."]
        err_lines.append("RECEIVED: {}".format(final_state.value))
        err_msg = os.linesep.join(err_lines)
        raise BuildInputsInvalidError(err_msg) from None

    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is None:
        err_lines = ["Build run not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise BuildRunNotFoundError(err_msg) from None

    if row.state in TERMINAL_STATES:
        rtnval = get_build_run(db_session=db_session, run_id=run_id)
        return rtnval

    now = utc_now()
    row.state = final_state
    if layer5_run_id is not None:
        row.layer5_run_id = layer5_run_id
    row.finished_at = now
    row.final_state_reason = reason
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=BuildEventTopics.STATE_CHANGED,
            payload={
                "run_id": str(row.run_id),
                "project_id": str(row.project_id),
                "state": final_state.value,
                "layer5_run_id": layer5_run_id,
            },
            source_event_id=new_uuid(),
        ),
    )

    final_topic = BuildEventTopics.COMPLETED
    if final_state == BuildRunState.FAILED:
        final_topic = BuildEventTopics.FAILED
    elif final_state == BuildRunState.CANCELLED:
        final_topic = BuildEventTopics.CANCELLED
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=final_topic,
            payload={
                "run_id": str(row.run_id),
                "project_id": str(row.project_id),
                "state": final_state.value,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_build_run(db_session=db_session, run_id=run_id)
    return rtnval


def get_build_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> BuildRunView:
    """
        Read a build run + its toolchain rows.

        :raises: BuildRunNotFoundError on miss.
    """
    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is None:
        err_lines = ["Build run not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise BuildRunNotFoundError(err_msg) from None
    toolchain_rows = repository.list_toolchain_for_run(
        db_session=db_session, run_id=run_id,
    )
    run_state = _resolve_run_state(db_session=db_session, run_id=run_id)
    rtnval = _to_view(
        row=row,
        toolchain_rows=toolchain_rows,
        run_state=run_state,
    )
    return rtnval


def list_build_runs_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        limit: int = LIST_BUILD_RUNS_DEFAULT_LIMIT
    ) -> List[BuildRunView]:
    """
        Recent build runs for a project, newest-first.
    """
    rows = repository.list_runs_for_project(
        db_session=db_session, project_id=project_id, limit=limit,
    )
    rtnval: List[BuildRunView] = []
    for row in rows:
        run_id = str(row.run_id)
        toolchain_rows = repository.list_toolchain_for_run(
            db_session=db_session, run_id=run_id,
        )
        run_state = _resolve_run_state(db_session=db_session, run_id=run_id)
        rtnval.append(
            _to_view(
                row=row,
                toolchain_rows=toolchain_rows,
                run_state=run_state,
            )
        )
    return rtnval


def _resolve_runner(*, runner_kind: str) -> Type[BuildRunnerKindProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=BUILD_RUNNER_KIND_PROTOCOL,
    )
    for impl in candidates:
        if impl.runner_kind() == runner_kind:
            return impl
    err_lines = ["No registered build_runner_kind for name."]
    err_lines.append("RUNNER_KIND: {}".format(runner_kind))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.runner_kind() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise BuildRunnerKindUnknownError(err_msg) from None


def _resolve_run_state(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[str]:
    """
        Best-effort read of the run-state-machine state for a build
        run. Returns ``None`` when no run-state row exists yet (the
        build was triggered before dispatch wiring landed).

        :param db_session: Active SQLAlchemy session.
        :param run_id: BuildRun UUID.

        :returns: Run-state value string or ``None``.
    """
    try:
        snapshot = get_run_state_snapshot(
            db_session=db_session, run_id=run_id,
        )
    except RunStateNotFoundError:
        rtnval = None
        return rtnval
    rtnval = snapshot.state.value
    return rtnval


def _to_view(
        *,
        row: BuildRun,
        toolchain_rows: List[BuildToolchainSnapshot],
        run_state: Optional[str] = None
    ) -> BuildRunView:
    toolchain = tuple(
        BuildToolchainSnapshotView(
            toolchain_key=t.toolchain_key,
            version=t.version,
            fingerprint_sha256=t.fingerprint_sha256,
        )
        for t in toolchain_rows
    )
    all_annotations = dict(row.annotations or {})
    source_block = all_annotations.pop(BUILD_SOURCE_ANNOTATION_KEY, None)
    if isinstance(source_block, dict) is False:
        source_block = None

    rtnval = BuildRunView(
        run_id=str(row.run_id),
        project_id=str(row.project_id),
        runner_kind=row.runner_kind,
        repro_digest_sha256=row.repro_digest_sha256,
        state=row.state,
        layer5_run_id=(
            str(row.layer5_run_id) if row.layer5_run_id is not None else None
        ),
        pipeline_run_id=(
            str(row.pipeline_run_id)
            if row.pipeline_run_id is not None else None
        ),
        pipeline_step_run_id=(
            str(row.pipeline_step_run_id)
            if row.pipeline_step_run_id is not None else None
        ),
        actor_id=(
            str(row.actor_id) if row.actor_id is not None else None
        ),
        started_at=row.started_at,
        finished_at=row.finished_at,
        final_state_reason=row.final_state_reason,
        inputs=dict(row.inputs or {}),
        annotations=all_annotations,
        toolchain=toolchain,
        run_state=run_state,
        dispatch_attempt_id=(
            str(row.layer5_run_id)
            if row.layer5_run_id is not None else None
        ),
        source=source_block,
    )
    return rtnval
