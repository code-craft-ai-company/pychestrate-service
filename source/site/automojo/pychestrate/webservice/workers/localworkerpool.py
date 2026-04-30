"""
.. module:: pychestrate.webservice.workers.localworkerpool
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-process pool of ``local-process`` workers.

.. moduleauthor:: Automation Mojo LLC

The :class:`LocalWorkerPool` is the simplest possible
:class:`Worker` implementation: a small set of background threads
running inside the pychestrate-service process itself. Each thread:

1. self-registers as a :class:`WorkerKind.LOCAL_PROCESS` row on
   start (or reuses an existing row with the same name when one
   already exists from a prior run);
2. polls :func:`workers.jobservice.claim_next_job` for the oldest
   PENDING job whose selectors match;
3. when a ``run-command`` job is claimed, runs the command via
   :func:`subprocess.run` with the timeout from the job's payload;
4. reports ``result_code``, ``stdout``, ``stderr``, and (on
   subprocess failure) ``error_text`` via
   :func:`workers.jobservice.report_result`;
5. heartbeats periodically so the registry's liveness view is
   accurate.

The pool exists primarily so the service can run flow steps that
call :class:`RemoteCommand` against a ``local-process`` target
without operators having to stand up a separate worker host. On
hardware-test setups the pool is typically left small (1-2
threads) because the heavy work is dispatched to the Raspberry
Pis via remote-machine workers.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import socket
import subprocess
import threading
import time

from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.workers import (
    jobservice,
    service as worker_service,
)
from automojo.pychestrate.webservice.workers.exceptions import (
    WorkerAlreadyRegisteredError,
    WorkerNotFoundError,
)
from automojo.pychestrate.webservice.workers.models import (
    Worker,
    WorkerKind,
    WorkerStatus,
)


logger = logging.getLogger(__name__)


SessionFactory = Callable[[], DbSession]


_DEFAULT_POOL_SIZE = 1
_DEFAULT_POLL_INTERVAL_SECONDS = 0.5
_DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0
_DEFAULT_COMMAND_TIMEOUT_SECONDS = 300.0


def _resolve_existing_worker(
        *,
        db_session: DbSession,
        name: str,
    ) -> Optional[str]:
    """
        Look up a previously-registered local worker by name so a
        restart of the service reuses the same worker_id rather
        than colliding on the (project_id, name) unique constraint.
    """
    row = (
        db_session.query(Worker)
        .filter(Worker.name == name)
        .filter(Worker.kind == WorkerKind.LOCAL_PROCESS.value)
        .first()
    )
    if row is None:
        return None
    rtnval = str(row.worker_id)
    return rtnval


class LocalWorker:
    """
        One in-process worker thread.

        Owns its own thread, opens its own DbSession per
        operation, and runs ``run-command`` jobs with
        :func:`subprocess.run`.
    """

    def __init__(
            self,
            *,
            name: str,
            session_factory: SessionFactory,
            poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
            heartbeat_interval_seconds: float = (
                _DEFAULT_HEARTBEAT_INTERVAL_SECONDS
            ),
            default_command_timeout_seconds: float = (
                _DEFAULT_COMMAND_TIMEOUT_SECONDS
            ),
            attributes: Optional[Dict[str, Any]] = None,
        ):
        self._name: str = name
        self._session_factory: SessionFactory = session_factory
        self._poll_interval_seconds: float = poll_interval_seconds
        self._heartbeat_interval_seconds: float = (
            heartbeat_interval_seconds
        )
        self._default_command_timeout_seconds: float = (
            default_command_timeout_seconds
        )
        if attributes is None:
            self._attributes: Dict[str, Any] = {
                "host": socket.gethostname(),
                "pid": os.getpid(),
                "pool": "local",
            }
        else:
            self._attributes = dict(attributes)
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._worker_id: Optional[str] = None
        self._last_heartbeat_at: float = 0.0
        return

    @property
    def name(self) -> str:
        rtnval = self._name
        return rtnval

    @property
    def worker_id(self) -> Optional[str]:
        rtnval = self._worker_id
        return rtnval

    def _ensure_registered(self) -> str:
        """
            Make sure a :class:`Worker` row exists for this worker
            and return the ``worker_id``. Idempotent across service
            restarts: a row from a previous boot with the same
            name is reused.
        """
        if self._worker_id is not None:
            return self._worker_id
        db_session = self._session_factory()
        try:
            existing = _resolve_existing_worker(
                db_session=db_session, name=self._name,
            )
            if existing is not None:
                self._worker_id = existing
                # Stamp a heartbeat so the registry reflects that
                # this restart inherited the row.
                worker_service.heartbeat_worker(
                    db_session=db_session,
                    worker_id=existing,
                    status=WorkerStatus.IDLE,
                )
                return existing
            try:
                view = worker_service.register_worker(
                    db_session=db_session,
                    name=self._name,
                    kind=WorkerKind.LOCAL_PROCESS,
                    attributes=self._attributes,
                )
            except WorkerAlreadyRegisteredError:
                # Race: another startup path won. Re-resolve.
                existing = _resolve_existing_worker(
                    db_session=db_session, name=self._name,
                )
                if existing is None:
                    raise
                self._worker_id = existing
                return existing
        finally:
            db_session.close()
        self._worker_id = view.worker_id
        return view.worker_id

    def start(self) -> None:
        """
            Spin up the worker thread.
        """
        if self._thread is not None:
            err_lines = [
                "Worker has already been started.",
                "NAME: {}".format(self._name),
            ]
            err_msg = os.linesep.join(err_lines)
            raise RuntimeError(err_msg)
        self._ensure_registered()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="pych-local-worker-{0}".format(self._name),
            daemon=True,
        )
        self._thread.start()
        return

    def shutdown(self, *, wait: bool = True) -> None:
        """
            Signal the worker to exit and (optionally) join.
        """
        self._stop_event.set()
        if wait is True:
            if self._thread is not None:
                self._thread.join(timeout=10.0)
        return

    def _run_loop(self) -> None:
        logger.info(
            "local_worker.start name=%s worker_id=%s",
            self._name, self._worker_id,
        )
        while self._stop_event.is_set() is False:
            stop_requested = self._tick()
            if stop_requested is True:
                break
        logger.info(
            "local_worker.stop name=%s worker_id=%s",
            self._name, self._worker_id,
        )
        return

    def _tick(self) -> bool:
        """
            One iteration of the loop. Returns ``True`` when the
            worker should exit (the registry reports it as
            DRAINING, or the run loop encountered a fatal error).
        """
        # Heartbeat / drain check.
        now = time.time()
        if now - self._last_heartbeat_at >= self._heartbeat_interval_seconds:
            should_drain = self._heartbeat_and_check_drain()
            self._last_heartbeat_at = now
            if should_drain is True:
                logger.info(
                    "local_worker.draining name=%s worker_id=%s",
                    self._name, self._worker_id,
                )
                return True

        # Try to claim a job.
        claimed = self._try_claim()
        if claimed is None:
            self._stop_event.wait(self._poll_interval_seconds)
            return False

        self._execute_and_report(claimed=claimed)
        return False

    def _heartbeat_and_check_drain(self) -> bool:
        """
            Stamp last_heartbeat_at and report IDLE. If the
            registry now says DRAINING, the worker should exit.
            Returns ``True`` when DRAINING.
        """
        if self._worker_id is None:
            return False
        db_session = self._session_factory()
        try:
            try:
                view = worker_service.heartbeat_worker(
                    db_session=db_session,
                    worker_id=self._worker_id,
                    status=None,
                )
            except WorkerNotFoundError:
                # Admin deregistered us — exit cleanly.
                logger.info(
                    "local_worker.deregistered name=%s",
                    self._name,
                )
                return True
            if view.status == WorkerStatus.DRAINING.value:
                return True
        finally:
            db_session.close()
        return False

    def _try_claim(self) -> Optional[Any]:
        if self._worker_id is None:
            return None
        db_session = self._session_factory()
        try:
            rtnval = jobservice.claim_next_job(
                db_session=db_session, worker_id=self._worker_id,
            )
        finally:
            db_session.close()
        return rtnval

    def _execute_and_report(self, *, claimed: Any) -> None:
        """
            Execute the claimed job and report the outcome.
        """
        kind = claimed.kind
        if kind != "run-command":
            self._report(
                job_id=claimed.job_id,
                result_code=1,
                stdout="",
                stderr="",
                error_text="unsupported job kind: {0}".format(kind),
            )
            return

        command_raw = claimed.payload.get("command", None)
        if command_raw is None or len(str(command_raw)) == 0:
            self._report(
                job_id=claimed.job_id,
                result_code=1,
                stdout="",
                stderr="",
                error_text="missing 'command' in job payload",
            )
            return
        timeout_raw = claimed.payload.get(
            "timeout_seconds", self._default_command_timeout_seconds,
        )
        try:
            timeout_value = float(timeout_raw)
        except (TypeError, ValueError):
            timeout_value = self._default_command_timeout_seconds

        try:
            completed = subprocess.run(
                str(command_raw),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_value,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if exc.stdout is not None else ""
            stderr = exc.stderr if exc.stderr is not None else ""
            err_text = "command timed out after {0:.1f}s".format(
                timeout_value,
            )
            self._report(
                job_id=claimed.job_id,
                result_code=1,
                stdout=stdout if isinstance(stdout, str) else stdout.decode(
                    "utf-8", errors="replace",
                ),
                stderr=stderr if isinstance(stderr, str) else stderr.decode(
                    "utf-8", errors="replace",
                ),
                error_text=err_text,
            )
            return
        except Exception as exc:
            self._report(
                job_id=claimed.job_id,
                result_code=1,
                stdout="",
                stderr="",
                error_text="subprocess crashed: {0}".format(exc),
            )
            return

        self._report(
            job_id=claimed.job_id,
            result_code=int(completed.returncode),
            stdout=completed.stdout if completed.stdout is not None else "",
            stderr=completed.stderr if completed.stderr is not None else "",
            error_text=None,
        )
        return

    def _report(
            self,
            *,
            job_id: str,
            result_code: int,
            stdout: str,
            stderr: str,
            error_text: Optional[str],
        ) -> None:
        if self._worker_id is None:
            return
        db_session = self._session_factory()
        try:
            jobservice.report_result(
                db_session=db_session,
                worker_id=self._worker_id,
                job_id=job_id,
                result_code=result_code,
                stdout=stdout,
                stderr=stderr,
                error_text=error_text,
            )
        except LookupError as exc:
            logger.warning(
                "local_worker.report_failed job_id=%s err=%s",
                job_id, exc,
            )
        finally:
            db_session.close()
        return


class LocalWorkerPool:
    """
        Manages a fixed-size set of :class:`LocalWorker` threads.
    """

    def __init__(
            self,
            *,
            session_factory: SessionFactory,
            size: int = _DEFAULT_POOL_SIZE,
            base_name: Optional[str] = None,
            poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
            heartbeat_interval_seconds: float = (
                _DEFAULT_HEARTBEAT_INTERVAL_SECONDS
            ),
            default_command_timeout_seconds: float = (
                _DEFAULT_COMMAND_TIMEOUT_SECONDS
            ),
        ):
        if size < 0:
            err_lines = [
                "Pool size must be >= 0.",
                "REQUESTED: {}".format(size),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg)
        self._session_factory: SessionFactory = session_factory
        self._size: int = size
        if base_name is None or len(base_name) == 0:
            self._base_name: str = "local-{0}".format(socket.gethostname())
        else:
            self._base_name = base_name
        self._poll_interval_seconds: float = poll_interval_seconds
        self._heartbeat_interval_seconds: float = (
            heartbeat_interval_seconds
        )
        self._default_command_timeout_seconds: float = (
            default_command_timeout_seconds
        )
        self._workers: List[LocalWorker] = []
        self._started: bool = False
        return

    @property
    def size(self) -> int:
        rtnval = self._size
        return rtnval

    @property
    def workers(self) -> List[LocalWorker]:
        rtnval = list(self._workers)
        return rtnval

    @property
    def is_started(self) -> bool:
        rtnval = self._started
        return rtnval

    def start(self) -> None:
        """
            Construct and start each worker thread.
        """
        if self._started is True:
            return
        if self._size == 0:
            self._started = True
            return
        for index in range(self._size):
            if self._size == 1:
                name = self._base_name
            else:
                name = "{0}-{1}".format(self._base_name, index)
            worker = LocalWorker(
                name=name,
                session_factory=self._session_factory,
                poll_interval_seconds=self._poll_interval_seconds,
                heartbeat_interval_seconds=(
                    self._heartbeat_interval_seconds
                ),
                default_command_timeout_seconds=(
                    self._default_command_timeout_seconds
                ),
            )
            worker.start()
            self._workers.append(worker)
        self._started = True
        return

    def shutdown(self, *, wait: bool = True) -> None:
        """
            Signal every worker to stop, then join.
        """
        for worker in self._workers:
            worker.shutdown(wait=False)
        if wait is True:
            for worker in self._workers:
                worker.shutdown(wait=True)
        return


def resolve_pool_config_from_env(
        *,
        environment: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
    """
        Read pool configuration from process environment so the
        operator can disable / resize the pool without a code
        change.

        Recognised vars:

        * ``PYCHESTRATE_LOCAL_WORKER_POOL_SIZE`` — integer >= 0;
          default ``1``. Set to ``0`` to disable.
        * ``PYCHESTRATE_LOCAL_WORKER_POOL_NAME`` — base worker
          name; defaults to ``local-<hostname>``.
        * ``PYCHESTRATE_LOCAL_WORKER_POLL_INTERVAL`` — seconds
          between empty polls; default ``0.5``.
        * ``PYCHESTRATE_LOCAL_WORKER_HEARTBEAT_INTERVAL`` —
          seconds between heartbeats; default ``30``.
        * ``PYCHESTRATE_LOCAL_WORKER_COMMAND_TIMEOUT`` — seconds
          before a subprocess is killed; default ``300``.
    """
    if environment is None:
        env = os.environ
    else:
        env = environment

    raw_size = env.get("PYCHESTRATE_LOCAL_WORKER_POOL_SIZE", None)
    if raw_size is None:
        size = _DEFAULT_POOL_SIZE
    else:
        try:
            size = int(raw_size)
        except (TypeError, ValueError):
            size = _DEFAULT_POOL_SIZE
        if size < 0:
            size = 0

    base_name = env.get("PYCHESTRATE_LOCAL_WORKER_POOL_NAME", None)

    raw_poll = env.get("PYCHESTRATE_LOCAL_WORKER_POLL_INTERVAL", None)
    if raw_poll is None:
        poll_interval = _DEFAULT_POLL_INTERVAL_SECONDS
    else:
        try:
            poll_interval = float(raw_poll)
        except (TypeError, ValueError):
            poll_interval = _DEFAULT_POLL_INTERVAL_SECONDS

    raw_hb = env.get(
        "PYCHESTRATE_LOCAL_WORKER_HEARTBEAT_INTERVAL", None,
    )
    if raw_hb is None:
        heartbeat_interval = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    else:
        try:
            heartbeat_interval = float(raw_hb)
        except (TypeError, ValueError):
            heartbeat_interval = _DEFAULT_HEARTBEAT_INTERVAL_SECONDS

    raw_timeout = env.get(
        "PYCHESTRATE_LOCAL_WORKER_COMMAND_TIMEOUT", None,
    )
    if raw_timeout is None:
        command_timeout = _DEFAULT_COMMAND_TIMEOUT_SECONDS
    else:
        try:
            command_timeout = float(raw_timeout)
        except (TypeError, ValueError):
            command_timeout = _DEFAULT_COMMAND_TIMEOUT_SECONDS

    rtnval = {
        "size": size,
        "base_name": base_name,
        "poll_interval_seconds": poll_interval,
        "heartbeat_interval_seconds": heartbeat_interval,
        "default_command_timeout_seconds": command_timeout,
    }
    return rtnval
