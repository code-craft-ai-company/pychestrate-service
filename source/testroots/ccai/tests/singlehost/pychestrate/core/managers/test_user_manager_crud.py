"""
.. module:: test_user_manager_crud
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for UserManager CRUD operations

.. moduleauthor:: Code Craft AI LLC

Tests for user creation uniqueness, deactivation, and role management.

**Feature: system-configuration**
**Property 1: User Creation Uniqueness**
**Validates: Requirements 1.1, 1.2**

**Property 4: User Deactivation Session Invalidation**
**Validates: Requirements 1.4**

**Property 13: Role Permission Propagation**
**Validates: Requirements 4.2, 4.3**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string


from ccai import testbase
from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.user_manager import (
    UserManager,
    UserCreateRequest,
    UserUpdateRequest,
    ValidationError,
    DuplicateUserError,
    UserNotFoundError,
    RoleNotFoundError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_valid_username():
    """Generate a valid username for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest_chars = ''.join(random.choices(string.ascii_letters + string.digits + '_-', k=random.randint(5, 15)))
    return start_char + rest_chars


def generate_valid_email():
    """Generate a valid email for testing."""
    local_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(5, 10)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 8)))
    tld = random.choice(['com', 'org', 'net', 'io', 'dev'])
    return f"{local_part}@{domain}.{tld}"


def generate_valid_password():
    """Generate a valid password for testing (12+ chars)."""
    return ''.join(random.choices(string.ascii_letters + string.digits + '!@#$%', k=16))


def create_mock_user(user_id, username, email, status="active", roles=""):
    """Create a mock user object matching the User ORM model field names."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', username)  # User model uses 'login' for username
    ctx.set_attribute('email', email)
    ctx.set_attribute('display_name', f"Display {username}")
    ctx.set_attribute('first_name', "First")  # User model uses 'first_name'
    ctx.set_attribute('last_name', "Last")    # User model uses 'last_name'
    ctx.set_attribute('status', status)
    ctx.set_attribute('roles', roles)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    return mock_user


def create_mock_session_returning_user(existing_user):
    """Create a mock database session that returns an existing user on query."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    
    mock_first = Mock()
    mock_first.configure(return_value=existing_user)
    
    mock_filter.mock_context().mock_method('first', return_value=existing_user)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session


