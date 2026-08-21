"""
.. module:: test_p19i_client_cancel_delivery_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for client-facing cancel delivery + terminal
               outcome classification.

.. moduleauthor:: Code Craft AI LLC

Covers:

* :class:`HeartbeatCancelTransport` -- the production pull transport
  whose queue is the ``jobs_cancel_request`` table.
* ``GET /api/v1/clients/{client_id}/heartbeat`` carrying pending
  cancellations: 204 when nothing is queued (unchanged), 200 +
  ``ClientHeartbeatAck`` when something is, and the same mTLS auth
  contract as its sibling client endpoints in both cases.
* The drain's stop conditions -- an acknowledged request and a run
  that already reached a terminal state.
* :func:`advance_to_cancelled` -- a cancelled run reaching
  ``CANCELLED`` / ``TerminalOutcome.CANCELLED`` rather than
  ``FAILED`` / ``FAILURE``.
* :mod:`ingest.result.classification` -- the structured
  ``extras.failure_classification`` member.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.clients.restapi.v1 import (
    client_dispatch_routes,
)
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes
from ccai.pychestrate.webservice.ingest.result import (
    classification as result_classification,
)
from ccai.pychestrate.webservice.ingest.result.classification import (
    RunFailureClassification,
)
from ccai.pychestrate.webservice.jobs.cancel import repository as cancel_repo
from ccai.pychestrate.webservice.jobs.cancel.dispatcher import (
    CancelDispatcher,
)
from ccai.pychestrate.webservice.jobs.cancel.heartbeattransport import (
    HEARTBEAT_CANCEL_TRANSPORT_NAME,
    HeartbeatCancelTransport,
    acknowledge_client_cancellation,
    cancellation_to_dict,
    drain_pending_cancellations,
)
from ccai.pychestrate.webservice.jobs.cancel.models import CancelStatus
from ccai.pychestrate.webservice.jobs.run.state import (
    create_run as create_run_state,
)
from ccai.pychestrate.webservice.jobs.run.state import transition
from ccai.pychestrate.webservice.jobs.run.state.advance import (
    advance_to_cancelled,
    advance_to_terminal,
)
from ccai.pychestrate.webservice.jobs.run.state.enums import (
    RunEvent,
    RunState,
    TerminalOutcome,
)
from ccai.pychestrate.webservice.jobs.run.state.machine import get_snapshot
from ccai.pychestrate.webservice.messaging.event_bus import (
    reset_for_testing as reset_event_bus,
)
from ccai.testbase.mocking import create_module_patch

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


_CLIENT_ID = "77777777-7777-4000-8000-000000000901"
_OTHER_CLIENT_ID = "88888888-8888-4000-8000-000000000901"
_PROJECT_ID = "00000000-0000-4000-8000-000000000901"
_RUN_ID = "11111111-1111-4000-8000-000000000901"
_OTHER_RUN_ID = "22222222-2222-4000-8000-000000000901"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


class _FakeRequest:
    """
        Minimal duck-typed stand-in for the webworks ``Request``.
        Mirrors the helper in
        ``test_p19g_long_poll_transport_m1`` so both client-endpoint
        suites exercise the same request shape.
    """

    def __init__(
            self,
            *,
            path: str,
            path_params: Optional[Dict[str, Any]] = None,
            query_params: Optional[Dict[str, Any]] = None,
            mtls_client_cn: Optional[str] = None,
            db_session: Optional[Any] = None
        ) -> None:
        self.path: str = path
        self.path_params: Dict[str, Any] = (
            path_params if path_params is not None else {}
        )
        self.query_params: Dict[str, Any] = (
            query_params if query_params is not None else {}
        )
        if mtls_client_cn is not None:
            self.mtls_client_cn: str = mtls_client_cn
        self.db_session: Optional[Any] = db_session
        return


def _decode_body(response: Any) -> Any:
    """
        Decode a webworks JSON response body.

        :param response: ``Response`` instance.

        :returns: Parsed JSON.
    """
    body_text = response.body.decode("utf-8")
    rtnval = json.loads(body_text)
    return rtnval


def _heartbeat_request(
        *,
        client_id: str = _CLIENT_ID,
        cert_cn: Optional[str] = _CLIENT_ID,
        db_session: Optional[Any] = None
    ) -> _FakeRequest:
    """
        Build a heartbeat request for ``client_id``.

        :param client_id: Path-param client UUID.
        :param cert_cn: mTLS common-name nginx forwarded, or None.
        :param db_session: Optional bound session.

        :returns: A :class:`_FakeRequest`.
    """
    rtnval = _FakeRequest(
        path="/api/v1/clients/{}/heartbeat".format(client_id),
        path_params={"client_id": client_id},
        mtls_client_cn=cert_cn,
        db_session=db_session,
    )
    return rtnval


def _open_cancel_request(
        *,
        db_session: Any,
        run_id: str = _RUN_ID,
        client_id: str = _CLIENT_ID,
        reason: str = "operator cancelled"
    ) -> Any:
    """
        Insert an open (TRANSMITTED) cancel request row.

        Goes through the real :class:`CancelDispatcher` with the
        production :class:`HeartbeatCancelTransport` so the row lands
        in exactly the state the endpoint sees in production.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID being cancelled.
        :param client_id: Target client UUID.
        :param reason: Operator-supplied reason.

        :returns: The persisted :class:`CancelRequest`.
    """
    dispatcher = CancelDispatcher(transport=HeartbeatCancelTransport())
    rtnval = dispatcher.send_cancel_rpc(
        db_session=db_session,
        run_id=run_id,
        project_id=_PROJECT_ID,
        client_id=client_id,
        requested_by=None,
        reason=reason,
    )
    return rtnval


def _seed_running_run(*, db_session: Any, run_id: str = _RUN_ID) -> None:
    """
        Create a run-state row and walk it to ``RUNNING``.

        The advance helpers walk forward from wherever the row sits,
        but the transition table has no cancel or completion edge out
        of ``PENDING`` -- a run reaches those only once it has been
        dispatched. Seeding a realistic in-flight run is therefore
        part of the setup, not something the helper under test should
        paper over.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID to seed.

        :returns: None.
    """
    create_run_state(
        db_session=db_session, run_id=run_id, project_id=_PROJECT_ID,
        job_type="testbase-singlehost")
    transition(
        db_session=db_session, run_id=run_id,
        event=RunEvent.DISPATCH_STARTED, actor="system:test",
        reason="seeded for test")
    transition(
        db_session=db_session, run_id=run_id,
        event=RunEvent.RECEIPT_RECORDED, actor="system:test",
        reason="seeded for test")
    transition(
        db_session=db_session, run_id=run_id,
        event=RunEvent.FIRST_PROGRESS, actor="system:test",
        reason="seeded for test")
    return


def _prepare_runtime() -> None:
    """
        Reset the in-process event bus so queued outbox events from a
        prior test do not leak into this one.

        :returns: None.
    """
    reset_event_bus()
    return


# ---------------------------------------------------------------------------
# HeartbeatCancelTransport
# ---------------------------------------------------------------------------


def test_heartbeat_transport_reports_its_name():
    """
    **Feature: client cancel delivery**
    **Property: the production cancel transport names itself
    distinctly from the in-memory test transport, so operator logs
    say which mechanism carried a cancel.**
    """
    transport = HeartbeatCancelTransport()
    testbase.assert_equal(
        transport.transport_name(), HEARTBEAT_CANCEL_TRANSPORT_NAME)
    return


def test_heartbeat_transport_send_cancel_does_not_raise():
    """
    **Feature: client cancel delivery**
    **Property: queueing a cancel for pull delivery cannot fail --
    the persisted row IS the queue, so there is no wire to be down.**
    """
    transport = HeartbeatCancelTransport()
    transport.send_cancel(
        run_id=_RUN_ID, client_id=_CLIENT_ID, request_id="req-1",
        reason="stop",
    )
    return


def test_cancel_dispatcher_marks_the_request_transmitted():
    """
    **Feature: client cancel delivery**
    **Property: a cancel queued through the heartbeat transport
    reaches TRANSMITTED -- meaning "queued for the pod to pull", the
    state the drain looks for.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    row = _open_cancel_request(db_session=session)

    testbase.assert_equal(row.status, CancelStatus.TRANSMITTED)
    return


