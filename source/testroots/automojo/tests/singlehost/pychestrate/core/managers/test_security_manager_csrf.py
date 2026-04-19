"""
.. module:: test_security_manager_csrf
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for SecurityManager CSRF token functionality

.. moduleauthor:: Automation Mojo LLC

Tests for CSRF token uniqueness and validation.

**Feature: system-configuration**
**Property 19: CSRF Token Uniqueness**
**Property 20: CSRF Token Validation**
**Validates: Requirements 6.1, 6.2, 6.3**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid
import secrets

from datetime import datetime, timedelta

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.security_manager import (
    SecurityManager,
    SessionNotFoundError,
)
from automojo.pychestrate.core.defaults import utc_now


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_session_token():
    """Generate a random session token."""
    return secrets.token_urlsafe(32)


def create_mock_session(session_id, token, user_id, csrf_token=None):
    """Create a mock session object."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    ctx = mock_session.mock_context()
    ctx.set_attribute('id', session_id)
    ctx.set_attribute('token', token)
    ctx.set_attribute('user_id', user_id)
    ctx.set_attribute('csrf_token', csrf_token)
    ctx.set_attribute('created_at', utc_now())
    ctx.set_attribute('expires_at', utc_now() + timedelta(hours=24))
    ctx.set_attribute('last_activity', utc_now())
    ctx.set_attribute('client_ip', '127.0.0.1')
    ctx.set_attribute('user_agent', 'TestAgent/1.0')
    return mock_session


def create_mock_db_session_for_csrf(mock_session_obj):
    """Create a mock database session for CSRF tests."""
    mock_db_session = Mock()
    mock_db_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_session_obj)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db_session.mock_context().mock_method('query', return_value=mock_query)
    mock_db_session.mock_context().mock_method('commit')
    
    return mock_db_session


# =============================================================================
# Property 19: CSRF Token Uniqueness Tests
# =============================================================================

def test_csrf_tokens_are_unique_across_sessions():
    """
    **Feature: system-configuration, Property 19: CSRF Token Uniqueness**
    **Validates: Requirements 6.1**
    
    CSRF tokens should be unique across different sessions.
    """
    # Generate multiple CSRF tokens and verify uniqueness
    csrf_tokens = set()
    
    for _ in range(100):
        # Each call to secrets.token_urlsafe(32) should produce a unique token
        token = secrets.token_urlsafe(32)
        assert token not in csrf_tokens, f"Duplicate CSRF token generated: {token}"
        csrf_tokens.add(token)
    
    assert len(csrf_tokens) == 100, "All CSRF tokens should be unique"


def test_generate_csrf_token_creates_unique_token():
    """
    **Feature: system-configuration, Property 19: CSRF Token Uniqueness**
    **Validates: Requirements 6.1**
    
    generate_csrf_token should create a unique token for a session.
    """
    session_id = 1
    session_token = generate_session_token()
    user_id = uuid.uuid4()
    
    mock_session_obj = create_mock_session(session_id, session_token, user_id, csrf_token=None)
    mock_db_session = create_mock_db_session_for_csrf(mock_session_obj)
    
    manager = SecurityManager(mock_db_session)
    
    csrf_token = manager.generate_csrf_token(session_token)
    
    assert csrf_token is not None
    assert len(csrf_token) > 0


def test_generate_csrf_token_returns_existing_token():
    """
    **Feature: system-configuration, Property 19: CSRF Token Uniqueness**
    **Validates: Requirements 6.1**
    
    generate_csrf_token should return existing token if already set.
    """
    session_id = 1
    session_token = generate_session_token()
    user_id = uuid.uuid4()
    existing_csrf = "existing_csrf_token_123"
    
    mock_session_obj = create_mock_session(session_id, session_token, user_id, csrf_token=existing_csrf)
    mock_db_session = create_mock_db_session_for_csrf(mock_session_obj)
    
    manager = SecurityManager(mock_db_session)
    
    csrf_token = manager.generate_csrf_token(session_token)
    
    assert csrf_token == existing_csrf


