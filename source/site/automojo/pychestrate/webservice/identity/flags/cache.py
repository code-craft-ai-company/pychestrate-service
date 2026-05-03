"""
.. module:: identity.flags.cache
    :synopsis: TTL + last-good cache for feature-flag evaluation.

Two complementary caches:

* **TTL cache** — keyed on ``(flag_key, bucketing_key)``;
  configured staleness window (default 60 s) hides the
  evaluator from hot-path callers that hit the same flag
  thousands of times per minute.
* **Last-good cache** — keyed on ``flag_key``; preserves the
  most recent successful evaluation per flag so callers fall
  through to a stable answer when the backend returns a
  transient error (DB outage, retired-flag race, etc.).

:func:`evaluate_resilient` glues the two together: TTL hit
returns immediately; on miss it calls the supplied evaluator;
on caller-classified transient failure it returns the
last-good answer if any. Bus-driven invalidation runs from
:func:`wire_invalidation_subscribers` so the cache is
self-healing when an operator updates a flag.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional, Tuple


from automojo.pychestrate.webservice.identity.flags.events import (
    FlagEventTopics,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    subscribe,
)


DEFAULT_TTL = timedelta(seconds=60)


@dataclass(frozen=True)
class _CacheEntry:
    value: Any
    cached_at: datetime
    ttl: timedelta


_LOCK = threading.RLock()
_TTL_CACHE: Dict[Tuple[str, str], _CacheEntry] = {}
_LAST_GOOD: Dict[str, _CacheEntry] = {}
_STALE_SERVED: int = 0
_INSTALLED: bool = False


def reset_for_testing() -> None:
    """
        Drop all caches and unwire the subscribers. Tests use
        this to keep the module-level state from leaking.
    """
    global _STALE_SERVED, _INSTALLED
    with _LOCK:
        _TTL_CACHE.clear()
        _LAST_GOOD.clear()
        _STALE_SERVED = 0
        _INSTALLED = False
    return


def stale_served_count() -> int:
    """
        Return the running count of fallbacks served from the
        last-good cache. Surfaced to operator metrics as
        ``pychestrate_flags_cache_stale_served_total``.
    """
    with _LOCK:
        rtnval = _STALE_SERVED
    return rtnval


def get_cached(
        *,
        flag_key: str,
        bucketing_key: str,
        now: Optional[datetime] = None
    ) -> Optional[Any]:
    """
        Return the TTL-cached value for ``(flag_key,
        bucketing_key)`` if it has not expired. ``None`` on
        miss / expiry.
    """
    materialized_now = (
        now if now is not None else datetime.now(tz=timezone.utc)
    )
    cache_key = (flag_key, bucketing_key)
    with _LOCK:
        entry = _TTL_CACHE.get(cache_key)
    if entry is None:
        return None
    if _is_expired(entry=entry, now=materialized_now):
        with _LOCK:
            _TTL_CACHE.pop(cache_key, None)
        return None
    rtnval = entry.value
    return rtnval


def put_cached(
        *,
        flag_key: str,
        bucketing_key: str,
        value: Any,
        ttl: Optional[timedelta] = None,
        now: Optional[datetime] = None
    ) -> None:
    """
        Cache ``value`` for ``(flag_key, bucketing_key)`` and
        record it as the last-good entry for ``flag_key``.
    """
    materialized_now = (
        now if now is not None else datetime.now(tz=timezone.utc)
    )
    materialized_ttl = ttl if ttl is not None else DEFAULT_TTL
    entry = _CacheEntry(
        value=value, cached_at=materialized_now, ttl=materialized_ttl,
    )
    cache_key = (flag_key, bucketing_key)
    with _LOCK:
        _TTL_CACHE[cache_key] = entry
        _LAST_GOOD[flag_key] = entry
    return


def get_last_good(*, flag_key: str) -> Optional[Any]:
    """
        Return the most recent successful evaluation cached
        for ``flag_key``, or ``None`` when the flag has never
        been seen.
    """
    with _LOCK:
        entry = _LAST_GOOD.get(flag_key)
    if entry is None:
        return None
    rtnval = entry.value
    return rtnval


def invalidate_flag(*, flag_key: str) -> int:
    """
        Drop every TTL row for ``flag_key`` and the matching
        last-good entry. Used by the bus subscribers and by
        callers that mutate a flag through a bypass channel.

        :returns: Number of TTL entries removed.
    """
    removed = 0
    with _LOCK:
        keys_to_drop = [
            k for k in _TTL_CACHE.keys() if k[0] == flag_key
        ]
        for k in keys_to_drop:
            _TTL_CACHE.pop(k, None)
            removed = removed + 1
        _LAST_GOOD.pop(flag_key, None)
    return removed


def evaluate_resilient(
        *,
        flag_key: str,
        bucketing_key: str,
        evaluator: Callable[[], Any],
        default: Any,
        ttl: Optional[timedelta] = None,
        now: Optional[datetime] = None
    ) -> Any:
    """
        TTL-cached evaluation with last-good fallback.

        :param flag_key: Flag key being evaluated.
        :param bucketing_key: Caller's bucketing key — folded
                              into the TTL cache so every
                              context gets its own window.
        :param evaluator: Zero-arg callable that runs the real
                          evaluation. May raise.
        :param default: Returned when neither the TTL cache
                        nor the last-good cache has anything
                        usable on a backend failure.
        :param ttl: Optional TTL override.
        :param now: Optional clock override (test surface).

        :returns: The evaluated (or fallback) value.
    """
    cached = get_cached(
        flag_key=flag_key, bucketing_key=bucketing_key, now=now,
    )
    if cached is not None:
        return cached
    try:
        value = evaluator()
    except Exception:
        # Evaluator raised — try the last-good cache before
        # falling back to ``default`` so a transient DB
        # outage doesn't flip every consumer's flag.
        global _STALE_SERVED
        last_good = get_last_good(flag_key=flag_key)
        if last_good is not None:
            with _LOCK:
                _STALE_SERVED = _STALE_SERVED + 1
            return last_good
        return default
    put_cached(
        flag_key=flag_key,
        bucketing_key=bucketing_key,
        value=value,
        ttl=ttl,
        now=now,
    )
    return value


def wire_invalidation_subscribers() -> None:
    """
        Subscribe the cache-invalidation handlers to
        ``entity.flag.updated`` / ``entity.flag.retired`` /
        ``entity.flag.removed``. Idempotent — second call is
        a no-op.
    """
    global _INSTALLED
    with _LOCK:
        if _INSTALLED is True:
            return
        _INSTALLED = True
    subscribe(
        topic=FlagEventTopics.FLAG_UPDATED,
        subscriber=_on_flag_change,
    )
    subscribe(
        topic=FlagEventTopics.FLAG_RETIRED,
        subscriber=_on_flag_change,
    )
    subscribe(
        topic=FlagEventTopics.FLAG_REMOVED,
        subscriber=_on_flag_change,
    )
    return


def _on_flag_change(event: EntityEvent) -> None:
    payload = event.payload or {}
    flag_key = payload.get("flag_key")
    if flag_key is None:
        return
    invalidate_flag(flag_key=flag_key)
    return


def _is_expired(*, entry: _CacheEntry, now: datetime) -> bool:
    cached_at = entry.cached_at
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    deadline = cached_at + entry.ttl
    rtnval = now >= deadline
    return rtnval
