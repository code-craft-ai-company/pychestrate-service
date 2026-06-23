"""
.. module:: test_allocation_manager_reservation_activation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for AllocationManager reservation activation property

.. moduleauthor:: Code Craft AI LLC

Tests for reservation activation property in the AllocationManager.

**Feature: resources**
**Property 11: Reservation Activation**
**Validates: Requirements 5.3**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid
from datetime import datetime, timezone, timedelta

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.allocation_manager import (
    AllocationManager,
    ReservationRequest,
    ReservationResponse,
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


def utc_now():
    """Get current UTC time."""
    return datetime.now(timezone.utc)


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


def create_mock_reservation(reservation_id, resource_id, user_id, start_time, end_time, 
                            mode='exclusive', status='pending'):
    """Create a mock reservation object matching the Reservation ORM model."""
    mock_reservation = Mock()
    mock_reservation.configure(recursive=True)
    ctx = mock_reservation.mock_context()
    ctx.set_attribute('id', reservation_id)
    ctx.set_attribute('resource_id', resource_id)
    ctx.set_attribute('user_id', user_id)
    ctx.set_attribute('job_id', None)
    ctx.set_attribute('start_time', start_time)
    ctx.set_attribute('end_time', end_time)
    ctx.set_attribute('mode', mode)
    ctx.set_attribute('status', status)
    ctx.set_attribute('reason', '')
    ctx.set_attribute('created_at', utc_now())
    ctx.set_attribute('allocation_id', None)
    return mock_reservation


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
    ctx.set_attribute('checkout_time', utc_now())
    ctx.set_attribute('expected_checkin', None)
    ctx.set_attribute('actual_checkin', None)
    ctx.set_attribute('duration_minutes', None)
    ctx.set_attribute('reason', '')
    ctx.set_attribute('forced_by_id', None)
    ctx.set_attribute('force_reason', None)
    ctx.set_attribute('metadata_snapshot', {'key': 'value'})
    return mock_allocation


def create_mock_session_for_activation(due_reservations, resources_map, active_allocations_map=None):
    """
    Create a mock session for reservation activation.
    
    Query flow for activate_due_reservations:
    1. Query Reservation to find due reservations
    2. For each reservation:
       a. Query Resource to get resource details
       b. Query Allocation to check for active allocations
       c. Add new allocation
    3. Commit
    
    :param due_reservations: List of mock reservations that are due
    :param resources_map: Dict mapping resource_id to mock resource
    :param active_allocations_map: Dict mapping resource_id to list of active allocations
    """
    active_allocations_map = active_allocations_map or {}
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    allocation_id_counter = [100]  # Start allocation IDs at 100
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        
        def create_filter_chain(final_result, is_list=False):
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            def filter_side_effect(*args, **kwargs):
                return create_filter_chain(final_result, is_list)
            
            mock_filter.mock_context().mock_method('filter', side_effect=filter_side_effect)
            
            if is_list:
                mock_filter.mock_context().mock_method('all', return_value=final_result)
            else:
                mock_filter.mock_context().mock_method('first', return_value=final_result)
            
            return mock_filter
        
        # First call is for finding due reservations
        if call_count[0] == 1:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(due_reservations, is_list=True))
        else:
            # Subsequent calls alternate between Resource and Allocation queries
            # We need to determine which based on the model being queried
            # For simplicity, we'll use a pattern: Resource, Allocation, Resource, Allocation...
            # But since we can't easily detect the model, we'll use call count
            
            # After the first call, we have pairs of (Resource, Allocation) for each reservation
            # Plus additional Resource queries for response building
            pair_index = (call_count[0] - 2) // 2
            is_resource_query = (call_count[0] - 2) % 2 == 0
            
            if pair_index < len(due_reservations):
                reservation = due_reservations[pair_index]
                resource_id = reservation.resource_id
                
                if is_resource_query:
                    resource = resources_map.get(resource_id)
                    mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(resource, is_list=False))
                else:
                    allocations = active_allocations_map.get(resource_id, [])
                    mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(allocations, is_list=True))
            else:
                # Default to empty result
                mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(None, is_list=False))
        
        return mock_query
    
    def add_side_effect(obj):
        # Simulate setting the ID on the allocation
        if hasattr(obj, 'id') and obj.id is None:
            obj.id = allocation_id_counter[0]
            allocation_id_counter[0] += 1
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add', side_effect=add_side_effect)
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Reservation Activation Tests - Property 11
# =============================================================================

def test_reservation_activation_basic():
    """
    **Feature: resources, Property 11: Reservation Activation**
    **Validates: Requirements 5.3**
    
    For any pending reservation whose start time has arrived, the reservation
    should be automatically converted to an active allocation.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Create a reservation that is due (start time in the past)
    start_time = now - timedelta(minutes=5)
    end_time = now + timedelta(hours=1)
    
    mock_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        mode='exclusive',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    mock_session = create_mock_session_for_activation(
        due_reservations=[mock_reservation],
        resources_map={resource_id: mock_resource},
        active_allocations_map={resource_id: []}
    )
    
    manager = AllocationManager(mock_session)
    
    count = manager.activate_due_reservations()
    
    assert count == 1, "Should have activated 1 reservation"
    assert mock_reservation.status == 'active', "Reservation status should be 'active'"
    assert mock_reservation.allocation_id is not None, "Reservation should have allocation_id set"


