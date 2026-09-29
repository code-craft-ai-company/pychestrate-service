"""
.. module:: test_p31zz_bundle_control_names_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Every form control of a bundle page has a name (ORC-42).

.. moduleauthor:: Code Craft AI LLC

``mj-select`` takes its accessible name from a wrapping ``<label>``, but
``mj-text-field`` and ``mj-textarea`` do not, and a host ``aria-label`` is not
passed on either: only their own ``label`` attribute names them. Six controls
(the pipeline document and matrix spec, the new resource pool's name,
description and tags, and the webhooks page's project id) had a visible
wrapping label or none and no accessible name. They now use the component's
``label``. The pages are opened in a browser and the accessibility tree read.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict, List, Tuple

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    all_navigation_permissions,
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

ROLES = re.compile(r'^\s*- (combobox|textbox|searchbox|checkbox|listbox|spinbutton|switch|radio)\b(?: "([^"]*)")?', re.M)

PROJECT_ID: str = "0f6c2c1e-6666-4000-8000-000000000001"

#: What the pages fetch on load: one project (so the project picker and the
#: forms that need a project render) and no data.
API_STUBS: Dict[str, Any] = {
    "/api/v1/projects": {"items": [{"project_id": PROJECT_ID, "display_name": "Demo", "slug": "demo"}], "total": 1},
    "/api/v1/resource-pools": {"items": [], "total": 0},
    # The create form is for people who may write pools.
    "/api/v1/me/permissions": {"permissions": all_navigation_permissions() + ["system:resource_pools.write"]},
}

#: (route, bundle, names that must be there)
PAGES: List[Tuple[str, str, List[str]]] = [
    ("/pipelines", "pyc-pipelines-bundle", ["Pipeline document (YAML / JSON)", "Matrix spec (JSON)"]),
    ("/resource-pools", "pyc-resources-bundle", ["Name", "Description", "Capability tags"]),
    ("/webhooks", "pyc-ops-bundle", ["Project id"]),
]


def test_every_form_control_on_these_bundle_pages_has_an_accessible_name(browser: Browser):
    """
    **Feature: labelled controls (ORC-42)**
    **Property: on the pipelines, resource pools and webhooks pages, no
    combobox, textbox or checkbox in the accessibility tree is unnamed, and
    the six controls that were unnamed are there under the names their
    visible labels gave them.**
    """
    problems = []
    for route, bundle, expected in PAGES:
        page = open_shell_page(
            browser, path=route, bundle_names=["pyc-site-shell", bundle], api_stubs=API_STUBS, **DESKTOP,
        )
        try:
            page.wait_for_timeout(1500)
            found = ROLES.findall(page.locator("body").aria_snapshot())
        finally:
            page.context.close()
        names = [name for _role, name in found]
        unnamed = [role for role, name in found if not name.strip()]
        missing = [name for name in expected if name not in names]
        if unnamed or missing:
            problems.append((route, {"unnamed": unnamed, "missing": missing, "names": names}))

    testbase.assert_equal(problems, [])
    return
