"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_roles_say_what_the_menu_needs_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The role picker says what the menu also needs beside a permission (ADM-06).

.. moduleauthor:: Code Craft AI LLC

A menu entry is shown only to someone who holds every permission it needs: its own, and its group's. Admin, Users needs
``system:users.read`` and also ``system:ui.admin.view`` (the whole Admin menu does); Resources and Pools needs ``resources.read`` and
``resource_pools.read``; Dashboards needs ``metrics.read`` and ``dashboards.read``. A role built with one half got no entry and no message
saying why. The picker now says, under each permission involved, which menu entry also needs which other permission, named as the picker shows
it. The hints come from the navigation manifest, so a new entry with two requirements is covered without a second list to keep.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from types import SimpleNamespace
from typing import Any, Dict, List

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import permission_presentation as presentation
from ccai.pychestrate.webservice.webinterface.site_shell import nav_manifest

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm


def test_each_half_of_a_pair_names_the_other():
    """
    **Feature: role picker menu hints (ADM-06)**
    **Property: the two halves of Resources and Pools, and of Dashboards, each say the entry also needs the other (named as the picker shows
    it); Users says it also needs the Admin menu permission; a permission no menu entry pairs gets no hint.**
    """
    hints = {
        key: presentation.menu_hint(key)
        for key in (
            "system:resources.read", "system:resource_pools.read", "system:metrics.read", "system:dashboards.read",
            "system:users.read", "system:builds.read",
        )
    }

    testbase.assert_equal(
        hints,
        {
            "system:resources.read": "In the menu, Resources and Pools also needs Resource pools › View.",
            "system:resource_pools.read": "In the menu, Resources and Pools also needs Resources › View.",
            "system:metrics.read": "In the menu, Dashboards also needs Dashboards › View.",
            "system:dashboards.read": "In the menu, Dashboards also needs Metrics › View.",
            "system:users.read": "In the menu, Users also needs Interface › Admin · see in the menu.",
            "system:builds.read": "",
        },
    )
    return


def test_the_admin_menu_permission_says_it_only_opens_the_menu():
    """
    **Feature: role picker menu hints (ADM-06)**
    **Property: ``system:ui.admin.view`` says it shows the Admin menu and that each entry in it also needs its own permission.**
    """
    testbase.assert_equal(
        presentation.menu_hint("system:ui.admin.view"),
        "Shows the Admin menu. Each entry in it also needs its own permission.",
    )
    return


def test_every_menu_entry_that_needs_two_keys_is_covered_for_each_key():
    """
    **Feature: role picker menu hints (ADM-06)**
    **Property: for every entry of the navigation manifest that needs more than one permission (its own and its group's), every one of those
    permissions has a hint, and the hint names the entry (or, for the group's own permission, its menu); a manifest change cannot leave a
    pair unexplained.**
    """
    groups = {group.group_id: group for group in nav_manifest.NAV_GROUPS}
    unexplained: List[str] = []
    checked = 0
    for entry in nav_manifest.NAV_ENTRIES:
        group = groups[entry.group_id]
        needed = list(dict.fromkeys(list(entry.required_permissions) + list(group.required_permissions)))
        if len(needed) < 2:
            continue
        checked += 1
        label = entry.label.replace(nav_manifest.PREVIEW_LABEL_SUFFIX, "")
        for key in needed:
            hint = presentation.menu_hint(key)
            if label not in hint and "Shows the {} menu".format(group.label) not in hint:
                unexplained.append("{} -> {}".format(entry.entry_id, key))

    testbase.assert_equal((unexplained, checked > 10), ([], True))
    return


def test_the_picker_items_carry_the_hint_and_the_role_form_shows_it():
    """
    **Feature: role picker menu hints (ADM-06)**
    **Property: grouping permissions gives every item a ``menu_hint`` (empty when none), and the Create Role page shows the hint under
    Users › Read and nothing under a permission with none.**
    """
    permissions = [
        SimpleNamespace(id="system:users.read", name="system:users.read", description="Read users."),
        SimpleNamespace(id="system:builds.read", name="system:builds.read", description="Read builds."),
    ]
    items: Dict[str, str] = {}
    for group in presentation.group_permissions(permissions):
        for item in group["items"]:
            items[item["permission"].name] = item["menu_hint"]

    cookies = adm.admin_cookies()
    page = adm.get(path="/admin/roles/create", cookies=cookies).text
    hints = re.findall(r'<span class="muted pyc-permissions__hint" data-role="menu-hint">([^<]*)</span>', page)

    testbase.assert_equal(
        (
            items,
            "In the menu, Users also needs Interface › Admin · see in the menu." in hints,
            "Shows the Admin menu. Each entry in it also needs its own permission." in hints,
            len(hints) >= 5, any("Resources and Pools" in hint for hint in hints),
        ),
        (
            {"system:users.read": "In the menu, Users also needs Interface › Admin · see in the menu.", "system:builds.read": ""},
            True, True, True, True,
        ),
    )
    return
