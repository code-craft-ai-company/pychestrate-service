"""
.. module:: test_ip_pool_manager_address_calculation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for IPPoolManager IP address calculation methods

.. moduleauthor:: Code Craft AI LLC

Tests for IP pool address calculation in the IPPoolManager.

**Feature: resources**
**Property 20: IP Pool Address Calculation**
**Validates: Requirements 2A.3**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import ipaddress
import random

from ccai.pychestrate.core.managers.ip_pool_manager import (
    calculate_usable_hosts,
    get_usable_ips,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_ipv4_cidr_with_known_hosts(prefix_length: int):
    """Generate an IPv4 CIDR with a known number of hosts."""
    octets = [random.randint(0, 255) for _ in range(4)]
    cidr = f"{octets[0]}.{octets[1]}.{octets[2]}.{octets[3]}/{prefix_length}"
    # Normalize to network address
    network = ipaddress.ip_network(cidr, strict=False)
    return str(network)


def calculate_expected_ipv4_hosts(prefix_length: int):
    """Calculate expected usable hosts for IPv4 based on prefix length."""
    total = 2 ** (32 - prefix_length)
    if prefix_length >= 31:
        return total  # /31 and /32 are special cases
    return total - 2  # Subtract network and broadcast


# =============================================================================
# IP Pool Address Calculation Tests - Property 20
# =============================================================================

def test_ipv4_usable_hosts_calculation():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    For any valid IPv4 CIDR, the calculated usable hosts should equal
    total addresses minus network and broadcast addresses.
    """
    test_cases = [
        ("192.168.1.0/24", 254),  # 256 - 2 = 254
        ("10.0.0.0/8", 16777214),  # 2^24 - 2
        ("172.16.0.0/16", 65534),  # 2^16 - 2
        ("192.168.1.0/30", 2),  # 4 - 2 = 2
        ("192.168.1.0/29", 6),  # 8 - 2 = 6
        ("192.168.1.0/28", 14),  # 16 - 2 = 14
    ]
    
    for cidr, expected in test_cases:
        result = calculate_usable_hosts(cidr)
        assert result == expected, f"CIDR '{cidr}' should have {expected} usable hosts, got {result}"


def test_ipv4_special_prefix_lengths():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    Test special prefix lengths /31 and /32 for IPv4.
    """
    # /31 networks have 2 addresses, both usable (point-to-point links)
    result = calculate_usable_hosts("192.168.1.0/31")
    assert result == 2, f"/31 should have 2 usable hosts, got {result}"
    
    # /32 networks have 1 address (single host)
    result = calculate_usable_hosts("192.168.1.1/32")
    assert result == 1, f"/32 should have 1 usable host, got {result}"


def test_ipv6_usable_hosts_calculation():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    For any valid IPv6 CIDR, the calculated usable hosts should equal
    total addresses minus network address (no broadcast in IPv6).
    """
    # /64 is the most common IPv6 subnet
    result = calculate_usable_hosts("2001:db8::/64")
    expected = 2**64 - 1  # Subtract network address only
    assert result == expected, f"/64 should have {expected} usable hosts, got {result}"
    
    # /128 is a single host
    result = calculate_usable_hosts("2001:db8::1/128")
    assert result == 0, f"/128 should have 0 usable hosts (only network address), got {result}"
    
    # /127 is point-to-point
    result = calculate_usable_hosts("2001:db8::/127")
    assert result == 1, f"/127 should have 1 usable host, got {result}"


def test_usable_hosts_with_reserved_ips():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    Reserved IPs should be subtracted from usable hosts count.
    """
    cidr = "192.168.1.0/24"
    
    # No reserved IPs
    result = calculate_usable_hosts(cidr, [])
    assert result == 254, f"No reserved IPs should give 254 hosts, got {result}"
    
    # One reserved IP
    result = calculate_usable_hosts(cidr, ["192.168.1.1"])
    assert result == 253, f"One reserved IP should give 253 hosts, got {result}"
    
    # Multiple reserved IPs
    result = calculate_usable_hosts(cidr, ["192.168.1.1", "192.168.1.2", "192.168.1.3"])
    assert result == 251, f"Three reserved IPs should give 251 hosts, got {result}"


def test_reserved_ips_outside_range_not_counted():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    Reserved IPs outside the CIDR range should not affect the count.
    """
    cidr = "192.168.1.0/24"
    
    # Reserved IP outside the range
    result = calculate_usable_hosts(cidr, ["10.0.0.1"])
    assert result == 254, f"Reserved IP outside range should not affect count, got {result}"
    
    # Mix of inside and outside
    result = calculate_usable_hosts(cidr, ["192.168.1.1", "10.0.0.1"])
    assert result == 253, f"Only reserved IP inside range should be counted, got {result}"


