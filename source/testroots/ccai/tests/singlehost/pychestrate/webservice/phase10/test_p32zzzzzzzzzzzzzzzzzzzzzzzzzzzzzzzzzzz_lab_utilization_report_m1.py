"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_lab_utilization_report_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: How long each lab resource was in use over a period (ORG-F22).

.. moduleauthor:: Code Craft AI LLC

A lab manager's first questions about the equipment are which resources are busy, which sit idle and how
long people keep them. The allocation pages list who holds what and what was held, but gave no answer, and
the functions meant to (``get_utilization_metrics``, ``export_allocation_data``) were never surfaced.
``GET /resources/allocations/utilization`` now reports, for the last 7, 30, 90 or 365 days, each resource's
allocations, time in use and share of the period, and the same as a spreadsheet with ``?format=csv``.

Time in use is measured, not counted: each allocation is clipped to the period and overlapping allocations of
one resource are merged, so a resource shared by three people at the same hour is in use for one hour.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io
import uuid

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from ccai import testbase

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import Allocation, Resource
from ccai.pychestrate.webservice.webinterface.blueprints.resources import utilization as report_module
from ccai.pychestrate.webservice.webinterface.blueprints.resources.utilization import (
    AllocationSpan,
    ResourceRef,
    compute_utilization,
    merge_intervals,
    parse_period_days,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    ensure_seeded_viewer,
    login_as,
)


NOW = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)


def _at(day: str, hour: int, minute: int = 0) -> datetime:
    year, month, number = (int(part) for part in day.split("-"))
    return datetime(year, month, number, hour, minute, tzinfo=timezone.utc)


def test_a_period_is_one_of_the_offered_lengths():
    """
    **Feature: lab utilization report (ORG-F22)**
    **Property: ``?days=`` of 7, 30, 90 or 365 is kept, anything else (missing, text, 31, 0, negative) is 30.**
    """
    answers = [parse_period_days(raw) for raw in ("7", "30", "90", "365", None, "abc", "31", "0", "-7", " 90 ")]

    testbase.assert_equal(answers, [7, 30, 90, 365, 30, 30, 30, 30, 30, 90])
    return


def test_overlapping_intervals_are_merged_and_touching_ones_joined():
    """
    **Feature: lab utilization report (ORG-F22)**
    **Property: three intervals, two overlapping and one touching the end of the second, merge into one; a separate one stays apart.**
    """
    merged = merge_intervals([
        (_at("2026-05-01", 6), _at("2026-05-01", 12)),
        (_at("2026-05-01", 0), _at("2026-05-01", 10)),
        (_at("2026-05-01", 12), _at("2026-05-01", 14)),
        (_at("2026-05-02", 0), _at("2026-05-02", 1)),
    ])

    testbase.assert_equal(merged, [(_at("2026-05-01", 0), _at("2026-05-01", 14)), (_at("2026-05-02", 0), _at("2026-05-02", 1))])
    return


