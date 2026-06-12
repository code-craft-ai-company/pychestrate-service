"""
.. module:: test_agents_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the Layer-3 agent services.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.agents import (
    capability_service,
    inventory_service,
    protocol_service,
    upgrade_service,
)
from ccai.pychestrate.webservice.agents.exceptions import (
    FrameValidationError,
    UnknownCapabilityKindError,
)
from ccai.pychestrate.webservice.agents.factories.in_memory_transport import (
    InMemoryLoopbackTransport,
)
from ccai.pychestrate.webservice.agents.factories.transport import (
    InboundFrame,
    OutboundFrame,
)
from ccai.pychestrate.webservice.agents.models import (
    FrameDirection,
    UpgradeOfferOutcome,
)
from ccai.pychestrate.webservice.messaging.event_bus import subscribe

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from ccai.tests.singlehost.pychestrate.webservice.phase3.fixtures import (
    reset_phase3_runtime,
)


def test_in_memory_transport_round_trip():
    """
    **Feature: 3-client-agent-protocol (M1)**
    **Property: InMemoryLoopbackTransport.encode → decode returns the
    original frame kind + payload.**
    """
    out = OutboundFrame(kind="heartbeat", payload={"agent_version": "1.2.3"})
    encoded = InMemoryLoopbackTransport.encode(frame=out)
    decoded = InMemoryLoopbackTransport.decode(payload=encoded)
    testbase.assert_equal(decoded.kind, "heartbeat")
    testbase.assert_equal(decoded.payload.get("agent_version"), "1.2.3")
    return


def test_open_record_close_session_and_events():
    """
    **Feature: 3-client-agent-protocol (M1)**
    **Property: open_session → record_frame → close_session publishes
    matching bus events.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    opened = []
    closed = []
    subscribe(topic="entity.client.session_opened", subscriber=lambda e: opened.append(e))
    subscribe(topic="entity.client.session_closed", subscriber=lambda e: closed.append(e))

    session_row = protocol_service.open_session(
        db_session=session, transport_name="in_memory_loopback",
        remote_addr="127.0.0.1", cert_serial=None, client_id=None,
    )
    protocol_service.record_frame(
        db_session=session, session_id=str(session_row.session_id),
        kind="heartbeat", direction=FrameDirection.INBOUND,
        size_bytes=10, accepted=True, reject_reason=None,
    )
    protocol_service.close_session(
        db_session=session, session_id=str(session_row.session_id),
        close_code="ok",
    )

    testbase.assert_equal(len(opened), 1)
    testbase.assert_equal(len(closed), 1)
    return


def test_record_frame_rejects_unknown_kind():
    """
    **Feature: 3-client-agent-protocol (M1)**
    **Property: Unknown frame kinds raise FrameValidationError before
    hitting the audit table.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()
    session_row = protocol_service.open_session(
        db_session=session, transport_name="in_memory_loopback",
        remote_addr=None, cert_serial=None, client_id=None,
    )
    raised = False
    try:
        protocol_service.record_frame(
            db_session=session, session_id=str(session_row.session_id),
            kind="not_real", direction=FrameDirection.INBOUND,
            size_bytes=0, accepted=True, reject_reason=None,
        )
    except FrameValidationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_apply_advertisement_and_read_back():
    """
    **Feature: 3-client-capability-advertisement (M1)**
    **Property: apply_advertisement replaces rows and
    list_capabilities_for_client returns them.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    client_id = new_uuid()
    capability_service.apply_advertisement(
        db_session=session, client_id=client_id,
        advertisements=[
            {"kind": "concurrency", "value": {"max_parallel_jobs": 4}},
            {"kind": "pod_member_ownership", "value": ["linux_host"]},
        ],
        actor_user_id=None,
    )

    rows = capability_service.list_capabilities_for_client(
        db_session=session, client_id=client_id, include_sensitive=False,
    )
    kinds = sorted([r.kind for r in rows])
    testbase.assert_equal(kinds, ["concurrency", "pod_member_ownership"])
    return


def test_apply_advertisement_rejects_unknown_kind():
    """
    **Feature: 3-client-capability-advertisement (M1)**
    **Property: Unknown kinds raise UnknownCapabilityKindError.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        capability_service.apply_advertisement(
            db_session=session, client_id=new_uuid(),
            advertisements=[{"kind": "does_not_exist", "value": {}}],
            actor_user_id=None,
        )
    except UnknownCapabilityKindError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_draft_and_start_rollout_publishes_offers():
    """
    **Feature: 3-agent-upgrade-channel (M1)**
    **Property: start_rollout transitions to ACTIVE and emits an
    ``entity.upgrade.offered`` per picked client.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    offers_received = []
    subscribe(topic="entity.upgrade.offered", subscriber=lambda e: offers_received.append(e))

    rollout = upgrade_service.draft_rollout(
        db_session=session, version="2.3.4",
        artifact_source="object_store",
        artifact_ref="objstore://agents/2.3.4.tar.gz",
        signature=None, actor_user_id=None,
    )

    candidate_ids = [new_uuid() for _ in range(5)]
    offers = upgrade_service.start_rollout(
        db_session=session, rollout_id=str(rollout.rollout_id),
        candidate_client_ids=candidate_ids, target_size=3,
        actor_user_id=None,
    )
    testbase.assert_equal(len(offers), 3)
    testbase.assert_equal(len(offers_received), 3)

    finalized = upgrade_service.record_upgrade_outcome(
        db_session=session, offer_id=str(offers[0].offer_id),
        outcome=UpgradeOfferOutcome.SUCCEEDED, detail="installed",
    )
    testbase.assert_equal(finalized.outcome, UpgradeOfferOutcome.SUCCEEDED)
    return
