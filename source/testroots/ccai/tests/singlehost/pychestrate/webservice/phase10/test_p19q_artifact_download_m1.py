"""
.. module:: test_p19q_artifact_download_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for GET /api/v1/runs/{run_id}/artifacts/{artifact_path}.

.. moduleauthor:: Code Craft AI LLC

Covers the operator-facing artifact download route:

* register_artifacts_routes attaches the GET wildcard route.
* 503 when no db session is bound.
* 401 when no auth principal is bound.
* 403 when the principal does not hold ``system:runs.read``.
* 404 when the run row does not exist.
* 400 when the artifact path carries a traversal segment.
* 404 when the run has no shared-results allocation.
* 404 when the file is absent from the result tree.
* 200 streaming an inert text artifact inline with ``nosniff``.
* HTML artifacts are forced to ``application/octet-stream`` +
  ``Content-Disposition: attachment`` (untrusted job output must
  never render in the service origin).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import shutil
import tempfile

from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai import testbase
from ccai.testbase.mocking import create_instance_patch, create_module_patch

from ccai.pychestrate.webservice.jobs.results.backend import (
    SharedResultsBackend,
)
from ccai.pychestrate.webservice.jobs.results.errors import (
    AllocationNotFoundError,
)
from ccai.pychestrate.webservice.jobs.run.state.enums import RunState
from ccai.pychestrate.webservice.runs.restapi.v1 import artifacts_routes


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        db_session: Optional[Any] = None,
        auth_principal: Optional[Any] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: Dict[str, Any] = {}
        self.db_session: Optional[Any] = db_session
        self.auth_principal: Optional[Any] = auth_principal
        return

    def json(self) -> Any:
        return None


class _FakeApp:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[str, ...], Callable]] = []
        return

    def attach_route(
        self, path: str, methods: Optional[List[str]] = None
    ) -> Callable:
        resolved_methods = tuple(methods if methods is not None else ["GET"])

        def decorator(func: Callable) -> Callable:
            self.calls.append((path, resolved_methods, func))
            rtnval = func
            return rtnval

        rtnval = decorator
        return rtnval


class _FakePrincipal:
    def __init__(self) -> None:
        self.user_id: str = "user-1"
        return


class _FakeRun:
    def __init__(self) -> None:
        self.run_id: str = "run-1"
        self.state: RunState = RunState.COMPLETED
        return


class _FakeDecision:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed: bool = allowed
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _streamed_bytes(response: Any) -> bytes:
    chunks = list(response.iter_content())
    rtnval = b"".join(chunks)
    return rtnval


def _patch_check_permission(*, allowed: bool) -> Any:
    patch = create_module_patch(
        artifacts_routes.rbac_evaluator, "check_permission",
    )
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _FakeDecision(allowed=allowed))
    return patch


def _patch_find_run(*, run_row: Optional[_FakeRun]) -> Any:
    patch = create_module_patch(artifacts_routes.run_repo, "find_run")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: run_row)
    return patch


def _request_for(*, artifact_path: str) -> _FakeRequest:
    rtnval = _FakeRequest(
        path="/api/v1/runs/run-1/artifacts/{}".format(artifact_path),
        path_params={"run_id": "run-1", "artifact_path": artifact_path},
        db_session=object(),
        auth_principal=_FakePrincipal(),
    )
    return rtnval


class _DownloadHarness:
    """
        Bundles the seam patches + temp result tree a download
        happy-path test needs, so each test reads as intent.
    """

    def __init__(self) -> None:
        self.tmp_root: str = tempfile.mkdtemp(prefix="p19q-")
        self.prefix: str = os.path.join(self.tmp_root, "proj", "results", "run-1")
        self.backend: SharedResultsBackend = SharedResultsBackend(
            backend_driver="local-test",
        )
        self._patches: List[Any] = []
        return

    def start(self) -> None:
        artifacts_routes.set_shared_results_backend(backend=self.backend)

        prefix = self.prefix

        class _Allocation:
            def __init__(self) -> None:
                self.backend_key_prefix: str = prefix
                return

        resolve_patch = create_instance_patch(self.backend, "resolve")
        resolve_mock = resolve_patch.activate()
        resolve_mock.configure(side_effect=lambda **kwargs: _Allocation())
        self._patches.append(resolve_patch)

        self._patches.append(_patch_check_permission(allowed=True))
        self._patches.append(_patch_find_run(run_row=_FakeRun()))
        return

    def write_artifact(self, *, relative_path: str, body: bytes) -> None:
        destination = os.path.join(self.prefix, relative_path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as handle:
            handle.write(body)
        return

    def stop(self) -> None:
        for patch in reversed(self._patches):
            patch.deactivate()
        artifacts_routes.set_shared_results_backend(backend=None)
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        return


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_artifacts_routes_attaches_download_endpoint():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: register_artifacts_routes attaches the GET
    wildcard download route alongside the presign + local-upload
    operations.**
    """
    app = _FakeApp()
    artifacts_routes.register_artifacts_routes(app=app, version_prefix="/api/v1")
    pairs = tuple((path, methods) for path, methods, _ in app.calls)
    expected_pair = (
        "/api/v1/runs/{run_id}/artifacts/{artifact_path:path}",
        ("GET",),
    )
    testbase.assert_true(expected_pair in pairs)
    return


