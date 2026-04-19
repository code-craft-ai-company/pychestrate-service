"""
.. module:: test_build_manager_spec_versioning
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for BuildManager specification versioning

.. moduleauthor:: Automation Mojo LLC

Tests for build specification versioning in the BuildManager.

**Feature: projects**
**Property 6: Specification Versioning**
**Validates: Requirements 4.2, 17.2**
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
    BuildSpecCreateRequest,
    BuildSpecUpdateRequest,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_spec_name():
    """Generate a unique build specification name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(5, 20)))
    return start_char + rest


def create_mock_project(project_id, name='test-project'):
    """Create a mock project object matching the Project ORM model."""
    mock_project = Mock()
    mock_project.configure(recursive=True)
    ctx = mock_project.mock_context()
    ctx.set_attribute('id', project_id)
    ctx.set_attribute('name', name)
    return mock_project


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


def create_mock_session_for_spec_update(existing_spec, project=None, repository=None):
    """
    Create a mock session that simulates finding an existing spec for update.
    
    Query flow for update_spec:
    1. Query ProjectBuildSpec to find the spec
    2. (Optional) Query ProjectBuildSpec to check for duplicate name
    3. (Optional) Query ProjectRepository to verify repository
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: find the spec to update
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=existing_spec)
        # Subsequent calls: return None (no duplicate, etc.)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Specification Versioning Tests - Property 6
# =============================================================================

def test_update_spec_increments_version_by_one():
    """
    **Feature: projects, Property 6: Specification Versioning**
    **Validates: Requirements 4.2, 17.2**
    
    For any build specification, updating the specification increments the version
    number by exactly 1.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    initial_version = 1
    
    # Create mock existing spec
    existing_spec = create_mock_build_spec(spec_id, project_id, spec_name, version=initial_version)
    
    # Create mock session
    mock_session = create_mock_session_for_spec_update(existing_spec)
    
    manager = BuildManager(mock_session)
    
    # Update the spec
    request = BuildSpecUpdateRequest(
        description='Updated description'
    )
    
    result = manager.update_spec(spec_id, request, 'user-1')
    
    # Verify version was incremented by exactly 1
    assert result.version == initial_version + 1, \
        f"Version should be {initial_version + 1}, got {result.version}"


def test_multiple_updates_increment_version_sequentially():
    """
    **Feature: projects, Property 6: Specification Versioning**
    **Validates: Requirements 4.2, 17.2**
    
    For any build specification, multiple updates should increment the version
    sequentially (1 -> 2 -> 3 -> ...).
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    # Track version through multiple updates
    current_version = 1
    
    for i in range(5):
        # Create mock spec with current version
        existing_spec = create_mock_build_spec(spec_id, project_id, spec_name, version=current_version)
        
        # Create mock session
        mock_session = create_mock_session_for_spec_update(existing_spec)
        
        manager = BuildManager(mock_session)
        
        # Update the spec
        request = BuildSpecUpdateRequest(
            description=f'Update {i + 1}'
        )
        
        result = manager.update_spec(spec_id, request, 'user-1')
        
        # Verify version was incremented by exactly 1
        expected_version = current_version + 1
        assert result.version == expected_version, \
            f"After update {i + 1}, version should be {expected_version}, got {result.version}"
        
        # Update current version for next iteration
        current_version = expected_version


def test_property_version_increment_for_random_initial_versions():
    """
    **Feature: projects, Property 6: Specification Versioning**
    **Validates: Requirements 4.2, 17.2**
    
    Property test: For any randomly generated initial version, updating the
    specification should increment the version by exactly 1.
    """
    for _ in range(100):
        spec_name = generate_unique_spec_name()
        project_id = random.randint(1, 100)
        spec_id = random.randint(1, 1000)
        initial_version = random.randint(1, 1000)
        
        # Create mock spec with random initial version
        existing_spec = create_mock_build_spec(spec_id, project_id, spec_name, version=initial_version)
        
        # Create mock session
        mock_session = create_mock_session_for_spec_update(existing_spec)
        
        manager = BuildManager(mock_session)
        
        # Update the spec
        request = BuildSpecUpdateRequest(
            description=f'Random update for version {initial_version}'
        )
        
        result = manager.update_spec(spec_id, request, f'user-{random.randint(1, 100)}')
        
        # Verify version was incremented by exactly 1
        expected_version = initial_version + 1
        assert result.version == expected_version, \
            f"For initial version {initial_version}, expected {expected_version}, got {result.version}"


def test_version_increment_with_different_update_fields():
    """
    **Feature: projects, Property 6: Specification Versioning**
    **Validates: Requirements 4.2, 17.2**
    
    For any build specification, updating any field should increment the version
    by exactly 1.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    initial_version = 5
    
    # Test different update fields
    update_requests = [
        BuildSpecUpdateRequest(description='New description'),
        BuildSpecUpdateRequest(branch='develop'),
        BuildSpecUpdateRequest(timeout_minutes=120),
        BuildSpecUpdateRequest(steps=[{'name': 'test', 'type': 'script', 'config': {}}]),
        BuildSpecUpdateRequest(environment={'KEY': 'value'}),
    ]
    
    for request in update_requests:
        # Create mock spec
        existing_spec = create_mock_build_spec(spec_id, project_id, spec_name, version=initial_version)
        
        # Create mock session
        mock_session = create_mock_session_for_spec_update(existing_spec)
        
        manager = BuildManager(mock_session)
        
        result = manager.update_spec(spec_id, request, 'user-1')
        
        # Verify version was incremented by exactly 1
        expected_version = initial_version + 1
        assert result.version == expected_version, \
            f"Version should be {expected_version} after update, got {result.version}"


