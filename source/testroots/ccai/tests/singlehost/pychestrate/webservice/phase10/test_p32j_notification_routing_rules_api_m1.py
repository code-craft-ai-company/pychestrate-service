"""
.. module:: test_p32j_notification_routing_rules_api_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Routing rules can be created through the API, and a rule that could never send is refused (ORG-F08).

.. moduleauthor:: Code Craft AI LLC

Routing rules could be stored by the service layer but not created through the API,
so no installation could turn a run failure into a message. The four routes (create,
list, disable/enable, delete) are exercised here at the handler level against a real
in-memory database, like the channels' tests, and the last test follows a rule made
through the API to a message sent by the notifier.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import uuid

from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import Session as DbSession, sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.webservice.extensions import registry
from ccai.pychestrate.webservice.jobs.run.state.events import RunStateEventTopics
from ccai.pychestrate.webservice.messaging import event_bus
from ccai.pychestrate.webservice.notifications import register_builtin_extensions as register_notifications
from ccai.pychestrate.webservice.notifications import run_notifier
from ccai.pychestrate.webservice.notifications import service as notification_service
from ccai.pychestrate.webservice.notifications.models import ChannelScopeLevel
from ccai.pychestrate.webservice.notifications.restapi.v1 import routing_rules_routes as routes
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from ccai.pychestrate.webservice.projects.models import Project

from ccai.tests.singlehost.pychestrate.webservice.phase10.test_p32i_run_notifications_m1 import _RecordingChannel


PROJECT: str = "0f6c2c1e-6666-4000-8000-00000000000a"


class _Query:
    def __init__(self, values: Dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._values.get(key, default)


class _Request:
    """The parts of a webworks request the handlers read."""

    def __init__(self, *, session: DbSession, body: Any = None, path_params: Optional[Dict[str, str]] = None, query: Optional[Dict[str, str]] = None) -> None:
        self.path = "/api/v1/notifications/routing-rules"
        self.db_session = session
        self.actor_user_id = "u-1"
        self.path_params = path_params or {}
        self.query_params = _Query(query or {})
        self._body = body

    def json(self) -> Any:
        return self._body


def _world() -> Tuple[Any, DbSession, str]:
    registry.reset_registry_for_testing()
    event_bus.reset_for_testing()
    register_notifications()
    registry.register_factory_implementation(implementation=_RecordingChannel)
    _RecordingChannel.sent = []
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.add(Project(project_id=PROJECT, slug="alpha", display_name="Alpha"))
    session.commit()
    channel = notification_service.create_channel(
        db_session=session, name="ops", kind="test_recorder", scope_level=ChannelScopeLevel.SYSTEM, project_id=None, config={}, actor_user_id=None,
    )
    return factory, session, str(channel.channel_id)


def _done(session: DbSession) -> None:
    session.close()
    run_notifier.unwire_run_notifications()
    registry.reset_registry_for_testing()
    event_bus.reset_for_testing()


def _body(response: Any) -> Any:
    raw = response.body if hasattr(response, "body") else response._body
    return json.loads(raw.decode("utf-8")) if raw else None


def _valid(channel_id: str, **changes: Any) -> Dict[str, Any]:
    body: Dict[str, Any] = {"event_pattern": "entity.run.failed", "template_name": "run_failed", "channel_ids": [channel_id], "recipients": ["oncall@example.test"]}
    body.update(changes)
    return body


def test_a_rule_is_created_listed_disabled_enabled_and_deleted():
    """
    **Feature: notification routing rules API (ORG-F08)**
    **Property: POST answers 201 with the rule; GET lists it (and can be limited to
    a project); PATCH turns it off and on; DELETE answers 204 and the rule is gone.**
    """
    factory, session, channel = _world()
    try:
        created = routes.handle_create_routing_rule(_Request(session=session, body=_valid(channel, project_id=PROJECT, rate_limit_per_minute=5)))
        rule = _body(created)
        listed = _body(routes.handle_list_routing_rules(_Request(session=session)))
        for_project = _body(routes.handle_list_routing_rules(_Request(session=session, query={"project_id": PROJECT})))
        for_other = _body(routes.handle_list_routing_rules(_Request(session=session, query={"project_id": str(uuid.uuid4())})))
        off = routes.handle_update_routing_rule(_Request(session=session, body={"disabled": True}, path_params={"rule_id": rule["rule_id"]}))
        on = routes.handle_update_routing_rule(_Request(session=session, body={"disabled": False}, path_params={"rule_id": rule["rule_id"]}))
        gone = routes.handle_delete_routing_rule(_Request(session=session, path_params={"rule_id": rule["rule_id"]}))
        after = _body(routes.handle_list_routing_rules(_Request(session=session)))
    finally:
        _done(session)

    testbase.assert_equal(
        (
            created.status_code,
            {key: rule[key] for key in ("project_id", "event_pattern", "template_name", "channel_ids", "recipients", "rate_limit_per_minute", "disabled")},
            [item["rule_id"] for item in listed] == [rule["rule_id"]], [item["rule_id"] for item in for_project] == [rule["rule_id"]], for_other,
            (off.status_code, _body(off)["disabled"]), (on.status_code, _body(on)["disabled"]), gone.status_code, after,
        ),
        (
            201,
            {"project_id": PROJECT, "event_pattern": "entity.run.failed", "template_name": "run_failed", "channel_ids": [channel], "recipients": ["oncall@example.test"], "rate_limit_per_minute": 5, "disabled": False},
            True, True, [], (200, True), (200, False), 204, [],
        ),
    )
    return


def test_a_rule_that_could_never_send_is_refused_with_the_reason():
    """
    **Feature: notification routing rules API (ORG-F08)**
    **Property: each of these is a 400 whose text says what is wrong: no pattern; a
    pattern matching no run event; an unknown template; a template that does not
    describe the pattern's event; an unknown or malformed channel; no or too many
    recipients; an unknown project; a tag filter (not supported yet); a bad rate limit.**
    """
    factory, session, channel = _world()
    try:
        cases = {
            "no pattern": ({"event_pattern": ""}, "event_pattern is required"),
            "matches nothing": ({"event_pattern": "entity.user.created"}, "matches none of the events that can be notified"),
            "unknown template": ({"template_name": "nope"}, "No notification template is named 'nope'"),
            "template for another event": ({"template_name": "run_succeeded"}, "would never send"),
            "unknown channel": ({"channel_ids": [str(uuid.uuid4())]}, "No notification channel has the id"),
            "channel not an id": ({"channel_ids": ["smtp"]}, "not a channel id"),
            "no recipients": ({"recipients": []}, "recipients must list between 1 and"),
            "too many recipients": ({"recipients": ["a@x.test"] * 21}, "recipients must list between 1 and"),
            "blank recipient": ({"recipients": [" "]}, "not an address"),
            "unknown project": ({"project_id": str(uuid.uuid4())}, "No project has the id"),
            "tag filter": ({"filter_tag_expression": "env:prod"}, "filter_tag_expression is not supported yet"),
            "bad rate limit": ({"rate_limit_per_minute": 0}, "rate_limit_per_minute must be"),
        }
        outcomes: Dict[str, Tuple[int, bool]] = {}
        for name, (changes, phrase) in cases.items():
            response = routes.handle_create_routing_rule(_Request(session=session, body=_valid(channel, **changes)))
            outcomes[name] = (response.status_code, phrase in _body(response)["detail"])
        stored = _body(routes.handle_list_routing_rules(_Request(session=session)))
    finally:
        _done(session)

    testbase.assert_equal((outcomes, stored), ({name: (400, True) for name in cases}, []))
    return


def test_a_body_that_is_not_an_object_and_unknown_ids_are_answered_plainly():
    """
    **Feature: notification routing rules API (ORG-F08)**
    **Property: a body that is not a JSON object is a 400; PATCH with a body other than
    {"disabled": boolean} is a 400; PATCH or DELETE of an id that is not a rule (or not
    an id at all) is a 404; a project_id filter that is not an id is a 400.**
    """
    factory, session, channel = _world()
    try:
        not_object = routes.handle_create_routing_rule(_Request(session=session, body=["x"]))
        missing = uuid.uuid4().hex
        bad_patch = routes.handle_update_routing_rule(_Request(session=session, body={"disabled": "yes"}, path_params={"rule_id": missing}))
        extra_patch = routes.handle_update_routing_rule(_Request(session=session, body={"disabled": True, "recipients": []}, path_params={"rule_id": missing}))
        patch_404 = routes.handle_update_routing_rule(_Request(session=session, body={"disabled": True}, path_params={"rule_id": str(uuid.uuid4())}))
        delete_404 = routes.handle_delete_routing_rule(_Request(session=session, path_params={"rule_id": str(uuid.uuid4())}))
        delete_junk = routes.handle_delete_routing_rule(_Request(session=session, path_params={"rule_id": "junk"}))
        bad_filter = routes.handle_list_routing_rules(_Request(session=session, query={"project_id": "junk"}))
    finally:
        _done(session)

    testbase.assert_equal(
        [response.status_code for response in (not_object, bad_patch, extra_patch, patch_404, delete_404, delete_junk, bad_filter)],
        [400, 400, 400, 404, 404, 404, 400],
    )
    return


def test_the_four_routes_are_registered_under_the_notifications_path():
    """
    **Feature: notification routing rules API (ORG-F08)**
    **Property: registering attaches GET and POST on the collection and PATCH and DELETE
    on ``{rule_id}``, under the versioned notifications path.**
    """
    attached: List[Tuple[str, Tuple[str, ...]]] = []

    class _App:
        def attach_route(self, path: str, methods: List[str]) -> Any:
            attached.append((path, tuple(methods)))
            return lambda handler: handler

    routes.register_routing_rules_routes(app=_App(), version_prefix="/api/v1")

    testbase.assert_equal(
        attached,
        [
            ("/api/v1/notifications/routing-rules", ("GET",)),
            ("/api/v1/notifications/routing-rules", ("POST",)),
            ("/api/v1/notifications/routing-rules/{rule_id}", ("PATCH",)),
            ("/api/v1/notifications/routing-rules/{rule_id}", ("DELETE",)),
        ],
    )
    return


def test_a_rule_made_through_the_api_sends_a_message_when_a_run_fails():
    """
    **Feature: notification routing rules API (ORG-F08)**
    **Property: after creating a rule through the API, a published run failure in the
    rule's project is delivered by the notifier to the rule's recipient; a disabled rule
    sends nothing.**
    """
    factory, session, channel = _world()
    try:
        rule = _body(routes.handle_create_routing_rule(_Request(session=session, body=_valid(channel, project_id=PROJECT))))
        notifier = run_notifier.wire_run_notifications(session_factory=factory)
        run_id = str(uuid.uuid4())
        event = event_bus.EntityEvent(topic=RunStateEventTopics.FAILED, payload={"run_id": run_id, "project_id": PROJECT, "to_state": "failed", "reason": "boom"}, source_event_id="e-1")
        event_bus.publish(event=event)
        notifier.wait_until_idle()
        delivered = list(_RecordingChannel.sent)

        routes.handle_update_routing_rule(_Request(session=session, body={"disabled": True}, path_params={"rule_id": rule["rule_id"]}))
        event_bus.publish(event=event)
        notifier.wait_until_idle()
        after_disable = list(_RecordingChannel.sent)
    finally:
        _done(session)

    testbase.assert_equal(
        ([(recipient, subject) for recipient, subject, _b in delivered], len(after_disable)),
        ([("oncall@example.test", "[Pychestrate] Run {} failed in alpha".format(run_id))], 1),
    )
    return
