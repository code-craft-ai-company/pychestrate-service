"""
.. module:: system_health.registry
    :synopsis: HealthRegistry + ProbeRecord / ProbeResult / HealthSnapshot shapes.

The registry is the authoritative directory of registered
probes. The scheduler consults it on every cycle and writes
the latest :class:`ProbeResult` back into the matching
:class:`ProbeRecord`. All endpoint serialization reads from
:meth:`HealthRegistry.snapshot` so the request path never
calls a probe synchronously.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import os
import threading

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from automojo.pychestrate.webservice.system_health.exceptions import (
    DuplicateProbeError,
    ProbeNotFoundError,
)


LAST_ERROR_MAX_CHARS: int = 512


class ProbeKind(str, enum.Enum):
    """
        Probe classification.

        * LIVENESS — process-up signal, surfaces on
          ``/__health/live``.
        * READINESS — accept-traffic signal, surfaces on
          ``/__health/ready``.
        * INFORMATIONAL — visible only on
          ``/__health/detailed``; never blocks readiness.
    """
    LIVENESS = "liveness"
    READINESS = "readiness"
    INFORMATIONAL = "informational"


class ProbeStatus(str, enum.Enum):
    """
        Per-result probe verdict.
    """
    OK = "ok"
    FAIL = "fail"
    UNKNOWN = "unknown"


class OverallStatus(str, enum.Enum):
    """
        Aggregate health verdict.

        * OK — every readiness probe is ``ok``.
        * DEGRADED — at least one informational or liveness
          probe is failing but readiness is intact.
        * FAILING — at least one readiness probe is failing.
    """
    OK = "ok"
    DEGRADED = "degraded"
    FAILING = "failing"


@dataclass(frozen=True)
class ProbeResult:
    """
        Result of one probe invocation.

        :param status: Verdict.
        :param duration_ms: Wall-clock time the probe took.
        :param observed_at: Timestamp the result was recorded.
        :param last_error: Stable token + detail when failing;
                           truncated at :data:`LAST_ERROR_MAX_CHARS`.
        :param details: Probe-supplied informational mapping.
    """
    status: ProbeStatus
    duration_ms: float
    observed_at: datetime
    last_error: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ProbeRecord:
    """
        Mutable per-probe record. The scheduler writes
        ``last_result`` / ``last_started_at`` / ``in_flight``
        on every run; everything else is operator-supplied at
        registration.
    """
    name: str
    kind: ProbeKind
    probe: Callable[[], ProbeResult]
    interval_seconds: float
    timeout_seconds: float
    last_result: Optional[ProbeResult] = None
    last_started_at: Optional[datetime] = None
    in_flight: bool = False


@dataclass(frozen=True)
class HealthSnapshot:
    """
        Immutable snapshot suitable for endpoint
        serialization.

        :param overall: Aggregate verdict.
        :param probes: Tuple of ``(name, kind, last_result)``
                       triples in registration order.
        :param failing_readiness_probes: Names of readiness
                                         probes whose last
                                         result is not OK;
                                         drives the
                                         ``/__health/ready``
                                         response body.
    """
    overall: OverallStatus
    probes: Tuple[Tuple[str, ProbeKind, Optional[ProbeResult]], ...]
    failing_readiness_probes: Tuple[str, ...]


class HealthRegistry:
    """
        Authoritative directory of registered probes.
    """

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._probes: Dict[str, ProbeRecord] = {}
        self._registration_order: List[str] = []
        return

    def register_probe(
            self,
            *,
            name: str,
            kind: ProbeKind,
            probe: Callable[[], ProbeResult],
            interval_seconds: float,
            timeout_seconds: float
        ) -> ProbeRecord:
        """
            Register a probe.

            :raises: DuplicateProbeError on duplicate name;
                     ValueError on empty name / non-positive
                     interval / non-positive timeout.
        """
        if name is None or len(name) == 0:
            err_lines = ["register_probe requires a non-empty name."]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        if interval_seconds <= 0.0:
            err_lines = [
                "register_probe requires a positive interval_seconds.",
            ]
            err_lines.append("VALUE: {}".format(interval_seconds))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        if timeout_seconds <= 0.0:
            err_lines = [
                "register_probe requires a positive timeout_seconds.",
            ]
            err_lines.append("VALUE: {}".format(timeout_seconds))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        with self._lock:
            if name in self._probes:
                err_lines = ["Probe with that name is already registered."]
                err_lines.append("NAME: {}".format(name))
                err_msg = os.linesep.join(err_lines)
                raise DuplicateProbeError(err_msg) from None
            record = ProbeRecord(
                name=name,
                kind=kind,
                probe=probe,
                interval_seconds=interval_seconds,
                timeout_seconds=timeout_seconds,
            )
            self._probes[name] = record
            self._registration_order.append(name)
        return record

    def unregister_probe(self, *, name: str) -> bool:
        """
            Drop a probe. Idempotent — returns ``True`` when a
            row was removed, ``False`` when the name was not
            registered.
        """
        with self._lock:
            if name not in self._probes:
                return False
            del self._probes[name]
            self._registration_order = [
                n for n in self._registration_order if n != name
            ]
        return True

    def get_probe(self, *, name: str) -> ProbeRecord:
        """
            Return the registered :class:`ProbeRecord`.

            :raises: ProbeNotFoundError on miss.
        """
        with self._lock:
            record = self._probes.get(name)
            if record is None:
                err_lines = ["Probe not found."]
                err_lines.append("NAME: {}".format(name))
                err_msg = os.linesep.join(err_lines)
                raise ProbeNotFoundError(err_msg) from None
            return record

    def list_probes(self) -> Tuple[ProbeRecord, ...]:
        """
            Return the registered probes in registration order.
        """
        with self._lock:
            rtnval = tuple(
                self._probes[name] for name in self._registration_order
            )
            return rtnval

    def record_result(
            self,
            *,
            name: str,
            result: ProbeResult,
            started_at: datetime
        ) -> None:
        """
            Stamp ``result`` + ``started_at`` on the matching
            :class:`ProbeRecord`. Used by the scheduler.
        """
        with self._lock:
            record = self._probes.get(name)
            if record is None:
                return
            record.last_result = result
            record.last_started_at = started_at
            record.in_flight = False
        return

    def mark_in_flight(
            self, *, name: str, started_at: datetime
        ) -> None:
        """
            Mark the probe as currently running. The scheduler
            sets this immediately before invoking the probe so
            an externally-observable in_flight flag flips
            during the run.
        """
        with self._lock:
            record = self._probes.get(name)
            if record is None:
                return
            record.in_flight = True
            record.last_started_at = started_at
        return

    def snapshot(self) -> HealthSnapshot:
        """
            Build an immutable snapshot for endpoint
            serialization.
        """
        with self._lock:
            ordered_records = [
                self._probes[name] for name in self._registration_order
            ]
        probes_tuple: List[Tuple[str, ProbeKind, Optional[ProbeResult]]] = []
        failing_readiness: List[str] = []
        any_readiness_fail = False
        any_other_fail = False
        any_readiness = False
        for record in ordered_records:
            probes_tuple.append((record.name, record.kind, record.last_result))
            if record.kind == ProbeKind.READINESS:
                any_readiness = True
                if record.last_result is None:
                    any_readiness_fail = True
                    failing_readiness.append(record.name)
                elif record.last_result.status != ProbeStatus.OK:
                    any_readiness_fail = True
                    failing_readiness.append(record.name)
                continue
            if record.last_result is not None and record.last_result.status != ProbeStatus.OK:
                any_other_fail = True

        if any_readiness_fail is True or any_readiness is False and any_other_fail is False and len(ordered_records) == 0:
            # Edge case: no probes registered at all → start with FAILING so
            # readiness flips to ready only after the first probe lands.
            overall = (
                OverallStatus.FAILING if any_readiness_fail is True
                else OverallStatus.OK
            )
        elif any_readiness_fail is True:
            overall = OverallStatus.FAILING
        elif any_other_fail is True:
            overall = OverallStatus.DEGRADED
        else:
            overall = OverallStatus.OK

        rtnval = HealthSnapshot(
            overall=overall,
            probes=tuple(probes_tuple),
            failing_readiness_probes=tuple(failing_readiness),
        )
        return rtnval


def truncate_last_error(*, message: Optional[str]) -> Optional[str]:
    """
        Apply the :data:`LAST_ERROR_MAX_CHARS` cap.
    """
    if message is None:
        return None
    if len(message) <= LAST_ERROR_MAX_CHARS:
        return message
    rtnval = message[:LAST_ERROR_MAX_CHARS]
    return rtnval
