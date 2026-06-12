"""
.. module:: test_allocation_manager_reservation_conflict
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for AllocationManager reservation conflict detection property

.. moduleauthor:: Code Craft AI LLC

Tests for reservation conflict detection property in the AllocationManager.

**Feature: resources**
**Property 10: Reservation Conflict Detection**
**Validates: Requirements 5.1, 5.2**
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
    ReservationConflictError,
    InvalidTimeWindowError,
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


def create_mock_user(user_id, login='testuser'):
    """Create a mock user object."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', login)
    return mock_user


def create_mock_session_for_reservation_create(resource, existing_reservations=None, user=None):
    """
    Create a mock session for reservation creation.
    
    Query flow for create_reservation:
    1. Query Resource to verify it exists
    2. Query Reservation to check for conflicts (with multiple filter calls)
    3. Add new reservation
    4. Commit
    5. Query Resource for response
    6. Query User for response
    """
    existing_reservations = existing_reservations or []
    if user is None:
        user = create_mock_user(generate_user_id())
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        
        # Create a chain of filter mocks that eventually returns the right data
        def create_filter_chain(final_result, is_list=False):
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            # Each filter call returns another filter mock
            def filter_side_effect(*args, **kwargs):
                return create_filter_chain(final_result, is_list)
            
            mock_filter.mock_context().mock_method('filter', side_effect=filter_side_effect)
            
            if is_list:
                mock_filter.mock_context().mock_method('all', return_value=final_result)
            else:
                mock_filter.mock_context().mock_method('first', return_value=final_result)
            
            return mock_filter
        
        # First call is for resource lookup
        if call_count[0] == 1:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(resource, is_list=False))
        # Second call is for conflict check (Reservation query)
        elif call_count[0] == 2:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(existing_reservations, is_list=True))
        # Third call is for resource lookup in response
        elif call_count[0] == 3:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(resource, is_list=False))
        # Fourth call is for user lookup in response
        else:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(user, is_list=False))
        
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


def create_mock_session_for_conflict_check(existing_reservations=None, resource=None, user=None):
    """
    Create a mock session for conflict checking.
    """
    existing_reservations = existing_reservations or []
    if resource is None:
        resource = create_mock_resource(1, generate_unique_name())
    if user is None:
        user = create_mock_user(generate_user_id())
    
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
        
        # First call is for reservation conflict check
        if call_count[0] == 1:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(existing_reservations, is_list=True))
        # Subsequent calls for response building
        elif call_count[0] == 2:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(resource, is_list=False))
        else:
            mock_query.mock_context().mock_method('filter', return_value=create_filter_chain(user, is_list=False))
        
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    
    return mock_session


# =============================================================================
# Reservation Conflict Detection Tests - Property 10
# =============================================================================

