"""variables: description, default and history, and the legacy variables copied in

Adds ``description``, ``default_value_text`` and ``created_at`` to ``variables_variable_bindings`` and a ``variables_binding_history`` table, so the modern
variables store holds everything the Admin Variables pages show (audit ADM-08, ``specs/model-convergence.md`` section 8).

Then copies the legacy ``global_variables`` rows (and their ``global_variable_history``) into the modern store as SYSTEM-scope bindings, one name at a time and only
where the modern store has no SYSTEM binding of that name, so a variable somebody already set through the API wins. The legacy tables are not touched: a rollback is a
redeploy of the previous release, and a later step removes them.

Revision ID: f7b2c9a4d1e6
Revises: e3b9c6d1f472
Create Date: 2026-10-15 04:00:00+00:00

"""
import json
import uuid

from typing import Any, Dict, Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils

from sqlalchemy.dialects import postgresql

from ccai.pychestrate.core.utc_datetime import UtcDateTime


# revision identifiers, used by Alembic.
revision: str = "f7b2c9a4d1e6"
down_revision: Union[str, Sequence[str], None] = "e3b9c6d1f472"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCOPES = ("SYSTEM", "PROJECT", "PIPELINE", "JOB")
_TYPES = ("STRING", "INTEGER", "FLOAT", "BOOLEAN", "JSON", "SECRET_REF")


def _enum(values: Sequence[str], name: str) -> sa.types.TypeEngine:
    """
        The enum the baseline created, without trying to create its type again on PostgreSQL.
    """
    rtnval = sa.Enum(*values, name=name).with_variant(postgresql.ENUM(*values, name=name, create_type=False), "postgresql")
    return rtnval