# ---------------------------------------------------------------------------
# drain_pending_cancellations
# ---------------------------------------------------------------------------


def test_drain_returns_an_open_cancel_for_the_target_client():
    """
    **Feature: client cancel delivery**
    **Property: an open cancel request is drained for the client it
    targets.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    entries = drain_pending_cancellations(
        db_session=session, client_id=_CLIENT_ID)

    testbase.assert_equal(len(entries), 1)
    testbase.assert_equal(entries[0]["run_id"], _RUN_ID)
    return


def test_drain_does_not_leak_a_cancel_to_another_client():
    """
    **Feature: client cancel delivery**
    **Property: a cancel addressed to one pod is never handed to a
    different pod, which would stop the wrong job.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    entries = drain_pending_cancellations(
        db_session=session, client_id=_OTHER_CLIENT_ID)

    testbase.assert_equal(len(entries), 0)
    return


def test_drain_returns_nothing_when_no_cancel_is_queued():
    """
    **Feature: client cancel delivery**
    **Property: the common case -- a healthy pod with no cancel
    pending -- drains to an empty list.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    entries = drain_pending_cancellations(
        db_session=session, client_id=_CLIENT_ID)

    testbase.assert_equal(len(entries), 0)
    return


def test_drain_redelivers_an_unacknowledged_cancel():
    """
    **Feature: client cancel delivery**
    **Property: delivery is at-least-once -- a cancel the pod has not
    acknowledged is offered again on the next heartbeat, because the
    response carrying it may never have arrived.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    first = drain_pending_cancellations(
        db_session=session, client_id=_CLIENT_ID)
    second = drain_pending_cancellations(
        db_session=session, client_id=_CLIENT_ID)

    testbase.assert_equal(len(first), 1)
    testbase.assert_equal(len(second), 1)
    return


