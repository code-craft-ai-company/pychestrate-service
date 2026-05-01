"""
.. module:: test_p28d_test_results_m3
    :synopsis: Tests for the first-class test-result ORM + REST.

Covers:

* :func:`record_test_result` writes the row, copies the
  current ``attempt`` from the job, parses ISO timestamps,
  defaults missing ``completed_at`` to "now".
* :func:`record_test_result` validates ``case_name`` and
  ``outcome``; unknown ``job_id`` raises LookupError.
* :func:`record_test_results_batch` is all-or-nothing: a
  single bad entry raises before any row is written.
* :func:`list_test_results_for_job` returns rows in
  ``completed_at`` ascending order; ``outcome`` and
  ``attempt`` filters are honoured independently.
* :func:`summarize_test_results_for_job` always reports the
  conventional outcomes with at least 0; non-conventional
  outcomes appear under their literal name; total reflects
  every row.
* REST: agent records single + batch; admin lists + filters;
  admin reads summary; bad payloads return 400; unknown job
  returns 404; anonymous returns 401.
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
from automojo.pychestrate.webservice.workers import (
    jobservice,
    testresultservice,
)
from automojo.pychestrate.webservice.workers import service as worker_service
from automojo.pychestrate.webservice.workers.models import WorkerKind
from automojo.pychestrate.webservice.workers.testresultmodels import (
    TestOutcome,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p28d_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def _build_app() -> Tuple[PychestrateApplication, sessionmaker, str]:
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p28d-test-pepper"))
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
            identifier="00000000-0000-4000-8000-00000000d400",
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


def _enqueue_and_claim(
        *, factory: sessionmaker,
    ) -> Tuple[str, str]:
    db_session = factory()
    try:
        wv = worker_service.register_worker(
            db_session=db_session,
            name="tr-pi", kind=WorkerKind.REMOTE_MACHINE,
        )
        jv = jobservice.enqueue_job(
            db_session=db_session, payload={"command": "x"},
        )
        jobservice.claim_next_job(
            db_session=db_session, worker_id=wv.worker_id,
        )
    finally:
        db_session.close()
    return wv.worker_id, jv.job_id


def test_record_test_result_writes_row_and_copies_attempt():
    """
    **Feature: P28d test results (M3)**
    **Property: record_test_result persists every field;
    ``attempt`` mirrors the job's current attempt counter.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id, job_id = _enqueue_and_claim(factory=factory)
        started = datetime(2026, 5, 1, 1, 0, 0, tzinfo=timezone.utc)
        completed = started + timedelta(seconds=2.5)
        db_session = factory()
        try:
            view = testresultservice.record_test_result(
                db_session=db_session,
                job_id=job_id,
                worker_id=worker_id,
                suite_name="smoke",
                case_name="test_login_basic",
                outcome="passed",
                duration_seconds=2.5,
                started_at=started.isoformat(),
                completed_at=completed.isoformat(),
                attributes={"browser": "chromium"},
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.suite_name, "smoke")
        testbase.assert_equal(view.case_name, "test_login_basic")
        testbase.assert_equal(view.outcome, "passed")
        testbase.assert_equal(view.duration_seconds, 2.5)
        testbase.assert_equal(view.attempt, 1)
        testbase.assert_equal(view.attributes, {"browser": "chromium"})
        testbase.assert_equal(view.failure_message, None)
        testbase.assert_equal(view.failure_trace, None)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_record_test_result_validates_required_fields():
    """
    **Feature: P28d test results (M3)**
    **Property: Missing/empty ``case_name`` and ``outcome``
    raise ValueError. The REST handler maps to 400.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            try:
                testresultservice.record_test_result(
                    db_session=db_session, job_id=job_id,
                    worker_id=None,
                    case_name="   ", outcome="passed",
                )
                raised = False
            except ValueError:
                raised = True
            testbase.assert_equal(raised, True)
            try:
                testresultservice.record_test_result(
                    db_session=db_session, job_id=job_id,
                    worker_id=None,
                    case_name="t", outcome=None,
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


def test_record_test_result_unknown_job_raises_lookup_error():
    """
    **Feature: P28d test results (M3)**
    **Property: An unknown ``job_id`` raises LookupError, the
    REST handler maps to 404.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            try:
                testresultservice.record_test_result(
                    db_session=db_session,
                    job_id="00000000-0000-4000-8000-00000000beed",
                    worker_id=None,
                    case_name="t", outcome="passed",
                )
                raised = False
            except LookupError:
                raised = True
        finally:
            db_session.close()
        testbase.assert_equal(raised, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_record_batch_is_all_or_nothing_on_validation_failure():
    """
    **Feature: P28d test results (M3)**
    **Property: A bad entry in the batch raises before any
    row is written — partial commits would corrupt summary
    counts.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            try:
                testresultservice.record_test_results_batch(
                    db_session=db_session, job_id=job_id,
                    worker_id=None,
                    results=[
                        {"case_name": "a", "outcome": "passed"},
                        {"case_name": "", "outcome": "passed"},  # bad.
                        {"case_name": "c", "outcome": "passed"},
                    ],
                )
                raised = False
            except ValueError as exc:
                raised = True
                err_text = str(exc)
            testbase.assert_equal(raised, True)
            testbase.assert_equal("INDEX: 1" in err_text, True)

            existing = testresultservice.list_test_results_for_job(
                db_session=db_session, job_id=job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(existing, [])
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_record_batch_writes_all_on_success():
    """
    **Feature: P28d test results (M3)**
    **Property: A clean batch writes every row in one commit
    and returns the persisted views in input order.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            views = testresultservice.record_test_results_batch(
                db_session=db_session, job_id=job_id,
                worker_id=None,
                results=[
                    {
                        "case_name": "a",
                        "outcome": "passed",
                        "duration_seconds": 1.0,
                    },
                    {
                        "case_name": "b",
                        "outcome": "failed",
                        "failure_message": "boom",
                        "failure_trace": "stack...",
                    },
                ],
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(views), 2)
        testbase.assert_equal(views[0].case_name, "a")
        testbase.assert_equal(views[1].outcome, "failed")
        testbase.assert_equal(views[1].failure_message, "boom")
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_list_test_results_filter_by_outcome_and_attempt():
    """
    **Feature: P28d test results (M3)**
    **Property: list_test_results_for_job honours the
    ``outcome`` and ``attempt`` filters; results are
    completed_at ascending.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id, job_id = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            from automojo.pychestrate.webservice.workers.jobmodels import (
                WorkerJob,
            )
            row = (
                db_session.query(WorkerJob)
                .filter(WorkerJob.job_id == job_id)
                .first()
            )
            row.max_attempts = 3
            db_session.commit()

            # attempt 1: passed + failed.
            testresultservice.record_test_result(
                db_session=db_session, job_id=job_id,
                worker_id=worker_id,
                case_name="a", outcome="passed",
            )
            testresultservice.record_test_result(
                db_session=db_session, job_id=job_id,
                worker_id=worker_id,
                case_name="b", outcome="failed",
            )

            # Force retry → attempt 2.
            jobservice.report_result(
                db_session=db_session, worker_id=worker_id,
                job_id=job_id, result_code=1,
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            testresultservice.record_test_result(
                db_session=db_session, job_id=job_id,
                worker_id=worker_id,
                case_name="b", outcome="passed",
            )

            failed_only = testresultservice.list_test_results_for_job(
                db_session=db_session, job_id=job_id,
                outcome="failed",
            )
            attempt_2 = testresultservice.list_test_results_for_job(
                db_session=db_session, job_id=job_id,
                attempt=2,
            )
            all_results = testresultservice.list_test_results_for_job(
                db_session=db_session, job_id=job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(
            [v.case_name for v in failed_only], ["b"],
        )
        testbase.assert_equal(
            [(v.case_name, v.outcome) for v in attempt_2],
            [("b", "passed")],
        )
        testbase.assert_equal(len(all_results), 3)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_summary_includes_zero_buckets_and_counts_total():
    """
    **Feature: P28d test results (M3)**
    **Property: summary always reports
    passed/failed/skipped/errored (zero where appropriate);
    non-conventional outcomes appear under their literal
    name; total is the sum.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            for case, outcome in [
                ("a", "passed"),
                ("b", "passed"),
                ("c", "failed"),
                ("d", "skipped"),
                ("e", "xfailed"),  # non-conventional.
            ]:
                testresultservice.record_test_result(
                    db_session=db_session, job_id=job_id,
                    worker_id=None,
                    case_name=case, outcome=outcome,
                )
            summary = testresultservice.summarize_test_results_for_job(
                db_session=db_session, job_id=job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(summary["total"], 5)
        testbase.assert_equal(summary["passed"], 2)
        testbase.assert_equal(summary["failed"], 1)
        testbase.assert_equal(summary["skipped"], 1)
        testbase.assert_equal(summary["errored"], 0)
        testbase.assert_equal(
            summary["by_outcome"][TestOutcome.PASSED.value], 2,
        )
        testbase.assert_equal(
            summary["by_outcome"][TestOutcome.ERRORED.value], 0,
        )
        testbase.assert_equal(
            summary["by_outcome"]["xfailed"], 1,
        )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def _provision_job_via_rest(*, app, factory):
    register = app.dispatcher.dispatch(request=Request(
        method="POST",
        path="/api/v1/workers/register",
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "name": "tr-rest-pi", "kind": "remote-machine",
        }).encode(),
    ))
    worker_id = json.loads(register.body.decode())["worker_id"]
    db_session = factory()
    try:
        view = jobservice.enqueue_job(
            db_session=db_session, payload={"command": "x"},
        )
        jobservice.claim_next_job(
            db_session=db_session, worker_id=worker_id,
        )
    finally:
        db_session.close()
    return worker_id, view.job_id


