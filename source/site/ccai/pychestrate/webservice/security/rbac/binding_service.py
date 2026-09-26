"""
.. module:: security.rbac.binding_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Role binding CRUD — assign_role, revoke_role, list_bindings.

.. moduleauthor:: Code Craft AI LLC

Implements the M2 surface for role bindings. Every write publishes an
``entity.role.assigned`` / ``entity.role.revoked`` event via the
transactional outbox so ``1-audit-log`` records each change exactly once
and the process-local RBAC cache can invalidate downstream.

``assign_role`` enforces scope semantics:

- ``scope_kind = SYSTEM`` — ``scope_id`` must be None.
- ``scope_kind = ORGANIZATION`` — ``scope_id`` must be None; may set
  ``inherits_into_project = True`` to seed project-scoped bindings when a
  new project is created.
- ``scope_kind = PROJECT`` — ``scope_id`` must be a non-null project id;
  ``inherits_into_project`` must be False.

Illegal combinations raise :class:`InvalidBindingScopeError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.security.rbac.events import RbacEventTopics
from ccai.pychestrate.webservice.security.rbac.exceptions import (
    BindingNotFoundError,
    InvalidBindingScopeError,
    RoleNotFoundError,
)
from ccai.pychestrate.webservice.security.rbac.models import (
    BindingScope,
    PrincipalKind,
    RbacRole,
    RbacRoleBinding,
)


@dataclass(frozen=True)
class BindingView:
    """
        Read-model returned by :func:`list_bindings`.

        :param binding_id: UUID of the binding row.
        :param role_name: Role carried by the binding.
        :param principal_kind: USER | GROUP.
        :param principal_id: User or group UUID.
        :param scope_kind: SYSTEM | ORGANIZATION | PROJECT.
        :param scope_id: Project UUID when scope_kind == PROJECT, else None.
        :param inherits_into_project: Whether org bindings seed project scope.
        :param created_at_iso: ISO-8601 string timestamp of binding creation.
        :param created_by: Actor UUID, or None for system-created bindings.
    """
    binding_id: str
    role_name: str
    principal_kind: PrincipalKind
    principal_id: str
    scope_kind: BindingScope
    scope_id: Optional[str]
    inherits_into_project: bool
    created_at_iso: str
    created_by: Optional[str]


def _validate_scope_arguments(
        *,
        scope_kind: BindingScope,
        scope_id: Optional[str],
        inherits_into_project: bool
    ) -> None:
    """
        Raise :class:`InvalidBindingScopeError` when scope arguments violate
        the per-scope contract documented in the module docstring.

        :param scope_kind: Requested scope enum.
        :param scope_id: Project UUID string or None.
        :param inherits_into_project: Caller's inheritance flag.

        :returns: None.
        :raises: InvalidBindingScopeError
    """
    if scope_kind == BindingScope.SYSTEM:
        if scope_id is not None:
            _raise_invalid_scope(
                scope_kind=scope_kind,
                scope_id=scope_id,
                inherits_into_project=inherits_into_project,
                reason="SYSTEM_bindings_must_not_set_scope_id",
            )
        if inherits_into_project is True:
            _raise_invalid_scope(
                scope_kind=scope_kind,
                scope_id=scope_id,
                inherits_into_project=inherits_into_project,
                reason="SYSTEM_bindings_cannot_inherit_into_project",
            )
        return

    if scope_kind == BindingScope.ORGANIZATION:
        if scope_id is not None:
            _raise_invalid_scope(
                scope_kind=scope_kind,
                scope_id=scope_id,
                inherits_into_project=inherits_into_project,
                reason="ORGANIZATION_bindings_must_not_set_scope_id",
            )
        return

    if scope_kind == BindingScope.PROJECT:
        if scope_id is None or len(scope_id.strip()) == 0:
            _raise_invalid_scope(
                scope_kind=scope_kind,
                scope_id=scope_id,
                inherits_into_project=inherits_into_project,
                reason="PROJECT_bindings_require_scope_id",
            )
        if inherits_into_project is True:
            _raise_invalid_scope(
                scope_kind=scope_kind,
                scope_id=scope_id,
                inherits_into_project=inherits_into_project,
                reason="PROJECT_bindings_cannot_declare_inherits_into_project",
            )
        return

    raise SemanticError("Unknown BindingScope: {}".format(scope_kind))


def _raise_invalid_scope(
        *,
        scope_kind: BindingScope,
        scope_id: Optional[str],
        inherits_into_project: bool,
        reason: str
    ) -> None:
    """
        Build and raise :class:`InvalidBindingScopeError` with a multi-line
        message per AGENTS.md.

        :returns: None — always raises.
        :raises: InvalidBindingScopeError
    """
    err_msg_lines = ["Invalid role binding scope combination."]
    err_msg_lines.append("SCOPE_KIND: {}".format(scope_kind.value))
    err_msg_lines.append("SCOPE_ID: {}".format(scope_id))
    err_msg_lines.append("INHERITS_INTO_PROJECT: {}".format(inherits_into_project))
    err_msg_lines.append("REASON: {}".format(reason))
    err_msg = os.linesep.join(err_msg_lines)
    raise InvalidBindingScopeError(err_msg) from None


def _resolve_role_by_name(*, db_session: DbSession, role_name: str) -> RbacRole:
    """
        Return the :class:`RbacRole` with the given name, or raise.

        :returns: The persisted role row.
        :raises: RoleNotFoundError
    """
    role = db_session.query(RbacRole).filter(RbacRole.role_name == role_name).first()
    if role is None:
        err_msg_lines = ["Cannot resolve role binding — role name is not registered."]
        err_msg_lines.append("ROLE_NAME: {}".format(role_name))
        err_msg = os.linesep.join(err_msg_lines)
        raise RoleNotFoundError(err_msg) from None
    return role


def assign_role(
        *,
        db_session: DbSession,
        role_name: str,
        principal_kind: PrincipalKind,
        principal_id: str,
        scope_kind: BindingScope,
        scope_id: Optional[str],
        inherits_into_project: bool,
        actor_user_id: Optional[str],
        commit: bool = True
    ) -> RbacRoleBinding:
    """
        Create a new role binding and publish ``entity.role.assigned``.

        Idempotent on the unique ``(role_id, principal_kind, principal_id,
        scope_kind, scope_id)`` tuple — re-assigning the same binding
        returns the existing row without re-publishing.

        :param db_session: Active SQLAlchemy session.
        :param role_name: Name of the role to assign.
        :param principal_kind: USER or GROUP.
        :param principal_id: UUID of the user or group receiving the binding.
        :param scope_kind: SYSTEM | ORGANIZATION | PROJECT.
        :param scope_id: Project UUID when scope_kind == PROJECT, else None.
        :param inherits_into_project: Only meaningful on ORGANIZATION scope.
        :param actor_user_id: Acting principal UUID, or None for system flows.
        :param commit: Commit (the default); ``False`` leaves the binding
                       in the caller's transaction.

        :returns: The persisted :class:`RbacRoleBinding`.
        :raises: RoleNotFoundError, InvalidBindingScopeError, SemanticError
    """
    _validate_scope_arguments(
        scope_kind=scope_kind,
        scope_id=scope_id,
        inherits_into_project=inherits_into_project,
    )

    role = _resolve_role_by_name(db_session=db_session, role_name=role_name)

    existing = (
        db_session.query(RbacRoleBinding)
        .filter(RbacRoleBinding.role_id == role.role_id)
        .filter(RbacRoleBinding.principal_kind == principal_kind)
        .filter(RbacRoleBinding.principal_id == principal_id)
        .filter(RbacRoleBinding.scope_kind == scope_kind)
        .filter(RbacRoleBinding.scope_id == scope_id)
        .first()
    )
    if existing is not None:
        return existing

    now = utc_now()
    binding = RbacRoleBinding(
        binding_id=new_uuid(),
        role_id=role.role_id,
        principal_kind=principal_kind,
        principal_id=principal_id,
        scope_kind=scope_kind,
        scope_id=scope_id,
        inherits_into_project=inherits_into_project,
        created_at=now,
        created_by=actor_user_id,
    )
    db_session.add(binding)
    db_session.flush()

    payload = {
        "binding_id": str(binding.binding_id),
        "role_name": role_name,
        "principal_kind": principal_kind.value,
        "principal_id": str(principal_id),
        "scope_kind": scope_kind.value,
        "scope_id": str(scope_id) if scope_id is not None else None,
        "inherits_into_project": bool(inherits_into_project),
        "actor_user_id": actor_user_id,
        "created_at": now.isoformat(),
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RbacEventTopics.ROLE_ASSIGNED,
            payload=payload,
            source_event_id=new_uuid(),
        ),
    )
    if commit is True:
        db_session.commit()

    rtnval = binding
    return rtnval


def revoke_role(
        *,
        db_session: DbSession,
        binding_id: str,
        actor_user_id: Optional[str],
        commit: bool = True
    ) -> None:
    """
        Remove a role binding and publish ``entity.role.revoked``.

        :param db_session: Active SQLAlchemy session.
        :param binding_id: UUID of the binding to revoke.
        :param actor_user_id: Acting principal UUID, or None.
        :param commit: Commit (the default); ``False`` leaves the removal
                       in the caller's transaction.

        :returns: None.
        :raises: BindingNotFoundError
    """
    binding = (
        db_session.query(RbacRoleBinding)
        .filter(RbacRoleBinding.binding_id == binding_id)
        .first()
    )
    if binding is None:
        err_msg_lines = ["Cannot revoke role binding — binding id not found."]
        err_msg_lines.append("BINDING_ID: {}".format(binding_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise BindingNotFoundError(err_msg) from None

    role = db_session.query(RbacRole).filter(RbacRole.role_id == binding.role_id).first()
    role_name = role.role_name if role is not None else ""

    snapshot_binding_id = str(binding.binding_id)
    snapshot_principal_kind = binding.principal_kind
    snapshot_principal_id = str(binding.principal_id)
    snapshot_scope_kind = binding.scope_kind
    snapshot_scope_id = str(binding.scope_id) if binding.scope_id is not None else None

    payload = {
        "binding_id": snapshot_binding_id,
        "role_name": role_name,
        "principal_kind": snapshot_principal_kind.value,
        "principal_id": snapshot_principal_id,
        "scope_kind": snapshot_scope_kind.value,
        "scope_id": snapshot_scope_id,
        "actor_user_id": actor_user_id,
        "revoked_at": utc_now().isoformat(),
    }

    db_session.delete(binding)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=RbacEventTopics.ROLE_REVOKED,
            payload=payload,
            source_event_id=new_uuid(),
        ),
    )
    if commit is True:
        db_session.commit()

    return


def list_bindings(
        *,
        db_session: DbSession,
        principal_kind: Optional[PrincipalKind] = None,
        principal_id: Optional[str] = None,
        scope_kind: Optional[BindingScope] = None,
        scope_id: Optional[str] = None
    ) -> List[BindingView]:
    """
        Return bindings matching the optional filters.

        :param db_session: Active SQLAlchemy session.
        :param principal_kind: Limit to USER or GROUP bindings when set.
        :param principal_id: Limit to a specific principal when set.
        :param scope_kind: Limit to SYSTEM | ORGANIZATION | PROJECT when set.
        :param scope_id: Limit to a specific project id when set.

        :returns: List of :class:`BindingView` in binding_id order.
    """
    query = (
        db_session.query(RbacRoleBinding, RbacRole.role_name)
        .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
    )
    if principal_kind is not None:
        query = query.filter(RbacRoleBinding.principal_kind == principal_kind)
    if principal_id is not None:
        query = query.filter(RbacRoleBinding.principal_id == principal_id)
    if scope_kind is not None:
        query = query.filter(RbacRoleBinding.scope_kind == scope_kind)
    if scope_id is not None:
        query = query.filter(RbacRoleBinding.scope_id == scope_id)

    rows = query.order_by(RbacRoleBinding.binding_id.asc()).all()

    rtnval: List[BindingView] = []
    for binding, role_name in rows:
        rtnval.append(BindingView(
            binding_id=str(binding.binding_id),
            role_name=role_name,
            principal_kind=binding.principal_kind,
            principal_id=str(binding.principal_id),
            scope_kind=binding.scope_kind,
            scope_id=str(binding.scope_id) if binding.scope_id is not None else None,
            inherits_into_project=bool(binding.inherits_into_project),
            created_at_iso=binding.created_at.isoformat() if binding.created_at is not None else "",
            created_by=str(binding.created_by) if binding.created_by is not None else None,
        ))
    return rtnval
