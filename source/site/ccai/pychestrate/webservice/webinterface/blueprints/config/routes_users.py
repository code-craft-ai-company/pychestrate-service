"""
.. module:: webinterface.blueprints.config.routes_users
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /admin/users
               (user management over the modern identity store).

.. moduleauthor:: Code Craft AI LLC

The user-management routes served under the config blueprint:

* ``GET  /admin/users``                      -- paginated list +
                                                search.
* ``GET  /admin/users/create``               -- new-user form.
* ``POST /admin/users/create``               -- create user.
* ``GET  /admin/users/{user_id}``            -- detail page.
* ``GET  /admin/users/{user_id}/edit``       -- edit form.
* ``POST /admin/users/{user_id}/edit``       -- update user.
* ``POST /admin/users/{user_id}/deactivate`` -- deactivate
                                                (soft delete).

The handlers are backed by
:mod:`webinterface.blueprints.config.identity_admin`, which reads
and writes the modern identity store (``identity_users`` +
``auth_local_credentials``) the login flow authenticates against,
mirrors the legacy ``user`` row, and manages SYSTEM-scope
``rbac_role_bindings`` -- the rows the RBAC evaluator actually
consults. A user created here can log in, and a role granted here
changes access.

All handlers gate on ``_resolve_authenticated_request`` and POST
handlers additionally enforce CSRF via
:func:`auth_guard.enforce_csrf_or_redirect`.

Test seam
---------

The ``_svc_*`` module-level builders wrap the lazy service imports
so unit tests can patch them at the module binding without
dragging the password-hashing source modules into the test
process.
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
# Lazy-import service seams (test-patchable)
# ---------------------------------------------------------------------------


def _svc_list_users(
        *,
        db_session: Any,
        offset: int,
        limit: int,
        search: Optional[str]
    ) -> Any:
    """
        List identity users. Lazy-imports the service so the routes
        module does not pull the identity / hashing chain at import
        time.

        :param db_session: Open SQLAlchemy session.
        :param offset: Pagination offset.
        :param limit: Page size.
        :param search: Optional search substring.

        :returns: An ``AdminUserListResult``.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    rtnval = identity_admin.list_identity_users(
        db_session=db_session, offset=offset, limit=limit, search=search
    )
    return rtnval


def _svc_get_user(*, db_session: Any, user_id: str) -> Any:
    """
        Fetch one identity user view, or None.

        :param db_session: Open SQLAlchemy session.
        :param user_id: Identity user UUID string.

        :returns: An ``AdminUserView`` or None.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    rtnval = identity_admin.get_identity_user(
        db_session=db_session, user_id=user_id
    )
    return rtnval


def _svc_create_user(
        *,
        db_session: Any,
        username: str,
        email: str,
        password: str,
        display_name: str,
        firstname: str,
        lastname: str,
        role_names: List[str],
        actor_user_id: Optional[str]
    ) -> str:
    """
        Create a user in the modern identity store (with credentials,
        legacy mirror, and role bindings).

        :returns: The new user's UUID string.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    rtnval = identity_admin.create_identity_user(
        db_session=db_session,
        username=username,
        email=email,
        password=password,
        display_name=display_name,
        firstname=firstname,
        lastname=lastname,
        role_names=role_names,
        actor_user_id=actor_user_id,
    )
    return rtnval


def _svc_update_user(
        *,
        db_session: Any,
        user_id: str,
        email: str,
        display_name: str,
        firstname: str,
        lastname: str,
        is_active: bool,
        role_names: List[str],
        actor_user_id: Optional[str]
    ) -> None:
    """
        Update the identity row, mirror, and role bindings.

        :returns: None.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    identity_admin.update_identity_user(
        db_session=db_session,
        user_id=user_id,
        email=email,
        display_name=display_name,
        firstname=firstname,
        lastname=lastname,
        is_active=is_active,
        role_names=role_names,
        actor_user_id=actor_user_id,
    )
    return


def _svc_deactivate_user(
        *,
        db_session: Any,
        user_id: str,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Deactivate the identity user (and mirror the status).

        :returns: None.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    identity_admin.deactivate_identity_user(
        db_session=db_session, user_id=user_id, actor_user_id=actor_user_id
    )
    return


def _svc_list_role_options(*, db_session: Any) -> List[Any]:
    """
        List the RBAC roles offered by the role picker on the user
        forms, first ensuring every catalog-declared role has a
        persisted row.

        :param db_session: Open SQLAlchemy session.

        :returns: List of ``AdminRoleView``.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    identity_admin.ensure_catalog_roles_persisted(db_session=db_session)
    rtnval = identity_admin.list_rbac_roles(db_session=db_session)
    return rtnval


