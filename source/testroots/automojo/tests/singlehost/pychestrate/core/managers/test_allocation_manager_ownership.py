"""
.. module:: test_allocation_manager_ownership
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for AllocationManager checkin ownership validation

.. moduleauthor:: Automation Mojo LLC

Tests for checkin ownership validation in the AllocationManager.

**Feature: resources**
**Property 9: Checkin Ownership Validation**
**Validates: Requirements 4.2**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid
from datetime import datetime, timezone

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.allocation_manager import (
    AllocationManager,
    CheckoutRequest,
    NotAllocationOwnerError,
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


def create_mock_resource(resource_id, name, pool_id=1, capacity=1, health_status='online'):
    """Create a mock resource object matching the Resource ORM model."""
    mock_resource = Mock()
    mock_resource.configure(recursive=True)
    ctx = mock_resource.mock_context()
    ctx.set_attribute('id', resource_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('pool_id', pool_id)
    ctx.set_attribute('resource_type', 'device')
    ctx.set_attribute('description', '')
    ctx.set_attribute('metadata_json', {'key': 'value'})
    ctx.set_attribute('sensitive_fields', [])
    ctx.set_attribute('capacity', capacity)
    ctx.set_attribute('health_status', health_status)
    ctx.set_attribute('tags', [])
    return mock_resource


def create_mock_allocation(allocation_id, resource_id, user_id, mode='exclusive', status='active'):
    """Create a mock allocation object matching the Allocation ORM model."""
    mock_allocation = Mock()
    mock_allocation.configure(recursive=True)
    ctx = mock_allocation.mock_context()
    ctx.set_attribute('id', allocation_id)
    ctx.set_attribute('resource_id', resource_id)
    ctx.set_attribute('user_id', user_id)
    ctx.set_attribute('job_id', None)
    ctx.set_attribute('mode', mode)
    ctx.set_attribute('status', status)
    ctx.set_attribute('checkout_time', datetime.now(timezone.utc))
    ctx.set_attribute('expected_checkin', None)
    ctx.set_attribute('actual_checkin', None)
    ctx.set_attribute('duration_minutes', None)
    ctx.set_attribute('reason', '')
    ctx.set_attribute('forced_by_id', None)
    ctx.set_attribute('force_reason', None)
    ctx.set_attribute('metadata_snapshot', {'key': 'value'})
    return mock_allocation


def create_mock_user(user_id, login='testuser'):
    """Create a mock user object."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', login)
    return mock_user


def create_mock_session_for_checkin(allocation, resource, user):
    """Create a mock session for checkin operation."""
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
            mock_filter.mock_context().mock_method('first', return_value=allocation)
        elif call_count[0] == 2:
            mock_filter.mock_context().mock_method('first', return_value=resource)
        else:
            mock_filter.mock_context().mock_method('first', return_value=user)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Checkin Ownership Validation Tests - Property 9
# =============================================================================

def test_checkin_by_owner_succeeds():
    """
    **Feature: resources, Property 9: Checkin Ownership Validation**
    **Validates: Requirements 4.2**
    
    The owner of an allocation should be able to check it in.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    owner_id = generate_user_id()
    allocation_id = 1
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_allocation = create_mock_allocation(allocation_id, resource_id, owner_id, status='active')
    mock_user = create_mock_user(owner_id)
    
    mock_session = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
    manager = AllocationManager(mock_session)
    
    # Owner should be able to checkin
    result = manager.checkin(allocation_id, owner_id)
    assert result is not None, "Owner should be able to checkin"
    assert result.id == allocation_id, "Checkin should return correct allocation"


def test_checkin_by_non_owner_fails():
    """
    **Feature: resources, Property 9: Checkin Ownership Validation**
    **Validates: Requirements 4.2**
    
    A user who is not the owner should not be able to check in an allocation.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    owner_id = generate_user_id()
    other_user_id = generate_user_id()
    allocation_id = 1
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_allocation = create_mock_allocation(allocation_id, resource_id, owner_id, status='active')
    mock_user = create_mock_user(owner_id)
    
    mock_session = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
    manager = AllocationManager(mock_session)
    
    # Non-owner should not be able to checkin
    checkin_rejected = False
    try:
        manager.checkin(allocation_id, other_user_id)
    except NotAllocationOwnerError:
        checkin_rejected = True
    
    assert checkin_rejected, "Non-owner should not be able to checkin"


