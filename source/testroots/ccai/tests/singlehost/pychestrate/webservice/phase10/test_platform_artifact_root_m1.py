"""
.. module:: test_platform_artifact_root_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression locks for the configured run-artifact root
               (audit LD-14).

.. moduleauthor:: Code Craft AI LLC

Run artifacts used to be written wherever the relative allocation
prefix ``<project>/results/<yyyy>/<mm>/<dd>/<job>/<run>`` resolved
against the process working directory -- inside the code checkout
under gunicorn's ``--chdir source/site``. These tests pin:

* the artifact root comes from ``PYCHESTRATE_ARTIFACT_ROOT`` and
  defaults to ``<presence_dir>/artifacts``;
* a relative prefix resolves under the artifact root, whatever the
  working directory is;
* prefixes that escape the root, and client-supplied absolute
  prefixes, are refused;
* the presigned upload sink writes under the artifact root;
* the operator download route reads from the artifact root;
* the results-complete route scans the anchored tree and refuses an
  absolute prefix from the pod;
* the systemd unit keeps the presence directory writable.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import shutil
import tempfile

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from ccai import testbase
from ccai.testbase.mocking import create_instance_patch, create_module_patch

from ccai.pychestrate.webservice.jobs.results import artifact_root
from ccai.pychestrate.webservice.jobs.results.backend import (
    SharedResultsBackend,
)
from ccai.pychestrate.webservice.jobs.results.errors import (
    ArtifactPathInvalidError,
)
from ccai.pychestrate.webservice.jobs.run.state.enums import RunState
from ccai.pychestrate.webservice.runs.restapi.v1 import (
    artifacts_routes,
    runs_routes,
)


_SECRET = b"ld14-unit-test-signing-secret"
_PREFIX = "hello-echo-poc/results/2026/09/22/rpa-hello-echo/run-1"


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
            auth_principal: Optional[Any] = None,
            mtls_client_cn: Optional[str] = None
        ) -> None:
        self.path = path
        self.path_params = path_params if path_params is not None else {}
        self.query_params = query_params if query_params is not None else {}
        self._json_body = body
        self.body = raw_body
        self.db_session = db_session
        self.auth_principal = auth_principal
        if mtls_client_cn is not None:
            self.mtls_client_cn = mtls_client_cn
        return

    def json(self) -> Any:
        return self._json_body


class _FakeRun:
    def __init__(self, *, state: RunState) -> None:
        self.run_id = "run-1"
        self.state = state
        self.project_id = "project-1"
        return


class _FakeDecision:
    def __init__(self) -> None:
        self.allowed = True
        return


class _Allocation:
    def __init__(self, *, prefix: str) -> None:
        self.backend_key_prefix = prefix
        return


class _Workspace:
    """
        A temporary artifact root plus a separate temporary working
        directory, so a test can tell "under the root" from "under
        the CWD".
    """

    def __init__(self) -> None:
        self.root = tempfile.mkdtemp(prefix="ld14-artifacts-")
        self.cwd = tempfile.mkdtemp(prefix="ld14-cwd-")
        self._previous_cwd = os.getcwd()
        return

    def __enter__(self) -> "_Workspace":
        artifact_root.set_artifact_root_override(root=self.root)
        os.chdir(self.cwd)
        return self

    def __exit__(self, *exc_info: Any) -> None:
        os.chdir(self._previous_cwd)
        artifact_root.set_artifact_root_override(root=None)
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.cwd, ignore_errors=True)
        return


def _query_from_url(*, put_url: str) -> Dict[str, str]:
    raw = parse_qs(urlparse(put_url).query)
    rtnval = {key: values[0] for key, values in raw.items() if len(values) > 0}
    return rtnval


def _decode_body(response: Any) -> Any:
    rtnval = json.loads(response.body.decode("utf-8"))
    return rtnval


# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------


def test_artifact_root_comes_from_the_environment_variable():
    """
    **Feature: run artifact root (LD-14)**
    **Property: PYCHESTRATE_ARTIFACT_ROOT sets the artifact root.**
    """
    configured = tempfile.mkdtemp(prefix="ld14-env-root-")
    previous = os.environ.get(artifact_root.ENV_ARTIFACT_ROOT, None)
    os.environ[artifact_root.ENV_ARTIFACT_ROOT] = configured
    try:
        resolved = artifact_root.resolve_artifact_root()
    finally:
        if previous is None:
            del os.environ[artifact_root.ENV_ARTIFACT_ROOT]
        else:
            os.environ[artifact_root.ENV_ARTIFACT_ROOT] = previous
        os.rmdir(configured)
    testbase.assert_equal(resolved, configured)
    return


def test_artifact_root_defaults_to_the_presence_directory():
    """
    **Feature: run artifact root (LD-14)**
    **Property: with no configuration the artifact root is
    <presence_dir>/artifacts.**
    """
    from ccai.thisapp.personavariables import PersonaVariables

    previous = os.environ.pop(artifact_root.ENV_ARTIFACT_ROOT, None)
    try:
        resolved = artifact_root.resolve_artifact_root()
    finally:
        if previous is not None:
            os.environ[artifact_root.ENV_ARTIFACT_ROOT] = previous
    expected = os.path.abspath(
        os.path.join(os.path.expanduser(PersonaVariables.AM_PRESENCE_DIR), "artifacts")
    )
    testbase.assert_equal(resolved, expected)
    return


def test_relative_prefix_resolves_under_the_root_not_the_working_directory():
    """
    **Feature: run artifact root (LD-14)**
    **Property: a relative allocation prefix resolves under the
    artifact root regardless of the process working directory.**
    """
    with _Workspace() as workspace:
        resolved = artifact_root.resolve_result_tree_path(backend_key_prefix=_PREFIX)
    testbase.assert_equal(resolved, os.path.join(workspace.root, _PREFIX))
    return


def test_prefix_escaping_the_root_is_refused():
    """
    **Feature: run artifact root (LD-14)**
    **Property: a prefix that climbs out of the artifact root with
    ".." raises ArtifactPathInvalidError.**
    """
    raised = False
    with _Workspace():
        try:
            artifact_root.resolve_result_tree_path(backend_key_prefix="../outside/run-1")
        except ArtifactPathInvalidError:
            raised = True
    testbase.assert_equal(raised, True)
    return


def test_client_supplied_absolute_prefix_is_refused():
    """
    **Feature: run artifact root (LD-14)**
    **Property: with allow_absolute=False an absolute prefix raises
    ArtifactPathInvalidError instead of naming an arbitrary host
    directory.**
    """
    raised = False
    try:
        artifact_root.resolve_result_tree_path(
            backend_key_prefix="/etc", allow_absolute=False,
        )
    except ArtifactPathInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# Upload sink / download route / results-complete
# ---------------------------------------------------------------------------


def _upload(*, prefix: str, relative_path: str, body: bytes) -> Any:
    backend = SharedResultsBackend(backend_driver="local-test")
    artifacts_routes.set_presign_signing_secret(secret=_SECRET)
    artifacts_routes.set_shared_results_backend(backend=backend)
    targets = backend.presign_put(
        run_id="run-1",
        version_prefix="/api/v1",
        relative_paths=[relative_path],
        signing_secret=_SECRET,
    )
    resolve_patch = create_instance_patch(backend, "resolve")
    resolve_mock = resolve_patch.activate()
    resolve_mock.configure(side_effect=lambda **kwargs: _Allocation(prefix=prefix))
    run_patch = create_module_patch(artifacts_routes.run_repo, "find_run")
    run_mock = run_patch.activate()
    run_mock.configure(side_effect=lambda **kwargs: _FakeRun(state=RunState.RUNNING))
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/artifacts/_local-upload",
            path_params={"run_id": "run-1"},
            query_params=_query_from_url(put_url=targets[0].put_url),
            raw_body=body,
            db_session=object(),
            mtls_client_cn="client-1",
        )
        rtnval = artifacts_routes.handle_local_upload(request)
    finally:
        run_patch.deactivate()
        resolve_patch.deactivate()
        artifacts_routes.set_shared_results_backend(backend=None)
        artifacts_routes.set_presign_signing_secret(secret=None)
    return rtnval


def test_upload_lands_under_the_artifact_root():
    """
    **Feature: run artifact root (LD-14)**
    **Property: a presigned upload for a run with a relative prefix
    writes the file under the artifact root.**
    """
    with _Workspace() as workspace:
        response = _upload(prefix=_PREFIX, relative_path="logs/out.log", body=b"hello")
        landed = os.path.join(workspace.root, _PREFIX, "logs", "out.log")
        exists = os.path.isfile(landed)
    testbase.assert_equal((response.status_code, exists), (201, True))
    return


def test_upload_writes_nothing_under_the_working_directory():
    """
    **Feature: run artifact root (LD-14)**
    **Property: the upload leaves the process working directory (the
    code checkout under gunicorn) untouched.**
    """
    with _Workspace() as workspace:
        _upload(prefix=_PREFIX, relative_path="logs/out.log", body=b"hello")
        cwd_entries = os.listdir(workspace.cwd)
    testbase.assert_equal(cwd_entries, [])
    return


def test_download_reads_from_the_artifact_root():
    """
    **Feature: run artifact root (LD-14)**
    **Property: the operator download route streams the file stored
    under the artifact root for a relative allocation prefix.**
    """
    with _Workspace() as workspace:
        target = os.path.join(workspace.root, _PREFIX, "report.txt")
        os.makedirs(os.path.dirname(target))
        with open(target, "wb") as handle:
            handle.write(b"stored-under-root")

        backend = SharedResultsBackend(backend_driver="local-test")
        artifacts_routes.set_shared_results_backend(backend=backend)
        patches: List[Any] = []
        resolve_patch = create_instance_patch(backend, "resolve")
        resolve_patch.activate().configure(side_effect=lambda **kwargs: _Allocation(prefix=_PREFIX))
        patches.append(resolve_patch)
        perm_patch = create_module_patch(artifacts_routes.rbac_evaluator, "check_permission")
        perm_patch.activate().configure(side_effect=lambda **kwargs: _FakeDecision())
        patches.append(perm_patch)
        run_patch = create_module_patch(artifacts_routes.run_repo, "find_run")
        run_patch.activate().configure(side_effect=lambda **kwargs: _FakeRun(state=RunState.COMPLETED))
        patches.append(run_patch)
        try:
            response = artifacts_routes.handle_get_artifact(
                _FakeRequest(
                    path="/api/v1/runs/run-1/artifacts/report.txt",
                    path_params={"run_id": "run-1", "artifact_path": "report.txt"},
                    db_session=object(),
                    auth_principal=object(),
                )
            )
            streamed = b"".join(response.iter_content())
        finally:
            for patch in reversed(patches):
                patch.deactivate()
            artifacts_routes.set_shared_results_backend(backend=None)
    testbase.assert_equal((response.status_code, streamed), (200, b"stored-under-root"))
    return


_MANIFEST = {
    "client_id": "client-1",
    "format_tag": "testbase-v1",
    "backend_key_prefix": _PREFIX,
    "completed_at": "2026-09-22T12:00:00Z",
    "terminal_outcome": "success",
}


def _post_results_complete(*, manifest: Dict[str, Any], captured: Dict[str, Any]) -> Any:
    def fake_scan(**kwargs: Any) -> Any:
        captured.update(kwargs)

        class _Outcome:
            status = "scanned"

        return _Outcome()

    run_patch = create_module_patch(runs_routes.run_repo, "find_run")
    run_patch.activate().configure(side_effect=lambda **kwargs: _FakeRun(state=RunState.RUNNING))
    scan_patch = create_module_patch(runs_routes.result_scanner, "scan_once")
    scan_patch.activate().configure(side_effect=fake_scan)
    advance_patch = create_module_patch(runs_routes, "_advance_run_state_from_outcome")
    advance_patch.activate().configure(return_value=None)
    event_patch = create_module_patch(runs_routes, "_emit_result_manifest_event")
    event_patch.activate().configure(return_value=None)
    cancel_patch = create_module_patch(runs_routes, "_close_cancel_request_on_cancelled_result")
    cancel_patch.activate().configure(return_value=None)
    try:
        rtnval = runs_routes.handle_post_results_complete(
            _FakeRequest(
                path="/api/v1/runs/run-1/results/complete",
                path_params={"run_id": "run-1"},
                body=manifest,
                db_session=object(),
                mtls_client_cn="client-1",
            )
        )
    finally:
        for patch in (cancel_patch, event_patch, advance_patch, scan_patch, run_patch):
            patch.deactivate()
    return rtnval


def test_results_complete_scans_the_tree_under_the_artifact_root():
    """
    **Feature: run artifact root (LD-14)**
    **Property: the testbase result scanner is pointed at the
    manifest prefix anchored under the artifact root.**
    """
    captured: Dict[str, Any] = {}
    with _Workspace() as workspace:
        _post_results_complete(manifest=dict(_MANIFEST), captured=captured)
    testbase.assert_equal(captured.get("tree_path"), os.path.join(workspace.root, _PREFIX))
    return


def test_results_complete_refuses_an_absolute_prefix_from_the_pod():
    """
    **Feature: run artifact root (LD-14)**
    **Property: a manifest whose backend_key_prefix is an absolute
    host path is answered 400 and never scanned.**
    """
    captured: Dict[str, Any] = {}
    manifest = dict(_MANIFEST)
    manifest["backend_key_prefix"] = "/etc"
    with _Workspace():
        response = _post_results_complete(manifest=manifest, captured=captured)
    testbase.assert_equal((response.status_code, "tree_path" in captured), (400, False))
    return


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(
        os.path.join(here, "..", "..", "..", "..", "..", "..", "..", "..")
    )
    return rtnval


def test_systemd_unit_keeps_the_presence_directory_writable():
    """
    **Feature: run artifact root (LD-14)**
    **Property: the unit's ReadWritePaths include the presence
    directory that holds the default artifact root.**
    """
    path = os.path.join(_repo_root(), "deployment", "pychestrate.service.template")
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    writable: List[str] = []
    for line in lines:
        if line.startswith("ReadWritePaths="):
            writable.extend(line[len("ReadWritePaths="):].split())
    testbase.assert_true("/home/@USER@/pychestrate" in writable)
    return
