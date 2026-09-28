"""
.. module:: webinterface.blueprints.config.identity_admin
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Service layer backing the /admin Users and Roles pages,
               ported to the modern identity + RBAC stores.

.. moduleauthor:: Code Craft AI LLC

The admin Users and Roles pages previously read and wrote the legacy
``user`` / ``system_roles`` / ``permissions`` tables, which the login
flow (:mod:`security.auth.local_flow` over ``identity_users`` +
``auth_local_credentials``) and the access evaluator
(:mod:`security.rbac.rbac_evaluator` over ``rbac_role_bindings`` /
``rbac_roles``) never consult. Users created through the UI could never
log in and role grants had no effect on access.

This module gives the pages a truthful backend:

* Users are created / listed / updated in the modern identity store
  (:class:`IdentityUser` + :class:`AuthLocalCredentials`, password
  hashed via ``local_flow.hash_password`` with the active pepper), so a
  freshly created user can immediately authenticate.
* A legacy ``core.orm.User`` mirror row is upserted inside a savepoint
  (exactly like ``identity.setup.testadmin_seeder``) so anything still
  reading the legacy table sees consistent data. A missing legacy table
  (the ``PYCHESTRATE_AUTO_CREATE_SCHEMA`` dev case) never aborts the
  modern commit.
* Role assignment creates / removes :class:`RbacRoleBinding` rows at
  SYSTEM scope -- the rows ``rbac_evaluator.check_permission`` actually
  joins against.
* Role management operates on :class:`RbacRole` rows. Built-in /
  extension-contributed roles (``source != CUSTOM``) carry their grants
  in the in-memory catalog and are read-only here; custom roles store
  their grants as :class:`RbacRolePermission` rows which the evaluator
  honours.

Self-lockout guards refuse (server-side) an admin deactivating their
own account or removing their own ``system-admin`` binding, and role
deletion refuses built-ins and the last role granting the admin UI.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import re
import uuid

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ``MIN_PASSWORD_LENGTH`` is re-exported for callers that read the
# bound from here; the rules themselves live in
# security.auth.password_policy.
from ccai.pychestrate.webservice.security.auth.password_policy import (
    MIN_PASSWORD_LENGTH,
)


ADMIN_UI_PERMISSION_KEY: str = "system:ui.admin.view"

SYSTEM_ADMIN_ROLE_NAME: str = "system-admin"

USER_STATUS_ACTIVE: str = "active"
USER_STATUS_INACTIVE: str = "inactive"
USER_STATUS_INVITED: str = "invited"

_LOGIN_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_LEGACY_STATUS_ACTIVE: str = "active"
_LEGACY_STATUS_INACTIVE: str = "inactive"


_module_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IdentityAdminError(Exception):
    """
        Base class for the admin-page service errors. Carries a
        ``message`` attribute the route handlers surface, and the
        ``field`` of the form input it is about (None when it is about
        no single input), so the page can show it next to that input.
    """

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        """
            Initialize with a user-facing message.

            :param message: Human-readable error description.
            :param field: The form field the error is about, if any.
        """
        self.message = message
        self.field = field
        super().__init__(message)
        return


class AdminValidationError(IdentityAdminError):
    """
        Raised when submitted form data fails validation.
    """
    pass


class AdminDuplicateError(IdentityAdminError):
    """
        Raised when a create would collide with an existing record.
    """
    pass


class AdminNotFoundError(IdentityAdminError):
    """
        Raised when the target user or role does not exist.
    """
    pass


class SelfLockoutError(IdentityAdminError):
    """
        Raised when an admin attempts to deactivate their own account
        or remove their own ``system-admin`` role binding.
    """
    pass


class BuiltinRoleProtectedError(IdentityAdminError):
    """
        Raised when an edit or delete targets a built-in / extension
        role whose grants live in the in-memory catalog.
    """
    pass


class LastAdminRoleError(IdentityAdminError):
    """
        Raised when deleting a role would leave no role granting the
        admin UI permission.
    """
    pass


# ---------------------------------------------------------------------------
# View models consumed by the templates
# ---------------------------------------------------------------------------


@dataclass
class AdminPermissionView:
    """
        One permission entry for the role forms. ``id`` and ``name``
        are both the canonical permission key (the templates use
        ``id`` as the checkbox value and ``name`` as the label).

        :param id: Canonical permission key.
        :param name: Canonical permission key.
        :param description: Free-form description from the catalog.
    """
    id: str
    name: str
    description: str


@dataclass
class AdminRoleView:
    """
        Role row for the Roles pages and the user-form role picker.

        :param id: Role UUID as a string.
        :param name: Role name.
        :param description: Role description.
        :param is_system: True for built-in / extension roles whose
                          grants live in the catalog (read-only here).
        :param permissions: Permission entries the role grants.
        :param binding_count: Number of live bindings referencing the
                              role.
        :param created_at: Row creation timestamp.
    """
    id: str
    name: str
    description: str
    is_system: bool
    permissions: List[AdminPermissionView] = field(default_factory=list)
    binding_count: int = 0
    created_at: Optional[datetime] = None


@dataclass
class AdminUserView:
    """
        User row for the Users pages.

        :param id: Identity user UUID as a string.
        :param username: Login name.
        :param email: Primary email.
        :param display_name: Display name.
        :param firstname: First name from the legacy mirror ("" when
                          the mirror row / table is absent).
        :param lastname: Last name from the legacy mirror.
        :param is_active: True when the identity status is ACTIVE.
        :param roles: RBAC role names bound to the user at SYSTEM
                      scope.
        :param created_at: Identity row creation timestamp.
        :param updated_at: Identity row update timestamp.
        :param status: ``"active"``, ``"inactive"`` (deactivated) or
                       ``"invited"`` (created with an invite link, no
                       password yet).
    """
    id: str
    username: str
    email: str
    display_name: str
    firstname: str
    lastname: str
    is_active: bool
    roles: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status: str = "active"


@dataclass
class AdminUserListResult:
    """
        Result of :func:`list_identity_users`.

        :param users: The page of user views.
        :param total: Total matching users before pagination.
    """
    users: List[AdminUserView]
    total: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_user_uuid(*, user_id: str) -> Optional[uuid.UUID]:
    """
        Parse a path-supplied user id into a UUID. Returns None on
        unparsable input -- callers treat that as not-found.

        :param user_id: Raw user id string.

        :returns: The parsed UUID or None.
    """
    if user_id is None or len(str(user_id).strip()) == 0:
        return None
    try:
        rtnval = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return None
    return rtnval


def _validate_new_user_fields(
        *,
        username: str,
        email: str,
        password: Optional[str],
        display_name: str
    ) -> None:
    """
        Validate the create-user form fields, mirroring the legacy
        UserManager rules so the UI contract is unchanged.

        :param username: Submitted login name.
        :param email: Submitted email.
        :param password: Submitted plaintext password; None for an
                         invited account (the user sets it from the
                         invite link).
        :param display_name: Submitted display name.

        :returns: None.
        :raises: AdminValidationError
    """
    if _LOGIN_NAME_PATTERN.match(username) is None:
        raise AdminValidationError(
            "Username must be 3-64 characters, start with alphanumeric, "
            "and contain only alphanumeric characters, underscores, and "
            "hyphens",
            field="username",
        )
    if _EMAIL_PATTERN.match(email) is None:
        raise AdminValidationError(
            "Email address must conform to standard email format",
            field="email",
        )
    if display_name is None or len(display_name.strip()) == 0:
        raise AdminValidationError("Display name is required", field="display_name")
    if password is not None:
        _validate_password_for_user(
            password=password, login_name=username, email=email
        )
    return


def _validate_password_for_user(
        *,
        password: Optional[str],
        login_name: Optional[str],
        email: Optional[str]
    ) -> None:
    """
        Enforce the shared password policy
        (:mod:`security.auth.password_policy`) for a password being
        set on an account. Every path in this module that stores a
        password goes through here, so the rules the forms state are
        the rules the server applies.

        :param password: Candidate plaintext password.
        :param login_name: The account's login name.
        :param email: The account's email address.

        :returns: None.
        :raises: AdminValidationError
    """
    from ccai.pychestrate.webservice.security.auth.password_policy import (
        check_password_against_policy,
        describe_password_problems,
    )

    problems = check_password_against_policy(
        password=password, login_name=login_name, email=email
    )
    if len(problems) > 0:
        raise AdminValidationError(
            describe_password_problems(problems=problems),
            field="password",
        )
    return


def _upsert_legacy_mirror(
        *,
        db_session: Any,
        user_id: uuid.UUID,
        login: str,
        email: str,
        display_name: str,
        firstname: Optional[str],
        lastname: Optional[str],
        status: str,
        role_names: Optional[List[str]]
    ) -> bool:
    """
        Idempotently upsert the legacy ``user`` row mirroring the
        modern identity record, wrapped in a savepoint so a missing
        legacy table (the ``PYCHESTRATE_AUTO_CREATE_SCHEMA`` dev case)
        does not abort the modern commit. Mirrors the pattern in
        ``identity.setup.testadmin_seeder._write_legacy_admin_row``.

        :param db_session: The active SQLAlchemy session.
        :param user_id: The shared user UUID.
        :param login: Login name.
        :param email: Primary email.
        :param display_name: Display name.
        :param firstname: First name; None leaves an existing row's
                          value untouched.
        :param lastname: Last name; None leaves an existing row's
                         value untouched.
        :param status: Legacy status string ("active" / "inactive").
        :param role_names: RBAC role names to mirror into the legacy
                           CSV column; None leaves the CSV untouched
                           on an existing row.

        :returns: True when the legacy row was written, False when the
                  legacy table is absent.
    """
    from sqlalchemy.exc import OperationalError as _OpError
    from ccai.pychestrate.core.orm import User as _LegacyUser

    legacy_savepoint = db_session.begin_nested()
    legacy_written = False
    try:
        existing_legacy = (
            db_session.query(_LegacyUser)
            .filter(_LegacyUser.id == user_id)
            .first()
        )
        if existing_legacy is not None:
            existing_legacy.email = email
            existing_legacy.login = login
            existing_legacy.display_name = display_name
            if firstname is not None:
                existing_legacy.first_name = firstname
            if lastname is not None:
                existing_legacy.last_name = lastname
            existing_legacy.status = status
            existing_legacy.authtype = "internal"
            if role_names is not None:
                existing_legacy.roles = ",".join(role_names)
        else:
            csv_roles = ""
            if role_names is not None:
                csv_roles = ",".join(role_names)
            legacy_user = _LegacyUser(
                id=user_id,
                first_name=firstname if firstname is not None else "",
                last_name=lastname if lastname is not None else "",
                display_name=display_name,
                email=email,
                login=login,
                ownertag="config-admin",
                status=status,
                roles=csv_roles,
                authtype="internal",
            )
            db_session.add(legacy_user)

        db_session.flush()
        legacy_savepoint.commit()
        legacy_written = True
    except _OpError as op_exc:
        legacy_savepoint.rollback()
        first_line = str(op_exc).split(os.linesep)[0]
        _module_logger.warning(
            "pychestrate.config.legacy_user_skipped reason=%s",
            first_line,
        )
        legacy_written = False

    rtnval = legacy_written
    return rtnval


def _read_legacy_names(
        *,
        db_session: Any,
        user_ids: List[uuid.UUID]
    ) -> Dict[str, Tuple[str, str]]:
    """
        Read (first_name, last_name) for the given users from the
        legacy mirror, tolerating an absent legacy table.

        :param db_session: The active SQLAlchemy session.
        :param user_ids: Identity user UUIDs to look up.

        :returns: Mapping of user-id string to (firstname, lastname).
    """
    rtnval: Dict[str, Tuple[str, str]] = {}
    if user_ids is None or len(user_ids) == 0:
        return rtnval

    from sqlalchemy.exc import OperationalError as _OpError
    from ccai.pychestrate.core.orm import User as _LegacyUser

    legacy_savepoint = db_session.begin_nested()
    try:
        rows = (
            db_session.query(_LegacyUser)
            .filter(_LegacyUser.id.in_(user_ids))
            .all()
        )
        legacy_savepoint.commit()
        for row in rows:
            firstname = row.first_name if row.first_name is not None else ""
            lastname = row.last_name if row.last_name is not None else ""
            rtnval[str(row.id)] = (firstname, lastname)
    except _OpError:
        legacy_savepoint.rollback()

    return rtnval


def _system_role_names_by_user(
        *,
        db_session: Any,
        user_ids: List[uuid.UUID]
    ) -> Dict[str, List[str]]:
    """
        Collect the SYSTEM-scope role names bound directly to each of
        the given users.

        :param db_session: The active SQLAlchemy session.
        :param user_ids: Identity user UUIDs to look up.

        :returns: Mapping of user-id string to sorted role-name list.
    """
    from ccai.pychestrate.webservice.security.rbac.models import (
        BindingScope,
        PrincipalKind,
        RbacRole,
        RbacRoleBinding,
    )

    rtnval: Dict[str, List[str]] = {}
    if user_ids is None or len(user_ids) == 0:
        return rtnval

    rows = (
        db_session.query(RbacRoleBinding.principal_id, RbacRole.role_name)
        .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
        .filter(RbacRoleBinding.principal_kind == PrincipalKind.USER)
        .filter(RbacRoleBinding.principal_id.in_(user_ids))
        .filter(RbacRoleBinding.scope_kind == BindingScope.SYSTEM)
        .all()
    )
    for principal_id, role_name in rows:
        key = str(principal_id)
        if key not in rtnval:
            rtnval[key] = []
        rtnval[key].append(role_name)

    for key in rtnval:
        rtnval[key] = sorted(rtnval[key])

    return rtnval


def _ensure_system_binding(
        *,
        db_session: Any,
        role_name: str,
        principal_uuid: uuid.UUID,
        actor_user_id: Optional[str]
    ) -> Optional[str]:
    """
        Idempotently bind ``role_name`` to the user at SYSTEM scope
        (flush only -- the caller owns the commit). Role rows are
        lazily persisted for catalog-declared roles the way
        ``rbac.seeding.ensure_role_persisted`` does for the setup
        wizard. A new binding stages ``entity.role.assigned``.

        :param db_session: The active SQLAlchemy session.
        :param role_name: Role to bind.
        :param principal_uuid: Target user UUID.
        :param actor_user_id: Acting admin UUID for attribution.

        :returns: The new binding's id, or None when the binding
                  already existed.
        :raises: AdminValidationError when the role name is unknown.
    """
    from ccai.pychestrate.webservice.security.rbac.models import (
        BindingScope,
        PrincipalKind,
        RbacRole,
        RbacRoleBinding,
    )

    role = (
        db_session.query(RbacRole)
        .filter(RbacRole.role_name == role_name)
        .first()
    )
    if role is None:
        from ccai.pychestrate.webservice.security.rbac.catalog import (
            load_catalog_from_registry,
        )
        from ccai.pychestrate.webservice.security.rbac.seeding import (
            ensure_role_persisted,
        )
        catalog = load_catalog_from_registry()
        if role_name not in catalog.roles:
            raise AdminValidationError(
                'Unknown role "{}".'.format(role_name)
            )
        role = ensure_role_persisted(
            db_session=db_session, role_name=role_name
        )

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
        return None

    actor_uuid = None
    if actor_user_id is not None and len(str(actor_user_id)) > 0:
        try:
            actor_uuid = uuid.UUID(str(actor_user_id))
        except (TypeError, ValueError):
            actor_uuid = None

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

    _publish_role_binding_event(
        db_session=db_session,
        topic=_TOPIC_ROLE_ASSIGNED,
        binding_id=str(binding.binding_id),
        role_name=role_name,
        principal_uuid=principal_uuid,
        actor_user_id=actor_user_id,
    )

    rtnval = str(binding.binding_id)
    return rtnval


def _remove_system_bindings(
        *,
        db_session: Any,
        role_names: List[str],
        principal_uuid: uuid.UUID,
        actor_user_id: Optional[str] = None
    ) -> None:
    """
        Remove the user's direct SYSTEM-scope bindings for the given
        role names (flush only -- the caller owns the commit), staging
        ``entity.role.revoked`` for each.

        :param db_session: The active SQLAlchemy session.
        :param role_names: Role names to unbind.
        :param principal_uuid: Target user UUID.
        :param actor_user_id: Acting admin UUID for attribution.

        :returns: None.
    """
    from ccai.pychestrate.webservice.security.rbac.models import (
        BindingScope,
        PrincipalKind,
        RbacRole,
        RbacRoleBinding,
    )

    if role_names is None or len(role_names) == 0:
        return

    rows = (
        db_session.query(RbacRoleBinding, RbacRole.role_name)
        .join(RbacRole, RbacRole.role_id == RbacRoleBinding.role_id)
        .filter(RbacRole.role_name.in_(role_names))
        .filter(RbacRoleBinding.principal_kind == PrincipalKind.USER)
        .filter(RbacRoleBinding.principal_id == principal_uuid)
        .filter(RbacRoleBinding.scope_kind == BindingScope.SYSTEM)
        .all()
    )
    for row, bound_role_name in rows:
        binding_id = str(row.binding_id)
        db_session.delete(row)
        _publish_role_binding_event(
            db_session=db_session,
            topic=_TOPIC_ROLE_REVOKED,
            binding_id=binding_id,
            role_name=bound_role_name,
            principal_uuid=principal_uuid,
            actor_user_id=actor_user_id,
        )
    db_session.flush()
    return


def _invalidate_rbac_cache_for_principal(*, principal_id: str) -> None:
    """
        Drop cached RBAC decisions for the principal so binding
        changes take effect immediately.

        :param principal_id: The user UUID string.

        :returns: None.
    """
    from ccai.pychestrate.webservice.security.rbac import cache as rbac_cache

    rbac_cache.invalidate_principal(principal_id=principal_id)
    return


def _invalidate_rbac_cache_all() -> None:
    """
        Drop every cached RBAC decision. Used after a role's
        permission set changes, which can affect every bound
        principal.

        :returns: None.
    """
    from ccai.pychestrate.webservice.security.rbac import cache as rbac_cache

    rbac_cache.invalidate_all()
    return


def _publish_entity_event(
        *,
        db_session: Any,
        topic: str,
        payload: Dict[str, Any]
    ) -> None:
    """
        Stage an entity event on the session's outbox; it is published
        (and captured into the audit log) only when the caller's
        transaction commits. The acting admin's client address, when
        the request tagged the session with one, rides along.

        :param db_session: The active SQLAlchemy session.
        :param topic: Entity topic (``entity.user.created`` ...).
        :param payload: JSON-serializable payload.

        :returns: None.
    """
    from ccai.pychestrate.core.defaults import new_uuid
    from ccai.pychestrate.webservice.audit.data_change_bridge import (
        session_client_address,
    )
    from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
    from ccai.pychestrate.webservice.messaging.outbox import enqueue_event

    full_payload = dict(payload)
    if "client_address" not in full_payload:
        full_payload["client_address"] = session_client_address(
            db_session=db_session
        )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=topic,
            payload=full_payload,
            source_event_id=new_uuid(),
        ),
    )
    return


def _publish_role_binding_event(
        *,
        db_session: Any,
        topic: str,
        binding_id: Optional[str],
        role_name: str,
        principal_uuid: Any,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Stage ``entity.role.assigned`` / ``entity.role.revoked`` for a
        SYSTEM-scope user binding, in the payload shape
        ``rbac.binding_service`` uses.

        :param db_session: The active SQLAlchemy session.
        :param topic: ``entity.role.assigned`` or ``entity.role.revoked``.
        :param binding_id: The binding's id (None when unknown).
        :param role_name: Role name.
        :param principal_uuid: The user the binding names.
        :param actor_user_id: Acting admin UUID.

        :returns: None.
    """
    from ccai.pychestrate.core.defaults import utc_now

    payload: Dict[str, Any] = {
        "binding_id": binding_id,
        "role_name": role_name,
        "principal_kind": "USER",
        "principal_id": str(principal_uuid),
        "scope_kind": "SYSTEM",
        "scope_id": None,
        "actor_user_id": _actor_text(actor_user_id=actor_user_id),
    }
    if topic.endswith(".assigned") is True:
        payload["created_at"] = utc_now().isoformat()
    else:
        payload["revoked_at"] = utc_now().isoformat()
    _publish_entity_event(db_session=db_session, topic=topic, payload=payload)
    return


