"""
.. module:: webservice.pychestrate_variables
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Application variable declarations for pychestrate.

.. moduleauthor:: Automation Mojo LLC

Declarative pychestrate application variables using
:mod:`automojo.thisapp.appvardesc` / :class:`AppVarSet` /
:class:`AppVarAccessor`. Variables resolve through the
``ThisApplication`` precedence chain at call time:

    application overrides  >  environment  >  settings file  >  default

Sections are named by **function** -- ``DATASTORAGE`` for anything
that touches persistent state, future sections (``SECURITY`` for
KEK / pepper, ``NETWORK`` for bind host / port, etc.) come later.

Variable attribute names are also the env-var names and the
settings.config keys, e.g. ``PYCHESTRATE_DATABASE_URL`` is read
from ``os.environ["PYCHESTRATE_DATABASE_URL"]`` OR
``settings.config[DATASTORAGE].PYCHESTRATE_DATABASE_URL``.

Usage
-----

    from automojo.pychestrate.webservice.pychestrate_variables import (
        PychestrateVariables,
    )

    db_url = PychestrateVariables.PYCHESTRATE_DATABASE_URL

The accessor pulls the value from the
:func:`automojo.thisapp.wellknown.ThisApplicationSingleton` at call
time. The persona must be established
(``establish_webapp_persona(name="pychestrate", ...)``) before the
first access; the singleton's variable resolution depends on it.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from automojo.thisapp.appvardesc import AppVarDesc, VariableSource
from automojo.thisapp.appvaraccessor import AppVarAccessor
from automojo.thisapp.appvarset import AppVarSet
from automojo.thisapp.personavariables import PersonaVariables


# Section names. Functional groupings; matches the convention used
# by ``PersonaVariables`` (which puts persona-management variables
# in section "DEFAULT" by virtue of source=NONE).
SECTION_DATASTORAGE: str = "DATASTORAGE"


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
        (``DATASTORAGE``, ``SECURITY``, ``NETWORK``, etc.). Each
        :class:`AppVarDesc`'s ``source`` flag controls which input
        channels the resolver consults:

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


__all__ = [
    "PychestrateVariables",
    "PychestrateVariablesDesc",
    "SECTION_DATASTORAGE",
]
