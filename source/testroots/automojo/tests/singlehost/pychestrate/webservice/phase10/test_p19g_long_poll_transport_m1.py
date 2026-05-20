"""
.. module:: test_p19g_long_poll_transport_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the PR p19g LongPollTransport + client-pull
               REST routes.

.. moduleauthor:: Automation Mojo LLC

Covers:

* :class:`LongPollTransport` enqueue / dequeue / timeout shapes.
* ``GET /api/v1/clients/{client_id}/dispatches:next`` route shape:
  401 when no mTLS, 403 on cert/client mismatch, 422 on bad
  ``timeout_seconds``, 503 when transport unconfigured, 204 on
  timeout, 200 + envelope body when a dispatch is queued.
* ``GET /api/v1/clients/{client_id}/heartbeat`` route shape: 204
  on success, 401 / 403 problem responses on auth failure.
* Integration: dispatcher -> long-poll queue -> route dequeues.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import threading
import time

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from automojo import testbase
from automojo.testbase.mocking import create_module_patch

from automojo.pychestrate.webservice.agents.factories.long_poll_transport import (
    DEFAULT_LONG_POLL_TIMEOUT_SECONDS,
    LONG_POLL_TRANSPORT_NAME,
    LongPollTransport,
    MAX_LONG_POLL_TIMEOUT_SECONDS,
)
from automojo.pychestrate.webservice.clients.restapi.v1 import (
    client_dispatch_routes,
)
from automojo.pychestrate.webservice.jobs.dispatch.errors import (
    DispatchTransportError,
)
from automojo.pychestrate.webservice.jobs.envelope import (
    DispatchRequest,
    JobDeadline,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    SignedJobEnvelope,
    build as build_envelope,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


_TEST_CLIENT_ID = "11111111-1111-1111-1111-111111111111"
_OTHER_CLIENT_ID = "22222222-2222-2222-2222-222222222222"
_TEST_POD_ID = "33333333-3333-3333-3333-333333333333"
_TEST_RUN_ID = "44444444-4444-4444-4444-444444444444"
_TEST_PROJECT_ID = "55555555-5555-5555-5555-555555555555"
_TEST_JOB_ID = "66666666-6666-6666-6666-666666666666"


def _build_signed_envelope() -> SignedJobEnvelope:
    """
        Construct an unsigned envelope and wrap it in a
        :class:`SignedJobEnvelope` with stub signature bytes. The
        transport never inspects the signature; the routes hex-encode
        whatever bytes the dispatcher hands them.

        :returns: A test-only :class:`SignedJobEnvelope`.
    """
    now = datetime.now(timezone.utc)
    soft = now + timedelta(minutes=30)
    hard = now + timedelta(minutes=60)
    request = DispatchRequest(
        project_id=_TEST_PROJECT_ID,
        job_id=_TEST_JOB_ID,
        job_name="probe-job",
        job_type="testbase-singlehost",
        run_id=_TEST_RUN_ID,
        client_id=_TEST_CLIENT_ID,
        pod_id=_TEST_POD_ID,
        issuer="pychestrate.example.com/0.3.1",
        pipeline=JobPipelineRef(pipeline_id="pl-1", instance_id="inst-1"),
        refs=JobRefs(
            branch="main",
            build="b-1",
            flavor="debug",
            release="v0.1",
            commit_sha="a" * 40,
        ),
        params={"timeout_seconds": 60},
        scoped_secrets=tuple(),
        results=JobResultsLocator(
            backend_key_prefix="runs/{}".format(_TEST_RUN_ID),
            backend_driver="s3",
        ),
        forwarding=JobForwardingInfo(
            progress_url="https://example.com/progress",
            summary_url="https://example.com/summary",
            auth_method="bearer",
        ),
        deadline=JobDeadline(soft_deadline_at=soft, hard_deadline_at=hard),
        extension_claims={},
    )
    envelope = build_envelope(request=request)
    signed = SignedJobEnvelope(
        envelope=envelope,
        canonical_payload=b"canonical-bytes",
        signature=b"\x01\x02\x03\x04",
        key_id="test-ed25519",
        signed_at=now,
    )
    return signed


class _FakeRequest:
    """
        Minimal duck-typed stand-in for the webworks ``Request``.
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


# ---------------------------------------------------------------------------
# LongPollTransport unit tests
# ---------------------------------------------------------------------------


