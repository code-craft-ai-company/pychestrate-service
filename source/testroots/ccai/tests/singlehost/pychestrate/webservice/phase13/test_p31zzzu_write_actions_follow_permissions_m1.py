"""
.. module:: test_p31zzzu_write_actions_follow_permissions_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bundle views leave out the actions the viewer cannot use (ORC-33).

.. moduleauthor:: Code Craft AI LLC

The bundle views showed every write action to every viewer, and the missing
permission surfaced only after the form was submitted. The primary create,
register, trigger and delete controls now use ``hide_unless_may`` with the
``system:`` key the API itself enforces (the shell's permission list is computed
from those keys and the viewer's own grants, so it matches the server's check).
Each control is shown when the viewer holds the key, left out when they do not,
and shown when the permissions cannot be read (the server still decides).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict, List, Optional, Tuple

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

PROJECT: str = "0f6c2c1e-1111-4000-8000-000000000001"
PIPELINE: str = "e" * 64
SLO: str = "0f6c2c1e-1111-4000-8000-0000000000a1"

PROJECTS = {"items": [{"project_id": PROJECT, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}
EXTRA: Dict[str, Any] = {
    "slo": {"/api/v1/projects/{}/slos".format(PROJECT): {"items": [{"slo_id": SLO, "project_id": PROJECT, "name": "API", "kind": "availability_ratio", "target": 0.999, "window_seconds": 86400, "definition_config": {}}], "meta": {"total": 1}}},
    "pipeline": {"/api/v1/projects/{}/pipelines/{}".format(PROJECT, PIPELINE): {
        "pipeline_id": PIPELINE, "project_id": PROJECT, "name": "release", "schema_version": 1, "stages": [], "filename": "p.yaml", "commit_sha": "abc", "cached_at": "2026-09-29T10:00:00+00:00",
    }},
}

# (label, path, bundle, extras, tab to open first, selector, the key the API enforces)
CASES: List[Tuple[str, str, str, str, Optional[str], str, str]] = [
    ("start a build", "/builds?project_id=" + PROJECT, "pyc-builds-bundle", "", None, '[data-role="trigger-toggle"]', "system:builds.create"),
    ("attach a guard", "/blast-radius-guards", "pyc-infra-bundle", "", None, '[data-role="attach-toggle"]', "system:guards.write"),
    ("create an alert rule", "/metric-alerts?project_id=" + PROJECT, "pyc-metrics-bundle", "", None, '[data-role="create-toggle"]', "system:metric_alerts.write"),
    ("import tests", "/test-catalog?project_id=" + PROJECT, "pyc-catalog-bundle", "", None, '[data-role="import-toggle"]', "system:test_catalog.write"),
    ("register an environment", "/environments?project_id=" + PROJECT, "pyc-infra-bundle", "", None, '[data-role="register-toggle"]', "system:environments.write"),
    ("publish a release", "/release-channels?project_id=" + PROJECT, "pyc-ops-bundle", "", None, '[data-role="publish-toggle"]', "system:release_channels.write"),
    ("create an inbound webhook", "/webhooks", "pyc-ops-bundle", "", None, '[data-role="inbound-create-toggle"]', "system:webhooks.write"),
    ("create an outbound webhook", "/webhooks", "pyc-ops-bundle", "", "outbound", '[data-role="outbound-create-toggle"]', "system:webhooks.write"),
    ("create an SLO", "/slos?project_id=" + PROJECT, "pyc-metrics-bundle", "", None, '[data-role="create-toggle"]', "system:slos.write"),
    ("delete an SLO", "/slos?project_id=" + PROJECT, "pyc-metrics-bundle", "slo", None, '[data-role="delete-slo"]', "system:slos.write"),
    ("trigger provisioning", "/provisioning-runs?project_id=" + PROJECT, "pyc-infra-bundle", "", None, '[data-role="trigger-toggle"]', "system:provisioning.create"),
    ("delete a pipeline", "/pipelines/{}?project_id={}".format(PIPELINE, PROJECT), "pyc-pipelines-bundle", "pipeline", None, '[data-role="delete-pipeline"]', "system:pipelines.write"),
]


def _visible(browser: Browser, case: Tuple[str, str, str, str, Optional[str], str, str], permissions: Optional[List[str]]) -> bool:
    """Whether the control is on the page when the viewer holds exactly ``permissions`` (None: the list cannot be read)."""
    _label, path, bundle, extra, tab, selector, _key = case
    stubs: Dict[str, Any] = {"/api/v1/projects": PROJECTS, "/api/v1/me/permissions": {"permissions": permissions or []}}
    stubs.update(EXTRA.get(extra, {}))
    context = browser.new_context(**DESKTOP)
    install_site_routes(context, bundle_names=["pyc-site-shell", bundle], api_stubs=stubs)
    if permissions is None:
        context.route(
            re.compile(re.escape(FAKE_ORIGIN) + r"/api/v1/me/permissions(\?.*)?$"),
            lambda route: route.fulfill(status=500, headers={"Content-Type": "application/json"}, body=b"{}"),
        )
    page = context.new_page()
    page.set_default_timeout(READY_TIMEOUT_MS)
    try:
        page.goto(FAKE_ORIGIN + path)
        if tab is not None:
            page.wait_for_selector('[data-role="tab-{}"]'.format(tab))
            page.wait_for_timeout(500)
            page.locator('[data-role="tab-{}"]'.format(tab)).click()
        page.wait_for_selector(selector, state="attached")
        page.wait_for_timeout(1000)
        return page.locator(selector).first.is_visible()
    finally:
        context.close()


def test_each_write_control_is_shown_to_a_holder_and_left_out_for_everyone_else(browser: Browser):
    """
    **Feature: hide what cannot be used (ORC-33)**
    **Property: for each gated control (twelve of them), with the API's own key it is
    on the page; holding only a read permission it is left out.**
    """
    results: Dict[str, Tuple[bool, bool]] = {}
    for case in CASES:
        results[case[0]] = (_visible(browser, case, [case[6]]), _visible(browser, case, ["system:runs.read"]))

    testbase.assert_equal(results, {case[0]: (True, False) for case in CASES})
    return


def test_an_unreadable_permission_list_hides_nothing(browser: Browser):
    """
    **Feature: hide what cannot be used (ORC-33)**
    **Property: when the permission list cannot be read (500), every gated control is
    still on the page, because the server decides and a wrongly hidden action is
    worse than one that is refused with a reason.**
    """
    results: Dict[str, bool] = {case[0]: _visible(browser, case, None) for case in CASES}

    testbase.assert_equal(results, {case[0]: True for case in CASES})
    return
