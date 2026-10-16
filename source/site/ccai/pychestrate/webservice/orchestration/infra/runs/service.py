"""
.. module:: orchestration.infra.runs.service
    :synopsis: Infra-orchestration facade — trigger / plan / mirror / read.

Ships:

* :func:`trigger_run` — resolve env + driver, validate inputs
  + action support, persist a PENDING InfraRun, then build +
  sign a ``job_kind=provision`` JobEnvelope and dispatch it
  through the wired :class:`JobDispatcher` so the provisioning
  job queues for an enrolled client. Drives the run-state
  machine through ``PENDING → DISPATCHING``. Emits
  ``entity.infra.run_triggered`` then ``run_dispatched``.
* :func:`record_plan_summary` — store the per-plan summary +
  artifact ref + diff digest on the run row, emit
  PLAN_RECORDED.
* :func:`apply_run_terminal` — mirror a Layer-5 outcome onto
  the InfraRun; emits STATE_CHANGED + the kind-specific
  COMPLETED / FAILED / CANCELLED / REJECTED_BY_GUARD topic.
* :func:`get_infra_run` /
  :func:`list_infra_runs_for_environment`.
* :func:`set_active_job_dispatcher` /
  :func:`set_active_results_backend` — module seams the Phase-6
  bootstrap publishes so the infra-runs service dispatches
  through the SAME long-poll queue test + build runs already
  use.

The bound environment must be ACTIVE or FROZEN at trigger time;
DESTROY against a non-active env is allowed for cleanup, but
APPLY against a frozen env is rejected here. ARCHIVED /
DESTROYED envs reject every trigger.

The client-side provision executor is a separate
``pychestrate-client`` PR; until it lands a dispatched provision
envelope sits in the client's long-poll queue unconsumed -- the
server side (this module) is complete.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import hashlib
import json
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
    JOB_KIND_PROVISION,
    JobDeadline,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
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
from ccai.pychestrate.webservice.orchestration.infra.environment import (
    repository as env_repository,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.models import (
    EnvironmentState,
)
from ccai.pychestrate.webservice.orchestration.infra.runs import repository
from ccai.pychestrate.webservice.orchestration.infra.runs.errors import (
    InfraDispatchFailedError,
    InfraDispatchUnavailableError,
    InfraDriverUnknownError,
    InfraEnvironmentStateError,
    InfraInputsInvalidError,
    InfraRunNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.events import (
    InfraEventTopics,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.factories.driver_protocol import (
    InfraToolDriverProtocol,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.models import (
    InfraAction,
    InfraRun,
    InfraRunState,
)


INFRA_TOOL_DRIVER_PROTOCOL: str = "infra_tool_driver"
LIST_INFRA_RUNS_DEFAULT_LIMIT: int = 50
TERMINAL_RUN_STATES: Tuple[InfraRunState, ...] = (
    InfraRunState.COMPLETED,
    InfraRunState.FAILED,
    InfraRunState.CANCELLED,
    InfraRunState.REJECTED_BY_GUARD,
)
PROVISION_JOB_TYPE_PREFIX: str = "provision-"
DEFAULT_PROVISION_SOFT_DEADLINE_SECONDS: int = 1800
DEFAULT_PROVISION_HARD_DEADLINE_SECONDS: int = 3600

_LOGGER = logging.getLogger("pychestrate.infra.runs.service")


# ---------------------------------------------------------------------------
# Bootstrap-published seams
# ---------------------------------------------------------------------------
#
# The Phase-6 bootstrap constructs a single :class:`JobDispatcher` (over the
# production :class:`LongPollTransport`) and publishes it here so provisioning
# dispatches land in the SAME long-poll queue enrolled clients already poll
# for test + build runs.

ACTIVE_JOB_DISPATCHER: Optional[JobDispatcher] = None
ACTIVE_RESULTS_BACKEND: Optional[SharedResultsBackend] = None


def set_active_job_dispatcher(*, dispatcher: Optional[JobDispatcher]) -> None:
    """
        Publish the process-wide :class:`JobDispatcher` the
        infra-runs service dispatches provision job envelopes
        through.

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
        Publish the shared results backend the infra-runs service
        allocates provision result-tree prefixes against.

        :param backend: Shared results backend, or ``None`` to clear
                        the seam (a ``local-test`` backend is then
                        constructed on demand).

        :returns: None.
    """
    global ACTIVE_RESULTS_BACKEND
    ACTIVE_RESULTS_BACKEND = backend
    return


class ResourceOpKind(str, enum.Enum):
    """
        Per-resource op kind on a plan summary.
    """
    ADD = "add"
    CHANGE = "change"
    DESTROY = "destroy"
    NO_OP = "no_op"


@dataclass(frozen=True)
class ResourceOp:
    """
        One per-resource operation on a plan summary.
    """
    resource_address: str
    op: ResourceOpKind
    module_path: str = ""


@dataclass(frozen=True)
class PlanSummary:
    """
        Aggregate plan output. Surfaced on
        :data:`InfraEventTopics.PLAN_RECORDED` and persisted on
        the run row.
    """
    resources_to_add: int
    resources_to_change: int
    resources_to_destroy: int
    resource_ops: Tuple[ResourceOp, ...] = ()


@dataclass(frozen=True)
class InfraRunInputs:
    """
        Caller-supplied infra-run inputs.

        :param environment_id: Bound environment.
        :param driver_name: Registered :class:`InfraToolDriverProtocol`
                            name.
        :param action: ``plan`` / ``apply`` / ``destroy``.
        :param driver_inputs: Driver-specific input dict.
    """
    environment_id: str
    driver_name: str
    action: InfraAction
    driver_inputs: Mapping[str, Any] = field(default_factory=dict)


def provision_params_for(*, inputs: InfraRunInputs, digest: str) -> Dict[str, Any]:
    """
        The ``params`` of a provisioning job's envelope: what the pod reads its driver, action and driver inputs from. Kept in one place so
        the service-and-pod contract (``specs/contracts/pod-job-contract.json``) checks exactly what is sent.

        :param inputs: The caller's infra-run inputs.
        :param digest: The canonical digest of the driver inputs.

        :returns: The params map.
    """
    rtnval: Dict[str, Any] = {
        "environment_id": inputs.environment_id,
        "action": inputs.action.value,
        "driver_name": inputs.driver_name,
        "driver_inputs": dict(inputs.driver_inputs),
        "inputs_canonical_sha256": digest,
    }
    return rtnval


@dataclass(frozen=True)
class InfraTriggerAspects:
    """
        Caller-tunable knobs.

        :param actor_id: Optional actor UUID persisted on the row.
        :param actor_role_set: Caller role set persisted on the row.
        :param replay_of: Optional run id this run replays.
        :param candidates: Eligible dispatch candidates the
                           dispatcher picks the target client/pod
                           from. The REST route builds these from
                           the project's enrolled, REGISTERED pods
                           (the same capability-based selection the
                           test + build orchestrators use). An empty
                           tuple means "no eligible pod" and yields a
                           :class:`InfraDispatchFailedError`.
        :param project_slug: Project slug, sanitized into the
                             results-backend prefix.
        :param issuer: Service DNS-name + release string stamped on
                       the provision job envelope; ``None`` uses
                       :func:`public_endpoint.service_issuer`.
        :param soft_deadline_seconds: Provision soft deadline
                                      relative to trigger time.
        :param hard_deadline_seconds: Provision hard deadline
                                      relative to trigger time.
    """
    actor_id: Optional[str] = None
    actor_role_set: Tuple[str, ...] = ()
    replay_of: Optional[str] = None
    candidates: Sequence[DispatchCandidate] = field(default_factory=tuple)
    project_slug: str = ""
    issuer: Optional[str] = None
    soft_deadline_seconds: int = DEFAULT_PROVISION_SOFT_DEADLINE_SECONDS
    hard_deadline_seconds: int = DEFAULT_PROVISION_HARD_DEADLINE_SECONDS


@dataclass(frozen=True)
class InfraRunView:
    """
        Caller-facing read-model.
    """
    run_id: str
    project_id: str
    environment_id: str
    driver_name: str
    action: InfraAction
    state: InfraRunState
    layer5_run_id: Optional[str]
    actor_id: Optional[str]
    actor_role_set: Tuple[str, ...]
    inputs: Mapping[str, Any]
    inputs_canonical_sha256: str
    plan_summary: Optional[PlanSummary]
    plan_artifact_ref: Optional[str]
    plan_diff_digest_sha256: str
    plan_issued_at: Optional[datetime]
    replay_of: Optional[str]
    output_digest_sha256: str
    failing_guard_rule_id: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    final_state_reason: str
    run_state: Optional[str] = None
    dispatch_attempt_id: Optional[str] = None


def trigger_run(
        *,
        db_session: DbSession,
        project_id: str,
        inputs: InfraRunInputs,
        aspects: Optional[InfraTriggerAspects] = None
    ) -> InfraRunView:
    """
        Resolve env + driver, validate inputs, persist a PENDING
        InfraRun, then build + sign a ``job_kind=provision``
        JobEnvelope and dispatch it through the wired
        :class:`JobDispatcher` so the provisioning job queues for an
        enrolled client.

        On a successful dispatch the run-state machine drives the
        run through ``PENDING → DISPATCHING`` and the
        :class:`InfraRun` row flips to ``RUNNING`` -- i.e. the same
        "dispatched to a client over the wire" state test + build
        runs reach. Emits :data:`InfraEventTopics.TRIGGERED` then
        :data:`InfraEventTopics.DISPATCHED`.

        :raises: InfraEnvironmentStateError when the bound
                 env is in a state that forbids the action.
        :raises: InfraDriverUnknownError when ``driver_name``
                 has no registered factory.
        :raises: InfraInputsInvalidError when the driver
                 rejects the inputs.
        :raises: InfraDispatchUnavailableError when no
                 :class:`JobDispatcher` is wired.
        :raises: InfraDispatchFailedError when the dispatcher
                 rejects the job (no eligible pod, transport
                 failure, ...).
    """
    env = env_repository.find_by_id(
        db_session=db_session, environment_id=inputs.environment_id,
    )
    if env is None:
        err_lines = ["Environment not found."]
        err_lines.append("ENVIRONMENT_ID: {}".format(inputs.environment_id))
        err_msg = os.linesep.join(err_lines)
        raise InfraEnvironmentStateError(err_msg) from None

    if str(env.project_id) != project_id:
        err_lines = ["Environment project mismatch."]
        err_lines.append("ENVIRONMENT_ID: {}".format(inputs.environment_id))
        err_lines.append("EXPECTED_PROJECT: {}".format(project_id))
        err_lines.append("ACTUAL_PROJECT: {}".format(env.project_id))
        err_msg = os.linesep.join(err_lines)
        raise InfraEnvironmentStateError(err_msg) from None

    if env.state in (EnvironmentState.ARCHIVED, EnvironmentState.DESTROYED):
        err_lines = ["Cannot trigger infra run against terminal environment."]
        err_lines.append("ENVIRONMENT_ID: {}".format(inputs.environment_id))
        err_lines.append("ENVIRONMENT_STATE: {}".format(env.state.value))
        err_msg = os.linesep.join(err_lines)
        raise InfraEnvironmentStateError(err_msg) from None

    if (
        env.state == EnvironmentState.FROZEN
        and inputs.action != InfraAction.PLAN
    ):
        err_lines = ["Frozen environment only accepts the plan action."]
        err_lines.append("ENVIRONMENT_ID: {}".format(inputs.environment_id))
        err_lines.append("REQUESTED_ACTION: {}".format(inputs.action.value))
        err_msg = os.linesep.join(err_lines)
        raise InfraEnvironmentStateError(err_msg) from None

    driver_cls = _resolve_driver(driver_name=inputs.driver_name)
    if inputs.action.value not in driver_cls.supported_actions():
        err_lines = ["Driver does not support requested action."]
        err_lines.append("DRIVER: {}".format(inputs.driver_name))
        err_lines.append("ACTION: {}".format(inputs.action.value))
        err_lines.append("SUPPORTED: {}".format(
            ", ".join(driver_cls.supported_actions()),
        ))
        err_msg = os.linesep.join(err_lines)
        raise InfraInputsInvalidError(err_msg) from None

    ok, issues = driver_cls.validate_inputs(
        action=inputs.action.value, inputs=inputs.driver_inputs,
    )
    if ok is False:
        err_lines = [
            "Driver '{}' rejected inputs: {} issue(s).".format(
                inputs.driver_name, len(issues),
            ),
        ]
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise InfraInputsInvalidError(err_msg) from None

    canonical = json.dumps(
        dict(inputs.driver_inputs),
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    effective = aspects or InfraTriggerAspects()
    actor_role_set_csv = ",".join(effective.actor_role_set)
    now = utc_now()

    row = repository.insert_infra_run(
        db_session=db_session,
        project_id=project_id,
        environment_id=inputs.environment_id,
        driver_name=inputs.driver_name,
        action=inputs.action,
        actor_id=effective.actor_id,
        actor_role_set_csv=actor_role_set_csv,
        inputs=dict(inputs.driver_inputs),
        inputs_canonical_sha256=digest,
        replay_of=effective.replay_of,
        started_at=now,
    )
    run_id = str(row.run_id)
    job_type = PROVISION_JOB_TYPE_PREFIX + inputs.driver_name

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=InfraEventTopics.TRIGGERED,
            payload={
                "run_id": run_id,
                "project_id": project_id,
                "environment_id": inputs.environment_id,
                "driver_name": inputs.driver_name,
                "action": inputs.action.value,
                "inputs_canonical_sha256": digest,
                "replay_of": effective.replay_of,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    # Run-state machine: create the run + advance to DISPATCHING
    # before the dispatcher's own commit so the audit trail reflects
    # the trigger phase distinctly -- exactly as the test + build
    # orchestrators do.
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
        actor="system:infra-orchestrator",
        reason="driver_name={} action={}".format(
            inputs.driver_name, inputs.action.value,
        ),
    )

    dispatch_outcome = _dispatch_provision_job(
        db_session=db_session,
        run_id=run_id,
        project_id=project_id,
        job_type=job_type,
        digest=digest,
        inputs=inputs,
        aspects=effective,
        triggered_at=now,
    )

    # Happy path: the provision job envelope is queued for the target
    # client. The InfraRun row flips PENDING -> RUNNING (dispatched +
    # executing on a client); the run-state machine row stays at
    # DISPATCHING -- the dispatch-receipt path advances it onward,
    # exactly as it does for test + build runs. ``layer5_run_id``
    # records the dispatch attempt id.
    row.state = InfraRunState.RUNNING
    row.layer5_run_id = dispatch_outcome.attempt_id
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=InfraEventTopics.DISPATCHED,
            payload={
                "run_id": run_id,
                "project_id": project_id,
                "environment_id": inputs.environment_id,
                "driver_name": inputs.driver_name,
                "action": inputs.action.value,
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
        "pychestrate.infra.runs.dispatched run_id=%s envelope_id=%s"
        " client_id=%s pod_id=%s transport=%s",
        run_id,
        dispatch_outcome.envelope_id,
        dispatch_outcome.client_id,
        dispatch_outcome.pod_id,
        dispatch_outcome.transport_name,
    )

    rtnval = get_infra_run(db_session=db_session, run_id=run_id)
    return rtnval


def _dispatch_provision_job(
        *,
        db_session: DbSession,
        run_id: str,
        project_id: str,
        job_type: str,
        digest: str,
        inputs: "InfraRunInputs",
        aspects: "InfraTriggerAspects",
        triggered_at: datetime
    ) -> Any:
    """
        Build a signed ``job_kind=provision`` JobEnvelope describing
        the provisioning job and dispatch it through the wired
        :class:`JobDispatcher`.

        The provision job envelope's ``params`` section carries the
        provisioning-spec payload: the target environment, the
        provisioning action, the infra driver/tool, and the driver
        inputs. A future ``pychestrate-client`` provision executor
        consumes this payload.

        On dispatch failure the run-state machine is driven to
        ``DISPATCH_FAILED`` and the InfraRun row to ``FAILED`` so the
        failure is durably recorded before the error surfaces.

        :param db_session: Active SQLAlchemy session.
        :param run_id: InfraRun UUID (also the run-state run id).
        :param project_id: Owning project UUID.
        :param job_type: ``provision-<driver_name>`` job-type string.
        :param digest: Canonical-inputs digest stamped into the spec.
        :param inputs: Caller-supplied :class:`InfraRunInputs`.
        :param aspects: Effective :class:`InfraTriggerAspects`.
        :param triggered_at: Trigger timestamp (deadline anchor).

        :returns: The :class:`DispatchOutcome`.
        :raises: InfraDispatchUnavailableError,
                 InfraDispatchFailedError.
    """
    dispatcher = ACTIVE_JOB_DISPATCHER
    if dispatcher is None:
        _fail_infra_run(
            db_session=db_session,
            run_id=run_id,
            reason="job dispatcher not wired",
        )
        err_lines = ["Provision dispatch failed -- no JobDispatcher is wired."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append(
            "HINT: bootstrap_phase6_runtime publishes the dispatcher"
            " via set_active_job_dispatcher().")
        err_msg = os.linesep.join(err_lines)
        raise InfraDispatchUnavailableError(err_msg) from None

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

    provision_spec: Dict[str, Any] = provision_params_for(inputs=inputs, digest=digest)

    soft_deadline = triggered_at + timedelta(
        seconds=aspects.soft_deadline_seconds,
    )
    hard_deadline = triggered_at + timedelta(
        seconds=aspects.hard_deadline_seconds,
    )

    pipeline_ref: Optional[JobPipelineRef] = None

    dispatch_inputs = DispatchRequestInputs(
        run_id=run_id,
        project_id=project_id,
        job_id=run_id,
        job_name="provision:{}:{}".format(
            inputs.driver_name, inputs.action.value,
        ),
        job_type=job_type,
        job_kind=JOB_KIND_PROVISION,
        issuer=aspects.issuer or service_issuer(),
        refs=JobRefs(
            branch="main",
            build="",
            flavor="",
            release="",
            commit_sha="0" * 40,
        ),
        params=provision_spec,
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
        _fail_infra_run(
            db_session=db_session,
            run_id=run_id,
            reason="dispatch failed: {}".format(str(xcpt)),
        )
        err_lines = ["Provision dispatch failed."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_lines)
        raise InfraDispatchFailedError(err_msg) from xcpt

    return rtnval


def _fail_infra_run(
        *,
        db_session: DbSession,
        run_id: str,
        reason: str
    ) -> None:
    """
        Durably record a dispatch failure: drive the run-state
        machine to ``DISPATCH_FAILED`` and flip the InfraRun row to
        ``FAILED`` with ``final_state_reason``. Best-effort -- a
        secondary failure here is swallowed so the original dispatch
        error is what the caller sees.

        :param db_session: Active SQLAlchemy session.
        :param run_id: InfraRun UUID.
        :param reason: Human-readable failure reason.

        :returns: None.
    """
    try:
        transition_run_state(
            db_session=db_session,
            run_id=run_id,
            event=RunEvent.DISPATCH_ABORTED,
            actor="system:infra-orchestrator",
            reason=reason,
        )
    except Exception:
        _LOGGER.warning(
            "pychestrate.infra.runs.dispatch_fail.run_state_transition_skipped"
            " run_id=%s", run_id,
        )

    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is not None and row.state not in TERMINAL_RUN_STATES:
        row.state = InfraRunState.FAILED
        row.finished_at = utc_now()
        row.final_state_reason = reason
        db_session.flush()
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=InfraEventTopics.FAILED,
                payload={
                    "run_id": run_id,
                    "project_id": str(row.project_id),
                    "state": InfraRunState.FAILED.value,
                    "reason": reason,
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()
    return


def record_plan_summary(
        *,
        db_session: DbSession,
        run_id: str,
        summary: PlanSummary,
        plan_artifact_ref: Optional[str] = None,
        plan_diff_digest_sha256: str = ""
    ) -> InfraRunView:
    """
        Persist the plan summary + artifact ref + diff digest on
        a PLAN run. Stamps ``plan_issued_at = now()``. Emits
        :data:`InfraEventTopics.PLAN_RECORDED`. Idempotent on
        a run that already has a recorded summary — overwrites.

        :raises: InfraRunNotFoundError; InfraInputsInvalidError
                 when the run's action is not PLAN.
    """
    row = repository.find_run_by_id(
        db_session=db_session, run_id=run_id,
    )
    if row is None:
        _raise_not_found(run_id=run_id)
    if row.action != InfraAction.PLAN:
        err_lines = ["record_plan_summary requires a PLAN run."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("ACTION: {}".format(row.action.value))
        err_msg = os.linesep.join(err_lines)
        raise InfraInputsInvalidError(err_msg) from None

    now = utc_now()
    row.plan_summary = _summary_to_json(summary=summary)
    row.plan_artifact_ref = plan_artifact_ref
    row.plan_diff_digest_sha256 = plan_diff_digest_sha256
    row.plan_issued_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=InfraEventTopics.PLAN_RECORDED,
            payload={
                "run_id": str(row.run_id),
                "resources_to_add": summary.resources_to_add,
                "resources_to_change": summary.resources_to_change,
                "resources_to_destroy": summary.resources_to_destroy,
                "plan_diff_digest_sha256": plan_diff_digest_sha256,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_infra_run(db_session=db_session, run_id=run_id)
    return rtnval


def apply_run_terminal(
        *,
        db_session: DbSession,
        run_id: str,
        final_state: InfraRunState,
        layer5_run_id: Optional[str] = None,
        output_digest_sha256: str = "",
        failing_guard_rule_id: Optional[str] = None,
        reason: str = ""
    ) -> InfraRunView:
    """
        Mirror a Layer-5 outcome (or guard rejection) onto an
        infra run. Idempotent on already-terminal rows. Emits
        STATE_CHANGED + the kind-specific COMPLETED / FAILED /
        CANCELLED / REJECTED_BY_GUARD topic.

        :raises: InfraRunNotFoundError;
                 InfraInputsInvalidError when ``final_state`` is
                 not in the terminal set.
    """
    if final_state not in TERMINAL_RUN_STATES:
        err_lines = ["apply_run_terminal requires a terminal run state."]
        err_lines.append("RECEIVED: {}".format(final_state.value))
        err_msg = os.linesep.join(err_lines)
        raise InfraInputsInvalidError(err_msg) from None

    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is None:
        _raise_not_found(run_id=run_id)
    if row.state in TERMINAL_RUN_STATES:
        rtnval = get_infra_run(db_session=db_session, run_id=run_id)
        return rtnval

    now = utc_now()
    row.state = final_state
    if layer5_run_id is not None:
        row.layer5_run_id = layer5_run_id
    if len(output_digest_sha256) > 0:
        row.output_digest_sha256 = output_digest_sha256
    if failing_guard_rule_id is not None:
        row.failing_guard_rule_id = failing_guard_rule_id
    row.finished_at = now
    row.final_state_reason = reason
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=InfraEventTopics.STATE_CHANGED,
            payload={
                "run_id": str(row.run_id),
                "project_id": str(row.project_id),
                "environment_id": str(row.environment_id),
                "state": final_state.value,
            },
            source_event_id=new_uuid(),
        ),
    )

    final_topic = InfraEventTopics.COMPLETED
    if final_state == InfraRunState.FAILED:
        final_topic = InfraEventTopics.FAILED
    elif final_state == InfraRunState.CANCELLED:
        final_topic = InfraEventTopics.CANCELLED
    elif final_state == InfraRunState.REJECTED_BY_GUARD:
        final_topic = InfraEventTopics.REJECTED_BY_GUARD
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=final_topic,
            payload={
                "run_id": str(row.run_id),
                "state": final_state.value,
                "failing_guard_rule_id": failing_guard_rule_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = get_infra_run(db_session=db_session, run_id=run_id)
    return rtnval


def get_infra_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> InfraRunView:
    """
        Read by id.

        :raises: InfraRunNotFoundError on miss.
    """
    row = repository.find_run_by_id(db_session=db_session, run_id=run_id)
    if row is None:
        _raise_not_found(run_id=run_id)
    run_state = _resolve_run_state(db_session=db_session, run_id=run_id)
    rtnval = _to_view(row=row, run_state=run_state)
    return rtnval


def list_infra_runs_for_environment(
        *,
        db_session: DbSession,
        environment_id: str,
        limit: int = LIST_INFRA_RUNS_DEFAULT_LIMIT
    ) -> List[InfraRunView]:
    """
        Recent infra runs for an environment, newest-first.
    """
    rows = repository.list_runs_for_environment(
        db_session=db_session, environment_id=environment_id, limit=limit,
    )
    rtnval: List[InfraRunView] = []
    for r in rows:
        run_state = _resolve_run_state(
            db_session=db_session, run_id=str(r.run_id),
        )
        rtnval.append(_to_view(row=r, run_state=run_state))
    return rtnval


def list_infra_runs_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: Optional[str] = None,
        limit: int = LIST_INFRA_RUNS_DEFAULT_LIMIT
    ) -> List[InfraRunView]:
    """
        Recent infra runs for a project, newest-first. The
        optional ``environment_id`` narrows the listing to a
        single bound environment.
    """
    rows = repository.list_runs_for_project(
        db_session=db_session,
        project_id=project_id,
        environment_id=environment_id,
        limit=limit,
    )
    rtnval: List[InfraRunView] = []
    for r in rows:
        run_state = _resolve_run_state(
            db_session=db_session, run_id=str(r.run_id),
        )
        rtnval.append(_to_view(row=r, run_state=run_state))
    return rtnval


def _resolve_driver(*, driver_name: str) -> Type[InfraToolDriverProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=INFRA_TOOL_DRIVER_PROTOCOL,
    )
    for impl in candidates:
        if impl.driver_name() == driver_name:
            return impl
    err_lines = ["No registered infra_tool_driver for name."]
    err_lines.append("DRIVER_NAME: {}".format(driver_name))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.driver_name() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise InfraDriverUnknownError(err_msg) from None


def _resolve_run_state(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[str]:
    """
        Best-effort read of the run-state-machine state for an infra
        run. Returns ``None`` when no run-state row exists yet (the
        run was triggered before dispatch wiring landed).

        :param db_session: Active SQLAlchemy session.
        :param run_id: InfraRun UUID.

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


