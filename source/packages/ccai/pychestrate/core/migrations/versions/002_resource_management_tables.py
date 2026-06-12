"""
Create resource management tables

Revision ID: 002_resource_management
Revises: 001_system_configuration
Create Date: 2026-02-21

This migration creates the following tables for the Resource Management module:
- resource_pools: Logical groupings of resources for organization and access control
- resource_tags_def: Tag definitions for resource filtering and organization
- resources: Resource definitions that can be allocated to jobs or users
- resource_tags: Association table for resource-tag many-to-many relationship
- pool_permissions: Association table for pool-role permissions
- ip_pools: IP address pools with CIDR ranges
- ip_allocations: IP address allocation tracking
- allocations: Resource allocation (checkout) tracking
- reservations: Future resource reservation tracking
- health_check_configs: Health check configuration for resources
- health_transition_logs: Health status transition audit trail
- resource_metadata_history: Resource metadata change audit trail

Also creates default resource pool and resource management permissions.
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '002_resource_management'
down_revision = '001_system_configuration'
branch_labels = None
depends_on = None


def upgrade():
    """
        Create resource management tables and seed default data.
    """
    # Create resource_pools table
    op.create_table(
        'resource_pools',
        sa.Column('pool_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pool_name', sa.VARCHAR(128), nullable=False),
        sa.Column('pool_description', sa.VARCHAR(512), nullable=True),
        sa.Column('pool_is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('pool_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pool_created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['pool_created_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('pool_id'),
        sa.UniqueConstraint('pool_name')
    )
    op.create_index('ix_resource_pools_pool_name', 'resource_pools', ['pool_name'])

    # Create resource_tags_def table
    op.create_table(
        'resource_tags_def',
        sa.Column('tag_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tag_name', sa.VARCHAR(64), nullable=False),
        sa.Column('tag_description', sa.VARCHAR(255), nullable=True),
        sa.Column('tag_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('tag_id'),
        sa.UniqueConstraint('tag_name')
    )
    op.create_index('ix_resource_tags_def_tag_name', 'resource_tags_def', ['tag_name'])


    # Create resources table
    op.create_table(
        'resources',
        sa.Column('res_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('res_name', sa.VARCHAR(128), nullable=False),
        sa.Column('res_type', sa.VARCHAR(32), nullable=False),
        sa.Column('res_pool_id', sa.BigInteger(), nullable=True),
        sa.Column('res_description', sa.VARCHAR(512), nullable=True),
        sa.Column('res_metadata_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('res_sensitive_fields', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('res_capacity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('res_health_status', sa.VARCHAR(32), nullable=False, server_default="'online'"),
        sa.Column('res_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('res_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('res_created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['res_pool_id'], ['resource_pools.pool_id']),
        sa.ForeignKeyConstraint(['res_created_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('res_id')
    )
    op.create_index('ix_resources_res_name', 'resources', ['res_name'])
    op.create_index('ix_resources_res_pool_id', 'resources', ['res_pool_id'])
    op.create_index('ix_resources_pool_name', 'resources', ['res_pool_id', 'res_name'], unique=True)

    # Create resource_tags association table
    op.create_table(
        'resource_tags',
        sa.Column('resource_id', sa.BigInteger(), nullable=False),
        sa.Column('tag_id', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['resource_id'], ['resources.res_id']),
        sa.ForeignKeyConstraint(['tag_id'], ['resource_tags_def.tag_id']),
        sa.PrimaryKeyConstraint('resource_id', 'tag_id')
    )

    # Create pool_permissions association table
    op.create_table(
        'pool_permissions',
        sa.Column('pool_id', sa.BigInteger(), nullable=False),
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('can_view', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('can_checkout', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('can_manage', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['pool_id'], ['resource_pools.pool_id']),
        sa.ForeignKeyConstraint(['role_id'], ['system_roles.role_id']),
        sa.PrimaryKeyConstraint('pool_id', 'role_id')
    )

    # Create ip_pools table
    op.create_table(
        'ip_pools',
        sa.Column('ippool_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ippool_name', sa.VARCHAR(128), nullable=False),
        sa.Column('ippool_cidr', sa.VARCHAR(64), nullable=False),
        sa.Column('ippool_ip_version', sa.VARCHAR(8), nullable=False),
        sa.Column('ippool_network_address', sa.VARCHAR(64), nullable=False),
        sa.Column('ippool_broadcast_address', sa.VARCHAR(64), nullable=True),
        sa.Column('ippool_subnet_mask', sa.VARCHAR(64), nullable=False),
        sa.Column('ippool_gateway', sa.VARCHAR(64), nullable=True),
        sa.Column('ippool_dns_servers', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('ippool_description', sa.VARCHAR(512), nullable=True),
        sa.Column('ippool_reserved_ips', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('ippool_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('ippool_created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['ippool_created_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('ippool_id'),
        sa.UniqueConstraint('ippool_name')
    )
    op.create_index('ix_ip_pools_ippool_name', 'ip_pools', ['ippool_name'])

    # Create ip_allocations table
    op.create_table(
        'ip_allocations',
        sa.Column('ipalloc_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ipalloc_pool_id', sa.BigInteger(), nullable=False),
        sa.Column('ipalloc_ip_address', sa.VARCHAR(64), nullable=False),
        sa.Column('ipalloc_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ipalloc_job_id', sa.VARCHAR(128), nullable=True),
        sa.Column('ipalloc_status', sa.VARCHAR(16), nullable=False, server_default="'active'"),
        sa.Column('ipalloc_checkout_time', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('ipalloc_expected_checkin', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ipalloc_actual_checkin', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ipalloc_reason', sa.VARCHAR(512), nullable=True),
        sa.ForeignKeyConstraint(['ipalloc_pool_id'], ['ip_pools.ippool_id']),
        sa.ForeignKeyConstraint(['ipalloc_user_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('ipalloc_id')
    )
    op.create_index('ix_ip_allocations_ipalloc_pool_id', 'ip_allocations', ['ipalloc_pool_id'])
    op.create_index('ix_ip_allocations_ipalloc_user_id', 'ip_allocations', ['ipalloc_user_id'])
    op.create_index('ix_ip_allocations_pool_ip', 'ip_allocations', ['ipalloc_pool_id', 'ipalloc_ip_address'])
    op.create_index('ix_ip_allocations_pool_status', 'ip_allocations', ['ipalloc_pool_id', 'ipalloc_status'])
    op.create_index('ix_ip_allocations_job', 'ip_allocations', ['ipalloc_job_id'])


    # Create allocations table
    op.create_table(
        'allocations',
        sa.Column('alloc_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('alloc_resource_id', sa.BigInteger(), nullable=False),
        sa.Column('alloc_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('alloc_job_id', sa.VARCHAR(128), nullable=True),
        sa.Column('alloc_mode', sa.VARCHAR(16), nullable=False, server_default="'exclusive'"),
        sa.Column('alloc_status', sa.VARCHAR(16), nullable=False, server_default="'active'"),
        sa.Column('alloc_checkout_time', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('alloc_expected_checkin', sa.DateTime(timezone=True), nullable=True),
        sa.Column('alloc_actual_checkin', sa.DateTime(timezone=True), nullable=True),
        sa.Column('alloc_duration_minutes', sa.Integer(), nullable=True),
        sa.Column('alloc_reason', sa.VARCHAR(512), nullable=True),
        sa.Column('alloc_forced_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('alloc_force_reason', sa.VARCHAR(512), nullable=True),
        sa.Column('alloc_metadata_snapshot', sa.JSON(), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['alloc_resource_id'], ['resources.res_id']),
        sa.ForeignKeyConstraint(['alloc_user_id'], ['user.user_id']),
        sa.ForeignKeyConstraint(['alloc_forced_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('alloc_id')
    )
    op.create_index('ix_allocations_alloc_resource_id', 'allocations', ['alloc_resource_id'])
    op.create_index('ix_allocations_alloc_user_id', 'allocations', ['alloc_user_id'])
    op.create_index('ix_allocations_resource_status', 'allocations', ['alloc_resource_id', 'alloc_status'])
    op.create_index('ix_allocations_user_status', 'allocations', ['alloc_user_id', 'alloc_status'])
    op.create_index('ix_allocations_job', 'allocations', ['alloc_job_id'])

    # Create reservations table
    op.create_table(
        'reservations',
        sa.Column('resv_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('resv_resource_id', sa.BigInteger(), nullable=False),
        sa.Column('resv_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resv_job_id', sa.VARCHAR(128), nullable=True),
        sa.Column('resv_start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resv_end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resv_mode', sa.VARCHAR(16), nullable=False, server_default="'exclusive'"),
        sa.Column('resv_status', sa.VARCHAR(16), nullable=False, server_default="'pending'"),
        sa.Column('resv_reason', sa.VARCHAR(512), nullable=True),
        sa.Column('resv_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('resv_allocation_id', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['resv_resource_id'], ['resources.res_id']),
        sa.ForeignKeyConstraint(['resv_user_id'], ['user.user_id']),
        sa.ForeignKeyConstraint(['resv_allocation_id'], ['allocations.alloc_id']),
        sa.PrimaryKeyConstraint('resv_id')
    )
    op.create_index('ix_reservations_resv_resource_id', 'reservations', ['resv_resource_id'])
    op.create_index('ix_reservations_resv_user_id', 'reservations', ['resv_user_id'])
    op.create_index('ix_reservations_resource_time', 'reservations', ['resv_resource_id', 'resv_start_time', 'resv_end_time'])
    op.create_index('ix_reservations_job', 'reservations', ['resv_job_id'])

    # Create health_check_configs table
    op.create_table(
        'health_check_configs',
        sa.Column('hcc_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('hcc_resource_id', sa.BigInteger(), nullable=False),
        sa.Column('hcc_probe_url', sa.VARCHAR(512), nullable=True),
        sa.Column('hcc_probe_command', sa.VARCHAR(1024), nullable=True),
        sa.Column('hcc_interval_seconds', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('hcc_timeout_seconds', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('hcc_failure_threshold', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('hcc_success_threshold', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('hcc_consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('hcc_consecutive_successes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('hcc_last_check_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hcc_last_check_result', sa.Boolean(), nullable=True),
        sa.Column('hcc_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['hcc_resource_id'], ['resources.res_id']),
        sa.PrimaryKeyConstraint('hcc_id'),
        sa.UniqueConstraint('hcc_resource_id')
    )
    op.create_index('ix_health_check_configs_hcc_resource_id', 'health_check_configs', ['hcc_resource_id'])


    # Create health_transition_logs table
    op.create_table(
        'health_transition_logs',
        sa.Column('htl_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('htl_resource_id', sa.BigInteger(), nullable=False),
        sa.Column('htl_old_status', sa.VARCHAR(32), nullable=False),
        sa.Column('htl_new_status', sa.VARCHAR(32), nullable=False),
        sa.Column('htl_reason', sa.VARCHAR(512), nullable=True),
        sa.Column('htl_triggered_by', sa.VARCHAR(32), nullable=False),
        sa.Column('htl_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('htl_timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['htl_resource_id'], ['resources.res_id']),
        sa.ForeignKeyConstraint(['htl_user_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('htl_id')
    )
    op.create_index('ix_health_transition_logs_htl_resource_id', 'health_transition_logs', ['htl_resource_id'])
    op.create_index('ix_health_transition_logs_resource_time', 'health_transition_logs', ['htl_resource_id', 'htl_timestamp'])

    # Create resource_metadata_history table
    op.create_table(
        'resource_metadata_history',
        sa.Column('rmh_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('rmh_resource_id', sa.BigInteger(), nullable=False),
        sa.Column('rmh_old_metadata_json', sa.JSON(), nullable=True),
        sa.Column('rmh_new_metadata_json', sa.JSON(), nullable=True),
        sa.Column('rmh_changed_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('rmh_changed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['rmh_resource_id'], ['resources.res_id']),
        sa.ForeignKeyConstraint(['rmh_changed_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('rmh_id')
    )
    op.create_index('ix_resource_metadata_history_rmh_resource_id', 'resource_metadata_history', ['rmh_resource_id'])
    op.create_index('ix_resource_metadata_history_resource_time', 'resource_metadata_history', ['rmh_resource_id', 'rmh_changed_at'])

    # Seed default resource pool
    _seed_default_resource_pool()

    # Seed resource management permissions
    _seed_resource_permissions()


def _seed_default_resource_pool():
    """
        Insert default resource pool for unassigned resources.
    """
    pools_table = sa.table(
        'resource_pools',
        sa.column('pool_name', sa.VARCHAR(128)),
        sa.column('pool_description', sa.VARCHAR(512)),
        sa.column('pool_is_default', sa.Boolean())
    )

    default_pool = {
        'pool_name': 'default',
        'pool_description': 'Default pool for unassigned resources',
        'pool_is_default': True
    }

    op.bulk_insert(pools_table, [default_pool])

    # Grant Administrator role full access to default pool
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO pool_permissions (pool_id, role_id, can_view, can_checkout, can_manage)
        SELECT p.pool_id, r.role_id, true, true, true
        FROM resource_pools p, system_roles r
        WHERE p.pool_name = 'default' AND r.role_name = 'Administrator'
    """))

    # Grant Operator role checkout access to default pool
    connection.execute(sa.text("""
        INSERT INTO pool_permissions (pool_id, role_id, can_view, can_checkout, can_manage)
        SELECT p.pool_id, r.role_id, true, true, false
        FROM resource_pools p, system_roles r
        WHERE p.pool_name = 'default' AND r.role_name = 'Operator'
    """))

    # Grant Viewer role view access to default pool
    connection.execute(sa.text("""
        INSERT INTO pool_permissions (pool_id, role_id, can_view, can_checkout, can_manage)
        SELECT p.pool_id, r.role_id, true, false, false
        FROM resource_pools p, system_roles r
        WHERE p.pool_name = 'default' AND r.role_name = 'Viewer'
    """))


