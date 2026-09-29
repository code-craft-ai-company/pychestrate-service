"""
.. module:: test_p31u_ip_holder_and_release_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: An IP pool shows who holds each address and why, and a
               lab manager can release an address for its holder
               (RES-14).

.. moduleauthor:: Code Craft AI LLC

The pool page's User column was always "-" (the response builder left
the name unset), the reason given at check-out was write-only, and a
manager who tried to release someone else's address was told the person
was not its owner. The page now names the holder, shows the reason, and
marks a person's own addresses. A person with the resource-management
permission may release an address for its holder, giving a reason that
is audited with the holder's name; anyone else is refused as before. The
pool list has a "Your IP addresses" card.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from typing import Dict, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    audit_records_for,
    ensure_audit_wiring,
    get,
    latest_audit_sequence,
    merge_cookies,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_admin,
    ensure_seeded_viewer,
    login_via_post,
)


NEEDS_A_REASON = "Give a reason to release an address someone else holds; it is recorded in the audit log."
OWNER_ONLY = "Only the person who checked this address out can check it in."


def _pool_with_a_viewer_address() -> Tuple[int, str, Dict[str, str], Dict[str, str], str, str]:
    """
        A /29 pool, one address checked out by the viewer (reason
        "CI run 7") and one by the administrator. Returns ``(pool id,
        the viewer's address, admin cookies, viewer cookies, the
        viewer's login, the viewer's user id)``.
    """
    admin = admin_cookies()
    viewer = ensure_seeded_viewer()
    _response, viewer_cookies = login_via_post(wsgi_app=app(), login=viewer.login, password=viewer.password)
    first = uuid.uuid4().int % 200 + 20
    second = uuid.uuid4().int % 200 + 20
    created = post_form(
        path="/resources/ip-pools/create",
        fields={"name": unique_name(prefix="iph"), "cidr": "10.{}.{}.0/29".format(first, second),
                "gateway": "", "dns_servers": "", "reserved_ips": "", "description": ""},
        cookies=admin,
    )
    pool_id = int(re.search(r"/resources/ip-pools/(\d+)", created.header("Location") or "").group(1))
    viewer_address = "10.{}.{}.2".format(first, second)
    admin_address = "10.{}.{}.3".format(first, second)
    post_form(path="/resources/ip-pools/{}/checkout".format(pool_id),
              fields={"count": "1", "specific_ip": viewer_address, "job_id": "job-7",
                      "timeout_minutes": "", "reason": "CI run 7"},
              cookies=viewer_cookies)
    post_form(path="/resources/ip-pools/{}/checkout".format(pool_id),
              fields={"count": "1", "specific_ip": admin_address, "job_id": "",
                      "timeout_minutes": "", "reason": "admin bench"},
              cookies=admin)
    rtnval = (pool_id, viewer_address, admin, viewer_cookies, viewer.login, str(viewer.user_id))
    return rtnval


def _allocation_id(pool_id: int, address: str, cookies: Dict[str, str]) -> str:
    page = get(path="/resources/ip-pools/{}".format(pool_id), cookies=cookies).text
    row = re.search(r"<tr>\s*<td><code>" + re.escape(address) + r"</code></td>.*?</tr>", page, re.S)
    testbase.assert_true(row is not None, "no row for {}".format(address))
    found = re.search(r'name="allocation_id" value="(\d+)"', row.group(0))
    testbase.assert_true(found is not None, "no allocation id in the row of {}".format(address))
    return found.group(1)


def _flash_after(response, cookies: Dict[str, str]) -> str:
    followed = get(path=response.header("Location") or "/", cookies=merge_cookies(cookies=cookies, response=response))
    return html.unescape(followed.text)


def _row(page: str, address: str) -> str:
    match = re.search(r"<tr>\s*<td><code>" + re.escape(address) + r"</code></td>.*?</tr>", page, re.S)
    return match.group(0) if match is not None else ""


def test_the_pool_page_names_who_holds_an_address_and_why():
    """
    **Feature: IP holders (RES-14)**
    **Property: the pool page's rows name the holder (not "-") and show
    the reason and job given at check-out; the holder's own row is
    marked "(you)".**
    """
    pool_id, viewer_address, admin, viewer_cookies, viewer_login, _viewer_id = _pool_with_a_viewer_address()
    admin_page = get(path="/resources/ip-pools/{}".format(pool_id), cookies=admin).text
    viewer_page = get(path="/resources/ip-pools/{}".format(pool_id), cookies=viewer_cookies).text
    row = _row(admin_page, viewer_address)
    own_row = _row(viewer_page, viewer_address)

    testbase.assert_equal(
        (viewer_login in row, "CI run 7" in row, "job-7" in row, "(you)" in row,
         viewer_login in own_row and "(you)" in own_row),
        (True, True, True, False, True),
    )
    return


def test_a_manager_releases_someone_elses_address_with_a_reason_that_is_audited():
    """
    **Feature: IP holders (RES-14)**
    **Property: the administrator releases the viewer's address giving a
    reason; it is released, the message says the reason is recorded, and
    one audit record names the administrator, the holder, the address and
    the reason.**
    """
    ensure_audit_wiring()
    pool_id, address, admin, _viewer_cookies, _login, viewer_id = _pool_with_a_viewer_address()
    allocation_id = _allocation_id(pool_id, address, admin)
    mark = latest_audit_sequence()
    response = post_form(
        path="/resources/ip-pools/{}/checkin".format(pool_id),
        fields={"allocation_id": allocation_id, "reason": "Bench needed for the audit"}, cookies=admin,
    )
    message = _flash_after(response, admin)
    rows = audit_records_for(kind="audit.ip_allocation.force_released", since_sequence=mark)
    payload = rows[0].payload_json if len(rows) == 1 else {}
    page = get(path="/resources/ip-pools/{}".format(pool_id), cookies=admin).text

    testbase.assert_equal(
        (response.status_code, "Your reason was recorded in the audit log." in message, _row(page, address),
         len(rows), str(rows[0].actor_user_id) if rows else "", payload.get("holder_user_id"),
         payload.get("ip_address"), payload.get("reason")),
        (303, True, "", 1, str(ensure_seeded_admin().user_id), viewer_id, address, "Bench needed for the audit"),
    )
    return


def test_a_manager_needs_a_reason_to_release_someone_elses_address():
    """
    **Feature: IP holders (RES-14)**
    **Property: releasing the viewer's address with no reason is refused
    asking for one; the address stays checked out and nothing is
    audited.**
    """
    ensure_audit_wiring()
    pool_id, address, admin, _viewer_cookies, _login, _viewer_id = _pool_with_a_viewer_address()
    allocation_id = _allocation_id(pool_id, address, admin)
    mark = latest_audit_sequence()
    response = post_form(
        path="/resources/ip-pools/{}/checkin".format(pool_id),
        fields={"allocation_id": allocation_id, "reason": "  "}, cookies=admin,
    )
    page = get(path="/resources/ip-pools/{}".format(pool_id), cookies=admin).text

    testbase.assert_equal(
        (NEEDS_A_REASON in _flash_after(response, admin), _row(page, address) != "",
         len(audit_records_for(kind="audit.ip_allocation.force_released", since_sequence=mark))),
        (True, True, 0),
    )
    return


def test_a_person_who_is_not_a_manager_still_cannot_release_someone_elses_address():
    """
    **Feature: IP holders (RES-14)**
    **Property: the viewer cannot release the administrator's address
    even when giving a reason; the message says only who checked it out
    can, and the address stays checked out.**
    """
    pool_id, viewer_address, admin, viewer_cookies, _login, _viewer_id = _pool_with_a_viewer_address()
    admin_address = viewer_address[:-1] + "3"
    allocation_id = _allocation_id(pool_id, admin_address, admin)
    response = post_form(
        path="/resources/ip-pools/{}/checkin".format(pool_id),
        fields={"allocation_id": allocation_id, "reason": "I would like it"}, cookies=viewer_cookies,
    )
    page = get(path="/resources/ip-pools/{}".format(pool_id), cookies=admin).text

    testbase.assert_equal(
        (OWNER_ONLY in _flash_after(response, viewer_cookies), _row(page, admin_address) != ""),
        (True, True),
    )
    return


def test_the_manager_is_offered_release_and_the_holder_check_in():
    """
    **Feature: IP holders (RES-14)**
    **Property: on the viewer's row the administrator has a Release that
    asks for a reason and the viewer has a plain Checkin; on the
    administrator's row the viewer has no form at all.**
    """
    pool_id, viewer_address, admin, viewer_cookies, _login, _viewer_id = _pool_with_a_viewer_address()
    admin_address = viewer_address[:-1] + "3"
    admin_page = get(path="/resources/ip-pools/{}".format(pool_id), cookies=admin).text
    viewer_page = get(path="/resources/ip-pools/{}".format(pool_id), cookies=viewer_cookies).text

    testbase.assert_equal(
        ('name="reason"' in _row(admin_page, viewer_address) and "Release" in _row(admin_page, viewer_address),
         'name="reason"' not in _row(admin_page, admin_address) and "Checkin" in _row(admin_page, admin_address),
         "Checkin" in _row(viewer_page, viewer_address) and 'name="reason"' not in _row(viewer_page, viewer_address),
         "<form" in _row(viewer_page, admin_address)),
        (True, True, True, False),
    )
    return


def test_the_pool_list_shows_a_person_their_own_addresses():
    """
    **Feature: IP holders (RES-14)**
    **Property: the IP pool list has a "Your IP addresses" card naming
    the viewer's address, its pool and its reason, and the administrator's
    card lists theirs, not the viewer's.**
    """
    pool_id, viewer_address, admin, viewer_cookies, _login, _viewer_id = _pool_with_a_viewer_address()
    viewer_page = get(path="/resources/ip-pools", cookies=viewer_cookies).text
    admin_page = get(path="/resources/ip-pools", cookies=admin).text
    card = viewer_page.split("Your IP addresses", 1)[1] if "Your IP addresses" in viewer_page else ""
    admin_card = admin_page.split("Your IP addresses", 1)[1] if "Your IP addresses" in admin_page else ""

    testbase.assert_equal(
        ("Your IP addresses" in viewer_page, "<code>{}</code>".format(viewer_address) in card, "CI run 7" in card,
         "/resources/ip-pools/{}".format(pool_id) in card, "<code>{}</code>".format(viewer_address) in admin_card),
        (True, True, True, True, False),
    )
    return
