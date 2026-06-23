"""
.. module:: maintenance.repository
    :synopsis: CRUD helpers for maintenance-mode rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.maintenance.models import (
    MaintenanceModeAudit,
    MaintenanceModeRow,
)


def upsert_mode_row(
        *,
        db_session: DbSession,
        scope: str,
        mode: str,
        reason: str,
        ends_at: Optional[datetime],
        actor_id: Optional[str],
        now: datetime
    ) -> MaintenanceModeRow:
    row = (
        db_session.query(MaintenanceModeRow)
        .filter(MaintenanceModeRow.scope == scope)
        .first()
    )
    if row is None:
        row = MaintenanceModeRow(
            scope=scope,
            mode=mode,
            reason=reason,
            ends_at=ends_at,
            changed_at=now,
            changed_by=actor_id,
            version=1,
        )
        db_session.add(row)
    else:
        row.mode = mode
        row.reason = reason
        row.ends_at = ends_at
        row.changed_at = now
        row.changed_by = actor_id
        row.version = row.version + 1
    db_session.flush()
    return row


def find_mode_row(
        *,
        db_session: DbSession,
        scope: str
    ) -> Optional[MaintenanceModeRow]:
    rtnval = (
        db_session.query(MaintenanceModeRow)
        .filter(MaintenanceModeRow.scope == scope)
        .first()
    )
    return rtnval


def list_active_rows(
        *,
        db_session: DbSession
    ) -> List[MaintenanceModeRow]:
    """
        Return every scope row whose mode is not ``"active"``.
        The ``"active"`` row is the default, so listings only
        ever surface non-default scopes.
    """
    rows = (
        db_session.query(MaintenanceModeRow)
        .filter(MaintenanceModeRow.mode != "active")
        .order_by(MaintenanceModeRow.scope.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def insert_audit_row(
        *,
        db_session: DbSession,
        scope: str,
        from_mode: str,
        to_mode: str,
        reason: str,
        ends_at: Optional[datetime],
        actor_id: Optional[str],
        changed_at: datetime
    ) -> MaintenanceModeAudit:
    row = MaintenanceModeAudit(
        audit_id=new_uuid(),
        scope=scope,
        from_mode=from_mode,
        to_mode=to_mode,
        reason=reason,
        ends_at=ends_at,
        actor_user_id=actor_id,
        changed_at=changed_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_audit_for_scope(
        *,
        db_session: DbSession,
        scope: str,
        limit: int
    ) -> List[MaintenanceModeAudit]:
    rows = (
        db_session.query(MaintenanceModeAudit)
        .filter(MaintenanceModeAudit.scope == scope)
        .order_by(MaintenanceModeAudit.changed_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval
