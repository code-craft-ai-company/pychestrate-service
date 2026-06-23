"""
.. module:: metrics.alerts.service
    :synopsis: Alerts-budgets facade — create / disable / evaluate.

M1 ships:

* :func:`create_alert_rule` — name UNIQUE per project; rule
  config validated against the kind's ``validate_config``.
* :func:`get_alert_rule` / :func:`list_alert_rules_for_project`.
* :func:`disable_alert_rule` — idempotent + emits.
* :func:`evaluate_alert_rule` — invokes the kind's
  ``evaluate``, upserts :class:`AlertLiveState`, emits
  EVALUATED + STATE_CHANGED + FIRED / RESOLVED on transitions.
* :func:`get_live_state` / :func:`list_alert_kinds`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.metrics.alerts import repository
from ccai.pychestrate.webservice.metrics.alerts.errors import (
    AlertRuleConfigInvalidError,
    AlertRuleConflictError,
    AlertRuleKindUnknownError,
    AlertRuleNotFoundError,
)
from ccai.pychestrate.webservice.metrics.alerts.events import (
    AlertEventTopics,
)
from ccai.pychestrate.webservice.metrics.alerts.factories.rule_kind_protocol import (
    AlertRuleKindProtocol,
    AlertRuleKindRecord,
)
from ccai.pychestrate.webservice.metrics.alerts.models import (
    AlertLiveState,
    AlertRule,
    AlertSeverity,
    AlertState,
)


ALERT_RULE_KIND_PROTOCOL: str = "alert_rule_kind"


@dataclass(frozen=True)
class AlertRuleView:
    """
        Caller-facing rule read-model.
    """
    rule_id: str
    project_id: str
    name: str
    description: str
    kind: str
    config: Mapping[str, Any]
    severity: AlertSeverity
    enabled: bool
    notification_targets: Tuple[str, ...]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AlertLiveStateView:
    """
        Caller-facing live-state read-model.
    """
    rule_id: str
    state: AlertState
    last_value: Optional[Any]
    last_threshold: Optional[Any]
    last_reason: str
    last_evaluated_at: Optional[datetime]
    last_state_changed_at: Optional[datetime]
    fired_at: Optional[datetime]
    resolved_at: Optional[datetime]
    fire_count: int
    resolve_count: int


@dataclass(frozen=True)
class AlertEvaluationResult:
    """
        Caller-facing outcome surfaced by
        :func:`evaluate_alert_rule`.
    """
    rule_id: str
    state: AlertState
    state_changed: bool
    observed_value: Optional[float]
    threshold_value: Optional[float]
    reason: str


def create_alert_rule(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        kind: str,
        config: Mapping[str, Any],
        description: str = "",
        severity: AlertSeverity = AlertSeverity.WARNING,
        enabled: bool = True,
        notification_targets: Optional[List[str]] = None,
        actor_id: Optional[str] = None
    ) -> AlertRuleView:
    """
        Persist a new rule. Validates the config against the
        kind's ``validate_config``.

        :raises: AlertRuleConflictError on duplicate name;
                 AlertRuleKindUnknownError on unknown kind;
                 AlertRuleConfigInvalidError on bad config.
    """
    if name is None or len(name) == 0:
        err_lines = ["Alert rule name must be non-empty."]
        err_msg = os.linesep.join(err_lines)
        raise AlertRuleConfigInvalidError(err_msg) from None

    existing = repository.find_rule_by_name(
        db_session=db_session, project_id=project_id, name=name,
    )
    if existing is not None:
        err_lines = ["Alert rule name already exists in project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("NAME: {}".format(name))
        err_msg = os.linesep.join(err_lines)
        raise AlertRuleConflictError(err_msg) from None

    kind_cls = _resolve_kind(kind=kind)
    ok, issues = kind_cls.validate_config(config=config)
    if ok is False:
        err_lines = [
            "Alert rule config failed validation: {} issue(s).".format(
                len(issues),
            ),
        ]
        err_lines.append("KIND: {}".format(kind))
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise AlertRuleConfigInvalidError(err_msg) from None

    now = utc_now()
    row = repository.insert_rule(
        db_session=db_session,
        project_id=project_id,
        name=name,
        description=description,
        kind=kind,
        config=dict(config),
        severity=severity,
        enabled=enabled,
        notification_targets=list(notification_targets or []),
        created_by=actor_id,
        created_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AlertEventTopics.RULE_CREATED,
            payload={
                "rule_id": str(row.rule_id),
                "project_id": project_id,
                "name": name,
                "kind": kind,
                "severity": severity.value,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _rule_to_view(row=row)
    return rtnval


def get_alert_rule(
        *,
        db_session: DbSession,
        rule_id: str
    ) -> AlertRuleView:
    """
        Read by id.

        :raises: AlertRuleNotFoundError on miss.
    """
    row = _require_rule(db_session=db_session, rule_id=rule_id)
    rtnval = _rule_to_view(row=row)
    return rtnval


def list_alert_rules_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        enabled_only: bool = False
    ) -> List[AlertRuleView]:
    """
        Project-scoped list with optional enabled-only filter.
    """
    rows = repository.list_rules_for_project(
        db_session=db_session,
        project_id=project_id,
        enabled_only=enabled_only,
    )
    rtnval = [_rule_to_view(row=r) for r in rows]
    return rtnval


def disable_alert_rule(
        *,
        db_session: DbSession,
        rule_id: str,
        actor_id: Optional[str] = None
    ) -> AlertRuleView:
    """
        Flip ``enabled = False``. Idempotent.

        :raises: AlertRuleNotFoundError on miss.
    """
    row = _require_rule(db_session=db_session, rule_id=rule_id)
    if row.enabled is False:
        rtnval = _rule_to_view(row=row)
        return rtnval

    now = utc_now()
    row.enabled = False
    row.updated_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AlertEventTopics.RULE_DISABLED,
            payload={
                "rule_id": str(row.rule_id),
                "project_id": str(row.project_id),
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _rule_to_view(row=row)
    return rtnval


def evaluate_alert_rule(
        *,
        db_session: DbSession,
        rule_id: str
    ) -> AlertEvaluationResult:
    """
        Invoke the kind's ``evaluate``, upsert
        :class:`AlertLiveState`, emit EVALUATED on every call,
        STATE_CHANGED + FIRED / RESOLVED on transitions.

        :raises: AlertRuleNotFoundError on miss.
    """
    row = _require_rule(db_session=db_session, rule_id=rule_id)
    kind_cls = _resolve_kind(kind=row.kind)
    outcome = kind_cls.evaluate(
        db_session=db_session,
        project_id=str(row.project_id),
        config=dict(row.config or {}),
    )
    new_state = AlertState.FIRING if outcome.fires else AlertState.OK
    now = utc_now()
    live = repository.upsert_live_state(
        db_session=db_session,
        rule_id=str(row.rule_id),
        new_state=new_state,
        last_value=outcome.observed_value,
        last_threshold=outcome.threshold_value,
        last_reason=outcome.reason,
        evaluated_at=now,
    )
    state_changed = bool(getattr(live, "_state_changed_this_eval", False))

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AlertEventTopics.EVALUATED,
            payload={
                "rule_id": str(row.rule_id),
                "project_id": str(row.project_id),
                "state": new_state.value,
                "observed_value": outcome.observed_value,
                "threshold_value": outcome.threshold_value,
                "state_changed": state_changed,
                "reason": outcome.reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    if state_changed is True:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=AlertEventTopics.STATE_CHANGED,
                payload={
                    "rule_id": str(row.rule_id),
                    "project_id": str(row.project_id),
                    "from_state": (
                        AlertState.OK.value
                        if new_state == AlertState.FIRING
                        else AlertState.FIRING.value
                    ),
                    "to_state": new_state.value,
                },
                source_event_id=new_uuid(),
            ),
        )
        if new_state == AlertState.FIRING:
            enqueue_event(
                db_session=db_session,
                event=EntityEvent(
                    topic=AlertEventTopics.FIRED,
                    payload={
                        "rule_id": str(row.rule_id),
                        "project_id": str(row.project_id),
                        "severity": row.severity.value,
                        "reason": outcome.reason,
                    },
                    source_event_id=new_uuid(),
                ),
            )
        else:
            enqueue_event(
                db_session=db_session,
                event=EntityEvent(
                    topic=AlertEventTopics.RESOLVED,
                    payload={
                        "rule_id": str(row.rule_id),
                        "project_id": str(row.project_id),
                    },
                    source_event_id=new_uuid(),
                ),
            )
    db_session.commit()

    rtnval = AlertEvaluationResult(
        rule_id=str(row.rule_id),
        state=new_state,
        state_changed=state_changed,
        observed_value=outcome.observed_value,
        threshold_value=outcome.threshold_value,
        reason=outcome.reason,
    )
    return rtnval


def get_live_state(
        *,
        db_session: DbSession,
        rule_id: str
    ) -> AlertLiveStateView:
    """
        Read the live-state row.

        :raises: AlertRuleNotFoundError when neither the rule
                 nor a live-state row exists.
    """
    row = _require_rule(db_session=db_session, rule_id=rule_id)
    live = repository.find_live_state(
        db_session=db_session, rule_id=str(row.rule_id),
    )
    if live is None:
        rtnval = AlertLiveStateView(
            rule_id=str(row.rule_id),
            state=AlertState.UNKNOWN,
            last_value=None,
            last_threshold=None,
            last_reason="",
            last_evaluated_at=None,
            last_state_changed_at=None,
            fired_at=None,
            resolved_at=None,
            fire_count=0,
            resolve_count=0,
        )
        return rtnval
    rtnval = _live_state_to_view(row=live)
    return rtnval


def list_alert_kinds() -> Tuple[AlertRuleKindRecord, ...]:
    """
        Enumerate registered alert-rule-kind records in
        PRECEDENCE order.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=ALERT_RULE_KIND_PROTOCOL,
    )
    rtnval = tuple(impl.record() for impl in candidates)
    return rtnval