def test_drain_stops_after_the_pod_acknowledges():
    """
    **Feature: client cancel delivery**
    **Property: acknowledging closes the row, so the re-delivery loop
    terminates once the pod has confirmed it stopped the job.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    acknowledge_client_cancellation(
        db_session=session, run_id=_RUN_ID, client_id=_CLIENT_ID)

    entries = drain_pending_cancellations(
        db_session=session, client_id=_CLIENT_ID)

    testbase.assert_equal(len(entries), 0)
    return


def test_drain_skips_a_cancel_whose_run_already_finished():
    """
    **Feature: client cancel delivery**
    **Property: a cancel that raced a run which was finishing anyway
    stops being delivered. The pod never had a job to stop, so it
    will never post a cancelled result to close the row -- without
    this filter the cancel would be re-sent forever.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    _seed_running_run(db_session=session)
    advance_to_terminal(
        db_session=session, run_id=_RUN_ID, succeeded=True,
        actor="system:test", reason="finished before the cancel landed")

    _open_cancel_request(db_session=session)

    entries = drain_pending_cancellations(
        db_session=session, client_id=_CLIENT_ID)

    testbase.assert_equal(len(entries), 0)
    return


def test_drain_delivers_a_cancel_for_a_run_with_no_state_row():
    """
    **Feature: client cancel delivery**
    **Property: a missing run-state row is not treated as terminal.
    Refusing to deliver on a missing row would silently drop cancels
    for any run whose state bookkeeping lags behind its dispatch.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    entries = drain_pending_cancellations(
        db_session=session, client_id=_CLIENT_ID)

    testbase.assert_equal(len(entries), 1)
    return


def test_cancellation_to_dict_carries_the_operator_reason():
    """
    **Feature: client cancel delivery**
    **Property: the reason an operator typed reaches the pod, so the
    pod can put it on the ack note and the result manifest.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    row = _open_cancel_request(
        db_session=session, reason="pod needed for a hotfix")

    rendered = cancellation_to_dict(row=row)

    testbase.assert_equal(rendered["reason"], "pod needed for a hotfix")
    testbase.assert_equal(rendered["run_id"], _RUN_ID)
    testbase.assert_equal(
        rendered["transport_name"], HEARTBEAT_CANCEL_TRANSPORT_NAME)
    return


