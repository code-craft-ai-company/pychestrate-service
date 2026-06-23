"""
Create project management tables

Revision ID: 003_project_management
Revises: 002_resource_management
Create Date: 2026-02-21

This migration creates the following tables for the Project Management module:
- projects: Project definitions
- project_members: Project membership associations
- project_variables: Project-level variables
- project_resources: Association table for project-resource assignments
- project_repositories: Repository associations
- project_build_specs: Build specifications
- project_builds: Build execution records
- project_build_artifacts: Build artifacts
- project_infra_specs: Infrastructure specifications
- project_infra_jobs: Infrastructure job records
- project_test_specs: Test specifications
- project_test_jobs: Test job records
- project_test_results: Test case results
- project_release_pipelines: Release pipeline definitions
- project_pipeline_runs: Pipeline run records
- project_stage_runs: Stage run records
- project_releases: Release records
- project_release_artifacts: Release artifacts
- project_release_channels: Release channels
- project_channel_history: Channel release history
- project_release_schedules: Release schedules
- project_calendar_events: Calendar events base table
- project_release_events: Release calendar events
- project_phase_events: Phase events within releases
- project_release_branches: Branch associations with releases
- project_merge_events: Scheduled merge events
- project_pull_events: Scheduled pull events
- project_watches: Watch configurations
- project_watch_trigger_logs: Watch trigger logs
"""

__author__ = "CodeCraftX"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '003_project_management'
down_revision = '002_resource_management'
branch_labels = None
depends_on = None


