"""
.. module:: test_secret_manager_scope
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for SecretManager scope management

.. moduleauthor:: Automation Mojo LLC

Property tests for secret scope management including deletion constraints.

**Feature: system-configuration**
**Property 33: Scope Deletion Constraint**
**Validates: Requirements 12.4**
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
    SecretScopeCreateRequest,
    SecretCreateRequest,
    ScopeNotEmptyError,
    ScopeNotFoundError,
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


def create_mock_scope(scope_id=1, name="test_scope", description="", is_system=False, secret_count=0):
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


def create_mock_secret(secret_id=1, name="test_secret", scope_id=1, secret_type="generic", 
                       description="", version=1, is_deleted=False):
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
    ctx.set_attribute('encrypted_value', b'encrypted')
    return mock_secret


def generate_scope_name():
    """Generate a random scope name."""
    prefix = ''.join(random.choices(string.ascii_lowercase, k=8))
    suffix = random.randint(1000, 9999)
    return f"scope_{prefix}_{suffix}"


def generate_secret_name():
    """Generate a random secret name."""
    prefix = ''.join(random.choices(string.ascii_lowercase, k=8))
    suffix = random.randint(1000, 9999)
    return f"secret_{prefix}_{suffix}"


# =============================================================================
# Property Tests - Property 33: Scope Deletion Constraint
# =============================================================================

def test_empty_scope_can_be_deleted():
    """
    **Feature: system-configuration, Property 33: Scope Deletion Constraint**
    **Validates: Requirements 12.4**
    
    For any empty scope (no secrets), deletion should succeed.
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_id = random.randint(1, 10000)
        scope_name = generate_scope_name()
        mock_scope = create_mock_scope(scope_id=scope_id, name=scope_name)
        
        # Track which model is being queried
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            """Return appropriate mock query based on which model is queried."""
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                # First query: SecretScope - return the scope
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            else:
                # Second query: Secret - return count of 0 (empty scope)
                mock_filter.mock_context().mock_method('count', return_value=0)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        mock_session.mock_context().mock_method('delete', return_value=None)
        mock_session.mock_context().mock_method('commit', return_value=None)
        
        manager = SecretManager(mock_session, key)
        
        # Delete should succeed for empty scope
        manager.delete_scope(scope_id)


def test_scope_with_secrets_cannot_be_deleted():
    """
    **Feature: system-configuration, Property 33: Scope Deletion Constraint**
    **Validates: Requirements 12.4**
    
    For any scope containing secrets, deletion should be rejected.
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_id = random.randint(1, 10000)
        scope_name = generate_scope_name()
        num_secrets = random.randint(1, 100)
        
        mock_scope = create_mock_scope(scope_id=scope_id, name=scope_name)
        
        # Track which model is being queried
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            """Return appropriate mock query based on which model is queried."""
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                # First query: SecretScope - return the scope
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            else:
                # Second query: Secret - return count > 0 (non-empty scope)
                mock_filter.mock_context().mock_method('count', return_value=num_secrets)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # Delete should fail for scope with secrets
        try:
            manager.delete_scope(scope_id)
            assert False, f"Should have raised ScopeNotEmptyError for {num_secrets} secrets"
        except ScopeNotEmptyError as e:
            # Verify error message mentions secrets
            assert "secret" in str(e).lower() or str(num_secrets) in str(e)


def test_nonexistent_scope_deletion_raises_error():
    """
    **Feature: system-configuration, Property 33: Scope Deletion Constraint**
    **Validates: Requirements 12.4**
    
    Attempting to delete a non-existent scope should raise an error.
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        fake_scope_id = random.randint(10000, 99999)
        
        def create_query_for_model(*args, **kwargs):
            """Return mock query that returns None (scope not found)."""
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            mock_filter.mock_context().mock_method('first', return_value=None)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # Delete should fail for non-existent scope
        try:
            manager.delete_scope(fake_scope_id)
            assert False, "Should have raised ScopeNotFoundError"
        except ScopeNotFoundError as e:
            assert str(fake_scope_id) in str(e) or "not found" in str(e).lower()


def test_scope_deletion_constraint_with_varying_secret_counts():
    """
    **Feature: system-configuration, Property 33: Scope Deletion Constraint**
    **Validates: Requirements 12.4**
    
    Scopes with any number of secrets (1 to many) should not be deletable.
    """
    secret_counts = [1, 2, 5, 10, 50, 100, 1000]
    
    for num_secrets in secret_counts:
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_id = random.randint(1, 10000)
        scope_name = generate_scope_name()
        
        mock_scope = create_mock_scope(scope_id=scope_id, name=scope_name)
        
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            """Return appropriate mock query based on which model is queried."""
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            else:
                mock_filter.mock_context().mock_method('count', return_value=num_secrets)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        try:
            manager.delete_scope(scope_id)
            assert False, f"Should have raised ScopeNotEmptyError for {num_secrets} secrets"
        except ScopeNotEmptyError:
            pass  # Expected


def test_scope_deletion_succeeds_with_zero_secrets():
    """
    **Feature: system-configuration, Property 33: Scope Deletion Constraint**
    **Validates: Requirements 12.4**
    
    Scopes with exactly zero secrets should be deletable.
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_id = random.randint(1, 10000)
        scope_name = generate_scope_name()
        
        mock_scope = create_mock_scope(scope_id=scope_id, name=scope_name)
        
        query_count = [0]
        
        def create_query_for_model(*args, **kwargs):
            """Return appropriate mock query based on which model is queried."""
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            current_query = query_count[0]
            query_count[0] += 1
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if current_query == 0:
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            else:
                mock_filter.mock_context().mock_method('count', return_value=0)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        mock_session.mock_context().mock_method('delete', return_value=None)
        mock_session.mock_context().mock_method('commit', return_value=None)
        
        manager = SecretManager(mock_session, key)
        
        # Should succeed without raising
        manager.delete_scope(scope_id)
