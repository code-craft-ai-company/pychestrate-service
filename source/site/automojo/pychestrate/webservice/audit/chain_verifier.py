"""
.. module:: audit.chain_verifier
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Chain verification for audit_records.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.audit.audit_writer import GENESIS_HASH
from automojo.pychestrate.webservice.audit.models import AuditRecord


@dataclass(frozen=True)
class ChainVerificationResult:
    """
        Outcome of a chain verification run.

        :param ok: True when every record matches recomputed hashes.
        :param first_break: First sequence number whose hash mismatched.
        :param records_checked: Total records inspected.
    """
    ok: bool
    first_break: Optional[int]
    records_checked: int


def _canonical_json_bytes(payload: dict) -> bytes:
    rtnval = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return rtnval


def verify_audit_chain(
        *,
        db_session: DbSession,
        from_sequence: int,
        to_sequence: int
    ) -> ChainVerificationResult:
    """
        Recompute the hash chain for a sequence span and return whether it
        matches the stored hashes.

        :param db_session: Active SQLAlchemy session.
        :param from_sequence: Start sequence (inclusive).
        :param to_sequence: End sequence (inclusive).

        :returns: The :class:`ChainVerificationResult`.
    """
    rows = (
        db_session.query(AuditRecord)
        .filter(AuditRecord.sequence_number >= from_sequence)
        .filter(AuditRecord.sequence_number <= to_sequence)
        .order_by(AuditRecord.sequence_number.asc())
        .all()
    )

    checked = 0
    if from_sequence <= 1:
        previous_hash = GENESIS_HASH
    else:
        earlier = (
            db_session.query(AuditRecord)
            .filter(AuditRecord.sequence_number == from_sequence - 1)
            .first()
        )
        if earlier is None:
            rtnval = ChainVerificationResult(ok=False, first_break=from_sequence, records_checked=0)
            return rtnval
        previous_hash = bytes(earlier.record_hash)

    for row in rows:
        payload_bytes = _canonical_json_bytes(row.payload_json)
        payload_hash = hashlib.sha256(payload_bytes).digest()
        recomputed = hashlib.sha256(previous_hash + payload_hash).digest()

        stored_payload_hash = bytes(row.payload_hash)
        stored_record_hash = bytes(row.record_hash)
        stored_previous_hash = bytes(row.previous_hash)

        if stored_payload_hash != payload_hash:
            rtnval = ChainVerificationResult(
                ok=False, first_break=row.sequence_number, records_checked=checked + 1
            )
            return rtnval
        if stored_previous_hash != previous_hash:
            rtnval = ChainVerificationResult(
                ok=False, first_break=row.sequence_number, records_checked=checked + 1
            )
            return rtnval
        if stored_record_hash != recomputed:
            rtnval = ChainVerificationResult(
                ok=False, first_break=row.sequence_number, records_checked=checked + 1
            )
            return rtnval

        previous_hash = stored_record_hash
        checked = checked + 1

    rtnval = ChainVerificationResult(ok=True, first_break=None, records_checked=checked)
    return rtnval
