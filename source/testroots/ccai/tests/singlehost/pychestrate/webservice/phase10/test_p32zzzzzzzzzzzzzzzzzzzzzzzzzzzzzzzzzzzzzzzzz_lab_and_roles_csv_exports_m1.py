"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_lab_and_roles_csv_exports_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Roles, resources, reservations and allocation history download as spreadsheets (ORG-F22).

.. moduleauthor:: Code Craft AI LLC

Runs, the audit log, the users list and the utilization report already download as CSV. A lab manager or an auditor also wants the roles (who may
do what), the device inventory, the bookings and the allocation history without reading them a page at a time. Each list now has a Download CSV
button and ``?format=csv`` that returns every row the page's filters match, up to 5,000 (cut and flagged beyond that), with cells a spreadsheet
cannot read as a formula, behind the same permission as the page. A device's metadata, which can hold addresses and credentials, is never
exported.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import csv
import io
import uuid

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

from ccai import testbase

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import Allocation, Reservation, Resource
from ccai.pychestrate.webservice.webinterface.blueprints.resources import exports

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    ensure_seeded_viewer,
    login_as,
)


def _rows(body: str) -> List[Dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body)))


def _kind(response: Any) -> str:
    return (response.header("Content-Type") or "").split(";")[0]


def test_every_page_of_a_list_is_read_and_a_list_over_the_limit_is_cut_and_flagged():
    """
    **Feature: spreadsheet exports (ORG-F22)**
    **Property: ``collect_rows`` reads page after page until the total is reached; a list of exactly the limit is not flagged, one more is
    (and is cut to the limit); an empty list gives no rows; a manager that reports a total larger than it returns stops instead of looping.**
    """
    def paged(total: int) -> Any:
        def fetch(offset: int, limit: int) -> Tuple[List[int], int]:
            return list(range(offset, min(offset + limit, total))), total
        return fetch

    exact = exports.collect_rows(paged(exports.EXPORT_MAX_ROWS))
    over = exports.collect_rows(paged(exports.EXPORT_MAX_ROWS + 1))
    small = exports.collect_rows(paged(450))
    empty = exports.collect_rows(paged(0))
    liar = exports.collect_rows(lambda offset, limit: ([] if offset >= 3 else [offset], 99))

    testbase.assert_equal(
        (
            (len(exact[0]), exact[1]), (len(over[0]), over[1]), (len(small[0]), small[1], small[0][-1]), (empty[0], empty[1]), (len(liar[0]), liar[1]),
        ),
        (
            (exports.EXPORT_MAX_ROWS, False), (exports.EXPORT_MAX_ROWS, True), (450, False, 449), ([], False), (3, False),
        ),
    )
    return


def test_the_filters_become_the_buttons_address_and_a_format_is_recognised():
    """
    **Feature: spreadsheet exports (ORG-F22)**
    **Property: ``export_url`` keeps the filters that are set (repeated ``tags`` too), leaves out empty ones and ends with ``format=csv``;
    ``wants_csv`` accepts ``csv`` in any case and nothing else.**
    """
    url = exports.export_url("/resources/list", [("pool_id", 3), ("search", ""), ("resource_type", None), ("tags", "lab"), ("tags", "usb 3")])

    testbase.assert_equal(
        (url, [exports.wants_csv(value) for value in ("csv", "CSV", " csv ", "json", "", None)]),
        ("/resources/list?pool_id=3&tags=lab&tags=usb+3&format=csv", [True, True, True, False, False, False]),
    )
    return


