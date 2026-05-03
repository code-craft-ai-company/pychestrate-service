"""
.. module:: security.rbac.restapi.v1.rbac_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/rbac.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This module replaces the flask_restx
``rbac_controller`` next to it.

Six routes mirror the flask_restx controller's M2 matrix:

* ``GET    /api/v1/rbac/permissions``
  — list the permission key catalog.
* ``GET    /api/v1/rbac/roles``
  — list registered role presets.
* ``POST   /api/v1/rbac/bindings``
  — assign a role to a principal at a scope.
* ``GET    /api/v1/rbac/bindings``
  — list bindings with optional filters.
* ``DELETE /api/v1/rbac/bindings/{binding_id}``
  — revoke a binding.
* ``POST   /api/v1/rbac/check``
  — evaluate a single permission for a principal (used by
  out-of-process integrations such as ``8-cli``).

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import Any, Optional

from automojo.errors.exceptions import SemanticError
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    AuthPrincipal,
)
from automojo.pychestrate.webservice.security.rbac import (
    binding_service,
    rbac_evaluator,
)
from automojo.pychestrate.webservice.security.rbac.binding_service import (
    BindingView,
)
from automojo.pychestrate.webservice.security.rbac.catalog import (
    load_catalog_from_registry,
)
from automojo.pychestrate.webservice.security.rbac.exceptions import (
    BindingNotFoundError,
    InvalidBindingScopeError,
    RoleNotFoundError,
)
from automojo.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
)


RBAC_PATH = "/rbac"


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition once
        and the handler can convert it to a return at the boundary.
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
        extensions: Optional[dict] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.
    """
    db_session = _resolve_db_session(request=request)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as JSON, aborting 400 on missing /
        non-dict.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request, status=400, detail="Request body must be JSON"
        )
    if not isinstance(payload, dict):
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be a JSON object",
        )

    rtnval = payload
    return rtnval


def _parse_principal_kind(raw: str) -> PrincipalKind:
    """
        Coerce a ``principal_kind`` string. Raises SemanticError on
        unknown so the caller chooses how to map it (mirrors the
        flask controller's two-step flow).

        :param raw: Raw value.

        :returns: :class:`PrincipalKind`.
        :raises: SemanticError.
    """
    try:
        rtnval = PrincipalKind(raw)
    except ValueError:
        raise SemanticError("Unknown principal_kind: {}".format(raw))
    return rtnval


def _parse_scope_kind(raw: str) -> BindingScope:
    """
        Coerce a ``scope_kind`` string. Raises SemanticError on
        unknown.

        :param raw: Raw value.

        :returns: :class:`BindingScope`.
        :raises: SemanticError.
    """
    try:
        rtnval = BindingScope(raw)
    except ValueError:
        raise SemanticError("Unknown scope_kind: {}".format(raw))
    return rtnval