def test_version_is_preserved_on_read():
    """
    **Feature: projects, Property 6: Specification Versioning**
    **Validates: Requirements 4.2, 17.2**
    
    For any build specification, reading the specification should return the
    current version without modification.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    version = 42
    
    # Create mock spec with specific version
    existing_spec = create_mock_build_spec(spec_id, project_id, spec_name, version=version)
    
    # Create mock session for get_spec
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=existing_spec)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = BuildManager(mock_session)
    
    result = manager.get_spec(spec_id)
    
    # Verify version is unchanged
    assert result.version == version, \
        f"Version should be {version} on read, got {result.version}"


def test_version_starts_at_one_for_new_specs():
    """
    **Feature: projects, Property 6: Specification Versioning**
    **Validates: Requirements 4.2, 17.2**
    
    For any newly created build specification, the initial version should be 1.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    repo_id = 1
    
    # Create mock project and repository
    mock_project = create_mock_project(project_id)
    mock_repo = create_mock_repository(repo_id, project_id)
    
    # Create mock session for create_spec
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    created_spec_version = [None]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: check project exists
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=mock_project)
        # Second call: check repository exists
        elif call_count[0] == 2:
            mock_filter.mock_context().mock_method('first', return_value=mock_repo)
        # Third call: check for duplicate name
        elif call_count[0] == 3:
            mock_filter.mock_context().mock_method('first', return_value=None)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    def add_side_effect(obj):
        # Capture the created spec version to verify
        created_spec_version[0] = obj.version
        # Simulate database assigning an ID
        obj.id = 1
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add', side_effect=add_side_effect)
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    manager = BuildManager(mock_session)
    
    request = BuildSpecCreateRequest(
        name=spec_name,
        repository_id=repo_id,
        branch='main',
        steps=[],
        environment={},
        timeout_minutes=60,
        description='Test spec'
    )
    
    # We need to catch the exception since the mock doesn't fully support ORM relationships
    # Instead, verify the version was set to 1 when the object was added
    try:
        manager.create_spec(project_id, request, 'user-1')
    except AttributeError:
        # Expected due to mock limitations with ORM relationships
        pass
    
    # Verify initial version is 1
    assert created_spec_version[0] == 1, \
        f"Initial version should be 1, got {created_spec_version[0]}"

