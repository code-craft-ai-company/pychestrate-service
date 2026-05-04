"""
.. module:: webinterface.blueprints.config.routes_variables
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/variables
               (D3 slice -- global-variable management).

.. moduleauthor:: Automation Mojo LLC

The six global-variable routes ported from the legacy flask
``config_blueprint``:

* ``GET  /config/variables``                  -- paginated list +
                                                 ?search= filter.
* ``GET  /config/variables/create``           -- create form.
* ``POST /config/variables/create``           -- create variable.
* ``GET  /config/variables/{name}``           -- detail.
* ``GET  /config/variables/{name}/edit``      -- edit form.
* ``POST /config/variables/{name}/edit``      -- update.
* ``POST /config/variables/{name}/delete``    -- delete.
* ``GET  /config/variables/{name}/history``   -- change history.

Variable values are typed via the :class:`VariableType` enum
(``string`` / ``integer`` / ``float`` / ``boolean`` / ``json``).
The form's raw ``value`` string is parsed via
:meth:`GlobalVariableStore.parse_value_from_string` -- which the
manager owns and the routes module just dispatches to.
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


_ROUTE_TABLE = (
    ("config.variable_list", "/variables", ("GET",)),
    ("config.variable_create", "/variables/create", ("GET", "POST")),
    ("config.variable_detail", "/variables/{name}", ("GET",)),
    ("config.variable_edit", "/variables/{name}/edit", ("GET", "POST")),
    ("config.variable_delete", "/variables/{name}/delete", ("POST",)),
    ("config.variable_history", "/variables/{name}/history", ("GET",)),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _build_variable_store(*, db_session: Any) -> Any:
    """
        Construct a :class:`GlobalVariableStore`. Lazy-import.

        :param db_session: Open SQLAlchemy session.

        :returns: GlobalVariableStore instance.
    """
    from automojo.pychestrate.core.managers.global_variable_store import (  # noqa: E402
        GlobalVariableStore,
    )
    rtnval = GlobalVariableStore(db_session)
    return rtnval


def _resolve_variable_type(*, var_type_str: str) -> Any:
    """
        Resolve a string like ``"string"`` / ``"integer"`` etc.
        to the manager's :class:`VariableType` enum value. Raises
        ValueError on unknown.

        :param var_type_str: Submitted ``var_type`` form field.

        :returns: VariableType enum value.
        :raises: ValueError on unknown type.
    """
    from automojo.pychestrate.core.managers.global_variable_store import (  # noqa: E402
        VariableType,
    )
    rtnval = VariableType(var_type_str)
    return rtnval


def _build_variable_create_request(
        *,
        name: str,
        value: Any,
        var_type: Any,
        description: str,
        default_value: Any
    ) -> Any:
    """
        Construct a :class:`GlobalVariableCreateRequest`. Lazy-import.
    """
    from automojo.pychestrate.core.managers.global_variable_store import (  # noqa: E402
        GlobalVariableCreateRequest,
    )
    rtnval = GlobalVariableCreateRequest(
        name=name,
        value=value,
        var_type=var_type,
        description=description,
        default_value=default_value,
    )
    return rtnval


def _build_variable_update_request(
        *,
        value: Any,
        description: Optional[str]
    ) -> Any:
    """
        Construct a :class:`GlobalVariableUpdateRequest`. Lazy-import.
    """
    from automojo.pychestrate.core.managers.global_variable_store import (  # noqa: E402
        GlobalVariableUpdateRequest,
    )
    rtnval = GlobalVariableUpdateRequest(
        value=value,
        description=description,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 20
    ) -> Dict[str, Any]:
    """
        Pull ``page`` / ``per_page`` / ``search`` from the query
        string. Same defaults as the user-list handler so list
        templates render consistently.
    """
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

    search = request.query_params.get("search", "") or ""

    rtnval = {"page": page, "per_page": per_page, "search": search}
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_variable_list(request: Request) -> Response:
    """
        ``GET /config/variables`` -- paginated list.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        search = params["search"]
        if len(search) == 0:
            search_arg: Optional[str] = None
        else:
            search_arg = search

        variable_store = _build_variable_store(db_session=db_session)
        result = variable_store.list_variables(
            offset=offset,
            limit=params["per_page"],
            search=search_arg,
        )

        total = result.total
        per_page = params["per_page"]
        total_pages = (total + per_page - 1) // per_page

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.variable_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["variables"] = result.variables
        context["total"] = total
        context["page"] = params["page"]
        context["per_page"] = per_page
        context["total_pages"] = total_pages
        context["search"] = search

        response = _render(
            template_name="config/variables/list.html",
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


def handle_variable_create(request: Request) -> Response:
    """
        ``GET /config/variables/create`` / ``POST /config/variables/create``.
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
                request_endpoint="config.variable_create",
                flashes=flashes,
                csrf_token=auth.csrf_token,
            )
            context["form_data"] = None
            response = _render(
                template_name="config/variables/create.html",
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
            fallback_url=_url_for_module.url_for(
                "config.variable_create"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        value_raw = str(single_form.get("value", ""))
        var_type_str = str(single_form.get("var_type", "string"))
        description = str(single_form.get("description", "")).strip()
        default_value_raw = str(single_form.get("default_value", ""))

        variable_store = _build_variable_store(db_session=db_session)

        try:
            var_type = _resolve_variable_type(var_type_str=var_type_str)
            parsed_value = variable_store.parse_value_from_string(
                value_raw, var_type
            )
            if len(default_value_raw) > 0:
                parsed_default = variable_store.parse_value_from_string(
                    default_value_raw, var_type
                )
            else:
                parsed_default = None

            create_request = _build_variable_create_request(
                name=name,
                value=parsed_value,
                var_type=var_type,
                description=description,
                default_value=parsed_default,
            )
            variable_store.create_variable(create_request, auth.user_id)

            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message='Variable "{}" created successfully.'.format(name),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except ValueError as exc:
            flash.add_flash(
                session=auth.session,
                message="Invalid value: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error creating variable: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )

        # Re-render the form with the submitted values + flash.
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.variable_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["form_data"] = form_view
        response = _render(
            template_name="config/variables/create.html",
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


def handle_variable_detail(request: Request) -> Response:
    """
        ``GET /config/variables/{name}`` -- detail page.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        name = str(request.path_params.get("name", ""))
        variable_store = _build_variable_store(db_session=db_session)
        variable = variable_store.get_variable(name)

        if variable is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message="Variable not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.variable_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["variable"] = variable
        response = _render(
            template_name="config/variables/detail.html",
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


def handle_variable_edit(request: Request) -> Response:
    """
        ``GET /config/variables/{name}/edit`` /
        ``POST /config/variables/{name}/edit``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        name = str(request.path_params.get("name", ""))
        variable_store = _build_variable_store(db_session=db_session)
        method = request.method.upper()

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "config.variable_edit", name=name
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            value_raw = str(single_form.get("value", ""))
            description = str(single_form.get("description", "")).strip()

            variable = variable_store.get_variable(name)
            if variable is None:
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for("config.variable_list"),
                    message="Variable not found.",
                    category=flash.CATEGORY_ERROR,
                )
                return response

            try:
                parsed_value = variable_store.parse_value_from_string(
                    value_raw, variable.var_type
                )
                update_request = _build_variable_update_request(
                    value=parsed_value,
                    description=(
                        description if len(description) > 0 else None
                    ),
                )
                variable_store.update_variable(
                    name, update_request, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "config.variable_detail", name=name
                    ),
                    message="Variable updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except ValueError as exc:
                flash.add_flash(
                    session=auth.session,
                    message="Invalid value: {}".format(str(exc)),
                    category=flash.CATEGORY_ERROR,
                )
            except Exception as exc:
                flash.add_flash(
                    session=auth.session,
                    message="Error updating variable: {}".format(str(exc)),
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through.
        variable = variable_store.get_variable(name)
        if variable is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message="Variable not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.variable_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["variable"] = variable
        response = _render(
            template_name="config/variables/edit.html",
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


def handle_variable_delete(request: Request) -> Response:
    """
        ``POST /config/variables/{name}/delete`` -- delete the
        variable, redirect to the list with a success / error
        flash.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        name = str(request.path_params.get("name", ""))
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.variable_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        variable_store = _build_variable_store(db_session=db_session)

        try:
            variable_store.delete_variable(name, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message='Variable "{}" deleted successfully.'.format(name),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message="Error deleting variable: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_variable_history(request: Request) -> Response:
    """
        ``GET /config/variables/{name}/history`` -- change history.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        name = str(request.path_params.get("name", ""))
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        variable_store = _build_variable_store(db_session=db_session)
        variable = variable_store.get_variable(name)
        if variable is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message="Variable not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        history = variable_store.get_change_history(
            name, offset=offset, limit=params["per_page"]
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.variable_history",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["variable"] = variable
        context["history"] = history
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        response = _render(
            template_name="config/variables/history.html",
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


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "config.variable_list": handle_variable_list,
    "config.variable_create": handle_variable_create,
    "config.variable_detail": handle_variable_detail,
    "config.variable_edit": handle_variable_edit,
    "config.variable_delete": handle_variable_delete,
    "config.variable_history": handle_variable_history,
}


def register_variables_routes(*, app: Any) -> None:
    """
        Attach the variables routes to a webworks app and
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
    "register_variables_routes",
    "handle_variable_list",
    "handle_variable_create",
    "handle_variable_detail",
    "handle_variable_edit",
    "handle_variable_delete",
    "handle_variable_history",
]
