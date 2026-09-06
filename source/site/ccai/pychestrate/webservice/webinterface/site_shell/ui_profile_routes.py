"""
.. module:: webinterface.site_shell.ui_profile_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST surface for the deployment UI profile (9-ui-profiles).

.. moduleauthor:: Code Craft AI LLC

* ``GET /api/v1/admin/ui-profile`` -- the deployment surfaces plus the
  count of navigation entries each surface governs
  (``system:ui.profile.manage``).
* ``PUT /api/v1/admin/ui-profile`` -- body ``{"surfaces": [...]}``;
  422 on an unknown surface or an empty list.

Both answer RFC 7807 problem documents on failure.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator
from ccai.pychestrate.webservice.webinterface.site_shell import ui_profile as _ui_profile
from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (
    governed_entry_counts,
)


_LOGGER = logging.getLogger("pychestrate.ui_profile.routes")

UI_PROFILE_MANAGE_PERMISSION_KEY: str = "system:ui.profile.manage"
ADMIN_UI_PROFILE_PATH: str = "/admin/ui-profile"


def _problem(*, request: Request, status: int, detail: str, extensions: Optional[Dict[str, Any]] = None) -> Response:
    rtnval = problem_response_for_http_status(
        status=status, detail=detail, instance=request.path, extensions=extensions,
    )
    return rtnval


def _authorize(*, request: Request) -> Optional[Response]:
    """
        Return a problem response when the caller may not manage the
        profile, else ``None``.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        rtnval = _problem(request=request, status=503, detail="Request-scoped db_session not configured")
        return rtnval
    principal = getattr(request, "auth_principal", None)
    if principal is None:
        rtnval = _problem(request=request, status=401, detail="Authentication required.")
        return rtnval
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=UI_PROFILE_MANAGE_PERMISSION_KEY,
        now=datetime.now(timezone.utc),
    )
    if decision.allowed is False:
        rtnval = _problem(
            request=request, status=403,
            detail="Permission denied: {}".format(UI_PROFILE_MANAGE_PERMISSION_KEY),
            extensions={"required_permission": UI_PROFILE_MANAGE_PERMISSION_KEY},
        )
        return rtnval
    return None


def _body(*, db_session: Any) -> Dict[str, Any]:
    deployment = _ui_profile.resolve_deployment_surfaces(db_session=db_session, use_cache=False)
    profile = _ui_profile.build_profile(deployment=deployment)
    rtnval = {
        "surfaces": profile.deployment_values,
        "governed_entries": governed_entry_counts(),
        "catalog": [
            {
                "surface": s.value,
                "label": _ui_profile.SURFACE_DISPLAY[s],
                "description": _ui_profile.SURFACE_DESCRIPTIONS[s],
                "enabled": s in deployment,
            }
            for s in _ui_profile.SURFACE_ORDER
        ],
        "variable_name": _ui_profile.DEPLOYMENT_VARIABLE_NAME,
    }
    return rtnval


def handle_get_ui_profile(request: Request) -> Response:
    """
        ``GET /api/v1/admin/ui-profile``
    """
    denied = _authorize(request=request)
    if denied is not None:
        return denied
    rtnval = JSONResponse(content=_body(db_session=request.db_session), status_code=200)
    return rtnval


def handle_put_ui_profile(request: Request) -> Response:
    """
        ``PUT /api/v1/admin/ui-profile``
    """
    denied = _authorize(request=request)
    if denied is not None:
        return denied
    raw = getattr(request, "body", b"")
    if callable(raw):
        raw = raw()
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        decoded = json.loads(raw) if raw else {}
    except (ValueError, UnicodeDecodeError) as xcpt:
        rtnval = _problem(request=request, status=400, detail="Request body is not valid JSON: {}".format(xcpt))
        return rtnval
    if not isinstance(decoded, dict) or not isinstance(decoded.get("surfaces", None), list):
        rtnval = _problem(request=request, status=422, detail="Body must be {\"surfaces\": [...]}.")
        return rtnval
    principal = getattr(request, "auth_principal", None)
    actor_id = getattr(principal, "user_id", None)
    try:
        _ui_profile.set_deployment_surfaces(
            db_session=request.db_session,
            surfaces=decoded["surfaces"],
            actor_id=str(actor_id) if actor_id is not None else None,
        )
    except ValueError as xcpt:
        rtnval = _problem(
            request=request, status=422, detail=str(xcpt),
            extensions={"known_surfaces": list(_ui_profile.ALL_SURFACE_VALUES)},
        )
        return rtnval
    rtnval = JSONResponse(content=_body(db_session=request.db_session), status_code=200)
    return rtnval


def register_ui_profile_api_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the UI-profile admin REST routes to a webworks app.
    """
    path = version_prefix + ADMIN_UI_PROFILE_PATH
    app.attach_route(path, methods=["GET"])(handle_get_ui_profile)
    app.attach_route(path, methods=["PUT"])(handle_put_ui_profile)
    return


__all__ = [
    "register_ui_profile_api_routes",
    "handle_get_ui_profile",
    "handle_put_ui_profile",
    "UI_PROFILE_MANAGE_PERMISSION_KEY",
]
