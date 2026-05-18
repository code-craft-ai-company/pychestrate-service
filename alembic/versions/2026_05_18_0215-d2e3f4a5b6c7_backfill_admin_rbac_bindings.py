"""backfill admin rbac bindings

Backfill of the modern :class:`RbacRoleBinding` table for
existing deploys whose only "admin" signal is the legacy
``user.user_roles`` CSV string (the setup wizard writes
``roles="admin"`` to that column when it seeds the first
administrator).

Two things land here:

1. Insert (idempotently) the ``system-admin`` row into
   ``rbac_roles``. The catalog's permission grants for that role
   live in-memory as the :class:`SystemAdminRole`
   :class:`RoleExtension` subclass; the row this migration adds
   is the database half that ``RbacRoleBinding.role_id`` joins
   against.

2. For every row in the legacy ``user`` table whose
   ``user_roles`` CSV contains ``admin`` (case-insensitive,
   whole-token), insert an ``RbacRoleBinding`` at SYSTEM scope
   linking that user to the ``system-admin`` role. Re-running
   this migration is a no-op -- the existence check on the
   ``(role_id, principal_kind, principal_id, scope_kind,
   scope_id)`` unique tuple short-circuits second runs.

After this migration runs against the alpha deploy, the seeded
admin's ``check_permission(user, "system:ui.admin.view")``
returns True and the site shell's ``/api/v1/me/permissions``
endpoint reports the full ``SystemAdminRole`` grant set
instead of the empty array it currently returns.

The legacy ``user`` table is created by the
``include_legacy_core_orm_tables`` revision (340748287bde) which
sits earlier in the chain; SQLite deploys that ran with
``PYCHESTRATE_AUTO_CREATE_SCHEMA=true`` and skipped the legacy
half are handled by a presence-check before the SELECT.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-18 02:15:00+00:00

"""
from typing import Sequence, Union

import uuid

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Stable role-name value the in-tree ``SystemAdminRole``
# extension declares. Mirrored from
# :data:`security.rbac.seeding.SYSTEM_ADMIN_ROLE_NAME` -- keep
# the two strings in sync.
SYSTEM_ADMIN_ROLE_NAME: str = "system-admin"


# Description string written onto the freshly-created
# ``rbac_roles`` row. Cosmetic only -- the evaluator does not
# read it.
SYSTEM_ADMIN_ROLE_DESCRIPTION: str = (
    "Full administrative access to system-scoped capabilities."
)


def _legacy_user_table_present(*, bind: sa.engine.Connection) -> bool:
    """
        Report whether the legacy ``user`` table is present in
        the bound database. Dev deploys that ran with
        ``PYCHESTRATE_AUTO_CREATE_SCHEMA=true`` and never applied
        the legacy-schema migration will not have the table; the
        backfill SELECT below must be skipped on those.

        :param bind: SQLAlchemy connection.

        :returns: True when the ``user`` table exists.
    """
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()
    rtnval = "user" in table_names
    return rtnval


def _ensure_system_admin_role_row(
        *, bind: sa.engine.Connection
    ) -> str:
    """
        Idempotently ensure an ``rbac_roles`` row for
        ``system-admin`` exists. Returns the row's ``role_id``
        as a string (UUID).

        :param bind: SQLAlchemy connection.

        :returns: The system-admin ``role_id`` (UUID string).
    """
    existing = bind.execute(
        sa.text(
            "SELECT role_id FROM rbac_roles WHERE role_name = :role_name"
        ),
        {"role_name": SYSTEM_ADMIN_ROLE_NAME},
    ).fetchone()

    if existing is not None:
        rtnval = str(existing[0])
        return rtnval

    role_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            "INSERT INTO rbac_roles ("
            " role_id, role_name, source, source_name, description,"
            " created_at"
            ") VALUES ("
            " :role_id, :role_name, :source, :source_name, :description,"
            " :created_at"
            ")"
        ),
        {
            "role_id": role_id,
            "role_name": SYSTEM_ADMIN_ROLE_NAME,
            "source": "BUILTIN",
            "source_name": SYSTEM_ADMIN_ROLE_NAME,
            "description": SYSTEM_ADMIN_ROLE_DESCRIPTION,
            "created_at": datetime.now(timezone.utc),
        },
    )

    rtnval = role_id
    return rtnval


def _collect_legacy_admin_user_ids(
        *, bind: sa.engine.Connection
    ) -> list:
    """
        Return the list of ``user.user_id`` UUID strings whose
        ``user.user_roles`` CSV column contains the ``admin``
        token (case-insensitive, whole-token match -- a CSV
        value of ``superadmin,foo`` does NOT match).

        :param bind: SQLAlchemy connection.

        :returns: List of user_id strings.
    """
    rows = bind.execute(
        sa.text(
            "SELECT user_id, user_roles FROM \"user\""
            " WHERE user_roles IS NOT NULL"
        )
    ).fetchall()

    rtnval = []
    for row in rows:
        raw_user_id = row[0]
        roles_csv = row[1]
        if raw_user_id is None:
            continue
        if roles_csv is None:
            continue
        tokens = [tok.strip().lower() for tok in roles_csv.split(",")]
        if "admin" not in tokens:
            continue
        # The legacy ``user.user_id`` column is declared
        # ``UUIDType()`` (binary mode = 16 raw bytes on SQLite),
        # while the modern ``rbac_role_bindings.principal_id``
        # column is declared ``UUIDType(binary=False)`` (hex string).
        # The evaluator joins on the hex form, so the legacy blob
        # must be normalized to a canonical UUID string before
        # the binding is inserted -- otherwise the binding row
        # will never match the principal at evaluation time.
        normalized = _normalize_uuid(raw_value=raw_user_id)
        if normalized is None:
            continue
        rtnval.append(normalized)
    return rtnval


