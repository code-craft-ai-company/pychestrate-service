"""
.. module:: security.auth.restapi.v1.auth_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/auth.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module is the webworks-native
REST surface for the M1 auth-flow endpoints.

One route at M1:

* ``POST /api/v1/auth/logout`` — close a session by id.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.security.auth import session_service


AUTH_PATH = "/auth"


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
        *, request: Request, status: int, detail: str
    ) -> None:
    """
        Build a problem response from the request context and raise
        :class:`_ProblemAbort` so the handler returns the response.

        :param request: Incoming webworks request (used for the
                        ``instance`` URI).
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.

        :returns: Never returns; raises :class:`_ProblemAbort`.
    """
    response = problem_response_for_http_status(
        status=status, detail=detail, instance=request.path
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session attached by
        :class:`PychestrateSessionMiddleware`, or ``None`` when no
        middleware has populated it. Module-level so tests can
        patch this rather than constructing a full middleware stack.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort with a 503
        problem document.

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
        Decode the request body as JSON, aborting with a 400 when
        the body is missing or non-dict.

        :param request: Incoming webworks request.

        :returns: Decoded JSON object.
        :raises: :class:`_ProblemAbort` (400).
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


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_logout(request: Request) -> Response:
    """
        ``POST /api/v1/auth/logout`` — close the session named in
        the request body and return ``{session_id, status: closed}``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) on success, problem response
                  on failure.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)

        session_id = payload.get("session_id", "")
        if not isinstance(session_id, str) or len(session_id) == 0:
            _abort_problem(
                request=request,
                status=400,
                detail="session_id is required",
            )

        session_service.close_session(
            db_session=db_session, session_id=session_id
        )

        body = {"session_id": session_id, "status": "closed"}
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_auth_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the auth-flow routes to a webworks application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + AUTH_PATH
    app.attach_route(base + "/logout", methods=["POST"])(handle_logout)
    return


__all__ = [
    "AUTH_PATH",
    "register_auth_routes",
    "handle_logout",
]
