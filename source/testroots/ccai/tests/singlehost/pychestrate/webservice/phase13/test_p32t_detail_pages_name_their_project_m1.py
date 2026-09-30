"""
.. module:: test_p32t_detail_pages_name_their_project_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Build, provisioning-run and pipeline pages name their project and environment (ORC-18).

.. moduleauthor:: Code Craft AI LLC
.. Copyright 2026, Code Craft AI LLC

The build, provisioning-run and pipeline pages showed "Project  0f6c2c1e-..." (and the
provisioning page an environment id) as a field's value: identity nobody chose and nobody can
read. They now show the project's name as a link to its page, the environment's name, and keep
the id in the hover text; when a name cannot be read they show a short id. The pages are opened in
a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-5555-4000-8000-000000000001"
ENVIRONMENT_ID: str = "0f6c2c1e-5555-4000-8000-000000000002"
BUILD_ID: str = "0f6c2c1e-5555-4000-8000-000000000003"
RUN_ID: str = "0f6c2c1e-5555-4000-8000-000000000004"
PIPELINE_ID: str = "c" * 64

PROJECTS = {"items": [{"project_id": PROJECT_ID, "display_name": "Lab Automation", "slug": "lab"}], "meta": {"total": 1}}
ENVIRONMENTS = {"items": [{"environment_id": ENVIRONMENT_ID, "name": "staging cluster", "kind": "k8s_cluster"}], "meta": {"total": 1}}

#: page, bundle, stubs that answer the page's own record, the selector that says it has rendered
PAGES: List[Tuple[str, str, str, Dict[str, Any], str]] = [
    (
        "build", "/builds/{}?project_id={}".format(BUILD_ID, PROJECT_ID), "pyc-builds-bundle",
        {
            "/api/v1/projects/{}/builds/{}".format(PROJECT_ID, BUILD_ID): {
                "run_id": BUILD_ID, "project_id": PROJECT_ID, "runner_kind": "makefile", "repro_digest_sha256": "ab" * 8,
                "state": "completed", "started_at": "2026-09-29T10:00:00+00:00", "finished_at": "2026-09-29T10:01:00+00:00",
            },
            "/api/v1/projects/{}/builds/{}/artifacts".format(PROJECT_ID, BUILD_ID): {"items": [], "meta": {"total": 0}},
        },
        ".pyc-build-detail__grid",
    ),
    (
        "provisioning run", "/provisioning-runs/{}?project_id={}".format(RUN_ID, PROJECT_ID), "pyc-infra-bundle",
        {
            "/api/v1/projects/{}/provisioning-runs/{}".format(PROJECT_ID, RUN_ID): {
                "run_id": RUN_ID, "project_id": PROJECT_ID, "environment_id": ENVIRONMENT_ID, "action": "apply", "state": "succeeded",
                "driver": "terraform", "created_at": "2026-09-01T10:00:00+00:00", "started_at": "2026-09-01T10:00:05+00:00",
                "finished_at": "2026-09-01T10:01:00+00:00", "plan_issued_at": "2026-09-01T10:00:02+00:00", "final_state_reason": "",
                "steps": [], "plan_summary": None,
            },
        },
        ".pyc-provisioning-detail__grid",
    ),
    (
        "pipeline", "/pipelines/{}?project_id={}".format(PIPELINE_ID, PROJECT_ID), "pyc-pipelines-bundle",
        {
            "/api/v1/projects/{}/pipelines/{}".format(PROJECT_ID, PIPELINE_ID): {
                "pipeline_id": PIPELINE_ID, "project_id": PROJECT_ID, "name": "release", "schema_version": 1, "commit_sha": "1a2b3c4d5e6f",
                "filename": "ci.yaml", "cached_at": "2026-09-29T10:00:00+00:00", "stages": [],
            },
        },
        ".pyc-pipeline-detail__grid",
    ),
]


def _fields(page: Any, grid_selector: str) -> Dict[str, Tuple[str, Optional[str], Optional[str]]]:
    """label -> (value text, the link it points to, its hover text)"""
    found = page.evaluate(
        """(selector) => {
            const found = {};
            for (const field of document.querySelectorAll(selector + ' > div')) {
                const label = field.querySelector('dt').textContent.trim();
                const value = field.querySelector('dd');
                const link = value.querySelector('a');
                found[label] = [value.textContent.trim(), link ? link.getAttribute('href') : null, (link || value).getAttribute('title')];
            }
            return found;
        }""",
        grid_selector,
    )
    return {label: tuple(values) for label, values in found.items()}


def _open(browser: Browser, path: str, bundle: str, stubs: Dict[str, Any], *, names: bool) -> Any:
    answers = dict(stubs)
    answers["/api/v1/projects"] = PROJECTS if names is True else {"items": [], "meta": {"total": 0}}
    answers["/api/v1/projects/{}/environments".format(PROJECT_ID)] = ENVIRONMENTS if names is True else {"items": [], "meta": {"total": 0}}
    page = open_shell_page(browser, path=path, bundle_names=["pyc-site-shell", bundle], api_stubs=answers, **DESKTOP)
    return page


def test_each_page_shows_the_project_by_name_as_a_link_with_the_id_on_hover(browser: Browser):
    """
    **Feature: names, not ids (ORC-18)**
    **Property: on the build, provisioning-run and pipeline pages the Project field reads
    "Lab Automation", links to /projects/<id>, and has the id as its hover text.**
    """
    outcomes: Dict[str, Any] = {}
    for label, path, bundle, stubs, grid in PAGES:
        page = _open(browser, path, bundle, stubs, names=True)
        try:
            page.wait_for_selector(grid)
            page.wait_for_timeout(1200)
            outcomes[label] = _fields(page, grid)["Project"]
        finally:
            page.context.close()

    expected = ("Lab Automation", "/projects/" + PROJECT_ID, PROJECT_ID)
    testbase.assert_equal(outcomes, {label: expected for label, *_rest in PAGES})
    return


def test_the_provisioning_page_shows_the_environment_by_name(browser: Browser):
    """
    **Feature: names, not ids (ORC-18)**
    **Property: the Environment field reads "staging cluster" with the id on hover, not the id.**
    """
    _label, path, bundle, stubs, grid = PAGES[1]
    page = _open(browser, path, bundle, stubs, names=True)
    try:
        page.wait_for_selector(grid)
        page.wait_for_timeout(1200)
        environment = _fields(page, grid)["Environment"]
    finally:
        page.context.close()

    testbase.assert_equal(environment, ("staging cluster", None, ENVIRONMENT_ID))
    return


def test_when_a_name_cannot_be_read_a_short_id_is_shown_and_the_page_still_works(browser: Browser):
    """
    **Feature: names, not ids (ORC-18)**
    **Property: with no project or environment names available, the fields show the id's first
    segment (never blank, never the whole UUID) and the rest of the page still renders.**
    """
    outcomes: Dict[str, Any] = {}
    for label, path, bundle, stubs, grid in PAGES:
        page = _open(browser, path, bundle, stubs, names=False)
        try:
            page.wait_for_selector(grid)
            page.wait_for_timeout(1200)
            fields = _fields(page, grid)
            outcomes[label] = (fields["Project"][0], fields.get("Environment", ("",))[0])
        finally:
            page.context.close()

    testbase.assert_equal(
        outcomes,
        {"build": ("0f6c2c1e", ""), "provisioning run": ("0f6c2c1e", "0f6c2c1e"), "pipeline": ("0f6c2c1e", "")},
    )
    return
