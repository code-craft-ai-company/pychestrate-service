"""
.. module:: variables.restapi.v1.variables_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/variables.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This module replaces the flask_restx
``variables_controller`` next to it.

Five routes mirror the flask_restx controller's matrix:

* ``PUT    /api/v1/variables/{scope}/{scope_id}/{name}``
  — set / replace a variable binding.
* ``GET    /api/v1/variables/{scope}/{scope_id}/{name}``
  — read a single binding.
* ``DELETE /api/v1/variables/{scope}/{scope_id}/{name}``
  — remove a binding.
* ``GET    /api/v1/variables/{scope}/{scope_id}``
  — list bindings at a given scope.
* ``GET    /api/v1/variables/effective?name=...&...``
  — resolve a variable through the scope chain (with optional
  trace + secret dereference).

Each path-depth is unique (1 / 2 / 3 segments after ``/variables``)
so the routes do not collide regardless of registration order.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Optional

from automojo.errors.exceptions import SemanticError
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
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


VARIABLES_PATH = "/variables"

_TRUTHY_QUERY_VALUES = ("1", "true", "yes")


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition once
        and the handler can convert it to a return at the boundary.
    """

    def __init__(self, response: Response) -> None:
        super().__init__("problem abort")
        self.response: Response = response
        return


def _abort_problem(
        *,
        request: Request,
        status: int,
        detail: str,
        extensions: Optional[dict] = None
    ) -> None:
    """
        Build a problem response from the request context and raise
        :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional extension members.

        :returns: Never returns.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: Session.
        :raises: :class:`_ProblemAbort` (503).
    """
    db_session = _resolve_db_session(request=request)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as JSON, aborting 400 on missing /
        non-dict.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request, status=400, detail="Request body must be JSON"
        )
    if not isinstance(payload, dict):
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be a JSON object",
        )

    rtnval = payload
    return rtnval


def _parse_scope_or_abort(
        *, request: Request, raw: str
    ) -> VariableScope:
    """
        Coerce a URL scope segment to :class:`VariableScope`,
        aborting 400 with the raw value as an extension on unknown.

        :param request: Incoming webworks request.
        :param raw: Raw scope string from the path.

        :returns: :class:`VariableScope`.
    """
    normalized = raw.strip().upper()
    try:
        scope = VariableScope[normalized]
    except KeyError:
        _abort_problem(
            request=request,
            status=400,
            detail="Unknown scope: {}".format(raw),
            extensions={"scope": raw},
        )
    rtnval = scope
    return rtnval


def _parse_value_type_or_abort(
        *, request: Request, raw: str
    ) -> VariableValueType:
    """
        Coerce a value_type body field to :class:`VariableValueType`,
        aborting 400 on unknown.

        :param request: Incoming webworks request.
        :param raw: Raw value_type string.

        :returns: :class:`VariableValueType`.
    """
    normalized = raw.strip().upper()
    try:
        value_type = VariableValueType[normalized]
    except KeyError:
        _abort_problem(
            request=request,
            status=400,
            detail="Unknown value_type: {}".format(raw),
            extensions={"value_type": raw},
        )
    rtnval = value_type
    return rtnval


def _is_truthy_query(*, raw: Optional[str]) -> bool:
    """
        Return True when a query parameter value is one of the
        documented truthy strings (``1`` / ``true`` / ``yes``,
        case-insensitive).

        :param raw: Raw query string value or None.

        :returns: Bool.
    """
    if raw is None:
        return False
    rtnval = raw.strip().lower() in _TRUTHY_QUERY_VALUES
    return rtnval


def _binding_extensions(
        *, scope: str, scope_id: str, name: Optional[str] = None
    ) -> dict:
    """
        Build the standard ``{scope, scope_id[, name]}`` extension
        dict attached to scope-and-name-scoped problem documents.

        :param scope: Scope string from the path.
        :param scope_id: Scope id string from the path.
        :param name: Optional variable name.

        :returns: Extension-member dict.
    """
    rtnval = {"scope": scope, "scope_id": scope_id}
    if name is not None:
        rtnval["name"] = name
    return rtnval


