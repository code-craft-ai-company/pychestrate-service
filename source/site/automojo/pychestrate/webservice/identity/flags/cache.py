"""
.. module:: identity.flags.cache
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Process-local staleness-window cache for evaluated flag values.

.. moduleauthor:: Automation Mojo LLC

The hot path of :func:`flag_evaluator.evaluate_flag` reads from this cache
keyed on ``(flag_key, flag_version, bucketing_key)``. Entries expire after
the configured staleness window (default 60 seconds). Subscribers attached
in :func:`subscribe_invalidation_to_bus` invalidate the per-flag namespace
when ``entity.flag.updated`` / ``entity.flag.retired`` /
``entity.flag.removed`` events fire, so callers do not have to thread
invalidation through their own write paths.

Thread-safe via a single ``RLock``; the cache map is small enough (one
entry per ``(flag_key, version, bucketing_key)`` tuple in active use) that
linear sweeps on flag-scoped invalidation are acceptable.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading
import time

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from automojo.pychestrate.webservice.identity.flags.events import FlagEventTopics
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe


DEFAULT_STALENESS_WINDOW_SECONDS: int = 60


CacheKey = Tuple[str, int, str]


@dataclass(frozen=True)
class _CacheEntry:
    """
        A cached evaluation result.

        :param value: The evaluated value (any encoded type).
        :param recorded_at: Monotonic seconds when the entry was stored.
    """
    value: Any
    recorded_at: float


_CACHE_LOCK = threading.RLock()
_CACHE: Dict[CacheKey, _CacheEntry] = {}
_LAST_GOOD: Dict[CacheKey, _CacheEntry] = {}
_STALENESS_WINDOW_SECONDS: float = float(DEFAULT_STALENESS_WINDOW_SECONDS)
_CLOCK: Callable[[], float] = time.monotonic
_INVALIDATION_WIRED: bool = False


def configure(
        *,
        staleness_window_seconds: float,
        clock: Optional[Callable[[], float]]
    ) -> None:
    """
        Configure the cache TTL and clock source. Tests use this to stub
        the clock; production callers set ``staleness_window_seconds``
        from configuration.

        :param staleness_window_seconds: Positive TTL in seconds.
        :param clock: Optional callable returning monotonic seconds.

        :returns: None.
    """
    global _STALENESS_WINDOW_SECONDS
    global _CLOCK

    if staleness_window_seconds <= 0:
        return

    with _CACHE_LOCK:
        _STALENESS_WINDOW_SECONDS = float(staleness_window_seconds)
        if clock is not None:
            _CLOCK = clock

    return


def get_staleness_window_seconds() -> float:
    """
        Return the configured staleness window in seconds.

        :returns: Float seconds.
    """
    with _CACHE_LOCK:
        rtnval = _STALENESS_WINDOW_SECONDS
    return rtnval


def lookup(*, flag_key: str, flag_version: int, bucketing_key: str) -> Optional[Any]:
    """
        Return a cached value for the given key tuple if it is still fresh.

        :param flag_key: Flag identifier.
        :param flag_version: Flag's ``current_version`` at evaluation.
        :param bucketing_key: Caller-supplied stable key.

        :returns: Cached value or None on miss / staleness.
    """
    cache_key: CacheKey = (flag_key, flag_version, bucketing_key)
    with _CACHE_LOCK:
        entry = _CACHE.get(cache_key, None)
        if entry is None:
            rtnval: Optional[Any] = None
            return rtnval
        elapsed = _CLOCK() - entry.recorded_at
        if elapsed > _STALENESS_WINDOW_SECONDS:
            del _CACHE[cache_key]
            rtnval = None
            return rtnval
        rtnval = entry.value
        return rtnval


def store(*, flag_key: str, flag_version: int, bucketing_key: str, value: Any) -> None:
    """
        Store an evaluation result. Also updates the last-good map so a
        backend outage can fall back during the staleness window.

        :param flag_key: Flag identifier.
        :param flag_version: Flag's ``current_version`` at evaluation.
        :param bucketing_key: Caller-supplied stable key.
        :param value: Value to cache.

        :returns: None.
    """
    cache_key: CacheKey = (flag_key, flag_version, bucketing_key)
    entry = _CacheEntry(value=value, recorded_at=_CLOCK())
    with _CACHE_LOCK:
        _CACHE[cache_key] = entry
        _LAST_GOOD[cache_key] = entry
    return


def lookup_last_good(
        *,
        flag_key: str,
        flag_version: int,
        bucketing_key: str
    ) -> Optional[Any]:
    """
        Return the last-good cached value if its age is within the
        staleness window. Used by the evaluator to absorb transient
        backend errors.

        :param flag_key: Flag identifier.
        :param flag_version: Flag's ``current_version`` at evaluation.
        :param bucketing_key: Caller-supplied stable key.

        :returns: Cached value or None.
    """
    cache_key: CacheKey = (flag_key, flag_version, bucketing_key)
    with _CACHE_LOCK:
        entry = _LAST_GOOD.get(cache_key, None)
        if entry is None:
            rtnval: Optional[Any] = None
            return rtnval
        elapsed = _CLOCK() - entry.recorded_at
        if elapsed > _STALENESS_WINDOW_SECONDS:
            rtnval = None
            return rtnval
        rtnval = entry.value
        return rtnval


def invalidate_flag(*, flag_key: str) -> int:
    """
        Drop every cache entry whose ``flag_key`` matches.

        :param flag_key: The flag whose entries should be discarded.

        :returns: Number of entries removed from the fresh cache.
    """
    removed_count = 0
    with _CACHE_LOCK:
        for key in list(_CACHE.keys()):
            entry_flag_key, _flag_version, _bucketing_key = key
            if entry_flag_key == flag_key:
                del _CACHE[key]
                removed_count += 1
        for key in list(_LAST_GOOD.keys()):
            entry_flag_key, _flag_version, _bucketing_key = key
            if entry_flag_key == flag_key:
                del _LAST_GOOD[key]
    return removed_count


def reset_for_testing() -> None:
    """
        Clear the cache and reset configuration to defaults.

        :returns: None.
    """
    global _STALENESS_WINDOW_SECONDS
    global _CLOCK
    global _INVALIDATION_WIRED
    with _CACHE_LOCK:
        _CACHE.clear()
        _LAST_GOOD.clear()
        _STALENESS_WINDOW_SECONDS = float(DEFAULT_STALENESS_WINDOW_SECONDS)
        _CLOCK = time.monotonic
        _INVALIDATION_WIRED = False
    return


def _on_flag_event(event: EntityEvent) -> None:
    """
        Bus subscriber that invalidates per-flag entries on lifecycle
        events.

        :param event: Published :class:`EntityEvent`.

        :returns: None.
    """
    payload = event.payload or {}
    flag_key = payload.get("flag_key", None)
    if flag_key is None:
        return
    invalidate_flag(flag_key=str(flag_key))
    return


def subscribe_invalidation_to_bus() -> None:
    """
        Wire the cache invalidator to the in-process event bus. Idempotent
        within a single bus lifetime — subsequent calls without an
        intervening :func:`reset_for_testing` (or bus reset) are no-ops so
        bootstrap can run more than once without duplicating subscriptions.

        :returns: None.
    """
    global _INVALIDATION_WIRED
    with _CACHE_LOCK:
        if _INVALIDATION_WIRED is True:
            return
        _INVALIDATION_WIRED = True

    subscribe(topic=FlagEventTopics.FLAG_UPDATED, subscriber=_on_flag_event)
    subscribe(topic=FlagEventTopics.FLAG_RETIRED, subscriber=_on_flag_event)
    subscribe(topic=FlagEventTopics.FLAG_REMOVED, subscriber=_on_flag_event)
    return
