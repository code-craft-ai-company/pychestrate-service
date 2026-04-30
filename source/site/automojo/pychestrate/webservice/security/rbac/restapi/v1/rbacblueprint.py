"""
.. module:: security.rbac.restapi.v1.rbac_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/rbac.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks. Pattern follows
the worked example documented in
:mod:`automojo.pychestrate.webservice.security.auth.restapi.v1.auth_controller`.

Endpoints (unchanged URLs):

* ``GET    /api/v1/rbac/permissions`` — list the permission key catalog.
* ``GET    /api/v1/rbac/roles`` — list registered role presets.
* ``POST   /api/v1/rbac/bindings`` — assign a role to a principal at a scope.
* ``GET    /api/v1/rbac/bindings`` — list bindings with optional filters.
* ``DELETE /api/v1/rbac/bindings/{binding_id}`` — revoke a binding.
* ``POST   /api/v1/rbac/check`` — evaluate a single permission for a principal.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime, timezone
from typing import Any, Dict

from automojo.errors.exceptions import SemanticError

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse
from automojo.webworks.security.accesspolicy import AccessPolicy


_ADMIN_POLICY = AccessPolicy(roles=("system-admin",))

from automojo.pychestrate.webservice.dbsessionmiddleware import (
    get_request_actor_user_id,
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


RBAC_BASE_PATH = "/api/v1/rbac"


def _binding_to_dict(view: BindingView) -> Dict[str, Any]:
    """
        Render a :class:`BindingView` as the REST response dict.

        :param view: The view object.

        :returns: A plain dict suitable for JSON serialization.
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


def _parse_principal_kind(*, raw: str) -> PrincipalKind:
    """
        Coerce a string to a :class:`PrincipalKind` member.

        :param raw: Raw string value.

        :returns: The matching :class:`PrincipalKind`.

        :raises SemanticError: When ``raw`` is unknown.
    """
    try:
        rtnval = PrincipalKind(raw)
    except ValueError as exc:
        err_msg = "Unknown principal_kind: {}".format(raw)
        raise SemanticError(err_msg) from exc
    return rtnval


def _parse_scope_kind(*, raw: str) -> BindingScope:
    """
        Coerce a string to a :class:`BindingScope` member.

        :param raw: Raw string value.

        :returns: The matching :class:`BindingScope`.

        :raises SemanticError: When ``raw`` is unknown.
    """
    try:
        rtnval = BindingScope(raw)
    except ValueError as exc:
        err_msg = "Unknown scope_kind: {}".format(raw)
        raise SemanticError(err_msg) from exc
    return rtnval


