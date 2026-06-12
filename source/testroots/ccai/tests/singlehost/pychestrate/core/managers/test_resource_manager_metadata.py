"""
.. module:: test_resource_manager_metadata
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ResourceManager metadata sensitive field masking

.. moduleauthor:: Code Craft AI LLC

Tests for metadata sensitive field masking in the ResourceManager.

**Feature: resources**
**Property 14: Metadata Sensitive Field Masking**
**Validates: Requirements 8.5**
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
    ResourceNotFoundError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_unique_name():
    """Generate a unique resource name for testing."""
    return 'resource_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def generate_random_metadata(num_fields=5, sensitive_fields=None):
    """Generate random metadata with optional sensitive fields."""
    metadata = {}
    for i in range(num_fields):
        field_name = f"field_{i}"
        field_value = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        metadata[field_name] = field_value
    
    # Add sensitive fields if specified
    if sensitive_fields:
        for field_name in sensitive_fields:
            metadata[field_name] = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    
    return metadata


def create_mock_resource(resource_id, name, metadata_json, sensitive_fields):
    """Create a mock resource object with metadata and sensitive fields."""
    mock_resource = Mock()
    mock_resource.configure(recursive=True)
    ctx = mock_resource.mock_context()
    ctx.set_attribute('id', resource_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('pool_id', 1)
    ctx.set_attribute('resource_type', 'device')
    ctx.set_attribute('description', '')
    ctx.set_attribute('metadata_json', metadata_json)
    ctx.set_attribute('sensitive_fields', sensitive_fields)
    ctx.set_attribute('capacity', 1)
    ctx.set_attribute('health_status', 'online')
    ctx.set_attribute('tags', [])
    ctx.set_attribute('pool', None)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    return mock_resource


def create_mock_session_for_get_metadata(resource):
    """Create a mock session for get_metadata tests."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=resource)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session


def create_mock_session_resource_not_found():
    """Create a mock session that returns no resource."""
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
# Metadata Sensitive Field Masking Tests - Property 14
# =============================================================================

def test_sensitive_fields_masked_by_default():
    """
    **Feature: resources, Property 14: Metadata Sensitive Field Masking**
    **Validates: Requirements 8.5**
    
    Sensitive fields should be masked when include_sensitive is False (default).
    """
    resource_id = 1
    resource_name = generate_unique_name()
    sensitive_fields = ['password', 'api_key', 'secret_token']
    
    metadata = {
        'hostname': 'server1.example.com',
        'port': '8080',
        'password': 'super_secret_password',
        'api_key': 'sk-1234567890abcdef',
        'secret_token': 'token_xyz_123'
    }
    
    mock_resource = create_mock_resource(resource_id, resource_name, metadata, sensitive_fields)
    mock_session = create_mock_session_for_get_metadata(mock_resource)
    
    manager = ResourceManager(mock_session)
    
    # Get metadata without sensitive fields
    result = manager.get_metadata(resource_id, include_sensitive=False)
    
    # Non-sensitive fields should be visible
    assert result['hostname'] == 'server1.example.com'
    assert result['port'] == '8080'
    
    # Sensitive fields should be masked
    assert result['password'] == ResourceManager.SENSITIVE_MASK
    assert result['api_key'] == ResourceManager.SENSITIVE_MASK
    assert result['secret_token'] == ResourceManager.SENSITIVE_MASK


def test_sensitive_fields_visible_when_requested():
    """
    **Feature: resources, Property 14: Metadata Sensitive Field Masking**
    **Validates: Requirements 8.5**
    
    Sensitive fields should be visible when include_sensitive is True.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    sensitive_fields = ['password', 'api_key']
    
    metadata = {
        'hostname': 'server1.example.com',
        'password': 'super_secret_password',
        'api_key': 'sk-1234567890abcdef'
    }
    
    mock_resource = create_mock_resource(resource_id, resource_name, metadata, sensitive_fields)
    mock_session = create_mock_session_for_get_metadata(mock_resource)
    
    manager = ResourceManager(mock_session)
    
    # Get metadata with sensitive fields
    result = manager.get_metadata(resource_id, include_sensitive=True)
    
    # All fields should be visible
    assert result['hostname'] == 'server1.example.com'
    assert result['password'] == 'super_secret_password'
    assert result['api_key'] == 'sk-1234567890abcdef'


def test_no_sensitive_fields_returns_all_metadata():
    """
    **Feature: resources, Property 14: Metadata Sensitive Field Masking**
    **Validates: Requirements 8.5**
    
    When no sensitive fields are defined, all metadata should be visible.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    metadata = {
        'hostname': 'server1.example.com',
        'port': '8080',
        'description': 'Test server'
    }
    
    mock_resource = create_mock_resource(resource_id, resource_name, metadata, [])
    mock_session = create_mock_session_for_get_metadata(mock_resource)
    
    manager = ResourceManager(mock_session)
    
    # Get metadata (no sensitive fields defined)
    result = manager.get_metadata(resource_id, include_sensitive=False)
    
    # All fields should be visible
    assert result['hostname'] == 'server1.example.com'
    assert result['port'] == '8080'
    assert result['description'] == 'Test server'


