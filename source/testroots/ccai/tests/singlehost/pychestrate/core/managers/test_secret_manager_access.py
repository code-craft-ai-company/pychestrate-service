"""
.. module:: test_secret_manager_access
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for SecretManager scope access control

.. moduleauthor:: Code Craft AI LLC

Property tests for secret scope access control - ensuring proper permission enforcement.

**Feature: system-configuration**
**Property 31: Secret Scope Access Control**
**Validates: Requirements 11.7, 12.2**
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
    ScopeAccessDeniedError,
    SecretNotFoundError,
    generate_encryption_key,
    encrypt_value,
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
                       description="", version=1, is_deleted=False, encrypted_value=None):
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
    ctx.set_attribute('encrypted_value', encrypted_value or b'encrypted')
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


def create_mock_user(user_id="user123", login="testuser", status="active", roles=""):
    """Create a mock User object."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', login)
    ctx.set_attribute('status', status)
    ctx.set_attribute('roles', roles)
    return mock_user


def create_mock_role(role_id=1, name="TestRole"):
    """Create a mock SystemRole object."""
    mock_role = Mock()
    mock_role.configure(recursive=True)
    ctx = mock_role.mock_context()
    ctx.set_attribute('id', role_id)
    ctx.set_attribute('name', name)
    return mock_role


def generate_user_id():
    """Generate a random user ID."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))


def generate_secret_name():
    """Generate a random secret name."""
    prefix = ''.join(random.choices(string.ascii_lowercase, k=8))
    suffix = random.randint(1000, 9999)
    return f"secret_{prefix}_{suffix}"


def generate_secret_value():
    """Generate a random secret value."""
    length = random.randint(8, 32)
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


# =============================================================================
# Property Tests - Property 31: Secret Scope Access Control
# =============================================================================

def test_user_without_permission_cannot_access_secret():
    """
    **Feature: system-configuration, Property 31: Secret Scope Access Control**
    **Validates: Requirements 11.7, 12.2**
    
    Users without read permission should be denied access to secret values.
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        user_id = generate_user_id()
        secret_name = generate_secret_name()
        secret_value = generate_secret_value()
        scope_id = random.randint(1, 100)
        
        # Encrypt the secret value
        encrypted_value = encrypt_value(secret_value, key)
        
        mock_secret = create_mock_secret(
            name=secret_name,
            scope_id=scope_id,
            encrypted_value=encrypted_value
        )
        mock_scope = create_mock_scope(scope_id=scope_id, name="test_scope")
        mock_user = create_mock_user(user_id=user_id, status="active", roles="")  # No roles
        
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
            elif current_query == 1:
                # Second query: User (for permission check)
                mock_filter.mock_context().mock_method('first', return_value=mock_user)
            else:
                # Other queries: SecretScope
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # Attempt to get secret value should fail
        try:
            manager.get_secret_value(secret_name, scope_id, user_id)
            assert False, "Should have raised ScopeAccessDeniedError"
        except ScopeAccessDeniedError:
            pass  # Expected


def test_inactive_user_cannot_access_secret():
    """
    **Feature: system-configuration, Property 31: Secret Scope Access Control**
    **Validates: Requirements 11.7, 12.2**
    
    Inactive users should be denied access to secret values.
    """
    inactive_statuses = ["inactive", "suspended", "disabled", "locked"]
    
    for status in inactive_statuses:
        for _ in range(25):
            mock_session = create_mock_session()
            key = generate_encryption_key()
            
            user_id = generate_user_id()
            secret_name = generate_secret_name()
            secret_value = generate_secret_value()
            scope_id = random.randint(1, 100)
            
            encrypted_value = encrypt_value(secret_value, key)
            
            mock_secret = create_mock_secret(
                name=secret_name,
                scope_id=scope_id,
                encrypted_value=encrypted_value
            )
            mock_scope = create_mock_scope(scope_id=scope_id, name="test_scope")
            mock_user = create_mock_user(user_id=user_id, status=status, roles="Admin")
            
            query_count = [0]
            
            def create_query_for_model(*args, **kwargs):
                mock_query = Mock()
                mock_query.configure(recursive=True)
                
                current_query = query_count[0]
                query_count[0] += 1
                
                mock_filter = Mock()
                mock_filter.configure(recursive=True)
                
                if current_query == 0:
                    mock_filter.mock_context().mock_method('first', return_value=mock_secret)
                elif current_query == 1:
                    mock_filter.mock_context().mock_method('first', return_value=mock_user)
                else:
                    mock_filter.mock_context().mock_method('first', return_value=mock_scope)
                
                mock_query.mock_context().mock_method('filter', return_value=mock_filter)
                return mock_query
            
            mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
            
            manager = SecretManager(mock_session, key)
            
            try:
                manager.get_secret_value(secret_name, scope_id, user_id)
                assert False, f"Should have raised ScopeAccessDeniedError for status '{status}'"
            except ScopeAccessDeniedError:
                pass  # Expected


def test_nonexistent_user_cannot_access_secret():
    """
    **Feature: system-configuration, Property 31: Secret Scope Access Control**
    **Validates: Requirements 11.7, 12.2**
    
    Non-existent users should be denied access to secret values.
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        user_id = generate_user_id()
        secret_name = generate_secret_name()
        secret_value = generate_secret_value()
        scope_id = random.randint(1, 100)
        
        encrypted_value = encrypt_value(secret_value, key)
        
        mock_secret = create_mock_secret(
            name=secret_name,
            scope_id=scope_id,
            encrypted_value=encrypted_value
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
                mock_filter.mock_context().mock_method('first', return_value=mock_secret)
            elif current_query == 1:
                # User not found
                mock_filter.mock_context().mock_method('first', return_value=None)
            else:
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        try:
            manager.get_secret_value(secret_name, scope_id, user_id)
            assert False, "Should have raised ScopeAccessDeniedError for non-existent user"
        except ScopeAccessDeniedError:
            pass  # Expected


def test_access_without_user_id_succeeds():
    """
    **Feature: system-configuration, Property 31: Secret Scope Access Control**
    **Validates: Requirements 11.7, 12.2**
    
    When no user_id is provided, permission check is skipped (system access).
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        secret_name = generate_secret_name()
        secret_value = generate_secret_value()
        scope_id = random.randint(1, 100)
        
        encrypted_value = encrypt_value(secret_value, key)
        
        mock_secret = create_mock_secret(
            name=secret_name,
            scope_id=scope_id,
            encrypted_value=encrypted_value
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
                mock_filter.mock_context().mock_method('first', return_value=mock_secret)
            else:
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # Access without user_id should succeed
        result = manager.get_secret_value(secret_name, scope_id, user_id=None)
        
        assert result.value == secret_value
        assert result.name == secret_name


def test_check_scope_permission_returns_false_for_no_roles():
    """
    **Feature: system-configuration, Property 31: Secret Scope Access Control**
    **Validates: Requirements 11.7, 12.2**
    
    check_scope_permission should return False for users with no roles.
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        user_id = generate_user_id()
        scope_id = random.randint(1, 100)
        
        mock_user = create_mock_user(user_id=user_id, status="active", roles="")
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
                mock_filter.mock_context().mock_method('first', return_value=mock_user)
            else:
                mock_filter.mock_context().mock_method('first', return_value=mock_scope)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        # Check permission should return False
        result = manager.check_scope_permission(user_id, scope_id, 'read')
        assert result == False, "User with no roles should not have permission"
