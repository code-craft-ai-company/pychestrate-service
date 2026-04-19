"""
.. module:: test_global_variable_store_serialization
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for GlobalVariableStore serialization round-trip

.. moduleauthor:: Automation Mojo LLC

Property tests for global variable serialization and deserialization.

**Feature: system-configuration**
**Property 22: Global Variable Serialization Round-Trip**
**Validates: Requirements 7.7, 7.8**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import json

from automojo.pychestrate.core.orm import VariableType
from automojo.pychestrate.core.managers.global_variable_store import (
    serialize_value,
    deserialize_value,
    validate_value,
)


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


def generate_json_value(depth=0, max_depth=3):
    """Generate a random JSON-serializable value."""
    if depth >= max_depth:
        # At max depth, return a primitive
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
        length = random.randint(0, 5)
        return [generate_json_value(depth + 1, max_depth) for _ in range(length)]
    elif value_type == 'dict':
        length = random.randint(0, 5)
        return {
            f"key_{i}": generate_json_value(depth + 1, max_depth)
            for i in range(length)
        }


# =============================================================================
# Property Tests - Property 22: Global Variable Serialization Round-Trip
# =============================================================================

def test_string_serialization_round_trip():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    For any string value, serializing to JSON and deserializing should produce
    an equivalent value.
    """
    for _ in range(100):
        original_value = generate_string_value()
        
        # Serialize
        json_str = serialize_value(original_value, VariableType.STRING)
        
        # Deserialize
        restored_value = deserialize_value(json_str, VariableType.STRING)
        
        assert restored_value == original_value, \
            f"String round-trip failed: original={repr(original_value)}, restored={repr(restored_value)}"


def test_integer_serialization_round_trip():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    For any integer value, serializing to JSON and deserializing should produce
    an equivalent value.
    """
    for _ in range(100):
        original_value = generate_integer_value()
        
        # Serialize
        json_str = serialize_value(original_value, VariableType.INTEGER)
        
        # Deserialize
        restored_value = deserialize_value(json_str, VariableType.INTEGER)
        
        assert restored_value == original_value, \
            f"Integer round-trip failed: original={original_value}, restored={restored_value}"


def test_float_serialization_round_trip():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    For any float value, serializing to JSON and deserializing should produce
    an equivalent value (within floating point precision).
    """
    for _ in range(100):
        original_value = generate_float_value()
        
        # Serialize
        json_str = serialize_value(original_value, VariableType.FLOAT)
        
        # Deserialize
        restored_value = deserialize_value(json_str, VariableType.FLOAT)
        
        # Use approximate comparison for floats due to precision
        assert abs(restored_value - original_value) < 1e-10, \
            f"Float round-trip failed: original={original_value}, restored={restored_value}"


def test_boolean_serialization_round_trip():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    For any boolean value, serializing to JSON and deserializing should produce
    an equivalent value.
    """
    for _ in range(100):
        original_value = generate_boolean_value()
        
        # Serialize
        json_str = serialize_value(original_value, VariableType.BOOLEAN)
        
        # Deserialize
        restored_value = deserialize_value(json_str, VariableType.BOOLEAN)
        
        assert restored_value == original_value, \
            f"Boolean round-trip failed: original={original_value}, restored={restored_value}"


def test_json_serialization_round_trip():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    For any JSON-serializable value, serializing to JSON and deserializing should produce
    an equivalent value.
    """
    for _ in range(100):
        original_value = generate_json_value()
        
        # Serialize
        json_str = serialize_value(original_value, VariableType.JSON)
        
        # Deserialize
        restored_value = deserialize_value(json_str, VariableType.JSON)
        
        # For JSON, we need to handle float comparison specially
        assert _json_equal(original_value, restored_value), \
            f"JSON round-trip failed: original={original_value}, restored={restored_value}"


