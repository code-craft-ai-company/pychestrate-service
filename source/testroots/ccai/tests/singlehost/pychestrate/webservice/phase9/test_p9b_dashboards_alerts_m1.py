"""
.. module:: test_p9b_dashboards_alerts_m1
    :synopsis: Tests for P9b — 7-project-dashboards + 7-alerts-budgets M1.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.metrics.alerts import (
    AlertEventTopics,
    AlertRuleConfigInvalidError,
    AlertRuleConflictError,
    AlertRuleKindUnknownError,
    AlertRuleNotFoundError,
    AlertSeverity,
    AlertState,
    create_alert_rule,
    disable_alert_rule,
    evaluate_alert_rule,
    get_alert_rule,
    get_live_state,
    list_alert_kinds,
    list_alert_rules_for_project,
    register_builtin_extensions as alerts_register,
)
from ccai.pychestrate.webservice.metrics.dashboards import (
    DashboardConflictError,
    DashboardEventTopics,
    DashboardNotFoundError,
    TileConfigInvalidError,
    TileInstance,
    TileKindUnknownError,
    create_dashboard,
    delete_dashboard,
    get_dashboard,
    list_dashboards_for_project,
    list_tile_kinds,
    register_builtin_extensions as dashboards_register,
    update_dashboard_tiles,
)
from ccai.pychestrate.webservice.metrics.ingest import (
    register_builtin_extensions as metrics_ingest_register,
)
from ccai.pychestrate.webservice.metrics.timeseries import (
    MetricDefinition,
    MetricKind,
    register_builtin_extensions as timeseries_register,
    register_definition,
    reset_for_testing,
    write_counter,
    write_gauge,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000080001"
ACTOR_UUID = "00000000-0000-4000-8000-000000080002"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_for_testing()
    timeseries_register()
    metrics_ingest_register()
    dashboards_register()
    alerts_register()
    return


def _seed_test_metric(*, session) -> str:
    """
        Helper: register a gauge metric the threshold rule can
        read against.
    """
    register_definition(
        db_session=session,
        definition=MetricDefinition(
            name="pychestrate_test_gauge_threshold",
            kind=MetricKind.GAUGE,
            label_names=("project_id",),
            help_text="test gauge for threshold tests",
        ),
    )
    rtnval = "pychestrate_test_gauge_threshold"
    return rtnval


# -------------------------------------
# 7-project-dashboards
# -------------------------------------

def test_list_tile_kinds_exposes_in_tree_pack():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: list_tile_kinds returns the in-tree
    line-chart + single-stat references in PRECEDENCE order.**
    """
    _prepare_runtime()
    records = list_tile_kinds()
    kinds = [r.kind for r in records]
    testbase.assert_equal("metric-line-chart" in kinds, True)
    testbase.assert_equal("metric-single-stat" in kinds, True)
    return


def test_create_dashboard_persists_and_emits():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: create_dashboard persists the row, emits
    entity.dashboard.created, validates each tile against its
    kind.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=DashboardEventTopics.CREATED,
        subscriber=lambda e: received.append(e),
    )
    tile = TileInstance(
        tile_id="t1", kind="metric-line-chart",
        x=0, y=0, w=6, h=3,
        config={"metric_name": "m1", "label_filter": {}, "range_seconds": 60},
    )
    view = create_dashboard(
        db_session=session, project_id=PROJECT_UUID,
        name="ops", tiles=[tile],
        owner_principal_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.name, "ops")
    testbase.assert_equal(len(view.tiles), 1)
    testbase.assert_equal(view.tiles[0].kind, "metric-line-chart")
    testbase.assert_equal(len(received), 1)
    return


