"""
.. module:: orchestration.source.service
    :synopsis: Source-integrations facade — config / webhook / dedup.

M1 ships:

* :func:`set_project_config` — bind a project to an SCM
  provider + repo + pipeline file path.
* :func:`handle_webhook` — verify signature → dedup delivery
  id → parse event → emit ``entity.source.webhook.received``.
  When the caller supplies ``aspects.pipeline_document_fetcher``,
  the resolved pipeline document bytes are returned on the
  :class:`WebhookAckResult` so the caller can hand them off to
  :func:`pipelines.definition.trigger_run`. M2 wires that
  handoff inside the service once the HTTP / object-store
  fetch boundary lands.
* :func:`record_last_seen_head` — cache the (project, ref, sha)
  triple so the M2 polling worker can skip already-seen heads.
* Read helpers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import json
import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.orchestration.source import repository
from ccai.pychestrate.webservice.orchestration.source.errors import (
    ScmConfigNotFoundError,
    ScmPayloadInvalidError,
    ScmProviderNotFoundError,
    ScmSignatureInvalidError,
)
from ccai.pychestrate.webservice.orchestration.source.events import (
    SourceEventTopics,
)
from ccai.pychestrate.webservice.orchestration.source.factories.provider_protocol import (
    ParsedWebhook,
    ScmEventKind,
    ScmProviderProtocol,
)
from ccai.pychestrate.webservice.orchestration.source.models import (
    ScmLastSeenHead,
    ScmProjectConfig,
    ScmWebhookDelivery,
)


SCM_PROVIDER_PROTOCOL: str = "scm_provider"
DEFAULT_PIPELINE_FILE_PATH: str = ".pychestrate/pipeline.yaml"
WEBHOOK_PAYLOAD_MAX_BYTES: int = 1 * 1024 * 1024
DELIVERIES_DEFAULT_LIMIT: int = 100

# Default ref a build checks out when the project config does not
# pin a polling ref glob to a concrete branch.
DEFAULT_SOURCE_REF: str = "main"
# Provider host used to expand a ``github`` ``owner/repo`` repo_key
# into an HTTPS clone URL.
GITHUB_HTTPS_HOST: str = "https://github.com/"


PipelineDocumentFetcher = Callable[[str, str, str], bytes]


class WebhookAckState(str, enum.Enum):
    """
        Outcome of :func:`handle_webhook`.

        * ``ACCEPTED`` — first time we have seen this delivery.
        * ``DEDUPED`` — duplicate delivery; nothing persisted on
          the second arrival apart from the dedup-suppressed
          topic.
        * ``REJECTED`` — signature verification failed or the
          payload was unparseable.
    """
    ACCEPTED = "accepted"
    DEDUPED = "deduped"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SourceIntegrationsAspects:
    """
        Caller-tunable knobs for :func:`handle_webhook`.

        :param secret: HMAC secret used by the provider's
                       signature verifier. Required.
        :param pipeline_document_fetcher: Optional callback
                                          ``(repo_key, ref,
                                          commit_sha) ->
                                          document_bytes``. M2
                                          wires the real HTTP
                                          fetcher; M1 callers
                                          inject one (typically
                                          a stub in tests).
    """
    secret: bytes
    pipeline_document_fetcher: Optional[PipelineDocumentFetcher] = None


@dataclass(frozen=True)
class WebhookAckResult:
    """
        Caller-facing outcome surface.

        :param state: Resolved :class:`WebhookAckState`.
        :param event_kind: The provider's resolved event kind.
        :param delivery_id: The provider-supplied delivery id.
        :param parsed: The provider's typed parse result.
        :param pipeline_document_bytes: When the caller
                                        supplied a fetcher,
                                        the bytes returned by
                                        it are forwarded here
                                        so the caller can hand
                                        them to
                                        :func:`pipelines.definition.trigger_run`.
        :param reason: Human-readable explanation when
                       ``state != ACCEPTED``.
    """
    state: WebhookAckState
    event_kind: ScmEventKind
    delivery_id: str
    parsed: Optional[ParsedWebhook] = None
    pipeline_document_bytes: Optional[bytes] = None
    reason: str = ""


@dataclass(frozen=True)
class ScmProjectConfigView:
    """
        Caller-facing project-config read-model.
    """
    project_id: str
    provider_name: str
    repo_key: str
    pipeline_file_path: str
    use_polling: bool
    polling_ref_glob: str
    last_poll_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SourceReferenceView:
    """
        Resolved structured source reference for a build job.

        The build orchestrator resolves a registered
        ``source-integration`` into this read-model and embeds it as
        the ``source`` block of the ``job_kind=build`` JobEnvelope.

        :param integration_id: UUID of the registered
                               source-integration the reference was
                               resolved from.
        :param kind: Source-integration kind discriminator. Only
                     ``"git"`` is modeled today.
        :param url: Clone / fetch URL for the source repository.
        :param ref: Default ref (branch / tag) the build checks out.
        :param credentials_ref: Symbolic secret reference (NOT the
                                credential value) the client agent
                                resolves to fetch a private
                                repository. Empty string for a
                                public repository -- full credential
                                vaulting is a documented follow-up.
    """
    integration_id: str
    kind: str
    url: str
    ref: str
    credentials_ref: str = ""


@dataclass(frozen=True)
class ScmWebhookDeliveryView:
    """
        Caller-facing delivery read-model.
    """
    project_id: str
    delivery_id: str
    provider_name: str
    event_kind: str
    received_at: datetime
    first_seen_at: datetime


@dataclass(frozen=True)
class ScmLastSeenHeadView:
    """
        Caller-facing last-seen-head read-model.
    """
    project_id: str
    ref: str
    commit_sha: str
    observed_at: datetime


def set_project_config(
        *,
        db_session: DbSession,
        project_id: str,
        provider_name: str,
        repo_key: str,
        pipeline_file_path: str = DEFAULT_PIPELINE_FILE_PATH,
        use_polling: bool = False,
        polling_ref_glob: str = ""
    ) -> ScmProjectConfigView:
    """
        Persist (or update) the per-project SCM config and emit
        :data:`SourceEventTopics.PROJECT_CONFIG_SET`.

        :raises: ScmProviderNotFoundError when ``provider_name``
                 has no registered factory implementation.
    """
    _resolve_provider(provider_name=provider_name)
    now = utc_now()
    row = repository.upsert_project_config(
        db_session=db_session,
        project_id=project_id,
        provider_name=provider_name,
        repo_key=repo_key,
        pipeline_file_path=pipeline_file_path,
        use_polling=use_polling,
        polling_ref_glob=polling_ref_glob,
        now=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SourceEventTopics.PROJECT_CONFIG_SET,
            payload={
                "project_id": project_id,
                "provider_name": provider_name,
                "repo_key": repo_key,
                "pipeline_file_path": pipeline_file_path,
                "use_polling": use_polling,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _config_to_view(row=row)
    return rtnval


def get_project_config(
        *,
        db_session: DbSession,
        project_id: str
    ) -> ScmProjectConfigView:
    """
        Read the per-project SCM config.

        :raises: ScmConfigNotFoundError on miss.
    """
    row = repository.find_project_config(
        db_session=db_session, project_id=project_id,
    )
    if row is None:
        err_lines = ["No SCM config for project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_msg = os.linesep.join(err_lines)
        raise ScmConfigNotFoundError(err_msg) from None
    rtnval = _config_to_view(row=row)
    return rtnval


def resolve_source_reference(
        *,
        db_session: DbSession,
        integration_id: str
    ) -> SourceReferenceView:
    """
        Resolve a registered ``source-integration`` into the
        structured source reference the build orchestrator embeds as
        the ``source`` block of a ``job_kind=build`` JobEnvelope.

        The source domain models one SCM project config per project
        and the REST surface presents the ``project_id`` itself as
        the ``integration_id`` -- so a resolve looks the config up by
        ``project_id == integration_id``.

        The repo URL is derived from the provider + ``repo_key``: a
        ``github`` provider's ``owner/repo`` key expands to an HTTPS
        clone URL. ``credentials_ref`` is left empty -- public-repo
        sources are in scope for this PR; private-repo credential
        vaulting is a documented follow-up. The field is reserved on
        the envelope so the follow-up needs no schema change.

        :param db_session: Active SQLAlchemy session.
        :param integration_id: UUID of the registered
                               source-integration to resolve.

        :returns: :class:`SourceReferenceView`.
        :raises: ScmConfigNotFoundError when no source integration is
                 registered for ``integration_id``.
    """
    row = repository.find_project_config(
        db_session=db_session, project_id=integration_id,
    )
    if row is None:
        err_lines = ["No source integration registered for id."]
        err_lines.append("INTEGRATION_ID: {}".format(integration_id))
        err_msg = os.linesep.join(err_lines)
        raise ScmConfigNotFoundError(err_msg) from None

    url = _repo_url_for_provider(
        provider_name=row.provider_name,
        repo_key=row.repo_key,
    )
    ref = _default_ref_for_config(row=row)
    rtnval = SourceReferenceView(
        integration_id=str(row.project_id),
        kind="git",
        url=url,
        ref=ref,
        credentials_ref="",
    )
    return rtnval


def handle_webhook(
        *,
        db_session: DbSession,
        project_id: str,
        raw_headers: Mapping[str, str],
        raw_body: bytes,
        aspects: SourceIntegrationsAspects
    ) -> WebhookAckResult:
    """
        Verify, dedup, and parse an inbound webhook. Returns a
        :class:`WebhookAckResult` describing the outcome.

        :raises: ScmConfigNotFoundError when the project has no
                 SCM config.
        :raises: ScmProviderNotFoundError when the configured
                 provider has no registered factory.
        :raises: ScmPayloadInvalidError when the body exceeds
                 :data:`WEBHOOK_PAYLOAD_MAX_BYTES` or fails
                 JSON parsing.
        :raises: ScmSignatureInvalidError when signature
                 verification fails.
    """
    config = repository.find_project_config(
        db_session=db_session, project_id=project_id,
    )
    if config is None:
        err_lines = ["No SCM config for project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_msg = os.linesep.join(err_lines)
        raise ScmConfigNotFoundError(err_msg) from None

    if raw_body is None:
        raw_body = b""
    if len(raw_body) > WEBHOOK_PAYLOAD_MAX_BYTES:
        err_lines = ["Webhook body exceeds the M1 cap."]
        err_lines.append("LENGTH: {}".format(len(raw_body)))
        err_lines.append("MAX: {}".format(WEBHOOK_PAYLOAD_MAX_BYTES))
        err_msg = os.linesep.join(err_lines)
        raise ScmPayloadInvalidError(err_msg) from None

    provider_cls = _resolve_provider(provider_name=config.provider_name)
    headers = provider_cls.normalize_headers(raw_headers=raw_headers)
    if headers.delivery_id is None or len(headers.delivery_id) == 0:
        err_lines = ["Webhook missing delivery id header."]
        err_lines.append("PROVIDER: {}".format(config.provider_name))
        err_msg = os.linesep.join(err_lines)
        raise ScmPayloadInvalidError(err_msg) from None

    valid = provider_cls.verify_signature(
        secret=aspects.secret, raw_body=raw_body, headers=headers,
    )
    if valid is False:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=SourceEventTopics.WEBHOOK_REJECTED,
                payload={
                    "project_id": project_id,
                    "delivery_id": headers.delivery_id,
                    "provider_name": config.provider_name,
                    "reason": "signature_invalid",
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        err_lines = ["Webhook signature verification failed."]
        err_lines.append("DELIVERY_ID: {}".format(headers.delivery_id))
        err_lines.append("PROVIDER: {}".format(config.provider_name))
        err_msg = os.linesep.join(err_lines)
        raise ScmSignatureInvalidError(err_msg) from None

    existing = repository.find_webhook_delivery(
        db_session=db_session,
        project_id=project_id,
        delivery_id=headers.delivery_id,
    )
    if existing is not None:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=SourceEventTopics.WEBHOOK_DEDUPED,
                payload={
                    "project_id": project_id,
                    "delivery_id": headers.delivery_id,
                    "provider_name": config.provider_name,
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        rtnval = WebhookAckResult(
            state=WebhookAckState.DEDUPED,
            event_kind=ScmEventKind(existing.event_kind)
            if _is_known_event_kind(existing.event_kind)
            else ScmEventKind.UNKNOWN,
            delivery_id=headers.delivery_id,
            reason="duplicate delivery id",
        )
        return rtnval

    payload: Mapping[str, Any] = {}
    if len(raw_body) > 0:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as decode_err:
            err_lines = ["Webhook body is not valid JSON."]
            err_lines.append("DELIVERY_ID: {}".format(headers.delivery_id))
            err_lines.append("DETAIL: {}".format(decode_err))
            err_msg = os.linesep.join(err_lines)
            raise ScmPayloadInvalidError(err_msg) from None
    parsed = provider_cls.parse_event(headers=headers, payload=payload)

    now = utc_now()
    repository.insert_webhook_delivery(
        db_session=db_session,
        project_id=project_id,
        delivery_id=headers.delivery_id,
        provider_name=config.provider_name,
        event_kind=parsed.event_kind.value,
        received_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SourceEventTopics.WEBHOOK_RECEIVED,
            payload={
                "project_id": project_id,
                "delivery_id": headers.delivery_id,
                "provider_name": config.provider_name,
                "event_kind": parsed.event_kind.value,
            },
            source_event_id=new_uuid(),
        ),
    )

    document_bytes: Optional[bytes] = None
    if (
        aspects.pipeline_document_fetcher is not None
        and parsed.event_kind == ScmEventKind.PUSH
        and parsed.push is not None
    ):
        document_bytes = aspects.pipeline_document_fetcher(
            parsed.push.repo_key,
            parsed.push.ref,
            parsed.push.commit_sha,
        )
        repository.upsert_last_seen_head(
            db_session=db_session,
            project_id=project_id,
            ref=parsed.push.ref,
            commit_sha=parsed.push.commit_sha,
            observed_at=now,
        )
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=SourceEventTopics.PIPELINE_TRIGGERED,
                payload={
                    "project_id": project_id,
                    "delivery_id": headers.delivery_id,
                    "ref": parsed.push.ref,
                    "commit_sha": parsed.push.commit_sha,
                    "pipeline_file_path": config.pipeline_file_path,
                },
                source_event_id=new_uuid(),
            ),
        )

    db_session.commit()
    rtnval = WebhookAckResult(
        state=WebhookAckState.ACCEPTED,
        event_kind=parsed.event_kind,
        delivery_id=headers.delivery_id,
        parsed=parsed,
        pipeline_document_bytes=document_bytes,
    )
    return rtnval


def record_last_seen_head(
        *,
        db_session: DbSession,
        project_id: str,
        ref: str,
        commit_sha: str
    ) -> ScmLastSeenHeadView:
    """
        Persist a (project, ref, sha) triple so the M2 polling
        worker can skip already-seen heads. Emits
        :data:`SourceEventTopics.LAST_SEEN_HEAD_UPDATED`.
    """
    now = utc_now()
    row = repository.upsert_last_seen_head(
        db_session=db_session,
        project_id=project_id,
        ref=ref,
        commit_sha=commit_sha,
        observed_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SourceEventTopics.LAST_SEEN_HEAD_UPDATED,
            payload={
                "project_id": project_id,
                "ref": ref,
                "commit_sha": commit_sha,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _last_seen_to_view(row=row)
    return rtnval


def get_last_seen_head(
        *,
        db_session: DbSession,
        project_id: str,
        ref: str
    ) -> Optional[ScmLastSeenHeadView]:
    """
        Read the (project, ref) last-seen-head; returns ``None``
        on miss (no exception — this is a polling-worker
        helper).
    """
    row = repository.find_last_seen_head(
        db_session=db_session, project_id=project_id, ref=ref,
    )
    if row is None:
        return None
    rtnval = _last_seen_to_view(row=row)
    return rtnval


def list_recent_deliveries(
        *,
        db_session: DbSession,
        project_id: str,
        limit: int = DELIVERIES_DEFAULT_LIMIT
    ) -> List[ScmWebhookDeliveryView]:
    """
        List recent webhook deliveries for diagnostics.
    """
    rows = repository.list_recent_deliveries(
        db_session=db_session, project_id=project_id, limit=limit,
    )
    rtnval = [_delivery_to_view(row=r) for r in rows]
    return rtnval


def _resolve_provider(*, provider_name: str) -> Type[ScmProviderProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=SCM_PROVIDER_PROTOCOL,
    )
    for impl in candidates:
        if impl.provider_name() == provider_name:
            return impl
    err_lines = ["No registered scm_provider for name."]
    err_lines.append("PROVIDER_NAME: {}".format(provider_name))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.provider_name() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise ScmProviderNotFoundError(err_msg) from None


def _repo_url_for_provider(*, provider_name: str, repo_key: str) -> str:
    """
        Expand a provider-specific ``repo_key`` into a clone URL.

        A ``github`` provider stores ``owner/repo`` as its repo_key;
        that expands to an HTTPS clone URL. A repo_key that is
        already an absolute URL (``http(s)://`` or ``git@``) is
        returned verbatim so non-GitHub providers and explicit URLs
        pass through unchanged.

        :param provider_name: Registered SCM provider name.
        :param repo_key: Provider-specific repository identifier.

        :returns: Clone / fetch URL string.
    """
    if repo_key.startswith("http://") or repo_key.startswith("https://"):
        rtnval = repo_key
        return rtnval
    if repo_key.startswith("git@"):
        rtnval = repo_key
        return rtnval
    if provider_name == "github":
        trimmed = repo_key.strip("/")
        rtnval = GITHUB_HTTPS_HOST + trimmed + ".git"
        return rtnval
    rtnval = repo_key
    return rtnval


def _default_ref_for_config(*, row: ScmProjectConfig) -> str:
    """
        Resolve the default ref a build checks out for a project
        config. When the config pins a concrete polling ref (no glob
        metacharacters) that ref is used; otherwise the build falls
        back to :data:`DEFAULT_SOURCE_REF`.

        :param row: SCM project-config ORM row.

        :returns: Ref string.
    """
    glob = row.polling_ref_glob
    if glob is not None and len(glob) > 0:
        has_meta = "*" in glob or "?" in glob or "[" in glob
        if has_meta is False:
            rtnval = glob
            return rtnval
    rtnval = DEFAULT_SOURCE_REF
    return rtnval


def _is_known_event_kind(value: str) -> bool:
    for kind in ScmEventKind:
        if kind.value == value:
            return True
    return False


def _config_to_view(*, row: ScmProjectConfig) -> ScmProjectConfigView:
    rtnval = ScmProjectConfigView(
        project_id=str(row.project_id),
        provider_name=row.provider_name,
        repo_key=row.repo_key,
        pipeline_file_path=row.pipeline_file_path,
        use_polling=row.use_polling,
        polling_ref_glob=row.polling_ref_glob,
        last_poll_at=row.last_poll_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval


def _delivery_to_view(*, row: ScmWebhookDelivery) -> ScmWebhookDeliveryView:
    rtnval = ScmWebhookDeliveryView(
        project_id=str(row.project_id),
        delivery_id=row.delivery_id,
        provider_name=row.provider_name,
        event_kind=row.event_kind,
        received_at=row.received_at,
        first_seen_at=row.first_seen_at,
    )
    return rtnval


def _last_seen_to_view(*, row: ScmLastSeenHead) -> ScmLastSeenHeadView:
    rtnval = ScmLastSeenHeadView(
        project_id=str(row.project_id),
        ref=row.ref,
        commit_sha=row.commit_sha,
        observed_at=row.observed_at,
    )
    return rtnval
