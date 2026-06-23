"""
.. module:: test_allocation_manager_concurrent
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for AllocationManager concurrent checkout serialization

.. moduleauthor:: Code Craft AI LLC

Tests for concurrent checkout serialization in the AllocationManager.

**Feature: resources**
**Property 15: Concurrent Checkout Serialization**
**Validates: Requirements 12.1**
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
    ResourceUnavailableError,
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


def create_mock_session_for_checkout(resource, existing_allocations=None):
    """
    Create a mock session for checkout operation.
    """
    existing_allocations = existing_allocations or []
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
# Concurrent Checkout Serialization Tests - Property 15
# =============================================================================

def test_checkout_uses_database_locking():
    """
    **Feature: resources, Property 15: Concurrent Checkout Serialization**
    **Validates: Requirements 12.1**
    
    The checkout operation should use database-level locking (SELECT FOR UPDATE)
    to serialize concurrent access.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Create mock session
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    # Track if with_for_update was called
    for_update_called = [False]
    
    def query_side_effect(model):
        mock_query = Mock()
        mock_query.configure(recursive=True)
        
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # Create with_for_update mock that tracks calls
        mock_for_update = Mock()
        mock_for_update.configure(recursive=True)
        mock_for_update.mock_context().mock_method('first', return_value=mock_resource)
        
        def with_for_update_side_effect(*args, **kwargs):
            for_update_called[0] = True
            return mock_for_update
        
        mock_filter.mock_context().mock_method('with_for_update', side_effect=with_for_update_side_effect)
        mock_filter.mock_context().mock_method('first', return_value=mock_resource)
        mock_filter.mock_context().mock_method('all', return_value=[])
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    manager = AllocationManager(mock_session)
    
    # Perform checkout
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive"
    )
    
    manager.checkout(checkout_request, user_id)
    
    assert for_update_called[0], "Checkout should use SELECT FOR UPDATE for locking"


def test_simulated_concurrent_checkouts_one_succeeds():
    """
    **Feature: resources, Property 15: Concurrent Checkout Serialization**
    **Validates: Requirements 12.1**
    
    When simulating concurrent checkout requests, exactly one should succeed
    and the rest should be rejected.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    num_concurrent = 5
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Simulate concurrent checkouts by having the first succeed and rest see the allocation
    success_count = 0
    failure_count = 0
    
    for i in range(num_concurrent):
        user_id = generate_user_id()
        
        if i == 0:
            # First checkout - no existing allocations
            mock_session = create_mock_session_for_checkout(mock_resource, [])
        else:
            # Subsequent checkouts - see the first allocation
            existing_allocation = create_mock_allocation(1, resource_id, generate_user_id(), 
                                                         mode='exclusive', status='active')
            mock_session = create_mock_session_for_checkout(mock_resource, [existing_allocation])
        
        manager = AllocationManager(mock_session)
        
        checkout_request = CheckoutRequest(
            resource_id=resource_id,
            mode="exclusive"
        )
        
        try:
            manager.checkout(checkout_request, user_id)
            success_count += 1
        except ResourceUnavailableError:
            failure_count += 1
    
    assert success_count == 1, f"Exactly one checkout should succeed, got {success_count}"
    assert failure_count == num_concurrent - 1, \
        f"Exactly {num_concurrent - 1} checkouts should fail, got {failure_count}"


def test_property_concurrent_checkout_serialization_random():
    """
    **Feature: resources, Property 15: Concurrent Checkout Serialization**
    **Validates: Requirements 12.1**
    
    Property test: For any resource and N simultaneous checkout requests,
    exactly one request should succeed and (N-1) should be rejected.
    """
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        num_concurrent = random.randint(2, 10)
        
        # Create mock resource
        mock_resource = create_mock_resource(resource_id, resource_name)
        
        success_count = 0
        failure_count = 0
        
        for i in range(num_concurrent):
            user_id = generate_user_id()
            
            if i == 0:
                # First checkout - no existing allocations
                mock_session = create_mock_session_for_checkout(mock_resource, [])
            else:
                # Subsequent checkouts - see the first allocation
                existing_allocation = create_mock_allocation(1, resource_id, generate_user_id(),
                                                             mode='exclusive', status='active')
                mock_session = create_mock_session_for_checkout(mock_resource, [existing_allocation])
            
            manager = AllocationManager(mock_session)
            
            checkout_request = CheckoutRequest(
                resource_id=resource_id,
                mode="exclusive"
            )
            
            try:
                manager.checkout(checkout_request, user_id)
                success_count += 1
            except ResourceUnavailableError:
                failure_count += 1
        
        assert success_count == 1, \
            f"Exactly one checkout should succeed for {num_concurrent} concurrent requests"
        assert failure_count == num_concurrent - 1, \
            f"Exactly {num_concurrent - 1} checkouts should fail"


def test_concurrent_shared_checkouts_respect_capacity():
    """
    **Feature: resources, Property 15: Concurrent Checkout Serialization**
    **Validates: Requirements 12.1**
    
    When simulating concurrent shared checkout requests, exactly N should succeed
    where N is the resource capacity.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    capacity = 3
    num_concurrent = 5
    
    # Create mock resource with capacity
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=capacity)
    
    success_count = 0
    failure_count = 0
    
    # Track allocations as they're created
    current_allocations = []
    
    for i in range(num_concurrent):
        user_id = generate_user_id()
        
        # Create mock session with current allocations
        mock_session = create_mock_session_for_checkout(mock_resource, list(current_allocations))
        
        manager = AllocationManager(mock_session)
        
        checkout_request = CheckoutRequest(
            resource_id=resource_id,
            mode="shared"
        )
        
        try:
            allocation = manager.checkout(checkout_request, user_id)
            success_count += 1
            # Add to current allocations for next iteration
            new_alloc = create_mock_allocation(i + 1, resource_id, user_id, mode='shared', status='active')
            current_allocations.append(new_alloc)
        except Exception:
            failure_count += 1
    
    assert success_count == capacity, \
        f"Exactly {capacity} shared checkouts should succeed, got {success_count}"
    assert failure_count == num_concurrent - capacity, \
        f"Exactly {num_concurrent - capacity} checkouts should fail, got {failure_count}"


def test_locking_prevents_race_condition():
    """
    **Feature: resources, Property 15: Concurrent Checkout Serialization**
    **Validates: Requirements 12.1**
    
    The database locking mechanism should prevent race conditions where
    multiple checkouts could succeed for an exclusive resource.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Simulate the scenario where locking ensures serialization
    # First request gets the lock and succeeds
    mock_session1 = create_mock_session_for_checkout(mock_resource, [])
    manager1 = AllocationManager(mock_session1)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive"
    )
    
    # First checkout succeeds
    allocation1 = manager1.checkout(checkout_request, generate_user_id())
    assert allocation1 is not None, "First checkout should succeed"
    
    # Second request sees the allocation (after lock is released)
    existing_allocation = create_mock_allocation(1, resource_id, generate_user_id(),
                                                 mode='exclusive', status='active')
    mock_session2 = create_mock_session_for_checkout(mock_resource, [existing_allocation])
    manager2 = AllocationManager(mock_session2)
    
    # Second checkout should fail
    checkout_rejected = False
    try:
        manager2.checkout(checkout_request, generate_user_id())
    except ResourceUnavailableError:
        checkout_rejected = True
    
    assert checkout_rejected, "Second checkout should be rejected after first succeeds"