def upgrade():
    """
        Create project management tables.
    """
    # Create projects table
    op.create_table(
        'projects',
        sa.Column('proj_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_name', sa.VARCHAR(128), nullable=False),
        sa.Column('proj_description', sa.Text(), nullable=True),
        sa.Column('proj_owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('proj_metadata_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('proj_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('proj_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('proj_last_activity_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_owner_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('proj_id'),
        sa.UniqueConstraint('proj_name')
    )
    op.create_index('ix_projects_proj_name', 'projects', ['proj_name'])
    op.create_index('ix_projects_proj_owner_id', 'projects', ['proj_owner_id'])

    # Create project_members table
    op.create_table(
        'project_members',
        sa.Column('pm_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pm_role', sa.VARCHAR(32), nullable=False),
        sa.Column('pm_joined_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('pm_id'),
        sa.UniqueConstraint('proj_id', 'user_id', name='uq_project_member')
    )
    op.create_index('ix_project_members_proj_id', 'project_members', ['proj_id'])
    op.create_index('ix_project_members_user_id', 'project_members', ['user_id'])
    op.create_index('ix_project_members_project_user', 'project_members', ['proj_id', 'user_id'])

    # Create project_variables table
    op.create_table(
        'project_variables',
        sa.Column('pvar_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('pvar_name', sa.VARCHAR(128), nullable=False),
        sa.Column('pvar_value_json', sa.Text(), nullable=False),
        sa.Column('pvar_type', sa.VARCHAR(16), nullable=False),
        sa.Column('pvar_is_sensitive', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('pvar_description', sa.VARCHAR(512), nullable=True),
        sa.Column('pvar_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pvar_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.PrimaryKeyConstraint('pvar_id'),
        sa.UniqueConstraint('proj_id', 'pvar_name', name='uq_project_variable_name')
    )
    op.create_index('ix_project_variables_proj_id', 'project_variables', ['proj_id'])
    op.create_index('ix_project_variables_project_name', 'project_variables', ['proj_id', 'pvar_name'])

    # Create project_resources association table
    op.create_table(
        'project_resources',
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('res_id', sa.BigInteger(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('assigned_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['res_id'], ['resources.res_id']),
        sa.ForeignKeyConstraint(['assigned_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('proj_id', 'res_id')
    )

    # Create project_repositories table
    op.create_table(
        'project_repositories',
        sa.Column('prepo_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('prepo_name', sa.VARCHAR(128), nullable=False),
        sa.Column('prepo_url', sa.VARCHAR(2048), nullable=False),
        sa.Column('prepo_auth_type', sa.VARCHAR(32), nullable=False),
        sa.Column('prepo_credential_secret_ref', sa.VARCHAR(256), nullable=True),
        sa.Column('prepo_default_branch', sa.VARCHAR(128), nullable=False, server_default='main'),
        sa.Column('prepo_description', sa.VARCHAR(512), nullable=True),
        sa.Column('prepo_last_commit_sha', sa.VARCHAR(64), nullable=True),
        sa.Column('prepo_last_commit_message', sa.VARCHAR(512), nullable=True),
        sa.Column('prepo_last_commit_author', sa.VARCHAR(128), nullable=True),
        sa.Column('prepo_last_commit_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prepo_last_fetch_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prepo_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.PrimaryKeyConstraint('prepo_id'),
        sa.UniqueConstraint('proj_id', 'prepo_name', name='uq_project_repository_name')
    )
    op.create_index('ix_project_repositories_proj_id', 'project_repositories', ['proj_id'])
    op.create_index('ix_project_repositories_project_name', 'project_repositories', ['proj_id', 'prepo_name'])


    # Create project_build_specs table
    op.create_table(
        'project_build_specs',
        sa.Column('pbspec_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('prepo_id', sa.BigInteger(), nullable=False),
        sa.Column('pbspec_name', sa.VARCHAR(128), nullable=False),
        sa.Column('pbspec_branch', sa.VARCHAR(128), nullable=False, server_default='main'),
        sa.Column('pbspec_steps_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('pbspec_environment_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('pbspec_timeout_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('pbspec_description', sa.VARCHAR(512), nullable=True),
        sa.Column('pbspec_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('pbspec_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pbspec_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['prepo_id'], ['project_repositories.prepo_id']),
        sa.PrimaryKeyConstraint('pbspec_id'),
        sa.UniqueConstraint('proj_id', 'pbspec_name', name='uq_project_build_spec_name')
    )
    op.create_index('ix_project_build_specs_proj_id', 'project_build_specs', ['proj_id'])
    op.create_index('ix_project_build_specs_prepo_id', 'project_build_specs', ['prepo_id'])
    op.create_index('ix_project_build_specs_project_name', 'project_build_specs', ['proj_id', 'pbspec_name'])

    # Create project_builds table
    op.create_table(
        'project_builds',
        sa.Column('pbuild_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('pbspec_id', sa.BigInteger(), nullable=False),
        sa.Column('pbuild_spec_version', sa.Integer(), nullable=False),
        sa.Column('pbuild_branch', sa.VARCHAR(128), nullable=False),
        sa.Column('pbuild_commit_sha', sa.VARCHAR(64), nullable=False),
        sa.Column('pbuild_commit_message', sa.VARCHAR(512), nullable=True),
        sa.Column('pbuild_status', sa.VARCHAR(32), nullable=False, server_default='pending'),
        sa.Column('pbuild_trigger_type', sa.VARCHAR(32), nullable=False),
        sa.Column('pbuild_triggered_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pbuild_parameters_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('pbuild_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pbuild_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pbuild_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('pbuild_logs_path', sa.VARCHAR(512), nullable=True),
        sa.Column('pbuild_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['pbspec_id'], ['project_build_specs.pbspec_id']),
        sa.ForeignKeyConstraint(['pbuild_triggered_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('pbuild_id')
    )
    op.create_index('ix_project_builds_proj_id', 'project_builds', ['proj_id'])
    op.create_index('ix_project_builds_pbspec_id', 'project_builds', ['pbspec_id'])
    op.create_index('ix_project_builds_triggered_by_id', 'project_builds', ['pbuild_triggered_by_id'])
    op.create_index('ix_project_builds_project_status', 'project_builds', ['proj_id', 'pbuild_status'])
    op.create_index('ix_project_builds_spec_status', 'project_builds', ['pbspec_id', 'pbuild_status'])

    # Create project_build_artifacts table
    op.create_table(
        'project_build_artifacts',
        sa.Column('pbartifact_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pbuild_id', sa.BigInteger(), nullable=False),
        sa.Column('pbartifact_name', sa.VARCHAR(256), nullable=False),
        sa.Column('pbartifact_path', sa.VARCHAR(512), nullable=False),
        sa.Column('pbartifact_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('pbartifact_checksum', sa.VARCHAR(128), nullable=False),
        sa.Column('pbartifact_checksum_algorithm', sa.VARCHAR(16), nullable=False, server_default='sha256'),
        sa.Column('pbartifact_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['pbuild_id'], ['project_builds.pbuild_id']),
        sa.PrimaryKeyConstraint('pbartifact_id')
    )
    op.create_index('ix_project_build_artifacts_pbuild_id', 'project_build_artifacts', ['pbuild_id'])

    # Create project_infra_specs table
    op.create_table(
        'project_infra_specs',
        sa.Column('pispec_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('pispec_name', sa.VARCHAR(128), nullable=False),
        sa.Column('pispec_provider', sa.VARCHAR(32), nullable=False),
        sa.Column('pispec_resources_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('pispec_variables_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('pispec_timeout_minutes', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('pispec_description', sa.VARCHAR(512), nullable=True),
        sa.Column('pispec_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('pispec_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pispec_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.PrimaryKeyConstraint('pispec_id'),
        sa.UniqueConstraint('proj_id', 'pispec_name', name='uq_project_infra_spec_name')
    )
    op.create_index('ix_project_infra_specs_proj_id', 'project_infra_specs', ['proj_id'])
    op.create_index('ix_project_infra_specs_project_name', 'project_infra_specs', ['proj_id', 'pispec_name'])

    # Create project_infra_jobs table
    op.create_table(
        'project_infra_jobs',
        sa.Column('pijob_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('pispec_id', sa.BigInteger(), nullable=False),
        sa.Column('pijob_spec_version', sa.Integer(), nullable=False),
        sa.Column('pijob_action', sa.VARCHAR(32), nullable=False),
        sa.Column('pijob_state', sa.VARCHAR(32), nullable=False, server_default='pending'),
        sa.Column('pijob_status', sa.VARCHAR(32), nullable=False, server_default='pending'),
        sa.Column('pijob_triggered_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pijob_variables_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('pijob_provisioned_resources_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('pijob_connection_details_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('pijob_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pijob_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pijob_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('pijob_logs_path', sa.VARCHAR(512), nullable=True),
        sa.Column('pijob_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['pispec_id'], ['project_infra_specs.pispec_id']),
        sa.ForeignKeyConstraint(['pijob_triggered_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('pijob_id')
    )
    op.create_index('ix_project_infra_jobs_proj_id', 'project_infra_jobs', ['proj_id'])
    op.create_index('ix_project_infra_jobs_pispec_id', 'project_infra_jobs', ['pispec_id'])
    op.create_index('ix_project_infra_jobs_triggered_by_id', 'project_infra_jobs', ['pijob_triggered_by_id'])
    op.create_index('ix_project_infra_jobs_project_state', 'project_infra_jobs', ['proj_id', 'pijob_state'])
    op.create_index('ix_project_infra_jobs_spec_status', 'project_infra_jobs', ['pispec_id', 'pijob_status'])

    # Create project_test_specs table
    op.create_table(
        'project_test_specs',
        sa.Column('ptspec_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('ptspec_name', sa.VARCHAR(128), nullable=False),
        sa.Column('ptspec_framework', sa.VARCHAR(32), nullable=False),
        sa.Column('ptspec_test_command', sa.VARCHAR(1024), nullable=False),
        sa.Column('ptspec_test_selection', sa.VARCHAR(512), nullable=True),
        sa.Column('ptspec_build_ref', sa.BigInteger(), nullable=True),
        sa.Column('ptspec_infra_ref', sa.BigInteger(), nullable=True),
        sa.Column('ptspec_environment_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('ptspec_timeout_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('ptspec_result_format', sa.VARCHAR(32), nullable=False, server_default='junit_xml'),
        sa.Column('ptspec_description', sa.VARCHAR(512), nullable=True),
        sa.Column('ptspec_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('ptspec_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('ptspec_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['ptspec_build_ref'], ['project_build_specs.pbspec_id']),
        sa.ForeignKeyConstraint(['ptspec_infra_ref'], ['project_infra_specs.pispec_id']),
        sa.PrimaryKeyConstraint('ptspec_id'),
        sa.UniqueConstraint('proj_id', 'ptspec_name', name='uq_project_test_spec_name')
    )
    op.create_index('ix_project_test_specs_proj_id', 'project_test_specs', ['proj_id'])
    op.create_index('ix_project_test_specs_project_name', 'project_test_specs', ['proj_id', 'ptspec_name'])

    # Create project_test_jobs table
    op.create_table(
        'project_test_jobs',
        sa.Column('ptjob_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('ptspec_id', sa.BigInteger(), nullable=False),
        sa.Column('ptjob_spec_version', sa.Integer(), nullable=False),
        sa.Column('ptjob_build_id', sa.BigInteger(), nullable=True),
        sa.Column('ptjob_infra_job_id', sa.BigInteger(), nullable=True),
        sa.Column('ptjob_status', sa.VARCHAR(32), nullable=False, server_default='pending'),
        sa.Column('ptjob_triggered_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ptjob_parameters_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('ptjob_result_summary_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ptjob_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ptjob_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ptjob_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('ptjob_logs_path', sa.VARCHAR(512), nullable=True),
        sa.Column('ptjob_results_path', sa.VARCHAR(512), nullable=True),
        sa.Column('ptjob_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['ptspec_id'], ['project_test_specs.ptspec_id']),
        sa.ForeignKeyConstraint(['ptjob_build_id'], ['project_builds.pbuild_id']),
        sa.ForeignKeyConstraint(['ptjob_infra_job_id'], ['project_infra_jobs.pijob_id']),
        sa.ForeignKeyConstraint(['ptjob_triggered_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('ptjob_id')
    )
    op.create_index('ix_project_test_jobs_proj_id', 'project_test_jobs', ['proj_id'])
    op.create_index('ix_project_test_jobs_ptspec_id', 'project_test_jobs', ['ptspec_id'])
    op.create_index('ix_project_test_jobs_triggered_by_id', 'project_test_jobs', ['ptjob_triggered_by_id'])
    op.create_index('ix_project_test_jobs_project_status', 'project_test_jobs', ['proj_id', 'ptjob_status'])
    op.create_index('ix_project_test_jobs_spec_status', 'project_test_jobs', ['ptspec_id', 'ptjob_status'])

    # Create project_test_results table
    op.create_table(
        'project_test_results',
        sa.Column('ptresult_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ptjob_id', sa.BigInteger(), nullable=False),
        sa.Column('ptresult_name', sa.VARCHAR(512), nullable=False),
        sa.Column('ptresult_classname', sa.VARCHAR(512), nullable=True),
        sa.Column('ptresult_status', sa.VARCHAR(32), nullable=False),
        sa.Column('ptresult_duration_seconds', sa.Float(), nullable=True),
        sa.Column('ptresult_failure_message', sa.Text(), nullable=True),
        sa.Column('ptresult_failure_trace', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['ptjob_id'], ['project_test_jobs.ptjob_id']),
        sa.PrimaryKeyConstraint('ptresult_id')
    )
    op.create_index('ix_project_test_results_ptjob_id', 'project_test_results', ['ptjob_id'])


    # Create project_release_pipelines table
    op.create_table(
        'project_release_pipelines',
        sa.Column('prpipe_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('prpipe_name', sa.VARCHAR(128), nullable=False),
        sa.Column('prpipe_stages_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('prpipe_triggers_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('prpipe_variables_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('prpipe_description', sa.VARCHAR(512), nullable=True),
        sa.Column('prpipe_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('prpipe_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('prpipe_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.PrimaryKeyConstraint('prpipe_id'),
        sa.UniqueConstraint('proj_id', 'prpipe_name', name='uq_project_release_pipeline_name')
    )
    op.create_index('ix_project_release_pipelines_proj_id', 'project_release_pipelines', ['proj_id'])
    op.create_index('ix_project_release_pipelines_project_name', 'project_release_pipelines', ['proj_id', 'prpipe_name'])

    # Create project_release_schedules table (before releases since releases reference it)
    op.create_table(
        'project_release_schedules',
        sa.Column('prsched_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('prsched_name', sa.VARCHAR(128), nullable=False),
        sa.Column('prsched_cron_expression', sa.VARCHAR(128), nullable=False),
        sa.Column('prsched_pipeline_id', sa.BigInteger(), nullable=False),
        sa.Column('prsched_variables_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('prsched_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('prsched_description', sa.VARCHAR(512), nullable=True),
        sa.Column('prsched_last_run_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prsched_next_run_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prsched_run_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('prsched_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('prsched_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['prsched_pipeline_id'], ['project_release_pipelines.prpipe_id']),
        sa.PrimaryKeyConstraint('prsched_id'),
        sa.UniqueConstraint('proj_id', 'prsched_name', name='uq_project_release_schedule_name')
    )
    op.create_index('ix_project_release_schedules_proj_id', 'project_release_schedules', ['proj_id'])
    op.create_index('ix_project_release_schedules_project_name', 'project_release_schedules', ['proj_id', 'prsched_name'])
    op.create_index('ix_project_release_schedules_next_run', 'project_release_schedules', ['prsched_enabled', 'prsched_next_run_time'])

    # Create project_releases table
    op.create_table(
        'project_releases',
        sa.Column('prelease_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('prelease_version', sa.VARCHAR(64), nullable=False),
        sa.Column('prelease_name', sa.VARCHAR(256), nullable=False),
        sa.Column('prelease_description', sa.Text(), nullable=True),
        sa.Column('prelease_status', sa.VARCHAR(32), nullable=False, server_default='draft'),
        sa.Column('prelease_metadata_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('prelease_pipeline_run_id', sa.BigInteger(), nullable=True),
        sa.Column('prelease_schedule_id', sa.BigInteger(), nullable=True),
        sa.Column('prelease_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('prelease_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('prelease_published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prelease_published_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['prelease_schedule_id'], ['project_release_schedules.prsched_id']),
        sa.ForeignKeyConstraint(['prelease_published_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('prelease_id'),
        sa.UniqueConstraint('proj_id', 'prelease_version', name='uq_project_release_version')
    )
    op.create_index('ix_project_releases_proj_id', 'project_releases', ['proj_id'])
    op.create_index('ix_project_releases_project_version', 'project_releases', ['proj_id', 'prelease_version'])
    op.create_index('ix_project_releases_project_status', 'project_releases', ['proj_id', 'prelease_status'])

    # Create project_pipeline_runs table (after releases since it references releases)
    op.create_table(
        'project_pipeline_runs',
        sa.Column('prrun_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('prpipe_id', sa.BigInteger(), nullable=False),
        sa.Column('prrun_pipeline_version', sa.Integer(), nullable=False),
        sa.Column('prrun_status', sa.VARCHAR(32), nullable=False, server_default='pending'),
        sa.Column('prrun_current_stage', sa.VARCHAR(128), nullable=True),
        sa.Column('prrun_trigger_type', sa.VARCHAR(32), nullable=False),
        sa.Column('prrun_triggered_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prrun_variables_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('prrun_release_id', sa.BigInteger(), nullable=True),
        sa.Column('prrun_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prrun_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prrun_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['prpipe_id'], ['project_release_pipelines.prpipe_id']),
        sa.ForeignKeyConstraint(['prrun_triggered_by_id'], ['user.user_id']),
        sa.ForeignKeyConstraint(['prrun_release_id'], ['project_releases.prelease_id']),
        sa.PrimaryKeyConstraint('prrun_id')
    )
    op.create_index('ix_project_pipeline_runs_prpipe_id', 'project_pipeline_runs', ['prpipe_id'])
    op.create_index('ix_project_pipeline_runs_triggered_by_id', 'project_pipeline_runs', ['prrun_triggered_by_id'])
    op.create_index('ix_project_pipeline_runs_pipeline_status', 'project_pipeline_runs', ['prpipe_id', 'prrun_status'])

    # Add foreign key from releases to pipeline_runs
    op.create_foreign_key(
        'fk_project_releases_pipeline_run',
        'project_releases', 'project_pipeline_runs',
        ['prelease_pipeline_run_id'], ['prrun_id']
    )

    # Create project_stage_runs table
    op.create_table(
        'project_stage_runs',
        sa.Column('pstagerun_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('prrun_id', sa.BigInteger(), nullable=False),
        sa.Column('pstagerun_stage_name', sa.VARCHAR(128), nullable=False),
        sa.Column('pstagerun_stage_type', sa.VARCHAR(32), nullable=False),
        sa.Column('pstagerun_status', sa.VARCHAR(32), nullable=False, server_default='pending'),
        sa.Column('pstagerun_requires_approval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('pstagerun_approved_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('pstagerun_approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pstagerun_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pstagerun_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pstagerun_logs_path', sa.VARCHAR(512), nullable=True),
        sa.Column('pstagerun_output_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['prrun_id'], ['project_pipeline_runs.prrun_id']),
        sa.ForeignKeyConstraint(['pstagerun_approved_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('pstagerun_id')
    )
    op.create_index('ix_project_stage_runs_prrun_id', 'project_stage_runs', ['prrun_id'])

    # Create project_release_artifacts table
    op.create_table(
        'project_release_artifacts',
        sa.Column('prartifact_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('prelease_id', sa.BigInteger(), nullable=False),
        sa.Column('prartifact_name', sa.VARCHAR(256), nullable=False),
        sa.Column('prartifact_type', sa.VARCHAR(32), nullable=False),
        sa.Column('prartifact_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('prartifact_checksum', sa.VARCHAR(128), nullable=False),
        sa.Column('prartifact_checksum_algorithm', sa.VARCHAR(16), nullable=False, server_default='sha256'),
        sa.Column('prartifact_storage_path', sa.VARCHAR(512), nullable=False),
        sa.Column('prartifact_signature', sa.Text(), nullable=True),
        sa.Column('prartifact_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['prelease_id'], ['project_releases.prelease_id']),
        sa.PrimaryKeyConstraint('prartifact_id')
    )
    op.create_index('ix_project_release_artifacts_prelease_id', 'project_release_artifacts', ['prelease_id'])

    # Create project_release_channels table
    op.create_table(
        'project_release_channels',
        sa.Column('prchan_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('prchan_name', sa.VARCHAR(64), nullable=False),
        sa.Column('prchan_description', sa.VARCHAR(512), nullable=True),
        sa.Column('prchan_current_release_id', sa.BigInteger(), nullable=True),
        sa.Column('prchan_requires_approval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('prchan_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('prchan_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['prchan_current_release_id'], ['project_releases.prelease_id']),
        sa.PrimaryKeyConstraint('prchan_id'),
        sa.UniqueConstraint('proj_id', 'prchan_name', name='uq_project_release_channel_name')
    )
    op.create_index('ix_project_release_channels_proj_id', 'project_release_channels', ['proj_id'])
    op.create_index('ix_project_release_channels_project_name', 'project_release_channels', ['proj_id', 'prchan_name'])

    # Create project_channel_history table
    op.create_table(
        'project_channel_history',
        sa.Column('pchanhist_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('prchan_id', sa.BigInteger(), nullable=False),
        sa.Column('prelease_id', sa.BigInteger(), nullable=False),
        sa.Column('pchanhist_published_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pchanhist_published_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['prchan_id'], ['project_release_channels.prchan_id']),
        sa.ForeignKeyConstraint(['prelease_id'], ['project_releases.prelease_id']),
        sa.ForeignKeyConstraint(['pchanhist_published_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('pchanhist_id')
    )
    op.create_index('ix_project_channel_history_prchan_id', 'project_channel_history', ['prchan_id'])
    op.create_index('ix_project_channel_history_prelease_id', 'project_channel_history', ['prelease_id'])


    # Create project_calendar_events table
    op.create_table(
        'project_calendar_events',
        sa.Column('pcalevent_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('pcalevent_event_type', sa.VARCHAR(32), nullable=False),
        sa.Column('pcalevent_name', sa.VARCHAR(256), nullable=False),
        sa.Column('pcalevent_description', sa.Text(), nullable=True),
        sa.Column('pcalevent_start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('pcalevent_end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('pcalevent_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pcalevent_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.PrimaryKeyConstraint('pcalevent_id')
    )
    op.create_index('ix_project_calendar_events_proj_id', 'project_calendar_events', ['proj_id'])
    op.create_index('ix_project_calendar_events_project_time', 'project_calendar_events', ['proj_id', 'pcalevent_start_time', 'pcalevent_end_time'])
    op.create_index('ix_project_calendar_events_type', 'project_calendar_events', ['pcalevent_event_type'])

    # Create project_release_events table
    op.create_table(
        'project_release_events',
        sa.Column('prelevent_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('prelease_id', sa.BigInteger(), nullable=False),
        sa.Column('prelevent_name', sa.VARCHAR(256), nullable=False),
        sa.Column('prelevent_description', sa.Text(), nullable=True),
        sa.Column('prelevent_start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('prelevent_end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('prelevent_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('prelevent_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['prelease_id'], ['project_releases.prelease_id']),
        sa.PrimaryKeyConstraint('prelevent_id')
    )
    op.create_index('ix_project_release_events_proj_id', 'project_release_events', ['proj_id'])
    op.create_index('ix_project_release_events_prelease_id', 'project_release_events', ['prelease_id'])
    op.create_index('ix_project_release_events_project_time', 'project_release_events', ['proj_id', 'prelevent_start_time', 'prelevent_end_time'])

    # Create project_phase_events table
    op.create_table(
        'project_phase_events',
        sa.Column('pphase_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('prelevent_id', sa.BigInteger(), nullable=False),
        sa.Column('pphase_name', sa.VARCHAR(256), nullable=False),
        sa.Column('pphase_description', sa.Text(), nullable=True),
        sa.Column('pphase_start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('pphase_end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('pphase_order', sa.Integer(), nullable=False),
        sa.Column('pphase_status', sa.VARCHAR(32), nullable=False, server_default='planned'),
        sa.Column('pphase_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pphase_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['prelevent_id'], ['project_release_events.prelevent_id']),
        sa.PrimaryKeyConstraint('pphase_id')
    )
    op.create_index('ix_project_phase_events_prelevent_id', 'project_phase_events', ['prelevent_id'])
    op.create_index('ix_project_phase_events_release_order', 'project_phase_events', ['prelevent_id', 'pphase_order'])

    # Create project_release_branches table
    op.create_table(
        'project_release_branches',
        sa.Column('prelbranch_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('prelease_id', sa.BigInteger(), nullable=False),
        sa.Column('prepo_id', sa.BigInteger(), nullable=False),
        sa.Column('prelbranch_branch_name', sa.VARCHAR(256), nullable=False),
        sa.Column('prelbranch_description', sa.Text(), nullable=True),
        sa.Column('prelbranch_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['prelease_id'], ['project_releases.prelease_id']),
        sa.ForeignKeyConstraint(['prepo_id'], ['project_repositories.prepo_id']),
        sa.PrimaryKeyConstraint('prelbranch_id'),
        sa.UniqueConstraint('prelease_id', 'prepo_id', 'prelbranch_branch_name', name='uq_project_release_branch')
    )
    op.create_index('ix_project_release_branches_prelease_id', 'project_release_branches', ['prelease_id'])
    op.create_index('ix_project_release_branches_prepo_id', 'project_release_branches', ['prepo_id'])
    op.create_index('ix_project_release_branches_release_repo', 'project_release_branches', ['prelease_id', 'prepo_id'])

    # Create project_merge_events table
    op.create_table(
        'project_merge_events',
        sa.Column('pmerge_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('prelease_id', sa.BigInteger(), nullable=False),
        sa.Column('prepo_id', sa.BigInteger(), nullable=False),
        sa.Column('pmerge_source_branch', sa.VARCHAR(256), nullable=False),
        sa.Column('pmerge_target_branch', sa.VARCHAR(256), nullable=False),
        sa.Column('pmerge_name', sa.VARCHAR(256), nullable=False),
        sa.Column('pmerge_description', sa.Text(), nullable=True),
        sa.Column('pmerge_scheduled_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('pmerge_status', sa.VARCHAR(32), nullable=False, server_default='scheduled'),
        sa.Column('pmerge_executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pmerge_executed_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('pmerge_error_message', sa.Text(), nullable=True),
        sa.Column('pmerge_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pmerge_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['prelease_id'], ['project_releases.prelease_id']),
        sa.ForeignKeyConstraint(['prepo_id'], ['project_repositories.prepo_id']),
        sa.ForeignKeyConstraint(['pmerge_executed_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('pmerge_id')
    )
    op.create_index('ix_project_merge_events_proj_id', 'project_merge_events', ['proj_id'])
    op.create_index('ix_project_merge_events_prelease_id', 'project_merge_events', ['prelease_id'])
    op.create_index('ix_project_merge_events_prepo_id', 'project_merge_events', ['prepo_id'])
    op.create_index('ix_project_merge_events_project_time', 'project_merge_events', ['proj_id', 'pmerge_scheduled_time'])
    op.create_index('ix_project_merge_events_status', 'project_merge_events', ['pmerge_status'])

    # Create project_pull_events table
    op.create_table(
        'project_pull_events',
        sa.Column('ppull_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('prelease_id', sa.BigInteger(), nullable=False),
        sa.Column('prepo_id', sa.BigInteger(), nullable=False),
        sa.Column('ppull_source_branch', sa.VARCHAR(256), nullable=False),
        sa.Column('ppull_target_branch', sa.VARCHAR(256), nullable=False),
        sa.Column('ppull_name', sa.VARCHAR(256), nullable=False),
        sa.Column('ppull_description', sa.Text(), nullable=True),
        sa.Column('ppull_scheduled_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ppull_status', sa.VARCHAR(32), nullable=False, server_default='scheduled'),
        sa.Column('ppull_executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ppull_executed_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ppull_error_message', sa.Text(), nullable=True),
        sa.Column('ppull_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('ppull_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['prelease_id'], ['project_releases.prelease_id']),
        sa.ForeignKeyConstraint(['prepo_id'], ['project_repositories.prepo_id']),
        sa.ForeignKeyConstraint(['ppull_executed_by_id'], ['user.user_id']),
        sa.PrimaryKeyConstraint('ppull_id')
    )
    op.create_index('ix_project_pull_events_proj_id', 'project_pull_events', ['proj_id'])
    op.create_index('ix_project_pull_events_prelease_id', 'project_pull_events', ['prelease_id'])
    op.create_index('ix_project_pull_events_prepo_id', 'project_pull_events', ['prepo_id'])
    op.create_index('ix_project_pull_events_project_time', 'project_pull_events', ['proj_id', 'ppull_scheduled_time'])
    op.create_index('ix_project_pull_events_status', 'project_pull_events', ['ppull_status'])

    # Create project_watches table
    op.create_table(
        'project_watches',
        sa.Column('pwatch_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('proj_id', sa.BigInteger(), nullable=False),
        sa.Column('pwatch_name', sa.VARCHAR(128), nullable=False),
        sa.Column('pwatch_trigger_source', sa.VARCHAR(32), nullable=False),
        sa.Column('pwatch_source_id', sa.BigInteger(), nullable=False),
        sa.Column('prepo_id', sa.BigInteger(), nullable=True),
        sa.Column('pwatch_conditions_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('pwatch_actions_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('pwatch_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('pwatch_description', sa.VARCHAR(512), nullable=True),
        sa.Column('pwatch_last_trigger_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pwatch_trigger_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pwatch_created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pwatch_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['proj_id'], ['projects.proj_id']),
        sa.ForeignKeyConstraint(['prepo_id'], ['project_repositories.prepo_id']),
        sa.PrimaryKeyConstraint('pwatch_id'),
        sa.UniqueConstraint('proj_id', 'pwatch_name', name='uq_project_watch_name')
    )
    op.create_index('ix_project_watches_proj_id', 'project_watches', ['proj_id'])
    op.create_index('ix_project_watches_prepo_id', 'project_watches', ['prepo_id'])
    op.create_index('ix_project_watches_project_name', 'project_watches', ['proj_id', 'pwatch_name'])
    op.create_index('ix_project_watches_source', 'project_watches', ['pwatch_trigger_source', 'pwatch_source_id'])

    # Create project_watch_trigger_logs table
    op.create_table(
        'project_watch_trigger_logs',
        sa.Column('pwatchlog_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pwatch_id', sa.BigInteger(), nullable=False),
        sa.Column('pwatchlog_triggered_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('pwatchlog_trigger_event_json', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('pwatchlog_actions_executed_json', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('pwatchlog_success', sa.Boolean(), nullable=False),
        sa.Column('pwatchlog_error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['pwatch_id'], ['project_watches.pwatch_id']),
        sa.PrimaryKeyConstraint('pwatchlog_id')
    )
    op.create_index('ix_project_watch_trigger_logs_pwatch_id', 'project_watch_trigger_logs', ['pwatch_id'])

    # Seed default project permissions
    _seed_project_permissions()


def _seed_project_permissions():
    """
        Insert default permissions for project management.
    """
    permissions_table = sa.table(
        'permissions',
        sa.column('perm_name', sa.VARCHAR(64)),
        sa.column('perm_description', sa.VARCHAR(255))
    )

    project_permissions = [
        # Project management permissions
        {'perm_name': 'projects.create', 'perm_description': 'Create new projects'},
        {'perm_name': 'projects.read', 'perm_description': 'View project information'},
        {'perm_name': 'projects.update', 'perm_description': 'Update project information'},
        {'perm_name': 'projects.delete', 'perm_description': 'Delete projects'},
        {'perm_name': 'projects.manage_members', 'perm_description': 'Manage project membership'},
        {'perm_name': 'projects.manage_resources', 'perm_description': 'Manage project resource assignments'},
        # Repository permissions
        {'perm_name': 'repositories.create', 'perm_description': 'Add repositories to projects'},
        {'perm_name': 'repositories.read', 'perm_description': 'View repository information'},
        {'perm_name': 'repositories.update', 'perm_description': 'Update repository configuration'},
        {'perm_name': 'repositories.delete', 'perm_description': 'Remove repositories from projects'},
        # Build permissions
        {'perm_name': 'builds.create', 'perm_description': 'Create build specifications'},
        {'perm_name': 'builds.read', 'perm_description': 'View build information'},
        {'perm_name': 'builds.trigger', 'perm_description': 'Trigger builds'},
        {'perm_name': 'builds.cancel', 'perm_description': 'Cancel running builds'},
        # Infrastructure permissions
        {'perm_name': 'infrastructure.create', 'perm_description': 'Create infrastructure specifications'},
        {'perm_name': 'infrastructure.read', 'perm_description': 'View infrastructure information'},
        {'perm_name': 'infrastructure.trigger', 'perm_description': 'Trigger infrastructure jobs'},
        {'perm_name': 'infrastructure.cancel', 'perm_description': 'Cancel running infrastructure jobs'},
        # Test permissions
        {'perm_name': 'tests.create', 'perm_description': 'Create test specifications'},
        {'perm_name': 'tests.read', 'perm_description': 'View test information'},
        {'perm_name': 'tests.trigger', 'perm_description': 'Trigger test jobs'},
        {'perm_name': 'tests.cancel', 'perm_description': 'Cancel running test jobs'},
        # Release permissions
        {'perm_name': 'releases.create', 'perm_description': 'Create releases'},
        {'perm_name': 'releases.read', 'perm_description': 'View release information'},
        {'perm_name': 'releases.update', 'perm_description': 'Update release information'},
        {'perm_name': 'releases.publish', 'perm_description': 'Publish releases to channels'},
        {'perm_name': 'releases.approve', 'perm_description': 'Approve releases and pipeline stages'},
        # Watch permissions
        {'perm_name': 'watches.create', 'perm_description': 'Create watches'},
        {'perm_name': 'watches.read', 'perm_description': 'View watch information'},
        {'perm_name': 'watches.update', 'perm_description': 'Update watch configuration'},
        {'perm_name': 'watches.delete', 'perm_description': 'Delete watches'},
    ]

    op.bulk_insert(permissions_table, project_permissions)

    # Assign project permissions to Administrator role
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.perm_id
        FROM system_roles r, permissions p
        WHERE r.role_name = 'Administrator'
        AND p.perm_name LIKE 'projects.%'
        OR p.perm_name LIKE 'repositories.%'
        OR p.perm_name LIKE 'builds.%'
        OR p.perm_name LIKE 'infrastructure.%'
        OR p.perm_name LIKE 'tests.%'
        OR p.perm_name LIKE 'releases.%'
        OR p.perm_name LIKE 'watches.%'
        AND NOT EXISTS (
            SELECT 1 FROM role_permissions rp
            WHERE rp.role_id = r.role_id AND rp.permission_id = p.perm_id
        )
    """))


def downgrade():
    """
        Drop all project management tables.
    """
    op.drop_table('project_watch_trigger_logs')
    op.drop_table('project_watches')
    op.drop_table('project_pull_events')
    op.drop_table('project_merge_events')
    op.drop_table('project_release_branches')
    op.drop_table('project_phase_events')
    op.drop_table('project_release_events')
    op.drop_table('project_calendar_events')
    op.drop_table('project_channel_history')
    op.drop_table('project_release_channels')
    op.drop_table('project_release_artifacts')
    op.drop_table('project_stage_runs')
    op.drop_constraint('fk_project_releases_pipeline_run', 'project_releases', type_='foreignkey')
    op.drop_table('project_pipeline_runs')
    op.drop_table('project_releases')
    op.drop_table('project_release_schedules')
    op.drop_table('project_release_pipelines')
    op.drop_table('project_test_results')
    op.drop_table('project_test_jobs')
    op.drop_table('project_test_specs')
    op.drop_table('project_infra_jobs')
    op.drop_table('project_infra_specs')
    op.drop_table('project_build_artifacts')
    op.drop_table('project_builds')
    op.drop_table('project_build_specs')
    op.drop_table('project_repositories')
    op.drop_table('project_resources')
    op.drop_table('project_variables')
    op.drop_table('project_members')
    op.drop_table('projects')

    # Remove project permissions
    connection = op.get_bind()
    connection.execute(sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT perm_id FROM permissions
            WHERE perm_name LIKE 'projects.%'
            OR perm_name LIKE 'repositories.%'
            OR perm_name LIKE 'builds.%'
            OR perm_name LIKE 'infrastructure.%'
            OR perm_name LIKE 'tests.%'
            OR perm_name LIKE 'releases.%'
            OR perm_name LIKE 'watches.%'
        )
    """))
    connection.execute(sa.text("""
        DELETE FROM permissions
        WHERE perm_name LIKE 'projects.%'
        OR perm_name LIKE 'repositories.%'
        OR perm_name LIKE 'builds.%'
        OR perm_name LIKE 'infrastructure.%'
        OR perm_name LIKE 'tests.%'
        OR perm_name LIKE 'releases.%'
        OR perm_name LIKE 'watches.%'
    """))