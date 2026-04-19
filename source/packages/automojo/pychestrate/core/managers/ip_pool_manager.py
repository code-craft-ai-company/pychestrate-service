"""
.. module:: ip_pool_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the IPPoolManager class for IP address pool management and allocation

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import ipaddress

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import utc_now


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class IPPoolCreateRequest:
    """Request dataclass for creating a new IP pool."""
    name: str
    cidr: str
    gateway: Optional[str] = None
    dns_servers: List[str] = field(default_factory=list)
    description: str = ""
    reserved_ips: List[str] = field(default_factory=list)


@dataclass
class IPPoolUpdateRequest:
    """Request dataclass for updating an existing IP pool."""
    description: Optional[str] = None
    gateway: Optional[str] = None
    dns_servers: Optional[List[str]] = None
    reserved_ips: Optional[List[str]] = None


@dataclass
class IPPoolResponse:
    """Response dataclass for IP pool data."""
    id: int
    name: str
    cidr: str
    ip_version: str
    network_address: str
    broadcast_address: Optional[str]
    subnet_mask: str
    gateway: Optional[str]
    dns_servers: List[str]
    description: str
    total_addresses: int
    reserved_count: int
    allocated_count: int
    available_count: int
    created_at: datetime
    created_by: Optional[str]


@dataclass
class IPPoolListResponse:
    """Response dataclass for paginated IP pool list."""
    pools: List[IPPoolResponse]
    total: int
    offset: int
    limit: int


@dataclass
class IPAllocationRequest:
    """Request dataclass for IP allocation."""
    pool_id: int
    count: int = 1
    specific_ip: Optional[str] = None
    prefer_contiguous: bool = True
    job_id: Optional[str] = None
    timeout_minutes: Optional[int] = None
    reason: str = ""


@dataclass
class IPAllocationResponse:
    """Response dataclass for IP allocation data."""
    id: int
    pool_id: int
    pool_name: str
    ip_address: str
    subnet_mask: str
    gateway: Optional[str]
    dns_servers: List[str]
    user_id: str
    username: Optional[str]
    job_id: Optional[str]
    status: str
    checkout_time: datetime
    expected_checkin: Optional[datetime]


@dataclass
class IPBulkAllocationResponse:
    """Response dataclass for bulk IP allocation."""
    allocations: List[IPAllocationResponse]
    contiguous: bool
    start_ip: str
    end_ip: str


@dataclass
class IPAllocationListResponse:
    """Response dataclass for paginated IP allocation list."""
    allocations: List[IPAllocationResponse]
    total: int
    offset: int
    limit: int


# =============================================================================
# Exceptions
# =============================================================================

class IPPoolValidationError(Exception):
    """Exception raised when IP pool validation fails."""
    
    def __init__(self, message: str, field: str = None, error_code: str = None):
        self.message = message
        self.field = field
        self.error_code = error_code or "VALIDATION_ERROR"
        super().__init__(self.message)


class IPPoolNotFoundError(Exception):
    """Exception raised when an IP pool is not found."""
    
    def __init__(self, message: str, error_code: str = "IP_POOL_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DuplicateIPPoolError(Exception):
    """Exception raised when attempting to create an IP pool with duplicate name."""
    
    def __init__(self, message: str, field: str = None, error_code: str = "IP_POOL_NAME_EXISTS"):
        self.message = message
        self.field = field
        self.error_code = error_code
        super().__init__(self.message)


class CIDROverlapError(Exception):
    """Exception raised when CIDR ranges overlap."""
    
    def __init__(self, message: str, overlapping_pools: List[str] = None, error_code: str = "CIDR_OVERLAP"):
        self.message = message
        self.overlapping_pools = overlapping_pools or []
        self.error_code = error_code
        super().__init__(self.message)


class IPPoolHasAllocationsError(Exception):
    """Exception raised when attempting to delete an IP pool with active allocations."""
    
    def __init__(self, message: str, error_code: str = "IP_POOL_HAS_ALLOCATIONS"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class IPPoolExhaustedError(Exception):
    """Exception raised when an IP pool has no available addresses."""
    
    def __init__(self, message: str, error_code: str = "IP_POOL_EXHAUSTED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class IPNotAvailableError(Exception):
    """Exception raised when a requested IP address is not available."""
    
    def __init__(self, message: str, error_code: str = "IP_NOT_AVAILABLE"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class IPNotInPoolError(Exception):
    """Exception raised when a requested IP address is not in the pool range."""
    
    def __init__(self, message: str, error_code: str = "IP_NOT_IN_POOL"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class IPAllocationNotFoundError(Exception):
    """Exception raised when an IP allocation is not found."""
    
    def __init__(self, message: str, error_code: str = "IP_ALLOCATION_NOT_FOUND"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class NotIPAllocationOwnerError(Exception):
    """Exception raised when user is not the owner of an IP allocation."""
    
    def __init__(self, message: str, error_code: str = "NOT_IP_ALLOCATION_OWNER"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class IPReservedError(Exception):
    """Exception raised when an IP address is marked as reserved."""
    
    def __init__(self, message: str, error_code: str = "IP_RESERVED"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


# =============================================================================
# CIDR Validation and Utility Functions
# =============================================================================

def validate_cidr(cidr: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a CIDR string is valid IPv4 or IPv6 notation.
    
    :param cidr: The CIDR string to validate (e.g., "192.168.1.0/24" or "2001:db8::/32")
    :returns: Tuple of (is_valid, error_message). If valid, error_message is None.
    
    Validates: Requirements 2A.2
    """
    if not cidr:
        return False, "CIDR cannot be empty"
    
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        return True, None
    except ValueError as e:
        return False, str(e)


