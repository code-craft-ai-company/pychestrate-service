/**
 * Unit tests for the pyc-resources-bundle views.
 *
 * Covers the pure helpers and the three Custom Elements --
 * ``<pyc-resource-pools>``, ``<pyc-pool-detail>`` and
 * ``<pyc-resource-detail>`` -- driven against a jsdom document and
 * a stubbed ``fetch``.
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
    "pyc-resources-bundle",
    "index.js",
)

const dom = new JSDOM(
    "<!doctype html><html><head></head><body></body></html>",
    { url: "https://example.test/resource-pools" },
)
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.customElements = dom.window.customElements
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.HTMLButtonElement = dom.window.HTMLButtonElement
globalThis.HTMLSelectElement = dom.window.HTMLSelectElement
globalThis.HTMLInputElement = dom.window.HTMLInputElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycResourcePools,
    PycPoolDetail,
    PycResourceDetail,
    build_resource_pools_url,
    parse_capability_tags,
    short_id,
    pools_has_next_page,
    pools_has_previous_page,
    pool_id_from_path,
    project_id_from_search,
    is_valid_uuid,
    is_active_reservation,
    reservation_tone,
    build_pool_url,
    build_pool_resources_url,
    build_pool_reservations_url,
    build_reservation_url,
    resource_id_from_path,
    health_tone,
    resource_state_tone,
    usage_event_tone,
    build_resource_health_url,
    build_resource_usage_url,
    register_resources_sidebar,
    classify_resources_route,
    tag_for_resources_route,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const POOL_ID = "11111111-2222-3333-4444-555555555555"
const RESOURCE_ID = "99999999-8888-7777-6666-555555555555"
const RESERVATION_ID = "abababab-cdcd-efef-1212-343434343434"

/**
 * Route-aware fetch stub. ``handlers`` is a list of
 * (predicate, responder) pairs; the first matching predicate wins.
 */
function _install_router(handlers) {
    const calls = []
    globalThis.fetch = async (url, options) => {
        calls.push({ url, options })
        for (const [matches, responder] of handlers) {
            if (matches(url) === true) {
                return responder(url)
            }
        }
        return { ok: false, status: 404, json: async () => ({}) }
    }
    return calls
}

function _json_ok(body) {
    return { ok: true, status: 200, json: async () => body }
}

function _make_pool(overrides) {
    const base = {
        pool_id: POOL_ID,
        project_id: PROJECT_ID,
        name: "edge-pool",
        description: "edge devices",
        capability_tags: ["device", "linux"],
        member_count: 3,
        created_at: "2026-05-20T10:00:00Z",
    }
    return Object.assign(base, overrides)
}

function _pool_page(items, total) {
    return {
        items: items,
        meta: { page: 1, per_page: 50, total: total },
    }
}

// ---- pure helpers ----------------------------------------------

test("build_resource_pools_url carries project_id + paging", () => {
    const url = build_resource_pools_url(PROJECT_ID, 2, 25)
    assert.ok(url.startsWith("/api/v1/resource-pools?"))
    assert.ok(url.includes("project_id=" + PROJECT_ID))
    assert.ok(url.includes("page=2"))
    assert.ok(url.includes("per_page=25"))
})

test("parse_capability_tags trims, dedups, drops empties", () => {
    const tags = parse_capability_tags(" device , linux,device , ")
    assert.deepEqual(tags, ["device", "linux"])
    assert.deepEqual(parse_capability_tags(""), [])
})

test("short_id shortens a uuid to its first segment", () => {
    assert.equal(short_id(POOL_ID), "11111111")
    assert.equal(short_id(""), "")
})

test("pools pager helpers respect total and page", () => {
    const state = { page: 1, perPage: 50, total: 120 }
    assert.equal(pools_has_next_page(state), true)
    assert.equal(pools_has_previous_page(state), false)
    assert.equal(pools_has_next_page({ page: 3, perPage: 50, total: 120 }),
        false)
    assert.equal(pools_has_previous_page({ page: 2, perPage: 50 }), true)
})

test("pool_id_from_path extracts the pool segment", () => {
    assert.equal(
        pool_id_from_path("/resource-pools/" + POOL_ID + "?project_id=x"),
        POOL_ID,
    )
    assert.equal(pool_id_from_path("/resource-pools"), "")
    assert.equal(pool_id_from_path("/other"), "")
})

test("resource_id_from_path extracts the nested resource segment",
    () => {
        assert.equal(
            resource_id_from_path(
                "/resource-pools/resources/" + RESOURCE_ID,
            ),
            RESOURCE_ID,
        )
        assert.equal(resource_id_from_path("/resource-pools"), "")
        assert.equal(
            resource_id_from_path("/resources/" + RESOURCE_ID),
            "",
        )
    })

