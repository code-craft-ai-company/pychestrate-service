"""
.. module:: test_allocation_manager_exclusive
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for AllocationManager exclusive allocation enforcement

.. moduleauthor:: Code Craft AI LLC

Tests for exclusive allocation enforcement in the AllocationManager.

**Feature: resources**
**Property 6: Exclusive Allocation Enforcement**
**Validates: Requirements 3.2**
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


def create_mock_user(user_id, login='testuser'):
    """Create a mock user object."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', login)
    return mock_user


def create_mock_session_for_checkout_with_existing_allocation(resource, existing_allocations):
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
# Exclusive Allocation Enforcement Tests - Property 6
# =============================================================================

def test_exclusive_allocation_blocks_second_checkout():
    """
    **Feature: resources, Property 6: Exclusive Allocation Enforcement**
    **Validates: Requirements 3.2**
    
    For any resource with an active exclusive allocation, subsequent checkout
    requests for that resource should be rejected.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user1_id = generate_user_id()
    user2_id = generate_user_id()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Create existing exclusive allocation
    existing_allocation = create_mock_allocation(1, resource_id, user1_id, mode='exclusive', status='active')
    
    # Create mock session with existing allocation
    mock_session = create_mock_session_for_checkout_with_existing_allocation(
        mock_resource, [existing_allocation]
    )
    
    manager = AllocationManager(mock_session)
    
    # Attempt second checkout
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive",
        reason="Second checkout attempt"
    )
    
    checkout_rejected = False
    current_allocation_returned = False
    
    try:
        manager.checkout(checkout_request, user2_id)
    except ResourceUnavailableError as e:
        checkout_rejected = True
        if e.current_allocation is not None:
            current_allocation_returned = True
    
    assert checkout_rejected, "Second exclusive checkout should be rejected"
    assert current_allocation_returned, "Current allocation details should be returned"


def test_exclusive_allocation_blocks_shared_checkout():
    """
    **Feature: resources, Property 6: Exclusive Allocation Enforcement**
    **Validates: Requirements 3.2**
    
    For any resource with an active exclusive allocation, shared checkout
    requests should also be rejected.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user1_id = generate_user_id()
    user2_id = generate_user_id()
    
    # Create mock resource with capacity > 1
    mock_resource = create_mock_resource(resource_id, resource_name, capacity=5)
    
    # Create existing exclusive allocation
    existing_allocation = create_mock_allocation(1, resource_id, user1_id, mode='exclusive', status='active')
    
    # Create mock session with existing allocation
    mock_session = create_mock_session_for_checkout_with_existing_allocation(
        mock_resource, [existing_allocation]
    )
    
    manager = AllocationManager(mock_session)
    
    # Attempt shared checkout
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="shared",
        reason="Shared checkout attempt"
    )
    
    checkout_rejected = False
    
    try:
        manager.checkout(checkout_request, user2_id)
    except ResourceUnavailableError:
        checkout_rejected = True
    
    assert checkout_rejected, "Shared checkout should be rejected when exclusive allocation exists"


def test_property_exclusive_allocation_enforcement_random():
    """
    **Feature: resources, Property 6: Exclusive Allocation Enforcement**
    **Validates: Requirements 3.2**
    
    Property test: For any randomly generated resource with an exclusive allocation,
    all subsequent checkout attempts should be rejected.
    """
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        user1_id = generate_user_id()
        user2_id = generate_user_id()
        capacity = random.randint(1, 10)
        second_mode = random.choice(['exclusive', 'shared'])
        
        # Create mock resource
        mock_resource = create_mock_resource(resource_id, resource_name, capacity=capacity)
        
        # Create existing exclusive allocation
        existing_allocation = create_mock_allocation(1, resource_id, user1_id, mode='exclusive', status='active')
        
        # Create mock session with existing allocation
        mock_session = create_mock_session_for_checkout_with_existing_allocation(
            mock_resource, [existing_allocation]
        )
        
        manager = AllocationManager(mock_session)
        
        # Attempt second checkout
        checkout_request = CheckoutRequest(
            resource_id=resource_id,
            mode=second_mode,
            reason="Property test checkout"
        )
        
        checkout_rejected = False
        
        try:
            manager.checkout(checkout_request, user2_id)
        except ResourceUnavailableError:
            checkout_rejected = True
        
        assert checkout_rejected, \
            f"Checkout ({second_mode}) should be rejected when exclusive allocation exists"


def test_exclusive_checkout_returns_allocation_details():
    """
    **Feature: resources, Property 6: Exclusive Allocation Enforcement**
    **Validates: Requirements 3.2**
    
    When a checkout is rejected due to exclusive allocation, the error should
    include the current allocation details.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user1_id = generate_user_id()
    user2_id = generate_user_id()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Create existing exclusive allocation
    existing_allocation = create_mock_allocation(1, resource_id, user1_id, mode='exclusive', status='active')
    
    # Create mock session with existing allocation
    mock_session = create_mock_session_for_checkout_with_existing_allocation(
        mock_resource, [existing_allocation]
    )
    
    manager = AllocationManager(mock_session)
    
    # Attempt second checkout
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive"
    )
    
    try:
        manager.checkout(checkout_request, user2_id)
        assert False, "Should have raised ResourceUnavailableError"
    except ResourceUnavailableError as e:
        assert e.current_allocation is not None, "Current allocation should be returned"
        assert e.current_allocation.resource_id == resource_id, "Allocation should be for correct resource"
        assert e.current_allocation.mode == "exclusive", "Allocation mode should be exclusive"


def test_same_user_cannot_double_checkout_exclusive():
    """
    **Feature: resources, Property 6: Exclusive Allocation Enforcement**
    **Validates: Requirements 3.2**
    
    Even the same user cannot checkout an exclusively allocated resource twice.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    user_id = generate_user_id()
    
    # Create mock resource
    mock_resource = create_mock_resource(resource_id, resource_name)
    
    # Create existing exclusive allocation by same user
    existing_allocation = create_mock_allocation(1, resource_id, user_id, mode='exclusive', status='active')
    
    # Create mock session with existing allocation
    mock_session = create_mock_session_for_checkout_with_existing_allocation(
        mock_resource, [existing_allocation]
    )
    
    manager = AllocationManager(mock_session)
    
    # Attempt second checkout by same user
    checkout_request = CheckoutRequest(
        resource_id=resource_id,
        mode="exclusive"
    )
    
    checkout_rejected = False
    
    try:
        manager.checkout(checkout_request, user_id)
    except ResourceUnavailableError:
        checkout_rejected = True
    
    assert checkout_rejected, "Same user should not be able to double checkout exclusive resource"
