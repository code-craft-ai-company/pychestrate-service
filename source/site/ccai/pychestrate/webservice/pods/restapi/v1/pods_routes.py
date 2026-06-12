"""
.. module:: pods.restapi.v1.pods_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for the Layer-3 pod surface.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module provides the
webworks-native ``pods`` controller.

Thirteen routes spread across four logical groupings under
``/api/v1/projects/{project_id}/...``:

* **Pod definitions** (versioned spec storage)
    * ``POST /pod-definitions``
    * ``GET  /pod-definitions``
    * ``GET  /pod-definitions/{pod_id}``

* **Pod lifecycle** (state machine + history)
    * ``GET  /pods/{pod_id}/state``
    * ``GET  /pods/{pod_id}/state/history``

* **Pod registration** (per-client claim records + topology)
    * ``GET  /pods/{pod_id}/registration``
    * ``GET  /pods/{pod_id}/registrations``
    * ``GET  /pods/{pod_id}/topology``

* **Pod templates** (materialization workflow)
    * ``POST /pod-templates``
    * ``GET  /pod-templates``
    * ``POST /pod-templates/{template_id}:materialize``
      (AIP-style colon verb)

* **Run-scoped pod variables**
    * ``PUT    /runs/{run_id}/variables/{name}?pod_id=...``
    * ``DELETE /runs/{run_id}/variables/{name}?pod_id=...``

Like the agents port (#125), the namespace path is empty -- each
route lands under ``/projects/{project_id}/...`` directly. This
port shares the ``/projects/...`` URL-prefix space with the
pending projects port (#projects_controller, last in the
migration backlog); the pods routes here use distinct sub-paths
(``pod-definitions``, ``pods``, ``pod-templates``, ``runs``) so
no collision is possible with project-level routes that live at
``/projects/{project_id}`` (depth 3) or ``/projects/{project_id}
/<other>``.

Error responses are RFC 7807 problem documents per the
convention in :mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from ccai.errors.exceptions import SemanticError
from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.pods.definitions_service import (
    create_pod_definition,
    list_pod_definitions,
    read_pod_definition,
    read_pod_definition_version,
)
from ccai.pychestrate.webservice.pods.dynamic_service import (
    create_pod_template,
    list_pod_templates,
    start_materialization,
)
from ccai.pychestrate.webservice.pods.exceptions import (
    MaterializationError,
    MemberKindNotRegisteredError,
    PodDefinitionAlreadyExistsError,
    PodDefinitionNotFoundError,
    PodSpecValidationError,
    PodTemplateNotFoundError,
)
from ccai.pychestrate.webservice.pods.lifecycle_service import (
    read_state,
    read_state_history,
)
from ccai.pychestrate.webservice.pods.scoped_config_service import (
    delete_scoped_variable,
    set_scoped_variable,
)
from ccai.pychestrate.webservice.pods.static_service import (
    list_registration_history,
    read_active_registration,
)
from ccai.pychestrate.webservice.pods.topology_service import (
    compose_topology,
    topology_as_dict,
)


PROJECTS_PATH = "/projects"

DEFAULT_HISTORY_OFFSET = 0
DEFAULT_HISTORY_LIMIT = 100


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
        Build a problem response and raise :class:`_ProblemAbort`.
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


def _parse_int_query_or_abort(
        *,
        request: Request,
        name: str,
        default: int
    ) -> int:
    """
        Coerce a query parameter to int, aborting 400 problem+json
        with the bad value as an extension on coercion failure.
        Defaults are returned untouched when the param is absent.

        :param request: Incoming webworks request.
        :param name: Query parameter name.
        :param default: Default integer value when absent.

        :returns: Coerced int.
    """
    raw = request.query_params.get(name, None)
    if raw is None or len(raw) == 0:
        return default
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        _abort_problem(
            request=request,
            status=400,
            detail="Invalid {!r} argument".format(name),
            extensions={name: raw},
        )
    return rtnval


def _require_query_pod_id(*, request: Request) -> str:
    """
        Read the ``pod_id`` query parameter; abort 400 problem+json
        when missing / blank. The scoped-variable handlers thread
        the pod_id through the query string rather than the URL
        because variables are run-scoped, not pod-scoped, but the
        write goes through a pod-aware service path.

        :param request: Incoming webworks request.

        :returns: Non-blank pod_id string.
    """
    raw = request.query_params.get("pod_id", "")
    if raw is None or len(raw.strip()) == 0:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param 'pod_id' is required",
        )
    rtnval = raw
    return rtnval


def _project_extensions(*, project_id: str, **kwargs: Any) -> dict:
    """
        Build the standard ``{project_id, ...}`` extension dict
        attached to project-scoped problem documents.

        :param project_id: Project id.
        :param kwargs: Additional extension members.

        :returns: Extension-member dict.
    """
    rtnval: dict = {"project_id": project_id}
    for key, value in kwargs.items():
        rtnval[key] = value
    return rtnval


def _definition_to_dict(definition: Any, version: Any) -> dict:
    """
        Render a (definition, version) pair as the REST response
        dict.

        :param definition: ORM PodDefinition row.
        :param version: ORM PodDefinitionVersion row (or None).

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "pod_id": str(definition.pod_id),
        "project_id": str(definition.project_id),
        "pod_name": definition.pod_name,
        "current_version": int(definition.current_version),
        "spec": version.spec_json if version is not None else None,
        "spec_hash": version.spec_hash if version is not None else None,
        "created_at": (
            definition.created_at.isoformat()
            if definition.created_at is not None else None
        ),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers — pod definitions
