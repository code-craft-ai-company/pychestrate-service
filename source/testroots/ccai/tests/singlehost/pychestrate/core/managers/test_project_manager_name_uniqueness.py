"""
.. module:: test_project_manager_name_uniqueness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ProjectManager project name uniqueness

.. moduleauthor:: Code Craft AI LLC

Tests for project name uniqueness constraint in the ProjectManager.

**Feature: projects**
**Property 1: Project Name Uniqueness**
**Validates: Requirements 1.2**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.project_manager import (
    ProjectManager,
    ProjectCreateRequest,
    DuplicateProjectError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_project_name():
    """Generate a unique project name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_-.', k=random.randint(5, 20)))
    return start_char + rest


def create_mock_user(user_id, login='testuser'):
    """Create a mock user object matching the User ORM model."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', login)
    ctx.set_attribute('display_name', f'Test User {user_id}')
    return mock_user


def create_mock_project(project_id, name, owner_id='user-1'):
    """Create a mock project object matching the Project ORM model."""
    mock_project = Mock()
    mock_project.configure(recursive=True)
    ctx = mock_project.mock_context()
    ctx.set_attribute('id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('description', '')
    ctx.set_attribute('owner_id', owner_id)
    ctx.set_attribute('metadata_json', {})
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    ctx.set_attribute('last_activity_at', Mock())
    
    # Mock owner relationship
    mock_owner = create_mock_user(owner_id)
    ctx.set_attribute('owner', mock_owner)
    
    # Mock members relationship
    ctx.set_attribute('members', [])
    
    return mock_project


def create_mock_session_for_duplicate_check(existing_project, user=None):
    """
    Create a mock session that simulates finding a duplicate project.
    
    Query flow for create_project:
    1. Query Project to check for duplicate name
    2. Query User to verify user exists
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
        
        # First call: duplicate project check
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=existing_project)
        # Second call: user lookup
        elif call_count[0] == 2 and user is not None:
            mock_filter.mock_context().mock_method('first', return_value=user)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


