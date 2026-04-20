"""
.. module:: audit.audit_writer
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Canonical audit record writer with SHA-256 hash chain.

.. moduleauthor:: Automation Mojo LLC

Implements :func:`capture_event` per the 1-audit-log design. The M1
skeleton covers the INSERT-only write, canonical JSON hashing, and
publication of ``entity.audit.emitted`` — enough for downstream services
to subscribe and fan-out to land in M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json
import os

from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.audit.events import AuditEventTopics
from automojo.pychestrate.webservice.audit.exceptions import UnknownAuditKindError
from automojo.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension
from automojo.pychestrate.webservice.audit.models import AuditRecord
from automojo.pychestrate.webservice.extensions.registry import list_resource_extensions
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


GENESIS_HASH: bytes = bytes(32)


def _canonical_json_bytes(payload: dict) -> bytes:
    """
        Return bytes of the canonical JSON serialization of a payload.

        :param payload: The dict to serialize.

        :returns: Canonical JSON bytes.
    """
    rtnval = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return rtnval


def _known_kinds() -> set:
    """
        Return the set of kinds contributed by registered event-type packs.

        :returns: Set of kind strings.
    """
    packs = list_resource_extensions(base_class=AuditEventTypeExtension)
    rtnval = set()
    for pack in packs:
        rtnval.add(pack.kind)
    return rtnval


def capture_event(
        *,
        db_session: DbSession,
        source_event_id: str,
        source_topic: str,
        kind: str,
        actor_user_id: Optional[str],
        actor_service_identity: Optional[str],
        target_ref: Optional[str],
        payload: dict
    ) -> AuditRecord:
    """
        Persist one audit record inside the supplied session, compute the
        hash chain, and stage ``entity.audit.emitted``. Not committed by
        this function — the caller controls the transaction boundary so
        the audit write and the entity write land atomically.

        :param db_session: Active SQLAlchemy session.
        :param source_event_id: De-dup key across bus retries.
        :param source_topic: Originating bus topic.
        :param kind: Registered audit kind.
        :param actor_user_id: Acting principal, if any.
        :param actor_service_identity: Acting service identity, if any.
        :param target_ref: Canonical ref of affected entity.
        :param payload: Structured payload.

        :returns: The persisted :class:`AuditRecord`.
        :raises: UnknownAuditKindError
    """
    known = _known_kinds()
    if kind not in known:
        err_msg_lines = ["Cannot capture audit — kind is not registered."]
        err_msg_lines.append("KIND: {}".format(kind))
        err_msg_lines.append("SOURCE_TOPIC: {}".format(source_topic))
        err_msg_lines.append("KNOWN_COUNT: {}".format(len(known)))
        err_msg = os.linesep.join(err_msg_lines)
        raise UnknownAuditKindError(err_msg) from None

    previous = (
        db_session.query(AuditRecord)
        .order_by(AuditRecord.sequence_number.desc())
        .limit(1)
        .first()
    )
    if previous is None:
        previous_hash = GENESIS_HASH
    else:
        previous_hash = bytes(previous.record_hash)

    payload_bytes = _canonical_json_bytes(payload)
    payload_hash = hashlib.sha256(payload_bytes).digest()
    record_hash = hashlib.sha256(previous_hash + payload_hash).digest()

    record = AuditRecord(
        record_id=new_uuid(),
        kind=kind,
        source_topic=source_topic,
        source_event_id=source_event_id,
        actor_user_id=actor_user_id,
        actor_service_identity=actor_service_identity,
        target_ref=target_ref,
        payload_json=payload,
        payload_hash=payload_hash,
        previous_hash=previous_hash,
        record_hash=record_hash,
        written_at=utc_now(),
    )
    db_session.add(record)
    db_session.flush()

    event_payload = {
        "sequence_number": record.sequence_number,
        "kind": record.kind,
        "source_topic": record.source_topic,
        "record_hash_hex": record_hash.hex(),
        "written_at": record.written_at.isoformat(),
    }
    event = EntityEvent(
        topic=AuditEventTopics.AUDIT_EMITTED,
        payload=event_payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)

    rtnval = record
    return rtnval
