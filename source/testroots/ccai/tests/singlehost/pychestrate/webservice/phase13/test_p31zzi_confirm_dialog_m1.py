"""
.. module:: test_p31zzi_confirm_dialog_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A destructive action asks in the site's own dialog (XC-15).

.. moduleauthor:: Code Craft AI LLC

Every ``data-confirm`` form asked through the browser's own confirm box, which a
page can neither style nor word, and which the confirm delegate's comment says
was meant to be replaced by an ``mj-dialog`` the component library does not
ship. The delegate now asks in a modal ``<dialog>``: the message in full, a
title, Cancel focused (a stray Enter deletes nothing), the acting button named
for what it does, Escape meaning no, and the rest of the page inert. A real form
is put in the shell page and used.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from playwright.sync_api import Browser

import os

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

DIALOG = "dialog.pyc-confirm"

SETUP_JS: str = """(label) => {
    window.__nativeConfirms = 0;
    window.confirm = () => { window.__nativeConfirms += 1; return true; };
    window.__submits = 0;
    const form = document.createElement('form');
    form.id = 'victim';
    form.method = 'post';
    form.action = '/projects/1/delete';
    form.setAttribute('data-confirm', 'Delete the project "alpha"?\\nIts 3 repositories and 42 builds go with it. This cannot be undone.');
    const button = document.createElement('button');
    button.type = 'submit';
    button.id = 'go';
    button.textContent = label;
    form.appendChild(button);
    // The delegate holds the first submit (defaultPrevented); only a submit that
    // goes ahead after a yes is counted, and it is not allowed to navigate.
    form.addEventListener('submit', (event) => {
        if (event.defaultPrevented === false) { window.__submits += 1; event.preventDefault(); }
    });
    const main = document.querySelector('main.pyc-site-shell__main');
    main.appendChild(form);
}"""


def _open(browser: Browser, label: str = "Delete project") -> Any:
    page = open_shell_page(browser, **DESKTOP)
    page.evaluate(SETUP_JS, label)
    return page


def test_the_page_asks_in_its_own_dialog_with_the_whole_message_and_cancel_focused(browser: Browser):
    """
    **Feature: confirmation dialog (XC-15)**
    **Property: submitting a data-confirm form opens a modal dialog with a
    title, the message as paragraphs (both lines), a Confirm button named
    "Delete project" and a Cancel button that has focus; the browser's own
    confirm is never called; nothing has been submitted yet.**
    """
    page = _open(browser)
    try:
        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]", timeout=5000)
        found = page.evaluate(
            """() => {
                const dialog = document.querySelector('dialog.pyc-confirm');
                return {
                    title: dialog.querySelector('.pyc-confirm__title').textContent,
                    paragraphs: Array.from(dialog.querySelectorAll('.pyc-confirm__message p')).map((p) => p.textContent),
                    accept: dialog.querySelector('[data-role=confirm-accept]').textContent,
                    focused: document.activeElement.getAttribute('data-role'),
                    labelled: dialog.getAttribute('aria-labelledby'), described: dialog.getAttribute('aria-describedby'),
                    native: window.__nativeConfirms, submits: window.__submits,
                };
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        found,
        {"title": "Please confirm",
         "paragraphs": ['Delete the project "alpha"?', "Its 3 repositories and 42 builds go with it. This cannot be undone."],
         "accept": "Delete project", "focused": "confirm-cancel", "labelled": "pyc-confirm-title",
         "described": "pyc-confirm-message", "native": 0, "submits": 0},
    )
    return


def test_cancel_and_escape_submit_nothing_and_confirm_submits_once(browser: Browser):
    """
    **Feature: confirmation dialog (XC-15)**
    **Property: Cancel and Escape close the dialog without submitting the
    form; Confirm closes it and submits exactly once.**
    """
    page = _open(browser)
    try:
        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        page.click("[data-role=confirm-cancel]")
        page.wait_for_timeout(300)
        after_cancel = (page.locator(DIALOG).count(), page.evaluate("window.__submits"))

        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        after_escape = (page.locator(DIALOG).count(), page.evaluate("window.__submits"))

        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        page.click("[data-role=confirm-accept]")
        page.wait_for_timeout(500)
        after_confirm = (page.locator(DIALOG).count(), page.evaluate("window.__submits"))
    finally:
        page.context.close()

    testbase.assert_equal((after_cancel, after_escape, after_confirm), ((0, 0), (0, 0), (0, 1)))
    return


