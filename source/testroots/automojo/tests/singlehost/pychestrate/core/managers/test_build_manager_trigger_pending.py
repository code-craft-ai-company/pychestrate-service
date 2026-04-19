"""
.. module:: test_build_manager_trigger_pending
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for BuildManager build trigger creates pending record

.. moduleauthor:: Automation Mojo LLC

Tests for build trigger creating pending records in the BuildManager.

**Feature: projects**
**Property 9: Build Trigger Creates Pending Record**
**Validates: Requirements 5.1**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.build_manager import (
    BuildManager,
    BuildTriggerRequest,
    BuildTriggerType,
    JobStatus,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_spec_name():
    """Generate a unique build specification name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(5, 20)))
    return start_char + rest


def create_mock_repository(repo_id, project_id, name='test-repo'):
    """Create a mock repository object matching the ProjectRepository ORM model."""
    mock_repo = Mock()
    mock_repo.configure(recursive=True)
    ctx = mock_repo.mock_context()
    ctx.set_attribute('id', repo_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    return mock_repo


def create_mock_build_spec(spec_id, project_id, name, version=1, repository=None):
    """Create a mock build specification object matching the ProjectBuildSpec ORM model."""
    mock_spec = Mock()
    mock_spec.configure(recursive=True)
    ctx = mock_spec.mock_context()
    ctx.set_attribute('id', spec_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('repository_id', 1)
    ctx.set_attribute('branch', 'main')
    ctx.set_attribute('steps_json', [])
    ctx.set_attribute('environment_json', {})
    ctx.set_attribute('timeout_minutes', 60)
    ctx.set_attribute('description', '')
    ctx.set_attribute('version', version)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    
    # Mock repository relationship
    if repository is None:
        repository = create_mock_repository(1, project_id)
    ctx.set_attribute('repository', repository)
    
    return mock_spec


def create_mock_session_for_trigger_build(spec):
    """
    Create a mock session that simulates finding a spec for build trigger.
    
    Query flow for trigger_build:
    1. Query ProjectBuildSpec to find the spec
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    created_build = [None]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: find the spec
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=spec)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    def add_side_effect(obj):
        # Capture the created build to verify status
        created_build[0] = obj
        # Simulate database assigning an ID
        obj.id = random.randint(1, 10000)
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add', side_effect=add_side_effect)
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    # Store reference to created_build for test verification
    mock_session._test_created_build = created_build
    
    return mock_session


# =============================================================================
# Build Trigger Creates Pending Record Tests - Property 9
# =============================================================================

def test_trigger_build_creates_pending_status():
    """
    **Feature: projects, Property 9: Build Trigger Creates Pending Record**
    **Validates: Requirements 5.1**
    
    For any valid build trigger request, a build record is created with status "pending".
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    # Create mock spec
    mock_spec = create_mock_build_spec(spec_id, project_id, spec_name)
    
    # Create mock session
    mock_session = create_mock_session_for_trigger_build(mock_spec)
    
    manager = BuildManager(mock_session)
    
    # Trigger a build
    request = BuildTriggerRequest(
        spec_id=spec_id,
        trigger_type=BuildTriggerType.MANUAL
    )
    
    result = manager.trigger_build(request, 'user-1')
    
    # Verify status is pending
    assert result.status == JobStatus.PENDING, \
        f"Build status should be 'pending', got '{result.status}'"


def test_trigger_build_with_different_trigger_types():
    """
    **Feature: projects, Property 9: Build Trigger Creates Pending Record**
    **Validates: Requirements 5.1**
    
    For any trigger type, a build record is created with status "pending".
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    trigger_types = [
        BuildTriggerType.MANUAL,
        BuildTriggerType.WEBHOOK,
        BuildTriggerType.SCHEDULE,
        BuildTriggerType.WATCH,
        BuildTriggerType.API,
    ]
    
    for trigger_type in trigger_types:
        # Create mock spec
        mock_spec = create_mock_build_spec(spec_id, project_id, spec_name)
        
        # Create mock session
        mock_session = create_mock_session_for_trigger_build(mock_spec)
        
        manager = BuildManager(mock_session)
        
        # Trigger a build
        request = BuildTriggerRequest(
            spec_id=spec_id,
            trigger_type=trigger_type
        )
        
        result = manager.trigger_build(request, 'user-1')
        
        # Verify status is pending
        assert result.status == JobStatus.PENDING, \
            f"Build status should be 'pending' for trigger type '{trigger_type}', got '{result.status}'"


def test_property_trigger_build_always_creates_pending():
    """
    **Feature: projects, Property 9: Build Trigger Creates Pending Record**
    **Validates: Requirements 5.1**
    
    Property test: For any randomly generated build trigger request, the build
    record is created with status "pending".
    """
    for _ in range(100):
        spec_name = generate_unique_spec_name()
        project_id = random.randint(1, 100)
        spec_id = random.randint(1, 1000)
        version = random.randint(1, 100)
        
        # Create mock spec
        mock_spec = create_mock_build_spec(spec_id, project_id, spec_name, version=version)
        
        # Create mock session
        mock_session = create_mock_session_for_trigger_build(mock_spec)
        
        manager = BuildManager(mock_session)
        
        # Random trigger type
        trigger_type = random.choice(list(BuildTriggerType))
        
        # Trigger a build
        request = BuildTriggerRequest(
            spec_id=spec_id,
            branch=random.choice([None, 'main', 'develop', 'feature/test']),
            commit_sha=random.choice([None, 'abc123', 'def456']),
            parameters={'key': f'value_{random.randint(1, 100)}'},
            trigger_type=trigger_type
        )
        
        result = manager.trigger_build(request, f'user-{random.randint(1, 100)}')
        
        # Verify status is pending
        assert result.status == JobStatus.PENDING, \
            f"Build status should be 'pending', got '{result.status}'"


def test_trigger_build_uses_spec_version():
    """
    **Feature: projects, Property 9: Build Trigger Creates Pending Record**
    **Validates: Requirements 5.1**
    
    For any build trigger, the build record captures the current spec version.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    spec_version = 42
    
    # Create mock spec with specific version
    mock_spec = create_mock_build_spec(spec_id, project_id, spec_name, version=spec_version)
    
    # Create mock session
    mock_session = create_mock_session_for_trigger_build(mock_spec)
    
    manager = BuildManager(mock_session)
    
    # Trigger a build
    request = BuildTriggerRequest(
        spec_id=spec_id,
        trigger_type=BuildTriggerType.MANUAL
    )
    
    result = manager.trigger_build(request, 'user-1')
    
    # Verify spec version is captured
    assert result.spec_version == spec_version, \
        f"Build spec_version should be {spec_version}, got {result.spec_version}"


def test_trigger_build_uses_spec_branch_by_default():
    """
    **Feature: projects, Property 9: Build Trigger Creates Pending Record**
    **Validates: Requirements 5.1**
    
    For any build trigger without branch override, the build uses the spec's default branch.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    default_branch = 'develop'
    
    # Create mock spec with specific branch
    mock_spec = create_mock_build_spec(spec_id, project_id, spec_name)
    mock_spec.mock_context().set_attribute('branch', default_branch)
    
    # Create mock session
    mock_session = create_mock_session_for_trigger_build(mock_spec)
    
    manager = BuildManager(mock_session)
    
    # Trigger a build without branch override
    request = BuildTriggerRequest(
        spec_id=spec_id,
        branch=None,  # No override
        trigger_type=BuildTriggerType.MANUAL
    )
    
    result = manager.trigger_build(request, 'user-1')
    
    # Verify branch is from spec
    assert result.branch == default_branch, \
        f"Build branch should be '{default_branch}', got '{result.branch}'"


def test_trigger_build_allows_branch_override():
    """
    **Feature: projects, Property 9: Build Trigger Creates Pending Record**
    **Validates: Requirements 5.1**
    
    For any build trigger with branch override, the build uses the override branch.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    override_branch = 'feature/test'
    
    # Create mock spec with default branch
    mock_spec = create_mock_build_spec(spec_id, project_id, spec_name)
    mock_spec.mock_context().set_attribute('branch', 'main')
    
    # Create mock session
    mock_session = create_mock_session_for_trigger_build(mock_spec)
    
    manager = BuildManager(mock_session)
    
    # Trigger a build with branch override
    request = BuildTriggerRequest(
        spec_id=spec_id,
        branch=override_branch,
        trigger_type=BuildTriggerType.MANUAL
    )
    
    result = manager.trigger_build(request, 'user-1')
    
    # Verify branch is overridden
    assert result.branch == override_branch, \
        f"Build branch should be '{override_branch}', got '{result.branch}'"


def test_trigger_build_captures_trigger_type():
    """
    **Feature: projects, Property 9: Build Trigger Creates Pending Record**
    **Validates: Requirements 5.1**
    
    For any build trigger, the build record captures the trigger type.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    for trigger_type in BuildTriggerType:
        # Create mock spec
        mock_spec = create_mock_build_spec(spec_id, project_id, spec_name)
        
        # Create mock session
        mock_session = create_mock_session_for_trigger_build(mock_spec)
        
        manager = BuildManager(mock_session)
        
        # Trigger a build
        request = BuildTriggerRequest(
            spec_id=spec_id,
            trigger_type=trigger_type
        )
        
        result = manager.trigger_build(request, 'user-1')
        
        # Verify trigger type is captured
        assert result.trigger_type == trigger_type, \
            f"Build trigger_type should be '{trigger_type}', got '{result.trigger_type}'"

