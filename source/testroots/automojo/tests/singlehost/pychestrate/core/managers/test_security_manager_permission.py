"""
.. module:: test_security_manager_permission
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for SecurityManager permission checking functionality

.. moduleauthor:: Automation Mojo LLC

Tests for permission check enforcement.

**Feature: system-configuration**
**Property 14: Permission Check Enforcement**
**Validates: Requirements 4.4**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.security_manager import (
    SecurityManager,
    PermissionDeniedError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_permission_name():
    """Generate a random permission name."""
    resources = ['users', 'roles', 'sessions', 'variables', 'secrets', 'audit']
    actions = ['create', 'read', 'update', 'delete', 'list', 'manage']
    return f"{random.choice(resources)}.{random.choice(actions)}"


def create_mock_permission(name):
    """Create a mock permission object."""
    mock_perm = Mock()
    mock_perm.configure(recursive=True)
    ctx = mock_perm.mock_context()
    ctx.set_attribute('name', name)
    ctx.set_attribute('description', f"Permission to {name}")
    return mock_perm


def create_mock_role(name, permissions):
    """Create a mock role object with permissions."""
    mock_role = Mock()
    mock_role.configure(recursive=True)
    ctx = mock_role.mock_context()
    ctx.set_attribute('name', name)
    ctx.set_attribute('permissions', permissions)
    ctx.set_attribute('is_system', False)
    return mock_role


def create_mock_user(user_id, username, roles_str, status="active"):
    """Create a mock user object."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', username)
    ctx.set_attribute('roles', roles_str)
    ctx.set_attribute('status', status)
    ctx.set_attribute('email', f"{username}@example.com")
    return mock_user


def create_mock_session_for_permission(mock_user, mock_roles):
    """Create a mock database session for permission tests."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    query_call_count = [0]
    
    def query_side_effect(model):
        query_call_count[0] += 1
        
        mock_query = Mock()
        mock_query.configure(recursive=True)
        
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First query is for User, second is for SystemRole
        if query_call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=mock_user)
        else:
            mock_filter.mock_context().mock_method('all', return_value=mock_roles)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    
    return mock_session


# =============================================================================
# Property 14: Permission Check Enforcement Tests
# =============================================================================

def test_user_with_permission_is_allowed():
    """
    **Feature: system-configuration, Property 14: Permission Check Enforcement**
    **Validates: Requirements 4.4**
    
    User with required permission should be allowed.
    """
    user_id = uuid.uuid4()
    username = "testuser"
    permission_name = "users.create"
    
    mock_permission = create_mock_permission(permission_name)
    mock_role = create_mock_role("Administrator", [mock_permission])
    mock_user = create_mock_user(user_id, username, "Administrator")
    mock_session = create_mock_session_for_permission(mock_user, [mock_role])
    
    manager = SecurityManager(mock_session)
    
    result = manager.check_permission(str(user_id), permission_name)
    
    assert result == True


def test_user_without_permission_is_denied():
    """
    **Feature: system-configuration, Property 14: Permission Check Enforcement**
    **Validates: Requirements 4.4**
    
    User without required permission should be denied.
    """
    user_id = uuid.uuid4()
    username = "testuser"
    
    mock_permission = create_mock_permission("users.read")
    mock_role = create_mock_role("Viewer", [mock_permission])
    mock_user = create_mock_user(user_id, username, "Viewer")
    mock_session = create_mock_session_for_permission(mock_user, [mock_role])
    
    manager = SecurityManager(mock_session)
    
    # User has users.read but not users.create
    result = manager.check_permission(str(user_id), "users.create")
    
    assert result == False


def test_nonexistent_user_is_denied():
    """
    **Feature: system-configuration, Property 14: Permission Check Enforcement**
    **Validates: Requirements 4.4**
    
    Non-existent user should be denied.
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=None)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_session)
    
    result = manager.check_permission("nonexistent-user-id", "users.create")
    
    assert result == False


def test_inactive_user_is_denied():
    """
    **Feature: system-configuration, Property 14: Permission Check Enforcement**
    **Validates: Requirements 4.4**
    
    Inactive user should be denied even with permission.
    """
    user_id = uuid.uuid4()
    username = "inactiveuser"
    
    mock_user = create_mock_user(user_id, username, "Administrator", status="inactive")
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_user)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_session)
    
    result = manager.check_permission(str(user_id), "users.create")
    
    assert result == False


def test_user_with_no_roles_is_denied():
    """
    **Feature: system-configuration, Property 14: Permission Check Enforcement**
    **Validates: Requirements 4.4**
    
    User with no roles should be denied.
    """
    user_id = uuid.uuid4()
    username = "noroleuser"
    
    mock_user = create_mock_user(user_id, username, "")  # No roles
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_user)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_session)
    
    result = manager.check_permission(str(user_id), "users.create")
    
    assert result == False


