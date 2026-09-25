"""
.. module:: test_p19l_presigned_result_upload_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the presigned result-upload surface (PR p19l).

.. moduleauthor:: Code Craft AI LLC

Covers the two operations added in PR p19l:

* ``POST /api/v1/runs/{run_id}/artifacts:presign``

  * 401 when no mTLS client common-name was forwarded.
  * 404 when the run row does not exist.
  * 403 when the cert common-name does not own the run's dispatch.
  * 409 when the run has reached a terminal state.
  * 422 when too many artifact paths are requested.
  * 200 with one presigned target per requested path.

* ``PUT /api/v1/runs/{run_id}/artifacts/_local-upload``

  * 403 when the upload signature has been tampered with.
  * 403 when the upload signature has expired.
  * 201 round-trip: presign -> PUT bytes -> file lands at the
    result-tree path.

The presign signing helpers (HMAC sign / verify, path
canonicalization, batch limits) are also unit-tested directly.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import shutil
import tempfile

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from ccai import testbase
from ccai.testbase.mocking import create_instance_patch, create_module_patch

from ccai.pychestrate.webservice.jobs.results import presign
from ccai.pychestrate.webservice.jobs.results.backend import (
    SharedResultsBackend,
)
from ccai.pychestrate.webservice.jobs.results.errors import (
    ArtifactPathInvalidError,
    PresignSignatureInvalidError,
    TooManyArtifactPathsError,
)
from ccai.pychestrate.webservice.jobs.run.state.enums import RunState
from ccai.pychestrate.webservice.runs.restapi.v1 import artifacts_routes


_TEST_SECRET = b"p19l-unit-test-signing-secret"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        body: Any = None,
        raw_body: Optional[bytes] = None,
        db_session: Optional[Any] = None,
        mtls_client_cn: Optional[str] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: Dict[str, Any] = (
            query_params if query_params is not None else {}
        )
        self._json_body: Any = body
        self.body: Optional[bytes] = raw_body
        self.db_session: Optional[Any] = db_session
        if mtls_client_cn is not None:
            self.mtls_client_cn: str = mtls_client_cn
        return

    def json(self) -> Any:
        return self._json_body


class _FakeRun:
    def __init__(self, *, state: RunState) -> None:
        self.run_id: str = "run-1"
        self.state: RunState = state
        return


class _FakeReceipt:
    def __init__(self, *, client_id: str) -> None:
        self.client_id: str = client_id
        return


def _decode_body(response: Any) -> Any:
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _patch_find_run(*, run_row: Optional[_FakeRun]) -> Any:
    patch = create_module_patch(artifacts_routes.run_repo, "find_run")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: run_row)
    return patch


def _patch_find_receipt(*, receipt: Optional[_FakeReceipt]) -> Any:
    patch = create_module_patch(artifacts_routes.receipt_repo, "find_by_run")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: receipt)
    return patch


# ---------------------------------------------------------------------------
# presign helper unit tests
# ---------------------------------------------------------------------------


def test_canonicalize_relative_path_rejects_parent_traversal():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a relative path containing a `..` segment is
    rejected by canonicalize_relative_path.**
    """
    raised = False
    try:
        presign.canonicalize_relative_path(raw="artifacts/../../etc/passwd")
    except ArtifactPathInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_canonicalize_relative_path_rejects_absolute_path():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: an absolute path is rejected.**
    """
    raised = False
    try:
        presign.canonicalize_relative_path(raw="/etc/passwd")
    except ArtifactPathInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_validate_artifact_path_batch_rejects_over_cap_count():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a batch with more than MAX_ARTIFACT_PATHS paths is
    rejected with TooManyArtifactPathsError.**
    """
    over_cap = ["file-{}.log".format(idx) for idx in range(presign.MAX_ARTIFACT_PATHS + 1)]
    raised = False
    try:
        presign.validate_artifact_path_batch(paths=over_cap)
    except TooManyArtifactPathsError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_verify_upload_signature_round_trip_accepts_valid_signature():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a signature minted by compute_upload_signature
    verifies cleanly against the same secret.**
    """
    now = datetime.now(timezone.utc)
    expires_epoch = int((now + timedelta(minutes=15)).timestamp())
    signature = presign.compute_upload_signature(
        secret=_TEST_SECRET,
        run_id="run-1",
        relative_path="artifacts/foo.log",
        expires_epoch=expires_epoch,
    )
    presign.verify_upload_signature(
        secret=_TEST_SECRET,
        run_id="run-1",
        relative_path="artifacts/foo.log",
        expires_epoch=expires_epoch,
        signature=signature,
        now=now,
    )
    return


def test_verify_upload_signature_rejects_tampered_signature():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a signature minted for one path does not verify
    against a different path (tamper rejection).**
    """
    now = datetime.now(timezone.utc)
    expires_epoch = int((now + timedelta(minutes=15)).timestamp())
    signature = presign.compute_upload_signature(
        secret=_TEST_SECRET,
        run_id="run-1",
        relative_path="artifacts/foo.log",
        expires_epoch=expires_epoch,
    )
    raised = False
    try:
        presign.verify_upload_signature(
            secret=_TEST_SECRET,
            run_id="run-1",
            relative_path="artifacts/EVIL.log",
            expires_epoch=expires_epoch,
            signature=signature,
            now=now,
        )
    except PresignSignatureInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_verify_upload_signature_rejects_expired_signature():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a signature whose expiry is in the past is
    rejected even when the HMAC itself is correct.**
    """
    now = datetime.now(timezone.utc)
    expires_epoch = int((now - timedelta(minutes=1)).timestamp())
    signature = presign.compute_upload_signature(
        secret=_TEST_SECRET,
        run_id="run-1",
        relative_path="artifacts/foo.log",
        expires_epoch=expires_epoch,
    )
    raised = False
    try:
        presign.verify_upload_signature(
            secret=_TEST_SECRET,
            run_id="run-1",
            relative_path="artifacts/foo.log",
            expires_epoch=expires_epoch,
            signature=signature,
            now=now,
        )
    except PresignSignatureInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# POST /api/v1/runs/{run_id}/artifacts:presign
# ---------------------------------------------------------------------------


_PRESIGN_BODY = {
    "paths": ["testrun_summary.json", "artifacts/foo.log"],
}


def test_presign_returns_401_when_mtls_cn_absent():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: POST .../artifacts:presign returns 401 when no
    mTLS handshake has been forwarded by nginx.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1/artifacts:presign",
        path_params={"run_id": "run-1"},
        body=_PRESIGN_BODY,
        db_session=object(),
    )
    response = artifacts_routes.handle_presign_artifacts(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_presign_returns_404_when_run_unknown():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: an unknown run id returns 404.**
    """
    artifacts_routes.set_presign_signing_secret(secret=_TEST_SECRET)
    artifacts_routes.set_shared_results_backend(
        backend=SharedResultsBackend(backend_driver="local-test"),
    )
    run_patch = _patch_find_run(run_row=None)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-missing/artifacts:presign",
            path_params={"run_id": "run-missing"},
            body=_PRESIGN_BODY,
            db_session=object(),
            mtls_client_cn="client-1",
        )
        response = artifacts_routes.handle_presign_artifacts(request)
    finally:
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_presign_returns_403_when_cert_does_not_own_run():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a cert common-name that does not match the run's
    dispatch-receipt client_id is rejected with 403.**
    """
    artifacts_routes.set_presign_signing_secret(secret=_TEST_SECRET)
    artifacts_routes.set_shared_results_backend(
        backend=SharedResultsBackend(backend_driver="local-test"),
    )
    run_patch = _patch_find_run(run_row=_FakeRun(state=RunState.RUNNING))
    receipt_patch = _patch_find_receipt(
        receipt=_FakeReceipt(client_id="the-real-owner"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/artifacts:presign",
            path_params={"run_id": "run-1"},
            body=_PRESIGN_BODY,
            db_session=object(),
            mtls_client_cn="an-impostor",
        )
        response = artifacts_routes.handle_presign_artifacts(request)
    finally:
        receipt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    return


def test_presign_returns_409_when_run_terminal():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a run already in a terminal state (COMPLETED) no
    longer accepts result upload -- 409.**
    """
    artifacts_routes.set_presign_signing_secret(secret=_TEST_SECRET)
    artifacts_routes.set_shared_results_backend(
        backend=SharedResultsBackend(backend_driver="local-test"),
    )
    run_patch = _patch_find_run(run_row=_FakeRun(state=RunState.COMPLETED))
    receipt_patch = _patch_find_receipt(
        receipt=_FakeReceipt(client_id="client-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/artifacts:presign",
            path_params={"run_id": "run-1"},
            body=_PRESIGN_BODY,
            db_session=object(),
            mtls_client_cn="client-1",
        )
        response = artifacts_routes.handle_presign_artifacts(request)
    finally:
        receipt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    return


def test_presign_returns_422_when_too_many_paths():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a presign request asking for more than the path
    cap is rejected with 422.**
    """
    artifacts_routes.set_presign_signing_secret(secret=_TEST_SECRET)
    artifacts_routes.set_shared_results_backend(
        backend=SharedResultsBackend(backend_driver="local-test"),
    )
    run_patch = _patch_find_run(run_row=_FakeRun(state=RunState.RUNNING))
    receipt_patch = _patch_find_receipt(
        receipt=_FakeReceipt(client_id="client-1"),
    )
    over_cap = ["file-{}.log".format(idx) for idx in range(presign.MAX_ARTIFACT_PATHS + 1)]
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/artifacts:presign",
            path_params={"run_id": "run-1"},
            body={"paths": over_cap},
            db_session=object(),
            mtls_client_cn="client-1",
        )
        response = artifacts_routes.handle_presign_artifacts(request)
    finally:
        receipt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 422)
    return


def test_presign_returns_200_with_one_target_per_path():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a well-formed presign request returns 200 with one
    upload target per requested path.**
    """
    artifacts_routes.set_presign_signing_secret(secret=_TEST_SECRET)
    artifacts_routes.set_shared_results_backend(
        backend=SharedResultsBackend(backend_driver="local-test"),
    )
    run_patch = _patch_find_run(run_row=_FakeRun(state=RunState.RUNNING))
    receipt_patch = _patch_find_receipt(
        receipt=_FakeReceipt(client_id="client-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/artifacts:presign",
            path_params={"run_id": "run-1"},
            body=_PRESIGN_BODY,
            db_session=object(),
            mtls_client_cn="client-1",
        )
        response = artifacts_routes.handle_presign_artifacts(request)
    finally:
        receipt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(len(body["uploads"]), 2)
    testbase.assert_equal(body["uploads"][0]["path"], "testrun_summary.json")
    testbase.assert_true("_local-upload" in body["uploads"][0]["put_url"])
    return


# ---------------------------------------------------------------------------
# PUT /api/v1/runs/{run_id}/artifacts/_local-upload
# ---------------------------------------------------------------------------


def _query_from_url(*, put_url: str) -> Dict[str, str]:
    """Extract the query parameters from a minted put_url."""
    parsed = urlparse(put_url)
    raw = parse_qs(parsed.query)
    rtnval: Dict[str, str] = {}
    for key, values in raw.items():
        if len(values) > 0:
            rtnval[key] = values[0]
    return rtnval


def test_local_upload_returns_403_on_tampered_signature():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: PUT .../_local-upload rejects a request whose
    signature does not match the path with 403.**
    """
    tmp_root = tempfile.mkdtemp(prefix="p19l-")
    try:
        artifacts_routes.set_presign_signing_secret(secret=_TEST_SECRET)
        artifacts_routes.set_shared_results_backend(
            backend=SharedResultsBackend(backend_driver="local-test"),
        )
        now = datetime.now(timezone.utc)
        expires_epoch = int((now + timedelta(minutes=15)).timestamp())
        signature = presign.compute_upload_signature(
            secret=_TEST_SECRET,
            run_id="run-1",
            relative_path="artifacts/foo.log",
            expires_epoch=expires_epoch,
        )
        run_patch = _patch_find_run(run_row=_FakeRun(state=RunState.RUNNING))
        try:
            request = _FakeRequest(
                path="/api/v1/runs/run-1/artifacts/_local-upload",
                path_params={"run_id": "run-1"},
                query_params={
                    # path differs from what the signature was minted for.
                    "path": "artifacts/EVIL.log",
                    "expires": str(expires_epoch),
                    "signature": signature,
                },
                raw_body=b"payload",
                db_session=object(),
                mtls_client_cn="client-1",
            )
            response = artifacts_routes.handle_local_upload(request)
        finally:
            run_patch.deactivate()
        testbase.assert_equal(response.status_code, 403)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return


def test_local_upload_returns_403_on_expired_signature():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: PUT .../_local-upload rejects an expired signed
    URL with 403.**
    """
    artifacts_routes.set_presign_signing_secret(secret=_TEST_SECRET)
    artifacts_routes.set_shared_results_backend(
        backend=SharedResultsBackend(backend_driver="local-test"),
    )
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    expires_epoch = int(past.timestamp())
    signature = presign.compute_upload_signature(
        secret=_TEST_SECRET,
        run_id="run-1",
        relative_path="artifacts/foo.log",
        expires_epoch=expires_epoch,
    )
    run_patch = _patch_find_run(run_row=_FakeRun(state=RunState.RUNNING))
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/artifacts/_local-upload",
            path_params={"run_id": "run-1"},
            query_params={
                "path": "artifacts/foo.log",
                "expires": str(expires_epoch),
                "signature": signature,
            },
            raw_body=b"payload",
            db_session=object(),
            mtls_client_cn="client-1",
        )
        response = artifacts_routes.handle_local_upload(request)
    finally:
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 403)
    return


