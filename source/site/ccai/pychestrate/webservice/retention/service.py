"""
.. module:: retention.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for 2-retention-policies (M1).

.. moduleauthor:: Code Craft AI LLC

M1 surface:

- ``create_policy`` — create a policy in ``DRAFT`` state.
- ``publish_policy`` — transition DRAFT/PAUSED → PUBLISHED and emit
  ``entity.retention.policy_published``.
- ``read_policy`` / ``list_policies`` — lookup helpers.

M2 adds the evaluator + dispatcher, selector compilers, additional
action impls, dry-run, legal hold, and failure / retry.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, List, Mapping, Optional, Sequence

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import list_factory_implementations
from ccai.pychestrate.webservice.hardening import metrics as hardening_metrics
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.retention import legal_hold as retention_legal_hold
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.retention.events import RetentionEventTopics
from ccai.pychestrate.webservice.retention.exceptions import (
    PolicyAlreadyExistsError,
    PolicyNotFoundError,
    PolicyStateTransitionError,
    UnsupportedRetentionActionError,
)
from ccai.pychestrate.webservice.retention.models import (
    ActionOutcome,
    ActionStep,
    PolicyScopeLevel,
    PolicyState,
    RetentionActionResult,
    RetentionPolicy,
    RetentionRunRecord,
    SelectorClause,
)
from ccai.pychestrate.webservice.retention import repository as retention_repository


def create_policy(
        *,
        db_session: DbSession,
        name: str,
        data_class: str,
        scope_level: PolicyScopeLevel,
        project_id: Optional[str],
        selector: SelectorClause,
        action_chain: Sequence[ActionStep],
        interval_minutes: int,
        batch_size: int,
        max_attempts: int,
        actor_user_id: Optional[str]
    ) -> RetentionPolicy:
    """
        Create a new policy in ``DRAFT`` state.

        :param db_session: Active SQLAlchemy session.
        :param name: Policy name (unique within scope).
        :param data_class: Declared data class.
        :param scope_level: SYSTEM or PROJECT.
        :param project_id: Project id when scope_level=PROJECT.
        :param selector: Selector clause.
        :param action_chain: Ordered sequence of :class:`ActionStep`.
        :param interval_minutes: Schedule interval.
        :param batch_size: Batch size per run.
        :param max_attempts: Retry ceiling per entity.
        :param actor_user_id: Acting principal.

        :returns: The persisted :class:`RetentionPolicy`.
        :raises: PolicyAlreadyExistsError, UnsupportedRetentionActionError,
                 SemanticError
    """
    if name is None or len(name.strip()) == 0:
        raise SemanticError("create_policy requires a non-empty name")

    if data_class is None or len(data_class.strip()) == 0:
        raise SemanticError("create_policy requires a non-empty data_class")

    if scope_level == PolicyScopeLevel.PROJECT:
        if project_id is None or len(str(project_id).strip()) == 0:
            raise SemanticError("PROJECT scope requires a non-empty project_id")

    if action_chain is None or len(list(action_chain)) == 0:
        raise SemanticError("create_policy requires at least one action step")

    for step in action_chain:
        _require_action_registered(action_name=step.action_name)

    existing = retention_repository.get_policy_by_name(
        db_session=db_session,
        scope_level=scope_level,
        project_id=project_id,
        name=name.strip(),
    )
    if existing is not None:
        err_msg_lines = ["Cannot create policy — name already exists in scope."]
        err_msg_lines.append("NAME: {}".format(name.strip()))
        err_msg_lines.append("SCOPE: {}/{}".format(scope_level.value, project_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise PolicyAlreadyExistsError(err_msg) from None

    now = utc_now()
    policy = RetentionPolicy(
        policy_id=new_uuid(),
        name=name.strip(),
        data_class=data_class.strip(),
        scope_level=scope_level,
        project_id=project_id,
        selector=_encode_selector(selector=selector),
        action_chain=_encode_action_chain(action_chain=action_chain),
        interval_minutes=int(interval_minutes),
        batch_size=int(batch_size),
        max_attempts=int(max_attempts),
        state=PolicyState.DRAFT,
        created_at=now,
        updated_at=now,
        published_at=None,
    )
    retention_repository.insert_policy(db_session=db_session, policy=policy)

    event_payload = {
        "policy_id": str(policy.policy_id),
        "name": policy.name,
        "data_class": policy.data_class,
        "scope_level": scope_level.value,
        "project_id": str(project_id) if project_id is not None else None,
        "actor_user_id": actor_user_id,
    }
    bus_event = EntityEvent(
        topic=RetentionEventTopics.RETENTION_POLICY_CREATED,
        payload=event_payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=bus_event)

    db_session.commit()

    rtnval = policy
    return rtnval


def publish_policy(
        *,
        db_session: DbSession,
        policy_id: str,
        actor_user_id: Optional[str]
    ) -> RetentionPolicy:
    """
        Transition a policy into ``PUBLISHED`` state.

        :param db_session: Active SQLAlchemy session.
        :param policy_id: Target id.
        :param actor_user_id: Acting principal.

        :returns: The updated :class:`RetentionPolicy`.
        :raises: PolicyNotFoundError, PolicyStateTransitionError
    """
    policy = read_policy(db_session=db_session, policy_id=policy_id)

    if policy.state == PolicyState.PUBLISHED:
        rtnval = policy
        return rtnval

    if policy.state not in (PolicyState.DRAFT, PolicyState.PAUSED):
        err_msg_lines = ["Cannot publish policy from current state."]
        err_msg_lines.append("POLICY_ID: {}".format(policy_id))
        err_msg_lines.append("CURRENT_STATE: {}".format(policy.state.value))
        err_msg = os.linesep.join(err_msg_lines)
        raise PolicyStateTransitionError(err_msg) from None

    policy.state = PolicyState.PUBLISHED
    policy.published_at = utc_now()
    policy.updated_at = utc_now()
    db_session.add(policy)
    db_session.flush()

    event_payload = {
        "policy_id": str(policy.policy_id),
        "name": policy.name,
        "actor_user_id": actor_user_id,
        "published_at": policy.published_at.isoformat(),
    }
    bus_event = EntityEvent(
        topic=RetentionEventTopics.RETENTION_POLICY_PUBLISHED,
        payload=event_payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=bus_event)

    db_session.commit()

    rtnval = policy
    return rtnval


def read_policy(*, db_session: DbSession, policy_id: str) -> RetentionPolicy:
    """
        Return a policy by id.

        :param db_session: Active SQLAlchemy session.
        :param policy_id: Target id.

        :returns: The :class:`RetentionPolicy`.
        :raises: PolicyNotFoundError
    """
    policy = retention_repository.get_policy_by_id(
        db_session=db_session, policy_id=policy_id,
    )
    if policy is None:
        err_msg_lines = ["Cannot read policy — no matching row."]
        err_msg_lines.append("POLICY_ID: {}".format(policy_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise PolicyNotFoundError(err_msg) from None

    rtnval = policy
    return rtnval


def list_policies(
        *,
        db_session: DbSession,
        scope_level: Optional[PolicyScopeLevel],
        project_id: Optional[str],
        state: Optional[PolicyState]
    ) -> List[RetentionPolicy]:
    """
        Return policies matching the supplied filters.
    """
    rtnval = retention_repository.list_policies(
        db_session=db_session,
        scope_level=scope_level,
        project_id=project_id,
        state=state,
    )
    return rtnval


def evaluate_policy(
        *,
        db_session: DbSession,
        policy_id: str,
        candidate_entity_ids: Sequence[str],
        dry_run: bool,
        actor_user_id: Optional[str]
    ) -> RetentionRunRecord:
    """
        Apply a published policy's action chain to ``candidate_entity_ids``.

        This evaluator is deliberately simple at M2: callers supply the
        candidate set (because a generic selector compiler requires data
        classes that land in Phase-10). Each candidate is sent through
        every :class:`ActionStep`, and the outcomes + counts are rolled
        into a :class:`RetentionRunRecord`. An ``entity.retention.applied``
        event summarizes the run at the end.

        :returns: The persisted :class:`RetentionRunRecord`.
    """
    policy = read_policy(db_session=db_session, policy_id=policy_id)

    if policy.state != PolicyState.PUBLISHED and dry_run is False:
        err_msg_lines = ["Policy must be PUBLISHED before real evaluation."]
        err_msg_lines.append("POLICY_ID: {}".format(policy_id))
        err_msg_lines.append("CURRENT_STATE: {}".format(policy.state.value))
        err_msg = os.linesep.join(err_msg_lines)
        raise PolicyStateTransitionError(err_msg) from None

    run = RetentionRunRecord(
        run_id=new_uuid(),
        policy_id=policy.policy_id,
        started_at=utc_now(),
        finished_at=None,
        matched_count=0,
        actioned_count=0,
        skipped_count=0,
        failed_count=0,
        error_summary=None,
    )
    db_session.add(run)
    db_session.flush()

    action_chain = policy.action_chain if policy.action_chain is not None else []
    action_impls = list_factory_implementations(factory_protocol_name="retention_action")
    action_by_name = {}
    for impl in action_impls:
        action_by_name[getattr(impl, "action_name", "")] = impl

    matched = 0
    actioned = 0
    skipped = 0
    failed = 0

    max_attempts = int(policy.max_attempts) if policy.max_attempts is not None else 3

    for entity_id in candidate_entity_ids:
        matched += 1

        if retention_legal_hold.is_held(
                db_session=db_session,
                entity_kind=policy.data_class,
                entity_id=entity_id,
            ) is True:
            skipped += 1
            _record_result(
                db_session=db_session,
                run_id=run.run_id,
                entity_id=entity_id,
                action_name="legal_hold_check",
                outcome=ActionOutcome.SKIPPED,
                reason="Entity is under legal hold",
                terminal=False,
            )
            hardening_metrics.increment_counter(
                name="retention.action.skipped_legal_hold", labels={},
            )
            continue

        for step in action_chain:
            action_name = step.get("action_name", "") if isinstance(step, dict) else step.action_name
            parameters = step.get("parameters", {}) if isinstance(step, dict) else (step.parameters or {})

            impl = action_by_name.get(action_name, None)
            if impl is None:
                skipped += 1
                _record_result(
                    db_session=db_session,
                    run_id=run.run_id,
                    entity_id=entity_id,
                    action_name=action_name,
                    outcome=ActionOutcome.SKIPPED,
                    reason="No registered action impl",
                    terminal=False,
                )
                continue

            application = None
            last_error = None
            for attempt_index in range(max_attempts):
                try:
                    application = impl.apply(
                        entity_kind=policy.data_class,
                        entity_id=entity_id,
                        parameters=parameters,
                        dry_run=dry_run,
                    )
                    break
                except Exception as xcpt:  # noqa: BLE001 — retried + tracked
                    last_error = xcpt
                    hardening_metrics.increment_counter(
                        name="retention.action.attempt_failed",
                        labels={"action_name": action_name},
                    )
                    continue

            if application is None:
                failed += 1
                _record_result(
                    db_session=db_session,
                    run_id=run.run_id,
                    entity_id=entity_id,
                    action_name=action_name,
                    outcome=ActionOutcome.FAILED,
                    reason=str(last_error) if last_error is not None else "Unknown failure",
                    terminal=False,
                )
                break

            if application.outcome == "applied":
                actioned += 1
                outcome_enum = ActionOutcome.APPLIED
            elif application.outcome == "skipped":
                skipped += 1
                outcome_enum = ActionOutcome.SKIPPED
            else:
                failed += 1
                outcome_enum = ActionOutcome.FAILED

            _record_result(
                db_session=db_session,
                run_id=run.run_id,
                entity_id=entity_id,
                action_name=action_name,
                outcome=outcome_enum,
                reason=application.reason,
                terminal=application.terminal,
            )

            if application.terminal is True:
                break

    run.finished_at = utc_now()
    run.matched_count = matched
    run.actioned_count = actioned
    run.skipped_count = skipped
    run.failed_count = failed
    db_session.add(run)
    db_session.flush()

    event_payload = {
        "policy_id": str(policy.policy_id),
        "run_id": str(run.run_id),
        "matched_count": matched,
        "actioned_count": actioned,
        "skipped_count": skipped,
        "failed_count": failed,
        "dry_run": bool(dry_run),
        "actor_user_id": actor_user_id,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RetentionEventTopics.RETENTION_APPLIED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    rtnval = run
    return rtnval


def _record_result(
        *,
        db_session: DbSession,
        run_id: str,
        entity_id: str,
        action_name: str,
        outcome: ActionOutcome,
        reason: str,
        terminal: bool
    ) -> None:
    """
        Persist a :class:`RetentionActionResult` row.
    """
    row = RetentionActionResult(
        result_id=new_uuid(),
        run_id=run_id,
        entity_id=entity_id,
        action_name=action_name,
        outcome=outcome,
        reason=reason,
        terminal="true" if terminal is True else "false",
        applied_at=utc_now(),
    )
    db_session.add(row)
    db_session.flush()
    return


def _encode_selector(*, selector: SelectorClause) -> Mapping[str, Any]:
    """
        Encode a :class:`SelectorClause` into a JSON-serializable mapping.
    """
    rtnval = {
        "tag_expression": selector.tag_expression,
        "age_days": int(selector.age_days),
        "size_bytes_over": int(selector.size_bytes_over),
        "project_ids": list(selector.project_ids),
    }
    return rtnval


def _encode_action_chain(*, action_chain: Sequence[ActionStep]) -> List[Mapping[str, Any]]:
    """
        Encode a sequence of :class:`ActionStep` into a list of dicts.
    """
    rtnval: List[Mapping[str, Any]] = []
    for step in action_chain:
        row = {
            "action_name": step.action_name,
            "parameters": dict(step.parameters) if step.parameters is not None else {},
            "wait_days_after_previous": int(step.wait_days_after_previous),
        }
        rtnval.append(row)

    return rtnval


def _require_action_registered(*, action_name: str) -> None:
    """
        Guard against referencing a retention action with no impl.
    """
    impls = list_factory_implementations(factory_protocol_name="retention_action")
    for impl in impls:
        declared = getattr(impl, "action_name", "")
        if declared == action_name:
            return

    err_msg_lines = ["No retention_action implementation matches this name."]
    err_msg_lines.append("ACTION_NAME: {}".format(action_name))
    err_msg = os.linesep.join(err_msg_lines)
    raise UnsupportedRetentionActionError(err_msg) from None
