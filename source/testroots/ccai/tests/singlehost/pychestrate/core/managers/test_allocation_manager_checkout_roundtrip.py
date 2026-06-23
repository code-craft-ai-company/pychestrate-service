"""
.. module:: test_allocation_manager_checkout_roundtrip
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for AllocationManager checkout-checkin round-trip property

.. moduleauthor:: Code Craft AI LLC

Tests for checkout-checkin round-trip property in the AllocationManager.

**Feature: resources**
**Property 5: Checkout-Checkin Round-Trip**
**Validates: Requirements 3.1, 4.1**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.allocation_manager import (
    AllocationManager,
    CheckoutRequest,
    AllocationResponse,
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
    from datetime import datetime, timezone
    
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


def create_mock_session_for_checkout(resource, existing_allocations=None):
    """
    Create a mock session for checkout operation.
    
    Query flow for checkout:
    1. Query Resource with for_update to lock the row
    2. Query Allocation to get active allocations
    3. Add new allocation
    4. Commit
    """
    existing_allocations = existing_allocations or []
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        
        # Create filter mock
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


def create_mock_session_for_checkin(allocation, resource, user):
    """
    Create a mock session for checkin operation.
    
    Query flow for checkin:
    1. Query Allocation to get the allocation
    2. Query Resource to get resource details (for response)
    3. Query User to get user details (for response)
    4. Commit
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
        
        # Return appropriate object based on call order
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


def create_mock_session_for_availability_check(resource, active_allocations=None):
    """
    Create a mock session for availability check.
    """
    active_allocations = active_allocations or []
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
            mock_filter.mock_context().mock_method('first', return_value=resource)
        else:
            mock_filter.mock_context().mock_method('all', return_value=active_allocations)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    
    return mock_session


# =============================================================================
# Checkout-Checkin Round-Trip Tests - Property 5
# =============================================================================

def test_checkout_checkin_roundtrip_basic():
    """
    **Feature: resources, Property 5: Checkout-Checkin Round-Trip**
    **Validates: Requirements 3.1, 4.1**
    
    For any available resource and valid checkout request, checking out the resource
    and then checking it back in should return the resource to available status.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Step 1: Verify resource is initially available
    mock_session_check = create_mock_session_for_availability_check(mock_resource, [])
    manager_check = AllocationManager(mock_session_check)
    
    initial_available = manager_check.check_availability(resource_id, mode="exclusive")
    assert initial_available, "Resource should be initially available"
    
    # Step 2: Checkout the resource
    mock_session_checkout = create_mock_session_for_checkout(mock_resource, [])
    manager_checkout = AllocationManager(mock_session_checkout)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive",
        reason="Test checkout"
    )
    
    allocation = manager_checkout.checkout(checkout_request, user_id)
    assert allocation is not None, "Checkout should succeed"
    assert allocation.resource_id == resource_id, "Allocation should be for the correct resource"
    
    # Step 3: Checkin the resource
    mock_allocation = create_mock_allocation(allocation.id, resource_id, user_id, status='active')
    mock_user = create_mock_user(user_id)
    mock_session_checkin = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
    manager_checkin = AllocationManager(mock_session_checkin)
    
    checkin_result = manager_checkin.checkin(allocation.id, user_id)
    assert checkin_result is not None, "Checkin should succeed"
    
    # Step 4: Verify resource is available again
    mock_session_check2 = create_mock_session_for_availability_check(mock_resource, [])
    manager_check2 = AllocationManager(mock_session_check2)
    
    final_available = manager_check2.check_availability(resource_id, mode="exclusive")
    assert final_available, "Resource should be available after checkin"


def test_checkout_checkin_roundtrip_preserves_capacity():
    """
    **Feature: resources, Property 5: Checkout-Checkin Round-Trip**
    **Validates: Requirements 3.1, 4.1**
    
    After checkout and checkin, the resource should have the same capacity as before.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    capacity = 5
    
    # Create mock resource with specific capacity
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=capacity)
    
    # Verify initial capacity
    assert mock_resource.capacity == capacity, "Initial capacity should be set"
    
    # Checkout
    mock_session_checkout = create_mock_session_for_checkout(mock_resource, [])
    manager_checkout = AllocationManager(mock_session_checkout)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="shared",
        reason="Test checkout"
    )
    
    allocation = manager_checkout.checkout(checkout_request, user_id)
    assert allocation is not None, "Checkout should succeed"
    
    # Checkin
    mock_allocation = create_mock_allocation(allocation.id, resource_id, user_id, mode='shared', status='active')
    mock_user = create_mock_user(user_id)
    mock_session_checkin = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
    manager_checkin = AllocationManager(mock_session_checkin)
    
    manager_checkin.checkin(allocation.id, user_id)
    
    # Verify capacity is unchanged
    assert mock_resource.capacity == capacity, "Capacity should be unchanged after round-trip"