def test_long_poll_transport_transmit_then_await_returns_record():
    """
    **Feature: 5-job-dispatch + 3-client-agent-protocol PR p19g**
    **Property: transmit() enqueues; await_pending_dispatch() returns
    the same SignedJobEnvelope on the next call.**
    """
    transport = LongPollTransport(ack_deadline_seconds=10)
    signed = _build_signed_envelope()

    transport.transmit(
        client_id=_TEST_CLIENT_ID, pod_id=_TEST_POD_ID, signed=signed,
    )
    testbase.assert_equal(
        transport.pending_count(client_id=_TEST_CLIENT_ID), 1,
    )

    record = transport.await_pending_dispatch(
        client_id=_TEST_CLIENT_ID, timeout_seconds=1,
    )
    testbase.assert_true(record is not None)
    testbase.assert_equal(record.client_id, _TEST_CLIENT_ID)
    testbase.assert_equal(record.pod_id, _TEST_POD_ID)
    testbase.assert_equal(record.envelope_id, signed.envelope.envelope_id)
    testbase.assert_equal(record.run_id, _TEST_RUN_ID)
    testbase.assert_equal(
        transport.pending_count(client_id=_TEST_CLIENT_ID), 0,
    )
    return


def test_long_poll_transport_await_returns_none_on_timeout():
    """
    **Feature: PR p19g**
    **Property: await_pending_dispatch() returns None when no record
    is queued before the timeout elapses.**
    """
    transport = LongPollTransport()
    record = transport.await_pending_dispatch(
        client_id=_TEST_CLIENT_ID, timeout_seconds=0,
    )
    testbase.assert_true(record is None)
    return


def test_long_poll_transport_rejects_empty_client_id():
    """
    **Feature: PR p19g**
    **Property: transmit() raises DispatchTransportError when
    client_id is empty.**
    """
    transport = LongPollTransport()
    signed = _build_signed_envelope()
    raised = False
    try:
        transport.transmit(client_id="", pod_id=_TEST_POD_ID, signed=signed)
    except DispatchTransportError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_long_poll_transport_clamps_timeout_to_max():
    """
    **Feature: PR p19g**
    **Property: await_pending_dispatch() clamps an over-large
    timeout to MAX_LONG_POLL_TIMEOUT_SECONDS rather than honoring
    the caller's value.**
    """
    transport = LongPollTransport()
    signed = _build_signed_envelope()

    transport.transmit(
        client_id=_TEST_CLIENT_ID, pod_id=_TEST_POD_ID, signed=signed,
    )
    # Pass a huge timeout — the record is already queued so the
    # call returns immediately regardless. We just want to prove
    # the clamp does not crash.
    record = transport.await_pending_dispatch(
        client_id=_TEST_CLIENT_ID,
        timeout_seconds=MAX_LONG_POLL_TIMEOUT_SECONDS * 1000,
    )
    testbase.assert_true(record is not None)
    return


def test_long_poll_transport_transport_name_is_stable():
    """
    **Feature: PR p19g**
    **Property: transport_name() returns the stable
    'http-long-poll' identifier persisted on attempt rows.**
    """
    transport = LongPollTransport()
    testbase.assert_equal(transport.transport_name(), LONG_POLL_TRANSPORT_NAME)
    return


def test_long_poll_transport_concurrent_transmit_and_await():
    """
    **Feature: PR p19g**
    **Property: a thread blocked in await_pending_dispatch() wakes
    when transmit() runs on another thread.**
    """
    transport = LongPollTransport()
    signed = _build_signed_envelope()
    captured: Dict[str, Any] = {}

    def waiter() -> None:
        record = transport.await_pending_dispatch(
            client_id=_TEST_CLIENT_ID, timeout_seconds=5,
        )
        captured["record"] = record
        return

    waiter_thread = threading.Thread(target=waiter, daemon=True)
    waiter_thread.start()
    time.sleep(0.05)
    transport.transmit(
        client_id=_TEST_CLIENT_ID, pod_id=_TEST_POD_ID, signed=signed,
    )
    waiter_thread.join(timeout=3.0)

    testbase.assert_equal(waiter_thread.is_alive(), False)
    testbase.assert_true(captured.get("record") is not None)
    testbase.assert_equal(
        captured["record"].envelope_id, signed.envelope.envelope_id,
    )
    return


# ---------------------------------------------------------------------------
# Route helpers / fixtures
# ---------------------------------------------------------------------------


def _install_transport(*, transport: Optional[LongPollTransport]) -> None:
    """
        Override the module-level transport seam on
        :mod:`client_dispatch_routes`.

        :param transport: Transport instance (or ``None``).

        :returns: None.
    """
    client_dispatch_routes.set_active_long_poll_transport(transport=transport)
    return


