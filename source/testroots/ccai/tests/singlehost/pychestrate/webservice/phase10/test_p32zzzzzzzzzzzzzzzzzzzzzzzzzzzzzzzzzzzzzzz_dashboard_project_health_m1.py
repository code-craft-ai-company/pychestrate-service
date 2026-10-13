"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_dashboard_project_health_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The projects dashboard says which projects are in trouble and lists them first (PRJ-21).

.. moduleauthor:: Code Craft AI LLC

The projects table showed each project's latest run, so a project with three failures this week and a green latest run looked fine, and projects
were in no order that helped. Each listed project now carries how many of its runs need attention (failed, dispatch failed, dispatch lost or
needing a look in the last seven days) and the projects with some come first. The count is one grouped query over the listed projects; it uses the
same states and window as the "Needs attention" card.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import uuid

from types import SimpleNamespace

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ccai import testbase

from ccai.pychestrate.webservice.jobs.run.state.enums import RunState
from ccai.pychestrate.webservice.jobs.run.state.models import Run
from ccai.pychestrate.webservice.projects.bridge import registry_project_uuid_for_ref
from ccai.pychestrate.webservice.projects.models import Project
from ccai.pychestrate.webservice.webinterface.blueprints.projects import dashboard_activity as activity

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    open_db_session,
)


NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


def _project(session: Any, *, legacy_id: Optional[int], name: str) -> str:
    project_id = uuid.uuid4()
    session.add(Project(project_id=project_id, slug="p-{}".format(project_id.hex[:10]), display_name=name, legacy_proj_id=legacy_id))
    session.flush()
    return str(project_id)


def _run(session: Any, project_id: str, state: RunState, *, hours_ago: float) -> None:
    session.add(Run(run_id=uuid.uuid4(), project_id=uuid.UUID(project_id), job_type="testbase", state=state, entered_state_at=NOW - timedelta(hours=hours_ago)))
    session.flush()
    return


def test_each_listed_project_counts_its_own_runs_that_need_attention_this_week():
    """
    **Feature: projects dashboard health (PRJ-21)**
    **Property: a listed project's count is how many of its runs failed, were lost or dispatch-failed in the last 7 days (three here, though its
    latest run is fine); older failures, completed runs and another project's failures do not count; a project with none, one the viewer cannot
    reach and one that is not listed are left out.**
    """
    _engine, session = build_in_memory_session()
    alpha = _project(session, legacy_id=1, name="Alpha")
    beta = _project(session, legacy_id=2, name="Beta")
    quiet = _project(session, legacy_id=3, name="Quiet")
    hidden = _project(session, legacy_id=4, name="Hidden")
    unlisted = _project(session, legacy_id=5, name="Unlisted")
    _run(session, alpha, RunState.FAILED, hours_ago=30)
    _run(session, alpha, RunState.DISPATCH_LOST, hours_ago=20)
    _run(session, alpha, RunState.NEEDS_INVESTIGATION, hours_ago=10)
    _run(session, alpha, RunState.COMPLETED, hours_ago=1)
    _run(session, alpha, RunState.FAILED, hours_ago=24 * 9)
    _run(session, beta, RunState.FAILED, hours_ago=2)
    _run(session, quiet, RunState.COMPLETED, hours_ago=3)
    _run(session, hidden, RunState.FAILED, hours_ago=1)
    _run(session, unlisted, RunState.FAILED, hours_ago=1)

    found = activity.collect_run_activity(db_session=session, accessible_legacy_ids=[1, 2, 3, 5], listed_legacy_ids=[1, 2, 3, 4], now=NOW)

    testbase.assert_equal(
        (found["attention_by_project"], found["last_by_project"][1]["state"]),
        ({1: 3, 2: 1}, "completed"),
    )
    return


def test_an_administrator_and_a_new_installation_get_counts_too_or_none():
    """
    **Feature: projects dashboard health (PRJ-21)**
    **Property: for a viewer who can reach every project (``None``) the counts are still per listed project; with no bridged project the count
    is empty and so is everything else.**
    """
    _engine, session = build_in_memory_session()
    alpha = _project(session, legacy_id=1, name="Alpha")
    _run(session, alpha, RunState.FAILED, hours_ago=2)
    everything = activity.collect_run_activity(db_session=session, accessible_legacy_ids=None, listed_legacy_ids=[1], now=NOW)

    _engine2, empty_session = build_in_memory_session()
    nothing = activity.collect_run_activity(db_session=empty_session, accessible_legacy_ids=[1], listed_legacy_ids=[1], now=NOW)

    testbase.assert_equal((everything["attention_by_project"], nothing["attention_by_project"]), ({1: 1}, {}))
    return


def test_projects_with_runs_that_need_attention_come_first_and_the_rest_keep_their_order():
    """
    **Feature: projects dashboard health (PRJ-21)**
    **Property: ``attention_first`` puts the project with the most runs needing attention first, then the next, and leaves the others in the order
    given (a stable sort); with no counts nothing moves.**
    """
    projects = [SimpleNamespace(id=1, name="a"), SimpleNamespace(id=2, name="b"), SimpleNamespace(id=3, name="c"), SimpleNamespace(id=4, name="d")]

    ordered = [project.name for project in activity.attention_first(projects, {3: 1, 2: 4})]
    unchanged = [project.name for project in activity.attention_first(projects, {})]

    testbase.assert_equal((ordered, unchanged), (["b", "c", "a", "d"], ["a", "b", "c", "d"]))
    return


def test_through_the_real_route_the_project_in_trouble_is_listed_first_with_its_count():
    """
    **Feature: projects dashboard health (PRJ-21)**
    **Property: of two projects whose names sort first, the quiet one by name and the one whose run just failed second, the dashboard lists the
    failed one above the quiet one, with "1 needs attention" in its row and the note that such projects come first; the quiet row has no badge.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    quiet = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="0000-a-quiet")
    in_trouble = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="0000-b-broken")
    session = open_db_session()
    try:
        registry_id = registry_project_uuid_for_ref(db_session=session, project_ref=in_trouble)
        session.add(Run(run_id=uuid.uuid4(), project_id=uuid.UUID(registry_id), job_type="build-makefile", state=RunState.FAILED, entered_state_at=datetime.now(timezone.utc)))
        session.commit()
    finally:
        session.close()

    response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/projects/dashboard", cookies=cookies)
    page = html.unescape(response.text)
    table = page[page.index("Projects ("):]
    bad_at = table.index('href="/projects/{}"'.format(in_trouble))
    quiet_at = table.index('href="/projects/{}"'.format(quiet))
    bad_row = table[bad_at:table.index("</tr>", bad_at)]
    quiet_row = table[quiet_at:table.index("</tr>", quiet_at)]

    testbase.assert_equal(
        (response.status_code, bad_at < quiet_at, "1 needs attention" in bad_row, "needs attention" in quiet_row, 'data-role="projects-order"' in table),
        (200, True, True, False, True),
    )
    return
