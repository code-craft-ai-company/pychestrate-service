"""
.. module:: test_p19c_dispatch_ack_route_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for POST /api/v1/runs/{run_id}/dispatch-ack.

.. moduleauthor:: Code Craft AI LLC

Covers the dispatch-ack endpoint added in PR p19c:

* 401 when mTLS-verified client common-name is absent.
* 404 when run / dispatch-attempt is unknown.
* 202 on success.
* 202 on idempotent re-ack (the service returns the existing
  receipt and the handler treats that as success).
* 409 when DuplicateRunReceiptError is raised.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, List, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.jobs.dispatch.receipt.errors import (
    DuplicateRunReceiptError,
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


class _FakeAttempt:
    def __init__(self, *, run_id: str = "run-1", project_id: str = "proj-1") -> None:
        self.attempt_id: str = "attempt-1"
        self.run_id: str = run_id
        self.project_id: str = project_id
        return


_VALID_BODY = {
    "envelope_id": "env-1",
    "dispatch_attempt_id": "attempt-1",
    "client_id": "client-1",
    "local_run_id": "local-1",
    "accepted_at": "2026-05-17T12:00:00+00:00",
}


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


def _patch_get_attempt(*, attempt: Optional[Any]) -> Any:
    patch = create_module_patch(runs_routes.dispatch_repo, "get_attempt")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: attempt)
    return patch


def _patch_mark_attempt_acked(*, calls: List[Any]) -> Any:
    patch = create_module_patch(runs_routes.dispatch_repo, "mark_attempt_acked")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: calls.append(kwargs))
    return patch


def test_dispatch_ack_returns_401_when_mtls_cn_absent():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: POST /runs/{id}/dispatch-ack returns 401 when no
    mTLS handshake has been forwarded.**
    """
    request = _FakeRequest(
        path="/api/v1/runs/run-1/dispatch-ack",
        path_params={"run_id": "run-1"},
        body=_VALID_BODY,
        db_session=object(),
    )
    response = runs_routes.handle_dispatch_ack(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_dispatch_ack_returns_404_when_run_unknown():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: Unknown run id returns 404 problem+json.**
    """
    patch = _patch_find_run(exists=False)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-missing/dispatch-ack",
            path_params={"run_id": "run-missing"},
            body=_VALID_BODY,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_dispatch_ack(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    return


def test_dispatch_ack_returns_404_when_attempt_unknown():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: Unknown dispatch_attempt_id returns 404.**
    """
    run_patch = _patch_find_run(exists=True)
    attempt_patch = _patch_get_attempt(attempt=None)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/dispatch-ack",
            path_params={"run_id": "run-1"},
            body=_VALID_BODY,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_dispatch_ack(request)
    finally:
        attempt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 404)
    body = _decode_body(response)
    testbase.assert_equal(body["dispatch_attempt_id"], "attempt-1")
    return


def test_dispatch_ack_returns_202_on_success():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A valid ack is delegated to receipt_service.record
    and the handler returns 202 with status=acked.**
    """
    captured: Dict[str, Any] = {}

    def fake_record(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return object()

    run_patch = _patch_find_run(exists=True)
    attempt_patch = _patch_get_attempt(attempt=_FakeAttempt())
    acked_patch = _patch_mark_attempt_acked(calls=[])
    svc_patch = create_module_patch(runs_routes.receipt_service, "record")
    svc_mock = svc_patch.activate()
    svc_mock.configure(side_effect=fake_record)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/dispatch-ack",
            path_params={"run_id": "run-1"},
            body=_VALID_BODY,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_dispatch_ack(request)
    finally:
        svc_patch.deactivate()
        acked_patch.deactivate()
        attempt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    body = _decode_body(response)
    testbase.assert_equal(body["status"], "acked")
    testbase.assert_equal(captured["envelope_id"], "env-1")
    testbase.assert_equal(captured["client_local_run_id"], "local-1")
    return


def test_dispatch_ack_idempotent_replay_returns_202():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A replayed ack -- handled idempotently by
    receipt_service.record (no exception raised) -- returns 202
    again, never 409.**
    """
    # The receipt service's record() is idempotent for matching
    # (client_id, client_local_run_id); it returns the previously
    # persisted record and does NOT raise. The route should
    # treat that as 202, matching the OpenAPI spec note that
    # repeat acks are idempotent.
    run_patch = _patch_find_run(exists=True)
    attempt_patch = _patch_get_attempt(attempt=_FakeAttempt())
    acked_patch = _patch_mark_attempt_acked(calls=[])
    svc_patch = create_module_patch(runs_routes.receipt_service, "record")
    svc_mock = svc_patch.activate()
    svc_mock.configure(side_effect=lambda **kwargs: object())
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/dispatch-ack",
            path_params={"run_id": "run-1"},
            body=_VALID_BODY,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_dispatch_ack(request)
    finally:
        svc_patch.deactivate()
        acked_patch.deactivate()
        attempt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 202)
    return


