"""
.. module:: test_p31zzzx_release_template_repository_choices_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A release template names its repositories by tick box (PRJ-16).

.. moduleauthor:: Code Craft AI LLC

The release template form asked for "Default Repository IDs" as a text box
("comma-separated, e.g. 12, 34, 56"), and the ids are shown nowhere else in the
interface. The form now lists the project's repositories by name as tick boxes,
on both the create and the edit form. A submission still accepts the older
comma-separated text (a script may send it), a repository the project no longer
has stays ticked and is named as gone so saving does not drop it unseen, and a
rejected submission comes back with the same boxes ticked. These tests drive
the whole application.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import urllib.parse
import uuid

from typing import Any, Dict, List, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    extract_csrf_token_from_cookies,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._test_repository import (
    add_repository,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    open_db_session,
    post_form,
)


def _project(*, wsgi_app: Any, cookies: Dict[str, str], repositories: int) -> Tuple[int, List[Tuple[int, str]]]:
    project_id = create_project_via_ui(wsgi_app=wsgi_app, cookies=cookies, prefix="rtc" + uuid.uuid4().hex[:4])
    made = []
    for index in range(repositories):
        name = "repo{}{}".format(chr(ord("a") + index), uuid.uuid4().hex[:4])
        made.append((add_repository(wsgi_app=wsgi_app, cookies=cookies, project_id=project_id, name=name), name))
    return project_id, made


def _boxes(html: str) -> List[Tuple[str, bool, str]]:
    """``(value, ticked, visible text)`` of each default-repository box on the page."""
    fieldset = re.search(r'<fieldset[^>]*data-role="default-repositories".*?</fieldset>', html, re.S)
    if fieldset is None:
        return []
    found = []
    for box in re.finditer(r'<input type="checkbox"[^>]*name="default_repo_ids"[^>]*>.*?<label[^>]*>(.*?)</label>', fieldset.group(0), re.S):
        tag = box.group(0)
        value = re.search(r'value="(\d+)"', tag).group(1)
        text = re.sub(r"<[^>]+>", "", box.group(1)).strip()
        found.append((value, " checked" in tag.split(">")[0], text))
    return found


def _template_ids(*, project_id: int, template_id: int) -> List[int]:
    from ccai.pychestrate.core.managers.release_template_manager import (  # noqa: E402
        ReleaseTemplateManager,
    )
    db_session = open_db_session()
    try:
        return list(ReleaseTemplateManager(db_session=db_session).get(template_id).default_repo_ids)
    finally:
        db_session.close()


def _create(*, wsgi_app: Any, cookies: Dict[str, str], project_id: int, fields: Dict[str, Any]) -> Any:
    return post_form(wsgi_app=wsgi_app, path="/projects/{}/release-templates/create".format(project_id), cookies=cookies, fields=fields)


def _create_ticking(*, wsgi_app: Any, cookies: Dict[str, str], project_id: int, name: str, ticked: List[int]) -> Any:
    """Submit the create form the way a browser does: the same field once per ticked box."""
    pairs = [("csrf_token", extract_csrf_token_from_cookies(cookies=cookies)), ("name", name)] + [("default_repo_ids", str(repo_id)) for repo_id in ticked]
    rtnval = drive_request(
        wsgi_app=wsgi_app, method="POST", path="/projects/{}/release-templates/create".format(project_id),
        body=urllib.parse.urlencode(pairs).encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded"}, cookies=cookies,
    )
    cookies.update(rtnval.collect_set_cookies())
    return rtnval


def test_the_create_form_offers_the_projects_repositories_by_name():
    """
    **Feature: choices, not ids (PRJ-16)**
    **Property: a project with two repositories gets the create form with
    one unticked box per repository, named by the repository and holding its
    id, and no text field for ids; a project with none says so and links to
    where one is added.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id, made = _project(wsgi_app=handle.wsgi_app, cookies=cookies, repositories=2)
    empty_id, _none = _project(wsgi_app=handle.wsgi_app, cookies=cookies, repositories=0)

    page = get_page(wsgi_app=handle.wsgi_app, path="/projects/{}/release-templates/create".format(project_id), cookies=cookies).text
    empty = get_page(wsgi_app=handle.wsgi_app, path="/projects/{}/release-templates/create".format(empty_id), cookies=cookies).text

    testbase.assert_equal(
        (sorted(_boxes(page)), 'type="text" id="default_repo_ids"' in page, _boxes(empty), 'data-role="no-repositories"' in empty, "/projects/{}/repositories".format(empty_id) in empty),
        (sorted((str(repo_id), False, name) for repo_id, name in made), False, [], True, True),
    )
    return


