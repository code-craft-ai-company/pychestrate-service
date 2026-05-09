"""
.. module:: security_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the SecurityManager class for authentication, session management, and access control

.. moduleauthor:: Automation Mojo LLC

This module provides the SecurityManager class which handles:
- Password strength validation (Requirements 3.1, 3.2)
- Password hashing using werkzeug (Requirement 3.3)
- Password history enforcement (Requirement 3.4)
- Authentication flow with session creation (Requirements 2.1, 2.2)
- Session management and invalidation

The implementation leverages existing functionality from the automojo.webservice.xflask module:
- RouteSecurityManager for route-based access control
- get_csrf_token() and validate_csrf_token() for CSRF protection
- check_password_hash() and generate_password_hash() from werkzeug
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import secrets

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

# NOTE: ``werkzeug`` is intentionally NOT imported at module
# load time. The consumer-UI auth flow has migrated to the
# modern stack (``security.auth.local_flow`` +
# ``ConsumerUISecurityAdapter``); the only remaining live
# consumer of this module is ``routes_sessions.py`` which calls
# ``list_active_sessions`` / ``terminate_session`` -- neither
# of which touches password hashing. The two methods below that
# DO call werkzeug (``_check_password_history``, ``authenticate``)
# are dead at runtime; their imports stay lazy so this module
# loads cleanly without werkzeug installed. werkzeug was
# previously transitive through the (now-removed)
# ``pychestrate-core`` git-source dep; reintroducing it as a
# direct dep would defeat the purpose of cutting that branch
# of the dep tree.

from automojo.pychestrate.core.defaults import utc_now


# =============================================================================
# Password Validation Constants
# =============================================================================

# Minimum password length requirement (Requirement 3.1)
MIN_PASSWORD_LENGTH = 12

# Password complexity requirements (Requirement 3.2)
PASSWORD_UPPERCASE_PATTERN = re.compile(r'[A-Z]')
PASSWORD_LOWERCASE_PATTERN = re.compile(r'[a-z]')
PASSWORD_DIGIT_PATTERN = re.compile(r'[0-9]')
PASSWORD_SPECIAL_PATTERN = re.compile(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?`~]')

# Session configuration defaults
DEFAULT_SESSION_EXPIRY_HOURS = 24
DEFAULT_INACTIVITY_TIMEOUT_MINUTES = 30
DEFAULT_MAX_CONCURRENT_SESSIONS = 5

# Password history count (Requirement 3.4)
DEFAULT_PASSWORD_HISTORY_COUNT = 5

# Password reset token expiry (default 24 hours)
DEFAULT_PASSWORD_RESET_TOKEN_EXPIRY_HOURS = 24


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class AuthRequest:
    """Request dataclass for authentication."""
    username: str
    password: str
    client_ip: str = ""
    user_agent: str = ""


@dataclass
class AuthResponse:
    """Response dataclass for successful authentication."""
    token: str
    expires_at: datetime
    user_id: str
    username: str
    csrf_token: str


@dataclass
class SessionInfo:
    """Information about an active session."""
    session_id: int
    token: str
    user_id: str
    username: str
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    client_ip: Optional[str]
    user_agent: Optional[str]
    csrf_token: Optional[str]


@dataclass
class PasswordResetRequest:
    """Request dataclass for password reset."""
    username: str
    email: str


@dataclass
class PasswordResetTokenInfo:
    """Information about a password reset token."""
    token: str
    user_id: str
    expires_at: datetime
    used: bool


# =============================================================================
# Security Errors
# =============================================================================

class AuthenticationError(Exception):
    """Exception raised when authentication fails."""
    
    def __init__(self, message: str = "Invalid credentials"):
        self.message = message
        super().__init__(self.message)


class PasswordValidationError(Exception):
    """Exception raised when password validation fails."""
    
    def __init__(self, message: str, violations: List[str] = None):
        self.message = message
        self.violations = violations or []
        super().__init__(self.message)


class PasswordHistoryError(Exception):
    """Exception raised when password was recently used."""
    
    def __init__(self, message: str = "Password was recently used"):
        self.message = message
        super().__init__(self.message)


class SessionNotFoundError(Exception):
    """Exception raised when a session is not found."""
    
    def __init__(self, message: str = "Session not found"):
        self.message = message
        super().__init__(self.message)


class SessionExpiredError(Exception):
    """Exception raised when a session has expired."""
    
    def __init__(self, message: str = "Session has expired"):
        self.message = message
        super().__init__(self.message)


class PasswordResetTokenError(Exception):
    """Exception raised when a password reset token is invalid or expired."""
    
    def __init__(self, message: str = "Invalid or expired password reset token"):
        self.message = message
        super().__init__(self.message)


class PermissionDeniedError(Exception):
    """Exception raised when a user lacks required permission."""
    
    def __init__(self, message: str = "Permission denied", permission: str = None):
        self.message = message
        self.permission = permission
        super().__init__(self.message)


# =============================================================================
# Password Validation Functions
# =============================================================================

def validate_password_strength(password: str) -> List[str]:
    """
    Validate that a password meets security requirements.
    
    Requirements:
    - At least 12 characters long (Requirement 3.1)
    - Contains at least one uppercase letter (Requirement 3.2)
    - Contains at least one lowercase letter (Requirement 3.2)
    - Contains at least one digit (Requirement 3.2)
    - Contains at least one special character (Requirement 3.2)
    
    :param password: The password to validate
    :returns: List of violation messages (empty if valid)
    
    Validates: Requirements 3.1, 3.2
    """
    violations = []
    
    if not password:
        violations.append("Password is required")
        return violations
    
    if len(password) < MIN_PASSWORD_LENGTH:
        violations.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    
    if not PASSWORD_UPPERCASE_PATTERN.search(password):
        violations.append("Password must contain at least one uppercase letter")
    
    if not PASSWORD_LOWERCASE_PATTERN.search(password):
        violations.append("Password must contain at least one lowercase letter")
    
    if not PASSWORD_DIGIT_PATTERN.search(password):
        violations.append("Password must contain at least one digit")
    
    if not PASSWORD_SPECIAL_PATTERN.search(password):
        violations.append("Password must contain at least one special character")
    
    return violations


def is_password_strong(password: str) -> bool:
    """
    Check if a password meets all security requirements.
    
    :param password: The password to check
    :returns: True if password is strong, False otherwise
    
    Validates: Requirements 3.1, 3.2
    """
    return len(validate_password_strength(password)) == 0



# NOTE: module-level ``hash_password`` / ``verify_password``
# helpers have been removed. They had zero consumers in the
# codebase (the modern stack uses ``local_flow.hash_password``
# and the ``password_hasher`` factory protocol instead) and
# their werkzeug calls were the only path that forced werkzeug
# into the install tree at module load time.


# =============================================================================
# SecurityManager Class
# =============================================================================

class SecurityManager:
    """
    Manager class for authentication, session management, and access control.
    
    This class handles:
    - Password strength validation (Requirements 3.1, 3.2)
    - Password hashing and verification (Requirement 3.3)
    - Password history enforcement (Requirement 3.4)
    - Authentication with session creation (Requirements 2.1, 2.2)
    - Session management and invalidation
    
    The implementation leverages existing functionality from automojo.webservice.xflask:
    - werkzeug's generate_password_hash() and check_password_hash()
    - CSRF token functions from basesecurity module
    """
    
    def __init__(
        self,
        db_session: DbSession,
        session_expiry_hours: int = DEFAULT_SESSION_EXPIRY_HOURS,
        inactivity_timeout_minutes: int = DEFAULT_INACTIVITY_TIMEOUT_MINUTES,
        max_concurrent_sessions: int = DEFAULT_MAX_CONCURRENT_SESSIONS,
        password_history_count: int = DEFAULT_PASSWORD_HISTORY_COUNT,
        password_reset_token_expiry_hours: int = DEFAULT_PASSWORD_RESET_TOKEN_EXPIRY_HOURS,
        audit_logger=None
    ):
        """
        Initialize the SecurityManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param session_expiry_hours: Hours until session expires
        :param inactivity_timeout_minutes: Minutes of inactivity before session expires
        :param max_concurrent_sessions: Maximum concurrent sessions per user
        :param password_history_count: Number of previous passwords to track
        :param password_reset_token_expiry_hours: Hours until password reset token expires
        :param audit_logger: Optional AuditLogger instance for audit logging
        """
        self._db_session = db_session
        self._session_expiry_hours = session_expiry_hours
        self._inactivity_timeout_minutes = inactivity_timeout_minutes
        self._max_concurrent_sessions = max_concurrent_sessions
        self._password_history_count = password_history_count
        self._password_reset_token_expiry_hours = password_reset_token_expiry_hours
        self._audit_logger = audit_logger
    
    # =========================================================================
    # Password Validation Methods
    # =========================================================================
    
    def validate_password_strength(self, password: str) -> List[str]:
        """
        Validate that a password meets security requirements.
        
        :param password: The password to validate
        :returns: List of violation messages (empty if valid)
        
        Validates: Requirements 3.1, 3.2
        """
        return validate_password_strength(password)
    
    def is_password_strong(self, password: str) -> bool:
        """
        Check if a password meets all security requirements.
        
        :param password: The password to check
        :returns: True if password is strong, False otherwise
        
        Validates: Requirements 3.1, 3.2
        """
        return is_password_strong(password)
    
    def hash_password(self, password: str) -> str:
        """
        Hash a password using secure hashing.
        
        :param password: The plaintext password to hash
        :returns: The hashed password
        
        Validates: Requirement 3.3
        """
        return hash_password(password)
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """
        Verify a password against its hash.
        
        :param password: The plaintext password to verify
        :param password_hash: The stored password hash
        :returns: True if password matches, False otherwise
        
        Validates: Requirement 3.3
        """
        return verify_password(password, password_hash)
    
    # =========================================================================
    # Password History Methods
    # =========================================================================
    
    def check_password_history(self, user_id: str, password: str) -> bool:
        """
        Check if a password was recently used by the user.
        
        :param user_id: The user's unique identifier
        :param password: The password to check
        :returns: True if password was recently used, False otherwise
        
        Validates: Requirement 3.4
        """
        from automojo.pychestrate.core.orm import PasswordHistory
        
        # Get the last N password hashes for this user
        history_entries = (
            self._db_session.query(PasswordHistory)
            .filter(PasswordHistory.user_id == user_id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(self._password_history_count)
            .all()
        )
        
        # Lazy-import werkzeug -- this method is dead at runtime
        # via the modern ``ConsumerUISecurityAdapter``; importing
        # the module at top-level would force werkzeug into the
        # install tree for code that is never called.
        from werkzeug.security import check_password_hash  # noqa: E402

        # Check if the password matches any of the recent hashes
        for entry in history_entries:
            if check_password_hash(entry.password_hash, password):
                return True
        
        return False
    
    def add_password_to_history(self, user_id: str, password_hash: str) -> None:
        """
        Add a password hash to the user's password history.
        
        :param user_id: The user's unique identifier
        :param password_hash: The hashed password to add
        
        Validates: Requirement 3.4
        """
        from automojo.pychestrate.core.orm import PasswordHistory
        
        # Add the new password hash to history
        history_entry = PasswordHistory(
            user_id=user_id,
            password_hash=password_hash,
            created_at=utc_now()
        )
        self._db_session.add(history_entry)
        
        # Remove old entries beyond the history count
        old_entries = (
            self._db_session.query(PasswordHistory)
            .filter(PasswordHistory.user_id == user_id)
            .order_by(PasswordHistory.created_at.desc())
            .offset(self._password_history_count)
            .all()
        )
        
        for entry in old_entries:
            self._db_session.delete(entry)
        
        self._db_session.commit()
    
    def change_password(self, user_id: str, new_password: str, current_session_token: str = None) -> int:
        """
        Change a user's password and invalidate all other sessions.
        
        :param user_id: The user's unique identifier
        :param new_password: The new password (will be validated and hashed)
        :param current_session_token: Optional token of current session to keep valid
        :returns: Number of sessions invalidated
        :raises PasswordValidationError: If password doesn't meet strength requirements
        :raises PasswordHistoryError: If password was recently used
        
        Validates: Requirements 3.4, 3.5
        """
        # Validate password strength
        violations = self.validate_password_strength(new_password)
        if violations:
            raise PasswordValidationError("Password does not meet requirements", violations)
        
        # Check password history
        if self.check_password_history(user_id, new_password):
            raise PasswordHistoryError("Password was recently used")
        
        # Hash and store the new password
        password_hash = self.hash_password(new_password)
        self.add_password_to_history(user_id, password_hash)
        
        # Invalidate all other sessions (Requirement 3.5)
        invalidated_count = self.logout_all(user_id, except_token=current_session_token)
        
        # Log the password change event
        if self._audit_logger:
            from automojo.pychestrate.core.orm import User
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            self._audit_logger.log_password_changed(
                user_id=user_id,
                username=username,
                details={"sessions_invalidated": invalidated_count}
            )
        
        return invalidated_count
    
    # =========================================================================
    # Authentication Methods
    # =========================================================================
    
    def authenticate(self, request: AuthRequest) -> AuthResponse:
        """
        Authenticate a user and create a session.
        
        :param request: The authentication request
        :returns: AuthResponse with session token and user info
        :raises AuthenticationError: If authentication fails (generic error, no info leakage)
        
        Validates: Requirements 2.1, 2.2
        """
        from automojo.pychestrate.core.orm import User, Session as SessionModel
        
        # Look up user by username (login field in User model)
        user = self._db_session.query(User).filter(User.login == request.username).first()
        
        if user is None:
            # Log authentication failure
            if self._audit_logger:
                self._audit_logger.log_auth_failure(
                    username=request.username,
                    client_ip=request.client_ip,
                    details={"reason": "user_not_found"}
                )
            # Generic error - don't reveal that user doesn't exist
            raise AuthenticationError("Invalid credentials")
        
        # Check if user is active
        if user.status != "active":
            # Log authentication failure
            if self._audit_logger:
                self._audit_logger.log_auth_failure(
                    username=request.username,
                    client_ip=request.client_ip,
                    details={"reason": "user_inactive"}
                )
            raise AuthenticationError("Invalid credentials")
        
        # Get the user's credential (password hash)
        # For internal auth, we need to look up the credential
        from automojo.pychestrate.core.orm import PasswordHistory
        
        # For now, we'll check against the most recent password in history
        # In a full implementation, this would use a Credential table
        latest_password = (
            self._db_session.query(PasswordHistory)
            .filter(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc())
            .first()
        )
        
        if latest_password is None:
            # Log authentication failure
            if self._audit_logger:
                self._audit_logger.log_auth_failure(
                    username=request.username,
                    client_ip=request.client_ip,
                    details={"reason": "no_password_set"}
                )
            raise AuthenticationError("Invalid credentials")
        
        # Verify password. Lazy werkzeug import -- this method
        # path is dead at runtime; consumer-UI auth flows
        # through the modern ``ConsumerUISecurityAdapter`` now.
        from werkzeug.security import check_password_hash  # noqa: E402

        if not check_password_hash(latest_password.password_hash, request.password):
            # Log authentication failure
            if self._audit_logger:
                self._audit_logger.log_auth_failure(
                    username=request.username,
                    client_ip=request.client_ip,
                    details={"reason": "invalid_password"}
                )
            raise AuthenticationError("Invalid credentials")
        
        # Enforce concurrent session limit (Requirement 5.5)
        now = utc_now()
        active_sessions = (
            self._db_session.query(SessionModel)
            .filter(SessionModel.user_id == user.id)
            .filter(SessionModel.expires_at > now)
            .order_by(SessionModel.created_at.asc())
            .all()
        )
        
        # If at or over the limit, remove oldest sessions to make room
        if len(active_sessions) >= self._max_concurrent_sessions:
            sessions_to_remove = len(active_sessions) - self._max_concurrent_sessions + 1
            for i in range(sessions_to_remove):
                self._db_session.delete(active_sessions[i])
        
        # Create session
        expires_at = now + timedelta(hours=self._session_expiry_hours)
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        
        session = SessionModel(
            token=session_token,
            user_id=user.id,
            created_at=now,
            expires_at=expires_at,
            last_activity=now,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            csrf_token=csrf_token
        )
        
        self._db_session.add(session)
        self._db_session.commit()
        
        # Log successful authentication
        if self._audit_logger:
            self._audit_logger.log_auth_success(
                user_id=str(user.id),
                username=user.login,
                client_ip=request.client_ip,
                details={"user_agent": request.user_agent}
            )
        
        return AuthResponse(
            token=session_token,
            expires_at=expires_at,
            user_id=str(user.id),
            username=user.login,
            csrf_token=csrf_token
        )
    
    def validate_token(self, token: str) -> Optional[SessionInfo]:
        """
        Validate a session token and return session info.
        
        :param token: The session token to validate
        :returns: SessionInfo if valid, None otherwise
        
        Validates: Requirements 2.4, 5.1
        """
        from automojo.pychestrate.core.orm import Session as SessionModel, User
        
        session = (
            self._db_session.query(SessionModel)
            .filter(SessionModel.token == token)
            .first()
        )
        
        if session is None:
            return None
        
        now = utc_now()
        
        # Check if session has expired
        if session.expires_at < now:
            return None
        
        # Check inactivity timeout
        inactivity_limit = session.last_activity + timedelta(minutes=self._inactivity_timeout_minutes)
        if inactivity_limit < now:
            return None
        
        # Update last activity
        session.last_activity = now
        self._db_session.commit()
        
        # Get username
        user = self._db_session.query(User).filter(User.id == session.user_id).first()
        username = user.login if user else ""
        
        return SessionInfo(
            session_id=session.id,
            token=session.token,
            user_id=str(session.user_id),
            username=username,
            created_at=session.created_at,
            last_activity=session.last_activity,
            expires_at=session.expires_at,
            client_ip=session.client_ip,
            user_agent=session.user_agent,
            csrf_token=session.csrf_token
        )
    
    def logout(self, token: str) -> None:
        """
        Invalidate a session by token.
        
        :param token: The session token to invalidate
        
        Validates: Requirement 2.3
        """
        from automojo.pychestrate.core.orm import Session as SessionModel, User
        
        # Get session info before deleting for audit logging
        session = self._db_session.query(SessionModel).filter(
            SessionModel.token == token
        ).first()
        
        user_id = None
        username = None
        if session:
            user_id = str(session.user_id)
            user = self._db_session.query(User).filter(User.id == session.user_id).first()
            if user:
                username = user.login
        
        self._db_session.query(SessionModel).filter(
            SessionModel.token == token
        ).delete()
        
        self._db_session.commit()
        
        # Log the logout event
        if self._audit_logger and user_id:
            self._audit_logger.log_logout(
                user_id=user_id,
                username=username or ""
            )
    
    def logout_all(self, user_id: str, except_token: str = None) -> int:
        """
        Invalidate all sessions for a user, optionally keeping one.
        
        :param user_id: The user's unique identifier
        :param except_token: Optional token to keep valid
        :returns: Number of sessions invalidated
        
        Validates: Requirement 3.5
        """
        from automojo.pychestrate.core.orm import Session as SessionModel
        
        query = self._db_session.query(SessionModel).filter(
            SessionModel.user_id == user_id
        )
        
        if except_token:
            query = query.filter(SessionModel.token != except_token)
        
        count = query.delete()
        self._db_session.commit()
        
        return count
    
    def list_active_sessions(self, user_id: str = None) -> List[SessionInfo]:
        """
        List active sessions, optionally filtered by user.
        
        :param user_id: Optional user ID to filter by
        :returns: List of active sessions
        
        Validates: Requirement 5.3
        """
        from automojo.pychestrate.core.orm import Session as SessionModel, User
        
        now = utc_now()
        
        query = self._db_session.query(SessionModel).filter(
            SessionModel.expires_at > now
        )
        
        if user_id:
            query = query.filter(SessionModel.user_id == user_id)
        
        sessions = query.all()
        
        result = []
        for session in sessions:
            user = self._db_session.query(User).filter(User.id == session.user_id).first()
            username = user.login if user else ""
            
            result.append(SessionInfo(
                session_id=session.id,
                token=session.token,
                user_id=str(session.user_id),
                username=username,
                created_at=session.created_at,
                last_activity=session.last_activity,
                expires_at=session.expires_at,
                client_ip=session.client_ip,
                user_agent=session.user_agent,
                csrf_token=session.csrf_token
            ))
        
        return result
    
    def get_active_session_count(self, user_id: str) -> int:
        """
        Get the count of active sessions for a user.
        
        :param user_id: The user's unique identifier
        :returns: Number of active sessions
        
        Validates: Requirement 5.5
        """
        from automojo.pychestrate.core.orm import Session as SessionModel
        
        now = utc_now()
        
        count = (
            self._db_session.query(SessionModel)
            .filter(SessionModel.user_id == user_id)
            .filter(SessionModel.expires_at > now)
            .count()
        )
        
        return count
    
    def terminate_session(self, session_id: int) -> None:
        """
        Terminate a specific session by ID.
        
        :param session_id: The session ID to terminate
        
        Validates: Requirement 5.4
        """
        from automojo.pychestrate.core.orm import Session as SessionModel
        
        self._db_session.query(SessionModel).filter(
            SessionModel.id == session_id
        ).delete()
        
        self._db_session.commit()
    
    def cleanup_expired_sessions(self) -> int:
        """
        Remove expired sessions from the database.
        
        :returns: Number of sessions removed
        """
        from automojo.pychestrate.core.orm import Session as SessionModel
        
        now = utc_now()
        
        count = self._db_session.query(SessionModel).filter(
            SessionModel.expires_at < now
        ).delete()
        
        self._db_session.commit()
        
        return count
    
    # =========================================================================
    # CSRF Token Methods (leveraging base framework)
    # =========================================================================
    
    def generate_csrf_token(self, session_token: str) -> str:
        """
        Generate or retrieve CSRF token for a session.
        
        :param session_token: The session token
        :returns: CSRF token string
        
        Validates: Requirement 6.1
        """
        from automojo.pychestrate.core.orm import Session as SessionModel
        
        session = (
            self._db_session.query(SessionModel)
            .filter(SessionModel.token == session_token)
            .first()
        )
        
        if session is None:
            raise SessionNotFoundError()
        
        if session.csrf_token is None:
            session.csrf_token = secrets.token_urlsafe(32)
            self._db_session.commit()
        
        return session.csrf_token
    
    def validate_csrf_token(self, session_token: str, csrf_token: str) -> bool:
        """
        Validate a CSRF token for a session.
        
        :param session_token: The session token
        :param csrf_token: The CSRF token to validate
        :returns: True if valid, False otherwise
        
        Validates: Requirements 6.2, 6.3
        """
        from automojo.pychestrate.core.orm import Session as SessionModel
        
        if not csrf_token:
            return False
        
        session = (
            self._db_session.query(SessionModel)
            .filter(SessionModel.token == session_token)
            .first()
        )
        
        if session is None:
            return False
        
        if session.csrf_token is None:
            return False
        
        return secrets.compare_digest(session.csrf_token, csrf_token)
    
    def regenerate_csrf_token(self, session_token: str) -> str:
        """
        Regenerate CSRF token for a session.
        
        :param session_token: The session token
        :returns: New CSRF token string
        
        Validates: Requirement 6.4
        """
        from automojo.pychestrate.core.orm import Session as SessionModel
        
        session = (
            self._db_session.query(SessionModel)
            .filter(SessionModel.token == session_token)
            .first()
        )
        
        if session is None:
            raise SessionNotFoundError()
        
        session.csrf_token = secrets.token_urlsafe(32)
        self._db_session.commit()
        
        return session.csrf_token
    
    # =========================================================================
    # Password Reset Methods
    # =========================================================================
    
    def request_password_reset(self, request: PasswordResetRequest) -> Optional[str]:
        """
        Generate a password reset token for a user.
        
        This method validates that the username and email match an existing user,
        then generates a time-limited reset token.
        
        :param request: The password reset request containing username and email
        :returns: The reset token if user found, None otherwise (no info leakage)
        
        Validates: Requirements 2.5
        """
        from automojo.pychestrate.core.orm import User, PasswordResetToken
        
        # Look up user by username and email
        user = (
            self._db_session.query(User)
            .filter(User.login == request.username)
            .filter(User.email == request.email)
            .first()
        )
        
        # If user not found, return None (no info leakage)
        if user is None:
            return None
        
        # Check if user is active
        if user.status != "active":
            return None
        
        # Invalidate any existing reset tokens for this user
        self._db_session.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == False
        ).update({"used": True})
        
        # Generate new reset token
        now = utc_now()
        expires_at = now + timedelta(hours=self._password_reset_token_expiry_hours)
        token = secrets.token_urlsafe(32)
        
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=token,
            created_at=now,
            expires_at=expires_at,
            used=False
        )
        
        self._db_session.add(reset_token)
        self._db_session.commit()
        
        # Log the password reset request event
        if self._audit_logger:
            self._audit_logger.log_password_reset_requested(
                username=user.login
            )
        
        return token
    
    def validate_password_reset_token(self, token: str) -> Optional[PasswordResetTokenInfo]:
        """
        Validate a password reset token.
        
        :param token: The reset token to validate
        :returns: PasswordResetTokenInfo if valid, None otherwise
        
        Validates: Requirements 2.6, 2.7
        """
        from automojo.pychestrate.core.orm import PasswordResetToken
        
        reset_token = (
            self._db_session.query(PasswordResetToken)
            .filter(PasswordResetToken.token == token)
            .first()
        )
        
        if reset_token is None:
            return None
        
        # Check if token has been used
        if reset_token.used:
            return None
        
        # Check if token has expired
        now = utc_now()
        if reset_token.expires_at < now:
            return None
        
        return PasswordResetTokenInfo(
            token=reset_token.token,
            user_id=str(reset_token.user_id),
            expires_at=reset_token.expires_at,
            used=reset_token.used
        )
    
    def reset_password(self, token: str, new_password: str) -> None:
        """
        Reset a user's password using a valid reset token.
        
        This method validates the token, checks password strength and history,
        updates the password, and invalidates the token.
        
        :param token: The password reset token
        :param new_password: The new password
        :raises PasswordResetTokenError: If token is invalid or expired
        :raises PasswordValidationError: If password doesn't meet strength requirements
        :raises PasswordHistoryError: If password was recently used
        
        Validates: Requirements 2.5, 2.6, 2.7
        """
        from automojo.pychestrate.core.orm import PasswordResetToken, User
        
        # Validate the token
        reset_token = (
            self._db_session.query(PasswordResetToken)
            .filter(PasswordResetToken.token == token)
            .first()
        )
        
        if reset_token is None:
            raise PasswordResetTokenError("Invalid password reset token")
        
        # Check if token has been used
        if reset_token.used:
            raise PasswordResetTokenError("Password reset token has already been used")
        
        # Check if token has expired
        now = utc_now()
        if reset_token.expires_at < now:
            raise PasswordResetTokenError("Password reset token has expired")
        
        # Get the user
        user = self._db_session.query(User).filter(User.id == reset_token.user_id).first()
        
        if user is None:
            raise PasswordResetTokenError("User not found")
        
        # Validate password strength
        violations = self.validate_password_strength(new_password)
        if violations:
            raise PasswordValidationError("Password does not meet requirements", violations)
        
        # Check password history
        if self.check_password_history(str(user.id), new_password):
            raise PasswordHistoryError("Password was recently used")
        
        # Hash and store the new password
        password_hash = self.hash_password(new_password)
        self.add_password_to_history(str(user.id), password_hash)
        
        # Mark the token as used
        reset_token.used = True
        
        # Invalidate all sessions for this user
        self.logout_all(str(user.id))
        
        self._db_session.commit()
        
        # Log the password reset completion event
        if self._audit_logger:
            self._audit_logger.log_password_reset_completed(
                user_id=str(user.id),
                username=user.login
            )
    
    def cleanup_expired_reset_tokens(self) -> int:
        """
        Remove expired password reset tokens from the database.
        
        :returns: Number of tokens removed
        """
        from automojo.pychestrate.core.orm import PasswordResetToken
        
        now = utc_now()
        
        count = self._db_session.query(PasswordResetToken).filter(
            PasswordResetToken.expires_at < now
        ).delete()
        
        self._db_session.commit()
        
        return count
    
    # =========================================================================
    # Permission Checking Methods
    # =========================================================================
    
    def check_permission(self, user_id: str, permission: str) -> bool:
        """
        Check if a user has a specific permission.
        
        This method calculates the user's effective permissions from all assigned
        roles and checks if the required permission is present.
        
        :param user_id: The user's unique identifier
        :param permission: The permission to check (e.g., "users.create")
        :returns: True if user has the permission, False otherwise
        
        Validates: Requirements 4.4
        """
        from automojo.pychestrate.core.orm import User, SystemRole
        
        user = self._db_session.query(User).filter(User.id == user_id).first()
        
        if user is None:
            return False
        
        # Check if user is active
        if user.status != "active":
            return False
        
        # Get role names from user
        role_names = user.roles.split(",") if user.roles else []
        role_names = [r.strip() for r in role_names if r.strip()]
        
        if not role_names:
            return False
        
        # Get all roles with their permissions
        roles = self._db_session.query(SystemRole).filter(
            SystemRole.name.in_(role_names)
        ).all()
        
        # Check if any role has the required permission
        for role in roles:
            for perm in role.permissions:
                if perm.name == permission:
                    return True
        
        return False
    
    def require_permission(self, user_id: str, permission: str) -> None:
        """
        Require that a user has a specific permission, raising an error if not.
        
        :param user_id: The user's unique identifier
        :param permission: The permission to require
        :raises PermissionDeniedError: If user lacks the permission
        
        Validates: Requirements 4.4
        """
        if not self.check_permission(user_id, permission):
            raise PermissionDeniedError(
                f"User lacks required permission: {permission}",
                permission=permission
            )