def test_create_dashboard_duplicate_name_raises():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: a second dashboard with the same (project,
    name) raises DashboardConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    create_dashboard(
        db_session=session, project_id=PROJECT_UUID, name="dup",
    )
    raised = False
    try:
        create_dashboard(
            db_session=session, project_id=PROJECT_UUID, name="dup",
        )
    except DashboardConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_create_dashboard_unknown_tile_kind_raises():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: a tile referencing an unregistered kind raises
    TileKindUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        create_dashboard(
            db_session=session, project_id=PROJECT_UUID, name="bad",
            tiles=[
                TileInstance(
                    tile_id="x", kind="unknown-kind",
                    x=0, y=0, w=2, h=2, config={},
                )
            ],
        )
    except TileKindUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_create_dashboard_invalid_tile_config_raises():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: a tile whose config fails the kind's validation
    raises TileConfigInvalidError listing every issue.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        create_dashboard(
            db_session=session, project_id=PROJECT_UUID, name="bad-tile",
            tiles=[
                TileInstance(
                    tile_id="x", kind="metric-line-chart",
                    x=0, y=0, w=4, h=2,
                    # missing metric_name
                    config={"label_filter": {}},
                )
            ],
        )
    except TileConfigInvalidError as xcpt:
        raised = True
        testbase.assert_equal("metric_name" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_update_dashboard_tiles_emits_and_bumps_version():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: update_dashboard_tiles replaces the tile array,
    bumps version, emits UPDATED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=DashboardEventTopics.UPDATED,
        subscriber=lambda e: received.append(e),
    )
    view = create_dashboard(
        db_session=session, project_id=PROJECT_UUID, name="ops",
    )
    new_tile = TileInstance(
        tile_id="t1", kind="metric-single-stat",
        x=0, y=0, w=2, h=2,
        config={"metric_name": "m1"},
    )
    updated = update_dashboard_tiles(
        db_session=session, dashboard_id=view.dashboard_id,
        tiles=[new_tile],
    )
    testbase.assert_equal(updated.version, view.version + 1)
    testbase.assert_equal(len(updated.tiles), 1)
    testbase.assert_equal(len(received), 1)
    return


def test_update_dashboard_optimistic_concurrency_mismatch_raises():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: update_dashboard_tiles with a mismatched
    expected_version raises DashboardConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = create_dashboard(
        db_session=session, project_id=PROJECT_UUID, name="ops",
    )
    raised = False
    try:
        update_dashboard_tiles(
            db_session=session, dashboard_id=view.dashboard_id,
            tiles=[], expected_version=999,
        )
    except DashboardConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_get_dashboard_unknown_raises():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: get_dashboard on an unknown id raises
    DashboardNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_dashboard(db_session=session, dashboard_id=new_uuid())
    except DashboardNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_dashboards_scopes_to_project():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: list_dashboards_for_project returns rows for
    the requested project only.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    other = new_uuid()
    create_dashboard(
        db_session=session, project_id=PROJECT_UUID, name="a",
    )
    create_dashboard(
        db_session=session, project_id=PROJECT_UUID, name="b",
    )
    create_dashboard(
        db_session=session, project_id=other, name="c",
    )
    rows = list_dashboards_for_project(
        db_session=session, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(len(rows), 2)
    return


def test_delete_dashboard_emits_and_idempotent():
    """
    **Feature: 7-project-dashboards (M1)**
    **Property: delete_dashboard emits entity.dashboard.deleted
    on first call; second call is a no-op (returns False).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=DashboardEventTopics.DELETED,
        subscriber=lambda e: received.append(e),
    )
    view = create_dashboard(
        db_session=session, project_id=PROJECT_UUID, name="ops",
    )
    deleted_first = delete_dashboard(
        db_session=session, dashboard_id=view.dashboard_id,
    )
    deleted_second = delete_dashboard(
        db_session=session, dashboard_id=view.dashboard_id,
    )
    testbase.assert_equal(deleted_first, True)
    testbase.assert_equal(deleted_second, False)
    testbase.assert_equal(len(received), 1)
    return


# -------------------------------------
# 7-alerts-budgets
# -------------------------------------

def test_list_alert_kinds_exposes_threshold_reference():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: list_alert_kinds returns the in-tree threshold
    reference.**
    """
    _prepare_runtime()
    records = list_alert_kinds()
    kinds = [r.kind for r in records]
    testbase.assert_equal("threshold" in kinds, True)
    return


def test_create_alert_rule_persists_and_emits():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: create_alert_rule persists + emits
    entity.alert.rule_created; default state is UNKNOWN.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AlertEventTopics.RULE_CREATED,
        subscriber=lambda e: received.append(e),
    )
    metric = _seed_test_metric(session=session)
    view = create_alert_rule(
        db_session=session, project_id=PROJECT_UUID,
        name="hi-cpu", kind="threshold",
        config={
            "metric_name": metric, "threshold": 80, "op": ">=",
            "label_filter": {"project_id": PROJECT_UUID},
        },
        severity=AlertSeverity.CRITICAL,
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.name, "hi-cpu")
    testbase.assert_equal(view.severity, AlertSeverity.CRITICAL)
    testbase.assert_equal(len(received), 1)

    live = get_live_state(db_session=session, rule_id=view.rule_id)
    testbase.assert_equal(live.state, AlertState.UNKNOWN)
    return


