"""
.. module:: test_infrastructure_manager_spec_versioning
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for InfrastructureManager specification versioning

.. moduleauthor:: Code Craft AI LLC

Tests for infrastructure specification versioning in the InfrastructureManager.

**Feature: projects**
**Property 6: Specification Versioning**
**Validates: Requirements 6.1, 6.2**
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
    InfraSpecCreateRequest,
    InfraSpecUpdateRequest,
    InfraProvider,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_spec_name():
    """Generate a unique infrastructure specification name for testing."""
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


def create_mock_session_for_spec_update(existing_spec, project=None):
    """
    Create a mock session that simulates finding an existing spec for update.
    
    Query flow for update_spec:
    1. Query ProjectInfraSpec to find the spec
    2. (Optional) Query ProjectInfraSpec to check for duplicate name
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
    **Validates: Requirements 6.2**
    
    For any infrastructure specification, updating the specification increments the version
    number by exactly 1.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    initial_version = 1
    
    # Create mock existing spec
    existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name, version=initial_version)
    
    # Create mock session
    mock_session = create_mock_session_for_spec_update(existing_spec)
    
    manager = InfrastructureManager(mock_session)
    
    # Update the spec
    request = InfraSpecUpdateRequest(
        description='Updated description'
    )
    
    result = manager.update_spec(spec_id, request, 'user-1')
    
    # Verify version was incremented by exactly 1
    assert result.version == initial_version + 1, \
        f"Version should be {initial_version + 1}, got {result.version}"


def test_multiple_updates_increment_version_sequentially():
    """
    **Feature: projects, Property 6: Specification Versioning**
    **Validates: Requirements 6.2**
    
    For any infrastructure specification, multiple updates should increment the version
    sequentially (1 -> 2 -> 3 -> ...).
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    
    # Track version through multiple updates
    current_version = 1
    
    for i in range(5):
        # Create mock spec with current version
        existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name, version=current_version)
        
        # Create mock session
        mock_session = create_mock_session_for_spec_update(existing_spec)
        
        manager = InfrastructureManager(mock_session)
        
        # Update the spec
        request = InfraSpecUpdateRequest(
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
    **Validates: Requirements 6.2**
    
    Property test: For any randomly generated initial version, updating the
    specification should increment the version by exactly 1.
    """
    for _ in range(100):
        spec_name = generate_unique_spec_name()
        project_id = random.randint(1, 100)
        spec_id = random.randint(1, 1000)
        initial_version = random.randint(1, 1000)
        
        # Create mock spec with random initial version
        existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name, version=initial_version)
        
        # Create mock session
        mock_session = create_mock_session_for_spec_update(existing_spec)
        
        manager = InfrastructureManager(mock_session)
        
        # Update the spec
        request = InfraSpecUpdateRequest(
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
    **Validates: Requirements 6.2**
    
    For any infrastructure specification, updating any field should increment the version
    by exactly 1.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    initial_version = 5
    
    # Test different update fields
    update_requests = [
        InfraSpecUpdateRequest(description='New description'),
        InfraSpecUpdateRequest(provider=InfraProvider.KUBERNETES),
        InfraSpecUpdateRequest(timeout_minutes=120),
        InfraSpecUpdateRequest(resources=[{'name': 'test', 'type': 'vm', 'provider_config': {}}]),
        InfraSpecUpdateRequest(variables={'KEY': 'value'}),
    ]
    
    for request in update_requests:
        # Create mock spec
        existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name, version=initial_version)
        
        # Create mock session
        mock_session = create_mock_session_for_spec_update(existing_spec)
        
        manager = InfrastructureManager(mock_session)
        
        result = manager.update_spec(spec_id, request, 'user-1')
        
        # Verify version was incremented by exactly 1
        expected_version = initial_version + 1
        assert result.version == expected_version, \
            f"Version should be {expected_version} after update, got {result.version}"


def test_version_is_preserved_on_read():
    """
    **Feature: projects, Property 6: Specification Versioning**
    **Validates: Requirements 6.1, 6.2**
    
    For any infrastructure specification, reading the specification should return the
    current version without modification.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    spec_id = 1
    version = 42
    
    # Create mock spec with specific version
    existing_spec = create_mock_infra_spec(spec_id, project_id, spec_name, version=version)
    
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
    
    manager = InfrastructureManager(mock_session)
    
    result = manager.get_spec(spec_id)
    
    # Verify version is unchanged
    assert result.version == version, \
        f"Version should be {version} on read, got {result.version}"


def test_version_starts_at_one_for_new_specs():
    """
    **Feature: projects, Property 6: Specification Versioning**
    **Validates: Requirements 6.1**
    
    For any newly created infrastructure specification, the initial version should be 1.
    """
    spec_name = generate_unique_spec_name()
    project_id = 1
    
    # Create mock project
    mock_project = create_mock_project(project_id)
    
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
        # Second call: check for duplicate name
        elif call_count[0] == 2:
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
    
    manager = InfrastructureManager(mock_session)
    
    request = InfraSpecCreateRequest(
        name=spec_name,
        provider=InfraProvider.DOCKER,
        resources=[],
        variables={},
        timeout_minutes=30,
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

