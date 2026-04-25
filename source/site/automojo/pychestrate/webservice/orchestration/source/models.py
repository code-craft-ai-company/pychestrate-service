"""
.. module:: orchestration.source.models
    :synopsis: SQLAlchemy models for SCM integrations.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ScmProjectConfig(PychestratePhase1Base, SerializableModel):
    """
        Per-project SCM configuration row. ``provider_name``
        resolves to a registered :class:`ScmProviderProtocol`
        implementation; ``repo_key`` is the provider-specific
        identifier (e.g. ``owner/repo`` for GitHub).
    """

    __tablename__ = "orch_scm_project_config"

    project_id = Column(UUIDType(binary=False), primary_key=True)
    provider_name = Column(String(64), nullable=False, default="")
    repo_key = Column(String(256), nullable=False, default="")
    pipeline_file_path = Column(
        String(256),
        nullable=False,
        default=".pychestrate/pipeline.yaml",
    )
    use_polling = Column(Boolean, nullable=False, default=False)
    polling_ref_glob = Column(String(128), nullable=False, default="")
    last_poll_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class ScmWebhookDelivery(PychestratePhase1Base, SerializableModel):
    """
        Inbound webhook delivery dedup record. The composite PK
        ``(project_id, delivery_id)`` is the dedup key — a
        second arrival with the same pair is suppressed.
    """

    __tablename__ = "orch_scm_webhook_delivery"

    project_id = Column(UUIDType(binary=False), nullable=False)
    delivery_id = Column(String(128), nullable=False)
    provider_name = Column(String(64), nullable=False, default="")
    event_kind = Column(String(64), nullable=False, default="")
    received_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id", "delivery_id",
            name="pk_orch_scm_webhook_delivery",
        ),
        Index(
            "ix_orch_scm_webhook_delivery_received",
            "project_id", "received_at",
        ),
    )


class ScmLastSeenHead(PychestratePhase1Base, SerializableModel):
    """
        Last commit SHA observed on a given ref. Used by the M2
        polling worker; M1 only writes through
        :func:`record_last_seen_head` when an event lands.
    """

    __tablename__ = "orch_scm_last_seen_head"

    project_id = Column(UUIDType(binary=False), nullable=False)
    ref = Column(String(256), nullable=False)
    commit_sha = Column(String(64), nullable=False, default="")
    observed_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id", "ref",
            name="pk_orch_scm_last_seen_head",
        ),
    )