def parse_cidr(cidr: str) -> Dict[str, Any]:
    """
    Parse a CIDR string and return network information.
    
    :param cidr: The CIDR string to parse
    :returns: Dictionary with network information
    :raises IPPoolValidationError: If CIDR is invalid
    """
    is_valid, error_msg = validate_cidr(cidr)
    if not is_valid:
        raise IPPoolValidationError(error_msg, field="cidr", error_code="INVALID_CIDR")
    
    network = ipaddress.ip_network(cidr, strict=False)
    
    result = {
        "network": network,
        "network_address": str(network.network_address),
        "subnet_mask": str(network.netmask),
        "prefix_length": network.prefixlen,
    }
    
    if network.version == 4:
        result["ip_version"] = "ipv4"
        result["broadcast_address"] = str(network.broadcast_address)
    else:
        result["ip_version"] = "ipv6"
        result["broadcast_address"] = None
    
    return result


def calculate_usable_hosts(cidr: str, reserved_ips: List[str] = None) -> int:
    """
    Calculate the number of usable host addresses in a CIDR range.
    
    For IPv4:
    - Excludes network address and broadcast address
    - Excludes reserved IPs
    
    For IPv6:
    - Excludes network address (no broadcast in IPv6)
    - Excludes reserved IPs
    
    :param cidr: The CIDR string
    :param reserved_ips: List of reserved IP addresses to exclude
    :returns: Number of usable host addresses
    
    Validates: Requirements 2A.3
    """
    reserved_ips = reserved_ips or []
    
    network = ipaddress.ip_network(cidr, strict=False)
    
    # Total hosts in the network
    total_hosts = network.num_addresses
    
    if network.version == 4:
        # For IPv4, exclude network and broadcast addresses
        # For /31 and /32 networks, special handling
        if network.prefixlen >= 31:
            usable = total_hosts
        else:
            usable = total_hosts - 2  # Exclude network and broadcast
    else:
        # For IPv6, exclude network address only
        usable = total_hosts - 1
    
    # Subtract reserved IPs that are actually in the network
    for ip_str in reserved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
            if ip in network:
                usable -= 1
        except ValueError:
            pass  # Invalid IP, skip
    
    return max(0, usable)


def get_usable_ips(cidr: str, reserved_ips: List[str] = None) -> List[str]:
    """
    Get a list of all usable IP addresses in a CIDR range.
    
    :param cidr: The CIDR string
    :param reserved_ips: List of reserved IP addresses to exclude
    :returns: List of usable IP address strings
    """
    reserved_ips = reserved_ips or []
    reserved_set = set(reserved_ips)
    
    network = ipaddress.ip_network(cidr, strict=False)
    usable_ips = []
    
    for ip in network.hosts():
        ip_str = str(ip)
        if ip_str not in reserved_set:
            usable_ips.append(ip_str)
    
    return usable_ips


def check_cidr_overlap(cidr1: str, cidr2: str) -> bool:
    """
    Check if two CIDR ranges overlap.
    
    :param cidr1: First CIDR string
    :param cidr2: Second CIDR string
    :returns: True if the ranges overlap, False otherwise
    
    Validates: Requirements 2A.6
    """
    try:
        network1 = ipaddress.ip_network(cidr1, strict=False)
        network2 = ipaddress.ip_network(cidr2, strict=False)
        
        # Networks of different versions cannot overlap
        if network1.version != network2.version:
            return False
        
        return network1.overlaps(network2)
    except ValueError:
        return False


def is_ip_in_cidr(ip_address: str, cidr: str) -> bool:
    """
    Check if an IP address is within a CIDR range.
    
    :param ip_address: The IP address to check
    :param cidr: The CIDR range
    :returns: True if the IP is in the range, False otherwise
    """
    try:
        ip = ipaddress.ip_address(ip_address)
        network = ipaddress.ip_network(cidr, strict=False)
        return ip in network
    except ValueError:
        return False


