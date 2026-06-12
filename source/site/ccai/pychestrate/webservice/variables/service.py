"""
.. module:: variables.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for 2-global-variables (M1).

.. moduleauthor:: Code Craft AI LLC

Implements the M1 skeleton: ``set_variable``, ``unset_variable``,
``get_variable`` and ``list_for_scope``. Only ``SYSTEM`` and ``PROJECT``
scopes are wired. Pipeline / job scopes and the effective-resolution
chain land in M2.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from typing import Any, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.hardening import metrics as hardening_metrics
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.variables import cache as variable_cache
from ccai.pychestrate.webservice.variables.events import VariableEventTopics
from ccai.pychestrate.webservice.variables.exceptions import (
    InvalidVariableScopeError,
    InvalidVariableValueError,
    VariableNotFoundError,
)
from ccai.pychestrate.webservice.variables.factories.database_resolver import (
    DatabaseVariableResolver,
)
from ccai.pychestrate.webservice.variables.models import (
    VariableBinding,
    VariableScope,
    VariableValueType,
)
from ccai.pychestrate.webservice.variables import repository as variable_repository


_SUPPORTED_SCOPES = frozenset({
    VariableScope.SYSTEM,
    VariableScope.PROJECT,
    VariableScope.PIPELINE,
    VariableScope.JOB,
})


_SCOPE_ORDER = (
    VariableScope.JOB,
    VariableScope.PIPELINE,
    VariableScope.PROJECT,
    VariableScope.SYSTEM,
)


def set_variable(
        *,
        db_session: DbSession,
        scope: VariableScope,
        scope_id: str,
        name: str,
        value: Any,
        value_type: VariableValueType,
        actor_user_id: Optional[str]
    ) -> VariableBinding:
    """
        Create or replace a variable binding.

        :param db_session: Active SQLAlchemy session.
        :param scope: Target scope.
        :param scope_id: Scope-local id. Empty string for ``SYSTEM`` scope.
        :param name: Variable name.
        :param value: Python value.
        :param value_type: Declared value type.
        :param actor_user_id: Acting principal.

        :returns: The persisted :class:`VariableBinding`.
        :raises: InvalidVariableScopeError, InvalidVariableValueError, SemanticError
    """
    _require_supported_scope(scope=scope, scope_id=scope_id)

    if name is None or len(name.strip()) == 0:
        raise SemanticError("set_variable requires a non-empty name")

    encoded = _encode_value(value=value, value_type=value_type)

    binding = VariableBinding(
        binding_id=new_uuid(),
        scope=scope,
        scope_id=_normalize_scope_id(scope=scope, scope_id=scope_id),
        name=name.strip(),
        value_type=value_type,
        value_text=encoded,
        set_by_user_id=actor_user_id,
        set_at=utc_now(),
    )

    persisted = variable_repository.upsert_binding(db_session=db_session, binding=binding)
    variable_cache.invalidate_for_name(name=binding.name)

    event_payload = {
        "binding_id": str(persisted.binding_id),
        "scope": scope.value,
        "scope_id": persisted.scope_id,
        "name": persisted.name,
        "value_type": value_type.value,
        "actor_user_id": actor_user_id,
        "set_at": persisted.set_at.isoformat(),
    }
    event = EntityEvent(
        topic=VariableEventTopics.VARIABLE_SET,
        payload=event_payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)

    db_session.commit()

    rtnval = persisted
    return rtnval


def unset_variable(
        *,
        db_session: DbSession,
        scope: VariableScope,
        scope_id: str,
        name: str,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Remove a variable binding.

        :param db_session: Active SQLAlchemy session.
        :param scope: Target scope.
        :param scope_id: Scope-local id.
        :param name: Variable name.
        :param actor_user_id: Acting principal.

        :returns: None.
        :raises: VariableNotFoundError, InvalidVariableScopeError
    """
    _require_supported_scope(scope=scope, scope_id=scope_id)

    normalized_id = _normalize_scope_id(scope=scope, scope_id=scope_id)
    existing = variable_repository.get_binding(
        db_session=db_session,
        scope=scope,
        scope_id=normalized_id,
        name=name,
    )
    if existing is None:
        err_msg_lines = ["Cannot unset variable — no matching binding."]
        err_msg_lines.append("SCOPE: {}/{}".format(scope.value, normalized_id))
        err_msg_lines.append("NAME: {}".format(name))
        err_msg = os.linesep.join(err_msg_lines)
        raise VariableNotFoundError(err_msg) from None

    variable_repository.delete_binding(db_session=db_session, binding=existing)
    variable_cache.invalidate_for_name(name=name)

    event_payload = {
        "scope": scope.value,
        "scope_id": normalized_id,
        "name": name,
        "actor_user_id": actor_user_id,
    }
    event = EntityEvent(
        topic=VariableEventTopics.VARIABLE_UNSET,
        payload=event_payload,
        source_event_id=new_uuid(),
    )
    enqueue_event(db_session=db_session, event=event)

    db_session.commit()

    return


