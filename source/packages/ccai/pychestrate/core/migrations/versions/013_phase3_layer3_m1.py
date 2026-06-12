"""
Create Phase 3 Layer-3 M1 tables.

Revision ID: 013_phase3_layer3_m1
Revises: 012_phase2_m3_hardening
Create Date: 2026-04-20

Creates the combined pod + agent tables for 10 Layer-3 specs: pod
definitions, lifecycle, static registration, dynamic materialization,
scoped-config, client-agent-protocol sessions/audits, capability
advertisements, inventory change log, and agent-upgrade rollouts/offers.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "013_phase3_layer3_m1"
down_revision = "012_phase2_m3_hardening"
branch_labels = None
depends_on = None


POD_STATE = "pods_pod_state"
REGISTRATION_STATE = "pods_registration_state"
MATERIALIZATION_STATE = "pods_materialization_state"
FRAME_DIRECTION = "agents_frame_direction"
ROLLOUT_STATE = "agents_rollout_state"
OFFER_OUTCOME = "agents_upgrade_offer_outcome"


def upgrade():
    """
        Create Layer-3 M1 tables.
    """
    op.create_table(
        "pods_definitions",
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_name", sa.VARCHAR(128), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("pod_id"),
        sa.UniqueConstraint("project_id", "pod_name", name="uq_pods_definition_project_name"),
    )
    op.create_index("ix_pods_definition_project", "pods_definitions", ["project_id"])

    op.create_table(
        "pods_definition_versions",
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods_definitions.pod_id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("spec_hash", sa.VARCHAR(64), nullable=False),
        sa.Column("validator_report", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("pod_id", "version"),
    )

    op.create_table(
        "pods_runtime_state",
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods_definitions.pod_id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.Enum("DEFINED", "PROVISIONING", "READY", "IN_USE", "DRAINING", "RELEASED", "CLIENT_LOST", "FAILED", name=POD_STATE), nullable=False, server_default="DEFINED"),
        sa.Column("previous_state", sa.Enum("DEFINED", "PROVISIONING", "READY", "IN_USE", "DRAINING", "RELEASED", "CLIENT_LOST", "FAILED", name=POD_STATE), nullable=True),
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_transition_event", sa.VARCHAR(64), nullable=True),
        sa.Column("in_use_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runs_remaining", sa.Integer(), nullable=True),
        sa.Column("transition_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("pod_id"),
    )

    op.create_table(
        "pods_lifecycle_log",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods_definitions.pod_id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_state", sa.Enum("DEFINED", "PROVISIONING", "READY", "IN_USE", "DRAINING", "RELEASED", "CLIENT_LOST", "FAILED", name=POD_STATE), nullable=True),
        sa.Column("to_state", sa.Enum("DEFINED", "PROVISIONING", "READY", "IN_USE", "DRAINING", "RELEASED", "CLIENT_LOST", "FAILED", name=POD_STATE), nullable=False),
        sa.Column("event_kind", sa.VARCHAR(64), nullable=False),
        sa.Column("event_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actor", sa.VARCHAR(128), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("log_id"),
    )
    op.create_index("ix_pods_lifecycle_log_pod", "pods_lifecycle_log", ["pod_id"])

    op.create_table(
        "pods_registrations",
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods_definitions.pod_id", ondelete="CASCADE"), nullable=False),
        sa.Column("pod_definition_version", sa.Integer(), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.Enum("REGISTERED", "CLIENT_LOST", "DRAINING", "DEREGISTERED", name=REGISTRATION_STATE), nullable=False, server_default="REGISTERED"),
        sa.Column("report_hash", sa.VARCHAR(64), nullable=False),
        sa.Column("report_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_report_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deregistered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deregister_reason", sa.VARCHAR(256), nullable=True),
        sa.Column("client_lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("registration_id"),
    )
    op.create_index("ix_pods_registration_pod", "pods_registrations", ["pod_id"])
    op.create_index("ix_pods_registration_state", "pods_registrations", ["state"])

    op.create_table(
        "pods_templates",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column("template_kind", sa.VARCHAR(64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("parameter_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("template_id"),
        sa.UniqueConstraint("project_id", "name", name="uq_pods_template_project_name"),
    )

    op.create_table(
        "pods_dynamic_materializations",
        sa.Column("materialization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods_templates.template_id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_source_version", sa.Integer(), nullable=False),
        sa.Column("parameters_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("rendered_spec_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods_definitions.pod_id", ondelete="SET NULL"), nullable=True),
        sa.Column("state", sa.Enum("PENDING", "RENDERING", "RESERVING", "PROVISIONING", "AWAITING_CLIENT", "READY", "FAILED", "RELEASED", name=MATERIALIZATION_STATE), nullable=False, server_default="PENDING"),
        sa.Column("current_step", sa.VARCHAR(64), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("reservation_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orphaned_reason", sa.VARCHAR(256), nullable=True),
        sa.PrimaryKeyConstraint("materialization_id"),
    )

    op.create_table(
        "pods_run_variables",
        sa.Column("variable_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(128), nullable=False),
        sa.Column("value_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("value_schema", postgresql.JSONB(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("set_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("variable_id"),
        sa.UniqueConstraint("run_id", "pod_id", "name", name="uq_pods_run_variable_scope"),
    )
    op.create_index("ix_pods_run_variable_run", "pods_run_variables", ["run_id"])

    op.create_table(
        "agents_client_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transport_name", sa.VARCHAR(64), nullable=False),
        sa.Column("remote_addr", sa.VARCHAR(128), nullable=True),
        sa.Column("cert_serial", sa.VARCHAR(64), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_code", sa.VARCHAR(64), nullable=True),
        sa.Column("enrollment_nonce", sa.VARCHAR(128), nullable=True),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_agents_client_sessions_client", "agents_client_sessions", ["client_id"])

    op.create_table(
        "agents_client_frame_audit",
        sa.Column("frame_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents_client_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.VARCHAR(64), nullable=False),
        sa.Column("direction", sa.Enum("INBOUND", "OUTBOUND", name=FRAME_DIRECTION), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reject_reason", sa.VARCHAR(256), nullable=True),
        sa.PrimaryKeyConstraint("frame_id"),
    )

    op.create_table(
        "agents_client_capabilities",
        sa.Column("capability_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.VARCHAR(64), nullable=False),
        sa.Column("value_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sensitive_ref", sa.VARCHAR(256), nullable=True),
        sa.Column("revision_token", sa.VARCHAR(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("capability_id"),
        sa.UniqueConstraint("client_id", "kind", name="uq_agents_capability_client_kind"),
    )
    op.create_index("ix_agents_capability_client", "agents_client_capabilities", ["client_id"])

    op.create_table(
        "agents_client_inventory_change_log",
        sa.Column("change_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("change_kind", sa.VARCHAR(64), nullable=False),
        sa.Column("payload_summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("change_id"),
    )
    op.create_index("ix_agents_inventory_change_client", "agents_client_inventory_change_log", ["client_id"])
    op.create_index("ix_agents_inventory_change_logged", "agents_client_inventory_change_log", ["logged_at"])

    op.create_table(
        "agents_rollouts",
        sa.Column("rollout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.VARCHAR(64), nullable=False),
        sa.Column("artifact_source", sa.VARCHAR(64), nullable=False),
        sa.Column("artifact_ref", sa.VARCHAR(512), nullable=False),
        sa.Column("signature", sa.LargeBinary(), nullable=True),
        sa.Column("state", sa.Enum("DRAFT", "ACTIVE", "HALTED", "COMPLETED", name=ROLLOUT_STATE), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("rollout_id"),
    )

    op.create_table(
        "agents_upgrade_offers",
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rollout_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents_rollouts.rollout_id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.VARCHAR(64), nullable=False),
        sa.Column("outcome", sa.Enum("OFFERED", "SUCCEEDED", "FAILED", "DEFERRED", "EXPIRED", "SHA256_MISMATCH", name=OFFER_OUTCOME), nullable=False, server_default="OFFERED"),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("offer_id"),
    )
    op.create_index("ix_agents_upgrade_offer_rollout", "agents_upgrade_offers", ["rollout_id"])
    op.create_index("ix_agents_upgrade_offer_client", "agents_upgrade_offers", ["client_id"])

    return


def downgrade():
    """
        Drop Layer-3 M1 tables.
    """
    op.drop_index("ix_agents_upgrade_offer_client", table_name="agents_upgrade_offers")
    op.drop_index("ix_agents_upgrade_offer_rollout", table_name="agents_upgrade_offers")
    op.drop_table("agents_upgrade_offers")
    op.drop_table("agents_rollouts")
    op.drop_index("ix_agents_inventory_change_logged", table_name="agents_client_inventory_change_log")
    op.drop_index("ix_agents_inventory_change_client", table_name="agents_client_inventory_change_log")
    op.drop_table("agents_client_inventory_change_log")
    op.drop_index("ix_agents_capability_client", table_name="agents_client_capabilities")
    op.drop_table("agents_client_capabilities")
    op.drop_table("agents_client_frame_audit")
    op.drop_index("ix_agents_client_sessions_client", table_name="agents_client_sessions")
    op.drop_table("agents_client_sessions")
    op.drop_index("ix_pods_run_variable_run", table_name="pods_run_variables")
    op.drop_table("pods_run_variables")
    op.drop_table("pods_dynamic_materializations")
    op.drop_table("pods_templates")
    op.drop_index("ix_pods_registration_state", table_name="pods_registrations")
    op.drop_index("ix_pods_registration_pod", table_name="pods_registrations")
    op.drop_table("pods_registrations")
    op.drop_index("ix_pods_lifecycle_log_pod", table_name="pods_lifecycle_log")
    op.drop_table("pods_lifecycle_log")
    op.drop_table("pods_runtime_state")
    op.drop_table("pods_definition_versions")
    op.drop_index("ix_pods_definition_project", table_name="pods_definitions")
    op.drop_table("pods_definitions")

    bind = op.get_bind()
    for enum_name in (OFFER_OUTCOME, ROLLOUT_STATE, FRAME_DIRECTION,
                      MATERIALIZATION_STATE, REGISTRATION_STATE, POD_STATE):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
    return
