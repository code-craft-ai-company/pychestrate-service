"""
.. module:: test_security_manager_password
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for SecurityManager password validation and hashing

.. moduleauthor:: Automation Mojo LLC

Tests for password strength validation and password hash storage.

**Feature: system-configuration**
**Property 9: Password Strength Validation**
**Validates: Requirements 3.1, 3.2**

**Property 10: Password Hash Storage**
**Validates: Requirements 3.3**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.pychestrate.core.managers.security_manager import (
    validate_password_strength,
    is_password_strong,
    hash_password,
    verify_password,
    MIN_PASSWORD_LENGTH,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_strong_password():
    """Generate a password that meets all strength requirements."""
    # Ensure we have at least one of each required character type
    uppercase = random.choice(string.ascii_uppercase)
    lowercase = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    special = random.choice('!@#$%^&*()_+-=[]{}|;:,.<>?')
    
    # Fill the rest with random characters to meet minimum length
    remaining_length = max(0, MIN_PASSWORD_LENGTH - 4 + random.randint(0, 8))
    remaining = ''.join(random.choices(
        string.ascii_letters + string.digits + '!@#$%^&*()_+-=[]{}|;:,.<>?',
        k=remaining_length
    ))
    
    # Combine and shuffle
    password_chars = list(uppercase + lowercase + digit + special + remaining)
    random.shuffle(password_chars)
    return ''.join(password_chars)


def generate_weak_password_missing_uppercase():
    """Generate a password missing uppercase letters."""
    lowercase = ''.join(random.choices(string.ascii_lowercase, k=8))
    digit = random.choice(string.digits)
    special = random.choice('!@#$%^&*')
    remaining = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return lowercase + digit + special + remaining


def generate_weak_password_missing_lowercase():
    """Generate a password missing lowercase letters."""
    uppercase = ''.join(random.choices(string.ascii_uppercase, k=8))
    digit = random.choice(string.digits)
    special = random.choice('!@#$%^&*')
    remaining = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return uppercase + digit + special + remaining


def generate_weak_password_missing_digit():
    """Generate a password missing digits."""
    uppercase = random.choice(string.ascii_uppercase)
    lowercase = ''.join(random.choices(string.ascii_lowercase, k=8))
    special = random.choice('!@#$%^&*')
    remaining = ''.join(random.choices(string.ascii_letters, k=4))
    return uppercase + lowercase + special + remaining


def generate_weak_password_missing_special():
    """Generate a password missing special characters."""
    uppercase = random.choice(string.ascii_uppercase)
    lowercase = ''.join(random.choices(string.ascii_lowercase, k=8))
    digit = random.choice(string.digits)
    remaining = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
    return uppercase + lowercase + digit + remaining


def generate_short_password():
    """Generate a password that is too short."""
    length = random.randint(1, MIN_PASSWORD_LENGTH - 1)
    return ''.join(random.choices(
        string.ascii_letters + string.digits + '!@#$%^&*',
        k=length
    ))


# =============================================================================
# Property 9: Password Strength Validation Tests
# =============================================================================

def test_strong_passwords_pass_validation():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    Valid strong passwords should pass validation with no violations.
    """
    strong_passwords = [
        "SecurePass123!",
        "MyP@ssw0rd!234",
        "Complex#Pass99",
        "Str0ng!Password",
        "Test@12345678",
        "AbCdEf123!@#",
    ]
    
    for password in strong_passwords:
        violations = validate_password_strength(password)
        assert len(violations) == 0, f"Strong password '{password}' should have no violations, got: {violations}"
        assert is_password_strong(password) is True, f"Strong password '{password}' should be marked as strong"


def test_generated_strong_passwords_pass_validation():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    For any generated strong password, validation should pass with no violations.
    """
    for _ in range(100):
        password = generate_strong_password()
        violations = validate_password_strength(password)
        assert len(violations) == 0, f"Generated strong password '{password}' should have no violations, got: {violations}"
        assert is_password_strong(password) is True, f"Generated strong password '{password}' should be marked as strong"


def test_short_passwords_fail_validation():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    Passwords shorter than 12 characters should fail validation.
    """
    short_passwords = [
        "Short1!",
        "Ab1!",
        "Pass123!",
        "Test@1234",
        "A1!bcdefgh",  # 11 chars
    ]
    
    for password in short_passwords:
        violations = validate_password_strength(password)
        assert any("12 characters" in v for v in violations), \
            f"Short password '{password}' should have length violation"
        assert is_password_strong(password) is False, \
            f"Short password '{password}' should not be marked as strong"


def test_generated_short_passwords_fail_validation():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    For any generated short password, validation should fail with length violation.
    """
    for _ in range(100):
        password = generate_short_password()
        violations = validate_password_strength(password)
        assert any("12 characters" in v for v in violations), \
            f"Generated short password '{password}' (len={len(password)}) should have length violation"
        assert is_password_strong(password) is False


def test_passwords_missing_uppercase_fail_validation():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    Passwords without uppercase letters should fail validation.
    """
    for _ in range(50):
        password = generate_weak_password_missing_uppercase()
        violations = validate_password_strength(password)
        assert any("uppercase" in v.lower() for v in violations), \
            f"Password '{password}' missing uppercase should have uppercase violation"
        assert is_password_strong(password) is False


