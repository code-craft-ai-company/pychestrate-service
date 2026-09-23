"""
.. module:: webservice.mcp.tooling
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared building blocks for MCP tools: the tool definition,
               the tool error, and request / argument helpers.

.. moduleauthor:: Code Craft AI LLC

Every MCP tool is a :class:`ToolDefinition` whose handler takes the
webworks request and the call's ``arguments`` and returns a JSON-friendly
dict. A handler that cannot complete raises :class:`McpToolError`; the
endpoint renders it as an ``isError`` tool result so the calling agent
sees a structured failure. Authentication and authorization reuse the
request-scoped ``db_session`` / ``auth_principal`` the session middleware
attaches, and the same permission keys the REST routes check.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from ccai.webworks.routing.request import Request

from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


# MCP / application error codes used for tool-execution failures that
# are surfaced as tool results (isError) rather than protocol errors.
MCP_AUTH_REQUIRED = -32001
MCP_PERMISSION_DENIED = -32002
MCP_SESSION_UNAVAILABLE = -32003
MCP_INVALID_ARGUMENT = -32004
MCP_NOT_FOUND = -32005
MCP_CONFLICT = -32006
MCP_UNAVAILABLE = -32007


class McpToolError(Exception):
    """
        Raised by a tool implementation when the invocation cannot be
        completed. Carries an application error code + message that the
        dispatcher renders as an ``isError`` tool result so the calling
        agent sees a structured failure rather than a protocol error.
    """

    def __init__(self, *, code: int, message: str) -> None:
        super().__init__(message)
        self.code: int = code
        self.message: str = message
        return


ToolHandler = Callable[..., Dict[str, Any]]


class ToolDefinition:
    """
        A single MCP tool: its advertised name / description / input
        schema, whether it only reads, and the in-process handler that
        executes it.
    """

    def __init__(
            self,
            *,
            name: str,
            description: str,
            input_schema: Dict[str, Any],
            handler: ToolHandler,
            read_only: bool = True,
            title: Optional[str] = None
        ) -> None:
        self.name: str = name
        self.description: str = description
        self.input_schema: Dict[str, Any] = input_schema
        self.handler: ToolHandler = handler
        self.read_only: bool = read_only
        self.title: Optional[str] = title
        return

    def describe(self) -> Dict[str, Any]:
        """
            The tool's ``tools/list`` entry, with MCP tool annotations
            telling the client whether the tool changes anything.

            :returns: JSON-friendly tool description.
        """
        annotations: Dict[str, Any] = {
            "readOnlyHint": self.read_only,
            "openWorldHint": False,
        }
        if self.title is not None:
            annotations["title"] = self.title
        rtnval: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": annotations,
        }
        if self.title is not None:
            rtnval["title"] = self.title
        return rtnval


def require_session(*, request: Request) -> Any:
    """
        Resolve the request-scoped db session or raise.

        :param request: Incoming webworks request.

        :returns: The active db session.
        :raises: :class:`McpToolError` when no session is attached.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        raise McpToolError(
            code=MCP_SESSION_UNAVAILABLE,
            message="Request-scoped database session is not available.",
        )
    rtnval = db_session
    return rtnval


def require_principal(*, request: Request) -> Any:
    """
        Require an authenticated caller.

        :param request: Incoming webworks request.

        :returns: The :class:`AuthPrincipal`.
        :raises: :class:`McpToolError` when the request is anonymous.
    """
    principal = getattr(request, "auth_principal", None)
    if principal is None:
        raise McpToolError(
            code=MCP_AUTH_REQUIRED,
            message=(
                "Authentication required. Present a valid Pychestrate"
                " session or API token to invoke this tool."
            ),
        )
    rtnval = principal
    return rtnval


def has_permission(*, db_session: Any, principal: Any, permission_key: str) -> bool:
    """
        Whether ``principal`` holds ``permission_key``.

        :param db_session: Active SQLAlchemy session.
        :param principal: The caller's :class:`AuthPrincipal`.
        :param permission_key: A ``system:*`` permission key.

        :returns: ``True`` when the permission is granted.
    """
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=permission_key,
        now=datetime.now(timezone.utc),
    )
    rtnval = decision.allowed is True
    return rtnval


