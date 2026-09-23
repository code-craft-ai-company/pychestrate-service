"""
.. module:: webinterface.blueprints.config.routes_roles
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /admin/roles
               (role management over the modern RBAC store).

.. moduleauthor:: Code Craft AI LLC

The role-management routes served under the config blueprint:

* ``GET  /admin/roles``                    -- list roles.
* ``GET  /admin/roles/create``             -- new-role form.
* ``POST /admin/roles/create``             -- create role.
* ``GET  /admin/roles/{role_id}``          -- detail page.
* ``GET  /admin/roles/{role_id}/edit``     -- edit form.
* ``POST /admin/roles/{role_id}/edit``     -- update role.
* ``POST /admin/roles/{role_id}/delete``   -- delete role.

The handlers are backed by
:mod:`webinterface.blueprints.config.identity_admin`, which
operates on the modern :class:`RbacRole` /
:class:`RbacRolePermission` / :class:`RbacRoleBinding` tables --
the store ``rbac_evaluator.check_permission`` evaluates. Custom
roles created here grant real access once bound; built-in /
extension roles (grants defined in the in-memory catalog) are
shown read-only and refuse edit / delete with an explanatory
message.

Removing every permission from a role requires the explicit
``confirm_remove_all`` form acknowledgement so a submit with no
boxes ticked cannot silently wipe a role's grants.

Test seam
---------

The ``_svc_*`` module-level builders wrap the lazy service imports
so unit tests can patch them at the module binding.
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


_ROUTE_TABLE = (
    ("config.role_list", "/roles", ("GET",)),
    ("config.role_create", "/roles/create", ("GET", "POST")),
    ("config.role_detail", "/roles/{role_id}", ("GET",)),
    ("config.role_edit", "/roles/{role_id}/edit", ("GET", "POST")),
    ("config.role_delete", "/roles/{role_id}/delete", ("POST",)),
)

# Permission each route enforces server-side (see
# ``routes._require_admin_permission_for``). Roles and their permission sets.
_ROUTE_PERMISSIONS = {
    "config.role_list": "system:rbac.read",
    "config.role_create": "system:rbac.admin",
    "config.role_detail": "system:rbac.read",
    "config.role_edit": "system:rbac.admin",
    "config.role_delete": "system:rbac.admin",
}


# ---------------------------------------------------------------------------
# Lazy-import service seams (test-patchable)
# ---------------------------------------------------------------------------


def _svc_list_roles(*, db_session: Any) -> List[Any]:
    """
        List every RBAC role (with permissions + binding counts),
        first ensuring every catalog-declared role has a persisted
        row so the page shows the complete role set.

        :param db_session: Open SQLAlchemy session.

        :returns: List of ``AdminRoleView``.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    identity_admin.ensure_catalog_roles_persisted(db_session=db_session)
    rtnval = identity_admin.list_rbac_roles(db_session=db_session)
    return rtnval


def _svc_get_role(*, db_session: Any, role_id: str) -> Optional[Any]:
    """
        Fetch one role view, or None.

        :param db_session: Open SQLAlchemy session.
        :param role_id: Role UUID string.

        :returns: An ``AdminRoleView`` or None.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    rtnval = identity_admin.get_rbac_role(
        db_session=db_session, role_id=role_id
    )
    return rtnval


def _svc_create_role(
        *,
        db_session: Any,
        name: str,
        description: str,
        permission_keys: List[str],
        actor_user_id: Optional[str] = None
    ) -> str:
    """
        Create a custom RBAC role carrying the selected catalog
        permission keys.

        :returns: The new role's UUID string.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    rtnval = identity_admin.create_rbac_role(
        db_session=db_session,
        name=name,
        description=description,
        permission_keys=permission_keys,
        actor_user_id=actor_user_id,
    )
    return rtnval


def _svc_update_role(
        *,
        db_session: Any,
        role_id: str,
        description: str,
        permission_keys: List[str],
        actor_user_id: Optional[str] = None
    ) -> None:
    """
        Update a custom role's description + permission relation.

        :returns: None.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    identity_admin.update_rbac_role(
        db_session=db_session,
        role_id=role_id,
        description=description,
        permission_keys=permission_keys,
        actor_user_id=actor_user_id,
    )
    return


def _svc_delete_role(
        *,
        db_session: Any,
        role_id: str,
        actor_user_id: Optional[str] = None
    ) -> int:
    """
        Delete a custom role (with its permission rows + bindings).

        :returns: Number of bindings that were removed.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    rtnval = identity_admin.delete_rbac_role(
        db_session=db_session, role_id=role_id, actor_user_id=actor_user_id
    )
    return rtnval


