"""
.. module:: test_p31zzf_chart_focus_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The timeseries chart leaves no focusable element inside its aria-hidden SVG (ORC-24).

.. moduleauthor:: Code Craft AI LLC

``<mj-chart>`` hides its SVG from assistive technology (its data is also in an
accessible table) but its renderers give every data point ``tabindex="0"``, so
a keyboard user could tab to points a screen reader cannot see (axe
``aria-hidden-focus``, serious). The timeseries view takes the points out of
the tab order after each render. The real page is opened with chart data.
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

POINTS = [{"observed_at": "2026-09-29T0{}:00:00+00:00".format(hour), "value": float(hour)} for hour in range(1, 9)]
STUBS: Dict[str, Any] = {
    "/api/v1/metrics/catalog": {"items": [{"name": "demo_metric", "kind": "gauge"}]},
    "/api/v1/metrics/timeseries": {"points": POINTS, "metric": "demo_metric"},
}


def test_no_element_inside_the_charts_hidden_svg_can_take_focus(browser: Browser):
    """
    **Feature: chart focus (ORC-24)**
    **Property: with data on the timeseries page, the chart's SVG is
    aria-hidden and has no element with a tabindex, and pressing Tab through
    the page never lands inside it.**
    """
    page = open_shell_page(browser, path="/timeseries", bundle_names=["pyc-site-shell", "pyc-metrics-bundle"], api_stubs=STUBS, **DESKTOP)
    try:
        page.wait_for_selector("mj-chart", timeout=8000)
        page.wait_for_timeout(1500)
        state = page.evaluate(
            """() => {
                const svg = document.querySelector('mj-chart').shadowRoot.querySelector('svg');
                return {hidden: svg.getAttribute('aria-hidden'), focusable: svg.querySelectorAll('[tabindex]').length};
            }"""
        )
        landed_inside = False
        for _step in range(40):
            page.keyboard.press("Tab")
            inside = page.evaluate(
                """() => {
                    let active = document.activeElement;
                    while (active && active.shadowRoot && active.shadowRoot.activeElement) { active = active.shadowRoot.activeElement; }
                    return !!(active && active.closest && active.closest('svg'));
                }"""
            )
            landed_inside = landed_inside or inside
    finally:
        page.context.close()

    testbase.assert_equal((state["hidden"], state["focusable"], landed_inside), ("true", 0, False))
    return