def _seed_resource_permissions():
    """
        Insert resource management permissions.
    """
    permissions_table = sa.table(
        'permissions',
        sa.column('perm_name', sa.VARCHAR(64)),
        sa.column('perm_description', sa.VARCHAR(255))
    )

    resource_permissions = [
        # Resource management permissions
        {'perm_name': 'resources.create', 'perm_description': 'Create new resources'},
        {'perm_name': 'resources.read', 'perm_description': 'View resource information'},
        {'perm_name': 'resources.update', 'perm_description': 'Update resource information'},
        {'perm_name': 'resources.delete', 'perm_description': 'Delete resources'},
        {'perm_name': 'resources.checkout', 'perm_description': 'Checkout resources'},
        {'perm_name': 'resources.checkin', 'perm_description': 'Checkin resources'},
        {'perm_name': 'resources.force_checkin', 'perm_description': 'Force checkin of resources'},
        # Pool management permissions
        {'perm_name': 'pools.create', 'perm_description': 'Create resource pools'},
        {'perm_name': 'pools.read', 'perm_description': 'View resource pools'},
        {'perm_name': 'pools.update', 'perm_description': 'Update resource pools'},
        {'perm_name': 'pools.delete', 'perm_description': 'Delete resource pools'},
        # IP pool management permissions
        {'perm_name': 'ip_pools.create', 'perm_description': 'Create IP address pools'},
        {'perm_name': 'ip_pools.read', 'perm_description': 'View IP address pools'},
        {'perm_name': 'ip_pools.update', 'perm_description': 'Update IP address pools'},
        {'perm_name': 'ip_pools.delete', 'perm_description': 'Delete IP address pools'},
        {'perm_name': 'ip_pools.checkout', 'perm_description': 'Checkout IP addresses'},
        {'perm_name': 'ip_pools.checkin', 'perm_description': 'Checkin IP addresses'},
        # Reservation management permissions
        {'perm_name': 'reservations.create', 'perm_description': 'Create resource reservations'},
        {'perm_name': 'reservations.read', 'perm_description': 'View resource reservations'},
        {'perm_name': 'reservations.update', 'perm_description': 'Update resource reservations'},
        {'perm_name': 'reservations.delete', 'perm_description': 'Cancel resource reservations'},
        # Health management permissions
        {'perm_name': 'health.read', 'perm_description': 'View resource health status'},
        {'perm_name': 'health.update', 'perm_description': 'Update resource health status'},
        {'perm_name': 'health.configure', 'perm_description': 'Configure health checks'},
    ]

    op.bulk_insert(permissions_table, resource_permissions)

    # Assign resource permissions to Administrator role
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.perm_id
        FROM system_roles r, permissions p
        WHERE r.role_name = 'Administrator'
        AND p.perm_name IN (
            'resources.create', 'resources.read', 'resources.update', 'resources.delete',
            'resources.checkout', 'resources.checkin', 'resources.force_checkin',
            'pools.create', 'pools.read', 'pools.update', 'pools.delete',
            'ip_pools.create', 'ip_pools.read', 'ip_pools.update', 'ip_pools.delete',
            'ip_pools.checkout', 'ip_pools.checkin',
            'reservations.create', 'reservations.read', 'reservations.update', 'reservations.delete',
            'health.read', 'health.update', 'health.configure'
        )
    """))

    # Assign operational permissions to Operator role
    connection.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.perm_id
        FROM system_roles r, permissions p
        WHERE r.role_name = 'Operator'
        AND p.perm_name IN (
            'resources.read', 'resources.checkout', 'resources.checkin',
            'pools.read',
            'ip_pools.read', 'ip_pools.checkout', 'ip_pools.checkin',
            'reservations.create', 'reservations.read', 'reservations.update', 'reservations.delete',
            'health.read'
        )
    """))

    # Assign read-only permissions to Viewer role
    connection.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.perm_id
        FROM system_roles r, permissions p
        WHERE r.role_name = 'Viewer'
        AND p.perm_name IN (
            'resources.read', 'pools.read', 'ip_pools.read',
            'reservations.read', 'health.read'
        )
    """))


def downgrade():
    """
        Drop all resource management tables.
    """
    op.drop_table('resource_metadata_history')
    op.drop_table('health_transition_logs')
    op.drop_table('health_check_configs')
    op.drop_table('reservations')
    op.drop_table('allocations')
    op.drop_table('ip_allocations')
    op.drop_table('ip_pools')
    op.drop_table('pool_permissions')
    op.drop_table('resource_tags')
    op.drop_table('resources')
    op.drop_table('resource_tags_def')
    op.drop_table('resource_pools')

    # Remove resource management permissions
    connection = op.get_bind()
    connection.execute(sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT perm_id FROM permissions
            WHERE perm_name LIKE 'resources.%'
            OR perm_name LIKE 'pools.%'
            OR perm_name LIKE 'ip_pools.%'
            OR perm_name LIKE 'reservations.%'
            OR perm_name LIKE 'health.%'
        )
    """))
    connection.execute(sa.text("""
        DELETE FROM permissions
        WHERE perm_name LIKE 'resources.%'
        OR perm_name LIKE 'pools.%'
        OR perm_name LIKE 'ip_pools.%'
        OR perm_name LIKE 'reservations.%'
        OR perm_name LIKE 'health.%'
    """))
