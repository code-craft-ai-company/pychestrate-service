"""
.. module:: plugin_api.restapi.v1.catalog_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/plugin-api/_meta/*.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This module is the webworks-native
REST surface for the plugin-api meta endpoints, replacing the
flask_restx ``catalog_controller`` next to it.

Three read-only routes mirror the flask_restx controller's matrix:

* ``GET /api/v1/plugin-api/_meta/catalog``
  — full published-surface catalog (factory protocols + resource
  extensions).
* ``GET /api/v1/plugin-api/_meta/catalog/{protocol_name}``
  — single catalog entry by protocol or resource-extension name.
* ``GET /api/v1/plugin-api/_meta/mounts``
  — concrete extension routes the host has discovered at startup.

These endpoints are read-only views over in-process state — no
SQLAlchemy session, no actor lookup, no auth gate. The session
middleware still attaches a session to the request (every
``/api/v1/`` path is in scope), but the handlers do not consume it.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`. The detail endpoint's 404
upgrades the flask_restx ``ns.abort(404, ...)`` (which produced a
``{"message": "..."}`` body) to a documented problem document with
the protocol name carried as an extension member.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.extensions.ext_router import (
    manifest_to_jsonable,
    mount_extension_routes,
)
from automojo.pychestrate.webservice.plugin_api import runtime as plugin_api_runtime
from automojo.pychestrate.webservice.plugin_api.catalog_builder import (
    catalog_to_jsonable,
)


CATALOG_PATH = "/plugin-api/_meta"


def _problem_404(*, request: Request, protocol_name: str) -> Response:
    """
        Build the documented 404 problem response for an unknown
        ``protocol_name`` lookup. Carries the protocol name as an
        extension member so wire consumers can correlate the error
        without re-parsing the detail string.

        :param request: Incoming webworks request (used for the
                        ``instance`` URI).
        :param protocol_name: The unknown name the caller asked for.

        :returns: webworks problem-json response.
    """
    rtnval = problem_response_for_http_status(
        status=404,
        detail="Plugin API catalog entry not found: {}".format(protocol_name),
        instance=request.path,
        extensions={"protocol_name": protocol_name},
    )
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_list_catalog(request: Request) -> Response:
    """
        ``GET /api/v1/plugin-api/_meta/catalog`` — full published
        surface as ``{"factory_protocols": [...], "resource_extensions": [...]}``.

        :param request: Incoming webworks request (unused).

        :returns: JSON response (200) carrying the rendered catalog.
    """
    catalog = plugin_api_runtime.get_active_catalog()
    body = catalog_to_jsonable(catalog=catalog)
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


def handle_read_catalog_entry(request: Request) -> Response:
    """
        ``GET /api/v1/plugin-api/_meta/catalog/{protocol_name}`` — one
        catalog entry by name. Returns 404 problem+json when no
        factory protocol or resource-extension entry matches.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the entry dict, or
                  problem response (404).
    """
    protocol_name = request.path_params.get("protocol_name", "")

    catalog = plugin_api_runtime.get_active_catalog()
    rendered = catalog_to_jsonable(catalog=catalog)

    for entry_dict in rendered["factory_protocols"]:
        if entry_dict["name"] == protocol_name:
            rtnval: Response = JSONResponse(
                content=entry_dict, status_code=200
            )
            return rtnval

    for entry_dict in rendered["resource_extensions"]:
        if entry_dict["name"] == protocol_name:
            rtnval = JSONResponse(content=entry_dict, status_code=200)
            return rtnval

    rtnval = _problem_404(
        request=request, protocol_name=protocol_name
    )
    return rtnval


def handle_list_mounts(request: Request) -> Response:
    """
        ``GET /api/v1/plugin-api/_meta/mounts`` — concrete extension
        routes the host has discovered. Re-runs the mount step at
        request time (mirrors the flask controller's behavior); the
        underlying ``mount_extension_routes`` is idempotent.

        :param request: Incoming webworks request (unused).

        :returns: JSON response (200) carrying the mount manifest as
                  a list of dicts.
    """
    manifest = mount_extension_routes(extensions=None)
    body = manifest_to_jsonable(manifest=manifest)
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_catalog_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the plugin-api meta routes to a webworks application.

        Called from :func:`pychestrate_website_main` -
        :func:`register_service_extensions` before
        ``app.startup``. Routes are queued until the
        infrastructure-ready phase and flushed there.

        Note that the fixed ``/catalog`` route is registered BEFORE
        the ``/catalog/{protocol_name}`` parameterized route. The
        webworks router resolves overlapping patterns by
        registration order; declaring the fixed path first avoids
        ``GET /api/v1/plugin-api/_meta/catalog`` being routed to
        :func:`handle_read_catalog_entry` with a path param of an
        empty string.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + CATALOG_PATH

    app.attach_route(base + "/catalog", methods=["GET"])(handle_list_catalog)
    app.attach_route(
        base + "/catalog/{protocol_name}", methods=["GET"]
    )(handle_read_catalog_entry)
    app.attach_route(base + "/mounts", methods=["GET"])(handle_list_mounts)

    return


__all__ = [
    "CATALOG_PATH",
    "register_catalog_routes",
    "handle_list_catalog",
    "handle_read_catalog_entry",
    "handle_list_mounts",
]
