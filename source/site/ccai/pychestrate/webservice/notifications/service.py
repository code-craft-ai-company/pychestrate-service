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

import logging

from typing import Any, Dict, List, Mapping, Optional, Tuple

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
from ccai.pychestrate.webservice.notifications.channel_config import (
    PreparedChannelConfig,
    channel_secret_name,
    is_http_url,
    is_secret_ref,
    prepare_channel_config,
    public_config,
    secret_name_from_ref,
    secret_ref_for,
)
from ccai.pychestrate.webservice.notifications.exceptions import (
    ChannelAlreadyExistsError,
    ChannelConfigInvalidError,
    ChannelInUseError,
    ChannelNotFoundError,
    ChannelSecretAccessDeniedError,
    ChannelSecretUnavailableError,
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
from ccai.pychestrate.webservice.secrets import secrets_service
from ccai.pychestrate.webservice.secrets.exceptions import (
    SecretAccessDeniedError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretVersionExpiredError,
)
from ccai.pychestrate.webservice.secrets.models import SecretScopeKind
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.secrets.secrets_aspects import (
    build_default_aspects as build_default_secrets_aspects,
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


_LOGGER = logging.getLogger(__name__)

#: The name the vault records for reads the dispatcher makes when it sends.
NOTIFICATIONS_SERVICE_IDENTITY: str = "notifications"


def create_channel(
        *,
        db_session: DbSession,
        name: str,
        kind: str,
        scope_level: ChannelScopeLevel,
        project_id: Optional[str],
        config: Mapping[str, Any],
        actor_user_id: Optional[str],
        secrets: Optional[Mapping[str, str]] = None,
        principal: Any = None
    ) -> NotificationChannel:
    """
        Create a new delivery channel.

        A secret setting of the kind (an SMTP password, a webhook address that works like a password) is never stored in the channel. It
        arrives in ``secrets`` and is written to the secrets vault on behalf of ``principal`` (so the vault's own access rules and audit
        apply), or ``config`` points it at an existing vault secret the principal may read. The channel keeps only a ``secret://`` reference.

        :param db_session: Active SQLAlchemy session.
        :param name: Unique channel name within its scope.
        :param kind: Channel kind (``smtp_email``, ``slack_webhook`` ...).
        :param scope_level: SYSTEM or PROJECT.
        :param project_id: Required when scope_level=PROJECT.
        :param config: Channel-specific settings, and ``secret://`` references.
        :param actor_user_id: Acting principal's user id.
        :param secrets: Secret setting name to the new plain value to store in the vault.
        :param principal: The authenticated caller, needed whenever a secret is stored or bound.

        :returns: The persisted :class:`NotificationChannel`.
        :raises: ChannelAlreadyExistsError, UnsupportedChannelKindError, ChannelConfigInvalidError,
                 ChannelSecretAccessDeniedError, SemanticError
    """
    if name is None or len(name.strip()) == 0:
        raise SemanticError("create_channel requires a non-empty name")

    if scope_level == ChannelScopeLevel.PROJECT:
        if project_id is None or len(str(project_id).strip()) == 0:
            raise SemanticError("PROJECT scope requires a non-empty project_id")

    _require_channel_kind_registered(kind=kind)
    protocol = _resolve_channel_protocol(kind=kind)

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

    prepared = prepare_channel_config(
        fields=protocol.config_fields, kind=kind, config=config, secrets=secrets,
    )

    channel_id = new_uuid()
    stored_config = dict(prepared.config)
    stored_names: List[str] = []
    try:
        _check_bound_secrets(db_session=db_session, principal=principal, prepared=prepared, fields=protocol.config_fields)
        for setting, value in prepared.new_secrets.items():
            vault_name = channel_secret_name(channel_id=channel_id, setting=setting)
            _store_channel_secret(
                db_session=db_session, principal=principal, vault_name=vault_name, value=value,
                scope_level=scope_level, project_id=project_id,
            )
            stored_names.append(vault_name)
            stored_config[setting] = secret_ref_for(name=vault_name)

        now = utc_now()
        channel = NotificationChannel(
            channel_id=channel_id,
            name=name.strip(),
            kind=kind,
            scope_level=scope_level,
            project_id=project_id,
            config=stored_config,
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
        _stage_admin_event(
            db_session=db_session, topic=NotificationEventTopics.CHANNEL_CREATED, actor_user_id=actor_user_id,
            payload={
                "channel_id": str(channel_id), "name": channel.name, "kind": kind,
                "secret_settings": sorted(setting for setting, value in stored_config.items() if is_secret_ref(value=value)),
            },
        )
        db_session.commit()
    except BaseException:
        db_session.rollback()
        _discard_channel_secrets(db_session=db_session, principal=principal, vault_names=stored_names)
        raise

    rtnval = channel
    return rtnval


def describe_channel(*, channel: NotificationChannel) -> Dict[str, Any]:
    """
        A channel's settings as they may be shown: secrets as ``secret://`` references (or masked, when still held as plain text).

        :param channel: The channel.

        :returns: ``{"config": {...}, "unprotected_secret_fields": [...]}``.
    """
    try:
        protocol = _resolve_channel_protocol(kind=channel.kind)
        fields = protocol.config_fields
    except UnsupportedChannelKindError:
        fields = ()
    shown, unprotected = public_config(fields=fields, config=channel.config)
    rtnval = {"config": shown, "unprotected_secret_fields": unprotected}
    return rtnval


def update_channel(
        *,
        db_session: DbSession,
        channel_id: str,
        disabled: Optional[bool] = None,
        config: Optional[Mapping[str, Any]] = None,
        secrets: Optional[Mapping[str, str]] = None,
        principal: Any = None
    ) -> NotificationChannel:
    """
        Change a channel: switch it on or off, change plain settings, and replace or rotate secrets.

        A new value in ``secrets`` for a setting the channel already keeps in the vault under its own name becomes a new version of that
        vault secret (so the channel follows). For a setting that is unset, points at someone else's vault secret, or is still held as plain
        text, the value is stored under the channel's own name and the setting now points at it.

        :param db_session: Active SQLAlchemy session.
        :param channel_id: The channel.
        :param disabled: True to stop sending through it, False to resume; None leaves it.
        :param config: Settings to change (only the ones given are replaced).
        :param secrets: Secret setting name to its new plain value.
        :param principal: The authenticated caller, needed when a secret is stored.

        :returns: The updated channel.
        :raises: ChannelNotFoundError, ChannelConfigInvalidError, ChannelSecretAccessDeniedError
    """
    channel = read_channel(db_session=db_session, channel_id=channel_id)
    protocol = _resolve_channel_protocol(kind=channel.kind)
    stored_names: List[str] = []
    changed: List[str] = []
    try:
        if config is not None or secrets is not None:
            current = dict(channel.config) if channel.config is not None else {}
            merged = {key: value for key, value in current.items() if key not in (secrets or {})}
            for key, value in (config or {}).items():
                merged[key] = value
            prepared = prepare_channel_config(
                fields=protocol.config_fields, kind=channel.kind, config=merged, secrets=secrets, current_config=current,
            )
            _check_bound_secrets(db_session=db_session, principal=principal, prepared=prepared, fields=protocol.config_fields)
            stored_config = dict(prepared.config)
            for setting, value in prepared.new_secrets.items():
                vault_name = channel_secret_name(channel_id=str(channel.channel_id), setting=setting)
                current_value = current.get(setting, None)
                owns_current = current_value == secret_ref_for(name=vault_name)
                if owns_current is True and _vault_secret_exists(db_session=db_session, vault_name=vault_name) is True:
                    _rotate_channel_secret(db_session=db_session, principal=principal, vault_name=vault_name, value=value)
                else:
                    _store_channel_secret(
                        db_session=db_session, principal=principal, vault_name=vault_name, value=value,
                        scope_level=channel.scope_level, project_id=channel.project_id,
                    )
                    stored_names.append(vault_name)
                stored_config[setting] = secret_ref_for(name=vault_name)
                changed.append("secret:{}".format(setting))
            changed.extend(
                "config:{}".format(key) for key in sorted(stored_config)
                if key not in prepared.new_secrets and stored_config.get(key) != current.get(key)
            )
            channel.config = stored_config
        if disabled is not None and bool(disabled) != bool(channel.disabled):
            changed.append("disabled" if bool(disabled) is True else "enabled")
        if disabled is not None:
            channel.disabled = bool(disabled)
        channel.updated_at = utc_now()
        if len(changed) > 0:
            _stage_admin_event(
                db_session=db_session, topic=NotificationEventTopics.CHANNEL_UPDATED,
                payload={"channel_id": str(channel.channel_id), "name": channel.name, "changed": changed},
            )
        db_session.commit()
    except BaseException:
        db_session.rollback()
        _discard_channel_secrets(db_session=db_session, principal=principal, vault_names=stored_names)
        raise

    rtnval = channel
    return rtnval


def delete_channel(*, db_session: DbSession, channel_id: str, principal: Any = None) -> None:
    """
        Delete a channel, the messages recorded through it (and their dead letters) and the vault secrets the service stored for it (never a vault
        secret it merely points at).

        :param db_session: Active SQLAlchemy session.
        :param channel_id: The channel.
        :param principal: The authenticated caller, who deletes the channel's own vault secrets.

        :raises: ChannelNotFoundError, ChannelInUseError when a routing rule still sends through the channel.
    """
    channel = read_channel(db_session=db_session, channel_id=channel_id)
    using = [
        rule for rule in notification_repository.list_routing_rules(db_session=db_session, project_id=None)
        if str(channel.channel_id) in [str(item) for item in (rule.channel_ids or [])]
    ]
    if len(using) > 0:
        err_msg_lines = ["The channel '{}' cannot be deleted while routing rules send through it.".format(channel.name)]
        for rule in using:
            err_msg_lines.append("RULE: {} ({})".format(rule.event_pattern, rule.rule_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ChannelInUseError(err_msg) from None

    own_names = [
        secret_name_from_ref(ref=value) for value in (channel.config or {}).values()
        if is_secret_ref(value=value) is True
        and secret_name_from_ref(ref=value).startswith(channel_secret_name(channel_id=str(channel.channel_id), setting=""))
    ]
    _stage_admin_event(
        db_session=db_session, topic=NotificationEventTopics.CHANNEL_DELETED,
        payload={"channel_id": str(channel.channel_id), "name": channel.name, "kind": channel.kind},
    )
    notification_repository.delete_channel_history(db_session=db_session, channel_id=str(channel.channel_id))
    db_session.delete(channel)
    db_session.commit()
    _discard_channel_secrets(db_session=db_session, principal=principal, vault_names=own_names)
    return


def send_test_message(
        *,
        db_session: DbSession,
        channel_id: str,
        recipient: str,
        sent_by: str
    ) -> ChannelDeliveryOutcome:
    """
        Send one test message through a channel, so an administrator learns whether its settings work before a real event needs them.
        The attempt is recorded like any other delivery.

        :param db_session: Active SQLAlchemy session.
        :param channel_id: The channel.
        :param recipient: Who or where to send it (an address for email).
        :param sent_by: Who pressed the button, named in the message.

        :returns: How it went; a failed delivery is a result, not an exception.
        :raises: ChannelNotFoundError
    """
    channel = read_channel(db_session=db_session, channel_id=channel_id)
    try:
        dispatch_envelope(
            db_session=db_session,
            channel_id=str(channel.channel_id),
            recipient=recipient,
            event_topic="notification.channel.test",
            template_name="channel_test",
            payload={"channel_name": channel.name, "sent_by": sent_by},
        )
    except NotificationDispatchError:
        attempt = notification_repository.latest_attempt_for_channel(db_session=db_session, channel_id=str(channel.channel_id))
        message = attempt.error_message if attempt is not None and attempt.error_message else "The channel did not accept the message."
        latency = int(attempt.latency_ms or 0) if attempt is not None else 0
        rtnval = ChannelDeliveryOutcome(delivered=False, error_message=message, latency_ms=latency)
        return rtnval

    attempt = notification_repository.latest_attempt_for_channel(db_session=db_session, channel_id=str(channel.channel_id))
    latency = int(attempt.latency_ms or 0) if attempt is not None else 0
    rtnval = ChannelDeliveryOutcome(delivered=True, error_message="", latency_ms=latency)
    return rtnval


def _stage_admin_event(*, db_session: DbSession, topic: str, payload: Mapping[str, Any], actor_user_id: Optional[str] = None) -> None:
    """
        Stage an audit event for something an administrator did, to be published when the surrounding transaction commits. The acting user is the one
        given, or the one the session is tagged with; the client address rides along. Payloads carry names, never a secret value.
    """
    from ccai.pychestrate.webservice.audit.data_change_bridge import session_actor, session_client_address  # noqa: E402

    full_payload = dict(payload)
    full_payload["actor_user_id"] = actor_user_id if actor_user_id is not None else session_actor(db_session=db_session)
    full_payload["client_address"] = session_client_address(db_session=db_session)
    enqueue_event(db_session=db_session, event=EntityEvent(topic=topic, payload=full_payload, source_event_id=new_uuid()))
    return


def _vault_scope(*, scope_level: ChannelScopeLevel, project_id: Optional[str]) -> Tuple[SecretScopeKind, Optional[str]]:
    """
        The vault scope a channel's secrets are stored in: service-wide for a system channel, the project's for a project channel.
    """
    if scope_level == ChannelScopeLevel.PROJECT:
        rtnval = (SecretScopeKind.PROJECT, str(project_id))
    else:
        rtnval = (SecretScopeKind.ORG, None)
    return rtnval


def _store_channel_secret(
        *,
        db_session: DbSession,
        principal: Any,
        vault_name: str,
        value: str,
        scope_level: ChannelScopeLevel,
        project_id: Optional[str]
    ) -> None:
    """
        Write a channel's secret to the vault on behalf of ``principal``.

        :raises: ChannelSecretAccessDeniedError
    """
    if principal is None:
        raise ChannelSecretAccessDeniedError("Storing a channel's secret in the secrets vault needs a signed-in user.") from None
    scope_kind, scope_ref = _vault_scope(scope_level=scope_level, project_id=project_id)
    payload = SecretBytes(value.encode("utf-8"))
    try:
        secrets_service.put_secret(
            db_session=db_session,
            principal=principal,
            secret_ref=vault_name,
            plaintext=payload,
            aspects=build_default_secrets_aspects(),
            scope_kind=scope_kind,
            scope_ref=scope_ref,
        )
    except SecretAccessDeniedError:
        db_session.rollback()
        raise ChannelSecretAccessDeniedError(
            "You may not store secrets in the secrets vault. Storing a channel's secret needs system:secrets.admin"
            " (or, for a project channel, project membership plus system:project_secrets.write)."
        ) from None
    except SecretAlreadyExistsError:
        db_session.rollback()
        raise ChannelSecretAccessDeniedError("A vault secret named {} already exists.".format(vault_name)) from None
    finally:
        payload.close()
    return


def _rotate_channel_secret(*, db_session: DbSession, principal: Any, vault_name: str, value: str) -> None:
    """
        Install a new version of a channel's own vault secret.

        :raises: ChannelSecretAccessDeniedError
    """
    if principal is None:
        raise ChannelSecretAccessDeniedError("Replacing a channel's secret in the secrets vault needs a signed-in user.") from None
    payload = SecretBytes(value.encode("utf-8"))
    try:
        secrets_service.update_secret(
            db_session=db_session, principal=principal, secret_ref=vault_name, plaintext=payload,
            aspects=build_default_secrets_aspects(),
        )
    except SecretAccessDeniedError:
        db_session.rollback()
        raise ChannelSecretAccessDeniedError("You may not change secrets in the secrets vault. Replacing a channel's secret needs system:secrets.admin.") from None
    finally:
        payload.close()
    return


def _vault_secret_exists(*, db_session: DbSession, vault_name: str) -> bool:
    """
        Whether the vault holds a secret under ``vault_name``.
    """
    try:
        secrets_service.get_secret_record(db_session=db_session, secret_ref=vault_name)
    except SecretNotFoundError:
        return False
    return True


def _check_bound_secrets(
        *,
        db_session: DbSession,
        principal: Any,
        prepared: PreparedChannelConfig,
        fields: Tuple[Any, ...]
    ) -> None:
    """
        Refuse to point a channel at a vault secret that does not exist, has expired, or that ``principal`` may not read. Uses the vault's own
        read path so its access rules and audit apply to the binding. An address setting is also checked to be an address.

        :raises: ChannelConfigInvalidError, ChannelSecretAccessDeniedError
    """
    by_name = {field.name: field for field in fields}
    for setting, vault_name in prepared.bound_refs.items():
        if principal is None:
            raise ChannelSecretAccessDeniedError("Using a vault secret needs a signed-in user.") from None
        field = by_name[setting]
        try:
            read = secrets_service.read_secret(
                db_session=db_session, principal=principal, secret_ref=vault_name, aspects=build_default_secrets_aspects(),
            )
        except SecretNotFoundError:
            db_session.rollback()
            raise ChannelConfigInvalidError(["{} ('{}'): there is no secret named {} in the secrets vault. Create it first, or send the value in 'secrets'.".format(field.label, setting, vault_name)]) from None
        except SecretVersionExpiredError:
            db_session.rollback()
            raise ChannelConfigInvalidError(["{} ('{}'): the secret {} has expired. Rotate it in the secrets vault.".format(field.label, setting, vault_name)]) from None
        except SecretAccessDeniedError:
            db_session.rollback()
            raise ChannelSecretAccessDeniedError("You may not read the vault secret {}, so a channel cannot use it for you.".format(vault_name)) from None
        try:
            if field.field_type == "url":
                text = read.plaintext.reveal().decode("utf-8", errors="replace")
                if is_http_url(text=text) is False:
                    raise ChannelConfigInvalidError(["{} ('{}'): the secret {} does not hold an address starting http:// or https://.".format(field.label, setting, vault_name)]) from None
        finally:
            read.plaintext.close()
    return


def _discard_channel_secrets(*, db_session: DbSession, principal: Any, vault_names: List[str]) -> None:
    """
        Best-effort removal of vault secrets a channel created, so a failed create or a deleted channel leaves nothing behind.
    """
    if principal is None:
        return
    for vault_name in vault_names:
        try:
            secrets_service.delete_secret(
                db_session=db_session, principal=principal, secret_ref=vault_name, aspects=build_default_secrets_aspects(),
            )
        except Exception as xcpt:  # noqa: BLE001 -- best-effort compensation
            db_session.rollback()
            _LOGGER.warning("pychestrate.notifications.secret_cleanup_failed vault_name=%s error=%s", vault_name, type(xcpt).__name__)
    return


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
    outcome = _send_through_channel(
        db_session=db_session, channel=channel, channel_cls=channel_cls,
        recipient=recipient, subject=rendered.subject, body=rendered.body,
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
    _stage_admin_event(
        db_session=db_session, topic=NotificationEventTopics.RULE_CREATED, actor_user_id=actor_user_id,
        payload={
            "rule_id": str(rule.rule_id), "event_pattern": rule.event_pattern, "template_name": rule.template_name,
            "channel_ids": [str(item) for item in rule.channel_ids], "recipients": list(rule.recipients),
            "project_id": str(rule.project_id) if rule.project_id is not None else None,
        },
    )
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


def set_routing_rule_disabled(*, db_session: DbSession, rule_id: str, disabled: bool) -> NotificationRoutingRule:
    """
        Turn a routing rule off or on.

        :param db_session: Active SQLAlchemy session.
        :param rule_id: The rule.
        :param disabled: True to stop it sending, False to resume.

        :returns: The rule.
        :raises: ChannelNotFoundError when there is no such rule.
    """
    rule = notification_repository.get_routing_rule(db_session=db_session, rule_id=rule_id)
    if rule is None:
        err_msg_lines = ["Cannot change routing rule — not found."]
        err_msg_lines.append("RULE_ID: {}".format(rule_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ChannelNotFoundError(err_msg) from None
    rule.disabled = bool(disabled)
    rule.updated_at = utc_now()
    _stage_admin_event(
        db_session=db_session, topic=NotificationEventTopics.RULE_UPDATED,
        payload={"rule_id": str(rule.rule_id), "event_pattern": rule.event_pattern, "disabled": bool(disabled)},
    )
    db_session.commit()
    rtnval = rule
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

    _stage_admin_event(
        db_session=db_session, topic=NotificationEventTopics.RULE_DELETED,
        payload={"rule_id": str(rule.rule_id), "event_pattern": rule.event_pattern},
    )
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
    outcome = _send_through_channel(
        db_session=db_session, channel=channel, channel_cls=channel_cls,
        recipient=envelope.recipient, subject=envelope.rendered_subject, body=envelope.rendered_body,
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


def _send_through_channel(
        *,
        db_session: DbSession,
        channel: NotificationChannel,
        channel_cls: Any,
        recipient: str,
        subject: str,
        body: str
    ) -> ChannelDeliveryOutcome:
    """
        Read the channel's secrets from the vault and hand the message to its sender. A secret that cannot be read is a failed delivery (it is
        recorded and parked like any other), not an exception, and the message says which channel and setting.

        :returns: How the send went.
    """
    try:
        resolved_config = _resolve_config_secrets(
            db_session=db_session,
            config=channel.config if channel.config is not None else {},
            channel_name=channel.name,
        )
    except ChannelSecretUnavailableError as xcpt:
        rtnval = ChannelDeliveryOutcome(delivered=False, error_message=str(xcpt), latency_ms=0)
        return rtnval

    rtnval = channel_cls.send(
        channel_config=resolved_config,
        recipient=recipient,
        subject=subject,
        body=body,
    )
    return rtnval


def _resolve_config_secrets(
        *,
        db_session: DbSession,
        config: Mapping[str, Any],
        channel_name: str
    ) -> Mapping[str, Any]:
    """
        Replace each ``secret://<name>`` setting of a channel with the current value of that vault secret, read as the notification service
        (no user is present when a run fails). The result is handed to the sender and then dropped: it is not stored, logged, or put on an
        envelope or an event.

        :param db_session: Active SQLAlchemy session.
        :param config: What the channel stores.
        :param channel_name: The channel's name, for messages.

        :returns: A shallow copy with the secrets read.
        :raises: ChannelSecretUnavailableError when a secret is missing, expired or not text.
    """
    rtnval = {}
    for key, value in (config if config is not None else {}).items():
        if is_secret_ref(value=value) is False:
            rtnval[key] = value
            continue
        vault_name = secret_name_from_ref(ref=value)
        try:
            read = secrets_service.read_secret_for_service(
                db_session=db_session, secret_ref=vault_name, service_identity=NOTIFICATIONS_SERVICE_IDENTITY,
            )
        except (SecretNotFoundError, SecretVersionExpiredError):
            raise ChannelSecretUnavailableError(
                "The secret behind the setting '{}' of the channel '{}' is missing or has expired ({}). Enter it again on the Notifications page.".format(
                    key, channel_name, vault_name)
            ) from None
        try:
            rtnval[key] = read.plaintext.reveal().decode("utf-8")
        except UnicodeDecodeError:
            raise ChannelSecretUnavailableError(
                "The secret behind the setting '{}' of the channel '{}' is not text ({}).".format(key, channel_name, vault_name)
            ) from None
        finally:
            read.plaintext.close()
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