# ---------------------------------------------------------------------------


def handle_create_pod_definition(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/pod-definitions`` —
        create a new pod definition (version 1).

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the definition dict, or
                  problem response on failure.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        pod_name = payload.get("pod_name", "")
        try:
            definition = create_pod_definition(
                db_session=db_session,
                project_id=project_id,
                pod_name=pod_name,
                spec=payload.get("spec", {}),
                actor_user_id=actor,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_project_extensions(project_id=project_id),
            )
        except PodSpecValidationError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_project_extensions(project_id=project_id),
            )
        except MemberKindNotRegisteredError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_project_extensions(project_id=project_id),
            )
        except PodDefinitionAlreadyExistsError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions=_project_extensions(
                    project_id=project_id, pod_name=pod_name
                ),
            )

        version = read_pod_definition_version(
            db_session=db_session,
            pod_id=str(definition.pod_id),
            version=int(definition.current_version),
        )
        body = _definition_to_dict(definition, version)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_pod_definitions(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pod-definitions`` —
        list all definitions in a project.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of
                  definition dicts.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        definitions = list_pod_definitions(
            db_session=db_session, project_id=project_id
        )
        body = []
        for definition in definitions:
            version = read_pod_definition_version(
                db_session=db_session,
                pod_id=str(definition.pod_id),
                version=int(definition.current_version),
            )
            body.append(_definition_to_dict(definition, version))
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_pod_definition(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pod-definitions/{pod_id}``
        — read one pod definition.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the definition dict, or
                  problem response on failure.
    """
    project_id = request.path_params.get("project_id", "")
    pod_id = request.path_params.get("pod_id", "")
    try:
        db_session = _require_session(request=request)

        try:
            definition = read_pod_definition(
                db_session=db_session, pod_id=pod_id
            )
            version = read_pod_definition_version(
                db_session=db_session,
                pod_id=pod_id,
                version=int(definition.current_version),
            )
        except PodDefinitionNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions=_project_extensions(
                    project_id=project_id, pod_id=pod_id
                ),
            )

        body = _definition_to_dict(definition, version)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Handlers — pod state + state history
# ---------------------------------------------------------------------------


def handle_read_pod_state(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pods/{pod_id}/state`` —
        read the current state row for a pod.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the state dict, or
                  problem response on failure.
    """
    project_id = request.path_params.get("project_id", "")
    pod_id = request.path_params.get("pod_id", "")
    try:
        db_session = _require_session(request=request)

        try:
            row = read_state(db_session=db_session, pod_id=pod_id)
        except PodDefinitionNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions=_project_extensions(
                    project_id=project_id, pod_id=pod_id
                ),
            )

        body = {
            "pod_id": str(row.pod_id),
            "state": row.state.value,
            "previous_state": (
                row.previous_state.value
                if row.previous_state is not None else None
            ),
            "last_transition_at": (
                row.last_transition_at.isoformat()
                if row.last_transition_at is not None else None
            ),
            "last_transition_event": row.last_transition_event,
            "transition_cursor": int(row.transition_cursor or 0),
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_pod_state_history(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pods/{pod_id}/state/history``
        — list transition log rows with pagination.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a list of log rows, or
                  problem response on failure.
    """
    pod_id = request.path_params.get("pod_id", "")
    try:
        db_session = _require_session(request=request)
        offset = _parse_int_query_or_abort(
            request=request, name="offset", default=DEFAULT_HISTORY_OFFSET
        )
        limit = _parse_int_query_or_abort(
            request=request, name="limit", default=DEFAULT_HISTORY_LIMIT
        )

        rows = read_state_history(
            db_session=db_session, pod_id=pod_id, offset=offset, limit=limit,
        )
        body = [
            {
                "log_id": str(row.log_id),
                "from_state": (
                    row.from_state.value
                    if row.from_state is not None else None
                ),
                "to_state": row.to_state.value,
                "event_kind": row.event_kind,
                "actor": row.actor,
                "applied_at": (
                    row.applied_at.isoformat()
                    if row.applied_at is not None else None
                ),
            }
            for row in rows
        ]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Handlers — registration + topology
# ---------------------------------------------------------------------------


def handle_read_pod_registration(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pods/{pod_id}/registration``
        — read the active registration row for a pod.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the registration dict, or
                  404 problem+json when no active registration.
    """
    project_id = request.path_params.get("project_id", "")
    pod_id = request.path_params.get("pod_id", "")
    try:
        db_session = _require_session(request=request)
        row = read_active_registration(db_session=db_session, pod_id=pod_id)
        if row is None:
            _abort_problem(
                request=request,
                status=404,
                detail="No active registration",
                extensions=_project_extensions(
                    project_id=project_id, pod_id=pod_id
                ),
            )

        body = {
            "registration_id": str(row.registration_id),
            "pod_id": str(row.pod_id),
            "pod_definition_version": int(row.pod_definition_version),
            "client_id": (
                str(row.client_id) if row.client_id is not None else None
            ),
            "state": row.state.value,
            "report_hash": row.report_hash,
            "registered_at": (
                row.registered_at.isoformat()
                if row.registered_at is not None else None
            ),
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_pod_registrations(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pods/{pod_id}/registrations``
        — list the full registration history for a pod.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a list of registration
                  dicts.
    """
    pod_id = request.path_params.get("pod_id", "")
    try:
        db_session = _require_session(request=request)
        rows = list_registration_history(
            db_session=db_session, pod_id=pod_id
        )
        body = [
            {
                "registration_id": str(row.registration_id),
                "state": row.state.value,
                "pod_definition_version": int(row.pod_definition_version),
                "registered_at": (
                    row.registered_at.isoformat()
                    if row.registered_at is not None else None
                ),
                "deregistered_at": (
                    row.deregistered_at.isoformat()
                    if row.deregistered_at is not None else None
                ),
                "deregister_reason": row.deregister_reason,
            }
            for row in rows
        ]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_pod_topology(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pods/{pod_id}/topology``
        — compose the pod's topology graph.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the topology dict, or
                  problem response on failure.
    """
    project_id = request.path_params.get("project_id", "")
    pod_id = request.path_params.get("pod_id", "")
    try:
        db_session = _require_session(request=request)

        try:
            graph = compose_topology(
                db_session=db_session, pod_id=pod_id
            )
        except PodDefinitionNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions=_project_extensions(
                    project_id=project_id, pod_id=pod_id
                ),
            )

        body = topology_as_dict(graph=graph)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Handlers — pod templates
# ---------------------------------------------------------------------------


def handle_create_pod_template(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/pod-templates`` —
        create a new pod template.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the template dict, or
                  problem response on failure.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        try:
            template = create_pod_template(
                db_session=db_session,
                project_id=project_id,
                name=payload.get("name", ""),
                template_kind=payload.get("template_kind", ""),
                source_json=payload.get("source_json", {}),
                parameter_schema=payload.get("parameter_schema", None),
                actor_user_id=actor,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_project_extensions(project_id=project_id),
            )

        body = {
            "template_id": str(template.template_id),
            "project_id": str(template.project_id),
            "name": template.name,
            "template_kind": template.template_kind,
            "source_version": int(template.source_version),
        }
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_pod_templates(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pod-templates`` —
        list templates in the project.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a list of template
                  summary dicts.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        rows = list_pod_templates(
            db_session=db_session, project_id=project_id
        )
        body = [
            {
                "template_id": str(row.template_id),
                "name": row.name,
                "template_kind": row.template_kind,
                "source_version": int(row.source_version),
            }
            for row in rows
        ]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_materialize_pod_template(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/pod-templates/{template_id}:materialize``
        — start a materialization job. Returns 202 with the
        materialization summary.

        :param request: Incoming webworks request.

        :returns: JSON response (202) or problem response on
                  failure.
    """
    project_id = request.path_params.get("project_id", "")
    template_id = request.path_params.get("template_id", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        try:
            materialization = start_materialization(
                db_session=db_session,
                template_id=template_id,
                parameters=payload.get("parameters", {}) or {},
                actor_user_id=actor,
            )
        except PodTemplateNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions=_project_extensions(
                    project_id=project_id, template_id=template_id
                ),
            )
        except MaterializationError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions=_project_extensions(
                    project_id=project_id, template_id=template_id
                ),
            )

        body = {
            "materialization_id": str(materialization.materialization_id),
            "template_id": str(materialization.template_id),
            "state": materialization.state.value,
            "pod_id": (
                str(materialization.pod_id)
                if materialization.pod_id is not None else None
            ),
        }
        rtnval: Response = JSONResponse(content=body, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Handlers — run-scoped variables
# ---------------------------------------------------------------------------


def handle_set_scoped_variable(request: Request) -> Response:
    """
        ``PUT /api/v1/projects/{project_id}/runs/{run_id}/variables/{name}?pod_id=...``
        — set a run-scoped variable. ``pod_id`` is supplied via
        the query string because variables are run-scoped but the
        write goes through a pod-aware service path.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the variable dict, or
                  problem response on failure.
    """
    run_id = request.path_params.get("run_id", "")
    name = request.path_params.get("name", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)
        pod_id = _require_query_pod_id(request=request)

        try:
            row = set_scoped_variable(
                db_session=db_session,
                run_id=run_id,
                pod_id=pod_id,
                name=name,
                value=payload.get("value", None),
                value_schema=payload.get("value_schema", None),
                locked=bool(payload.get("locked", False)),
                actor_user_id=actor,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={
                    "run_id": run_id,
                    "pod_id": pod_id,
                    "name": name,
                },
            )

        body = {
            "variable_id": str(row.variable_id),
            "run_id": str(row.run_id),
            "pod_id": str(row.pod_id),
            "name": row.name,
            "locked": bool(row.locked),
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_delete_scoped_variable(request: Request) -> Response:
    """
        ``DELETE /api/v1/projects/{project_id}/runs/{run_id}/variables/{name}?pod_id=...``
        — remove a run-scoped variable. Returns 204 on success.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    run_id = request.path_params.get("run_id", "")
    name = request.path_params.get("name", "")
    try:
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)
        pod_id = _require_query_pod_id(request=request)

        delete_scoped_variable(
            db_session=db_session,
            run_id=run_id,
            pod_id=pod_id,
            name=name,
            actor_user_id=actor,
        )
        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_pods_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the pod routes to a webworks application.

        Each route family lives at a distinct sub-path under
        ``/projects/{project_id}/`` (``pod-definitions``, ``pods``,
        ``pod-templates``, ``runs``) so no in-namespace collision
        is possible. The AIP-style ``:materialize`` action verb on
        the template route matches via regex backtracking on the
        StringConverter -- UUIDs do not contain colons so the
        match is unambiguous.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix.

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH

    # Pod definitions
    app.attach_route(
        base + "/{project_id}/pod-definitions", methods=["GET"]
    )(handle_list_pod_definitions)
    app.attach_route(
        base + "/{project_id}/pod-definitions", methods=["POST"]
    )(handle_create_pod_definition)
    app.attach_route(
        base + "/{project_id}/pod-definitions/{pod_id}", methods=["GET"]
    )(handle_read_pod_definition)

    # Pod lifecycle
    app.attach_route(
        base + "/{project_id}/pods/{pod_id}/state", methods=["GET"]
    )(handle_read_pod_state)
    app.attach_route(
        base + "/{project_id}/pods/{pod_id}/state/history", methods=["GET"]
    )(handle_read_pod_state_history)

    # Registration + topology
    app.attach_route(
        base + "/{project_id}/pods/{pod_id}/registration", methods=["GET"]
    )(handle_read_pod_registration)
    app.attach_route(
        base + "/{project_id}/pods/{pod_id}/registrations", methods=["GET"]
    )(handle_list_pod_registrations)
    app.attach_route(
        base + "/{project_id}/pods/{pod_id}/topology", methods=["GET"]
    )(handle_read_pod_topology)

    # Pod templates
    app.attach_route(
        base + "/{project_id}/pod-templates", methods=["GET"]
    )(handle_list_pod_templates)
    app.attach_route(
        base + "/{project_id}/pod-templates", methods=["POST"]
    )(handle_create_pod_template)
    app.attach_route(
        base + "/{project_id}/pod-templates/{template_id}:materialize",
        methods=["POST"],
    )(handle_materialize_pod_template)

    # Run-scoped pod variables
    app.attach_route(
        base + "/{project_id}/runs/{run_id}/variables/{name}",
        methods=["PUT"],
    )(handle_set_scoped_variable)
    app.attach_route(
        base + "/{project_id}/runs/{run_id}/variables/{name}",
        methods=["DELETE"],
    )(handle_delete_scoped_variable)

    return


__all__ = [
    "PROJECTS_PATH",
    "DEFAULT_HISTORY_OFFSET",
    "DEFAULT_HISTORY_LIMIT",
    "register_pods_routes",
    "handle_create_pod_definition",
    "handle_list_pod_definitions",
    "handle_read_pod_definition",
    "handle_read_pod_state",
    "handle_read_pod_state_history",
    "handle_read_pod_registration",
    "handle_list_pod_registrations",
    "handle_read_pod_topology",
    "handle_create_pod_template",
    "handle_list_pod_templates",
    "handle_materialize_pod_template",
    "handle_set_scoped_variable",
    "handle_delete_scoped_variable",
]