def _require_db_session(*, request: Request) -> Any:
    """
        Pull the request-scoped ``db_session`` set by
        :class:`DbSessionMiddleware`, or 503.

        :param request: The incoming HTTP request.

        :returns: The SQLAlchemy session attached by the middleware.

        :raises HTTPException: 503 when the middleware did not run.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


def _read_json_body(*, request: Request) -> Dict[str, Any]:
    """
        Parse the request body as a JSON object.

        :param request: The incoming HTTP request.

        :returns: The decoded JSON object as a dict.

        :raises HTTPException: 400 when the body is missing or not an
                               object.
    """
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")
    try:
        decoded = request.json()
    except Exception as exc:
        err_msg = "request body must be valid JSON"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object",
        )
    rtnval = decoded
    return rtnval


class RbacBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/rbac`` endpoints.
    """

    base_path = RBAC_BASE_PATH
    tags = ["rbac", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/rbac/permissions",
        methods=["GET"],
        doc=Doc(
            summary="List permission catalog",
            description="Return the full catalog of registered permission keys.",
        ),
    )
    def list_permissions(request: Request) -> JSONResponse:
        """
            List the permission key catalog.

            :param request: The incoming HTTP request.

            :returns: 200 with a list of permission entries.
        """
        catalog = load_catalog_from_registry()
        permission_entries = []
        for key in sorted(catalog.permissions.keys()):
            descriptor = catalog.permissions[key]
            entry = {
                "permission_key": descriptor.permission_key,
                "description": descriptor.description,
                "namespace": descriptor.namespace,
            }
            permission_entries.append(entry)
        rtnval = JSONResponse(
            content=permission_entries, status_code=200,
        )
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/rbac/roles",
        methods=["GET"],
        doc=Doc(
            summary="List role presets",
            description="Return all registered role presets and their grant counts.",
        ),
    )
    def list_roles(request: Request) -> JSONResponse:
        """
            List registered role presets.

            :param request: The incoming HTTP request.

            :returns: 200 with a list of role entries.
        """
        catalog = load_catalog_from_registry()
        role_entries = []
        for role_name in sorted(catalog.roles.keys()):
            grants = catalog.roles[role_name]
            entry = {
                "role_name": role_name,
                "permission_count": len(grants),
            }
            role_entries.append(entry)
        rtnval = JSONResponse(content=role_entries, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/rbac/bindings",
        methods=["POST"],
        doc=Doc(
            summary="Assign a role binding",
            description=(
                "Bind a role preset to a principal at a SYSTEM, "
                "ORGANIZATION, or PROJECT scope."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def create_binding(request: Request) -> JSONResponse:
        """
            Assign a role binding.

            :param request: The incoming HTTP request.

            :returns: 201 with the created binding view.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)

        try:
            principal_kind = _parse_principal_kind(
                raw=payload.get("principal_kind", ""),
            )
            scope_kind = _parse_scope_kind(
                raw=payload.get("scope_kind", ""),
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        try:
            binding = binding_service.assign_role(
                db_session=db_session,
                role_name=payload.get("role_name", ""),
                principal_kind=principal_kind,
                principal_id=payload.get("principal_id", ""),
                scope_kind=scope_kind,
                scope_id=payload.get("scope_id", None),
                inherits_into_project=bool(
                    payload.get("inherits_into_project", False),
                ),
                actor_user_id=actor_user_id,
            )
        except RoleNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        except InvalidBindingScopeError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        # Re-read through the view helper so created_at is normalised.
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
                rtnval = JSONResponse(content=body, status_code=201)
                return rtnval

        err_msg = "Binding created but view lookup returned no row"
        raise HTTPException(status_code=500, detail=err_msg)

    @RestBlueprint.attach_at(
        path="/api/v1/rbac/bindings",
        methods=["GET"],
        doc=Doc(
            summary="List role bindings",
            description="List role bindings with optional filters.",
        ),
    )
    def list_bindings(request: Request) -> JSONResponse:
        """
            List role bindings (optional filters via query params).

            :param request: The incoming HTTP request.

            :returns: 200 with a list of binding views.
        """
        db_session = _require_db_session(request=request)

        principal_kind = None
        principal_id = request.query_params.get("principal_id", None)
        scope_kind = None
        scope_id = request.query_params.get("scope_id", None)

        principal_kind_raw = request.query_params.get(
            "principal_kind", None,
        )
        if principal_kind_raw is not None:
            if len(principal_kind_raw) > 0:
                try:
                    principal_kind = _parse_principal_kind(
                        raw=principal_kind_raw,
                    )
                except SemanticError as exc:
                    raise HTTPException(
                        status_code=400, detail=str(exc),
                    ) from exc

        scope_kind_raw = request.query_params.get("scope_kind", None)
        if scope_kind_raw is not None:
            if len(scope_kind_raw) > 0:
                try:
                    scope_kind = _parse_scope_kind(raw=scope_kind_raw)
                except SemanticError as exc:
                    raise HTTPException(
                        status_code=400, detail=str(exc),
                    ) from exc

        views = binding_service.list_bindings(
            db_session=db_session,
            principal_kind=principal_kind,
            principal_id=principal_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )
        body = [_binding_to_dict(view=v) for v in views]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/rbac/bindings/{binding_id}",
        methods=["DELETE"],
        doc=Doc(
            summary="Revoke a role binding",
            description="Revoke an existing role binding by id.",
        ),
        access_policy=_ADMIN_POLICY,
    )
    def delete_binding(request: Request) -> JSONResponse:
        """
            Revoke a binding by id.

            :param request: The incoming HTTP request.

            :returns: 200 with ``{"binding_id": ..., "status":
                      "revoked"}``.
        """
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        binding_id = request.path_params.get("binding_id", "")

        try:
            binding_service.revoke_role(
                db_session=db_session,
                binding_id=binding_id,
                actor_user_id=actor_user_id,
            )
        except BindingNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = {"binding_id": binding_id, "status": "revoked"}
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/rbac/check",
        methods=["POST"],
        doc=Doc(
            summary="Check a permission",
            description=(
                "Evaluate a single permission key against a principal "
                "and return the allow/deny outcome with a reason."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def check_permission(request: Request) -> JSONResponse:
        """
            Evaluate a single permission.

            :param request: The incoming HTTP request.

            :returns: 200 with the decision payload.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)

        principal_id = payload.get("principal_id", "")
        permission_key = payload.get("permission_key", "")

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
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        body = {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "permission_key": decision.permission_key,
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
