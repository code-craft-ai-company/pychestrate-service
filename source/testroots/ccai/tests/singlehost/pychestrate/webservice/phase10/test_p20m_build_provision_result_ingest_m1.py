"""
.. module:: test_p20m_build_provision_result_ingest_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for build + provision result-ingest (PR p20m).

.. moduleauthor:: Code Craft AI LLC

Covers the job-kind-aware completion path
(:mod:`ingest.result.completion`) plus the
``POST /api/v1/runs/{run_id}/results/complete`` routing:

* a ``format_tag=build`` ResultManifest advances the BuildRun to a
  terminal state and registers the uploaded artifacts;
* a ``format_tag=provision`` ResultManifest advances the InfraRun
  to a terminal state;
* a build manifest reporting ``terminal_outcome=failure`` lands the
  BuildRun in FAILED;
* the run-state machine row is driven to a terminal state;
* a ``format_tag=testbase`` manifest still routes to the testbase
  scanner unchanged (backward compatibility).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.ingest.result import completion
from ccai.pychestrate.webservice.jobs.run.state import (
    RunEvent,
    create_run as create_run_state,
    get_snapshot as get_run_state_snapshot,
    transition as transition_run_state,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts import (
    repository as build_artifacts_repository,
)
from ccai.pychestrate.webservice.orchestration.build.models import (
    BuildRun,
    BuildRunState,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.models import (
    InfraAction,
    InfraRun,
    InfraRunState,
)
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000020a0"
ENVIRONMENT_UUID = "00000000-0000-4000-8000-0000000020a1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_build_run(*, db_session: Any, run_id: str) -> None:
    """
        Insert a RUNNING BuildRun row + a run-state row parked at
        DISPATCHING -- the shape a dispatched build run carries
        before its results land.
    """
    row = BuildRun(
        run_id=run_id,
        project_id=PROJECT_UUID,
        runner_kind="makefile",
        repro_digest_sha256="a" * 64,
        state=BuildRunState.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.flush()
    db_session.commit()

    create_run_state(
        db_session=db_session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_type="build-makefile",
    )
    transition_run_state(
        db_session=db_session,
        run_id=run_id,
        event=RunEvent.DISPATCH_STARTED,
        actor="system:test",
    )
    return


def _seed_infra_run(*, db_session: Any, run_id: str) -> None:
    """
        Insert a RUNNING InfraRun row and a run-state row parked at
        DISPATCHING -- the shape a dispatched provisioning run
        carries before its results land.
    """
    row = InfraRun(
        run_id=run_id,
        project_id=PROJECT_UUID,
        environment_id=ENVIRONMENT_UUID,
        driver_name="terraform",
        action=InfraAction.APPLY,
        state=InfraRunState.RUNNING,
        inputs={},
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.flush()
    db_session.commit()

    create_run_state(
        db_session=db_session,
        run_id=run_id,
        project_id=PROJECT_UUID,
        job_type="provision-terraform",
    )
    transition_run_state(
        db_session=db_session,
        run_id=run_id,
        event=RunEvent.DISPATCH_STARTED,
        actor="system:test",
    )
    return


def _build_manifest(
        *,
        run_id: str,
        format_tag: str,
        terminal_outcome: str,
        files: Optional[list] = None
    ) -> Dict[str, Any]:
    """
        Build a ResultManifest dict shaped like the one the
        ``pychestrate-client`` result uploader posts.
    """
    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "client_id": "00000000-0000-4000-8000-0000000020c0",
        "format_tag": format_tag,
        "backend_key_prefix": "runs/{}/output".format(run_id),
        "completed_at": "2026-05-20T12:00:00+00:00",
        "terminal_outcome": terminal_outcome,
    }
    if files is not None:
        manifest["extras"] = {"file_count": len(files), "files": files}
    return manifest


# ---------------------------------------------------------------------------
# complete_build_run
# ---------------------------------------------------------------------------


def test_build_manifest_advances_build_run_to_completed():
    """
    **Feature: p20m build + provision result ingest**
    **Property: A format_tag=build ResultManifest reporting
    terminal_outcome=success advances the BuildRun to COMPLETED.**
    """
    engine, db_session = build_in_memory_session()
    try:
        run_id = new_uuid()
        _seed_build_run(db_session=db_session, run_id=run_id)

        manifest = _build_manifest(
            run_id=run_id,
            format_tag="build",
            terminal_outcome="success",
            files=[
                {
                    "relative_path": "image.tar",
                    "size_bytes": 4096,
                    "sha256": "b" * 64,
                },
            ],
        )
        outcome = completion.complete_build_run(
            db_session=db_session,
            run_id=run_id,
            manifest=manifest,
        )
        testbase.assert_equal(outcome.domain_state, "completed")
        testbase.assert_equal(outcome.artifacts_recorded, 1)
    finally:
        db_session.close()
        engine.dispose()
    return


def test_build_manifest_registers_artifacts_queryably():
    """
    **Feature: p20m build + provision result ingest**
    **Property: The uploaded artifact files are registered as a
    build-artifacts manifest so GET /builds/{id}/artifacts returns
    them.**
    """
    engine, db_session = build_in_memory_session()
    try:
        run_id = new_uuid()
        _seed_build_run(db_session=db_session, run_id=run_id)

        manifest = _build_manifest(
            run_id=run_id,
            format_tag="build",
            terminal_outcome="success",
            files=[
                {"relative_path": "a.bin", "size_bytes": 1, "sha256": "c" * 64},
                {"relative_path": "b.bin", "size_bytes": 2, "sha256": "d" * 64},
            ],
        )
        outcome = completion.complete_build_run(
            db_session=db_session,
            run_id=run_id,
            manifest=manifest,
        )
        testbase.assert_true(outcome.manifest_id is not None)

        manifest_row = build_artifacts_repository.find_manifest_by_build_run(
            db_session=db_session, build_run_id=run_id,
        )
        testbase.assert_true(manifest_row is not None)
        entries = build_artifacts_repository.list_entries_for_manifest(
            db_session=db_session,
            manifest_id=str(manifest_row.manifest_id),
        )
        testbase.assert_equal(len(entries), 2)
    finally:
        db_session.close()
        engine.dispose()
    return


def test_build_manifest_failure_outcome_lands_failed():
    """
    **Feature: p20m build + provision result ingest**
    **Property: A build manifest reporting terminal_outcome=failure
    advances the BuildRun to FAILED.**
    """
    engine, db_session = build_in_memory_session()
    try:
        run_id = new_uuid()
        _seed_build_run(db_session=db_session, run_id=run_id)

        manifest = _build_manifest(
            run_id=run_id,
            format_tag="build",
            terminal_outcome="failure",
        )
        outcome = completion.complete_build_run(
            db_session=db_session,
            run_id=run_id,
            manifest=manifest,
        )
        testbase.assert_equal(outcome.domain_state, "failed")
    finally:
        db_session.close()
        engine.dispose()
    return


def test_build_manifest_drives_run_state_terminal():
    """
    **Feature: p20m build + provision result ingest**
    **Property: Build completion drives the run-state machine row
    out of DISPATCHING to a terminal state.**
    """
    engine, db_session = build_in_memory_session()
    try:
        run_id = new_uuid()
        _seed_build_run(db_session=db_session, run_id=run_id)

        manifest = _build_manifest(
            run_id=run_id,
            format_tag="build",
            terminal_outcome="success",
        )
        completion.complete_build_run(
            db_session=db_session,
            run_id=run_id,
            manifest=manifest,
        )
        snapshot = get_run_state_snapshot(
            db_session=db_session, run_id=run_id,
        )
        testbase.assert_equal(snapshot.state.value, "completed")
    finally:
        db_session.close()
        engine.dispose()
    return


# ---------------------------------------------------------------------------
# complete_provision_run
# ---------------------------------------------------------------------------


def test_provision_manifest_advances_infra_run_to_completed():
    """
    **Feature: p20m build + provision result ingest**
    **Property: A format_tag=provision ResultManifest advances the
    InfraRun to COMPLETED and drives the run-state terminal.**
    """
    engine, db_session = build_in_memory_session()
    try:
        run_id = new_uuid()
        _seed_infra_run(db_session=db_session, run_id=run_id)

        manifest = _build_manifest(
            run_id=run_id,
            format_tag="provision",
            terminal_outcome="success",
            files=[
                {"relative_path": "tfstate", "size_bytes": 9, "sha256": "e" * 64},
            ],
        )
        outcome = completion.complete_provision_run(
            db_session=db_session,
            run_id=run_id,
            manifest=manifest,
        )
        testbase.assert_equal(outcome.domain_state, "completed")
        testbase.assert_equal(outcome.artifacts_recorded, 1)

        snapshot = get_run_state_snapshot(
            db_session=db_session, run_id=run_id,
        )
        testbase.assert_equal(snapshot.state.value, "completed")
    finally:
        db_session.close()
        engine.dispose()
    return


def test_provision_manifest_failure_outcome_lands_failed():
    """
    **Feature: p20m build + provision result ingest**
    **Property: A provision manifest reporting failure advances the
    InfraRun to FAILED.**
    """
    engine, db_session = build_in_memory_session()
    try:
        run_id = new_uuid()
        _seed_infra_run(db_session=db_session, run_id=run_id)

        manifest = _build_manifest(
            run_id=run_id,
            format_tag="provision",
            terminal_outcome="failure",
        )
        outcome = completion.complete_provision_run(
            db_session=db_session,
            run_id=run_id,
            manifest=manifest,
        )
        testbase.assert_equal(outcome.domain_state, "failed")
    finally:
        db_session.close()
        engine.dispose()
    return


def test_a_failed_build_or_provision_run_records_the_pods_explanation_as_its_reason():
    """
    **Feature: p20m build + provision result ingest**
    **Property: the reason recorded for a build or provisioning run is the manifest's notes (the pod's own account, which the page, the
    event and the notification show) when the pod gave some, and the service's outcome text when it gave none.**
    """
    engine, db_session = build_in_memory_session()
    try:
        build_noted, build_silent, infra_noted, infra_silent = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        for run_id in (build_noted, build_silent):
            _seed_build_run(db_session=db_session, run_id=run_id)
        for run_id in (infra_noted, infra_silent):
            _seed_infra_run(db_session=db_session, run_id=run_id)

        def _reason(model: Any, run_id: str) -> str:
            return str(db_session.query(model).filter(model.run_id == run_id).first().final_state_reason)

        for run_id, format_tag, notes, complete in (
            (build_noted, "build", "make exited with code 2: no rule to make target 'all'", completion.complete_build_run),
            (build_silent, "build", None, completion.complete_build_run),
            (infra_noted, "provision", "terraform exited with code 1: invalid credentials", completion.complete_provision_run),
            (infra_silent, "provision", "  ", completion.complete_provision_run),
        ):
            manifest = _build_manifest(run_id=run_id, format_tag=format_tag, terminal_outcome="failure")
            if notes is not None:
                manifest["notes"] = notes
            complete(db_session=db_session, run_id=run_id, manifest=manifest)

        reasons = (
            _reason(BuildRun, build_noted), _reason(BuildRun, build_silent),
            _reason(InfraRun, infra_noted), _reason(InfraRun, infra_silent).split(" ")[0:4],
        )
        testbase.assert_equal(
            reasons,
            (
                "make exited with code 2: no rule to make target 'all'", "build result manifest: outcome=failure",
                "terraform exited with code 1: invalid credentials", ["provision", "result", "manifest:", "outcome=failure"],
            ),
        )
    finally:
        db_session.close()
        engine.dispose()
    return


# ---------------------------------------------------------------------------
# results/complete routing
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(
        self,
        *,
        path: str,
        path_params: Dict[str, Any],
        body: Any,
        db_session: Any,
        mtls_client_cn: Optional[str] = None,
    ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = path_params
        self._body: Any = body
        self.db_session: Any = db_session
        if mtls_client_cn is not None:
            self.mtls_client_cn: str = mtls_client_cn
        return

    def json(self) -> Any:
        return self._body


def _decode_body(response: Any) -> Any:
    rtnval = json.loads(response.body.decode("utf-8"))
    return rtnval


def test_results_complete_routes_build_manifest_to_completion():
    """
    **Feature: p20m build + provision result ingest**
    **Property: POST /runs/{id}/results/complete with format_tag=
    build routes to the build-completion path and answers 202 with
    the completed domain state.**
    """
    engine, db_session = build_in_memory_session()
    try:
        run_id = new_uuid()
        _seed_build_run(db_session=db_session, run_id=run_id)

        manifest = _build_manifest(
            run_id=run_id,
            format_tag="build",
            terminal_outcome="success",
        )
        request = _FakeRequest(
            path="/api/v1/runs/{}/results/complete".format(run_id),
            path_params={"run_id": run_id},
            body=manifest,
            db_session=db_session,
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_results_complete(request)
        testbase.assert_equal(response.status_code, 202)
        body = _decode_body(response)
        testbase.assert_equal(body["job_kind"], "build")
        testbase.assert_equal(body["domain_state"], "completed")
    finally:
        db_session.close()
        engine.dispose()
    return


def test_results_complete_build_unknown_run_returns_404():
    """
    **Feature: p20m build + provision result ingest**
    **Property: A build manifest for a run with no BuildRow returns
    404.**
    """
    engine, db_session = build_in_memory_session()
    try:
        run_id = new_uuid()
        # Only a run-state row exists -- no BuildRun row.
        create_run_state(
            db_session=db_session,
            run_id=run_id,
            project_id=PROJECT_UUID,
            job_type="build-makefile",
        )
        manifest = _build_manifest(
            run_id=run_id,
            format_tag="build",
            terminal_outcome="success",
        )
        request = _FakeRequest(
            path="/api/v1/runs/{}/results/complete".format(run_id),
            path_params={"run_id": run_id},
            body=manifest,
            db_session=db_session,
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_results_complete(request)
        testbase.assert_equal(response.status_code, 404)
    finally:
        db_session.close()
        engine.dispose()
    return


def test_results_complete_testbase_manifest_still_invokes_scanner():
    """
    **Feature: p20m build + provision result ingest**
    **Property: Backward compat -- a format_tag=testbase manifest
    still routes to the testbase result scanner, not the build /
    provision completion path.**
    """
    captured: Dict[str, Any] = {}

    def fake_scan(**kwargs: Any) -> Any:
        captured.update(kwargs)

        class _Outcome:
            status = "scanned"

        return _Outcome()

    engine, db_session = build_in_memory_session()
    scan_patch = create_module_patch(runs_routes.result_scanner, "scan_once")
    scan_mock = scan_patch.activate()
    scan_mock.configure(side_effect=fake_scan)
    run_patch = create_module_patch(runs_routes.run_repo, "find_run")
    run_mock = run_patch.activate()
    run_mock.configure(side_effect=lambda **kwargs: object())
    try:
        run_id = new_uuid()
        manifest = _build_manifest(
            run_id=run_id,
            format_tag="testbase",
            terminal_outcome="success",
        )
        request = _FakeRequest(
            path="/api/v1/runs/{}/results/complete".format(run_id),
            path_params={"run_id": run_id},
            body=manifest,
            db_session=db_session,
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_post_results_complete(request)
        testbase.assert_equal(response.status_code, 202)
        body = _decode_body(response)
        testbase.assert_equal(body["status"], "scanned")
        testbase.assert_true("tree_path" in captured)
    finally:
        scan_patch.deactivate()
        run_patch.deactivate()
        db_session.close()
        engine.dispose()
    return