def upgrade() -> None:
    """
        Add the columns and the history table, then copy the legacy variables.
    """
    with op.batch_alter_table("variables_variable_bindings") as batch:
        batch.add_column(sa.Column("description", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("default_value_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "variables_binding_history",
        sa.Column("history_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("scope", _enum(_SCOPES, "variables_variable_scope"), nullable=False),
        sa.Column("scope_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("value_type", _enum(_TYPES, "variables_value_type"), nullable=False),
        sa.Column("old_value_text", sa.Text(), nullable=True),
        sa.Column("new_value_text", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("history_id"),
    )
    op.create_index("ix_variables_history_name", "variables_binding_history", ["scope", "scope_id", "name", "changed_at"], unique=False)

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE variables_variable_bindings SET created_at = set_at WHERE created_at IS NULL"))
    _copy_legacy_variables(bind)
    return


def downgrade() -> None:
    """
        Drop the history table and the new columns. The copied bindings stay (they are valid rows of the older schema); the legacy tables were never touched.
    """
    op.drop_index("ix_variables_history_name", table_name="variables_binding_history")
    op.drop_table("variables_binding_history")
    with op.batch_alter_table("variables_variable_bindings") as batch:
        batch.drop_column("created_at")
        batch.drop_column("default_value_text")
        batch.drop_column("description")
    return


def _encode(value: Any, value_type: str) -> Optional[str]:
    """
        A Python value as the modern store's text (the same rules as ``variables.service._encode_value``).
    """
    if value is None:
        return None
    if value_type == "STRING":
        return str(value)
    if value_type == "INTEGER":
        return str(int(value))
    if value_type == "FLOAT":
        return repr(float(value))
    if value_type == "BOOLEAN":
        return "true" if value is True else "false"
    return json.dumps(value, sort_keys=True)


def _from_legacy_json(text: Optional[str], value_type: str) -> Optional[str]:
    """
        A legacy JSON-encoded value as the modern store's text; unreadable text is kept as it was.
    """
    if text is None:
        return None
    try:
        return _encode(json.loads(text), value_type)
    except (ValueError, TypeError):
        return text


def _copy_legacy_variables(bind: Any) -> None:
    """
        Copy ``global_variables`` and ``global_variable_history`` into the modern tables (SYSTEM scope), skipping every name that already has a SYSTEM binding.
    """
    inspector = sa.inspect(bind)
    if inspector.has_table("global_variables") is False:
        return
    # Written out, not reflected: reflecting follows the foreign key to the legacy ``user`` table, which this copy does not need.
    # The legacy tables declare their user ids with the library's default (binary) UUID type; the modern tables store them as text on SQLite.
    uuid_type = sqlalchemy_utils.types.uuid.UUIDType()
    legacy = sa.table(
        "global_variables",
        sa.column("gvar_name", sa.String), sa.column("gvar_value_json", sa.Text), sa.column("gvar_type", sa.String), sa.column("gvar_description", sa.String),
        sa.column("gvar_default_value_json", sa.Text), sa.column("gvar_created_at", UtcDateTime(timezone=True)),
        sa.column("gvar_updated_at", UtcDateTime(timezone=True)), sa.column("gvar_updated_by_id", uuid_type),
    )
    bindings = sa.table(
        "variables_variable_bindings",
        sa.column("binding_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False)), sa.column("scope", sa.String), sa.column("scope_id", sa.String),
        sa.column("name", sa.String), sa.column("value_type", sa.String), sa.column("value_text", sa.Text),
        sa.column("set_by_user_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False)), sa.column("set_at", UtcDateTime(timezone=True)),
        sa.column("description", sa.String), sa.column("default_value_text", sa.Text), sa.column("created_at", UtcDateTime(timezone=True)),
    )
    history = sa.table(
        "variables_binding_history",
        sa.column("history_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False)), sa.column("scope", sa.String), sa.column("scope_id", sa.String),
        sa.column("name", sa.String), sa.column("value_type", sa.String), sa.column("old_value_text", sa.Text), sa.column("new_value_text", sa.Text),
        sa.column("changed_by_user_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False)), sa.column("changed_at", UtcDateTime(timezone=True)),
    )

    already = {row[0] for row in bind.execute(sa.text("SELECT name FROM variables_variable_bindings WHERE scope = 'SYSTEM' AND scope_id = ''")).fetchall()}
    types: Dict[str, str] = {}
    for row in bind.execute(sa.select(legacy)).mappings().all():
        name = row["gvar_name"]
        value_type = str(row["gvar_type"]).upper()
        types[name] = value_type
        if name in already or value_type not in _TYPES:
            continue
        updated_by = row["gvar_updated_by_id"]
        bind.execute(bindings.insert().values(
            binding_id=uuid.uuid4(), scope="SYSTEM", scope_id="", name=name, value_type=value_type,
            value_text=_from_legacy_json(row["gvar_value_json"], value_type), set_by_user_id=updated_by, set_at=row["gvar_updated_at"],
            description=row["gvar_description"] or "", default_value_text=_from_legacy_json(row["gvar_default_value_json"], value_type),
            created_at=row["gvar_created_at"],
        ))

    if inspector.has_table("global_variable_history") is False:
        return
    legacy_history = sa.table(
        "global_variable_history",
        sa.column("gvarhist_variable_name", sa.String), sa.column("gvarhist_old_value_json", sa.Text), sa.column("gvarhist_new_value_json", sa.Text),
        sa.column("gvarhist_changed_by_id", uuid_type), sa.column("gvarhist_changed_at", UtcDateTime(timezone=True)),
    )
    for row in bind.execute(sa.select(legacy_history).order_by(legacy_history.c.gvarhist_changed_at)).mappings().all():
        name = row["gvarhist_variable_name"]
        if name in already:
            continue
        value_type = types.get(name, "JSON")
        if value_type not in _TYPES:
            value_type = "JSON"
        bind.execute(history.insert().values(
            history_id=uuid.uuid4(), scope="SYSTEM", scope_id="", name=name, value_type=value_type,
            old_value_text=_from_legacy_json(row["gvarhist_old_value_json"], value_type),
            new_value_text=_from_legacy_json(row["gvarhist_new_value_json"], value_type),
            changed_by_user_id=row["gvarhist_changed_by_id"], changed_at=row["gvarhist_changed_at"],
        ))
    return
