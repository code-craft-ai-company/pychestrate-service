"""
.. module:: identity.users.restapi.v1.users_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/identity/users.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module provides the
webworks-native ``users`` controller.

Routes (reading needs ``system:users.read``, everything else ``system:users.write``):

* ``POST /api/v1/identity/users`` — create user.
* ``GET  /api/v1/identity/users`` — a page of users for a picker.
* ``GET  /api/v1/identity/users/{user_id}`` — read user.
* ``POST /api/v1/identity/users/{user_id}/deactivate`` — end the account's access (can be undone).
* ``POST /api/v1/identity/users/{user_id}/reactivate`` — undo a deactivation.
* ``POST /api/v1/identity/users/{user_id}/anonymise`` — erase a *deactivated* account's personal data in place
  (a data-protection request; cannot be undone). 409 with the reason when refused. These three call the same
  functions as the Users pages, so the rules (not your own account, deactivate first, not a project's owner)
  are the same.

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

from ccai.pychestrate.webservice.api.rest_authz import require_rest_permission
from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.identity.users.limits import (
    MAX_DISPLAY_NAME_LENGTH,
    display_name_too_long_message,
)
from ccai.pychestrate.webservice.identity.users import user_service
from ccai.pychestrate.webservice.identity.users.exceptions import (
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
        display_name = payload.get("display_name", "")
        if isinstance(display_name, str) and len(display_name) > MAX_DISPLAY_NAME_LENGTH:
            _abort_problem(
                request=request,
                status=422,
                detail=display_name_too_long_message() + ".",
                extensions={"invalid_fields": ["display_name"], "max_length": MAX_DISPLAY_NAME_LENGTH},
            )
        try:
            user = user_service.create_user(
                db_session=db_session,
                login_name=payload.get("login_name", ""),
                primary_email=primary_email,
                display_name=display_name,
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


def _admin_user_action(request: Request, *, action: str) -> Response:
    """
        Run one of the account-lifecycle actions the Users pages offer (``deactivate``, ``reactivate``, ``anonymise``, ``delete``) for the user in the path.
        ``delete`` is the administrator's name for ``anonymise``: the same function, the same rules, the same effect.
        The functions are :mod:`webinterface.blueprints.config.identity_admin`'s, so the REST API and the pages cannot disagree about what is
        allowed. A refusal (not found, your own account, wrong state, a project's owner) is a problem document; nothing changed.

        :param request: Incoming webworks request.
        :param action: ``deactivate``, ``reactivate``, ``anonymise`` or ``delete``.

        :returns: JSON ``{"user_id", "status"}`` (or ``"anonymised": true``, plus ``"deleted": true`` for ``delete``), or a problem response.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import identity_admin  # noqa: E402

    user_id = str(request.path_params.get("user_id", ""))
    try:
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)
        try:
            if action == "deactivate":
                identity_admin.deactivate_identity_user(db_session=db_session, user_id=user_id, actor_user_id=actor)
                body = {"user_id": user_id, "status": "deactivated"}
            elif action == "reactivate":
                status = identity_admin.reactivate_identity_user(db_session=db_session, user_id=user_id, actor_user_id=actor)
                body = {"user_id": user_id, "status": str(status).lower()}
            else:
                identity_admin.anonymise_identity_user(db_session=db_session, user_id=user_id, actor_user_id=actor)
                body = {"user_id": user_id, "status": "anonymised", "anonymised": True}
                if action == "delete":
                    body["deleted"] = True
        except identity_admin.AdminNotFoundError as xcpt:
            _abort_problem(request=request, status=404, detail=str(xcpt), extensions={"user_id": user_id})
        except (identity_admin.SelfLockoutError, identity_admin.AdminValidationError) as xcpt:
            _abort_problem(request=request, status=409, detail=str(xcpt), extensions={"user_id": user_id})
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_deactivate_user(request: Request) -> Response:
    """
        ``POST /api/v1/identity/users/{user_id}/deactivate``.
    """
    return _admin_user_action(request, action="deactivate")