def test_create_alert_rule_invalid_config_raises():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: a config that fails the kind's validation
    raises AlertRuleConfigInvalidError listing the offenders.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        create_alert_rule(
            db_session=session, project_id=PROJECT_UUID,
            name="bad", kind="threshold",
            config={"metric_name": "", "threshold": "x", "op": "??"},
        )
    except AlertRuleConfigInvalidError as xcpt:
        raised = True
        msg = str(xcpt)
        testbase.assert_equal("metric_name" in msg, True)
        testbase.assert_equal("threshold" in msg, True)
        testbase.assert_equal("op" in msg, True)
    testbase.assert_equal(raised, True)
    return


def test_create_alert_rule_unknown_kind_raises():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: an unknown rule kind raises
    AlertRuleKindUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        create_alert_rule(
            db_session=session, project_id=PROJECT_UUID,
            name="bad", kind="unknown-kind", config={},
        )
    except AlertRuleKindUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_create_alert_rule_duplicate_name_raises():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: duplicate (project, name) raises
    AlertRuleConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    metric = _seed_test_metric(session=session)
    config = {
        "metric_name": metric, "threshold": 1, "op": ">",
        "label_filter": {},
    }
    create_alert_rule(
        db_session=session, project_id=PROJECT_UUID,
        name="dup", kind="threshold", config=config,
    )
    raised = False
    try:
        create_alert_rule(
            db_session=session, project_id=PROJECT_UUID,
            name="dup", kind="threshold", config=config,
        )
    except AlertRuleConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_evaluate_threshold_rule_with_no_sample_returns_ok():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: evaluating a threshold rule before any sample
    has been written returns state=OK with a
    no-sample-yet reason and emits EVALUATED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AlertEventTopics.EVALUATED,
        subscriber=lambda e: received.append(e),
    )
    metric = _seed_test_metric(session=session)
    rule = create_alert_rule(
        db_session=session, project_id=PROJECT_UUID,
        name="cpu", kind="threshold",
        config={
            "metric_name": metric, "threshold": 80, "op": ">",
            "label_filter": {"project_id": PROJECT_UUID},
        },
    )
    result = evaluate_alert_rule(
        db_session=session, rule_id=rule.rule_id,
    )
    testbase.assert_equal(result.state, AlertState.OK)
    testbase.assert_equal("no sample" in result.reason, True)
    testbase.assert_equal(len(received), 1)
    return


