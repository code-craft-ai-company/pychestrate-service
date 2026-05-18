"""normalize admin rbac uuid storage

Second repair pass: the rbac role + bindings rows written by
``d2e3f4a5b6c7`` / ``e3f4a5b6c7d8`` used the 36-char dashed
form (``str(uuid.UUID)``) for both ``role_id`` and
``principal_id``. ``sqlalchemy_utils.UUIDType(binary=False)``
stores UUIDs on SQLite as 32-char dashless hex
(``uuid.UUID.hex``) and its ``process_bind_param`` normalizes
query parameters to the same form -- so dashed-form rows on
disk never compare equal to bound parameters at query time
and the SQLAlchemy join in ``rbac_evaluator`` returns nothing.

This revision rewrites every ``rbac_roles.role_id`` and
``rbac_role_bindings.role_id`` / ``rbac_role_bindings.principal_id``
column in place to the canonical 32-char form when (and only
when) the existing on-disk value is a parseable UUID stored in
a non-canonical shape. It is a no-op when no rows need
rewriting, so subsequent runs and fresh deploys (whose rows
were written through the type's bind processor and are
already canonical) skip cleanly.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-05-18 04:00:00+00:00

"""
from typing import Sequence, Union

import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _to_canonical_storage_form(*, raw_value: object) -> Union[str, None]:
    """
        Coerce a value pulled out of a SQL row to the canonical
        on-disk UUID storage form used by
        ``sqlalchemy_utils.UUIDType(binary=False)`` on SQLite
        (32 lowercase hex chars, no dashes). Returns ``None``
        when the value is not a parseable UUID.

        :param raw_value: Whatever the driver returned.

        :returns: 32-char canonical hex string or ``None``.
    """
    if raw_value is None:
        return None
    if isinstance(raw_value, uuid.UUID):
        rtnval = raw_value.hex
        return rtnval
    if isinstance(raw_value, bytes):
        if len(raw_value) != 16:
            return None
        try:
            parsed = uuid.UUID(bytes=raw_value)
        except (ValueError, TypeError):
            return None
        rtnval = parsed.hex
        return rtnval
    if isinstance(raw_value, str):
        try:
            parsed = uuid.UUID(raw_value)
        except (ValueError, TypeError):
            return None
        rtnval = parsed.hex
        return rtnval
    rtnval = None
    return rtnval


def _rewrite_rbac_roles(*, bind: sa.engine.Connection) -> dict:
    """
        Rewrite every ``rbac_roles.role_id`` to the canonical
        32-char form when the on-disk value is in a different
        shape. Returns a mapping of ``old_value -> new_value``
        for the caller to propagate across the bindings table.

        :param bind: SQLAlchemy connection.

        :returns: Dict of ``{old_role_id: new_role_id}`` for
                  rows that were rewritten.
    """
    rows = bind.execute(sa.text("SELECT role_id FROM rbac_roles")).fetchall()

    rtnval: dict = {}
    for row in rows:
        old_value = row[0]
        new_value = _to_canonical_storage_form(raw_value=old_value)
        if new_value is None:
            continue
        if new_value == old_value:
            continue
        bind.execute(
            sa.text(
                "UPDATE rbac_roles SET role_id = :new_value"
                " WHERE role_id = :old_value"
            ),
            {"new_value": new_value, "old_value": old_value},
        )
        rtnval[old_value] = new_value
    return rtnval


def _rewrite_rbac_role_bindings(
        *,
        bind: sa.engine.Connection,
        role_id_remap: dict
    ) -> None:
    """
        Rewrite every ``rbac_role_bindings`` row whose
        ``role_id`` / ``principal_id`` / ``binding_id`` columns
        carry a non-canonical UUID storage shape. Also applies
        the role_id remap produced by :func:`_rewrite_rbac_roles`
        so the foreign-key edge stays intact.

        :param bind: SQLAlchemy connection.
        :param role_id_remap: ``{old_role_id: new_role_id}``
                              produced by the role rewrite pass.

        :returns: None.
    """
    rows = bind.execute(
        sa.text(
            "SELECT binding_id, role_id, principal_id"
            " FROM rbac_role_bindings"
        )
    ).fetchall()

    for row in rows:
        old_binding_id = row[0]
        old_role_id = row[1]
        old_principal_id = row[2]

        new_binding_id = _to_canonical_storage_form(raw_value=old_binding_id)
        new_principal_id = _to_canonical_storage_form(raw_value=old_principal_id)

        # role_id flips through the remap first (in case the
        # parent table renamed it) and only falls back to the
        # value-as-stored if the remap had nothing to say.
        if old_role_id in role_id_remap:
            new_role_id = role_id_remap[old_role_id]
        else:
            new_role_id = _to_canonical_storage_form(raw_value=old_role_id)

        if new_binding_id is None:
            continue
        if new_role_id is None:
            continue
        if new_principal_id is None:
            continue

        if (
            new_binding_id == old_binding_id
            and new_role_id == old_role_id
            and new_principal_id == old_principal_id
        ):
            continue

        bind.execute(
            sa.text(
                "UPDATE rbac_role_bindings"
                " SET binding_id = :new_binding_id,"
                "     role_id = :new_role_id,"
                "     principal_id = :new_principal_id"
                " WHERE binding_id = :old_binding_id"
            ),
            {
                "new_binding_id": new_binding_id,
                "new_role_id": new_role_id,
                "new_principal_id": new_principal_id,
                "old_binding_id": old_binding_id,
            },
        )
    return


def upgrade() -> None:
    """
        Normalize every UUID-typed column in ``rbac_roles`` and
        ``rbac_role_bindings`` to the canonical 32-char hex
        storage form.
    """
    bind = op.get_bind()
    role_id_remap = _rewrite_rbac_roles(bind=bind)
    _rewrite_rbac_role_bindings(
        bind=bind, role_id_remap=role_id_remap
    )
    return


def downgrade() -> None:
    """
        No-op downgrade. The canonical-storage form is what
        every SQLAlchemy bind-path writes; reverting to the
        dashed form would re-break the evaluator.
    """
    return