# ---------------------------------------------------------------------------
# /dispatches:next route tests
# ---------------------------------------------------------------------------


def test_next_dispatch_returns_401_when_mtls_cn_absent():
    """
    **Feature: PR p19g**
    **Property: GET /clients/{client_id}/dispatches:next returns
    401 when no mTLS handshake forwarded a client common-name.**
    """
    _install_transport(transport=LongPollTransport())
    try:
        request = _FakeRequest(
            path="/api/v1/clients/{}/dispatches:next".format(_TEST_CLIENT_ID),
            path_params={"client_id": _TEST_CLIENT_ID},
        )
        response = client_dispatch_routes.handle_next_dispatch(request)
    finally:
        _install_transport(transport=None)
    testbase.assert_equal(response.status_code, 401)
    return


def test_next_dispatch_returns_403_when_cert_cn_mismatches_path():
    """
    **Feature: PR p19g**
    **Property: cert common-name not matching the path client_id
    returns 403 with both ids in the problem extensions.**
    """
    _install_transport(transport=LongPollTransport())
    try:
        request = _FakeRequest(
            path="/api/v1/clients/{}/dispatches:next".format(_TEST_CLIENT_ID),
            path_params={"client_id": _TEST_CLIENT_ID},
            mtls_client_cn=_OTHER_CLIENT_ID,
        )
        response = client_dispatch_routes.handle_next_dispatch(request)
    finally:
        _install_transport(transport=None)
    testbase.assert_equal(response.status_code, 403)
    body = _decode_body(response)
    testbase.assert_equal(body["path_client_id"], _TEST_CLIENT_ID)
    testbase.assert_equal(body["cert_client_cn"], _OTHER_CLIENT_ID)
    return


def test_next_dispatch_returns_422_on_malformed_timeout():
    """
    **Feature: PR p19g**
    **Property: non-integer timeout_seconds returns 422.**
    """
    _install_transport(transport=LongPollTransport())
    try:
        request = _FakeRequest(
            path="/api/v1/clients/{}/dispatches:next".format(_TEST_CLIENT_ID),
            path_params={"client_id": _TEST_CLIENT_ID},
            query_params={"timeout_seconds": "not-a-number"},
            mtls_client_cn=_TEST_CLIENT_ID,
        )
        response = client_dispatch_routes.handle_next_dispatch(request)
    finally:
        _install_transport(transport=None)
    testbase.assert_equal(response.status_code, 422)
    return


def test_next_dispatch_returns_503_when_transport_unconfigured():
    """
    **Feature: PR p19g**
    **Property: returns 503 when the bootstrap has not published a
    LongPollTransport.**
    """
    _install_transport(transport=None)
    request = _FakeRequest(
        path="/api/v1/clients/{}/dispatches:next".format(_TEST_CLIENT_ID),
        path_params={"client_id": _TEST_CLIENT_ID},
        mtls_client_cn=_TEST_CLIENT_ID,
    )
    response = client_dispatch_routes.handle_next_dispatch(request)
    testbase.assert_equal(response.status_code, 503)
    return


def test_next_dispatch_returns_204_on_timeout():
    """
    **Feature: PR p19g**
    **Property: an empty queue + timeout=0 returns 204 with empty
    body.**
    """
    transport = LongPollTransport()
    _install_transport(transport=transport)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/{}/dispatches:next".format(_TEST_CLIENT_ID),
            path_params={"client_id": _TEST_CLIENT_ID},
            query_params={"timeout_seconds": "0"},
            mtls_client_cn=_TEST_CLIENT_ID,
        )
        response = client_dispatch_routes.handle_next_dispatch(request)
    finally:
        _install_transport(transport=None)
    testbase.assert_equal(response.status_code, 204)
    testbase.assert_equal(response.body, b"")
    return


