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
* :func:`enable_webhook` — flips ``enabled = True``, clears
  ``disabled_at``, idempotent + emits
  CONFIGURATION_ENABLED.
* :func:`create_webhook_with_secret` — the operator-facing
  create: stores the caller-supplied shared secret in
  ``1-secrets-vault`` (or binds an existing vault secret the
  caller may read) and persists only the vault reference.
* :func:`resolve_shared_secret` — resolves an integration's
  vault reference to the HMAC key at receive time.
* :func:`is_secret_ref_stored` — whether a reference names a
  secret that exists in the vault.

The shared secret itself never lives in
``webhooks_in_configurations``: ``secret_ref`` is always a
pointer into the vault, and nothing returns the secret.

The replay endpoint and the rotate-secret PATCH path land in
M2.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
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
from ccai.pychestrate.webservice.webhooks_in import repository
from ccai.pychestrate.webservice.webhooks_in.errors import (
    WebhookConfigurationConflictError,
    WebhookConfigurationInvalidError,
    WebhookConfigurationNotFoundError,
    WebhookProviderUnknownError,
    WebhookSecretAccessDeniedError,
    WebhookSecretInvalidError,
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


_LOGGER = logging.getLogger("pychestrate.webhooks_in.configuration")

#: Service identity the receiver presents when it resolves an
#: integration's shared secret through the secrets vault.
WEBHOOKS_IN_SERVICE_IDENTITY: str = "webhooks_in"

#: Prefix of the vault reference a caller-supplied shared secret is
#: stored under (8-webhooks-in design: ``webhooks.in.<provider>.
#: <hook_name>.secret``, plus the webhook id because a provider /
#: hook-name pair is only unique within one project).
WEBHOOK_SECRET_REF_PREFIX: str = "webhooks.in"


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
        actor_id: Optional[str] = None,
        webhook_id: Optional[str] = None
    ) -> WebhookConfigurationView:
    """
        Persist a new webhook configuration. UNIQUE on
        ``(project_id, provider, hook_name)``.

        ``secret_ref`` is a reference into ``1-secrets-vault`` --
        never the shared secret itself. The receiver resolves it
        through the vault on every delivery
        (:func:`resolve_shared_secret`); operator-facing callers go
        through :func:`create_webhook_with_secret`, which stores or
        verifies the vault secret first.

        :param webhook_id: Optional pre-allocated id; a fresh UUID
                           when ``None``.

        :raises: WebhookConfigurationInvalidError on empty
                 fields; WebhookProviderUnknownError when no
                 parser is registered for ``provider``;
                 WebhookConfigurationConflictError on duplicate.
    """
    if secret_ref is None or len(secret_ref) == 0:
        err_lines = ["Webhook secret_ref must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise WebhookConfigurationInvalidError(err_msg) from None

    _validate_new_configuration(
        db_session=db_session,
        project_id=project_id,
        provider=provider,
        hook_name=hook_name,
    )

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
        webhook_id=webhook_id,
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


def build_webhook_secret_ref(
        *,
        provider: str,
        hook_name: str,
        webhook_id: str
    ) -> str:
    """
        The vault reference a caller-supplied shared secret is stored
        under: ``webhooks.in.<provider>.<hook_name>.<webhook_id>.secret``.

        :param provider: Parser provider name.
        :param hook_name: Per-project hook nickname.
        :param webhook_id: The integration's id.

        :returns: The vault reference string.
    """
    rtnval = "{}.{}.{}.{}.secret".format(
        WEBHOOK_SECRET_REF_PREFIX, provider, hook_name, webhook_id,
    )
    return rtnval


def create_webhook_with_secret(
        *,
        db_session: DbSession,
        principal: Any,
        project_id: str,
        provider: str,
        hook_name: str,
        shared_secret: Optional[SecretBytes] = None,
        secret_ref: Optional[str] = None,
        mtls_required: bool = False,
        description: str = "",
        actor_id: Optional[str] = None
    ) -> WebhookConfigurationView:
    """
        Operator-facing create. Exactly one of ``shared_secret`` and
        ``secret_ref`` is supplied:

        * ``shared_secret`` -- the literal HMAC key. It is written to
          ``1-secrets-vault`` as a project-scoped secret under
          :func:`build_webhook_secret_ref`, on behalf of ``principal``
          (so the vault's own ACL and audit apply), and only that
          reference is persisted on the configuration.
        * ``secret_ref`` -- an existing vault secret. ``principal``
          must be allowed to read it; binding a secret you cannot
          read is refused.

        Every configuration check (field shape, registered parser,
        duplicate) runs before anything touches the vault, and a
        vault secret this call created is removed again if the
        configuration row cannot be written.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated caller (an
                          :class:`AuthPrincipal`).
        :param project_id: Owning project UUID.
        :param provider: Parser provider name.
        :param hook_name: Per-project hook nickname.
        :param shared_secret: The shared secret to store.
        :param secret_ref: Reference of an existing vault secret.
        :param mtls_required: Whether deliveries must arrive over mTLS.
        :param description: Free-form description.
        :param actor_id: Acting user id for the configured event.

        :returns: The created configuration read-model.

        :raises: WebhookConfigurationInvalidError,
                 WebhookProviderUnknownError,
                 WebhookConfigurationConflictError,
                 WebhookSecretInvalidError,
                 WebhookSecretAccessDeniedError.
    """
    has_secret = shared_secret is not None and len(shared_secret) > 0
    has_ref = secret_ref is not None and len(secret_ref) > 0
    if has_secret is True and has_ref is True:
        err_lines = ["Supply either a shared secret or an existing secret_ref, not both."]
        err_msg = os.linesep.join(err_lines)
        raise WebhookSecretInvalidError(err_msg) from None
    if has_secret is False and has_ref is False:
        err_lines = ["A shared secret (or an existing vault secret_ref) is required."]
        err_msg = os.linesep.join(err_lines)
        raise WebhookSecretInvalidError(err_msg) from None

    _validate_new_configuration(
        db_session=db_session,
        project_id=project_id,
        provider=provider,
        hook_name=hook_name,
    )

    webhook_id = new_uuid()
    stored_ref: Optional[str] = None
    if has_secret is True:
        resolved_ref = build_webhook_secret_ref(
            provider=provider, hook_name=hook_name, webhook_id=webhook_id,
        )
        _store_shared_secret(
            db_session=db_session,
            principal=principal,
            project_id=project_id,
            secret_ref=resolved_ref,
            shared_secret=shared_secret,
        )
        stored_ref = resolved_ref
    else:
        resolved_ref = secret_ref
        _require_readable_secret(
            db_session=db_session,
            principal=principal,
            secret_ref=resolved_ref,
        )

    try:
        rtnval = create_webhook(
            db_session=db_session,
            project_id=project_id,
            provider=provider,
            hook_name=hook_name,
            secret_ref=resolved_ref,
            mtls_required=mtls_required,
            description=description,
            actor_id=actor_id,
            webhook_id=webhook_id,
        )
    except Exception:
        db_session.rollback()
        if stored_ref is not None:
            _discard_stored_secret(
                db_session=db_session,
                principal=principal,
                secret_ref=stored_ref,
            )
        raise
    return rtnval


def resolve_shared_secret(
        *,
        db_session: DbSession,
        secret_ref: Optional[str]
    ) -> Optional[bytes]:
    """
        Resolve an integration's ``secret_ref`` through the secrets
        vault into the HMAC key the dispatcher verifies with.

        :param db_session: Active SQLAlchemy session.
        :param secret_ref: The configuration's vault reference.

        :returns: The shared-secret bytes, or ``None`` when the
                  reference does not resolve (missing, deleted, or
                  expired secret) -- the integration cannot verify
                  deliveries until an operator fixes it.
    """
    if secret_ref is None or len(secret_ref) == 0:
        return None
    try:
        read = secrets_service.read_secret_for_service(
            db_session=db_session,
            secret_ref=secret_ref,
            service_identity=WEBHOOKS_IN_SERVICE_IDENTITY,
        )
    except (SecretNotFoundError, SecretVersionExpiredError):
        return None
    rtnval = read.plaintext.reveal()
    return rtnval


def is_secret_ref_stored(
        *,
        db_session: DbSession,
        secret_ref: Optional[str]
    ) -> bool:
    """
        Whether ``secret_ref`` names a secret that exists in the
        vault. Read surfaces echo a configuration's reference only
        when this is True, so a value that is not a vault reference
        is never returned.

        :param db_session: Active SQLAlchemy session.
        :param secret_ref: The configuration's reference.

        :returns: True when the vault holds a record under the name.
    """
    if secret_ref is None or len(secret_ref) == 0:
        return False
    try:
        secrets_service.get_secret_record(
            db_session=db_session, secret_ref=secret_ref,
        )
    except SecretNotFoundError:
        return False
    rtnval = True
    return rtnval


def _validate_new_configuration(
        *,
        db_session: DbSession,
        project_id: str,
        provider: str,
        hook_name: str
    ) -> None:
    """
        Run the create-time checks shared by :func:`create_webhook`
        and :func:`create_webhook_with_secret`.

        :raises: WebhookConfigurationInvalidError on empty fields;
                 WebhookProviderUnknownError when no parser is
                 registered for ``provider``;
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

    parser_cls = _resolve_parser(provider=provider)
    if parser_cls is None:
        err_lines = ["No registered parser for provider."]
        err_lines.append("PROVIDER: {!r}".format(provider))
        err_lines.append("REGISTERED: {}".format(
            ", ".join(list_registered_providers()) or "(none)",
        ))
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
    return


def list_registered_providers() -> List[str]:
    """
        The provider names with a registered inbound parser, sorted.

        :returns: Provider names.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=InboundWebhookParserProtocol.factory_protocol_name,
    )
    names: List[str] = []
    for impl in candidates:
        try:
            name = impl.provider_name()
        except NotImplementedError:
            continue
        if name not in names:
            names.append(name)
    rtnval = sorted(names)
    return rtnval


