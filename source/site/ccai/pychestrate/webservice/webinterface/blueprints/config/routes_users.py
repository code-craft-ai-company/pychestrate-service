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
* ``POST /admin/users/{user_id}/reactivate`` -- reactivate a
                                                deactivated user.
* ``GET  /admin/users/{user_id}/password``   -- reset-password page.
* ``POST /admin/users/{user_id}/password``   -- set a (temporary)
                                                password.
* ``POST /admin/users/{user_id}/password-link`` -- create a single-use
                                                reset (or invite)
                                                link to hand to the
                                                user.

The create form can also create the account *without* a password and
hand back a single-use invite link instead (the product sends no email
yet, so the administrator copies the link to the user).

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


from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.security.auth.password_policy import (
    password_policy_template_context,
)
from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    form_errors,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    MultiFormView,
    _AuthResolution,
    _attach_session_to_response,
    _build_default_template_context,
    _has_permission,
    _parse_form_multi,
    _parse_form_or_empty,
    _not_found_redirect,
    _redirect_with_flash,
    _render,
    _require_admin_permission_for,
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
    ("config.user_reactivate", "/users/{user_id}/reactivate", ("POST",)),
    ("config.user_password", "/users/{user_id}/password", ("GET", "POST")),
    ("config.user_password_link", "/users/{user_id}/password-link", ("POST",)),
)

USERS_READ_PERMISSION: str = "system:users.read"
USERS_WRITE_PERMISSION: str = "system:users.write"

#: Granting or removing roles changes what a user may do, so it needs
#: the RBAC administration key on top of ``system:users.write``.
#: Without it, a user manager could hand out ``system-admin``.
ROLE_ASSIGN_PERMISSION: str = "system:rbac.admin"

ROLE_CHANGE_NOT_APPLIED_MESSAGE: str = (
    "Role changes were not applied: changing a user's roles requires "
    "the system:rbac.admin permission."
)

#: Visible labels of the user form fields, for the error summary.
USER_FIELD_LABELS: Dict[str, str] = {
    "username": "Username",
    "email": "Email",
    "password": "Password",
    "display_name": "Display Name",
    "firstname": "First Name",
    "lastname": "Last Name",
}


def _user_with_submitted_values(
        *, user: Any, email: str, display_name: str, firstname: str,
        lastname: str, is_active: bool, role_names: List[str]
    ) -> Any:
    """
        The user the edit form re-renders after a refused save: the
        stored user with what was typed laid over it, so a validation
        error does not throw the edits away.
    """
    fields = dict(vars(user)) if hasattr(user, "__dict__") else {}
    for name in ("id", "username", "roles", "is_active"):
        if name not in fields:
            fields[name] = getattr(user, name, None)
    fields.update(
        email=email,
        display_name=display_name,
        firstname=firstname,
        lastname=lastname,
        is_active=is_active,
        roles=list(role_names),
    )
    rtnval = SimpleNamespace(**fields)
    return rtnval

# Permission each route enforces server-side. Create and edit forms
# need the write key even to display, since they exist only to write.
_ROUTE_PERMISSIONS = {
    "config.user_list": USERS_READ_PERMISSION,
    "config.user_create": USERS_WRITE_PERMISSION,
    "config.user_detail": USERS_READ_PERMISSION,
    "config.user_edit": USERS_WRITE_PERMISSION,
    "config.user_deactivate": USERS_WRITE_PERMISSION,
    "config.user_reactivate": USERS_WRITE_PERMISSION,
    "config.user_password": USERS_WRITE_PERMISSION,
    "config.user_password_link": USERS_WRITE_PERMISSION,
}

#: ``password_setup`` choices on the create form.
PASSWORD_SETUP_SET_NOW: str = "password"
PASSWORD_SETUP_INVITE: str = "invite"


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


def _svc_reactivate_user(
        *,
        db_session: Any,
        user_id: str,
        actor_user_id: Optional[str]
    ) -> str:
    """
        Reactivate a deactivated identity user (and mirror the status).

        :returns: The resulting status text ("active" or "invited").
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    rtnval = identity_admin.reactivate_identity_user(
        db_session=db_session, user_id=user_id, actor_user_id=actor_user_id
    )
    return rtnval


def _status_action_return_url(*, form: Any, user_id: str) -> str:
    """
        Where a Deactivate / Reactivate button returns to: the user's
        detail page when the button was on it (``return_to=detail``),
        else the user list. Any other value falls back to the list.
    """
    return_to = ""
    try:
        return_to = str(form.get("return_to", "") or "")
    except Exception:
        return_to = ""
    if return_to == "detail" and len(user_id) > 0:
        rtnval = _url_for_module.url_for("config.user_detail", user_id=user_id)
        return rtnval
    rtnval = _url_for_module.url_for("config.user_list")
    return rtnval


def _svc_create_invited_user(
        *,
        db_session: Any,
        username: str,
        email: str,
        display_name: str,
        firstname: str,
        lastname: str,
        role_names: List[str],
        actor_user_id: Optional[str]
    ) -> Any:
    """
        Create an account without a password plus a single-use invite
        link.

        :returns: ``identity_admin.InvitedUser``.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    rtnval = identity_admin.create_invited_identity_user(
        db_session=db_session,
        username=username,
        email=email,
        display_name=display_name,
        firstname=firstname,
        lastname=lastname,
        role_names=role_names,
        actor_user_id=actor_user_id,
    )
    return rtnval


