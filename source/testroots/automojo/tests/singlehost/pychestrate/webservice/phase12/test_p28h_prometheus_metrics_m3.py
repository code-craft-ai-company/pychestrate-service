"""
.. module:: test_p28h_prometheus_metrics_m3
    :synopsis: Tests for the Prometheus /metrics surface.

Covers:

* :func:`render_metrics` emits HELP + TYPE comments and one
  sample line per gauge family, including zero buckets.
* Output is well-formed Prometheus text format: every body
  line is either a comment, blank, or ``name value`` /
  ``name{labels} value``.
* Counts reflect the underlying queue state (jobs_by_state,
  workers_by_status, in_flight, retry_scheduled,
  oldest_pending_age_seconds).
* ``oldest_pending_age_seconds`` falls back to 0 for an
  empty queue (Prometheus gauges don't have null).
* :func:`_resolve_require_admin` returns False by default;
  truthy env values flip it.
* Label values are escaped (backslash, newline, double
  quote).

End-to-end through dispatcher coverage of the public ``/metrics``
endpoint requires juggling the env var at import time, so we
only test the inner ``render_metrics`` builder + the
``_resolve_require_admin`` helper at unit level. The endpoint
shape is validated by integration testing with a real running
service.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import tempfile

from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (  # noqa: F401
    PychestrateApplication,
)
from automojo.pychestrate.webservice.workers import jobservice
from automojo.pychestrate.webservice.workers import service as worker_service
from automojo.pychestrate.webservice.workers.models import WorkerKind
from automojo.pychestrate.webservice.workers.restapi.v1 import (
    metricsblueprint,
)


def _build_engine_and_factory() -> Tuple[sa.engine.Engine, sessionmaker, str]:
    fd, path = tempfile.mkstemp(prefix="pych_p28h_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory, path


def _line_set(*, body: str):
    rtnval = [line for line in body.split("\n") if len(line) > 0]
    return rtnval


def test_render_metrics_emits_help_and_type_comments():
    """
    **Feature: P28h Prometheus metrics (M3)**
    **Property: Each gauge family emits the conventional
    ``# HELP`` and ``# TYPE`` comments, in that order, with
    every advertised metric name appearing.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            body = metricsblueprint.render_metrics(
                db_session=db_session,
            )
        finally:
            db_session.close()
        for name in (
            "pychestrate_jobs_by_state",
            "pychestrate_workers_by_status",
            "pychestrate_jobs_in_flight",
            "pychestrate_jobs_retry_scheduled",
            "pychestrate_oldest_pending_age_seconds",
        ):
            testbase.assert_equal(
                "# HELP {0}".format(name) in body, True,
            )
            testbase.assert_equal(
                "# TYPE {0} gauge".format(name) in body, True,
            )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_render_metrics_includes_zero_buckets_for_states_and_statuses():
    """
    **Feature: P28h Prometheus metrics (M3)**
    **Property: Every JobState and WorkerStatus value appears
    in the body, including ``0`` buckets, so a Prometheus
    rate() against an empty bucket doesn't error out.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            jobservice.enqueue_job(
                db_session=db_session, payload={"command": "x"},
            )
            worker_service.register_worker(
                db_session=db_session, name="alive",
                kind=WorkerKind.LOCAL_PROCESS,
            )
            body = metricsblueprint.render_metrics(
                db_session=db_session,
            )
        finally:
            db_session.close()
        for state in ("pending", "claimed", "running", "succeeded", "failed"):
            testbase.assert_equal(
                'pychestrate_jobs_by_state{{state="{0}"}}'.format(state)
                in body,
                True,
            )
        for status in ("idle", "running", "draining", "offline"):
            testbase.assert_equal(
                'pychestrate_workers_by_status{{status="{0}"}}'.format(status)
                in body,
                True,
            )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_render_metrics_counts_match_queue_stats():
    """
    **Feature: P28h Prometheus metrics (M3)**
    **Property: Numbers in the metrics body match the
    /queue/stats payload by construction (same service-layer
    helpers).**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            for n in range(3):
                jobservice.enqueue_job(
                    db_session=db_session,
                    payload={"command": "x{0}".format(n)},
                )
            wv = worker_service.register_worker(
                db_session=db_session, name="claimer",
                kind=WorkerKind.LOCAL_PROCESS,
            )
            jobservice.claim_next_job(
                db_session=db_session, worker_id=wv.worker_id,
            )

            stats_jobs = jobservice.count_jobs_by_state(
                db_session=db_session,
            )
            stats_workers = (
                worker_service.count_workers_by_status(
                    db_session=db_session,
                )
            )
            body = metricsblueprint.render_metrics(
                db_session=db_session,
            )
        finally:
            db_session.close()
        # Spot-check that the actual counts appear.
        testbase.assert_equal(
            'pychestrate_jobs_by_state{{state="pending"}} {0}'.format(
                stats_jobs["pending"],
            ) in body,
            True,
        )
        testbase.assert_equal(
            'pychestrate_jobs_by_state{{state="claimed"}} {0}'.format(
                stats_jobs["claimed"],
            ) in body,
            True,
        )
        testbase.assert_equal(
            'pychestrate_workers_by_status{{status="idle"}} {0}'.format(
                stats_workers["idle"],
            ) in body,
            True,
        )
        testbase.assert_equal(
            "pychestrate_jobs_in_flight 1" in body,
            True,
        )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_render_metrics_oldest_pending_age_seconds_zero_when_empty():
    """
    **Feature: P28h Prometheus metrics (M3)**
    **Property: Prometheus gauges can't be null. An empty
    queue reports ``oldest_pending_age_seconds`` as 0.0
    rather than skipping the metric.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            body = metricsblueprint.render_metrics(
                db_session=db_session,
            )
        finally:
            db_session.close()
        testbase.assert_equal(
            "pychestrate_oldest_pending_age_seconds 0" in body,
            True,
        )
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_render_metrics_body_is_well_formed_text_format():
    """
    **Feature: P28h Prometheus metrics (M3)**
    **Property: Every non-empty line is either a ``#``
    comment or a ``name`` / ``name{labels}`` followed by a
    space and a numeric value. No trailing whitespace.**
    """
    engine, factory, path = _build_engine_and_factory()
    try:
        db_session = factory()
        try:
            jobservice.enqueue_job(
                db_session=db_session, payload={"command": "x"},
            )
            body = metricsblueprint.render_metrics(
                db_session=db_session,
            )
        finally:
            db_session.close()
        for line in _line_set(body=body):
            if line.startswith("#"):
                continue
            # A sample line: <name>(<labels>)? <value>
            # Quick sanity — exactly one space between the
            # final ``}`` (or name) and the value.
            testbase.assert_equal(
                line.endswith(" ") is False,
                True,
            )
            parts = line.rsplit(" ", 1)
            testbase.assert_equal(len(parts), 2)
            # Value parses as a number.
            float(parts[1])
    finally:
        engine.dispose()
        os.unlink(path)
    return


def test_resolve_require_admin_default_is_false():
    """
    **Feature: P28h Prometheus metrics (M3)**
    **Property: Without the env var, the gate is OFF
    (public). Operators have to opt in to admin-gating
    explicitly.**
    """
    rtnval = metricsblueprint._resolve_require_admin(environment={})
    testbase.assert_equal(rtnval, False)
    return


def test_resolve_require_admin_truthy_values_flip():
    """
    **Feature: P28h Prometheus metrics (M3)**
    **Property: ``1`` / ``true`` / ``yes`` / ``on`` (case-
    insensitive) flip the gate ON.**
    """
    for raw in ("1", "true", "True", "YES", "on"):
        rtnval = metricsblueprint._resolve_require_admin(
            environment={"PYCHESTRATE_METRICS_REQUIRE_ADMIN": raw},
        )
        testbase.assert_equal(rtnval, True)
    return


def test_resolve_require_admin_falsy_values_stay_off():
    """
    **Feature: P28h Prometheus metrics (M3)**
    **Property: Anything other than the truthy set leaves
    the gate OFF.**
    """
    for raw in ("0", "false", "no", "", "garbage"):
        rtnval = metricsblueprint._resolve_require_admin(
            environment={"PYCHESTRATE_METRICS_REQUIRE_ADMIN": raw},
        )
        testbase.assert_equal(rtnval, False)
    return


def test_label_value_escaping():
    """
    **Feature: P28h Prometheus metrics (M3)**
    **Property: ``\\``, newline, and ``"`` in label values
    get escaped to ``\\\\``, ``\\n``, and ``\\"`` per the
    text format spec.**
    """
    out = metricsblueprint._escape_label_value(
        value='line\nwith"quote\\and\\back',
    )
    testbase.assert_equal(
        out, 'line\\nwith\\"quote\\\\and\\\\back',
    )
    return
