"""
.. module:: test_p30zz_bundle_control_hosts_unboxed_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bundle controls are not wrapped in a second box, and
               primary buttons are real primary buttons (ORC-19).

.. moduleauthor:: Code Craft AI LLC

Every bundle stylesheet gave its filter and form controls (``mj-select``,
``mj-text-field``, ``mj-textarea``, ``mj-password-field``, ``mj-button``)
a host-level padding, border, radius and background. The component draws
its own frame inside, so each control sat in a second bordered box, and a
"primary" button was a white button on a blue slab. The host classes now
carry only layout and type; a primary button says ``variant="primary"``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import glob
import os
import re

from typing import Dict, List, Set, Tuple

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


#: Components a bundle draws a frame around, so a host class on one of
#: them must not draw a second frame.
FRAMED_HOSTS: Tuple[str, ...] = (
    "mj-button", "mj-text-field", "mj-select", "mj-textarea", "mj-password-field",
)

#: Host classes that legitimately style their own surface: the small
#: "dismiss" cross on a toast, and chips / tags, which are not controls.
EXEMPT_CLASS = re.compile(r"(toast-dismiss|__tag$|__chart$)")

BOX_DECLARATION = re.compile(
    r"^\s*(padding(-[a-z-]+)?|border(-[a-z-]+)?|background(-color)?|box-shadow)\s*:", re.IGNORECASE
)

PRIMARY_CLASS = re.compile(r"(__submit|__primary)$")


def _bundle_root() -> str:
    rtnval = os.path.join(SITE_DIRECTORIES.DIR_STATIC, "javascript")
    return rtnval


def _framed_host_classes() -> Dict[str, Set[str]]:
    """
        ``{bundle name: host classes}`` for every class a bundle's source
        adds to a freshly created framed component.
    """
    rtnval: Dict[str, Set[str]] = {}
    creation = re.compile(r'const (\w+) = document\.createElement\("(mj-[a-z-]+)"\);((?:\n.*){0,8})')
    for path in glob.glob(os.path.join(_bundle_root(), "pyc-*-bundle", "*.js")):
        if os.path.basename(path) == "index.js":
            continue
        bundle = os.path.basename(os.path.dirname(path))
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        for match in creation.finditer(text):
            name, tag, tail = match.group(1), match.group(2), match.group(3)
            if tag not in FRAMED_HOSTS:
                continue
            for added in re.finditer(re.escape(name) + r'\.classList\.add\("([^"]+)"', tail):
                for cls in added.group(1).replace('"', "").split(","):
                    cls = cls.strip()
                    if len(cls) > 0 and EXEMPT_CLASS.search(cls) is None:
                        rtnval.setdefault(bundle, set()).add(cls)
    return rtnval


def test_no_bundle_stylesheet_boxes_a_framed_component_host():
    """
    **Feature: bundle controls (ORC-19)**
    **Property: no bundle stylesheet declares a padding, border,
    background or shadow on a class that a bundle puts on an mj-select,
    mj-text-field, mj-textarea, mj-password-field or mj-button.**
    """
    offenders: List[str] = []
    for bundle, classes in sorted(_framed_host_classes().items()):
        css_path = os.path.join(_bundle_root(), bundle, bundle + ".css")
        with open(css_path, "r", encoding="utf-8") as handle:
            css = handle.read()
        for rule in re.finditer(r"(?m)^([^\n{}@/][^{}]*)\{([^{}]*)\}", css):
            selectors = [item.strip() for item in rule.group(1).split(",")]
            if any(re.match(r"^\.([A-Za-z0-9_-]+)$", sel) and sel[1:] in classes for sel in selectors) is False:
                continue
            for line in rule.group(2).split("\n"):
                if BOX_DECLARATION.match(line) is not None:
                    offenders.append("{}: {} -> {}".format(bundle, rule.group(1).strip(), line.strip()))
    testbase.assert_equal(offenders, [])
    return


def test_primary_buttons_are_variant_primary():
    """
    **Feature: bundle controls (ORC-19)**
    **Property: every mj-button a bundle marks as its submit or primary
    button sets variant="primary" instead of colouring the host.**
    """
    creation = re.compile(r'const (\w+) = document\.createElement\("mj-button"\);((?:\n.*){0,8})')
    missing: List[str] = []
    for path in glob.glob(os.path.join(_bundle_root(), "pyc-*-bundle", "*.js")):
        if os.path.basename(path) == "index.js":
            continue
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        for match in creation.finditer(text):
            name, tail = match.group(1), match.group(2)
            added = re.search(re.escape(name) + r'\.classList\.add\("([^"]+)"', tail)
            if added is None:
                continue
            classes = [c.strip().strip('"') for c in added.group(1).split(",")]
            if any(PRIMARY_CLASS.search(c) or c.endswith("--primary") for c in classes) is False:
                continue
            if re.search(re.escape(name) + r'\.setAttribute\("variant", "primary"\)', tail) is None:
                missing.append("{}: {}".format(os.path.relpath(path, _bundle_root()), name))
    testbase.assert_equal(missing, [])
    return


HOST_BOX_JS: str = r"""
async () => {
  await customElements.whenDefined('mj-select');
  const read = (selector) => {
    const el = document.querySelector(selector);
    if (el === null) {
      return null;
    }
    const style = getComputedStyle(el);
    return [style.borderTopWidth, style.paddingTop, style.backgroundColor].join(' | ');
  };
  return {
    select: read('mj-select.pyc-runs-list__select'),
    button: read('mj-button.pyc-runs-list__button'),
  };
}
"""


def test_the_runs_filter_hosts_draw_no_frame_of_their_own(browser: Browser):
    """
    **Feature: bundle controls (ORC-19)**
    **Property: on the runs page the state filter and the Refresh button
    hosts have no border, no padding and a transparent background.**
    """
    page = open_shell_page(
        browser,
        path="/runs",
        bundle_names=["pyc-site-shell", "pyc-runs-bundle"],
        viewport={"width": 1440, "height": 900},
    )
    try:
        page.locator("mj-select.pyc-runs-list__select").first.wait_for()
        found = page.evaluate(HOST_BOX_JS)
        testbase.assert_equal(
            found, {"select": "0px | 0px | rgba(0, 0, 0, 0)", "button": "0px | 0px | rgba(0, 0, 0, 0)"},
        )
    finally:
        page.context.close()
    return
