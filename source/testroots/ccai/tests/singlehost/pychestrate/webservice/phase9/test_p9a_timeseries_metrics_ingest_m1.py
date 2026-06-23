"""
.. module:: test_p9a_timeseries_metrics_ingest_m1
    :synopsis: Tests for P9a — 0-timeseries-backend + 7-metrics-ingest M1.
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
from ccai.pychestrate.webservice.metrics.ingest import (
    MetricExtensionUnknownError,
    MetricsIngestEventTopics,
    ResourceReservationGrantedCounter,
    emit_metric_for_event,
    list_metric_extensions,
    register_builtin_extensions as metrics_ingest_register,
    reload_definitions_from_extensions,
)
from ccai.pychestrate.webservice.metrics.timeseries import (
    MetricCardinalityExceededError,
    MetricDefinition,
    MetricKind,
    MetricLabelInvalidError,
    MetricUnknownError,
    NativePgTimeseriesDriver,
    TimeseriesDriverNotFoundError,
    TimeseriesEventTopics,
    get_facade,
    get_metric_registry,
    list_definitions,
    list_samples_for_metric,
    register_builtin_extensions as timeseries_register,
    register_definition,
    reset_for_testing,
    write_counter,
    write_gauge,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_for_testing()
    timeseries_register()
    return


def _prepare_runtime_with_ingest() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    reset_for_testing()
    timeseries_register()
    metrics_ingest_register()
    return


def _counter_definition(
        *,
        name: str = "pychestrate_test_counter",
        cardinality_max: int = 1000
    ) -> MetricDefinition:
    rtnval = MetricDefinition(
        name=name,
        kind=MetricKind.COUNTER,
        label_names=("project_id", "kind"),
        help_text="test counter",
        cardinality_max=cardinality_max,
    )
    return rtnval


def _gauge_definition() -> MetricDefinition:
    rtnval = MetricDefinition(
        name="pychestrate_test_gauge",
        kind=MetricKind.GAUGE,
        label_names=("env",),
        help_text="test gauge",
    )
    return rtnval


# -------------------------------------
# Registry + facade primitives
# -------------------------------------

def test_register_definition_persists_in_registry_and_emits():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: register_definition adds the definition to the
    in-memory registry and emits DEFINITION_REGISTERED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=TimeseriesEventTopics.DEFINITION_REGISTERED,
        subscriber=lambda e: received.append(e),
    )
    register_definition(
        db_session=session, definition=_counter_definition(),
    )
    registry = get_metric_registry()
    found = registry.find(name="pychestrate_test_counter")
    testbase.assert_equal(found is not None, True)
    testbase.assert_equal(found.kind, MetricKind.COUNTER)
    testbase.assert_equal(len(received), 1)
    return


def test_write_counter_persists_sample_and_buffers():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: write_counter persists a sample via the active
    driver and appends to the in-memory buffer.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_definition(
        db_session=session, definition=_counter_definition(),
    )
    sample = write_counter(
        db_session=session, name="pychestrate_test_counter",
        delta=1.0, labels={"project_id": "p1", "kind": "device"},
    )
    testbase.assert_equal(sample.value, 1.0)
    testbase.assert_equal(sample.metric_name, "pychestrate_test_counter")

    # Persisted via the active driver
    rows = list_samples_for_metric(
        db_session=session, metric_name="pychestrate_test_counter",
    )
    testbase.assert_equal(len(rows), 1)
    testbase.assert_equal(rows[0].value, 1.0)

    # Buffered in the facade
    facade = get_facade()
    snapshot = facade.buffer_snapshot()
    testbase.assert_equal(len(snapshot), 1)
    return


def test_write_gauge_records_value():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: write_gauge persists the current value (not a
    delta).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_definition(
        db_session=session, definition=_gauge_definition(),
    )
    sample = write_gauge(
        db_session=session, name="pychestrate_test_gauge",
        value=42.5, labels={"env": "prod"},
    )
    testbase.assert_equal(sample.value, 42.5)
    return


def test_write_unknown_metric_raises():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: write_counter on an unregistered metric raises
    MetricUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        write_counter(
            db_session=session, name="pychestrate_unknown",
            delta=1.0, labels={},
        )
    except MetricUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_write_kind_mismatch_raises():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: calling write_counter on a gauge metric raises
    MetricLabelInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_definition(
        db_session=session, definition=_gauge_definition(),
    )
    raised = False
    try:
        write_counter(
            db_session=session, name="pychestrate_test_gauge",
            delta=1.0, labels={"env": "prod"},
        )
    except MetricLabelInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_write_label_mismatch_raises():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: missing or extra labels raise
    MetricLabelInvalidError listing each.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_definition(
        db_session=session, definition=_counter_definition(),
    )
    raised_missing = False
    try:
        write_counter(
            db_session=session, name="pychestrate_test_counter",
            delta=1.0, labels={"project_id": "p1"},
        )
    except MetricLabelInvalidError as xcpt:
        raised_missing = True
        testbase.assert_equal("kind" in str(xcpt), True)
    testbase.assert_equal(raised_missing, True)

    raised_extra = False
    try:
        write_counter(
            db_session=session, name="pychestrate_test_counter",
            delta=1.0,
            labels={"project_id": "p1", "kind": "device", "extra": "x"},
        )
    except MetricLabelInvalidError as xcpt:
        raised_extra = True
        testbase.assert_equal("extra" in str(xcpt), True)
    testbase.assert_equal(raised_extra, True)
    return


def test_write_cardinality_max_enforced():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: a write that would push past cardinality_max
    raises MetricCardinalityExceededError; the offending
    label-tuple does not get persisted.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_definition(
        db_session=session,
        definition=_counter_definition(
            name="pychestrate_capped", cardinality_max=2,
        ),
    )
    write_counter(
        db_session=session, name="pychestrate_capped",
        delta=1.0, labels={"project_id": "p1", "kind": "device"},
    )
    write_counter(
        db_session=session, name="pychestrate_capped",
        delta=1.0, labels={"project_id": "p2", "kind": "device"},
    )
    # Same label tuple as one already seen — does NOT count
    # toward cardinality and should succeed.
    write_counter(
        db_session=session, name="pychestrate_capped",
        delta=1.0, labels={"project_id": "p1", "kind": "device"},
    )

    raised = False
    try:
        write_counter(
            db_session=session, name="pychestrate_capped",
            delta=1.0, labels={"project_id": "p3", "kind": "device"},
        )
    except MetricCardinalityExceededError:
        raised = True
    testbase.assert_equal(raised, True)
    facade = get_facade()
    testbase.assert_equal(facade.cardinality_for(name="pychestrate_capped"), 2)
    return


def test_write_without_driver_raises():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: with no driver registered, writes raise
    TimeseriesDriverNotFoundError.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    reset_for_testing()
    _engine, session = build_in_memory_session()
    register_definition(
        db_session=session, definition=_counter_definition(),
    )
    raised = False
    try:
        write_counter(
            db_session=session, name="pychestrate_test_counter",
            delta=1.0, labels={"project_id": "p1", "kind": "device"},
        )
    except TimeseriesDriverNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_definitions_returns_sorted():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: list_definitions returns registered definitions
    in sorted-name order.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_definition(
        db_session=session, definition=_counter_definition(name="b_metric"),
    )
    register_definition(
        db_session=session, definition=_counter_definition(name="a_metric"),
    )
    names = [d.name for d in list_definitions()]
    testbase.assert_equal(names, sorted(names))
    return


def test_label_signature_is_dict_order_insensitive():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: two writes with the same label values in
    different dict orders share the same label_signature.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_definition(
        db_session=session, definition=_counter_definition(),
    )
    a = write_counter(
        db_session=session, name="pychestrate_test_counter",
        delta=1.0, labels={"project_id": "p1", "kind": "device"},
    )
    b = write_counter(
        db_session=session, name="pychestrate_test_counter",
        delta=1.0, labels={"kind": "device", "project_id": "p1"},
    )
    testbase.assert_equal(a.label_signature, b.label_signature)
    return


# -------------------------------------
# Native driver
# -------------------------------------

def test_native_driver_is_registered_at_phase9_bootstrap():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: register_builtin_extensions seeds the
    NativePgTimeseriesDriver and writes succeed.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    testbase.assert_equal(
        NativePgTimeseriesDriver.driver_name(), "native-pg",
    )
    register_definition(
        db_session=session, definition=_counter_definition(),
    )
    sample = write_counter(
        db_session=session, name="pychestrate_test_counter",
        delta=2.5, labels={"project_id": "p1", "kind": "pool"},
    )
    testbase.assert_equal(sample.value, 2.5)
    return


# -------------------------------------
# 7-metrics-ingest
# -------------------------------------

def test_reload_definitions_from_extensions_seeds_registry_and_emits():
    """
    **Feature: 7-metrics-ingest (M1)**
    **Property: reload_definitions_from_extensions walks every
    registered MetricDefinitionExtension, pushes its definition
    into the registry, and emits METRICS_REGISTRY_LOADED.**
    """
    _prepare_runtime_with_ingest()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=MetricsIngestEventTopics.METRICS_REGISTRY_LOADED,
        subscriber=lambda e: received.append(e),
    )
    views = reload_definitions_from_extensions(db_session=session)
    testbase.assert_equal(len(views) >= 1, True)
    # The reference extension is registered in the registry.
    registered_names = [d.name for d in list_definitions()]
    testbase.assert_equal(
        ResourceReservationGrantedCounter.metric_name() in registered_names,
        True,
    )
    testbase.assert_equal(len(received), 1)
    return


def test_emit_metric_for_event_writes_through_facade():
    """
    **Feature: 7-metrics-ingest (M1)**
    **Property: emit_metric_for_event resolves the extension,
    extracts labels + value, and writes through the facade.
    Emits SAMPLE_EMITTED.**
    """
    _prepare_runtime_with_ingest()
    _engine, session = build_in_memory_session()
    reload_definitions_from_extensions(db_session=session)
    received: List[EntityEvent] = []
    subscribe(
        topic=MetricsIngestEventTopics.SAMPLE_EMITTED,
        subscriber=lambda e: received.append(e),
    )
    sample = emit_metric_for_event(
        db_session=session,
        metric_name=ResourceReservationGrantedCounter.metric_name(),
        event_payload={
            "project_id": "p1",
            "resource_id": "r1",
            "mode": "exclusive",
        },
    )
    testbase.assert_equal(sample.metric_name, ResourceReservationGrantedCounter.metric_name())
    testbase.assert_equal(sample.labels["mode"], "exclusive")
    testbase.assert_equal(len(received), 1)
    rows = list_samples_for_metric(
        db_session=session,
        metric_name=ResourceReservationGrantedCounter.metric_name(),
    )
    testbase.assert_equal(len(rows), 1)
    return


def test_emit_metric_unknown_extension_raises():
    """
    **Feature: 7-metrics-ingest (M1)**
    **Property: emit_metric_for_event with an unknown metric
    name raises MetricExtensionUnknownError.**
    """
    _prepare_runtime_with_ingest()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        emit_metric_for_event(
            db_session=session,
            metric_name="pychestrate_unknown",
            event_payload={},
        )
    except MetricExtensionUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_metric_extensions_returns_in_tree_pack():
    """
    **Feature: 7-metrics-ingest (M1)**
    **Property: list_metric_extensions returns at least the
    in-tree reference extension after registration.**
    """
    _prepare_runtime_with_ingest()
    extensions = list_metric_extensions()
    metric_names = [v.metric_name for v in extensions]
    testbase.assert_equal(
        ResourceReservationGrantedCounter.metric_name() in metric_names,
        True,
    )
    return


def test_reset_for_testing_drops_singletons():
    """
    **Feature: 0-timeseries-backend (M1)**
    **Property: reset_for_testing drops the registry + facade
    singletons; subsequent get_metric_registry returns a fresh
    empty registry.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    register_definition(
        db_session=session, definition=_counter_definition(),
    )
    testbase.assert_equal(
        get_metric_registry().find(name="pychestrate_test_counter") is not None,
        True,
    )
    reset_for_testing()
    fresh = get_metric_registry()
    testbase.assert_equal(
        fresh.find(name="pychestrate_test_counter") is None, True,
    )
    return
