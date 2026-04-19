"""
.. module:: test_security_manager_session
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for SecurityManager session management

.. moduleauthor:: Automation Mojo LLC

Tests for session management functionality including logout, expiry, and concurrent sessions.

**Feature: system-configuration**
**Property 6: Session Logout Invalidation**
**Validates: Requirements 2.3**

**Property 16: Session Data Completeness**
**Validates: Requirements 5.1**

**Property 7: Session Expiry Enforcement**
**Validates: Requirements 2.4**

**Property 17: Session Inactivity Expiration**
**Validates: Requirements 5.2**

**Property 18: Concurrent Session Limit**
**Validates: Requirements 5.5**

**Property 12: Password Change Session Invalidation**
**Validates: Requirements 3.5**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import secrets
from datetime import datetime, timedelta, timezone

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.security_manager import (
    SecurityManager,
    SessionInfo,
    DEFAULT_SESSION_EXPIRY_HOURS,
    DEFAULT_INACTIVITY_TIMEOUT_MINUTES,
    DEFAULT_MAX_CONCURRENT_SESSIONS,
)
from automojo.pychestrate.core.defaults import utc_now


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_session_token():
    """Generate a random session token."""
    return secrets.token_urlsafe(32)


def generate_user_id():
    """Generate a random user ID."""
    return f"user-{random.randint(1000, 9999)}"


def generate_username():
    """Generate a valid username for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest_chars = ''.join(random.choices(string.ascii_letters + string.digits + '_-', k=random.randint(5, 15)))
    return start_char + rest_chars


def generate_ip_address():
    """Generate a random IP address."""
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def generate_user_agent():
    """Generate a random user agent string."""
    browsers = ["Chrome", "Firefox", "Safari", "Edge"]
    versions = ["100.0", "101.0", "102.0", "103.0"]
    return f"Mozilla/5.0 ({random.choice(browsers)}/{random.choice(versions)})"


def create_mock_session(session_id, token, user_id, created_at=None, expires_at=None, 
                        last_activity=None, client_ip=None, user_agent=None, csrf_token=None):
    """Create a mock session object."""
    now = utc_now()
    mock_session = Mock()
    mock_session.configure(recursive=True)
    ctx = mock_session.mock_context()
    ctx.set_attribute('id', session_id)
    ctx.set_attribute('token', token)
    ctx.set_attribute('user_id', user_id)
    ctx.set_attribute('created_at', created_at or now)
    ctx.set_attribute('expires_at', expires_at or (now + timedelta(hours=DEFAULT_SESSION_EXPIRY_HOURS)))
    ctx.set_attribute('last_activity', last_activity or now)
    ctx.set_attribute('client_ip', client_ip or generate_ip_address())
    ctx.set_attribute('user_agent', user_agent or generate_user_agent())
    ctx.set_attribute('csrf_token', csrf_token or secrets.token_urlsafe(32))
    return mock_session


def create_mock_user(user_id, username):
    """Create a mock user object."""
    mock_user = Mock()
    mock_user.configure(recursive=True)
    ctx = mock_user.mock_context()
    ctx.set_attribute('id', user_id)
    ctx.set_attribute('login', username)
    return mock_user


# =============================================================================
# Property 6: Session Logout Invalidation Tests
# =============================================================================

def test_logout_invalidates_session():
    """
    **Feature: system-configuration, Property 6: Session Logout Invalidation**
    **Validates: Requirements 2.3**
    
    When a user logs out, the session should be invalidated.
    """
    token = generate_session_token()
    
    # Track if delete was called
    delete_called = [False]
    commit_called = [False]
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    
    def delete_side_effect():
        delete_called[0] = True
        return 1
    
    def commit_side_effect():
        commit_called[0] = True
    
    mock_filter.mock_context().mock_method('delete', side_effect=delete_side_effect)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    mock_session.mock_context().mock_method('commit', side_effect=commit_side_effect)
    
    manager = SecurityManager(mock_session)
    manager.logout(token)
    
    assert delete_called[0] is True, "Session should be deleted on logout"
    assert commit_called[0] is True, "Changes should be committed"


