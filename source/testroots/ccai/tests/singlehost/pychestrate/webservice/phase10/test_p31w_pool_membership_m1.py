"""
.. module:: test_p31w_pool_membership_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A resource can move between pools, and a pool can be
               emptied instead of its devices deleted (RES-08).

.. moduleauthor:: Code Craft AI LLC

A resource could never move between pools (the edit form had no pool
field), the pool page's "Add Resource" made a new resource, and deleting
a pool meant deleting every device in it: the confirmation announced
that it would fail while members existed. The edit form now has a pool
select; a pool's page has "Add existing resources" and "Move resources
out" (to another pool, so the pool can be deleted); a name that already
exists in the target pool stops the move with the reason. Moving needs
the resource-management permission.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from typing import Dict, List, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    merge_cookies,
    post_form,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_viewer,
    login_via_post,
)


def _name(prefix: str) -> str:
    return "{}-{}".format(prefix, uuid.uuid4().hex[:8])


def _pool(cookies: Dict[str, str], prefix: str = "mp") -> Tuple[str, str]:
    name = _name(prefix)
    response = post_form(path="/resources/pools/create", fields={"name": name, "description": ""}, cookies=cookies)
    match = re.search(r"/resources/pools/(\d+)", response.header("Location") or "")
    testbase.assert_true(match is not None, "pool not created: {}".format(response.status_code))
    return (match.group(1), name)


def _resource(cookies: Dict[str, str], pool_id: str, name: str = "") -> str:
    response = post_form(
        path="/resources/create",
        fields={"name": name or _name("mpres"), "resource_type": "device", "pool_id": pool_id,
                "description": "", "capacity": "1", "metadata": "{}"},
        cookies=cookies,
    )
    match = re.search(r"/resources/(\d+)", response.header("Location") or "")
    testbase.assert_true(match is not None, "resource not created: {}".format(response.status_code))
    return match.group(1)


def _in_pool(pool_id: str, resource_id: str, cookies: Dict[str, str]) -> bool:
    page = get(path="/resources/pools/{}".format(pool_id), cookies=cookies).text
    return 'href="/resources/{}"'.format(resource_id) in page


def _messages(response, cookies: Dict[str, str]) -> str:
    followed = get(path=response.header("Location") or "/", cookies=merge_cookies(cookies=cookies, response=response))
    return html.unescape(followed.text)


def _error_text(page: str, field_id: str) -> str:
    match = re.search(r'id="' + re.escape(field_id) + r'-error"[^>]*>(.*?)</div>', page, re.S)
    return html.unescape(match.group(1).strip()) if match is not None else ""


def test_the_edit_form_moves_a_resource_to_another_pool():
    """
    **Feature: pool membership (RES-08)**
    **Property: the edit form has a pool select showing the current pool;
    choosing another pool moves the resource, which then appears on that
    pool's page and not on the first.**
    """
    admin = admin_cookies()
    first, _first_name = _pool(admin)
    second, second_name = _pool(admin)
    resource_id = _resource(admin, first)
    form = get(path="/resources/{}/edit".format(resource_id), cookies=admin).text
    current = re.search(r'<option value="{}"\s+selected'.format(first), form)
    response = post_form(
        path="/resources/{}/edit".format(resource_id),
        fields={"pool_id": second, "description": "", "capacity": "1", "metadata": "{}"}, cookies=admin,
    )

    testbase.assert_equal(
        (current is not None, response.status_code, _in_pool(second, resource_id, admin),
         _in_pool(first, resource_id, admin),
         second_name in get(path="/resources/{}".format(resource_id), cookies=admin).text),
        (True, 303, True, False, True),
    )
    return


def test_a_name_already_in_the_target_pool_is_shown_beside_the_pool_select():
    """
    **Feature: pool membership (RES-08)**
    **Property: moving a resource into a pool that already has one of
    the same name answers 400 with the message beside the pool select,
    and the resource stays where it was.**
    """
    admin = admin_cookies()
    first, _n1 = _pool(admin)
    second, _n2 = _pool(admin)
    same = _name("clash")
    resource_id = _resource(admin, first, name=same)
    _resource(admin, second, name=same)
    response = post_form(
        path="/resources/{}/edit".format(resource_id),
        fields={"pool_id": second, "description": "", "capacity": "1", "metadata": "{}"}, cookies=admin,
    )
    select = re.search(r'<select[^>]*\bid="pool_id"[^>]*>', response.text, re.S)

    testbase.assert_equal(
        (response.status_code, "already in that pool" in _error_text(response.text, "pool_id"),
         select is not None and 'aria-invalid="true"' in select.group(0), _in_pool(first, resource_id, admin)),
        (400, True, True, True),
    )
    return


def test_a_pool_page_adds_existing_resources_and_names_one_it_could_not_move():
    """
    **Feature: pool membership (RES-08)**
    **Property: "Add existing resources" moves the chosen resources into
    the pool; one whose name is already there stays put and the message
    names why.**
    """
    admin = admin_cookies()
    target, _t = _pool(admin)
    source, _s = _pool(admin)
    clash = _name("dupe")
    _resource(admin, target, name=clash)
    movable = _resource(admin, source)
    stuck = _resource(admin, source, name=clash)
    response = post_form(
        path="/resources/pools/{}/add-resources".format(target),
        fields=[("resource_ids", movable), ("resource_ids", stuck)], cookies=admin,
    )
    message = _messages(response, admin)

    testbase.assert_equal(
        (response.status_code, "Added 1 resource to the pool." in message, "already" in message,
         _in_pool(target, movable, admin), _in_pool(target, stuck, admin), _in_pool(source, stuck, admin)),
        (303, True, True, True, False, True),
    )
    return


def test_a_pool_can_be_emptied_into_another_and_then_deleted():
    """
    **Feature: pool membership (RES-08)**
    **Property: "Move resources out" moves every resource of a pool to
    another, after which deleting the pool succeeds and the resources
    are still there.**
    """
    admin = admin_cookies()
    doomed, _d = _pool(admin)
    keeper, _k = _pool(admin)
    resources = [_resource(admin, doomed), _resource(admin, doomed)]
    refused = post_form(path="/resources/pools/{}/delete".format(doomed), fields={}, cookies=admin)
    moved = post_form(path="/resources/pools/{}/move-resources".format(doomed), fields={"target_pool_id": keeper}, cookies=admin)
    message = _messages(moved, admin)
    deleted = post_form(path="/resources/pools/{}/delete".format(doomed), fields={}, cookies=admin)
    still = [get(path="/resources/{}".format(rid), cookies=admin).status_code for rid in resources]

    testbase.assert_equal(
        ("Move or delete them first" in _messages(refused, admin), "Moved 2 resources." in message,
         all(_in_pool(keeper, rid, admin) for rid in resources), deleted.status_code,
         "deleted successfully" in _messages(deleted, admin), still),
        (True, True, True, 303, True, [200, 200]),
    )
    return


def test_a_move_that_would_clash_moves_nothing():
    """
    **Feature: pool membership (RES-08)**
    **Property: moving a pool's resources into a pool that already has
    one of the same name is refused, naming it, and none of the pool's
    resources moves.**
    """
    admin = admin_cookies()
    source, _s = _pool(admin)
    target, _t = _pool(admin)
    same = _name("both")
    first = _resource(admin, source, name=same)
    second = _resource(admin, source)
    _resource(admin, target, name=same)
    response = post_form(path="/resources/pools/{}/move-resources".format(source), fields={"target_pool_id": target}, cookies=admin)
    message = _messages(response, admin)

    testbase.assert_equal(
        (same in message, _in_pool(source, first, admin), _in_pool(source, second, admin)),
        (True, True, True),
    )
    return


def test_only_a_manager_is_offered_and_can_use_the_pool_moves():
    """
    **Feature: pool membership (RES-08)**
    **Property: a plain user's pool page has neither card, and posting
    the actions anyway is refused with a message naming the action and
    moves nothing.**
    """
    admin = admin_cookies()
    viewer = ensure_seeded_viewer()
    _r, viewer_cookies = login_via_post(wsgi_app=app(), login=viewer.login, password=viewer.password)
    target, _t = _pool(admin)
    source, _s = _pool(admin)
    resource_id = _resource(admin, source)
    manager_page = get(path="/resources/pools/{}".format(target), cookies=admin).text
    plain_page = get(path="/resources/pools/{}".format(target), cookies=viewer_cookies).text
    added = post_form(
        path="/resources/pools/{}/add-resources".format(target), fields=[("resource_ids", resource_id)], cookies=viewer_cookies,
    )
    moved = post_form(
        path="/resources/pools/{}/move-resources".format(source), fields={"target_pool_id": target}, cookies=viewer_cookies,
    )

    testbase.assert_equal(
        ("Add existing resources" in manager_page, "Add existing resources" in plain_page,
         "to add resources to a resource pool." in _messages(added, viewer_cookies),
         "to move resources between pools." in _messages(moved, viewer_cookies),
         _in_pool(source, resource_id, admin)),
        (True, False, True, True, True),
    )
    return
