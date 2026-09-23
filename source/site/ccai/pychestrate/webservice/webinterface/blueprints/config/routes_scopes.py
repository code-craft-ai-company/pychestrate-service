"""
.. module:: webinterface.blueprints.config.routes_scopes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/scopes
               (D3 slice -- secret scope management).

.. moduleauthor:: Code Craft AI LLC

The secret-scope routes served under the config blueprint:

* ``GET  /config/scopes``                       -- list.
* ``GET  /config/scopes/create``                -- create form.
* ``POST /config/scopes/create``                -- create scope.
* ``GET  /config/scopes/{scope_id}/edit``       -- edit form.
* ``POST /config/scopes/{scope_id}/edit``       -- update description.
* ``POST /config/scopes/{scope_id}/delete``     -- delete.

The :class:`SecretManager` constructor takes a SQLAlchemy
session AND an encryption-key bytes parameter. The key is read
from ``$SECRET_ENCRYPTION_KEY`` with a hard-coded dev fallback
in :func:`_resolve_secret_encryption_key`. A future secrets
port will replace this with a KEK-derived key alongside the
rest of the secret-management surface.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    MultiFormView,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
    _require_admin_permission_for,
    _wrap_admin_handler_in_shell,
)


_module_logger = logging.getLogger(__name__)


_ROUTE_TABLE = (
    ("config.scope_list", "/scopes", ("GET",)),
    ("config.scope_create", "/scopes/create", ("GET", "POST")),
    ("config.scope_edit", "/scopes/{scope_id}/edit", ("GET", "POST")),
    ("config.scope_delete", "/scopes/{scope_id}/delete", ("POST",)),
)

# Permission each route enforces server-side (see
# ``routes._require_admin_permission_for``). Secret scopes (the navigation gates the page on ``system:secrets.admin``).
_ROUTE_PERMISSIONS = {
    "config.scope_list": "system:secrets.admin",
    "config.scope_create": "system:secrets.admin",
    "config.scope_edit": "system:secrets.admin",
    "config.scope_delete": "system:secrets.admin",
}


_SECRET_ENCRYPTION_KEY_ENV_VAR: str = "SECRET_ENCRYPTION_KEY"
_SECRET_ENCRYPTION_KEY_DEFAULT: str = "default-key-for-dev"
_SECRET_ENCRYPTION_KEY_REQUIRED_BYTES: int = 32
_KEK_FILE_PATH_ENV_VAR: str = "PYCHESTRATE_KEK_FILE_PATH"
_KEK_DERIVATION_SALT: bytes = b"pychestrate/secret-manager/v1"


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _resolve_secret_encryption_key() -> bytes:
    """
        Return the 32-byte encryption key the SecretManager
        constructor expects, resolved in this priority order:

        1. ``SECRET_ENCRYPTION_KEY`` env var when set -- honored
           byte-for-byte if exactly 32 bytes, else SHA-256-derived.
           This is the operator's explicit override.
        2. ``PYCHESTRATE_KEK_FILE_PATH`` env var when set -- the
           KEK file the deploy provisions. SecretManager's
           encryption key is derived from the KEK contents via
           ``SHA-256(salt || kek)`` so a single secret (the KEK)
           drives both the application KEK and SecretManager.
        3. The hard-coded dev fallback, SHA-256-derived.

        The salt domain-separates this derivation from any other
        future use of the KEK (e.g. cookie-secret derivation) so
        compromising one derived secret does not compromise the
        others.

        Test seam: tests patch this helper to bypass the env-var
        / KEK-file read.
    """
    import hashlib
    env_value = os.environ.get(_SECRET_ENCRYPTION_KEY_ENV_VAR)
    if env_value is not None and len(env_value) > 0:
        env_bytes = env_value.encode("utf-8")
        if len(env_bytes) == _SECRET_ENCRYPTION_KEY_REQUIRED_BYTES:
            rtnval = env_bytes
            return rtnval
        rtnval = hashlib.sha256(env_bytes).digest()
        return rtnval

    kek_file_path = os.environ.get(_KEK_FILE_PATH_ENV_VAR)
    if kek_file_path is not None and len(kek_file_path) > 0:
        try:
            with open(kek_file_path, "rb") as kek_file:
                kek_bytes = kek_file.read()
        except OSError:
            kek_bytes = None
        if kek_bytes is not None and len(kek_bytes) > 0:
            rtnval = hashlib.sha256(
                _KEK_DERIVATION_SALT + kek_bytes
            ).digest()
            return rtnval

    fallback_bytes = _SECRET_ENCRYPTION_KEY_DEFAULT.encode("utf-8")
    rtnval = hashlib.sha256(fallback_bytes).digest()
    return rtnval


def _build_secret_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`SecretManager` against the supplied
        session and the resolved encryption key.

        :param db_session: Open SQLAlchemy session.

        :returns: SecretManager instance.
    """
    from ccai.pychestrate.core.managers.secret_manager import (  # noqa: E402
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
    from ccai.pychestrate.core.managers.secret_manager import (  # noqa: E402
        SecretScopeCreateRequest,
    )
    rtnval = SecretScopeCreateRequest(
        name=name, description=description
    )
    return rtnval


def _update_scope_description(
        *, db_session: Any, scope_id: int, description: str
    ) -> None:
    """
        Persist a new description for an existing scope.
        :class:`SecretManager` exposes no scope-update API, so
        this seam updates the ORM row directly (name stays
        immutable). Test-patchable.

        :param db_session: Open SQLAlchemy session.
        :param scope_id: Target scope id.
        :param description: New description text.

        :returns: None.
        :raises: ValueError when the scope does not exist.
    """
    from ccai.pychestrate.core.orm import SecretScope  # noqa: E402

    scope_row = (
        db_session.query(SecretScope)
        .filter(SecretScope.id == scope_id)
        .first()
    )
    if scope_row is None:
        raise ValueError("Scope not found: {}".format(scope_id))

    scope_row.description = description
    db_session.commit()
    return


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


def _resolve_surfaceable_error_types() -> Tuple[type, ...]:
    """
        Return the exception types whose messages are curated,
        operator-facing text safe to surface in a flash:
        :class:`SecretManagerError` (and subclasses) plus
        :class:`ValueError`. Lazy-imports so this module stays
        importable without the secret-manager dependency set.

        :returns: Tuple of exception types.
    """
    try:
        from ccai.pychestrate.core.managers.secret_manager import (  # noqa: E402
            SecretManagerError,
        )
        rtnval: Tuple[type, ...] = (SecretManagerError, ValueError)
    except ImportError:
        rtnval = (ValueError,)
    return rtnval


def _describe_scope_failure(*, exc: Exception, action: str) -> str:
    """
        Build the operator-facing flash message for a failed
        scope operation. Curated manager / validation errors are
        surfaced verbatim; anything else is logged server-side
        (with traceback) and replaced by a generic message so raw
        internal exception text never reaches the browser.

        :param exc: The exception raised by the operation.
        :param action: Present-participle action label (e.g.
                       ``"creating"``) used in the message.

        :returns: Flash message string.
    """
    surfaceable_types = _resolve_surfaceable_error_types()
    if isinstance(exc, surfaceable_types) is True:
        rtnval = "Error {} scope: {}".format(action, str(exc))
        return rtnval

    _module_logger.exception(
        "Unexpected error while %s scope.", action
    )
    rtnval = (
        "Error {} scope: an unexpected internal error occurred."
        " The details have been logged."
    ).format(action)
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
        list_response = secret_manager.list_scopes(
            auth.user_id,
            offset=offset,
            limit=params["per_page"],
        )
        scopes = list_response.scopes
        total = list_response.total
        total_pages = (total + params["per_page"] - 1) // params["per_page"]

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
        context["total"] = total
        context["total_pages"] = total_pages
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
                message=_describe_scope_failure(
                    exc=exc, action="creating"
                ),
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


def handle_scope_edit(request: Request) -> Response:
    """
        ``GET /admin/scopes/{scope_id}/edit`` /
        ``POST /admin/scopes/{scope_id}/edit`` -- edit a scope's
        description. The scope name is immutable (secrets
        reference scopes by name), so the form only offers the
        description.

        :param request: Incoming webworks request.

        :returns: HTMLResponse with the edit form on GET / failed
                  POST, RedirectResponse to the scope list on a
                  successful POST or missing scope.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        scope_id = _coerce_scope_id(
            raw=request.path_params.get("scope_id", None)
        )
        if scope_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.scope_list"),
                message="Scope not found.",
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
                    "config.scope_edit", scope_id=scope_id
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            description = str(
                single_form.get("description", "")
            ).strip()

            try:
                _update_scope_description(
                    db_session=db_session,
                    scope_id=scope_id,
                    description=description,
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for("config.scope_list"),
                    message="Scope updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                flash.add_flash(
                    session=auth.session,
                    message=_describe_scope_failure(
                        exc=exc, action="updating"
                    ),
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through.
        scope = secret_manager.get_scope(scope_id)
        if scope is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.scope_list"),
                message="Scope not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.scope_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["scope"] = scope
        response = _render(
            template_name="config/secrets/scope_edit.html",
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
                message=_describe_scope_failure(
                    exc=exc, action="deleting"
                ),
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
    "config.scope_edit": handle_scope_edit,
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
        wrapped_handler = _require_admin_permission_for(
            _wrap_admin_handler_in_shell(handler),
            permission=_ROUTE_PERMISSIONS[endpoint_name],
        )
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_scopes_routes",
    "handle_scope_list",
    "handle_scope_create",
    "handle_scope_edit",
    "handle_scope_delete",
]