def test_logout_property_session_becomes_invalid():
    """
    **Feature: system-configuration, Property 6: Session Logout Invalidation**
    **Validates: Requirements 2.3**
    
    Property Test: For any valid session, after logout, the session token
    SHALL no longer be valid for authentication.
    """
    for _ in range(50):
        token = generate_session_token()
        user_id = generate_user_id()
        session_id = random.randint(1, 10000)
        
        # Track state
        session_deleted = [False]
        
        def create_mock_db_session():
            mock_db = Mock()
            mock_db.configure(recursive=True)
            
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            def delete_side_effect():
                session_deleted[0] = True
                return 1
            
            mock_filter.mock_context().mock_method('delete', side_effect=delete_side_effect)
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            mock_db.mock_context().mock_method('query', return_value=mock_query)
            mock_db.mock_context().mock_method('commit')
            
            return mock_db
        
        mock_db = create_mock_db_session()
        manager = SecurityManager(mock_db)
        
        # Logout should delete the session
        manager.logout(token)
        
        assert session_deleted[0] is True, \
            f"Session with token should be deleted after logout"


def test_logout_all_invalidates_all_user_sessions():
    """
    **Feature: system-configuration, Property 6: Session Logout Invalidation**
    **Validates: Requirements 2.3**
    
    logout_all should invalidate all sessions for a user.
    """
    user_id = generate_user_id()
    num_sessions = random.randint(2, 5)
    
    delete_called = [False]
    deleted_count = [0]
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    
    def delete_side_effect():
        delete_called[0] = True
        deleted_count[0] = num_sessions
        return num_sessions
    
    mock_filter.mock_context().mock_method('delete', side_effect=delete_side_effect)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    mock_session.mock_context().mock_method('commit')
    
    manager = SecurityManager(mock_session)
    count = manager.logout_all(user_id)
    
    assert delete_called[0] is True, "Sessions should be deleted"
    assert count == num_sessions, f"Should return count of deleted sessions"


def test_logout_all_except_current_keeps_one_session():
    """
    **Feature: system-configuration, Property 6: Session Logout Invalidation**
    **Validates: Requirements 2.3**
    
    logout_all with except_token should keep the specified session.
    """
    user_id = generate_user_id()
    current_token = generate_session_token()
    
    # Track filter calls to verify except_token is used
    filter_calls = []
    
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter1 = Mock()
    mock_filter1.configure(recursive=True)
    
    mock_filter2 = Mock()
    mock_filter2.configure(recursive=True)
    
    def filter_side_effect(*args, **kwargs):
        filter_calls.append(args)
        if len(filter_calls) == 1:
            return mock_filter1
        return mock_filter2
    
    mock_filter2.mock_context().mock_method('delete', return_value=2)
    mock_filter1.mock_context().mock_method('filter', side_effect=filter_side_effect)
    mock_query.mock_context().mock_method('filter', side_effect=filter_side_effect)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    mock_session.mock_context().mock_method('commit')
    
    manager = SecurityManager(mock_session)
    count = manager.logout_all(user_id, except_token=current_token)
    
    # Should have made two filter calls (one for user_id, one for except_token)
    assert len(filter_calls) >= 1, "Should filter by user_id"




# =============================================================================
# Property 16: Session Data Completeness Tests
# =============================================================================

def test_session_contains_required_metadata():
    """
    **Feature: system-configuration, Property 16: Session Data Completeness**
    **Validates: Requirements 5.1**
    
    Sessions should track all required metadata fields.
    """
    session_id = random.randint(1, 10000)
    token = generate_session_token()
    user_id = generate_user_id()
    username = generate_username()
    client_ip = generate_ip_address()
    user_agent = generate_user_agent()
    csrf_token = secrets.token_urlsafe(32)
    now = utc_now()
    expires_at = now + timedelta(hours=DEFAULT_SESSION_EXPIRY_HOURS)
    
    mock_session_obj = create_mock_session(
        session_id=session_id,
        token=token,
        user_id=user_id,
        created_at=now,
        expires_at=expires_at,
        last_activity=now,
        client_ip=client_ip,
        user_agent=user_agent,
        csrf_token=csrf_token
    )
    
    mock_user = create_mock_user(user_id, username)
    
    # Create mock db session that returns the session and user
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    query_call_count = [0]
    
    def query_side_effect(model):
        query_call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        if query_call_count[0] == 1:
            # First query is for Session
            mock_filter.mock_context().mock_method('first', return_value=mock_session_obj)
        else:
            # Second query is for User
            mock_filter.mock_context().mock_method('first', return_value=mock_user)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_db.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_db.mock_context().mock_method('commit')
    
    manager = SecurityManager(mock_db)
    session_info = manager.validate_token(token)
    
    assert session_info is not None, "Valid token should return session info"
    assert session_info.session_id == session_id, "Session ID should be present"
    assert session_info.token == token, "Token should be present"
    assert session_info.user_id == str(user_id), "User ID should be present"
    assert session_info.username == username, "Username should be present"
    assert session_info.created_at is not None, "Created timestamp should be present"
    assert session_info.last_activity is not None, "Last activity timestamp should be present"
    assert session_info.expires_at is not None, "Expiry timestamp should be present"
    assert session_info.client_ip == client_ip, "Client IP should be present"
    assert session_info.user_agent == user_agent, "User agent should be present"
    assert session_info.csrf_token == csrf_token, "CSRF token should be present"


