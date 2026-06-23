"""
.. module:: project_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the ProjectManager class for project CRUD operations, membership management,
               resource assignment, and project variables

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import VariableType


# =============================================================================
# Validation Constants
# =============================================================================

# Project name validation: alphanumeric, underscore, hyphen, period
# Must start with alphanumeric, 1-128 characters
# Use \Z instead of $ to ensure no trailing newlines are accepted
PROJECT_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}\Z')


# =============================================================================
# Enums
# =============================================================================

class ProjectRole(str, Enum):
    """
        Enum-like class to represent the roles a user can have in a project.
    """
    OWNER = 'owner'
    ADMINISTRATOR = 'administrator'
    DEVELOPER = 'developer'
    VIEWER = 'viewer'


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class ProjectCreateRequest:
    """Request dataclass for creating a new project."""
    name: str
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectUpdateRequest:
    """Request dataclass for updating an existing project."""
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ProjectResponse:
    """Response dataclass for project data."""
    id: int
    name: str
    description: str
    owner_id: str
    owner_username: str
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    member_count: int
    repository_count: int
    active_jobs: int


@dataclass
class ProjectListResponse:
    """Response dataclass for paginated project list."""
    projects: List[ProjectResponse]
    total: int
    offset: int
    limit: int


@dataclass
class ProjectMemberResponse:
    """Response dataclass for project member data."""
    user_id: str
    username: str
    display_name: str
    role: ProjectRole
    joined_at: datetime


@dataclass
class ProjectMemberListResponse:
    """Response dataclass for paginated project member list."""
    members: List[ProjectMemberResponse]
    total: int
    offset: int
    limit: int


@dataclass
class ProjectVariableCreateRequest:
    """Request dataclass for creating a new project variable."""
    name: str
    value: Any
    var_type: str  # string, integer, float, boolean, json
    is_sensitive: bool = False
    description: str = ""


@dataclass
class ProjectVariableUpdateRequest:
    """Request dataclass for updating an existing project variable."""
    value: Any
    description: Optional[str] = None


@dataclass
class ProjectVariableResponse:
    """Response dataclass for project variable data."""
    id: int
    name: str
    value: Any  # Masked if sensitive
    var_type: str
    is_sensitive: bool
    description: str
    created_at: datetime
    updated_at: datetime


@dataclass
class ProjectVariableListResponse:
    """Response dataclass for paginated project variable list."""
    variables: List[ProjectVariableResponse]
    total: int
    offset: int
    limit: int


@dataclass
class AssignedResourceResponse:
    """Response dataclass for assigned resource data."""
    resource_id: int
    resource_name: str
    resource_type: str
    pool_id: Optional[int]
    pool_name: Optional[str]
    health_status: str
    current_allocations: int
    capacity: int
    assigned_at: datetime


@dataclass
class AssignedResourceListResponse:
    """Response dataclass for paginated assigned resource list."""
    resources: List[AssignedResourceResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Exceptions
# =============================================================================

class ProjectValidationError(Exception):
    """Exception raised when project validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "VALIDATION_ERROR"
        super().__init__(self.message)


