"""
.. module:: test_p26c_metrics_runtime_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression tests for audit ORC-04 -- the Layer-7 runtime
               (metric catalog, metric writer, alert evaluator), the
               series selection SLOs and alert rules read, the view
               registry self-check, and real outbound test deliveries.

.. moduleauthor:: Code Craft AI LLC

Before the fix nothing bootstrapped Layer 7 or Layer 8: the SLO,
alert-rule and tile registries were empty, the metric catalog was
empty, no metric extension ever wrote a sample, no alert rule was
ever evaluated, and an outbound test delivery stayed ``pending``
forever. Once registered, the kinds still read nothing: they matched
one series by the exact signature of the rule's label filter, so an
empty filter (the natural choice) matched no series of any in-tree
metric, and a counter alert compared a single increment instead of
the increments in a window.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import threading

from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import sessionmaker

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.phase7_bootstrap import (
    ALERT_EVALUATOR_TASK_NAME,
    Phase7BootstrapConfig,
    bootstrap_phase7_runtime,
    evaluate_alert_rules_once,
    make_alert_evaluator_task,
    register_phase7_builtin_extensions,
    reset_phase7_runtime_for_testing,
)
from ccai.pychestrate.webservice.extensions.phase8_bootstrap import (
    register_phase8_builtin_extensions,
)
from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.extensions.view_registry_self_check import (
    check_view_registries,
)
from ccai.pychestrate.webservice.jobs.scheduling import PeriodicTaskScheduler
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    publish,
    reset_for_testing as reset_event_bus,
)
from ccai.pychestrate.webservice.metrics.alerts import (
    AlertState,
    create_alert_rule,
    evaluate_alert_rule,
    get_live_state,
)
from ccai.pychestrate.webservice.metrics.slos import (
    compute_status,
    create_slo,
)
from ccai.pychestrate.webservice.metrics.timeseries import (
    MetricDefinition,
    MetricKind,
    list_definitions,
    register_definition,
    reset_for_testing as reset_timeseries,
    write_counter,
)
from ccai.pychestrate.webservice.metrics.timeseries import (
    repository as ts_repository,
)
from ccai.pychestrate.webservice.metrics.timeseries.models import (
    TimeseriesSample,
)
from ccai.pychestrate.webservice.metrics.timeseries.selection import (
    select_samples,
)
from ccai.pychestrate.webservice.webhooks_out import delivery as out_delivery
from ccai.pychestrate.webservice.webhooks_out.models import DeliveryOutcome
from ccai.pychestrate.webservice.webhooks_out.service import (
    SignedRequest,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-00000000c401"
OTHER_PROJECT_UUID = "00000000-0000-4000-8000-00000000c402"

COUNTER_METRIC = "pychestrate_test_c4_events_total"
GOOD_METRIC = "pychestrate_test_c4_good_total"
TOTAL_METRIC = "pychestrate_test_c4_all_total"
GLOBAL_COUNTER_METRIC = "pychestrate_test_c4_global_total"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_runtime() -> None:
    """
        Empty every registry the Layer-7 runtime touches, then register
        the Layer-7 extensions the way the service start does.
    """
    reset_phase7_runtime_for_testing()
    reset_registry_for_testing()
    reset_event_bus()
    reset_timeseries()
    register_phase7_builtin_extensions()
    return


def _teardown_runtime() -> None:
    reset_phase7_runtime_for_testing()
    reset_event_bus()
    reset_timeseries()
    return


def _register_counter(*, session: Any, name: str, label_names: Tuple[str, ...]) -> None:
    register_definition(
        db_session=session,
        definition=MetricDefinition(
            name=name,
            kind=MetricKind.COUNTER,
            label_names=label_names,
            help_text="ORC-04 test counter",
        ),
    )
    return


def _insert_old_increment(*, session: Any, name: str, labels: Dict[str, str], value: float, age_seconds: int) -> None:
    ts_repository.insert_sample(
        db_session=session,
        metric_name=name,
        label_signature="old",
        labels=dict(labels),
        value=value,
        observed_at=utc_now() - timedelta(seconds=age_seconds),
    )
    session.commit()
    return


def _threshold_rule(*, session: Any, config: Dict[str, Any], name: str = "rule") -> Any:
    rtnval = create_alert_rule(
        db_session=session,
        project_id=PROJECT_UUID,
        name=name,
        kind="threshold",
        config=config,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Layer-7 runtime bootstrap
# ---------------------------------------------------------------------------


def test_phase7_bootstrap_loads_the_metric_catalog():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: bootstrap_phase7_runtime loads every registered metric
    definition into the timeseries registry, so the metric catalog the
    Timeseries view and the tile / alert pickers list is not empty.**
    """
    _fresh_runtime()
    engine, session = build_in_memory_session()
    scheduler = PeriodicTaskScheduler()
    try:
        bootstrap_phase7_runtime(config=Phase7BootstrapConfig(
            session_factory=sessionmaker(bind=engine),
            scheduler=scheduler,
        ))
        names = [definition.name for definition in list_definitions()]
    finally:
        scheduler.stop()
        session.close()
        _teardown_runtime()
    testbase.assert_equal("pychestrate_rpa_jobs_triggered_total" in names, True)
    return


