"""
.. module:: webinterface.blueprints.config.routes_users
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/users
               (D2 slice -- user management).

.. moduleauthor:: Code Craft AI LLC

The user-management routes served under the config blueprint:

* ``GET  /config/users``                      -- paginated list +
                                                 search.
* ``GET  /config/users/create``               -- new-user form.
* ``POST /config/users/create``               -- create user.
* ``GET  /config/users/{user_id}``            -- detail page.
* ``GET  /config/users/{user_id}/edit``       -- edit form.
* ``POST /config/users/{user_id}/edit``       -- update user.
* ``POST /config/users/{user_id}/deactivate`` -- deactivate
                                                 (soft delete).

All handlers gate on ``_resolve_authenticated_request`` and POST
handlers additionally enforce CSRF via
:func:`auth_guard.enforce_csrf_or_redirect`. The user-management
admin permission check (``users.manage``) lives at the manager
layer; until the user-permission RBAC ports are complete we
allow any authenticated user.

Test seam
---------

``_build_user_manager`` and ``_build_user_create_request`` /
``_build_user_update_request`` are module-level builders around
the lazy imports so unit tests can patch them at the module
binding without dragging the password-hashing source modules
into the test process.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

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
    _AuthResolution,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
    _resolve_db_session,
    _wrap_admin_handler_in_shell,
)


# ---------------------------------------------------------------------------
# Routes table
# ---------------------------------------------------------------------------


_ROUTE_TABLE = (
    ("config.user_list", "/users", ("GET",)),
    ("config.user_create", "/users/create", ("GET", "POST")),
    ("config.user_detail", "/users/{user_id}", ("GET",)),
    ("config.user_edit", "/users/{user_id}/edit", ("GET", "POST")),
    ("config.user_deactivate", "/users/{user_id}/deactivate", ("POST",)),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _build_user_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`UserManager` against the supplied
        SQLAlchemy session. Lazy-imports so the routes module
        does not pull the manager (and its password-hashing
        chain via SecurityManager) at import time.

        :param db_session: Open SQLAlchemy session.

        :returns: UserManager instance.
    """
    from ccai.pychestrate.core.managers.user_manager import (  # noqa: E402
        UserManager,
    )
    rtnval = UserManager(db_session)
    return rtnval


def _build_user_create_request(
        *,
        username: str,
        email: str,
        password: str,
        display_name: str,
        firstname: str,
        lastname: str,
        role_ids: List[int]
    ) -> Any:
    """
        Construct a :class:`UserCreateRequest` carrying the form
        data. Lazy-imports the dataclass so tests can patch this
        helper without importing the source.
    """
    from ccai.pychestrate.core.managers.user_manager import (  # noqa: E402
        UserCreateRequest,
    )
    rtnval = UserCreateRequest(
        username=username,
        email=email,
        password=password,
        display_name=display_name,
        firstname=firstname,
        lastname=lastname,
        role_ids=role_ids,
    )
    return rtnval


def _build_user_update_request(
        *,
        email: Optional[str],
        display_name: Optional[str],
        firstname: Optional[str],
        lastname: Optional[str],
        is_active: Optional[bool],
        role_ids: Optional[List[int]]
    ) -> Any:
    """
        Construct a :class:`UserUpdateRequest` carrying the form
        data. Lazy-imports the dataclass so tests can patch this
        helper.
    """
    from ccai.pychestrate.core.managers.user_manager import (  # noqa: E402
        UserUpdateRequest,
    )
    rtnval = UserUpdateRequest(
        email=email,
        display_name=display_name,
        firstname=firstname,
        lastname=lastname,
        is_active=is_active,
        role_ids=role_ids,
    )
    return rtnval


def _query_system_roles(*, db_session: Any) -> List[Any]:
    """
        Return every :class:`SystemRole` row. Used to populate
        the role-checkbox list on the create/edit user pages.
        Pulled out as a builder so tests can patch the DB call.

        :param db_session: Open SQLAlchemy session.

        :returns: List of SystemRole ORM rows.
    """
    from ccai.pychestrate.core.orm import SystemRole  # noqa: E402
    rtnval = db_session.query(SystemRole).all()
    return rtnval


