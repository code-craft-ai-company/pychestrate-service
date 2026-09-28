"""
.. module:: test_p30x_fragment_link_colour_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Links in server-rendered pages use the accent colour
               (XC-23).

.. moduleauthor:: Code Craft AI LLC

Nothing styled plain links inside ``.pyc-admin-page-fragment``, so
entity links in server tables (user names on /admin/users, role names
on /admin/roles) and "Create your first project" rendered in the
browser's #0000EE blue, and in lavender in dark mode.
``pyc-fragment.css`` now gives them ``--pyc-color-accent-on-surface``
at one-class specificity, leaving buttons and the navigation link
rules alone.
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

#: JS: put a server fragment with a table link, a paragraph link, a
#: button link and a sub-navigation link into the shell's main region;
#: report each one's colour next to the accent token's colour.
FRAGMENT_LINKS_JS: str = r"""
() => {
  const main = document.querySelector('main.pyc-site-shell__main');
  const fragment = document.createElement('section');
  fragment.className = 'pyc-admin-page-fragment';
  fragment.innerHTML = [
    '<nav class="pyc-subnav"><ul><li><a data-probe="subnav" href="/admin/users">Users</a></li></ul></nav>',
    '<table class="data-table"><tbody><tr><td><a data-probe="table" href="/admin/users/1">ada</a></td></tr></tbody></table>',
    '<p><a data-probe="paragraph" href="/projects/new">Create your first project</a></p>',
    '<a data-probe="button" class="btn btn-primary" href="/projects/new">New Project</a>',
  ].join('');
  main.appendChild(fragment);
  const swatch = document.createElement('span');
  swatch.style.color = 'var(--pyc-color-accent-on-surface)';
  fragment.appendChild(swatch);
  const out = {accent: getComputedStyle(swatch).color};
  for (const link of fragment.querySelectorAll('[data-probe]')) {
    out[link.getAttribute('data-probe')] = getComputedStyle(link).color;
  }
  return out;
}
"""


def _link_colours(browser: Browser, *, color_scheme: str) -> Dict[str, str]:
    page = open_shell_page(browser, color_scheme=color_scheme, **DESKTOP)
    try:
        rtnval = page.evaluate(FRAGMENT_LINKS_JS)
    finally:
        page.context.close()
    return rtnval


def test_table_and_text_links_use_the_accent_in_light_mode(browser: Browser):
    """
    **Feature: fragment link colour (XC-23)**
    **Property: in light mode a table link and a paragraph link render
    in the accent-on-surface colour.**
    """
    colours = _link_colours(browser, color_scheme="light")
    testbase.assert_equal(
        (colours["table"], colours["paragraph"]),
        (colours["accent"], colours["accent"]),
        str(colours),
    )
    return


def test_table_and_text_links_use_the_accent_in_dark_mode(browser: Browser):
    """
    **Feature: fragment link colour (XC-23)**
    **Property: in dark mode a table link and a paragraph link render
    in the dark accent-on-surface colour, not the browser's lavender.**
    """
    colours = _link_colours(browser, color_scheme="dark")
    testbase.assert_equal(
        (colours["table"], colours["paragraph"]),
        (colours["accent"], colours["accent"]),
        str(colours),
    )
    return


def test_button_and_subnav_links_keep_their_own_colours(browser: Browser):
    """
    **Feature: fragment link colour (XC-23)**
    **Property: a .btn link and a sub-navigation link are not recoloured
    by the plain-link rule.**
    """
    colours = _link_colours(browser, color_scheme="light")
    testbase.assert_equal(
        (colours["button"] == colours["accent"], colours["subnav"] == colours["accent"]),
        (False, False),
        str(colours),
    )
    return
