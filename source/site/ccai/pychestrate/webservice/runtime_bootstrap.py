"""
.. module:: webservice.runtime_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: One-call runtime bootstrap for the Pychestrate
               webservice.

.. moduleauthor:: Code Craft AI LLC

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
  ``PychestratePhase1Base.metadata.create_all``. Production uses
  alembic — see ``alembic/`` at the repo root and the
  ``make db-upgrade`` target.
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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
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

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.extensions.bootstrap import (
    Phase1BootstrapConfig,
    bootstrap_phase1_runtime,
)
from ccai.pychestrate.webservice.extensions.phase2_bootstrap import (
    Phase2BootstrapConfig,
    bootstrap_phase2_runtime,
)
from ccai.pychestrate.webservice.extensions.phase3_bootstrap import (
    Phase3BootstrapConfig,
    bootstrap_phase3_runtime,
)
from ccai.pychestrate.webservice.extensions.phase5_bootstrap import (
    Phase5BootstrapConfig,
    bootstrap_phase5_runtime,
)
from ccai.pychestrate.webservice.extensions.phase6_bootstrap import (
    Phase6BootstrapConfig,
    Phase6BootstrapResult,
    bootstrap_phase6_runtime,
)
from ccai.pychestrate.webservice.extensions.phase7_bootstrap import (
    Phase7BootstrapConfig,
    Phase7BootstrapResult,
    bootstrap_phase7_runtime,
)
from ccai.pychestrate.webservice.extensions.phase8_bootstrap import (
    Phase8BootstrapConfig,
    bootstrap_phase8_runtime,
)
from ccai.pychestrate.webservice.jobs.scheduling import SchedulerHandle
from ccai.pychestrate.webservice.metadata import (
    RUNTIME_ENVIRONMENTS,
    SITE_SHARED_GLOBALS,
)
from ccai.pychestrate.webservice.pychestrate_variables import (
    PychestrateVariables,
    PychestrateVariablesDesc,
)
from ccai.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from ccai.pychestrate.core.orm import (
    PychestrateModelBase as PychestrateLegacyCoreBase,
)
from ccai.pychestrate.webservice.clients.enrollment import ca_adapter
from ccai.pychestrate.webservice.secrets.kek_loader import KekHandle
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes


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
ENV_UI_COOKIE_SECRET_SOURCE: str = "PYCHESTRATE_UI_COOKIE_SECRET_SOURCE"
ENV_UI_COOKIE_SECRET_FILE_PATH: str = "PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH"
ENV_UI_COOKIE_SECRET_ENV_VAR: str = "PYCHESTRATE_UI_COOKIE_SECRET_ENV_VAR"

ENV_ENROLLMENT_CA_SOURCE: str = "PYCHESTRATE_ENROLLMENT_CA_SOURCE"
ENV_ENROLLMENT_CA_FILE_PATH: str = "PYCHESTRATE_ENROLLMENT_CA_FILE_PATH"
ENV_ENROLLMENT_CA_ENV_VAR: str = "PYCHESTRATE_ENROLLMENT_CA_ENV_VAR"
ENV_ENROLLMENT_CA_ID: str = "PYCHESTRATE_ENROLLMENT_CA_ID"
ENV_TEST_MODE: str = "PYCHESTRATE_TEST_MODE"
ENV_TEST_ADMIN_LOGIN: str = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_TEST_ADMIN_EMAIL: str = "PYCHESTRATE_TEST_ADMIN_EMAIL"
ENV_TEST_ADMIN_PASSWORD: str = "PYCHESTRATE_TEST_ADMIN_PASSWORD"
ENV_TEST_ADMIN_DISPLAY_NAME: str = "PYCHESTRATE_TEST_ADMIN_DISPLAY_NAME"


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
        :param test_mode: When True, seed / reset a known admin
                          credential at the end of bootstrap. OFF by
                          default; refused in production.
        :param test_admin_login: Login name for the seeded test admin.
        :param test_admin_email: Primary email for the seeded test
                                 admin.
        :param test_admin_password: Cleartext password for the seeded
                                    test admin. Required when
                                    ``test_mode`` is True.
        :param test_admin_display_name: Display name for the seeded
                                        test admin.
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
    ui_cookie_secret_source: Optional[str]
    ui_cookie_secret_file_path: Optional[str]
    ui_cookie_secret_env_var: Optional[str]
    auto_create_schema: bool
    sql_echo: bool
    # The client-enrollment CA carries defaults for the same reason
    # the test-mode fields below do -- existing constructors keep
    # working unchanged -- and because it is genuinely optional: a
    # deployment that never enrolls pods should not be made to hold
    # a signing key. ``load_config_from_environment`` always
    # populates these from the documented env vars.
    enrollment_ca_source: Optional[str] = None
    enrollment_ca_file_path: Optional[str] = None
    enrollment_ca_env_var: Optional[str] = None
    enrollment_ca_id: Optional[str] = None
    # Test-mode fields carry defaults so existing constructors (tests,
    # the e2e harness) keep working unchanged and test mode stays OFF
    # unless an operator explicitly opts in. ``load_config_from_environment``
    # always populates them from the documented env vars.
    test_mode: bool = False
    test_admin_login: Optional[str] = None
    test_admin_email: Optional[str] = None
    test_admin_password: Optional[str] = None
    test_admin_display_name: Optional[str] = None


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
    phase5_scheduler_handle: Optional[SchedulerHandle] = None
    phase6_result: Optional[Phase6BootstrapResult] = None
    phase7_result: Optional[Phase7BootstrapResult] = None


# ---------------------------------------------------------------------------
# env-driven config loader
# ---------------------------------------------------------------------------


def _read_env(*, name: str, default: Optional[str] = None) -> Optional[str]:
    """
        Read an environment variable, returning ``default`` when
        unset or empty. Pulled out so tests can patch a single
        function rather than every ``os.environ.get`` call.

        Used only for ad-hoc operator-named env vars (e.g. the
        env-var name the operator chose to hold the password
        pepper). Documented ``PYCHESTRATE_*`` config vars are read
        via :func:`_read_app_var` so they flow through the
        :class:`PychestrateVariables` accessor's precedence chain.

        :param name: Environment variable name.
        :param default: Default value when unset / empty.

        :returns: The env var value, or ``default``.
    """
    value = os.environ.get(name, None)
    if value is None or len(value) == 0:
        return default
    rtnval = value
    return rtnval


def _read_app_var(
        *, accessor_name: str, default: Optional[str] = None
    ) -> Optional[str]:
    """
        Read a documented ``PYCHESTRATE_*`` variable through the
        :class:`PychestrateVariables` accessor and apply the same
        "unset or empty string -> default" semantic the legacy
        :func:`_read_env` enforced. The descriptor cache is forgotten
        before the read so each call re-resolves against the current
        ``os.environ`` -- matches the eager ``os.environ.get`` flow
        callers expect from this loader.

        :param accessor_name: Attribute name on
                              :class:`PychestrateVariables` (also the
                              env-var name -- they match by design).
        :param default: Default value when unset / empty.

        :returns: The resolved value, or ``default``.
    """
    var_desc = getattr(PychestrateVariablesDesc, accessor_name)

    from ccai.thisapp.wellknown import ThisApplicationSingleton
    this_app = ThisApplicationSingleton()
    this_app.forget_variable(var_desc)

    value = getattr(PychestrateVariables, accessor_name)
    if value is None or (isinstance(value, str) and len(value) == 0):
        return default
    rtnval = value
    return rtnval


def _read_app_var_bool(*, accessor_name: str, default: bool = False) -> bool:
    """
        Read a documented ``PYCHESTRATE_*`` variable through
        :func:`_read_app_var` and parse it as a boolean. ``true`` /
        ``yes`` / ``1`` (case-insensitive) -> True; everything else
        -> False; absent -> ``default``.

        :param accessor_name: Attribute name on
                              :class:`PychestrateVariables`.
        :param default: Value to return when the variable is unset.

        :returns: Boolean value.
    """
    raw = _read_app_var(accessor_name=accessor_name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    rtnval = normalized in ("true", "yes", "1")
    return rtnval


def _read_env_bool(*, name: str, default: bool = False) -> bool:
    """
        Read an arbitrary OS environment variable as a boolean.
        Kept for parity with :func:`_read_env` -- callers that read
        operator-named env vars (not documented ``PYCHESTRATE_*``
        config) still use this helper.

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
    # Database URL resolves through the ``DATASTORAGE`` variable
    # accessor: env (PYCHESTRATE_DATABASE_URL) -> settings.config ->
    # persona-derived default (sqlite at
    # ${presence_dir}/pychestrate.sqlite). The accessor is
    # ``required=True`` so the lookup raises KeyError if no value
    # surfaces -- reclassify into ConfigurationError so the error
    # message points operators at the canonical env / settings
    # source. Forget first so a fresh ``os.environ`` snapshot is
    # honored on every loader invocation (matches the eager-read
    # semantic the loader had pre-refactor).
    from ccai.thisapp.wellknown import ThisApplicationSingleton
    this_app = ThisApplicationSingleton()
    this_app.forget_variable(
        PychestrateVariablesDesc.PYCHESTRATE_DATABASE_URL
    )
    try:
        database_url = PychestrateVariables.PYCHESTRATE_DATABASE_URL
    except KeyError as key_exc:
        raise ConfigurationError(
            "PYCHESTRATE_DATABASE_URL is required to bootstrap the"
            " runtime: {}".format(str(key_exc))
        ) from key_exc

    runtime_environment = _read_app_var(
        accessor_name="PYCHESTRATE_RUNTIME_ENVIRONMENT",
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

    # KEK_SOURCE / KEK_ID are ``required=True`` on the descriptor so
    # missing values raise KeyError out of the accessor. Reclassify
    # to ConfigurationError preserving the historical error message
    # text -- operators grep for these strings in deploy logs.
    try:
        kek_source = _read_app_var(accessor_name="PYCHESTRATE_KEK_SOURCE")
    except KeyError:
        kek_source = None
    if kek_source is None:
        raise ConfigurationError(
            "{} is required to bootstrap the runtime".format(ENV_KEK_SOURCE)
        )
    try:
        kek_id = _read_app_var(accessor_name="PYCHESTRATE_KEK_ID")
    except KeyError:
        kek_id = None
    if kek_id is None:
        raise ConfigurationError(
            "{} is required to bootstrap the runtime".format(ENV_KEK_ID)
        )

    rtnval = RuntimeBootstrapConfig(
        database_url=database_url,
        runtime_environment=runtime_environment,
        kek_source=kek_source,
        kek_id=kek_id,
        kek_file_path=_read_app_var(
            accessor_name="PYCHESTRATE_KEK_FILE_PATH"
        ),
        kek_env_var=_read_app_var(
            accessor_name="PYCHESTRATE_KEK_ENV_VAR"
        ),
        password_pepper_source=_read_app_var(
            accessor_name="PYCHESTRATE_PASSWORD_PEPPER_SOURCE"
        ),
        password_pepper_file_path=_read_app_var(
            accessor_name="PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH"
        ),
        password_pepper_env_var=_read_app_var(
            accessor_name="PYCHESTRATE_PASSWORD_PEPPER_ENV_VAR"
        ),
        ui_cookie_secret_source=_read_app_var(
            accessor_name="PYCHESTRATE_UI_COOKIE_SECRET_SOURCE"
        ),
        ui_cookie_secret_file_path=_read_app_var(
            accessor_name="PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH"
        ),
        ui_cookie_secret_env_var=_read_app_var(
            accessor_name="PYCHESTRATE_UI_COOKIE_SECRET_ENV_VAR"
        ),
        enrollment_ca_source=_read_app_var(
            accessor_name="PYCHESTRATE_ENROLLMENT_CA_SOURCE"
        ),
        enrollment_ca_file_path=_read_app_var(
            accessor_name="PYCHESTRATE_ENROLLMENT_CA_FILE_PATH"
        ),
        enrollment_ca_env_var=_read_app_var(
            accessor_name="PYCHESTRATE_ENROLLMENT_CA_ENV_VAR"
        ),
        enrollment_ca_id=_read_app_var(
            accessor_name="PYCHESTRATE_ENROLLMENT_CA_ID"
        ),
        auto_create_schema=_read_app_var_bool(
            accessor_name="PYCHESTRATE_AUTO_CREATE_SCHEMA"
        ),
        sql_echo=_read_env_bool(name="PYCHESTRATE_SQL_ECHO"),
        test_mode=_read_app_var_bool(
            accessor_name="PYCHESTRATE_TEST_MODE"
        ),
        test_admin_login=_read_app_var(
            accessor_name="PYCHESTRATE_TEST_ADMIN_LOGIN",
            default="admin",
        ),
        test_admin_email=_read_app_var(
            accessor_name="PYCHESTRATE_TEST_ADMIN_EMAIL",
            default="admin@example.com",
        ),
        test_admin_password=_read_app_var(
            accessor_name="PYCHESTRATE_TEST_ADMIN_PASSWORD"
        ),
        test_admin_display_name=_read_app_var(
            accessor_name="PYCHESTRATE_TEST_ADMIN_DISPLAY_NAME",
            default="Test Admin",
        ),
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
# UI cookie secret loader
# ---------------------------------------------------------------------------


def _load_ui_cookie_secret_or_none(
        *, config: RuntimeBootstrapConfig
    ) -> Optional[bytes]:
    """
        Resolve the UI cookie signing secret from the configured
        source. Returns ``None`` when no source is configured -- a
        deployment can run without the consumer-facing web UI
        wired (the REST surface needs no cookie signing). Mirrors
        the KEK + pepper loader's source dispatch shape exactly.

        Refuses material < 32 bytes so the
        :func:`cookie_session.sign_session_payload` minimum
        secret size is met.

        :param config: Full runtime config.

        :returns: Secret bytes (>= 32 bytes) or ``None`` when no
                  source is configured.
        :raises: ConfigurationError on misconfiguration.
    """
    source = config.ui_cookie_secret_source
    if source is None:
        return None

    if source == "file":
        path = config.ui_cookie_secret_file_path
        if path is None or len(path) == 0:
            raise ConfigurationError(
                "{} 'file' requires {}".format(
                    ENV_UI_COOKIE_SECRET_SOURCE,
                    ENV_UI_COOKIE_SECRET_FILE_PATH,
                )
            )
        if os.path.exists(path) is False:
            err_msg_lines = ["UI cookie secret file not found."]
            err_msg_lines.append("PATH: {}".format(path))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)
        with open(path, "rb") as handle:
            material = handle.read()
        if len(material) < 32:
            raise ConfigurationError(
                "UI cookie secret material must be >= 32 bytes"
            )
        rtnval = bytes(material)
        return rtnval

    if source == "env":
        env_var = config.ui_cookie_secret_env_var
        if env_var is None or len(env_var) == 0:
            raise ConfigurationError(
                "{} 'env' requires {}".format(
                    ENV_UI_COOKIE_SECRET_SOURCE,
                    ENV_UI_COOKIE_SECRET_ENV_VAR,
                )
            )
        raw = os.environ.get(env_var, None)
        if raw is None:
            err_msg_lines = ["UI cookie secret env var not set."]
            err_msg_lines.append("ENV_VAR: {}".format(env_var))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg)
        material = raw.encode("utf-8")
        if len(material) < 32:
            raise ConfigurationError(
                "UI cookie secret material must be >= 32 bytes"
            )
        rtnval = material
        return rtnval

    err_msg_lines = ["Unsupported UI cookie secret source."]
    err_msg_lines.append("SOURCE: {}".format(source))
    err_msg_lines.append("SUPPORTED: file, env")
    err_msg = os.linesep.join(err_msg_lines)
    raise ConfigurationError(err_msg)


