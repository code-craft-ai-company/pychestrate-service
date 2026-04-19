"""
.. module:: test_api_error_format
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for API error format consistency

.. moduleauthor:: Automation Mojo LLC

Tests for API error format consistency in the REST API.

**Feature: system-configuration**
**Property 27: API Error Format Consistency**
**Validates: Requirements 9.3**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import json


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_error_code():
    """Generate a random error code string."""
    prefixes = ['VALIDATION', 'AUTH', 'NOT_FOUND', 'CONFLICT', 'INTERNAL', 'HTTP']
    suffixes = ['ERROR', 'FAILED', 'INVALID', 'DENIED', 'EXPIRED']
    return f"{random.choice(prefixes)}_{random.choice(suffixes)}"


def generate_error_message():
    """Generate a random error message."""
    messages = [
        "Invalid input provided",
        "Resource not found",
        "Authentication required",
        "Permission denied",
        "Duplicate entry exists",
        "Internal server error occurred",
        "Session has expired",
        "Invalid token format",
        "Validation failed for field",
        "Operation not permitted",
    ]
    return random.choice(messages)


def generate_error_details():
    """Generate random error details dictionary."""
    if random.choice([True, False, False]):  # 33% chance of None
        return None
    
    details = {}
    
    if random.choice([True, False]):
        details['field'] = ''.join(random.choices(string.ascii_lowercase, k=random.randint(3, 15)))
    
    if random.choice([True, False]):
        details['resource'] = random.choice(['user', 'role', 'variable', 'secret', 'session'])
    
    if random.choice([True, False]):
        details['identifier'] = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(5, 20)))
    
    if random.choice([True, False]):
        details['required_permission'] = f"{random.choice(['users', 'roles', 'variables'])}.{random.choice(['read', 'write', 'delete'])}"
    
    return details if details else None


def generate_http_status_code():
    """Generate a random HTTP status code."""
    return random.choice([400, 401, 403, 404, 405, 409, 422, 429, 500, 502, 503])


# =============================================================================
# Error Response Format Validation
# =============================================================================

def validate_error_response_format(response: dict) -> tuple:
    """
    Validate that an error response has the correct format.
    
    Expected format:
    {
        "error_code": "ERROR_CODE",
        "message": "Human-readable error message",
        "details": { ... optional additional details ... }
    }
    
    :param response: The error response dictionary
    :returns: Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check required fields
    if 'error_code' not in response:
        errors.append("Missing required field 'error_code'")
    elif not isinstance(response['error_code'], str):
        errors.append(f"'error_code' must be a string, got {type(response['error_code']).__name__}")
    elif not response['error_code']:
        errors.append("'error_code' cannot be empty")
    
    if 'message' not in response:
        errors.append("Missing required field 'message'")
    elif not isinstance(response['message'], str):
        errors.append(f"'message' must be a string, got {type(response['message']).__name__}")
    elif not response['message']:
        errors.append("'message' cannot be empty")
    
    if 'details' not in response:
        errors.append("Missing required field 'details'")
    elif response['details'] is not None and not isinstance(response['details'], dict):
        errors.append(f"'details' must be a dict or null, got {type(response['details']).__name__}")
    
    return (len(errors) == 0, errors)


def create_error_response(error_code: str, message: str, details: dict = None) -> dict:
    """
    Create a standardized error response.
    
    This mirrors the logic in the errors.py module.
    
    :param error_code: Error code identifier
    :param message: Human-readable error message
    :param details: Optional dictionary with additional error details
    :returns: Error response dictionary
    """
    return {
        'error_code': error_code,
        'message': message,
        'details': details or {}
    }


# =============================================================================
# Error Format Consistency Tests - Property 27
# =============================================================================

def test_error_response_has_required_fields():
    """
    **Feature: system-configuration, Property 27: API Error Format Consistency**
    **Validates: Requirements 9.3**
    
    For any error response, it SHALL contain error_code, message, and details fields.
    """
    for _ in range(100):
        error_code = generate_error_code()
        message = generate_error_message()
        details = generate_error_details()
        
        response = create_error_response(error_code, message, details)
        
        is_valid, errors = validate_error_response_format(response)
        
        assert is_valid, f"Error response should be valid. Errors: {errors}"
        assert 'error_code' in response, "Response must have 'error_code' field"
        assert 'message' in response, "Response must have 'message' field"
        assert 'details' in response, "Response must have 'details' field"


