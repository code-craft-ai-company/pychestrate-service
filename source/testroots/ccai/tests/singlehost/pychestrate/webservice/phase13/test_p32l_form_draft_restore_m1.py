"""
.. module:: test_p32l_form_draft_restore_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The shell puts back what was typed before a sign-in or form token expired (XC-11).

.. moduleauthor:: Code Craft AI LLC

After a refused form the server hands the page a draft of the typed fields as data
(``<script type="application/json" id="pyc-form-draft">``). The shell fills the form the
draft belongs to with it and says so: text, single and several-choice lists, tick boxes and
radio buttons are put back; passwords, hidden fields and files are left alone (and the notice
says to enter passwords and files again). The page is opened in a browser with a server-rendered
form and a draft.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional

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

FORM = """
<form id="spec-form" method="post">
  <input type="hidden" name="csrf_token" value="fresh-token">
  <input type="text" name="name" value="">
  <input name="branch" value="main">
  <input type="number" name="timeout_minutes" value="60">
  <textarea name="steps">[]</textarea>
  <select name="kind"><option value="a">A</option><option value="b">B</option></select>
  <select name="tags" multiple><option value="x">x</option><option value="y">y</option></select>
  <input type="checkbox" name="enabled" value="true">
  <input type="password" name="passphrase" value="">
</form>
"""

DRAFT = [
    ["csrf_token", "old"], ["name", "Nightly build"], ["branch", "release/2"], ["timeout_minutes", "90"], ["steps", '[{"name": "x"}]'],
    ["kind", "b"], ["tags", "y"], ["enabled", "true"], ["passphrase", "hunter2"], ["unknown_field", "ignored"],
]


def _values(page: Any) -> Dict[str, Any]:
    return page.evaluate(
        """() => {
            const form = document.getElementById('spec-form');
            return {
                name: form.elements.name.value, branch: form.elements.branch.value, timeout: form.elements.timeout_minutes.value,
                steps: form.elements.steps.value, kind: form.elements.kind.value,
                tags: Array.from(form.elements.tags.selectedOptions).map((o) => o.value),
                enabled: form.elements.enabled.checked, passphrase: form.elements.passphrase.value, csrf: form.elements.csrf_token.value,
            };
        }"""
    )


def _notice(page: Any) -> Optional[str]:
    locator = page.locator('[data-role="draft-restored"]')
    return " ".join(locator.first.inner_text().split()) if locator.count() > 0 else None


def test_the_typed_fields_are_put_back_and_the_notice_says_what_is_left_to_enter(browser: Browser):
    """
    **Feature: form drafts (XC-11)**
    **Property: with a draft, the form shows the typed name, branch, timeout, steps and
    choice, the ticked box and the several-choice selection; the hidden token and the
    password keep what the page gave them; a field the form does not have is ignored; a
    notice says it was put back and that passwords and files must be entered again; and
    the ``draft`` parameter is removed from the address.**
    """
    page = open_shell_page(browser, path="/projects/create?draft=tok-123&keep=1", content_html=FORM, form_draft=DRAFT, **DESKTOP)
    try:
        values = _values(page)
        notice = _notice(page)
        address = page.evaluate("() => window.location.search")
    finally:
        page.context.close()

    testbase.assert_equal(
        (values, notice, address),
        (
            {
                "name": "Nightly build", "branch": "release/2", "timeout": "90", "steps": '[{"name": "x"}]', "kind": "b",
                "tags": ["y"], "enabled": True, "passphrase": "", "csrf": "fresh-token",
            },
            "Your session or the form had expired. What you had typed has been put back. Check it, then submit again. "
            "Passwords and files are not restored: enter them again.",
            "?keep=1",
        ),
    )
    return


def test_a_form_without_such_controls_gets_the_short_notice_and_no_draft_means_no_change(browser: Browser):
    """
    **Feature: form drafts (XC-11)**
    **Property: a form with only text fields is restored with the short notice (no line
    about boxes and passwords); a page with no draft, and a draft for a form the page
    does not have, change nothing and show no notice.**
    """
    simple = '<form id="spec-form"><input name="name" value=""><input name="branch" value="main"><textarea name="steps">[]</textarea><select name="kind"><option value="a">A</option></select><input name="timeout_minutes" value="60"><select name="tags" multiple></select><input type="checkbox" name="enabled"><input type="password" name="passphrase"><input type="hidden" name="csrf_token" value="t"></form>'
    plain_form = simple.replace('<select name="tags" multiple></select><input type="checkbox" name="enabled"><input type="password" name="passphrase">', "")

    restored = open_shell_page(browser, path="/projects/create?draft=t", content_html=plain_form, form_draft=[["name", "Only text"]], **DESKTOP)
    try:
        short = _notice(restored)
        name = restored.evaluate("() => document.getElementById('spec-form').elements.name.value")
    finally:
        restored.context.close()

    untouched = open_shell_page(browser, path="/projects/create", content_html=FORM, form_draft=None, **DESKTOP)
    try:
        without_draft = (_notice(untouched), _values(untouched)["name"], _values(untouched)["branch"])
    finally:
        untouched.context.close()

    unrelated = open_shell_page(browser, path="/projects/create?draft=t", content_html=FORM, form_draft=[["nothing_here", "x"]], **DESKTOP)
    try:
        unrelated_state = (_notice(unrelated), _values(unrelated)["name"])
    finally:
        unrelated.context.close()

    testbase.assert_equal(
        (short, name, without_draft, unrelated_state),
        ("Your session or the form had expired. What you had typed has been put back. Check it, then submit again.", "Only text", (None, "", "main"), (None, "")),
    )
    return


CHOICES = """
<form id="choices" method="post">
  <input type="radio" name="mode" value="password" checked> <input type="radio" name="mode" value="invite">
  <input type="checkbox" name="roles" value="viewer" checked> <input type="checkbox" name="roles" value="editor"> <input type="checkbox" name="roles" value="admin">
  <input type="checkbox" name="notify" value="on" checked>
  <select name="tags" multiple><option value="x">x</option><option value="y">y</option><option value="z">z</option></select>
  <input type="text" name="name" value="">