def test_ticked_repositories_are_saved_and_the_older_comma_list_still_works():
    """
    **Feature: choices, not ids (PRJ-16)**
    **Property: two ticked boxes save both repositories on the template; a
    submission that still sends the older comma-separated text saves the same
    ids; a value that is not a whole number is refused.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id, made = _project(wsgi_app=handle.wsgi_app, cookies=cookies, repositories=2)
    (first_id, _n1), (second_id, _n2) = made

    both = _create_ticking(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id, name="ticks", ticked=[first_id, second_id])
    legacy = _create(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id, fields={"name": "legacy", "default_repo_ids": "{}, {}".format(second_id, first_id)})
    refused = _create(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id, fields={"name": "refused", "default_repo_ids": "abc"})

    def saved(response: Any) -> List[int]:
        found = re.search(r"/release-templates/(\d+)", response.header("Location") or "")
        return _template_ids(project_id=project_id, template_id=int(found.group(1))) if found is not None else []

    testbase.assert_equal(
        (both.status_code in (302, 303), saved(both), saved(legacy), refused.status_code >= 400),
        (True, [first_id, second_id], [second_id, first_id], True),
    )
    return


def test_a_rejected_submission_keeps_the_boxes_ticked():
    """
    **Feature: choices, not ids (PRJ-16)**
    **Property: a create that fails (no name) comes back with the boxes the
    person ticked still ticked, not reset.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id, made = _project(wsgi_app=handle.wsgi_app, cookies=cookies, repositories=3)
    ordered = sorted(made, key=lambda pair: pair[1])
    chosen = ordered[1][0]

    response = _create_ticking(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id, name="", ticked=[chosen])

    testbase.assert_equal(
        (response.status_code >= 400, [(value, ticked) for value, ticked, _text in _boxes(response.text)]),
        (True, [(str(repo_id), repo_id == chosen) for repo_id, _name in ordered]),
    )
    return


def test_the_edit_form_ticks_the_current_repositories_and_unticking_all_clears_them():
    """
    **Feature: choices, not ids (PRJ-16)**
    **Property: the edit form shows the template's repositories ticked and
    the others not; submitting it with none ticked leaves the template with no
    default repositories.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id, made = _project(wsgi_app=handle.wsgi_app, cookies=cookies, repositories=2)
    (first_id, _n1), (second_id, _n2) = sorted(made, key=lambda pair: pair[1])
    created = _create(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id, fields={"name": "editme", "default_repo_ids": str(second_id)})
    template_id = int(re.search(r"/release-templates/(\d+)", created.header("Location") or "").group(1))

    edit_path = "/projects/{}/release-templates/{}/edit".format(project_id, template_id)
    before = _boxes(get_page(wsgi_app=handle.wsgi_app, path=edit_path, cookies=cookies).text)
    saved = post_form(wsgi_app=handle.wsgi_app, path=edit_path, cookies=cookies, fields={"name": "editme"})

    testbase.assert_equal(
        ([(value, ticked) for value, ticked, _text in before], saved.status_code in (302, 303), _template_ids(project_id=project_id, template_id=template_id)),
        ([(str(first_id), False), (str(second_id), True)], True, []),
    )
    return


def test_a_repository_the_project_no_longer_has_stays_ticked_and_is_named_as_gone():
    """
    **Feature: choices, not ids (PRJ-16)**
    **Property: when a template names a repository that has since been
    removed from the project, the edit form still shows it, ticked, as
    "Repository N (no longer in this project)", so saving does not drop it
    unseen.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id, made = _project(wsgi_app=handle.wsgi_app, cookies=cookies, repositories=2)
    (kept_id, _n1), (gone_id, _n2) = made
    created = _create(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id, fields={"name": "stale", "default_repo_ids": "{}, {}".format(kept_id, gone_id)})
    template_id = int(re.search(r"/release-templates/(\d+)", created.header("Location") or "").group(1))
    removed = post_form(wsgi_app=handle.wsgi_app, path="/projects/{}/repositories/{}/delete".format(project_id, gone_id), cookies=cookies, fields={})

    boxes = _boxes(get_page(wsgi_app=handle.wsgi_app, path="/projects/{}/release-templates/{}/edit".format(project_id, template_id), cookies=cookies).text)

    testbase.assert_equal(
        (removed.status_code in (302, 303), [(value, ticked) for value, ticked, _text in boxes if value == str(gone_id)], [text for value, _t, text in boxes if value == str(gone_id)]),
        (True, [(str(gone_id), True)], ["Repository {} (no longer in this project)".format(gone_id)]),
    )
    return