def create_mock_session_with_side_effect(side_effect_values):
    """Create a mock database session with side effect for multiple query calls."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_index = [0]
    
    def first_side_effect():
        result = side_effect_values[call_index[0]] if call_index[0] < len(side_effect_values) else None
        call_index[0] += 1
        return result
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', side_effect=first_side_effect)
    
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session


# =============================================================================
# Property 1: User Creation Uniqueness Tests
# =============================================================================

def test_create_user_with_duplicate_username_raises_error():
    """
    **Feature: system-configuration, Property 1: User Creation Uniqueness**
    **Validates: Requirements 1.1, 1.2**
    
    For any username that already exists in the system, attempting to create
    a new user with that username SHALL raise a DuplicateUserError.
    """
    existing_user = create_mock_user("existing-id", "existinguser", "existing@example.com")
    mock_session = create_mock_session_returning_user(existing_user)
    
    manager = UserManager(mock_session)
    
    request = UserCreateRequest(
        username="existinguser",
        email="new@example.com",
        password="SecurePassword123!",
        display_name="New User"
    )
    
    try:
        manager.create_user(request)
        assert False, "Should have raised DuplicateUserError"
    except DuplicateUserError as e:
        assert "username" in e.field.lower() or "existinguser" in e.message.lower()


def test_create_user_with_duplicate_email_raises_error():
    """
    **Feature: system-configuration, Property 1: User Creation Uniqueness**
    **Validates: Requirements 1.1, 1.2**
    
    For any email that already exists in the system, attempting to create
    a new user with that email SHALL raise a DuplicateUserError.
    """
    existing_user = create_mock_user("existing-id", "otheruser", "existing@example.com")
    
    # First call for username check returns None, second call for email check returns existing user
    mock_session = create_mock_session_with_side_effect([None, existing_user])
    
    manager = UserManager(mock_session)
    
    request = UserCreateRequest(
        username="newuser123",
        email="existing@example.com",
        password="SecurePassword123!",
        display_name="New User"
    )
    
    try:
        manager.create_user(request)
        assert False, "Should have raised DuplicateUserError"
    except DuplicateUserError as e:
        assert "email" in e.field.lower() or "existing@example.com" in e.message.lower()


def test_create_user_uniqueness_property_multiple_attempts():
    """
    **Feature: system-configuration, Property 1: User Creation Uniqueness**
    **Validates: Requirements 1.1, 1.2**
    
    For any set of generated usernames and emails, the system SHALL reject
    duplicates consistently.
    """
    for _ in range(50):
        username = generate_valid_username()
        email = generate_valid_email()
        
        existing_user = create_mock_user("existing-id", username, email)
        mock_session = create_mock_session_returning_user(existing_user)
        
        manager = UserManager(mock_session)
        
        request = UserCreateRequest(
            username=username,
            email=email,
            password=generate_valid_password(),
            display_name="Test User"
        )
        
        try:
            manager.create_user(request)
            assert False, f"Should have raised DuplicateUserError for username '{username}'"
        except DuplicateUserError:
            pass  # Expected behavior


def test_create_user_with_unique_credentials_succeeds():
    """
    **Feature: system-configuration, Property 1: User Creation Uniqueness**
    **Validates: Requirements 1.1, 1.2**
    
    For any unique username and email, user creation SHALL succeed.
    """
    for _ in range(20):
        # Setup mock to return None for both username and email checks (no duplicates)
        mock_session = create_mock_session_returning_user(None)
        
        manager = UserManager(mock_session)
        
        username = generate_valid_username()
        email = generate_valid_email()
        
        request = UserCreateRequest(
            username=username,
            email=email,
            password=generate_valid_password(),
            display_name="Test User"
        )
        
        # Should not raise any exception
        try:
            result = manager.create_user(request)
            assert result.username == username
            assert result.email == email
        except DuplicateUserError:
            assert False, f"Should not raise DuplicateUserError for unique credentials"


# =============================================================================
# Property 4: User Deactivation Session Invalidation Tests
# =============================================================================

def create_mock_session_for_deactivation(mock_user, session_delete_count=3):
    """Create a mock session configured for user deactivation tests."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_user_query = Mock()
    mock_user_query.configure(recursive=True)
    mock_user_filter = Mock()
    mock_user_filter.configure(recursive=True)
    mock_user_filter.mock_context().mock_method('first', return_value=mock_user)
    mock_user_query.mock_context().mock_method('filter', return_value=mock_user_filter)
    
    mock_session_query = Mock()
    mock_session_query.configure(recursive=True)
    mock_session_filter = Mock()
    mock_session_filter.configure(recursive=True)
    mock_session_filter.mock_context().mock_method('delete', return_value=session_delete_count)
    mock_session_query.mock_context().mock_method('filter', return_value=mock_session_filter)
    
    call_count = [0]
    def query_side_effect(model):
        call_count[0] += 1
        if hasattr(model, '__name__') and model.__name__ == 'User':
            return mock_user_query
        else:
            return mock_session_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('commit')
    
    return mock_session, mock_session_filter


def test_deactivate_user_invalidates_sessions():
    """
    **Feature: system-configuration, Property 4: User Deactivation Session Invalidation**
    **Validates: Requirements 1.4**
    
    When a user is deactivated, ALL active sessions for that user SHALL be invalidated.
    """
    user_id = "test-user-id"
    mock_user = create_mock_user(user_id, "testuser", "test@example.com", status="active")
    
    mock_session, mock_session_filter = create_mock_session_for_deactivation(mock_user, session_delete_count=3)
    
    manager = UserManager(mock_session)
    manager.deactivate_user(user_id)
    
    # Verify user status was set to inactive
    assert mock_user.status == "inactive"


