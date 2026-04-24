"""
.. module:: variables.cache
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Process-local resolution cache for 2-global-variables M3.

.. moduleauthor:: Automation Mojo LLC

A tiny thread-safe LRU keyed by
``(name, project_id, pipeline_id, job_id, dereference_secrets)``. The
cache is invalidated whenever :func:`variable_service.set_variable` or
``unset_variable`` publishes a bus event, so callers never see stale
values across mutations on the same node.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from collections import OrderedDict
from typing import Any, Optional, Tuple


CacheKey = Tuple[str, Optional[str], Optional[str], Optional[str], bool]


_CACHE_SIZE: int = 1024
_LOCK = threading.RLock()
_ORDER: "OrderedDict[CacheKey, Any]" = OrderedDict()

_SENTINEL = object()


def get(*, key: CacheKey) -> Any:
    """
        Return the cached value for ``key`` or the sentinel meaning
        "no entry". Promotes the entry on hit.
    """
    with _LOCK:
        if key not in _ORDER:
            return _SENTINEL
        value = _ORDER.pop(key)
        _ORDER[key] = value
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
        _ORDER[key] = value
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