# ---------------------------------------------------------------------------
# acknowledge_client_cancellation
# ---------------------------------------------------------------------------


def test_acknowledge_marks_the_request_acked():
    """
    **Feature: client cancel delivery**
    **Property: the pod confirming it stopped the run flips the row to
    ACKED -- the only status that means the pod actually saw the
    cancel.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    row = _open_cancel_request(db_session=session)

    acknowledge_client_cancellation(
        db_session=session, run_id=_RUN_ID, client_id=_CLIENT_ID)

    refreshed = cancel_repo.get_request(
        db_session=session, request_id=str(row.request_id))

    testbase.assert_equal(refreshed.status, CancelStatus.ACKED)
    return


def test_acknowledge_of_an_unknown_run_is_a_no_op():
    """
    **Feature: client cancel delivery**
    **Property: acking a run with no open cancel returns None rather
    than raising. At-least-once delivery guarantees duplicate acks,
    and a pod that did the right thing must not be answered with an
    error.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    result = acknowledge_client_cancellation(
        db_session=session, run_id=_OTHER_RUN_ID, client_id=_CLIENT_ID)

    testbase.assert_true(result is None)
    return


def test_acknowledge_twice_is_a_no_op_the_second_time():
    """
    **Feature: client cancel delivery**
    **Property: a repeated ack for an already-closed request is
    harmless.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    first = acknowledge_client_cancellation(
        db_session=session, run_id=_RUN_ID, client_id=_CLIENT_ID)
    second = acknowledge_client_cancellation(
        db_session=session, run_id=_RUN_ID, client_id=_CLIENT_ID)

    testbase.assert_true(first is not None)
    testbase.assert_true(second is None)
    return


def test_acknowledge_by_the_wrong_client_is_a_no_op():
    """
    **Feature: client cancel delivery**
    **Property: a pod can only close a cancel request that was
    addressed to it -- otherwise one pod could silence another pod's
    cancel.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    row = _open_cancel_request(db_session=session)

    result = acknowledge_client_cancellation(
        db_session=session, run_id=_RUN_ID, client_id=_OTHER_CLIENT_ID)

    refreshed = cancel_repo.get_request(
        db_session=session, request_id=str(row.request_id))

    testbase.assert_true(result is None)
    testbase.assert_equal(refreshed.status, CancelStatus.TRANSMITTED)
    return


# ---------------------------------------------------------------------------
# GET /api/v1/clients/{client_id}/heartbeat
# ---------------------------------------------------------------------------


def test_heartbeat_returns_204_when_nothing_is_queued():
    """
    **Feature: client cancel delivery**
    **Property: the pre-existing 204 contract is preserved for a pod
    with no cancel pending, so a client built before cancel support
    is unaffected.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    response = client_dispatch_routes.handle_client_heartbeat(
        _heartbeat_request(db_session=session))

    testbase.assert_equal(response.status_code, 204)
    return


def test_heartbeat_returns_200_when_a_cancel_is_queued():
    """
    **Feature: client cancel delivery**
    **Property: a queued cancellation turns the heartbeat into a 200
    carrying it, which is the whole delivery channel.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    response = client_dispatch_routes.handle_client_heartbeat(
        _heartbeat_request(db_session=session))

    testbase.assert_equal(response.status_code, 200)
    return


