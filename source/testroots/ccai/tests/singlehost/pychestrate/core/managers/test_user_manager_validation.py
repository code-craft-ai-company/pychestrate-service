"""
.. module:: test_user_manager_validation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for UserManager validation methods

.. moduleauthor:: Code Craft AI LLC

Tests for username and email validation in the UserManager.

**Feature: system-configuration**
**Property 2: Username Validation**
**Validates: Requirements 1.6**

**Property 3: Email Validation**
**Validates: Requirements 1.7**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from ccai.pychestrate.core.managers.user_manager import validate_username, validate_email


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_valid_username():
    """Generate a valid username for testing."""
    start_char = random.choice(string.ascii_letters + string.digits)
    rest_chars = ''.join(random.choices(string.ascii_letters + string.digits + '_-', k=random.randint(2, 20)))
    return start_char + rest_chars


def generate_valid_email():
    """Generate a valid email for testing."""
    local_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(3, 10)))
    domain = ''.join(random.choices(string.ascii_lowercase, k=random.randint(3, 8)))
    tld = random.choice(['com', 'org', 'net', 'io', 'dev'])
    return f"{local_part}@{domain}.{tld}"


# =============================================================================
# Username Validation Tests - Property 2
# =============================================================================

def test_valid_usernames_pass_validation():
    """
    **Feature: system-configuration, Property 2: Username Validation**
    **Validates: Requirements 1.6**
    
    Valid usernames with alphanumeric start and allowed characters should pass.
    """
    valid_usernames = [
        "user123",
        "test_user",
        "my-username",
        "User_Name-123",
        "a12",
        "ABC",
        "user_with_underscore",
        "user-with-hyphen",
        "MixedCase123",
        "x" * 64,  # Max length
    ]
    
    for username in valid_usernames:
        result = validate_username(username)
        assert result is True, f"Valid username '{username}' should pass validation"


def test_generated_valid_usernames_pass_validation():
    """
    **Feature: system-configuration, Property 2: Username Validation**
    **Validates: Requirements 1.6**
    
    For any generated valid username, validation should pass.
    """
    for _ in range(100):
        username = generate_valid_username()
        result = validate_username(username)
        assert result is True, f"Generated valid username '{username}' should pass validation"


def test_usernames_with_invalid_chars_fail_validation():
    """
    **Feature: system-configuration, Property 2: Username Validation**
    **Validates: Requirements 1.6**
    
    Usernames with special characters should fail validation.
    """
    invalid_chars = "!@#$%^&*()+=[]{}|;':\",./<>?`~ "
    
    for char in invalid_chars:
        username = f"valid{char}user"
        result = validate_username(username)
        assert result is False, f"Username '{username}' with invalid char '{char}' should fail"


def test_usernames_starting_with_non_alphanumeric_fail():
    """
    **Feature: system-configuration, Property 2: Username Validation**
    **Validates: Requirements 1.6**
    
    Usernames starting with underscore or hyphen should fail.
    """
    invalid_starts = ['_validuser', '-validuser', '_123', '-abc']
    
    for username in invalid_starts:
        result = validate_username(username)
        assert result is False, f"Username '{username}' starting with non-alphanumeric should fail"


def test_short_usernames_fail_validation():
    """
    **Feature: system-configuration, Property 2: Username Validation**
    **Validates: Requirements 1.6**
    
    Usernames shorter than 3 characters should fail.
    """
    short_usernames = ['a', 'ab', 'x', '12']
    
    for username in short_usernames:
        result = validate_username(username)
        assert result is False, f"Short username '{username}' should fail validation"


def test_empty_username_fails_validation():
    """
    **Feature: system-configuration, Property 2: Username Validation**
    **Validates: Requirements 1.6**
    
    Empty and None usernames should fail validation.
    """
    result = validate_username("")
    assert result is False, "Empty username should fail validation"
    
    result = validate_username(None)
    assert result is False, "None username should fail validation"


def test_long_usernames_fail_validation():
    """
    **Feature: system-configuration, Property 2: Username Validation**
    **Validates: Requirements 1.6**
    
    Usernames longer than 64 characters should fail.
    """
    long_username = "a" * 65
    result = validate_username(long_username)
    assert result is False, f"Username with {len(long_username)} chars should fail validation"


# =============================================================================
# Email Validation Tests - Property 3
# =============================================================================

def test_valid_emails_pass_validation():
    """
    **Feature: system-configuration, Property 3: Email Validation**
    **Validates: Requirements 1.7**
    
    Valid email addresses should pass validation.
    """
    valid_emails = [
        "user@example.com",
        "test.user@domain.org",
        "user123@test.net",
        "user+tag@example.io",
        "user_name@domain.co",
        "a@b.cd",
        "user.name.here@subdomain.example.com",
    ]
    
    for email in valid_emails:
        result = validate_email(email)
        assert result is True, f"Valid email '{email}' should pass validation"


def test_generated_valid_emails_pass_validation():
    """
    **Feature: system-configuration, Property 3: Email Validation**
    **Validates: Requirements 1.7**
    
    For any generated valid email, validation should pass.
    """
    for _ in range(100):
        email = generate_valid_email()
        result = validate_email(email)
        assert result is True, f"Generated valid email '{email}' should pass validation"


def test_emails_without_at_fail_validation():
    """
    **Feature: system-configuration, Property 3: Email Validation**
    **Validates: Requirements 1.7**
    
    Emails without @ symbol should fail validation.
    """
    invalid_emails = [
        "userexample.com",
        "testdomain.org",
        "nodomain",
        "just.dots.here",
    ]
    
    for email in invalid_emails:
        result = validate_email(email)
        assert result is False, f"Email '{email}' without @ should fail validation"


def test_emails_without_domain_fail_validation():
    """
    **Feature: system-configuration, Property 3: Email Validation**
    **Validates: Requirements 1.7**
    
    Emails without proper domain should fail validation.
    """
    invalid_emails = [
        "user@",
        "user@nodomain",
        "user@.com",
        "user@domain.",
    ]
    
    for email in invalid_emails:
        result = validate_email(email)
        assert result is False, f"Email '{email}' without proper domain should fail"


def test_emails_with_single_char_tld_fail_validation():
    """
    **Feature: system-configuration, Property 3: Email Validation**
    **Validates: Requirements 1.7**
    
    Emails with single character TLD should fail validation.
    """
    invalid_emails = [
        "user@domain.a",
        "test@example.x",
    ]
    
    for email in invalid_emails:
        result = validate_email(email)
        assert result is False, f"Email '{email}' with single char TLD should fail"


def test_empty_email_fails_validation():
    """
    **Feature: system-configuration, Property 3: Email Validation**
    **Validates: Requirements 1.7**
    
    Empty and None emails should fail validation.
    """
    result = validate_email("")
    assert result is False, "Empty email should fail validation"
    
    result = validate_email(None)
    assert result is False, "None email should fail validation"


def test_emails_with_multiple_at_fail_validation():
    """
    **Feature: system-configuration, Property 3: Email Validation**
    **Validates: Requirements 1.7**
    
    Emails with multiple @ symbols should fail validation.
    """
    invalid_emails = [
        "user@@domain.com",
        "user@domain@example.com",
        "a@b@c.com",
    ]
    
    for email in invalid_emails:
        result = validate_email(email)
        assert result is False, f"Email '{email}' with multiple @ should fail"