def test_presign_then_upload_round_trip_lands_file_at_result_tree_path():
    """
    **Feature: presigned-result-upload PR p19l**
    **Property: a presign-minted URL, when PUT to, writes the body
    under the run's allocated backend_key_prefix.**
    """
    tmp_root = tempfile.mkdtemp(prefix="p19l-")
    try:
        backend = SharedResultsBackend(backend_driver="local-test")
        artifacts_routes.set_presign_signing_secret(secret=_TEST_SECRET)
        artifacts_routes.set_shared_results_backend(backend=backend)

        prefix = os.path.join(tmp_root, "proj", "results", "run-1")

        # The local-upload handler resolves the prefix via
        # backend.resolve(); patch resolve to return our temp prefix.
        class _Allocation:
            def __init__(self) -> None:
                self.backend_key_prefix: str = prefix
                return

        resolve_patch = create_instance_patch(backend, "resolve")
        resolve_mock = resolve_patch.activate()
        resolve_mock.configure(side_effect=lambda **kwargs: _Allocation())

        # Mint a real presigned URL via the backend.
        targets = backend.presign_put(
            run_id="run-1",
            version_prefix="/api/v1",
            relative_paths=["artifacts/foo.log"],
            signing_secret=_TEST_SECRET,
        )
        query = _query_from_url(put_url=targets[0].put_url)

        run_patch = _patch_find_run(run_row=_FakeRun(state=RunState.RUNNING))
        try:
            request = _FakeRequest(
                path="/api/v1/runs/run-1/artifacts/_local-upload",
                path_params={"run_id": "run-1"},
                query_params=query,
                raw_body=b"hello-result-tree",
                db_session=object(),
                mtls_client_cn="client-1",
            )
            response = artifacts_routes.handle_local_upload(request)
        finally:
            run_patch.deactivate()
            resolve_patch.deactivate()

        testbase.assert_equal(response.status_code, 201)
        landed = os.path.join(prefix, "artifacts", "foo.log")
        testbase.assert_true(os.path.isfile(landed))
        with open(landed, "rb") as handle:
            stored = handle.read()
        testbase.assert_equal(stored, b"hello-result-tree")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return


def test_presign_accepts_a_run_awaiting_its_cancel():
    """
    **Feature: run cancel (E2E-09, live E2E finding)**
    **Property: a run in CANCEL_REQUESTED still accepts result upload --
    the pod uploads what the stopped job produced before reporting the
    cancelled outcome; it used to get 409.**
    """
    artifacts_routes.set_presign_signing_secret(secret=_TEST_SECRET)
    artifacts_routes.set_shared_results_backend(
        backend=SharedResultsBackend(backend_driver="local-test"),
    )
    run_patch = _patch_find_run(run_row=_FakeRun(state=RunState.CANCEL_REQUESTED))
    receipt_patch = _patch_find_receipt(
        receipt=_FakeReceipt(client_id="client-1"),
    )
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/artifacts:presign",
            path_params={"run_id": "run-1"},
            body=_PRESIGN_BODY,
            db_session=object(),
            mtls_client_cn="client-1",
        )
        response = artifacts_routes.handle_presign_artifacts(request)
    finally:
        receipt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_true(response.status_code != 409)
    return