def _raise_not_found(*, run_id: str) -> None:
    err_lines = ["Infra run not found."]
    err_lines.append("RUN_ID: {}".format(run_id))
    err_msg = os.linesep.join(err_lines)
    raise InfraRunNotFoundError(err_msg) from None


def _summary_to_json(*, summary: PlanSummary) -> Dict[str, Any]:
    rtnval = {
        "resources_to_add": summary.resources_to_add,
        "resources_to_change": summary.resources_to_change,
        "resources_to_destroy": summary.resources_to_destroy,
        "resource_ops": [
            {
                "resource_address": op.resource_address,
                "op": op.op.value,
                "module_path": op.module_path,
            }
            for op in summary.resource_ops
        ],
    }
    return rtnval


def _summary_from_json(*, payload: Dict[str, Any]) -> PlanSummary:
    ops_raw = payload.get("resource_ops", []) or []
    ops_tuple = tuple(
        ResourceOp(
            resource_address=item.get("resource_address", ""),
            op=ResourceOpKind(item.get("op", ResourceOpKind.NO_OP.value)),
            module_path=item.get("module_path", ""),
        )
        for item in ops_raw
    )
    rtnval = PlanSummary(
        resources_to_add=payload.get("resources_to_add", 0),
        resources_to_change=payload.get("resources_to_change", 0),
        resources_to_destroy=payload.get("resources_to_destroy", 0),
        resource_ops=ops_tuple,
    )
    return rtnval


