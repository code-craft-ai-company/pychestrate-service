"""
.. module:: webservice.runtime_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One-call runtime bootstrap for the Pychestrate
               webservice.

.. moduleauthor:: Automation Mojo LLC

The webservice declares its operator-supplied state in
:class:`SITE_SHARED_GLOBALS` (database engine, session factory,
SMTP credentials, etc.) and exposes phase-specific bootstrap
helpers (``bootstrap_phase1_runtime`` / ``bootstrap_phase2_runtime``
/ ``bootstrap_phase3_runtime``) that wire the KEK, password
pepper, and bus subscribers from a caller-supplied config. None
of those helpers were called by ``pychestrate_website_main``;
the service started with no DB connection, no KEK, no pepper,
and no bus wiring — every request flowed into the 503 fail-soft
path the session middleware emits when no factory is configured.

This module fixes that. :func:`bootstrap_runtime` is the one-call
entry that:

* builds a SQLAlchemy engine + session factory from a
  caller-supplied :class:`RuntimeBootstrapConfig`
* publishes them on
  :data:`SITE_SHARED_GLOBALS.DATABASE_ENGINE` /
  :data:`.DATABASE_SESSION_FACTORY` so the rest of the service
  can resolve them
* (development / testing only) creates every Phase-1/2/3 ORM
  table on the engine via
  ``PychestratePhase1Base.metadata.create_all`` — production
  uses out-of-band migrations
* loads the KEK, sets the active password pepper, and wires the
  audit + Phase-2 + Phase-3 bus subscribers in the documented
  order

:func:`load_config_from_environment` is the convenience that
reads operator config from environment variables (a
:file:`.env`-style flow) so the bootstrap can be driven by the
deployer without code changes.

Required environment variables (production)
-------------------------------------------

* ``PYCHESTRATE_DATABASE_URL`` — SQLAlchemy URL.
* ``PYCHESTRATE_RUNTIME_ENVIRONMENT`` — one of ``development``,
  ``staging``, ``production``, ``testing``. Defaults to
  ``production`` so an unset value is the safer choice.
* ``PYCHESTRATE_KEK_SOURCE`` — ``file`` or ``env``.
* ``PYCHESTRATE_KEK_ID`` — operator-assigned identifier for the
  active KEK.
* For ``KEK_SOURCE=file``: ``PYCHESTRATE_KEK_FILE_PATH``.
* For ``KEK_SOURCE=env``: ``PYCHESTRATE_KEK_ENV_VAR`` (the name of
  the env var holding the key material — NOT the material
  itself, mirrors ``load_kek_at_startup``).

Optional
~~~~~~~~

* ``PYCHESTRATE_PASSWORD_PEPPER_SOURCE`` — ``file`` or ``env``.
  When unset, the active pepper is left empty (auth flow then
  fails on first password verify).
* For pepper sources, ``PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH`` /
  ``PYCHESTRATE_PASSWORD_PEPPER_ENV_VAR``.
* ``PYCHESTRATE_AUTO_CREATE_SCHEMA`` — ``true`` to run
  ``metadata.create_all`` at boot. Refused in
  ``RUNTIME_ENVIRONMENT=production`` to keep operators on the
  real migration path.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine.base import Engine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.extensions.bootstrap import (
    Phase1BootstrapConfig,
    bootstrap_phase1_runtime,
)
from automojo.pychestrate.webservice.extensions.phase2_bootstrap import (
    Phase2BootstrapConfig,
    bootstrap_phase2_runtime,
)
from automojo.pychestrate.webservice.extensions.phase3_bootstrap import (
    Phase3BootstrapConfig,
    bootstrap_phase3_runtime,
)
from automojo.pychestrate.webservice.metadata import (
    RUNTIME_ENVIRONMENTS,
    SITE_SHARED_GLOBALS,
)
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.secrets.kek_loader import KekHandle
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes


SessionFactory = Callable[[], DbSession]


_module_logger = logging.getLogger(__name__)


# Documented environment-variable names. Keep the prefix consistent so
# operators can grep the deploy environment for ``PYCHESTRATE_*``.
ENV_DATABASE_URL: str = "PYCHESTRATE_DATABASE_URL"
ENV_RUNTIME_ENVIRONMENT: str = "PYCHESTRATE_RUNTIME_ENVIRONMENT"
ENV_AUTO_CREATE_SCHEMA: str = "PYCHESTRATE_AUTO_CREATE_SCHEMA"
ENV_KEK_SOURCE: str = "PYCHESTRATE_KEK_SOURCE"
ENV_KEK_ID: str = "PYCHESTRATE_KEK_ID"
ENV_KEK_FILE_PATH: str = "PYCHESTRATE_KEK_FILE_PATH"
ENV_KEK_ENV_VAR: str = "PYCHESTRATE_KEK_ENV_VAR"
ENV_PEPPER_SOURCE: str = "PYCHESTRATE_PASSWORD_PEPPER_SOURCE"
ENV_PEPPER_FILE_PATH: str = "PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH"
ENV_PEPPER_ENV_VAR: str = "PYCHESTRATE_PASSWORD_PEPPER_ENV_VAR"


_VALID_RUNTIME_ENVIRONMENTS = (
    RUNTIME_ENVIRONMENTS.DEVELOPMENT,
    RUNTIME_ENVIRONMENTS.STAGING,
    RUNTIME_ENVIRONMENTS.PRODUCTION,
    RUNTIME_ENVIRONMENTS.TESTING,
)


@dataclass(frozen=True)
class RuntimeBootstrapConfig:
    """
        Operator-supplied configuration for the one-call runtime
        bootstrap.

        :param database_url: SQLAlchemy database URL passed to
                             ``create_engine``.
        :param runtime_environment: One of the
                                    :class:`RUNTIME_ENVIRONMENTS`
                                    values. Used to gate
                                    development-only behaviors like
                                    ``create_all``.
        :param kek_source: ``"file"`` or ``"env"``.
        :param kek_id: Operator-assigned KEK identifier (logged at
                       startup).
        :param kek_file_path: Path to the KEK material file when
                              ``kek_source == "file"``.
        :param kek_env_var: Environment variable holding KEK
                            material when ``kek_source == "env"``.
        :param password_pepper_source: Optional ``"file"`` or
                                       ``"env"``; ``None`` skips
                                       pepper installation.
        :param password_pepper_file_path: Path when
                                          ``password_pepper_source
                                          == "file"``.
        :param password_pepper_env_var: Env var when
                                        ``password_pepper_source ==
                                        "env"``.
        :param auto_create_schema: When True, run
                                   ``PychestratePhase1Base.metadata.
                                   create_all`` after engine
                                   construction. Refused in
                                   production.
        :param sql_echo: When True, SQLAlchemy echoes every
                         executed statement. For local debugging.
    """
    database_url: str
    runtime_environment: str
    kek_source: str
    kek_id: str
    kek_file_path: Optional[str]
    kek_env_var: Optional[str]
    password_pepper_source: Optional[str]
    password_pepper_file_path: Optional[str]
    password_pepper_env_var: Optional[str]
    auto_create_schema: bool
    sql_echo: bool


@dataclass(frozen=True)
class RuntimeBootstrapResult:
    """
        Return value from :func:`bootstrap_runtime`. Carries the
        objects the bootstrap built so callers (operators, tests)
        can hold a reference for diagnostics or shutdown handling.

        :param engine: The active SQLAlchemy engine.
        :param session_factory: Callable that returns a fresh
                                ``DbSession``.
        :param kek: Loaded :class:`KekHandle`.
    """
    engine: Engine
    session_factory: SessionFactory
    kek: KekHandle


# ---------------------------------------------------------------------------
# env-driven config loader
# ---------------------------------------------------------------------------


def _read_env(*, name: str, default: Optional[str] = None) -> Optional[str]:
    """
        Read an environment variable, returning ``default`` when
        unset or empty. Pulled out so tests can patch a single
        function rather than every ``os.environ.get`` call.

        :param name: Environment variable name.
        :param default: Default value when unset / empty.

        :returns: The env var value, or ``default``.
    """
    value = os.environ.get(name, None)
    if value is None or len(value) == 0:
        return default
    rtnval = value
    return rtnval


def _read_env_bool(*, name: str, default: bool = False) -> bool:
    """
        Read an environment variable as a boolean. ``true`` /
        ``yes`` / ``1`` (case-insensitive) → True; everything else
        → False; absent → ``default``.

        :param name: Environment variable name.
        :param default: Value to return when the env var is unset.

        :returns: Boolean value.
    """
    raw = _read_env(name=name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    rtnval = normalized in ("true", "yes", "1")
    return rtnval


def load_config_from_environment() -> RuntimeBootstrapConfig:
    """
        Build a :class:`RuntimeBootstrapConfig` from documented
        environment variables. Raises :class:`ConfigurationError` on
        missing-required so service startup bails rather than booting
        partially configured.

        :returns: Populated :class:`RuntimeBootstrapConfig`.
        :raises: ConfigurationError on missing required fields.
    """
    database_url = _read_env(name=ENV_DATABASE_URL)
    if database_url is None:
        raise ConfigurationError(
            "{} is required to bootstrap the runtime".format(ENV_DATABASE_URL)
        )

    runtime_environment = _read_env(
        name=ENV_RUNTIME_ENVIRONMENT,
        default=RUNTIME_ENVIRONMENTS.PRODUCTION,
    )
    if runtime_environment not in _VALID_RUNTIME_ENVIRONMENTS:
        err_msg_lines = ["Unrecognized {}.".format(ENV_RUNTIME_ENVIRONMENT)]
        err_msg_lines.append("VALUE: {}".format(runtime_environment))
        err_msg_lines.append(
            "ALLOWED: {}".format(", ".join(_VALID_RUNTIME_ENVIRONMENTS))
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    kek_source = _read_env(name=ENV_KEK_SOURCE)
    if kek_source is None:
        raise ConfigurationError(
            "{} is required to bootstrap the runtime".format(ENV_KEK_SOURCE)
        )
    kek_id = _read_env(name=ENV_KEK_ID)
    if kek_id is None:
        raise ConfigurationError(
            "{} is required to bootstrap the runtime".format(ENV_KEK_ID)
        )

    rtnval = RuntimeBootstrapConfig(
        database_url=database_url,
        runtime_environment=runtime_environment,
        kek_source=kek_source,
        kek_id=kek_id,
        kek_file_path=_read_env(name=ENV_KEK_FILE_PATH),
        kek_env_var=_read_env(name=ENV_KEK_ENV_VAR),
        password_pepper_source=_read_env(name=ENV_PEPPER_SOURCE),
        password_pepper_file_path=_read_env(name=ENV_PEPPER_FILE_PATH),
        password_pepper_env_var=_read_env(name=ENV_PEPPER_ENV_VAR),
        auto_create_schema=_read_env_bool(name=ENV_AUTO_CREATE_SCHEMA),
        sql_echo=_read_env_bool(name="PYCHESTRATE_SQL_ECHO"),
    )
    return rtnval


# ---------------------------------------------------------------------------
# pepper loader
# ---------------------------------------------------------------------------


def _load_pepper_or_none(
        *, config: RuntimeBootstrapConfig
    ) -> Optional[SecretBytes]:
    """
        Resolve the password pepper material from the configured
        source. ``None`` source returns ``None`` (auth-disabled
        deployments are legal during early bring-up). Mirrors the
        KEK loader's source dispatch.

        :param config: Full runtime config.

        :returns: :class:`SecretBytes` or ``None``.
        :raises: ConfigurationError on misconfiguration.
    """
    source = config.password_pepper_source
    if source is None:
        return None

    if source == "file":
        path = config.password_pepper_file_path
        if path is None or len(path) == 0:
            raise ConfigurationError(
                "{} 'file' requires {}".format(
                    ENV_PEPPER_SOURCE, ENV_PEPPER_FILE_PATH
                )
            )
        if os.path.exists(path) is False:
            err_msg_lines = ["Password pepper file not found."]
            err_msg_lines.append("PATH: {}".format(path))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)
        with open(path, "rb") as handle:
            material = handle.read()
        rtnval = SecretBytes(material)
        return rtnval

    if source == "env":
        env_var = config.password_pepper_env_var
        if env_var is None or len(env_var) == 0:
            raise ConfigurationError(
                "{} 'env' requires {}".format(
                    ENV_PEPPER_SOURCE, ENV_PEPPER_ENV_VAR
                )
            )
        raw = os.environ.get(env_var, None)
        if raw is None:
            err_msg_lines = ["Password pepper environment variable not set."]
            err_msg_lines.append("ENV_VAR: {}".format(env_var))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)
        rtnval = SecretBytes(raw.encode("utf-8"))
        return rtnval

    err_msg_lines = ["Unsupported password pepper source."]
    err_msg_lines.append("SOURCE: {}".format(source))
    err_msg_lines.append("SUPPORTED: file, env")
    err_msg = os.linesep.join(err_msg_lines)
    raise ConfigurationError(err_msg)


# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------


def _build_engine_and_factory(
        *, config: RuntimeBootstrapConfig
    ) -> tuple:
    """
        Build a SQLAlchemy engine and a sessionmaker-backed factory
        from the supplied URL. Engine connection-pool tuning is
        intentionally left to defaults — operators tune via the URL
        query string when needed (e.g. ``?pool_size=20``).

        :param config: Full runtime config.

        :returns: ``(engine, session_factory)`` tuple.
    """
    engine = create_engine(config.database_url, echo=config.sql_echo)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    rtnval = (engine, factory)
    return rtnval


def _publish_globals(
        *, engine: Engine, session_factory: SessionFactory
    ) -> None:
    """
        Set the engine + session factory on
        :class:`SITE_SHARED_GLOBALS` so the rest of the service can
        find them. Pulled out so tests can verify the publication
        without running the full bootstrap.

        :param engine: Active SQLAlchemy engine.
        :param session_factory: Active session factory.

        :returns: None.
    """
    SITE_SHARED_GLOBALS.DATABASE_ENGINE = engine
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = session_factory
    return


def _maybe_create_schema(
        *, engine: Engine, config: RuntimeBootstrapConfig
    ) -> None:
    """
        Run ``PychestratePhase1Base.metadata.create_all`` when the
        operator has opted in via ``auto_create_schema``. Refused in
        production — production uses out-of-band schema management
        (alembic or equivalent).

        :param engine: Active SQLAlchemy engine.
        :param config: Full runtime config.

        :returns: None.
        :raises: ConfigurationError when ``auto_create_schema`` is
                 set in production.
    """
    if config.auto_create_schema is False:
        return

    if config.runtime_environment == RUNTIME_ENVIRONMENTS.PRODUCTION:
        err_msg_lines = [
            "{} is refused in production.".format(ENV_AUTO_CREATE_SCHEMA)
        ]
        err_msg_lines.append(
            "Use out-of-band migrations (alembic) for production schema"
            " management. Set {}=development|testing to enable schema"
            " auto-create.".format(ENV_RUNTIME_ENVIRONMENT)
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    PychestratePhase1Base.metadata.create_all(engine)
    _module_logger.info(
        "pychestrate.runtime_bootstrap.schema_created environment=%s",
        config.runtime_environment,
    )
    return


# ---------------------------------------------------------------------------
# One-call entry
# ---------------------------------------------------------------------------


def bootstrap_runtime(
        *, config: RuntimeBootstrapConfig
    ) -> RuntimeBootstrapResult:
    """
        Build the runtime — engine, session factory, KEK, password
        pepper, and bus subscribers — and publish the operator-facing
        globals so the rest of the service can resolve them.

        Call this once at service startup BEFORE
        ``PychestrateSessionMiddleware`` is installed and BEFORE
        ``run_server`` begins serving. Order with respect to
        ``app.startup()`` is irrelevant — this function does not
        touch the webworks application.

        :param config: Caller-supplied
                       :class:`RuntimeBootstrapConfig`.

        :returns: :class:`RuntimeBootstrapResult` carrying the active
                  engine, session factory, and KEK handle.

        :raises: ConfigurationError on misconfiguration.
    """
    engine, session_factory = _build_engine_and_factory(config=config)
    _publish_globals(engine=engine, session_factory=session_factory)
    _maybe_create_schema(engine=engine, config=config)

    pepper = _load_pepper_or_none(config=config)

    phase1_config = Phase1BootstrapConfig(
        kek_source=config.kek_source,
        kek_file_path=config.kek_file_path,
        kek_env_var=config.kek_env_var,
        kek_id=config.kek_id,
        password_pepper=pepper,
        session_factory=session_factory,
    )
    kek = bootstrap_phase1_runtime(config=phase1_config)

    phase2_config = Phase2BootstrapConfig(session_factory=session_factory)
    bootstrap_phase2_runtime(config=phase2_config)

    phase3_config = Phase3BootstrapConfig(session_factory=session_factory)
    bootstrap_phase3_runtime(config=phase3_config)

    _module_logger.info(
        "pychestrate.runtime_bootstrap.ready environment=%s kek_id=%s"
        " pepper_loaded=%s schema_auto_created=%s",
        config.runtime_environment,
        kek.kek_id,
        pepper is not None,
        config.auto_create_schema,
    )

    rtnval = RuntimeBootstrapResult(
        engine=engine,
        session_factory=session_factory,
        kek=kek,
    )
    return rtnval


__all__ = [
    "ENV_DATABASE_URL",
    "ENV_RUNTIME_ENVIRONMENT",
    "ENV_AUTO_CREATE_SCHEMA",
    "ENV_KEK_SOURCE",
    "ENV_KEK_ID",
    "ENV_KEK_FILE_PATH",
    "ENV_KEK_ENV_VAR",
    "ENV_PEPPER_SOURCE",
    "ENV_PEPPER_FILE_PATH",
    "ENV_PEPPER_ENV_VAR",
    "RuntimeBootstrapConfig",
    "RuntimeBootstrapResult",
    "load_config_from_environment",
    "bootstrap_runtime",
]
