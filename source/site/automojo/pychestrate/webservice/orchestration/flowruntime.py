"""
.. module:: pychestrate.webservice.orchestration.flowruntime
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Thread-pool runtime that drives :mod:`automojo.taskplus`.

.. moduleauthor:: Automation Mojo LLC

The :class:`FlowRuntime` accepts a
:class:`automojo.taskplus.model.workflow.Workflow` definition (parsed
from YAML), executes it on a :class:`ThreadPoolExecutor`, and tracks
submission state.

Persistence model:

* When a ``session_factory`` is supplied, every state transition
  mirrors to a :class:`FlowSubmissionRecord` row, so submissions
  survive process restart and the REST surface can show historical
  runs. On construction the runtime loads existing rows into its
  in-memory cache.
* Without a ``session_factory`` the runtime falls back to in-memory
  only — useful for unit tests that don't want a DB.

Concurrency model:

* the runtime owns a :class:`concurrent.futures.ThreadPoolExecutor`;
* :func:`submit_workflow_yaml` schedules the workflow on the pool
  and returns immediately with a fresh ``flow_id``;
* the worker thread opens its own SQLAlchemy session (sessions are
  not safe to share across threads), updates the persisted row at
  state transitions, and captures the engine + tasks log output
  into ``log_text``;
* in-memory reads are protected by a lock; DB reads happen on the
  caller's thread via the session_factory.
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
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.orchestration.flowsubmissionrecord import (
    FlowSubmissionRecord,
)


logger = logging.getLogger(__name__)


SessionFactory = Callable[[], DbSession]


class _ThreadLocalLogHandler(logging.Handler):
    """
        Logging handler that routes records into a per-thread
        :class:`io.StringIO` buffer, so the :class:`FlowRuntime`
        worker pool can capture logs without one worker's records
        bleeding into another's persisted ``log_text``.

        Workers call :meth:`attach_buffer` before invoking the
        engine and :meth:`detach_buffer` in the ``finally`` clause
        afterwards. The handler is registered once on the root
        logger when the :class:`FlowRuntime` is constructed and
        removed on :meth:`FlowRuntime.shutdown`.

        Records emitted from threads that haven't attached a buffer
        are dropped silently (the workers are the only producers we
        care to capture).
    """

    def __init__(self):
        """
            Construct a :class:`_ThreadLocalLogHandler`.
        """
        super().__init__(level=logging.DEBUG)
        self._local: threading.local = threading.local()
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s",
            ),
        )
        return

    def attach_buffer(self, *, buffer: io.StringIO) -> None:
        """
            Bind ``buffer`` as this thread's capture target.
        """
        self._local.buffer = buffer
        return

    def detach_buffer(self) -> None:
        """
            Clear this thread's capture target.
        """
        self._local.buffer = None
        return

    def emit(self, record: logging.LogRecord) -> None:
        """
            Append the formatted record to the thread-local buffer
            when one is attached, otherwise drop it.
        """
        buffer = getattr(self._local, "buffer", None)
        if buffer is None:
            return
        try:
            message = self.format(record)
            buffer.write(message)
            buffer.write("\n")
        except Exception:  # noqa: BLE001 — handler must not raise
            self.handleError(record)
        return


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
        Captured state of a single flow submission, as returned to
        callers of :class:`FlowRuntime`.
    """
    flow_id: str
    name: str
    state: FlowState
    submitted_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result_code: Optional[int] = None
    error_text: Optional[str] = None
    actor_user_id: Optional[str] = None


def _isoformat(*, value: Optional[datetime]) -> Optional[str]:
    """
        Render a UTC ``datetime`` as an ISO-8601 string, or None.
    """
    if value is None:
        return None
    rtnval = value.isoformat()
    return rtnval


def _record_to_submission(*, record: FlowSubmissionRecord) -> FlowSubmission:
    """
        Convert a persisted :class:`FlowSubmissionRecord` to the
        public :class:`FlowSubmission` snapshot.
    """
    rtnval = FlowSubmission(
        flow_id=record.flow_id,
        name=record.name,
        state=FlowState(record.state),
        submitted_at=_isoformat(value=record.submitted_at),
        started_at=_isoformat(value=record.started_at),
        completed_at=_isoformat(value=record.completed_at),
        result_code=record.result_code,
        error_text=record.error_text,
        actor_user_id=record.actor_user_id,
    )
    return rtnval


