"""
.. module:: webservice.pychestrate_variables
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Application variable declarations for pychestrate.

.. moduleauthor:: Code Craft AI LLC

Declarative pychestrate application variables using
:mod:`ccai.thisapp.appvardesc` / :class:`AppVarSet` /
:class:`AppVarAccessor`. Variables resolve through the
``ThisApplication`` precedence chain at call time:

    application overrides  >  environment  >  settings file  >  default

Sections are named by **function** -- ``DATASTORAGE`` for anything
that touches persistent state, ``SECURITY`` for KEK / pepper /
cookie material, ``NETWORK`` for bind host / port, ``RUNTIME``
for environment / schema-create flags. Future sections continue
the pattern.

Variable attribute names are also the env-var names and the
settings.config keys, e.g. ``PYCHESTRATE_DATABASE_URL`` is read
from ``os.environ["PYCHESTRATE_DATABASE_URL"]`` OR
``settings.config[DATASTORAGE].PYCHESTRATE_DATABASE_URL``.

Usage
-----

    from ccai.pychestrate.webservice.pychestrate_variables import (
        PychestrateVariables,
    )

    db_url = PychestrateVariables.PYCHESTRATE_DATABASE_URL

The accessor pulls the value from the
:func:`ccai.thisapp.wellknown.ThisApplicationSingleton` at call
time. The persona must be established
(``establish_webapp_persona(name="pychestrate", ...)``) before the
first access; the singleton's variable resolution depends on it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from ccai.thisapp.appvardesc import AppVarDesc, VariableSource
from ccai.thisapp.appvaraccessor import AppVarAccessor
from ccai.thisapp.appvarset import AppVarSet
from ccai.thisapp.personavariables import PersonaVariables


# Section names. Functional groupings; matches the convention used
# by ``PersonaVariables`` (which puts persona-management variables
# in section "DEFAULT" by virtue of source=NONE).
SECTION_DATASTORAGE: str = "DATASTORAGE"
SECTION_SECURITY: str = "SECURITY"
SECTION_NETWORK: str = "NETWORK"
SECTION_RUNTIME: str = "RUNTIME"


# Default-value computers. Pulled out as named functions (not
# inline lambdas) so the resolution chain is traceable in logs and
# stack traces. Each is invoked LAZILY by
# ``AppVarDesc.default`` -- the property invokes the callable at
# get-time, not at class-construction time, so persona-singleton
# access here is safe.


def _default_database_url() -> str:
    """
        Compute the default SQLite URL inside the pychestrate
        presence directory. Resolved at variable-lookup time so the
        persona's ``presence_dir`` is already established by the
        ``establish_webapp_persona`` call.

        Operators who want to point at Postgres (or relocate the
        SQLite file) set the env var ``PYCHESTRATE_DATABASE_URL``
        directly; the env-var read takes precedence over this
        default.

        :returns: SQLAlchemy URL string.
    """
    presence_dir = PersonaVariables.AM_PRESENCE_DIR
    expanded_presence = os.path.expanduser(presence_dir)
    db_path = os.path.join(expanded_presence, "pychestrate.sqlite")
    rtnval = "sqlite:///{}".format(db_path)
    return rtnval


class PychestrateVariablesDesc(AppVarSet):
    """
        Declarative pychestrate variable descriptors.

        Add new variables here, grouped into functional sections
        (``DATASTORAGE``, ``SECURITY``, ``NETWORK``, ``RUNTIME``,
        etc.). Each :class:`AppVarDesc`'s ``source`` flag controls
        which input channels the resolver consults:

        * ``VariableSource.ENVIRONMENT`` -- read ``os.environ[NAME]``.
        * ``VariableSource.SETTINGS`` -- read from settings.config.
        * ``VariableSource.BOTH`` -- env first, then settings.
        * ``VariableSource.NONE`` -- defaults / overrides only.

        Defaults are callables so persona-derived paths resolve at
        get-time rather than at import-time.
    """

    PYCHESTRATE_DATABASE_URL = AppVarDesc(
        section=SECTION_DATASTORAGE,
        source=VariableSource.BOTH,
        default=_default_database_url,
        required=True,
    )

    # ------------------------------------------------------------------
    # SECURITY section -- KEK, password pepper, UI cookie secret
    # ------------------------------------------------------------------

    PYCHESTRATE_KEK_SOURCE = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        required=True,
    )

    PYCHESTRATE_KEK_ID = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        required=True,
    )

    PYCHESTRATE_KEK_FILE_PATH = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        default=None,
    )

    PYCHESTRATE_KEK_ENV_VAR = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        default=None,
    )

    PYCHESTRATE_PASSWORD_PEPPER_SOURCE = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        default=None,
    )

    PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        default=None,
    )

    PYCHESTRATE_PASSWORD_PEPPER_ENV_VAR = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        default=None,
    )

    PYCHESTRATE_UI_COOKIE_SECRET_SOURCE = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        default=None,
    )

    PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        default=None,
    )

    PYCHESTRATE_UI_COOKIE_SECRET_ENV_VAR = AppVarDesc(
        section=SECTION_SECURITY,
        source=VariableSource.ENVIRONMENT,
        default=None,
    )

    # ------------------------------------------------------------------
    # NETWORK section -- bind host / port for the embedded server
    # ------------------------------------------------------------------

    PYCHESTRATE_BIND_HOST = AppVarDesc(
        section=SECTION_NETWORK,
        source=VariableSource.ENVIRONMENT,
        default="127.0.0.1",
    )

    # Kept as a string so the existing ``int(...)`` cast at the call
    # site continues to work unchanged.
    PYCHESTRATE_BIND_PORT = AppVarDesc(
        section=SECTION_NETWORK,
        source=VariableSource.ENVIRONMENT,
        default="8888",
    )

    # ------------------------------------------------------------------
    # RUNTIME section -- runtime-environment + schema-create flag
    # ------------------------------------------------------------------

    # Default kept as a literal "production" string rather than
    # ``RUNTIME_ENVIRONMENTS.PRODUCTION`` to avoid pulling
    # ``ccai.pychestrate.webservice.metadata`` into this module
    # (keeps the variable-declaration module dependency-light, and
    # the literal matches the metadata constant exactly).
    PYCHESTRATE_RUNTIME_ENVIRONMENT = AppVarDesc(
        section=SECTION_RUNTIME,
        source=VariableSource.ENVIRONMENT,
        default="production",
    )

    # Kept as a string so the existing ``_read_env_bool`` parser at
    # the call site continues to interpret ``true|yes|1`` unchanged.
    PYCHESTRATE_AUTO_CREATE_SCHEMA = AppVarDesc(
        section=SECTION_RUNTIME,
        source=VariableSource.ENVIRONMENT,
        default="false",
    )

    # ------------------------------------------------------------------
    # RUNTIME section -- test mode
    #
    # Test mode is OFF by default and REFUSED in production (the
    # bootstrap gate raises ConfigurationError). When enabled in a
    # non-production environment, the runtime seeds / resets a known
    # admin credential from the variables below so the live-deploy test
    # suites can authenticate deterministically. Never enable on an
    # internet-facing instance -- it injects a backdoor admin by design.
    # ------------------------------------------------------------------

    # Kept as a string so the ``_read_env_bool`` parser at the call site
    # interprets ``true|yes|1`` unchanged.
    PYCHESTRATE_TEST_MODE = AppVarDesc(
        section=SECTION_RUNTIME,
        source=VariableSource.ENVIRONMENT,
        default="false",
    )

    PYCHESTRATE_TEST_ADMIN_LOGIN = AppVarDesc(
        section=SECTION_RUNTIME,
        source=VariableSource.ENVIRONMENT,
        default="admin",
    )

    PYCHESTRATE_TEST_ADMIN_EMAIL = AppVarDesc(
        section=SECTION_RUNTIME,
        source=VariableSource.ENVIRONMENT,
        default="admin@example.com",
    )

    # No default -- a password MUST be supplied when test mode is on.
    # The bootstrap gate raises ConfigurationError when it is missing.
    PYCHESTRATE_TEST_ADMIN_PASSWORD = AppVarDesc(
        section=SECTION_RUNTIME,
        source=VariableSource.ENVIRONMENT,
        default=None,
    )

    PYCHESTRATE_TEST_ADMIN_DISPLAY_NAME = AppVarDesc(
        section=SECTION_RUNTIME,
        source=VariableSource.ENVIRONMENT,
        default="Test Admin",
    )


class PychestrateVariables:
    """
        Descriptor-style accessors for
        :class:`PychestrateVariablesDesc`. Access an attribute to
        resolve the value through the
        :func:`ThisApplicationSingleton` precedence chain.

        Read-only -- assignment raises ``AttributeError``. Apply
        overrides via
        ``ThisApplicationSingleton().override_variable_value(...)``
        when you need to inject a value at a higher precedence than
        env / settings.
    """

    PYCHESTRATE_DATABASE_URL = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_DATABASE_URL
    )

    PYCHESTRATE_KEK_SOURCE = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_KEK_SOURCE
    )
    PYCHESTRATE_KEK_ID = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_KEK_ID
    )
    PYCHESTRATE_KEK_FILE_PATH = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_KEK_FILE_PATH
    )
    PYCHESTRATE_KEK_ENV_VAR = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_KEK_ENV_VAR
    )
    PYCHESTRATE_PASSWORD_PEPPER_SOURCE = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_PASSWORD_PEPPER_SOURCE
    )
    PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH
    )
    PYCHESTRATE_PASSWORD_PEPPER_ENV_VAR = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_PASSWORD_PEPPER_ENV_VAR
    )
    PYCHESTRATE_UI_COOKIE_SECRET_SOURCE = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_UI_COOKIE_SECRET_SOURCE
    )
    PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH
    )
    PYCHESTRATE_UI_COOKIE_SECRET_ENV_VAR = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_UI_COOKIE_SECRET_ENV_VAR
    )

    PYCHESTRATE_BIND_HOST = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_BIND_HOST
    )
    PYCHESTRATE_BIND_PORT = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_BIND_PORT
    )

    PYCHESTRATE_RUNTIME_ENVIRONMENT = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_RUNTIME_ENVIRONMENT
    )
    PYCHESTRATE_AUTO_CREATE_SCHEMA = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_AUTO_CREATE_SCHEMA
    )

    PYCHESTRATE_TEST_MODE = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_TEST_MODE
    )
    PYCHESTRATE_TEST_ADMIN_LOGIN = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_TEST_ADMIN_LOGIN
    )
    PYCHESTRATE_TEST_ADMIN_EMAIL = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_TEST_ADMIN_EMAIL
    )
    PYCHESTRATE_TEST_ADMIN_PASSWORD = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_TEST_ADMIN_PASSWORD
    )
    PYCHESTRATE_TEST_ADMIN_DISPLAY_NAME = AppVarAccessor(
        PychestrateVariablesDesc.PYCHESTRATE_TEST_ADMIN_DISPLAY_NAME
    )


__all__ = [
    "PychestrateVariables",
    "PychestrateVariablesDesc",
    "SECTION_DATASTORAGE",
    "SECTION_SECURITY",
    "SECTION_NETWORK",
    "SECTION_RUNTIME",
]
