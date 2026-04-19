"""
.. module:: test_project_manager_name_validation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ProjectManager project name validation

.. moduleauthor:: Automation Mojo LLC

Tests for project name validation in the ProjectManager.

**Feature: projects**
**Property 2: Project Name Validation**
**Validates: Requirements 1.6**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.pychestrate.core.managers.project_manager import validate_project_name


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_valid_project_name():
    """Generate a valid project name for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    # Valid chars: alphanumeric, underscore, hyphen, period
    valid_chars = string.ascii_letters + string.digits + '_-.'
    rest_chars = ''.join(random.choices(valid_chars, k=random.randint(0, 50)))
    return start_char + rest_chars


# =============================================================================
# Project Name Validation Tests - Property 2
# =============================================================================

def test_valid_project_names_pass_validation():
    """
    **Feature: projects, Property 2: Project Name Validation**
    **Validates: Requirements 1.6**
    
    Valid project names with alphanumeric start and allowed characters should pass.
    """
    valid_names = [
        "project123",
        "test_project",
        "my-project",
        "Project_Name-123",
        "a",
        "ABC",
        "project_with_underscore",
        "project-with-hyphen",
        "project.with.period",
        "MixedCase123",
        "x" * 128,  # Max length
        "server.prod.us-east-1",
        "project_01",
        "ci-cd.pipeline",
    ]
    
    for name in valid_names:
        result = validate_project_name(name)
        assert result is True, f"Valid project name '{name}' should pass validation"


def test_generated_valid_project_names_pass_validation():
    """
    **Feature: projects, Property 2: Project Name Validation**
    **Validates: Requirements 1.6**
    
    For any generated valid project name, validation should pass.
    Property: For all strings containing only alphanumeric, underscore, hyphen, and period
    characters that start with alphanumeric, validation should return True.
    """
    for _ in range(100):
        name = generate_valid_project_name()
        result = validate_project_name(name)
        assert result is True, f"Generated valid project name '{name}' should pass validation"


def test_project_names_with_invalid_chars_fail_validation():
    """
    **Feature: projects, Property 2: Project Name Validation**
    **Validates: Requirements 1.6**
    
    Project names with special characters (other than underscore, hyphen, period) should fail validation.
    """
    invalid_chars = "!@#$%^&*()+=[]{}|;':\"<>?`~ "
    
    for char in invalid_chars:
        name = f"valid{char}project"
        result = validate_project_name(name)
        assert result is False, f"Project name '{name}' with invalid char '{char}' should fail"


def test_project_names_starting_with_non_alphanumeric_fail():
    """
    **Feature: projects, Property 2: Project Name Validation**
    **Validates: Requirements 1.6**
    
    Project names starting with underscore, hyphen, or period should fail.
    """
    invalid_starts = ['_validproject', '-validproject', '.validproject', '_123', '-abc', '.test']
    
    for name in invalid_starts:
        result = validate_project_name(name)
        assert result is False, f"Project name '{name}' starting with non-alphanumeric should fail"


def test_empty_project_name_fails_validation():
    """
    **Feature: projects, Property 2: Project Name Validation**
    **Validates: Requirements 1.6**
    
    Empty and None project names should fail validation.
    """
    result = validate_project_name("")
    assert result is False, "Empty project name should fail validation"
    
    result = validate_project_name(None)
    assert result is False, "None project name should fail validation"


def test_long_project_names_fail_validation():
    """
    **Feature: projects, Property 2: Project Name Validation**
    **Validates: Requirements 1.6**
    
    Project names longer than 128 characters should fail.
    """
    long_name = "a" * 129
    result = validate_project_name(long_name)
    assert result is False, f"Project name with {len(long_name)} chars should fail validation"


def test_project_name_boundary_lengths():
    """
    **Feature: projects, Property 2: Project Name Validation**
    **Validates: Requirements 1.6**
    
    Test boundary conditions for project name length.
    """
    # Single character (minimum valid)
    result = validate_project_name("a")
    assert result is True, "Single character project name should pass"
    
    # 128 characters (maximum valid)
    result = validate_project_name("a" * 128)
    assert result is True, "128 character project name should pass"
    
    # 129 characters (too long)
    result = validate_project_name("a" * 129)
    assert result is False, "129 character project name should fail"


def test_project_name_validation_is_deterministic():
    """
    **Feature: projects, Property 2: Project Name Validation**
    **Validates: Requirements 1.6**
    
    Property: For any string, calling validate_project_name multiple times
    should always return the same result.
    """
    test_names = [
        "valid_project",
        "invalid project",
        "_invalid",
        "a" * 128,
        "a" * 129,
        "",
    ]
    
    for name in test_names:
        results = [validate_project_name(name) for _ in range(10)]
        assert all(r == results[0] for r in results), \
            f"Validation for '{name}' should be deterministic"


def test_project_name_accepts_only_valid_characters():
    """
    **Feature: projects, Property 2: Project Name Validation**
    **Validates: Requirements 1.6**
    
    Property: For any string, validation accepts it if and only if it contains
    only alphanumeric characters, underscores, hyphens, and periods.
    """
    # Test common special characters (excluding whitespace which is handled separately)
    special_chars = "!@#$%^&*()+=[]{}|;':\"<>?`~"
    
    for char in string.ascii_letters + string.digits:
        # Alphanumeric at start should pass
        result = validate_project_name(char)
        assert result is True, f"Alphanumeric char '{char}' should pass as single char name"
    
    for char in '_-.':
        # These are valid but not at start
        result = validate_project_name(char)
        assert result is False, f"Char '{char}' should fail at start"
        # But valid after alphanumeric
        result = validate_project_name(f"a{char}")
        assert result is True, f"Char '{char}' should pass after alphanumeric"
    
    for char in special_chars:
        # All special chars should fail
        result = validate_project_name(f"a{char}")
        assert result is False, f"Char '{repr(char)}' should fail validation"
    
    # Test whitespace characters
    for char in ' \t\n\r':
        result = validate_project_name(f"a{char}")
        assert result is False, f"Whitespace char '{repr(char)}' should fail validation"
