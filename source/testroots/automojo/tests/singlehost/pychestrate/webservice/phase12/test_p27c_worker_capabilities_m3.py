"""
.. module:: test_p27c_worker_capabilities_m3
    :synopsis: Tests for worker capability matching.

Covers:

* :func:`worker_satisfies_capabilities` is a strict superset
  check: empty requirements always match, missing
  ``capabilities`` attribute never matches, capability list
  matched as a set.
* :func:`enqueue_job` validates ``required_capabilities`` —
  rejects non-list inputs and non-string entries; trims
  whitespace; de-duplicates.
* :func:`claim_next_job` skips workers that don't advertise
  every required capability, even when the
  ``target_pod_name`` / ``target_kind`` selector matches.
* The capability match is order-independent and case-sensitive.
* End-to-end via :class:`RemoteCommand`: a workflow declaring
  ``required_capabilities: [uefi]`` is dispatched only to a
  worker whose ``attributes.capabilities`` includes ``"uefi"``;
  a workflow with no capability requirement still lands on any
  worker.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile
import threading
import time

from typing import Tuple

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
from automojo.pychestrate.webservice.workers.jobmodels import JobState
from automojo.pychestrate.webservice.workers.models import WorkerKind

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p27c_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def test_worker_satisfies_capabilities_empty_requirement_matches():
    """
    **Feature: P27c worker capabilities (M3)**
    **Property: An empty required-capabilities list matches any
    worker, even one with no capabilities advertised at all.**
    """
    testbase.assert_equal(
        jobservice.worker_satisfies_capabilities(
            worker_attributes={},
            required_capabilities=[],
        ),
        True,
    )
    testbase.assert_equal(
        jobservice.worker_satisfies_capabilities(
            worker_attributes=None,
            required_capabilities=[],
        ),
        True,
    )
    return


def test_worker_satisfies_capabilities_strict_superset():
    """
    **Feature: P27c worker capabilities (M3)**
    **Property: Worker matches iff every required capability
    appears in its advertised set; missing one fails the gate.**
    """
    attrs = {"capabilities": ["uefi", "tpm-2.0", "usb3"]}
    testbase.assert_equal(
        jobservice.worker_satisfies_capabilities(
            worker_attributes=attrs,
            required_capabilities=["uefi"],
        ),
        True,
    )
    testbase.assert_equal(
        jobservice.worker_satisfies_capabilities(
            worker_attributes=attrs,
            required_capabilities=["uefi", "tpm-2.0"],
        ),
        True,
    )
    testbase.assert_equal(
        jobservice.worker_satisfies_capabilities(
            worker_attributes=attrs,
            required_capabilities=["uefi", "secure-boot"],
        ),
        False,
    )
    return


def test_worker_satisfies_capabilities_missing_attribute_never_matches():
    """
    **Feature: P27c worker capabilities (M3)**
    **Property: A worker whose attributes don't include a
    ``capabilities`` list (or whose value isn't a list) never
    satisfies a non-empty requirement — explicit-rather-than-
    implicit failure mode.**
    """
    testbase.assert_equal(
        jobservice.worker_satisfies_capabilities(
            worker_attributes={"pod_name": "pi-01"},
            required_capabilities=["uefi"],
        ),
        False,
    )
    testbase.assert_equal(
        jobservice.worker_satisfies_capabilities(
            worker_attributes={"capabilities": "uefi"},  # str, not list
            required_capabilities=["uefi"],
        ),
        False,
    )
    return


def test_worker_satisfies_capabilities_match_is_case_sensitive():
    """
    **Feature: P27c worker capabilities (M3)**
    **Property: Capability matching is exact-string — ``UEFI``
    does not match ``uefi``. Operators establish a convention
    (lowercase, dashes) at the project level.**
    """
    attrs = {"capabilities": ["uefi"]}
    testbase.assert_equal(
        jobservice.worker_satisfies_capabilities(
            worker_attributes=attrs,
            required_capabilities=["UEFI"],
        ),
        False,
    )
    return


def test_enqueue_job_validates_required_capabilities():
    """
    **Feature: P27c worker capabilities (M3)**
    **Property: enqueue_job rejects non-list inputs, rejects
    non-string entries, trims whitespace, and de-duplicates +
    sorts so two equivalent requirement lists round-trip the
    same JSON.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            # Valid case — trim + dedupe + sort.
            view = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
                required_capabilities=[
                    "  uefi", "tpm-2.0", "uefi  ", "usb3",
                ],
            )
            testbase.assert_equal(
                view.required_capabilities,
                ["tpm-2.0", "uefi", "usb3"],
            )

            # Empty / None → empty list.
            view2 = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
            )
            testbase.assert_equal(view2.required_capabilities, [])

            # Non-list → ValueError.
            try:
                jobservice.enqueue_job(
                    db_session=db_session,
                    payload={"command": "x"},
                    required_capabilities="uefi",
                )
                raised = False
            except ValueError:
                raised = True
            testbase.assert_equal(raised, True)

            # Non-string entry → ValueError.
            try:
                jobservice.enqueue_job(
                    db_session=db_session,
                    payload={"command": "x"},
                    required_capabilities=["uefi", 42],
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


def test_claim_next_job_skips_worker_without_required_capabilities():
    """
    **Feature: P27c worker capabilities (M3)**
    **Property: A worker that satisfies the
    ``target_pod_name`` selector but lacks a required
    capability cannot claim the job.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            # Two workers with the same name (different
            # project_id implied — actually same project here,
            # so use distinct names) advertising different
            # capability sets.
            without_caps = worker_service.register_worker(
                db_session=db_session,
                name="generic-pi", kind=WorkerKind.REMOTE_MACHINE,
                attributes={"capabilities": ["usb3"]},
            )
            with_caps = worker_service.register_worker(
                db_session=db_session,
                name="uefi-pi", kind=WorkerKind.REMOTE_MACHINE,
                attributes={"capabilities": ["uefi", "tpm-2.0"]},
            )
            # Job needs uefi; only with_caps matches.
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "secure-boot-check"},
                required_capabilities=["uefi"],
            )
        finally:
            db_session.close()

        # Generic worker tries first — must be rejected.
        db_session = factory()
        try:
            generic_claim = jobservice.claim_next_job(
                db_session=db_session,
                worker_id=without_caps.worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(generic_claim, None)

        # Capable worker succeeds.
        db_session = factory()
        try:
            uefi_claim = jobservice.claim_next_job(
                db_session=db_session,
                worker_id=with_caps.worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(uefi_claim is not None, True)
        testbase.assert_equal(
            uefi_claim.required_capabilities, ["uefi"],
        )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_capability_match_is_order_independent():
    """
    **Feature: P27c worker capabilities (M3)**
    **Property: Worker advertises capabilities in some order,
    job requires them in another. The match is set-based.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = worker_service.register_worker(
                db_session=db_session,
                name="multi", kind=WorkerKind.REMOTE_MACHINE,
                attributes={"capabilities": ["c", "a", "b"]},
            )
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
                required_capabilities=["a", "b", "c"],
            )
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=view.worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(claimed is not None, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_remote_command_routes_by_capability_end_to_end():
    """
    **Feature: P27c worker capabilities (M3)**
    **Property: A workflow with ``required_capabilities:
    [uefi]`` is dispatched only to a worker whose advertised
    capabilities include ``uefi``. A capability-bearing stub
    worker completes the flow; the non-bearing stub never
    sees it.**
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p27c-test-pepper"))
    engine, factory, path = _build_engine_and_factory()
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
        local_worker_pool_size=0,
    )

    db_session = factory()
    try:
        generic = worker_service.register_worker(
            db_session=db_session,
            name="generic", kind=WorkerKind.REMOTE_MACHINE,
            attributes={"capabilities": ["usb3"]},
        )
        uefi = worker_service.register_worker(
            db_session=db_session,
            name="uefi-host", kind=WorkerKind.REMOTE_MACHINE,
            attributes={"capabilities": ["uefi", "tpm-2.0"]},
        )
    finally:
        db_session.close()

    stop_event = threading.Event()
    generic_polls: list = []
    uefi_polls: list = []

    def _stub_worker_loop(*, worker_id: str, poll_log: list) -> None:
        while not stop_event.is_set():
            db_session = factory()
            try:
                claimed = jobservice.claim_next_job(
                    db_session=db_session, worker_id=worker_id,
                )
            finally:
                db_session.close()
            if claimed is None:
                poll_log.append(None)
                stop_event.wait(0.05)
                continue
            poll_log.append(claimed.job_id)
            db_session = factory()
            try:
                jobservice.report_result(
                    db_session=db_session,
                    worker_id=worker_id,
                    job_id=claimed.job_id,
                    result_code=0,
                    stdout="ran on {0}\n".format(worker_id),
                )
            finally:
                db_session.close()
        return

    generic_thread = threading.Thread(
        target=_stub_worker_loop,
        kwargs={
            "worker_id": generic.worker_id,
            "poll_log": generic_polls,
        },
        daemon=True,
    )
    uefi_thread = threading.Thread(
        target=_stub_worker_loop,
        kwargs={
            "worker_id": uefi.worker_id,
            "poll_log": uefi_polls,
        },
        daemon=True,
    )
    generic_thread.start()
    uefi_thread.start()

    try:
        workflow_yaml = "\n".join([
            "name: p27c-cap-route",
            "environment: {}",
            "parameters: {}",
            "flow:",
            "  - task: probe",
            "    tasktype: automojo.pychestrate.webservice.orchestration.remotecommand@RemoteCommand",
            "    command: secure-boot-check",
            "    required_capabilities: [uefi]",
            "    timeout_seconds: 5",
            "",
        ])
        flow_id = app.flow_runtime.submit_workflow_yaml(
            workflow_yaml=workflow_yaml,
        )

        deadline = time.time() + 8.0
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

        # Only the uefi worker actually claimed the job.
        uefi_claims = [p for p in uefi_polls if p is not None]
        generic_claims = [p for p in generic_polls if p is not None]
        testbase.assert_equal(len(uefi_claims), 1)
        testbase.assert_equal(generic_claims, [])
    finally:
        stop_event.set()
        generic_thread.join(timeout=2.0)
        uefi_thread.join(timeout=2.0)
        app.shutdown(wait=True)
        engine.dispose()
        os.unlink(path)
    return


def test_workflow_without_capability_requirement_runs_anywhere():
    """
    **Feature: P27c worker capabilities (M3)**
    **Property: A workflow that omits ``required_capabilities``
    still dispatches to whatever worker matches the
    target_pod_name / target_kind selectors — the gate is
    additive, not subtractive.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            generic = worker_service.register_worker(
                db_session=db_session,
                name="lone", kind=WorkerKind.REMOTE_MACHINE,
                attributes={},  # no capabilities advertised.
            )
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
                # No required_capabilities supplied.
            )
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=generic.worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(claimed is not None, True)
        testbase.assert_equal(claimed.state, JobState.CLAIMED.value)
    finally:
        engine.dispose()
        os.unlink(path)
    return
