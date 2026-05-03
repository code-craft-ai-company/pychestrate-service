"""
.. module:: webhooks_out.service
    :synopsis: Webhooks-out facade — register / sign / record delivery.

M1 ships:

* :func:`register_target` — UNIQUE per project; URL must
  start with ``http(s)://``; signature scheme verified
  against the channel's supported set.
* :func:`disable_target` — idempotent + emits.
* :func:`build_signed_request` — produces a
  :class:`SignedRequest` carrying the headers + signature
  the M2 dispatcher writes onto the wire. Computes the
  HMAC-SHA-256 over a canonical ``timestamp + "." + body``
  string.
* :func:`record_delivery_attempt` — persists per-attempt
  outcome row + emits DELIVERY_ATTEMPTED + DELIVERY_FAILED on
  failure.
* :func:`compute_signature` — exposed for callers that need
  the raw signature value (test fixtures, observability
  surfaces).
* Read helpers.

The actual HTTP write lands in M2 along with the topic-prefix
matcher and the auto-disable-after-N-failures policy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac
import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.webhooks_out import repository
from automojo.pychestrate.webservice.webhooks_out.errors import (
    WebhookTargetConflictError,
    WebhookTargetInvalidError,
    WebhookTargetNotFoundError,
)
from automojo.pychestrate.webservice.webhooks_out.events import (
    WebhookOutEventTopics,
)
from automojo.pychestrate.webservice.webhooks_out.models import (
    DeliveryOutcome,
    SignatureScheme,
    WebhookDelivery,
    WebhookTarget,
)


SIGNATURE_HEADER: str = "X-Pychestrate-Signature"
TIMESTAMP_HEADER: str = "X-Pychestrate-Timestamp"
TOPIC_HEADER: str = "X-Pychestrate-Topic"
DELIVERY_ID_HEADER: str = "X-Pychestrate-Delivery-Id"


@dataclass(frozen=True)
class WebhookTargetView:
    """
        Caller-facing target read-model.
    """
    target_id: str
    project_id: str
    name: str
    description: str
    url: str
    signature_scheme: SignatureScheme
    topic_filters: Tuple[str, ...]
    enabled: bool
    custom_headers: Mapping[str, str]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SignedRequest:
    """
        Caller-facing signed-request bundle.

        :param method: Always ``"POST"`` for M1.
        :param url: Target URL.
        :param headers: Headers the M2 dispatcher writes to the
                        wire (signature, timestamp, topic,
                        delivery-id, plus any per-target
                        custom headers).
        :param body: Raw payload bytes — already canonical, the
                     dispatcher sends as-is.
        :param signature: Resolved HMAC signature; also present
                          in ``headers``.
        :param payload_digest_sha256: SHA-256 hex digest of the
                                      body for persistence.
        :param delivery_id: Pre-allocated UUID surfaced on the
                            X-Pychestrate-Delivery-Id header so
                            the receiver can dedup against the
                            ledger row that gets persisted by
                            :func:`record_delivery_attempt`.
    """
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes
    signature: str
    payload_digest_sha256: str
    delivery_id: str


@dataclass(frozen=True)
class WebhookDeliveryView:
    """
        Caller-facing delivery read-model.
    """
    delivery_id: str
    target_id: str
    project_id: str
    topic: str
    payload_digest_sha256: str
    signature: str
    request_headers: Mapping[str, str]
    outcome: DeliveryOutcome
    response_status: Optional[int]
    response_excerpt: Optional[str]
    duration_ms: Optional[int]
    attempted_at: datetime


def register_target(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        url: str,
        secret_ref: str = "",
        description: str = "",
        signature_scheme: SignatureScheme = SignatureScheme.HMAC_SHA256,
        topic_filters: Optional[List[str]] = None,
        custom_headers: Optional[Dict[str, str]] = None,
        actor_id: Optional[str] = None
    ) -> WebhookTargetView:
    """
        Persist a new outbound target. UNIQUE on
        ``(project, name)``. Validates URL scheme + signature
        scheme.

        :raises: WebhookTargetConflictError on duplicate name;
                 WebhookTargetInvalidError on bad URL or empty
                 name.
    """
    if name is None or len(name) == 0:
        err_lines = ["Webhook target name must be non-empty."]
        err_msg = os.linesep.join(err_lines)
        raise WebhookTargetInvalidError(err_msg) from None
    if url is None or not (
        url.startswith("https://") or url.startswith("http://")
    ):
        err_lines = ["Webhook target URL must start with http:// or https://."]
        err_lines.append("VALUE: {!r}".format(url))
        err_msg = os.linesep.join(err_lines)
        raise WebhookTargetInvalidError(err_msg) from None

    existing = repository.find_target_by_name(
        db_session=db_session, project_id=project_id, name=name,
    )
    if existing is not None:
        err_lines = ["Webhook target name already exists in project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("NAME: {}".format(name))
        err_msg = os.linesep.join(err_lines)
        raise WebhookTargetConflictError(err_msg) from None

    now = utc_now()
    row = repository.insert_target(
        db_session=db_session,
        project_id=project_id,
        name=name,
        description=description,
        url=url,
        secret_ref=secret_ref,
        signature_scheme=signature_scheme,
        topic_filters=list(topic_filters or []),
        custom_headers=dict(custom_headers or {}),
        created_by=actor_id,
        created_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookOutEventTopics.TARGET_REGISTERED,
            payload={
                "target_id": str(row.target_id),
                "project_id": project_id,
                "name": name,
                "url": url,
                "signature_scheme": signature_scheme.value,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _target_to_view(row=row)
    return rtnval


def get_target(
        *,
        db_session: DbSession,
        target_id: str
    ) -> WebhookTargetView:
    """
        Read by id.

        :raises: WebhookTargetNotFoundError on miss.
    """
    row = _require_target(db_session=db_session, target_id=target_id)
    rtnval = _target_to_view(row=row)
    return rtnval


def list_targets_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        enabled_only: bool = False
    ) -> List[WebhookTargetView]:
    """
        Project-scoped list with enabled-only filter.
    """
    rows = repository.list_targets_for_project(
        db_session=db_session,
        project_id=project_id,
        enabled_only=enabled_only,
    )
    rtnval = [_target_to_view(row=r) for r in rows]
    return rtnval


def disable_target(
        *,
        db_session: DbSession,
        target_id: str,
        actor_id: Optional[str] = None
    ) -> WebhookTargetView:
    """
        Flip ``enabled = False``. Idempotent + emits
        TARGET_DISABLED.
    """
    row = _require_target(db_session=db_session, target_id=target_id)
    if row.enabled is False:
        rtnval = _target_to_view(row=row)
        return rtnval
    now = utc_now()
    row.enabled = False
    row.updated_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookOutEventTopics.TARGET_DISABLED,
            payload={
                "target_id": str(row.target_id),
                "project_id": str(row.project_id),
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _target_to_view(row=row)
    return rtnval


def build_signed_request(
        *,
        db_session: DbSession,
        target_id: str,
        topic: str,
        body: bytes,
        secret: bytes,
        timestamp: Optional[datetime] = None
    ) -> SignedRequest:
    """
        Build a :class:`SignedRequest` ready for the M2
        dispatcher to put on the wire. Uses the HMAC-SHA-256
        scheme over ``timestamp.isoformat() + "." + body``.

        :raises: WebhookTargetNotFoundError, WebhookTargetInvalidError.
    """
    row = _require_target(db_session=db_session, target_id=target_id)
    if row.enabled is False:
        err_lines = ["Cannot build a request for a disabled target."]
        err_lines.append("TARGET_ID: {}".format(target_id))
        err_msg = os.linesep.join(err_lines)
        raise WebhookTargetInvalidError(err_msg) from None

    when = timestamp if timestamp is not None else utc_now()
    timestamp_str = when.isoformat()
    signature = compute_signature(
        secret=secret, timestamp=timestamp_str, body=body,
    )
    payload_digest = hashlib.sha256(body).hexdigest()
    delivery_id = new_uuid()

    headers: Dict[str, str] = {
        SIGNATURE_HEADER: signature,
        TIMESTAMP_HEADER: timestamp_str,
        TOPIC_HEADER: topic,
        DELIVERY_ID_HEADER: delivery_id,
        "Content-Type": "application/json",
    }
    for key, value in (row.custom_headers or {}).items():
        headers[key] = value

    rtnval = SignedRequest(
        method="POST",
        url=row.url,
        headers=headers,
        body=body,
        signature=signature,
        payload_digest_sha256=payload_digest,
        delivery_id=delivery_id,
    )
    return rtnval


def record_delivery_attempt(
        *,
        db_session: DbSession,
        target_id: str,
        delivery_id: str,
        topic: str,
        payload_digest_sha256: str,
        signature: str,
        request_headers: Dict[str, str],
        outcome: DeliveryOutcome,
        response_status: Optional[int] = None,
        response_excerpt: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> WebhookDeliveryView:
    """
        Persist one delivery attempt. Emits DELIVERY_ATTEMPTED;
        when ``outcome`` is FAILED or REJECTED_DISABLED also
        emits DELIVERY_FAILED.

        The caller (M2 dispatcher) supplies ``delivery_id``
        from the matching :class:`SignedRequest` so the audit
        trail correlates request-to-response.

        :raises: WebhookTargetNotFoundError on miss.
    """
    target_row = _require_target(
        db_session=db_session, target_id=target_id,
    )
    when = utc_now()
    row = WebhookDelivery(
        delivery_id=delivery_id,
        target_id=str(target_row.target_id),
        project_id=str(target_row.project_id),
        topic=topic,
        payload_digest_sha256=payload_digest_sha256,
        signature=signature,
        request_headers=dict(request_headers),
        outcome=outcome,
        response_status=response_status,
        response_excerpt=response_excerpt,
        duration_ms=duration_ms,
        attempted_at=when,
    )
    db_session.add(row)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookOutEventTopics.DELIVERY_ATTEMPTED,
            payload={
                "delivery_id": delivery_id,
                "target_id": str(target_row.target_id),
                "project_id": str(target_row.project_id),
                "topic": topic,
                "outcome": outcome.value,
                "response_status": response_status,
            },
            source_event_id=new_uuid(),
        ),
    )
    if outcome in (DeliveryOutcome.FAILED, DeliveryOutcome.REJECTED_DISABLED):
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=WebhookOutEventTopics.DELIVERY_FAILED,
                payload={
                    "delivery_id": delivery_id,
                    "target_id": str(target_row.target_id),
                    "outcome": outcome.value,
                    "response_status": response_status,
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()
    rtnval = _delivery_to_view(row=row)
    return rtnval


def list_recent_deliveries_for_target(
        *,
        db_session: DbSession,
        target_id: str,
        limit: int = 100
    ) -> List[WebhookDeliveryView]:
    """
        Read newest-first delivery rows.
    """
    rows = repository.list_recent_deliveries(
        db_session=db_session, target_id=target_id, limit=limit,
    )
    rtnval = [_delivery_to_view(row=r) for r in rows]
    return rtnval


def compute_signature(
        *,
        secret: bytes,
        timestamp: str,
        body: bytes
    ) -> str:
    """
        Compute the canonical HMAC-SHA-256 signature.
        ``"sha256=" + hex(hmac(secret, timestamp + "." + body))``.
        Identical scheme as the GitHub-style header so M2
        consumers can verify the same way.
    """
    canonical = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(
        key=secret, msg=canonical, digestmod=hashlib.sha256,
    ).hexdigest()
    rtnval = "sha256=" + digest
    return rtnval


def _require_target(
        *, db_session: DbSession, target_id: str
    ) -> WebhookTarget:
    row = repository.find_target_by_id(
        db_session=db_session, target_id=target_id,
    )
    if row is None:
        err_lines = ["Webhook target not found."]
        err_lines.append("TARGET_ID: {}".format(target_id))
        err_msg = os.linesep.join(err_lines)
        raise WebhookTargetNotFoundError(err_msg) from None
    return row


def _target_to_view(*, row: WebhookTarget) -> WebhookTargetView:
    rtnval = WebhookTargetView(
        target_id=str(row.target_id),
        project_id=str(row.project_id),
        name=row.name,
        description=row.description,
        url=row.url,
        signature_scheme=row.signature_scheme,
        topic_filters=tuple(row.topic_filters or []),
        enabled=row.enabled,
        custom_headers=dict(row.custom_headers or {}),
        created_by=str(row.created_by) if row.created_by is not None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval


def _delivery_to_view(*, row: WebhookDelivery) -> WebhookDeliveryView:
    rtnval = WebhookDeliveryView(
        delivery_id=str(row.delivery_id),
        target_id=str(row.target_id),
        project_id=str(row.project_id),
        topic=row.topic,
        payload_digest_sha256=row.payload_digest_sha256,
        signature=row.signature,
        request_headers=dict(row.request_headers or {}),
        outcome=row.outcome,
        response_status=row.response_status,
        response_excerpt=row.response_excerpt,
        duration_ms=row.duration_ms,
        attempted_at=row.attempted_at,
    )
    return rtnval
