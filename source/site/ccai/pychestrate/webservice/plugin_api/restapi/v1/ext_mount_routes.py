"""
.. module:: plugin_api.restapi.v1.ext_mount_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Mount extension-contributed REST routes
               (``/api/v1/ext/<ext-name>/...``) on the webworks app.

.. moduleauthor:: Code Craft AI LLC

:func:`extensions.ext_router.mount_extension_routes` discovers every
:class:`RestEndpointExtension` and validates its descriptors into a
manifest. This module binds each manifest route whose extension can serve
it (see :meth:`RestEndpointExtension.serves`) to a live webworks route.
Every request to a mounted route is checked before the extension runs:

* the caller must be authenticated (the session middleware's default-deny
  already refuses anonymous ``/api/v1`` requests; this is a second gate);
* the caller must hold every permission in the descriptor's
  ``required_permissions``;
* the extension must hold, in the sandbox authority, every capability in
  the descriptor's ``required_capabilities``. Grants are read per request,
  so a revoke takes effect at once.

An extension that raises gets a 500 problem document that does not echo
the exception; the traceback goes to the log.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import threading

from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Set, Tuple

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.extensions.ext_router import (
    MountedRoute,
    MountManifest,
    mount_extension_routes,
)
from ccai.pychestrate.webservice.extensions.sandbox.authority import (
    get_capability_authority,
)
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


_LOGGER = logging.getLogger("pychestrate.plugin_api.ext_mount")

APP_MOUNTED_ATTRIBUTE: str = "_pychestrate_extension_routes"

_MOUNT_LOCK = threading.Lock()
_MOUNTED_KEYS: Set[Tuple[str, str]] = set()
_ATTACHED: List[bool] = [False]


def _problem(*, request: Request, status: int, detail: str, extensions: Optional[dict] = None) -> Response:
    rtnval = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=str(getattr(request, "path", "")),
        extensions=extensions,
    )
    return rtnval


def build_extension_route_handler(*, route: MountedRoute) -> Callable[[Request], Response]:
    """
        Build the webworks handler for one mounted extension route.

        :param route: The manifest row to serve.

        :returns: A ``(request) -> Response`` handler.
    """
    descriptor = route.descriptor

    def _handle(request: Request) -> Response:
        principal = getattr(request, "auth_principal", None)
        if principal is None:
            return _problem(request=request, status=401, detail="Authentication required.")

        db_session = getattr(request, "db_session", None)
        if len(descriptor.required_permissions) > 0:
            if db_session is None:
                return _problem(request=request, status=503, detail="The service's database session is not available.")
            now = datetime.now(timezone.utc)
            for permission_key in descriptor.required_permissions:
                decision = rbac_evaluator.check_permission(
                    db_session=db_session, principal=principal, permission_key=permission_key, now=now,
                )
                if decision.allowed is False:
                    return _problem(
                        request=request, status=403,
                        detail="Permission denied: {}".format(permission_key),
                        extensions={"required_permission": permission_key},
                    )

        missing = sorted(
            set(descriptor.required_capabilities)
            - set(get_capability_authority().granted_for(ext_name=route.ext_name))
        )
        if len(missing) > 0:
            return _problem(
                request=request, status=403,
                detail=(
                    "The '{}' extension has not been granted the capabilities this endpoint needs: {}. "
                    "An administrator grants extension capabilities."
                ).format(route.ext_name, ", ".join(missing)),
                extensions={"missing_capabilities": missing, "ext_name": route.ext_name},
            )

        try:
            result = route.handler_class.handle_request(descriptor=descriptor, request=request)
        except Exception:  # noqa: BLE001 — an extension must not take the request down with a traceback
            _LOGGER.exception(
                "pychestrate.ext_mount.handler_failed ext=%s method=%s path=%s",
                route.ext_name, route.method, route.full_path,
            )
            return _problem(
                request=request, status=500,
                detail="The '{}' extension failed to handle the request. The error has been logged.".format(
                    route.ext_name,
                ),
            )
        if isinstance(result, Response):
            return result
        rtnval: Response = JSONResponse(content=result, status_code=200)
        return rtnval

    handler_name = "ext_{}_{}_{}".format(
        route.ext_name, route.method.lower(), route.path_suffix.strip("/").replace("/", "_") or "root",
    ).replace("-", "_")
    _handle.__name__ = handler_name
    _handle.__qualname__ = handler_name
    rtnval = _handle
    return rtnval


def attach_extension_routes(*, app: Any, manifest: Optional[MountManifest] = None) -> List[MountedRoute]:
    """
        Mount every route in ``manifest`` whose extension can serve it.
        Routes whose extension names no handler stay listed but unmounted,
        with a warning in the log.

        :param app: The webworks application (before ``startup``).
        :param manifest: The routes to mount; ``None`` discovers every
                         loaded extension.

        :returns: The routes that were mounted.
    """
    if manifest is None:
        manifest = mount_extension_routes(extensions=None)
    # Routes already bound to this app (a second call must not attach them
    # twice); other apps in the same process get their own routes.
    on_app = getattr(app, APP_MOUNTED_ATTRIBUTE, None)
    if on_app is None:
        on_app = set()
        setattr(app, APP_MOUNTED_ATTRIBUTE, on_app)
    mounted: List[MountedRoute] = []
    with _MOUNT_LOCK:
        for route in manifest.routes:
            if route.handler_class.serves(descriptor=route.descriptor) is False:
                _LOGGER.warning(
                    "pychestrate.ext_mount.not_mounted ext=%s method=%s path=%s reason=no_handler",
                    route.ext_name, route.method, route.full_path,
                )
                continue
            key = (route.method, route.full_path)
            if key in on_app:
                continue
            app.attach_route(route.full_path, methods=[route.method])(build_extension_route_handler(route=route))
            on_app.add(key)
            _MOUNTED_KEYS.add(key)
            mounted.append(route)
        _ATTACHED[0] = True
    _LOGGER.info("pychestrate.ext_mount.mounted count=%s", len(mounted))
    rtnval = mounted
    return rtnval


def is_route_mounted(*, route: MountedRoute) -> bool:
    """
        Whether ``route`` was mounted by :func:`attach_extension_routes`.

        :param route: A manifest row.

        :returns: Boolean.
    """
    with _MOUNT_LOCK:
        rtnval = (route.method, route.full_path) in _MOUNTED_KEYS
    return rtnval


def extension_routes_attached() -> bool:
    """
        Whether :func:`attach_extension_routes` has run in this process.

        :returns: Boolean.
    """
    with _MOUNT_LOCK:
        rtnval = _ATTACHED[0]
    return rtnval


def reset_extension_mounts_for_testing() -> None:
    """
        Forget every mounted route (tests build several apps per process).

        :returns: None.
    """
    with _MOUNT_LOCK:
        _MOUNTED_KEYS.clear()
        _ATTACHED[0] = False
    return