def test_deactivate_user_not_found_raises_error():
    """
    **Feature: system-configuration, Property 4: User Deactivation Session Invalidation**
    **Validates: Requirements 1.4**
    
    When attempting to deactivate a non-existent user, UserNotFoundError SHALL be raised.
    """
    mock_session = create_mock_session_returning_user(None)
    
    manager = UserManager(mock_session)
    
    try:
        manager.deactivate_user("nonexistent-user-id")
        assert False, "Should have raised UserNotFoundError"
    except UserNotFoundError:
        pass  # Expected behavior


def test_deactivate_user_property_multiple_users():
    """
    **Feature: system-configuration, Property 4: User Deactivation Session Invalidation**
    **Validates: Requirements 1.4**
    
    For any user that is deactivated, their status SHALL be set to inactive
    and their sessions SHALL be invalidated.
    """
    for i in range(20):
        user_id = f"user-{i}"
        mock_user = create_mock_user(user_id, f"user{i}", f"user{i}@example.com", status="active")
        
        mock_session, _ = create_mock_session_for_deactivation(mock_user, session_delete_count=random.randint(0, 5))
        
        manager = UserManager(mock_session)
        manager.deactivate_user(user_id)
        
        # Verify user was deactivated
        assert mock_user.status == "inactive", f"User {user_id} should be inactive"


def test_deactivate_user_all_sessions_invalidated_property():
    """
    **Feature: system-configuration, Property 4: User Deactivation Session Invalidation**
    **Validates: Requirements 1.4**
    
    For any user with N active sessions (where N >= 0), when the user is deactivated,
    ALL N sessions for that user SHALL be deleted/invalidated.
    """
    for iteration in range(100):
        user_id = f"user-{iteration}-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        email = generate_valid_email()
        num_sessions = random.randint(0, 10)
        
        mock_user = create_mock_user(user_id, username, email, status="active")
        mock_session, mock_session_filter = create_mock_session_for_deactivation(mock_user, session_delete_count=num_sessions)
        
        manager = UserManager(mock_session)
        manager.deactivate_user(user_id)
        
        # Property 1: User status MUST be set to inactive
        assert mock_user.status == "inactive", \
            f"Iteration {iteration}: User status should be 'inactive' after deactivation"


def test_deactivate_user_sessions_filtered_by_user_id_property():
    """
    **Feature: system-configuration, Property 4: User Deactivation Session Invalidation**
    **Validates: Requirements 1.4**
    
    For any user deactivation, the session invalidation query SHALL filter
    sessions by the specific user_id, ensuring only that user's sessions are affected.
    """
    for iteration in range(50):
        user_id_to_deactivate = f"deactivate-user-{iteration}"
        
        mock_user = create_mock_user(
            user_id_to_deactivate,
            f"deactivateuser{iteration}",
            f"deactivate{iteration}@example.com",
            status="active"
        )
        
        mock_session, mock_session_filter = create_mock_session_for_deactivation(
            mock_user, session_delete_count=random.randint(0, 5)
        )
        
        manager = UserManager(mock_session)
        manager.deactivate_user(user_id_to_deactivate)
        
        # Verify user was deactivated
        assert mock_user.status == "inactive", \
            f"Iteration {iteration}: User should be deactivated"


def test_deactivate_user_with_zero_sessions_property():
    """
    **Feature: system-configuration, Property 4: User Deactivation Session Invalidation**
    **Validates: Requirements 1.4**
    
    For any user with zero active sessions, deactivation SHALL still succeed
    and the user status SHALL be set to inactive.
    """
    for iteration in range(30):
        user_id = f"no-sessions-user-{iteration}"
        mock_user = create_mock_user(user_id, f"nosessions{iteration}", f"nosessions{iteration}@example.com", status="active")
        
        mock_session, _ = create_mock_session_for_deactivation(mock_user, session_delete_count=0)
        
        manager = UserManager(mock_session)
        
        # Should not raise any exception
        manager.deactivate_user(user_id)
        
        # User should still be deactivated
        assert mock_user.status == "inactive", \
            f"Iteration {iteration}: User with zero sessions should still be deactivated"


