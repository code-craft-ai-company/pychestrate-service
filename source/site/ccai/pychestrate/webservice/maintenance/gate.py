"""
.. module:: maintenance.gate
    :synopsis: MaintenanceGate — process-singleton in-memory gate.

The gate caches per-scope state so the hot path (every
incoming request, every dispatch) is a dict lookup rather
than a database round-trip.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import os
import threading

from datetime import datetime
from typing import Dict, Iterable, List, Optional


class MaintenanceMode(str, enum.Enum):
    """
        Possible scope modes. ``active`` lets every operation
        through; ``read_only`` blocks mutations; ``draining``
        blocks mutations and rejects new long-running work.
    """
    ACTIVE = "active"
    READ_ONLY = "read_only"
    DRAINING = "draining"


PRECEDENCE_ORDER: Dict[MaintenanceMode, int] = {
    MaintenanceMode.ACTIVE: 0,
    MaintenanceMode.READ_ONLY: 1,
    MaintenanceMode.DRAINING: 2,
}


def mode_precedence(*, modes: Iterable[MaintenanceMode]) -> MaintenanceMode:
    """
        Combine a list of scope modes into the most-restrictive
        effective mode. Ordering: ``active < read_only <
        draining``.

        :raises: ValueError on empty list.
    """
    materialized = list(modes)
    if len(materialized) == 0:
        err_lines = ["mode_precedence requires at least one mode."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    rtnval = materialized[0]
    best_score = PRECEDENCE_ORDER[rtnval]
    for mode in materialized[1:]:
        score = PRECEDENCE_ORDER[mode]
        if score > best_score:
            best_score = score
            rtnval = mode
    return rtnval


class MaintenanceGate:
    """
        Process-singleton in-memory cache of scope modes. The
        service-side helpers seed the cache via
        :meth:`set_mode_in_memory` after each persistence-layer
        write.
    """

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._cache: Dict[str, MaintenanceMode] = {}
        return

    def set_mode_in_memory(
            self,
            *,
            scope: str,
            mode: MaintenanceMode
        ) -> None:
        with self._lock:
            if mode == MaintenanceMode.ACTIVE:
                self._cache.pop(scope, None)
            else:
                self._cache[scope] = mode
        return

    def get_mode_in_memory(self, *, scope: str) -> MaintenanceMode:
        with self._lock:
            rtnval = self._cache.get(scope, MaintenanceMode.ACTIVE)
        return rtnval

    def get_effective_mode(
            self,
            *,
            scopes: Iterable[str]
        ) -> MaintenanceMode:
        """
            Return the most-restrictive mode across every
            supplied scope. ``"service"`` is implicit — callers
            do NOT need to add it; the gate always folds the
            global service scope into the result.
        """
        materialized: List[MaintenanceMode] = []
        with self._lock:
            materialized.append(
                self._cache.get("service", MaintenanceMode.ACTIVE),
            )
            for scope in scopes:
                if scope == "service":
                    continue
                materialized.append(
                    self._cache.get(scope, MaintenanceMode.ACTIVE),
                )
        if len(materialized) == 0:
            return MaintenanceMode.ACTIVE
        rtnval = mode_precedence(modes=materialized)
        return rtnval

    def warm(
            self,
            *,
            initial_modes: Iterable[tuple]
        ) -> None:
        """
            Seed the in-memory cache from persistent state. The
            caller passes ``[(scope, mode), ...]`` tuples;
            typically the service-side reload pulls these from
            the ledger.
        """
        with self._lock:
            self._cache.clear()
            for scope, mode in initial_modes:
                if mode == MaintenanceMode.ACTIVE:
                    continue
                self._cache[scope] = mode
        return

    def snapshot(self) -> Dict[str, MaintenanceMode]:
        """
            Frozen view of the current cache (only non-active
            entries).
        """
        with self._lock:
            rtnval = dict(self._cache)
        return rtnval

    def reset(self) -> None:
        with self._lock:
            self._cache.clear()
        return


_GATE_LOCK = threading.RLock()
_GATE_INSTANCE: Optional[MaintenanceGate] = None


def get_gate() -> MaintenanceGate:
    """
        Process-singleton accessor.
    """
    global _GATE_INSTANCE
    with _GATE_LOCK:
        if _GATE_INSTANCE is None:
            _GATE_INSTANCE = MaintenanceGate()
        rtnval = _GATE_INSTANCE
    return rtnval


def reset_for_testing() -> None:
    """
        Drop the singleton + clear in-memory state.
    """
    global _GATE_INSTANCE
    with _GATE_LOCK:
        if _GATE_INSTANCE is not None:
            _GATE_INSTANCE.reset()
        _GATE_INSTANCE = None
    return
