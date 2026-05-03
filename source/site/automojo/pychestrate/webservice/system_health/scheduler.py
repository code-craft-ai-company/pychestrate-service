"""
.. module:: system_health.scheduler
    :synopsis: Probe scheduler with timeout enforcement.

The scheduler runs every registered probe at its declared
cadence and writes the result back to the registry. Probes
run inside a small thread pool so a slow probe cannot block
the others; per-probe ``timeout_seconds`` is enforced via
``future.result(timeout=...)``.

M1 ships :func:`run_probe_now` for synchronous one-shot runs
(used by the test surface and the bootstrap warm-up) plus
:class:`HealthScheduler` for the long-running cadence loop.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import threading
import time

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.system_health.exceptions import (
    ProbeNotFoundError,
)
from automojo.pychestrate.webservice.system_health.registry import (
    HealthRegistry,
    ProbeKind,
    ProbeResult,
    ProbeStatus,
    truncate_last_error,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthConfig:
    """
        Operator-supplied scheduler config.

        :param probe_worker_count: Thread-pool size for probe
                                   invocations.
        :param detailed_permission_name: Name of the RBAC
                                         permission that gates
                                         ``/__health/detailed``.
                                         M1 stores it but does
                                         not enforce — that
                                         lands in M2 alongside
                                         the REST surface.
    """
    probe_worker_count: int = 4
    detailed_permission_name: str = "pychestrate.system_health.detailed"


def run_probe_now(
        *,
        registry: HealthRegistry,
        name: str
    ) -> ProbeResult:
    """
        Synchronously invoke a probe by name, write the result
        back into the registry, and return the result.

        :raises: ProbeNotFoundError on miss.
    """
    record = registry.get_probe(name=name)
    started_at = datetime.now(tz=timezone.utc)
    registry.mark_in_flight(name=name, started_at=started_at)
    monotonic_start = time.monotonic()
    try:
        result = record.probe()
    except Exception as probe_err:
        elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
        result = ProbeResult(
            status=ProbeStatus.FAIL,
            duration_ms=elapsed_ms,
            observed_at=datetime.now(tz=timezone.utc),
            last_error=truncate_last_error(
                message="{}: {}".format(
                    type(probe_err).__name__, probe_err,
                ),
            ),
        )
    if not isinstance(result, ProbeResult):
        elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
        result = ProbeResult(
            status=ProbeStatus.FAIL,
            duration_ms=elapsed_ms,
            observed_at=datetime.now(tz=timezone.utc),
            last_error=truncate_last_error(
                message="probe returned non-ProbeResult value",
            ),
        )
    registry.record_result(
        name=name, result=result, started_at=started_at,
    )
    return result


class HealthScheduler:
    """
        Background probe scheduler. Tests typically use
        :func:`run_probe_now` for synchronous runs; the long-
        running cadence loop is exercised via :meth:`tick`.
    """

    def __init__(
            self,
            *,
            registry: HealthRegistry,
            config: HealthConfig
        ) -> None:
        self._registry: HealthRegistry = registry
        self._config: HealthConfig = config
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running: bool = False
        self._lock: threading.RLock = threading.RLock()
        return

    def start(self) -> None:
        """
            Spin up the probe-worker thread pool.

            :raises: SemanticError if already running.
        """
        with self._lock:
            if self._running is True:
                err_lines = ["HealthScheduler is already running."]
                err_msg = os.linesep.join(err_lines)
                raise SemanticError(err_msg) from None
            self._executor = ThreadPoolExecutor(
                max_workers=self._config.probe_worker_count,
                thread_name_prefix="health-probe",
            )
            self._running = True
        return

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        """
            Stop the executor and wait for in-flight probes.
            Idempotent.
        """
        with self._lock:
            executor = self._executor
            self._executor = None
            self._running = False
        if executor is not None:
            executor.shutdown(wait=True)
        return

    def is_running(self) -> bool:
        """
            Return whether the scheduler is currently running.
        """
        with self._lock:
            rtnval = self._running
            return rtnval

    def tick(self) -> int:
        """
            Run every registered probe once, blocking until
            each one returns or its timeout fires. Used by the
            test surface and by the bootstrap warm-up; the
            production cadence loop wraps this on a timer.

            :returns: Number of probes attempted.
        """
        executor = self._require_executor()
        records = self._registry.list_probes()
        if records is None or len(records) == 0:
            return 0
        attempted = 0
        for record in records:
            self._run_one(executor=executor, record=record)
            attempted = attempted + 1
        return attempted

    def _run_one(self, *, executor: ThreadPoolExecutor, record) -> None:
        started_at = datetime.now(tz=timezone.utc)
        self._registry.mark_in_flight(
            name=record.name, started_at=started_at,
        )
        future: Future = executor.submit(record.probe)
        monotonic_start = time.monotonic()
        try:
            outcome = future.result(timeout=record.timeout_seconds)
        except TimeoutError:
            elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
            outcome = ProbeResult(
                status=ProbeStatus.FAIL,
                duration_ms=elapsed_ms,
                observed_at=datetime.now(tz=timezone.utc),
                last_error=truncate_last_error(message="probe timeout"),
            )
            future.cancel()
        except Exception as probe_err:
            elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
            outcome = ProbeResult(
                status=ProbeStatus.FAIL,
                duration_ms=elapsed_ms,
                observed_at=datetime.now(tz=timezone.utc),
                last_error=truncate_last_error(
                    message="{}: {}".format(
                        type(probe_err).__name__, probe_err,
                    ),
                ),
            )
        if not isinstance(outcome, ProbeResult):
            elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
            outcome = ProbeResult(
                status=ProbeStatus.FAIL,
                duration_ms=elapsed_ms,
                observed_at=datetime.now(tz=timezone.utc),
                last_error=truncate_last_error(
                    message="probe returned non-ProbeResult value",
                ),
            )
        self._registry.record_result(
            name=record.name,
            result=outcome,
            started_at=started_at,
        )
        return

    def _require_executor(self) -> ThreadPoolExecutor:
        with self._lock:
            executor = self._executor
        if executor is None:
            err_lines = ["HealthScheduler.tick called before start()."]
            err_msg = os.linesep.join(err_lines)
            raise SemanticError(err_msg) from None
        return executor
