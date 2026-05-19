"""
.. module:: webinterface.blueprints.config.routes_scopes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/scopes
               (D3 slice -- secret scope management).

.. moduleauthor:: Automation Mojo LLC

The three secret-scope routes ported from the legacy flask
``config_blueprint``:

* ``GET  /config/scopes``                       -- list.
* ``GET  /config/scopes/create``                -- create form.
* ``POST /config/scopes/create``                -- create scope.
* ``POST /config/scopes/{scope_id}/delete``     -- delete.

The :class:`SecretManager` constructor takes a SQLAlchemy
session AND an encryption-key bytes parameter. The legacy flask
code read the key from ``$SECRET_ENCRYPTION_KEY`` falling back
to a hard-coded dev value -- that pattern is preserved here in
:func:`_resolve_secret_encryption_key` so behavior matches the
flask-era setup. PR D4 (secrets ports) will replace this with a
KEK-derived key alongside the rest of the secret-management
port.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Callable, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from automojo.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    url_for as _url_for_module,
)
from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    MultiFormView,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
    _wrap_admin_handler_in_shell,
)


_ROUTE_TABLE = (
    ("config.scope_list", "/scopes", ("GET",)),
    ("config.scope_create", "/scopes/create", ("GET", "POST")),
    ("config.scope_delete", "/scopes/{scope_id}/delete", ("POST",)),
)


_SECRET_ENCRYPTION_KEY_ENV_VAR: str = "SECRET_ENCRYPTION_KEY"
_SECRET_ENCRYPTION_KEY_DEFAULT: str = "default-key-for-dev"


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _resolve_secret_encryption_key() -> bytes:
    """
        Return the encryption-key bytes the SecretManager
        constructor expects. Mirrors the legacy flask handler's
        ``os.environ.get('SECRET_ENCRYPTION_KEY',
        'default-key-for-dev').encode()`` pattern.

        Test seam: tests patch this helper to bypass the env-var
        read.
    """
    raw = os.environ.get(
        _SECRET_ENCRYPTION_KEY_ENV_VAR,
        _SECRET_ENCRYPTION_KEY_DEFAULT,
    )
    rtnval = raw.encode("utf-8")
    return rtnval


def _build_secret_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`SecretManager` against the supplied
        session and the resolved encryption key.

        :param db_session: Open SQLAlchemy session.

        :returns: SecretManager instance.
    """
    from automojo.pychestrate.core.managers.secret_manager import (  # noqa: E402
        SecretManager,
    )
    encryption_key = _resolve_secret_encryption_key()
    rtnval = SecretManager(db_session, encryption_key)
    return rtnval


def _build_scope_create_request(
        *, name: str, description: str
    ) -> Any:
    """
        Construct a :class:`SecretScopeCreateRequest`.
    """
    from automojo.pychestrate.core.managers.secret_manager import (  # noqa: E402
        SecretScopeCreateRequest,
    )
    rtnval = SecretScopeCreateRequest(
        name=name, description=description
    )
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 20
    ) -> Dict[str, Any]:
    raw_page = request.query_params.get("page", "1") or "1"
    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1

    raw_per_page = (
        request.query_params.get("per_page", str(default_per_page))
        or str(default_per_page)
    )
    try:
        per_page = int(raw_per_page)
    except (TypeError, ValueError):
        per_page = default_per_page
    if per_page < 1:
        per_page = default_per_page

    rtnval = {"page": page, "per_page": per_page}
    return rtnval


def _coerce_scope_id(*, raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        return None
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_scope_list(request: Request) -> Response:
    """
        ``GET /config/scopes`` -- paginated scope list.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        secret_manager = _build_secret_manager(db_session=db_session)
        scopes = secret_manager.list_scopes(
            auth.user_id,
            offset=offset,
            limit=params["per_page"],
        ).scopes

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.scope_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["scopes"] = scopes
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        response = _render(
            template_name="config/secrets/scope_list.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_scope_create(request: Request) -> Response:
    """
        ``GET /config/scopes/create`` / ``POST /config/scopes/create``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        method = request.method.upper()

        if method == "GET":
            flashes = flash.consume_flashes(session=auth.session)
            context = _build_default_template_context(
                session=auth.session,
                request_endpoint="config.scope_create",
                flashes=flashes,
                csrf_token=auth.csrf_token,
            )
            context["form_data"] = None
            response = _render(
                template_name="config/secrets/scope_create.html",
                context=context,
            )
            _attach_session_to_response(
                response=response, session=auth.session
            )
            return response

        # POST
        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        form_view = MultiFormView(data=multi_form)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.scope_create"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        description = str(single_form.get("description", "")).strip()

        secret_manager = _build_secret_manager(db_session=db_session)

        try:
            create_request = _build_scope_create_request(
                name=name, description=description
            )
            secret_manager.create_scope(create_request, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.scope_list"),
                message='Scope "{}" created successfully.'.format(name),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error creating scope: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )

        # Re-render the form with the submitted values + flash.
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.scope_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["form_data"] = form_view
        response = _render(
            template_name="config/secrets/scope_create.html",
            context=context,
            status_code=400,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_scope_delete(request: Request) -> Response:
    """
        ``POST /config/scopes/{scope_id}/delete``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        scope_id = _coerce_scope_id(
            raw=request.path_params.get("scope_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.scope_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if scope_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.scope_list"),
                message="Scope not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        secret_manager = _build_secret_manager(db_session=db_session)

        try:
            secret_manager.delete_scope(scope_id, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.scope_list"),
                message="Scope deleted successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.scope_list"),
                message="Error deleting scope: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "config.scope_list": handle_scope_list,
    "config.scope_create": handle_scope_create,
    "config.scope_delete": handle_scope_delete,
}


def register_scopes_routes(*, app: Any) -> None:
    """
        Attach the scope routes to a webworks app and register
        their endpoint names with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_admin_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_scopes_routes",
    "handle_scope_list",
    "handle_scope_create",
    "handle_scope_delete",
]
