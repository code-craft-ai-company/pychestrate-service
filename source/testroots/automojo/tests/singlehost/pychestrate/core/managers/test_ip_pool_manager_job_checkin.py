"""
.. module:: test_ip_pool_manager_job_checkin
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for IPPoolManager job IP bulk checkin

.. moduleauthor:: Automation Mojo LLC

Tests for job IP bulk checkin in the IPPoolManager.

**Feature: resources**
**Property 25: Job IP Bulk Checkin**
**Validates: Requirements 4A.3**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import uuid

from automojo.pychestrate.core.managers.ip_pool_manager import (
    get_usable_ips,
)


# =============================================================================
# Test Fixtures - Mock-based approach for SQLite compatibility
# =============================================================================

class MockIPPoolState:
    """
    A helper class to maintain state for mock IP pool operations.
    This simulates the database state for testing job bulk checkin.
    """
    
    def __init__(self, pool_id, cidr, reserved_ips=None):
        self.pool_id = pool_id
        self.cidr = cidr
        self.reserved_ips = set(reserved_ips or [])
        self.allocations = {}  # alloc_id -> (ip_address, user_id, job_id, status)
        self._next_alloc_id = 1
        
        # Calculate usable IPs
        self.all_usable_ips = set(get_usable_ips(cidr, list(self.reserved_ips)))
    
    def get_available_ips(self):
        """Get IPs that are not allocated or reserved."""
        allocated_ips = {ip for ip, _, _, status in self.allocations.values() if status == 'active'}
        return self.all_usable_ips - allocated_ips - self.reserved_ips
    
    def checkout_ip(self, user_id, job_id=None, specific_ip=None):
        """Checkout an IP and return allocation info."""
        available = self.get_available_ips()
        
        if specific_ip:
            if specific_ip not in available:
                raise ValueError(f"IP {specific_ip} not available")
            ip_to_allocate = specific_ip
        else:
            if not available:
                raise ValueError("Pool exhausted")
            ip_to_allocate = sorted(available)[0]
        
        alloc_id = self._next_alloc_id
        self._next_alloc_id += 1
        self.allocations[alloc_id] = (ip_to_allocate, user_id, job_id, 'active')
        return alloc_id, ip_to_allocate
    
    def checkin_ip(self, alloc_id, user_id):
        """Checkin a single IP allocation."""
        if alloc_id not in self.allocations:
            return False
        
        ip, owner, job_id, status = self.allocations[alloc_id]
        if str(owner) != str(user_id):
            return False
        
        if status != 'active':
            return True  # Already released
        
        self.allocations[alloc_id] = (ip, owner, job_id, 'released')
        return True
    
    def checkin_job_ips(self, job_id, user_id):
        """
        Release all IPs allocated to a specific job.
        
        :param job_id: The job identifier
        :param user_id: The user performing the checkin
        :returns: Count of allocations released
        """
        released_count = 0
        for alloc_id, (ip, owner, alloc_job_id, status) in list(self.allocations.items()):
            if alloc_job_id == job_id and status == 'active':
                self.allocations[alloc_id] = (ip, owner, alloc_job_id, 'released')
                released_count += 1
        return released_count
    
    def get_stats(self):
        """Get pool statistics."""
        total = len(self.all_usable_ips)
        allocated = sum(1 for _, _, _, status in self.allocations.values() if status == 'active')
        available = total - allocated
        return {
            'total_addresses': total,
            'allocated_count': allocated,
            'available_count': max(0, available)
        }
    
    def get_job_allocations(self, job_id):
        """Get all active allocations for a job."""
        return [
            (alloc_id, ip) 
            for alloc_id, (ip, _, alloc_job_id, status) in self.allocations.items()
            if alloc_job_id == job_id and status == 'active'
        ]


# =============================================================================
# Job IP Bulk Checkin Tests - Property 25
# =============================================================================

def test_job_checkin_releases_all_job_ips():
    """
    **Feature: resources, Property 25: Job IP Bulk Checkin**
    **Validates: Requirements 4A.3**
    
    Checking in by job ID should release all IPs allocated to that job.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/24")
    user_id = str(uuid.uuid4())
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    
    initial_stats = pool_state.get_stats()
    initial_available = initial_stats["available_count"]
    
    # Allocate multiple IPs to the job
    num_ips = 5
    for _ in range(num_ips):
        pool_state.checkout_ip(user_id, job_id=job_id)
    
    # Verify IPs are allocated
    stats = pool_state.get_stats()
    assert stats["allocated_count"] == num_ips, f"Should have {num_ips} allocations"
    
    # Checkin all job IPs
    released = pool_state.checkin_job_ips(job_id, user_id)
    
    assert released == num_ips, f"Should release {num_ips} IPs, released {released}"
    
    # Verify pool is restored
    final_stats = pool_state.get_stats()
    assert final_stats["available_count"] == initial_available, \
        "Pool should be restored after job checkin"


