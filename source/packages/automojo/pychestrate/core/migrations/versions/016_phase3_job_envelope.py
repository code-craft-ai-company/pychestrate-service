"""
Add Phase 3 / Layer-5 job-envelope archive table.

Revision ID: 016_phase3_job_envelope
Revises: 014_phase3_layer3_m2
Create Date: 2026-04-24

Adds:

- ``jobs_envelope_archive`` — one row per signed envelope emitted by
  :mod:`jobs.envelope`. Retains the exact canonical bytes and the
  detached Ed25519 signature so reconciliation can re-verify without
  reconstructing the JCS payload.

Chain note: this migration branches off ``014_phase3_layer3_m2``
(the current ``main`` head). The in-flight PR for
``3-client-enrollment`` M2 also branches off ``014`` as
``015_phase2_enrollment_m2``. Whichever of the two PRs merges second
needs a trivial chain-reconciliation commit to bump its
``down_revision`` onto the already-landed one; Alembic's
``merge-heads`` or a ``down_revision`` bump suffices.
"""

__author__ = "AutomationX"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "016_phase3_job_envelope"
down_revision = "014_phase3_layer3_m2"
branch_labels = None
depends_on = None


ENVELOPE_RUN_INDEX = "ix_jobs_envelope_archive_run_id"
ENVELOPE_PROJECT_INDEX = "ix_jobs_envelope_archive_project_id"
ENVELOPE_ISSUED_AT_INDEX = "ix_jobs_envelope_archive_issued_at"


def upgrade():
    """
        Create the ``jobs_envelope_archive`` table + its lookup
        indexes.
    """
    op.create_table(
        "jobs_envelope_archive",
        sa.Column("envelope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.VARCHAR(32), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("hard_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("key_id", sa.VARCHAR(128), nullable=False, server_default=""),
        sa.Column("canonical_payload", sa.LargeBinary(), nullable=False),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("canonical_payload_text", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("envelope_id"),
    )
    op.create_index(
        ENVELOPE_RUN_INDEX,
        "jobs_envelope_archive",
        ["run_id"],
    )
    op.create_index(
        ENVELOPE_PROJECT_INDEX,
        "jobs_envelope_archive",
        ["project_id"],
    )
    op.create_index(
        ENVELOPE_ISSUED_AT_INDEX,
        "jobs_envelope_archive",
        ["issued_at"],
    )
    return


def downgrade():
    """
        Drop the envelope archive indexes + table.
    """
    op.drop_index(ENVELOPE_ISSUED_AT_INDEX, table_name="jobs_envelope_archive")
    op.drop_index(ENVELOPE_PROJECT_INDEX, table_name="jobs_envelope_archive")
    op.drop_index(ENVELOPE_RUN_INDEX, table_name="jobs_envelope_archive")
    op.drop_table("jobs_envelope_archive")
    return