def _store_shared_secret(
        *,
        db_session: DbSession,
        principal: Any,
        project_id: str,
        secret_ref: str,
        shared_secret: SecretBytes
    ) -> None:
    """
        Write a caller-supplied shared secret to the vault as a
        project-scoped secret, translating the vault's errors.

        :raises: WebhookSecretAccessDeniedError, WebhookSecretInvalidError.
    """
    if principal is None:
        err_lines = ["Storing a webhook secret requires an authenticated principal."]
        err_msg = os.linesep.join(err_lines)
        raise WebhookSecretAccessDeniedError(err_msg) from None
    try:
        secrets_service.put_secret(
            db_session=db_session,
            principal=principal,
            secret_ref=secret_ref,
            plaintext=shared_secret,
            aspects=build_default_secrets_aspects(),
            scope_kind=SecretScopeKind.PROJECT,
            scope_ref=project_id,
        )
    except SecretAccessDeniedError:
        db_session.rollback()
        err_lines = ["You may not store secrets for this project."]
        err_lines.append(
            "Storing the webhook's shared secret in the secrets vault needs"
            " system:secrets.admin, or project membership plus"
            " system:project_secrets.write."
        )
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_msg = os.linesep.join(err_lines)
        raise WebhookSecretAccessDeniedError(err_msg) from None
    except SecretAlreadyExistsError:
        db_session.rollback()
        err_lines = ["A vault secret already exists under the integration's reference."]
        err_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_lines)
        raise WebhookSecretInvalidError(err_msg) from None
    return


