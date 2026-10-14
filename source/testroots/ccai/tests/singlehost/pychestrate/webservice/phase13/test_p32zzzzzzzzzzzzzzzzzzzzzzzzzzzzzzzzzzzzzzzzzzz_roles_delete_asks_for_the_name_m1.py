"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_roles_delete_asks_for_the_name_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Roles page's Delete asks for the role's name before it submits (XC-15).

.. moduleauthor:: Code Craft AI LLC

The role's Delete is a button inside a form: the name to type is on the button (``data-confirm-type``), and the form posts only once the dialog's
confirming button, kept off until the name is typed, is pressed. The real Roles list template is rendered in the strict environment and its row is
driven in a browser with the shell loaded.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from types import SimpleNamespace
from typing import Any, Dict

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)
from ccai.testshared.factories.webui.template_contexts import (
    MODE_POPULATED,
    build_template_context,
)

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


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

TEMPLATE = "config/roles/list.html"

ROLE_NAME = "Lab Lead"


def _rows_html() -> str:
    context = build_template_context(template_name=TEMPLATE, variable_names=undeclared_variables(template_name=TEMPLATE), mode=MODE_POPULATED)
    context["roles"] = [
        SimpleNamespace(id="11111111-2222-4333-8444-555555555555", name=ROLE_NAME, description="Runs the lab", is_system=False, permissions=[], binding_count=2),
    ]
    context["may_change_roles"] = True
    page = strict_environment().get_template(TEMPLATE).render(context)
    start = page.index('<div class="table-scroll"')
    return page[start:page.index("</table></div>", start) + len("</table></div>")]


def _open(browser: Browser) -> Any:
    page = open_shell_page(browser, **DESKTOP)
    page.evaluate(
        """(html) => {
            window.__submits = 0;
            const holder = document.createElement('div');
            holder.innerHTML = html;
            document.querySelector('main.pyc-site-shell__main').appendChild(holder);
            for (const form of holder.querySelectorAll('form')) {
                form.addEventListener('submit', (event) => {
                    if (event.defaultPrevented === false) { window.__submits += 1; event.preventDefault(); }
                });
            }
        }""",
        _rows_html(),
    )
    return page


def test_the_delete_button_asks_for_the_roles_name_and_submits_only_when_it_is_typed(browser: Browser):
    """
    **Feature: type to confirm on server-rendered pages (XC-15)**
    **Property: choosing Delete on a custom role opens the dialog asking to "Type Lab Lead to confirm" with the confirming button off and
    nothing submitted; typing the wrong name keeps it off; typing the exact name turns it on and pressing it submits the form once; the dialog
    says how many people lose the role.**
    """
    page = _open(browser)
    try:
        page.click('button[data-confirm-type]')
        page.wait_for_selector("dialog.pyc-confirm[open]")
        opened = page.evaluate(
            """() => {
                const dialog = document.querySelector('dialog.pyc-confirm');
                return {
                    label: dialog.querySelector('.pyc-confirm__typed').textContent,
                    disabled: dialog.querySelector('[data-role=confirm-accept]').disabled,
                    message: dialog.textContent.includes('2 users will lose this role'), submits: window.__submits,
                };
            }"""
        )
        page.fill("[data-role=confirm-typed]", "Lab")
        wrong = page.evaluate("() => document.querySelector('[data-role=confirm-accept]').disabled")
        page.fill("[data-role=confirm-typed]", ROLE_NAME)
        right = page.evaluate("() => document.querySelector('[data-role=confirm-accept]').disabled")
        page.click("[data-role=confirm-accept]")
        page.wait_for_timeout(300)
        submits = page.evaluate("() => window.__submits")
    finally:
        page.context.close()

    testbase.assert_equal(
        (opened, wrong, right, submits),
        ({"label": "Type Lab Lead to confirm", "disabled": True, "message": True, "submits": 0}, True, False, 1),
    )
    return


def test_cancelling_the_dialog_submits_nothing(browser: Browser):
    """
    **Feature: type to confirm on server-rendered pages (XC-15)**
    **Property: choosing Cancel in the dialog, even after the right name was typed, submits nothing.**
    """
    page = _open(browser)
    try:
        page.click('button[data-confirm-type]')
        page.wait_for_selector("dialog.pyc-confirm[open]")
        page.fill("[data-role=confirm-typed]", ROLE_NAME)
        page.click("[data-role=confirm-cancel]")
        page.wait_for_timeout(300)
        submits = page.evaluate("() => window.__submits")
    finally:
        page.context.close()

    testbase.assert_equal(submits, 0)
    return
