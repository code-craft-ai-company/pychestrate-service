"""
.. module:: metrics.alerts.repository
    :synopsis: CRUD helpers for alert rule + live-state rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.metrics.alerts.models import (
    AlertLiveState,
    AlertRule,
    AlertSeverity,
    AlertState,
)


def insert_rule(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        description: str,
        kind: str,
        config: Dict[str, Any],
        severity: AlertSeverity,
        enabled: bool,
        notification_targets: List[str],
        created_by: Optional[str],
        created_at: datetime
    ) -> AlertRule:
    row = AlertRule(
        rule_id=new_uuid(),
        project_id=project_id,
        name=name,
        description=description,
        kind=kind,
        config=dict(config),
        severity=severity,
        enabled=enabled,
        notification_targets=list(notification_targets),
        created_by=created_by,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_rule_by_id(
        *,
        db_session: DbSession,
        rule_id: str
    ) -> Optional[AlertRule]:
    rtnval = (
        db_session.query(AlertRule)
        .filter(AlertRule.rule_id == rule_id)
        .first()
    )
    return rtnval


def find_rule_by_name(
        *,
        db_session: DbSession,
        project_id: str,
        name: str
    ) -> Optional[AlertRule]:
    rtnval = (
        db_session.query(AlertRule)
        .filter(AlertRule.project_id == project_id)
        .filter(AlertRule.name == name)
        .first()
    )
    return rtnval


def list_rules_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        enabled_only: bool
    ) -> List[AlertRule]:
    query = (
        db_session.query(AlertRule)
        .filter(AlertRule.project_id == project_id)
    )
    if enabled_only is True:
        query = query.filter(AlertRule.enabled.is_(True))
    rows = query.order_by(AlertRule.name.asc()).all()
    rtnval = list(rows)
    return rtnval


def upsert_live_state(
        *,
        db_session: DbSession,
        rule_id: str,
        new_state: AlertState,
        last_value: Optional[Any],
        last_threshold: Optional[Any],
        last_reason: str,
        evaluated_at: datetime
    ) -> AlertLiveState:
    row = (
        db_session.query(AlertLiveState)
        .filter(AlertLiveState.rule_id == rule_id)
        .first()
    )
    state_changed = False
    if row is None:
        # New row: the live-state lifecycle starts at UNKNOWN
        # implicitly. Only a brand-new FIRING result counts as
        # a state change that operators care about — an
        # initial OK is just baseline calibration and shouldn't
        # spawn a STATE_CHANGED + RESOLVED pair.
        is_initial_firing = (new_state == AlertState.FIRING)
        row = AlertLiveState(
            rule_id=rule_id,
            state=new_state,
            last_value=last_value,
            last_threshold=last_threshold,
            last_reason=last_reason,
            last_evaluated_at=evaluated_at,
            last_state_changed_at=(
                evaluated_at if is_initial_firing is True else None
            ),
            fired_at=evaluated_at if is_initial_firing is True else None,
            resolved_at=None,
            fire_count=1 if is_initial_firing is True else 0,
            resolve_count=0,
        )
        db_session.add(row)
        state_changed = is_initial_firing
    else:
        if row.state != new_state:
            state_changed = True
            row.last_state_changed_at = evaluated_at
            if new_state == AlertState.FIRING:
                row.fired_at = evaluated_at
                row.fire_count = row.fire_count + 1
            elif new_state == AlertState.OK and row.state == AlertState.FIRING:
                row.resolved_at = evaluated_at
                row.resolve_count = row.resolve_count + 1
        row.state = new_state
        row.last_value = last_value
        row.last_threshold = last_threshold
        row.last_reason = last_reason
        row.last_evaluated_at = evaluated_at
    db_session.flush()
    setattr(row, "_state_changed_this_eval", state_changed)
    return row


def find_live_state(
        *,
        db_session: DbSession,
        rule_id: str
    ) -> Optional[AlertLiveState]:
    rtnval = (
        db_session.query(AlertLiveState)
        .filter(AlertLiveState.rule_id == rule_id)
        .first()
    )
    return rtnval
