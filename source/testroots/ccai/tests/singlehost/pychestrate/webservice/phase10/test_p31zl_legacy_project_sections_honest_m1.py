"""
.. module:: test_p31zl_legacy_project_sections_honest_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The project sections nothing can fill say so (PRJ-08).

.. moduleauthor:: Code Craft AI LLC

Test specifications, infrastructure specifications, release pipelines and
the release calendar's events are read from the web-UI project model, and
no page or API creates them. Their empty states said "managed via the API",
"configured via the API" and "triggered by watches, pipelines, or the API",
which sent people looking for something that does not exist. They now carry
the same "Preview" notice the release channels and schedules already had
(ORG-F14), the sub-navigation labels them "(preview)", and Tests and
Pipelines point to the places where those things do work (the Test catalog,
Runs, Pipelines). The Releases list is not permanently empty (a release is
created from a release template), so its empty state points there.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from typing import Any, Dict, List

from ccai import testbase

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


#: The pages nothing can fill.
NOTICE_TEMPLATES: List[str] = [
    "projects/tests/list.html",
    "projects/tests/spec_list.html",
    "projects/infrastructure/list.html",
    "projects/infrastructure/spec_list.html",
    "projects/releases/pipeline_list.html",
    "projects/calendar/event_list.html",
    "projects/calendar/view.html",
]

#: What they said before.
FALSE_PHRASES: List[str] = [
    "managed via the API",
    "managed via API",
    "configured via the API",
    "triggered by watches, pipelines, or the API",
    "created by pipelines or via the API",
]


def _render_empty(template_name: str) -> str:
    context = build_template_context(
        template_name=template_name,
        variable_names=undeclared_variables(template_name=template_name),
        mode=MODE_SPARSE,
    )
    return html.unescape(strict_environment().get_template(template_name).render(context))


def test_every_section_nothing_can_fill_carries_the_preview_notice_and_no_false_pointer():
    """
    **Feature: honest project sections (PRJ-08)**
    **Property: each of the seven pages renders the preview notice and none
    of the phrases that pointed to an API that does not exist.**
    """
    results = {}
    for template_name in NOTICE_TEMPLATES:
        rendered = _render_empty(template_name)
        results[template_name] = (
            'data-role="preview-notice"' in rendered,
            [phrase for phrase in FALSE_PHRASES if phrase in rendered],
        )

    testbase.assert_equal(results, {name: (True, []) for name in NOTICE_TEMPLATES})
    return


def test_the_releases_list_points_to_release_templates_not_to_pipelines():
    """
    **Feature: honest project sections (PRJ-08)**
    **Property: the empty Releases list says a release is created from a
    release template and links to the templates, and no longer says
    pipelines create releases.**
    """
    rendered = _render_empty("projects/releases/list.html")

    testbase.assert_equal(
        ("created from a release template" in rendered, "release-templates" in rendered or "release_templates" in rendered,
         "created by pipelines" in rendered),
        (True, True, False),
    )
    return


def test_the_project_sub_navigation_labels_the_four_dead_ends_as_preview():
    """
    **Feature: honest project sections (PRJ-08)**
    **Property: the sub-navigation labels Infrastructure, Tests, Pipelines
    and Calendar "(preview)", as it already did Channels and Schedules, and
    leaves the working sections (Builds, Releases, Release Templates, RPA,
    Watches) unlabelled.**
    """
    rendered = _render_empty("projects/releases/pipeline_list.html")
    labelled = sorted(set(re.findall(r"\s(\w+) \(preview\)", rendered)))
    plain = [label for label in ("Builds", "Releases", "Release Templates", "Watches") if "{} (preview)".format(label) in rendered]

    testbase.assert_equal((labelled, plain), (["Calendar", "Channels", "Infrastructure", "Pipelines", "Schedules", "Tests"], []))
    return


# ---------------------------------------------------------------------------
# The pages, live
# ---------------------------------------------------------------------------


def _get(setup: Dict[str, Any], path: str) -> str:
    response = drive_request(wsgi_app=setup["wsgi_app"], method="GET", path=path, cookies=setup["cookies"])
    setup["cookies"].update(response.collect_set_cookies())
    return html.unescape(response.text)


def test_the_tests_and_pipelines_pages_link_to_this_projects_catalog_runs_and_pipelines():
    """
    **Feature: honest project sections (PRJ-08)**
    **Property: on a real project the Tests, test specification and
    Pipelines pages link to the Test catalog, Runs and Pipelines filtered
    to that project's registry id, so the person lands on the working
    version of the same thing.**
    """
    handle = ensure_app()
    setup = {"wsgi_app": handle.wsgi_app, "cookies": logged_in_cookies(wsgi_app=handle.wsgi_app)}
    project_id = create_project_via_ui(wsgi_app=setup["wsgi_app"], cookies=setup["cookies"], prefix="prj08" + uuid.uuid4().hex[:4])
    db_session = open_db_session()
    try:
        registry_id = str(get_project_by_legacy_id(db_session=db_session, legacy_proj_id=project_id).project_id)
    finally:
        db_session.close()

    jobs = _get(setup, "/projects/{}/tests".format(project_id))
    specs = _get(setup, "/projects/{}/tests/specs".format(project_id))
    pipelines = _get(setup, "/projects/{}/releases/pipelines".format(project_id))
    query = "?project_id=" + registry_id

    testbase.assert_equal(
        (
            'href="/test-catalog{}"'.format(query) in jobs and 'href="/runs{}"'.format(query) in jobs,
            'href="/test-catalog{}"'.format(query) in specs,
            'href="/pipelines{}"'.format(query) in pipelines,
            [phrase for page in (jobs, specs, pipelines) for phrase in FALSE_PHRASES if phrase in page],
        ),
        (True, True, True, []),
    )
    return
