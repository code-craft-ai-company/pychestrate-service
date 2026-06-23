"""
.. module:: test_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the TestManager class for test specification CRUD operations and job execution

.. moduleauthor:: Code Craft AI LLC

This module provides the TestManager class which handles:
- Test specification CRUD operations (Requirements 8.1, 8.2, 8.3, 8.4, 8.5)
- Test job execution and tracking (Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6)
- Test results and metrics (Requirements 9.7)
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession
from sqlalchemy import func

from ccai.pychestrate.core.defaults import utc_now


# =============================================================================
# Enums
# =============================================================================

class TestFramework(str, Enum):
    """
        Enum-like class to represent the test frameworks.
    """
    PYTEST = 'pytest'
    UNITTEST = 'unittest'
    TESTBASE = 'testbase'
    CUSTOM = 'custom'


class TestResultFormat(str, Enum):
    """
        Enum-like class to represent the test result formats.
    """
    JUNIT_XML = 'junit_xml'
    TAP = 'tap'
    JSON = 'json'


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


class TestCaseStatus(str, Enum):
    """
        Enum-like class to represent the status of individual test cases.
    """
    PASSED = 'passed'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    ERROR = 'error'


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class TestSpecCreateRequest:
    """Request dataclass for creating a new test specification."""
    name: str
    framework: TestFramework
    test_command: str
    test_selection: str = ""
    build_ref: Optional[int] = None
    infra_ref: Optional[int] = None
    environment: Dict[str, str] = field(default_factory=dict)
    timeout_minutes: int = 60
    result_format: TestResultFormat = TestResultFormat.JUNIT_XML
    description: str = ""


@dataclass
class TestSpecUpdateRequest:
    """Request dataclass for updating an existing test specification."""
    name: Optional[str] = None
    framework: Optional[TestFramework] = None
    test_command: Optional[str] = None
    test_selection: Optional[str] = None
    build_ref: Optional[int] = None
    infra_ref: Optional[int] = None
    environment: Optional[Dict[str, str]] = None
    timeout_minutes: Optional[int] = None
    result_format: Optional[TestResultFormat] = None
    description: Optional[str] = None


@dataclass
class TestSpecResponse:
    """Response dataclass for test specification data."""
    id: int
    project_id: int
    name: str
    framework: TestFramework
    test_command: str
    test_selection: str
    build_ref: Optional[int]
    infra_ref: Optional[int]
    environment: Dict[str, str]
    timeout_minutes: int
    result_format: TestResultFormat
    description: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass
class TestSpecListResponse:
    """Response dataclass for paginated test specification list."""
    specs: List[TestSpecResponse]
    total: int
    offset: int
    limit: int


@dataclass
class TestJobTriggerRequest:
    """Request dataclass for triggering a test job."""
    spec_id: int
    build_id: Optional[int] = None
    infra_job_id: Optional[int] = None
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResultSummary:
    """Summary of test results."""
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration_seconds: float


@dataclass
class TestJobResponse:
    """Response dataclass for test job data."""
    id: int
    project_id: int
    spec_id: int
    spec_name: str
    spec_version: int
    build_id: Optional[int]
    infra_job_id: Optional[int]
    status: JobStatus
    triggered_by_id: str
    triggered_by_username: str
    result_summary: Optional[TestResultSummary]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    created_at: datetime


@dataclass
class TestJobListResponse:
    """Response dataclass for paginated test job list."""
    jobs: List[TestJobResponse]
    total: int
    offset: int
    limit: int


@dataclass
class TestCaseResult:
    """Result of an individual test case."""
    name: str
    classname: str
    status: TestCaseStatus
    duration_seconds: float
    failure_message: Optional[str]
    failure_trace: Optional[str]


@dataclass
class TestMetrics:
    """Test metrics for a project or specification."""
    total_runs: int
    pass_rate: float
    failure_rate: float
    average_duration_seconds: float
    duration_trend: List[Dict[str, Any]]
    flaky_test_count: int


@dataclass
class FlakyTest:
    """Information about a flaky test."""
    name: str
    classname: str
    flakiness_rate: float
    total_runs: int
    passed_count: int
    failed_count: int


# =============================================================================
# Exceptions
# =============================================================================

class TestSpecValidationError(Exception):
    """Exception raised when test specification validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "VALIDATION_ERROR"
        super().__init__(self.message)


