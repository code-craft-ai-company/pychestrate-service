"""
Add Phase-10 / 10-release-channels + 3-agent-upgrade-channel M1 tables.

Revision ID: 040_phase10_release_channels_agent_upgrade
Revises: 039_phase10_webhooks_in
Create Date: 2026-04-25

Adds:

- ``release_releases``.
- ``release_channel_state``.
- ``release_stage_events``.
- ``release_consumer_outcomes``.
- ``release_trusted_issuer_keys``.
- ``agent_rollout``.
- ``agent_rollout_stage``.
- ``agent_upgrade_offer``.
- ``agent_pod_pin``.

Plus the ``release_component``, ``release_channel``,
``release_status``, ``release_stage_event_kind``,
``release_consumer_outcome``, ``agent_rollout_state``,
``agent_rollout_stage_state``, and
``agent_upgrade_offer_outcome`` enums.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "040_phase10_release_channels_agent_upgrade"
down_revision = "039_phase10_webhooks_in"
branch_labels = None
depends_on = None


RELEASE_COMPONENT_ENUM = "release_component"
RELEASE_COMPONENT_VALUES = ("SERVICE", "AGENT")

RELEASE_CHANNEL_ENUM = "release_channel"
RELEASE_CHANNEL_VALUES = ("CANARY", "BETA", "STABLE")

RELEASE_STATUS_ENUM = "release_status"
RELEASE_STATUS_VALUES = ("ACTIVE", "SUPERSEDED", "ROLLED_BACK", "WITHDRAWN")

RELEASE_STAGE_EVENT_KIND_ENUM = "release_stage_event_kind"
RELEASE_STAGE_EVENT_KIND_VALUES = (
    "PUBLISHED", "PROMOTED", "DEMOTED", "ROLLED_BACK", "AUTO_HALTED",
)

RELEASE_CONSUMER_OUTCOME_ENUM = "release_consumer_outcome"
RELEASE_CONSUMER_OUTCOME_VALUES = ("SUCCESS", "FAILURE", "DEFERRED")

ROLLOUT_STATE_ENUM = "agent_rollout_state"
ROLLOUT_STATE_VALUES = ("DRAFT", "ACTIVE", "HALTED", "COMPLETED", "ABANDONED")

STAGE_STATE_ENUM = "agent_rollout_stage_state"
STAGE_STATE_VALUES = ("PENDING", "ACTIVE", "HELD", "COMPLETED", "HALTED")

OFFER_OUTCOME_ENUM = "agent_upgrade_offer_outcome"
OFFER_OUTCOME_VALUES = (
    "OFFERED", "SUCCEEDED", "FAILED", "DEFERRED",
    "EXPIRED", "SHA256_MISMATCH", "FETCH_FAILED",
)


def upgrade():
    """
        Create the release-channels + agent-upgrade tables.
    """
    op.create_table(
        "release_trusted_issuer_keys",
        sa.Column("issuer_key_id", sa.VARCHAR(128), nullable=False),
        sa.Column("public_key_bytes", sa.LargeBinary(), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.VARCHAR(128), nullable=True),
        sa.PrimaryKeyConstraint("issuer_key_id"),
    )

    op.create_table(
        "release_releases",
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "component",
            sa.Enum(*RELEASE_COMPONENT_VALUES, name=RELEASE_COMPONENT_ENUM),
            nullable=False,
        ),
        sa.Column("version", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(*RELEASE_CHANNEL_VALUES, name=RELEASE_CHANNEL_ENUM),
            nullable=False,
        ),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("artifact_sha256", sa.VARCHAR(64), nullable=False),
        sa.Column("manifest_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("signature", sa.LargeBinary(), nullable=False),
        sa.Column("issuer_key_id", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("issued_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*RELEASE_STATUS_VALUES, name=RELEASE_STATUS_ENUM),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "rollout_fraction", sa.Float(), nullable=False, server_default="0",
        ),
        sa.Column(
            "stage_started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "previous_release_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("release_id"),
        sa.UniqueConstraint(
            "component", "version", "channel",
            name="uq_release_releases_component_version_channel",
        ),
    )
    op.create_index(
        "ix_release_releases_component_channel_status",
        "release_releases",
        ["component", "channel", "status"],
    )
    op.create_index(
        "ix_release_releases_issued_at",
        "release_releases",
        ["issued_at"],
    )

    op.create_table(
        "release_channel_state",
        sa.Column(
            "component",
            sa.Enum(*RELEASE_COMPONENT_VALUES, name=RELEASE_COMPONENT_ENUM),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum(*RELEASE_CHANNEL_VALUES, name=RELEASE_CHANNEL_ENUM),
            nullable=False,
        ),
        sa.Column(
            "current_release_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "previous_release_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "last_promotion_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "last_rollback_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.PrimaryKeyConstraint("component", "channel"),
    )

    op.create_table(
        "release_stage_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                *RELEASE_STAGE_EVENT_KIND_VALUES,
                name=RELEASE_STAGE_EVENT_KIND_ENUM,
            ),
            nullable=False,
        ),
        sa.Column("from_fraction", sa.Float(), nullable=True),
        sa.Column("to_fraction", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "actor_user_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["release_releases.release_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_release_stage_events_release_occurred",
        "release_stage_events",
        ["release_id", "occurred_at"],
    )

    op.create_table(
        "release_consumer_outcomes",
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_id", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "component",
            sa.Enum(*RELEASE_COMPONENT_VALUES, name=RELEASE_COMPONENT_ENUM),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                *RELEASE_CONSUMER_OUTCOME_VALUES,
                name=RELEASE_CONSUMER_OUTCOME_ENUM,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("release_id", "consumer_id"),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["release_releases.release_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_release_consumer_outcomes_release_outcome",
        "release_consumer_outcomes",
        ["release_id", "outcome", "reported_at"],
    )

    op.create_table(
        "agent_rollout",
        sa.Column("rollout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.VARCHAR(64), nullable=False),
        sa.Column("artifact_source", sa.VARCHAR(64), nullable=False),
        sa.Column("artifact_ref", sa.Text(), nullable=False),
        sa.Column("artifact_sha256", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "signature", sa.Text(), nullable=False, server_default="",
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "state",
            sa.Enum(*ROLLOUT_STATE_VALUES, name=ROLLOUT_STATE_ENUM),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("halted_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("rollout_id"),
    )
    op.create_index("ix_agent_rollout_version", "agent_rollout", ["version"])
    op.create_index("ix_agent_rollout_state", "agent_rollout", ["state"])

    op.create_table(
        "agent_rollout_stage",
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rollout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_index", sa.Integer(), nullable=False),
        sa.Column("rollout_policy", sa.VARCHAR(64), nullable=False),
        sa.Column("policy_params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "target_size", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "state",
            sa.Enum(*STAGE_STATE_VALUES, name=STAGE_STATE_ENUM),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "success_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "failure_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "deferred_count", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.PrimaryKeyConstraint("stage_id"),
        sa.ForeignKeyConstraint(
            ["rollout_id"],
            ["agent_rollout.rollout_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "rollout_id", "stage_index",
            name="uq_agent_rollout_stage_rollout_index",
        ),
    )

    op.create_table(
        "agent_upgrade_offer",
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.VARCHAR(128), nullable=False),
        sa.Column("version", sa.VARCHAR(64), nullable=False),
        sa.Column(
            "offered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "outcome",
            sa.Enum(*OFFER_OUTCOME_VALUES, name=OFFER_OUTCOME_ENUM),
            nullable=False,
            server_default="OFFERED",
        ),
        sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_detail", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("offer_id"),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["agent_rollout_stage.stage_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "stage_id", "client_id",
            name="uq_agent_upgrade_offer_stage_client",
        ),
    )
    op.create_index(
        "ix_agent_upgrade_offer_outcome",
        "agent_upgrade_offer",
        ["outcome"],
    )

    op.create_table(
        "agent_pod_pin",
        sa.Column("pod_id", sa.VARCHAR(128), nullable=False),
        sa.Column("pinned_version", sa.VARCHAR(64), nullable=False),
        sa.Column("set_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "set_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("pod_id"),
    )
    return


def downgrade():
    """
        Drop the release-channels + agent-upgrade tables.
    """
    op.drop_table("agent_pod_pin")
    op.drop_index(
        "ix_agent_upgrade_offer_outcome", table_name="agent_upgrade_offer",
    )
    op.drop_table("agent_upgrade_offer")
    op.drop_table("agent_rollout_stage")
    op.drop_index("ix_agent_rollout_state", table_name="agent_rollout")
    op.drop_index("ix_agent_rollout_version", table_name="agent_rollout")
    op.drop_table("agent_rollout")

    op.drop_index(
        "ix_release_consumer_outcomes_release_outcome",
        table_name="release_consumer_outcomes",
    )
    op.drop_table("release_consumer_outcomes")

    op.drop_index(
        "ix_release_stage_events_release_occurred",
        table_name="release_stage_events",
    )
    op.drop_table("release_stage_events")

    op.drop_table("release_channel_state")

    op.drop_index(
        "ix_release_releases_issued_at", table_name="release_releases",
    )
    op.drop_index(
        "ix_release_releases_component_channel_status",
        table_name="release_releases",
    )
    op.drop_table("release_releases")

    op.drop_table("release_trusted_issuer_keys")

    sa.Enum(name=OFFER_OUTCOME_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=STAGE_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=ROLLOUT_STATE_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RELEASE_CONSUMER_OUTCOME_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RELEASE_STAGE_EVENT_KIND_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RELEASE_STATUS_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RELEASE_CHANNEL_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=RELEASE_COMPONENT_ENUM).drop(op.get_bind(), checkfirst=True)
    return
