"""
.. module:: global_variable_store
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the GlobalVariableStore class for managing system-wide configuration variables

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Union

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import VariableType


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class GlobalVariableCreateRequest:
    """Request dataclass for creating a new global variable."""
    name: str
    value: Any
    var_type: VariableType
    description: str = ""
    default_value: Any = None


@dataclass
class GlobalVariableUpdateRequest:
    """Request dataclass for updating an existing global variable."""
    value: Any
    description: Optional[str] = None


@dataclass
class GlobalVariableResponse:
    """Response dataclass for global variable data."""
    id: int
    name: str
    value: Any
    var_type: VariableType
    description: str
    default_value: Any
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str]


@dataclass
class GlobalVariableListResponse:
    """Response dataclass for paginated global variable list."""
    variables: List[GlobalVariableResponse]
    total: int
    offset: int
    limit: int


@dataclass
class VariableChangeLog:
    """Dataclass for variable change history entry."""
    id: int
    variable_name: str
    old_value: Any
    new_value: Any
    changed_by: Optional[str]
    changed_at: datetime


# =============================================================================
# Exceptions
# =============================================================================

class VariableValidationError(Exception):
    """Exception raised when variable validation fails."""
    
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(self.message)


class VariableNotFoundError(Exception):
    """Exception raised when a variable is not found."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class DuplicateVariableError(Exception):
    """Exception raised when attempting to create a variable with duplicate name."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class TypeValidationError(Exception):
    """Exception raised when value type validation fails."""
    
    def __init__(self, message: str, expected_type: str = None, actual_type: str = None):
        self.message = message
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(self.message)


# =============================================================================
# Type Validation and Serialization Functions
# =============================================================================

def validate_value(value: Any, var_type: VariableType) -> bool:
    """
    Validate that a value matches the expected variable type.
    
    :param value: The value to validate
    :param var_type: The expected variable type
    :returns: True if valid, False otherwise
    
    Validates: Requirements 7.5
    """
    if value is None:
        return True  # None is valid for all types
    
    if var_type == VariableType.STRING:
        return isinstance(value, str)
    
    elif var_type == VariableType.INTEGER:
        # Accept int but not bool (bool is subclass of int in Python)
        return isinstance(value, int) and not isinstance(value, bool)
    
    elif var_type == VariableType.FLOAT:
        # Accept int or float but not bool
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    
    elif var_type == VariableType.BOOLEAN:
        return isinstance(value, bool)
    
    elif var_type == VariableType.JSON:
        # JSON type accepts any JSON-serializable value
        try:
            json.dumps(value)
            return True
        except (TypeError, ValueError):
            return False
    
    return False


def serialize_value(value: Any, var_type: VariableType) -> str:
    """
    Serialize a value to JSON string for storage.
    
    :param value: The value to serialize
    :param var_type: The variable type
    :returns: JSON-encoded string
    
    Validates: Requirements 7.7
    """
    return json.dumps(value)


def deserialize_value(json_str: str, var_type: VariableType) -> Any:
    """
    Deserialize a JSON string to a typed value.
    
    :param json_str: The JSON-encoded string
    :param var_type: The expected variable type
    :returns: The deserialized value
    
    Validates: Requirements 7.8
    """
    if json_str is None:
        return None
    
    value = json.loads(json_str)
    
    # For float type, ensure we return a float even if stored as int
    if var_type == VariableType.FLOAT and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    
    return value


# =============================================================================
# GlobalVariableStore Class
# =============================================================================

class GlobalVariableStore:
    """
    Manager class for global variable CRUD operations and type handling.
    
    This class handles all global variable operations including:
    - Variable creation with type validation
    - Variable retrieval by name
    - Variable updates with type validation
    - Variable deletion
    - Variable listing with pagination
    - Change history tracking
    
    Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None):
        """
        Initialize the GlobalVariableStore with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
    
    # =========================================================================
    # Type Validation and Serialization Methods
    # =========================================================================
    
    def validate_value(self, value: Any, var_type: VariableType) -> bool:
        """
        Validate that a value matches the expected variable type.
        
        :param value: The value to validate
        :param var_type: The expected variable type
        :returns: True if valid, False otherwise
        
        Validates: Requirements 7.5
        """
        return validate_value(value, var_type)
    
    def serialize_value(self, value: Any, var_type: VariableType) -> str:
        """
        Serialize a value to JSON string for storage.
        
        :param value: The value to serialize
        :param var_type: The variable type
        :returns: JSON-encoded string
        
        Validates: Requirements 7.7
        """
        return serialize_value(value, var_type)
    
    def deserialize_value(self, json_str: str, var_type: VariableType) -> Any:
        """
        Deserialize a JSON string to a typed value.
        
        :param json_str: The JSON-encoded string
        :param var_type: The expected variable type
        :returns: The deserialized value
        
        Validates: Requirements 7.8
        """
        return deserialize_value(json_str, var_type)
    
    def parse_value_from_string(self, value_str: str, var_type: VariableType) -> Any:
        """
        Parse a string value into the appropriate type.
        
        Used by web interface to convert form input to typed values.
        
        :param value_str: The string value from form input
        :param var_type: The expected variable type
        :returns: The parsed value
        :raises ValueError: If the value cannot be parsed
        """
        if var_type == VariableType.STRING:
            return value_str
        
        elif var_type == VariableType.INTEGER:
            try:
                return int(value_str)
            except ValueError:
                raise ValueError(f"'{value_str}' is not a valid integer")
        
        elif var_type == VariableType.FLOAT:
            try:
                return float(value_str)
            except ValueError:
                raise ValueError(f"'{value_str}' is not a valid float")
        
        elif var_type == VariableType.BOOLEAN:
            lower_val = value_str.lower().strip()
            if lower_val in ('true', '1', 'yes', 'on'):
                return True
            elif lower_val in ('false', '0', 'no', 'off'):
                return False
            else:
                raise ValueError(f"'{value_str}' is not a valid boolean (use 'true' or 'false')")
        
        elif var_type == VariableType.JSON:
            try:
                return json.loads(value_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {str(e)}")
        
        return value_str
    
    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    def create_variable(
        self,
        request: GlobalVariableCreateRequest,
        user_id: str = None
    ) -> GlobalVariableResponse:
        """
        Create a new global variable.
        
        :param request: The variable creation request
        :param user_id: The ID of the user creating the variable
        :returns: GlobalVariableResponse with the created variable data
        :raises VariableValidationError: If validation fails
        :raises DuplicateVariableError: If variable name already exists
        :raises TypeValidationError: If value doesn't match type
        
        Validates: Requirements 7.1
        """
        from ccai.pychestrate.core.orm import GlobalVariable, GlobalVariableHistory
        
        # Validate name
        if not request.name or len(request.name.strip()) == 0:
            raise VariableValidationError("Variable name is required", field="name")
        
        if len(request.name) > 128:
            raise VariableValidationError(
                "Variable name must be 128 characters or less",
                field="name"
            )
        
        # Validate value type
        if not self.validate_value(request.value, request.var_type):
            raise TypeValidationError(
                f"Value does not match type '{request.var_type.value}'",
                expected_type=request.var_type.value,
                actual_type=type(request.value).__name__
            )
        
        # Validate default value type if provided
        if request.default_value is not None:
            if not self.validate_value(request.default_value, request.var_type):
                raise TypeValidationError(
                    f"Default value does not match type '{request.var_type.value}'",
                    expected_type=request.var_type.value,
                    actual_type=type(request.default_value).__name__
                )
        
        # Check for duplicate name
        existing = self._db_session.query(GlobalVariable).filter(
            GlobalVariable.name == request.name
        ).first()
        
        if existing:
            raise DuplicateVariableError(f"Variable '{request.name}' already exists")
        
        # Create the variable
        now = utc_now()
        
        variable = GlobalVariable(
            name=request.name,
            value_json=self.serialize_value(request.value, request.var_type),
            var_type=request.var_type.value,
            description=request.description or "",
            default_value_json=self.serialize_value(request.default_value, request.var_type) if request.default_value is not None else None,
            created_at=now,
            updated_at=now,
            updated_by_id=user_id
        )
        
        self._db_session.add(variable)
        
        # Log the creation in history
        history_entry = GlobalVariableHistory(
            variable_id=None,  # Will be set after flush
            variable_name=request.name,
            old_value_json=None,
            new_value_json=self.serialize_value(request.value, request.var_type),
            changed_by_id=user_id,
            changed_at=now
        )
        
        self._db_session.flush()  # Get the variable ID
        history_entry.variable_id = variable.id
        self._db_session.add(history_entry)
        
        self._db_session.commit()
        
        # Log the variable creation event
        if self._audit_logger and user_id:
            from ccai.pychestrate.core.orm import User
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            self._audit_logger.log_variable_created(
                user_id=str(user_id),
                username=username,
                variable_name=request.name,
                variable_value=request.value
            )
        
        return self._variable_to_response(variable)
    
    def get_variable(self, name: str) -> Optional[GlobalVariableResponse]:
        """
        Get a variable by name.
        
        :param name: The variable name
        :returns: GlobalVariableResponse if found, None otherwise
        """
        from ccai.pychestrate.core.orm import GlobalVariable
        
        variable = self._db_session.query(GlobalVariable).filter(
            GlobalVariable.name == name
        ).first()
        
        if not variable:
            return None
        
        return self._variable_to_response(variable)
    
    def get_value(self, name: str, default: Any = None) -> Any:
        """
        Get variable value, returning default if not set.
        
        :param name: The variable name
        :param default: Default value to return if variable not found
        :returns: The variable value or default
        
        Validates: Requirements 7.4
        """
        from ccai.pychestrate.core.orm import GlobalVariable
        
        variable = self._db_session.query(GlobalVariable).filter(
            GlobalVariable.name == name
        ).first()
        
        if not variable:
            return default
        
        var_type = VariableType(variable.var_type)
        return self.deserialize_value(variable.value_json, var_type)
    
    def update_variable(
        self,
        name: str,
        request: GlobalVariableUpdateRequest,
        user_id: str = None
    ) -> GlobalVariableResponse:
        """
        Update a variable's value.
        
        :param name: The variable name
        :param request: The update request
        :param user_id: The ID of the user making the update
        :returns: GlobalVariableResponse with the updated variable data
        :raises VariableNotFoundError: If variable is not found
        :raises TypeValidationError: If value doesn't match type
        
        Validates: Requirements 7.2
        """
        from ccai.pychestrate.core.orm import GlobalVariable, GlobalVariableHistory
        
        variable = self._db_session.query(GlobalVariable).filter(
            GlobalVariable.name == name
        ).first()
        
        if not variable:
            raise VariableNotFoundError(f"Variable '{name}' not found")
        
        var_type = VariableType(variable.var_type)
        
        # Validate value type
        if not self.validate_value(request.value, var_type):
            raise TypeValidationError(
                f"Value does not match type '{var_type.value}'",
                expected_type=var_type.value,
                actual_type=type(request.value).__name__
            )
        
        now = utc_now()
        old_value_json = variable.value_json
        new_value_json = self.serialize_value(request.value, var_type)
        
        # Update the variable
        variable.value_json = new_value_json
        variable.updated_at = now
        variable.updated_by_id = user_id
        
        if request.description is not None:
            variable.description = request.description
        
        # Log the change in history
        history_entry = GlobalVariableHistory(
            variable_id=variable.id,
            variable_name=name,
            old_value_json=old_value_json,
            new_value_json=new_value_json,
            changed_by_id=user_id,
            changed_at=now
        )
        
        self._db_session.add(history_entry)
        self._db_session.commit()
        
        # Log the variable update event
        if self._audit_logger and user_id:
            from ccai.pychestrate.core.orm import User
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            old_value = self.deserialize_value(old_value_json, var_type)
            self._audit_logger.log_variable_updated(
                user_id=str(user_id),
                username=username,
                variable_name=name,
                old_value=old_value,
                new_value=request.value
            )
        
        return self._variable_to_response(variable)
    
    def delete_variable(self, name: str, user_id: str = None) -> None:
        """
        Delete a variable.
        
        :param name: The variable name
        :param user_id: The ID of the user deleting the variable
        :raises VariableNotFoundError: If variable is not found
        
        Validates: Requirements 7.3
        """
        from ccai.pychestrate.core.orm import GlobalVariable, GlobalVariableHistory
        
        variable = self._db_session.query(GlobalVariable).filter(
            GlobalVariable.name == name
        ).first()
        
        if not variable:
            raise VariableNotFoundError(f"Variable '{name}' not found")
        
        var_type = VariableType(variable.var_type)
        now = utc_now()
        
        # Log the deletion in history
        history_entry = GlobalVariableHistory(
            variable_id=variable.id,
            variable_name=name,
            old_value_json=variable.value_json,
            new_value_json=None,
            changed_by_id=user_id,
            changed_at=now
        )
        
        self._db_session.add(history_entry)
        
        # Get old value for audit logging before deletion
        old_value = self.deserialize_value(variable.value_json, var_type)
        
        # Delete the variable
        self._db_session.delete(variable)
        self._db_session.commit()
        
        # Log the variable deletion event
        if self._audit_logger and user_id:
            from ccai.pychestrate.core.orm import User
            user = self._db_session.query(User).filter(User.id == user_id).first()
            username = user.login if user else ""
            self._audit_logger.log_variable_deleted(
                user_id=str(user_id),
                username=username,
                variable_name=name,
                old_value=old_value
            )
    
    def list_variables(
        self,
        offset: int = 0,
        limit: int = 50,
        search: str = None
    ) -> GlobalVariableListResponse:
        """
        List variables with pagination.
        
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :param search: Optional search string for variable name or description
        :returns: GlobalVariableListResponse with paginated variable list
        """
        from ccai.pychestrate.core.orm import GlobalVariable
        from sqlalchemy import or_
        
        query = self._db_session.query(GlobalVariable)
        
        # Apply search filter
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    GlobalVariable.name.ilike(search_pattern),
                    GlobalVariable.description.ilike(search_pattern)
                )
            )
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        variables = query.order_by(GlobalVariable.name).offset(offset).limit(limit).all()
        
        return GlobalVariableListResponse(
            variables=[self._variable_to_response(var) for var in variables],
            total=total,
            offset=offset,
            limit=limit
        )
    
    # =========================================================================
    # Change History
    # =========================================================================
    
    def get_change_history(
        self,
        name: str,
        offset: int = 0,
        limit: int = 50
    ) -> List[VariableChangeLog]:
        """
        Get change history for a variable.
        
        :param name: The variable name
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: List of VariableChangeLog entries
        
        Validates: Requirements 7.6
        """
        from ccai.pychestrate.core.orm import GlobalVariableHistory, User
        
        query = self._db_session.query(GlobalVariableHistory).filter(
            GlobalVariableHistory.variable_name == name
        ).order_by(GlobalVariableHistory.changed_at.desc())
        
        history_entries = query.offset(offset).limit(limit).all()
        
        result = []
        for entry in history_entries:
            # Get username if user_id is set
            changed_by = None
            if entry.changed_by_id:
                user = self._db_session.query(User).filter(
                    User.id == entry.changed_by_id
                ).first()
                if user:
                    changed_by = user.login
            
            # Determine var_type from the variable or use JSON as fallback
            var_type = VariableType.JSON
            
            result.append(VariableChangeLog(
                id=entry.id,
                variable_name=entry.variable_name,
                old_value=self.deserialize_value(entry.old_value_json, var_type) if entry.old_value_json else None,
                new_value=self.deserialize_value(entry.new_value_json, var_type) if entry.new_value_json else None,
                changed_by=changed_by,
                changed_at=entry.changed_at
            ))
        
        return result
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _variable_to_response(self, variable) -> GlobalVariableResponse:
        """
        Convert a GlobalVariable ORM object to a GlobalVariableResponse dataclass.
        
        :param variable: The GlobalVariable ORM object
        :returns: GlobalVariableResponse dataclass
        """
        from ccai.pychestrate.core.orm import User
        
        var_type = VariableType(variable.var_type)
        
        # Get username if updated_by_id is set
        updated_by = None
        if variable.updated_by_id:
            user = self._db_session.query(User).filter(
                User.id == variable.updated_by_id
            ).first()
            if user:
                updated_by = user.login
        
        return GlobalVariableResponse(
            id=variable.id,
            name=variable.name,
            value=self.deserialize_value(variable.value_json, var_type),
            var_type=var_type,
            description=variable.description or "",
            default_value=self.deserialize_value(variable.default_value_json, var_type) if variable.default_value_json else None,
            created_at=variable.created_at,
            updated_at=variable.updated_at,
            updated_by=updated_by
        )