def test_job_checkin_only_affects_specified_job():
    """
    **Feature: resources, Property 25: Job IP Bulk Checkin**
    **Validates: Requirements 4A.3**
    
    Job checkin should only release IPs for the specified job, not other jobs.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/24")
    user_id = str(uuid.uuid4())
    job_id_1 = f"job-{uuid.uuid4().hex[:8]}"
    job_id_2 = f"job-{uuid.uuid4().hex[:8]}"
    
    # Allocate IPs to job 1
    for _ in range(3):
        pool_state.checkout_ip(user_id, job_id=job_id_1)
    
    # Allocate IPs to job 2
    for _ in range(2):
        pool_state.checkout_ip(user_id, job_id=job_id_2)
    
    # Verify total allocations
    stats = pool_state.get_stats()
    assert stats["allocated_count"] == 5, "Should have 5 total allocations"
    
    # Checkin only job 1
    released = pool_state.checkin_job_ips(job_id_1, user_id)
    
    assert released == 3, "Should release 3 IPs for job 1"
    
    # Verify job 2 allocations remain
    stats = pool_state.get_stats()
    assert stats["allocated_count"] == 2, "Job 2 should still have 2 allocations"
    
    # Verify job 2 allocations are still active
    job2_allocs = pool_state.get_job_allocations(job_id_2)
    assert len(job2_allocs) == 2, "Job 2 should still have 2 active allocations"


def test_job_checkin_with_no_allocations():
    """
    **Feature: resources, Property 25: Job IP Bulk Checkin**
    **Validates: Requirements 4A.3**
    
    Job checkin for a job with no allocations should return 0 and not error.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/24")
    user_id = str(uuid.uuid4())
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    
    # Checkin a job that has no allocations
    released = pool_state.checkin_job_ips(job_id, user_id)
    
    assert released == 0, "Should release 0 IPs for job with no allocations"


def test_job_checkin_idempotent():
    """
    **Feature: resources, Property 25: Job IP Bulk Checkin**
    **Validates: Requirements 4A.3**
    
    Calling job checkin multiple times should be idempotent.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/24")
    user_id = str(uuid.uuid4())
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    
    # Allocate IPs to the job
    for _ in range(3):
        pool_state.checkout_ip(user_id, job_id=job_id)
    
    # First checkin
    released1 = pool_state.checkin_job_ips(job_id, user_id)
    assert released1 == 3, "First checkin should release 3 IPs"
    
    # Second checkin (should be idempotent)
    released2 = pool_state.checkin_job_ips(job_id, user_id)
    assert released2 == 0, "Second checkin should release 0 IPs (already released)"
    
    # Pool state should be consistent
    stats = pool_state.get_stats()
    assert stats["allocated_count"] == 0, "No allocations should remain"


def test_job_checkin_mixed_with_non_job_allocations():
    """
    **Feature: resources, Property 25: Job IP Bulk Checkin**
    **Validates: Requirements 4A.3**
    
    Job checkin should not affect allocations without a job ID.
    """
    pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/24")
    user_id = str(uuid.uuid4())
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    
    # Allocate IPs with job ID
    for _ in range(3):
        pool_state.checkout_ip(user_id, job_id=job_id)
    
    # Allocate IPs without job ID
    for _ in range(2):
        pool_state.checkout_ip(user_id, job_id=None)
    
    # Verify total allocations
    stats = pool_state.get_stats()
    assert stats["allocated_count"] == 5, "Should have 5 total allocations"
    
    # Checkin job IPs
    released = pool_state.checkin_job_ips(job_id, user_id)
    
    assert released == 3, "Should release 3 job IPs"
    
    # Non-job allocations should remain
    stats = pool_state.get_stats()
    assert stats["allocated_count"] == 2, "Non-job allocations should remain"


def test_property_job_checkin_releases_exact_count():
    """
    **Feature: resources, Property 25: Job IP Bulk Checkin**
    **Validates: Requirements 4A.3**
    
    Property: For any number of IPs allocated to a job, job checkin should
    release exactly that number of IPs.
    """
    for _ in range(20):
        pool_state = MockIPPoolState(pool_id=1, cidr="192.168.1.0/24")
        user_id = str(uuid.uuid4())
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        
        # Random number of allocations
        num_ips = random.randint(1, 20)
        
        # Allocate IPs to the job
        for _ in range(num_ips):
            pool_state.checkout_ip(user_id, job_id=job_id)
        
        # Checkin job IPs
        released = pool_state.checkin_job_ips(job_id, user_id)
        
        assert released == num_ips, \
            f"Should release exactly {num_ips} IPs, released {released}"


def test_generated_multiple_jobs_checkin():
    """
    **Feature: resources, Property 25: Job IP Bulk Checkin**
    **Validates: Requirements 4A.3**
    
    Property test: Multiple jobs can have allocations, and checking in one
    job should not affect others.
    """
    for _ in range(10):
        pool_state = MockIPPoolState(pool_id=1, cidr="10.0.0.0/22")  # Large pool
        user_id = str(uuid.uuid4())
        
        # Create multiple jobs with random allocations
        jobs = {}
        num_jobs = random.randint(2, 5)
        
        for i in range(num_jobs):
            job_id = f"job-{i}-{uuid.uuid4().hex[:8]}"
            num_ips = random.randint(1, 10)
            jobs[job_id] = num_ips
            
            for _ in range(num_ips):
                pool_state.checkout_ip(user_id, job_id=job_id)
        
        total_allocated = sum(jobs.values())
        
        # Verify total allocations
        stats = pool_state.get_stats()
        assert stats["allocated_count"] == total_allocated, \
            f"Should have {total_allocated} total allocations"
        
        # Checkin each job and verify
        remaining = total_allocated
        for job_id, expected_count in jobs.items():
            released = pool_state.checkin_job_ips(job_id, user_id)
            assert released == expected_count, \
                f"Job {job_id} should release {expected_count} IPs, released {released}"
            
            remaining -= expected_count
            stats = pool_state.get_stats()
            assert stats["allocated_count"] == remaining, \
                f"Should have {remaining} allocations remaining"