def test_records_carry_only_what_the_page_shows_and_never_a_devices_metadata():
    """
    **Feature: spreadsheet exports (ORG-F22)**
    **Property: a resource record has the documented columns, sorted joined tags and no metadata (a secret in it is nowhere in the row); an
    allocation or reservation with missing optional values has empty cells, not "None".**
    """
    resource = SimpleNamespace(
        name="bench", resource_type="device", pool_name=None, health_status="online", current_allocations=1, capacity=2, tags=["usb", "lab"],
        description="desk", created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc), metadata={"password": "hunter2"},
    )
    allocation = SimpleNamespace(
        id=7, resource_name="bench", resource_type="device", username=None, job_id=None, mode="exclusive", status="active",
        checkout_time=datetime(2026, 1, 2, tzinfo=timezone.utc), expected_checkin=None, actual_checkin=None, duration_minutes=None,
        reason=None, forced_by=None, force_reason=None,
    )
    reservation = SimpleNamespace(
        id=9, resource_name="bench", username="ada", job_id=None, mode="shared", status="pending", start_time=datetime(2026, 1, 3, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 4, tzinfo=timezone.utc), reason=None, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    record = exports.resource_records([resource])[0]
    allocated = exports.allocation_records([allocation])[0]
    reserved = exports.reservation_records([reservation])[0]

    testbase.assert_equal(
        (
            list(record.keys()), record["tags"], "hunter2" in str(record), record["pool"],
            list(allocated.keys()) == list(exports.ALLOCATION_COLUMNS), "None" in str(allocated), allocated["duration_minutes"],
            list(reserved.keys()) == list(exports.RESERVATION_COLUMNS), reserved["user"], reserved["reason"],
        ),
        (list(exports.RESOURCE_COLUMNS), "lab; usb", False, "", True, False, "", True, "ada", ""),
    )
    return


def _seed(tag: str) -> Dict[str, Any]:
    """A device (with a secret in its metadata and a formula for a name), an allocation that ended, and a reservation."""
    session = adm.open_db_session()
    try:
        plain = Resource(
            name="csvbench-" + tag, resource_type="device", description="lab desk", metadata_json={"password": "hunter2-" + tag}, sensitive_fields=["password"],
        )
        formula = Resource(name="=1+1-" + tag, resource_type="device", description="x", metadata_json={}, sensitive_fields=[])
        other = Resource(name="csvother-" + tag, resource_type="device", description="y", metadata_json={}, sensitive_fields=[])
        session.add_all([plain, formula, other])
        session.flush()
        now = utc_now()
        session.add(Allocation(
            resource_id=plain.id, user_id=uuid.uuid4(), mode="exclusive", status="released", checkout_time=now - timedelta(days=2),
            actual_checkin=now - timedelta(days=1), duration_minutes=1440, reason='=HYPERLINK("http://x","y")', metadata_snapshot={},
        ))
        session.add(Allocation(
            resource_id=other.id, user_id=uuid.uuid4(), mode="shared", status="released", checkout_time=now - timedelta(days=3),
            actual_checkin=now - timedelta(days=2), duration_minutes=60, metadata_snapshot={},
        ))
        session.add(Reservation(
            resource_id=plain.id, user_id=uuid.uuid4(), start_time=now + timedelta(days=1), end_time=now + timedelta(days=1, hours=2),
            mode="exclusive", status="pending", reason="+cmd booking",
        ))
        session.commit()
        return {"plain": plain.name, "formula": formula.name, "other": other.name, "plain_id": plain.id, "secret": "hunter2-" + tag}
    finally:
        session.close()


def test_the_resource_inventory_downloads_filtered_without_metadata_and_with_formulas_defused():
    """
    **Feature: spreadsheet exports (ORG-F22)**
    **Property: ``/resources/list?format=csv`` answers 200 ``text/csv`` as an attachment named for resources, with the documented header and a
    row per device; ``search`` narrows it and ``per_page`` does not limit it; a device named like a formula comes back as text; a device's
    secret metadata is nowhere in the file.**
    """
    cookies = adm.admin_cookies()
    seeded = _seed(uuid.uuid4().hex[:8])
    everything = adm.get(path="/resources/list", cookies=cookies, query={"format": "csv", "per_page": "1"})
    narrowed = adm.get(path="/resources/list", cookies=cookies, query={"format": "csv", "search": "csvbench-"})
    names = {row["name"]: row for row in _rows(everything.text)}
    narrowed_names = [row["name"] for row in _rows(narrowed.text)]

    testbase.assert_equal(
        (
            everything.status_code, _kind(everything), (everything.header("Content-Disposition") or "").startswith('attachment; filename="pychestrate-resources-'),
            list(_rows(everything.text)[0].keys()), seeded["plain"] in names, "'" + seeded["formula"] in names, seeded["other"] in names,
            seeded["secret"] in everything.text, seeded["plain"] in narrowed_names, seeded["other"] in narrowed_names,
        ),
        (200, "text/csv", True, list(exports.RESOURCE_COLUMNS), True, True, True, False, True, False),
    )
    return


def test_allocation_history_and_reservations_download_with_their_filters():
    """
    **Feature: spreadsheet exports (ORG-F22)**
    **Property: the allocation history CSV holds each allocation with its dates and status, narrows to one device with ``resource_id`` and writes
    a formula-like reason as text; the reservations CSV holds the pending booking with its window and writes a ``+...`` reason as text.**
    """
    cookies = adm.admin_cookies()
    seeded = _seed(uuid.uuid4().hex[:8])
    history = adm.get(path="/resources/allocations/history", cookies=cookies, query={"format": "csv"})
    one_device = adm.get(path="/resources/allocations/history", cookies=cookies, query={"format": "csv", "resource_id": str(seeded["plain_id"])})
    reservations = adm.get(path="/resources/reservations", cookies=cookies, query={"format": "csv"})
    mine = [row for row in _rows(history.text) if row["resource"] == seeded["plain"]]
    only = _rows(one_device.text)
    booked = [row for row in _rows(reservations.text) if row["resource"] == seeded["plain"]]

    testbase.assert_equal(
        (
            history.status_code, _kind(history), (history.header("Content-Disposition") or "").startswith('attachment; filename="pychestrate-allocation-history-'),
            list(_rows(history.text)[0].keys()) == list(exports.ALLOCATION_COLUMNS), len(mine), mine[0]["status"], mine[0]["duration_minutes"],
            mine[0]["reason"], [row["resource"] for row in only],
            reservations.status_code, _kind(reservations), list(_rows(reservations.text)[0].keys()) == list(exports.RESERVATION_COLUMNS),
            len(booked), booked[0]["status"], booked[0]["reason"],
        ),
        (
            200, "text/csv", True, True, 1, "released", "1440", "'=HYPERLINK(\"http://x\",\"y\")", [seeded["plain"]],
            200, "text/csv", True, 1, "pending", "'+cmd booking",
        ),
    )
    return


def test_roles_download_with_their_permissions_and_a_formula_description_is_text():
    """
    **Feature: spreadsheet exports (ORG-F22)**
    **Property: ``/admin/roles?format=csv`` lists the built-in roles (type "built-in", a permission count that matches the keys, the keys
    themselves) and a custom role made here (type "custom", exactly the permission keys it was given, assigned 0), writes a ``=...``
    description as text, and is named for roles.**
    """
    cookies = adm.admin_cookies()
    name = "csvrole-" + uuid.uuid4().hex[:8]
    created = adm.post_form(
        path="/admin/roles/create", cookies=cookies,
        fields=[("name", name), ("description", "=1+1"), ("permission_keys", "system:builds.read"), ("permission_keys", "system:runs.read")],
    )
    export = adm.get(path="/admin/roles", cookies=cookies, query={"format": "csv"})
    rows = {row["name"]: row for row in _rows(export.text)}
    custom = rows[name]
    built_in = [row for row in rows.values() if row["type"] == "built-in"]

    testbase.assert_equal(
        (
            created.status_code in (302, 303), export.status_code, _kind(export), (export.header("Content-Disposition") or "").startswith('attachment; filename="pychestrate-roles-'),
            list(_rows(export.text)[0].keys()), custom["type"], custom["permissions"], custom["permission_keys"], custom["assigned"], custom["description"],
            len(built_in) >= 2, all(int(row["permissions"]) == len([key for key in row["permission_keys"].split("; ") if key]) for row in rows.values()),
        ),
        (
            True, 200, "text/csv", True, ["name", "description", "type", "permissions", "assigned", "permission_keys"], "custom", "2",
            "system:builds.read; system:runs.read", "0", "'=1+1", True, True,
        ),
    )
    return


def test_a_signed_in_person_without_the_permission_gets_no_file_and_readers_get_the_buttons():
    """
    **Feature: spreadsheet exports (ORG-F22)**
    **Property: a user without the resources and roles permissions is turned away from every export (a redirect or 403, never CSV, never a
    seeded name); a signed-out visitor is sent to sign in; each of the four pages shows a Download CSV button to an administrator, and the
    button on the resources page carries its search.**
    """
    cookies = adm.admin_cookies()
    seeded = _seed(uuid.uuid4().hex[:8])
    viewer = login_as(wsgi_app=ensure_app().wsgi_app, user=ensure_seeded_viewer())
    paths = ["/resources/list", "/resources/allocations/history", "/resources/reservations", "/admin/roles"]
    refused = [adm.get(path=path, cookies=viewer, query={"format": "csv"}) for path in paths]
    signed_out = [adm.get(path=path, cookies={}, query={"format": "csv"}) for path in paths]
    pages = [adm.get(path=path, cookies=cookies).text for path in paths]
    searched = adm.get(path="/resources/list", cookies=cookies, query={"search": "bench x"}).text

    testbase.assert_equal(
        (
            [response.status_code in (302, 303, 403) for response in refused], [_kind(response) == "text/csv" for response in refused],
            [seeded["plain"] in response.text for response in refused],
            [response.status_code in (302, 303) for response in signed_out],
            ['data-role="download-csv"' in page for page in pages],
            "search=bench+x&amp;format=csv" in searched,
        ),
        ([True] * 4, [False] * 4, [False] * 4, [True] * 4, [True] * 4, True),
    )
    return
