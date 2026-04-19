"""
.. module:: infrastructure_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the InfrastructureManager class for infrastructure specification CRUD operations and job execution

.. moduleauthor:: Automation Mojo LLC

This module provides the InfrastructureManager class which handles:
- Infrastructure specification CRUD operations (Requirements 6.1, 6.2, 6.3, 6.4, 6.5)
- Infrastructure job execution and tracking (Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7)
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import utc_now


# =============================================================================
# Enums
# =============================================================================

class InfraProvider(str, Enum):
    """
        Enum-like class to represent the infrastructure providers.
    """
    LOCAL = 'local'
    DOCKER = 'docker'
    KUBERNETES = 'kubernetes'
    AWS = 'aws'
    AZURE = 'azure'
    GCP = 'gcp'


class InfraAction(str, Enum):
    """
        Enum-like class to represent the infrastructure job actions.
    """
    PROVISION = 'provision'
    UPDATE = 'update'
    DESTROY = 'destroy'


class InfraState(str, Enum):
    """
        Enum-like class to represent the infrastructure lifecycle state.
    """
    PENDING = 'pending'
    PROVISIONING = 'provisioning'
    RUNNING = 'running'
    UPDATING = 'updating'
    DESTROYING = 'destroying'
    DESTROYED = 'destroyed'
    FAILED = 'failed'


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
class InfraResourceDefinition:
    """Definition of an infrastructure resource."""
    name: str
    type: str  # vm, container, network, storage, etc.
    provider_config: Dict[str, Any]


@dataclass
class InfraSpecCreateRequest:
    """Request dataclass for creating a new infrastructure specification."""
    name: str
    provider: InfraProvider
    resources: List[Dict[str, Any]] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    timeout_minutes: int = 30
    description: str = ""


@dataclass
class InfraSpecUpdateRequest:
    """Request dataclass for updating an existing infrastructure specification."""
    name: Optional[str] = None
    provider: Optional[InfraProvider] = None
    resources: Optional[List[Dict[str, Any]]] = None
    variables: Optional[Dict[str, Any]] = None
    timeout_minutes: Optional[int] = None
    description: Optional[str] = None


@dataclass
class InfraSpecResponse:
    """Response dataclass for infrastructure specification data."""
    id: int
    project_id: int
    name: str
    provider: InfraProvider
    resources: List[Dict[str, Any]]
    variables: Dict[str, Any]
    timeout_minutes: int
    description: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass
class InfraSpecListResponse:
    """Response dataclass for paginated infrastructure specification list."""
    specs: List[InfraSpecResponse]
    total: int
    offset: int
    limit: int



@dataclass
class InfraJobTriggerRequest:
    """Request dataclass for triggering an infrastructure job."""
    spec_id: int
    action: InfraAction
    variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InfraJobResponse:
    """Response dataclass for infrastructure job data."""
    id: int
    project_id: int
    spec_id: int
    spec_name: str
    spec_version: int
    action: InfraAction
    state: InfraState
    status: JobStatus
    triggered_by_id: str
    triggered_by_username: str
    variables: Dict[str, Any]
    provisioned_resources: List[Dict[str, Any]]
    connection_details: Dict[str, Any]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    created_at: datetime


@dataclass
class InfraJobListResponse:
    """Response dataclass for paginated infrastructure job list."""
    jobs: List[InfraJobResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Exceptions
# =============================================================================

class InfraSpecValidationError(Exception):
    """Exception raised when infrastructure specification validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "VALIDATION_ERROR"
        super().__init__(self.message)


