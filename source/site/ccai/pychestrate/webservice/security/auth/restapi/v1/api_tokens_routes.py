"""
.. module:: security.auth.restapi.v1.api_tokens_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for API tokens, service
               accounts, and ``/api/v1/me``.

.. moduleauthor:: Code Craft AI LLC

Self-service (any signed-in principal):

* ``GET    /api/v1/me``                          -- who am I, and how did
                                                    I authenticate.
* ``GET    /api/v1/me/api-tokens``               -- my tokens.
* ``POST   /api/v1/me/api-tokens``               -- issue a token for me;
                                                    the secret is in the
                                                    201 body, once.
* ``GET    /api/v1/me/api-tokens/{token_id}``    -- one of my tokens.
* ``DELETE /api/v1/me/api-tokens/{token_id}``    -- revoke one of my
                                                    tokens.

Administration:

* ``GET    /api/v1/api-tokens``                  -- every token
                                                    (``system:auth.read``).
* ``DELETE /api/v1/api-tokens/{token_id}``       -- revoke any token
                                                    (``system:auth.admin``).
* ``GET    /api/v1/service-accounts``            -- service accounts
                                                    (``system:users.read``).
* ``POST   /api/v1/service-accounts``            -- create one
                                                    (``system:users.write``).
* ``GET    /api/v1/service-accounts/{user_id}/api-tokens``
                                                 -- its tokens
                                                    (``system:auth.read``).
* ``POST   /api/v1/service-accounts/{user_id}/api-tokens``
                                                 -- issue it a token
                                                    (``system:auth.admin``).

Issuing a token requires a signed-in (cookie) session: a request that
authenticated with an API token may list and revoke tokens but not
issue new ones, so a leaked token cannot mint itself a longer-lived
successor.

Error responses are RFC 7807 problem documents.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.api.rest_authz import (
    AUTHENTICATED_ONLY,
    require_rest_permission,
)
from ccai.pychestrate.webservice.security.auth.api_tokens import service as token_service
from ccai.pychestrate.webservice.security.auth.api_tokens.exceptions import (
    ApiTokenNotFoundError,
    ApiTokenValidationError,
    ServiceAccountNotFoundError,
)


ME_PATH = "/me"
ME_TOKENS_PATH = "/me/api-tokens"
TOKENS_PATH = "/api-tokens"
SERVICE_ACCOUNTS_PATH = "/service-accounts"

TOKENS_READ_PERMISSION_KEY = "system:auth.read"
TOKENS_ADMIN_PERMISSION_KEY = "system:auth.admin"
SERVICE_ACCOUNTS_READ_PERMISSION_KEY = "system:users.read"
SERVICE_ACCOUNTS_WRITE_PERMISSION_KEY = "system:users.write"


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a problem response so
        nested helpers can signal an error once and the handler
        returns it at the boundary.
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
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional extension members.

        :returns: Never returns.
        :raises: :class:`_ProblemAbort`
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _require_db_session(request: Request) -> Any:
    """
        Return the request-scoped db session or abort with 503.

        :param request: Incoming webworks request.

        :returns: Session.
        :raises: :class:`_ProblemAbort` (503).
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _require_principal(request: Request) -> Any:
    """
        Return the authenticated principal or abort with 401.

        :param request: Incoming webworks request.

        :returns: The principal.
        :raises: :class:`_ProblemAbort` (401).
    """
    principal = getattr(request, "auth_principal", None)
    if principal is None or getattr(principal, "user_id", None) is None:
        _abort_problem(request=request, status=401, detail="Authentication required.")
    rtnval = principal
    return rtnval


def _authenticated_with_api_token(principal: Any) -> bool:
    """
        Whether the principal authenticated with an API token.

        :param principal: Request principal.

        :returns: Boolean.
    """
    rtnval = len(str(getattr(principal, "token_id", "") or "")) > 0
    return rtnval


