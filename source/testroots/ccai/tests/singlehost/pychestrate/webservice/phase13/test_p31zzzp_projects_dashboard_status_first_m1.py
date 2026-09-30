"""
.. module:: test_p31zzzp_projects_dashboard_status_first_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The projects dashboard leads with what needs attention (PRJ-21).

.. moduleauthor:: Code Craft AI LLC

The dashboard's largest element was a count ("3"); it listed builds and tests from
tables nothing fills, named projects "Project #1", and said nothing about what
was broken. It now leads with "Needs attention" (runs that failed this week),
gives each project a "Last run", lists the latest runs, and shows the older build
and test cards only when they hold something. The template is rendered in the strict
environment with the fixture context the route's real values are checked against.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict

from ccai import testbase

from ccai.testshared.factories.webui.template_contexts import (
    MODE_POPULATED,
    build_template_context,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


TEMPLATE = "projects/dashboard.html"

ROW: Dict[str, Any] = {
    "run_id": "11111111-2222-4333-8444-555555555555", "project_legacy_id": 1, "project_name": "Alpha",
    "kind": "Test · testbase", "state": "failed", "state_label": "Failed", "tone": "danger",
    "at": datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc),
}


def _context() -> Dict[str, Any]:
    return build_template_context(template_name=TEMPLATE, variable_names=undeclared_variables(template_name=TEMPLATE), mode=MODE_POPULATED)


def _render(**overrides: Any) -> str:
    context = _context()
    context.update(overrides)
    return strict_environment().get_template(TEMPLATE).render(context)


def test_the_dashboard_leads_with_what_needs_attention_and_not_with_a_count():
    """
    **Feature: projects dashboard (PRJ-21)**
    **Property: "Needs attention" comes before the projects table; a failed run is
    a row linking to the run, naming its kind and project, with a danger badge;
    the big "Your Projects" count card is gone and the count is in the table's
    heading.**
    """
    page = _render(dashboard_attention_runs=[ROW])
    section = page[page.index('data-role="needs-attention"'):]
    section = section[:section.index('Projects (')]

    testbase.assert_equal(
        (
            page.index('data-role="needs-attention"') < page.index("Projects ("),
            'href="/runs/{}"'.format(ROW["run_id"]) in section,
            "Test · testbase" in section,
            "Alpha" in section,
            'class="badge badge-danger">Failed<' in section,
            "Your Projects" in page or "Projects you have access to" in page,
            "Projects (42)" in page,
        ),
        (True, True, True, True, True, False, True),
    )
    return


def test_a_quiet_week_and_a_new_installation_each_say_so():
    """
    **Feature: projects dashboard (PRJ-21)**
    **Property: with runs but none failed the card says nothing needs attention;
    with no runs at all it says so and points at the Test catalog; neither draws an
    attention table; the recent-runs card says there are no runs.**
    """
    quiet = _render(dashboard_attention_runs=[], dashboard_recent_runs=[ROW])
    fresh = _render(dashboard_attention_runs=[], dashboard_recent_runs=[])

    testbase.assert_equal(
        (
            'data-role="nothing-needs-attention"' in quiet, 'data-role="attention-run"' in quiet,
            'data-role="no-runs-yet"' in fresh, 'href="/test-catalog"' in fresh, 'data-role="attention-run"' in fresh,
            "No runs yet. Runs appear here" in fresh, 'data-role="recent-run"' in quiet,
        ),
        (True, False, True, True, False, True, True),
    )
    return


def test_each_listed_project_shows_its_last_run_or_a_dash():
    """
    **Feature: projects dashboard (PRJ-21)**
    **Property: a project with a last run shows its state as a badge linking to the
    run; the others show a dash.**
    """
    context = _context()
    projects = list(context["projects"])
    page = _render(dashboard_last_runs={projects[0].id: ROW})
    with_run = sum(1 for project in projects if project.id == projects[0].id)

    testbase.assert_equal(
        (page.count('data-role="last-run"'), page.count('data-role="no-last-run"'), 'data-role="last-run"><span class="badge badge-danger">Failed</span>' in page),
        (with_run, len(projects) - with_run, True),
    )
    return


def test_the_older_build_and_test_cards_show_only_when_they_hold_something_and_name_the_project():
    """
    **Feature: projects dashboard (PRJ-21)**
    **Property: with no legacy builds or tests neither card is drawn; a legacy build
    names its project ("Zed") and never "Project #7"; an unknown project reads
    "Project 9".**
    """
    empty = _render(recent_builds=[], recent_tests=[])
    build = SimpleNamespace(id=5, project_id=7, spec_name="core", status="succeeded", created_at=datetime(2026, 9, 29, tzinfo=timezone.utc))
    unknown = SimpleNamespace(id=6, project_id=9, spec_name="core", status="succeeded", created_at=datetime(2026, 9, 29, tzinfo=timezone.utc))
    shown = _render(recent_builds=[build, unknown], recent_tests=[], dashboard_project_names={7: "Zed"})

    testbase.assert_equal(
        ("Recent Builds" in empty, "Recent Tests" in empty, "Zed" in shown, "Project #" in shown, "Project 9" in shown, "Recent Tests" in shown),
        (False, False, True, False, True, False),
    )
    return
