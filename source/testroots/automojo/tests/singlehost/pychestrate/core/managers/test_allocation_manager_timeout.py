"""
.. module:: test_allocation_manager_timeout
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for AllocationManager allocation timeout expiration

.. moduleauthor:: Automation Mojo LLC

Tests for allocation timeout expiration in the AllocationManager.

**Feature: resources**
**Property 8: Allocation Timeout Expiration**
**Validates: Requirements 3.6**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid
from datetime import datetime, timezone, timedelta

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.allocation_manager import (
    AllocationManager,
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


def create_mock_allocation_with_timeout(allocation_id, resource_id, user_id, 
                                        checkout_time, expected_checkin, status='active'):
    """Create a mock allocation with specific timeout settings."""
    mock_allocation = Mock()
    mock_allocation.configure(recursive=True)
    ctx = mock_allocation.mock_context()
    ctx.set_attribute('id', allocation_id)
    ctx.set_attribute('resource_id', resource_id)
    ctx.set_attribute('user_id', user_id)
    ctx.set_attribute('job_id', None)
    ctx.set_attribute('mode', 'exclusive')
    ctx.set_attribute('status', status)
    ctx.set_attribute('checkout_time', checkout_time)
    ctx.set_attribute('expected_checkin', expected_checkin)
    ctx.set_attribute('actual_checkin', None)
    ctx.set_attribute('duration_minutes', None)
    ctx.set_attribute('reason', '')
    ctx.set_attribute('forced_by_id', None)
    ctx.set_attribute('force_reason', None)
    ctx.set_attribute('metadata_snapshot', {})
    return mock_allocation


def create_mock_session_for_expiration(expired_allocations, non_expired_allocations=None):
    """Create a mock session for expiration check."""
    non_expired_allocations = non_expired_allocations or []
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    def query_side_effect(model):
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # Return expired allocations for the filter query
        mock_filter.mock_context().mock_method('all', return_value=expired_allocations)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Allocation Timeout Expiration Tests - Property 8
# =============================================================================

def test_expired_allocation_is_released():
    """
    **Feature: resources, Property 8: Allocation Timeout Expiration**
    **Validates: Requirements 3.6**
    
    An allocation that has exceeded its timeout should be automatically released.
    """
    now = datetime.now(timezone.utc)
    past_time = now - timedelta(hours=2)
    expired_time = now - timedelta(hours=1)
    
    allocation_id = 1
    resource_id = 1
    user_id = generate_user_id()
    
    # Create expired allocation
    mock_allocation = create_mock_allocation_with_timeout(
        allocation_id, resource_id, user_id,
        checkout_time=past_time,
        expected_checkin=expired_time,
        status='active'
    )
    
    mock_session = create_mock_session_for_expiration([mock_allocation])
    manager = AllocationManager(mock_session)
    
    # Run expiration
    expired_count = manager.expire_timed_out_allocations()
    
    assert expired_count == 1, "One allocation should be expired"
    assert mock_allocation.status == 'expired', "Allocation status should be 'expired'"
    assert mock_allocation.actual_checkin is not None, "Actual checkin time should be set"


def test_non_expired_allocation_not_released():
    """
    **Feature: resources, Property 8: Allocation Timeout Expiration**
    **Validates: Requirements 3.6**
    
    An allocation that has not exceeded its timeout should not be released.
    """
    now = datetime.now(timezone.utc)
    past_time = now - timedelta(hours=1)
    future_time = now + timedelta(hours=1)
    
    allocation_id = 1
    resource_id = 1
    user_id = generate_user_id()
    
    # Create non-expired allocation (expected_checkin is in the future)
    mock_allocation = create_mock_allocation_with_timeout(
        allocation_id, resource_id, user_id,
        checkout_time=past_time,
        expected_checkin=future_time,
        status='active'
    )
    
    # Session returns no expired allocations
    mock_session = create_mock_session_for_expiration([])
    manager = AllocationManager(mock_session)
    
    # Run expiration
    expired_count = manager.expire_timed_out_allocations()
    
    assert expired_count == 0, "No allocations should be expired"


def test_allocation_without_timeout_not_released():
    """
    **Feature: resources, Property 8: Allocation Timeout Expiration**
    **Validates: Requirements 3.6**
    
    An allocation without a timeout (expected_checkin is None) should not be released.
    """
    now = datetime.now(timezone.utc)
    past_time = now - timedelta(hours=2)
    
    allocation_id = 1
    resource_id = 1
    user_id = generate_user_id()
    
    # Create allocation without timeout
    mock_allocation = create_mock_allocation_with_timeout(
        allocation_id, resource_id, user_id,
        checkout_time=past_time,
        expected_checkin=None,  # No timeout
        status='active'
    )
    
    # Session returns no expired allocations (since expected_checkin is None)
    mock_session = create_mock_session_for_expiration([])
    manager = AllocationManager(mock_session)
    
    # Run expiration
    expired_count = manager.expire_timed_out_allocations()
    
    assert expired_count == 0, "Allocation without timeout should not be expired"


def test_property_timeout_expiration_random():
    """
    **Feature: resources, Property 8: Allocation Timeout Expiration**
    **Validates: Requirements 3.6**
    
    Property test: For any set of allocations, only those with expired timeouts
    should be released.
    """
    for _ in range(100):
        now = datetime.now(timezone.utc)
        
        # Generate random number of expired and non-expired allocations
        num_expired = random.randint(0, 5)
        num_non_expired = random.randint(0, 5)
        
        expired_allocations = []
        for i in range(num_expired):
            past_time = now - timedelta(hours=random.randint(2, 10))
            expired_time = now - timedelta(minutes=random.randint(1, 60))
            
            mock_allocation = create_mock_allocation_with_timeout(
                allocation_id=i + 1,
                resource_id=random.randint(1, 100),
                user_id=generate_user_id(),
                checkout_time=past_time,
                expected_checkin=expired_time,
                status='active'
            )
            expired_allocations.append(mock_allocation)
        
        mock_session = create_mock_session_for_expiration(expired_allocations)
        manager = AllocationManager(mock_session)
        
        # Run expiration
        expired_count = manager.expire_timed_out_allocations()
        
        assert expired_count == num_expired, \
            f"Expected {num_expired} expired, got {expired_count}"
        
        # Verify all expired allocations have correct status
        for alloc in expired_allocations:
            assert alloc.status == 'expired', "Expired allocation should have 'expired' status"
            assert alloc.actual_checkin is not None, "Expired allocation should have actual_checkin set"


def test_duration_calculated_on_expiration():
    """
    **Feature: resources, Property 8: Allocation Timeout Expiration**
    **Validates: Requirements 3.6**
    
    When an allocation expires, the duration should be calculated.
    """
    now = datetime.now(timezone.utc)
    checkout_time = now - timedelta(hours=2)
    expired_time = now - timedelta(hours=1)
    
    allocation_id = 1
    resource_id = 1
    user_id = generate_user_id()
    
    mock_allocation = create_mock_allocation_with_timeout(
        allocation_id, resource_id, user_id,
        checkout_time=checkout_time,
        expected_checkin=expired_time,
        status='active'
    )
    
    mock_session = create_mock_session_for_expiration([mock_allocation])
    manager = AllocationManager(mock_session)
    
    # Run expiration
    manager.expire_timed_out_allocations()
    
    # Duration should be calculated (approximately 2 hours = 120 minutes)
    assert mock_allocation.duration_minutes is not None, "Duration should be calculated"
    assert mock_allocation.duration_minutes >= 119, "Duration should be approximately 120 minutes"


def test_multiple_expired_allocations():
    """
    **Feature: resources, Property 8: Allocation Timeout Expiration**
    **Validates: Requirements 3.6**
    
    Multiple expired allocations should all be released.
    """
    now = datetime.now(timezone.utc)
    
    expired_allocations = []
    for i in range(5):
        past_time = now - timedelta(hours=i + 2)
        expired_time = now - timedelta(minutes=i + 1)
        
        mock_allocation = create_mock_allocation_with_timeout(
            allocation_id=i + 1,
            resource_id=i + 1,
            user_id=generate_user_id(),
            checkout_time=past_time,
            expected_checkin=expired_time,
            status='active'
        )
        expired_allocations.append(mock_allocation)
    
    mock_session = create_mock_session_for_expiration(expired_allocations)
    manager = AllocationManager(mock_session)
    
    # Run expiration
    expired_count = manager.expire_timed_out_allocations()
    
    assert expired_count == 5, "All 5 allocations should be expired"
    
    for alloc in expired_allocations:
        assert alloc.status == 'expired', "All allocations should have 'expired' status"

