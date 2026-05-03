"""
.. module:: identity.users.restapi.v1.users_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/identity/users.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This module replaces the flask_restx
``users_controller`` next to it.

Two routes mirror the flask_restx controller's M1 matrix:

* ``POST /api/v1/identity/users`` — create user.
* ``GET  /api/v1/identity/users/{user_id}`` — read user.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.identity.users.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)


USERS_PATH = "/identity/users"


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
        :class:`_ProblemAbort` so the handler returns the response.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional extension members.

        :returns: Never returns; raises :class:`_ProblemAbort`.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session attached by
        :class:`PychestrateSessionMiddleware`.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    """
        Return the authenticated actor's user id.

        :param request: Incoming webworks request.

        :returns: User id string or None.
    """
    rtnval = getattr(request, "actor_user_id", None)
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


def _model_to_dict(user: Any) -> dict:
    """
        Render an :class:`IdentityUser` ORM row as the REST response
        dict.

        :param user: ORM user instance.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "user_id": str(user.user_id),
        "login_name": user.login_name,
        "primary_email": user.primary_email,
        "display_name": user.display_name,
        "status": user.status.value if user.status is not None else None,
        "provisioning_source": user.provisioning_source,
        "external_id": user.external_id,
        "timezone": user.timezone,
        "created_at": (
            user.created_at.isoformat() if user.created_at is not None else None
        ),
        "updated_at": (
            user.updated_at.isoformat() if user.updated_at is not None else None
        ),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_create_user(request: Request) -> Response:
    """
        ``POST /api/v1/identity/users`` — create a new identity
        user.

        :param request: Incoming webworks request.

        :returns: JSON response (201) carrying the user dict, or
                  problem response on failure.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        primary_email = payload.get("primary_email", "")
        try:
            user = user_service.create_user(
                db_session=db_session,
                login_name=payload.get("login_name", ""),
                primary_email=primary_email,
                display_name=payload.get("display_name", ""),
                timezone=payload.get("timezone", "UTC"),
                provisioning_source=payload.get("provisioning_source", "local"),
                external_id=payload.get("external_id", None),
                actor_user_id=actor_user_id,
            )
        except UserAlreadyExistsError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"primary_email": primary_email},
            )

        body = _model_to_dict(user)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_user(request: Request) -> Response:
    """
        ``GET /api/v1/identity/users/{user_id}`` — read one user
        by id. Returns 404 problem+json with the user_id as an
        extension member when the user does not exist.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the user dict, or
                  problem response on failure.
    """
    user_id = request.path_params.get("user_id", "")
    try:
        db_session = _require_session(request=request)

        try:
            user = user_service.read_user(
                db_session=db_session, user_id=user_id
            )
        except UserNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"user_id": user_id},
            )

        body = _model_to_dict(user)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_users_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the identity-users routes to a webworks application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + USERS_PATH

    app.attach_route(base, methods=["POST"])(handle_create_user)
    app.attach_route(
        base + "/{user_id}", methods=["GET"]
    )(handle_read_user)

    return


__all__ = [
    "USERS_PATH",
    "register_users_routes",
    "handle_create_user",
    "handle_read_user",
]
