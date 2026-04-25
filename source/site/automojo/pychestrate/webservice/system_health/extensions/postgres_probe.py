"""
.. module:: system_health.extensions.postgres_probe
    :synopsis: PostgresHealthProbe — liveness probe over the configured DB.

The probe runs ``SELECT 1`` against the registered Phase-1
session factory and returns OK on success. The factory is
installed at bootstrap by :func:`set_db_session_factory`;
tests inject a no-op factory to keep the probe pure.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading
import time

from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.system_health.extensions.probe import (
    SystemHealthProbeExtension,
)
from automojo.pychestrate.webservice.system_health.registry import (
    ProbeKind,
    ProbeResult,
    ProbeStatus,
    truncate_last_error,
)


SessionFactory = Callable[[], DbSession]


_LOCK = threading.RLock()
_SESSION_FACTORY: Optional[SessionFactory] = None


def set_db_session_factory(*, factory: Optional[SessionFactory]) -> None:
    """
        Install the SQLAlchemy session factory the probe uses.
        ``None`` clears the registration; the probe will then
        report ``unknown`` until a factory is installed.
    """
    global _SESSION_FACTORY
    with _LOCK:
        _SESSION_FACTORY = factory
    return


def reset_for_testing() -> None:
    """
        Drop the registered session factory.
    """
    global _SESSION_FACTORY
    with _LOCK:
        _SESSION_FACTORY = None
    return


class PostgresHealthProbe(SystemHealthProbeExtension):
    """
        Liveness probe that runs ``SELECT 1`` against the DB
        engine fronted by the active session factory. The
        probe returns ``unknown`` when no factory has been
        installed (so the registry can still build a snapshot
        before the engine attaches).
    """
    resource_extension_name: str = "system_health_probe"

    name: str = "postgres"
    kind: ProbeKind = ProbeKind.LIVENESS
    interval_seconds: float = 10.0
    timeout_seconds: float = 2.0

    @classmethod
    def run_probe(cls) -> ProbeResult:
        with _LOCK:
            factory = _SESSION_FACTORY
        observed_at = datetime.now(tz=timezone.utc)
        if factory is None:
            rtnval = ProbeResult(
                status=ProbeStatus.UNKNOWN,
                duration_ms=0.0,
                observed_at=observed_at,
                last_error="db_session_factory_not_installed",
            )
            return rtnval
        monotonic_start = time.monotonic()
        try:
            session = factory()
            try:
                session.execute(text("SELECT 1"))
            finally:
                session.close()
        except Exception as probe_err:
            elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
            rtnval = ProbeResult(
                status=ProbeStatus.FAIL,
                duration_ms=elapsed_ms,
                observed_at=datetime.now(tz=timezone.utc),
                last_error=truncate_last_error(
                    message="{}: {}".format(
                        type(probe_err).__name__, probe_err,
                    ),
                ),
            )
            return rtnval
        elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
        rtnval = ProbeResult(
            status=ProbeStatus.OK,
            duration_ms=elapsed_ms,
            observed_at=datetime.now(tz=timezone.utc),
        )
        return rtnval