def test_heartbeat_body_lists_the_pending_cancellation():
    """
    **Feature: client cancel delivery**
    **Property: the ClientHeartbeatAck body names the run the pod must
    stop.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    response = client_dispatch_routes.handle_client_heartbeat(
        _heartbeat_request(db_session=session))
    body = _decode_body(response)

    testbase.assert_equal(body["client_id"], _CLIENT_ID)
    testbase.assert_equal(len(body["cancellations"]), 1)
    testbase.assert_equal(body["cancellations"][0]["run_id"], _RUN_ID)
    return


def test_heartbeat_returns_401_without_mtls_even_with_a_cancel_queued():
    """
    **Feature: client cancel delivery**
    **Property: the cancel payload is behind the same mTLS gate as the
    rest of the client surface -- an unauthenticated caller learns
    nothing about queued cancellations.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    response = client_dispatch_routes.handle_client_heartbeat(
        _heartbeat_request(cert_cn=None, db_session=session))

    testbase.assert_equal(response.status_code, 401)
    return


def test_heartbeat_returns_403_on_cert_mismatch_even_with_a_cancel_queued():
    """
    **Feature: client cancel delivery**
    **Property: a cert CN that does not match the path client_id is
    refused before the drain runs, so one pod cannot read another
    pod's cancellations.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    response = client_dispatch_routes.handle_client_heartbeat(
        _heartbeat_request(cert_cn=_OTHER_CLIENT_ID, db_session=session))

    testbase.assert_equal(response.status_code, 403)
    return


def test_heartbeat_returns_204_when_the_cancel_drain_raises():
    """
    **Feature: client cancel delivery**
    **Property: a drain failure degrades to "nothing queued" rather
    than failing the heartbeat. A heartbeat error would make the
    registry believe a healthy pod died, which is a far worse outcome
    than a cancel that waits for the next tick.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _open_cancel_request(db_session=session)

    def _exploding_drain(**kwargs: Any):
        raise RuntimeError("database is on fire")

    patch = create_module_patch(
        client_dispatch_routes.cancel_heartbeat_transport,
        "drain_pending_cancellations",
    )
    mock = patch.activate()
    mock.configure(side_effect=_exploding_drain)
    try:
        response = client_dispatch_routes.handle_client_heartbeat(
            _heartbeat_request(db_session=session))
    finally:
        patch.deactivate()

    testbase.assert_equal(response.status_code, 204)
    return


# ---------------------------------------------------------------------------
# advance_to_cancelled
# ---------------------------------------------------------------------------


def test_advance_to_cancelled_reaches_the_cancelled_state():
    """
    **Feature: terminal outcomes**
    **Property: a cancelled run lands in CANCELLED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _seed_running_run(db_session=session)

    advance_to_cancelled(
        db_session=session, run_id=_RUN_ID, actor="system:test",
        reason="operator cancelled")

    snapshot = get_snapshot(db_session=session, run_id=_RUN_ID)
    testbase.assert_equal(snapshot.state, RunState.CANCELLED)
    return


def test_advance_to_cancelled_stamps_the_cancelled_terminal_outcome():
    """
    **Feature: terminal outcomes**
    **Property: the run carries TerminalOutcome.CANCELLED, NOT
    FAILURE. Folding a deliberate stop into the failure bucket makes
    a cancel indistinguishable from a broken job in every downstream
    metric and alert.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _seed_running_run(db_session=session)

    advance_to_cancelled(
        db_session=session, run_id=_RUN_ID, actor="system:test",
        reason="operator cancelled")

    snapshot = get_snapshot(db_session=session, run_id=_RUN_ID)
    testbase.assert_equal(
        snapshot.terminal_outcome, TerminalOutcome.CANCELLED.value)
    return


