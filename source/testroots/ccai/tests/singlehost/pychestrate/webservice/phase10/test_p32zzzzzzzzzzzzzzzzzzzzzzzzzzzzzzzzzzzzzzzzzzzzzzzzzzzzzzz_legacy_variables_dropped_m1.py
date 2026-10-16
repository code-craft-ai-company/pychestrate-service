"""
.. module:: test_legacy_variables_dropped_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The migration that drops the legacy global variable tables (ADM-08, step 3).

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import importlib.util
import os

from typing import Any, List

import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.pool import StaticPool

from ccai import testbase


def _load_migration() -> Any:
    root = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(root, "alembic", "versions")):
        root = os.path.dirname(root)
    versions = os.path.join(root, "alembic", "versions")
    name = [item for item in os.listdir(versions) if "b4d6f8a0c2e5" in item and item.endswith(".py")][0]
    spec = importlib.util.spec_from_file_location("drop_legacy_variables_migration", os.path.join(versions, name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine: Any, direction: str) -> None:
    migration = _load_migration()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            getattr(migration, direction)()
    return


def _tables(engine: Any) -> List[str]:
    return sorted(name for name in sa.inspect(engine).get_table_names() if name.startswith("global_variable"))


def _legacy_database() -> Any:
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE global_variables (gvar_id INTEGER NOT NULL PRIMARY KEY, gvar_name VARCHAR(128) NOT NULL, gvar_value_json TEXT NOT NULL)"))
        connection.execute(sa.text("CREATE UNIQUE INDEX ix_global_variables_gvar_name ON global_variables (gvar_name)"))
        connection.execute(sa.text("CREATE TABLE global_variable_history (gvarhist_id INTEGER NOT NULL PRIMARY KEY, gvarhist_variable_id INTEGER NOT NULL)"))
        connection.execute(sa.text("CREATE INDEX ix_global_variable_history_gvarhist_variable_id ON global_variable_history (gvarhist_variable_id)"))
        connection.execute(sa.text("INSERT INTO global_variables VALUES (1, 'left.over', '\"x\"')"))
        connection.execute(sa.text("INSERT INTO global_variable_history VALUES (1, 1)"))
    return engine


def test_the_upgrade_drops_both_legacy_tables_and_can_run_again_on_a_database_that_never_had_them():
    """
    **Feature: one variables store (ADM-08, step 3)**
    **Property: the upgrade drops ``global_variables`` and ``global_variable_history`` with their indexes, and running it on a database without them (a fresh install, or a second
    run) changes nothing and raises nothing.**
    """
    engine = _legacy_database()
    before = _tables(engine)
    _run(engine, "upgrade")
    after = _tables(engine)
    _run(engine, "upgrade")
    testbase.assert_equal((before, after, _tables(engine)), (["global_variable_history", "global_variables"], [], []))
    return


def test_the_downgrade_recreates_both_tables_empty_so_the_previous_release_starts():
    """
    **Feature: one variables store (ADM-08, step 3)**
    **Property: the downgrade recreates both tables (empty, with the name index on the variables), and running it where they exist already changes nothing.**
    """
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    _run(engine, "downgrade")
    created = _tables(engine)
    with engine.connect() as connection:
        counts = (
            connection.execute(sa.text("SELECT count(*) FROM global_variables")).scalar(), connection.execute(sa.text("SELECT count(*) FROM global_variable_history")).scalar(),
        )
    indexes = sorted(index["name"] for index in sa.inspect(engine).get_indexes("global_variables"))
    _run(engine, "downgrade")
    testbase.assert_equal(
        (created, counts, indexes, _tables(engine)),
        (["global_variable_history", "global_variables"], (0, 0), ["ix_global_variables_gvar_name"], ["global_variable_history", "global_variables"]),
    )
    return
