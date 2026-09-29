"""
.. module:: build_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the BuildManager class for build specification CRUD operations and build execution

.. moduleauthor:: Code Craft AI LLC

This module provides the BuildManager class which handles:
- Build specification CRUD operations (Requirements 4.1, 4.2, 4.3, 4.4, 4.5)
- Build execution and tracking (Requirements 5.1, 5.3, 5.4, 5.5, 5.6)
- Artifact management (Requirements 5.7)
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import re

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession
from sqlalchemy import or_

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.managers.git_validation import (
    commit_sha_problem,
    ref_name_problem,
)


_module_logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class BuildTriggerType(str, Enum):
    """
        Enum-like class to represent the trigger types for builds.
    """
    MANUAL = 'manual'
    WEBHOOK = 'webhook'
    SCHEDULE = 'schedule'
    WATCH = 'watch'
    API = 'api'


class JobStatus(str, Enum):
    """
        Enum-like class to represent the status of jobs.
    """
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class BuildStepDefinition:
    """Definition of a build step."""
    name: str
    type: str  # checkout, script, artifact, notification
    config: Dict[str, Any]
    continue_on_failure: bool = False


@dataclass
class BuildSpecCreateRequest:
    """Request dataclass for creating a new build specification."""
    name: str
    repository_id: int
    branch: str = "main"
    steps: List[Dict[str, Any]] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    timeout_minutes: int = 60
    description: str = ""


@dataclass
class BuildSpecUpdateRequest:
    """Request dataclass for updating an existing build specification."""
    name: Optional[str] = None
    repository_id: Optional[int] = None
    branch: Optional[str] = None
    steps: Optional[List[Dict[str, Any]]] = None
    environment: Optional[Dict[str, str]] = None
    timeout_minutes: Optional[int] = None
    description: Optional[str] = None


@dataclass
class BuildSpecResponse:
    """Response dataclass for build specification data."""
    id: int
    project_id: int
    name: str
    repository_id: int
    repository_name: str
    branch: str
    steps: List[Dict[str, Any]]
    environment: Dict[str, str]
    timeout_minutes: int
    description: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass
class BuildSpecListResponse:
    """Response dataclass for paginated build specification list."""
    specs: List[BuildSpecResponse]
    total: int
    offset: int
    limit: int


@dataclass
class BuildTriggerRequest:
    """Request dataclass for triggering a build."""
    spec_id: int
    branch: Optional[str] = None  # Override spec branch
    commit_sha: Optional[str] = None  # Specific commit
    parameters: Dict[str, Any] = field(default_factory=dict)
    trigger_type: BuildTriggerType = BuildTriggerType.MANUAL


@dataclass
class BuildResponse:
    """Response dataclass for build data."""
    id: int
    project_id: int
    spec_id: int
    spec_name: str
    spec_version: int
    repository_name: str
    branch: str
    commit_sha: str
    commit_message: Optional[str]
    status: JobStatus
    trigger_type: BuildTriggerType
    triggered_by_id: str
    triggered_by_username: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    artifact_count: int
    created_at: datetime


@dataclass
class BuildListResponse:
    """Response dataclass for paginated build list."""
    builds: List[BuildResponse]
    total: int
    offset: int
    limit: int


@dataclass
class BuildArtifactResponse:
    """Response dataclass for build artifact data."""
    id: int
    build_id: int
    name: str
    path: str
    size_bytes: int
    checksum: str
    checksum_algorithm: str
    created_at: datetime


@dataclass
class BuildArtifactListResponse:
    """Response dataclass for paginated build artifact list."""
    artifacts: List[BuildArtifactResponse]
    total: int


# =============================================================================
# Exceptions
# =============================================================================

class BuildSpecValidationError(Exception):
    """Exception raised when build specification validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "VALIDATION_ERROR"
        super().__init__(self.message)


class BuildValidationError(Exception):
    """Exception raised when a build request or result is not valid."""

    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "BUILD_VALIDATION_ERROR"
        super().__init__(self.message)