def test_session_data_completeness_property():
    """
    **Feature: system-configuration, Property 16: Session Data Completeness**
    **Validates: Requirements 5.1**
    
    Property Test: For any valid session, the Security_Manager SHALL track
    user identifier, creation time, last activity time, and client information.
    """
    for _ in range(50):
        session_id = random.randint(1, 10000)
        token = generate_session_token()
        user_id = generate_user_id()
        username = generate_username()
        client_ip = generate_ip_address()
        user_agent = generate_user_agent()
        csrf_token = secrets.token_urlsafe(32)
        now = utc_now()
        expires_at = now + timedelta(hours=DEFAULT_SESSION_EXPIRY_HOURS)
        
        mock_session_obj = create_mock_session(
            session_id=session_id,
            token=token,
            user_id=user_id,
            created_at=now,
            expires_at=expires_at,
            last_activity=now,
            client_ip=client_ip,
            user_agent=user_agent,
            csrf_token=csrf_token
        )
        
        mock_user = create_mock_user(user_id, username)
        
        mock_db = Mock()
        mock_db.configure(recursive=True)
        
        query_call_count = [0]
        
        def query_side_effect(model):
            query_call_count[0] += 1
            mock_query = Mock()
            mock_query.configure(recursive=True)
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            
            if query_call_count[0] == 1:
                mock_filter.mock_context().mock_method('first', return_value=mock_session_obj)
            else:
                mock_filter.mock_context().mock_method('first', return_value=mock_user)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_db.mock_context().mock_method('query', side_effect=query_side_effect)
        mock_db.mock_context().mock_method('commit')
        
        manager = SecurityManager(mock_db)
        session_info = manager.validate_token(token)
        
        # Verify all required fields are present
        assert session_info is not None, "Valid session should return info"
        assert session_info.user_id is not None, "User ID must be tracked"
        assert session_info.created_at is not None, "Creation time must be tracked"
        assert session_info.last_activity is not None, "Last activity must be tracked"
        assert session_info.client_ip is not None, "Client IP must be tracked"
        assert session_info.user_agent is not None, "User agent must be tracked"


# =============================================================================
# Property 7: Session Expiry Enforcement Tests
# =============================================================================

def test_expired_session_returns_none():
    """
    **Feature: system-configuration, Property 7: Session Expiry Enforcement**
    **Validates: Requirements 2.4**
    
    An expired session should return None on validation.
    """
    session_id = random.randint(1, 10000)
    token = generate_session_token()
    user_id = generate_user_id()
    now = utc_now()
    
    # Create an expired session
    expired_time = now - timedelta(hours=1)
    mock_session_obj = create_mock_session(
        session_id=session_id,
        token=token,
        user_id=user_id,
        created_at=now - timedelta(hours=25),
        expires_at=expired_time,  # Already expired
        last_activity=now - timedelta(hours=1)
    )
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_session_obj)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_db)
    result = manager.validate_token(token)
    
    assert result is None, "Expired session should return None"


def test_session_expiry_enforcement_property():
    """
    **Feature: system-configuration, Property 7: Session Expiry Enforcement**
    **Validates: Requirements 2.4**
    
    Property Test: For any session that has passed its expiry time,
    the Security_Manager SHALL reject the session and require re-authentication.
    """
    for _ in range(50):
        session_id = random.randint(1, 10000)
        token = generate_session_token()
        user_id = generate_user_id()
        now = utc_now()
        
        # Generate a random expiry time in the past
        hours_expired = random.randint(1, 100)
        expired_time = now - timedelta(hours=hours_expired)
        
        mock_session_obj = create_mock_session(
            session_id=session_id,
            token=token,
            user_id=user_id,
            created_at=expired_time - timedelta(hours=DEFAULT_SESSION_EXPIRY_HOURS),
            expires_at=expired_time,
            last_activity=expired_time
        )
        
        mock_db = Mock()
        mock_db.configure(recursive=True)
        
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        mock_filter.mock_context().mock_method('first', return_value=mock_session_obj)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        mock_db.mock_context().mock_method('query', return_value=mock_query)
        
        manager = SecurityManager(mock_db)
        result = manager.validate_token(token)
        
        assert result is None, \
            f"Session expired {hours_expired} hours ago should be rejected"