class ProjectNotFoundError(Exception):
    """Exception raised when a project is not found."""
    
    def __init__(self, message: str, error_code: str = "PROJECT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateProjectError(Exception):
    """Exception raised when attempting to create a project with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "PROJECT_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class ProjectHasActiveJobsError(Exception):
    """Exception raised when attempting to delete a project with active jobs."""
    
    def __init__(self, message: str, error_code: str = "PROJECT_HAS_ACTIVE_JOBS"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class MemberNotFoundError(Exception):
    """Exception raised when a project member is not found."""
    
    def __init__(self, message: str, error_code: str = "MEMBER_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateMemberError(Exception):
    """Exception raised when attempting to add a duplicate member."""
    
    def __init__(self, message: str, error_code: str = "MEMBER_ALREADY_EXISTS"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ResourceNotFoundError(Exception):
    """Exception raised when a resource is not found."""
    
    def __init__(self, message: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ResourceAlreadyAssignedError(Exception):
    """Exception raised when a resource is already assigned to the project."""
    
    def __init__(self, message: str, error_code: str = "RESOURCE_ALREADY_ASSIGNED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ResourceNotAssignedError(Exception):
    """Exception raised when a resource is not assigned to the project."""
    
    def __init__(self, message: str, error_code: str = "RESOURCE_NOT_ASSIGNED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class VariableNotFoundError(Exception):
    """Exception raised when a project variable is not found."""
    
    def __init__(self, message: str, error_code: str = "VARIABLE_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateVariableError(Exception):
    """Exception raised when attempting to create a duplicate variable."""
    
    def __init__(self, message: str, error_code: str = "VARIABLE_ALREADY_EXISTS"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class TypeValidationError(Exception):
    """Exception raised when value type validation fails."""
    
    def __init__(self, message: str, expected_type: str = None, actual_type: str = None):
        self.message = message
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(self.message)


class PermissionDeniedError(Exception):
    """Exception raised when a user does not have permission for an action."""
    
    def __init__(self, message: str, error_code: str = "PERMISSION_DENIED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


# =============================================================================
# Validation Functions
# =============================================================================

def validate_project_name(name: str) -> bool:
    """
    Validate that a project name contains only alphanumeric characters, underscores, hyphens, and periods.
    
    Requirements:
    - Must start with an alphanumeric character
    - Can contain alphanumeric characters, underscores, hyphens, and periods
    - Must be between 1 and 128 characters long
    
    :param name: The project name to validate
    :returns: True if valid, False otherwise
    
    Validates: Requirements 1.6
    """
    if not name:
        return False
    
    if not PROJECT_NAME_PATTERN.match(name):
        return False
    
    return True


# =============================================================================
# Type Validation and Serialization Functions
# =============================================================================

def validate_variable_value(value: Any, var_type: str) -> bool:
    """
    Validate that a value matches the expected variable type.
    
    :param value: The value to validate
    :param var_type: The expected variable type (string, integer, float, boolean, json)
    :returns: True if valid, False otherwise
    
    Validates: Requirements 11.4
    """
    if value is None:
        return True  # None is valid for all types
    
    if var_type == 'string':
        return isinstance(value, str)
    
    elif var_type == 'integer':
        # Accept int but not bool (bool is subclass of int in Python)
        return isinstance(value, int) and not isinstance(value, bool)
    
    elif var_type == 'float':
        # Accept int or float but not bool
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    
    elif var_type == 'boolean':
        return isinstance(value, bool)
    
    elif var_type == 'json':
        # JSON type accepts any JSON-serializable value
        try:
            json.dumps(value)
            return True
        except (TypeError, ValueError):
            return False
    
    return False


def serialize_variable_value(value: Any) -> str:
    """
    Serialize a value to JSON string for storage.
    
    :param value: The value to serialize
    :returns: JSON-encoded string
    
    Validates: Requirements 11.7
    """
    return json.dumps(value)


def deserialize_variable_value(json_str: str, var_type: str) -> Any:
    """
    Deserialize a JSON string to a typed value.
    
    :param json_str: The JSON-encoded string
    :param var_type: The expected variable type
    :returns: The deserialized value
    """
    if json_str is None:
        return None
    
    value = json.loads(json_str)
    
    # For float type, ensure we return a float even if stored as int
    if var_type == 'float' and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    
    return value


# =============================================================================
# Permission Definitions
# =============================================================================

# Role permissions mapping
ROLE_PERMISSIONS = {
    ProjectRole.OWNER: {
        'project.read', 'project.update', 'project.delete',
        'member.read', 'member.add', 'member.remove', 'member.update',
        'resource.read', 'resource.assign', 'resource.unassign', 'resource.checkout',
        'variable.read', 'variable.create', 'variable.update', 'variable.delete',
        'repository.read', 'repository.add', 'repository.update', 'repository.remove',
        'build.read', 'build.create', 'build.trigger', 'build.cancel',
        'infra.read', 'infra.create', 'infra.trigger', 'infra.cancel',
        'test.read', 'test.create', 'test.trigger', 'test.cancel',
        'release.read', 'release.create', 'release.update', 'release.publish',
        'watch.read', 'watch.create', 'watch.update', 'watch.delete',
    },
    ProjectRole.ADMINISTRATOR: {
        'project.read', 'project.update',
        'member.read', 'member.add', 'member.remove', 'member.update',
        'resource.read', 'resource.assign', 'resource.unassign', 'resource.checkout',
        'variable.read', 'variable.create', 'variable.update', 'variable.delete',
        'repository.read', 'repository.add', 'repository.update', 'repository.remove',
        'build.read', 'build.create', 'build.trigger', 'build.cancel',
        'infra.read', 'infra.create', 'infra.trigger', 'infra.cancel',
        'test.read', 'test.create', 'test.trigger', 'test.cancel',
        'release.read', 'release.create', 'release.update', 'release.publish',
        'watch.read', 'watch.create', 'watch.update', 'watch.delete',
    },
    ProjectRole.DEVELOPER: {
        'project.read',
        'member.read',
        'resource.read', 'resource.checkout',
        'variable.read',
        'repository.read',
        'build.read', 'build.trigger',
        'infra.read', 'infra.trigger',
        'test.read', 'test.trigger',
        'release.read',
        'watch.read',
    },
    ProjectRole.VIEWER: {
        'project.read',
        'member.read',
        'resource.read',
        'variable.read',
        'repository.read',
        'build.read',
        'infra.read',
        'test.read',
        'release.read',
        'watch.read',
    },
}



# =============================================================================
# ProjectManager Class
# =============================================================================

class ProjectManager:
    """
    Manager class for project CRUD operations, membership management, resource assignment,
    and project variables.
    
    This class handles all project-related operations including:
    - Project creation with validation
    - Project retrieval by ID or name
    - Project updates
    - Project deletion with active job check
    - Membership management (add, remove, update role)
    - Resource assignment and unassignment
    - Project variable management
    - Permission checking
    
    Validates: Requirements 1.1-1.6, 2.1-2.6, 11.1-11.7, 14.1-14.4
    """
    
    # Mask value for sensitive variables
    SENSITIVE_MASK = "********"
    
    def __init__(self, db_session: DbSession, audit_logger=None):
        """
        Initialize the ProjectManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def validate_project_name(self, name: str) -> bool:
        """
        Validate that a project name contains only alphanumeric characters, underscores, hyphens, and periods.
        
        :param name: The project name to validate
        :returns: True if valid, False otherwise
        
        Validates: Requirements 1.6
        """
        return validate_project_name(name)
    
    def _validate_project_create_request(self, request: ProjectCreateRequest) -> None:
        """
        Validate a project creation request.
        
        :param request: The project creation request to validate
        :raises ProjectValidationError: If validation fails
        """
        if not self.validate_project_name(request.name):
            raise ProjectValidationError(
                "Project name must be 1-128 characters, start with alphanumeric, "
                "and contain only alphanumeric characters, underscores, hyphens, and periods",
                field="name",
                error_code="INVALID_PROJECT_NAME"
            )
    
    # =========================================================================
    # Project CRUD Operations
    # =========================================================================
    
    def create_project(self, request: ProjectCreateRequest, user_id: str) -> ProjectResponse:
        """
        Create a new project with the user as owner.
        
        :param request: The project creation request containing project data
        :param user_id: The ID of the user creating the project (becomes owner)
        :returns: ProjectResponse with the created project data
        :raises ProjectValidationError: If validation fails
        :raises DuplicateProjectError: If project name already exists
        
        Validates: Requirements 1.1, 1.2, 1.6
        """
        from ccai.pychestrate.core.orm import Project, ProjectMember, User
        
        # Validate the request
        self._validate_project_create_request(request)
        
        # Check for duplicate name
        existing_project = self._db_session.query(Project).filter(
            Project.name == request.name
        ).first()
        
        if existing_project:
            raise DuplicateProjectError(
                f"Project with name '{request.name}' already exists",
                field="name"
            )
        
        # Verify user exists
        user = self._db_session.query(User).filter(User.id == user_id).first()
        if not user:
            raise ProjectValidationError(
                f"User with ID '{user_id}' not found",
                field="owner_id",
                error_code="USER_NOT_FOUND"
            )
        
        # Create the project
        now = utc_now()
        
        project = Project(
            name=request.name,
            description=request.description or "",
            owner_id=user_id,
            metadata_json=request.metadata,
            created_at=now,
            updated_at=now,
            last_activity_at=now
        )
        
        self._db_session.add(project)
        self._db_session.flush()  # Get the project ID
        
        # Add the owner as a member with owner role
        member = ProjectMember(
            project_id=project.id,
            user_id=user_id,
            role=ProjectRole.OWNER.value,
            joined_at=now
        )
        
        self._db_session.add(member)
        self._db_session.commit()
        
        # Log the project creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_created',
                user_id=str(user_id),
                details={
                    "project_id": project.id,
                    "project_name": project.name
                }
            )
        
        return self._project_to_response(project)
    
    def get_project(self, project_id: int) -> Optional[ProjectResponse]:
        """
        Get a project by ID.
        
        :param project_id: The project's unique identifier
        :returns: ProjectResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import Project
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            return None
        
        return self._project_to_response(project)
    
    def get_project_by_name(self, name: str) -> Optional[ProjectResponse]:
        """
        Get a project by name.
        
        :param name: The project name to search for
        :returns: ProjectResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import Project
        
        project = self._db_session.query(Project).filter(Project.name == name).first()
        
        if not project:
            return None
        
        return self._project_to_response(project)
    
    def update_project(self, project_id: int, request: ProjectUpdateRequest, user_id: str) -> ProjectResponse:
        """
        Update project information.
        
        :param project_id: The project's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: ProjectResponse with the updated project data
        :raises ProjectNotFoundError: If project is not found
        :raises ProjectValidationError: If validation fails
        :raises DuplicateProjectError: If new name already exists
        
        Validates: Requirements 1.3
        """
        from ccai.pychestrate.core.orm import Project
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Update name if provided
        if request.name is not None:
            if not self.validate_project_name(request.name):
                raise ProjectValidationError(
                    "Project name must be 1-128 characters, start with alphanumeric, "
                    "and contain only alphanumeric characters, underscores, hyphens, and periods",
                    field="name",
                    error_code="INVALID_PROJECT_NAME"
                )
            
            # Check for duplicate name (excluding current project)
            existing_project = self._db_session.query(Project).filter(
                Project.name == request.name,
                Project.id != project_id
            ).first()
            
            if existing_project:
                raise DuplicateProjectError(
                    f"Project with name '{request.name}' already exists",
                    field="name"
                )
            
            project.name = request.name
        
        # Update description if provided
        if request.description is not None:
            project.description = request.description
        
        # Update metadata if provided
        if request.metadata is not None:
            project.metadata_json = request.metadata
        
        project.updated_at = utc_now()
        self._db_session.commit()
        
        # Log the project update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_updated',
                user_id=str(user_id),
                details={
                    "project_id": project.id,
                    "project_name": project.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._project_to_response(project)
    
    def delete_project(self, project_id: int, user_id: str) -> None:
        """
        Delete a project. Fails if active jobs exist.
        
        :param project_id: The project's unique identifier
        :param user_id: The ID of the user deleting the project
        :raises ProjectNotFoundError: If project is not found
        :raises ProjectHasActiveJobsError: If project has active jobs
        
        Validates: Requirements 1.4
        """
        from ccai.pychestrate.core.orm import (
            Project, ProjectBuild, ProjectInfraJob, ProjectTestJob, ProjectJobStatus
        )
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check for active builds
        active_builds = self._db_session.query(ProjectBuild).filter(
            ProjectBuild.project_id == project_id,
            ProjectBuild.status.in_([ProjectJobStatus.PENDING.value, ProjectJobStatus.RUNNING.value, ProjectJobStatus.QUEUED.value])
        ).count()
        
        # Check for active infra jobs
        active_infra_jobs = self._db_session.query(ProjectInfraJob).filter(
            ProjectInfraJob.project_id == project_id,
            ProjectInfraJob.status.in_([ProjectJobStatus.PENDING.value, ProjectJobStatus.RUNNING.value, ProjectJobStatus.QUEUED.value])
        ).count()
        
        # Check for active test jobs
        active_test_jobs = self._db_session.query(ProjectTestJob).filter(
            ProjectTestJob.project_id == project_id,
            ProjectTestJob.status.in_([ProjectJobStatus.PENDING.value, ProjectJobStatus.RUNNING.value, ProjectJobStatus.QUEUED.value])
        ).count()
        
        total_active_jobs = active_builds + active_infra_jobs + active_test_jobs
        
        if total_active_jobs > 0:
            raise ProjectHasActiveJobsError(
                f"Cannot delete project '{project.name}' with {total_active_jobs} active job(s)"
            )
        
        project_name = project.name
        
        # Delete the project (cascades to members, variables, etc.)
        self._db_session.delete(project)
        self._db_session.commit()
        
        # Log the project deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "project_name": project_name
                }
            )
    
    def list_projects(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 50,
        search: str = None
    ) -> ProjectListResponse:
        """
        List projects the user has access to.
        
        :param user_id: The user's ID (for permission filtering)
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :param search: Optional search string for project name or description
        :returns: ProjectListResponse with paginated project list
        
        Validates: Requirements 1.5, 14.6
        """
        from ccai.pychestrate.core.orm import Project, ProjectMember
        from sqlalchemy import or_
        
        # Get projects where user is a member
        query = self._db_session.query(Project).join(
            ProjectMember, Project.id == ProjectMember.project_id
        ).filter(
            ProjectMember.user_id == user_id
        )
        
        # Apply search filter
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Project.name.ilike(search_pattern),
                    Project.description.ilike(search_pattern)
                )
            )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        projects = query.order_by(Project.name).offset(offset).limit(limit).all()
        
        return ProjectListResponse(
            projects=[self._project_to_response(project) for project in projects],
            total=total,
            offset=offset,
            limit=limit
        )

    
    # =========================================================================
    # Membership Management
    # =========================================================================
    
    def add_member(
        self,
        project_id: int,
        user_id: str,
        role: ProjectRole,
        added_by: str
    ) -> ProjectMemberResponse:
        """
        Add a user to a project with specified role.
        
        :param project_id: The project's unique identifier
        :param user_id: The user's unique identifier to add
        :param role: The role to assign to the user
        :param added_by: The ID of the user adding the member
        :returns: ProjectMemberResponse with the member data
        :raises ProjectNotFoundError: If project is not found
        :raises DuplicateMemberError: If user is already a member
        
        Validates: Requirements 14.1
        """
        from ccai.pychestrate.core.orm import Project, ProjectMember, User
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Verify user exists
        user = self._db_session.query(User).filter(User.id == user_id).first()
        if not user:
            raise ProjectValidationError(
                f"User with ID '{user_id}' not found",
                field="user_id",
                error_code="USER_NOT_FOUND"
            )
        
        # Check if user is already a member
        existing_member = self._db_session.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id
        ).first()
        
        if existing_member:
            raise DuplicateMemberError(
                f"User '{user.login}' is already a member of project '{project.name}'"
            )
        
        # Create the membership
        now = utc_now()
        
        member = ProjectMember(
            project_id=project_id,
            user_id=user_id,
            role=role.value,
            joined_at=now
        )
        
        self._db_session.add(member)
        
        # Update project activity
        project.last_activity_at = now
        
        self._db_session.commit()
        
        # Log the member addition event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_member_added',
                user_id=str(added_by),
                details={
                    "project_id": project_id,
                    "project_name": project.name,
                    "member_user_id": str(user_id),
                    "member_username": user.login,
                    "role": role.value
                }
            )
        
        return ProjectMemberResponse(
            user_id=str(user.id),
            username=user.login,
            display_name=user.display_name or "",
            role=role,
            joined_at=member.joined_at
        )
    
    def remove_member(self, project_id: int, user_id: str, removed_by: str) -> None:
        """
        Remove a user from a project.
        
        :param project_id: The project's unique identifier
        :param user_id: The user's unique identifier to remove
        :param removed_by: The ID of the user removing the member
        :raises ProjectNotFoundError: If project is not found
        :raises MemberNotFoundError: If user is not a member
        :raises ProjectValidationError: If trying to remove the owner
        
        Validates: Requirements 14.2
        """
        from ccai.pychestrate.core.orm import Project, ProjectMember, User
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check if user is a member
        member = self._db_session.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id
        ).first()
        
        if not member:
            raise MemberNotFoundError(
                f"User with ID '{user_id}' is not a member of project '{project.name}'"
            )
        
        # Cannot remove the owner
        if member.role == ProjectRole.OWNER.value:
            raise ProjectValidationError(
                "Cannot remove the project owner",
                field="user_id",
                error_code="CANNOT_REMOVE_OWNER"
            )
        
        # Get user info for logging
        user = self._db_session.query(User).filter(User.id == user_id).first()
        username = user.login if user else str(user_id)
        
        # Remove the membership
        self._db_session.delete(member)
        
        # Update project activity
        project.last_activity_at = utc_now()
        
        self._db_session.commit()
        
        # Log the member removal event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_member_removed',
                user_id=str(removed_by),
                details={
                    "project_id": project_id,
                    "project_name": project.name,
                    "member_user_id": str(user_id),
                    "member_username": username
                }
            )
    
    def update_member_role(
        self,
        project_id: int,
        user_id: str,
        role: ProjectRole,
        updated_by: str
    ) -> ProjectMemberResponse:
        """
        Update a member's role in the project.
        
        :param project_id: The project's unique identifier
        :param user_id: The user's unique identifier
        :param role: The new role to assign
        :param updated_by: The ID of the user updating the role
        :returns: ProjectMemberResponse with the updated member data
        :raises ProjectNotFoundError: If project is not found
        :raises MemberNotFoundError: If user is not a member
        :raises ProjectValidationError: If trying to change owner role
        
        Validates: Requirements 14.3
        """
        from ccai.pychestrate.core.orm import Project, ProjectMember, User
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check if user is a member
        member = self._db_session.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id
        ).first()
        
        if not member:
            raise MemberNotFoundError(
                f"User with ID '{user_id}' is not a member of project '{project.name}'"
            )
        
        # Cannot change owner role
        if member.role == ProjectRole.OWNER.value:
            raise ProjectValidationError(
                "Cannot change the project owner's role",
                field="role",
                error_code="CANNOT_CHANGE_OWNER_ROLE"
            )
        
        old_role = member.role
        member.role = role.value
        
        # Update project activity
        project.last_activity_at = utc_now()
        
        self._db_session.commit()
        
        # Get user info for response
        user = self._db_session.query(User).filter(User.id == user_id).first()
        
        # Log the role update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_member_role_updated',
                user_id=str(updated_by),
                details={
                    "project_id": project_id,
                    "project_name": project.name,
                    "member_user_id": str(user_id),
                    "member_username": user.login if user else str(user_id),
                    "old_role": old_role,
                    "new_role": role.value
                }
            )
        
        return ProjectMemberResponse(
            user_id=str(user.id) if user else str(user_id),
            username=user.login if user else "",
            display_name=user.display_name if user else "",
            role=role,
            joined_at=member.joined_at
        )
    
    def list_members(
        self,
        project_id: int,
        offset: int = 0,
        limit: int = 50
    ) -> ProjectMemberListResponse:
        """
        List project members.
        
        :param project_id: The project's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: ProjectMemberListResponse with paginated member list
        :raises ProjectNotFoundError: If project is not found
        """
        from ccai.pychestrate.core.orm import Project, ProjectMember, User
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        query = self._db_session.query(ProjectMember).filter(
            ProjectMember.project_id == project_id
        )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        members = query.offset(offset).limit(limit).all()
        
        result = []
        for member in members:
            user = self._db_session.query(User).filter(User.id == member.user_id).first()
            result.append(ProjectMemberResponse(
                user_id=str(member.user_id),
                username=user.login if user else "",
                display_name=user.display_name if user else "",
                role=ProjectRole(member.role),
                joined_at=member.joined_at
            ))
        
        return ProjectMemberListResponse(
            members=result,
            total=total,
            offset=offset,
            limit=limit
        )
    
    def check_permission(self, project_id: int, user_id: str, permission: str) -> bool:
        """
        Check if user has permission on project.

        Accepts two kinds of ``permission`` values:

        * **Role-level shortcuts** used by the legacy web UI routes:
          ``'view'`` (any project member), ``'admin'`` (administrator or
          owner), ``'owner'`` (owner only).
        * **Granular permission strings** defined in :data:`ROLE_PERMISSIONS`
          (e.g. ``'project.update'``, ``'build.trigger'``).

        :param project_id: The project's unique identifier
        :param user_id: The user's unique identifier
        :param permission: The permission to check.
        :returns: True if user has permission, False otherwise

        Validates: Requirements 14.4
        """
        from ccai.pychestrate.core.orm import ProjectMember

        # Check if user is a member
        member = self._db_session.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id
        ).first()

        if not member:
            return False

        role_str = member.role

        # --- Role-level shortcuts (used by the web-UI routes) ----------------
        if permission == "view":
            # Any role may view.
            rtnval = True
            return rtnval

        if permission == "developer":
            # Developer, administrator, or owner.
            rtnval = role_str in (
                ProjectRole.DEVELOPER.value,
                ProjectRole.ADMINISTRATOR.value,
                ProjectRole.OWNER.value,
            )
            return rtnval

        if permission == "admin":
            # Administrator or owner.
            rtnval = role_str in (
                ProjectRole.ADMINISTRATOR.value,
                ProjectRole.OWNER.value,
            )
            return rtnval

        if permission == "owner":
            # Owner only.
            rtnval = role_str == ProjectRole.OWNER.value
            return rtnval

        # --- Granular permission string check ---------------------------------
        try:
            role = ProjectRole(role_str)
        except ValueError:
            return False

        role_permissions = ROLE_PERMISSIONS.get(role, set())
        rtnval = permission in role_permissions
        return rtnval

    
    # =========================================================================
    # Resource Assignment
    # =========================================================================
    
    def assign_resource(self, project_id: int, resource_id: int, user_id: str) -> None:
        """
        Assign a resource to the project.
        
        :param project_id: The project's unique identifier
        :param resource_id: The resource's unique identifier
        :param user_id: The ID of the user assigning the resource
        :raises ProjectNotFoundError: If project is not found
        :raises ResourceNotFoundError: If resource is not found
        :raises ResourceAlreadyAssignedError: If resource is already assigned
        
        Validates: Requirements 2.1, 2.3
        """
        from ccai.pychestrate.core.orm import Project, Resource, project_resources
        from sqlalchemy import insert, select
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Verify resource exists
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        # Check if resource is already assigned
        existing = self._db_session.execute(
            select(project_resources).where(
                project_resources.c.proj_id == project_id,
                project_resources.c.res_id == resource_id
            )
        ).first()
        
        if existing:
            raise ResourceAlreadyAssignedError(
                f"Resource '{resource.name}' is already assigned to project '{project.name}'"
            )
        
        # Create the assignment
        now = utc_now()
        
        self._db_session.execute(
            insert(project_resources).values(
                proj_id=project_id,
                res_id=resource_id,
                assigned_at=now,
                assigned_by_id=user_id
            )
        )
        
        # Update project activity
        project.last_activity_at = now
        
        self._db_session.commit()
        
        # Log the resource assignment event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_resource_assigned',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "project_name": project.name,
                    "resource_id": resource_id,
                    "resource_name": resource.name
                }
            )
    
    def unassign_resource(self, project_id: int, resource_id: int, user_id: str) -> None:
        """
        Remove resource assignment from project.
        
        :param project_id: The project's unique identifier
        :param resource_id: The resource's unique identifier
        :param user_id: The ID of the user unassigning the resource
        :raises ProjectNotFoundError: If project is not found
        :raises ResourceNotAssignedError: If resource is not assigned
        
        Validates: Requirements 2.2
        """
        from ccai.pychestrate.core.orm import Project, Resource, project_resources
        from sqlalchemy import delete, select
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check if resource is assigned
        existing = self._db_session.execute(
            select(project_resources).where(
                project_resources.c.proj_id == project_id,
                project_resources.c.res_id == resource_id
            )
        ).first()
        
        if not existing:
            raise ResourceNotAssignedError(
                f"Resource with ID '{resource_id}' is not assigned to project '{project.name}'"
            )
        
        # Get resource name for logging
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        resource_name = resource.name if resource else str(resource_id)
        
        # Remove the assignment
        self._db_session.execute(
            delete(project_resources).where(
                project_resources.c.proj_id == project_id,
                project_resources.c.res_id == resource_id
            )
        )
        
        # Update project activity
        project.last_activity_at = utc_now()
        
        self._db_session.commit()
        
        # Log the resource unassignment event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_resource_unassigned',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "project_name": project.name,
                    "resource_id": resource_id,
                    "resource_name": resource_name
                }
            )
    
    def list_assigned_resources(
        self,
        project_id: int,
        offset: int = 0,
        limit: int = 50
    ) -> AssignedResourceListResponse:
        """
        List resources assigned to project.
        
        :param project_id: The project's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: AssignedResourceListResponse with paginated resource list
        :raises ProjectNotFoundError: If project is not found
        
        Validates: Requirements 2.4
        """
        from ccai.pychestrate.core.orm import Project, Resource, ResourcePool, project_resources, Allocation, AllocationStatus
        from sqlalchemy import select, func
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Query assigned resources with assignment info
        query = self._db_session.execute(
            select(
                Resource,
                project_resources.c.assigned_at
            ).select_from(
                project_resources.join(Resource, project_resources.c.res_id == Resource.id)
            ).where(
                project_resources.c.proj_id == project_id
            )
        )
        
        all_results = query.fetchall()
        total = len(all_results)
        
        # Apply pagination
        paginated_results = all_results[offset:offset + limit]
        
        result = []
        for resource, assigned_at in paginated_results:
            # Get pool info
            pool = self._db_session.query(ResourcePool).filter(
                ResourcePool.id == resource.pool_id
            ).first() if resource.pool_id else None
            
            # Get current allocations count
            current_allocations = self._db_session.query(func.count(Allocation.id)).filter(
                Allocation.resource_id == resource.id,
                Allocation.status == AllocationStatus.ACTIVE.value
            ).scalar() or 0
            
            result.append(AssignedResourceResponse(
                resource_id=resource.id,
                resource_name=resource.name,
                resource_type=resource.resource_type,
                pool_id=resource.pool_id,
                pool_name=pool.name if pool else None,
                health_status=resource.health_status,
                current_allocations=current_allocations,
                capacity=resource.capacity,
                assigned_at=assigned_at
            ))
        
        return AssignedResourceListResponse(
            resources=result,
            total=total,
            offset=offset,
            limit=limit
        )
    
    def is_resource_assigned(self, project_id: int, resource_id: int) -> bool:
        """
        Check if resource is assigned to project.
        
        :param project_id: The project's unique identifier
        :param resource_id: The resource's unique identifier
        :returns: True if resource is assigned, False otherwise
        
        Validates: Requirements 2.6
        """
        from ccai.pychestrate.core.orm import project_resources
        from sqlalchemy import select
        
        existing = self._db_session.execute(
            select(project_resources).where(
                project_resources.c.proj_id == project_id,
                project_resources.c.res_id == resource_id
            )
        ).first()
        
        return existing is not None

    
    # =========================================================================
    # Project Variables
    # =========================================================================
    
    def create_variable(
        self,
        project_id: int,
        request: ProjectVariableCreateRequest,
        user_id: str
    ) -> ProjectVariableResponse:
        """
        Create a project variable.
        
        :param project_id: The project's unique identifier
        :param request: The variable creation request
        :param user_id: The ID of the user creating the variable
        :returns: ProjectVariableResponse with the created variable data
        :raises ProjectNotFoundError: If project is not found
        :raises DuplicateVariableError: If variable name already exists
        :raises TypeValidationError: If value doesn't match type
        
        Validates: Requirements 11.1, 11.4
        """
        from ccai.pychestrate.core.orm import Project, ProjectVariable
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Validate name
        if not request.name or len(request.name.strip()) == 0:
            raise ProjectValidationError("Variable name is required", field="name")
        
        if len(request.name) > 128:
            raise ProjectValidationError(
                "Variable name must be 128 characters or less",
                field="name"
            )
        
        # Validate type
        valid_types = {'string', 'integer', 'float', 'boolean', 'json'}
        if request.var_type not in valid_types:
            raise ProjectValidationError(
                f"Variable type must be one of: {', '.join(sorted(valid_types))}",
                field="var_type"
            )
        
        # Validate value type
        if not validate_variable_value(request.value, request.var_type):
            raise TypeValidationError(
                f"Value does not match type '{request.var_type}'",
                expected_type=request.var_type,
                actual_type=type(request.value).__name__
            )
        
        # Check for duplicate name
        existing = self._db_session.query(ProjectVariable).filter(
            ProjectVariable.project_id == project_id,
            ProjectVariable.name == request.name
        ).first()
        
        if existing:
            raise DuplicateVariableError(
                f"Variable '{request.name}' already exists in project '{project.name}'"
            )
        
        # Create the variable
        now = utc_now()
        
        variable = ProjectVariable(
            project_id=project_id,
            name=request.name,
            value_json=serialize_variable_value(request.value),
            var_type=request.var_type,
            is_sensitive=request.is_sensitive,
            description=request.description or "",
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(variable)
        
        # Update project activity
        project.last_activity_at = now
        
        self._db_session.commit()
        
        # Log the variable creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_variable_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "project_name": project.name,
                    "variable_name": request.name,
                    "variable_type": request.var_type,
                    "is_sensitive": request.is_sensitive
                }
            )
        
        return self._variable_to_response(variable, include_sensitive=True)
    
    def update_variable(
        self,
        project_id: int,
        variable_id: int,
        request: ProjectVariableUpdateRequest,
        user_id: str
    ) -> ProjectVariableResponse:
        """
        Update a project variable value.
        
        :param project_id: The project's unique identifier
        :param variable_id: The variable's unique identifier
        :param request: The update request
        :param user_id: The ID of the user updating the variable
        :returns: ProjectVariableResponse with the updated variable data
        :raises ProjectNotFoundError: If project is not found
        :raises VariableNotFoundError: If variable is not found
        :raises TypeValidationError: If value doesn't match type
        
        Validates: Requirements 11.2
        """
        from ccai.pychestrate.core.orm import Project, ProjectVariable
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        variable = self._db_session.query(ProjectVariable).filter(
            ProjectVariable.id == variable_id,
            ProjectVariable.project_id == project_id
        ).first()
        
        if not variable:
            raise VariableNotFoundError(
                f"Variable with ID '{variable_id}' not found in project '{project.name}'"
            )
        
        # Validate value type
        if not validate_variable_value(request.value, variable.var_type):
            raise TypeValidationError(
                f"Value does not match type '{variable.var_type}'",
                expected_type=variable.var_type,
                actual_type=type(request.value).__name__
            )
        
        # Update the variable
        variable.value_json = serialize_variable_value(request.value)
        
        if request.description is not None:
            variable.description = request.description
        
        variable.updated_at = utc_now()
        
        # Update project activity
        project.last_activity_at = utc_now()
        
        self._db_session.commit()
        
        # Log the variable update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_variable_updated',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "project_name": project.name,
                    "variable_name": variable.name
                }
            )
        
        return self._variable_to_response(variable, include_sensitive=True)
    
    def delete_variable(self, project_id: int, variable_id: int, user_id: str) -> None:
        """
        Delete a project variable.
        
        :param project_id: The project's unique identifier
        :param variable_id: The variable's unique identifier
        :param user_id: The ID of the user deleting the variable
        :raises ProjectNotFoundError: If project is not found
        :raises VariableNotFoundError: If variable is not found
        
        Validates: Requirements 11.3
        """
        from ccai.pychestrate.core.orm import Project, ProjectVariable
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        variable = self._db_session.query(ProjectVariable).filter(
            ProjectVariable.id == variable_id,
            ProjectVariable.project_id == project_id
        ).first()
        
        if not variable:
            raise VariableNotFoundError(
                f"Variable with ID '{variable_id}' not found in project '{project.name}'"
            )
        
        variable_name = variable.name
        
        # Delete the variable
        self._db_session.delete(variable)
        
        # Update project activity
        project.last_activity_at = utc_now()
        
        self._db_session.commit()
        
        # Log the variable deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='project_variable_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "project_name": project.name,
                    "variable_name": variable_name
                }
            )
    
    def list_variables(
        self,
        project_id: int,
        include_sensitive: bool = False,
        offset: int = 0,
        limit: int = 50
    ) -> ProjectVariableListResponse:
        """
        List project variables.
        
        :param project_id: The project's unique identifier
        :param include_sensitive: If True, include sensitive variable values (otherwise masked)
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: ProjectVariableListResponse with paginated variable list
        :raises ProjectNotFoundError: If project is not found
        """
        from ccai.pychestrate.core.orm import Project, ProjectVariable
        
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        query = self._db_session.query(ProjectVariable).filter(
            ProjectVariable.project_id == project_id
        )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        variables = query.order_by(ProjectVariable.name).offset(offset).limit(limit).all()
        
        return ProjectVariableListResponse(
            variables=[self._variable_to_response(var, include_sensitive) for var in variables],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def resolve_variable(self, project_id: int, name: str) -> Any:
        """
        Resolve variable value, checking project then global scope.
        
        :param project_id: The project's unique identifier
        :param name: The variable name to resolve
        :returns: The variable value, or None if not found
        
        Validates: Requirements 11.5
        """
        from ccai.pychestrate.core.orm import ProjectVariable, GlobalVariable
        
        # First check project variables
        project_var = self._db_session.query(ProjectVariable).filter(
            ProjectVariable.project_id == project_id,
            ProjectVariable.name == name
        ).first()
        
        if project_var:
            return deserialize_variable_value(project_var.value_json, project_var.var_type)
        
        # Then check global variables
        global_var = self._db_session.query(GlobalVariable).filter(
            GlobalVariable.name == name
        ).first()
        
        if global_var:
            return deserialize_variable_value(global_var.value_json, global_var.var_type)
        
        return None

    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _project_to_response(self, project) -> ProjectResponse:
        """
        Convert a Project ORM object to a ProjectResponse dataclass.
        
        :param project: The Project ORM object
        :returns: ProjectResponse dataclass
        """
        from ccai.pychestrate.core.orm import (
            User, ProjectMember, ProjectRepository, ProjectBuild, 
            ProjectInfraJob, ProjectTestJob, ProjectJobStatus
        )
        from sqlalchemy import func
        
        # Get owner info
        owner = self._db_session.query(User).filter(User.id == project.owner_id).first()
        
        # Get member count
        member_count = self._db_session.query(func.count(ProjectMember.id)).filter(
            ProjectMember.project_id == project.id
        ).scalar() or 0
        
        # Get repository count
        repository_count = self._db_session.query(func.count(ProjectRepository.id)).filter(
            ProjectRepository.project_id == project.id
        ).scalar() or 0
        
        # Get active jobs count
        active_builds = self._db_session.query(func.count(ProjectBuild.id)).filter(
            ProjectBuild.project_id == project.id,
            ProjectBuild.status.in_([ProjectJobStatus.PENDING.value, ProjectJobStatus.RUNNING.value, ProjectJobStatus.QUEUED.value])
        ).scalar() or 0
        
        active_infra_jobs = self._db_session.query(func.count(ProjectInfraJob.id)).filter(
            ProjectInfraJob.project_id == project.id,
            ProjectInfraJob.status.in_([ProjectJobStatus.PENDING.value, ProjectJobStatus.RUNNING.value, ProjectJobStatus.QUEUED.value])
        ).scalar() or 0
        
        active_test_jobs = self._db_session.query(func.count(ProjectTestJob.id)).filter(
            ProjectTestJob.project_id == project.id,
            ProjectTestJob.status.in_([ProjectJobStatus.PENDING.value, ProjectJobStatus.RUNNING.value, ProjectJobStatus.QUEUED.value])
        ).scalar() or 0
        
        active_jobs = active_builds + active_infra_jobs + active_test_jobs
        
        return ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description or "",
            owner_id=str(project.owner_id),
            owner_username=owner.login if owner else "",
            metadata=project.metadata_json or {},
            created_at=project.created_at,
            updated_at=project.updated_at,
            last_activity_at=project.last_activity_at,
            member_count=member_count,
            repository_count=repository_count,
            active_jobs=active_jobs
        )
    
    def _variable_to_response(self, variable, include_sensitive: bool = False) -> ProjectVariableResponse:
        """
        Convert a ProjectVariable ORM object to a ProjectVariableResponse dataclass.
        
        :param variable: The ProjectVariable ORM object
        :param include_sensitive: If True, include sensitive variable values
        :returns: ProjectVariableResponse dataclass
        """
        value = deserialize_variable_value(variable.value_json, variable.var_type)
        
        # Mask sensitive values if not including them
        if variable.is_sensitive and not include_sensitive:
            value = self.SENSITIVE_MASK
        
        return ProjectVariableResponse(
            id=variable.id,
            name=variable.name,
            value=value,
            var_type=variable.var_type,
            is_sensitive=variable.is_sensitive,
            description=variable.description or "",
            created_at=variable.created_at,
            updated_at=variable.updated_at
        )
