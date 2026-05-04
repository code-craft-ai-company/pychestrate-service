"""
.. module:: webinterface.blueprints.config.routes_secrets
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/secrets
               (D4 slice -- secret management).

.. moduleauthor:: Automation Mojo LLC

The four secret-management routes ported from the legacy flask
``config_blueprint``:

* ``GET  /config/secrets``                                  -- list +
                                                               scope filter.
* ``GET  /config/secrets/create``                           -- form.
* ``POST /config/secrets/create``                           -- create.
* ``GET  /config/secrets/{scope_id}/{name}/edit``           -- form.
* ``POST /config/secrets/{scope_id}/{name}/edit``           -- update.
* ``POST /config/secrets/{scope_id}/{name}/delete``         -- delete.

The :class:`SecretManager` constructor takes a SQLAlchemy
session AND an encryption-key bytes parameter. This module
delegates secret-key resolution to the same helper
:mod:`webinterface.blueprints.config.routes_scopes` uses, so
secrets and scopes share the operator's configured key.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


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
)
from automojo.pychestrate.webservice.webinterface.blueprints.config.routes_scopes import (
    _resolve_secret_encryption_key,
)


_ROUTE_TABLE = (
    ("config.secret_list", "/secrets", ("GET",)),
    ("config.secret_create", "/secrets/create", ("GET", "POST")),
    (
        "config.secret_edit",
        "/secrets/{scope_id}/{name}/edit",
        ("GET", "POST"),
    ),
    (
        "config.secret_delete",
        "/secrets/{scope_id}/{name}/delete",
        ("POST",),
    ),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams
# ---------------------------------------------------------------------------


def _build_secret_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`SecretManager` against the supplied
        session and the resolved encryption key. Lazy-imports.

        :param db_session: Open SQLAlchemy session.

        :returns: SecretManager instance.
    """
    from automojo.pychestrate.core.managers.secret_manager import (  # noqa: E402
        SecretManager,
    )
    encryption_key = _resolve_secret_encryption_key()
    rtnval = SecretManager(db_session, encryption_key)
    return rtnval


def _resolve_secret_type(*, secret_type_str: str) -> Any:
    """
        Resolve a string like ``"generic"`` / ``"password"`` /
        ``"api_key"`` / ``"certificate"`` / ``"ssh_key"`` to the
        :class:`SecretType` enum value. Raises ValueError on
        unknown.
    """
    from automojo.pychestrate.core.orm import SecretType  # noqa: E402
    rtnval = SecretType(secret_type_str)
    return rtnval


def _build_secret_create_request(
        *,
        name: str,
        value: str,
        secret_type: Any,
        scope_id: int,
        description: str
    ) -> Any:
    """
        Construct a :class:`SecretCreateRequest`. Lazy-imports.
    """
    from automojo.pychestrate.core.managers.secret_manager import (  # noqa: E402
        SecretCreateRequest,
    )
    rtnval = SecretCreateRequest(
        name=name,
        value=value,
        secret_type=secret_type,
        scope_id=scope_id,
        description=description,
    )
    return rtnval