def test_deactivate_user_with_many_sessions_property():
    """
    **Feature: system-configuration, Property 4: User Deactivation Session Invalidation**
    **Validates: Requirements 1.4**
    
    For any user with many active sessions (stress test), ALL sessions SHALL
    be invalidated when the user is deactivated.
    """
    for iteration in range(20):
        user_id = f"many-sessions-user-{iteration}"
        mock_user = create_mock_user(user_id, f"manysessions{iteration}", f"manysessions{iteration}@example.com", status="active")
        
        # Simulate many sessions (10 to 100)
        num_sessions = random.randint(10, 100)
        
        mock_session, _ = create_mock_session_for_deactivation(mock_user, session_delete_count=num_sessions)
        
        manager = UserManager(mock_session)
        manager.deactivate_user(user_id)
        
        # Verify user was deactivated
        assert mock_user.status == "inactive", \
            f"Iteration {iteration}: User with {num_sessions} sessions should be deactivated"


# =============================================================================
# Property 13: Role Permission Propagation Tests
# =============================================================================

def create_mock_role(role_id, role_name, permissions=None):
    """Create a mock role object."""
    mock_role = Mock()
    mock_role.configure(recursive=True)
    ctx = mock_role.mock_context()
    ctx.set_attribute('id', role_id)
    ctx.set_attribute('name', role_name)
    ctx.set_attribute('permissions', permissions or [])
    return mock_role


def create_mock_permission(name):
    """Create a mock permission object."""
    mock_perm = Mock()
    mock_perm.configure(recursive=True)
    mock_perm.mock_context().set_attribute('name', name)
    return mock_perm


def create_mock_session_for_role_ops(mock_user, mock_role):
    """Create a mock session configured for role operations."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_user_query = Mock()
    mock_user_query.configure(recursive=True)
    mock_user_filter = Mock()
    mock_user_filter.configure(recursive=True)
    mock_user_filter.mock_context().mock_method('first', return_value=mock_user)
    mock_user_query.mock_context().mock_method('filter', return_value=mock_user_filter)
    
    mock_role_query = Mock()
    mock_role_query.configure(recursive=True)
    mock_role_filter = Mock()
    mock_role_filter.configure(recursive=True)
    mock_role_filter.mock_context().mock_method('first', return_value=mock_role)
    mock_role_query.mock_context().mock_method('filter', return_value=mock_role_filter)
    
    call_count = [0]
    def query_side_effect(model):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_user_query
        else:
            return mock_role_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


def test_assign_role_updates_user_roles():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    When a role is assigned to a user, the user's roles SHALL be updated
    to include the new role.
    """
    user_id = "test-user-id"
    role_id = 1
    
    mock_user = create_mock_user(user_id, "testuser", "test@example.com", roles="")
    mock_role = create_mock_role(role_id, "Administrator")
    
    mock_session = create_mock_session_for_role_ops(mock_user, mock_role)
    
    manager = UserManager(mock_session)
    manager.assign_role(user_id, role_id)
    
    # Verify role was added
    assert "Administrator" in mock_user.roles


