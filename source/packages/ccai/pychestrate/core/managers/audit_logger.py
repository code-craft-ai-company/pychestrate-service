"""
.. module:: audit_logger
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the AuditLogger class for recording security-relevant audit events

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import AuditEventType, AuditLog


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class AuditLogEntry:
    """Dataclass representing an audit log entry."""
    id: int
    event_type: Any  # Can be AuditEventType enum or string for custom event types
    timestamp: datetime
    user_id: Optional[str]
    username: Optional[str]
    target_user_id: Optional[str]
    target_username: Optional[str]
    client_ip: Optional[str]
    details: Optional[Dict[str, Any]]


@dataclass
class AuditLogQuery:
    """Dataclass for querying audit logs with filters."""
    event_types: Optional[List[AuditEventType]] = None
    user_id: Optional[str] = None
    target_user_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    offset: int = 0
    limit: int = 50


@dataclass
class AuditLogListResponse:
    """Response dataclass for paginated audit log list."""
    entries: List[AuditLogEntry]
    total: int
    offset: int
    limit: int


# =============================================================================
# Constants
# =============================================================================

DEFAULT_RETENTION_DAYS = 90


# =============================================================================
# AuditLogger Class
# =============================================================================

class AuditLogger:
    """
    Manager class for recording and querying security-relevant audit events.
    
    This class handles all audit logging operations including:
    - Logging authentication events (success/failure)
    - Logging permission and role changes
    - Logging global variable modifications
    - Logging secret operations
    - Querying audit logs with filtering and pagination
    - Cleaning up old audit logs based on retention policy
    
    Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5
    """
    
    def __init__(self, db_session: DbSession):
        """
        Initialize the AuditLogger with a database session.
        
        :param db_session: SQLAlchemy database session
        """
        self._db_session = db_session
    
    # =========================================================================
    # Event Logging Methods
    # =========================================================================
    
    def log_event(
        self,
        event_type,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        target_user_id: Optional[str] = None,
        target_username: Optional[str] = None,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log an audit event.
        
        :param event_type: The type of audit event (AuditEventType enum or string)
        :param user_id: ID of the user who performed the action
        :param username: Username of the user who performed the action
        :param target_user_id: ID of the user affected by the action (if applicable)
        :param target_username: Username of the user affected by the action (if applicable)
        :param client_ip: IP address of the client
        :param details: Additional details about the event as a dictionary
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.1, 8.2, 8.3
        """
        now = utc_now()
        
        # Handle both enum and string event types
        if isinstance(event_type, AuditEventType):
            event_type_value = event_type.value
        else:
            event_type_value = str(event_type)
        
        # Serialize details to JSON if provided
        details_json = None
        if details is not None:
            details_json = json.dumps(details)
        
        # Create the audit log entry
        audit_log = AuditLog(
            event_type=event_type_value,
            timestamp=now,
            user_id=str(user_id) if user_id is not None else None,
            username=username,
            target_user_id=str(target_user_id) if target_user_id is not None else None,
            target_username=target_username,
            client_ip=client_ip,
            details_json=details_json
        )
        
        self._db_session.add(audit_log)
        self._db_session.commit()
        
        return self._audit_log_to_entry(audit_log)

    
    # =========================================================================
    # Convenience Logging Methods
    # =========================================================================
    
    def log_auth_success(
        self,
        user_id: str,
        username: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a successful authentication event.
        
        :param user_id: ID of the authenticated user
        :param username: Username of the authenticated user
        :param client_ip: IP address of the client
        :param details: Additional details about the authentication
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.1
        """
        return self.log_event(
            event_type=AuditEventType.AUTH_SUCCESS,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=details
        )
    
    def log_auth_failure(
        self,
        username: Optional[str] = None,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a failed authentication event.
        
        :param username: Username that was attempted (if available)
        :param client_ip: IP address of the client
        :param details: Additional details about the failure
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.1
        """
        return self.log_event(
            event_type=AuditEventType.AUTH_FAILURE,
            username=username,
            client_ip=client_ip,
            details=details
        )
    
    def log_logout(
        self,
        user_id: str,
        username: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a logout event.
        
        :param user_id: ID of the user who logged out
        :param username: Username of the user who logged out
        :param client_ip: IP address of the client
        :param details: Additional details about the logout
        :returns: AuditLogEntry with the created log entry data
        """
        return self.log_event(
            event_type=AuditEventType.LOGOUT,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=details
        )
    
    def log_user_created(
        self,
        user_id: str,
        username: str,
        target_user_id: str,
        target_username: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a user creation event.
        
        :param user_id: ID of the user who created the new user
        :param username: Username of the user who created the new user
        :param target_user_id: ID of the newly created user
        :param target_username: Username of the newly created user
        :param client_ip: IP address of the client
        :param details: Additional details about the user creation
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.2
        """
        return self.log_event(
            event_type=AuditEventType.USER_CREATED,
            user_id=user_id,
            username=username,
            target_user_id=target_user_id,
            target_username=target_username,
            client_ip=client_ip,
            details=details
        )
    
    def log_user_updated(
        self,
        user_id: str,
        username: str,
        target_user_id: str,
        target_username: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a user update event.
        
        :param user_id: ID of the user who made the update
        :param username: Username of the user who made the update
        :param target_user_id: ID of the updated user
        :param target_username: Username of the updated user
        :param client_ip: IP address of the client
        :param details: Additional details about the update
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.2
        """
        return self.log_event(
            event_type=AuditEventType.USER_UPDATED,
            user_id=user_id,
            username=username,
            target_user_id=target_user_id,
            target_username=target_username,
            client_ip=client_ip,
            details=details
        )

    
    def log_user_deactivated(
        self,
        user_id: str,
        username: str,
        target_user_id: str,
        target_username: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a user deactivation event.
        
        :param user_id: ID of the user who deactivated the account
        :param username: Username of the user who deactivated the account
        :param target_user_id: ID of the deactivated user
        :param target_username: Username of the deactivated user
        :param client_ip: IP address of the client
        :param details: Additional details about the deactivation
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.2
        """
        return self.log_event(
            event_type=AuditEventType.USER_DEACTIVATED,
            user_id=user_id,
            username=username,
            target_user_id=target_user_id,
            target_username=target_username,
            client_ip=client_ip,
            details=details
        )
    
    def log_role_assigned(
        self,
        user_id: str,
        username: str,
        target_user_id: str,
        target_username: str,
        role_name: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a role assignment event.
        
        :param user_id: ID of the user who assigned the role
        :param username: Username of the user who assigned the role
        :param target_user_id: ID of the user who received the role
        :param target_username: Username of the user who received the role
        :param role_name: Name of the assigned role
        :param client_ip: IP address of the client
        :param details: Additional details about the assignment
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.2
        """
        event_details = details.copy() if details else {}
        event_details['role_name'] = role_name
        
        return self.log_event(
            event_type=AuditEventType.ROLE_ASSIGNED,
            user_id=user_id,
            username=username,
            target_user_id=target_user_id,
            target_username=target_username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_role_removed(
        self,
        user_id: str,
        username: str,
        target_user_id: str,
        target_username: str,
        role_name: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a role removal event.
        
        :param user_id: ID of the user who removed the role
        :param username: Username of the user who removed the role
        :param target_user_id: ID of the user who lost the role
        :param target_username: Username of the user who lost the role
        :param role_name: Name of the removed role
        :param client_ip: IP address of the client
        :param details: Additional details about the removal
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.2
        """
        event_details = details.copy() if details else {}
        event_details['role_name'] = role_name
        
        return self.log_event(
            event_type=AuditEventType.ROLE_REMOVED,
            user_id=user_id,
            username=username,
            target_user_id=target_user_id,
            target_username=target_username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_password_changed(
        self,
        user_id: str,
        username: str,
        target_user_id: Optional[str] = None,
        target_username: Optional[str] = None,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a password change event.
        
        :param user_id: ID of the user who changed the password
        :param username: Username of the user who changed the password
        :param target_user_id: ID of the user whose password was changed (if different)
        :param target_username: Username of the user whose password was changed (if different)
        :param client_ip: IP address of the client
        :param details: Additional details about the password change
        :returns: AuditLogEntry with the created log entry data
        """
        return self.log_event(
            event_type=AuditEventType.PASSWORD_CHANGED,
            user_id=user_id,
            username=username,
            target_user_id=target_user_id or user_id,
            target_username=target_username or username,
            client_ip=client_ip,
            details=details
        )
    
    def log_password_reset_requested(
        self,
        username: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a password reset request event.
        
        :param username: Username for which reset was requested
        :param client_ip: IP address of the client
        :param details: Additional details about the request
        :returns: AuditLogEntry with the created log entry data
        """
        return self.log_event(
            event_type=AuditEventType.PASSWORD_RESET_REQUESTED,
            username=username,
            client_ip=client_ip,
            details=details
        )
    
    def log_password_reset_completed(
        self,
        user_id: str,
        username: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a password reset completion event.
        
        :param user_id: ID of the user who completed the reset
        :param username: Username of the user who completed the reset
        :param client_ip: IP address of the client
        :param details: Additional details about the reset
        :returns: AuditLogEntry with the created log entry data
        """
        return self.log_event(
            event_type=AuditEventType.PASSWORD_RESET_COMPLETED,
            user_id=user_id,
            username=username,
            target_user_id=user_id,
            target_username=username,
            client_ip=client_ip,
            details=details
        )

    
    def log_variable_created(
        self,
        user_id: str,
        username: str,
        variable_name: str,
        variable_value: Any,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a global variable creation event.
        
        :param user_id: ID of the user who created the variable
        :param username: Username of the user who created the variable
        :param variable_name: Name of the created variable
        :param variable_value: Value of the created variable
        :param client_ip: IP address of the client
        :param details: Additional details about the creation
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.3
        """
        event_details = details.copy() if details else {}
        event_details['variable_name'] = variable_name
        event_details['new_value'] = variable_value
        
        return self.log_event(
            event_type=AuditEventType.VARIABLE_CREATED,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_variable_updated(
        self,
        user_id: str,
        username: str,
        variable_name: str,
        old_value: Any,
        new_value: Any,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a global variable update event.
        
        :param user_id: ID of the user who updated the variable
        :param username: Username of the user who updated the variable
        :param variable_name: Name of the updated variable
        :param old_value: Previous value of the variable
        :param new_value: New value of the variable
        :param client_ip: IP address of the client
        :param details: Additional details about the update
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.3
        """
        event_details = details.copy() if details else {}
        event_details['variable_name'] = variable_name
        event_details['old_value'] = old_value
        event_details['new_value'] = new_value
        
        return self.log_event(
            event_type=AuditEventType.VARIABLE_UPDATED,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_variable_deleted(
        self,
        user_id: str,
        username: str,
        variable_name: str,
        old_value: Any,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a global variable deletion event.
        
        :param user_id: ID of the user who deleted the variable
        :param username: Username of the user who deleted the variable
        :param variable_name: Name of the deleted variable
        :param old_value: Value of the variable before deletion
        :param client_ip: IP address of the client
        :param details: Additional details about the deletion
        :returns: AuditLogEntry with the created log entry data
        
        Validates: Requirements 8.3
        """
        event_details = details.copy() if details else {}
        event_details['variable_name'] = variable_name
        event_details['old_value'] = old_value
        
        return self.log_event(
            event_type=AuditEventType.VARIABLE_DELETED,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_session_terminated(
        self,
        user_id: str,
        username: str,
        target_user_id: Optional[str] = None,
        target_username: Optional[str] = None,
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a session termination event.
        
        :param user_id: ID of the user who terminated the session
        :param username: Username of the user who terminated the session
        :param target_user_id: ID of the user whose session was terminated
        :param target_username: Username of the user whose session was terminated
        :param session_id: ID of the terminated session
        :param client_ip: IP address of the client
        :param details: Additional details about the termination
        :returns: AuditLogEntry with the created log entry data
        """
        event_details = details.copy() if details else {}
        if session_id:
            event_details['session_id'] = session_id
        
        return self.log_event(
            event_type=AuditEventType.SESSION_TERMINATED,
            user_id=user_id,
            username=username,
            target_user_id=target_user_id,
            target_username=target_username,
            client_ip=client_ip,
            details=event_details
        )

    
    def log_secret_created(
        self,
        user_id: str,
        username: str,
        secret_name: str,
        scope_name: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a secret creation event.
        
        :param user_id: ID of the user who created the secret
        :param username: Username of the user who created the secret
        :param secret_name: Name of the created secret
        :param scope_name: Name of the scope containing the secret
        :param client_ip: IP address of the client
        :param details: Additional details about the creation
        :returns: AuditLogEntry with the created log entry data
        """
        event_details = details.copy() if details else {}
        event_details['secret_name'] = secret_name
        event_details['scope_name'] = scope_name
        
        return self.log_event(
            event_type=AuditEventType.SECRET_CREATED,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_secret_updated(
        self,
        user_id: str,
        username: str,
        secret_name: str,
        scope_name: str,
        version: int,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a secret update event.
        
        :param user_id: ID of the user who updated the secret
        :param username: Username of the user who updated the secret
        :param secret_name: Name of the updated secret
        :param scope_name: Name of the scope containing the secret
        :param version: New version number of the secret
        :param client_ip: IP address of the client
        :param details: Additional details about the update
        :returns: AuditLogEntry with the created log entry data
        """
        event_details = details.copy() if details else {}
        event_details['secret_name'] = secret_name
        event_details['scope_name'] = scope_name
        event_details['version'] = version
        
        return self.log_event(
            event_type=AuditEventType.SECRET_UPDATED,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_secret_deleted(
        self,
        user_id: str,
        username: str,
        secret_name: str,
        scope_name: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a secret deletion event.
        
        :param user_id: ID of the user who deleted the secret
        :param username: Username of the user who deleted the secret
        :param secret_name: Name of the deleted secret
        :param scope_name: Name of the scope containing the secret
        :param client_ip: IP address of the client
        :param details: Additional details about the deletion
        :returns: AuditLogEntry with the created log entry data
        """
        event_details = details.copy() if details else {}
        event_details['secret_name'] = secret_name
        event_details['scope_name'] = scope_name
        
        return self.log_event(
            event_type=AuditEventType.SECRET_DELETED,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_secret_accessed(
        self,
        user_id: str,
        username: str,
        secret_name: str,
        scope_name: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a secret access event.
        
        :param user_id: ID of the user who accessed the secret
        :param username: Username of the user who accessed the secret
        :param secret_name: Name of the accessed secret
        :param scope_name: Name of the scope containing the secret
        :param client_ip: IP address of the client
        :param details: Additional details about the access
        :returns: AuditLogEntry with the created log entry data
        """
        event_details = details.copy() if details else {}
        event_details['secret_name'] = secret_name
        event_details['scope_name'] = scope_name
        
        return self.log_event(
            event_type=AuditEventType.SECRET_ACCESSED,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_scope_created(
        self,
        user_id: str,
        username: str,
        scope_name: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a scope creation event.
        
        :param user_id: ID of the user who created the scope
        :param username: Username of the user who created the scope
        :param scope_name: Name of the created scope
        :param client_ip: IP address of the client
        :param details: Additional details about the creation
        :returns: AuditLogEntry with the created log entry data
        """
        event_details = details.copy() if details else {}
        event_details['scope_name'] = scope_name
        
        return self.log_event(
            event_type=AuditEventType.SCOPE_CREATED,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=event_details
        )
    
    def log_scope_deleted(
        self,
        user_id: str,
        username: str,
        scope_name: str,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLogEntry:
        """
        Log a scope deletion event.
        
        :param user_id: ID of the user who deleted the scope
        :param username: Username of the user who deleted the scope
        :param scope_name: Name of the deleted scope
        :param client_ip: IP address of the client
        :param details: Additional details about the deletion
        :returns: AuditLogEntry with the created log entry data
        """
        event_details = details.copy() if details else {}
        event_details['scope_name'] = scope_name
        
        return self.log_event(
            event_type=AuditEventType.SCOPE_DELETED,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            details=event_details
        )

    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def query_logs(self, query: AuditLogQuery) -> AuditLogListResponse:
        """
        Query audit logs with filters.
        
        :param query: AuditLogQuery with filter criteria
        :returns: AuditLogListResponse with paginated results
        
        Validates: Requirements 8.5
        """
        db_query = self._db_session.query(AuditLog)
        
        # Apply event type filter
        if query.event_types:
            event_type_values = [et.value for et in query.event_types]
            db_query = db_query.filter(AuditLog.event_type.in_(event_type_values))
        
        # Apply user filter
        if query.user_id:
            db_query = db_query.filter(AuditLog.user_id == str(query.user_id))
        
        # Apply target user filter
        if query.target_user_id:
            db_query = db_query.filter(AuditLog.target_user_id == str(query.target_user_id))
        
        # Apply date range filters
        if query.start_date:
            db_query = db_query.filter(AuditLog.timestamp >= query.start_date)
        
        if query.end_date:
            db_query = db_query.filter(AuditLog.timestamp <= query.end_date)
        
        # Get total count before pagination
        total = db_query.count()
        
        # Apply ordering and pagination
        entries = db_query.order_by(AuditLog.timestamp.desc()) \
            .offset(query.offset) \
            .limit(query.limit) \
            .all()
        
        return AuditLogListResponse(
            entries=[self._audit_log_to_entry(entry) for entry in entries],
            total=total,
            offset=query.offset,
            limit=query.limit
        )
    
    def get_logs_by_event_type(
        self,
        event_type: AuditEventType,
        offset: int = 0,
        limit: int = 50
    ) -> AuditLogListResponse:
        """
        Get audit logs filtered by event type.
        
        :param event_type: The event type to filter by
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: AuditLogListResponse with paginated results
        """
        query = AuditLogQuery(
            event_types=[event_type],
            offset=offset,
            limit=limit
        )
        return self.query_logs(query)
    
    def get_logs_by_user(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 50
    ) -> AuditLogListResponse:
        """
        Get audit logs for a specific user.
        
        :param user_id: The user ID to filter by
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: AuditLogListResponse with paginated results
        """
        query = AuditLogQuery(
            user_id=user_id,
            offset=offset,
            limit=limit
        )
        return self.query_logs(query)
    
    def get_logs_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        offset: int = 0,
        limit: int = 50
    ) -> AuditLogListResponse:
        """
        Get audit logs within a date range.
        
        :param start_date: Start of the date range
        :param end_date: End of the date range
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: AuditLogListResponse with paginated results
        """
        query = AuditLogQuery(
            start_date=start_date,
            end_date=end_date,
            offset=offset,
            limit=limit
        )
        return self.query_logs(query)
    
    # =========================================================================
    # Cleanup Methods
    # =========================================================================
    
    def cleanup_old_logs(self, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
        """
        Remove logs older than the retention period.
        
        :param retention_days: Number of days to retain logs (default 90)
        :returns: Number of logs removed
        
        Validates: Requirements 8.4
        """
        cutoff_date = utc_now() - timedelta(days=retention_days)
        
        # Count logs to be deleted
        count = self._db_session.query(AuditLog).filter(
            AuditLog.timestamp < cutoff_date
        ).count()
        
        # Delete old logs
        self._db_session.query(AuditLog).filter(
            AuditLog.timestamp < cutoff_date
        ).delete(synchronize_session=False)
        
        self._db_session.commit()
        
        return count
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _audit_log_to_entry(self, audit_log: AuditLog) -> AuditLogEntry:
        """
        Convert an AuditLog ORM object to an AuditLogEntry dataclass.
        
        :param audit_log: The AuditLog ORM object
        :returns: AuditLogEntry dataclass
        """
        # Parse details JSON if present
        details = None
        if audit_log.details_json:
            details = json.loads(audit_log.details_json)
        
        # Convert event_type string to enum if possible, otherwise keep as string
        try:
            event_type = AuditEventType(audit_log.event_type)
        except ValueError:
            # Event type is not in the enum, use the string value
            event_type = audit_log.event_type
        
        return AuditLogEntry(
            id=audit_log.id,
            event_type=event_type,
            timestamp=audit_log.timestamp,
            user_id=audit_log.user_id,
            username=audit_log.username,
            target_user_id=audit_log.target_user_id,
            target_username=audit_log.target_username,
            client_ip=audit_log.client_ip,
            details=details
        )
