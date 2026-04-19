"""
.. module:: test_global_variable_store_type_validation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for GlobalVariableStore type validation

.. moduleauthor:: Automation Mojo LLC

Property tests for global variable type validation.

**Feature: system-configuration**
**Property 21: Global Variable Type Validation**
**Validates: Requirements 7.2, 7.5**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo.pychestrate.core.orm import VariableType
from automojo.pychestrate.core.managers.global_variable_store import validate_value


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_string_value():
    """Generate a random string value."""
    length = random.randint(0, 100)
    return ''.join(random.choices(string.ascii_letters + string.digits + ' _-!@#$%', k=length))


def generate_integer_value():
    """Generate a random integer value."""
    return random.randint(-1000000, 1000000)


def generate_float_value():
    """Generate a random float value."""
    return random.uniform(-1000000.0, 1000000.0)


def generate_boolean_value():
    """Generate a random boolean value."""
    return random.choice([True, False])


def generate_json_value(depth=0, max_depth=2):
    """Generate a random JSON-serializable value."""
    if depth >= max_depth:
        return random.choice([
            generate_string_value(),
            generate_integer_value(),
            generate_float_value(),
            generate_boolean_value(),
            None
        ])
    
    value_type = random.choice(['string', 'int', 'float', 'bool', 'null', 'list', 'dict'])
    
    if value_type == 'string':
        return generate_string_value()
    elif value_type == 'int':
        return generate_integer_value()
    elif value_type == 'float':
        return generate_float_value()
    elif value_type == 'bool':
        return generate_boolean_value()
    elif value_type == 'null':
        return None
    elif value_type == 'list':
        length = random.randint(0, 3)
        return [generate_json_value(depth + 1, max_depth) for _ in range(length)]
    elif value_type == 'dict':
        length = random.randint(0, 3)
        return {f"key_{i}": generate_json_value(depth + 1, max_depth) for i in range(length)}


def generate_value_for_type(var_type: VariableType):
    """Generate a valid value for the given type."""
    if var_type == VariableType.STRING:
        return generate_string_value()
    elif var_type == VariableType.INTEGER:
        return generate_integer_value()
    elif var_type == VariableType.FLOAT:
        return generate_float_value()
    elif var_type == VariableType.BOOLEAN:
        return generate_boolean_value()
    elif var_type == VariableType.JSON:
        return generate_json_value()


def generate_invalid_value_for_type(var_type: VariableType):
    """Generate an invalid value for the given type."""
    if var_type == VariableType.STRING:
        # Return a non-string value
        return random.choice([42, 3.14, True, [1, 2, 3], {"key": "value"}])
    elif var_type == VariableType.INTEGER:
        # Return a non-integer value (including bool which should be rejected)
        return random.choice(["string", 3.14, True, False, [1, 2, 3], {"key": "value"}])
    elif var_type == VariableType.FLOAT:
        # Return a non-numeric value (including bool which should be rejected)
        return random.choice(["string", True, False, [1, 2, 3], {"key": "value"}])
    elif var_type == VariableType.BOOLEAN:
        # Return a non-boolean value
        return random.choice(["true", "false", 1, 0, "yes", "no"])
    elif var_type == VariableType.JSON:
        # JSON accepts almost anything that's serializable, so return something non-serializable
        # This is tricky since most Python objects are JSON-serializable
        # We'll use a function which is not JSON-serializable
        return lambda x: x  # Functions are not JSON-serializable


# =============================================================================
# Property Tests - Property 21: Global Variable Type Validation
# =============================================================================

def test_string_type_accepts_all_strings():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any string value, STRING type validation should accept it.
    """
    for _ in range(100):
        value = generate_string_value()
        result = validate_value(value, VariableType.STRING)
        
        assert result is True, \
            f"STRING type should accept string value: {repr(value)}"


def test_string_type_rejects_non_strings():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any non-string value, STRING type validation should reject it.
    """
    non_string_values = [
        42, -100, 0,  # integers
        3.14, -2.5, 0.0,  # floats
        True, False,  # booleans
        [1, 2, 3], [],  # lists
        {"key": "value"}, {},  # dicts
    ]
    
    for value in non_string_values:
        result = validate_value(value, VariableType.STRING)
        
        assert result is False, \
            f"STRING type should reject non-string value: {repr(value)}"


def test_integer_type_accepts_all_integers():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any integer value (excluding booleans), INTEGER type validation should accept it.
    """
    for _ in range(100):
        value = generate_integer_value()
        result = validate_value(value, VariableType.INTEGER)
        
        assert result is True, \
            f"INTEGER type should accept integer value: {value}"


