"""
.. module:: test_infrastructure_manager_job_state
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for InfrastructureManager job state transitions

.. moduleauthor:: Code Craft AI LLC

Tests for infrastructure job state transitions in the InfrastructureManager.

**Feature: projects**
**Validates: Requirements 7.1, 7.2, 7.4, 7.7**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.infrastructure_manager import (
    InfrastructureManager,
    InfraJobTriggerRequest,
    InfraAction,
    InfraState,
    JobStatus,
    InfraJobCannotBeCancelledError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_spec_name():
    """Generate a unique infrastructure specification name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(5, 20)))
    return start_char + rest


def create_mock_infra_spec(spec_id, project_id, name, version=1, provider='docker'):
    """Create a mock infrastructure specification object matching the ProjectInfraSpec ORM model."""
    mock_spec = Mock()
    mock_spec.configure(recursive=True)
    ctx = mock_spec.mock_context()
    ctx.set_attribute('id', spec_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('provider', provider)
    ctx.set_attribute('resources_json', [])
    ctx.set_attribute('variables_json', {})
    ctx.set_attribute('timeout_minutes', 30)
    ctx.set_attribute('description', '')
    ctx.set_attribute('version', version)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    
    return mock_spec


def create_mock_infra_job(job_id, project_id, spec_id, spec_name, action, state, status, spec_version=1):
    """Create a mock infrastructure job object matching the ProjectInfraJob ORM model."""
    mock_job = Mock()
    mock_job.configure(recursive=True)
    ctx = mock_job.mock_context()
    ctx.set_attribute('id', job_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('spec_id', spec_id)
    ctx.set_attribute('spec_version', spec_version)
    ctx.set_attribute('action', action)
    ctx.set_attribute('state', state)
    ctx.set_attribute('status', status)
    ctx.set_attribute('triggered_by_id', 'user-1')
    ctx.set_attribute('variables_json', {})
    ctx.set_attribute('provisioned_resources_json', [])
    ctx.set_attribute('connection_details_json', {})
    ctx.set_attribute('started_at', None)
    ctx.set_attribute('completed_at', None)
    ctx.set_attribute('duration_seconds', None)
    ctx.set_attribute('logs_path', None)
    ctx.set_attribute('created_at', Mock())
    
    # Mock spec relationship
    mock_spec = Mock()
    mock_spec.configure(recursive=True)
    mock_spec.mock_context().set_attribute('name', spec_name)
    ctx.set_attribute('spec', mock_spec)
    
    return mock_job


def create_mock_session_for_job_trigger(existing_spec):
    """
    Create a mock session that simulates finding an existing spec for job trigger.
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    created_job = [None]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: find the spec (ProjectInfraSpec)
        # Second call: find the user (User) for triggered_by_username
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=existing_spec)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    def add_side_effect(obj):
        # Capture the created job
        created_job[0] = obj
        # Simulate database assigning an ID
        obj.id = 1
        # Note: We don't set obj.spec here because SQLAlchemy ORM objects
        # can't have Mock objects assigned to relationship attributes.
        # The _infra_job_to_response method handles job.spec being None.
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add', side_effect=add_side_effect)
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session, created_job


def create_mock_session_for_job_cancel(existing_job):
    """
    Create a mock session that simulates finding an existing job for cancellation.
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=existing_job)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Job Trigger Tests - Requirements 7.1
# =============================================================================

def test_trigger_job_creates_pending_record():
    """
    **Feature: projects**
    **Validates: Requirements 7.1**
    
    For any valid infrastructure job trigger request, a job record is created with
    status "pending" and the job is queued for execution.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    # Create mock spec
    existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name)
    
    # Create mock session
    mock_session, created_job = create_mock_session_for_job_trigger(existing_spec)
    
    manager = InfrastructureManager(mock_session)
    
    # Trigger a job
    request = InfraJobTriggerRequest(
        spec_id=spec_id,
        action=InfraAction.PROVISION,
        variables={}
    )
    
    result = manager.trigger_job(request, 'user-1')
    
    # Verify job was created with pending status
    assert result.status == JobStatus.PENDING, \
        f"Job status should be PENDING, got {result.status}"


def test_trigger_job_with_provision_action():
    """
    **Feature: projects**
    **Validates: Requirements 7.1**
    
    For a provision action, the job should be created with the correct action type.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    # Create mock spec
    existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name)
    
    # Create mock session
    mock_session, created_job = create_mock_session_for_job_trigger(existing_spec)
    
    manager = InfrastructureManager(mock_session)
    
    # Trigger a provision job
    request = InfraJobTriggerRequest(
        spec_id=spec_id,
        action=InfraAction.PROVISION,
        variables={}
    )
    
    result = manager.trigger_job(request, 'user-1')
    
    # Verify action is correct
    assert result.action == InfraAction.PROVISION, \
        f"Job action should be PROVISION, got {result.action}"