def test_phase7_bootstrap_attaches_the_metric_writer():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: after bootstrap_phase7_runtime, publishing an event a
    metric extension measures (entity.rpa.job_started) writes a
    sample for that metric.**
    """
    _fresh_runtime()
    engine, session = build_in_memory_session()
    scheduler = PeriodicTaskScheduler()
    try:
        bootstrap_phase7_runtime(config=Phase7BootstrapConfig(
            session_factory=sessionmaker(bind=engine),
            scheduler=scheduler,
        ))
        publish(event=EntityEvent(
            topic="entity.rpa.job_started",
            payload={"project_id": PROJECT_UUID, "type_id": "smoke", "execution_mode": "pod"},
            source_event_id=new_uuid(),
        ))
        rows = (
            session.query(TimeseriesSample)
            .filter(TimeseriesSample.metric_name == "pychestrate_rpa_jobs_triggered_total")
            .all()
        )
    finally:
        scheduler.stop()
        session.close()
        _teardown_runtime()
    testbase.assert_equal(len(rows), 1)
    return


def test_phase7_bootstrap_schedules_the_alert_evaluator():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: bootstrap_phase7_runtime registers the periodic alert
    evaluator on the scheduler and starts it.**
    """
    _fresh_runtime()
    engine, session = build_in_memory_session()
    scheduler = PeriodicTaskScheduler()
    try:
        bootstrap_phase7_runtime(config=Phase7BootstrapConfig(
            session_factory=sessionmaker(bind=engine),
            scheduler=scheduler,
        ))
        names = scheduler.task_names()
        running = scheduler.is_running()
    finally:
        scheduler.stop()
        session.close()
        _teardown_runtime()
    testbase.assert_equal(names, [ALERT_EVALUATOR_TASK_NAME])
    testbase.assert_equal(running, True)
    return


def test_alert_evaluator_tick_evaluates_every_enabled_rule():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: one tick of the alert evaluator evaluates the enabled
    rules, so a rule whose metric crossed its threshold is FIRING
    without anyone calling evaluate by hand.**
    """
    _fresh_runtime()
    engine, session = build_in_memory_session()
    try:
        _register_counter(session=session, name=COUNTER_METRIC, label_names=("project_id",))
        rule = _threshold_rule(session=session, config={
            "metric_name": COUNTER_METRIC, "op": ">", "threshold": 0,
        })
        write_counter(db_session=session, name=COUNTER_METRIC, delta=1.0, labels={"project_id": PROJECT_UUID})
        session.commit()
        make_alert_evaluator_task(session_factory=sessionmaker(bind=engine), interval_seconds=60.0)
        evaluated = evaluate_alert_rules_once()
        live = get_live_state(db_session=session, rule_id=rule.rule_id)
    finally:
        session.close()
        _teardown_runtime()
    testbase.assert_equal(evaluated, 1)
    testbase.assert_equal(live.state, AlertState.FIRING)
    return


def test_alert_evaluator_tick_survives_an_unreadable_rule_table():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: when the rule table cannot be read (schema not
    created), an evaluator tick evaluates nothing and does not raise,
    so the scheduler keeps ticking.**
    """
    _fresh_runtime()
    try:
        # A bare in-memory engine: no tables at all.
        from sqlalchemy import create_engine  # noqa: E402
        make_alert_evaluator_task(
            session_factory=sessionmaker(bind=create_engine("sqlite://")),
            interval_seconds=60.0,
        )
        evaluated = evaluate_alert_rules_once()
    finally:
        _teardown_runtime()
    testbase.assert_equal(evaluated, 0)
    return


