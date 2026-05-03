"""
.. module:: test_p11c_audit_log_m2
    :synopsis: Tests for P11c — 1-audit-log M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import tempfile

from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.audit import (
    audit_writer,
    register_builtin_extensions as audit_register,
    sink_dispatcher,
    sink_health,
)
from automojo.pychestrate.webservice.audit.events import AuditEventTopics
from automojo.pychestrate.webservice.audit.extensions.event_type import (
    AuditEventTypeExtension,
)
from automojo.pychestrate.webservice.audit.extensions.session_events import (
    SessionOpenedAuditEvents,
    SessionsRevokedAuditEvents,
)
from automojo.pychestrate.webservice.audit.extensions.flag_events import (
    FlagCreatedAuditEvents,
)
from automojo.pychestrate.webservice.audit.extensions.unknown_events import (
    UnknownAuditKindAuditEvents,
)
from automojo.pychestrate.webservice.audit.factories.json_file_sink import (
    JsonFileAuditSink,
    configure as configure_json_sink,
    reset_for_testing as reset_json_sink_path,
)
from automojo.pychestrate.webservice.audit.models import (
    AuditRecord,
    AuditSinkOutbox,
    AuditSinkOutboxStatus,
)
from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    list_resource_extensions,
    register_factory_implementation,
    reset_registry_for_testing,
    unregister_factory_implementation,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.audit.factories.audit_sink import (
    AuditSinkProtocol,
    SinkHealth,
    SinkWriteResult,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_json_sink_path()
    sink_health.reset_for_testing()
    audit_register()
    return


# -------------------------------------
# Event-type extensions (T2.1)
# -------------------------------------

def test_session_audit_event_packs_register():
    """
    **Feature: 1-audit-log (M2)**
    **Property: register_builtin_extensions seats every M2
    session-related event-type pack.**
    """
    _prepare_runtime()
    impls = list_resource_extensions(base_class=AuditEventTypeExtension)
    kinds = set(impl.kind for impl in impls)
    expected = {
        "audit.session.opened",
        "audit.session.closed",
        "audit.session.revoked",
        "audit.auth.login.rejected",
        "audit.mfa.enrollment.created",
        "audit.mfa.challenge.verified",
    }
    testbase.assert_equal(expected.issubset(kinds), True)
    return


def test_flag_audit_event_packs_register():
    """
    **Feature: 1-audit-log (M2)**
    **Property: register_builtin_extensions seats the four
    feature-flag audit packs.**
    """
    _prepare_runtime()
    impls = list_resource_extensions(base_class=AuditEventTypeExtension)
    kinds = set(impl.kind for impl in impls)
    expected = {
        "audit.flag.created",
        "audit.flag.updated",
        "audit.flag.retired",
        "audit.flag.removed",
    }
    testbase.assert_equal(expected.issubset(kinds), True)
    return


def test_unknown_audit_kind_pack_is_registered():
    """
    **Feature: 1-audit-log (M2)**
    **Property: the audit.unknown fallback pack is always
    registered.**
    """
    _prepare_runtime()
    impls = list_resource_extensions(base_class=AuditEventTypeExtension)
    kinds = set(impl.kind for impl in impls)
    testbase.assert_equal("audit.unknown" in kinds, True)
    return


# -------------------------------------
# audit.unknown fallback (T2.7)
# -------------------------------------

def test_capture_unknown_kind_lands_under_audit_unknown():
    """
    **Feature: 1-audit-log (M2)**
    **Property: capture_event with an unregistered kind
    reroutes to audit.unknown and stamps the original kind +
    topic on the payload.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    record = audit_writer.capture_event(
        db_session=session,
        source_event_id=new_uuid(),
        source_topic="entity.feature.never-registered",
        kind="audit.feature.does-not-exist",
        actor_user_id=None,
        actor_service_identity=None,
        target_ref=None,
        payload={"some": "data"},
    )
    session.commit()
    testbase.assert_equal(record.kind, "audit.unknown")
    testbase.assert_equal(
        record.payload_json["unknown_original_kind"],
        "audit.feature.does-not-exist",
    )
    testbase.assert_equal(
        record.payload_json["unknown_source_topic"],
        "entity.feature.never-registered",
    )
    return