def test_user_with_multiple_roles_gets_combined_permissions():
    """
    **Feature: system-configuration, Property 14: Permission Check Enforcement**
    **Validates: Requirements 4.4**
    
    User with multiple roles should have combined permissions.
    """
    user_id = uuid.uuid4()
    username = "multiroleuser"
    
    # Role 1 has users.read
    mock_perm1 = create_mock_permission("users.read")
    mock_role1 = create_mock_role("Viewer", [mock_perm1])
    
    # Role 2 has users.create
    mock_perm2 = create_mock_permission("users.create")
    mock_role2 = create_mock_role("Creator", [mock_perm2])
    
    mock_user = create_mock_user(user_id, username, "Viewer,Creator")
    mock_session = create_mock_session_for_permission(mock_user, [mock_role1, mock_role2])
    
    manager = SecurityManager(mock_session)
    
    # User should have both permissions
    result1 = manager.check_permission(str(user_id), "users.read")
    assert result1 == True
    
    # Need to reset the mock for second call
    mock_session2 = create_mock_session_for_permission(mock_user, [mock_role1, mock_role2])
    manager2 = SecurityManager(mock_session2)
    
    result2 = manager2.check_permission(str(user_id), "users.create")
    assert result2 == True


def test_require_permission_raises_for_missing_permission():
    """
    **Feature: system-configuration, Property 14: Permission Check Enforcement**
    **Validates: Requirements 4.4**
    
    require_permission should raise PermissionDeniedError for missing permission.
    """
    user_id = uuid.uuid4()
    username = "testuser"
    
    mock_permission = create_mock_permission("users.read")
    mock_role = create_mock_role("Viewer", [mock_permission])
    mock_user = create_mock_user(user_id, username, "Viewer")
    mock_session = create_mock_session_for_permission(mock_user, [mock_role])
    
    manager = SecurityManager(mock_session)
    
    try:
        manager.require_permission(str(user_id), "users.delete")
        assert False, "Should have raised PermissionDeniedError"
    except PermissionDeniedError as e:
        assert "users.delete" in e.message
        assert e.permission == "users.delete"


def test_require_permission_passes_for_valid_permission():
    """
    **Feature: system-configuration, Property 14: Permission Check Enforcement**
    **Validates: Requirements 4.4**
    
    require_permission should pass silently for valid permission.
    """
    user_id = uuid.uuid4()
    username = "testuser"
    permission_name = "users.create"
    
    mock_permission = create_mock_permission(permission_name)
    mock_role = create_mock_role("Administrator", [mock_permission])
    mock_user = create_mock_user(user_id, username, "Administrator")
    mock_session = create_mock_session_for_permission(mock_user, [mock_role])
    
    manager = SecurityManager(mock_session)
    
    # Should not raise
    manager.require_permission(str(user_id), permission_name)


def test_permission_check_enforcement_property():
    """
    **Feature: system-configuration, Property 14: Permission Check Enforcement**
    **Validates: Requirements 4.4**
    
    Property Test: For any action requiring a specific permission, the Security_Manager
    SHALL allow the action if and only if the user has that permission in their
    effective permissions.
    """
    for _ in range(50):
        user_id = uuid.uuid4()
        username = f"user_{random.randint(1000, 9999)}"
        
        # Generate random permissions
        all_permissions = [generate_permission_name() for _ in range(5)]
        user_permissions = random.sample(all_permissions, k=random.randint(1, 4))
        
        # Create mock permissions and role
        mock_perms = [create_mock_permission(p) for p in user_permissions]
        mock_role = create_mock_role("TestRole", mock_perms)
        mock_user = create_mock_user(user_id, username, "TestRole")
        mock_session = create_mock_session_for_permission(mock_user, [mock_role])
        
        manager = SecurityManager(mock_session)
        
        # Test with a permission the user has
        if user_permissions:
            has_perm = random.choice(user_permissions)
            result = manager.check_permission(str(user_id), has_perm)
            assert result == True, f"User should have permission {has_perm}"
        
        # Test with a permission the user doesn't have
        missing_perms = [p for p in all_permissions if p not in user_permissions]
        if missing_perms:
            mock_session2 = create_mock_session_for_permission(mock_user, [mock_role])
            manager2 = SecurityManager(mock_session2)
            
            missing_perm = random.choice(missing_perms)
            result = manager2.check_permission(str(user_id), missing_perm)
            assert result == False, f"User should not have permission {missing_perm}"