test("project_id_from_search reads the project_id query param", () => {
    assert.equal(
        project_id_from_search("?project_id=" + PROJECT_ID),
        PROJECT_ID,
    )
    assert.equal(project_id_from_search(""), "")
})

test("is_valid_uuid validates canonical uuids", () => {
    assert.equal(is_valid_uuid(POOL_ID), true)
    assert.equal(is_valid_uuid("not-a-uuid"), false)
})

test("reservation helpers classify state", () => {
    assert.equal(is_active_reservation("granted"), true)
    assert.equal(is_active_reservation("pending"), true)
    assert.equal(is_active_reservation("released"), false)
    assert.equal(reservation_tone("granted"), "ok")
    assert.equal(reservation_tone("pending"), "warn")
    assert.equal(reservation_tone("rejected"), "error")
    assert.equal(reservation_tone("released"), "neutral")
})

test("health + resource-state + usage tones classify correctly", () => {
    assert.equal(health_tone("pass"), "ok")
    assert.equal(health_tone("fail"), "error")
    assert.equal(health_tone("unknown"), "neutral")
    assert.equal(resource_state_tone("available"), "ok")
    assert.equal(resource_state_tone("leased"), "warn")
    assert.equal(resource_state_tone("quarantined"), "error")
    assert.equal(usage_event_tone("reservation.granted"), "ok")
    assert.equal(usage_event_tone("health.failed"), "error")
    assert.equal(usage_event_tone("lease.attached"), "neutral")
})

test("url builders compose the resource sub-paths", () => {
    assert.equal(
        build_pool_url(POOL_ID),
        "/api/v1/resource-pools/" + POOL_ID,
    )
    assert.equal(
        build_pool_resources_url(POOL_ID),
        "/api/v1/resource-pools/" + POOL_ID + "/resources",
    )
    assert.equal(
        build_pool_reservations_url(POOL_ID),
        "/api/v1/resource-pools/" + POOL_ID + "/reservations",
    )
    assert.equal(
        build_reservation_url(POOL_ID, RESERVATION_ID),
        "/api/v1/resource-pools/" + POOL_ID + "/reservations/" +
            RESERVATION_ID,
    )
    assert.equal(
        build_resource_health_url(RESOURCE_ID),
        "/api/v1/resources/" + RESOURCE_ID + "/health",
    )
    assert.equal(
        build_resource_usage_url(RESOURCE_ID),
        "/api/v1/resources/" + RESOURCE_ID + "/usage-history",
    )
})

// ---- index routing ---------------------------------------------

test("classify_resources_route classifies shell paths", () => {
    assert.equal(classify_resources_route("/resource-pools"), "pools-list")
    assert.equal(
        classify_resources_route("/resource-pools/" + POOL_ID),
        "pool-detail",
    )
    assert.equal(
        classify_resources_route(
            "/resource-pools/resources/" + RESOURCE_ID,
        ),
        "resource-detail",
    )
    assert.equal(classify_resources_route("/builds"), "none")
    assert.equal(classify_resources_route("/resources/x"), "none")
})

test("tag_for_resources_route maps to element tags", () => {
    assert.equal(
        tag_for_resources_route("pools-list"),
        "pyc-resource-pools",
    )
    assert.equal(tag_for_resources_route("pool-detail"), "pyc-pool-detail")
    assert.equal(
        tag_for_resources_route("resource-detail"),
        "pyc-resource-detail",
    )
    assert.equal(tag_for_resources_route("none"), "")
})

test("register_resources_sidebar registers a Fleet group + entry", () => {
    const groups = []
    const entries = []
    register_resources_sidebar({
        registerGroup: (g) => groups.push(g),
        registerEntry: (e) => entries.push(e),
    })
    assert.equal(groups.length, 1)
    assert.equal(groups[0].groupId, "fleet")
    assert.equal(entries.length, 1)
    assert.equal(entries[0].entryId, "fleet.resources")
    assert.equal(entries[0].route, "/resource-pools")
})

// ---- <pyc-resource-pools> --------------------------------------

test("resource-pools view shows a prompt without a project", () => {
    const el = new PycResourcePools()
    el.connectedCallback()
    assert.equal(el.listState.needsProject, true)
    const prompt = el.querySelector('[data-role="needs-project"]')
    assert.ok(prompt !== null)
})

test("resource-pools view fetches and renders a pools table", async () => {
    _install_router([
        [
            (url) => url.includes("/api/v1/resource-pools?"),
            () => _json_ok(_pool_page([_make_pool({})], 1)),
        ],
    ])
    const el = new PycResourcePools()
    el.connectedCallback()
    const input = el.querySelector('[data-role="project-filter"]')
    input.value = PROJECT_ID
    input.dispatchEvent(new dom.window.Event("change"))
    await el.refresh()
    assert.equal(el.listState.errored, false)
    const rows = el.querySelectorAll(".pyc-resources__row")
    assert.equal(rows.length, 1)
    const tags = el.querySelectorAll(".pyc-resources__tag")
    assert.equal(tags.length, 2)
})

