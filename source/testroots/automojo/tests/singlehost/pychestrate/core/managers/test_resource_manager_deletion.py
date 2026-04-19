"""
.. module:: test_resource_manager_deletion
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ResourceManager resource deletion constraint

.. moduleauthor:: Automation Mojo LLC

Tests for resource deletion constraint in the ResourceManager.
Resources with active allocations cannot be deleted.

**Feature: resources**
**Property 3: Resource Deletion Constraint**
**Validates: Requirements 1.4**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.orm import AllocationStatus
from automojo.pychestrate.core.managers.resource_manager import (
    ResourceManager,
    ResourceHasAllocationsError,
    ResourceNotFoundError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_name():
    """Generate a unique resource name for testing."""
    return 'resource_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def generate_user_id():
    """Generate a unique user ID for testing."""
    return str(uuid.uuid4())


def create_mock_resource(resource_id, name, pool_id=1, resource_type='device'):
    """Create a mock resource object matching the Resource ORM model."""
    mock_resource = Mock()
    mock_resource.configure(recursive=True)
    ctx = mock_resource.mock_context()
    ctx.set_attribute('id', resource_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('pool_id', pool_id)
    ctx.set_attribute('resource_type', resource_type)
    ctx.set_attribute('description', '')
    ctx.set_attribute('metadata_json', {})
    ctx.set_attribute('sensitive_fields', [])
    ctx.set_attribute('capacity', 1)
    ctx.set_attribute('health_status', 'online')
    ctx.set_attribute('tags', [])
    ctx.set_attribute('pool', None)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    return mock_resource


def create_mock_session_for_deletion(resource, active_allocation_count):
    """
    Create a mock session for testing resource deletion.
    
    Query flow for delete_resource:
    1. Query Resource to find the resource by ID
    2. Query Allocation to count active allocations
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
        
        if call_count[0] == 1:
            # First call: Resource lookup
            mock_filter.mock_context().mock_method('first', return_value=resource)
        else:
            # Second call: Allocation count
            mock_filter.mock_context().mock_method('count', return_value=active_allocation_count)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('delete')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


def create_mock_session_resource_not_found():
    """
    Create a mock session that returns no resource (not found).
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=None)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session


# =============================================================================
# Resource Deletion Constraint Tests - Property 3
# =============================================================================

def test_resource_with_active_allocation_cannot_be_deleted():
    """
    **Feature: resources, Property 3: Resource Deletion Constraint**
    **Validates: Requirements 1.4**
    
    For any resource with an active allocation, deletion should be rejected
    with a ResourceHasAllocationsError.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Create mock session with 1 active allocation
    mock_session = create_mock_session_for_deletion(mock_resource, active_allocation_count=1)
    
    manager = ResourceManager(mock_session)
    
    # Attempt to delete the resource - should fail
    deletion_rejected = False
    try:
        manager.delete_resource(resource_id)
    except ResourceHasAllocationsError as e:
        deletion_rejected = True
        assert 'active allocation' in e.message.lower()
    
    assert deletion_rejected, "Resource with active allocation should not be deletable"