# ---------------------------------------------------------------------------
# Client-enrollment CA
# ---------------------------------------------------------------------------


def _install_enrollment_ca_or_skip(
        *, config: RuntimeBootstrapConfig
    ) -> bool:
    """
        Load the client-enrollment CA and install it as the active
        signing CA, when a source is configured.

        The CA is what signs the client certificates minted during
        ``POST /enrollment-tokens/redeem``. Without it that route
        answers 503 and no pod can enroll, so a deployment that
        wants pods must configure this. It stays OPTIONAL because a
        REST-only or UI-only deployment never enrolls anything, and
        those should not be forced to hold a signing key.

        The PEM file must carry the CA certificate AND its private
        key concatenated, and must be the same CA whose certificate
        fronts the mTLS routes -- nginx verifies client certs
        against that CA, so certificates signed by any other one are
        rejected at the edge no matter how valid they are.

        Mirrors the KEK / pepper / cookie-secret loaders' source
        dispatch shape.

        :param config: Full runtime config.

        :returns: True when a CA was installed, False when no source
                  is configured.
        :raises: ConfigurationError on misconfiguration.
    """
    source = config.enrollment_ca_source
    if source is None or len(source) == 0:
        rtnval = False
        return rtnval

    ca_id = config.enrollment_ca_id
    if ca_id is None or len(ca_id) == 0:
        err_msg_lines = ["Enrollment CA is configured without an id."]
        err_msg_lines.append("SOURCE: {}".format(source))
        err_msg_lines.append("REQUIRED: {}".format(ENV_ENROLLMENT_CA_ID))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    handle = ca_adapter.load_ca_at_startup(
        source=source,
        file_path=config.enrollment_ca_file_path,
        env_var=config.enrollment_ca_env_var,
        ca_id=ca_id,
    )
    ca_adapter.set_active_ca(ca=handle)

    rtnval = True
    return rtnval


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
            "Use alembic (``make db-upgrade``) for production schema"
            " management. Set {}=development|testing to enable schema"
            " auto-create for non-production environments.".format(
                ENV_RUNTIME_ENVIRONMENT
            )
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    PychestratePhase1Base.metadata.create_all(engine)
    # The consumer web UI (projects / resources dashboards etc.) is served
    # by the legacy "core ORM + managers" stack, whose tables live on a
    # separate declarative base. Auto-create those too so the dashboards
    # do not 500 with "no such table: projects" on a fresh dev/staging DB.
    PychestrateLegacyCoreBase.metadata.create_all(engine)
    _module_logger.info(
        "pychestrate.runtime_bootstrap.schema_created environment=%s",
        config.runtime_environment,
    )
    return


