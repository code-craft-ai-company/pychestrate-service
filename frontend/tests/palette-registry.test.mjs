/**
 * Unit tests for the PaletteRegistry: provider registration,
 * permission gating, and failure isolation (M2 / PR5).
 *
 * Imports the built ESM bundle from the dist directory, matching
 * the policy used by sidebar-registry.test.mjs.
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

globalThis.customElements = {
    define: () => {},
    get: () => undefined,
}
globalThis.HTMLElement = class HTMLElement {}
globalThis.window = { location: { pathname: "/" } }

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const { PaletteRegistry, PermissionSet } = bundle

test("registerProvider drops malformed descriptors", () => {
    const registry = new PaletteRegistry()
    registry.registerProvider(null)
    registry.registerProvider({})
    registry.registerProvider({ providerId: "no_query", label: "L" })
    assert.equal(registry.size(), 0)
})

test("visibleProviders gates on required permissions", () => {
    const registry = new PaletteRegistry()
    registry.registerProvider({
        providerId: "admin",
        label: "Admin",
        requiredPermissions: ["system:ui.admin.view"],
        query: async () => [],
    })
    registry.registerProvider({
        providerId: "everyone",
        label: "Everyone",
        query: async () => [],
    })

    const empty_visible = registry.visibleProviders(new PermissionSet([]))
    assert.equal(empty_visible.length, 1)
    assert.equal(empty_visible[0].providerId, "everyone")

    const admin_visible = registry.visibleProviders(
        new PermissionSet(["system:ui.admin.view"]),
    )
    assert.equal(admin_visible.length, 2)
})

test("queryAll only invokes providers whose permissions are held", async () => {
    let admin_invoked = false
    let everyone_invoked = false
    const registry = new PaletteRegistry()
    registry.registerProvider({
        providerId: "admin",
        label: "Admin",
        requiredPermissions: ["system:ui.admin.view"],
        query: async () => {
            admin_invoked = true
            return [{ id: "a", label: "A" }]
        },
    })
    registry.registerProvider({
        providerId: "everyone",
        label: "Everyone",
        query: async () => {
            everyone_invoked = true
            return [{ id: "e", label: "E" }]
        },
    })

    const outcomes = await registry.queryAll("foo", new PermissionSet([]))
    assert.equal(admin_invoked, false)
    assert.equal(everyone_invoked, true)
    assert.equal(outcomes.length, 1)
    assert.equal(outcomes[0].providerId, "everyone")
    assert.equal(outcomes[0].results.length, 1)
})

test("queryAll isolates a failing provider from a healthy one", async () => {
    const registry = new PaletteRegistry()
    registry.registerProvider({
        providerId: "broken",
        label: "Broken",
        query: async () => {
            throw new Error("boom")
        },
    })
    registry.registerProvider({
        providerId: "healthy",
        label: "Healthy",
        query: async () => [{ id: "h1", label: "Healthy 1" }],
    })

    const outcomes = await registry.queryAll("q", new PermissionSet([]))
    assert.equal(outcomes.length, 2)
    const broken = outcomes.find((o) => o.providerId === "broken")
    const healthy = outcomes.find((o) => o.providerId === "healthy")
    assert.notEqual(broken.error, null)
    assert.equal(broken.results.length, 0)
    assert.equal(healthy.error, null)
    assert.equal(healthy.results.length, 1)
})

test("queryAll surfaces a timeout as a provider error", async () => {
    const registry = new PaletteRegistry()
    registry.registerProvider({
        providerId: "slow",
        label: "Slow",
        timeoutMs: 25,
        query: () => new Promise((resolve) => {
            setTimeout(() => resolve([{ id: "x", label: "X" }]), 200)
        }),
    })
    const outcomes = await registry.queryAll("q", new PermissionSet([]))
    assert.equal(outcomes.length, 1)
    assert.notEqual(outcomes[0].error, null)
    assert.equal(outcomes[0].results.length, 0)
})

test("registerProvider drops duplicate providerId (first wins)", () => {
    const registry = new PaletteRegistry()
    registry.registerProvider({
        providerId: "p",
        label: "First",
        query: async () => [],
    })
    registry.registerProvider({
        providerId: "p",
        label: "Second",
        query: async () => [],
    })
    const visible = registry.visibleProviders(new PermissionSet([]))
    assert.equal(visible.length, 1)
    assert.equal(visible[0].label, "First")
})