def _binding_to_dict(binding: Any) -> dict:
    """
        Render a :class:`VariableBinding` ORM row as the REST
        response dict.

        :param binding: ORM row.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "binding_id": str(binding.binding_id),
        "scope": binding.scope.value,
        "scope_id": binding.scope_id,
        "name": binding.name,
        "value_type": binding.value_type.value,
        "value": variable_service.decode_binding_value(binding=binding),
        "set_at": (
            binding.set_at.isoformat() if binding.set_at is not None else None
        ),
    }
    return rtnval


def _trace_to_list(*, entries: List[dict]) -> List[dict]:
    """
        Render the service's trace-entries list as JSON-friendly
        rows. Mirrors the flask controller's shape exactly:
        ``{scope, scope_id, present, value_type, set_by_user_id,
        set_at}`` per entry.

        :param entries: Trace entries from
                        ``variable_service.build_trace``.

        :returns: List of rendered rows.
    """
    rtnval = []
    for entry in entries:
        binding = entry["binding"]
        row = {
            "scope": entry["scope"],
            "scope_id": entry["scope_id"],
            "present": binding is not None,
            "value_type": (
                binding.value_type.value if binding is not None else None
            ),
            "set_by_user_id": (
                str(binding.set_by_user_id)
                if binding is not None and binding.set_by_user_id is not None
                else None
            ),
            "set_at": (
                binding.set_at.isoformat()
                if binding is not None and binding.set_at is not None
                else None
            ),
        }
        rtnval.append(row)
    return rtnval


# ---------------------------------------------------------------------------
# Handlers — single-binding triple
# ---------------------------------------------------------------------------


def handle_set_variable(request: Request) -> Response:
    """
        ``PUT /api/v1/variables/{scope}/{scope_id}/{name}`` — set
        or replace a binding.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the binding dict, or
                  problem response on failure.
    """
    scope_raw = request.path_params.get("scope", "")
    scope_id = request.path_params.get("scope_id", "")
    name = request.path_params.get("name", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        scope = _parse_scope_or_abort(request=request, raw=scope_raw)
        value_type = _parse_value_type_or_abort(
            request=request, raw=str(payload.get("value_type", ""))
        )

        try:
            binding = variable_service.set_variable(
                db_session=db_session,
                scope=scope,
                scope_id=scope_id,
                name=name,
                value=payload.get("value", None),
                value_type=value_type,
                actor_user_id=actor_user_id,
            )
        except InvalidVariableScopeError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_binding_extensions(
                    scope=scope_raw, scope_id=scope_id, name=name
                ),
            )
        except InvalidVariableValueError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_binding_extensions(
                    scope=scope_raw, scope_id=scope_id, name=name
                ),
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_binding_extensions(
                    scope=scope_raw, scope_id=scope_id, name=name
                ),
            )

        body = _binding_to_dict(binding)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_variable(request: Request) -> Response:
    """
        ``GET /api/v1/variables/{scope}/{scope_id}/{name}`` — read
        one binding.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the binding dict, or
                  problem response on failure.
    """
    scope_raw = request.path_params.get("scope", "")
    scope_id = request.path_params.get("scope_id", "")
    name = request.path_params.get("name", "")
    try:
        db_session = _require_session(request=request)
        scope = _parse_scope_or_abort(request=request, raw=scope_raw)

        try:
            binding = variable_service.get_variable(
                db_session=db_session,
                scope=scope,
                scope_id=scope_id,
                name=name,
            )
        except InvalidVariableScopeError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_binding_extensions(
                    scope=scope_raw, scope_id=scope_id, name=name
                ),
            )
        except VariableNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions=_binding_extensions(
                    scope=scope_raw, scope_id=scope_id, name=name
                ),
            )

        body = _binding_to_dict(binding)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_unset_variable(request: Request) -> Response:
    """
        ``DELETE /api/v1/variables/{scope}/{scope_id}/{name}`` —
        remove a binding.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    scope_raw = request.path_params.get("scope", "")
    scope_id = request.path_params.get("scope_id", "")
    name = request.path_params.get("name", "")
    try:
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)
        scope = _parse_scope_or_abort(request=request, raw=scope_raw)

        try:
            variable_service.unset_variable(
                db_session=db_session,
                scope=scope,
                scope_id=scope_id,
                name=name,
                actor_user_id=actor_user_id,
            )
        except InvalidVariableScopeError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_binding_extensions(
                    scope=scope_raw, scope_id=scope_id, name=name
                ),
            )
        except VariableNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions=_binding_extensions(
                    scope=scope_raw, scope_id=scope_id, name=name
                ),
            )

        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Handlers — list + effective