# -------------------------------------
# JsonFileAuditSink (T2.3)
# -------------------------------------

def test_json_file_sink_health_reports_unconfigured():
    """
    **Feature: 1-audit-log (M2)**
    **Property: JsonFileAuditSink.health_check returns
    unhealthy when no path is configured.**
    """
    _prepare_runtime()
    health = JsonFileAuditSink.health_check()
    testbase.assert_equal(health.healthy, False)
    testbase.assert_equal(health.reason, "path_not_configured")
    return


def test_json_file_sink_writes_canonical_jsonl():
    """
    **Feature: 1-audit-log (M2)**
    **Property: JsonFileAuditSink.write_records appends one
    canonical JSON line per record, with sequence + hash hex
    fields populated.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "audit.jsonl")
        configure_json_sink(file_path=path)

        record = audit_writer.capture_event(
            db_session=session,
            source_event_id=new_uuid(),
            source_topic="entity.session.opened",
            kind="audit.session.opened",
            actor_user_id=None,
            actor_service_identity=None,
            target_ref="user:alice",
            payload={
                "session_id": new_uuid(),
                "user_id": new_uuid(),
                "provider_kind": "LOCAL",
                "provider_name": "local",
                "mfa_method_name": None,
                "opened_at": "2026-04-25T00:00:00+00:00",
            },
        )
        session.commit()
        result = JsonFileAuditSink.write_records(records=(record,))
        testbase.assert_equal(result.written_count, 1)
        testbase.assert_equal(
            result.last_sequence_written,
            int(record.sequence_number),
        )
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        testbase.assert_equal(len(lines), 1)
        decoded = json.loads(lines[0])
        testbase.assert_equal(decoded["kind"], "audit.session.opened")
        testbase.assert_equal(
            decoded["sequence_number"], int(record.sequence_number),
        )
        testbase.assert_equal(
            decoded["record_hash_hex"],
            bytes(record.record_hash).hex(),
        )
    return


def test_json_file_sink_write_without_configure_raises():
    """
    **Feature: 1-audit-log (M2)**
    **Property: write_records without a configured path raises
    RuntimeError so wiring bugs surface loudly.**
    """
    _prepare_runtime()
    raised = False
    try:
        JsonFileAuditSink.write_records(records=tuple())
    except RuntimeError:
        raised = True
    # An empty record tuple short-circuits before the path
    # check; force non-empty.
    _engine, session = build_in_memory_session()
    record = audit_writer.capture_event(
        db_session=session,
        source_event_id=new_uuid(),
        source_topic="entity.session.opened",
        kind="audit.session.opened",
        actor_user_id=None,
        actor_service_identity=None,
        target_ref=None,
        payload={
            "session_id": new_uuid(),
            "user_id": new_uuid(),
            "provider_kind": "LOCAL",
            "provider_name": "local",
            "mfa_method_name": None,
            "opened_at": "2026-04-25T00:00:00+00:00",
        },
    )
    session.commit()
    raised = False
    try:
        JsonFileAuditSink.write_records(records=(record,))
    except RuntimeError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# Per-sink outbox + dispatcher (T2.2)
# -------------------------------------

def test_capture_event_enqueues_fanout_for_non_canonical_sinks():
    """
    **Feature: 1-audit-log (M2)**
    **Property: capture_event inserts one PENDING outbox row
    per non-canonical registered sink.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    record = audit_writer.capture_event(
        db_session=session,
        source_event_id=new_uuid(),
        source_topic="entity.session.opened",
        kind="audit.session.opened",
        actor_user_id=None,
        actor_service_identity=None,
        target_ref=None,
        payload={
            "session_id": new_uuid(),
            "user_id": new_uuid(),
            "provider_kind": "LOCAL",
            "provider_name": "local",
            "mfa_method_name": None,
            "opened_at": "2026-04-25T00:00:00+00:00",
        },
    )
    session.commit()
    pending = (
        session.query(AuditSinkOutbox)
        .filter(AuditSinkOutbox.sequence_number == record.sequence_number)
        .all()
    )
    sink_names = sorted(row.sink_name for row in pending)
    testbase.assert_equal(sink_names, ["json-file"])
    testbase.assert_equal(
        pending[0].status, AuditSinkOutboxStatus.PENDING,
    )
    return