class TestSpecNotFoundError(Exception):
    """Exception raised when a test specification is not found."""
    
    def __init__(self, message: str, error_code: str = "TEST_SPEC_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateTestSpecError(Exception):
    """Exception raised when attempting to create a test specification with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "TEST_SPEC_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class TestSpecHasActiveJobsError(Exception):
    """Exception raised when attempting to delete a test specification with active jobs."""
    
    def __init__(self, message: str, error_code: str = "TEST_SPEC_HAS_ACTIVE_JOBS"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ProjectNotFoundError(Exception):
    """Exception raised when a project is not found."""
    
    def __init__(self, message: str, error_code: str = "PROJECT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class TestJobNotFoundError(Exception):
    """Exception raised when a test job is not found."""
    
    def __init__(self, message: str, error_code: str = "TEST_JOB_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class TestJobCannotBeCancelledError(Exception):
    """Exception raised when a test job cannot be cancelled."""
    
    def __init__(self, message: str, error_code: str = "TEST_JOB_CANNOT_BE_CANCELLED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class BuildNotFoundError(Exception):
    """Exception raised when a build is not found."""
    
    def __init__(self, message: str, error_code: str = "BUILD_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class InfraJobNotFoundError(Exception):
    """Exception raised when an infrastructure job is not found."""
    
    def __init__(self, message: str, error_code: str = "INFRA_JOB_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


# =============================================================================
# Validation Constants
# =============================================================================

# Test spec name validation: alphanumeric, underscore, hyphen, period
# Must start with alphanumeric, 1-128 characters
TEST_SPEC_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}\Z')

# Valid test frameworks
VALID_FRAMEWORKS = {f.value for f in TestFramework}

# Valid result formats
VALID_RESULT_FORMATS = {f.value for f in TestResultFormat}


# =============================================================================
# Validation Functions
# =============================================================================

def validate_test_spec_name(name: str) -> bool:
    """
    Validate that a test specification name contains only alphanumeric characters,
    underscores, hyphens, and periods.
    
    :param name: The test specification name to validate
    :returns: True if valid, False otherwise
    """
    if not name:
        return False
    
    if not TEST_SPEC_NAME_PATTERN.match(name):
        return False
    
    return True


def validate_test_command(command: str) -> bool:
    """
    Validate that a test command is not empty.
    
    :param command: The test command to validate
    :returns: True if valid, False otherwise
    """
    if not command or not command.strip():
        return False
    return True


def validate_environment(environment: Dict[str, str]) -> List[str]:
    """
    Validate environment variables dictionary.
    
    :param environment: Dictionary of environment variables
    :returns: List of validation error messages (empty if valid)
    """
    errors = []
    
    if not isinstance(environment, dict):
        errors.append("Environment must be a dictionary")
        return errors
    
    for key, value in environment.items():
        if not isinstance(key, str):
            errors.append(f"Environment key '{key}' must be a string")
        if not isinstance(value, str):
            errors.append(f"Environment value for '{key}' must be a string")
    
    return errors



# =============================================================================
# TestManager Class
# =============================================================================

class TestManager:
    """
    Manager class for test specification CRUD operations and job execution.
    
    This class handles all test-related operations including:
    - Test specification creation with validation
    - Test specification retrieval by ID
    - Test specification updates with versioning
    - Test specification deletion with active job check
    - Test job triggering and execution tracking
    - Test results and metrics
    
    Validates: Requirements 8.1-8.5, 9.1-9.7
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None, resource_manager=None, secret_manager=None):
        """
        Initialize the TestManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        :param resource_manager: Optional ResourceManager instance for resource checkout
        :param secret_manager: Optional SecretManager instance for secret resolution
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
        self._resource_manager = resource_manager
        self._secret_manager = secret_manager
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def _validate_test_spec_create_request(self, request: TestSpecCreateRequest) -> None:
        """
        Validate a test specification creation request.
        
        :param request: The test specification creation request to validate
        :raises TestSpecValidationError: If validation fails
        """
        if not validate_test_spec_name(request.name):
            raise TestSpecValidationError(
                "Test specification name must be 1-128 characters, start with alphanumeric, "
                "and contain only alphanumeric characters, underscores, hyphens, and periods",
                field="name",
                error_code="INVALID_TEST_SPEC_NAME"
            )
        
        # Validate framework
        if request.framework is None:
            raise TestSpecValidationError(
                "Framework is required",
                field="framework",
                error_code="MISSING_FRAMEWORK"
            )
        
        if isinstance(request.framework, str):
            if request.framework not in VALID_FRAMEWORKS:
                raise TestSpecValidationError(
                    f"Invalid framework '{request.framework}'. Must be one of: {', '.join(VALID_FRAMEWORKS)}",
                    field="framework",
                    error_code="INVALID_FRAMEWORK"
                )
        elif not isinstance(request.framework, TestFramework):
            raise TestSpecValidationError(
                "Framework must be a valid TestFramework value",
                field="framework",
                error_code="INVALID_FRAMEWORK"
            )
        
        # Validate test command
        if not validate_test_command(request.test_command):
            raise TestSpecValidationError(
                "Test command is required and must not be empty",
                field="test_command",
                error_code="INVALID_TEST_COMMAND"
            )
        
        # Validate timeout
        if request.timeout_minutes is not None and request.timeout_minutes <= 0:
            raise TestSpecValidationError(
                "Timeout must be a positive integer",
                field="timeout_minutes",
                error_code="INVALID_TIMEOUT"
            )
        
        # Validate result format
        if request.result_format is not None:
            if isinstance(request.result_format, str):
                if request.result_format not in VALID_RESULT_FORMATS:
                    raise TestSpecValidationError(
                        f"Invalid result format '{request.result_format}'. Must be one of: {', '.join(VALID_RESULT_FORMATS)}",
                        field="result_format",
                        error_code="INVALID_RESULT_FORMAT"
                    )
            elif not isinstance(request.result_format, TestResultFormat):
                raise TestSpecValidationError(
                    "Result format must be a valid TestResultFormat value",
                    field="result_format",
                    error_code="INVALID_RESULT_FORMAT"
                )
        
        # Validate environment
        if request.environment:
            env_errors = validate_environment(request.environment)
            if env_errors:
                raise TestSpecValidationError(
                    f"Invalid environment: {'; '.join(env_errors)}",
                    field="environment",
                    error_code="INVALID_ENVIRONMENT"
                )
    
    def validate_spec(self, spec: TestSpecCreateRequest) -> List[str]:
        """
        Validate test specification syntax. Returns list of errors.
        
        :param spec: The test specification to validate
        :returns: List of validation error messages (empty if valid)
        
        Validates: Requirements 8.5
        """
        errors = []
        
        # Validate name
        if not validate_test_spec_name(spec.name):
            errors.append("Name must be 1-128 characters, start with alphanumeric, "
                         "and contain only alphanumeric characters, underscores, hyphens, and periods")
        
        # Validate framework
        if spec.framework is None:
            errors.append("Framework is required")
        elif isinstance(spec.framework, str):
            if spec.framework not in VALID_FRAMEWORKS:
                errors.append(f"Invalid framework '{spec.framework}'. Must be one of: {', '.join(VALID_FRAMEWORKS)}")
        elif not isinstance(spec.framework, TestFramework):
            errors.append("Framework must be a valid TestFramework value")
        
        # Validate test command
        if not validate_test_command(spec.test_command):
            errors.append("Test command is required and must not be empty")
        
        # Validate timeout
        if spec.timeout_minutes is not None and spec.timeout_minutes <= 0:
            errors.append("Timeout must be a positive integer")
        
        # Validate result format
        if spec.result_format is not None:
            if isinstance(spec.result_format, str):
                if spec.result_format not in VALID_RESULT_FORMATS:
                    errors.append(f"Invalid result format '{spec.result_format}'. Must be one of: {', '.join(VALID_RESULT_FORMATS)}")
            elif not isinstance(spec.result_format, TestResultFormat):
                errors.append("Result format must be a valid TestResultFormat value")
        
        # Validate environment
        if spec.environment:
            env_errors = validate_environment(spec.environment)
            errors.extend(env_errors)
        
        return errors
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _test_spec_to_response(self, spec) -> TestSpecResponse:
        """
        Convert a ProjectTestSpec ORM object to a TestSpecResponse.
        
        :param spec: The ProjectTestSpec ORM object
        :returns: TestSpecResponse dataclass
        """
        framework_value = spec.framework
        if isinstance(framework_value, str):
            framework = TestFramework(framework_value)
        else:
            framework = framework_value
        
        result_format_value = spec.result_format
        if isinstance(result_format_value, str):
            result_format = TestResultFormat(result_format_value)
        else:
            result_format = result_format_value
        
        return TestSpecResponse(
            id=spec.id,
            project_id=spec.project_id,
            name=spec.name,
            framework=framework,
            test_command=spec.test_command,
            test_selection=spec.test_selection or "",
            build_ref=spec.build_ref,
            infra_ref=spec.infra_ref,
            environment=spec.environment_json or {},
            timeout_minutes=spec.timeout_minutes,
            result_format=result_format,
            description=spec.description or "",
            version=spec.version,
            created_at=spec.created_at,
            updated_at=spec.updated_at
        )
    
    def _test_job_to_response(self, job) -> TestJobResponse:
        """
        Convert a ProjectTestJob ORM object to a TestJobResponse.
        
        :param job: The ProjectTestJob ORM object
        :returns: TestJobResponse dataclass
        """
        from ccai.pychestrate.core.orm import User
        
        spec_name = job.spec.name if job.spec else ""
        
        # Get triggered by username
        triggered_by_username = ""
        if job.triggered_by_id:
            user = self._db_session.query(User).filter(User.id == job.triggered_by_id).first()
            if user:
                triggered_by_username = user.login
        
        # Convert status to enum
        status_value = job.status
        if isinstance(status_value, str):
            status = JobStatus(status_value)
        else:
            status = status_value
        
        # Parse result summary
        result_summary = None
        if job.result_summary_json:
            summary = job.result_summary_json
            result_summary = TestResultSummary(
                total=summary.get('total', 0),
                passed=summary.get('passed', 0),
                failed=summary.get('failed', 0),
                skipped=summary.get('skipped', 0),
                errors=summary.get('errors', 0),
                duration_seconds=summary.get('duration_seconds', 0.0)
            )
        
        return TestJobResponse(
            id=job.id,
            project_id=job.project_id,
            spec_id=job.spec_id,
            spec_name=spec_name,
            spec_version=job.spec_version,
            build_id=job.build_id,
            infra_job_id=job.infra_job_id,
            status=status,
            triggered_by_id=str(job.triggered_by_id),
            triggered_by_username=triggered_by_username,
            result_summary=result_summary,
            started_at=job.started_at,
            completed_at=job.completed_at,
            duration_seconds=job.duration_seconds,
            created_at=job.created_at
        )
    
    def _test_result_to_response(self, result) -> TestCaseResult:
        """
        Convert a ProjectTestResult ORM object to a TestCaseResult.
        
        :param result: The ProjectTestResult ORM object
        :returns: TestCaseResult dataclass
        """
        status_value = result.status
        if isinstance(status_value, str):
            status = TestCaseStatus(status_value)
        else:
            status = status_value
        
        return TestCaseResult(
            name=result.name,
            classname=result.classname or "",
            status=status,
            duration_seconds=result.duration_seconds or 0.0,
            failure_message=result.failure_message,
            failure_trace=result.failure_trace
        )

    
    # =========================================================================
    # Test Specification CRUD Operations
    # =========================================================================
    
    def create_spec(
        self,
        project_id: int,
        request: TestSpecCreateRequest,
        user_id: str
    ) -> TestSpecResponse:
        """
        Create a test specification.
        
        :param project_id: The project's unique identifier
        :param request: The test specification creation request
        :param user_id: The ID of the user creating the specification
        :returns: TestSpecResponse with the created specification data
        :raises ProjectNotFoundError: If project is not found
        :raises TestSpecValidationError: If validation fails
        :raises DuplicateTestSpecError: If specification name already exists in project
        
        Validates: Requirements 8.1
        """
        from ccai.pychestrate.core.orm import Project, ProjectTestSpec, ProjectBuildSpec, ProjectInfraSpec
        
        # Validate the request
        self._validate_test_spec_create_request(request)
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check for duplicate name within project
        existing_spec = self._db_session.query(ProjectTestSpec).filter(
            ProjectTestSpec.project_id == project_id,
            ProjectTestSpec.name == request.name
        ).first()
        
        if existing_spec:
            raise DuplicateTestSpecError(
                f"Test specification with name '{request.name}' already exists in project '{project.name}'",
                field="name"
            )
        
        # Validate build_ref if provided (Requirements 8.6)
        if request.build_ref is not None:
            build_spec = self._db_session.query(ProjectBuildSpec).filter(
                ProjectBuildSpec.id == request.build_ref,
                ProjectBuildSpec.project_id == project_id
            ).first()
            if not build_spec:
                raise TestSpecValidationError(
                    f"Build specification with ID '{request.build_ref}' not found in project",
                    field="build_ref",
                    error_code="BUILD_SPEC_NOT_FOUND"
                )
        
        # Validate infra_ref if provided (Requirements 8.7)
        if request.infra_ref is not None:
            infra_spec = self._db_session.query(ProjectInfraSpec).filter(
                ProjectInfraSpec.id == request.infra_ref,
                ProjectInfraSpec.project_id == project_id
            ).first()
            if not infra_spec:
                raise TestSpecValidationError(
                    f"Infrastructure specification with ID '{request.infra_ref}' not found in project",
                    field="infra_ref",
                    error_code="INFRA_SPEC_NOT_FOUND"
                )
        
        # Get framework and result_format values
        framework_value = request.framework.value if isinstance(request.framework, TestFramework) else request.framework
        result_format_value = request.result_format.value if isinstance(request.result_format, TestResultFormat) else request.result_format
        
        # Create the test specification
        now = utc_now()
        
        spec = ProjectTestSpec(
            project_id=project_id,
            name=request.name,
            framework=framework_value,
            test_command=request.test_command,
            test_selection=request.test_selection or "",
            build_ref=request.build_ref,
            infra_ref=request.infra_ref,
            environment_json=request.environment,
            timeout_minutes=request.timeout_minutes,
            result_format=result_format_value,
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
                event_type='test_spec_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "spec_id": spec.id,
                    "spec_name": spec.name,
                    "framework": framework_value
                }
            )
        
        return self._test_spec_to_response(spec)
    
    def get_spec(self, spec_id: int) -> Optional[TestSpecResponse]:
        """
        Get test specification by ID.
        
        :param spec_id: The test specification's unique identifier
        :returns: TestSpecResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import ProjectTestSpec
        
        spec = self._db_session.query(ProjectTestSpec).filter(
            ProjectTestSpec.id == spec_id
        ).first()
        
        if not spec:
            return None
        
        return self._test_spec_to_response(spec)
    
    def update_spec(
        self,
        spec_id: int,
        request: TestSpecUpdateRequest,
        user_id: str
    ) -> TestSpecResponse:
        """
        Update test specification (creates new version).
        
        :param spec_id: The test specification's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: TestSpecResponse with the updated specification data
        :raises TestSpecNotFoundError: If specification is not found
        :raises TestSpecValidationError: If validation fails
        :raises DuplicateTestSpecError: If new name already exists in project
        
        Validates: Requirements 8.2
        """
        from ccai.pychestrate.core.orm import ProjectTestSpec, ProjectBuildSpec, ProjectInfraSpec
        
        spec = self._db_session.query(ProjectTestSpec).filter(
            ProjectTestSpec.id == spec_id
        ).first()
        
        if not spec:
            raise TestSpecNotFoundError(f"Test specification with ID '{spec_id}' not found")
        
        old_version = spec.version
        
        # Update name if provided
        if request.name is not None:
            if not validate_test_spec_name(request.name):
                raise TestSpecValidationError(
                    "Test specification name must be 1-128 characters, start with alphanumeric, "
                    "and contain only alphanumeric characters, underscores, hyphens, and periods",
                    field="name",
                    error_code="INVALID_TEST_SPEC_NAME"
                )
            
            # Check for duplicate name (excluding current spec)
            existing_spec = self._db_session.query(ProjectTestSpec).filter(
                ProjectTestSpec.project_id == spec.project_id,
                ProjectTestSpec.name == request.name,
                ProjectTestSpec.id != spec_id
            ).first()
            
            if existing_spec:
                raise DuplicateTestSpecError(
                    f"Test specification with name '{request.name}' already exists in this project",
                    field="name"
                )
            
            spec.name = request.name
        
        # Update framework if provided
        if request.framework is not None:
            if isinstance(request.framework, str):
                if request.framework not in VALID_FRAMEWORKS:
                    raise TestSpecValidationError(
                        f"Invalid framework '{request.framework}'. Must be one of: {', '.join(VALID_FRAMEWORKS)}",
                        field="framework",
                        error_code="INVALID_FRAMEWORK"
                    )
                spec.framework = request.framework
            elif isinstance(request.framework, TestFramework):
                spec.framework = request.framework.value
            else:
                raise TestSpecValidationError(
                    "Framework must be a valid TestFramework value",
                    field="framework",
                    error_code="INVALID_FRAMEWORK"
                )
        
        # Update test_command if provided
        if request.test_command is not None:
            if not validate_test_command(request.test_command):
                raise TestSpecValidationError(
                    "Test command is required and must not be empty",
                    field="test_command",
                    error_code="INVALID_TEST_COMMAND"
                )
            spec.test_command = request.test_command
        
        # Update test_selection if provided
        if request.test_selection is not None:
            spec.test_selection = request.test_selection
        
        # Update build_ref if provided
        if request.build_ref is not None:
            if request.build_ref != 0:  # 0 means clear the reference
                build_spec = self._db_session.query(ProjectBuildSpec).filter(
                    ProjectBuildSpec.id == request.build_ref,
                    ProjectBuildSpec.project_id == spec.project_id
                ).first()
                if not build_spec:
                    raise TestSpecValidationError(
                        f"Build specification with ID '{request.build_ref}' not found in project",
                        field="build_ref",
                        error_code="BUILD_SPEC_NOT_FOUND"
                    )
                spec.build_ref = request.build_ref
            else:
                spec.build_ref = None
        
        # Update infra_ref if provided
        if request.infra_ref is not None:
            if request.infra_ref != 0:  # 0 means clear the reference
                infra_spec = self._db_session.query(ProjectInfraSpec).filter(
                    ProjectInfraSpec.id == request.infra_ref,
                    ProjectInfraSpec.project_id == spec.project_id
                ).first()
                if not infra_spec:
                    raise TestSpecValidationError(
                        f"Infrastructure specification with ID '{request.infra_ref}' not found in project",
                        field="infra_ref",
                        error_code="INFRA_SPEC_NOT_FOUND"
                    )
                spec.infra_ref = request.infra_ref
            else:
                spec.infra_ref = None
        
        # Update environment if provided
        if request.environment is not None:
            env_errors = validate_environment(request.environment)
            if env_errors:
                raise TestSpecValidationError(
                    f"Invalid environment: {'; '.join(env_errors)}",
                    field="environment",
                    error_code="INVALID_ENVIRONMENT"
                )
            spec.environment_json = request.environment
        
        # Update timeout if provided
        if request.timeout_minutes is not None:
            if request.timeout_minutes <= 0:
                raise TestSpecValidationError(
                    "Timeout must be a positive integer",
                    field="timeout_minutes",
                    error_code="INVALID_TIMEOUT"
                )
            spec.timeout_minutes = request.timeout_minutes
        
        # Update result_format if provided
        if request.result_format is not None:
            if isinstance(request.result_format, str):
                if request.result_format not in VALID_RESULT_FORMATS:
                    raise TestSpecValidationError(
                        f"Invalid result format '{request.result_format}'. Must be one of: {', '.join(VALID_RESULT_FORMATS)}",
                        field="result_format",
                        error_code="INVALID_RESULT_FORMAT"
                    )
                spec.result_format = request.result_format
            elif isinstance(request.result_format, TestResultFormat):
                spec.result_format = request.result_format.value
            else:
                raise TestSpecValidationError(
                    "Result format must be a valid TestResultFormat value",
                    field="result_format",
                    error_code="INVALID_RESULT_FORMAT"
                )
        
        # Update description if provided
        if request.description is not None:
            spec.description = request.description
        
        # Increment version (Requirements 8.2)
        spec.version = old_version + 1
        spec.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the specification update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='test_spec_updated',
                user_id=str(user_id),
                details={
                    "spec_id": spec.id,
                    "spec_name": spec.name,
                    "old_version": old_version,
                    "new_version": spec.version,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._test_spec_to_response(spec)


    def delete_spec(self, spec_id: int, user_id: str) -> None:
        """
        Delete test specification. Fails if active jobs exist.
        
        :param spec_id: The test specification's unique identifier
        :param user_id: The ID of the user deleting the specification
        :raises TestSpecNotFoundError: If specification is not found
        :raises TestSpecHasActiveJobsError: If specification has active jobs
        
        Validates: Requirements 8.3
        """
        from ccai.pychestrate.core.orm import ProjectTestSpec, ProjectTestJob, ProjectJobStatus
        
        spec = self._db_session.query(ProjectTestSpec).filter(
            ProjectTestSpec.id == spec_id
        ).first()
        
        if not spec:
            raise TestSpecNotFoundError(f"Test specification with ID '{spec_id}' not found")
        
        # Check for active jobs
        active_jobs = self._db_session.query(ProjectTestJob).filter(
            ProjectTestJob.spec_id == spec_id,
            ProjectTestJob.status.in_([
                ProjectJobStatus.PENDING.value,
                ProjectJobStatus.QUEUED.value,
                ProjectJobStatus.RUNNING.value
            ])
        ).count()
        
        if active_jobs > 0:
            raise TestSpecHasActiveJobsError(
                f"Cannot delete test specification '{spec.name}' with {active_jobs} active job(s)"
            )
        
        spec_name = spec.name
        project_id = spec.project_id
        
        # Delete the specification (cascades to jobs)
        self._db_session.delete(spec)
        self._db_session.commit()
        
        # Log the specification deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='test_spec_deleted',
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
    ) -> TestSpecListResponse:
        """
        List test specifications in a project.
        
        :param project_id: The project's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: TestSpecListResponse with paginated specification list
        """
        from ccai.pychestrate.core.orm import ProjectTestSpec
        
        query = self._db_session.query(ProjectTestSpec).filter(
            ProjectTestSpec.project_id == project_id
        )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        specs = query.order_by(ProjectTestSpec.name).offset(offset).limit(limit).all()
        
        return TestSpecListResponse(
            specs=[self._test_spec_to_response(spec) for spec in specs],
            total=total,
            offset=offset,
            limit=limit
        )

    
    # =========================================================================
    # Test Job Execution Operations
    # =========================================================================
    
    def trigger_job(
        self,
        request: TestJobTriggerRequest,
        user_id: str
    ) -> TestJobResponse:
        """
        Trigger a test job.
        
        :param request: The test job trigger request
        :param user_id: The ID of the user triggering the job
        :returns: TestJobResponse with the created job data
        :raises TestSpecNotFoundError: If specification is not found
        :raises BuildNotFoundError: If build is not found
        :raises InfraJobNotFoundError: If infrastructure job is not found
        
        Validates: Requirements 9.1
        """
        from ccai.pychestrate.core.orm import ProjectTestSpec, ProjectTestJob, ProjectJobStatus, ProjectBuild, ProjectInfraJob
        
        # Get the test specification
        spec = self._db_session.query(ProjectTestSpec).filter(
            ProjectTestSpec.id == request.spec_id
        ).first()
        
        if not spec:
            raise TestSpecNotFoundError(f"Test specification with ID '{request.spec_id}' not found")
        
        # Validate build_id if provided (Requirements 8.6)
        if request.build_id is not None:
            build = self._db_session.query(ProjectBuild).filter(
                ProjectBuild.id == request.build_id,
                ProjectBuild.project_id == spec.project_id
            ).first()
            if not build:
                raise BuildNotFoundError(
                    f"Build with ID '{request.build_id}' not found in project"
                )
        
        # Validate infra_job_id if provided (Requirements 8.7)
        if request.infra_job_id is not None:
            infra_job = self._db_session.query(ProjectInfraJob).filter(
                ProjectInfraJob.id == request.infra_job_id,
                ProjectInfraJob.project_id == spec.project_id
            ).first()
            if not infra_job:
                raise InfraJobNotFoundError(
                    f"Infrastructure job with ID '{request.infra_job_id}' not found in project"
                )
        
        # Create the test job record with status pending
        now = utc_now()
        
        job = ProjectTestJob(
            project_id=spec.project_id,
            spec_id=spec.id,
            spec_version=spec.version,
            build_id=request.build_id,
            infra_job_id=request.infra_job_id,
            status=ProjectJobStatus.PENDING.value,
            triggered_by_id=user_id,
            parameters_json=request.parameters,
            created_at=now
        )
        
        self._db_session.add(job)
        self._db_session.commit()
        
        # Log the job trigger event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='test_job_triggered',
                user_id=str(user_id),
                details={
                    "project_id": spec.project_id,
                    "spec_id": spec.id,
                    "spec_name": spec.name,
                    "job_id": job.id,
                    "build_id": request.build_id,
                    "infra_job_id": request.infra_job_id
                }
            )
        
        return self._test_job_to_response(job)
    
    def get_job(self, job_id: int) -> Optional[TestJobResponse]:
        """
        Get test job by ID.
        
        :param job_id: The test job's unique identifier
        :returns: TestJobResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import ProjectTestJob
        
        job = self._db_session.query(ProjectTestJob).filter(
            ProjectTestJob.id == job_id
        ).first()
        
        if not job:
            return None
        
        return self._test_job_to_response(job)
    
    def cancel_job(self, job_id: int, user_id: str) -> TestJobResponse:
        """
        Cancel a pending or running test job.
        
        :param job_id: The test job's unique identifier
        :param user_id: The ID of the user cancelling the job
        :returns: TestJobResponse with the updated job data
        :raises TestJobNotFoundError: If job is not found
        :raises TestJobCannotBeCancelledError: If job cannot be cancelled
        
        Validates: Requirements 9.5
        """
        from ccai.pychestrate.core.orm import ProjectTestJob, ProjectJobStatus
        
        job = self._db_session.query(ProjectTestJob).filter(
            ProjectTestJob.id == job_id
        ).first()
        
        if not job:
            raise TestJobNotFoundError(f"Test job with ID '{job_id}' not found")
        
        # Check if job can be cancelled
        cancellable_statuses = [
            ProjectJobStatus.PENDING.value,
            ProjectJobStatus.QUEUED.value,
            ProjectJobStatus.RUNNING.value
        ]
        
        if job.status not in cancellable_statuses:
            raise TestJobCannotBeCancelledError(
                f"Test job with status '{job.status}' cannot be cancelled"
            )
        
        # Update job status
        job.status = ProjectJobStatus.CANCELLED.value
        job.completed_at = utc_now()
        
        if job.started_at:
            job.duration_seconds = int((job.completed_at - job.started_at).total_seconds())
        
        self._db_session.commit()
        
        # Log the job cancellation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='test_job_cancelled',
                user_id=str(user_id),
                details={
                    "job_id": job.id,
                    "spec_id": job.spec_id,
                    "previous_status": job.status
                }
            )
        
        return self._test_job_to_response(job)
    
    def list_jobs(
        self,
        project_id: int = None,
        spec_id: int = None,
        status: JobStatus = None,
        offset: int = 0,
        limit: int = 50
    ) -> TestJobListResponse:
        """
        List test jobs with filtering.
        
        :param project_id: Optional project ID filter
        :param spec_id: Optional specification ID filter
        :param status: Optional status filter
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: TestJobListResponse with paginated job list
        
        Validates: Requirements 9.6
        """
        from ccai.pychestrate.core.orm import ProjectTestJob
        
        query = self._db_session.query(ProjectTestJob)
        
        # Apply filters
        if project_id is not None:
            query = query.filter(ProjectTestJob.project_id == project_id)
        
        if spec_id is not None:
            query = query.filter(ProjectTestJob.spec_id == spec_id)
        
        if status is not None:
            query = query.filter(ProjectTestJob.status == status.value)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (order by created_at descending for most recent first)
        jobs = query.order_by(ProjectTestJob.created_at.desc()).offset(offset).limit(limit).all()
        
        return TestJobListResponse(
            jobs=[self._test_job_to_response(job) for job in jobs],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def get_job_logs(self, job_id: int) -> str:
        """
        Get test job execution logs.
        
        :param job_id: The test job's unique identifier
        :returns: Job logs as a string
        :raises TestJobNotFoundError: If job is not found
        """
        from ccai.pychestrate.core.orm import ProjectTestJob
        
        job = self._db_session.query(ProjectTestJob).filter(
            ProjectTestJob.id == job_id
        ).first()
        
        if not job:
            raise TestJobNotFoundError(f"Test job with ID '{job_id}' not found")
        
        # If logs_path is set, read from file
        if job.logs_path and os.path.exists(job.logs_path):
            try:
                with open(job.logs_path, 'r') as f:
                    return f.read()
            except IOError:
                return ""
        
        return ""

    
    # =========================================================================
    # Test Results and Metrics Operations
    # =========================================================================
    
    def get_test_results(self, job_id: int) -> List[TestCaseResult]:
        """
        Get detailed test case results.
        
        :param job_id: The test job's unique identifier
        :returns: List of TestCaseResult objects
        :raises TestJobNotFoundError: If job is not found
        
        Validates: Requirements 9.7
        """
        from ccai.pychestrate.core.orm import ProjectTestJob, ProjectTestResult
        
        job = self._db_session.query(ProjectTestJob).filter(
            ProjectTestJob.id == job_id
        ).first()
        
        if not job:
            raise TestJobNotFoundError(f"Test job with ID '{job_id}' not found")
        
        results = self._db_session.query(ProjectTestResult).filter(
            ProjectTestResult.job_id == job_id
        ).order_by(ProjectTestResult.classname, ProjectTestResult.name).all()
        
        return [self._test_result_to_response(result) for result in results]
    
    def get_result_summary(self, job_id: int) -> TestResultSummary:
        """
        Get test result summary.
        
        :param job_id: The test job's unique identifier
        :returns: TestResultSummary object
        :raises TestJobNotFoundError: If job is not found
        
        Validates: Requirements 9.7
        """
        from ccai.pychestrate.core.orm import ProjectTestJob, ProjectTestResult
        
        job = self._db_session.query(ProjectTestJob).filter(
            ProjectTestJob.id == job_id
        ).first()
        
        if not job:
            raise TestJobNotFoundError(f"Test job with ID '{job_id}' not found")
        
        # If we have a cached summary, return it
        if job.result_summary_json:
            summary = job.result_summary_json
            return TestResultSummary(
                total=summary.get('total', 0),
                passed=summary.get('passed', 0),
                failed=summary.get('failed', 0),
                skipped=summary.get('skipped', 0),
                errors=summary.get('errors', 0),
                duration_seconds=summary.get('duration_seconds', 0.0)
            )
        
        # Calculate summary from results
        results = self._db_session.query(ProjectTestResult).filter(
            ProjectTestResult.job_id == job_id
        ).all()
        
        total = len(results)
        passed = sum(1 for r in results if r.status == TestCaseStatus.PASSED.value)
        failed = sum(1 for r in results if r.status == TestCaseStatus.FAILED.value)
        skipped = sum(1 for r in results if r.status == TestCaseStatus.SKIPPED.value)
        errors = sum(1 for r in results if r.status == TestCaseStatus.ERROR.value)
        duration_seconds = sum(r.duration_seconds or 0.0 for r in results)
        
        return TestResultSummary(
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration_seconds=duration_seconds
        )
    
    def get_test_metrics(
        self,
        project_id: int,
        spec_id: int = None,
        days: int = 30
    ) -> TestMetrics:
        """
        Get test metrics (pass rate, duration trends, flaky tests).
        
        :param project_id: The project's unique identifier
        :param spec_id: Optional specification ID filter
        :param days: Number of days to analyze
        :returns: TestMetrics object
        
        Validates: Requirements 9.7
        """
        from ccai.pychestrate.core.orm import ProjectTestJob, ProjectTestResult, ProjectJobStatus
        
        cutoff_date = utc_now() - timedelta(days=days)
        
        # Build query for completed jobs
        query = self._db_session.query(ProjectTestJob).filter(
            ProjectTestJob.project_id == project_id,
            ProjectTestJob.status.in_([
                ProjectJobStatus.SUCCEEDED.value,
                ProjectJobStatus.FAILED.value
            ]),
            ProjectTestJob.created_at >= cutoff_date
        )
        
        if spec_id is not None:
            query = query.filter(ProjectTestJob.spec_id == spec_id)
        
        jobs = query.all()
        
        total_runs = len(jobs)
        
        if total_runs == 0:
            return TestMetrics(
                total_runs=0,
                pass_rate=0.0,
                failure_rate=0.0,
                average_duration_seconds=0.0,
                duration_trend=[],
                flaky_test_count=0
            )
        
        # Calculate pass/failure rates
        passed_runs = sum(1 for j in jobs if j.status == ProjectJobStatus.SUCCEEDED.value)
        failed_runs = total_runs - passed_runs
        
        pass_rate = (passed_runs / total_runs) * 100 if total_runs > 0 else 0.0
        failure_rate = (failed_runs / total_runs) * 100 if total_runs > 0 else 0.0
        
        # Calculate average duration
        durations = [j.duration_seconds for j in jobs if j.duration_seconds is not None]
        average_duration = sum(durations) / len(durations) if durations else 0.0
        
        # Calculate duration trend (group by day)
        duration_trend = []
        jobs_by_date = {}
        for job in jobs:
            date_key = job.created_at.date().isoformat()
            if date_key not in jobs_by_date:
                jobs_by_date[date_key] = []
            if job.duration_seconds is not None:
                jobs_by_date[date_key].append(job.duration_seconds)
        
        for date_key in sorted(jobs_by_date.keys()):
            durations = jobs_by_date[date_key]
            if durations:
                duration_trend.append({
                    'date': date_key,
                    'average_duration': sum(durations) / len(durations),
                    'run_count': len(durations)
                })
        
        # Count flaky tests
        flaky_tests = self.get_flaky_tests(project_id, threshold=0.1, days=days)
        flaky_test_count = len(flaky_tests)
        
        return TestMetrics(
            total_runs=total_runs,
            pass_rate=pass_rate,
            failure_rate=failure_rate,
            average_duration_seconds=average_duration,
            duration_trend=duration_trend,
            flaky_test_count=flaky_test_count
        )
    
    def get_flaky_tests(
        self,
        project_id: int,
        threshold: float = 0.1,
        days: int = 30
    ) -> List[FlakyTest]:
        """
        Identify flaky tests based on inconsistent results.
        
        A test is considered flaky if it has both passed and failed within the
        time period and the failure rate is between threshold and (1 - threshold).
        
        :param project_id: The project's unique identifier
        :param threshold: Minimum flakiness threshold (default 0.1 = 10%)
        :param days: Number of days to analyze
        :returns: List of FlakyTest objects
        
        Validates: Requirements 9.7
        """
        from ccai.pychestrate.core.orm import ProjectTestJob, ProjectTestResult, ProjectJobStatus
        
        cutoff_date = utc_now() - timedelta(days=days)
        
        # Get all completed jobs in the time period
        job_ids = self._db_session.query(ProjectTestJob.id).filter(
            ProjectTestJob.project_id == project_id,
            ProjectTestJob.status.in_([
                ProjectJobStatus.SUCCEEDED.value,
                ProjectJobStatus.FAILED.value
            ]),
            ProjectTestJob.created_at >= cutoff_date
        ).all()
        
        job_ids = [j[0] for j in job_ids]
        
        if not job_ids:
            return []
        
        # Get all test results for these jobs
        results = self._db_session.query(ProjectTestResult).filter(
            ProjectTestResult.job_id.in_(job_ids)
        ).all()
        
        # Group results by test name and classname
        test_results = {}
        for result in results:
            key = (result.classname or "", result.name)
            if key not in test_results:
                test_results[key] = {'passed': 0, 'failed': 0, 'total': 0}
            
            test_results[key]['total'] += 1
            if result.status == TestCaseStatus.PASSED.value:
                test_results[key]['passed'] += 1
            elif result.status in [TestCaseStatus.FAILED.value, TestCaseStatus.ERROR.value]:
                test_results[key]['failed'] += 1
        
        # Identify flaky tests
        flaky_tests = []
        for (classname, name), counts in test_results.items():
            total = counts['total']
            passed = counts['passed']
            failed = counts['failed']
            
            if total < 2:
                continue  # Need at least 2 runs to determine flakiness
            
            # A test is flaky if it has both passed and failed
            if passed > 0 and failed > 0:
                flakiness_rate = min(passed, failed) / total
                
                # Only include if flakiness is above threshold
                if flakiness_rate >= threshold:
                    flaky_tests.append(FlakyTest(
                        name=name,
                        classname=classname,
                        flakiness_rate=flakiness_rate,
                        total_runs=total,
                        passed_count=passed,
                        failed_count=failed
                    ))
        
        # Sort by flakiness rate descending
        flaky_tests.sort(key=lambda x: x.flakiness_rate, reverse=True)
        
        return flaky_tests