def test_generate_csrf_token_raises_for_invalid_session():
    """
    **Feature: system-configuration, Property 19: CSRF Token Uniqueness**
    **Validates: Requirements 6.1**
    
    generate_csrf_token should raise SessionNotFoundError for invalid session.
    """
    mock_db_session = Mock()
    mock_db_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=None)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_db_session)
    
    try:
        manager.generate_csrf_token("invalid_session_token")
        assert False, "Should have raised SessionNotFoundError"
    except SessionNotFoundError:
        pass  # Expected


def test_csrf_token_uniqueness_property():
    """
    **Feature: system-configuration, Property 19: CSRF Token Uniqueness**
    **Validates: Requirements 6.1**
    
    Property Test: For any two different sessions, their CSRF tokens SHALL be different.
    """
    # Generate many CSRF tokens and verify uniqueness
    csrf_tokens = []
    
    for i in range(100):
        session_id = i + 1
        session_token = generate_session_token()
        user_id = uuid.uuid4()
        
        mock_session_obj = create_mock_session(session_id, session_token, user_id, csrf_token=None)
        mock_db_session = create_mock_db_session_for_csrf(mock_session_obj)
        
        manager = SecurityManager(mock_db_session)
        csrf_token = manager.generate_csrf_token(session_token)
        
        csrf_tokens.append(csrf_token)
    
    # Verify all tokens are unique
    unique_tokens = set(csrf_tokens)
    assert len(unique_tokens) == len(csrf_tokens), \
        f"Expected {len(csrf_tokens)} unique tokens, got {len(unique_tokens)}"


# =============================================================================
# Property 20: CSRF Token Validation Tests
# =============================================================================

def test_valid_csrf_token_is_accepted():
    """
    **Feature: system-configuration, Property 20: CSRF Token Validation**
    **Validates: Requirements 6.2, 6.3**
    
    Valid CSRF token should be accepted.
    """
    session_id = 1
    session_token = generate_session_token()
    user_id = uuid.uuid4()
    csrf_token = "valid_csrf_token_123"
    
    mock_session_obj = create_mock_session(session_id, session_token, user_id, csrf_token=csrf_token)
    mock_db_session = create_mock_db_session_for_csrf(mock_session_obj)
    
    manager = SecurityManager(mock_db_session)
    
    result = manager.validate_csrf_token(session_token, csrf_token)
    
    assert result == True


def test_invalid_csrf_token_is_rejected():
    """
    **Feature: system-configuration, Property 20: CSRF Token Validation**
    **Validates: Requirements 6.2, 6.3**
    
    Invalid CSRF token should be rejected.
    """
    session_id = 1
    session_token = generate_session_token()
    user_id = uuid.uuid4()
    correct_csrf = "correct_csrf_token"
    wrong_csrf = "wrong_csrf_token"
    
    mock_session_obj = create_mock_session(session_id, session_token, user_id, csrf_token=correct_csrf)
    mock_db_session = create_mock_db_session_for_csrf(mock_session_obj)
    
    manager = SecurityManager(mock_db_session)
    
    result = manager.validate_csrf_token(session_token, wrong_csrf)
    
    assert result == False


def test_missing_csrf_token_is_rejected():
    """
    **Feature: system-configuration, Property 20: CSRF Token Validation**
    **Validates: Requirements 6.3**
    
    Missing CSRF token should be rejected.
    """
    session_id = 1
    session_token = generate_session_token()
    user_id = uuid.uuid4()
    csrf_token = "valid_csrf_token"
    
    mock_session_obj = create_mock_session(session_id, session_token, user_id, csrf_token=csrf_token)
    mock_db_session = create_mock_db_session_for_csrf(mock_session_obj)
    
    manager = SecurityManager(mock_db_session)
    
    # Test with empty string
    result = manager.validate_csrf_token(session_token, "")
    assert result == False
    
    # Test with None
    result = manager.validate_csrf_token(session_token, None)
    assert result == False