def _maybe_seed_test_admin(
        *, config: RuntimeBootstrapConfig, session_factory: SessionFactory
    ) -> None:
    """
        Seed / reset a known admin credential when the operator has opted
        in via ``test_mode``. OFF by default. REFUSED in production -- test
        mode injects a backdoor admin from environment variables, which must
        never run on an internet-facing instance, so the gate raises rather
        than silently seeding.

        Idempotent: creates the admin on a fresh database or resets the
        existing admin's password, so the live-deploy test suites always
        authenticate with the same login / password pair.

        Call AFTER the Phase-1 runtime is bootstrapped so the password
        pepper is installed and ``local_flow.hash_password`` succeeds.

        :param config: Full runtime config.
        :param session_factory: Active session factory published by the
                                bootstrap.

        :returns: None.
        :raises: ConfigurationError when test mode is set in production or
                 when no admin password is supplied.
    """
    if config.test_mode is False:
        return

    if config.runtime_environment == RUNTIME_ENVIRONMENTS.PRODUCTION:
        err_msg_lines = [
            "{} is refused in production.".format(ENV_TEST_MODE)
        ]
        err_msg_lines.append(
            "Test mode injects a known admin credential from the"
            " environment and must never run on a production instance."
            " Set {}=development|staging|testing to use it.".format(
                ENV_RUNTIME_ENVIRONMENT
            )
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    password = config.test_admin_password
    if password is None or len(password) == 0:
        err_msg_lines = [
            "{} is set but no admin password was supplied.".format(
                ENV_TEST_MODE
            )
        ]
        err_msg_lines.append(
            "Set {} to the password the test admin should authenticate"
            " with.".format(ENV_TEST_ADMIN_PASSWORD)
        )
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    # Lazy imports so the module stays importable in unit tests that do
    # not exercise the full Phase-1 stack.
    from ccai.pychestrate.webservice.identity.setup.testadmin_seeder import (
        seed_or_reset_test_admin,
    )
    from ccai.pychestrate.webservice.identity.setup.setup_service import (
        mark_setup_complete_for_test_admin,
    )
    from ccai.pychestrate.webservice.security.auth import local_flow

    # Reset exponential login backoff so the freshly seeded admin is not
    # rate-limited by stale failed-attempt state from a prior run.
    reset_helper = getattr(local_flow, "reset_backoff_for_testing", None)
    if reset_helper is not None:
        reset_helper()

    result = seed_or_reset_test_admin(
        session_factory=session_factory,
        login=config.test_admin_login,
        email=config.test_admin_email,
        password=password,
        display_name=config.test_admin_display_name,
    )

    # An injected credential is useless if the setup-gate middleware still
    # redirects every request to the wizard. Stamp setup complete so
    # ``/login`` and the authenticated surfaces are immediately reachable.
    mark_setup_complete_for_test_admin(
        session_factory=session_factory,
        completed_by_user_id=result.user_id,
    )

    _module_logger.warning(
        "pychestrate.runtime_bootstrap.test_admin_seeded action=%s login=%s"
        " user_id=%s legacy_row=%s environment=%s",
        result.action,
        result.login,
        result.user_id,
        result.legacy_written,
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

    ui_cookie_secret = _load_ui_cookie_secret_or_none(config=config)
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = ui_cookie_secret

    _install_enrollment_ca_or_skip(config=config)

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

    phase5_config = Phase5BootstrapConfig(session_factory=session_factory)
    phase5_handle = bootstrap_phase5_runtime(config=phase5_config)

    phase6_config = Phase6BootstrapConfig(session_factory=session_factory)
    phase6_result = bootstrap_phase6_runtime(config=phase6_config)

    # Layer 7 (metrics, dashboards, SLOs, alerts) and Layer 8 (public
    # surface: inbound / outbound webhooks, release channels) were
    # never bootstrapped, so their registries stayed empty (audit
    # ORC-04). Layer 7 also loads the metric catalog, attaches the
    # metric writer, and starts the alert evaluator.
    phase7_config = Phase7BootstrapConfig(session_factory=session_factory)
    phase7_result = bootstrap_phase7_runtime(config=phase7_config)

    phase8_config = Phase8BootstrapConfig(session_factory=session_factory)
    bootstrap_phase8_runtime(config=phase8_config)

    # Test-mode admin seeding runs last so the pepper, KEK, session
    # factory, and RBAC seeding helpers are all live. No-op (and OFF) by
    # default; refused in production.
    _maybe_seed_test_admin(config=config, session_factory=session_factory)

    _module_logger.info(
        "pychestrate.runtime_bootstrap.ready environment=%s kek_id=%s"
        " pepper_loaded=%s ui_cookie_secret_loaded=%s"
        " schema_auto_created=%s",
        config.runtime_environment,
        kek.kek_id,
        pepper is not None,
        ui_cookie_secret is not None,
        config.auto_create_schema,
    )

    rtnval = RuntimeBootstrapResult(
        engine=engine,
        session_factory=session_factory,
        kek=kek,
        phase5_scheduler_handle=phase5_handle,
        phase6_result=phase6_result,
        phase7_result=phase7_result,
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
    "ENV_UI_COOKIE_SECRET_SOURCE",
    "ENV_UI_COOKIE_SECRET_FILE_PATH",
    "ENV_UI_COOKIE_SECRET_ENV_VAR",
    "ENV_TEST_MODE",
    "ENV_TEST_ADMIN_LOGIN",
    "ENV_TEST_ADMIN_EMAIL",
    "ENV_TEST_ADMIN_PASSWORD",
    "ENV_TEST_ADMIN_DISPLAY_NAME",
    "RuntimeBootstrapConfig",
    "RuntimeBootstrapResult",
    "load_config_from_environment",
    "bootstrap_runtime",
]
