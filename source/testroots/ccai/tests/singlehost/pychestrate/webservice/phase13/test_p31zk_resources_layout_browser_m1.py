"""
.. module:: test_p31zk_resources_layout_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The resources pages give the content the width of the page
               and keep row actions compact (RES-33).

.. moduleauthor:: Code Craft AI LLC

The resources pages had two left-hand navigations: the shell's and their
own, beside the content. The content got 837px of a 1440px screen and 421px
of a 1024px one, so tables wrapped to three lines. Each row also stacked
Edit over a solid red Delete, twenty red blocks to a page. The sections now
run across the top of the page (``pyc-subnav-layout--top``), the content
has the full width, and Edit and Delete sit side by side with Delete
outlined instead of filled.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

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
LAPTOP: Dict[str, Any] = {"viewport": {"width": 1024, "height": 768}}
PHONE: Dict[str, Any] = {"viewport": {"width": 390, "height": 844}, "has_touch": True, "is_mobile": True}

#: JS: a resources-style fragment (eleven links in four sections and a card
#: with a table), in the layout the ``top`` argument picks.
FRAGMENT_JS: str = r"""
(top) => {
  const main = document.querySelector('main.pyc-site-shell__main');
  const link = (name) => '<li><a href="/x/' + name + '">' + name + '</a></li>';
  const items = [
    '<li class="pyc-subnav__section">Resources</li>', link('Overview'), link('Resources'), link('Resource Pools'), link('Tags'),
    '<li class="pyc-subnav__section">IP Management</li>', link('IP Pools'),
    '<li class="pyc-subnav__section">Allocations</li>', link('Active Allocations'), link('Allocation History'), link('Reservations'), link('Availability'),
    '<li class="pyc-subnav__section">Monitoring</li>', link('Health Status'),
  ].join('');
  const fragment = document.createElement('section');
  fragment.className = 'pyc-admin-page-fragment pyc-resources-fragment';
  fragment.innerHTML = [
    '<div class="pyc-subnav-layout' + (top ? ' pyc-subnav-layout--top' : '') + '">',
    '<nav class="pyc-subnav" aria-label="Resource management"><ul>' + items + '</ul></nav>',
    '<div class="pyc-subnav-layout__content" data-probe="content"><div class="card">Content</div></div>',
    '</div>',
  ].join('');
  main.appendChild(fragment);
  return true;
}
"""

#: JS: where the navigation and the content sit.
MEASURE_JS: str = r"""
() => {
  const nav = document.querySelector('.pyc-subnav').getBoundingClientRect();
  const content = document.querySelector('[data-probe=content]').getBoundingClientRect();
  return {navBottom: nav.bottom, navHeight: nav.height, contentTop: content.top, contentWidth: content.width,
          contentLeft: content.left, navWidth: nav.width};
}
"""


def _measure(browser: Browser, *, top: bool, **options: Any) -> Dict[str, float]:
    page = open_shell_page(browser, **options)
    try:
        page.evaluate(FRAGMENT_JS, top)
        page.wait_for_timeout(200)
        return page.evaluate(MEASURE_JS)
    finally:
        page.context.close()


def test_the_content_gets_the_width_of_the_page_with_the_sections_on_top(browser: Browser):
    """
    **Feature: resources layout (RES-33)**
    **Property: at 1440px the content of a top-aligned page is at least 1000
    wide and starts below the sections, where the side-by-side layout gave
    it under 900; the sections wrap over at most three lines.**
    """
    side = _measure(browser, top=False, **DESKTOP)
    top = _measure(browser, top=True, **DESKTOP)

    testbase.assert_equal(
        (side["contentWidth"] < 900, top["contentWidth"] >= 1000, top["contentTop"] >= top["navBottom"] - 1,
         top["navHeight"] < 150, top["contentWidth"] - side["contentWidth"] > 200),
        (True, True, True, True, True),
    )
    return


def test_a_laptop_screen_gets_the_side_navigations_width_back(browser: Browser):
    """
    **Feature: resources layout (RES-33)**
    **Property: at 1024px the side-by-side layout leaves the content
    under 650px; the top layout gives it at least 200px more (the width
    of the side navigation and its gap) and over 600px.**
    """
    side = _measure(browser, top=False, **LAPTOP)
    top = _measure(browser, top=True, **LAPTOP)

    testbase.assert_equal(
        (side["contentWidth"] < 650, top["contentWidth"] - side["contentWidth"] >= 200, top["contentWidth"] > 600),
        (True, True, True),
    )
    return


def test_a_phone_still_gets_one_scrolling_row_of_links(browser: Browser):
    """
    **Feature: resources layout (RES-33)**
    **Property: on a 390px phone the top layout keeps the links in one row
    that scrolls, so it does not fill the first screen: the navigation is
    under 100px tall.**
    """
    top = _measure(browser, top=True, **PHONE)

    testbase.assert_equal((top["navHeight"] < 100, top["contentTop"] >= top["navBottom"] - 1), (True, True))
    return


# ---------------------------------------------------------------------------
# The templates
# ---------------------------------------------------------------------------


def _blueprints_root() -> str:
    return os.path.join(os.path.dirname(SITE_DIRECTORIES.DIR_STATIC), "blueprints")


def _read(*parts: str) -> str:
    with open(os.path.join(_blueprints_root(), *parts), encoding="utf-8") as handle:
        return handle.read()


def test_the_resources_pages_use_the_top_layout_and_the_projects_pages_do_not_change():
    """
    **Feature: resources layout (RES-33)**
    **Property: the resources base template asks for the top layout; the
    projects base template keeps the side layout.**
    """
    resources = _read("resources", "templates", "resources", "base.html")
    projects = _read("projects", "templates", "projects", "base.html")

    testbase.assert_equal(
        ("pyc-subnav-layout pyc-subnav-layout--top" in resources, "pyc-subnav-layout--top" in projects),
        (True, False),
    )
    return


def test_edit_and_delete_share_a_row_and_delete_is_not_a_solid_red_block():
    """
    **Feature: resources layout (RES-33)**
    **Property: in the resource, IP pool and tag lists the Edit link and
    the Delete form sit in one row-actions container, and in those and the
    pool list Delete uses the quiet style, not the filled red one; the
    confirmation on Delete is unchanged.**
    """
    results = []
    for folder, name in (("resources", "list.html"), ("ip_pools", "list.html"), ("tags", "list.html"), ("pools", "list.html")):
        source = _read("resources", "templates", "resources", folder, name)
        delete = re.search(r'<form[^>]*_delete[^>]*data-confirm="[^"]+".*?</form>', source, re.S)
        results.append((
            "row-actions" in source or folder == "pools",
            delete is not None and "btn-quiet-danger" in delete.group(0) and "btn-danger" not in delete.group(0).replace("btn-quiet-danger", ""),
        ))

    testbase.assert_equal(results, [(True, True)] * 4)
    return


def test_the_stylesheet_defines_the_top_layout_and_the_quiet_button():
    """
    **Feature: resources layout (RES-33)**
    **Property: pyc-fragment.css defines the top layout, the row-actions
    row and the quiet danger button.**
    """
    with open(os.path.join(SITE_DIRECTORIES.DIR_STATIC, "styles", "pyc-fragment.css"), encoding="utf-8") as handle:
        css = handle.read()

    testbase.assert_equal(
        (".pyc-subnav-layout--top {" in css, ".row-actions {" in css, ".btn-quiet-danger {" in css),
        (True, True, True),
    )
    return
