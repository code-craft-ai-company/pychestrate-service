"""
.. module:: test_security_manager_auth
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for SecurityManager authentication flow

.. moduleauthor:: Automation Mojo LLC

Tests for authentication correctness.

**Feature: system-configuration**
**Property 5: Authentication Correctness**
**Validates: Requirements 2.1, 2.2**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.security_manager import (
    SecurityManager,
    AuthRequest,
    AuthenticationError,
    hash_password,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_valid_username():
    """Generate a valid username for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest_chars = ''.join(random.choices(string.ascii_letters + string.digits + '_-', k=random.randint(5, 15)))
    return start_char + rest_chars


def generate_strong_password():
    """Generate a password that meets all strength requirements."""
    uppercase = random.choice(string.ascii_uppercase)
    lowercase = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    special = random.choice('!@#$%^&*()_+-=[]{}|;:,.<>?')
    remaining = ''.join(random.choices(
        string.ascii_letters + string.digits + '!@#$%^&*',
        k=random.randint(8, 16)
    ))
    password_chars = list(uppercase + lowercase + digit + special + remaining)
    random.shuffle(password_chars)
    return ''.join(password_chars)


def create_mock_user(user_id, username, status="active"):
    """Create a mock user object."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', username)
    ctx.set_attribute('status', status)
    ctx.set_attribute('email', f"{username}@example.com")
    ctx.set_attribute('display_name', f"Display {username}")
    return mock_user


def create_mock_password_history(user_id, password_hash):
    """Create a mock password history entry."""
    mock_history = Mock()
    mock_history.configure(recursive=True)
    ctx = mock_history.mock_context()
    ctx.set_attribute('user_id', user_id)
    ctx.set_attribute('password_hash', password_hash)
    return mock_history


def create_mock_session_for_auth(mock_user, mock_password_history):
    """Create a mock database session for authentication tests."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    # Track query calls to return appropriate results
    query_call_count = [0]
    
    def query_side_effect(model):
        query_call_count[0] += 1
        
        mock_query = Mock()
        mock_query.configure(recursive=True)
        
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First query is for User, second is for PasswordHistory, third is for Session
        if query_call_count[0] == 1:
            # User query - just needs filter().first()
            mock_filter.mock_context().mock_method('first', return_value=mock_user)
        elif query_call_count[0] == 2:
            # PasswordHistory query - needs filter().order_by().first()
            mock_order_by = Mock()
            mock_order_by.configure(recursive=True)
            mock_order_by.mock_context().mock_method('first', return_value=mock_password_history)
            mock_filter.mock_context().mock_method('order_by', return_value=mock_order_by)
        else:
            # Session query - needs filter().filter().order_by().all()
            mock_filter2 = Mock()
            mock_filter2.configure(recursive=True)
            mock_order_by = Mock()
            mock_order_by.configure(recursive=True)
            mock_order_by.mock_context().mock_method('all', return_value=[])
            mock_filter2.mock_context().mock_method('order_by', return_value=mock_order_by)
            mock_filter.mock_context().mock_method('filter', return_value=mock_filter2)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Property 5: Authentication Correctness Tests
# =============================================================================

def test_valid_credentials_return_session_token():
    """
    **Feature: system-configuration, Property 5: Authentication Correctness**
    **Validates: Requirements 2.1, 2.2**
    
    Valid credentials should return a session token.
    """
    user_id = "test-user-id"
    username = "testuser"
    password = "SecurePass123!"
    password_hash = hash_password(password)
    
    mock_user = create_mock_user(user_id, username)
    mock_password_history = create_mock_password_history(user_id, password_hash)
    mock_session = create_mock_session_for_auth(mock_user, mock_password_history)
    
    manager = SecurityManager(mock_session)
    
    request = AuthRequest(
        username=username,
        password=password,
        client_ip="127.0.0.1",
        user_agent="TestAgent/1.0"
    )
    
    response = manager.authenticate(request)
    
    assert response is not None
    assert response.token is not None
    assert len(response.token) > 0
    assert response.user_id == user_id
    assert response.username == username
    assert response.csrf_token is not None


def test_invalid_password_raises_authentication_error():
    """
    **Feature: system-configuration, Property 5: Authentication Correctness**
    **Validates: Requirements 2.1, 2.2**
    
    Invalid password should raise AuthenticationError with generic message.
    """
    user_id = "test-user-id"
    username = "testuser"
    correct_password = "SecurePass123!"
    wrong_password = "WrongPass456!"
    password_hash = hash_password(correct_password)
    
    mock_user = create_mock_user(user_id, username)
    mock_password_history = create_mock_password_history(user_id, password_hash)
    mock_session = create_mock_session_for_auth(mock_user, mock_password_history)
    
    manager = SecurityManager(mock_session)
    
    request = AuthRequest(
        username=username,
        password=wrong_password,
        client_ip="127.0.0.1",
        user_agent="TestAgent/1.0"
    )
    
    try:
        manager.authenticate(request)
        assert False, "Should have raised AuthenticationError"
    except AuthenticationError as e:
        # Error message should be generic (no info leakage)
        assert "Invalid credentials" in e.message


