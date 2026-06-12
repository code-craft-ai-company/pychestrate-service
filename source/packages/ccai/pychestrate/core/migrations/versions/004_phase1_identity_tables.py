"""
Create Phase 1 identity, authentication, rbac, secrets, audit, and flag tables

Revision ID: 004_phase1_identity
Revises: 003_project_management
Create Date: 2026-04-19

This migration creates the Phase 1 spec-shaped tables backing the
layer-1 features. The tables live next to the legacy system-configuration
tables until the Phase 10 cut-over retires the legacy schema.

1-user-management
    - identity_users
    - identity_groups
    - identity_group_memberships
    - identity_email_verifications

1-authentication
    - auth_sessions
    - auth_local_credentials
    - auth_saml_replay_cache
    - auth_mfa_enrollments
    - auth_oidc_state

1-rbac
    - rbac_roles
    - rbac_permissions
    - rbac_role_permissions
    - rbac_role_bindings

1-secrets-vault (``phase1_`` prefix during parallel-run)
    - phase1_secrets
    - phase1_secret_versions
    - secret_acls
    - secret_outbox

1-audit-log
    - audit_records  (INSERT-only; UPDATE + DELETE grants are revoked at deploy
      time against the application role as required by the 1-audit-log spec)
    - audit_sink_registrations
    - audit_sink_outbox
    - audit_event_catalog

1-feature-flags
    - feature_flags
    - feature_flag_versions
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "004_phase1_identity"
down_revision = "003_project_management"
branch_labels = None
depends_on = None


# The application database role whose UPDATE / DELETE grants on
# ``audit_records`` are revoked to enforce the INSERT-only contract in
# the 1-audit-log spec. Operators can override via the Alembic environment
# config; the default targets the role used by the local development
# compose profile.
DEFAULT_AUDIT_APP_ROLE = "pychestrate_app"


# =============================================================================
# Enum type names — stable identifiers used in both upgrade and downgrade
# =============================================================================

IDENTITY_USER_STATUS = "identity_user_status"
AUTH_PROVIDER_KIND = "auth_provider_kind"
RBAC_ROLE_SOURCE = "rbac_role_source"
RBAC_PERMISSION_SOURCE = "rbac_permission_source"
RBAC_PERMISSION_EFFECT = "rbac_permission_effect"
RBAC_PRINCIPAL_KIND = "rbac_principal_kind"
RBAC_BINDING_SCOPE = "rbac_binding_scope"
SECRET_VERSION_STATE = "secret_version_state"
SECRET_OUTBOX_STATUS = "secret_outbox_status"
AUDIT_SINK_OUTBOX_STATUS = "audit_sink_outbox_status"
FEATURE_FLAG_KIND = "feature_flag_kind"
FEATURE_FLAG_STATE = "feature_flag_state"


def upgrade():
    """
        Create every Phase 1 table, its indexes, and the named
        PostgreSQL enum types each column depends on.
    """
    _upgrade_identity_users()
    _upgrade_authentication()
    _upgrade_rbac()
    _upgrade_secrets()
    _upgrade_audit()
    _upgrade_feature_flags()
    _revoke_audit_mutation_grants()
    return


def downgrade():
    """
        Reverse the upgrade. Drops every table in reverse dependency
        order, then drops each Postgres enum type.
    """
    _downgrade_feature_flags()
    _downgrade_audit()
    _downgrade_secrets()
    _downgrade_rbac()
    _downgrade_authentication()
    _downgrade_identity_users()
    _drop_enum_types()
    return


# =============================================================================
# 1-user-management
# =============================================================================

def _upgrade_identity_users():
    op.create_table(
        "identity_users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("login_name", sa.VARCHAR(128), nullable=False),
        sa.Column("primary_email", sa.VARCHAR(320), nullable=False),
        sa.Column("display_name", sa.VARCHAR(256), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "DEACTIVATED", "PENDING", name=IDENTITY_USER_STATUS),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("provisioning_source", sa.VARCHAR(128), nullable=False, server_default="local"),
        sa.Column("external_id", sa.VARCHAR(256), nullable=True),
        sa.Column("timezone", sa.VARCHAR(64), nullable=False, server_default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("login_name", name="uq_identity_users_login_name"),
        sa.UniqueConstraint("primary_email", name="uq_identity_users_primary_email"),
        sa.UniqueConstraint(
            "provisioning_source", "external_id",
            name="uq_identity_users_provisioning_external",
        ),
    )
    op.create_index("ix_identity_users_status", "identity_users", ["status"])

    op.create_table(
        "identity_groups",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_name", sa.VARCHAR(128), nullable=False),
        sa.Column("description", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("group_id"),
        sa.UniqueConstraint("group_name", name="uq_identity_groups_group_name"),
    )

    op.create_table(
        "identity_group_memberships",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["identity_groups.group_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by"], ["identity_users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("group_id", "user_id"),
    )

    op.create_table(
        "identity_email_verifications",
        sa.Column("verification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("new_email", sa.VARCHAR(320), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("verification_id"),
    )
    return


def _downgrade_identity_users():
    op.drop_table("identity_email_verifications")
    op.drop_table("identity_group_memberships")
    op.drop_table("identity_groups")
    op.drop_index("ix_identity_users_status", table_name="identity_users")
    op.drop_table("identity_users")
    return


# =============================================================================
# 1-authentication
# =============================================================================

def _upgrade_authentication():
    op.create_table(
        "auth_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider_kind",
            sa.Enum("OIDC", "SAML", "LOCAL", name=AUTH_PROVIDER_KIND),
            nullable=False,
        ),
        sa.Column("provider_name", sa.VARCHAR(128), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("idle_timeout_seconds", sa.Integer(), nullable=False, server_default="1800"),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("mfa_method_name", sa.VARCHAR(64), nullable=True),
        sa.Column("ip_fingerprint", sa.VARCHAR(128), nullable=False, server_default=""),
        sa.Column("user_agent_fingerprint", sa.VARCHAR(128), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_auth_sessions_user_expires", "auth_sessions", ["user_id", "expires_at"])
    op.create_index("ix_auth_sessions_last_seen", "auth_sessions", ["last_seen_at"])

    op.create_table(
        "auth_local_credentials",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("argon2id_hash", sa.LargeBinary(), nullable=False),
        sa.Column("algo_params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("must_rotate_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "auth_saml_replay_cache",
        sa.Column("response_id", sa.VARCHAR(128), nullable=False),
        sa.Column("not_on_or_after", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("response_id"),
    )

    op.create_table(
        "auth_mfa_enrollments",
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method_name", sa.VARCHAR(64), nullable=False),
        sa.Column("secret_ref", sa.VARCHAR(256), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("enrollment_id"),
    )

    op.create_table(
        "auth_oidc_state",
        sa.Column("state", sa.VARCHAR(128), nullable=False),
        sa.Column("nonce", sa.VARCHAR(128), nullable=False),
        sa.Column("pkce_verifier_enc", sa.LargeBinary(), nullable=False),
        sa.Column("provider_name", sa.VARCHAR(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redirect_target", sa.VARCHAR(1024), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("state"),
    )
    return


def _downgrade_authentication():
    op.drop_table("auth_oidc_state")
    op.drop_table("auth_mfa_enrollments")
    op.drop_table("auth_saml_replay_cache")
    op.drop_table("auth_local_credentials")
    op.drop_index("ix_auth_sessions_last_seen", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_expires", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    return


# =============================================================================
# 1-rbac
# =============================================================================

def _upgrade_rbac():
    op.create_table(
        "rbac_roles",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_name", sa.VARCHAR(128), nullable=False),
        sa.Column(
            "source",
            sa.Enum("BUILTIN", "EXTENSION", "CUSTOM", name=RBAC_ROLE_SOURCE),
            nullable=False,
        ),
        sa.Column("source_name", sa.VARCHAR(128), nullable=True),
        sa.Column("description", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("role_id"),
        sa.UniqueConstraint("role_name", name="uq_rbac_roles_role_name"),
    )

    op.create_table(
        "rbac_permissions",
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_key", sa.VARCHAR(256), nullable=False),
        sa.Column("description", sa.VARCHAR(512), nullable=False, server_default=""),
        sa.Column(
            "source",
            sa.Enum("BUILTIN", "EXTENSION", "CUSTOM", name=RBAC_PERMISSION_SOURCE),
            nullable=False,
        ),
        sa.Column("source_name", sa.VARCHAR(128), nullable=True),
        sa.PrimaryKeyConstraint("permission_id"),
        sa.UniqueConstraint("permission_key", name="uq_rbac_permissions_permission_key"),
    )

    op.create_table(
        "rbac_role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_key", sa.VARCHAR(256), nullable=False),
        sa.Column(
            "effect",
            sa.Enum("ALLOW", "DENY", name=RBAC_PERMISSION_EFFECT),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["role_id"], ["rbac_roles.role_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_key"),
    )

    op.create_table(
        "rbac_role_bindings",
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "principal_kind",
            sa.Enum("USER", "GROUP", name=RBAC_PRINCIPAL_KIND),
            nullable=False,
        ),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scope_kind",
            sa.Enum("SYSTEM", "ORGANIZATION", "PROJECT", name=RBAC_BINDING_SCOPE),
            nullable=False,
        ),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("inherits_into_project", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["role_id"], ["rbac_roles.role_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("binding_id"),
        sa.UniqueConstraint(
            "role_id", "principal_kind", "principal_id", "scope_kind", "scope_id",
            name="uq_rbac_role_bindings_assignment",
        ),
    )
    op.create_index(
        "ix_rbac_role_bindings_principal",
        "rbac_role_bindings",
        ["principal_kind", "principal_id"],
    )
    op.create_index(
        "ix_rbac_role_bindings_scope",
        "rbac_role_bindings",
        ["scope_kind", "scope_id"],
    )
    return


def _downgrade_rbac():
    op.drop_index("ix_rbac_role_bindings_scope", table_name="rbac_role_bindings")
    op.drop_index("ix_rbac_role_bindings_principal", table_name="rbac_role_bindings")
    op.drop_table("rbac_role_bindings")
    op.drop_table("rbac_role_permissions")
    op.drop_table("rbac_permissions")
    op.drop_table("rbac_roles")
    return


# =============================================================================
# 1-secrets-vault (phase1_ prefix during parallel-run)
# =============================================================================

def _upgrade_secrets():
    op.create_table(
        "phase1_secrets",
        sa.Column("secret_ref", sa.VARCHAR(256), nullable=False),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("backend_name", sa.VARCHAR(128), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("secret_ref"),
    )

    op.create_table(
        "phase1_secret_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_ref", sa.VARCHAR(256), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            sa.Enum("ACTIVE", "SUPERSEDED", "EXPIRED", name=SECRET_VERSION_STATE),
            nullable=False,
        ),
        sa.Column("ciphertext_ref", sa.VARCHAR(256), nullable=True),
        sa.Column("ciphertext_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=True),
        sa.Column("kek_id", sa.VARCHAR(128), nullable=True),
        sa.Column("grace_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["secret_ref"], ["phase1_secrets.secret_ref"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("version_id"),
    )
    op.create_index(
        "ix_secret_versions_ref_number",
        "phase1_secret_versions",
        ["secret_ref", "version_number"],
        unique=True,
    )

    op.create_table(
        "secret_acls",
        sa.Column("acl_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_ref", sa.VARCHAR(256), nullable=False),
        sa.Column("effect", sa.VARCHAR(16), nullable=False),
        sa.Column("principal_kind", sa.VARCHAR(16), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actions_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["secret_ref"], ["phase1_secrets.secret_ref"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("acl_id"),
    )

    op.create_table(
        "secret_outbox",
        sa.Column("outbox_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.VARCHAR(64), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "IN_FLIGHT", "FAILED", "COMPLETED", name=SECRET_OUTBOX_STATUS),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("outbox_id"),
    )
    return


def _downgrade_secrets():
    op.drop_table("secret_outbox")
    op.drop_table("secret_acls")
    op.drop_index("ix_secret_versions_ref_number", table_name="phase1_secret_versions")
    op.drop_table("phase1_secret_versions")
    op.drop_table("phase1_secrets")
    return


# =============================================================================
# 1-audit-log
# =============================================================================

def _upgrade_audit():
    op.create_table(
        "audit_records",
        sa.Column("sequence_number", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.VARCHAR(128), nullable=False),
        sa.Column("source_topic", sa.VARCHAR(128), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_service_identity", sa.VARCHAR(128), nullable=True),
        sa.Column("target_ref", sa.VARCHAR(256), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("payload_hash", sa.LargeBinary(64), nullable=False),
        sa.Column("previous_hash", sa.LargeBinary(64), nullable=False),
        sa.Column("record_hash", sa.LargeBinary(64), nullable=False),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("sequence_number"),
        sa.UniqueConstraint("record_id", name="uq_audit_records_record_id"),
        sa.UniqueConstraint("source_event_id", name="uq_audit_records_source_event_id"),
    )
    op.create_index("ix_audit_records_kind_written_at", "audit_records", ["kind", "written_at"])
    op.create_index(
        "ix_audit_records_actor_written_at",
        "audit_records",
        ["actor_user_id", "written_at"],
    )
    op.create_index(
        "ix_audit_records_target_ref_written_at",
        "audit_records",
        ["target_ref", "written_at"],
    )

    op.create_table(
        "audit_sink_registrations",
        sa.Column("sink_name", sa.VARCHAR(128), nullable=False),
        sa.Column("precedence", sa.Integer(), nullable=False),
        sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("capabilities_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("sink_name"),
    )

    op.create_table(
        "audit_sink_outbox",
        sa.Column("outbox_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sink_name", sa.VARCHAR(128), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "IN_FLIGHT", "FAILED", "COMPLETED", name=AUDIT_SINK_OUTBOX_STATUS),
            nullable=False,
        ),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("outbox_id"),
    )

    op.create_table(
        "audit_event_catalog",
        sa.Column("kind", sa.VARCHAR(128), nullable=False),
        sa.Column("source_name", sa.VARCHAR(128), nullable=True),
        sa.Column("payload_schema", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_reserved", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("kind"),
    )
    return


def _downgrade_audit():
    op.drop_table("audit_event_catalog")
    op.drop_table("audit_sink_outbox")
    op.drop_table("audit_sink_registrations")
    op.drop_index("ix_audit_records_target_ref_written_at", table_name="audit_records")
    op.drop_index("ix_audit_records_actor_written_at", table_name="audit_records")
    op.drop_index("ix_audit_records_kind_written_at", table_name="audit_records")
    op.drop_table("audit_records")
    return


# =============================================================================
# 1-feature-flags
# =============================================================================

def _upgrade_feature_flags():
    op.create_table(
        "feature_flags",
        sa.Column("flag_key", sa.VARCHAR(256), nullable=False),
        sa.Column(
            "flag_kind",
            sa.Enum("BOOLEAN", "STRING", "ENUM", "PERCENTAGE", name=FEATURE_FLAG_KIND),
            nullable=False,
        ),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "state",
            sa.Enum("ACTIVE", "RETIRED", name=FEATURE_FLAG_STATE),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("flag_key"),
    )

    op.create_table(
        "feature_flag_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flag_key", sa.VARCHAR(256), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("default_value", sa.JSON(), nullable=False),
        sa.Column("rules_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["flag_key"], ["feature_flags.flag_key"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("version_id"),
        sa.UniqueConstraint(
            "flag_key", "version",
            name="uq_feature_flag_versions_flag_version",
        ),
    )
    op.create_index("ix_feature_flag_versions_flag", "feature_flag_versions", ["flag_key"])
    return


def _downgrade_feature_flags():
    op.drop_index("ix_feature_flag_versions_flag", table_name="feature_flag_versions")
    op.drop_table("feature_flag_versions")
    op.drop_table("feature_flags")
    return


# =============================================================================
# 1-audit-log INSERT-only grant enforcement
# =============================================================================

def _revoke_audit_mutation_grants():
    """
        Enforce the 1-audit-log INSERT-only contract by revoking UPDATE +
        DELETE privileges from the application role on ``audit_records``.

        The role name is read from the Alembic context config under
        ``audit.app_role`` when present; otherwise the default
        ``pychestrate_app`` role is used. The ``IF EXISTS`` guard makes
        this idempotent on environments where the role does not exist yet
        — operators are expected to create the role before running
        migrations in production.
    """
    connection = op.get_bind()
    context = op.get_context()
    app_role = DEFAULT_AUDIT_APP_ROLE
    if context.config is not None:
        configured = context.config.get_main_option("audit.app_role")
        if configured is not None and len(configured) > 0:
            app_role = configured

    # The REVOKE is intentionally guarded. If the role does not exist the
    # statement is a no-op — the operator enforces the grant policy when
    # they create the role.
    connection.execute(sa.text(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role_name) THEN "
        "EXECUTE format('REVOKE UPDATE, DELETE ON TABLE audit_records FROM %I', :role_name); "
        "END IF; "
        "END $$;"
    ).bindparams(role_name=app_role))
    return


# =============================================================================
# Enum cleanup
# =============================================================================

def _drop_enum_types():
    """
        Drop every named PostgreSQL enum type created by the upgrade. SQLAlchemy
        does not drop these automatically when the referencing table is dropped,
        so we do it explicitly.
    """
    enum_names = [
        FEATURE_FLAG_STATE,
        FEATURE_FLAG_KIND,
        AUDIT_SINK_OUTBOX_STATUS,
        SECRET_OUTBOX_STATUS,
        SECRET_VERSION_STATE,
        RBAC_BINDING_SCOPE,
        RBAC_PRINCIPAL_KIND,
        RBAC_PERMISSION_EFFECT,
        RBAC_PERMISSION_SOURCE,
        RBAC_ROLE_SOURCE,
        AUTH_PROVIDER_KIND,
        IDENTITY_USER_STATUS,
    ]
    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name != "postgresql":
        return
    for name in enum_names:
        sa.Enum(name=name).drop(bind, checkfirst=True)
    return
