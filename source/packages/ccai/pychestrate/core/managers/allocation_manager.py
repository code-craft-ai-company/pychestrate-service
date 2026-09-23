"""
.. module:: allocation_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the AllocationManager class for resource checkout, checkin, reservations, and concurrency control

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import ensure_utc, utc_now


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class CheckoutRequest:
    """Request dataclass for resource checkout."""
    resource_id: Optional[int] = None
    resource_name: Optional[str] = None
    pool_id: Optional[int] = None
    tags: Optional[List[str]] = None
    job_id: Optional[str] = None
    mode: str = "exclusive"
    timeout_minutes: Optional[int] = None
    reason: str = ""


@dataclass
class AllocationResponse:
    """Response dataclass for allocation data."""
    id: int
    resource_id: int
    resource_name: str
    resource_type: str
    user_id: str
    username: Optional[str]
    job_id: Optional[str]
    mode: str
    status: str
    checkout_time: datetime
    expected_checkin: Optional[datetime]
    actual_checkin: Optional[datetime]
    duration_minutes: Optional[int]
    metadata: Dict[str, Any]


@dataclass
class AllocationListResponse:
    """Response dataclass for paginated allocation list."""
    allocations: List[AllocationResponse]
    total: int
    offset: int
    limit: int


@dataclass
class ReservationRequest:
    """Request dataclass for resource reservation."""
    resource_id: int
    job_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    mode: str = "exclusive"
    reason: str = ""


@dataclass
class ReservationResponse:
    """Response dataclass for reservation data."""
    id: int
    resource_id: int
    resource_name: str
    user_id: str
    username: Optional[str]
    job_id: Optional[str]
    start_time: datetime
    end_time: datetime
    mode: str
    status: str
    created_at: datetime


@dataclass
class ReservationListResponse:
    """Response dataclass for paginated reservation list."""
    reservations: List[ReservationResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Exceptions
# =============================================================================

class AllocationError(Exception):
    """Base exception for allocation errors."""
    
    def __init__(self, message: str, error_code: str = "ALLOCATION_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ResourceUnavailableError(AllocationError):
    """Exception raised when a resource is not available for checkout."""
    
    def __init__(self, message: str, current_allocation: Optional[AllocationResponse] = None,
                 error_code: str = "RESOURCE_UNAVAILABLE"):
        self.current_allocation = current_allocation
        super().__init__(message, error_code)


class ResourceOfflineError(AllocationError):
    """Exception raised when a resource is offline or in maintenance."""
    
    def __init__(self, message: str, health_status: str = None,
                 error_code: str = "RESOURCE_OFFLINE"):
        self.health_status = health_status
        super().__init__(message, error_code)


class CapacityExceededError(AllocationError):
    """Exception raised when a shared resource has reached capacity limit."""
    
    def __init__(self, message: str, capacity: int = None, current_allocations: int = None,
                 error_code: str = "CAPACITY_EXCEEDED"):
        self.capacity = capacity
        self.current_allocations = current_allocations
        super().__init__(message, error_code)


class AllocationNotFoundError(AllocationError):
    """Exception raised when an allocation is not found."""
    
    def __init__(self, message: str, error_code: str = "ALLOCATION_NOT_FOUND"):
        super().__init__(message, error_code)


class NotAllocationOwnerError(AllocationError):
    """Exception raised when user is not the owner of an allocation."""
    
    def __init__(self, message: str, error_code: str = "NOT_ALLOCATION_OWNER"):
        super().__init__(message, error_code)


class ReservationConflictError(AllocationError):
    """Exception raised when a reservation conflicts with existing reservations."""
    
    def __init__(self, message: str, conflicting_reservations: List[ReservationResponse] = None,
                 error_code: str = "RESERVATION_CONFLICT"):
        self.conflicting_reservations = conflicting_reservations or []
        super().__init__(message, error_code)


class ReservationNotFoundError(AllocationError):
    """Exception raised when a reservation is not found."""
    
    def __init__(self, message: str, error_code: str = "RESERVATION_NOT_FOUND"):
        super().__init__(message, error_code)


class InvalidTimeWindowError(AllocationError):
    """Exception raised when a reservation time window is invalid."""
    
    def __init__(self, message: str, error_code: str = "INVALID_TIME_WINDOW"):
        super().__init__(message, error_code)


class CheckoutPermissionDeniedError(AllocationError):
    """Exception raised when user lacks checkout permission for pool."""
    
    def __init__(self, message: str, error_code: str = "CHECKOUT_PERMISSION_DENIED"):
        super().__init__(message, error_code)


class LockTimeoutError(AllocationError):
    """Exception raised when lock acquisition times out."""
    
    def __init__(self, message: str, error_code: str = "LOCK_TIMEOUT"):
        super().__init__(message, error_code)


class ConcurrentModificationError(AllocationError):
    """Exception raised when resource was modified by another request."""
    
    def __init__(self, message: str, error_code: str = "CONCURRENT_MODIFICATION"):
        super().__init__(message, error_code)


class ResourceNotFoundError(AllocationError):
    """Exception raised when a resource is not found."""
    
    def __init__(self, message: str, error_code: str = "RESOURCE_NOT_FOUND"):
        super().__init__(message, error_code)


class NoMatchingResourceError(AllocationError):
    """Exception raised when no resource matches the checkout criteria."""
    
    def __init__(self, message: str, error_code: str = "NO_MATCHING_RESOURCE"):
        super().__init__(message, error_code)


# =============================================================================
# AllocationManager Class
# =============================================================================

class AllocationManager:
    """
    Manager class for resource checkout, checkin, reservations, and concurrency control.
    
    This class handles all allocation-related operations including:
    - Resource checkout with exclusive and shared modes
    - Resource checkin with ownership validation
    - Force checkin for administrators
    - Reservation management
    - Timeout handling
    - Tag-based resource selection
    - Concurrency control with database-level locking
    
    Validates: Requirements 3.1-3.7, 4.1-4.5, 5.1-5.6, 7.3-7.4, 12.1-12.4
    """
    
    # Valid allocation modes
    VALID_MODES = {'exclusive', 'shared'}
    
    # Health statuses that block allocation
    BLOCKED_HEALTH_STATUSES = {'offline', 'maintenance'}
    
    def __init__(self, db_session: DbSession, audit_logger=None):
        """
        Initialize the AllocationManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
    
    # =========================================================================
    # Availability Checking Methods
    # =========================================================================
    
    def check_availability(
        self,
        resource_id: int,
        mode: str = "exclusive",
        check_time: Optional[datetime] = None,
        duration_minutes: Optional[int] = None
    ) -> bool:
        """
        Check if a resource is available for allocation.
        
        For exclusive mode: resource must have no active allocations and no conflicting reservations
        For shared mode: resource must have fewer active allocations than capacity and no conflicting exclusive reservations
        
        :param resource_id: The resource's unique identifier
        :param mode: Allocation mode ('exclusive' or 'shared')
        :param check_time: Optional time to check availability for (defaults to now)
        :param duration_minutes: Optional duration to check for reservation conflicts
        :returns: True if resource is available, False otherwise
        
        Validates: Requirements 3.1, 3.4, 3.5, 5.6
        """
        from ccai.pychestrate.core.orm import Resource, Allocation, AllocationStatus, Reservation, ReservationStatus
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            return False
        
        # Check health status
        if resource.health_status in self.BLOCKED_HEALTH_STATUSES:
            return False
        
        # Count active allocations
        active_allocations = self._db_session.query(Allocation).filter(
            Allocation.resource_id == resource_id,
            Allocation.status == AllocationStatus.ACTIVE.value
        ).all()
        
        active_count = len(active_allocations)
        
        # Check for conflicting reservations (Requirement 5.6)
        now = check_time if check_time is not None else utc_now()
        
        # If duration is specified, check for reservations that overlap with the time window
        if duration_minutes is not None:
            end_time = now + timedelta(minutes=duration_minutes)
        else:
            # Default to checking for reservations starting within the next hour
            # This provides a reasonable window for immediate checkouts
            end_time = now + timedelta(hours=1)
        
        # Find pending/active reservations that overlap with the check window
        conflicting_reservations = self._db_session.query(Reservation).filter(
            Reservation.resource_id == resource_id,
            Reservation.status.in_([ReservationStatus.PENDING.value, ReservationStatus.ACTIVE.value]),
            Reservation.start_time < end_time,
            Reservation.end_time > now
        ).all()
        
        if mode == "exclusive":
            # Exclusive mode requires no active allocations and no conflicting reservations
            if active_count > 0:
                return False
            # Any reservation (exclusive or shared) conflicts with exclusive checkout
            if len(conflicting_reservations) > 0:
                return False
            return True
        else:
            # Shared mode requires fewer allocations than capacity
            # Also check that no exclusive allocation exists
            has_exclusive = any(a.mode == "exclusive" for a in active_allocations)
            if has_exclusive:
                return False
            
            # Check for exclusive reservations that would conflict
            has_exclusive_reservation = any(r.mode == "exclusive" for r in conflicting_reservations)
            if has_exclusive_reservation:
                return False
            
            # Count shared reservations that overlap
            shared_reservation_count = sum(1 for r in conflicting_reservations if r.mode == "shared")
            
            # Total concurrent usage would be active allocations + shared reservations
            # For shared mode, we need to ensure we don't exceed capacity
            return (active_count + shared_reservation_count) < resource.capacity
    
    def find_available_resource(
        self,
        pool_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        resource_type: Optional[str] = None,
        mode: str = "exclusive",
        check_time: Optional[datetime] = None,
        duration_minutes: Optional[int] = None
    ) -> Optional[int]:
        """
        Find an available resource matching the given criteria.
        
        Uses load balancing by selecting the resource with the fewest active allocations.
        Also considers future reservations when determining availability.
        
        :param pool_id: Optional pool ID to filter by
        :param tags: Optional list of tags to filter by (resource must have all tags)
        :param resource_type: Optional resource type to filter by
        :param mode: Allocation mode ('exclusive' or 'shared')
        :param check_time: Optional time to check availability for (defaults to now)
        :param duration_minutes: Optional duration to check for reservation conflicts
        :returns: Resource ID if found, None otherwise
        
        Validates: Requirements 7.3, 7.4, 5.6
        """
        from ccai.pychestrate.core.orm import Resource, Tag, Allocation, AllocationStatus, Reservation, ReservationStatus
        
        query = self._db_session.query(Resource)
        
        # Filter by pool
        if pool_id is not None:
            query = query.filter(Resource.pool_id == pool_id)
        
        # Filter by resource type
        if resource_type is not None:
            query = query.filter(Resource.resource_type == resource_type)
        
        # Filter by health status (exclude offline and maintenance)
        query = query.filter(~Resource.health_status.in_(self.BLOCKED_HEALTH_STATUSES))
        
        # Filter by tags (resource must have all specified tags)
        if tags:
            for tag_name in tags:
                tag = self._db_session.query(Tag).filter(Tag.name == tag_name).first()
                if tag:
                    query = query.filter(Resource.tags.contains(tag))
                else:
                    # Tag doesn't exist, no resources can match
                    return None
        
        resources = query.all()
        
        # Calculate time window for reservation checking
        now = check_time if check_time is not None else utc_now()
        if duration_minutes is not None:
            end_time = now + timedelta(minutes=duration_minutes)
        else:
            end_time = now + timedelta(hours=1)
        
        # Find available resources with load balancing
        best_resource_id = None
        min_allocations = float('inf')
        
        for resource in resources:
            # Count active allocations for this resource
            active_allocations = self._db_session.query(Allocation).filter(
                Allocation.resource_id == resource.id,
                Allocation.status == AllocationStatus.ACTIVE.value
            ).all()
            
            active_count = len(active_allocations)
            
            # Check for conflicting reservations (Requirement 5.6)
            conflicting_reservations = self._db_session.query(Reservation).filter(
                Reservation.resource_id == resource.id,
                Reservation.status.in_([ReservationStatus.PENDING.value, ReservationStatus.ACTIVE.value]),
                Reservation.start_time < end_time,
                Reservation.end_time > now
            ).all()
            
            # Check availability based on mode
            if mode == "exclusive":
                if active_count == 0 and len(conflicting_reservations) == 0:
                    # For exclusive, prefer resources with no allocations and no reservations
                    # Use resource ID for deterministic selection
                    if best_resource_id is None or resource.id < best_resource_id:
                        best_resource_id = resource.id
                        min_allocations = 0
            else:
                # Shared mode
                has_exclusive = any(a.mode == "exclusive" for a in active_allocations)
                has_exclusive_reservation = any(r.mode == "exclusive" for r in conflicting_reservations)
                
                if not has_exclusive and not has_exclusive_reservation:
                    # Count shared reservations
                    shared_reservation_count = sum(1 for r in conflicting_reservations if r.mode == "shared")
                    total_usage = active_count + shared_reservation_count
                    
                    if total_usage < resource.capacity:
                        # Prefer resources with fewer allocations (load balancing)
                        if active_count < min_allocations or (active_count == min_allocations and 
                                                              (best_resource_id is None or resource.id < best_resource_id)):
                            best_resource_id = resource.id
                            min_allocations = active_count
        
        return best_resource_id

    
    # =========================================================================
    # Checkout Operations
    # =========================================================================
    
    def checkout(self, request: CheckoutRequest, user_id: str) -> AllocationResponse:
        """
        Checkout a resource. Uses database locking for concurrency control.
        
        Supports checkout by:
        - resource_id: Direct resource checkout
        - resource_name + pool_id: Checkout by name within pool
        - tags: Tag-based checkout with load balancing
        
        :param request: The checkout request containing checkout parameters
        :param user_id: The ID of the user making the checkout
        :returns: AllocationResponse with the allocation data
        :raises ResourceNotFoundError: If resource is not found
        :raises ResourceUnavailableError: If resource is not available
        :raises ResourceOfflineError: If resource is offline or in maintenance
        :raises CapacityExceededError: If shared resource has reached capacity
        :raises NoMatchingResourceError: If no resource matches tag criteria
        
        Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 8.2, 12.1, 12.2
        """
        from ccai.pychestrate.core.orm import (
            Resource, ResourcePool, Allocation, AllocationStatus, AllocationMode, User
        )
        
        # Validate mode
        mode = request.mode.lower() if request.mode else "exclusive"
        if mode not in self.VALID_MODES:
            mode = "exclusive"
        
        # Determine which resource to checkout
        resource_id = request.resource_id
        
        if resource_id is None and request.resource_name:
            # Lookup by name
            query = self._db_session.query(Resource).filter(Resource.name == request.resource_name)
            if request.pool_id is not None:
                query = query.filter(Resource.pool_id == request.pool_id)
            else:
                # Use default pool
                default_pool = self._db_session.query(ResourcePool).filter(
                    ResourcePool.is_default == True
                ).first()
                if default_pool:
                    query = query.filter(Resource.pool_id == default_pool.id)
            
            resource = query.first()
            if resource:
                resource_id = resource.id
        
        if resource_id is None and request.tags:
            # Tag-based checkout
            resource_id = self.find_available_resource(
                pool_id=request.pool_id,
                tags=request.tags,
                mode=mode
            )
            if resource_id is None:
                raise NoMatchingResourceError(
                    f"No available resource found matching tags: {', '.join(request.tags)}"
                )
        
        if resource_id is None:
            raise ResourceNotFoundError("No resource specified for checkout")
        
        # Use SELECT FOR UPDATE to lock the resource row for concurrency control
        # This prevents race conditions when multiple requests try to checkout the same resource
        resource = self._db_session.query(Resource).filter(
            Resource.id == resource_id
        ).with_for_update(nowait=False).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        # Check health status
        if resource.health_status in self.BLOCKED_HEALTH_STATUSES:
            raise ResourceOfflineError(
                f"Resource '{resource.name}' is {resource.health_status} and cannot be checked out",
                health_status=resource.health_status
            )
        
        # Check availability
        active_allocations = self._db_session.query(Allocation).filter(
            Allocation.resource_id == resource_id,
            Allocation.status == AllocationStatus.ACTIVE.value
        ).all()
        
        active_count = len(active_allocations)
        
        if mode == "exclusive":
            if active_count > 0:
                # Return current allocation details
                current = active_allocations[0]
                current_response = self._allocation_to_response(current)
                raise ResourceUnavailableError(
                    f"Resource '{resource.name}' is already allocated",
                    current_allocation=current_response
                )
        else:
            # Shared mode
            has_exclusive = any(a.mode == "exclusive" for a in active_allocations)
            if has_exclusive:
                current = next(a for a in active_allocations if a.mode == "exclusive")
                current_response = self._allocation_to_response(current)
                raise ResourceUnavailableError(
                    f"Resource '{resource.name}' has an exclusive allocation",
                    current_allocation=current_response
                )
            
            if active_count >= resource.capacity:
                raise CapacityExceededError(
                    f"Resource '{resource.name}' has reached its capacity limit of {resource.capacity}",
                    capacity=resource.capacity,
                    current_allocations=active_count
                )
        
        # Create the allocation
        now = utc_now()
        expected_checkin = None
        if request.timeout_minutes:
            expected_checkin = now + timedelta(minutes=request.timeout_minutes)
        
        # Create metadata snapshot
        metadata_snapshot = dict(resource.metadata_json) if resource.metadata_json else {}
        
        allocation = Allocation(
            resource_id=resource_id,
            user_id=user_id,
            job_id=request.job_id,
            mode=mode,
            status=AllocationStatus.ACTIVE.value,
            checkout_time=now,
            expected_checkin=expected_checkin,
            reason=request.reason,
            metadata_snapshot=metadata_snapshot
        )
        
        self._db_session.add(allocation)
        self._db_session.commit()
        
        # Log the checkout event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_checkout',
                user_id=str(user_id) if user_id else None,
                details={
                    "allocation_id": allocation.id,
                    "resource_id": resource_id,
                    "resource_name": resource.name,
                    "mode": mode,
                    "job_id": request.job_id
                }
            )
        
        return self._allocation_to_response(allocation)
    
    # =========================================================================
    # Checkin Operations
    # =========================================================================
    
    def checkin(self, allocation_id: int, user_id: str) -> AllocationResponse:
        """
        Checkin a resource, releasing the allocation.
        
        :param allocation_id: The allocation's unique identifier
        :param user_id: The ID of the user making the checkin
        :returns: AllocationResponse with the updated allocation data
        :raises AllocationNotFoundError: If allocation is not found
        :raises NotAllocationOwnerError: If user is not the allocation owner
        
        Validates: Requirements 4.1, 4.2, 4.3
        """
        from ccai.pychestrate.core.orm import Allocation, AllocationStatus
        
        allocation = self._db_session.query(Allocation).filter(
            Allocation.id == allocation_id
        ).first()
        
        if not allocation:
            raise AllocationNotFoundError(f"Allocation with ID '{allocation_id}' not found")
        
        # Check ownership
        if str(allocation.user_id) != str(user_id):
            raise NotAllocationOwnerError(
                f"User '{user_id}' is not the owner of allocation '{allocation_id}'"
            )
        
        # Check if already released
        if allocation.status != AllocationStatus.ACTIVE.value:
            raise AllocationNotFoundError(
                f"Allocation '{allocation_id}' is not active (status: {allocation.status})"
            )
        
        # Release the allocation
        now = utc_now()
        allocation.status = AllocationStatus.RELEASED.value
        allocation.actual_checkin = now
        
        # Calculate duration
        if allocation.checkout_time:
            duration = now - ensure_utc(allocation.checkout_time)
            allocation.duration_minutes = int(duration.total_seconds() / 60)
        
        self._db_session.commit()
        
        # Log the checkin event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_checkin',
                user_id=str(user_id) if user_id else None,
                details={
                    "allocation_id": allocation.id,
                    "resource_id": allocation.resource_id,
                    "duration_minutes": allocation.duration_minutes
                }
            )
        
        return self._allocation_to_response(allocation)
    
    def force_checkin(self, allocation_id: int, admin_user_id: str, reason: str) -> AllocationResponse:
        """
        Force checkin by administrator.
        
        :param allocation_id: The allocation's unique identifier
        :param admin_user_id: The ID of the administrator forcing the checkin
        :param reason: Reason for the forced checkin
        :returns: AllocationResponse with the updated allocation data
        :raises AllocationNotFoundError: If allocation is not found
        
        Validates: Requirements 4.4, 4.5
        """
        from ccai.pychestrate.core.orm import Allocation, AllocationStatus
        
        allocation = self._db_session.query(Allocation).filter(
            Allocation.id == allocation_id
        ).first()
        
        if not allocation:
            raise AllocationNotFoundError(f"Allocation with ID '{allocation_id}' not found")
        
        # Check if already released
        if allocation.status != AllocationStatus.ACTIVE.value:
            raise AllocationNotFoundError(
                f"Allocation '{allocation_id}' is not active (status: {allocation.status})"
            )
        
        # Force release the allocation
        now = utc_now()
        allocation.status = AllocationStatus.FORCED.value
        allocation.actual_checkin = now
        allocation.forced_by_id = admin_user_id
        allocation.force_reason = reason
        
        # Calculate duration
        if allocation.checkout_time:
            duration = now - ensure_utc(allocation.checkout_time)
            allocation.duration_minutes = int(duration.total_seconds() / 60)
        
        self._db_session.commit()
        
        # Log the forced checkin event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_force_checkin',
                user_id=str(admin_user_id) if admin_user_id else None,
                details={
                    "allocation_id": allocation.id,
                    "resource_id": allocation.resource_id,
                    "original_user_id": str(allocation.user_id),
                    "reason": reason,
                    "duration_minutes": allocation.duration_minutes
                }
            )
        
        return self._allocation_to_response(allocation)
    
    # =========================================================================
    # Timeout Handling
    # =========================================================================
    
    def expire_timed_out_allocations(self) -> int:
        """
        Release allocations that have exceeded their timeout.
        
        :returns: Number of allocations expired
        
        Validates: Requirements 3.6
        """
        from ccai.pychestrate.core.orm import Allocation, AllocationStatus
        
        now = utc_now()
        
        # Find active allocations with expired timeout
        expired_allocations = self._db_session.query(Allocation).filter(
            Allocation.status == AllocationStatus.ACTIVE.value,
            Allocation.expected_checkin != None,
            Allocation.expected_checkin < now
        ).all()
        
        count = 0
        for allocation in expired_allocations:
            allocation.status = AllocationStatus.EXPIRED.value
            allocation.actual_checkin = now
            
            # Calculate duration
            if allocation.checkout_time:
                duration = now - ensure_utc(allocation.checkout_time)
                allocation.duration_minutes = int(duration.total_seconds() / 60)
            
            count += 1
            
            # Log the expiration event
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type='resource_allocation_expired',
                    user_id=str(allocation.user_id) if allocation.user_id else None,
                    details={
                        "allocation_id": allocation.id,
                        "resource_id": allocation.resource_id,
                        "expected_checkin": str(allocation.expected_checkin),
                        "duration_minutes": allocation.duration_minutes
                    }
                )
        
        if count > 0:
            self._db_session.commit()
        
        return count

    
    # =========================================================================
    # Allocation Query Methods
    # =========================================================================
    
    def get_allocation(self, allocation_id: int) -> Optional[AllocationResponse]:
        """
        Get allocation details.
        
        :param allocation_id: The allocation's unique identifier
        :returns: AllocationResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import Allocation
        
        allocation = self._db_session.query(Allocation).filter(
            Allocation.id == allocation_id
        ).first()
        
        if not allocation:
            return None
        
        return self._allocation_to_response(allocation)
    
    def list_allocations(
        self,
        resource_id: Optional[int] = None,
        user_id: Optional[str] = None,
        job_id: Optional[str] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 50
    ) -> AllocationListResponse:
        """
        List allocations with filtering.
        
        :param resource_id: Optional resource ID to filter by
        :param user_id: Optional user ID to filter by
        :param job_id: Optional job ID to filter by
        :param status: Optional status to filter by
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: AllocationListResponse with paginated allocation list
        """
        from ccai.pychestrate.core.orm import Allocation
        
        query = self._db_session.query(Allocation)
        
        if resource_id is not None:
            query = query.filter(Allocation.resource_id == resource_id)
        
        if user_id is not None:
            query = query.filter(Allocation.user_id == user_id)
        
        if job_id is not None:
            query = query.filter(Allocation.job_id == job_id)
        
        if status is not None:
            query = query.filter(Allocation.status == status)
        
        # Order by checkout time descending (most recent first)
        query = query.order_by(Allocation.checkout_time.desc())
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        allocations = query.offset(offset).limit(limit).all()
        
        return AllocationListResponse(
            allocations=[self._allocation_to_response(a) for a in allocations],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def get_active_allocations(self, resource_id: int) -> List[AllocationResponse]:
        """
        Get all active allocations for a resource.
        
        :param resource_id: The resource's unique identifier
        :returns: List of active allocation responses
        """
        from ccai.pychestrate.core.orm import Allocation, AllocationStatus
        
        allocations = self._db_session.query(Allocation).filter(
            Allocation.resource_id == resource_id,
            Allocation.status == AllocationStatus.ACTIVE.value
        ).all()
        
        return [self._allocation_to_response(a) for a in allocations]
    
    def get_allocation_history(
        self,
        resource_id: Optional[int] = None,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        offset: int = 0,
        limit: int = 50
    ) -> AllocationListResponse:
        """
        Get historical allocations.
        
        :param resource_id: Optional resource ID to filter by
        :param user_id: Optional user ID to filter by
        :param start_date: Optional start date to filter by
        :param end_date: Optional end date to filter by
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: AllocationListResponse with paginated allocation history
        
        Validates: Requirements 9.1, 9.2
        """
        from ccai.pychestrate.core.orm import Allocation
        
        query = self._db_session.query(Allocation)
        
        if resource_id is not None:
            query = query.filter(Allocation.resource_id == resource_id)
        
        if user_id is not None:
            query = query.filter(Allocation.user_id == user_id)
        
        if start_date is not None:
            query = query.filter(Allocation.checkout_time >= start_date)
        
        if end_date is not None:
            query = query.filter(Allocation.checkout_time <= end_date)
        
        # Order by checkout time descending
        query = query.order_by(Allocation.checkout_time.desc())
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        allocations = query.offset(offset).limit(limit).all()
        
        return AllocationListResponse(
            allocations=[self._allocation_to_response(a) for a in allocations],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def get_utilization_metrics(
        self,
        resource_id: Optional[int] = None,
        pool_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate utilization metrics.
        
        :param resource_id: Optional resource ID to filter by
        :param pool_id: Optional pool ID to filter by
        :param start_date: Optional start date to filter by
        :param end_date: Optional end date to filter by
        :returns: Dictionary with utilization metrics
        
        Validates: Requirements 9.3
        """
        from ccai.pychestrate.core.orm import Allocation, Resource
        from sqlalchemy import func
        
        query = self._db_session.query(Allocation)
        
        if resource_id is not None:
            query = query.filter(Allocation.resource_id == resource_id)
        
        if pool_id is not None:
            query = query.join(Resource).filter(Resource.pool_id == pool_id)
        
        if start_date is not None:
            query = query.filter(Allocation.checkout_time >= start_date)
        
        if end_date is not None:
            query = query.filter(Allocation.checkout_time <= end_date)
        
        allocations = query.all()
        
        if not allocations:
            return {
                "total_allocations": 0,
                "total_duration_minutes": 0,
                "average_duration_minutes": 0,
                "peak_concurrent_usage": 0
            }
        
        total_duration = sum(a.duration_minutes or 0 for a in allocations)
        avg_duration = total_duration / len(allocations) if allocations else 0
        
        # Calculate peak concurrent usage by analyzing time intervals
        # Collect all start and end events
        events = []
        for a in allocations:
            if a.checkout_time:
                events.append((ensure_utc(a.checkout_time), 1))  # Start event
                end_time = a.actual_checkin or a.expected_checkin or utc_now()
                events.append((ensure_utc(end_time), -1))  # End event
        
        # Sort events by time
        events.sort(key=lambda x: x[0])
        
        # Calculate peak concurrent usage
        current_concurrent = 0
        peak_concurrent = 0
        for _, delta in events:
            current_concurrent += delta
            peak_concurrent = max(peak_concurrent, current_concurrent)
        
        return {
            "total_allocations": len(allocations),
            "total_duration_minutes": total_duration,
            "average_duration_minutes": round(avg_duration, 2),
            "peak_concurrent_usage": peak_concurrent
        }
    
    def export_allocation_data(
        self,
        resource_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format: str = "json"
    ) -> str:
        """
        Export allocation data in specified format.
        
        :param resource_id: Optional resource ID to filter by
        :param start_date: Optional start date to filter by
        :param end_date: Optional end date to filter by
        :param format: Export format ('json' or 'csv')
        :returns: Exported data as string
        
        Validates: Requirements 9.5
        """
        import json
        import csv
        import io
        
        from ccai.pychestrate.core.orm import Allocation
        
        query = self._db_session.query(Allocation)
        
        if resource_id is not None:
            query = query.filter(Allocation.resource_id == resource_id)
        
        if start_date is not None:
            query = query.filter(Allocation.checkout_time >= start_date)
        
        if end_date is not None:
            query = query.filter(Allocation.checkout_time <= end_date)
        
        allocations = query.order_by(Allocation.checkout_time.desc()).all()
        
        if format.lower() == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                "id", "resource_id", "user_id", "job_id", "mode", "status",
                "checkout_time", "actual_checkin", "duration_minutes"
            ])
            
            # Write data
            for a in allocations:
                writer.writerow([
                    a.id, a.resource_id, str(a.user_id), a.job_id, a.mode, a.status,
                    str(a.checkout_time) if a.checkout_time else "",
                    str(a.actual_checkin) if a.actual_checkin else "",
                    a.duration_minutes or ""
                ])
            
            return output.getvalue()
        else:
            # JSON format
            data = []
            for a in allocations:
                data.append({
                    "id": a.id,
                    "resource_id": a.resource_id,
                    "user_id": str(a.user_id),
                    "job_id": a.job_id,
                    "mode": a.mode,
                    "status": a.status,
                    "checkout_time": str(a.checkout_time) if a.checkout_time else None,
                    "actual_checkin": str(a.actual_checkin) if a.actual_checkin else None,
                    "duration_minutes": a.duration_minutes
                })
            
            return json.dumps(data, indent=2)
    
    def cleanup_old_allocations(self, retention_days: int = 90) -> int:
        """
        Remove allocation records older than the retention period.
        
        Only removes allocations that are not active (released, expired, or forced).
        Active allocations are never cleaned up regardless of age.
        
        :param retention_days: Number of days to retain allocation records (default 90)
        :returns: Number of allocation records removed
        
        Validates: Requirements 9.4
        """
        from ccai.pychestrate.core.orm import Allocation, AllocationStatus
        
        cutoff_date = utc_now() - timedelta(days=retention_days)
        
        # Count allocations to be deleted (only non-active allocations)
        count = self._db_session.query(Allocation).filter(
            Allocation.checkout_time < cutoff_date,
            Allocation.status != AllocationStatus.ACTIVE.value
        ).count()
        
        # Delete old non-active allocations
        self._db_session.query(Allocation).filter(
            Allocation.checkout_time < cutoff_date,
            Allocation.status != AllocationStatus.ACTIVE.value
        ).delete(synchronize_session=False)
        
        self._db_session.commit()
        
        # Log the cleanup event
        if self._audit_logger and count > 0:
            self._audit_logger.log_event(
                event_type='allocation_history_cleanup',
                details={
                    "retention_days": retention_days,
                    "records_deleted": count,
                    "cutoff_date": str(cutoff_date)
                }
            )
        
        return count
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    # =========================================================================
    # Reservation Operations
    # =========================================================================
    
    def create_reservation(self, request: ReservationRequest, user_id: str) -> ReservationResponse:
        """
        Create a future reservation for a resource.
        
        :param request: The reservation request containing reservation parameters
        :param user_id: The ID of the user making the reservation
        :returns: ReservationResponse with the reservation data
        :raises ResourceNotFoundError: If resource is not found
        :raises InvalidTimeWindowError: If time window is invalid
        :raises ReservationConflictError: If reservation conflicts with existing reservations
        
        Validates: Requirements 5.1, 5.2
        """
        from ccai.pychestrate.core.orm import Resource, Reservation, ReservationStatus
        
        # Validate resource exists
        resource = self._db_session.query(Resource).filter(
            Resource.id == request.resource_id
        ).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{request.resource_id}' not found")
        
        # Validate time window
        if request.start_time is None or request.end_time is None:
            raise InvalidTimeWindowError("Both start_time and end_time are required")
        
        if request.start_time >= request.end_time:
            raise InvalidTimeWindowError("start_time must be before end_time")
        
        now = utc_now()
        if request.start_time < now:
            raise InvalidTimeWindowError("start_time cannot be in the past")
        
        # Validate mode
        mode = request.mode.lower() if request.mode else "exclusive"
        if mode not in self.VALID_MODES:
            mode = "exclusive"
        
        # Check for conflicts with existing reservations
        conflicts = self.check_reservation_conflicts(
            resource_id=request.resource_id,
            start_time=request.start_time,
            end_time=request.end_time,
            mode=mode
        )
        
        if conflicts:
            raise ReservationConflictError(
                f"Reservation conflicts with {len(conflicts)} existing reservation(s)",
                conflicting_reservations=conflicts
            )
        
        # Create the reservation
        reservation = Reservation(
            resource_id=request.resource_id,
            user_id=user_id,
            job_id=request.job_id,
            start_time=request.start_time,
            end_time=request.end_time,
            mode=mode,
            status=ReservationStatus.PENDING.value,
            reason=request.reason
        )
        
        self._db_session.add(reservation)
        self._db_session.commit()
        
        # Log the reservation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_reservation_created',
                user_id=str(user_id) if user_id else None,
                details={
                    "reservation_id": reservation.id,
                    "resource_id": request.resource_id,
                    "resource_name": resource.name,
                    "start_time": str(request.start_time),
                    "end_time": str(request.end_time),
                    "mode": mode
                }
            )
        
        return self._reservation_to_response(reservation)
    
    def cancel_reservation(self, reservation_id: int, user_id: str) -> ReservationResponse:
        """
        Cancel a pending reservation.
        
        :param reservation_id: The reservation's unique identifier
        :param user_id: The ID of the user cancelling the reservation
        :returns: ReservationResponse with the updated reservation data
        :raises ReservationNotFoundError: If reservation is not found
        :raises NotAllocationOwnerError: If user is not the reservation owner
        
        Validates: Requirements 5.4
        """
        from ccai.pychestrate.core.orm import Reservation, ReservationStatus
        
        reservation = self._db_session.query(Reservation).filter(
            Reservation.id == reservation_id
        ).first()
        
        if not reservation:
            raise ReservationNotFoundError(f"Reservation with ID '{reservation_id}' not found")
        
        # Check ownership
        if str(reservation.user_id) != str(user_id):
            raise NotAllocationOwnerError(
                f"User '{user_id}' is not the owner of reservation '{reservation_id}'"
            )
        
        # Check if reservation can be cancelled
        if reservation.status not in (ReservationStatus.PENDING.value, ReservationStatus.ACTIVE.value):
            raise ReservationNotFoundError(
                f"Reservation '{reservation_id}' cannot be cancelled (status: {reservation.status})"
            )
        
        # Cancel the reservation
        reservation.status = ReservationStatus.CANCELLED.value
        
        self._db_session.commit()
        
        # Log the cancellation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_reservation_cancelled',
                user_id=str(user_id) if user_id else None,
                details={
                    "reservation_id": reservation.id,
                    "resource_id": reservation.resource_id
                }
            )
        
        return self._reservation_to_response(reservation)
    
    def modify_reservation(
        self,
        reservation_id: int,
        user_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> ReservationResponse:
        """
        Modify reservation time window.
        
        :param reservation_id: The reservation's unique identifier
        :param user_id: The ID of the user modifying the reservation
        :param start_time: New start time (optional)
        :param end_time: New end time (optional)
        :returns: ReservationResponse with the updated reservation data
        :raises ReservationNotFoundError: If reservation is not found
        :raises NotAllocationOwnerError: If user is not the reservation owner
        :raises InvalidTimeWindowError: If new time window is invalid
        :raises ReservationConflictError: If new time window conflicts with existing reservations
        
        Validates: Requirements 5.5
        """
        from ccai.pychestrate.core.orm import Reservation, ReservationStatus
        
        reservation = self._db_session.query(Reservation).filter(
            Reservation.id == reservation_id
        ).first()
        
        if not reservation:
            raise ReservationNotFoundError(f"Reservation with ID '{reservation_id}' not found")
        
        # Check ownership
        if str(reservation.user_id) != str(user_id):
            raise NotAllocationOwnerError(
                f"User '{user_id}' is not the owner of reservation '{reservation_id}'"
            )
        
        # Check if reservation can be modified
        if reservation.status != ReservationStatus.PENDING.value:
            raise ReservationNotFoundError(
                f"Reservation '{reservation_id}' cannot be modified (status: {reservation.status})"
            )
        
        # Determine new time window
        new_start = start_time if start_time is not None else reservation.start_time
        new_end = end_time if end_time is not None else reservation.end_time
        
        # Validate new time window
        if new_start >= new_end:
            raise InvalidTimeWindowError("start_time must be before end_time")
        
        now = utc_now()
        if new_start < now:
            raise InvalidTimeWindowError("start_time cannot be in the past")
        
        # Check for conflicts with existing reservations (excluding this one)
        conflicts = self.check_reservation_conflicts(
            resource_id=reservation.resource_id,
            start_time=new_start,
            end_time=new_end,
            mode=reservation.mode,
            exclude_id=reservation_id
        )
        
        if conflicts:
            raise ReservationConflictError(
                f"Modified reservation conflicts with {len(conflicts)} existing reservation(s)",
                conflicting_reservations=conflicts
            )
        
        # Update the reservation
        reservation.start_time = new_start
        reservation.end_time = new_end
        
        self._db_session.commit()
        
        # Log the modification event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='resource_reservation_modified',
                user_id=str(user_id) if user_id else None,
                details={
                    "reservation_id": reservation.id,
                    "resource_id": reservation.resource_id,
                    "new_start_time": str(new_start),
                    "new_end_time": str(new_end)
                }
            )
        
        return self._reservation_to_response(reservation)
    
    def get_reservation(self, reservation_id: int) -> Optional[ReservationResponse]:
        """
        Get reservation details.
        
        :param reservation_id: The reservation's unique identifier
        :returns: ReservationResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import Reservation
        
        reservation = self._db_session.query(Reservation).filter(
            Reservation.id == reservation_id
        ).first()
        
        if not reservation:
            return None
        
        return self._reservation_to_response(reservation)
    
    def list_reservations(
        self,
        resource_id: Optional[int] = None,
        user_id: Optional[str] = None,
        start_after: Optional[datetime] = None,
        end_before: Optional[datetime] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 50
    ) -> ReservationListResponse:
        """
        List reservations with filtering.
        
        :param resource_id: Optional resource ID to filter by
        :param user_id: Optional user ID to filter by
        :param start_after: Optional filter for reservations starting after this time
        :param end_before: Optional filter for reservations ending before this time
        :param status: Optional status to filter by
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: ReservationListResponse with paginated reservation list
        
        Validates: Requirements 5.1
        """
        from ccai.pychestrate.core.orm import Reservation
        
        query = self._db_session.query(Reservation)
        
        if resource_id is not None:
            query = query.filter(Reservation.resource_id == resource_id)
        
        if user_id is not None:
            query = query.filter(Reservation.user_id == user_id)
        
        if start_after is not None:
            query = query.filter(Reservation.start_time >= start_after)
        
        if end_before is not None:
            query = query.filter(Reservation.end_time <= end_before)
        
        if status is not None:
            query = query.filter(Reservation.status == status)
        
        # Order by start time ascending (earliest first)
        query = query.order_by(Reservation.start_time.asc())
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        reservations = query.offset(offset).limit(limit).all()
        
        return ReservationListResponse(
            reservations=[self._reservation_to_response(r) for r in reservations],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def check_reservation_conflicts(
        self,
        resource_id: int,
        start_time: datetime,
        end_time: datetime,
        mode: str = "exclusive",
        exclude_id: Optional[int] = None
    ) -> List[ReservationResponse]:
        """
        Check for conflicting reservations.
        
        Two reservations conflict if:
        - They are for the same resource
        - Their time windows overlap
        - At least one is exclusive mode
        
        :param resource_id: The resource's unique identifier
        :param start_time: Start time of the proposed reservation
        :param end_time: End time of the proposed reservation
        :param mode: Mode of the proposed reservation
        :param exclude_id: Optional reservation ID to exclude from conflict check
        :returns: List of conflicting reservations
        
        Validates: Requirements 5.1, 5.2
        """
        from ccai.pychestrate.core.orm import Reservation, ReservationStatus
        
        # Find overlapping reservations for the same resource
        # Two time windows overlap if: start1 < end2 AND start2 < end1
        query = self._db_session.query(Reservation).filter(
            Reservation.resource_id == resource_id,
            Reservation.status.in_([ReservationStatus.PENDING.value, ReservationStatus.ACTIVE.value]),
            Reservation.start_time < end_time,
            Reservation.end_time > start_time
        )
        
        if exclude_id is not None:
            query = query.filter(Reservation.id != exclude_id)
        
        overlapping = query.all()
        
        # Filter for actual conflicts based on mode
        conflicts = []
        for reservation in overlapping:
            # Conflict if either reservation is exclusive
            if mode == "exclusive" or reservation.mode == "exclusive":
                conflicts.append(self._reservation_to_response(reservation))
        
        return conflicts
    
    # =========================================================================
    # Reservation Activation
    # =========================================================================
    
    def activate_due_reservations(self) -> int:
        """
        Convert due reservations to active allocations.
        
        Finds all pending reservations whose start time has arrived and converts
        them to active allocations with the same parameters.
        
        :returns: Number of reservations activated
        
        Validates: Requirements 5.3
        """
        from ccai.pychestrate.core.orm import (
            Resource, Reservation, Allocation, ReservationStatus, AllocationStatus
        )
        
        now = utc_now()
        
        # Find pending reservations whose start time has arrived
        due_reservations = self._db_session.query(Reservation).filter(
            Reservation.status == ReservationStatus.PENDING.value,
            Reservation.start_time <= now
        ).all()
        
        count = 0
        for reservation in due_reservations:
            # Get the resource to check availability and get metadata
            resource = self._db_session.query(Resource).filter(
                Resource.id == reservation.resource_id
            ).first()
            
            if not resource:
                # Resource no longer exists, cancel the reservation
                reservation.status = ReservationStatus.CANCELLED.value
                continue
            
            # Check if resource is available (health status)
            if resource.health_status in self.BLOCKED_HEALTH_STATUSES:
                # Resource is offline/maintenance, skip activation but don't cancel
                # The reservation will be retried on next activation run
                continue
            
            # Check for conflicting active allocations
            active_allocations = self._db_session.query(Allocation).filter(
                Allocation.resource_id == reservation.resource_id,
                Allocation.status == AllocationStatus.ACTIVE.value
            ).all()
            
            active_count = len(active_allocations)
            
            # Check availability based on mode
            can_activate = False
            if reservation.mode == "exclusive":
                can_activate = active_count == 0
            else:
                # Shared mode
                has_exclusive = any(a.mode == "exclusive" for a in active_allocations)
                if not has_exclusive:
                    can_activate = active_count < resource.capacity
            
            if not can_activate:
                # Cannot activate yet due to conflicting allocations
                # The reservation will be retried on next activation run
                continue
            
            # Create the allocation from the reservation
            # Calculate expected checkin from reservation end time
            expected_checkin = reservation.end_time
            
            # Create metadata snapshot
            metadata_snapshot = dict(resource.metadata_json) if resource.metadata_json else {}
            
            allocation = Allocation(
                resource_id=reservation.resource_id,
                user_id=reservation.user_id,
                job_id=reservation.job_id,
                mode=reservation.mode,
                status=AllocationStatus.ACTIVE.value,
                checkout_time=now,
                expected_checkin=expected_checkin,
                reason=reservation.reason,
                metadata_snapshot=metadata_snapshot
            )
            
            self._db_session.add(allocation)
            self._db_session.flush()  # Get the allocation ID
            
            # Update the reservation status and link to allocation
            reservation.status = ReservationStatus.ACTIVE.value
            reservation.allocation_id = allocation.id
            
            count += 1
            
            # Log the activation event
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type='resource_reservation_activated',
                    user_id=str(reservation.user_id) if reservation.user_id else None,
                    details={
                        "reservation_id": reservation.id,
                        "allocation_id": allocation.id,
                        "resource_id": reservation.resource_id,
                        "resource_name": resource.name,
                        "mode": reservation.mode
                    }
                )
        
        if count > 0:
            self._db_session.commit()
        
        return count
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _allocation_to_response(self, allocation) -> AllocationResponse:
        """
        Convert an Allocation ORM object to an AllocationResponse.
        
        :param allocation: The Allocation ORM object
        :returns: AllocationResponse dataclass
        """
        from ccai.pychestrate.core.orm import Resource, User
        
        resource = self._db_session.query(Resource).filter(
            Resource.id == allocation.resource_id
        ).first()
        
        user = self._db_session.query(User).filter(
            User.id == allocation.user_id
        ).first()
        
        return AllocationResponse(
            id=allocation.id,
            resource_id=allocation.resource_id,
            resource_name=resource.name if resource else "Unknown",
            resource_type=resource.resource_type if resource else "Unknown",
            user_id=str(allocation.user_id),
            username=user.login if user else None,
            job_id=allocation.job_id,
            mode=allocation.mode,
            status=allocation.status,
            checkout_time=allocation.checkout_time,
            expected_checkin=allocation.expected_checkin,
            actual_checkin=allocation.actual_checkin,
            duration_minutes=allocation.duration_minutes,
            metadata=allocation.metadata_snapshot or {}
        )
    
    def _reservation_to_response(self, reservation) -> ReservationResponse:
        """
        Convert a Reservation ORM object to a ReservationResponse.
        
        :param reservation: The Reservation ORM object
        :returns: ReservationResponse dataclass
        """
        from ccai.pychestrate.core.orm import Resource, User
        
        resource = self._db_session.query(Resource).filter(
            Resource.id == reservation.resource_id
        ).first()
        
        user = self._db_session.query(User).filter(
            User.id == reservation.user_id
        ).first()
        
        return ReservationResponse(
            id=reservation.id,
            resource_id=reservation.resource_id,
            resource_name=resource.name if resource else "Unknown",
            user_id=str(reservation.user_id),
            username=user.login if user else None,
            job_id=reservation.job_id,
            start_time=reservation.start_time,
            end_time=reservation.end_time,
            mode=reservation.mode,
            status=reservation.status,
            created_at=reservation.created_at
        )
