"""
.. module:: webhooks_in.dispatcher
    :synopsis: Top-level inbound-webhook dispatch pipeline.

The dispatcher composes the individual primitives — parser
resolution, signature verification, replay-cache de-duplication,
parser invocation, and normalized-event publishing — into one
total function. The function is *total*: every uncaught
exception from a parser is reclassified as a
:class:`StructuredRejection` so the inbound surface never
returns 500 because of a parser bug.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.webhooks_in import (
    normalization,
    repository,
    replay_cache,
    verification,
)
from ccai.pychestrate.webservice.webhooks_in.events import (
    WebhookInEventTopics,
)
from ccai.pychestrate.webservice.webhooks_in.factories.inbound_webhook_parser import (
    InboundWebhookParserProtocol,
)
from ccai.pychestrate.webservice.webhooks_in.models import (
    ParsedWebhook,
    StructuredRejection,
    WebhookConfiguration,
)


@dataclass(frozen=True)
class WebhookDispatchResult:
    """
        Result handed back to the controller. ``status`` is one
        of:

        * ``"dispatched"`` — verified, parsed, and events
          published.
        * ``"replay_ignored"`` — verified but a duplicate
          delivery; no events published.
        * ``"rejected"`` — verification or parser produced a
          :class:`StructuredRejection`.
    """
    status: str
    request_id: str
    provider: str
    hook_name: str
    delivery_id: Optional[str]
    domain_event_count: int
    rejection: Optional[StructuredRejection]
    matched_signature_header: Optional[str]


def dispatch_inbound_webhook(
        *,
        db_session: DbSession,
        provider: str,
        hook_name: str,
        raw_bytes: bytes,
        headers: Mapping[str, str],
        shared_secret: bytes,
        remote_ip: str = "",
        request_id: Optional[str] = None,
        mtls_subject: Optional[str] = None
    ) -> WebhookDispatchResult:
    """
        Run the verify → dedup → parse → publish pipeline.

        :param db_session: Open DB session; the helper owns the
                           commit on success and on rejection.
        :param provider: URL segment selecting the parser.
        :param hook_name: Per-project nickname.
        :param raw_bytes: Raw request body bytes.
        :param headers: Request headers mapping (case-insensitive
                        on read).
        :param shared_secret: Resolved bytes for the configured
                              webhook. The REST receiver resolves
                              them from the secrets vault via
                              :func:`configuration_service.resolve_shared_secret`;
                              the configuration row only holds
                              the vault reference.
        :param remote_ip: Source IP used by the audit log.
        :param request_id: Caller-supplied id; the helper
                           synthesizes one when missing.
        :param mtls_subject: Subject DN when the request arrived
                             over mTLS.
    """
    correlation_id = (
        request_id if request_id is not None and len(request_id) > 0
        else new_uuid()
    )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookInEventTopics.RECEIVED,
            payload={
                "provider": provider,
                "hook_name": hook_name,
                "request_id": correlation_id,
                "remote_ip": remote_ip,
                "mtls_subject": mtls_subject,
            },
            source_event_id=new_uuid(),
        ),
    )

    parser_cls = _resolve_parser(provider=provider)
    if parser_cls is None:
        rejection = StructuredRejection(
            reason="provider_unknown",
            detail="No registered parser for provider {!r}.".format(provider),
            recoverable=False,
            status_code=404,
        )
        rtnval = _emit_rejection(
            db_session=db_session,
            rejection=rejection,
            provider=provider,
            hook_name=hook_name,
            request_id=correlation_id,
            delivery_id=None,
            matched_header=None,
        )
        return rtnval

    config = _resolve_configuration(
        db_session=db_session,
        provider=provider,
        hook_name=hook_name,
    )
    if config is None:
        rejection = StructuredRejection(
            reason="configuration_not_found",
            detail="No enabled configuration for {!r}/{!r}.".format(
                provider, hook_name,
            ),
            recoverable=False,
            status_code=404,
        )
        rtnval = _emit_rejection(
            db_session=db_session,
            rejection=rejection,
            provider=provider,
            hook_name=hook_name,
            request_id=correlation_id,
            delivery_id=None,
            matched_header=None,
        )
        return rtnval

    if config.mtls_required is True and (
        mtls_subject is None or len(mtls_subject) == 0
    ):
        rejection = StructuredRejection(
            reason="mtls_required",
            detail="Configured webhook requires mTLS but no subject was presented.",
            recoverable=False,
            status_code=401,
        )
        rtnval = _emit_rejection(
            db_session=db_session,
            rejection=rejection,
            provider=provider,
            hook_name=hook_name,
            request_id=correlation_id,
            delivery_id=None,
            matched_header=None,
        )
        return rtnval

    verdict = verification.verify_signature(
        parser=parser_cls,
        raw_bytes=raw_bytes,
        headers=headers,
        shared_secret=shared_secret,
    )
    if verdict.verified is False:
        rejection = StructuredRejection(
            reason=verdict.reason or "signature_invalid",
            detail="Signature verification failed.",
            recoverable=False,
            status_code=401,
        )
        rtnval = _emit_rejection(
            db_session=db_session,
            rejection=rejection,
            provider=provider,
            hook_name=hook_name,
            request_id=correlation_id,
            delivery_id=None,
            matched_header=None,
        )
        return rtnval

    delivery_id = _read_delivery_id(parser=parser_cls, headers=headers)
    if delivery_id is not None and len(delivery_id) > 0:
        outcome = replay_cache.record_delivery_or_replay(
            db_session=db_session,
            provider=provider,
            hook_name=hook_name,
            delivery_id=delivery_id,
        )
        if outcome == replay_cache.ReplayOutcome.REPLAY_IGNORED:
            enqueue_event(
                db_session=db_session,
                event=EntityEvent(
                    topic=WebhookInEventTopics.REPLAY_IGNORED,
                    payload={
                        "provider": provider,
                        "hook_name": hook_name,
                        "delivery_id": delivery_id,
                        "request_id": correlation_id,
                    },
                    source_event_id=new_uuid(),
                ),
            )
            db_session.commit()
            rtnval = WebhookDispatchResult(
                status="replay_ignored",
                request_id=correlation_id,
                provider=provider,
                hook_name=hook_name,
                delivery_id=delivery_id,
                domain_event_count=0,
                rejection=None,
                matched_signature_header=verdict.matched_header,
            )
            return rtnval

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookInEventTopics.VERIFIED,
            payload={
                "provider": provider,
                "hook_name": hook_name,
                "request_id": correlation_id,
                "delivery_id": delivery_id,
                "matched_header": verdict.matched_header,
            },
            source_event_id=new_uuid(),
        ),
    )

    parse_result = _safe_parse(
        parser=parser_cls,
        raw_bytes=raw_bytes,
        headers=headers,
    )
    if isinstance(parse_result, StructuredRejection):
        rtnval = _emit_rejection(
            db_session=db_session,
            rejection=parse_result,
            provider=provider,
            hook_name=hook_name,
            request_id=correlation_id,
            delivery_id=delivery_id,
            matched_header=verdict.matched_header,
        )
        return rtnval

    count = normalization.publish_domain_events(
        db_session=db_session,
        parsed=parse_result,
        webhook_id=str(config.webhook_id),
        request_id=correlation_id,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookInEventTopics.DISPATCHED,
            payload={
                "provider": provider,
                "hook_name": hook_name,
                "request_id": correlation_id,
                "delivery_id": delivery_id,
                "domain_event_count": count,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = WebhookDispatchResult(
        status="dispatched",
        request_id=correlation_id,
        provider=provider,
        hook_name=hook_name,
        delivery_id=delivery_id,
        domain_event_count=count,
        rejection=None,
        matched_signature_header=verdict.matched_header,
    )
    return rtnval


def _safe_parse(
        *,
        parser: Type[InboundWebhookParserProtocol],
        raw_bytes: bytes,
        headers: Mapping[str, str]
    ):
    """
        Invoke the parser inside a catch-and-reclassify
        boundary. ``SemanticError`` is the only escape — it
        marks an actual contract violation by the parser and
        must bubble.
    """
    try:
        result = parser.parse(raw_bytes=raw_bytes, headers=headers)
    except SemanticError:
        raise
    except Exception as parse_err:
        rtnval = StructuredRejection(
            reason="parser_crashed",
            detail="{}: {}".format(type(parse_err).__name__, parse_err),
            recoverable=True,
            status_code=400,
        )
        return rtnval
    if not isinstance(result, (ParsedWebhook, StructuredRejection)):
        err_lines = ["Parser returned an unexpected type."]
        err_lines.append("PARSER: {}".format(parser.__qualname__))
        err_lines.append("RETURNED: {}".format(type(result).__name__))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None
    rtnval = result
    return rtnval


def _resolve_parser(
        *, provider: str
    ) -> Optional[Type[InboundWebhookParserProtocol]]:
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


def _resolve_configuration(
        *,
        db_session: DbSession,
        provider: str,
        hook_name: str
    ) -> Optional[WebhookConfiguration]:
    rows = repository.list_active_configurations_for_provider(
        db_session=db_session,
        provider=provider,
        hook_name=hook_name,
    )
    if rows is None or len(rows) == 0:
        return None
    rtnval = rows[0]
    return rtnval


def _read_delivery_id(
        *,
        parser: Type[InboundWebhookParserProtocol],
        headers: Mapping[str, str]
    ) -> Optional[str]:
    header_name = parser.delivery_id_header()
    if header_name is None or len(header_name) == 0:
        return None
    target = header_name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def _emit_rejection(
        *,
        db_session: DbSession,
        rejection: StructuredRejection,
        provider: str,
        hook_name: str,
        request_id: str,
        delivery_id: Optional[str],
        matched_header: Optional[str]
    ) -> WebhookDispatchResult:
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=WebhookInEventTopics.FAILED,
            payload={
                "provider": provider,
                "hook_name": hook_name,
                "request_id": request_id,
                "delivery_id": delivery_id,
                "reason": rejection.reason,
                "detail": rejection.detail,
                "recoverable": rejection.recoverable,
                "status_code": rejection.status_code,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = WebhookDispatchResult(
        status="rejected",
        request_id=request_id,
        provider=provider,
        hook_name=hook_name,
        delivery_id=delivery_id,
        domain_event_count=0,
        rejection=rejection,
        matched_signature_header=matched_header,
    )
    return rtnval
