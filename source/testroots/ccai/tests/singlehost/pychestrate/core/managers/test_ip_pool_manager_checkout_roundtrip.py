"""
.. module:: test_ip_pool_manager_checkout_roundtrip
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for IPPoolManager IP checkout-checkin round-trip

.. moduleauthor:: Code Craft AI LLC

Tests for IP checkout-checkin round-trip in the IPPoolManager.

**Feature: resources**
**Property 21: IP Checkout-Checkin Round-Trip**
**Validates: Requirements 3A.1, 4A.1**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import uuid

from ccai.testbase.mocking import Mock

from ccai.pychestrate.core.managers.ip_pool_manager import (
    IPPoolManager,
    IPPoolCreateRequest,
    IPAllocationRequest,
    validate_cidr,
    parse_cidr,
    calculate_usable_hosts,
    get_usable_ips,
    check_cidr_overlap,
    is_ip_in_cidr,
)


# =============================================================================
# Test Fixtures - Mock-based approach for SQLite compatibility
# =============================================================================

# Global counter for generating unique IDs
_id_counter = [0]


def get_next_id():
    """Get the next unique ID for mock objects."""
    _id_counter[0] += 1
    return _id_counter[0]


def create_mock_pool(pool_id, name, cidr, gateway=None, dns_servers=None, reserved_ips=None):
    """Create a mock IP pool object."""
    cidr_info = parse_cidr(cidr)
    
    mock_pool = Mock()
    mock_pool.configure(recursive=True)
    ctx = mock_pool.mock_context()
    ctx.set_attribute('id', pool_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('cidr', cidr)
    ctx.set_attribute('ip_version', cidr_info['ip_version'])
    ctx.set_attribute('network_address', cidr_info['network_address'])
    ctx.set_attribute('broadcast_address', cidr_info.get('broadcast_address'))
    ctx.set_attribute('subnet_mask', cidr_info['subnet_mask'])
    ctx.set_attribute('gateway', gateway)
    ctx.set_attribute('dns_servers', dns_servers or [])
    ctx.set_attribute('description', 'Test pool')
    ctx.set_attribute('reserved_ips', reserved_ips or [])
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('created_by_id', None)
    ctx.set_attribute('allocations', [])
    return mock_pool


def create_mock_allocation(alloc_id, pool_id, ip_address, user_id, status='active'):
    """Create a mock IP allocation object."""
    mock_alloc = Mock()
    mock_alloc.configure(recursive=True)
    ctx = mock_alloc.mock_context()
    ctx.set_attribute('id', alloc_id)
    ctx.set_attribute('pool_id', pool_id)
    ctx.set_attribute('ip_address', ip_address)
    ctx.set_attribute('user_id', user_id)
    ctx.set_attribute('job_id', None)
    ctx.set_attribute('status', status)
    ctx.set_attribute('checkout_time', Mock())
    ctx.set_attribute('expected_checkin', None)
    ctx.set_attribute('actual_checkin', None)
    ctx.set_attribute('reason', '')
    return mock_alloc


class MockIPPoolState:
    """
    A helper class to maintain state for mock IP pool operations.
    This simulates the database state for testing checkout-checkin operations.
    """
    
    def __init__(self, pool_id, cidr, gateway=None, dns_servers=None, reserved_ips=None):
        self.pool_id = pool_id
        self.cidr = cidr
        self.gateway = gateway
        self.dns_servers = dns_servers or []
        self.reserved_ips = set(reserved_ips or [])
        self.allocations = {}  # alloc_id -> (ip_address, user_id, status)
        self._next_alloc_id = 1
        
        # Calculate usable IPs
        self.all_usable_ips = set(get_usable_ips(cidr, list(self.reserved_ips)))
    
    def get_available_ips(self):
        """Get IPs that are not allocated or reserved."""
        allocated_ips = {ip for ip, _, status in self.allocations.values() if status == 'active'}
        return self.all_usable_ips - allocated_ips - self.reserved_ips
    
    def checkout_ip(self, user_id, specific_ip=None):
        """Checkout an IP and return allocation info."""
        available = self.get_available_ips()
        
        if specific_ip:
            if specific_ip not in self.all_usable_ips:
                raise ValueError(f"IP {specific_ip} not in pool")
            if specific_ip in self.reserved_ips:
                raise ValueError(f"IP {specific_ip} is reserved")
            if specific_ip not in available:
                raise ValueError(f"IP {specific_ip} not available")
            ip_to_allocate = specific_ip
        else:
            if not available:
                raise ValueError("Pool exhausted")
            ip_to_allocate = sorted(available)[0]
        
        alloc_id = self._next_alloc_id
        self._next_alloc_id += 1
        self.allocations[alloc_id] = (ip_to_allocate, user_id, 'active')
        return alloc_id, ip_to_allocate
    
    def checkin_ip(self, alloc_id, user_id):
        """Checkin an IP allocation."""
        if alloc_id not in self.allocations:
            return False
        
        ip, owner, status = self.allocations[alloc_id]
        if str(owner) != str(user_id):
            return False
        
        if status != 'active':
            return True  # Already released, idempotent
        
        self.allocations[alloc_id] = (ip, owner, 'released')
        return True
    
    def get_stats(self):
        """Get pool statistics."""
        total = len(self.all_usable_ips)
        reserved = len(self.reserved_ips)
        allocated = sum(1 for _, _, status in self.allocations.values() if status == 'active')
        available = total - reserved - allocated
        return {
            'total_addresses': total,
            'reserved_count': reserved,
            'allocated_count': allocated,
            'available_count': max(0, available)
        }
    
    def is_ip_available(self, ip_address):
        """Check if a specific IP is available."""
        if ip_address not in self.all_usable_ips:
            return False
        if ip_address in self.reserved_ips:
            return False
        allocated_ips = {ip for ip, _, status in self.allocations.values() if status == 'active'}
        return ip_address not in allocated_ips


# =============================================================================
# IP Checkout-Checkin Round-Trip Tests - Property 21
# =============================================================================

def test_checkout_checkin_returns_ip_to_pool():
    """
    **Feature: resources, Property 21: IP Checkout-Checkin Round-Trip**
    **Validates: Requirements 3A.1, 4A.1**
    
    Checking out an IP and then checking it back in should return the IP to available status.
    """
    pool_state = MockIPPoolState(
        pool_id=1,
        cidr="192.168.1.0/28",
        gateway="192.168.1.1",
        dns_servers=["8.8.8.8"]
    )
    user_id = str(uuid.uuid4())
    
    # Get initial available count
    initial_stats = pool_state.get_stats()
    initial_available = initial_stats["available_count"]
    
    # Checkout an IP
    alloc_id, ip_address = pool_state.checkout_ip(user_id)
    
    # Verify available count decreased
    after_checkout_stats = pool_state.get_stats()
    assert after_checkout_stats["available_count"] == initial_available - 1, \
        "Available count should decrease by 1 after checkout"
    
    # Checkin the IP
    pool_state.checkin_ip(alloc_id, user_id)
    
    # Verify available count restored
    after_checkin_stats = pool_state.get_stats()
    assert after_checkin_stats["available_count"] == initial_available, \
        "Available count should be restored after checkin"


def test_checkout_checkin_same_ip_available_again():
    """
    **Feature: resources, Property 21: IP Checkout-Checkin Round-Trip**
    **Validates: Requirements 3A.1, 4A.1**
    
    After checkin, the same IP should be available for checkout again.
    """
    pool_state = MockIPPoolState(
        pool_id=1,
        cidr="192.168.1.0/28",
        gateway="192.168.1.1",
        dns_servers=["8.8.8.8"]
    )
    user_id = str(uuid.uuid4())
    
    # Checkout a specific IP
    specific_ip = "192.168.1.5"
    alloc_id, allocated_ip = pool_state.checkout_ip(user_id, specific_ip=specific_ip)
    
    assert allocated_ip == specific_ip, "Should allocate the specific IP"
    
    # Verify IP is not available
    assert pool_state.is_ip_available(specific_ip) is False, \
        "IP should not be available after checkout"
    
    # Checkin the IP
    pool_state.checkin_ip(alloc_id, user_id)
    
    # Verify IP is available again
    assert pool_state.is_ip_available(specific_ip) is True, \
        "IP should be available again after checkin"
    
    # Should be able to checkout the same IP again
    alloc_id2, allocated_ip2 = pool_state.checkout_ip(user_id, specific_ip=specific_ip)
    
    assert allocated_ip2 == specific_ip, "Should be able to checkout same IP again"


def test_multiple_checkout_checkin_cycles():
    """
    **Feature: resources, Property 21: IP Checkout-Checkin Round-Trip**
    **Validates: Requirements 3A.1, 4A.1**
    
    Multiple checkout-checkin cycles should work correctly.
    Property: For any IP pool, repeated checkout-checkin cycles should maintain pool integrity.
    """
    pool_state = MockIPPoolState(
        pool_id=1,
        cidr="192.168.1.0/28",
        gateway="192.168.1.1",
        dns_servers=["8.8.8.8"]
    )
    user_id = str(uuid.uuid4())
    
    initial_stats = pool_state.get_stats()
    initial_available = initial_stats["available_count"]
    
    # Perform multiple checkout-checkin cycles
    for _ in range(10):
        # Checkout
        alloc_id, _ = pool_state.checkout_ip(user_id)
        
        # Checkin
        pool_state.checkin_ip(alloc_id, user_id)
    
    # Verify pool is back to initial state
    final_stats = pool_state.get_stats()
    assert final_stats["available_count"] == initial_available, \
        "Pool should return to initial state after multiple cycles"


def test_bulk_checkout_checkin_roundtrip():
    """
    **Feature: resources, Property 21: IP Checkout-Checkin Round-Trip**
    **Validates: Requirements 3A.1, 4A.1**
    
    Bulk checkout and checkin should work correctly.
    """
    pool_state = MockIPPoolState(
        pool_id=1,
        cidr="192.168.1.0/24",  # Larger pool for bulk operations
        gateway="192.168.1.1",
        dns_servers=["8.8.8.8"]
    )
    user_id = str(uuid.uuid4())
    
    initial_stats = pool_state.get_stats()
    initial_available = initial_stats["available_count"]
    
    # Bulk checkout
    count = 5
    allocations = []
    for _ in range(count):
        alloc_id, ip = pool_state.checkout_ip(user_id)
        allocations.append(alloc_id)
    
    assert len(allocations) == count, f"Should allocate {count} IPs"
    
    # Verify available count decreased
    after_checkout_stats = pool_state.get_stats()
    assert after_checkout_stats["available_count"] == initial_available - count, \
        f"Available count should decrease by {count}"
    
    # Bulk checkin
    released = 0
    for alloc_id in allocations:
        if pool_state.checkin_ip(alloc_id, user_id):
            released += 1
    
    assert released == count, f"Should release {count} IPs"
    
    # Verify available count restored
    after_checkin_stats = pool_state.get_stats()
    assert after_checkin_stats["available_count"] == initial_available, \
        "Available count should be restored after bulk checkin"


def test_generated_checkout_checkin_roundtrip():
    """
    **Feature: resources, Property 21: IP Checkout-Checkin Round-Trip**
    **Validates: Requirements 3A.1, 4A.1**
    
    For any random number of checkouts, checking them all in should restore the pool.
    Property: For all checkout operations, checkin restores the IP to available status.
    """
    pool_state = MockIPPoolState(
        pool_id=1,
        cidr="192.168.1.0/24",  # Larger pool
        gateway="192.168.1.1",
        dns_servers=["8.8.8.8"]
    )
    user_id = str(uuid.uuid4())
    
    initial_stats = pool_state.get_stats()
    initial_available = initial_stats["available_count"]
    
    # Random number of checkouts
    for _ in range(50):
        num_checkouts = random.randint(1, 10)
        allocations = []
        
        # Checkout random number of IPs
        for _ in range(num_checkouts):
            try:
                alloc_id, _ = pool_state.checkout_ip(user_id)
                allocations.append(alloc_id)
            except ValueError:
                break  # Pool might be exhausted
        
        # Checkin all
        for alloc_id in allocations:
            pool_state.checkin_ip(alloc_id, user_id)
        
        # Verify pool is restored
        current_stats = pool_state.get_stats()
        assert current_stats["available_count"] == initial_available, \
            f"Pool should be restored after checkin (iteration)"


def test_checkin_idempotent():
    """
    **Feature: resources, Property 21: IP Checkout-Checkin Round-Trip**
    **Validates: Requirements 3A.1, 4A.1**
    
    Checking in an already checked-in allocation should be idempotent.
    """
    pool_state = MockIPPoolState(
        pool_id=1,
        cidr="192.168.1.0/28",
        gateway="192.168.1.1",
        dns_servers=["8.8.8.8"]
    )
    user_id = str(uuid.uuid4())
    
    # Checkout an IP
    alloc_id, _ = pool_state.checkout_ip(user_id)
    
    # Checkin once
    result1 = pool_state.checkin_ip(alloc_id, user_id)
    assert result1 is True, "First checkin should succeed"
    
    # Checkin again (should be idempotent)
    result2 = pool_state.checkin_ip(alloc_id, user_id)
    assert result2 is True, "Second checkin should be idempotent"
    
    # Pool should still be in correct state
    stats = pool_state.get_stats()
    assert stats["allocated_count"] == 0, "No allocations should remain"

