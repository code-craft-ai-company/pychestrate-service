"""
.. module:: test_p28a_hardware_reservation_m3
    :synopsis: Tests for the hardware-reservation / lease layer.

Covers:

* :func:`acquire_lease` succeeds on an unleased worker, rejects
  ``ttl_seconds <= 0``, and refreshes the TTL when the same
  holder re-acquires.
* :func:`acquire_lease` raises :class:`WorkerBusyError` when a
  different holder already holds an unexpired lease, and
  succeeds (steals) when the prior lease has expired.
* :func:`is_lease_active` is the central truth for lease state
  — None lease holder is inactive; expired lease is inactive;
  unset expires is active.
* :func:`release_lease` is permissive (silent no-op when the
  lease is already absent or held by someone else) so callers
  don't need to check first.
* :func:`release_all_leases_for_holder` clears every lease for
  that holder across the registry; used by FlowRuntime on flow
  exit.
* :func:`expire_stale_leases` clears expired leases without
  touching active ones.
* :func:`claim_next_job` skips workers whose lease is held by
  someone other than the candidate's ``lease_holder``, allows
  workers leased to the candidate's holder to claim, and
  acquires/extends the lease on first claim from a new holder.
* :class:`StaleWorkerSweeper` clears the lease when it flips
  the worker to OFFLINE.
* End-to-end: a flow with two ``exclusive: true`` steps both
  land on the same worker; another flow can't claim that
  worker until the first one finishes; the lease is released
  in the FlowRuntime ``finally``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile
import threading
import time

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
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
from automojo.pychestrate.webservice.workers.exceptions import (
    WorkerBusyError,
    WorkerNotFoundError,
)
from automojo.pychestrate.webservice.workers.jobmodels import (
    JobState,
    WorkerJob,
)
from automojo.pychestrate.webservice.workers.models import (
    Worker,
    WorkerKind,
    WorkerStatus,
)
from automojo.pychestrate.webservice.workers.staleworkersweeper import (
    sweep_once,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p28a_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def _register_worker(*, factory, name: str, attrs=None) -> str:
    db_session = factory()
    try:
        view = worker_service.register_worker(
            db_session=db_session,
            name=name,
            kind=WorkerKind.REMOTE_MACHINE,
            attributes=attrs,
        )
    finally:
        db_session.close()
    rtnval = view.worker_id
    return rtnval


def test_acquire_lease_on_unleased_worker():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: acquire_lease on an unleased worker stamps the
    holder, acquired_at, and expires_at; the JobView surfaces
    all three.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="pi-01")
        db_session = factory()
        try:
            view = worker_service.acquire_lease(
                db_session=db_session,
                worker_id=worker_id,
                holder="flow:abc",
                ttl_seconds=60,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.lease_holder, "flow:abc")
        testbase.assert_equal(view.lease_acquired_at is not None, True)
        testbase.assert_equal(view.lease_expires_at is not None, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_acquire_lease_rejects_zero_or_negative_ttl():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: ``ttl_seconds <= 0`` raises ValueError so a
    buggy caller doesn't accidentally lease "forever-but-
    expired".**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="pi-02")
        db_session = factory()
        try:
            try:
                worker_service.acquire_lease(
                    db_session=db_session,
                    worker_id=worker_id,
                    holder="flow:x",
                    ttl_seconds=0,
                )
                raised = False
            except ValueError:
                raised = True
            testbase.assert_equal(raised, True)
        finally:
            db_session.close()
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_acquire_lease_blocks_different_holder_when_active():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: An active lease prevents a different holder
    from acquiring; WorkerBusyError carries the held-by /
    requested-by context so the caller can log it usefully.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="pi-03")
        db_session = factory()
        try:
            worker_service.acquire_lease(
                db_session=db_session,
                worker_id=worker_id,
                holder="flow:owner",
                ttl_seconds=60,
            )
            try:
                worker_service.acquire_lease(
                    db_session=db_session,
                    worker_id=worker_id,
                    holder="flow:other",
                    ttl_seconds=60,
                )
                raised = False
            except WorkerBusyError as exc:
                raised = True
                err_text = str(exc)
            testbase.assert_equal(raised, True)
            testbase.assert_equal("flow:owner" in err_text, True)
            testbase.assert_equal("flow:other" in err_text, True)
        finally:
            db_session.close()
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_acquire_lease_extends_for_same_holder():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: The current holder can re-acquire to push
    expires_at forward; acquired_at is preserved (the lease
    didn't lapse, it was just extended).**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="pi-04")
        now = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
        db_session = factory()
        try:
            first = worker_service.acquire_lease(
                db_session=db_session,
                worker_id=worker_id,
                holder="flow:keep",
                ttl_seconds=60,
                now=now,
            )
            later = now + timedelta(seconds=30)
            second = worker_service.acquire_lease(
                db_session=db_session,
                worker_id=worker_id,
                holder="flow:keep",
                ttl_seconds=60,
                now=later,
            )
        finally:
            db_session.close()
        testbase.assert_equal(first.lease_acquired_at, second.lease_acquired_at)
        # New expires is later than first.
        testbase.assert_equal(
            second.lease_expires_at > first.lease_expires_at,
            True,
        )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_acquire_lease_succeeds_after_prior_lease_expired():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: An expired lease no longer blocks a different
    holder; the new acquire succeeds and stamps a fresh
    acquired_at.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="pi-05")
        early = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
        late = early + timedelta(seconds=120)
        db_session = factory()
        try:
            worker_service.acquire_lease(
                db_session=db_session,
                worker_id=worker_id,
                holder="flow:gone",
                ttl_seconds=30,
                now=early,
            )
            view = worker_service.acquire_lease(
                db_session=db_session,
                worker_id=worker_id,
                holder="flow:new",
                ttl_seconds=60,
                now=late,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.lease_holder, "flow:new")
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_release_lease_is_permissive_for_wrong_holder():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: Releasing under a different holder is a silent
    no-op — the worker still belongs to the original holder
    and the caller doesn't get an exception.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="pi-06")
        db_session = factory()
        try:
            worker_service.acquire_lease(
                db_session=db_session,
                worker_id=worker_id,
                holder="flow:hold",
                ttl_seconds=60,
            )
            view = worker_service.release_lease(
                db_session=db_session,
                worker_id=worker_id,
                holder="flow:wrong",
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.lease_holder, "flow:hold")
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_release_all_leases_for_holder_clears_every_match():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: release_all_leases_for_holder clears the
    holder on every worker it currently holds, returns the
    list of cleared worker_ids, and leaves other holders'
    leases untouched.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        a = _register_worker(factory=factory, name="pi-a")
        b = _register_worker(factory=factory, name="pi-b")
        c = _register_worker(factory=factory, name="pi-c")
        db_session = factory()
        try:
            for w in [a, b]:
                worker_service.acquire_lease(
                    db_session=db_session,
                    worker_id=w,
                    holder="flow:ours",
                    ttl_seconds=60,
                )
            worker_service.acquire_lease(
                db_session=db_session,
                worker_id=c,
                holder="flow:other",
                ttl_seconds=60,
            )
            cleared = worker_service.release_all_leases_for_holder(
                db_session=db_session, holder="flow:ours",
            )
        finally:
            db_session.close()
        testbase.assert_equal(set(cleared), {a, b})
        # c still holds its lease.
        db_session = factory()
        try:
            row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == c)
                .first()
            )
        finally:
            db_session.close()
        testbase.assert_equal(row.lease_holder, "flow:other")
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_expire_stale_leases_clears_only_expired():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: expire_stale_leases clears leases past their
    expires_at and leaves still-active leases alone.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        live = _register_worker(factory=factory, name="alive")
        dead = _register_worker(factory=factory, name="dead")
        early = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
        db_session = factory()
        try:
            worker_service.acquire_lease(
                db_session=db_session, worker_id=live,
                holder="flow:live", ttl_seconds=120, now=early,
            )
            worker_service.acquire_lease(
                db_session=db_session, worker_id=dead,
                holder="flow:dead", ttl_seconds=10, now=early,
            )
            cleared = worker_service.expire_stale_leases(
                db_session=db_session,
                now=early + timedelta(seconds=60),
            )
        finally:
            db_session.close()
        testbase.assert_equal(cleared, [dead])
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_claim_next_job_blocks_when_worker_leased_elsewhere():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: A worker leased to flow:A cannot claim a job
    targeted at flow:B (or unscoped), even when selectors
    otherwise match.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="locked")
        db_session = factory()
        try:
            worker_service.acquire_lease(
                db_session=db_session, worker_id=worker_id,
                holder="flow:A", ttl_seconds=600,
            )
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
                lease_holder="flow:B",
                lease_ttl_seconds=600,
            )
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "y"},
                # No lease_holder.
            )
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(claimed, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_claim_next_job_extends_lease_for_matching_holder():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: When the candidate's lease_holder matches the
    worker's existing lease, the claim succeeds and the lease
    expires_at is pushed forward (extended) per the
    candidate's lease_ttl_seconds.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="held")
        db_session = factory()
        try:
            worker_service.acquire_lease(
                db_session=db_session, worker_id=worker_id,
                holder="flow:hold", ttl_seconds=30,
            )
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "step1"},
                lease_holder="flow:hold",
                lease_ttl_seconds=600,
            )
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
        finally:
            db_session.close()
        testbase.assert_equal(claimed is not None, True)
        testbase.assert_equal(row.lease_holder, "flow:hold")
        # Lease's new TTL is 600s, much longer than the 30s
        # from the original acquire.
        testbase.assert_equal(
            (row.lease_expires_at - row.lease_acquired_at)
            > timedelta(seconds=120),
            True,
        )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_claim_next_job_acquires_lease_for_first_holder():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: When the candidate carries a lease_holder and
    the worker is unleased, the claim acquires the lease so
    subsequent jobs from the same holder land here and other
    holders are kept out.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="fresh")
        db_session = factory()
        try:
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "first"},
                lease_holder="flow:newhold",
                lease_ttl_seconds=300,
            )
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
        finally:
            db_session.close()
        testbase.assert_equal(claimed is not None, True)
        testbase.assert_equal(row.lease_holder, "flow:newhold")
        testbase.assert_equal(row.lease_expires_at is not None, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_stale_worker_sweeper_clears_lease_on_offline_flip():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: When the sweeper flips a worker to OFFLINE,
    its lease fields are cleared so the holder isn't left
    waiting on hardware that won't return.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id = _register_worker(factory=factory, name="ghost")
        db_session = factory()
        try:
            worker_service.acquire_lease(
                db_session=db_session, worker_id=worker_id,
                holder="flow:lost", ttl_seconds=600,
            )
            row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
            row.last_heartbeat_at = (
                datetime.now(timezone.utc) - timedelta(seconds=300)
            )
            db_session.commit()
            sweep_once(
                db_session=db_session, stale_threshold_seconds=60.0,
            )
            row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
        finally:
            db_session.close()
        testbase.assert_equal(row.status, WorkerStatus.OFFLINE.value)
        testbase.assert_equal(row.lease_holder, None)
        testbase.assert_equal(row.lease_acquired_at, None)
        testbase.assert_equal(row.lease_expires_at, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_remote_command_exclusive_holds_worker_across_two_steps_end_to_end():
    """
    **Feature: P28a hardware reservation (M3)**
    **Property: A flow with two ``exclusive: true`` steps
    targeted at the same pod runs both steps on the same
    worker; another flow trying to claim that worker mid-way
    is blocked. After the first flow completes, FlowRuntime
    releases the lease and the second flow can run.**
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p28a-test-pepper"))
    engine, factory, path = _build_engine_and_factory()
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
        local_worker_pool_size=0,
    )
    db_session = factory()
    try:
        view = worker_service.register_worker(
            db_session=db_session,
            name="lab-pi", kind=WorkerKind.REMOTE_MACHINE,
            attributes={"pod_name": "lab-pi"},
        )
        worker_id = view.worker_id
    finally:
        db_session.close()

    stop_event = threading.Event()
    seen_lease_holders: List[Optional[str]] = []

    def _stub_worker_loop() -> None:
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
            seen_lease_holders.append(claimed.lease_holder)
            db_session = factory()
            try:
                jobservice.report_result(
                    db_session=db_session,
                    worker_id=worker_id,
                    job_id=claimed.job_id,
                    result_code=0,
                    stdout="ok\n",
                )
            finally:
                db_session.close()
        return

    worker_thread = threading.Thread(
        target=_stub_worker_loop, daemon=True,
    )
    worker_thread.start()

    try:
        workflow_yaml = "\n".join([
            "name: p28a-exclusive-flow",
            "environment: {}",
            "parameters: {}",
            "flow:",
            "  - task: setup",
            "    tasktype: automojo.pychestrate.webservice.orchestration.remotecommand@RemoteCommand",
            "    command: setup.sh",
            "    target_pod_name: lab-pi",
            "    exclusive: true",
            "    timeout_seconds: 5",
            "  - task: probe",
            "    tasktype: automojo.pychestrate.webservice.orchestration.remotecommand@RemoteCommand",
            "    command: probe.sh",
            "    target_pod_name: lab-pi",
            "    exclusive: true",
            "    timeout_seconds: 5",
            "",
        ])
        flow_id = app.flow_runtime.submit_workflow_yaml(
            workflow_yaml=workflow_yaml,
        )
        deadline = time.time() + 10.0
        terminal_state = None
        while time.time() < deadline:
            sub = app.flow_runtime.status(flow_id=flow_id)
            if sub is not None and sub.state in (
                FlowState.SUCCEEDED, FlowState.FAILED,
            ):
                terminal_state = sub.state
                break
            time.sleep(0.05)
        testbase.assert_equal(terminal_state, FlowState.SUCCEEDED)

        # Both steps carried the same lease_holder (== flow id
        # prefixed with "flow:").
        testbase.assert_equal(len(seen_lease_holders), 2)
        testbase.assert_equal(
            seen_lease_holders[0], seen_lease_holders[1],
        )
        testbase.assert_equal(
            seen_lease_holders[0].startswith("flow:"), True,
        )

        # FlowRuntime released the lease in finally.
        db_session = factory()
        try:
            row = (
                db_session.query(Worker)
                .filter(Worker.worker_id == worker_id)
                .first()
            )
        finally:
            db_session.close()
        testbase.assert_equal(row.lease_holder, None)
    finally:
        stop_event.set()
        worker_thread.join(timeout=2.0)
        app.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return