class InfraSpecNotFoundError(Exception):
    """Exception raised when an infrastructure specification is not found."""
    
    def __init__(self, message: str, error_code: str = "INFRA_SPEC_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateInfraSpecError(Exception):
    """Exception raised when attempting to create an infrastructure specification with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "INFRA_SPEC_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class InfraSpecHasActiveJobsError(Exception):
    """Exception raised when attempting to delete an infrastructure specification with active jobs."""
    
    def __init__(self, message: str, error_code: str = "INFRA_SPEC_HAS_ACTIVE_JOBS"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ProjectNotFoundError(Exception):
    """Exception raised when a project is not found."""
    
    def __init__(self, message: str, error_code: str = "PROJECT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class InfraJobNotFoundError(Exception):
    """Exception raised when an infrastructure job is not found."""
    
    def __init__(self, message: str, error_code: str = "INFRA_JOB_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class InfraJobCannotBeCancelledError(Exception):
    """Exception raised when an infrastructure job cannot be cancelled."""
    
    def __init__(self, message: str, error_code: str = "INFRA_JOB_CANNOT_BE_CANCELLED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


# =============================================================================
# Validation Constants
# =============================================================================

# Infrastructure spec name validation: alphanumeric, underscore, hyphen, period
# Must start with alphanumeric, 1-128 characters
INFRA_SPEC_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}\Z')

# Valid infrastructure providers
VALID_PROVIDERS = {p.value for p in InfraProvider}

# Valid resource types
VALID_RESOURCE_TYPES = {'vm', 'container', 'network', 'storage', 'database', 'loadbalancer', 'dns', 'custom'}


# =============================================================================
# Validation Functions
# =============================================================================

def validate_infra_spec_name(name: str) -> bool:
    """
    Validate that an infrastructure specification name contains only alphanumeric characters,
    underscores, hyphens, and periods.
    
    :param name: The infrastructure specification name to validate
    :returns: True if valid, False otherwise
    """
    if not name:
        return False
    
    if not INFRA_SPEC_NAME_PATTERN.match(name):
        return False
    
    return True


def validate_infra_resources(resources: List[Dict[str, Any]]) -> List[str]:
    """
    Validate infrastructure resource definitions.
    
    :param resources: List of resource definitions
    :returns: List of validation error messages (empty if valid)
    
    Validates: Requirements 6.5
    """
    errors = []
    
    if not isinstance(resources, list):
        errors.append("Resources must be a list")
        return errors
    
    for i, resource in enumerate(resources):
        if not isinstance(resource, dict):
            errors.append(f"Resource {i}: must be a dictionary")
            continue
        
        # Check required fields
        if 'name' not in resource:
            errors.append(f"Resource {i}: missing required field 'name'")
        elif not isinstance(resource['name'], str) or not resource['name'].strip():
            errors.append(f"Resource {i}: 'name' must be a non-empty string")
        
        if 'type' not in resource:
            errors.append(f"Resource {i}: missing required field 'type'")
        elif not isinstance(resource['type'], str):
            errors.append(f"Resource {i}: 'type' must be a string")
        
        # Check provider_config field
        if 'provider_config' in resource and not isinstance(resource.get('provider_config'), dict):
            errors.append(f"Resource {i}: 'provider_config' must be a dictionary")
    
    return errors



# =============================================================================
# InfrastructureManager Class
# =============================================================================

class InfrastructureManager:
    """
    Manager class for infrastructure specification CRUD operations and job execution.
    
    This class handles all infrastructure-related operations including:
    - Infrastructure specification creation with validation
    - Infrastructure specification retrieval by ID
    - Infrastructure specification updates with versioning
    - Infrastructure specification deletion with active job check
    - Infrastructure job triggering and execution tracking
    
    Validates: Requirements 6.1-6.5, 7.1-7.7
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None, secret_manager=None):
        """
        Initialize the InfrastructureManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        :param secret_manager: Optional SecretManager instance for secret resolution
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
        self._secret_manager = secret_manager
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def _validate_infra_spec_create_request(self, request: InfraSpecCreateRequest) -> None:
        """
        Validate an infrastructure specification creation request.
        
        :param request: The infrastructure specification creation request to validate
        :raises InfraSpecValidationError: If validation fails
        """
        if not validate_infra_spec_name(request.name):
            raise InfraSpecValidationError(
                "Infrastructure specification name must be 1-128 characters, start with alphanumeric, "
                "and contain only alphanumeric characters, underscores, hyphens, and periods",
                field="name",
                error_code="INVALID_INFRA_SPEC_NAME"
            )
        
        # Validate provider
        if request.provider is None:
            raise InfraSpecValidationError(
                "Provider is required",
                field="provider",
                error_code="MISSING_PROVIDER"
            )
        
        if isinstance(request.provider, str):
            if request.provider not in VALID_PROVIDERS:
                raise InfraSpecValidationError(
                    f"Invalid provider '{request.provider}'. Must be one of: {', '.join(VALID_PROVIDERS)}",
                    field="provider",
                    error_code="INVALID_PROVIDER"
                )
        elif isinstance(request.provider, InfraProvider):
            pass  # Valid enum value
        else:
            raise InfraSpecValidationError(
                "Provider must be a valid InfraProvider value",
                field="provider",
                error_code="INVALID_PROVIDER"
            )
        
        if request.timeout_minutes is not None and request.timeout_minutes <= 0:
            raise InfraSpecValidationError(
                "Timeout must be a positive integer",
                field="timeout_minutes",
                error_code="INVALID_TIMEOUT"
            )
        
        # Validate resources syntax
        resource_errors = validate_infra_resources(request.resources)
        if resource_errors:
            raise InfraSpecValidationError(
                f"Invalid resources: {'; '.join(resource_errors)}",
                field="resources",
                error_code="INVALID_RESOURCES"
            )
    
    def validate_spec(self, spec: InfraSpecCreateRequest) -> List[str]:
        """
        Validate infrastructure specification syntax. Returns list of errors.
        
        :param spec: The infrastructure specification to validate
        :returns: List of validation error messages (empty if valid)
        
        Validates: Requirements 6.5
        """
        errors = []
        
        # Validate name
        if not validate_infra_spec_name(spec.name):
            errors.append("Name must be 1-128 characters, start with alphanumeric, "
                         "and contain only alphanumeric characters, underscores, hyphens, and periods")
        
        # Validate provider
        if spec.provider is None:
            errors.append("Provider is required")
        elif isinstance(spec.provider, str):
            if spec.provider not in VALID_PROVIDERS:
                errors.append(f"Invalid provider '{spec.provider}'. Must be one of: {', '.join(VALID_PROVIDERS)}")
        elif not isinstance(spec.provider, InfraProvider):
            errors.append("Provider must be a valid InfraProvider value")
        
        # Validate timeout
        if spec.timeout_minutes is not None and spec.timeout_minutes <= 0:
            errors.append("Timeout must be a positive integer")
        
        # Validate resources
        resource_errors = validate_infra_resources(spec.resources)
        errors.extend(resource_errors)
        
        # Validate variables
        if spec.variables:
            if not isinstance(spec.variables, dict):
                errors.append("Variables must be a dictionary")
        
        return errors
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _infra_spec_to_response(self, spec) -> InfraSpecResponse:
        """
        Convert a ProjectInfraSpec ORM object to an InfraSpecResponse.
        
        :param spec: The ProjectInfraSpec ORM object
        :returns: InfraSpecResponse dataclass
        """
        provider_value = spec.provider
        if isinstance(provider_value, str):
            provider = InfraProvider(provider_value)
        else:
            provider = provider_value
        
        return InfraSpecResponse(
            id=spec.id,
            project_id=spec.project_id,
            name=spec.name,
            provider=provider,
            resources=spec.resources_json or [],
            variables=spec.variables_json or {},
            timeout_minutes=spec.timeout_minutes,
            description=spec.description or "",
            version=spec.version,
            created_at=spec.created_at,
            updated_at=spec.updated_at
        )
    
    def _infra_job_to_response(self, job) -> InfraJobResponse:
        """
        Convert a ProjectInfraJob ORM object to an InfraJobResponse.
        
        :param job: The ProjectInfraJob ORM object
        :returns: InfraJobResponse dataclass
        """
        from automojo.pychestrate.core.orm import User
        
        spec_name = job.spec.name if job.spec else ""
        
        # Get triggered by username
        triggered_by_username = ""
        if job.triggered_by_id:
            user = self._db_session.query(User).filter(User.id == job.triggered_by_id).first()
            if user:
                triggered_by_username = user.login
        
        # Convert string values to enums
        action_value = job.action
        if isinstance(action_value, str):
            action = InfraAction(action_value)
        else:
            action = action_value
        
        state_value = job.state
        if isinstance(state_value, str):
            state = InfraState(state_value)
        else:
            state = state_value
        
        status_value = job.status
        if isinstance(status_value, str):
            status = JobStatus(status_value)
        else:
            status = status_value
        
        return InfraJobResponse(
            id=job.id,
            project_id=job.project_id,
            spec_id=job.spec_id,
            spec_name=spec_name,
            spec_version=job.spec_version,
            action=action,
            state=state,
            status=status,
            triggered_by_id=str(job.triggered_by_id),
            triggered_by_username=triggered_by_username,
            variables=job.variables_json or {},
            provisioned_resources=job.provisioned_resources_json or [],
            connection_details=job.connection_details_json or {},
            started_at=job.started_at,
            completed_at=job.completed_at,
            duration_seconds=job.duration_seconds,
            created_at=job.created_at
        )
    

    # =========================================================================
    # Infrastructure Specification CRUD Operations
    # =========================================================================
    
    def create_spec(
        self,
        project_id: int,
        request: InfraSpecCreateRequest,
        user_id: str
    ) -> InfraSpecResponse:
        """
        Create an infrastructure specification.
        
        :param project_id: The project's unique identifier
        :param request: The infrastructure specification creation request
        :param user_id: The ID of the user creating the specification
        :returns: InfraSpecResponse with the created specification data
        :raises ProjectNotFoundError: If project is not found
        :raises InfraSpecValidationError: If validation fails
        :raises DuplicateInfraSpecError: If specification name already exists in project
        
        Validates: Requirements 6.1
        """
        from automojo.pychestrate.core.orm import Project, ProjectInfraSpec
        
        # Validate the request
        self._validate_infra_spec_create_request(request)
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check for duplicate name within project
        existing_spec = self._db_session.query(ProjectInfraSpec).filter(
            ProjectInfraSpec.project_id == project_id,
            ProjectInfraSpec.name == request.name
        ).first()
        
        if existing_spec:
            raise DuplicateInfraSpecError(
                f"Infrastructure specification with name '{request.name}' already exists in project '{project.name}'",
                field="name"
            )
        
        # Get provider value
        provider_value = request.provider.value if isinstance(request.provider, InfraProvider) else request.provider
        
        # Create the infrastructure specification
        now = utc_now()
        
        spec = ProjectInfraSpec(
            project_id=project_id,
            name=request.name,
            provider=provider_value,
            resources_json=request.resources,
            variables_json=request.variables,
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
                event_type='infra_spec_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "spec_id": spec.id,
                    "spec_name": spec.name,
                    "provider": provider_value
                }
            )
        
        return self._infra_spec_to_response(spec)
    
    def get_spec(self, spec_id: int) -> Optional[InfraSpecResponse]:
        """
        Get infrastructure specification by ID.
        
        :param spec_id: The infrastructure specification's unique identifier
        :returns: InfraSpecResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectInfraSpec
        
        spec = self._db_session.query(ProjectInfraSpec).filter(
            ProjectInfraSpec.id == spec_id
        ).first()
        
        if not spec:
            return None
        
        return self._infra_spec_to_response(spec)
    
    def update_spec(
        self,
        spec_id: int,
        request: InfraSpecUpdateRequest,
        user_id: str
    ) -> InfraSpecResponse:
        """
        Update infrastructure specification (creates new version).
        
        :param spec_id: The infrastructure specification's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: InfraSpecResponse with the updated specification data
        :raises InfraSpecNotFoundError: If specification is not found
        :raises InfraSpecValidationError: If validation fails
        :raises DuplicateInfraSpecError: If new name already exists in project
        
        Validates: Requirements 6.2
        """
        from automojo.pychestrate.core.orm import ProjectInfraSpec
        
        spec = self._db_session.query(ProjectInfraSpec).filter(
            ProjectInfraSpec.id == spec_id
        ).first()
        
        if not spec:
            raise InfraSpecNotFoundError(f"Infrastructure specification with ID '{spec_id}' not found")
        
        old_version = spec.version
        
        # Update name if provided
        if request.name is not None:
            if not validate_infra_spec_name(request.name):
                raise InfraSpecValidationError(
                    "Infrastructure specification name must be 1-128 characters, start with alphanumeric, "
                    "and contain only alphanumeric characters, underscores, hyphens, and periods",
                    field="name",
                    error_code="INVALID_INFRA_SPEC_NAME"
                )
            
            # Check for duplicate name (excluding current spec)
            existing_spec = self._db_session.query(ProjectInfraSpec).filter(
                ProjectInfraSpec.project_id == spec.project_id,
                ProjectInfraSpec.name == request.name,
                ProjectInfraSpec.id != spec_id
            ).first()
            
            if existing_spec:
                raise DuplicateInfraSpecError(
                    f"Infrastructure specification with name '{request.name}' already exists in this project",
                    field="name"
                )
            
            spec.name = request.name
        
        # Update provider if provided
        if request.provider is not None:
            if isinstance(request.provider, str):
                if request.provider not in VALID_PROVIDERS:
                    raise InfraSpecValidationError(
                        f"Invalid provider '{request.provider}'. Must be one of: {', '.join(VALID_PROVIDERS)}",
                        field="provider",
                        error_code="INVALID_PROVIDER"
                    )
                spec.provider = request.provider
            elif isinstance(request.provider, InfraProvider):
                spec.provider = request.provider.value
            else:
                raise InfraSpecValidationError(
                    "Provider must be a valid InfraProvider value",
                    field="provider",
                    error_code="INVALID_PROVIDER"
                )
        
        # Update resources if provided
        if request.resources is not None:
            resource_errors = validate_infra_resources(request.resources)
            if resource_errors:
                raise InfraSpecValidationError(
                    f"Invalid resources: {'; '.join(resource_errors)}",
                    field="resources",
                    error_code="INVALID_RESOURCES"
                )
            spec.resources_json = request.resources
        
        # Update variables if provided
        if request.variables is not None:
            spec.variables_json = request.variables
        
        # Update timeout if provided
        if request.timeout_minutes is not None:
            if request.timeout_minutes <= 0:
                raise InfraSpecValidationError(
                    "Timeout must be a positive integer",
                    field="timeout_minutes",
                    error_code="INVALID_TIMEOUT"
                )
            spec.timeout_minutes = request.timeout_minutes
        
        # Update description if provided
        if request.description is not None:
            spec.description = request.description
        
        # Increment version (Requirements 6.2)
        spec.version = old_version + 1
        spec.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the specification update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='infra_spec_updated',
                user_id=str(user_id),
                details={
                    "spec_id": spec.id,
                    "spec_name": spec.name,
                    "old_version": old_version,
                    "new_version": spec.version,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._infra_spec_to_response(spec)


    def delete_spec(self, spec_id: int, user_id: str) -> None:
        """
        Delete infrastructure specification. Fails if active jobs exist.
        
        :param spec_id: The infrastructure specification's unique identifier
        :param user_id: The ID of the user deleting the specification
        :raises InfraSpecNotFoundError: If specification is not found
        :raises InfraSpecHasActiveJobsError: If specification has active jobs
        
        Validates: Requirements 6.3
        """
        from automojo.pychestrate.core.orm import ProjectInfraSpec, ProjectInfraJob, ProjectJobStatus
        
        spec = self._db_session.query(ProjectInfraSpec).filter(
            ProjectInfraSpec.id == spec_id
        ).first()
        
        if not spec:
            raise InfraSpecNotFoundError(f"Infrastructure specification with ID '{spec_id}' not found")
        
        # Check for active jobs
        active_jobs = self._db_session.query(ProjectInfraJob).filter(
            ProjectInfraJob.spec_id == spec_id,
            ProjectInfraJob.status.in_([
                ProjectJobStatus.PENDING.value,
                ProjectJobStatus.QUEUED.value,
                ProjectJobStatus.RUNNING.value
            ])
        ).count()
        
        if active_jobs > 0:
            raise InfraSpecHasActiveJobsError(
                f"Cannot delete infrastructure specification '{spec.name}' with {active_jobs} active job(s)"
            )
        
        spec_name = spec.name
        project_id = spec.project_id
        
        # Delete the specification (cascades to jobs)
        self._db_session.delete(spec)
        self._db_session.commit()
        
        # Log the specification deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='infra_spec_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "spec_id": spec_id,
                    "spec_name": spec_name
                }
            )
    
    def list_specs(
        self,
        project_id: int,
        offset: int = 0,
        limit: int = 50
    ) -> InfraSpecListResponse:
        """
        List infrastructure specifications in a project.
        
        :param project_id: The project's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: InfraSpecListResponse with paginated specification list
        """
        from automojo.pychestrate.core.orm import ProjectInfraSpec
        
        query = self._db_session.query(ProjectInfraSpec).filter(
            ProjectInfraSpec.project_id == project_id
        )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        specs = query.order_by(ProjectInfraSpec.name).offset(offset).limit(limit).all()
        
        return InfraSpecListResponse(
            specs=[self._infra_spec_to_response(spec) for spec in specs],
            total=total,
            offset=offset,
            limit=limit
        )
    

    # =========================================================================
    # Infrastructure Job Execution Operations
    # =========================================================================
    
    def trigger_job(
        self,
        request: InfraJobTriggerRequest,
        user_id: str
    ) -> InfraJobResponse:
        """
        Trigger an infrastructure job.
        
        :param request: The infrastructure job trigger request
        :param user_id: The ID of the user triggering the job
        :returns: InfraJobResponse with the created job data
        :raises InfraSpecNotFoundError: If specification is not found
        
        Validates: Requirements 7.1
        """
        from automojo.pychestrate.core.orm import ProjectInfraSpec, ProjectInfraJob, ProjectJobStatus
        
        # Get the infrastructure specification
        spec = self._db_session.query(ProjectInfraSpec).filter(
            ProjectInfraSpec.id == request.spec_id
        ).first()
        
        if not spec:
            raise InfraSpecNotFoundError(f"Infrastructure specification with ID '{request.spec_id}' not found")
        
        # Determine initial state based on action
        action_value = request.action.value if isinstance(request.action, InfraAction) else request.action
        
        if action_value == InfraAction.PROVISION.value:
            initial_state = InfraState.PENDING.value
        elif action_value == InfraAction.UPDATE.value:
            initial_state = InfraState.PENDING.value
        elif action_value == InfraAction.DESTROY.value:
            initial_state = InfraState.PENDING.value
        else:
            initial_state = InfraState.PENDING.value
        
        # Create the job record with status pending
        now = utc_now()
        
        job = ProjectInfraJob(
            project_id=spec.project_id,
            spec_id=spec.id,
            spec_version=spec.version,
            action=action_value,
            state=initial_state,
            status=ProjectJobStatus.PENDING.value,
            triggered_by_id=user_id,
            variables_json=request.variables,
            provisioned_resources_json=[],
            connection_details_json={},
            created_at=now
        )
        
        self._db_session.add(job)
        self._db_session.commit()
        
        # Log the job trigger event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='infra_job_triggered',
                user_id=str(user_id),
                details={
                    "project_id": spec.project_id,
                    "spec_id": spec.id,
                    "spec_name": spec.name,
                    "job_id": job.id,
                    "action": action_value
                }
            )
        
        return self._infra_job_to_response(job)
    
    def get_job(self, job_id: int) -> Optional[InfraJobResponse]:
        """
        Get infrastructure job by ID.
        
        :param job_id: The infrastructure job's unique identifier
        :returns: InfraJobResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectInfraJob
        
        job = self._db_session.query(ProjectInfraJob).filter(
            ProjectInfraJob.id == job_id
        ).first()
        
        if not job:
            return None
        
        return self._infra_job_to_response(job)
    
    def cancel_job(self, job_id: int, user_id: str) -> InfraJobResponse:
        """
        Cancel a pending or running infrastructure job.
        
        :param job_id: The infrastructure job's unique identifier
        :param user_id: The ID of the user cancelling the job
        :returns: InfraJobResponse with the updated job data
        :raises InfraJobNotFoundError: If job is not found
        :raises InfraJobCannotBeCancelledError: If job cannot be cancelled
        
        Validates: Requirements 7.4
        """
        from automojo.pychestrate.core.orm import ProjectInfraJob, ProjectJobStatus
        
        job = self._db_session.query(ProjectInfraJob).filter(
            ProjectInfraJob.id == job_id
        ).first()
        
        if not job:
            raise InfraJobNotFoundError(f"Infrastructure job with ID '{job_id}' not found")
        
        # Check if job can be cancelled
        cancellable_statuses = [
            ProjectJobStatus.PENDING.value,
            ProjectJobStatus.QUEUED.value,
            ProjectJobStatus.RUNNING.value
        ]
        
        if job.status not in cancellable_statuses:
            raise InfraJobCannotBeCancelledError(
                f"Infrastructure job with status '{job.status}' cannot be cancelled"
            )
        
        # Update job status
        job.status = ProjectJobStatus.CANCELLED.value
        job.state = InfraState.FAILED.value
        job.completed_at = utc_now()
        
        if job.started_at:
            job.duration_seconds = int((job.completed_at - job.started_at).total_seconds())
        
        self._db_session.commit()
        
        # Log the job cancellation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='infra_job_cancelled',
                user_id=str(user_id),
                details={
                    "job_id": job.id,
                    "spec_id": job.spec_id,
                    "previous_status": job.status
                }
            )
        
        return self._infra_job_to_response(job)
    
    def list_jobs(
        self,
        project_id: int = None,
        spec_id: int = None,
        state: InfraState = None,
        status: JobStatus = None,
        offset: int = 0,
        limit: int = 50
    ) -> InfraJobListResponse:
        """
        List infrastructure jobs with filtering.
        
        :param project_id: Optional project ID filter
        :param spec_id: Optional specification ID filter
        :param state: Optional infrastructure state filter
        :param status: Optional job status filter
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: InfraJobListResponse with paginated job list
        
        Validates: Requirements 7.6
        """
        from automojo.pychestrate.core.orm import ProjectInfraJob
        
        query = self._db_session.query(ProjectInfraJob)
        
        # Apply filters
        if project_id is not None:
            query = query.filter(ProjectInfraJob.project_id == project_id)
        
        if spec_id is not None:
            query = query.filter(ProjectInfraJob.spec_id == spec_id)
        
        if state is not None:
            state_value = state.value if isinstance(state, InfraState) else state
            query = query.filter(ProjectInfraJob.state == state_value)
        
        if status is not None:
            status_value = status.value if isinstance(status, JobStatus) else status
            query = query.filter(ProjectInfraJob.status == status_value)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (order by created_at descending for most recent first)
        jobs = query.order_by(ProjectInfraJob.created_at.desc()).offset(offset).limit(limit).all()
        
        return InfraJobListResponse(
            jobs=[self._infra_job_to_response(job) for job in jobs],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def get_job_logs(self, job_id: int) -> str:
        """
        Get infrastructure job execution logs.
        
        :param job_id: The infrastructure job's unique identifier
        :returns: Job logs as a string
        :raises InfraJobNotFoundError: If job is not found
        """
        from automojo.pychestrate.core.orm import ProjectInfraJob
        
        job = self._db_session.query(ProjectInfraJob).filter(
            ProjectInfraJob.id == job_id
        ).first()
        
        if not job:
            raise InfraJobNotFoundError(f"Infrastructure job with ID '{job_id}' not found")
        
        # If logs_path is set, read from file
        if job.logs_path and os.path.exists(job.logs_path):
            try:
                with open(job.logs_path, 'r') as f:
                    return f.read()
            except IOError:
                return ""
        
        return ""
    
    def get_provisioned_resources(self, job_id: int) -> List[Dict[str, Any]]:
        """
        Get details of provisioned resources.
        
        :param job_id: The infrastructure job's unique identifier
        :returns: List of provisioned resource details
        :raises InfraJobNotFoundError: If job is not found
        
        Validates: Requirements 7.3
        """
        from automojo.pychestrate.core.orm import ProjectInfraJob
        
        job = self._db_session.query(ProjectInfraJob).filter(
            ProjectInfraJob.id == job_id
        ).first()
        
        if not job:
            raise InfraJobNotFoundError(f"Infrastructure job with ID '{job_id}' not found")
        
        return job.provisioned_resources_json or []
    
    def get_connection_details(self, job_id: int) -> Dict[str, Any]:
        """
        Get connection details for provisioned infrastructure.
        
        :param job_id: The infrastructure job's unique identifier
        :returns: Connection details dictionary
        :raises InfraJobNotFoundError: If job is not found
        
        Validates: Requirements 7.3
        """
        from automojo.pychestrate.core.orm import ProjectInfraJob
        
        job = self._db_session.query(ProjectInfraJob).filter(
            ProjectInfraJob.id == job_id
        ).first()
        
        if not job:
            raise InfraJobNotFoundError(f"Infrastructure job with ID '{job_id}' not found")
        
        return job.connection_details_json or {}
    
    # =========================================================================
    # Job State Management (Internal Methods)
    # =========================================================================
    
    def _update_job_state(
        self,
        job_id: int,
        state: InfraState,
        status: JobStatus,
        provisioned_resources: List[Dict[str, Any]] = None,
        connection_details: Dict[str, Any] = None
    ) -> InfraJobResponse:
        """
        Update infrastructure job state and status.
        
        This is an internal method used by job executors to update job state.
        
        :param job_id: The infrastructure job's unique identifier
        :param state: The new infrastructure state
        :param status: The new job status
        :param provisioned_resources: Optional list of provisioned resources
        :param connection_details: Optional connection details
        :returns: InfraJobResponse with the updated job data
        :raises InfraJobNotFoundError: If job is not found
        
        Validates: Requirements 7.2, 7.7
        """
        from automojo.pychestrate.core.orm import ProjectInfraJob
        
        job = self._db_session.query(ProjectInfraJob).filter(
            ProjectInfraJob.id == job_id
        ).first()
        
        if not job:
            raise InfraJobNotFoundError(f"Infrastructure job with ID '{job_id}' not found")
        
        now = utc_now()
        
        # Update state and status
        state_value = state.value if isinstance(state, InfraState) else state
        status_value = status.value if isinstance(status, JobStatus) else status
        
        job.state = state_value
        job.status = status_value
        
        # Update started_at if transitioning to running
        if status_value == JobStatus.RUNNING.value and job.started_at is None:
            job.started_at = now
        
        # Update completed_at if transitioning to terminal state
        terminal_statuses = [
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value
        ]
        if status_value in terminal_statuses and job.completed_at is None:
            job.completed_at = now
            if job.started_at:
                job.duration_seconds = int((job.completed_at - job.started_at).total_seconds())
        
        # Update provisioned resources if provided
        if provisioned_resources is not None:
            job.provisioned_resources_json = provisioned_resources
        
        # Update connection details if provided
        if connection_details is not None:
            job.connection_details_json = connection_details
        
        self._db_session.commit()
        
        return self._infra_job_to_response(job)

