"""
.. module:: test_p40o_migrations_create_enum_types_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A migration that adds an enum column must create the PostgreSQL type first.

.. moduleauthor:: Code Craft AI LLC

On PostgreSQL an enum is a real type, and ``op.add_column`` with a ``sa.Enum`` does not create it (only ``op.create_table``
does), so a migration that adds an enum column to an existing table fails on a fresh PostgreSQL database with
``type "..." does not exist``. SQLite stores enums as text and never shows the problem, so the development server, the staging
server and this test harness all passed while ``make db-upgrade`` on a new PostgreSQL database stopped at
``a7b8c9d0e1f2`` (found by the runbook smoke test in CI, 2026-10-21).

These tests do not start a database; they read the migration files. The migration's runtime behaviour on PostgreSQL is
covered by the runbook smoke test (``.github/workflows/docs.yml``).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import ast
import os

from typing import List, Tuple

from ccai import testbase


def _versions_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(here, "..", "..", "..", "..", "..", "..", "..", ".."))
    rtnval = os.path.join(root, "alembic", "versions")
    return rtnval


def _is_call_to(node: ast.AST, owner: str, attribute: str) -> bool:
    rtnval = False
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attribute:
        rtnval = isinstance(node.func.value, ast.Name) and node.func.value.id == owner
    return rtnval


def _adds_enum_column(source: str) -> bool:
    """
        True when the module calls ``op.add_column`` and builds a named ``sa.Enum`` anywhere (directly in the call or through a helper).
    """
    tree = ast.parse(source)
    adds_column = any(_is_call_to(n, "op", "add_column") for n in ast.walk(tree))
    named_enum = any(
        _is_call_to(n, "sa", "Enum") and any(k.arg == "name" for k in n.keywords)
        for n in ast.walk(tree)
    )
    return adds_column and named_enum


def _creates_the_type_first(source: str) -> bool:
    """
        True when the module creates the type for PostgreSQL: a ``.create(bind, checkfirst=True)`` call and a dialect check.
    """
    tree = ast.parse(source)
    creates = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "create"
        and any(k.arg == "checkfirst" and isinstance(k.value, ast.Constant) and k.value.value is True for k in n.keywords)
        for n in ast.walk(tree)
    )
    dialect_checked = "postgresql" in source
    return creates and dialect_checked


def _offenders() -> List[Tuple[str, str]]:
    rtnval = []
    versions = _versions_dir()
    for name in sorted(os.listdir(versions)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(versions, name), encoding="utf-8") as handle:
            source = handle.read()
        if _adds_enum_column(source) and not _creates_the_type_first(source):
            rtnval.append((name, "adds an enum column without creating the PostgreSQL type first"))
    return rtnval


def test_every_migration_that_adds_an_enum_column_creates_the_type_first():
    """
    **Feature: migrations run on a fresh PostgreSQL database**
    **Property: no migration file calls ``op.add_column`` with a named ``sa.Enum`` unless it also creates the type with ``.create(bind, checkfirst=True)`` behind a PostgreSQL check.**
    """
    testbase.assert_equal(_offenders(), [])
    return


def test_the_check_recognises_the_migration_that_failed_and_its_fix():
    """
    **Feature: migrations run on a fresh PostgreSQL database**
    **Property: the check flags the shape of ``a7b8c9d0e1f2`` before the fix (an enum added with ``op.add_column`` and no type creation) and accepts the fixed shape, so it cannot pass by matching nothing.**
    """
    broken = (
        "import sqlalchemy as sa\nfrom alembic import op\n"
        "def upgrade():\n    op.add_column('t', sa.Column('k', sa.Enum('A', 'B', name='k_enum'), nullable=False))\n"
    )
    fixed = (
        "import sqlalchemy as sa\nfrom alembic import op\n"
        "def upgrade():\n    bind = op.get_bind()\n    if bind.dialect.name == 'postgresql':\n"
        "        sa.Enum('A', 'B', name='k_enum').create(bind, checkfirst=True)\n"
        "    op.add_column('t', sa.Column('k', sa.Enum('A', 'B', name='k_enum'), nullable=False))\n"
    )
    testbase.assert_equal(
        (_adds_enum_column(broken), _creates_the_type_first(broken), _adds_enum_column(fixed), _creates_the_type_first(fixed)),
        (True, False, True, True),
    )
    return


def test_the_secret_scope_migration_creates_its_type_and_drops_it_on_downgrade():
    """
    **Feature: migrations run on a fresh PostgreSQL database**
    **Property: ``a7b8c9d0e1f2`` creates ``secret_scope_kind`` before adding the column and drops it again when it is downgraded.**
    """
    versions = _versions_dir()
    name = [n for n in os.listdir(versions) if "a7b8c9d0e1f2" in n][0]
    with open(os.path.join(versions, name), encoding="utf-8") as handle:
        source = handle.read()
    testbase.assert_equal(
        (".create(bind, checkfirst=True)" in source, ".drop(bind, checkfirst=True)" in source, source.index(".create(bind") < source.index("op.add_column(")),
        (True, True, True),
    )
    return
