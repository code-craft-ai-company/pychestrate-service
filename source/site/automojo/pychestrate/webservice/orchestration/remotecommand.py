"""
.. module:: pychestrate.webservice.orchestration.remotecommand
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Taskplus :class:`Task` that dispatches a shell command to a worker.

.. moduleauthor:: Automation Mojo LLC

The :class:`RemoteCommand` task is the bridge between
:mod:`automojo.taskplus` and the pychestrate worker queue. When the
flow engine reaches a ``RemoteCommand`` step it:

1. enqueues a :class:`WorkerJob` with kind ``run-command`` and the
   declared selectors (``target_pod_name`` / ``target_kind``);
2. blocks on :func:`workers.jobservice.wait_for_completion` until the
   chosen worker reports a result;
3. emits the captured stdout / stderr to the worker thread's log
   buffer so it lands in the persisted ``log_text``;
4. returns the worker-reported ``result_code`` (or ``1`` on
   timeout / crash) — taskplus uses this as the step's exit code.

Workflow YAML::

    flow:
      - task: probe-raspi-01
        tasktype: automojo.pychestrate.webservice.orchestration.remotecommand@RemoteCommand
        command: uname -a
        target_pod_name: raspi-01
        timeout_seconds: 30
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import threading

from typing import Any, Callable, Dict, Optional

from automojo.taskplus.model.task import Task

from automojo.pychestrate.webservice.workers import jobservice
from automojo.pychestrate.webservice.workers.models import WorkerKind


_DEFAULT_TIMEOUT_SECONDS = 60.0


# The FlowRuntime worker thread binds its session_factory here
# before invoking FlowEngine.execute. RemoteCommand reads it back
# rather than threading the factory through the taskplus flowstate
# (which would require subclassing FlowEngine just to inject one
# extra dict entry).
_THREAD_LOCAL = threading.local()


def set_session_factory(*, factory: Optional[Callable]) -> None:
    """
        Bind a zero-arg callable that returns a fresh DbSession.
        Set by the :class:`FlowRuntime` worker thread; read by
        :class:`RemoteCommand` instances running in that worker.
    """
    _THREAD_LOCAL.session_factory = factory
    return


def get_session_factory() -> Optional[Callable]:
    """
        Return the thread-local session_factory, or ``None`` when
        the worker hasn't bound one (e.g. unit tests using
        :class:`FlowEngine` directly without a runtime wrapper).
    """
    rtnval = getattr(_THREAD_LOCAL, "session_factory", None)
    return rtnval


class RemoteCommand(Task):
    """
        Dispatch a shell command to a registered worker and wait
        for its result.

        Required ``task_info`` fields:

        * ``command`` — string command to run.

        Optional ``task_info`` fields:

        * ``target_pod_name`` — pod-name selector.
        * ``target_kind`` — ``local-process`` or ``remote-machine``.
        * ``timeout_seconds`` — how long to wait. Defaults to 60.
    """

    def __init__(
            self,
            ordinal: str,
            label: str,
            task_info: Dict[str, Any],
            logger: logging.Logger,
        ):
        super(RemoteCommand, self).__init__(
            ordinal, label, task_info, logger,
        )
        if "command" not in task_info:
            err_lines = ["RemoteCommand requires a 'command' field."]
            err_lines.append("LABEL: {}".format(label))
            err_msg = os.linesep.join(err_lines)
            raise KeyError(err_msg) from None
        self._command: str = str(task_info["command"])
        self._target_pod_name: Optional[str] = task_info.get(
            "target_pod_name", None,
        )
        target_kind_raw = task_info.get("target_kind", None)
        if target_kind_raw is not None:
            self._target_kind: Optional[WorkerKind] = WorkerKind(
                target_kind_raw,
            )
        else:
            self._target_kind = None
        timeout_raw = task_info.get(
            "timeout_seconds", _DEFAULT_TIMEOUT_SECONDS,
        )
        try:
            self._timeout_seconds: float = float(timeout_raw)
        except (TypeError, ValueError):
            self._timeout_seconds = _DEFAULT_TIMEOUT_SECONDS

        # Retry policy. ``retries`` is the workflow-author-facing
        # name (consistent with shell ``retry`` semantics: 0
        # retries == 1 attempt). It is translated to the
        # queue's ``max_attempts``.
        retries_raw = task_info.get("retries", 0)
        try:
            retries_value = int(retries_raw)
        except (TypeError, ValueError):
            retries_value = 0
        if retries_value < 0:
            retries_value = 0
        self._max_attempts: int = retries_value + 1
        retry_delay_raw = task_info.get("retry_delay_seconds", 0.0)
        try:
            self._retry_delay_seconds: float = float(retry_delay_raw)
        except (TypeError, ValueError):
            self._retry_delay_seconds = 0.0
        if self._retry_delay_seconds < 0.0:
            self._retry_delay_seconds = 0.0
        retry_strategy_raw = task_info.get("retry_strategy", None)
        if retry_strategy_raw is None:
            self._retry_strategy: str = "fixed"
        else:
            self._retry_strategy = str(retry_strategy_raw)
        required_caps_raw = task_info.get("required_capabilities", None)
        if required_caps_raw is None:
            self._required_capabilities: list = []
        elif isinstance(required_caps_raw, (list, tuple)):
            self._required_capabilities = [
                str(item) for item in required_caps_raw
                if isinstance(item, str)
            ]
        else:
            err_lines = [
                "RemoteCommand 'required_capabilities' must be a list.",
                "LABEL: {}".format(label),
                "FOUND_TYPE: {}".format(type(required_caps_raw).__name__),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        return

    @property
    def command(self) -> str:
        rtnval = self._command
        return rtnval

    @property
    def target_pod_name(self) -> Optional[str]:
        rtnval = self._target_pod_name
        return rtnval

    @property
    def target_kind(self) -> Optional[WorkerKind]:
        rtnval = self._target_kind
        return rtnval

    @property
    def timeout_seconds(self) -> float:
        rtnval = self._timeout_seconds
        return rtnval

    @property
    def max_attempts(self) -> int:
        rtnval = self._max_attempts
        return rtnval

    @property
    def retry_delay_seconds(self) -> float:
        rtnval = self._retry_delay_seconds
        return rtnval

    @property
    def retry_strategy(self) -> str:
        rtnval = self._retry_strategy
        return rtnval

    @property
    def required_capabilities(self) -> list:
        rtnval = list(self._required_capabilities)
        return rtnval

    def _compute_wait_budget(self) -> float:
        """
            Sum the per-attempt timeout across every attempt
            plus the cumulative retry backoff so
            ``wait_for_completion`` doesn't return before the
            queue has had a chance to schedule each retry.

            For ``max_attempts=1`` (the default, no retries)
            this returns ``timeout_seconds`` exactly — same
            behaviour as before retries existed.
        """
        attempts = max(1, int(self._max_attempts))
        per_attempt = self._timeout_seconds * attempts
        retries = attempts - 1
        if retries <= 0:
            rtnval = per_attempt
            return rtnval
        if self._retry_strategy == "exponential":
            # Backoffs are base * 2**(k-1) for k = 1..retries.
            multiplier_total = (2 ** retries) - 1
            backoff_total = self._retry_delay_seconds * multiplier_total
        else:
            backoff_total = self._retry_delay_seconds * retries
        rtnval = per_attempt + backoff_total
        return rtnval

    def perform_task(
            self,
            environment: Dict[str, str],
            parameters: Optional[Dict[str, Any]],
            flowstate: Dict[str, Any],
        ) -> int:
        """
            Enqueue + wait. The session_factory is read from a
            thread-local set by the :class:`FlowRuntime` worker
            thread.
        """
        session_factory = get_session_factory()
        if session_factory is None:
            err_lines = [
                "RemoteCommand requires a session_factory bound on the",
                "calling thread. Use FlowRuntime to invoke flows that",
                "include RemoteCommand tasks (it sets the thread-local",
                "automatically).",
            ]
            err_msg = os.linesep.join(err_lines)
            self._logger.error(err_msg)
            return 1

        # Enqueue. ``timeout_seconds`` is per-attempt — workers
        # use it to bound the subprocess. The overall budget for
        # the ``wait_for_completion`` call below is computed
        # separately so retries fit inside it.
        db_session = session_factory()
        try:
            job_view = jobservice.enqueue_job(
                db_session=db_session,
                kind="run-command",
                payload={
                    "command": self._command,
                    "timeout_seconds": self._timeout_seconds,
                },
                target_pod_name=self._target_pod_name,
                target_kind=self._target_kind,
                max_attempts=self._max_attempts,
                retry_delay_seconds=self._retry_delay_seconds,
                retry_strategy=self._retry_strategy,
                required_capabilities=self._required_capabilities,
            )
        finally:
            db_session.close()

        self._logger.info(
            "REMOTE_COMMAND enqueued job=%s pod=%s kind=%s command=%s",
            job_view.job_id,
            self._target_pod_name,
            self._target_kind.value if self._target_kind else None,
            self._command,
        )

        # Wait. The per-attempt budget is ``timeout_seconds``;
        # with retries we add a per-attempt slice plus the sum
        # of the configured backoffs so the wait_for_completion
        # call doesn't time out before the queue exhausts the
        # retry policy.
        wait_budget = self._compute_wait_budget()
        terminal = jobservice.wait_for_completion(
            session_factory=session_factory,
            job_id=job_view.job_id,
            timeout_seconds=wait_budget,
        )
        if terminal is None:
            self._logger.error(
                "REMOTE_COMMAND missing job after enqueue job=%s",
                job_view.job_id,
            )
            return 1
        if terminal.state == "succeeded" or terminal.state == "failed":
            self._logger.info(
                "REMOTE_COMMAND result job=%s state=%s code=%s",
                terminal.job_id,
                terminal.state,
                terminal.result_code,
            )
            if len(terminal.stdout) > 0:
                self._logger.info(
                    "REMOTE_COMMAND stdout job=%s:\n%s",
                    terminal.job_id, terminal.stdout,
                )
            if len(terminal.stderr) > 0:
                self._logger.error(
                    "REMOTE_COMMAND stderr job=%s:\n%s",
                    terminal.job_id, terminal.stderr,
                )
            if terminal.error_text is not None:
                self._logger.error(
                    "REMOTE_COMMAND error_text job=%s: %s",
                    terminal.job_id, terminal.error_text,
                )
                return 1
            if terminal.result_code is None:
                return 1
            rtnval = int(terminal.result_code)
            return rtnval

        # Still PENDING / CLAIMED / RUNNING — timed out.
        self._logger.error(
            "REMOTE_COMMAND timed out after %.1fs job=%s state=%s",
            self._timeout_seconds, terminal.job_id, terminal.state,
        )
        return 1