def _resolve_kind(*, kind: str) -> Type[AlertRuleKindProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=ALERT_RULE_KIND_PROTOCOL,
    )
    for impl in candidates:
        if impl.kind_name() == kind:
            return impl
    err_lines = ["No registered alert_rule_kind for name."]
    err_lines.append("KIND: {}".format(kind))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.kind_name() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise AlertRuleKindUnknownError(err_msg) from None


def _require_rule(
        *, db_session: DbSession, rule_id: str
    ) -> AlertRule:
    row = repository.find_rule_by_id(
        db_session=db_session, rule_id=rule_id,
    )
    if row is None:
        err_lines = ["Alert rule not found."]
        err_lines.append("RULE_ID: {}".format(rule_id))
        err_msg = os.linesep.join(err_lines)
        raise AlertRuleNotFoundError(err_msg) from None
    return row


def _rule_to_view(*, row: AlertRule) -> AlertRuleView:
    rtnval = AlertRuleView(
        rule_id=str(row.rule_id),
        project_id=str(row.project_id),
        name=row.name,
        description=row.description,
        kind=row.kind,
        config=dict(row.config or {}),
        severity=row.severity,
        enabled=row.enabled,
        notification_targets=tuple(row.notification_targets or []),
        created_by=str(row.created_by) if row.created_by is not None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval


def _live_state_to_view(*, row: AlertLiveState) -> AlertLiveStateView:
    rtnval = AlertLiveStateView(
        rule_id=str(row.rule_id),
        state=row.state,
        last_value=row.last_value,
        last_threshold=row.last_threshold,
        last_reason=row.last_reason,
        last_evaluated_at=row.last_evaluated_at,
        last_state_changed_at=row.last_state_changed_at,
        fired_at=row.fired_at,
        resolved_at=row.resolved_at,
        fire_count=row.fire_count,
        resolve_count=row.resolve_count,
    )
    return rtnval
