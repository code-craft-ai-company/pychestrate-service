"""
.. module:: test_ip_pool_manager_cidr_validation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for IPPoolManager CIDR validation methods

.. moduleauthor:: Code Craft AI LLC

Tests for CIDR validation in the IPPoolManager.

**Feature: resources**
**Property 19: CIDR Validation**
**Validates: Requirements 2A.2**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random

from ccai.pychestrate.core.managers.ip_pool_manager import validate_cidr


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_valid_ipv4_cidr():
    """Generate a valid IPv4 CIDR notation."""
    octets = [random.randint(0, 255) for _ in range(4)]
    prefix = random.randint(0, 32)
    return f"{octets[0]}.{octets[1]}.{octets[2]}.{octets[3]}/{prefix}"


def generate_valid_ipv6_cidr():
    """Generate a valid IPv6 CIDR notation."""
    # Generate 8 groups of 4 hex digits
    groups = [format(random.randint(0, 65535), 'x') for _ in range(8)]
    prefix = random.randint(0, 128)
    return f"{':'.join(groups)}/{prefix}"


def generate_invalid_cidr():
    """Generate an invalid CIDR notation."""
    invalid_patterns = [
        "not.a.valid.cidr",
        "192.168.1.0",  # Missing prefix
        "192.168.1.0/33",  # Invalid prefix for IPv4
        "192.168.1.256/24",  # Invalid octet
        "192.168.1/24",  # Missing octet
        "192.168.1.0.1/24",  # Too many octets
        "abc.def.ghi.jkl/24",  # Non-numeric octets
        "/24",  # Missing address
        "192.168.1.0/",  # Missing prefix value
        "192.168.1.0/-1",  # Negative prefix
        "::1/129",  # Invalid prefix for IPv6
        "gggg::1/64",  # Invalid hex in IPv6
    ]
    return random.choice(invalid_patterns)


# =============================================================================
# CIDR Validation Tests - Property 19
# =============================================================================

def test_valid_ipv4_cidr_passes_validation():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    Valid IPv4 CIDR notations should pass validation.
    """
    valid_cidrs = [
        "192.168.1.0/24",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "0.0.0.0/0",
        "255.255.255.255/32",
        "192.168.0.0/16",
        "10.10.10.0/30",
        "192.168.1.128/25",
    ]
    
    for cidr in valid_cidrs:
        is_valid, error_msg = validate_cidr(cidr)
        assert is_valid is True, f"Valid IPv4 CIDR '{cidr}' should pass validation, got error: {error_msg}"
        assert error_msg is None, f"Valid CIDR should have no error message"


def test_valid_ipv6_cidr_passes_validation():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    Valid IPv6 CIDR notations should pass validation.
    """
    valid_cidrs = [
        "2001:db8::/32",
        "fe80::/10",
        "::1/128",
        "::/0",
        "2001:db8:85a3::8a2e:370:7334/64",
        "fd00::/8",
    ]
    
    for cidr in valid_cidrs:
        is_valid, error_msg = validate_cidr(cidr)
        assert is_valid is True, f"Valid IPv6 CIDR '{cidr}' should pass validation, got error: {error_msg}"
        assert error_msg is None, f"Valid CIDR should have no error message"


def test_generated_valid_ipv4_cidr_passes_validation():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    For any generated valid IPv4 CIDR, validation should pass.
    Property: For all valid IPv4 CIDR notations, validation should return (True, None).
    """
    for _ in range(100):
        cidr = generate_valid_ipv4_cidr()
        is_valid, error_msg = validate_cidr(cidr)
        assert is_valid is True, f"Generated valid IPv4 CIDR '{cidr}' should pass validation, got error: {error_msg}"


