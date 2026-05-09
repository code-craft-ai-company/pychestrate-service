"""
.. module:: test_p13a_alembic_setup_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the alembic configuration files.

.. moduleauthor:: Automation Mojo LLC

The alembic toolchain itself is exercised end-to-end by the
operator (``make db-upgrade``) -- this suite covers the static
configuration: alembic.ini parses, env.py imports cleanly, the
baseline migration parses + carries valid revision metadata, and
the env.py reads the documented PYCHESTRATE_DATABASE_URL env var.

These tests do NOT spin up a real database. They cover the
conf wiring; the migration runtime behavior is validated by
the ``alembic upgrade head`` smoke at deploy time.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import configparser
import os
import re

from typing import List

from automojo import testbase


def _repo_root() -> str:
    """
        Resolve the repo root from the test file location.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(
        os.path.join(
            here, "..", "..", "..", "..", "..", "..", "..", "..",
        )
    )
    return rtnval


def _alembic_dir() -> str:
    rtnval = os.path.join(_repo_root(), "alembic")
    return rtnval


def _versions_dir() -> str:
    rtnval = os.path.join(_alembic_dir(), "versions")
    return rtnval


def _list_version_files() -> List[str]:
    """
        List the alembic version migration files (excluding
        ``.gitkeep`` / ``__init__.py`` / ``__pycache__``).
    """
    rtnval = []
    versions = _versions_dir()
    if not os.path.isdir(versions):
        return rtnval
    for name in sorted(os.listdir(versions)):
        if name.endswith(".py"):
            rtnval.append(os.path.join(versions, name))
    return rtnval


# ---------------------------------------------------------------------------
# alembic.ini
# ---------------------------------------------------------------------------


def test_alembic_ini_parses_and_points_at_alembic_directory():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: alembic.ini parses as INI and the
    ``script_location`` is set to ``alembic`` (the directory next
    to it).**
    """
    ini_path = os.path.join(_repo_root(), "alembic.ini")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ini_path, encoding="utf-8")
    testbase.assert_equal(parser.has_section("alembic"), True)
    testbase.assert_equal(
        parser.get("alembic", "script_location"), "alembic"
    )
    return


def test_alembic_ini_leaves_sqlalchemy_url_blank():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: ``sqlalchemy.url`` is intentionally blank in
    alembic.ini -- the runtime URL is read from
    PYCHESTRATE_DATABASE_URL inside env.py so the same alembic.ini
    serves dev SQLite and production Postgres.**
    """
    ini_path = os.path.join(_repo_root(), "alembic.ini")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ini_path, encoding="utf-8")
    url_value = parser.get("alembic", "sqlalchemy.url", fallback="").strip()
    testbase.assert_equal(url_value, "")
    return


