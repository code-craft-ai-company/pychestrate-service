"""
.. module:: webinterface.blueprints.resources.routes_tags
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources/tags
               (E4 slice -- tag list).

.. moduleauthor:: Code Craft AI LLC

The single tag-list route served under the resources blueprint:

* ``GET /resources/tags`` -- list every tag known to the
                             ResourceManager.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    _attach_session_to_response,
    _build_default_template_context,
    _render,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_PATH,
    _resources_permission_flags,
    _wrap_resources_handler_in_shell,
    _build_page_window,
    _calculate_total_pages,
)


_ROUTE_TABLE = (
    ("resources.tag_list", "/tags", ("GET",)),
)


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
    rtnval = {"page": page, "per_page": per_page}
    return rtnval


# ---------------------------------------------------------------------------
# Lazy-import builder seam
# ---------------------------------------------------------------------------


def _build_resource_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ResourceManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceManager,
    )
    rtnval = ResourceManager(db_session)
    return rtnval


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handle_tag_list(request: Request) -> Response:
    """
        ``GET /resources/tags`` -- paginated tag list with an
        optional ``?search=`` name filter.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]
        search = (request.query_params.get("search", "") or "").strip()

        list_kwargs: Dict[str, Any] = {
            "offset": offset,
            "limit": params["per_page"],
        }
        if len(search) > 0:
            list_kwargs["search"] = search

        resource_manager = _build_resource_manager(db_session=db_session)
        tags_response = resource_manager.list_tags(**list_kwargs)
        tags = tags_response.tags

        total_pages = _calculate_total_pages(
            total=tags_response.total,
            per_page=params["per_page"],
        )
        page_window = _build_page_window(
            page=params["page"], total_pages=total_pages
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.tag_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["tags"] = tags
        context["search"] = search
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["page_window"] = page_window
        response = _render(
            template_name="resources/tags/list.html",
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
    "resources.tag_list": handle_tag_list,
}


def register_tags_routes(*, app: Any) -> None:
    """
        Attach the tag list route to a webworks app and register
        its endpoint name with the url_for shim.
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
    "register_tags_routes",
    "handle_tag_list",
]