def _require_readable_secret(
        *,
        db_session: DbSession,
        principal: Any,
        secret_ref: str
    ) -> None:
    """
        Refuse to bind a vault secret that does not exist, has
        expired, or that ``principal`` may not read. Uses the vault's
        own read path so its ACL and audit apply to the binding.

        :raises: WebhookSecretInvalidError, WebhookSecretAccessDeniedError.
    """
    if principal is None:
        err_lines = ["Binding a vault secret requires an authenticated principal."]
        err_msg = os.linesep.join(err_lines)
        raise WebhookSecretAccessDeniedError(err_msg) from None
    try:
        secrets_service.read_secret(
            db_session=db_session,
            principal=principal,
            secret_ref=secret_ref,
            aspects=build_default_secrets_aspects(),
        )
    except SecretNotFoundError:
        db_session.rollback()
        err_lines = ["secret_ref does not name a secret in the secrets vault."]
        err_lines.append(
            "Create the secret first, or send the shared secret itself as"
            " 'secret' and it will be stored in the vault for you."
        )
        err_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_lines)
        raise WebhookSecretInvalidError(err_msg) from None
    except SecretVersionExpiredError:
        db_session.rollback()
        err_lines = ["The vault secret's active version has expired."]
        err_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_lines)
        raise WebhookSecretInvalidError(err_msg) from None
    except SecretAccessDeniedError:
        db_session.rollback()
        err_lines = ["You may not read the vault secret named by secret_ref."]
        err_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_lines)
        raise WebhookSecretAccessDeniedError(err_msg) from None
    return


def _discard_stored_secret(
        *,
        db_session: DbSession,
        principal: Any,
        secret_ref: str
    ) -> None:
    """
        Best-effort removal of a vault secret stored by a create that
        then failed, so a failed create leaves nothing behind.

        :returns: None.
    """
    try:
        secrets_service.delete_secret(
            db_session=db_session,
            principal=principal,
            secret_ref=secret_ref,
            aspects=build_default_secrets_aspects(),
        )
    except Exception as xcpt:  # noqa: BLE001 -- best-effort compensation
        db_session.rollback()
        _LOGGER.warning(
            "pychestrate.webhooks_in.secret_cleanup_failed secret_ref=%s error=%s",
            secret_ref,
            type(xcpt).__name__,
        )
    return


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


def enable_webhook(
        *,
        db_session: DbSession,
        webhook_id: str,
        actor_id: Optional[str] = None
    ) -> WebhookConfigurationView:
    """
        Flip ``enabled = True`` and clear ``disabled_at``.
        Idempotent + emits
        :data:`WebhookInEventTopics.CONFIGURATION_ENABLED`
        on the first transition.

        :param db_session: Active SQLAlchemy session.
        :param webhook_id: Configuration to enable.
        :param actor_id: Optional acting-user id for the event.

        :returns: The refreshed configuration read-model.

        :raises: WebhookConfigurationNotFoundError on miss.
    """
    row = _require_configuration(
        db_session=db_session, webhook_id=webhook_id,
    )
    if row.enabled is True:
        rtnval = _row_to_view(row=row)
        return rtnval
    row.enabled = True
    row.disabled_at = None
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookInEventTopics.CONFIGURATION_ENABLED,
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
