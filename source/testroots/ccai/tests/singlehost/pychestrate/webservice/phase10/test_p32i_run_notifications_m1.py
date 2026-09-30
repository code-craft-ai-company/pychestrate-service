"""
.. module:: test_p32i_run_notifications_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A run's failure or completion reaches the notification rules (ORG-F08).

.. moduleauthor:: Code Craft AI LLC

The service could render a notification and send it through a channel, and could
store routing rules, but nothing connected a run's end to either: ``dispatch_envelope``
had no caller and the Webhooks, Alert Rules and Notifications settings had no effect.
The run notifier now subscribes to ``entity.run.failed`` and ``entity.run.completed``,
queues each event (so sending never runs inside the request that ingests the pod's
result), and a worker delivers it through the enabled rules that apply. These tests
cover the matching, the rate limit, the delivery and its failure paths, and the queue
and worker, against an in-memory database and a recording channel.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, ClassVar, Dict, List, Mapping, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import Session as DbSession, sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.webservice.extensions import registry
from ccai.pychestrate.webservice.jobs.run.state.events import RunStateEventTopics
from ccai.pychestrate.webservice.messaging import event_bus
from ccai.pychestrate.webservice.notifications import register_builtin_extensions as register_notifications
from ccai.pychestrate.webservice.notifications import router, run_notifier
from ccai.pychestrate.webservice.notifications import service as notification_service
from ccai.pychestrate.webservice.notifications.factories.channel import (
    ChannelDeliveryOutcome,
    NotificationChannelProtocol,
)
from ccai.pychestrate.webservice.notifications.models import (
    ChannelScopeLevel,
    NotificationDeadLetter,
    NotificationDispatchAttempt,
    NotificationDispatchEnvelope,
)
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from ccai.pychestrate.webservice.projects.models import Project


PROJECT_A: str = "0f6c2c1e-6666-4000-8000-00000000000a"
PROJECT_B: str = "0f6c2c1e-6666-4000-8000-00000000000b"
RUN_ID: str = "aaaaaaaa-1111-4000-8000-000000000001"


class _RecordingChannel(NotificationChannelProtocol):
    """A channel that records what it is asked to send; ``config['fail']`` makes it report a failure."""

    factory_protocol_name: ClassVar[str] = "notification_channel"
    protocol_schema_version: ClassVar[int] = 1
    channel_kind: ClassVar[str] = "test_recorder"
    PRECEDENCE: ClassVar[int] = 1000
    sent: ClassVar[List[Tuple[str, str, str]]] = []

    @classmethod
    def send(cls, *, channel_config: Mapping[str, Any], recipient: str, subject: str, body: str) -> ChannelDeliveryOutcome:
        if channel_config.get("fail", False) is True:
            return ChannelDeliveryOutcome(delivered=False, error_message="relay down", latency_ms=3)
        cls.sent.append((recipient, subject, body))
        return ChannelDeliveryOutcome(delivered=True, error_message="", latency_ms=2)


def _world() -> Tuple[Any, Any]:
    """A fresh registry and an in-memory database that a worker thread can share (one connection)."""
    registry.reset_registry_for_testing()
    event_bus.reset_for_testing()
    register_notifications()
    registry.register_factory_implementation(implementation=_RecordingChannel)
    _RecordingChannel.sent = []
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.add(Project(project_id=PROJECT_A, slug="alpha", display_name="Alpha"))
    session.add(Project(project_id=PROJECT_B, slug="beta", display_name="Beta"))
    session.commit()
    return factory, session


def _cleanup(session: DbSession) -> None:
    session.close()
    run_notifier.unwire_run_notifications()
    registry.reset_registry_for_testing()
    event_bus.reset_for_testing()


def _channel(session: DbSession, name: str = "ops", config: Dict[str, Any] = None) -> str:
    channel = notification_service.create_channel(
        db_session=session, name=name, kind="test_recorder", scope_level=ChannelScopeLevel.SYSTEM,
        project_id=None, config=config or {}, actor_user_id=None,
    )
    return str(channel.channel_id)


def _rule(session: DbSession, channel_ids: List[str], *, project_id: Any = None, pattern: str = RunStateEventTopics.FAILED, template: str = "run_failed", recipients: List[str] = None, limit: Any = None) -> Any:
    return notification_service.create_routing_rule(
        db_session=session, project_id=project_id, event_pattern=pattern, template_name=template, channel_ids=channel_ids,
        recipients=recipients or ["oncall@example.test"], filter_tag_expression=None, rate_limit_per_minute=limit, actor_user_id=None,
    )


def _payload(project_id: str = PROJECT_A) -> Dict[str, Any]:
    return {"run_id": RUN_ID, "project_slug": "alpha", "project_id": project_id, "reason": "3 tests failed"}


def test_a_pattern_is_a_topic_or_a_glob_over_topics():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: a rule's event pattern matches the topic it names and any topic a glob
    covers (``entity.run.*``), and not a topic outside it; matching is case-sensitive.**
    """
    cases = {
        ("entity.run.failed", "entity.run.failed"): True,
        ("entity.run.*", "entity.run.completed"): True,
        ("entity.run.failed", "entity.run.completed"): False,
        ("entity.*", "entity.notification.failed"): True,
        ("ENTITY.RUN.FAILED", "entity.run.failed"): False,
        (" entity.run.failed ", "entity.run.failed"): True,
    }

    testbase.assert_equal({key: router.pattern_matches(pattern=key[0], topic=key[1]) for key in cases}, cases)
    return


