"""
.. module:: test_p19c_progress_route_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for POST /api/v1/runs/{run_id}/progress.

.. moduleauthor:: Code Craft AI LLC

Covers the agent-facing progress ingest endpoint added in PR
p19c:

* 401 when no mTLS-verified client common-name has been
  forwarded by nginx.
* 404 when the run row does not exist.
* 422 / 400 when the body is malformed.
* 202 on a happy-path summary + records frame.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.ingest.progress.errors import (
    ProgressUnknownRunError,
)
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        body: Any = None,
        db_session: Optional[Any] = None,
        mtls_client_cn: Optional[str] = None,
        environ: Optional[Dict[str, str]] = None,
        scope: Optional[Dict[str, str]] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        if mtls_client_cn is not None:
            self.mtls_client_cn: str = mtls_client_cn
        if environ is not None:
            self.environ: Dict[str, str] = environ
        if scope is not None:
            self.scope: Dict[str, str] = scope
        return

    def json(self) -> Any:
        return self._body


class _FakeRun:
    def __init__(self, *, run_id: str = "run-1") -> None:
        self.run_id: str = run_id
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_find_run(*, exists: bool) -> Any:
    """
        Patch ``runs_routes.run_repo.find_run`` to return a stub
        row (or None when ``exists`` is False).
    """
    patch = create_module_patch(runs_routes.run_repo, "find_run")
    mock = patch.activate()
    if exists is True:
        mock.configure(side_effect=lambda **kwargs: _FakeRun())
    else:
        mock.configure(side_effect=lambda **kwargs: None)
    return patch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_progress_returns_401_when_mtls_cn_absent():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: POST /runs/{id}/progress returns 401 when no
    SSL_CLIENT_S_DN_CN has been forwarded by nginx -- proves
    the mTLS gate is in place even though nginx is not yet
    wired for client-cert auth.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1/progress",
        path_params={"run_id": "run-1"},
        body={"summary": {}},
        db_session=object(),
    )
    response = runs_routes.handle_post_progress(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_progress_returns_404_when_run_unknown():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: With mTLS satisfied but no run row matching the
    path id, the handler returns 404 problem+json.**
    """
    patch = _patch_find_run(exists=False)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-missing/progress",
            path_params={"run_id": "run-missing"},
            body={"summary": {
                "run_id": "run-missing",
                "client_id": "client-1",
                "format_tag": "testbase",
            }},
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_progress(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-missing")
    return


def test_progress_returns_400_when_body_missing_summary_and_records():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A ProgressFrame with neither ``summary`` nor
    ``records`` is rejected with 400.**
    """
    patch = _patch_find_run(exists=True)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/progress",
            path_params={"run_id": "run-1"},
            body={},
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_progress(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    return


def test_progress_returns_400_when_body_not_object():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A non-object request body is rejected with 400.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1/progress",
        path_params={"run_id": "run-1"},
        body=None,
        db_session=object(),
        mtls_client_cn="pod-client-cert",
    )
    response = runs_routes.handle_post_progress(request)
    testbase.assert_equal(response.status_code, 400)
    return


def test_progress_returns_202_on_happy_path():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A well-formed summary frame is forwarded to the
    progress service and the handler returns 202 with counters.**
    """
    captured: Dict[str, Any] = {}

    def fake_ingest_summary(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return object()

    run_patch = _patch_find_run(exists=True)
    svc_patch = create_module_patch(runs_routes.progress_service, "ingest_summary")
    svc_mock = svc_patch.activate()
    svc_mock.configure(side_effect=fake_ingest_summary)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/progress",
            path_params={"run_id": "run-1"},
            body={"summary": {
                "run_id": "run-1",
                "client_id": "client-7",
                "format_tag": "testbase",
                "tests_passed": 1,
                "tests_failed": 0,
                "tests_skipped": 0,
                "tests_errored": 0,
                "recorded_at": "2026-05-17T12:00:00+00:00",
            }},
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_progress(request)
    finally:
        svc_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["summaries_accepted"], 1)
    testbase.assert_equal(body["records_accepted"], 0)
    testbase.assert_equal(captured["authenticated_client_id"], "client-7")
    return


def test_progress_mtls_via_environ_key_is_accepted():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A SSL_CLIENT_S_DN_CN value forwarded via the
    WSGI environ dict is accepted as proof of mTLS handshake.**
    """
    run_patch = _patch_find_run(exists=True)
    svc_patch = create_module_patch(runs_routes.progress_service, "ingest_summary")
    svc_mock = svc_patch.activate()
    svc_mock.configure(side_effect=lambda **kwargs: object())
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/progress",
            path_params={"run_id": "run-1"},
            body={"summary": {
                "run_id": "run-1",
                "client_id": "client-7",
                "format_tag": "testbase",
                "tests_passed": 0,
                "tests_failed": 0,
                "tests_skipped": 0,
                "tests_errored": 0,
                "recorded_at": "2026-05-17T12:00:00+00:00",
            }},
            db_session=object(),
            environ={
                runs_routes.MTLS_CLIENT_CN_ENVIRON_KEY: "nginx-forwarded-cn",
            },
        )
        response = runs_routes.handle_post_progress(request)
    finally:
        svc_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    return