def test_property_ownership_validation_random():
    """
    **Feature: resources, Property 9: Checkin Ownership Validation**
    **Validates: Requirements 4.2**
    
    Property test: For any allocation, only the owner can check it in.
    Non-owners should always be rejected.
    """
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        owner_id = generate_user_id()
        allocation_id = random.randint(1, 1000)
        
        mock_resource = create_mock_resource(resource_id, resource_name)
        mock_allocation = create_mock_allocation(allocation_id, resource_id, owner_id, status='active')
        mock_user = create_mock_user(owner_id)
        
        # Test owner can checkin
        mock_session_owner = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
        manager_owner = AllocationManager(mock_session_owner)
        
        result = manager_owner.checkin(allocation_id, owner_id)
        assert result is not None, f"Owner should be able to checkin allocation {allocation_id}"
        
        # Test non-owner cannot checkin (create fresh allocation since previous was modified)
        mock_allocation2 = create_mock_allocation(allocation_id, resource_id, owner_id, status='active')
        mock_session_other = create_mock_session_for_checkin(mock_allocation2, mock_resource, mock_user)
        manager_other = AllocationManager(mock_session_other)
        
        other_user_id = generate_user_id()
        checkin_rejected = False
        try:
            manager_other.checkin(allocation_id, other_user_id)
        except NotAllocationOwnerError:
            checkin_rejected = True
        
        assert checkin_rejected, f"Non-owner should not be able to checkin allocation {allocation_id}"


def test_force_checkin_by_admin_succeeds():
    """
    **Feature: resources, Property 9: Checkin Ownership Validation**
    **Validates: Requirements 4.4, 4.5**
    
    An administrator should be able to force checkin any allocation.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    owner_id = generate_user_id()
    admin_id = generate_user_id()
    allocation_id = 1
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_allocation = create_mock_allocation(allocation_id, resource_id, owner_id, status='active')
    mock_user = create_mock_user(owner_id)
    
    mock_session = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
    manager = AllocationManager(mock_session)
    
    # Admin should be able to force checkin
    result = manager.force_checkin(allocation_id, admin_id, "Administrative action")
    assert result is not None, "Admin should be able to force checkin"
    assert result.id == allocation_id, "Force checkin should return correct allocation"


def test_checkin_different_users_different_allocations():
    """
    **Feature: resources, Property 9: Checkin Ownership Validation**
    **Validates: Requirements 4.2**
    
    Each user should only be able to checkin their own allocations.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user1_id = generate_user_id()
    user2_id = generate_user_id()
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # User 1's allocation
    allocation1_id = 1
    mock_allocation1 = create_mock_allocation(allocation1_id, resource_id, user1_id, status='active')
    mock_user1 = create_mock_user(user1_id)
    
    # User 2's allocation
    allocation2_id = 2
    mock_allocation2 = create_mock_allocation(allocation2_id, resource_id, user2_id, status='active')
    mock_user2 = create_mock_user(user2_id)
    
    # User 1 can checkin allocation 1
    mock_session1 = create_mock_session_for_checkin(mock_allocation1, mock_resource, mock_user1)
    manager1 = AllocationManager(mock_session1)
    result1 = manager1.checkin(allocation1_id, user1_id)
    assert result1 is not None, "User 1 should checkin their own allocation"
    
    # User 1 cannot checkin allocation 2
    mock_allocation2_fresh = create_mock_allocation(allocation2_id, resource_id, user2_id, status='active')
    mock_session2 = create_mock_session_for_checkin(mock_allocation2_fresh, mock_resource, mock_user2)
    manager2 = AllocationManager(mock_session2)
    
    user1_rejected = False
    try:
        manager2.checkin(allocation2_id, user1_id)
    except NotAllocationOwnerError:
        user1_rejected = True
    
    assert user1_rejected, "User 1 should not be able to checkin User 2's allocation"