def test_invalid_reserved_ips_ignored():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    Invalid reserved IP strings should be ignored.
    """
    cidr = "192.168.1.0/24"
    
    result = calculate_usable_hosts(cidr, ["not-an-ip", "192.168.1.1"])
    assert result == 253, f"Invalid reserved IP should be ignored, got {result}"


def test_get_usable_ips_returns_correct_addresses():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    get_usable_ips should return actual usable IP addresses.
    """
    cidr = "192.168.1.0/29"  # 8 addresses, 6 usable
    
    usable_ips = get_usable_ips(cidr)
    
    # Should have 6 usable IPs
    assert len(usable_ips) == 6, f"Should have 6 usable IPs, got {len(usable_ips)}"
    
    # Should not include network address
    assert "192.168.1.0" not in usable_ips, "Network address should not be in usable IPs"
    
    # Should not include broadcast address
    assert "192.168.1.7" not in usable_ips, "Broadcast address should not be in usable IPs"
    
    # Should include host addresses
    expected_ips = ["192.168.1.1", "192.168.1.2", "192.168.1.3", 
                    "192.168.1.4", "192.168.1.5", "192.168.1.6"]
    assert usable_ips == expected_ips, f"Expected {expected_ips}, got {usable_ips}"


def test_get_usable_ips_excludes_reserved():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    get_usable_ips should exclude reserved IPs.
    """
    cidr = "192.168.1.0/29"
    reserved = ["192.168.1.1", "192.168.1.3"]
    
    usable_ips = get_usable_ips(cidr, reserved)
    
    # Should have 4 usable IPs (6 - 2 reserved)
    assert len(usable_ips) == 4, f"Should have 4 usable IPs, got {len(usable_ips)}"
    
    # Reserved IPs should not be in the list
    assert "192.168.1.1" not in usable_ips, "Reserved IP should not be in usable IPs"
    assert "192.168.1.3" not in usable_ips, "Reserved IP should not be in usable IPs"


def test_generated_ipv4_cidr_host_calculation():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    For any generated IPv4 CIDR, the calculated usable hosts should match
    the expected formula: 2^(32-prefix) - 2 (for prefix < 31).
    Property: For all valid IPv4 CIDRs, usable hosts = total - network - broadcast.
    """
    for _ in range(100):
        prefix = random.randint(16, 30)  # Reasonable range for testing
        cidr = generate_ipv4_cidr_with_known_hosts(prefix)
        expected = calculate_expected_ipv4_hosts(prefix)
        
        result = calculate_usable_hosts(cidr)
        assert result == expected, f"CIDR '{cidr}' should have {expected} usable hosts, got {result}"


def test_usable_hosts_count_matches_usable_ips_list():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    The count from calculate_usable_hosts should match the length of get_usable_ips.
    Property: For all CIDRs, calculate_usable_hosts(cidr) == len(get_usable_ips(cidr)).
    """
    test_cidrs = [
        "192.168.1.0/28",
        "192.168.1.0/29",
        "192.168.1.0/30",
        "10.0.0.0/28",
    ]
    
    for cidr in test_cidrs:
        count = calculate_usable_hosts(cidr)
        ips = get_usable_ips(cidr)
        assert count == len(ips), f"CIDR '{cidr}': count {count} != len(ips) {len(ips)}"


def test_usable_hosts_with_reserved_matches_list():
    """
    **Feature: resources, Property 20: IP Pool Address Calculation**
    **Validates: Requirements 2A.3**
    
    With reserved IPs, the count should still match the list length.
    """
    cidr = "192.168.1.0/28"
    reserved = ["192.168.1.1", "192.168.1.5", "192.168.1.10"]
    
    count = calculate_usable_hosts(cidr, reserved)
    ips = get_usable_ips(cidr, reserved)
    
    assert count == len(ips), f"Count {count} should match len(ips) {len(ips)}"

