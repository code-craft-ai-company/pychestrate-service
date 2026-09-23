"""
.. module:: webinterface.blueprints.config.routes_tokens
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native pages for API tokens and service
               accounts (machine identity).

.. moduleauthor:: Code Craft AI LLC

Every signed-in user manages their own tokens:

* ``GET  /account/api-tokens``                     -- my tokens + the
                                                      create form.
* ``POST /account/api-tokens/create``              -- issue a token; the
                                                      page renders
                                                      directly with a
                                                      one-time panel
                                                      showing the secret
                                                      and the ``pyc
                                                      login`` command.
* ``POST /account/api-tokens/{token_id}/revoke``   -- revoke one of mine.

Administrators manage service accounts and everyone's tokens:

* ``GET  /admin/api-tokens``                       -- service accounts,
                                                      every token
                                                      (``system:auth.read``).
* ``POST /admin/service-accounts/create``          -- new service account
                                                      (``system:users.write``).
* ``POST /admin/service-accounts/{user_id}/api-tokens/create``
                                                   -- issue it a token
                                                      (``system:auth.admin``).
* ``POST /admin/api-tokens/{token_id}/revoke``     -- revoke any token
                                                      (``system:auth.admin``).

The secret of a new token is rendered once, in the POST response
itself: it never rides in the flash cookie and cannot be fetched
again. The handlers call :mod:`security.auth.api_tokens.service`
directly, as the sibling admin pages call their services.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import Response

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    _attach_session_to_response,
    _build_default_template_context,
    _has_permission,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_admin_permission_for,
    _resolve_authenticated_request,
    _wrap_admin_handler_in_shell,
)


_module_logger = logging.getLogger(__name__)


ACCOUNT_PATH: str = "/account"

TOKENS_READ_PERMISSION: str = "system:auth.read"
TOKENS_ADMIN_PERMISSION: str = "system:auth.admin"
SERVICE_ACCOUNTS_WRITE_PERMISSION: str = "system:users.write"

# (endpoint_name, full_path, methods)
_ACCOUNT_ROUTE_TABLE = (
    ("config.account_api_tokens", ACCOUNT_PATH + "/api-tokens", ("GET",)),
    ("config.account_api_token_create", ACCOUNT_PATH + "/api-tokens/create", ("POST",)),
    (
        "config.account_api_token_revoke",
        ACCOUNT_PATH + "/api-tokens/{token_id}/revoke",
        ("POST",),
    ),
)

_ADMIN_ROUTE_TABLE = (
    ("config.admin_api_tokens", CONFIG_PATH + "/api-tokens", ("GET",)),
    (
        "config.service_account_create",
        CONFIG_PATH + "/service-accounts/create",
        ("POST",),
    ),
    (
        "config.service_account_token_create",
        CONFIG_PATH + "/service-accounts/{user_id}/api-tokens/create",
        ("POST",),
    ),
    (
        "config.admin_api_token_revoke",
        CONFIG_PATH + "/api-tokens/{token_id}/revoke",
        ("POST",),
    ),
)

# Permission each admin route enforces server-side (see
# ``routes._require_admin_permission_for``).
_ROUTE_PERMISSIONS: Dict[str, str] = {
    "config.admin_api_tokens": TOKENS_READ_PERMISSION,
    "config.service_account_create": SERVICE_ACCOUNTS_WRITE_PERMISSION,
    "config.service_account_token_create": TOKENS_ADMIN_PERMISSION,
    "config.admin_api_token_revoke": TOKENS_ADMIN_PERMISSION,
}

# Lifetimes offered by the create forms, in days.
_LIFETIME_CHOICES_DAYS = (7, 30, 90, 180, 366)


# ---------------------------------------------------------------------------
# Lazy-import service seams (test-patchable)
# ---------------------------------------------------------------------------


def _service_module() -> Any:
    """
        Import the API-token service lazily so the page module stays
        importable without the service's dependencies and tests can
        patch the seams below.

        :returns: The :mod:`security.auth.api_tokens.service` module.
    """
    from ccai.pychestrate.webservice.security.auth.api_tokens import (  # noqa: E402
        service as token_service,
    )
    rtnval = token_service
    return rtnval


def _list_tokens(*, db_session: Any, user_id: Optional[str]) -> List[Any]:
    """
        List tokens (one user's, or everyone's for ``None``).

        :param db_session: Open SQLAlchemy session.
        :param user_id: Owner filter or ``None``.

        :returns: List of token views.
    """
    rtnval = _service_module().list_api_tokens(db_session=db_session, user_id=user_id)
    return rtnval


def _list_service_accounts(*, db_session: Any) -> List[Any]:
    """
        List service accounts.

        :param db_session: Open SQLAlchemy session.

        :returns: List of service-account views.
    """
    rtnval = _service_module().list_service_accounts(db_session=db_session)
    return rtnval


def _create_token(
        *,
        db_session: Any,
        user_id: str,
        name: str,
        lifetime_days: Any,
        scope: Any,
        actor_user_id: str
    ) -> Any:
    """
        Issue a token.

        :param db_session: Open SQLAlchemy session.
        :param user_id: The user the token acts as.
        :param name: Token label.
        :param lifetime_days: Days until expiry.
        :param scope: Token scope.
        :param actor_user_id: Who is issuing it.

        :returns: The issued token.
    """
    rtnval = _service_module().create_api_token(
        db_session=db_session,
        user_id=user_id,
        name=name,
        lifetime_days=lifetime_days,
        scope=scope,
        actor_user_id=actor_user_id,
    )
    return rtnval


def _revoke_token(
        *,
        db_session: Any,
        token_id: str,
        actor_user_id: str,
        owner_user_id: Optional[str]
    ) -> Any:
    """
        Revoke a token.

        :param db_session: Open SQLAlchemy session.
        :param token_id: Token id.
        :param actor_user_id: Who is revoking it.
        :param owner_user_id: Required owner (self-service) or ``None``.

        :returns: The revoked token's view.
    """
    rtnval = _service_module().revoke_api_token(
        db_session=db_session,
        token_id=token_id,
        actor_user_id=actor_user_id,
        owner_user_id=owner_user_id,
    )
    return rtnval


def _create_service_account(
        *,
        db_session: Any,
        login_name: str,
        display_name: str,
        actor_user_id: str
    ) -> Any:
    """
        Create a service account.

        :param db_session: Open SQLAlchemy session.
        :param login_name: Login name.
        :param display_name: Display name.
        :param actor_user_id: Who is creating it.

        :returns: The new identity user.
    """
    rtnval = _service_module().create_service_account(
        db_session=db_session,
        login_name=login_name,
        display_name=display_name,
        actor_user_id=actor_user_id,
    )
    return rtnval


def _read_service_account(*, db_session: Any, user_id: str) -> Any:
    """
        Load a service account.

        :param db_session: Open SQLAlchemy session.
        :param user_id: Identity user id.

        :returns: The identity user.
    """
    rtnval = _service_module().read_service_account(db_session=db_session, user_id=user_id)
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _resolve_service_base_url(*, request: Request) -> str:
    """
        This service's browser-facing base URL (scheme + authority),
        for the copy-paste ``pyc login --server-url`` command. Prefers
        the ``Host`` header the browser used.

        :param request: Incoming webworks request.

        :returns: Base URL, e.g. ``https://pyc.example:8443``.
    """
    scheme = getattr(request, "scheme", None)
    if isinstance(scheme, str) is False or len(scheme) == 0:
        scheme = "http"

    host_header = None
    headers = getattr(request, "headers", None)
    if headers is not None:
        try:
            host_header = headers.get("host", None)
        except Exception:
            host_header = None
    if host_header is not None and len(str(host_header)) > 0:
        rtnval = "{}://{}".format(scheme, host_header)
        return rtnval

    host = getattr(request, "host", None)
    if isinstance(host, str) is True and len(host) > 0:
        port = getattr(request, "port", None)
        if isinstance(port, int) is True and port not in (0, 80, 443):
            rtnval = "{}://{}:{}".format(scheme, host, port)
            return rtnval
        rtnval = "{}://{}".format(scheme, host)
        return rtnval

    rtnval = "{}://<service-host>".format(scheme)
    return rtnval


def _is_validation_error(exc: Exception) -> bool:
    """
        Whether ``exc`` carries a message curated for the user (the
        service's validation errors are ``ValueError`` subclasses).

        :param exc: Raised exception.

        :returns: Boolean.
    """
    rtnval = isinstance(exc, ValueError)
    return rtnval


def _describe_failure(*, exc: Exception, action: str) -> str:
    """
        Operator-facing message for a failed action. Validation
        messages are shown verbatim; anything else is logged with its
        traceback and replaced by a generic message.

        :param exc: Raised exception.
        :param action: Present-participle label, e.g. ``"creating the token"``.

        :returns: Flash message.
    """
    if _is_validation_error(exc) is True:
        rtnval = str(exc)
        return rtnval
    _module_logger.exception("Unexpected %s while %s.", type(exc).__name__, action)
    rtnval = (
        "Error {}: an unexpected internal error occurred. The details have been logged."
    ).format(action)
    return rtnval


def _close_quietly(db_session: Any) -> None:
    """
        Close a db session, ignoring close failures.

        :param db_session: Session or ``None``.

        :returns: None.
    """
    if db_session is None:
        return
    try:
        db_session.close()
    except Exception:
        pass
    return


def _csrf_redirect(*, auth: Any, form: Dict[str, Any], fallback_endpoint: str) -> Optional[Response]:
    """
        Enforce the CSRF token on a POST form.

        :param auth: Auth resolution.
        :param form: Parsed form.
        :param fallback_endpoint: Where to send a request that fails.

        :returns: Redirect on failure, ``None`` when the token matched.
    """
    redirect = auth_guard.enforce_csrf_or_redirect(
        form=form,
        session=auth.session,
        fallback_url=_url_for_module.url_for(fallback_endpoint),
    )
    if redirect is not None:
        _attach_session_to_response(response=redirect, session=auth.session)
    return redirect


def _base_context(*, auth: Any, request_endpoint: str) -> Dict[str, Any]:
    """
        Template context shared by both pages.

        :param auth: Auth resolution.
        :param request_endpoint: Endpoint name of the page.

        :returns: Context dict.
    """
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint=request_endpoint,
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["lifetime_choices"] = _LIFETIME_CHOICES_DAYS
    context["default_lifetime_days"] = 90
    rtnval = context
    return rtnval


def _minted_panel(*, request: Request, issued: Any, owner_label: str) -> Dict[str, Any]:
    """
        The one-time panel shown after a token is issued.

        :param request: Incoming webworks request.
        :param issued: The issued token.
        :param owner_label: Whose token it is, for the heading.

        :returns: Template dict.
    """
    base_url = _resolve_service_base_url(request=request)
    rtnval = {
        "token": issued.token,
        "name": issued.view.name,
        "owner_label": owner_label,
        "scope": issued.view.scope,
        "expires_at": issued.view.expires_at,
        "login_command": "pyc login --server-url {}".format(base_url),
        "curl_command": 'curl -H "Authorization: Bearer $PYC_TOKEN" {}/api/v1/me'.format(base_url),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Account pages
# ---------------------------------------------------------------------------


def _render_account_page(*, request: Request, auth: Any, minted: Optional[Dict[str, Any]] = None) -> Response:
    """
        Render ``/account/api-tokens``.

        :param request: Incoming webworks request.
        :param auth: Auth resolution (open db session).
        :param minted: One-time panel data, or ``None``.

        :returns: HTML response.
    """
    context = _base_context(auth=auth, request_endpoint="config.account_api_tokens")
    context["tokens"] = _list_tokens(db_session=auth.db_session, user_id=str(auth.user_id))
    context["minted"] = minted
    context["can_view_admin_tokens"] = _has_permission(auth=auth, permission=TOKENS_READ_PERMISSION)
    response = _render(template_name="config/tokens/account.html", context=context)
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_account_tokens(request: Request) -> Response:
    """
        ``GET /account/api-tokens`` -- the signed-in user's tokens.

        :param request: Incoming webworks request.

        :returns: HTML page or a sign-in redirect.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    try:
        rtnval = _render_account_page(request=request, auth=auth)
        return rtnval
    finally:
        _close_quietly(auth.db_session)


def handle_account_token_create(request: Request) -> Response:
    """
        ``POST /account/api-tokens/create`` -- issue a token for the
        signed-in user and show its secret once.

        :param request: Incoming webworks request.

        :returns: HTML page with the one-time panel, or a redirect with
                  an error flash.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    try:
        form = _parse_form_or_empty(request=request)
        csrf_redirect = _csrf_redirect(auth=auth, form=form, fallback_endpoint="config.account_api_tokens")
        if csrf_redirect is not None:
            return csrf_redirect

        try:
            issued = _create_token(
                db_session=auth.db_session,
                user_id=str(auth.user_id),
                name=str(form.get("name", "")),
                lifetime_days=form.get("expires_in_days", None),
                scope=form.get("scope", None),
                actor_user_id=str(auth.user_id),
            )
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.account_api_tokens"),
                message=_describe_failure(exc=exc, action="creating the token"),
                category=flash.CATEGORY_ERROR,
            )
            return response

        minted = _minted_panel(request=request, issued=issued, owner_label=str(auth.username))
        rtnval = _render_account_page(request=request, auth=auth, minted=minted)
        return rtnval
    finally:
        _close_quietly(auth.db_session)


def handle_account_token_revoke(request: Request) -> Response:
    """
        ``POST /account/api-tokens/{token_id}/revoke`` -- revoke one of
        the signed-in user's tokens.

        :param request: Incoming webworks request.

        :returns: Redirect to the list with a flash.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    try:
        form = _parse_form_or_empty(request=request)
        csrf_redirect = _csrf_redirect(auth=auth, form=form, fallback_endpoint="config.account_api_tokens")
        if csrf_redirect is not None:
            return csrf_redirect

        token_id = str(request.path_params.get("token_id", "") or "").strip()
        try:
            view = _revoke_token(
                db_session=auth.db_session,
                token_id=token_id,
                actor_user_id=str(auth.user_id),
                owner_user_id=str(auth.user_id),
            )
        except LookupError:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.account_api_tokens"),
                message="Token not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.account_api_tokens"),
                message=_describe_failure(exc=exc, action="revoking the token"),
                category=flash.CATEGORY_ERROR,
            )
            return response

        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.account_api_tokens"),
            message="Token '{}' revoked. It no longer authenticates.".format(view.name),
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        _close_quietly(auth.db_session)


