"""
.. module:: test_p19c_results_route_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for POST /api/v1/runs/{run_id}/results/complete.

.. moduleauthor:: Code Craft AI LLC

Covers the result-manifest ingest endpoint added in PR p19c:

* 401 when mTLS-verified client common-name is absent.
* 404 when the run row does not exist.
* 400 when required ResultManifest fields are missing.
* 202 on the happy path.
* 409 when the result tree has not been written to the
  configured backend yet.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.ingest.result.errors import (
    ResultTreeNotFoundError,
)
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        body: Any = None,
        db_session: Optional[Any] = None,
        mtls_client_cn: Optional[str] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self._body: Any = body
        self.db_session: Optional[Any] = db_session
        if mtls_client_cn is not None:
            self.mtls_client_cn: str = mtls_client_cn
        return

    def json(self) -> Any:
        return self._body


class _FakeRun:
    def __init__(self) -> None:
        self.run_id: str = "run-1"
        return


class _FakeOutcome:
    def __init__(self) -> None:
        self.status: str = "scanned"
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_find_run(*, exists: bool) -> Any:
    patch = create_module_patch(runs_routes.run_repo, "find_run")
    mock = patch.activate()
    if exists is True:
        mock.configure(side_effect=lambda **kwargs: _FakeRun())
    else:
        mock.configure(side_effect=lambda **kwargs: None)
    return patch


_MANIFEST_BODY = {
    "run_id": "run-1",
    "client_id": "client-1",
    "format_tag": "testbase",
    "backend_key_prefix": "runs/run-1/",
    "completed_at": "2026-05-17T12:00:00+00:00",
    "terminal_outcome": "success",
}


def test_results_complete_returns_401_when_mtls_cn_absent():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: POST /runs/{id}/results/complete returns 401
    when no mTLS handshake has been forwarded by nginx.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1/results/complete",
        path_params={"run_id": "run-1"},
        body=_MANIFEST_BODY,
        db_session=object(),
    )
    response = runs_routes.handle_post_results_complete(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_results_complete_returns_404_when_run_unknown():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: An unknown run id returns 404 problem+json.**
    """
    patch = _patch_find_run(exists=False)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-missing/results/complete",
            path_params={"run_id": "run-missing"},
            body=_MANIFEST_BODY,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_results_complete(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_results_complete_returns_400_when_required_fields_missing():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A manifest missing required fields lists them in
    the problem's ``missing_fields`` extension.**
    """
    patch = _patch_find_run(exists=True)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/results/complete",
            path_params={"run_id": "run-1"},
            body={"run_id": "run-1"},
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_results_complete(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_true("client_id" in body["missing_fields"])
    testbase.assert_true("backend_key_prefix" in body["missing_fields"])
    return


def test_results_complete_returns_202_on_happy_path():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A well-formed manifest triggers scan_once and
    the handler returns 202 echoing the terminal outcome.**
    """
    captured: Dict[str, Any] = {}

    def fake_scan(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _FakeOutcome()

    run_patch = _patch_find_run(exists=True)
    scan_patch = create_module_patch(runs_routes.result_scanner, "scan_once")
    scan_mock = scan_patch.activate()
    scan_mock.configure(side_effect=fake_scan)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/results/complete",
            path_params={"run_id": "run-1"},
            body=_MANIFEST_BODY,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_results_complete(request)
    finally:
        scan_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-1")
    testbase.assert_equal(body["terminal_outcome"], "success")
    testbase.assert_equal(captured["tree_path"], "runs/run-1/")
    return


def test_results_complete_returns_409_when_tree_missing():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: ResultTreeNotFoundError from the scanner is
    mapped to 409 conflict with the backend_key_prefix in the
    problem extensions.**
    """
    def raise_missing(**kwargs: Any) -> Any:
        raise ResultTreeNotFoundError("tree not yet written")

    run_patch = _patch_find_run(exists=True)
    scan_patch = create_module_patch(runs_routes.result_scanner, "scan_once")
    scan_mock = scan_patch.activate()
    scan_mock.configure(side_effect=raise_missing)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/results/complete",
            path_params={"run_id": "run-1"},
            body=_MANIFEST_BODY,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_results_complete(request)
    finally:
        scan_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["backend_key_prefix"], "runs/run-1/")
    return
