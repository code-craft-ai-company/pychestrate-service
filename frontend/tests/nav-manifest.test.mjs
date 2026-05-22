/**
 * Unit tests for the central navigation-manifest client
 * (`sidebar/nav-manifest.ts`) -- p22b.
 *
 * Covers `fetch_nav_manifest` (success / non-2xx / network-error /
 * malformed body) and `apply_nav_manifest` (seeding the
 * `SidebarRegistry` so the shell sidebar is complete on every
 * route, including the bare `/` route which loads no feature
 * bundle).
 *
 * Imports the component module directly from the served
 * static tree -- no build step.
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
    "pyc-site-shell",
    "index.js",
)

globalThis.customElements = {
    define: () => {},
    get: () => undefined,
}
globalThis.HTMLElement = class HTMLElement {}
globalThis.window = { location: { pathname: "/" } }

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    SidebarRegistry,
    PermissionSet,
    fetch_nav_manifest,
    apply_nav_manifest,
    DEFAULT_NAVIGATION_ENDPOINT,
} = bundle

/**
 * Build a minimal fake `fetch` returning the supplied JSON body
 * and status.
 */
function fake_fetch(status, body) {
    return async () => {
        return {
            ok: status >= 200 && status < 300,
            status,
            json: async () => body,
        }
    }
}

const SAMPLE_MANIFEST = {
    groups: [
        {
            group_id: "orchestration",
            label: "Orchestration",
            icon: null,
            required_permissions: [],
            entries: [
                {
                    entry_id: "orchestration.runs",
                    label: "Runs",
                    route: "/runs",
                    icon: null,
                    required_permissions: ["system:runs.read"],
                },
                {
                    entry_id: "orchestration.builds",
                    label: "Builds",
                    route: "/builds",
                    icon: null,
                    required_permissions: ["system:builds.read"],
                },
            ],
        },
        {
            group_id: "admin",
            label: "Admin",
            icon: null,
            required_permissions: ["system:ui.admin.view"],
            entries: [
                {
                    entry_id: "admin.overview",
                    label: "Overview",
                    route: "/admin",
                    icon: null,
                    required_permissions: ["system:ui.admin.view"],
                },
            ],
        },
    ],
}

test("DEFAULT_NAVIGATION_ENDPOINT points at /api/v1/me/navigation", () => {
    assert.equal(DEFAULT_NAVIGATION_ENDPOINT, "/api/v1/me/navigation")
})

test("fetch_nav_manifest returns the manifest on a 200 response", async () => {
    globalThis.fetch = fake_fetch(200, SAMPLE_MANIFEST)
    const result = await fetch_nav_manifest("/api/v1/me/navigation")
    assert.equal(result.ok, true)
    assert.notEqual(result.manifest, null)
    assert.equal(result.manifest.groups.length, 2)
})

test("fetch_nav_manifest degrades on a 401 response", async () => {
    globalThis.fetch = fake_fetch(401, { detail: "unauthorized" })
    const result = await fetch_nav_manifest("/api/v1/me/navigation")
    assert.equal(result.ok, false)
    assert.equal(result.manifest, null)
})

test("fetch_nav_manifest degrades on a 5xx response", async () => {
    globalThis.fetch = fake_fetch(503, {})
    const result = await fetch_nav_manifest("/api/v1/me/navigation")
    assert.equal(result.ok, false)
    assert.equal(result.manifest, null)
})

test("fetch_nav_manifest degrades on a malformed body", async () => {
    globalThis.fetch = fake_fetch(200, { unexpected: true })
    const result = await fetch_nav_manifest("/api/v1/me/navigation")
    assert.equal(result.ok, false)
    assert.equal(result.manifest, null)
})

test("fetch_nav_manifest degrades on a network error", async () => {
    globalThis.fetch = async () => {
        throw new Error("network down")
    }
    const result = await fetch_nav_manifest("/api/v1/me/navigation")
    assert.equal(result.ok, false)
    assert.equal(result.manifest, null)
})

test("apply_nav_manifest seeds the registry with every group + entry", () => {
    const registry = new SidebarRegistry()
    apply_nav_manifest(registry, SAMPLE_MANIFEST)
    // The server already permission-filtered the manifest, so the
    // registry renders the full sidebar even with zero local
    // permissions.
    const visible = registry.visible(new PermissionSet([]))
    assert.equal(visible.groups.length, 2)
    const labels = visible.groups.map((bucket) => bucket.group.label).sort()
    assert.deepEqual(labels, ["Admin", "Orchestration"])
    const orchestration = visible.groups.find(
        (bucket) => bucket.group.groupId === "orchestration",
    )
    assert.equal(orchestration.entries.length, 2)
    const routes = orchestration.entries.map((entry) => entry.route).sort()
    assert.deepEqual(routes, ["/builds", "/runs"])
})

test("apply_nav_manifest result is independent of caller permissions", () => {
    // Regression for the p22b lockout bug: the sidebar must be the
    // full manifest on every route, including bare `/`, regardless
    // of which feature bundle is loaded. The manifest entries carry
    // empty requiredPermissions because the server filtered them,
    // so even an empty PermissionSet shows the full sidebar.
    const registry = new SidebarRegistry()
    apply_nav_manifest(registry, SAMPLE_MANIFEST)
    assert.equal(registry.visibleEntryCount(new PermissionSet([])), 3)
})

test("apply_nav_manifest tolerates a malformed manifest", () => {
    const registry = new SidebarRegistry()
    apply_nav_manifest(registry, { groups: null })
    assert.equal(registry.visibleEntryCount(new PermissionSet([])), 0)
})

test("apply_nav_manifest skips entries with no route", () => {
    const registry = new SidebarRegistry()
    apply_nav_manifest(registry, {
        groups: [
            {
                group_id: "g1",
                label: "Group One",
                entries: [
                    { entry_id: "bad", label: "Bad" },
                    {
                        entry_id: "good",
                        label: "Good",
                        route: "/good",
                    },
                ],
            },
        ],
    })
    assert.equal(registry.visibleEntryCount(new PermissionSet([])), 1)
})
