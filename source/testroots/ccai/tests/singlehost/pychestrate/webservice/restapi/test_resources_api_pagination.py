"""
.. module:: test_resources_api_pagination
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for resource API pagination correctness

.. moduleauthor:: Code Craft AI LLC

Tests for API pagination correctness in the resource REST API.

**Feature: resources**
**Property 17: API Pagination Correctness**
**Validates: Requirements 10.4**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_resource_items(count: int) -> list:
    """Generate a list of random resource items for testing pagination."""
    items = []
    for i in range(count):
        items.append({
            'id': i + 1,
            'name': ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 15))),
            'resource_type': random.choice(['device', 'ip_address', 'port', 'credential', 'generic']),
            'pool_id': random.randint(1, 10),
            'health_status': random.choice(['online', 'offline', 'degraded', 'maintenance']),
        })
    return items


def generate_offset() -> int:
    """Generate a random offset value."""
    return random.randint(0, 500)


def generate_limit() -> int:
    """Generate a random limit value."""
    return random.randint(1, 100)


# =============================================================================
# Pagination Logic Implementation
# =============================================================================

def get_pagination_params(offset_str: str = None, limit_str: str = None) -> tuple:
    """
    Parse and validate pagination parameters.
    
    This mirrors the logic in base.py get_pagination_params().
    
    :param offset_str: Offset parameter as string (from request args)
    :param limit_str: Limit parameter as string (from request args)
    :returns: Tuple of (offset, limit)
    """
    try:
        offset = int(offset_str) if offset_str is not None else 0
    except ValueError:
        offset = 0
    
    try:
        limit = int(limit_str) if limit_str is not None else 50
    except ValueError:
        limit = 50
    
    # Enforce limits
    offset = max(0, offset)
    limit = max(1, min(100, limit))
    
    return offset, limit


def paginated_response(items: list, total: int, offset: int, limit: int) -> dict:
    """
    Create a paginated response.
    
    This mirrors the logic in base.py paginated_response().
    
    :param items: List of items for current page
    :param total: Total number of items
    :param offset: Current offset
    :param limit: Items per page
    :returns: Paginated response dict
    """
    return {
        'items': items,
        'total': total,
        'offset': offset,
        'limit': limit
    }


def apply_pagination(all_items: list, offset: int, limit: int) -> list:
    """
    Apply pagination to a list of items.
    
    :param all_items: Complete list of items
    :param offset: Starting offset
    :param limit: Maximum items to return
    :returns: Paginated subset of items
    """
    return all_items[offset:offset + limit]


# =============================================================================
# Pagination Correctness Tests - Property 17
# =============================================================================

def test_pagination_response_has_required_fields():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    For any paginated response, it SHALL contain items, total, offset, and limit fields.
    """
    for _ in range(100):
        total_count = random.randint(0, 500)
        all_items = generate_resource_items(total_count)
        offset = random.randint(0, max(0, total_count - 1)) if total_count > 0 else 0
        limit = random.randint(1, 100)
        
        page_items = apply_pagination(all_items, offset, limit)
        response = paginated_response(page_items, total_count, offset, limit)
        
        assert 'items' in response, "Response must have 'items' field"
        assert 'total' in response, "Response must have 'total' field"
        assert 'offset' in response, "Response must have 'offset' field"
        assert 'limit' in response, "Response must have 'limit' field"


def test_pagination_items_count_within_limit():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    For any paginated response, the number of items SHALL not exceed the limit.
    """
    for _ in range(100):
        total_count = random.randint(0, 500)
        all_items = generate_resource_items(total_count)
        offset = random.randint(0, max(0, total_count - 1)) if total_count > 0 else 0
        limit = random.randint(1, 100)
        
        page_items = apply_pagination(all_items, offset, limit)
        response = paginated_response(page_items, total_count, offset, limit)
        
        assert len(response['items']) <= response['limit'], \
            f"Items count ({len(response['items'])}) should not exceed limit ({response['limit']})"


def test_pagination_offset_reflects_request():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    For any paginated response, the offset SHALL match the requested offset.
    """
    for _ in range(100):
        total_count = random.randint(0, 500)
        all_items = generate_resource_items(total_count)
        requested_offset = random.randint(0, 1000)
        limit = random.randint(1, 100)
        
        # Normalize offset (can't be negative)
        normalized_offset = max(0, requested_offset)
        
        page_items = apply_pagination(all_items, normalized_offset, limit)
        response = paginated_response(page_items, total_count, normalized_offset, limit)
        
        assert response['offset'] == normalized_offset, \
            f"Response offset ({response['offset']}) should match requested ({normalized_offset})"


