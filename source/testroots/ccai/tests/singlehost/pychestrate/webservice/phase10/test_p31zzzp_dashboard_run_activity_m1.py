"""
.. module:: test_p31zzzp_dashboard_run_activity_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The projects dashboard reads real runs through the bridged projects (PRJ-21).

.. moduleauthor:: Code Craft AI LLC

The runs a viewer should see first are read from the runs table by the registry id
of each web-UI project (the bridge). These tests cover the query (the last week,
the states that mean something broke, order and limits, the last run per project,
a project with no counterpart) over an in-memory database, and one request through
the real route to prove the dashboard passes the data to its template.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import uuid

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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


def _run(session: Any, project_id: str, state: RunState, *, hours_ago: float, job_type: str = "testbase") -> str:
    run_id = uuid.uuid4()
    session.add(Run(run_id=run_id, project_id=uuid.UUID(project_id), job_type=job_type, state=state, entered_state_at=NOW - timedelta(hours=hours_ago)))
    session.flush()
    return str(run_id)


def test_only_runs_that_broke_in_the_last_week_need_attention_newest_first():
    """
    **Feature: projects dashboard (PRJ-21)**
    **Property: failed, dispatch-failed, dispatch-lost and needs-investigation runs
    from the last 7 days are listed newest first (at most five); completed and
    running runs and older failures are not.**
    """
    _engine, session = build_in_memory_session()
    alpha = _project(session, legacy_id=1, name="Alpha")
    old = _run(session, alpha, RunState.FAILED, hours_ago=24 * 8)
    failed = _run(session, alpha, RunState.FAILED, hours_ago=5)
    lost = _run(session, alpha, RunState.DISPATCH_LOST, hours_ago=2)
    _run(session, alpha, RunState.COMPLETED, hours_ago=1)
    _run(session, alpha, RunState.RUNNING, hours_ago=0.5)
    found = activity.collect_run_activity(db_session=session, accessible_legacy_ids=[1], listed_legacy_ids=[1], now=NOW)

    testbase.assert_equal(
        ([row["run_id"] for row in found["attention"]], old in [row["run_id"] for row in found["attention"]], found["attention"][0]["state_label"], found["attention"][0]["tone"]),
        ([lost, failed], False, "Dispatch lost", "danger"),
    )
    return


def test_the_lists_are_bounded_and_the_last_run_is_per_project_and_only_for_reachable_bridged_projects():
    """
    **Feature: projects dashboard (PRJ-21)**
    **Property: ten failures give five attention rows and ten runs give eight
    recent rows; each listed project's last run is its own newest run; a project the
    viewer cannot reach, and a web-UI project with no registry counterpart, add
    nothing; a project with no runs has no last run.**
    """
    _engine, session = build_in_memory_session()
    alpha = _project(session, legacy_id=1, name="Alpha")
    beta = _project(session, legacy_id=2, name="Beta")
    hidden = _project(session, legacy_id=3, name="Hidden")
    quiet = _project(session, legacy_id=4, name="Quiet")
    for index in range(10):
        _run(session, alpha, RunState.FAILED, hours_ago=index + 1)
    beta_last = _run(session, beta, RunState.COMPLETED, hours_ago=0.1, job_type="build-makefile")
    _run(session, hidden, RunState.FAILED, hours_ago=0.2)
    found = activity.collect_run_activity(db_session=session, accessible_legacy_ids=[1, 2, 4, 99], listed_legacy_ids=[1, 2, 4, 99], now=NOW)

    testbase.assert_equal(
        (
            len(found["attention"]), len(found["recent"]), found["recent"][0]["run_id"], found["recent"][0]["kind"], found["recent"][0]["project_name"],
            sorted(found["last_by_project"].keys()), found["last_by_project"][2]["run_id"], 4 in found["last_by_project"],
            any(row["project_name"] == "Hidden" for row in found["attention"] + found["recent"]),
        ),
        (5, 8, beta_last, "Build · makefile", "Beta", [1, 2], beta_last, False, False),
    )
    return


def test_no_bridged_project_means_no_activity_and_the_labels_read_as_words():
    """
    **Feature: projects dashboard (PRJ-21)**
    **Property: with no registry counterpart there is nothing to show (and no
    query error); job types read "Build · makefile" / "Test · testbase" / "RPA";
    states read "Dispatch failed" with the tone the badge uses.**
    """
    _engine, session = build_in_memory_session()
    nothing = activity.collect_run_activity(db_session=session, accessible_legacy_ids=[5], listed_legacy_ids=[5], now=NOW)

    testbase.assert_equal(
        (
            nothing, activity.run_kind_label("build-makefile"), activity.run_kind_label("testbase"), activity.run_kind_label("rpa-onboard"), activity.run_kind_label(""),
            activity.state_label("dispatch_failed"), activity.state_tone("dispatch_failed"), activity.state_tone("completed"), activity.state_tone("running"), activity.state_tone("progress_stalled"),
        ),
        (
            {"attention": [], "recent": [], "last_by_project": {}}, "Build · makefile", "Test · testbase", "RPA · onboard", "Run",
            "Dispatch failed", "danger", "success", "info", "warning",
        ),
    )
    return


def test_the_route_puts_a_recent_failure_on_the_dashboard():
    """
    **Feature: projects dashboard (PRJ-21)**
    **Property: through the real route, a run that just failed in a project the admin
    can reach appears under "Needs attention" as a link to the run, naming the
    project, before the projects table, and the old count card is not drawn.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    legacy_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="dash-attn")
    session = open_db_session()
    try:
        registry_id = registry_project_uuid_for_ref(db_session=session, project_ref=legacy_id)
        run_id = uuid.uuid4()
        session.add(Run(run_id=run_id, project_id=uuid.UUID(registry_id), job_type="build-makefile", state=RunState.FAILED, entered_state_at=datetime.now(timezone.utc)))
        session.commit()
    finally:
        session.close()
    response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/projects/dashboard", cookies=cookies)
    page = html.unescape(response.text)
    section = page[page.index('data-role="needs-attention"'):]
    section = section[:section.index("Projects (")]

    testbase.assert_equal(
        (response.status_code, 'href="/runs/{}"'.format(run_id) in section, "Build · makefile" in section, "Failed" in section, "Your Projects" in page),
        (200, True, True, True, False),
    )
    return


def test_a_viewer_who_can_reach_every_project_sees_the_runs_of_all_bridged_ones():
    """
    **Feature: projects dashboard (PRJ-21)**
    **Property: ``None`` (an administrator, who can reach every project) scopes the
    runs to every bridged project without loading the projects: a failure in one
    is listed with its project's name, one in a project with no web-UI counterpart
    is not, and a listed project still gets its last run.**
    """
    _engine, session = build_in_memory_session()
    alpha = _project(session, legacy_id=1, name="Alpha")
    unbridged = _project(session, legacy_id=None, name="Unbridged")
    failed = _run(session, alpha, RunState.FAILED, hours_ago=3)
    _run(session, unbridged, RunState.FAILED, hours_ago=1)
    found = activity.collect_run_activity(db_session=session, accessible_legacy_ids=None, listed_legacy_ids=[1], now=NOW)

    testbase.assert_equal(
        ([(row["run_id"], row["project_name"]) for row in found["attention"]], [row["project_name"] for row in found["recent"]], found["last_by_project"][1]["run_id"]),
        ([(failed, "Alpha")], ["Alpha"], failed),
    )
    return