def _actor_text(*, actor_user_id: Optional[str]) -> Optional[str]:
    """
        The acting admin's id as text, or None.

        :param actor_user_id: Acting admin UUID (any form).

        :returns: String or None.
    """
    if actor_user_id is None:
        return None
    text = str(actor_user_id).strip()
    if len(text) == 0:
        return None
    return text


_TOPIC_USER_CREATED: str = "entity.user.created"
_TOPIC_USER_UPDATED: str = "entity.user.updated"
_TOPIC_USER_DEACTIVATED: str = "entity.user.deactivated"
_TOPIC_USER_REACTIVATED: str = "entity.user.reactivated"
_TOPIC_ROLE_ASSIGNED: str = "entity.role.assigned"
_TOPIC_ROLE_REVOKED: str = "entity.role.revoked"
_TOPIC_ROLE_CREATED: str = "entity.role.created"
_TOPIC_ROLE_UPDATED: str = "entity.role.updated"
_TOPIC_ROLE_DELETED: str = "entity.role.deleted"


def _user_to_view(
        *,
        user: Any,
        roles: List[str],
        firstname: str,
        lastname: str
    ) -> AdminUserView:
    """
        Convert an :class:`IdentityUser` row plus side-loaded fields
        into an :class:`AdminUserView`.

        :param user: The IdentityUser ORM row.
        :param roles: SYSTEM-scope role names bound to the user.
        :param firstname: First name from the legacy mirror.
        :param lastname: Last name from the legacy mirror.

        :returns: The populated view.
    """
    from ccai.pychestrate.webservice.identity.users.models import UserStatus

    is_active = user.status == UserStatus.ACTIVE
    if user.status == UserStatus.PENDING:
        status_text = USER_STATUS_INVITED
    elif is_active is True:
        status_text = USER_STATUS_ACTIVE
    else:
        status_text = USER_STATUS_INACTIVE

    rtnval = AdminUserView(
        id=str(user.user_id),
        username=user.login_name,
        email=user.primary_email,
        display_name=user.display_name if user.display_name is not None else "",
        firstname=firstname,
        lastname=lastname,
        is_active=is_active,
        roles=roles,
        created_at=user.created_at,
        updated_at=user.updated_at,
        status=status_text,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Users -- public surface
# ---------------------------------------------------------------------------


def list_identity_users(
        *,
        db_session: Any,
        offset: int,
        limit: int,
        search: Optional[str]
    ) -> AdminUserListResult:
    """
        Return a page of identity users with their SYSTEM-scope role
        names, optionally filtered by a search term matched against
        login name, email, and display name.

        :param db_session: The active SQLAlchemy session.
        :param offset: Pagination offset.
        :param limit: Page size.
        :param search: Optional search substring.

        :returns: An :class:`AdminUserListResult`.
    """
    import sqlalchemy as sa

    from ccai.pychestrate.webservice.identity.users.models import IdentityUser

    query = db_session.query(IdentityUser)
    if search is not None and len(search) > 0:
        pattern = "%{}%".format(search)
        query = query.filter(
            sa.or_(
                IdentityUser.login_name.ilike(pattern),
                IdentityUser.primary_email.ilike(pattern),
                IdentityUser.display_name.ilike(pattern),
            )
        )

    total = query.count()
    rows = (
        query.order_by(IdentityUser.login_name.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    user_ids = [row.user_id for row in rows]
    roles_map = _system_role_names_by_user(
        db_session=db_session, user_ids=user_ids
    )
    names_map = _read_legacy_names(
        db_session=db_session, user_ids=user_ids
    )

    users: List[AdminUserView] = []
    for row in rows:
        key = str(row.user_id)
        firstname, lastname = names_map.get(key, ("", ""))
        view = _user_to_view(
            user=row,
            roles=roles_map.get(key, []),
            firstname=firstname,
            lastname=lastname,
        )
        users.append(view)

    rtnval = AdminUserListResult(users=users, total=total)
    return rtnval


def get_identity_user(
        *,
        db_session: Any,
        user_id: str
    ) -> Optional[AdminUserView]:
    """
        Return the view for one identity user, or None when the id is
        unparsable or no such user exists.

        :param db_session: The active SQLAlchemy session.
        :param user_id: Identity user UUID string.

        :returns: The :class:`AdminUserView` or None.
    """
    from ccai.pychestrate.webservice.identity.users.models import IdentityUser

    user_uuid = _parse_user_uuid(user_id=user_id)
    if user_uuid is None:
        return None

    row = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.user_id == user_uuid)
        .first()
    )
    if row is None:
        return None

    roles_map = _system_role_names_by_user(
        db_session=db_session, user_ids=[user_uuid]
    )
    names_map = _read_legacy_names(
        db_session=db_session, user_ids=[user_uuid]
    )
    key = str(user_uuid)
    firstname, lastname = names_map.get(key, ("", ""))

    rtnval = _user_to_view(
        user=row,
        roles=roles_map.get(key, []),
        firstname=firstname,
        lastname=lastname,
    )
    return rtnval


@dataclass
class InvitedUser:
    """
        Result of :func:`create_invited_identity_user`.

        :param user_id: The new account's UUID.
        :param link: The single-use invite link (its secret is shown
                     once and never stored).
    """
    user_id: str
    link: Any


def create_identity_user(
        *,
        db_session: Any,
        username: str,
        email: str,
        password: str,
        display_name: str,
        firstname: str,
        lastname: str,
        role_names: List[str],
        actor_user_id: Optional[str]
    ) -> str:
    """
        Create a user in the modern identity store so they can
        actually log in: an :class:`IdentityUser` row, an
        :class:`AuthLocalCredentials` row hashed via
        ``local_flow.hash_password`` (pepper included), the legacy
        mirror row, and one SYSTEM-scope :class:`RbacRoleBinding` per
        selected role. All writes commit in a single transaction.

        :param db_session: The active SQLAlchemy session.
        :param username: Login name (normalized to lower case).
        :param email: Primary email (normalized to lower case).
        :param password: Plaintext password (hashed before storage).
        :param display_name: Display name.
        :param firstname: First name (legacy mirror only).
        :param lastname: Last name (legacy mirror only).
        :param role_names: RBAC role names to bind at SYSTEM scope.
        :param actor_user_id: Acting admin UUID for attribution.

        :returns: The new user's UUID as a string.
        :raises: AdminValidationError, AdminDuplicateError
    """
    if password is None:
        password = ""
    user_uuid, _link = _create_identity_user(
        db_session=db_session,
        username=username,
        email=email,
        password=password,
        display_name=display_name,
        firstname=firstname,
        lastname=lastname,
        role_names=role_names,
        actor_user_id=actor_user_id,
    )
    rtnval = str(user_uuid)
    return rtnval


def create_invited_identity_user(
        *,
        db_session: Any,
        username: str,
        email: str,
        display_name: str,
        firstname: str,
        lastname: str,
        role_names: List[str],
        actor_user_id: Optional[str]
    ) -> InvitedUser:
    """
        Create an account without a password and a single-use invite
        link for it (audit ADM-04: the product sends no email yet, so
        the administrator copies the link to the user). The account is
        ``PENDING`` -- it cannot sign in -- until the user sets a
        password from the link.

        :param db_session: The active SQLAlchemy session.
        :param username: Login name (normalized to lower case).
        :param email: Primary email (normalized to lower case).
        :param display_name: Display name.
        :param firstname: First name (legacy mirror only).
        :param lastname: Last name (legacy mirror only).
        :param role_names: RBAC role names to bind at SYSTEM scope.
        :param actor_user_id: Acting admin UUID for attribution.

        :returns: :class:`InvitedUser` carrying the one-time link.
        :raises: AdminValidationError, AdminDuplicateError
    """
    user_uuid, link = _create_identity_user(
        db_session=db_session,
        username=username,
        email=email,
        password=None,
        display_name=display_name,
        firstname=firstname,
        lastname=lastname,
        role_names=role_names,
        actor_user_id=actor_user_id,
    )
    rtnval = InvitedUser(user_id=str(user_uuid), link=link)
    return rtnval


def _create_identity_user(
        *,
        db_session: Any,
        username: str,
        email: str,
        password: Optional[str],
        display_name: str,
        firstname: str,
        lastname: str,
        role_names: List[str],
        actor_user_id: Optional[str]
    ) -> Tuple[uuid.UUID, Any]:
    """
        Shared body of :func:`create_identity_user` (``password`` set)
        and :func:`create_invited_identity_user` (``password`` None:
        a ``PENDING`` account, no credentials, an invite link).

        :returns: ``(user_uuid, invite_link_or_None)``.
        :raises: AdminValidationError, AdminDuplicateError
    """
    from ccai.pychestrate.webservice.identity.users.models import (
        IdentityUser,
        UserStatus,
    )
    from ccai.pychestrate.webservice.security.auth import local_flow
    from ccai.pychestrate.webservice.security.auth import password_lifecycle
    from ccai.pychestrate.webservice.security.auth.models import (
        AuthLocalCredentials,
    )

    invited = password is None

    normalized_login = username.strip().lower()
    normalized_email = email.strip().lower()

    _validate_new_user_fields(
        username=normalized_login,
        email=normalized_email,
        password=password,
        display_name=display_name,
    )

    existing_login = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.login_name == normalized_login)
        .first()
    )
    if existing_login is not None:
        raise AdminDuplicateError(
            'A user with login "{}" already exists.'.format(normalized_login),
            field="username",
        )
    existing_email = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.primary_email == normalized_email)
        .first()
    )
    if existing_email is not None:
        raise AdminDuplicateError(
            'A user with email "{}" already exists.'.format(normalized_email),
            field="email",
        )

    if role_names is None:
        role_names = []

    invite_link = None
    try:
        user_uuid = uuid.uuid4()
        modern_user = IdentityUser(
            user_id=user_uuid,
            login_name=normalized_login,
            primary_email=normalized_email,
            display_name=display_name,
            status=UserStatus.PENDING if invited is True else UserStatus.ACTIVE,
            provisioning_source="local",
            external_id=None,
            timezone="UTC",
        )
        db_session.add(modern_user)
        db_session.flush()

        if invited is False:
            encoded_hash, algo_params = local_flow.hash_password(
                password=password
            )
            credentials = AuthLocalCredentials(
                user_id=user_uuid,
                argon2id_hash=encoded_hash,
                algo_params=algo_params,
            )
            db_session.add(credentials)
            db_session.flush()

        _upsert_legacy_mirror(
            db_session=db_session,
            user_id=user_uuid,
            login=normalized_login,
            email=normalized_email,
            display_name=display_name,
            firstname=firstname,
            lastname=lastname,
            status=_LEGACY_STATUS_ACTIVE,
            role_names=role_names,
        )

        for role_name in role_names:
            _ensure_system_binding(
                db_session=db_session,
                role_name=role_name,
                principal_uuid=user_uuid,
                actor_user_id=actor_user_id,
            )

        _publish_entity_event(
            db_session=db_session,
            topic=_TOPIC_USER_CREATED,
            payload={
                "user_id": str(user_uuid),
                "login_name": normalized_login,
                "provisioning_source": "local",
                "invited": invited,
                "actor_user_id": _actor_text(actor_user_id=actor_user_id),
                "created_at": modern_user.created_at.isoformat()
                if modern_user.created_at is not None else None,
            },
        )

        if invited is True:
            invite_link = password_lifecycle.issue_password_link(
                db_session=db_session,
                user_id=str(user_uuid),
                purpose="INVITE",
                actor_user_id=_actor_text(actor_user_id=actor_user_id),
            )

        db_session.commit()
    except IdentityAdminError:
        db_session.rollback()
        raise
    except Exception as commit_exc:
        db_session.rollback()
        err_msg_lines = ["Failed to create the user."]
        err_msg_lines.append("LOGIN: {}".format(normalized_login))
        err_msg_lines.append("CAUSE: {}".format(str(commit_exc)))
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg) from commit_exc

    _invalidate_rbac_cache_for_principal(principal_id=str(user_uuid))

    rtnval = (user_uuid, invite_link)
    return rtnval


