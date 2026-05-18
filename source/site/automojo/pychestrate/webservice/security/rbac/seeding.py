"""
.. module:: security.rbac.seeding
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Idempotent seed helpers for built-in RBAC role rows
               and admin role bindings.

.. moduleauthor:: Automation Mojo LLC

The RBAC evaluator joins ``RbacRoleBinding`` rows against
``RbacRole`` rows (by ``role_id``) to discover the role name
and then looks the role's permission grants up in the in-memory
catalog. The catalog is loaded from registered ``RoleExtension``
subclasses at process start, but the ``rbac_roles`` table is
only schema -- no migration seeds the built-in
:class:`SystemAdminRole` row. Live deploys therefore have a
working catalog but no rows in ``rbac_roles``, and any
``RbacRoleBinding`` write requires a row to point at.

This module provides the small idempotent surface
:func:`ensure_role_persisted` /
:func:`ensure_system_admin_binding_for_user` that two callers
use:

* :func:`identity.setup.setup_service.create_initial_admin`
  invokes the helper after creating the first admin so the
  fresh deploy has a working ``system:ui.admin.view`` check
  for the seeded admin.

* The alembic data migration that backfills bindings for
  existing alpha deploys with legacy ``user.user_roles`` CSVs
  containing ``admin`` reuses the same helper at upgrade
  time.

Both call sites are explicitly idempotent -- re-running
either is a no-op when the rows already exist. The helpers
match the shape :mod:`tests...phase10._e2e_harness`'s
``grant_role_to_user`` uses (the harness is the canonical
reference implementation), so the seed produced by the
setup wizard is byte-equivalent to what the e2e harness
seeds at test time.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Optional


SYSTEM_ADMIN_ROLE_NAME: str = "system-admin"


def ensure_role_persisted(
        *,
        db_session: Any,
        role_name: str,
        description: str = ""
    ) -> Any:
    """
        Idempotently ensure an ``rbac_roles`` row exists for the
        given role name. Returns the row whether it pre-existed
        or was created by this call.

        The row's permission grants live in the in-memory catalog
        (the role's :class:`RoleExtension` subclass), not in the
        database -- this helper only seeds the row that bindings
        reference.

        :param db_session: Active SQLAlchemy session.
        :param role_name: Role name; must match a registered
                          :class:`RoleExtension` ``role_name``.
        :param description: Description text recorded on the row
                            when it is newly created. Ignored when
                            the row already exists.

        :returns: The persisted :class:`RbacRole` row.
    """
    from automojo.pychestrate.webservice.security.rbac.models import (
        RbacRole,
        RoleSource,
    )

    existing = (
        db_session.query(RbacRole)
        .filter(RbacRole.role_name == role_name)
        .first()
    )
    if existing is not None:
        rtnval = existing
        return rtnval

    row = RbacRole(
        role_id=uuid.uuid4(),
        role_name=role_name,
        source=RoleSource.BUILTIN,
        source_name=role_name,
        description=description,
    )
    db_session.add(row)
    db_session.flush()

    rtnval = row
    return rtnval


def ensure_system_admin_binding_for_user(
        *,
        db_session: Any,
        user_id: str,
        actor_user_id: Optional[str] = None
    ) -> Any:
    """
        Idempotently bind the built-in ``system-admin`` role to
        ``user_id`` at SYSTEM scope.

        Used by the setup wizard (for the first admin) and by the
        backfill alembic data migration (for legacy CSV-role
        admins). After this call, the modern
        ``rbac_evaluator.check_permission`` answers ``True`` for
        every permission the in-tree :class:`SystemAdminRole`
        catalog entry declares, including
        ``system:ui.admin.view``.

        :param db_session: Active SQLAlchemy session.
        :param user_id: Target user UUID (string).
        :param actor_user_id: Optional acting principal UUID for
                              audit attribution. ``None`` for
                              system-driven seeds.

        :returns: The persisted (or pre-existing)
                  :class:`RbacRoleBinding` row.
    """
    from automojo.pychestrate.webservice.security.rbac.models import (
        BindingScope,
        PrincipalKind,
        RbacRoleBinding,
    )

    role = ensure_role_persisted(
        db_session=db_session,
        role_name=SYSTEM_ADMIN_ROLE_NAME,
        description=(
            "Full administrative access to system-scoped capabilities."
        ),
    )

    principal_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

    existing = (
        db_session.query(RbacRoleBinding)
        .filter(RbacRoleBinding.role_id == role.role_id)
        .filter(RbacRoleBinding.principal_kind == PrincipalKind.USER)
        .filter(RbacRoleBinding.principal_id == principal_uuid)
        .filter(RbacRoleBinding.scope_kind == BindingScope.SYSTEM)
        .filter(RbacRoleBinding.scope_id.is_(None))
        .first()
    )
    if existing is not None:
        rtnval = existing
        return rtnval

    actor_uuid = None
    if actor_user_id is not None and len(actor_user_id) > 0:
        actor_uuid = uuid.UUID(actor_user_id)

    binding = RbacRoleBinding(
        binding_id=uuid.uuid4(),
        role_id=role.role_id,
        principal_kind=PrincipalKind.USER,
        principal_id=principal_uuid,
        scope_kind=BindingScope.SYSTEM,
        scope_id=None,
        inherits_into_project=False,
        created_by=actor_uuid,
    )
    db_session.add(binding)
    db_session.flush()

    rtnval = binding
    return rtnval


__all__ = [
    "SYSTEM_ADMIN_ROLE_NAME",
    "ensure_role_persisted",
    "ensure_system_admin_binding_for_user",
]
