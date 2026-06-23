"""
.. module:: extensions.sandbox.models
    :synopsis: SQLAlchemy model for extension capability grants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class ExtensionCapabilityGrant(PychestratePhase1Base, SerializableModel):
    """
        One per-(ext_name, capability) grant ledger row. The
        ``revoked_at`` column being non-NULL marks the grant
        revoked; the row stays in place so the audit trail
        survives.
    """

    __tablename__ = "extensions_capability_grant"

    ext_name = Column(String(128), nullable=False)
    capability = Column(String(64), nullable=False)
    source = Column(String(16), nullable=False, default="manifest")
    granted_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    granted_by = Column(UUIDType(binary=False), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(UUIDType(binary=False), nullable=True)
    revoked_reason = Column(Text, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint(
            "ext_name", "capability",
            name="pk_extensions_capability_grant",
        ),
        Index(
            "ix_extensions_capability_grant_ext_revoked",
            "ext_name", "revoked_at",
        ),
    )