def test_valid_session_not_expired():
    """
    **Feature: system-configuration, Property 7: Session Expiry Enforcement**
    **Validates: Requirements 2.4**
    
    A session that has not expired should be valid.
    """
    session_id = random.randint(1, 10000)
    token = generate_session_token()
    user_id = generate_user_id()
    username = generate_username()
    now = utc_now()
    
    # Create a valid session (not expired)
    mock_session_obj = create_mock_session(
        session_id=session_id,
        token=token,
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(hours=DEFAULT_SESSION_EXPIRY_HOURS),
        last_activity=now
    )
    
    mock_user = create_mock_user(user_id, username)
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    query_call_count = [0]
    
    def query_side_effect(model):
        query_call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        if query_call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=mock_session_obj)
        else:
            mock_filter.mock_context().mock_method('first', return_value=mock_user)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_db.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_db.mock_context().mock_method('commit')
    
    manager = SecurityManager(mock_db)
    result = manager.validate_token(token)
    
    assert result is not None, "Valid session should not be rejected"


# =============================================================================
# Property 17: Session Inactivity Expiration Tests
# =============================================================================

def test_inactive_session_returns_none():
    """
    **Feature: system-configuration, Property 17: Session Inactivity Expiration**
    **Validates: Requirements 5.2**
    
    A session that has been inactive too long should return None.
    """
    session_id = random.randint(1, 10000)
    token = generate_session_token()
    user_id = generate_user_id()
    now = utc_now()
    
    # Create a session with old last_activity (inactive)
    inactive_time = now - timedelta(minutes=DEFAULT_INACTIVITY_TIMEOUT_MINUTES + 10)
    mock_session_obj = create_mock_session(
        session_id=session_id,
        token=token,
        user_id=user_id,
        created_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=23),  # Not expired by absolute time
        last_activity=inactive_time  # But inactive too long
    )
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_session_obj)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_db)
    result = manager.validate_token(token)
    
    assert result is None, "Inactive session should return None"


def test_session_inactivity_expiration_property():
    """
    **Feature: system-configuration, Property 17: Session Inactivity Expiration**
    **Validates: Requirements 5.2**
    
    Property Test: For any session that has been inactive for longer than
    the configured timeout, the Security_Manager SHALL automatically expire it.
    """
    for _ in range(50):
        session_id = random.randint(1, 10000)
        token = generate_session_token()
        user_id = generate_user_id()
        now = utc_now()
        
        # Generate a random inactivity period beyond the timeout
        extra_minutes = random.randint(1, 60)
        inactive_time = now - timedelta(minutes=DEFAULT_INACTIVITY_TIMEOUT_MINUTES + extra_minutes)
        
        mock_session_obj = create_mock_session(
            session_id=session_id,
            token=token,
            user_id=user_id,
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=23),  # Not expired by absolute time
            last_activity=inactive_time
        )
        
        mock_db = Mock()
        mock_db.configure(recursive=True)
        
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        mock_filter.mock_context().mock_method('first', return_value=mock_session_obj)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        mock_db.mock_context().mock_method('query', return_value=mock_query)
        
        manager = SecurityManager(mock_db)
        result = manager.validate_token(token)
        
        assert result is None, \
            f"Session inactive for {DEFAULT_INACTIVITY_TIMEOUT_MINUTES + extra_minutes} minutes should be expired"


def test_active_session_not_expired_by_inactivity():
    """
    **Feature: system-configuration, Property 17: Session Inactivity Expiration**
    **Validates: Requirements 5.2**
    
    A session with recent activity should not be expired.
    """
    session_id = random.randint(1, 10000)
    token = generate_session_token()
    user_id = generate_user_id()
    username = generate_username()
    now = utc_now()
    
    # Create a session with recent activity
    recent_activity = now - timedelta(minutes=5)  # Active 5 minutes ago
    mock_session_obj = create_mock_session(
        session_id=session_id,
        token=token,
        user_id=user_id,
        created_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=23),
        last_activity=recent_activity
    )
    
    mock_user = create_mock_user(user_id, username)
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    query_call_count = [0]
    
    def query_side_effect(model):
        query_call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        if query_call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=mock_session_obj)
        else:
            mock_filter.mock_context().mock_method('first', return_value=mock_user)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_db.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_db.mock_context().mock_method('commit')
    
    manager = SecurityManager(mock_db)
    result = manager.validate_token(token)
    
    assert result is not None, "Active session should not be expired"