def test_advance_to_cancelled_on_a_missing_run_returns_none():
    """
    **Feature: terminal outcomes**
    **Property: cancelling a run with no state row is tolerated, in
    keeping with the other advance helpers.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    result = advance_to_cancelled(
        db_session=session, run_id=_OTHER_RUN_ID, actor="system:test",
        reason="no such run")

    testbase.assert_true(result is None)
    return


def test_advance_to_cancelled_is_idempotent_on_an_already_cancelled_run():
    """
    **Feature: terminal outcomes**
    **Property: a replayed cancelled result does not raise and leaves
    the run in CANCELLED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _seed_running_run(db_session=session)

    advance_to_cancelled(
        db_session=session, run_id=_RUN_ID, actor="system:test",
        reason="operator cancelled")
    second = advance_to_cancelled(
        db_session=session, run_id=_RUN_ID, actor="system:test",
        reason="operator cancelled again")

    testbase.assert_equal(second, RunState.CANCELLED.value)
    return


def test_advance_to_terminal_still_reaches_failed_for_a_failure():
    """
    **Feature: terminal outcomes**
    **Property: the pre-existing failure path is unchanged by the
    addition of the cancelled path.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _seed_running_run(db_session=session)

    advance_to_terminal(
        db_session=session, run_id=_RUN_ID, succeeded=False,
        actor="system:test", reason="tests failed")

    snapshot = get_snapshot(db_session=session, run_id=_RUN_ID)
    testbase.assert_equal(snapshot.state, RunState.FAILED)
    testbase.assert_equal(
        snapshot.terminal_outcome, TerminalOutcome.FAILURE.value)
    return


# ---------------------------------------------------------------------------
# RunFailureClassification
# ---------------------------------------------------------------------------


def test_classification_reads_a_known_value_from_the_manifest_extras():
    """
    **Feature: terminal outcomes**
    **Property: the structured reason a run ended is read off
    extras.failure_classification, so a timeout is queryable rather
    than buried in prose.**
    """
    manifest = {
        "terminal_outcome": "failure",
        "extras": {"failure_classification": "timeout"},
    }
    resolved = result_classification.failure_classification_from_manifest(
        manifest=manifest)
    testbase.assert_equal(
        resolved, RunFailureClassification.TIMEOUT.value)
    return


def test_classification_distinguishes_a_missing_binary_from_a_test_failure():
    """
    **Feature: terminal outcomes**
    **Property: a pod missing its binary and a job that ran and failed
    both report TerminalOutcome.FAILURE but carry different
    classifications -- which is the entire point of the field.**
    """
    missing = result_classification.failure_classification_from_manifest(
        manifest={"extras": {
            "failure_classification": "executable_not_found"}})
    failed = result_classification.failure_classification_from_manifest(
        manifest={"extras": {"failure_classification": "nonzero_exit"}})

    testbase.assert_equal(
        missing, RunFailureClassification.EXECUTABLE_NOT_FOUND.value)
    testbase.assert_equal(
        failed, RunFailureClassification.NONZERO_EXIT.value)
    return


def test_classification_drops_a_value_outside_the_enum():
    """
    **Feature: terminal outcomes**
    **Property: an unrecognized classification is dropped rather than
    stored. The field exists so a fixed vocabulary can be aggregated;
    letting arbitrary strings through would turn it back into the
    free-form prose it replaces.**
    """
    resolved = result_classification.failure_classification_from_manifest(
        manifest={"extras": {"failure_classification": "vibes"}})
    testbase.assert_true(resolved is None)
    return


def test_classification_is_none_when_the_manifest_carries_no_extras():
    """
    **Feature: terminal outcomes**
    **Property: a manifest without the member resolves to None rather
    than raising -- the field is optional.**
    """
    resolved = result_classification.failure_classification_from_manifest(
        manifest={"terminal_outcome": "success"})
    testbase.assert_true(resolved is None)
    return


def test_classification_normalizes_case_and_surrounding_space():
    """
    **Feature: terminal outcomes**
    **Property: a value that differs only in case or padding is
    accepted rather than silently discarded.**
    """
    resolved = result_classification.normalize_failure_classification(
        candidate="  TIMEOUT  ")
    testbase.assert_equal(resolved, RunFailureClassification.TIMEOUT.value)
    return


def test_classification_rejects_a_non_string_value():
    """
    **Feature: terminal outcomes**
    **Property: a client sending the wrong type gets the value
    dropped, not an exception raised inside result ingest.**
    """
    resolved = result_classification.normalize_failure_classification(
        candidate=17)
    testbase.assert_true(resolved is None)
    return


def test_classification_enum_covers_the_cancelled_case():
    """
    **Feature: terminal outcomes**
    **Property: a cancelled run has a classification of its own, so
    the reason is present even when the outcome already says
    cancelled.**
    """
    resolved = result_classification.normalize_failure_classification(
        candidate="cancelled")
    testbase.assert_equal(resolved, RunFailureClassification.CANCELLED.value)
    return


# ---------------------------------------------------------------------------
# The extras whitelist
# ---------------------------------------------------------------------------


def _manifest_payload(*, extras: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
        Build a minimal posted ``ResultManifest`` body.

        :param extras: Optional ``extras`` map.

        :returns: A manifest dict.
    """
    rtnval: Dict[str, Any] = {
        "run_id": _RUN_ID,
        "client_id": _CLIENT_ID,
        "format_tag": "testbase",
        "backend_key_prefix": "runs/{}".format(_RUN_ID),
        "completed_at": "2026-08-21T12:00:00+00:00",
        "terminal_outcome": "failure",
    }
    if extras is not None:
        rtnval["extras"] = extras
    return rtnval


