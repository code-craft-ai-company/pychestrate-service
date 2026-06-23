"""
.. module:: security.rbac.rbac_evaluator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: RBAC evaluation — check_permission and require_permission.

.. moduleauthor:: Code Craft AI LLC

M2 evaluator. Handles:

- ``system:<action>`` keys — matched against SYSTEM-scope bindings.
- ``project:<id>:<action>`` keys — matched against PROJECT-scope
  bindings with ``scope_id`` equal to ``<id>``, and against
  ORGANIZATION-scope bindings with ``inherits_into_project = True``
  that resolve to the same ``permission_key`` after the
  ``inheritance.seed_project_permissions`` pass.

Group membership is resolved per evaluation: for each principal, the
evaluator collects the set of groups the user belongs to via
``identity_group_memberships`` and evaluates GROUP-kind bindings with
matching ``principal_id``.

Deny beats allow across every binding source (direct user, group,
organization inheritance, project). Every positive and negative decision
goes through the process-local LRU cache in :mod:`cache`; callers that
want a fresh read call :func:`cache.invalidate_principal` first.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.webservice.identity.users.models import IdentityGroupMembership
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from ccai.pychestrate.webservice.security.rbac import cache
from ccai.pychestrate.webservice.security.rbac.catalog import (
    CatalogSnapshot,
    load_catalog_from_registry,
)
from ccai.pychestrate.webservice.security.rbac.exceptions import AuthorizationError
from ccai.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PermissionEffect,
    PrincipalKind,
    RbacRole,
    RbacRoleBinding,
)


@dataclass(frozen=True)
class AuthzDecision:
    """
        The outcome of an authorization check.

        :param allowed: True if the principal holds the permission.
        :param reason: Short string describing which rule decided.
        :param permission_key: The key that was evaluated.
    """
    allowed: bool
    reason: str
    permission_key: str


@dataclass(frozen=True)
class _ParsedKey:
    """
        Internal representation of a parsed permission key.

        :param namespace: 'system' or 'project'.
        :param project_id: None for system keys; project UUID for project keys.
        :param action: Tail of the key after the namespace (and project id).
    """
    namespace: str
    project_id: Optional[str]
    action: str


def _parse_permission_key(*, permission_key: str) -> _ParsedKey:
    """
        Parse ``system:<action>`` or ``project:<id>:<action>``.

        :param permission_key: Caller-supplied key.

        :returns: :class:`_ParsedKey`.
        :raises: SemanticError
    """
    if permission_key is None or len(permission_key.strip()) == 0:
        raise SemanticError("check_permission requires a non-empty permission_key")

    segments = permission_key.split(":")
    if len(segments) < 2:
        err_msg_lines = ["check_permission received a malformed permission_key."]
        err_msg_lines.append("KEY: {}".format(permission_key))
        err_msg_lines.append("EXPECTED: 'system:<action>' or 'project:<id>:<action>'")
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg)

    namespace = segments[0]
    if namespace == "system":
        action = ":".join(segments[1:])
        rtnval = _ParsedKey(namespace=namespace, project_id=None, action=action)
        return rtnval

    if namespace == "project":
        if len(segments) < 3:
            err_msg_lines = ["project:<id>:<action> requires a project id segment."]
            err_msg_lines.append("KEY: {}".format(permission_key))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg)
        project_id = segments[1]
        action = ":".join(segments[2:])
        rtnval = _ParsedKey(namespace=namespace, project_id=project_id, action=action)
        return rtnval

    err_msg_lines = ["check_permission received an unsupported namespace."]
    err_msg_lines.append("KEY: {}".format(permission_key))
    err_msg_lines.append("NAMESPACE: {}".format(namespace))
    err_msg_lines.append("SUPPORTED: system, project")
    err_msg = os.linesep.join(err_msg_lines)
    raise SemanticError(err_msg)


def _resolve_group_ids_for_user(*, db_session: DbSession, user_id: str) -> Set[str]:
    """
        Return the set of group UUIDs the user belongs to.

        :param db_session: Active SQLAlchemy session.
        :param user_id: User UUID string.

        :returns: Set of group UUID strings.
    """
    rows = (
        db_session.query(IdentityGroupMembership.group_id)
        .filter(IdentityGroupMembership.user_id == user_id)
        .all()
    )
    rtnval: Set[str] = set()
    for row in rows:
        group_id = row[0]
        if group_id is not None:
            rtnval.add(str(group_id))
    return rtnval


def _collect_applicable_bindings(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        parsed: _ParsedKey
    ) -> List[Tuple[RbacRoleBinding, str]]:
    """
        Collect every binding that could influence the decision for the
        parsed key + principal. Covers direct user bindings, group
        bindings, and organization-scope bindings with
        ``inherits_into_project = True`` when the key is project-scoped.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param parsed: Parsed permission key.

        :returns: List of (RbacRoleBinding, role_name) tuples.
    """
    user_id = principal.user_id
    group_ids = _resolve_group_ids_for_user(db_session=db_session, user_id=user_id)

    if parsed.namespace == "system":
        query = (
            db_session.query(RbacRoleBinding, RbacRole.role_name)
            .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
            .filter(RbacRoleBinding.scope_kind == BindingScope.SYSTEM)
        )
        user_rows = (
            query
            .filter(RbacRoleBinding.principal_kind == PrincipalKind.USER)
            .filter(RbacRoleBinding.principal_id == user_id)
            .all()
        )
        group_rows: List = []
        if len(group_ids) > 0:
            group_rows = (
                db_session.query(RbacRoleBinding, RbacRole.role_name)
                .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
                .filter(RbacRoleBinding.scope_kind == BindingScope.SYSTEM)
                .filter(RbacRoleBinding.principal_kind == PrincipalKind.GROUP)
                .filter(RbacRoleBinding.principal_id.in_(group_ids))
                .all()
            )
        rtnval = list(user_rows) + list(group_rows)
        return rtnval

    # project:<id>:<action>
    project_id = parsed.project_id

    # Direct user bindings at the project scope.
    project_user_rows = (
        db_session.query(RbacRoleBinding, RbacRole.role_name)
        .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
        .filter(RbacRoleBinding.scope_kind == BindingScope.PROJECT)
        .filter(RbacRoleBinding.scope_id == project_id)
        .filter(RbacRoleBinding.principal_kind == PrincipalKind.USER)
        .filter(RbacRoleBinding.principal_id == user_id)
        .all()
    )

    # Group bindings at the project scope.
    project_group_rows: List = []
    if len(group_ids) > 0:
        project_group_rows = (
            db_session.query(RbacRoleBinding, RbacRole.role_name)
            .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
            .filter(RbacRoleBinding.scope_kind == BindingScope.PROJECT)
            .filter(RbacRoleBinding.scope_id == project_id)
            .filter(RbacRoleBinding.principal_kind == PrincipalKind.GROUP)
            .filter(RbacRoleBinding.principal_id.in_(group_ids))
            .all()
        )

    # Organization bindings with inherits_into_project = True (user + group).
    org_user_rows = (
        db_session.query(RbacRoleBinding, RbacRole.role_name)
        .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
        .filter(RbacRoleBinding.scope_kind == BindingScope.ORGANIZATION)
        .filter(RbacRoleBinding.inherits_into_project == True)  # noqa: E712 — SQLAlchemy filter needs literal
        .filter(RbacRoleBinding.principal_kind == PrincipalKind.USER)
        .filter(RbacRoleBinding.principal_id == user_id)
        .all()
    )
    org_group_rows: List = []
    if len(group_ids) > 0:
        org_group_rows = (
            db_session.query(RbacRoleBinding, RbacRole.role_name)
            .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
            .filter(RbacRoleBinding.scope_kind == BindingScope.ORGANIZATION)
            .filter(RbacRoleBinding.inherits_into_project == True)  # noqa: E712
            .filter(RbacRoleBinding.principal_kind == PrincipalKind.GROUP)
            .filter(RbacRoleBinding.principal_id.in_(group_ids))
            .all()
        )

    rtnval = (
        list(project_user_rows)
        + list(project_group_rows)
        + list(org_user_rows)
        + list(org_group_rows)
    )
    return rtnval


def _role_grant_key(*, parsed: _ParsedKey) -> str:
    """
        Return the canonical permission-key string a role preset is
        expected to declare for ``parsed``.

        For system keys this is the original string. For project keys,
        role presets declare ``project:<action>`` without the per-instance
        project id so the preset is reusable across projects. The
        evaluator matches either the full instantiated key or the
        preset form.

        :param parsed: Parsed permission key.

        :returns: The preset form of the key.
    """
    if parsed.namespace == "system":
        return "system:{}".format(parsed.action)
    return "project:{}".format(parsed.action)


def _decide_from_bindings(
        *,
        bindings: List[Tuple[RbacRoleBinding, str]],
        catalog: CatalogSnapshot,
        parsed: _ParsedKey,
        permission_key: str
    ) -> AuthzDecision:
    """
        Collapse a list of binding rows into an :class:`AuthzDecision`.
        Deny beats allow.

        :param bindings: List of (binding, role_name) tuples.
        :param catalog: Loaded catalog snapshot.
        :param parsed: Parsed permission key.
        :param permission_key: The original key string for error messages.

        :returns: :class:`AuthzDecision`.
    """
    role_preset_key = _role_grant_key(parsed=parsed)

    allow_hit = False
    deny_hit = False

    for _binding, role_name in bindings:
        grants = catalog.roles.get(role_name, ())
        for grant in grants:
            grant_key = grant.permission_key
            if grant_key != permission_key and grant_key != role_preset_key:
                continue
            if grant.effect == PermissionEffect.DENY:
                deny_hit = True
            else:
                allow_hit = True

    if deny_hit is True:
        rtnval = AuthzDecision(
            allowed=False,
            reason="explicit_deny",
            permission_key=permission_key,
        )
        return rtnval

    if allow_hit is True:
        rtnval = AuthzDecision(
            allowed=True,
            reason="binding_allow",
            permission_key=permission_key,
        )
        return rtnval

    rtnval = AuthzDecision(
        allowed=False,
        reason="no_matching_binding",
        permission_key=permission_key,
    )
    return rtnval


def check_permission(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        permission_key: str,
        now: datetime
    ) -> AuthzDecision:
    """
        Evaluate whether a principal holds a permission across every
        binding source that applies to the key.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param permission_key: Canonical key string.
        :param now: Evaluation timestamp.

        :returns: An :class:`AuthzDecision`.
        :raises: SemanticError on malformed ``permission_key``.
    """
    parsed = _parse_permission_key(permission_key=permission_key)

    cached = cache.cache_get(
        principal_id=principal.user_id,
        permission_key=permission_key,
        scope_id=parsed.project_id,
    )
    if cached is not None:
        rtnval = AuthzDecision(
            allowed=cached.allowed,
            reason=cached.reason,
            permission_key=permission_key,
        )
        return rtnval

    catalog = load_catalog_from_registry()
    if parsed.namespace == "system" and permission_key not in catalog.permissions:
        rtnval = AuthzDecision(
            allowed=False,
            reason="unknown_permission_key",
            permission_key=permission_key,
        )
        cache.cache_put(
            principal_id=principal.user_id,
            permission_key=permission_key,
            scope_id=parsed.project_id,
            decision=cache.CachedDecision(allowed=False, reason="unknown_permission_key"),
        )
        return rtnval

    bindings = _collect_applicable_bindings(
        db_session=db_session, principal=principal, parsed=parsed,
    )
    decision = _decide_from_bindings(
        bindings=bindings,
        catalog=catalog,
        parsed=parsed,
        permission_key=permission_key,
    )
    cache.cache_put(
        principal_id=principal.user_id,
        permission_key=permission_key,
        scope_id=parsed.project_id,
        decision=cache.CachedDecision(
            allowed=decision.allowed,
            reason=decision.reason,
        ),
    )
    return decision


def require_permission(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        permission_key: str,
        now: datetime
    ) -> None:
    """
        Shortcut that raises :class:`AuthorizationError` on deny.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param permission_key: Canonical key string.
        :param now: Evaluation timestamp.

        :returns: None.
        :raises: AuthorizationError, SemanticError
    """
    decision = check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=permission_key,
        now=now,
    )
    if decision.allowed is False:
        err_msg_lines = ["Authorization denied."]
        err_msg_lines.append("PRINCIPAL_ID: {}".format(principal.user_id))
        err_msg_lines.append("PERMISSION: {}".format(permission_key))
        err_msg_lines.append("REASON: {}".format(decision.reason))
        err_msg = os.linesep.join(err_msg_lines)
        raise AuthorizationError(err_msg) from None

    return
