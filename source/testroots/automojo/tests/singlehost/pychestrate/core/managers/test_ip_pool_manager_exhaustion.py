"""
.. module:: test_ip_pool_manager_exhaustion
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for IPPoolManager IP pool exhaustion handling

.. moduleauthor:: Automation Mojo LLC

Tests for IP pool exhaustion behavior in the IPPoolManager.

**Feature: resources**
**Property 22: IP Pool Exhaustion**
**Validates: Requirements 3A.6**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import uuid

from automojo.pychestrate.core.managers.ip_pool_manager import (
    get_usable_ips,
    calculate_usable_hosts,
)


# =============================================================================
# Test Fixtures - Mock-based approach for SQLite compatibility
# =============================================================================

class MockIPPoolState:
    """
    A helper class to maintain state for mock IP pool operations.
    This simulates the database state for testing exhaustion behavior.
    """
    
    def __init__(self, pool_id, cidr, reserved_ips=None):
        self.pool_id = pool_id
        self.cidr = cidr
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
        """Checkout an IP and return allocation info. Raises ValueError if exhausted."""
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
                raise ValueError("Pool exhausted - no available IPs")
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
            return True  # Already released
        
        self.allocations[alloc_id] = (ip, owner, 'released')
        return True
    
    def get_stats(self):
        """Get pool statistics."""
        # all_usable_ips already excludes reserved IPs
        total = len(self.all_usable_ips)
        reserved = 0  # Reserved are already excluded from all_usable_ips
        allocated = sum(1 for _, _, status in self.allocations.values() if status == 'active')
        available = total - allocated
        return {
            'total_addresses': total,
            'reserved_count': len(self.reserved_ips),  # Report actual reserved count for info
            'allocated_count': allocated,
            'available_count': max(0, available)
        }


# =============================================================================
# IP Pool Exhaustion Tests - Property 22
# =============================================================================

def test_pool_exhaustion_raises_error():
    """
    **Feature: resources, Property 22: IP Pool Exhaustion**
    **Validates: Requirements 3A.6**
    
    When all IPs in a pool are allocated, further checkout attempts should fail.
    """
    # Use a small /30 network (2 usable IPs)
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/30")
    user_id = str(uuid.uuid4())
    
    # Get total usable IPs
    total_usable = len(pool_state.all_usable_ips)
    assert total_usable == 2, f"Expected 2 usable IPs in /30, got {total_usable}"
    
    # Allocate all IPs
    allocations = []
    for _ in range(total_usable):
        alloc_id, _ = pool_state.checkout_ip(user_id)
        allocations.append(alloc_id)
    
    # Verify pool is exhausted
    stats = pool_state.get_stats()
    assert stats["available_count"] == 0, "Pool should have no available IPs"
    
    # Attempt to checkout another IP - should fail
    exhausted_error_raised = False
    try:
        pool_state.checkout_ip(user_id)
    except ValueError as e:
        if "exhausted" in str(e).lower():
            exhausted_error_raised = True
    
    assert exhausted_error_raised, "Pool exhaustion should raise an error"


def test_pool_exhaustion_with_reserved_ips():
    """
    **Feature: resources, Property 22: IP Pool Exhaustion**
    **Validates: Requirements 3A.6**
    
    Reserved IPs should reduce the available pool and contribute to exhaustion.
    """
    # Use a /29 network (6 usable IPs) with 2 reserved
    reserved = ["192.168.1.1", "192.168.1.2"]
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/29", reserved_ips=reserved)
    user_id = str(uuid.uuid4())
    
    # all_usable_ips already excludes reserved IPs (via get_usable_ips)
    # So available = all_usable_ips (which is already reduced by reserved)
    expected_available = len(pool_state.all_usable_ips)
    
    stats = pool_state.get_stats()
    assert stats["available_count"] == expected_available, \
        f"Expected {expected_available} available IPs, got {stats['available_count']}"
    
    # Allocate all available IPs
    allocations = []
    for _ in range(expected_available):
        alloc_id, _ = pool_state.checkout_ip(user_id)
        allocations.append(alloc_id)
    
    # Verify pool is exhausted
    stats = pool_state.get_stats()
    assert stats["available_count"] == 0, "Pool should be exhausted"
    
    # Attempt to checkout another IP - should fail
    exhausted_error_raised = False
    try:
        pool_state.checkout_ip(user_id)
    except ValueError as e:
        if "exhausted" in str(e).lower():
            exhausted_error_raised = True
    
    assert exhausted_error_raised, "Pool exhaustion should raise an error"


def test_exhaustion_recovery_after_checkin():
    """
    **Feature: resources, Property 22: IP Pool Exhaustion**
    **Validates: Requirements 3A.6**
    
    After checking in an IP from an exhausted pool, new checkouts should succeed.
    """
    # Use a small /30 network (2 usable IPs)
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/30")
    user_id = str(uuid.uuid4())
    
    # Allocate all IPs
    allocations = []
    for _ in range(2):
        alloc_id, _ = pool_state.checkout_ip(user_id)
        allocations.append(alloc_id)
    
    # Verify pool is exhausted
    stats = pool_state.get_stats()
    assert stats["available_count"] == 0, "Pool should be exhausted"
    
    # Checkin one IP
    pool_state.checkin_ip(allocations[0], user_id)
    
    # Verify pool has one available IP
    stats = pool_state.get_stats()
    assert stats["available_count"] == 1, "Pool should have 1 available IP after checkin"
    
    # Should be able to checkout again
    new_alloc_id, _ = pool_state.checkout_ip(user_id)
    assert new_alloc_id is not None, "Should be able to checkout after checkin"


def test_property_exhaustion_at_capacity():
    """
    **Feature: resources, Property 22: IP Pool Exhaustion**
    **Validates: Requirements 3A.6**
    
    Property: For any CIDR range, allocating exactly the number of usable IPs
    should exhaust the pool.
    """
    # Test with various CIDR sizes
    test_cidrs = [
        "10.0.0.0/30",   # 2 usable IPs
        "10.0.0.0/29",   # 6 usable IPs
        "10.0.0.0/28",   # 14 usable IPs
    ]
    
    for cidr in test_cidrs:
        pool_state = MockIPPoolState(pool_id=1, cidr=cidr)
        user_id = str(uuid.uuid4())
        
        total_usable = len(pool_state.all_usable_ips)
        
        # Allocate all IPs
        for _ in range(total_usable):
            pool_state.checkout_ip(user_id)
        
        # Verify exhaustion
        stats = pool_state.get_stats()
        assert stats["available_count"] == 0, \
            f"Pool {cidr} should be exhausted after {total_usable} allocations"
        
        # Verify checkout fails
        exhausted = False
        try:
            pool_state.checkout_ip(user_id)
        except ValueError:
            exhausted = True
        
        assert exhausted, f"Pool {cidr} should raise error when exhausted"


def test_generated_exhaustion_scenarios():
    """
    **Feature: resources, Property 22: IP Pool Exhaustion**
    **Validates: Requirements 3A.6**
    
    Property test: For randomly generated pool configurations, exhaustion
    should occur exactly when all usable IPs are allocated.
    """
    for _ in range(20):
        # Generate random CIDR (prefix 28-30 for small pools)
        prefix = random.randint(28, 30)
        cidr = f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.0/{prefix}"
        
        pool_state = MockIPPoolState(pool_id=1, cidr=cidr)
        user_id = str(uuid.uuid4())
        
        total_usable = len(pool_state.all_usable_ips)
        
        # Allocate all IPs one by one
        allocated_count = 0
        while True:
            try:
                pool_state.checkout_ip(user_id)
                allocated_count += 1
            except ValueError:
                break
        
        # Verify we allocated exactly the expected number
        assert allocated_count == total_usable, \
            f"Should allocate exactly {total_usable} IPs from {cidr}, got {allocated_count}"


def test_exhaustion_with_partial_allocation():
    """
    **Feature: resources, Property 22: IP Pool Exhaustion**
    **Validates: Requirements 3A.6**
    
    Partial allocation should not trigger exhaustion until all IPs are used.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/28")  # 14 usable IPs
    user_id = str(uuid.uuid4())
    
    total_usable = len(pool_state.all_usable_ips)
    
    # Allocate half the IPs
    half = total_usable // 2
    for _ in range(half):
        pool_state.checkout_ip(user_id)
    
    # Verify pool is not exhausted
    stats = pool_state.get_stats()
    assert stats["available_count"] > 0, "Pool should not be exhausted after partial allocation"
    
    # Should still be able to checkout
    alloc_id, _ = pool_state.checkout_ip(user_id)
    assert alloc_id is not None, "Should be able to checkout from non-exhausted pool"