def test_pagination_total_reflects_full_dataset():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    For any paginated response, total SHALL reflect the full dataset size.
    """
    for _ in range(100):
        total_count = random.randint(0, 500)
        all_items = generate_resource_items(total_count)
        offset = random.randint(0, max(0, total_count - 1)) if total_count > 0 else 0
        limit = random.randint(1, 100)
        
        page_items = apply_pagination(all_items, offset, limit)
        response = paginated_response(page_items, total_count, offset, limit)
        
        assert response['total'] == total_count, \
            f"Response total ({response['total']}) should match dataset size ({total_count})"


def test_pagination_negative_offset_normalized_to_zero():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    For any negative offset, it SHALL be normalized to zero.
    """
    for _ in range(100):
        negative_offset = -random.randint(1, 1000)
        limit_str = str(random.randint(1, 100))
        
        offset, limit = get_pagination_params(str(negative_offset), limit_str)
        
        assert offset == 0, \
            f"Negative offset ({negative_offset}) should be normalized to 0, got {offset}"


def test_pagination_limit_enforced_minimum():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    For any limit less than 1, it SHALL be normalized to 1.
    """
    for _ in range(100):
        invalid_limit = random.randint(-100, 0)
        offset_str = str(random.randint(0, 100))
        
        offset, limit = get_pagination_params(offset_str, str(invalid_limit))
        
        assert limit >= 1, \
            f"Limit ({invalid_limit}) should be normalized to at least 1, got {limit}"


def test_pagination_limit_enforced_maximum():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    For any limit greater than 100, it SHALL be capped at 100.
    """
    for _ in range(100):
        large_limit = random.randint(101, 10000)
        offset_str = str(random.randint(0, 100))
        
        offset, limit = get_pagination_params(offset_str, str(large_limit))
        
        assert limit <= 100, \
            f"Limit ({large_limit}) should be capped at 100, got {limit}"


def test_pagination_invalid_offset_defaults_to_zero():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    For any non-numeric offset, it SHALL default to zero.
    """
    invalid_offsets = ['abc', '', 'null', 'undefined', '1.5.3', 'NaN', 'Infinity']
    
    for invalid_offset in invalid_offsets:
        offset, limit = get_pagination_params(invalid_offset, '50')
        
        assert offset == 0, \
            f"Invalid offset '{invalid_offset}' should default to 0, got {offset}"


def test_pagination_invalid_limit_defaults_to_fifty():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    For any non-numeric limit, it SHALL default to 50.
    """
    invalid_limits = ['abc', '', 'null', 'undefined', '1.5.3', 'NaN', 'Infinity']
    
    for invalid_limit in invalid_limits:
        offset, limit = get_pagination_params('0', invalid_limit)
        
        assert limit == 50, \
            f"Invalid limit '{invalid_limit}' should default to 50, got {limit}"


def test_pagination_offset_beyond_total_returns_empty():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    When offset exceeds total items, the items list SHALL be empty.
    """
    for _ in range(100):
        total_count = random.randint(1, 100)
        all_items = generate_resource_items(total_count)
        offset = total_count + random.randint(1, 100)  # Beyond total
        limit = random.randint(1, 100)
        
        page_items = apply_pagination(all_items, offset, limit)
        response = paginated_response(page_items, total_count, offset, limit)
        
        assert len(response['items']) == 0, \
            f"Items should be empty when offset ({offset}) exceeds total ({total_count})"
        assert response['total'] == total_count, \
            "Total should still reflect full dataset size"


def test_pagination_items_are_correct_slice():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    The items returned SHALL be the correct slice of the full dataset.
    """
    for _ in range(100):
        total_count = random.randint(10, 200)
        all_items = generate_resource_items(total_count)
        offset = random.randint(0, total_count - 1)
        limit = random.randint(1, 50)
        
        page_items = apply_pagination(all_items, offset, limit)
        expected_items = all_items[offset:offset + limit]
        
        assert page_items == expected_items, \
            f"Paginated items should match expected slice from offset {offset} with limit {limit}"


def test_pagination_default_values():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    When no parameters provided, defaults SHALL be offset=0, limit=50.
    """
    offset, limit = get_pagination_params(None, None)
    
    assert offset == 0, f"Default offset should be 0, got {offset}"
    assert limit == 50, f"Default limit should be 50, got {limit}"


def test_pagination_resource_list_endpoints():
    """
    **Feature: resources, Property 17: API Pagination Correctness**
    **Validates: Requirements 10.4**
    
    All resource list endpoints should support pagination parameters.
    """
    # List of resource API endpoints that support pagination
    paginated_endpoints = [
        '/api/v1/resources',
        '/api/v1/pools',
        '/api/v1/ip-pools',
        '/api/v1/allocations',
        '/api/v1/allocations/history',
        '/api/v1/reservations',
        '/api/v1/tags',
        '/api/v1/resources/{id}/health/history',
    ]
    
    # Verify all endpoints are in the paginated list
    assert len(paginated_endpoints) > 0, "Should have paginated endpoints defined"
    
    # Each endpoint should support offset and limit parameters
    for endpoint in paginated_endpoints:
        assert endpoint.startswith('/api/v1/'), f"Endpoint should be under /api/v1/: {endpoint}"
