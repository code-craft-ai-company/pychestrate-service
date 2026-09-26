"""
.. module:: webinterface.blueprints.projects.project_access
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Who may use which project in the /projects UI.

.. moduleauthor:: Code Craft AI LLC

Access to a project in the consumer ``/projects`` UI comes from two
places, and :class:`ProjectManager` combines them (the strongest wins):

* **Project membership** -- the role a user is given on a project's
  Members page (owner / administrator / developer / viewer).
* **Global roles** -- RBAC role bindings that apply to every project:
  the ``project-owner`` / ``project-editor`` / ``project-viewer``
  presets assigned on a user's page (a SYSTEM-scope binding, or an
  ORGANIZATION-scope binding that inherits into projects), and the
  system-wide project permissions held by system administrators.

Before this module the ``project-*`` presets granted nothing: their
``project:<action>`` keys were never evaluated, only
``system:projects.read`` (held by system administrators alone) showed
the Projects area, and a project member without a system role got the
"no access yet" page.

Global grant -> role on every project:

* ``system:projects.write`` or ``project:projects.admin``
  (``project-owner``) -> owner
* ``project:runs.dispatch`` (``project-editor``) -> developer
* ``system:projects.read`` or ``project:projects.read``
  (``project-viewer``) -> viewer

An explicit DENY of a key in any applicable binding removes that grant,
as in :mod:`security.rbac.rbac_evaluator`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


#: Permission key that makes the Projects area visible in the site
#: shell's navigation. It is not bound through a role: it is derived
#: for every user who has access to at least one project (see
#: :func:`navigation_permission_keys`).
PROJECTS_ACCESS_PERMISSION_KEY: str = "system:projects.access"

_SYSTEM_PROJECTS_READ: str = "system:projects.read"
_SYSTEM_PROJECTS_WRITE: str = "system:projects.write"

#: Preset project keys (as declared by the ``project-*`` roles) that
#: give a role on every project when bound globally, strongest first.
_PRESET_KEY_ROLES: Tuple[Tuple[str, str], ...] = (
    ("project:projects.admin", "owner"),
    ("project:runs.dispatch", "developer"),
    ("project:projects.read", "viewer"),
)


def _as_uuid(value: Any) -> Optional[uuid.UUID]:
    """
        Parse a user id into a UUID (``None`` when it is not one).
    """
    try:
        rtnval = uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        rtnval = None
    return rtnval


def _global_bindings(*, db_session: Any, user_id: uuid.UUID) -> List[Tuple[Any, str]]:
    """
        The user's role bindings that apply to every project: SYSTEM
        scope, and ORGANIZATION scope with ``inherits_into_project``,
        bound to the user directly or to one of the user's groups.

        :returns: List of (binding, role_name) tuples.
    """
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityGroupMembership,
    )
    from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
        BindingScope,
        PrincipalKind,
        RbacRole,
        RbacRoleBinding,
    )
    from sqlalchemy import and_, or_

    group_ids = [
        row[0]
        for row in db_session.query(IdentityGroupMembership.group_id)
        .filter(IdentityGroupMembership.user_id == user_id)
        .all()
        if row[0] is not None
    ]
    principal_filter = and_(
        RbacRoleBinding.principal_kind == PrincipalKind.USER,
        RbacRoleBinding.principal_id == user_id,
    )
    if len(group_ids) > 0:
        principal_filter = or_(
            principal_filter,
            and_(
                RbacRoleBinding.principal_kind == PrincipalKind.GROUP,
                RbacRoleBinding.principal_id.in_(group_ids),
            ),
        )
    scope_filter = or_(
        RbacRoleBinding.scope_kind == BindingScope.SYSTEM,
        and_(
            RbacRoleBinding.scope_kind == BindingScope.ORGANIZATION,
            RbacRoleBinding.inherits_into_project == True,  # noqa: E712 -- SQL expression
        ),
    )
    rows = (
        db_session.query(RbacRoleBinding, RbacRole.role_name)
        .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
        .filter(principal_filter)
        .filter(scope_filter)
        .all()
    )
    rtnval = [(binding, role_name) for binding, role_name in rows]
    return rtnval


def _preset_project_grants(*, db_session: Any, user_id: uuid.UUID) -> Set[str]:
    """
        The ``project:<action>`` preset keys the user's global bindings
        allow (catalog grants of built-in / extension roles plus the DB
        rows of custom roles), with any explicitly denied key removed.
    """
    from ccai.pychestrate.webservice.security.rbac.catalog import (  # noqa: E402
        load_catalog_from_registry,
    )
    from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
        PermissionEffect,
        RbacRolePermission,
    )

    bindings = _global_bindings(db_session=db_session, user_id=user_id)
    if len(bindings) == 0:
        return set()

    catalog = load_catalog_from_registry()
    role_ids = list({binding.role_id for binding, _role_name in bindings})
    db_grants: Dict[str, List[Any]] = {}
    for row in db_session.query(RbacRolePermission).filter(RbacRolePermission.role_id.in_(role_ids)).all():
        db_grants.setdefault(str(row.role_id), []).append(row)

    allowed: Set[str] = set()
    denied: Set[str] = set()
    for binding, role_name in bindings:
        grants = list(catalog.roles.get(role_name, ())) + db_grants.get(str(binding.role_id), [])
        for grant in grants:
            key = grant.permission_key
            if key.startswith("project:") is False:
                continue
            if grant.effect == PermissionEffect.DENY:
                denied.add(key)
            else:
                allowed.add(key)
    rtnval = allowed - denied
    return rtnval


def _holds_system_permission(*, db_session: Any, user_id: uuid.UUID, permission_key: str) -> bool:
    """
        Evaluate a ``system:*`` key through the RBAC evaluator (so the
        answer matches the REST surface and its decision cache).
    """
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthProviderKind,
    )
    from ccai.pychestrate.webservice.security.auth.session_service import (  # noqa: E402
        AuthPrincipal,
    )
    from ccai.pychestrate.webservice.security.rbac import rbac_evaluator  # noqa: E402

    principal = AuthPrincipal(
        user_id=str(user_id),
        session_id="",
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
    )
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=permission_key,
        now=datetime.now(timezone.utc),
    )
    rtnval = decision.allowed is True
    return rtnval


def resolve_global_project_role(*, db_session: Any, user_id: Any) -> Optional[str]:
    """
        The role (``owner`` / ``developer`` / ``viewer``) ``user_id``
        holds on every project through global grants, or ``None``.

        :param db_session: Open SQLAlchemy session.
        :param user_id: The user's id.

        :returns: Role value string, or ``None`` for no global access.
    """
    parsed = _as_uuid(user_id)
    if parsed is None:
        return None

    if _holds_system_permission(db_session=db_session, user_id=parsed, permission_key=_SYSTEM_PROJECTS_WRITE):
        return "owner"

    grants = _preset_project_grants(db_session=db_session, user_id=parsed)
    for key, role in _PRESET_KEY_ROLES:
        if key in grants:
            return role

    if _holds_system_permission(db_session=db_session, user_id=parsed, permission_key=_SYSTEM_PROJECTS_READ):
        return "viewer"

    return None


def build_project_access_resolver(*, db_session: Any) -> Callable[[str], Any]:
    """
        Build the ``access_resolver`` :class:`ProjectManager` takes: a
        callable ``(user_id) -> ProjectRole | None`` over this session.

        :param db_session: Open SQLAlchemy session.

        :returns: The resolver.
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectRole,
    )

    def _resolve(user_id: str) -> Any:
        role_value = resolve_global_project_role(db_session=db_session, user_id=user_id)
        if role_value is None:
            return None
        rtnval = ProjectRole(role_value)
        return rtnval

    return _resolve


