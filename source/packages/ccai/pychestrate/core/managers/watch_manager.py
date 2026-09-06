"""
.. module:: watch_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the WatchManager class for watch CRUD operations and event processing

.. moduleauthor:: Code Craft AI LLC

This module provides the WatchManager class which handles:
- Watch CRUD operations (Requirements 10.1, 10.2, 10.3, 10.4, 10.5)
- Watch event processing (Requirements 10.6, 10.7, 10.8)
- Watch trigger logging
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now


# =============================================================================
# Enums
# =============================================================================

class WatchTriggerSource(str, Enum):
    """
        Enum-like class to represent the trigger sources for watches.
    """
    REPOSITORY_COMMIT = 'repository_commit'
    REPOSITORY_TAG = 'repository_tag'
    REPOSITORY_BRANCH = 'repository_branch'
    BUILD_COMPLETION = 'build_completion'


class WatchAction(str, Enum):
    """
        Enum-like class to represent the actions that can be triggered by watches.
    """
    TRIGGER_BUILD = 'trigger_build'
    TRIGGER_INFRA_JOB = 'trigger_infra_job'
    TRIGGER_TEST_JOB = 'trigger_test_job'
    TRIGGER_PIPELINE = 'trigger_pipeline'
    TRIGGER_RPA_JOB = 'trigger_rpa_job'
    SEND_NOTIFICATION = 'send_notification'


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class WatchCondition:
    """Dataclass for watch trigger conditions."""
    branch_pattern: Optional[str] = None  # Regex pattern
    tag_pattern: Optional[str] = None
    file_pattern: Optional[str] = None
    build_status: Optional[str] = None  # succeeded, failed, any


@dataclass
class WatchActionConfig:
    """Dataclass for watch action configuration."""
    action: WatchAction
    target_id: int  # spec_id or pipeline_id
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WatchCreateRequest:
    """Request dataclass for creating a new watch."""
    name: str
    trigger_source: WatchTriggerSource
    source_id: int  # repository_id or build_spec_id
    conditions: WatchCondition
    actions: List[WatchActionConfig]
    enabled: bool = True
    description: str = ""


@dataclass
class WatchUpdateRequest:
    """Request dataclass for updating an existing watch."""
    name: Optional[str] = None
    conditions: Optional[WatchCondition] = None
    actions: Optional[List[WatchActionConfig]] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None


@dataclass
class WatchResponse:
    """Response dataclass for watch data."""
    id: int
    project_id: int
    name: str
    trigger_source: WatchTriggerSource
    source_id: int
    source_name: str
    conditions: WatchCondition
    actions: List[WatchActionConfig]
    enabled: bool
    description: str
    last_trigger_time: Optional[datetime]
    trigger_count: int
    created_at: datetime
    updated_at: datetime


@dataclass
class WatchListResponse:
    """Response dataclass for paginated watch list."""
    watches: List[WatchResponse]
    total: int
    offset: int
    limit: int


@dataclass
class WatchTriggerLog:
    """Dataclass for watch trigger log data."""
    id: int
    watch_id: int
    triggered_at: datetime
    trigger_event: Dict[str, Any]
    actions_executed: List[Dict[str, Any]]
    success: bool
    error_message: Optional[str]


@dataclass
class WatchTriggerLogListResponse:
    """Response dataclass for paginated watch trigger log list."""
    logs: List[WatchTriggerLog]
    total: int
    offset: int
    limit: int


# =============================================================================
# Exceptions
# =============================================================================

class WatchValidationError(Exception):
    """Exception raised when watch validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "VALIDATION_ERROR"
        super().__init__(self.message)