def _svc_list_catalog_permissions() -> List[Any]:
    """
        List the valid (catalog-registered) system permission keys
        for the role forms.

        :returns: List of ``AdminPermissionView``.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )
    rtnval = identity_admin.list_catalog_permissions()
    return rtnval


def _roles_exception_classes() -> Dict[str, type]:
    """
        Return a dict mapping the names of the identity-admin service
        exceptions the role handlers branch on to their classes.
        Tests patch this to substitute fakes.

        :returns: ``{"AdminValidationError": cls, "AdminDuplicateError":
                  cls, "AdminNotFoundError": cls,
                  "BuiltinRoleProtectedError": cls,
                  "LastAdminRoleError": cls}``
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config.identity_admin import (  # noqa: E402
        AdminDuplicateError,
        AdminNotFoundError,
        AdminValidationError,
        BuiltinRoleProtectedError,
        LastAdminRoleError,
    )
    rtnval = {
        "AdminValidationError": AdminValidationError,
        "AdminDuplicateError": AdminDuplicateError,
        "AdminNotFoundError": AdminNotFoundError,
        "BuiltinRoleProtectedError": BuiltinRoleProtectedError,
        "LastAdminRoleError": LastAdminRoleError,
    }
    return rtnval


# ---------------------------------------------------------------------------
# Helpers local to this module
# ---------------------------------------------------------------------------


