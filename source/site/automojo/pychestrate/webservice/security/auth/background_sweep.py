"""
.. module:: security.auth.background_sweep
    :synopsis: Periodic sweep of expired auth_oidc_state + auth_saml_replay_cache (M3 T3.4).

The 1-authentication M3 hardening pass calls for a
background job that prunes the two ephemeral auth tables:

* ``auth_oidc_state`` — one-shot rows with a ``expires_at``
  TTL that survive past the IdP-redirect window only when
  the user abandons the flow.
* ``auth_saml_replay_cache`` — replay-defense rows that
  can be pruned once their ``not_on_or_after`` is in the
  past (no conforming validator will accept the assertion
  past that horizon, so the row's job is done).

This module ships :func:`sweep_auth_caches` — the
controller-facing entry point a scheduler (cron / APScheduler
/ K8s CronJob) calls on a fixed cadence. The sweep:

1. Opens a trace span (``session.resolve`` group — the
   sweep is a maintenance flow, not a user-facing one,
   but the span shape mirrors the user-facing flows so
   one ingest pipeline catches both).
2. Runs the two underlying ``sweep_expired`` helpers.
3. Returns a :class:`SweepReport` summarizing the counts,
   timestamps, and elapsed time.
4. Emits a structured log event so operators get a record
   of every sweep run.

The sweep is idempotent and re-entrant — calling it twice
in a row simply finds zero rows the second time.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.security.auth import log_events
from automojo.pychestrate.webservice.security.auth.oidc import state as oidc_state
from automojo.pychestrate.webservice.security.auth.saml import (
    replay_cache as saml_replay_cache,
)
from automojo.pychestrate.webservice.security.auth.tracing import (
    start_span,
)


SPAN_AUTH_BACKGROUND_SWEEP: str = "auth.background_sweep"
LOG_EVENT_AUTH_BACKGROUND_SWEPT: str = "auth.background.swept"


@dataclass(frozen=True)
class SweepReport:
    """
        Result bundle returned by :func:`sweep_auth_caches`.

        :param oidc_state_rows_removed: Count of expired
                                        ``auth_oidc_state``
                                        rows the sweep
                                        deleted.
        :param saml_replay_rows_removed: Count of stale
                                         ``auth_saml_replay_cache``
                                         rows the sweep
                                         deleted.
        :param started_at: tz-aware UTC timestamp when the
                           sweep entered.
        :param ended_at: tz-aware UTC timestamp when the
                         sweep finished.
    """
    oidc_state_rows_removed: int
    saml_replay_rows_removed: int
    started_at: datetime
    ended_at: datetime

    def total_rows_removed(self) -> int:
        """
            Convenience accessor — the sum of both counts
            for operator dashboards that care about the
            pruning rate without distinguishing the two
            tables.
        """
        rtnval = (
            self.oidc_state_rows_removed
            + self.saml_replay_rows_removed
        )
        return rtnval

    def duration_seconds(self) -> float:
        """
            Elapsed seconds between ``started_at`` and
            ``ended_at``.
        """
        delta = self.ended_at - self.started_at
        rtnval = delta.total_seconds()
        return rtnval


def sweep_auth_caches(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None,
        logger: Optional[logging.Logger] = None
    ) -> SweepReport:
    """
        Run the combined sweep across
        ``auth_oidc_state`` and ``auth_saml_replay_cache``.

        :param db_session: Active SQLAlchemy session — both
                           sub-sweeps commit their own
                           deletes.
        :param now: Optional clock override (test seam).
        :param logger: Optional logger override; defaults
                       to the auth module logger.

        :returns: :class:`SweepReport`.
        :raises: ValueError on missing ``db_session``.
    """
    if db_session is None:
        err_lines = ["sweep_auth_caches requires a db_session."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    started_at = now if now is not None else _now_utc()
    with start_span(
        name=SPAN_AUTH_BACKGROUND_SWEEP,
        attributes={"flow": "background_sweep"},
    ) as span:
        oidc_removed = oidc_state.sweep_expired(
            db_session=db_session, now=started_at,
        )
        saml_removed = saml_replay_cache.sweep_expired(
            db_session=db_session, now=started_at,
        )
        span.set_attribute(
            key="oidc_state_rows_removed", value=oidc_removed,
        )
        span.set_attribute(
            key="saml_replay_rows_removed", value=saml_removed,
        )
    ended_at = _now_utc()

    report = SweepReport(
        oidc_state_rows_removed=oidc_removed,
        saml_replay_rows_removed=saml_removed,
        started_at=started_at,
        ended_at=ended_at,
    )
    log_events.emit_log_event(
        event_name=LOG_EVENT_AUTH_BACKGROUND_SWEPT,
        payload={
            "oidc_state_rows_removed": oidc_removed,
            "saml_replay_rows_removed": saml_removed,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration_seconds": report.duration_seconds(),
        },
        logger=logger,
    )
    rtnval = report
    return rtnval


def _now_utc() -> datetime:
    rtnval = datetime.now(tz=timezone.utc)
    return rtnval