def test_the_routes_follow_the_rules_project_pattern_and_enabled_state():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: an enabled rule of the event's project, or of no project, whose pattern
    matches yields one route per channel and recipient; a rule of another project, a
    disabled rule and a rule for another event yield none.**
    """
    class Rule:
        def __init__(self, **fields: Any) -> None:
            self.__dict__.update({"disabled": False, "project_id": None, "rule_id": str(uuid.uuid4()), "template_name": "run_failed", "channel_ids": ["c1", "c2"], "recipients": ["a@x", "b@x"], "event_pattern": "entity.run.failed"})
            self.__dict__.update(fields)

    rules = [
        Rule(),
        Rule(project_id=PROJECT_A, channel_ids=["c3"], recipients=["only@x"]),
        Rule(project_id=PROJECT_B),
        Rule(disabled=True),
        Rule(event_pattern="entity.run.completed"),
    ]
    routes = router.compute_routes(rules=rules, topic="entity.run.failed", project_id=PROJECT_A)

    testbase.assert_equal(
        (len(routes), [(route.channel_id, route.recipient) for route in routes]),
        (5, [("c1", "a@x"), ("c1", "b@x"), ("c2", "a@x"), ("c2", "b@x"), ("c3", "only@x")]),
    )
    return


def test_a_rule_is_limited_to_its_share_of_each_minute():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: with a limit of 2 a rule is allowed twice in a minute and refused the
    third time, allowed again once the minute has passed, and a rule with no limit is
    never refused; the limit of one rule does not count against another.**
    """
    now = {"t": 1000.0}
    limiter = router.RuleRateLimiter(clock=lambda: now["t"])
    first = [limiter.allow(rule_id="r1", per_minute=2) for _ in range(3)]
    other = limiter.allow(rule_id="r2", per_minute=2)
    now["t"] += 61.0
    later = limiter.allow(rule_id="r1", per_minute=2)
    unlimited = [limiter.allow(rule_id="r3", per_minute=None) for _ in range(50)]

    testbase.assert_equal((first, other, later, all(unlimited)), ([True, True, False], True, True, True))
    return


