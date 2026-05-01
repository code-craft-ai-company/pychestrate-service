"""
.. module:: test_p27d_queue_stats_m3
    :synopsis: Tests for the queue/worker stats REST surface.

Covers:

* :func:`count_jobs_by_state` always reports every JobState
  member with at least 0, even when a state has no rows.
* :func:`count_retry_scheduled_jobs` reports only PENDING rows
  whose ``not_before`` is in the future.
* :func:`oldest_pending_age_seconds` returns ``None`` for an
  empty queue, the oldest claimable PENDING job's age
  otherwise, and skips PENDING rows whose ``not_before`` is
  still in the future.
* :func:`list_jobs` honours every documented filter and
  clamps ``limit`` to ``[1, 500]``.
* :func:`count_workers_by_status` reports every WorkerStatus
  member with at least 0.
* ``GET /api/v1/queue/stats`` returns the combined operator
  payload via the dispatcher under admin auth.
* ``GET /api/v1/queue/jobs`` lists with filters and ``limit``,
  and a non-int ``limit`` returns 400.
* ``GET /api/v1/queue/jobs/{job_id}`` reads one job and 404s
  for an unknown id.
* Anonymous calls to any ``/api/v1/queue/*`` endpoint get 401.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import tempfile

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.authentication.core import (
    AuthenticationContext,
    Principal,
)
from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
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
from automojo.pychestrate.webservice.workers.models import (
    WorkerKind,
    WorkerStatus,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p27d_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def _build_app() -> Tuple[
        PychestrateApplication, sessionmaker, str,
    ]:
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p27d-test-pepper"))
    engine, factory, path = _build_engine_and_factory()
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )
    return app, factory, path


def _admin_context() -> AuthenticationContext:
    return AuthenticationContext(
        principal=Principal(
            identifier="00000000-0000-4000-8000-00000000d100",
            display_name="Admin",
            roles={"system-admin"},
        ),
        scheme="test-injection",
    )


def _wrap(*, app, context: Optional[AuthenticationContext]) -> None:
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = context
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped
    return


def test_count_jobs_by_state_includes_zero_buckets():
    """
    **Feature: P27d queue stats (M3)**
    **Property: ``count_jobs_by_state`` returns every
    :class:`JobState` member's count, even ``0``, so the
    dashboard layer never has to guess at missing keys.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
            )
            counts = jobservice.count_jobs_by_state(
                db_session=db_session,
            )
        finally:
            db_session.close()
        for member in JobState:
            testbase.assert_equal(member.value in counts, True)
        testbase.assert_equal(counts[JobState.PENDING.value], 1)
        testbase.assert_equal(counts[JobState.SUCCEEDED.value], 0)
        testbase.assert_equal(counts[JobState.FAILED.value], 0)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_count_retry_scheduled_jobs_only_counts_future_not_before():
    """
    **Feature: P27d queue stats (M3)**
    **Property: A PENDING job with ``not_before`` in the
    future is "retry scheduled"; one with NULL or past
    ``not_before`` is not.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            future = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "f"},
            )
            past = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "p"},
            )
            null = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "n"},
            )
            future_row = (
                db_session.query(WorkerJob)
                .filter(WorkerJob.job_id == future.job_id)
                .first()
            )
            future_row.not_before = (
                datetime.now(timezone.utc) + timedelta(seconds=60)
            )
            past_row = (
                db_session.query(WorkerJob)
                .filter(WorkerJob.job_id == past.job_id)
                .first()
            )
            past_row.not_before = (
                datetime.now(timezone.utc) - timedelta(seconds=60)
            )
            db_session.commit()
            count = jobservice.count_retry_scheduled_jobs(
                db_session=db_session,
            )
        finally:
            db_session.close()
        testbase.assert_equal(count, 1)
        # null doesn't count as retry-scheduled.
        _ = null
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_oldest_pending_age_seconds_returns_none_for_empty_queue():
    """
    **Feature: P27d queue stats (M3)**
    **Property: An empty queue reports ``None`` rather than
    raising or returning ``0`` — the dashboard distinguishes
    "no work" from "fresh work".**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            age = jobservice.oldest_pending_age_seconds(
                db_session=db_session,
            )
        finally:
            db_session.close()
        testbase.assert_equal(age, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_oldest_pending_age_skips_jobs_in_retry_window():
    """
    **Feature: P27d queue stats (M3)**
    **Property: A PENDING row in its retry-backoff window
    (``not_before`` still in the future) is NOT counted as
    "the oldest pending" — those rows are intentionally not
    yet claimable.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            future = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "f"},
            )
            future_row = (
                db_session.query(WorkerJob)
                .filter(WorkerJob.job_id == future.job_id)
                .first()
            )
            future_row.not_before = (
                datetime.now(timezone.utc) + timedelta(seconds=60)
            )
            db_session.commit()
            age = jobservice.oldest_pending_age_seconds(
                db_session=db_session,
            )
        finally:
            db_session.close()
        testbase.assert_equal(age, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_oldest_pending_age_returns_age_of_oldest_claimable_job():
    """
    **Feature: P27d queue stats (M3)**
    **Property: The age reported is positive and reasonable
    for a freshly enqueued claimable job.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
            )
            age = jobservice.oldest_pending_age_seconds(
                db_session=db_session,
            )
        finally:
            db_session.close()
        testbase.assert_equal(age is not None, True)
        testbase.assert_equal(age >= 0.0, True)
        testbase.assert_equal(age < 5.0, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_list_jobs_filters_and_limits():
    """
    **Feature: P27d queue stats (M3)**
    **Property: list_jobs honours ``state`` /
    ``target_pod_name`` filters and clamps ``limit`` into
    ``[1, 500]``.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "a"},
                target_pod_name="raspi-01",
            )
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "b"},
                target_pod_name="raspi-02",
            )
            # state filter.
            pending_only = jobservice.list_jobs(
                db_session=db_session,
                state=JobState.PENDING.value,
            )
            failed_only = jobservice.list_jobs(
                db_session=db_session,
                state=JobState.FAILED.value,
            )
            # pod filter.
            raspi_one = jobservice.list_jobs(
                db_session=db_session,
                target_pod_name="raspi-01",
            )
            # over-limit clamp doesn't crash.
            jumbo = jobservice.list_jobs(
                db_session=db_session, limit=10000,
            )
            tiny = jobservice.list_jobs(
                db_session=db_session, limit=0,
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(pending_only), 2)
        testbase.assert_equal(len(failed_only), 0)
        testbase.assert_equal(len(raspi_one), 1)
        testbase.assert_equal(len(jumbo), 2)
        testbase.assert_equal(len(tiny), 1)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_count_workers_by_status_includes_zero_buckets():
    """
    **Feature: P27d queue stats (M3)**
    **Property: ``count_workers_by_status`` always reports
    every :class:`WorkerStatus` member, even ``0``.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            worker_service.register_worker(
                db_session=db_session,
                name="alive", kind=WorkerKind.LOCAL_PROCESS,
            )
            counts = worker_service.count_workers_by_status(
                db_session=db_session,
            )
        finally:
            db_session.close()
        for member in WorkerStatus:
            testbase.assert_equal(member.value in counts, True)
        testbase.assert_equal(counts[WorkerStatus.IDLE.value], 1)
        testbase.assert_equal(counts[WorkerStatus.OFFLINE.value], 0)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_queue_stats_endpoint_returns_full_dashboard_payload():
    """
    **Feature: P27d queue stats (M3)**
    **Property: GET /api/v1/queue/stats returns the combined
    payload (jobs.by_state, jobs.in_flight, jobs.retry_scheduled,
    jobs.oldest_pending_age_seconds, workers.by_status) under
    admin auth.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        db_session = factory()
        try:
            worker_service.register_worker(
                db_session=db_session,
                name="busybee", kind=WorkerKind.LOCAL_PROCESS,
            )
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
            )
        finally:
            db_session.close()

        response = app.dispatcher.dispatch(request=Request(
            method="GET", path="/api/v1/queue/stats",
        ))
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode())
        testbase.assert_equal("jobs" in body, True)
        testbase.assert_equal("workers" in body, True)
        testbase.assert_equal("by_state" in body["jobs"], True)
        testbase.assert_equal(
            body["jobs"]["by_state"][JobState.PENDING.value], 1,
        )
        testbase.assert_equal(body["jobs"]["in_flight"], 0)
        testbase.assert_equal(body["jobs"]["retry_scheduled"], 0)
        testbase.assert_equal(
            body["jobs"]["oldest_pending_age_seconds"] is not None, True,
        )
        testbase.assert_equal("by_status" in body["workers"], True)
        testbase.assert_equal(
            body["workers"]["by_status"][WorkerStatus.IDLE.value], 1,
        )
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_list_queue_jobs_endpoint_with_filters_and_bad_limit():
    """
    **Feature: P27d queue stats (M3)**
    **Property: GET /api/v1/queue/jobs honours filters via
    query string; a non-integer ``limit`` returns 400.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        db_session = factory()
        try:
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "raspi-01-cmd"},
                target_pod_name="raspi-01",
            )
            jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "raspi-02-cmd"},
                target_pod_name="raspi-02",
            )
        finally:
            db_session.close()

        response = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs",
            query_string=b"target_pod_name=raspi-01",
        ))
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode())
        testbase.assert_equal(len(body), 1)
        testbase.assert_equal(body[0]["target_pod_name"], "raspi-01")

        bad = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs",
            query_string=b"limit=not-a-number",
        ))
        testbase.assert_equal(bad.status_code, 400)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_read_queue_job_endpoint_404_for_unknown_id():
    """
    **Feature: P27d queue stats (M3)**
    **Property: GET /api/v1/queue/jobs/{id} returns 200 with
    the row when it exists, 404 when it doesn't.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        db_session = factory()
        try:
            view = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
            )
        finally:
            db_session.close()

        good = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/{0}".format(view.job_id),
        ))
        testbase.assert_equal(good.status_code, 200)
        body = json.loads(good.body.decode())
        testbase.assert_equal(body["job_id"], view.job_id)

        missing = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/00000000-0000-4000-8000-000000000bad",
        ))
        testbase.assert_equal(missing.status_code, 404)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_queue_stats_anonymous_access_returns_401():
    """
    **Feature: P27d queue stats (M3)**
    **Property: All ``/api/v1/queue/*`` endpoints are gated
    system-admin; an unauthenticated request gets 401.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=None)
    try:
        for path_under_test in [
            "/api/v1/queue/stats",
            "/api/v1/queue/jobs",
            "/api/v1/queue/jobs/00000000-0000-4000-8000-00000000d101",
        ]:
            response = app.dispatcher.dispatch(request=Request(
                method="GET", path=path_under_test,
            ))
            testbase.assert_equal(response.status_code, 401)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return