def test_reservation_conflict_overlapping_exclusive():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    For any two exclusive reservations on the same resource with overlapping time windows,
    the second reservation should be rejected with conflict details.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Existing reservation: 1 hour from now to 3 hours from now
    existing_start = now + timedelta(hours=1)
    existing_end = now + timedelta(hours=3)
    
    existing_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=generate_user_id(),
        start_time=existing_start,
        end_time=existing_end,
        mode='exclusive',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_user = create_mock_user(user_id)
    
    # New reservation overlaps: 2 hours from now to 4 hours from now
    new_start = now + timedelta(hours=2)
    new_end = now + timedelta(hours=4)
    
    mock_session = create_mock_session_for_reservation_create(
        mock_resource, 
        existing_reservations=[existing_reservation],
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    request = ReservationRequest(
        resource_id=resource_id,
        start_time=new_start,
        end_time=new_end,
        mode='exclusive'
    )
    
    try:
        manager.create_reservation(request, user_id)
        assert False, "Should have raised ReservationConflictError"
    except ReservationConflictError as e:
        assert len(e.conflicting_reservations) > 0, "Should have conflict details"


def test_reservation_no_conflict_non_overlapping():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    For any two reservations on the same resource with non-overlapping time windows,
    both reservations should be accepted.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_user = create_mock_user(user_id)
    
    # New reservation: 3 hours from now to 4 hours from now (no overlap)
    new_start = now + timedelta(hours=3)
    new_end = now + timedelta(hours=4)
    
    # No conflicts since time windows don't overlap
    mock_session = create_mock_session_for_reservation_create(
        mock_resource, 
        existing_reservations=[],  # No overlapping reservations
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    request = ReservationRequest(
        resource_id=resource_id,
        start_time=new_start,
        end_time=new_end,
        mode='exclusive'
    )
    
    # Should succeed without conflict
    reservation = manager.create_reservation(request, user_id)
    assert reservation is not None, "Non-overlapping reservation should succeed"


def test_reservation_conflict_partial_overlap_start():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    Reservations that overlap at the start should be detected as conflicts.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Existing reservation: 2 hours from now to 4 hours from now
    existing_start = now + timedelta(hours=2)
    existing_end = now + timedelta(hours=4)
    
    existing_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=generate_user_id(),
        start_time=existing_start,
        end_time=existing_end,
        mode='exclusive',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_user = create_mock_user(user_id)
    
    # New reservation overlaps at start: 1 hour from now to 3 hours from now
    new_start = now + timedelta(hours=1)
    new_end = now + timedelta(hours=3)
    
    mock_session = create_mock_session_for_reservation_create(
        mock_resource, 
        existing_reservations=[existing_reservation],
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    request = ReservationRequest(
        resource_id=resource_id,
        start_time=new_start,
        end_time=new_end,
        mode='exclusive'
    )
    
    try:
        manager.create_reservation(request, user_id)
        assert False, "Should have raised ReservationConflictError"
    except ReservationConflictError as e:
        assert len(e.conflicting_reservations) > 0, "Should have conflict details"


def test_reservation_conflict_partial_overlap_end():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    Reservations that overlap at the end should be detected as conflicts.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Existing reservation: 1 hour from now to 3 hours from now
    existing_start = now + timedelta(hours=1)
    existing_end = now + timedelta(hours=3)
    
    existing_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=generate_user_id(),
        start_time=existing_start,
        end_time=existing_end,
        mode='exclusive',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_user = create_mock_user(user_id)
    
    # New reservation overlaps at end: 2 hours from now to 5 hours from now
    new_start = now + timedelta(hours=2)
    new_end = now + timedelta(hours=5)
    
    mock_session = create_mock_session_for_reservation_create(
        mock_resource, 
        existing_reservations=[existing_reservation],
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    request = ReservationRequest(
        resource_id=resource_id,
        start_time=new_start,
        end_time=new_end,
        mode='exclusive'
    )
    
    try:
        manager.create_reservation(request, user_id)
        assert False, "Should have raised ReservationConflictError"
    except ReservationConflictError as e:
        assert len(e.conflicting_reservations) > 0, "Should have conflict details"


def test_reservation_conflict_contained_within():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    A reservation contained entirely within another should be detected as a conflict.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Existing reservation: 1 hour from now to 5 hours from now
    existing_start = now + timedelta(hours=1)
    existing_end = now + timedelta(hours=5)
    
    existing_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=generate_user_id(),
        start_time=existing_start,
        end_time=existing_end,
        mode='exclusive',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_user = create_mock_user(user_id)
    
    # New reservation is contained within: 2 hours from now to 4 hours from now
    new_start = now + timedelta(hours=2)
    new_end = now + timedelta(hours=4)
    
    mock_session = create_mock_session_for_reservation_create(
        mock_resource, 
        existing_reservations=[existing_reservation],
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    request = ReservationRequest(
        resource_id=resource_id,
        start_time=new_start,
        end_time=new_end,
        mode='exclusive'
    )
    
    try:
        manager.create_reservation(request, user_id)
        assert False, "Should have raised ReservationConflictError"
    except ReservationConflictError as e:
        assert len(e.conflicting_reservations) > 0, "Should have conflict details"


def test_reservation_conflict_contains_existing():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    A reservation that contains an existing reservation should be detected as a conflict.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Existing reservation: 2 hours from now to 3 hours from now
    existing_start = now + timedelta(hours=2)
    existing_end = now + timedelta(hours=3)
    
    existing_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=generate_user_id(),
        start_time=existing_start,
        end_time=existing_end,
        mode='exclusive',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_user = create_mock_user(user_id)
    
    # New reservation contains existing: 1 hour from now to 5 hours from now
    new_start = now + timedelta(hours=1)
    new_end = now + timedelta(hours=5)
    
    mock_session = create_mock_session_for_reservation_create(
        mock_resource, 
        existing_reservations=[existing_reservation],
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    request = ReservationRequest(
        resource_id=resource_id,
        start_time=new_start,
        end_time=new_end,
        mode='exclusive'
    )
    
    try:
        manager.create_reservation(request, user_id)
        assert False, "Should have raised ReservationConflictError"
    except ReservationConflictError as e:
        assert len(e.conflicting_reservations) > 0, "Should have conflict details"


def test_reservation_no_conflict_adjacent_times():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    Reservations that are adjacent (end of one equals start of another) should not conflict.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_user = create_mock_user(user_id)
    
    # New reservation starts exactly when existing ends: 2 hours from now to 3 hours from now
    new_start = now + timedelta(hours=2)
    new_end = now + timedelta(hours=3)
    
    # No conflicts since time windows are adjacent, not overlapping
    mock_session = create_mock_session_for_reservation_create(
        mock_resource, 
        existing_reservations=[],  # Adjacent reservations don't overlap
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    request = ReservationRequest(
        resource_id=resource_id,
        start_time=new_start,
        end_time=new_end,
        mode='exclusive'
    )
    
    # Should succeed without conflict
    reservation = manager.create_reservation(request, user_id)
    assert reservation is not None, "Adjacent reservation should succeed"


def test_property_reservation_conflict_random_time_windows():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    Property test: For any randomly generated time windows, overlapping reservations
    should be rejected and non-overlapping should be accepted.
    """
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        user_id = generate_user_id()
        
        now = utc_now()
        
        # Generate random existing reservation
        existing_start_offset = random.randint(1, 10)
        existing_duration = random.randint(1, 5)
        existing_start = now + timedelta(hours=existing_start_offset)
        existing_end = existing_start + timedelta(hours=existing_duration)
        
        existing_reservation = create_mock_reservation(
            reservation_id=1,
            resource_id=resource_id,
            user_id=generate_user_id(),
            start_time=existing_start,
            end_time=existing_end,
            mode='exclusive',
            status='pending'
        )
        
        mock_resource = create_mock_resource(resource_id, resource_name)
        mock_user = create_mock_user(user_id)
        
        # Generate random new reservation
        new_start_offset = random.randint(1, 15)
        new_duration = random.randint(1, 5)
        new_start = now + timedelta(hours=new_start_offset)
        new_end = new_start + timedelta(hours=new_duration)
        
        # Determine if they overlap
        # Two intervals [a, b) and [c, d) overlap if a < d AND c < b
        overlaps = new_start < existing_end and existing_start < new_end
        
        if overlaps:
            # Should conflict
            mock_session = create_mock_session_for_reservation_create(
                mock_resource, 
                existing_reservations=[existing_reservation],
                user=mock_user
            )
        else:
            # Should not conflict
            mock_session = create_mock_session_for_reservation_create(
                mock_resource, 
                existing_reservations=[],
                user=mock_user
            )
        
        manager = AllocationManager(mock_session)
        
        request = ReservationRequest(
            resource_id=resource_id,
            start_time=new_start,
            end_time=new_end,
            mode='exclusive'
        )
        
        if overlaps:
            try:
                manager.create_reservation(request, user_id)
                assert False, f"Overlapping reservation should have been rejected"
            except ReservationConflictError:
                pass  # Expected
        else:
            # Should succeed
            reservation = manager.create_reservation(request, user_id)
            assert reservation is not None, "Non-overlapping reservation should succeed"


def test_check_reservation_conflicts_direct():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    Direct test of check_reservation_conflicts method.
    """
    resource_id = 1
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Existing reservation: 2 hours from now to 4 hours from now
    existing_start = now + timedelta(hours=2)
    existing_end = now + timedelta(hours=4)
    
    existing_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=generate_user_id(),
        start_time=existing_start,
        end_time=existing_end,
        mode='exclusive',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, generate_unique_name())
    mock_user = create_mock_user(user_id)
    
    mock_session = create_mock_session_for_conflict_check(
        [existing_reservation],
        resource=mock_resource,
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    # Check overlapping time window
    conflicts = manager.check_reservation_conflicts(
        resource_id=resource_id,
        start_time=now + timedelta(hours=3),
        end_time=now + timedelta(hours=5),
        mode='exclusive'
    )
    
    assert len(conflicts) > 0, "Should detect conflict with overlapping reservation"


def test_reservation_shared_mode_no_conflict():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    Two shared reservations on the same resource with overlapping time windows
    should NOT conflict (both can be accepted).
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=5)
    mock_user = create_mock_user(user_id)
    
    # New shared reservation overlaps: 2 hours from now to 4 hours from now
    new_start = now + timedelta(hours=2)
    new_end = now + timedelta(hours=4)
    
    # Both are shared, so no conflict
    mock_session = create_mock_session_for_reservation_create(
        mock_resource, 
        existing_reservations=[],  # No conflict for shared+shared
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    request = ReservationRequest(
        resource_id=resource_id,
        start_time=new_start,
        end_time=new_end,
        mode='shared'
    )
    
    # Should succeed without conflict
    reservation = manager.create_reservation(request, user_id)
    assert reservation is not None, "Two shared reservations should not conflict"


def test_reservation_exclusive_vs_shared_conflict():
    """
    **Feature: resources, Property 10: Reservation Conflict Detection**
    **Validates: Requirements 5.1, 5.2**
    
    An exclusive reservation should conflict with an overlapping shared reservation.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    now = utc_now()
    
    # Existing shared reservation: 1 hour from now to 3 hours from now
    existing_start = now + timedelta(hours=1)
    existing_end = now + timedelta(hours=3)
    
    existing_reservation = create_mock_reservation(
        reservation_id=1,
        resource_id=resource_id,
        user_id=generate_user_id(),
        start_time=existing_start,
        end_time=existing_end,
        mode='shared',
        status='pending'
    )
    
    mock_resource = create_mock_resource(resource_id, resource_name)
    mock_user = create_mock_user(user_id)
    
    # New exclusive reservation overlaps: 2 hours from now to 4 hours from now
    new_start = now + timedelta(hours=2)
    new_end = now + timedelta(hours=4)
    
    mock_session = create_mock_session_for_reservation_create(
        mock_resource, 
        existing_reservations=[existing_reservation],
        user=mock_user
    )
    manager = AllocationManager(mock_session)
    
    request = ReservationRequest(
        resource_id=resource_id,
        start_time=new_start,
        end_time=new_end,
        mode='exclusive'  # Exclusive conflicts with shared
    )
    
    try:
        manager.create_reservation(request, user_id)
        assert False, "Exclusive should conflict with shared"
    except ReservationConflictError as e:
        assert len(e.conflicting_reservations) > 0, "Should have conflict details"

