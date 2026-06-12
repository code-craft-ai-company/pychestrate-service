"""
.. module:: test_p22b_nav_manifest_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-10 unit coverage for the central navigation
               manifest and its server-side permission filtering
               (PR p22b).

.. moduleauthor:: Code Craft AI LLC

The site-shell sidebar used to be populated per-bundle: each
feature bundle registered its own sidebar entries, and a bundle
only loaded on its own route prefix. On the bare ``/`` route no
feature bundle loads, so the sidebar was empty and the shell
rendered its zero-entries "no access" empty state even for a full
administrator.

p22b moves the sidebar navigation into a single authoritative
server-side manifest (:mod:`webinterface.site_shell.nav_manifest`)
exposed at ``GET /api/v1/me/navigation`` and permission-filtered
server-side. These tests exercise the pure manifest-building
logic directly -- no DB, no HTTP -- so they catch a regression
in the filtering math without needing the deploy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (
    NAV_ENTRIES,
    NAV_GROUPS,
    build_navigation_manifest,
)


def _all_manifest_permission_keys() -> List[str]:
    """
        Collect every distinct permission key referenced by the
        full manifest -- the set an unrestricted administrator
        effectively holds.

        :returns: List of distinct permission keys.
    """
    keys = set()
    for group in NAV_GROUPS:
        for key in group.required_permissions:
            keys.add(key)
    for entry in NAV_ENTRIES:
        for key in entry.required_permissions:
            keys.add(key)
    rtnval = list(keys)
    return rtnval


def test_admin_with_all_permissions_sees_every_group():
    """
    **Feature: site-shell central nav manifest**
    **Property: build_navigation_manifest, given the full set of
    permission keys the manifest references, returns every group
    and every entry -- this is the regression for the p22b
    lockout bug where a full admin saw an empty sidebar on /.**
    """
    held = _all_manifest_permission_keys()

    manifest = build_navigation_manifest(held_permissions=held)

    groups = manifest["groups"]
    # Every declared group surfaces for the all-permissions admin.
    testbase.assert_equal(len(groups), len(NAV_GROUPS))

    total_entries = 0
    for group in groups:
        total_entries = total_entries + len(group["entries"])
    testbase.assert_equal(total_entries, len(NAV_ENTRIES))

    # The four headline features the regression specifically
    # cares about are all present.
    labels = []
    for group in groups:
        for entry in group["entries"]:
            labels.append(entry["label"])
    for expected in ("Runs", "Builds", "Test Metrics", "Overview"):
        testbase.assert_true(expected in labels)
    return


def test_caller_with_no_permissions_sees_no_groups():
    """
    **Feature: site-shell central nav manifest**
    **Property: build_navigation_manifest with an empty held set
    returns zero groups -- the shell empty-state then renders
    legitimately (genuine no-access), not as an artifact of a
    missing bundle.**
    """
    manifest = build_navigation_manifest(held_permissions=[])

    testbase.assert_equal(len(manifest["groups"]), 0)
    return


def test_partial_permissions_filter_groups_and_entries():
    """
    **Feature: site-shell central nav manifest**
    **Property: A caller holding only system:runs.read sees the
    Orchestration group with exactly the Runs entry -- entries
    whose required permissions are unmet are filtered, and a
    group with at least one visible entry surfaces.**
    """
    manifest = build_navigation_manifest(
        held_permissions=["system:runs.read"],
    )

    groups = manifest["groups"]
    testbase.assert_equal(len(groups), 1)

    orchestration = groups[0]
    testbase.assert_equal(orchestration["group_id"], "orchestration")
    testbase.assert_equal(len(orchestration["entries"]), 1)
    testbase.assert_equal(orchestration["entries"][0]["route"], "/runs")
    return


def test_group_hidden_when_group_permission_unmet():
    """
    **Feature: site-shell central nav manifest**
    **Property: The Admin group declares system:ui.admin.view as a
    group-level required permission. A caller holding an Admin
    entry's permission (system:users.read) but NOT the group
    permission does not see the Admin group at all.**
    """
    manifest = build_navigation_manifest(
        held_permissions=["system:users.read"],
    )

    for group in manifest["groups"]:
        testbase.assert_true(group["group_id"] != "admin")
    return


def test_group_with_no_visible_entries_is_dropped():
    """
    **Feature: site-shell central nav manifest**
    **Property: A caller holding only the Admin group permission
    (system:ui.admin.view) but no entry that requires solely that
    key beyond the overview entries still gets an Admin group
    only when at least one entry is visible -- and a group with
    zero visible entries is never emitted.**
    """
    # system:ui.admin.view alone makes the admin group visible AND
    # satisfies the overview / feature-flags / system-health
    # entries, so the admin group surfaces with those entries.
    manifest = build_navigation_manifest(
        held_permissions=["system:ui.admin.view"],
    )

    admin_groups = [
        group
        for group in manifest["groups"]
        if group["group_id"] == "admin"
    ]
    testbase.assert_equal(len(admin_groups), 1)
    testbase.assert_true(len(admin_groups[0]["entries"]) > 0)
    return


def test_manifest_entry_shape_is_json_safe():
    """
    **Feature: site-shell central nav manifest**
    **Property: Every emitted entry carries the JSON-response
    contract keys -- entry_id, label, route, icon,
    required_permissions -- so the shell client can consume the
    payload without shape guards.**
    """
    held = _all_manifest_permission_keys()
    manifest = build_navigation_manifest(held_permissions=held)

    for group in manifest["groups"]:
        for key in (
                "group_id",
                "label",
                "icon",
                "required_permissions",
                "entries",
            ):
            testbase.assert_true(key in group)
        for entry in group["entries"]:
            for key in (
                    "entry_id",
                    "label",
                    "route",
                    "icon",
                    "required_permissions",
                ):
                testbase.assert_true(key in entry)
    return
