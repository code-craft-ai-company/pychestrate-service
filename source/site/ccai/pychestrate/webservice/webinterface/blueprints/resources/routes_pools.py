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
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_PATH,
)


_ROUTE_TABLE = (
    ("resources.pool_list", "/pools", ("GET",)),
    ("resources.pool_create", "/pools/create", ("GET", "POST")),
    ("resources.pool_detail", "/pools/{pool_id}", ("GET",)),
    (
        "resources.pool_delete",
        "/pools/{pool_id}/delete",
        ("POST",),
    ),
)


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
        resource_manager = _build_resource_manager(db_session=db_session)
        pools = resource_manager.list_pools(auth.user_id).pools

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.pool_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["pools"] = pools
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
            flash.add_flash(
                session=auth.session,
                message="Error creating pool: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.pool_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["form_data"] = form_view
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

        resources = resource_manager.list_resources(
            pool_id=pool_id, limit=100
        ).resources

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.pool_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["pool"] = pool
        context["resources"] = resources
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
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.pool_list"),
                message="Error deleting pool: {}".format(str(exc)),
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
    "resources.pool_list": handle_pool_list,
    "resources.pool_create": handle_pool_create,
    "resources.pool_detail": handle_pool_detail,
    "resources.pool_delete": handle_pool_delete,
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
        app.attach_route(full_path, methods=list(methods))(handler)
    return


__all__ = [
    "register_pools_routes",
    "handle_pool_list",
    "handle_pool_create",
    "handle_pool_detail",
    "handle_pool_delete",
]