def build_access_aware_project_manager(*, db_session: Any) -> Any:
    """
        A :class:`ProjectManager` whose permission checks and project
        lists honour global roles as well as membership, and whose
        project changes keep the project registry in step.

        :param db_session: Open SQLAlchemy session.

        :returns: ProjectManager instance.
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectManager,
    )
    from ccai.pychestrate.webservice.projects.bridge import (  # noqa: E402
        LegacyProjectListener,
    )
    # The listener keeps each UI project's registry project (the owner
    # of project identity) in step with it -- see projects.bridge.
    rtnval = ProjectManager(
        db_session,
        access_resolver=build_project_access_resolver(db_session=db_session),
        lifecycle_listener=LegacyProjectListener(),
    )
    return rtnval


def _role_from_keys(*, system_keys: Set[str], preset_keys: Set[str]) -> Optional[str]:
    """
        Map the global grants a user holds to their role on every
        project (the table in the module docstring).
    """
    if _SYSTEM_PROJECTS_WRITE in system_keys:
        return "owner"
    for key, role in _PRESET_KEY_ROLES:
        if key in preset_keys:
            return role
    if _SYSTEM_PROJECTS_READ in system_keys:
        return "viewer"
    return None


def list_global_project_access(*, db_session: Any) -> List[Dict[str, Any]]:
    """
        Everyone who can open every project through a global grant, for
        the Members page: users bound (directly or through a group) to a
        ``project-*`` role at SYSTEM scope or at ORGANIZATION scope with
        ``inherits_into_project``, and holders of the system projects
        permissions (system administrators).

        :param db_session: Open SQLAlchemy session.

        :returns: Rows ``{user_id, username, display_name, role, roles}``
                  sorted by username; ``role`` is the resulting project
                  role, ``roles`` the role names that grant it.
    """
    from ccai.pychestrate.core.orm import User  # noqa: E402
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityGroupMembership,
    )
    from ccai.pychestrate.webservice.security.rbac.catalog import (  # noqa: E402
        load_catalog_from_registry,
    )
    from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
        BindingScope,
        PermissionEffect,
        PrincipalKind,
        RbacRole,
        RbacRoleBinding,
        RbacRolePermission,
    )
    from sqlalchemy import and_, or_

    interesting = {_SYSTEM_PROJECTS_READ, _SYSTEM_PROJECTS_WRITE} | {key for key, _role in _PRESET_KEY_ROLES}
    rows = (
        db_session.query(RbacRoleBinding, RbacRole.role_name)
        .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
        .filter(or_(
            RbacRoleBinding.scope_kind == BindingScope.SYSTEM,
            and_(
                RbacRoleBinding.scope_kind == BindingScope.ORGANIZATION,
                RbacRoleBinding.inherits_into_project == True,  # noqa: E712 -- SQL expression
            ),
        ))
        .all()
    )
    if len(rows) == 0:
        return []

    catalog = load_catalog_from_registry()
    role_ids = list({binding.role_id for binding, _name in rows})
    db_grants: Dict[str, List[Any]] = {}
    for grant_row in db_session.query(RbacRolePermission).filter(RbacRolePermission.role_id.in_(role_ids)).all():
        db_grants.setdefault(str(grant_row.role_id), []).append(grant_row)

    # user id -> {"allow": set, "deny": set, "roles": set}
    per_user: Dict[str, Dict[str, Set[str]]] = {}
    for binding, role_name in rows:
        grants = list(catalog.roles.get(role_name, ())) + db_grants.get(str(binding.role_id), [])
        allow: Set[str] = set()
        deny: Set[str] = set()
        for grant in grants:
            key = grant.permission_key
            if key not in interesting:
                continue
            # System keys only come from SYSTEM-scope bindings, as in
            # the RBAC evaluator.
            if key.startswith("system:") and binding.scope_kind != BindingScope.SYSTEM:
                continue
            if grant.effect == PermissionEffect.DENY:
                deny.add(key)
            else:
                allow.add(key)
        if len(allow) == 0 and len(deny) == 0:
            continue
        if binding.principal_kind == PrincipalKind.USER:
            user_ids = [str(binding.principal_id)]
        else:
            user_ids = [
                str(member_row[0])
                for member_row in db_session.query(IdentityGroupMembership.user_id)
                .filter(IdentityGroupMembership.group_id == binding.principal_id)
                .all()
            ]
        for user_id in user_ids:
            entry = per_user.setdefault(user_id, {"allow": set(), "deny": set(), "roles": set()})
            entry["allow"] |= allow
            entry["deny"] |= deny
            if len(allow) > 0:
                entry["roles"].add(role_name)

    rtnval: List[Dict[str, Any]] = []
    for user_id, entry in per_user.items():
        granted = entry["allow"] - entry["deny"]
        role = _role_from_keys(
            system_keys={key for key in granted if key.startswith("system:")},
            preset_keys={key for key in granted if key.startswith("project:")},
        )
        if role is None:
            continue
        parsed = _as_uuid(user_id)
        user = None
        if parsed is not None:
            user = db_session.query(User).filter(User.id == parsed).first()
        rtnval.append({
            "user_id": user_id,
            "username": user.login if user is not None else user_id,
            "display_name": (user.display_name or "") if user is not None else "",
            "role": role,
            "roles": sorted(entry["roles"]),
        })
    rtnval.sort(key=lambda item: str(item["username"]).lower())
    return rtnval


def navigation_permission_keys(*, db_session: Any, user_id: Any) -> List[str]:
    """
        Extra navigation keys for ``/api/v1/me/permissions`` and
        ``/api/v1/me/navigation``: :data:`PROJECTS_ACCESS_PERMISSION_KEY`
        when the user can use at least one project (as a member or
        through a global role). Any failure yields no keys.

        :param db_session: Request-scoped session.
        :param user_id: The principal's user id.

        :returns: List of keys to add to the held set.
    """
    # A savepoint keeps a failed lookup (for example a database without
    # the legacy project tables) from poisoning the caller's
    # transaction.
    savepoint = None
    try:
        savepoint = db_session.begin_nested()
        manager = build_access_aware_project_manager(db_session=db_session)
        has_access = manager.has_any_project_access(str(user_id))
        savepoint.commit()
    except Exception:
        has_access = False
        if savepoint is not None:
            try:
                savepoint.rollback()
            except Exception:
                pass
    rtnval = [PROJECTS_ACCESS_PERMISSION_KEY] if has_access is True else []
    return rtnval


__all__ = [
    "PROJECTS_ACCESS_PERMISSION_KEY",
    "resolve_global_project_role",
    "build_project_access_resolver",
    "build_access_aware_project_manager",
    "list_global_project_access",
    "navigation_permission_keys",
]
