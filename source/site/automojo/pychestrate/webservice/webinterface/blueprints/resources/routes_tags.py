"""
.. module:: webinterface.blueprints.resources.routes_tags
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources/tags
               (E4 slice -- tag list).

.. moduleauthor:: Automation Mojo LLC

The single tag-list route served under the resources blueprint:

* ``GET /resources/tags`` -- list every tag known to the
                             ResourceManager.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import (
    HTMLResponse,
    Response,
)

from automojo.pychestrate.webservice.webinterface.foundation import (
    flash,
    url_for as _url_for_module,
)
from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
    _attach_session_to_response,
    _build_default_template_context,
    _render,
    _resolve_authenticated_request,
)
from automojo.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_PATH,
)


_ROUTE_TABLE = (
    ("resources.tag_list", "/tags", ("GET",)),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seam
# ---------------------------------------------------------------------------


def _build_resource_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ResourceManager`. Lazy-imports.
    """
    from automojo.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceManager,
    )
    rtnval = ResourceManager(db_session)
    return rtnval


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handle_tag_list(request: Request) -> Response:
    """
        ``GET /resources/tags`` -- list of every known tag.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        resource_manager = _build_resource_manager(db_session=db_session)
        tags = resource_manager.list_tags().tags

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.tag_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["tags"] = tags
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
        app.attach_route(full_path, methods=list(methods))(handler)
    return


__all__ = [
    "register_tags_routes",
    "handle_tag_list",
]
