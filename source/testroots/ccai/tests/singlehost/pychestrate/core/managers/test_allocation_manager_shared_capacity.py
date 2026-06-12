"""
.. module:: test_allocation_manager_shared_capacity
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for AllocationManager shared capacity enforcement

.. moduleauthor:: Code Craft AI LLC

Tests for shared capacity enforcement in the AllocationManager.

**Feature: resources**
**Property 7: Shared Capacity Enforcement**
**Validates: Requirements 3.5**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid
from datetime import datetime, timezone

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.allocation_manager import (
    AllocationManager,
    CheckoutRequest,
    CapacityExceededError,
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


def create_mock_allocation(allocation_id, resource_id, user_id, mode='shared', status='active'):
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


def create_mock_session_for_checkout_with_allocations(resource, existing_allocations):
    """
    Create a mock session for checkout operation with existing allocations.
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
        
        # Create with_for_update mock
        mock_for_update = Mock()
        mock_for_update.configure(recursive=True)
        mock_for_update.mock_context().mock_method('first', return_value=resource)
        
        mock_filter.mock_context().mock_method('with_for_update', return_value=mock_for_update)
        mock_filter.mock_context().mock_method('first', return_value=resource)
        mock_filter.mock_context().mock_method('all', return_value=existing_allocations)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Shared Capacity Enforcement Tests - Property 7
# =============================================================================

def test_shared_capacity_allows_up_to_n_allocations():
    """
    **Feature: resources, Property 7: Shared Capacity Enforcement**
    **Validates: Requirements 3.5**
    
    For any shared resource with capacity N, exactly N concurrent shared
    allocations should be allowed.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    capacity = 3
    
    # Create mock resource with capacity 3
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=capacity)
    
    # Create 2 existing shared allocations (capacity - 1)
    existing_allocations = [
        create_mock_allocation(i, resource_id, generate_user_id(), mode='shared', status='active')
        for i in range(1, capacity)
    ]
    
    # Create mock session with existing allocations
    mock_session = create_mock_session_for_checkout_with_allocations(
        mock_resource, existing_allocations
    )
    
    manager = AllocationManager(mock_session)
    
    # Attempt Nth checkout (should succeed)
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="shared",
        reason="Nth checkout"
    )
    
    new_user_id = generate_user_id()
    
    try:
        allocation = manager.checkout(checkout_request, new_user_id)
        checkout_succeeded = True
    except CapacityExceededError:
        checkout_succeeded = False
    
    assert checkout_succeeded, f"Checkout should succeed when {capacity - 1} of {capacity} slots used"


def test_shared_capacity_rejects_n_plus_1_allocation():
    """
    **Feature: resources, Property 7: Shared Capacity Enforcement**
    **Validates: Requirements 3.5**
    
    For any shared resource with capacity N, the (N+1)th checkout request
    should be rejected.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    capacity = 3
    
    # Create mock resource with capacity 3
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=capacity)
    
    # Create N existing shared allocations (at capacity)
    existing_allocations = [
        create_mock_allocation(i, resource_id, generate_user_id(), mode='shared', status='active')
        for i in range(1, capacity + 1)
    ]
    
    # Create mock session with existing allocations
    mock_session = create_mock_session_for_checkout_with_allocations(
        mock_resource, existing_allocations
    )
    
    manager = AllocationManager(mock_session)
    
    # Attempt (N+1)th checkout (should fail)
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="shared",
        reason="N+1 checkout"
    )
    
    new_user_id = generate_user_id()
    
    checkout_rejected = False
    capacity_info_returned = False
    
    try:
        manager.checkout(checkout_request, new_user_id)
    except CapacityExceededError as e:
        checkout_rejected = True
        if e.capacity == capacity and e.current_allocations == capacity:
            capacity_info_returned = True
    
    assert checkout_rejected, f"Checkout should be rejected when at capacity ({capacity})"
    assert capacity_info_returned, "Capacity information should be returned in error"


def test_property_shared_capacity_enforcement_random():
    """
    **Feature: resources, Property 7: Shared Capacity Enforcement**
    **Validates: Requirements 3.5**
    
    Property test: For any randomly generated resource with capacity N,
    exactly N shared allocations should be allowed, and N+1 should be rejected.
    """
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        capacity = random.randint(1, 10)
        
        # Create mock resource
        mock_resource = create_mock_resource(resource_id, resource_name, capacity=capacity)
        
        # Create N existing shared allocations (at capacity)
        existing_allocations = [
            create_mock_allocation(i, resource_id, generate_user_id(), mode='shared', status='active')
            for i in range(1, capacity + 1)
        ]
        
        # Create mock session with existing allocations
        mock_session = create_mock_session_for_checkout_with_allocations(
            mock_resource, existing_allocations
        )
        
        manager = AllocationManager(mock_session)
        
        # Attempt (N+1)th checkout
        checkout_request = CheckoutRequest(
            resource_id=resource_id,
            mode="shared"
        )
        
        checkout_rejected = False
        
        try:
            manager.checkout(checkout_request, generate_user_id())
        except CapacityExceededError:
            checkout_rejected = True
        
        assert checkout_rejected, \
            f"Checkout should be rejected when at capacity ({capacity})"


def test_shared_capacity_with_capacity_one():
    """
    **Feature: resources, Property 7: Shared Capacity Enforcement**
    **Validates: Requirements 3.5**
    
    A shared resource with capacity 1 should behave like exclusive allocation.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    capacity = 1
    
    # Create mock resource with capacity 1
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=capacity)
    
    # Create 1 existing shared allocation (at capacity)
    existing_allocations = [
        create_mock_allocation(1, resource_id, generate_user_id(), mode='shared', status='active')
    ]
    
    # Create mock session with existing allocation
    mock_session = create_mock_session_for_checkout_with_allocations(
        mock_resource, existing_allocations
    )
    
    manager = AllocationManager(mock_session)
    
    # Attempt second checkout
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="shared"
    )
    
    checkout_rejected = False
    
    try:
        manager.checkout(checkout_request, generate_user_id())
    except CapacityExceededError:
        checkout_rejected = True
    
    assert checkout_rejected, "Shared resource with capacity 1 should reject second checkout"


def test_shared_capacity_error_includes_details():
    """
    **Feature: resources, Property 7: Shared Capacity Enforcement**
    **Validates: Requirements 3.5**
    
    When capacity is exceeded, the error should include capacity and current
    allocation count.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    capacity = 5
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=capacity)
    
    # Create N existing shared allocations
    existing_allocations = [
        create_mock_allocation(i, resource_id, generate_user_id(), mode='shared', status='active')
        for i in range(1, capacity + 1)
    ]
    
    # Create mock session with existing allocations
    mock_session = create_mock_session_for_checkout_with_allocations(
        mock_resource, existing_allocations
    )
    
    manager = AllocationManager(mock_session)
    
    # Attempt checkout
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="shared"
    )
    
    try:
        manager.checkout(checkout_request, generate_user_id())
        assert False, "Should have raised CapacityExceededError"
    except CapacityExceededError as e:
        assert e.capacity == capacity, f"Capacity should be {capacity}"
        assert e.current_allocations == capacity, f"Current allocations should be {capacity}"
        assert "capacity" in e.message.lower(), "Error message should mention capacity"
