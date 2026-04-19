"""
.. module:: test_release_manager_semantic_version
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for ReleaseManager semantic version validation

.. moduleauthor:: Automation Mojo LLC

Property tests for semantic version validation in the ReleaseManager.

**Feature: projects**
**Property 12: Semantic Version Validation**
**Validates: Requirements 16.5**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.pychestrate.core.managers.release_manager import (
    validate_semantic_version,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_basic_semver():
    """Generate a random basic semantic version (major.minor.patch)."""
    major = random.randint(0, 999)
    minor = random.randint(0, 999)
    patch = random.randint(0, 999)
    return f"{major}.{minor}.{patch}"


def generate_semver_with_prerelease():
    """Generate a random semantic version with pre-release tag."""
    major = random.randint(0, 99)
    minor = random.randint(0, 99)
    patch = random.randint(0, 99)
    
    prerelease_tags = ['alpha', 'beta', 'rc', 'dev', 'pre']
    tag = random.choice(prerelease_tags)
    
    # Optionally add a numeric suffix
    if random.choice([True, False]):
        tag_num = random.randint(1, 99)
        return f"{major}.{minor}.{patch}-{tag}.{tag_num}"
    
    return f"{major}.{minor}.{patch}-{tag}"


def generate_semver_with_build_metadata():
    """Generate a random semantic version with build metadata."""
    major = random.randint(0, 99)
    minor = random.randint(0, 99)
    patch = random.randint(0, 99)
    
    # Generate alphanumeric build metadata
    build_chars = string.ascii_lowercase + string.digits
    build = ''.join(random.choices(build_chars, k=random.randint(1, 10)))
    
    return f"{major}.{minor}.{patch}+{build}"


def generate_semver_with_prerelease_and_build():
    """Generate a random semantic version with both pre-release and build metadata."""
    major = random.randint(0, 99)
    minor = random.randint(0, 99)
    patch = random.randint(0, 99)
    
    prerelease_tags = ['alpha', 'beta', 'rc']
    tag = random.choice(prerelease_tags)
    
    build_chars = string.ascii_lowercase + string.digits
    build = ''.join(random.choices(build_chars, k=random.randint(1, 10)))
    
    return f"{major}.{minor}.{patch}-{tag}+{build}"


def generate_invalid_semver():
    """Generate an invalid semantic version string."""
    invalid_patterns = [
        lambda: "",  # Empty string
        lambda: str(random.randint(0, 99)),  # Missing minor and patch
        lambda: f"{random.randint(0, 99)}.{random.randint(0, 99)}",  # Missing patch
        lambda: f"{random.randint(0, 99)}.{random.randint(0, 99)}.{random.randint(0, 99)}.{random.randint(0, 99)}",  # Too many parts
        lambda: f"v{random.randint(0, 99)}.{random.randint(0, 99)}.{random.randint(0, 99)}",  # Leading 'v'
        lambda: f"0{random.randint(1, 9)}.0.0",  # Leading zero in major
        lambda: f"1.0{random.randint(1, 9)}.0",  # Leading zero in minor
        lambda: f"1.0.0{random.randint(1, 9)}",  # Leading zero in patch
        lambda: f"{random.choice(string.ascii_letters)}.{random.choice(string.ascii_letters)}.{random.choice(string.ascii_letters)}",  # Non-numeric parts
        lambda: f"-{random.randint(1, 99)}.0.0",  # Negative major
    ]
    
    return random.choice(invalid_patterns)()


# =============================================================================
# Semantic Version Validation Tests - Property 12
# =============================================================================

def test_valid_basic_semver():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Basic semantic versions (major.minor.patch) should be valid.
    """
    valid_versions = [
        "0.0.0",
        "1.0.0",
        "0.1.0",
        "0.0.1",
        "1.2.3",
        "10.20.30",
        "100.200.300",
    ]
    
    for version in valid_versions:
        assert validate_semantic_version(version), \
            f"Version '{version}' should be valid"


def test_valid_semver_with_prerelease():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Semantic versions with pre-release identifiers should be valid.
    """
    valid_versions = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-0.3.7",
        "1.0.0-x.7.z.92",
        "1.0.0-alpha.beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
    ]
    
    for version in valid_versions:
        assert validate_semantic_version(version), \
            f"Version '{version}' should be valid"


def test_valid_semver_with_build_metadata():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Semantic versions with build metadata should be valid.
    """
    valid_versions = [
        "1.0.0+build",
        "1.0.0+20130313144700",
        "1.0.0+build.123",
        "1.0.0+exp.sha.5114f85",
    ]
    
    for version in valid_versions:
        assert validate_semantic_version(version), \
            f"Version '{version}' should be valid"


