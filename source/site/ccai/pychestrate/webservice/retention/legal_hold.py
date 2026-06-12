"""
.. module:: retention.legal_hold
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Legal-hold model + service for 2-retention-policies M3.

.. moduleauthor:: Code Craft AI LLC

A legal hold pins an entity out of retention: while the hold is present,
the evaluator skips every action that targets the entity. Holds are
manually applied and released; M3 adds them to stop runaway deletions
while compliance investigations run.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Optional

from sqlalchemy import Column, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Session as DbSession
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import new_uuid, utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class LegalHold(PychestratePhase1Base, SerializableModel):
    """
        A single (entity_kind, entity_id) legal hold row.
    """

    __tablename__ = "retention_legal_holds"

    hold_id = Column(UUIDType(binary=False), primary_key=True)
    entity_kind = Column(String(64), nullable=False)
    entity_id = Column(String(128), nullable=False)
    reason = Column(Text(), nullable=False, default="")
    created_by_user_id = Column(UUIDType(binary=False), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    released_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "entity_kind", "entity_id", name="uq_retention_legal_hold_entity",
        ),
        Index("ix_retention_legal_hold_entity", "entity_kind", "entity_id"),
    )


def place_hold(
        *,
        db_session: DbSession,
        entity_kind: str,
        entity_id: str,
        reason: str,
        actor_user_id: Optional[str]
    ) -> LegalHold:
    """
        Create or refresh a legal hold on a single entity.
    """
    existing = (
        db_session.query(LegalHold)
        .filter(LegalHold.entity_kind == entity_kind)
        .filter(LegalHold.entity_id == entity_id)
        .first()
    )
    if existing is not None:
        existing.released_at = None
        existing.reason = reason if reason is not None else existing.reason
        existing.created_by_user_id = actor_user_id
        db_session.add(existing)
        db_session.flush()
        db_session.commit()
        rtnval = existing
        return rtnval

    row = LegalHold(
        hold_id=new_uuid(),
        entity_kind=entity_kind,
        entity_id=entity_id,
        reason=reason if reason is not None else "",
        created_by_user_id=actor_user_id,
        created_at=utc_now(),
        released_at=None,
    )
    db_session.add(row)
    db_session.flush()
    db_session.commit()
    rtnval = row
    return rtnval


def release_hold(
        *,
        db_session: DbSession,
        entity_kind: str,
        entity_id: str
    ) -> None:
    """
        Release an active hold.
    """
    row = (
        db_session.query(LegalHold)
        .filter(LegalHold.entity_kind == entity_kind)
        .filter(LegalHold.entity_id == entity_id)
        .first()
    )
    if row is None:
        return
    row.released_at = utc_now()
    db_session.add(row)
    db_session.flush()
    db_session.commit()
    return


def is_held(
        *,
        db_session: DbSession,
        entity_kind: str,
        entity_id: str
    ) -> bool:
    """
        Return True iff there is an active (not-yet-released) hold on
        ``(entity_kind, entity_id)``.
    """
    row = (
        db_session.query(LegalHold)
        .filter(LegalHold.entity_kind == entity_kind)
        .filter(LegalHold.entity_id == entity_id)
        .first()
    )
    if row is None:
        return False
    rtnval = row.released_at is None
    return rtnval
