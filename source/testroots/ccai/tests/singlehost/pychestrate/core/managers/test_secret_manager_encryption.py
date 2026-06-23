"""
.. module:: test_secret_manager_encryption
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for SecretManager encryption round-trip

.. moduleauthor:: Code Craft AI LLC

Property tests for secret encryption and decryption.

**Feature: system-configuration**
**Property 29: Secret Encryption Round-Trip**
**Validates: Requirements 11.1, 11.2**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import os

from ccai.pychestrate.core.managers.secret_manager import (
    encrypt_value,
    decrypt_value,
    generate_encryption_key,
    AES_KEY_SIZE,
    GCM_NONCE_SIZE,
    EncryptionError,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_random_string(min_length=0, max_length=1000):
    """Generate a random string value."""
    length = random.randint(min_length, max_length)
    # Include various character types
    chars = string.ascii_letters + string.digits + string.punctuation + ' \t\n'
    return ''.join(random.choices(chars, k=length))


def generate_unicode_string():
    """Generate a string with unicode characters."""
    unicode_samples = [
        "Hello, World!",
        "你好世界",
        "مرحبا بالعالم",
        "Привет мир",
        "🌍🌎🌏",
        "日本語テスト",
        "한국어 테스트",
        "Ελληνικά",
        "עברית",
        "ไทย",
    ]
    return random.choice(unicode_samples) + generate_random_string(0, 50)


def generate_special_string():
    """Generate strings with special characters and edge cases."""
    special_cases = [
        "",  # Empty string
        " ",  # Single space
        "\t\n\r",  # Whitespace characters
        "\\",  # Backslash
        "\"'`",  # Quotes
        "\x00\x01\x02",  # Control characters
        "a" * 10000,  # Long string
        "${secret/reference}",  # Secret reference format
        "password123!@#$%^&*()",  # Typical password
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",  # SSH key format
    ]
    return random.choice(special_cases)


# =============================================================================
# Property Tests - Property 29: Secret Encryption Round-Trip
# =============================================================================

def test_encryption_round_trip_random_strings():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    For any secret value, encrypting with AES-256 and then decrypting should
    produce the original plaintext value.
    """
    key = generate_encryption_key()
    
    for _ in range(100):
        original_value = generate_random_string()
        
        # Encrypt
        encrypted = encrypt_value(original_value, key)
        
        # Decrypt
        decrypted = decrypt_value(encrypted, key)
        
        assert decrypted == original_value, \
            f"Round-trip failed: original={repr(original_value)}, decrypted={repr(decrypted)}"


def test_encryption_round_trip_unicode():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Unicode strings should encrypt and decrypt correctly.
    """
    key = generate_encryption_key()
    
    for _ in range(100):
        original_value = generate_unicode_string()
        
        # Encrypt
        encrypted = encrypt_value(original_value, key)
        
        # Decrypt
        decrypted = decrypt_value(encrypted, key)
        
        assert decrypted == original_value, \
            f"Unicode round-trip failed: original={repr(original_value)}, decrypted={repr(decrypted)}"


def test_encryption_round_trip_special_strings():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Special strings (empty, whitespace, control chars) should round-trip correctly.
    """
    key = generate_encryption_key()
    
    for _ in range(100):
        original_value = generate_special_string()
        
        # Encrypt
        encrypted = encrypt_value(original_value, key)
        
        # Decrypt
        decrypted = decrypt_value(encrypted, key)
        
        assert decrypted == original_value, \
            f"Special string round-trip failed: original={repr(original_value)}, decrypted={repr(decrypted)}"


def test_encrypted_value_differs_from_plaintext():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    The encrypted value should NOT equal the plaintext (except for edge cases).
    """
    key = generate_encryption_key()
    
    for _ in range(100):
        original_value = generate_random_string(min_length=10, max_length=100)
        
        # Encrypt
        encrypted = encrypt_value(original_value, key)
        
        # Encrypted bytes should not equal plaintext bytes
        plaintext_bytes = original_value.encode('utf-8')
        assert encrypted != plaintext_bytes, \
            f"Encrypted value equals plaintext for: {repr(original_value)}"


def test_different_nonces_produce_different_ciphertexts():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Encrypting the same value twice should produce different ciphertexts
    (due to random nonce generation).
    """
    key = generate_encryption_key()
    
    for _ in range(100):
        original_value = generate_random_string(min_length=10, max_length=100)
        
        # Encrypt twice
        encrypted1 = encrypt_value(original_value, key)
        encrypted2 = encrypt_value(original_value, key)
        
        # Ciphertexts should be different (different nonces)
        assert encrypted1 != encrypted2, \
            f"Same ciphertext produced for: {repr(original_value)}"
        
        # But both should decrypt to the same value
        decrypted1 = decrypt_value(encrypted1, key)
        decrypted2 = decrypt_value(encrypted2, key)
        
        assert decrypted1 == original_value
        assert decrypted2 == original_value


