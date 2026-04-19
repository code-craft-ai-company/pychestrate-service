"""
.. module:: release_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the ReleaseManager class for release pipeline CRUD operations,
               release management, artifact management, channel management, and schedule management

.. moduleauthor:: Automation Mojo LLC

This module provides the ReleaseManager class which handles:
- Release pipeline CRUD operations (Requirements 17.1, 17.2, 17.3, 17.4, 17.5)
- Pipeline execution and tracking (Requirements 18.1-18.8)
- Release CRUD operations (Requirements 16.1-16.8)
- Artifact management (Requirements 19.1-19.7)
- Channel management (Requirements 20.1-20.7)
- Schedule management (Requirements 21.1-21.8)
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
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

class ReleaseStatus(str, Enum):
    """
        Enum-like class to represent the status of releases.
    """
    DRAFT = 'draft'
    PENDING_APPROVAL = 'pending_approval'
    APPROVED = 'approved'
    PUBLISHED = 'published'
    DEPRECATED = 'deprecated'
    RECALLED = 'recalled'


class PipelineStageType(str, Enum):
    """
        Enum-like class to represent the types of pipeline stages.
    """
    CHECKOUT = 'checkout'
    BUILD = 'build'
    TEST = 'test'
    PACKAGE = 'package'
    SIGN = 'sign'
    PUBLISH = 'publish'
    NOTIFY = 'notify'
    APPROVAL = 'approval'


class PipelineTriggerType(str, Enum):
    """
        Enum-like class to represent the trigger types for pipelines.
    """
    MANUAL = 'manual'
    TAG_PUSH = 'tag_push'
    BRANCH_MERGE = 'branch_merge'
    SCHEDULE = 'schedule'
    API = 'api'


class PipelineRunStatus(str, Enum):
    """
        Enum-like class to represent the status of pipeline runs.
    """
    PENDING = 'pending'
    RUNNING = 'running'
    PAUSED = 'paused'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class StageRunStatus(str, Enum):
    """
        Enum-like class to represent the status of stage runs.
    """
    PENDING = 'pending'
    RUNNING = 'running'
    AWAITING_APPROVAL = 'awaiting_approval'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class ArtifactType(str, Enum):
    """
        Enum-like class to represent the types of artifacts.
    """
    BINARY = 'binary'
    ARCHIVE = 'archive'
    CONTAINER_IMAGE = 'container_image'
    PACKAGE = 'package'
    DOCUMENTATION = 'documentation'
    CUSTOM = 'custom'


# =============================================================================
# Request/Response Dataclasses - Pipeline
# =============================================================================

@dataclass
class PipelineStageDefinition:
    """Definition of a pipeline stage."""
    name: str
    type: str
    config: Dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    continue_on_failure: bool = False


@dataclass
class ReleasePipelineCreateRequest:
    """Request dataclass for creating a new release pipeline."""
    name: str
    stages: List[Dict[str, Any]] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class ReleasePipelineUpdateRequest:
    """Request dataclass for updating an existing release pipeline."""
    name: Optional[str] = None
    stages: Optional[List[Dict[str, Any]]] = None
    triggers: Optional[List[str]] = None
    variables: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


@dataclass
class ReleasePipelineResponse:
    """Response dataclass for release pipeline data."""
    id: int
    project_id: int
    name: str
    stages: List[Dict[str, Any]]
    triggers: List[str]
    variables: Dict[str, Any]
    description: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass
class ReleasePipelineListResponse:
    """Response dataclass for paginated release pipeline list."""
    pipelines: List[ReleasePipelineResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Request/Response Dataclasses - Pipeline Run
# =============================================================================

@dataclass
class PipelineRunResponse:
    """Response dataclass for pipeline run data."""
    id: int
    pipeline_id: int
    pipeline_name: str
    pipeline_version: int
    status: PipelineRunStatus
    current_stage: Optional[str]
    triggered_by_id: str
    triggered_by_username: str
    trigger_type: PipelineTriggerType
    variables: Dict[str, Any]
    release_id: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


@dataclass
class PipelineRunListResponse:
    """Response dataclass for paginated pipeline run list."""
    runs: List[PipelineRunResponse]
    total: int
    offset: int
    limit: int


@dataclass
class StageRunResponse:
    """Response dataclass for stage run data."""
    id: int
    pipeline_run_id: int
    stage_name: str
    stage_type: str
    status: StageRunStatus
    requires_approval: bool
    approved_by_id: Optional[str]
    approved_by_username: Optional[str]
    approved_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    logs: Optional[str]
    output: Dict[str, Any]


# =============================================================================
# Request/Response Dataclasses - Release
# =============================================================================

@dataclass
class ReleaseCreateRequest:
    """Request dataclass for creating a new release."""
    version: str
    name: str
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReleaseUpdateRequest:
    """Request dataclass for updating an existing release."""
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ReleaseResponse:
    """Response dataclass for release data."""
    id: int
    project_id: int
    version: str
    name: str
    description: str
    status: ReleaseStatus
    metadata: Dict[str, Any]
    pipeline_run_id: Optional[int]
    schedule_id: Optional[int]
    artifact_count: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]
    published_by_id: Optional[str]
    published_by_username: Optional[str]


@dataclass
class ReleaseListResponse:
    """Response dataclass for paginated release list."""
    releases: List[ReleaseResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Request/Response Dataclasses - Artifact
# =============================================================================

@dataclass
class ReleaseArtifactResponse:
    """Response dataclass for release artifact data."""
    id: int
    release_id: int
    name: str
    artifact_type: ArtifactType
    size_bytes: int
    checksum: str
    checksum_algorithm: str
    storage_path: str
    download_url: str
    signature: Optional[str]
    created_at: datetime


@dataclass
class ReleaseArtifactListResponse:
    """Response dataclass for release artifact list."""
    artifacts: List[ReleaseArtifactResponse]
    total: int


# =============================================================================
# Request/Response Dataclasses - Channel
# =============================================================================

@dataclass
class ReleaseChannelCreateRequest:
    """Request dataclass for creating a new release channel."""
    name: str
    description: str = ""
    requires_approval: bool = False


@dataclass
class ReleaseChannelResponse:
    """Response dataclass for release channel data."""
    id: int
    project_id: int
    name: str
    description: str
    current_release_id: Optional[int]
    current_release_version: Optional[str]
    requires_approval: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class ReleaseChannelListResponse:
    """Response dataclass for release channel list."""
    channels: List[ReleaseChannelResponse]
    total: int


@dataclass
class ChannelHistoryEntry:
    """Response dataclass for channel history entry."""
    id: int
    channel_id: int
    release_id: int
    release_version: str
    release_name: str
    published_at: datetime
    published_by_id: str
    published_by_username: str


@dataclass
class ChannelHistoryResponse:
    """Response dataclass for channel history."""
    history: List[ChannelHistoryEntry]
    total: int
    offset: int
    limit: int


# =============================================================================
# Request/Response Dataclasses - Schedule
# =============================================================================

@dataclass
class ReleaseScheduleCreateRequest:
    """Request dataclass for creating a new release schedule."""
    name: str
    cron_expression: str
    pipeline_id: int
    variables: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    description: str = ""


@dataclass
class ReleaseScheduleUpdateRequest:
    """Request dataclass for updating an existing release schedule."""
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    pipeline_id: Optional[int] = None
    variables: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None


@dataclass
class ReleaseScheduleResponse:
    """Response dataclass for release schedule data."""
    id: int
    project_id: int
    name: str
    cron_expression: str
    pipeline_id: int
    pipeline_name: str
    variables: Dict[str, Any]
    enabled: bool
    description: str
    last_run_time: Optional[datetime]
    next_run_time: Optional[datetime]
    run_count: int
    created_at: datetime
    updated_at: datetime


@dataclass
class ReleaseScheduleListResponse:
    """Response dataclass for paginated release schedule list."""
    schedules: List[ReleaseScheduleResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Exceptions
# =============================================================================

class ReleasePipelineValidationError(Exception):
    """Exception raised when release pipeline validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "VALIDATION_ERROR"
        super().__init__(self.message)


