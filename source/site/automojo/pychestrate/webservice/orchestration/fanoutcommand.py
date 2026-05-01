"""
.. module:: pychestrate.webservice.orchestration.fanoutcommand
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Taskplus :class:`Task` that runs the same command on N workers concurrently.

.. moduleauthor:: Automation Mojo LLC

The :class:`FanOutCommand` is :class:`RemoteCommand`'s
many-targets cousin. A single workflow step enqueues one job per
entry in ``targets``, waits for all of them in parallel via a
``ThreadPoolExecutor``, aggregates per-target outcomes for
operator inspection (logged + summarised), and reports a single
``result_code`` to the engine: ``0`` only when every target
returned ``0``.

The natural use case is "run the same smoke test on every Pi at
once" — historically that meant N hand-coded copy-paste flow
steps. Workflow YAML::

    flow:
      - task: smoke-on-fleet
        tasktype: automojo.pychestrate.webservice.orchestration.fanoutcommand@FanOutCommand
        command: smoke-test.sh
        timeout_seconds: 60
        retries: 1
        targets:
          - target_pod_name: raspi-01
          - target_pod_name: raspi-02
          - target_pod_name: raspi-03
            required_capabilities: [tpm-2.0]

Each target may override ``target_pod_name`` / ``target_kind`` /
``required_capabilities``; every other field
(``command`` / ``timeout_seconds`` / ``retries`` /
``retry_delay_seconds`` / ``retry_strategy``) is inherited from
the parent.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from automojo.taskplus.model.task import Task

from automojo.pychestrate.webservice.workers import jobservice
from automojo.pychestrate.webservice.workers.models import WorkerKind

from automojo.pychestrate.webservice.orchestration.remotecommand import (
    get_flow_id,
    get_session_factory,
)


_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_TARGET_PARALLELISM = 8


@dataclass(frozen=True)
class _TargetSpec:
    """
        One fan-out target after parameter resolution. Internal
        scratch type — not part of the public surface.
    """
    target_pod_name: Optional[str]
    target_kind: Optional[WorkerKind]
    required_capabilities: List[str]


def _coerce_target_kind(*, raw, label: str, index: int):
    if raw is None:
        return None
    try:
        rtnval = WorkerKind(raw)
    except ValueError as exc:
        err_lines = [
            "FanOutCommand target_kind not recognised.",
            "LABEL: {}".format(label),
            "TARGET_INDEX: {}".format(index),
            "FOUND: {!r}".format(raw),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from exc
    return rtnval


def _coerce_required_caps(*, raw, label: str, index: int) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        err_lines = [
            "FanOutCommand target.required_capabilities must be a list.",
            "LABEL: {}".format(label),
            "TARGET_INDEX: {}".format(index),
            "FOUND_TYPE: {}".format(type(raw).__name__),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    rtnval = [str(item) for item in raw if isinstance(item, str)]
    return rtnval


class FanOutCommand(Task):
    """
        Dispatch the same shell command to every entry in
        ``targets`` in parallel.

        Required ``task_info`` fields:

        * ``command`` — string command to run.
        * ``targets`` — list of dicts; each entry is a partial
          ``RemoteCommand`` selector. At least one target is
          required.

        Optional ``task_info`` fields (inherited by every
        target unless the entry overrides):

        * ``timeout_seconds`` — per-target subprocess bound.
          Default 60.
        * ``retries`` / ``retry_delay_seconds`` /
          ``retry_strategy`` — retry policy applied to every
          target.
        * ``parallelism`` — max concurrent ``wait_for_completion``
          calls (i.e. thread pool size). Default 8.
    """

    def __init__(
            self,
            ordinal: str,
            label: str,
            task_info: Dict[str, Any],
            logger: logging.Logger,
        ):
        super(FanOutCommand, self).__init__(
            ordinal, label, task_info, logger,
        )
        if "command" not in task_info:
            err_lines = ["FanOutCommand requires a 'command' field."]
            err_lines.append("LABEL: {}".format(label))
            err_msg = os.linesep.join(err_lines)
            raise KeyError(err_msg) from None
        targets_raw = task_info.get("targets", None)
        if targets_raw is None or not isinstance(targets_raw, list):
            err_lines = [
                "FanOutCommand requires 'targets' (list).",
                "LABEL: {}".format(label),
            ]
            err_msg = os.linesep.join(err_lines)
            raise KeyError(err_msg) from None
        if len(targets_raw) == 0:
            err_lines = [
                "FanOutCommand 'targets' list cannot be empty.",
                "LABEL: {}".format(label),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None

        self._command: str = str(task_info["command"])

        timeout_raw = task_info.get(
            "timeout_seconds", _DEFAULT_TIMEOUT_SECONDS,
        )
        try:
            self._timeout_seconds: float = float(timeout_raw)
        except (TypeError, ValueError):
            self._timeout_seconds = _DEFAULT_TIMEOUT_SECONDS

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

        parallelism_raw = task_info.get(
            "parallelism", _DEFAULT_TARGET_PARALLELISM,
        )
        try:
            self._parallelism: int = int(parallelism_raw)
        except (TypeError, ValueError):
            self._parallelism = _DEFAULT_TARGET_PARALLELISM
        if self._parallelism < 1:
            self._parallelism = 1

        priority_raw = task_info.get("priority", 0)
        try:
            self._priority: int = int(priority_raw)
        except (TypeError, ValueError):
            self._priority = 0

        self._targets: List[_TargetSpec] = []
        for index, entry in enumerate(targets_raw):
            if not isinstance(entry, dict):
                err_lines = [
                    "FanOutCommand 'targets' entries must be objects.",
                    "LABEL: {}".format(label),
                    "TARGET_INDEX: {}".format(index),
                    "FOUND_TYPE: {}".format(type(entry).__name__),
                ]
                err_msg = os.linesep.join(err_lines)
                raise ValueError(err_msg) from None
            self._targets.append(_TargetSpec(
                target_pod_name=entry.get("target_pod_name", None),
                target_kind=_coerce_target_kind(
                    raw=entry.get("target_kind", None),
                    label=label, index=index,
                ),
                required_capabilities=_coerce_required_caps(
                    raw=entry.get("required_capabilities", None),
                    label=label, index=index,
                ),
            ))
        return

    @property
    def command(self) -> str:
        rtnval = self._command
        return rtnval

    @property
    def targets(self) -> List[_TargetSpec]:
        rtnval = list(self._targets)
        return rtnval

    @property
    def timeout_seconds(self) -> float:
        rtnval = self._timeout_seconds
        return rtnval

    @property
    def parallelism(self) -> int:
        rtnval = self._parallelism
        return rtnval

    def _compute_wait_budget(self) -> float:
        """
            Same shape as RemoteCommand: per-attempt timeout
            times attempts, plus cumulative backoff. Each
            target waits independently inside the pool, so
            this budget applies per target rather than per
            block.
        """
        attempts = max(1, int(self._max_attempts))
        per_attempt = self._timeout_seconds * attempts
        retries = attempts - 1
        if retries <= 0:
            rtnval = per_attempt
            return rtnval
        if self._retry_strategy == "exponential":
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
            Enqueue one job per target in parallel; wait for
            every job; aggregate the result codes. Returns
            ``0`` only when every target returned ``0``.
        """
        session_factory = get_session_factory()
        if session_factory is None:
            err_lines = [
                "FanOutCommand requires a session_factory bound on the",
                "calling thread. Use FlowRuntime to invoke flows that",
                "include FanOutCommand tasks (it sets the thread-local",
                "automatically).",
            ]
            err_msg = os.linesep.join(err_lines)
            self._logger.error(err_msg)
            return 1

        # We always tag the dispatched jobs with the owning
        # flow_id so a partially-completed fan-out doesn't leak
        # leases / orphan rows on flow exit (FlowRuntime cleans
        # up on the same holder string).
        flow_id = get_flow_id()
        if flow_id is not None and len(flow_id) > 0:
            lease_holder: Optional[str] = "flow:{0}".format(flow_id)
        else:
            lease_holder = None

        # Enqueue every target's job up front; wait afterwards
        # so all targets start their wait clocks at the same
        # moment.
        enqueued_jobs: List[Dict[str, Any]] = []
        for index, target in enumerate(self._targets):
            db_session = session_factory()
            try:
                job_view = jobservice.enqueue_job(
                    db_session=db_session,
                    kind="run-command",
                    payload={
                        "command": self._command,
                        "timeout_seconds": self._timeout_seconds,
                    },
                    target_pod_name=target.target_pod_name,
                    target_kind=target.target_kind,
                    max_attempts=self._max_attempts,
                    retry_delay_seconds=self._retry_delay_seconds,
                    retry_strategy=self._retry_strategy,
                    required_capabilities=target.required_capabilities,
                    # Fan-out doesn't acquire a lease — multiple
                    # targets shouldn't fight to reserve workers
                    # they don't share. Lease semantics are for
                    # single-target ``exclusive: true`` paths.
                    lease_holder=None,
                    lease_ttl_seconds=None,
                    priority=self._priority,
                )
            finally:
                db_session.close()
            enqueued_jobs.append({
                "index": index,
                "target": target,
                "job_id": job_view.job_id,
            })
            self._logger.info(
                "FAN_OUT_COMMAND enqueued idx=%d job=%s pod=%s kind=%s caps=%s command=%s",
                index, job_view.job_id,
                target.target_pod_name,
                target.target_kind.value if target.target_kind else None,
                target.required_capabilities,
                self._command,
            )

        wait_budget = self._compute_wait_budget()

        # Wait for every job in parallel.
        with ThreadPoolExecutor(
            max_workers=self._parallelism,
            thread_name_prefix="pych-fanout",
        ) as pool:
            future_to_meta = {
                pool.submit(
                    jobservice.wait_for_completion,
                    session_factory=session_factory,
                    job_id=entry["job_id"],
                    timeout_seconds=wait_budget,
                ): entry
                for entry in enqueued_jobs
            }
            outcomes: List[Dict[str, Any]] = []
            for future, entry in future_to_meta.items():
                terminal = future.result()
                outcomes.append({
                    "index": entry["index"],
                    "target": entry["target"],
                    "job_id": entry["job_id"],
                    "terminal": terminal,
                })

        outcomes.sort(key=lambda o: o["index"])

        any_failed = False
        for o in outcomes:
            terminal = o["terminal"]
            if terminal is None:
                self._logger.error(
                    "FAN_OUT_COMMAND missing job after enqueue idx=%d job=%s",
                    o["index"], o["job_id"],
                )
                any_failed = True
                continue
            if terminal.state == "succeeded" and (terminal.result_code or 0) == 0:
                self._logger.info(
                    "FAN_OUT_COMMAND ok idx=%d job=%s rc=%s",
                    o["index"], terminal.job_id, terminal.result_code,
                )
            else:
                any_failed = True
                self._logger.error(
                    "FAN_OUT_COMMAND fail idx=%d job=%s state=%s rc=%s err=%s",
                    o["index"],
                    terminal.job_id,
                    terminal.state,
                    terminal.result_code,
                    terminal.error_text,
                )
                if terminal.stderr is not None and len(terminal.stderr) > 0:
                    self._logger.error(
                        "FAN_OUT_COMMAND stderr idx=%d job=%s:\n%s",
                        o["index"], terminal.job_id, terminal.stderr,
                    )

        if any_failed is True:
            return 1
        return 0