def test_reservation_activation_not_due():
    """
    **Feature: resources, Property 11: Reservation Activation**
    **Validates: Requirements 5.3**
    
    Reservations whose start time has not arrived should not be activated.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Create a reservation that is NOT due (start time in the future)
    start_time = now + timedelta(hours=1)
    end_time = now + timedelta(hours=2)
    
    mock_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        mode='exclusive',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # No due reservations returned by query
    mock_session = create_mock_session_for_activation(
        due_reservations=[],  # Empty because start_time > now
        resources_map={resource_id: mock_resource},
        active_allocations_map={}
    )
    
    manager = AllocationManager(mock_session)
    
    count = manager.activate_due_reservations()
    
    assert count == 0, "Should not have activated any reservations"


def test_reservation_activation_resource_offline():
    """
    **Feature: resources, Property 11: Reservation Activation**
    **Validates: Requirements 5.3**
    
    Reservations for offline resources should not be activated.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Create a due reservation
    start_time = now - timedelta(minutes=5)
    end_time = now + timedelta(hours=1)
    
    mock_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        mode='exclusive',
        status='pending'
    )
    
    # Resource is offline
    mock_resource = create_mock_resource(resource_id, resource_name, health_status='offline')
    
    mock_session = create_mock_session_for_activation(
        due_reservations=[mock_reservation],
        resources_map={resource_id: mock_resource},
        active_allocations_map={resource_id: []}
    )
    
    manager = AllocationManager(mock_session)
    
    count = manager.activate_due_reservations()
    
    assert count == 0, "Should not have activated reservation for offline resource"
    assert mock_reservation.status == 'pending', "Reservation should still be pending"


def test_reservation_activation_resource_has_active_allocation():
    """
    **Feature: resources, Property 11: Reservation Activation**
    **Validates: Requirements 5.3**
    
    Exclusive reservations should not be activated if resource has active allocations.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Create a due reservation
    start_time = now - timedelta(minutes=5)
    end_time = now + timedelta(hours=1)
    
    mock_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        mode='exclusive',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Resource has an active allocation
    existing_allocation = create_mock_allocation(
        allocation_id=50,
        resource_id=resource_id,
        user_id=generate_user_id(),
        mode='exclusive',
        status='active'
    )
    
    mock_session = create_mock_session_for_activation(
        due_reservations=[mock_reservation],
        resources_map={resource_id: mock_resource},
        active_allocations_map={resource_id: [existing_allocation]}
    )
    
    manager = AllocationManager(mock_session)
    
    count = manager.activate_due_reservations()
    
    assert count == 0, "Should not have activated reservation due to existing allocation"
    assert mock_reservation.status == 'pending', "Reservation should still be pending"


def test_reservation_activation_multiple_reservations():
    """
    **Feature: resources, Property 11: Reservation Activation**
    **Validates: Requirements 5.3**
    
    Multiple due reservations for different resources should all be activated.
    """
    now = utc_now()
    
    # Create multiple due reservations for different resources
    reservations = []
    resources_map = {}
    
    for i in range(3):
        resource_id = i + 1
        user_id = generate_user_id()
        
        mock_reservation = create_mock_reservation(
            reservation_id=i + 1,
            resource_id=resource_id,
            user_id=user_id,
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(hours=1),
            mode='exclusive',
            status='pending'
        )
        reservations.append(mock_reservation)
        
        mock_resource = create_mock_resource(resource_id, generate_unique_name())
        resources_map[resource_id] = mock_resource
    
    mock_session = create_mock_session_for_activation(
        due_reservations=reservations,
        resources_map=resources_map,
        active_allocations_map={1: [], 2: [], 3: []}
    )
    
    manager = AllocationManager(mock_session)
    
    count = manager.activate_due_reservations()
    
    assert count == 3, "Should have activated all 3 reservations"
    for reservation in reservations:
        assert reservation.status == 'active', "All reservations should be active"


def test_reservation_activation_shared_mode():
    """
    **Feature: resources, Property 11: Reservation Activation**
    **Validates: Requirements 5.3**
    
    Shared reservations should be activated even if resource has other shared allocations.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Create a due shared reservation
    start_time = now - timedelta(minutes=5)
    end_time = now + timedelta(hours=1)
    
    mock_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        mode='shared',
        status='pending'
    )
    
    # Resource with capacity 5
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=5)
    
    # Resource has 2 active shared allocations (under capacity)
    existing_allocations = [
        create_mock_allocation(50, resource_id, generate_user_id(), mode='shared', status='active'),
        create_mock_allocation(51, resource_id, generate_user_id(), mode='shared', status='active'),
    ]
    
    mock_session = create_mock_session_for_activation(
        due_reservations=[mock_reservation],
        resources_map={resource_id: mock_resource},
        active_allocations_map={resource_id: existing_allocations}
    )
    
    manager = AllocationManager(mock_session)
    
    count = manager.activate_due_reservations()
    
    assert count == 1, "Should have activated shared reservation"
    assert mock_reservation.status == 'active', "Reservation should be active"