def test_different_keys_produce_different_ciphertexts():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Encrypting with different keys should produce different ciphertexts.
    """
    key1 = generate_encryption_key()
    key2 = generate_encryption_key()
    
    for _ in range(100):
        original_value = generate_random_string(min_length=10, max_length=100)
        
        # Encrypt with different keys
        encrypted1 = encrypt_value(original_value, key1)
        encrypted2 = encrypt_value(original_value, key2)
        
        # Ciphertexts should be different
        assert encrypted1 != encrypted2, \
            f"Same ciphertext with different keys for: {repr(original_value)}"


def test_wrong_key_fails_decryption():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Decrypting with the wrong key should fail.
    """
    key1 = generate_encryption_key()
    key2 = generate_encryption_key()
    
    for _ in range(100):
        original_value = generate_random_string(min_length=10, max_length=100)
        
        # Encrypt with key1
        encrypted = encrypt_value(original_value, key1)
        
        # Decrypt with key2 should fail
        try:
            decrypt_value(encrypted, key2)
            assert False, "Decryption with wrong key should have failed"
        except EncryptionError:
            pass  # Expected


def test_invalid_key_size_raises_error():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Using an invalid key size should raise an error.
    """
    invalid_key_sizes = [0, 1, 15, 16, 24, 31, 33, 64, 128]
    
    for size in invalid_key_sizes:
        invalid_key = os.urandom(size)
        
        try:
            encrypt_value("test", invalid_key)
            assert False, f"Should have raised error for key size {size}"
        except EncryptionError as e:
            assert "Invalid key size" in str(e)


def test_invalid_encrypted_data_raises_error():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Decrypting invalid data should raise an error.
    """
    key = generate_encryption_key()
    
    # Too short data
    try:
        decrypt_value(b"short", key)
        assert False, "Should have raised error for short data"
    except EncryptionError as e:
        assert "too short" in str(e).lower() or "Invalid" in str(e)
    
    # Corrupted data
    original_value = "test secret"
    encrypted = encrypt_value(original_value, key)
    
    # Corrupt the ciphertext
    corrupted = encrypted[:-1] + bytes([encrypted[-1] ^ 0xFF])
    
    try:
        decrypt_value(corrupted, key)
        assert False, "Should have raised error for corrupted data"
    except EncryptionError:
        pass  # Expected


def test_encryption_format():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Encrypted data should have the expected format (nonce + ciphertext + tag).
    """
    key = generate_encryption_key()
    
    for _ in range(100):
        original_value = generate_random_string(min_length=1, max_length=100)
        
        # Encrypt
        encrypted = encrypt_value(original_value, key)
        
        # Check minimum length (nonce + at least 1 byte + tag)
        min_length = GCM_NONCE_SIZE + 1 + 16  # nonce + min ciphertext + tag
        assert len(encrypted) >= min_length, \
            f"Encrypted data too short: {len(encrypted)} < {min_length}"
        
        # Nonce should be at the beginning
        nonce = encrypted[:GCM_NONCE_SIZE]
        assert len(nonce) == GCM_NONCE_SIZE


def test_empty_string_encryption():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Empty strings should encrypt and decrypt correctly.
    """
    key = generate_encryption_key()
    
    original_value = ""
    
    # Encrypt
    encrypted = encrypt_value(original_value, key)
    
    # Decrypt
    decrypted = decrypt_value(encrypted, key)
    
    assert decrypted == original_value, \
        f"Empty string round-trip failed: decrypted={repr(decrypted)}"


def test_long_string_encryption():
    """
    **Feature: system-configuration, Property 29: Secret Encryption Round-Trip**
    **Validates: Requirements 11.1, 11.2**
    
    Long strings should encrypt and decrypt correctly.
    """
    key = generate_encryption_key()
    
    # Test various long string lengths
    lengths = [1000, 10000, 100000]
    
    for length in lengths:
        original_value = 'a' * length
        
        # Encrypt
        encrypted = encrypt_value(original_value, key)
        
        # Decrypt
        decrypted = decrypt_value(encrypted, key)
        
        assert decrypted == original_value, \
            f"Long string ({length} chars) round-trip failed"