def _admin_exception_classes() -> Dict[str, type]:
    """
        Return a dict mapping the names of the identity-admin service
        exceptions to their classes so handlers can branch on the
        exception type without hard-importing the classes at module
        load time. Tests patch this to substitute fakes.

        :returns: ``{"AdminValidationError": cls, "AdminDuplicateError":
                  cls, "AdminNotFoundError": cls, "SelfLockoutError":
                  cls}``
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config.identity_admin import (  # noqa: E402
        AdminDuplicateError,
        AdminNotFoundError,
        AdminValidationError,
        SelfLockoutError,
    )
    rtnval = {
        "AdminValidationError": AdminValidationError,
        "AdminDuplicateError": AdminDuplicateError,
        "AdminNotFoundError": AdminNotFoundError,
        "SelfLockoutError": SelfLockoutError,
    }
    return rtnval


# ---------------------------------------------------------------------------
# Helpers local to this module
# ---------------------------------------------------------------------------


def _clean_role_names(*, raw_values: List[str]) -> List[str]:
    """
        Normalize the submitted role-name checkbox values: strip
        whitespace and drop empties / duplicates while preserving
        order.

        :param raw_values: List of submitted strings (may be empty).

        :returns: List of role names (may be empty).
    """
    rtnval: List[str] = []
    for value in raw_values:
        cleaned = str(value).strip()
        if len(cleaned) == 0:
            continue
        if cleaned in rtnval:
            continue
        rtnval.append(cleaned)
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
        ``GET /admin/users`` -- paginated list of identity users with
        an optional ``?search=`` filter.

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

        result = _svc_list_users(
            db_session=db_session,
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
        context["current_user_id"] = auth.user_id

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
        ``GET /admin/users/create`` -- show the create-user form.
        ``POST /admin/users/create`` -- create the user in the modern
        identity store so the new account can actually log in.

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
            roles = _svc_list_role_options(db_session=db_session)
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
        role_names = _clean_role_names(
            raw_values=multi_form.get("role_names", [])
        )

        exc_classes = _admin_exception_classes()

        try:
            _svc_create_user(
                db_session=db_session,
                username=username,
                email=email,
                password=password,
                display_name=display_name,
                firstname=firstname,
                lastname=lastname,
                role_names=role_names,
                actor_user_id=auth.user_id,
            )

            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message='User "{}" created successfully.'.format(username),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except exc_classes["AdminValidationError"] as exc:
            flash.add_flash(
                session=auth.session,
                message="Validation error: {}".format(
                    getattr(exc, "message", str(exc))
                ),
                category=flash.CATEGORY_ERROR,
            )
        except exc_classes["AdminDuplicateError"] as exc:
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
        roles = _svc_list_role_options(db_session=db_session)
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
        ``GET /admin/users/{user_id}`` -- detail page.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        user_id = str(request.path_params.get("user_id", ""))
        user = _svc_get_user(db_session=db_session, user_id=user_id)

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
        context["current_user_id"] = auth.user_id
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
        ``GET /admin/users/{user_id}/edit`` -- edit form.
        ``POST /admin/users/{user_id}/edit`` -- apply update
        (identity row + legacy mirror + SYSTEM-scope role bindings).

        Server-side self-lockout guards refuse an admin deactivating
        their own account or removing their own system-admin role.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        user_id = str(request.path_params.get("user_id", ""))
        method = request.method.upper()
        is_self = user_id == str(auth.user_id)

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
            role_names = _clean_role_names(
                raw_values=multi_form.get("role_names", [])
            )

            if is_self is True:
                # The self row hides the status + role controls, so
                # the form posts neither. Preserve the current values
                # server-side rather than treating absence as
                # "deactivate + remove all roles".
                current = _svc_get_user(
                    db_session=db_session, user_id=user_id
                )
                if current is not None:
                    is_active = current.is_active
                    role_names = list(current.roles)

            exc_classes = _admin_exception_classes()

            try:
                _svc_update_user(
                    db_session=db_session,
                    user_id=user_id,
                    email=email,
                    display_name=display_name,
                    firstname=firstname,
                    lastname=lastname,
                    is_active=is_active,
                    role_names=role_names,
                    actor_user_id=auth.user_id,
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "config.user_detail", user_id=user_id
                    ),
                    message="User updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except exc_classes["AdminNotFoundError"]:
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for("config.user_list"),
                    message="User not found.",
                    category=flash.CATEGORY_ERROR,
                )
                return response
            except exc_classes["SelfLockoutError"] as exc:
                flash.add_flash(
                    session=auth.session,
                    message=getattr(exc, "message", str(exc)),
                    category=flash.CATEGORY_ERROR,
                )
            except exc_classes["AdminValidationError"] as exc:
                flash.add_flash(
                    session=auth.session,
                    message="Validation error: {}".format(
                        getattr(exc, "message", str(exc))
                    ),
                    category=flash.CATEGORY_ERROR,
                )
            except exc_classes["AdminDuplicateError"] as exc:
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
        user = _svc_get_user(db_session=db_session, user_id=user_id)
        if user is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        roles = _svc_list_role_options(db_session=db_session)
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.user_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["user"] = user
        context["roles"] = roles
        context["current_user_id"] = auth.user_id
        context["is_self"] = is_self
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
        ``POST /admin/users/{user_id}/deactivate`` -- deactivate the
        identity user, redirect to the list with a success / error
        flash. Refuses (server-side) when an admin targets their own
        account.
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

        exc_classes = _admin_exception_classes()

        try:
            _svc_deactivate_user(
                db_session=db_session,
                user_id=user_id,
                actor_user_id=auth.user_id,
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User deactivated successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except exc_classes["AdminNotFoundError"]:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response
        except exc_classes["SelfLockoutError"] as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message=getattr(exc, "message", str(exc)),
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
