"""
.. module:: test_p31zzm_project_builds_page_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A project's builds are on the Builds page, not the retired list (PRJ-07).

.. moduleauthor:: Code Craft AI LLC

Nothing in this version picks up a build made on a project's own Builds page
(``BuildManager`` is called only from those pages), so every such build waited
in "pending" while its log page said "Live: refreshing every 10s". The
orchestration model behind the site-wide Builds page does dispatch. The
project sidebar's Builds entry now opens that page filtered to the project
(``/projects/{id}/open/builds``); the older pages stay reachable by address
with a notice that says what happens to a build made there, and a build that
has not started is "Waiting" in its log, not "Live".
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from types import SimpleNamespace
from typing import Any, Dict, List

from ccai import testbase

from ccai.pychestrate.core.orm import ProjectJobStatus
from ccai.pychestrate.webservice.projects.repository import get_project_by_legacy_id

from ccai.testshared.factories.webui.dataclass_fixtures import MODE_SPARSE
from ccai.testshared.factories.webui.template_contexts import build_template_context

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    open_db_session,
)
from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


def _render(template_name: str, **overrides: Any) -> str:
    context = build_template_context(
        template_name=template_name,
        variable_names=undeclared_variables(template_name=template_name),
        mode=MODE_SPARSE,
    )
    context.update(overrides)
    rendered = html.unescape(strict_environment().get_template(template_name).render(context))
    return re.sub(r"[ \t\r\n]+", " ", rendered)


def _build(status: ProjectJobStatus) -> Any:
    """A build in the given state, with what the logs page reads."""
    return SimpleNamespace(id=7, spec_name="unit", status=status, branch="main", commit_sha="HEAD")


def _sidebar_href(rendered: str, label: str) -> str:
    nav = re.search(r'<nav class="pyc-subnav".*?</nav>', rendered, re.S)
    for href, text in re.findall(r'<a href="([^"]*)"[^>]*>(.*?)</a>', nav.group(0), re.S):
        if re.sub(r"<[^>]+>|\s+", " ", text).strip() == label:
            return href
    return ""


def test_the_sidebar_builds_entry_opens_the_site_wide_builds_page_for_the_project():
    """
    **Feature: project builds on the Builds page (PRJ-07)**
    **Property: the project sidebar's Builds entry links to
    ``/projects/{id}/open/builds``, not to the retired project build list.**
    """
    href = _sidebar_href(_render("projects/releases/list.html"), "Builds")

    testbase.assert_equal("/open/builds" in href, True)
    return


def test_the_older_build_pages_say_a_build_made_there_is_not_run():
    """
    **Feature: project builds on the Builds page (PRJ-07)**
    **Property: the older build list carries a notice that a build started
    there is not run and links to the Builds page; a page that is not a build
    page (Releases) carries no such notice.**
    """
    build_list = _render("projects/builds/list.html", request_endpoint="projects.build_list")
    releases = _render("projects/releases/list.html", request_endpoint="projects.release_list")

    testbase.assert_equal(
        (
            'data-role="preview-notice"' in build_list and "is not run" in build_list,
            "/open/builds" in build_list.split('data-role="preview-notice"', 1)[1].split("</div>", 1)[0],
            "is not run" in releases,
        ),
        (True, True, False),
    )
    return


def test_a_build_that_has_not_started_is_waiting_not_live():
    """
    **Feature: project builds on the Builds page (PRJ-07)**
    **Property: the log page of a pending build says "Waiting" and has no
    "Live: refreshing"; a running build still says "Live"; a finished one
    says "Finished".**
    """
    def status_text(status: ProjectJobStatus) -> str:
        page = _render("projects/builds/logs.html", build=_build(status), logs="", selected_step=None, request_endpoint="projects.build_logs")
        match = re.search(r'data-log-status role="status">([^<]*)<', page)
        return match.group(1) if match else ""

    pending = status_text(ProjectJobStatus.PENDING)
    running = status_text(ProjectJobStatus.RUNNING)
    finished = status_text(ProjectJobStatus.SUCCEEDED)

    testbase.assert_equal(
        (pending.startswith("Waiting"), "Live" in pending, running.startswith("Live"), finished.startswith("Finished")),
        (True, False, True, True),
    )
    return


def test_the_open_link_for_builds_goes_to_the_builds_page_filtered_to_the_project():
    """
    **Feature: project builds on the Builds page (PRJ-07)**
    **Property: ``/projects/{id}/open/builds`` redirects to ``/builds`` with
    ``?project_id=`` set to the project's registry id.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="prj07" + uuid.uuid4().hex[:4])
    db_session = open_db_session()
    try:
        registry_id = str(get_project_by_legacy_id(db_session=db_session, legacy_proj_id=project_id).project_id)
    finally:
        db_session.close()
    response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/projects/{}/open/builds".format(project_id), cookies=cookies)

    testbase.assert_equal(
        (response.status_code, response.header("Location")),
        (302, "/builds?project_id=" + registry_id),
    )
    return