def test_time_in_use_is_clipped_merged_and_ordered_busiest_first():
    """
    **Feature: lab utilization report (ORG-F22)**
    **Property: over 30 days, an allocation that began before the period counts only inside it (24 h); two shared allocations of one
    resource overlapping for 4 h count once (12 h); a still-active one runs to the end of the period (2 h) and marks the resource in
    use now; an expired one with no check-in ends when its lease did (3 h); one that ended before the period and one for an unknown
    resource are left out; a zero-length one is still an allocation; the idle resource has a row of zeros; rows are busiest first;
    the summary adds up the same figures.**
    """
    resources = [ResourceRef(1, "bench-1", "Lab A"), ResourceRef(2, "bench-2"), ResourceRef(3, "bench-3")]
    spans = [
        AllocationSpan(1, _at("2026-04-01", 12), actual_checkin=_at("2026-04-05", 12), status="released"),
        AllocationSpan(1, _at("2026-05-01", 0), actual_checkin=_at("2026-05-01", 10), status="released"),
        AllocationSpan(1, _at("2026-05-01", 6), actual_checkin=_at("2026-05-01", 12), status="released"),
        AllocationSpan(1, _at("2026-05-04", 10), status="active"),
        AllocationSpan(2, _at("2026-04-20", 8), expected_checkin=_at("2026-04-20", 11), status="expired"),
        AllocationSpan(2, _at("2026-03-01", 8), actual_checkin=_at("2026-03-02", 8), status="released"),
        AllocationSpan(2, _at("2026-04-25", 9), actual_checkin=_at("2026-04-25", 9), status="forced"),
        AllocationSpan(99, _at("2026-05-02", 8), actual_checkin=_at("2026-05-02", 9), status="released"),
    ]

    report = compute_utilization(resources=resources, spans=spans, period_days=30, now=NOW)

    summary = {row.name: (row.allocations, row.hours_in_use, row.percent_in_use, row.in_use_now, row.last_checked_out) for row in report.rows}
    testbase.assert_equal(
        (
            [row.name for row in report.rows], summary["bench-1"], summary["bench-2"], summary["bench-3"],
            (report.allocations, report.resources_total, report.resources_used, report.hours_in_use, report.average_hours, report.peak_at_once),
        ),
        (
            ["bench-1", "bench-2", "bench-3"],
            (4, 38.0, 5.3, True, _at("2026-05-04", 10)),
            (2, 3.0, 0.4, False, _at("2026-04-25", 9)),
            (0, 0.0, 0.0, False, None),
            (6, 3, 2, 41.0, 7.5, 2),
        ),
    )
    return


def test_edges_naive_times_a_full_period_and_a_nothing_report():
    """
    **Feature: lab utilization report (ORG-F22)**
    **Property: an allocation that ended exactly when the period began is left out; a naive datetime is read as UTC; a resource held for
    the whole period is 100% and never more; with no resources and no allocations every figure is zero and the rows are empty.**
    """
    edge = compute_utilization(
        resources=[ResourceRef(1, "edge")],
        spans=[AllocationSpan(1, _at("2026-04-01", 0), actual_checkin=NOW - timedelta(days=7), status="released")],
        period_days=7, now=NOW,
    )
    naive = compute_utilization(
        resources=[ResourceRef(1, "naive")],
        spans=[AllocationSpan(1, datetime(2026, 5, 4, 8, 0), actual_checkin=datetime(2026, 5, 4, 10, 0), status="released")],
        period_days=7, now=NOW,
    )
    full = compute_utilization(
        resources=[ResourceRef(1, "always")],
        spans=[AllocationSpan(1, _at("2026-01-01", 0), status="active")],
        period_days=7, now=NOW,
    )
    nothing = compute_utilization(resources=[], spans=[], period_days=30, now=NOW)

    testbase.assert_equal(
        (
            edge.allocations, naive.rows[0].hours_in_use, full.rows[0].percent_in_use, full.rows[0].hours_in_use,
            (nothing.rows, nothing.allocations, nothing.resources_total, nothing.hours_in_use, nothing.average_hours, nothing.peak_at_once),
        ),
        (0, 2.0, 100.0, 168.0, ([], 0, 0, 0.0, 0.0, 0)),
    )
    return


def _seed_resources(tag: str) -> Dict[str, Any]:
    """Two resources: one held for 2 h then again for the last hour (still held), and one whose name would be a formula."""
    session = adm.open_db_session()
    try:
        busy = Resource(name="util-" + tag, resource_type="device", metadata_json={}, sensitive_fields=[])
        formula = Resource(name="=SUM(1,1)-" + tag, resource_type="device", metadata_json={}, sensitive_fields=[])
        session.add(busy)
        session.add(formula)
        session.flush()
        now = utc_now()
        session.add(Allocation(
            resource_id=busy.id, user_id=uuid.uuid4(), mode="exclusive", status="released",
            checkout_time=now - timedelta(hours=5), actual_checkin=now - timedelta(hours=3), metadata_snapshot={},
        ))
        session.add(Allocation(
            resource_id=busy.id, user_id=uuid.uuid4(), mode="exclusive", status="active",
            checkout_time=now - timedelta(hours=1), metadata_snapshot={},
        ))
        session.commit()
        return {"busy": "util-" + tag, "formula": "=SUM(1,1)-" + tag}
    finally:
        session.close()


