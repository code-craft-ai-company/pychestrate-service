"""
.. module:: test_p31zzzw_projects_nav_highlight_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The sidebar highlights the right projects entry (PRJ-27).

.. moduleauthor:: Code Craft AI LLC

The Projects group now has two entries, "Projects Dashboard" at
``/projects/dashboard`` and "All Projects" at ``/projects``. The shell picks the
active entry by the longest matching address, so the dashboard wins on its own
page and "All Projects" stays lit on the list and on every page of a project.
The shell is opened in a browser with the real navigation manifest.
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


def test_the_sidebar_lights_the_entry_that_matches_the_page(browser: Browser):
    """
    **Feature: one name per projects page (PRJ-27)**
    **Property: on /projects/dashboard the sidebar's active entry is "Projects
    Dashboard"; on /projects, /projects/list, a project's page and its members
    page it is "All Projects".**
    """
    active: Dict[str, Any] = {}
    for path in ("/projects/dashboard", "/projects", "/projects/list", "/projects/7", "/projects/7/members"):
        page = open_shell_page(browser, path=path, **DESKTOP)
        try:
            page.wait_for_selector('a[aria-current="page"]', state="attached")
            active[path] = [text.strip() for text in page.locator('a[aria-current="page"]').all_text_contents()]
        finally:
            page.context.close()

    testbase.assert_equal(
        active,
        {
            "/projects/dashboard": ["Projects Dashboard"],
            "/projects": ["All Projects"],
            "/projects/list": ["All Projects"],
            "/projects/7": ["All Projects"],
            "/projects/7/members": ["All Projects"],
        },
    )
    return