# ---------------------------------------------------------------------------
# Series selection -- threshold alert kind
# ---------------------------------------------------------------------------


def test_threshold_rule_with_an_empty_filter_reads_labelled_series():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: a threshold rule with no label filter reads every
    series of its metric (subset match) -- the in-tree metrics all
    carry labels, and an exact match on the empty filter read none.**
    """
    _fresh_runtime()
    _engine, session = build_in_memory_session()
    try:
        _register_counter(session=session, name=COUNTER_METRIC, label_names=("project_id", "type_id"))
        rule = _threshold_rule(session=session, config={
            "metric_name": COUNTER_METRIC, "op": ">=", "threshold": 1,
        })
        write_counter(db_session=session, name=COUNTER_METRIC, delta=1.0,
                      labels={"project_id": PROJECT_UUID, "type_id": "smoke"})
        result = evaluate_alert_rule(db_session=session, rule_id=rule.rule_id)
    finally:
        session.close()
        _teardown_runtime()
    testbase.assert_equal(result.state, AlertState.FIRING)
    return


def test_threshold_rule_on_a_counter_sums_the_increments_in_its_window():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: a counter stores increments; a threshold rule on a
    counter compares the sum of the increments inside window_seconds,
    not the latest single increment.**
    """
    _fresh_runtime()
    _engine, session = build_in_memory_session()
    try:
        _register_counter(session=session, name=COUNTER_METRIC, label_names=("project_id",))
        rule = _threshold_rule(session=session, config={
            "metric_name": COUNTER_METRIC, "op": ">", "threshold": 2, "window_seconds": 600,
        })
        for _index in range(3):
            write_counter(db_session=session, name=COUNTER_METRIC, delta=1.0, labels={"project_id": PROJECT_UUID})
        result = evaluate_alert_rule(db_session=session, rule_id=rule.rule_id)
    finally:
        session.close()
        _teardown_runtime()
    testbase.assert_equal(result.observed_value, 3.0)
    return


def test_threshold_rule_on_a_counter_ignores_increments_older_than_its_window():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: increments recorded before window_seconds do not count,
    so a failure-count rule resolves once a window passes without
    failures.**
    """
    _fresh_runtime()
    _engine, session = build_in_memory_session()
    try:
        _register_counter(session=session, name=COUNTER_METRIC, label_names=("project_id",))
        rule = _threshold_rule(session=session, config={
            "metric_name": COUNTER_METRIC, "op": ">", "threshold": 0, "window_seconds": 3600,
        })
        _insert_old_increment(session=session, name=COUNTER_METRIC,
                              labels={"project_id": PROJECT_UUID}, value=5.0, age_seconds=7200)
        result = evaluate_alert_rule(db_session=session, rule_id=rule.rule_id)
    finally:
        session.close()
        _teardown_runtime()
    testbase.assert_equal((result.state, result.observed_value), (AlertState.OK, 0.0))
    return


def test_threshold_rule_reads_only_its_own_project_series():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: for a metric that carries a project_id label, a rule
    reads only the series of its own project.**
    """
    _fresh_runtime()
    _engine, session = build_in_memory_session()
    try:
        _register_counter(session=session, name=COUNTER_METRIC, label_names=("project_id",))
        rule = _threshold_rule(session=session, config={
            "metric_name": COUNTER_METRIC, "op": ">", "threshold": 0,
        })
        write_counter(db_session=session, name=COUNTER_METRIC, delta=4.0, labels={"project_id": OTHER_PROJECT_UUID})
        result = evaluate_alert_rule(db_session=session, rule_id=rule.rule_id)
    finally:
        session.close()
        _teardown_runtime()
    testbase.assert_equal((result.state, result.observed_value), (AlertState.OK, 0.0))
    return


