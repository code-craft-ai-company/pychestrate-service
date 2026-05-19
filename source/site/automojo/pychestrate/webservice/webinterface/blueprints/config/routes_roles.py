"""
.. module:: webinterface.blueprints.config.routes_roles
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/roles
               (D2 slice -- role management).

.. moduleauthor:: Automation Mojo LLC

The four role-management routes ported from the flask
``config_blueprint``:

* ``GET  /config/roles``                   -- list roles.
* ``GET  /config/roles/create``            -- new-role form.
* ``POST /config/roles/create``            -- create role.
* ``GET  /config/roles/{role_id}``         -- detail page.
* ``GET  /config/roles/{role_id}/edit``    -- edit form.
* ``POST /config/roles/{role_id}/edit``    -- update role.

System roles (``role.is_system == True``) cannot be modified --
the edit handler short-circuits with an error flash and the list
template hides the Edit button.

The legacy flask handlers worked directly with the
:class:`SystemRole` and :class:`Permission` ORM classes. This
port keeps that shape but routes the lookups + commits through
small builder helpers so unit tests can patch them at the module
level without importing the source ORM (which transitively pulls
sqlalchemy + werkzeug).
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
    _wrap_admin_handler_in_shell,
)


_ROUTE_TABLE = (
    ("config.role_list", "/roles", ("GET",)),
    ("config.role_create", "/roles/create", ("GET", "POST")),
    ("config.role_detail", "/roles/{role_id}", ("GET",)),
    ("config.role_edit", "/roles/{role_id}/edit", ("GET", "POST")),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _query_all_system_roles(*, db_session: Any) -> List[Any]:
    """
        Return every :class:`SystemRole` row.

        :param db_session: Open SQLAlchemy session.

        :returns: List of SystemRole ORM rows.
    """
    from automojo.pychestrate.core.orm import SystemRole  # noqa: E402
    rtnval = db_session.query(SystemRole).all()
    return rtnval


def _query_system_role_by_id(
        *, db_session: Any, role_id: int
    ) -> Optional[Any]:
    """
        Return the :class:`SystemRole` with the supplied id, or
        ``None``.

        :param db_session: Open SQLAlchemy session.
        :param role_id: Integer role id.

        :returns: SystemRole or None.
    """
    from automojo.pychestrate.core.orm import SystemRole  # noqa: E402
    rtnval = (
        db_session.query(SystemRole)
        .filter(SystemRole.id == role_id)
        .first()
    )
    return rtnval


def _query_system_role_by_name(
        *, db_session: Any, name: str
    ) -> Optional[Any]:
    """
        Return the :class:`SystemRole` with the supplied name, or
        ``None``. Used by the create handler to detect dupes.

        :param db_session: Open SQLAlchemy session.
        :param name: Role name.

        :returns: SystemRole or None.
    """
    from automojo.pychestrate.core.orm import SystemRole  # noqa: E402
    rtnval = (
        db_session.query(SystemRole)
        .filter(SystemRole.name == name)
        .first()
    )
    return rtnval


def _query_permissions_by_ids(
        *, db_session: Any, permission_ids: List[int]
    ) -> List[Any]:
    """
        Return the :class:`Permission` rows whose ids are in
        ``permission_ids``. Returns an empty list when the input
        is empty (avoids the "IN ()" dialect quirk).
    """
    if permission_ids is None or len(permission_ids) == 0:
        return []
    from automojo.pychestrate.core.orm import Permission  # noqa: E402
    rtnval = (
        db_session.query(Permission)
        .filter(Permission.id.in_(permission_ids))
        .all()
    )
    return rtnval


def _query_all_permissions(*, db_session: Any) -> List[Any]:
    """
        Return every :class:`Permission` row.
    """
    from automojo.pychestrate.core.orm import Permission  # noqa: E402
    rtnval = db_session.query(Permission).all()
    return rtnval


def _build_system_role(
        *, name: str, description: str, is_system: bool = False
    ) -> Any:
    """
        Construct a :class:`SystemRole` ORM row (not yet added to
        the session). Lazy imports the class so tests can patch.
    """
    from automojo.pychestrate.core.orm import SystemRole  # noqa: E402
    rtnval = SystemRole(
        name=name, description=description, is_system=is_system
    )
    return rtnval


def _add_and_commit(*, db_session: Any, instance: Any) -> None:
    """
        ``db_session.add(instance); db_session.commit()`` extracted
        so tests can patch the persistence step.
    """
    db_session.add(instance)
    db_session.commit()
    return


def _commit(*, db_session: Any) -> None:
    """
        ``db_session.commit()`` extracted so tests can patch.
    """
    db_session.commit()
    return


def _rollback(*, db_session: Any) -> None:
    """
        ``db_session.rollback()`` extracted so tests can patch.
    """
    db_session.rollback()
    return


# ---------------------------------------------------------------------------
# Helpers local to this module
# ---------------------------------------------------------------------------


def _coerce_int_list(*, raw_values: List[str]) -> List[int]:
    """
        Convert form-string list to int list, dropping
        non-numeric entries.
    """
    rtnval: List[int] = []
    for value in raw_values:
        try:
            rtnval.append(int(value))
        except (TypeError, ValueError):
            continue
    return rtnval


def _coerce_role_id(*, raw: Any) -> Optional[int]:
    """
        Convert a path-param role id to int. Returns None on
        unparsable input -- the caller treats that as a 404
        equivalent.
    """
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


def handle_role_list(request: Request) -> Response:
    """
        ``GET /config/roles`` -- list every role.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        roles = _query_all_system_roles(db_session=db_session)
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
        ``GET /config/roles/create`` -- show the create-role form.
        ``POST /config/roles/create`` -- create the role.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        method = request.method.upper()

        if method == "GET":
            permissions = _query_all_permissions(db_session=db_session)
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
        permission_ids = _coerce_int_list(
            raw_values=multi_form.get("permission_ids", [])
        )

        validation_error_msg: Optional[str] = None
        if len(name) == 0:
            validation_error_msg = "Role name is required."
        else:
            existing = _query_system_role_by_name(
                db_session=db_session, name=name
            )
            if existing is not None:
                validation_error_msg = (
                    'Role "{}" already exists.'.format(name)
                )

        if validation_error_msg is not None:
            flash.add_flash(
                session=auth.session,
                message=validation_error_msg,
                category=flash.CATEGORY_ERROR,
            )
        else:
            try:
                role = _build_system_role(
                    name=name, description=description, is_system=False
                )
                if len(permission_ids) > 0:
                    permissions = _query_permissions_by_ids(
                        db_session=db_session,
                        permission_ids=permission_ids,
                    )
                    role.permissions = permissions
                _add_and_commit(db_session=db_session, instance=role)

                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for("config.role_list"),
                    message='Role "{}" created successfully.'.format(name),
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                try:
                    _rollback(db_session=db_session)
                except Exception:
                    pass
                flash.add_flash(
                    session=auth.session,
                    message="Error creating role: {}".format(str(exc)),
                    category=flash.CATEGORY_ERROR,
                )

        # Re-render the form with the submitted values.
        permissions = _query_all_permissions(db_session=db_session)
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
        ``GET /config/roles/{role_id}`` -- detail page.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        role_id = _coerce_role_id(
            raw=request.path_params.get("role_id", None)
        )
        if role_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message="Role not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        role = _query_system_role_by_id(
            db_session=db_session, role_id=role_id
        )
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
        ``GET /config/roles/{role_id}/edit`` -- edit form.
        ``POST /config/roles/{role_id}/edit`` -- apply update.
        System roles refuse the update with an error flash.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        role_id = _coerce_role_id(
            raw=request.path_params.get("role_id", None)
        )
        if role_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.role_list"),
                message="Role not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        role = _query_system_role_by_id(
            db_session=db_session, role_id=role_id
        )
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
                    message="System roles cannot be modified.",
                    category=flash.CATEGORY_ERROR,
                )
                return response

            try:
                description = str(
                    single_form.get("description", "")
                ).strip()
                permission_ids = _coerce_int_list(
                    raw_values=multi_form.get("permission_ids", [])
                )

                role.description = description
                if len(permission_ids) > 0:
                    permissions = _query_permissions_by_ids(
                        db_session=db_session,
                        permission_ids=permission_ids,
                    )
                    role.permissions = permissions
                else:
                    role.permissions = []

                _commit(db_session=db_session)

                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "config.role_detail", role_id=role_id
                    ),
                    message="Role updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                try:
                    _rollback(db_session=db_session)
                except Exception:
                    pass
                flash.add_flash(
                    session=auth.session,
                    message="Error updating role: {}".format(str(exc)),
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through after a recoverable error.
        permissions = _query_all_permissions(db_session=db_session)
        current_permission_ids: List[int] = []
        if getattr(role, "permissions", None) is not None:
            for p in role.permissions:
                current_permission_ids.append(p.id)

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.role_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["role"] = role
        context["permissions"] = permissions
        context["current_permission_ids"] = current_permission_ids
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


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "config.role_list": handle_role_list,
    "config.role_create": handle_role_create,
    "config.role_detail": handle_role_detail,
    "config.role_edit": handle_role_edit,
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
        wrapped_handler = _wrap_admin_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_roles_routes",
    "handle_role_list",
    "handle_role_create",
    "handle_role_detail",
    "handle_role_edit",
]