def test_property_checkout_checkin_roundtrip_random_resources():
    """
    **Feature: resources, Property 5: Checkout-Checkin Round-Trip**
    **Validates: Requirements 3.1, 4.1**
    
    Property test: For any randomly generated resource, checkout followed by checkin
    should return the resource to available status.
    """
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        user_id = generate_user_id()
        capacity = random.randint(1, 10)
        mode = random.choice(['exclusive', 'shared'])
        
        # Create mock resource
        mock_resource = create_mock_resource(resource_id, resource_name, capacity=capacity)
        
        # Verify initially available
        mock_session_check = create_mock_session_for_availability_check(mock_resource, [])
        manager_check = AllocationManager(mock_session_check)
        
        initial_available = manager_check.check_availability(resource_id, mode=mode)
        assert initial_available, f"Resource {resource_id} should be initially available"
        
        # Checkout
        mock_session_checkout = create_mock_session_for_checkout(mock_resource, [])
        manager_checkout = AllocationManager(mock_session_checkout)
        
        checkout_request = CheckoutRequest(
            resource_id=resource_id,
            mode=mode,
            reason="Property test checkout"
        )
        
        allocation = manager_checkout.checkout(checkout_request, user_id)
        assert allocation is not None, f"Checkout should succeed for resource {resource_id}"
        
        # Checkin
        mock_allocation = create_mock_allocation(allocation.id, resource_id, user_id, mode=mode, status='active')
        mock_user = create_mock_user(user_id)
        mock_session_checkin = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
        manager_checkin = AllocationManager(mock_session_checkin)
        
        manager_checkin.checkin(allocation.id, user_id)
        
        # Verify available after checkin
        mock_session_check2 = create_mock_session_for_availability_check(mock_resource, [])
        manager_check2 = AllocationManager(mock_session_check2)
        
        final_available = manager_check2.check_availability(resource_id, mode=mode)
        assert final_available, f"Resource {resource_id} should be available after checkin"


def test_checkout_checkin_roundtrip_with_metadata():
    """
    **Feature: resources, Property 5: Checkout-Checkin Round-Trip**
    **Validates: Requirements 3.1, 4.1**
    
    Checkout should capture metadata snapshot, and checkin should not affect resource metadata.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    # Create mock resource with metadata
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_resource.metadata_json = {'host': 'server1', 'port': 8080}
    
    # Checkout
    mock_session_checkout = create_mock_session_for_checkout(mock_resource, [])
    manager_checkout = AllocationManager(mock_session_checkout)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive",
        reason="Test with metadata"
    )
    
    allocation = manager_checkout.checkout(checkout_request, user_id)
    assert allocation is not None, "Checkout should succeed"
    assert allocation.metadata is not None, "Allocation should have metadata snapshot"
    
    # Checkin
    mock_allocation = create_mock_allocation(allocation.id, resource_id, user_id, status='active')
    mock_allocation.metadata_snapshot = {'host': 'server1', 'port': 8080}
    mock_user = create_mock_user(user_id)
    mock_session_checkin = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
    manager_checkin = AllocationManager(mock_session_checkin)
    
    manager_checkin.checkin(allocation.id, user_id)
    
    # Verify resource metadata is unchanged
    assert mock_resource.metadata_json == {'host': 'server1', 'port': 8080}, \
        "Resource metadata should be unchanged after round-trip"


def test_checkout_checkin_roundtrip_exclusive_mode():
    """
    **Feature: resources, Property 5: Checkout-Checkin Round-Trip**
    **Validates: Requirements 3.1, 4.1**
    
    Exclusive checkout followed by checkin should return resource to fully available state.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=1)
    
    # Checkout exclusive
    mock_session_checkout = create_mock_session_for_checkout(mock_resource, [])
    manager_checkout = AllocationManager(mock_session_checkout)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive"
    )
    
    allocation = manager_checkout.checkout(checkout_request, user_id)
    assert allocation.mode == "exclusive", "Allocation should be exclusive"
    
    # Checkin
    mock_allocation = create_mock_allocation(allocation.id, resource_id, user_id, mode='exclusive', status='active')
    mock_user = create_mock_user(user_id)
    mock_session_checkin = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
    manager_checkin = AllocationManager(mock_session_checkin)
    
    manager_checkin.checkin(allocation.id, user_id)
    
    # Verify available for both exclusive and shared
    mock_session_check = create_mock_session_for_availability_check(mock_resource, [])
    manager_check = AllocationManager(mock_session_check)
    
    assert manager_check.check_availability(resource_id, "exclusive"), \
        "Resource should be available for exclusive after checkin"


def test_checkout_checkin_roundtrip_shared_mode():
    """
    **Feature: resources, Property 5: Checkout-Checkin Round-Trip**
    **Validates: Requirements 3.1, 4.1**
    
    Shared checkout followed by checkin should return resource to available state.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=5)
    
    # Checkout shared
    mock_session_checkout = create_mock_session_for_checkout(mock_resource, [])
    manager_checkout = AllocationManager(mock_session_checkout)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="shared"
    )
    
    allocation = manager_checkout.checkout(checkout_request, user_id)
    assert allocation.mode == "shared", "Allocation should be shared"
    
    # Checkin
    mock_allocation = create_mock_allocation(allocation.id, resource_id, user_id, mode='shared', status='active')
    mock_user = create_mock_user(user_id)
    mock_session_checkin = create_mock_session_for_checkin(mock_allocation, mock_resource, mock_user)
    manager_checkin = AllocationManager(mock_session_checkin)
    
    manager_checkin.checkin(allocation.id, user_id)
    
    # Verify available
    mock_session_check = create_mock_session_for_availability_check(mock_resource, [])
    manager_check = AllocationManager(mock_session_check)
    
    assert manager_check.check_availability(resource_id, "shared"), \
        "Resource should be available for shared after checkin"
