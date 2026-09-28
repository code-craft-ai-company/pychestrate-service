"""
.. module:: test_p30v_detail_view_landmarks_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bundle detail views add no second main landmark (XC-03).

.. moduleauthor:: Code Craft AI LLC

The site shell's ``<main class="pyc-site-shell__main">`` is the page's
one main landmark and every bundle mounts inside it. Five detail views
(provisioning run, pod, client, resource pool and resource) also put
``role="main"`` on their own root, so those pages exposed main > main.
They now use a named region, like the run and build detail views.
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

SAMPLE_ID: str = "0f6c2c1e-3333-4000-8000-00000000000b"


def _landmarks_on(browser: Browser, *, path: str, bundle_name: str, view_label: str) -> Dict[str, int]:
    """
        Open a detail route with its bundle, wait for the view's chrome
        (its heading, also ``view_label``), and count the main landmarks
        and the region named ``view_label``.
    """
    page = open_shell_page(
        browser,
        path=path,
        bundle_names=["pyc-site-shell", bundle_name],
        **DESKTOP,
    )
    try:
        page.get_by_role("heading", name=view_label, exact=True).first.wait_for()
        rtnval = {
            "main": page.get_by_role("main").count(),
            "region": page.get_by_role("region", name=view_label, exact=True).count(),
        }
    finally:
        page.context.close()
    return rtnval


def test_provisioning_run_detail_has_one_main_landmark(browser: Browser):
    """
    **Feature: site shell -- landmarks (XC-03)**
    **Property: the provisioning run detail page exposes one main
    landmark and names its own region.**
    """
    found = _landmarks_on(
        browser,
        path="/provisioning-runs/" + SAMPLE_ID,
        bundle_name="pyc-infra-bundle",
        view_label="Provisioning run detail",
    )
    testbase.assert_equal(found, {"main": 1, "region": 1})
    return


def test_pod_detail_has_one_main_landmark(browser: Browser):
    """
    **Feature: site shell -- landmarks (XC-03)**
    **Property: the pod detail page exposes one main landmark and names
    its own region.**
    """
    found = _landmarks_on(
        browser,
        path="/pods/" + SAMPLE_ID,
        bundle_name="pyc-pods-bundle",
        view_label="Pod detail",
    )
    testbase.assert_equal(found, {"main": 1, "region": 1})
    return


def test_client_detail_has_one_main_landmark(browser: Browser):
    """
    **Feature: site shell -- landmarks (XC-03)**
    **Property: the client detail page exposes one main landmark and
    names its own region.**
    """
    found = _landmarks_on(
        browser,
        path="/clients/" + SAMPLE_ID,
        bundle_name="pyc-pods-bundle",
        view_label="Client detail",
    )
    testbase.assert_equal(found, {"main": 1, "region": 1})
    return


def test_resource_pool_detail_has_one_main_landmark(browser: Browser):
    """
    **Feature: site shell -- landmarks (XC-03)**
    **Property: the resource pool detail page exposes one main landmark
    and names its own region.**
    """
    found = _landmarks_on(
        browser,
        path="/resource-pools/" + SAMPLE_ID,
        bundle_name="pyc-resources-bundle",
        view_label="Resource pool detail",
    )
    testbase.assert_equal(found, {"main": 1, "region": 1})
    return


def test_resource_detail_has_one_main_landmark(browser: Browser):
    """
    **Feature: site shell -- landmarks (XC-03)**
    **Property: the resource detail page exposes one main landmark and
    names its own region.**
    """
    found = _landmarks_on(
        browser,
        path="/resource-pools/resources/" + SAMPLE_ID,
        bundle_name="pyc-resources-bundle",
        view_label="Resource detail",
    )
    testbase.assert_equal(found, {"main": 1, "region": 1})
    return
