"""
.. module:: webhooks_in.models
    :synopsis: SQLAlchemy models + IO shapes for inbound webhooks.

M1 lands three persistence rows:

* :class:`WebhookConfiguration` — per ``(project, provider,
  hook_name)`` configuration.
* :class:`WebhookSeenDelivery` — replay-cache entry keyed on
  ``(provider, hook_name, delivery_id)``.
* :class:`WebhookDeadletter` — pointer-only row referencing
  the raw payload stashed in the object store; the M2
  controller populates it from the dispatcher's
  catch-and-reclassify boundary.

Plus the framework dataclasses :class:`ParsedWebhook`,
:class:`StructuredRejection`, :class:`NormalizedEvent`, and
:class:`SignatureHeaderSpec` that the parser protocol exchanges
across the dispatcher seam.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class SignatureAlgorithm(str, enum.Enum):
    """
        Hash algorithm used by an inbound parser's signature
        header. M1 ships HMAC-SHA-256 as the canonical strong
        algorithm; the GitHub-style weak SHA-1 algorithm is
        declared so verifications can reject when it is the
        sole signature offered.
    """
    HMAC_SHA256 = "hmac_sha256"
    HMAC_SHA1 = "hmac_sha1"
    OPAQUE_TOKEN = "opaque_token"


class SignatureEncoding(str, enum.Enum):
    """
        Encoding the parser expects when reading a header
        value. ``HEX_WITH_PREFIX`` matches the GitHub
        ``sha256=<hex>`` form; ``HEX`` matches a bare hex
        digest; ``RAW`` matches an opaque token where the
        string itself is the signature.
    """
    HEX_WITH_PREFIX = "hex_with_prefix"
    HEX = "hex"
    RAW = "raw"


@dataclass(frozen=True)
class SignatureHeaderSpec:
    """
        Parser-declared description of a signature header.

        :param header: Header name (case-insensitive on read).
        :param algorithm: Hash algorithm used to compute the
                          signature.
        :param encoding: How the header value encodes the
                         digest.
        :param prefix: Required prefix when
                       ``encoding=HEX_WITH_PREFIX`` (e.g.,
                       ``"sha256="``).
        :param weak: ``True`` when the algorithm is too weak to
                     stand on its own (GitHub's ``X-Hub-Signature``).
                     M1 verification rejects requests that
                     present only weak signatures.
    """
    header: str
    algorithm: SignatureAlgorithm
    encoding: SignatureEncoding
    prefix: str = ""
    weak: bool = False


@dataclass(frozen=True)
class NormalizedEvent:
    """
        One normalized domain event a parser emits per
        request. ``topic`` follows ``entity.<feature>.<verb>``
        and ``payload`` is an opaque mapping.

        :param topic: Dotted event-bus topic.
        :param payload: Event payload mapping; serialized as
                        JSON when published.
        :param source_event_id: Optional caller-supplied id
                                used by downstream dedup; the
                                dispatcher synthesizes one when
                                empty.
    """
    topic: str
    payload: Mapping[str, Any]
    source_event_id: Optional[str] = None


@dataclass(frozen=True)
class ParsedWebhook:
    """
        Parser success result returned to the dispatcher.

        :param provider: Parser factory name.
        :param hook_name: Per-project nickname.
        :param delivery_id: Provider-native delivery id (used
                            as the replay-cache key when
                            present).
        :param domain_events: One or more normalized events the
                              dispatcher will publish atomically.
    """
    provider: str
    hook_name: str
    delivery_id: Optional[str]
    domain_events: Tuple[NormalizedEvent, ...] = ()


@dataclass(frozen=True)
class StructuredRejection:
    """
        Parser-or-framework rejection result. The dispatcher
        reclassifies any uncaught parser exception into a
        :class:`StructuredRejection` to keep the inbound API
        free of 500s.

        :param reason: Stable token (``"signature_invalid"``,
                       ``"parser_crashed"``, etc.) used by
                       observability and the deadletter row.
        :param detail: Human-readable description; safe for
                       audit logs but not echoed to clients.
        :param recoverable: ``True`` when an operator could
                            replay the deadlettered payload
                            after fixing the parser.
        :param status_code: HTTP status the controller will
                            return; defaults to 400 for
                            payload-related failures.
    """
    reason: str
    detail: str
    recoverable: bool
    status_code: int = 400


class WebhookConfiguration(PychestratePhase1Base, SerializableModel):
    """
        Per-(project, provider, hook_name) inbound webhook
        configuration. M1 surfaces just enough of the row that
        the dispatcher pipeline can resolve the parser, the
        secret, and the mTLS gate. M2 widens the schema (rotate
        history, replay quotas).
    """

    __tablename__ = "webhooks_in_configurations"

    webhook_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    provider = Column(String(64), nullable=False)
    hook_name = Column(String(128), nullable=False)
    secret_ref = Column(Text, nullable=False, default="")
    mtls_required = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=False, default="")
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(UUIDType(binary=False), nullable=True)
    created_at = Column(
        UtcDateTime(timezone=True), nullable=False, default=utc_now,
    )
    disabled_at = Column(UtcDateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "provider", "hook_name",
            name="uq_webhooks_in_configurations_project_provider_name",
        ),
        Index(
            "ix_webhooks_in_configurations_provider_name",
            "provider", "hook_name",
        ),
    )


class WebhookSeenDelivery(PychestratePhase1Base, SerializableModel):
    """
        Replay-cache row. The composite primary key is
        ``(provider, hook_name, delivery_id)``; the M2
        background sweeper drops rows past ``expires_at``.
    """

    __tablename__ = "webhooks_in_seen_deliveries"

    provider = Column(String(64), primary_key=True)
    hook_name = Column(String(128), primary_key=True)
    delivery_id = Column(String(256), primary_key=True)
    first_seen_at = Column(
        UtcDateTime(timezone=True), nullable=False, default=utc_now,
    )
    expires_at = Column(UtcDateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ix_webhooks_in_seen_deliveries_expires_at",
            "expires_at",
        ),
    )


class WebhookDeadletter(PychestratePhase1Base, SerializableModel):
    """
        Pointer to a deadlettered raw payload in the object
        store. M1 lands the table so M2 can write rows into it
        without a follow-on migration.
    """

    __tablename__ = "webhooks_in_deadletter_index"

    request_id = Column(UUIDType(binary=False), primary_key=True)
    webhook_id = Column(UUIDType(binary=False), nullable=True)
    provider = Column(String(64), nullable=False)
    hook_name = Column(String(128), nullable=False)
    object_store_path = Column(Text, nullable=False)
    content_type = Column(String(128), nullable=False, default="")
    byte_size = Column(Integer, nullable=False, default=0)
    reason = Column(String(64), nullable=False)
    recoverable = Column(Boolean, nullable=False, default=True)
    stored_at = Column(
        UtcDateTime(timezone=True), nullable=False, default=utc_now,
    )
    expires_at = Column(UtcDateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ix_webhooks_in_deadletter_index_provider_name",
            "provider", "hook_name",
        ),
        Index(
            "ix_webhooks_in_deadletter_index_expires_at",
            "expires_at",
        ),
    )
