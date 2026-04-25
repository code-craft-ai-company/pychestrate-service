"""
.. module:: test_p9c_slo_views_m1
    :synopsis: Tests for P9c — 7-slo-views M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.metrics.slos import (
    SLOConfigInvalidError,
    SLOConflictError,
    SLOEventTopics,
    SLOKindUnknownError,
    SLONotFoundError,
    compute_status,
    create_slo,
    delete_slo,
    get_slo,
    list_slo_kinds,
    list_slos_for_project,
    register_builtin_extensions as slos_register,
)
from automojo.pychestrate.webservice.metrics.timeseries import (
    MetricDefinition,
    MetricKind,
    register_builtin_extensions as timeseries_register,
    register_definition,
    reset_for_testing,
    write_counter,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000090001"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_for_testing()
    timeseries_register()
    slos_register()
    return


def _seed_metrics(*, session) -> None:
    register_definition(
        db_session=session,
        definition=MetricDefinition(
            name="pychestrate_runs_succeeded_total",
            kind=MetricKind.COUNTER,
            label_names=("project_id",),
            help_text="successful runs",
        ),
    )
    register_definition(
        db_session=session,
        definition=MetricDefinition(
            name="pychestrate_runs_total",
            kind=MetricKind.COUNTER,
            label_names=("project_id",),
            help_text="total runs",
        ),
    )
    return


def _valid_config() -> dict:
    rtnval = {
        "good_metric_name": "pychestrate_runs_succeeded_total",
        "total_metric_name": "pychestrate_runs_total",
        "label_filter": {"project_id": PROJECT_UUID},
    }
    return rtnval


# -------------------------------------
# create_slo
# -------------------------------------

def test_list_slo_kinds_exposes_availability_ratio_reference():
    """
    **Feature: 7-slo-views (M1)**
    **Property: list_slo_kinds returns the in-tree
    availability_ratio reference.**
    """
    _prepare_runtime()
    records = list_slo_kinds()
    kinds = [r.kind for r in records]
    testbase.assert_equal("availability_ratio" in kinds, True)
    return


def test_create_slo_persists_and_emits():
    """
    **Feature: 7-slo-views (M1)**
    **Property: create_slo persists the row + emits CREATED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=SLOEventTopics.CREATED,
        subscriber=lambda e: received.append(e),
    )
    view = create_slo(
        db_session=session, project_id=PROJECT_UUID,
        name="run-success", kind="availability_ratio",
        target=0.99, window_seconds=86400,
        definition_config=_valid_config(),
    )
    testbase.assert_equal(view.target, 0.99)
    testbase.assert_equal(view.window_seconds, 86400)
    testbase.assert_equal(view.kind, "availability_ratio")
    testbase.assert_equal(len(received), 1)
    return


def test_create_slo_invalid_target_raises():
    """
    **Feature: 7-slo-views (M1)**
    **Property: target outside [0.0, 1.0] raises
    SLOConfigInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised_high = False
    try:
        create_slo(
            db_session=session, project_id=PROJECT_UUID,
            name="bad-high", kind="availability_ratio",
            target=1.5, window_seconds=60,
            definition_config=_valid_config(),
        )
    except SLOConfigInvalidError:
        raised_high = True
    testbase.assert_equal(raised_high, True)

    raised_low = False
    try:
        create_slo(
            db_session=session, project_id=PROJECT_UUID,
            name="bad-low", kind="availability_ratio",
            target=-0.1, window_seconds=60,
            definition_config=_valid_config(),
        )
    except SLOConfigInvalidError:
        raised_low = True
    testbase.assert_equal(raised_low, True)
    return


def test_create_slo_invalid_window_raises():
    """
    **Feature: 7-slo-views (M1)**
    **Property: non-positive window_seconds raises
    SLOConfigInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        create_slo(
            db_session=session, project_id=PROJECT_UUID,
            name="bad-window", kind="availability_ratio",
            target=0.99, window_seconds=0,
            definition_config=_valid_config(),
        )
    except SLOConfigInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_create_slo_unknown_kind_raises():
    """
    **Feature: 7-slo-views (M1)**
    **Property: unknown kind raises SLOKindUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        create_slo(
            db_session=session, project_id=PROJECT_UUID,
            name="bad", kind="not-a-kind", target=0.99,
            window_seconds=60, definition_config={},
        )
    except SLOKindUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_create_slo_invalid_config_raises():
    """
    **Feature: 7-slo-views (M1)**
    **Property: a config that fails the kind's validation
    raises SLOConfigInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        create_slo(
            db_session=session, project_id=PROJECT_UUID,
            name="bad-config", kind="availability_ratio",
            target=0.99, window_seconds=60,
            definition_config={"label_filter": {}},
        )
    except SLOConfigInvalidError as xcpt:
        raised = True
        msg = str(xcpt)
        testbase.assert_equal("good_metric_name" in msg, True)
        testbase.assert_equal("total_metric_name" in msg, True)
    testbase.assert_equal(raised, True)
    return