def test_next_dispatch_returns_200_with_envelope_when_queued():
    """
    **Feature: PR p19g (integration)**
    **Property: a record enqueued via transport.transmit() is
    delivered by the route on the next pull with the signed
    envelope in the body.**
    """
    transport = LongPollTransport()
    signed = _build_signed_envelope()
    transport.transmit(
        client_id=_TEST_CLIENT_ID, pod_id=_TEST_POD_ID, signed=signed,
    )
    _install_transport(transport=transport)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/{}/dispatches:next".format(_TEST_CLIENT_ID),
            path_params={"client_id": _TEST_CLIENT_ID},
            query_params={"timeout_seconds": "1"},
            mtls_client_cn=_TEST_CLIENT_ID,
        )
        response = client_dispatch_routes.handle_next_dispatch(request)
    finally:
        _install_transport(transport=None)
    testbase.assert_equal(response.status_code, 200)
    body = _decode_body(response)
    testbase.assert_equal(body["client_id"], _TEST_CLIENT_ID)
    testbase.assert_equal(body["pod_id"], _TEST_POD_ID)
    testbase.assert_equal(body["run_id"], _TEST_RUN_ID)
    testbase.assert_equal(
        body["envelope_id"], signed.envelope.envelope_id,
    )
    testbase.assert_equal(body["transport_name"], LONG_POLL_TRANSPORT_NAME)
    testbase.assert_equal(body["envelope"]["run_id"], _TEST_RUN_ID)
    testbase.assert_equal(body["signature"], "01020304")
    return


# ---------------------------------------------------------------------------
# /heartbeat route tests
# ---------------------------------------------------------------------------


def test_heartbeat_returns_401_without_mtls():
    """
    **Feature: PR p19g**
    **Property: heartbeat returns 401 when no mTLS cert.**
    """
    request = _FakeRequest(
        path="/api/v1/clients/{}/heartbeat".format(_TEST_CLIENT_ID),
        path_params={"client_id": _TEST_CLIENT_ID},
    )
    response = client_dispatch_routes.handle_client_heartbeat(request)
    testbase.assert_equal(response.status_code, 401)
    return


def test_heartbeat_returns_403_on_cert_mismatch():
    """
    **Feature: PR p19g**
    **Property: heartbeat returns 403 when cert CN does not match
    path client_id.**
    """
    request = _FakeRequest(
        path="/api/v1/clients/{}/heartbeat".format(_TEST_CLIENT_ID),
        path_params={"client_id": _TEST_CLIENT_ID},
        mtls_client_cn=_OTHER_CLIENT_ID,
    )
    response = client_dispatch_routes.handle_client_heartbeat(request)
    testbase.assert_equal(response.status_code, 403)
    return


def test_heartbeat_returns_204_when_no_db_session_bound():
    """
    **Feature: PR p19g**
    **Property: heartbeat returns 204 even when the request lacks a
    db session (registry update is skipped, the agent still gets a
    success answer).**
    """
    request = _FakeRequest(
        path="/api/v1/clients/{}/heartbeat".format(_TEST_CLIENT_ID),
        path_params={"client_id": _TEST_CLIENT_ID},
        mtls_client_cn=_TEST_CLIENT_ID,
    )
    response = client_dispatch_routes.handle_client_heartbeat(request)
    testbase.assert_equal(response.status_code, 204)
    return


def test_heartbeat_invokes_registry_record_heartbeat():
    """
    **Feature: PR p19g**
    **Property: a successful heartbeat call delegates to
    clients.registry.service.record_heartbeat() with the path
    client_id and the long-poll transport name.**
    """
    captured: Dict[str, Any] = {}

    def fake_record_heartbeat(**kwargs: Any) -> None:
        captured.update(kwargs)
        return

    patch = create_module_patch(
        client_dispatch_routes.client_registry_service, "record_heartbeat",
    )
    mock = patch.activate()
    mock.configure(side_effect=fake_record_heartbeat)
    try:
        request = _FakeRequest(
            path="/api/v1/clients/{}/heartbeat".format(_TEST_CLIENT_ID),
            path_params={"client_id": _TEST_CLIENT_ID},
            mtls_client_cn=_TEST_CLIENT_ID,
            db_session=object(),
        )
        response = client_dispatch_routes.handle_client_heartbeat(request)
    finally:
        patch.deactivate()
    testbase.assert_equal(response.status_code, 204)
    testbase.assert_equal(captured["client_id"], _TEST_CLIENT_ID)
    testbase.assert_equal(captured["transport_name"], LONG_POLL_TRANSPORT_NAME)
    return


# ---------------------------------------------------------------------------
# Default-timeout regression
# ---------------------------------------------------------------------------


def test_default_timeout_constant_matches_spec():
    """
    **Feature: PR p19g**
    **Property: the long-poll default timeout matches the OpenAPI
    spec value (30s) so client + server agree on the wait window.**
    """
    testbase.assert_equal(DEFAULT_LONG_POLL_TIMEOUT_SECONDS, 30)
    testbase.assert_equal(MAX_LONG_POLL_TIMEOUT_SECONDS, 60)
    return
