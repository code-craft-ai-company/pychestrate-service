"""
.. module:: test_p31zzj_project_sidebar_working_pages_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A project's sidebar lists only sections that can hold data (PRJ-08).

.. moduleauthor:: Code Craft AI LLC

Eight of the project sidebar's sixteen destinations could never contain
anything: nothing creates a test or infrastructure specification, a release
pipeline, a channel, a schedule or a calendar event in the web-UI project
model. Labelling them "(preview)" (see ``test_p31zl``) was honest but left
eight dead ends in the navigation. The sidebar now lists the sections that
work, and reaches the pages where the same things do work -- Runs, Pipelines
and the Test catalog -- through ``/projects/{id}/open/{destination}``, which
opens the site-wide page filtered to the project. The old addresses still
open, with their Preview notice.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from typing import Any, Dict, List, Optional

from ccai import testbase

from ccai.pychestrate.webservice.projects.repository import get_project_by_legacy_id

from ccai.testshared.factories.webui.dataclass_fixtures import MODE_SPARSE
from ccai.testshared.factories.webui.template_contexts import build_template_context

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    ensure_seeded_viewer,
    login_as,
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


#: The sidebar entries that lead to lists nothing can fill.
DEAD_END_LABELS: List[str] = ["Infrastructure", "Tests", "Channels", "Schedules", "Calendar"]


def _render(template_name: str) -> str:
    context = build_template_context(
        template_name=template_name,
        variable_names=undeclared_variables(template_name=template_name),
        mode=MODE_SPARSE,
    )
    return html.unescape(strict_environment().get_template(template_name).render(context))


def _sidebar_links(rendered: str) -> List[Any]:
    """The (label, href) of every link in the project sidebar."""
    nav = re.search(r'<nav class="pyc-subnav".*?</nav>', rendered, re.S)
    assert nav is not None, "the page has no project sidebar"
    links = re.findall(r'<a href="([^"]*)"[^>]*>(.*?)</a>', nav.group(0), re.S)
    rtnval = [(re.sub(r"<[^>]+>|\s+", " ", label).strip(), href) for href, label in links]
    return rtnval


def test_the_sidebar_lists_no_section_nothing_can_fill():
    """
    **Feature: a project sidebar without dead ends (PRJ-08)**
    **Property: the project sidebar has no Infrastructure, Tests, Channels,
    Schedules or Calendar entry, no "(preview)" label, and no second
    "Pipelines" that leads to the empty release pipelines.**
    """
    links = _sidebar_links(_render("projects/releases/pipeline_list.html"))
    labels = [label for label, _href in links]
    hrefs = [href for _label, href in links]

    testbase.assert_equal(
        (
            [label for label in labels if label in DEAD_END_LABELS or "preview" in label],
            [href for href in hrefs if href.endswith("/pipelines") and "/open/" not in href],
        ),
        ([], []),
    )
    return


def test_the_sidebar_reaches_runs_pipelines_and_the_test_catalog_for_this_project():
    """
    **Feature: a project sidebar without dead ends (PRJ-08)**
    **Property: the sidebar lists Runs, Pipelines and Test catalog, each
    through the project's ``/open/`` link, and keeps the sections that work
    (Builds, Releases, Release Templates, Watches).**
    """
    links = _sidebar_links(_render("projects/releases/pipeline_list.html"))
    by_label = dict(links)

    testbase.assert_equal(
        (
            [label for label in ("Runs", "Pipelines", "Test catalog") if "/open/" in by_label.get(label, "")],
            [label for label in ("Builds", "Releases", "Release Templates", "Watches") if label not in by_label],
        ),
        (["Runs", "Pipelines", "Test catalog"], []),
    )
    return


def test_the_project_overview_points_its_tests_card_at_runs():
    """
    **Feature: a project sidebar without dead ends (PRJ-08)**
    **Property: with no legacy test jobs the Recent Tests card offers no
    link to the empty Tests list, links to Runs instead, and says where a
    test run is listed.**
    """
    rendered = _render("projects/projects/detail.html")
    card = rendered[rendered.index("Recent Tests"):]
    card = card[:card.index("Team Members")]

    testbase.assert_equal(
        (
            "/tests" in card,
            "/open/runs" in card,
            "listed under Runs" in card,
        ),
        (False, True, True),
    )
    return


def test_the_releases_list_no_longer_links_to_the_empty_pipelines_and_channels():
    """
    **Feature: a project sidebar without dead ends (PRJ-08)**
    **Property: the Releases list has no Pipelines or Channels buttons.**
    """
    rendered = _render("projects/releases/list.html")
    hrefs = re.findall(r'href="([^"]*)"', rendered)

    testbase.assert_equal(
        (
            [href for href in hrefs if href.endswith("/pipelines") and "/open/" not in href],
            [href for href in hrefs if href.endswith("/channels")],
            "rss_feed" in rendered,
        ),
        ([], [], False),
    )
    return


# ---------------------------------------------------------------------------
# The link, live
# ---------------------------------------------------------------------------


def _get(wsgi_app: Any, cookies: Optional[Dict[str, str]], path: str) -> Any:
    rtnval = drive_request(wsgi_app=wsgi_app, method="GET", path=path, cookies=cookies)
    return rtnval


def test_the_open_link_sends_a_project_to_the_site_wide_page_filtered_to_it():
    """
    **Feature: a project sidebar without dead ends (PRJ-08)**
    **Property: ``/projects/{id}/open/runs``, ``pipelines`` and
    ``test-catalog`` redirect to ``/runs``, ``/pipelines`` and
    ``/test-catalog`` with ``?project_id=`` set to the project's registry
    id; an unknown destination goes back to the project with a notice;
    an unknown project goes to the project list.**
    """
    handle = ensure_app()
    wsgi_app = handle.wsgi_app
    cookies = logged_in_cookies(wsgi_app=wsgi_app)
    project_id = create_project_via_ui(wsgi_app=wsgi_app, cookies=cookies, prefix="prj08n" + uuid.uuid4().hex[:4])
    db_session = open_db_session()
    try:
        registry_id = str(get_project_by_legacy_id(db_session=db_session, legacy_proj_id=project_id).project_id)
    finally:
        db_session.close()

    seen: List[Any] = []
    for destination, path in (("runs", "/runs"), ("pipelines", "/pipelines"), ("test-catalog", "/test-catalog")):
        response = _get(wsgi_app, cookies, "/projects/{}/open/{}".format(project_id, destination))
        seen.append((response.status_code, response.header("Location")))
    unknown_destination = _get(wsgi_app, cookies, "/projects/{}/open/nowhere".format(project_id))
    unknown_project = _get(wsgi_app, cookies, "/projects/99999999/open/runs")

    testbase.assert_equal(
        (
            seen,
            (unknown_destination.status_code, unknown_destination.header("Location")),
            (unknown_project.status_code, unknown_project.header("Location")),
        ),
        (
            [
                (302, "/runs?project_id=" + registry_id),
                (302, "/pipelines?project_id=" + registry_id),
                (302, "/test-catalog?project_id=" + registry_id),
            ],
            (303, "/projects/{}".format(project_id)),
            (303, "/projects/list"),
        ),
    )
    return


def test_the_open_link_needs_a_sign_in_and_view_access():
    """
    **Feature: a project sidebar without dead ends (PRJ-08)**
    **Property: a person who is not signed in is sent to the sign-in page,
    and a signed-in person with no access to the project is sent to the
    project list instead of to the project's pages.**
    """
    handle = ensure_app()
    wsgi_app = handle.wsgi_app
    owner_cookies = logged_in_cookies(wsgi_app=wsgi_app)
    project_id = create_project_via_ui(wsgi_app=wsgi_app, cookies=owner_cookies, prefix="prj08a" + uuid.uuid4().hex[:4])
    viewer_cookies = login_as(wsgi_app=wsgi_app, user=ensure_seeded_viewer())

    anonymous = _get(wsgi_app, None, "/projects/{}/open/runs".format(project_id))
    outsider = _get(wsgi_app, viewer_cookies, "/projects/{}/open/runs".format(project_id))

    testbase.assert_equal(
        (
            anonymous.status_code,
            (anonymous.header("Location") or "").startswith("/login"),
            outsider.status_code,
            "project_id" in (outsider.header("Location") or ""),
        ),
        (302, True, 302, False),
    )
    return