def update_identity_user(
        *,
        db_session: Any,
        user_id: str,
        email: str,
        display_name: str,
        firstname: str,
        lastname: str,
        is_active: bool,
        role_names: List[str],
        actor_user_id: Optional[str]
    ) -> None:
    """
        Update the identity row, the legacy mirror, and the user's
        SYSTEM-scope role bindings to match the submitted form.
        Server-side self-lockout guards refuse an admin deactivating
        their own account or removing their own ``system-admin``
        binding.

        :param db_session: The active SQLAlchemy session.
        :param user_id: Target user UUID string.
        :param email: New primary email.
        :param display_name: New display name.
        :param firstname: New first name (legacy mirror only).
        :param lastname: New last name (legacy mirror only).
        :param is_active: Whether the account should be active.
        :param role_names: Full desired SYSTEM-scope role-name set.
        :param actor_user_id: Acting admin UUID.

        :returns: None.
        :raises: AdminNotFoundError, AdminValidationError,
                 AdminDuplicateError, SelfLockoutError
    """
    from ccai.pychestrate.webservice.identity.users.models import (
        IdentityUser,
        UserStatus,
    )

    user_uuid = _parse_user_uuid(user_id=user_id)
    if user_uuid is None:
        raise AdminNotFoundError(
            'User "{}" not found.'.format(user_id)
        )

    row = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.user_id == user_uuid)
        .first()
    )
    if row is None:
        raise AdminNotFoundError(
            'User "{}" not found.'.format(user_id)
        )

    if role_names is None:
        role_names = []

    is_self = False
    if actor_user_id is not None:
        is_self = str(actor_user_id) == str(user_uuid)

    if is_self is True and is_active is False:
        raise SelfLockoutError(
            "You cannot deactivate your own account. Ask another "
            "administrator to deactivate it."
        )

    current_roles_map = _system_role_names_by_user(
        db_session=db_session, user_ids=[user_uuid]
    )
    current_roles = current_roles_map.get(str(user_uuid), [])

    if is_self is True:
        has_admin_now = SYSTEM_ADMIN_ROLE_NAME in current_roles
        keeps_admin = SYSTEM_ADMIN_ROLE_NAME in role_names
        if has_admin_now is True and keeps_admin is False:
            raise SelfLockoutError(
                "You cannot remove your own '{}' role. Ask another "
                "administrator to change it.".format(SYSTEM_ADMIN_ROLE_NAME)
            )

    normalized_email = email.strip().lower()
    if _EMAIL_PATTERN.match(normalized_email) is None:
        raise AdminValidationError(
            "Email address must conform to standard email format",
            field="email",
        )
    if display_name is None or len(display_name.strip()) == 0:
        raise AdminValidationError("Display name is required", field="display_name")

    conflicting_email = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.primary_email == normalized_email)
        .filter(IdentityUser.user_id != user_uuid)
        .first()
    )
    if conflicting_email is not None:
        raise AdminDuplicateError(
            'A user with email "{}" already exists.'.format(normalized_email),
            field="email",
        )

    names_before = _read_legacy_names(
        db_session=db_session, user_ids=[user_uuid]
    ).get(str(user_uuid), ("", ""))
    changed_fields: List[str] = []
    if row.primary_email != normalized_email:
        changed_fields.append("email")
    if (row.display_name or "") != display_name:
        changed_fields.append("display_name")
    if firstname is not None and names_before[0] != firstname:
        changed_fields.append("firstname")
    if lastname is not None and names_before[1] != lastname:
        changed_fields.append("lastname")
    status_before = row.status
    was_active = row.status == UserStatus.ACTIVE
    if row.status == UserStatus.PENDING:
        # An invited account has no password yet: the edit form's
        # Active box neither activates nor deactivates it. The invite
        # link activates it; Deactivate cancels the invitation.
        new_status = UserStatus.PENDING
    elif is_active is True:
        new_status = UserStatus.ACTIVE
    else:
        new_status = UserStatus.DEACTIVATED
    becomes_inactive = was_active is True and new_status == UserStatus.DEACTIVATED
    becomes_active = was_active is False and new_status == UserStatus.ACTIVE

    try:
        row.primary_email = normalized_email
        row.display_name = display_name
        row.status = new_status
        db_session.flush()

        legacy_status = _LEGACY_STATUS_ACTIVE
        if new_status != UserStatus.ACTIVE:
            legacy_status = _LEGACY_STATUS_INACTIVE
        _upsert_legacy_mirror(
            db_session=db_session,
            user_id=user_uuid,
            login=row.login_name,
            email=normalized_email,
            display_name=display_name,
            firstname=firstname,
            lastname=lastname,
            status=legacy_status,
            role_names=role_names,
        )

        roles_to_add = [
            name for name in role_names if name not in current_roles
        ]
        roles_to_remove = [
            name for name in current_roles if name not in role_names
        ]
        # ADM-26: "Updated" on the user pages never moved. Any change
        # to the profile, the status or the roles is an update.
        if (
            len(changed_fields) > 0
            or new_status != status_before
            or len(roles_to_add) > 0
            or len(roles_to_remove) > 0
        ):
            row.updated_at = _utc_now()
        for role_name in roles_to_add:
            _ensure_system_binding(
                db_session=db_session,
                role_name=role_name,
                principal_uuid=user_uuid,
                actor_user_id=actor_user_id,
            )
        _remove_system_bindings(
            db_session=db_session,
            role_names=roles_to_remove,
            principal_uuid=user_uuid,
            actor_user_id=actor_user_id,
        )

        if new_status == UserStatus.DEACTIVATED:
            # Deactivation must end access now, not at session expiry.
            _close_user_sessions(
                db_session=db_session,
                user_uuid=user_uuid,
                actor_user_id=actor_user_id,
            )

        user_event_payload = {
            "user_id": str(user_uuid),
            "login_name": row.login_name,
            "actor_user_id": _actor_text(actor_user_id=actor_user_id),
        }
        if len(changed_fields) > 0:
            updated_payload = dict(user_event_payload)
            updated_payload["changed_fields"] = changed_fields
            _publish_entity_event(
                db_session=db_session,
                topic=_TOPIC_USER_UPDATED,
                payload=updated_payload,
            )
        if becomes_inactive is True:
            _publish_entity_event(
                db_session=db_session,
                topic=_TOPIC_USER_DEACTIVATED,
                payload=user_event_payload,
            )
        if becomes_active is True:
            _publish_entity_event(
                db_session=db_session,
                topic=_TOPIC_USER_REACTIVATED,
                payload=user_event_payload,
            )

        db_session.commit()
    except IdentityAdminError:
        db_session.rollback()
        raise
    except Exception as commit_exc:
        db_session.rollback()
        err_msg_lines = ["Failed to update the user."]
        err_msg_lines.append("USER_ID: {}".format(user_id))
        err_msg_lines.append("CAUSE: {}".format(str(commit_exc)))
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg) from commit_exc

    _invalidate_rbac_cache_for_principal(principal_id=str(user_uuid))
    return


