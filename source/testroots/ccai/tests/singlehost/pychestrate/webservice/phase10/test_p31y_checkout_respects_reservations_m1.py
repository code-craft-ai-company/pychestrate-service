"""
.. module:: test_p31y_checkout_respects_reservations_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A check-out cannot run into someone else's reservation
               (RES-11).

.. moduleauthor:: Code Craft AI LLC

An administrator checked out a reserved phone for three days across two
pending reservations, and the detail page listed the reservations right
under the new allocation with no warning: the check-out never looked at
reservations. It now refuses a check-out whose window (now until its
timeout, or without end when it has none) overlaps a pending reservation
of someone else, saying who reserved it and when and how to check it out
anyway (with a timeout that ends before then). The person who holds the
reservation is never in their own way, and two shared windows do not
clash. The checkout card names the reservation up front. Activating due
reservations and expiring timed-out check-outs run in the housekeeping
worker.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    merge_cookies,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_admin,
    ensure_seeded_viewer,
    login_via_post,
)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def _reserved_device(*, mode: str = "exclusive") -> Tuple[str, Dict[str, str], Dict[str, str], str]:
    """
        A device the administrator has reserved from two to three hours
        from now. Returns ``(device id, admin cookies, viewer cookies,
        the administrator's login)``.
    """
    admin = admin_cookies()
    viewer = ensure_seeded_viewer()
    _r, viewer_cookies = login_via_post(wsgi_app=app(), login=viewer.login, password=viewer.password)
    created = post_form(
        path="/resources/create",
        fields={"name": unique_name(prefix="rsv"), "resource_type": "device", "pool_id": "",
                "description": "", "capacity": "3", "metadata": "{}"},
        cookies=admin,
    )
    device_id = re.search(r"/resources/(\d+)", created.header("Location") or "").group(1)
    now = datetime.now(timezone.utc)
    made = post_form(
        path="/resources/reservations/create",
        fields={"resource_id": device_id, "start_time": _stamp(now + timedelta(hours=2)),
                "end_time": _stamp(now + timedelta(hours=3)), "tz": "UTC", "mode": mode,
                "job_id": "", "reason": ""},
        cookies=admin,
    )
    testbase.assert_equal(made.status_code, 303)
    return (device_id, admin, viewer_cookies, ensure_seeded_admin().login)


def _checkout(device_id: str, cookies: Dict[str, str], *, minutes: str = "", mode: str = "exclusive"):
    response = post_form(
        path="/resources/{}/checkout".format(device_id),
        fields={"mode": mode, "job_id": "", "timeout_minutes": minutes, "reason": ""}, cookies=cookies,
    )
    followed = get(path=response.header("Location") or "/", cookies=merge_cookies(cookies=cookies, response=response))
    return (response, html.unescape(followed.text))


def _held(device_id: str, cookies: Dict[str, str]) -> bool:
    page = get(path="/resources/{}".format(device_id), cookies=cookies).text
    return "No active allocations" not in page


def test_a_check_out_without_a_timeout_is_refused_when_someone_else_has_reserved_the_device():
    """
    **Feature: checkout and reservations (RES-11)**
    **Property: the viewer's open-ended check-out of a device the
    administrator has reserved for later is refused, naming the
    administrator and the window and saying how to check out anyway, and
    the device is not checked out.**
    """
    device_id, admin, viewer, admin_login = _reserved_device()
    _response, message = _checkout(device_id, viewer)

    testbase.assert_equal(
        (admin_login + " has reserved this from" in message, "Check it out with a timeout that ends before then" in message,
         _held(device_id, admin)),
        (True, True, False),
    )
    return


def test_a_check_out_that_ends_before_the_reservation_is_allowed_and_one_that_overlaps_is_not():
    """
    **Feature: checkout and reservations (RES-11)**
    **Property: with the reservation two hours away, a one-hour check-out
    goes through, and (after it is checked in) a three-hour one is
    refused.**
    """
    device_id, admin, viewer, _login = _reserved_device()
    short, message = _checkout(device_id, viewer, minutes="60")
    held_after_short = _held(device_id, admin)
    allocation = re.search(r"/resources/allocations/(\d+)", get(path="/resources/{}".format(device_id), cookies=admin).text)
    post_form(path="/resources/allocations/{}/checkin".format(allocation.group(1)) if allocation else "/resources/allocations/0/checkin",
              fields={}, cookies=viewer)
    long_response, refusal = _checkout(device_id, viewer, minutes="180")

    testbase.assert_equal(
        (short.status_code, "checked out successfully" in message, held_after_short,
         "has reserved this from" in refusal, _held(device_id, admin)),
        (303, True, True, True, False),
    )
    return


def test_the_person_who_holds_the_reservation_is_not_in_their_own_way():
    """
    **Feature: checkout and reservations (RES-11)**
    **Property: the administrator, who holds the reservation, checks the
    device out with no timeout without being refused.**
    """
    device_id, admin, _viewer, _login = _reserved_device()
    response, message = _checkout(device_id, admin)

    testbase.assert_equal(
        (response.status_code, "checked out successfully" in message, _held(device_id, admin)),
        (303, True, True),
    )
    return


def test_a_shared_check_out_does_not_clash_with_a_shared_reservation():
    """
    **Feature: checkout and reservations (RES-11)**
    **Property: when the reservation is shared, the viewer's shared
    check-out with no timeout goes through.**
    """
    device_id, admin, viewer, _login = _reserved_device(mode="shared")
    response, message = _checkout(device_id, viewer, mode="shared")

    testbase.assert_equal(
        (response.status_code, "checked out successfully" in message, _held(device_id, admin)),
        (303, True, True),
    )
    return


def test_the_checkout_card_says_who_has_reserved_the_device():
    """
    **Feature: checkout and reservations (RES-11)**
    **Property: the viewer's device page shows a notice on the checkout
    card naming the administrator's reservation, and the administrator's
    own page shows none.**
    """
    device_id, admin, viewer, admin_login = _reserved_device()
    viewer_page = get(path="/resources/{}".format(device_id), cookies=viewer).text
    admin_page = get(path="/resources/{}".format(device_id), cookies=admin).text
    notice = re.search(r'data-role="reserved-notice">(.*?)</p>', viewer_page, re.S)
    text = html.unescape(re.sub(r"\s+", " ", notice.group(1))) if notice is not None else ""

    testbase.assert_equal(
        (admin_login in text, "Check it out with a timeout that ends before then" in text,
         'data-role="reserved-notice"' in admin_page),
        (True, True, False),
    )
    return
