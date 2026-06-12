"""
.. module:: test_project_manager_resource_checkout
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ProjectManager resource checkout authorization

.. moduleauthor:: Code Craft AI LLC

Tests for resource checkout authorization in the ProjectManager.

**Feature: projects**
**Property 5: Resource Checkout Authorization**
**Validates: Requirements 2.6**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.project_manager import ProjectManager


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_name():
    """Generate a unique name for testing."""
    return 'test_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def create_mock_project(project_id, name, owner_id='user-1'):
    """Create a mock project object."""
    mock_project = Mock()
    mock_project.configure(recursive=True)
    ctx = mock_project.mock_context()
    ctx.set_attribute('id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('owner_id', owner_id)
    return mock_project


def create_mock_resource(resource_id, name, pool_id=1):
    """Create a mock resource object."""
    mock_resource = Mock()
    mock_resource.configure(recursive=True)
    ctx = mock_resource.mock_context()
    ctx.set_attribute('id', resource_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('pool_id', pool_id)
    ctx.set_attribute('resource_type', 'device')
    return mock_resource


def create_mock_session_resource_assigned(project_id, resource_id, is_assigned):
    """
    Create a mock session that simulates resource assignment check.
    
    The is_resource_assigned method uses a select query on project_resources table.
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    # Mock the execute method for the select query
    mock_result = Mock()
    mock_result.configure(recursive=True)
    
    if is_assigned:
        # Return a non-None result to indicate assignment exists
        mock_row = Mock()
        mock_row.configure(recursive=True)
        mock_result.mock_context().mock_method('first', return_value=mock_row)
    else:
        # Return None to indicate no assignment
        mock_result.mock_context().mock_method('first', return_value=None)
    
    mock_session.mock_context().mock_method('execute', return_value=mock_result)
    
    return mock_session


# =============================================================================
# Resource Checkout Authorization Tests - Property 5
# =============================================================================

def test_resource_checkout_succeeds_when_assigned():
    """
    **Feature: projects, Property 5: Resource Checkout Authorization**
    **Validates: Requirements 2.6**
    
    For any job attempting to checkout a resource, the checkout succeeds
    only if the resource is assigned to the job's project.
    """
    project_id = 1
    resource_id = 100
    
    # Create mock session where resource IS assigned
    mock_session = create_mock_session_resource_assigned(project_id, resource_id, is_assigned=True)
    
    manager = ProjectManager(mock_session)
    
    # Check if resource is assigned - should return True
    result = manager.is_resource_assigned(project_id, resource_id)
    
    assert result is True, "Resource checkout should succeed when resource is assigned"


def test_resource_checkout_fails_when_not_assigned():
    """
    **Feature: projects, Property 5: Resource Checkout Authorization**
    **Validates: Requirements 2.6**
    
    For any job attempting to checkout a resource, the checkout fails
    if the resource is NOT assigned to the job's project.
    """
    project_id = 1
    resource_id = 100
    
    # Create mock session where resource is NOT assigned
    mock_session = create_mock_session_resource_assigned(project_id, resource_id, is_assigned=False)
    
    manager = ProjectManager(mock_session)
    
    # Check if resource is assigned - should return False
    result = manager.is_resource_assigned(project_id, resource_id)
    
    assert result is False, "Resource checkout should fail when resource is not assigned"


def test_property_resource_checkout_authorization_random_projects():
    """
    **Feature: projects, Property 5: Resource Checkout Authorization**
    **Validates: Requirements 2.6**
    
    Property test: For any randomly generated project and resource combination,
    checkout authorization depends solely on whether the resource is assigned.
    """
    for _ in range(100):
        project_id = random.randint(1, 1000)
        resource_id = random.randint(1, 1000)
        is_assigned = random.choice([True, False])
        
        # Create mock session with the assignment state
        mock_session = create_mock_session_resource_assigned(project_id, resource_id, is_assigned)
        
        manager = ProjectManager(mock_session)
        
        # Check authorization
        result = manager.is_resource_assigned(project_id, resource_id)
        
        # Result should match the assignment state
        assert result == is_assigned, \
            f"Authorization for project {project_id}, resource {resource_id} " \
            f"should be {is_assigned}, got {result}"


def test_resource_checkout_different_projects_different_results():
    """
    **Feature: projects, Property 5: Resource Checkout Authorization**
    **Validates: Requirements 2.6**
    
    A resource assigned to project A should not be accessible from project B.
    """
    resource_id = 100
    project_a_id = 1
    project_b_id = 2
    
    # Resource is assigned to project A
    mock_session_a = create_mock_session_resource_assigned(project_a_id, resource_id, is_assigned=True)
    manager_a = ProjectManager(mock_session_a)
    result_a = manager_a.is_resource_assigned(project_a_id, resource_id)
    
    # Resource is NOT assigned to project B
    mock_session_b = create_mock_session_resource_assigned(project_b_id, resource_id, is_assigned=False)
    manager_b = ProjectManager(mock_session_b)
    result_b = manager_b.is_resource_assigned(project_b_id, resource_id)
    
    assert result_a is True, "Resource should be accessible from project A"
    assert result_b is False, "Resource should NOT be accessible from project B"


def test_resource_checkout_authorization_is_deterministic():
    """
    **Feature: projects, Property 5: Resource Checkout Authorization**
    **Validates: Requirements 2.6**
    
    Property: For any project and resource, calling is_resource_assigned
    multiple times should always return the same result.
    """
    project_id = 1
    resource_id = 100
    
    for is_assigned in [True, False]:
        results = []
        for _ in range(10):
            mock_session = create_mock_session_resource_assigned(project_id, resource_id, is_assigned)
            manager = ProjectManager(mock_session)
            results.append(manager.is_resource_assigned(project_id, resource_id))
        
        assert all(r == results[0] for r in results), \
            f"Authorization check should be deterministic for assigned={is_assigned}"