def test_valid_semver_with_prerelease_and_build():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Semantic versions with both pre-release and build metadata should be valid.
    """
    valid_versions = [
        "1.0.0-alpha+001",
        "1.0.0-alpha.1+build.123",
        "1.0.0-beta+exp.sha.5114f85",
    ]
    
    for version in valid_versions:
        assert validate_semantic_version(version), \
            f"Version '{version}' should be valid"


def test_invalid_semver_formats():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Invalid semantic version formats should be rejected.
    """
    invalid_versions = [
        "",           # Empty string
        "1",          # Missing minor and patch
        "1.0",        # Missing patch
        "1.0.0.0",    # Too many parts
        "v1.0.0",     # Leading 'v'
        "1.0.0-",     # Empty pre-release
        "1.0.0+",     # Empty build metadata
        "01.0.0",     # Leading zero in major
        "1.01.0",     # Leading zero in minor
        "1.0.01",     # Leading zero in patch
        "a.b.c",      # Non-numeric parts
        "1.0.0-01",   # Leading zero in numeric pre-release
        "-1.0.0",     # Negative major
        "1.-1.0",     # Negative minor
        "1.0.-1",     # Negative patch
    ]
    
    for version in invalid_versions:
        assert not validate_semantic_version(version), \
            f"Version '{version}' should be invalid"


def test_empty_version_invalid():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Empty version string should be invalid.
    """
    assert not validate_semantic_version(""), "Empty string should be invalid"
    assert not validate_semantic_version(None), "None should be invalid"


def test_property_basic_semver_valid():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Property test: For any generated major.minor.patch version,
    the validation should pass.
    """
    for _ in range(100):
        version = generate_basic_semver()
        assert validate_semantic_version(version), \
            f"Generated version '{version}' should be valid"


def test_property_any_non_negative_integers_valid():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Property test: For any non-negative integers as major, minor, patch,
    the resulting version string should be valid.
    """
    for _ in range(100):
        major = random.randint(0, 999)
        minor = random.randint(0, 999)
        patch = random.randint(0, 999)
        version = f"{major}.{minor}.{patch}"
        
        assert validate_semantic_version(version), \
            f"Version '{version}' should be valid"


def test_leading_zeros_in_numeric_parts_invalid():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Leading zeros in numeric parts should be invalid per semver spec.
    """
    invalid_versions = [
        "01.0.0",
        "1.01.0",
        "1.0.01",
        "001.0.0",
        "1.001.0",
        "1.0.001",
    ]
    
    for version in invalid_versions:
        assert not validate_semantic_version(version), \
            f"Version '{version}' with leading zeros should be invalid"


def test_zero_versions_valid():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Zero versions (0.x.x) should be valid for initial development.
    """
    valid_versions = [
        "0.0.0",
        "0.0.1",
        "0.1.0",
        "0.1.1",
    ]
    
    for version in valid_versions:
        assert validate_semantic_version(version), \
            f"Zero version '{version}' should be valid"


def test_prerelease_identifiers_rules():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Pre-release identifiers must follow semver rules:
    - Alphanumeric and hyphen only
    - Numeric identifiers must not have leading zeros
    """
    # Valid pre-release identifiers
    valid_versions = [
        "1.0.0-alpha",
        "1.0.0-alpha1",
        "1.0.0-alpha-1",
        "1.0.0-0",
        "1.0.0-1",
        "1.0.0-123",
    ]
    
    for version in valid_versions:
        assert validate_semantic_version(version), \
            f"Version '{version}' should be valid"


def test_build_metadata_rules():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Build metadata must follow semver rules:
    - Alphanumeric and hyphen only
    - Can have leading zeros (unlike pre-release)
    """
    valid_versions = [
        "1.0.0+build",
        "1.0.0+001",
        "1.0.0+20130313144700",
        "1.0.0+build-123",
    ]
    
    for version in valid_versions:
        assert validate_semantic_version(version), \
            f"Version '{version}' should be valid"


def test_version_comparison_ordering():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Test that various versions in a typical release sequence are all valid.
    """
    release_sequence = [
        "0.1.0",
        "0.2.0",
        "0.2.1",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-rc.1",
        "1.0.0",
        "1.0.1",
        "1.1.0",
        "2.0.0",
    ]
    
    for version in release_sequence:
        assert validate_semantic_version(version), \
            f"Version '{version}' in release sequence should be valid"