def test_property_reservation_activation_random():
    """
    **Feature: resources, Property 11: Reservation Activation**
    **Validates: Requirements 5.3**
    
    Property test: For any randomly generated due reservations with available resources,
    they should be activated.
    """
    for _ in range(100):
        now = utc_now()
        
        resource_id = random.randint(1, 1000)
        user_id = generate_user_id()
        
        # Random time offset (always in the past for due reservations)
        minutes_ago = random.randint(1, 60)
        duration_hours = random.randint(1, 8)
        
        start_time = now - timedelta(minutes=minutes_ago)
        end_time = now + timedelta(hours=duration_hours)
        
        mode = random.choice(['exclusive', 'shared'])
        capacity = random.randint(1, 10) if mode == 'shared' else 1
        
        mock_reservation = create_mock_reservation(
            reservation_id=1,
            resource_id=resource_id,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            mode=mode,
            status='pending'
        )
        
        mock_resource = create_mock_resource(resource_id, generate_unique_name(), capacity=capacity)
        
        mock_session = create_mock_session_for_activation(
            due_reservations=[mock_reservation],
            resources_map={resource_id: mock_resource},
            active_allocations_map={resource_id: []}
        )
        
        manager = AllocationManager(mock_session)
        
        count = manager.activate_due_reservations()
        
        assert count == 1, f"Should have activated reservation (mode={mode})"
        assert mock_reservation.status == 'active', "Reservation should be active"
        assert mock_reservation.allocation_id is not None, "Should have allocation_id"


def test_reservation_activation_preserves_parameters():
    """
    **Feature: resources, Property 11: Reservation Activation**
    **Validates: Requirements 5.3**
    
    When a reservation is activated, the allocation should have the same parameters.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    job_id = "test-job-123"
    
    now = utc_now()
    
    start_time = now - timedelta(minutes=5)
    end_time = now + timedelta(hours=2)
    
    mock_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=user_id,
        start_time=start_time,
        end_time=end_time,
        mode='exclusive',
        status='pending'
    )
    mock_reservation.job_id = job_id
    mock_reservation.reason = "Test reservation"
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Track the allocation that gets created
    created_allocations = []
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        
        def create_filter_chain(final_result, is_list=False):
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            def filter_side_effect(*args, **kwargs):
                return create_filter_chain(final_result, is_list)
            
            mock_filter.mock_context().mock_method('filter', side_effect=filter_side_effect)
            
            if is_list:
                mock_filter.mock_context().mock_method('all', return_value=final_result)
            else:
                mock_filter.mock_context().mock_method('first', return_value=final_result)
            
            return mock_filter
        
        if call_count[0] == 1:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain([mock_reservation], is_list=True))
        elif call_count[0] == 2:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(mock_resource, is_list=False))
        elif call_count[0] == 3:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain([], is_list=True))
        else:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(None, is_list=False))
        
        return mock_query
    
    def add_side_effect(obj):
        obj.id = 100
        created_allocations.append(obj)
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add', side_effect=add_side_effect)
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    manager = AllocationManager(mock_session)
    
    count = manager.activate_due_reservations()
    
    assert count == 1, "Should have activated 1 reservation"
    assert len(created_allocations) == 1, "Should have created 1 allocation"
    
    allocation = created_allocations[0]
    assert allocation.resource_id == resource_id, "Allocation should have same resource_id"
    assert allocation.user_id == user_id, "Allocation should have same user_id"
    assert allocation.job_id == job_id, "Allocation should have same job_id"
    assert allocation.mode == 'exclusive', "Allocation should have same mode"
    assert allocation.expected_checkin == end_time, "Allocation expected_checkin should be reservation end_time"