def _refuse_token_issuance_by_token(*, request: Request, principal: Any) -> None:
    """
        Abort with 403 when an API-token-authenticated request tries to
        issue a token.

        :param request: Incoming webworks request.
        :param principal: Request principal.

        :returns: None.
        :raises: :class:`_ProblemAbort` (403).
    """
    if _authenticated_with_api_token(principal) is True:
        _abort_problem(
            request=request,
            status=403,
            detail=(
                "API tokens cannot issue API tokens. Sign in to the web UI"
                " (Account > API tokens) to create one."
            ),
        )
    return


def _decode_json_object_or_abort(*, request: Request, allow_empty: bool) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object.

        :param request: Incoming webworks request.
        :param allow_empty: Treat an empty body as ``{}``.

        :returns: Decoded object.
        :raises: :class:`_ProblemAbort` (400).
    """
    raw_body = getattr(request, "body", b"")
    if callable(raw_body):
        raw_body = raw_body()
    if allow_empty is True and (raw_body is None or len(raw_body) == 0):
        return {}
    try:
        payload = request.json()
    except Exception:
        payload = None
    if payload is None:
        _abort_problem(request=request, status=400, detail="Request body must be JSON")
    if not isinstance(payload, dict):
        _abort_problem(request=request, status=400, detail="Request body must be a JSON object")
    rtnval = payload
    return rtnval


def _path_param(*, request: Request, name: str) -> str:
    """
        Read a path parameter as a trimmed string.

        :param request: Incoming webworks request.
        :param name: Parameter name.

        :returns: Value (may be empty).
    """
    params = getattr(request, "path_params", None) or {}
    rtnval = str(params.get(name, "") or "").strip()
    return rtnval


def _issue_token(*, request: Request, user_id: str, actor_user_id: str) -> Response:
    """
        Shared body of the two token-issuing handlers.

        :param request: Incoming webworks request.
        :param user_id: The user the token acts as.
        :param actor_user_id: Who is issuing it.

        :returns: 201 JSON response carrying the secret once.
        :raises: :class:`_ProblemAbort`
    """
    payload = _decode_json_object_or_abort(request=request, allow_empty=False)
    db_session = _require_db_session(request)
    try:
        issued = token_service.create_api_token(
            db_session=db_session,
            user_id=user_id,
            name=payload.get("name", None),
            lifetime_days=payload.get("expires_in_days", None),
            scope=payload.get("scope", None),
            actor_user_id=actor_user_id,
        )
    except ApiTokenValidationError as xcpt:
        _abort_problem(request=request, status=422, detail=str(xcpt))

    response = JSONResponse(content=issued.to_dict(), status_code=201)
    # The body carries a credential: keep it out of every cache.
    response.set_header("Cache-Control", "no-store")
    rtnval = response
    return rtnval


# ---------------------------------------------------------------------------
# Self-service handlers
# ---------------------------------------------------------------------------


def handle_get_me(request: Request) -> Response:
    """
        ``GET /api/v1/me`` -- the signed-in principal: identity, account
        kind (``user`` or ``service_account``), and how the request
        authenticated (session or API token, with the token's name,
        scope, and expiry). ``pyc whoami`` and ``pyc login`` use it.

        :param request: Incoming webworks request.

        :returns: 200 JSON response, or a problem response.
    """
    try:
        principal = _require_principal(request)
        db_session = _require_db_session(request)

        from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
            IdentityUser,
        )
        user = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.user_id == str(principal.user_id))
            .first()
        )
        if user is None:
            _abort_problem(request=request, status=401, detail="Authentication required.")

        if _authenticated_with_api_token(principal) is True:
            expires_at = getattr(principal, "token_expires_at", None)
            authentication = {
                "method": "api_token",
                "token_id": principal.token_id,
                "token_name": getattr(principal, "token_name", ""),
                "token_scope": getattr(principal, "token_scope", ""),
                "token_expires_at": expires_at.isoformat() if expires_at is not None else None,
            }
        else:
            authentication = {"method": "session"}

        account_kind = "user"
        if token_service.is_service_account(user=user) is True:
            account_kind = "service_account"

        body = {
            "user_id": str(user.user_id),
            "login_name": user.login_name,
            "display_name": user.display_name,
            "primary_email": user.primary_email,
            "status": user.status.value if user.status is not None else None,
            "account_kind": account_kind,
            "authentication": authentication,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_list_my_tokens(request: Request) -> Response:
    """
        ``GET /api/v1/me/api-tokens`` -- the caller's tokens, newest
        first, including expired and revoked ones.

        :param request: Incoming webworks request.

        :returns: 200 ``{"items": [...], "total": n}``.
    """
    try:
        principal = _require_principal(request)
        db_session = _require_db_session(request)
        views = token_service.list_api_tokens(
            db_session=db_session, user_id=str(principal.user_id)
        )
        items = [view.to_dict() for view in views]
        rtnval: Response = JSONResponse(
            content={"items": items, "total": len(items)}, status_code=200
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_create_my_token(request: Request) -> Response:
    """
        ``POST /api/v1/me/api-tokens`` -- issue a token that acts as the
        caller. Body: ``{"name": str, "expires_in_days": int (1-366,
        default 90), "scope": "read-write" | "read-only"}``. Requires a
        signed-in session (403 for token-authenticated callers).

        :param request: Incoming webworks request.

        :returns: 201 with the token view plus ``token`` (shown once).
    """
    try:
        principal = _require_principal(request)
        _refuse_token_issuance_by_token(request=request, principal=principal)
        rtnval = _issue_token(
            request=request,
            user_id=str(principal.user_id),
            actor_user_id=str(principal.user_id),
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_get_my_token(request: Request) -> Response:
    """
        ``GET /api/v1/me/api-tokens/{token_id}`` -- one of the caller's
        tokens (404 for anyone else's).

        :param request: Incoming webworks request.

        :returns: 200 token view, or 404.
    """
    token_id = _path_param(request=request, name="token_id")
    try:
        principal = _require_principal(request)
        db_session = _require_db_session(request)
        try:
            view = token_service.read_api_token(
                db_session=db_session,
                token_id=token_id,
                owner_user_id=str(principal.user_id),
            )
        except ApiTokenNotFoundError:
            _abort_problem(
                request=request, status=404, detail="API token not found.",
                extensions={"token_id": token_id},
            )
        rtnval: Response = JSONResponse(content=view.to_dict(), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_revoke_my_token(request: Request) -> Response:
    """
        ``DELETE /api/v1/me/api-tokens/{token_id}`` -- revoke one of the
        caller's tokens (404 for anyone else's). A token may revoke
        itself.

        :param request: Incoming webworks request.

        :returns: 200 with the revoked token's view.
    """
    token_id = _path_param(request=request, name="token_id")
    try:
        principal = _require_principal(request)
        db_session = _require_db_session(request)
        try:
            view = token_service.revoke_api_token(
                db_session=db_session,
                token_id=token_id,
                actor_user_id=str(principal.user_id),
                owner_user_id=str(principal.user_id),
            )
        except ApiTokenNotFoundError:
            _abort_problem(
                request=request, status=404, detail="API token not found.",
                extensions={"token_id": token_id},
            )
        rtnval: Response = JSONResponse(content=view.to_dict(), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Administration handlers
# ---------------------------------------------------------------------------


def handle_list_tokens(request: Request) -> Response:
    """
        ``GET /api/v1/api-tokens[?user_id=<id>]`` -- every token (or one
        user's), newest first.

        :param request: Incoming webworks request.

        :returns: 200 ``{"items": [...], "total": n}``.
    """
    try:
        db_session = _require_db_session(request)
        user_id = None
        query_params = getattr(request, "query_params", None)
        if query_params is not None:
            raw_user_id = query_params.get("user_id", None)
            if raw_user_id is not None and len(str(raw_user_id).strip()) > 0:
                user_id = str(raw_user_id).strip()
        views = token_service.list_api_tokens(db_session=db_session, user_id=user_id)
        items = [view.to_dict() for view in views]
        rtnval: Response = JSONResponse(
            content={"items": items, "total": len(items)}, status_code=200
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_revoke_token(request: Request) -> Response:
    """
        ``DELETE /api/v1/api-tokens/{token_id}`` -- revoke any token.

        :param request: Incoming webworks request.

        :returns: 200 with the revoked token's view, or 404.
    """
    token_id = _path_param(request=request, name="token_id")
    try:
        principal = _require_principal(request)
        db_session = _require_db_session(request)
        try:
            view = token_service.revoke_api_token(
                db_session=db_session,
                token_id=token_id,
                actor_user_id=str(principal.user_id),
            )
        except ApiTokenNotFoundError:
            _abort_problem(
                request=request, status=404, detail="API token not found.",
                extensions={"token_id": token_id},
            )
        rtnval: Response = JSONResponse(content=view.to_dict(), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_list_service_accounts(request: Request) -> Response:
    """
        ``GET /api/v1/service-accounts`` -- every service account with
        its count of working tokens.

        :param request: Incoming webworks request.

        :returns: 200 ``{"items": [...], "total": n}``.
    """
    try:
        db_session = _require_db_session(request)
        views = token_service.list_service_accounts(db_session=db_session)
        items = [view.to_dict() for view in views]
        rtnval: Response = JSONResponse(
            content={"items": items, "total": len(items)}, status_code=200
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_create_service_account(request: Request) -> Response:
    """
        ``POST /api/v1/service-accounts`` -- body
        ``{"login_name": str, "display_name": str}``. The account has no
        password; bind roles to it on the Users / Roles pages and issue
        it tokens.

        :param request: Incoming webworks request.

        :returns: 201 service-account view, or 422 on a bad / taken name.
    """
    try:
        principal = _require_principal(request)
        payload = _decode_json_object_or_abort(request=request, allow_empty=False)
        db_session = _require_db_session(request)
        try:
            user = token_service.create_service_account(
                db_session=db_session,
                login_name=payload.get("login_name", None),
                display_name=payload.get("display_name", None),
                actor_user_id=str(principal.user_id),
            )
        except ApiTokenValidationError as xcpt:
            _abort_problem(request=request, status=422, detail=str(xcpt))
        body = {
            "user_id": str(user.user_id),
            "login_name": user.login_name,
            "display_name": user.display_name,
            "status": user.status.value if user.status is not None else None,
            "active_token_count": 0,
        }
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def _require_service_account(*, request: Request, db_session: Any) -> Any:
    """
        Load the service account named by the ``user_id`` path
        parameter or abort with 404.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.

        :returns: The :class:`IdentityUser`.
        :raises: :class:`_ProblemAbort` (404).
    """
    user_id = _path_param(request=request, name="user_id")
    try:
        user = token_service.read_service_account(db_session=db_session, user_id=user_id)
    except ServiceAccountNotFoundError:
        _abort_problem(
            request=request, status=404, detail="Service account not found.",
            extensions={"user_id": user_id},
        )
    rtnval = user
    return rtnval


def handle_list_service_account_tokens(request: Request) -> Response:
    """
        ``GET /api/v1/service-accounts/{user_id}/api-tokens``.

        :param request: Incoming webworks request.

        :returns: 200 ``{"items": [...], "total": n}``, or 404.
    """
    try:
        db_session = _require_db_session(request)
        user = _require_service_account(request=request, db_session=db_session)
        views = token_service.list_api_tokens(db_session=db_session, user_id=str(user.user_id))
        items = [view.to_dict() for view in views]
        rtnval: Response = JSONResponse(
            content={"items": items, "total": len(items)}, status_code=200
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_create_service_account_token(request: Request) -> Response:
    """
        ``POST /api/v1/service-accounts/{user_id}/api-tokens`` -- issue
        a token that acts as the service account. Same body as
        ``POST /api/v1/me/api-tokens``; requires a signed-in session.

        :param request: Incoming webworks request.

        :returns: 201 with the token view plus ``token`` (shown once).
    """
    try:
        principal = _require_principal(request)
        _refuse_token_issuance_by_token(request=request, principal=principal)
        db_session = _require_db_session(request)
        user = _require_service_account(request=request, db_session=db_session)
        rtnval = _issue_token(
            request=request,
            user_id=str(user.user_id),
            actor_user_id=str(principal.user_id),
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_api_tokens_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the API-token, service-account, and ``/me`` routes.

        :param app: WebWorks application.
        :param version_prefix: Versioned API prefix (``"/api/v1"``).

        :returns: None.
    """
    me_base = version_prefix + ME_PATH
    me_tokens = version_prefix + ME_TOKENS_PATH
    tokens = version_prefix + TOKENS_PATH
    accounts = version_prefix + SERVICE_ACCOUNTS_PATH

    app.attach_route(me_base, methods=["GET"])(
        require_rest_permission(handle_get_me, permission_key=AUTHENTICATED_ONLY)
    )
    app.attach_route(me_tokens, methods=["GET"])(
        require_rest_permission(handle_list_my_tokens, permission_key=AUTHENTICATED_ONLY)
    )
    app.attach_route(me_tokens, methods=["POST"])(
        require_rest_permission(handle_create_my_token, permission_key=AUTHENTICATED_ONLY)
    )
    app.attach_route(me_tokens + "/{token_id}", methods=["GET"])(
        require_rest_permission(handle_get_my_token, permission_key=AUTHENTICATED_ONLY)
    )
    app.attach_route(me_tokens + "/{token_id}", methods=["DELETE"])(
        require_rest_permission(handle_revoke_my_token, permission_key=AUTHENTICATED_ONLY)
    )

    app.attach_route(tokens, methods=["GET"])(
        require_rest_permission(handle_list_tokens, permission_key=TOKENS_READ_PERMISSION_KEY)
    )
    app.attach_route(tokens + "/{token_id}", methods=["DELETE"])(
        require_rest_permission(handle_revoke_token, permission_key=TOKENS_ADMIN_PERMISSION_KEY)
    )

    app.attach_route(accounts, methods=["GET"])(
        require_rest_permission(
            handle_list_service_accounts, permission_key=SERVICE_ACCOUNTS_READ_PERMISSION_KEY
        )
    )
    app.attach_route(accounts, methods=["POST"])(
        require_rest_permission(
            handle_create_service_account, permission_key=SERVICE_ACCOUNTS_WRITE_PERMISSION_KEY
        )
    )
    app.attach_route(accounts + "/{user_id}/api-tokens", methods=["GET"])(
        require_rest_permission(
            handle_list_service_account_tokens, permission_key=TOKENS_READ_PERMISSION_KEY
        )
    )
    app.attach_route(accounts + "/{user_id}/api-tokens", methods=["POST"])(
        require_rest_permission(
            handle_create_service_account_token, permission_key=TOKENS_ADMIN_PERMISSION_KEY
        )
    )
    return


__all__ = [
    "ME_PATH",
    "ME_TOKENS_PATH",
    "SERVICE_ACCOUNTS_PATH",
    "TOKENS_PATH",
    "handle_create_my_token",
    "handle_create_service_account",
    "handle_create_service_account_token",
    "handle_get_me",
    "handle_get_my_token",
    "handle_list_my_tokens",
    "handle_list_service_account_tokens",
    "handle_list_service_accounts",
    "handle_list_tokens",
    "handle_revoke_my_token",
    "handle_revoke_token",
    "register_api_tokens_routes",
]
