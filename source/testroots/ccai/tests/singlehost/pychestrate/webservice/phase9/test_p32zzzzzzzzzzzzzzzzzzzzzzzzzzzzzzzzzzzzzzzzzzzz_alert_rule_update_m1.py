"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_alert_rule_update_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: An alert rule can be changed and deleted (ORC-26): service rules, events and the PUT and DELETE routes.

.. moduleauthor:: Code Craft AI LLC

An alert rule could be created and disabled but not changed: a mistyped threshold meant creating a second rule and leaving the first one
disabled for ever. ``update_alert_rule`` changes the fields it is given under the rules of create (a non-empty name unique in the project, a config the
rule's kind accepts), keeps the kind and the project, writes nothing when nothing differs and otherwise says what changed;
``delete_alert_rule`` removes a rule and its live state. ``PUT`` and ``DELETE`` on ``.../metric-alerts/{rule_id}`` are their REST face.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import Any, Dict, List

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.metrics.alerts import (
    AlertEventTopics,
    AlertRuleConfigInvalidError,
    AlertRuleConflictError,
    AlertRuleNotFoundError,
    AlertSeverity,
    AlertState,
    create_alert_rule,
    delete_alert_rule,
    get_alert_rule,
    get_live_state,
    list_alert_rules_for_project,
    register_builtin_extensions as alerts_register,
    update_alert_rule,
)
from ccai.pychestrate.webservice.metrics.alerts import repository as alerts_repository
from ccai.pychestrate.webservice.metrics.restapi.v1 import metric_alerts_routes
from ccai.pychestrate.webservice.metrics.timeseries import (
    register_builtin_extensions as timeseries_register,
    reset_for_testing,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session
from ccai.tests.singlehost.pychestrate.webservice.phase10.test_p20f_metric_alerts_routes_m1 import (
    _FakePrincipal,
    _FakeProject,
    _FakeRequest,
    _decode_body,
    _patch_check_permission,
    _patch_project_exists,
)


PROJECT = "00000000-0000-4000-8000-000000090001"
OTHER_PROJECT = "00000000-0000-4000-8000-000000090002"


def _prepare() -> Any:
    reset_registry_for_testing()
    reset_event_bus()
    reset_for_testing()
    timeseries_register()
    alerts_register()
    _engine, session = build_in_memory_session()
    return session


def _config(threshold: float = 5.0) -> Dict[str, Any]:
    return {"metric_name": "pychestrate_test_runs_total", "threshold": threshold, "op": ">"}


def _create(session: Any, *, name: str = "failure spike", project: str = PROJECT, threshold: float = 5.0) -> Any:
    return create_alert_rule(
        db_session=session, project_id=project, name=name, kind="threshold", config=_config(threshold),
        description="runs that fail", severity=AlertSeverity.WARNING, enabled=True, notification_targets=["ops"],
    )


def test_update_changes_only_what_it_is_given_and_names_what_changed():
    """
    **Feature: alert rule edit (ORC-26)**
    **Property: updating the threshold and the severity changes those fields on the same rule (same id, kind, project, name, targets),
    stamps updated_at and publishes entity.alert.rule_updated naming exactly the changed fields.**
    """
    session = _prepare()
    created = _create(session)
    events: List[EntityEvent] = []
    subscribe(topic=AlertEventTopics.RULE_UPDATED, subscriber=lambda event: events.append(event))

    after = update_alert_rule(db_session=session, rule_id=created.rule_id, config=_config(9.0), severity=AlertSeverity.CRITICAL, actor_id="user-1")
    stored = get_alert_rule(db_session=session, rule_id=created.rule_id)

    testbase.assert_equal(
        (
            stored.rule_id == created.rule_id, stored.kind, stored.project_id, stored.name, stored.description, stored.config["threshold"],
            stored.severity, stored.enabled, stored.notification_targets, stored.updated_at >= created.updated_at, after.config["threshold"],
            len(events), sorted(events[0].payload["changed"]), events[0].payload["actor_id"],
        ),
        (
            True, "threshold", PROJECT, "failure spike", "runs that fail", 9.0, AlertSeverity.CRITICAL, True, ("ops",), True, 9.0,
            1, ["config", "severity"], "user-1",
        ),
    )
    return


def test_update_that_changes_nothing_writes_nothing_and_says_nothing():
    """
    **Feature: alert rule edit (ORC-26)**
    **Property: saving a rule exactly as it is, or with no field at all, leaves updated_at where it was and publishes no event.**
    """
    session = _prepare()
    created = _create(session)
    events: List[EntityEvent] = []
    subscribe(topic=AlertEventTopics.RULE_UPDATED, subscriber=lambda event: events.append(event))

    same = update_alert_rule(
        db_session=session, rule_id=created.rule_id, name=created.name, description=created.description, config=_config(),
        severity=AlertSeverity.WARNING, enabled=True, notification_targets=["ops"],
    )
    empty = update_alert_rule(db_session=session, rule_id=created.rule_id)

    testbase.assert_equal((same.updated_at, empty.updated_at, len(events)), (created.updated_at, created.updated_at, 0))
    return


def test_the_rules_of_create_apply_and_a_failed_update_changes_nothing():
    """
    **Feature: alert rule edit (ORC-26)**
    **Property: an empty name or a config the kind refuses is a config error, a name another rule in the project has is a conflict (its
    own name is not), an unknown rule is not found; after each refusal the rule is as it was; another project may reuse the name.**
    """
    session = _prepare()
    first = _create(session, name="first")
    second = _create(session, name="second")
    _create(session, name="first", project=OTHER_PROJECT)
    refusals: List[str] = []
    for label, call in (
        ("empty name", lambda: update_alert_rule(db_session=session, rule_id=first.rule_id, name="")),
        ("bad config", lambda: update_alert_rule(db_session=session, rule_id=first.rule_id, config={"metric_name": "x"})),
        ("clash", lambda: update_alert_rule(db_session=session, rule_id=second.rule_id, name="first")),
        ("unknown", lambda: update_alert_rule(db_session=session, rule_id="00000000-0000-4000-8000-0000000000ff", name="x")),
    ):
        try:
            call()
            refusals.append(label + ": allowed")
        except AlertRuleConfigInvalidError:
            refusals.append(label + ": invalid")
        except AlertRuleConflictError:
            refusals.append(label + ": conflict")
        except AlertRuleNotFoundError:
            refusals.append(label + ": not found")
    own_name = update_alert_rule(db_session=session, rule_id=first.rule_id, name="first", description="same name is fine")
    renamed = update_alert_rule(db_session=session, rule_id=second.rule_id, name="second renamed")
    names = sorted(rule.name for rule in list_alert_rules_for_project(db_session=session, project_id=PROJECT))

    testbase.assert_equal(
        (refusals, own_name.description, renamed.name, names, get_alert_rule(db_session=session, rule_id=first.rule_id).config["threshold"]),
        (
            ["empty name: invalid", "bad config: invalid", "clash: conflict", "unknown: not found"], "same name is fine", "second renamed",
            ["first", "second renamed"], 5.0,
        ),
    )
    return


def test_delete_removes_the_rule_and_its_live_state_and_nothing_else():
    """
    **Feature: alert rule delete (ORC-26)**
    **Property: deleting a rule removes it and its live state, publishes entity.alert.rule_deleted with its name, leaves the project's other
    rule alone, and a second delete (or an unknown id) is not found.**
    """
    session = _prepare()
    doomed = _create(session, name="doomed")
    kept = _create(session, name="kept")
    alerts_repository.upsert_live_state(
        db_session=session, rule_id=doomed.rule_id, new_state=AlertState.FIRING, last_value=7, last_threshold=5,
        last_reason="seven is over five", evaluated_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    session.commit()
    events: List[EntityEvent] = []
    subscribe(topic=AlertEventTopics.RULE_DELETED, subscriber=lambda event: events.append(event))

    delete_alert_rule(db_session=session, rule_id=doomed.rule_id, actor_id="user-1")
    remaining = [rule.name for rule in list_alert_rules_for_project(db_session=session, project_id=PROJECT)]
    state = alerts_repository.find_live_state(db_session=session, rule_id=doomed.rule_id)
    again = "deleted twice"
    try:
        delete_alert_rule(db_session=session, rule_id=doomed.rule_id)
    except AlertRuleNotFoundError:
        again = "not found"

    testbase.assert_equal(
        (remaining, state, again, len(events), events[0].payload["name"], events[0].payload["actor_id"], get_alert_rule(db_session=session, rule_id=kept.rule_id).name),
        (["kept"], None, "not found", 1, "doomed", "user-1", "kept"),
    )
    return


def _put(session: Any, rule_id: str, body: Dict[str, Any], *, project: str = PROJECT, allowed: bool = True) -> Any:
    permission = _patch_check_permission(allowed=allowed)
    exists = _patch_project_exists(project=_FakeProject(project_id=project))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/{}/metric-alerts/{}".format(project, rule_id), path_params={"project_id": project, "rule_id": rule_id},
            db_session=session, auth_principal=_FakePrincipal(), body=body,
        )
        return metric_alerts_routes.handle_update_metric_alert(request)
    finally:
        exists.deactivate()
        permission.deactivate()


def _delete(session: Any, rule_id: str, *, project: str = PROJECT, allowed: bool = True) -> Any:
    permission = _patch_check_permission(allowed=allowed)
    exists = _patch_project_exists(project=_FakeProject(project_id=project))
    try:
        request = _FakeRequest(
            path="/api/v1/projects/{}/metric-alerts/{}".format(project, rule_id), path_params={"project_id": project, "rule_id": rule_id},
            db_session=session, auth_principal=_FakePrincipal(),
        )
        return metric_alerts_routes.handle_delete_metric_alert(request)
    finally:
        exists.deactivate()
        permission.deactivate()


def test_put_changes_the_rule_and_refuses_what_create_refuses():
    """
    **Feature: alert rule edit (ORC-26)**
    **Property: PUT answers 200 with the rule after the change (a field left out keeps its value); the rule's own kind may be sent, another kind is
    422 saying to create a new rule; a name another rule has is 409; a config the kind refuses is 422; another project's rule is 404; a caller
    without the write permission gets 403 and nothing changes.**
    """
    session = _prepare()
    rule = _create(session)
    other = _create(session, name="taken")
    foreign = _create(session, name="foreign", project=OTHER_PROJECT)

    ok = _put(session, rule.rule_id, {"kind": "threshold", "config": _config(12.0), "enabled": False})
    wrong_kind = _put(session, rule.rule_id, {"kind": "rate"})
    clash = _put(session, rule.rule_id, {"name": other.name})
    bad = _put(session, rule.rule_id, {"config": {"metric_name": "x"}})
    wrong_project = _put(session, foreign.rule_id, {"name": "hijacked"})
    forbidden = _put(session, rule.rule_id, {"name": "nope"}, allowed=False)
    body = _decode_body(ok)
    stored = get_alert_rule(db_session=session, rule_id=rule.rule_id)

    testbase.assert_equal(
        (
            ok.status_code, body["name"], body["enabled"], body["config"]["threshold"], body["severity"],
            wrong_kind.status_code, "create a new rule" in _decode_body(wrong_kind)["detail"], clash.status_code, bad.status_code,
            wrong_project.status_code, get_alert_rule(db_session=session, rule_id=foreign.rule_id).name,
            forbidden.status_code, stored.name,
        ),
        (200, "failure spike", False, 12.0, "warning", 422, True, 409, 422, 404, "foreign", 403, "failure spike"),
    )
    return


def test_delete_answers_204_then_404_and_never_touches_another_projects_rule():
    """
    **Feature: alert rule delete (ORC-26)**
    **Property: DELETE answers 204 and the rule is gone (a second DELETE is 404); another project's rule is 404 and stays; a caller without the
    write permission gets 403 and the rule stays.**
    """
    session = _prepare()
    rule = _create(session, name="to delete")
    mine = _create(session, name="forbidden delete")
    foreign = _create(session, name="foreign", project=OTHER_PROJECT)

    forbidden = _delete(session, mine.rule_id, allowed=False)
    wrong_project = _delete(session, foreign.rule_id)
    gone = _delete(session, rule.rule_id)
    again = _delete(session, rule.rule_id)

    testbase.assert_equal(
        (
            forbidden.status_code, wrong_project.status_code, gone.status_code, again.status_code,
            sorted(item.name for item in list_alert_rules_for_project(db_session=session, project_id=PROJECT)),
            get_alert_rule(db_session=session, rule_id=foreign.rule_id).name,
        ),
        (403, 404, 204, 404, ["forbidden delete"], "foreign"),
    )
    return


def test_the_two_new_routes_are_registered():
    """
    **Feature: alert rule edit (ORC-26)**
    **Property: register_metric_alerts_routes also attaches PUT and DELETE on ``.../metric-alerts/{rule_id}``.**
    """
    class _App:
        def __init__(self) -> None:
            self.calls: List[Any] = []

        def attach_route(self, path: str, methods: Any = None) -> Any:
            def decorator(func: Any) -> Any:
                self.calls.append((path, tuple(methods or ["GET"])))
                return func
            return decorator

    app = _App()
    metric_alerts_routes.register_metric_alerts_routes(app=app, version_prefix="/api/v1")

    testbase.assert_equal(
        sorted(app.calls),
        sorted([
            ("/api/v1/projects/{project_id}/metric-alerts", ("GET",)),
            ("/api/v1/projects/{project_id}/metric-alerts", ("POST",)),
            ("/api/v1/projects/{project_id}/metric-alerts/{rule_id}", ("PUT",)),
            ("/api/v1/projects/{project_id}/metric-alerts/{rule_id}", ("DELETE",)),
        ]),
    )
    return