def _to_view(
        *,
        row: InfraRun,
        run_state: Optional[str] = None
    ) -> InfraRunView:
    plan_summary: Optional[PlanSummary] = None
    if row.plan_summary is not None:
        plan_summary = _summary_from_json(payload=dict(row.plan_summary))
    role_csv = row.actor_role_set_csv or ""
    role_set: Tuple[str, ...] = tuple()
    if len(role_csv) > 0:
        role_set = tuple(part for part in role_csv.split(",") if len(part) > 0)
    rtnval = InfraRunView(
        run_id=str(row.run_id),
        project_id=str(row.project_id),
        environment_id=str(row.environment_id),
        driver_name=row.driver_name,
        action=row.action,
        state=row.state,
        layer5_run_id=(
            str(row.layer5_run_id) if row.layer5_run_id is not None else None
        ),
        actor_id=str(row.actor_id) if row.actor_id is not None else None,
        actor_role_set=role_set,
        inputs=dict(row.inputs or {}),
        inputs_canonical_sha256=row.inputs_canonical_sha256,
        plan_summary=plan_summary,
        plan_artifact_ref=row.plan_artifact_ref,
        plan_diff_digest_sha256=row.plan_diff_digest_sha256,
        plan_issued_at=row.plan_issued_at,
        replay_of=str(row.replay_of) if row.replay_of is not None else None,
        output_digest_sha256=row.output_digest_sha256,
        failing_guard_rule_id=row.failing_guard_rule_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        final_state_reason=row.final_state_reason,
        run_state=run_state,
        dispatch_attempt_id=(
            str(row.layer5_run_id)
            if row.layer5_run_id is not None else None
        ),
    )
    return rtnval