def test_manifest_block_lifts_the_failure_classification_out_of_extras():
    """
    **Feature: terminal outcomes**
    **Property: the classification survives into the durable manifest
    block. That block is a WHITELIST -- it copies named members and
    discards `extras` wholesale -- so a classification that is not
    lifted here is silently dropped before anything durable is
    written, and the field would look implemented while recording
    nothing.**
    """
    block = runs_routes._build_result_manifest_block(
        run_id=_RUN_ID,
        format_tag="testbase",
        payload=_manifest_payload(
            extras={"failure_classification": "timeout"}),
    )
    testbase.assert_equal(block["failure_classification"], "timeout")
    return


def test_manifest_block_reports_no_classification_when_extras_is_absent():
    """
    **Feature: terminal outcomes**
    **Property: a manifest carrying no classification yields None
    rather than a missing key, so consumers can read the member
    unconditionally.**
    """
    block = runs_routes._build_result_manifest_block(
        run_id=_RUN_ID, format_tag="testbase", payload=_manifest_payload())
    testbase.assert_true(block["failure_classification"] is None)
    return


def test_manifest_block_drops_a_classification_outside_the_enum():
    """
    **Feature: terminal outcomes**
    **Property: validation happens on the way into the durable
    record, not just at the edge, so an unrecognized value never
    reaches storage.**
    """
    block = runs_routes._build_result_manifest_block(
        run_id=_RUN_ID,
        format_tag="testbase",
        payload=_manifest_payload(
            extras={"failure_classification": "vibes"}),
    )
    testbase.assert_true(block["failure_classification"] is None)
    return


def test_manifest_block_carries_a_cancelled_classification():
    """
    **Feature: run cancellation**
    **Property: the cancelled classification the pod reports for a
    terminated job reaches the durable manifest block.**
    """
    block = runs_routes._build_result_manifest_block(
        run_id=_RUN_ID,
        format_tag="testbase",
        payload=_manifest_payload(
            extras={"failure_classification": "cancelled"}),
    )
    testbase.assert_equal(
        block["failure_classification"],
        RunFailureClassification.CANCELLED.value)
    return