# ---------------------------------------------------------------------------


def handle_list_variables(request: Request) -> Response:
    """
        ``GET /api/v1/variables/{scope}/{scope_id}`` — list all
        bindings at the given scope.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying the list of binding
                  dicts, or problem response on failure.
    """
    scope_raw = request.path_params.get("scope", "")
    scope_id = request.path_params.get("scope_id", "")
    try:
        db_session = _require_session(request=request)
        scope = _parse_scope_or_abort(request=request, raw=scope_raw)

        try:
            rows = variable_service.list_for_scope(
                db_session=db_session,
                scope=scope,
                scope_id=scope_id,
            )
        except InvalidVariableScopeError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_binding_extensions(
                    scope=scope_raw, scope_id=scope_id
                ),
            )

        body = [_binding_to_dict(row) for row in rows]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_effective_variable(request: Request) -> Response:
    """
        ``GET /api/v1/variables/effective?name=...`` — resolve a
        variable through the scope chain. Optional ``project`` /
        ``pipeline`` / ``job`` narrow the scope chain;
        ``include_trace`` adds a per-scope diagnostic trace; and
        ``dereference_secrets`` requests SECRET_REF resolution.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with ``{name, value [, trace]}``,
                  or problem response on failure.
    """
    try:
        db_session = _require_session(request=request)

        name = request.query_params.get("name", "") or ""
        if name is None or len(name.strip()) == 0:
            _abort_problem(
                request=request,
                status=400,
                detail="Query parameter 'name' is required",
            )

        project_id = request.query_params.get("project", None)
        pipeline_id = request.query_params.get("pipeline", None)
        job_id = request.query_params.get("job", None)
        include_trace = _is_truthy_query(
            raw=request.query_params.get("include_trace", None)
        )
        dereference = _is_truthy_query(
            raw=request.query_params.get("dereference_secrets", None)
        )

        value = variable_service.resolve_effective(
            db_session=db_session,
            name=name,
            project_id=project_id,
            pipeline_id=pipeline_id,
            job_id=job_id,
            dereference_secrets=dereference,
        )

        body: dict = {"name": name, "value": value}
        if include_trace is True:
            entries = variable_service.build_trace(
                db_session=db_session,
                name=name,
                project_id=project_id,
                pipeline_id=pipeline_id,
                job_id=job_id,
            )
            body["trace"] = _trace_to_list(entries=entries)

        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_variables_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the variables routes to a webworks application.

        Each path-depth is unique (1 / 2 / 3 segments after
        ``/variables``) so the routes do not collide structurally.
        The fixed ``/effective`` registers first as a self-
        documenting choice that mirrors the prior ports.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix.

        :returns: None.
    """
    base = version_prefix + VARIABLES_PATH

    app.attach_route(
        base + "/effective", methods=["GET"]
    )(handle_effective_variable)

    app.attach_route(
        base + "/{scope}/{scope_id}", methods=["GET"]
    )(handle_list_variables)

    app.attach_route(
        base + "/{scope}/{scope_id}/{name}", methods=["GET"]
    )(handle_read_variable)
    app.attach_route(
        base + "/{scope}/{scope_id}/{name}", methods=["PUT"]
    )(handle_set_variable)
    app.attach_route(
        base + "/{scope}/{scope_id}/{name}", methods=["DELETE"]
    )(handle_unset_variable)

    return


__all__ = [
    "VARIABLES_PATH",
    "register_variables_routes",
    "handle_set_variable",
    "handle_read_variable",
    "handle_unset_variable",
    "handle_list_variables",
    "handle_effective_variable",
]
