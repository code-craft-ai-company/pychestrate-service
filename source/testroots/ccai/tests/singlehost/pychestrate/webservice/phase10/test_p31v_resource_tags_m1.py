"""
.. module:: test_p31v_resource_tags_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tags can be made, renamed and deleted in the interface
               (RES-06).

.. moduleauthor:: Code Craft AI LLC

The tag checkboxes on the resource forms only appeared once tags
existed, and the Tags page said tags were "created automatically when
assigned" while nothing could assign a new one: a specialist had to
forge a POST. The Tags page now has a form that makes a tag (name and
description), an Edit page that renames it (resources that carry it keep
it), and a Delete that takes it off every resource. The resource create
and edit forms have a "New tags" input for tags that do not exist yet.
Errors show beside the input. Managing tags needs the
resource-management permission; anyone can still read the list.
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
    get,
    merge_cookies,
    post_form,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_viewer,
    login_via_post,
)


def _tag_name(prefix: str = "tg") -> str:
    return "{}-{}".format(prefix, uuid.uuid4().hex[:8])


def _tag_id(name: str, cookies: Dict[str, str]) -> str:
    page = get(path="/resources/tags", cookies=cookies, query={"search": name}).text
    row = re.search(r'<span class="badge badge-info">' + re.escape(name) + r"</span>.*?/resources/tags/(\d+)/edit", page, re.S)
    testbase.assert_true(row is not None, "tag {} not on the page".format(name))
    return row.group(1)


def _listed(name: str, page: str) -> bool:
    """
        Whether the Tags page lists ``name`` as a tag (the search box
        echoes what was searched for, so the name alone proves nothing).
    """
    return '<span class="badge badge-info">{}</span>'.format(name) in page


def _input_tag(page: str, field_id: str) -> str:
    match = re.search(r'<input[^>]*\bid="' + re.escape(field_id) + r'"[^>]*>', page, re.S)
    return match.group(0) if match is not None else ""


def _error_text(page: str, field_id: str) -> str:
    match = re.search(r'id="' + re.escape(field_id) + r'-error"[^>]*>(.*?)</div>', page, re.S)
    return html.unescape(match.group(1).strip()) if match is not None else ""


def _new_resource(cookies: Dict[str, str], **extra: str) -> Tuple[str, Dict[str, str]]:
    fields = {"name": _tag_name("tagres"), "resource_type": "device", "pool_id": "", "description": "",
              "capacity": "1", "metadata": "{}"}
    fields.update(extra)
    response = post_form(path="/resources/create", fields=fields, cookies=cookies)
    location = response.header("Location") or ""
    match = re.search(r"/resources/(\d+)", location)
    return (match.group(1) if match is not None else "", {"status": str(response.status_code), "text": response.text})


def _resource_page(resource_id: str, cookies: Dict[str, str]) -> str:
    return get(path="/resources/{}".format(resource_id), cookies=cookies).text


def test_a_manager_makes_a_tag_with_a_description():
    """
    **Feature: resource tags (RES-06)**
    **Property: the Tags page's form makes a tag that then appears in the
    list with its description.**
    """
    admin = admin_cookies()
    name = _tag_name()
    response = post_form(
        path="/resources/tags/create", fields={"name": name, "description": "Front rack of the lab"}, cookies=admin,
    )
    listing = get(path="/resources/tags", cookies=admin, query={"search": name}).text

    testbase.assert_equal(
        (response.status_code, _listed(name, listing), "Front rack of the lab" in listing),
        (303, True, True),
    )
    return


def test_a_refused_tag_name_is_shown_beside_the_name_and_keeps_what_was_typed():
    """
    **Feature: resource tags (RES-06)**
    **Property: a tag name with a space, and a name that already exists,
    each answer 400 with the message beside the name input and the typed
    description kept.**
    """
    admin = admin_cookies()
    taken = _tag_name()
    post_form(path="/resources/tags/create", fields={"name": taken, "description": ""}, cookies=admin)
    bad = post_form(path="/resources/tags/create", fields={"name": "not a name", "description": "kept text"}, cookies=admin)
    duplicate = post_form(path="/resources/tags/create", fields={"name": taken, "description": ""}, cookies=admin)

    testbase.assert_equal(
        (bad.status_code, len(_error_text(bad.text, "name")) > 0, 'aria-invalid="true"' in _input_tag(bad.text, "name"),
         'value="kept text"' in _input_tag(bad.text, "description"),
         duplicate.status_code, "already exists" in _error_text(duplicate.text, "name")),
        (400, True, True, True, 400, True),
    )
    return


def test_a_person_without_the_permission_cannot_manage_tags_and_is_not_offered_it():
    """
    **Feature: resource tags (RES-06)**
    **Property: a plain user's Tags page has no create form and no Edit
    or Delete; posting a create anyway is refused with a message naming
    the action, and nothing is made.**
    """
    viewer = ensure_seeded_viewer()
    _response, cookies = login_via_post(wsgi_app=app(), login=viewer.login, password=viewer.password)
    name = _tag_name()
    page = get(path="/resources/tags", cookies=cookies).text
    response = post_form(path="/resources/tags/create", fields={"name": name, "description": ""}, cookies=cookies)
    followed = get(path=response.header("Location") or "/", cookies=merge_cookies(cookies=cookies, response=response))
    listing = get(path="/resources/tags", cookies=admin_cookies(), query={"search": name}).text

    testbase.assert_equal(
        ("/resources/tags/create" in page, "/edit" in page, "/delete" in page,
         "You need the resource-management permission to create a tag." in html.unescape(followed.text),
         _listed(name, listing)),
        (False, False, False, True, False),
    )
    return


def test_renaming_a_tag_keeps_it_on_the_resources_that_carry_it():
    """
    **Feature: resource tags (RES-06)**
    **Property: after a tag is renamed, a resource that carried it shows
    the new name and not the old one; a name that is invalid or taken
    is refused beside the name input.**
    """
    admin = admin_cookies()
    old = _tag_name("old")
    new = _tag_name("new")
    other = _tag_name("other")
    post_form(path="/resources/tags/create", fields={"name": other, "description": ""}, cookies=admin)
    resource_id, _info = _new_resource(admin, new_tags=old)
    tag_id = _tag_id(old, admin)
    renamed = post_form(
        path="/resources/tags/{}/edit".format(tag_id), fields={"name": new, "description": "renamed"}, cookies=admin,
    )
    page = _resource_page(resource_id, admin)
    taken = post_form(path="/resources/tags/{}/edit".format(tag_id), fields={"name": other, "description": ""}, cookies=admin)
    invalid = post_form(path="/resources/tags/{}/edit".format(tag_id), fields={"name": "no spaces allowed", "description": ""}, cookies=admin)

    testbase.assert_equal(
        (renamed.status_code, new in page, old in page,
         taken.status_code, "already exists" in _error_text(taken.text, "name"),
         invalid.status_code, len(_error_text(invalid.text, "name")) > 0),
        (303, True, False, 400, True, 400, True),
    )
    return


def test_deleting_a_tag_takes_it_off_the_resources_and_keeps_them():
    """
    **Feature: resource tags (RES-06)**
    **Property: deleting a tag removes it from the list and from a
    resource that carried it; the resource stays; the message says how
    many resources it was taken off.**
    """
    admin = admin_cookies()
    name = _tag_name("del")
    resource_id, _info = _new_resource(admin, new_tags=name)
    tag_id = _tag_id(name, admin)
    response = post_form(path="/resources/tags/{}/delete".format(tag_id), fields={}, cookies=admin)
    message = html.unescape(get(path=response.header("Location") or "/", cookies=merge_cookies(cookies=admin, response=response)).text)
    listing = get(path="/resources/tags", cookies=admin, query={"search": name}).text
    page = get(path="/resources/{}".format(resource_id), cookies=admin)

    testbase.assert_equal(
        (response.status_code, "removed from 1 resource" in message, _listed(name, listing), page.status_code, name in page.text),
        (303, True, False, 200, False),
    )
    return


def test_a_new_tag_can_be_typed_when_creating_a_resource():
    """
    **Feature: resource tags (RES-06)**
    **Property: typing "alpha-x beta-x, gamma-x" in the new tags input
    of the create form makes the three tags and puts them on the new
    resource, and the Tags page lists them.**
    """
    admin = admin_cookies()
    suffix = uuid.uuid4().hex[:6]
    names = ["alpha-" + suffix, "beta-" + suffix, "gamma-" + suffix]
    resource_id, info = _new_resource(admin, new_tags="{} {}, {}".format(*names))
    page = _resource_page(resource_id, admin) if resource_id else ""
    listing = get(path="/resources/tags", cookies=admin, query={"search": suffix}).text

    testbase.assert_equal(
        (resource_id != "", all(name in page for name in names), all(_listed(name, listing) for name in names)),
        (True, True, True),
        info["status"],
    )
    return


def test_an_invalid_new_tag_is_shown_beside_the_new_tags_input():
    """
    **Feature: resource tags (RES-06)**
    **Property: a new tag that is not a valid name (a leading dash)
    refuses the create with a 400, the message beside the new-tags
    input naming it, the typed text kept, and no resource made.**
    """
    admin = admin_cookies()
    name = _tag_name("norescreate")
    _resource_id, info = _new_resource(admin, name=name, new_tags="good-one -bad")
    listing = get(path="/resources/list", cookies=admin, query={"search": name}).text

    testbase.assert_equal(
        (info["status"], "-bad" in _error_text(info["text"], "new_tags"),
         'aria-invalid="true"' in _input_tag(info["text"], "new_tags"),
         'value="good-one -bad"' in _input_tag(info["text"], "new_tags"),
         ">{}</a>".format(name) in listing),
        ("400", True, True, True, False),
    )
    return


def test_typing_a_new_tag_when_editing_adds_it_and_keeps_the_others():
    """
    **Feature: resource tags (RES-06)**
    **Property: typing a new tag in the edit form adds it to a resource
    without dropping the tags it already had.**
    """
    admin = admin_cookies()
    existing = _tag_name("keep")
    added = _tag_name("added")
    resource_id, _info = _new_resource(admin, new_tags=existing)
    response = post_form(
        path="/resources/{}/edit".format(resource_id),
        fields=[("tags_present", "1"), ("tags", existing), ("new_tags", added), ("capacity", "1"),
                ("description", ""), ("metadata", "{}")],
        cookies=admin,
    )
    page = _resource_page(resource_id, admin)

    testbase.assert_equal(
        (response.status_code, existing in page, added in page),
        (303, True, True),
    )
    return
