"""
.. module:: user_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the UserManager class for user CRUD operations, validation, and role management

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now


# =============================================================================
# Validation Constants
# =============================================================================

# Username validation: alphanumeric, underscore, hyphen only
# Must start with alphanumeric, 3-64 characters
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$')

# Email validation pattern (RFC 5322 simplified)
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class UserCreateRequest:
    """Request dataclass for creating a new user."""
    username: str
    email: str
    password: str
    display_name: str
    firstname: str = ""
    lastname: str = ""
    role_ids: List[int] = field(default_factory=list)


@dataclass
class UserUpdateRequest:
    """Request dataclass for updating an existing user."""
    email: Optional[str] = None
    display_name: Optional[str] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    is_active: Optional[bool] = None
    role_ids: Optional[List[int]] = None


@dataclass
class UserResponse:
    """Response dataclass for user data."""
    id: str
    username: str
    email: str
    display_name: str
    firstname: str
    lastname: str
    is_active: bool
    roles: List[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class UserListResponse:
    """Response dataclass for paginated user list."""
    users: List[UserResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Validation Errors
# =============================================================================

class ValidationError(Exception):
    """Exception raised when validation fails."""
    
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(self.message)


class DuplicateUserError(Exception):
    """Exception raised when attempting to create a user with duplicate username or email."""
    
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(self.message)


class UserNotFoundError(Exception):
    """Exception raised when a user is not found."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class RoleNotFoundError(Exception):
    """Exception raised when a role is not found."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


# =============================================================================
# Validation Functions
# =============================================================================

def validate_username(username: str) -> bool:
    """
    Validate that a username contains only alphanumeric characters, underscores, and hyphens.
    
    Requirements:
    - Must start with an alphanumeric character
    - Can contain alphanumeric characters, underscores, and hyphens
    - Must be between 3 and 64 characters long
    
    :param username: The username to validate
    :returns: True if valid, False otherwise
    
    Validates: Requirements 1.6
    """
    if not username:
        return False
    
    if not USERNAME_PATTERN.match(username):
        return False
    
    return True


def validate_email(email: str) -> bool:
    """
    Validate that an email address conforms to standard email format.
    
    Requirements:
    - Must contain exactly one @ symbol
    - Must have a valid local part (before @)
    - Must have a valid domain part (after @)
    - Domain must have at least one dot with valid TLD
    
    :param email: The email address to validate
    :returns: True if valid, False otherwise
    
    Validates: Requirements 1.7
    """
    if not email:
        return False
    
    if not EMAIL_PATTERN.match(email):
        return False
    
    return True


# =============================================================================
# UserManager Class
# =============================================================================

class UserManager:
    """
    Manager class for user CRUD operations, validation, and role management.
    
    This class handles all user-related operations including:
    - User creation with validation
    - User retrieval by ID or username
    - User updates
    - User deactivation with session invalidation
    - Role assignment and removal
    - Permission calculation
    
    Note: The User ORM model uses 'login' for username and 'first_name'/'last_name'
    for name fields. This manager maps these to the API's 'username'/'firstname'/'lastname'.
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None):
        """
        Initialize the UserManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def validate_username(self, username: str) -> bool:
        """
        Validate that a username contains only alphanumeric characters, underscores, and hyphens.
        
        :param username: The username to validate
        :returns: True if valid, False otherwise
        
        Validates: Requirements 1.6
        """
        return validate_username(username)
    
    def validate_email(self, email: str) -> bool:
        """
        Validate that an email address conforms to standard email format.
        
        :param email: The email address to validate
        :returns: True if valid, False otherwise
        
        Validates: Requirements 1.7
        """
        return validate_email(email)
    
    def _validate_user_create_request(self, request: UserCreateRequest) -> None:
        """
        Validate a user creation request.
        
        :param request: The user creation request to validate
        :raises ValidationError: If validation fails
        """
        if not self.validate_username(request.username):
            raise ValidationError(
                "Username must be 3-64 characters, start with alphanumeric, "
                "and contain only alphanumeric characters, underscores, and hyphens",
                field="username"
            )
        
        if not self.validate_email(request.email):
            raise ValidationError(
                "Email address must conform to standard email format",
                field="email"
            )
        
        if not request.display_name or len(request.display_name.strip()) == 0:
            raise ValidationError(
                "Display name is required",
                field="display_name"
            )
        
        if not request.password or len(request.password) < 12:
            raise ValidationError(
                "Password must be at least 12 characters",
                field="password"
            )

    
    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    def create_user(self, request: UserCreateRequest) -> UserResponse:
        """
        Create a new user account.
        
        :param request: The user creation request containing user data
        :returns: UserResponse with the created user data
        :raises ValidationError: If validation fails
        :raises DuplicateUserError: If username or email already exists
        
        Validates: Requirements 1.1, 1.2
        """
        from automojo.pychestrate.core.orm import User, SystemRole
        
        # Validate the request
        self._validate_user_create_request(request)
        
        # Check for duplicate username (login field in User model)
        existing_user = self._db_session.query(User).filter(
            User.login == request.username
        ).first()
        
        if existing_user:
            raise DuplicateUserError(
                f"Username '{request.username}' already exists",
                field="username"
            )
        
        # Check for duplicate email
        existing_email = self._db_session.query(User).filter(
            User.email == request.email
        ).first()
        
        if existing_email:
            raise DuplicateUserError(
                f"Email '{request.email}' already exists",
                field="email"
            )
        
        # Create the user
        now = utc_now()
        
        user = User(
            login=request.username,
            email=request.email,
            display_name=request.display_name,
            first_name=request.firstname or "",
            last_name=request.lastname or "",
            status="active",
            authtype="internal",
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(user)
        
        # Get role names for response
        role_names = []
        if request.role_ids:
            roles = self._db_session.query(SystemRole).filter(
                SystemRole.id.in_(request.role_ids)
            ).all()
            role_names = [role.name for role in roles]
            # Store roles as comma-separated string
            user.roles = ",".join(role_names)
        
        self._db_session.commit()
        
        # Log the user creation event
        if self._audit_logger:
            self._audit_logger.log_user_created(
                user_id=str(user.id),
                username=user.login,
                target_user_id=str(user.id),
                target_username=user.login,
                details={"email": user.email, "display_name": user.display_name}
            )
        
        return UserResponse(
            id=str(user.id),
            username=user.login,
            email=user.email,
            display_name=user.display_name or "",
            firstname=user.first_name,
            lastname=user.last_name,
            is_active=(user.status == "active"),
            roles=role_names,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    
    def get_user(self, user_id: str) -> Optional[UserResponse]:
        """
        Retrieve a user by ID.
        
        :param user_id: The user's unique identifier
        :returns: UserResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import User
        
        user = self._db_session.query(User).filter(User.id == user_id).first()
        
        if not user:
            return None
        
        return self._user_to_response(user)
    
    def get_user_by_username(self, username: str) -> Optional[UserResponse]:
        """
        Retrieve a user by username.
        
        :param username: The username to search for
        :returns: UserResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import User
        
        user = self._db_session.query(User).filter(User.login == username).first()
        
        if not user:
            return None
        
        return self._user_to_response(user)
    
    def update_user(self, user_id: str, request: UserUpdateRequest) -> UserResponse:
        """
        Update user information.
        
        :param user_id: The user's unique identifier
        :param request: The update request containing fields to update
        :returns: UserResponse with the updated user data
        :raises UserNotFoundError: If user is not found
        :raises ValidationError: If validation fails
        :raises DuplicateUserError: If email already exists
        
        Validates: Requirements 1.3
        """
        from automojo.pychestrate.core.orm import User, SystemRole
        
        user = self._db_session.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        
        # Validate and update email if provided
        if request.email is not None:
            if not self.validate_email(request.email):
                raise ValidationError(
                    "Email address must conform to standard email format",
                    field="email"
                )
            
            # Check for duplicate email (excluding current user)
            existing_email = self._db_session.query(User).filter(
                User.email == request.email,
                User.id != user_id
            ).first()
            
            if existing_email:
                raise DuplicateUserError(
                    f"Email '{request.email}' already exists",
                    field="email"
                )
            
            user.email = request.email
        
        # Update display name if provided
        if request.display_name is not None:
            if len(request.display_name.strip()) == 0:
                raise ValidationError(
                    "Display name cannot be empty",
                    field="display_name"
                )
            user.display_name = request.display_name
        
        # Update firstname if provided
        if request.firstname is not None:
            user.first_name = request.firstname
        
        # Update lastname if provided
        if request.lastname is not None:
            user.last_name = request.lastname
        
        # Update active status if provided
        if request.is_active is not None:
            user.status = "active" if request.is_active else "inactive"
        
        # Update roles if provided
        if request.role_ids is not None:
            roles = self._db_session.query(SystemRole).filter(
                SystemRole.id.in_(request.role_ids)
            ).all()
            role_names = [role.name for role in roles]
            user.roles = ",".join(role_names)
        
        user.updated_at = utc_now()
        self._db_session.commit()
        
        # Log the user update event
        if self._audit_logger:
            self._audit_logger.log_user_updated(
                user_id=str(user.id),
                username=user.login,
                target_user_id=str(user.id),
                target_username=user.login,
                details={"updated_fields": [k for k, v in request.__dict__.items() if v is not None]}
            )
        
        return self._user_to_response(user)
    
    def list_users(
        self,
        offset: int = 0,
        limit: int = 50,
        search: str = None,
        is_active: bool = None
    ) -> UserListResponse:
        """
        List users with pagination and filtering.
        
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :param search: Optional search string for username, email, or display_name
        :param is_active: Optional filter for active/inactive users
        :returns: UserListResponse with paginated user list
        
        Validates: Requirements 1.5
        """
        from automojo.pychestrate.core.orm import User
        from sqlalchemy import or_
        
        query = self._db_session.query(User)
        
        # Apply search filter
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    User.login.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.display_name.ilike(search_pattern)
                )
            )
        
        # Apply active status filter
        if is_active is not None:
            status = "active" if is_active else "inactive"
            query = query.filter(User.status == status)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        users = query.offset(offset).limit(limit).all()
        
        return UserListResponse(
            users=[self._user_to_response(user) for user in users],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def deactivate_user(self, user_id: str) -> None:
        """
        Deactivate a user account and invalidate all active sessions.
        
        :param user_id: The user's unique identifier
        :raises UserNotFoundError: If user is not found
        
        Validates: Requirements 1.4
        """
        from automojo.pychestrate.core.orm import User, Session as SessionModel
        
        user = self._db_session.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        
        # Deactivate the user
        user.status = "inactive"
        user.updated_at = utc_now()
        
        # Invalidate all sessions for this user
        self._db_session.query(SessionModel).filter(
            SessionModel.user_id == user_id
        ).delete()
        
        self._db_session.commit()
        
        # Log the user deactivation event
        if self._audit_logger:
            self._audit_logger.log_user_deactivated(
                user_id=str(user.id),
                username=user.login,
                target_user_id=str(user.id),
                target_username=user.login
            )
    
    # =========================================================================
    # Role Management
    # =========================================================================
    
    def assign_role(self, user_id: str, role_id: int) -> None:
        """
        Assign a role to a user.
        
        :param user_id: The user's unique identifier
        :param role_id: The role's unique identifier
        :raises UserNotFoundError: If user is not found
        :raises RoleNotFoundError: If role is not found
        
        Validates: Requirements 4.2
        """
        from automojo.pychestrate.core.orm import User, SystemRole
        
        user = self._db_session.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        
        role = self._db_session.query(SystemRole).filter(SystemRole.id == role_id).first()
        
        if not role:
            raise RoleNotFoundError(f"Role with ID '{role_id}' not found")
        
        # Get current roles
        current_roles = set(user.roles.split(",")) if user.roles else set()
        
        # Add the new role
        current_roles.add(role.name)
        current_roles.discard("")  # Remove empty string if present
        
        # Update user roles
        user.roles = ",".join(sorted(current_roles))
        user.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the role assignment event
        if self._audit_logger:
            self._audit_logger.log_role_assigned(
                user_id=str(user.id),
                username=user.login,
                target_user_id=str(user.id),
                target_username=user.login,
                role_name=role.name
            )
    
    def remove_role(self, user_id: str, role_id: int) -> None:
        """
        Remove a role from a user.
        
        :param user_id: The user's unique identifier
        :param role_id: The role's unique identifier
        :raises UserNotFoundError: If user is not found
        :raises RoleNotFoundError: If role is not found
        
        Validates: Requirements 4.3
        """
        from automojo.pychestrate.core.orm import User, SystemRole
        
        user = self._db_session.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        
        role = self._db_session.query(SystemRole).filter(SystemRole.id == role_id).first()
        
        if not role:
            raise RoleNotFoundError(f"Role with ID '{role_id}' not found")
        
        # Get current roles
        current_roles = set(user.roles.split(",")) if user.roles else set()
        
        # Remove the role
        current_roles.discard(role.name)
        current_roles.discard("")  # Remove empty string if present
        
        # Update user roles
        user.roles = ",".join(sorted(current_roles))
        user.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the role removal event
        if self._audit_logger:
            self._audit_logger.log_role_removed(
                user_id=str(user.id),
                username=user.login,
                target_user_id=str(user.id),
                target_username=user.login,
                role_name=role.name
            )
    
    def get_effective_permissions(self, user_id: str) -> List[str]:
        """
        Calculate effective permissions from all assigned roles.
        
        :param user_id: The user's unique identifier
        :returns: List of permission names the user has
        :raises UserNotFoundError: If user is not found
        
        Validates: Requirements 4.2, 4.3
        """
        from automojo.pychestrate.core.orm import User, SystemRole
        
        user = self._db_session.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise UserNotFoundError(f"User with ID '{user_id}' not found")
        
        # Get role names from user
        role_names = user.roles.split(",") if user.roles else []
        role_names = [r.strip() for r in role_names if r.strip()]
        
        if not role_names:
            return []
        
        # Get all roles with their permissions
        roles = self._db_session.query(SystemRole).filter(
            SystemRole.name.in_(role_names)
        ).all()
        
        # Collect all unique permissions
        permissions = set()
        for role in roles:
            for permission in role.permissions:
                permissions.add(permission.name)
        
        return sorted(list(permissions))
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _user_to_response(self, user) -> UserResponse:
        """
        Convert a User ORM object to a UserResponse dataclass.
        
        :param user: The User ORM object
        :returns: UserResponse dataclass
        """
        role_names = user.roles.split(",") if user.roles else []
        role_names = [r.strip() for r in role_names if r.strip()]
        
        return UserResponse(
            id=str(user.id),
            username=user.login,
            email=user.email,
            display_name=user.display_name or "",
            firstname=user.first_name or "",
            lastname=user.last_name or "",
            is_active=(user.status == "active"),
            roles=role_names,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
