"""
.. module:: webhooks_out.repository
    :synopsis: CRUD helpers for outbound-webhook rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.webhooks_out.models import (
    DeliveryOutcome,
    SignatureScheme,
    WebhookDelivery,
    WebhookTarget,
)


def insert_target(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        description: str,
        url: str,
        secret_ref: str,
        signature_scheme: SignatureScheme,
        topic_filters: List[str],
        custom_headers: Dict[str, str],
        created_by: Optional[str],
        created_at: datetime
    ) -> WebhookTarget:
    row = WebhookTarget(
        target_id=new_uuid(),
        project_id=project_id,
        name=name,
        description=description,
        url=url,
        secret_ref=secret_ref,
        signature_scheme=signature_scheme,
        topic_filters=list(topic_filters),
        enabled=True,
        custom_headers=dict(custom_headers),
        created_by=created_by,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_target_by_id(
        *,
        db_session: DbSession,
        target_id: str
    ) -> Optional[WebhookTarget]:
    rtnval = (
        db_session.query(WebhookTarget)
        .filter(WebhookTarget.target_id == target_id)
        .first()
    )
    return rtnval


def find_target_by_name(
        *,
        db_session: DbSession,
        project_id: str,
        name: str
    ) -> Optional[WebhookTarget]:
    rtnval = (
        db_session.query(WebhookTarget)
        .filter(WebhookTarget.project_id == project_id)
        .filter(WebhookTarget.name == name)
        .first()
    )
    return rtnval


def list_targets_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        enabled_only: bool
    ) -> List[WebhookTarget]:
    query = (
        db_session.query(WebhookTarget)
        .filter(WebhookTarget.project_id == project_id)
    )
    if enabled_only is True:
        query = query.filter(WebhookTarget.enabled.is_(True))
    rows = query.order_by(WebhookTarget.name.asc()).all()
    rtnval = list(rows)
    return rtnval


def insert_delivery(
        *,
        db_session: DbSession,
        target_id: str,
        project_id: str,
        topic: str,
        payload_digest_sha256: str,
        signature: str,
        request_headers: Dict[str, str],
        outcome: DeliveryOutcome,
        response_status: Optional[int],
        response_excerpt: Optional[str],
        duration_ms: Optional[int],
        attempted_at: datetime
    ) -> WebhookDelivery:
    row = WebhookDelivery(
        delivery_id=new_uuid(),
        target_id=target_id,
        project_id=project_id,
        topic=topic,
        payload_digest_sha256=payload_digest_sha256,
        signature=signature,
        request_headers=dict(request_headers),
        outcome=outcome,
        response_status=response_status,
        response_excerpt=response_excerpt,
        duration_ms=duration_ms,
        attempted_at=attempted_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def list_recent_deliveries(
        *,
        db_session: DbSession,
        target_id: str,
        limit: int
    ) -> List[WebhookDelivery]:
    rows = (
        db_session.query(WebhookDelivery)
        .filter(WebhookDelivery.target_id == target_id)
        .order_by(WebhookDelivery.attempted_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval
