"""
.. module:: notifications.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for 2-notification-hub (M1).

.. moduleauthor:: Code Craft AI LLC

M1 surface:

- ``create_channel`` / ``read_channel`` / ``list_channels`` — channel CRUD.
- ``dispatch_envelope`` — helper that resolves a channel, renders a
  template, records an envelope + attempt, and publishes
  ``entity.notification.dispatched`` / ``entity.notification.failed``.

M2 adds routing rules, per-user preferences, Slack/Teams/PagerDuty/webhook
channels, and the dead-letter queue.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, List, Mapping, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import ConfigurationError, SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    list_resource_extensions,
)
from ccai.pychestrate.webservice.hardening.collisions import check_unique_identifiers
from ccai.pychestrate.webservice.hardening import metrics as hardening_metrics
from ccai.pychestrate.webservice.hardening.rate_limit import (
    RateLimitExceeded,
    acquire as rate_limit_acquire,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.notifications.events import NotificationEventTopics
from ccai.pychestrate.webservice.notifications.exceptions import (
    ChannelAlreadyExistsError,
    ChannelNotFoundError,
    NotificationDispatchError,
    TemplateNotFoundError,
    UnsupportedChannelKindError,
)
from ccai.pychestrate.webservice.notifications.extensions.template import (
    NotificationTemplateExtension,
)
from ccai.pychestrate.webservice.notifications.factories.channel import (
    ChannelDeliveryOutcome,
    NotificationChannelProtocol,
)
from ccai.pychestrate.webservice.notifications.models import (
    ChannelScopeLevel,
    DispatchOutcome,
    NotificationChannel,
    NotificationDeadLetter,
    NotificationDispatchAttempt,
    NotificationDispatchEnvelope,
    NotificationRoutingRule,
    UserNotificationPreferences,
)
from ccai.pychestrate.webservice.notifications import repository as notification_repository


def create_channel(
        *,
        db_session: DbSession,
        name: str,
        kind: str,
        scope_level: ChannelScopeLevel,
        project_id: Optional[str],
        config: Mapping[str, Any],
        actor_user_id: Optional[str]
    ) -> NotificationChannel:
    """
        Create a new delivery channel.

        :param db_session: Active SQLAlchemy session.
        :param name: Unique channel name within its scope.
        :param kind: Channel kind (``smtp_email`` at M1).
        :param scope_level: SYSTEM or PROJECT.
        :param project_id: Required when scope_level=PROJECT.
        :param config: Channel-specific configuration mapping.
        :param actor_user_id: Acting principal.

        :returns: The persisted :class:`NotificationChannel`.
        :raises: ChannelAlreadyExistsError, UnsupportedChannelKindError,
                 SemanticError
    """
    if name is None or len(name.strip()) == 0:
        raise SemanticError("create_channel requires a non-empty name")

    if scope_level == ChannelScopeLevel.PROJECT:
        if project_id is None or len(str(project_id).strip()) == 0:
            raise SemanticError("PROJECT scope requires a non-empty project_id")

    _require_channel_kind_registered(kind=kind)

    existing = notification_repository.get_channel_by_name(
        db_session=db_session,
        scope_level=scope_level,
        project_id=project_id,
        name=name.strip(),
    )
    if existing is not None:
        err_msg_lines = ["Cannot create channel — name already exists in scope."]
        err_msg_lines.append("NAME: {}".format(name.strip()))
        err_msg_lines.append("SCOPE: {}/{}".format(scope_level.value, project_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ChannelAlreadyExistsError(err_msg) from None

    now = utc_now()
    channel = NotificationChannel(
        channel_id=new_uuid(),
        name=name.strip(),
        kind=kind,
        scope_level=scope_level,
        project_id=project_id,
        config=dict(config) if config is not None else {},
        disabled=False,
        created_at=now,
        updated_at=now,
    )

    try:
        notification_repository.insert_channel(db_session=db_session, channel=channel)
    except IntegrityError:
        err_msg_lines = ["Cannot create channel — name already exists (integrity race)."]
        err_msg_lines.append("NAME: {}".format(name.strip()))
        err_msg = os.linesep.join(err_msg_lines)
        raise ChannelAlreadyExistsError(err_msg) from None

    db_session.commit()
    rtnval = channel
    return rtnval


def read_channel(*, db_session: DbSession, channel_id: str) -> NotificationChannel:
    """
        Return a channel by id.

        :param db_session: Active SQLAlchemy session.
        :param channel_id: Target id.

        :returns: The :class:`NotificationChannel`.
        :raises: ChannelNotFoundError
    """
    channel = notification_repository.get_channel_by_id(
        db_session=db_session, channel_id=channel_id
    )
    if channel is None:
        err_msg_lines = ["Cannot read channel — no matching row."]
        err_msg_lines.append("CHANNEL_ID: {}".format(channel_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ChannelNotFoundError(err_msg) from None

    rtnval = channel
    return rtnval


def list_channels(
        *,
        db_session: DbSession,
        scope_level: Optional[ChannelScopeLevel],
        project_id: Optional[str]
    ) -> List[NotificationChannel]:
    """
        Return channels matching the supplied filters.
    """
    rtnval = notification_repository.list_channels(
        db_session=db_session,
        scope_level=scope_level,
        project_id=project_id,
    )
    return rtnval


def dispatch_envelope(
        *,
        db_session: DbSession,
        channel_id: str,
        recipient: str,
        event_topic: str,
        template_name: str,
        payload: Mapping[str, Any]
    ) -> NotificationDispatchEnvelope:
    """
        Render a template and attempt delivery via the resolved channel.

        :param db_session: Active SQLAlchemy session.
        :param channel_id: Target channel id.
        :param recipient: Address (email, webhook URL, ...).
        :param event_topic: Originating bus topic recorded on the envelope.
        :param template_name: Registered template name.
        :param payload: Input mapping passed to the template's ``render``.

        :returns: The persisted :class:`NotificationDispatchEnvelope`.
        :raises: ChannelNotFoundError, TemplateNotFoundError,
                 UnsupportedChannelKindError, NotificationDispatchError
    """
    channel = read_channel(db_session=db_session, channel_id=channel_id)
    template_cls = _resolve_template(template_name=template_name)
    rendered = template_cls.render(payload=payload)

    envelope = NotificationDispatchEnvelope(
        envelope_id=new_uuid(),
        event_topic=event_topic,
        recipient=recipient,
        channel_id=channel.channel_id,
        template_name=template_name,
        severity=rendered.severity,
        rendered_subject=rendered.subject,
        rendered_body=rendered.body,
        created_at=utc_now(),
    )
    notification_repository.insert_envelope(db_session=db_session, envelope=envelope)

    channel_cls = _resolve_channel_protocol(kind=channel.kind)
    resolved_config = _resolve_config_secrets(
        config=channel.config if channel.config is not None else {},
    )
    outcome: ChannelDeliveryOutcome = channel_cls.send(
        channel_config=resolved_config,
        recipient=recipient,
        subject=rendered.subject,
        body=rendered.body,
    )
    hardening_metrics.record_latency(name="notification.dispatch.latency_ms", latency_ms=outcome.latency_ms)
    if outcome.delivered is True:
        hardening_metrics.increment_counter(name="notification.dispatch.ok", labels={"kind": channel.kind})
    else:
        hardening_metrics.increment_counter(name="notification.dispatch.failed", labels={"kind": channel.kind})

    if outcome.delivered is True:
        attempt_outcome = DispatchOutcome.DELIVERED
    else:
        attempt_outcome = DispatchOutcome.FAILED

    attempt = NotificationDispatchAttempt(
        attempt_id=new_uuid(),
        envelope_id=envelope.envelope_id,
        attempt_number=1,
        outcome=attempt_outcome,
        error_message=outcome.error_message,
        latency_ms=outcome.latency_ms,
        attempted_at=utc_now(),
    )
    notification_repository.insert_attempt(db_session=db_session, attempt=attempt)

    if outcome.delivered is True:
        topic = NotificationEventTopics.NOTIFICATION_DISPATCHED
    else:
        topic = NotificationEventTopics.NOTIFICATION_FAILED

    event_payload = {
        "envelope_id": str(envelope.envelope_id),
        "channel_id": str(channel.channel_id),
        "channel_kind": channel.kind,
        "event_topic": event_topic,
        "template_name": template_name,
        "recipient": recipient,
        "latency_ms": outcome.latency_ms,
        "error_message": outcome.error_message,
    }
    bus_event = EntityEvent(
        topic=topic,
        payload=event_payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=bus_event)

    db_session.commit()

    if outcome.delivered is False:
        dead_letter = NotificationDeadLetter(
            envelope_id=envelope.envelope_id,
            last_error=outcome.error_message or "",
            attempt_count=1,
            replayable=True,
            parked_at=utc_now(),
        )
        notification_repository.park_dead_letter(
            db_session=db_session, dead_letter=dead_letter,
        )
        db_session.commit()

        err_msg_lines = ["Notification dispatch failed."]
        err_msg_lines.append("CHANNEL: {}".format(channel.name))
        err_msg_lines.append("RECIPIENT: {}".format(recipient))
        err_msg_lines.append("ERROR: {}".format(outcome.error_message))
        err_msg = os.linesep.join(err_msg_lines)
        raise NotificationDispatchError(err_msg) from None

    rtnval = envelope
    return rtnval


def create_routing_rule(
        *,
        db_session: DbSession,
        project_id: Optional[str],
        event_pattern: str,
        template_name: str,
        channel_ids: List[str],
        recipients: List[str],
        filter_tag_expression: Optional[str],
        rate_limit_per_minute: Optional[int],
        actor_user_id: Optional[str]
    ) -> NotificationRoutingRule:
    """
        Create a routing rule binding an event pattern to channels.
    """
    if event_pattern is None or len(event_pattern.strip()) == 0:
        raise SemanticError("event_pattern is required")
    if template_name is None or len(template_name.strip()) == 0:
        raise SemanticError("template_name is required")

    now = utc_now()
    rule = NotificationRoutingRule(
        rule_id=new_uuid(),
        project_id=project_id,
        event_pattern=event_pattern.strip(),
        filter_tag_expression=filter_tag_expression,
        recipients=list(recipients or []),
        channel_ids=list(channel_ids or []),
        template_name=template_name.strip(),
        rate_limit_per_minute=rate_limit_per_minute,
        disabled=False,
        created_at=now,
        updated_at=now,
    )
    notification_repository.insert_routing_rule(db_session=db_session, rule=rule)
    db_session.commit()
    rtnval = rule
    return rtnval


def list_routing_rules(
        *,
        db_session: DbSession,
        project_id: Optional[str]
    ) -> List[NotificationRoutingRule]:
    """
        Return routing rules, optionally filtered by project id.
    """
    rtnval = notification_repository.list_routing_rules(
        db_session=db_session, project_id=project_id,
    )
    return rtnval


def delete_routing_rule(*, db_session: DbSession, rule_id: str) -> None:
    """
        Remove a routing rule by id.
    """
    rule = notification_repository.get_routing_rule(
        db_session=db_session, rule_id=rule_id,
    )
    if rule is None:
        err_msg_lines = ["Cannot delete routing rule — not found."]
        err_msg_lines.append("RULE_ID: {}".format(rule_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ChannelNotFoundError(err_msg) from None

    notification_repository.delete_routing_rule(db_session=db_session, rule=rule)
    db_session.commit()
    return


def set_user_preferences(
        *,
        db_session: DbSession,
        user_id: str,
        topics_enabled: Mapping[str, Any],
        quiet_hours: Mapping[str, Any]
    ) -> UserNotificationPreferences:
    """
        Upsert a :class:`UserNotificationPreferences` row.
    """
    if user_id is None or len(str(user_id).strip()) == 0:
        raise SemanticError("user_id is required")

    preferences = UserNotificationPreferences(
        user_id=user_id,
        topics_enabled=dict(topics_enabled) if topics_enabled is not None else {},
        quiet_hours=dict(quiet_hours) if quiet_hours is not None else {},
        updated_at=utc_now(),
    )
    persisted = notification_repository.upsert_user_preferences(
        db_session=db_session, preferences=preferences,
    )
    db_session.commit()
    rtnval = persisted
    return rtnval


def get_user_preferences(
        *,
        db_session: DbSession,
        user_id: str
    ) -> Optional[UserNotificationPreferences]:
    """
        Return a user's preferences row or None.
    """
    rtnval = notification_repository.get_user_preferences(
        db_session=db_session, user_id=user_id,
    )
    return rtnval


def list_dead_letters(
        *,
        db_session: DbSession,
        offset: int,
        limit: int
    ) -> List[NotificationDeadLetter]:
    """
        Paginate dead-letter rows.
    """
    rtnval = notification_repository.list_dead_letters(
        db_session=db_session, offset=offset, limit=limit,
    )
    return rtnval


def drop_dead_letter(*, db_session: DbSession, envelope_id: str) -> None:
    """
        Drop a dead-letter entry without replay.
    """
    dlq = notification_repository.get_dead_letter(
        db_session=db_session, envelope_id=envelope_id,
    )
    if dlq is None:
        err_msg_lines = ["Dead-letter entry not found."]
        err_msg_lines.append("ENVELOPE_ID: {}".format(envelope_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ChannelNotFoundError(err_msg) from None

    notification_repository.delete_dead_letter(db_session=db_session, dead_letter=dlq)
    db_session.commit()
    return


def replay_dead_letter(*, db_session: DbSession, envelope_id: str) -> NotificationDeadLetter:
    """
        Attempt to re-send a dead-lettered envelope. On success the DLQ
        row is removed; on failure the row's ``attempt_count`` increments.

        :raises: ChannelNotFoundError when the dead-letter row is missing.
    """
    dlq = notification_repository.get_dead_letter(
        db_session=db_session, envelope_id=envelope_id,
    )
    if dlq is None:
        err_msg_lines = ["Dead-letter entry not found."]
        err_msg_lines.append("ENVELOPE_ID: {}".format(envelope_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ChannelNotFoundError(err_msg) from None

    envelope = (
        db_session.query(NotificationDispatchEnvelope)
        .filter(NotificationDispatchEnvelope.envelope_id == envelope_id)
        .first()
    )
    if envelope is None:
        err_msg_lines = ["Envelope referenced by dead-letter is missing."]
        err_msg_lines.append("ENVELOPE_ID: {}".format(envelope_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ChannelNotFoundError(err_msg) from None

    channel = read_channel(
        db_session=db_session, channel_id=str(envelope.channel_id),
    )
    channel_cls = _resolve_channel_protocol(kind=channel.kind)
    outcome = channel_cls.send(
        channel_config=channel.config if channel.config is not None else {},
        recipient=envelope.recipient,
        subject=envelope.rendered_subject,
        body=envelope.rendered_body,
    )

    attempt = NotificationDispatchAttempt(
        attempt_id=new_uuid(),
        envelope_id=envelope.envelope_id,
        attempt_number=int(dlq.attempt_count or 0) + 1,
        outcome=DispatchOutcome.DELIVERED if outcome.delivered else DispatchOutcome.FAILED,
        error_message=outcome.error_message,
        latency_ms=outcome.latency_ms,
        attempted_at=utc_now(),
    )
    notification_repository.insert_attempt(db_session=db_session, attempt=attempt)

    if outcome.delivered is True:
        notification_repository.delete_dead_letter(db_session=db_session, dead_letter=dlq)
        db_session.commit()
        rtnval = dlq
        return rtnval

    dlq.attempt_count = int(dlq.attempt_count or 0) + 1
    dlq.last_error = outcome.error_message or dlq.last_error
    notification_repository.park_dead_letter(db_session=db_session, dead_letter=dlq)
    db_session.commit()

    rtnval = dlq
    return rtnval


def _resolve_template(*, template_name: str):
    """
        Return the registered :class:`NotificationTemplateExtension` for a
        given template name.

        :param template_name: Declared template_name.

        :returns: The subclass.
        :raises: TemplateNotFoundError, ConfigurationError on duplicates.
    """
    packs = list_resource_extensions(base_class=NotificationTemplateExtension)
    registry = check_unique_identifiers(
        packs=packs,
        identifier_attribute="template_name",
        category_label="NotificationTemplateExtension",
    )
    pack = registry.get(template_name, None)
    if pack is None:
        err_msg_lines = ["No notification template is registered with this name."]
        err_msg_lines.append("TEMPLATE: {}".format(template_name))
        err_msg = os.linesep.join(err_msg_lines)
        raise TemplateNotFoundError(err_msg) from None

    rtnval = pack
    return rtnval


def _resolve_config_secrets(*, config: Mapping[str, Any]) -> Mapping[str, Any]:
    """
        Replace ``secret://…`` string values in a channel config with the
        dereferenced payload returned by the registered
        ``secret_ref_dereferencer`` chain.

        :param config: Channel configuration mapping.

        :returns: A shallow-copied mapping with secret-refs resolved.
    """
    if config is None:
        rtnval = {}
        return rtnval

    impls = list_factory_implementations(factory_protocol_name="secret_ref_dereferencer")

    rtnval = {}
    for key, value in config.items():
        if isinstance(value, str) is True and value.startswith("secret://") is True:
            resolved = None
            for impl in impls:
                try:
                    resolved = impl.dereference(secret_ref=value)
                    break
                except NotImplementedError:
                    continue
            rtnval[key] = resolved if resolved is not None else value
        else:
            rtnval[key] = value

    return rtnval


def _resolve_channel_protocol(*, kind: str):
    """
        Return the highest-priority ``notification_channel`` implementation
        that matches ``channel_kind``.
    """
    impls = list_factory_implementations(factory_protocol_name="notification_channel")
    for impl in impls:
        declared = getattr(impl, "channel_kind", "")
        if declared == kind:
            rtnval = impl
            return rtnval

    err_msg_lines = ["No notification_channel implementation matches this kind."]
    err_msg_lines.append("KIND: {}".format(kind))
    err_msg = os.linesep.join(err_msg_lines)
    raise UnsupportedChannelKindError(err_msg) from None


def _require_channel_kind_registered(*, kind: str) -> None:
    """
        Guard against creating a channel whose kind has no protocol impl.
    """
    try:
        _resolve_channel_protocol(kind=kind)
    except UnsupportedChannelKindError:
        raise
    except ConfigurationError as xcpt:
        raise UnsupportedChannelKindError(str(xcpt)) from None

    return
