"""
.. module:: jobs.envelope.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy model for persisted JobEnvelope archive rows.

.. moduleauthor:: Automation Mojo LLC

The :class:`JobEnvelopeRecord` table keeps a one-row-per-dispatch
archive so the full signed payload can be re-verified during
reconciliation (``5-cancel-reconcile``) and during audit investigations
(``1-audit-log``). Retention is governed by ``2-retention-policies``
and is out of this feature's scope.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    Index,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class JobEnvelopeRecord(PychestratePhase1Base, SerializableModel):
    """
        Persisted envelope archive row. One row per emitted envelope.

        ``canonical_payload`` stores the exact bytes the signature was
        computed over so re-verification is possible without
        reconstructing the JCS form. ``signature`` stores the detached
        Ed25519 bytes; ``key_id`` resolves through the signer's JWKS
        to the public key that can verify.
    """

    __tablename__ = "jobs_envelope_archive"

    envelope_id = Column(UUIDType(binary=False), primary_key=True)
    schema_version = Column(String(32), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    run_id = Column(UUIDType(binary=False), nullable=False)
    job_id = Column(UUIDType(binary=False), nullable=False)
    job_type = Column(String(64), nullable=False, default="")
    client_id = Column(UUIDType(binary=False), nullable=False)
    pod_id = Column(UUIDType(binary=False), nullable=False)
    issued_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    hard_deadline_at = Column(DateTime(timezone=True), nullable=False)
    key_id = Column(String(128), nullable=False, default="")
    canonical_payload = Column(LargeBinary, nullable=False)
    signature = Column(LargeBinary, nullable=False)
    canonical_payload_text = Column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_jobs_envelope_archive_run_id", "run_id"),
        Index("ix_jobs_envelope_archive_project_id", "project_id"),
        Index("ix_jobs_envelope_archive_issued_at", "issued_at"),
    )
