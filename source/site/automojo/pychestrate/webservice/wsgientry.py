"""
.. module:: pychestrate.webservice.wsgientry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WSGI server entrypoint for the pychestrate service.

.. moduleauthor:: Automation Mojo LLC

This module exposes the conventional ``application`` global expected by
WSGI servers (gunicorn, uWSGI, the built-in webworks WSGI server). It
reads its database URL from the ``PYCHESTRATE_DATABASE_URL`` environment
variable, builds a SQLAlchemy session factory, and constructs a
:class:`PychestrateApplication`.

Typical invocations:

* ``gunicorn 'automojo.pychestrate.webservice.wsgientry:application'``
* ``automojo.webworks.wsgi.server`` (built-in, programmatic)

For a full programmatic boot, callers can import :func:`build_default_app`
or the underlying :class:`PychestrateApplication` and supply explicit
parameters.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Optional

import sqlalchemy as sa

from sqlalchemy.orm import Session as DbSession, sessionmaker

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)


DATABASE_URL_ENV_VAR = "PYCHESTRATE_DATABASE_URL"
DEBUG_ENV_VAR = "PYCHESTRATE_DEBUG"
CREATE_SCHEMA_ENV_VAR = "PYCHESTRATE_CREATE_SCHEMA"


def _read_database_url() -> str:
    """
        Read the database URL from the environment.

        :returns: The connection string.

        :raises ConfigurationError: When the required env var is missing.
    """
    url = os.environ.get(DATABASE_URL_ENV_VAR, None)
    if url is None:
        err_lines = [
            "Database URL not configured.",
            "Set the {} environment variable to a SQLAlchemy connection string.".format(
                DATABASE_URL_ENV_VAR,
            ),
            "Example: sqlite:///./pychestrate.db",
            "Example: postgresql+psycopg://pychestrate:secret@localhost/pychestrate",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ConfigurationError(err_msg) from None
    if len(url.strip()) == 0:
        err_lines = [
            "Database URL is empty.",
            "Set the {} environment variable to a non-empty SQLAlchemy connection string.".format(
                DATABASE_URL_ENV_VAR,
            ),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ConfigurationError(err_msg) from None
    rtnval = url
    return rtnval


def _read_truthy_env(*, name: str, default: bool) -> bool:
    """
        Coerce an env var to bool.

        :param name: Variable name.
        :param default: Default when unset.

        :returns: The coerced bool.
    """
    raw = os.environ.get(name, None)
    if raw is None:
        return default
    if str(raw).strip().lower() in ("1", "true", "yes", "on"):
        return True
    return False


def build_default_app(
        *,
        database_url: Optional[str] = None,
        debug: Optional[bool] = None,
        create_schema: Optional[bool] = None,
    ) -> PychestrateApplication:
    """
        Build a :class:`PychestrateApplication` using configuration
        sourced from the environment unless explicit overrides are
        supplied.

        :param database_url: Override the ``PYCHESTRATE_DATABASE_URL``
                             env var.
        :param debug: Override the ``PYCHESTRATE_DEBUG`` env var.
        :param create_schema: When True, create all phase-1 tables on
                              boot. Useful for bring-up against an
                              empty SQLite file. Defaults to the
                              ``PYCHESTRATE_CREATE_SCHEMA`` env var,
                              which itself defaults to False.

        :returns: A constructed :class:`PychestrateApplication`.
    """
    if database_url is None:
        url = _read_database_url()
    else:
        url = database_url

    if debug is None:
        debug_value = _read_truthy_env(name=DEBUG_ENV_VAR, default=False)
    else:
        debug_value = debug

    if create_schema is None:
        create_schema_value = _read_truthy_env(
            name=CREATE_SCHEMA_ENV_VAR, default=False,
        )
    else:
        create_schema_value = create_schema

    engine = sa.create_engine(url)
    if create_schema_value is True:
        PychestratePhase1Base.metadata.create_all(engine)

    factory = sessionmaker(bind=engine)

    def _open_session() -> DbSession:
        rtnval = factory()
        return rtnval

    rtnval = PychestrateApplication(
        session_factory=_open_session,
        debug=debug_value,
    )
    return rtnval


def _build_module_application() -> Optional[PychestrateApplication]:
    """
        Construct the module-level ``application`` global, swallowing
        a :class:`ConfigurationError` when imported in a context with
        no DB configured (e.g. ``importlib`` for tooling). Real WSGI
        invocations expect the env var to be present; the swallowed
        path leaves ``application`` as ``None`` so the import succeeds.

        :returns: The constructed app, or ``None`` when the DB URL is
                  not configured at import time.
    """
    try:
        rtnval = build_default_app()
    except ConfigurationError:
        return None
    return rtnval


# WSGI servers (gunicorn, uWSGI) look up this name when invoked with
# ``module:application``. When ``PYCHESTRATE_DATABASE_URL`` is not set
# at import time, this stays ``None`` and the server will surface the
# misconfiguration on first request via the ConfigurationError in
# :func:`build_default_app`.
application: Optional[PychestrateApplication] = _build_module_application()
