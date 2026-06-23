"""
.. module:: identity.flags.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy models for the 1-feature-flags feature.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from dataclasses import dataclass, field
from typing import Optional, Tuple

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class FlagKind(enum.Enum):
    """
        Typing of a feature flag.
    """
    BOOLEAN = "BOOLEAN"
    STRING = "STRING"
    ENUM = "ENUM"
    PERCENTAGE = "PERCENTAGE"


class FlagState(enum.Enum):
    """
        Lifecycle state of a feature flag.
    """
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class FlagContext:
    """
        Evaluation context for :func:`evaluate_flag`.

        :param bucketing_key: Stable string used for hash-based rollout.
        :param user_id: Acting user id, if any.
        :param project_id: Project id, if any.
        :param attributes: Tuple of (key, value) attribute pairs.
    """
    bucketing_key: str
    user_id: Optional[str]
    project_id: Optional[str]
    attributes: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)


class FeatureFlag(PychestratePhase1Base, SerializableModel):
    """
        Current view of each flag.
    """

    __tablename__ = "feature_flags"

    flag_key = Column(String(256), primary_key=True)
    flag_kind = Column(Enum(FlagKind, name="feature_flag_kind"), nullable=False)
    current_version = Column(Integer, nullable=False, default=1)
    state = Column(Enum(FlagState, name="feature_flag_state"), nullable=False, default=FlagState.ACTIVE)
    retired_at = Column(DateTime(timezone=True), nullable=True)
    grace_expires_at = Column(DateTime(timezone=True), nullable=True)
    owner_user_id = Column(UUIDType(binary=False), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class FeatureFlagVersion(PychestratePhase1Base, SerializableModel):
    """
        Immutable version history per flag.
    """

    __tablename__ = "feature_flag_versions"

    version_id = Column(UUIDType(binary=False), primary_key=True)
    flag_key = Column(
        String(256),
        ForeignKey("feature_flags.flag_key", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    default_value = Column(JSON, nullable=False)
    rules_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(UUIDType(binary=False), nullable=True)

    __table_args__ = (
        UniqueConstraint("flag_key", "version", name="uq_feature_flag_versions_flag_version"),
        Index("ix_feature_flag_versions_flag", "flag_key"),
    )
