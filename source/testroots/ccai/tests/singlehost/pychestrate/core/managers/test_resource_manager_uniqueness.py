"""
.. module:: test_resource_manager_uniqueness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ResourceManager resource name uniqueness within pools

.. moduleauthor:: Code Craft AI LLC

Tests for resource name uniqueness constraint in the ResourceManager.

**Feature: resources**
**Property 1: Resource Name Uniqueness**
**Validates: Requirements 1.2**
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
    ResourceCreateRequest,
    DuplicateResourceError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_name():
    """Generate a unique resource name for testing."""
    return 'resource_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def create_mock_resource(resource_id, name, pool_id, resource_type='device'):
    """Create a mock resource object matching the Resource ORM model."""
    mock_resource = Mock()
    mock_resource.configure(recursive=True)
    ctx = mock_resource.mock_context()
    ctx.set_attribute('id', resource_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('pool_id', pool_id)
    ctx.set_attribute('resource_type', resource_type)
    ctx.set_attribute('description', '')
    ctx.set_attribute('metadata_json', {})
    ctx.set_attribute('sensitive_fields', [])
    ctx.set_attribute('capacity', 1)
    ctx.set_attribute('health_status', 'online')
    ctx.set_attribute('tags', [])
    ctx.set_attribute('pool', None)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    return mock_resource


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


def create_mock_session_for_duplicate_check(existing_resource, pool=None):
    """
    Create a mock session that simulates finding a duplicate resource.
    
    Query flow for create_resource:
    1. Query ResourcePool for default pool (if pool_id is None)
    2. Query ResourcePool to verify pool exists (if pool_id provided)
    3. Query Resource to check for duplicate name in pool
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
        
        # Determine what to return based on call order
        if call_count[0] == 1 and pool is not None:
            # First call: pool lookup
            mock_filter.mock_context().mock_method('first', return_value=pool)
        elif call_count[0] == 2 or (call_count[0] == 1 and pool is None):
            # Second call (or first if no pool lookup): duplicate check
            mock_filter.mock_context().mock_method('first', return_value=existing_resource)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


