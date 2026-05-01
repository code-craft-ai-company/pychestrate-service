"""
.. module:: test_p28b_job_artifacts_m3
    :synopsis: Tests for the worker-job artifact upload + read surface.

Covers:

* :func:`upload_artifact` writes the row, computes a SHA-256
  hash, copies the job's current ``attempt`` onto the artifact,
  and returns an :class:`ArtifactView`.
* :func:`upload_artifact` rejects an empty ``name``, raises
  :class:`LookupError` for an unknown job, and raises
  :class:`ArtifactTooLargeError` over the inline cap.
* :func:`list_artifacts_for_job` returns rows oldest-first.
* :func:`read_artifact_metadata` enforces the optional
  ``scoped_job_id`` defence.
* :func:`read_artifact_content` returns the raw bytes verbatim.
* :func:`_resolve_max_inline_bytes` reads the env override and
  ignores garbage / non-positive values.
* REST round-trip via the dispatcher: agent uploads via
  ``POST /workers/.../artifacts``; admin lists via
  ``GET /queue/jobs/{id}/artifacts``; admin downloads via
  ``GET /queue/artifacts/{id}/content`` and gets the raw
  bytes back with the recorded content_type.
* The download endpoint exposes ``X-Artifact-Hash`` and
  ``X-Artifact-Name`` headers so an operator can verify the
  bytes against the metadata record.
* Anonymous list/download returns 401.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.00"


import base64
import hashlib
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
    artifactservice,
    jobservice,
)
from automojo.pychestrate.webservice.workers import service as worker_service
from automojo.pychestrate.webservice.workers.artifactservice import (
    ArtifactJobMismatchError,
    ArtifactNotFoundError,
    ArtifactTooLargeError,
)
from automojo.pychestrate.webservice.workers.models import WorkerKind

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p28b_", suffix=".db")
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
    set_active_pepper(pepper=SecretBytes(b"p28b-test-pepper"))
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
            identifier="00000000-0000-4000-8000-00000000d200",
            display_name="Admin",
            roles={"system-admin"},
        ),
        scheme="test-injection",
    )


def _agent_context(*, client_id: str) -> AuthenticationContext:
    return AuthenticationContext(
        principal=Principal(
            identifier=client_id,
            display_name="agent:test",
            roles={"agent"},
        ),
        scheme="bearer-client",
        attributes={"client_id": client_id, "pod_name": "raspi-01"},
    )


def _wrap(*, app, context: Optional[AuthenticationContext]) -> None:
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = context
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped
    return


def _enqueue_and_register(
        *,
        factory: sessionmaker,
    ) -> Tuple[str, str]:
    """
        Helper: register a worker, enqueue a job, claim it,
        return ``(worker_id, job_id)``.
    """
    db_session = factory()
    try:
        worker_view = worker_service.register_worker(
            db_session=db_session,
            name="art-pi", kind=WorkerKind.REMOTE_MACHINE,
        )
        job_view = jobservice.enqueue_job(
            db_session=db_session,
            payload={"command": "x"},
        )
        jobservice.claim_next_job(
            db_session=db_session, worker_id=worker_view.worker_id,
        )
    finally:
        db_session.close()
    return worker_view.worker_id, job_view.job_id


def test_upload_artifact_writes_row_and_hashes_content():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: upload_artifact persists the row, copies the
    job's current ``attempt``, and stamps a SHA-256 of the
    bytes that callers can verify against later.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        worker_id, job_id = _enqueue_and_register(factory=factory)
        content = b"first attempt log\nstuff happened\n"
        db_session = factory()
        try:
            view = artifactservice.upload_artifact(
                db_session=db_session,
                job_id=job_id,
                worker_id=worker_id,
                name="run.log",
                content=content,
                kind="log",
                content_type="text/plain",
                attributes={"compressed": False},
            )
        finally:
            db_session.close()
        testbase.assert_equal(view.name, "run.log")
        testbase.assert_equal(view.kind, "log")
        testbase.assert_equal(view.content_type, "text/plain")
        testbase.assert_equal(view.size_bytes, len(content))
        testbase.assert_equal(
            view.content_hash, hashlib.sha256(content).hexdigest(),
        )
        testbase.assert_equal(view.attempt, 1)
        testbase.assert_equal(view.attributes, {"compressed": False})
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_upload_artifact_rejects_empty_name():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: upload_artifact requires a non-empty ``name``;
    a buggy YAML doesn't end up writing a nameless row.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_register(factory=factory)
        db_session = factory()
        try:
            try:
                artifactservice.upload_artifact(
                    db_session=db_session,
                    job_id=job_id,
                    worker_id=None,
                    name="   ",
                    content=b"x",
                )
                raised = False
            except ValueError:
                raised = True
        finally:
            db_session.close()
        testbase.assert_equal(raised, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_upload_artifact_unknown_job_raises_lookup_error():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: upload_artifact for an unknown ``job_id``
    raises LookupError (REST translates to 404).**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            try:
                artifactservice.upload_artifact(
                    db_session=db_session,
                    job_id="00000000-0000-4000-8000-00000000beef",
                    worker_id=None,
                    name="x",
                    content=b"x",
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


def test_upload_artifact_enforces_inline_cap():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: Content over ``max_inline_bytes`` raises
    ArtifactTooLargeError instead of silently dropping or
    truncating.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_register(factory=factory)
        db_session = factory()
        try:
            try:
                artifactservice.upload_artifact(
                    db_session=db_session,
                    job_id=job_id,
                    worker_id=None,
                    name="big.bin",
                    content=b"x" * 200,
                    max_inline_bytes=100,
                )
                raised = False
            except ArtifactTooLargeError as exc:
                raised = True
                err_text = str(exc)
            testbase.assert_equal(raised, True)
            testbase.assert_equal("200" in err_text, True)
            testbase.assert_equal("100" in err_text, True)
        finally:
            db_session.close()
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_list_artifacts_for_job_oldest_first():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: list_artifacts_for_job returns rows in
    upload order so a forensic viewer can replay evidence in
    sequence.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_register(factory=factory)
        db_session = factory()
        try:
            artifactservice.upload_artifact(
                db_session=db_session,
                job_id=job_id, worker_id=None,
                name="first.log", content=b"1",
            )
            artifactservice.upload_artifact(
                db_session=db_session,
                job_id=job_id, worker_id=None,
                name="second.log", content=b"2",
            )
            artifactservice.upload_artifact(
                db_session=db_session,
                job_id=job_id, worker_id=None,
                name="third.log", content=b"3",
            )
            views = artifactservice.list_artifacts_for_job(
                db_session=db_session, job_id=job_id,
            )
        finally:
            db_session.close()
        names = [v.name for v in views]
        testbase.assert_equal(names, ["first.log", "second.log", "third.log"])
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_read_artifact_metadata_scope_check_blocks_url_tampering():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: When ``scoped_job_id`` is supplied,
    read_artifact_metadata raises ArtifactJobMismatchError if
    the stored ``job_id`` differs — defends against URL
    tampering through job-scoped REST paths.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_a = _enqueue_and_register(factory=factory)
        # Need a second job to scope-mismatch against.
        db_session = factory()
        try:
            job_b_view = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "y"},
            )
            view = artifactservice.upload_artifact(
                db_session=db_session,
                job_id=job_a, worker_id=None,
                name="a.log", content=b"a",
            )
        finally:
            db_session.close()
        db_session = factory()
        try:
            try:
                artifactservice.read_artifact_metadata(
                    db_session=db_session,
                    artifact_id=view.artifact_id,
                    scoped_job_id=job_b_view.job_id,
                )
                raised = False
            except ArtifactJobMismatchError:
                raised = True
        finally:
            db_session.close()
        testbase.assert_equal(raised, True)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_read_artifact_content_returns_bytes_verbatim():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: read_artifact_content returns exactly the
    bytes that were uploaded (binary-safe round-trip,
    including non-UTF-8 / null bytes / arbitrary bytes).**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        _, job_id = _enqueue_and_register(factory=factory)
        payload = bytes(range(256))  # 0x00..0xFF — covers nulls.
        db_session = factory()
        try:
            view = artifactservice.upload_artifact(
                db_session=db_session,
                job_id=job_id, worker_id=None,
                name="raw.bin", content=payload,
                content_type="application/octet-stream",
            )
            got = artifactservice.read_artifact_content(
                db_session=db_session,
                artifact_id=view.artifact_id,
            )
        finally:
            db_session.close()
        testbase.assert_equal(got, payload)
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_resolve_max_inline_bytes_env_override_and_fallbacks():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: env override is honoured; non-int / non-
    positive values fall back to the default rather than
    crashing the bootstrap.**
    """
    bigger = artifactservice._resolve_max_inline_bytes(environment={
        "PYCHESTRATE_ARTIFACT_MAX_INLINE_BYTES": "26214400",
    })
    testbase.assert_equal(bigger, 26214400)
    fallback_for_garbage = artifactservice._resolve_max_inline_bytes(
        environment={
            "PYCHESTRATE_ARTIFACT_MAX_INLINE_BYTES": "not-a-number",
        },
    )
    testbase.assert_equal(fallback_for_garbage, 10 * 1024 * 1024)
    fallback_for_zero = artifactservice._resolve_max_inline_bytes(
        environment={
            "PYCHESTRATE_ARTIFACT_MAX_INLINE_BYTES": "0",
        },
    )
    testbase.assert_equal(fallback_for_zero, 10 * 1024 * 1024)
    return


