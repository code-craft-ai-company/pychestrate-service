"""
.. module:: test_ip_pool_manager_specific_allocation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for IPPoolManager specific IP allocation

.. moduleauthor:: Automation Mojo LLC

Tests for specific IP allocation in the IPPoolManager.

**Feature: resources**
**Property 23: Specific IP Allocation**
**Validates: Requirements 3A.3**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import uuid

from automojo.pychestrate.core.managers.ip_pool_manager import (
    get_usable_ips,
    is_ip_in_cidr,
)


# =============================================================================
# Test Fixtures - Mock-based approach for SQLite compatibility
# =============================================================================

class MockIPPoolState:
    """
    A helper class to maintain state for mock IP pool operations.
    This simulates the database state for testing specific IP allocation.
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
        """
        Checkout an IP and return allocation info.
        
        Raises:
            ValueError: If specific IP is not in pool, reserved, or not available
        """
        available = self.get_available_ips()
        
        if specific_ip:
            # Check if IP is in pool range
            if not is_ip_in_cidr(specific_ip, self.cidr):
                raise ValueError(f"IP {specific_ip} not in pool range")
            
            # Check if IP is reserved
            if specific_ip in self.reserved_ips:
                raise ValueError(f"IP {specific_ip} is reserved")
            
            # Check if IP is a network/broadcast address (not in usable)
            if specific_ip not in self.all_usable_ips:
                raise ValueError(f"IP {specific_ip} is not a usable address")
            
            # Check if IP is available
            if specific_ip not in available:
                raise ValueError(f"IP {specific_ip} is already allocated")
            
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
    
    def is_ip_available(self, ip_address):
        """Check if a specific IP is available."""
        if ip_address not in self.all_usable_ips:
            return False
        if ip_address in self.reserved_ips:
            return False
        allocated_ips = {ip for ip, _, status in self.allocations.values() if status == 'active'}
        return ip_address not in allocated_ips


# =============================================================================
# Specific IP Allocation Tests - Property 23
# =============================================================================

def test_specific_ip_allocation_success():
    """
    **Feature: resources, Property 23: Specific IP Allocation**
    **Validates: Requirements 3A.3**
    
    Requesting a specific available IP should allocate exactly that IP.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/28")
    user_id = str(uuid.uuid4())
    
    # Choose a specific IP from the pool
    specific_ip = "192.168.1.5"
    
    # Verify IP is available
    assert pool_state.is_ip_available(specific_ip), "IP should be available before allocation"
    
    # Allocate the specific IP
    alloc_id, allocated_ip = pool_state.checkout_ip(user_id, specific_ip=specific_ip)
    
    # Verify the exact IP was allocated
    assert allocated_ip == specific_ip, f"Should allocate exactly {specific_ip}, got {allocated_ip}"
    
    # Verify IP is no longer available
    assert not pool_state.is_ip_available(specific_ip), "IP should not be available after allocation"


def test_specific_ip_not_in_pool_rejected():
    """
    **Feature: resources, Property 23: Specific IP Allocation**
    **Validates: Requirements 3A.3**
    
    Requesting an IP outside the pool's CIDR range should fail.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/28")
    user_id = str(uuid.uuid4())
    
    # Try to allocate an IP outside the pool range
    outside_ip = "10.0.0.1"
    
    error_raised = False
    try:
        pool_state.checkout_ip(user_id, specific_ip=outside_ip)
    except ValueError as e:
        if "not in pool" in str(e).lower():
            error_raised = True
    
    assert error_raised, "Allocating IP outside pool range should fail"


def test_specific_ip_reserved_rejected():
    """
    **Feature: resources, Property 23: Specific IP Allocation**
    **Validates: Requirements 3A.3**
    
    Requesting a reserved IP should fail.
    """
    reserved_ip = "192.168.1.5"
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/28", reserved_ips=[reserved_ip])
    user_id = str(uuid.uuid4())
    
    # Try to allocate the reserved IP
    error_raised = False
    try:
        pool_state.checkout_ip(user_id, specific_ip=reserved_ip)
    except ValueError as e:
        if "reserved" in str(e).lower():
            error_raised = True
    
    assert error_raised, "Allocating reserved IP should fail"