def get_variable(
        *,
        db_session: DbSession,
        scope: VariableScope,
        scope_id: str,
        name: str
    ) -> VariableBinding:
    """
        Return the binding at the given scope.

        :param db_session: Active SQLAlchemy session.
        :param scope: Target scope.
        :param scope_id: Scope-local id.
        :param name: Variable name.

        :returns: The :class:`VariableBinding`.
        :raises: VariableNotFoundError
    """
    _require_supported_scope(scope=scope, scope_id=scope_id)
    normalized_id = _normalize_scope_id(scope=scope, scope_id=scope_id)

    binding = DatabaseVariableResolver.resolve(
        db_session=db_session,
        scope=scope,
        scope_id=normalized_id,
        name=name,
    )
    if binding is None:
        err_msg_lines = ["Cannot read variable — not set at scope."]
        err_msg_lines.append("SCOPE: {}/{}".format(scope.value, normalized_id))
        err_msg_lines.append("NAME: {}".format(name))
        err_msg = os.linesep.join(err_msg_lines)
        raise VariableNotFoundError(err_msg) from None

    rtnval = binding
    return rtnval


def list_for_scope(
        *,
        db_session: DbSession,
        scope: VariableScope,
        scope_id: str
    ) -> List[VariableBinding]:
    """
        Return all bindings at the given scope.

        :param db_session: Active SQLAlchemy session.
        :param scope: Target scope.
        :param scope_id: Scope-local id.

        :returns: List of :class:`VariableBinding` rows.
        :raises: InvalidVariableScopeError
    """
    _require_supported_scope(scope=scope, scope_id=scope_id)
    normalized_id = _normalize_scope_id(scope=scope, scope_id=scope_id)

    rtnval = variable_repository.list_for_scope(
        db_session=db_session,
        scope=scope,
        scope_id=normalized_id,
    )
    return rtnval


def resolve_effective(
        *,
        db_session: DbSession,
        name: str,
        project_id: Optional[str],
        pipeline_id: Optional[str],
        job_id: Optional[str],
        dereference_secrets: bool
    ) -> Any:
    """
        Resolve the effective value of a variable by walking the scope
        chain (``job → pipeline → project → system``).

        :param db_session: Active SQLAlchemy session.
        :param name: Variable name.
        :param project_id: Project id or None.
        :param pipeline_id: Pipeline id or None.
        :param job_id: Job id or None.
        :param dereference_secrets: When True and the resolved binding's
                                    ``value_type`` is ``SECRET_REF``,
                                    invoke the registered
                                    ``secret_ref_dereferencer`` chain.

        :returns: The decoded effective value or None if not found.
    """
    cache_key = (name, project_id, pipeline_id, job_id, bool(dereference_secrets))
    cached = variable_cache.get(key=cache_key)
    if cached is not variable_cache.sentinel():
        hardening_metrics.increment_counter(name="variable.resolve.cache_hit", labels={})
        return cached

    hardening_metrics.increment_counter(name="variable.resolve.cache_miss", labels={})

    entries = build_trace(
        db_session=db_session,
        name=name,
        project_id=project_id,
        pipeline_id=pipeline_id,
        job_id=job_id,
    )

    for entry in entries:
        binding = entry["binding"]
        if binding is None:
            continue
        value = decode_binding_value(binding=binding)
        if binding.value_type == VariableValueType.SECRET_REF and dereference_secrets is True:
            rtnval = _dereference_secret_ref(secret_ref=value)
            variable_cache.put(key=cache_key, value=rtnval)
            return rtnval
        rtnval = value
        variable_cache.put(key=cache_key, value=rtnval)
        return rtnval

    rtnval = None
    variable_cache.put(key=cache_key, value=rtnval)
    return rtnval