test("resource-pools view surfaces a fetch error", async () => {
    _install_router([
        [
            (url) => url.includes("/api/v1/resource-pools?"),
            () => ({ ok: false, status: 500, json: async () => ({}) }),
        ],
    ])
    const el = new PycResourcePools()
    el.connectedCallback()
    const input = el.querySelector('[data-role="project-filter"]')
    input.value = PROJECT_ID
    input.dispatchEvent(new dom.window.Event("change"))
    await el.refresh()
    assert.equal(el.listState.errored, true)
    assert.ok(el.querySelector('[data-role="error-state"]') !== null)
})

test("resource-pools create form POSTs a create request", async () => {
    let posted = null
    const calls = _install_router([
        [
            (url) => url.includes("/api/v1/resource-pools?"),
            () => _json_ok(_pool_page([], 0)),
        ],
        [
            (url) => url === "/api/v1/resource-pools",
            () => _json_ok(_make_pool({})),
        ],
    ])
    const el = new PycResourcePools()
    el.connectedCallback()
    const input = el.querySelector('[data-role="project-filter"]')
    input.value = PROJECT_ID
    input.dispatchEvent(new dom.window.Event("change"))
    await el.refresh()

    el.querySelector('[data-role="create-name"]').value = "new-pool"
    el.querySelector('[data-role="create-tags"]').value = "device, x"
    const form = el.querySelector('[data-role="create-form"]')
    form.dispatchEvent(new dom.window.Event("submit"))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const post_call = calls.find(
        (c) => c.options !== undefined && c.options.method === "POST",
    )
    assert.ok(post_call !== undefined)
    posted = JSON.parse(post_call.options.body)
    assert.equal(posted.project_id, PROJECT_ID)
    assert.equal(posted.name, "new-pool")
    assert.deepEqual(posted.capability_tags, ["device", "x"])
})

// ---- <pyc-pool-detail> -----------------------------------------

test("pool-detail view errors without a project id", async () => {
    const el = new PycPoolDetail()
    el.setAttribute("pool-id", POOL_ID)
    el.connectedCallback()
    await el.load()
    assert.equal(el.detailState.errored, true)
})

test("pool-detail view loads pool, resources and reservations",
    async () => {
        _install_router([
            [
                (url) => url.endsWith("/resources"),
                () => _json_ok({
                    items: [{
                        membership_id: "m1",
                        pool_id: POOL_ID,
                        resource_id: RESOURCE_ID,
                        added_at: "2026-05-20T11:00:00Z",
                    }],
                    meta: { page: 1, per_page: 50, total: 1 },
                }),
            ],
            [
                (url) => url.endsWith("/reservations"),
                () => _json_ok({
                    items: [{
                        reservation_id: RESERVATION_ID,
                        project_id: PROJECT_ID,
                        resource_id: RESOURCE_ID,
                        mode: "exclusive",
                        state: "granted",
                        requested_at: "2026-05-20T12:00:00Z",
                    }],
                    meta: { page: 1, per_page: 50, total: 1 },
                }),
            ],
            [
                (url) => url.includes("/resource-pools/" + POOL_ID),
                () => _json_ok(_make_pool({})),
            ],
        ])
        const el = new PycPoolDetail()
        el.setAttribute("pool-id", POOL_ID)
        el.setAttribute("project-id", PROJECT_ID)
        el.connectedCallback()
        await el.load()
        assert.equal(el.detailState.errored, false)
        assert.ok(
            el.querySelector('[data-role="resources-section"]') !== null,
        )
        const release = el.querySelector(
            '[data-role="release-reservation"]',
        )
        assert.ok(release !== null)
    })

test("pool-detail reserve form POSTs a reservation request", async () => {
    const calls = _install_router([
        [
            (url) => url.endsWith("/resources"),
            () => _json_ok({ items: [], meta: { page: 1, per_page: 50,
                total: 0 } }),
        ],
        [
            (url) => url.endsWith("/reservations") === true,
            () => _json_ok({ items: [], meta: { page: 1, per_page: 50,
                total: 0 } }),
        ],
        [
            (url) => url.includes("/resource-pools/" + POOL_ID),
            () => _json_ok(_make_pool({})),
        ],
    ])
    const el = new PycPoolDetail()
    el.setAttribute("pool-id", POOL_ID)
    el.setAttribute("project-id", PROJECT_ID)
    el.connectedCallback()
    await el.load()

    const form = el.querySelector('[data-role="reserve-form"]')
    form.dispatchEvent(new dom.window.Event("submit"))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const post_call = calls.find(
        (c) => c.options !== undefined && c.options.method === "POST" &&
            String(c.url).endsWith("/reservations"),
    )
    assert.ok(post_call !== undefined)
    const body = JSON.parse(post_call.options.body)
    assert.equal(body.project_id, PROJECT_ID)
    assert.equal(body.mode, "exclusive")
})

