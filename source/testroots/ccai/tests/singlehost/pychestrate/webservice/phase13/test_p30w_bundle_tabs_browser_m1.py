"""
.. module:: test_p30w_bundle_tabs_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bundle tab strips show which tab is selected and nest
               no controls (XC-07).

.. moduleauthor:: Code Craft AI LLC

The Secrets scope tabs (Org / Project / User) and the Webhooks
direction tabs (Inbound / Outbound) were ``<mj-button>`` hosts. The
library's shadow ``<button>`` inside each one nested a control in a
control, and the Secrets view set ``aria-pressed`` while its stylesheet
styled ``aria-selected``, so the active scope looked like the others.
Both strips are now a ``tablist`` of plain ``<button role="tab">``
elements with ``aria-selected``, roving focus and a linked tabpanel.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List

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

#: JS: describe every tab: element, selected state, focusability and
#: the rendered look that should mark the selected one.
TABS_JS: str = r"""
() => Array.from(document.querySelectorAll('[role="tab"]')).map((tab) => {
  const style = getComputedStyle(tab);
  return {
    label: tab.textContent.trim(),
    tag: tab.tagName.toLowerCase(),
    hasShadow: tab.shadowRoot !== null,
    selected: tab.getAttribute('aria-selected'),
    pressed: tab.getAttribute('aria-pressed'),
    tabIndex: tab.tabIndex,
    look: [style.color, style.borderBottomColor, style.fontWeight].join(' | '),
  };
})
"""

#: JS: the label of the tab that labels the tabpanel.
PANEL_LABEL_JS: str = r"""
() => {
  const panel = document.querySelector('[role="tabpanel"]');
  if (panel === null) {
    return null;
  }
  const tab = document.getElementById(panel.getAttribute('aria-labelledby') || '');
  return tab === null ? null : tab.textContent.trim();
}
"""


def _open(browser: Browser, *, path: str, bundle_name: str) -> Any:
    page = open_shell_page(
        browser,
        path=path,
        bundle_names=["pyc-site-shell", bundle_name],
        **DESKTOP,
    )
    # The view renders its heading and tab strip in one pass.
    page.locator("main.pyc-site-shell__main h1").first.wait_for()
    return page


def _tabs(page: Any) -> List[Dict[str, Any]]:
    rtnval = page.evaluate(TABS_JS)
    return rtnval


def _selected_labels(tabs: List[Dict[str, Any]]) -> List[str]:
    rtnval = [tab["label"] for tab in tabs if tab["selected"] == "true"]
    return rtnval


def _selected_look_is_distinct(tabs: List[Dict[str, Any]]) -> bool:
    """
        True when the selected tab renders differently from every
        unselected one.
    """
    selected = [tab["look"] for tab in tabs if tab["selected"] == "true"]
    others = [tab["look"] for tab in tabs if tab["selected"] != "true"]
    rtnval = len(selected) == 1 and len(others) > 0 and selected[0] not in others
    return rtnval


# ---------------------------------------------------------------------------
# Secrets scope tabs
# ---------------------------------------------------------------------------


def test_secrets_scope_tabs_are_plain_tab_buttons(browser: Browser):
    """
    **Feature: bundle tabs (XC-07)**
    **Property: each Secrets scope tab is a plain <button role="tab">
    with no shadow root and no aria-pressed.**
    """
    page = _open(browser, path="/secrets", bundle_name="pyc-secrets-bundle")
    try:
        found = sorted({(tab["tag"], tab["hasShadow"], tab["pressed"]) for tab in _tabs(page)})
        testbase.assert_equal(found, [("button", False, None)])
    finally:
        page.context.close()
    return


def test_secrets_selected_scope_tab_looks_selected(browser: Browser):
    """
    **Feature: bundle tabs (XC-07)**
    **Property: on load exactly the Org tab is selected, and it renders
    differently from Project and User.**
    """
    page = _open(browser, path="/secrets", bundle_name="pyc-secrets-bundle")
    try:
        tabs = _tabs(page)
        testbase.assert_equal(
            (_selected_labels(tabs), _selected_look_is_distinct(tabs)),
            (["Org"], True),
            str(tabs),
        )
    finally:
        page.context.close()
    return


def test_secrets_clicking_a_scope_moves_the_selection(browser: Browser):
    """
    **Feature: bundle tabs (XC-07)**
    **Property: clicking Project selects only Project, gives it the
    tab stop, renders it as selected, and labels the panel with it.**
    """
    page = _open(browser, path="/secrets", bundle_name="pyc-secrets-bundle")
    try:
        page.get_by_role("tab", name="Project").click()
        tabs = _tabs(page)
        focusable = [tab["label"] for tab in tabs if tab["tabIndex"] == 0]
        testbase.assert_equal(
            (_selected_labels(tabs), focusable, _selected_look_is_distinct(tabs), page.evaluate(PANEL_LABEL_JS)),
            (["Project"], ["Project"], True, "Project"),
            str(tabs),
        )
    finally:
        page.context.close()
    return


# ---------------------------------------------------------------------------
# Webhooks direction tabs
# ---------------------------------------------------------------------------


def test_webhooks_tabs_nest_no_interactive_element(browser: Browser):
    """
    **Feature: bundle tabs (XC-07)**
    **Property: each Webhooks tab is a plain <button role="tab"> with no
    shadow root, so no control is nested in another.**
    """
    page = _open(browser, path="/webhooks", bundle_name="pyc-ops-bundle")
    try:
        found = sorted({(tab["tag"], tab["hasShadow"]) for tab in _tabs(page)})
        testbase.assert_equal(found, [("button", False)])
    finally:
        page.context.close()
    return


def test_webhooks_selected_tab_looks_selected(browser: Browser):
    """
    **Feature: bundle tabs (XC-07)**
    **Property: on load exactly the Inbound tab is selected, and it
    renders differently from Outbound.**
    """
    page = _open(browser, path="/webhooks", bundle_name="pyc-ops-bundle")
    try:
        tabs = _tabs(page)
        testbase.assert_equal(
            (_selected_labels(tabs), _selected_look_is_distinct(tabs)),
            (["Inbound"], True),
            str(tabs),
        )
    finally:
        page.context.close()
    return


def test_webhooks_arrow_key_moves_selection_and_focus(browser: Browser):
    """
    **Feature: bundle tabs (XC-07)**
    **Property: ArrowRight on the focused Inbound tab selects and
    focuses Outbound and labels the panel with it.**
    """
    page = _open(browser, path="/webhooks", bundle_name="pyc-ops-bundle")
    try:
        page.get_by_role("tab", name="Inbound").focus()
        page.keyboard.press("ArrowRight")
        focused = page.evaluate("() => document.activeElement ? document.activeElement.textContent.trim() : null")
        testbase.assert_equal(
            (_selected_labels(_tabs(page)), focused, page.evaluate(PANEL_LABEL_JS)),
            (["Outbound"], "Outbound", "Outbound"),
        )
    finally:
        page.context.close()
    return
