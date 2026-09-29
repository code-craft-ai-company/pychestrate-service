"""
.. module:: test_p31za_orm_matches_migrations_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Every table and column the code maps exists after
               ``alembic upgrade head``.

.. moduleauthor:: Code Craft AI LLC

The test database is built from the mapped classes, so a model that gains
a column with no migration behind it passes every test and then fails on
a deployed database, which is built by ``alembic upgrade head``. That
happened once: a migration was written in a directory alembic does not
read, the suite was green, and staging answered every health page with a
missing-column error. This test migrates a fresh SQLite database and
fails when a mapped table or column is missing from it.

Only missing tables and columns are checked. Alembic's full comparison
also reports differences in how SQLite names types and in foreign keys
the migrations leave out, which are not a reason to fail.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

from ccai import testbase


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = here
    while not os.path.isfile(os.path.join(rtnval, "alembic.ini")):
        parent = os.path.dirname(rtnval)
        testbase.assert_true(parent != rtnval, "alembic.ini not found above {}".format(here))
        rtnval = parent
    return rtnval


COMPARE_SCRIPT = textwrap.dedent(
    """
    import os
    import sys

    from ccai.pychestrate.webservice.extensions import bootstrap, phase2_bootstrap, phase3_bootstrap  # noqa: F401
    from ccai.pychestrate.webservice.identity.setup import models as _setup  # noqa: F401
    from ccai.pychestrate.webservice.backup import models as _backup  # noqa: F401
    from ccai.pychestrate.webservice.housekeeping import models as _housekeeping  # noqa: F401
    from ccai.pychestrate.core import orm  # noqa: F401
    from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
    from ccai.pychestrate.core.orm import PychestrateModelBase

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    missing = []
    engine = create_engine(os.environ["PYCHESTRATE_DATABASE_URL"])
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        for metadata in (PychestratePhase1Base.metadata, PychestrateModelBase.metadata):
            for difference in compare_metadata(context, metadata):
                if not isinstance(difference, tuple):
                    continue
                if difference[0] == "add_table":
                    missing.append("table {}".format(difference[1].name))
                elif difference[0] == "add_column":
                    missing.append("column {}.{}".format(difference[2], difference[3].name))
    for line in sorted(missing):
        print(line)
    sys.exit(0)
    """
)


def test_every_mapped_table_and_column_exists_after_alembic_upgrade_head():
    """
    **Feature: schema migrations**
    **Property: on a fresh SQLite database migrated with ``alembic upgrade
    head``, no table or column that the mapped classes declare is missing.**
    """
    repo_root = _repo_root()
    workdir = tempfile.mkdtemp(prefix="pyc-orm-vs-migrations-")
    try:
        env = dict(os.environ)
        env["PYCHESTRATE_DATABASE_URL"] = "sqlite:///{}".format(os.path.join(workdir, "migrated.sqlite"))
        env["PYTHONPATH"] = os.pathsep.join(
            [os.path.join(repo_root, "source", "packages"), os.path.join(repo_root, "source", "site")]
        )
        # The console script, not ``python -m alembic``: the repo root has an
        # ``alembic/`` directory that ``-m`` would resolve to instead of the
        # library.
        upgraded = subprocess.run(
            [os.path.join(os.path.dirname(sys.executable), "alembic"), "upgrade", "head"],
            cwd=repo_root, env=env, capture_output=True, text=True,
        )
        testbase.assert_equal(upgraded.returncode, 0, "alembic upgrade head failed:\n" + upgraded.stderr[-2000:])

        compared = subprocess.run(
            [sys.executable, "-c", COMPARE_SCRIPT],
            cwd=repo_root, env=env, capture_output=True, text=True,
        )
        testbase.assert_equal(compared.returncode, 0, "the comparison failed:\n" + compared.stderr[-2000:])
        missing = [line for line in compared.stdout.splitlines() if line.strip() != ""]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    testbase.assert_equal(missing, [], "mapped but not created by any migration")
    return