def require_permission(*, request: Request, db_session: Any, permission_key: str) -> Any:
    """
        Require the calling principal to hold ``permission_key``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param permission_key: Required ``system:*`` permission key.

        :returns: The :class:`AuthPrincipal`.
        :raises: :class:`McpToolError` when anonymous (auth required) or
                 the permission is denied.
    """
    principal = require_principal(request=request)
    if has_permission(db_session=db_session, principal=principal, permission_key=permission_key) is False:
        raise McpToolError(
            code=MCP_PERMISSION_DENIED,
            message="Permission denied: {}".format(permission_key),
        )
    rtnval = principal
    return rtnval


def string_argument(*, arguments: Dict[str, Any], name: str, required: bool = False) -> Optional[str]:
    """
        Read a string argument, stripped; empty counts as absent.

        :param arguments: The call's arguments.
        :param name: Argument name.
        :param required: Raise when the argument is absent.

        :returns: The value, or ``None`` when absent and optional.
        :raises: :class:`McpToolError` when required and absent, or not a
                 string.
    """
    raw = arguments.get(name, None)
    if raw is not None and not isinstance(raw, str):
        raise McpToolError(code=MCP_INVALID_ARGUMENT, message="Argument '{}' must be a string.".format(name))
    value = raw.strip() if isinstance(raw, str) else ""
    if len(value) == 0:
        if required is True:
            raise McpToolError(code=MCP_INVALID_ARGUMENT, message="Argument '{}' is required.".format(name))
        rtnval = None
    else:
        rtnval = value
    return rtnval


def int_argument(
        *,
        arguments: Dict[str, Any],
        name: str,
        default: Optional[int] = None,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
        required: bool = False
    ) -> Optional[int]:
    """
        Read an integer argument within bounds.

        :param arguments: The call's arguments.
        :param name: Argument name.
        :param default: Value when absent.
        :param minimum: Smallest accepted value.
        :param maximum: Largest accepted value.
        :param required: Raise when the argument is absent.

        :returns: The value or ``default``.
        :raises: :class:`McpToolError` when the value is not an integer or
                 out of bounds, or required and absent.
    """
    raw = arguments.get(name, None)
    if raw is None:
        if required is True:
            raise McpToolError(code=MCP_INVALID_ARGUMENT, message="Argument '{}' is required.".format(name))
        rtnval = default
        return rtnval
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise McpToolError(code=MCP_INVALID_ARGUMENT, message="Argument '{}' must be an integer.".format(name))
    if minimum is not None and raw < minimum:
        raise McpToolError(
            code=MCP_INVALID_ARGUMENT, message="Argument '{}' must be at least {}.".format(name, minimum),
        )
    if maximum is not None and raw > maximum:
        raise McpToolError(
            code=MCP_INVALID_ARGUMENT, message="Argument '{}' must be at most {}.".format(name, maximum),
        )
    rtnval = raw
    return rtnval


def bool_argument(*, arguments: Dict[str, Any], name: str, default: bool = False) -> bool:
    """
        Read a boolean argument.

        :param arguments: The call's arguments.
        :param name: Argument name.
        :param default: Value when absent.

        :returns: The value or ``default``.
        :raises: :class:`McpToolError` when the value is not a boolean.
    """
    raw = arguments.get(name, None)
    if raw is None:
        rtnval = default
    elif isinstance(raw, bool):
        rtnval = raw
    else:
        raise McpToolError(code=MCP_INVALID_ARGUMENT, message="Argument '{}' must be true or false.".format(name))
    return rtnval


def iso_or_none(value: Any) -> Optional[str]:
    """
        Render a datetime as ISO 8601 (naive values are UTC), or ``None``.

        :param value: A datetime or ``None``.

        :returns: The ISO string or ``None``.
    """
    if value is None:
        rtnval = None
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        rtnval = value.isoformat()
    else:
        rtnval = str(value)
    return rtnval
