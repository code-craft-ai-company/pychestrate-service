"""
Alembic env.py for pychestrate-service.

Reads the database URL from the ``PYCHESTRATE_DATABASE_URL``
environment variable (or, when explicitly supplied,
``alembic.config.main(['-x', 'database_url=...'])``).

Imports :data:`PychestratePhase1Base` so autogenerate sees every
declared table. The blueprint modules are imported as a side-effect
of ``import automojo.pychestrate.webservice.pychestrateapplication``
because every controller declares its endpoints there; the
application import also chains the ORM-model imports the schema
depends on. We keep that import isolated to the
``run_migrations_*`` functions so importing this env module for
``alembic --help`` does not require a full app boot.
"""

import os
import sys

from logging.config import fileConfig
from typing import Optional

from sqlalchemy import engine_from_config, pool

from alembic import context


# Alembic Config object — set in alembic.ini.
config = context.config

# Configure Python logging from the config file unless skipped.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_database_url() -> str:
    """
        Resolve the SQLAlchemy URL from a CLI -x override or the
        PYCHESTRATE_DATABASE_URL env var.
    """
    x_args = context.get_x_argument(as_dictionary=True)
    if "database_url" in x_args:
        rtnval = x_args["database_url"]
        return rtnval
    env_value = os.environ.get("PYCHESTRATE_DATABASE_URL", None)
    if env_value is None or len(env_value.strip()) == 0:
        sys.stderr.write(
            "ERROR: PYCHESTRATE_DATABASE_URL not set and no -x "
            "database_url=... override supplied.\n",
        )
        raise SystemExit(2)
    rtnval = env_value
    return rtnval


def _load_target_metadata():
    """
        Import the canonical declarative base and every blueprint
        module so autogenerate sees every model class.

        Imported lazily so ``alembic revision --autogenerate`` works
        but ``alembic --help`` doesn't pay the boot cost.
    """
    # The application import chains every blueprint, which in turn
    # chains the ORM models the schema depends on.
    import automojo.pychestrate.webservice.pychestrateapplication  # noqa: F401
    from automojo.pychestrate.webservice.persistence.schema import (
        PychestratePhase1Base,
    )
    return PychestratePhase1Base.metadata


def run_migrations_offline() -> None:
    """
        Run migrations in 'offline' mode (no live engine).
    """
    url = _resolve_database_url()
    target_metadata = _load_target_metadata()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
        Run migrations in 'online' mode (live SQLAlchemy engine).
    """
    url = _resolve_database_url()
    target_metadata = _load_target_metadata()

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