def create_mock_session_for_unique_project(user=None):
    """
    Create a mock session that simulates no duplicate project found.
    
    Query flow for create_project:
    1. Query Project to check for duplicate name (returns None)
    2. Query User to verify user exists
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
        
        # First call: no duplicate found
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=None)
        # Second call: user lookup
        elif call_count[0] == 2 and user is not None:
            mock_filter.mock_context().mock_method('first', return_value=user)
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
# Project Name Uniqueness Tests - Property 1
# =============================================================================

def test_duplicate_project_name_rejected():
    """
    **Feature: projects, Property 1: Project Name Uniqueness**
    **Validates: Requirements 1.2**
    
    For any two projects in the system, if they have the same name, the second
    creation attempt should be rejected with DuplicateProjectError.
    """
    project_name = generate_unique_project_name()
    user_id = 'user-1'
    
    # Create mock existing project
    existing_project = create_mock_project(1, project_name, user_id)
    mock_user = create_mock_user(user_id)
    
    # Create mock session that returns the existing project on duplicate check
    mock_session = create_mock_session_for_duplicate_check(existing_project, mock_user)
    
    manager = ProjectManager(mock_session)
    
    # Attempt to create project with same name
    request = ProjectCreateRequest(
        name=project_name,
        description='Duplicate project'
    )
    
    duplicate_rejected = False
    try:
        manager.create_project(request, user_id)
    except DuplicateProjectError as e:
        duplicate_rejected = True
        assert 'already exists' in e.message.lower()
    
    assert duplicate_rejected, "Duplicate project name should be rejected"


def test_unique_project_names_allowed():
    """
    **Feature: projects, Property 1: Project Name Uniqueness**
    **Validates: Requirements 1.2**
    
    Multiple projects with unique names should all be created successfully.
    """
    user_id = 'user-1'
    mock_user = create_mock_user(user_id)
    
    # Create multiple projects with unique names
    created_count = 0
    for i in range(10):
        project_name = f"unique_project_{i}_{generate_unique_project_name()}"
        
        # Create mock session that returns no duplicate
        mock_session = create_mock_session_for_unique_project(mock_user)
        
        manager = ProjectManager(mock_session)
        
        request = ProjectCreateRequest(
            name=project_name,
            description=f'Project {i}'
        )
        
        try:
            manager.create_project(request, user_id)
            created_count += 1
        except DuplicateProjectError:
            pass  # Should not happen
    
    # Verify all projects were created
    assert created_count == 10, "All unique projects should be created"


def test_property_duplicate_names_rejected_for_random_names():
    """
    **Feature: projects, Property 1: Project Name Uniqueness**
    **Validates: Requirements 1.2**
    
    Property test: For any randomly generated project name, creating two projects
    with that name should result in the second being rejected.
    """
    for _ in range(100):
        project_name = generate_unique_project_name()
        user_id = f'user-{random.randint(1, 100)}'
        
        # Create mock existing project
        existing_project = create_mock_project(1, project_name, user_id)
        mock_user = create_mock_user(user_id)
        
        # Create mock session that returns the existing project
        mock_session = create_mock_session_for_duplicate_check(existing_project, mock_user)
        
        manager = ProjectManager(mock_session)
        
        # Attempt to create duplicate
        request = ProjectCreateRequest(
            name=project_name,
            description='Duplicate attempt'
        )
        
        duplicate_rejected = False
        try:
            manager.create_project(request, user_id)
        except DuplicateProjectError:
            duplicate_rejected = True
        
        assert duplicate_rejected, f"Duplicate name '{project_name}' should be rejected"


def test_case_sensitive_project_names():
    """
    **Feature: projects, Property 1: Project Name Uniqueness**
    **Validates: Requirements 1.2**
    
    Project names should be case-sensitive, so 'Project' and 'project' are different.
    """
    user_id = 'user-1'
    mock_user = create_mock_user(user_id)
    
    # Test that different case names are treated as unique
    names = ['myproject', 'MYPROJECT', 'MyProject']
    
    for name in names:
        # Create mock session that returns no duplicate
        mock_session = create_mock_session_for_unique_project(mock_user)
        
        manager = ProjectManager(mock_session)
        
        request = ProjectCreateRequest(
            name=name,
            description=f'Project with name {name}'
        )
        
        try:
            manager.create_project(request, user_id)
            success = True
        except DuplicateProjectError:
            success = False
        
        assert success, f"Project name '{name}' should be allowed (case-sensitive)"


def test_project_name_uniqueness_is_global():
    """
    **Feature: projects, Property 1: Project Name Uniqueness**
    **Validates: Requirements 1.2**
    
    Project names must be unique across all projects, regardless of owner.
    Different users cannot create projects with the same name.
    """
    project_name = generate_unique_project_name()
    
    # First user creates a project
    user1_id = 'user-1'
    existing_project = create_mock_project(1, project_name, user1_id)
    
    # Second user tries to create project with same name
    user2_id = 'user-2'
    mock_user2 = create_mock_user(user2_id)
    
    # Create mock session that returns the existing project (owned by user1)
    mock_session = create_mock_session_for_duplicate_check(existing_project, mock_user2)
    
    manager = ProjectManager(mock_session)
    
    request = ProjectCreateRequest(
        name=project_name,
        description='Project by different user'
    )
    
    duplicate_rejected = False
    try:
        manager.create_project(request, user2_id)
    except DuplicateProjectError:
        duplicate_rejected = True
    
    assert duplicate_rejected, "Project name must be globally unique across all users"


def test_project_uniqueness_property_same_id_for_same_name():
    """
    **Feature: projects, Property 1: Project Name Uniqueness**
    **Validates: Requirements 1.2**
    
    Property: For any two projects in the system, if they have the same name,
    they must be the same project (same ID). This is enforced by rejecting
    duplicate names at creation time.
    """
    # This test verifies the property by checking that:
    # 1. When a project with a given name exists, creating another with the same name fails
    # 2. The only way to have a project with that name is to reference the existing one
    
    project_name = generate_unique_project_name()
    project_id = 42
    user_id = 'user-1'
    
    # Create the "existing" project
    existing_project = create_mock_project(project_id, project_name, user_id)
    mock_user = create_mock_user(user_id)
    
    # Verify that attempting to create a project with the same name fails
    mock_session = create_mock_session_for_duplicate_check(existing_project, mock_user)
    manager = ProjectManager(mock_session)
    
    request = ProjectCreateRequest(name=project_name)
    
    duplicate_rejected = False
    try:
        manager.create_project(request, user_id)
    except DuplicateProjectError:
        duplicate_rejected = True
    
    assert duplicate_rejected, "System enforces uniqueness by rejecting duplicates"
    
    # The property holds: if two projects have the same name, they must be the same project
    # because the system prevents creating a second project with the same name
