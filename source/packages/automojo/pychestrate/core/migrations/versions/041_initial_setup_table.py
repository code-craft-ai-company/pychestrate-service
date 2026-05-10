"""
Create the system_initial_setup table that backs the Jenkins-style
first-run setup wizard.

Revision ID: 041_initial_setup_table
Revises: 040_phase10_release_channels_agent_upgrade
Create Date: 2026-05-09

The webservice ships with no admin user. On first boot, the runtime
records a single ``system_initial_setup`` row carrying:

* a sha256 hash of an on-disk initial-admin token (cleartext written
  to ``${PYCHESTRATE_RUNTIME_DIR}/initial-admin-token`` mode 0600),
* the path the token was written to,
* timestamps for creation and completion,
* the user_id of whoever finishes setup (for the audit trail).

While ``completed_at IS NULL`` the setup-gate middleware redirects
every non-setup request to ``/setup/unlock``. After admin creation,
``completed_at`` is stamped and the gate becomes a no-op forever
(one-way; resetting requires direct DB intervention).

The table is intentionally singleton-by-construction via the
``singleton_key`` column + UNIQUE constraint. The application-side
manager refuses to insert a second row, but the constraint is the
real backstop on Postgres + SQLite alike.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "041_initial_setup_table"
down_revision = "040_phase10_release_channels_agent_upgrade"
branch_labels = None
depends_on = None


# Stable name for the singleton-key constraint so migrations on
# Postgres can address it explicitly. Both upgrade and downgrade
# refer to this constant.
SINGLETON_CONSTRAINT_NAME = "uq_system_initial_setup_singleton"


# Stable singleton-key value the application writes when it
# inserts the one-and-only setup row. The UNIQUE constraint on
# ``singleton_key`` plus this fixed value guarantees at most one
# row exists.
SINGLETON_KEY_VALUE = "INITIAL"


def upgrade():
    """
        Create the ``system_initial_setup`` table.

        :returns: None.
    """
    op.create_table(
        "system_initial_setup",
        sa.Column(
            "setup_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "singleton_key",
            sa.VARCHAR(16),
            nullable=False,
            server_default=SINGLETON_KEY_VALUE,
        ),
        sa.Column(
            "token_hash",
            sa.LargeBinary(32),
            nullable=False,
        ),
        sa.Column(
            "token_path",
            sa.VARCHAR(1024),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("setup_id"),
        sa.UniqueConstraint(
            "singleton_key",
            name=SINGLETON_CONSTRAINT_NAME,
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"],
            ["identity_users.user_id"],
            ondelete="SET NULL",
        ),
    )
    return


def downgrade():
    """
        Drop the ``system_initial_setup`` table.

        :returns: None.
    """
    op.drop_table("system_initial_setup")
    return
