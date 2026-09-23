"""
.. module:: webservice.mcp.service_endpoint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Model Context Protocol (MCP) server endpoint for the
               Pychestrate service.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module exposes a single MCP server
endpoint so AI agents can work with the Pychestrate service to manage
projects and coordinate activities.

One endpoint, ``/mcp/1/service``, speaking the MCP Streamable HTTP
transport:

* ``POST`` -- the MCP JSON-RPC 2.0 transport; replies are
  ``application/json``, and a body of only notifications or responses is
  answered ``202 Accepted`` with no body.
* ``GET`` -- ``405 Method Not Allowed`` (``Allow: POST``): the server does
  not open a server-to-client SSE stream. The problem body still names
  the endpoint and its tools for a human probing it.

The endpoint speaks the Model Context Protocol over JSON-RPC 2.0. It
implements the protocol methods an MCP client needs to discover and
invoke tools:

* ``initialize`` -- handshake; advertises ``tools`` capability.
* ``notifications/initialized`` -- post-handshake notification (no reply).
* ``ping`` -- liveness.
* ``tools/list`` -- enumerate the available tools + their JSON schemas.
* ``tools/call`` -- invoke a named tool with arguments.

Tools are wired to the in-process Pychestrate service layer (the same
functions the REST routes call) so the MCP surface and the REST surface
stay behaviourally consistent: projects and system health here, and the
lab tools -- runs and failures, queue status, RPA jobs, lab devices -- in
:mod:`mcp.lab_tools`. Authentication + authorization reuse the
request-scoped ``db_session`` / ``auth_principal`` the session middleware
attaches; the MCP path is added to that middleware's prefix allowlist so
machine callers get the same session + RBAC treatment as the REST API.
Discovery methods (``initialize`` / ``tools/list`` / ``ping``) are
unauthenticated; tool invocations are RBAC-gated on the same permission
keys the REST routes use. Each tool advertises MCP annotations saying
whether it only reads.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.mcp.lab_tools import build_lab_tools
from ccai.pychestrate.webservice.mcp.tooling import (
    MCP_AUTH_REQUIRED,
    MCP_CONFLICT,
    MCP_INVALID_ARGUMENT,
    MCP_NOT_FOUND,
    MCP_PERMISSION_DENIED,
    MCP_SESSION_UNAVAILABLE,
    McpToolError,
    ToolDefinition,
    require_permission as _require_permission,
    require_session as _require_session,
)

from ccai.pychestrate.webservice.projects import repository as project_repository
from ccai.pychestrate.webservice.projects import service as project_service
from ccai.pychestrate.webservice.projects.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    SlugValidationError,
)
from ccai.pychestrate.webservice.projects.models import ProjectState
from ccai.pychestrate.webservice.system.restapi.v1.system_health_routes import (
    build_system_health_document,
)


# ---------------------------------------------------------------------------
# Endpoint + protocol constants
# ---------------------------------------------------------------------------

MCP_SERVICE_PATH = "/mcp/1/service"

# The middleware prefix that must be allow-listed so the session
# middleware attaches db_session / auth_principal to MCP requests.
MCP_MIDDLEWARE_PREFIX = "/mcp/"

MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_SERVER_NAME = "pychestrate-service"
MCP_SERVER_VERSION = "1.0.0"

PROJECTS_READ_PERMISSION_KEY = "system:projects.read"
PROJECTS_WRITE_PERMISSION_KEY = "system:projects.write"
SYSTEM_VIEW_PERMISSION_KEY = "system:ui.admin.view"

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# JSON-RPC 2.0 standard error codes.
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

# ---------------------------------------------------------------------------
# Request-scoped resolution helpers
# ---------------------------------------------------------------------------

def _resolve_actor_user_id(*, request: Request) -> Optional[str]:
    """
        Return the acting user id attached by the session middleware.

        :param request: Incoming webworks request.

        :returns: The actor user id, or None when anonymous.
    """
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _serialize_project(*, project: Any) -> Dict[str, Any]:
    """
        Render a ``Project`` ORM row as a JSON-friendly dict for MCP
        tool results.

        :param project: ORM project instance.

        :returns: JSON-friendly project dict.
    """
    state_value = None
    if project.state is not None:
        state_value = project.state.value

    owning_group_id = None
    if project.owning_group_id is not None:
        owning_group_id = str(project.owning_group_id)

    created_at = None
    if getattr(project, "created_at", None) is not None:
        created_at = project.created_at.isoformat()

    updated_at = None
    if getattr(project, "updated_at", None) is not None:
        updated_at = project.updated_at.isoformat()

    rtnval = {
        "project_id": str(project.project_id),
        "slug": project.slug,
        "display_name": project.display_name,
        "description": project.description,
        "state": state_value,
        "owning_group_id": owning_group_id,
        "template_id": project.template_id,
        "template_version": project.template_version,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    return rtnval


def _coerce_state_filter(*, raw: Optional[str]) -> Optional[ProjectState]:
    """
        Coerce a caller-supplied state string into a :class:`ProjectState`.

        :param raw: Optional caller-supplied state string.

        :returns: A ProjectState, or None when ``raw`` is empty.
        :raises: :class:`McpToolError` on an unrecognized value.
    """
    if raw is None:
        rtnval = None
        return rtnval

    stripped = raw.strip()
    if len(stripped) == 0:
        rtnval = None
        return rtnval

    try:
        rtnval = ProjectState(stripped.upper())
    except ValueError:
        raise McpToolError(
            code=MCP_INVALID_ARGUMENT,
            message="Unknown project state: {!r}.".format(raw),
        )
    return rtnval


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tool_list_projects(
        *, request: Request, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
    """
        Tool ``list_projects`` -- enumerate projects the caller can see.

        :param request: Incoming webworks request.
        :param arguments: Tool arguments (``state``, ``page``, ``per_page``).

        :returns: A dict with an ``items`` list and pagination ``meta``.
    """
    db_session = _require_session(request=request)
    _require_permission(
        request=request,
        db_session=db_session,
        permission_key=PROJECTS_READ_PERMISSION_KEY,
    )

    state_filter = _coerce_state_filter(raw=arguments.get("state", None))

    page = arguments.get("page", 1)
    if not isinstance(page, int) or page < 1:
        page = 1

    per_page = arguments.get("per_page", DEFAULT_PAGE_SIZE)
    if not isinstance(per_page, int) or per_page < 1:
        per_page = DEFAULT_PAGE_SIZE
    if per_page > MAX_PAGE_SIZE:
        per_page = MAX_PAGE_SIZE

    offset = (page - 1) * per_page
    rows = project_repository.list_projects(
        db_session=db_session,
        state=state_filter,
        offset=offset,
        limit=per_page,
    )

    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(_serialize_project(project=row))

    rtnval = {
        "items": items,
        "meta": {
            "page": page,
            "per_page": per_page,
            "returned": len(items),
        },
    }
    return rtnval


def _tool_get_project(
        *, request: Request, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
    """
        Tool ``get_project`` -- read a single project by slug.

        :param request: Incoming webworks request.
        :param arguments: Tool arguments (``slug``).

        :returns: The serialized project dict.
    """
    db_session = _require_session(request=request)
    _require_permission(
        request=request,
        db_session=db_session,
        permission_key=PROJECTS_READ_PERMISSION_KEY,
    )

    slug = arguments.get("slug", "")
    if not isinstance(slug, str) or len(slug.strip()) == 0:
        raise McpToolError(
            code=MCP_INVALID_ARGUMENT,
            message="Argument 'slug' is required.",
        )

    try:
        project = project_service.read_project_by_slug(
            db_session=db_session,
            slug=slug.strip(),
        )
    except ProjectNotFoundError:
        raise McpToolError(
            code=MCP_NOT_FOUND,
            message="No project found with slug {!r}.".format(slug),
        )

    rtnval = _serialize_project(project=project)
    return rtnval


def _tool_create_project(
        *, request: Request, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
    """
        Tool ``create_project`` -- create a new project.

        :param request: Incoming webworks request.
        :param arguments: Tool arguments (``slug``, ``display_name``,
                          ``description``, ``owning_group_id``).

        :returns: The serialized created project dict.
    """
    db_session = _require_session(request=request)
    _require_permission(
        request=request,
        db_session=db_session,
        permission_key=PROJECTS_WRITE_PERMISSION_KEY,
    )
    actor_user_id = _resolve_actor_user_id(request=request)

    slug = arguments.get("slug", "")
    if not isinstance(slug, str) or len(slug.strip()) == 0:
        raise McpToolError(
            code=MCP_INVALID_ARGUMENT,
            message="Argument 'slug' is required.",
        )

    display_name = arguments.get("display_name", "")
    if not isinstance(display_name, str) or len(display_name.strip()) == 0:
        raise McpToolError(
            code=MCP_INVALID_ARGUMENT,
            message="Argument 'display_name' is required.",
        )

    description = arguments.get("description", "")
    if not isinstance(description, str):
        description = ""

    owning_group_id = arguments.get("owning_group_id", None)

    try:
        project = project_service.create_project(
            db_session=db_session,
            slug=slug.strip(),
            display_name=display_name.strip(),
            description=description,
            owning_group_id=owning_group_id,
            template_id=None,
            template_version=None,
            actor_user_id=actor_user_id,
        )
    except SlugValidationError as xcpt:
        raise McpToolError(code=MCP_INVALID_ARGUMENT, message=str(xcpt))
    except ProjectAlreadyExistsError as xcpt:
        raise McpToolError(code=MCP_CONFLICT, message=str(xcpt))

    rtnval = _serialize_project(project=project)
    return rtnval


def _tool_system_health(
        *, request: Request, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
    """
        Tool ``system_health`` -- aggregate subsystem-health summary used
        to coordinate activities against current service status.

        :param request: Incoming webworks request.
        :param arguments: Tool arguments (none).

        :returns: The system-health document.
    """
    db_session = _require_session(request=request)
    _require_permission(
        request=request,
        db_session=db_session,
        permission_key=SYSTEM_VIEW_PERMISSION_KEY,
    )
    rtnval = build_system_health_document(request=request)
    return rtnval


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def _build_tool_registry() -> List[ToolDefinition]:
    """
        Build the ordered list of MCP tools the endpoint advertises.

        :returns: The tool definitions.
    """
    tools: List[ToolDefinition] = []

    tools.append(ToolDefinition(
        name="list_projects",
        description=(
            "List Pychestrate projects. Optionally filter by lifecycle"
            " state and page through results."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "enum": ["ACTIVE", "ARCHIVED"],
                    "description": "Filter by project lifecycle state.",
                },
                "page": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "1-based page number.",
                },
                "per_page": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_PAGE_SIZE,
                    "description": "Page size.",
                },
            },
            "additionalProperties": False,
        },
        handler=_tool_list_projects,
    ))

    tools.append(ToolDefinition(
        name="get_project",
        description="Read a single Pychestrate project by its slug.",
        input_schema={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "The project slug.",
                },
            },
            "required": ["slug"],
            "additionalProperties": False,
        },
        handler=_tool_get_project,
    ))

    tools.append(ToolDefinition(
        name="create_project",
        description=(
            "Create a new Pychestrate project. Requires the"
            " 'system:projects.write' permission."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Desired project slug (canonicalized).",
                },
                "display_name": {
                    "type": "string",
                    "description": "Human-friendly project name.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional project description.",
                },
                "owning_group_id": {
                    "type": "string",
                    "description": "Optional owning group id.",
                },
            },
            "required": ["slug", "display_name"],
            "additionalProperties": False,
        },
        handler=_tool_create_project,
        read_only=False,
    ))

    tools.append(ToolDefinition(
        name="system_health",
        description=(
            "Get the aggregate Pychestrate subsystem-health summary to"
            " coordinate activities against current service status."
        ),
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_tool_system_health,
    ))

    tools.extend(build_lab_tools())
    return tools


_TOOL_REGISTRY: List[ToolDefinition] = _build_tool_registry()


def _tool_by_name(*, name: str) -> Optional[ToolDefinition]:
    """
        Look up a tool definition by advertised name.

        :param name: Tool name.

        :returns: The matching :class:`ToolDefinition` or None.
    """
    rtnval: Optional[ToolDefinition] = None
    for tool in _TOOL_REGISTRY:
        if tool.name == name:
            rtnval = tool
            break
    return rtnval


# ---------------------------------------------------------------------------
# JSON-RPC envelope helpers
# ---------------------------------------------------------------------------

def _jsonrpc_result(*, request_id: Any, result: Any) -> Dict[str, Any]:
    """
        Build a JSON-RPC 2.0 success envelope.

        :param request_id: The id echoed from the request.
        :param result: The result payload.

        :returns: A JSON-RPC response dict.
    """
    rtnval = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }
    return rtnval


def _jsonrpc_error(
        *, request_id: Any, code: int, message: str
    ) -> Dict[str, Any]:
    """
        Build a JSON-RPC 2.0 error envelope.

        :param request_id: The id echoed from the request (may be None).
        :param code: JSON-RPC error code.
        :param message: Error message.

        :returns: A JSON-RPC error response dict.
    """
    rtnval = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
    return rtnval


# ---------------------------------------------------------------------------
# MCP method handlers
# ---------------------------------------------------------------------------

def _handle_initialize(*, params: Dict[str, Any]) -> Dict[str, Any]:
    """
        Handle the MCP ``initialize`` handshake.

        :param params: The initialize params (clientInfo etc.).

        :returns: The initialize result advertising server capabilities.
    """
    rtnval = {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {
            "tools": {
                "listChanged": False,
            },
        },
        "serverInfo": {
            "name": MCP_SERVER_NAME,
            "version": MCP_SERVER_VERSION,
        },
        "instructions": (
            "Pychestrate service MCP endpoint. Use 'tools/list' to"
            " discover tools for projects, runs and their failures, the"
            " execution queue, RPA jobs and lab devices, then 'tools/call'"
            " to invoke them. Authenticate with a Pychestrate API token"
            " (Authorization: Bearer pyc_...) or a signed-in session."
        ),
    }
    return rtnval


def _handle_tools_list() -> Dict[str, Any]:
    """
        Handle ``tools/list`` -- enumerate advertised tools.

        :returns: A result with the ``tools`` array.
    """
    tools: List[Dict[str, Any]] = []
    for tool in _TOOL_REGISTRY:
        tools.append(tool.describe())
    rtnval = {"tools": tools}
    return rtnval


def _refuse_write_tool_for_read_only_token(*, request: Request, tool: ToolDefinition) -> None:
    """
        Refuse a state-changing tool to a caller authenticated with a
        ``read-only`` API token. The session middleware lets such tokens
        POST to this endpoint (reads travel over POST too) and leaves the
        scope check to each tool's ``read_only`` flag.

        :param request: Incoming webworks request.
        :param tool: The tool being called.

        :returns: None.
        :raises: :class:`McpToolError` when the tool changes state and the
                 token is read-only.
    """
    principal = getattr(request, "auth_principal", None)
    if tool.read_only is False and getattr(principal, "token_scope", None) == "read-only":
        raise McpToolError(
            code=MCP_PERMISSION_DENIED,
            message=(
                "This API token is read-only; the {} tool changes state and"
                " needs a read-write token.".format(tool.name)
            ),
        )
    return


def _handle_tools_call(
        *, request: Request, params: Dict[str, Any]
    ) -> Dict[str, Any]:
    """
        Handle ``tools/call`` -- invoke a named tool. Tool-execution
        failures are returned as ``isError`` results (per MCP) so the
        calling agent receives a structured failure rather than a
        transport error.

        :param request: Incoming webworks request.
        :param params: The call params (``name`` + ``arguments``).

        :returns: An MCP tool-call result with ``content`` (and
                  ``structuredContent`` on success).
        :raises: :class:`McpToolError` with :data:`MCP_INVALID_ARGUMENT`
                 when the tool name is unknown (rendered as a protocol
                 error by the dispatcher).
    """
    name = params.get("name", None)
    if name is None or not isinstance(name, str):
        raise McpToolError(
            code=JSONRPC_INVALID_PARAMS,
            message="tools/call requires a string 'name'.",
        )

    arguments = params.get("arguments", None)
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise McpToolError(
            code=JSONRPC_INVALID_PARAMS,
            message="tools/call 'arguments' must be an object.",
        )

    tool = _tool_by_name(name=name)
    if tool is None:
        raise McpToolError(
            code=JSONRPC_INVALID_PARAMS,
            message="Unknown tool: {!r}.".format(name),
        )

    try:
        _refuse_write_tool_for_read_only_token(request=request, tool=tool)
        result = tool.handler(request=request, arguments=arguments)
    except McpToolError as xcpt:
        rtnval = {
            "content": [
                {
                    "type": "text",
                    "text": "Error [{}]: {}".format(xcpt.code, xcpt.message),
                }
            ],
            "isError": True,
        }
        return rtnval

    result_text = json.dumps(result, indent=2, default=str)
    rtnval = {
        "content": [
            {
                "type": "text",
                "text": result_text,
            }
        ],
        "structuredContent": result,
        "isError": False,
    }
    return rtnval


# ---------------------------------------------------------------------------
# JSON-RPC dispatch
# ---------------------------------------------------------------------------

def _dispatch_message(
        *, request: Request, message: Any
    ) -> Optional[Dict[str, Any]]:
    """
        Dispatch a single JSON-RPC message. Returns a JSON-RPC response
        dict, or ``None`` for notifications (no reply expected).

        :param request: Incoming webworks request.
        :param message: A decoded JSON-RPC message object.

        :returns: A JSON-RPC response dict, or None for notifications.
    """
    if not isinstance(message, dict):
        rtnval = _jsonrpc_error(
            request_id=None,
            code=JSONRPC_INVALID_REQUEST,
            message="JSON-RPC message must be an object.",
        )
        return rtnval

    method = message.get("method", None)
    request_id = message.get("id", None)
    is_notification = "id" not in message

    params = message.get("params", None)
    if params is None:
        params = {}
    if not isinstance(params, dict):
        params = {}

    if method is None or not isinstance(method, str):
        if is_notification is True:
            rtnval = None
            return rtnval
        rtnval = _jsonrpc_error(
            request_id=request_id,
            code=JSONRPC_INVALID_REQUEST,
            message="JSON-RPC message requires a string 'method'.",
        )
        return rtnval

    # Notifications: acknowledge by returning None (no reply body).
    if is_notification is True:
        rtnval = None
        return rtnval

    if method == "initialize":
        result = _handle_initialize(params=params)
        rtnval = _jsonrpc_result(request_id=request_id, result=result)
        return rtnval

    if method == "ping":
        rtnval = _jsonrpc_result(request_id=request_id, result={})
        return rtnval

    if method == "tools/list":
        result = _handle_tools_list()
        rtnval = _jsonrpc_result(request_id=request_id, result=result)
        return rtnval

    if method == "tools/call":
        try:
            result = _handle_tools_call(request=request, params=params)
        except McpToolError as xcpt:
            rtnval = _jsonrpc_error(
                request_id=request_id,
                code=xcpt.code,
                message=xcpt.message,
            )
            return rtnval
        rtnval = _jsonrpc_result(request_id=request_id, result=result)
        return rtnval

    rtnval = _jsonrpc_error(
        request_id=request_id,
        code=JSONRPC_METHOD_NOT_FOUND,
        message="Method not found: {}.".format(method),
    )
    return rtnval


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def handle_mcp_service(request: Request) -> Response:
    """
        ``POST /mcp/1/service`` -- the MCP JSON-RPC 2.0 transport.

        Accepts a single JSON-RPC request object or a batch array.
        Returns the corresponding response(s). A payload consisting only
        of notifications yields a ``202 Accepted`` with an empty body.

        :param request: Incoming webworks request.

        :returns: JSON response carrying the JSON-RPC reply.
    """
    try:
        payload = request.json()
    except Exception:
        body = _jsonrpc_error(
            request_id=None,
            code=JSONRPC_PARSE_ERROR,
            message="Request body is not valid JSON.",
        )
        rtnval: Response = JSONResponse(content=body, status_code=200)
        return rtnval

    # Batch form: a JSON array of messages.
    if isinstance(payload, list):
        if len(payload) == 0:
            body = _jsonrpc_error(
                request_id=None,
                code=JSONRPC_INVALID_REQUEST,
                message="JSON-RPC batch must not be empty.",
            )
            rtnval = JSONResponse(content=body, status_code=200)
            return rtnval

        responses: List[Dict[str, Any]] = []
        for message in payload:
            response = _dispatch_message(request=request, message=message)
            if response is not None:
                responses.append(response)

        if len(responses) == 0:
            rtnval = Response(status_code=202)
            return rtnval

        rtnval = JSONResponse(content=responses, status_code=200)
        return rtnval

    # Single message form.
    response = _dispatch_message(request=request, message=payload)
    if response is None:
        rtnval = Response(status_code=202)
        return rtnval

    rtnval = JSONResponse(content=response, status_code=200)
    return rtnval


def handle_mcp_service_descriptor(request: Request) -> Response:
    """
        ``GET /mcp/1/service`` -- ``405 Method Not Allowed``. Under the
        MCP Streamable HTTP transport a client may GET the endpoint to
        open a server-to-client SSE stream; a server that offers none
        must answer 405. The problem body still names the endpoint,
        protocol and tools for a human probing it.

        :param request: Incoming webworks request.

        :returns: 405 problem response with ``Allow: POST``.
    """
    rtnval = problem_response_for_http_status(
        status=405,
        detail=(
            "This is a Model Context Protocol endpoint: send JSON-RPC 2.0"
            " messages with POST. It does not open a server-to-client stream."
        ),
        instance=MCP_SERVICE_PATH,
        extensions={
            "service": MCP_SERVER_NAME,
            "version": MCP_SERVER_VERSION,
            "protocol": "Model Context Protocol",
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "transport": "Streamable HTTP (POST only)",
            "endpoint": MCP_SERVICE_PATH,
            "tools": [tool.name for tool in _TOOL_REGISTRY],
        },
    )
    rtnval.headers["Allow"] = "POST"
    return rtnval


def register_mcp_service_routes(*, app: Any) -> None:
    """
        Attach the MCP service routes to a webworks application.

        Called from :func:`register_service_extensions` in
        :mod:`app_pychestrate_main` before ``app.startup``. The endpoint
        lives at the fixed path :data:`MCP_SERVICE_PATH` (``/mcp/1/service``)
        -- it is intentionally not under the versioned ``/api/v1`` REST
        prefix. The session middleware's prefix allowlist must include
        :data:`MCP_MIDDLEWARE_PREFIX` so request-scoped ``db_session`` /
        ``auth_principal`` are attached for MCP calls.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
    app.attach_route(MCP_SERVICE_PATH, methods=["POST"])(handle_mcp_service)
    app.attach_route(
        MCP_SERVICE_PATH, methods=["GET"]
    )(handle_mcp_service_descriptor)
    return


__all__ = [
    "MCP_SERVICE_PATH",
    "MCP_MIDDLEWARE_PREFIX",
    "MCP_PROTOCOL_VERSION",
    "handle_mcp_service",
    "handle_mcp_service_descriptor",
    "register_mcp_service_routes",
]
