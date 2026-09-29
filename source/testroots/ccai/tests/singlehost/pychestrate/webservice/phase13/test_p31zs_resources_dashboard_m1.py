"""
.. module:: test_p31zs_resources_dashboard_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The resources dashboard's cards fit one row, line up, and a new
               lab is told what to do first (RES-44).

.. moduleauthor:: Code Craft AI LLC

At laptop width the four count cards wrapped three and one; the Maintenance
tile's icon circle was 2px taller than the others (its border), so its number
sat low; Quick Actions was a narrow column beside full-width cards; and an
empty lab was shown four zeros and nothing else. The real template is rendered
with fixture data, put into the shell page and measured, and the first-run
checklist is checked from the rendered HTML.
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
from ccai.testshared.factories.webui.dataclass_fixtures import MODE_POPULATED
from ccai.testshared.factories.webui.template_contexts import build_template_context

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    open_shell_page,
)
from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


TEMPLATE = "resources/dashboard.html"
LAPTOP: Dict[str, Any] = {"viewport": {"width": 1024, "height": 768}}
DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}


def _render(**overrides: Any) -> str:
    context = build_template_context(
        template_name=TEMPLATE,
        variable_names=undeclared_variables(template_name=TEMPLATE),
        mode=MODE_POPULATED,
    )
    context.update(overrides)
    return strict_environment().get_template(TEMPLATE).render(context)


def _open(browser: Browser, **options: Any) -> Any:
    page = open_shell_page(browser, **options)
    page.evaluate(
        """(html) => {
            const main = document.querySelector('main.pyc-site-shell__main');
            const section = document.createElement('section');
            section.className = 'pyc-admin-page-fragment';
            section.innerHTML = html;
            main.appendChild(section);
        }""",
        _render(resource_count=12, pool_count=3, ip_pool_count=2, can_manage=True),
    )
    page.wait_for_timeout(200)
    return page


MEASURE_JS: str = r"""
() => {
  const tops = (selector) => Array.from(document.querySelectorAll(selector)).map((el) => Math.round(el.getBoundingClientRect().top));
  const box = (el) => { const r = el.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height)}; };
  const cards = Array.from(document.querySelectorAll('.card'));
  const health = cards.find((c) => (c.querySelector('.card-header') || {}).textContent === 'Resource Health Status');
  const quick = cards.find((c) => (c.querySelector('.card-header') || {}).textContent === 'Quick Actions');
  return {
    statTops: tops('.stat-grid > .stat-card'),
    iconSizes: Array.from(document.querySelectorAll('.pyc-icon-large')).map((el) => box(el)),
    valueTops: tops('.card .center.pad .stat-value'),
    healthWidth: box(health).w, quickWidth: box(quick).w,
  };
}
"""


def test_the_four_count_cards_share_a_row_at_laptop_width(browser: Browser):
    """
    **Feature: resources dashboard (RES-44)**
    **Property: at 1024px the four count cards all start at the same
    height, not three and one.**
    """
    page = _open(browser, **LAPTOP)
    try:
        measured = page.evaluate(MEASURE_JS)
    finally:
        page.context.close()

    testbase.assert_equal((len(measured["statTops"]), len(set(measured["statTops"]))), (4, 1))
    return


def test_the_four_health_tiles_are_one_size_and_their_numbers_line_up(browser: Browser):
    """
    **Feature: resources dashboard (RES-44)**
    **Property: the four state icons are the same size (the Maintenance
    one was 2px taller) and the four numbers under them share a top.**
    """
    page = _open(browser, **DESKTOP)
    try:
        measured = page.evaluate(MEASURE_JS)
    finally:
        page.context.close()

    testbase.assert_equal(
        (len(measured["iconSizes"]), len({(size["w"], size["h"]) for size in measured["iconSizes"]}),
         len(set(measured["valueTops"]))),
        (4, 1, 1),
    )
    return


def test_quick_actions_is_as_wide_as_the_card_above_it(browser: Browser):
    """
    **Feature: resources dashboard (RES-44)**
    **Property: Quick Actions is as wide as the Health card (it was a
    narrow column), and its buttons sit in a row.**
    """
    page = _open(browser, **DESKTOP)
    try:
        measured = page.evaluate(MEASURE_JS)
        button_tops = page.evaluate(
            "() => Array.from(document.querySelectorAll('.actions-row a.btn')).map(el => Math.round(el.getBoundingClientRect().top))"
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (measured["quickWidth"] == measured["healthWidth"], len(button_tops), len(set(button_tops))),
        (True, 4, 1),
    )
    return


def test_an_empty_lab_gets_a_checklist_in_the_order_it_needs_and_a_full_one_does_not():
    """
    **Feature: resources dashboard (RES-44)**
    **Property: with nothing set up (and permission to manage) the page
    shows the three steps in the order pool, devices, IP pool, each marked
    "To do"; with the pool made only that one is "Done"; with everything
    set up, or without permission, there is no checklist.**
    """
    empty = _render(resource_count=0, pool_count=0, ip_pool_count=0, can_manage=True)
    partly = _render(resource_count=0, pool_count=2, ip_pool_count=0, can_manage=True)
    full = _render(resource_count=5, pool_count=2, ip_pool_count=1, can_manage=True)
    viewer = _render(resource_count=0, pool_count=0, ip_pool_count=0, can_manage=False)

    order = [empty.index(text) for text in ("Create a resource pool", "Register your devices", "Create an IP pool")]
    testbase.assert_equal(
        (order == sorted(order), empty.count(">To do<"), partly.count(">Done<"), partly.count(">To do<"),
         "first-run-checklist" in full, "first-run-checklist" in viewer, "Get started" in empty),
        (True, 3, 1, 2, False, False, True),
    )
    return