class FlowRuntime:
    """
        Thread-pool-backed runtime for taskplus workflows.

        :param max_workers: Maximum concurrent flow worker threads.
                            Defaults to 4.
        :param session_factory: Optional zero-arg callable returning a
                                fresh ``DbSession``. When supplied,
                                every state transition is mirrored to
                                a :class:`FlowSubmissionRecord` row
                                and existing rows are loaded into the
                                cache on construction.
    """

    def __init__(
            self,
            *,
            max_workers: int = 4,
            session_factory: Optional[SessionFactory] = None,
        ):
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
        self._session_factory: Optional[SessionFactory] = session_factory

        # Single thread-local handler shared by every worker, attached
        # to the root logger for the runtime's lifetime. Per-worker
        # buffers are bound via :meth:`_ThreadLocalLogHandler.attach_buffer`
        # so concurrent flows don't cross-contaminate each other's
        # persisted log_text.
        #
        # Defensive: remove any stale ``_ThreadLocalLogHandler``
        # already attached to root from a prior runtime that
        # didn't shut down cleanly (e.g. a test that crashed
        # before its ``finally`` ran). Otherwise the stale
        # handler carries pre-attach state — its threading.local
        # may have buffers from worker threads we've reused, and
        # records emitted on those threads land in *both*
        # handlers, polluting the new runtime's log_text.
        self._log_handler: _ThreadLocalLogHandler = _ThreadLocalLogHandler()
        root_logger = logging.getLogger()
        for stale in [
            h for h in root_logger.handlers
            if isinstance(h, _ThreadLocalLogHandler)
        ]:
            root_logger.removeHandler(stale)
        root_logger.addHandler(self._log_handler)
        # The root logger defaults to WARNING; ``RunCommand`` and
        # ``RemoteCommand`` log progress at INFO. Without this
        # adjustment the records are filtered before they reach
        # the per-thread handler and ``log_text`` ends up empty.
        # We remember the prior level so shutdown can restore it
        # rather than leaving the process noisier than we found
        # it.
        self._prior_root_level: int = root_logger.level
        if (
            root_logger.level == logging.NOTSET
            or root_logger.level > logging.INFO
        ):
            root_logger.setLevel(logging.INFO)

        if session_factory is not None:
            self._load_existing_submissions()
        return

    @property
    def max_workers(self) -> int:
        """
            Configured maximum number of concurrent worker threads.
        """
        rtnval = self._max_workers
        return rtnval

    @property
    def is_persistent(self) -> bool:
        """
            Whether the runtime mirrors writes to a DB.
        """
        rtnval = self._session_factory is not None
        return rtnval

    def submit_workflow_yaml(
            self,
            *,
            workflow_yaml: str,
            actor_user_id: Optional[str] = None,
        ) -> str:
        """
            Parse and submit a YAML workflow.
        """
        from automojo.taskplus.model.workflow import Workflow

        workflow = Workflow.parse(workflow_stream=io.StringIO(workflow_yaml))
        flow_id = self._submit_workflow(
            workflow=workflow,
            workflow_yaml=workflow_yaml,
            actor_user_id=actor_user_id,
        )
        return flow_id

    def submit_workflow(
            self,
            *,
            workflow: Any,
            workflow_yaml: str = "",
            actor_user_id: Optional[str] = None,
        ) -> str:
        """
            Submit an already-parsed :class:`Workflow`.
        """
        flow_id = self._submit_workflow(
            workflow=workflow,
            workflow_yaml=workflow_yaml,
            actor_user_id=actor_user_id,
        )
        return flow_id

    def status(self, *, flow_id: str) -> Optional[FlowSubmission]:
        """
            Read a submission's current state from the cache, falling
            through to the DB when persistence is enabled and the
            entry isn't cached.
        """
        with self._lock:
            cached = self._submissions.get(flow_id, None)
            if cached is not None:
                rtnval = self._copy_submission(submission=cached)
                return rtnval

        if self._session_factory is not None:
            db_session = self._session_factory()
            try:
                record = (
                    db_session.query(FlowSubmissionRecord)
                    .filter(FlowSubmissionRecord.flow_id == flow_id)
                    .first()
                )
                if record is None:
                    return None
                submission = _record_to_submission(record=record)
            finally:
                db_session.close()
            with self._lock:
                self._submissions[flow_id] = submission
            rtnval = self._copy_submission(submission=submission)
            return rtnval

        return None

    def list_submissions(self) -> List[FlowSubmission]:
        """
            Return every tracked submission, ordered by submitted_at
            descending. Reads from the DB when persistence is enabled
            so historical rows are included.
        """
        if self._session_factory is not None:
            db_session = self._session_factory()
            try:
                rows = (
                    db_session.query(FlowSubmissionRecord)
                    .order_by(FlowSubmissionRecord.submitted_at.desc())
                    .all()
                )
                snapshots = [_record_to_submission(record=r) for r in rows]
            finally:
                db_session.close()
            return snapshots

        with self._lock:
            entries = list(self._submissions.values())
        entries.sort(
            key=lambda s: s.submitted_at if s.submitted_at else "",
            reverse=True,
        )
        rtnval: List[FlowSubmission] = []
        for entry in entries:
            rtnval.append(self._copy_submission(submission=entry))
        return rtnval

    def read_log(self, *, flow_id: str) -> Optional[str]:
        """
            Return captured log output for ``flow_id``, or ``None``
            when the submission is unknown. In-memory-only mode never
            returns log text (logs only persist when a DB is wired).
        """
        if self._session_factory is None:
            return None
        db_session = self._session_factory()
        try:
            record = (
                db_session.query(FlowSubmissionRecord)
                .filter(FlowSubmissionRecord.flow_id == flow_id)
                .first()
            )
            if record is None:
                return None
            rtnval = record.log_text
            return rtnval
        finally:
            db_session.close()

    def shutdown(self, *, wait: bool = True) -> None:
        """
            Drain the worker pool and detach the per-thread log
            handler from the root logger. Restore the root
            logger level we found at construction time so we
            don't leave the process noisier than when we
            arrived.
        """
        self._executor.shutdown(wait=wait)
        root_logger = logging.getLogger()
        try:
            root_logger.removeHandler(self._log_handler)
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
        try:
            root_logger.setLevel(self._prior_root_level)
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
        return

    def _copy_submission(
            self, *, submission: FlowSubmission
        ) -> FlowSubmission:
        """
            Return a shallow copy so the caller can't mutate cache
            state through the reference.
        """
        rtnval = FlowSubmission(
            flow_id=submission.flow_id,
            name=submission.name,
            state=submission.state,
            submitted_at=submission.submitted_at,
            started_at=submission.started_at,
            completed_at=submission.completed_at,
            result_code=submission.result_code,
            error_text=submission.error_text,
            actor_user_id=submission.actor_user_id,
        )
        return rtnval

    def _load_existing_submissions(self) -> None:
        """
            Populate the in-memory cache from existing
            :class:`FlowSubmissionRecord` rows. Called once at
            construction when a ``session_factory`` is wired.
        """
        db_session = self._session_factory()
        try:
            rows = (
                db_session.query(FlowSubmissionRecord)
                .order_by(FlowSubmissionRecord.submitted_at.desc())
                .all()
            )
            for row in rows:
                snapshot = _record_to_submission(record=row)
                self._submissions[row.flow_id] = snapshot
        finally:
            db_session.close()
        return

    def _submit_workflow(
            self,
            *,
            workflow: Any,
            workflow_yaml: str,
            actor_user_id: Optional[str],
        ) -> str:
        """
            Register a submission and schedule the worker.
        """
        flow_id = str(uuid.uuid4())
        name_attr = getattr(workflow, "name", None)
        if name_attr is None:
            name = "<unnamed>"
        else:
            name = str(name_attr)

        submitted_at_dt = datetime.now(timezone.utc)
        submitted_at = submitted_at_dt.isoformat()
        submission = FlowSubmission(
            flow_id=flow_id,
            name=name,
            state=FlowState.PENDING,
            submitted_at=submitted_at,
            actor_user_id=actor_user_id,
        )
        with self._lock:
            self._submissions[flow_id] = submission

        if self._session_factory is not None:
            db_session = self._session_factory()
            try:
                record = FlowSubmissionRecord(
                    flow_id=flow_id,
                    name=name,
                    state=FlowState.PENDING.value,
                    submitted_at=submitted_at_dt,
                    workflow_yaml=workflow_yaml,
                    log_text="",
                    actor_user_id=actor_user_id,
                )
                db_session.add(record)
                db_session.commit()
            finally:
                db_session.close()

        future = self._executor.submit(
            self._run_workflow_worker, flow_id, workflow,
        )
        with self._lock:
            self._futures[flow_id] = future
        rtnval = flow_id
        return rtnval

    def _run_workflow_worker(self, flow_id: str, workflow: Any) -> int:
        """
            Worker thread entry point.
        """
        from automojo.taskplus.model.flowengine import FlowEngine

        # Bind a thread-local capture buffer to the runtime's shared
        # log handler so this worker's records land in log_text
        # without cross-contaminating concurrent workers.
        log_buffer = io.StringIO()
        self._log_handler.attach_buffer(buffer=log_buffer)

        # Bind the session_factory and flow_id on thread-locals so
        # RemoteCommand tasks running inside this worker can
        # dispatch jobs through the worker queue (and acquire
        # exclusive leases keyed to this flow) without us having
        # to thread the factory + flow_id through every taskplus
        # call.
        from automojo.pychestrate.webservice.orchestration.remotecommand import (
            set_flow_id,
            set_session_factory,
        )
        set_session_factory(factory=self._session_factory)
        set_flow_id(flow_id=flow_id)

        started_at_dt = datetime.now(timezone.utc)
        with self._lock:
            submission = self._submissions[flow_id]
            submission.state = FlowState.RUNNING
            submission.started_at = started_at_dt.isoformat()
        self._persist_state_transition(
            flow_id=flow_id,
            state=FlowState.RUNNING.value,
            started_at=started_at_dt,
        )

        result_code = 1
        error_text: Optional[str] = None
        try:
            engine = FlowEngine()
            result_code = int(engine.execute(workflow=workflow))
        except Exception as exc:
            error_text = str(exc)
            logger.exception(
                "flow_runtime.worker.crashed flow_id=%s", flow_id,
            )
            result_code = 1
        finally:
            # Release every worker lease held by this flow so a
            # crashed (or successful) flow doesn't leave hardware
            # reserved.
            self._release_flow_leases(flow_id=flow_id)
            set_flow_id(flow_id=None)
            self._log_handler.detach_buffer()

        completed_at_dt = datetime.now(timezone.utc)
        if error_text is not None:
            terminal = FlowState.FAILED
        elif result_code == 0:
            terminal = FlowState.SUCCEEDED
        else:
            terminal = FlowState.FAILED

        with self._lock:
            sub = self._submissions[flow_id]
            sub.state = terminal
            sub.completed_at = completed_at_dt.isoformat()
            sub.result_code = result_code
            sub.error_text = error_text

        self._persist_terminal_transition(
            flow_id=flow_id,
            state=terminal.value,
            completed_at=completed_at_dt,
            result_code=result_code,
            error_text=error_text,
            log_text=log_buffer.getvalue(),
        )

        rtnval = result_code
        return rtnval

    def _release_flow_leases(self, *, flow_id: str) -> None:
        """
            Release every worker lease this flow currently holds.
            Called from the worker-thread ``finally`` so a crash
            mid-flow doesn't leave hardware reserved indefinitely.
            No-op when the runtime has no session_factory (in-memory
            test mode) — leases live in the DB.
        """
        if self._session_factory is None:
            return
        try:
            from automojo.pychestrate.webservice.workers import (
                service as worker_service,
            )
            holder = "flow:{0}".format(flow_id)
            db_session = self._session_factory()
            try:
                worker_service.release_all_leases_for_holder(
                    db_session=db_session, holder=holder,
                )
            finally:
                db_session.close()
        except Exception:
            logger.exception(
                "flow_runtime.lease_release_failed flow_id=%s",
                flow_id,
            )
        return

    def _persist_state_transition(
            self,
            *,
            flow_id: str,
            state: str,
            started_at: Optional[datetime],
        ) -> None:
        """
            Persist a non-terminal state change.
        """
        if self._session_factory is None:
            return
        db_session = self._session_factory()
        try:
            record = (
                db_session.query(FlowSubmissionRecord)
                .filter(FlowSubmissionRecord.flow_id == flow_id)
                .first()
            )
            if record is None:
                return
            record.state = state
            if started_at is not None:
                record.started_at = started_at
            db_session.commit()
        finally:
            db_session.close()
        return

    def _persist_terminal_transition(
            self,
            *,
            flow_id: str,
            state: str,
            completed_at: datetime,
            result_code: int,
            error_text: Optional[str],
            log_text: str,
        ) -> None:
        """
            Persist a terminal SUCCEEDED / FAILED transition.
        """
        if self._session_factory is None:
            return
        db_session = self._session_factory()
        try:
            record = (
                db_session.query(FlowSubmissionRecord)
                .filter(FlowSubmissionRecord.flow_id == flow_id)
                .first()
            )
            if record is None:
                return
            record.state = state
            record.completed_at = completed_at
            record.result_code = result_code
            record.error_text = error_text
            record.log_text = log_text
            db_session.commit()
        finally:
            db_session.close()
        return


# Module-level singleton kept for backwards compatibility with
# callers that don't yet wire a session_factory. This instance is
# in-memory only; production deployments should construct a runtime
# with a session_factory and inject it via
# ``request.flow_runtime``.
default_flow_runtime: FlowRuntime = FlowRuntime()