def test_threshold_rule_rejects_a_non_positive_window():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: window_seconds must be a positive integer.**
    """
    from ccai.pychestrate.webservice.metrics.alerts.factories.threshold_rule_kind import (  # noqa: E402
        ThresholdAlertRuleKind,
    )
    valid, issues = ThresholdAlertRuleKind.validate_config(config={
        "metric_name": COUNTER_METRIC, "op": ">", "threshold": 1, "window_seconds": 0,
    })
    testbase.assert_equal((valid, len(issues)), (False, 1))
    return


# ---------------------------------------------------------------------------
# Series selection -- SLO availability ratio + selection helper
# ---------------------------------------------------------------------------


def test_availability_slo_with_an_empty_filter_reads_labelled_series():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: an availability_ratio SLO with no label filter computes
    good / total over the labelled series of its project.**
    """
    _fresh_runtime()
    _engine, session = build_in_memory_session()
    try:
        _register_counter(session=session, name=GOOD_METRIC, label_names=("project_id", "type_id"))
        _register_counter(session=session, name=TOTAL_METRIC, label_names=("project_id", "type_id", "execution_mode"))
        slo = create_slo(
            db_session=session, project_id=PROJECT_UUID, name="rpa success",
            kind="availability_ratio", target=0.5, window_seconds=86400,
            definition_config={"good_metric_name": GOOD_METRIC, "total_metric_name": TOTAL_METRIC},
        )
        for _index in range(3):
            write_counter(db_session=session, name=GOOD_METRIC, delta=1.0,
                          labels={"project_id": PROJECT_UUID, "type_id": "smoke"})
        for _index in range(4):
            write_counter(db_session=session, name=TOTAL_METRIC, delta=1.0,
                          labels={"project_id": PROJECT_UUID, "type_id": "smoke", "execution_mode": "pod"})
        write_counter(db_session=session, name=TOTAL_METRIC, delta=1.0,
                      labels={"project_id": OTHER_PROJECT_UUID, "type_id": "smoke", "execution_mode": "pod"})
        status = compute_status(db_session=session, slo_id=slo.slo_id)
    finally:
        session.close()
        _teardown_runtime()
    testbase.assert_equal(status.achieved_ratio, 0.75)
    return


def test_select_samples_does_not_scope_metrics_without_a_project_label():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: a metric without a project_id label is not narrowed by
    the rule's project -- its series are global.**
    """
    _fresh_runtime()
    _engine, session = build_in_memory_session()
    try:
        _register_counter(session=session, name=GLOBAL_COUNTER_METRIC, label_names=("surface_count",))
        write_counter(db_session=session, name=GLOBAL_COUNTER_METRIC, delta=1.0, labels={"surface_count": "4"})
        rows = select_samples(
            db_session=session,
            metric_name=GLOBAL_COUNTER_METRIC,
            label_filter={},
            project_id=PROJECT_UUID,
        )
    finally:
        session.close()
        _teardown_runtime()
    testbase.assert_equal(len(rows), 1)
    return


def test_select_samples_applies_the_label_filter_as_a_subset():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: a label filter keeps series whose labels include every
    filter pair and drops the rest.**
    """
    _fresh_runtime()
    _engine, session = build_in_memory_session()
    try:
        _register_counter(session=session, name=COUNTER_METRIC, label_names=("project_id", "type_id"))
        write_counter(db_session=session, name=COUNTER_METRIC, delta=1.0,
                      labels={"project_id": PROJECT_UUID, "type_id": "smoke"})
        write_counter(db_session=session, name=COUNTER_METRIC, delta=1.0,
                      labels={"project_id": PROJECT_UUID, "type_id": "nightly"})
        rows = select_samples(
            db_session=session,
            metric_name=COUNTER_METRIC,
            label_filter={"type_id": "nightly"},
            project_id=PROJECT_UUID,
        )
    finally:
        session.close()
        _teardown_runtime()
    testbase.assert_equal([row.labels["type_id"] for row in rows], ["nightly"])
    return


