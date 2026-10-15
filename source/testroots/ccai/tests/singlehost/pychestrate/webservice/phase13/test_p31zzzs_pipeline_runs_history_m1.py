"""
.. module:: test_p31zzzs_pipeline_runs_history_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A pipeline's page shows the runs it has had (ORC-13).

.. moduleauthor:: Code Craft AI LLC

A pipeline run started over REST failed and appeared nowhere in the UI: the pipeline
page showed the definition and nothing else. The page now lists the runs of that
pipeline (newest first; the project's runs of other pipelines are left out), each
with its state, when it started, how it was started and how far it got, its
reason when it did not finish, and, expanded, its stages and steps with a link to
each step's own run. A person without access to runs, a failed request and a
pipeline that has never run each say so. The real page is opened in a browser
against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict, List

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    FAKE_ORIGIN,
    READY_TIMEOUT_MS,
    install_site_routes,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

PROJECT_ID: str = "0f6c2c1e-eeee-4000-8000-000000000001"
PIPELINE_ID: str = "c" * 64
OTHER_PIPELINE: str = "d" * 64

PIPELINE = {
    "pipeline_id": PIPELINE_ID, "project_id": PROJECT_ID, "name": "release", "schema_version": 1,
    "stages": [{"stage_id": "build", "needs": [], "steps": ["compile"]}, {"stage_id": "test", "needs": ["build"], "steps": ["unit"]}],
    "filename": "pipeline.yaml", "commit_sha": "abcdef1234", "cached_at": "2026-09-29T10:00:00+00:00",
}


def _run(run_id: str, pipeline: str, state: str, started: str, *, reason: Any = None, cause: str = "manual") -> Dict[str, Any]:
    failed = state == "failed"
    return {
        "run_id": run_id, "project_id": PROJECT_ID, "pipeline_id": pipeline, "commit_sha": "abcdef1234", "ref": "main", "filename": "pipeline.yaml",
        "state": state, "trigger_cause": cause, "actor_id": "user-1", "final_state_reason": reason, "started_at": started, "finished_at": None,
        "stages": [
            {
                "stage_run_id": run_id + "-s1", "stage_id": "build", "stage_index": 0, "state": "completed", "when_clause": "", "needs": [],
                "final_state_reason": None, "started_at": started, "finished_at": started,
                "steps": [{"step_run_id": run_id + "-p1", "step_id": "compile", "step_index": 0, "kind_name": "build", "job_kind": "build", "layer5_run_id": "aaaaaaaa-0000-4000-8000-00000000000" + run_id[-1], "state": "completed", "final_state_reason": None}],
            },
            {
                "stage_run_id": run_id + "-s2", "stage_id": "test", "stage_index": 1, "state": "failed" if failed else "pending", "when_clause": "", "needs": ["build"],
                "final_state_reason": "no pod could take the job" if failed else None, "started_at": started, "finished_at": None,
                "steps": [{"step_run_id": run_id + "-p2", "step_id": "unit", "step_index": 0, "kind_name": "test", "job_kind": "test", "layer5_run_id": None, "state": "failed" if failed else "pending", "final_state_reason": None}],
            },
        ],
    }


RUNS = {"items": [
    _run("run-1", PIPELINE_ID, "completed", "2026-09-29T10:00:00+00:00"),
    _run("run-2", PIPELINE_ID, "failed", "2026-09-29T12:00:00+00:00", reason="Stage 'test' failed: no pod could take the job", cause="api"),
    _run("run-3", OTHER_PIPELINE, "failed", "2026-09-29T13:00:00+00:00"),
], "meta": {"page": 1, "per_page": 100, "total": 3}}


def _open(browser: Browser, *, runs: Any = RUNS, runs_status: int = 200) -> Any:
    context = browser.new_context(**DESKTOP)
    install_site_routes(
        context, bundle_names=["pyc-site-shell", "pyc-pipelines-bundle"],
        api_stubs={"/api/v1/projects/{}/pipelines/{}".format(PROJECT_ID, PIPELINE_ID): PIPELINE, "/api/v1/projects/{}/pipeline-runs".format(PROJECT_ID): runs},
    )
    if runs_status != 200:
        context.route(
            re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/projects/" + PROJECT_ID + r"/pipeline-runs(\?.*)?$"),
            lambda route: route.fulfill(status=runs_status, headers={"Content-Type": "application/json"}, body=b"{}"),
        )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    page.goto(FAKE_ORIGIN + "/pipelines/{}?project_id={}".format(PIPELINE_ID, PROJECT_ID))
    page.wait_for_selector('[data-role="runs-section"]')
    page.wait_for_timeout(1200)
    return page


def test_the_page_lists_this_pipelines_runs_newest_first_with_their_state_and_reason(browser: Browser):
    """
    **Feature: pipeline run history (ORC-13)**
    **Property: the runs section says "Runs (2)"; the two runs of this pipeline are
    listed newest first ("Failed" then "Completed") and the other pipeline's run is
    not; a run shows how it was started and how far it got ("Api · 1 of 2 stages
    completed"), and the failed one shows its reason.**
    """
    page = _open(browser)
    try:
        heading = page.locator('[data-role="runs-section"] h2').inner_text()
        rows = page.locator('[data-role="run-row"]')
        states = [rows.nth(index).get_attribute("data-state") for index in range(rows.count())]
        first_summary = rows.nth(0).locator("summary").inner_text().replace("\n", " ")
        reason = rows.nth(0).locator('[data-role="run-reason"]').inner_text()
    finally:
        page.context.close()

    testbase.assert_equal(
        (heading, states, "Failed" in first_summary, "Api · 1 of 2 stages completed" in first_summary, reason),
        ("Runs (2)", ["failed", "completed"], True, True, "Stage 'test' failed: no pod could take the job"),
    )
    return


def test_a_run_expands_to_its_stages_and_steps_and_links_each_steps_own_run(browser: Browser):
    """
    **Feature: pipeline run history (ORC-13)**
    **Property: expanding a run lists its stages in order with their states and the
    steps under them; a step that started a run links to it; one that did not has no
    link.**
    """
    page = _open(browser)
    try:
        row = page.locator('[data-role="run-row"]').nth(0)
        row.locator("summary").click()
        page.wait_for_timeout(300)
        stages = row.locator(".pyc-pipeline-detail__run-stage-head").all_inner_texts()
        steps = [text.replace("\n", " ") for text in row.locator('[data-role="run-step"]').all_inner_texts()]
        links = row.locator('[data-role="run-step-link"]').evaluate_all("(els) => els.map((el) => el.getAttribute('href'))")
    finally:
        page.context.close()

    testbase.assert_equal(
        ([text.replace("\n", " ") for text in stages], steps, links),
        (
            ["Completed build", "Failed test"],
            ["Completed compile (build) Open the run", "Failed unit (test)"],
            ["/runs/aaaaaaaa-0000-4000-8000-000000000002"],
        ),
    )
    return


def test_a_failed_run_with_only_the_services_token_names_the_stage_and_step_that_failed(browser: Browser):
    """
    **Feature: pipeline run history (ORC-13)**
    **Property: the service records only "stage_failure" on a failed run (seen on a real pod); the run's line then
    names the stage and step that failed and the first line of the step's own reason, cut at 200 characters
    ("Stage “test”, step “check” failed: dispatch failed: No candidate pod satisfies ..."); a failed stage with no failed
    step says which stage; a run with no stage to name shows the token as words ("Stage failure"); a reason that is already a sentence is shown as it is.**
    """
    reason = "dispatch failed: No candidate pod satisfies the catalog entry's required capabilities.\nENTRY_ID: f97a5bbf\nREQUIRED: ['lab-browser']"

    def _failed_run(run_id: str, *, step_reason: Any, stage_reason: Any, with_step: bool, token: str, started: str) -> Dict[str, Any]:
        run = _run(run_id, PIPELINE_ID, "failed", started, reason=token)
        stage = run["stages"][1]
        stage["stage_id"], stage["final_state_reason"] = "test", stage_reason
        stage["steps"][0].update({"step_id": "check", "state": "failed" if with_step else "pending", "final_state_reason": step_reason})
        return run

    long_reason = "x" * 300
    runs = {"items": [
        _failed_run("run-1", step_reason=reason, stage_reason=None, with_step=True, token="stage_failure", started="2026-09-29T14:00:00+00:00"),
        _failed_run("run-2", step_reason=None, stage_reason=None, with_step=False, token="stage_failure", started="2026-09-29T13:00:00+00:00"),
        _failed_run("run-3", step_reason=long_reason, stage_reason=None, with_step=True, token="stage_failure", started="2026-09-29T12:00:00+00:00"),
        _failed_run("run-4", step_reason="ignored", stage_reason=None, with_step=True, token="Stage 'test' failed: no pod", started="2026-09-29T11:00:00+00:00"),
    ], "meta": {"page": 1, "per_page": 100, "total": 4}}
    runs["items"][1]["stages"][1]["state"] = "pending"
    runs["items"][1]["stages"][0]["state"] = "completed"
    page = _open(browser, runs=runs)
    try:
        lines = [page.locator('[data-role="run-row"]').nth(index).locator('[data-role="run-reason"]').inner_text() for index in range(4)]
    finally:
        page.context.close()

    testbase.assert_equal(
        lines,
        [
            "Stage \u201Ctest\u201D, step \u201Ccheck\u201D failed: dispatch failed: No candidate pod satisfies the catalog entry's required capabilities.",
            "Stage failure",
            "Stage \u201Ctest\u201D, step \u201Ccheck\u201D failed: " + "x" * 199 + "\u2026",
            "Stage 'test' failed: no pod",
        ],
    )
    return


def test_the_runs_refresh_while_one_is_going_keep_an_opened_run_open_and_stop_when_all_are_final(browser: Browser):
    """
    **Feature: pipeline run history (ORC-13)**
    **Property: right after Run the page listed the new run as "Running" and never changed; while a run is going the
    list is now fetched again every 5 seconds, the run turns "Completed" without a reload, a run the person opened is
    still open after the refresh, and once every run is final the page stops asking.**
    """
    calls = []

    def answer(query: Any) -> Dict[str, Any]:
        calls.append(1)
        state = "running" if len(calls) < 2 else "completed"
        return {"items": [_run("run-1", PIPELINE_ID, state, "2026-09-29T10:00:00+00:00")], "meta": {"page": 1, "per_page": 100, "total": 1}}

    page = _open(browser, runs=answer)
    try:
        first_state = page.locator('[data-role="run-row"]').first.get_attribute("data-state")
        page.locator('[data-role="run-row"] summary').first.click()
        page.wait_for_timeout(6500)
        row = page.locator('[data-role="run-row"]').first
        second_state = row.get_attribute("data-state")
        still_open = row.locator("details").evaluate("(el) => el.open")
        asked_when_final = len(calls)
        page.wait_for_timeout(6000)
        asked_later = len(calls)
    finally:
        page.context.close()

    testbase.assert_equal(
        (first_state, second_state, still_open, asked_when_final, asked_later),
        ("running", "completed", True, 2, 2),
    )
    return


def test_a_pipeline_never_run_a_refusal_and_a_failed_request_each_say_so(browser: Browser):
    """
    **Feature: pipeline run history (ORC-13)**
    **Property: no runs of this pipeline reads "This pipeline has not been run yet.";
    a 403 says the person has no access to pipeline runs (and is not an error
    banner); a 500 says the runs could not be loaded; in every case the pipeline's
    own page is still shown.**
    """
    said: Dict[str, Any] = {}
    for name, options in (
        ("never", dict(runs={"items": [_run("run-3", OTHER_PIPELINE, "failed", "2026-09-29T13:00:00+00:00")], "meta": {"total": 1}})),
        ("refused", dict(runs_status=403)),
        ("broken", dict(runs_status=500)),
    ):
        page = _open(browser, **options)
        try:
            role = {"never": "runs-empty", "refused": "runs-error", "broken": "runs-error"}[name]
            said[name] = (
                page.locator('[data-role="{}"]'.format(role)).inner_text(),
                page.locator('[data-role="pipeline-name"]').inner_text(),
                "pyc-pipeline-detail__status--error" in (page.locator('[data-role="{}"]'.format(role)).get_attribute("class") or ""),
                page.locator('[data-role="runs-section"] h2').inner_text(),
            )
        finally:
            page.context.close()

    testbase.assert_equal(
        said,
        {
            "never": ("This pipeline has not been run yet.", "release", False, "Runs"),
            "refused": ("You don't have access to pipeline runs.", "release", False, "Runs"),
            "broken": ("Couldn't load this pipeline's runs.", "release", True, "Runs"),
        },
    )
    return