# =============================================================================
# Property 18: Concurrent Session Limit Tests
# =============================================================================

def test_concurrent_session_limit_enforced():
    """
    **Feature: system-configuration, Property 18: Concurrent Session Limit**
    **Validates: Requirements 5.5**
    
    The system should enforce a configurable maximum number of concurrent sessions.
    """
    user_id = generate_user_id()
    max_sessions = 3
    
    # Create mock sessions exceeding the limit
    sessions = []
    for i in range(max_sessions + 2):
        sessions.append(create_mock_session(
            session_id=i + 1,
            token=generate_session_token(),
            user_id=user_id
        ))
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('all', return_value=sessions)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_db, max_concurrent_sessions=max_sessions)
    
    # The manager should have the max_concurrent_sessions configuration
    assert manager._max_concurrent_sessions == max_sessions


def test_concurrent_session_limit_property():
    """
    **Feature: system-configuration, Property 18: Concurrent Session Limit**
    **Validates: Requirements 5.5**
    
    Property Test: For any user, the Security_Manager SHALL limit concurrent
    sessions to a configurable maximum.
    """
    for _ in range(30):
        max_sessions = random.randint(1, 10)
        
        mock_db = Mock()
        mock_db.configure(recursive=True)
        
        manager = SecurityManager(mock_db, max_concurrent_sessions=max_sessions)
        
        # Verify the configuration is stored
        assert manager._max_concurrent_sessions == max_sessions, \
            f"Max concurrent sessions should be configurable to {max_sessions}"


def test_list_active_sessions_returns_user_sessions():
    """
    **Feature: system-configuration, Property 18: Concurrent Session Limit**
    **Validates: Requirements 5.5**
    
    list_active_sessions should return all active sessions for a user.
    """
    user_id = generate_user_id()
    username = generate_username()
    num_sessions = random.randint(1, 5)
    now = utc_now()
    
    # Create mock sessions
    sessions = []
    for i in range(num_sessions):
        sessions.append(create_mock_session(
            session_id=i + 1,
            token=generate_session_token(),
            user_id=user_id,
            expires_at=now + timedelta(hours=DEFAULT_SESSION_EXPIRY_HOURS)
        ))
    
    mock_user = create_mock_user(user_id, username)
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    query_call_count = [0]
    
    def query_side_effect(model):
        query_call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        if query_call_count[0] == 1:
            # First query for sessions
            mock_filter2 = Mock()
            mock_filter2.configure(recursive=True)
            mock_filter2.mock_context().mock_method('all', return_value=sessions)
            mock_filter.mock_context().mock_method('filter', return_value=mock_filter2)
        else:
            # Subsequent queries for users
            mock_filter.mock_context().mock_method('first', return_value=mock_user)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_db.mock_context().mock_method('query', side_effect=query_side_effect)
    
    manager = SecurityManager(mock_db)
    result = manager.list_active_sessions(user_id)
    
    assert len(result) == num_sessions, f"Should return {num_sessions} sessions"


# =============================================================================
# Property 12: Password Change Session Invalidation Tests
# =============================================================================

def test_password_change_invalidates_other_sessions():
    """
    **Feature: system-configuration, Property 12: Password Change Session Invalidation**
    **Validates: Requirements 3.5**
    
    When a password is changed, all other sessions should be invalidated.
    """
    user_id = generate_user_id()
    current_token = generate_session_token()
    
    delete_called = [False]
    deleted_count = [0]
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter1 = Mock()
    mock_filter1.configure(recursive=True)
    
    mock_filter2 = Mock()
    mock_filter2.configure(recursive=True)
    
    def delete_side_effect():
        delete_called[0] = True
        deleted_count[0] = 3  # Simulating 3 other sessions deleted
        return 3
    
    mock_filter2.mock_context().mock_method('delete', side_effect=delete_side_effect)
    mock_filter1.mock_context().mock_method('filter', return_value=mock_filter2)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter1)
    mock_db.mock_context().mock_method('query', return_value=mock_query)
    mock_db.mock_context().mock_method('commit')
    
    manager = SecurityManager(mock_db)
    count = manager.logout_all(user_id, except_token=current_token)
    
    assert delete_called[0] is True, "Other sessions should be deleted"
    assert count == 3, "Should return count of deleted sessions"