def _build_secret_update_request(
        *,
        value: Optional[str],
        description: Optional[str]
    ) -> Any:
    """
        Construct a :class:`SecretUpdateRequest`. Lazy-imports.
    """
    from automojo.pychestrate.core.managers.secret_manager import (  # noqa: E402
        SecretUpdateRequest,
    )
    rtnval = SecretUpdateRequest(
        value=value, description=description
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


def _coerce_optional_int(*, raw: Any) -> Optional[int]:
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


def handle_secret_list(request: Request) -> Response:
    """
        ``GET /config/secrets`` -- paginated list with optional
        ``?scope_id=`` filter. Only metadata is returned -- the
        encrypted values never leave the SecretManager.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        scope_id = _coerce_optional_int(
            raw=request.query_params.get("scope_id", None)
        )

        secret_manager = _build_secret_manager(db_session=db_session)
        secrets = secret_manager.list_secrets(
            scope_id=scope_id,
            user_id=auth.user_id,
            offset=offset,
            limit=params["per_page"],
        )
        scopes = secret_manager.list_scopes(auth.user_id)

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.secret_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["secrets"] = secrets
        context["scopes"] = scopes
        context["selected_scope_id"] = scope_id
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        response = _render(
            template_name="config/secrets/list.html",
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


def handle_secret_create(request: Request) -> Response:
    """
        ``GET /config/secrets/create`` / ``POST /config/secrets/create``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        method = request.method.upper()
        secret_manager = _build_secret_manager(db_session=db_session)

        if method == "GET":
            scopes = secret_manager.list_scopes(auth.user_id)
            flashes = flash.consume_flashes(session=auth.session)
            context = _build_default_template_context(
                session=auth.session,
                request_endpoint="config.secret_create",
                flashes=flashes,
                csrf_token=auth.csrf_token,
            )
            context["scopes"] = scopes
            context["form_data"] = None
            response = _render(
                template_name="config/secrets/create.html",
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
            fallback_url=_url_for_module.url_for("config.secret_create"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        value = str(single_form.get("value", ""))
        secret_type_str = str(single_form.get("secret_type", "generic"))
        scope_id = _coerce_optional_int(
            raw=single_form.get("scope_id", None)
        )
        description = str(single_form.get("description", "")).strip()

        try:
            secret_type = _resolve_secret_type(
                secret_type_str=secret_type_str
            )
            create_request = _build_secret_create_request(
                name=name,
                value=value,
                secret_type=secret_type,
                scope_id=scope_id if scope_id is not None else 0,
                description=description,
            )
            secret_manager.create_secret(create_request, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.secret_list"),
                message='Secret "{}" created successfully.'.format(name),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error creating secret: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )

        # Re-render the form with the submitted values + flash.
        scopes = secret_manager.list_scopes(auth.user_id)
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.secret_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["scopes"] = scopes
        context["form_data"] = form_view
        response = _render(
            template_name="config/secrets/create.html",
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


def handle_secret_edit(request: Request) -> Response:
    """
        ``GET /config/secrets/{scope_id}/{name}/edit`` /
        ``POST /config/secrets/{scope_id}/{name}/edit``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        scope_id = _coerce_optional_int(
            raw=request.path_params.get("scope_id", None)
        )
        name = str(request.path_params.get("name", ""))

        if scope_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.secret_list"),
                message="Secret not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        secret_manager = _build_secret_manager(db_session=db_session)
        method = request.method.upper()

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "config.secret_edit",
                    scope_id=scope_id,
                    name=name,
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            value = str(single_form.get("value", ""))
            description = str(single_form.get("description", "")).strip()

            try:
                update_request = _build_secret_update_request(
                    value=value if len(value) > 0 else None,
                    description=(
                        description if len(description) > 0 else None
                    ),
                )
                secret_manager.update_secret(
                    name, scope_id, update_request, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for("config.secret_list"),
                    message="Secret updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                flash.add_flash(
                    session=auth.session,
                    message="Error updating secret: {}".format(str(exc)),
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through.
        secret = secret_manager.get_secret_metadata(name, scope_id)
        if secret is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.secret_list"),
                message="Secret not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.secret_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["secret"] = secret
        response = _render(
            template_name="config/secrets/edit.html",
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


def handle_secret_delete(request: Request) -> Response:
    """
        ``POST /config/secrets/{scope_id}/{name}/delete``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        scope_id = _coerce_optional_int(
            raw=request.path_params.get("scope_id", None)
        )
        name = str(request.path_params.get("name", ""))
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.secret_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if scope_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.secret_list"),
                message="Secret not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        secret_manager = _build_secret_manager(db_session=db_session)
        try:
            secret_manager.delete_secret(name, scope_id, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.secret_list"),
                message='Secret "{}" deleted successfully.'.format(name),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.secret_list"),
                message="Error deleting secret: {}".format(str(exc)),
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
    "config.secret_list": handle_secret_list,
    "config.secret_create": handle_secret_create,
    "config.secret_edit": handle_secret_edit,
    "config.secret_delete": handle_secret_delete,
}


def register_secrets_routes(*, app: Any) -> None:
    """
        Attach the secret-management routes to a webworks app and
        register their endpoint names with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(handler)
    return


__all__ = [
    "register_secrets_routes",
    "handle_secret_list",
    "handle_secret_create",
    "handle_secret_edit",
    "handle_secret_delete",
]
