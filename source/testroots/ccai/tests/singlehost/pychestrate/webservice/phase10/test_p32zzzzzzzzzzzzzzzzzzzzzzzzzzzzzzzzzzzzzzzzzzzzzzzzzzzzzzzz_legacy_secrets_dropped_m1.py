"""
.. module:: test_legacy_secrets_dropped_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The migration that drops the legacy secret tables, and refuses to while a live secret is in them (ADM-07, step 3).

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


LEGACY_TABLES = ["scope_permissions", "secret_scopes", "secret_versions", "secrets"]


def _load_migration() -> Any:
    root = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(root, "alembic", "versions")):
        root = os.path.dirname(root)
    versions = os.path.join(root, "alembic", "versions")
    name = [item for item in os.listdir(versions) if "c5e7a9b1d3f4" in item and item.endswith(".py")][0]
    spec = importlib.util.spec_from_file_location("drop_legacy_secrets_migration", os.path.join(versions, name))
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
    return sorted(name for name in sa.inspect(engine).get_table_names() if name in LEGACY_TABLES)


def _legacy_database(*, live: int, soft_deleted: int) -> Any:
    """A database holding the legacy tables, with ``live`` live secrets and ``soft_deleted`` soft-deleted ones, in scopes with a grant."""
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE secret_scopes (scope_id INTEGER NOT NULL PRIMARY KEY, scope_name VARCHAR(128) NOT NULL)"))
        connection.execute(sa.text("CREATE UNIQUE INDEX ix_secret_scopes_scope_name ON secret_scopes (scope_name)"))
        connection.execute(sa.text(
            "CREATE TABLE secrets (secret_id INTEGER NOT NULL PRIMARY KEY, secret_name VARCHAR(128) NOT NULL, secret_scope_id INTEGER NOT NULL, secret_is_deleted BOOLEAN NOT NULL)"
        ))
        connection.execute(sa.text("CREATE INDEX ix_secrets_secret_name ON secrets (secret_name)"))
        connection.execute(sa.text("CREATE TABLE secret_versions (secver_id INTEGER NOT NULL PRIMARY KEY, secver_secret_id INTEGER NOT NULL)"))
        connection.execute(sa.text("CREATE TABLE scope_permissions (scope_id INTEGER NOT NULL, role_id INTEGER NOT NULL, PRIMARY KEY (scope_id, role_id))"))
        connection.execute(sa.text("INSERT INTO secret_scopes VALUES (1, 'company'), (2, 'ci')"))
        connection.execute(sa.text("INSERT INTO scope_permissions VALUES (1, 7)"))
        number = 0
        for deleted, count in ((False, live), (True, soft_deleted)):
            for _ in range(count):
                number += 1
                connection.execute(sa.text("INSERT INTO secrets VALUES (:i, :n, 1, :d)"), {"i": number, "n": "secret.{}".format(number), "d": deleted})
                connection.execute(sa.text("INSERT INTO secret_versions VALUES (:i, :i)"), {"i": number})
    return engine


def test_the_upgrade_refuses_while_a_live_secret_exists_and_changes_nothing():
    """
    **Feature: one secrets vault (ADM-07, step 3)**
    **Property: with two live and three soft-deleted legacy secrets, the upgrade raises an error that says how many would be lost and to import them into the vault with the previous
    release, and leaves all four tables and every row exactly as they were.**
    """
    engine = _legacy_database(live=2, soft_deleted=3)
    message = ""
    try:
        _run(engine, "upgrade")
    except RuntimeError as xcpt:
        message = str(xcpt)
    with engine.connect() as connection:
        rows = (
            connection.execute(sa.text("SELECT count(*) FROM secrets")).scalar(), connection.execute(sa.text("SELECT count(*) FROM secret_versions")).scalar(),
            connection.execute(sa.text("SELECT count(*) FROM secret_scopes")).scalar(), connection.execute(sa.text("SELECT count(*) FROM scope_permissions")).scalar(),
        )
    testbase.assert_equal(
        ("2 live secret" in message, "previous release" in message, "Import 2 secrets into the vault" in message, _tables(engine), rows),
        (True, True, True, LEGACY_TABLES, (5, 5, 2, 1)),
    )
    return


def test_the_upgrade_drops_all_four_tables_when_only_soft_deleted_leftovers_remain_and_runs_again_harmlessly():
    """
    **Feature: one secrets vault (ADM-07, step 3)**
    **Property: with only soft-deleted secrets (and scopes, versions and a grant) the upgrade drops all four tables with their indexes, and running it again on a database
    that no longer has them changes nothing and raises nothing.**
    """
    engine = _legacy_database(live=0, soft_deleted=4)
    before = _tables(engine)
    _run(engine, "upgrade")
    after = _tables(engine)
    _run(engine, "upgrade")
    testbase.assert_equal((before, after, _tables(engine)), (LEGACY_TABLES, [], []))
    return


def test_the_upgrade_drops_empty_legacy_tables_and_a_database_that_never_had_them_is_untouched():
    """
    **Feature: one secrets vault (ADM-07, step 3)**
    **Property: legacy tables with no secrets at all are dropped, and a database without them (a fresh install) is left alone.**
    """
    empty = _legacy_database(live=0, soft_deleted=0)
    _run(empty, "upgrade")
    fresh = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    _run(fresh, "upgrade")
    testbase.assert_equal((_tables(empty), _tables(fresh)), ([], []))
    return


def test_the_downgrade_recreates_the_four_tables_empty_so_the_previous_release_starts():
    """
    **Feature: one secrets vault (ADM-07, step 3)**
    **Property: the downgrade recreates ``secret_scopes``, ``secrets``, ``secret_versions`` and ``scope_permissions`` empty, with the unique scope-name index and the
    scope-and-name index on secrets, and running it where they exist already changes nothing.**
    """
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    _run(engine, "downgrade")
    created = _tables(engine)
    with engine.connect() as connection:
        counts = [connection.execute(sa.text("SELECT count(*) FROM {}".format(table))).scalar() for table in LEGACY_TABLES]
    inspector = sa.inspect(engine)
    scope_indexes = sorted((index["name"], bool(index["unique"])) for index in inspector.get_indexes("secret_scopes"))
    secret_indexes = sorted(index["name"] for index in inspector.get_indexes("secrets"))
    _run(engine, "downgrade")
    testbase.assert_equal(
        (created, counts, scope_indexes, secret_indexes, _tables(engine)),
        (LEGACY_TABLES, [0, 0, 0, 0], [("ix_secret_scopes_scope_name", True)], ["ix_secrets_scope_name", "ix_secrets_secret_name", "ix_secrets_secret_scope_id"], LEGACY_TABLES),
    )
    return
