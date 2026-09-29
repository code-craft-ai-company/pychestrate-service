"""
.. module:: test_p31s_resources_manage_controls_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Controls that need permission are shown only to people
               who hold it (RES-10).

.. moduleauthor:: Code Craft AI LLC

A least-privilege lab user saw Create, Edit, Delete, Force check-in and
Configure on 11 of the 13 resources pages and was bounced with "You do
not have permission to access this page" when they used one. The pages
already received the flag (``can_manage``, the same probe the handlers
gate on); the templates used it once. Every control that leads to a
handler gated on ``system:resources.manage`` is now shown only to people
who hold it, and editing or cancelling a reservation (which only its
owner may do) only to its owner. The projects list shows Edit only on
projects the person may edit.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from typing import Dict, List, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_viewer,
    login_via_post,
)


_STATE: Dict[str, object] = {}


def _id_from(response, *, prefix: str) -> str:
    location = response.header("Location") or ""
    match = re.search(re.escape(prefix) + r"/(\d+)", location)
    testbase.assert_true(match is not None, "no id in the redirect: {} {}".format(response.status_code, location))
    return match.group(1)


def _lab() -> Dict[str, object]:
    """
        One lab, built once: a device, a resource pool, an IP pool, a
        check-out held by the administrator on the device, one held by
        the viewer on a second device, and a reservation the
        administrator owns. Returns the ids and both cookie jars.
    """
    if "lab" in _STATE:
        return _STATE["lab"]
    admin = admin_cookies()
    viewer = ensure_seeded_viewer()
    _response, viewer_cookies = login_via_post(wsgi_app=app(), login=viewer.login, password=viewer.password)

    def create_device() -> str:
        created = post_form(
            path="/resources/create",
            fields={"name": unique_name(prefix="mc"), "resource_type": "device", "pool_id": "",
                    "description": "", "capacity": "1", "metadata": "{}"},
            cookies=admin,
        )
        return _id_from(created, prefix="/resources")

    device = create_device()
    second_device = create_device()
    pool = _id_from(
        post_form(path="/resources/pools/create",
                  fields={"name": unique_name(prefix="mcpool"), "description": ""}, cookies=admin),
        prefix="/resources/pools",
    )
    first = uuid.uuid4().int % 200 + 20
    second = uuid.uuid4().int % 200 + 20
    ip_pool = _id_from(
        post_form(path="/resources/ip-pools/create",
                  fields={"name": unique_name(prefix="mcip"), "cidr": "10.{}.{}.0/29".format(first, second),
                          "gateway": "", "dns_servers": "", "reserved_ips": "", "description": ""},
                  cookies=admin),
        prefix="/resources/ip-pools",
    )
    post_form(path="/resources/{}/checkout".format(device),
              fields={"mode": "exclusive", "job_id": "", "timeout_minutes": "", "reason": "held by the admin"},
              cookies=admin)
    post_form(path="/resources/{}/checkout".format(second_device),
              fields={"mode": "exclusive", "job_id": "", "timeout_minutes": "", "reason": "held by the viewer"},
              cookies=viewer_cookies)
    reservation = _id_from(
        post_form(path="/resources/reservations/create",
                  fields={"resource_id": device, "start_time": "2031-03-01T10:00", "end_time": "2031-03-01T11:00",
                          "tz": "UTC", "mode": "exclusive", "job_id": "", "reason": ""},
                  cookies=admin),
        prefix="/resources/reservations",
    )
    allocations = get(path="/resources/allocations", cookies=admin).text
    rows = re.findall(r"<tr>(.*?)</tr>", allocations, re.S)
    admin_allocation = viewer_allocation = ""
    for row in rows:
        found = re.search(r"/resources/allocations/(\d+)", row)
        if found is None:
            continue
        if "/resources/{}\"".format(device) in row or "/resources/{}>".format(device) in row:
            admin_allocation = found.group(1)
        if "/resources/{}\"".format(second_device) in row or "/resources/{}>".format(second_device) in row:
            viewer_allocation = found.group(1)
    testbase.assert_true(len(admin_allocation) > 0 and len(viewer_allocation) > 0, "allocations not found")
    _STATE["lab"] = {
        "device": device, "pool": pool, "ip_pool": ip_pool, "reservation": reservation,
        "admin_allocation": admin_allocation, "viewer_allocation": viewer_allocation,
        "admin": admin, "viewer": viewer_cookies,
    }
    return _STATE["lab"]


def _page(path: str, *, who: str) -> str:
    lab = _lab()
    response = get(path=path.format(**lab), cookies=lab[who])
    testbase.assert_equal(response.status_code, 200, path)
    return response.text


def _controls(path: str, needles: List[str]) -> Tuple[List[str], List[str]]:
    """
        ``(the needles the viewer's page has, the ones the administrator's
        page lacks)``.
    """
    viewer_page = _page(path, who="viewer")
    admin_page = _page(path, who="admin")
    lab = _lab()
    filled = [needle.format(**lab) for needle in needles]
    rtnval = (
        [needle for needle in filled if needle in viewer_page],
        [needle for needle in filled if needle not in admin_page],
    )
    return rtnval


def test_the_dashboard_offers_creating_only_to_managers():
    """
    **Feature: manage controls (RES-10)**
    **Property: the dashboard's Create Resource / Pool / IP Pool links
    are on the administrator's page and not on a plain user's.**
    """
    testbase.assert_equal(
        _controls("/resources/dashboard", ['href="/resources/create"', 'href="/resources/pools/create"', 'href="/resources/ip-pools/create"']),
        ([], []),
    )
    return


def test_the_device_list_and_page_offer_edit_and_delete_only_to_managers():
    """
    **Feature: manage controls (RES-10)**
    **Property: Create, Edit and Delete on the device list, and Edit
    and Delete on a device's page, are the administrator's only.**
    """
    testbase.assert_equal(
        (_controls("/resources/list", ['href="/resources/create"', "/edit\"", "/delete\""]),
         _controls("/resources/{device}", ["/resources/{device}/edit", "/resources/{device}/delete"])),
        (([], []), ([], [])),
    )
    return


def test_the_resource_pool_pages_offer_creating_and_deleting_only_to_managers():
    """
    **Feature: manage controls (RES-10)**
    **Property: Create and Delete on the pool list, and Add Resource
    and Delete on a pool's page, are the administrator's only.**
    """
    testbase.assert_equal(
        (_controls("/resources/pools", ['href="/resources/pools/create"', "/resources/pools/{pool}/delete"]),
         _controls("/resources/pools/{pool}", ["/resources/create?pool_id={pool}", "/resources/pools/{pool}/delete"])),
        (([], []), ([], [])),
    )
    return


def test_the_ip_pool_pages_offer_creating_editing_and_deleting_only_to_managers():
    """
    **Feature: manage controls (RES-10)**
    **Property: Create, Edit and Delete on the IP pool list, and Edit
    and Delete on an IP pool's page, are the administrator's only.**
    """
    testbase.assert_equal(
        (_controls("/resources/ip-pools", ['href="/resources/ip-pools/create"', "/resources/ip-pools/{ip_pool}/edit", "/resources/ip-pools/{ip_pool}/delete"]),
         _controls("/resources/ip-pools/{ip_pool}", ["/resources/ip-pools/{ip_pool}/edit", "/resources/ip-pools/{ip_pool}/delete"])),
        (([], []), ([], [])),
    )
    return


def test_force_check_in_is_offered_only_to_managers_on_someone_elses_allocation():
    """
    **Feature: manage controls (RES-10)**
    **Property: on an allocation another person holds, Force check in
    is on the administrator's pages and not on a plain user's; a plain
    user still has Check in on their own allocation.**
    """
    lab = _lab()
    viewer_on_admins = get(path="/resources/allocations/{}".format(lab["admin_allocation"]), cookies=lab["viewer"]).text
    admin_on_viewers = get(path="/resources/allocations/{}".format(lab["viewer_allocation"]), cookies=lab["admin"]).text
    viewer_on_own = get(path="/resources/allocations/{}".format(lab["viewer_allocation"]), cookies=lab["viewer"]).text
    viewer_list = get(path="/resources/allocations", cookies=lab["viewer"]).text
    admin_list = get(path="/resources/allocations", cookies=lab["admin"]).text
    force = "allocations/{}/force-checkin"

    testbase.assert_equal(
        (force.format(lab["admin_allocation"]) in viewer_on_admins,
         force.format(lab["viewer_allocation"]) in admin_on_viewers,
         "allocations/{}/checkin".format(lab["viewer_allocation"]) in viewer_on_own,
         force.format(lab["admin_allocation"]) in viewer_list,
         force.format(lab["viewer_allocation"]) in admin_list),
        (False, True, True, False, True),
    )
    return


def test_only_the_owner_is_offered_edit_and_cancel_on_a_reservation():
    """
    **Feature: manage controls (RES-10)**
    **Property: a reservation's Edit and Cancel are on the owner's
    pages and not on another person's, in the list and on its page.**
    """
    lab = _lab()
    edit = "reservations/{}/edit".format(lab["reservation"])
    cancel = "reservations/{}/cancel".format(lab["reservation"])
    owner_page = get(path="/resources/reservations/{}".format(lab["reservation"]), cookies=lab["admin"]).text
    other_page = get(path="/resources/reservations/{}".format(lab["reservation"]), cookies=lab["viewer"]).text
    owner_list = get(path="/resources/reservations", cookies=lab["admin"]).text
    other_list = get(path="/resources/reservations", cookies=lab["viewer"]).text

    testbase.assert_equal(
        (edit in owner_page and cancel in owner_page, edit in other_page or cancel in other_page,
         edit in owner_list and cancel in owner_list, edit in other_list or cancel in other_list),
        (True, False, True, False),
    )
    return


def test_the_health_page_offers_status_changes_and_checks_only_to_managers():
    """
    **Feature: manage controls (RES-10)**
    **Property: on a device's health page, the status form, Configure
    Health Check and Run Health Check are the administrator's only.**
    """
    testbase.assert_equal(
        _controls("/resources/health/{device}", [
            "/resources/health/{device}/update", "/resources/health/{device}/config", "/resources/health/{device}/check",
        ]),
        ([], []),
    )
    return


def test_the_projects_list_offers_edit_only_on_projects_the_person_may_edit():
    """
    **Feature: manage controls (RES-10, PRJ-34)**
    **Property: a project the viewer is only a viewer of appears in
    their list without an Edit link, and in the administrator's list
    with one.**
    """
    from ccai.pychestrate.core.managers.project_manager import (  # noqa: E402
        ProjectManager,
        ProjectRole,
    )
    from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
        create_project_via_ui,
        open_db_session,
    )

    lab = _lab()
    project_id = create_project_via_ui(wsgi_app=app(), cookies=lab["admin"], prefix="mc-proj")
    viewer = ensure_seeded_viewer()
    db_session = open_db_session()
    try:
        ProjectManager(db_session).add_member(project_id, viewer.user_id, ProjectRole("viewer"), viewer.user_id)
    finally:
        db_session.close()
    edit = 'href="/projects/{}/edit"'.format(project_id)
    view = 'href="/projects/{}"'.format(project_id)
    viewer_page = get(path="/projects/list", cookies=lab["viewer"]).text
    admin_page = get(path="/projects/list", cookies=lab["admin"], query={"search": "mc-proj"}).text

    testbase.assert_equal(
        (view in viewer_page, edit in viewer_page, edit in admin_page),
        (True, False, True),
    )
    return
