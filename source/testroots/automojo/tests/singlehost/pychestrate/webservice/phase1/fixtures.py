"""
.. module:: tests.singlehost.pychestrate.webservice.phase1.fixtures
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared test fixtures for Phase-1 tests.

.. moduleauthor:: Automation Mojo LLC

Provides a helper that builds an in-memory SQLite engine bound to the
Phase-1 declarative metadata, plus a registry-reset helper used to
isolate the extension host from cross-test state.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import Session as DbSession, sessionmaker

from automojo.pychestrate.webservice.extensions.bootstrap import register_phase1_builtin_extensions
from automojo.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from automojo.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from automojo.pychestrate.webservice.projects.metadata_registry import (
    reset_for_testing as reset_projects_metadata_registry,
)
from automojo.pychestrate.webservice.security.rbac import cache as rbac_cache
from automojo.pychestrate.webservice.security.rbac import inheritance as rbac_inheritance


def build_in_memory_session() -> Tuple[sa.engine.Engine, DbSession]:
    """
        Build an in-memory SQLite engine with all Phase-1 tables created.

        :returns: Tuple of (engine, session) — tests are responsible for
                  closing the session. The engine is returned so tests can
                  open additional sessions against the same database.
    """
    engine = sa.create_engine("sqlite://")
    PychestratePhase1Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    rtnval = (engine, session)
    return rtnval


def session_for(*, engine: sa.engine.Engine) -> DbSession:
    """
        Open a fresh session bound to an existing in-memory engine.

        :param engine: The engine returned by :func:`build_in_memory_session`.

        :returns: A new SQLAlchemy session.
    """
    session_factory = sessionmaker(bind=engine)
    rtnval = session_factory()
    return rtnval


def reset_phase1_runtime() -> None:
    """
        Reset the extension registry, in-process event bus, RBAC cache,
        and inheritance wire-once guard; then re-seed the built-in
        extension registrations. Intended as a setup hook at the top of
        Phase-1 tests so they do not leak extension state.

        :returns: None.
    """
    reset_registry_for_testing()
    reset_event_bus()
    rbac_cache.reset_for_testing()
    rbac_inheritance.reset_for_testing()
    reset_projects_metadata_registry()
    register_phase1_builtin_extensions()
    return
