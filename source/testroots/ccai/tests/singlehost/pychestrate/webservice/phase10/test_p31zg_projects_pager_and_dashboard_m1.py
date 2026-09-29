"""
.. module:: test_p31zg_projects_pager_and_dashboard_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The projects pagers keep the page size and show totals, and
               the dashboard's recent activity covers every project
               (PRJ-31).

.. moduleauthor:: Code Craft AI LLC

Every project list dropped the page size when paging ("20 a page" turned
into the default on page two) and none said how many rows there were. The
dashboard built its Recent Builds and Recent Tests from the first ten
projects only, with two queries for each, so activity in the eleventh
project and beyond never appeared. It now reads recent builds and test
jobs across all of a person's projects with one query each, and says when
it lists ten of more projects, with a link to the rest.
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
from urllib.parse import parse_qs, urlparse

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.blueprints.projects import routes as projects_routes

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    ensure_seeded_admin,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    open_db_session,
)


def _admin() -> Dict[str, Any]:
    handle = ensure_app()
    return {"wsgi_app": handle.wsgi_app, "cookies": logged_in_cookies(wsgi_app=handle.wsgi_app)}


def _get(setup: Dict[str, Any], path: str, query: str = "") -> str:
    response = drive_request(wsgi_app=setup["wsgi_app"], method="GET", path=path, query_string=query, cookies=setup["cookies"])
    setup["cookies"].update(response.collect_set_cookies())
    return html.unescape(response.text)


def test_the_project_list_keeps_the_page_size_and_says_how_many_there_are():
    """
    **Feature: projects pager (PRJ-31)**
    **Property: with five projects sharing a name prefix, two to a page,
    the Next link keeps the page size and the search, and the list says
    "Page 1 of 3 · 5 total".**
    """
    setup = _admin()
    prefix = "pgr" + uuid.uuid4().hex[:6]
    for _index in range(5):
        create_project_via_ui(wsgi_app=setup["wsgi_app"], cookies=setup["cookies"], prefix=prefix)
    page = _get(setup, "/projects/list", "search={}&per_page=2".format(prefix))
    found = re.search(r'<a href="([^"]*)" rel="next"', page)
    query = parse_qs(urlparse(found.group(1)).query) if found is not None else {}

    testbase.assert_equal(
        (query.get("per_page"), query.get("search"), "Page 1 of 3 · 5 total" in page),
        (["2"], [prefix], True),
    )
    return


def test_the_project_pagers_all_pass_the_page_size_and_a_total():
    """
    **Feature: projects pager (PRJ-31)**
    **Property: every pager in the projects templates is written with the
    page size and the total, so a list cannot go back to dropping them.**
    """
    import glob
    import os

    import ccai.pychestrate.webservice.webinterface.blueprints.projects as projects_package

    root = os.path.join(os.path.dirname(os.path.abspath(projects_package.__file__)), "templates")
    missing: List[str] = []
    checked = 0
    for path in glob.glob(os.path.join(root, "**", "*.html"), recursive=True):
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for call in re.findall(r"\{\{ ui\.pagination\(.*?\) \}\}", source, re.S):
            checked += 1
            if "'per_page': per_page" not in call or "total=" not in call or "total=None" in call:
                missing.append(os.path.relpath(path, root))

    testbase.assert_equal((checked >= 13, missing), (True, []))
    return


def _project_with_a_build() -> Dict[str, Any]:
    """A project named to sort after every other one, with one build; returns its ids."""
    from ccai.pychestrate.core.orm import (  # noqa: E402
        ProjectBuild, ProjectBuildSpec, ProjectRepository,
    )

    setup = _admin()
    project_id = create_project_via_ui(wsgi_app=setup["wsgi_app"], cookies=setup["cookies"], prefix="zzz-late")
    db_session = open_db_session()
    try:
        repository = ProjectRepository(
            project_id=project_id, name="app", url="https://git.example.invalid/app.git", auth_type="none", default_branch="main",
        )
        db_session.add(repository)
        db_session.flush()
        spec = ProjectBuildSpec(project_id=project_id, repository_id=repository.id, name="late-build")
        db_session.add(spec)
        db_session.flush()
        build = ProjectBuild(
            project_id=project_id, spec_id=spec.id, spec_version=1, branch="main", commit_sha="HEAD", status="pending",
            trigger_type="manual", triggered_by_id=ensure_seeded_admin().user_id,
        )
        db_session.add(build)
        db_session.commit()
        setup["project_id"], setup["build_id"] = project_id, build.id
    finally:
        db_session.close()
    return setup


def test_the_dashboard_shows_recent_activity_from_a_project_past_the_first_ten():
    """
    **Feature: projects dashboard (PRJ-31)**
    **Property: a build in the alphabetically last project (well past the
    ten the dashboard lists) appears under Recent Builds, and when there
    are more than ten projects the dashboard says it shows ten of them and
    links to the list.**
    """
    setup = _admin()
    for _index in range(11):
        create_project_via_ui(wsgi_app=setup["wsgi_app"], cookies=setup["cookies"], prefix="aaa-filler")
    setup = _project_with_a_build()
    page = _get(setup, "/projects/dashboard")
    listed = re.search(r"Showing (\d+) of (\d+) projects", page)

    testbase.assert_equal(
        ("/projects/{}/builds/{}".format(setup["project_id"], setup["build_id"]) in page,
         listed is not None and listed.group(1) == "10" and int(listed.group(2)) > 10,
         'data-role="projects-limit"' in page and "View all" in page),
        (True, True, True),
    )
    return


class _RecordingManager:
    """Stands in for the build and test managers; remembers how it was asked."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        return

    def list_builds(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(builds=[])

    def list_jobs(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(jobs=[])


def test_recent_activity_is_two_queries_however_many_projects_there_are():
    """
    **Feature: projects dashboard (PRJ-31)**
    **Property: reading recent activity for forty projects asks the build
    manager once and the test manager once, each for all forty ids, not
    once per project.**
    """
    builds, jobs = _RecordingManager(), _RecordingManager()
    original = (projects_routes._build_build_manager, projects_routes._build_test_manager)
    projects_routes._build_build_manager = lambda **kwargs: builds
    projects_routes._build_test_manager = lambda **kwargs: jobs
    try:
        result = projects_routes._collect_recent_activity(db_session=None, project_ids=list(range(1, 41)))
    finally:
        projects_routes._build_build_manager, projects_routes._build_test_manager = original

    testbase.assert_equal(
        (len(builds.calls), builds.calls[0].get("project_ids") == list(range(1, 41)),
         len(jobs.calls), jobs.calls[0].get("project_ids") == list(range(1, 41)), result),
        (1, True, 1, True, {"builds": [], "tests": []}),
    )
    return


def test_the_dashboard_reads_a_persons_own_projects_and_a_strangers_are_none():
    """
    **Feature: projects dashboard (PRJ-31)**
    **Property: the ids the dashboard reads for the signed-in
    administrator (who has no global role in the test database, only the
    projects they made) include the project with the build, and for
    someone who belongs to no project the list is empty.**
    """
    from ccai.pychestrate.core.managers.project_manager import ProjectManager  # noqa: E402

    setup = _project_with_a_build()
    db_session = open_db_session()
    try:
        manager = ProjectManager(db_session)
        own_ids = manager.accessible_project_ids(ensure_seeded_admin().user_id)
        stranger_ids = manager.accessible_project_ids("00000000-0000-0000-0000-000000000abc")
    finally:
        db_session.close()

    testbase.assert_equal(
        (own_ids is not None and setup["project_id"] in own_ids, stranger_ids),
        (True, []),
    )
    return