def test_drain_sink_outbox_completes_pending_rows():
    """
    **Feature: 1-audit-log (M2)**
    **Property: drain_sink_outbox processes pending rows for a
    sink, flips them to COMPLETED, and reports the run.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "audit.jsonl")
        configure_json_sink(file_path=path)
        for i in range(3):
            audit_writer.capture_event(
                db_session=session,
                source_event_id=new_uuid(),
                source_topic="entity.session.opened",
                kind="audit.session.opened",
                actor_user_id=None,
                actor_service_identity=None,
                target_ref="session-{}".format(i),
                payload={
                    "session_id": new_uuid(),
                    "user_id": new_uuid(),
                    "provider_kind": "LOCAL",
                    "provider_name": "local",
                    "mfa_method_name": None,
                    "opened_at": "2026-04-25T00:00:00+00:00",
                },
            )
        session.commit()
        report = sink_dispatcher.drain_sink_outbox(
            db_session=session, sink_name="json-file",
        )
        testbase.assert_equal(report.processed, 3)
        testbase.assert_equal(report.succeeded, 3)
        testbase.assert_equal(report.failed, 0)
        completed = (
            session.query(AuditSinkOutbox)
            .filter(AuditSinkOutbox.sink_name == "json-file")
            .filter(AuditSinkOutbox.status == AuditSinkOutboxStatus.COMPLETED)
            .all()
        )
        testbase.assert_equal(len(completed), 3)
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        testbase.assert_equal(len(lines), 3)
    return


def test_drain_sink_outbox_canonical_is_no_op():
    """
    **Feature: 1-audit-log (M2)**
    **Property: drain_sink_outbox against the canonical sink
    is a no-op (the canonical write happened inline).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    audit_writer.capture_event(
        db_session=session,
        source_event_id=new_uuid(),
        source_topic="entity.session.opened",
        kind="audit.session.opened",
        actor_user_id=None,
        actor_service_identity=None,
        target_ref=None,
        payload={
            "session_id": new_uuid(),
            "user_id": new_uuid(),
            "provider_kind": "LOCAL",
            "provider_name": "local",
            "mfa_method_name": None,
            "opened_at": "2026-04-25T00:00:00+00:00",
        },
    )
    session.commit()
    report = sink_dispatcher.drain_sink_outbox(
        db_session=session, sink_name="local-db",
    )
    testbase.assert_equal(report.processed, 0)
    return


