"""
.. module:: orchestration.test.triage.models
    :synopsis: SQLAlchemy models + enums for triage rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Index,
    String,
    Text,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class TriageClass(str, enum.Enum):
    """
        Output classification for a triage case.
    """
    KNOWN_ISSUE = "known_issue"
    NEW_BUG = "new_bug"
    INFRA_FLAKE = "infra_flake"
    OTHER = "other"


TRIAGE_CLASS_ENUM = "orch_triage_class"


class TriageCase(PychestratePhase1Base, SerializableModel):
    """
        Per-failure triage record. The ``stack_signature_sha256``
        column is what M2 uses to look up similar prior failures
        in the signature cache.
    """

    __tablename__ = "orch_triage_case"

    case_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    run_id = Column(UUIDType(binary=False), nullable=False)
    catalog_entry_id = Column(UUIDType(binary=False), nullable=False)
    test_case_identity_sha256 = Column(String(64), nullable=False)
    stack_signature_sha256 = Column(String(64), nullable=False, default="")
    classification = Column(
        Enum(TriageClass, name=TRIAGE_CLASS_ENUM),
        nullable=False,
        default=TriageClass.OTHER,
    )
    confidence = Column(Float, nullable=False, default=0.0)
    rationale = Column(Text, nullable=False, default="")
    classifier_name = Column(String(64), nullable=False, default="")
    tracker = Column(String(64), nullable=True)
    ticket_key = Column(String(128), nullable=True)
    ticket_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_orch_triage_case_run",
            "run_id",
        ),
        Index(
            "ix_orch_triage_case_project_class",
            "project_id", "classification",
        ),
        Index(
            "ix_orch_triage_case_signature",
            "stack_signature_sha256",
        ),
    )


class TriageCaseLedger(PychestratePhase1Base, SerializableModel):
    """
        Append-only audit trail for classification transitions.
    """

    __tablename__ = "orch_triage_case_ledger"

    ledger_id = Column(UUIDType(binary=False), primary_key=True)
    case_id = Column(UUIDType(binary=False), nullable=False)
    actor_id = Column(UUIDType(binary=False), nullable=True)
    from_class = Column(
        Enum(TriageClass, name=TRIAGE_CLASS_ENUM),
        nullable=True,
    )
    to_class = Column(
        Enum(TriageClass, name=TRIAGE_CLASS_ENUM),
        nullable=False,
    )
    rationale = Column(Text, nullable=False, default="")
    at_ts = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_orch_triage_case_ledger_case_at", "case_id", "at_ts"),
    )
