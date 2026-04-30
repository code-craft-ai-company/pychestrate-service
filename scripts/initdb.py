"""
.. module:: scripts.initdb
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Create the pychestrate Phase-1 schema in a target DB.

.. moduleauthor:: Automation Mojo LLC

Convenience CLI for first-time bring-up. Reads
``PYCHESTRATE_DATABASE_URL`` from the environment (or accepts a
``--database-url`` flag), connects via SQLAlchemy, and creates every
table declared on :class:`PychestratePhase1Base`.

Usage::

    PYCHESTRATE_DATABASE_URL=sqlite:///./pychestrate.db \\
        python scripts/initdb.py

    python scripts/initdb.py --database-url postgresql+psycopg://u:p@h/db
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import os
import sys

from typing import Optional

import sqlalchemy as sa

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


DATABASE_URL_ENV_VAR = "PYCHESTRATE_DATABASE_URL"


def _resolve_database_url(*, cli_value: Optional[str]) -> str:
    """
        Resolve the DB URL, preferring the CLI flag over the env var.

        :returns: A non-empty connection string.

        :raises SystemExit: When neither source supplies a value.
    """
    if cli_value is not None:
        if len(cli_value.strip()) > 0:
            return cli_value
    env_value = os.environ.get(DATABASE_URL_ENV_VAR, None)
    if env_value is not None:
        if len(env_value.strip()) > 0:
            return env_value
    sys.stderr.write(
        "ERROR: database url not configured.{0}".format(os.linesep),
    )
    sys.stderr.write(
        "  Set --database-url or {0}={1}{2}".format(
            DATABASE_URL_ENV_VAR,
            "<sqlalchemy connection string>",
            os.linesep,
        ),
    )
    raise SystemExit(2)


def main(*, argv: Optional[list] = None) -> int:
    """
        CLI entry point.

        :param argv: Optional argv override (defaults to ``sys.argv``).

        :returns: ``0`` on success, non-zero on configuration errors.
    """
    parser = argparse.ArgumentParser(
        description="Create the pychestrate Phase-1 schema.",
    )
    parser.add_argument(
        "--database-url",
        dest="database_url",
        default=None,
        help=(
            "SQLAlchemy connection string. Falls back to the "
            "{} environment variable.".format(DATABASE_URL_ENV_VAR)
        ),
    )
    parser.add_argument(
        "--use-metadata-create-all",
        dest="use_metadata",
        action="store_true",
        help=(
            "Skip Alembic and call metadata.create_all instead. "
            "Faster for tests / one-shot SQLite bring-up; not "
            "recommended for production where you need a migration "
            "trail. The default path runs `alembic upgrade head`."
        ),
    )
    args = parser.parse_args(argv)

    database_url = _resolve_database_url(cli_value=args.database_url)
    sys.stdout.write(
        "Connecting to: {0}{1}".format(database_url, os.linesep),
    )

    if args.use_metadata is True:
        engine = sa.create_engine(database_url)
        PychestratePhase1Base.metadata.create_all(engine)
        sys.stdout.write(
            "Phase-1 schema created via metadata.create_all.{0}".format(
                os.linesep,
            ),
        )
    else:
        # Apply via Alembic so the schema_versions row records the
        # migration trail. PYCHESTRATE_DATABASE_URL is read by
        # alembic/env.py at runtime.
        os.environ[DATABASE_URL_ENV_VAR] = database_url
        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig

        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), ".."),
        )
        alembic_cfg = AlembicConfig(
            os.path.join(repo_root, "alembic.ini"),
        )
        alembic_cfg.set_main_option(
            "script_location",
            os.path.join(repo_root, "alembic"),
        )
        alembic_command.upgrade(alembic_cfg, "head")
        sys.stdout.write(
            "Phase-1 schema applied via `alembic upgrade head`.{0}".format(
                os.linesep,
            ),
        )

    rtnval = 0
    return rtnval


if __name__ == "__main__":
    raise SystemExit(main())
