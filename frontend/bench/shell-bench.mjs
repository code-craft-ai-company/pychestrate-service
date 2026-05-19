/**
 * Performance benchmark suite for `<pyc-site-shell>` (T3.2).
 *
 * Targets per NFR-1 of 9-site-shell/requirements.md:
 *
 *   - Shell TTI (cold instantiate -> ready): p95 < 400ms
 *   - Sidebar render for 100 entries: p95 < 50ms
 *   - Permission refetch + sidebar diff: p95 < 80ms
 *   - Palette open: p95 < 80ms
 *   - Palette fan-out (5 providers each 10-30ms): p95 < 250ms
 *
 * Bench harness uses ``node:perf_hooks`` directly; tinybench is
 * installed as a fallback option but the rolled-our-own loop here
 * keeps the harness portable and the JSON output minimal.
 *
 * Output: a JSON object on stdout with per-case ``p50`` / ``p95``
 * / ``samples``. Run with ``npm run bench``.
 */

import { performance } from "node:perf_hooks"
import * as path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { JSDOM } from "jsdom"

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

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
    pretendToBeVisual: true,
})
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.customElements = dom.window.customElements
globalThis.CustomEvent = dom.window.CustomEvent
globalThis.Node = dom.window.Node
globalThis.KeyboardEvent = dom.window.KeyboardEvent
// jsdom does not implement performance — node provides it.
if (typeof globalThis.performance === "undefined") {
    globalThis.performance = performance
}
// Stub navigator.sendBeacon to a no-op so the metrics module does
// not try to ship to localhost.
if (globalThis.navigator !== undefined && typeof globalThis.navigator.sendBeacon !== "function") {
    Object.defineProperty(globalThis.navigator, "sendBeacon", {
        value: () => true,
        configurable: true,
    })
}
// Stub fetch with a permissive permission set so refresh() works.
const PERMISSIONS_FIXTURE = ["perm.a", "perm.b", "perm.c", "ui.admin.view"]
globalThis.fetch = async () => {
    return {
        ok: true,
        status: 200,
        async json() {
            return { permissions: PERMISSIONS_FIXTURE }
        },
    }
}

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const { PycSiteShell, SidebarRegistry, PermissionSet, PaletteRegistry, PaletteDialog } = bundle

function percentile(samples, p) {
    if (samples.length === 0) {
        return 0
    }
    const sorted = [...samples].sort((a, b) => a - b)
    const idx = Math.min(
        sorted.length - 1,
        Math.max(0, Math.ceil(samples.length * (p / 100)) - 1),
    )
    return sorted[idx]
}

async function bench(name, target_ms, iterations, factory) {
    const samples = []
    // 10% warmup
    const warmup = Math.max(1, Math.floor(iterations / 10))
    for (let i = 0; i < warmup; i = i + 1) {
        const runner = await factory()
        await runner()
    }
    for (let i = 0; i < iterations; i = i + 1) {
        const runner = await factory()
        const t0 = performance.now()
        await runner()
        const t1 = performance.now()
        samples.push(t1 - t0)
    }
    const p50 = percentile(samples, 50)
    const p95 = percentile(samples, 95)
    const result = {
        name,
        target_p95_ms: target_ms,
        p50_ms: Number(p50.toFixed(3)),
        p95_ms: Number(p95.toFixed(3)),
        samples: samples.length,
        meets_target: p95 < target_ms,
    }
    return result
}

const results = []

// 1. Shell TTI
results.push(
    await bench("shell_tti", 400, 30, () => {
        return async () => {
            const shell = document.createElement("pyc-site-shell")
            document.body.appendChild(shell)
            // Wait for the queueMicrotask boot to land.
            await new Promise((resolve) => setTimeout(resolve, 0))
            shell.remove()
        }
    }),
)

// 2. Sidebar render of 100 entries
results.push(
    await bench("sidebar_render_100", 50, 100, () => {
        const registry = new SidebarRegistry()
        for (let i = 0; i < 100; i = i + 1) {
            registry.registerEntry({
                entryId: "e" + i,
                label: "Entry " + i,
                route: "/r/" + i,
                requiredPermissions: [],
            })
        }
        const perms = new PermissionSet(PERMISSIONS_FIXTURE)
        return async () => {
            registry.visible(perms)
        }
    }),
)

// 3. Permission refetch + diff
results.push(
    await bench("permission_refetch", 80, 60, () => {
        const { PermissionCache } = bundle
        const cache = new PermissionCache("/api/v1/me/permissions")
        return async () => {
            await cache.refresh(true)
        }
    }),
)

// 4. Palette open
results.push(
    await bench("palette_open", 80, 60, () => {
        const registry = new PaletteRegistry()
        const host = {
            getPermissions: () => new PermissionSet(PERMISSIONS_FIXTURE),
            navigate: () => {},
            emit: () => {},
        }
        const dialog = new PaletteDialog(registry, host)
        return async () => {
            dialog.open()
            dialog.close()
        }
    }),
)

// 5. Palette fan-out with 5 providers each 10-30ms
results.push(
    await bench("palette_fanout_5_providers", 250, 30, () => {
        const registry = new PaletteRegistry()
        for (let i = 0; i < 5; i = i + 1) {
            registry.registerProvider({
                providerId: "p" + i,
                label: "Provider " + i,
                requiredPermissions: [],
                query: async () => {
                    const latency = 10 + Math.floor(Math.random() * 20)
                    await new Promise((resolve) => setTimeout(resolve, latency))
                    return [
                        { id: "r" + i, label: "fixture", route: "/x" },
                    ]
                },
            })
        }
        const perms = new PermissionSet(PERMISSIONS_FIXTURE)
        return async () => {
            await registry.queryAll("hello", perms)
        }
    }),
)

const payload = {
    suite: "pyc-site-shell",
    generated_at: new Date().toISOString(),
    cases: results,
}

console.log(JSON.stringify(payload, null, 2))
