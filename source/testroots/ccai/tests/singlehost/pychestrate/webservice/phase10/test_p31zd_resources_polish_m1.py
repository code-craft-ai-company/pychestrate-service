"""
.. module:: test_p31zd_resources_polish_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reasons and actors are shown, an offline device says why
               it cannot be checked out, pagers keep their filters and show
               totals, and two small accessibility and copy fixes
               (RES-41, RES-23, RES-28, RES-30, RES-31).

.. moduleauthor:: Code Craft AI LLC

* **RES-28**: the reason given at check-out, the reason for a reservation,
  who force-checked an allocation in and why, who made a pool, and who
  made a manual health change were stored and never shown.
* **RES-30**: on an offline device the Checkout card vanished, and a person
  who already held a device was told it was "at capacity". The card now
  says what is true: blocked since when and why, held by you, or held by
  whom.
* **RES-23**: pagers dropped filters (the history's end date, the resource
  list's tags) and never showed how many rows there were.
* **RES-41**: the reservation edit page's disabled Mode field had a label
  that pointed at nothing (an axe critical).
* **RES-31**: a full IP pool told people to "extend the pool", which cannot
  be done.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from typing import Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import url_for as url_for_module

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    merge_cookies,
    post_form,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_admin,
    ensure_seeded_viewer,
    login_via_post,
)


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _viewer_cookies() -> Tuple[Dict[str, str], str]:
    viewer = ensure_seeded_viewer()
    _response, cookies = login_via_post(wsgi_app=app(), login=viewer.login, password=viewer.password)
    return (cookies, viewer.login)


def _device(cookies: Dict[str, str], prefix: str = "pol", **extra: str) -> Tuple[str, str]:
    name = "{}-{}".format(prefix, _suffix())
    fields = {"name": name, "resource_type": "device", "pool_id": "", "description": "", "capacity": "1", "metadata": "{}"}
    fields.update(extra)
    response = post_form(path="/resources/create", fields=fields, cookies=cookies)
    found = re.search(r"/resources/(\d+)", response.header("Location") or "")
    testbase.assert_true(found is not None, "device not created: {}".format(response.status_code))
    return (found.group(1), name)


def _page(cookies: Dict[str, str], path: str, **query: str) -> str:
    return html.unescape(get(path=path, cookies=cookies, query=query).text)


def _role_text(page: str, role: str) -> str:
    match = re.search(r'data-role="' + re.escape(role) + r'"[^>]*>(.*?)</(?:td|div|p)>', page, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1))).strip() if match is not None else ""


def _checkout(cookies: Dict[str, str], device_id: str, *, reason: str = "", minutes: str = "") -> str:
    """Check the device out; returns the allocation id (read from the device page)."""
    post_form(path="/resources/{}/checkout".format(device_id),
              fields={"mode": "exclusive", "job_id": "", "timeout_minutes": minutes, "reason": reason}, cookies=cookies)
    found = re.search(r"/resources/allocations/(\d+)", _page(cookies, "/resources/{}".format(device_id)))
    testbase.assert_true(found is not None, "no allocation on the device page after the checkout")
    return found.group(1)


def _total_line(page: str) -> str:
    match = re.search(r"Page \d+ of \d+ · (\d+) total", page)
    return match.group(1) if match is not None else ""


# ---------------------------------------------------------------------------
# RES-28: reasons and actors
# ---------------------------------------------------------------------------


def test_the_reason_given_at_checkout_is_shown_on_the_allocation_and_in_the_lists():
    """
    **Feature: reasons and actors (RES-28)**
    **Property: the reason typed at check-out shows on the allocation's
    page and under the holder in the active and history lists.**
    """
    admin = admin_cookies()
    device_id, _name = _device(admin)
    allocation_id = _checkout(admin, device_id, reason="Nightly regression, bench 4")
    detail = _page(admin, "/resources/allocations/{}".format(allocation_id))
    active = _page(admin, "/resources/allocations", resource_id=device_id)
    post_form(path="/resources/allocations/{}/checkin".format(allocation_id), fields={}, cookies=admin)
    history = _page(admin, "/resources/allocations/history", resource_id=device_id)

    testbase.assert_equal(
        (_role_text(detail, "allocation-reason"), "Nightly regression, bench 4" in active, "Nightly regression, bench 4" in history),
        ("Nightly regression, bench 4", True, True),
    )
    return


def test_a_forced_check_in_shows_who_did_it_and_why():
    """
    **Feature: reasons and actors (RES-28)**
    **Property: after the administrator force-checks-in the viewer's
    allocation with a reason, the allocation's page names the
    administrator and the reason, and the history shows "by <login>: reason"
    beside the Forced badge.**
    """
    admin = admin_cookies()
    viewer, _viewer_login = _viewer_cookies()
    device_id, _name = _device(admin)
    allocation_id = _checkout(viewer, device_id)
    post_form(path="/resources/allocations/{}/force-checkin".format(allocation_id),
              fields={"reason": "Bench needed for the release"}, cookies=admin)
    detail = _page(admin, "/resources/allocations/{}".format(allocation_id))
    history = _page(admin, "/resources/allocations/history", resource_id=device_id)
    admin_login = ensure_seeded_admin().login

    testbase.assert_equal(
        (_role_text(detail, "forced-by"), _role_text(detail, "force-reason"), _role_text(history, "forced-by")),
        (admin_login, "Bench needed for the release", "by {}: Bench needed for the release".format(admin_login)),
    )
    return


def test_a_reservations_reason_is_shown_on_its_page():
    """
    **Feature: reasons and actors (RES-28)**
    **Property: the reason typed when reserving a device shows on the
    reservation's page.**
    """
    admin = admin_cookies()
    device_id, _name = _device(admin)
    response = post_form(
        path="/resources/reservations/create",
        fields={"resource_id": device_id, "start_time": "2030-05-01T09:00", "end_time": "2030-05-01T10:00", "tz": "UTC",
                "mode": "exclusive", "job_id": "", "reason": "Demo for the QA review"},
        cookies=admin,
    )
    reservation_id = re.search(r"/resources/reservations/(\d+)", response.header("Location") or "").group(1)
    page = _page(admin, "/resources/reservations/{}".format(reservation_id))

    testbase.assert_equal(_role_text(page, "reservation-reason"), "Demo for the QA review")
    return


def test_a_pool_shows_who_made_it_by_name_not_by_id():
    """
    **Feature: reasons and actors (RES-28)**
    **Property: the pool page's Created By is the administrator's login,
    not a UUID.**
    """
    admin = admin_cookies()
    response = post_form(path="/resources/pools/create", fields={"name": "pol-pool-" + _suffix(), "description": ""}, cookies=admin)
    pool_id = re.search(r"/resources/pools/(\d+)", response.header("Location") or "").group(1)
    text = _role_text(_page(admin, "/resources/pools/{}".format(pool_id)), "pool-created-by")

    testbase.assert_equal(
        (text, re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", text) is None),
        (ensure_seeded_admin().login, True),
    )
    return


def test_a_manual_health_change_shows_who_made_it():
    """
    **Feature: reasons and actors (RES-28)**
    **Property: a health change the administrator made by hand shows the
    administrator's login beside "user" in Triggered By.**
    """
    admin = admin_cookies()
    device_id, _name = _device(admin)
    post_form(path="/resources/health/{}/update".format(device_id), fields={"status": "maintenance", "reason": "Firmware update"}, cookies=admin)
    page = _page(admin, "/resources/health/{}".format(device_id))

    testbase.assert_equal(_role_text(page, "triggered-by-user"), "({})".format(ensure_seeded_admin().login))
    return


# ---------------------------------------------------------------------------
# RES-30: the checkout card
# ---------------------------------------------------------------------------


def test_an_offline_device_says_checkout_is_blocked_since_when_and_why():
    """
    **Feature: checkout card (RES-30)**
    **Property: on a device set to maintenance the Checkout card is still
    there, says checkout is blocked, since when, why and by whom, and
    tells an administrator where to change it; a plain user is told to ask
    a lab manager; neither sees a checkout form.**
    """
    admin = admin_cookies()
    viewer, _login = _viewer_cookies()
    device_id, _name = _device(admin)
    post_form(path="/resources/health/{}/update".format(device_id), fields={"status": "maintenance", "reason": "Swapping the power supply"}, cookies=admin)
    as_admin = _page(admin, "/resources/{}".format(device_id))
    as_viewer = _page(viewer, "/resources/{}".format(device_id))
    admin_text = _role_text(as_admin, "checkout-blocked")
    viewer_text = _role_text(as_viewer, "checkout-blocked")

    testbase.assert_equal(
        ("blocked" in admin_text and "maintenance since 20" in admin_text, "Swapping the power supply" in admin_text,
         "set by {}".format(ensure_seeded_admin().login) in admin_text, "Health" in admin_text,
         "ask a lab manager" in viewer_text.lower(), "Change its status" in viewer_text,
         'action="/resources/{}/checkout"'.format(device_id) in as_admin or 'action="/resources/{}/checkout"'.format(device_id) in as_viewer),
        (True, True, True, True, True, False, False),
    )
    return


def test_the_holder_is_told_they_have_it_and_others_are_told_who_does():
    """
    **Feature: checkout card (RES-30)**
    **Property: on a device the viewer has checked out, the viewer's
    Checkout card says they have it and links to their allocation, while
    the administrator's card says it is held by the viewer; neither offers
    a checkout form.**
    """
    admin = admin_cookies()
    viewer, viewer_login = _viewer_cookies()
    device_id, _name = _device(admin)
    allocation_id = _checkout(viewer, device_id, minutes="90")
    mine = _page(viewer, "/resources/{}".format(device_id))
    theirs = _page(admin, "/resources/{}".format(device_id))

    testbase.assert_equal(
        ("You have this checked out" in _role_text(mine, "checkout-held-by-you"),
         "/resources/allocations/{}".format(allocation_id) in mine.split('data-role="checkout-held-by-you"')[1].split("</p>")[0],
         'data-role="checkout-at-capacity"' in mine,
         "held by {}".format(viewer_login) in _role_text(theirs, "checkout-at-capacity"),
         "until 20" in _role_text(theirs, "checkout-at-capacity"),
         'data-role="checkout-held-by-you"' in theirs),
        (True, True, False, True, True, False),
    )
    return


def test_a_free_device_still_offers_checkout():
    """
    **Feature: checkout card (RES-30)**
    **Property: a device that is online with room left shows the checkout
    form and none of the explanations.**
    """
    admin = admin_cookies()
    device_id, _name = _device(admin)
    page = _page(admin, "/resources/{}".format(device_id))

    testbase.assert_equal(
        ('action="/resources/{}/checkout"'.format(device_id) in page, 'data-role="checkout-blocked"' in page,
         'data-role="checkout-held-by-you"' in page, 'data-role="checkout-at-capacity"' in page),
        (True, False, False, False),
    )
    return


# ---------------------------------------------------------------------------
# RES-23: pagers keep their filters and show totals
# ---------------------------------------------------------------------------


def _next_query(page: str) -> Dict[str, List[str]]:
    found = re.search(r'<a href="([^"]*)" rel="next"', page)
    return parse_qs(urlparse(found.group(1)).query) if found is not None else {}


def test_the_history_pager_keeps_the_end_date():
    """
    **Feature: pager filters and totals (RES-23)**
    **Property: the next link of a paged allocation history keeps the end
    date as well as the start date and the resource.**
    """
    admin = admin_cookies()
    device_id, _name = _device(admin)
    for _round in range(2):
        allocation_id = _checkout(admin, device_id)
        post_form(path="/resources/allocations/{}/checkin".format(allocation_id), fields={}, cookies=admin)
    page = _page(admin, "/resources/allocations/history", resource_id=device_id, per_page="1",
                 start_date="2020-01-01", end_date="2099-12-31")
    query = _next_query(page)

    testbase.assert_equal(
        (query.get("end_date"), query.get("start_date"), query.get("resource_id") == [device_id], _total_line(page)),
        (["2099-12-31"], ["2020-01-01"], True, "2"),
    )
    return


def test_the_resource_list_pager_keeps_the_tag_filter():
    """
    **Feature: pager filters and totals (RES-23)**
    **Property: with two devices carrying a tag and one to a page, the
    next link keeps the tag (which it dropped), and the list says how many
    there are.**
    """
    admin = admin_cookies()
    tag = "pt" + _suffix()
    _device(admin, new_tags=tag)
    _device(admin, new_tags=tag)
    page = _page(admin, "/resources/list", tags=tag, per_page="1")
    query = _next_query(page)

    testbase.assert_equal((query.get("tags"), _total_line(page)), ([tag], "2"))
    return


def test_lists_say_how_many_rows_there_are():
    """
    **Feature: pager filters and totals (RES-23)**
    **Property: the resource list (for a search), the reservation list
    (for a device), the tag list (for a search), the pool list, the IP
    pool list and the allocation lists each show "Page 1 of N · T total"
    with T the number of rows the filter matches.**
    """
    admin = admin_cookies()
    prefix = "tot" + _suffix()
    first, _n1 = _device(admin, prefix=prefix)
    _second, _n2 = _device(admin, prefix=prefix)
    for day in ("2030-06-01", "2030-06-02", "2030-06-03"):
        post_form(path="/resources/reservations/create",
                  fields={"resource_id": first, "start_time": day + "T09:00", "end_time": day + "T10:00", "tz": "UTC",
                          "mode": "exclusive", "job_id": "", "reason": ""}, cookies=admin)
    post_form(path="/resources/tags/create", fields={"name": prefix + "-tag", "description": ""}, cookies=admin)
    totals = {
        "resources": _total_line(_page(admin, "/resources/list", search=prefix)),
        "reservations": _total_line(_page(admin, "/resources/reservations", resource_id=first)),
        "tags": _total_line(_page(admin, "/resources/tags", search=prefix)),
        "pools": _total_line(_page(admin, "/resources/pools")),
        "ip pools": _total_line(_page(admin, "/resources/ip-pools")),
        "allocations": _total_line(_page(admin, "/resources/allocations")),
        "history": _total_line(_page(admin, "/resources/allocations/history")),
    }

    testbase.assert_equal(
        (totals["resources"], totals["reservations"], totals["tags"],
         all(totals[key] != "" for key in ("pools", "ip pools", "allocations", "history"))),
        ("2", "3", "1", True),
    )
    return


def test_a_list_value_in_a_link_is_written_once_per_item():
    """
    **Feature: pager filters and totals (RES-23)**
    **Property: url_for writes a list as repeated parameters (tags=a&tags=b),
    writes nothing for an empty list, and still skips None.**
    """
    endpoint = "test.polish_lists"
    url_for_module.register_endpoint(endpoint=endpoint, pattern="/polish")

    testbase.assert_equal(
        (url_for_module.url_for(endpoint, tags=["a", "b"], page=2), url_for_module.url_for(endpoint, tags=[], page=None),
         url_for_module.url_for(endpoint, tags=("x y",))),
        ("/polish?tags=a&tags=b&page=2", "/polish", "/polish?tags=x+y"),
    )
    return


# ---------------------------------------------------------------------------
# RES-41 and RES-31
# ---------------------------------------------------------------------------


def test_the_disabled_mode_field_on_the_reservation_edit_page_has_a_label():
    """
    **Feature: accessibility (RES-41)**
    **Property: the reservation edit page's Mode field is an input with an
    id, a label whose for points at that id, and a description; it is not
    a label with nothing to label.**
    """
    admin = admin_cookies()
    device_id, _name = _device(admin)
    response = post_form(
        path="/resources/reservations/create",
        fields={"resource_id": device_id, "start_time": "2030-05-02T09:00", "end_time": "2030-05-02T10:00", "tz": "UTC",
                "mode": "shared", "job_id": "", "reason": ""},
        cookies=admin,
    )
    reservation_id = re.search(r"/resources/reservations/(\d+)", response.header("Location") or "").group(1)
    page = _page(admin, "/resources/reservations/{}/edit".format(reservation_id))
    label = re.search(r'<label for="([^"]+)">Mode</label>', page)
    field = re.search(r'<input[^>]*\bid="' + re.escape(label.group(1)) + r'"[^>]*>', page) if label is not None else None

    testbase.assert_equal(
        (label is not None, field is not None and "disabled" in field.group(0) and 'value="shared"' in field.group(0),
         field is not None and "aria-describedby=" in field.group(0), "<label>Mode</label>" in page),
        (True, True, True, False),
    )
    return


def test_a_full_ip_pool_does_not_tell_people_to_extend_it():
    """
    **Feature: IP pool advice (RES-31)**
    **Property: on a pool with no address left, the advice offers a link
    to create another pool and says a range cannot be changed once made;
    it no longer says to "extend the pool".**
    """
    admin = admin_cookies()
    first = uuid.uuid4().int % 200 + 20
    second = uuid.uuid4().int % 200 + 20
    created = post_form(
        path="/resources/ip-pools/create",
        fields={"name": "pol-ip-" + _suffix(), "cidr": "10.{}.{}.0/30".format(first, second), "gateway": "", "dns_servers": "",
                "reserved_ips": "", "description": ""},
        cookies=admin,
    )
    pool_id = re.search(r"/resources/ip-pools/(\d+)", created.header("Location") or "").group(1)
    post_form(path="/resources/ip-pools/{}/checkout".format(pool_id),
              fields={"count": "2", "specific_ip": "", "job_id": "", "timeout_minutes": "", "reason": ""}, cookies=admin)
    page = _page(admin, "/resources/ip-pools/{}".format(pool_id))
    advice = re.search(r"This pool is at capacity.*?</p>", page, re.S)
    text = advice.group(0) if advice is not None else ""

    testbase.assert_equal(
        (advice is not None, "extend the pool" in text, 'href="/resources/ip-pools/create"' in text, "cannot be changed" in text),
        (True, False, True, True),
    )
    return
