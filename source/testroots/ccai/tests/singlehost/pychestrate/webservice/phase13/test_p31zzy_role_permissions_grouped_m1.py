"""
.. module:: test_p31zzy_role_permissions_grouped_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Building a role picks permissions by product area, not from 73 raw keys (ADM-06).

.. moduleauthor:: Code Craft AI LLC

The role forms listed every permission key in one scroll box, 52 of the 73
described as "... via the REST surface". They now group the keys by product
area ("Builds", "Resource pools") with plain names for what each allows ("View",
"Start", "Administer"), a filter box and a selected count; the checkbox value is
still the canonical key. The grouping is tested on the real catalog, the markup
in the strict template environment, and the filter in a browser.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from types import SimpleNamespace
from typing import Any, Dict, List

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.security.rbac.extensions.core_permissions import _CORE_PERMISSION_DESCRIPTIONS
from ccai.pychestrate.webservice.webinterface.foundation.permission_presentation import (
    group_permissions,
    plain_description,
)

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    open_fixture_page,
)
from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import strict_environment


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}


def _catalog() -> List[Any]:
    return [SimpleNamespace(id=key, name=key, description=text) for key, text in _CORE_PERMISSION_DESCRIPTIONS.items()]


def test_every_key_is_in_exactly_one_named_area_in_a_sensible_order():
    """
    **Feature: roles built by area (ADM-06)**
    **Property: the catalog's keys fall into fewer than 45 areas with distinct,
    readable names, each key appears exactly once, areas are sorted by name,
    and within an area a key that only views comes before one that changes.**
    """
    catalog = _catalog()
    groups = group_permissions(catalog)
    labels = [group["label"] for group in groups]
    placed = [item["permission"].name for group in groups for item in group["items"]]
    builds = next(group for group in groups if group["label"] == "Builds")

    testbase.assert_equal(
        (
            len(catalog) > 60,
            len(groups) < 45,
            len(set(labels)) == len(labels),
            sorted(placed) == sorted(_CORE_PERMISSION_DESCRIPTIONS.keys()),
            labels == sorted(labels, key=str.lower),
            [item["label"] for item in builds["items"]],
        ),
        (True, True, True, True, True, ["View", "Start"]),
    )
    return


def test_actions_and_areas_are_named_for_people():
    """
    **Feature: roles built by area (ADM-06)**
    **Property: a nested action reads "Members · manage", a key with no action
    name in the table is humanised, and the description no longer says "via the
    REST surface" anywhere in the catalog.**
    """
    groups = group_permissions(_catalog())
    by_key = {item["permission"].name: (group["label"], item["label"], item["description"]) for group in groups for item in group["items"]}

    testbase.assert_equal(
        (
            by_key["system:projects.members.manage"][:2],
            by_key["system:project_secrets.read"][:2],
            by_key["system:rpa.job_types.manage"][:2],
            [key for key, (_area, _action, description) in by_key.items() if "REST surface" in description],
            plain_description("Read runs and run-state listings via the REST surface"),
        ),
        (
            ("Projects", "Members · manage"),
            ("Project secrets", "View"),
            ("RPA", "Job types · manage"),
            [],
            "Read runs and run-state listings",
        ),
    )
    return


def _picker_html(selected: List[str]) -> str:
    template = strict_environment().from_string(
        '{% import "site_shell/_macros.html" as ui %}{{ ui.permission_picker(permissions, selected) }}'
        '{% include "site_shell/_permission_filter.html" %}'
    )
    return template.render(permissions=_catalog(), selected=selected)


def test_the_form_markup_keeps_the_canonical_key_as_the_value_and_checks_the_held_ones():
    """
    **Feature: roles built by area (ADM-06)**
    **Property: the picker renders one checkbox per key whose value is the
    canonical key, checks exactly the keys the role holds, wraps each area in
    a fieldset with its name as the legend, and carries a filter box.**
    """
    held = ["system:builds.read", "system:runs.read"]
    html_text = _picker_html(held)
    values = re.findall(r'<input type="checkbox" name="permission_keys" value="([^"]+)"', html_text)
    checked = re.findall(r'value="([^"]+)" checked', html_text)

    testbase.assert_equal(
        (
            sorted(values) == sorted(_CORE_PERMISSION_DESCRIPTIONS.keys()),
            sorted(checked),
            html_text.count("<fieldset") == len(group_permissions(_catalog())),
            "<legend>Resource pools</legend>" in html_text,
            'data-role="permission-filter"' in html_text,
        ),
        (True, sorted(held), True, True, True),
    )
    return


def test_the_filter_narrows_the_list_by_words_and_the_count_follows_the_ticks(browser: Browser):
    """
    **Feature: roles built by area (ADM-06)**
    **Property: typing "secret" leaves only permissions whose area, name or
    description mention it and hides the emptied areas; a filter nothing matches
    says so; clearing it restores all; the count reads "N of 73 selected" and
    follows the ticks.**
    """
    page = open_fixture_page(browser, body_html="<form>" + _picker_html([]) + "</form>", **DESKTOP)
    try:
        visible = "() => [...document.querySelectorAll('[data-permission-text]')].filter((row) => !row.hidden).length"
        groups_visible = "() => [...document.querySelectorAll('[data-permission-group]')].filter((group) => !group.hidden).map((group) => group.querySelector('legend').textContent)"
        total = page.evaluate(visible)
        initial = page.locator('[data-role="permission-count"]').inner_text()
        page.locator('[data-role="permission-filter"]').fill("secret")
        secret_rows = page.evaluate(visible)
        secret_areas = page.evaluate(groups_visible)
        page.locator('[data-role="permission-filter"]').fill("zzzzqq")
        none_shown = not page.locator('[data-role="permission-none"]').is_hidden()
        page.locator('[data-role="permission-filter"]').fill("")
        restored = page.evaluate(visible)
        page.locator("input[name=permission_keys]").first.check()
        page.locator("input[name=permission_keys]").nth(1).check()
        after = page.locator('[data-role="permission-count"]').inner_text()
    finally:
        page.context.close()

    testbase.assert_equal(
        (total, initial, 0 < secret_rows < total, secret_areas, none_shown, restored, after),
        (73, "0 of 73 selected", True, ["Project secrets", "Secrets"], True, 73, "2 of 73 selected"),
    )
    return



def test_a_permission_row_reads_checkbox_then_name_over_description(browser: Browser):
    """
    **Feature: roles built by area (ADM-06)**
    **Property: inside the real form's ``.form-group`` (whose generic label rule
    is display: block) a permission row keeps its checkbox beside the text, and
    the description starts below the name.**
    """
    stylesheet = '<link rel="stylesheet" href="/static/styles/pyc-tokens.css"><link rel="stylesheet" href="/static/styles/pyc-fragment.css">'
    page = open_fixture_page(
        browser,
        body_html=stylesheet + '<section class="pyc-admin-page-fragment"><form><div class="form-group">' + _picker_html([]) + "</div></form></section>",
        **DESKTOP,
    )
    try:
        page.wait_for_timeout(500)
        boxes = page.evaluate(
            """() => {
                const row = document.querySelector('[data-permission-text*="builds"]');
                const check = row.querySelector('input').getBoundingClientRect();
                const name = row.querySelector('.pyc-permissions__name').getBoundingClientRect();
                const description = row.querySelector('.pyc-permissions__description').getBoundingClientRect();
                return {check_right: check.right, check_top: check.top, name_left: name.left, name_top: name.top,
                        name_bottom: name.bottom, description_top: description.top};
            }"""
        )
    finally:
        page.context.close()

    testbase.assert_equal(
        (
            boxes["check_right"] <= boxes["name_left"] + 1,
            abs(boxes["check_top"] - boxes["name_top"]) < 12,
            boxes["description_top"] >= boxes["name_bottom"] - 1,
        ),
        (True, True, True),
    )
    return