def _normalize_uuid(*, raw_value: object) -> Union[str, None]:
    """
        Coerce a value pulled out of a SQL row to a canonical
        UUID hex-with-dashes string, regardless of whether the
        column stored it as 16 raw bytes (``UUIDType`` binary
        mode), a hex string, or already a :class:`uuid.UUID`.
        Returns ``None`` when the value cannot be coerced.

        :param raw_value: Whatever the driver returned.

        :returns: Canonical UUID string or ``None``.
    """
    if raw_value is None:
        return None
    if isinstance(raw_value, uuid.UUID):
        rtnval = str(raw_value)
        return rtnval
    if isinstance(raw_value, bytes):
        if len(raw_value) != 16:
            return None
        try:
            normalized = uuid.UUID(bytes=raw_value)
        except (ValueError, TypeError):
            return None
        rtnval = str(normalized)
        return rtnval
    if isinstance(raw_value, str):
        try:
            normalized = uuid.UUID(raw_value)
        except (ValueError, TypeError):
            return None
        rtnval = str(normalized)
        return rtnval
    rtnval = None
    return rtnval


def _ensure_system_admin_binding(
        *,
        bind: sa.engine.Connection,
        role_id: str,
        user_id: str
    ) -> None:
    """
        Idempotently insert an ``rbac_role_bindings`` row binding
        ``user_id`` to the ``system-admin`` role at SYSTEM scope.

        :param bind: SQLAlchemy connection.
        :param role_id: The system-admin role's UUID string.
        :param user_id: Target user's UUID string.

        :returns: None.
    """
    existing = bind.execute(
        sa.text(
            "SELECT binding_id FROM rbac_role_bindings"
            " WHERE role_id = :role_id"
            "  AND principal_kind = :principal_kind"
            "  AND principal_id = :principal_id"
            "  AND scope_kind = :scope_kind"
            "  AND scope_id IS NULL"
        ),
        {
            "role_id": role_id,
            "principal_kind": "USER",
            "principal_id": user_id,
            "scope_kind": "SYSTEM",
        },
    ).fetchone()
    if existing is not None:
        return

    binding_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            "INSERT INTO rbac_role_bindings ("
            " binding_id, role_id, principal_kind, principal_id,"
            " scope_kind, scope_id, inherits_into_project, created_at,"
            " created_by"
            ") VALUES ("
            " :binding_id, :role_id, :principal_kind, :principal_id,"
            " :scope_kind, NULL, :inherits_into_project, :created_at,"
            " NULL"
            ")"
        ),
        {
            "binding_id": binding_id,
            "role_id": role_id,
            "principal_kind": "USER",
            "principal_id": user_id,
            "scope_kind": "SYSTEM",
            "inherits_into_project": False,
            "created_at": datetime.now(timezone.utc),
        },
    )
    return


def upgrade() -> None:
    """
        Seed the ``system-admin`` role row and backfill
        ``rbac_role_bindings`` for every legacy admin user.
    """
    bind = op.get_bind()

    role_id = _ensure_system_admin_role_row(bind=bind)

    if _legacy_user_table_present(bind=bind) is False:
        return

    user_ids = _collect_legacy_admin_user_ids(bind=bind)
    for user_id in user_ids:
        _ensure_system_admin_binding(
            bind=bind, role_id=role_id, user_id=user_id
        )
    return


def downgrade() -> None:
    """
        Drop the system-admin bindings + role row this revision
        added. A downgrade leaves the alpha admin without a
        modern RBAC binding; the legacy CSV path remains intact.
    """
    bind = op.get_bind()

    role_row = bind.execute(
        sa.text(
            "SELECT role_id FROM rbac_roles WHERE role_name = :role_name"
        ),
        {"role_name": SYSTEM_ADMIN_ROLE_NAME},
    ).fetchone()
    if role_row is None:
        return

    role_id = str(role_row[0])
    bind.execute(
        sa.text(
            "DELETE FROM rbac_role_bindings"
            " WHERE role_id = :role_id"
            "  AND scope_kind = :scope_kind"
            "  AND scope_id IS NULL"
        ),
        {"role_id": role_id, "scope_kind": "SYSTEM"},
    )
    bind.execute(
        sa.text("DELETE FROM rbac_roles WHERE role_id = :role_id"),
        {"role_id": role_id},
    )
    return
