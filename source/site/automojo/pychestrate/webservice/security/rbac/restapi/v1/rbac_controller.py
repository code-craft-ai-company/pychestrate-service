"""
.. module:: security.rbac.restapi.v1.rbac_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/rbac.

.. moduleauthor:: Automation Mojo LLC

M2 exposes the full RBAC surface:

* ``GET  /api/v1/rbac/roles`` — list registered role presets.
* ``GET  /api/v1/rbac/permissions`` — list the permission key catalog.
* ``POST /api/v1/rbac/bindings`` — assign a role to a principal at a scope.
* ``GET  /api/v1/rbac/bindings`` — list bindings with optional filters.
* ``DELETE /api/v1/rbac/bindings/{binding_id}`` — revoke a binding.
* ``POST /api/v1/rbac/check`` — evaluate a single permission for a principal
  (used by out-of-process integrations such as ``8-cli``).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone

from flask import g, request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.security.auth.models import AuthProviderKind
from automojo.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from automojo.pychestrate.webservice.security.rbac import (
    binding_service,
    rbac_evaluator,
)
from automojo.pychestrate.webservice.security.rbac.binding_service import BindingView
from automojo.pychestrate.webservice.security.rbac.catalog import load_catalog_from_registry
from automojo.pychestrate.webservice.security.rbac.exceptions import (
    BindingNotFoundError,
    InvalidBindingScopeError,
    RoleNotFoundError,
)
from automojo.pychestrate.webservice.security.rbac.models import BindingScope, PrincipalKind


RBAC_NAMESPACE_PATH = "/rbac"


rbac_ns = Namespace(
    "RBAC v1",
    description="Role, permission, and binding APIs (1-rbac).",
)


permission_model = rbac_ns.model(
    "RbacPermission",
    {
        "permission_key": fields.String(description="Canonical key"),
        "description": fields.String(description="Free-form description"),
        "namespace": fields.String(description="Namespace (system|project)"),
    },
)


role_model = rbac_ns.model(
    "RbacRole",
    {
        "role_name": fields.String(description="Unique role name"),
        "permission_count": fields.Integer(description="Number of permission grants"),
    },
)


binding_create_model = rbac_ns.model(
    "RbacBindingCreate",
    {
        "role_name": fields.String(required=True, description="Role preset name"),
        "principal_kind": fields.String(required=True, description="USER | GROUP"),
        "principal_id": fields.String(required=True, description="User or group UUID"),
        "scope_kind": fields.String(required=True, description="SYSTEM | ORGANIZATION | PROJECT"),
        "scope_id": fields.String(required=False, description="Project UUID for PROJECT scope"),
        "inherits_into_project": fields.Boolean(
            required=False, default=False,
            description="Seed project-scope bindings on project creation",
        ),
    },
)


binding_view_model = rbac_ns.model(
    "RbacBindingView",
    {
        "binding_id": fields.String(description="Binding UUID"),
        "role_name": fields.String(description="Role preset name"),
        "principal_kind": fields.String(description="USER | GROUP"),
        "principal_id": fields.String(description="User or group UUID"),
        "scope_kind": fields.String(description="SYSTEM | ORGANIZATION | PROJECT"),
        "scope_id": fields.String(description="Project UUID for PROJECT scope, else null"),
        "inherits_into_project": fields.Boolean(description="Inheritance flag"),
        "created_at": fields.String(description="ISO-8601 create timestamp"),
        "created_by": fields.String(description="Actor UUID (nullable)"),
    },
)


check_request_model = rbac_ns.model(
    "RbacCheck",
    {
        "principal_id": fields.String(required=True, description="User UUID to evaluate"),
        "permission_key": fields.String(
            required=True,
            description="Canonical key (system:<action> or project:<id>:<action>)",
        ),
    },
)


check_response_model = rbac_ns.model(
    "RbacCheckResult",
    {
        "allowed": fields.Boolean(description="Allow/deny outcome"),
        "reason": fields.String(description="Short decision reason string"),
        "permission_key": fields.String(description="Key that was evaluated"),
    },
)


def _binding_to_dict(view: BindingView) -> dict:
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


def _parse_principal_kind(raw: str) -> PrincipalKind:
    try:
        rtnval = PrincipalKind(raw)
    except ValueError:
        raise SemanticError("Unknown principal_kind: {}".format(raw))
    return rtnval


def _parse_scope_kind(raw: str) -> BindingScope:
    try:
        rtnval = BindingScope(raw)
    except ValueError:
        raise SemanticError("Unknown scope_kind: {}".format(raw))
    return rtnval


def _get_db_session():
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        rbac_ns.abort(503, "Request-scoped db_session not configured")
    return db_session


@rbac_ns.route("/permissions")
class RbacPermissionsList(Resource):
    """
        GET ``/api/v1/rbac/permissions`` — list the permission key catalog.
    """

    @rbac_ns.marshal_list_with(permission_model)
    def get(self):
        catalog = load_catalog_from_registry()
        rtnval = []
        for key in sorted(catalog.permissions.keys()):
            descriptor = catalog.permissions[key]
            rtnval.append({
                "permission_key": descriptor.permission_key,
                "description": descriptor.description,
                "namespace": descriptor.namespace,
            })
        return rtnval


@rbac_ns.route("/roles")
class RbacRolesList(Resource):
    """
        GET ``/api/v1/rbac/roles`` — list all registered roles.
    """

    @rbac_ns.marshal_list_with(role_model)
    def get(self):
        catalog = load_catalog_from_registry()
        rtnval = []
        for role_name in sorted(catalog.roles.keys()):
            grants = catalog.roles[role_name]
            rtnval.append({
                "role_name": role_name,
                "permission_count": len(grants),
            })
        return rtnval


@rbac_ns.route("/bindings")
class RbacBindingsCollection(Resource):
    """
        POST ``/api/v1/rbac/bindings`` — create a binding.
        GET  ``/api/v1/rbac/bindings`` — list bindings with optional filters.
    """

    @rbac_ns.expect(binding_create_model, validate=True)
    @rbac_ns.marshal_with(binding_view_model, code=201)
    def post(self):
        payload = request.get_json(force=True, silent=False)
        db_session = _get_db_session()
        actor = getattr(g, "actor_user_id", None)

        try:
            principal_kind = _parse_principal_kind(payload.get("principal_kind", ""))
            scope_kind = _parse_scope_kind(payload.get("scope_kind", ""))
        except SemanticError as xcpt:
            rbac_ns.abort(400, str(xcpt))

        try:
            binding = binding_service.assign_role(
                db_session=db_session,
                role_name=payload.get("role_name", ""),
                principal_kind=principal_kind,
                principal_id=payload.get("principal_id", ""),
                scope_kind=scope_kind,
                scope_id=payload.get("scope_id", None),
                inherits_into_project=bool(payload.get("inherits_into_project", False)),
                actor_user_id=actor,
            )
        except RoleNotFoundError as xcpt:
            rbac_ns.abort(404, str(xcpt))
        except InvalidBindingScopeError as xcpt:
            rbac_ns.abort(400, str(xcpt))

        # Re-read through the view helper so the created_at string is normalised.
        views = binding_service.list_bindings(
            db_session=db_session,
            principal_kind=None,
            principal_id=None,
            scope_kind=None,
            scope_id=None,
        )
        for view in views:
            if view.binding_id == str(binding.binding_id):
                rtnval = (_binding_to_dict(view), 201)
                return rtnval

        rbac_ns.abort(500, "Binding created but view lookup returned no row")
        return

    @rbac_ns.marshal_list_with(binding_view_model)
    def get(self):
        db_session = _get_db_session()

        principal_kind = None
        principal_id = request.args.get("principal_id", None)
        scope_kind = None
        scope_id = request.args.get("scope_id", None)

        principal_kind_raw = request.args.get("principal_kind", None)
        if principal_kind_raw is not None and len(principal_kind_raw) > 0:
            try:
                principal_kind = _parse_principal_kind(principal_kind_raw)
            except SemanticError as xcpt:
                rbac_ns.abort(400, str(xcpt))

        scope_kind_raw = request.args.get("scope_kind", None)
        if scope_kind_raw is not None and len(scope_kind_raw) > 0:
            try:
                scope_kind = _parse_scope_kind(scope_kind_raw)
            except SemanticError as xcpt:
                rbac_ns.abort(400, str(xcpt))

        views = binding_service.list_bindings(
            db_session=db_session,
            principal_kind=principal_kind,
            principal_id=principal_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )
        rtnval = [_binding_to_dict(v) for v in views]
        return rtnval


@rbac_ns.route("/bindings/<string:binding_id>")
@rbac_ns.param("binding_id", "Binding UUID")
class RbacBindingResource(Resource):
    """
        DELETE ``/api/v1/rbac/bindings/{binding_id}`` — revoke a binding.
    """

    def delete(self, binding_id: str):
        db_session = _get_db_session()
        actor = getattr(g, "actor_user_id", None)

        try:
            binding_service.revoke_role(
                db_session=db_session,
                binding_id=binding_id,
                actor_user_id=actor,
            )
        except BindingNotFoundError as xcpt:
            rbac_ns.abort(404, str(xcpt))

        rtnval = ({"binding_id": binding_id, "status": "revoked"}, 200)
        return rtnval


@rbac_ns.route("/check")
class RbacCheck(Resource):
    """
        POST ``/api/v1/rbac/check`` — evaluate a single permission.
    """

    @rbac_ns.expect(check_request_model, validate=True)
    @rbac_ns.marshal_with(check_response_model)
    def post(self):
        payload = request.get_json(force=True, silent=False)
        db_session = _get_db_session()

        principal_id = payload.get("principal_id", "")
        permission_key = payload.get("permission_key", "")

        # Build a lightweight principal representation for the evaluator.
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
            rbac_ns.abort(400, str(xcpt))

        rtnval = {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "permission_key": decision.permission_key,
        }
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(rbac_ns, version_prefix + RBAC_NAMESPACE_PATH)]
    return rtnval
