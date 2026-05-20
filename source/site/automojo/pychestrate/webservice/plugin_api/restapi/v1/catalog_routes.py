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

These endpoints are read-only views over in-process state. Per
``specs/8-plugin-api`` Operations §, every read endpoint in the
plugin-api domain is RBAC-gated on ``system:plugin_api.read``; the
handlers consume the request-scoped session the middleware attaches
to evaluate that permission.

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


from datetime import datetime, timezone
from typing import Any, Dict, Optional

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
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


CATALOG_PATH = "/plugin-api/_meta"
EXT_LISTING_PATH = "/ext"

PLUGIN_API_READ_PERMISSION_KEY = "system:plugin_api.read"


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks problem
        response so the RBAC gate can signal a 401/403 once and the
        top-level handler converts it at the boundary.
    """

    def __init__(self, response: Response) -> None:
        super().__init__("problem abort")
        self.response: Response = response
        return


def _abort_problem(
        *,
        request: Request,
        status: int,
        detail: str,
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _require_plugin_api_read(request: Request) -> None:
    """
        Require the calling principal to hold
        ``system:plugin_api.read``. The plugin-api meta surface is
        read-only but still operator-gated per
        ``specs/8-plugin-api``.

        :param request: Incoming webworks request.

        :returns: None.
        :raises: _ProblemAbort on missing session / principal /
                 permission.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )

    principal = getattr(request, "auth_principal", None)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )

    now = datetime.now(timezone.utc)
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=PLUGIN_API_READ_PERMISSION_KEY,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(
                PLUGIN_API_READ_PERMISSION_KEY
            ),
            extensions={"required_permission": PLUGIN_API_READ_PERMISSION_KEY},
        )
    return


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
        Each entry carries deprecation-window metadata
        (``deprecation_date``, ``sunset_date``). RBAC-gated on
        ``system:plugin_api.read``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying the rendered catalog,
                  or a problem response.
    """
    try:
        _require_plugin_api_read(request=request)
        catalog = plugin_api_runtime.get_active_catalog()
        body = catalog_to_jsonable(catalog=catalog)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_read_catalog_entry(request: Request) -> Response:
    """
        ``GET /api/v1/plugin-api/_meta/catalog/{protocol_name}`` — one
        catalog entry by name. Returns 404 problem+json when no
        factory protocol or resource-extension entry matches.
        RBAC-gated on ``system:plugin_api.read``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the entry dict, or
                  problem response (401/403/404).
    """
    protocol_name = request.path_params.get("protocol_name", "")
    try:
        _require_plugin_api_read(request=request)

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
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_list_mounts(request: Request) -> Response:
    """
        ``GET /api/v1/plugin-api/_meta/mounts`` — concrete extension
        routes the host has discovered. Re-runs the mount step at
        request time; the underlying ``mount_extension_routes`` is
        idempotent. RBAC-gated on ``system:plugin_api.read``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying the mount manifest as
                  a list of dicts, or a problem response.
    """
    try:
        _require_plugin_api_read(request=request)
        manifest = mount_extension_routes(extensions=None)
        body = manifest_to_jsonable(manifest=manifest)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_list_ext(request: Request) -> Response:
    """
        ``GET /api/v1/ext`` — operator-facing listing of the
        extension-contributed REST endpoints the host has discovered
        at startup. Each entry is a concrete route mounted under the
        ``/api/v1/ext/<extension_name>/...`` namespace.

        The dynamic mount itself (binding each
        :class:`RestEndpointExtension` descriptor to a live webworks
        route at startup) is a deliberate follow-up: the discovery +
        collision-validation surface (``ext_router``) is complete and
        produces the manifest exposed here, but wiring each manifest
        row to ``app.attach_route`` against the running dispatcher is
        scoped separately. This listing is the stable observability
        surface that the dynamic-mount work will populate.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, total,
                  dynamic_mount}`` body, or a problem response.
    """
    try:
        _require_plugin_api_read(request=request)
        manifest = mount_extension_routes(extensions=None)
        items = manifest_to_jsonable(manifest=manifest)
        body = {
            "items": items,
            "total": len(items),
            "dynamic_mount": "deferred",
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
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

    # Operator-facing extension-endpoint listing. The /api/v1/ext/...
    # namespace is reserved by ext_router for dynamically-mounted
    # extension routes; this listing exposes the discovered manifest
    # while the dynamic mount remains a scoped follow-up.
    app.attach_route(
        version_prefix + EXT_LISTING_PATH, methods=["GET"]
    )(handle_list_ext)

    return


__all__ = [
    "CATALOG_PATH",
    "EXT_LISTING_PATH",
    "PLUGIN_API_READ_PERMISSION_KEY",
    "register_catalog_routes",
    "handle_list_catalog",
    "handle_read_catalog_entry",
    "handle_list_mounts",
    "handle_list_ext",
]