def test_the_rest_of_the_page_cannot_be_reached_while_the_dialog_is_open(browser: Browser):
    """
    **Feature: confirmation dialog (XC-15)**
    **Property: pressing Tab six times while the dialog is open keeps focus
    inside it, and the submit button behind it cannot be given focus (the
    rest of the page is inert).**
    """
    page = _open(browser)
    try:
        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        outside = False
        for _step in range(6):
            page.keyboard.press("Tab")
            # Focus may leave the page for the browser's own chrome (the active
            # element is then the body); it must never land on a page element.
            if page.evaluate(
                "document.activeElement !== document.body && document.activeElement !== document.documentElement"
                " && !document.activeElement.closest('dialog.pyc-confirm')"
            ):
                outside = True
        # An element behind a modal dialog is inert: it cannot be given focus.
        reachable = page.evaluate("() => { const go = document.getElementById('go'); go.focus(); return document.activeElement === go; }")
    finally:
        page.context.close()

    testbase.assert_equal((outside, reachable), (False, False))
    return


def test_a_button_with_no_usable_label_falls_back_to_continue(browser: Browser):
    """
    **Feature: confirmation dialog (XC-15)**
    **Property: a submitter whose text is longer than 40 characters is not
    used as the acting button's name; the dialog says "Continue".**
    """
    page = _open(browser, label="Yes I really do want to permanently remove this whole thing now")
    try:
        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        accept = page.locator("[data-role=confirm-accept]").inner_text()
    finally:
        page.context.close()

    testbase.assert_equal(accept, "Continue")
    return


def test_a_harmless_action_gets_the_primary_button_and_everything_else_stays_red(browser: Browser):
    """
    **Feature: confirmation dialog (XC-15)**
    **Property: a data-confirm form with no tone has the red (danger) confirming button, as every one did; data-confirm-tone="neutral" on the
    form or on the button gives the primary one (running a job, checking a resource in is not destructive); any other value stays red.**
    """
    def _accept_classes(where: str, value: str = "neutral") -> str:
        page = _open(browser, label="Run job now")
        try:
            if where != "none":
                page.evaluate(
                    "([where, value]) => (where === 'form' ? document.getElementById('victim') : document.getElementById('go')).setAttribute('data-confirm-tone', value)",
                    [where, value],
                )
            page.click("#go")
            page.wait_for_selector(DIALOG + "[open]", timeout=5000)
            return page.evaluate("() => document.querySelector('dialog.pyc-confirm [data-role=confirm-accept]').className")
        finally:
            page.context.close()

    def _tone(classes: str) -> str:
        return "primary" if "pyc-confirm__button--primary" in classes else "danger" if "pyc-confirm__button--danger" in classes else "other"

    testbase.assert_equal(
        (_tone(_accept_classes("none")), _tone(_accept_classes("form")), _tone(_accept_classes("button")), _tone(_accept_classes("form", "calm"))),
        ("danger", "primary", "primary", "danger"),
    )
    return


def test_only_harmless_confirms_in_the_templates_are_neutral():
    """
    **Feature: confirmation dialog (XC-15)**
    **Property: the server-rendered confirms that run a job and check a resource or an address in or out say data-confirm-tone="neutral"; no
    confirm that deletes, revokes, removes, terminates, retires, deactivates or forces is neutral (a red button is what tells a person it cannot be taken back).**
    """
    import re

    root = os.path.join(os.path.dirname(SITE_DIRECTORIES.DIR_STATIC), "blueprints")
    neutral, wrongly_neutral = [], []
    for current, _dirs, names in os.walk(root):
        for name in names:
            if not name.endswith(".html"):
                continue
            with open(os.path.join(current, name), encoding="utf-8") as handle:
                text = handle.read()
            for match in re.finditer(r'data-confirm="([^"]*)"([^>]*)>', text):
                message, rest = match.group(1), match.group(2)
                if 'data-confirm-tone="neutral"' in rest:
                    neutral.append(message.split("?")[0].split("{{")[0].strip())
                    if re.search(r"delete|revoke|remove|terminate|retire|deactivate|force|cancel|release|move|sign out|change", message, re.I):
                        wrongly_neutral.append(message)

    testbase.assert_equal(
        (sorted(set(neutral)), wrongly_neutral),
        (["Check in this IP", "Check in this resource", "Check out", "Check this resource back in", "Dispatch an RPA job with this work packet"], []),
    )
    return