def test_integer_type_rejects_booleans():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    INTEGER type should reject boolean values even though bool is subclass of int.
    """
    for value in [True, False]:
        result = validate_value(value, VariableType.INTEGER)
        
        assert result is False, \
            f"INTEGER type should reject boolean value: {value}"


def test_integer_type_rejects_non_integers():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any non-integer value, INTEGER type validation should reject it.
    """
    non_integer_values = [
        "42", "hello",  # strings
        3.14, -2.5, 0.0,  # floats
        [1, 2, 3], [],  # lists
        {"key": "value"}, {},  # dicts
    ]
    
    for value in non_integer_values:
        result = validate_value(value, VariableType.INTEGER)
        
        assert result is False, \
            f"INTEGER type should reject non-integer value: {repr(value)}"


def test_float_type_accepts_floats_and_integers():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any float or integer value, FLOAT type validation should accept it.
    """
    for _ in range(100):
        # Test floats
        float_value = generate_float_value()
        result = validate_value(float_value, VariableType.FLOAT)
        assert result is True, f"FLOAT type should accept float value: {float_value}"
        
        # Test integers (should also be accepted as floats)
        int_value = generate_integer_value()
        result = validate_value(int_value, VariableType.FLOAT)
        assert result is True, f"FLOAT type should accept integer value: {int_value}"


def test_float_type_rejects_booleans():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    FLOAT type should reject boolean values.
    """
    for value in [True, False]:
        result = validate_value(value, VariableType.FLOAT)
        
        assert result is False, \
            f"FLOAT type should reject boolean value: {value}"


def test_float_type_rejects_non_numeric():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any non-numeric value, FLOAT type validation should reject it.
    """
    non_numeric_values = [
        "3.14", "hello",  # strings
        [1, 2, 3], [],  # lists
        {"key": "value"}, {},  # dicts
    ]
    
    for value in non_numeric_values:
        result = validate_value(value, VariableType.FLOAT)
        
        assert result is False, \
            f"FLOAT type should reject non-numeric value: {repr(value)}"


def test_boolean_type_accepts_booleans():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any boolean value, BOOLEAN type validation should accept it.
    """
    for _ in range(100):
        value = generate_boolean_value()
        result = validate_value(value, VariableType.BOOLEAN)
        
        assert result is True, \
            f"BOOLEAN type should accept boolean value: {value}"


def test_boolean_type_rejects_non_booleans():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any non-boolean value, BOOLEAN type validation should reject it.
    """
    non_boolean_values = [
        "true", "false", "True", "False",  # strings
        1, 0, -1,  # integers
        1.0, 0.0,  # floats
        [True], [],  # lists
        {"key": True}, {},  # dicts
    ]
    
    for value in non_boolean_values:
        result = validate_value(value, VariableType.BOOLEAN)
        
        assert result is False, \
            f"BOOLEAN type should reject non-boolean value: {repr(value)}"


def test_json_type_accepts_json_serializable():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any JSON-serializable value, JSON type validation should accept it.
    """
    for _ in range(100):
        value = generate_json_value()
        result = validate_value(value, VariableType.JSON)
        
        assert result is True, \
            f"JSON type should accept JSON-serializable value: {repr(value)}"


def test_json_type_rejects_non_serializable():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For non-JSON-serializable values, JSON type validation should reject them.
    """
    # Functions are not JSON-serializable
    result = validate_value(lambda x: x, VariableType.JSON)
    assert result is False, "JSON type should reject function"
    
    # Sets are not JSON-serializable
    result = validate_value({1, 2, 3}, VariableType.JSON)
    assert result is False, "JSON type should reject set"


def test_all_types_accept_none():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any variable type, None should be accepted as a valid value.
    """
    for var_type in VariableType:
        result = validate_value(None, var_type)
        
        assert result is True, \
            f"Type {var_type} should accept None value"


def test_valid_values_accepted_for_each_type():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    For any type and any valid value of that type, validation should accept it.
    """
    for _ in range(100):
        for var_type in VariableType:
            value = generate_value_for_type(var_type)
            result = validate_value(value, var_type)
            
            assert result is True, \
                f"Type {var_type} should accept valid value: {repr(value)}"


def test_type_validation_is_strict():
    """
    **Feature: system-configuration, Property 21: Global Variable Type Validation**
    **Validates: Requirements 7.2, 7.5**
    
    Type validation should be strict - values should only be accepted for their correct type.
    """
    # String should not be accepted as integer
    assert validate_value("42", VariableType.INTEGER) is False
    
    # Integer should not be accepted as string
    assert validate_value(42, VariableType.STRING) is False
    
    # String "true" should not be accepted as boolean
    assert validate_value("true", VariableType.BOOLEAN) is False
    
    # Integer 1 should not be accepted as boolean
    assert validate_value(1, VariableType.BOOLEAN) is False
    
    # Boolean should not be accepted as integer
    assert validate_value(True, VariableType.INTEGER) is False
    
    # Boolean should not be accepted as float
    assert validate_value(True, VariableType.FLOAT) is False