def test_passwords_missing_lowercase_fail_validation():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    Passwords without lowercase letters should fail validation.
    """
    for _ in range(50):
        password = generate_weak_password_missing_lowercase()
        violations = validate_password_strength(password)
        assert any("lowercase" in v.lower() for v in violations), \
            f"Password '{password}' missing lowercase should have lowercase violation"
        assert is_password_strong(password) is False


def test_passwords_missing_digit_fail_validation():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    Passwords without digits should fail validation.
    """
    for _ in range(50):
        password = generate_weak_password_missing_digit()
        violations = validate_password_strength(password)
        assert any("digit" in v.lower() for v in violations), \
            f"Password '{password}' missing digit should have digit violation"
        assert is_password_strong(password) is False


def test_passwords_missing_special_fail_validation():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    Passwords without special characters should fail validation.
    """
    for _ in range(50):
        password = generate_weak_password_missing_special()
        violations = validate_password_strength(password)
        assert any("special" in v.lower() for v in violations), \
            f"Password '{password}' missing special char should have special char violation"
        assert is_password_strong(password) is False


def test_empty_password_fails_validation():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    Empty passwords should fail validation.
    """
    violations = validate_password_strength("")
    assert len(violations) > 0, "Empty password should have violations"
    assert is_password_strong("") is False
    
    violations = validate_password_strength(None)
    assert len(violations) > 0, "None password should have violations"
    assert is_password_strong(None) is False


def test_password_strength_property_all_requirements():
    """
    **Feature: system-configuration, Property 9: Password Strength Validation**
    **Validates: Requirements 3.1, 3.2**
    
    Property Test: For any password, it SHALL be accepted if and only if it is
    at least 12 characters long AND contains at least one uppercase letter,
    one lowercase letter, one digit, and one special character.
    """
    for _ in range(100):
        password = generate_strong_password()
        
        # Verify the password meets all requirements
        has_min_length = len(password) >= MIN_PASSWORD_LENGTH
        has_uppercase = any(c.isupper() for c in password)
        has_lowercase = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
        
        expected_strong = (
            has_min_length and has_uppercase and has_lowercase and 
            has_digit and has_special
        )
        
        actual_strong = is_password_strong(password)
        
        assert actual_strong == expected_strong, \
            f"Password '{password}' strength mismatch: expected={expected_strong}, actual={actual_strong}"


# =============================================================================
# Property 10: Password Hash Storage Tests
# =============================================================================

def test_password_hash_not_equal_to_plaintext():
    """
    **Feature: system-configuration, Property 10: Password Hash Storage**
    **Validates: Requirements 3.3**
    
    The stored hash SHALL NOT equal the plaintext password.
    """
    passwords = [
        "SecurePass123!",
        "MyP@ssw0rd!234",
        "Complex#Pass99",
        "Test@12345678",
    ]
    
    for password in passwords:
        hashed = hash_password(password)
        assert hashed != password, f"Hash should not equal plaintext for '{password}'"


def test_password_hash_is_verifiable():
    """
    **Feature: system-configuration, Property 10: Password Hash Storage**
    **Validates: Requirements 3.3**
    
    The stored hash SHALL be verifiable using the verification function.
    """
    passwords = [
        "SecurePass123!",
        "MyP@ssw0rd!234",
        "Complex#Pass99",
        "Test@12345678",
    ]
    
    for password in passwords:
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True, \
            f"Password '{password}' should verify against its hash"


def test_wrong_password_does_not_verify():
    """
    **Feature: system-configuration, Property 10: Password Hash Storage**
    **Validates: Requirements 3.3**
    
    A wrong password SHALL NOT verify against a hash.
    """
    password = "SecurePass123!"
    wrong_password = "WrongPass456!"
    
    hashed = hash_password(password)
    assert verify_password(wrong_password, hashed) is False, \
        "Wrong password should not verify"


def test_password_hash_round_trip_property():
    """
    **Feature: system-configuration, Property 10: Password Hash Storage**
    **Validates: Requirements 3.3**
    
    Property Test: For any password, hashing and then verifying with the same
    password SHALL return True, and the hash SHALL NOT equal the plaintext.
    """
    for _ in range(100):
        password = generate_strong_password()
        
        hashed = hash_password(password)
        
        # Property 1: Hash is not equal to plaintext
        assert hashed != password, \
            f"Hash should not equal plaintext for '{password}'"
        
        # Property 2: Verification with correct password succeeds
        assert verify_password(password, hashed) is True, \
            f"Password '{password}' should verify against its hash"
        
        # Property 3: Verification with wrong password fails
        wrong_password = password + "X"
        assert verify_password(wrong_password, hashed) is False, \
            f"Wrong password should not verify"


def test_different_passwords_produce_different_hashes():
    """
    **Feature: system-configuration, Property 10: Password Hash Storage**
    **Validates: Requirements 3.3**
    
    Different passwords should produce different hashes (with high probability).
    """
    passwords = [generate_strong_password() for _ in range(50)]
    hashes = [hash_password(p) for p in passwords]
    
    # All hashes should be unique
    unique_hashes = set(hashes)
    assert len(unique_hashes) == len(hashes), \
        "Different passwords should produce different hashes"


def test_same_password_produces_different_hashes():
    """
    **Feature: system-configuration, Property 10: Password Hash Storage**
    **Validates: Requirements 3.3**
    
    The same password hashed multiple times should produce different hashes
    (due to salting), but all should verify correctly.
    """
    password = "SecurePass123!"
    
    hashes = [hash_password(password) for _ in range(10)]
    
    # All hashes should be different (due to salting)
    unique_hashes = set(hashes)
    assert len(unique_hashes) == len(hashes), \
        "Same password should produce different hashes due to salting"
    
    # But all should verify correctly
    for hashed in hashes:
        assert verify_password(password, hashed) is True, \
            "All hashes of the same password should verify"