def build_trace(
        *,
        db_session: DbSession,
        name: str,
        project_id: Optional[str],
        pipeline_id: Optional[str],
        job_id: Optional[str]
    ) -> List[dict]:
    """
        Build the scope chain resolution trace for a variable name.

        :returns: Ordered list of ``{scope, scope_id, binding}`` dicts
                  from innermost to outermost scope.
    """
    entries: List[dict] = []
    for scope in _SCOPE_ORDER:
        scope_id = _scope_id_for(
            scope=scope,
            project_id=project_id,
            pipeline_id=pipeline_id,
            job_id=job_id,
        )
        if scope_id is None:
            continue

        binding = variable_repository.get_binding(
            db_session=db_session,
            scope=scope,
            scope_id=scope_id,
            name=name,
        )
        entries.append({
            "scope": scope.value,
            "scope_id": scope_id,
            "binding": binding,
        })

    return entries


def _scope_id_for(
        *,
        scope: VariableScope,
        project_id: Optional[str],
        pipeline_id: Optional[str],
        job_id: Optional[str]
    ) -> Optional[str]:
    """
        Return the appropriate scope_id or None when the caller supplied
        nothing for this scope.
    """
    if scope == VariableScope.SYSTEM:
        return ""
    if scope == VariableScope.PROJECT:
        rtnval = project_id if project_id is not None and len(str(project_id).strip()) > 0 else None
        return rtnval
    if scope == VariableScope.PIPELINE:
        rtnval = pipeline_id if pipeline_id is not None and len(str(pipeline_id).strip()) > 0 else None
        return rtnval
    if scope == VariableScope.JOB:
        rtnval = job_id if job_id is not None and len(str(job_id).strip()) > 0 else None
        return rtnval
    return None


def _dereference_secret_ref(*, secret_ref: str) -> Any:
    """
        Call the highest-priority registered ``secret_ref_dereferencer``.

        :param secret_ref: The ``secret://…`` reference string.

        :returns: The dereferenced payload.
    """
    from ccai.pychestrate.webservice.extensions.registry import (
        list_factory_implementations,
    )
    impls = list_factory_implementations(factory_protocol_name="secret_ref_dereferencer")
    for impl in impls:
        try:
            rtnval = impl.dereference(secret_ref=secret_ref)
            return rtnval
        except NotImplementedError:
            continue

    err_msg_lines = ["No secret_ref_dereferencer implementation could resolve reference."]
    err_msg_lines.append("REF: {}".format(secret_ref))
    err_msg = os.linesep.join(err_msg_lines)
    raise InvalidVariableValueError(err_msg) from None


def decode_binding_value(*, binding: VariableBinding) -> Any:
    """
        Convert a binding's stored text back into a Python value.

        :param binding: The binding whose value should be decoded.

        :returns: The decoded value.
    """
    rtnval = _decode_value(
        encoded=binding.value_text,
        value_type=binding.value_type,
    )
    return rtnval