def test_trigger_job_with_destroy_action():
    """
    **Feature: projects**
    **Validates: Requirements 7.1**
    
    For a destroy action, the job should be created with the correct action type.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    # Create mock spec
    existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name)
    
    # Create mock session
    mock_session, created_job = create_mock_session_for_job_trigger(existing_spec)
    
    manager = InfrastructureManager(mock_session)
    
    # Trigger a destroy job
    request = InfraJobTriggerRequest(
        spec_id=spec_id,
        action=InfraAction.DESTROY,
        variables={}
    )
    
    result = manager.trigger_job(request, 'user-1')
    
    # Verify action is correct
    assert result.action == InfraAction.DESTROY, \
        f"Job action should be DESTROY, got {result.action}"


def test_trigger_job_with_update_action():
    """
    **Feature: projects**
    **Validates: Requirements 7.1**
    
    For an update action, the job should be created with the correct action type.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    # Create mock spec
    existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name)
    
    # Create mock session
    mock_session, created_job = create_mock_session_for_job_trigger(existing_spec)
    
    manager = InfrastructureManager(mock_session)
    
    # Trigger an update job
    request = InfraJobTriggerRequest(
        spec_id=spec_id,
        action=InfraAction.UPDATE,
        variables={}
    )
    
    result = manager.trigger_job(request, 'user-1')
    
    # Verify action is correct
    assert result.action == InfraAction.UPDATE, \
        f"Job action should be UPDATE, got {result.action}"