</form>
"""


def test_radio_buttons_tick_boxes_and_several_choice_lists_are_put_back(browser: Browser):
    """
    **Feature: form drafts (XC-11)**
    **Property: a draft that chose the "invite" radio button, ticked the editor and admin boxes (and not the
    viewer or the pre-ticked notify box) and selected two list entries restores exactly that: the radio button,
    the ticks (a box the draft does not name is unticked, even if the page pre-ticked it) and the selection; the
    notice is the short one (nothing was left to enter again).**
    """
    draft = [["mode", "invite"], ["roles", "editor"], ["roles", "admin"], ["tags", "x"], ["tags", "z"], ["name", "Ada"]]
    page = open_shell_page(browser, path="/admin/users/create?draft=t", content_html=CHOICES, form_draft=draft, **DESKTOP)
    try:
        state = page.evaluate(
            """() => {
                const form = document.getElementById('choices');
                const roles = Array.from(form.querySelectorAll('input[name=roles]'));
                return {
                    mode: form.querySelector('input[name=mode]:checked').value,
                    roles: roles.filter((box) => box.checked).map((box) => box.value),
                    notify: form.querySelector('input[name=notify]').checked,
                    tags: Array.from(form.elements.tags.selectedOptions).map((option) => option.value),
                    name: form.elements.name.value,
                };
            }"""
        )
        notice = _notice(page)
    finally:
        page.context.close()

    testbase.assert_equal(
        (state, notice),
        (
            {"mode": "invite", "roles": ["editor", "admin"], "notify": False, "tags": ["x", "z"], "name": "Ada"},
            "Your session or the form had expired. What you had typed has been put back. Check it, then submit again.",
        ),
    )
    return