def _rows(body: str) -> List[Dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body)))


def test_the_page_and_the_spreadsheet_report_the_same_resources():
    """
    **Feature: lab utilization report (ORG-F22)**
    **Property: the page answers 200 with the period choices, the summary, a Download CSV link that keeps the period, and a row for the
    resource that is in use now; ``format=csv`` answers 200 ``text/csv`` as an attachment with the documented header and that resource at 2
    allocations and about 3 hours; a resource named like a formula is written as text; an unknown ``days`` reads as 30.**
    """
    cookies = adm.admin_cookies()
    names = _seed_resources(uuid.uuid4().hex[:8])

    page = adm.get(path="/resources/allocations/utilization", cookies=cookies, query={"days": "7"})
    bogus = adm.get(path="/resources/allocations/utilization", cookies=cookies, query={"days": "banana"})
    export = adm.get(path="/resources/allocations/utilization", cookies=cookies, query={"days": "7", "format": "csv"})
    rows = {row["resource"]: row for row in _rows(export.text)}
    busy = rows[names["busy"]]

    testbase.assert_equal(
        (
            page.status_code, "last 7 days" in page.text, 'data-role="summary"' in page.text, names["busy"] in page.text,
            "in use now" in page.text, "?days=7&amp;format=csv" in page.text or "?days=7&format=csv" in page.text,
            "last 30 days" in bogus.text,
            export.status_code, (export.header("Content-Type") or "").split(";")[0],
            (export.header("Content-Disposition") or "").startswith('attachment; filename="pychestrate-utilization-7d-'),
            list(rows[names["busy"]].keys()),
            busy["allocations"], 2.9 <= float(busy["hours_in_use"]) <= 3.1, busy["period_days"], bool(busy["last_checked_out"]),
            "'" + names["formula"] in rows,
        ),
        (
            200, True, True, True, True, True, True,
            200, "text/csv", True, list(report_module.EXPORT_COLUMNS),
            "2", True, "7", True, True,
        ),
    )
    return


def test_a_signed_out_visitor_and_a_person_without_the_permission_get_no_report():
    """
    **Feature: lab utilization report (ORG-F22)**
    **Property: with no session the page and the export redirect to sign in and carry no data; a signed-in user without the resources
    permission is turned away from both (a redirect with a message, no CSV).**
    """
    _seed_resources(uuid.uuid4().hex[:8])
    viewer = login_as(wsgi_app=ensure_app().wsgi_app, user=ensure_seeded_viewer())

    signed_out_page = adm.get(path="/resources/allocations/utilization", cookies={})
    signed_out_csv = adm.get(path="/resources/allocations/utilization", cookies={}, query={"format": "csv"})
    refused_page = adm.get(path="/resources/allocations/utilization", cookies=viewer)
    refused_csv = adm.get(path="/resources/allocations/utilization", cookies=viewer, query={"format": "csv"})

    testbase.assert_equal(
        (
            signed_out_page.status_code in (302, 303), signed_out_csv.status_code in (302, 303),
            "text/csv" in (signed_out_csv.header("Content-Type") or ""),
            refused_page.status_code in (302, 303, 403), refused_csv.status_code in (302, 303, 403),
            "text/csv" in (refused_csv.header("Content-Type") or ""), "util-" in refused_csv.text,
        ),
        (True, True, False, True, True, False, False),
    )
    return
