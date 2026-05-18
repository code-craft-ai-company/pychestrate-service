"""repair admin rbac bindings

Repair pass for the backfill landed by ``d2e3f4a5b6c7``. The
first cut of that migration normalized the legacy
``user.user_id`` column with ``str(raw_value)``, but on SQLite
that column stores 16 raw bytes (``UUIDType()`` binary mode)
and ``str(bytes_value)`` produces the Python ``repr`` form
(e.g. ``b'%\\xe6b...'``) rather than the canonical UUID hex.
The bogus bindings written that way never match the principal
at evaluator time, so ``/api/v1/me/permissions`` continued to
return an empty array for the alpha admin.

This revision:

1. Deletes every ``rbac_role_bindings`` row whose
   ``principal_id`` does not parse as a valid UUID (the
   malformed rows; well-formed rows from any other source
   are left alone).

2. Re-runs the backfill against the legacy ``user`` table with
   a ``principal_id`` value normalized through
   ``uuid.UUID(bytes=...).__str__()``, so the inserted row's
   id matches the authoritative form
   :class:`AuthPrincipal.user_id` carries.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-05-18 03:00:00+00:00

"""
from typing import Sequence, Union

import uuid

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYSTEM_ADMIN_ROLE_NAME: str = "system-admin"


def _normalize_uuid(*, raw_value: object) -> Union[str, None]:
    """
        Coerce a value pulled out of a SQL row to a canonical
        UUID hex-with-dashes string, regardless of whether the
        column stored it as 16 raw bytes, a hex string, or
        already a :class:`uuid.UUID`. Returns ``None`` when the
        value cannot be coerced.

        Identical to the helper of the same name in revision
        ``d2e3f4a5b6c7`` -- duplicated here so this repair
        migration is self-contained.

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


def _is_well_formed_uuid_text(*, value: str) -> bool:
    """
        Return True when ``value`` parses cleanly as a UUID
        (with or without dashes). ``sqlalchemy_utils.UUIDType``
        stores UUIDs as 32-hex-character strings on SQLite, so
        the bound storage form is dash-less; both forms are
        accepted here.

        :param value: Candidate string.

        :returns: True when parseable as a UUID.
    """
    if value is None:
        return False
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except (ValueError, TypeError):
        return False
    return True


def _legacy_user_table_present(*, bind: sa.engine.Connection) -> bool:
    """
        Report whether the legacy ``user`` table is present.

        :param bind: SQLAlchemy connection.

        :returns: True when the ``user`` table exists.
    """
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()
    rtnval = "user" in table_names
    return rtnval


def upgrade() -> None:
    """
        Delete malformed admin bindings written by the buggy
        first cut of ``d2e3f4a5b6c7`` and re-run the backfill
        with a properly-normalized ``principal_id``.
    """
    bind = op.get_bind()

    # Step 1: locate the system-admin role row (created by
    # the previous migration; no-op fallback if missing).
    role_row = bind.execute(
        sa.text(
            "SELECT role_id FROM rbac_roles WHERE role_name = :role_name"
        ),
        {"role_name": SYSTEM_ADMIN_ROLE_NAME},
    ).fetchone()
    if role_row is None:
        return
    role_id = str(role_row[0])

    # Step 2: scan every SYSTEM-scope binding for the role and
    # delete the ones whose principal_id does not parse as a
    # UUID. Well-formed bindings (including ones a future
    # admin tool may have inserted) survive untouched.
    binding_rows = bind.execute(
        sa.text(
            "SELECT binding_id, principal_id FROM rbac_role_bindings"
            " WHERE role_id = :role_id"
            "  AND scope_kind = :scope_kind"
            "  AND scope_id IS NULL"
        ),
        {"role_id": role_id, "scope_kind": "SYSTEM"},
    ).fetchall()

    for binding_row in binding_rows:
        binding_id = binding_row[0]
        principal_id = binding_row[1]
        if _is_well_formed_uuid_text(value=principal_id) is True:
            continue
        bind.execute(
            sa.text(
                "DELETE FROM rbac_role_bindings"
                " WHERE binding_id = :binding_id"
            ),
            {"binding_id": str(binding_id)},
        )

    # Step 3: re-run the legacy ``user`` table backfill with
    # the corrected normalization. Skip cleanly when the
    # legacy table is absent (dev SQLite deploys that ran
    # auto-create-schema only).
    if _legacy_user_table_present(bind=bind) is False:
        return

    legacy_rows = bind.execute(
        sa.text(
            "SELECT user_id, user_roles FROM \"user\""
            " WHERE user_roles IS NOT NULL"
        )
    ).fetchall()

    for legacy_row in legacy_rows:
        raw_user_id = legacy_row[0]
        roles_csv = legacy_row[1]
        if roles_csv is None:
            continue
        tokens = [tok.strip().lower() for tok in roles_csv.split(",")]
        if "admin" not in tokens:
            continue
        normalized_user_id = _normalize_uuid(raw_value=raw_user_id)
        if normalized_user_id is None:
            continue

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
                "principal_id": normalized_user_id,
                "scope_kind": "SYSTEM",
            },
        ).fetchone()
        if existing is not None:
            continue

        binding_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO rbac_role_bindings ("
                " binding_id, role_id, principal_kind, principal_id,"
                " scope_kind, scope_id, inherits_into_project,"
                " created_at, created_by"
                ") VALUES ("
                " :binding_id, :role_id, :principal_kind, :principal_id,"
                " :scope_kind, NULL, :inherits_into_project,"
                " :created_at, NULL"
                ")"
            ),
            {
                "binding_id": binding_id,
                "role_id": role_id,
                "principal_kind": "USER",
                "principal_id": normalized_user_id,
                "scope_kind": "SYSTEM",
                "inherits_into_project": False,
                "created_at": datetime.now(timezone.utc),
            },
        )
    return


def downgrade() -> None:
    """
        No-op downgrade. The repair pass cannot reconstruct the
        malformed-principal_id rows it deleted (they were never
        useful), and dropping the well-formed bindings would
        regress the alpha admin to the broken state. Leave the
        DB at its repaired shape on downgrade.
    """
    return
