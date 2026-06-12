"""
.. module:: orchestration.test.catalog.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy model for ``test_catalog_entry``.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class TestCatalogEntry(PychestratePhase1Base, SerializableModel):
    """
        One row per registered test entry. Re-imports overwrite
        in place — the row's identity is
        ``(project_id, importer_tag, entry_key)``.
    """

    __tablename__ = "orchestration_test_catalog_entry"

    entry_id = Column(UUIDType(binary=False), primary_key=True)
    project_id = Column(UUIDType(binary=False), nullable=False)
    importer_tag = Column(String(64), nullable=False, default="")
    entry_key = Column(String(256), nullable=False, default="")
    display_name = Column(String(256), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    required_capability_tags = Column(JSON, nullable=False, default=list)
    param_schema = Column(JSON, nullable=False, default=dict)
    raw_metadata = Column(JSON, nullable=False, default=dict)
    canonical_digest = Column(String(64), nullable=False, default="")
    retired = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "importer_tag", "entry_key",
            name="uq_orchestration_test_catalog_entry_id_keys",
        ),
        Index(
            "ix_orchestration_test_catalog_entry_project",
            "project_id",
        ),
        Index(
            "ix_orchestration_test_catalog_entry_retired",
            "retired",
        ),
    )