def test_rest_upload_list_download_round_trip():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: An agent uploads via POST, an admin lists via
    GET, and an admin downloads via GET /content — the
    download body is the raw bytes and the response carries
    Content-Type + X-Artifact-Hash + X-Artifact-Name.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        # Use admin path to register a worker and enqueue.
        register = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/register",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "name": "art-rest-pi", "kind": "remote-machine",
            }).encode(),
        ))
        testbase.assert_equal(register.status_code, 201)
        worker_id = json.loads(register.body.decode())["worker_id"]

        db_session = factory()
        try:
            enqueued = jobservice.enqueue_job(
                db_session=db_session,
                payload={"command": "x"},
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=worker_id,
            )
        finally:
            db_session.close()

        # Upload the artifact (admin path; same gate as agent).
        content_bytes = b"PNG\x89\x00\x01\x02 fake-screenshot"
        upload = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/jobs/{1}/artifacts".format(
                worker_id, enqueued.job_id,
            ),
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "name": "shot.png",
                "kind": "screenshot",
                "content_type": "image/png",
                "content_b64": base64.b64encode(content_bytes).decode("ascii"),
            }).encode(),
        ))
        testbase.assert_equal(upload.status_code, 201)
        artifact_meta = json.loads(upload.body.decode())
        artifact_id = artifact_meta["artifact_id"]
        testbase.assert_equal(artifact_meta["size_bytes"], len(content_bytes))
        testbase.assert_equal(
            artifact_meta["content_hash"],
            hashlib.sha256(content_bytes).hexdigest(),
        )

        # Admin lists artifacts for the job.
        listed = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/jobs/{0}/artifacts".format(
                enqueued.job_id,
            ),
        ))
        testbase.assert_equal(listed.status_code, 200)
        listed_body = json.loads(listed.body.decode())
        testbase.assert_equal(len(listed_body), 1)
        testbase.assert_equal(listed_body[0]["artifact_id"], artifact_id)

        # Admin downloads the bytes.
        downloaded = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/queue/artifacts/{0}/content".format(
                artifact_id,
            ),
        ))
        testbase.assert_equal(downloaded.status_code, 200)
        testbase.assert_equal(downloaded.body, content_bytes)
        # Headers carry the verifiable metadata.
        # Webworks Response stores headers as a dict-like; values
        # may be strings or bytes — coerce.
        def _hdr(name: str) -> str:
            for k, v in downloaded.headers.items():
                if k.lower() == name.lower():
                    if isinstance(v, bytes):
                        return v.decode("utf-8")
                    return str(v)
            return ""
        testbase.assert_equal(_hdr("Content-Type"), "image/png")
        testbase.assert_equal(
            _hdr("X-Artifact-Hash"),
            hashlib.sha256(content_bytes).hexdigest(),
        )
        testbase.assert_equal(_hdr("X-Artifact-Name"), "shot.png")
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return