def test_create_slo_duplicate_name_raises():
    """
    **Feature: 7-slo-views (M1)**
    **Property: duplicate (project, name) raises
    SLOConflictError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    create_slo(
        db_session=session, project_id=PROJECT_UUID,
        name="dup", kind="availability_ratio",
        target=0.99, window_seconds=60,
        definition_config=_valid_config(),
    )
    raised = False
    try:
        create_slo(
            db_session=session, project_id=PROJECT_UUID,
            name="dup", kind="availability_ratio",
            target=0.99, window_seconds=60,
            definition_config=_valid_config(),
        )
    except SLOConflictError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# read helpers
# -------------------------------------

def test_get_slo_unknown_raises():
    """
    **Feature: 7-slo-views (M1)**
    **Property: get_slo on an unknown id raises
    SLONotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_slo(db_session=session, slo_id=new_uuid())
    except SLONotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_slos_scopes_to_project():
    """
    **Feature: 7-slo-views (M1)**
    **Property: list_slos_for_project returns rows for the
    requested project only.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    other = new_uuid()
    create_slo(
        db_session=session, project_id=PROJECT_UUID,
        name="a", kind="availability_ratio",
        target=0.99, window_seconds=60,
        definition_config=_valid_config(),
    )
    create_slo(
        db_session=session, project_id=PROJECT_UUID,
        name="b", kind="availability_ratio",
        target=0.99, window_seconds=60,
        definition_config=_valid_config(),
    )
    create_slo(
        db_session=session, project_id=other,
        name="c", kind="availability_ratio",
        target=0.99, window_seconds=60,
        definition_config=_valid_config(),
    )
    rows = list_slos_for_project(
        db_session=session, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(len(rows), 2)
    return


def test_delete_slo_emits_and_idempotent():
    """
    **Feature: 7-slo-views (M1)**
    **Property: delete_slo emits DELETED on first call;
    second call returns False.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=SLOEventTopics.DELETED,
        subscriber=lambda e: received.append(e),
    )
    view = create_slo(
        db_session=session, project_id=PROJECT_UUID,
        name="goer", kind="availability_ratio",
        target=0.99, window_seconds=60,
        definition_config=_valid_config(),
    )
    first = delete_slo(db_session=session, slo_id=view.slo_id)
    second = delete_slo(db_session=session, slo_id=view.slo_id)
    testbase.assert_equal(first, True)
    testbase.assert_equal(second, False)
    testbase.assert_equal(len(received), 1)
    return


# -------------------------------------
# compute_status
# -------------------------------------

