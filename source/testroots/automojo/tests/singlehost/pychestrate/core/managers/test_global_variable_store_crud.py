"""
.. module:: test_global_variable_store_crud
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for GlobalVariableStore CRUD operations

.. moduleauthor:: Automation Mojo LLC

Tests for global variable CRUD operations.

**Feature: system-configuration**
**Validates: Requirements 7.1, 7.2, 7.3, 7.4**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.core.orm import VariableType
from automojo.pychestrate.core.managers.global_variable_store import (
    GlobalVariableStore,
    GlobalVariableCreateRequest,
    GlobalVariableUpdateRequest,
    VariableValidationError,
    VariableNotFoundError,
    DuplicateVariableError,
    TypeValidationError,
)

from automojo.testbase.mocking import Mock


# =============================================================================
# Mock Database Session Factory
# =============================================================================

def create_mock_session():
    """Create a mock database session for testing."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    return mock_session


def create_mock_session_with_no_existing_variable():
    """Create a mock session that returns no existing variable on query."""
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
# Type Validation Tests
# =============================================================================

def test_validate_value_string_accepts_strings():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    String type should accept string values.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert store.validate_value("hello", VariableType.STRING) is True
    assert store.validate_value("", VariableType.STRING) is True
    assert store.validate_value("123", VariableType.STRING) is True


def test_validate_value_string_rejects_non_strings():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    String type should reject non-string values.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert store.validate_value(123, VariableType.STRING) is False
    assert store.validate_value(True, VariableType.STRING) is False
    assert store.validate_value([1, 2, 3], VariableType.STRING) is False


def test_validate_value_integer_accepts_integers():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    Integer type should accept integer values.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert store.validate_value(42, VariableType.INTEGER) is True
    assert store.validate_value(0, VariableType.INTEGER) is True
    assert store.validate_value(-100, VariableType.INTEGER) is True


def test_validate_value_integer_rejects_booleans():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    Integer type should reject boolean values (even though bool is subclass of int).
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert store.validate_value(True, VariableType.INTEGER) is False
    assert store.validate_value(False, VariableType.INTEGER) is False


def test_validate_value_float_accepts_floats_and_ints():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    Float type should accept float and integer values.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert store.validate_value(3.14, VariableType.FLOAT) is True
    assert store.validate_value(42, VariableType.FLOAT) is True
    assert store.validate_value(0.0, VariableType.FLOAT) is True


def test_validate_value_float_rejects_booleans():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    Float type should reject boolean values.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert store.validate_value(True, VariableType.FLOAT) is False
    assert store.validate_value(False, VariableType.FLOAT) is False


def test_validate_value_boolean_accepts_booleans():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    Boolean type should accept boolean values.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert store.validate_value(True, VariableType.BOOLEAN) is True
    assert store.validate_value(False, VariableType.BOOLEAN) is True


def test_validate_value_boolean_rejects_non_booleans():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    Boolean type should reject non-boolean values.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert store.validate_value(1, VariableType.BOOLEAN) is False
    assert store.validate_value(0, VariableType.BOOLEAN) is False
    assert store.validate_value("true", VariableType.BOOLEAN) is False


def test_validate_value_json_accepts_json_serializable():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    JSON type should accept any JSON-serializable value.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    assert store.validate_value({"key": "value"}, VariableType.JSON) is True
    assert store.validate_value([1, 2, 3], VariableType.JSON) is True
    assert store.validate_value("string", VariableType.JSON) is True
    assert store.validate_value(42, VariableType.JSON) is True
    assert store.validate_value(None, VariableType.JSON) is True


def test_validate_value_accepts_none_for_all_types():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.5**
    
    None should be valid for all variable types.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    for var_type in VariableType:
        assert store.validate_value(None, var_type) is True, \
            f"None should be valid for type {var_type}"


# =============================================================================
# Serialization Tests
# =============================================================================

def test_serialize_and_deserialize_string():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.7, 7.8**
    
    String values should serialize and deserialize correctly.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    original = "Hello, World!"
    serialized = store.serialize_value(original, VariableType.STRING)
    deserialized = store.deserialize_value(serialized, VariableType.STRING)
    
    assert deserialized == original


def test_serialize_and_deserialize_integer():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.7, 7.8**
    
    Integer values should serialize and deserialize correctly.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    original = 42
    serialized = store.serialize_value(original, VariableType.INTEGER)
    deserialized = store.deserialize_value(serialized, VariableType.INTEGER)
    
    assert deserialized == original


def test_serialize_and_deserialize_float():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.7, 7.8**
    
    Float values should serialize and deserialize correctly.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    original = 3.14159
    serialized = store.serialize_value(original, VariableType.FLOAT)
    deserialized = store.deserialize_value(serialized, VariableType.FLOAT)
    
    assert abs(deserialized - original) < 1e-10


def test_serialize_and_deserialize_boolean():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.7, 7.8**
    
    Boolean values should serialize and deserialize correctly.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    for original in [True, False]:
        serialized = store.serialize_value(original, VariableType.BOOLEAN)
        deserialized = store.deserialize_value(serialized, VariableType.BOOLEAN)
        
        assert deserialized == original


def test_serialize_and_deserialize_json():
    """
    **Feature: system-configuration**
    **Validates: Requirements 7.7, 7.8**
    
    JSON values should serialize and deserialize correctly.
    """
    mock_session = create_mock_session()
    store = GlobalVariableStore(mock_session)
    
    original = {"key": "value", "nested": {"list": [1, 2, 3]}}
    serialized = store.serialize_value(original, VariableType.JSON)
    deserialized = store.deserialize_value(serialized, VariableType.JSON)
    
    assert deserialized == original


# =============================================================================
# Exception Tests
# =============================================================================

def test_variable_validation_error_has_message_and_field():
    """
    Test that VariableValidationError contains message and field.
    """
    error = VariableValidationError("Test message", field="test_field")
    
    assert error.message == "Test message"
    assert error.field == "test_field"
    assert str(error) == "Test message"


def test_variable_not_found_error_has_message():
    """
    Test that VariableNotFoundError contains message.
    """
    error = VariableNotFoundError("Variable not found")
    
    assert error.message == "Variable not found"
    assert str(error) == "Variable not found"


def test_duplicate_variable_error_has_message():
    """
    Test that DuplicateVariableError contains message.
    """
    error = DuplicateVariableError("Variable already exists")
    
    assert error.message == "Variable already exists"
    assert str(error) == "Variable already exists"


def test_type_validation_error_has_type_info():
    """
    Test that TypeValidationError contains type information.
    """
    error = TypeValidationError(
        "Type mismatch",
        expected_type="integer",
        actual_type="string"
    )
    
    assert error.message == "Type mismatch"
    assert error.expected_type == "integer"
    assert error.actual_type == "string"
