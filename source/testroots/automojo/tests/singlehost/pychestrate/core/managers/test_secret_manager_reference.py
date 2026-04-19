"""
.. module:: test_secret_manager_reference
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for SecretManager secret reference resolution

.. moduleauthor:: Automation Mojo LLC

Property tests for secret reference resolution - parsing ${scope/name} format.

**Feature: system-configuration**
**Property 32: Secret Reference Resolution**
**Validates: Requirements 11.10**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import re

from automojo.pychestrate.core.managers.secret_manager import (
    SecretManager,
    InvalidSecretReferenceError,
    ScopeNotFoundError,
    generate_encryption_key,
    SECRET_REFERENCE_PATTERN,
)

from automojo.testbase.mocking import Mock


# =============================================================================
# Mock Factories
# =============================================================================

def create_mock_session():
    """Create a basic mock database session."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    return mock_session


def generate_scope_name():
    """Generate a random scope name."""
    prefix = ''.join(random.choices(string.ascii_lowercase, k=8))
    return f"scope_{prefix}"


def generate_secret_name():
    """Generate a random secret name."""
    prefix = ''.join(random.choices(string.ascii_lowercase, k=8))
    return f"secret_{prefix}"


# =============================================================================
# Property Tests - Property 32: Secret Reference Resolution
# =============================================================================

def test_invalid_reference_format_raises_error():
    """
    **Feature: system-configuration, Property 32: Secret Reference Resolution**
    **Validates: Requirements 11.10**
    
    Invalid reference formats should raise InvalidSecretReferenceError.
    """
    # These formats definitely don't match the pattern ${scope/name}
    invalid_formats = [
        "scope/secret",           # Missing ${}
        "${scope}",               # Missing /secret
        "${/secret}",             # Missing scope (empty scope)
        "${scope/}",              # Missing secret name (empty name)
        "${}",                    # Empty
        "{}",                     # Missing $
        "plain_text",             # No reference syntax
        "",                       # Empty string
        "${",                     # Incomplete
        "}",                      # Just closing brace
        "$ {scope/secret}",       # Space after $
    ]
    
    for invalid_ref in invalid_formats:
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        manager = SecretManager(mock_session, key)
        
        try:
            manager.resolve_secret_reference(invalid_ref)
            assert False, f"Should have raised InvalidSecretReferenceError for '{invalid_ref}'"
        except InvalidSecretReferenceError:
            pass  # Expected


def test_nonexistent_scope_raises_error():
    """
    **Feature: system-configuration, Property 32: Secret Reference Resolution**
    **Validates: Requirements 11.10**
    
    References to non-existent scopes should raise ScopeNotFoundError.
    """
    for _ in range(100):
        mock_session = create_mock_session()
        key = generate_encryption_key()
        
        scope_name = generate_scope_name()
        secret_name = generate_secret_name()
        reference = f"${{{scope_name}/{secret_name}}}"
        
        def create_query_for_model(*args, **kwargs):
            mock_query = Mock()
            mock_query.configure(recursive=True)
            
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            # Scope not found
            mock_filter.mock_context().mock_method('first', return_value=None)
            mock_filter.mock_context().mock_method('count', return_value=0)
            
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            return mock_query
        
        mock_session.mock_context().mock_method('query', side_effect=create_query_for_model)
        
        manager = SecretManager(mock_session, key)
        
        try:
            manager.resolve_secret_reference(reference)
            assert False, "Should have raised ScopeNotFoundError"
        except ScopeNotFoundError as e:
            assert scope_name in str(e)


def test_reference_pattern_matches_valid_formats():
    """
    **Feature: system-configuration, Property 32: Secret Reference Resolution**
    **Validates: Requirements 11.10**
    
    The SECRET_REFERENCE_PATTERN should match valid ${scope/name} formats.
    """
    for _ in range(100):
        scope_name = generate_scope_name()
        secret_name = generate_secret_name()
        reference = f"${{{scope_name}/{secret_name}}}"
        
        match = SECRET_REFERENCE_PATTERN.match(reference)
        
        assert match is not None, f"Pattern should match '{reference}'"
        assert match.group(1) == scope_name, f"Scope name should be '{scope_name}'"
        assert match.group(2) == secret_name, f"Secret name should be '{secret_name}'"


def test_reference_pattern_rejects_invalid_formats():
    """
    **Feature: system-configuration, Property 32: Secret Reference Resolution**
    **Validates: Requirements 11.10**
    
    The SECRET_REFERENCE_PATTERN should not match invalid formats.
    """
    invalid_formats = [
        "scope/secret",           # Missing ${}
        "${scope}",               # Missing /secret
        "${}",                    # Empty
        "{}",                     # Missing $
        "plain_text",             # No reference syntax
        "",                       # Empty string
        "${",                     # Incomplete
        "}",                      # Just closing brace
        "$ {scope/secret}",       # Space after $
    ]
    
    for invalid_ref in invalid_formats:
        match = SECRET_REFERENCE_PATTERN.match(invalid_ref)
        assert match is None, f"Pattern should not match '{invalid_ref}'"


def test_reference_pattern_with_various_name_formats():
    """
    **Feature: system-configuration, Property 32: Secret Reference Resolution**
    **Validates: Requirements 11.10**
    
    The pattern should match various valid name formats.
    """
    valid_name_chars = string.ascii_letters + string.digits + "_-"
    
    for _ in range(100):
        # Generate names with various characters
        scope_name = ''.join(random.choices(valid_name_chars, k=random.randint(1, 20)))
        secret_name = ''.join(random.choices(valid_name_chars, k=random.randint(1, 20)))
        
        reference = f"${{{scope_name}/{secret_name}}}"
        
        match = SECRET_REFERENCE_PATTERN.match(reference)
        
        assert match is not None, f"Pattern should match '{reference}'"
        assert match.group(1) == scope_name
        assert match.group(2) == secret_name


def test_reference_format_consistency():
    """
    **Feature: system-configuration, Property 32: Secret Reference Resolution**
    **Validates: Requirements 11.10**
    
    Reference format should be consistent: ${scope/name}
    """
    for _ in range(100):
        scope_name = generate_scope_name()
        secret_name = generate_secret_name()
        
        # Build reference
        reference = f"${{{scope_name}/{secret_name}}}"
        
        # Verify format
        assert reference.startswith("${"), "Reference should start with '${''"
        assert reference.endswith("}"), "Reference should end with '}'"
        assert "/" in reference, "Reference should contain '/'"
        
        # Extract parts
        inner = reference[2:-1]  # Remove ${ and }
        parts = inner.split("/")
        
        assert len(parts) == 2, "Reference should have exactly two parts"
        assert parts[0] == scope_name, "First part should be scope name"
        assert parts[1] == secret_name, "Second part should be secret name"
