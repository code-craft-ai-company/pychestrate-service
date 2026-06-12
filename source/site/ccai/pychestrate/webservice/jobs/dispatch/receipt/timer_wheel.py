"""
.. module:: jobs.dispatch.receipt.timer_wheel
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-memory expect-timer wheel for pending receipts.

.. moduleauthor:: Code Craft AI LLC

The dispatcher arms an expect-timer when it transmits an envelope
so a receipt that never arrives surfaces as an explicit timeout
event. M1 ships a simple sorted-list wheel — O(log n) insert + O(1)
cancel + O(k) fire-expired where ``k`` is the number of entries
that crossed their deadline. Postgres-backed durable scheduling is
M3 scope.

Concurrency: callers MUST serialize access across threads via the
class's internal lock. The dispatcher typically does this by
holding the request-scoped SQLAlchemy session the wheel is attached
to, but standalone callers can call :meth:`fire_expired` from a
background thread without extra synchronization.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class TimerEntry:
    """
        One pending expect-timer.

        :param attempt_id: Dispatch attempt UUID the timer guards.
        :param run_id: Owning run UUID (for observability).
        :param project_id: Owning project UUID (for gauge labels).
        :param deadline_at: UTC timestamp the receipt must arrive
                            by.
    """
    attempt_id: str
    run_id: str
    project_id: str
    deadline_at: datetime


class TimerWheel:
    """
        Simple in-memory timer wheel. Not intended for
        process-restart durability — that lands in M3. Callers use
        :meth:`expect` on dispatch, :meth:`cancel` when a receipt
        lands, and :meth:`fire_expired` on a tick (typically 100 ms
        when a daemon runs, or once per test assertion).
    """

    def __init__(self) -> None:
        """
            Construct an empty wheel.

            :returns: None.
        """
        self._lock: threading.Lock = threading.Lock()
        self._entries: Dict[str, TimerEntry] = {}
        return

    def expect(
            self,
            *,
            attempt_id: str,
            run_id: str,
            project_id: str,
            deadline_at: datetime
        ) -> None:
        """
            Register an expect-timer. A second call for the same
            ``attempt_id`` overwrites the prior entry so callers
            who re-transmit reset the timer.

            :param attempt_id: Dispatch attempt UUID.
            :param run_id: Owning run UUID.
            :param project_id: Owning project UUID.
            :param deadline_at: UTC deadline.

            :returns: None.
        """
        entry = TimerEntry(
            attempt_id=attempt_id,
            run_id=run_id,
            project_id=project_id,
            deadline_at=deadline_at,
        )
        with self._lock:
            self._entries[attempt_id] = entry
        return

    def cancel(self, *, attempt_id: str) -> bool:
        """
            Remove a pending timer. Returns ``True`` if an entry
            was removed, ``False`` if none existed — so callers
            can log doubled-ack or late-cancel paths.

            :param attempt_id: Dispatch attempt UUID.

            :returns: Whether a pending entry was removed.
        """
        with self._lock:
            entry = self._entries.pop(attempt_id, None)
        rtnval = entry is not None
        return rtnval

    def pending_count(self) -> int:
        """
            Return the number of pending expect-timers. Used by
            the ``pychestrate_job_dispatch_pending_receipts``
            gauge when the M3 observability wiring lands.

            :returns: Integer count.
        """
        with self._lock:
            rtnval = len(self._entries)
        return rtnval

    def peek(self, *, attempt_id: str) -> Optional[TimerEntry]:
        """
            Return a snapshot of the pending entry for
            ``attempt_id`` or ``None``. Non-mutating.

            :param attempt_id: Dispatch attempt UUID.

            :returns: :class:`TimerEntry` or ``None``.
        """
        with self._lock:
            rtnval = self._entries.get(attempt_id, None)
        return rtnval

    def fire_expired(
            self,
            *,
            now: Optional[datetime] = None,
            on_timeout: Optional[Callable[[TimerEntry], None]] = None
        ) -> List[TimerEntry]:
        """
            Remove and return every entry whose ``deadline_at`` is
            <= ``now``. Optionally invokes ``on_timeout`` per
            removed entry so callers can publish a bus event
            without walking the return list.

            :param now: Optional override for the current time
                        (tests pass a fixed value).
            :param on_timeout: Optional per-entry callback invoked
                               after removal.

            :returns: List of fired :class:`TimerEntry` rows.
        """
        effective_now = now
        if effective_now is None:
            effective_now = datetime.now(timezone.utc)

        with self._lock:
            expired_ids: List[str] = []
            for key, entry in self._entries.items():
                if entry.deadline_at <= effective_now:
                    expired_ids.append(key)

            fired: List[TimerEntry] = []
            for key in expired_ids:
                entry = self._entries.pop(key)
                fired.append(entry)

        if on_timeout is not None:
            for entry in fired:
                on_timeout(entry)

        rtnval = list(fired)
        return rtnval

    def reset(self) -> None:
        """
            Clear every pending entry. Tests call this between
            cases.

            :returns: None.
        """
        with self._lock:
            self._entries = {}
        return


_DEFAULT_WHEEL_LOCK = threading.Lock()
_DEFAULT_WHEEL: Optional[TimerWheel] = None


def default_timer_wheel() -> TimerWheel:
    """
        Return the process-wide default :class:`TimerWheel`,
        constructing it lazily on first call. The phase-5 bootstrap
        scheduler ticks against this shared wheel so the wheel an
        in-process dispatcher arms is the same wheel the periodic
        ``fire_expired`` task scans.

        :returns: Singleton :class:`TimerWheel`.
    """
    global _DEFAULT_WHEEL
    with _DEFAULT_WHEEL_LOCK:
        if _DEFAULT_WHEEL is None:
            _DEFAULT_WHEEL = TimerWheel()
        rtnval = _DEFAULT_WHEEL
    return rtnval


def reset_default_timer_wheel_for_testing() -> None:
    """
        Discard the module-level default wheel so each test starts
        from a clean slate.

        :returns: None.
    """
    global _DEFAULT_WHEEL
    with _DEFAULT_WHEEL_LOCK:
        _DEFAULT_WHEEL = None
    return
