"""
.. module:: test_security_manager_history
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for SecurityManager password history enforcement

.. moduleauthor:: Automation Mojo LLC

Tests for password history enforcement.

**Feature: system-configuration**
**Property 11: Password History Enforcement**
**Validates: Requirements 3.4**
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
    hash_password,
    verify_password,
    DEFAULT_PASSWORD_HISTORY_COUNT,
)


# =============================================================================
# Test Data Generators
# =============================================================================

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


def create_mock_password_history_entry(user_id, password_hash, created_at=None):
    """Create a mock password history entry."""
    mock_entry = Mock()
    mock_entry.configure(recursive=True)
    ctx = mock_entry.mock_context()
    ctx.set_attribute('user_id', user_id)
    ctx.set_attribute('password_hash', password_hash)
    ctx.set_attribute('created_at', created_at)
    return mock_entry


def create_mock_session_for_history_check(history_entries):
    """Create a mock database session for password history check tests."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    
    mock_order_by = Mock()
    mock_order_by.configure(recursive=True)
    
    mock_limit = Mock()
    mock_limit.configure(recursive=True)
    mock_limit.mock_context().mock_method('all', return_value=history_entries)
    
    mock_order_by.mock_context().mock_method('limit', return_value=mock_limit)
    mock_filter.mock_context().mock_method('order_by', return_value=mock_order_by)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session


# =============================================================================
# Property 11: Password History Enforcement Tests
# =============================================================================

def test_recently_used_password_is_detected():
    """
    **Feature: system-configuration, Property 11: Password History Enforcement**
    **Validates: Requirements 3.4**
    
    A password that was recently used should be detected.
    """
    user_id = "test-user-id"
    password = "SecurePass123!"
    password_hash = hash_password(password)
    
    # Create history with the password
    history_entries = [
        create_mock_password_history_entry(user_id, password_hash)
    ]
    
    mock_session = create_mock_session_for_history_check(history_entries)
    manager = SecurityManager(mock_session)
    
    result = manager.check_password_history(user_id, password)
    
    assert result is True, "Recently used password should be detected"


def test_new_password_is_not_in_history():
    """
    **Feature: system-configuration, Property 11: Password History Enforcement**
    **Validates: Requirements 3.4**
    
    A new password that was never used should not be in history.
    """
    user_id = "test-user-id"
    old_password = "OldPass123!"
    new_password = "NewPass456!"
    old_password_hash = hash_password(old_password)
    
    # Create history with old password only
    history_entries = [
        create_mock_password_history_entry(user_id, old_password_hash)
    ]
    
    mock_session = create_mock_session_for_history_check(history_entries)
    manager = SecurityManager(mock_session)
    
    result = manager.check_password_history(user_id, new_password)
    
    assert result is False, "New password should not be in history"


def test_empty_history_allows_any_password():
    """
    **Feature: system-configuration, Property 11: Password History Enforcement**
    **Validates: Requirements 3.4**
    
    When history is empty, any password should be allowed.
    """
    user_id = "test-user-id"
    password = "SecurePass123!"
    
    # Empty history
    history_entries = []
    
    mock_session = create_mock_session_for_history_check(history_entries)
    manager = SecurityManager(mock_session)
    
    result = manager.check_password_history(user_id, password)
    
    assert result is False, "Empty history should allow any password"


def test_password_history_checks_last_5_passwords():
    """
    **Feature: system-configuration, Property 11: Password History Enforcement**
    **Validates: Requirements 3.4**
    
    Password history should check the last 5 passwords.
    """
    user_id = "test-user-id"
    
    # Generate 5 different passwords
    passwords = [generate_strong_password() for _ in range(5)]
    
    # Ensure all passwords are unique
    while len(set(passwords)) != 5:
        passwords = [generate_strong_password() for _ in range(5)]
    
    password_hashes = [hash_password(p) for p in passwords]
    
    # Create history with all 5 passwords
    history_entries = [
        create_mock_password_history_entry(user_id, h) for h in password_hashes
    ]
    
    mock_session = create_mock_session_for_history_check(history_entries)
    manager = SecurityManager(mock_session)
    
    # All 5 passwords should be detected
    for password in passwords:
        result = manager.check_password_history(user_id, password)
        assert result is True, f"Password '{password}' should be in history"


