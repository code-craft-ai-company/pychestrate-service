"""
.. module:: orchestration.test.flake.models
    :synopsis: SQLAlchemy models + enums for flake-tracking.
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
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class Outcome(str, enum.Enum):
    """
        Per-test-case outcome from a single run.
    """
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"
    XFAIL = "xfail"
    XPASS = "xpass"


class FlakeClass(str, enum.Enum):
    """
        Output classification of a per-test history window.
    """
    STABLE = "stable"
    INTERMITTENT = "intermittent"
    FLAKY = "flaky"
    QUARANTINED = "quarantined"
    BROKEN = "broken"
    INSUFFICIENT_DATA = "insufficient_data"


class QuarantineAction(str, enum.Enum):
    """
        Action recorded in :class:`FlakeQuarantineLedger`.
    """
    QUARANTINE = "quarantine"
    CLEAR = "clear"


# NOTE: ``orch_test_outcome`` is also a TABLE name (see
# ``TestOutcome.__tablename__`` below). Postgres treats tables
# as implicit composite types in the same namespace, so the
# enum name has to be distinct from the table name. Suffixed
# with ``_value`` to match the ``outcome`` column it backs.
OUTCOME_ENUM = "orch_test_outcome_value"
FLAKE_CLASS_ENUM = "orch_flake_class"
QUARANTINE_ACTION_ENUM = "orch_flake_quarantine_action"


class TestOutcome(PychestratePhase1Base, SerializableModel):
    """
        One per-test outcome, ingested from a completed run. The
        ``(run_id, test_case_identity_sha256)`` UNIQUE makes
        re-ingest of the same run idempotent.
    """

    __tablename__ = "orch_test_outcome"

    outcome_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    catalog_entry_id = Column(UUIDType(binary=False), nullable=False)
    test_case_identity_sha256 = Column(String(64), nullable=False)
    run_id = Column(UUIDType(binary=False), nullable=False)
    runtime_env_digest = Column(String(64), nullable=False, default="")
    outcome = Column(
        Enum(Outcome, name=OUTCOME_ENUM),
        nullable=False,
        default=Outcome.PASS,
    )
    duration_ms = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "test_case_identity_sha256",
            name="uq_orch_test_outcome_run_identity",
        ),
        Index(
            "ix_orch_test_outcome_project_entry_started",
            "project_id", "catalog_entry_id", "started_at",
        ),
        Index(
            "ix_orch_test_outcome_identity_started",
            "test_case_identity_sha256", "started_at",
        ),
    )


class FlakeClassification(PychestratePhase1Base, SerializableModel):
    """
        Per-(test-case, runtime-env) classification. ``runtime_env_digest``
        is part of the composite PK; the empty string represents
        the "no env binding" classification.
    """

    __tablename__ = "orch_flake_classification"

    project_id = Column(UUIDType(binary=False), nullable=False)
    catalog_entry_id = Column(UUIDType(binary=False), nullable=False)
    test_case_identity_sha256 = Column(String(64), nullable=False)
    runtime_env_digest = Column(String(64), nullable=False, default="")
    classification = Column(
        Enum(FlakeClass, name=FLAKE_CLASS_ENUM),
        nullable=False,
        default=FlakeClass.INSUFFICIENT_DATA,
    )
    classifier_name = Column(String(64), nullable=False, default="")
    classifier_version = Column(String(32), nullable=False, default="")
    sample_count = Column(Integer, nullable=False, default=0)
    rationale_tag = Column(String(128), nullable=False, default="")
    last_computed_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id",
            "catalog_entry_id",
            "test_case_identity_sha256",
            "runtime_env_digest",
            name="pk_orch_flake_classification",
        ),
        Index(
            "ix_orch_flake_classification_entry_class",
            "catalog_entry_id", "classification",
        ),
    )


class FlakeQuarantineLedger(PychestratePhase1Base, SerializableModel):
    """
        Append-only ledger of manual quarantine actions. Each
        row records a quarantine or clear action plus the actor
        and reason.
    """

    __tablename__ = "orch_flake_quarantine_ledger"

    ledger_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    catalog_entry_id = Column(UUIDType(binary=False), nullable=False)
    test_case_identity_sha256 = Column(String(64), nullable=False)
    runtime_env_digest = Column(String(64), nullable=False, default="")
    action = Column(
        Enum(QuarantineAction, name=QUARANTINE_ACTION_ENUM),
        nullable=False,
    )
    actor_id = Column(UUIDType(binary=False), nullable=True)
    reason = Column(Text, nullable=False, default="")
    at_ts = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_orch_flake_quarantine_ledger_target_at",
            "test_case_identity_sha256", "at_ts",
        ),
    )
