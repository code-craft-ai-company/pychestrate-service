"""
.. module:: test_p31zze_run_progress_bar_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The run's progress bar has a name and a spoken value (ORC-24).

.. moduleauthor:: Code Craft AI LLC

The run detail page's progress bar had the ``progressbar`` role and its
numbers but no accessible name (axe ``aria-progressbar-name``), so a screen
reader announced an unnamed progress bar. It is now "Run progress", with a
value text ("42% complete"). The real run page is opened in a browser with a
stubbed running run.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

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

RUN_ID: str = "0f6c2c1e-7777-4000-8000-000000000001"
PROJECT_ID: str = "0f6c2c1e-7777-4000-8000-000000000002"


def test_the_progress_bar_is_named_and_reads_its_value(browser: Browser):
    """
    **Feature: run progress bar (ORC-24)**
    **Property: on a running run at 42%, the progress bar's accessible name
    is "Run progress", its value text is "42% complete" and its value is 42.**
    """
    run = {
        "run_id": RUN_ID, "project_id": PROJECT_ID, "state": "running", "created_at": "2026-09-29T10:00:00+00:00",
        "started_at": "2026-09-29T10:00:05+00:00", "progress_summary": {"percent_complete": 42, "phase": "build"},
    }
    page = open_shell_page(
        browser,
        path="/runs/" + RUN_ID,
        bundle_names=["pyc-site-shell", "pyc-runs-bundle"],
        api_stubs={"/api/v1/runs/" + RUN_ID: run},
        **DESKTOP,
    )
    try:
        page.wait_for_selector('[data-role="progress-bar"]', timeout=8000)
        bar = page.locator('[data-role="progress-bar"]')
        found = (bar.get_attribute("aria-label"), bar.get_attribute("aria-valuetext"), bar.get_attribute("aria-valuenow"))
        named = page.get_by_role("progressbar", name="Run progress").count()
    finally:
        page.context.close()

    testbase.assert_equal((found, named), (("Run progress", "42% complete", "42"), 1))
    return