def test_dispatch_ack_returns_409_on_duplicate_run_receipt():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: A second distinct receipt for the same run is
    surfaced as 409 with run_id in the problem extensions.**
    """
    def raise_dup(**kwargs: Any) -> Any:
        raise DuplicateRunReceiptError("duplicate")

    run_patch = _patch_find_run(exists=True)
    attempt_patch = _patch_get_attempt(attempt=_FakeAttempt())
    acked_patch = _patch_mark_attempt_acked(calls=[])
    svc_patch = create_module_patch(runs_routes.receipt_service, "record")
    svc_mock = svc_patch.activate()
    svc_mock.configure(side_effect=raise_dup)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/dispatch-ack",
            path_params={"run_id": "run-1"},
            body=_VALID_BODY,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_dispatch_ack(request)
    finally:
        svc_patch.deactivate()
        acked_patch.deactivate()
        attempt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 409)
    body = _decode_body(response)
    testbase.assert_equal(body["run_id"], "run-1")
    return


def test_dispatch_ack_returns_400_when_body_fields_missing():
    """
    **Feature: 5-run-state-machine PR p19c**
    **Property: Missing required fields yield 400 with
    ``missing_fields`` extension listing every absent key.**
    """
    run_patch = _patch_find_run(exists=True)
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/dispatch-ack",
            path_params={"run_id": "run-1"},
            body={"envelope_id": "env-1"},
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        response = runs_routes.handle_dispatch_ack(request)
    finally:
        run_patch.deactivate()
    testbase.assert_equal(response.status_code, 400)
    body = _decode_body(response)
    testbase.assert_true("dispatch_attempt_id" in body["missing_fields"])
    testbase.assert_true("client_id" in body["missing_fields"])
    return


def test_dispatch_ack_marks_the_attempt_acked():
    """
    **Feature: dispatch protocol (E2E-07)**
    **Property: A valid ack moves the dispatch attempt it names to
    ACKED, so the attempt row records that the pod received the job.**
    """
    acked_calls: List[Any] = []
    attempt = _FakeAttempt()
    run_patch = _patch_find_run(exists=True)
    attempt_patch = _patch_get_attempt(attempt=attempt)
    acked_patch = _patch_mark_attempt_acked(calls=acked_calls)
    svc_patch = create_module_patch(runs_routes.receipt_service, "record")
    svc_mock = svc_patch.activate()
    svc_mock.configure(side_effect=lambda **kwargs: object())
    try:
        request = _FakeRequest(
            path="/api/v1/runs/run-1/dispatch-ack",
            path_params={"run_id": "run-1"},
            body=_VALID_BODY,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        runs_routes.handle_dispatch_ack(request)
    finally:
        svc_patch.deactivate()
        acked_patch.deactivate()
        attempt_patch.deactivate()
        run_patch.deactivate()
    testbase.assert_equal(len(acked_calls), 1)
    testbase.assert_true(acked_calls[0]["attempt"] is attempt)
    return


def _ack_and_capture_transitions(*, notes: Optional[str]) -> List[Any]:
    """
        Post a valid ack (with ``notes`` when given) and return the
        run-state transitions the route asked for.
    """
    transitions: List[Any] = []
    run_patch = _patch_find_run(exists=True)
    attempt_patch = _patch_get_attempt(attempt=_FakeAttempt())
    acked_patch = _patch_mark_attempt_acked(calls=[])
    svc_patch = create_module_patch(runs_routes.receipt_service, "record")
    svc_patch.activate().configure(side_effect=lambda **kwargs: object())
    transition_patch = create_module_patch(runs_routes, "_run_state_transition")
    transition_patch.activate().configure(side_effect=lambda **kwargs: transitions.append(kwargs))
    try:
        body = dict(_VALID_BODY)
        if notes is not None:
            body["notes"] = notes
        request = _FakeRequest(
            path="/api/v1/runs/run-1/dispatch-ack",
            path_params={"run_id": "run-1"},
            body=body,
            db_session=object(),
            mtls_client_cn="pod-client-cert",
        )
        runs_routes.handle_dispatch_ack(request)
    finally:
        transition_patch.deactivate()
        svc_patch.deactivate()
        acked_patch.deactivate()
        attempt_patch.deactivate()
        run_patch.deactivate()
    return transitions


def test_rejected_dispatch_ends_the_run_with_the_pods_reason():
    """
    **Feature: pod refusals (E2E-15)**
    **Property: an ack whose notes start "REJECTED:" ends the run
    (FAILURE_OBSERVED) with the pod's notes as the reason, instead of
    leaving it dispatched with no explanation.**
    """
    notes = "REJECTED: envelope verification failed (unknown_key): no key 'k1'"

    transitions = _ack_and_capture_transitions(notes=notes)

    testbase.assert_equal(len(transitions), 1)
    testbase.assert_equal(transitions[0]["event"], runs_routes.RunEvent.FAILURE_OBSERVED)
    testbase.assert_equal(transitions[0]["reason"], notes)
    return


def test_accepted_dispatch_does_not_end_the_run():
    """
    **Feature: pod refusals (E2E-15)**
    **Property: an ordinary ack ("ACCEPTED: ...") does not end the run.**
    """
    transitions = _ack_and_capture_transitions(notes="ACCEPTED: starting job_kind=test")

    testbase.assert_equal(transitions, [])
    return