def handle_reactivate_user(request: Request) -> Response:
    """
        ``POST /api/v1/identity/users/{user_id}/reactivate``.
    """
    return _admin_user_action(request, action="reactivate")


def handle_anonymise_user(request: Request) -> Response:
    """
        ``POST /api/v1/identity/users/{user_id}/anonymise``.
    """
    return _admin_user_action(request, action="anonymise")


def handle_delete_user(request: Request) -> Response:
    """
        ``DELETE /api/v1/identity/users/{user_id}`` -- delete a deactivated account: erase the person's personal data and take the account out of the lists
        (its id stays, with no name, so the audit log still resolves). The same rules and effect as ``anonymise``.
    """
    return _admin_user_action(request, action="delete")


#: The most users one page of the picker list returns.
MAX_USERS_PAGE_SIZE: int = 200
DEFAULT_USERS_PAGE_SIZE: int = 50


def handle_list_users(request: Request) -> Response:
    """
        ``GET /api/v1/identity/users`` -- a page of users for a picker.

        Query params: ``q`` (a substring of the login or display name), ``page``,
        ``per_page`` (at most 200), ``include_deleted`` (``true`` to list deleted accounts,
        which are left out otherwise). Only what a picker needs is returned: the id,
        the login name, the display name and the status (not the email address).

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying ``{items, meta}``, or a problem response.
    """
    try:
        db_session = _require_session(request=request)

        def number(name: str, default: int, maximum: int) -> int:
            raw = request.query_params.get(name, None)
            if raw is None or len(str(raw)) == 0:
                return default
            try:
                value = int(raw)
            except ValueError:
                _abort_problem(request=request, status=400, detail="Query param '{}' must be an integer.".format(name), extensions={"query_param": name})
            if value < 1 or value > maximum:
                _abort_problem(request=request, status=400, detail="Query param '{}' must be between 1 and {}.".format(name, maximum), extensions={"query_param": name})
            return value

        page = number("page", 1, 1000000)
        per_page = number("per_page", DEFAULT_USERS_PAGE_SIZE, MAX_USERS_PAGE_SIZE)
        include_deleted = str(request.query_params.get("include_deleted", "") or "").strip().lower() in ("1", "true", "yes")
        users, total = user_service.list_users(
            db_session=db_session, text=str(request.query_params.get("q", "") or ""), page=page, per_page=per_page, include_deleted=include_deleted,
        )
        body = {
            "items": [
                {
                    "user_id": str(user.user_id),
                    "login_name": user.login_name,
                    "display_name": user.display_name,
                    "status": user.status.value if user.status is not None else None,
                }
                for user in users
            ],
            "meta": {"page": page, "per_page": per_page, "total": total},
        }
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

    app.attach_route(base, methods=["GET"])(require_rest_permission(handle_list_users, permission_key="system:users.read"))
    app.attach_route(base, methods=["POST"])(require_rest_permission(handle_create_user, permission_key="system:users.write"))
    app.attach_route(
        base + "/{user_id}", methods=["GET"]
    )(require_rest_permission(handle_read_user, permission_key="system:users.read"))
    for action, handler in (("deactivate", handle_deactivate_user), ("reactivate", handle_reactivate_user), ("anonymise", handle_anonymise_user)):
        app.attach_route(
            base + "/{user_id}/" + action, methods=["POST"]
        )(require_rest_permission(handler, permission_key="system:users.write"))
    app.attach_route(
        base + "/{user_id}", methods=["DELETE"]
    )(require_rest_permission(handle_delete_user, permission_key="system:users.write"))

    return


__all__ = [
    "DEFAULT_USERS_PAGE_SIZE",
    "MAX_USERS_PAGE_SIZE",
    "USERS_PATH",
    "handle_list_users",
    "register_users_routes",
    "handle_create_user",
    "handle_read_user",
    "handle_deactivate_user",
    "handle_delete_user",
    "handle_reactivate_user",
    "handle_anonymise_user",
]