def _user_manager_exception_classes() -> Dict[str, type]:
    """
        Return a dict mapping the names of UserManager exceptions
        to their classes. Used by handlers to branch on the
        exception type without hard-importing the classes at
        module load time. Tests can patch this to substitute their
        own exception classes.

        :returns: ``{"ValidationError": cls, "DuplicateUserError":
                  cls, "UserNotFoundError": cls}``
    """
    from ccai.pychestrate.core.managers.user_manager import (  # noqa: E402
        DuplicateUserError,
        UserNotFoundError,
        ValidationError,
    )
    rtnval = {
        "ValidationError": ValidationError,
        "DuplicateUserError": DuplicateUserError,
        "UserNotFoundError": UserNotFoundError,
    }
    return rtnval


# ---------------------------------------------------------------------------
# Helpers local to this module
# ---------------------------------------------------------------------------


def _coerce_int_list(*, raw_values: List[str]) -> List[int]:
    """
        Convert a list of form-submitted strings to a list of
        ints, silently dropping non-numeric entries. The HTML
        ``<input type="checkbox">`` always submits the string
        ``value=`` attribute; the manager API requires int IDs.

        :param raw_values: List of submitted strings (may be empty).

        :returns: List of ints (may be empty).
    """
    rtnval: List[int] = []
    for value in raw_values:
        try:
            rtnval.append(int(value))
        except (TypeError, ValueError):
            continue
    return rtnval


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 20
    ) -> Dict[str, Any]:
    """
        Pull ``page`` / ``per_page`` / ``search`` out of the query
        string with safe defaults.

        :param request: Webworks request.
        :param default_per_page: Default items-per-page.

        :returns: ``{"page": int, "per_page": int, "search": str}``
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


def handle_user_list(request: Request) -> Response:
    """
        ``GET /config/users`` -- paginated list of users with an
        optional ``?search=`` filter.

        :param request: Incoming webworks request.

        :returns: HTMLResponse rendering ``config/users/list.html``
                  or a RedirectResponse on unauthenticated /
                  expired session.
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

        user_manager = _build_user_manager(db_session=db_session)
        result = user_manager.list_users(
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
            request_endpoint="config.user_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["users"] = result.users
        context["total"] = total
        context["page"] = params["page"]
        context["per_page"] = per_page
        context["total_pages"] = total_pages
        context["search"] = search

        response = _render(
            template_name="config/users/list.html",
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


def handle_user_create(request: Request) -> Response:
    """
        ``GET /config/users/create`` -- show the create-user form.
        ``POST /config/users/create`` -- create the user.

        :param request: Incoming webworks request.

        :returns: HTMLResponse on GET / failed POST, RedirectResponse
                  to the user list on a successful POST.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        method = request.method.upper()

        if method == "GET":
            roles = _query_system_roles(db_session=db_session)
            flashes = flash.consume_flashes(session=auth.session)
            context = _build_default_template_context(
                session=auth.session,
                request_endpoint="config.user_create",
                flashes=flashes,
                csrf_token=auth.csrf_token,
            )
            context["roles"] = roles
            context["form_data"] = None
            response = _render(
                template_name="config/users/create.html",
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
            fallback_url=_url_for_module.url_for("config.user_create"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        username = str(single_form.get("username", "")).strip()
        email = str(single_form.get("email", "")).strip()
        password = str(single_form.get("password", ""))
        display_name = str(single_form.get("display_name", "")).strip()
        firstname = str(single_form.get("firstname", "")).strip()
        lastname = str(single_form.get("lastname", "")).strip()
        role_ids = _coerce_int_list(
            raw_values=multi_form.get("role_ids", [])
        )

        exc_classes = _user_manager_exception_classes()
        user_manager = _build_user_manager(db_session=db_session)

        try:
            create_request = _build_user_create_request(
                username=username,
                email=email,
                password=password,
                display_name=display_name,
                firstname=firstname,
                lastname=lastname,
                role_ids=role_ids,
            )
            user_manager.create_user(create_request)

            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message='User "{}" created successfully.'.format(username),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except exc_classes["ValidationError"] as exc:
            flash.add_flash(
                session=auth.session,
                message="Validation error: {}".format(
                    getattr(exc, "message", str(exc))
                ),
                category=flash.CATEGORY_ERROR,
            )
        except exc_classes["DuplicateUserError"] as exc:
            flash.add_flash(
                session=auth.session,
                message="Duplicate error: {}".format(
                    getattr(exc, "message", str(exc))
                ),
                category=flash.CATEGORY_ERROR,
            )
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error creating user: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )

        # Re-render the form with the submitted values + flashes.
        roles = _query_system_roles(db_session=db_session)
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.user_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["roles"] = roles
        context["form_data"] = form_view
        response = _render(
            template_name="config/users/create.html",
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


def handle_user_detail(request: Request) -> Response:
    """
        ``GET /config/users/{user_id}`` -- detail page.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        user_id = str(request.path_params.get("user_id", ""))
        user_manager = _build_user_manager(db_session=db_session)
        user = user_manager.get_user(user_id)

        if user is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.user_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["user"] = user
        response = _render(
            template_name="config/users/detail.html",
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


def handle_user_edit(request: Request) -> Response:
    """
        ``GET /config/users/{user_id}/edit`` -- edit form.
        ``POST /config/users/{user_id}/edit`` -- apply update.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        user_id = str(request.path_params.get("user_id", ""))
        user_manager = _build_user_manager(db_session=db_session)
        method = request.method.upper()

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)
            multi_form = _parse_form_multi(request=request)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "config.user_edit", user_id=user_id
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            email = str(single_form.get("email", "")).strip()
            display_name = str(single_form.get("display_name", "")).strip()
            firstname = str(single_form.get("firstname", "")).strip()
            lastname = str(single_form.get("lastname", "")).strip()
            is_active = single_form.get("is_active", "") == "on"
            role_ids = _coerce_int_list(
                raw_values=multi_form.get("role_ids", [])
            )

            exc_classes = _user_manager_exception_classes()

            try:
                update_request = _build_user_update_request(
                    email=email if len(email) > 0 else None,
                    display_name=(
                        display_name if len(display_name) > 0 else None
                    ),
                    firstname=firstname,
                    lastname=lastname,
                    is_active=is_active,
                    role_ids=role_ids,
                )
                user_manager.update_user(user_id, update_request)
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "config.user_detail", user_id=user_id
                    ),
                    message="User updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except exc_classes["ValidationError"] as exc:
                flash.add_flash(
                    session=auth.session,
                    message="Validation error: {}".format(
                        getattr(exc, "message", str(exc))
                    ),
                    category=flash.CATEGORY_ERROR,
                )
            except exc_classes["DuplicateUserError"] as exc:
                flash.add_flash(
                    session=auth.session,
                    message="Duplicate error: {}".format(
                        getattr(exc, "message", str(exc))
                    ),
                    category=flash.CATEGORY_ERROR,
                )
            except Exception as exc:
                flash.add_flash(
                    session=auth.session,
                    message="Error updating user: {}".format(str(exc)),
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through after a recoverable error.
        user = user_manager.get_user(user_id)
        if user is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        roles = _query_system_roles(db_session=db_session)
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.user_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["user"] = user
        context["roles"] = roles
        response = _render(
            template_name="config/users/edit.html",
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


def handle_user_deactivate(request: Request) -> Response:
    """
        ``POST /config/users/{user_id}/deactivate`` -- deactivate
        the user, redirect to the list with a success / error
        flash.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        user_id = str(request.path_params.get("user_id", ""))
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.user_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        user_manager = _build_user_manager(db_session=db_session)
        exc_classes = _user_manager_exception_classes()

        try:
            user_manager.deactivate_user(user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User deactivated successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except exc_classes["UserNotFoundError"]:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="Error deactivating user: {}".format(str(exc)),
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
    "config.user_list": handle_user_list,
    "config.user_create": handle_user_create,
    "config.user_detail": handle_user_detail,
    "config.user_edit": handle_user_edit,
    "config.user_deactivate": handle_user_deactivate,
}


def register_users_routes(*, app: Any) -> None:
    """
        Attach the user-management routes to a webworks app and
        register their endpoint names with the url_for shim.

        :param app: WebWorks application.

        :returns: None.
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
    "register_users_routes",
    "handle_user_list",
    "handle_user_create",
    "handle_user_detail",
    "handle_user_edit",
    "handle_user_deactivate",
]
