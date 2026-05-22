/**
 * Unit tests for the shell-native pyc-admin-bundle views.
 *
 * Covers the pure helpers (route classification, status / state
 * tones, manifest grouping, status-code messages) and the
 * ``<pyc-admin-overview>``, ``<pyc-feature-flags>``,
 * ``<pyc-extension-registry>`` and ``<pyc-system-health>`` Custom
 * Elements -- driven against a jsdom document and a stubbed
 * ``fetch``.
 *
 * Imports the component module directly from the served
 * static tree -- no build step.
 */

import { test } from "node:test"
import assert from "node:assert/strict"
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
    "pyc-admin-bundle",
    "index.js",
)

const dom = new JSDOM(
    "<!doctype html><html><head></head><body></body></html>",
    { url: "https://example.test/admin" },
)
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.customElements = dom.window.customElements
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.HTMLButtonElement = dom.window.HTMLButtonElement
globalThis.HTMLAnchorElement = dom.window.HTMLAnchorElement
globalThis.HTMLTableRowElement = dom.window.HTMLTableRowElement
globalThis.HTMLSpanElement = dom.window.HTMLSpanElement
globalThis.HTMLParagraphElement = dom.window.HTMLParagraphElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycAdminOverview,
    PycFeatureFlags,
    PycExtensionRegistry,
    PycSystemHealth,
    fetch_system_health,
    health_status_tone,
    flag_state_tone,
    next_flag_state,
    toggle_message_for_status,
    group_routes_by_extension,
    mount_state_tone,
    classify_admin_route,
    tag_for_admin_route,
} = bundle

function _install_router(handlers) {
    const calls = []
    globalThis.fetch = async (url, options) => {
        calls.push({ url, options })
        for (const [matches, responder] of handlers) {
            if (matches(url, options) === true) {
                return responder(url, options)
            }
        }
        return { ok: false, status: 500, json: async () => ({}) }
    }
    return calls
}

function _json_ok(body, status) {
    return {
        ok: status === undefined || (status >= 200 && status < 300),
        status: status === undefined ? 200 : status,
        json: async () => body,
    }
}

const FLAGS = [
    {
        flag_key: "beta.search",
        flag_kind: "boolean",
        current_version: 3,
        state: "enabled",
        retired_at: null,
        grace_expires_at: null,
        created_at: "2026-01-01T00:00:00+00:00",
        updated_at: "2026-01-02T00:00:00+00:00",
    },
    {
        flag_key: "alpha.dark-mode",
        flag_kind: "boolean",
        current_version: 1,
        state: "disabled",
        retired_at: null,
        grace_expires_at: null,
        created_at: "2026-01-01T00:00:00+00:00",
        updated_at: "2026-01-01T00:00:00+00:00",
    },
    {
        flag_key: "gone.legacy",
        flag_kind: "boolean",
        current_version: 9,
        state: "retired",
        retired_at: "2026-02-01T00:00:00+00:00",
        grace_expires_at: null,
        created_at: "2025-01-01T00:00:00+00:00",
        updated_at: "2026-02-01T00:00:00+00:00",
    },
]

const HEALTH_DOC = {
    status: "degraded",
    generated_at: "2026-05-20T00:00:00+00:00",
    subsystems: [
        {
            name: "database",
            label: "Database",
            status: "ok",
            detail: "Request-scoped session attached.",
        },
        {
            name: "feature-flags",
            label: "Feature Flags",
            status: "degraded",
            detail: "1 of 2 feature-flag backends unhealthy.",
            backends: [
                { name: "local", status: "ok", reason: "" },
                {
                    name: "remote",
                    status: "degraded",
                    reason: "timeout",
                },
            ],
        },
        {
            name: "extension-routes",
            label: "Extension Routes",
            status: "ok",
            detail: "4 extension route(s) discovered.",
            route_count: 4,
        },
    ],
}

const EXT_LISTING = {
    items: [
        {
            ext_name: "alpha-ext",
            method: "GET",
            path_suffix: "/things",
            full_path: "/api/v1/ext/alpha-ext/things",
            handler_class: "AlphaThingsHandler",
            required_permissions: ["system:alpha.read"],
            required_capabilities: ["cap.read"],
            description: "List alpha things.",
        },
        {
            ext_name: "alpha-ext",
            method: "POST",
            path_suffix: "/things",
            full_path: "/api/v1/ext/alpha-ext/things",
            handler_class: "AlphaThingsHandler",
            required_permissions: ["system:alpha.write"],
            required_capabilities: ["cap.write"],
            description: "Create an alpha thing.",
        },
        {
            ext_name: "beta-ext",
            method: "GET",
            path_suffix: "/widgets",
            full_path: "/api/v1/ext/beta-ext/widgets",
            handler_class: "BetaWidgetsHandler",
            required_permissions: [],
            required_capabilities: [],
            description: "List beta widgets.",
        },
    ],
    total: 3,
    dynamic_mount: "deferred",
}

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

test("health_status_tone maps coarse statuses", () => {
    assert.equal(health_status_tone("ok"), "ok")
    assert.equal(health_status_tone("degraded"), "warn")
    assert.equal(health_status_tone("error"), "error")
    assert.equal(health_status_tone("mystery"), "neutral")
})

