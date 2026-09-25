"""
.. module:: hardening.idempotency
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 48-hour Idempotency-Key dedup table.

.. moduleauthor:: Code Craft AI LLC

A thin wrapper over :class:`IdempotencyRecord` rows. The service layer
records a ``(scope, key) → result`` mapping the first time a client
sends an ``Idempotency-Key`` header. Subsequent requests with the same
key return the stored result without re-running the business logic.
Rows older than ``IDEMPOTENCY_TTL_SECONDS`` are discarded.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import new_uuid, utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


IDEMPOTENCY_TTL_SECONDS: int = 48 * 60 * 60


_JsonPayload = JSON().with_variant(JSONB(), "postgresql")


class IdempotencyRecord(PychestratePhase1Base, SerializableModel):
    """
        Dedup row. ``scope`` disambiguates keys across operations so the
        same ``Idempotency-Key`` value may be reused for, e.g.,
        ``project.create`` and ``retention.policy.create``.
    """

    __tablename__ = "hardening_idempotency_records"

    record_id = Column(UUIDType(binary=False), primary_key=True)
    scope = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    recorded_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    response_payload = Column(_JsonPayload, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_hardening_idempotency_scope_key", "scope", "idempotency_key", unique=True),
    )


def lookup(
        *,
        db_session: DbSession,
        scope: str,
        idempotency_key: str
    ) -> Optional[Mapping[str, Any]]:
    """
        Return the cached response payload for a given key, or None.

        Rows older than :data:`IDEMPOTENCY_TTL_SECONDS` are treated as
        expired and return None.

        :returns: Cached payload or None.
    """
    if idempotency_key is None or len(idempotency_key.strip()) == 0:
        return None

    row = (
        db_session.query(IdempotencyRecord)
        .filter(IdempotencyRecord.scope == scope)
        .filter(IdempotencyRecord.idempotency_key == idempotency_key)
        .first()
    )
    if row is None:
        return None

    recorded = row.recorded_at
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - recorded > timedelta(seconds=IDEMPOTENCY_TTL_SECONDS):
        return None

    rtnval = row.response_payload if row.response_payload is not None else {}
    return rtnval


def record(
        *,
        db_session: DbSession,
        scope: str,
        idempotency_key: str,
        response_payload: Mapping[str, Any]
    ) -> None:
    """
        Record a response for later dedup.

        No-op when ``idempotency_key`` is empty.
    """
    if idempotency_key is None or len(idempotency_key.strip()) == 0:
        return

    existing = (
        db_session.query(IdempotencyRecord)
        .filter(IdempotencyRecord.scope == scope)
        .filter(IdempotencyRecord.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        existing.response_payload = dict(response_payload) if response_payload is not None else {}
        existing.recorded_at = utc_now()
        db_session.add(existing)
        db_session.flush()
        return

    row = IdempotencyRecord(
        record_id=new_uuid(),
        scope=scope,
        idempotency_key=idempotency_key,
        recorded_at=utc_now(),
        response_payload=dict(response_payload) if response_payload is not None else {},
    )
    db_session.add(row)
    db_session.flush()
    return