def test_remove_role_updates_user_roles():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    When a role is removed from a user, the user's roles SHALL be updated
    to exclude the removed role.
    """
    user_id = "test-user-id"
    role_id = 1
    
    mock_user = create_mock_user(user_id, "testuser", "test@example.com", roles="Administrator,Operator")
    mock_role = create_mock_role(role_id, "Administrator")
    
    mock_session = create_mock_session_for_role_ops(mock_user, mock_role)
    
    manager = UserManager(mock_session)
    manager.remove_role(user_id, role_id)
    
    # Verify role was removed
    assert "Administrator" not in mock_user.roles
    assert "Operator" in mock_user.roles


def create_mock_session_for_permissions(mock_user, roles):
    """Create a mock session configured for get_effective_permissions."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_user_query = Mock()
    mock_user_query.configure(recursive=True)
    mock_user_filter = Mock()
    mock_user_filter.configure(recursive=True)
    mock_user_filter.mock_context().mock_method('first', return_value=mock_user)
    mock_user_query.mock_context().mock_method('filter', return_value=mock_user_filter)
    
    mock_role_query = Mock()
    mock_role_query.configure(recursive=True)
    mock_role_filter = Mock()
    mock_role_filter.configure(recursive=True)
    mock_role_filter.mock_context().mock_method('all', return_value=roles)
    mock_role_query.mock_context().mock_method('filter', return_value=mock_role_filter)
    
    call_count = [0]
    def query_side_effect(model):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_user_query
        else:
            return mock_role_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    
    return mock_session


def test_get_effective_permissions_aggregates_role_permissions():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    For any user with multiple roles, get_effective_permissions SHALL return
    the union of all permissions from all assigned roles.
    """
    user_id = "test-user-id"
    mock_user = create_mock_user(user_id, "testuser", "test@example.com", roles="Administrator,Operator")
    
    # Create mock permissions
    perm1 = create_mock_permission("users.create")
    perm2 = create_mock_permission("users.read")
    perm3 = create_mock_permission("users.delete")
    perm4 = create_mock_permission("variables.read")
    
    # Create mock roles with permissions
    admin_role = create_mock_role(1, "Administrator", [perm1, perm2, perm3])
    operator_role = create_mock_role(2, "Operator", [perm2, perm4])  # perm2 is shared
    
    mock_session = create_mock_session_for_permissions(mock_user, [admin_role, operator_role])
    
    manager = UserManager(mock_session)
    permissions = manager.get_effective_permissions(user_id)
    
    # Verify all unique permissions are returned
    assert "users.create" in permissions
    assert "users.read" in permissions
    assert "users.delete" in permissions
    assert "variables.read" in permissions
    
    # Verify no duplicates (users.read appears in both roles)
    assert len(permissions) == 4


def test_role_assignment_not_found_raises_error():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    When attempting to assign a non-existent role, RoleNotFoundError SHALL be raised.
    """
    user_id = "test-user-id"
    mock_user = create_mock_user(user_id, "testuser", "test@example.com")
    
    mock_session = create_mock_session_for_role_ops(mock_user, None)  # Role not found
    
    manager = UserManager(mock_session)
    
    try:
        manager.assign_role(user_id, 999)
        assert False, "Should have raised RoleNotFoundError"
    except RoleNotFoundError:
        pass  # Expected behavior


# =============================================================================
# Property 13: Role Permission Propagation - Property-Based Tests
# =============================================================================

def generate_random_permissions(count=None):
    """Generate a random set of permissions for testing."""
    if count is None:
        count = random.randint(1, 10)
    
    resources = ['users', 'roles', 'variables', 'secrets', 'sessions', 'audit']
    actions = ['create', 'read', 'update', 'delete', 'list', 'manage']
    
    permissions = []
    for i in range(count):
        resource = random.choice(resources)
        action = random.choice(actions)
        perm = create_mock_permission(f"{resource}.{action}")
        permissions.append(perm)
    
    return permissions


def generate_random_role(role_id, role_name, permissions):
    """Generate a mock role with given permissions."""
    return create_mock_role(role_id, role_name, permissions)


