"""
.. module:: test_p25c_flow_log_isolation_m3
    :synopsis: Verifies thread-local FlowRuntime log capture is isolated.

The pre-fix implementation attached a fresh ``logging.StreamHandler``
to the root logger for each worker, so a record emitted while two
workers were both running landed in **both** of their capture buffers.
This test stages that exact race: two workflows whose first task is
a long-running ``sleep`` so their windows overlap, with each
workflow's tasks emitting a marker the test can scan for in the
persisted ``log_text``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile
import time

from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.orchestration.flowruntime import (
    FlowRuntime,
    FlowState,
)
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


def _workflow_yaml(*, marker: str) -> str:
    """
        Build a YAML workflow whose tasks emit ``marker`` via
        ``echo`` so the persisted log_text carries an identifiable
        signature. The leading ``sleep 0.4`` widens the worker
        window so the two submissions overlap reliably under a
        2-worker pool.
    """
    rtnval = (
        "name: log-isolation-{0}\n"
        "environment: {{}}\n"
        "parameters: {{}}\n"
        "flow:\n"
        "  - task: sleep\n"
        "    tasktype: automojo.taskplus.tasks.runcommand@RunCommand\n"
        "    command: sleep 0.4\n"
        "  - task: emit\n"
        "    tasktype: automojo.taskplus.tasks.runcommand@RunCommand\n"
        "    command: echo {0}\n"
    ).format(marker)
    return rtnval


def _make_engine() -> Tuple[object, str]:
    """
        File-backed SQLite so worker threads share state with the
        main thread.
    """
    fd, path = tempfile.mkstemp(prefix="pych_p25c_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    return engine, path


def _wait_terminal(*, runtime: FlowRuntime, flow_id: str, deadline_s: float = 10.0) -> str:
    """
        Poll until the submission reaches a terminal state.
    """
    end = time.time() + deadline_s
    last = "MISSING"
    while time.time() < end:
        snapshot = runtime.status(flow_id=flow_id)
        if snapshot is None:
            time.sleep(0.05)
            continue
        last = snapshot.state.value
        if snapshot.state in (FlowState.SUCCEEDED, FlowState.FAILED):
            return last
        time.sleep(0.05)
    return last


def test_concurrent_flow_logs_are_thread_isolated():
    """
    **Feature: P25c thread-local FlowRuntime log capture (M3)**
    **Property: Two workflows running concurrently land their log
    output in their own log_text only — flow A's log contains its
    marker, flow B's log contains its marker, and neither sees the
    other's marker.**
    """
    engine, path = _make_engine()
    factory = sessionmaker(bind=engine)
    runtime = FlowRuntime(session_factory=factory, max_workers=2)
    try:
        flow_a = runtime.submit_workflow_yaml(
            workflow_yaml=_workflow_yaml(marker="alpha-marker-AAAA"),
        )
        flow_b = runtime.submit_workflow_yaml(
            workflow_yaml=_workflow_yaml(marker="bravo-marker-BBBB"),
        )

        terminal_a = _wait_terminal(runtime=runtime, flow_id=flow_a)
        terminal_b = _wait_terminal(runtime=runtime, flow_id=flow_b)
        testbase.assert_equal(terminal_a, "SUCCEEDED")
        testbase.assert_equal(terminal_b, "SUCCEEDED")

        log_a = runtime.read_log(flow_id=flow_a)
        log_b = runtime.read_log(flow_id=flow_b)
        testbase.assert_equal(log_a is not None, True)
        testbase.assert_equal(log_b is not None, True)

        # Each flow's log carries its own marker.
        testbase.assert_equal("alpha-marker-AAAA" in log_a, True)
        testbase.assert_equal("bravo-marker-BBBB" in log_b, True)

        # Neither log carries the other's marker — the cross-
        # contamination bug would otherwise put both markers in
        # both logs.
        testbase.assert_equal("bravo-marker-BBBB" in log_a, False)
        testbase.assert_equal("alpha-marker-AAAA" in log_b, False)
    finally:
        runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_handler_is_removed_on_runtime_shutdown():
    """
    **Feature: P25c thread-local FlowRuntime log capture (M3)**
    **Property: FlowRuntime.shutdown removes the thread-local
    handler from the root logger so test harnesses constructing
    multiple runtimes don't accumulate stale handlers.**
    """
    import logging

    engine, path = _make_engine()
    factory = sessionmaker(bind=engine)

    root = logging.getLogger()
    before = len(root.handlers)

    runtime = FlowRuntime(session_factory=factory, max_workers=1)
    during = len(root.handlers)
    runtime.shutdown(wait=True)
    after = len(root.handlers)

    testbase.assert_equal(during, before + 1)
    testbase.assert_equal(after, before)

    os.unlink(path)
    return