def test_compute_status_no_observations_returns_none():
    """
    **Feature: 7-slo-views (M1)**
    **Property: compute_status with no samples in the window
    returns achieved_ratio=None and breaching=False; emits
    STATUS_COMPUTED but not BUDGET_DEPLETED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_status: List[EntityEvent] = []
    received_depleted: List[EntityEvent] = []
    subscribe(
        topic=SLOEventTopics.STATUS_COMPUTED,
        subscriber=lambda e: received_status.append(e),
    )
    subscribe(
        topic=SLOEventTopics.BUDGET_DEPLETED,
        subscriber=lambda e: received_depleted.append(e),
    )
    _seed_metrics(session=session)
    view = create_slo(
        db_session=session, project_id=PROJECT_UUID,
        name="empty", kind="availability_ratio",
        target=0.99, window_seconds=86400,
        definition_config=_valid_config(),
    )
    status = compute_status(db_session=session, slo_id=view.slo_id)
    testbase.assert_equal(status.achieved_ratio is None, True)
    testbase.assert_equal(status.breaching, False)
    testbase.assert_equal(len(received_status), 1)
    testbase.assert_equal(len(received_depleted), 0)
    return


def test_compute_status_above_target_does_not_emit_depleted():
    """
    **Feature: 7-slo-views (M1)**
    **Property: when achieved_ratio >= target, breaching is
    False, error_budget_remaining_ratio is in [0, 1], and
    BUDGET_DEPLETED does not fire.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_depleted: List[EntityEvent] = []
    subscribe(
        topic=SLOEventTopics.BUDGET_DEPLETED,
        subscriber=lambda e: received_depleted.append(e),
    )
    _seed_metrics(session=session)
    view = create_slo(
        db_session=session, project_id=PROJECT_UUID,
        name="happy", kind="availability_ratio",
        target=0.9, window_seconds=86400,
        definition_config=_valid_config(),
    )
    # 99 successes + 100 totals = 0.99 ratio, target=0.9 → above
    for index in range(99):
        write_counter(
            db_session=session,
            name="pychestrate_runs_succeeded_total",
            delta=1.0, labels={"project_id": PROJECT_UUID},
        )
    for index in range(100):
        write_counter(
            db_session=session,
            name="pychestrate_runs_total",
            delta=1.0, labels={"project_id": PROJECT_UUID},
        )

    status = compute_status(db_session=session, slo_id=view.slo_id)
    testbase.assert_equal(status.achieved_ratio is not None, True)
    testbase.assert_equal(status.achieved_ratio > 0.9, True)
    testbase.assert_equal(status.breaching, False)
    testbase.assert_equal(status.good_count, 99)
    testbase.assert_equal(status.total_count, 100)
    testbase.assert_equal(
        status.error_budget_remaining_ratio is not None, True,
    )
    testbase.assert_equal(
        0.0 <= status.error_budget_remaining_ratio <= 1.0, True,
    )
    testbase.assert_equal(len(received_depleted), 0)
    return


def test_compute_status_below_target_emits_budget_depleted():
    """
    **Feature: 7-slo-views (M1)**
    **Property: when achieved_ratio < target, breaching is
    True, error_budget_remaining_ratio is 0.0, and
    BUDGET_DEPLETED fires.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_depleted: List[EntityEvent] = []
    subscribe(
        topic=SLOEventTopics.BUDGET_DEPLETED,
        subscriber=lambda e: received_depleted.append(e),
    )
    _seed_metrics(session=session)
    view = create_slo(
        db_session=session, project_id=PROJECT_UUID,
        name="bad", kind="availability_ratio",
        target=0.99, window_seconds=86400,
        definition_config=_valid_config(),
    )
    # 8/10 success rate — well below 0.99 target
    for index in range(8):
        write_counter(
            db_session=session,
            name="pychestrate_runs_succeeded_total",
            delta=1.0, labels={"project_id": PROJECT_UUID},
        )
    for index in range(10):
        write_counter(
            db_session=session,
            name="pychestrate_runs_total",
            delta=1.0, labels={"project_id": PROJECT_UUID},
        )
    status = compute_status(db_session=session, slo_id=view.slo_id)
    testbase.assert_equal(status.breaching, True)
    testbase.assert_equal(status.error_budget_remaining_ratio, 0.0)
    testbase.assert_equal(len(received_depleted), 1)
    return


def test_compute_status_unknown_slo_raises():
    """
    **Feature: 7-slo-views (M1)**
    **Property: compute_status on an unknown id raises
    SLONotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        compute_status(db_session=session, slo_id=new_uuid())
    except SLONotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