def test_resource_without_allocations_can_be_deleted():
    """
    **Feature: resources, Property 3: Resource Deletion Constraint**
    **Validates: Requirements 1.4**
    
    Resources without any allocations should be deletable.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Create mock session with 0 active allocations
    mock_session = create_mock_session_for_deletion(mock_resource, active_allocation_count=0)
    
    manager = ResourceManager(mock_session)
    
    # Delete the resource - should succeed (no exception)
    try:
        manager.delete_resource(resource_id)
        success = True
    except ResourceHasAllocationsError:
        success = False
    
    assert success, "Resource without allocations should be deletable"


def test_resource_with_released_allocation_can_be_deleted():
    """
    **Feature: resources, Property 3: Resource Deletion Constraint**
    **Validates: Requirements 1.4**
    
    Resources with only released (non-active) allocations should be deletable.
    The delete_resource method only checks for ACTIVE allocations.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Create mock session with 0 active allocations (released allocations don't count)
    mock_session = create_mock_session_for_deletion(mock_resource, active_allocation_count=0)
    
    manager = ResourceManager(mock_session)
    
    # Delete the resource - should succeed since no ACTIVE allocations
    try:
        manager.delete_resource(resource_id)
        success = True
    except ResourceHasAllocationsError:
        success = False
    
    assert success, "Resource with only released allocations should be deletable"


def test_delete_nonexistent_resource_raises_error():
    """
    **Feature: resources, Property 3: Resource Deletion Constraint**
    **Validates: Requirements 1.4**
    
    Attempting to delete a non-existent resource should raise ResourceNotFoundError.
    """
    # Create mock session that returns no resource
    mock_session = create_mock_session_resource_not_found()
    
    manager = ResourceManager(mock_session)
    
    # Attempt to delete a resource that doesn't exist
    not_found_raised = False
    try:
        manager.delete_resource(99999)
    except ResourceNotFoundError:
        not_found_raised = True
    
    assert not_found_raised, "Deleting non-existent resource should raise ResourceNotFoundError"


def test_property_active_allocations_block_deletion_for_random_resources():
    """
    **Feature: resources, Property 3: Resource Deletion Constraint**
    **Validates: Requirements 1.4**
    
    Property test: For any randomly generated resource with an active allocation,
    deletion should be rejected.
    """
    for _ in range(100):
        resource_id = random.randint(1, 10000)
        resource_name = generate_unique_name()
        resource_type = random.choice(['device', 'ip_address', 'port', 'credential', 'generic'])
        active_count = random.randint(1, 10)  # At least 1 active allocation
        
        # Create mock resource
        mock_resource = create_mock_resource(resource_id, resource_name, resource_type=resource_type)
        
        # Create mock session with active allocations
        mock_session = create_mock_session_for_deletion(mock_resource, active_allocation_count=active_count)
        
        manager = ResourceManager(mock_session)
        
        # Attempt to delete - should fail
        deletion_rejected = False
        try:
            manager.delete_resource(resource_id)
        except ResourceHasAllocationsError:
            deletion_rejected = True
        
        assert deletion_rejected, f"Resource '{resource_name}' with {active_count} active allocation(s) should not be deletable"


def test_property_no_active_allocations_allows_deletion():
    """
    **Feature: resources, Property 3: Resource Deletion Constraint**
    **Validates: Requirements 1.4**
    
    Property test: For any randomly generated resource without active allocations,
    deletion should succeed.
    """
    for _ in range(100):
        resource_id = random.randint(1, 10000)
        resource_name = generate_unique_name()
        resource_type = random.choice(['device', 'ip_address', 'port', 'credential', 'generic'])
        
        # Create mock resource
        mock_resource = create_mock_resource(resource_id, resource_name, resource_type=resource_type)
        
        # Create mock session with 0 active allocations
        mock_session = create_mock_session_for_deletion(mock_resource, active_allocation_count=0)
        
        manager = ResourceManager(mock_session)
        
        # Delete should succeed
        try:
            manager.delete_resource(resource_id)
            success = True
        except ResourceHasAllocationsError:
            success = False
        
        assert success, f"Resource '{resource_name}' without active allocations should be deletable"


def test_multiple_active_allocations_block_deletion():
    """
    **Feature: resources, Property 3: Resource Deletion Constraint**
    **Validates: Requirements 1.4**
    
    Resources with multiple active allocations (shared mode) should not be deletable.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource with capacity > 1 (shared resource)
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_resource.mock_context().set_attribute('capacity', 5)
    
    # Create mock session with 3 active allocations
    mock_session = create_mock_session_for_deletion(mock_resource, active_allocation_count=3)
    
    manager = ResourceManager(mock_session)
    
    # Attempt to delete - should fail
    deletion_rejected = False
    try:
        manager.delete_resource(resource_id)
    except ResourceHasAllocationsError as e:
        deletion_rejected = True
        # Should mention the count of active allocations
        assert '3' in e.message
    
    assert deletion_rejected, "Resource with multiple active allocations should not be deletable"


def test_boundary_single_active_allocation_blocks_deletion():
    """
    **Feature: resources, Property 3: Resource Deletion Constraint**
    **Validates: Requirements 1.4**
    
    Even a single active allocation should block deletion.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Create mock session with exactly 1 active allocation
    mock_session = create_mock_session_for_deletion(mock_resource, active_allocation_count=1)
    
    manager = ResourceManager(mock_session)
    
    # Attempt to delete - should fail
    deletion_rejected = False
    try:
        manager.delete_resource(resource_id)
    except ResourceHasAllocationsError:
        deletion_rejected = True
    
    assert deletion_rejected, "Resource with single active allocation should not be deletable"


def test_boundary_zero_active_allocations_allows_deletion():
    """
    **Feature: resources, Property 3: Resource Deletion Constraint**
    **Validates: Requirements 1.4**
    
    Zero active allocations should allow deletion.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Create mock session with exactly 0 active allocations
    mock_session = create_mock_session_for_deletion(mock_resource, active_allocation_count=0)
    
    manager = ResourceManager(mock_session)
    
    # Delete should succeed
    try:
        manager.delete_resource(resource_id)
        success = True
    except ResourceHasAllocationsError:
        success = False
    
    assert success, "Resource with zero active allocations should be deletable"