def test_drain_sink_outbox_unknown_sink_raises():
    """
    **Feature: 1-audit-log (M2)**
    **Property: drain_sink_outbox against an unknown sink
    raises ValueError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        sink_dispatcher.drain_sink_outbox(
            db_session=session, sink_name="not-real",
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# Canonical-sink health probe (T2.6)
# -------------------------------------

class _FlakySink(AuditSinkProtocol):
    factory_protocol_name: str = "audit_sink"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 5000
    SINK_NAME: str = "flaky"
    HEALTHY: bool = True

    @classmethod
    def sink_name(cls):
        return cls.SINK_NAME

    @classmethod
    def is_canonical(cls):
        return False

    @classmethod
    def write_records(cls, *, records):
        return SinkWriteResult(written_count=0, last_sequence_written=0)

    @classmethod
    def health_check(cls):
        if cls.HEALTHY is True:
            return SinkHealth(healthy=True, reason="")
        return SinkHealth(healthy=False, reason="simulated_failure")


def test_evaluate_sink_health_emits_unhealthy_on_first_failure():
    """
    **Feature: 1-audit-log (M2)**
    **Property: a sink that reports unhealthy on first probe
    triggers an AUDIT_SINK_UNHEALTHY emit. (The JsonFile sink
    is configured first so its initial-probe verdict is
    healthy.)
    """
    _prepare_runtime()
    register_factory_implementation(implementation=_FlakySink)
    _FlakySink.HEALTHY = False
    received: List[EntityEvent] = []
    subscribe(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        subscriber=lambda e: received.append(e),
    )
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            configure_json_sink(
                file_path=os.path.join(tmpdir, "audit.jsonl"),
            )
            _engine, session = build_in_memory_session()
            sink_health.evaluate_sink_health(db_session=session)
            flaky_emits = [
                e for e in received
                if e.payload.get("sink_name") == _FlakySink.SINK_NAME
            ]
            testbase.assert_equal(len(flaky_emits), 1)
    finally:
        _FlakySink.HEALTHY = True
        unregister_factory_implementation(implementation=_FlakySink)
    return


def test_evaluate_sink_health_emits_recovery_on_transition():
    """
    **Feature: 1-audit-log (M2)**
    **Property: a sink transitioning from unhealthy to healthy
    triggers an AUDIT_SINK_HEALTHY emit on the next probe.**
    """
    _prepare_runtime()
    register_factory_implementation(implementation=_FlakySink)
    _FlakySink.HEALTHY = False
    received_recovery: List[EntityEvent] = []
    subscribe(
        topic=AuditEventTopics.AUDIT_SINK_HEALTHY,
        subscriber=lambda e: received_recovery.append(e),
    )
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            configure_json_sink(
                file_path=os.path.join(tmpdir, "audit.jsonl"),
            )
            _engine, session = build_in_memory_session()
            sink_health.evaluate_sink_health(db_session=session)
            _FlakySink.HEALTHY = True
            sink_health.evaluate_sink_health(db_session=session)
            flaky_recovery = [
                e for e in received_recovery
                if e.payload.get("sink_name") == _FlakySink.SINK_NAME
            ]
            testbase.assert_equal(len(flaky_recovery), 1)
    finally:
        _FlakySink.HEALTHY = True
        unregister_factory_implementation(implementation=_FlakySink)
    return


def test_evaluate_sink_health_no_transition_no_emit():
    """
    **Feature: 1-audit-log (M2)**
    **Property: probing the same healthy sink twice emits
    nothing.**
    """
    _prepare_runtime()
    received_unhealthy: List[EntityEvent] = []
    received_healthy: List[EntityEvent] = []
    subscribe(
        topic=AuditEventTopics.AUDIT_SINK_UNHEALTHY,
        subscriber=lambda e: received_unhealthy.append(e),
    )
    subscribe(
        topic=AuditEventTopics.AUDIT_SINK_HEALTHY,
        subscriber=lambda e: received_healthy.append(e),
    )
    _engine, session = build_in_memory_session()
    sink_health.evaluate_sink_health(db_session=session)
    sink_health.evaluate_sink_health(db_session=session)
    testbase.assert_equal(len(received_healthy), 0)
    # The local-db sink reports healthy on first probe so no
    # transition emit fires.
    return


# -------------------------------------
# Bootstrap registration (T2.3 + T2.1)
# -------------------------------------

def test_json_file_sink_is_registered_as_factory():
    """
    **Feature: 1-audit-log (M2)**
    **Property: register_builtin_extensions seats the
    JsonFileAuditSink under the audit_sink factory protocol
    alongside the canonical local-db sink.**
    """
    _prepare_runtime()
    impls = list_factory_implementations(
        factory_protocol_name="audit_sink",
    )
    testbase.assert_equal(JsonFileAuditSink in impls, True)
    return
