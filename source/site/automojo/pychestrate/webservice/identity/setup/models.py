"""
.. module:: identity.setup.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy model for the initial-setup singleton row.

.. moduleauthor:: Automation Mojo LLC

The ``system_initial_setup`` table is a singleton-by-construction.
The ``singleton_key`` column is constrained UNIQUE and the
application always inserts the literal value
:data:`SINGLETON_KEY_VALUE`, so at most one row can ever exist.

While ``completed_at IS NULL`` the setup-gate middleware is active.
After admin creation the manager stamps ``completed_at`` and the
gate becomes a no-op forever (one-way; resetting requires direct
DB intervention).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


# Stable singleton-key value the application writes when it inserts
# the one-and-only setup row. The UNIQUE constraint on
# ``singleton_key`` plus this fixed value guarantees at most one row
# exists. The constant is duplicated in alembic migration 041 (the
# migration cannot import application code) -- keep them in sync.
SINGLETON_KEY_VALUE: str = "INITIAL"


# Stable name for the singleton-key UNIQUE constraint. Mirrors the
# constant in alembic migration 041.
SINGLETON_CONSTRAINT_NAME: str = "uq_system_initial_setup_singleton"


# Length of the on-disk token in raw bytes BEFORE base64 encoding.
# The hash column is sha256 (32 bytes) regardless of token length.
INITIAL_TOKEN_BYTE_LENGTH: int = 32


class InitialSetup(PychestratePhase1Base, SerializableModel):
    """
        Singleton row tracking the first-run setup wizard's lifecycle.

        :ivar setup_id: UUID primary key.
        :ivar singleton_key: Always
                             :data:`SINGLETON_KEY_VALUE`; UNIQUE
                             constraint enforces a single row.
        :ivar token_hash: sha256 of the cleartext token written to
                          disk on first boot. 32 bytes.
        :ivar token_path: Filesystem path the cleartext token was
                          written to. Recorded for diagnostics and
                          for the deletion step on completion.
        :ivar created_at: First-boot timestamp.
        :ivar completed_at: When the operator finished the wizard.
                            ``None`` while setup is pending.
        :ivar completed_by_user_id: ``identity_users.user_id`` of the
                                    administrator created by the
                                    wizard. ``None`` while pending.
    """

    __tablename__ = "system_initial_setup"

    setup_id = Column(UUIDType(binary=False), primary_key=True)
    singleton_key = Column(
        String(16),
        nullable=False,
        default=SINGLETON_KEY_VALUE,
    )
    token_hash = Column(LargeBinary(32), nullable=False)
    token_path = Column(String(1024), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_by_user_id = Column(
        UUIDType(binary=False),
        ForeignKey("identity_users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "singleton_key",
            name=SINGLETON_CONSTRAINT_NAME,
        ),
    )


__all__ = [
    "INITIAL_TOKEN_BYTE_LENGTH",
    "SINGLETON_CONSTRAINT_NAME",
    "SINGLETON_KEY_VALUE",
    "InitialSetup",
]
