"""
.. module:: resource_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the ResourceManager class for resource CRUD operations, pool management, tag management, and metadata handling

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now


# =============================================================================
# Validation Constants
# =============================================================================

# Resource name validation: alphanumeric, underscore, hyphen, period
# Must be 1-128 characters
RESOURCE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}$')

# Tag name validation: alphanumeric, underscore, hyphen only
# Must be 1-64 characters
TAG_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,63}$')

# Pool name validation: alphanumeric, underscore, hyphen only (the rule the
# create form states); must start with alphanumeric, 1-128 characters
POOL_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,127}$')


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class ResourceCreateRequest:
    """Request dataclass for creating a new resource."""
    name: str
    resource_type: str
    pool_id: Optional[int] = None
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    capacity: int = 1
    sensitive_fields: List[str] = field(default_factory=list)


@dataclass
class ResourceUpdateRequest:
    """Request dataclass for updating an existing resource."""
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    capacity: Optional[int] = None
    health_status: Optional[str] = None
    sensitive_fields: Optional[List[str]] = None



@dataclass
class ResourceResponse:
    """Response dataclass for resource data."""
    id: int
    name: str
    resource_type: str
    pool_id: Optional[int]
    pool_name: Optional[str]
    description: str
    metadata: Dict[str, Any]
    tags: List[str]
    capacity: int
    current_allocations: int
    health_status: str
    created_at: datetime
    updated_at: datetime


@dataclass
class ResourceListResponse:
    """Response dataclass for paginated resource list."""
    resources: List[ResourceResponse]
    total: int
    offset: int
    limit: int


@dataclass
class ResourcePoolCreateRequest:
    """Request dataclass for creating a new resource pool."""
    name: str
    description: str = ""


@dataclass
class ResourcePoolResponse:
    """Response dataclass for resource pool data."""
    id: int
    name: str
    description: str
    is_default: bool
    resource_count: int
    created_at: datetime
    created_by: Optional[str]
    created_by_name: Optional[str] = None


@dataclass
class ResourcePoolListResponse:
    """Response dataclass for paginated pool list."""
    pools: List[ResourcePoolResponse]
    total: int
    offset: int
    limit: int


@dataclass
class TagResponse:
    """Response dataclass for tag data."""
    id: int
    name: str
    description: Optional[str]
    created_at: datetime


@dataclass
class TagListResponse:
    """Response dataclass for paginated tag list."""
    tags: List[TagResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Validation Errors
# =============================================================================

class ResourceValidationError(Exception):
    """Exception raised when resource validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "VALIDATION_ERROR"
        super().__init__(self.message)


