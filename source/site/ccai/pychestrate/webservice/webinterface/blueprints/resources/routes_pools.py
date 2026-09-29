"""
.. module:: webinterface.blueprints.resources.routes_pools
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources/pools
               (E2 slice -- resource-pool management).

.. moduleauthor:: Code Craft AI LLC

The four resource-pool routes served under the resources
blueprint:

* ``GET  /resources/pools``                   -- list.
* ``GET  /resources/pools/create``            -- form.
* ``POST /resources/pools/create``            -- create
                                                 (admin-gated).
* ``GET  /resources/pools/{pool_id}``         -- detail (with
                                                 the resources
                                                 in the pool).
* ``POST /resources/pools/{pool_id}/delete``  -- delete
                                                 (admin-gated).

The IP pool surface ports separately in
:mod:`webinterface.blueprints.resources.routes_ip_pools`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

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
    MultiFormView,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_MAX_PER_PAGE,
    RESOURCES_PATH,
    _ADMIN_PERMISSION,
    _denial_message,
    _resources_permission_flags,
    _wrap_resources_handler_in_shell,
    _build_page_window,
    _calculate_total_pages,
    _describe_resource_manager_error,
    _resource_field_errors,
)


_LOGGER = logging.getLogger("pychestrate.ui.resources.pools")


_ROUTE_TABLE = (
    ("resources.pool_list", "/pools", ("GET",)),
    ("resources.pool_create", "/pools/create", ("GET", "POST")),
    ("resources.pool_detail", "/pools/{pool_id}", ("GET",)),
    (
        "resources.pool_delete",
        "/pools/{pool_id}/delete",
        ("POST",),
    ),
    (
        "resources.pool_add_resources",
        "/pools/{pool_id}/add-resources",
        ("POST",),
    ),
    (
        "resources.pool_move_resources",
        "/pools/{pool_id}/move-resources",
        ("POST",),
    ),
)

#: How many resources outside the pool the "Add existing resources" list offers.
ADDABLE_RESOURCES_LIMIT: int = 200


_ADMIN_PERMISSION = "system:resources.manage"


# ---------------------------------------------------------------------------
# Lazy-import builder seams
# ---------------------------------------------------------------------------


def _build_resource_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ResourceManager`. Defined locally
        (rather than imported from ``resources.routes``) so each
        per-feature module owns its own test-patch surface --
        cross-module ``from .routes import _build_*`` static
        bindings would freeze the original when one feature's
        test triggers a cascade import while another feature's
        test has the source patched.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceManager,
    )
    rtnval = ResourceManager(db_session)
    return rtnval


def _build_pool_create_request(
        *, name: str, description: str
    ) -> Any:
    """
        Construct a :class:`ResourcePoolCreateRequest`.
        Lazy-imports.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourcePoolCreateRequest,
    )
    rtnval = ResourcePoolCreateRequest(
        name=name, description=description
    )
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _coerce_int(*, raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        return None
    return rtnval


def _coerce_int_with_default(*, raw: Any, default: int) -> int:
    parsed = _coerce_int(raw=raw)
    if parsed is None:
        return default
    return parsed


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 20
    ) -> Dict[str, Any]:
    page = _coerce_int_with_default(
        raw=request.query_params.get("page", None), default=1
    )
    if page < 1:
        page = 1
    per_page = _coerce_int_with_default(
        raw=request.query_params.get("per_page", None),
        default=default_per_page,
    )
    if per_page < 1:
        per_page = default_per_page
    if per_page > RESOURCES_MAX_PER_PAGE:
        per_page = RESOURCES_MAX_PER_PAGE
    rtnval = {"page": page, "per_page": per_page}
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_pool_list(request: Request) -> Response:
    """
        ``GET /resources/pools``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        resource_manager = _build_resource_manager(db_session=db_session)
        pools_response = resource_manager.list_pools(
            auth.user_id, offset=offset, limit=params["per_page"]
        )
        pools = pools_response.pools

        total_pages = _calculate_total_pages(
            total=pools_response.total,
            per_page=params["per_page"],
        )
        page_window = _build_page_window(
            page=params["page"], total_pages=total_pages
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.pool_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["pools"] = pools
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["total"] = pools_response.total
        context["page_window"] = page_window
        response = _render(
            template_name="resources/pools/list.html",
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


def handle_pool_create(request: Request) -> Response:
    """
        ``GET /resources/pools/create`` /
        ``POST /resources/pools/create`` (admin-gated).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_message=_denial_message(action="create a resource pool"),
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        method = request.method.upper()
        resource_manager = _build_resource_manager(db_session=db_session)

        if method == "GET":
            flashes = flash.consume_flashes(session=auth.session)
            context = _build_default_template_context(
                session=auth.session,
                request_endpoint="resources.pool_create",
                flashes=flashes,
                csrf_token=auth.csrf_token,
            )
            context.update(_resources_permission_flags(auth=auth))
            context["form_data"] = None
            response = _render(
                template_name="resources/pools/create.html",
                context=context,
            )
            _attach_session_to_response(
                response=response, session=auth.session
            )
            return response

        # POST
        single_form = _parse_form_or_empty(request=request)
        # MultiFormView wraps the multi-value-aware view of the
        # body so the template's form_data shape ports unchanged.
        from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (  # noqa: E402
            _parse_form_multi,
        )
        multi_form = _parse_form_multi(request=request)
        form_view = MultiFormView(data=multi_form)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.pool_create"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        description = str(single_form.get("description", "")).strip()
        errors: Dict[str, str] = {}

        try:
            create_request = _build_pool_create_request(
                name=name, description=description
            )
            pool = resource_manager.create_pool(
                create_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.pool_detail", pool_id=pool.id
                ),
                message='Pool "{}" created successfully.'.format(name),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            errors = _resource_field_errors(exc=exc)
            if "name" not in errors:
                errors = {}
            if len(errors) == 0:
                message = _describe_resource_manager_error(exc=exc)
                if message is None:
                    _LOGGER.exception("Unexpected error creating pool")
                    message = (
                        "An unexpected error occurred while creating the"
                        " pool. The problem has been logged."
                    )
                flash.add_flash(
                    session=auth.session,
                    message=message,
                    category=flash.CATEGORY_ERROR,
                )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.pool_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["form_data"] = form_view
        context["errors"] = errors
        context["error_labels"] = {"name": "Pool Name", "description": "Description"}
        response = _render(
            template_name="resources/pools/create.html",
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


def handle_pool_detail(request: Request) -> Response:
    """
        ``GET /resources/pools/{pool_id}`` -- detail page with the
        list of resources in the pool.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        pool_id = _coerce_int(
            raw=request.path_params.get("pool_id", None)
        )
        if pool_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.pool_list"),
                message="Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        pool = resource_manager.get_pool(pool_id)
        if pool is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.pool_list"),
                message="Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        resources_response = resource_manager.list_resources(
            pool_id=pool_id, offset=offset, limit=params["per_page"]
        )
        resources = resources_response.resources

        total_pages = _calculate_total_pages(
            total=resources_response.total,
            per_page=params["per_page"],
        )
        page_window = _build_page_window(
            page=params["page"], total_pages=total_pages
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.pool_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["pool"] = pool
        context["resources"] = resources
        context["resource_total"] = resources_response.total
        context["addable_resources"] = []
        context["other_pools"] = []
        if context["can_manage"] is True:
            everything = resource_manager.list_resources(limit=ADDABLE_RESOURCES_LIMIT).resources
            context["addable_resources"] = [
                item for item in everything if getattr(item, "pool_id", None) != pool_id
            ]
            context["other_pools"] = [
                item for item in resource_manager.list_pools(auth.user_id).pools if item.id != pool_id
            ]
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["page_window"] = page_window
        response = _render(
            template_name="resources/pools/detail.html",
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


def handle_pool_delete(request: Request) -> Response:
    """
        ``POST /resources/pools/{pool_id}/delete`` (admin-gated).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_message=_denial_message(action="delete a resource pool"),
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        pool_id = _coerce_int(
            raw=request.path_params.get("pool_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("resources.pool_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if pool_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.pool_list"),
                message="Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        try:
            resource_manager.delete_pool(pool_id, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.pool_list"),
                message="Pool deleted successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_resource_manager_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error deleting pool %s", pool_id
                )
                message = (
                    "An unexpected error occurred while deleting the"
                    " pool. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.pool_list"),
                message=message,
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


def _pool_gate(*, auth: Any, action: str, pool_id: Optional[int]) -> Optional[Response]:
    """
        The redirect for someone who may not manage pools, naming the
        action, or ``None`` for a manager.
    """
    rtnval = _require_permission_or_redirect(
        auth=auth,
        permission=_ADMIN_PERMISSION,
        deny_message=_denial_message(action=action),
        deny_redirect_url=_url_for_module.url_for("resources.pool_list"),
    )
    return rtnval


def _pool_action_preamble(
        *, request: Request, auth: Any, action: str
    ) -> Any:
    """
        The checks every pool action shares: the permission, the CSRF
        token and the pool id. Returns ``(response, pool_id, form)`` where
        ``response`` is a redirect to send back instead of acting, or
        ``None`` to go on.
    """
    deny = _pool_gate(auth=auth, action=action, pool_id=None)
    if deny is not None:
        return (deny, None, None)
    single_form = _parse_form_or_empty(request=request)
    csrf_redirect = auth_guard.enforce_csrf_or_redirect(
        form=single_form,
        session=auth.session,
        fallback_url=_url_for_module.url_for("resources.pool_list"),
    )
    if csrf_redirect is not None:
        _attach_session_to_response(response=csrf_redirect, session=auth.session)
        return (csrf_redirect, None, None)
    pool_id = _coerce_int(raw=request.path_params.get("pool_id", None))
    if pool_id is None:
        return (
            _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.pool_list"),
                message="Pool not found.",
                category=flash.CATEGORY_ERROR,
            ),
            None,
            None,
        )
    return (None, pool_id, single_form)


def handle_pool_add_resources(request: Request) -> Response:
    """
        ``POST /resources/pools/{pool_id}/add-resources`` (manager) --
        move the chosen existing resources into this pool. A resource
        whose name is already in the pool stays where it is, and the
        message names it.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        early, pool_id, _single = _pool_action_preamble(
            request=request, auth=auth, action="add resources to a resource pool",
        )
        if early is not None:
            return early
        chosen = [
            _coerce_int(raw=value) for value in _parse_form_multi(request=request).get("resource_ids", [])
        ]
        resource_ids = [value for value in chosen if value is not None]
        detail_url = _url_for_module.url_for("resources.pool_detail", pool_id=pool_id)
        if len(resource_ids) == 0:
            return _redirect_with_flash(
                session=auth.session, url=detail_url,
                message="Choose at least one resource to add.", category=flash.CATEGORY_ERROR,
            )
        resource_manager = _build_resource_manager(db_session=db_session)
        moved = 0
        refused: List[str] = []
        for resource_id in resource_ids:
            try:
                resource_manager.assign_resource_to_pool(resource_id, pool_id, auth.user_id)
                moved += 1
            except Exception as exc:
                message = _describe_resource_manager_error(exc=exc)
                if message is None:
                    _LOGGER.exception("Unexpected error adding resource %s to pool %s", resource_id, pool_id)
                    message = "An unexpected error occurred. The problem has been logged."
                refused.append(message)
        if moved > 0:
            flash.add_flash(
                session=auth.session,
                message="Added {} resource{} to the pool.".format(moved, "" if moved == 1 else "s"),
                category=flash.CATEGORY_SUCCESS,
            )
        for message in refused:
            flash.add_flash(session=auth.session, message=message, category=flash.CATEGORY_ERROR)
        return _plain_redirect(auth=auth, url=detail_url)
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _plain_redirect(*, auth: Any, url: str) -> Response:
    """
        Redirect (303) with the session cookie re-signed, after the
        messages have already been queued as flashes.
    """
    from ccai.webworks.routing.response import RedirectResponse  # noqa: E402

    response = RedirectResponse(url=url, status_code=303)
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_pool_move_resources(request: Request) -> Response:
    """
        ``POST /resources/pools/{pool_id}/move-resources`` (manager) --
        move every resource of this pool into another, so the pool can
        be deleted without deleting its devices. Nothing moves unless
        every resource can (a name already in the target stops it).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        early, pool_id, single_form = _pool_action_preamble(
            request=request, auth=auth, action="move resources between pools",
        )
        if early is not None:
            return early
        detail_url = _url_for_module.url_for("resources.pool_detail", pool_id=pool_id)
        target = _coerce_int(raw=single_form.get("target_pool_id", None))
        if target is None:
            return _redirect_with_flash(
                session=auth.session, url=detail_url,
                message="Choose the pool to move the resources to.", category=flash.CATEGORY_ERROR,
            )
        resource_manager = _build_resource_manager(db_session=db_session)
        try:
            moved = resource_manager.move_pool_resources(pool_id, target, auth.user_id)
        except Exception as exc:
            message = _describe_resource_manager_error(exc=exc)
            if message is None:
                _LOGGER.exception("Unexpected error moving the resources of pool %s", pool_id)
                message = "An unexpected error occurred. The problem has been logged."
            return _redirect_with_flash(
                session=auth.session, url=detail_url, message=message, category=flash.CATEGORY_ERROR,
            )
        return _redirect_with_flash(
            session=auth.session, url=detail_url,
            message="Moved {} resource{}. The pool is empty and can be deleted.".format(
                moved, "" if moved == 1 else "s"
            ),
            category=flash.CATEGORY_SUCCESS,
        )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "resources.pool_list": handle_pool_list,
    "resources.pool_create": handle_pool_create,
    "resources.pool_detail": handle_pool_detail,
    "resources.pool_delete": handle_pool_delete,
    "resources.pool_add_resources": handle_pool_add_resources,
    "resources.pool_move_resources": handle_pool_move_resources,
}


def register_pools_routes(*, app: Any) -> None:
    """
        Attach the pool routes to a webworks app and register
        their endpoint names with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = RESOURCES_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_resources_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "handle_pool_add_resources",
    "handle_pool_move_resources",
    "register_pools_routes",
    "handle_pool_list",
    "handle_pool_create",
    "handle_pool_detail",
    "handle_pool_delete",
]
