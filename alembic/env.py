"""
.. module:: alembic.env
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Alembic environment for the Pychestrate webservice.

.. moduleauthor:: Automation Mojo LLC

This module is the configuration entry point alembic invokes for
``revision --autogenerate``, ``upgrade``, ``downgrade``, etc.

Two operator decisions are deliberately delegated to environment
variables so the same alembic.ini works from a fresh checkout
through to a production deploy:

* **Database URL** — read from
  ``PYCHESTRATE_DATABASE_URL`` (the same env var the runtime
  bootstrap consumes). The ``sqlalchemy.url`` field in
  ``alembic.ini`` is intentionally blank.
* **Schema target** — :data:`PychestratePhase1Base.metadata`,
  populated by side-effect-importing the three phase-bootstrap
  modules from :mod:`webservice.extensions.bootstrap` /
  :mod:`webservice.extensions.phase2_bootstrap` /
  :mod:`webservice.extensions.phase3_bootstrap`. Each of those
  modules re-exports every Phase-1 / 2 / 3 model module via the
  same noqa-F401 pattern the runtime bootstrap uses, so all 57+
  in-tree tables register against
  :class:`PychestratePhase1Base.metadata` before alembic walks
  the diff.

Online vs offline
-----------------

* ``upgrade`` / ``downgrade`` against a real DB use ``run_migrations_online``
  (engine + connection).
* ``alembic upgrade --sql`` uses ``run_migrations_offline`` and emits
  raw SQL without connecting; useful for review-and-apply
  workflows where the migration is reviewed by a human before the
  DBA runs it.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import sys

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool


# ---------------------------------------------------------------------------
# PYTHONPATH setup so the webservice modules import cleanly.
#
# Alembic is invoked from the repo root, so ``source/site``,
# ``source/packages``, and ``source/service`` need to be on the
# path before any ``from automojo.pychestrate.webservice...`` line.
# Mirrors the layout in ``development/run-website.sh``.
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _component in ("source/site", "source/packages", "source/service"):
    _resolved = os.path.join(_REPO_ROOT, _component)
    if _resolved not in sys.path:
        sys.path.insert(0, _resolved)


# Side-effect imports — load every phase's bootstrap module so the
# noqa-F401 model imports inside them register every in-tree table
# on PychestratePhase1Base.metadata before alembic walks the diff.
from automojo.pychestrate.webservice.extensions import bootstrap as _phase1_bootstrap  # noqa: E402, F401
from automojo.pychestrate.webservice.extensions import phase2_bootstrap as _phase2_bootstrap  # noqa: E402, F401
from automojo.pychestrate.webservice.extensions import phase3_bootstrap as _phase3_bootstrap  # noqa: E402, F401

from automojo.pychestrate.webservice.persistence.schema import (  # noqa: E402
    PychestratePhase1Base,
)


config = context.config


# Configure stdlib logging from alembic.ini ``[loggers]`` /
# ``[handlers]`` blocks.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = PychestratePhase1Base.metadata


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


ENV_DATABASE_URL = "PYCHESTRATE_DATABASE_URL"


def _resolve_database_url() -> str:
    """
        Resolve the database URL alembic will operate against. The
        runtime bootstrap uses the same env var name -- this keeps
        alembic and the running service pointed at the same DB
        without operator double-configuration.

        :returns: SQLAlchemy URL string.
        :raises: RuntimeError when the env var is unset; alembic
                 swallows ConfigurationError, so a stdlib RuntimeError
                 surfaces the issue more clearly.
    """
    raw = os.environ.get(ENV_DATABASE_URL, None)
    if raw is None or len(raw) == 0:
        err_msg_lines = [
            "{} is required for alembic.".format(ENV_DATABASE_URL)
        ]
        err_msg_lines.append(
            "Set it to the URL alembic should connect to (e.g."
            " sqlite:///./.cache/dev-db/pychestrate.sqlite for"
            " local dev, or the operator-supplied production URL)."
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise RuntimeError(err_msg)
    rtnval = raw
    return rtnval


# ---------------------------------------------------------------------------
# Online / offline runners
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """
        Run migrations in 'offline' mode -- emit SQL without a live
        connection. Used by ``alembic upgrade --sql`` for
        review-and-apply workflows where a DBA executes the SQL
        manually.

        :returns: None.
    """
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    return


def run_migrations_online() -> None:
    """
        Run migrations in 'online' mode -- connect to the live DB
        and apply.

        :returns: None.
    """
    section_overrides = {"sqlalchemy.url": _resolve_database_url()}
    section = config.get_section(config.config_ini_section, {})
    section.update(section_overrides)

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    return


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
