"""
.. module:: test_resource_manager_pool_deletion
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ResourceManager pool deletion constraint

.. moduleauthor:: Code Craft AI LLC

Tests for pool deletion constraint in the ResourceManager.

**Feature: resources**
**Property 4: Pool Deletion Constraint**
**Validates: Requirements 2.5**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.resource_manager import (
    ResourceManager,
    PoolNotFoundError,
    PoolHasResourcesError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_name():
    """Generate a unique pool name for testing."""
    return 'pool_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def create_mock_pool(pool_id, name, is_default=False):
    """Create a mock pool object matching the ResourcePool ORM model."""
    mock_pool = Mock()
    mock_pool.configure(recursive=True)
    ctx = mock_pool.mock_context()
    ctx.set_attribute('id', pool_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('description', '')
    ctx.set_attribute('is_default', is_default)
    ctx.set_attribute('resources', [])
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('created_by_id', None)
    return mock_pool


def create_mock_session_for_pool_deletion(pool, resource_count):
    """
    Create a mock session for pool deletion tests.
    
    Query flow for delete_pool:
    1. Query ResourcePool to find the pool by ID
    2. Query Resource to count resources in pool
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
            # First call: pool lookup
            mock_filter.mock_context().mock_method('first', return_value=pool)
        else:
            # Second call: resource count
            mock_filter.mock_context().mock_method('count', return_value=resource_count)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('delete')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


def create_mock_session_pool_not_found():
    """Create a mock session that returns no pool."""
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
# Pool Deletion Constraint Tests - Property 4
# =============================================================================

def test_delete_pool_with_resources_rejected():
    """
    **Feature: resources, Property 4: Pool Deletion Constraint**
    **Validates: Requirements 2.5**
    
    For any pool with resources, deletion should be rejected.
    """
    pool_id = 1
    pool_name = generate_unique_name()
    
    # Create mock pool with resources
    mock_pool = create_mock_pool(pool_id, pool_name)
    mock_session = create_mock_session_for_pool_deletion(mock_pool, resource_count=5)
    
    manager = ResourceManager(mock_session)
    
    deletion_rejected = False
    try:
        manager.delete_pool(pool_id)
    except PoolHasResourcesError as e:
        deletion_rejected = True
        assert 'resource' in e.message.lower()
    
    assert deletion_rejected, "Pool with resources should not be deleted"


def test_delete_pool_without_resources_succeeds():
    """
    **Feature: resources, Property 4: Pool Deletion Constraint**
    **Validates: Requirements 2.5**
    
    For any pool without resources, deletion should succeed.
    """
    pool_id = 1
    pool_name = generate_unique_name()
    
    # Create mock pool with no resources
    mock_pool = create_mock_pool(pool_id, pool_name)
    mock_session = create_mock_session_for_pool_deletion(mock_pool, resource_count=0)
    
    manager = ResourceManager(mock_session)
    
    # Should not raise any exception
    try:
        manager.delete_pool(pool_id)
        success = True
    except PoolHasResourcesError:
        success = False
    
    assert success, "Pool without resources should be deleted"


def test_delete_nonexistent_pool_raises_error():
    """
    **Feature: resources, Property 4: Pool Deletion Constraint**
    **Validates: Requirements 2.5**
    
    Attempting to delete a non-existent pool should raise PoolNotFoundError.
    """
    mock_session = create_mock_session_pool_not_found()
    
    manager = ResourceManager(mock_session)
    
    not_found_raised = False
    try:
        manager.delete_pool(999)
    except PoolNotFoundError:
        not_found_raised = True
    
    assert not_found_raised, "Deleting non-existent pool should raise PoolNotFoundError"


def test_property_deletion_blocked_for_any_resource_count():
    """
    **Feature: resources, Property 4: Pool Deletion Constraint**
    **Validates: Requirements 2.5**
    
    Property test: For any pool with N resources (where N > 0),
    deletion should be rejected.
    """
    for _ in range(100):
        pool_id = random.randint(1, 1000)
        pool_name = generate_unique_name()
        resource_count = random.randint(1, 100)  # At least 1 resource
        
        mock_pool = create_mock_pool(pool_id, pool_name)
        mock_session = create_mock_session_for_pool_deletion(mock_pool, resource_count)
        
        manager = ResourceManager(mock_session)
        
        deletion_rejected = False
        try:
            manager.delete_pool(pool_id)
        except PoolHasResourcesError:
            deletion_rejected = True
        
        assert deletion_rejected, \
            f"Pool with {resource_count} resources should not be deleted"


def test_property_deletion_allowed_for_zero_resources():
    """
    **Feature: resources, Property 4: Pool Deletion Constraint**
    **Validates: Requirements 2.5**
    
    Property test: For any pool with zero resources,
    deletion should succeed.
    """
    for _ in range(100):
        pool_id = random.randint(1, 1000)
        pool_name = generate_unique_name()
        
        mock_pool = create_mock_pool(pool_id, pool_name)
        mock_session = create_mock_session_for_pool_deletion(mock_pool, resource_count=0)
        
        manager = ResourceManager(mock_session)
        
        try:
            manager.delete_pool(pool_id)
            success = True
        except PoolHasResourcesError:
            success = False
        
        assert success, f"Pool '{pool_name}' with zero resources should be deleted"


def test_deletion_constraint_with_single_resource():
    """
    **Feature: resources, Property 4: Pool Deletion Constraint**
    **Validates: Requirements 2.5**
    
    Even a single resource should block pool deletion.
    """
    pool_id = 1
    pool_name = generate_unique_name()
    
    mock_pool = create_mock_pool(pool_id, pool_name)
    mock_session = create_mock_session_for_pool_deletion(mock_pool, resource_count=1)
    
    manager = ResourceManager(mock_session)
    
    deletion_rejected = False
    try:
        manager.delete_pool(pool_id)
    except PoolHasResourcesError as e:
        deletion_rejected = True
        assert '1' in e.message  # Should mention the count
    
    assert deletion_rejected, "Pool with single resource should not be deleted"