def validate_ip_address(ip_address: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a string is a valid IP address.
    
    :param ip_address: The IP address string to validate
    :returns: Tuple of (is_valid, error_message)
    """
    if not ip_address:
        return False, "IP address cannot be empty"
    
    try:
        ipaddress.ip_address(ip_address)
        return True, None
    except ValueError as e:
        return False, str(e)




# =============================================================================
# IPPoolManager Class
# =============================================================================

class IPPoolManager:
    """
    Manager class for IP address pool management and allocation.
    
    This class handles all IP pool-related operations including:
    - IP pool creation with CIDR validation
    - IP pool retrieval and listing
    - IP pool updates and deletion
    - IP address checkout (allocation)
    - IP address checkin (release)
    - Reserved IP management
    - Pool statistics calculation
    
    Validates: Requirements 2A.1-2A.6, 3A.1-3A.6, 4A.1-4A.4
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None):
        """
        Initialize the IPPoolManager with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
    
    # =========================================================================
    # CIDR Validation Methods
    # =========================================================================
    
    def validate_cidr(self, cidr: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that a CIDR string is valid IPv4 or IPv6 notation.
        
        :param cidr: The CIDR string to validate
        :returns: Tuple of (is_valid, error_message)
        
        Validates: Requirements 2A.2
        """
        return validate_cidr(cidr)
    
    def check_cidr_overlap(self, cidr: str, exclude_pool_id: int = None) -> List[IPPoolResponse]:
        """
        Check if a CIDR range overlaps with existing pools.
        
        :param cidr: The CIDR string to check
        :param exclude_pool_id: Optional pool ID to exclude from overlap check
        :returns: List of overlapping pool responses
        
        Validates: Requirements 2A.6
        """
        from automojo.pychestrate.core.orm import IPPool
        
        overlapping_pools = []
        
        query = self._db_session.query(IPPool)
        if exclude_pool_id is not None:
            query = query.filter(IPPool.id != exclude_pool_id)
        
        pools = query.all()
        
        for pool in pools:
            if check_cidr_overlap(cidr, pool.cidr):
                overlapping_pools.append(self._pool_to_response(pool))
        
        return overlapping_pools
    
    def calculate_pool_stats(self, pool_id: int) -> Dict[str, int]:
        """
        Calculate pool statistics (total, reserved, allocated, available).
        
        :param pool_id: The pool's unique identifier
        :returns: Dictionary with pool statistics
        :raises IPPoolNotFoundError: If pool is not found
        
        Validates: Requirements 2A.3, 2A.5
        """
        from automojo.pychestrate.core.orm import IPPool, IPAllocation, IPAllocationStatus
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == pool_id).first()
        
        if not pool:
            raise IPPoolNotFoundError(f"IP pool with ID '{pool_id}' not found")
        
        # Calculate total usable addresses
        total_usable = calculate_usable_hosts(pool.cidr, [])
        
        # Count reserved IPs
        reserved_count = len(pool.reserved_ips) if pool.reserved_ips else 0
        
        # Count active allocations
        allocated_count = self._db_session.query(IPAllocation).filter(
            IPAllocation.pool_id == pool_id,
            IPAllocation.status == IPAllocationStatus.ACTIVE.value
        ).count()
        
        # Calculate available
        available_count = total_usable - reserved_count - allocated_count
        
        return {
            "total_addresses": total_usable,
            "reserved_count": reserved_count,
            "allocated_count": allocated_count,
            "available_count": max(0, available_count)
        }
    
    # =========================================================================
    # IP Pool CRUD Operations
    # =========================================================================
    
    def create_pool(self, request: IPPoolCreateRequest, user_id: str = None) -> IPPoolResponse:
        """
        Create a new IP address pool from CIDR range.
        
        :param request: The pool creation request containing pool data
        :param user_id: The ID of the user creating the pool
        :returns: IPPoolResponse with the created pool data
        :raises IPPoolValidationError: If validation fails
        :raises DuplicateIPPoolError: If pool name already exists
        :raises CIDROverlapError: If CIDR overlaps with existing pools
        
        Validates: Requirements 2A.1, 2A.2, 2A.6
        """
        from automojo.pychestrate.core.orm import IPPool
        
        # Validate pool name
        if not request.name or len(request.name.strip()) == 0:
            raise IPPoolValidationError(
                "Pool name is required",
                field="name",
                error_code="INVALID_POOL_NAME"
            )
        
        # Validate CIDR
        is_valid, error_msg = self.validate_cidr(request.cidr)
        if not is_valid:
            raise IPPoolValidationError(
                f"Invalid CIDR: {error_msg}",
                field="cidr",
                error_code="INVALID_CIDR"
            )
        
        # Check for duplicate pool name
        existing_pool = self._db_session.query(IPPool).filter(
            IPPool.name == request.name
        ).first()
        
        if existing_pool:
            raise DuplicateIPPoolError(
                f"IP pool with name '{request.name}' already exists",
                field="name"
            )
        
        # Check for CIDR overlap
        overlapping_pools = self.check_cidr_overlap(request.cidr)
        if overlapping_pools:
            pool_names = [p.name for p in overlapping_pools]
            raise CIDROverlapError(
                f"CIDR range '{request.cidr}' overlaps with existing pools: {', '.join(pool_names)}",
                overlapping_pools=pool_names
            )
        
        # Parse CIDR to get network information
        cidr_info = parse_cidr(request.cidr)
        
        # Validate reserved IPs are in the CIDR range
        for ip in request.reserved_ips:
            if not is_ip_in_cidr(ip, request.cidr):
                raise IPPoolValidationError(
                    f"Reserved IP '{ip}' is not in CIDR range '{request.cidr}'",
                    field="reserved_ips",
                    error_code="IP_NOT_IN_POOL"
                )
        
        # Validate gateway is in the CIDR range (if provided)
        if request.gateway:
            if not is_ip_in_cidr(request.gateway, request.cidr):
                raise IPPoolValidationError(
                    f"Gateway '{request.gateway}' is not in CIDR range '{request.cidr}'",
                    field="gateway",
                    error_code="IP_NOT_IN_POOL"
                )
        
        # Validate DNS servers are valid IP addresses
        for dns in request.dns_servers:
            is_valid, error_msg = validate_ip_address(dns)
            if not is_valid:
                raise IPPoolValidationError(
                    f"Invalid DNS server '{dns}': {error_msg}",
                    field="dns_servers",
                    error_code="INVALID_DNS_SERVER"
                )
        
        # Create the pool
        now = utc_now()
        
        pool = IPPool(
            name=request.name,
            cidr=request.cidr,
            ip_version=cidr_info["ip_version"],
            network_address=cidr_info["network_address"],
            broadcast_address=cidr_info["broadcast_address"],
            subnet_mask=cidr_info["subnet_mask"],
            gateway=request.gateway,
            dns_servers=request.dns_servers,
            description=request.description,
            reserved_ips=request.reserved_ips,
            created_at=now,
            created_by_id=user_id
        )
        
        self._db_session.add(pool)
        self._db_session.commit()
        
        # Log the pool creation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='ip_pool_created',
                user_id=str(user_id) if user_id else None,
                details={
                    "pool_id": pool.id,
                    "pool_name": pool.name,
                    "cidr": pool.cidr
                }
            )
        
        return self._pool_to_response(pool)
    
    def get_pool(self, pool_id: int) -> Optional[IPPoolResponse]:
        """
        Get IP pool by ID.
        
        :param pool_id: The pool's unique identifier
        :returns: IPPoolResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import IPPool
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == pool_id).first()
        
        if not pool:
            return None
        
        return self._pool_to_response(pool)
    
    def get_pool_by_name(self, name: str) -> Optional[IPPoolResponse]:
        """
        Get IP pool by name.
        
        :param name: The pool name to search for
        :returns: IPPoolResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import IPPool
        
        pool = self._db_session.query(IPPool).filter(IPPool.name == name).first()
        
        if not pool:
            return None
        
        return self._pool_to_response(pool)
    
    def update_pool(self, pool_id: int, request: IPPoolUpdateRequest, user_id: str = None) -> IPPoolResponse:
        """
        Update IP pool settings.
        
        :param pool_id: The pool's unique identifier
        :param request: The update request containing fields to update
        :param user_id: The ID of the user making the update
        :returns: IPPoolResponse with the updated pool data
        :raises IPPoolNotFoundError: If pool is not found
        :raises IPPoolValidationError: If validation fails
        
        Validates: Requirements 2A.4
        """
        from automojo.pychestrate.core.orm import IPPool
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == pool_id).first()
        
        if not pool:
            raise IPPoolNotFoundError(f"IP pool with ID '{pool_id}' not found")
        
        # Update description if provided
        if request.description is not None:
            pool.description = request.description
        
        # Update gateway if provided
        if request.gateway is not None:
            if request.gateway and not is_ip_in_cidr(request.gateway, pool.cidr):
                raise IPPoolValidationError(
                    f"Gateway '{request.gateway}' is not in CIDR range '{pool.cidr}'",
                    field="gateway",
                    error_code="IP_NOT_IN_POOL"
                )
            pool.gateway = request.gateway
        
        # Update DNS servers if provided
        if request.dns_servers is not None:
            for dns in request.dns_servers:
                is_valid, error_msg = validate_ip_address(dns)
                if not is_valid:
                    raise IPPoolValidationError(
                        f"Invalid DNS server '{dns}': {error_msg}",
                        field="dns_servers",
                        error_code="INVALID_DNS_SERVER"
                    )
            pool.dns_servers = request.dns_servers
        
        # Update reserved IPs if provided
        if request.reserved_ips is not None:
            for ip in request.reserved_ips:
                if not is_ip_in_cidr(ip, pool.cidr):
                    raise IPPoolValidationError(
                        f"Reserved IP '{ip}' is not in CIDR range '{pool.cidr}'",
                        field="reserved_ips",
                        error_code="IP_NOT_IN_POOL"
                    )
            pool.reserved_ips = request.reserved_ips
        
        self._db_session.commit()
        
        # Log the pool update event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='ip_pool_updated',
                user_id=str(user_id) if user_id else None,
                details={
                    "pool_id": pool.id,
                    "pool_name": pool.name,
                    "updated_fields": [k for k, v in request.__dict__.items() if v is not None]
                }
            )
        
        return self._pool_to_response(pool)
    
    def delete_pool(self, pool_id: int, user_id: str = None) -> None:
        """
        Delete IP pool. Fails if allocations exist.
        
        :param pool_id: The pool's unique identifier
        :param user_id: The ID of the user deleting the pool
        :raises IPPoolNotFoundError: If pool is not found
        :raises IPPoolHasAllocationsError: If pool has active allocations
        """
        from automojo.pychestrate.core.orm import IPPool, IPAllocation, IPAllocationStatus
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == pool_id).first()
        
        if not pool:
            raise IPPoolNotFoundError(f"IP pool with ID '{pool_id}' not found")
        
        # Check for active allocations
        active_allocations = self._db_session.query(IPAllocation).filter(
            IPAllocation.pool_id == pool_id,
            IPAllocation.status == IPAllocationStatus.ACTIVE.value
        ).count()
        
        if active_allocations > 0:
            raise IPPoolHasAllocationsError(
                f"Cannot delete IP pool '{pool.name}' with {active_allocations} active allocation(s)"
            )
        
        pool_name = pool.name
        
        # Delete the pool
        self._db_session.delete(pool)
        self._db_session.commit()
        
        # Log the pool deletion event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='ip_pool_deleted',
                user_id=str(user_id) if user_id else None,
                details={
                    "pool_id": pool_id,
                    "pool_name": pool_name
                }
            )
    
    def list_pools(self, user_id: str = None, offset: int = 0, limit: int = 50) -> IPPoolListResponse:
        """
        List IP pools the user has access to.
        
        :param user_id: The user's ID (for permission filtering - not implemented yet)
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: IPPoolListResponse with paginated pool list
        """
        from automojo.pychestrate.core.orm import IPPool
        
        query = self._db_session.query(IPPool)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        pools = query.offset(offset).limit(limit).all()
        
        return IPPoolListResponse(
            pools=[self._pool_to_response(pool) for pool in pools],
            total=total,
            offset=offset,
            limit=limit
        )
    
    # =========================================================================
    # Reserved IP Management
    # =========================================================================
    
    def mark_ip_reserved(self, pool_id: int, ip_address: str, reason: str, user_id: str = None) -> None:
        """
        Mark an IP as reserved (excluded from allocation).
        
        :param pool_id: The pool's unique identifier
        :param ip_address: The IP address to mark as reserved
        :param reason: Reason for reserving the IP
        :param user_id: The ID of the user making the reservation
        :raises IPPoolNotFoundError: If pool is not found
        :raises IPNotInPoolError: If IP is not in pool range
        :raises IPNotAvailableError: If IP is already allocated
        
        Validates: Requirements 2A.4
        """
        from automojo.pychestrate.core.orm import IPPool, IPAllocation, IPAllocationStatus
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == pool_id).first()
        
        if not pool:
            raise IPPoolNotFoundError(f"IP pool with ID '{pool_id}' not found")
        
        # Validate IP is in pool range
        if not is_ip_in_cidr(ip_address, pool.cidr):
            raise IPNotInPoolError(
                f"IP address '{ip_address}' is not in pool CIDR range '{pool.cidr}'"
            )
        
        # Check if IP is already allocated
        active_allocation = self._db_session.query(IPAllocation).filter(
            IPAllocation.pool_id == pool_id,
            IPAllocation.ip_address == ip_address,
            IPAllocation.status == IPAllocationStatus.ACTIVE.value
        ).first()
        
        if active_allocation:
            raise IPNotAvailableError(
                f"IP address '{ip_address}' is currently allocated and cannot be reserved"
            )
        
        # Add to reserved list if not already there
        reserved_ips = list(pool.reserved_ips) if pool.reserved_ips else []
        if ip_address not in reserved_ips:
            reserved_ips.append(ip_address)
            pool.reserved_ips = reserved_ips
            self._db_session.commit()
        
        # Log the reservation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='ip_reserved',
                user_id=str(user_id) if user_id else None,
                details={
                    "pool_id": pool_id,
                    "pool_name": pool.name,
                    "ip_address": ip_address,
                    "reason": reason
                }
            )
    
    def unmark_ip_reserved(self, pool_id: int, ip_address: str, user_id: str = None) -> None:
        """
        Remove reserved status from an IP.
        
        :param pool_id: The pool's unique identifier
        :param ip_address: The IP address to unreserve
        :param user_id: The ID of the user making the change
        :raises IPPoolNotFoundError: If pool is not found
        
        Validates: Requirements 2A.4
        """
        from automojo.pychestrate.core.orm import IPPool
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == pool_id).first()
        
        if not pool:
            raise IPPoolNotFoundError(f"IP pool with ID '{pool_id}' not found")
        
        # Remove from reserved list if present
        reserved_ips = list(pool.reserved_ips) if pool.reserved_ips else []
        if ip_address in reserved_ips:
            reserved_ips.remove(ip_address)
            pool.reserved_ips = reserved_ips
            self._db_session.commit()
        
        # Log the unreservation event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='ip_unreserved',
                user_id=str(user_id) if user_id else None,
                details={
                    "pool_id": pool_id,
                    "pool_name": pool.name,
                    "ip_address": ip_address
                }
            )

    
    # =========================================================================
    # IP Availability Methods
    # =========================================================================
    
    def is_ip_available(self, pool_id: int, ip_address: str) -> bool:
        """
        Check if specific IP is available in pool.
        
        :param pool_id: The pool's unique identifier
        :param ip_address: The IP address to check
        :returns: True if IP is available, False otherwise
        """
        from automojo.pychestrate.core.orm import IPPool, IPAllocation, IPAllocationStatus
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == pool_id).first()
        
        if not pool:
            return False
        
        # Check if IP is in pool range
        if not is_ip_in_cidr(ip_address, pool.cidr):
            return False
        
        # Check if IP is reserved
        if pool.reserved_ips and ip_address in pool.reserved_ips:
            return False
        
        # Check if IP is network or broadcast address (for IPv4)
        network = ipaddress.ip_network(pool.cidr, strict=False)
        ip = ipaddress.ip_address(ip_address)
        
        if network.version == 4 and network.prefixlen < 31:
            if ip == network.network_address or ip == network.broadcast_address:
                return False
        
        # Check if IP is already allocated
        active_allocation = self._db_session.query(IPAllocation).filter(
            IPAllocation.pool_id == pool_id,
            IPAllocation.ip_address == ip_address,
            IPAllocation.status == IPAllocationStatus.ACTIVE.value
        ).first()
        
        return active_allocation is None
    
    def get_available_ips(self, pool_id: int, count: int = 10) -> List[str]:
        """
        Get list of available IPs in pool (for preview).
        
        :param pool_id: The pool's unique identifier
        :param count: Maximum number of IPs to return
        :returns: List of available IP address strings
        """
        from automojo.pychestrate.core.orm import IPPool, IPAllocation, IPAllocationStatus
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == pool_id).first()
        
        if not pool:
            return []
        
        # Get all allocated IPs
        allocated_ips = set(
            alloc.ip_address for alloc in self._db_session.query(IPAllocation).filter(
                IPAllocation.pool_id == pool_id,
                IPAllocation.status == IPAllocationStatus.ACTIVE.value
            ).all()
        )
        
        # Get reserved IPs
        reserved_ips = set(pool.reserved_ips) if pool.reserved_ips else set()
        
        # Get usable IPs from CIDR
        network = ipaddress.ip_network(pool.cidr, strict=False)
        available_ips = []
        
        for ip in network.hosts():
            ip_str = str(ip)
            if ip_str not in allocated_ips and ip_str not in reserved_ips:
                available_ips.append(ip_str)
                if len(available_ips) >= count:
                    break
        
        return available_ips
    
    def find_contiguous_block(self, pool_id: int, count: int) -> Optional[Tuple[str, str]]:
        """
        Find a contiguous block of available IPs.
        
        :param pool_id: The pool's unique identifier
        :param count: Number of contiguous IPs needed
        :returns: Tuple of (start_ip, end_ip) or None if not found
        
        Validates: Requirements 3A.2
        """
        from automojo.pychestrate.core.orm import IPPool, IPAllocation, IPAllocationStatus
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == pool_id).first()
        
        if not pool:
            return None
        
        # Get all allocated IPs
        allocated_ips = set(
            alloc.ip_address for alloc in self._db_session.query(IPAllocation).filter(
                IPAllocation.pool_id == pool_id,
                IPAllocation.status == IPAllocationStatus.ACTIVE.value
            ).all()
        )
        
        # Get reserved IPs
        reserved_ips = set(pool.reserved_ips) if pool.reserved_ips else set()
        unavailable = allocated_ips | reserved_ips
        
        # Get all usable IPs in order
        network = ipaddress.ip_network(pool.cidr, strict=False)
        
        contiguous_start = None
        contiguous_count = 0
        
        for ip in network.hosts():
            ip_str = str(ip)
            
            if ip_str not in unavailable:
                if contiguous_start is None:
                    contiguous_start = ip_str
                    contiguous_count = 1
                else:
                    contiguous_count += 1
                
                if contiguous_count >= count:
                    return (contiguous_start, ip_str)
            else:
                contiguous_start = None
                contiguous_count = 0
        
        return None
    
    # =========================================================================
    # IP Checkout Operations
    # =========================================================================
    
    def checkout_ip(self, request: IPAllocationRequest, user_id: str) -> IPAllocationResponse:
        """
        Checkout a single IP address from pool.
        
        :param request: The allocation request
        :param user_id: The ID of the user checking out the IP
        :returns: IPAllocationResponse with the allocation data
        :raises IPPoolNotFoundError: If pool is not found
        :raises IPPoolExhaustedError: If no IPs are available
        :raises IPNotAvailableError: If specific IP is not available
        :raises IPNotInPoolError: If specific IP is not in pool range
        :raises IPReservedError: If specific IP is reserved
        
        Validates: Requirements 3A.1, 3A.3
        """
        from automojo.pychestrate.core.orm import IPPool, IPAllocation, IPAllocationStatus
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == request.pool_id).first()
        
        if not pool:
            raise IPPoolNotFoundError(f"IP pool with ID '{request.pool_id}' not found")
        
        # Determine which IP to allocate
        if request.specific_ip:
            # Validate specific IP is in pool range
            if not is_ip_in_cidr(request.specific_ip, pool.cidr):
                raise IPNotInPoolError(
                    f"IP address '{request.specific_ip}' is not in pool CIDR range '{pool.cidr}'"
                )
            
            # Check if IP is reserved
            if pool.reserved_ips and request.specific_ip in pool.reserved_ips:
                raise IPReservedError(
                    f"IP address '{request.specific_ip}' is reserved"
                )
            
            # Check if IP is available
            if not self.is_ip_available(request.pool_id, request.specific_ip):
                raise IPNotAvailableError(
                    f"IP address '{request.specific_ip}' is not available"
                )
            
            ip_to_allocate = request.specific_ip
        else:
            # Get next available IP
            available_ips = self.get_available_ips(request.pool_id, count=1)
            
            if not available_ips:
                raise IPPoolExhaustedError(
                    f"IP pool '{pool.name}' has no available addresses"
                )
            
            ip_to_allocate = available_ips[0]
        
        # Calculate expected checkin time if timeout specified
        expected_checkin = None
        if request.timeout_minutes:
            expected_checkin = utc_now() + timedelta(minutes=request.timeout_minutes)
        
        # Create the allocation
        now = utc_now()
        
        allocation = IPAllocation(
            pool_id=request.pool_id,
            ip_address=ip_to_allocate,
            user_id=user_id,
            job_id=request.job_id,
            status=IPAllocationStatus.ACTIVE.value,
            checkout_time=now,
            expected_checkin=expected_checkin,
            reason=request.reason
        )
        
        self._db_session.add(allocation)
        self._db_session.commit()
        
        # Log the checkout event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='ip_checkout',
                user_id=str(user_id) if user_id else None,
                details={
                    "allocation_id": allocation.id,
                    "pool_id": pool.id,
                    "pool_name": pool.name,
                    "ip_address": ip_to_allocate,
                    "job_id": request.job_id
                }
            )
        
        return self._allocation_to_response(allocation, pool)
    
    def checkout_ips(self, request: IPAllocationRequest, user_id: str) -> IPBulkAllocationResponse:
        """
        Checkout multiple IP addresses from pool.
        
        :param request: The allocation request with count > 1
        :param user_id: The ID of the user checking out the IPs
        :returns: IPBulkAllocationResponse with the allocation data
        :raises IPPoolNotFoundError: If pool is not found
        :raises IPPoolExhaustedError: If not enough IPs are available
        
        Validates: Requirements 3A.1, 3A.2
        """
        from automojo.pychestrate.core.orm import IPPool, IPAllocation, IPAllocationStatus
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == request.pool_id).first()
        
        if not pool:
            raise IPPoolNotFoundError(f"IP pool with ID '{request.pool_id}' not found")
        
        count = request.count
        if count < 1:
            count = 1
        
        # Try to find contiguous block if preferred
        contiguous = False
        ips_to_allocate = []
        
        if request.prefer_contiguous and count > 1:
            contiguous_block = self.find_contiguous_block(request.pool_id, count)
            if contiguous_block:
                start_ip, end_ip = contiguous_block
                # Get all IPs in the contiguous range
                network = ipaddress.ip_network(pool.cidr, strict=False)
                start = ipaddress.ip_address(start_ip)
                end = ipaddress.ip_address(end_ip)
                
                for ip in network.hosts():
                    if ip >= start and ip <= end:
                        ips_to_allocate.append(str(ip))
                        if len(ips_to_allocate) >= count:
                            break
                
                contiguous = True
        
        # If no contiguous block found or not preferred, get individual IPs
        if not ips_to_allocate:
            available_ips = self.get_available_ips(request.pool_id, count=count)
            
            if len(available_ips) < count:
                raise IPPoolExhaustedError(
                    f"IP pool '{pool.name}' has only {len(available_ips)} available addresses, "
                    f"but {count} were requested"
                )
            
            ips_to_allocate = available_ips[:count]
        
        # Calculate expected checkin time if timeout specified
        expected_checkin = None
        if request.timeout_minutes:
            expected_checkin = utc_now() + timedelta(minutes=request.timeout_minutes)
        
        # Create allocations
        now = utc_now()
        allocations = []
        
        for ip in ips_to_allocate:
            allocation = IPAllocation(
                pool_id=request.pool_id,
                ip_address=ip,
                user_id=user_id,
                job_id=request.job_id,
                status=IPAllocationStatus.ACTIVE.value,
                checkout_time=now,
                expected_checkin=expected_checkin,
                reason=request.reason
            )
            self._db_session.add(allocation)
            allocations.append(allocation)
        
        self._db_session.commit()
        
        # Log the bulk checkout event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='ip_bulk_checkout',
                user_id=str(user_id) if user_id else None,
                details={
                    "pool_id": pool.id,
                    "pool_name": pool.name,
                    "ip_count": len(allocations),
                    "contiguous": contiguous,
                    "job_id": request.job_id
                }
            )
        
        return IPBulkAllocationResponse(
            allocations=[self._allocation_to_response(alloc, pool) for alloc in allocations],
            contiguous=contiguous,
            start_ip=ips_to_allocate[0],
            end_ip=ips_to_allocate[-1]
        )
    
    # =========================================================================
    # IP Checkin Operations
    # =========================================================================
    
    def checkin_ip(self, allocation_id: int, user_id: str) -> None:
        """
        Release a single IP allocation.
        
        :param allocation_id: The allocation's unique identifier
        :param user_id: The ID of the user checking in the IP
        :raises IPAllocationNotFoundError: If allocation is not found
        :raises NotIPAllocationOwnerError: If user is not the owner
        
        Validates: Requirements 4A.1
        """
        from automojo.pychestrate.core.orm import IPAllocation, IPAllocationStatus
        
        allocation = self._db_session.query(IPAllocation).filter(
            IPAllocation.id == allocation_id
        ).first()
        
        if not allocation:
            raise IPAllocationNotFoundError(f"IP allocation with ID '{allocation_id}' not found")
        
        # Check ownership
        if str(allocation.user_id) != str(user_id):
            raise NotIPAllocationOwnerError(
                f"User '{user_id}' is not the owner of allocation '{allocation_id}'"
            )
        
        # Check if already released
        if allocation.status != IPAllocationStatus.ACTIVE.value:
            return  # Already released, nothing to do
        
        # Release the allocation
        allocation.status = IPAllocationStatus.RELEASED.value
        allocation.actual_checkin = utc_now()
        
        self._db_session.commit()
        
        # Log the checkin event
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='ip_checkin',
                user_id=str(user_id) if user_id else None,
                details={
                    "allocation_id": allocation.id,
                    "pool_id": allocation.pool_id,
                    "ip_address": allocation.ip_address
                }
            )
    
    def checkin_ips(self, allocation_ids: List[int], user_id: str) -> int:
        """
        Release multiple IP allocations.
        
        :param allocation_ids: List of allocation IDs to release
        :param user_id: The ID of the user checking in the IPs
        :returns: Count of allocations released
        
        Validates: Requirements 4A.2
        """
        from automojo.pychestrate.core.orm import IPAllocation, IPAllocationStatus
        
        released_count = 0
        now = utc_now()
        
        for allocation_id in allocation_ids:
            allocation = self._db_session.query(IPAllocation).filter(
                IPAllocation.id == allocation_id,
                IPAllocation.user_id == user_id,
                IPAllocation.status == IPAllocationStatus.ACTIVE.value
            ).first()
            
            if allocation:
                allocation.status = IPAllocationStatus.RELEASED.value
                allocation.actual_checkin = now
                released_count += 1
        
        self._db_session.commit()
        
        # Log the bulk checkin event
        if self._audit_logger and released_count > 0:
            self._audit_logger.log_event(
                event_type='ip_bulk_checkin',
                user_id=str(user_id) if user_id else None,
                details={
                    "released_count": released_count,
                    "requested_count": len(allocation_ids)
                }
            )
        
        return released_count
    
    def checkin_job_ips(self, job_id: str, user_id: str) -> int:
        """
        Release all IPs allocated to a job.
        
        :param job_id: The job identifier
        :param user_id: The ID of the user checking in the IPs
        :returns: Count of allocations released
        
        Validates: Requirements 4A.3
        """
        from automojo.pychestrate.core.orm import IPAllocation, IPAllocationStatus
        
        now = utc_now()
        
        allocations = self._db_session.query(IPAllocation).filter(
            IPAllocation.job_id == job_id,
            IPAllocation.status == IPAllocationStatus.ACTIVE.value
        ).all()
        
        released_count = 0
        for allocation in allocations:
            allocation.status = IPAllocationStatus.RELEASED.value
            allocation.actual_checkin = now
            released_count += 1
        
        self._db_session.commit()
        
        # Log the job checkin event
        if self._audit_logger and released_count > 0:
            self._audit_logger.log_event(
                event_type='ip_job_checkin',
                user_id=str(user_id) if user_id else None,
                details={
                    "job_id": job_id,
                    "released_count": released_count
                }
            )
        
        return released_count
    
    # =========================================================================
    # Allocation Query Methods
    # =========================================================================
    
    def get_allocation(self, allocation_id: int) -> Optional[IPAllocationResponse]:
        """
        Get IP allocation details.
        
        :param allocation_id: The allocation's unique identifier
        :returns: IPAllocationResponse if found, None otherwise
        """
        from automojo.pychestrate.core.orm import IPAllocation, IPPool
        
        allocation = self._db_session.query(IPAllocation).filter(
            IPAllocation.id == allocation_id
        ).first()
        
        if not allocation:
            return None
        
        pool = self._db_session.query(IPPool).filter(IPPool.id == allocation.pool_id).first()
        
        return self._allocation_to_response(allocation, pool)
    
    def list_allocations(
        self,
        pool_id: int = None,
        user_id: str = None,
        job_id: str = None,
        status: str = None,
        offset: int = 0,
        limit: int = 50
    ) -> IPAllocationListResponse:
        """
        List IP allocations with filtering.
        
        :param pool_id: Optional pool ID to filter by
        :param user_id: Optional user ID to filter by
        :param job_id: Optional job ID to filter by
        :param status: Optional status to filter by
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: IPAllocationListResponse with paginated allocation list
        """
        from automojo.pychestrate.core.orm import IPAllocation, IPPool
        
        query = self._db_session.query(IPAllocation)
        
        if pool_id is not None:
            query = query.filter(IPAllocation.pool_id == pool_id)
        
        if user_id is not None:
            query = query.filter(IPAllocation.user_id == user_id)
        
        if job_id is not None:
            query = query.filter(IPAllocation.job_id == job_id)
        
        if status is not None:
            query = query.filter(IPAllocation.status == status)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        allocations = query.offset(offset).limit(limit).all()
        
        # Get pools for response building
        pool_cache = {}
        responses = []
        for allocation in allocations:
            if allocation.pool_id not in pool_cache:
                pool_cache[allocation.pool_id] = self._db_session.query(IPPool).filter(
                    IPPool.id == allocation.pool_id
                ).first()
            responses.append(self._allocation_to_response(allocation, pool_cache[allocation.pool_id]))
        
        return IPAllocationListResponse(
            allocations=responses,
            total=total,
            offset=offset,
            limit=limit
        )
    
    # =========================================================================
    # Timeout Handling
    # =========================================================================
    
    def expire_timed_out_allocations(self) -> int:
        """
        Release IP allocations that have exceeded timeout.
        
        :returns: Count of allocations expired
        """
        from automojo.pychestrate.core.orm import IPAllocation, IPAllocationStatus
        
        now = utc_now()
        
        expired_allocations = self._db_session.query(IPAllocation).filter(
            IPAllocation.status == IPAllocationStatus.ACTIVE.value,
            IPAllocation.expected_checkin != None,
            IPAllocation.expected_checkin < now
        ).all()
        
        expired_count = 0
        for allocation in expired_allocations:
            allocation.status = IPAllocationStatus.EXPIRED.value
            allocation.actual_checkin = now
            expired_count += 1
        
        self._db_session.commit()
        
        # Log the expiration event
        if self._audit_logger and expired_count > 0:
            self._audit_logger.log_event(
                event_type='ip_allocations_expired',
                user_id=None,
                details={
                    "expired_count": expired_count
                }
            )
        
        return expired_count
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _pool_to_response(self, pool) -> IPPoolResponse:
        """
        Convert an IPPool ORM object to an IPPoolResponse dataclass.
        
        :param pool: The IPPool ORM object
        :returns: IPPoolResponse dataclass
        """
        stats = self.calculate_pool_stats(pool.id)
        created_by = str(pool.created_by_id) if pool.created_by_id else None
        
        return IPPoolResponse(
            id=pool.id,
            name=pool.name,
            cidr=pool.cidr,
            ip_version=pool.ip_version,
            network_address=pool.network_address,
            broadcast_address=pool.broadcast_address,
            subnet_mask=pool.subnet_mask,
            gateway=pool.gateway,
            dns_servers=pool.dns_servers or [],
            description=pool.description or "",
            total_addresses=stats["total_addresses"],
            reserved_count=stats["reserved_count"],
            allocated_count=stats["allocated_count"],
            available_count=stats["available_count"],
            created_at=pool.created_at,
            created_by=created_by
        )
    
    def _allocation_to_response(self, allocation, pool) -> IPAllocationResponse:
        """
        Convert an IPAllocation ORM object to an IPAllocationResponse dataclass.
        
        :param allocation: The IPAllocation ORM object
        :param pool: The IPPool ORM object
        :returns: IPAllocationResponse dataclass
        """
        return IPAllocationResponse(
            id=allocation.id,
            pool_id=allocation.pool_id,
            pool_name=pool.name if pool else "",
            ip_address=allocation.ip_address,
            subnet_mask=pool.subnet_mask if pool else "",
            gateway=pool.gateway if pool else None,
            dns_servers=pool.dns_servers if pool else [],
            user_id=str(allocation.user_id),
            username=None,  # Would need to join with User table
            job_id=allocation.job_id,
            status=allocation.status,
            checkout_time=allocation.checkout_time,
            expected_checkin=allocation.expected_checkin
        )
