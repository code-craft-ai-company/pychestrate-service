"""
Create system configuration tables

Revision ID: 001_system_configuration
Revises: None
Create Date: 2026-02-21

This migration creates the following tables for the System Configuration module:
- permissions: Permission definitions
- system_roles: System role definitions with permission associations
- role_permissions: Association table for role-permission many-to-many
- sessions: User session tracking
- password_history: Password history for reuse prevention
- global_variables: System-wide configuration variables
- global_variable_history: Audit trail for variable changes
- secret_scopes: Secret organization and access control
- secrets: Encrypted secret storage
- secret_versions: Secret version tracking
- scope_permissions: Association table for scope-role permissions
- audit_logs: Security event audit trail

Also creates default system roles and permissions.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '001_system_configuration'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """
        Create system configuration tables and seed default data.
    """
    # Create permissions table
    op.create_table(
        'permissions',
        sa.Column('perm_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('perm_name', sa.VARCHAR(64), nullable=False),
        sa.Column('perm_description', sa.VARCHAR(255), nullable=True),
        sa.PrimaryKeyConstraint('perm_id'),
        sa.UniqueConstraint('perm_name')
    )
    op.create_index('ix_permissions_perm_name', 'permissions', ['perm_name'])

    # Create system_roles table
    op.create_table(
        'system_roles',
        sa.Column('role_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('role_name', sa.VARCHAR(64), nullable=False),
        sa.Column('role_description', sa.VARCHAR(255), nullable=True),
        sa.Column('role_is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('role_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('role_id'),
        sa.UniqueConstraint('role_name')
    )
    op.create_index('ix_system_roles_role_name', 'system_roles', ['role_name'])

    # Create role_permissions association table
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('permission_id', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['system_roles.role_id']),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.perm_id']),
        sa.PrimaryKeyConstraint('role_id', 'permission_id')
    )

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('sess_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('sess_token', sa.VARCHAR(64), nullable=False),
        sa.Column('sess_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sess_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('sess_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sess_last_activity', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('sess_client_ip', sa.VARCHAR(45), nullable=True),
        sa.Column('sess_user_agent', sa.VARCHAR(255), nullable=True),
        sa.Column('sess_csrf_token', sa.VARCHAR(64), nullable=True),
        sa.ForeignKeyConstraint(['sess_user_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('sess_id'),
        sa.UniqueConstraint('sess_token')
    )
    op.create_index('ix_sessions_sess_token', 'sessions', ['sess_token'])
    op.create_index('ix_sessions_sess_user_id', 'sessions', ['sess_user_id'])

    # Create password_history table
    op.create_table(
        'password_history',
        sa.Column('pwdhist_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pwdhist_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pwdhist_password_hash', sa.VARCHAR(255), nullable=False),
        sa.Column('pwdhist_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['pwdhist_user_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('pwdhist_id')
    )
    op.create_index('ix_password_history_pwdhist_user_id', 'password_history', ['pwdhist_user_id'])

    # Create global_variables table
    op.create_table(
        'global_variables',
        sa.Column('gvar_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('gvar_name', sa.VARCHAR(128), nullable=False),
        sa.Column('gvar_value_json', sa.Text(), nullable=False),
        sa.Column('gvar_type', sa.VARCHAR(16), nullable=False),
        sa.Column('gvar_description', sa.VARCHAR(512), nullable=True),
        sa.Column('gvar_default_value_json', sa.Text(), nullable=True),
        sa.Column('gvar_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('gvar_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('gvar_updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['gvar_updated_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('gvar_id'),
        sa.UniqueConstraint('gvar_name')
    )
    op.create_index('ix_global_variables_gvar_name', 'global_variables', ['gvar_name'])

    # Create global_variable_history table
    op.create_table(
        'global_variable_history',
        sa.Column('gvarhist_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('gvarhist_variable_id', sa.BigInteger(), nullable=False),
        sa.Column('gvarhist_variable_name', sa.VARCHAR(128), nullable=False),
        sa.Column('gvarhist_old_value_json', sa.Text(), nullable=True),
        sa.Column('gvarhist_new_value_json', sa.Text(), nullable=True),
        sa.Column('gvarhist_changed_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('gvarhist_changed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['gvarhist_variable_id'], ['global_variables.gvar_id']),
        sa.ForeignKeyConstraint(['gvarhist_changed_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('gvarhist_id')
    )
    op.create_index('ix_global_variable_history_gvarhist_variable_id', 'global_variable_history', ['gvarhist_variable_id'])

    # Create secret_scopes table
    op.create_table(
        'secret_scopes',
        sa.Column('scope_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('scope_name', sa.VARCHAR(128), nullable=False),
        sa.Column('scope_description', sa.VARCHAR(512), nullable=True),
        sa.Column('scope_is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('scope_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('scope_created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['scope_created_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('scope_id'),
        sa.UniqueConstraint('scope_name')
    )
    op.create_index('ix_secret_scopes_scope_name', 'secret_scopes', ['scope_name'])

    # Create secrets table
    op.create_table(
        'secrets',
        sa.Column('secret_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('secret_name', sa.VARCHAR(128), nullable=False),
        sa.Column('secret_scope_id', sa.BigInteger(), nullable=False),
        sa.Column('secret_encrypted_value', sa.LargeBinary(), nullable=False),
        sa.Column('secret_type', sa.VARCHAR(32), nullable=False),
        sa.Column('secret_description', sa.VARCHAR(512), nullable=True),
        sa.Column('secret_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('secret_is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('secret_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('secret_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('secret_updated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['secret_scope_id'], ['secret_scopes.scope_id']),
        sa.ForeignKeyConstraint(['secret_updated_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('secret_id')
    )
    op.create_index('ix_secrets_secret_name', 'secrets', ['secret_name'])
    op.create_index('ix_secrets_secret_scope_id', 'secrets', ['secret_scope_id'])
    op.create_index('ix_secrets_scope_name', 'secrets', ['secret_scope_id', 'secret_name'], unique=True)

    # Create secret_versions table
    op.create_table(
        'secret_versions',
        sa.Column('secver_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('secver_secret_id', sa.BigInteger(), nullable=False),
        sa.Column('secver_version', sa.Integer(), nullable=False),
        sa.Column('secver_changed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('secver_changed_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['secver_secret_id'], ['secrets.secret_id']),
        sa.ForeignKeyConstraint(['secver_changed_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('secver_id')
    )
    op.create_index('ix_secret_versions_secver_secret_id', 'secret_versions', ['secver_secret_id'])

    # Create scope_permissions association table
    op.create_table(
        'scope_permissions',
        sa.Column('scope_id', sa.BigInteger(), nullable=False),
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('can_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('can_manage', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['scope_id'], ['secret_scopes.scope_id']),
        sa.ForeignKeyConstraint(['role_id'], ['system_roles.role_id']),
        sa.PrimaryKeyConstraint('scope_id', 'role_id')
    )

    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('audit_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('audit_event_type', sa.VARCHAR(64), nullable=False),
        sa.Column('audit_timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('audit_user_id', sa.VARCHAR(40), nullable=True),
        sa.Column('audit_username', sa.VARCHAR(64), nullable=True),
        sa.Column('audit_target_user_id', sa.VARCHAR(40), nullable=True),
        sa.Column('audit_target_username', sa.VARCHAR(64), nullable=True),
        sa.Column('audit_client_ip', sa.VARCHAR(45), nullable=True),
        sa.Column('audit_details_json', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('audit_id')
    )
    op.create_index('ix_audit_logs_audit_event_type', 'audit_logs', ['audit_event_type'])
    op.create_index('ix_audit_logs_audit_timestamp', 'audit_logs', ['audit_timestamp'])

    # Seed default permissions
    _seed_default_permissions()

    # Seed default system roles
    _seed_default_roles()

    # Seed default system scope for secrets
    _seed_default_scope()


def _seed_default_permissions():
    """
        Insert default permissions for the system.
    """
    permissions_table = sa.table(
        'permissions',
        sa.column('perm_name', sa.VARCHAR(64)),
        sa.column('perm_description', sa.VARCHAR(255))
    )

    default_permissions = [
        # User management permissions
        {'perm_name': 'users.create', 'perm_description': 'Create new user accounts'},
        {'perm_name': 'users.read', 'perm_description': 'View user account information'},
        {'perm_name': 'users.update', 'perm_description': 'Update user account information'},
        {'perm_name': 'users.delete', 'perm_description': 'Deactivate user accounts'},
        {'perm_name': 'users.manage_roles', 'perm_description': 'Assign and remove roles from users'},
        # Role management permissions
        {'perm_name': 'roles.create', 'perm_description': 'Create new roles'},
        {'perm_name': 'roles.read', 'perm_description': 'View role information'},
        {'perm_name': 'roles.update', 'perm_description': 'Update role permissions'},
        {'perm_name': 'roles.delete', 'perm_description': 'Delete non-system roles'},
        # Session management permissions
        {'perm_name': 'sessions.read', 'perm_description': 'View active sessions'},
        {'perm_name': 'sessions.terminate', 'perm_description': 'Terminate user sessions'},
        # Global variable permissions
        {'perm_name': 'variables.create', 'perm_description': 'Create global variables'},
        {'perm_name': 'variables.read', 'perm_description': 'View global variables'},
        {'perm_name': 'variables.update', 'perm_description': 'Update global variables'},
        {'perm_name': 'variables.delete', 'perm_description': 'Delete global variables'},
        # Secret management permissions
        {'perm_name': 'secrets.create', 'perm_description': 'Create secrets'},
        {'perm_name': 'secrets.read', 'perm_description': 'View secret metadata'},
        {'perm_name': 'secrets.read_value', 'perm_description': 'Read secret values'},
        {'perm_name': 'secrets.update', 'perm_description': 'Update secrets'},
        {'perm_name': 'secrets.delete', 'perm_description': 'Delete secrets'},
        # Scope management permissions
        {'perm_name': 'scopes.create', 'perm_description': 'Create secret scopes'},
        {'perm_name': 'scopes.read', 'perm_description': 'View secret scopes'},
        {'perm_name': 'scopes.update', 'perm_description': 'Update scope permissions'},
        {'perm_name': 'scopes.delete', 'perm_description': 'Delete secret scopes'},
        # Audit log permissions
        {'perm_name': 'audit.read', 'perm_description': 'View audit logs'},
    ]

    op.bulk_insert(permissions_table, default_permissions)


def _seed_default_roles():
    """
        Insert default system roles with their permission assignments.
    """
    roles_table = sa.table(
        'system_roles',
        sa.column('role_name', sa.VARCHAR(64)),
        sa.column('role_description', sa.VARCHAR(255)),
        sa.column('role_is_system', sa.Boolean())
    )

    default_roles = [
        {
            'role_name': 'Administrator',
            'role_description': 'Full system access with all permissions',
            'role_is_system': True
        },
        {
            'role_name': 'Operator',
            'role_description': 'Operational access for managing variables and secrets',
            'role_is_system': True
        },
        {
            'role_name': 'Viewer',
            'role_description': 'Read-only access to system information',
            'role_is_system': True
        }
    ]

    op.bulk_insert(roles_table, default_roles)

    # Assign permissions to roles using raw SQL for cross-database compatibility
    connection = op.get_bind()

    # Administrator gets all permissions
    connection.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.perm_id
        FROM system_roles r, permissions p
        WHERE r.role_name = 'Administrator'
    """))

    # Operator gets operational permissions
    operator_permissions = [
        'users.read', 'roles.read', 'sessions.read',
        'variables.create', 'variables.read', 'variables.update', 'variables.delete',
        'secrets.create', 'secrets.read', 'secrets.read_value', 'secrets.update', 'secrets.delete',
        'scopes.read', 'audit.read'
    ]
    for perm in operator_permissions:
        connection.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.role_id, p.perm_id
            FROM system_roles r, permissions p
            WHERE r.role_name = 'Operator' AND p.perm_name = :perm_name
        """), {'perm_name': perm})

    # Viewer gets read-only permissions
    viewer_permissions = [
        'users.read', 'roles.read', 'sessions.read',
        'variables.read', 'secrets.read', 'scopes.read', 'audit.read'
    ]
    for perm in viewer_permissions:
        connection.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.role_id, p.perm_id
            FROM system_roles r, permissions p
            WHERE r.role_name = 'Viewer' AND p.perm_name = :perm_name
        """), {'perm_name': perm})