def test_none_serialization_round_trip():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    None values should serialize and deserialize correctly for all types.
    """
    for var_type in VariableType:
        # Serialize None
        json_str = serialize_value(None, var_type)
        
        # Deserialize
        restored_value = deserialize_value(json_str, var_type)
        
        assert restored_value is None, \
            f"None round-trip failed for type {var_type}: restored={restored_value}"


def test_special_string_values_round_trip():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    Special string values (empty, unicode, special chars) should round-trip correctly.
    """
    special_strings = [
        "",
        " ",
        "\t\n\r",
        "Hello, World!",
        "Unicode: 你好世界 🌍",
        "Quotes: \"single' and double\"",
        "Backslash: \\path\\to\\file",
        "Newlines:\nLine1\nLine2",
        "Tab:\tindented",
        "JSON-like: {\"key\": \"value\"}",
        "a" * 1000,  # Long string
    ]
    
    for original_value in special_strings:
        json_str = serialize_value(original_value, VariableType.STRING)
        restored_value = deserialize_value(json_str, VariableType.STRING)
        
        assert restored_value == original_value, \
            f"Special string round-trip failed: original={repr(original_value)}, restored={repr(restored_value)}"


def test_edge_case_numbers_round_trip():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    Edge case numbers should round-trip correctly.
    """
    # Integer edge cases
    integer_cases = [0, 1, -1, 2**31 - 1, -2**31, 2**63 - 1, -2**63]
    
    for original_value in integer_cases:
        json_str = serialize_value(original_value, VariableType.INTEGER)
        restored_value = deserialize_value(json_str, VariableType.INTEGER)
        
        assert restored_value == original_value, \
            f"Integer edge case round-trip failed: original={original_value}, restored={restored_value}"
    
    # Float edge cases
    float_cases = [0.0, -0.0, 1.0, -1.0, 1e-10, 1e10, 3.14159265358979]
    
    for original_value in float_cases:
        json_str = serialize_value(original_value, VariableType.FLOAT)
        restored_value = deserialize_value(json_str, VariableType.FLOAT)
        
        assert abs(restored_value - original_value) < 1e-15, \
            f"Float edge case round-trip failed: original={original_value}, restored={restored_value}"


def test_complex_json_structures_round_trip():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    Complex nested JSON structures should round-trip correctly.
    """
    complex_structures = [
        [],
        {},
        [1, 2, 3],
        {"key": "value"},
        {"nested": {"deep": {"value": 42}}},
        [{"a": 1}, {"b": 2}, {"c": [1, 2, 3]}],
        {"list": [1, "two", 3.0, True, None]},
        {"mixed": {"int": 1, "str": "hello", "bool": True, "null": None, "list": [1, 2]}},
    ]
    
    for original_value in complex_structures:
        json_str = serialize_value(original_value, VariableType.JSON)
        restored_value = deserialize_value(json_str, VariableType.JSON)
        
        assert restored_value == original_value, \
            f"Complex JSON round-trip failed: original={original_value}, restored={restored_value}"


def test_integer_stored_as_float_converts_correctly():
    """
    **Feature: system-configuration, Property 22: Global Variable Serialization Round-Trip**
    **Validates: Requirements 7.7, 7.8**
    
    When an integer is stored for a FLOAT type, it should be converted to float on deserialization.
    """
    # Store an integer value
    original_value = 42
    
    # Serialize as float type
    json_str = serialize_value(original_value, VariableType.FLOAT)
    
    # Deserialize - should return a float
    restored_value = deserialize_value(json_str, VariableType.FLOAT)
    
    assert isinstance(restored_value, float), \
        f"Expected float type, got {type(restored_value)}"
    assert restored_value == 42.0, \
        f"Value mismatch: expected 42.0, got {restored_value}"


# =============================================================================
# Helper Functions
# =============================================================================

def _json_equal(a, b):
    """
    Compare two JSON values for equality, handling float precision.
    """
    if type(a) != type(b):
        # Special case: int and float comparison
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(float(a) - float(b)) < 1e-10
        return False
    
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_json_equal(a[k], b[k]) for k in a.keys())
    
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_json_equal(x, y) for x, y in zip(a, b))
    
    if isinstance(a, float):
        return abs(a - b) < 1e-10
    
    return a == b
