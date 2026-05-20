"""
.. module:: orchestration.infra.runs.service
    :synopsis: Infra-orchestration facade — trigger / plan / mirror / read.

M1 ships:

* :func:`trigger_run` — resolve env + driver, validate inputs
  + action support, persist a PENDING InfraRun, emit
  TRIGGERED. The actual Layer-5 dispatch handoff and the
  guard integration land in M2.
* :func:`record_plan_summary` — store the per-plan summary +
  artifact ref + diff digest on the run row, emit
  PLAN_RECORDED.
* :func:`apply_run_terminal` — mirror a Layer-5 outcome onto
  the InfraRun; emits STATE_CHANGED + the kind-specific
  COMPLETED / FAILED / CANCELLED / REJECTED_BY_GUARD topic.
* :func:`get_infra_run` /
  :func:`list_infra_runs_for_environment`.

The bound environment must be ACTIVE or FROZEN at trigger time;
DESTROY against a non-active env is allowed for cleanup, but
APPLY against a frozen env is rejected here without the M2
guard integration. ARCHIVED / DESTROYED envs reject every
trigger.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import hashlib
import json
import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.orchestration.infra.environment import (
    repository as env_repository,
)
from automojo.pychestrate.webservice.orchestration.infra.environment.models import (
    EnvironmentState,
)
from automojo.pychestrate.webservice.orchestration.infra.runs import repository
from automojo.pychestrate.webservice.orchestration.infra.runs.errors import (
    InfraDriverUnknownError,
    InfraEnvironmentStateError,
    InfraInputsInvalidError,
    InfraRunNotFoundError,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.events import (
    InfraEventTopics,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.factories.driver_protocol import (
    InfraToolDriverProtocol,
)
from automojo.pychestrate.webservice.orchestration.infra.runs.models import (
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


@dataclass(frozen=True)
class InfraTriggerAspects:
    """
        Caller-tunable knobs.
    """
    actor_id: Optional[str] = None
    actor_role_set: Tuple[str, ...] = ()
    replay_of: Optional[str] = None


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


def trigger_run(
        *,
        db_session: DbSession,
        project_id: str,
        inputs: InfraRunInputs,
        aspects: Optional[InfraTriggerAspects] = None
    ) -> InfraRunView:
    """
        Resolve env + driver, validate inputs, persist a
        PENDING InfraRun + emit TRIGGERED.

        :raises: InfraEnvironmentStateError when the bound
                 env is in a state that forbids the action.
        :raises: InfraDriverUnknownError when ``driver_name``
                 has no registered factory.
        :raises: InfraInputsInvalidError when the driver
                 rejects the inputs.
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
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=InfraEventTopics.TRIGGERED,
            payload={
                "run_id": str(row.run_id),
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
    rtnval = get_infra_run(
        db_session=db_session, run_id=str(row.run_id),
    )
    return rtnval


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
    rtnval = _to_view(row=row)
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
    rtnval = [_to_view(row=r) for r in rows]
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
    rtnval = [_to_view(row=r) for r in rows]
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


def _to_view(*, row: InfraRun) -> InfraRunView:
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
    )
    return rtnval
