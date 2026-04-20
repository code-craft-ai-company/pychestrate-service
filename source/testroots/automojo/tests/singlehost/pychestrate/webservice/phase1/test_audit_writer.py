"""
.. module:: test_audit_writer
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-audit-log audit_writer + chain_verifier + bus_subscriber.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.audit import audit_writer, bus_subscriber, chain_verifier
from automojo.pychestrate.webservice.audit.exceptions import UnknownAuditKindError
from automojo.pychestrate.webservice.audit.models import AuditRecord
from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, publish

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
    session_for,
)


def _capture_user_event(session) -> AuditRecord:
    record = audit_writer.capture_event(
        db_session=session,
        source_event_id=new_uuid(),
        source_topic="entity.user.created",
        kind="audit.user.created",
        actor_user_id=None,
        actor_service_identity=None,
        target_ref="user:abc",
        payload={
            "user_id": "abc",
            "login_name": "u1",
            "provisioning_source": "local",
        },
    )
    session.commit()
    return record


def test_capture_event_assigns_monotonic_sequence():
    """
    **Feature: 1-audit-log**
    **Property: sequence_number is server-assigned and monotonic.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    first = _capture_user_event(session)
    second = _capture_user_event(session)

    testbase.assert_equal(second.sequence_number > first.sequence_number, True)
    return


def test_chain_hash_is_stable_and_verifiable():
    """
    **Feature: 1-audit-log**
    **Property: verify_audit_chain returns ok=True for a clean span.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    first = _capture_user_event(session)
    second = _capture_user_event(session)

    result = chain_verifier.verify_audit_chain(
        db_session=session,
        from_sequence=first.sequence_number,
        to_sequence=second.sequence_number,
    )

    testbase.assert_equal(result.ok, True)
    testbase.assert_equal(result.first_break, None)
    testbase.assert_equal(result.records_checked, 2)
    return


def test_chain_tamper_is_detected():
    """
    **Feature: 1-audit-log**
    **Property: Mutating a record's payload breaks the hash chain and the
    verifier reports the tampered row.**
    """
    reset_phase1_runtime()
    engine, session = build_in_memory_session()

    first = _capture_user_event(session)
    second = _capture_user_event(session)

    tamper_session = session_for(engine=engine)
    row = (
        tamper_session.query(AuditRecord)
        .filter(AuditRecord.sequence_number == first.sequence_number)
        .first()
    )
    mutated = dict(row.payload_json)
    mutated["login_name"] = "tampered"
    row.payload_json = mutated
    tamper_session.commit()
    tamper_session.close()

    verify_session = session_for(engine=engine)
    result = chain_verifier.verify_audit_chain(
        db_session=verify_session,
        from_sequence=first.sequence_number,
        to_sequence=second.sequence_number,
    )
    verify_session.close()

    testbase.assert_equal(result.ok, False)
    testbase.assert_equal(result.first_break, first.sequence_number)
    return


def test_unknown_kind_raises_unknown_audit_kind_error():
    """
    **Feature: 1-audit-log**
    **Property: capture_event with an unregistered kind raises
    UnknownAuditKindError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        audit_writer.capture_event(
            db_session=session,
            source_event_id=new_uuid(),
            source_topic="entity.test.never",
            kind="audit.unknown.kind",
            actor_user_id=None,
            actor_service_identity=None,
            target_ref=None,
            payload={},
        )
    except UnknownAuditKindError:
        raised = True

    testbase.assert_equal(raised, True)
    return


def test_bus_subscriber_wires_entity_to_audit():
    """
    **Feature: 1-audit-log**
    **Property: wire_bus_subscribers installs handlers that turn
    published entity events into audit_records rows.**
    """
    reset_phase1_runtime()
    engine, _unused = build_in_memory_session()

    def _session_factory():
        return session_for(engine=engine)

    bus_subscriber.wire_bus_subscribers(session_factory=_session_factory)

    publish(event=EntityEvent(
        topic="entity.user.created",
        payload={
            "user_id": "u1",
            "login_name": "u1",
            "provisioning_source": "local",
            "target_ref": "user:u1",
        },
        source_event_id=new_uuid(),
    ))

    verify_session = session_for(engine=engine)
    count = verify_session.query(AuditRecord).count()
    verify_session.close()

    testbase.assert_equal(count, 1)
    return


def test_end_to_end_user_create_produces_audit_row():
    """
    **Feature: 1-user-management + 1-audit-log**
    **Property: user_service.create_user's published event flows through
    bus_subscriber and lands in audit_records.**
    """
    reset_phase1_runtime()
    engine, session = build_in_memory_session()

    def _session_factory():
        return session_for(engine=engine)

    bus_subscriber.wire_bus_subscribers(session_factory=_session_factory)

    user_service.create_user(
        db_session=session,
        login_name="eve",
        primary_email="eve@example.com",
        display_name="Eve",
        timezone="UTC",
        provisioning_source="local",
        external_id=None,
        actor_user_id=None,
    )

    verify_session = session_for(engine=engine)
    rows = verify_session.query(AuditRecord).all()
    verify_session.close()

    testbase.assert_equal(len(rows), 1)
    testbase.assert_equal(rows[0].kind, "audit.user.created")
    return