# ---------------------------------------------------------------------------
# Auth sweep
# ---------------------------------------------------------------------------


def test_get_artifact_returns_503_when_session_missing():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: 503 problem when the request-scoped db session is
    not bound.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1/artifacts/foo.log",
        path_params={"run_id": "run-1", "artifact_path": "foo.log"},
        db_session=None,
    )
    response = artifacts_routes.handle_get_artifact(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_get_artifact_returns_401_when_no_principal():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: 401 when no AuthPrincipal has been bound by the
    session middleware -- the download is operator-facing, not
    mTLS-gated.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1/artifacts/foo.log",
        path_params={"run_id": "run-1", "artifact_path": "foo.log"},
        db_session=object(),
        auth_principal=None,
    )
    response = artifacts_routes.handle_get_artifact(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_get_artifact_returns_403_when_permission_denied():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: 403 when the principal does not hold
    system:runs.read.**
    """
    patch = _patch_check_permission(allowed=False)
    try:
        response = artifacts_routes.handle_get_artifact(
            _request_for(artifact_path="foo.log"),
        )
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["required_permission"], "system:runs.read")
    return


# ---------------------------------------------------------------------------
# Validation + lookup failures
# ---------------------------------------------------------------------------


def test_get_artifact_returns_404_when_run_unknown():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: 404 problem when the run row does not exist.**
    """
    backend = SharedResultsBackend(backend_driver="local-test")
    artifacts_routes.set_shared_results_backend(backend=backend)
    perm_patch = _patch_check_permission(allowed=True)
    run_patch = _patch_find_run(run_row=None)
    try:
        response = artifacts_routes.handle_get_artifact(
            _request_for(artifact_path="foo.log"),
        )
    finally:
        run_patch.deactivate()
        perm_patch.deactivate()
        artifacts_routes.set_shared_results_backend(backend=None)
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-1")
    return


def test_get_artifact_returns_400_on_traversal_path():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: a `..` traversal segment in the artifact path is
    rejected with 400 before any filesystem access.**
    """
    backend = SharedResultsBackend(backend_driver="local-test")
    artifacts_routes.set_shared_results_backend(backend=backend)
    perm_patch = _patch_check_permission(allowed=True)
    run_patch = _patch_find_run(run_row=_FakeRun())
    try:
        response = artifacts_routes.handle_get_artifact(
            _request_for(artifact_path="../../etc/passwd"),
        )
    finally:
        run_patch.deactivate()
        perm_patch.deactivate()
        artifacts_routes.set_shared_results_backend(backend=None)
    testbase.assert_equal(response.status_code, 400)
    return


def test_get_artifact_returns_404_when_allocation_missing():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: a run with no shared-results allocation returns
    404 -- there is no result tree to read from.**
    """
    backend = SharedResultsBackend(backend_driver="local-test")
    artifacts_routes.set_shared_results_backend(backend=backend)

    def raise_missing(**kwargs: Any) -> Any:
        raise AllocationNotFoundError("no allocation")

    resolve_patch = create_instance_patch(backend, "resolve")
    resolve_mock = resolve_patch.activate()
    resolve_mock.configure(side_effect=raise_missing)
    perm_patch = _patch_check_permission(allowed=True)
    run_patch = _patch_find_run(run_row=_FakeRun())
    try:
        response = artifacts_routes.handle_get_artifact(
            _request_for(artifact_path="foo.log"),
        )
    finally:
        run_patch.deactivate()
        perm_patch.deactivate()
        resolve_patch.deactivate()
        artifacts_routes.set_shared_results_backend(backend=None)
    testbase.assert_equal(response.status_code, 404)
    return


def test_get_artifact_returns_404_when_file_absent():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: 404 problem carrying run_id + artifact_path when
    the file does not exist in the allocated result tree.**
    """
    harness = _DownloadHarness()
    harness.start()
    try:
        response = artifacts_routes.handle_get_artifact(
            _request_for(artifact_path="missing/nothing.log"),
        )
    finally:
        harness.stop()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["artifact_path"], "missing/nothing.log")
    return


# ---------------------------------------------------------------------------
# Download happy paths + content-type policy
# ---------------------------------------------------------------------------


def test_get_artifact_streams_text_artifact_inline_with_nosniff():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: an inert text artifact streams back 200 with
    text/plain, inline disposition, the exact stored bytes, and
    X-Content-Type-Options: nosniff.**
    """
    harness = _DownloadHarness()
    harness.start()
    try:
        harness.write_artifact(
            relative_path="artifacts/console.log",
            body=b"line-1\nline-2\n",
        )
        response = artifacts_routes.handle_get_artifact(
            _request_for(artifact_path="artifacts/console.log"),
        )
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            response.headers["Content-Type"], "text/plain; charset=utf-8",
        )
        testbase.assert_equal(
            response.headers["X-Content-Type-Options"], "nosniff",
        )
        testbase.assert_true(
            response.headers["Content-Disposition"].startswith("inline;"),
        )
        testbase.assert_equal(response.headers["Content-Length"], "14")
        testbase.assert_equal(_streamed_bytes(response), b"line-1\nline-2\n")
    finally:
        harness.stop()
    return