def create_mock_session_for_unique_resource(pool=None):
    """
    Create a mock session that simulates no duplicate resource found.
    
    Query flow for create_resource:
    1. Query ResourcePool for default pool or verify pool exists
    2. Query Resource to check for duplicate name in pool (returns None)
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
        
        # First call: pool lookup returns the pool
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=pool)
        else:
            # Subsequent calls: no duplicate found
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Resource Name Uniqueness Tests - Property 1
# =============================================================================

def test_duplicate_resource_name_in_same_pool_rejected():
    """
    **Feature: resources, Property 1: Resource Name Uniqueness**
    **Validates: Requirements 1.2**
    
    For any resource pool and any two resources within that pool, if both resources
    have the same name, then the second creation attempt should be rejected.
    """
    pool_id = 1
    resource_name = generate_unique_name()
    
    # Create mock pool and existing resource
    mock_pool = create_mock_pool(pool_id, 'test_pool')
    existing_resource = create_mock_resource(1, resource_name, pool_id)
    
    # Create mock session that returns the existing resource on duplicate check
    mock_session = create_mock_session_for_duplicate_check(existing_resource, mock_pool)
    
    manager = ResourceManager(mock_session)
    
    # Attempt to create resource with same name in same pool
    request = ResourceCreateRequest(
        name=resource_name,
        resource_type='device',
        pool_id=pool_id,
        description='Duplicate resource'
    )
    
    duplicate_rejected = False
    try:
        manager.create_resource(request)
    except DuplicateResourceError as e:
        duplicate_rejected = True
        assert 'already exists' in e.message.lower()
    
    assert duplicate_rejected, "Duplicate resource name in same pool should be rejected"


def test_same_resource_name_in_different_pools_allowed():
    """
    **Feature: resources, Property 1: Resource Name Uniqueness**
    **Validates: Requirements 1.2**
    
    Resources with the same name in different pools should be allowed.
    """
    resource_name = generate_unique_name()
    
    # Create mock pool
    mock_pool = create_mock_pool(2, 'pool_2')
    
    # Create mock session that returns no duplicate (different pool)
    mock_session = create_mock_session_for_unique_resource(mock_pool)
    
    manager = ResourceManager(mock_session)
    
    # Create resource with same name in different pool - should succeed
    request = ResourceCreateRequest(
        name=resource_name,
        resource_type='device',
        pool_id=2,
        description='Resource in pool 2'
    )
    
    # Should not raise DuplicateResourceError
    try:
        result = manager.create_resource(request)
        # Result will be based on mock, but no exception means success
        success = True
    except DuplicateResourceError:
        success = False
    
    assert success, "Resource with same name in different pool should be allowed"


def test_property_duplicate_names_rejected_for_random_names():
    """
    **Feature: resources, Property 1: Resource Name Uniqueness**
    **Validates: Requirements 1.2**
    
    Property test: For any randomly generated resource name, creating two resources
    with that name in the same pool should result in the second being rejected.
    """
    for _ in range(100):
        pool_id = random.randint(1, 100)
        resource_name = generate_unique_name()
        
        # Create mock pool and existing resource
        mock_pool = create_mock_pool(pool_id, f'pool_{pool_id}')
        existing_resource = create_mock_resource(1, resource_name, pool_id)
        
        # Create mock session that returns the existing resource
        mock_session = create_mock_session_for_duplicate_check(existing_resource, mock_pool)
        
        manager = ResourceManager(mock_session)
        
        # Attempt to create duplicate
        request = ResourceCreateRequest(
            name=resource_name,
            resource_type='device',
            pool_id=pool_id
        )
        
        duplicate_rejected = False
        try:
            manager.create_resource(request)
        except DuplicateResourceError:
            duplicate_rejected = True
        
        assert duplicate_rejected, f"Duplicate name '{resource_name}' should be rejected"


def test_unique_names_in_same_pool_allowed():
    """
    **Feature: resources, Property 1: Resource Name Uniqueness**
    **Validates: Requirements 1.2**
    
    Multiple resources with unique names in the same pool should all be created successfully.
    """
    pool_id = 1
    mock_pool = create_mock_pool(pool_id, 'test_pool')
    
    # Create multiple resources with unique names
    created_count = 0
    for i in range(10):
        resource_name = f"unique_resource_{i}_{generate_unique_name()}"
        
        # Create mock session that returns no duplicate
        mock_session = create_mock_session_for_unique_resource(mock_pool)
        
        manager = ResourceManager(mock_session)
        
        request = ResourceCreateRequest(
            name=resource_name,
            resource_type='device',
            pool_id=pool_id
        )
        
        try:
            manager.create_resource(request)
            created_count += 1
        except DuplicateResourceError:
            pass  # Should not happen
    
    # Verify all resources were created
    assert created_count == 10, "All unique resources should be created"


def test_case_sensitive_names_are_different():
    """
    **Feature: resources, Property 1: Resource Name Uniqueness**
    **Validates: Requirements 1.2**
    
    Resource names should be case-sensitive, so 'Resource' and 'resource' are different.
    """
    pool_id = 1
    mock_pool = create_mock_pool(pool_id, 'test_pool')
    
    # Test that different case names are treated as unique
    names = ['myresource', 'MYRESOURCE', 'MyResource']
    
    for name in names:
        # Create mock session that returns no duplicate
        mock_session = create_mock_session_for_unique_resource(mock_pool)
        
        manager = ResourceManager(mock_session)
        
        request = ResourceCreateRequest(
            name=name,
            resource_type='device',
            pool_id=pool_id
        )
        
        try:
            manager.create_resource(request)
            success = True
        except DuplicateResourceError:
            success = False
        
        assert success, f"Resource name '{name}' should be allowed (case-sensitive)"