def _utc_now() -> datetime:
    """
        The current time, for ``identity_users.updated_at``.
    """
    from ccai.pychestrate.core.defaults import utc_now  # noqa: E402
    rtnval = utc_now()
    return rtnval


def _close_user_sessions(
        *,
        db_session: Any,
        user_uuid: Any,
        actor_user_id: Optional[str] = None,
        reason: str = "user_deactivated"
    ) -> None:
    """
        Close every sign-in session of a user, in the caller's
        transaction. Deactivation calls this so a deactivated user
        does not keep every permission until their session expires.

        :param db_session: The active SQLAlchemy session.
        :param user_uuid: Identity user id.
        :param actor_user_id: The admin who caused the close.
        :param reason: Why the sessions were closed.

        :returns: None.
    """
    from ccai.pychestrate.webservice.security.auth.session_service import (  # noqa: E402
        close_sessions_for_user,
    )
    close_sessions_for_user(
        db_session=db_session,
        user_id=user_uuid,
        reason=reason,
        actor_user_id=_actor_text(actor_user_id=actor_user_id),
    )
    return


def deactivate_identity_user(
        *,
        db_session: Any,
        user_id: str,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Deactivate the identity user and mirror the status into the
        legacy row. Refuses (server-side) when the admin targets
        their own account.

        :param db_session: The active SQLAlchemy session.
        :param user_id: Target user UUID string.
        :param actor_user_id: Acting admin UUID.

        :returns: None.
        :raises: AdminNotFoundError, SelfLockoutError
    """
    from ccai.pychestrate.webservice.identity.users.models import (
        IdentityUser,
        UserStatus,
    )

    user_uuid = _parse_user_uuid(user_id=user_id)
    if user_uuid is None:
        raise AdminNotFoundError(
            'User "{}" not found.'.format(user_id)
        )

    if actor_user_id is not None and str(actor_user_id) == str(user_uuid):
        raise SelfLockoutError(
            "You cannot deactivate your own account. Ask another "
            "administrator to deactivate it."
        )

    row = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.user_id == user_uuid)
        .first()
    )
    if row is None:
        raise AdminNotFoundError(
            'User "{}" not found.'.format(user_id)
        )

    was_active = row.status == UserStatus.ACTIVE
    was_deactivated = row.status == UserStatus.DEACTIVATED

    try:
        row.status = UserStatus.DEACTIVATED
        if was_deactivated is False:
            row.updated_at = _utc_now()
        db_session.flush()

        _upsert_legacy_mirror(
            db_session=db_session,
            user_id=user_uuid,
            login=row.login_name,
            email=row.primary_email,
            display_name=(
                row.display_name if row.display_name is not None else ""
            ),
            firstname=None,
            lastname=None,
            status=_LEGACY_STATUS_INACTIVE,
            role_names=None,
        )

        # Deactivation must end access now, not at session expiry.
        _close_user_sessions(
            db_session=db_session,
            user_uuid=user_uuid,
            actor_user_id=actor_user_id,
        )

        if was_active is True:
            _publish_entity_event(
                db_session=db_session,
                topic=_TOPIC_USER_DEACTIVATED,
                payload={
                    "user_id": str(user_uuid),
                    "login_name": row.login_name,
                    "actor_user_id": _actor_text(actor_user_id=actor_user_id),
                },
            )

        db_session.commit()
    except Exception as commit_exc:
        db_session.rollback()
        err_msg_lines = ["Failed to deactivate the user."]
        err_msg_lines.append("USER_ID: {}".format(user_id))
        err_msg_lines.append("CAUSE: {}".format(str(commit_exc)))
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg) from commit_exc

    _invalidate_rbac_cache_for_principal(principal_id=str(user_uuid))
    return


def _has_local_password(*, db_session: Any, user_uuid: Any) -> bool:
    """
        Whether the user has a local password (an invited user who
        never opened their link has none).
    """
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthLocalCredentials,
    )
    row = (
        db_session.query(AuthLocalCredentials)
        .filter(AuthLocalCredentials.user_id == user_uuid)
        .first()
    )
    rtnval = row is not None
    return rtnval


def reactivate_identity_user(
        *,
        db_session: Any,
        user_id: str,
        actor_user_id: Optional[str]
    ) -> str:
    """
        Reactivate a deactivated identity user and mirror the status
        into the legacy row. A local account that never set a password
        (a cancelled invitation) goes back to *invited* -- it still
        cannot sign in until the user opens a new invite link -- rather
        than showing as active.

        :param db_session: The active SQLAlchemy session.
        :param user_id: Target user UUID string.
        :param actor_user_id: Acting admin UUID.

        :returns: The resulting status text: :data:`USER_STATUS_ACTIVE`
                  or :data:`USER_STATUS_INVITED`.
        :raises: AdminNotFoundError, AdminValidationError (the user is
                 not deactivated)
    """
    from ccai.pychestrate.webservice.identity.users.models import (
        IdentityUser,
        UserStatus,
    )

    user_uuid = _parse_user_uuid(user_id=user_id)
    if user_uuid is None:
        raise AdminNotFoundError(
            'User "{}" not found.'.format(user_id)
        )

    row = (
        db_session.query(IdentityUser)
        .filter(IdentityUser.user_id == user_uuid)
        .first()
    )
    if row is None:
        raise AdminNotFoundError(
            'User "{}" not found.'.format(user_id)
        )
    if row.status != UserStatus.DEACTIVATED:
        raise AdminValidationError(
            'User "{}" is not deactivated.'.format(row.login_name)
        )

    new_status = UserStatus.ACTIVE
    status_text = USER_STATUS_ACTIVE
    is_local = (row.provisioning_source or "local") == "local"
    if is_local is True and _has_local_password(db_session=db_session, user_uuid=user_uuid) is False:
        new_status = UserStatus.PENDING
        status_text = USER_STATUS_INVITED

    try:
        row.status = new_status
        row.updated_at = _utc_now()
        db_session.flush()

        _upsert_legacy_mirror(
            db_session=db_session,
            user_id=user_uuid,
            login=row.login_name,
            email=row.primary_email,
            display_name=(
                row.display_name if row.display_name is not None else ""
            ),
            firstname=None,
            lastname=None,
            status=(
                _LEGACY_STATUS_ACTIVE if new_status == UserStatus.ACTIVE
                else _LEGACY_STATUS_INACTIVE
            ),
            role_names=None,
        )

        _publish_entity_event(
            db_session=db_session,
            topic=_TOPIC_USER_REACTIVATED,
            payload={
                "user_id": str(user_uuid),
                "login_name": row.login_name,
                "status": status_text,
                "actor_user_id": _actor_text(actor_user_id=actor_user_id),
            },
        )

        db_session.commit()
    except Exception as commit_exc:
        db_session.rollback()
        err_msg_lines = ["Failed to reactivate the user."]
        err_msg_lines.append("USER_ID: {}".format(user_id))
        err_msg_lines.append("CAUSE: {}".format(str(commit_exc)))
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg) from commit_exc

    _invalidate_rbac_cache_for_principal(principal_id=str(user_uuid))
    return status_text


# ---------------------------------------------------------------------------
# Roles -- public surface
# ---------------------------------------------------------------------------


def ensure_catalog_roles_persisted(*, db_session: Any) -> None:
    """
        Idempotently persist an :class:`RbacRole` row for every role
        the in-memory catalog declares, so the Roles page and the
        user-form role picker list the full role set with stable ids.
        Commits only when a row was created.

        :param db_session: The active SQLAlchemy session.

        :returns: None.
    """
    from ccai.pychestrate.webservice.security.rbac.catalog import (
        load_catalog_from_registry,
    )
    from ccai.pychestrate.webservice.security.rbac.models import RbacRole
    from ccai.pychestrate.webservice.security.rbac.seeding import (
        ensure_role_persisted,
    )

    catalog = load_catalog_from_registry()
    existing_names = set()
    rows = db_session.query(RbacRole.role_name).all()
    for row in rows:
        existing_names.add(row[0])

    created_any = False
    for role_name in catalog.roles:
        if role_name in existing_names:
            continue
        ensure_role_persisted(db_session=db_session, role_name=role_name)
        created_any = True

    if created_any is True:
        db_session.commit()
    return


def _role_permissions_view(
        *,
        db_session: Any,
        role: Any,
        catalog: Any
    ) -> List[AdminPermissionView]:
    """
        Resolve the permission entries a role grants: catalog grants
        for built-in / extension roles, :class:`RbacRolePermission`
        rows for custom roles.

        :param db_session: The active SQLAlchemy session.
        :param role: The RbacRole ORM row.
        :param catalog: A loaded :class:`CatalogSnapshot`.

        :returns: Sorted list of :class:`AdminPermissionView`.
    """
    from ccai.pychestrate.webservice.security.rbac.models import (
        PermissionEffect,
        RbacRolePermission,
        RoleSource,
    )

    entries: List[AdminPermissionView] = []

    if role.source != RoleSource.CUSTOM:
        grants = catalog.roles.get(role.role_name, ())
        for grant in grants:
            description = ""
            descriptor = catalog.permissions.get(grant.permission_key, None)
            if descriptor is not None:
                description = descriptor.description
            if grant.effect == PermissionEffect.DENY:
                description = "(deny) {}".format(description)
            entries.append(AdminPermissionView(
                id=grant.permission_key,
                name=grant.permission_key,
                description=description,
            ))
    else:
        rows = (
            db_session.query(RbacRolePermission)
            .filter(RbacRolePermission.role_id == role.role_id)
            .all()
        )
        for row in rows:
            description = ""
            descriptor = catalog.permissions.get(row.permission_key, None)
            if descriptor is not None:
                description = descriptor.description
            if row.effect == PermissionEffect.DENY:
                description = "(deny) {}".format(description)
            entries.append(AdminPermissionView(
                id=row.permission_key,
                name=row.permission_key,
                description=description,
            ))

    entries.sort(key=lambda entry: entry.name)
    rtnval = entries
    return rtnval


def _role_to_view(
        *,
        db_session: Any,
        role: Any,
        catalog: Any,
        binding_count: int
    ) -> AdminRoleView:
    """
        Convert an :class:`RbacRole` row into an
        :class:`AdminRoleView` with its permission entries.

        :param db_session: The active SQLAlchemy session.
        :param role: The RbacRole ORM row.
        :param catalog: A loaded :class:`CatalogSnapshot`.
        :param binding_count: Number of live bindings for the role.

        :returns: The populated view.
    """
    from ccai.pychestrate.webservice.security.rbac.models import RoleSource

    permissions = _role_permissions_view(
        db_session=db_session, role=role, catalog=catalog
    )
    is_system = role.source != RoleSource.CUSTOM

    rtnval = AdminRoleView(
        id=str(role.role_id),
        name=role.role_name,
        description=role.description if role.description is not None else "",
        is_system=is_system,
        permissions=permissions,
        binding_count=binding_count,
        created_at=role.created_at,
    )
    return rtnval


def list_rbac_roles(*, db_session: Any) -> List[AdminRoleView]:
    """
        Return every RBAC role with its permission entries and live
        binding count, ordered by role name.

        :param db_session: The active SQLAlchemy session.

        :returns: List of :class:`AdminRoleView`.
    """
    import sqlalchemy as sa

    from ccai.pychestrate.webservice.security.rbac.catalog import (
        load_catalog_from_registry,
    )
    from ccai.pychestrate.webservice.security.rbac.models import (
        RbacRole,
        RbacRoleBinding,
    )

    catalog = load_catalog_from_registry()

    counts: Dict[str, int] = {}
    count_rows = (
        db_session.query(
            RbacRoleBinding.role_id,
            sa.func.count(RbacRoleBinding.binding_id),
        )
        .group_by(RbacRoleBinding.role_id)
        .all()
    )
    for role_id, count in count_rows:
        counts[str(role_id)] = int(count)

    rows = (
        db_session.query(RbacRole)
        .order_by(RbacRole.role_name.asc())
        .all()
    )

    rtnval: List[AdminRoleView] = []
    for row in rows:
        view = _role_to_view(
            db_session=db_session,
            role=row,
            catalog=catalog,
            binding_count=counts.get(str(row.role_id), 0),
        )
        rtnval.append(view)
    return rtnval


def get_rbac_role(
        *,
        db_session: Any,
        role_id: str
    ) -> Optional[AdminRoleView]:
    """
        Return the view for one role, or None when the id is
        unparsable or no such role exists.

        :param db_session: The active SQLAlchemy session.
        :param role_id: Role UUID string.

        :returns: The :class:`AdminRoleView` or None.
    """
    from ccai.pychestrate.webservice.security.rbac.catalog import (
        load_catalog_from_registry,
    )

    role = _load_role_row(db_session=db_session, role_id=role_id)
    if role is None:
        return None

    catalog = load_catalog_from_registry()
    binding_count = count_role_bindings(
        db_session=db_session, role_id=role_id
    )

    rtnval = _role_to_view(
        db_session=db_session,
        role=role,
        catalog=catalog,
        binding_count=binding_count,
    )
    return rtnval


def _load_role_row(*, db_session: Any, role_id: str) -> Optional[Any]:
    """
        Load the :class:`RbacRole` row for a path-supplied role id.
        Returns None on unparsable input or a missing row.

        :param db_session: The active SQLAlchemy session.
        :param role_id: Role UUID string.

        :returns: The RbacRole ORM row or None.
    """
    from ccai.pychestrate.webservice.security.rbac.models import RbacRole

    role_uuid = _parse_user_uuid(user_id=role_id)
    if role_uuid is None:
        return None

    rtnval = (
        db_session.query(RbacRole)
        .filter(RbacRole.role_id == role_uuid)
        .first()
    )
    return rtnval


def count_role_bindings(*, db_session: Any, role_id: str) -> int:
    """
        Return the number of live bindings referencing the role.

        :param db_session: The active SQLAlchemy session.
        :param role_id: Role UUID string.

        :returns: The binding count (0 for an unknown role).
    """
    from ccai.pychestrate.webservice.security.rbac.models import (
        RbacRoleBinding,
    )

    role_uuid = _parse_user_uuid(user_id=role_id)
    if role_uuid is None:
        return 0

    rtnval = (
        db_session.query(RbacRoleBinding)
        .filter(RbacRoleBinding.role_id == role_uuid)
        .count()
    )
    return rtnval


def list_catalog_permissions() -> List[AdminPermissionView]:
    """
        Return every system-namespace permission key registered in
        the catalog (the ``core_permissions`` extension plus any other
        registered packs), sorted by key. This is the source of valid
        keys for the role forms.

        :returns: List of :class:`AdminPermissionView`.
    """
    from ccai.pychestrate.webservice.security.rbac.catalog import (
        load_catalog_from_registry,
    )

    catalog = load_catalog_from_registry()

    rtnval: List[AdminPermissionView] = []
    for permission_key in sorted(catalog.permissions.keys()):
        descriptor = catalog.permissions[permission_key]
        if descriptor.namespace != "system":
            continue
        rtnval.append(AdminPermissionView(
            id=permission_key,
            name=permission_key,
            description=descriptor.description,
        ))
    return rtnval


def _validate_permission_keys(*, permission_keys: List[str]) -> None:
    """
        Refuse permission keys the catalog does not declare, so a
        custom role can only grant registered permissions.

        :param permission_keys: The submitted key list.

        :returns: None.
        :raises: AdminValidationError
    """
    from ccai.pychestrate.webservice.security.rbac.catalog import (
        load_catalog_from_registry,
    )

    if permission_keys is None or len(permission_keys) == 0:
        return

    catalog = load_catalog_from_registry()
    unknown = [
        key for key in permission_keys if key not in catalog.permissions
    ]
    if len(unknown) > 0:
        err_msg_lines = ["Unknown permission keys were submitted."]
        err_msg_lines.append("UNKNOWN: ({})".format(len(unknown)))
        for key in unknown:
            err_msg_lines.append("    {}".format(key))
        err_msg = os.linesep.join(err_msg_lines)
        raise AdminValidationError(err_msg)
    return


def create_rbac_role(
        *,
        db_session: Any,
        name: str,
        description: str,
        permission_keys: List[str],
        actor_user_id: Optional[str] = None
    ) -> str:
    """
        Create a custom :class:`RbacRole` with the selected catalog
        permission keys stored as ALLOW :class:`RbacRolePermission`
        rows -- the relation the evaluator honours for custom roles.

        :param db_session: The active SQLAlchemy session.
        :param name: Role name (must be unique).
        :param description: Role description.
        :param permission_keys: Catalog permission keys to grant.
        :param actor_user_id: Acting admin UUID (audit attribution).

        :returns: The new role's UUID as a string.
        :raises: AdminValidationError, AdminDuplicateError
    """
    from ccai.pychestrate.webservice.security.rbac.models import (
        PermissionEffect,
        RbacRole,
        RbacRolePermission,
        RoleSource,
    )

    stripped_name = name.strip() if name is not None else ""
    if len(stripped_name) == 0:
        raise AdminValidationError("Role name is required.", field="name")
    if len(stripped_name) > 128:
        raise AdminValidationError(
            "Role name must be 128 characters or fewer.",
            field="name",
        )

    existing = (
        db_session.query(RbacRole)
        .filter(RbacRole.role_name == stripped_name)
        .first()
    )
    if existing is not None:
        raise AdminDuplicateError(
            'Role "{}" already exists.'.format(stripped_name),
            field="name",
        )

    if permission_keys is None:
        permission_keys = []
    _validate_permission_keys(permission_keys=permission_keys)

    try:
        role_uuid = uuid.uuid4()
        role = RbacRole(
            role_id=role_uuid,
            role_name=stripped_name,
            source=RoleSource.CUSTOM,
            source_name=None,
            description=description if description is not None else "",
        )
        db_session.add(role)
        db_session.flush()

        for permission_key in sorted(set(permission_keys)):
            grant_row = RbacRolePermission(
                role_id=role_uuid,
                permission_key=permission_key,
                effect=PermissionEffect.ALLOW,
            )
            db_session.add(grant_row)
        db_session.flush()

        _publish_entity_event(
            db_session=db_session,
            topic=_TOPIC_ROLE_CREATED,
            payload={
                "role_id": str(role_uuid),
                "role_name": stripped_name,
                "permission_keys": sorted(set(permission_keys)),
                "actor_user_id": _actor_text(actor_user_id=actor_user_id),
            },
        )

        db_session.commit()
    except IdentityAdminError:
        db_session.rollback()
        raise
    except Exception as commit_exc:
        db_session.rollback()
        err_msg_lines = ["Failed to create the role."]
        err_msg_lines.append("ROLE_NAME: {}".format(stripped_name))
        err_msg_lines.append("CAUSE: {}".format(str(commit_exc)))
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg) from commit_exc

    rtnval = str(role_uuid)
    return rtnval


def update_rbac_role(
        *,
        db_session: Any,
        role_id: str,
        description: str,
        permission_keys: List[str],
        actor_user_id: Optional[str] = None
    ) -> None:
    """
        Update a custom role's description and replace its
        :class:`RbacRolePermission` rows with the submitted keys.
        Built-in / extension roles are refused -- their grants live in
        the in-memory catalog and editing the rows would silently
        diverge from the seeded truth.

        :param db_session: The active SQLAlchemy session.
        :param role_id: Role UUID string.
        :param description: New description.
        :param permission_keys: Full desired ALLOW key set.
        :param actor_user_id: Acting admin UUID (audit attribution).

        :returns: None.
        :raises: AdminNotFoundError, BuiltinRoleProtectedError,
                 AdminValidationError
    """
    from ccai.pychestrate.webservice.security.rbac.models import (
        PermissionEffect,
        RbacRolePermission,
        RoleSource,
    )

    role = _load_role_row(db_session=db_session, role_id=role_id)
    if role is None:
        raise AdminNotFoundError(
            'Role "{}" not found.'.format(role_id)
        )

    if role.source != RoleSource.CUSTOM:
        raise BuiltinRoleProtectedError(
            'Role "{}" is a built-in role. Its permissions are defined '
            "by the system and cannot be edited.".format(role.role_name)
        )

    if permission_keys is None:
        permission_keys = []
    _validate_permission_keys(permission_keys=permission_keys)

    try:
        role.description = description if description is not None else ""

        existing_rows = (
            db_session.query(RbacRolePermission)
            .filter(RbacRolePermission.role_id == role.role_id)
            .all()
        )
        for row in existing_rows:
            db_session.delete(row)
        db_session.flush()

        for permission_key in sorted(set(permission_keys)):
            grant_row = RbacRolePermission(
                role_id=role.role_id,
                permission_key=permission_key,
                effect=PermissionEffect.ALLOW,
            )
            db_session.add(grant_row)
        db_session.flush()

        _publish_entity_event(
            db_session=db_session,
            topic=_TOPIC_ROLE_UPDATED,
            payload={
                "role_id": str(role.role_id),
                "role_name": role.role_name,
                "permission_keys": sorted(set(permission_keys)),
                "actor_user_id": _actor_text(actor_user_id=actor_user_id),
            },
        )

        db_session.commit()
    except IdentityAdminError:
        db_session.rollback()
        raise
    except Exception as commit_exc:
        db_session.rollback()
        err_msg_lines = ["Failed to update the role."]
        err_msg_lines.append("ROLE_ID: {}".format(role_id))
        err_msg_lines.append("CAUSE: {}".format(str(commit_exc)))
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg) from commit_exc

    _invalidate_rbac_cache_all()
    return


def delete_rbac_role(
        *,
        db_session: Any,
        role_id: str,
        actor_user_id: Optional[str] = None
    ) -> int:
    """
        Delete a custom role, its permission rows, and every binding
        referencing it. Refuses built-in / extension roles and the
        last role granting the admin UI permission
        (``system:ui.admin.view``).

        :param db_session: The active SQLAlchemy session.
        :param role_id: Role UUID string.
        :param actor_user_id: Acting admin UUID (audit attribution).

        :returns: The number of bindings that were removed (the "N
                  users lose this role" count).
        :raises: AdminNotFoundError, BuiltinRoleProtectedError,
                 LastAdminRoleError
    """
    from ccai.pychestrate.webservice.security.rbac.catalog import (
        load_catalog_from_registry,
    )
    from ccai.pychestrate.webservice.security.rbac.models import (
        PermissionEffect,
        RbacRole,
        RbacRolePermission,
        RbacRoleBinding,
        RoleSource,
    )

    role = _load_role_row(db_session=db_session, role_id=role_id)
    if role is None:
        raise AdminNotFoundError(
            'Role "{}" not found.'.format(role_id)
        )

    if role.source != RoleSource.CUSTOM:
        raise BuiltinRoleProtectedError(
            'Role "{}" is a built-in role and cannot be '
            "deleted.".format(role.role_name)
        )

    # Guard: never delete the last role that grants the admin UI.
    own_rows = (
        db_session.query(RbacRolePermission)
        .filter(RbacRolePermission.role_id == role.role_id)
        .all()
    )
    grants_admin_ui = False
    for row in own_rows:
        if (
            row.permission_key == ADMIN_UI_PERMISSION_KEY
            and row.effect == PermissionEffect.ALLOW
        ):
            grants_admin_ui = True
            break

    if grants_admin_ui is True:
        catalog = load_catalog_from_registry()
        another_grants = False
        for role_name, grants in catalog.roles.items():
            if role_name == role.role_name:
                continue
            for grant in grants:
                if (
                    grant.permission_key == ADMIN_UI_PERMISSION_KEY
                    and grant.effect == PermissionEffect.ALLOW
                ):
                    another_grants = True
                    break
            if another_grants is True:
                break
        if another_grants is False:
            other_rows = (
                db_session.query(RbacRolePermission)
                .filter(RbacRolePermission.role_id != role.role_id)
                .filter(
                    RbacRolePermission.permission_key
                    == ADMIN_UI_PERMISSION_KEY
                )
                .filter(
                    RbacRolePermission.effect == PermissionEffect.ALLOW
                )
                .all()
            )
            if len(other_rows) == 0:
                raise LastAdminRoleError(
                    'Role "{}" is the last role granting the admin UI '
                    "and cannot be deleted.".format(role.role_name)
                )

    binding_rows = (
        db_session.query(RbacRoleBinding)
        .filter(RbacRoleBinding.role_id == role.role_id)
        .all()
    )
    removed_binding_count = len(binding_rows)

    deleted_role_id = str(role.role_id)
    deleted_role_name = role.role_name

    try:
        for binding in binding_rows:
            db_session.delete(binding)
        for row in own_rows:
            db_session.delete(row)
        db_session.delete(role)
        db_session.flush()

        _publish_entity_event(
            db_session=db_session,
            topic=_TOPIC_ROLE_DELETED,
            payload={
                "role_id": deleted_role_id,
                "role_name": deleted_role_name,
                "removed_binding_count": removed_binding_count,
                "actor_user_id": _actor_text(actor_user_id=actor_user_id),
            },
        )

        db_session.commit()
    except Exception as commit_exc:
        db_session.rollback()
        err_msg_lines = ["Failed to delete the role."]
        err_msg_lines.append("ROLE_ID: {}".format(role_id))
        err_msg_lines.append("CAUSE: {}".format(str(commit_exc)))
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg) from commit_exc

    _invalidate_rbac_cache_all()

    rtnval = removed_binding_count
    return rtnval


__all__ = [
    "ADMIN_UI_PERMISSION_KEY",
    "SYSTEM_ADMIN_ROLE_NAME",
    "AdminDuplicateError",
    "AdminNotFoundError",
    "AdminPermissionView",
    "AdminRoleView",
    "AdminUserListResult",
    "AdminUserView",
    "AdminValidationError",
    "BuiltinRoleProtectedError",
    "IdentityAdminError",
    "LastAdminRoleError",
    "SelfLockoutError",
    "count_role_bindings",
    "InvitedUser",
    "USER_STATUS_ACTIVE",
    "USER_STATUS_INACTIVE",
    "USER_STATUS_INVITED",
    "reactivate_identity_user",
    "create_identity_user",
    "create_invited_identity_user",
    "create_rbac_role",
    "deactivate_identity_user",
    "delete_rbac_role",
    "ensure_catalog_roles_persisted",
    "get_identity_user",
    "get_rbac_role",
    "list_catalog_permissions",
    "list_identity_users",
    "list_rbac_roles",
    "update_identity_user",
    "update_rbac_role",
]