class ResourceNotFoundError(Exception):
    """Exception raised when a resource is not found."""
    
    def __init__(self, message: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateResourceError(Exception):
    """Exception raised when attempting to create a resource with duplicate name in pool."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "RESOURCE_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class ResourceHasAllocationsError(Exception):
    """Exception raised when attempting to delete a resource with active allocations."""
    
    def __init__(self, message: str, error_code: str = "RESOURCE_HAS_ALLOCATIONS"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class PoolNotFoundError(Exception):
    """Exception raised when a pool is not found."""
    
    def __init__(self, message: str, error_code: str = "POOL_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class PoolHasResourcesError(Exception):
    """Exception raised when attempting to delete a pool with resources."""
    
    def __init__(self, message: str, error_code: str = "POOL_HAS_RESOURCES"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class TagNotFoundError(Exception):
    """Exception raised when a tag is not found."""
    
    def __init__(self, message: str, error_code: str = "TAG_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


# =============================================================================
# Supported Resource Types
# =============================================================================

SUPPORTED_RESOURCE_TYPES = {'device', 'ip_address', 'port', 'credential', 'generic'}


# =============================================================================
# Validation Functions
# =============================================================================

def validate_resource_name(name: str) -> bool:
    """
    Validate that a resource name contains only alphanumeric characters, underscores, hyphens, and periods.
    
    Requirements:
    - Must start with an alphanumeric character
    - Can contain alphanumeric characters, underscores, hyphens, and periods
    - Must be between 1 and 128 characters long
    
    :param name: The resource name to validate
    :returns: True if valid, False otherwise
    
    Validates: Requirements 1.7
    """
    if not name:
        return False
    
    if not RESOURCE_NAME_PATTERN.match(name):
        return False
    
    return True


def validate_tag_name(tag: str) -> bool:
    """
    Validate that a tag name contains only alphanumeric characters, underscores, and hyphens.
    
    Requirements:
    - Must start with an alphanumeric character
    - Can contain alphanumeric characters, underscores, and hyphens
    - Must be between 1 and 64 characters long
    
    :param tag: The tag name to validate
    :returns: True if valid, False otherwise
    
    Validates: Requirements 7.5
    """
    if not tag:
        return False
    
    if not TAG_NAME_PATTERN.match(tag):
        return False
    
    return True



# =============================================================================
# ResourceManager Class
# =============================================================================

class ResourceManager:
    """
    Manager class for resource CRUD operations, pool management, tag management, and metadata handling.
    
    This class handles all resource-related operations including:
    - Resource creation with validation
    - Resource retrieval by ID or name
    - Resource updates
    - Resource deletion with allocation check
    - Pool management (create, list, delete)
    - Tag management (add, remove)
    - Metadata management with history tracking
    
    Validates: Requirements 1.1-1.7, 2.1-2.5, 7.1-7.5, 8.1-8.5
    """
    
    # Mask value for sensitive fields
    SENSITIVE_MASK = "********"
    
    def __init__(self, db_session: DbSession, audit_logger=None):
        """
        Initialize the ResourceManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def validate_resource_name(self, name: str) -> bool:
        """
        Validate that a resource name contains only alphanumeric characters, underscores, hyphens, and periods.
        
        :param name: The resource name to validate
        :returns: True if valid, False otherwise
        
        Validates: Requirements 1.7
        """
        return validate_resource_name(name)
    
    def validate_tag_name(self, tag: str) -> bool:
        """
        Validate that a tag name contains only alphanumeric characters, underscores, and hyphens.
        
        :param tag: The tag name to validate
        :returns: True if valid, False otherwise
        
        Validates: Requirements 7.5
        """
        return validate_tag_name(tag)
    
    def _validate_resource_create_request(self, request: ResourceCreateRequest) -> None:
        """
        Validate a resource creation request.
        
        :param request: The resource creation request to validate
        :raises ResourceValidationError: If validation fails
        """
        if not self.validate_resource_name(request.name):
            raise ResourceValidationError(
                "Resource name must be 1-128 characters, start with alphanumeric, "
                "and contain only alphanumeric characters, underscores, hyphens, and periods",
                field="name",
                error_code="INVALID_RESOURCE_NAME"
            )
        
        if request.resource_type not in SUPPORTED_RESOURCE_TYPES:
            raise ResourceValidationError(
                f"Resource type must be one of: {', '.join(sorted(SUPPORTED_RESOURCE_TYPES))}",
                field="resource_type",
                error_code="INVALID_RESOURCE_TYPE"
            )
        
        if request.capacity < 1:
            raise ResourceValidationError(
                "Capacity must be at least 1",
                field="capacity",
                error_code="INVALID_CAPACITY"
            )
        
        # Validate tags
        for tag in request.tags:
            if not self.validate_tag_name(tag):
                raise ResourceValidationError(
                    f"Tag name '{tag}' is invalid. Tags must be 1-64 characters, start with alphanumeric, "
                    "and contain only alphanumeric characters, underscores, and hyphens",
                    field="tags",
                    error_code="INVALID_TAG_NAME"
                )
    
    # =========================================================================
    # Resource CRUD Operations
    # =========================================================================
    
    def create_resource(self, request: ResourceCreateRequest, user_id: str = None) -> ResourceResponse:
        """
        Create a new resource.
        
        :param request: The resource creation request containing resource data
        :param user_id: The ID of the user creating the resource
        :returns: ResourceResponse with the created resource data
        :raises ResourceValidationError: If validation fails
        :raises DuplicateResourceError: If resource name already exists in pool
        :raises PoolNotFoundError: If specified pool does not exist
        
        Validates: Requirements 1.1, 1.2, 1.7
        """
        from ccai.pychestrate.core.orm import Resource, ResourcePool, Tag, AllocationStatus
        
        # Validate the request
        self._validate_resource_create_request(request)
        
        # Determine the pool
        pool_id = request.pool_id
        if pool_id is None:
            # Use default pool
            default_pool = self._db_session.query(ResourcePool).filter(
                ResourcePool.is_default == True
            ).first()
            if default_pool:
                pool_id = default_pool.id
        else:
            # Verify pool exists
            pool = self._db_session.query(ResourcePool).filter(
                ResourcePool.id == pool_id
            ).first()
            if not pool:
                raise PoolNotFoundError(f"Pool with ID '{pool_id}' not found")
        
        # Check for duplicate name within pool
        existing_resource = self._db_session.query(Resource).filter(
            Resource.name == request.name,
            Resource.pool_id == pool_id
        ).first()
        
        if existing_resource:
            raise DuplicateResourceError(
                f"Resource with name '{request.name}' already exists in this pool",
                field="name"
            )
        
        # Create the resource
        now = utc_now()
        
        resource = Resource(
            name=request.name,
            resource_type=request.resource_type,
            pool_id=pool_id,
            description=request.description,
            metadata_json=request.metadata,
            sensitive_fields=request.sensitive_fields,
            capacity=request.capacity,
            health_status='online',
            created_at=now,
            updated_at=now,
            created_by_id=user_id
        )
        
        self._db_session.add(resource)
        self._db_session.flush()  # Get the resource ID
        
        # Handle tags
        if request.tags:
            for tag_name in request.tags:
                tag = self._db_session.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name, created_at=now)
                    self._db_session.add(tag)
                    self._db_session.flush()
                resource.tags.append(tag)
        
        self._db_session.commit()
        
        # Log the resource creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_created',
                user_id=str(user_id) if user_id else None,
                details={
                    "resource_id": resource.id,
                    "resource_name": resource.name,
                    "resource_type": resource.resource_type,
                    "pool_id": pool_id
                }
            )
        
        return self._resource_to_response(resource)
    
    def get_resource(self, resource_id: int) -> Optional[ResourceResponse]:
        """
        Retrieve a resource by ID.
        
        :param resource_id: The resource's unique identifier
        :returns: ResourceResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import Resource
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            return None
        
        return self._resource_to_response(resource)
    
    def get_resource_by_name(self, name: str, pool_id: int = None) -> Optional[ResourceResponse]:
        """
        Retrieve a resource by name within a pool.
        
        :param name: The resource name to search for
        :param pool_id: Optional pool ID to search within
        :returns: ResourceResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import Resource, ResourcePool
        
        query = self._db_session.query(Resource).filter(Resource.name == name)
        
        if pool_id is not None:
            query = query.filter(Resource.pool_id == pool_id)
        else:
            # Search in default pool if no pool specified
            default_pool = self._db_session.query(ResourcePool).filter(
                ResourcePool.is_default == True
            ).first()
            if default_pool:
                query = query.filter(Resource.pool_id == default_pool.id)
        
        resource = query.first()
        
        if not resource:
            return None
        
        return self._resource_to_response(resource)
    
    def update_resource(self, resource_id: int, request: ResourceUpdateRequest, user_id: str = None) -> ResourceResponse:
        """
        Update resource information.
        
        :param resource_id: The resource's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: ResourceResponse with the updated resource data
        :raises ResourceNotFoundError: If resource is not found
        :raises ResourceValidationError: If validation fails
        
        Validates: Requirements 1.3
        """
        from ccai.pychestrate.core.orm import Resource, Tag, ResourceMetadataHistory
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        # Update description if provided
        if request.description is not None:
            resource.description = request.description
        
        # Update capacity if provided
        if request.capacity is not None:
            if request.capacity < 1:
                raise ResourceValidationError(
                    "Capacity must be at least 1",
                    field="capacity",
                    error_code="INVALID_CAPACITY"
                )
            resource.capacity = request.capacity
        
        # Update health status if provided
        if request.health_status is not None:
            valid_statuses = {'online', 'offline', 'degraded', 'maintenance'}
            if request.health_status not in valid_statuses:
                raise ResourceValidationError(
                    f"Health status must be one of: {', '.join(sorted(valid_statuses))}",
                    field="health_status",
                    error_code="INVALID_HEALTH_STATUS"
                )
            resource.health_status = request.health_status
        
        # Update metadata if provided (with history tracking)
        if request.metadata is not None:
            # Record metadata history
            history = ResourceMetadataHistory(
                resource_id=resource.id,
                old_metadata_json=resource.metadata_json,
                new_metadata_json=request.metadata,
                changed_by_id=user_id,
                changed_at=utc_now()
            )
            self._db_session.add(history)
            resource.metadata_json = request.metadata
        
        # Update sensitive fields if provided
        if request.sensitive_fields is not None:
            resource.sensitive_fields = request.sensitive_fields
        
        # Update tags if provided
        if request.tags is not None:
            # Validate tags
            for tag_name in request.tags:
                if not self.validate_tag_name(tag_name):
                    raise ResourceValidationError(
                        f"Tag name '{tag_name}' is invalid",
                        field="tags",
                        error_code="INVALID_TAG_NAME"
                    )
            
            # Clear existing tags and add new ones
            resource.tags.clear()
            now = utc_now()
            for tag_name in request.tags:
                tag = self._db_session.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name, created_at=now)
                    self._db_session.add(tag)
                    self._db_session.flush()
                resource.tags.append(tag)
        
        resource.updated_at = utc_now()
        self._db_session.commit()
        
        # Log the resource update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_updated',
                user_id=str(user_id) if user_id else None,
                details={
                    "resource_id": resource.id,
                    "resource_name": resource.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._resource_to_response(resource)
    
    def delete_resource(self, resource_id: int, user_id: str = None) -> Dict[str, Any]:
        """
        Delete a resource together with the records that belong to it. Fails if
        active allocations exist (check them in, or force check-in, first).

        The resource's reservations (including upcoming ones, which cannot be
        honoured once the device is gone), its allocation history, its health
        check configuration and health history, its metadata history and its
        project assignments are removed with it. Those rows all reference the
        resource through NOT NULL foreign keys, so leaving them made every
        device with any history undeletable.

        :param resource_id: The resource's unique identifier
        :param user_id: The ID of the user deleting the resource
        :returns: Counts of the dependent records removed, keyed
                  ``reservations``, ``allocations``, ``health_check_configs``,
                  ``health_transitions`` and ``metadata_history``
        :raises ResourceNotFoundError: If resource is not found
        :raises ResourceHasAllocationsError: If resource has active allocations

        Validates: Requirements 1.4
        """
        from sqlalchemy import delete as sql_delete

        from ccai.pychestrate.core.orm import (
            Allocation,
            AllocationStatus,
            HealthCheckConfig,
            HealthTransitionLog,
            Reservation,
            Resource,
            ResourceMetadataHistory,
            project_resources,
        )

        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()

        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")

        # Check for active allocations
        active_allocations = self._db_session.query(Allocation).filter(
            Allocation.resource_id == resource_id,
            Allocation.status == AllocationStatus.ACTIVE.value
        ).count()

        if active_allocations > 0:
            raise ResourceHasAllocationsError(
                f"Cannot delete resource '{resource.name}' with {active_allocations} active allocation(s)"
            )

        resource_name = resource.name

        # Remove the dependent rows in an order the foreign keys allow:
        # reservations first (an activated reservation points at its
        # allocation), then the allocation history, then the health and
        # metadata records, then the project assignments.
        removed: Dict[str, Any] = {}
        removed["reservations"] = self._db_session.query(Reservation).filter(
            Reservation.resource_id == resource_id
        ).delete(synchronize_session=False)
        removed["allocations"] = self._db_session.query(Allocation).filter(
            Allocation.resource_id == resource_id
        ).delete(synchronize_session=False)
        removed["health_check_configs"] = self._db_session.query(HealthCheckConfig).filter(
            HealthCheckConfig.resource_id == resource_id
        ).delete(synchronize_session=False)
        removed["health_transitions"] = self._db_session.query(HealthTransitionLog).filter(
            HealthTransitionLog.resource_id == resource_id
        ).delete(synchronize_session=False)
        removed["metadata_history"] = self._db_session.query(ResourceMetadataHistory).filter(
            ResourceMetadataHistory.resource_id == resource_id
        ).delete(synchronize_session=False)
        self._db_session.execute(
            sql_delete(project_resources).where(project_resources.c.res_id == resource_id)
        )

        # Those rows are gone; reload the resource's collections so deleting
        # the resource does not try to detach children that no longer exist.
        self._db_session.expire(resource, [
            'allocations', 'reservations', 'health_check_config',
            'health_transitions', 'metadata_history',
        ])

        # Delete the resource (its tag links go with it)
        self._db_session.delete(resource)
        self._db_session.commit()

        # Log the resource deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_deleted',
                user_id=str(user_id) if user_id else None,
                details={
                    "resource_id": resource_id,
                    "resource_name": resource_name,
                    "removed_records": {key: value for key, value in removed.items() if isinstance(value, int)}
                }
            )

        return removed
    
    def list_resources(
        self,
        pool_id: int = None,
        resource_type: str = None,
        tags: List[str] = None,
        health_status: str = None,
        available_only: bool = False,
        offset: int = 0,
        limit: int = 50,
        search: str = None,
        availability: str = None,
        order_by: str = "id"
    ) -> ResourceListResponse:
        """
        List resources with filtering and pagination.

        :param pool_id: Optional pool ID to filter by
        :param resource_type: Optional resource type to filter by
        :param tags: Optional list of tags to filter by (resources must have all tags)
        :param health_status: Optional health status to filter by
        :param available_only: Same as ``availability="available"``
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :param search: Optional substring to match against resource name,
                       description or metadata (so an OS version or a
                       serial number finds the device); a resource that
                       marks metadata keys as sensitive is matched by name
                       and description only
        :param availability: ``"available"`` for resources that can be
                             checked out now (online or degraded, with
                             capacity left) or ``"in_use"`` for resources
                             with every slot taken. Applied before paging,
                             so the total and the pages are right.
        :param order_by: ``"id"`` (the default, oldest first) or ``"name"``
                         (alphabetical, case-insensitive). Either way the
                         order is total, so pages never repeat or skip a
                         resource.
        :returns: ResourceListResponse with paginated resource list

        Validates: Requirements 1.5
        """
        from sqlalchemy import String, and_, cast, func, or_

        from ccai.pychestrate.core.orm import Allocation, AllocationStatus, Resource, Tag

        query = self._db_session.query(Resource)

        # Apply pool filter
        if pool_id is not None:
            query = query.filter(Resource.pool_id == pool_id)

        # Apply resource type filter
        if resource_type is not None:
            query = query.filter(Resource.resource_type == resource_type)

        # Apply health status filter
        if health_status is not None:
            query = query.filter(Resource.health_status == health_status)

        # Apply search filter (case-insensitive substring on name, description
        # or the metadata's text)
        if search:
            like_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Resource.name.ilike(like_pattern),
                    Resource.description.ilike(like_pattern),
                    # A resource that marks metadata keys as sensitive is
                    # found by name and description only: matching its
                    # metadata would let a search probe values the pages
                    # mask.
                    and_(
                        cast(Resource.sensitive_fields, String).in_(("[]", "null")),
                        cast(Resource.metadata_json, String).ilike(like_pattern)
                    )
                )
            )

        # Apply availability filter in the query, so paging stays right
        if available_only and availability is None:
            availability = "available"
        if availability in ("available", "in_use"):
            active_count = (
                self._db_session.query(func.count(Allocation.id))
                .filter(
                    Allocation.resource_id == Resource.id,
                    Allocation.status == AllocationStatus.ACTIVE.value
                )
                .correlate(Resource)
                .scalar_subquery()
            )
            if availability == "available":
                query = query.filter(
                    Resource.health_status.in_(("online", "degraded")),
                    active_count < Resource.capacity
                )
            else:
                query = query.filter(active_count >= Resource.capacity)
        
        # Apply tag filter (resources must have all specified tags)
        if tags:
            for tag_name in tags:
                tag = self._db_session.query(Tag).filter(Tag.name == tag_name).first()
                if tag:
                    query = query.filter(Resource.tags.contains(tag))
                else:
                    # Tag doesn't exist, no resources can match
                    return ResourceListResponse(
                        resources=[],
                        total=0,
                        offset=offset,
                        limit=limit
                    )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination, in an order that cannot repeat or skip a row
        # between pages
        if order_by == "name":
            query = query.order_by(func.lower(Resource.name), Resource.id)
        else:
            query = query.order_by(Resource.id)
        resources = query.offset(offset).limit(limit).all()
        
        return ResourceListResponse(
            resources=[self._resource_to_response(resource) for resource in resources],
            total=total,
            offset=offset,
            limit=limit
        )

    def count_resources_by_health_status(self) -> Dict[str, int]:
        """
        Count resources grouped by health status using a single aggregate query.

        :returns: Dictionary mapping health status value to resource count.
                  The four documented statuses ('online', 'offline', 'degraded',
                  'maintenance') are always present (zero when absent); any other
                  status values found in the database are included as-is.
        """
        from sqlalchemy import func

        from ccai.pychestrate.core.orm import Resource

        counts: Dict[str, int] = {
            'online': 0,
            'offline': 0,
            'degraded': 0,
            'maintenance': 0
        }

        rows = self._db_session.query(
            Resource.health_status, func.count(Resource.id)
        ).group_by(Resource.health_status).all()

        for status_value, status_count in rows:
            if status_value is None:
                continue
            counts[status_value] = status_count

        return counts

    # =========================================================================
    # Pool Management
    # =========================================================================
    
    def create_pool(self, request: ResourcePoolCreateRequest, user_id: str = None) -> ResourcePoolResponse:
        """
        Create a new resource pool.
        
        :param request: The pool creation request containing pool data
        :param user_id: The ID of the user creating the pool
        :returns: ResourcePoolResponse with the created pool data
        :raises ResourceValidationError: If validation fails
        :raises DuplicateResourceError: If pool name already exists
        
        Validates: Requirements 2.1
        """
        from ccai.pychestrate.core.orm import ResourcePool
        
        # Validate pool name
        if not request.name or len(request.name.strip()) == 0:
            raise ResourceValidationError(
                "Pool name is required",
                field="name",
                error_code="INVALID_POOL_NAME"
            )

        if not POOL_NAME_PATTERN.match(request.name):
            raise ResourceValidationError(
                "Pool name must be 1-128 characters, start with a letter or digit, "
                "and contain only letters, digits, underscores and hyphens",
                field="name",
                error_code="INVALID_POOL_NAME"
            )

        # Check for duplicate pool name
        existing_pool = self._db_session.query(ResourcePool).filter(
            ResourcePool.name == request.name
        ).first()
        
        if existing_pool:
            raise DuplicateResourceError(
                f"Pool with name '{request.name}' already exists",
                field="name",
                error_code="POOL_NAME_EXISTS"
            )
        
        # Create the pool
        now = utc_now()
        
        pool = ResourcePool(
            name=request.name,
            description=request.description,
            is_default=False,
            created_at=now,
            created_by_id=user_id
        )
        
        self._db_session.add(pool)
        self._db_session.commit()
        
        # Log the pool creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pool_created',
                user_id=str(user_id) if user_id else None,
                details={
                    "pool_id": pool.id,
                    "pool_name": pool.name
                }
            )
        
        return self._pool_to_response(pool)
    
    def get_pool(self, pool_id: int) -> Optional[ResourcePoolResponse]:
        """
        Get a pool by ID.
        
        :param pool_id: The pool's unique identifier
        :returns: ResourcePoolResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import ResourcePool
        
        pool = self._db_session.query(ResourcePool).filter(ResourcePool.id == pool_id).first()
        
        if not pool:
            return None
        
        return self._pool_to_response(pool, resolve_creator=True)
    
    def list_pools(self, user_id: str = None, offset: int = 0, limit: int = 50) -> ResourcePoolListResponse:
        """
        List pools the user has access to.
        
        :param user_id: The user's ID (for permission filtering - not implemented yet)
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: ResourcePoolListResponse with paginated pool list
        """
        from ccai.pychestrate.core.orm import ResourcePool
        
        query = self._db_session.query(ResourcePool)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        pools = query.offset(offset).limit(limit).all()
        
        return ResourcePoolListResponse(
            pools=[self._pool_to_response(pool) for pool in pools],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def delete_pool(self, pool_id: int, user_id: str = None) -> None:
        """
        Delete a pool. Fails if resources exist in pool.
        
        :param pool_id: The pool's unique identifier
        :param user_id: The ID of the user deleting the pool
        :raises PoolNotFoundError: If pool is not found
        :raises PoolHasResourcesError: If pool contains resources
        
        Validates: Requirements 2.5
        """
        from ccai.pychestrate.core.orm import ResourcePool, Resource
        
        pool = self._db_session.query(ResourcePool).filter(ResourcePool.id == pool_id).first()
        
        if not pool:
            raise PoolNotFoundError(f"Pool with ID '{pool_id}' not found")
        
        # Check for resources in pool
        resource_count = self._db_session.query(Resource).filter(
            Resource.pool_id == pool_id
        ).count()
        
        if resource_count > 0:
            raise PoolHasResourcesError(
                f"Cannot delete pool '{pool.name}' with {resource_count} resource(s)"
            )
        
        pool_name = pool.name
        
        # Delete the pool
        self._db_session.delete(pool)
        self._db_session.commit()
        
        # Log the pool deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='pool_deleted',
                user_id=str(user_id) if user_id else None,
                details={
                    "pool_id": pool_id,
                    "pool_name": pool_name
                }
            )
    
    def move_pool_resources(self, source_pool_id: int, target_pool_id: int, user_id: str = None) -> int:
        """
        Move every resource of one pool into another, so the first can be
        deleted without deleting its devices.

        Nothing moves unless every resource can: a resource whose name
        already exists in the target pool stops the whole move.

        :param source_pool_id: The pool to empty
        :param target_pool_id: The pool that takes its resources
        :param user_id: The ID of the user moving them
        :returns: How many resources moved
        :raises PoolNotFoundError: If either pool is not found
        :raises ResourceValidationError: If the two pools are the same
        :raises DuplicateResourceError: If a name is already in the target
        """
        from ccai.pychestrate.core.orm import Resource, ResourcePool

        if source_pool_id == target_pool_id:
            raise ResourceValidationError(
                "Choose a different pool to move the resources to",
                field="target_pool_id",
                error_code="SAME_POOL"
            )
        source = self._db_session.query(ResourcePool).filter(ResourcePool.id == source_pool_id).first()
        if not source:
            raise PoolNotFoundError(f"Pool with ID '{source_pool_id}' not found")
        target = self._db_session.query(ResourcePool).filter(ResourcePool.id == target_pool_id).first()
        if not target:
            raise PoolNotFoundError(f"Pool with ID '{target_pool_id}' not found")

        moving = self._db_session.query(Resource).filter(Resource.pool_id == source_pool_id).all()
        taken = {
            row.name for row in self._db_session.query(Resource).filter(Resource.pool_id == target_pool_id).all()
        }
        clashes = sorted(resource.name for resource in moving if resource.name in taken)
        if len(clashes) > 0:
            raise DuplicateResourceError(
                f"Pool '{target.name}' already has a resource named {', '.join(repr(name) for name in clashes)}",
                field="target_pool_id"
            )

        now = utc_now()
        for resource in moving:
            resource.pool_id = target_pool_id
            resource.updated_at = now
        self._db_session.commit()

        if self._audit_logger and len(moving) > 0:
            self._audit_logger.log_event(
                event_type='pool_resources_moved',
                user_id=str(user_id) if user_id else None,
                details={
                    "source_pool_id": source_pool_id,
                    "target_pool_id": target_pool_id,
                    "resource_count": len(moving)
                }
            )
        return len(moving)

    def assign_resource_to_pool(self, resource_id: int, pool_id: int, user_id: str = None) -> None:
        """
        Assign a resource to a pool.
        
        :param resource_id: The resource's unique identifier
        :param pool_id: The pool's unique identifier
        :param user_id: The ID of the user making the assignment
        :raises ResourceNotFoundError: If resource is not found
        :raises PoolNotFoundError: If pool is not found
        :raises DuplicateResourceError: If resource name already exists in target pool
        
        Validates: Requirements 2.2
        """
        from ccai.pychestrate.core.orm import Resource, ResourcePool
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        pool = self._db_session.query(ResourcePool).filter(ResourcePool.id == pool_id).first()
        
        if not pool:
            raise PoolNotFoundError(f"Pool with ID '{pool_id}' not found")
        
        # Check for duplicate name in target pool
        existing_resource = self._db_session.query(Resource).filter(
            Resource.name == resource.name,
            Resource.pool_id == pool_id,
            Resource.id != resource_id
        ).first()
        
        if existing_resource:
            raise DuplicateResourceError(
                f"Resource with name '{resource.name}' already exists in pool '{pool.name}'",
                field="name"
            )
        
        old_pool_id = resource.pool_id
        resource.pool_id = pool_id
        resource.updated_at = utc_now()
        self._db_session.commit()
        
        # Log the pool assignment event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_pool_assigned',
                user_id=str(user_id) if user_id else None,
                details={
                    "resource_id": resource_id,
                    "resource_name": resource.name,
                    "old_pool_id": old_pool_id,
                    "new_pool_id": pool_id,
                    "new_pool_name": pool.name
                }
            )
    
    def remove_resource_from_pool(self, resource_id: int, user_id: str = None) -> None:
        """
        Remove a resource from its pool (assign to default pool).
        
        :param resource_id: The resource's unique identifier
        :param user_id: The ID of the user making the change
        :raises ResourceNotFoundError: If resource is not found
        
        Validates: Requirements 2.3
        """
        from ccai.pychestrate.core.orm import Resource, ResourcePool
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        old_pool_id = resource.pool_id
        
        # Find default pool
        default_pool = self._db_session.query(ResourcePool).filter(
            ResourcePool.is_default == True
        ).first()
        
        if default_pool:
            resource.pool_id = default_pool.id
        else:
            resource.pool_id = None
        
        resource.updated_at = utc_now()
        self._db_session.commit()
        
        # Log the pool removal event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_pool_removed',
                user_id=str(user_id) if user_id else None,
                details={
                    "resource_id": resource_id,
                    "resource_name": resource.name,
                    "old_pool_id": old_pool_id,
                    "new_pool_id": default_pool.id if default_pool else None
                }
            )
    
    # =========================================================================
    # Tag Management
    # =========================================================================
    
    def add_tags(self, resource_id: int, tags: List[str], user_id: str = None) -> None:
        """
        Add tags to a resource.
        
        :param resource_id: The resource's unique identifier
        :param tags: List of tag names to add
        :param user_id: The ID of the user adding the tags
        :raises ResourceNotFoundError: If resource is not found
        :raises ResourceValidationError: If tag name is invalid
        
        Validates: Requirements 7.1
        """
        from ccai.pychestrate.core.orm import Resource, Tag
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        now = utc_now()
        added_tags = []
        
        for tag_name in tags:
            if not self.validate_tag_name(tag_name):
                raise ResourceValidationError(
                    f"Tag name '{tag_name}' is invalid",
                    field="tags",
                    error_code="INVALID_TAG_NAME"
                )
            
            # Get or create tag
            tag = self._db_session.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                tag = Tag(name=tag_name, created_at=now)
                self._db_session.add(tag)
                self._db_session.flush()
            
            # Add tag to resource if not already present
            if tag not in resource.tags:
                resource.tags.append(tag)
                added_tags.append(tag_name)
        
        resource.updated_at = now
        self._db_session.commit()
        
        # Log the tag addition event
        if self._audit_logger and added_tags:
            self._audit_logger.log_event(
                event_type='resource_tags_added',
                user_id=str(user_id) if user_id else None,
                details={
                    "resource_id": resource_id,
                    "resource_name": resource.name,
                    "tags_added": added_tags
                }
            )
    
    def remove_tags(self, resource_id: int, tags: List[str], user_id: str = None) -> None:
        """
        Remove tags from a resource.
        
        :param resource_id: The resource's unique identifier
        :param tags: List of tag names to remove
        :param user_id: The ID of the user removing the tags
        :raises ResourceNotFoundError: If resource is not found
        
        Validates: Requirements 7.1
        """
        from ccai.pychestrate.core.orm import Resource, Tag
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        removed_tags = []
        
        for tag_name in tags:
            tag = self._db_session.query(Tag).filter(Tag.name == tag_name).first()
            if tag and tag in resource.tags:
                resource.tags.remove(tag)
                removed_tags.append(tag_name)
        
        resource.updated_at = utc_now()
        self._db_session.commit()
        
        # Log the tag removal event
        if self._audit_logger and removed_tags:
            self._audit_logger.log_event(
                event_type='resource_tags_removed',
                user_id=str(user_id) if user_id else None,
                details={
                    "resource_id": resource_id,
                    "resource_name": resource.name,
                    "tags_removed": removed_tags
                }
            )
    
    def create_tag(self, name: str, description: str = None, user_id: str = None) -> TagResponse:
        """
        Create a tag that no resource carries yet.

        Tags used to come into being only when they were first assigned to
        a resource, which left the Tags page and the resource forms with no
        way to make one.

        :param name: The tag name (letters, digits, ``_`` and ``-``,
                     starting with a letter or digit, at most 64)
        :param description: What the tag is for (optional, at most 255)
        :param user_id: The ID of the user creating the tag
        :returns: TagResponse for the new tag
        :raises ResourceValidationError: If the name or description is
                                         invalid, or the name is taken
        """
        from ccai.pychestrate.core.orm import Tag

        tag_name = (name or "").strip()
        if not self.validate_tag_name(tag_name):
            raise ResourceValidationError(
                f"Tag name '{tag_name}' is invalid",
                field="name",
                error_code="INVALID_TAG_NAME"
            )
        tag_description = (description or "").strip() or None
        if tag_description is not None and len(tag_description) > 255:
            raise ResourceValidationError(
                "A tag description may be at most 255 characters",
                field="description",
                error_code="TAG_DESCRIPTION_TOO_LONG"
            )
        existing = self._db_session.query(Tag).filter(Tag.name == tag_name).first()
        if existing:
            raise ResourceValidationError(
                f"A tag named '{tag_name}' already exists",
                field="name",
                error_code="TAG_NAME_EXISTS"
            )

        tag = Tag(name=tag_name, description=tag_description, created_at=utc_now())
        self._db_session.add(tag)
        self._db_session.commit()

        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_tag_created',
                user_id=str(user_id) if user_id else None,
                details={"tag_id": tag.id, "tag_name": tag_name}
            )
        return self._tag_to_response(tag)

    def get_tag(self, tag_id: int) -> Optional[TagResponse]:
        """
        Get one tag.

        :param tag_id: The tag's unique identifier
        :returns: TagResponse, or ``None`` when there is no such tag
        """
        from ccai.pychestrate.core.orm import Tag

        tag = self._db_session.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            return None
        return self._tag_to_response(tag)

    def update_tag(self, tag_id: int, name: str = None, description: str = None, user_id: str = None) -> TagResponse:
        """
        Rename a tag and/or change its description. Renaming keeps every
        resource that carries it.

        :param tag_id: The tag's unique identifier
        :param name: The new name, or ``None`` to keep it
        :param description: The new description, or ``None`` to keep it
                            (an empty string clears it)
        :param user_id: The ID of the user changing the tag
        :returns: TagResponse for the updated tag
        :raises ResourceNotFoundError: If the tag does not exist
        :raises ResourceValidationError: If the name or description is
                                         invalid, or the name is taken
        """
        from ccai.pychestrate.core.orm import Tag

        tag = self._db_session.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise ResourceNotFoundError(
                f"Tag with ID '{tag_id}' not found", error_code="TAG_NOT_FOUND"
            )
        if name is not None:
            new_name = name.strip()
            if not self.validate_tag_name(new_name):
                raise ResourceValidationError(
                    f"Tag name '{new_name}' is invalid",
                    field="name",
                    error_code="INVALID_TAG_NAME"
                )
            other = self._db_session.query(Tag).filter(Tag.name == new_name, Tag.id != tag_id).first()
            if other:
                raise ResourceValidationError(
                    f"A tag named '{new_name}' already exists",
                    field="name",
                    error_code="TAG_NAME_EXISTS"
                )
            tag.name = new_name
        if description is not None:
            new_description = description.strip() or None
            if new_description is not None and len(new_description) > 255:
                raise ResourceValidationError(
                    "A tag description may be at most 255 characters",
                    field="description",
                    error_code="TAG_DESCRIPTION_TOO_LONG"
                )
            tag.description = new_description
        self._db_session.commit()

        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_tag_updated',
                user_id=str(user_id) if user_id else None,
                details={"tag_id": tag.id, "tag_name": tag.name}
            )
        return self._tag_to_response(tag)

    def delete_tag(self, tag_id: int, user_id: str = None) -> int:
        """
        Delete a tag. It is taken off every resource that carries it;
        the resources stay.

        :param tag_id: The tag's unique identifier
        :param user_id: The ID of the user deleting the tag
        :returns: How many resources carried it
        :raises ResourceNotFoundError: If the tag does not exist
        """
        from ccai.pychestrate.core.orm import Tag

        tag = self._db_session.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise ResourceNotFoundError(
                f"Tag with ID '{tag_id}' not found", error_code="TAG_NOT_FOUND"
            )
        carried_by = len(tag.resources)
        tag_name = tag.name
        for resource in list(tag.resources):
            resource.tags.remove(tag)
        self._db_session.delete(tag)
        self._db_session.commit()

        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_tag_deleted',
                user_id=str(user_id) if user_id else None,
                details={"tag_id": tag_id, "tag_name": tag_name, "resources": carried_by}
            )
        return carried_by

    def list_tags(self, offset: int = 0, limit: int = 50, search: str = None) -> TagListResponse:
        """
        List all tags.

        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :param search: Optional substring to match against the tag name
        :returns: TagListResponse with paginated tag list
        """
        from ccai.pychestrate.core.orm import Tag

        query = self._db_session.query(Tag)

        # Apply search filter (case-insensitive substring on name)
        if search:
            query = query.filter(Tag.name.ilike(f"%{search}%"))

        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        tags = query.offset(offset).limit(limit).all()
        
        return TagListResponse(
            tags=[self._tag_to_response(tag) for tag in tags],
            total=total,
            offset=offset,
            limit=limit
        )
    
    # =========================================================================
    # Metadata Management
    # =========================================================================
    
    def update_metadata(self, resource_id: int, metadata: Dict[str, Any], user_id: str = None) -> None:
        """
        Update resource metadata with history tracking.
        
        :param resource_id: The resource's unique identifier
        :param metadata: The new metadata dictionary
        :param user_id: The ID of the user making the update
        :raises ResourceNotFoundError: If resource is not found
        
        Validates: Requirements 8.1, 8.4
        """
        from ccai.pychestrate.core.orm import Resource, ResourceMetadataHistory
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        # Record metadata history
        now = utc_now()
        old_metadata = dict(resource.metadata_json) if resource.metadata_json else {}
        
        history = ResourceMetadataHistory(
            resource_id=resource.id,
            old_metadata_json=resource.metadata_json,
            new_metadata_json=metadata,
            changed_by_id=user_id,
            changed_at=now
        )
        self._db_session.add(history)
        
        resource.metadata_json = metadata
        resource.updated_at = now
        self._db_session.commit()
        
        # Log the metadata update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_metadata_updated',
                user_id=str(user_id) if user_id else None,
                details={
                    "resource_id": resource_id,
                    "resource_name": resource.name,
                    "changed_keys": list(set(list(old_metadata.keys()) + list(metadata.keys())))
                }
            )
    
    def get_metadata(self, resource_id: int, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Get resource metadata, optionally including sensitive fields.
        
        :param resource_id: The resource's unique identifier
        :param include_sensitive: If True, include sensitive field values; otherwise mask them
        :returns: Metadata dictionary with sensitive fields optionally masked
        :raises ResourceNotFoundError: If resource is not found
        
        Validates: Requirements 8.1, 8.5
        """
        from ccai.pychestrate.core.orm import Resource
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        metadata = dict(resource.metadata_json) if resource.metadata_json else {}
        
        if not include_sensitive and resource.sensitive_fields:
            for field_name in resource.sensitive_fields:
                if field_name in metadata:
                    metadata[field_name] = self.SENSITIVE_MASK
        
        return metadata
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def get_current_holders(self, resource_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
        """
        Who holds each of the given resources now.

        :param resource_ids: The resources to look up
        :returns: ``{resource id: [{"username", "user_id", "mode",
                  "job_id", "checkout_time", "expected_checkin"}, ...]}``
                  for the resources
                  that have an active check-out, longest-held first
        """
        from ccai.pychestrate.core.orm import Allocation, AllocationStatus, User

        rtnval: Dict[int, List[Dict[str, Any]]] = {}
        if len(resource_ids) == 0:
            return rtnval
        rows = (
            self._db_session.query(Allocation, User)
            .outerjoin(User, User.id == Allocation.user_id)
            .filter(
                Allocation.resource_id.in_(list(resource_ids)),
                Allocation.status == AllocationStatus.ACTIVE.value
            )
            .order_by(Allocation.checkout_time.asc())
            .all()
        )
        for allocation, holder in rows:
            rtnval.setdefault(allocation.resource_id, []).append({
                "username": holder.login if holder else None,
                "user_id": str(allocation.user_id),
                "mode": allocation.mode,
                "job_id": allocation.job_id,
                "checkout_time": allocation.checkout_time,
                "expected_checkin": allocation.expected_checkin,
            })
        return rtnval

    def _get_current_allocations(self, resource) -> int:
        """
        Get the count of current active allocations for a resource.
        
        :param resource: The Resource ORM object
        :returns: Count of active allocations
        """
        from ccai.pychestrate.core.orm import Allocation, AllocationStatus
        
        return self._db_session.query(Allocation).filter(
            Allocation.resource_id == resource.id,
            Allocation.status == AllocationStatus.ACTIVE.value
        ).count()
    
    def _resource_to_response(self, resource) -> ResourceResponse:
        """
        Convert a Resource ORM object to a ResourceResponse dataclass.
        
        :param resource: The Resource ORM object
        :returns: ResourceResponse dataclass
        """
        pool_name = resource.pool.name if resource.pool else None
        tag_names = [tag.name for tag in resource.tags] if resource.tags else []
        current_allocations = self._get_current_allocations(resource)
        
        return ResourceResponse(
            id=resource.id,
            name=resource.name,
            resource_type=resource.resource_type,
            pool_id=resource.pool_id,
            pool_name=pool_name,
            description=resource.description or "",
            metadata=resource.metadata_json or {},
            tags=tag_names,
            capacity=resource.capacity,
            current_allocations=current_allocations,
            health_status=resource.health_status,
            created_at=resource.created_at,
            updated_at=resource.updated_at
        )
    
    def _pool_to_response(self, pool, resolve_creator: bool = False) -> ResourcePoolResponse:
        """
        Convert a ResourcePool ORM object to a ResourcePoolResponse dataclass.
        
        :param pool: The ResourcePool ORM object
        :param resolve_creator: Look up the creator's login for ``created_by_name``
            (one query, so only a single pool's page asks for it)
        :returns: ResourcePoolResponse dataclass
        """
        resource_count = len(pool.resources) if pool.resources else 0
        created_by = str(pool.created_by_id) if pool.created_by_id else None
        created_by_name = None
        if resolve_creator and pool.created_by_id:
            from ccai.pychestrate.core.orm import User

            creator = self._db_session.query(User).filter(User.id == pool.created_by_id).first()
            created_by_name = creator.login if creator else None
        
        return ResourcePoolResponse(
            id=pool.id,
            name=pool.name,
            description=pool.description or "",
            is_default=pool.is_default,
            resource_count=resource_count,
            created_at=pool.created_at,
            created_by=created_by,
            created_by_name=created_by_name
        )
    
    def _tag_to_response(self, tag) -> TagResponse:
        """
        Convert a Tag ORM object to a TagResponse dataclass.
        
        :param tag: The Tag ORM object
        :returns: TagResponse dataclass
        """
        return TagResponse(
            id=tag.id,
            name=tag.name,
            description=tag.description,
            created_at=tag.created_at
        )