# ---------------------------------------------------------------------------
# Admin pages
# ---------------------------------------------------------------------------


def _render_admin_page(
        *,
        request: Request,
        auth: Any,
        minted: Optional[Dict[str, Any]] = None,
        status_code: int = 200
    ) -> Response:
    """
        Render ``/admin/api-tokens``.

        :param request: Incoming webworks request.
        :param auth: Auth resolution (open db session).
        :param minted: One-time panel data, or ``None``.
        :param status_code: HTTP status.

        :returns: HTML response.
    """
    context = _base_context(auth=auth, request_endpoint="config.admin_api_tokens")
    context["service_accounts"] = _list_service_accounts(db_session=auth.db_session)
    context["tokens"] = _list_tokens(db_session=auth.db_session, user_id=None)
    context["minted"] = minted
    context["can_manage_tokens"] = _has_permission(auth=auth, permission=TOKENS_ADMIN_PERMISSION)
    context["can_create_service_accounts"] = _has_permission(
        auth=auth, permission=SERVICE_ACCOUNTS_WRITE_PERMISSION
    )
    response = _render(template_name="config/tokens/admin.html", context=context, status_code=status_code)
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_admin_tokens(request: Request) -> Response:
    """
        ``GET /admin/api-tokens`` -- service accounts and every token.

        :param request: Incoming webworks request.

        :returns: HTML page or a sign-in redirect.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    try:
        rtnval = _render_admin_page(request=request, auth=auth)
        return rtnval
    finally:
        _close_quietly(auth.db_session)


def handle_service_account_create(request: Request) -> Response:
    """
        ``POST /admin/service-accounts/create`` -- create a service
        account.

        :param request: Incoming webworks request.

        :returns: Redirect to the admin page with a flash.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    try:
        form = _parse_form_or_empty(request=request)
        csrf_redirect = _csrf_redirect(auth=auth, form=form, fallback_endpoint="config.admin_api_tokens")
        if csrf_redirect is not None:
            return csrf_redirect

        try:
            user = _create_service_account(
                db_session=auth.db_session,
                login_name=str(form.get("login_name", "")),
                display_name=str(form.get("display_name", "")),
                actor_user_id=str(auth.user_id),
            )
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.admin_api_tokens"),
                message=_describe_failure(exc=exc, action="creating the service account"),
                category=flash.CATEGORY_ERROR,
            )
            return response

        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.admin_api_tokens"),
            message=(
                "Service account '{}' created. Give it roles on the Users page,"
                " then issue it a token."
            ).format(user.login_name),
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        _close_quietly(auth.db_session)