def test_password_history_enforcement_property():
    """
    **Feature: system-configuration, Property 11: Password History Enforcement**
    **Validates: Requirements 3.4**
    
    Property Test: For any password change attempt, if the new password matches
    any of the user's last 5 password hashes, the change SHALL be rejected.
    """
    for _ in range(50):
        user_id = f"user-{random.randint(1000, 9999)}"
        
        # Generate N passwords for history (1 to 5)
        num_history = random.randint(1, DEFAULT_PASSWORD_HISTORY_COUNT)
        history_passwords = [generate_strong_password() for _ in range(num_history)]
        
        # Ensure all passwords are unique
        while len(set(history_passwords)) != num_history:
            history_passwords = [generate_strong_password() for _ in range(num_history)]
        
        history_hashes = [hash_password(p) for p in history_passwords]
        
        history_entries = [
            create_mock_password_history_entry(user_id, h) for h in history_hashes
        ]
        
        mock_session = create_mock_session_for_history_check(history_entries)
        manager = SecurityManager(mock_session)
        
        # Test: Reusing any password in history should be detected
        for password in history_passwords:
            result = manager.check_password_history(user_id, password)
            assert result is True, \
                f"Password in history should be detected"
        
        # Test: A new password not in history should be allowed
        new_password = generate_strong_password()
        while new_password in history_passwords:
            new_password = generate_strong_password()
        
        # Need to create a new mock session for the new password check
        mock_session = create_mock_session_for_history_check(history_entries)
        manager = SecurityManager(mock_session)
        
        result = manager.check_password_history(user_id, new_password)
        assert result is False, \
            f"New password not in history should be allowed"


def test_password_history_property_multiple_users():
    """
    **Feature: system-configuration, Property 11: Password History Enforcement**
    **Validates: Requirements 3.4**
    
    Property Test: Password history is user-specific - one user's history
    should not affect another user's password validation.
    """
    for _ in range(30):
        user1_id = f"user1-{random.randint(1000, 9999)}"
        user2_id = f"user2-{random.randint(1000, 9999)}"
        
        # User 1's password
        user1_password = generate_strong_password()
        user1_hash = hash_password(user1_password)
        
        # User 2's password (different)
        user2_password = generate_strong_password()
        while user2_password == user1_password:
            user2_password = generate_strong_password()
        user2_hash = hash_password(user2_password)
        
        # User 1's history contains user1_password
        user1_history = [create_mock_password_history_entry(user1_id, user1_hash)]
        
        # User 2's history contains user2_password
        user2_history = [create_mock_password_history_entry(user2_id, user2_hash)]
        
        # Check user 1's password against user 1's history - should be found
        mock_session1 = create_mock_session_for_history_check(user1_history)
        manager1 = SecurityManager(mock_session1)
        result1 = manager1.check_password_history(user1_id, user1_password)
        assert result1 is True, "User 1's password should be in User 1's history"
        
        # Check user 1's password against user 2's history - should NOT be found
        mock_session2 = create_mock_session_for_history_check(user2_history)
        manager2 = SecurityManager(mock_session2)
        result2 = manager2.check_password_history(user2_id, user1_password)
        assert result2 is False, "User 1's password should NOT be in User 2's history"


def test_password_history_exact_match_required():
    """
    **Feature: system-configuration, Property 11: Password History Enforcement**
    **Validates: Requirements 3.4**
    
    Password history check should require exact match, not partial match.
    """
    user_id = "test-user-id"
    password = "SecurePass123!"
    password_hash = hash_password(password)
    
    history_entries = [
        create_mock_password_history_entry(user_id, password_hash)
    ]
    
    mock_session = create_mock_session_for_history_check(history_entries)
    manager = SecurityManager(mock_session)
    
    # Exact match should be detected
    result = manager.check_password_history(user_id, password)
    assert result is True, "Exact password match should be detected"
    
    # Similar but different passwords should not match
    similar_passwords = [
        "SecurePass123",   # Missing special char
        "SecurePass123!!",  # Extra char
        "securepass123!",   # Different case
        "SecurePass124!",   # Different digit
    ]
    
    for similar in similar_passwords:
        mock_session = create_mock_session_for_history_check(history_entries)
        manager = SecurityManager(mock_session)
        result = manager.check_password_history(user_id, similar)
        assert result is False, f"Similar password '{similar}' should not match"