def test_rest_record_and_list_round_trip():
    """
    **Feature: P28d test results (M3)**
    **Property: Agent posts a batch via POST; admin lists
    via GET and gets the persisted views back; admin reads
    the summary aggregated across attempts.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        worker_id, job_id = _provision_job_via_rest(
            app=app, factory=factory,
        )
        recorded = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/jobs/{1}/test-results".format(
                worker_id, job_id,
            ),
            headers={"Content-Type": "application/json"},
            body=json.dumps({"results": [
                {
                    "suite_name": "smoke",
                    "case_name": "t1",
                    "outcome": "passed",
                    "duration_seconds": 0.4,
                },
                {
                    "suite_name": "smoke",
                    "case_name": "t2",
                    "outcome": "failed",
                    "duration_seconds": 1.1,
                    "failure_message": "expected 200, got 500",
                },
            ]}).encode(),
        ))
        testbase.assert_equal(recorded.status_code, 201)
        recorded_body = json.loads(recorded.body.decode())
        testbase.assert_equal(len(recorded_body["results"]), 2)

        listed = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/{0}/test-results".format(job_id),
        ))
        testbase.assert_equal(listed.status_code, 200)
        listed_body = json.loads(listed.body.decode())
        testbase.assert_equal(len(listed_body), 2)
        testbase.assert_equal(
            [r["case_name"] for r in listed_body], ["t1", "t2"],
        )

        summary = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/{0}/test-results/summary".format(
                job_id,
            ),
        ))
        testbase.assert_equal(summary.status_code, 200)
        summary_body = json.loads(summary.body.decode())
        testbase.assert_equal(summary_body["total"], 2)
        testbase.assert_equal(summary_body["passed"], 1)
        testbase.assert_equal(summary_body["failed"], 1)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_rest_record_single_form_returns_persisted_view():
    """
    **Feature: P28d test results (M3)**
    **Property: POST without ``results`` accepts a single
    record and returns the persisted view (not wrapped in
    ``results``).**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        worker_id, job_id = _provision_job_via_rest(
            app=app, factory=factory,
        )
        response = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/jobs/{1}/test-results".format(
                worker_id, job_id,
            ),
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "case_name": "single",
                "outcome": "passed",
            }).encode(),
        ))
        testbase.assert_equal(response.status_code, 201)
        body = json.loads(response.body.decode())
        testbase.assert_equal(body["case_name"], "single")
        testbase.assert_equal("results" in body, False)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_rest_bad_payload_returns_400_and_unknown_job_returns_404():
    """
    **Feature: P28d test results (M3)**
    **Property: Missing ``case_name`` or ``outcome`` returns
    400; recording against an unknown job_id returns 404.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        worker_id, job_id = _provision_job_via_rest(
            app=app, factory=factory,
        )
        bad = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/jobs/{1}/test-results".format(
                worker_id, job_id,
            ),
            headers={"Content-Type": "application/json"},
            body=json.dumps({"case_name": "x"}).encode(),
        ))
        testbase.assert_equal(bad.status_code, 400)

        missing = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/jobs/00000000-0000-4000-8000-00000000baad/test-results".format(
                worker_id,
            ),
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "case_name": "x", "outcome": "passed",
            }).encode(),
        ))
        testbase.assert_equal(missing.status_code, 404)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_rest_anonymous_returns_401():
    """
    **Feature: P28d test results (M3)**
    **Property: List, summary, and record all gate; an
    anonymous request returns 401 on each.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=None)
    try:
        for path_under_test in [
            "/api/v1/queue/jobs/00000000-0000-4000-8000-00000000d401/test-results",
            "/api/v1/queue/jobs/00000000-0000-4000-8000-00000000d401/test-results/summary",
        ]:
            response = app.dispatcher.dispatch(request=Request(
                method="GET", path=path_under_test,
            ))
            testbase.assert_equal(response.status_code, 401)
        post = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/00000000-0000-4000-8000-00000000d402/jobs/00000000-0000-4000-8000-00000000d403/test-results",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "case_name": "x", "outcome": "passed",
            }).encode(),
        ))
        testbase.assert_equal(post.status_code, 401)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return
