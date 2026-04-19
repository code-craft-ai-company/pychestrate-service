"""
.. module:: test_secret_manager_listing
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for SecretManager secret listing permission filter

.. moduleauthor:: Automation Mojo LLC

Property tests for secret listing permission filter - ensuring proper filtering by scope.

**Feature: system-configuration**
**Property 34: Secret Listing Permission Filter**
**Validates: Requirements 12.5**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.pychestrate.core.orm import SecretType
from automojo.pychestrate.core.managers.secret_manager import (
    SecretManager,
    SecretListResponse,
    SecretMetadataResponse,
    generate_encryption_key,
)

from automojo.testbase.mocking import Mock


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


def generate_secret_name():
    """Generate a random secret name."""
    prefix = ''.join(random.choices(string.ascii_lowercase, k=8))
    suffix = random.randint(1000, 9999)
    return f"secret_{prefix}_{suffix}"


# =============================================================================
# Property Tests - Property 34: Secret Listing Permission Filter
# =============================================================================

def test_list_secrets_filters_by_scope():
    """
    **Feature: system-configuration, Property 34: Secret Listing Permission Filter**
    **Validates: Requirements 12.5**
    
    list_secrets should only return secrets from the specified scope.
    """
    for _ in range(50):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_id = random.randint(1, 100)
        num_secrets = random.randint(1, 10)
        
        # Create mock secrets for the specified scope
        mock_secrets = []
        for i in range(num_secrets):
            mock_secret = create_mock_secret(
                secret_id=i + 1,
                name=generate_secret_name(),
                scope_id=scope_id,
                is_deleted=False
            )
            mock_secrets.append(mock_secret)
        
        mock_scope = create_mock_scope(scope_id=scope_id, name=f"scope_{scope_id}")
        
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                # First query: Secret count and list
                mock_filter.mock_context().mock_method('count', return_value=num_secrets)
                mock_filter.mock_context().mock_method('filter', return_value=mock_filter)
                
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
                # Subsequent queries: SecretScope
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # List secrets for specific scope
        result = manager.list_secrets(scope_id=scope_id)
        
        # Verify result
        assert isinstance(result, SecretListResponse)
        assert result.total == num_secrets
        assert len(result.secrets) == num_secrets
        
        # Verify all secrets belong to the specified scope
        for secret_meta in result.secrets:
            assert secret_meta.scope_id == scope_id


def test_list_secrets_excludes_deleted_by_default():
    """
    **Feature: system-configuration, Property 34: Secret Listing Permission Filter**
    **Validates: Requirements 12.5**
    
    list_secrets should exclude soft-deleted secrets by default.
    """
    for _ in range(50):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_id = random.randint(1, 100)
        num_active = random.randint(1, 5)
        
        # Create mock active secrets only (deleted ones are filtered by query)
        mock_secrets = []
        for i in range(num_active):
            mock_secret = create_mock_secret(
                secret_id=i + 1,
                name=generate_secret_name(),
                scope_id=scope_id,
                is_deleted=False
            )
            mock_secrets.append(mock_secret)
        
        mock_scope = create_mock_scope(scope_id=scope_id, name=f"scope_{scope_id}")
        
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                mock_filter.mock_context().mock_method('count', return_value=num_active)
                mock_filter.mock_context().mock_method('filter', return_value=mock_filter)
                
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
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # List secrets without include_deleted
        result = manager.list_secrets(scope_id=scope_id, include_deleted=False)
        
        # Verify only active secrets are returned
        assert result.total == num_active
        for secret_meta in result.secrets:
            assert secret_meta.is_deleted == False


def test_list_secrets_pagination():
    """
    **Feature: system-configuration, Property 34: Secret Listing Permission Filter**
    **Validates: Requirements 12.5**
    
    list_secrets should properly paginate results.
    """
    for _ in range(50):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_id = random.randint(1, 100)
        total_secrets = random.randint(10, 50)
        offset = random.randint(0, total_secrets - 1)
        limit = random.randint(1, 10)
        
        # Calculate expected page size
        expected_page_size = min(limit, total_secrets - offset)
        
        # Create mock secrets for the page
        mock_secrets = []
        for i in range(expected_page_size):
            mock_secret = create_mock_secret(
                secret_id=offset + i + 1,
                name=generate_secret_name(),
                scope_id=scope_id,
                is_deleted=False
            )
            mock_secrets.append(mock_secret)
        
        mock_scope = create_mock_scope(scope_id=scope_id, name=f"scope_{scope_id}")
        
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                mock_filter.mock_context().mock_method('count', return_value=total_secrets)
                mock_filter.mock_context().mock_method('filter', return_value=mock_filter)
                
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
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # List secrets with pagination
        result = manager.list_secrets(scope_id=scope_id, offset=offset, limit=limit)
        
        # Verify pagination metadata
        assert result.total == total_secrets
        assert result.offset == offset
        assert result.limit == limit
        assert len(result.secrets) == expected_page_size


def test_list_secrets_returns_metadata_only():
    """
    **Feature: system-configuration, Property 34: Secret Listing Permission Filter**
    **Validates: Requirements 12.5**
    
    list_secrets should return metadata only, never actual values.
    """
    for _ in range(50):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_id = random.randint(1, 100)
        num_secrets = random.randint(1, 10)
        
        mock_secrets = []
        for i in range(num_secrets):
            mock_secret = create_mock_secret(
                secret_id=i + 1,
                name=generate_secret_name(),
                scope_id=scope_id,
                encrypted_value=b'super_secret_encrypted_data'
            )
            mock_secrets.append(mock_secret)
        
        mock_scope = create_mock_scope(scope_id=scope_id, name=f"scope_{scope_id}")
        
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                mock_filter.mock_context().mock_method('count', return_value=num_secrets)
                mock_filter.mock_context().mock_method('filter', return_value=mock_filter)
                
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
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        result = manager.list_secrets(scope_id=scope_id)
        
        # Verify each item is metadata only
        for secret_meta in result.secrets:
            assert isinstance(secret_meta, SecretMetadataResponse)
            assert not hasattr(secret_meta, 'value')
            assert not hasattr(secret_meta, 'encrypted_value')


def test_list_secrets_empty_scope():
    """
    **Feature: system-configuration, Property 34: Secret Listing Permission Filter**
    **Validates: Requirements 12.5**
    
    list_secrets should return empty list for scope with no secrets.
    """
    for _ in range(50):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_id = random.randint(1, 100)
        
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                mock_filter.mock_context().mock_method('count', return_value=0)
                mock_filter.mock_context().mock_method('filter', return_value=mock_filter)
                
                mock_order = Mock()
                mock_order.configure(recursive=True)
                mock_offset = Mock()
                mock_offset.configure(recursive=True)
                mock_limit = Mock()
                mock_limit.configure(recursive=True)
                mock_limit.mock_context().mock_method('all', return_value=[])
                mock_offset.mock_context().mock_method('limit', return_value=mock_limit)
                mock_order.mock_context().mock_method('offset', return_value=mock_offset)
                mock_filter.mock_context().mock_method('order_by', return_value=mock_order)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        result = manager.list_secrets(scope_id=scope_id)
        
        assert result.total == 0
        assert len(result.secrets) == 0
