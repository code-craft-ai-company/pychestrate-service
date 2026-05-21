/**
 * Unit tests for SidebarRegistry.visible() — permission-intersection
 * logic and route-collision handling.
 *
 * Imports the built ESM bundle from the dist directory. The bundle
 * is committed to git so this test runs without re-running the
 * build first; CI/dev should rerun `npm run build` before testing
 * if they edited a .ts source.
 */

import { test } from "node:test"
import assert from "node:assert/strict"
import * as path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const BUNDLE_PATH = path.resolve(
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
    "pyc-site-shell.js",
)

// The bundle defines a Custom Element on import; stub the bits the
// browser supplies so the import does not crash under Node.
globalThis.customElements = {
    define: () => {},
    get: () => undefined,
}
globalThis.HTMLElement = class HTMLElement {}
globalThis.window = { location: { pathname: "/" } }

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const { SidebarRegistry, PermissionSet } = bundle

test("visible() returns entries when caller holds required permissions", () => {
    const registry = new SidebarRegistry()
    registry.registerEntry({
        entryId: "settings",
        label: "Settings",
        route: "/settings",
        requiredPermissions: [],
    })
    const result = registry.visible(new PermissionSet([]))
    assert.equal(result.ungrouped.length, 1)
    assert.equal(result.ungrouped[0].route, "/settings")
})

test("visible() filters entries whose required permissions are absent", () => {
    const registry = new SidebarRegistry()
    registry.registerEntry({
        entryId: "users",
        label: "Users",
        route: "/admin/users",
        requiredPermissions: ["users.read"],
    })
    const without = registry.visible(new PermissionSet([]))
    assert.equal(without.ungrouped.length, 0)
    const withp = registry.visible(new PermissionSet(["users.read"]))
    assert.equal(withp.ungrouped.length, 1)
})

test("visible() hides whole group when group requirements are unmet", () => {
    const registry = new SidebarRegistry()
    registry.registerGroup({
        groupId: "admin",
        label: "Admin",
        requiredPermissions: ["system:ui.admin.view"],
    })
    registry.registerEntry({
        entryId: "users",
        label: "Users",
        route: "/admin/users",
        requiredPermissions: [],
        group: "admin",
    })
    const without = registry.visible(new PermissionSet([]))
    assert.equal(without.groups.length, 0)
    const withp = registry.visible(
        new PermissionSet(["system:ui.admin.view"]),
    )
    assert.equal(withp.groups.length, 1)
    assert.equal(withp.groups[0].entries.length, 1)
})

test("visible() drops duplicate routes (first wins)", () => {
    const registry = new SidebarRegistry()
    registry.registerEntry({
        entryId: "first",
        label: "First",
        route: "/dup",
        requiredPermissions: [],
    })
    registry.registerEntry({
        entryId: "second",
        label: "Second",
        route: "/dup",
        requiredPermissions: [],
    })
    const result = registry.visible(new PermissionSet([]))
    assert.equal(result.ungrouped.length, 1)
    assert.equal(result.ungrouped[0].label, "First")
})

test("visibleEntryCount() reports the total across groups + ungrouped", () => {
    const registry = new SidebarRegistry()
    registry.registerGroup({
        groupId: "admin",
        label: "Admin",
        requiredPermissions: [],
    })
    registry.registerEntry({
        entryId: "a",
        label: "A",
        route: "/a",
        requiredPermissions: [],
        group: "admin",
    })
    registry.registerEntry({
        entryId: "b",
        label: "B",
        route: "/b",
        requiredPermissions: [],
        group: "admin",
    })
    registry.registerEntry({
        entryId: "c",
        label: "C",
        route: "/c",
        requiredPermissions: [],
    })
    const count = registry.visibleEntryCount(new PermissionSet([]))
    assert.equal(count, 3)
})

test("PermissionSet.diff returns sorted added/removed", () => {
    const before = new PermissionSet(["a", "b"])
    const after = new PermissionSet(["b", "c", "d"])
    const diff = before.diff(after)
    assert.deepEqual(diff.added, ["c", "d"])
    assert.deepEqual(diff.removed, ["a"])
})

// Regression (p22a): a feature bundle that registers its sidebar
// groups / entries AFTER the shell's initial render must trigger
// a re-render -- otherwise the shell stays stuck on the
// zero-permissions empty state even though the user holds every
// permission. The registry's onChange notification is the seam
// the shell uses to re-render on late registration.
test("registry onChange fires on registerGroup", () => {
    const registry = new SidebarRegistry()
    let calls = 0
    registry.onChange(() => {
        calls = calls + 1
    })
    registry.registerGroup({
        groupId: "admin",
        label: "Admin",
        requiredPermissions: [],
    })
    assert.equal(calls, 1)
})

test("registry onChange fires on registerEntry", () => {
    const registry = new SidebarRegistry()
    let calls = 0
    registry.onChange(() => {
        calls = calls + 1
    })
    registry.registerEntry({
        entryId: "a",
        label: "A",
        route: "/a",
        requiredPermissions: [],
    })
    assert.equal(calls, 1)
})

test("registry onChange does not fire on a dropped duplicate", () => {
    const registry = new SidebarRegistry()
    registry.registerEntry({
        entryId: "a",
        label: "A",
        route: "/dup",
        requiredPermissions: [],
    })
    let calls = 0
    registry.onChange(() => {
        calls = calls + 1
    })
    // Duplicate route -- dropped, no mutation, no notification.
    registry.registerEntry({
        entryId: "a2",
        label: "A2",
        route: "/dup",
        requiredPermissions: [],
    })
    assert.equal(calls, 0)
})
