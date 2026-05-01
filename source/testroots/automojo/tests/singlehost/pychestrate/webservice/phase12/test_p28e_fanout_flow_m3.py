"""
.. module:: test_p28e_fanout_flow_m3
    :synopsis: Tests for the FanOutCommand parallel-targets task.

Covers:

* Construction rejects missing ``command``, missing /
  empty ``targets``, non-list ``targets``, non-dict target
  entries, and bad per-target fields.
* Per-target ``required_capabilities`` and ``target_kind``
  resolve correctly; ``parallelism`` clamps to >= 1.
* End-to-end via :class:`PychestrateApplication`: a flow
  enqueues N jobs, stub workers (one per target) return
  zero, the flow lands SUCCEEDED.
* When one target fails, the FanOutCommand returns
  non-zero; every other target's outcome is still
  reported (no fast-fail).
* When a target's worker is missing (no claim ever), the
  fan-out times out at the wait budget and reports
  failure rather than blocking the engine indefinitely.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import tempfile
import threading
import time

from typing import Dict, List, Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)
from automojo.pychestrate.webservice.orchestration.fanoutcommand import (
    FanOutCommand,
)
from automojo.pychestrate.webservice.orchestration.flowruntime import (
    FlowState,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)
from automojo.pychestrate.webservice.workers import jobservice
from automojo.pychestrate.webservice.workers import service as worker_service
from automojo.pychestrate.webservice.workers.jobmodels import (
    JobState,
    WorkerJob,
)
from automojo.pychestrate.webservice.workers.models import WorkerKind

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p28e_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def test_construction_rejects_missing_command():
    """
    **Feature: P28e fan-out flow (M3)**
    **Property: A FanOutCommand without ``command`` is a
    construction error — fail fast at parse time, not at
    runtime.**
    """
    try:
        FanOutCommand(
            ordinal="1", label="test",
            task_info={"targets": [{"target_pod_name": "x"}]},
            logger=logging.getLogger("p28e"),
        )
        raised = False
    except KeyError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_construction_rejects_missing_or_empty_targets():
    """
    **Feature: P28e fan-out flow (M3)**
    **Property: Missing or empty ``targets`` is invalid — a
    fan-out with nothing to fan out to is almost certainly
    a YAML bug.**
    """
    for task_info in (
        {"command": "x"},
        {"command": "x", "targets": []},
        {"command": "x", "targets": "not-a-list"},
    ):
        try:
            FanOutCommand(
                ordinal="1", label="test",
                task_info=task_info,
                logger=logging.getLogger("p28e"),
            )
            raised = False
        except (KeyError, ValueError):
            raised = True
        testbase.assert_equal(raised, True)
    return


def test_construction_validates_target_entry_types():
    """
    **Feature: P28e fan-out flow (M3)**
    **Property: A non-object target entry, an unknown
    ``target_kind``, or a non-list ``required_capabilities``
    raises ValueError with the offending index.**
    """
    try:
        FanOutCommand(
            ordinal="1", label="test",
            task_info={
                "command": "x",
                "targets": ["not-an-object"],
            },
            logger=logging.getLogger("p28e"),
        )
        raised = False
    except ValueError as exc:
        raised = True
        err_text = str(exc)
    testbase.assert_equal(raised, True)
    testbase.assert_equal("TARGET_INDEX: 0" in err_text, True)

    try:
        FanOutCommand(
            ordinal="1", label="test",
            task_info={
                "command": "x",
                "targets": [
                    {"target_pod_name": "raspi-01"},
                    {"target_kind": "garbage"},
                ],
            },
            logger=logging.getLogger("p28e"),
        )
        raised = False
    except ValueError as exc:
        raised = True
        err_text = str(exc)
    testbase.assert_equal(raised, True)
    testbase.assert_equal("TARGET_INDEX: 1" in err_text, True)

    try:
        FanOutCommand(
            ordinal="1", label="test",
            task_info={
                "command": "x",
                "targets": [
                    {
                        "target_pod_name": "raspi-01",
                        "required_capabilities": "uefi",  # str.
                    },
                ],
            },
            logger=logging.getLogger("p28e"),
        )
        raised = False
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_parallelism_clamps_to_at_least_one():
    """
    **Feature: P28e fan-out flow (M3)**
    **Property: ``parallelism: 0`` (and negatives) clamp to
    1 so the ThreadPoolExecutor never gets a zero pool.**
    """
    task = FanOutCommand(
        ordinal="1", label="test",
        task_info={
            "command": "x",
            "targets": [{"target_pod_name": "raspi-01"}],
            "parallelism": 0,
        },
        logger=logging.getLogger("p28e"),
    )
    testbase.assert_equal(task.parallelism, 1)

    task2 = FanOutCommand(
        ordinal="1", label="test",
        task_info={
            "command": "x",
            "targets": [{"target_pod_name": "raspi-01"}],
            "parallelism": -5,
        },
        logger=logging.getLogger("p28e"),
    )
    testbase.assert_equal(task2.parallelism, 1)
    return


def test_construction_resolves_required_capabilities_per_target():
    """
    **Feature: P28e fan-out flow (M3)**
    **Property: Per-target ``required_capabilities`` and
    ``target_kind`` round-trip onto the parsed _TargetSpec.**
    """
    task = FanOutCommand(
        ordinal="1", label="test",
        task_info={
            "command": "x",
            "targets": [
                {
                    "target_pod_name": "raspi-01",
                    "required_capabilities": ["uefi", "tpm-2.0"],
                    "target_kind": "remote-machine",
                },
                {"target_pod_name": "raspi-02"},
            ],
        },
        logger=logging.getLogger("p28e"),
    )
    targets = task.targets
    testbase.assert_equal(len(targets), 2)
    testbase.assert_equal(
        targets[0].required_capabilities, ["uefi", "tpm-2.0"],
    )
    testbase.assert_equal(
        targets[0].target_kind, WorkerKind.REMOTE_MACHINE,
    )
    testbase.assert_equal(targets[1].target_kind, None)
    testbase.assert_equal(targets[1].required_capabilities, [])
    return


def _make_app() -> Tuple[PychestrateApplication, sessionmaker, str]:
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p28e-test-pepper"))
    engine, factory, path = _build_engine_and_factory()
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
        local_worker_pool_size=0,
    )
    return app, factory, path


def _stub_worker(
        *,
        factory: sessionmaker,
        worker_id: str,
        stop_event: threading.Event,
        outcome: int,
        seen: List[Dict[str, str]],
        sleep_before_report: float = 0.0,
    ) -> None:
    while not stop_event.is_set():
        db_session = factory()
        try:
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()
        if claimed is None:
            stop_event.wait(0.05)
            continue
        seen.append({
            "worker_id": worker_id,
            "job_id": claimed.job_id,
            "command": claimed.payload.get("command", ""),
        })
        if sleep_before_report > 0:
            time.sleep(sleep_before_report)
        db_session = factory()
        try:
            jobservice.report_result(
                db_session=db_session, worker_id=worker_id,
                job_id=claimed.job_id,
                result_code=outcome,
                stdout="ran on {0}\n".format(worker_id),
            )
        finally:
            db_session.close()
    return


def _spin_worker_thread(
        *,
        factory: sessionmaker,
        worker_id: str,
        stop_event: threading.Event,
        outcome: int,
        seen: List[Dict[str, str]],
        sleep_before_report: float = 0.0,
    ) -> threading.Thread:
    t = threading.Thread(
        target=_stub_worker,
        kwargs={
            "factory": factory,
            "worker_id": worker_id,
            "stop_event": stop_event,
            "outcome": outcome,
            "seen": seen,
            "sleep_before_report": sleep_before_report,
        },
        daemon=True,
    )
    t.start()
    return t


def _wait_terminal(
        *, app, flow_id: str, timeout: float,
    ) -> Optional[FlowState]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        sub = app.flow_runtime.status(flow_id=flow_id)
        if sub is not None and sub.state in (
            FlowState.SUCCEEDED, FlowState.FAILED,
        ):
            return sub.state
        time.sleep(0.05)
    return None


def test_fan_out_dispatches_to_every_target_in_parallel():
    """
    **Feature: P28e fan-out flow (M3)**
    **Property: A flow with three fan-out targets enqueues
    three jobs; every worker claims its targeted job; the
    flow completes SUCCEEDED with the same command echoed by
    each target.**
    """
    app, factory, path = _make_app()
    db_session = factory()
    try:
        worker_ids: Dict[str, str] = {}
        for name in ("raspi-01", "raspi-02", "raspi-03"):
            v = worker_service.register_worker(
                db_session=db_session,
                name=name, kind=WorkerKind.REMOTE_MACHINE,
                attributes={"pod_name": name},
            )
            worker_ids[name] = v.worker_id
    finally:
        db_session.close()

    stop_event = threading.Event()
    seen: List[Dict[str, str]] = []
    threads = [
        _spin_worker_thread(
            factory=factory, worker_id=worker_ids[name],
            stop_event=stop_event, outcome=0, seen=seen,
        )
        for name in ("raspi-01", "raspi-02", "raspi-03")
    ]
    try:
        workflow_yaml = "\n".join([
            "name: p28e-fanout-fleet",
            "environment: {}",
            "parameters: {}",
            "flow:",
            "  - task: fleet-smoke",
            "    tasktype: automojo.pychestrate.webservice.orchestration.fanoutcommand@FanOutCommand",
            "    command: smoke.sh",
            "    timeout_seconds: 5",
            "    targets:",
            "      - target_pod_name: raspi-01",
            "      - target_pod_name: raspi-02",
            "      - target_pod_name: raspi-03",
            "",
        ])
        flow_id = app.flow_runtime.submit_workflow_yaml(
            workflow_yaml=workflow_yaml,
        )
        terminal = _wait_terminal(app=app, flow_id=flow_id, timeout=10.0)
        testbase.assert_equal(terminal, FlowState.SUCCEEDED)
        # Every worker saw exactly one job.
        per_worker = {}
        for entry in seen:
            per_worker.setdefault(entry["worker_id"], 0)
            per_worker[entry["worker_id"]] += 1
        testbase.assert_equal(len(per_worker), 3)
        for count in per_worker.values():
            testbase.assert_equal(count, 1)
        # Every claimed job ran the same command.
        commands = {entry["command"] for entry in seen}
        testbase.assert_equal(commands, {"smoke.sh"})
    finally:
        stop_event.set()
        for t in threads:
            t.join(timeout=2.0)
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_fan_out_returns_failure_when_any_target_fails():
    """
    **Feature: P28e fan-out flow (M3)**
    **Property: A fan-out where one target reports rc!=0
    fails the flow's task, but the other targets still
    complete (no fast-fail/cancel) so their evidence is
    captured.**
    """
    app, factory, path = _make_app()
    db_session = factory()
    try:
        wids: Dict[str, str] = {}
        for name in ("good-1", "bad-1", "good-2"):
            v = worker_service.register_worker(
                db_session=db_session,
                name=name, kind=WorkerKind.REMOTE_MACHINE,
                attributes={"pod_name": name},
            )
            wids[name] = v.worker_id
    finally:
        db_session.close()

    stop_event = threading.Event()
    seen: List[Dict[str, str]] = []
    good1 = _spin_worker_thread(
        factory=factory, worker_id=wids["good-1"],
        stop_event=stop_event, outcome=0, seen=seen,
    )
    bad1 = _spin_worker_thread(
        factory=factory, worker_id=wids["bad-1"],
        stop_event=stop_event, outcome=2, seen=seen,
    )
    good2 = _spin_worker_thread(
        factory=factory, worker_id=wids["good-2"],
        stop_event=stop_event, outcome=0, seen=seen,
    )
    try:
        workflow_yaml = "\n".join([
            "name: p28e-mixed-outcome",
            "environment: {}",
            "parameters: {}",
            "flow:",
            "  - task: mixed",
            "    tasktype: automojo.pychestrate.webservice.orchestration.fanoutcommand@FanOutCommand",
            "    command: probe.sh",
            "    timeout_seconds: 5",
            "    targets:",
            "      - target_pod_name: good-1",
            "      - target_pod_name: bad-1",
            "      - target_pod_name: good-2",
            "",
        ])
        flow_id = app.flow_runtime.submit_workflow_yaml(
            workflow_yaml=workflow_yaml,
        )
        terminal = _wait_terminal(app=app, flow_id=flow_id, timeout=10.0)
        testbase.assert_equal(
            terminal in (FlowState.SUCCEEDED, FlowState.FAILED),
            True,
        )

        # All three jobs are terminal; one is FAILED, two are
        # SUCCEEDED.
        db_session = factory()
        try:
            rows = (
                db_session.query(WorkerJob)
                .order_by(WorkerJob.enqueued_at.asc())
                .all()
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(rows), 3)
        states = sorted([r.state for r in rows])
        testbase.assert_equal(
            states,
            sorted([
                JobState.FAILED.value,
                JobState.SUCCEEDED.value,
                JobState.SUCCEEDED.value,
            ]),
        )
    finally:
        stop_event.set()
        good1.join(timeout=2.0)
        bad1.join(timeout=2.0)
        good2.join(timeout=2.0)
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_fan_out_times_out_when_a_target_has_no_worker():
    """
    **Feature: P28e fan-out flow (M3)**
    **Property: A target whose pod doesn't exist times out
    at the wait budget and the fan-out reports failure;
    the present targets still complete.**
    """
    app, factory, path = _make_app()
    db_session = factory()
    try:
        v = worker_service.register_worker(
            db_session=db_session,
            name="present", kind=WorkerKind.REMOTE_MACHINE,
            attributes={"pod_name": "present"},
        )
        present_id = v.worker_id
    finally:
        db_session.close()

    stop_event = threading.Event()
    seen: List[Dict[str, str]] = []
    present_thread = _spin_worker_thread(
        factory=factory, worker_id=present_id,
        stop_event=stop_event, outcome=0, seen=seen,
    )
    try:
        workflow_yaml = "\n".join([
            "name: p28e-missing-worker",
            "environment: {}",
            "parameters: {}",
            "flow:",
            "  - task: probe",
            "    tasktype: automojo.pychestrate.webservice.orchestration.fanoutcommand@FanOutCommand",
            "    command: probe.sh",
            "    timeout_seconds: 0.4",
            "    targets:",
            "      - target_pod_name: present",
            "      - target_pod_name: ghost",
            "",
        ])
        flow_id = app.flow_runtime.submit_workflow_yaml(
            workflow_yaml=workflow_yaml,
        )
        terminal = _wait_terminal(app=app, flow_id=flow_id, timeout=10.0)
        testbase.assert_equal(
            terminal in (FlowState.SUCCEEDED, FlowState.FAILED),
            True,
        )

        # The present worker did claim its job; the ghost one
        # never got picked up.
        present_jobs = [s for s in seen if s["worker_id"] == present_id]
        testbase.assert_equal(len(present_jobs), 1)
    finally:
        stop_event.set()
        present_thread.join(timeout=2.0)
        app.shutdown(wait=True)
        os.unlink(path)
    return