def test_a_failed_run_is_delivered_through_the_matching_rules_and_recorded():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: routing ``entity.run.failed`` sends the run-failed message (naming the
    run and the project) to each recipient of the project's rule and of the system-wide
    rule, sends nothing for another project's rule, and records an envelope and a
    delivered attempt for each message.**
    """
    factory, session = _world()
    try:
        channel = _channel(session)
        _rule(session, [channel], project_id=PROJECT_A, recipients=["a@example.test"])
        _rule(session, [channel], project_id=None, recipients=["all@example.test"])
        _rule(session, [channel], project_id=PROJECT_B, recipients=["b@example.test"])

        outcomes = router.route_event(db_session=session, topic=RunStateEventTopics.FAILED, payload=_payload())
        envelopes = session.query(NotificationDispatchEnvelope).count()
        attempts = [attempt.outcome.value for attempt in session.query(NotificationDispatchAttempt).all()]
    finally:
        _cleanup(session)

    testbase.assert_equal(
        (sorted(recipient for recipient, _s, _b in _RecordingChannel.sent), [outcome.delivered for outcome in outcomes], envelopes, attempts),
        (["a@example.test", "all@example.test"], [True, True], 2, ["DELIVERED", "DELIVERED"]),
    )
    testbase.assert_equal(
        [subject for _r, subject, _b in _RecordingChannel.sent][0],
        "[Pychestrate] Run {} failed in alpha".format(RUN_ID),
    )
    return


def test_a_delivery_that_cannot_be_made_is_recorded_and_the_others_still_go():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: a channel that reports failure, a channel that is disabled and a rule
    that names a template that does not exist are each reported with the reason and do
    not stop the delivery through a working channel; the failed delivery is parked as a
    dead letter for replay.**
    """
    factory, session = _world()
    try:
        good = _channel(session, "good")
        broken = _channel(session, "broken", {"fail": True})
        off = _channel(session, "off")
        notification_service.read_channel(db_session=session, channel_id=off).disabled = True
        session.commit()
        _rule(session, [broken, off, good], recipients=["a@example.test"])
        _rule(session, [good], template="no_such_template", recipients=["b@example.test"])

        outcomes = router.route_event(db_session=session, topic=RunStateEventTopics.FAILED, payload=_payload())
        summary = [(outcome.route.recipient, outcome.delivered, outcome.skipped_reason, outcome.error.split(":")[0]) for outcome in outcomes]
        dead_letters = session.query(NotificationDeadLetter).count()
    finally:
        _cleanup(session)

    testbase.assert_equal(
        (summary, [recipient for recipient, _s, _b in _RecordingChannel.sent], dead_letters),
        (
            [
                ("a@example.test", False, "", "NotificationDispatchError"),
                ("a@example.test", False, "channel_disabled", ""),
                ("a@example.test", True, "", ""),
                ("b@example.test", False, "", "TemplateNotFoundError"),
            ],
            ["a@example.test"],
            1,
        ),
    )
    return


def test_a_rule_over_its_limit_skips_the_delivery():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: with a limit of 1 per minute, two failures in a minute send one message
    and report the second as skipped for rate limiting.**
    """
    factory, session = _world()
    try:
        _rule(session, [_channel(session)], limit=1)
        limiter = router.RuleRateLimiter()
        first = router.route_event(db_session=session, topic=RunStateEventTopics.FAILED, payload=_payload(), limiter=limiter)
        second = router.route_event(db_session=session, topic=RunStateEventTopics.FAILED, payload=_payload(), limiter=limiter)
    finally:
        _cleanup(session)

    testbase.assert_equal(
        ([outcome.delivered for outcome in first], [(outcome.delivered, outcome.skipped_reason) for outcome in second], len(_RecordingChannel.sent)),
        ([True], [(False, "rate_limited")], 1),
    )
    return


def test_a_published_run_failure_is_delivered_by_the_worker_not_the_publisher():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: with the notifier wired, publishing ``entity.run.failed`` on the bus
    returns at once, and the worker then sends the message (naming the project by its
    slug, read from the database); an event for a topic no rule asks for sends
    nothing; ``entity.run.completed`` uses the run-succeeded template; and a glob rule
    (``entity.run.*``) whose template describes only failures is skipped for a
    completed run instead of calling it a failure.**
    """
    factory, session = _world()
    try:
        channel = _channel(session)
        _rule(session, [channel], pattern="entity.run.*", template="run_failed", recipients=["all@example.test"])
        _rule(session, [channel], pattern=RunStateEventTopics.COMPLETED, template="run_succeeded", recipients=["done@example.test"])
        notifier = run_notifier.wire_run_notifications(session_factory=factory)

        event_bus.publish(event=event_bus.EntityEvent(topic=RunStateEventTopics.FAILED, payload={"run_id": RUN_ID, "project_id": PROJECT_A, "to_state": "failed", "reason": "3 tests failed"}, source_event_id=str(uuid.uuid4())))
        event_bus.publish(event=event_bus.EntityEvent(topic=RunStateEventTopics.COMPLETED, payload={"run_id": RUN_ID, "project_id": PROJECT_B, "to_state": "completed"}, source_event_id=str(uuid.uuid4())))
        event_bus.publish(event=event_bus.EntityEvent(topic=RunStateEventTopics.CANCELLED, payload={"run_id": RUN_ID, "project_id": PROJECT_A, "to_state": "cancelled"}, source_event_id=str(uuid.uuid4())))
        idle = notifier.wait_until_idle()
        sent = sorted(_RecordingChannel.sent)
    finally:
        _cleanup(session)

    testbase.assert_equal(
        (idle, [(recipient, subject) for recipient, subject, _b in sent]),
        (
            True,
            [
                ("all@example.test", "[Pychestrate] Run {} failed in alpha".format(RUN_ID)),
                ("done@example.test", "[Pychestrate] Run {} completed in beta".format(RUN_ID)),
            ],
        ),
    )
    return


