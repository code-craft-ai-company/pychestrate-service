"""
.. module:: test_p31zp_admin_forms_and_rows_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Admin row actions sit side by side and quietly, checkbox
               groups put the box beside its text, and the audit filter row
               shares one baseline (ADM-42).

.. moduleauthor:: Code Craft AI LLC

The real templates are rendered with fixture data (every list holding rows),
put into the shell page, and measured in a browser with the real stylesheet.
Edit and Delete used to stack, one over the other, in every row; the checkboxes
of the UI Profile and Preferences pages sat on a line of their own above their
labels (the ``pyc-choice`` class had no styling at all); and the select of the
audit filter was taller than its inputs, so the labels above them did not line
up.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict, List

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
    template_source,
    undeclared_variables,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

#: Admin lists whose fixture rows show an Edit link and a destructive form,
#: which the browser measures.
ROW_ACTION_TEMPLATES: List[str] = [
    "config/users/list.html",
    "config/variables/list.html",
    "config/secrets/list.html",
]

#: Lists where a row shows both only when it is not built-in / has no secrets,
#: which the fixtures do not include: their markup is checked instead.
CONDITIONAL_ACTION_TEMPLATES: List[str] = [
    "config/roles/list.html",
    "config/secrets/scope_list.html",
]

#: Admin lists whose only row action is one destructive button.
SINGLE_ACTION_TEMPLATES: List[str] = [
    "config/tokens/admin.html",
    "config/tokens/account.html",
    "config/enrollment/list.html",
    "config/sessions/list.html",
]


def _render(template_name: str) -> str:
    context = build_template_context(
        template_name=template_name,
        variable_names=undeclared_variables(template_name=template_name),
        mode=MODE_POPULATED,
    )
    return strict_environment().get_template(template_name).render(context)


def _open_with(browser: Browser, template_name: str) -> Any:
    """The shell page with the rendered template as its content."""
    page = open_shell_page(browser, **DESKTOP)
    page.evaluate(
        """(html) => {
            const main = document.querySelector('main.pyc-site-shell__main');
            const section = document.createElement('section');
            section.className = 'pyc-admin-page-fragment';
            section.innerHTML = html;
            main.appendChild(section);
        }""",
        _render(template_name),
    )
    page.wait_for_timeout(200)
    return page


#: JS: for each body row that has controls in its last cell, the tops and
#: the number of controls (links and buttons).
ROW_CONTROLS_JS: str = r"""
() => Array.from(document.querySelectorAll('table tbody tr')).map((tr) => {
  const cell = tr.querySelector('td:last-child');
  if (!cell) { return null; }
  const controls = Array.from(cell.querySelectorAll('a.btn, button.btn')).filter((el) => el.offsetParent !== null);
  if (controls.length < 2) { return null; }
  const tops = controls.map((el) => Math.round(el.getBoundingClientRect().top));
  return {count: controls.length, spread: Math.max(...tops) - Math.min(...tops),
          danger: controls.filter((el) => el.classList.contains('btn-danger')).length,
          height: Math.round(cell.getBoundingClientRect().height)};
}).filter((row) => row !== null)
"""


def test_edit_and_the_destructive_action_share_a_line_in_the_admin_lists(browser: Browser):
    """
    **Feature: admin row actions (ADM-42)**
    **Property: in the users, variables, roles, secrets and secret-scope
    lists, every row with two or more actions has them on one line (their
    tops within 3px), and none of them is the filled red button.**
    """
    problems = []
    for template_name in ROW_ACTION_TEMPLATES:
        page = _open_with(browser, template_name)
        try:
            rows = page.evaluate(ROW_CONTROLS_JS)
        finally:
            page.context.close()
        if len(rows) == 0:
            problems.append((template_name, "no row with two actions"))
        for row in rows:
            if row["spread"] > 3 or row["danger"] > 0:
                problems.append((template_name, row))

    testbase.assert_equal(problems, [])
    return


def test_the_lists_whose_fixtures_show_one_action_still_group_them_and_use_the_quiet_button():
    """
    **Feature: admin row actions (ADM-42)**
    **Property: the roles and secret-scope lists put their actions in a
    ``row-actions`` container and use the quiet destructive button.**
    """
    results = {}
    for template_name in CONDITIONAL_ACTION_TEMPLATES:
        source = template_source(template_name=template_name)
        results[template_name] = ("row-actions" in source, "btn-quiet-danger" in source, "btn-danger" in source)

    testbase.assert_equal(results, {name: (True, True, False) for name in CONDITIONAL_ACTION_TEMPLATES})
    return


def test_a_lone_destructive_row_action_is_not_a_filled_red_block():
    """
    **Feature: admin row actions (ADM-42)**
    **Property: the token, enrollment-token and session lists use the quiet
    destructive button for their per-row action (the one bulk "Terminate
    all" button on the sessions page stays filled).**
    """
    counts = {}
    for template_name in SINGLE_ACTION_TEMPLATES:
        source = template_source(template_name=template_name)
        counts[template_name] = (len(re.findall(r"btn-quiet-danger", source)), len(re.findall(r"btn-danger", source)))

    testbase.assert_equal(
        counts,
        {"config/tokens/admin.html": (1, 0), "config/tokens/account.html": (1, 0),
         "config/enrollment/list.html": (1, 0), "config/sessions/list.html": (2, 1)},
    )
    return


#: JS: for each choice, the checkbox and the label's first line.
CHOICES_JS: str = r"""
() => Array.from(document.querySelectorAll('.pyc-choice')).map((choice) => {
  const box = choice.querySelector('input[type=checkbox]').getBoundingClientRect();
  const label = choice.querySelector('label').getBoundingClientRect();
  return {beside: box.right <= label.left + 1, top: Math.round(box.top - label.top), labelWidth: Math.round(label.width)};
})
"""


def test_the_checkbox_sits_beside_its_label_on_the_ui_profile_and_preferences_pages(browser: Browser):
    """
    **Feature: checkbox groups (ADM-42)**
    **Property: on both pages every checkbox is to the left of its label
    text and level with the label's first line (within 12px of its top), and
    the label is wider than 150px, not a narrow column of its own.**
    """
    problems = []
    for template_name in ("config/ui_profile.html", "config/account_preferences.html"):
        page = _open_with(browser, template_name)
        try:
            choices = page.evaluate(CHOICES_JS)
        finally:
            page.context.close()
        if len(choices) == 0:
            problems.append((template_name, "no choices"))
        for choice in choices:
            if choice["beside"] is False or not (-2 <= choice["top"] <= 12) or choice["labelWidth"] < 150:
                problems.append((template_name, choice))

    testbase.assert_equal(problems, [])
    return


#: JS: the audit filter's labels and controls.
AUDIT_FILTER_JS: str = r"""
() => {
  const form = document.querySelector('.pyc-audit-filters');
  const groups = Array.from(form.querySelectorAll('.form-group')).filter((g) => g.querySelector('label'));
  return groups.map((g) => ({
    labelTop: Math.round(g.querySelector('label').getBoundingClientRect().top),
    controlHeight: Math.round(g.querySelector('.form-control').getBoundingClientRect().height),
  }));
}
"""


def test_the_audit_filter_labels_share_a_line_and_its_controls_one_height(browser: Browser):
    """
    **Feature: audit filter (ADM-42)**
    **Property: the five audit filters' labels all start at the same
    height (within 1px) and their controls have the same height.**
    """
    page = _open_with(browser, "config/audit/list.html")
    try:
        groups = page.evaluate(AUDIT_FILTER_JS)
    finally:
        page.context.close()
    tops = {group["labelTop"] for group in groups}
    heights = {group["controlHeight"] for group in groups}

    testbase.assert_equal(
        (len(groups), max(tops) - min(tops) <= 1, max(heights) - min(heights) <= 1),
        (5, True, True),
    )
    return
