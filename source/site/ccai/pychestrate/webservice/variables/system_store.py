"""
.. module:: variables.system_store
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Admin Variables pages' store, over the modern variables service (audit ADM-08, ``specs/model-convergence.md`` section 8).

.. moduleauthor:: Code Craft AI LLC

The Admin Variables pages used to write the legacy ``global_variables`` table, which nothing in the runtime reads: a variable created there did nothing, and one set
through ``/api/v1/variables`` never appeared there. :class:`SystemVariableStore` has the legacy :class:`GlobalVariableStore`'s interface (it *is* one: it inherits
the type checks and the parsing of typed text, and raises the same errors, so the page's handlers, templates and field-level messages are untouched) but keeps
its variables where the runtime looks: the SYSTEM-scope bindings of ``variables_variable_bindings``, with their history in ``variables_binding_history``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Optional

from sqlalchemy import or_

from ccai.pychestrate.core.managers.global_variable_store import (
    DuplicateVariableError,
    GlobalVariableCreateRequest,
    GlobalVariableListResponse,
    GlobalVariableResponse,
    GlobalVariableStore,
    GlobalVariableUpdateRequest,
    TypeValidationError,
    VariableChangeLog,
    VariableNotFoundError,
    VariableValidationError,
)
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


class SystemVariableStore(GlobalVariableStore):
    """
        The legacy store's interface over the modern variables service.
    """

    # ------------------------------------------------------------------
    # Create, read, update, delete
    # ------------------------------------------------------------------

    def create_variable(self, request: GlobalVariableCreateRequest, user_id: Optional[str] = None) -> GlobalVariableResponse:
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

    def get_variable(self, name: str) -> Optional[GlobalVariableResponse]:
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

    def update_variable(self, name: str, request: GlobalVariableUpdateRequest, user_id: Optional[str] = None) -> GlobalVariableResponse:
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

    def list_variables(self, offset: int = 0, limit: int = 50, search: Optional[str] = None) -> GlobalVariableListResponse:
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
        return GlobalVariableListResponse(variables=[self._to_response(row) for row in rows], total=total, offset=offset, limit=limit)

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

    def _to_response(self, binding: VariableBinding) -> GlobalVariableResponse:
        """
            A binding as the page's response.
        """
        default = variable_service.decode_text(encoded=binding.default_value_text, value_type=binding.value_type) if binding.default_value_text is not None else None
        return GlobalVariableResponse(
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


__all__ = ["SYSTEM_SCOPE_ID", "SystemVariableStore"]
