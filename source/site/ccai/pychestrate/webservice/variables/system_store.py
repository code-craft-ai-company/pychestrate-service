"""
.. module:: variables.system_store
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Admin Variables pages' store, over the modern variables service (audit ADM-08, ``specs/model-convergence.md`` section 8).

.. moduleauthor:: Code Craft AI LLC

The Admin Variables pages used to write the legacy ``global_variables`` table, which nothing in the runtime read: a variable created there did nothing, and one set
through ``/api/v1/variables`` never appeared there. :class:`SystemVariableStore` keeps the pages' variables where the runtime looks: the SYSTEM-scope bindings of
``variables_variable_bindings``, with their history in ``variables_binding_history``. The legacy store and its tables are gone (``specs/model-convergence.md`` section 10); this module holds
what the pages kept of it: the value checks, the parsing of typed text, the request and response types and the errors.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import or_

from ccai.pychestrate.core.orm import VariableType
from ccai.pychestrate.webservice.variables import service as variable_service
from ccai.pychestrate.webservice.variables.exceptions import InvalidVariableValueError
from ccai.pychestrate.webservice.variables.models import (
    VariableBinding,
    VariableBindingHistory,
    VariableScope,
    VariableValueType,
)


#: Global variables are the SYSTEM scope, whose scope id is empty.
SYSTEM_SCOPE_ID: str = ""


# =============================================================================
# Request/Response dataclasses, errors and value helpers
# =============================================================================

_INTEGER_TEXT = re.compile(r"^[+-]?\d+\Z")
_FLOAT_TEXT = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\Z")


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class SystemVariableCreateRequest:
    """Request dataclass for creating a new system variable."""
    name: str
    value: Any
    var_type: VariableType
    description: str = ""
    default_value: Any = None


@dataclass
class SystemVariableUpdateRequest:
    """Request dataclass for updating an existing system variable."""
    value: Any
    description: Optional[str] = None


@dataclass
class SystemVariableResponse:
    """Response dataclass for system variable data."""
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
class SystemVariableListResponse:
    """Response dataclass for paginated system variable list."""
    variables: List[SystemVariableResponse]
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
    """
    return json.dumps(value)


def deserialize_value(json_str: str, var_type: VariableType) -> Any:
    """
    Deserialize a JSON string to a typed value.

    :param json_str: The JSON-encoded string
    :param var_type: The expected variable type
    :returns: The deserialized value
    """
    if json_str is None:
        return None

    value = json.loads(json_str)

    # For float type, ensure we return a float even if stored as int
    if var_type == VariableType.FLOAT and isinstance(value, int) and not isinstance(value, bool):
        return float(value)

    return value


def _modern_type(var_type: VariableType) -> VariableValueType:
    """
        The modern value type of a page's :class:`VariableType`.
    """
    return VariableValueType[var_type.value.upper()]


def _page_type(value_type: VariableValueType) -> VariableType:
    """
        The page's :class:`VariableType` of a stored value type. A ``SECRET_REF`` variable (the API has it, the page never offered it) reads as text.
    """
    if value_type == VariableValueType.SECRET_REF:
        return VariableType.STRING
    return VariableType(value_type.value.lower())