def _binding_to_dict(view: BindingView) -> dict:
    """
        Render a :class:`BindingView` as the REST response dict.

        :param view: BindingView from the binding service.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "binding_id": view.binding_id,
        "role_name": view.role_name,
        "principal_kind": view.principal_kind.value,
        "principal_id": view.principal_id,
        "scope_kind": view.scope_kind.value,
        "scope_id": view.scope_id,
        "inherits_into_project": view.inherits_into_project,
        "created_at": view.created_at_iso,
        "created_by": view.created_by,
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers — catalog (no session) reads
# ---------------------------------------------------------------------------


def handle_list_permissions(request: Request) -> Response:
    """
        ``GET /api/v1/rbac/permissions`` — list the permission key
        catalog. Read-only over the in-process registry — no
        SQLAlchemy session required.

        :param request: Incoming webworks request (unused).

        :returns: JSON response (200) with the permission catalog.
    """
    catalog = load_catalog_from_registry()
    body = []
    for key in sorted(catalog.permissions.keys()):
        descriptor = catalog.permissions[key]
        body.append({
            "permission_key": descriptor.permission_key,
            "description": descriptor.description,
            "namespace": descriptor.namespace,
        })
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


def handle_list_roles(request: Request) -> Response:
    """
        ``GET /api/v1/rbac/roles`` — list registered role presets.

        :param request: Incoming webworks request (unused).

        :returns: JSON response (200) with role summaries.
    """
    catalog = load_catalog_from_registry()
    body = []
    for role_name in sorted(catalog.roles.keys()):
        grants = catalog.roles[role_name]
        body.append({
            "role_name": role_name,
            "permission_count": len(grants),
        })
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


# ---------------------------------------------------------------------------
# Handlers — bindings
# ---------------------------------------------------------------------------


def handle_create_binding(request: Request) -> Response:
    """
        ``POST /api/v1/rbac/bindings`` — assign a role to a
        principal at a scope. Returns 201 with the created
        binding's view dict.

        :param request: Incoming webworks request.

        :returns: JSON response (201), or problem response.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        try:
            principal_kind = _parse_principal_kind(
                payload.get("principal_kind", "")
            )
            scope_kind = _parse_scope_kind(payload.get("scope_kind", ""))
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"role_name": payload.get("role_name", "")},
            )

        try:
            binding = binding_service.assign_role(
                db_session=db_session,
                role_name=payload.get("role_name", ""),
                principal_kind=principal_kind,
                principal_id=payload.get("principal_id", ""),
                scope_kind=scope_kind,
                scope_id=payload.get("scope_id", None),
                inherits_into_project=bool(
                    payload.get("inherits_into_project", False)
                ),
                actor_user_id=actor,
            )
        except RoleNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"role_name": payload.get("role_name", "")},
            )
        except InvalidBindingScopeError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={
                    "scope_kind": payload.get("scope_kind", ""),
                    "scope_id": payload.get("scope_id", None),
                },
            )

        # Re-read through the view helper so the created_at string is
        # normalized. Mirrors the flask controller exactly.
        views = binding_service.list_bindings(
            db_session=db_session,
            principal_kind=None,
            principal_id=None,
            scope_kind=None,
            scope_id=None,
        )
        for view in views:
            if view.binding_id == str(binding.binding_id):
                body = _binding_to_dict(view)
                rtnval: Response = JSONResponse(
                    content=body, status_code=201
                )
                return rtnval

        _abort_problem(
            request=request,
            status=500,
            detail="Binding created but view lookup returned no row",
            extensions={"binding_id": str(binding.binding_id)},
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_bindings(request: Request) -> Response:
    """
        ``GET /api/v1/rbac/bindings`` — list bindings with optional
        filters: ``principal_kind`` / ``principal_id`` /
        ``scope_kind`` / ``scope_id``.

        :param request: Incoming webworks request.

        :returns: JSON response (200), or problem response on filter
                  coercion failure.
    """
    try:
        db_session = _require_session(request=request)

        principal_id = request.query_params.get("principal_id", None)
        scope_id = request.query_params.get("scope_id", None)

        principal_kind: Optional[PrincipalKind] = None
        principal_kind_raw = request.query_params.get(
            "principal_kind", None
        )
        if (principal_kind_raw is not None
                and len(principal_kind_raw) > 0):
            try:
                principal_kind = _parse_principal_kind(principal_kind_raw)
            except SemanticError as xcpt:
                _abort_problem(
                    request=request,
                    status=400,
                    detail=str(xcpt),
                    extensions={"principal_kind": principal_kind_raw},
                )

        scope_kind: Optional[BindingScope] = None
        scope_kind_raw = request.query_params.get("scope_kind", None)
        if scope_kind_raw is not None and len(scope_kind_raw) > 0:
            try:
                scope_kind = _parse_scope_kind(scope_kind_raw)
            except SemanticError as xcpt:
                _abort_problem(
                    request=request,
                    status=400,
                    detail=str(xcpt),
                    extensions={"scope_kind": scope_kind_raw},
                )

        views = binding_service.list_bindings(
            db_session=db_session,
            principal_kind=principal_kind,
            principal_id=principal_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )
        body = [_binding_to_dict(view) for view in views]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_revoke_binding(request: Request) -> Response:
    """
        ``DELETE /api/v1/rbac/bindings/{binding_id}`` — revoke a
        binding. Returns 200 with
        ``{binding_id, status: "revoked"}``.

        :param request: Incoming webworks request.

        :returns: JSON response (200), or problem response on
                  failure.
    """
    binding_id = request.path_params.get("binding_id", "")
    try:
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        try:
            binding_service.revoke_role(
                db_session=db_session,
                binding_id=binding_id,
                actor_user_id=actor,
            )
        except BindingNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"binding_id": binding_id},
            )

        body = {"binding_id": binding_id, "status": "revoked"}
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Handlers — check
# ---------------------------------------------------------------------------


def handle_check_permission(request: Request) -> Response:
    """
        ``POST /api/v1/rbac/check`` — evaluate a single permission
        for a principal. Used by out-of-process integrations.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the decision dict, or
                  problem response on failure.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)

        principal_id = payload.get("principal_id", "")
        permission_key = payload.get("permission_key", "")

        # Build a lightweight principal representation for the
        # evaluator. Same shape as the flask controller built.
        principal = AuthPrincipal(
            user_id=principal_id,
            session_id="rbac-check",
            provider_kind=AuthProviderKind.LOCAL,
            provider_name="rbac-check",
        )

        try:
            decision = rbac_evaluator.check_permission(
                db_session=db_session,
                principal=principal,
                permission_key=permission_key,
                now=datetime.now(timezone.utc),
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={
                    "principal_id": principal_id,
                    "permission_key": permission_key,
                },
            )

        body = {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "permission_key": decision.permission_key,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_rbac_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the RBAC routes to a webworks application.

        Fixed sub-paths (``/permissions``, ``/roles``, ``/bindings``,
        ``/check``) all live at depth 2 after ``/rbac`` and the
        per-binding route lives at depth 3 — no collisions.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix.

        :returns: None.
    """
    base = version_prefix + RBAC_PATH

    app.attach_route(
        base + "/permissions", methods=["GET"]
    )(handle_list_permissions)
    app.attach_route(base + "/roles", methods=["GET"])(handle_list_roles)
    app.attach_route(
        base + "/bindings", methods=["GET"]
    )(handle_list_bindings)
    app.attach_route(
        base + "/bindings", methods=["POST"]
    )(handle_create_binding)
    app.attach_route(
        base + "/bindings/{binding_id}", methods=["DELETE"]
    )(handle_revoke_binding)
    app.attach_route(
        base + "/check", methods=["POST"]
    )(handle_check_permission)

    return


__all__ = [
    "RBAC_PATH",
    "register_rbac_routes",
    "handle_list_permissions",
    "handle_list_roles",
    "handle_create_binding",
    "handle_list_bindings",
    "handle_revoke_binding",
    "handle_check_permission",
]
