"""
.. module:: webinterface.blueprints.config.routes_secrets
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/secrets
               (D4 slice -- secret management).

.. moduleauthor:: Code Craft AI LLC

The secret-management routes served under the config blueprint:

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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

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
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_scopes import (
    _resolve_secret_encryption_key,
)


_module_logger = logging.getLogger(__name__)


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

# Permission each route enforces server-side (see
# ``routes._require_admin_permission_for``). Legacy secrets.
_ROUTE_PERMISSIONS = {
    "config.secret_list": "system:secrets.read",
    "config.secret_create": "system:secrets.write",
    "config.secret_edit": "system:secrets.write",
    "config.secret_delete": "system:secrets.write",
}


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
    from ccai.pychestrate.core.managers.secret_manager import (  # noqa: E402
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
    from ccai.pychestrate.core.orm import SecretType  # noqa: E402
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
    from ccai.pychestrate.core.managers.secret_manager import (  # noqa: E402
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
    from ccai.pychestrate.core.managers.secret_manager import (  # noqa: E402
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


def _resolve_surfaceable_error_types() -> Tuple[type, ...]:
    """
        Return the exception types whose messages are curated,
        operator-facing text safe to surface in a flash:
        :class:`SecretManagerError` (and subclasses) plus
        :class:`ValueError` (bad enum values / validation).
        Lazy-imports so this module stays importable without the
        secret-manager dependency set.

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


#: Visible labels of the secret form fields, for the error summary.
SECRET_FIELD_LABELS: Dict[str, str] = {
    "scope_id": "Scope",
    "name": "Secret Name",
    "secret_type": "Type",
    "value": "Value",
    "description": "Description",
}

#: The input each secret manager error is about, by error class name.
#: The manager's errors carry no field; their type says which input to
#: change.
_SECRET_ERROR_FIELDS: Dict[str, str] = {
    "DuplicateSecretError": "name",
    "ScopeNotFoundError": "scope_id",
    "ScopeAccessDeniedError": "scope_id",
}


def _secret_field_errors(*, exc: BaseException) -> Dict[str, str]:
    """
        The ``{field: message}`` for a refused secret form, or an empty
        dict when the error is about no single input (the caller then
        flashes it). Only the manager's curated errors are shown; their
        text was written for people.

        :param exc: The error the operation raised.

        :returns: One entry, or an empty dict.
    """
    field = _SECRET_ERROR_FIELDS.get(type(exc).__name__, None)
    rtnval: Dict[str, str] = {}
    if field is not None and isinstance(exc, _resolve_surfaceable_error_types()) is True:
        rtnval = {field: str(exc)}
    return rtnval


def _describe_secret_failure(*, exc: Exception, action: str) -> str:
    """
        Build the operator-facing flash message for a failed
        secret operation. Curated manager / validation errors are
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
        rtnval = "Error {} secret: {}".format(action, str(exc))
        return rtnval

    _module_logger.exception(
        "Unexpected error while %s secret.", action
    )
    rtnval = (
        "Error {} secret: an unexpected internal error occurred."
        " The details have been logged."
    ).format(action)
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
        list_response = secret_manager.list_secrets(
            scope_id=scope_id,
            user_id=auth.user_id,
            offset=offset,
            limit=params["per_page"],
        )
        secrets = list_response.secrets
        total = list_response.total
        total_pages = (total + params["per_page"] - 1) // params["per_page"]
        scopes = secret_manager.list_scopes(auth.user_id).scopes

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
        context["total"] = total
        context["total_pages"] = total_pages
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


#: Form fields whose submitted value is never rendered back into a page.
_SECRET_VALUE_FIELDS = ("value",)


def _form_data_without_secret_value(
        *, multi_form: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:
    """
        Copy of the submitted form without the secret value, for
        re-rendering the create form after a failure. The value is
        the one field that must not come back in the HTML (audit
        ADM-31: a duplicate name echoed the value into
        ``value="..."``); the user re-enters it.

        :param multi_form: Parsed form (field -> values).

        :returns: The same mapping minus :data:`_SECRET_VALUE_FIELDS`.
    """
    rtnval: Dict[str, List[str]] = {}
    for field_name, values in multi_form.items():
        if field_name in _SECRET_VALUE_FIELDS:
            continue
        rtnval[field_name] = values
    return rtnval


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
            scopes = secret_manager.list_scopes(auth.user_id).scopes
            flashes = flash.consume_flashes(session=auth.session)
            context = _build_default_template_context(
                session=auth.session,
                request_endpoint="config.secret_create",
                flashes=flashes,
                csrf_token=auth.csrf_token,
            )
            context["scopes"] = scopes
            context["form_data"] = None
            context["value_cleared"] = False
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
        # A failed create re-renders the form, and the re-render must
        # never carry the secret value back into the page HTML: drop
        # it here so the template cannot echo it.
        form_view = MultiFormView(
            data=_form_data_without_secret_value(multi_form=multi_form)
        )

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
        errors: Dict[str, str] = {}

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
            errors = _secret_field_errors(exc=exc)
            if len(errors) == 0:
                flash.add_flash(
                    session=auth.session,
                    message=_describe_secret_failure(
                        exc=exc, action="creating"
                    ),
                    category=flash.CATEGORY_ERROR,
                )

        # Re-render the form with the submitted values + errors.
        scopes = secret_manager.list_scopes(auth.user_id).scopes
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.secret_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["scopes"] = scopes
        context["form_data"] = form_view
        context["value_cleared"] = len(value) > 0
        context["errors"] = errors
        context["error_labels"] = SECRET_FIELD_LABELS
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
        submitted_description: Optional[str] = None
        status_code = 200

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
            submitted_description = description
            status_code = 400

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
                    message=_describe_secret_failure(
                        exc=exc, action="updating"
                    ),
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
        context["submitted_description"] = submitted_description
        context["errors"] = {}
        context["error_labels"] = SECRET_FIELD_LABELS
        response = _render(
            template_name="config/secrets/edit.html",
            context=context,
            status_code=status_code,
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
                message=_describe_secret_failure(
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
        wrapped_handler = _require_admin_permission_for(
            _wrap_admin_handler_in_shell(handler),
            permission=_ROUTE_PERMISSIONS[endpoint_name],
        )
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_secrets_routes",
    "handle_secret_list",
    "handle_secret_create",
    "handle_secret_edit",
    "handle_secret_delete",
]
