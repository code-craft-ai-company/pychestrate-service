"""
.. module:: test_p31zx_entity_page_titles_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A bundle detail page's tab names the thing you are looking at (ORC-35).

.. moduleauthor:: Code Craft AI LLC

The shell titles every bundle route from its navigation entry, so a run, a
build, a pod and a pool were all "Runs · Pychestrate", "Builds · Pychestrate"
and so on. Once a detail view has loaded its entity it now puts the entity in
front ("Run 3f2a1b7c · Runs · Pychestrate", the pool's or environment's name
where it has one), and does not stack a second one when it renders again.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES
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
RUN_ID: str = "0f6c2c1e-5555-4000-8000-000000000002"


def test_a_provisioning_run_page_is_titled_by_its_run(browser: Browser):
    """
    **Feature: entity page titles (ORC-35)**
    **Property: after the provisioning run detail view has loaded its run,
    the tab reads "Provisioning run 0f6c2c1e · <section title>" and not just
    the section title.**
    """
    stub = {
        "run_id": RUN_ID, "project_id": PROJECT_ID, "environment_id": "0f6c2c1e-5555-4000-8000-000000000004",
        "action": "apply", "state": "succeeded", "driver": "terraform", "layer5_run_id": None,
        "created_at": "2026-09-01T10:00:00+00:00", "started_at": "2026-09-01T10:00:05+00:00",
        "finished_at": "2026-09-01T10:01:00+00:00", "plan_issued_at": None,
        "final_state_reason": "", "steps": [], "plan_summary": None,
    }
    page = open_shell_page(
        browser,
        path="/provisioning-runs/{}?project_id={}".format(RUN_ID, PROJECT_ID),
        bundle_names=["pyc-site-shell", "pyc-infra-bundle"],
        api_stubs={"/api/v1/projects/{}/provisioning-runs/{}".format(PROJECT_ID, RUN_ID): stub},
        **DESKTOP,
    )
    try:
        page.wait_for_selector(".pyc-provisioning-detail__grid", timeout=8000)
        page.wait_for_function("document.title.startsWith('Provisioning run')", timeout=5000)
        title = page.title()
    finally:
        page.context.close()

    testbase.assert_equal((title.startswith("Provisioning run 0f6c2c1e · "), title.count("Provisioning run")), (True, 1))
    return


def test_a_second_render_replaces_the_entity_instead_of_stacking_a_second_one(browser: Browser):
    """
    **Feature: entity page titles (ORC-35)**
    **Property: setting the entity title twice (a refresh or a poll)
    leaves one entity in front of the section title; an empty label leaves
    the title alone.**
    """
    page = open_shell_page(browser, path="/pods", bundle_names=["pyc-site-shell", "pyc-pods-bundle"], **DESKTOP)
    try:
        page.wait_for_function("document.title === 'Pods \u00b7 Pychestrate'", timeout=8000)
        result = page.evaluate(
            """async () => {
                const t = await import('/static/javascript/shared/page-title.js');
                t.set_entity_title('Pod aaaa');
                const once = document.title;
                t.set_entity_title('Pod bbbb');
                const twice = document.title;
                t.set_entity_title('   ');
                return {once, twice, blank: document.title};
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (result["once"], result["twice"], result["blank"]),
        ("Pod aaaa \u00b7 Pods \u00b7 Pychestrate", "Pod bbbb \u00b7 Pods \u00b7 Pychestrate", "Pod bbbb \u00b7 Pods \u00b7 Pychestrate"),
    )
    return


def test_every_bundle_detail_view_sets_an_entity_title():
    """
    **Feature: entity page titles (ORC-35)**
    **Property: each of the nine bundle detail views calls set_entity_title,
    so a new one cannot quietly skip it.**
    """
    root = os.path.join(SITE_DIRECTORIES.DIR_STATIC, "javascript")
    missing = []
    for bundle in sorted(os.listdir(root)):
        directory = os.path.join(root, bundle)
        if not bundle.startswith("pyc-") or not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if name.endswith("-detail-view.js"):
                with open(os.path.join(directory, name), encoding="utf-8") as handle:
                    if "set_entity_title(" not in handle.read():
                        missing.append(bundle + "/" + name)

    testbase.assert_equal(missing, [])
    return