def test_get_artifact_forces_html_to_attachment_octet_stream():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: an HTML artifact -- untrusted job output -- is
    never served renderable: content type is
    application/octet-stream and the disposition is attachment,
    so the browser downloads instead of executing it in the
    service origin.**
    """
    harness = _DownloadHarness()
    harness.start()
    try:
        harness.write_artifact(
            relative_path="testsummary.html",
            body=b"<script>alert(1)</script>",
        )
        response = artifacts_routes.handle_get_artifact(
            _request_for(artifact_path="testsummary.html"),
        )
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            response.headers["Content-Type"], "application/octet-stream",
        )
        testbase.assert_true(
            response.headers["Content-Disposition"].startswith("attachment;"),
        )
        testbase.assert_equal(
            response.headers["X-Content-Type-Options"], "nosniff",
        )
        testbase.assert_equal(
            _streamed_bytes(response), b"<script>alert(1)</script>",
        )
    finally:
        harness.stop()
    return


def test_get_artifact_serves_json_artifact_as_json():
    """
    **Feature: run-detail artifacts PR p19q**
    **Property: a .json artifact serves inline as
    application/json.**
    """
    harness = _DownloadHarness()
    harness.start()
    try:
        harness.write_artifact(
            relative_path="testrun_summary.json",
            body=b"{\"result\": \"PASSED\"}",
        )
        response = artifacts_routes.handle_get_artifact(
            _request_for(artifact_path="testrun_summary.json"),
        )
        testbase.assert_equal(response.status_code, 200)
        testbase.assert_equal(
            response.headers["Content-Type"], "application/json",
        )
    finally:
        harness.stop()
    return
