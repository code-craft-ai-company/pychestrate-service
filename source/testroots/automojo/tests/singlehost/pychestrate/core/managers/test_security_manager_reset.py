"""
.. module:: test_security_manager_reset
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for SecurityManager password reset functionality

.. moduleauthor:: Automation Mojo LLC

Tests for password reset token lifecycle.

**Feature: system-configuration**
**Property 8: Password Reset Token Lifecycle**
**Validates: Requirements 2.5, 2.6, 2.7**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid

from datetime import datetime, timedelta

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.security_manager import (
    SecurityManager,
    PasswordResetRequest,
    PasswordResetTokenError,
    PasswordValidationError,
    PasswordHistoryError,
    hash_password,
)
from automojo.pychestrate.core.defaults import utc_now


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_valid_username():
    """Generate a valid username for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest_chars = ''.join(random.choices(string.ascii_letters + string.digits + '_-', k=random.randint(5, 15)))
    return start_char + rest_chars


def generate_valid_email(username=None):
    """Generate a valid email for testing."""
    if username is None:
        username = generate_valid_username()
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 10)))
    return f"{username}@{domain}.com"


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


def create_mock_user(user_id, username, email, status="active"):
    """Create a mock user object."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', username)
    ctx.set_attribute('email', email)
    ctx.set_attribute('status', status)
    ctx.set_attribute('display_name', f"Display {username}")
    ctx.set_attribute('roles', "")
    return mock_user


def create_mock_reset_token(user_id, token, expires_at, used=False):
    """Create a mock password reset token."""
    mock_token = Mock()
    mock_token.configure(recursive=True)
    ctx = mock_token.mock_context()
    ctx.set_attribute('user_id', user_id)
    ctx.set_attribute('token', token)
    ctx.set_attribute('expires_at', expires_at)
    ctx.set_attribute('used', used)
    ctx.set_attribute('created_at', utc_now())
    return mock_token


def create_mock_session_for_reset_request(mock_user):
    """Create a mock database session for password reset request tests."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    def query_side_effect(model):
        mock_query = Mock()
        mock_query.configure(recursive=True)
        
        mock_filter1 = Mock()
        mock_filter1.configure(recursive=True)
        
        mock_filter2 = Mock()
        mock_filter2.configure(recursive=True)
        mock_filter2.mock_context().mock_method('first', return_value=mock_user)
        mock_filter2.mock_context().mock_method('update')
        
        mock_filter1.mock_context().mock_method('filter', return_value=mock_filter2)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter1)
        
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


# =============================================================================
# Property 8: Password Reset Token Lifecycle Tests
# =============================================================================

def test_password_reset_request_generates_token():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.5**
    
    Valid password reset request should generate a token.
    """
    user_id = uuid.uuid4()
    username = "testuser"
    email = "testuser@example.com"
    
    mock_user = create_mock_user(user_id, username, email)
    mock_session = create_mock_session_for_reset_request(mock_user)
    
    manager = SecurityManager(mock_session)
    
    request = PasswordResetRequest(username=username, email=email)
    token = manager.request_password_reset(request)
    
    assert token is not None
    assert len(token) > 0


def test_password_reset_request_returns_none_for_nonexistent_user():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.5**
    
    Password reset request for non-existent user should return None (no info leakage).
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter1 = Mock()
    mock_filter1.configure(recursive=True)
    mock_filter2 = Mock()
    mock_filter2.configure(recursive=True)
    mock_filter2.mock_context().mock_method('first', return_value=None)
    mock_filter1.mock_context().mock_method('filter', return_value=mock_filter2)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter1)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_session)
    
    request = PasswordResetRequest(username="nonexistent", email="nonexistent@example.com")
    token = manager.request_password_reset(request)
    
    assert token is None


def test_password_reset_request_returns_none_for_inactive_user():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.5**
    
    Password reset request for inactive user should return None.
    """
    user_id = uuid.uuid4()
    username = "inactiveuser"
    email = "inactive@example.com"
    
    mock_user = create_mock_user(user_id, username, email, status="inactive")
    mock_session = create_mock_session_for_reset_request(mock_user)
    
    manager = SecurityManager(mock_session)
    
    request = PasswordResetRequest(username=username, email=email)
    token = manager.request_password_reset(request)
    
    assert token is None