def _seed_default_scope():
    """
        Insert default system scope for secrets.
    """
    scopes_table = sa.table(
        'secret_scopes',
        sa.column('scope_name', sa.VARCHAR(128)),
        sa.column('scope_description', sa.VARCHAR(512)),
        sa.column('scope_is_system', sa.Boolean())
    )

    default_scope = {
        'scope_name': 'system',
        'scope_description': 'System-wide secrets accessible only to administrators',
        'scope_is_system': True
    }

    op.bulk_insert(scopes_table, [default_scope])

    # Grant Administrator role full access to system scope
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO scope_permissions (scope_id, role_id, can_read, can_manage)
        SELECT s.scope_id, r.role_id, true, true
        FROM secret_scopes s, system_roles r
        WHERE s.scope_name = 'system' AND r.role_name = 'Administrator'
    """))


def downgrade():
    """
        Drop all system configuration tables.
    """
    op.drop_table('audit_logs')
    op.drop_table('scope_permissions')
    op.drop_table('secret_versions')
    op.drop_table('secrets')
    op.drop_table('secret_scopes')
    op.drop_table('global_variable_history')
    op.drop_table('global_variables')
    op.drop_table('password_history')
    op.drop_table('sessions')
    op.drop_table('role_permissions')
    op.drop_table('system_roles')
    op.drop_table('permissions')
