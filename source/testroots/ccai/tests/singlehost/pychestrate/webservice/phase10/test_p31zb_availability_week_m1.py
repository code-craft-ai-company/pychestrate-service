"""
.. module:: test_p31zb_availability_week_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A week of free and busy time, laid out in the viewer's
               zone (RES-43).

.. moduleauthor:: Code Craft AI LLC

There was no way to see when a lab's resources were free: finding a gap
meant reading the reservation list a row at a time. The new Availability
page draws a Monday-to-Monday week, one row per resource of a pool, with
the reservations and the current check-outs as blocks and an ordinary
table of the same bookings below it. The week is laid out in the
viewer's zone: the page's script keeps the browser's zone in a cookie and
reloads once, and an explicit ``tz`` in the address wins over the cookie.
These tests cover the layout (pure functions, including a week with a
daylight-saving change) and the page.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.blueprints.resources import availability_view
from ccai.pychestrate.webservice.webinterface.blueprints.resources.availability_view import (
    KIND_CHECKED_OUT,
    KIND_RESERVED_EXCLUSIVE,
    KIND_RESERVED_SHARED,
    build_rows,
    week_window,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    get,
    post_form,
)


LOS_ANGELES = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc


def _at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _reservation(resource_id: int, start: datetime, end: datetime, *, mode: str = "exclusive", who: str = "quinn",
                 reservation_id: int = 1) -> Any:
    return SimpleNamespace(id=reservation_id, resource_id=resource_id, username=who, job_id=None, mode=mode,
                           status="pending", start_time=start, end_time=end)


def _resource(resource_id: int = 1, name: str = "lab-1") -> Any:
    return SimpleNamespace(id=resource_id, name=name, health_status="online")


# ---------------------------------------------------------------------------
# The layout
# ---------------------------------------------------------------------------


def test_a_week_runs_monday_to_monday_in_the_viewers_zone():
    """
    **Feature: availability week (RES-43)**
    **Property: the week that contains a Wednesday starts on that
    Monday's local midnight and ends on the next Monday's; in Pacific
    time that is seven hours after UTC midnight in summer; the seven day
    columns cover the week without a gap.**
    """
    window = week_window(anchor=date(2026, 9, 30), zone=LOS_ANGELES, zone_name="America/Los_Angeles", now=_at(2026, 9, 30, 12))
    edges = [(round(day.left_percent + day.width_percent, 6)) for day in window.days]

    testbase.assert_equal(
        (window.monday, window.start_utc, window.end_utc, len(window.days), edges[-1], window.days[0].left_percent,
         [day.label for day in window.days][:2], window.previous_monday, window.next_monday),
        (date(2026, 9, 28), _at(2026, 9, 28, 7), _at(2026, 10, 5, 7), 7, 100.0, 0.0,
         ["Mon 28 Sep", "Tue 29 Sep"], date(2026, 9, 21), date(2026, 10, 5)),
    )
    return


def test_a_week_with_a_daylight_saving_change_is_a_real_hour_longer_or_shorter():
    """
    **Feature: availability week (RES-43)**
    **Property: the week that contains the autumn clock change is 169
    hours, the spring one 167, and an ordinary week 168; the day columns
    still add up to the whole week, with the changed day wider or
    narrower.**
    """
    def hours(anchor: date) -> Tuple[float, float, float]:
        window = week_window(anchor=anchor, zone=LOS_ANGELES, zone_name="America/Los_Angeles", now=_at(2026, 1, 1))
        widths = [day.width_percent for day in window.days]
        return (window.total_seconds / 3600, round(sum(widths), 6), max(widths) - min(widths))

    autumn, spring, ordinary = hours(date(2026, 11, 1)), hours(date(2026, 3, 8)), hours(date(2026, 9, 30))

    testbase.assert_equal(
        (autumn[0], spring[0], ordinary[0], autumn[1], spring[1], autumn[2] > 0.1, spring[2] > 0.1, ordinary[2] < 0.000001),
        (169.0, 167.0, 168.0, 100.0, 100.0, True, True, True),
    )
    return


def test_now_is_marked_only_inside_the_week_and_today_is_the_local_day():
    """
    **Feature: availability week (RES-43)**
    **Property: the now marker sits where now falls in the week and is
    absent for a week that does not contain it; today's column is the
    viewer's local day, which is already Wednesday in Tokyo when it is
    still Tuesday in UTC.**
    """
    now = _at(2026, 9, 29, 20, 0)
    inside = week_window(anchor=date(2026, 9, 29), zone=UTC, zone_name="UTC", now=now)
    outside = week_window(anchor=date(2026, 10, 6), zone=UTC, zone_name="UTC", now=now)
    tokyo = week_window(anchor=date(2026, 9, 29), zone=ZoneInfo("Asia/Tokyo"), zone_name="Asia/Tokyo", now=now)

    testbase.assert_equal(
        (round(inside.now_percent, 3), outside.now_percent,
         [day.label for day in inside.days if day.is_today], [day.label for day in tokyo.days if day.is_today]),
        (round((1 * 24 + 20) / 168 * 100, 3), None, ["Tue 29 Sep"], ["Wed 30 Sep"]),
    )
    return


def test_a_reservation_is_placed_by_its_share_of_the_week_and_clipped_at_the_edges():
    """
    **Feature: availability week (RES-43)**
    **Property: a reservation from noon Tuesday to noon Wednesday (UTC)
    starts 36 hours into the week and is 24 hours wide, as shares of the
    168-hour week; one that began the week before is clipped to the
    week's start and marked as starting before it; a reservation of
    another resource is on that resource's row only; one outside the
    week is left out.**
    """
    window = week_window(anchor=date(2026, 9, 29), zone=UTC, zone_name="UTC", now=_at(2026, 9, 29))
    rows = build_rows(
        resources=[_resource(1, "a"), _resource(2, "b")],
        reservations=[
            _reservation(1, _at(2026, 9, 29, 12), _at(2026, 9, 30, 12), reservation_id=1),
            _reservation(1, _at(2026, 9, 20, 0), _at(2026, 9, 29, 6), reservation_id=2),
            _reservation(2, _at(2026, 10, 12, 0), _at(2026, 10, 13, 0), reservation_id=3),
            _reservation(1, _at(2026, 10, 12, 0), _at(2026, 10, 13, 0), reservation_id=4),
        ],
        holders={}, window=window,
    )
    first = next(block for block in rows[0].blocks if block.reservation_id == 1)
    clipped = next(block for block in rows[0].blocks if block.reservation_id == 2)

    testbase.assert_equal(
        (round(first.left_percent, 4), round(first.width_percent, 4), first.kind,
         clipped.left_percent, clipped.starts_before_week, first.starts_before_week,
         sorted(block.reservation_id for block in rows[0].blocks), rows[1].blocks),
        (round(36 / 168 * 100, 4), round(24 / 168 * 100, 4), KIND_RESERVED_EXCLUSIVE,
         0.0, True, False, [1, 2], []),
    )
    return


def test_a_shared_reservation_is_marked_shared_and_overlapping_blocks_get_their_own_lines():
    """
    **Feature: availability week (RES-43)**
    **Property: a shared reservation has the shared kind; two that
    overlap are drawn on two lines so neither hides the other, and one
    that starts after the first ends goes back on the first line.**
    """
    window = week_window(anchor=date(2026, 9, 29), zone=UTC, zone_name="UTC", now=_at(2026, 9, 29))
    rows = build_rows(
        resources=[_resource()],
        reservations=[
            _reservation(1, _at(2026, 9, 29, 8), _at(2026, 9, 29, 12), mode="shared", reservation_id=1),
            _reservation(1, _at(2026, 9, 29, 10), _at(2026, 9, 29, 14), mode="shared", reservation_id=2),
            _reservation(1, _at(2026, 9, 29, 14), _at(2026, 9, 29, 16), mode="shared", reservation_id=3),
        ],
        holders={}, window=window,
    )
    lanes = {block.reservation_id: block.lane for block in rows[0].blocks}

    testbase.assert_equal(
        (lanes, rows[0].lanes, {block.kind for block in rows[0].blocks}),
        ({1: 0, 2: 1, 3: 0}, 2, {KIND_RESERVED_SHARED}),
    )
    return


def test_a_checkout_with_no_timeout_runs_to_the_end_of_the_week():
    """
    **Feature: availability week (RES-43)**
    **Property: a current check-out with a timeout ends there; one with
    no timeout is drawn to the end of the week and marked as continuing;
    both have the checked-out kind and their holder; one whose window is
    outside the week is left out.**
    """
    window = week_window(anchor=date(2026, 9, 29), zone=UTC, zone_name="UTC", now=_at(2026, 9, 29))
    rows = build_rows(
        resources=[_resource(1, "a"), _resource(2, "b"), _resource(3, "c")], reservations=[],
        holders={
            1: [{"username": "sam", "job_id": None, "checkout_time": _at(2026, 9, 29, 12), "expected_checkin": _at(2026, 9, 29, 18)}],
            2: [{"username": "kit", "job_id": "j", "checkout_time": _at(2026, 9, 30, 0), "expected_checkin": None}],
            3: [{"username": "old", "job_id": None, "checkout_time": _at(2026, 9, 1), "expected_checkin": _at(2026, 9, 2)}],
        },
        window=window,
    )
    timed, open_ended = rows[0].blocks[0], rows[1].blocks[0]

    testbase.assert_equal(
        (timed.kind, timed.who, round(timed.width_percent, 4), timed.ends_after_week,
         open_ended.kind, round(open_ended.left_percent + open_ended.width_percent, 4), open_ended.ends_after_week, open_ended.end,
         rows[2].blocks),
        (KIND_CHECKED_OUT, "sam", round(6 / 168 * 100, 4), False,
         KIND_CHECKED_OUT, 100.0, True, None, []),
    )
    return


def test_a_very_short_booking_is_still_wide_enough_to_see():
    """
    **Feature: availability week (RES-43)**
    **Property: a five-minute reservation is drawn no narrower than the
    minimum block width, and never runs off the right edge of the week.**
    """
    window = week_window(anchor=date(2026, 9, 29), zone=UTC, zone_name="UTC", now=_at(2026, 9, 29))
    rows = build_rows(
        resources=[_resource()],
        reservations=[_reservation(1, _at(2026, 10, 4, 23, 58), _at(2026, 10, 5, 0, 3))],
        holders={}, window=window,
    )
    block = rows[0].blocks[0]

    testbase.assert_equal(
        (block.width_percent >= availability_view.MINIMUM_BLOCK_PERCENT, block.left_percent + block.width_percent <= 100.0000001),
        (True, True),
    )
    return


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _pool(cookies: Dict[str, str]) -> Tuple[str, str]:
    name = "cal-pool-" + _suffix()
    response = post_form(path="/resources/pools/create", fields={"name": name, "description": ""}, cookies=cookies)
    return (re.search(r"/resources/pools/(\d+)", response.header("Location") or "").group(1), name)


def _device(cookies: Dict[str, str], pool_id: str = "", prefix: str = "cal") -> Tuple[str, str]:
    name = "{}-{}".format(prefix, _suffix())
    response = post_form(
        path="/resources/create",
        fields={"name": name, "resource_type": "device", "pool_id": pool_id, "description": "", "capacity": "1", "metadata": "{}"},
        cookies=cookies,
    )
    return (re.search(r"/resources/(\d+)", response.header("Location") or "").group(1), name)


def _reserve(cookies: Dict[str, str], device_id: str, start: str, end: str, *, mode: str = "exclusive", tz: str = "UTC") -> str:
    response = post_form(
        path="/resources/reservations/create",
        fields={"resource_id": device_id, "start_time": start, "end_time": end, "tz": tz, "mode": mode, "job_id": "", "reason": ""},
        cookies=cookies,
    )
    found = re.search(r"/resources/reservations/(\d+)", response.header("Location") or "")
    testbase.assert_true(found is not None, "reservation not made: {} {}".format(response.status_code, response.text[:200]))
    return found.group(1)


def _calendar(cookies: Dict[str, str], **query: str) -> str:
    response = get(path="/resources/reservations/calendar", cookies=cookies, query=query)
    testbase.assert_equal(response.status_code, 200)
    return html.unescape(response.text)


def _row_html(page: str, name: str) -> str:
    """The markup of the row of the resource called ``name`` (up to the next row), or an empty string."""
    for chunk in page.split('<div class="avail-row"')[1:]:
        if 'class="avail-name" title="{}"'.format(name) in chunk:
            return chunk
    return ""


def _blocks_in(row: str) -> List[str]:
    return re.findall(r'<span class="avail-block avail-([a-z-]+)"', row)


def test_the_availability_page_draws_a_reservation_on_its_resources_row_and_lists_it():
    """
    **Feature: availability week (RES-43)**
    **Property: a pending reservation next Tuesday shows as a block on
    its device's row (with the reserver's name) and as a line in the
    bookings table with its times in the chosen zone; a device with
    nothing booked has an empty row.**
    """
    admin = admin_cookies()
    pool_id, _pool_name = _pool(admin)
    busy_id, busy_name = _device(admin, pool_id)
    _free_id, free_name = _device(admin, pool_id)
    monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=7)
    tuesday = monday + timedelta(days=1)
    reservation_id = _reserve(admin, busy_id, "{}T09:00".format(tuesday), "{}T11:00".format(tuesday), tz="America/Los_Angeles")
    page = _calendar(admin, pool_id=pool_id, week=str(monday), tz="America/Los_Angeles")
    table = re.search(r'<table class="data-table" data-role="bookings">.*?</table>', page, re.S)
    table_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", table.group(0))) if table is not None else ""

    testbase.assert_equal(
        (_blocks_in(_row_html(page, busy_name)), _blocks_in(_row_html(page, free_name)),
         "{} 09:00 P".format(tuesday) in table_text and "{} 11:00 P".format(tuesday) in table_text,
         '/resources/reservations/{}"'.format(reservation_id) in page),
        (["reserved-exclusive"], [], True, True),
    )
    return


def test_a_pools_page_shows_only_that_pools_resources():
    """
    **Feature: availability week (RES-43)**
    **Property: choosing a pool lists that pool's devices as rows and no
    device of another pool.**
    """
    admin = admin_cookies()
    first_pool, _n1 = _pool(admin)
    second_pool, _n2 = _pool(admin)
    _id1, mine = _device(admin, first_pool)
    _id2, theirs = _device(admin, second_pool)
    page = _calendar(admin, pool_id=first_pool)

    testbase.assert_equal((_row_html(page, mine) != "", _row_html(page, theirs) == "", theirs in page), (True, True, False))
    return


def test_a_week_with_nothing_booked_says_everything_is_free():
    """
    **Feature: availability week (RES-43)**
    **Property: a pool with no reservations or check-outs in the week
    shows its rows and says everything shown is free, with no bookings
    table.**
    """
    admin = admin_cookies()
    pool_id, _name = _pool(admin)
    _device(admin, pool_id)
    page = _calendar(admin, pool_id=pool_id)

    testbase.assert_equal(
        ('data-role="all-free"' in page, 'data-role="bookings"' in page, 'data-role="availability-grid"' in page),
        (True, False, True),
    )
    return


def test_a_checked_out_device_is_drawn_as_checked_out_with_who_holds_it():
    """
    **Feature: availability week (RES-43)**
    **Property: a device the administrator has checked out for an hour
    shows a checked-out block this week, and the bookings table names the
    holder and says "Checked out".**
    """
    admin = admin_cookies()
    pool_id, _name = _pool(admin)
    device_id, device_name = _device(admin, pool_id)
    post_form(path="/resources/{}/checkout".format(device_id),
              fields={"mode": "exclusive", "job_id": "", "timeout_minutes": "60", "reason": "for the week view"}, cookies=admin)
    page = _calendar(admin, pool_id=pool_id)
    table = re.search(r'<table class="data-table" data-role="bookings">.*?</table>', page, re.S)

    testbase.assert_equal(
        (_blocks_in(_row_html(page, device_name)), table is not None and "Checked out" in table.group(0)),
        (["checked-out"], True),
    )
    return


def test_the_zone_comes_from_the_address_then_the_cookie_then_utc():
    """
    **Feature: availability week (RES-43)**
    **Property: with a zone cookie and no tz the week is in the cookie's
    zone (also when the slash was percent-encoded, which the page's script
    once did); an explicit tz wins over the cookie; an unknown tz falls
    back to the cookie, and no zone at all gives UTC; the week's title
    says which zone it is in.**
    """
    admin = admin_cookies()
    remembered = dict(admin)
    remembered["pyc_tz"] = "Asia/Tokyo"
    encoded = dict(admin)
    encoded["pyc_tz"] = "Europe%2FParis"

    def zone_of(page: str) -> str:
        return re.search(r'data-avail-zone="([^"]*)"', page).group(1)

    testbase.assert_equal(
        (zone_of(_calendar(remembered)), zone_of(_calendar(remembered, tz="Europe/Berlin")),
         zone_of(_calendar(remembered, tz="Not/AZone")), zone_of(_calendar(admin)),
         "times in Asia/Tokyo" in _calendar(remembered), zone_of(_calendar(encoded))),
        ("Asia/Tokyo", "Europe/Berlin", "Asia/Tokyo", "UTC", True, "Europe/Paris"),
    )
    return


def test_the_week_navigation_keeps_the_pool_and_the_chosen_zone():
    """
    **Feature: availability week (RES-43)**
    **Property: the previous, this and next week links go to the
    neighbouring Mondays and keep the pool and an explicit zone; the
    calendar address is not read as a reservation id.**
    """
    admin = admin_cookies()
    pool_id, _name = _pool(admin)
    page = _calendar(admin, pool_id=pool_id, week="2026-09-30", tz="Europe/Berlin")

    def link(role: str) -> str:
        found = re.search(r'<a href="([^"]*)"[^>]*data-role="' + role + '"', page)
        return found.group(1) if found is not None else ""

    previous, following = link("previous-week"), link("next-week")

    def keeps_zone_and_pool(address: str) -> bool:
        zone_kept = "tz=Europe/Berlin" in address or "tz=Europe%2FBerlin" in address
        return zone_kept and "pool_id={}".format(pool_id) in address

    testbase.assert_equal(
        ("week=2026-09-21" in previous, "week=2026-10-05" in following,
         keeps_zone_and_pool(previous), keeps_zone_and_pool(following), "Sep 2026" in page),
        (True, True, True, True, True),
    )
    return


def test_a_malformed_week_falls_back_to_this_week_instead_of_failing():
    """
    **Feature: availability week (RES-43)**
    **Property: a week that is not a date, or a pool that is not a
    number, still answers 200 with this week's page.**
    """
    admin = admin_cookies()
    response = get(path="/resources/reservations/calendar", cookies=admin, query={"week": "not-a-date", "pool_id": "abc"})

    testbase.assert_equal((response.status_code, 'data-role="week-title"' in response.text), (200, True))
    return


def test_only_the_first_rows_are_drawn_when_there_are_many_resources():
    """
    **Feature: availability week (RES-43)**
    **Property: the page draws at most forty rows and says how many
    resources there are and to choose a pool to see the rest.**
    """
    admin = admin_cookies()
    page = _calendar(admin)
    rows = len(re.findall(r'<div class="avail-row" data-resource-id=', page))
    total = re.search(r"Showing the first (\d+) of (\d+) resources", page)

    testbase.assert_equal(
        (rows <= 40, (total is None) or (int(total.group(1)) == rows and int(total.group(2)) > rows)),
        (True, True),
    )
    return
