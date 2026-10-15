"""
.. module:: variables.cache
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Process-local resolution cache for 2-global-variables M3.

.. moduleauthor:: Code Craft AI LLC

A tiny thread-safe LRU keyed by
``(name, project_id, pipeline_id, job_id, dereference_secrets)``. The
cache is invalidated whenever :func:`variable_service.set_variable` or
``unset_variable`` is called, so the process that made the change sees it at
once.

The cache is *per process* and the service runs several workers (four under the
gunicorn scripts), so a change made in one worker could not invalidate the entries
of the others, which kept the old value until they were evicted or the service
restarted (audit ADM-08: found when the Admin Variables pages began to write the same
store). Every entry therefore expires after :data:`DEFAULT_TTL_SECONDS` (settable with
``PYCHESTRATE_VARIABLE_CACHE_TTL_SECONDS``; ``0`` turns the cache off): a change
reaches every worker within that time.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading
import time

from collections import OrderedDict
from typing import Any, Optional, Tuple


CacheKey = Tuple[str, Optional[str], Optional[str], Optional[str], bool]


_CACHE_SIZE: int = 1024

#: How long a resolved value is kept, in seconds: the longest another worker can serve the value from before a change.
DEFAULT_TTL_SECONDS: float = 5.0

#: The environment variable that overrides it (``0`` turns the cache off).
TTL_ENV_VAR: str = "PYCHESTRATE_VARIABLE_CACHE_TTL_SECONDS"

_LOCK = threading.RLock()
_ORDER: "OrderedDict[CacheKey, Tuple[Any, float]]" = OrderedDict()

_SENTINEL = object()


def ttl_seconds() -> float:
    """
        The lifetime of a cached value: ``PYCHESTRATE_VARIABLE_CACHE_TTL_SECONDS`` when it is a non-negative number, else the default.
    """
    raw = os.environ.get(TTL_ENV_VAR, None)
    if raw is None or len(raw.strip()) == 0:
        return DEFAULT_TTL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TTL_SECONDS
    if value < 0:
        return DEFAULT_TTL_SECONDS
    return value


def get(*, key: CacheKey) -> Any:
    """
        Return the cached value for ``key`` or the sentinel meaning
        "no entry" (also for an entry that has expired). Promotes the entry on hit.
    """
    with _LOCK:
        if key not in _ORDER:
            return _SENTINEL
        value, expires_at = _ORDER.pop(key)
        if time.monotonic() >= expires_at:
            return _SENTINEL
        _ORDER[key] = (value, expires_at)
        rtnval = value
        return rtnval


def put(*, key: CacheKey, value: Any) -> None:
    """
        Insert or update an entry, evicting the least-recently-used when
        the cache is full.
    """
    with _LOCK:
        if key in _ORDER:
            _ORDER.pop(key)
        _ORDER[key] = (value, time.monotonic() + ttl_seconds())
        while len(_ORDER) > _CACHE_SIZE:
            _ORDER.popitem(last=False)
    return


def invalidate_for_name(*, name: str) -> None:
    """
        Remove every entry whose variable name matches. Called on every
        write that might change effective resolution.
    """
    with _LOCK:
        stale = [k for k in _ORDER.keys() if k[0] == name]
        for k in stale:
            _ORDER.pop(k, None)
    return


def sentinel() -> Any:
    """
        Return the "no entry" sentinel used by :func:`get` callers.
    """
    return _SENTINEL


def reset_for_testing() -> None:
    """
        Clear the cache. Test-only.
    """
    with _LOCK:
        _ORDER.clear()
    return