def test_a_full_queue_drops_the_event_and_a_bad_event_does_not_stop_the_worker():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: when the queue is full the event is dropped and counted (the publisher
    never blocks); an event whose handling raises is logged and the worker goes on to
    deliver the next one.**
    """
    factory, session = _world()
    try:
        _rule(session, [_channel(session)], recipients=["a@example.test"])
        notifier = run_notifier.RunNotifier(session_factory=factory, queue_limit=1)
        event = event_bus.EntityEvent(topic=RunStateEventTopics.FAILED, payload={"run_id": RUN_ID, "project_id": PROJECT_A}, source_event_id="e")
        notifier.on_event(event)
        notifier.on_event(event)
        dropped = notifier.dropped

        original = notifier.handle
        calls: List[int] = []

        def _flaky(*, topic: str, event_payload: Mapping[str, Any]) -> Any:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("database went away")
            return original(topic=topic, event_payload=event_payload)

        notifier.handle = _flaky  # type: ignore[method-assign]
        notifier.start()
        notifier.wait_until_idle()
        notifier.on_event(event)
        idle = notifier.wait_until_idle()
        notifier.stop()
        handled = notifier.handled
    finally:
        _cleanup(session)

    testbase.assert_equal((dropped, idle, handled, len(_RecordingChannel.sent)), (1, True, 2, 1))
    return


def test_wiring_twice_delivers_once():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: wiring the notifier again (a re-bootstrap) replaces the earlier one, so
    one failure is delivered once, not twice.**
    """
    factory, session = _world()
    try:
        _rule(session, [_channel(session)], recipients=["a@example.test"])
        run_notifier.wire_run_notifications(session_factory=factory)
        notifier = run_notifier.wire_run_notifications(session_factory=factory)
        event_bus.publish(event=event_bus.EntityEvent(topic=RunStateEventTopics.FAILED, payload={"run_id": RUN_ID, "project_id": PROJECT_A}, source_event_id="e"))
        notifier.wait_until_idle()
    finally:
        _cleanup(session)

    testbase.assert_equal(len(_RecordingChannel.sent), 1)
    return


def test_the_services_startup_wires_the_notifier():
    """
    **Feature: run notifications (ORG-F08)**
    **Property: the phase 2 bootstrap the service runs at start wires the notifier, so
    a run failure published after start is delivered (this is what makes the rules
    take effect in a deployed service, not only in a test that wires it by hand).**
    """
    from ccai.pychestrate.webservice.extensions.phase2_bootstrap import Phase2BootstrapConfig, bootstrap_phase2_runtime

    factory, session = _world()
    try:
        _rule(session, [_channel(session)], recipients=["a@example.test"])
        registry.reset_registry_for_testing()
        registry.register_factory_implementation(implementation=_RecordingChannel)
        bootstrap_phase2_runtime(config=Phase2BootstrapConfig(session_factory=factory))
        notifier = run_notifier._NOTIFIER
        event_bus.publish(event=event_bus.EntityEvent(topic=RunStateEventTopics.FAILED, payload={"run_id": RUN_ID, "project_id": PROJECT_A}, source_event_id="e"))
        idle = notifier.wait_until_idle() if notifier is not None else False
    finally:
        _cleanup(session)

    testbase.assert_equal((notifier is not None, idle, len(_RecordingChannel.sent)), (True, True, 1))
    return