test("flag_state_tone maps flag states", () => {
    assert.equal(flag_state_tone("enabled"), "ok")
    assert.equal(flag_state_tone("disabled"), "neutral")
    assert.equal(flag_state_tone("retired"), "error")
    assert.equal(flag_state_tone(null), "neutral")
})

test("next_flag_state flips enabled and defaults to enabled", () => {
    assert.equal(next_flag_state("enabled"), "disabled")
    assert.equal(next_flag_state("disabled"), "enabled")
    assert.equal(next_flag_state("retired"), "enabled")
    assert.equal(next_flag_state(null), "enabled")
})

test("toggle_message_for_status covers documented codes", () => {
    assert.match(toggle_message_for_status(200), /updated/)
    assert.match(toggle_message_for_status(409), /concurrently/)
    assert.match(toggle_message_for_status(403), /permission/)
    assert.match(toggle_message_for_status(500), /HTTP 500/)
})

test("mount_state_tone maps dynamic-mount states", () => {
    assert.equal(mount_state_tone("mounted"), "ok")
    assert.equal(mount_state_tone("deferred"), "warn")
    assert.equal(mount_state_tone("broken"), "error")
})

test("group_routes_by_extension buckets and orders extensions", () => {
    const grouped = group_routes_by_extension(EXT_LISTING.items)
    assert.equal(grouped.length, 2)
    assert.equal(grouped[0].extName, "alpha-ext")
    assert.equal(grouped[0].precedence, 0)
    assert.equal(grouped[0].routeCount, 2)
    assert.deepEqual(grouped[0].capabilities, ["cap.read", "cap.write"])
    assert.equal(grouped[1].extName, "beta-ext")
    assert.equal(grouped[1].precedence, 1)
    assert.equal(grouped[1].routeCount, 1)
})

test("classify_admin_route owns only the four shell-native routes", () => {
    assert.equal(classify_admin_route("/admin"), "overview")
    assert.equal(classify_admin_route("/admin/"), "overview")
    assert.equal(classify_admin_route("/admin/overview"), "overview")
    assert.equal(classify_admin_route("/admin/feature-flags"),
        "feature-flags")
    assert.equal(classify_admin_route("/admin/extensions"), "extensions")
    assert.equal(classify_admin_route("/admin/system-health"),
        "system-health")
    // Legacy Vue admin pages are left untouched.
    assert.equal(classify_admin_route("/admin/users"), "none")
    assert.equal(classify_admin_route("/admin/dashboard"), "none")
    assert.equal(classify_admin_route("/admin/audit-logs"), "none")
})

test("tag_for_admin_route resolves view tags", () => {
    assert.equal(tag_for_admin_route("overview"), "pyc-admin-overview")
    assert.equal(tag_for_admin_route("feature-flags"), "pyc-feature-flags")
    assert.equal(tag_for_admin_route("extensions"),
        "pyc-extension-registry")
    assert.equal(tag_for_admin_route("system-health"), "pyc-system-health")
    assert.equal(tag_for_admin_route("none"), "")
})

// ---------------------------------------------------------------------------
// <pyc-system-health>
// ---------------------------------------------------------------------------

test("fetch_system_health returns the parsed document", async () => {
    _install_router([
        [(u) => String(u).endsWith("/system/health"),
            () => _json_ok(HEALTH_DOC)],
    ])
    const doc = await fetch_system_health()
    assert.notEqual(doc, null)
    assert.equal(doc.status, "degraded")
    assert.equal(doc.subsystems.length, 3)
})

test("PycSystemHealth renders subsystem cards", async () => {
    _install_router([
        [(u) => String(u).endsWith("/system/health"),
            () => _json_ok(HEALTH_DOC)],
    ])
    const el = new PycSystemHealth()
    document.body.appendChild(el)
    await el.refresh()
    assert.equal(el.loading, false)
    assert.equal(el.errored, false)
    const cards = el.querySelectorAll('[data-role="subsystem-card"]')
    assert.equal(cards.length, 3)
    const overall = el.querySelector('[data-role="overall-status"]')
    assert.notEqual(overall, null)
    el.remove()
})

test("PycSystemHealth surfaces an error state", async () => {
    _install_router([
        [(u) => String(u).endsWith("/system/health"),
            () => ({ ok: false, status: 503, json: async () => ({}) })],
    ])
    const el = new PycSystemHealth()
    document.body.appendChild(el)
    await el.refresh()
    assert.equal(el.errored, true)
    assert.notEqual(el.querySelector('[data-role="error-state"]'), null)
    el.remove()
})

// ---------------------------------------------------------------------------
// <pyc-feature-flags>
// ---------------------------------------------------------------------------

test("PycFeatureFlags lists flags ordered by key", async () => {
    _install_router([
        [(u) => String(u).endsWith("/api/v1/flags"),
            () => _json_ok(FLAGS)],
    ])
    const el = new PycFeatureFlags()
    document.body.appendChild(el)
    await el.refresh()
    assert.equal(el.errored, false)
    const rows = el.querySelectorAll("tbody tr")
    assert.equal(rows.length, 3)
    assert.equal(rows[0].getAttribute("data-flag-key"), "alpha.dark-mode")
    el.remove()
})

