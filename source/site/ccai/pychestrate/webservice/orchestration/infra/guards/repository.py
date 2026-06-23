"""
.. module:: orchestration.infra.guards.repository
    :synopsis: CRUD helpers for guard attachments.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.orchestration.infra.guards.models import (
    GuardAttachment,
)


def upsert_attachment(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        rule_id: str,
        enabled: bool,
        actor_id: Optional[str],
        now: datetime
    ) -> GuardAttachment:
    row = (
        db_session.query(GuardAttachment)
        .filter(GuardAttachment.project_id == project_id)
        .filter(GuardAttachment.environment_id == environment_id)
        .filter(GuardAttachment.rule_id == rule_id)
        .first()
    )
    if row is None:
        row = GuardAttachment(
            project_id=project_id,
            environment_id=environment_id,
            rule_id=rule_id,
            enabled=enabled,
            added_by=actor_id,
            added_at=now,
            updated_at=now,
        )
        db_session.add(row)
    else:
        row.enabled = enabled
        row.updated_at = now
    db_session.flush()
    return row


def find_attachment(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        rule_id: str
    ) -> Optional[GuardAttachment]:
    rtnval = (
        db_session.query(GuardAttachment)
        .filter(GuardAttachment.project_id == project_id)
        .filter(GuardAttachment.environment_id == environment_id)
        .filter(GuardAttachment.rule_id == rule_id)
        .first()
    )
    return rtnval


def list_attachments_for_environment(
        *,
        db_session: DbSession,
        project_id: str,
        environment_id: str,
        enabled_only: bool
    ) -> List[GuardAttachment]:
    query = (
        db_session.query(GuardAttachment)
        .filter(GuardAttachment.project_id == project_id)
        .filter(GuardAttachment.environment_id == environment_id)
    )
    if enabled_only is True:
        query = query.filter(GuardAttachment.enabled.is_(True))
    rows = query.order_by(GuardAttachment.rule_id.asc()).all()
    rtnval = list(rows)
    return rtnval