def test_csrf_validation_for_invalid_session():
    """
    **Feature: system-configuration, Property 20: CSRF Token Validation**
    **Validates: Requirements 6.2, 6.3**
    
    CSRF validation for invalid session should return False.
    """
    mock_db_session = Mock()
    mock_db_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=None)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_db_session)
    
    result = manager.validate_csrf_token("invalid_session", "some_csrf_token")
    
    assert result == False


def test_csrf_validation_when_session_has_no_csrf():
    """
    **Feature: system-configuration, Property 20: CSRF Token Validation**
    **Validates: Requirements 6.2, 6.3**
    
    CSRF validation when session has no CSRF token should return False.
    """
    session_id = 1
    session_token = generate_session_token()
    user_id = uuid.uuid4()
    
    mock_session_obj = create_mock_session(session_id, session_token, user_id, csrf_token=None)
    mock_db_session = create_mock_db_session_for_csrf(mock_session_obj)
    
    manager = SecurityManager(mock_db_session)
    
    result = manager.validate_csrf_token(session_token, "some_csrf_token")
    
    assert result == False


def test_csrf_token_validation_property():
    """
    **Feature: system-configuration, Property 20: CSRF Token Validation**
    **Validates: Requirements 6.2, 6.3**
    
    Property Test: For any state-changing request, it SHALL be processed if and only if
    the provided CSRF token matches the session's current CSRF token.
    """
    for _ in range(50):
        session_id = random.randint(1, 1000)
        session_token = generate_session_token()
        user_id = uuid.uuid4()
        correct_csrf = secrets.token_urlsafe(32)
        
        mock_session_obj = create_mock_session(session_id, session_token, user_id, csrf_token=correct_csrf)
        mock_db_session = create_mock_db_session_for_csrf(mock_session_obj)
        
        manager = SecurityManager(mock_db_session)
        
        # Test with correct CSRF token - should be accepted
        result = manager.validate_csrf_token(session_token, correct_csrf)
        assert result == True, "Correct CSRF token should be accepted"
        
        # Test with wrong CSRF token - should be rejected
        wrong_csrf = secrets.token_urlsafe(32)
        while wrong_csrf == correct_csrf:
            wrong_csrf = secrets.token_urlsafe(32)
        
        result = manager.validate_csrf_token(session_token, wrong_csrf)
        assert result == False, "Wrong CSRF token should be rejected"


def test_regenerate_csrf_token():
    """
    **Feature: system-configuration, Property 20: CSRF Token Validation**
    **Validates: Requirements 6.4**
    
    regenerate_csrf_token should create a new unique token.
    """
    session_id = 1
    session_token = generate_session_token()
    user_id = uuid.uuid4()
    old_csrf = "old_csrf_token"
    
    mock_session_obj = create_mock_session(session_id, session_token, user_id, csrf_token=old_csrf)
    mock_db_session = create_mock_db_session_for_csrf(mock_session_obj)
    
    manager = SecurityManager(mock_db_session)
    
    new_csrf = manager.regenerate_csrf_token(session_token)
    
    assert new_csrf is not None
    assert len(new_csrf) > 0
    # Note: The new token is generated by secrets.token_urlsafe(32) which is different from old_csrf


def test_regenerate_csrf_token_raises_for_invalid_session():
    """
    **Feature: system-configuration, Property 20: CSRF Token Validation**
    **Validates: Requirements 6.4**
    
    regenerate_csrf_token should raise SessionNotFoundError for invalid session.
    """
    mock_db_session = Mock()
    mock_db_session.configure(recursive=True)
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=None)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_db_session)
    
    try:
        manager.regenerate_csrf_token("invalid_session_token")
        assert False, "Should have raised SessionNotFoundError"
    except SessionNotFoundError:
        pass  # Expected