def test_nonexistent_user_raises_authentication_error():
    """
    **Feature: system-configuration, Property 5: Authentication Correctness**
    **Validates: Requirements 2.1, 2.2**
    
    Non-existent user should raise AuthenticationError with generic message.
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
    
    request = AuthRequest(
        username="nonexistent",
        password="SomePass123!",
        client_ip="127.0.0.1",
        user_agent="TestAgent/1.0"
    )
    
    try:
        manager.authenticate(request)
        assert False, "Should have raised AuthenticationError"
    except AuthenticationError as e:
        # Error message should be generic (no info leakage)
        assert "Invalid credentials" in e.message


def test_inactive_user_raises_authentication_error():
    """
    **Feature: system-configuration, Property 5: Authentication Correctness**
    **Validates: Requirements 2.1, 2.2**
    
    Inactive user should raise AuthenticationError with generic message.
    """
    user_id = "test-user-id"
    username = "testuser"
    password = "SecurePass123!"
    
    mock_user = create_mock_user(user_id, username, status="inactive")
    
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
    
    request = AuthRequest(
        username=username,
        password=password,
        client_ip="127.0.0.1",
        user_agent="TestAgent/1.0"
    )
    
    try:
        manager.authenticate(request)
        assert False, "Should have raised AuthenticationError"
    except AuthenticationError as e:
        # Error message should be generic (no info leakage)
        assert "Invalid credentials" in e.message


def test_authentication_correctness_property():
    """
    **Feature: system-configuration, Property 5: Authentication Correctness**
    **Validates: Requirements 2.1, 2.2**
    
    Property Test: For any authentication attempt, the Security_Manager SHALL
    return a valid session token if and only if the provided username exists
    and the password matches the stored hash.
    """
    for _ in range(50):
        user_id = f"user-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        password = generate_strong_password()
        password_hash = hash_password(password)
        
        mock_user = create_mock_user(user_id, username)
        mock_password_history = create_mock_password_history(user_id, password_hash)
        mock_session = create_mock_session_for_auth(mock_user, mock_password_history)
        
        manager = SecurityManager(mock_session)
        
        # Test with correct password - should succeed
        request = AuthRequest(
            username=username,
            password=password,
            client_ip="127.0.0.1",
            user_agent="TestAgent/1.0"
        )
        
        response = manager.authenticate(request)
        assert response is not None, f"Valid credentials should return a response"
        assert response.token is not None, f"Valid credentials should return a token"
        assert response.user_id == user_id, f"Response should contain correct user_id"


def test_authentication_wrong_password_property():
    """
    **Feature: system-configuration, Property 5: Authentication Correctness**
    **Validates: Requirements 2.1, 2.2**
    
    Property Test: For any authentication attempt with wrong password,
    the Security_Manager SHALL reject the authentication.
    """
    for _ in range(50):
        user_id = f"user-{random.randint(1000, 9999)}"
        username = generate_valid_username()
        correct_password = generate_strong_password()
        wrong_password = generate_strong_password()
        
        # Ensure passwords are different
        while wrong_password == correct_password:
            wrong_password = generate_strong_password()
        
        password_hash = hash_password(correct_password)
        
        mock_user = create_mock_user(user_id, username)
        mock_password_history = create_mock_password_history(user_id, password_hash)
        mock_session = create_mock_session_for_auth(mock_user, mock_password_history)
        
        manager = SecurityManager(mock_session)
        
        # Test with wrong password - should fail
        request = AuthRequest(
            username=username,
            password=wrong_password,
            client_ip="127.0.0.1",
            user_agent="TestAgent/1.0"
        )
        
        try:
            manager.authenticate(request)
            assert False, f"Wrong password should raise AuthenticationError"
        except AuthenticationError:
            pass  # Expected behavior


def test_authentication_no_info_leakage_property():
    """
    **Feature: system-configuration, Property 5: Authentication Correctness**
    **Validates: Requirements 2.1, 2.2**
    
    Property Test: Authentication errors SHALL NOT reveal which credential
    was incorrect (no information leakage).
    """
    # Test with non-existent user
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
    
    request = AuthRequest(
        username="nonexistent",
        password="SomePass123!",
        client_ip="127.0.0.1",
        user_agent="TestAgent/1.0"
    )
    
    try:
        manager.authenticate(request)
        assert False, "Should have raised AuthenticationError"
    except AuthenticationError as e:
        nonexistent_user_error = e.message
    
    # Test with wrong password
    user_id = "test-user-id"
    username = "testuser"
    correct_password = "SecurePass123!"
    wrong_password = "WrongPass456!"
    password_hash = hash_password(correct_password)
    
    mock_user = create_mock_user(user_id, username)
    mock_password_history = create_mock_password_history(user_id, password_hash)
    mock_session = create_mock_session_for_auth(mock_user, mock_password_history)
    
    manager = SecurityManager(mock_session)
    
    request = AuthRequest(
        username=username,
        password=wrong_password,
        client_ip="127.0.0.1",
        user_agent="TestAgent/1.0"
    )
    
    try:
        manager.authenticate(request)
        assert False, "Should have raised AuthenticationError"
    except AuthenticationError as e:
        wrong_password_error = e.message
    
    # Both errors should be identical (no info leakage)
    assert nonexistent_user_error == wrong_password_error, \
        "Error messages should be identical to prevent info leakage"

