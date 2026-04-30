"""
.. module:: variables.restapi.v1.variablesblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/variables.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, List, Optional

from automojo.errors.exceptions import SemanticError

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.middleware_webworks import (
    get_request_actor_user_id,
)
from automojo.pychestrate.webservice.variables import (
    service as variable_service,
)
from automojo.pychestrate.webservice.variables.exceptions import (
    InvalidVariableScopeError,
    InvalidVariableValueError,
    VariableNotFoundError,
)
from automojo.pychestrate.webservice.variables.models import (
    VariableScope,
    VariableValueType,
)


VARIABLES_BASE_PATH = "/api/v1/variables"


def _binding_to_dict(binding) -> Dict[str, Any]:
    """
        Render a :class:`VariableBinding` as the REST response dict.
    """
    if binding.set_at is not None:
        set_at_field = binding.set_at.isoformat()
    else:
        set_at_field = None
    rtnval = {
        "binding_id": str(binding.binding_id),
        "scope": binding.scope.value,
        "scope_id": binding.scope_id,
        "name": binding.name,
        "value_type": binding.value_type.value,
        "value": variable_service.decode_binding_value(binding=binding),
        "set_at": set_at_field,
    }
    return rtnval


def _parse_scope(*, raw_scope: str) -> VariableScope:
    """
        Parse a URL scope segment into :class:`VariableScope`.
    """
    normalized = raw_scope.strip().upper()
    try:
        rtnval = VariableScope[normalized]
    except KeyError as exc:
        err_msg = "Unknown scope: {}".format(raw_scope)
        raise HTTPException(status_code=400, detail=err_msg) from exc
    return rtnval


def _parse_value_type(*, raw: str) -> VariableValueType:
    """
        Parse a value_type string.
    """
    normalized = raw.strip().upper()
    try:
        rtnval = VariableValueType[normalized]
    except KeyError as exc:
        err_msg = "Unknown value_type: {}".format(raw)
        raise HTTPException(status_code=400, detail=err_msg) from exc
    return rtnval


def _require_db_session(*, request: Request) -> Any:
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


def _read_json_body(*, request: Request) -> Dict[str, Any]:
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")
    try:
        decoded = request.json()
    except Exception as exc:
        err_msg = "request body must be valid JSON"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object",
        )
    rtnval = decoded
    return rtnval


def _truthy(*, raw: Optional[str]) -> bool:
    if raw is None:
        return False
    rtnval = str(raw).lower() in ("1", "true", "yes")
    return rtnval


class VariablesBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/variables`` endpoints.
    """

    base_path = VARIABLES_BASE_PATH
    tags = ["variables", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/variables/effective",
        methods=["GET"],
        doc=Doc(
            summary="Resolve effective variable value",
            description=(
                "Resolve a variable through the scope chain. "
                "Required: name. Optional: project, pipeline, job, "
                "include_trace, dereference_secrets."
            ),
        ),
    )
    def read_effective(request: Request) -> JSONResponse:
        """
            Return the effective resolved value plus optional trace.
        """
        db_session = _require_db_session(request=request)
        name = request.query_params.get("name", "")
        project_id = request.query_params.get("project", None)
        pipeline_id = request.query_params.get("pipeline", None)
        job_id = request.query_params.get("job", None)
        include_trace = _truthy(
            raw=request.query_params.get("include_trace", ""),
        )
        dereference = _truthy(
            raw=request.query_params.get("dereference_secrets", ""),
        )

        if name is None:
            raise HTTPException(
                status_code=400,
                detail="Query parameter 'name' is required",
            )
        if len(name.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="Query parameter 'name' is required",
            )

        value = variable_service.resolve_effective(
            db_session=db_session,
            name=name,
            project_id=project_id,
            pipeline_id=pipeline_id,
            job_id=job_id,
            dereference_secrets=dereference,
        )

        body: Dict[str, Any] = {"name": name, "value": value}
        if include_trace is True:
            entries = variable_service.build_trace(
                db_session=db_session,
                name=name,
                project_id=project_id,
                pipeline_id=pipeline_id,
                job_id=job_id,
            )
            trace: List[Dict[str, Any]] = []
            for entry in entries:
                binding = entry["binding"]
                if binding is not None:
                    value_type_field: Optional[str] = binding.value_type.value
                    if binding.set_by_user_id is not None:
                        set_by_field: Optional[str] = str(binding.set_by_user_id)
                    else:
                        set_by_field = None
                    if binding.set_at is not None:
                        set_at_field: Optional[str] = binding.set_at.isoformat()
                    else:
                        set_at_field = None
                else:
                    value_type_field = None
                    set_by_field = None
                    set_at_field = None
                trace_row = {
                    "scope": entry["scope"],
                    "scope_id": entry["scope_id"],
                    "present": binding is not None,
                    "value_type": value_type_field,
                    "set_by_user_id": set_by_field,
                    "set_at": set_at_field,
                }
                trace.append(trace_row)
            body["trace"] = trace

        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/variables/{scope}/{scope_id}/{name}",
        methods=["PUT"],
        doc=Doc(
            summary="Set variable",
            description="Set or replace a variable binding.",
        ),
    )
    def set_variable(request: Request) -> JSONResponse:
        """
            Set or replace a variable binding.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)

        scope = request.path_params.get("scope", "")
        scope_id = request.path_params.get("scope_id", "")
        name = request.path_params.get("name", "")

        scope_enum = _parse_scope(raw_scope=scope)
        value_type = _parse_value_type(raw=payload.get("value_type", ""))

        try:
            binding = variable_service.set_variable(
                db_session=db_session,
                scope=scope_enum,
                scope_id=scope_id,
                name=name,
                value=payload.get("value", None),
                value_type=value_type,
                actor_user_id=actor_user_id,
            )
        except InvalidVariableScopeError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except InvalidVariableValueError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        body = _binding_to_dict(binding=binding)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/variables/{scope}/{scope_id}/{name}",
        methods=["GET"],
        doc=Doc(
            summary="Read variable",
            description="Return a single variable binding.",
        ),
    )
    def get_variable(request: Request) -> JSONResponse:
        """
            Return a single variable binding.
        """
        db_session = _require_db_session(request=request)
        scope = request.path_params.get("scope", "")
        scope_id = request.path_params.get("scope_id", "")
        name = request.path_params.get("name", "")

        scope_enum = _parse_scope(raw_scope=scope)
        try:
            binding = variable_service.get_variable(
                db_session=db_session,
                scope=scope_enum,
                scope_id=scope_id,
                name=name,
            )
        except InvalidVariableScopeError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except VariableNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = _binding_to_dict(binding=binding)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/variables/{scope}/{scope_id}/{name}",
        methods=["DELETE"],
        doc=Doc(
            summary="Unset variable",
            description="Remove a variable binding.",
        ),
    )
    def unset_variable(request: Request) -> Response:
        """
            Remove a variable binding.
        """
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        scope = request.path_params.get("scope", "")
        scope_id = request.path_params.get("scope_id", "")
        name = request.path_params.get("name", "")

        scope_enum = _parse_scope(raw_scope=scope)
        try:
            variable_service.unset_variable(
                db_session=db_session,
                scope=scope_enum,
                scope_id=scope_id,
                name=name,
                actor_user_id=actor_user_id,
            )
        except InvalidVariableScopeError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except VariableNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        rtnval = Response(status_code=204, body=b"")
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/variables/{scope}/{scope_id}",
        methods=["GET"],
        doc=Doc(
            summary="List variables for scope",
            description="List all variable bindings at the given scope.",
        ),
    )
    def list_for_scope(request: Request) -> JSONResponse:
        """
            List all bindings at the given scope.
        """
        db_session = _require_db_session(request=request)
        scope = request.path_params.get("scope", "")
        scope_id = request.path_params.get("scope_id", "")

        scope_enum = _parse_scope(raw_scope=scope)
        try:
            rows = variable_service.list_for_scope(
                db_session=db_session,
                scope=scope_enum,
                scope_id=scope_id,
            )
        except InvalidVariableScopeError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        body = [_binding_to_dict(binding=row) for row in rows]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
