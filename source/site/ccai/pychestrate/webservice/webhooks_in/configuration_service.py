"""
.. module:: webhooks_in.configuration_service
    :synopsis: CRUD facade for ``webhooks_in_configurations``.

M1 ships:

* :func:`create_webhook` — UNIQUE on
  ``(project, provider, hook_name)``; validates that
  ``provider`` has a registered parser.
* :func:`get_webhook` / :func:`list_webhooks` — read helpers.
* :func:`disable_webhook` — flips ``enabled = False``,
  stamps ``disabled_at``, idempotent + emits
  CONFIGURATION_DISABLED.

The replay endpoint and the rotate-secret PATCH path land in
M2.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.webhooks_in import repository
from ccai.pychestrate.webservice.webhooks_in.errors import (
    WebhookConfigurationConflictError,
    WebhookConfigurationInvalidError,
    WebhookConfigurationNotFoundError,
    WebhookProviderUnknownError,
)
from ccai.pychestrate.webservice.webhooks_in.events import (
    WebhookInEventTopics,
)
from ccai.pychestrate.webservice.webhooks_in.factories.inbound_webhook_parser import (
    InboundWebhookParserProtocol,
)
from ccai.pychestrate.webservice.webhooks_in.models import (
    WebhookConfiguration,
)


@dataclass(frozen=True)
class WebhookConfigurationView:
    """
        Caller-facing inbound webhook read-model.
    """
    webhook_id: str
    project_id: str
    provider: str
    hook_name: str
    secret_ref: str
    mtls_required: bool
    description: str
    enabled: bool
    created_by: Optional[str]
    created_at: datetime
    disabled_at: Optional[datetime]


def create_webhook(
        *,
        db_session: DbSession,
        project_id: str,
        provider: str,
        hook_name: str,
        secret_ref: str,
        mtls_required: bool = False,
        description: str = "",
        actor_id: Optional[str] = None
    ) -> WebhookConfigurationView:
    """
        Persist a new webhook configuration. UNIQUE on
        ``(project_id, provider, hook_name)``.

        :raises: WebhookConfigurationInvalidError on empty
                 fields; WebhookProviderUnknownError when no
                 parser is registered for ``provider``;
                 WebhookConfigurationConflictError on duplicate.
    """
    if hook_name is None or len(hook_name) == 0:
        err_lines = ["Webhook hook_name must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise WebhookConfigurationInvalidError(err_msg) from None
    if provider is None or len(provider) == 0:
        err_lines = ["Webhook provider must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise WebhookConfigurationInvalidError(err_msg) from None
    if secret_ref is None or len(secret_ref) == 0:
        err_lines = ["Webhook secret_ref must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise WebhookConfigurationInvalidError(err_msg) from None

    parser_cls = _resolve_parser(provider=provider)
    if parser_cls is None:
        err_lines = ["No registered parser for provider."]
        err_lines.append("PROVIDER: {!r}".format(provider))
        err_msg = os.linesep.join(err_lines)
        raise WebhookProviderUnknownError(err_msg) from None

    existing = repository.find_configuration_by_provider_and_name(
        db_session=db_session,
        project_id=project_id,
        provider=provider,
        hook_name=hook_name,
    )
    if existing is not None:
        err_lines = [
            "Webhook configuration already exists in project.",
        ]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("PROVIDER: {}".format(provider))
        err_lines.append("HOOK_NAME: {}".format(hook_name))
        err_msg = os.linesep.join(err_lines)
        raise WebhookConfigurationConflictError(err_msg) from None

    now = utc_now()
    row = repository.insert_configuration(
        db_session=db_session,
        project_id=project_id,
        provider=provider,
        hook_name=hook_name,
        secret_ref=secret_ref,
        mtls_required=mtls_required,
        description=description,
        created_by=actor_id,
        created_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookInEventTopics.CONFIGURED,
            payload={
                "webhook_id": str(row.webhook_id),
                "project_id": project_id,
                "provider": provider,
                "hook_name": hook_name,
                "created_by": actor_id,
                "created_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _row_to_view(row=row)
    return rtnval


def get_webhook(
        *,
        db_session: DbSession,
        webhook_id: str
    ) -> WebhookConfigurationView:
    """
        Read by id.

        :raises: WebhookConfigurationNotFoundError on miss.
    """
    row = _require_configuration(
        db_session=db_session, webhook_id=webhook_id,
    )
    rtnval = _row_to_view(row=row)
    return rtnval


def list_webhooks(
        *,
        db_session: DbSession,
        project_id: str,
        enabled_only: bool = False
    ) -> List[WebhookConfigurationView]:
    """
        Project-scoped list with enabled-only filter.
    """
    rows = repository.list_configurations_for_project(
        db_session=db_session,
        project_id=project_id,
        enabled_only=enabled_only,
    )
    rtnval = [_row_to_view(row=r) for r in rows]
    return rtnval


def disable_webhook(
        *,
        db_session: DbSession,
        webhook_id: str,
        actor_id: Optional[str] = None
    ) -> WebhookConfigurationView:
    """
        Flip ``enabled = False`` and stamp ``disabled_at``.
        Idempotent + emits
        :data:`WebhookInEventTopics.CONFIGURATION_DISABLED`
        on the first transition.
    """
    row = _require_configuration(
        db_session=db_session, webhook_id=webhook_id,
    )
    if row.enabled is False:
        rtnval = _row_to_view(row=row)
        return rtnval
    now = utc_now()
    row.enabled = False
    row.disabled_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookInEventTopics.CONFIGURATION_DISABLED,
            payload={
                "webhook_id": str(row.webhook_id),
                "project_id": str(row.project_id),
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _row_to_view(row=row)
    return rtnval


def _require_configuration(
        *, db_session: DbSession, webhook_id: str
    ) -> WebhookConfiguration:
    row = repository.find_configuration_by_id(
        db_session=db_session, webhook_id=webhook_id,
    )
    if row is None:
        err_lines = ["Webhook configuration not found."]
        err_lines.append("WEBHOOK_ID: {}".format(webhook_id))
        err_msg = os.linesep.join(err_lines)
        raise WebhookConfigurationNotFoundError(err_msg) from None
    return row


def _resolve_parser(*, provider: str):
    candidates = list_factory_implementations(
        factory_protocol_name=InboundWebhookParserProtocol.factory_protocol_name,
    )
    for impl in candidates:
        try:
            name = impl.provider_name()
        except NotImplementedError:
            continue
        if name == provider:
            return impl
    return None


def _row_to_view(*, row: WebhookConfiguration) -> WebhookConfigurationView:
    rtnval = WebhookConfigurationView(
        webhook_id=str(row.webhook_id),
        project_id=str(row.project_id),
        provider=row.provider,
        hook_name=row.hook_name,
        secret_ref=row.secret_ref,
        mtls_required=row.mtls_required,
        description=row.description,
        enabled=row.enabled,
        created_by=(
            str(row.created_by) if row.created_by is not None else None
        ),
        created_at=row.created_at,
        disabled_at=row.disabled_at,
    )
    return rtnval
