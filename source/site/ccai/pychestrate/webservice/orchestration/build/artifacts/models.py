"""
.. module:: orchestration.build.artifacts.models
    :synopsis: SQLAlchemy models + enum for build-artifacts.
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
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class PromotionAction(str, enum.Enum):
    """
        Promotion-ledger actions.
    """
    PROMOTE = "promote"
    ROLLBACK = "rollback"


PROMOTION_ACTION_ENUM = "orch_build_artifact_promotion_action"


class BuildArtifactManifest(PychestratePhase1Base, SerializableModel):
    """
        One synthesized manifest per (build_run_id) — the
        manifest is the authoritative listing of artifacts a
        build produced.
    """

    __tablename__ = "orch_build_artifact_manifest"

    manifest_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    build_run_id = Column(UUIDType(binary=False), nullable=False)
    entry_count = Column(Integer, nullable=False, default=0)
    note = Column(Text, nullable=False, default="")
    synthesized_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "build_run_id",
            name="uq_orch_build_artifact_manifest_build_run",
        ),
        Index(
            "ix_orch_build_artifact_manifest_project",
            "project_id",
        ),
    )


class BuildArtifactEntryIndex(PychestratePhase1Base, SerializableModel):
    """
        One row per entry in a manifest. Composite PK
        ``(manifest_id, artifact_id)`` so manifests with
        multiple entries dedupe on insert.
    """

    __tablename__ = "orch_build_artifact_entry_index"

    manifest_id = Column(
        UUIDType(binary=False),
        ForeignKey(
            "orch_build_artifact_manifest.manifest_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    artifact_id = Column(String(128), nullable=False)
    artifact_type = Column(String(64), nullable=False, default="")
    artifact_name = Column(String(256), nullable=False, default="")
    storage_uri = Column(Text, nullable=False, default="")
    sha256 = Column(String(64), nullable=False, default="")
    payload = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        PrimaryKeyConstraint(
            "manifest_id", "artifact_id",
            name="pk_orch_build_artifact_entry_index",
        ),
        Index(
            "ix_orch_build_artifact_entry_index_artifact",
            "artifact_id", "artifact_type",
        ),
    )


class BuildArtifactPromotionLedger(PychestratePhase1Base, SerializableModel):
    """
        Append-only promotion-history ledger.
    """

    __tablename__ = "orch_build_artifact_promotion_ledger"

    ledger_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    manifest_id = Column(UUIDType(binary=False), nullable=False)
    artifact_id = Column(String(128), nullable=False, default="")
    channel = Column(String(64), nullable=False, default="")
    action = Column(
        Enum(PromotionAction, name=PROMOTION_ACTION_ENUM),
        nullable=False,
    )
    actor_id = Column(UUIDType(binary=False), nullable=True)
    note = Column(Text, nullable=False, default="")
    at_ts = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_orch_build_artifact_promotion_ledger_artifact",
            "artifact_id", "channel",
        ),
    )


class ChannelHead(PychestratePhase1Base, SerializableModel):
    """
        Per-(project, channel, artifact_id) head pointer to the
        latest manifest that owns the channel-promoted entry.
    """

    __tablename__ = "orch_build_artifact_channel_head"

    project_id = Column(UUIDType(binary=False), nullable=False)
    channel = Column(String(64), nullable=False)
    artifact_id = Column(String(128), nullable=False)
    manifest_id = Column(UUIDType(binary=False), nullable=False)
    promoted_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id", "channel", "artifact_id",
            name="pk_orch_build_artifact_channel_head",
        ),
    )
