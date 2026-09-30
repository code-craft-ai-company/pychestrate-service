"""
.. module:: test_p32q_type_to_confirm_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Deleting a project asks for its name to be typed (XC-15).

.. moduleauthor:: Code Craft AI LLC

A confirmation that says what will be lost is still one click away from losing it.
A form that carries ``data-confirm-type="<text>"`` now asks in the shell's dialog for
that text to be typed, and keeps its confirming button off until it has been (spaces
around it do not matter; case does). Enter with the wrong text does nothing, Cancel and
Escape still submit nothing, and a form without the attribute asks as before. The
project page uses it with the project's name.
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

DIALOG = "dialog.pyc-confirm"

SETUP_JS: str = """(typed) => {
    window.__submits = 0;
    const form = document.createElement('form');
    form.method = 'post';
    form.action = '/projects/1/delete';
    form.setAttribute('data-confirm', 'Delete the project "Alpha Lab"? This permanently deletes its 3 repositories. This cannot be undone.');
    if (typed !== null) { form.setAttribute('data-confirm-type', typed); }
    const button = document.createElement('button');
    button.type = 'submit';
    button.id = 'go';
    button.textContent = 'Delete';
    form.appendChild(button);
    form.addEventListener('submit', (event) => {
        if (event.defaultPrevented === false) { window.__submits += 1; event.preventDefault(); }
    });
    document.querySelector('main.pyc-site-shell__main').appendChild(form);
}"""


def _open(browser: Browser, typed: Any) -> Any:
    page = open_shell_page(browser, **DESKTOP)
    page.evaluate(SETUP_JS, typed)
    return page


def _state(page: Any) -> Dict[str, Any]:
    return page.evaluate(
        """() => {
            const dialog = document.querySelector('dialog.pyc-confirm');
            if (!dialog) { return {open: false, submits: window.__submits}; }
            const input = dialog.querySelector('[data-role=confirm-typed]');
            return {
                open: true, submits: window.__submits, has_input: input !== null,
                accept_disabled: dialog.querySelector('[data-role=confirm-accept]').disabled,
                focused: document.activeElement ? (document.activeElement.getAttribute('data-role') || '') : '',
                label: dialog.querySelector('.pyc-confirm__typed') ? dialog.querySelector('.pyc-confirm__typed').textContent : '',
            };
        }"""
    )


def test_the_confirming_button_stays_off_until_the_name_is_typed_exactly(browser: Browser):
    """
    **Feature: type to confirm (XC-15)**
    **Property: the dialog names the text to type and focuses the field; Delete is off when the field
    is empty, partly typed, or typed in the wrong case; on for the exact text, with or without spaces
    around it; off again when a letter is removed.**
    """
    page = _open(browser, "Alpha Lab")
    try:
        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        opened = _state(page)
        seen = []
        for typed in ("Alpha", "alpha lab", "Alpha Lab", "  Alpha Lab  ", "Alpha La"):
            page.fill("[data-role=confirm-typed]", typed)
            seen.append(_state(page)["accept_disabled"])
    finally:
        page.context.close()

    testbase.assert_equal(
        (opened["has_input"], opened["accept_disabled"], opened["focused"], opened["label"], seen),
        (True, True, "confirm-typed", "Type Alpha Lab to confirm", [True, True, False, False, True]),
    )
    return


def test_enter_confirms_only_with_the_right_text_and_cancel_and_escape_submit_nothing(browser: Browser):
    """
    **Feature: type to confirm (XC-15)**
    **Property: Enter with the wrong text leaves the dialog open and submits nothing; with the right
    text it submits once; Cancel and Escape close the dialog without submitting.**
    """
    page = _open(browser, "Alpha Lab")
    try:
        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        page.fill("[data-role=confirm-typed]", "Alpha")
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        wrong = _state(page)

        page.click("[data-role=confirm-cancel]")
        page.wait_for_timeout(300)
        after_cancel = _state(page)

        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        after_escape = _state(page)

        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        page.fill("[data-role=confirm-typed]", "Alpha Lab")
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)
        after_enter = _state(page)
    finally:
        page.context.close()

    testbase.assert_equal(
        (wrong["open"], wrong["submits"], after_cancel, after_escape, after_enter),
        (True, 0, {"open": False, "submits": 0}, {"open": False, "submits": 0}, {"open": False, "submits": 1}),
    )
    return


def test_a_form_without_the_attribute_asks_as_before(browser: Browser):
    """
    **Feature: type to confirm (XC-15)**
    **Property: a data-confirm form with no data-confirm-type has no field, Delete is on at once, and
    Cancel has focus.**
    """
    page = _open(browser, None)
    try:
        page.click("#go")
        page.wait_for_selector(DIALOG + "[open]")
        state = _state(page)
    finally:
        page.context.close()

    testbase.assert_equal(
        (state["has_input"], state["accept_disabled"], state["focused"]),
        (False, False, "confirm-cancel"),
    )
    return
