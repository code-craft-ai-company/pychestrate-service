"""
.. module:: test_health_monitor_allocation_blocking
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for health status allocation blocking property

.. moduleauthor:: Automation Mojo LLC

Tests for health status allocation blocking in the AllocationManager.

**Feature: resources**
**Property 12: Health Status Allocation Blocking**
**Validates: Requirements 6.3**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.allocation_manager import (
    AllocationManager,
    CheckoutRequest,
    ResourceOfflineError,
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
        
        # First call returns resource, subsequent calls return allocations/reservations
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=resource)
        else:
            mock_filter.mock_context().mock_method('all', return_value=active_allocations)
        
        mock_filter.mock_context().mock_method('filter', return_value=mock_filter)
        mock_filter.mock_context().mock_method('in_', return_value=mock_filter)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    
    return mock_session



# =============================================================================
# Health Status Allocation Blocking Tests - Property 12
# =============================================================================

def test_offline_resource_blocks_checkout():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    For any resource with health status 'offline', checkout requests should be rejected.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    # Create mock resource with offline status
    mock_resource = create_mock_resource(resource_id, resource_name, health_status='offline')
    
    # Attempt checkout
    mock_session = create_mock_session_for_checkout(mock_resource, [])
    manager = AllocationManager(mock_session)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive",
        reason="Test checkout"
    )
    
    try:
        manager.checkout(checkout_request, user_id)
        assert False, "Checkout should have been rejected for offline resource"
    except ResourceOfflineError as e:
        assert e.health_status == 'offline', "Error should indicate offline status"


def test_maintenance_resource_blocks_checkout():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    For any resource with health status 'maintenance', checkout requests should be rejected.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    # Create mock resource with maintenance status
    mock_resource = create_mock_resource(resource_id, resource_name, health_status='maintenance')
    
    # Attempt checkout
    mock_session = create_mock_session_for_checkout(mock_resource, [])
    manager = AllocationManager(mock_session)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive",
        reason="Test checkout"
    )
    
    try:
        manager.checkout(checkout_request, user_id)
        assert False, "Checkout should have been rejected for maintenance resource"
    except ResourceOfflineError as e:
        assert e.health_status == 'maintenance', "Error should indicate maintenance status"


def test_online_resource_allows_checkout():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    For any resource with health status 'online', checkout requests should be allowed.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    # Create mock resource with online status
    mock_resource = create_mock_resource(resource_id, resource_name, health_status='online')
    
    # Attempt checkout
    mock_session = create_mock_session_for_checkout(mock_resource, [])
    manager = AllocationManager(mock_session)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive",
        reason="Test checkout"
    )
    
    allocation = manager.checkout(checkout_request, user_id)
    assert allocation is not None, "Checkout should succeed for online resource"
    assert allocation.resource_id == resource_id, "Allocation should be for the correct resource"


def test_degraded_resource_allows_checkout():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    For any resource with health status 'degraded', checkout requests should be allowed.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    # Create mock resource with degraded status
    mock_resource = create_mock_resource(resource_id, resource_name, health_status='degraded')
    
    # Attempt checkout
    mock_session = create_mock_session_for_checkout(mock_resource, [])
    manager = AllocationManager(mock_session)
    
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive",
        reason="Test checkout"
    )
    
    allocation = manager.checkout(checkout_request, user_id)
    assert allocation is not None, "Checkout should succeed for degraded resource"
    assert allocation.resource_id == resource_id, "Allocation should be for the correct resource"


def test_offline_resource_unavailable_in_check():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    For any resource with health status 'offline', check_availability should return False.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource with offline status
    mock_resource = create_mock_resource(resource_id, resource_name, health_status='offline')
    
    # Check availability
    mock_session = create_mock_session_for_availability_check(mock_resource, [])
    manager = AllocationManager(mock_session)
    
    available = manager.check_availability(resource_id, mode="exclusive")
    assert not available, "Offline resource should not be available"


def test_maintenance_resource_unavailable_in_check():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    For any resource with health status 'maintenance', check_availability should return False.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource with maintenance status
    mock_resource = create_mock_resource(resource_id, resource_name, health_status='maintenance')
    
    # Check availability
    mock_session = create_mock_session_for_availability_check(mock_resource, [])
    manager = AllocationManager(mock_session)
    
    available = manager.check_availability(resource_id, mode="exclusive")
    assert not available, "Maintenance resource should not be available"


def test_online_resource_available_in_check():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    For any resource with health status 'online', check_availability should return True.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource with online status
    mock_resource = create_mock_resource(resource_id, resource_name, health_status='online')
    
    # Check availability
    mock_session = create_mock_session_for_availability_check(mock_resource, [])
    manager = AllocationManager(mock_session)
    
    available = manager.check_availability(resource_id, mode="exclusive")
    assert available, "Online resource should be available"


def test_degraded_resource_available_in_check():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    For any resource with health status 'degraded', check_availability should return True.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Create mock resource with degraded status
    mock_resource = create_mock_resource(resource_id, resource_name, health_status='degraded')
    
    # Check availability
    mock_session = create_mock_session_for_availability_check(mock_resource, [])
    manager = AllocationManager(mock_session)
    
    available = manager.check_availability(resource_id, mode="exclusive")
    assert available, "Degraded resource should be available"


def test_property_health_status_blocking_random():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    Property test: For any randomly generated resource with any health status,
    checkout should be blocked for 'offline' and 'maintenance' statuses,
    and allowed for 'online' and 'degraded' statuses.
    """
    blocked_statuses = {'offline', 'maintenance'}
    allowed_statuses = {'online', 'degraded'}
    all_statuses = list(blocked_statuses | allowed_statuses)
    
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        user_id = generate_user_id()
        health_status = random.choice(all_statuses)
        mode = random.choice(['exclusive', 'shared'])
        
        # Create mock resource with random health status
        mock_resource = create_mock_resource(resource_id, resource_name, health_status=health_status)
        
        # Attempt checkout
        mock_session = create_mock_session_for_checkout(mock_resource, [])
        manager = AllocationManager(mock_session)
        
        checkout_request = CheckoutRequest(
            resource_id=resource_id,
            mode=mode,
            reason="Property test checkout"
        )
        
        if health_status in blocked_statuses:
            # Should be blocked
            try:
                manager.checkout(checkout_request, user_id)
                assert False, f"Checkout should have been rejected for {health_status} resource"
            except ResourceOfflineError as e:
                assert e.health_status == health_status, \
                    f"Error should indicate {health_status} status"
        else:
            # Should be allowed
            allocation = manager.checkout(checkout_request, user_id)
            assert allocation is not None, \
                f"Checkout should succeed for {health_status} resource"
            assert allocation.resource_id == resource_id, \
                "Allocation should be for the correct resource"


def test_property_availability_check_health_status():
    """
    **Feature: resources, Property 12: Health Status Allocation Blocking**
    **Validates: Requirements 6.3**
    
    Property test: For any randomly generated resource with any health status,
    check_availability should return False for 'offline' and 'maintenance',
    and True for 'online' and 'degraded'.
    """
    blocked_statuses = {'offline', 'maintenance'}
    allowed_statuses = {'online', 'degraded'}
    all_statuses = list(blocked_statuses | allowed_statuses)
    
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        health_status = random.choice(all_statuses)
        mode = random.choice(['exclusive', 'shared'])
        
        # Create mock resource with random health status
        mock_resource = create_mock_resource(resource_id, resource_name, health_status=health_status)
        
        # Check availability
        mock_session = create_mock_session_for_availability_check(mock_resource, [])
        manager = AllocationManager(mock_session)
        
        available = manager.check_availability(resource_id, mode=mode)
        
        if health_status in blocked_statuses:
            assert not available, \
                f"Resource with {health_status} status should not be available"
        else:
            assert available, \
                f"Resource with {health_status} status should be available"