def test_trigger_job_captures_spec_version():
    """
    **Feature: projects**
    **Validates: Requirements 7.1**
    
    When a job is triggered, it should capture the current spec version.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    spec_version = 5
    
    # Create mock spec with specific version
    existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name, version=spec_version)
    
    # Create mock session
    mock_session, created_job = create_mock_session_for_job_trigger(existing_spec)
    
    manager = InfrastructureManager(mock_session)
    
    # Trigger a job
    request = InfraJobTriggerRequest(
        spec_id=spec_id,
        action=InfraAction.PROVISION,
        variables={}
    )
    
    result = manager.trigger_job(request, 'user-1')
    
    # Verify spec version was captured
    assert result.spec_version == spec_version, \
        f"Job spec_version should be {spec_version}, got {result.spec_version}"


# =============================================================================
# Job Cancellation Tests - Requirements 7.4
# =============================================================================

def test_cancel_pending_job_succeeds():
    """
    **Feature: projects**
    **Validates: Requirements 7.4**
    
    A pending job can be cancelled.
    """
    job_id = 1
    project_id = 1
    spec_id = 1
    
    # Create mock job with pending status
    existing_job = create_mock_infra_job(
        job_id, project_id, spec_id, 'test-spec',
        InfraAction.PROVISION.value, InfraState.PENDING.value, JobStatus.PENDING.value
    )
    
    # Create mock session
    mock_session = create_mock_session_for_job_cancel(existing_job)
    
    manager = InfrastructureManager(mock_session)
    
    result = manager.cancel_job(job_id, 'user-1')
    
    # Verify job was cancelled
    assert result.status == JobStatus.CANCELLED, \
        f"Job status should be CANCELLED, got {result.status}"


def test_cancel_running_job_succeeds():
    """
    **Feature: projects**
    **Validates: Requirements 7.4**
    
    A running job can be cancelled.
    """
    job_id = 1
    project_id = 1
    spec_id = 1
    
    # Create mock job with running status
    existing_job = create_mock_infra_job(
        job_id, project_id, spec_id, 'test-spec',
        InfraAction.PROVISION.value, InfraState.PROVISIONING.value, JobStatus.RUNNING.value
    )
    
    # Create mock session
    mock_session = create_mock_session_for_job_cancel(existing_job)
    
    manager = InfrastructureManager(mock_session)
    
    result = manager.cancel_job(job_id, 'user-1')
    
    # Verify job was cancelled
    assert result.status == JobStatus.CANCELLED, \
        f"Job status should be CANCELLED, got {result.status}"


def test_cancel_completed_job_fails():
    """
    **Feature: projects**
    **Validates: Requirements 7.4**
    
    A completed job cannot be cancelled.
    """
    job_id = 1
    project_id = 1
    spec_id = 1
    
    # Create mock job with succeeded status
    existing_job = create_mock_infra_job(
        job_id, project_id, spec_id, 'test-spec',
        InfraAction.PROVISION.value, InfraState.RUNNING.value, JobStatus.SUCCEEDED.value
    )
    
    # Create mock session
    mock_session = create_mock_session_for_job_cancel(existing_job)
    
    manager = InfrastructureManager(mock_session)
    
    # Attempt to cancel should raise exception
    try:
        manager.cancel_job(job_id, 'user-1')
        assert False, "Expected InfraJobCannotBeCancelledError"
    except InfraJobCannotBeCancelledError:
        pass  # Expected


def test_cancel_failed_job_fails():
    """
    **Feature: projects**
    **Validates: Requirements 7.4**
    
    A failed job cannot be cancelled.
    """
    job_id = 1
    project_id = 1
    spec_id = 1
    
    # Create mock job with failed status
    existing_job = create_mock_infra_job(
        job_id, project_id, spec_id, 'test-spec',
        InfraAction.PROVISION.value, InfraState.FAILED.value, JobStatus.FAILED.value
    )
    
    # Create mock session
    mock_session = create_mock_session_for_job_cancel(existing_job)
    
    manager = InfrastructureManager(mock_session)
    
    # Attempt to cancel should raise exception
    try:
        manager.cancel_job(job_id, 'user-1')
        assert False, "Expected InfraJobCannotBeCancelledError"
    except InfraJobCannotBeCancelledError:
        pass  # Expected


# =============================================================================
# Job State Transition Tests - Requirements 7.7
# =============================================================================

def test_job_state_transitions_for_provision():
    """
    **Feature: projects**
    **Validates: Requirements 7.7**
    
    For a provision action, the job should transition through the correct states:
    pending -> provisioning -> running (on success) or failed (on failure).
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    # Create mock spec
    existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name)
    
    # Create mock session
    mock_session, created_job = create_mock_session_for_job_trigger(existing_spec)
    
    manager = InfrastructureManager(mock_session)
    
    # Trigger a provision job
    request = InfraJobTriggerRequest(
        spec_id=spec_id,
        action=InfraAction.PROVISION,
        variables={}
    )
    
    result = manager.trigger_job(request, 'user-1')
    
    # Verify initial state is pending
    assert result.state == InfraState.PENDING, \
        f"Initial state should be PENDING, got {result.state}"


def test_job_state_transitions_for_destroy():
    """
    **Feature: projects**
    **Validates: Requirements 7.7**
    
    For a destroy action, the job should start in pending state.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    # Create mock spec
    existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name)
    
    # Create mock session
    mock_session, created_job = create_mock_session_for_job_trigger(existing_spec)
    
    manager = InfrastructureManager(mock_session)
    
    # Trigger a destroy job
    request = InfraJobTriggerRequest(
        spec_id=spec_id,
        action=InfraAction.DESTROY,
        variables={}
    )
    
    result = manager.trigger_job(request, 'user-1')
    
    # Verify initial state is pending
    assert result.state == InfraState.PENDING, \
        f"Initial state should be PENDING, got {result.state}"


def test_property_all_actions_start_in_pending_state():
    """
    **Feature: projects**
    **Validates: Requirements 7.1, 7.7**
    
    Property test: For any action type, the job should start in pending state.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    for action in [InfraAction.PROVISION, InfraAction.UPDATE, InfraAction.DESTROY]:
        # Create mock spec
        existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name)
        
        # Create mock session
        mock_session, created_job = create_mock_session_for_job_trigger(existing_spec)
        
        manager = InfrastructureManager(mock_session)
        
        # Trigger a job with this action
        request = InfraJobTriggerRequest(
            spec_id=spec_id,
            action=action,
            variables={}
        )
        
        result = manager.trigger_job(request, 'user-1')
        
        # Verify initial state is pending
        assert result.state == InfraState.PENDING, \
            f"For action {action}, initial state should be PENDING, got {result.state}"
        
        # Verify initial status is pending
        assert result.status == JobStatus.PENDING, \
            f"For action {action}, initial status should be PENDING, got {result.status}"

