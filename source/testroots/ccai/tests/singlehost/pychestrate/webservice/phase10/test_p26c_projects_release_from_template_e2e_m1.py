"""
.. module:: test_p26c_projects_release_from_template_e2e_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: End-to-end tests for creating a release from a release
               template in the consumer UI (PRJ-09).

.. moduleauthor:: Code Craft AI LLC

There was no way to create a release from a template in the UI. The
template page now has a "Create release" form; the release page shows
which template the release came from and what it contributed.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    open_db_session,
    post_form,
)


def _project_with_template(*, wsgi_app: Any, cookies: Dict[str, str], prefix: str) -> Tuple[int, int]:
    """
        Create a project through the UI and give it a release template
        (channel "stable", pattern for x.y.z versions).

        :returns: Tuple of (project_id, template_id).
    """
    from ccai.pychestrate.core.managers.release_template_manager import (  # noqa: E402
        ReleaseTemplateManager,
    )

    project_id = create_project_via_ui(wsgi_app=wsgi_app, cookies=cookies, prefix=prefix)
    db_session = open_db_session()
    try:
        template = ReleaseTemplateManager(db_session=db_session).create(
            project_id, name="standard", default_channel="stable",
            version_pattern=r"^\d+\.\d+\.\d+$",
        )
        template_id = template.id
    finally:
        db_session.close()
    rtnval = (project_id, template_id)
    return rtnval


def _release_count(*, project_id: int) -> int:
    from ccai.pychestrate.core.orm import ProjectRelease  # noqa: E402

    db_session = open_db_session()
    try:
        rtnval = db_session.query(ProjectRelease).filter(ProjectRelease.project_id == project_id).count()
    finally:
        db_session.close()
    return rtnval


def test_create_release_from_template_opens_the_new_release():
    """
    **Feature: projects release templates (PRJ-09)**
    **Property: POSTing a version to the template's create-release form
    redirects to the new release's page.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id, template_id = _project_with_template(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj09-create"
    )

    response = post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/release-templates/{}/create-release".format(project_id, template_id),
        cookies=cookies,
        fields={"version": "1.4.0", "name": ""},
    )

    location = response.header("Location") or ""
    pattern = r"^/projects/{}/releases/\d+$".format(project_id)
    testbase.assert_equal(re.match(pattern, location) is not None, True)
    return


def test_release_page_shows_the_template_it_came_from():
    """
    **Feature: projects release templates (PRJ-09)**
    **Property: the page of a release created from a template names the
    template and shows the channel it contributed.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id, template_id = _project_with_template(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj09-prov"
    )
    response = post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/release-templates/{}/create-release".format(project_id, template_id),
        cookies=cookies,
        fields={"version": "2.0.0", "name": ""},
    )

    page = get_page(wsgi_app=handle.wsgi_app, path=response.header("Location"), cookies=cookies)

    testbase.assert_equal(
        ("Created from template" in page.text, "standard" in page.text, "stable" in page.text),
        (True, True, True),
    )
    return


def test_a_version_outside_the_pattern_is_refused_next_to_the_field():
    """
    **Feature: projects release templates (PRJ-09)**
    **Property: a version that does not match the template's pattern
    re-renders the template page (400) with the message at the version
    field, and creates no release.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id, template_id = _project_with_template(
        wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj09-bad"
    )

    response = post_form(
        wsgi_app=handle.wsgi_app,
        path="/projects/{}/release-templates/{}/create-release".format(project_id, template_id),
        cookies=cookies,
        fields={"version": "1.4.0-rc1", "name": ""},
    )

    testbase.assert_equal(
        (
            response.status_code,
            'id="version-error"' in response.text,
            _release_count(project_id=project_id),
        ),
        (400, True, 0),
    )
    return
