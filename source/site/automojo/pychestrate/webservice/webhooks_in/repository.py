"""
.. module:: webhooks_in.repository
    :synopsis: CRUD helpers for inbound-webhook rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.webhooks_in.models import (
    WebhookConfiguration,
    WebhookSeenDelivery,
)


def insert_configuration(
        *,
        db_session: DbSession,
        project_id: str,
        provider: str,
        hook_name: str,
        secret_ref: str,
        mtls_required: bool,
        description: str,
        created_by: Optional[str],
        created_at: datetime
    ) -> WebhookConfiguration:
    """
        Insert a new ``webhooks_in_configurations`` row and
        flush so the dispatcher pipeline can read its
        ``webhook_id``.
    """
    row = WebhookConfiguration(
        webhook_id=new_uuid(),
        project_id=project_id,
        provider=provider,
        hook_name=hook_name,
        secret_ref=secret_ref,
        mtls_required=mtls_required,
        description=description,
        enabled=True,
        created_by=created_by,
        created_at=created_at,
        disabled_at=None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_configuration_by_id(
        *,
        db_session: DbSession,
        webhook_id: str
    ) -> Optional[WebhookConfiguration]:
    rtnval = (
        db_session.query(WebhookConfiguration)
        .filter(WebhookConfiguration.webhook_id == webhook_id)
        .first()
    )
    return rtnval


def find_configuration_by_provider_and_name(
        *,
        db_session: DbSession,
        project_id: str,
        provider: str,
        hook_name: str
    ) -> Optional[WebhookConfiguration]:
    rtnval = (
        db_session.query(WebhookConfiguration)
        .filter(WebhookConfiguration.project_id == project_id)
        .filter(WebhookConfiguration.provider == provider)
        .filter(WebhookConfiguration.hook_name == hook_name)
        .first()
    )
    return rtnval


def list_configurations_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        enabled_only: bool
    ) -> List[WebhookConfiguration]:
    query = (
        db_session.query(WebhookConfiguration)
        .filter(WebhookConfiguration.project_id == project_id)
    )
    if enabled_only is True:
        query = query.filter(WebhookConfiguration.enabled.is_(True))
    rows = query.order_by(
        WebhookConfiguration.provider.asc(),
        WebhookConfiguration.hook_name.asc(),
    ).all()
    rtnval = list(rows)
    return rtnval


def list_active_configurations_for_provider(
        *,
        db_session: DbSession,
        provider: str,
        hook_name: str
    ) -> List[WebhookConfiguration]:
    """
        Lookup helper for the inbound dispatcher path which
        only knows the URL segments (``provider`` and
        ``hook_name``) — not the project. M1 returns every
        enabled row; the dispatcher disambiguates via the
        signature compare.
    """
    rows = (
        db_session.query(WebhookConfiguration)
        .filter(WebhookConfiguration.provider == provider)
        .filter(WebhookConfiguration.hook_name == hook_name)
        .filter(WebhookConfiguration.enabled.is_(True))
        .all()
    )
    rtnval = list(rows)
    return rtnval


def insert_seen_delivery(
        *,
        db_session: DbSession,
        provider: str,
        hook_name: str,
        delivery_id: str,
        first_seen_at: datetime,
        expires_at: datetime
    ) -> WebhookSeenDelivery:
    row = WebhookSeenDelivery(
        provider=provider,
        hook_name=hook_name,
        delivery_id=delivery_id,
        first_seen_at=first_seen_at,
        expires_at=expires_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_seen_delivery(
        *,
        db_session: DbSession,
        provider: str,
        hook_name: str,
        delivery_id: str
    ) -> Optional[WebhookSeenDelivery]:
    rtnval = (
        db_session.query(WebhookSeenDelivery)
        .filter(WebhookSeenDelivery.provider == provider)
        .filter(WebhookSeenDelivery.hook_name == hook_name)
        .filter(WebhookSeenDelivery.delivery_id == delivery_id)
        .first()
    )
    return rtnval