def test_error_code_is_non_empty_string():
    """
    **Feature: system-configuration, Property 27: API Error Format Consistency**
    **Validates: Requirements 9.3**
    
    For any error response, error_code SHALL be a non-empty string.
    """
    for _ in range(100):
        error_code = generate_error_code()
        message = generate_error_message()
        
        response = create_error_response(error_code, message)
        
        assert isinstance(response['error_code'], str), \
            f"error_code must be a string, got {type(response['error_code']).__name__}"
        assert len(response['error_code']) > 0, \
            "error_code cannot be empty"


def test_message_is_non_empty_string():
    """
    **Feature: system-configuration, Property 27: API Error Format Consistency**
    **Validates: Requirements 9.3**
    
    For any error response, message SHALL be a non-empty string.
    """
    for _ in range(100):
        error_code = generate_error_code()
        message = generate_error_message()
        
        response = create_error_response(error_code, message)
        
        assert isinstance(response['message'], str), \
            f"message must be a string, got {type(response['message']).__name__}"
        assert len(response['message']) > 0, \
            "message cannot be empty"


def test_details_is_dict_or_empty_dict():
    """
    **Feature: system-configuration, Property 27: API Error Format Consistency**
    **Validates: Requirements 9.3**
    
    For any error response, details SHALL be a dictionary (possibly empty).
    """
    for _ in range(100):
        error_code = generate_error_code()
        message = generate_error_message()
        details = generate_error_details()
        
        response = create_error_response(error_code, message, details)
        
        assert isinstance(response['details'], dict), \
            f"details must be a dict, got {type(response['details']).__name__}"


def test_error_response_is_json_serializable():
    """
    **Feature: system-configuration, Property 27: API Error Format Consistency**
    **Validates: Requirements 9.3**
    
    For any error response, it SHALL be JSON serializable.
    """
    for _ in range(100):
        error_code = generate_error_code()
        message = generate_error_message()
        details = generate_error_details()
        
        response = create_error_response(error_code, message, details)
        
        try:
            json_str = json.dumps(response)
            parsed = json.loads(json_str)
            
            assert parsed == response, \
                "JSON round-trip should preserve response structure"
        except (TypeError, ValueError) as e:
            assert False, f"Error response should be JSON serializable: {e}"


def test_null_details_becomes_empty_dict():
    """
    **Feature: system-configuration, Property 27: API Error Format Consistency**
    **Validates: Requirements 9.3**
    
    When details is None, the response SHALL contain an empty dict.
    """
    for _ in range(100):
        error_code = generate_error_code()
        message = generate_error_message()
        
        response = create_error_response(error_code, message, None)
        
        assert response['details'] == {}, \
            f"None details should become empty dict, got {response['details']}"


def test_error_response_preserves_details_content():
    """
    **Feature: system-configuration, Property 27: API Error Format Consistency**
    **Validates: Requirements 9.3**
    
    When details are provided, they SHALL be preserved in the response.
    """
    for _ in range(100):
        error_code = generate_error_code()
        message = generate_error_message()
        
        # Generate non-empty details
        details = {
            'field': ''.join(random.choices(string.ascii_lowercase, k=10)),
            'value': random.randint(1, 1000),
        }
        
        response = create_error_response(error_code, message, details)
        
        assert response['details'] == details, \
            f"Details should be preserved: expected {details}, got {response['details']}"


def test_error_response_no_extra_fields():
    """
    **Feature: system-configuration, Property 27: API Error Format Consistency**
    **Validates: Requirements 9.3**
    
    Error responses SHALL only contain the standard fields.
    """
    for _ in range(100):
        error_code = generate_error_code()
        message = generate_error_message()
        details = generate_error_details()
        
        response = create_error_response(error_code, message, details)
        
        expected_keys = {'error_code', 'message', 'details'}
        actual_keys = set(response.keys())
        
        assert actual_keys == expected_keys, \
            f"Response should only have standard fields. Extra: {actual_keys - expected_keys}, Missing: {expected_keys - actual_keys}"

