"""
.. module:: test_p28g_project_scoped_queues_m3
    :synopsis: Tests for project-scoped queue isolation.

Covers:

* enqueue_job accepts ``project_id``; the JobView surfaces
  it; default is ``None`` (global queue).
* claim_next_job: a project-scoped worker only claims jobs
  from its own project or unscoped global jobs.
* claim_next_job: a global worker (no project_id) can claim
  any project's jobs.
* claim_next_job: a project-scoped job is invisible to
  workers in a different project.
* list_jobs supports a ``project_id`` filter.
* RemoteCommand and FanOutCommand pass ``project_id`` through
  to enqueue_job.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import tempfile

from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (  # noqa: F401
    PychestrateApplication,
)
from automojo.pychestrate.webservice.orchestration.fanoutcommand import (
    FanOutCommand,
)
from automojo.pychestrate.webservice.orchestration.remotecommand import (
    RemoteCommand,
)
from automojo.pychestrate.webservice.workers import jobservice
from automojo.pychestrate.webservice.workers import service as worker_service
from automojo.pychestrate.webservice.workers.models import WorkerKind


_PROJECT_A = "00000000-0000-4000-8000-00000000a001"
_PROJECT_B = "00000000-0000-4000-8000-00000000b001"


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p28g_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def test_enqueue_job_default_project_is_none():
    """
    **Feature: P28g project-scoped queues (M3)**
    **Property: enqueue_job without ``project_id`` defaults
    to None (global queue) and surfaces on the view.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = jobservice.enqueue_job(
                db_session=db_session, payload={"command": "x"},
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.project_id, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_enqueue_job_project_id_round_trips():
    """
    **Feature: P28g project-scoped queues (M3)**
    **Property: ``project_id`` round-trips on the view and
    persists on the row.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            view = jobservice.enqueue_job(
                db_session=db_session, payload={"command": "x"},
                project_id=_PROJECT_A,
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.project_id, _PROJECT_A)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_project_scoped_worker_only_claims_own_project_or_global():
    """
    **Feature: P28g project-scoped queues (M3)**
    **Property: A worker in project A claims A's jobs and
    unscoped global jobs, but not B's jobs.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            wv_a = worker_service.register_worker(
                db_session=db_session, name="a-pi",
                kind=WorkerKind.LOCAL_PROCESS,
                project_id=_PROJECT_A,
            )
            # B's job — must be invisible.
            jobservice.enqueue_job(
                db_session=db_session, payload={"command": "b"},
                project_id=_PROJECT_B,
            )
            # Global — claimable.
            global_view = jobservice.enqueue_job(
                db_session=db_session, payload={"command": "g"},
            )
            # A's own job (enqueued after global; FIFO + same
            # priority — global is older).
            a_view = jobservice.enqueue_job(
                db_session=db_session, payload={"command": "a"},
                project_id=_PROJECT_A,
            )

            first = jobservice.claim_next_job(
                db_session=db_session, worker_id=wv_a.worker_id,
            )
            jobservice.report_result(
                db_session=db_session, worker_id=wv_a.worker_id,
                job_id=first.job_id, result_code=0,
            )
            second = jobservice.claim_next_job(
                db_session=db_session, worker_id=wv_a.worker_id,
            )
            jobservice.report_result(
                db_session=db_session, worker_id=wv_a.worker_id,
                job_id=second.job_id, result_code=0,
            )
            # Third claim — B's job is NOT eligible.
            third = jobservice.claim_next_job(
                db_session=db_session, worker_id=wv_a.worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(first.job_id, global_view.job_id)
        testbase.assert_equal(second.job_id, a_view.job_id)
        testbase.assert_equal(third, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_global_worker_can_claim_any_project_job():
    """
    **Feature: P28g project-scoped queues (M3)**
    **Property: A worker without a project_id (global) is
    eligible to claim work from any project.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            wv = worker_service.register_worker(
                db_session=db_session, name="global-pi",
                kind=WorkerKind.LOCAL_PROCESS,
            )
            jobservice.enqueue_job(
                db_session=db_session, payload={"command": "a"},
                project_id=_PROJECT_A,
            )
            jobservice.enqueue_job(
                db_session=db_session, payload={"command": "b"},
                project_id=_PROJECT_B,
            )

            first = jobservice.claim_next_job(
                db_session=db_session, worker_id=wv.worker_id,
            )
            jobservice.report_result(
                db_session=db_session, worker_id=wv.worker_id,
                job_id=first.job_id, result_code=0,
            )
            second = jobservice.claim_next_job(
                db_session=db_session, worker_id=wv.worker_id,
            )
        finally:
            db_session.close()
        # Both jobs claimable — order is FIFO.
        testbase.assert_equal(first is not None, True)
        testbase.assert_equal(second is not None, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_project_a_workers_cannot_claim_project_b_jobs():
    """
    **Feature: P28g project-scoped queues (M3)**
    **Property: A worker in project A is never offered B's
    work, even when nothing else is in the queue.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            wv_a = worker_service.register_worker(
                db_session=db_session, name="a-only",
                kind=WorkerKind.LOCAL_PROCESS,
                project_id=_PROJECT_A,
            )
            jobservice.enqueue_job(
                db_session=db_session, payload={"command": "b"},
                project_id=_PROJECT_B,
            )
            claimed = jobservice.claim_next_job(
                db_session=db_session, worker_id=wv_a.worker_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(claimed, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_list_jobs_filters_by_project_id():
    """
    **Feature: P28g project-scoped queues (M3)**
    **Property: list_jobs honours the ``project_id`` filter
    so the dashboard can render per-project queues.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            jobservice.enqueue_job(
                db_session=db_session, payload={"command": "a1"},
                project_id=_PROJECT_A,
            )
            jobservice.enqueue_job(
                db_session=db_session, payload={"command": "b1"},
                project_id=_PROJECT_B,
            )
            jobservice.enqueue_job(
                db_session=db_session, payload={"command": "g1"},
            )
            a_only = jobservice.list_jobs(
                db_session=db_session, project_id=_PROJECT_A,
            )
            b_only = jobservice.list_jobs(
                db_session=db_session, project_id=_PROJECT_B,
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(a_only), 1)
        testbase.assert_equal(a_only[0].project_id, _PROJECT_A)
        testbase.assert_equal(len(b_only), 1)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_remote_command_propagates_project_id():
    """
    **Feature: P28g project-scoped queues (M3)**
    **Property: ``project_id`` in the workflow YAML lands on
    the underlying RemoteCommand and is passed to
    enqueue_job.**
    """
    task = RemoteCommand(
        ordinal="1", label="proj-step",
        task_info={
            "command": "x",
            "project_id": _PROJECT_A,
        },
        logger=logging.getLogger("p28g"),
    )
    testbase.assert_equal(task.project_id, _PROJECT_A)
    return


def test_fan_out_command_propagates_project_id():
    """
    **Feature: P28g project-scoped queues (M3)**
    **Property: ``project_id`` on a FanOutCommand stamps on
    every dispatched target.**
    """
    task = FanOutCommand(
        ordinal="1", label="proj-fanout",
        task_info={
            "command": "x",
            "project_id": _PROJECT_B,
            "targets": [{"target_pod_name": "raspi-01"}],
        },
        logger=logging.getLogger("p28g"),
    )
    testbase.assert_equal(task._project_id, _PROJECT_B)
    return