def _svc_admin_set_password(
        *,
        db_session: Any,
        user_id: str,
        password: str,
        must_change: bool,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Set a user's password (committing).

        :raises: PasswordPolicyError, PasswordLifecycleError
    """
    from ccai.pychestrate.webservice.security.auth import (  # noqa: E402
        password_lifecycle,
    )
    try:
        password_lifecycle.admin_set_password(
            db_session=db_session,
            user_id=user_id,
            new_password=password,
            must_change=must_change,
            actor_user_id=actor_user_id,
        )
        db_session.commit()
    except BaseException:
        db_session.rollback()
        raise
    return


def _svc_issue_password_link(
        *,
        db_session: Any,
        user_id: str,
        purpose: str,
        actor_user_id: Optional[str]
    ) -> Any:
    """
        Create a single-use password link (committing).

        :returns: ``password_lifecycle.IssuedPasswordLink``.
        :raises: PasswordLifecycleError
    """
    from ccai.pychestrate.webservice.security.auth import (  # noqa: E402
        password_lifecycle,
    )
    try:
        rtnval = password_lifecycle.issue_password_link(
            db_session=db_session,
            user_id=user_id,
            purpose=purpose,
            actor_user_id=actor_user_id,
        )
        db_session.commit()
    except BaseException:
        db_session.rollback()
        raise
    return rtnval


def _password_error_classes() -> Tuple[type, ...]:
    """
        The exceptions the password seams raise for a refused request.
    """
    from ccai.pychestrate.webservice.security.auth.password_lifecycle import (  # noqa: E402
        PasswordLifecycleError,
    )
    from ccai.pychestrate.webservice.security.auth.password_policy import (  # noqa: E402
        PasswordPolicyError,
    )
    rtnval = (PasswordPolicyError, PasswordLifecycleError)
    return rtnval


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


def _absolute_url(*, request: Request, path: str) -> str:
    """
        ``scheme://host`` + ``path`` for a link the administrator copies
        to the user (built from the address the browser used).

        :param request: Incoming webworks request.
        :param path: Absolute path.

        :returns: Absolute URL (or ``path`` when the host is unknown).
    """
    scheme = getattr(request, "scheme", None)
    if isinstance(scheme, str) is False or len(scheme) == 0:
        scheme = "http"
    host = None
    try:
        host = request.headers.get("host", None) or request.headers.get("Host", None)
    except Exception:
        host = None
    if host is None or len(str(host)) == 0:
        server_name = getattr(request, "host", None)
        if isinstance(server_name, str) is False or len(server_name) == 0:
            return path
        port = getattr(request, "port", None)
        if isinstance(port, int) is True and port not in (0, 80, 443):
            host = "{}:{}".format(server_name, port)
        else:
            host = server_name
    rtnval = "{}://{}{}".format(scheme, host, path)
    return rtnval


def _link_view(*, request: Request, link: Any) -> Dict[str, Any]:
    """
        What the password page shows for a freshly issued link.
    """
    path = _url_for_module.url_for("config.password_link", token=link.secret)
    rtnval = {
        "url": _absolute_url(request=request, path=path),
        "purpose": link.purpose,
        "expires_at": link.expires_at,
    }
    return rtnval


def _render_password_page(
        *,
        auth: _AuthResolution,
        user: Any,
        issued_link: Optional[Dict[str, Any]] = None,
        errors: Optional[Dict[str, str]] = None,
        problems: Optional[List[str]] = None,
        just_created: bool = False,
        status_code: int = 200
    ) -> Response:
    """
        Render ``config/users/password.html``: the reset-link and
        temporary-password options, and a freshly issued link shown
        once.
    """
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="config.user_password",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context.update(password_policy_template_context())
    context["user"] = user
    context["issued_link"] = issued_link
    context["errors"] = errors if errors is not None else {}
    context["error_labels"] = form_errors.PASSWORD_FIELD_LABELS
    context["problems"] = problems if problems is not None else []
    context["just_created"] = just_created
    context["is_self"] = str(user.id) == str(auth.user_id)
    response = _render(
        template_name="config/users/password.html",
        context=context,
        status_code=status_code,
    )
    # The page can carry a link secret: never cache it, never leak it
    # through the Referer header.
    response._headers["Cache-Control"] = "no-store"
    response._headers["Referrer-Policy"] = "no-referrer"
    _attach_session_to_response(response=response, session=auth.session)
    return response


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
            context.update(password_policy_template_context())
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
        password_setup = str(
            single_form.get("password_setup", PASSWORD_SETUP_SET_NOW)
        ).strip()
        display_name = str(single_form.get("display_name", "")).strip()
        firstname = str(single_form.get("firstname", "")).strip()
        lastname = str(single_form.get("lastname", "")).strip()
        role_names = _clean_role_names(
            raw_values=multi_form.get("role_names", [])
        )
        if (
            len(role_names) > 0
            and _has_permission(auth=auth, permission=ROLE_ASSIGN_PERMISSION) is False
        ):
            # Create the account, but never let a user manager grant
            # roles they could not grant through the Roles pages.
            role_names = []
            flash.add_flash(
                session=auth.session,
                message=ROLE_CHANGE_NOT_APPLIED_MESSAGE,
                category=flash.CATEGORY_WARNING,
            )

        exc_classes = _admin_exception_classes()
        errors: Dict[str, str] = {}

        try:
            if password_setup == PASSWORD_SETUP_INVITE:
                invited = _svc_create_invited_user(
                    db_session=db_session,
                    username=username,
                    email=email,
                    display_name=display_name,
                    firstname=firstname,
                    lastname=lastname,
                    role_names=role_names,
                    actor_user_id=auth.user_id,
                )
                # The link secret is shown once, on this response --
                # never in the flash cookie.
                new_user = _svc_get_user(
                    db_session=db_session, user_id=invited.user_id
                )
                response = _render_password_page(
                    auth=auth,
                    user=new_user,
                    issued_link=_link_view(request=request, link=invited.link),
                    just_created=True,
                    status_code=201,
                )
                return response

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
        except (exc_classes["AdminValidationError"], exc_classes["AdminDuplicateError"]) as exc:
            # A problem with one input is shown next to it; anything
            # else stays a banner above the form.
            errors = form_errors.field_errors_from(exc)
            if len(errors) == 0:
                flash.add_flash(
                    session=auth.session,
                    message=form_errors.error_message(exc),
                    category=flash.CATEGORY_ERROR,
                )
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error creating user: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )

        # Re-render the form with the submitted values + errors.
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
        context["errors"] = errors
        context["error_labels"] = USER_FIELD_LABELS
        context.update(password_policy_template_context())
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
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
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
        errors: Dict[str, str] = {}
        submitted: Optional[Dict[str, Any]] = None
        status_code = 200

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
            elif _has_permission(auth=auth, permission=ROLE_ASSIGN_PERMISSION) is False:
                # A user manager without RBAC administration may edit
                # profile fields and status, but not roles: keep the
                # user's current role set whatever the form posted.
                current = _svc_get_user(
                    db_session=db_session, user_id=user_id
                )
                current_roles = list(current.roles) if current is not None else []
                if set(role_names) != set(current_roles):
                    role_names = current_roles
                    flash.add_flash(
                        session=auth.session,
                        message=ROLE_CHANGE_NOT_APPLIED_MESSAGE,
                        category=flash.CATEGORY_WARNING,
                    )

            exc_classes = _admin_exception_classes()
            submitted = {
                "email": email,
                "display_name": display_name,
                "firstname": firstname,
                "lastname": lastname,
                "is_active": is_active,
                "role_names": role_names,
            }
            status_code = 400

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
                response = _not_found_redirect(
                    session=auth.session,
                    url=_url_for_module.url_for("config.user_list"),
                    message="User not found.",
                )
                return response
            except exc_classes["SelfLockoutError"] as exc:
                flash.add_flash(
                    session=auth.session,
                    message=getattr(exc, "message", str(exc)),
                    category=flash.CATEGORY_ERROR,
                )
            except (exc_classes["AdminValidationError"], exc_classes["AdminDuplicateError"]) as exc:
                errors = form_errors.field_errors_from(exc)
                if len(errors) == 0:
                    flash.add_flash(
                        session=auth.session,
                        message=form_errors.error_message(exc),
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
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
            )
            return response

        if submitted is not None:
            user = _user_with_submitted_values(user=user, **submitted)

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
        context["errors"] = errors
        context["error_labels"] = USER_FIELD_LABELS
        response = _render(
            template_name="config/users/edit.html",
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

        return_url = _status_action_return_url(form=single_form, user_id=user_id)

        try:
            _svc_deactivate_user(
                db_session=db_session,
                user_id=user_id,
                actor_user_id=auth.user_id,
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=return_url,
                message="User deactivated successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except exc_classes["AdminNotFoundError"]:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
            )
            return response
        except exc_classes["SelfLockoutError"] as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=return_url,
                message=getattr(exc, "message", str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=return_url,
                message="Error deactivating user: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_user_reactivate(request: Request) -> Response:
    """
        ``POST /admin/users/{user_id}/reactivate`` -- reactivate a
        deactivated identity user, then return to the list (or the
        detail page the button was on) with a flash. A local account
        that never set a password returns to *invited*, and the flash
        says to send a new invite link.
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

        return_url = _status_action_return_url(form=single_form, user_id=user_id)
        exc_classes = _admin_exception_classes()

        try:
            status_text = _svc_reactivate_user(
                db_session=db_session,
                user_id=user_id,
                actor_user_id=auth.user_id,
            )
        except exc_classes["AdminNotFoundError"]:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
            )
            return response
        except exc_classes["AdminValidationError"] as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=return_url,
                message=getattr(exc, "message", str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=return_url,
                message="Error reactivating user: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response

        message = "User reactivated. They can sign in again."
        if status_text == "invited":
            message = (
                "User reactivated as invited: they have never set a "
                "password, so send them a new invite link."
            )
        response = _redirect_with_flash(
            session=auth.session,
            url=return_url,
            message=message,
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_user_password(request: Request) -> Response:
    """
        ``GET /admin/users/{user_id}/password`` -- the reset-password
        page (reset link or temporary password).
        ``POST /admin/users/{user_id}/password`` -- set the user's
        password; by default they must choose a new one at their next
        sign-in. Their sessions end.

        :param request: Incoming webworks request.

        :returns: The page, or a redirect to the user after a set.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        user_id = str(request.path_params.get("user_id", ""))
        user = _svc_get_user(db_session=db_session, user_id=user_id)
        if user is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
            )
            return response

        if request.method.upper() != "POST":
            return _render_password_page(auth=auth, user=user)

        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.user_password", user_id=user_id),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        password = str(single_form.get("password", ""))
        confirm = str(single_form.get("password_confirm", ""))
        must_change = str(single_form.get("must_change", "")).strip() in ("1", "on", "true", "yes")
        if password != confirm:
            return _render_password_page(
                auth=auth, user=user,
                errors={"password_confirm": "The passwords do not match."}, status_code=400,
            )

        try:
            _svc_admin_set_password(
                db_session=db_session,
                user_id=user_id,
                password=password,
                must_change=must_change,
                actor_user_id=auth.user_id,
            )
        except _password_error_classes() as exc:
            errors, problems = form_errors.password_form_errors(exc)
            return _render_password_page(
                auth=auth, user=user, errors=errors, problems=problems, status_code=400,
            )

        if must_change is True:
            message = (
                'Password set for "{}". They must choose a new one when they '
                "next sign in; their open sessions were signed out."
            ).format(user.username)
        else:
            message = (
                'Password set for "{}"; their open sessions were signed out.'
            ).format(user.username)
        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.user_detail", user_id=user_id),
            message=message,
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_user_password_link(request: Request) -> Response:
    """
        ``POST /admin/users/{user_id}/password-link`` -- create a
        single-use link the user opens to choose a password: an invite
        for an account that has none yet, a reset otherwise. Earlier
        links stop working. The link is shown once, on this response.

        :param request: Incoming webworks request.

        :returns: The password page carrying the link.
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
            fallback_url=_url_for_module.url_for("config.user_password", user_id=user_id),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        user = _svc_get_user(db_session=db_session, user_id=user_id)
        if user is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("config.user_list"),
                message="User not found.",
            )
            return response

        purpose = "INVITE" if getattr(user, "status", "") == "invited" else "RESET"
        try:
            link = _svc_issue_password_link(
                db_session=db_session,
                user_id=user_id,
                purpose=purpose,
                actor_user_id=auth.user_id,
            )
        except _password_error_classes() as exc:
            return _render_password_page(
                auth=auth, user=user,
                problems=[getattr(exc, "message", str(exc))], status_code=400,
            )

        return _render_password_page(
            auth=auth, user=user, issued_link=_link_view(request=request, link=link),
        )
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
    "config.user_reactivate": handle_user_reactivate,
    "config.user_password": handle_user_password,
    "config.user_password_link": handle_user_password_link,
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
        wrapped_handler = _require_admin_permission_for(
            _wrap_admin_handler_in_shell(handler),
            permission=_ROUTE_PERMISSIONS[endpoint_name],
        )
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_users_routes",
    "handle_user_list",
    "handle_user_create",
    "handle_user_detail",
    "handle_user_edit",
    "handle_user_deactivate",
    "handle_user_reactivate",
    "handle_user_password",
    "handle_user_password_link",
]
