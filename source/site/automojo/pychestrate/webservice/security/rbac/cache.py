"""
.. module:: security.rbac.cache
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Process-local LRU cache for RBAC decisions.

.. moduleauthor:: Automation Mojo LLC

A single-process LRU indexed by ``(principal_id, permission_key,
scope_id)``. Hot-path consumers call :func:`cache_get` before hitting
the database; on cache miss the evaluator computes the decision and
stores the result via :func:`cache_put`.

The cache subscribes to bus topics that invalidate decisions:

- ``entity.role.assigned`` / ``entity.role.revoked`` — drop every
  entry for the affected ``principal_id``.
- ``entity.user.deactivated`` — drop every entry for the affected
  ``user_id``.
- ``entity.group.membership.changed`` — drop every entry for the
  affected user and group.

Cache bypass for tests is provided by :func:`reset_for_testing`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Tuple

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe


DEFAULT_CACHE_CAPACITY: int = 2048


CacheKey = Tuple[str, str, Optional[str]]


@dataclass(frozen=True)
class CachedDecision:
    """
        A cached decision tuple.

        :param allowed: Cached allow/deny outcome.
        :param reason: Short reason string matching the live decision.
    """
    allowed: bool
    reason: str


_CACHE_LOCK = threading.RLock()
_CACHE: "OrderedDict[CacheKey, CachedDecision]" = OrderedDict()
_CACHE_CAPACITY: int = DEFAULT_CACHE_CAPACITY
_WIRED: bool = False


def set_capacity(*, capacity: int) -> None:
    """
        Change the LRU capacity. Intended for operator tuning at startup
        or tests that want a tiny cache.

        :param capacity: Maximum entries to retain.

        :returns: None.
    """
    global _CACHE_CAPACITY
    with _CACHE_LOCK:
        _CACHE_CAPACITY = max(capacity, 1)
        while len(_CACHE) > _CACHE_CAPACITY:
            _CACHE.popitem(last=False)
    return


def cache_get(
        *,
        principal_id: str,
        permission_key: str,
        scope_id: Optional[str]
    ) -> Optional[CachedDecision]:
    """
        Look up a decision in the cache, updating recency on hit.

        :param principal_id: Principal UUID string.
        :param permission_key: Canonical key string.
        :param scope_id: Project UUID or None for system-scope evaluations.

        :returns: The cached :class:`CachedDecision`, or None on miss.
    """
    key: CacheKey = (principal_id, permission_key, scope_id)
    with _CACHE_LOCK:
        value = _CACHE.get(key, None)
        if value is None:
            return None
        _CACHE.move_to_end(key, last=True)
    return value


def cache_put(
        *,
        principal_id: str,
        permission_key: str,
        scope_id: Optional[str],
        decision: CachedDecision
    ) -> None:
    """
        Insert or update a decision, evicting the least-recently-used
        entry when the capacity is exceeded.

        :param principal_id: Principal UUID string.
        :param permission_key: Canonical key string.
        :param scope_id: Project UUID or None.
        :param decision: The decision tuple to store.

        :returns: None.
    """
    key: CacheKey = (principal_id, permission_key, scope_id)
    with _CACHE_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key, last=True)
            _CACHE[key] = decision
            return
        _CACHE[key] = decision
        while len(_CACHE) > _CACHE_CAPACITY:
            _CACHE.popitem(last=False)
    return


def invalidate_principal(*, principal_id: str) -> None:
    """
        Drop every cached decision for a principal.

        :param principal_id: Principal UUID string.

        :returns: None.
    """
    with _CACHE_LOCK:
        for key in list(_CACHE.keys()):
            if key[0] == principal_id:
                _CACHE.pop(key, None)
    return


def invalidate_all() -> None:
    """
        Drop every cached decision.

        :returns: None.
    """
    with _CACHE_LOCK:
        _CACHE.clear()
    return


def reset_for_testing() -> None:
    """
        Reset the cache and the wiring guard. Test-only helper.

        :returns: None.
    """
    global _WIRED
    with _CACHE_LOCK:
        _CACHE.clear()
        _WIRED = False
    return


def _on_role_assigned_or_revoked(event: EntityEvent) -> None:
    payload = event.payload
    principal_id = payload.get("principal_id", None)
    if principal_id is not None:
        invalidate_principal(principal_id=str(principal_id))
    return


def _on_user_deactivated(event: EntityEvent) -> None:
    payload = event.payload
    user_id = payload.get("user_id", None)
    if user_id is not None:
        invalidate_principal(principal_id=str(user_id))
    return


def _on_group_membership_changed(event: EntityEvent) -> None:
    payload = event.payload
    user_id = payload.get("user_id", None)
    group_id = payload.get("group_id", None)
    if user_id is not None:
        invalidate_principal(principal_id=str(user_id))
    if group_id is not None:
        invalidate_principal(principal_id=str(group_id))
    return


def wire_cache_invalidation() -> None:
    """
        Subscribe the invalidation handlers to the relevant bus topics.
        Idempotent — safe to call multiple times.

        :returns: None.
    """
    global _WIRED
    with _CACHE_LOCK:
        if _WIRED is True:
            return
        _WIRED = True

    subscribe(topic="entity.role.assigned", subscriber=_on_role_assigned_or_revoked)
    subscribe(topic="entity.role.revoked", subscriber=_on_role_assigned_or_revoked)
    subscribe(topic="entity.user.deactivated", subscriber=_on_user_deactivated)
    subscribe(topic="entity.group.membership.changed", subscriber=_on_group_membership_changed)

    return