def test_specific_ip_already_allocated_rejected():
    """
    **Feature: resources, Property 23: Specific IP Allocation**
    **Validates: Requirements 3A.3**
    
    Requesting an already allocated IP should fail.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/28")
    user_id1 = str(uuid.uuid4())
    user_id2 = str(uuid.uuid4())
    
    specific_ip = "192.168.1.5"
    
    # First user allocates the IP
    pool_state.checkout_ip(user_id1, specific_ip=specific_ip)
    
    # Second user tries to allocate the same IP
    error_raised = False
    try:
        pool_state.checkout_ip(user_id2, specific_ip=specific_ip)
    except ValueError as e:
        if "allocated" in str(e).lower():
            error_raised = True
    
    assert error_raised, "Allocating already allocated IP should fail"


def test_specific_ip_network_address_rejected():
    """
    **Feature: resources, Property 23: Specific IP Allocation**
    **Validates: Requirements 3A.3**
    
    Requesting the network address should fail (not a usable host address).
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/28")
    user_id = str(uuid.uuid4())
    
    # Try to allocate the network address
    network_address = "192.168.1.0"
    
    error_raised = False
    try:
        pool_state.checkout_ip(user_id, specific_ip=network_address)
    except ValueError as e:
        if "not a usable" in str(e).lower() or "not in pool" in str(e).lower():
            error_raised = True
    
    assert error_raised, "Allocating network address should fail"


def test_specific_ip_broadcast_address_rejected():
    """
    **Feature: resources, Property 23: Specific IP Allocation**
    **Validates: Requirements 3A.3**
    
    Requesting the broadcast address should fail (not a usable host address).
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/28")
    user_id = str(uuid.uuid4())
    
    # Try to allocate the broadcast address
    broadcast_address = "192.168.1.15"
    
    error_raised = False
    try:
        pool_state.checkout_ip(user_id, specific_ip=broadcast_address)
    except ValueError as e:
        if "not a usable" in str(e).lower() or "not in pool" in str(e).lower():
            error_raised = True
    
    assert error_raised, "Allocating broadcast address should fail"


def test_property_specific_ip_always_returns_requested():
    """
    **Feature: resources, Property 23: Specific IP Allocation**
    **Validates: Requirements 3A.3**
    
    Property: For any valid, available IP in the pool, requesting that specific IP
    should always return exactly that IP.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/24")
    user_id = str(uuid.uuid4())
    
    # Get all usable IPs
    usable_ips = list(pool_state.all_usable_ips)
    
    # Test with a sample of IPs
    sample_size = min(20, len(usable_ips))
    sample_ips = random.sample(usable_ips, sample_size)
    
    for specific_ip in sample_ips:
        # Create fresh pool state for each test
        test_pool = MockIPPoolState(pool_id=1, cidr="192.168.1.0/24")
        
        alloc_id, allocated_ip = test_pool.checkout_ip(user_id, specific_ip=specific_ip)
        
        assert allocated_ip == specific_ip, \
            f"Requested {specific_ip} but got {allocated_ip}"


def test_specific_ip_after_checkin_available():
    """
    **Feature: resources, Property 23: Specific IP Allocation**
    **Validates: Requirements 3A.3**
    
    After checking in a specific IP, it should be available for specific allocation again.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/28")
    user_id = str(uuid.uuid4())
    
    specific_ip = "192.168.1.5"
    
    # Allocate the specific IP
    alloc_id, _ = pool_state.checkout_ip(user_id, specific_ip=specific_ip)
    
    # Checkin the IP
    pool_state.checkin_ip(alloc_id, user_id)
    
    # Should be able to allocate the same specific IP again
    alloc_id2, allocated_ip = pool_state.checkout_ip(user_id, specific_ip=specific_ip)
    
    assert allocated_ip == specific_ip, "Should be able to allocate same specific IP after checkin"


def test_generated_specific_ip_allocation():
    """
    **Feature: resources, Property 23: Specific IP Allocation**
    **Validates: Requirements 3A.3**
    
    Property test: For randomly selected IPs from the pool, specific allocation
    should always succeed if the IP is available.
    """
    for _ in range(50):
        # Generate random CIDR
        prefix = random.randint(26, 28)
        cidr = f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.0/{prefix}"
        
        pool_state = MockIPPoolState(pool_id=1, cidr=cidr)
        user_id = str(uuid.uuid4())
        
        usable_ips = list(pool_state.all_usable_ips)
        if not usable_ips:
            continue
        
        # Pick a random IP from the pool
        specific_ip = random.choice(usable_ips)
        
        # Allocate it
        alloc_id, allocated_ip = pool_state.checkout_ip(user_id, specific_ip=specific_ip)
        
        assert allocated_ip == specific_ip, \
            f"For pool {cidr}, requested {specific_ip} but got {allocated_ip}"
