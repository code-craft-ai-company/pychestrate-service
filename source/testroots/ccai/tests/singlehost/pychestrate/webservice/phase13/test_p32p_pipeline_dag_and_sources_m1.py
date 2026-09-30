"""
.. module:: test_p32p_pipeline_dag_and_sources_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Pipeline DAG edges have arrowheads; a re-saved pipeline is one row (ORC-37).

.. moduleauthor:: Code Craft AI LLC

The pipeline page drew stage dependencies as bare lines, so a reader could not tell
which stage came first. Each edge now ends in an arrowhead at the stage that needs the
other. The pipelines list showed one row per cached (commit, file), so saving the same
definition again looked like a duplicate; it is now one row that names its other sources,
and saving something already in the list says so. The pages are opened in a browser
against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re

from typing import Any, Dict, List

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    FAKE_ORIGIN,
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"
PIPELINE_ID: str = "a" * 64
ONE_PROJECT = {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}


def _stage(stage_id: str, needs: List[str]) -> Dict[str, Any]:
    return {"stage_id": stage_id, "needs": needs, "when_clause": "succeeded", "steps": []}


def _definition(pipeline_id: str, **extra: Any) -> Dict[str, Any]:
    body = {
        "pipeline_id": pipeline_id, "project_id": PROJECT_ID, "name": "release", "schema_version": 1,
        "commit_sha": "1a2b3c4d5e6f", "filename": "ci.yaml", "cached_at": "2026-09-29T10:00:00+00:00",
        "stages": [_stage("build", []), _stage("test", ["build"]), _stage("deploy", ["test"])],
    }
    body.update(extra)
    return body


def test_every_dag_edge_ends_in_an_arrowhead_drawn_in_the_edge_colour(browser: Browser):
    """
    **Feature: DAG arrowheads (ORC-37)**
    **Property: a three-stage pipeline draws two edges; each names an arrowhead marker that
    exists, points along the line, and is filled with the colour the edge is stroked with.**
    """
    stubs = {
        "/api/v1/projects": ONE_PROJECT,
        "/api/v1/projects/{}/pipelines/{}".format(PROJECT_ID, PIPELINE_ID): _definition(PIPELINE_ID),
    }
    page = open_shell_page(
        browser, path="/pipelines/{}?project_id={}".format(PIPELINE_ID, PROJECT_ID),
        bundle_names=["pyc-site-shell", "pyc-pipelines-bundle"], api_stubs=stubs, **DESKTOP,
    )
    try:
        page.wait_for_selector('[data-role="dag-edge"]', state="attached")
        page.wait_for_timeout(500)
        facts = page.evaluate(
            """() => {
                const edges = [...document.querySelectorAll('[data-role="dag-edge"]')];
                return edges.map((edge) => {
                    const ref = /url\\(#([^)]+)\\)/.exec(edge.getAttribute('marker-end') || '');
                    const marker = ref ? document.getElementById(ref[1]) : null;
                    const arrow = marker ? marker.querySelector('[data-role="dag-arrow"]') : null;
                    return {
                        has_marker: marker !== null, orient: marker ? marker.getAttribute('orient') : null,
                        stroke: getComputedStyle(edge).stroke, fill: arrow ? getComputedStyle(arrow).fill : null,
                        drawn: arrow ? arrow.getBBox().width > 0 : false,
                    };
                });
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (len(facts), [item["has_marker"] for item in facts], [item["orient"] for item in facts], [item["drawn"] for item in facts], [item["stroke"] == item["fill"] and item["fill"] not in (None, "none") for item in facts]),
        (2, [True, True], ["auto", "auto"], [True, True], [True, True]),
    )
    return


def _open_list(browser: Browser, items: List[Dict[str, Any]]) -> Any:
    stubs = {
        "/api/v1/projects": ONE_PROJECT,
        "/api/v1/projects/{}/pipelines".format(PROJECT_ID): {"items": items, "meta": {"page": 1, "per_page": 25, "total": len(items)}},
    }
    page = open_shell_page(
        browser, path="/pipelines?project_id=" + PROJECT_ID, bundle_names=["pyc-site-shell", "pyc-pipelines-bundle"], api_stubs=stubs, **DESKTOP,
    )
    page.wait_for_selector("mj-data-table")
    page.wait_for_timeout(800)
    return page


def test_a_pipeline_saved_from_other_commits_is_one_row_that_names_them(browser: Browser):
    """
    **Feature: one row per definition (ORC-37)**
    **Property: a list entry with two other sources shows its newest source plus "+2 other
    sources" whose hover text names them; an entry with none shows no such note; a single
    other source says "+1 other source".**
    """
    other = [{"filename": "ci.yaml", "commit_sha": "9f8e7d6c5b4a", "cached_at": None}, {"filename": "old.yaml", "commit_sha": "0011223344", "cached_at": None}]
    page = _open_list(browser, [
        _definition(PIPELINE_ID, other_sources=other),
        _definition("b" * 64, name="deploy", filename="deploy.yaml", other_sources=[]),
        _definition("c" * 64, name="lint", filename="lint.yaml", other_sources=other[:1]),
    ])
    try:
        # The table draws its rows in its own shadow root: query through Playwright, not the document.
        note_locators = page.locator('[data-role="other-sources"]')
        notes = [(note_locators.nth(index).text_content().strip(), note_locators.nth(index).get_attribute("title")) for index in range(note_locators.count())]
        sources = [page.get_by_text(text).count() for text in ("ci.yaml @ 1a2b3c4", "deploy.yaml @ 1a2b3c4", "lint.yaml @ 1a2b3c4")]
    finally:
        page.context.close()

    testbase.assert_equal(
        ([note[0] for note in notes], [note[1] for note in notes], [count > 0 for count in sources]),
        (
            ["+2 other sources", "+1 other source"],
            ["Also saved from ci.yaml @ 9f8e7d6, old.yaml @ 0011223", "Also saved from ci.yaml @ 9f8e7d6"],
            [True, True, True],
        ),
    )
    return


def _save(page: Any, *, commit: str, filename: str, answer_id: str) -> str:
    """Submit the define form with the service answering ``answer_id``; return the status line."""
    def _answer(route: Any) -> None:
        if route.request.method == "POST":
            route.fulfill(status=200, headers={"Content-Type": "application/json"}, body=json.dumps(_definition(answer_id)))
        else:
            route.fallback()

    page.context.route(re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/[^/]+/pipelines$"), _answer)
    page.locator('[data-role="upsert-commit-sha"] input').fill(commit)
    page.locator('[data-role="upsert-filename"] input').fill(filename)
    page.locator('[data-role="upsert-document"] textarea').fill("name: release")
    page.locator('[data-role="save-submit"]').click()
    page.wait_for_timeout(800)
    return " ".join(page.locator('[data-role="form-status-message"]').inner_text().split())


def test_saving_what_is_already_in_the_list_says_so(browser: Browser):
    """
    **Feature: one row per definition (ORC-37)**
    **Property: saving a definition the list already holds from the same commit and file says
    nothing changed; from another commit says it is the same pipeline, listed once, with the new
    source; a definition that is new just says it was saved.**
    """
    page = _open_list(browser, [_definition(PIPELINE_ID, other_sources=[])])
    try:
        same = _save(page, commit="1a2b3c4d5e6f", filename="ci.yaml", answer_id=PIPELINE_ID)
        other_commit = _save(page, commit="9999999abcde", filename="ci.yaml", answer_id=PIPELINE_ID)
        new = _save(page, commit="1a2b3c4d5e6f", filename="ci.yaml", answer_id="d" * 64)
    finally:
        page.context.close()

    testbase.assert_equal(
        (same, other_commit, new),
        (
            "Nothing changed: this pipeline was already saved from ci.yaml @ 1a2b3c4.",
            "Saved. This is the same pipeline as release, so it is listed once; ci.yaml @ 9999999 is now its latest source.",
            "Pipeline saved.",
        ),
    )
    return