def test_rest_too_large_upload_returns_413():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: An over-cap upload returns HTTP 413 (Payload
    Too Large) — the agent / SDK can detect the size limit
    cleanly without parsing detail strings.**
    """
    # Tighten the cap by bypassing the env (the service helper
    # accepts an explicit max_inline_bytes; the REST path uses
    # the env helper, so we set the env here).
    os.environ["PYCHESTRATE_ARTIFACT_MAX_INLINE_BYTES"] = "100"
    try:
        app, factory, path = _build_app()
        _wrap(app=app, context=_admin_context())
        try:
            register = app.dispatcher.dispatch(request=Request(
                method="POST",
                path="/api/v1/workers/register",
                headers={"Content-Type": "application/json"},
                body=json.dumps({
                    "name": "fat-pi", "kind": "remote-machine",
                }).encode(),
            ))
            worker_id = json.loads(register.body.decode())["worker_id"]
            db_session = factory()
            try:
                enqueued = jobservice.enqueue_job(
                    db_session=db_session, payload={"command": "x"},
                )
                jobservice.claim_next_job(
                    db_session=db_session, worker_id=worker_id,
                )
            finally:
                db_session.close()
            response = app.dispatcher.dispatch(request=Request(
                method="POST",
                path="/api/v1/workers/{0}/jobs/{1}/artifacts".format(
                    worker_id, enqueued.job_id,
                ),
                headers={"Content-Type": "application/json"},
                body=json.dumps({
                    "name": "big.bin",
                    "content_b64": base64.b64encode(b"x" * 1000).decode("ascii"),
                }).encode(),
            ))
            testbase.assert_equal(response.status_code, 413)
        finally:
            app.shutdown(wait=True)
            os.unlink(path)
    finally:
        os.environ.pop(
            "PYCHESTRATE_ARTIFACT_MAX_INLINE_BYTES", None,
        )
    return


def test_anonymous_artifact_access_returns_401():
    """
    **Feature: P28b job artifacts (M3)**
    **Property: Both list and download endpoints are gated;
    an unauthenticated request gets 401.**
    """
    app, factory, path = _build_app()
    _wrap(app=app, context=None)
    try:
        for path_under_test in [
            "/api/v1/queue/jobs/00000000-0000-4000-8000-00000000d201/artifacts",
            "/api/v1/queue/artifacts/00000000-0000-4000-8000-00000000d202",
            "/api/v1/queue/artifacts/00000000-0000-4000-8000-00000000d203/content",
        ]:
            response = app.dispatcher.dispatch(request=Request(
                method="GET", path=path_under_test,
            ))
            testbase.assert_equal(response.status_code, 401)
    finally:
        app.shutdown(wait=True)
        os.unlink(path)
    return
