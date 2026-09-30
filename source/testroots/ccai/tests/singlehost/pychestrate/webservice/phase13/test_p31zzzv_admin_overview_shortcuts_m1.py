"""
.. module:: test_p31zzzv_admin_overview_shortcuts_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The administration overview is the one admin landing page (XC-18).

.. moduleauthor:: Code Craft AI LLC

``/admin`` showed system health, the extension registry and the feature flags,
and nothing about the administration areas themselves; the server-rendered
"Dashboard" at ``/admin/dashboard`` was the page with a way into users, roles,
variables, secrets, sessions and audit logs. That page now redirects to
``/admin`` (``phase10.test_p31zzzv_one_admin_landing_m1``), and the overview
carries what it had: a "People & access" tile (with how many users there are)
and a "Configuration" tile, each link described in a line and shown only to a
viewer who may use it. The overview is opened in a browser against stubbed API
answers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import GROUP_ADMIN, NAV_ENTRIES

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
PHONE: Dict[str, Any] = {"viewport": {"width": 400, "height": 800}}

BUNDLES = ["pyc-site-shell", "pyc-admin-bundle"]

HEALTH = {"status": "ok", "generated_at": "2026-09-29T19:49:03+00:00", "subsystems": []}

#: What the old dashboard offered, by address.
SHORTCUT_ROUTES = ("/admin/users", "/admin/roles", "/admin/sessions", "/admin/audit-logs", "/admin/variables", "/admin/secrets")

ADMIN_PERMISSIONS = [
    "system:ui.admin.view", "system:users.read", "system:rbac.read", "system:auth.read", "system:audit.read", "system:secrets.read",
]


def _open_overview(browser: Browser, *, permissions: Any, total: Optional[int] = 12, user_reads: Optional[List[str]] = None, **context_options: Any) -> Any:
    def users(query: Dict[str, Any]) -> Dict[str, Any]:
        if user_reads is not None:
            user_reads.append("read")
        return {"items": [], "meta": {"page": 1, "per_page": 1, "total": total}} if total is not None else {"items": []}

    stubs: Dict[str, Any] = {
        "/api/v1/system/health": HEALTH,
        "/api/v1/flags": [],
        "/api/v1/ext": {"items": []},
        "/api/v1/identity/users": users,
        "/api/v1/me/permissions": {"permissions": permissions} if isinstance(permissions, list) else permissions,
    }
    page = open_shell_page(browser, path="/admin", bundle_names=BUNDLES, api_stubs=stubs, **context_options)
    page.wait_for_selector("pyc-admin-overview")
    page.wait_for_selector('[data-role="health-status"], [data-role="health-error"]')
    page.wait_for_timeout(500)
    return page


def _shortcuts(page: Any) -> Dict[str, List[str]]:
    """The links each tile offers, as ``"label -> href"``."""
    return page.evaluate(
        """() => {
            const found = {};
            for (const role of ["people-tile", "configuration-tile"]) {
                const tile = document.querySelector('[data-role="' + role + '"]');
                found[role] = tile === null || tile.hidden ? [] : Array.from(tile.querySelectorAll('[data-role="shortcut-link"]')).map((a) => a.textContent + " -> " + a.getAttribute("href"));
            }
            return found;
        }"""
    )


def test_an_administrator_finds_a_way_into_every_admin_area_and_the_user_count(browser: Browser):
    """
    **Feature: one admin landing page (XC-18)**
    **Property: an administrator's overview offers Users, Roles, Sessions and
    Audit Logs under "People & access" (with "12 users") and Variables and
    Secrets under "Configuration", each with a line saying what it opens.**
    """
    page = _open_overview(browser, permissions=ADMIN_PERMISSIONS, **DESKTOP)
    try:
        found = _shortcuts(page)
        count = page.locator('[data-role="user-count"]').inner_text()
        titles = page.locator(".pyc-admin__tile-title").all_text_contents()
        details = page.locator('[data-role="people-tile"] li .pyc-admin__tile-detail').all_inner_texts()
    finally:
        page.context.close()

    testbase.assert_equal(
        (found, count, titles, details[:2]),
        (
            {
                "people-tile": ["Users -> /admin/users", "Roles -> /admin/roles", "Sessions -> /admin/sessions", "Audit Logs -> /admin/audit-logs"],
                "configuration-tile": ["Variables -> /admin/variables", "Secrets (legacy) -> /admin/secrets"],
            },
            "12 users",
            ["System Health", "Extension Registry", "People & access", "Configuration"],
            ["Accounts, their status and their roles.", "What each role may do."],
        ),
    )
    return


def test_a_viewer_is_offered_only_the_links_they_may_use(browser: Browser):
    """
    **Feature: one admin landing page (XC-18)**
    **Property: a viewer who may list users and open the admin pages but holds
    nothing else sees only Users under "People & access" and only Variables
    under "Configuration"; a viewer who may use none of them sees neither
    tile, and the user list is not even requested.**
    """
    reads: List[str] = []
    page = _open_overview(browser, permissions=["system:ui.admin.view", "system:users.read"], user_reads=reads, **DESKTOP)
    try:
        partial = _shortcuts(page)
    finally:
        page.context.close()

    silent_reads: List[str] = []
    page = _open_overview(browser, permissions=[], user_reads=silent_reads, **DESKTOP)
    try:
        none = _shortcuts(page)
        tiles_visible = [page.locator('[data-role="' + role + '"]').is_visible() for role in ("people-tile", "configuration-tile")]
    finally:
        page.context.close()

    testbase.assert_equal(
        (partial, len(reads) > 0, none, tiles_visible, silent_reads),
        (
            {"people-tile": ["Users -> /admin/users"], "configuration-tile": ["Variables -> /admin/variables"]},
            True,
            {"people-tile": [], "configuration-tile": []},
            [False, False],
            [],
        ),
    )
    return


def test_the_links_stay_when_the_permission_list_or_the_count_cannot_be_read(browser: Browser):
    """
    **Feature: one admin landing page (XC-18)**
    **Property: when the viewer's permission list cannot be read every link is
    still offered (the server checks each page anyway), and when the user list
    has no total the tile simply leaves the count out.**
    """
    page = _open_overview(browser, permissions={}, **DESKTOP)
    try:
        unreadable = _shortcuts(page)
    finally:
        page.context.close()

    page = _open_overview(browser, permissions=ADMIN_PERMISSIONS, total=None, **DESKTOP)
    try:
        without_count = (_shortcuts(page)["people-tile"], page.locator('[data-role="user-count"]').count())
    finally:
        page.context.close()

    testbase.assert_equal(
        (sum(len(links) for links in unreadable.values()), without_count),
        (6, (["Users -> /admin/users", "Roles -> /admin/roles", "Sessions -> /admin/sessions", "Audit Logs -> /admin/audit-logs"], 0)),
    )
    return


def test_each_link_matches_the_sidebar_entry_for_the_same_page(browser: Browser):
    """
    **Feature: one admin landing page (XC-18)**
    **Property: for each permission an admin page needs, a viewer who holds
    only that permission is offered exactly the overview links whose sidebar
    entry needs it, under the sidebar's own label. The landing page and the
    sidebar cannot drift apart on a label, an address or a gate.**
    """
    admin_entries = [entry for entry in NAV_ENTRIES if entry.group_id == GROUP_ADMIN and entry.route in SHORTCUT_ROUTES]
    testbase.assert_equal(sorted(entry.route for entry in admin_entries), sorted(SHORTCUT_ROUTES))

    outcomes: Dict[str, Any] = {}
    for permission in sorted({entry.required_permissions[0] for entry in admin_entries}):
        page = _open_overview(browser, permissions=[permission], **DESKTOP)
        try:
            found = _shortcuts(page)
        finally:
            page.context.close()
        offered = sorted(found["people-tile"] + found["configuration-tile"])
        expected = sorted("{} -> {}".format(entry.label, entry.route) for entry in admin_entries if entry.required_permissions == [permission])
        outcomes[permission] = (offered, expected)

    mismatched = {permission: pair for permission, pair in outcomes.items() if pair[0] != pair[1]}
    testbase.assert_equal(mismatched, {})
    return


def test_the_tiles_sit_in_one_grid_without_overlap_or_sideways_scrolling(browser: Browser):
    """
    **Feature: one admin landing page (XC-18)**
    **Property: on a desktop and on a phone the four tiles do not overlap, a
    link is never on top of its description, and the page does not scroll
    sideways.**
    """
    results: Dict[str, Any] = {}
    for name, size in (("desktop", DESKTOP), ("phone", PHONE)):
        page = _open_overview(browser, permissions=ADMIN_PERMISSIONS, **size)
        try:
            results[name] = page.evaluate(
                """() => {
                    const tiles = Array.from(document.querySelectorAll('.pyc-admin__tile')).filter((t) => !t.hidden).map((t) => t.getBoundingClientRect());
                    let overlap = false;
                    for (let i = 0; i < tiles.length; i++) {
                        for (let j = i + 1; j < tiles.length; j++) {
                            const a = tiles[i], b = tiles[j];
                            if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) { overlap = true; }
                        }
                    }
                    let stacked = true;
                    for (const item of document.querySelectorAll('.pyc-admin__tile-links li')) {
                        const link = item.querySelector('a').getBoundingClientRect();
                        const detail = item.querySelector('.pyc-admin__tile-detail').getBoundingClientRect();
                        if (detail.top < link.bottom - 1) { stacked = false; }
                    }
                    return { tiles: tiles.length, overlap, stacked, sideways: document.documentElement.scrollWidth > window.innerWidth };
                }"""
            )
        finally:
            page.context.close()

    testbase.assert_equal(
        results,
        {
            "desktop": {"tiles": 4, "overlap": False, "stacked": True, "sideways": False},
            "phone": {"tiles": 4, "overlap": False, "stacked": True, "sideways": False},
        },
    )
    return