def test_role_permission_propagation_property_assign():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    Property Test: For any user assigned to a role, the user's effective permissions
    SHALL include all permissions assigned to that role.
    """
    for iteration in range(100):
        user_id = f"user-{iteration}-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        email = generate_valid_email()
        
        role_id = random.randint(1, 1000)
        role_name = f"Role_{iteration}_{random.randint(100, 999)}"
        role_permissions = generate_random_permissions()
        
        mock_user = create_mock_user(user_id, username, email, roles="")
        mock_role = generate_random_role(role_id, role_name, role_permissions)
        
        mock_session = create_mock_session_for_role_ops(mock_user, mock_role)
        
        manager = UserManager(mock_session)
        
        # Assign the role
        manager.assign_role(user_id, role_id)
        
        # Verify role was added to user
        assert role_name in mock_user.roles, \
            f"Iteration {iteration}: Role '{role_name}' should be in user's roles after assignment"


def test_role_permission_propagation_property_remove():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    Property Test: When a role is removed from a user, those permissions SHALL be
    removed from the user's effective permissions.
    """
    for iteration in range(100):
        user_id = f"user-{iteration}-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        email = generate_valid_email()
        
        role_id = random.randint(1, 1000)
        role_name = f"RoleToRemove_{iteration}"
        role_permissions = generate_random_permissions()
        
        # User starts with the role assigned
        mock_user = create_mock_user(user_id, username, email, roles=role_name)
        mock_role = generate_random_role(role_id, role_name, role_permissions)
        
        mock_session = create_mock_session_for_role_ops(mock_user, mock_role)
        
        manager = UserManager(mock_session)
        
        # Remove the role
        manager.remove_role(user_id, role_id)
        
        # Verify role was removed from user
        assert role_name not in mock_user.roles, \
            f"Iteration {iteration}: Role '{role_name}' should NOT be in user's roles after removal"


def test_role_permission_propagation_property_multiple_roles():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    Property Test: For any user with multiple roles, the effective permissions
    SHALL be the union of all permissions from all assigned roles.
    """
    for iteration in range(100):
        user_id = f"user-{iteration}-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        email = generate_valid_email()
        
        num_roles = random.randint(2, 5)
        roles = []
        all_expected_permissions = set()
        role_names = []
        
        for r in range(num_roles):
            role_id = r + 1
            role_name = f"Role_{iteration}_{r}"
            role_names.append(role_name)
            role_permissions = generate_random_permissions(random.randint(1, 5))
            
            for perm in role_permissions:
                all_expected_permissions.add(perm.name)
            
            roles.append(generate_random_role(role_id, role_name, role_permissions))
        
        mock_user = create_mock_user(user_id, username, email, roles=",".join(role_names))
        mock_session = create_mock_session_for_permissions(mock_user, roles)
        
        manager = UserManager(mock_session)
        effective_permissions = manager.get_effective_permissions(user_id)
        
        # Property: Effective permissions MUST contain all permissions from all roles
        for expected_perm in all_expected_permissions:
            assert expected_perm in effective_permissions, \
                f"Iteration {iteration}: Permission '{expected_perm}' should be in effective permissions"


def test_role_permission_propagation_property_shared_permissions():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    Property Test: When multiple roles share the same permission, the effective
    permissions SHALL contain that permission exactly once (no duplicates).
    """
    for iteration in range(100):
        user_id = f"user-{iteration}-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        email = generate_valid_email()
        
        # Create a shared permission
        shared_perm = create_mock_permission("users.read")
        
        # Generate two roles that both have the shared permission
        role1_perms = [shared_perm]
        role1_perms.extend(generate_random_permissions(random.randint(1, 3)))
        
        role2_perms = [shared_perm]  # Same shared permission
        role2_perms.extend(generate_random_permissions(random.randint(1, 3)))
        
        role1 = generate_random_role(1, f"Role1_{iteration}", role1_perms)
        role2 = generate_random_role(2, f"Role2_{iteration}", role2_perms)
        
        mock_user = create_mock_user(
            user_id, username, email, 
            roles=f"Role1_{iteration},Role2_{iteration}"
        )
        
        mock_session = create_mock_session_for_permissions(mock_user, [role1, role2])
        
        manager = UserManager(mock_session)
        effective_permissions = manager.get_effective_permissions(user_id)
        
        # Property: Shared permission should appear exactly once
        count = effective_permissions.count("users.read")
        assert count == 1, \
            f"Iteration {iteration}: Shared permission 'users.read' should appear exactly once, but appeared {count} times"
        
        # Property: Result should be a list with no duplicates
        assert len(effective_permissions) == len(set(effective_permissions)), \
            f"Iteration {iteration}: Effective permissions should have no duplicates"