def test_property_semver_with_common_prerelease_tags():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Property test: Versions with common pre-release tags should be valid.
    """
    prerelease_tags = ['alpha', 'beta', 'rc', 'dev', 'pre']
    
    for _ in range(100):
        major = random.randint(0, 99)
        minor = random.randint(0, 99)
        patch = random.randint(0, 99)
        tag = random.choice(prerelease_tags)
        version = f"{major}.{minor}.{patch}-{tag}"
        
        assert validate_semantic_version(version), \
            f"Version '{version}' should be valid"


def test_property_semver_with_build_metadata():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Property test: Versions with build metadata should be valid.
    """
    for _ in range(100):
        major = random.randint(0, 99)
        minor = random.randint(0, 99)
        patch = random.randint(0, 99)
        build_chars = string.ascii_lowercase + string.digits
        build = ''.join(random.choices(build_chars, k=random.randint(1, 10)))
        version = f"{major}.{minor}.{patch}+{build}"
        
        assert validate_semantic_version(version), \
            f"Version '{version}' should be valid"


def test_property_generated_prerelease_versions_valid():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Property test: Generated versions with pre-release tags should be valid.
    """
    for _ in range(100):
        version = generate_semver_with_prerelease()
        assert validate_semantic_version(version), \
            f"Generated version '{version}' should be valid"


def test_property_generated_build_metadata_versions_valid():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Property test: Generated versions with build metadata should be valid.
    """
    for _ in range(100):
        version = generate_semver_with_build_metadata()
        assert validate_semantic_version(version), \
            f"Generated version '{version}' should be valid"


def test_property_generated_full_versions_valid():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Property test: Generated versions with both pre-release and build metadata should be valid.
    """
    for _ in range(100):
        version = generate_semver_with_prerelease_and_build()
        assert validate_semantic_version(version), \
            f"Generated version '{version}' should be valid"


def test_property_validation_is_deterministic():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Property test: For any version string, calling validate_semantic_version
    multiple times should always return the same result.
    """
    test_versions = [
        "1.0.0",
        "1.0.0-alpha",
        "1.0.0+build",
        "invalid",
        "",
        "01.0.0",
    ]
    
    for version in test_versions:
        results = [validate_semantic_version(version) for _ in range(10)]
        assert all(r == results[0] for r in results), \
            f"Validation for '{version}' should be deterministic"


def test_property_valid_semver_accepted_invalid_rejected():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Property test: For any version string, the validation function accepts it
    if and only if it conforms to semantic versioning.
    """
    # Test valid versions are accepted
    for _ in range(50):
        valid_version = generate_basic_semver()
        assert validate_semantic_version(valid_version), \
            f"Valid version '{valid_version}' should be accepted"
    
    # Test invalid versions are rejected
    for _ in range(50):
        invalid_version = generate_invalid_semver()
        # Skip empty strings as they're handled separately
        if invalid_version == "":
            continue
        assert not validate_semantic_version(invalid_version), \
            f"Invalid version '{invalid_version}' should be rejected"


def test_semver_edge_cases():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Test edge cases for semantic version validation.
    """
    # Large version numbers
    assert validate_semantic_version("999.999.999"), \
        "Large version numbers should be valid"
    
    # Long pre-release identifier
    assert validate_semantic_version("1.0.0-alpha.beta.gamma.delta"), \
        "Long pre-release identifiers should be valid"
    
    # Long build metadata
    assert validate_semantic_version("1.0.0+build.20230101.commit.abc123"), \
        "Long build metadata should be valid"
    
    # Hyphen in pre-release
    assert validate_semantic_version("1.0.0-alpha-beta"), \
        "Hyphen in pre-release should be valid"
    
    # Numeric pre-release
    assert validate_semantic_version("1.0.0-0"), \
        "Numeric pre-release '0' should be valid"
    assert validate_semantic_version("1.0.0-123"), \
        "Numeric pre-release should be valid"


def test_custom_pattern_validation():
    """
    **Feature: projects, Property 12: Semantic Version Validation**
    **Validates: Requirements 16.5**
    
    Test that the ReleaseManager.validate_version method supports custom patterns.
    """
    from automojo.pychestrate.core.managers.release_manager import ReleaseManager
    
    # Create a manager with a mock session
    from automojo.testbase.mocking import Mock
    mock_session = Mock()
    mock_session.configure(recursive=True)
    manager = ReleaseManager(mock_session)
    
    # Test with default semver pattern
    assert manager.validate_version("1.0.0"), \
        "Valid semver should pass with default pattern"
    assert not manager.validate_version("invalid"), \
        "Invalid semver should fail with default pattern"
    
    # Test with custom pattern (e.g., date-based versioning)
    date_pattern = r'^\d{4}\.\d{2}\.\d{2}$'
    assert manager.validate_version("2023.01.15", pattern=date_pattern), \
        "Date version should pass with custom pattern"
    assert not manager.validate_version("1.0.0", pattern=date_pattern), \
        "Semver should fail with date pattern"
    
    # Test with invalid regex pattern
    assert not manager.validate_version("1.0.0", pattern="[invalid"), \
        "Invalid regex pattern should return False"

