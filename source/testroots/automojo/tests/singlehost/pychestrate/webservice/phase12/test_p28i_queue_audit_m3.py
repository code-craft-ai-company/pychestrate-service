"""
.. module:: test_p28i_queue_audit_m3
    :synopsis: Tests for queue-action audit-log capture.

Covers:

* enqueue_job writes an ``audit.queue.job.enqueued`` row with
  the canonical payload (job_id, command, target_pod_name,
  target_kind, priority, project_id, attempt, max_attempts,
  required_capabilities, lease_holder).
* claim_next_job writes ``audit.queue.job.claimed``.
* report_result writes ``audit.queue.job.reported`` for
  terminal results AND for retry-re-enqueues; the
  ``is_retry`` boolean discriminates.
* acquire_lease / release_lease write
  ``audit.queue.lease.acquired`` / ``.released``.
* The hash chain stays well-formed across the new kinds —
  every record's previous_hash matches the predecessor's
  record_hash.
* An audit failure (kind not registered) does not crash the
  queue write — the queue commit stays in place even when the
  audit row is dropped.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile

from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.audit.models import AuditRecord
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (  # noqa: F401
    PychestrateApplication,
)
from automojo.pychestrate.webservice.workers import jobservice
from automojo.pychestrate.webservice.workers import service as worker_service
from automojo.pychestrate.webservice.workers.jobmodels import (
    JobState,
    WorkerJob,
)
from automojo.pychestrate.webservice.workers.models import WorkerKind

from automojo.pychestrate.webservice.audit import (
    register_builtin_extensions as register_audit_extensions,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _setup_extensions() -> None:
    """
        Reset the resource-extension registry and register only
        the audit packs we depend on. We avoid the full
        ``register_phase1_builtin_extensions`` because it
        freezes the project-metadata registry, which can't be
        re-frozen across test invocations.
    """
    reset_phase1_runtime()
    register_audit_extensions()
    return


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p28i_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def _all_audit_records(*, db_session) -> list:
    rtnval = (
        db_session.query(AuditRecord)
        .order_by(AuditRecord.sequence_number.asc())
        .all()
    )
    return rtnval


def _audit_records_by_kind(*, db_session, kind: str) -> list:
    rtnval = (
        db_session.query(AuditRecord)
        .filter(AuditRecord.kind == kind)
        .order_by(AuditRecord.sequence_number.asc())
        .all()
    )
    return rtnval


def test_enqueue_job_writes_audit_row():
    """
    **Feature: P28i queue audit (M3)**
    **Property: enqueue_job appends an
    ``audit.queue.job.enqueued`` record carrying the
    job_id, command, selectors, priority, project_id,
    attempt, and required_capabilities.**
    """
    _setup_extensions()
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "uname -a"},
                target_pod_name="raspi-01",
                target_kind=WorkerKind.REMOTE_MACHINE,
                priority=5,
                required_capabilities=["uefi"],
            )
            rows = _audit_records_by_kind(
                db_session=db_session,
                kind="audit.queue.job.enqueued",
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(rows), 1)
        payload = rows[0].payload_json
        testbase.assert_equal(payload["job_id"], view.job_id)
        testbase.assert_equal(payload["command"], "uname -a")
        testbase.assert_equal(payload["target_pod_name"], "raspi-01")
        testbase.assert_equal(payload["target_kind"], "remote-machine")
        testbase.assert_equal(payload["priority"], 5)
        testbase.assert_equal(payload["required_capabilities"], ["uefi"])
        testbase.assert_equal(payload["attempt"], 1)
        testbase.assert_equal(payload["max_attempts"], 1)
        testbase.assert_equal(payload["project_id"], None)
        testbase.assert_equal(
            rows[0].target_ref,
            "worker_job:{0}".format(view.job_id),
        )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_claim_next_job_writes_audit_row():
    """
    **Feature: P28i queue audit (M3)**
    **Property: claim_next_job appends
    ``audit.queue.job.claimed`` with worker_id + attempt.**
    """
    _setup_extensions()
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            wv = worker_service.register_worker(
                db_session=db_session, name="w",
                kind=WorkerKind.LOCAL_PROCESS,
            )
            jv = jobservice.enqueue_job(
                db_session=db_session, payload={"command": "x"},
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=wv.worker_id,
            )
            rows = _audit_records_by_kind(
                db_session=db_session,
                kind="audit.queue.job.claimed",
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(rows), 1)
        payload = rows[0].payload_json
        testbase.assert_equal(payload["job_id"], jv.job_id)
        testbase.assert_equal(payload["worker_id"], wv.worker_id)
        testbase.assert_equal(payload["attempt"], 1)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_report_result_terminal_writes_audit_row():
    """
    **Feature: P28i queue audit (M3)**
    **Property: A terminal report writes
    ``audit.queue.job.reported`` with ``is_retry=False``,
    the final state, and the result_code.**
    """
    _setup_extensions()
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            wv = worker_service.register_worker(
                db_session=db_session, name="w",
                kind=WorkerKind.LOCAL_PROCESS,
            )
            jv = jobservice.enqueue_job(
                db_session=db_session, payload={"command": "x"},
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=wv.worker_id,
            )
            jobservice.report_result(
                db_session=db_session, worker_id=wv.worker_id,
                job_id=jv.job_id, result_code=0,
            )
            rows = _audit_records_by_kind(
                db_session=db_session,
                kind="audit.queue.job.reported",
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(rows), 1)
        payload = rows[0].payload_json
        testbase.assert_equal(payload["job_id"], jv.job_id)
        testbase.assert_equal(payload["state"], JobState.SUCCEEDED.value)
        testbase.assert_equal(payload["result_code"], 0)
        testbase.assert_equal(payload["is_retry"], False)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_report_result_retry_writes_audit_row_with_is_retry_true():
    """
    **Feature: P28i queue audit (M3)**
    **Property: A failed-with-retries report writes
    ``audit.queue.job.reported`` with ``is_retry=True`` and
    state=PENDING (since the job is back in the queue).**
    """
    _setup_extensions()
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            wv = worker_service.register_worker(
                db_session=db_session, name="w",
                kind=WorkerKind.LOCAL_PROCESS,
            )
            jv = jobservice.enqueue_job(
                db_session=db_session, payload={"command": "x"},
                max_attempts=2,
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=wv.worker_id,
            )
            jobservice.report_result(
                db_session=db_session, worker_id=wv.worker_id,
                job_id=jv.job_id, result_code=1,
            )
            rows = _audit_records_by_kind(
                db_session=db_session,
                kind="audit.queue.job.reported",
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(rows), 1)
        payload = rows[0].payload_json
        testbase.assert_equal(payload["state"], JobState.PENDING.value)
        testbase.assert_equal(payload["is_retry"], True)
        testbase.assert_equal(payload["result_code"], 1)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_acquire_and_release_lease_write_audit_rows():
    """
    **Feature: P28i queue audit (M3)**
    **Property: Explicit lease acquire / release write
    ``audit.queue.lease.acquired`` / ``.released`` rows
    keyed to the worker target_ref.**
    """
    _setup_extensions()
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            wv = worker_service.register_worker(
                db_session=db_session, name="lease-pi",
                kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_service.acquire_lease(
                db_session=db_session, worker_id=wv.worker_id,
                holder="flow:abc", ttl_seconds=120,
            )
            worker_service.release_lease(
                db_session=db_session, worker_id=wv.worker_id,
                holder="flow:abc",
            )
            acquired = _audit_records_by_kind(
                db_session=db_session,
                kind="audit.queue.lease.acquired",
            )
            released = _audit_records_by_kind(
                db_session=db_session,
                kind="audit.queue.lease.released",
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(acquired), 1)
        testbase.assert_equal(
            acquired[0].payload_json["worker_id"], wv.worker_id,
        )
        testbase.assert_equal(
            acquired[0].payload_json["holder"], "flow:abc",
        )
        testbase.assert_equal(
            acquired[0].payload_json["ttl_seconds"], 120,
        )
        testbase.assert_equal(
            acquired[0].target_ref,
            "worker:{0}".format(wv.worker_id),
        )
        testbase.assert_equal(len(released), 1)
        testbase.assert_equal(
            released[0].payload_json["worker_id"], wv.worker_id,
        )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_release_lease_under_wrong_holder_does_not_audit():
    """
    **Feature: P28i queue audit (M3)**
    **Property: A no-op release (wrong holder) doesn't write
    a misleading "released" audit row — the holder still has
    the lease.**
    """
    _setup_extensions()
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            wv = worker_service.register_worker(
                db_session=db_session, name="held",
                kind=WorkerKind.REMOTE_MACHINE,
            )
            worker_service.acquire_lease(
                db_session=db_session, worker_id=wv.worker_id,
                holder="flow:owner", ttl_seconds=60,
            )
            worker_service.release_lease(
                db_session=db_session, worker_id=wv.worker_id,
                holder="flow:other",
            )
            released = _audit_records_by_kind(
                db_session=db_session,
                kind="audit.queue.lease.released",
            )
        finally:
            db_session.close()
        testbase.assert_equal(released, [])
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_audit_chain_stays_intact_across_queue_kinds():
    """
    **Feature: P28i queue audit (M3)**
    **Property: The hash chain is unbroken across queue-side
    audit kinds: every record's ``previous_hash`` equals its
    predecessor's ``record_hash``. This is the tamper-evident
    promise of the audit chain.**
    """
    _setup_extensions()
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            wv = worker_service.register_worker(
                db_session=db_session, name="chain-pi",
                kind=WorkerKind.LOCAL_PROCESS,
            )
            jv = jobservice.enqueue_job(
                db_session=db_session, payload={"command": "x"},
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=wv.worker_id,
            )
            jobservice.report_result(
                db_session=db_session, worker_id=wv.worker_id,
                job_id=jv.job_id, result_code=0,
            )
            worker_service.acquire_lease(
                db_session=db_session, worker_id=wv.worker_id,
                holder="flow:hold", ttl_seconds=60,
            )
            worker_service.release_lease(
                db_session=db_session, worker_id=wv.worker_id,
                holder="flow:hold",
            )
            rows = _all_audit_records(db_session=db_session)
        finally:
            db_session.close()
        testbase.assert_equal(len(rows) >= 5, True)
        for index in range(1, len(rows)):
            testbase.assert_equal(
                bytes(rows[index].previous_hash),
                bytes(rows[index - 1].record_hash),
            )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_queue_write_survives_audit_failure():
    """
    **Feature: P28i queue audit (M3)**
    **Property: An audit failure (e.g. unknown-kind path or
    a crashing audit_writer) doesn't block the queue write —
    the WorkerJob row stays committed even when the audit
    row is dropped. Operational queue > bookkeeping.**
    """
    _setup_extensions()
    engine, factory, path = _build_engine_and_factory()
    # Monkey-patch audit_writer.capture_event to always raise.
    from automojo.pychestrate.webservice.audit import audit_writer
    original = audit_writer.capture_event
    def _boom(**_kwargs):
        raise RuntimeError("simulated audit failure")
    audit_writer.capture_event = _boom
    try:
        db_session = factory()
        try:
            view = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
            )
            row = (
                db_session.query(WorkerJob)
                .filter(WorkerJob.job_id == view.job_id)
                .first()
            )
            audit_count = (
                db_session.query(AuditRecord).count()
            )
        finally:
            db_session.close()
        # Queue write committed even though audit raised.
        testbase.assert_equal(row is not None, True)
        testbase.assert_equal(row.state, JobState.PENDING.value)
        # No audit row landed.
        testbase.assert_equal(audit_count, 0)
    finally:
        audit_writer.capture_event = original
        engine.dispose()
        os.unlink(path)
    return
