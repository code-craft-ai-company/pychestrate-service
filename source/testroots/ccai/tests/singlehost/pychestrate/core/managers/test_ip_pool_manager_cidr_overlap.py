"""
.. module:: test_ip_pool_manager_cidr_overlap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for IPPoolManager CIDR overlap detection

.. moduleauthor:: Code Craft AI LLC

Tests for CIDR overlap detection in the IPPoolManager.

**Feature: resources**
**Property 24: CIDR Overlap Detection**
**Validates: Requirements 2A.6**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random

from ccai.pychestrate.core.managers.ip_pool_manager import check_cidr_overlap


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_non_overlapping_ipv4_cidrs():
    """Generate two non-overlapping IPv4 CIDR ranges."""
    # Use different /24 networks in different /16 ranges
    first_second_octet = random.randint(0, 127)
    second_second_octet = random.randint(128, 255)
    
    cidr1 = f"10.{first_second_octet}.0.0/24"
    cidr2 = f"10.{second_second_octet}.0.0/24"
    
    return cidr1, cidr2


def generate_overlapping_ipv4_cidrs():
    """Generate two overlapping IPv4 CIDR ranges."""
    # A /24 inside a /16
    base = random.randint(0, 255)
    cidr1 = f"192.168.{base}.0/24"
    cidr2 = f"192.168.0.0/16"
    
    return cidr1, cidr2


# =============================================================================
# CIDR Overlap Detection Tests - Property 24
# =============================================================================

def test_identical_cidrs_overlap():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    Identical CIDR ranges should be detected as overlapping.
    """
    cidr = "192.168.1.0/24"
    
    result = check_cidr_overlap(cidr, cidr)
    assert result is True, f"Identical CIDRs should overlap"


def test_supernet_subnet_overlap():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    A subnet should overlap with its supernet.
    """
    supernet = "192.168.0.0/16"
    subnet = "192.168.1.0/24"
    
    result = check_cidr_overlap(supernet, subnet)
    assert result is True, f"Supernet and subnet should overlap"
    
    # Order shouldn't matter
    result = check_cidr_overlap(subnet, supernet)
    assert result is True, f"Subnet and supernet should overlap (reversed order)"


def test_adjacent_cidrs_do_not_overlap():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    Adjacent CIDR ranges should not overlap.
    """
    cidr1 = "192.168.1.0/24"
    cidr2 = "192.168.2.0/24"
    
    result = check_cidr_overlap(cidr1, cidr2)
    assert result is False, f"Adjacent CIDRs should not overlap"


def test_completely_separate_cidrs_do_not_overlap():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    Completely separate CIDR ranges should not overlap.
    """
    test_cases = [
        ("10.0.0.0/8", "172.16.0.0/12"),
        ("192.168.1.0/24", "10.0.0.0/8"),
        ("192.168.1.0/24", "192.168.100.0/24"),
    ]
    
    for cidr1, cidr2 in test_cases:
        result = check_cidr_overlap(cidr1, cidr2)
        assert result is False, f"CIDRs '{cidr1}' and '{cidr2}' should not overlap"


def test_partial_overlap():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    Partially overlapping CIDR ranges should be detected.
    """
    # Two /23 networks that share a /24
    cidr1 = "192.168.0.0/23"  # 192.168.0.0 - 192.168.1.255
    cidr2 = "192.168.1.0/23"  # 192.168.1.0 - 192.168.2.255
    
    result = check_cidr_overlap(cidr1, cidr2)
    assert result is True, f"Partially overlapping CIDRs should overlap"


def test_ipv4_ipv6_do_not_overlap():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    IPv4 and IPv6 CIDR ranges should never overlap.
    """
    ipv4_cidr = "192.168.1.0/24"
    ipv6_cidr = "2001:db8::/32"
    
    result = check_cidr_overlap(ipv4_cidr, ipv6_cidr)
    assert result is False, f"IPv4 and IPv6 CIDRs should not overlap"


def test_ipv6_overlap_detection():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    IPv6 CIDR overlap should be detected correctly.
    """
    # Overlapping IPv6 ranges
    supernet = "2001:db8::/32"
    subnet = "2001:db8:1::/48"
    
    result = check_cidr_overlap(supernet, subnet)
    assert result is True, f"IPv6 supernet and subnet should overlap"
    
    # Non-overlapping IPv6 ranges
    cidr1 = "2001:db8::/32"
    cidr2 = "2001:db9::/32"
    
    result = check_cidr_overlap(cidr1, cidr2)
    assert result is False, f"Different IPv6 /32 ranges should not overlap"


def test_invalid_cidr_returns_false():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    Invalid CIDR strings should return False (no overlap).
    """
    valid_cidr = "192.168.1.0/24"
    invalid_cidr = "not-a-cidr"
    
    result = check_cidr_overlap(valid_cidr, invalid_cidr)
    assert result is False, f"Invalid CIDR should return False"
    
    result = check_cidr_overlap(invalid_cidr, valid_cidr)
    assert result is False, f"Invalid CIDR should return False (reversed)"
    
    result = check_cidr_overlap(invalid_cidr, invalid_cidr)
    assert result is False, f"Two invalid CIDRs should return False"


def test_generated_non_overlapping_cidrs():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    For any generated non-overlapping CIDRs, overlap detection should return False.
    Property: For all non-overlapping CIDR pairs, check_cidr_overlap returns False.
    """
    for _ in range(100):
        cidr1, cidr2 = generate_non_overlapping_ipv4_cidrs()
        result = check_cidr_overlap(cidr1, cidr2)
        assert result is False, f"Non-overlapping CIDRs '{cidr1}' and '{cidr2}' should not overlap"


def test_generated_overlapping_cidrs():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    For any generated overlapping CIDRs, overlap detection should return True.
    Property: For all overlapping CIDR pairs, check_cidr_overlap returns True.
    """
    for _ in range(100):
        cidr1, cidr2 = generate_overlapping_ipv4_cidrs()
        result = check_cidr_overlap(cidr1, cidr2)
        assert result is True, f"Overlapping CIDRs '{cidr1}' and '{cidr2}' should overlap"


def test_overlap_is_symmetric():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    Overlap detection should be symmetric: overlap(a, b) == overlap(b, a).
    Property: For all CIDR pairs, check_cidr_overlap(a, b) == check_cidr_overlap(b, a).
    """
    test_pairs = [
        ("192.168.0.0/16", "192.168.1.0/24"),
        ("10.0.0.0/8", "172.16.0.0/12"),
        ("192.168.1.0/24", "192.168.1.0/24"),
        ("192.168.1.0/24", "192.168.2.0/24"),
    ]
    
    for cidr1, cidr2 in test_pairs:
        result1 = check_cidr_overlap(cidr1, cidr2)
        result2 = check_cidr_overlap(cidr2, cidr1)
        assert result1 == result2, f"Overlap should be symmetric for '{cidr1}' and '{cidr2}'"


def test_single_host_overlap():
    """
    **Feature: resources, Property 24: CIDR Overlap Detection**
    **Validates: Requirements 2A.6**
    
    Single host (/32) should overlap with containing network.
    """
    network = "192.168.1.0/24"
    host = "192.168.1.100/32"
    
    result = check_cidr_overlap(network, host)
    assert result is True, f"Single host should overlap with containing network"
    
    # Host outside network
    outside_host = "192.168.2.100/32"
    result = check_cidr_overlap(network, outside_host)
    assert result is False, f"Single host outside network should not overlap"

