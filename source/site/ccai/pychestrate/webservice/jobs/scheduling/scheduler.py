"""
.. module:: webservice.jobs.scheduling.scheduler
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: PeriodicTaskScheduler — daemon-thread-per-task scheduler.

.. moduleauthor:: Code Craft AI LLC

Each registered :class:`PeriodicTask` runs on its own daemon
thread. The thread sleeps in small steps so :meth:`stop` returns
within at most ``poll_interval_seconds`` after being called. Tasks
that raise are logged and the loop continues — one misbehaving
task cannot starve the others.

This is a minimal in-process scheduler; durable scheduling is the
``0-system-health`` feature's M3+ scope.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import threading

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


TaskCallable = Callable[[], None]


@dataclass(frozen=True)
class PeriodicTask:
    """
        Operator-supplied description of one periodic task.

        :param name: Unique identifier (used in logs + tests).
        :param interval_seconds: Wall-clock interval between
                                 invocations of ``run``.
        :param run: Zero-arg callable invoked on each tick. Tasks
                    that need a session should close over a session
                    factory at registration time.
    """
    name: str
    interval_seconds: float
    run: TaskCallable


@dataclass
class _TaskRunner:
    """
        Internal bookkeeping for one running task. Mutable so the
        scheduler can flip the stop flag and join the thread.

        :param task: The :class:`PeriodicTask` being run.
        :param stop_event: Shared :class:`threading.Event` the loop
                           polls between sleeps.
        :param thread: The daemon thread the loop runs on. ``None``
                       until :meth:`PeriodicTaskScheduler.start`
                       constructs it.
    """
    task: PeriodicTask
    stop_event: threading.Event
    thread: Optional[threading.Thread] = field(default=None)


@dataclass(frozen=True)
class SchedulerHandle:
    """
        Operator-facing handle returned by
        :meth:`PeriodicTaskScheduler.start`. Exposes :meth:`stop` so
        callers can tear the scheduler down at process exit.

        :param scheduler: The owning scheduler instance.
    """
    scheduler: "PeriodicTaskScheduler"

    def stop(self, *, join_timeout_seconds: float = 5.0) -> None:
        """
            Stop every running task on this handle's scheduler.

            :param join_timeout_seconds: Upper bound the caller
                                         waits for each task thread
                                         to exit.

            :returns: None.
        """
        self.scheduler.stop(join_timeout_seconds=join_timeout_seconds)
        return


class PeriodicTaskScheduler:
    """
        Daemon-thread-per-task scheduler. Not durable; not
        cross-process; not a replacement for ``0-system-health``.
        Solves exactly one problem: invoking a handful of in-process
        ticks on a fixed cadence after service startup.
    """

    DEFAULT_POLL_INTERVAL_SECONDS: float = 0.5

    def __init__(
            self,
            *,
            poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
        ) -> None:
        """
            Construct an empty scheduler.

            :param poll_interval_seconds: Maximum sleep granularity
                                          inside the task loop —
                                          governs how fast
                                          :meth:`stop` returns.

            :returns: None.
        """
        self._lock: threading.RLock = threading.RLock()
        self._runners: Dict[str, _TaskRunner] = {}
        self._poll_interval_seconds: float = poll_interval_seconds
        self._started: bool = False
        return

    def register(self, *, task: PeriodicTask) -> None:
        """
            Add a task to the scheduler. Registering an already-
            present task name raises ``ValueError`` — duplicates
            indicate a bootstrap bug.

            :param task: Task to register.

            :returns: None.
            :raises: ValueError on duplicate name.
        """
        with self._lock:
            if task.name in self._runners:
                err_msg_lines = ["Duplicate periodic task name."]
                err_msg_lines.append("NAME: {}".format(task.name))
                err_msg_lines.append(
                    "EXISTING: ({})".format(len(self._runners))
                )
                err_msg = "\n".join(err_msg_lines)
                raise ValueError(err_msg)
            runner = _TaskRunner(
                task=task,
                stop_event=threading.Event(),
            )
            self._runners[task.name] = runner
        return

    def start(self) -> SchedulerHandle:
        """
            Spawn one daemon thread per registered task and run
            them on their respective intervals. Idempotent — a
            second call is a no-op so callers do not need to
            track whether bootstrap already started the scheduler.

            :returns: :class:`SchedulerHandle` for ``stop``.
        """
        with self._lock:
            if self._started is True:
                rtnval = SchedulerHandle(scheduler=self)
                return rtnval
            for runner in self._runners.values():
                thread = threading.Thread(
                    target=self._run_loop,
                    name="periodic:{}".format(runner.task.name),
                    args=(runner,),
                    daemon=True,
                )
                runner.thread = thread
                thread.start()
            self._started = True
        rtnval = SchedulerHandle(scheduler=self)
        return rtnval

    def stop(self, *, join_timeout_seconds: float = 5.0) -> None:
        """
            Signal every task to stop, then join their threads.
            Idempotent — calling on a stopped scheduler is a no-op.

            :param join_timeout_seconds: Max time to wait for each
                                         thread to exit before
                                         giving up. The threads are
                                         daemons so leaks are
                                         tolerated at process exit.

            :returns: None.
        """
        with self._lock:
            if self._started is False:
                return
            runners = list(self._runners.values())
        for runner in runners:
            runner.stop_event.set()
        for runner in runners:
            thread = runner.thread
            if thread is None:
                continue
            thread.join(timeout=join_timeout_seconds)
        with self._lock:
            self._started = False
        return

    def is_running(self) -> bool:
        """
            Return whether the scheduler has been started and not
            yet stopped. Used by the bootstrap smoke tests.

            :returns: Boolean.
        """
        with self._lock:
            rtnval = self._started
        return rtnval

    def task_names(self) -> List[str]:
        """
            Return the names of every registered task in insertion
            order.

            :returns: List of names.
        """
        with self._lock:
            rtnval = list(self._runners.keys())
        return rtnval

    def _run_loop(self, runner: _TaskRunner) -> None:
        """
            Internal thread target. Sleeps in
            ``poll_interval_seconds`` chunks so :meth:`stop`
            promptly observes the stop flag. Task exceptions are
            logged and the loop continues.

            :param runner: The task's :class:`_TaskRunner`.

            :returns: None.
        """
        task = runner.task
        stop_event = runner.stop_event
        elapsed = 0.0
        while stop_event.is_set() is False:
            sleep_for = self._poll_interval_seconds
            if sleep_for > task.interval_seconds:
                sleep_for = task.interval_seconds
            stop_event.wait(timeout=sleep_for)
            if stop_event.is_set() is True:
                break
            elapsed = elapsed + sleep_for
            if elapsed < task.interval_seconds:
                continue
            elapsed = 0.0
            try:
                task.run()
            except Exception as xcpt:  # noqa: BLE001 — task isolation
                logger.exception(
                    "scheduling.task_raised name=%s error=%s",
                    task.name, xcpt,
                )
        return


_DEFAULT_LOCK = threading.RLock()
_DEFAULT_SCHEDULER: Optional[PeriodicTaskScheduler] = None


def default_scheduler() -> PeriodicTaskScheduler:
    """
        Return the process-wide default scheduler, creating it on
        first call. Bootstraps register tasks against this single
        instance so the operator gets one start / stop handle.

        :returns: :class:`PeriodicTaskScheduler`.
    """
    global _DEFAULT_SCHEDULER
    with _DEFAULT_LOCK:
        if _DEFAULT_SCHEDULER is None:
            _DEFAULT_SCHEDULER = PeriodicTaskScheduler()
        rtnval = _DEFAULT_SCHEDULER
    return rtnval


def reset_default_scheduler_for_testing() -> None:
    """
        Discard the module-level default scheduler so each test
        starts from a clean slate. Stops the existing instance
        first if it was started.

        :returns: None.
    """
    global _DEFAULT_SCHEDULER
    with _DEFAULT_LOCK:
        if _DEFAULT_SCHEDULER is not None:
            _DEFAULT_SCHEDULER.stop()
        _DEFAULT_SCHEDULER = None
    return