class ReleasePipelineNotFoundError(Exception):
    """Exception raised when a release pipeline is not found."""
    
    def __init__(self, message: str, error_code: str = "RELEASE_PIPELINE_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateReleasePipelineError(Exception):
    """Exception raised when attempting to create a release pipeline with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "RELEASE_PIPELINE_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class ReleasePipelineHasActiveRunsError(Exception):
    """Exception raised when attempting to delete a release pipeline with active runs."""
    
    def __init__(self, message: str, error_code: str = "RELEASE_PIPELINE_HAS_ACTIVE_RUNS"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ProjectNotFoundError(Exception):
    """Exception raised when a project is not found."""
    
    def __init__(self, message: str, error_code: str = "PROJECT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class PipelineRunNotFoundError(Exception):
    """Exception raised when a pipeline run is not found."""
    
    def __init__(self, message: str, error_code: str = "PIPELINE_RUN_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class PipelineRunCannotBeCancelledError(Exception):
    """Exception raised when a pipeline run cannot be cancelled."""
    
    def __init__(self, message: str, error_code: str = "PIPELINE_RUN_CANNOT_BE_CANCELLED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class PipelineRunCannotBePausedError(Exception):
    """Exception raised when a pipeline run cannot be paused."""
    
    def __init__(self, message: str, error_code: str = "PIPELINE_RUN_CANNOT_BE_PAUSED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class PipelineRunCannotBeResumedError(Exception):
    """Exception raised when a pipeline run cannot be resumed."""
    
    def __init__(self, message: str, error_code: str = "PIPELINE_RUN_CANNOT_BE_RESUMED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class StageNotFoundError(Exception):
    """Exception raised when a stage is not found."""
    
    def __init__(self, message: str, error_code: str = "STAGE_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class StageCannotBeRetriedError(Exception):
    """Exception raised when a stage cannot be retried."""
    
    def __init__(self, message: str, error_code: str = "STAGE_CANNOT_BE_RETRIED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class StageCannotBeApprovedError(Exception):
    """Exception raised when a stage cannot be approved."""
    
    def __init__(self, message: str, error_code: str = "STAGE_CANNOT_BE_APPROVED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ReleaseNotFoundError(Exception):
    """Exception raised when a release is not found."""
    
    def __init__(self, message: str, error_code: str = "RELEASE_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateReleaseVersionError(Exception):
    """Exception raised when attempting to create a release with duplicate version."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "RELEASE_VERSION_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class ReleaseVersionValidationError(Exception):
    """Exception raised when release version validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "INVALID_RELEASE_VERSION"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class ArtifactNotFoundError(Exception):
    """Exception raised when an artifact is not found."""
    
    def __init__(self, message: str, error_code: str = "ARTIFACT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ArtifactChecksumMismatchError(Exception):
    """Exception raised when artifact checksum verification fails."""
    
    def __init__(self, message: str, error_code: str = "ARTIFACT_CHECKSUM_MISMATCH"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ReleaseChannelNotFoundError(Exception):
    """Exception raised when a release channel is not found."""
    
    def __init__(self, message: str, error_code: str = "RELEASE_CHANNEL_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateReleaseChannelError(Exception):
    """Exception raised when attempting to create a release channel with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "RELEASE_CHANNEL_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class ReleaseScheduleNotFoundError(Exception):
    """Exception raised when a release schedule is not found."""
    
    def __init__(self, message: str, error_code: str = "RELEASE_SCHEDULE_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateReleaseScheduleError(Exception):
    """Exception raised when attempting to create a release schedule with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "RELEASE_SCHEDULE_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class CronExpressionValidationError(Exception):
    """Exception raised when cron expression validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "INVALID_CRON_EXPRESSION"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


# =============================================================================
# Validation Constants
# =============================================================================

# Pipeline name validation: alphanumeric, underscore, hyphen, period
# Must start with alphanumeric, 1-128 characters
PIPELINE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}\Z')

# Valid pipeline stage types
VALID_STAGE_TYPES = {'checkout', 'build', 'test', 'package', 'sign', 'publish', 'notify', 'approval'}

# Valid pipeline trigger types
VALID_TRIGGER_TYPES = {'manual', 'tag_push', 'branch_merge', 'schedule', 'api'}

# Semantic version pattern (major.minor.patch with optional pre-release and build metadata)
SEMVER_PATTERN = re.compile(
    r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
    r'(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?'
    r'(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
)

# Cron expression pattern (5 fields: minute, hour, day-of-month, month, day-of-week)
CRON_FIELD_PATTERN = re.compile(r'^(\*|[0-9]+(-[0-9]+)?(/[0-9]+)?(,[0-9]+(-[0-9]+)?(/[0-9]+)?)*)$')


# =============================================================================
# Validation Functions
# =============================================================================

def validate_pipeline_name(name: str) -> bool:
    """
    Validate that a release pipeline name contains only alphanumeric characters,
    underscores, hyphens, and periods.
    
    :param name: The release pipeline name to validate
    :returns: True if valid, False otherwise
    """
    if not name:
        return False
    
    if not PIPELINE_NAME_PATTERN.match(name):
        return False
    
    return True


def validate_pipeline_stages(stages: List[Dict[str, Any]]) -> List[str]:
    """
    Validate pipeline stages syntax and ordering.
    
    :param stages: List of pipeline stage definitions
    :returns: List of validation error messages (empty if valid)
    
    Validates: Requirements 17.4, 17.5
    """
    errors = []
    
    if not isinstance(stages, list):
        errors.append("Stages must be a list")
        return errors
    
    if len(stages) == 0:
        errors.append("Pipeline must have at least one stage")
        return errors
    
    stage_names = set()
    
    for i, stage in enumerate(stages):
        if not isinstance(stage, dict):
            errors.append(f"Stage {i}: must be a dictionary")
            continue
        
        # Check required fields
        if 'name' not in stage:
            errors.append(f"Stage {i}: missing required field 'name'")
        elif not isinstance(stage['name'], str) or not stage['name'].strip():
            errors.append(f"Stage {i}: 'name' must be a non-empty string")
        else:
            # Check for duplicate stage names
            if stage['name'] in stage_names:
                errors.append(f"Stage {i}: duplicate stage name '{stage['name']}'")
            stage_names.add(stage['name'])
        
        if 'type' not in stage:
            errors.append(f"Stage {i}: missing required field 'type'")
        elif stage['type'] not in VALID_STAGE_TYPES:
            errors.append(f"Stage {i}: invalid type '{stage['type']}'. Must be one of: {', '.join(VALID_STAGE_TYPES)}")
        
        # Check config field
        if 'config' in stage and not isinstance(stage.get('config'), dict):
            errors.append(f"Stage {i}: 'config' must be a dictionary")
        
        # Check requires_approval field
        if 'requires_approval' in stage and not isinstance(stage.get('requires_approval'), bool):
            errors.append(f"Stage {i}: 'requires_approval' must be a boolean")
        
        # Check continue_on_failure field
        if 'continue_on_failure' in stage and not isinstance(stage.get('continue_on_failure'), bool):
            errors.append(f"Stage {i}: 'continue_on_failure' must be a boolean")
    
    return errors


def validate_pipeline_triggers(triggers: List[str]) -> List[str]:
    """
    Validate pipeline trigger types.
    
    :param triggers: List of trigger type strings
    :returns: List of validation error messages (empty if valid)
    """
    errors = []
    
    if not isinstance(triggers, list):
        errors.append("Triggers must be a list")
        return errors
    
    for i, trigger in enumerate(triggers):
        if not isinstance(trigger, str):
            errors.append(f"Trigger {i}: must be a string")
        elif trigger not in VALID_TRIGGER_TYPES:
            errors.append(f"Trigger {i}: invalid type '{trigger}'. Must be one of: {', '.join(VALID_TRIGGER_TYPES)}")
    
    return errors


def validate_semantic_version(version: str) -> bool:
    """
    Validate that a version string conforms to semantic versioning.
    
    :param version: The version string to validate
    :returns: True if valid, False otherwise
    
    Validates: Requirements 16.5
    """
    if not version:
        return False
    
    return bool(SEMVER_PATTERN.match(version))


def validate_cron_expression(cron_expression: str) -> bool:
    """
    Validate that a cron expression conforms to standard 5-field cron syntax.
    
    :param cron_expression: The cron expression to validate
    :returns: True if valid, False otherwise
    
    Validates: Requirements 21.3
    """
    if not cron_expression:
        return False
    
    fields = cron_expression.strip().split()
    
    if len(fields) != 5:
        return False
    
    # Validate each field
    field_ranges = [
        (0, 59),   # minute
        (0, 23),   # hour
        (1, 31),   # day of month
        (1, 12),   # month
        (0, 6),    # day of week
    ]
    
    for i, (field, (min_val, max_val)) in enumerate(zip(fields, field_ranges)):
        if not _validate_cron_field(field, min_val, max_val):
            return False
    
    return True


def _validate_cron_field(field: str, min_val: int, max_val: int) -> bool:
    """
    Validate a single cron field.
    
    :param field: The cron field to validate
    :param min_val: Minimum allowed value
    :param max_val: Maximum allowed value
    :returns: True if valid, False otherwise
    """
    if field == '*':
        return True
    
    # Handle comma-separated values
    parts = field.split(',')
    
    for part in parts:
        # Handle step values (e.g., */5, 1-10/2)
        if '/' in part:
            range_part, step = part.split('/', 1)
            try:
                step_val = int(step)
                if step_val <= 0:
                    return False
            except ValueError:
                return False
            part = range_part
        
        # Handle range values (e.g., 1-10)
        if '-' in part and part != '*':
            try:
                start, end = part.split('-', 1)
                start_val = int(start)
                end_val = int(end)
                if start_val < min_val or end_val > max_val or start_val > end_val:
                    return False
            except ValueError:
                return False
        elif part != '*':
            # Single value
            try:
                val = int(part)
                if val < min_val or val > max_val:
                    return False
            except ValueError:
                return False
    
    return True



# =============================================================================
# ReleaseManager Class
# =============================================================================


# =============================================================================
# Request/Response Dataclasses - Calendar Events
# =============================================================================

@dataclass
class ReleaseEventCreateRequest:
    """Request dataclass for creating a new release event."""
    release_id: int
    name: str
    start_time: datetime
    end_time: datetime
    description: str = ""


@dataclass
class ReleaseEventUpdateRequest:
    """Request dataclass for updating an existing release event."""
    name: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None


@dataclass
class ReleaseEventResponse:
    """Response dataclass for release event data."""
    id: int
    project_id: int
    release_id: int
    release_version: str
    release_name: str
    name: str
    description: str
    start_time: datetime
    end_time: datetime
    created_at: datetime
    updated_at: datetime
    phases: List['PhaseEventResponse']


@dataclass
class ReleaseEventListResponse:
    """Response dataclass for paginated release event list."""
    events: List[ReleaseEventResponse]
    total: int
    offset: int
    limit: int


@dataclass
class PhaseEventCreateRequest:
    """Request dataclass for creating a new phase event."""
    release_event_id: int
    name: str
    start_time: datetime
    end_time: datetime
    order: int
    description: str = ""


@dataclass
class PhaseEventUpdateRequest:
    """Request dataclass for updating an existing phase event."""
    name: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    order: Optional[int] = None
    status: Optional[str] = None
    description: Optional[str] = None


@dataclass
class PhaseEventResponse:
    """Response dataclass for phase event data."""
    id: int
    release_event_id: int
    name: str
    description: str
    start_time: datetime
    end_time: datetime
    order: int
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass
class PhaseEventListResponse:
    """Response dataclass for phase event list."""
    phases: List[PhaseEventResponse]
    total: int


@dataclass
class ReleaseBranchCreateRequest:
    """Request dataclass for creating a release branch association."""
    release_id: int
    repository_id: int
    branch_name: str
    description: str = ""


@dataclass
class ReleaseBranchResponse:
    """Response dataclass for release branch data."""
    id: int
    release_id: int
    repository_id: int
    repository_name: str
    branch_name: str
    description: str
    created_at: datetime


@dataclass
class ReleaseBranchListResponse:
    """Response dataclass for release branch list."""
    branches: List[ReleaseBranchResponse]
    total: int


@dataclass
class MergeEventCreateRequest:
    """Request dataclass for creating a merge event."""
    release_id: int
    repository_id: int
    source_branch: str
    target_branch: str
    name: str
    scheduled_time: datetime
    description: str = ""


@dataclass
class MergeEventUpdateRequest:
    """Request dataclass for updating a merge event."""
    name: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    status: Optional[str] = None
    description: Optional[str] = None


@dataclass
class MergeEventResponse:
    """Response dataclass for merge event data."""
    id: int
    project_id: int
    release_id: int
    repository_id: int
    repository_name: str
    source_branch: str
    target_branch: str
    name: str
    description: str
    scheduled_time: datetime
    status: str
    executed_at: Optional[datetime]
    executed_by_id: Optional[str]
    executed_by_username: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class MergeEventListResponse:
    """Response dataclass for paginated merge event list."""
    events: List[MergeEventResponse]
    total: int
    offset: int
    limit: int


@dataclass
class PullEventCreateRequest:
    """Request dataclass for creating a pull event."""
    release_id: int
    repository_id: int
    source_branch: str
    target_branch: str
    name: str
    scheduled_time: datetime
    description: str = ""


@dataclass
class PullEventUpdateRequest:
    """Request dataclass for updating a pull event."""
    name: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    status: Optional[str] = None
    description: Optional[str] = None


@dataclass
class PullEventResponse:
    """Response dataclass for pull event data."""
    id: int
    project_id: int
    release_id: int
    repository_id: int
    repository_name: str
    source_branch: str
    target_branch: str
    name: str
    description: str
    scheduled_time: datetime
    status: str
    executed_at: Optional[datetime]
    executed_by_id: Optional[str]
    executed_by_username: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class PullEventListResponse:
    """Response dataclass for paginated pull event list."""
    events: List[PullEventResponse]
    total: int
    offset: int
    limit: int


@dataclass
class CalendarEventResponse:
    """Response dataclass for unified calendar event view."""
    id: int
    project_id: int
    event_type: str
    name: str
    description: str
    start_time: datetime
    end_time: datetime
    created_at: datetime
    updated_at: datetime
    # Additional fields based on event type
    release_id: Optional[int] = None
    release_version: Optional[str] = None
    repository_id: Optional[int] = None
    repository_name: Optional[str] = None
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    status: Optional[str] = None


@dataclass
class CalendarEventsResponse:
    """Response dataclass for calendar events list."""
    events: List[CalendarEventResponse]
    total: int


# =============================================================================
# Calendar Event Exceptions
# =============================================================================

class ReleaseEventNotFoundError(Exception):
    """Exception raised when a release event is not found."""
    
    def __init__(self, message: str, error_code: str = "RELEASE_EVENT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ReleaseEventValidationError(Exception):
    """Exception raised when release event validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "RELEASE_EVENT_VALIDATION_ERROR"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class PhaseEventNotFoundError(Exception):
    """Exception raised when a phase event is not found."""
    
    def __init__(self, message: str, error_code: str = "PHASE_EVENT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class PhaseEventValidationError(Exception):
    """Exception raised when phase event validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "PHASE_EVENT_VALIDATION_ERROR"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class ReleaseBranchNotFoundError(Exception):
    """Exception raised when a release branch is not found."""
    
    def __init__(self, message: str, error_code: str = "RELEASE_BRANCH_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateReleaseBranchError(Exception):
    """Exception raised when attempting to create a duplicate release branch."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "RELEASE_BRANCH_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class MergeEventNotFoundError(Exception):
    """Exception raised when a merge event is not found."""
    
    def __init__(self, message: str, error_code: str = "MERGE_EVENT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class MergeEventValidationError(Exception):
    """Exception raised when merge event validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "MERGE_EVENT_VALIDATION_ERROR"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class PullEventNotFoundError(Exception):
    """Exception raised when a pull event is not found."""
    
    def __init__(self, message: str, error_code: str = "PULL_EVENT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class PullEventValidationError(Exception):
    """Exception raised when pull event validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "PULL_EVENT_VALIDATION_ERROR"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class RepositoryNotFoundError(Exception):
    """Exception raised when a repository is not found."""
    
    def __init__(self, message: str, error_code: str = "REPOSITORY_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)




class ReleaseManager:
    """
    Manager class for release pipeline CRUD operations, release management,
    artifact management, channel management, and schedule management.
    
    This class handles all release-related operations including:
    - Release pipeline creation with validation
    - Release pipeline retrieval by ID
    - Release pipeline updates with versioning
    - Release pipeline deletion with active run check
    - Pipeline execution and tracking
    - Release CRUD operations
    - Artifact management
    - Channel management
    - Schedule management
    
    Validates: Requirements 16.1-16.8, 17.1-17.5, 18.1-18.8, 19.1-19.7, 20.1-20.7, 21.1-21.8
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None, artifact_storage_path: str = None):
        """
        Initialize the ReleaseManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        :param artifact_storage_path: Optional path for artifact storage
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
        self._artifact_storage_path = artifact_storage_path or "/var/lib/pychestrate/artifacts"
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def _validate_pipeline_create_request(self, request: ReleasePipelineCreateRequest) -> None:
        """
        Validate a release pipeline creation request.
        
        :param request: The release pipeline creation request to validate
        :raises ReleasePipelineValidationError: If validation fails
        """
        if not validate_pipeline_name(request.name):
            raise ReleasePipelineValidationError(
                "Release pipeline name must be 1-128 characters, start with alphanumeric, "
                "and contain only alphanumeric characters, underscores, hyphens, and periods",
                field="name",
                error_code="INVALID_PIPELINE_NAME"
            )
        
        # Validate stages syntax
        stage_errors = validate_pipeline_stages(request.stages)
        if stage_errors:
            raise ReleasePipelineValidationError(
                f"Invalid pipeline stages: {'; '.join(stage_errors)}",
                field="stages",
                error_code="INVALID_STAGES"
            )
        
        # Validate triggers
        trigger_errors = validate_pipeline_triggers(request.triggers)
        if trigger_errors:
            raise ReleasePipelineValidationError(
                f"Invalid pipeline triggers: {'; '.join(trigger_errors)}",
                field="triggers",
                error_code="INVALID_TRIGGERS"
            )
    
    def validate_pipeline(self, pipeline: ReleasePipelineCreateRequest) -> List[str]:
        """
        Validate pipeline definition. Returns list of errors.
        
        :param pipeline: The release pipeline to validate
        :returns: List of validation error messages (empty if valid)
        
        Validates: Requirements 17.4, 17.5
        """
        errors = []
        
        # Validate name
        if not validate_pipeline_name(pipeline.name):
            errors.append("Name must be 1-128 characters, start with alphanumeric, "
                         "and contain only alphanumeric characters, underscores, hyphens, and periods")
        
        # Validate stages
        stage_errors = validate_pipeline_stages(pipeline.stages)
        errors.extend(stage_errors)
        
        # Validate triggers
        trigger_errors = validate_pipeline_triggers(pipeline.triggers)
        errors.extend(trigger_errors)
        
        # Validate variables
        if pipeline.variables:
            if not isinstance(pipeline.variables, dict):
                errors.append("Variables must be a dictionary")
        
        return errors
    
    def validate_version(self, version: str, pattern: str = None) -> bool:
        """
        Validate version string (semver or custom pattern).
        
        :param version: The version string to validate
        :param pattern: Optional custom regex pattern for validation
        :returns: True if valid, False otherwise
        
        Validates: Requirements 16.5
        """
        if not version:
            return False
        
        if pattern:
            try:
                custom_pattern = re.compile(pattern)
                return bool(custom_pattern.match(version))
            except re.error:
                return False
        
        return validate_semantic_version(version)
    
    def validate_cron_expression(self, cron_expression: str) -> bool:
        """
        Validate cron expression syntax.
        
        :param cron_expression: The cron expression to validate
        :returns: True if valid, False otherwise
        
        Validates: Requirements 21.3
        """
        return validate_cron_expression(cron_expression)
    
    # =========================================================================
    # Helper Methods - Pipeline
    # =========================================================================
    
    def _pipeline_to_response(self, pipeline) -> ReleasePipelineResponse:
        """
        Convert a ProjectReleasePipeline ORM object to a ReleasePipelineResponse.
        
        :param pipeline: The ProjectReleasePipeline ORM object
        :returns: ReleasePipelineResponse dataclass
        """
        return ReleasePipelineResponse(
            id=pipeline.id,
            project_id=pipeline.project_id,
            name=pipeline.name,
            stages=pipeline.stages_json or [],
            triggers=pipeline.triggers_json or [],
            variables=pipeline.variables_json or {},
            description=pipeline.description or "",
            version=pipeline.version,
            created_at=pipeline.created_at,
            updated_at=pipeline.updated_at
        )
    
    def _pipeline_run_to_response(self, run) -> PipelineRunResponse:
        """
        Convert a ProjectPipelineRun ORM object to a PipelineRunResponse.
        
        :param run: The ProjectPipelineRun ORM object
        :returns: PipelineRunResponse dataclass
        """
        from automojo.pychestrate.core.orm import User
        
        pipeline_name = run.pipeline.name if run.pipeline else ""
        
        # Get triggered by username
        triggered_by_username = ""
        if run.triggered_by_id:
            user = self._db_session.query(User).filter(User.id == run.triggered_by_id).first()
            if user:
                triggered_by_username = user.login
        
        return PipelineRunResponse(
            id=run.id,
            pipeline_id=run.pipeline_id,
            pipeline_name=pipeline_name,
            pipeline_version=run.pipeline_version,
            status=PipelineRunStatus(run.status),
            current_stage=run.current_stage,
            triggered_by_id=str(run.triggered_by_id),
            triggered_by_username=triggered_by_username,
            trigger_type=PipelineTriggerType(run.trigger_type),
            variables=run.variables_json or {},
            release_id=run.release_id,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at
        )
    
    def _stage_run_to_response(self, stage_run) -> StageRunResponse:
        """
        Convert a ProjectStageRun ORM object to a StageRunResponse.
        
        :param stage_run: The ProjectStageRun ORM object
        :returns: StageRunResponse dataclass
        """
        from automojo.pychestrate.core.orm import User
        
        # Get approved by username
        approved_by_username = None
        if stage_run.approved_by_id:
            user = self._db_session.query(User).filter(User.id == stage_run.approved_by_id).first()
            if user:
                approved_by_username = user.login
        
        # Read logs if path exists
        logs = None
        if stage_run.logs_path and os.path.exists(stage_run.logs_path):
            try:
                with open(stage_run.logs_path, 'r') as f:
                    logs = f.read()
            except IOError:
                pass
        
        return StageRunResponse(
            id=stage_run.id,
            pipeline_run_id=stage_run.pipeline_run_id,
            stage_name=stage_run.stage_name,
            stage_type=stage_run.stage_type,
            status=StageRunStatus(stage_run.status),
            requires_approval=stage_run.requires_approval,
            approved_by_id=str(stage_run.approved_by_id) if stage_run.approved_by_id else None,
            approved_by_username=approved_by_username,
            approved_at=stage_run.approved_at,
            started_at=stage_run.started_at,
            completed_at=stage_run.completed_at,
            logs=logs,
            output=stage_run.output_json or {}
        )
    
    # =========================================================================
    # Helper Methods - Release
    # =========================================================================
    
    def _release_to_response(self, release) -> ReleaseResponse:
        """
        Convert a ProjectRelease ORM object to a ReleaseResponse.
        
        :param release: The ProjectRelease ORM object
        :returns: ReleaseResponse dataclass
        """
        from automojo.pychestrate.core.orm import User
        
        # Get published by username
        published_by_username = None
        if release.published_by_id:
            user = self._db_session.query(User).filter(User.id == release.published_by_id).first()
            if user:
                published_by_username = user.login
        
        # Count artifacts
        artifact_count = len(release.artifacts) if release.artifacts else 0
        
        return ReleaseResponse(
            id=release.id,
            project_id=release.project_id,
            version=release.version,
            name=release.name,
            description=release.description or "",
            status=ReleaseStatus(release.status),
            metadata=release.metadata_json or {},
            pipeline_run_id=release.pipeline_run_id,
            schedule_id=release.schedule_id,
            artifact_count=artifact_count,
            created_at=release.created_at,
            updated_at=release.updated_at,
            published_at=release.published_at,
            published_by_id=str(release.published_by_id) if release.published_by_id else None,
            published_by_username=published_by_username
        )
    
    def _artifact_to_response(self, artifact) -> ReleaseArtifactResponse:
        """
        Convert a ProjectReleaseArtifact ORM object to a ReleaseArtifactResponse.
        
        :param artifact: The ProjectReleaseArtifact ORM object
        :returns: ReleaseArtifactResponse dataclass
        """
        # Generate download URL
        download_url = f"/api/v1/releases/{artifact.release_id}/artifacts/{artifact.id}/download"
        
        return ReleaseArtifactResponse(
            id=artifact.id,
            release_id=artifact.release_id,
            name=artifact.name,
            artifact_type=ArtifactType(artifact.artifact_type),
            size_bytes=artifact.size_bytes,
            checksum=artifact.checksum,
            checksum_algorithm=artifact.checksum_algorithm,
            storage_path=artifact.storage_path,
            download_url=download_url,
            signature=artifact.signature,
            created_at=artifact.created_at
        )
    
    def _channel_to_response(self, channel) -> ReleaseChannelResponse:
        """
        Convert a ProjectReleaseChannel ORM object to a ReleaseChannelResponse.
        
        :param channel: The ProjectReleaseChannel ORM object
        :returns: ReleaseChannelResponse dataclass
        """
        from automojo.pychestrate.core.orm import ProjectRelease
        
        # Get current release version
        current_release_version = None
        if channel.current_release_id:
            release = self._db_session.query(ProjectRelease).filter(
                ProjectRelease.id == channel.current_release_id
            ).first()
            if release:
                current_release_version = release.version
        
        return ReleaseChannelResponse(
            id=channel.id,
            project_id=channel.project_id,
            name=channel.name,
            description=channel.description or "",
            current_release_id=channel.current_release_id,
            current_release_version=current_release_version,
            requires_approval=channel.requires_approval,
            created_at=channel.created_at,
            updated_at=channel.updated_at
        )
    
    def _schedule_to_response(self, schedule) -> ReleaseScheduleResponse:
        """
        Convert a ProjectReleaseSchedule ORM object to a ReleaseScheduleResponse.
        
        :param schedule: The ProjectReleaseSchedule ORM object
        :returns: ReleaseScheduleResponse dataclass
        """
        pipeline_name = schedule.pipeline.name if schedule.pipeline else ""
        
        return ReleaseScheduleResponse(
            id=schedule.id,
            project_id=schedule.project_id,
            name=schedule.name,
            cron_expression=schedule.cron_expression,
            pipeline_id=schedule.pipeline_id,
            pipeline_name=pipeline_name,
            variables=schedule.variables_json or {},
            enabled=schedule.enabled,
            description=schedule.description or "",
            last_run_time=schedule.last_run_time,
            next_run_time=schedule.next_run_time,
            run_count=schedule.run_count,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at
        )
    
    # =========================================================================
    # Release Pipeline CRUD Operations
    # =========================================================================
    
    def create_pipeline(
        self,
        project_id: int,
        request: ReleasePipelineCreateRequest,
        user_id: str
    ) -> ReleasePipelineResponse:
        """
        Create a release pipeline.
        
        :param project_id: The project's unique identifier
        :param request: The release pipeline creation request
        :param user_id: The ID of the user creating the pipeline
        :returns: ReleasePipelineResponse with the created pipeline data
        :raises ProjectNotFoundError: If project is not found
        :raises ReleasePipelineValidationError: If validation fails
        :raises DuplicateReleasePipelineError: If pipeline name already exists in project
        
        Validates: Requirements 17.1
        """
        from automojo.pychestrate.core.orm import Project, ProjectReleasePipeline
        
        # Validate the request
        self._validate_pipeline_create_request(request)
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check for duplicate name within project
        existing_pipeline = self._db_session.query(ProjectReleasePipeline).filter(
            ProjectReleasePipeline.project_id == project_id,
            ProjectReleasePipeline.name == request.name
        ).first()
        
        if existing_pipeline:
            raise DuplicateReleasePipelineError(
                f"Release pipeline with name '{request.name}' already exists in project '{project.name}'",
                field="name"
            )
        
        # Create the release pipeline
        now = utc_now()
        
        pipeline = ProjectReleasePipeline(
            project_id=project_id,
            name=request.name,
            stages_json=request.stages,
            triggers_json=request.triggers,
            variables_json=request.variables,
            description=request.description or "",
            version=1,
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(pipeline)
        self._db_session.commit()
        
        # Log the pipeline creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_pipeline_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "pipeline_id": pipeline.id,
                    "pipeline_name": pipeline.name,
                    "stage_count": len(request.stages)
                }
            )
        
        return self._pipeline_to_response(pipeline)
    
    def get_pipeline(self, pipeline_id: int) -> Optional[ReleasePipelineResponse]:
        """
        Get release pipeline by ID.
        
        :param pipeline_id: The release pipeline's unique identifier
        :returns: ReleasePipelineResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectReleasePipeline
        
        pipeline = self._db_session.query(ProjectReleasePipeline).filter(
            ProjectReleasePipeline.id == pipeline_id
        ).first()
        
        if not pipeline:
            return None
        
        return self._pipeline_to_response(pipeline)
    
    def update_pipeline(
        self,
        pipeline_id: int,
        request: ReleasePipelineUpdateRequest,
        user_id: str
    ) -> ReleasePipelineResponse:
        """
        Update release pipeline (creates new version).
        
        :param pipeline_id: The release pipeline's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: ReleasePipelineResponse with the updated pipeline data
        :raises ReleasePipelineNotFoundError: If pipeline is not found
        :raises ReleasePipelineValidationError: If validation fails
        :raises DuplicateReleasePipelineError: If new name already exists in project
        
        Validates: Requirements 17.2
        """
        from automojo.pychestrate.core.orm import ProjectReleasePipeline
        
        pipeline = self._db_session.query(ProjectReleasePipeline).filter(
            ProjectReleasePipeline.id == pipeline_id
        ).first()
        
        if not pipeline:
            raise ReleasePipelineNotFoundError(f"Release pipeline with ID '{pipeline_id}' not found")
        
        old_version = pipeline.version
        
        # Update name if provided
        if request.name is not None:
            if not validate_pipeline_name(request.name):
                raise ReleasePipelineValidationError(
                    "Release pipeline name must be 1-128 characters, start with alphanumeric, "
                    "and contain only alphanumeric characters, underscores, hyphens, and periods",
                    field="name",
                    error_code="INVALID_PIPELINE_NAME"
                )
            
            # Check for duplicate name (excluding current pipeline)
            existing_pipeline = self._db_session.query(ProjectReleasePipeline).filter(
                ProjectReleasePipeline.project_id == pipeline.project_id,
                ProjectReleasePipeline.name == request.name,
                ProjectReleasePipeline.id != pipeline_id
            ).first()
            
            if existing_pipeline:
                raise DuplicateReleasePipelineError(
                    f"Release pipeline with name '{request.name}' already exists in this project",
                    field="name"
                )
            
            pipeline.name = request.name
        
        # Update stages if provided
        if request.stages is not None:
            stage_errors = validate_pipeline_stages(request.stages)
            if stage_errors:
                raise ReleasePipelineValidationError(
                    f"Invalid pipeline stages: {'; '.join(stage_errors)}",
                    field="stages",
                    error_code="INVALID_STAGES"
                )
            pipeline.stages_json = request.stages
        
        # Update triggers if provided
        if request.triggers is not None:
            trigger_errors = validate_pipeline_triggers(request.triggers)
            if trigger_errors:
                raise ReleasePipelineValidationError(
                    f"Invalid pipeline triggers: {'; '.join(trigger_errors)}",
                    field="triggers",
                    error_code="INVALID_TRIGGERS"
                )
            pipeline.triggers_json = request.triggers
        
        # Update variables if provided
        if request.variables is not None:
            pipeline.variables_json = request.variables
        
        # Update description if provided
        if request.description is not None:
            pipeline.description = request.description
        
        # Increment version (Requirements 17.2)
        pipeline.version = old_version + 1
        pipeline.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the pipeline update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_pipeline_updated',
                user_id=str(user_id),
                details={
                    "pipeline_id": pipeline.id,
                    "pipeline_name": pipeline.name,
                    "old_version": old_version,
                    "new_version": pipeline.version,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._pipeline_to_response(pipeline)
    
    def delete_pipeline(self, pipeline_id: int, user_id: str) -> None:
        """
        Delete release pipeline. Fails if active runs exist.
        
        :param pipeline_id: The release pipeline's unique identifier
        :param user_id: The ID of the user deleting the pipeline
        :raises ReleasePipelineNotFoundError: If pipeline is not found
        :raises ReleasePipelineHasActiveRunsError: If pipeline has active runs
        
        Validates: Requirements 17.3
        """
        from automojo.pychestrate.core.orm import ProjectReleasePipeline, ProjectPipelineRun
        
        pipeline = self._db_session.query(ProjectReleasePipeline).filter(
            ProjectReleasePipeline.id == pipeline_id
        ).first()
        
        if not pipeline:
            raise ReleasePipelineNotFoundError(f"Release pipeline with ID '{pipeline_id}' not found")
        
        # Check for active runs
        active_runs = self._db_session.query(ProjectPipelineRun).filter(
            ProjectPipelineRun.pipeline_id == pipeline_id,
            ProjectPipelineRun.status.in_([
                PipelineRunStatus.PENDING.value,
                PipelineRunStatus.RUNNING.value,
                PipelineRunStatus.PAUSED.value
            ])
        ).count()
        
        if active_runs > 0:
            raise ReleasePipelineHasActiveRunsError(
                f"Cannot delete release pipeline '{pipeline.name}' with {active_runs} active run(s)"
            )
        
        pipeline_name = pipeline.name
        project_id = pipeline.project_id
        
        # Delete the pipeline (cascades to runs)
        self._db_session.delete(pipeline)
        self._db_session.commit()
        
        # Log the pipeline deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_pipeline_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "pipeline_id": pipeline_id,
                    "pipeline_name": pipeline_name
                }
            )
    
    def list_pipelines(
        self,
        project_id: int,
        offset: int = 0,
        limit: int = 50
    ) -> ReleasePipelineListResponse:
        """
        List release pipelines in a project.
        
        :param project_id: The project's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: ReleasePipelineListResponse with paginated pipeline list
        """
        from automojo.pychestrate.core.orm import ProjectReleasePipeline
        
        query = self._db_session.query(ProjectReleasePipeline).filter(
            ProjectReleasePipeline.project_id == project_id
        )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        pipelines = query.order_by(ProjectReleasePipeline.name).offset(offset).limit(limit).all()
        
        return ReleasePipelineListResponse(
            pipelines=[self._pipeline_to_response(pipeline) for pipeline in pipelines],
            total=total,
            offset=offset,
            limit=limit
        )

    
    # =========================================================================
    # Pipeline Execution Operations
    # =========================================================================
    
    def trigger_pipeline(
        self,
        pipeline_id: int,
        trigger_type: PipelineTriggerType,
        variables: Dict[str, Any],
        user_id: str
    ) -> PipelineRunResponse:
        """
        Trigger a pipeline run.
        
        :param pipeline_id: The release pipeline's unique identifier
        :param trigger_type: The type of trigger
        :param variables: Variables to pass to the pipeline
        :param user_id: The ID of the user triggering the pipeline
        :returns: PipelineRunResponse with the created run data
        :raises ReleasePipelineNotFoundError: If pipeline is not found
        
        Validates: Requirements 18.1
        """
        from automojo.pychestrate.core.orm import ProjectReleasePipeline, ProjectPipelineRun, ProjectStageRun
        
        # Get the release pipeline
        pipeline = self._db_session.query(ProjectReleasePipeline).filter(
            ProjectReleasePipeline.id == pipeline_id
        ).first()
        
        if not pipeline:
            raise ReleasePipelineNotFoundError(f"Release pipeline with ID '{pipeline_id}' not found")
        
        # Create the pipeline run record with status pending
        now = utc_now()
        
        run = ProjectPipelineRun(
            pipeline_id=pipeline.id,
            pipeline_version=pipeline.version,
            status=PipelineRunStatus.PENDING.value,
            current_stage=None,
            trigger_type=trigger_type.value,
            triggered_by_id=user_id,
            variables_json=variables,
            release_id=None,
            started_at=None,
            completed_at=None,
            created_at=now
        )
        
        self._db_session.add(run)
        self._db_session.flush()  # Get the run ID
        
        # Create stage run records for each stage
        stages = pipeline.stages_json or []
        for stage in stages:
            stage_run = ProjectStageRun(
                pipeline_run_id=run.id,
                stage_name=stage.get('name', ''),
                stage_type=stage.get('type', ''),
                status=StageRunStatus.PENDING.value,
                requires_approval=stage.get('requires_approval', False),
                approved_by_id=None,
                approved_at=None,
                started_at=None,
                completed_at=None,
                logs_path=None,
                output_json={}
            )
            self._db_session.add(stage_run)
        
        self._db_session.commit()
        
        # Log the pipeline trigger event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pipeline_triggered',
                user_id=str(user_id),
                details={
                    "pipeline_id": pipeline.id,
                    "pipeline_name": pipeline.name,
                    "run_id": run.id,
                    "trigger_type": trigger_type.value
                }
            )
        
        return self._pipeline_run_to_response(run)
    
    def get_pipeline_run(self, run_id: int) -> Optional[PipelineRunResponse]:
        """
        Get pipeline run by ID.
        
        :param run_id: The pipeline run's unique identifier
        :returns: PipelineRunResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectPipelineRun
        
        run = self._db_session.query(ProjectPipelineRun).filter(
            ProjectPipelineRun.id == run_id
        ).first()
        
        if not run:
            return None
        
        return self._pipeline_run_to_response(run)
    
    def cancel_pipeline_run(self, run_id: int, user_id: str) -> PipelineRunResponse:
        """
        Cancel a pipeline run.
        
        :param run_id: The pipeline run's unique identifier
        :param user_id: The ID of the user cancelling the run
        :returns: PipelineRunResponse with the updated run data
        :raises PipelineRunNotFoundError: If run is not found
        :raises PipelineRunCannotBeCancelledError: If run cannot be cancelled
        
        Validates: Requirements 18.5
        """
        from automojo.pychestrate.core.orm import ProjectPipelineRun
        
        run = self._db_session.query(ProjectPipelineRun).filter(
            ProjectPipelineRun.id == run_id
        ).first()
        
        if not run:
            raise PipelineRunNotFoundError(f"Pipeline run with ID '{run_id}' not found")
        
        # Check if run can be cancelled
        cancellable_statuses = [
            PipelineRunStatus.PENDING.value,
            PipelineRunStatus.RUNNING.value,
            PipelineRunStatus.PAUSED.value
        ]
        
        if run.status not in cancellable_statuses:
            raise PipelineRunCannotBeCancelledError(
                f"Pipeline run with status '{run.status}' cannot be cancelled"
            )
        
        # Update run status
        run.status = PipelineRunStatus.CANCELLED.value
        run.completed_at = utc_now()
        
        self._db_session.commit()
        
        # Log the cancellation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pipeline_run_cancelled',
                user_id=str(user_id),
                details={
                    "run_id": run.id,
                    "pipeline_id": run.pipeline_id,
                    "previous_status": run.status
                }
            )
        
        return self._pipeline_run_to_response(run)
    
    def pause_pipeline_run(self, run_id: int, user_id: str) -> PipelineRunResponse:
        """
        Pause a running pipeline.
        
        :param run_id: The pipeline run's unique identifier
        :param user_id: The ID of the user pausing the run
        :returns: PipelineRunResponse with the updated run data
        :raises PipelineRunNotFoundError: If run is not found
        :raises PipelineRunCannotBePausedError: If run cannot be paused
        
        Validates: Requirements 18.5
        """
        from automojo.pychestrate.core.orm import ProjectPipelineRun
        
        run = self._db_session.query(ProjectPipelineRun).filter(
            ProjectPipelineRun.id == run_id
        ).first()
        
        if not run:
            raise PipelineRunNotFoundError(f"Pipeline run with ID '{run_id}' not found")
        
        # Check if run can be paused
        if run.status != PipelineRunStatus.RUNNING.value:
            raise PipelineRunCannotBePausedError(
                f"Pipeline run with status '{run.status}' cannot be paused"
            )
        
        # Update run status
        run.status = PipelineRunStatus.PAUSED.value
        
        self._db_session.commit()
        
        # Log the pause event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pipeline_run_paused',
                user_id=str(user_id),
                details={
                    "run_id": run.id,
                    "pipeline_id": run.pipeline_id
                }
            )
        
        return self._pipeline_run_to_response(run)
    
    def resume_pipeline_run(self, run_id: int, user_id: str) -> PipelineRunResponse:
        """
        Resume a paused pipeline.
        
        :param run_id: The pipeline run's unique identifier
        :param user_id: The ID of the user resuming the run
        :returns: PipelineRunResponse with the updated run data
        :raises PipelineRunNotFoundError: If run is not found
        :raises PipelineRunCannotBeResumedError: If run cannot be resumed
        
        Validates: Requirements 18.5
        """
        from automojo.pychestrate.core.orm import ProjectPipelineRun
        
        run = self._db_session.query(ProjectPipelineRun).filter(
            ProjectPipelineRun.id == run_id
        ).first()
        
        if not run:
            raise PipelineRunNotFoundError(f"Pipeline run with ID '{run_id}' not found")
        
        # Check if run can be resumed
        if run.status != PipelineRunStatus.PAUSED.value:
            raise PipelineRunCannotBeResumedError(
                f"Pipeline run with status '{run.status}' cannot be resumed"
            )
        
        # Update run status
        run.status = PipelineRunStatus.RUNNING.value
        
        self._db_session.commit()
        
        # Log the resume event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pipeline_run_resumed',
                user_id=str(user_id),
                details={
                    "run_id": run.id,
                    "pipeline_id": run.pipeline_id
                }
            )
        
        return self._pipeline_run_to_response(run)
    
    def retry_stage(self, run_id: int, stage_name: str, user_id: str) -> PipelineRunResponse:
        """
        Retry a failed stage.
        
        :param run_id: The pipeline run's unique identifier
        :param stage_name: The name of the stage to retry
        :param user_id: The ID of the user retrying the stage
        :returns: PipelineRunResponse with the updated run data
        :raises PipelineRunNotFoundError: If run is not found
        :raises StageNotFoundError: If stage is not found
        :raises StageCannotBeRetriedError: If stage cannot be retried
        
        Validates: Requirements 18.5
        """
        from automojo.pychestrate.core.orm import ProjectPipelineRun, ProjectStageRun
        
        run = self._db_session.query(ProjectPipelineRun).filter(
            ProjectPipelineRun.id == run_id
        ).first()
        
        if not run:
            raise PipelineRunNotFoundError(f"Pipeline run with ID '{run_id}' not found")
        
        # Find the stage
        stage_run = self._db_session.query(ProjectStageRun).filter(
            ProjectStageRun.pipeline_run_id == run_id,
            ProjectStageRun.stage_name == stage_name
        ).first()
        
        if not stage_run:
            raise StageNotFoundError(f"Stage '{stage_name}' not found in pipeline run")
        
        # Check if stage can be retried
        if stage_run.status != StageRunStatus.FAILED.value:
            raise StageCannotBeRetriedError(
                f"Stage with status '{stage_run.status}' cannot be retried"
            )
        
        # Reset stage status
        stage_run.status = StageRunStatus.PENDING.value
        stage_run.started_at = None
        stage_run.completed_at = None
        stage_run.output_json = {}
        
        # Update run status if it was failed
        if run.status == PipelineRunStatus.FAILED.value:
            run.status = PipelineRunStatus.RUNNING.value
            run.current_stage = stage_name
        
        self._db_session.commit()
        
        # Log the retry event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pipeline_stage_retried',
                user_id=str(user_id),
                details={
                    "run_id": run.id,
                    "pipeline_id": run.pipeline_id,
                    "stage_name": stage_name
                }
            )
        
        return self._pipeline_run_to_response(run)
    
    def approve_stage(self, run_id: int, stage_name: str, user_id: str) -> StageRunResponse:
        """
        Approve a stage awaiting approval.
        
        :param run_id: The pipeline run's unique identifier
        :param stage_name: The name of the stage to approve
        :param user_id: The ID of the user approving the stage
        :returns: StageRunResponse with the updated stage data
        :raises PipelineRunNotFoundError: If run is not found
        :raises StageNotFoundError: If stage is not found
        :raises StageCannotBeApprovedError: If stage cannot be approved
        
        Validates: Requirements 18.8
        """
        from automojo.pychestrate.core.orm import ProjectPipelineRun, ProjectStageRun
        
        run = self._db_session.query(ProjectPipelineRun).filter(
            ProjectPipelineRun.id == run_id
        ).first()
        
        if not run:
            raise PipelineRunNotFoundError(f"Pipeline run with ID '{run_id}' not found")
        
        # Find the stage
        stage_run = self._db_session.query(ProjectStageRun).filter(
            ProjectStageRun.pipeline_run_id == run_id,
            ProjectStageRun.stage_name == stage_name
        ).first()
        
        if not stage_run:
            raise StageNotFoundError(f"Stage '{stage_name}' not found in pipeline run")
        
        # Check if stage can be approved
        if stage_run.status != StageRunStatus.AWAITING_APPROVAL.value:
            raise StageCannotBeApprovedError(
                f"Stage with status '{stage_run.status}' cannot be approved"
            )
        
        # Approve the stage
        now = utc_now()
        stage_run.approved_by_id = user_id
        stage_run.approved_at = now
        stage_run.status = StageRunStatus.RUNNING.value
        stage_run.started_at = now
        
        self._db_session.commit()
        
        # Log the approval event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pipeline_stage_approved',
                user_id=str(user_id),
                details={
                    "run_id": run.id,
                    "pipeline_id": run.pipeline_id,
                    "stage_name": stage_name
                }
            )
        
        return self._stage_run_to_response(stage_run)
    
    def list_pipeline_runs(
        self,
        project_id: int = None,
        pipeline_id: int = None,
        status: PipelineRunStatus = None,
        offset: int = 0,
        limit: int = 50
    ) -> PipelineRunListResponse:
        """
        List pipeline runs with filtering.
        
        :param project_id: Optional project ID filter
        :param pipeline_id: Optional pipeline ID filter
        :param status: Optional status filter
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: PipelineRunListResponse with paginated run list
        
        Validates: Requirements 18.7
        """
        from automojo.pychestrate.core.orm import ProjectPipelineRun, ProjectReleasePipeline
        
        query = self._db_session.query(ProjectPipelineRun)
        
        # Apply filters
        if project_id is not None:
            query = query.join(ProjectReleasePipeline).filter(
                ProjectReleasePipeline.project_id == project_id
            )
        
        if pipeline_id is not None:
            query = query.filter(ProjectPipelineRun.pipeline_id == pipeline_id)
        
        if status is not None:
            query = query.filter(ProjectPipelineRun.status == status.value)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (order by created_at descending for most recent first)
        runs = query.order_by(ProjectPipelineRun.created_at.desc()).offset(offset).limit(limit).all()
        
        return PipelineRunListResponse(
            runs=[self._pipeline_run_to_response(run) for run in runs],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def get_stage_runs(self, run_id: int) -> List[StageRunResponse]:
        """
        Get all stage runs for a pipeline run.
        
        :param run_id: The pipeline run's unique identifier
        :returns: List of StageRunResponse objects
        :raises PipelineRunNotFoundError: If run is not found
        """
        from automojo.pychestrate.core.orm import ProjectPipelineRun, ProjectStageRun
        
        run = self._db_session.query(ProjectPipelineRun).filter(
            ProjectPipelineRun.id == run_id
        ).first()
        
        if not run:
            raise PipelineRunNotFoundError(f"Pipeline run with ID '{run_id}' not found")
        
        stage_runs = self._db_session.query(ProjectStageRun).filter(
            ProjectStageRun.pipeline_run_id == run_id
        ).order_by(ProjectStageRun.id).all()
        
        return [self._stage_run_to_response(stage_run) for stage_run in stage_runs]

    
    # =========================================================================
    # Release CRUD Operations
    # =========================================================================
    
    def create_release(
        self,
        project_id: int,
        request: ReleaseCreateRequest,
        pipeline_run_id: int = None,
        user_id: str = None
    ) -> ReleaseResponse:
        """
        Create a release.
        
        :param project_id: The project's unique identifier
        :param request: The release creation request
        :param pipeline_run_id: Optional pipeline run ID that created this release
        :param user_id: The ID of the user creating the release
        :returns: ReleaseResponse with the created release data
        :raises ProjectNotFoundError: If project is not found
        :raises ReleaseVersionValidationError: If version validation fails
        :raises DuplicateReleaseVersionError: If version already exists in project
        
        Validates: Requirements 16.1, 16.2, 16.5
        """
        from automojo.pychestrate.core.orm import Project, ProjectRelease
        
        # Validate version
        if not self.validate_version(request.version):
            raise ReleaseVersionValidationError(
                f"Version '{request.version}' does not conform to semantic versioning",
                field="version"
            )
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check for duplicate version within project
        existing_release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.project_id == project_id,
            ProjectRelease.version == request.version
        ).first()
        
        if existing_release:
            raise DuplicateReleaseVersionError(
                f"Release with version '{request.version}' already exists in project '{project.name}'",
                field="version"
            )
        
        # Create the release
        now = utc_now()
        
        release = ProjectRelease(
            project_id=project_id,
            version=request.version,
            name=request.name,
            description=request.description or "",
            status=ReleaseStatus.DRAFT.value,
            metadata_json=request.metadata,
            pipeline_run_id=pipeline_run_id,
            schedule_id=None,
            created_at=now,
            updated_at=now,
            published_at=None,
            published_by_id=None
        )
        
        self._db_session.add(release)
        self._db_session.commit()
        
        # Log the release creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_created',
                user_id=str(user_id) if user_id else 'system',
                details={
                    "project_id": project_id,
                    "release_id": release.id,
                    "version": release.version,
                    "pipeline_run_id": pipeline_run_id
                }
            )
        
        return self._release_to_response(release)
    
    def get_release(self, release_id: int) -> Optional[ReleaseResponse]:
        """
        Get release by ID.
        
        :param release_id: The release's unique identifier
        :returns: ReleaseResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectRelease
        
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == release_id
        ).first()
        
        if not release:
            return None
        
        return self._release_to_response(release)
    
    def get_release_by_version(self, project_id: int, version: str) -> Optional[ReleaseResponse]:
        """
        Get release by version string.
        
        :param project_id: The project's unique identifier
        :param version: The version string
        :returns: ReleaseResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectRelease
        
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.project_id == project_id,
            ProjectRelease.version == version
        ).first()
        
        if not release:
            return None
        
        return self._release_to_response(release)
    
    def update_release(
        self,
        release_id: int,
        name: str = None,
        description: str = None,
        metadata: Dict[str, Any] = None,
        user_id: str = None
    ) -> ReleaseResponse:
        """
        Update release metadata.
        
        :param release_id: The release's unique identifier
        :param name: Optional new name
        :param description: Optional new description
        :param metadata: Optional new metadata
        :param user_id: The ID of the user making the update
        :returns: ReleaseResponse with the updated release data
        :raises ReleaseNotFoundError: If release is not found
        
        Validates: Requirements 16.3
        """
        from automojo.pychestrate.core.orm import ProjectRelease
        
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == release_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(f"Release with ID '{release_id}' not found")
        
        # Update fields if provided (artifacts remain unchanged - Requirements 16.3)
        if name is not None:
            release.name = name
        
        if description is not None:
            release.description = description
        
        if metadata is not None:
            release.metadata_json = metadata
        
        release.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the release update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_updated',
                user_id=str(user_id) if user_id else 'system',
                details={
                    "release_id": release.id,
                    "version": release.version,
                    "updated_fields": [k for k, v in {'name': name, 'description': description, 'metadata': metadata}.items() if v is not None]
                }
            )
        
        return self._release_to_response(release)
    
    def update_release_status(
        self,
        release_id: int,
        status: ReleaseStatus,
        user_id: str
    ) -> ReleaseResponse:
        """
        Update release status.
        
        :param release_id: The release's unique identifier
        :param status: The new status
        :param user_id: The ID of the user making the update
        :returns: ReleaseResponse with the updated release data
        :raises ReleaseNotFoundError: If release is not found
        
        Validates: Requirements 16.7, 16.8
        """
        from automojo.pychestrate.core.orm import ProjectRelease
        
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == release_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(f"Release with ID '{release_id}' not found")
        
        old_status = release.status
        release.status = status.value
        release.updated_at = utc_now()
        
        # Record publish timestamp if status is published
        if status == ReleaseStatus.PUBLISHED and old_status != ReleaseStatus.PUBLISHED.value:
            release.published_at = utc_now()
            release.published_by_id = user_id
        
        self._db_session.commit()
        
        # Log the status update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_status_updated',
                user_id=str(user_id),
                details={
                    "release_id": release.id,
                    "version": release.version,
                    "old_status": old_status,
                    "new_status": status.value
                }
            )
        
        return self._release_to_response(release)
    
    def delete_release(self, release_id: int, user_id: str) -> None:
        """
        Mark release as deleted.
        
        :param release_id: The release's unique identifier
        :param user_id: The ID of the user deleting the release
        :raises ReleaseNotFoundError: If release is not found
        
        Validates: Requirements 16.4
        """
        from automojo.pychestrate.core.orm import ProjectRelease
        
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == release_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(f"Release with ID '{release_id}' not found")
        
        # Mark as recalled (soft delete for audit purposes)
        release.status = ReleaseStatus.RECALLED.value
        release.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_deleted',
                user_id=str(user_id),
                details={
                    "release_id": release.id,
                    "version": release.version
                }
            )
    
    def list_releases(
        self,
        project_id: int,
        status: ReleaseStatus = None,
        channel_id: int = None,
        offset: int = 0,
        limit: int = 50
    ) -> ReleaseListResponse:
        """
        List releases with filtering.
        
        :param project_id: The project's unique identifier
        :param status: Optional status filter
        :param channel_id: Optional channel ID filter
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: ReleaseListResponse with paginated release list
        
        Validates: Requirements 16.6
        """
        from automojo.pychestrate.core.orm import ProjectRelease, ProjectChannelHistory
        
        query = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.project_id == project_id
        )
        
        # Apply filters
        if status is not None:
            query = query.filter(ProjectRelease.status == status.value)
        
        if channel_id is not None:
            # Get releases that have been published to this channel
            release_ids = self._db_session.query(ProjectChannelHistory.release_id).filter(
                ProjectChannelHistory.channel_id == channel_id
            ).distinct()
            query = query.filter(ProjectRelease.id.in_(release_ids))
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (order by created_at descending for most recent first)
        releases = query.order_by(ProjectRelease.created_at.desc()).offset(offset).limit(limit).all()
        
        return ReleaseListResponse(
            releases=[self._release_to_response(release) for release in releases],
            total=total,
            offset=offset,
            limit=limit
        )

    
    # =========================================================================
    # Artifact Management Operations
    # =========================================================================
    
    def add_artifact(
        self,
        release_id: int,
        name: str,
        artifact_type: ArtifactType,
        content: bytes,
        user_id: str
    ) -> ReleaseArtifactResponse:
        """
        Add an artifact to a release.
        
        :param release_id: The release's unique identifier
        :param name: Name of the artifact
        :param artifact_type: Type of the artifact
        :param content: Artifact content as bytes
        :param user_id: The ID of the user adding the artifact
        :returns: ReleaseArtifactResponse with the created artifact data
        :raises ReleaseNotFoundError: If release is not found
        
        Validates: Requirements 19.1, 19.2, 19.3
        """
        from automojo.pychestrate.core.orm import ProjectRelease, ProjectReleaseArtifact
        
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == release_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(f"Release with ID '{release_id}' not found")
        
        # Calculate checksum
        checksum = hashlib.sha256(content).hexdigest()
        
        # Create storage path
        storage_dir = os.path.join(
            self._artifact_storage_path,
            str(release.project_id),
            str(release_id)
        )
        os.makedirs(storage_dir, exist_ok=True)
        storage_path = os.path.join(storage_dir, name)
        
        # Write artifact to storage
        with open(storage_path, 'wb') as f:
            f.write(content)
        
        # Create artifact record
        now = utc_now()
        
        artifact = ProjectReleaseArtifact(
            release_id=release_id,
            name=name,
            artifact_type=artifact_type.value,
            size_bytes=len(content),
            checksum=checksum,
            checksum_algorithm='sha256',
            storage_path=storage_path,
            signature=None,
            created_at=now
        )
        
        self._db_session.add(artifact)
        self._db_session.commit()
        
        # Log the artifact addition event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_artifact_added',
                user_id=str(user_id),
                details={
                    "release_id": release_id,
                    "artifact_id": artifact.id,
                    "artifact_name": name,
                    "artifact_type": artifact_type.value,
                    "size_bytes": len(content)
                }
            )
        
        return self._artifact_to_response(artifact)
    
    def get_artifact(self, artifact_id: int) -> Optional[ReleaseArtifactResponse]:
        """
        Get artifact metadata.
        
        :param artifact_id: The artifact's unique identifier
        :returns: ReleaseArtifactResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectReleaseArtifact
        
        artifact = self._db_session.query(ProjectReleaseArtifact).filter(
            ProjectReleaseArtifact.id == artifact_id
        ).first()
        
        if not artifact:
            return None
        
        return self._artifact_to_response(artifact)
    
    def download_artifact(self, artifact_id: int, user_id: str) -> bytes:
        """
        Download artifact content.
        
        :param artifact_id: The artifact's unique identifier
        :param user_id: The ID of the user downloading the artifact
        :returns: Artifact content as bytes
        :raises ArtifactNotFoundError: If artifact is not found or file doesn't exist
        
        Validates: Requirements 19.5
        """
        from automojo.pychestrate.core.orm import ProjectReleaseArtifact
        
        artifact = self._db_session.query(ProjectReleaseArtifact).filter(
            ProjectReleaseArtifact.id == artifact_id
        ).first()
        
        if not artifact:
            raise ArtifactNotFoundError(f"Artifact with ID '{artifact_id}' not found")
        
        if not artifact.storage_path or not os.path.exists(artifact.storage_path):
            raise ArtifactNotFoundError(f"Artifact file not found at path '{artifact.storage_path}'")
        
        try:
            with open(artifact.storage_path, 'rb') as f:
                content = f.read()
            
            # Log the download event
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type='release_artifact_downloaded',
                    user_id=str(user_id),
                    details={
                        "artifact_id": artifact.id,
                        "artifact_name": artifact.name,
                        "release_id": artifact.release_id
                    }
                )
            
            return content
        except IOError as e:
            raise ArtifactNotFoundError(f"Failed to read artifact file: {str(e)}")
    
    def list_artifacts(self, release_id: int) -> ReleaseArtifactListResponse:
        """
        List artifacts in a release.
        
        :param release_id: The release's unique identifier
        :returns: ReleaseArtifactListResponse with artifact list
        :raises ReleaseNotFoundError: If release is not found
        
        Validates: Requirements 19.7
        """
        from automojo.pychestrate.core.orm import ProjectRelease, ProjectReleaseArtifact
        
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == release_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(f"Release with ID '{release_id}' not found")
        
        artifacts = self._db_session.query(ProjectReleaseArtifact).filter(
            ProjectReleaseArtifact.release_id == release_id
        ).order_by(ProjectReleaseArtifact.name).all()
        
        return ReleaseArtifactListResponse(
            artifacts=[self._artifact_to_response(artifact) for artifact in artifacts],
            total=len(artifacts)
        )
    
    def sign_artifact(
        self,
        artifact_id: int,
        signing_key_ref: str,
        user_id: str
    ) -> ReleaseArtifactResponse:
        """
        Sign an artifact.
        
        :param artifact_id: The artifact's unique identifier
        :param signing_key_ref: Reference to the signing key in Secret_Manager
        :param user_id: The ID of the user signing the artifact
        :returns: ReleaseArtifactResponse with the updated artifact data
        :raises ArtifactNotFoundError: If artifact is not found
        
        Validates: Requirements 19.4
        """
        from automojo.pychestrate.core.orm import ProjectReleaseArtifact
        
        artifact = self._db_session.query(ProjectReleaseArtifact).filter(
            ProjectReleaseArtifact.id == artifact_id
        ).first()
        
        if not artifact:
            raise ArtifactNotFoundError(f"Artifact with ID '{artifact_id}' not found")
        
        # In a real implementation, this would use the signing key to create a signature
        # For now, we'll create a placeholder signature
        signature = f"SIGNED:{signing_key_ref}:{artifact.checksum}"
        
        artifact.signature = signature
        
        self._db_session.commit()
        
        # Log the signing event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_artifact_signed',
                user_id=str(user_id),
                details={
                    "artifact_id": artifact.id,
                    "artifact_name": artifact.name,
                    "signing_key_ref": signing_key_ref
                }
            )
        
        return self._artifact_to_response(artifact)
    
    def verify_artifact(self, artifact_id: int) -> bool:
        """
        Verify artifact checksum and signature.
        
        :param artifact_id: The artifact's unique identifier
        :returns: True if verification passes, False otherwise
        :raises ArtifactNotFoundError: If artifact is not found
        
        Validates: Requirements 19.3
        """
        from automojo.pychestrate.core.orm import ProjectReleaseArtifact
        
        artifact = self._db_session.query(ProjectReleaseArtifact).filter(
            ProjectReleaseArtifact.id == artifact_id
        ).first()
        
        if not artifact:
            raise ArtifactNotFoundError(f"Artifact with ID '{artifact_id}' not found")
        
        if not artifact.storage_path or not os.path.exists(artifact.storage_path):
            return False
        
        try:
            with open(artifact.storage_path, 'rb') as f:
                content = f.read()
            
            # Verify checksum
            computed_checksum = hashlib.sha256(content).hexdigest()
            if computed_checksum != artifact.checksum:
                return False
            
            # Signature verification would be done here in a real implementation
            
            return True
        except IOError:
            return False

    
    # =========================================================================
    # Channel Management Operations
    # =========================================================================
    
    def create_channel(
        self,
        project_id: int,
        name: str,
        description: str = "",
        requires_approval: bool = False,
        user_id: str = None
    ) -> ReleaseChannelResponse:
        """
        Create a release channel.
        
        :param project_id: The project's unique identifier
        :param name: Name of the channel
        :param description: Description of the channel
        :param requires_approval: Whether publishing to this channel requires approval
        :param user_id: The ID of the user creating the channel
        :returns: ReleaseChannelResponse with the created channel data
        :raises ProjectNotFoundError: If project is not found
        :raises DuplicateReleaseChannelError: If channel name already exists in project
        
        Validates: Requirements 20.1
        """
        from automojo.pychestrate.core.orm import Project, ProjectReleaseChannel
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check for duplicate name within project
        existing_channel = self._db_session.query(ProjectReleaseChannel).filter(
            ProjectReleaseChannel.project_id == project_id,
            ProjectReleaseChannel.name == name
        ).first()
        
        if existing_channel:
            raise DuplicateReleaseChannelError(
                f"Release channel with name '{name}' already exists in project '{project.name}'",
                field="name"
            )
        
        # Create the channel
        now = utc_now()
        
        channel = ProjectReleaseChannel(
            project_id=project_id,
            name=name,
            description=description,
            current_release_id=None,
            requires_approval=requires_approval,
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(channel)
        self._db_session.commit()
        
        # Log the channel creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_channel_created',
                user_id=str(user_id) if user_id else 'system',
                details={
                    "project_id": project_id,
                    "channel_id": channel.id,
                    "channel_name": name
                }
            )
        
        return self._channel_to_response(channel)
    
    def get_channel(self, channel_id: int) -> Optional[ReleaseChannelResponse]:
        """
        Get channel by ID.
        
        :param channel_id: The channel's unique identifier
        :returns: ReleaseChannelResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectReleaseChannel
        
        channel = self._db_session.query(ProjectReleaseChannel).filter(
            ProjectReleaseChannel.id == channel_id
        ).first()
        
        if not channel:
            return None
        
        return self._channel_to_response(channel)
    
    def list_channels(self, project_id: int) -> ReleaseChannelListResponse:
        """
        List channels in a project.
        
        :param project_id: The project's unique identifier
        :returns: ReleaseChannelListResponse with channel list
        
        Validates: Requirements 20.3
        """
        from automojo.pychestrate.core.orm import ProjectReleaseChannel
        
        channels = self._db_session.query(ProjectReleaseChannel).filter(
            ProjectReleaseChannel.project_id == project_id
        ).order_by(ProjectReleaseChannel.name).all()
        
        return ReleaseChannelListResponse(
            channels=[self._channel_to_response(channel) for channel in channels],
            total=len(channels)
        )
    
    def publish_to_channel(
        self,
        release_id: int,
        channel_id: int,
        user_id: str
    ) -> ReleaseChannelResponse:
        """
        Publish a release to a channel.
        
        :param release_id: The release's unique identifier
        :param channel_id: The channel's unique identifier
        :param user_id: The ID of the user publishing the release
        :returns: ReleaseChannelResponse with the updated channel data
        :raises ReleaseNotFoundError: If release is not found
        :raises ReleaseChannelNotFoundError: If channel is not found
        
        Validates: Requirements 20.2, 20.4, 20.5
        """
        from automojo.pychestrate.core.orm import ProjectRelease, ProjectReleaseChannel, ProjectChannelHistory
        
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == release_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(f"Release with ID '{release_id}' not found")
        
        channel = self._db_session.query(ProjectReleaseChannel).filter(
            ProjectReleaseChannel.id == channel_id
        ).first()
        
        if not channel:
            raise ReleaseChannelNotFoundError(f"Release channel with ID '{channel_id}' not found")
        
        # Update channel's current release reference (Requirements 20.2)
        channel.current_release_id = release_id
        channel.updated_at = utc_now()
        
        # Create history record (Requirements 20.5)
        history = ProjectChannelHistory(
            channel_id=channel_id,
            release_id=release_id,
            published_at=utc_now(),
            published_by_id=user_id
        )
        
        self._db_session.add(history)
        self._db_session.commit()
        
        # Log the publish event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_published_to_channel',
                user_id=str(user_id),
                details={
                    "release_id": release_id,
                    "release_version": release.version,
                    "channel_id": channel_id,
                    "channel_name": channel.name
                }
            )
        
        return self._channel_to_response(channel)
    
    def get_channel_history(
        self,
        channel_id: int,
        offset: int = 0,
        limit: int = 50
    ) -> ChannelHistoryResponse:
        """
        Get release history for a channel.
        
        :param channel_id: The channel's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: ChannelHistoryResponse with paginated history
        :raises ReleaseChannelNotFoundError: If channel is not found
        
        Validates: Requirements 20.5, 20.6
        """
        from automojo.pychestrate.core.orm import ProjectReleaseChannel, ProjectChannelHistory, ProjectRelease, User
        
        channel = self._db_session.query(ProjectReleaseChannel).filter(
            ProjectReleaseChannel.id == channel_id
        ).first()
        
        if not channel:
            raise ReleaseChannelNotFoundError(f"Release channel with ID '{channel_id}' not found")
        
        query = self._db_session.query(ProjectChannelHistory).filter(
            ProjectChannelHistory.channel_id == channel_id
        )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (order by published_at descending for most recent first)
        history_records = query.order_by(ProjectChannelHistory.published_at.desc()).offset(offset).limit(limit).all()
        
        history_entries = []
        for record in history_records:
            release = self._db_session.query(ProjectRelease).filter(
                ProjectRelease.id == record.release_id
            ).first()
            
            user = self._db_session.query(User).filter(
                User.id == record.published_by_id
            ).first()
            
            history_entries.append(ChannelHistoryEntry(
                id=record.id,
                channel_id=record.channel_id,
                release_id=record.release_id,
                release_version=release.version if release else "",
                release_name=release.name if release else "",
                published_at=record.published_at,
                published_by_id=str(record.published_by_id),
                published_by_username=user.login if user else ""
            ))
        
        return ChannelHistoryResponse(
            history=history_entries,
            total=total,
            offset=offset,
            limit=limit
        )
    
    def rollback_channel(
        self,
        channel_id: int,
        release_id: int,
        user_id: str
    ) -> ReleaseChannelResponse:
        """
        Rollback channel to a previous release.
        
        :param channel_id: The channel's unique identifier
        :param release_id: The release ID to rollback to
        :param user_id: The ID of the user performing the rollback
        :returns: ReleaseChannelResponse with the updated channel data
        :raises ReleaseChannelNotFoundError: If channel is not found
        :raises ReleaseNotFoundError: If release is not found
        
        Validates: Requirements 20.6
        """
        from automojo.pychestrate.core.orm import ProjectRelease, ProjectReleaseChannel, ProjectChannelHistory
        
        channel = self._db_session.query(ProjectReleaseChannel).filter(
            ProjectReleaseChannel.id == channel_id
        ).first()
        
        if not channel:
            raise ReleaseChannelNotFoundError(f"Release channel with ID '{channel_id}' not found")
        
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == release_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(f"Release with ID '{release_id}' not found")
        
        # Update channel's current release reference
        channel.current_release_id = release_id
        channel.updated_at = utc_now()
        
        # Create history record for the rollback
        history = ProjectChannelHistory(
            channel_id=channel_id,
            release_id=release_id,
            published_at=utc_now(),
            published_by_id=user_id
        )
        
        self._db_session.add(history)
        self._db_session.commit()
        
        # Log the rollback event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_channel_rollback',
                user_id=str(user_id),
                details={
                    "channel_id": channel_id,
                    "channel_name": channel.name,
                    "release_id": release_id,
                    "release_version": release.version
                }
            )
        
        return self._channel_to_response(channel)

    
    # =========================================================================
    # Schedule Management Operations
    # =========================================================================
    
    def create_schedule(
        self,
        project_id: int,
        request: ReleaseScheduleCreateRequest,
        user_id: str
    ) -> ReleaseScheduleResponse:
        """
        Create a release schedule.
        
        :param project_id: The project's unique identifier
        :param request: The release schedule creation request
        :param user_id: The ID of the user creating the schedule
        :returns: ReleaseScheduleResponse with the created schedule data
        :raises ProjectNotFoundError: If project is not found
        :raises ReleasePipelineNotFoundError: If pipeline is not found
        :raises CronExpressionValidationError: If cron expression is invalid
        :raises DuplicateReleaseScheduleError: If schedule name already exists in project
        
        Validates: Requirements 21.1, 21.3
        """
        from automojo.pychestrate.core.orm import Project, ProjectReleasePipeline, ProjectReleaseSchedule
        
        # Validate cron expression
        if not self.validate_cron_expression(request.cron_expression):
            raise CronExpressionValidationError(
                f"Invalid cron expression '{request.cron_expression}'",
                field="cron_expression"
            )
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Verify pipeline exists and belongs to project
        pipeline = self._db_session.query(ProjectReleasePipeline).filter(
            ProjectReleasePipeline.id == request.pipeline_id,
            ProjectReleasePipeline.project_id == project_id
        ).first()
        
        if not pipeline:
            raise ReleasePipelineNotFoundError(
                f"Release pipeline with ID '{request.pipeline_id}' not found in project"
            )
        
        # Check for duplicate name within project
        existing_schedule = self._db_session.query(ProjectReleaseSchedule).filter(
            ProjectReleaseSchedule.project_id == project_id,
            ProjectReleaseSchedule.name == request.name
        ).first()
        
        if existing_schedule:
            raise DuplicateReleaseScheduleError(
                f"Release schedule with name '{request.name}' already exists in project '{project.name}'",
                field="name"
            )
        
        # Calculate next run time
        next_run_time = self.calculate_next_run_time(request.cron_expression)
        
        # Create the schedule
        now = utc_now()
        
        schedule = ProjectReleaseSchedule(
            project_id=project_id,
            name=request.name,
            cron_expression=request.cron_expression,
            pipeline_id=request.pipeline_id,
            variables_json=request.variables,
            enabled=request.enabled,
            description=request.description or "",
            last_run_time=None,
            next_run_time=next_run_time if request.enabled else None,
            run_count=0,
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(schedule)
        self._db_session.commit()
        
        # Log the schedule creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_schedule_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "schedule_id": schedule.id,
                    "schedule_name": request.name,
                    "pipeline_id": request.pipeline_id,
                    "cron_expression": request.cron_expression
                }
            )
        
        return self._schedule_to_response(schedule)
    
    def get_schedule(self, schedule_id: int) -> Optional[ReleaseScheduleResponse]:
        """
        Get schedule by ID.
        
        :param schedule_id: The schedule's unique identifier
        :returns: ReleaseScheduleResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectReleaseSchedule
        
        schedule = self._db_session.query(ProjectReleaseSchedule).filter(
            ProjectReleaseSchedule.id == schedule_id
        ).first()
        
        if not schedule:
            return None
        
        return self._schedule_to_response(schedule)
    
    def update_schedule(
        self,
        schedule_id: int,
        request: ReleaseScheduleUpdateRequest,
        user_id: str
    ) -> ReleaseScheduleResponse:
        """
        Update schedule configuration.
        
        :param schedule_id: The schedule's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: ReleaseScheduleResponse with the updated schedule data
        :raises ReleaseScheduleNotFoundError: If schedule is not found
        :raises CronExpressionValidationError: If cron expression is invalid
        :raises ReleasePipelineNotFoundError: If pipeline is not found
        :raises DuplicateReleaseScheduleError: If new name already exists in project
        """
        from automojo.pychestrate.core.orm import ProjectReleaseSchedule, ProjectReleasePipeline
        
        schedule = self._db_session.query(ProjectReleaseSchedule).filter(
            ProjectReleaseSchedule.id == schedule_id
        ).first()
        
        if not schedule:
            raise ReleaseScheduleNotFoundError(f"Release schedule with ID '{schedule_id}' not found")
        
        # Update name if provided
        if request.name is not None:
            # Check for duplicate name (excluding current schedule)
            existing_schedule = self._db_session.query(ProjectReleaseSchedule).filter(
                ProjectReleaseSchedule.project_id == schedule.project_id,
                ProjectReleaseSchedule.name == request.name,
                ProjectReleaseSchedule.id != schedule_id
            ).first()
            
            if existing_schedule:
                raise DuplicateReleaseScheduleError(
                    f"Release schedule with name '{request.name}' already exists in this project",
                    field="name"
                )
            
            schedule.name = request.name
        
        # Update cron expression if provided
        if request.cron_expression is not None:
            if not self.validate_cron_expression(request.cron_expression):
                raise CronExpressionValidationError(
                    f"Invalid cron expression '{request.cron_expression}'",
                    field="cron_expression"
                )
            schedule.cron_expression = request.cron_expression
        
        # Update pipeline_id if provided
        if request.pipeline_id is not None:
            pipeline = self._db_session.query(ProjectReleasePipeline).filter(
                ProjectReleasePipeline.id == request.pipeline_id,
                ProjectReleasePipeline.project_id == schedule.project_id
            ).first()
            
            if not pipeline:
                raise ReleasePipelineNotFoundError(
                    f"Release pipeline with ID '{request.pipeline_id}' not found in project"
                )
            
            schedule.pipeline_id = request.pipeline_id
        
        # Update variables if provided
        if request.variables is not None:
            schedule.variables_json = request.variables
        
        # Update enabled if provided
        if request.enabled is not None:
            schedule.enabled = request.enabled
        
        # Update description if provided
        if request.description is not None:
            schedule.description = request.description
        
        # Recalculate next run time
        if schedule.enabled:
            schedule.next_run_time = self.calculate_next_run_time(schedule.cron_expression)
        else:
            schedule.next_run_time = None
        
        schedule.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the schedule update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_schedule_updated',
                user_id=str(user_id),
                details={
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._schedule_to_response(schedule)
    
    def delete_schedule(self, schedule_id: int, user_id: str) -> None:
        """
        Delete a schedule.
        
        :param schedule_id: The schedule's unique identifier
        :param user_id: The ID of the user deleting the schedule
        :raises ReleaseScheduleNotFoundError: If schedule is not found
        """
        from automojo.pychestrate.core.orm import ProjectReleaseSchedule
        
        schedule = self._db_session.query(ProjectReleaseSchedule).filter(
            ProjectReleaseSchedule.id == schedule_id
        ).first()
        
        if not schedule:
            raise ReleaseScheduleNotFoundError(f"Release schedule with ID '{schedule_id}' not found")
        
        schedule_name = schedule.name
        project_id = schedule.project_id
        
        self._db_session.delete(schedule)
        self._db_session.commit()
        
        # Log the schedule deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_schedule_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "schedule_id": schedule_id,
                    "schedule_name": schedule_name
                }
            )
    
    def list_schedules(
        self,
        project_id: int,
        enabled: bool = None,
        offset: int = 0,
        limit: int = 50
    ) -> ReleaseScheduleListResponse:
        """
        List release schedules in a project.
        
        :param project_id: The project's unique identifier
        :param enabled: Optional filter by enabled status
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: ReleaseScheduleListResponse with paginated schedule list
        
        Validates: Requirements 21.8
        """
        from automojo.pychestrate.core.orm import ProjectReleaseSchedule
        
        query = self._db_session.query(ProjectReleaseSchedule).filter(
            ProjectReleaseSchedule.project_id == project_id
        )
        
        # Apply filter
        if enabled is not None:
            query = query.filter(ProjectReleaseSchedule.enabled == enabled)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        schedules = query.order_by(ProjectReleaseSchedule.name).offset(offset).limit(limit).all()
        
        return ReleaseScheduleListResponse(
            schedules=[self._schedule_to_response(schedule) for schedule in schedules],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def enable_schedule(self, schedule_id: int, user_id: str) -> ReleaseScheduleResponse:
        """
        Enable a schedule.
        
        :param schedule_id: The schedule's unique identifier
        :param user_id: The ID of the user enabling the schedule
        :returns: ReleaseScheduleResponse with the updated schedule data
        :raises ReleaseScheduleNotFoundError: If schedule is not found
        
        Validates: Requirements 21.6
        """
        from automojo.pychestrate.core.orm import ProjectReleaseSchedule
        
        schedule = self._db_session.query(ProjectReleaseSchedule).filter(
            ProjectReleaseSchedule.id == schedule_id
        ).first()
        
        if not schedule:
            raise ReleaseScheduleNotFoundError(f"Release schedule with ID '{schedule_id}' not found")
        
        schedule.enabled = True
        schedule.next_run_time = self.calculate_next_run_time(schedule.cron_expression)
        schedule.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the enable event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_schedule_enabled',
                user_id=str(user_id),
                details={
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name,
                    "next_run_time": str(schedule.next_run_time)
                }
            )
        
        return self._schedule_to_response(schedule)
    
    def disable_schedule(self, schedule_id: int, user_id: str) -> ReleaseScheduleResponse:
        """
        Disable a schedule.
        
        :param schedule_id: The schedule's unique identifier
        :param user_id: The ID of the user disabling the schedule
        :returns: ReleaseScheduleResponse with the updated schedule data
        :raises ReleaseScheduleNotFoundError: If schedule is not found
        
        Validates: Requirements 21.6
        """
        from automojo.pychestrate.core.orm import ProjectReleaseSchedule
        
        schedule = self._db_session.query(ProjectReleaseSchedule).filter(
            ProjectReleaseSchedule.id == schedule_id
        ).first()
        
        if not schedule:
            raise ReleaseScheduleNotFoundError(f"Release schedule with ID '{schedule_id}' not found")
        
        schedule.enabled = False
        schedule.next_run_time = None
        schedule.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the disable event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_schedule_disabled',
                user_id=str(user_id),
                details={
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name
                }
            )
        
        return self._schedule_to_response(schedule)
    
    def trigger_scheduled_releases(self) -> List[PipelineRunResponse]:
        """
        Check and trigger due scheduled releases. Called by scheduler.
        
        :returns: List of PipelineRunResponse for triggered runs
        
        Validates: Requirements 21.2, 21.5
        """
        from automojo.pychestrate.core.orm import ProjectReleaseSchedule
        
        now = utc_now()
        
        # Find schedules that are due
        due_schedules = self._db_session.query(ProjectReleaseSchedule).filter(
            ProjectReleaseSchedule.enabled == True,
            ProjectReleaseSchedule.next_run_time <= now
        ).all()
        
        triggered_runs = []
        
        for schedule in due_schedules:
            try:
                # Trigger the pipeline
                run = self.trigger_pipeline(
                    pipeline_id=schedule.pipeline_id,
                    trigger_type=PipelineTriggerType.SCHEDULE,
                    variables=schedule.variables_json or {},
                    user_id='system'
                )
                
                triggered_runs.append(run)
                
                # Update schedule tracking (Requirements 21.5)
                schedule.last_run_time = now
                schedule.run_count += 1
                schedule.next_run_time = self.calculate_next_run_time(schedule.cron_expression, now)
                schedule.updated_at = now
                
            except Exception as e:
                # Log the error but continue with other schedules
                if self._audit_logger:
                    self._audit_logger.log_event(
                        event_type='release_schedule_trigger_failed',
                        user_id='system',
                        details={
                            "schedule_id": schedule.id,
                            "schedule_name": schedule.name,
                            "error": str(e)
                        }
                    )
        
        self._db_session.commit()
        
        return triggered_runs
    
    def calculate_next_run_time(
        self,
        cron_expression: str,
        after: datetime = None
    ) -> datetime:
        """
        Calculate next run time for a cron expression.
        
        :param cron_expression: The cron expression
        :param after: Optional datetime to calculate next run after (defaults to now)
        :returns: Next run datetime
        
        Validates: Requirements 21.5
        """
        from datetime import timedelta
        
        if after is None:
            after = utc_now()
        
        # Parse cron expression
        fields = cron_expression.strip().split()
        if len(fields) != 5:
            return after + timedelta(hours=1)  # Default fallback
        
        minute_spec, hour_spec, dom_spec, month_spec, dow_spec = fields
        
        # Simple implementation: find next matching time
        # In a production system, you would use a library like croniter
        current = after + timedelta(minutes=1)
        current = current.replace(second=0, microsecond=0)
        
        # Try up to 366 days ahead
        for _ in range(366 * 24 * 60):
            if self._matches_cron(current, minute_spec, hour_spec, dom_spec, month_spec, dow_spec):
                return current
            current += timedelta(minutes=1)
        
        # Fallback if no match found
        return after + timedelta(hours=1)
    
    def _matches_cron(
        self,
        dt: datetime,
        minute_spec: str,
        hour_spec: str,
        dom_spec: str,
        month_spec: str,
        dow_spec: str
    ) -> bool:
        """
        Check if a datetime matches a cron specification.
        
        :param dt: The datetime to check
        :param minute_spec: Minute field specification
        :param hour_spec: Hour field specification
        :param dom_spec: Day of month field specification
        :param month_spec: Month field specification
        :param dow_spec: Day of week field specification
        :returns: True if matches, False otherwise
        """
        return (
            self._matches_cron_field(dt.minute, minute_spec, 0, 59) and
            self._matches_cron_field(dt.hour, hour_spec, 0, 23) and
            self._matches_cron_field(dt.day, dom_spec, 1, 31) and
            self._matches_cron_field(dt.month, month_spec, 1, 12) and
            self._matches_cron_field(dt.weekday(), dow_spec, 0, 6)
        )
    
    def _matches_cron_field(self, value: int, spec: str, min_val: int, max_val: int) -> bool:
        """
        Check if a value matches a cron field specification.
        
        :param value: The value to check
        :param spec: The cron field specification
        :param min_val: Minimum allowed value
        :param max_val: Maximum allowed value
        :returns: True if matches, False otherwise
        """
        if spec == '*':
            return True
        
        # Handle comma-separated values
        parts = spec.split(',')
        
        for part in parts:
            step = 1
            
            # Handle step values
            if '/' in part:
                range_part, step_str = part.split('/', 1)
                try:
                    step = int(step_str)
                except ValueError:
                    continue
                part = range_part
            
            # Handle range values
            if '-' in part and part != '*':
                try:
                    start, end = part.split('-', 1)
                    start_val = int(start)
                    end_val = int(end)
                    
                    if start_val <= value <= end_val:
                        if step == 1 or (value - start_val) % step == 0:
                            return True
                except ValueError:
                    continue
            elif part == '*':
                if step == 1 or (value - min_val) % step == 0:
                    return True
            else:
                # Single value
                try:
                    if int(part) == value:
                        return True
                except ValueError:
                    continue
        
        return False

    # =========================================================================
    # Calendar Event Management - Release Events
    # =========================================================================
    def _release_event_to_response(self, event) -> ReleaseEventResponse:
        """
        Convert a ProjectReleaseEvent ORM object to a ReleaseEventResponse.
        
        :param event: The ProjectReleaseEvent ORM object
        :returns: ReleaseEventResponse dataclass
        """
        release_version = event.release.version if event.release else ""
        release_name = event.release.name if event.release else ""
        
        phases = []
        if event.phases:
            for phase in sorted(event.phases, key=lambda p: p.order):
                phases.append(self._phase_event_to_response(phase))
        
        return ReleaseEventResponse(
            id=event.id,
            project_id=event.project_id,
            release_id=event.release_id,
            release_version=release_version,
            release_name=release_name,
            name=event.name,
            description=event.description or "",
            start_time=event.start_time,
            end_time=event.end_time,
            created_at=event.created_at,
            updated_at=event.updated_at,
            phases=phases
        )
    
    def _phase_event_to_response(self, phase) -> PhaseEventResponse:
        """
        Convert a ProjectPhaseEvent ORM object to a PhaseEventResponse.
        
        :param phase: The ProjectPhaseEvent ORM object
        :returns: PhaseEventResponse dataclass
        """
        return PhaseEventResponse(
            id=phase.id,
            release_event_id=phase.release_event_id,
            name=phase.name,
            description=phase.description or "",
            start_time=phase.start_time,
            end_time=phase.end_time,
            order=phase.order,
            status=phase.status,
            created_at=phase.created_at,
            updated_at=phase.updated_at
        )
    
    def create_release_event(
        self,
        project_id: int,
        request: ReleaseEventCreateRequest,
        user_id: str
    ) -> ReleaseEventResponse:
        """
        Create a release calendar event.
        
        :param project_id: The project's unique identifier
        :param request: The release event creation request
        :param user_id: The ID of the user creating the event
        :returns: ReleaseEventResponse with the created event data
        :raises ProjectNotFoundError: If project is not found
        :raises ReleaseNotFoundError: If release is not found
        :raises ReleaseEventValidationError: If validation fails
        
        Validates: Requirements 22.1, 22.4
        """
        from automojo.pychestrate.core.orm import Project, ProjectRelease, ProjectReleaseEvent
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Verify release exists and belongs to project
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == request.release_id,
            ProjectRelease.project_id == project_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(
                f"Release with ID '{request.release_id}' not found in project '{project.name}'"
            )
        
        # Validate that end time is after start time (Requirements 22.4)
        if request.end_time <= request.start_time:
            raise ReleaseEventValidationError(
                "End time must be after start time",
                field="end_time"
            )
        
        # Create the release event
        now = utc_now()
        
        event = ProjectReleaseEvent(
            project_id=project_id,
            release_id=request.release_id,
            name=request.name,
            description=request.description or "",
            start_time=request.start_time,
            end_time=request.end_time,
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(event)
        self._db_session.commit()
        
        # Log the event creation
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_event_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "event_id": event.id,
                    "event_name": event.name,
                    "release_id": request.release_id
                }
            )
        
        return self._release_event_to_response(event)
    
    def get_release_event(self, event_id: int) -> Optional[ReleaseEventResponse]:
        """
        Get release event by ID.
        
        :param event_id: The release event's unique identifier
        :returns: ReleaseEventResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectReleaseEvent
        
        event = self._db_session.query(ProjectReleaseEvent).filter(
            ProjectReleaseEvent.id == event_id
        ).first()
        
        if not event:
            return None
        
        return self._release_event_to_response(event)
    
    def update_release_event(
        self,
        event_id: int,
        request: ReleaseEventUpdateRequest,
        user_id: str
    ) -> ReleaseEventResponse:
        """
        Update a release event.
        
        :param event_id: The release event's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: ReleaseEventResponse with the updated event data
        :raises ReleaseEventNotFoundError: If event is not found
        :raises ReleaseEventValidationError: If validation fails
        
        Validates: Requirements 22.2, 22.4
        """
        from automojo.pychestrate.core.orm import ProjectReleaseEvent
        
        event = self._db_session.query(ProjectReleaseEvent).filter(
            ProjectReleaseEvent.id == event_id
        ).first()
        
        if not event:
            raise ReleaseEventNotFoundError(f"Release event with ID '{event_id}' not found")
        
        # Update name if provided
        if request.name is not None:
            event.name = request.name
        
        # Update description if provided
        if request.description is not None:
            event.description = request.description
        
        # Update times if provided
        new_start_time = request.start_time if request.start_time is not None else event.start_time
        new_end_time = request.end_time if request.end_time is not None else event.end_time
        
        # Validate that end time is after start time (Requirements 22.4)
        if new_end_time <= new_start_time:
            raise ReleaseEventValidationError(
                "End time must be after start time",
                field="end_time"
            )
        
        if request.start_time is not None:
            event.start_time = request.start_time
        
        if request.end_time is not None:
            event.end_time = request.end_time
        
        event.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the event update
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_event_updated',
                user_id=str(user_id),
                details={
                    "event_id": event.id,
                    "event_name": event.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._release_event_to_response(event)
    
    def delete_release_event(self, event_id: int, user_id: str) -> None:
        """
        Delete a release event and all associated phases.
        
        :param event_id: The release event's unique identifier
        :param user_id: The ID of the user deleting the event
        :raises ReleaseEventNotFoundError: If event is not found
        
        Validates: Requirements 22.3
        """
        from automojo.pychestrate.core.orm import ProjectReleaseEvent
        
        event = self._db_session.query(ProjectReleaseEvent).filter(
            ProjectReleaseEvent.id == event_id
        ).first()
        
        if not event:
            raise ReleaseEventNotFoundError(f"Release event with ID '{event_id}' not found")
        
        event_name = event.name
        project_id = event.project_id
        
        # Delete the event (cascades to phases due to relationship configuration)
        self._db_session.delete(event)
        self._db_session.commit()
        
        # Log the event deletion
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_event_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "event_id": event_id,
                    "event_name": event_name
                }
            )
    
    def list_release_events(
        self,
        project_id: int,
        start_time: datetime = None,
        end_time: datetime = None,
        release_id: int = None,
        offset: int = 0,
        limit: int = 50
    ) -> ReleaseEventListResponse:
        """
        List release events with filtering.
        
        :param project_id: The project's unique identifier
        :param start_time: Optional filter for events starting after this time
        :param end_time: Optional filter for events ending before this time
        :param release_id: Optional filter by release ID
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: ReleaseEventListResponse with paginated event list
        
        Validates: Requirements 22.5, 22.6
        """
        from automojo.pychestrate.core.orm import ProjectReleaseEvent
        
        query = self._db_session.query(ProjectReleaseEvent).filter(
            ProjectReleaseEvent.project_id == project_id
        )
        
        # Apply filters
        if start_time is not None:
            query = query.filter(ProjectReleaseEvent.end_time >= start_time)
        
        if end_time is not None:
            query = query.filter(ProjectReleaseEvent.start_time <= end_time)
        
        if release_id is not None:
            query = query.filter(ProjectReleaseEvent.release_id == release_id)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (order by start_time)
        events = query.order_by(ProjectReleaseEvent.start_time).offset(offset).limit(limit).all()
        
        return ReleaseEventListResponse(
            events=[self._release_event_to_response(event) for event in events],
            total=total,
            offset=offset,
            limit=limit
        )

    
        # =========================================================================
        # Calendar Event Management - Phase Events
        # =========================================================================
    
    def create_phase_event(
        self,
        request: PhaseEventCreateRequest,
        user_id: str
    ) -> PhaseEventResponse:
        """
        Create a phase event within a release event.
        
        :param request: The phase event creation request
        :param user_id: The ID of the user creating the phase
        :returns: PhaseEventResponse with the created phase data
        :raises ReleaseEventNotFoundError: If release event is not found
        :raises PhaseEventValidationError: If validation fails
        
        Validates: Requirements 23.1, 23.4
        """
        from automojo.pychestrate.core.orm import ProjectReleaseEvent, ProjectPhaseEvent
        
        # Verify release event exists
        release_event = self._db_session.query(ProjectReleaseEvent).filter(
            ProjectReleaseEvent.id == request.release_event_id
        ).first()
        
        if not release_event:
            raise ReleaseEventNotFoundError(
                f"Release event with ID '{request.release_event_id}' not found"
            )
        
        # Validate that phase times fall within parent release event times (Requirements 23.4)
        if request.start_time < release_event.start_time:
            raise PhaseEventValidationError(
                "Phase start time must be within the release event time range",
                field="start_time"
            )
        
        if request.end_time > release_event.end_time:
            raise PhaseEventValidationError(
                "Phase end time must be within the release event time range",
                field="end_time"
            )
        
        if request.end_time <= request.start_time:
            raise PhaseEventValidationError(
                "Phase end time must be after start time",
                field="end_time"
            )
        
        # Create the phase event
        now = utc_now()
        
        phase = ProjectPhaseEvent(
            release_event_id=request.release_event_id,
            name=request.name,
            description=request.description or "",
            start_time=request.start_time,
            end_time=request.end_time,
            order=request.order,
            status='planned',
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(phase)
        self._db_session.commit()
        
        # Log the phase creation
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='phase_event_created',
                user_id=str(user_id),
                details={
                    "release_event_id": request.release_event_id,
                    "phase_id": phase.id,
                    "phase_name": phase.name,
                    "order": phase.order
                }
            )
        
        return self._phase_event_to_response(phase)
    
    def get_phase_event(self, phase_id: int) -> Optional[PhaseEventResponse]:
        """
        Get phase event by ID.
        
        :param phase_id: The phase event's unique identifier
        :returns: PhaseEventResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectPhaseEvent
        
        phase = self._db_session.query(ProjectPhaseEvent).filter(
            ProjectPhaseEvent.id == phase_id
        ).first()
        
        if not phase:
            return None
        
        return self._phase_event_to_response(phase)
    
    def update_phase_event(
        self,
        phase_id: int,
        request: PhaseEventUpdateRequest,
        user_id: str
    ) -> PhaseEventResponse:
        """
        Update a phase event.
        
        :param phase_id: The phase event's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: PhaseEventResponse with the updated phase data
        :raises PhaseEventNotFoundError: If phase is not found
        :raises PhaseEventValidationError: If validation fails
        
        Validates: Requirements 23.2, 23.4, 23.5
        """
        from automojo.pychestrate.core.orm import ProjectPhaseEvent, ProjectReleaseEvent
        
        phase = self._db_session.query(ProjectPhaseEvent).filter(
            ProjectPhaseEvent.id == phase_id
        ).first()
        
        if not phase:
            raise PhaseEventNotFoundError(f"Phase event with ID '{phase_id}' not found")
        
        # Get the parent release event for validation
        release_event = self._db_session.query(ProjectReleaseEvent).filter(
            ProjectReleaseEvent.id == phase.release_event_id
        ).first()
        
        # Update name if provided
        if request.name is not None:
            phase.name = request.name
        
        # Update description if provided
        if request.description is not None:
            phase.description = request.description
        
        # Update order if provided
        if request.order is not None:
            phase.order = request.order
        
        # Update status if provided (Requirements 23.5)
        if request.status is not None:
            valid_statuses = ['planned', 'in_progress', 'completed']
            if request.status not in valid_statuses:
                raise PhaseEventValidationError(
                    f"Invalid status '{request.status}'. Must be one of: {', '.join(valid_statuses)}",
                    field="status"
                )
            phase.status = request.status
        
        # Update times if provided
        new_start_time = request.start_time if request.start_time is not None else phase.start_time
        new_end_time = request.end_time if request.end_time is not None else phase.end_time
        
        # Validate that phase times fall within parent release event times (Requirements 23.4)
        if release_event:
            if new_start_time < release_event.start_time:
                raise PhaseEventValidationError(
                    "Phase start time must be within the release event time range",
                    field="start_time"
                )
            
            if new_end_time > release_event.end_time:
                raise PhaseEventValidationError(
                    "Phase end time must be within the release event time range",
                    field="end_time"
                )
        
        if new_end_time <= new_start_time:
            raise PhaseEventValidationError(
                "Phase end time must be after start time",
                field="end_time"
            )
        
        if request.start_time is not None:
            phase.start_time = request.start_time
        
        if request.end_time is not None:
            phase.end_time = request.end_time
        
        phase.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the phase update
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='phase_event_updated',
                user_id=str(user_id),
                details={
                    "phase_id": phase.id,
                    "phase_name": phase.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._phase_event_to_response(phase)
    
    def delete_phase_event(self, phase_id: int, user_id: str) -> None:
        """
        Delete a phase event and reorder remaining phases.
        
        :param phase_id: The phase event's unique identifier
        :param user_id: The ID of the user deleting the phase
        :raises PhaseEventNotFoundError: If phase is not found
        
        Validates: Requirements 23.3
        """
        from automojo.pychestrate.core.orm import ProjectPhaseEvent
        
        phase = self._db_session.query(ProjectPhaseEvent).filter(
            ProjectPhaseEvent.id == phase_id
        ).first()
        
        if not phase:
            raise PhaseEventNotFoundError(f"Phase event with ID '{phase_id}' not found")
        
        phase_name = phase.name
        release_event_id = phase.release_event_id
        deleted_order = phase.order
        
        # Delete the phase
        self._db_session.delete(phase)
        
        # Reorder remaining phases (Requirements 23.3)
        remaining_phases = self._db_session.query(ProjectPhaseEvent).filter(
            ProjectPhaseEvent.release_event_id == release_event_id,
            ProjectPhaseEvent.order > deleted_order
        ).all()
        
        for remaining_phase in remaining_phases:
            remaining_phase.order -= 1
        
        self._db_session.commit()
        
        # Log the phase deletion
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='phase_event_deleted',
                user_id=str(user_id),
                details={
                    "release_event_id": release_event_id,
                    "phase_id": phase_id,
                    "phase_name": phase_name
                }
            )
    
    def list_phase_events(self, release_event_id: int) -> PhaseEventListResponse:
        """
        List phases for a release event ordered by their order field.
        
        :param release_event_id: The release event's unique identifier
        :returns: PhaseEventListResponse with phase list
        :raises ReleaseEventNotFoundError: If release event is not found
        
        Validates: Requirements 23.6
        """
        from automojo.pychestrate.core.orm import ProjectReleaseEvent, ProjectPhaseEvent
        
        # Verify release event exists
        release_event = self._db_session.query(ProjectReleaseEvent).filter(
            ProjectReleaseEvent.id == release_event_id
        ).first()
        
        if not release_event:
            raise ReleaseEventNotFoundError(
                f"Release event with ID '{release_event_id}' not found"
            )
        
        phases = self._db_session.query(ProjectPhaseEvent).filter(
            ProjectPhaseEvent.release_event_id == release_event_id
        ).order_by(ProjectPhaseEvent.order).all()
        
        return PhaseEventListResponse(
            phases=[self._phase_event_to_response(phase) for phase in phases],
            total=len(phases)
        )

    
        # =========================================================================
        # Calendar Event Management - Release Branches
        # =========================================================================
    
    def _release_branch_to_response(self, branch) -> ReleaseBranchResponse:
        """
        Convert a ProjectReleaseBranch ORM object to a ReleaseBranchResponse.
        
        :param branch: The ProjectReleaseBranch ORM object
        :returns: ReleaseBranchResponse dataclass
        """
        repository_name = branch.repository.name if branch.repository else ""
        
        return ReleaseBranchResponse(
            id=branch.id,
            release_id=branch.release_id,
            repository_id=branch.repository_id,
            repository_name=repository_name,
            branch_name=branch.branch_name,
            description=branch.description or "",
            created_at=branch.created_at
        )
    
    def add_release_branch(
        self,
        request: ReleaseBranchCreateRequest,
        user_id: str
    ) -> ReleaseBranchResponse:
        """
        Associate a branch with a release.
        
        :param request: The release branch creation request
        :param user_id: The ID of the user creating the association
        :returns: ReleaseBranchResponse with the created association data
        :raises ReleaseNotFoundError: If release is not found
        :raises RepositoryNotFoundError: If repository is not found or doesn't belong to project
        :raises DuplicateReleaseBranchError: If branch association already exists
        
        Validates: Requirements 24.1, 24.3, 24.4
        """
        from automojo.pychestrate.core.orm import ProjectRelease, ProjectRepository, ProjectReleaseBranch
        
        # Verify release exists
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == request.release_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(f"Release with ID '{request.release_id}' not found")
        
        # Verify repository exists and belongs to the release's project (Requirements 24.3)
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == request.repository_id,
            ProjectRepository.project_id == release.project_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(
                f"Repository with ID '{request.repository_id}' not found in the release's project"
            )
        
        # Check for duplicate branch association (Requirements 24.4)
        existing_branch = self._db_session.query(ProjectReleaseBranch).filter(
            ProjectReleaseBranch.release_id == request.release_id,
            ProjectReleaseBranch.repository_id == request.repository_id,
            ProjectReleaseBranch.branch_name == request.branch_name
        ).first()
        
        if existing_branch:
            raise DuplicateReleaseBranchError(
                f"Branch '{request.branch_name}' is already associated with this release for repository '{repository.name}'",
                field="branch_name"
            )
        
        # Create the branch association
        now = utc_now()
        
        branch = ProjectReleaseBranch(
            release_id=request.release_id,
            repository_id=request.repository_id,
            branch_name=request.branch_name,
            description=request.description or "",
            created_at=now
        )
        
        self._db_session.add(branch)
        self._db_session.commit()
        
        # Log the branch association
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_branch_added',
                user_id=str(user_id),
                details={
                    "release_id": request.release_id,
                    "repository_id": request.repository_id,
                    "branch_name": request.branch_name
                }
            )
        
        return self._release_branch_to_response(branch)
    
    def remove_release_branch(self, branch_id: int, user_id: str) -> None:
        """
        Remove a branch association from a release.
        
        :param branch_id: The release branch's unique identifier
        :param user_id: The ID of the user removing the association
        :raises ReleaseBranchNotFoundError: If branch association is not found
        
        Validates: Requirements 24.2
        """
        from automojo.pychestrate.core.orm import ProjectReleaseBranch
        
        branch = self._db_session.query(ProjectReleaseBranch).filter(
            ProjectReleaseBranch.id == branch_id
        ).first()
        
        if not branch:
            raise ReleaseBranchNotFoundError(f"Release branch with ID '{branch_id}' not found")
        
        branch_name = branch.branch_name
        release_id = branch.release_id
        repository_id = branch.repository_id
        
        self._db_session.delete(branch)
        self._db_session.commit()
        
        # Log the branch removal
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='release_branch_removed',
                user_id=str(user_id),
                details={
                    "release_id": release_id,
                    "repository_id": repository_id,
                    "branch_name": branch_name
                }
            )
    
    def list_release_branches(self, release_id: int) -> ReleaseBranchListResponse:
        """
        List branches associated with a release.
        
        :param release_id: The release's unique identifier
        :returns: ReleaseBranchListResponse with branch list
        :raises ReleaseNotFoundError: If release is not found
        
        Validates: Requirements 24.5
        """
        from automojo.pychestrate.core.orm import ProjectRelease, ProjectReleaseBranch
        
        # Verify release exists
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == release_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(f"Release with ID '{release_id}' not found")
        
        branches = self._db_session.query(ProjectReleaseBranch).filter(
            ProjectReleaseBranch.release_id == release_id
        ).order_by(ProjectReleaseBranch.branch_name).all()
        
        return ReleaseBranchListResponse(
            branches=[self._release_branch_to_response(branch) for branch in branches],
            total=len(branches)
        )

    
        # =========================================================================
        # Calendar Event Management - Merge Events
        # =========================================================================
    
    def _merge_event_to_response(self, event) -> MergeEventResponse:
        """
        Convert a ProjectMergeEvent ORM object to a MergeEventResponse.
        
        :param event: The ProjectMergeEvent ORM object
        :returns: MergeEventResponse dataclass
        """
        from automojo.pychestrate.core.orm import User
        
        repository_name = event.repository.name if event.repository else ""
        
        # Get executed by username
        executed_by_username = None
        if event.executed_by_id:
            user = self._db_session.query(User).filter(User.id == event.executed_by_id).first()
            if user:
                executed_by_username = user.login
        
        return MergeEventResponse(
            id=event.id,
            project_id=event.project_id,
            release_id=event.release_id,
            repository_id=event.repository_id,
            repository_name=repository_name,
            source_branch=event.source_branch,
            target_branch=event.target_branch,
            name=event.name,
            description=event.description or "",
            scheduled_time=event.scheduled_time,
            status=event.status,
            executed_at=event.executed_at,
            executed_by_id=str(event.executed_by_id) if event.executed_by_id else None,
            executed_by_username=executed_by_username,
            error_message=event.error_message,
            created_at=event.created_at,
            updated_at=event.updated_at
        )
    
    def create_merge_event(
        self,
        project_id: int,
        request: MergeEventCreateRequest,
        user_id: str
    ) -> MergeEventResponse:
        """
        Create a scheduled merge event.
        
        :param project_id: The project's unique identifier
        :param request: The merge event creation request
        :param user_id: The ID of the user creating the event
        :returns: MergeEventResponse with the created event data
        :raises ProjectNotFoundError: If project is not found
        :raises ReleaseNotFoundError: If release is not found
        :raises RepositoryNotFoundError: If repository is not found
        
        Validates: Requirements 25.1
        """
        from automojo.pychestrate.core.orm import Project, ProjectRelease, ProjectRepository, ProjectMergeEvent
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Verify release exists and belongs to project
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == request.release_id,
            ProjectRelease.project_id == project_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(
                f"Release with ID '{request.release_id}' not found in project '{project.name}'"
            )
        
        # Verify repository exists and belongs to project
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == request.repository_id,
            ProjectRepository.project_id == project_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(
                f"Repository with ID '{request.repository_id}' not found in project '{project.name}'"
            )
        
        # Create the merge event
        now = utc_now()
        
        event = ProjectMergeEvent(
            project_id=project_id,
            release_id=request.release_id,
            repository_id=request.repository_id,
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            name=request.name,
            description=request.description or "",
            scheduled_time=request.scheduled_time,
            status='scheduled',
            executed_at=None,
            executed_by_id=None,
            error_message=None,
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(event)
        self._db_session.commit()
        
        # Log the event creation
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='merge_event_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "event_id": event.id,
                    "event_name": event.name,
                    "source_branch": request.source_branch,
                    "target_branch": request.target_branch
                }
            )
        
        return self._merge_event_to_response(event)
    
    def get_merge_event(self, event_id: int) -> Optional[MergeEventResponse]:
        """
        Get merge event by ID.
        
        :param event_id: The merge event's unique identifier
        :returns: MergeEventResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectMergeEvent
        
        event = self._db_session.query(ProjectMergeEvent).filter(
            ProjectMergeEvent.id == event_id
        ).first()
        
        if not event:
            return None
        
        return self._merge_event_to_response(event)
    
    def update_merge_event(
        self,
        event_id: int,
        request: MergeEventUpdateRequest,
        user_id: str
    ) -> MergeEventResponse:
        """
        Update a merge event.
        
        :param event_id: The merge event's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: MergeEventResponse with the updated event data
        :raises MergeEventNotFoundError: If event is not found
        :raises MergeEventValidationError: If validation fails
        
        Validates: Requirements 25.2, 25.6
        """
        from automojo.pychestrate.core.orm import ProjectMergeEvent
        
        event = self._db_session.query(ProjectMergeEvent).filter(
            ProjectMergeEvent.id == event_id
        ).first()
        
        if not event:
            raise MergeEventNotFoundError(f"Merge event with ID '{event_id}' not found")
        
        # Update name if provided
        if request.name is not None:
            event.name = request.name
        
        # Update description if provided
        if request.description is not None:
            event.description = request.description
        
        # Update scheduled_time if provided
        if request.scheduled_time is not None:
            event.scheduled_time = request.scheduled_time
        
        # Update status if provided (Requirements 25.6)
        if request.status is not None:
            valid_statuses = ['scheduled', 'in_progress', 'completed', 'failed']
            if request.status not in valid_statuses:
                raise MergeEventValidationError(
                    f"Invalid status '{request.status}'. Must be one of: {', '.join(valid_statuses)}",
                    field="status"
                )
            event.status = request.status
        
        event.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the event update
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='merge_event_updated',
                user_id=str(user_id),
                details={
                    "event_id": event.id,
                    "event_name": event.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._merge_event_to_response(event)
    
    def delete_merge_event(self, event_id: int, user_id: str) -> None:
        """
        Delete a merge event.
        
        :param event_id: The merge event's unique identifier
        :param user_id: The ID of the user deleting the event
        :raises MergeEventNotFoundError: If event is not found
        
        Validates: Requirements 25.3
        """
        from automojo.pychestrate.core.orm import ProjectMergeEvent
        
        event = self._db_session.query(ProjectMergeEvent).filter(
            ProjectMergeEvent.id == event_id
        ).first()
        
        if not event:
            raise MergeEventNotFoundError(f"Merge event with ID '{event_id}' not found")
        
        event_name = event.name
        project_id = event.project_id
        
        self._db_session.delete(event)
        self._db_session.commit()
        
        # Log the event deletion
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='merge_event_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "event_id": event_id,
                    "event_name": event_name
                }
            )
    
    def list_merge_events(
        self,
        project_id: int,
        release_id: int = None,
        repository_id: int = None,
        status: str = None,
        offset: int = 0,
        limit: int = 50
    ) -> MergeEventListResponse:
        """
        List merge events with filtering.
        
        :param project_id: The project's unique identifier
        :param release_id: Optional filter by release ID
        :param repository_id: Optional filter by repository ID
        :param status: Optional filter by status
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: MergeEventListResponse with paginated event list
        
        Validates: Requirements 25.7
        """
        from automojo.pychestrate.core.orm import ProjectMergeEvent
        
        query = self._db_session.query(ProjectMergeEvent).filter(
            ProjectMergeEvent.project_id == project_id
        )
        
        # Apply filters
        if release_id is not None:
            query = query.filter(ProjectMergeEvent.release_id == release_id)
        
        if repository_id is not None:
            query = query.filter(ProjectMergeEvent.repository_id == repository_id)
        
        if status is not None:
            query = query.filter(ProjectMergeEvent.status == status)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (order by scheduled_time)
        events = query.order_by(ProjectMergeEvent.scheduled_time).offset(offset).limit(limit).all()
        
        return MergeEventListResponse(
            events=[self._merge_event_to_response(event) for event in events],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def execute_merge_event(self, event_id: int, user_id: str) -> MergeEventResponse:
        """
        Execute a merge event.
        
        :param event_id: The merge event's unique identifier
        :param user_id: The ID of the user executing the merge
        :returns: MergeEventResponse with the updated event data
        :raises MergeEventNotFoundError: If event is not found
        :raises MergeEventValidationError: If event cannot be executed
        
        Validates: Requirements 25.4, 25.5, 25.6
        """
        from automojo.pychestrate.core.orm import ProjectMergeEvent
        
        event = self._db_session.query(ProjectMergeEvent).filter(
            ProjectMergeEvent.id == event_id
        ).first()
        
        if not event:
            raise MergeEventNotFoundError(f"Merge event with ID '{event_id}' not found")
        
        # Check if event can be executed
        if event.status not in ['scheduled']:
            raise MergeEventValidationError(
                f"Merge event with status '{event.status}' cannot be executed",
                field="status"
            )
        
        # Update status to in_progress
        event.status = 'in_progress'
        event.updated_at = utc_now()
        self._db_session.commit()
        
        try:
            # In a real implementation, this would perform the actual merge
            # For now, we'll simulate a successful merge
            event.status = 'completed'
            event.executed_at = utc_now()
            event.executed_by_id = user_id
            event.error_message = None
            
            # Log the successful execution
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type='merge_event_executed',
                    user_id=str(user_id),
                    details={
                        "event_id": event.id,
                        "event_name": event.name,
                        "source_branch": event.source_branch,
                        "target_branch": event.target_branch,
                        "status": "completed"
                    }
                )
        except Exception as e:
            # Handle merge failure (Requirements 25.5)
            event.status = 'failed'
            event.executed_at = utc_now()
            event.executed_by_id = user_id
            event.error_message = str(e)
            
            # Log the failed execution
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type='merge_event_failed',
                    user_id=str(user_id),
                    details={
                        "event_id": event.id,
                        "event_name": event.name,
                        "error": str(e)
                    }
                )
        
        event.updated_at = utc_now()
        self._db_session.commit()
        
        return self._merge_event_to_response(event)

    
        # =========================================================================
        # Calendar Event Management - Pull Events
        # =========================================================================
    
    def _pull_event_to_response(self, event) -> PullEventResponse:
        """
        Convert a ProjectPullEvent ORM object to a PullEventResponse.
        
        :param event: The ProjectPullEvent ORM object
        :returns: PullEventResponse dataclass
        """
        from automojo.pychestrate.core.orm import User
        
        repository_name = event.repository.name if event.repository else ""
        
        # Get executed by username
        executed_by_username = None
        if event.executed_by_id:
            user = self._db_session.query(User).filter(User.id == event.executed_by_id).first()
            if user:
                executed_by_username = user.login
        
        return PullEventResponse(
            id=event.id,
            project_id=event.project_id,
            release_id=event.release_id,
            repository_id=event.repository_id,
            repository_name=repository_name,
            source_branch=event.source_branch,
            target_branch=event.target_branch,
            name=event.name,
            description=event.description or "",
            scheduled_time=event.scheduled_time,
            status=event.status,
            executed_at=event.executed_at,
            executed_by_id=str(event.executed_by_id) if event.executed_by_id else None,
            executed_by_username=executed_by_username,
            error_message=event.error_message,
            created_at=event.created_at,
            updated_at=event.updated_at
        )
    
    def create_pull_event(
        self,
        project_id: int,
        request: PullEventCreateRequest,
        user_id: str
    ) -> PullEventResponse:
        """
        Create a scheduled pull event.
        
        :param project_id: The project's unique identifier
        :param request: The pull event creation request
        :param user_id: The ID of the user creating the event
        :returns: PullEventResponse with the created event data
        :raises ProjectNotFoundError: If project is not found
        :raises ReleaseNotFoundError: If release is not found
        :raises RepositoryNotFoundError: If repository is not found
        
        Validates: Requirements 26.1
        """
        from automojo.pychestrate.core.orm import Project, ProjectRelease, ProjectRepository, ProjectPullEvent
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Verify release exists and belongs to project
        release = self._db_session.query(ProjectRelease).filter(
            ProjectRelease.id == request.release_id,
            ProjectRelease.project_id == project_id
        ).first()
        
        if not release:
            raise ReleaseNotFoundError(
                f"Release with ID '{request.release_id}' not found in project '{project.name}'"
            )
        
        # Verify repository exists and belongs to project
        repository = self._db_session.query(ProjectRepository).filter(
            ProjectRepository.id == request.repository_id,
            ProjectRepository.project_id == project_id
        ).first()
        
        if not repository:
            raise RepositoryNotFoundError(
                f"Repository with ID '{request.repository_id}' not found in project '{project.name}'"
            )
        
        # Create the pull event
        now = utc_now()
        
        event = ProjectPullEvent(
            project_id=project_id,
            release_id=request.release_id,
            repository_id=request.repository_id,
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            name=request.name,
            description=request.description or "",
            scheduled_time=request.scheduled_time,
            status='scheduled',
            executed_at=None,
            executed_by_id=None,
            error_message=None,
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(event)
        self._db_session.commit()
        
        # Log the event creation
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pull_event_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "event_id": event.id,
                    "event_name": event.name,
                    "source_branch": request.source_branch,
                    "target_branch": request.target_branch
                }
            )
        
        return self._pull_event_to_response(event)
    
    def get_pull_event(self, event_id: int) -> Optional[PullEventResponse]:
        """
        Get pull event by ID.
        
        :param event_id: The pull event's unique identifier
        :returns: PullEventResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import ProjectPullEvent
        
        event = self._db_session.query(ProjectPullEvent).filter(
            ProjectPullEvent.id == event_id
        ).first()
        
        if not event:
            return None
        
        return self._pull_event_to_response(event)
    
    def update_pull_event(
        self,
        event_id: int,
        request: PullEventUpdateRequest,
        user_id: str
    ) -> PullEventResponse:
        """
        Update a pull event.
        
        :param event_id: The pull event's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: PullEventResponse with the updated event data
        :raises PullEventNotFoundError: If event is not found
        :raises PullEventValidationError: If validation fails
        
        Validates: Requirements 26.2, 26.6
        """
        from automojo.pychestrate.core.orm import ProjectPullEvent
        
        event = self._db_session.query(ProjectPullEvent).filter(
            ProjectPullEvent.id == event_id
        ).first()
        
        if not event:
            raise PullEventNotFoundError(f"Pull event with ID '{event_id}' not found")
        
        # Update name if provided
        if request.name is not None:
            event.name = request.name
        
        # Update description if provided
        if request.description is not None:
            event.description = request.description
        
        # Update scheduled_time if provided
        if request.scheduled_time is not None:
            event.scheduled_time = request.scheduled_time
        
        # Update status if provided (Requirements 26.6)
        if request.status is not None:
            valid_statuses = ['scheduled', 'in_progress', 'completed', 'failed']
            if request.status not in valid_statuses:
                raise PullEventValidationError(
                    f"Invalid status '{request.status}'. Must be one of: {', '.join(valid_statuses)}",
                    field="status"
                )
            event.status = request.status
        
        event.updated_at = utc_now()
        
        self._db_session.commit()
        
        # Log the event update
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pull_event_updated',
                user_id=str(user_id),
                details={
                    "event_id": event.id,
                    "event_name": event.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._pull_event_to_response(event)
    
    def delete_pull_event(self, event_id: int, user_id: str) -> None:
        """
        Delete a pull event.
        
        :param event_id: The pull event's unique identifier
        :param user_id: The ID of the user deleting the event
        :raises PullEventNotFoundError: If event is not found
        
        Validates: Requirements 26.3
        """
        from automojo.pychestrate.core.orm import ProjectPullEvent
        
        event = self._db_session.query(ProjectPullEvent).filter(
            ProjectPullEvent.id == event_id
        ).first()
        
        if not event:
            raise PullEventNotFoundError(f"Pull event with ID '{event_id}' not found")
        
        event_name = event.name
        project_id = event.project_id
        
        self._db_session.delete(event)
        self._db_session.commit()
        
        # Log the event deletion
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pull_event_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "event_id": event_id,
                    "event_name": event_name
                }
            )
    
    def list_pull_events(
        self,
        project_id: int,
        release_id: int = None,
        repository_id: int = None,
        status: str = None,
        offset: int = 0,
        limit: int = 50
    ) -> PullEventListResponse:
        """
        List pull events with filtering.
        
        :param project_id: The project's unique identifier
        :param release_id: Optional filter by release ID
        :param repository_id: Optional filter by repository ID
        :param status: Optional filter by status
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: PullEventListResponse with paginated event list
        
        Validates: Requirements 26.7
        """
        from automojo.pychestrate.core.orm import ProjectPullEvent
        
        query = self._db_session.query(ProjectPullEvent).filter(
            ProjectPullEvent.project_id == project_id
        )
        
        # Apply filters
        if release_id is not None:
            query = query.filter(ProjectPullEvent.release_id == release_id)
        
        if repository_id is not None:
            query = query.filter(ProjectPullEvent.repository_id == repository_id)
        
        if status is not None:
            query = query.filter(ProjectPullEvent.status == status)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (order by scheduled_time)
        events = query.order_by(ProjectPullEvent.scheduled_time).offset(offset).limit(limit).all()
        
        return PullEventListResponse(
            events=[self._pull_event_to_response(event) for event in events],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def execute_pull_event(self, event_id: int, user_id: str) -> PullEventResponse:
        """
        Execute a pull event.
        
        :param event_id: The pull event's unique identifier
        :param user_id: The ID of the user executing the pull
        :returns: PullEventResponse with the updated event data
        :raises PullEventNotFoundError: If event is not found
        :raises PullEventValidationError: If event cannot be executed
        
        Validates: Requirements 26.4, 26.5, 26.6
        """
        from automojo.pychestrate.core.orm import ProjectPullEvent
        
        event = self._db_session.query(ProjectPullEvent).filter(
            ProjectPullEvent.id == event_id
        ).first()
        
        if not event:
            raise PullEventNotFoundError(f"Pull event with ID '{event_id}' not found")
        
        # Check if event can be executed
        if event.status not in ['scheduled']:
            raise PullEventValidationError(
                f"Pull event with status '{event.status}' cannot be executed",
                field="status"
            )
        
        # Update status to in_progress
        event.status = 'in_progress'
        event.updated_at = utc_now()
        self._db_session.commit()
        
        try:
            # In a real implementation, this would perform the actual pull
            # For now, we'll simulate a successful pull
            event.status = 'completed'
            event.executed_at = utc_now()
            event.executed_by_id = user_id
            event.error_message = None
            
            # Log the successful execution
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type='pull_event_executed',
                    user_id=str(user_id),
                    details={
                        "event_id": event.id,
                        "event_name": event.name,
                        "source_branch": event.source_branch,
                        "target_branch": event.target_branch,
                        "status": "completed"
                    }
                )
        except Exception as e:
            # Handle pull failure (Requirements 26.5)
            event.status = 'failed'
            event.executed_at = utc_now()
            event.executed_by_id = user_id
            event.error_message = str(e)
            
            # Log the failed execution
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type='pull_event_failed',
                    user_id=str(user_id),
                    details={
                        "event_id": event.id,
                        "event_name": event.name,
                        "error": str(e)
                    }
                )
        
        event.updated_at = utc_now()
        self._db_session.commit()
        
        return self._pull_event_to_response(event)

    
        # =========================================================================
        # Calendar Event Management - Unified Calendar View
        # =========================================================================
    
    def get_calendar_events(
        self,
        project_id: int,
        start_time: datetime = None,
        end_time: datetime = None,
        event_types: List[str] = None
    ) -> CalendarEventsResponse:
        """
        Get unified calendar view of all event types.
        
        :param project_id: The project's unique identifier
        :param start_time: Optional filter for events starting after this time
        :param end_time: Optional filter for events ending before this time
        :param event_types: Optional list of event types to include
        :returns: CalendarEventsResponse with all calendar events
        
        Validates: Requirements 22.5, 22.6
        """
        from automojo.pychestrate.core.orm import (
            ProjectReleaseEvent, ProjectMergeEvent, ProjectPullEvent
        )
        
        all_events = []
        
        # Default to all event types if not specified
        if event_types is None:
            event_types = ['release_event', 'merge_event', 'pull_event']
        
        # Get release events
        if 'release_event' in event_types:
            query = self._db_session.query(ProjectReleaseEvent).filter(
                ProjectReleaseEvent.project_id == project_id
            )
            
            if start_time is not None:
                query = query.filter(ProjectReleaseEvent.end_time >= start_time)
            
            if end_time is not None:
                query = query.filter(ProjectReleaseEvent.start_time <= end_time)
            
            for event in query.all():
                release_version = event.release.version if event.release else None
                all_events.append(CalendarEventResponse(
                    id=event.id,
                    project_id=event.project_id,
                    event_type='release_event',
                    name=event.name,
                    description=event.description or "",
                    start_time=event.start_time,
                    end_time=event.end_time,
                    created_at=event.created_at,
                    updated_at=event.updated_at,
                    release_id=event.release_id,
                    release_version=release_version,
                    repository_id=None,
                    repository_name=None,
                    source_branch=None,
                    target_branch=None,
                    status=None
                ))
        
        # Get merge events
        if 'merge_event' in event_types:
            query = self._db_session.query(ProjectMergeEvent).filter(
                ProjectMergeEvent.project_id == project_id
            )
            
            if start_time is not None:
                query = query.filter(ProjectMergeEvent.scheduled_time >= start_time)
            
            if end_time is not None:
                query = query.filter(ProjectMergeEvent.scheduled_time <= end_time)
            
            for event in query.all():
                repository_name = event.repository.name if event.repository else None
                all_events.append(CalendarEventResponse(
                    id=event.id,
                    project_id=event.project_id,
                    event_type='merge_event',
                    name=event.name,
                    description=event.description or "",
                    start_time=event.scheduled_time,
                    end_time=event.scheduled_time,  # Point-in-time event
                    created_at=event.created_at,
                    updated_at=event.updated_at,
                    release_id=event.release_id,
                    release_version=None,
                    repository_id=event.repository_id,
                    repository_name=repository_name,
                    source_branch=event.source_branch,
                    target_branch=event.target_branch,
                    status=event.status
                ))
        
        # Get pull events
        if 'pull_event' in event_types:
            query = self._db_session.query(ProjectPullEvent).filter(
                ProjectPullEvent.project_id == project_id
            )
            
            if start_time is not None:
                query = query.filter(ProjectPullEvent.scheduled_time >= start_time)
            
            if end_time is not None:
                query = query.filter(ProjectPullEvent.scheduled_time <= end_time)
            
            for event in query.all():
                repository_name = event.repository.name if event.repository else None
                all_events.append(CalendarEventResponse(
                    id=event.id,
                    project_id=event.project_id,
                    event_type='pull_event',
                    name=event.name,
                    description=event.description or "",
                    start_time=event.scheduled_time,
                    end_time=event.scheduled_time,  # Point-in-time event
                    created_at=event.created_at,
                    updated_at=event.updated_at,
                    release_id=event.release_id,
                    release_version=None,
                    repository_id=event.repository_id,
                    repository_name=repository_name,
                    source_branch=event.source_branch,
                    target_branch=event.target_branch,
                    status=event.status
                ))
        
        # Sort all events by start_time
        all_events.sort(key=lambda e: e.start_time)
        
        return CalendarEventsResponse(
            events=all_events,
            total=len(all_events)
        )