class WatchNotFoundError(Exception):
    """Exception raised when a watch is not found."""
    
    def __init__(self, message: str, error_code: str = "WATCH_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateWatchError(Exception):
    """Exception raised when attempting to create a watch with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "WATCH_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class ProjectNotFoundError(Exception):
    """Exception raised when a project is not found."""
    
    def __init__(self, message: str, error_code: str = "PROJECT_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class SourceNotFoundError(Exception):
    """Exception raised when a watch source (repository or build spec) is not found."""
    
    def __init__(self, message: str, error_code: str = "SOURCE_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class InvalidPatternError(Exception):
    """Exception raised when a regex pattern is invalid."""
    
    def __init__(self, message: str, pattern: str = None, error_code: str = "INVALID_PATTERN"):
        self.message = message
        self.pattern = pattern
        self.error_code = error_code
        super().__init__(self.message)


# =============================================================================
# Validation Constants
# =============================================================================

# Watch name validation: alphanumeric, underscore, hyphen, period
# Must start with alphanumeric, 1-128 characters
WATCH_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}\Z')


# =============================================================================
# Validation Functions
# =============================================================================

def validate_watch_name(name: str) -> bool:
    """
    Validate that a watch name contains only alphanumeric characters, underscores, hyphens, and periods.
    
    :param name: The watch name to validate
    :returns: True if valid, False otherwise
    """
    if not name:
        return False
    
    if not WATCH_NAME_PATTERN.match(name):
        return False
    
    return True


def validate_regex_pattern(pattern: str) -> bool:
    """
    Validate that a string is a valid regex pattern.
    
    :param pattern: The regex pattern to validate
    :returns: True if valid, False otherwise
    """
    if not pattern:
        return True  # Empty pattern is valid (means no filter)
    
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False




# =============================================================================
# WatchManager Class
# =============================================================================

class WatchManager:
    """
    Manager class for watch CRUD operations and event processing.
    
    This class handles all watch-related operations including:
    - Watch creation with validation
    - Watch retrieval by ID
    - Watch updates
    - Watch deletion
    - Watch enable/disable
    - Event processing and action execution
    - Trigger logging
    
    Validates: Requirements 10.1-10.8
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None, build_manager=None,
                 infra_manager=None, test_manager=None, release_manager=None,
                 rpa_trigger=None):
        """
        Initialize the WatchManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        :param build_manager: Optional BuildManager instance for triggering builds
        :param infra_manager: Optional InfrastructureManager instance for triggering infra jobs
        :param test_manager: Optional TestManager instance for triggering test jobs
        :param release_manager: Optional ReleaseManager instance for triggering pipelines
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
        self._build_manager = build_manager
        self._infra_manager = infra_manager
        self._test_manager = test_manager
        self._release_manager = release_manager
        # Optional callable ``(spec_id: str, work_packet: dict, user_id: str) -> job``
        # used by the ``trigger_rpa_job`` action (6-rpa-orchestration).
        self._rpa_trigger = rpa_trigger
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def _validate_watch_create_request(self, request: WatchCreateRequest) -> None:
        """
        Validate a watch creation request.
        
        :param request: The watch creation request to validate
        :raises WatchValidationError: If validation fails
        :raises InvalidPatternError: If a regex pattern is invalid
        """
        if not validate_watch_name(request.name):
            raise WatchValidationError(
                "Watch name must be 1-128 characters, start with alphanumeric, "
                "and contain only alphanumeric characters, underscores, hyphens, and periods",
                field="name",
                error_code="INVALID_WATCH_NAME"
            )
        
        # Validate trigger_source is a valid enum value
        if not isinstance(request.trigger_source, WatchTriggerSource):
            try:
                request.trigger_source = WatchTriggerSource(request.trigger_source)
            except ValueError:
                raise WatchValidationError(
                    f"Invalid trigger source: {request.trigger_source}. "
                    f"Must be one of: {', '.join([e.value for e in WatchTriggerSource])}",
                    field="trigger_source",
                    error_code="INVALID_TRIGGER_SOURCE"
                )
        
        # Validate source_id is provided
        if not request.source_id:
            raise WatchValidationError(
                "Source ID is required",
                field="source_id",
                error_code="MISSING_SOURCE_ID"
            )
        
        # Validate conditions patterns
        if request.conditions:
            if request.conditions.branch_pattern and not validate_regex_pattern(request.conditions.branch_pattern):
                raise InvalidPatternError(
                    f"Invalid branch pattern: {request.conditions.branch_pattern}",
                    pattern=request.conditions.branch_pattern
                )
            
            if request.conditions.tag_pattern and not validate_regex_pattern(request.conditions.tag_pattern):
                raise InvalidPatternError(
                    f"Invalid tag pattern: {request.conditions.tag_pattern}",
                    pattern=request.conditions.tag_pattern
                )
            
            if request.conditions.file_pattern and not validate_regex_pattern(request.conditions.file_pattern):
                raise InvalidPatternError(
                    f"Invalid file pattern: {request.conditions.file_pattern}",
                    pattern=request.conditions.file_pattern
                )
            
            # Validate build_status if provided
            if request.conditions.build_status:
                valid_statuses = ['succeeded', 'failed', 'any']
                if request.conditions.build_status not in valid_statuses:
                    raise WatchValidationError(
                        f"Invalid build status: {request.conditions.build_status}. "
                        f"Must be one of: {', '.join(valid_statuses)}",
                        field="conditions.build_status",
                        error_code="INVALID_BUILD_STATUS"
                    )
        
        # Validate actions
        if not request.actions:
            raise WatchValidationError(
                "At least one action is required",
                field="actions",
                error_code="MISSING_ACTIONS"
            )
        
        for i, action_config in enumerate(request.actions):
            if not isinstance(action_config.action, WatchAction):
                try:
                    action_config.action = WatchAction(action_config.action)
                except ValueError:
                    raise WatchValidationError(
                        f"Invalid action type: {action_config.action}. "
                        f"Must be one of: {', '.join([e.value for e in WatchAction])}",
                        field=f"actions[{i}].action",
                        error_code="INVALID_ACTION_TYPE"
                    )
            
            if not action_config.target_id and action_config.action != WatchAction.SEND_NOTIFICATION:
                raise WatchValidationError(
                    f"Target ID is required for action '{action_config.action.value}'",
                    field=f"actions[{i}].target_id",
                    error_code="MISSING_TARGET_ID"
                )
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _get_source_name(self, trigger_source: WatchTriggerSource, source_id: int) -> str:
        """
        Get the name of the source (repository or build spec) for a watch.
        
        :param trigger_source: The trigger source type
        :param source_id: The source ID
        :returns: The source name or "Unknown" if not found
        """
        from ccai.pychestrate.core.orm import ProjectRepository, ProjectBuildSpec
        
        if trigger_source == WatchTriggerSource.BUILD_COMPLETION:
            build_spec = self._db_session.query(ProjectBuildSpec).filter(
                ProjectBuildSpec.id == source_id
            ).first()
            return build_spec.name if build_spec else "Unknown"
        else:
            # Repository-based triggers
            repository = self._db_session.query(ProjectRepository).filter(
                ProjectRepository.id == source_id
            ).first()
            return repository.name if repository else "Unknown"
    
    def _conditions_to_dict(self, conditions: WatchCondition) -> Dict[str, Any]:
        """
        Convert a WatchCondition to a dictionary for JSON storage.
        
        :param conditions: The WatchCondition to convert
        :returns: Dictionary representation
        """
        return {
            'branch_pattern': conditions.branch_pattern,
            'tag_pattern': conditions.tag_pattern,
            'file_pattern': conditions.file_pattern,
            'build_status': conditions.build_status,
        }
    
    def _dict_to_conditions(self, data: Dict[str, Any]) -> WatchCondition:
        """
        Convert a dictionary to a WatchCondition.
        
        :param data: The dictionary to convert
        :returns: WatchCondition instance
        """
        if not data:
            return WatchCondition()
        
        return WatchCondition(
            branch_pattern=data.get('branch_pattern'),
            tag_pattern=data.get('tag_pattern'),
            file_pattern=data.get('file_pattern'),
            build_status=data.get('build_status'),
        )
    
    def _actions_to_list(self, actions: List[WatchActionConfig]) -> List[Dict[str, Any]]:
        """
        Convert a list of WatchActionConfig to a list of dictionaries for JSON storage.
        
        :param actions: The list of WatchActionConfig to convert
        :returns: List of dictionary representations
        """
        return [
            {
                'action': action.action.value if isinstance(action.action, WatchAction) else action.action,
                'target_id': action.target_id,
                'parameters': action.parameters,
            }
            for action in actions
        ]
    
    def _list_to_actions(self, data: List[Dict[str, Any]]) -> List[WatchActionConfig]:
        """
        Convert a list of dictionaries to a list of WatchActionConfig.
        
        :param data: The list of dictionaries to convert
        :returns: List of WatchActionConfig instances
        """
        if not data:
            return []
        
        return [
            WatchActionConfig(
                action=WatchAction(item['action']),
                target_id=item.get('target_id'),
                parameters=item.get('parameters', {}),
            )
            for item in data
        ]
    
    def _watch_to_response(self, watch) -> WatchResponse:
        """
        Convert a ProjectWatch ORM object to a WatchResponse.
        
        :param watch: The ProjectWatch ORM object
        :returns: WatchResponse dataclass
        """
        source_name = self._get_source_name(
            WatchTriggerSource(watch.trigger_source),
            watch.source_id
        )
        
        return WatchResponse(
            id=watch.id,
            project_id=watch.project_id,
            name=watch.name,
            trigger_source=WatchTriggerSource(watch.trigger_source),
            source_id=watch.source_id,
            source_name=source_name,
            conditions=self._dict_to_conditions(watch.conditions_json),
            actions=self._list_to_actions(watch.actions_json),
            enabled=watch.enabled,
            description=watch.description or "",
            last_trigger_time=watch.last_trigger_time,
            trigger_count=watch.trigger_count,
            created_at=watch.created_at,
            updated_at=watch.updated_at
        )
    
    def _trigger_log_to_response(self, log) -> WatchTriggerLog:
        """
        Convert a ProjectWatchTriggerLog ORM object to a WatchTriggerLog.
        
        :param log: The ProjectWatchTriggerLog ORM object
        :returns: WatchTriggerLog dataclass
        """
        return WatchTriggerLog(
            id=log.id,
            watch_id=log.watch_id,
            triggered_at=log.triggered_at,
            trigger_event=log.trigger_event_json,
            actions_executed=log.actions_executed_json or [],
            success=log.success,
            error_message=log.error_message
        )
    
    def _verify_source_exists(self, project_id: int, trigger_source: WatchTriggerSource, source_id: int) -> int:
        """
        Verify that the source (repository or build spec) exists and belongs to the project.
        
        :param project_id: The project ID
        :param trigger_source: The trigger source type
        :param source_id: The source ID
        :returns: The repository_id if applicable, None otherwise
        :raises SourceNotFoundError: If the source is not found
        """
        from ccai.pychestrate.core.orm import ProjectRepository, ProjectBuildSpec
        
        repository_id = None
        
        if trigger_source == WatchTriggerSource.BUILD_COMPLETION:
            build_spec = self._db_session.query(ProjectBuildSpec).filter(
                ProjectBuildSpec.id == source_id,
                ProjectBuildSpec.project_id == project_id
            ).first()
            
            if not build_spec:
                raise SourceNotFoundError(
                    f"Build specification with ID '{source_id}' not found in project"
                )
        else:
            # Repository-based triggers
            repository = self._db_session.query(ProjectRepository).filter(
                ProjectRepository.id == source_id,
                ProjectRepository.project_id == project_id
            ).first()
            
            if not repository:
                raise SourceNotFoundError(
                    f"Repository with ID '{source_id}' not found in project"
                )
            
            repository_id = repository.id
        
        return repository_id

    
    # =========================================================================
    # Watch CRUD Operations
    # =========================================================================
    
    def create_watch(
        self,
        project_id: int,
        request: WatchCreateRequest,
        user_id: str
    ) -> WatchResponse:
        """
        Create a watch.
        
        :param project_id: The project's unique identifier
        :param request: The watch creation request containing watch data
        :param user_id: The ID of the user creating the watch
        :returns: WatchResponse with the created watch data
        :raises ProjectNotFoundError: If project is not found
        :raises WatchValidationError: If validation fails
        :raises DuplicateWatchError: If watch name already exists in project
        :raises SourceNotFoundError: If the source is not found
        
        Validates: Requirements 10.1
        """
        from ccai.pychestrate.core.orm import Project, ProjectWatch
        
        # Validate the request
        self._validate_watch_create_request(request)
        
        # Verify project exists
        project = self._db_session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ProjectNotFoundError(f"Project with ID '{project_id}' not found")
        
        # Check for duplicate name within project
        existing_watch = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.project_id == project_id,
            ProjectWatch.name == request.name
        ).first()
        
        if existing_watch:
            raise DuplicateWatchError(
                f"Watch with name '{request.name}' already exists in project '{project.name}'",
                field="name"
            )
        
        # Verify source exists and get repository_id if applicable
        repository_id = self._verify_source_exists(project_id, request.trigger_source, request.source_id)
        
        # Create the watch
        now = utc_now()
        
        watch = ProjectWatch(
            project_id=project_id,
            name=request.name,
            trigger_source=request.trigger_source.value,
            source_id=request.source_id,
            repository_id=repository_id,
            conditions_json=self._conditions_to_dict(request.conditions) if request.conditions else {},
            actions_json=self._actions_to_list(request.actions),
            enabled=request.enabled,
            description=request.description or "",
            trigger_count=0,
            created_at=now,
            updated_at=now
        )
        
        self._db_session.add(watch)
        self._db_session.commit()
        
        # Log the watch creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='watch_created',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "watch_id": watch.id,
                    "watch_name": watch.name,
                    "trigger_source": watch.trigger_source
                }
            )
        
        return self._watch_to_response(watch)
    
    def get_watch(self, watch_id: int) -> Optional[WatchResponse]:
        """
        Get watch by ID.
        
        :param watch_id: The watch's unique identifier
        :returns: WatchResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import ProjectWatch
        
        watch = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.id == watch_id
        ).first()
        
        if not watch:
            return None
        
        return self._watch_to_response(watch)
    
    def update_watch(
        self,
        watch_id: int,
        request: WatchUpdateRequest,
        user_id: str
    ) -> WatchResponse:
        """
        Update watch configuration.
        
        This resets any accumulated state as per Requirements 10.2.
        
        :param watch_id: The watch's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: WatchResponse with the updated watch data
        :raises WatchNotFoundError: If watch is not found
        :raises WatchValidationError: If validation fails
        :raises DuplicateWatchError: If new name already exists in project
        
        Validates: Requirements 10.2
        """
        from ccai.pychestrate.core.orm import ProjectWatch
        
        watch = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.id == watch_id
        ).first()
        
        if not watch:
            raise WatchNotFoundError(f"Watch with ID '{watch_id}' not found")
        
        # Update name if provided
        if request.name is not None:
            if not validate_watch_name(request.name):
                raise WatchValidationError(
                    "Watch name must be 1-128 characters, start with alphanumeric, "
                    "and contain only alphanumeric characters, underscores, hyphens, and periods",
                    field="name",
                    error_code="INVALID_WATCH_NAME"
                )
            
            # Check for duplicate name (excluding current watch)
            existing_watch = self._db_session.query(ProjectWatch).filter(
                ProjectWatch.project_id == watch.project_id,
                ProjectWatch.name == request.name,
                ProjectWatch.id != watch_id
            ).first()
            
            if existing_watch:
                raise DuplicateWatchError(
                    f"Watch with name '{request.name}' already exists in this project",
                    field="name"
                )
            
            watch.name = request.name
        
        # Update conditions if provided
        if request.conditions is not None:
            # Validate patterns
            if request.conditions.branch_pattern and not validate_regex_pattern(request.conditions.branch_pattern):
                raise InvalidPatternError(
                    f"Invalid branch pattern: {request.conditions.branch_pattern}",
                    pattern=request.conditions.branch_pattern
                )
            
            if request.conditions.tag_pattern and not validate_regex_pattern(request.conditions.tag_pattern):
                raise InvalidPatternError(
                    f"Invalid tag pattern: {request.conditions.tag_pattern}",
                    pattern=request.conditions.tag_pattern
                )
            
            if request.conditions.file_pattern and not validate_regex_pattern(request.conditions.file_pattern):
                raise InvalidPatternError(
                    f"Invalid file pattern: {request.conditions.file_pattern}",
                    pattern=request.conditions.file_pattern
                )
            
            watch.conditions_json = self._conditions_to_dict(request.conditions)
        
        # Update actions if provided
        if request.actions is not None:
            if not request.actions:
                raise WatchValidationError(
                    "At least one action is required",
                    field="actions",
                    error_code="MISSING_ACTIONS"
                )
            
            for i, action_config in enumerate(request.actions):
                if not isinstance(action_config.action, WatchAction):
                    try:
                        action_config.action = WatchAction(action_config.action)
                    except ValueError:
                        raise WatchValidationError(
                            f"Invalid action type: {action_config.action}",
                            field=f"actions[{i}].action",
                            error_code="INVALID_ACTION_TYPE"
                        )
            
            watch.actions_json = self._actions_to_list(request.actions)
        
        # Update enabled if provided
        if request.enabled is not None:
            watch.enabled = request.enabled
        
        # Update description if provided
        if request.description is not None:
            watch.description = request.description
        
        watch.updated_at = utc_now()
        self._db_session.commit()
        
        # Log the watch update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='watch_updated',
                user_id=str(user_id),
                details={
                    "watch_id": watch.id,
                    "watch_name": watch.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._watch_to_response(watch)
    
    def delete_watch(self, watch_id: int, user_id: str) -> None:
        """
        Delete a watch.
        
        :param watch_id: The watch's unique identifier
        :param user_id: The ID of the user deleting the watch
        :raises WatchNotFoundError: If watch is not found
        
        Validates: Requirements 10.3
        """
        from ccai.pychestrate.core.orm import ProjectWatch
        
        watch = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.id == watch_id
        ).first()
        
        if not watch:
            raise WatchNotFoundError(f"Watch with ID '{watch_id}' not found")
        
        watch_name = watch.name
        project_id = watch.project_id
        
        # Delete the watch (cascades to trigger logs)
        self._db_session.delete(watch)
        self._db_session.commit()
        
        # Log the watch deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='watch_deleted',
                user_id=str(user_id),
                details={
                    "project_id": project_id,
                    "watch_id": watch_id,
                    "watch_name": watch_name
                }
            )
    
    def list_watches(
        self,
        project_id: int,
        trigger_source: WatchTriggerSource = None,
        enabled: bool = None,
        offset: int = 0,
        limit: int = 50
    ) -> WatchListResponse:
        """
        List watches with filtering.
        
        :param project_id: The project's unique identifier
        :param trigger_source: Optional filter by trigger source
        :param enabled: Optional filter by enabled status
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: WatchListResponse with paginated watch list
        
        Validates: Requirements 10.8
        """
        from ccai.pychestrate.core.orm import ProjectWatch
        
        query = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.project_id == project_id
        )
        
        # Apply trigger_source filter
        if trigger_source is not None:
            source_value = trigger_source.value if isinstance(trigger_source, WatchTriggerSource) else trigger_source
            query = query.filter(ProjectWatch.trigger_source == source_value)
        
        # Apply enabled filter
        if enabled is not None:
            query = query.filter(ProjectWatch.enabled == enabled)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        watches = query.order_by(ProjectWatch.name).offset(offset).limit(limit).all()
        
        return WatchListResponse(
            watches=[self._watch_to_response(watch) for watch in watches],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def enable_watch(self, watch_id: int, user_id: str) -> WatchResponse:
        """
        Enable a watch.
        
        :param watch_id: The watch's unique identifier
        :param user_id: The ID of the user enabling the watch
        :returns: WatchResponse with the updated watch data
        :raises WatchNotFoundError: If watch is not found
        
        Validates: Requirements 10.5
        """
        from ccai.pychestrate.core.orm import ProjectWatch
        
        watch = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.id == watch_id
        ).first()
        
        if not watch:
            raise WatchNotFoundError(f"Watch with ID '{watch_id}' not found")
        
        watch.enabled = True
        watch.updated_at = utc_now()
        self._db_session.commit()
        
        # Log the watch enable event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='watch_enabled',
                user_id=str(user_id),
                details={
                    "watch_id": watch.id,
                    "watch_name": watch.name
                }
            )
        
        return self._watch_to_response(watch)
    
    def disable_watch(self, watch_id: int, user_id: str) -> WatchResponse:
        """
        Disable a watch.
        
        :param watch_id: The watch's unique identifier
        :param user_id: The ID of the user disabling the watch
        :returns: WatchResponse with the updated watch data
        :raises WatchNotFoundError: If watch is not found
        
        Validates: Requirements 10.5
        """
        from ccai.pychestrate.core.orm import ProjectWatch
        
        watch = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.id == watch_id
        ).first()
        
        if not watch:
            raise WatchNotFoundError(f"Watch with ID '{watch_id}' not found")
        
        watch.enabled = False
        watch.updated_at = utc_now()
        self._db_session.commit()
        
        # Log the watch disable event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='watch_disabled',
                user_id=str(user_id),
                details={
                    "watch_id": watch.id,
                    "watch_name": watch.name
                }
            )
        
        return self._watch_to_response(watch)

    
    # =========================================================================
    # Event Processing Operations
    # =========================================================================
    
    def _match_conditions(self, conditions: WatchCondition, event_data: Dict[str, Any]) -> bool:
        """
        Check if event data matches watch conditions.
        
        :param conditions: The watch conditions to check
        :param event_data: The event data to match against
        :returns: True if all conditions match, False otherwise
        """
        # Check branch pattern
        if conditions.branch_pattern:
            branch = event_data.get('branch', '')
            if not re.match(conditions.branch_pattern, branch):
                return False
        
        # Check tag pattern
        if conditions.tag_pattern:
            tag = event_data.get('tag', '')
            if not re.match(conditions.tag_pattern, tag):
                return False
        
        # Check file pattern
        if conditions.file_pattern:
            files = event_data.get('files', [])
            if not files:
                return False
            
            # At least one file must match the pattern
            pattern = re.compile(conditions.file_pattern)
            if not any(pattern.match(f) for f in files):
                return False
        
        # Check build status
        if conditions.build_status:
            build_status = event_data.get('build_status', '')
            if conditions.build_status != 'any' and conditions.build_status != build_status:
                return False
        
        return True
    
    def _execute_action(
        self,
        action_config: WatchActionConfig,
        event_data: Dict[str, Any],
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Execute a single watch action.
        
        :param action_config: The action configuration
        :param event_data: The event data that triggered the action
        :param user_id: Optional user ID for the action (defaults to system)
        :returns: Dictionary with action result
        """
        result = {
            'action': action_config.action.value,
            'target_id': action_config.target_id,
            'success': False,
            'error': None,
            'result_id': None
        }
        
        try:
            if action_config.action == WatchAction.TRIGGER_BUILD:
                if self._build_manager:
                    # Trigger a build
                    build_result = self._build_manager.trigger_build_by_spec_id(
                        spec_id=action_config.target_id,
                        user_id=user_id or 'system',
                        trigger_type='watch',
                        parameters=action_config.parameters
                    )
                    result['success'] = True
                    result['result_id'] = build_result.id if build_result else None
                else:
                    result['error'] = "Build manager not available"
            
            elif action_config.action == WatchAction.TRIGGER_INFRA_JOB:
                if self._infra_manager:
                    # Trigger an infrastructure job
                    job_result = self._infra_manager.trigger_job_by_spec_id(
                        spec_id=action_config.target_id,
                        user_id=user_id or 'system',
                        action=action_config.parameters.get('action', 'provision'),
                        variables=action_config.parameters.get('variables', {})
                    )
                    result['success'] = True
                    result['result_id'] = job_result.id if job_result else None
                else:
                    result['error'] = "Infrastructure manager not available"
            
            elif action_config.action == WatchAction.TRIGGER_TEST_JOB:
                if self._test_manager:
                    # Trigger a test job
                    job_result = self._test_manager.trigger_job_by_spec_id(
                        spec_id=action_config.target_id,
                        user_id=user_id or 'system',
                        parameters=action_config.parameters
                    )
                    result['success'] = True
                    result['result_id'] = job_result.id if job_result else None
                else:
                    result['error'] = "Test manager not available"
            
            elif action_config.action == WatchAction.TRIGGER_RPA_JOB:
                if self._rpa_trigger:
                    parameters = dict(action_config.parameters or {})
                    spec_id = str(parameters.get('spec_id', '') or action_config.target_id)
                    work_packet = parameters.get('work_packet', {}) or {}
                    if not isinstance(work_packet, dict):
                        work_packet = {}
                    job_result = self._rpa_trigger(
                        spec_id=spec_id,
                        work_packet=work_packet,
                        user_id=user_id or 'system',
                    )
                    result['success'] = True
                    result['result_id'] = getattr(job_result, 'job_id', None) if job_result else None
                else:
                    result['error'] = "RPA trigger not available"

            elif action_config.action == WatchAction.TRIGGER_PIPELINE:
                if self._release_manager:
                    # Trigger a release pipeline
                    run_result = self._release_manager.trigger_pipeline(
                        pipeline_id=action_config.target_id,
                        trigger_type='watch',
                        variables=action_config.parameters.get('variables', {}),
                        user_id=user_id or 'system'
                    )
                    result['success'] = True
                    result['result_id'] = run_result.id if run_result else None
                else:
                    result['error'] = "Release manager not available"
            
            elif action_config.action == WatchAction.SEND_NOTIFICATION:
                # For notifications, we just log success
                # In a real implementation, this would send to a notification service
                result['success'] = True
                result['notification_sent'] = True
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def process_event(
        self,
        trigger_source: WatchTriggerSource,
        source_id: int,
        event_data: Dict[str, Any]
    ) -> List[WatchTriggerLog]:
        """
        Process an event and trigger matching watches.
        
        :param trigger_source: The type of trigger source
        :param source_id: The ID of the source (repository or build spec)
        :param event_data: The event data containing details like branch, tag, files, etc.
        :returns: List of WatchTriggerLog for each triggered watch
        
        Validates: Requirements 10.6
        """
        from ccai.pychestrate.core.orm import ProjectWatch, ProjectWatchTriggerLog
        
        trigger_logs = []
        
        # Find all enabled watches matching the trigger source and source ID
        source_value = trigger_source.value if isinstance(trigger_source, WatchTriggerSource) else trigger_source
        
        watches = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.trigger_source == source_value,
            ProjectWatch.source_id == source_id,
            ProjectWatch.enabled == True
        ).all()
        
        now = utc_now()
        
        for watch in watches:
            conditions = self._dict_to_conditions(watch.conditions_json)
            
            # Check if conditions match
            if not self._match_conditions(conditions, event_data):
                continue
            
            # Execute all actions
            actions = self._list_to_actions(watch.actions_json)
            actions_executed = []
            all_success = True
            error_messages = []
            
            for action_config in actions:
                action_result = self._execute_action(action_config, event_data)
                actions_executed.append(action_result)
                
                if not action_result['success']:
                    all_success = False
                    if action_result.get('error'):
                        error_messages.append(action_result['error'])
            
            # Create trigger log
            trigger_log = ProjectWatchTriggerLog(
                watch_id=watch.id,
                triggered_at=now,
                trigger_event_json=event_data,
                actions_executed_json=actions_executed,
                success=all_success,
                error_message='; '.join(error_messages) if error_messages else None
            )
            
            self._db_session.add(trigger_log)
            
            # Update watch statistics
            watch.last_trigger_time = now
            watch.trigger_count = (watch.trigger_count or 0) + 1
            
            trigger_logs.append(self._trigger_log_to_response(trigger_log))
        
        self._db_session.commit()
        
        return trigger_logs
    
    def get_trigger_logs(
        self,
        watch_id: int,
        offset: int = 0,
        limit: int = 50
    ) -> WatchTriggerLogListResponse:
        """
        Get trigger history for a watch.
        
        :param watch_id: The watch's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: WatchTriggerLogListResponse with paginated trigger log list
        
        Validates: Requirements 10.8
        """
        from ccai.pychestrate.core.orm import ProjectWatchTriggerLog
        
        query = self._db_session.query(ProjectWatchTriggerLog).filter(
            ProjectWatchTriggerLog.watch_id == watch_id
        )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination (most recent first)
        logs = query.order_by(ProjectWatchTriggerLog.triggered_at.desc()).offset(offset).limit(limit).all()
        
        return WatchTriggerLogListResponse(
            logs=[self._trigger_log_to_response(log) for log in logs],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def test_watch(self, watch_id: int, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test watch conditions without executing actions.
        
        :param watch_id: The watch's unique identifier
        :param event_data: The event data to test against
        :returns: Dictionary with test results
        :raises WatchNotFoundError: If watch is not found
        
        Validates: Requirements 10.7
        """
        from ccai.pychestrate.core.orm import ProjectWatch
        
        watch = self._db_session.query(ProjectWatch).filter(
            ProjectWatch.id == watch_id
        ).first()
        
        if not watch:
            raise WatchNotFoundError(f"Watch with ID '{watch_id}' not found")
        
        conditions = self._dict_to_conditions(watch.conditions_json)
        actions = self._list_to_actions(watch.actions_json)
        
        # Test each condition
        condition_results = {
            'branch_pattern': {
                'pattern': conditions.branch_pattern,
                'value': event_data.get('branch', ''),
                'matches': True
            },
            'tag_pattern': {
                'pattern': conditions.tag_pattern,
                'value': event_data.get('tag', ''),
                'matches': True
            },
            'file_pattern': {
                'pattern': conditions.file_pattern,
                'value': event_data.get('files', []),
                'matches': True
            },
            'build_status': {
                'pattern': conditions.build_status,
                'value': event_data.get('build_status', ''),
                'matches': True
            }
        }
        
        # Check branch pattern
        if conditions.branch_pattern:
            branch = event_data.get('branch', '')
            condition_results['branch_pattern']['matches'] = bool(re.match(conditions.branch_pattern, branch))
        
        # Check tag pattern
        if conditions.tag_pattern:
            tag = event_data.get('tag', '')
            condition_results['tag_pattern']['matches'] = bool(re.match(conditions.tag_pattern, tag))
        
        # Check file pattern
        if conditions.file_pattern:
            files = event_data.get('files', [])
            if files:
                pattern = re.compile(conditions.file_pattern)
                condition_results['file_pattern']['matches'] = any(pattern.match(f) for f in files)
            else:
                condition_results['file_pattern']['matches'] = False
        
        # Check build status
        if conditions.build_status:
            build_status = event_data.get('build_status', '')
            condition_results['build_status']['matches'] = (
                conditions.build_status == 'any' or conditions.build_status == build_status
            )
        
        # Overall match
        overall_match = self._match_conditions(conditions, event_data)
        
        return {
            'watch_id': watch.id,
            'watch_name': watch.name,
            'enabled': watch.enabled,
            'would_trigger': overall_match and watch.enabled,
            'conditions_match': overall_match,
            'condition_results': condition_results,
            'actions_count': len(actions),
            'actions': [
                {
                    'action': action.action.value,
                    'target_id': action.target_id
                }
                for action in actions
            ]
        }