test("pool-detail add-resource form POSTs a member request", async () => {
    const calls = _install_router([
        [
            (url) => url.endsWith("/resources"),
            () => _json_ok({ items: [], meta: { page: 1, per_page: 50,
                total: 0 } }),
        ],
        [
            (url) => url.endsWith("/reservations"),
            () => _json_ok({ items: [], meta: { page: 1, per_page: 50,
                total: 0 } }),
        ],
        [
            (url) => url.includes("/resource-pools/" + POOL_ID),
            () => _json_ok(_make_pool({})),
        ],
    ])
    const el = new PycPoolDetail()
    el.setAttribute("pool-id", POOL_ID)
    el.setAttribute("project-id", PROJECT_ID)
    el.connectedCallback()
    await el.load()

    el.querySelector('[data-role="add-resource-id"]').value = RESOURCE_ID
    const form = el.querySelector('[data-role="add-resource-form"]')
    form.dispatchEvent(new dom.window.Event("submit"))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const post_call = calls.find(
        (c) => c.options !== undefined && c.options.method === "POST" &&
            String(c.url).endsWith("/resources"),
    )
    assert.ok(post_call !== undefined)
    const body = JSON.parse(post_call.options.body)
    assert.equal(body.resource_id, RESOURCE_ID)
})

// ---- <pyc-resource-detail> -------------------------------------

test("resource-detail view renders health and usage timeline",
    async () => {
        _install_router([
            [
                (url) => url.endsWith("/health"),
                () => _json_ok({
                    health_id: "h1",
                    resource_id: RESOURCE_ID,
                    project_id: PROJECT_ID,
                    probe_name: "ssh-ping",
                    last_outcome: "pass",
                    pass_count: 10,
                    fail_count: 1,
                    consecutive_failures: 0,
                }),
            ],
            [
                (url) => url.endsWith("/usage-history"),
                () => _json_ok({
                    items: [{
                        event_id: "e1",
                        source_event_id: "s1",
                        resource_id: RESOURCE_ID,
                        project_id: PROJECT_ID,
                        event_type: "reservation.granted",
                        at_ts: "2026-05-20T12:00:00Z",
                    }],
                    meta: { page: 1, per_page: 200, total: 1 },
                }),
            ],
            [
                (url) => url.includes("/api/v1/resources/" + RESOURCE_ID),
                () => _json_ok({
                    resource_id: RESOURCE_ID,
                    project_id: PROJECT_ID,
                    kind: "device",
                    state: "available",
                    tags: ["linux"],
                }),
            ],
        ])
        const el = new PycResourceDetail()
        el.setAttribute("resource-id", RESOURCE_ID)
        el.connectedCallback()
        await el.load()
        assert.equal(el.detailState.errored, false)
        assert.equal(el.detailState.hasHealth, true)
        const badge = el.querySelector('[data-role="health-badge"]')
        assert.equal(badge.getAttribute("data-tone"), "ok")
        const entries = el.querySelectorAll(
            ".pyc-resources__timeline-entry",
        )
        assert.equal(entries.length, 1)
    })

test("resource-detail view shows an empty health state on 404",
    async () => {
        _install_router([
            [
                (url) => url.endsWith("/health"),
                () => ({ ok: false, status: 404, json: async () => ({}) }),
            ],
            [
                (url) => url.endsWith("/usage-history"),
                () => _json_ok({ items: [], meta: { page: 1,
                    per_page: 200, total: 0 } }),
            ],
            [
                (url) => url.includes("/api/v1/resources/" + RESOURCE_ID),
                () => _json_ok({
                    resource_id: RESOURCE_ID,
                    project_id: PROJECT_ID,
                    kind: "device",
                    state: "leased",
                }),
            ],
        ])
        const el = new PycResourceDetail()
        el.setAttribute("resource-id", RESOURCE_ID)
        el.connectedCallback()
        await el.load()
        assert.equal(el.detailState.errored, false)
        assert.equal(el.detailState.hasHealth, false)
        assert.ok(el.querySelector('[data-role="health-empty"]') !== null)
        assert.ok(el.querySelector('[data-role="usage-empty"]') !== null)
    })

test("resource-detail view errors on an invalid resource id",
    async () => {
        const el = new PycResourceDetail()
        el.setAttribute("resource-id", "not-a-uuid")
        el.connectedCallback()
        await el.load()
        assert.equal(el.detailState.errored, true)
    })
