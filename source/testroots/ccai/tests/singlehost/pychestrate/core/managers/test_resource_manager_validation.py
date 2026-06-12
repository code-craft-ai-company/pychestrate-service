"""
.. module:: test_resource_manager_validation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ResourceManager validation methods

.. moduleauthor:: Code Craft AI LLC

Tests for resource name and tag name validation in the ResourceManager.

**Feature: resources**
**Property 2: Resource Name Validation**
**Validates: Requirements 1.7**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.pychestrate.core.managers.resource_manager import validate_resource_name, validate_tag_name


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_valid_resource_name():
    """Generate a valid resource name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    # Valid chars: alphanumeric, underscore, hyphen, period
    valid_chars = string.ascii_letters + string.digits + '_-.'
    rest_chars = ''.join(random.choices(valid_chars, k=random.randint(0, 50)))
    return start_char + rest_chars


def generate_valid_tag_name():
    """Generate a valid tag name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    # Valid chars: alphanumeric, underscore, hyphen (no period)
    valid_chars = string.ascii_letters + string.digits + '_-'
    rest_chars = ''.join(random.choices(valid_chars, k=random.randint(0, 30)))
    return start_char + rest_chars


# =============================================================================
# Resource Name Validation Tests - Property 2
# =============================================================================

def test_valid_resource_names_pass_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 1.7**
    
    Valid resource names with alphanumeric start and allowed characters should pass.
    """
    valid_names = [
        "resource123",
        "test_resource",
        "my-resource",
        "Resource_Name-123",
        "a",
        "ABC",
        "resource_with_underscore",
        "resource-with-hyphen",
        "resource.with.period",
        "MixedCase123",
        "x" * 128,  # Max length
        "server.prod.us-east-1",
        "device_01",
        "ip-192.168.1.1",
    ]
    
    for name in valid_names:
        result = validate_resource_name(name)
        assert result is True, f"Valid resource name '{name}' should pass validation"


def test_generated_valid_resource_names_pass_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 1.7**
    
    For any generated valid resource name, validation should pass.
    Property: For all strings containing only alphanumeric, underscore, hyphen, and period
    characters that start with alphanumeric, validation should return True.
    """
    for _ in range(100):
        name = generate_valid_resource_name()
        result = validate_resource_name(name)
        assert result is True, f"Generated valid resource name '{name}' should pass validation"


def test_resource_names_with_invalid_chars_fail_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 1.7**
    
    Resource names with special characters (other than underscore, hyphen, period) should fail validation.
    """
    invalid_chars = "!@#$%^&*()+=[]{}|;':\"<>?`~ "
    
    for char in invalid_chars:
        name = f"valid{char}resource"
        result = validate_resource_name(name)
        assert result is False, f"Resource name '{name}' with invalid char '{char}' should fail"


def test_resource_names_starting_with_non_alphanumeric_fail():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 1.7**
    
    Resource names starting with underscore, hyphen, or period should fail.
    """
    invalid_starts = ['_validresource', '-validresource', '.validresource', '_123', '-abc', '.test']
    
    for name in invalid_starts:
        result = validate_resource_name(name)
        assert result is False, f"Resource name '{name}' starting with non-alphanumeric should fail"


def test_empty_resource_name_fails_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 1.7**
    
    Empty and None resource names should fail validation.
    """
    result = validate_resource_name("")
    assert result is False, "Empty resource name should fail validation"
    
    result = validate_resource_name(None)
    assert result is False, "None resource name should fail validation"


def test_long_resource_names_fail_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 1.7**
    
    Resource names longer than 128 characters should fail.
    """
    long_name = "a" * 129
    result = validate_resource_name(long_name)
    assert result is False, f"Resource name with {len(long_name)} chars should fail validation"


def test_resource_name_boundary_lengths():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 1.7**
    
    Test boundary conditions for resource name length.
    """
    # Single character (minimum valid)
    result = validate_resource_name("a")
    assert result is True, "Single character resource name should pass"
    
    # 128 characters (maximum valid)
    result = validate_resource_name("a" * 128)
    assert result is True, "128 character resource name should pass"
    
    # 129 characters (too long)
    result = validate_resource_name("a" * 129)
    assert result is False, "129 character resource name should fail"


# =============================================================================
# Tag Name Validation Tests
# =============================================================================

def test_valid_tag_names_pass_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 7.5**
    
    Valid tag names with alphanumeric start and allowed characters should pass.
    """
    valid_tags = [
        "tag123",
        "test_tag",
        "my-tag",
        "Tag_Name-123",
        "a",
        "ABC",
        "tag_with_underscore",
        "tag-with-hyphen",
        "MixedCase123",
        "x" * 64,  # Max length
    ]
    
    for tag in valid_tags:
        result = validate_tag_name(tag)
        assert result is True, f"Valid tag name '{tag}' should pass validation"


def test_generated_valid_tag_names_pass_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 7.5**
    
    For any generated valid tag name, validation should pass.
    Property: For all strings containing only alphanumeric, underscore, and hyphen
    characters that start with alphanumeric, validation should return True.
    """
    for _ in range(100):
        tag = generate_valid_tag_name()
        result = validate_tag_name(tag)
        assert result is True, f"Generated valid tag name '{tag}' should pass validation"


def test_tag_names_with_period_fail_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 7.5**
    
    Tag names with periods should fail validation (unlike resource names).
    """
    invalid_tags = [
        "tag.with.period",
        "test.tag",
        "a.b",
    ]
    
    for tag in invalid_tags:
        result = validate_tag_name(tag)
        assert result is False, f"Tag name '{tag}' with period should fail validation"


def test_tag_names_with_invalid_chars_fail_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 7.5**
    
    Tag names with special characters should fail validation.
    """
    invalid_chars = "!@#$%^&*()+=[]{}|;':\"<>?`~ ."
    
    for char in invalid_chars:
        tag = f"valid{char}tag"
        result = validate_tag_name(tag)
        assert result is False, f"Tag name '{tag}' with invalid char '{char}' should fail"


def test_tag_names_starting_with_non_alphanumeric_fail():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 7.5**
    
    Tag names starting with underscore or hyphen should fail.
    """
    invalid_starts = ['_validtag', '-validtag', '_123', '-abc']
    
    for tag in invalid_starts:
        result = validate_tag_name(tag)
        assert result is False, f"Tag name '{tag}' starting with non-alphanumeric should fail"


def test_empty_tag_name_fails_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 7.5**
    
    Empty and None tag names should fail validation.
    """
    result = validate_tag_name("")
    assert result is False, "Empty tag name should fail validation"
    
    result = validate_tag_name(None)
    assert result is False, "None tag name should fail validation"


def test_long_tag_names_fail_validation():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 7.5**
    
    Tag names longer than 64 characters should fail.
    """
    long_tag = "a" * 65
    result = validate_tag_name(long_tag)
    assert result is False, f"Tag name with {len(long_tag)} chars should fail validation"


def test_tag_name_boundary_lengths():
    """
    **Feature: resources, Property 2: Resource Name Validation**
    **Validates: Requirements 7.5**
    
    Test boundary conditions for tag name length.
    """
    # Single character (minimum valid)
    result = validate_tag_name("a")
    assert result is True, "Single character tag name should pass"
    
    # 64 characters (maximum valid)
    result = validate_tag_name("a" * 64)
    assert result is True, "64 character tag name should pass"
    
    # 65 characters (too long)
    result = validate_tag_name("a" * 65)
    assert result is False, "65 character tag name should fail"