def test_alembic_ini_file_template_carries_chronological_prefix():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: The migration filename pattern starts with a
    YYYY_MM_DD_HHMM timestamp so versions/ stays
    chronologically ordered.**
    """
    ini_path = os.path.join(_repo_root(), "alembic.ini")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ini_path, encoding="utf-8")
    template = parser.get("alembic", "file_template")
    # configparser.interpolation=None preserves the literal ``%%``
    # escapes alembic uses for its own format string. Just check
    # the documented date components are present in order.
    has_year_first = "year" in template
    year_index = template.find("year")
    month_index = template.find("month")
    day_index = template.find("day")
    hour_index = template.find("hour")
    minute_index = template.find("minute")
    rev_index = template.find("rev")
    testbase.assert_equal(has_year_first, True)
    # year < month < day < hour < minute < rev order
    testbase.assert_equal(year_index < month_index, True)
    testbase.assert_equal(month_index < day_index, True)
    testbase.assert_equal(day_index < hour_index, True)
    testbase.assert_equal(hour_index < minute_index, True)
    testbase.assert_equal(minute_index < rev_index, True)
    return


# ---------------------------------------------------------------------------
# env.py
# ---------------------------------------------------------------------------


def test_env_py_documents_database_url_env_var_name():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: env.py declares the documented env var
    ``PYCHESTRATE_DATABASE_URL`` -- same name the runtime
    bootstrap reads, so alembic and the running service stay
    aligned without operator double-configuration.**
    """
    env_path = os.path.join(_alembic_dir(), "env.py")
    with open(env_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    has_constant = "ENV_DATABASE_URL" in text
    has_value = '"PYCHESTRATE_DATABASE_URL"' in text
    testbase.assert_equal(has_constant, True)
    testbase.assert_equal(has_value, True)
    return


def test_env_py_imports_phase_bootstraps_to_register_models():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: env.py side-effect-imports the three phase
    bootstrap modules so every model module loads before alembic
    walks the metadata. Without this, autogenerate would only
    catch the tables it could discover transitively from the
    declarative base.**
    """
    env_path = os.path.join(_alembic_dir(), "env.py")
    with open(env_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    has_phase1 = "extensions import bootstrap" in text
    has_phase2 = "extensions import phase2_bootstrap" in text
    has_phase3 = "extensions import phase3_bootstrap" in text
    testbase.assert_equal(has_phase1, True)
    testbase.assert_equal(has_phase2, True)
    testbase.assert_equal(has_phase3, True)
    return


def test_env_py_target_metadata_includes_phase1_and_legacy_bases():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: env.py targets BOTH
    ``PychestratePhase1Base.metadata`` (the modern Phase-1+
    models) AND ``PychestrateModelBase.metadata`` (the legacy
    ``core.orm`` tables: ``user``, ``password_history``,
    ``sessions``, ``permissions``, …). Alembic accepts a
    ``Sequence[MetaData]`` here; both bases must appear so the
    consumer-UI's legacy-``SecurityManager`` login flow has
    real schema in production.**
    """
    env_path = os.path.join(_alembic_dir(), "env.py")
    with open(env_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    has_phase1_import = (
        "from automojo.pychestrate.webservice.persistence.schema"
        in text
    )
    has_legacy_import = (
        "from automojo.pychestrate.core.orm import" in text
        and "PychestrateModelBase" in text
    )
    has_phase1_in_target = (
        "PychestratePhase1Base.metadata" in text
    )
    has_legacy_in_target = (
        "PychestrateModelBase.metadata" in text
    )
    testbase.assert_equal(has_phase1_import, True)
    testbase.assert_equal(has_legacy_import, True)
    testbase.assert_equal(has_phase1_in_target, True)
    testbase.assert_equal(has_legacy_in_target, True)
    return


def test_env_py_supports_both_offline_and_online_modes():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: env.py defines both ``run_migrations_offline`` and
    ``run_migrations_online`` so ``alembic upgrade --sql`` (review
    flow) and ``alembic upgrade head`` (apply flow) both work.**
    """
    env_path = os.path.join(_alembic_dir(), "env.py")
    with open(env_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    has_offline = "def run_migrations_offline" in text
    has_online = "def run_migrations_online" in text
    has_dispatch = "context.is_offline_mode()" in text
    testbase.assert_equal(has_offline, True)
    testbase.assert_equal(has_online, True)
    testbase.assert_equal(has_dispatch, True)
    return


def test_env_py_uses_compare_type_and_compare_server_default():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: ``compare_type=True`` and
    ``compare_server_default=True`` are passed to
    ``context.configure`` so autogenerate detects column-type
    drift and server-default drift -- both are off by default in
    alembic.**
    """
    env_path = os.path.join(_alembic_dir(), "env.py")
    with open(env_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    has_compare_type = "compare_type=True" in text
    has_compare_default = "compare_server_default=True" in text
    testbase.assert_equal(has_compare_type, True)
    testbase.assert_equal(has_compare_default, True)
    return


# ---------------------------------------------------------------------------
# Baseline migration
# ---------------------------------------------------------------------------


def test_versions_directory_exists():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: alembic/versions/ exists -- alembic refuses to run
    if its versions directory is missing.**
    """
    testbase.assert_equal(os.path.isdir(_versions_dir()), True)
    return


def test_baseline_migration_exists_with_valid_revision_metadata():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: At least one migration file exists. The earliest
    migration (the baseline) declares ``down_revision = None`` --
    that's the convention alembic uses to mark the chain start.**
    """
    files = _list_version_files()
    testbase.assert_equal(len(files) > 0, True)
    baseline = files[0]
    with open(baseline, "r", encoding="utf-8") as fh:
        text = fh.read()
    has_revision = re.search(r"^revision: str = '[a-f0-9]+'", text, re.M) is not None
    has_down_revision_none = re.search(
        r"^down_revision: .* = None", text, re.M
    ) is not None
    testbase.assert_equal(has_revision, True)
    testbase.assert_equal(has_down_revision_none, True)
    return


def test_baseline_migration_imports_required_modules():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: The autogenerate output references
    ``sqlalchemy_utils`` (UUIDType) and Postgres dialect helpers;
    both modules need explicit imports for the migration to
    execute. Catches the autogen-tool default of skipping the
    sqlalchemy_utils import.**
    """
    files = _list_version_files()
    baseline = files[0]
    with open(baseline, "r", encoding="utf-8") as fh:
        text = fh.read()
    if "sqlalchemy_utils" in text and "create_table" in text:
        # The migration uses sqlalchemy_utils types in column defs;
        # the import line must be present at module top.
        testbase.assert_equal("import sqlalchemy_utils" in text, True)
    if "postgresql.JSONB" in text:
        testbase.assert_equal(
            "from sqlalchemy.dialects import postgresql" in text, True
        )
    return


def test_baseline_migration_uses_qualified_text_for_jsonb_astext_type():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: The ``astext_type=Text()`` autogenerate emits in
    JSONB column defs needs the ``sa.`` prefix to import. Catches
    a common autogen post-fix gotcha that otherwise breaks the
    migration at first ``upgrade``.**
    """
    files = _list_version_files()
    baseline = files[0]
    with open(baseline, "r", encoding="utf-8") as fh:
        text = fh.read()
    has_bare = "astext_type=Text()" in text
    testbase.assert_equal(has_bare, False)
    return


# ---------------------------------------------------------------------------
# Makefile + runtime bootstrap glue
# ---------------------------------------------------------------------------


def test_makefile_exposes_db_targets():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: The Makefile exposes db-upgrade / db-downgrade /
    db-current / db-history / db-revision-autogen so operators
    have a single self-documenting interface.**
    """
    makefile_path = os.path.join(_repo_root(), "Makefile")
    with open(makefile_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    for target in (
        "db-upgrade:",
        "db-downgrade:",
        "db-current:",
        "db-history:",
        "db-revision-autogen:",
    ):
        testbase.assert_equal(target in text, True)
    return


def test_runtime_bootstrap_documents_alembic_for_production():
    """
    **Feature: 0-persistence T1.4 (alembic setup)**
    **Property: The runtime_bootstrap.py module docstring + the
    production-refuse error message both point operators at
    alembic for production schema management. Without this,
    operators who hit the ``auto_create_schema=true in production``
    guard would not know where to go next.**
    """
    rb_path = os.path.join(
        _repo_root(),
        "source", "site",
        "automojo", "pychestrate", "webservice", "runtime_bootstrap.py",
    )
    with open(rb_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    has_doc_pointer = "alembic" in text.lower()
    has_make_pointer = "make db-upgrade" in text
    testbase.assert_equal(has_doc_pointer, True)
    testbase.assert_equal(has_make_pointer, True)
    return


# ---------------------------------------------------------------------------
# Legacy core.orm migration (PR p13w)
# ---------------------------------------------------------------------------


def test_legacy_core_orm_migration_exists():
    """
    **Feature: 0-persistence T1.5 (legacy core.orm coverage)**
    **Property: A second migration brings every table on
    ``PychestrateModelBase.metadata`` (the legacy ``core.orm``
    base) under alembic management. Without this revision, the
    consumer-UI's legacy-``SecurityManager`` login flow has no
    ``user`` / ``password_history`` / ``sessions`` table to
    query in production; see
    ``userguide/12-00-consumer-ui-auth-stack.rst`` for context.**
    """
    files = _list_version_files()
    has_legacy = False
    for path in files:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if (
            "create_table('user'" in text
            and "create_table('password_history'" in text
            and "create_table('sessions'" in text
        ):
            has_legacy = True
            break
    testbase.assert_equal(has_legacy, True)
    return


def test_legacy_migration_creates_consumer_ui_auth_tables_on_apply():
    """
    **Feature: 0-persistence T1.5 (legacy core.orm coverage)**
    **Property: Running ``alembic upgrade head`` against a
    fresh SQLite DB results in the consumer-UI's auth tables
    (``user`` / ``password_history`` / ``sessions`` /
    ``permissions`` / ``system_roles`` / ``role_permissions``)
    actually existing. End-to-end test that proves the
    migration applies without error and produces the schema
    the consumer UI expects.**
    """
    import sys
    import tempfile
    import subprocess
    import sqlite3

    fd, db_path = tempfile.mkstemp(prefix="alembic-test-", suffix=".sqlite")
    os.close(fd)
    try:
        env = os.environ.copy()
        env["PYCHESTRATE_DATABASE_URL"] = "sqlite:///" + db_path

        # Invoke alembic via the ``alembic`` console script
        # installed alongside ``sys.executable``'s venv. Cannot
        # use ``python -m alembic`` here because the repo root
        # contains an ``alembic/`` *migrations* directory
        # (configured in ``alembic.ini``); when ``-m alembic``
        # runs with cwd at repo root, Python's namespace-package
        # search picks up the local migrations dir first and
        # shadows the installed alembic library. The console
        # script bypasses this because its launcher does not
        # add cwd to ``sys.path``.
        alembic_script = os.path.join(
            os.path.dirname(sys.executable), "alembic"
        )
        proc = subprocess.run(
            [alembic_script, "upgrade", "head"],
            cwd=_repo_root(),
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            err_msg_lines = ["alembic upgrade head failed."]
            err_msg_lines.append("STDOUT:")
            err_msg_lines.append(proc.stdout)
            err_msg_lines.append("STDERR:")
            err_msg_lines.append(proc.stderr)
            err_msg = os.linesep.join(err_msg_lines)
            raise AssertionError(err_msg)

        db = sqlite3.connect(db_path)
        try:
            cursor = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            actual_tables = set(row[0] for row in cursor)
        finally:
            db.close()

        required = {
            "user",
            "password_history",
            "sessions",
            "permissions",
            "system_roles",
            "role_permissions",
        }
        missing = required - actual_tables
        testbase.assert_equal(missing, set())
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass
    return
