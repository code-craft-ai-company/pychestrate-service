"""
.. module:: test_global_variable_store_default
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for GlobalVariableStore default fallback

.. moduleauthor:: Code Craft AI LLC

Property tests for global variable default value fallback.

**Feature: system-configuration**
**Property 23: Global Variable Default Fallback**
**Validates: Requirements 7.4**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string
import uuid

from ccai.pychestrate.core.managers.global_variable_store import GlobalVariableStore

from ccai.testbase.mocking import Mock


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_random_string():
    """Generate a random string value."""
    length = random.randint(1, 50)
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_random_int():
    """Generate a random integer value."""
    return random.randint(-10000, 10000)


def generate_random_float():
    """Generate a random float value."""
    return random.uniform(-10000.0, 10000.0)


def generate_random_bool():
    """Generate a random boolean value."""
    return random.choice([True, False])


def generate_random_default():
    """Generate a random default value of any type."""
    value_type = random.choice(['string', 'int', 'float', 'bool', 'list', 'dict', 'none'])
    
    if value_type == 'string':
        return generate_random_string()
    elif value_type == 'int':
        return generate_random_int()
    elif value_type == 'float':
        return generate_random_float()
    elif value_type == 'bool':
        return generate_random_bool()
    elif value_type == 'list':
        return [generate_random_int() for _ in range(random.randint(0, 5))]
    elif value_type == 'dict':
        return {f"key_{i}": generate_random_int() for i in range(random.randint(0, 3))}
    else:
        return None


def generate_nonexistent_variable_name():
    """Generate a variable name that doesn't exist."""
    return f"nonexistent_var_{uuid.uuid4().hex[:8]}"


# =============================================================================
# Mock Database Session Factory
# =============================================================================

def create_mock_session_returning_none():
    """Create a mock session that returns None for variable queries."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=None)
    
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session


# =============================================================================
# Property Tests - Property 23: Global Variable Default Fallback
# =============================================================================

def test_get_value_returns_default_for_nonexistent_variable():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    For any non-existent variable name and any default value,
    get_value should return the provided default.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    for _ in range(100):
        var_name = generate_nonexistent_variable_name()
        default_value = generate_random_default()
        
        result = store.get_value(var_name, default=default_value)
        
        assert result == default_value, \
            f"get_value should return default {repr(default_value)} for non-existent variable '{var_name}', got {repr(result)}"


def test_get_value_returns_none_when_no_default_provided():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    For any non-existent variable name with no default provided,
    get_value should return None.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    for _ in range(100):
        var_name = generate_nonexistent_variable_name()
        
        result = store.get_value(var_name)
        
        assert result is None, \
            f"get_value should return None for non-existent variable '{var_name}' with no default, got {repr(result)}"


def test_get_value_returns_string_default():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    For any non-existent variable with a string default, get_value should return the string.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    for _ in range(100):
        var_name = generate_nonexistent_variable_name()
        default_value = generate_random_string()
        
        result = store.get_value(var_name, default=default_value)
        
        assert result == default_value, \
            f"get_value should return string default '{default_value}', got '{result}'"


def test_get_value_returns_integer_default():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    For any non-existent variable with an integer default, get_value should return the integer.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    for _ in range(100):
        var_name = generate_nonexistent_variable_name()
        default_value = generate_random_int()
        
        result = store.get_value(var_name, default=default_value)
        
        assert result == default_value, \
            f"get_value should return integer default {default_value}, got {result}"


def test_get_value_returns_float_default():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    For any non-existent variable with a float default, get_value should return the float.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    for _ in range(100):
        var_name = generate_nonexistent_variable_name()
        default_value = generate_random_float()
        
        result = store.get_value(var_name, default=default_value)
        
        assert abs(result - default_value) < 1e-10, \
            f"get_value should return float default {default_value}, got {result}"


def test_get_value_returns_boolean_default():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    For any non-existent variable with a boolean default, get_value should return the boolean.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    for _ in range(100):
        var_name = generate_nonexistent_variable_name()
        default_value = generate_random_bool()
        
        result = store.get_value(var_name, default=default_value)
        
        assert result == default_value, \
            f"get_value should return boolean default {default_value}, got {result}"


def test_get_value_returns_list_default():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    For any non-existent variable with a list default, get_value should return the list.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    for _ in range(100):
        var_name = generate_nonexistent_variable_name()
        default_value = [generate_random_int() for _ in range(random.randint(0, 5))]
        
        result = store.get_value(var_name, default=default_value)
        
        assert result == default_value, \
            f"get_value should return list default {default_value}, got {result}"


def test_get_value_returns_dict_default():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    For any non-existent variable with a dict default, get_value should return the dict.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    for _ in range(100):
        var_name = generate_nonexistent_variable_name()
        default_value = {f"key_{i}": generate_random_int() for i in range(random.randint(0, 3))}
        
        result = store.get_value(var_name, default=default_value)
        
        assert result == default_value, \
            f"get_value should return dict default {default_value}, got {result}"


def test_get_value_returns_none_default_explicitly():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    For any non-existent variable with explicit None default, get_value should return None.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    for _ in range(100):
        var_name = generate_nonexistent_variable_name()
        
        result = store.get_value(var_name, default=None)
        
        assert result is None, \
            f"get_value should return None for explicit None default, got {repr(result)}"


def test_get_value_default_preserves_type():
    """
    **Feature: system-configuration, Property 23: Global Variable Default Fallback**
    **Validates: Requirements 7.4**
    
    The default value returned should preserve its original type.
    """
    mock_session = create_mock_session_returning_none()
    store = GlobalVariableStore(mock_session)
    
    test_cases = [
        ("string", "hello"),
        ("int", 42),
        ("float", 3.14),
        ("bool_true", True),
        ("bool_false", False),
        ("list", [1, 2, 3]),
        ("dict", {"key": "value"}),
        ("empty_string", ""),
        ("zero", 0),
        ("empty_list", []),
        ("empty_dict", {}),
    ]
    
    for name, default_value in test_cases:
        var_name = f"nonexistent_{name}_{uuid.uuid4().hex[:8]}"
        result = store.get_value(var_name, default=default_value)
        
        assert type(result) == type(default_value), \
            f"Type should be preserved: expected {type(default_value)}, got {type(result)}"
        assert result == default_value, \
            f"Value should match: expected {repr(default_value)}, got {repr(result)}"
