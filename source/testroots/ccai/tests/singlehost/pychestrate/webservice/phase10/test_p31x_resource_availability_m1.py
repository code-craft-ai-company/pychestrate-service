"""
.. module:: test_p31x_resource_availability_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The resource list says what is available, who has the
               rest, and finds devices by their metadata (RES-19).

.. moduleauthor:: Code Craft AI LLC

Finding a free device meant reading "Capacity 1/1" against "0/1", search
ignored metadata (an OS version or a serial number found nothing), and
checking a device out meant opening it first. The list now has an
availability filter (applied in the query, so the pages and the total are
right), an Availability column ("Available", or "In use by quinn until
18:30 UTC"), a Check out on each available row, and a search that also
matches metadata. A resource that marks metadata keys as sensitive is
found by name and description only, so a search cannot probe values the
pages mask.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import json
import re
import uuid

from typing import Dict, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    open_db_session,
    post_form,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_viewer,
    login_via_post,
)


def _prefix() -> str:
    return "av" + uuid.uuid4().hex[:8]


def _resource(cookies: Dict[str, str], name: str, **extra: str) -> str:
    fields = {"name": name, "resource_type": "device", "pool_id": "", "description": "",
              "capacity": "1", "metadata": "{}"}
    fields.update(extra)
    response = post_form(path="/resources/create", fields=fields, cookies=cookies)
    match = re.search(r"/resources/(\d+)", response.header("Location") or "")
    testbase.assert_true(match is not None, "resource {} not created: {}".format(name, response.status_code))
    return match.group(1)


def _lab() -> Tuple[Dict[str, str], Dict[str, str], str, Dict[str, str], str]:
    """
        Four devices sharing a unique name prefix: ``free``, ``busy`` (the
        viewer holds it for an hour), ``down`` (offline) and ``tagged``
        (metadata with an OS version and a serial number). Returns
        ``(admin cookies, viewer cookies, viewer login, {role: id},
        prefix)``.
    """
    admin = admin_cookies()
    viewer = ensure_seeded_viewer()
    _r, viewer_cookies = login_via_post(wsgi_app=app(), login=viewer.login, password=viewer.password)
    prefix = _prefix()
    serial = "SN-" + uuid.uuid4().hex[:8].upper()
    ids = {
        "free": _resource(admin, prefix + "-free"),
        "busy": _resource(admin, prefix + "-busy"),
        "down": _resource(admin, prefix + "-down"),
        "tagged": _resource(admin, prefix + "-tagged", metadata=json.dumps({"os_version": "22.04.3", "serial": serial})),
    }
    post_form(path="/resources/{}/checkout".format(ids["busy"]),
              fields={"mode": "exclusive", "job_id": "", "timeout_minutes": "60", "reason": "for the list"},
              cookies=viewer_cookies)
    post_form(path="/resources/health/{}/update".format(ids["down"]),
              fields={"status": "offline", "reason": "for the list"}, cookies=admin)
    ids["serial"] = serial
    return (admin, viewer_cookies, viewer.login, ids, prefix)


def _list(cookies: Dict[str, str], **query: str) -> str:
    return get(path="/resources/list", cookies=cookies, query=query).text


def _row(page: str, name: str) -> str:
    match = re.search(r"<tr>\s*<td><a href=\"/resources/\d+\">" + re.escape(name) + r"</a></td>.*?</tr>", page, re.S)
    return html.unescape(match.group(0)) if match is not None else ""


def _names_listed(page: str, prefix: str) -> set:
    return set(re.findall(r">(" + re.escape(prefix) + r"-[a-z]+)</a></td>", page))


def test_the_availability_filter_lists_what_can_be_checked_out_now():
    """
    **Feature: resource availability (RES-19)**
    **Property: "Available now" lists the free and the unchecked-out
    devices, not the one held by someone and not the offline one;
    "In use" lists only the held one.**
    """
    admin, _viewer, _login, _ids, prefix = _lab()
    available = _names_listed(_list(admin, search=prefix, availability="available"), prefix)
    in_use = _names_listed(_list(admin, search=prefix, availability="in_use"), prefix)

    testbase.assert_equal(
        (available, in_use),
        ({prefix + "-free", prefix + "-tagged"}, {prefix + "-busy"}),
    )
    return


def test_the_filter_is_applied_before_paging_and_kept_by_the_pager():
    """
    **Feature: resource availability (RES-19)**
    **Property: with one row a page, the two available devices make two
    pages (the total is right, not just the first page filtered), and the
    Next link keeps the filter and the search.**
    """
    admin, _viewer, _login, _ids, prefix = _lab()
    first = _list(admin, search=prefix, availability="available", per_page="1")
    nxt = re.search(r'<a href="([^"]*)" rel="next"', first)
    link = html.unescape(nxt.group(1)) if nxt is not None else ""
    second = _list(admin, search=prefix, availability="available", per_page="1", page="2")

    testbase.assert_equal(
        (len(_names_listed(first, prefix)), nxt is not None, "availability=available" in link, prefix in link,
         len(_names_listed(second, prefix)), _names_listed(first, prefix) != _names_listed(second, prefix)),
        (1, True, True, True, 1, True),
    )
    return


def test_the_list_says_who_has_a_device_and_until_when():
    """
    **Feature: resource availability (RES-19)**
    **Property: the held device's row reads "In use by <login> until
    <time> UTC", a free one reads "Available" with a Check out, and an
    offline one reads "Unavailable" with no Check out.**
    """
    admin, _viewer, login, _ids, prefix = _lab()
    page = _list(admin, search=prefix)
    busy, free, down = (_row(page, prefix + "-" + role) for role in ("busy", "free", "down"))
    busy_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", busy))

    testbase.assert_equal(
        (bool(re.search(r"In use by {} until \d{{4}}-\d\d-\d\d \d\d:\d\d UTC".format(re.escape(login)), busy_text)),
         "Available" in free and "Check out" in free,
         "Unavailable" in down and "Check out" not in down and "Offline" in down),
        (True, True, True),
    )
    return


def test_a_device_can_be_checked_out_from_its_row():
    """
    **Feature: resource availability (RES-19)**
    **Property: posting the row's Check out form for a free device holds
    it for the person, and the list then shows it in use by them.**
    """
    admin, viewer_cookies, login, ids, prefix = _lab()
    row = _row(_list(viewer_cookies, search=prefix), prefix + "-free")
    action = re.search(r'action="(/resources/\d+/checkout)"', row)
    fields = dict(re.findall(r'<input type="hidden" name="(mode)" value="([^"]*)"', row))
    testbase.assert_true(action is not None, "no check-out form on the free row")
    response = post_form(path=action.group(1), fields={"mode": fields.get("mode", "exclusive"), "job_id": "",
                                                        "timeout_minutes": "", "reason": ""}, cookies=viewer_cookies)
    after = _row(_list(viewer_cookies, search=prefix), prefix + "-free")

    testbase.assert_equal(
        (response.status_code, "In use" in after, login in after),
        (303, True, True),
    )
    return


def test_search_finds_a_device_by_its_metadata():
    """
    **Feature: resource availability (RES-19)**
    **Property: searching for the device's serial number or a part of its
    OS version lists it, and searching for something in no metadata does
    not.**
    """
    admin, _viewer, _login, ids, prefix = _lab()
    by_serial = _names_listed(_list(admin, search=ids["serial"]), prefix)
    by_version = _names_listed(_list(admin, search="22.04.3"), prefix)
    by_nothing = _names_listed(_list(admin, search=ids["serial"] + "-nope"), prefix)

    testbase.assert_equal(
        (by_serial, prefix + "-tagged" in by_version, by_nothing),
        ({prefix + "-tagged"}, True, set()),
    )
    return


def test_metadata_of_a_resource_with_sensitive_fields_is_not_searchable():
    """
    **Feature: resource availability (RES-19)**
    **Property: once a resource marks a metadata key as sensitive,
    searching for its metadata no longer finds it, while its name still
    does.**
    """
    admin, _viewer, _login, ids, prefix = _lab()
    from ccai.pychestrate.core.orm import Resource  # noqa: E402

    db_session = open_db_session()
    try:
        row = db_session.query(Resource).filter(Resource.id == int(ids["tagged"])).one()
        row.sensitive_fields = ["serial"]
        db_session.commit()
    finally:
        db_session.close()

    testbase.assert_equal(
        (_names_listed(_list(admin, search=ids["serial"]), prefix),
         prefix + "-tagged" in _names_listed(_list(admin, search=prefix), prefix)),
        (set(), True),
    )
    return
