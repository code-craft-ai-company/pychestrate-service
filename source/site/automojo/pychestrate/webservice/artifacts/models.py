"""
.. module:: artifacts.models
    :synopsis: Persistence rows for the artifact store.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ArtifactBlob(PychestratePhase1Base, SerializableModel):
    """
        Content-addressed blob row. ``cas_digest`` is the natural
        key — re-uploads of the same content increment
        ``reference_count`` rather than create a duplicate.
    """

    __tablename__ = "artifacts_artifact_blob"

    cas_digest = Column(String(64), primary_key=True)
    cas_key = Column(String(512), nullable=False, default="")
    backend_driver = Column(String(64), nullable=False, default="")
    size_bytes = Column(BigInteger, nullable=False, default=0)
    content_type = Column(String(128), nullable=True)
    reference_count = Column(Integer, nullable=False, default=0)
    tier = Column(String(16), nullable=False, default="hot")
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_referenced_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class RunArtifactReference(PychestratePhase1Base, SerializableModel):
    """
        One reference of a CAS blob from a run + label.
    """

    __tablename__ = "artifacts_run_artifact_reference"

    reference_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    label = Column(String(256), nullable=False, default="")
    artifact_type = Column(String(64), nullable=False, default="generic")
    cas_digest = Column(String(64), nullable=False)
    registered_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "label",
            name="uq_artifacts_run_reference_run_label",
        ),
        Index("ix_artifacts_run_reference_run", "run_id"),
        Index("ix_artifacts_run_reference_digest", "cas_digest"),
    )


class ArtifactTypeMetadata(PychestratePhase1Base, SerializableModel):
    """
        Per-type metadata declared by extension packs.
        ``ArtifactTypeExtension`` ships in M2; M1 keeps the row
        type but does not yet read from a registry.
    """

    __tablename__ = "artifacts_artifact_type_metadata"

    artifact_type = Column(String(64), primary_key=True)
    description = Column(String(512), nullable=False, default="")
    schema_json = Column(JSON, nullable=False, default=dict)


class ArtifactRetentionPlan(PychestratePhase1Base, SerializableModel):
    """
        One row per active retention plan applied to a blob.
        Promotion strategies write rows here; retention rolls
        them up to apply (M2).
    """

    __tablename__ = "artifacts_artifact_retention_plan"

    plan_id = Column(UUIDType(binary=False), primary_key=True)
    cas_digest = Column(String(64), nullable=False)
    target_tier = Column(String(16), nullable=False, default="cold")
    apply_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(String(512), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_artifacts_retention_plan_digest", "cas_digest"),
    )
