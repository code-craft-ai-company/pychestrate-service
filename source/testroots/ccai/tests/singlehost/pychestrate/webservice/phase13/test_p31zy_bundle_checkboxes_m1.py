"""
.. module:: test_p31zy_bundle_checkboxes_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The bundle views' native checkboxes follow the theme (ORC-48).

.. moduleauthor:: Code Craft AI LLC

The catalog's "Include retired" and the alert-rule editor's "Enabled" are the
browser's own checkboxes, in the browser's blue whatever the theme. There is
only a checkbox *group* in the component library, so they are styled in their
bundles' stylesheets: the theme's accent colour and a size a finger can hit.
The real stylesheets are loaded and the computed style is measured.
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


CASES = [
    ("pyc-catalog-bundle", "pyc-catalog__checkbox"),
    ("pyc-metrics-bundle", "pyc-metrics__field pyc-metrics__field--inline"),
]

MEASURE_JS: str = """(label_class) => {
    const label = document.createElement('label');
    label.className = label_class;
    const box = document.createElement('input');
    box.type = 'checkbox';
    label.appendChild(box);
    document.body.appendChild(label);
    const probe = document.createElement('span');
    probe.style.color = 'var(--pyc-color-accent)';
    document.body.appendChild(probe);
    const rect = box.getBoundingClientRect();
    return {accent: getComputedStyle(box).accentColor, wanted: getComputedStyle(probe).color,
            width: Math.round(rect.width), height: Math.round(rect.height)};
}"""


def test_the_native_checkboxes_use_the_theme_accent_and_a_usable_size(browser: Browser):
    """
    **Feature: bundle checkboxes (ORC-48)**
    **Property: in the light and the dark theme, each bundle checkbox's
    accent colour is the theme's accent token (not the browser default),
    and it is 18px square.**
    """
    problems = []
    for scheme in ("light", "dark"):
        for bundle, label_class in CASES:
            page = open_shell_page(
                browser, bundle_names=["pyc-site-shell", bundle], color_scheme=scheme,
                viewport={"width": 1200, "height": 800},
            )
            try:
                measured = page.evaluate(MEASURE_JS, label_class)
            finally:
                page.context.close()
            if measured["accent"] != measured["wanted"] or (measured["width"], measured["height"]) != (18, 18):
                problems.append((scheme, bundle, measured))

    testbase.assert_equal(problems, [])
    return