class BuildSpecNotFoundError(Exception):
    """Exception raised when a build specification is not found."""
    
    def __init__(self, message: str, error_code: str = "BUILD_SPEC_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateBuildSpecError(Exception):
    """Exception raised when attempting to create a build specification with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "BUILD_SPEC_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class BuildSpecHasActiveBuildsError(Exception):
    """Exception raised when attempting to delete a build specification with active builds."""

    def __init__(self, message: str, error_code: str = "BUILD_SPEC_HAS_ACTIVE_BUILDS"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class BuildSpecInUseError(Exception):
    """Exception raised when attempting to delete a build specification that watches still use."""

    def __init__(self, message: str, error_code: str = "BUILD_SPEC_IN_USE"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ProjectNotFoundError(Exception):
    """Exception raised when a project is not found."""
    
    def __init__(self, message: str, error_code: str = "PROJECT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class RepositoryNotFoundError(Exception):
    """Exception raised when a repository is not found."""
    
    def __init__(self, message: str, error_code: str = "REPOSITORY_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class BuildNotFoundError(Exception):
    """Exception raised when a build is not found."""
    
    def __init__(self, message: str, error_code: str = "BUILD_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class BuildCannotBeCancelledError(Exception):
    """Exception raised when a build cannot be cancelled."""

    def __init__(self, message: str, error_code: str = "BUILD_CANNOT_BE_CANCELLED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class BuildAlreadyFinishedError(Exception):
    """Exception raised when the outcome of a build that already finished is reported."""

    def __init__(self, message: str, error_code: str = "BUILD_ALREADY_FINISHED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ArtifactNotFoundError(Exception):
    """Exception raised when an artifact is not found."""
    
    def __init__(self, message: str, error_code: str = "ARTIFACT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


# =============================================================================
# Validation Constants
# =============================================================================

# Build spec name validation: alphanumeric, underscore, hyphen, period
# Must start with alphanumeric, 1-128 characters
BUILD_SPEC_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}\Z')

# Valid build step types
VALID_STEP_TYPES = {'checkout', 'script', 'artifact', 'notification'}


# =============================================================================
# Validation Functions
# =============================================================================

def validate_build_spec_name(name: str) -> bool:
    """
    Validate that a build specification name contains only alphanumeric characters,
    underscores, hyphens, and periods.
    
    :param name: The build specification name to validate
    :returns: True if valid, False otherwise
    """
    if not name:
        return False
    
    if not BUILD_SPEC_NAME_PATTERN.match(name):
        return False
    
    return True


def validate_build_steps(steps: List[Dict[str, Any]]) -> List[str]:
    """
    Validate build steps syntax.
    
    :param steps: List of build step definitions
    :returns: List of validation error messages (empty if valid)
    
    Validates: Requirements 4.4, 4.5
    """
    errors = []
    
    if not isinstance(steps, list):
        errors.append("Steps must be a list")
        return errors
    
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"Step {i}: must be a dictionary")
            continue
        
        # Check required fields
        if 'name' not in step:
            errors.append(f"Step {i}: missing required field 'name'")
        elif not isinstance(step['name'], str) or not step['name'].strip():
            errors.append(f"Step {i}: 'name' must be a non-empty string")
        
        if 'type' not in step:
            errors.append(f"Step {i}: missing required field 'type'")
        elif step['type'] not in VALID_STEP_TYPES:
            errors.append(f"Step {i}: invalid type '{step['type']}'. Must be one of: {', '.join(VALID_STEP_TYPES)}")
        
        # Check config field
        if 'config' in step and not isinstance(step.get('config'), dict):
            errors.append(f"Step {i}: 'config' must be a dictionary")
        
        # Check continue_on_failure field
        if 'continue_on_failure' in step and not isinstance(step.get('continue_on_failure'), bool):
            errors.append(f"Step {i}: 'continue_on_failure' must be a boolean")

    return errors


def normalize_build_steps(steps: Any) -> Any:
    """
    Return the build steps with every optional field present, so readers
    (the build-spec page, the build runner) never have to guess whether a
    key exists: ``config`` defaults to ``{}`` and ``continue_on_failure``
    to ``False``.

    Only the optional fields are filled; required fields (``name``,
    ``type``) are left to :func:`validate_build_steps`. Anything that is
    not a list of dictionaries is returned unchanged.

    :param steps: Build step definitions as stored or submitted.
    :returns: A new list of step dictionaries with the defaults applied.
    """
    if not isinstance(steps, list):
        return steps

    rtnval: List[Any] = []
    for step in steps:
        if not isinstance(step, dict):
            rtnval.append(step)
            continue
        normalized = dict(step)
        if normalized.get('config') is None:
            normalized['config'] = {}
        if normalized.get('continue_on_failure') is None:
            normalized['continue_on_failure'] = False
        rtnval.append(normalized)
    return rtnval



# =============================================================================
# BuildManager Class
# =============================================================================

class BuildManager:
    """
    Manager class for build specification CRUD operations and build execution.
    
    This class handles all build-related operations including:
    - Build specification creation with validation
    - Build specification retrieval by ID
    - Build specification updates with versioning
    - Build specification deletion with active build check
    - Build triggering and execution tracking
    - Build artifact management
    
    Validates: Requirements 4.1-4.5, 5.1, 5.3-5.7
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None, resource_manager=None, secret_manager=None,
                 event_sink=None):
        """
        Initialize the BuildManager with a database session.

        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        :param resource_manager: Optional ResourceManager instance for resource checkout
        :param secret_manager: Optional SecretManager instance for secret resolution
        :param event_sink: Optional callable
                           ``(*, trigger_source, source_id, event_data, user_id)``
                           returning the watch trigger logs, called when a
                           build finishes. Defaults to the project's watches
                           with the core action managers (see
                           :func:`watch_manager.dispatch_watch_event`).
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
        self._resource_manager = resource_manager
        self._secret_manager = secret_manager
        self._event_sink = event_sink
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def _validate_build_spec_create_request(self, request: BuildSpecCreateRequest) -> None:
        """
        Validate a build specification creation request.
        
        :param request: The build specification creation request to validate
        :raises BuildSpecValidationError: If validation fails
        """
        if not validate_build_spec_name(request.name):
            raise BuildSpecValidationError(
                "Build specification name must be 1-128 characters, start with alphanumeric, "
                "and contain only alphanumeric characters, underscores, hyphens, and periods",
                field="name",
                error_code="INVALID_BUILD_SPEC_NAME"
            )
        
        if request.timeout_minutes is not None and request.timeout_minutes <= 0:
            raise BuildSpecValidationError(
                "Timeout must be a positive integer",
                field="timeout_minutes",
                error_code="INVALID_TIMEOUT"
            )
        
        # Validate steps syntax
        step_errors = validate_build_steps(request.steps)
        if step_errors:
            raise BuildSpecValidationError(
                f"Invalid build steps: {'; '.join(step_errors)}",
                field="steps",
                error_code="INVALID_STEPS"
            )

        branch_problem = ref_name_problem(name=request.branch or "")
        if branch_problem is not None:
            raise BuildSpecValidationError(branch_problem, field="branch", error_code="INVALID_BRANCH")

    def validate_spec(self, spec: BuildSpecCreateRequest) -> List[str]:
        """
        Validate build specification syntax. Returns list of errors.
        
        :param spec: The build specification to validate
        :returns: List of validation error messages (empty if valid)
        
        Validates: Requirements 4.4
        """
        errors = []
        
        # Validate name
        if not validate_build_spec_name(spec.name):
            errors.append("Name must be 1-128 characters, start with alphanumeric, "
                         "and contain only alphanumeric characters, underscores, hyphens, and periods")
        
        # Validate timeout
        if spec.timeout_minutes is not None and spec.timeout_minutes <= 0:
            errors.append("Timeout must be a positive integer")
        
        # Validate steps
        step_errors = validate_build_steps(spec.steps)
        errors.extend(step_errors)
        
        # Validate environment
        if spec.environment:
            if not isinstance(spec.environment, dict):
                errors.append("Environment must be a dictionary")
            else:
                for key, value in spec.environment.items():
                    if not isinstance(key, str):
                        errors.append(f"Environment key '{key}' must be a string")
                    if not isinstance(value, str):
                        errors.append(f"Environment value for '{key}' must be a string")
        
        return errors
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _build_spec_to_response(self, spec) -> BuildSpecResponse:
        """
        Convert a ProjectBuildSpec ORM object to a BuildSpecResponse.
        
        :param spec: The ProjectBuildSpec ORM object
        :returns: BuildSpecResponse dataclass
        """
        repository_name = spec.repository.name if spec.repository else ""
        
        return BuildSpecResponse(
            id=spec.id,
            project_id=spec.project_id,
            name=spec.name,
            repository_id=spec.repository_id,
            repository_name=repository_name,
            branch=spec.branch,
            # Rows written before steps were normalized on save may lack
            # the optional fields; fill them here too.
            steps=normalize_build_steps(spec.steps_json or []),
            environment=spec.environment_json or {},
            timeout_minutes=spec.timeout_minutes,
            description=spec.description or "",
            version=spec.version,
            created_at=spec.created_at,
            updated_at=spec.updated_at
        )
    
    def _build_to_response(self, build) -> BuildResponse:
        """
        Convert a ProjectBuild ORM object to a BuildResponse.
        
        :param build: The ProjectBuild ORM object
        :returns: BuildResponse dataclass
        """
        from ccai.pychestrate.core.orm import User
        
        spec_name = build.spec.name if build.spec else ""
        repository_name = build.spec.repository.name if build.spec and build.spec.repository else ""
        
        # Get triggered by username
        triggered_by_username = ""
        if build.triggered_by_id:
            user = self._db_session.query(User).filter(User.id == build.triggered_by_id).first()
            if user:
                triggered_by_username = user.login
        
        # Count artifacts
        artifact_count = len(build.artifacts) if build.artifacts else 0
        
        return BuildResponse(
            id=build.id,
            project_id=build.project_id,
            spec_id=build.spec_id,
            spec_name=spec_name,
            spec_version=build.spec_version,
            repository_name=repository_name,
            branch=build.branch,
            commit_sha=build.commit_sha,
            commit_message=build.commit_message,
            status=JobStatus(build.status),
            trigger_type=BuildTriggerType(build.trigger_type),
            triggered_by_id=str(build.triggered_by_id),
            triggered_by_username=triggered_by_username,
            started_at=build.started_at,
            completed_at=build.completed_at,
            duration_seconds=build.duration_seconds,
            artifact_count=artifact_count,
            created_at=build.created_at
        )
    
    def _artifact_to_response(self, artifact) -> BuildArtifactResponse:
        """
        Convert a ProjectBuildArtifact ORM object to a BuildArtifactResponse.
        
        :param artifact: The ProjectBuildArtifact ORM object
        :returns: BuildArtifactResponse dataclass
        """
        return BuildArtifactResponse(
            id=artifact.id,
            build_id=artifact.build_id,
            name=artifact.name,
            path=artifact.path,
            size_bytes=artifact.size_bytes,
            checksum=artifact.checksum,
            checksum_algorithm=artifact.checksum_algorithm,
            created_at=artifact.created_at
        )
    
    # =========================================================================
    # Build Specification CRUD Operations
    # =========================================================================
    
    def create_spec(
        self,
        project_id: int,
        request: BuildSpecCreateRequest,
        user_id: str
    ) -> BuildSpecResponse:
        """
        Create a build specification.
        
        :param project_id: The project's unique identifier
        :param request: The build specification creation request
        :param user_id: The ID of the user creating the specification
        :returns: BuildSpecResponse with the created specification data
        :raises ProjectNotFoundError: If project is not found
        :raises RepositoryNotFoundError: If repository is not found
        :raises BuildSpecValidationError: If validation fails
        :raises DuplicateBuildSpecError: If specification name already exists in project
        
        Validates: Requirements 4.1
        """
        from ccai.pychestrate.core.orm import Project, ProjectRepository, ProjectBuildSpec
        
        # Validate the request
        self._validate_build_spec_create_request(request)
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Verify repository exists and belongs to project
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == request.repository_id,
            ProjectRepository.project_id == project_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(
                f"Repository with ID '{request.repository_id}' not found in project"
            )
        
        # Check for duplicate name within project
        existing_spec = self._db_session.query(ProjectBuildSpec).filter(
            ProjectBuildSpec.project_id == project_id,
            ProjectBuildSpec.name == request.name
        ).first()
        
        if existing_spec:
            raise DuplicateBuildSpecError(
                f"Build specification with name '{request.name}' already exists in project '{project.name}'",
                field="name"
            )
        
        # Create the build specification
        now = utc_now()
        
        spec = ProjectBuildSpec(
            project_id=project_id,
            repository_id=request.repository_id,
            name=request.name,
            branch=request.branch,
            steps_json=normalize_build_steps(request.steps),
            environment_json=request.environment,
            timeout_minutes=request.timeout_minutes,
            description=request.description or "",
            version=1,
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(spec)
        self._db_session.commit()
        
        # Log the specification creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='build_spec_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "spec_id": spec.id,
                    "spec_name": spec.name,
                    "repository_id": request.repository_id
                }
            )
        
        return self._build_spec_to_response(spec)
    
    def get_spec(self, spec_id: int) -> Optional[BuildSpecResponse]:
        """
        Get build specification by ID.
        
        :param spec_id: The build specification's unique identifier
        :returns: BuildSpecResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import ProjectBuildSpec
        
        spec = self._db_session.query(ProjectBuildSpec).filter(
            ProjectBuildSpec.id == spec_id
        ).first()
        
        if not spec:
            return None
        
        return self._build_spec_to_response(spec)
    
    def update_spec(
        self,
        spec_id: int,
        request: BuildSpecUpdateRequest,
        user_id: str
    ) -> BuildSpecResponse:
        """
        Update build specification (creates new version).
        
        :param spec_id: The build specification's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: BuildSpecResponse with the updated specification data
        :raises BuildSpecNotFoundError: If specification is not found
        :raises BuildSpecValidationError: If validation fails
        :raises DuplicateBuildSpecError: If new name already exists in project
        :raises RepositoryNotFoundError: If new repository is not found
        
        Validates: Requirements 4.2
        """
        from ccai.pychestrate.core.orm import ProjectBuildSpec, ProjectRepository
        
        spec = self._db_session.query(ProjectBuildSpec).filter(
            ProjectBuildSpec.id == spec_id
        ).first()
        
        if not spec:
            raise BuildSpecNotFoundError(f"Build specification with ID '{spec_id}' not found")
        
        old_version = spec.version
        
        # Update name if provided
        if request.name is not None:
            if not validate_build_spec_name(request.name):
                raise BuildSpecValidationError(
                    "Build specification name must be 1-128 characters, start with alphanumeric, "
                    "and contain only alphanumeric characters, underscores, hyphens, and periods",
                    field="name",
                    error_code="INVALID_BUILD_SPEC_NAME"
                )
            
            # Check for duplicate name (excluding current spec)
            existing_spec = self._db_session.query(ProjectBuildSpec).filter(
                ProjectBuildSpec.project_id == spec.project_id,
                ProjectBuildSpec.name == request.name,
                ProjectBuildSpec.id != spec_id
            ).first()
            
            if existing_spec:
                raise DuplicateBuildSpecError(
                    f"Build specification with name '{request.name}' already exists in this project",
                    field="name"
                )
            
            spec.name = request.name
        
        # Update repository_id if provided
        if request.repository_id is not None:
            repository = self._db_session.query(ProjectRepository).filter(
                ProjectRepository.id == request.repository_id,
                ProjectRepository.project_id == spec.project_id
            ).first()
            
            if not repository:
                raise RepositoryNotFoundError(
                    f"Repository with ID '{request.repository_id}' not found in project"
                )
            
            spec.repository_id = request.repository_id
        
        # Update branch if provided
        if request.branch is not None:
            branch_problem = ref_name_problem(name=request.branch)
            if branch_problem is not None:
                raise BuildSpecValidationError(branch_problem, field="branch", error_code="INVALID_BRANCH")
            spec.branch = request.branch
        
        # Update steps if provided
        if request.steps is not None:
            step_errors = validate_build_steps(request.steps)
            if step_errors:
                raise BuildSpecValidationError(
                    f"Invalid build steps: {'; '.join(step_errors)}",
                    field="steps",
                    error_code="INVALID_STEPS"
                )
            spec.steps_json = normalize_build_steps(request.steps)
        
        # Update environment if provided
        if request.environment is not None:
            spec.environment_json = request.environment
        
        # Update timeout if provided
        if request.timeout_minutes is not None:
            if request.timeout_minutes <= 0:
                raise BuildSpecValidationError(
                    "Timeout must be a positive integer",
                    field="timeout_minutes",
                    error_code="INVALID_TIMEOUT"
                )
            spec.timeout_minutes = request.timeout_minutes
        
        # Update description if provided
        if request.description is not None:
            spec.description = request.description
        
        # Increment version (Requirements 4.2)
        spec.version = old_version + 1
        spec.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the specification update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='build_spec_updated',
                user_id=str(user_id),
                details={
                    "spec_id": spec.id,
                    "spec_name": spec.name,
                    "old_version": old_version,
                    "new_version": spec.version,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._build_spec_to_response(spec)

    
    def spec_usage(self, spec_id: int) -> Dict[str, Any]:
        """
        What deleting a build specification would affect.

        :param spec_id: The build specification's unique identifier
        :returns: ``{"builds": n, "active_builds": n, "watches": [names]}``
                  -- its builds (deleted with it), those still pending or
                  running (which block deletion), and the watches that
                  start when it finishes or run it (which block deletion)
        """
        from ccai.pychestrate.core.orm import ProjectBuild, ProjectBuildSpec, ProjectJobStatus, ProjectWatch

        spec = self._db_session.query(ProjectBuildSpec).filter(
            ProjectBuildSpec.id == spec_id
        ).first()
        if not spec:
            raise BuildSpecNotFoundError(f"Build specification with ID '{spec_id}' not found")

        builds = self._db_session.query(ProjectBuild).filter(ProjectBuild.spec_id == spec_id).count()
        active_builds = self._db_session.query(ProjectBuild).filter(
            ProjectBuild.spec_id == spec_id,
            ProjectBuild.status.in_([
                ProjectJobStatus.PENDING.value,
                ProjectJobStatus.QUEUED.value,
                ProjectJobStatus.RUNNING.value
            ])
        ).count()

        watches: List[str] = []
        for watch in self._db_session.query(ProjectWatch).filter(
            ProjectWatch.project_id == spec.project_id
        ).order_by(ProjectWatch.name).all():
            started_by_spec = (
                watch.trigger_source == 'build_completion' and watch.source_id == spec_id
            )
            runs_spec = any(
                isinstance(action, dict)
                and action.get('action') == 'trigger_build'
                and action.get('target_id') == spec_id
                for action in (watch.actions_json or [])
            )
            if started_by_spec or runs_spec:
                watches.append(watch.name)

        rtnval = {"builds": builds, "active_builds": active_builds, "watches": watches}
        return rtnval

    def delete_spec(self, spec_id: int, user_id: str) -> Dict[str, int]:
        """
        Delete a build specification together with its builds and their
        artifacts. Test jobs that ran against those builds and test
        specifications that name it keep their history but lose the link.

        It is refused while builds are pending or running, and while
        watches start when it finishes or run it (they would fail) --
        the watches are named so they can be changed first.

        :param spec_id: The build specification's unique identifier
        :param user_id: The ID of the user deleting the specification
        :returns: ``{"builds": n}`` -- how many builds were deleted
        :raises BuildSpecNotFoundError: If specification is not found
        :raises BuildSpecHasActiveBuildsError: If specification has active builds
        :raises BuildSpecInUseError: If watches use the specification

        Validates: Requirements 4.3
        """
        from sqlalchemy import delete as sa_delete
        from sqlalchemy import select, update as sa_update

        from ccai.pychestrate.core.orm import (
            ProjectBuild, ProjectBuildArtifact, ProjectBuildSpec, ProjectTestJob, ProjectTestSpec,
        )

        usage = self.spec_usage(spec_id)
        spec = self._db_session.query(ProjectBuildSpec).filter(
            ProjectBuildSpec.id == spec_id
        ).first()
        spec_name = spec.name
        project_id = spec.project_id

        if usage["active_builds"] > 0:
            raise BuildSpecHasActiveBuildsError(
                f"The build specification '{spec_name}' cannot be deleted while "
                f"{usage['active_builds']} of its builds are waiting or running. "
                "Cancel them or wait for them to finish."
            )
        if len(usage["watches"]) > 0:
            raise BuildSpecInUseError(
                "The build specification '{}' cannot be deleted while watches use it: {}. "
                "Change or delete those watches first.".format(spec_name, ", ".join(usage["watches"]))
            )

        build_ids = select(ProjectBuild.id).where(ProjectBuild.spec_id == spec_id)
        artifact_paths = [
            row.path for row in self._db_session.query(ProjectBuildArtifact).filter(
                ProjectBuildArtifact.build_id.in_(build_ids)
            ).all() if row.path
        ]
        log_paths = [
            row.logs_path for row in self._db_session.query(ProjectBuild).filter(
                ProjectBuild.spec_id == spec_id
            ).all() if row.logs_path
        ]

        try:
            self._db_session.execute(
                sa_update(ProjectTestJob).where(ProjectTestJob.build_id.in_(build_ids)).values(build_id=None)
            )
            self._db_session.execute(
                sa_update(ProjectTestSpec).where(ProjectTestSpec.build_ref == spec_id).values(build_ref=None)
            )
            self._db_session.execute(
                sa_delete(ProjectBuildArtifact).where(ProjectBuildArtifact.build_id.in_(build_ids))
            )
            self._db_session.execute(sa_delete(ProjectBuild).where(ProjectBuild.spec_id == spec_id))
            self._db_session.execute(sa_delete(ProjectBuildSpec).where(ProjectBuildSpec.id == spec_id))
            self._db_session.commit()
        except Exception:
            self._db_session.rollback()
            raise
        self._db_session.expire_all()

        # The files go only after the rows did (best effort).
        for path in artifact_paths + log_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

        # Log the specification deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='build_spec_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "spec_id": spec_id,
                    "spec_name": spec_name,
                    "builds_deleted": usage["builds"]
                }
            )

        rtnval = {"builds": usage["builds"]}
        return rtnval
    
    def list_specs(
        self,
        project_id: int,
        offset: int = 0,
        limit: int = 50
    ) -> BuildSpecListResponse:
        """
        List build specifications in a project.
        
        :param project_id: The project's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: BuildSpecListResponse with paginated specification list
        """
        from ccai.pychestrate.core.orm import ProjectBuildSpec
        
        query = self._db_session.query(ProjectBuildSpec).filter(
            ProjectBuildSpec.project_id == project_id
        )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        specs = query.order_by(ProjectBuildSpec.name).offset(offset).limit(limit).all()
        
        return BuildSpecListResponse(
            specs=[self._build_spec_to_response(spec) for spec in specs],
            total=total,
            offset=offset,
            limit=limit
        )
    
    # =========================================================================
    # Build Execution Operations
    # =========================================================================
    
    def trigger_build(
        self,
        request: BuildTriggerRequest,
        user_id: str
    ) -> BuildResponse:
        """
        Trigger a new build.
        
        :param request: The build trigger request
        :param user_id: The ID of the user triggering the build
        :returns: BuildResponse with the created build data
        :raises BuildSpecNotFoundError: If specification is not found
        
        Validates: Requirements 5.1
        """
        from ccai.pychestrate.core.orm import ProjectBuildSpec, ProjectBuild, ProjectJobStatus
        
        # Get the build specification
        spec = self._db_session.query(ProjectBuildSpec).filter(
            ProjectBuildSpec.id == request.spec_id
        ).first()
        
        if not spec:
            raise BuildSpecNotFoundError(f"Build specification with ID '{request.spec_id}' not found")

        # A branch or commit that cannot exist is refused rather than
        # recorded (it used to accept "not-a-sha!!").
        if request.branch:
            branch_problem = ref_name_problem(name=request.branch)
            if branch_problem is not None:
                raise BuildValidationError(branch_problem, field="branch", error_code="INVALID_BRANCH")
        if request.commit_sha:
            sha_problem = commit_sha_problem(value=request.commit_sha)
            if sha_problem is not None:
                raise BuildValidationError(sha_problem, field="commit_sha", error_code="INVALID_COMMIT_SHA")

        # Determine branch and commit
        branch = request.branch if request.branch else spec.branch
        commit_sha = request.commit_sha if request.commit_sha else "HEAD"
        
        # Create the build record with status pending
        now = utc_now()
        
        build = ProjectBuild(
            project_id=spec.project_id,
            spec_id=spec.id,
            spec_version=spec.version,
            branch=branch,
            commit_sha=commit_sha,
            commit_message=None,
            status=ProjectJobStatus.PENDING.value,
            trigger_type=request.trigger_type.value,
            triggered_by_id=user_id,
            parameters_json=request.parameters,
            created_at=now
        )
        
        self._db_session.add(build)
        self._db_session.commit()
        
        # Log the build trigger event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='build_triggered',
                user_id=str(user_id),
                details={
                    "project_id": spec.project_id,
                    "spec_id": spec.id,
                    "spec_name": spec.name,
                    "build_id": build.id,
                    "branch": branch,
                    "trigger_type": request.trigger_type.value
                }
            )
        
        return self._build_to_response(build)
    
    def get_build(self, build_id: int) -> Optional[BuildResponse]:
        """
        Get build by ID.
        
        :param build_id: The build's unique identifier
        :returns: BuildResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import ProjectBuild
        
        build = self._db_session.query(ProjectBuild).filter(
            ProjectBuild.id == build_id
        ).first()
        
        if not build:
            return None
        
        return self._build_to_response(build)
    
    def cancel_build(self, build_id: int, user_id: str) -> BuildResponse:
        """
        Cancel a pending or running build.
        
        :param build_id: The build's unique identifier
        :param user_id: The ID of the user cancelling the build
        :returns: BuildResponse with the updated build data
        :raises BuildNotFoundError: If build is not found
        :raises BuildCannotBeCancelledError: If build cannot be cancelled
        
        Validates: Requirements 5.5
        """
        from ccai.pychestrate.core.orm import ProjectBuild, ProjectJobStatus
        
        build = self._db_session.query(ProjectBuild).filter(
            ProjectBuild.id == build_id
        ).first()
        
        if not build:
            raise BuildNotFoundError(f"Build with ID '{build_id}' not found")
        
        # Check if build can be cancelled
        cancellable_statuses = [
            ProjectJobStatus.PENDING.value,
            ProjectJobStatus.QUEUED.value,
            ProjectJobStatus.RUNNING.value
        ]
        
        if build.status not in cancellable_statuses:
            raise BuildCannotBeCancelledError(
                f"Build with status '{build.status}' cannot be cancelled"
            )
        
        # Update build status
        build.status = ProjectJobStatus.CANCELLED.value
        build.completed_at = utc_now()
        
        if build.started_at:
            build.duration_seconds = int((build.completed_at - build.started_at).total_seconds())
        
        self._db_session.commit()
        
        # Log the build cancellation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='build_cancelled',
                user_id=str(user_id),
                details={
                    "build_id": build.id,
                    "spec_id": build.spec_id,
                    "previous_status": build.status
                }
            )

        return self._build_to_response(build)

    def complete_build(
        self,
        build_id: int,
        status: JobStatus,
        user_id: Optional[str] = None
    ) -> BuildResponse:
        """
        Record that a build finished -- succeeded or failed -- and fire the
        project's build-completion watches for its specification. Whatever
        runs builds reports their outcome here. A cancelled build did not
        finish and fires nothing (see :meth:`cancel_build`).

        :param build_id: The build's unique identifier
        :param status: ``succeeded`` or ``failed``
        :param user_id: The user reporting the outcome, if any; the
                        watches' actions run as that user, otherwise as
                        the project owner
        :returns: BuildResponse with the updated build data
        :raises BuildValidationError: If ``status`` is not a finished status
        :raises BuildNotFoundError: If build is not found
        :raises BuildAlreadyFinishedError: If the build already finished
        """
        from ccai.pychestrate.core.orm import ProjectBuild, ProjectJobStatus

        status_value = status.value if isinstance(status, Enum) else str(status)
        if status_value not in (ProjectJobStatus.SUCCEEDED.value, ProjectJobStatus.FAILED.value):
            raise BuildValidationError(
                f"A build finishes as succeeded or failed, not '{status_value}'",
                field="status",
                error_code="INVALID_BUILD_RESULT"
            )

        build = self._db_session.query(ProjectBuild).filter(
            ProjectBuild.id == build_id
        ).first()

        if not build:
            raise BuildNotFoundError(f"Build with ID '{build_id}' not found")

        active_statuses = [
            ProjectJobStatus.PENDING.value,
            ProjectJobStatus.QUEUED.value,
            ProjectJobStatus.RUNNING.value
        ]
        if build.status not in active_statuses:
            raise BuildAlreadyFinishedError(
                f"Build with status '{build.status}' has already finished"
            )

        build.status = status_value
        build.completed_at = utc_now()
        if build.started_at:
            build.duration_seconds = int((build.completed_at - build.started_at).total_seconds())

        self._db_session.commit()

        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='build_completed',
                user_id=str(user_id) if user_id else 'system',
                details={
                    "build_id": build.id,
                    "spec_id": build.spec_id,
                    "status": status_value
                }
            )

        self._fire_build_completion(build=build, user_id=user_id)
        return self._build_to_response(build)

    def _fire_build_completion(self, *, build, user_id: Optional[str]) -> int:
        """
        Fire the build-completion watches of the build's specification.
        A failing watch never undoes the build's result: the error is
        logged.

        :param build: The finished ProjectBuild ORM object
        :param user_id: The user reporting the outcome, if any
        :returns: How many watches fired
        """
        from ccai.pychestrate.core.managers.watch_manager import (
            WatchTriggerSource, dispatch_watch_event,
        )

        event_data = {
            "build_id": build.id,
            "build_status": build.status,
            "spec_id": build.spec_id,
            "project_id": build.project_id,
            "branch": build.branch,
            "commit_sha": build.commit_sha,
        }
        try:
            if self._event_sink is not None:
                trigger_logs = self._event_sink(
                    trigger_source=WatchTriggerSource.BUILD_COMPLETION,
                    source_id=build.spec_id,
                    event_data=event_data,
                    user_id=user_id,
                )
            else:
                trigger_logs = dispatch_watch_event(
                    db_session=self._db_session,
                    trigger_source=WatchTriggerSource.BUILD_COMPLETION,
                    source_id=build.spec_id,
                    event_data=event_data,
                    user_id=user_id,
                )
        except Exception:
            _module_logger.exception(
                "pychestrate.build.watch_dispatch_failed build_id=%s", event_data["build_id"]
            )
            try:
                self._db_session.rollback()
            except Exception:
                pass
            trigger_logs = []
        rtnval = len(trigger_logs or [])
        return rtnval
    
    def list_builds(
        self,
        project_id: int = None,
        spec_id: int = None,
        status: JobStatus = None,
        offset: int = 0,
        limit: int = 50,
        project_ids: list = None
    ) -> BuildListResponse:
        """
        List builds with filtering.
        
        :param project_id: Optional project ID filter
        :param spec_id: Optional specification ID filter
        :param status: Optional status filter
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :param project_ids: Optional list of project IDs, any of which matches
            (one query across a person's projects; an empty list matches none)
        :returns: BuildListResponse with paginated build list
        
        Validates: Requirements 5.6
        """
        from ccai.pychestrate.core.orm import ProjectBuild
        
        query = self._db_session.query(ProjectBuild)
        
        # Apply filters
        if project_id is not None:
            query = query.filter(ProjectBuild.project_id == project_id)
        
        if project_ids is not None:
            query = query.filter(ProjectBuild.project_id.in_(list(project_ids)))
        
        if spec_id is not None:
            query = query.filter(ProjectBuild.spec_id == spec_id)
        
        if status is not None:
            query = query.filter(ProjectBuild.status == status.value)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (order by created_at descending for most recent first)
        builds = query.order_by(ProjectBuild.created_at.desc()).offset(offset).limit(limit).all()
        
        return BuildListResponse(
            builds=[self._build_to_response(build) for build in builds],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def get_build_logs(self, build_id: int, step_name: str = None) -> str:
        """
        Get build execution logs.
        
        :param build_id: The build's unique identifier
        :param step_name: Optional step name to filter logs
        :returns: Build logs as a string
        :raises BuildNotFoundError: If build is not found
        """
        from ccai.pychestrate.core.orm import ProjectBuild
        
        build = self._db_session.query(ProjectBuild).filter(
            ProjectBuild.id == build_id
        ).first()
        
        if not build:
            raise BuildNotFoundError(f"Build with ID '{build_id}' not found")
        
        # If logs_path is set, read from file
        if build.logs_path and os.path.exists(build.logs_path):
            try:
                with open(build.logs_path, 'r') as f:
                    logs = f.read()
                
                # Filter by step name if provided
                if step_name:
                    # Simple filtering - look for step markers
                    lines = logs.split('\n')
                    filtered_lines = []
                    in_step = False
                    for line in lines:
                        if f"[STEP: {step_name}]" in line:
                            in_step = True
                        elif "[STEP:" in line and in_step:
                            in_step = False
                        if in_step:
                            filtered_lines.append(line)
                    return '\n'.join(filtered_lines)
                
                return logs
            except IOError:
                return ""
        
        return ""

    
    # =========================================================================
    # Artifact Management Operations
    # =========================================================================
    
    def list_artifacts(self, build_id: int) -> BuildArtifactListResponse:
        """
        List artifacts produced by a build.
        
        :param build_id: The build's unique identifier
        :returns: BuildArtifactListResponse with artifact list
        :raises BuildNotFoundError: If build is not found
        
        Validates: Requirements 5.7
        """
        from ccai.pychestrate.core.orm import ProjectBuild, ProjectBuildArtifact
        
        build = self._db_session.query(ProjectBuild).filter(
            ProjectBuild.id == build_id
        ).first()
        
        if not build:
            raise BuildNotFoundError(f"Build with ID '{build_id}' not found")
        
        artifacts = self._db_session.query(ProjectBuildArtifact).filter(
            ProjectBuildArtifact.build_id == build_id
        ).order_by(ProjectBuildArtifact.name).all()
        
        return BuildArtifactListResponse(
            artifacts=[self._artifact_to_response(artifact) for artifact in artifacts],
            total=len(artifacts)
        )
    
    def get_artifact(self, artifact_id: int) -> Optional[BuildArtifactResponse]:
        """
        Get artifact metadata.
        
        :param artifact_id: The artifact's unique identifier
        :returns: BuildArtifactResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import ProjectBuildArtifact
        
        artifact = self._db_session.query(ProjectBuildArtifact).filter(
            ProjectBuildArtifact.id == artifact_id
        ).first()
        
        if not artifact:
            return None
        
        return self._artifact_to_response(artifact)
    
    def download_artifact(self, artifact_id: int) -> bytes:
        """
        Download artifact content.
        
        :param artifact_id: The artifact's unique identifier
        :returns: Artifact content as bytes
        :raises ArtifactNotFoundError: If artifact is not found or file doesn't exist
        """
        from ccai.pychestrate.core.orm import ProjectBuildArtifact
        
        artifact = self._db_session.query(ProjectBuildArtifact).filter(
            ProjectBuildArtifact.id == artifact_id
        ).first()
        
        if not artifact:
            raise ArtifactNotFoundError(f"Artifact with ID '{artifact_id}' not found")
        
        if not artifact.path or not os.path.exists(artifact.path):
            raise ArtifactNotFoundError(f"Artifact file not found at path '{artifact.path}'")
        
        try:
            with open(artifact.path, 'rb') as f:
                return f.read()
        except IOError as e:
            raise ArtifactNotFoundError(f"Failed to read artifact file: {str(e)}")
    
    def cleanup_old_builds(self, project_id: int, retention_days: int) -> int:
        """
        Remove builds older than retention period. Returns count removed.
        
        :param project_id: The project's unique identifier
        :param retention_days: Number of days to retain builds
        :returns: Number of builds removed
        
        Validates: Requirements 5.7
        """
        from ccai.pychestrate.core.orm import ProjectBuild, ProjectBuildArtifact, ProjectJobStatus
        
        cutoff_date = utc_now() - timedelta(days=retention_days)
        
        # Find builds to delete (only completed builds)
        completed_statuses = [
            ProjectJobStatus.SUCCEEDED.value,
            ProjectJobStatus.FAILED.value,
            ProjectJobStatus.CANCELLED.value
        ]
        
        builds_to_delete = self._db_session.query(ProjectBuild).filter(
            ProjectBuild.project_id == project_id,
            ProjectBuild.status.in_(completed_statuses),
            ProjectBuild.created_at < cutoff_date
        ).all()
        
        count = len(builds_to_delete)
        
        # Delete artifact files
        for build in builds_to_delete:
            for artifact in build.artifacts:
                if artifact.path and os.path.exists(artifact.path):
                    try:
                        os.remove(artifact.path)
                    except IOError:
                        pass  # Best effort cleanup
            
            # Delete log files
            if build.logs_path and os.path.exists(build.logs_path):
                try:
                    os.remove(build.logs_path)
                except IOError:
                    pass  # Best effort cleanup
            
            self._db_session.delete(build)
        
        self._db_session.commit()
        
        # Log the cleanup event
        if self._audit_logger and count > 0:
            self._audit_logger.log_event(
                event_type='builds_cleaned_up',
                user_id='system',
                details={
                    "project_id": project_id,
                    "retention_days": retention_days,
                    "builds_removed": count
                }
            )
        
        return count