def _clean_permission_keys(*, raw_values: List[str]) -> List[str]:
    """
        Normalize the submitted permission-key checkbox values: strip
        whitespace and drop empties / duplicates while preserving
        order.

        :param raw_values: List of submitted strings (may be empty).

        :returns: List of permission keys (may be empty).
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


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_role_list(request: Request) -> Response:
    """
        ``GET /admin/roles`` -- list every RBAC role.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        roles = _svc_list_roles(db_session=db_session)
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.role_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["roles"] = roles
        response = _render(
            template_name="config/roles/list.html",
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


def handle_role_create(request: Request) -> Response:
    """
        ``GET /admin/roles/create`` -- show the create-role form.
        ``POST /admin/roles/create`` -- create a custom RBAC role.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        method = request.method.upper()

        if method == "GET":
            permissions = _svc_list_catalog_permissions()
            flashes = flash.consume_flashes(session=auth.session)
            context = _build_default_template_context(
                session=auth.session,
                request_endpoint="config.role_create",
                flashes=flashes,
                csrf_token=auth.csrf_token,
            )
            context["permissions"] = permissions
            context["form_data"] = None
            response = _render(
                template_name="config/roles/create.html",
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
            fallback_url=_url_for_module.url_for("config.role_create"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        description = str(single_form.get("description", "")).strip()
        permission_keys = _clean_permission_keys(
            raw_values=multi_form.get("permission_keys", [])
        )

        exc_classes = _roles_exception_classes()

        try:
            _svc_create_role(
                db_session=db_session,
                name=name,
                description=description,
                permission_keys=permission_keys,
                actor_user_id=auth.user_id,
            )

            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message='Role "{}" created successfully.'.format(name),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except exc_classes["AdminValidationError"] as exc:
            flash.add_flash(
                session=auth.session,
                message=getattr(exc, "message", str(exc)),
                category=flash.CATEGORY_ERROR,
            )
        except exc_classes["AdminDuplicateError"] as exc:
            flash.add_flash(
                session=auth.session,
                message=getattr(exc, "message", str(exc)),
                category=flash.CATEGORY_ERROR,
            )
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error creating role: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )

        # Re-render the form with the submitted values.
        permissions = _svc_list_catalog_permissions()
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.role_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["permissions"] = permissions
        context["form_data"] = form_view
        response = _render(
            template_name="config/roles/create.html",
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


def handle_role_detail(request: Request) -> Response:
    """
        ``GET /admin/roles/{role_id}`` -- detail page with the
        role's permission keys and live binding count.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        role_id = str(request.path_params.get("role_id", ""))
        role = _svc_get_role(db_session=db_session, role_id=role_id)
        if role is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message="Role not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.role_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["role"] = role
        response = _render(
            template_name="config/roles/detail.html",
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


def handle_role_edit(request: Request) -> Response:
    """
        ``GET /admin/roles/{role_id}/edit`` -- edit form.
        ``POST /admin/roles/{role_id}/edit`` -- apply update.

        Built-in / extension roles refuse the update with an error
        flash. Submitting an empty permission set requires the
        ``confirm_remove_all`` acknowledgement checkbox so a role's
        grants cannot be silently wiped.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        role_id = str(request.path_params.get("role_id", ""))
        role = _svc_get_role(db_session=db_session, role_id=role_id)
        if role is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message="Role not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        method = request.method.upper()

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)
            multi_form = _parse_form_multi(request=request)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "config.role_edit", role_id=role_id
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            if role.is_system is True:
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "config.role_detail", role_id=role_id
                    ),
                    message=(
                        "Built-in roles cannot be modified. Their "
                        "permissions are defined by the system."
                    ),
                    category=flash.CATEGORY_ERROR,
                )
                return response

            description = str(single_form.get("description", "")).strip()
            permission_keys = _clean_permission_keys(
                raw_values=multi_form.get("permission_keys", [])
            )
            confirm_remove_all = (
                str(single_form.get("confirm_remove_all", "")) == "on"
            )

            # Only a genuine removal needs the confirmation. A role
            # that already grants nothing is not losing anything by
            # being saved with nothing selected, and demanding the
            # tick there makes its description un-editable.
            currently_grants_permissions = len(role.permissions) > 0
            removing_all_permissions = (
                currently_grants_permissions is True
                and len(permission_keys) == 0
            )

            if removing_all_permissions is True and confirm_remove_all is False:
                flash.add_flash(
                    session=auth.session,
                    message=(
                        "No permissions are selected. Tick "
                        '"I intend to remove all permissions from '
                        'this role" to confirm, or select the '
                        "permissions the role should keep."
                    ),
                    category=flash.CATEGORY_ERROR,
                )
            else:
                exc_classes = _roles_exception_classes()
                try:
                    _svc_update_role(
                        db_session=db_session,
                        role_id=role_id,
                        description=description,
                        permission_keys=permission_keys,
                        actor_user_id=auth.user_id,
                    )

                    response = _redirect_with_flash(
                        session=auth.session,
                        url=_url_for_module.url_for(
                            "config.role_detail", role_id=role_id
                        ),
                        message="Role updated successfully.",
                        category=flash.CATEGORY_SUCCESS,
                    )
                    return response
                except exc_classes["BuiltinRoleProtectedError"] as exc:
                    response = _redirect_with_flash(
                        session=auth.session,
                        url=_url_for_module.url_for(
                            "config.role_detail", role_id=role_id
                        ),
                        message=getattr(exc, "message", str(exc)),
                        category=flash.CATEGORY_ERROR,
                    )
                    return response
                except exc_classes["AdminValidationError"] as exc:
                    flash.add_flash(
                        session=auth.session,
                        message=getattr(exc, "message", str(exc)),
                        category=flash.CATEGORY_ERROR,
                    )
                except Exception as exc:
                    flash.add_flash(
                        session=auth.session,
                        message="Error updating role: {}".format(str(exc)),
                        category=flash.CATEGORY_ERROR,
                    )

        # GET, or POST that fell through after a recoverable error.
        role = _svc_get_role(db_session=db_session, role_id=role_id)
        if role is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message="Role not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        permissions = _svc_list_catalog_permissions()
        current_permission_keys: List[str] = []
        for entry in role.permissions:
            current_permission_keys.append(entry.id)

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.role_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["role"] = role
        context["permissions"] = permissions
        context["current_permission_keys"] = current_permission_keys
        response = _render(
            template_name="config/roles/edit.html",
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


def handle_role_delete(request: Request) -> Response:
    """
        ``POST /admin/roles/{role_id}/delete`` -- delete a custom
        role and every binding referencing it, redirect to the list
        with a flash reporting how many users lost the role.
        Built-in roles and the last role granting the admin UI are
        refused.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        role_id = str(request.path_params.get("role_id", ""))
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.role_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        role = _svc_get_role(db_session=db_session, role_id=role_id)
        if role is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message="Role not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        role_name = role.name
        exc_classes = _roles_exception_classes()

        try:
            removed_count = _svc_delete_role(
                db_session=db_session, role_id=role_id, actor_user_id=auth.user_id
            )
            if removed_count == 1:
                consequence = "1 user lost this role."
            else:
                consequence = "{} users lost this role.".format(
                    removed_count
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message='Role "{}" deleted. {}'.format(
                    role_name, consequence
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except exc_classes["AdminNotFoundError"]:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message="Role not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response
        except exc_classes["BuiltinRoleProtectedError"] as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "config.role_detail", role_id=role_id
                ),
                message=getattr(exc, "message", str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
        except exc_classes["LastAdminRoleError"] as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "config.role_detail", role_id=role_id
                ),
                message=getattr(exc, "message", str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message="Error deleting role: {}".format(str(exc)),
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
    "config.role_list": handle_role_list,
    "config.role_create": handle_role_create,
    "config.role_detail": handle_role_detail,
    "config.role_edit": handle_role_edit,
    "config.role_delete": handle_role_delete,
}


def register_roles_routes(*, app: Any) -> None:
    """
        Attach the role-management routes to a webworks app and
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
    "register_roles_routes",
    "handle_role_list",
    "handle_role_create",
    "handle_role_detail",
    "handle_role_edit",
    "handle_role_delete",
]