def test_generated_valid_ipv6_cidr_passes_validation():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    For any generated valid IPv6 CIDR, validation should pass.
    Property: For all valid IPv6 CIDR notations, validation should return (True, None).
    """
    for _ in range(100):
        cidr = generate_valid_ipv6_cidr()
        is_valid, error_msg = validate_cidr(cidr)
        assert is_valid is True, f"Generated valid IPv6 CIDR '{cidr}' should pass validation, got error: {error_msg}"


def test_invalid_cidr_fails_validation():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    Invalid CIDR notations should fail validation.
    """
    invalid_cidrs = [
        "not.a.valid.cidr",
        "192.168.1.0/33",  # Invalid prefix for IPv4
        "192.168.1.256/24",  # Invalid octet
        "192.168.1/24",  # Missing octet
        "abc.def.ghi.jkl/24",  # Non-numeric octets
        "/24",  # Missing address
        "192.168.1.0/",  # Missing prefix value
        "::1/129",  # Invalid prefix for IPv6
    ]
    
    for cidr in invalid_cidrs:
        is_valid, error_msg = validate_cidr(cidr)
        assert is_valid is False, f"Invalid CIDR '{cidr}' should fail validation"
        assert error_msg is not None, f"Invalid CIDR should have an error message"


def test_ip_without_prefix_is_valid():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    IP addresses without prefix are valid (treated as /32 for IPv4, /128 for IPv6).
    This is standard behavior of the ipaddress module.
    """
    # IPv4 without prefix is treated as /32
    is_valid, error_msg = validate_cidr("192.168.1.0")
    assert is_valid is True, f"IPv4 without prefix should be valid (treated as /32), got error: {error_msg}"
    
    # IPv6 without prefix is treated as /128
    is_valid, error_msg = validate_cidr("::1")
    assert is_valid is True, f"IPv6 without prefix should be valid (treated as /128), got error: {error_msg}"


def test_empty_cidr_fails_validation():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    Empty and None CIDR values should fail validation.
    """
    is_valid, error_msg = validate_cidr("")
    assert is_valid is False, "Empty CIDR should fail validation"
    assert error_msg is not None, "Empty CIDR should have an error message"
    
    is_valid, error_msg = validate_cidr(None)
    assert is_valid is False, "None CIDR should fail validation"
    assert error_msg is not None, "None CIDR should have an error message"


def test_cidr_with_invalid_prefix_fails_validation():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    CIDR with prefix outside valid range should fail validation.
    """
    # IPv4 prefix must be 0-32
    is_valid, error_msg = validate_cidr("192.168.1.0/33")
    assert is_valid is False, "IPv4 CIDR with prefix > 32 should fail"
    
    is_valid, error_msg = validate_cidr("192.168.1.0/-1")
    assert is_valid is False, "CIDR with negative prefix should fail"
    
    # IPv6 prefix must be 0-128
    is_valid, error_msg = validate_cidr("2001:db8::/129")
    assert is_valid is False, "IPv6 CIDR with prefix > 128 should fail"


def test_cidr_boundary_prefixes():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    Test boundary conditions for CIDR prefix lengths.
    """
    # IPv4 boundaries
    is_valid, _ = validate_cidr("192.168.1.0/0")
    assert is_valid is True, "IPv4 /0 should be valid"
    
    is_valid, _ = validate_cidr("192.168.1.0/32")
    assert is_valid is True, "IPv4 /32 should be valid"
    
    # IPv6 boundaries
    is_valid, _ = validate_cidr("2001:db8::/0")
    assert is_valid is True, "IPv6 /0 should be valid"
    
    is_valid, _ = validate_cidr("2001:db8::/128")
    assert is_valid is True, "IPv6 /128 should be valid"


def test_cidr_with_host_bits_set():
    """
    **Feature: resources, Property 19: CIDR Validation**
    **Validates: Requirements 2A.2**
    
    CIDR with host bits set should still be valid (strict=False behavior).
    The ipaddress module normalizes these to the network address.
    """
    # 192.168.1.100/24 has host bits set but is still valid CIDR notation
    is_valid, error_msg = validate_cidr("192.168.1.100/24")
    assert is_valid is True, f"CIDR with host bits should be valid (normalized), got error: {error_msg}"
    
    is_valid, error_msg = validate_cidr("10.0.0.5/8")
    assert is_valid is True, f"CIDR with host bits should be valid (normalized), got error: {error_msg}"

