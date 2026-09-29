"""
.. module:: test_p31zc_reservation_filters_and_zone_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The reservation list filters by status and reads its times
               in the viewer's zone, and reservation pages show times in
               that zone (RES-43).

.. moduleauthor:: Code Craft AI LLC

The reservation forms took times in the browser's zone while every list
showed UTC, and the list had no status filter, so cancelled reservations
stayed in it for good. The list now hides finished reservations unless
asked (Pending and active is the default; Pending, Active, Completed,
Cancelled and All are choices), reads its start and end filters in the
viewer's zone (the same ``tz`` the forms use), and keeps every filter
when paging. Times on the reservation pages and the resource page are
written so the page's script shows them in the viewer's zone; without
script they stay UTC and say so.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from datetime import datetime, timezone
from typing import Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation.templating import local_datetime_filter

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    get,
    post_form,
)


def _device(cookies: Dict[str, str]) -> str:
    response = post_form(
        path="/resources/create",
        fields={"name": "rf-" + uuid.uuid4().hex[:8], "resource_type": "device", "pool_id": "", "description": "",
                "capacity": "1", "metadata": "{}"},
        cookies=cookies,
    )
    return re.search(r"/resources/(\d+)", response.header("Location") or "").group(1)


def _reserve(cookies: Dict[str, str], device_id: str, start: str, end: str, tz: str = "UTC") -> str:
    response = post_form(
        path="/resources/reservations/create",
        fields={"resource_id": device_id, "start_time": start, "end_time": end, "tz": tz, "mode": "exclusive",
                "job_id": "", "reason": ""},
        cookies=cookies,
    )
    found = re.search(r"/resources/reservations/(\d+)", response.header("Location") or "")
    testbase.assert_true(found is not None, "reservation not made: {} {}".format(response.status_code, response.text[:200]))
    return found.group(1)


def _listed(cookies: Dict[str, str], **query: str) -> List[str]:
    page = get(path="/resources/reservations", cookies=cookies, query=query).text
    return re.findall(r'<td><a href="/resources/reservations/(\d+)">\1</a></td>', page)


def _page(cookies: Dict[str, str], **query: str) -> str:
    return html.unescape(get(path="/resources/reservations", cookies=cookies, query=query).text)


def _two_reservations() -> Tuple[Dict[str, str], str, str, str]:
    """A device with a pending reservation and a cancelled one; returns ``(cookies, device, pending id, cancelled id)``."""
    admin = admin_cookies()
    device = _device(admin)
    pending = _reserve(admin, device, "2030-06-15T09:00", "2030-06-15T10:00")
    cancelled = _reserve(admin, device, "2030-06-16T09:00", "2030-06-16T10:00")
    post_form(path="/resources/reservations/{}/cancel".format(cancelled), fields={}, cookies=admin)
    return (admin, device, pending, cancelled)


def test_the_list_hides_cancelled_reservations_unless_asked():
    """
    **Feature: reservation list filters (RES-43)**
    **Property: by default a cancelled reservation is not listed; the
    Cancelled filter lists only it; All lists both; Pending lists only
    the pending one; an unknown status is read as the default.**
    """
    admin, device, pending, cancelled = _two_reservations()

    testbase.assert_equal(
        (_listed(admin, resource_id=device), _listed(admin, resource_id=device, status="cancelled"),
         sorted(_listed(admin, resource_id=device, status="all")), _listed(admin, resource_id=device, status="pending"),
         _listed(admin, resource_id=device, status="active"), _listed(admin, resource_id=device, status="bogus")),
        ([pending], [cancelled], sorted([pending, cancelled]), [pending], [], [pending]),
    )
    return


def test_the_status_choice_is_offered_and_remembered():
    """
    **Feature: reservation list filters (RES-43)**
    **Property: the filter bar has a status select with Pending and
    active, Pending, Active, Completed, Cancelled and All, and the chosen
    one is selected after filtering.**
    """
    admin = admin_cookies()
    page = _page(admin, status="cancelled")
    select = re.search(r'<select name="status".*?</select>', page, re.S)
    options = re.findall(r'<option value="([a-z]+)"\s*(selected)?', select.group(0)) if select is not None else []

    testbase.assert_equal(
        ([value for value, _mark in options], [value for value, mark in options if mark]),
        (["open", "pending", "active", "completed", "cancelled", "all"], ["cancelled"]),
    )
    return


def test_an_empty_default_list_points_at_the_finished_ones():
    """
    **Feature: reservation list filters (RES-43)**
    **Property: when the chosen device has only a cancelled reservation,
    the default list says finished ones are hidden and links to show them
    with the device filter kept; following it lists the cancelled one; a
    status filter that matches nothing does not offer that link.**
    """
    admin = admin_cookies()
    device = _device(admin)
    cancelled = _reserve(admin, device, "2030-07-01T09:00", "2030-07-01T10:00")
    post_form(path="/resources/reservations/{}/cancel".format(cancelled), fields={}, cookies=admin)
    default_page = _page(admin, resource_id=device)
    link = re.search(r'<a href="([^"]*)" data-role="show-finished"', default_page)
    query = parse_qs(urlparse(link.group(1)).query) if link is not None else {}
    empty_status = _page(admin, resource_id=device, status="active")

    testbase.assert_equal(
        ("Finished ones are hidden" in default_page, query.get("status"), query.get("resource_id") == [device],
         _listed(admin, resource_id=device, status="all"), 'data-role="show-finished"' in empty_status,
         "No reservations match the current filters" in empty_status),
        (True, ["all"], True, [cancelled], False, True),
    )
    return


def test_paging_keeps_the_status_the_end_filter_and_the_zone():
    """
    **Feature: reservation list filters (RES-43)**
    **Property: the Next link of a paged list carries the status, both
    time filters and the zone (it dropped the end filter before), so page
    two is the same list.**
    """
    admin = admin_cookies()
    device = _device(admin)
    _reserve(admin, device, "2030-08-01T09:00", "2030-08-01T10:00")
    _reserve(admin, device, "2030-08-02T09:00", "2030-08-02T10:00")
    page = _page(admin, resource_id=device, status="all", per_page="1", start_after="2030-01-01T00:00",
                 end_before="2031-01-01T00:00", tz="America/Los_Angeles")
    found = re.search(r'<a href="([^"]*)" rel="next"', page)
    query = parse_qs(urlparse(found.group(1)).query) if found is not None else {}

    testbase.assert_equal(
        (found is not None, query.get("status"), query.get("end_before"), query.get("start_after"), query.get("tz"),
         query.get("resource_id") == [device]),
        (True, ["all"], ["2031-01-01T00:00"], ["2030-01-01T00:00"], ["America/Los_Angeles"], True),
    )
    return


def test_the_time_filters_are_read_in_the_viewers_zone():
    """
    **Feature: reservation list filters (RES-43)**
    **Property: a reservation starting at 20:00 UTC (13:00 Pacific) is
    listed for "starting after 14:00" typed in UTC and not when the same
    14:00 is typed in Pacific time (21:00 UTC); the typed value is kept in
    the input and the zone is carried in the hidden field.**
    """
    admin = admin_cookies()
    device = _device(admin)
    reservation = _reserve(admin, device, "2030-06-15T13:00", "2030-06-15T14:00", tz="America/Los_Angeles")
    in_utc = _listed(admin, resource_id=device, start_after="2030-06-15T14:00")
    in_pacific = _listed(admin, resource_id=device, start_after="2030-06-15T14:00", tz="America/Los_Angeles")
    page = _page(admin, resource_id=device, start_after="2030-06-15T14:00", tz="America/Los_Angeles")

    testbase.assert_equal(
        (in_utc, in_pacific, 'name="start_after"' in page and 'value="2030-06-15T14:00"' in page,
         bool(re.search(r'<input type="hidden" name="tz" value="America/Los_Angeles"', page))),
        ([reservation], [], True, True),
    )
    return


def test_an_unknown_zone_in_the_filter_is_read_as_utc_and_does_not_fail():
    """
    **Feature: reservation list filters (RES-43)**
    **Property: a tz that is not a zone this server knows answers 200 and
    is read as UTC, giving the same list as no tz.**
    """
    admin = admin_cookies()
    device = _device(admin)
    reservation = _reserve(admin, device, "2030-06-15T09:00", "2030-06-15T10:00")
    response = get(path="/resources/reservations", cookies=admin,
                   query={"resource_id": device, "start_after": "2030-06-15T00:00", "tz": "Mars/Olympus"})

    testbase.assert_equal(
        (response.status_code, reservation in re.findall(r'<td><a href="/resources/reservations/(\d+)">\1</a></td>', response.text)),
        (200, True),
    )
    return


def test_times_on_the_reservation_pages_are_marked_for_the_viewers_zone():
    """
    **Feature: viewer's zone everywhere (RES-43)**
    **Property: the list, the reservation page and the resource page write
    their times as <time> elements with an explicit UTC offset that the
    page's script rewrites into the viewer's zone, and include that
    script; the server text stays UTC and says so, which is what shows
    without script.**
    """
    admin = admin_cookies()
    device = _device(admin)
    reservation = _reserve(admin, device, "2030-06-15T09:00", "2030-06-15T10:00")
    pages = {
        "list": _page(admin, resource_id=device),
        "detail": _page_at(admin, "/resources/reservations/{}".format(reservation)),
        "resource": _page_at(admin, "/resources/{}".format(device)),
    }
    marked = '<time data-pyc-local datetime="2030-06-15T09:00:00+00:00" title="2030-06-15T09:00:00+00:00">2030-06-15 09:00 UTC</time>'
    marked_seconds = 'data-pyc-local data-pyc-seconds datetime="2030-06-15T09:00:00+00:00"'

    testbase.assert_equal(
        (marked in pages["list"], marked_seconds in pages["detail"], "data-pyc-local" in pages["resource"],
         all("time[data-pyc-local]" in page for page in pages.values())),
        (True, True, True, True),
    )
    return


def _page_at(cookies: Dict[str, str], path: str) -> str:
    return html.unescape(get(path=path, cookies=cookies).text)


def test_the_forms_no_longer_say_reservation_pages_list_times_in_utc():
    """
    **Feature: viewer's zone everywhere (RES-43)**
    **Property: the create form's zone note, and the script that fills it
    in, no longer claim that reservation pages list times in UTC.**
    """
    admin = admin_cookies()
    page = _page_at(admin, "/resources/reservations/create")

    testbase.assert_equal(
        ("reservation pages list times in UTC" in page, "your browser's time zone" in page),
        (False, True),
    )
    return


def test_the_local_time_filter_gives_naive_values_an_explicit_offset_and_keeps_the_placeholder():
    """
    **Feature: viewer's zone everywhere (RES-43)**
    **Property: a naive datetime (how the database returns them) is
    rendered as UTC with a +00:00 offset so the script cannot read it as
    local time; seconds are marked; None renders the placeholder.**
    """
    naive = datetime(2030, 6, 15, 9, 5, 7)
    aware = datetime(2030, 6, 15, 9, 5, 7, tzinfo=timezone.utc)
    rendered = str(local_datetime_filter(naive))

    testbase.assert_equal(
        (rendered, str(local_datetime_filter(aware, True)), local_datetime_filter(None, False, "None set"), local_datetime_filter("text")),
        ('<time data-pyc-local datetime="2030-06-15T09:05:07+00:00" title="2030-06-15T09:05:07+00:00">2030-06-15 09:05 UTC</time>',
         '<time data-pyc-local data-pyc-seconds datetime="2030-06-15T09:05:07+00:00" title="2030-06-15T09:05:07+00:00">2030-06-15 09:05:07 UTC</time>',
         "None set", "text"),
    )
    return
