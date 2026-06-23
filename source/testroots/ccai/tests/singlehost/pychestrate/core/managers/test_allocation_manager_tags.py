"""
.. module:: test_allocation_manager_tags
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for AllocationManager tag-based resource selection

.. moduleauthor:: Code Craft AI LLC

Tests for tag-based resource selection in the AllocationManager.

**Feature: resources**
**Property 13: Tag-Based Resource Selection**
**Validates: Requirements 7.3, 7.4**
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
    NoMatchingResourceError,
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


def generate_tag_name():
    """Generate a unique tag name for testing."""
    return 'tag_' + ''.join(random.choices(string.ascii_lowercase, k=6))


def create_mock_tag(tag_name):
    """Create a mock tag object."""
    mock_tag = Mock()
    mock_tag.configure(recursive=True)
    ctx = mock_tag.mock_context()
    ctx.set_attribute('id', random.randint(1, 1000))
    ctx.set_attribute('name', tag_name)
    ctx.set_attribute('description', '')
    return mock_tag


def create_mock_resource(resource_id, name, pool_id=1, capacity=1, health_status='online', tags=None):
    """Create a mock resource object with tags."""
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
    ctx.set_attribute('tags', tags or [])
    return mock_resource


def create_mock_allocation(allocation_id, resource_id, user_id, mode='exclusive', status='active'):
    """Create a mock allocation object."""
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


# =============================================================================
# Tag-Based Resource Selection Tests - Property 13
# =============================================================================

def test_checkout_request_accepts_tags():
    """
    **Feature: resources, Property 13: Tag-Based Resource Selection**
    **Validates: Requirements 7.3, 7.4**
    
    CheckoutRequest should accept tags parameter for tag-based selection.
    """
    tags = ['linux', 'x86_64', 'gpu']
    
    request = CheckoutRequest(
        tags=tags,
        mode="exclusive"
    )
    
    assert request.tags == tags, "CheckoutRequest should store tags"
    assert request.resource_id is None, "resource_id should be None for tag-based checkout"


def test_checkout_request_with_tags_and_pool():
    """
    **Feature: resources, Property 13: Tag-Based Resource Selection**
    **Validates: Requirements 7.3, 7.4**
    
    CheckoutRequest should accept both tags and pool_id for filtered selection.
    """
    tags = ['linux', 'x86_64']
    pool_id = 5
    
    request = CheckoutRequest(
        tags=tags,
        pool_id=pool_id,
        mode="shared"
    )
    
    assert request.tags == tags, "CheckoutRequest should store tags"
    assert request.pool_id == pool_id, "CheckoutRequest should store pool_id"


def test_no_matching_resource_error_contains_tags():
    """
    **Feature: resources, Property 13: Tag-Based Resource Selection**
    **Validates: Requirements 7.3**
    
    NoMatchingResourceError should be raised when no resource matches tags.
    """
    tags = ['nonexistent_tag1', 'nonexistent_tag2']
    
    error = NoMatchingResourceError(
        f"No available resource found matching tags: {', '.join(tags)}"
    )
    
    assert 'nonexistent_tag1' in error.message, "Error should mention the tags"
    assert 'nonexistent_tag2' in error.message, "Error should mention all tags"
    assert error.error_code == "NO_MATCHING_RESOURCE", "Error code should be correct"


def test_property_checkout_request_tags_random():
    """
    **Feature: resources, Property 13: Tag-Based Resource Selection**
    **Validates: Requirements 7.3, 7.4**
    
    Property test: CheckoutRequest should correctly store any combination of tags.
    """
    for _ in range(100):
        num_tags = random.randint(1, 5)
        tags = [generate_tag_name() for _ in range(num_tags)]
        pool_id = random.choice([None, random.randint(1, 100)])
        mode = random.choice(['exclusive', 'shared'])
        
        request = CheckoutRequest(
            tags=tags,
            pool_id=pool_id,
            mode=mode
        )
        
        assert request.tags == tags, f"Tags should be stored correctly: {tags}"
        assert request.pool_id == pool_id, f"Pool ID should be stored correctly: {pool_id}"
        assert request.mode == mode, f"Mode should be stored correctly: {mode}"


def test_allocation_manager_valid_modes():
    """
    **Feature: resources, Property 13: Tag-Based Resource Selection**
    **Validates: Requirements 7.4**
    
    AllocationManager should define valid modes for tag-based selection.
    """
    assert 'exclusive' in AllocationManager.VALID_MODES, "exclusive should be a valid mode"
    assert 'shared' in AllocationManager.VALID_MODES, "shared should be a valid mode"


def test_allocation_manager_blocked_health_statuses():
    """
    **Feature: resources, Property 13: Tag-Based Resource Selection**
    **Validates: Requirements 7.4**
    
    AllocationManager should block unhealthy resources from tag-based selection.
    """
    assert 'offline' in AllocationManager.BLOCKED_HEALTH_STATUSES, \
        "offline should block allocation"
    assert 'maintenance' in AllocationManager.BLOCKED_HEALTH_STATUSES, \
        "maintenance should block allocation"


def test_checkout_by_tags_raises_no_matching_when_none_found():
    """
    **Feature: resources, Property 13: Tag-Based Resource Selection**
    **Validates: Requirements 7.3**
    
    Checkout by tags should raise NoMatchingResourceError when find_available_resource returns None.
    """
    user_id = generate_user_id()
    tags = ['nonexistent_tag']
    
    # Create a mock session that simulates no matching resource
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    # Mock find_available_resource to return None by having the tag query return None
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # Tag query returns None (tag doesn't exist)
        mock_filter.mock_context().mock_method('first', return_value=None)
        mock_filter.mock_context().mock_method('all', return_value=[])
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    
    manager = AllocationManager(mock_session)
    
    # Checkout by tags should raise NoMatchingResourceError
    checkout_request = CheckoutRequest(
        tags=tags,
        mode="exclusive"
    )
    
    error_raised = False
    try:
        manager.checkout(checkout_request, user_id)
    except NoMatchingResourceError as e:
        error_raised = True
        assert 'nonexistent_tag' in e.message, "Error should mention the tag"
    
    assert error_raised, "Should raise NoMatchingResourceError for nonexistent tags"


def test_property_no_matching_resource_error_random():
    """
    **Feature: resources, Property 13: Tag-Based Resource Selection**
    **Validates: Requirements 7.3**
    
    Property test: NoMatchingResourceError should correctly format any tag list.
    """
    for _ in range(100):
        num_tags = random.randint(1, 5)
        tags = [generate_tag_name() for _ in range(num_tags)]
        
        error = NoMatchingResourceError(
            f"No available resource found matching tags: {', '.join(tags)}"
        )
        
        for tag in tags:
            assert tag in error.message, f"Error should mention tag: {tag}"

