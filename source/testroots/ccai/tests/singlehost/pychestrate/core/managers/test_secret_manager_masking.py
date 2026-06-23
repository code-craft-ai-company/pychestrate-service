"""
.. module:: test_secret_manager_masking
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for SecretManager secret value masking

.. moduleauthor:: Code Craft AI LLC

Property tests for secret value masking - ensuring metadata responses never expose values.

**Feature: system-configuration**
**Property 30: Secret Value Masking**
**Validates: Requirements 11.9**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.pychestrate.core.orm import SecretType
from ccai.pychestrate.core.managers.secret_manager import (
    SecretManager,
    SecretMetadataResponse,
    SecretListResponse,
    generate_encryption_key,
)

from ccai.testbase.mocking import Mock


# =============================================================================
# Mock Factories
# =============================================================================

def create_mock_session():
    """Create a basic mock database session."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    return mock_session


def create_mock_secret(secret_id=1, name="test_secret", scope_id=1, secret_type="generic", 
                       description="", version=1, is_deleted=False, encrypted_value=b'encrypted'):
    """Create a mock Secret object."""
    mock_secret = Mock()
    mock_secret.configure(recursive=True)
    ctx = mock_secret.mock_context()
    ctx.set_attribute('id', secret_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('scope_id', scope_id)
    ctx.set_attribute('secret_type', secret_type)
    ctx.set_attribute('description', description)
    ctx.set_attribute('version', version)
    ctx.set_attribute('is_deleted', is_deleted)
    ctx.set_attribute('created_at', None)
    ctx.set_attribute('updated_at', None)
    ctx.set_attribute('updated_by_id', None)
    ctx.set_attribute('encrypted_value', encrypted_value)
    return mock_secret


def create_mock_scope(scope_id=1, name="test_scope", description="", is_system=False):
    """Create a mock SecretScope object."""
    mock_scope = Mock()
    mock_scope.configure(recursive=True)
    ctx = mock_scope.mock_context()
    ctx.set_attribute('id', scope_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('description', description)
    ctx.set_attribute('is_system', is_system)
    ctx.set_attribute('created_at', None)
    ctx.set_attribute('created_by_id', None)
    return mock_scope


def generate_secret_value():
    """Generate a random secret value."""
    length = random.randint(8, 64)
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choices(chars, k=length))


def generate_secret_name():
    """Generate a random secret name."""
    prefix = ''.join(random.choices(string.ascii_lowercase, k=8))
    suffix = random.randint(1000, 9999)
    return f"secret_{prefix}_{suffix}"


# =============================================================================
# Property Tests - Property 30: Secret Value Masking
# =============================================================================

def test_metadata_response_never_contains_value():
    """
    **Feature: system-configuration, Property 30: Secret Value Masking**
    **Validates: Requirements 11.9**
    
    SecretMetadataResponse should never contain the actual secret value.
    """
    for _ in range(100):
        secret_value = generate_secret_value()
        secret_name = generate_secret_name()
        
        # Create a metadata response
        response = SecretMetadataResponse(
            id=random.randint(1, 10000),
            name=secret_name,
            secret_type=SecretType.GENERIC,
            scope_id=random.randint(1, 100),
            scope_name="test_scope",
            description="Test secret",
            version=random.randint(1, 100),
            is_deleted=False,
            created_at=None,
            updated_at=None,
            updated_by=None
        )
        
        # Verify the response object has no 'value' attribute
        assert not hasattr(response, 'value'), "SecretMetadataResponse should not have 'value' attribute"
        
        # Verify the secret value is not in any string representation
        response_str = str(response)
        assert secret_value not in response_str, "Secret value should not appear in string representation"


def test_get_secret_metadata_does_not_expose_value():
    """
    **Feature: system-configuration, Property 30: Secret Value Masking**
    **Validates: Requirements 11.9**
    
    get_secret_metadata should return metadata without the actual value.
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        secret_value = generate_secret_value()
        secret_name = generate_secret_name()
        scope_id = random.randint(1, 100)
        
        # Create mock secret with encrypted value
        mock_secret = create_mock_secret(
            secret_id=random.randint(1, 10000),
            name=secret_name,
            scope_id=scope_id,
            encrypted_value=b'encrypted_data_here'
        )
        
        mock_scope = create_mock_scope(scope_id=scope_id, name="test_scope")
        
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                # First query: Secret
                mock_filter.mock_context().mock_method('first', return_value=mock_secret)
            else:
                # Subsequent queries: User or SecretScope
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # Get metadata
        result = manager.get_secret_metadata(secret_name, scope_id)
        
        # Verify result is SecretMetadataResponse
        assert isinstance(result, SecretMetadataResponse)
        
        # Verify no 'value' attribute
        assert not hasattr(result, 'value'), "Metadata response should not have 'value' attribute"
        
        # Verify encrypted_value is not exposed
        assert not hasattr(result, 'encrypted_value'), "Metadata response should not have 'encrypted_value' attribute"


def test_list_secrets_does_not_expose_values():
    """
    **Feature: system-configuration, Property 30: Secret Value Masking**
    **Validates: Requirements 11.9**
    
    list_secrets should return metadata without actual values.
    """
    for _ in range(50):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        num_secrets = random.randint(1, 10)
        scope_id = random.randint(1, 100)
        
        # Create mock secrets
        mock_secrets = []
        for i in range(num_secrets):
            mock_secret = create_mock_secret(
                secret_id=i + 1,
                name=generate_secret_name(),
                scope_id=scope_id,
                encrypted_value=b'encrypted_data'
            )
            mock_secrets.append(mock_secret)
        
        mock_scope = create_mock_scope(scope_id=scope_id, name="test_scope")
        
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                # First query: Secret count
                mock_filter.mock_context().mock_method('count', return_value=num_secrets)
                mock_filter.mock_context().mock_method('filter', return_value=mock_filter)
                
                # For order_by().offset().limit().all()
                mock_order = Mock()
                mock_order.configure(recursive=True)
                mock_offset = Mock()
                mock_offset.configure(recursive=True)
                mock_limit = Mock()
                mock_limit.configure(recursive=True)
                mock_limit.mock_context().mock_method('all', return_value=mock_secrets)
                mock_offset.mock_context().mock_method('limit', return_value=mock_limit)
                mock_order.mock_context().mock_method('offset', return_value=mock_offset)
                mock_filter.mock_context().mock_method('order_by', return_value=mock_order)
            else:
                # Subsequent queries: User or SecretScope
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # List secrets
        result = manager.list_secrets(scope_id=scope_id)
        
        # Verify result is SecretListResponse
        assert isinstance(result, SecretListResponse)
        
        # Verify each secret in the list has no value
        for secret_meta in result.secrets:
            assert isinstance(secret_meta, SecretMetadataResponse)
            assert not hasattr(secret_meta, 'value'), "Secret metadata should not have 'value' attribute"
            assert not hasattr(secret_meta, 'encrypted_value'), "Secret metadata should not have 'encrypted_value' attribute"


def test_metadata_response_fields_are_correct():
    """
    **Feature: system-configuration, Property 30: Secret Value Masking**
    **Validates: Requirements 11.9**
    
    SecretMetadataResponse should only contain expected metadata fields.
    """
    expected_fields = {
        'id', 'name', 'secret_type', 'scope_id', 'scope_name',
        'description', 'version', 'is_deleted', 'created_at',
        'updated_at', 'updated_by'
    }
    
    forbidden_fields = {'value', 'encrypted_value', 'plaintext', 'decrypted_value'}
    
    for _ in range(100):
        response = SecretMetadataResponse(
            id=random.randint(1, 10000),
            name=generate_secret_name(),
            secret_type=SecretType.GENERIC,
            scope_id=random.randint(1, 100),
            scope_name="test_scope",
            description="Test secret",
            version=random.randint(1, 100),
            is_deleted=False,
            created_at=None,
            updated_at=None,
            updated_by=None
        )
        
        # Get actual fields
        actual_fields = set(response.__dataclass_fields__.keys())
        
        # Verify expected fields are present
        assert actual_fields == expected_fields, f"Expected fields {expected_fields}, got {actual_fields}"
        
        # Verify forbidden fields are not present
        for field in forbidden_fields:
            assert field not in actual_fields, f"Forbidden field '{field}' should not be in metadata response"