def handle_service_account_token_create(request: Request) -> Response:
    """
        ``POST /admin/service-accounts/{user_id}/api-tokens/create`` --
        issue a token for a service account and show its secret once.

        :param request: Incoming webworks request.

        :returns: HTML page with the one-time panel, or a redirect with
                  an error flash.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    try:
        form = _parse_form_or_empty(request=request)
        csrf_redirect = _csrf_redirect(auth=auth, form=form, fallback_endpoint="config.admin_api_tokens")
        if csrf_redirect is not None:
            return csrf_redirect

        user_id = str(request.path_params.get("user_id", "") or "").strip()
        try:
            account = _read_service_account(db_session=auth.db_session, user_id=user_id)
            issued = _create_token(
                db_session=auth.db_session,
                user_id=str(account.user_id),
                name=str(form.get("name", "")),
                lifetime_days=form.get("expires_in_days", None),
                scope=form.get("scope", None),
                actor_user_id=str(auth.user_id),
            )
        except LookupError:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.admin_api_tokens"),
                message="Service account not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.admin_api_tokens"),
                message=_describe_failure(exc=exc, action="creating the token"),
                category=flash.CATEGORY_ERROR,
            )
            return response

        minted = _minted_panel(request=request, issued=issued, owner_label=account.login_name)
        rtnval = _render_admin_page(request=request, auth=auth, minted=minted)
        return rtnval
    finally:
        _close_quietly(auth.db_session)


def handle_admin_token_revoke(request: Request) -> Response:
    """
        ``POST /admin/api-tokens/{token_id}/revoke`` -- revoke any
        token.

        :param request: Incoming webworks request.

        :returns: Redirect to the admin page with a flash.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    try:
        form = _parse_form_or_empty(request=request)
        csrf_redirect = _csrf_redirect(auth=auth, form=form, fallback_endpoint="config.admin_api_tokens")
        if csrf_redirect is not None:
            return csrf_redirect

        token_id = str(request.path_params.get("token_id", "") or "").strip()
        try:
            view = _revoke_token(
                db_session=auth.db_session,
                token_id=token_id,
                actor_user_id=str(auth.user_id),
                owner_user_id=None,
            )
        except LookupError:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.admin_api_tokens"),
                message="Token not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.admin_api_tokens"),
                message=_describe_failure(exc=exc, action="revoking the token"),
                category=flash.CATEGORY_ERROR,
            )
            return response

        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.admin_api_tokens"),
            message="Token '{}' of {} revoked.".format(view.name, view.login_name),
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        _close_quietly(auth.db_session)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "config.account_api_tokens": handle_account_tokens,
    "config.account_api_token_create": handle_account_token_create,
    "config.account_api_token_revoke": handle_account_token_revoke,
    "config.admin_api_tokens": handle_admin_tokens,
    "config.service_account_create": handle_service_account_create,
    "config.service_account_token_create": handle_service_account_token_create,
    "config.admin_api_token_revoke": handle_admin_token_revoke,
}


def register_tokens_routes(*, app: Any) -> None:
    """
        Attach the API-token and service-account pages and register
        their endpoint names with the url_for shim. Account pages need
        only a signed-in session (a user manages their own tokens);
        admin pages are gated by :data:`_ROUTE_PERMISSIONS`.

        :param app: WebWorks application.

        :returns: None.
    """
    for endpoint_name, full_path, methods in _ACCOUNT_ROUTE_TABLE:
        _url_for_module.register_endpoint(endpoint=endpoint_name, pattern=full_path)
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(_wrap_admin_handler_in_shell(handler))

    for endpoint_name, full_path, methods in _ADMIN_ROUTE_TABLE:
        _url_for_module.register_endpoint(endpoint=endpoint_name, pattern=full_path)
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _require_admin_permission_for(
            _wrap_admin_handler_in_shell(handler),
            permission=_ROUTE_PERMISSIONS[endpoint_name],
        )
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "ACCOUNT_PATH",
    "handle_account_token_create",
    "handle_account_token_revoke",
    "handle_account_tokens",
    "handle_admin_token_revoke",
    "handle_admin_tokens",
    "handle_service_account_create",
    "handle_service_account_token_create",
    "register_tokens_routes",
]
