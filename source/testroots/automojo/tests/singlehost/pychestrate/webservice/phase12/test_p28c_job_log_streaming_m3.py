"""
.. module:: test_p28c_job_log_streaming_m3
    :synopsis: Tests for the live job log streaming surface.

Covers:

* :func:`append_log_chunk` assigns a monotonically-increasing
  seq per job, copies the job's ``attempt`` onto the chunk,
  defaults stream to ``stdout``, and accepts unknown stream
  names (forward compat).
* :func:`append_log_chunk` raises LookupError for an unknown
  job.
* :func:`read_log_chunks` returns chunks in seq-asc order
  starting from ``since_seq+1``, clamped to the configured
  limit; ``since_seq=0`` (the default) returns from the
  beginning.
* :func:`read_log_chunks` clamps ``limit`` to ``[1, 1000]`` so
  a runaway long-poll can't OOM the API.
* :func:`latest_seq_for_job` returns 0 for an unknown / empty
  job; otherwise the max seq.
* The (job_id, seq) unique constraint guards against duplicate
  seqs in concurrent appends.
* Two attempts of the same job: chunks from attempt 1 stay
  visible after the retry, distinguishable by ``attempt``.
* REST round-trip: agent POSTs chunks under bearer auth;
  admin polls ``GET .../log/stream?since=N`` and gets
  ``{chunks, next_since}`` back; ``since=`` past the latest
  returns an empty list with ``next_since`` unchanged.
* REST returns 400 for a non-int ``since`` / ``limit``, 404
  for an unknown job.
* Anonymous tail returns 401.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import tempfile

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
    joblogservice,
    jobservice,
)
from automojo.pychestrate.webservice.workers import service as worker_service
from automojo.pychestrate.webservice.workers.joblogmodels import (
    LogStream,
)
from automojo.pychestrate.webservice.workers.models import WorkerKind

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p28c_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def _build_app() -> Tuple[PychestrateApplication, sessionmaker, str]:
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p28c-test-pepper"))
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
            identifier="00000000-0000-4000-8000-00000000d300",
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
            name="log-pi", kind=WorkerKind.REMOTE_MACHINE,
        )
        jv = jobservice.enqueue_job(
            db_session=db_session,
            payload={"command": "x"},
        )
        jobservice.claim_next_job(
            db_session=db_session, worker_id=wv.worker_id,
        )
    finally:
        db_session.close()
    return wv.worker_id, jv.job_id


def test_append_log_chunk_assigns_monotonic_seq_per_job():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: Each append for a given job_id gets the next
    sequence number (1, 2, 3, ...). Distinct jobs have
    independent sequences.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id, job_a = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            jv_b = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "y"},
            )
            v1 = joblogservice.append_log_chunk(
                db_session=db_session,
                job_id=job_a, worker_id=worker_id,
                text="line1",
            )
            v2 = joblogservice.append_log_chunk(
                db_session=db_session,
                job_id=job_a, worker_id=worker_id,
                text="line2",
            )
            v_b1 = joblogservice.append_log_chunk(
                db_session=db_session,
                job_id=jv_b.job_id, worker_id=worker_id,
                text="b1",
            )
        finally:
            db_session.close()
        testbase.assert_equal(v1.seq, 1)
        testbase.assert_equal(v2.seq, 2)
        testbase.assert_equal(v_b1.seq, 1)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_append_log_chunk_copies_attempt_from_job():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: The chunk's ``attempt`` mirrors the job's
    current attempt counter so a forensic viewer can split
    output between retried attempts.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id, job_id = _enqueue_and_claim(factory=factory)
        # Bump attempt by simulating a failed-with-retries report.
        db_session = factory()
        try:
            # Make the job retryable.
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
            jobservice.report_result(
                db_session=db_session, worker_id=worker_id,
                job_id=job_id, result_code=1,
            )
            # Re-claim for attempt 2.
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
            v = joblogservice.append_log_chunk(
                db_session=db_session,
                job_id=job_id, worker_id=worker_id,
                text="from attempt 2",
            )
        finally:
            db_session.close()
        testbase.assert_equal(v.attempt, 2)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_append_log_chunk_defaults_stream_and_accepts_custom():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: Stream defaults to ``stdout``; explicit values
    pass through (including operator-defined names — the
    column is a String, not an enum constraint, for forward
    compat).**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            default = joblogservice.append_log_chunk(
                db_session=db_session, job_id=job_id,
                worker_id=None, text="x",
            )
            stderr = joblogservice.append_log_chunk(
                db_session=db_session, job_id=job_id,
                worker_id=None, text="x", stream="stderr",
            )
            custom = joblogservice.append_log_chunk(
                db_session=db_session, job_id=job_id,
                worker_id=None, text="x", stream="metric",
            )
        finally:
            db_session.close()
        testbase.assert_equal(default.stream, LogStream.STDOUT.value)
        testbase.assert_equal(stderr.stream, LogStream.STDERR.value)
        testbase.assert_equal(custom.stream, "metric")
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_append_log_chunk_unknown_job_raises_lookup_error():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: append_log_chunk for an unknown job_id raises
    LookupError (the REST handler maps to 404).**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            try:
                joblogservice.append_log_chunk(
                    db_session=db_session,
                    job_id="00000000-0000-4000-8000-00000000baad",
                    worker_id=None, text="x",
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


def test_read_log_chunks_returns_since_seq_asc_with_limit():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: read_log_chunks returns rows whose
    ``seq > since_seq``, ascending, capped at ``limit``.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            for n in range(1, 6):
                joblogservice.append_log_chunk(
                    db_session=db_session,
                    job_id=job_id, worker_id=None,
                    text="line-{0}".format(n),
                )
            from_zero = joblogservice.read_log_chunks(
                db_session=db_session, job_id=job_id, since_seq=0,
            )
            after_two = joblogservice.read_log_chunks(
                db_session=db_session, job_id=job_id, since_seq=2,
            )
            limited = joblogservice.read_log_chunks(
                db_session=db_session, job_id=job_id,
                since_seq=0, limit=2,
            )
        finally:
            db_session.close()
        testbase.assert_equal(
            [c.seq for c in from_zero], [1, 2, 3, 4, 5],
        )
        testbase.assert_equal(
            [c.seq for c in after_two], [3, 4, 5],
        )
        testbase.assert_equal([c.seq for c in limited], [1, 2])
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_read_log_chunks_clamps_limit_into_valid_range():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: ``limit < 1`` is clamped to 1; ``limit >
    1000`` is clamped to 1000 — so a misbehaving consumer
    can't request unbounded payloads.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            joblogservice.append_log_chunk(
                db_session=db_session, job_id=job_id,
                worker_id=None, text="a",
            )
            joblogservice.append_log_chunk(
                db_session=db_session, job_id=job_id,
                worker_id=None, text="b",
            )
            zero = joblogservice.read_log_chunks(
                db_session=db_session, job_id=job_id, limit=0,
            )
            jumbo = joblogservice.read_log_chunks(
                db_session=db_session, job_id=job_id, limit=10000,
            )
        finally:
            db_session.close()
        testbase.assert_equal(len(zero), 1)  # clamped to 1.
        testbase.assert_equal(len(jumbo), 2)  # both rows fit.
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_latest_seq_for_job_returns_zero_for_empty():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: latest_seq_for_job returns 0 when the job has
    no chunks; otherwise the max seq. Lets the consumer pick
    "tail from now" semantics.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_claim(factory=factory)
        db_session = factory()
        try:
            empty = joblogservice.latest_seq_for_job(
                db_session=db_session, job_id=job_id,
            )
            joblogservice.append_log_chunk(
                db_session=db_session, job_id=job_id,
                worker_id=None, text="x",
            )
            joblogservice.append_log_chunk(
                db_session=db_session, job_id=job_id,
                worker_id=None, text="y",
            )
            after = joblogservice.latest_seq_for_job(
                db_session=db_session, job_id=job_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(empty, 0)
        testbase.assert_equal(after, 2)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_rest_append_and_tail_round_trip():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: Agent POSTs chunks; admin polls
    ``/queue/jobs/{id}/log/stream?since=N``; chunks come back
    seq-ascending with ``next_since`` advanced past the
    last delivered chunk.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        register = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/register",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "name": "log-rest-pi", "kind": "remote-machine",
            }).encode(),
        ))
        worker_id = json.loads(register.body.decode())["worker_id"]
        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "long-test"},
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()

        for line in ["one\n", "two\n", "three\n"]:
            posted = app.dispatcher.dispatch(request=Request(
                method="POST",
                path="/api/v1/workers/{0}/jobs/{1}/log".format(
                    worker_id, enqueued.job_id,
                ),
                headers={"Content-Type": "application/json"},
                body=json.dumps({"text": line}).encode(),
            ))
            testbase.assert_equal(posted.status_code, 201)

        # First poll — full payload.
        first = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/{0}/log/stream".format(
                enqueued.job_id,
            ),
        ))
        testbase.assert_equal(first.status_code, 200)
        body1 = json.loads(first.body.decode())
        testbase.assert_equal(len(body1["chunks"]), 3)
        testbase.assert_equal(body1["next_since"], 3)
        testbase.assert_equal(
            [c["text"] for c in body1["chunks"]],
            ["one\n", "two\n", "three\n"],
        )

        # Second poll using the cursor — empty.
        empty = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/{0}/log/stream".format(
                enqueued.job_id,
            ),
            query_string=b"since=3",
        ))
        body2 = json.loads(empty.body.decode())
        testbase.assert_equal(body2["chunks"], [])
        testbase.assert_equal(body2["next_since"], 3)

        # New chunks arrive.
        app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/jobs/{1}/log".format(
                worker_id, enqueued.job_id,
            ),
            headers={"Content-Type": "application/json"},
            body=json.dumps({"text": "four\n"}).encode(),
        ))
        third = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/{0}/log/stream".format(
                enqueued.job_id,
            ),
            query_string=b"since=3",
        ))
        body3 = json.loads(third.body.decode())
        testbase.assert_equal(len(body3["chunks"]), 1)
        testbase.assert_equal(body3["chunks"][0]["seq"], 4)
        testbase.assert_equal(body3["next_since"], 4)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_rest_tail_unknown_job_returns_404():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: GET /queue/jobs/{unknown}/log/stream returns
    404 — the dashboard distinguishes "no chunks yet" from
    "wrong id".**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        response = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/00000000-0000-4000-8000-00000000bad1/log/stream",
        ))
        testbase.assert_equal(response.status_code, 404)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_rest_tail_bad_since_or_limit_returns_400():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: Non-int ``since`` / ``limit`` query strings
    return 400 rather than coercing to 0.**
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
        bad_since = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/{0}/log/stream".format(
                view.job_id,
            ),
            query_string=b"since=nope",
        ))
        testbase.assert_equal(bad_since.status_code, 400)
        bad_limit = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/{0}/log/stream".format(
                view.job_id,
            ),
            query_string=b"limit=nope",
        ))
        testbase.assert_equal(bad_limit.status_code, 400)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_rest_tail_anonymous_returns_401():
    """
    **Feature: P28c live job log streaming (M3)**
    **Property: The tail endpoint is gated system-admin; an
    anonymous request gets 401.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=None)
    try:
        response = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/00000000-0000-4000-8000-00000000d301/log/stream",
        ))
        testbase.assert_equal(response.status_code, 401)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return