test("PycFeatureFlags disables the toggle for retired flags", async () => {
    _install_router([
        [(u) => String(u).endsWith("/api/v1/flags"),
            () => _json_ok(FLAGS)],
    ])
    const el = new PycFeatureFlags()
    document.body.appendChild(el)
    await el.refresh()
    const retired = el.querySelector('[data-flag-key="gone.legacy"]')
    const toggle = retired.querySelector('[data-role="toggle"]')
    assert.equal(toggle.disabled, true)
    el.remove()
})

test("PycFeatureFlags toggleFlag PATCHes the target state", async () => {
    let patched = null
    _install_router([
        [(u, o) => o !== undefined && o.method === "PATCH",
            (u, o) => {
                patched = { url: String(u), body: o.body }
                return _json_ok({}, 200)
            }],
        [(u) => String(u).endsWith("/api/v1/flags"),
            () => _json_ok(FLAGS)],
    ])
    const el = new PycFeatureFlags()
    document.body.appendChild(el)
    await el.refresh()
    const outcome = await el.toggleFlag("alpha.dark-mode", "enabled")
    assert.equal(outcome.ok, true)
    assert.match(patched.url, /alpha\.dark-mode/)
    assert.match(patched.body, /enabled/)
    el.remove()
})

// ---------------------------------------------------------------------------
// <pyc-extension-registry>
// ---------------------------------------------------------------------------

test("PycExtensionRegistry rows per extension", async () => {
    _install_router([
        [(u) => String(u).endsWith("/api/v1/ext"),
            () => _json_ok(EXT_LISTING)],
    ])
    const el = new PycExtensionRegistry()
    document.body.appendChild(el)
    await el.refresh()
    assert.equal(el.errored, false)
    const rows = el.querySelectorAll("tbody tr")
    assert.equal(rows.length, 2)
    assert.equal(rows[0].getAttribute("data-ext-name"), "alpha-ext")
    el.remove()
})

test("PycExtensionRegistry shows per-extension routes on demand", async () => {
    _install_router([
        [(u) => String(u).endsWith("/api/v1/ext"),
            () => _json_ok(EXT_LISTING)],
    ])
    const el = new PycExtensionRegistry()
    document.body.appendChild(el)
    await el.refresh()
    const button = el.querySelector('[data-role="show-routes"]')
    button.dispatchEvent(new dom.window.Event("click"))
    const detail = el.querySelector('[data-role="route-detail"]')
    assert.notEqual(detail, null)
    el.remove()
})

test("PycExtensionRegistry surfaces an empty state", async () => {
    _install_router([
        [(u) => String(u).endsWith("/api/v1/ext"),
            () => _json_ok({ items: [], total: 0,
                dynamic_mount: "deferred" })],
    ])
    const el = new PycExtensionRegistry()
    document.body.appendChild(el)
    await el.refresh()
    assert.notEqual(el.querySelector('[data-role="empty-state"]'), null)
    el.remove()
})

// ---------------------------------------------------------------------------
// <pyc-admin-overview>
// ---------------------------------------------------------------------------

test("PycAdminOverview composes the three sections", async () => {
    _install_router([
        [(u) => String(u).endsWith("/system/health"),
            () => _json_ok(HEALTH_DOC)],
        [(u) => String(u).endsWith("/api/v1/flags"),
            () => _json_ok(FLAGS)],
        [(u) => String(u).endsWith("/api/v1/ext"),
            () => _json_ok(EXT_LISTING)],
    ])
    const el = new PycAdminOverview()
    document.body.appendChild(el)
    await el.refresh()
    assert.equal(el.loading, false)
    const health = el.querySelector('[data-role="health-status"]')
    assert.notEqual(health, null)
    assert.equal(health.textContent, "degraded")
    const count = el.querySelector('[data-role="extension-count"]')
    assert.equal(count.textContent, "2")
    const flag_rows = el.querySelectorAll('[data-role="flags-region"] tbody tr')
    assert.equal(flag_rows.length, 3)
    const ext_link = el.querySelector('[data-role="extension-link"]')
    assert.equal(ext_link.getAttribute("href"), "/admin/extensions")
    el.remove()
})

test("PycAdminOverview tolerates a failed health fetch", async () => {
    _install_router([
        [(u) => String(u).endsWith("/system/health"),
            () => ({ ok: false, status: 500, json: async () => ({}) })],
        [(u) => String(u).endsWith("/api/v1/flags"),
            () => _json_ok(FLAGS)],
        [(u) => String(u).endsWith("/api/v1/ext"),
            () => _json_ok(EXT_LISTING)],
    ])
    const el = new PycAdminOverview()
    document.body.appendChild(el)
    await el.refresh()
    assert.notEqual(el.querySelector('[data-role="health-error"]'), null)
    // The other sections still render despite the health failure.
    assert.notEqual(el.querySelector('[data-role="extension-count"]'), null)
    el.remove()
})
