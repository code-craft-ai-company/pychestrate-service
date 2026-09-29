"""
.. module:: test_p31zv_plain_labels_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Detail pages use plain words, and a run reference is a link (ORC-38).

.. moduleauthor:: Code Craft AI LLC

The build and provisioning-run detail pages said "Layer-5 run" beside a bare
UUID, the builds list and detail page said "Repro digest", and a run's artifact
list said "Results stream (JSOS)": names from inside the product. They now say
"Run" (a link to the run's page), "Inputs digest" (with what it covers) and
"Raw results stream".
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, List

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

PROJECT_ID: str = "0f6c2c1e-4444-4000-8000-000000000001"
RUN_ID: str = "0f6c2c1e-4444-4000-8000-000000000002"
LAYER5_ID: str = "0f6c2c1e-4444-4000-8000-000000000003"

#: Words from inside the product that a person should not have to read.
JARGON: List[str] = ["Layer-5", "Repro digest", "JSOS"]


def test_a_provisioning_run_shows_its_run_as_a_link_with_a_plain_label(browser: Browser):
    """
    **Feature: plain labels (ORC-38)**
    **Property: the provisioning run detail shows a "Run" field whose value
    is a link to /runs/<id>, and no "Layer-5" anywhere.**
    """
    stub = {
        "run_id": RUN_ID, "project_id": PROJECT_ID, "environment_id": "0f6c2c1e-4444-4000-8000-000000000004",
        "action": "apply", "state": "succeeded", "driver": "terraform", "layer5_run_id": LAYER5_ID,
        "created_at": "2026-09-01T10:00:00+00:00", "started_at": "2026-09-01T10:00:05+00:00",
        "finished_at": "2026-09-01T10:01:00+00:00", "plan_issued_at": "2026-09-01T10:00:02+00:00",
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
        page.get_by_role("heading", name="Provisioning run detail", exact=True).first.wait_for()
        page.wait_for_selector(".pyc-provisioning-detail__grid", timeout=8000)
        field = page.locator(".pyc-provisioning-detail__field", has_text="Run").filter(has=page.locator("a"))
        link = field.locator("a").first
        found = (
            link.get_attribute("href"), link.inner_text(),
            [word for word in JARGON if word in page.content()],
        )
    finally:
        page.context.close()

    testbase.assert_equal(found, ("/runs/" + LAYER5_ID, LAYER5_ID, []))
    return


def test_the_bundle_sources_no_longer_use_the_internal_names():
    """
    **Feature: plain labels (ORC-38)**
    **Property: none of the orchestration bundles' sources or built files
    contains "Layer-5 run", "Repro digest" or "JSOS" as a label.**
    """
    root = os.path.join(SITE_DIRECTORIES.DIR_STATIC, "javascript")
    found = []
    for bundle in ("pyc-builds-bundle", "pyc-infra-bundle", "pyc-runs-bundle"):
        for name in sorted(os.listdir(os.path.join(root, bundle))):
            if not name.endswith(".js"):
                continue
            with open(os.path.join(root, bundle, name), encoding="utf-8") as handle:
                text = handle.read()
            for phrase in ("Layer-5 run", "Repro digest", "(JSOS)"):
                if phrase in text:
                    found.append((bundle + "/" + name, phrase))

    testbase.assert_equal(found, [])
    return
