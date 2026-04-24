"""
.. module:: jobs.envelope.repository
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: JobEnvelopeRepository — persistence of signed envelopes.

.. moduleauthor:: Automation Mojo LLC

One row per emitted envelope lands in ``jobs_envelope_archive`` so
reconciliation can re-verify the exact signed payload without
reconstructing it. The repository is intentionally thin — it does not
emit events, apply RBAC, or coordinate with the outbox. Callers (the
dispatcher in B1c) own those concerns.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.jobs.envelope.codec import SignedJobEnvelope
from automojo.pychestrate.webservice.jobs.envelope.errors import (
    JobEnvelopeError,
)
from automojo.pychestrate.webservice.jobs.envelope.models import (
    JobEnvelopeRecord,
)


def persist_signed_envelope(
        *,
        db_session: DbSession,
        signed: SignedJobEnvelope
    ) -> JobEnvelopeRecord:
    """
        Insert a row into ``jobs_envelope_archive`` capturing the
        full signed payload, signature, and key id. Flushes but
        does not commit — the caller's transaction decides when.

        :param db_session: Active SQLAlchemy session.
        :param signed: The signed envelope.

        :returns: The persisted :class:`JobEnvelopeRecord`.
    """
    envelope = signed.envelope
    row = JobEnvelopeRecord(
        envelope_id=envelope.envelope_id,
        schema_version=envelope.schema_version,
        project_id=envelope.project_id,
        run_id=envelope.run_id,
        job_id=envelope.job_id,
        job_type=envelope.job_type,
        client_id=envelope.client_id,
        pod_id=envelope.pod_id,
        issued_at=envelope.issued_at,
        hard_deadline_at=envelope.deadline.hard_deadline_at,
        key_id=signed.key_id,
        canonical_payload=signed.canonical_payload,
        signature=signed.signature,
        canonical_payload_text=signed.canonical_payload.decode("utf-8"),
    )
    db_session.add(row)
    db_session.flush()
    return row


def get_envelope(
        *,
        db_session: DbSession,
        envelope_id: str
    ) -> Optional[JobEnvelopeRecord]:
    """
        Look up an archived envelope by its ``envelope_id``.

        :param db_session: Active SQLAlchemy session.
        :param envelope_id: UUID hex string assigned at build time.

        :returns: The record, or ``None`` when not found.
    """
    rtnval = (
        db_session.query(JobEnvelopeRecord)
        .filter(JobEnvelopeRecord.envelope_id == envelope_id)
        .first()
    )
    return rtnval


def list_envelopes_for_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[JobEnvelopeRecord]:
    """
        Return every envelope issued for ``run_id`` ordered by
        ``issued_at``. A run may accumulate multiple envelope rows
        if the dispatcher re-issues after an ack timeout (not in M1,
        but the schema supports it).

        :param db_session: Active SQLAlchemy session.
        :param run_id: Target run UUID.

        :returns: List of records (possibly empty).
    """
    rows = (
        db_session.query(JobEnvelopeRecord)
        .filter(JobEnvelopeRecord.run_id == run_id)
        .order_by(JobEnvelopeRecord.issued_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