def _encode_value(*, value: Any, value_type: VariableValueType) -> str:
    """
        Encode a Python value into the string column.

        :param value: Input value.
        :param value_type: Declared type.

        :returns: The encoded text.
        :raises: InvalidVariableValueError
    """
    if value_type == VariableValueType.STRING:
        if isinstance(value, str) is False:
            _raise_invalid_value(value_type=value_type, detail="expected str")
        rtnval = value
        return rtnval

    if value_type == VariableValueType.INTEGER:
        if isinstance(value, bool) is True or isinstance(value, int) is False:
            _raise_invalid_value(value_type=value_type, detail="expected int")
        rtnval = str(int(value))
        return rtnval

    if value_type == VariableValueType.FLOAT:
        if isinstance(value, (int, float)) is False or isinstance(value, bool) is True:
            _raise_invalid_value(value_type=value_type, detail="expected float")
        rtnval = repr(float(value))
        return rtnval

    if value_type == VariableValueType.BOOLEAN:
        if isinstance(value, bool) is False:
            _raise_invalid_value(value_type=value_type, detail="expected bool")
        rtnval = "true" if value is True else "false"
        return rtnval

    if value_type == VariableValueType.JSON:
        try:
            rtnval = json.dumps(value, sort_keys=True)
        except (TypeError, ValueError) as xcpt:
            _raise_invalid_value(value_type=value_type, detail=str(xcpt))
        return rtnval

    if value_type == VariableValueType.SECRET_REF:
        if isinstance(value, str) is False or len(value.strip()) == 0:
            _raise_invalid_value(value_type=value_type, detail="expected non-empty str")
        rtnval = value.strip()
        return rtnval

    err_msg_lines = ["Unsupported variable value_type."]
    err_msg_lines.append("VALUE_TYPE: {}".format(value_type))
    err_msg = os.linesep.join(err_msg_lines)
    raise InvalidVariableValueError(err_msg)


def _decode_value(*, encoded: Optional[str], value_type: VariableValueType) -> Any:
    """
        Decode a stored text value back into its Python form.

        :param encoded: The stored text.
        :param value_type: Declared type.

        :returns: The decoded value.
    """
    if encoded is None:
        rtnval = None
        return rtnval

    if value_type == VariableValueType.STRING:
        rtnval = encoded
        return rtnval

    if value_type == VariableValueType.INTEGER:
        rtnval = int(encoded)
        return rtnval

    if value_type == VariableValueType.FLOAT:
        rtnval = float(encoded)
        return rtnval

    if value_type == VariableValueType.BOOLEAN:
        rtnval = True if encoded == "true" else False
        return rtnval

    if value_type == VariableValueType.JSON:
        rtnval = json.loads(encoded)
        return rtnval

    if value_type == VariableValueType.SECRET_REF:
        rtnval = encoded
        return rtnval

    rtnval = encoded
    return rtnval


def _raise_invalid_value(*, value_type: VariableValueType, detail: str) -> None:
    """
        Raise :class:`InvalidVariableValueError` with a contextual message.
    """
    err_msg_lines = ["Variable value does not match declared type."]
    err_msg_lines.append("VALUE_TYPE: {}".format(value_type.value))
    err_msg_lines.append("DETAIL: {}".format(detail))
    err_msg = os.linesep.join(err_msg_lines)
    raise InvalidVariableValueError(err_msg) from None


def _require_supported_scope(*, scope: VariableScope, scope_id: str) -> None:
    """
        Enforce M1 scope constraints: only SYSTEM and PROJECT are supported.
    """
    if scope is None or scope not in _SUPPORTED_SCOPES:
        err_msg_lines = ["Scope is not supported at M1."]
        err_msg_lines.append("SCOPE: {}".format(scope))
        err_msg_lines.append("SUPPORTED: {}".format([s.value for s in _SUPPORTED_SCOPES]))
        err_msg = os.linesep.join(err_msg_lines)
        raise InvalidVariableScopeError(err_msg)

    if scope == VariableScope.PROJECT:
        if scope_id is None or len(scope_id.strip()) == 0:
            err_msg_lines = ["PROJECT scope requires a non-empty scope_id."]
            err_msg = os.linesep.join(err_msg_lines)
            raise InvalidVariableScopeError(err_msg)

    return


def _normalize_scope_id(*, scope: VariableScope, scope_id: str) -> str:
    """
        Normalize scope_id: SYSTEM uses the empty string sentinel.
    """
    if scope == VariableScope.SYSTEM:
        rtnval = ""
        return rtnval

    rtnval = scope_id.strip()
    return rtnval