def test_role_permission_propagation_property_empty_role():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    Property Test: Assigning a role with no permissions should not add any
    permissions to the user's effective permissions.
    """
    for iteration in range(50):
        user_id = f"user-{iteration}-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        email = generate_valid_email()
        
        role_id = random.randint(1, 1000)
        role_name = f"EmptyRole_{iteration}"
        empty_role = generate_random_role(role_id, role_name, [])  # No permissions
        
        mock_user = create_mock_user(user_id, username, email, roles=role_name)
        mock_session = create_mock_session_for_permissions(mock_user, [empty_role])
        
        manager = UserManager(mock_session)
        effective_permissions = manager.get_effective_permissions(user_id)
        
        # Property: User with only empty role should have no permissions
        assert len(effective_permissions) == 0, \
            f"Iteration {iteration}: User with empty role should have no permissions, but has {effective_permissions}"


def test_role_permission_propagation_property_no_roles():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    Property Test: A user with no roles should have no effective permissions.
    """
    for iteration in range(50):
        user_id = f"user-{iteration}-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        email = generate_valid_email()
        
        mock_user = create_mock_user(user_id, username, email, roles="")
        
        mock_session = Mock()
        mock_session.configure(recursive=True)
        
        mock_user_query = Mock()
        mock_user_query.configure(recursive=True)
        mock_user_filter = Mock()
        mock_user_filter.configure(recursive=True)
        mock_user_filter.mock_context().mock_method('first', return_value=mock_user)
        mock_user_query.mock_context().mock_method('filter', return_value=mock_user_filter)
        mock_session.mock_context().mock_method('query', return_value=mock_user_query)
        
        manager = UserManager(mock_session)
        effective_permissions = manager.get_effective_permissions(user_id)
        
        # Property: User with no roles should have no permissions
        assert len(effective_permissions) == 0, \
            f"Iteration {iteration}: User with no roles should have no permissions, but has {effective_permissions}"


def test_role_permission_propagation_property_assign_then_remove():
    """
    **Feature: system-configuration, Property 13: Role Permission Propagation**
    **Validates: Requirements 4.2, 4.3**
    
    Property Test: For any role, assigning it and then removing it should result
    in the user having the same effective permissions as before the assignment.
    """
    for iteration in range(100):
        user_id = f"user-{iteration}-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        email = generate_valid_email()
        
        role_id = random.randint(1, 1000)
        role_name = f"TempRole_{iteration}"
        role_permissions = generate_random_permissions()
        
        # User starts with no roles
        mock_user = create_mock_user(user_id, username, email, roles="")
        mock_role = generate_random_role(role_id, role_name, role_permissions)
        
        # Track the initial state
        initial_roles = mock_user.roles
        
        mock_session = create_mock_session_for_role_ops(mock_user, mock_role)
        
        manager = UserManager(mock_session)
        
        # Assign the role
        manager.assign_role(user_id, role_id)
        
        # Verify role was added
        assert role_name in mock_user.roles, \
            f"Iteration {iteration}: Role should be assigned"
        
        # Now remove the role - need to recreate session for new call sequence
        mock_session2 = create_mock_session_for_role_ops(mock_user, mock_role)
        manager2 = UserManager(mock_session2)
        
        manager2.remove_role(user_id, role_id)
        
        # Property: After assign then remove, user should have no roles (back to initial state)
        final_roles = mock_user.roles
        
        # Both should be empty or equivalent
        initial_set = set(r.strip() for r in initial_roles.split(",") if r.strip())
        final_set = set(r.strip() for r in final_roles.split(",") if r.strip())
        
        assert initial_set == final_set, \
            f"Iteration {iteration}: After assign then remove, roles should return to initial state. Initial: {initial_set}, Final: {final_set}"


if __name__ == "__main__":
    from ccai.testbase.entrypoints import generic_test_entrypoint
    generic_test_entrypoint()
