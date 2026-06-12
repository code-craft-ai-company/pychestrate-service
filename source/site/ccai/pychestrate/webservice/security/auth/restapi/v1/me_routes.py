"""
.. module:: security.auth.restapi.v1.me_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/me.

.. moduleauthor:: Code Craft AI LLC

Self-introspection endpoints for the currently-authenticated
principal:

* ``GET /api/v1/me/permissions`` -- list the permission keys the
  current session holds. The site shell (9-site-shell) calls
  this on every full navigation to recompute sidebar visibility
  per Requirement 5 of 1-site-shell. The endpoint is a UX
  signal -- the security boundary remains the per-action
  permission check enforced by each owning feature's
  server-side route guard.
* ``GET /api/v1/me/navigation`` -- the permission-filtered
  central navigation manifest. The site shell renders its full
  sidebar from this on every route so the sidebar is complete
  even on the bare ``/`` route (which loads no feature bundle).
  See :mod:`webinterface.site_shell.nav_manifest`. Like
  ``me/permissions`` this is a UX signal, not a security
  boundary.

Returns HTTP 401 with an RFC 7807 problem document when the
request carries no authenticated session.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import Any, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator
from ccai.pychestrate.webservice.security.rbac.catalog import (
    load_catalog_from_registry,
)
from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (
    build_navigation_manifest,
)


ME_PATH = "/me"


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session attached by
        :class:`PychestrateSessionMiddleware`, or ``None`` when
        no middleware has populated it.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_auth_principal(request: Request) -> Optional[Any]:
    """
        Return the ``AuthPrincipal`` attached to the request by
        the session middleware, or ``None`` when the request is
        anonymous.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _build_unauthorized_response(*, request: Request) -> Response:
    """
        Build a 401 problem document for an unauthenticated
        request.

        :param request: Incoming webworks request.

        :returns: Webworks Response (401).
    """
    rtnval = problem_response_for_http_status(
        status=401,
        detail="Authentication required",
        instance=request.path,
    )
    return rtnval


def _evaluate_held_system_permissions(
        *,
        db_session: Any,
        principal: Any
    ) -> List[str]:
    """
        Evaluate which system-scoped permission keys the supplied
        principal effectively holds.

        Walks the system-scoped half of the in-tree permission
        catalog and runs :func:`rbac_evaluator.check_permission`
        for each key. A single permission evaluation failure is
        treated as not-held and does not abort the walk.

        :param db_session: Request-scoped db session.
        :param principal: The authenticated ``AuthPrincipal``.

        :returns: Sorted list of held system-scoped permission
                  keys.
    """
    catalog = load_catalog_from_registry()
    now = datetime.now(timezone.utc)

    held_keys: List[str] = []
    for permission_key in sorted(catalog.permissions.keys()):
        descriptor = catalog.permissions[permission_key]
        if descriptor.namespace != "system":
            continue

        try:
            decision = rbac_evaluator.check_permission(
                db_session=db_session,
                principal=principal,
                permission_key=permission_key,
                now=now,
            )
        except Exception:
            # A single permission evaluation failure must not
            # blow up the whole introspection call. Treat as
            # not-held and continue.
            continue

        if decision.allowed is True:
            held_keys.append(permission_key)

    return held_keys


def handle_list_my_permissions(request: Request) -> Response:
    """
        ``GET /api/v1/me/permissions`` -- return the system-scoped
        permission keys held by the current session.

        Response shape::

            {"permissions": ["system:users.write",
                             "system:ui.admin.view", ...]}

        The list is the intersection of the in-tree permission
        catalog (loaded from registered ``PermissionExtension``
        subclasses) and the principal's effective system-scoped
        bindings as evaluated by
        :func:`rbac_evaluator.check_permission`. Project-scoped
        permissions (``project:<id>:<action>``) are not enumerated
        here -- per 9-site-shell design, project-scoped UX gating
        happens elsewhere.

        Unauthenticated requests return HTTP 401 with an RFC
        7807 problem document.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with ``{"permissions":
                  [...]}`` on success; 401 problem response on
                  unauthenticated requests.
    """
    principal = _resolve_auth_principal(request=request)
    if principal is None:
        rtnval = _build_unauthorized_response(request=request)
        return rtnval

    db_session = _resolve_db_session(request=request)
    if db_session is None:
        rtnval = problem_response_for_http_status(
            status=503,
            detail="Request-scoped db_session not configured",
            instance=request.path,
        )
        return rtnval

    # Only the system-scoped half of the catalog is enumerated --
    # ``project:<id>:<action>`` keys live in
    # ``ProjectPermissionExtension`` and would require a
    # project_id to evaluate, which this self-introspection
    # endpoint does not carry.
    held_keys = _evaluate_held_system_permissions(
        db_session=db_session,
        principal=principal,
    )

    body = {"permissions": held_keys}
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


def handle_get_my_navigation(request: Request) -> Response:
    """
        ``GET /api/v1/me/navigation`` -- return the central
        navigation manifest permission-filtered against the
        current session.

        Response shape::

            {"groups": [
                {"group_id": "orchestration",
                 "label": "Orchestration",
                 "icon": null,
                 "required_permissions": [],
                 "entries": [
                     {"entry_id": "orchestration.runs",
                      "label": "Runs",
                      "route": "/runs",
                      "icon": null,
                      "required_permissions": ["system:runs.read"]},
                     ...]},
                ...]}

        The site shell renders its full sidebar from this manifest
        on every route, so the sidebar is complete even on the
        bare ``/`` route where no feature bundle is loaded. The
        manifest is the authoritative source of truth for sidebar
        navigation (see
        :mod:`webinterface.site_shell.nav_manifest`). This is a UX
        signal -- the security boundary remains the per-action
        permission check enforced by each owning feature's
        server-side route guard.

        Unauthenticated requests return HTTP 401 with an RFC 7807
        problem document.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the filtered manifest
                  on success; 401 problem response on
                  unauthenticated requests.
    """
    principal = _resolve_auth_principal(request=request)
    if principal is None:
        rtnval = _build_unauthorized_response(request=request)
        return rtnval

    db_session = _resolve_db_session(request=request)
    if db_session is None:
        rtnval = problem_response_for_http_status(
            status=503,
            detail="Request-scoped db_session not configured",
            instance=request.path,
        )
        return rtnval

    held_keys = _evaluate_held_system_permissions(
        db_session=db_session,
        principal=principal,
    )

    body = build_navigation_manifest(held_permissions=held_keys)
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


def register_me_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the self-introspection routes to a webworks
        application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + ME_PATH
    app.attach_route(base + "/permissions", methods=["GET"])(
        handle_list_my_permissions
    )
    app.attach_route(base + "/navigation", methods=["GET"])(
        handle_get_my_navigation
    )
    return


__all__ = [
    "ME_PATH",
    "register_me_routes",
    "handle_list_my_permissions",
    "handle_get_my_navigation",
]