class SystemVariableStore:
    """
        The Admin Variables pages' store: the SYSTEM-scope variables of the modern variables service.
    """

    def __init__(self, db_session: Any):
        """
            :param db_session: SQLAlchemy session (``None`` is fine for the pure value helpers).
        """
        self._db_session = db_session

    # ------------------------------------------------------------------
    # Value checks and typed text
    # ------------------------------------------------------------------

    def validate_value(self, value: Any, var_type: VariableType) -> bool:
        """
        Validate that a value matches the expected variable type.

        :param value: The value to validate
        :param var_type: The expected variable type
        :returns: True if valid, False otherwise
        """
        return validate_value(value, var_type)

    def serialize_value(self, value: Any, var_type: VariableType) -> str:
        """
        Serialize a value to JSON string for storage.

        :param value: The value to serialize
        :param var_type: The variable type
        :returns: JSON-encoded string
        """
        return serialize_value(value, var_type)

    def deserialize_value(self, json_str: str, var_type: VariableType) -> Any:
        """
        Deserialize a JSON string to a typed value.

        :param json_str: The JSON-encoded string
        :param var_type: The expected variable type
        :returns: The deserialized value
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
            # Digits with an optional sign: Python's int() also takes "1_000"
            # and surrounding spaces, which are not what a person typing a
            # number means to store.
            if _INTEGER_TEXT.match(value_str.strip()) is None:
                raise ValueError(f"'{value_str}' is not a valid integer")
            return int(value_str.strip())

        elif var_type == VariableType.FLOAT:
            # A decimal number with an optional sign and exponent; "inf",
            # "nan" and "1_0.5", which float() accepts, are refused.
            if _FLOAT_TEXT.match(value_str.strip()) is None:
                raise ValueError(f"'{value_str}' is not a valid float")
            return float(value_str.strip())

        elif var_type == VariableType.BOOLEAN:
            # Only the two words the form's help text names: "yes", "on"
            # and "1" used to become true without a word, and a typo such
            # as "ture" is refused rather than guessed at.
            lower_val = value_str.lower().strip()
            if lower_val == 'true':
                return True
            elif lower_val == 'false':
                return False
            else:
                raise ValueError(f"'{value_str}' is not a valid boolean (use 'true' or 'false')")

        elif var_type == VariableType.JSON:
            try:
                return json.loads(value_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {str(e)}")

        return value_str


    # ------------------------------------------------------------------
    # Create, read, update, delete
    # ------------------------------------------------------------------

    def create_variable(self, request: SystemVariableCreateRequest, user_id: Optional[str] = None) -> SystemVariableResponse:
        """
            Create a global variable.

            :param request: The variable creation request.
            :param user_id: Who is creating it.

            :returns: The created variable.
            :raises: VariableValidationError, TypeValidationError, DuplicateVariableError
        """
        if request.name is None or len(request.name.strip()) == 0:
            raise VariableValidationError("Variable name is required", field="name")
        if len(request.name) > 128:
            raise VariableValidationError("Variable name must be 128 characters or less", field="name")
        if self.validate_value(request.value, request.var_type) is False:
            raise TypeValidationError(
                "Value does not match type '{}'".format(request.var_type.value),
                expected_type=request.var_type.value, actual_type=type(request.value).__name__,
            )
        if request.default_value is not None and self.validate_value(request.default_value, request.var_type) is False:
            raise TypeValidationError(
                "Default value does not match type '{}'".format(request.var_type.value),
                expected_type=request.var_type.value, actual_type=type(request.default_value).__name__,
            )
        if self._binding(request.name) is not None:
            raise DuplicateVariableError("Variable '{}' already exists".format(request.name))

        binding = self._set(
            name=request.name, value=request.value, value_type=_modern_type(request.var_type), user_id=user_id,
            description=request.description or "", default_value=request.default_value,
        )
        return self._to_response(binding)

    def get_variable(self, name: str) -> Optional[SystemVariableResponse]:
        """
            Read a variable by name.

            :param name: The variable name.

            :returns: The variable, or ``None``.
        """
        binding = self._binding(name)
        if binding is None:
            return None
        return self._to_response(binding)

    def get_value(self, name: str, default: Any = None) -> Any:
        """
            The variable's value, or ``default`` when it is not set.

            :param name: The variable name.
            :param default: What to return when there is no such variable.
        """
        binding = self._binding(name)
        if binding is None:
            return default
        return variable_service.decode_binding_value(binding=binding)

    def update_variable(self, name: str, request: SystemVariableUpdateRequest, user_id: Optional[str] = None) -> SystemVariableResponse:
        """
            Change a variable's value (and, when given, its description). The type does not change.

            :param name: The variable name.
            :param request: The update request.
            :param user_id: Who is changing it.

            :returns: The variable as it is now.
            :raises: VariableNotFoundError, TypeValidationError
        """
        existing = self._binding(name)
        if existing is None:
            raise VariableNotFoundError("Variable '{}' not found".format(name))
        page_type = _page_type(existing.value_type)
        if self.validate_value(request.value, page_type) is False:
            raise TypeValidationError(
                "Value does not match type '{}'".format(page_type.value), expected_type=page_type.value, actual_type=type(request.value).__name__,
            )
        binding = self._set(
            name=name, value=request.value, value_type=existing.value_type, user_id=user_id, description=request.description, default_value=None,
        )
        return self._to_response(binding)

    def delete_variable(self, name: str, user_id: Optional[str] = None) -> None:
        """
            Delete a variable (its history stays).

            :param name: The variable name.
            :param user_id: Who is deleting it.

            :raises: VariableNotFoundError
        """
        if self._binding(name) is None:
            raise VariableNotFoundError("Variable '{}' not found".format(name))
        variable_service.unset_variable(
            db_session=self._db_session, scope=VariableScope.SYSTEM, scope_id=SYSTEM_SCOPE_ID, name=name, actor_user_id=user_id,
        )
        return

    def list_variables(self, offset: int = 0, limit: int = 50, search: Optional[str] = None) -> SystemVariableListResponse:
        """
            A page of variables, by name, optionally those whose name or description contains ``search``.

            :param offset: How many to skip.
            :param limit: How many to return.
            :param search: Text to look for in the name or description.
        """
        query = self._db_session.query(VariableBinding).filter(VariableBinding.scope == VariableScope.SYSTEM).filter(VariableBinding.scope_id == SYSTEM_SCOPE_ID)
        if search:
            pattern = "%{}%".format(search)
            query = query.filter(or_(VariableBinding.name.ilike(pattern), VariableBinding.description.ilike(pattern)))
        total = query.count()
        rows = query.order_by(VariableBinding.name).offset(offset).limit(limit).all()
        return SystemVariableListResponse(variables=[self._to_response(row) for row in rows], total=total, offset=offset, limit=limit)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def count_change_history(self, name: str) -> int:
        """
            How many changes a variable has had (for the history page's paging).

            :param name: The variable name.
        """
        return self._history_query(name).count()

    def get_change_history(self, name: str, offset: int = 0, limit: int = 50) -> List[VariableChangeLog]:
        """
            A variable's changes, newest first, with the old and the new value.

            :param name: The variable name.
            :param offset: How many to skip.
            :param limit: How many to return.
        """
        rows = self._history_query(name).order_by(VariableBindingHistory.changed_at.desc()).offset(offset).limit(limit).all()
        rtnval: List[VariableChangeLog] = []
        for index, row in enumerate(rows):
            rtnval.append(VariableChangeLog(
                id=offset + index + 1, variable_name=row.name,
                old_value=self._decode_loosely(row.old_value_text, row.value_type), new_value=self._decode_loosely(row.new_value_text, row.value_type),
                changed_by=self._login_of(row.changed_by_user_id), changed_at=row.changed_at,
            ))
        return rtnval

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _binding(self, name: str) -> Optional[VariableBinding]:
        """
            The SYSTEM binding with this name.
        """
        return (
            self._db_session.query(VariableBinding)
            .filter(VariableBinding.scope == VariableScope.SYSTEM).filter(VariableBinding.scope_id == SYSTEM_SCOPE_ID).filter(VariableBinding.name == name)
            .first()
        )

    def _history_query(self, name: str) -> Any:
        return (
            self._db_session.query(VariableBindingHistory)
            .filter(VariableBindingHistory.scope == VariableScope.SYSTEM).filter(VariableBindingHistory.scope_id == SYSTEM_SCOPE_ID)
            .filter(VariableBindingHistory.name == name)
        )

    def _set(
            self, *, name: str, value: Any, value_type: VariableValueType, user_id: Optional[str], description: Optional[str], default_value: Any
        ) -> VariableBinding:
        """
            Write the binding (and its history row) through the modern service.
        """
        try:
            return variable_service.set_variable(
                db_session=self._db_session, scope=VariableScope.SYSTEM, scope_id=SYSTEM_SCOPE_ID, name=name, value=value, value_type=value_type,
                actor_user_id=user_id, description=description, default_value=default_value,
            )
        except InvalidVariableValueError as xcpt:
            raise TypeValidationError(str(xcpt).splitlines()[0]) from None

    def _to_response(self, binding: VariableBinding) -> SystemVariableResponse:
        """
            A binding as the page's response.
        """
        default = variable_service.decode_text(encoded=binding.default_value_text, value_type=binding.value_type) if binding.default_value_text is not None else None
        return SystemVariableResponse(
            id=0, name=binding.name, value=variable_service.decode_binding_value(binding=binding), var_type=_page_type(binding.value_type),
            description=binding.description or "", default_value=default,
            created_at=binding.created_at if binding.created_at is not None else binding.set_at, updated_at=binding.set_at,
            updated_by=self._login_of(binding.set_by_user_id),
        )

    @staticmethod
    def _decode_loosely(text: Optional[str], value_type: VariableValueType) -> Any:
        """
            A stored value for the history, or its text when it cannot be read as the type (a variable whose type was changed through the API).
        """
        if text is None:
            return None
        try:
            return variable_service.decode_text(encoded=text, value_type=value_type)
        except (ValueError, TypeError):
            return text

    def _login_of(self, user_id: Any) -> Optional[str]:
        """
            The login name of a user id, or ``None``.
        """
        if user_id is None:
            return None
        from ccai.pychestrate.webservice.identity.users.models import IdentityUser  # noqa: E402

        user = self._db_session.query(IdentityUser).filter(IdentityUser.user_id == user_id).first()
        return user.login_name if user is not None else None


__all__ = [
    "DuplicateVariableError", "SYSTEM_SCOPE_ID", "SystemVariableCreateRequest", "SystemVariableListResponse", "SystemVariableResponse", "SystemVariableStore",
    "SystemVariableUpdateRequest", "TypeValidationError", "VariableChangeLog", "VariableNotFoundError", "VariableValidationError",
]