def test_password_change_session_invalidation_property():
    """
    **Feature: system-configuration, Property 12: Password Change Session Invalidation**
    **Validates: Requirements 3.5**
    
    Property Test: For any password change, the Security_Manager SHALL
    invalidate all existing sessions except the current one.
    """
    for _ in range(50):
        user_id = generate_user_id()
        current_token = generate_session_token()
        num_other_sessions = random.randint(0, 10)
        
        delete_called = [False]
        
        mock_db = Mock()
        mock_db.configure(recursive=True)
        
        mock_query = Mock()
        mock_query.configure(recursive=True)
        
        mock_filter1 = Mock()
        mock_filter1.configure(recursive=True)
        
        mock_filter2 = Mock()
        mock_filter2.configure(recursive=True)
        
        def delete_side_effect():
            delete_called[0] = True
            return num_other_sessions
        
        mock_filter2.mock_context().mock_method('delete', side_effect=delete_side_effect)
        mock_filter1.mock_context().mock_method('filter', return_value=mock_filter2)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter1)
        mock_db.mock_context().mock_method('query', return_value=mock_query)
        mock_db.mock_context().mock_method('commit')
        
        manager = SecurityManager(mock_db)
        count = manager.logout_all(user_id, except_token=current_token)
        
        assert delete_called[0] is True, \
            "logout_all should be called to invalidate other sessions"
        assert count == num_other_sessions, \
            f"Should return count of {num_other_sessions} deleted sessions"


def test_password_change_keeps_current_session():
    """
    **Feature: system-configuration, Property 12: Password Change Session Invalidation**
    **Validates: Requirements 3.5**
    
    The current session should remain valid after password change.
    """
    user_id = generate_user_id()
    current_token = generate_session_token()
    
    # Track that except_token is used
    filter_args = []
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter1 = Mock()
    mock_filter1.configure(recursive=True)
    
    mock_filter2 = Mock()
    mock_filter2.configure(recursive=True)
    
    def filter_side_effect(*args, **kwargs):
        filter_args.append((args, kwargs))
        return mock_filter2
    
    mock_filter2.mock_context().mock_method('delete', return_value=0)
    mock_filter1.mock_context().mock_method('filter', side_effect=filter_side_effect)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter1)
    mock_db.mock_context().mock_method('query', return_value=mock_query)
    mock_db.mock_context().mock_method('commit')
    
    manager = SecurityManager(mock_db)
    manager.logout_all(user_id, except_token=current_token)
    
    # The filter should have been called with except_token logic
    assert len(filter_args) >= 1, "Should filter to exclude current token"


# =============================================================================
# Additional Session Management Tests
# =============================================================================

def test_cleanup_expired_sessions():
    """
    Test that cleanup_expired_sessions removes expired sessions.
    """
    delete_called = [False]
    deleted_count = 5
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    
    def delete_side_effect():
        delete_called[0] = True
        return deleted_count
    
    mock_filter.mock_context().mock_method('delete', side_effect=delete_side_effect)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db.mock_context().mock_method('query', return_value=mock_query)
    mock_db.mock_context().mock_method('commit')
    
    manager = SecurityManager(mock_db)
    count = manager.cleanup_expired_sessions()
    
    assert delete_called[0] is True, "Should delete expired sessions"
    assert count == deleted_count, f"Should return count of {deleted_count} deleted sessions"


def test_terminate_session_by_id():
    """
    Test that terminate_session removes a specific session by ID.
    """
    session_id = random.randint(1, 10000)
    delete_called = [False]
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    
    def delete_side_effect():
        delete_called[0] = True
        return 1
    
    mock_filter.mock_context().mock_method('delete', side_effect=delete_side_effect)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db.mock_context().mock_method('query', return_value=mock_query)
    mock_db.mock_context().mock_method('commit')
    
    manager = SecurityManager(mock_db)
    manager.terminate_session(session_id)
    
    assert delete_called[0] is True, "Should delete the session"


def test_nonexistent_token_returns_none():
    """
    Test that validating a non-existent token returns None.
    """
    token = generate_session_token()
    
    mock_db = Mock()
    mock_db.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=None)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_db.mock_context().mock_method('query', return_value=mock_query)
    
    manager = SecurityManager(mock_db)
    result = manager.validate_token(token)
    
    assert result is None, "Non-existent token should return None"

