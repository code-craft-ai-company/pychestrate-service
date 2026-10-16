"""
.. module:: webinterface.blueprints.config.routes_variables
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/variables
               (D3 slice -- global-variable management).

.. moduleauthor:: Code Craft AI LLC

The global-variable routes served under the config blueprint:

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
:meth:`SystemVariableStore.parse_value_from_string` -- which the
manager owns and the routes module just dispatches to.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import difflib
import json
import re

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
    form_errors,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.site_shell import ui_profile as _ui_profile
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    MultiFormView,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _not_found_redirect,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
    _require_admin_permission_for,
    _wrap_admin_handler_in_shell,
)


#: Variables the product itself owns, each with the endpoint of the page that manages it and that page's name. They stay on
#: the Variables pages (nothing is hidden) but are read-only there: changing or deleting one changes how the whole
#: interface behaves, and the page that owns it checks what it writes (specs/model-convergence.md, ADM-08).
SYSTEM_OWNED_VARIABLES: Dict[str, Tuple[str, str]] = {
    _ui_profile.DEPLOYMENT_VARIABLE_NAME: ("config.ui_profile", "Interface profile"),
}


def system_owner_of(name: str) -> Optional[Dict[str, str]]:
    """
        The page that manages a product-owned variable.

        :param name: A variable's name.

        :returns: ``{"url", "label"}`` for a variable the product owns, else ``None``.
    """
    owner = SYSTEM_OWNED_VARIABLES.get(name)
    if owner is None:
        return None
    rtnval = {"url": _url_for_module.url_for(owner[0]), "label": owner[1]}
    return rtnval


def system_owned_message(name: str, owner: Dict[str, str]) -> str:
    """
        Why a product-owned variable cannot be changed here.
    """
    rtnval = '"{}" is managed by the product: change it on the {} page ({}).'.format(name, owner["label"], owner["url"])
    return rtnval


_ROUTE_TABLE = (
    ("config.variable_list", "/variables", ("GET",)),
    ("config.variable_create", "/variables/create", ("GET", "POST")),
    ("config.variable_detail", "/variables/{name}", ("GET",)),
    ("config.variable_edit", "/variables/{name}/edit", ("GET", "POST")),
    ("config.variable_delete", "/variables/{name}/delete", ("POST",)),
    ("config.variable_history", "/variables/{name}/history", ("GET",)),
)

# Permission each route enforces server-side (see
# ``routes._require_admin_permission_for``). Global variables. The catalog has no dedicated ``system:variables.*`` key yet, so the page keeps the admin gate the navigation already uses.
_ROUTE_PERMISSIONS = {
    "config.variable_list": "system:ui.admin.view",
    "config.variable_create": "system:ui.admin.view",
    "config.variable_detail": "system:ui.admin.view",
    "config.variable_edit": "system:ui.admin.view",
    "config.variable_delete": "system:ui.admin.view",
    "config.variable_history": "system:ui.admin.view",
}


#: Visible labels of the variable form fields, for the error summary.
VARIABLE_FIELD_LABELS: Dict[str, str] = {
    "name": "Variable Name",
    "var_type": "Type",
    "value": "Value",
    "default_value": "Default Value",
    "description": "Description",
}


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _build_variable_store(*, db_session: Any) -> Any:
    """
        Construct the store the pages use: a :class:`SystemVariableStore`, the legacy store's interface over the SYSTEM-scope variables the
        runtime and ``/api/v1/variables`` read (audit ADM-08). Lazy-import.

        :param db_session: Open SQLAlchemy session.

        :returns: SystemVariableStore instance.
    """
    from ccai.pychestrate.webservice.variables.system_store import (  # noqa: E402
        SystemVariableStore,
    )
    rtnval = SystemVariableStore(db_session)
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
    from ccai.pychestrate.webservice.variables.system_store import (  # noqa: E402
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
        Construct a :class:`SystemVariableCreateRequest`. Lazy-import.
    """
    from ccai.pychestrate.webservice.variables.system_store import (  # noqa: E402
        SystemVariableCreateRequest,
    )
    rtnval = SystemVariableCreateRequest(
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
        Construct a :class:`SystemVariableUpdateRequest`. Lazy-import.
    """
    from ccai.pychestrate.webservice.variables.system_store import (  # noqa: E402
        SystemVariableUpdateRequest,
    )
    rtnval = SystemVariableUpdateRequest(
        value=value,
        description=description,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _variable_type_name(*, var_type: Any) -> str:
    """
        The lower-case type name (``"json"``, ``"boolean"`` ...) of a
        :class:`VariableType` enum member or a plain string.

        :param var_type: VariableType member, string, or None.

        :returns: Type name ("" when unknown).
    """
    if var_type is None:
        return ""
    raw = getattr(var_type, "value", var_type)
    rtnval = str(raw).strip().lower()
    return rtnval


def format_variable_value(*, value: Any, var_type: Any) -> str:
    """
        Render a stored variable value as the text the edit form
        accepts back. The pages used to print the Python object
        (``{'a': 1}``, ``True``), which is not JSON, so saving an
        untouched edit form failed with "Invalid JSON" (audit ADM-09).

        * ``json`` -- ``json.dumps`` with two-space indentation.
        * ``boolean`` -- ``true`` / ``false``.
        * everything else -- ``str(value)``.
        * ``None`` -- an empty string.

        :param value: The deserialized value.
        :param var_type: The variable's :class:`VariableType` (or its
                         name).

        :returns: The canonical text form.
    """
    if value is None:
        return ""

    if var_type is None:
        # A deleted variable's history has no type to go by: show a
        # structure as JSON and a boolean as true / false.
        if isinstance(value, bool) is True:
            var_type = "boolean"
        elif isinstance(value, (dict, list)) is True:
            var_type = "json"

    type_name = _variable_type_name(var_type=var_type)
    if type_name == "json":
        try:
            rtnval = json.dumps(value, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            rtnval = str(value)
        return rtnval

    if type_name == "boolean" and isinstance(value, bool) is True:
        rtnval = "true" if value is True else "false"
        return rtnval

    rtnval = str(value)
    return rtnval


def change_diff_lines(*, old: str, new: str) -> List[Dict[str, str]]:
    """
        What changed between two renderings of a variable's value, line by
        line, for the history page: removed lines, added lines and one line
        of context around them. A one-line value gives its old line and its
        new line.

        :param old: The value before, as the page writes it.
        :param new: The value after.

        :returns: ``[{"kind": "add" | "remove" | "context" | "gap", "text": ...}]``.
    """
    lines: List[Dict[str, str]] = []
    for line in difflib.unified_diff(
            old.splitlines(), new.splitlines(), lineterm="", n=1
        ):
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("@@"):
            lines.append({"kind": "gap", "text": "\u2026"})
        elif line.startswith("+"):
            lines.append({"kind": "add", "text": line[1:]})
        elif line.startswith("-"):
            lines.append({"kind": "remove", "text": line[1:]})
        else:
            lines.append({"kind": "context", "text": line[1:]})
    return lines


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


#: What a variable name may be: a letter, then letters, digits, underscores
#: and periods (the system's own names use periods, ``ui.profile.surfaces``).
VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,127}\Z")
VARIABLE_NAME_RULE = (
    "Use letters, digits, underscores and periods, starting with a letter"
    " (up to 128 characters), for example ui.profile.surfaces."
)


def _variable_field_errors(*, exc: BaseException, default_field: Optional[str] = None) -> Dict[str, str]:
    """
        The ``{field: message}`` for a refused variable form.

        The store's validation, type and duplicate errors are about one
        input: a validation error names it, a type mismatch is about the
        value (or the default value when the message says so), and a
        duplicate is about the name. A ``ValueError`` from parsing the
        typed text is about the input being parsed (``default_field``).
        Anything else has no field and stays a banner.

        :param exc: The error the store or the parser raised.
        :param default_field: The field a ``ValueError`` is about.

        :returns: One entry, or an empty dict.
    """
    from ccai.pychestrate.webservice.variables.system_store import (  # noqa: E402
        DuplicateVariableError,
        TypeValidationError,
        VariableValidationError,
    )

    rtnval: Dict[str, str] = {}
    if isinstance(exc, VariableValidationError) is True:
        rtnval = form_errors.field_errors_from(exc)
    elif isinstance(exc, TypeValidationError) is True:
        message = form_errors.error_message(exc)
        field = "default_value" if message.startswith("Default value") else "value"
        rtnval = {field: message}
    elif isinstance(exc, DuplicateVariableError) is True:
        rtnval = {"name": form_errors.error_message(exc)}
    elif isinstance(exc, ValueError) is True and default_field is not None:
        rtnval = {default_field: form_errors.error_message(exc)}
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
        context["system_owners"] = {variable.name: system_owner_of(variable.name) for variable in result.variables if system_owner_of(variable.name) is not None}
        context["format_value"] = format_variable_value
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
        errors: Dict[str, str] = {}
        parsing_field = "value"

        try:
            if VARIABLE_NAME_PATTERN.match(name) is None:
                from ccai.pychestrate.webservice.variables.system_store import (  # noqa: E402
                    VariableValidationError,
                )
                raise VariableValidationError(VARIABLE_NAME_RULE, field="name")
            reserved_owner = system_owner_of(name)
            if reserved_owner is not None:
                from ccai.pychestrate.webservice.variables.system_store import (  # noqa: E402
                    VariableValidationError,
                )
                raise VariableValidationError(system_owned_message(name, reserved_owner), field="name")
            var_type = _resolve_variable_type(var_type_str=var_type_str)
            parsed_value = variable_store.parse_value_from_string(
                value_raw, var_type
            )
            if len(default_value_raw) > 0:
                parsing_field = "default_value"
                parsed_default = variable_store.parse_value_from_string(
                    default_value_raw, var_type
                )
            else:
                parsed_default = None
            parsing_field = "value"

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
        except Exception as exc:
            errors = _variable_field_errors(exc=exc, default_field=parsing_field)
            if len(errors) == 0:
                flash.add_flash(
                    session=auth.session,
                    message="Error creating variable: {}".format(str(exc)),
                    category=flash.CATEGORY_ERROR,
                )

        # Re-render the form with the submitted values + errors.
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.variable_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["form_data"] = form_view
        context["errors"] = errors
        context["error_labels"] = VARIABLE_FIELD_LABELS
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
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message="Variable not found.",
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
        context["system_owner"] = system_owner_of(variable.name)
        context["format_value"] = format_variable_value
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
        edit_owner = system_owner_of(name)
        if edit_owner is not None:
            return _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_detail", name=name),
                message=system_owned_message(name, edit_owner),
                category=flash.CATEGORY_ERROR,
            )
        variable_store = _build_variable_store(db_session=db_session)
        method = request.method.upper()
        errors: Dict[str, str] = {}
        submitted: Optional[Dict[str, str]] = None
        status_code = 200

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
                response = _not_found_redirect(
                    session=auth.session,
                    url=_url_for_module.url_for("config.variable_list"),
                    message="Variable not found.",
                )
                return response

            submitted = {"value": value_raw, "description": description}
            status_code = 400

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
            except Exception as exc:
                errors = _variable_field_errors(exc=exc, default_field="value")
                if len(errors) == 0:
                    flash.add_flash(
                        session=auth.session,
                        message="Error updating variable: {}".format(str(exc)),
                        category=flash.CATEGORY_ERROR,
                    )

        # GET, or POST that fell through.
        variable = variable_store.get_variable(name)
        if variable is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message="Variable not found.",
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
        context["format_value"] = format_variable_value
        context["submitted"] = submitted
        context["errors"] = errors
        context["error_labels"] = VARIABLE_FIELD_LABELS
        response = _render(
            template_name="config/variables/edit.html",
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

        delete_owner = system_owner_of(name)
        if delete_owner is not None:
            return _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_detail", name=name),
                message=system_owned_message(name, delete_owner),
                category=flash.CATEGORY_ERROR,
            )
        variable_store = _build_variable_store(db_session=db_session)

        try:
            variable_store.delete_variable(name, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message=(
                    'Variable "{}" deleted successfully. Its history is kept:'
                    " open {} to read it."
                ).format(
                    name,
                    _url_for_module.url_for("config.variable_history", name=name),
                ),
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
        history = variable_store.get_change_history(
            name, offset=offset, limit=params["per_page"]
        )
        try:
            history_total = int(variable_store.count_change_history(name))
        except Exception:
            history_total = len(history)
        # The history is kept when a variable is deleted (its rows are
        # keyed by name), so it can still be read: only a name that never
        # existed has nothing to show.
        if variable is None and history_total == 0:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("config.variable_list"),
                message="Variable not found.",
            )
            return response
        per_page = params["per_page"]
        total_pages = max(1, (history_total + per_page - 1) // per_page)

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.variable_history",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["variable"] = variable
        context["variable_name"] = name
        context["variable_deleted"] = variable is None
        context["format_value"] = format_variable_value
        context["change_diff"] = change_diff_lines
        context["history"] = history
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total"] = history_total
        context["total_pages"] = total_pages
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
        wrapped_handler = _require_admin_permission_for(
            _wrap_admin_handler_in_shell(handler),
            permission=_ROUTE_PERMISSIONS[endpoint_name],
        )
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
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