def test_valid_reset_token_can_be_validated():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.6**
    
    Valid reset token should be validated successfully.
    """
    user_id = uuid.uuid4()
    token_str = "valid_token_123"
    expires_at = utc_now() + timedelta(hours=24)
    
    mock_token = create_mock_reset_token(user_id, token_str, expires_at, used=False)
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_token)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_session)
    
    token_info = manager.validate_password_reset_token(token_str)
    
    assert token_info is not None
    assert token_info.token == token_str
    assert token_info.user_id == str(user_id)
    assert token_info.used == False


def test_used_reset_token_is_invalid():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.6**
    
    Used reset token should be invalid.
    """
    user_id = uuid.uuid4()
    token_str = "used_token_123"
    expires_at = utc_now() + timedelta(hours=24)
    
    mock_token = create_mock_reset_token(user_id, token_str, expires_at, used=True)
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_token)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_session)
    
    token_info = manager.validate_password_reset_token(token_str)
    
    assert token_info is None


def test_expired_reset_token_is_invalid():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.7**
    
    Expired reset token should be invalid.
    """
    user_id = uuid.uuid4()
    token_str = "expired_token_123"
    expires_at = utc_now() - timedelta(hours=1)  # Expired 1 hour ago
    
    mock_token = create_mock_reset_token(user_id, token_str, expires_at, used=False)
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_token)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_session)
    
    token_info = manager.validate_password_reset_token(token_str)
    
    assert token_info is None


def test_nonexistent_reset_token_is_invalid():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.6**
    
    Non-existent reset token should be invalid.
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
    
    token_info = manager.validate_password_reset_token("nonexistent_token")
    
    assert token_info is None


def test_password_reset_token_lifecycle_property():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.5, 2.6, 2.7**
    
    Property Test: For any password reset token, it SHALL be valid for password reset
    if and only if it has not expired and has not been used; after successful use,
    the token SHALL be invalidated.
    """
    for _ in range(50):
        user_id = uuid.uuid4()
        token_str = f"token_{random.randint(1000, 9999)}"
        
        # Test case 1: Valid token (not expired, not used)
        expires_at = utc_now() + timedelta(hours=random.randint(1, 48))
        mock_token = create_mock_reset_token(user_id, token_str, expires_at, used=False)
        
        mock_session = Mock()
        mock_session.configure(recursive=True)
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        mock_filter.mock_context().mock_method('first', return_value=mock_token)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        mock_session.mock_context().mock_method('query', return_value=mock_query)
        
        manager = SecurityManager(mock_session)
        token_info = manager.validate_password_reset_token(token_str)
        
        assert token_info is not None, "Valid token should be accepted"
        assert token_info.token == token_str
        
        # Test case 2: Used token should be invalid
        mock_token_used = create_mock_reset_token(user_id, token_str, expires_at, used=True)
        mock_filter.mock_context().mock_method('first', return_value=mock_token_used)
        
        token_info_used = manager.validate_password_reset_token(token_str)
        assert token_info_used is None, "Used token should be rejected"
        
        # Test case 3: Expired token should be invalid
        expired_at = utc_now() - timedelta(hours=random.randint(1, 48))
        mock_token_expired = create_mock_reset_token(user_id, token_str, expired_at, used=False)
        mock_filter.mock_context().mock_method('first', return_value=mock_token_expired)
        
        token_info_expired = manager.validate_password_reset_token(token_str)
        assert token_info_expired is None, "Expired token should be rejected"


def test_reset_password_with_invalid_token_raises_error():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.6**
    
    Reset password with invalid token should raise PasswordResetTokenError.
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
    
    try:
        manager.reset_password("invalid_token", "NewSecurePass123!")
        assert False, "Should have raised PasswordResetTokenError"
    except PasswordResetTokenError as e:
        assert "Invalid" in e.message


def test_reset_password_with_used_token_raises_error():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.6**
    
    Reset password with used token should raise PasswordResetTokenError.
    """
    user_id = uuid.uuid4()
    token_str = "used_token"
    expires_at = utc_now() + timedelta(hours=24)
    
    mock_token = create_mock_reset_token(user_id, token_str, expires_at, used=True)
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_token)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_session)
    
    try:
        manager.reset_password(token_str, "NewSecurePass123!")
        assert False, "Should have raised PasswordResetTokenError"
    except PasswordResetTokenError as e:
        assert "used" in e.message.lower()


def test_reset_password_with_expired_token_raises_error():
    """
    **Feature: system-configuration, Property 8: Password Reset Token Lifecycle**
    **Validates: Requirements 2.7**
    
    Reset password with expired token should raise PasswordResetTokenError.
    """
    user_id = uuid.uuid4()
    token_str = "expired_token"
    expires_at = utc_now() - timedelta(hours=1)  # Expired
    
    mock_token = create_mock_reset_token(user_id, token_str, expires_at, used=False)
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_token)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_session)
    
    try:
        manager.reset_password(token_str, "NewSecurePass123!")
        assert False, "Should have raised PasswordResetTokenError"
    except PasswordResetTokenError as e:
        assert "expired" in e.message.lower()
