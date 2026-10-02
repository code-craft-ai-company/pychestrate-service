"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzz_page_left_edge_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Every bundle page starts at the same left edge (XC-05).

.. moduleauthor:: Code Craft AI LLC

The server-rendered pages, the Secrets page and the admin pages began 32px inside the shell's main region; every other bundle page
padded its own root another 24px, so moving between pages shifted the heading sideways and the product read as two apps. The shell's
main region supplies the gutter; no bundle root adds to it. The pages are opened in a browser against stubbed API answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Tuple

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

PROJECT: str = "0f6c2c1e-1111-4000-8000-000000000001"
PROJECTS = {"items": [{"project_id": PROJECT, "display_name": "Demo", "slug": "demo"}], "meta": {"total": 1}}

PAGES: List[Tuple[str, str]] = [
    ("/secrets", "pyc-secrets-bundle"),
    ("/admin/system-health", "pyc-admin-bundle"),
    ("/runs?project_id=" + PROJECT, "pyc-runs-bundle"),
    ("/builds?project_id=" + PROJECT, "pyc-builds-bundle"),
    ("/pipelines?project_id=" + PROJECT, "pyc-pipelines-bundle"),
    ("/test-catalog?project_id=" + PROJECT, "pyc-catalog-bundle"),
    ("/environments?project_id=" + PROJECT, "pyc-infra-bundle"),
    ("/slos?project_id=" + PROJECT, "pyc-metrics-bundle"),
    ("/webhooks?project_id=" + PROJECT, "pyc-ops-bundle"),
    ("/pods?project_id=" + PROJECT, "pyc-pods-bundle"),
    ("/clients?project_id=" + PROJECT, "pyc-pods-bundle"),
    ("/resource-pools?project_id=" + PROJECT, "pyc-resources-bundle"),
]


def test_every_bundle_page_has_its_heading_at_the_same_left_edge(browser: Browser):
    """
    **Feature: one app (XC-05)**
    **Property: the page heading of twelve bundle pages (every bundle) starts at one and the same distance from the left
    edge, and that distance is the main region's own gutter (no bundle adds its own on top).**
    """
    edges: Dict[str, int] = {}
    gutter: Dict[str, int] = {}
    for path, bundle in PAGES:
        page = open_shell_page(browser, path=path, bundle_names=["pyc-site-shell", bundle], api_stubs={"/api/v1/projects": PROJECTS}, **DESKTOP)
        try:
            page.wait_for_selector("main h1")
            page.wait_for_timeout(800)
            found = page.evaluate("() => [Math.round(document.querySelector('main h1').getBoundingClientRect().left), Math.round(document.querySelector('main').getBoundingClientRect().left)]")
            edges[path] = found[0]
            gutter[path] = found[0] - found[1]
        finally:
            page.context.close()

    testbase.assert_equal((len(set(edges.values())), len(set(gutter.values()))), (1, 1))
    return