# ---------------------------------------------------------------------------
# View registry self-check
# ---------------------------------------------------------------------------


def test_view_registry_self_check_reports_an_empty_registry():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: with no registered SLO kind the self-check reports a
    gap for the /slos view.**
    """
    reset_registry_for_testing()
    try:
        gaps = check_view_registries()
    finally:
        _fresh_runtime()
        _teardown_runtime()
    routes = [(gap.route, gap.registry) for gap in gaps]
    testbase.assert_equal(("/slos", "slo_definition_kind") in routes, True)
    return


def test_view_registry_self_check_is_clean_for_layer7_and_layer8_views():
    """
    **Feature: metrics runtime -- audit ORC-04**
    **Property: after the Layer-7 / Layer-8 registration and catalog
    load the service start performs, no Layer-7 or Layer-8 view is
    reported.**
    """
    _fresh_runtime()
    engine, session = build_in_memory_session()
    scheduler = PeriodicTaskScheduler()
    try:
        register_phase8_builtin_extensions()
        bootstrap_phase7_runtime(config=Phase7BootstrapConfig(
            session_factory=sessionmaker(bind=engine),
            scheduler=scheduler,
        ))
        gaps = check_view_registries()
    finally:
        scheduler.stop()
        session.close()
        _teardown_runtime()
    layer78 = ("/timeseries", "/dashboards", "/slos", "/metric-alerts", "/webhooks", "/release-channels")
    testbase.assert_equal([gap.route for gap in gaps if gap.route in layer78], [])
    return


# ---------------------------------------------------------------------------
# Outbound delivery
# ---------------------------------------------------------------------------


class _Receiver:
    """
        A local HTTP receiver: ``/ok`` answers 200, ``/fail`` 500,
        ``/redirect`` 302 to ``/ok``. Records every request.
    """

    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        receiver = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 -- http.server hook
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                receiver.requests.append({
                    "path": self.path,
                    "headers": {key.lower(): value for key, value in self.headers.items()},
                    "body": body,
                })
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/ok")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 200 if self.path == "/ok" else 500
                payload = b"received" if status == 200 else b"boom"
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 -- http.server hook
                return

        self._server = HTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return

    def url(self, *, path: str) -> str:
        rtnval = "http://127.0.0.1:{}{}".format(self._server.server_address[1], path)
        return rtnval

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        return


def _signed(*, url: str) -> SignedRequest:
    body = json.dumps({"event": "test"}).encode("utf-8")
    rtnval = SignedRequest(
        method="POST",
        url=url,
        headers={
            "Content-Type": "application/json",
            "X-Pychestrate-Signature": "sha256=feedface",
            "X-Pychestrate-Delivery-Id": "d-1",
        },
        body=body,
        signature="sha256=feedface",
        payload_digest_sha256="0" * 64,
        delivery_id="d-1",
    )
    return rtnval


def _allow_loopback_receiver() -> Any:
    """
        Let the delivery guard accept the local test receiver (the guard
        refuses loopback in production).
    """
    patch = create_module_patch(out_delivery, "forbidden_address_reason")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: None)
    return patch


def test_delivery_url_check_refuses_loopback_addresses():
    """
    **Feature: outbound webhook delivery -- audit ORC-04**
    **Property: a subscription URL on a loopback address is refused, so
    a webhook cannot call the Pychestrate server's local services.**
    """
    reason = out_delivery.check_delivery_url(url="http://127.0.0.1:8080/admin")
    testbase.assert_equal(reason is not None and "loopback" in reason, True)
    return


def test_delivery_url_check_refuses_the_metadata_address():
    """
    **Feature: outbound webhook delivery -- audit ORC-04**
    **Property: the link-local cloud-metadata address is refused.**
    """
    reason = out_delivery.check_delivery_url(url="http://169.254.169.254/latest/meta-data")
    testbase.assert_equal(reason is not None and "link-local" in reason, True)
    return


def test_delivery_url_check_refuses_localhost_names():
    """
    **Feature: outbound webhook delivery -- audit ORC-04**
    **Property: localhost host names are refused without resolving.**
    """
    reason = out_delivery.check_delivery_url(url="https://api.localhost/hook")
    testbase.assert_equal(reason is not None and "localhost" in reason, True)
    return


def test_delivery_url_check_allows_private_addresses():
    """
    **Feature: outbound webhook delivery -- audit ORC-04**
    **Property: private-range receivers (on-premises tools) are
    allowed.**
    """
    reason = out_delivery.check_delivery_url(url="http://10.20.30.40:8443/hook")
    testbase.assert_equal(reason, None)
    return


def test_send_signed_request_delivers_to_a_2xx_receiver():
    """
    **Feature: outbound webhook delivery -- audit ORC-04**
    **Property: a delivery the receiver answers with 2xx is SUCCEEDED
    and carries the signed headers and body.**
    """
    receiver = _Receiver()
    patch = _allow_loopback_receiver()
    try:
        signed = _signed(url=receiver.url(path="/ok"))
        result = out_delivery.send_signed_request(signed=signed, timeout_seconds=5.0)
    finally:
        patch.deactivate()
        receiver.close()
    seen = receiver.requests[0]
    testbase.assert_equal(
        (result.outcome, result.response_status, seen["headers"]["x-pychestrate-signature"], seen["body"]),
        (DeliveryOutcome.SUCCEEDED, 200, "sha256=feedface", signed.body),
    )
    return


def test_send_signed_request_reports_a_receiver_error_as_failed():
    """
    **Feature: outbound webhook delivery -- audit ORC-04**
    **Property: a non-2xx answer is a FAILED delivery carrying the
    receiver's status and response excerpt.**
    """
    receiver = _Receiver()
    patch = _allow_loopback_receiver()
    try:
        result = out_delivery.send_signed_request(signed=_signed(url=receiver.url(path="/fail")), timeout_seconds=5.0)
    finally:
        patch.deactivate()
        receiver.close()
    testbase.assert_equal(
        (result.outcome, result.response_status, result.response_excerpt),
        (DeliveryOutcome.FAILED, 500, "boom"),
    )
    return


def test_send_signed_request_does_not_follow_redirects():
    """
    **Feature: outbound webhook delivery -- audit ORC-04**
    **Property: a 3xx answer is recorded as FAILED and the redirect
    target is never called.**
    """
    receiver = _Receiver()
    patch = _allow_loopback_receiver()
    try:
        result = out_delivery.send_signed_request(signed=_signed(url=receiver.url(path="/redirect")), timeout_seconds=5.0)
    finally:
        patch.deactivate()
        receiver.close()
    testbase.assert_equal(
        (result.outcome, [request["path"] for request in receiver.requests]),
        (DeliveryOutcome.FAILED, ["/redirect"]),
    )
    return


def test_send_signed_request_never_calls_a_refused_address():
    """
    **Feature: outbound webhook delivery -- audit ORC-04**
    **Property: a URL the guard refuses is not called; the attempt is
    FAILED with a "not sent" reason.**
    """
    receiver = _Receiver()
    try:
        result = out_delivery.send_signed_request(signed=_signed(url=receiver.url(path="/ok")), timeout_seconds=5.0)
    finally:
        receiver.close()
    testbase.assert_equal(
        (result.outcome, len(receiver.requests), (result.response_excerpt or "").startswith("not sent:")),
        (DeliveryOutcome.FAILED, 0, True),
    )
    return
