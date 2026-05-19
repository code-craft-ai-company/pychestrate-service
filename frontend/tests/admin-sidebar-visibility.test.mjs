/**
 * Visibility test for the admin sidebar bundle (PR4 / p17e).
 *
 * Drives the exported ``register_admin_sidebar`` registration
 * against a fresh ``SidebarRegistry`` under two permission sets:
 *
 * 1. Caller lacking ``system:ui.admin.view`` -- the entire Admin
 *    group must be hidden, regardless of per-entry permissions
 *    the caller may otherwise hold (Requirement 2.4 of
 *    ``9-site-shell``).
 *
 * 2. Caller holding ``system:ui.admin.view`` plus a representative
 *    subset of per-entry permissions -- the Admin group is
 *    visible AND each entry's permission gating is respected.
 *
 * Imports the BUILT bundles from ``dist`` (the same policy the
 * companion sidebar-registry test uses) so this test reflects
 * what is actually deployed.
 */

import { test } from "node:test"
import assert from "node:assert/strict"
import * as path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DIST_ROOT = path.resolve(
    HERE,
    "..",
    "..",
    "source",
    "site",
    "automojo",
    "pychestrate",
    "webservice",
    "webinterface",
    "static",
    "javascript",
    "dist",
)
const SHELL_BUNDLE_PATH = path.resolve(DIST_ROOT, "pyc-site-shell.js")
const ADMIN_BUNDLE_PATH = path.resolve(DIST_ROOT, "pyc-admin-bundle.js")

// Browser globals the bundles touch at import time.
globalThis.customElements = {
    define: () => {},
    get: () => undefined,
}
globalThis.HTMLElement = class HTMLElement {}
globalThis.window = { location: { pathname: "/" } }

const shell_bundle = await import(pathToFileURL(SHELL_BUNDLE_PATH).href)
const { SidebarRegistry, PermissionSet } = shell_bundle

// Importing the admin bundle for its side-effect ``_boot`` would
// call ``window.pychestrateShell.sidebar.registerGroup(...)``;
// the bundle handles the missing handle gracefully (microtask
// retry + console.warn). For this test we want the EXPORTED
// ``register_admin_sidebar`` function so we can drive it against
// our own registry.
const admin_bundle = await import(pathToFileURL(ADMIN_BUNDLE_PATH).href)
const { register_admin_sidebar, ADMIN_SIDEBAR_ENTRIES } = admin_bundle

test("admin bundle exports a non-empty entry catalog", () => {
    assert.ok(Array.isArray(ADMIN_SIDEBAR_ENTRIES))
    assert.ok(ADMIN_SIDEBAR_ENTRIES.length > 0)
    for (const entry of ADMIN_SIDEBAR_ENTRIES) {
        assert.equal(typeof entry.route, "string")
        assert.ok(entry.route.startsWith("/admin"))
        assert.equal(entry.group, "admin")
    }
})

test("admin group hidden when caller lacks system:ui.admin.view", () => {
    const registry = new SidebarRegistry()
    register_admin_sidebar(registry)

    // Hand the caller every per-entry permission, but NOT the
    // group-level one. Requirement 2.4: the group hides the whole
    // surface regardless of per-entry rights.
    const wide_perms = new PermissionSet([
        "system:users.read",
        "system:rbac.read",
        "system:secrets.read",
        "system:secrets.admin",
        "system:auth.read",
        "system:audit.read",
    ])
    const visible = registry.visible(wide_perms)
    assert.equal(visible.groups.length, 0)
    assert.equal(visible.ungrouped.length, 0)
    assert.equal(registry.visibleEntryCount(wide_perms), 0)
})

test("admin group visible when caller holds system:ui.admin.view", () => {
    const registry = new SidebarRegistry()
    register_admin_sidebar(registry)

    const admin_perms = new PermissionSet([
        "system:ui.admin.view",
        "system:users.read",
        "system:rbac.read",
        "system:secrets.read",
        "system:secrets.admin",
        "system:auth.read",
        "system:audit.read",
    ])
    const visible = registry.visible(admin_perms)
    assert.equal(visible.groups.length, 1)
    assert.equal(visible.groups[0].group.groupId, "admin")
    // Every entry in the catalog should be visible when the caller
    // holds the union of per-entry permissions.
    assert.equal(visible.groups[0].entries.length, ADMIN_SIDEBAR_ENTRIES.length)
})

test("admin entries respect their individual permission gates", () => {
    const registry = new SidebarRegistry()
    register_admin_sidebar(registry)

    // Caller holds the group permission but only the bare-minimum
    // entries -- Dashboard + Variables (both declare no required
    // permission) should be visible; gated entries should be
    // hidden.
    const minimal_perms = new PermissionSet(["system:ui.admin.view"])
    const visible = registry.visible(minimal_perms)
    assert.equal(visible.groups.length, 1)
    const visible_routes = visible.groups[0].entries.map((e) => e.route)
    assert.ok(visible_routes.includes("/admin/dashboard"))
    assert.ok(visible_routes.includes("/admin/variables"))
    // Gated entries hidden:
    assert.equal(visible_routes.includes("/admin/users"), false)
    assert.equal(visible_routes.includes("/admin/secrets"), false)
    assert.equal(visible_routes.includes("/admin/audit-logs"), false)
})