def test_get_metadata_nonexistent_resource_raises_error():
    """
    **Feature: resources, Property 14: Metadata Sensitive Field Masking**
    **Validates: Requirements 8.5**
    
    Getting metadata for a non-existent resource should raise ResourceNotFoundError.
    """
    mock_session = create_mock_session_resource_not_found()
    
    manager = ResourceManager(mock_session)
    
    not_found_raised = False
    try:
        manager.get_metadata(999)
    except ResourceNotFoundError:
        not_found_raised = True
    
    assert not_found_raised, "Getting metadata for non-existent resource should raise error"


def test_property_all_sensitive_fields_masked():
    """
    **Feature: resources, Property 14: Metadata Sensitive Field Masking**
    **Validates: Requirements 8.5**
    
    Property test: For any resource with N sensitive fields, ALL N fields
    should be masked when include_sensitive is False.
    """
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        
        # Generate random number of sensitive fields
        num_sensitive = random.randint(1, 10)
        sensitive_fields = [f"sensitive_{i}" for i in range(num_sensitive)]
        
        # Generate metadata with both sensitive and non-sensitive fields
        num_regular = random.randint(1, 5)
        metadata = {}
        for i in range(num_regular):
            metadata[f"regular_{i}"] = f"value_{i}"
        for field in sensitive_fields:
            metadata[field] = f"secret_value_{field}"
        
        mock_resource = create_mock_resource(resource_id, resource_name, metadata, sensitive_fields)
        mock_session = create_mock_session_for_get_metadata(mock_resource)
        
        manager = ResourceManager(mock_session)
        
        # Get metadata without sensitive fields
        result = manager.get_metadata(resource_id, include_sensitive=False)
        
        # Verify all sensitive fields are masked
        for field in sensitive_fields:
            assert result[field] == ResourceManager.SENSITIVE_MASK, \
                f"Sensitive field '{field}' should be masked"
        
        # Verify non-sensitive fields are not masked
        for i in range(num_regular):
            assert result[f"regular_{i}"] == f"value_{i}", \
                f"Regular field 'regular_{i}' should not be masked"


def test_property_all_fields_visible_when_include_sensitive():
    """
    **Feature: resources, Property 14: Metadata Sensitive Field Masking**
    **Validates: Requirements 8.5**
    
    Property test: For any resource, when include_sensitive is True,
    ALL fields (including sensitive) should be visible with original values.
    """
    for _ in range(100):
        resource_id = random.randint(1, 1000)
        resource_name = generate_unique_name()
        
        # Generate random sensitive fields
        num_sensitive = random.randint(1, 10)
        sensitive_fields = [f"sensitive_{i}" for i in range(num_sensitive)]
        
        # Generate metadata
        metadata = {}
        for i in range(random.randint(1, 5)):
            metadata[f"regular_{i}"] = f"value_{i}"
        for field in sensitive_fields:
            metadata[field] = f"secret_value_{field}"
        
        mock_resource = create_mock_resource(resource_id, resource_name, metadata, sensitive_fields)
        mock_session = create_mock_session_for_get_metadata(mock_resource)
        
        manager = ResourceManager(mock_session)
        
        # Get metadata with sensitive fields
        result = manager.get_metadata(resource_id, include_sensitive=True)
        
        # Verify all fields have original values
        for field, value in metadata.items():
            assert result[field] == value, \
                f"Field '{field}' should have original value when include_sensitive=True"


def test_sensitive_field_not_in_metadata_ignored():
    """
    **Feature: resources, Property 14: Metadata Sensitive Field Masking**
    **Validates: Requirements 8.5**
    
    If a sensitive field is defined but not present in metadata, it should be ignored.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    # Define sensitive fields that don't exist in metadata
    sensitive_fields = ['password', 'nonexistent_field']
    
    metadata = {
        'hostname': 'server1.example.com',
        'password': 'secret123'
        # 'nonexistent_field' is not in metadata
    }
    
    mock_resource = create_mock_resource(resource_id, resource_name, metadata, sensitive_fields)
    mock_session = create_mock_session_for_get_metadata(mock_resource)
    
    manager = ResourceManager(mock_session)
    
    # Should not raise error
    result = manager.get_metadata(resource_id, include_sensitive=False)
    
    # Existing sensitive field should be masked
    assert result['password'] == ResourceManager.SENSITIVE_MASK
    
    # Non-sensitive field should be visible
    assert result['hostname'] == 'server1.example.com'
    
    # Nonexistent field should not be in result
    assert 'nonexistent_field' not in result


def test_empty_metadata_returns_empty_dict():
    """
    **Feature: resources, Property 14: Metadata Sensitive Field Masking**
    **Validates: Requirements 8.5**
    
    Resource with no metadata should return empty dictionary.
    """
    resource_id = 1
    resource_name = generate_unique_name()
    
    mock_resource = create_mock_resource(resource_id, resource_name, {}, [])
    mock_session = create_mock_session_for_get_metadata(mock_resource)
    
    manager = ResourceManager(mock_session)
    
    result = manager.get_metadata(resource_id)
    
    assert result == {}, "Empty metadata should return empty dictionary"

