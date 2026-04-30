"""
.. module:: pychestrate.webservice.orchestration.flowruntime
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-memory flow runtime that drives :mod:`automojo.taskplus`.

.. moduleauthor:: Automation Mojo LLC

The :class:`FlowRuntime` is a thread-pool-backed in-process runtime
that accepts a :class:`automojo.taskplus.model.workflow.Workflow`
definition (parsed from YAML), executes it through
:class:`automojo.taskplus.model.flowengine.FlowEngine`, and tracks the
submission's state so the REST surface can poll for status.

Submissions are held in memory only; they do not survive a process
restart. Persistence to the pychestrate DB is a deliberate follow-up.

Concurrency model:

* the runtime owns a :class:`concurrent.futures.ThreadPoolExecutor`;
* :func:`submit` schedules the workflow on the pool and returns
  immediately with a fresh ``flow_id``;
* :func:`status` reads from the in-memory dict — safe for concurrent
  readers because each :class:`FlowSubmission` is mutated only by the
  worker thread that owns it;
* :func:`shutdown` drains the pool with a configurable timeout (used
  by tests to avoid leaking threads).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import logging
import threading
import uuid

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class FlowState(str, Enum):
    """
        Lifecycle state of a :class:`FlowSubmission`.
    """
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass
class FlowSubmission:
    """
        Captured state of a single flow submission.

        :param flow_id: Server-generated identifier for the submission.
        :param name: Workflow name (mirrors the ``name`` element of the
                     YAML doc; falls back to "<unnamed>" when absent).
        :param state: Current lifecycle state.
        :param submitted_at: ISO-8601 wall-clock timestamp when
                             :func:`FlowRuntime.submit` was called.
        :param started_at: ISO-8601 timestamp when the worker thread
                           picked up the submission. ``None`` until the
                           worker starts.
        :param completed_at: ISO-8601 timestamp when execution
                             finished. ``None`` until the flow exits.
        :param result_code: ``0`` on success, ``1`` on failure
                            (taskplus convention). ``None`` while the
                            flow is in PENDING / RUNNING.
        :param error_text: Stringified exception when the worker
                           crashed, otherwise ``None``.
    """
    flow_id: str
    name: str
    state: FlowState
    submitted_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result_code: Optional[int] = None
    error_text: Optional[str] = None


class FlowRuntime:
    """
        Thread-pool-backed in-process runtime for taskplus workflows.

        :param max_workers: Maximum number of concurrent flow worker
                            threads. Defaults to 4.
    """

    def __init__(self, *, max_workers: int = 4):
        """
            Construct a :class:`FlowRuntime`.
        """
        self._submissions: Dict[str, FlowSubmission] = {}
        self._futures: Dict[str, Future] = {}
        self._lock: threading.Lock = threading.Lock()
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="pychestrate-flow",
        )
        self._max_workers: int = max_workers
        return

    @property
    def max_workers(self) -> int:
        """
            Configured maximum number of concurrent worker threads.

            :returns: The integer worker count.
        """
        rtnval = self._max_workers
        return rtnval

    def submit_workflow_yaml(self, *, workflow_yaml: str) -> str:
        """
            Parse a YAML workflow document and submit it for execution.

            :param workflow_yaml: The full YAML document as a string.

            :returns: The newly issued ``flow_id``.

            :raises automojo.errors.exceptions.ConfigurationError: When
                    the YAML doc is missing a required field (raised
                    by :class:`Workflow.parse`).
        """
        # Imported lazily so the rest of the service can be imported
        # in environments without taskplus installed.
        from automojo.taskplus.model.workflow import Workflow

        workflow = Workflow.parse(workflow_stream=io.StringIO(workflow_yaml))
        flow_id = self._submit_workflow(workflow=workflow)
        return flow_id

    def submit_workflow(self, *, workflow: Any) -> str:
        """
            Submit an already-parsed :class:`Workflow` for execution.

            :param workflow: The :class:`automojo.taskplus.model.workflow.Workflow`.

            :returns: The newly issued ``flow_id``.
        """
        flow_id = self._submit_workflow(workflow=workflow)
        return flow_id

    def status(self, *, flow_id: str) -> Optional[FlowSubmission]:
        """
            Read a submission's current state.

            :param flow_id: Identifier returned by :func:`submit_workflow_yaml`.

            :returns: A :class:`FlowSubmission` snapshot, or ``None``
                      when the id is unknown.
        """
        with self._lock:
            submission = self._submissions.get(flow_id, None)
            if submission is None:
                return None
            # Return a shallow copy so the caller can't mutate
            # internal state through the reference.
            rtnval = FlowSubmission(
                flow_id=submission.flow_id,
                name=submission.name,
                state=submission.state,
                submitted_at=submission.submitted_at,
                started_at=submission.started_at,
                completed_at=submission.completed_at,
                result_code=submission.result_code,
                error_text=submission.error_text,
            )
        return rtnval

    def list_submissions(self) -> List[FlowSubmission]:
        """
            Return every tracked submission.

            :returns: A list of :class:`FlowSubmission` snapshots,
                      ordered by ``submitted_at`` descending.
        """
        with self._lock:
            entries = list(self._submissions.values())
        entries.sort(key=lambda s: s.submitted_at, reverse=True)
        rtnval: List[FlowSubmission] = []
        for entry in entries:
            rtnval.append(FlowSubmission(
                flow_id=entry.flow_id,
                name=entry.name,
                state=entry.state,
                submitted_at=entry.submitted_at,
                started_at=entry.started_at,
                completed_at=entry.completed_at,
                result_code=entry.result_code,
                error_text=entry.error_text,
            ))
        return rtnval

    def shutdown(self, *, wait: bool = True) -> None:
        """
            Drain the worker pool.

            :param wait: When ``True`` (default) block until in-flight
                         workers complete; when ``False`` return
                         immediately.
        """
        self._executor.shutdown(wait=wait)
        return

    def _submit_workflow(self, *, workflow: Any) -> str:
        """
            Internal helper that registers a submission and schedules
            the worker. Centralized so both YAML and pre-parsed
            submissions share the bookkeeping.
        """
        flow_id = str(uuid.uuid4())
        name_attr = getattr(workflow, "name", None)
        if name_attr is None:
            name = "<unnamed>"
        else:
            name = str(name_attr)

        submitted_at = datetime.now(timezone.utc).isoformat()
        submission = FlowSubmission(
            flow_id=flow_id,
            name=name,
            state=FlowState.PENDING,
            submitted_at=submitted_at,
        )
        with self._lock:
            self._submissions[flow_id] = submission

        future = self._executor.submit(
            self._run_workflow_worker, flow_id, workflow,
        )
        with self._lock:
            self._futures[flow_id] = future
        rtnval = flow_id
        return rtnval

    def _run_workflow_worker(self, flow_id: str, workflow: Any) -> int:
        """
            Worker thread entry point. Updates the submission state as
            the flow progresses, executes via
            :class:`automojo.taskplus.model.flowengine.FlowEngine`,
            and records the result.
        """
        # Imported lazily so unit tests that exercise the runtime can
        # do so without requiring taskplus to be installed.
        from automojo.taskplus.model.flowengine import FlowEngine

        with self._lock:
            submission = self._submissions[flow_id]
            submission.state = FlowState.RUNNING
            submission.started_at = datetime.now(timezone.utc).isoformat()

        try:
            engine = FlowEngine()
            result_code = engine.execute(workflow=workflow)
        except Exception as exc:
            with self._lock:
                completed_submission = self._submissions[flow_id]
                completed_submission.state = FlowState.FAILED
                completed_submission.completed_at = (
                    datetime.now(timezone.utc).isoformat()
                )
                completed_submission.result_code = 1
                completed_submission.error_text = str(exc)
            logger.exception(
                "flow_runtime.worker.crashed flow_id=%s", flow_id,
            )
            return 1

        with self._lock:
            completed_submission = self._submissions[flow_id]
            completed_submission.completed_at = (
                datetime.now(timezone.utc).isoformat()
            )
            completed_submission.result_code = int(result_code)
            if int(result_code) == 0:
                completed_submission.state = FlowState.SUCCEEDED
            else:
                completed_submission.state = FlowState.FAILED

        rtnval = int(result_code)
        return rtnval


# Module-level singleton. The bootstrap module reuses this instance so
# the REST surface and any other consumer share one runtime.
default_flow_runtime: FlowRuntime = FlowRuntime()