def test_evaluate_threshold_rule_fires_then_resolves():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: when the latest sample crosses threshold the
    rule transitions to FIRING + emits FIRED + STATE_CHANGED.
    A subsequent below-threshold sample transitions back to OK
    + emits RESOLVED + STATE_CHANGED. The fire / resolve
    counters increment.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_fired: List[EntityEvent] = []
    received_resolved: List[EntityEvent] = []
    received_state: List[EntityEvent] = []
    subscribe(
        topic=AlertEventTopics.FIRED,
        subscriber=lambda e: received_fired.append(e),
    )
    subscribe(
        topic=AlertEventTopics.RESOLVED,
        subscriber=lambda e: received_resolved.append(e),
    )
    subscribe(
        topic=AlertEventTopics.STATE_CHANGED,
        subscriber=lambda e: received_state.append(e),
    )
    metric = _seed_test_metric(session=session)
    rule = create_alert_rule(
        db_session=session, project_id=PROJECT_UUID,
        name="cpu", kind="threshold",
        config={
            "metric_name": metric, "threshold": 80, "op": ">",
            "label_filter": {"project_id": PROJECT_UUID},
        },
    )

    # Below threshold — OK
    write_gauge(
        db_session=session, name=metric,
        value=50.0, labels={"project_id": PROJECT_UUID},
    )
    first = evaluate_alert_rule(
        db_session=session, rule_id=rule.rule_id,
    )
    testbase.assert_equal(first.state, AlertState.OK)

    # Above threshold — FIRING + transition fires
    write_gauge(
        db_session=session, name=metric,
        value=95.0, labels={"project_id": PROJECT_UUID},
    )
    fired = evaluate_alert_rule(
        db_session=session, rule_id=rule.rule_id,
    )
    testbase.assert_equal(fired.state, AlertState.FIRING)
    testbase.assert_equal(fired.state_changed, True)
    testbase.assert_equal(fired.observed_value, 95.0)

    # Stays firing — no second FIRED emit
    write_gauge(
        db_session=session, name=metric,
        value=99.0, labels={"project_id": PROJECT_UUID},
    )
    still_firing = evaluate_alert_rule(
        db_session=session, rule_id=rule.rule_id,
    )
    testbase.assert_equal(still_firing.state, AlertState.FIRING)
    testbase.assert_equal(still_firing.state_changed, False)

    # Back below — RESOLVED + transition fires
    write_gauge(
        db_session=session, name=metric,
        value=10.0, labels={"project_id": PROJECT_UUID},
    )
    resolved = evaluate_alert_rule(
        db_session=session, rule_id=rule.rule_id,
    )
    testbase.assert_equal(resolved.state, AlertState.OK)
    testbase.assert_equal(resolved.state_changed, True)

    testbase.assert_equal(len(received_fired), 1)
    testbase.assert_equal(len(received_resolved), 1)
    testbase.assert_equal(len(received_state), 2)

    live = get_live_state(db_session=session, rule_id=rule.rule_id)
    testbase.assert_equal(live.state, AlertState.OK)
    testbase.assert_equal(live.fire_count, 1)
    testbase.assert_equal(live.resolve_count, 1)
    return


def test_evaluate_alert_rule_unknown_raises():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: evaluate_alert_rule on an unknown rule raises
    AlertRuleNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        evaluate_alert_rule(
            db_session=session, rule_id=new_uuid(),
        )
    except AlertRuleNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_disable_alert_rule_idempotent_and_emits():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: disable_alert_rule flips enabled=False,
    emits RULE_DISABLED, and a second call is idempotent.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AlertEventTopics.RULE_DISABLED,
        subscriber=lambda e: received.append(e),
    )
    metric = _seed_test_metric(session=session)
    rule = create_alert_rule(
        db_session=session, project_id=PROJECT_UUID,
        name="cpu", kind="threshold",
        config={
            "metric_name": metric, "threshold": 1, "op": ">",
            "label_filter": {},
        },
    )
    disable_alert_rule(
        db_session=session, rule_id=rule.rule_id,
        actor_id=ACTOR_UUID,
    )
    disable_alert_rule(
        db_session=session, rule_id=rule.rule_id,
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(len(received), 1)

    listed = list_alert_rules_for_project(
        db_session=session, project_id=PROJECT_UUID, enabled_only=True,
    )
    testbase.assert_equal(len(listed), 0)

    listed_all = list_alert_rules_for_project(
        db_session=session, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(len(listed_all), 1)
    return


def test_get_alert_rule_unknown_raises():
    """
    **Feature: 7-alerts-budgets (M1)**
    **Property: get_alert_rule on an unknown id raises
    AlertRuleNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_alert_rule(db_session=session, rule_id=new_uuid())
    except AlertRuleNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
