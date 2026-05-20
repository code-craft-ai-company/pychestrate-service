/**
 * Unit tests for the pyc-pods-bundle views.
 *
 * Covers the pure helpers and the four Custom Elements --
 * ``<pyc-pods-list>``, ``<pyc-pod-detail>``, ``<pyc-clients-list>``
 * and ``<pyc-client-detail>`` -- driven against a jsdom document
 * and a stubbed ``fetch``.
 *
 * Imports the built ESM bundle from the dist directory. The bundle
 * is committed to git so the test runs without re-running the
 * build first; rerun ``npm run build`` after editing a .ts source.
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
    "dist",
    "pyc-pods-bundle.js",
)

const dom = new JSDOM(
    "<!doctype html><html><head></head><body></body></html>",
    { url: "https://example.test/pods" },
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
    PycPodsList,
    PycPodDetail,
    PycClientsList,
    PycClientDetail,
    build_pod_definitions_url,
    build_pod_definition_url,
    build_pod_state_url,
    build_pod_registration_url,
    member_count,
    pods_has_next_page,
    pods_has_previous_page,
    pod_id_from_path,
    project_id_from_search,
    is_valid_pod_id,
    is_transient_pod_state,
    pod_state_tone,
    build_clients_query_url,
    build_client_detail_url,
    capability_tags,
    status_tone,
    liveness_tone,
    clients_has_next_page,
    client_id_from_path,
    is_valid_client_id,
    register_pods_sidebar,
    classify_pods_route,
    tag_for_pods_route,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const POD_ID = "11111111-2222-3333-4444-555555555555"
const CLIENT_ID = "99999999-8888-7777-6666-555555555555"

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

function _make_pod(overrides) {
    const base = {
        pod_id: POD_ID,
        project_id: PROJECT_ID,
        pod_name: "edge-pod",
        current_version: 2,
        spec: { members: [{ name: "worker", kind: "runner" }] },
        spec_hash: "deadbeef",
        created_at: "2026-05-20T10:00:00Z",
    }
    return Object.assign(base, overrides)
}

function _make_client(overrides) {
    const base = {
        client_id: CLIENT_ID,
        project_id: PROJECT_ID,
        pod_name: "edge-pod",
        status: "ACTIVE",
        liveness_state: "ALIVE",
        enrolled_at: "2026-05-19T08:00:00Z",
        last_seen: "2026-05-20T11:55:00Z",
        last_agent_version: "1.4.2",
        transport_name: "https",
        degraded_at: null,
        revision_token: "rev-7",
        attributes: { os: "linux", tags: ["gpu", "fast"] },
    }
    return Object.assign(base, overrides)
}

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

test("build_pod_definitions_url encodes the project id", () => {
    const url = build_pod_definitions_url(PROJECT_ID)
    assert.equal(
        url,
        "/api/v1/projects/" + PROJECT_ID + "/pod-definitions",
    )
})

test("build_pod_definition_url appends the pod id", () => {
    const url = build_pod_definition_url(PROJECT_ID, POD_ID)
    assert.ok(url.endsWith("/pod-definitions/" + POD_ID))
})

test("build_pod_state_url targets the state sub-resource", () => {
    const url = build_pod_state_url(PROJECT_ID, POD_ID)
    assert.ok(url.endsWith("/pods/" + POD_ID + "/state"))
})

test("build_pod_registration_url targets the registration sub-resource", () => {
    const url = build_pod_registration_url(PROJECT_ID, POD_ID)
    assert.ok(url.endsWith("/pods/" + POD_ID + "/registration"))
})

test("member_count reads the members array", () => {
    assert.equal(member_count({ members: [1, 2, 3] }), 3)
    assert.equal(member_count({}), 0)
    assert.equal(member_count(null), 0)
})

test("pod_id_from_path extracts the id segment", () => {
    assert.equal(pod_id_from_path("/pods/" + POD_ID), POD_ID)
    assert.equal(pod_id_from_path("/pods/" + POD_ID + "?project_id=x"), POD_ID)
    assert.equal(pod_id_from_path("/pods"), "")
    assert.equal(pod_id_from_path("/clients/x"), "")
})

test("project_id_from_search reads project_id", () => {
    assert.equal(project_id_from_search("?project_id=" + PROJECT_ID), PROJECT_ID)
    assert.equal(project_id_from_search(""), "")
})

test("is_valid_pod_id rejects non-uuids", () => {
    assert.equal(is_valid_pod_id(POD_ID), true)
    assert.equal(is_valid_pod_id("not-a-uuid"), false)
})

test("is_transient_pod_state flags mid-transition states", () => {
    assert.equal(is_transient_pod_state("PROVISIONING"), true)
    assert.equal(is_transient_pod_state("DRAINING"), true)
    assert.equal(is_transient_pod_state("READY"), false)
    assert.equal(is_transient_pod_state("FAILED"), false)
})

test("pod_state_tone classifies states", () => {
    assert.equal(pod_state_tone("READY"), "ok")
    assert.equal(pod_state_tone("IN_USE"), "ok")
    assert.equal(pod_state_tone("FAILED"), "error")
    assert.equal(pod_state_tone("PROVISIONING"), "warn")
    assert.equal(pod_state_tone("DEFINED"), "neutral")
})

test("pods pagination helpers compute page bounds", () => {
    const state = { page: 1, perPage: 25, total: 60 }
    assert.equal(pods_has_next_page(state), true)
    assert.equal(pods_has_previous_page(state), false)
    assert.equal(pods_has_previous_page({ page: 2, perPage: 25, total: 60 }), true)
})

test("build_clients_query_url omits empty filters", () => {
    const empty = build_clients_query_url({
        projectFilter: "",
        statusFilter: "",
        livenessFilter: "",
    })
    assert.equal(empty, "/api/v1/clients")
    const filtered = build_clients_query_url({
        projectFilter: PROJECT_ID,
        statusFilter: "ACTIVE",
        livenessFilter: "",
    })
    assert.ok(filtered.includes("project_id=" + PROJECT_ID))
    assert.ok(filtered.includes("status=ACTIVE"))
    assert.ok(filtered.includes("liveness_state") === false)
})

test("build_client_detail_url encodes the client id", () => {
    assert.ok(build_client_detail_url(CLIENT_ID).endsWith("/clients/" + CLIENT_ID))
})

test("capability_tags flattens attribute values", () => {
    const tags = capability_tags({ os: "linux", tags: ["gpu", "fast"] })
    assert.ok(tags.includes("os:linux"))
    assert.ok(tags.includes("tags:gpu"))
    assert.ok(tags.includes("tags:fast"))
    assert.deepEqual(capability_tags(null), [])
})

test("status_tone and liveness_tone classify states", () => {
    assert.equal(status_tone("ACTIVE"), "ok")
    assert.equal(status_tone("SUSPENDED"), "warn")
    assert.equal(status_tone("REVOKED"), "error")
    assert.equal(liveness_tone("ALIVE"), "ok")
    assert.equal(liveness_tone("DEGRADED"), "warn")
    assert.equal(liveness_tone("LOST"), "error")
})

test("client_id_from_path extracts the id segment", () => {
    assert.equal(client_id_from_path("/clients/" + CLIENT_ID), CLIENT_ID)
    assert.equal(client_id_from_path("/clients"), "")
})

test("is_valid_client_id rejects non-uuids", () => {
    assert.equal(is_valid_client_id(CLIENT_ID), true)
    assert.equal(is_valid_client_id("bad"), false)
})

test("clients pagination helper computes next-page bound", () => {
    assert.equal(
        clients_has_next_page({ page: 1, perPage: 25, total: 30 }),
        true,
    )
    assert.equal(
        clients_has_next_page({ page: 1, perPage: 25, total: 10 }),
        false,
    )
})

// ---------------------------------------------------------------------------
// Sidebar registration + route classification
// ---------------------------------------------------------------------------

test("register_pods_sidebar registers the Fleet group + two entries", () => {
    const groups = []
    const entries = []
    register_pods_sidebar({
        registerGroup: (g) => groups.push(g),
        registerEntry: (e) => entries.push(e),
    })
    assert.equal(groups.length, 1)
    assert.equal(groups[0].groupId, "fleet")
    assert.equal(entries.length, 2)
    const ids = entries.map((e) => e.entryId)
    assert.ok(ids.includes("fleet.pods"))
    assert.ok(ids.includes("fleet.clients"))
})

test("classify_pods_route maps the four routes", () => {
    assert.equal(classify_pods_route("/pods"), "pods-list")
    assert.equal(classify_pods_route("/clients"), "clients-list")
    assert.equal(classify_pods_route("/pods/" + POD_ID), "pod-detail")
    assert.equal(classify_pods_route("/clients/" + CLIENT_ID), "client-detail")
    assert.equal(classify_pods_route("/builds"), "none")
})

test("tag_for_pods_route resolves tags", () => {
    assert.equal(tag_for_pods_route("pods-list"), "pyc-pods-list")
    assert.equal(tag_for_pods_route("pod-detail"), "pyc-pod-detail")
    assert.equal(tag_for_pods_route("clients-list"), "pyc-clients-list")
    assert.equal(tag_for_pods_route("client-detail"), "pyc-client-detail")
    assert.equal(tag_for_pods_route("none"), "")
})

// ---------------------------------------------------------------------------
// <pyc-pods-list>
// ---------------------------------------------------------------------------

test("pods list requires a project before fetching", async () => {
    if (customElements.get("pyc-pods-list") === undefined) {
        customElements.define("pyc-pods-list", PycPodsList)
    }
    let fetched = false
    globalThis.fetch = async () => {
        fetched = true
        return _json_ok([])
    }
    const el = new PycPodsList()
    document.body.appendChild(el)
    await Promise.resolve()
    assert.equal(el.listState.needsProject, true)
    assert.equal(fetched, false)
    el.remove()
})

test("pods list fetches definitions for a project and paginates", async () => {
    if (customElements.get("pyc-pods-list") === undefined) {
        customElements.define("pyc-pods-list", PycPodsList)
    }
    const pods = []
    for (let i = 0; i < 30; i = i + 1) {
        pods.push(_make_pod({ pod_id: POD_ID, pod_name: "pod-" + String(i) }))
    }
    _install_router([
        [(u) => u.includes("/pod-definitions"), () => _json_ok(pods)],
    ])
    const el = new PycPodsList()
    document.body.appendChild(el)
    const input = el.querySelector('[data-role="project-filter"]')
    input.value = PROJECT_ID
    input.dispatchEvent(new dom.window.Event("change"))
    await new Promise((resolve) => setTimeout(resolve, 5))
    assert.equal(el.listState.total, 30)
    assert.equal(el.listState.errored, false)
    const rows = el.querySelectorAll(".pyc-pods-list__row")
    assert.equal(rows.length, 25)
    el.remove()
})

test("pods list renders an error state on a failed fetch", async () => {
    if (customElements.get("pyc-pods-list") === undefined) {
        customElements.define("pyc-pods-list", PycPodsList)
    }
    _install_router([
        [(u) => u.includes("/pod-definitions"),
            () => ({ ok: false, status: 500, json: async () => ({}) })],
    ])
    const el = new PycPodsList()
    el.setAttribute("data-noop", "1")
    document.body.appendChild(el)
    const input = el.querySelector('[data-role="project-filter"]')
    input.value = PROJECT_ID
    input.dispatchEvent(new dom.window.Event("change"))
    await new Promise((resolve) => setTimeout(resolve, 5))
    assert.equal(el.listState.errored, true)
    assert.ok(el.querySelector('[data-role="error-state"]') !== null)
    el.remove()
})

// ---------------------------------------------------------------------------
// <pyc-pod-detail>
// ---------------------------------------------------------------------------

test("pod detail errors when no project id is supplied", async () => {
    if (customElements.get("pyc-pod-detail") === undefined) {
        customElements.define("pyc-pod-detail", PycPodDetail)
    }
    const el = new PycPodDetail()
    el.setAttribute("pod-id", POD_ID)
    document.body.appendChild(el)
    await el.load()
    assert.equal(el.detailState.errored, true)
    el.remove()
})

test("pod detail fetches definition + runtime and renders members", async () => {
    if (customElements.get("pyc-pod-detail") === undefined) {
        customElements.define("pyc-pod-detail", PycPodDetail)
    }
    _install_router([
        [(u) => u.endsWith("/pod-definitions/" + POD_ID),
            () => _json_ok(_make_pod({}))],
        [(u) => u.endsWith("/state"),
            () => _json_ok({
                pod_id: POD_ID,
                state: "READY",
                previous_state: "PROVISIONING",
                last_transition_at: "2026-05-20T10:01:00Z",
                last_transition_event: "provision_completed",
                transition_cursor: 3,
            })],
        [(u) => u.endsWith("/registration"),
            () => _json_ok({
                registration_id: "reg-1",
                pod_id: POD_ID,
                pod_definition_version: 2,
                client_id: CLIENT_ID,
                state: "REGISTERED",
                report_hash: "h1",
                registered_at: "2026-05-20T10:02:00Z",
            })],
        [(u) => u.endsWith("/registrations"), () => _json_ok([])],
        [(u) => u.endsWith("/state/history"), () => _json_ok([])],
    ])
    const el = new PycPodDetail()
    el.setAttribute("pod-id", POD_ID)
    el.setAttribute("project-id", PROJECT_ID)
    document.body.appendChild(el)
    await el.load()
    assert.equal(el.detailState.errored, false)
    assert.equal(el.detailState.transient, false)
    assert.equal(el.detailState.pollStatus, "stopped")
    const members = el.querySelectorAll(".pyc-pod-detail__member-entry")
    assert.equal(members.length, 1)
    const client_link = el.querySelector(".pyc-pod-detail__client-link")
    assert.ok(client_link !== null)
    assert.equal(client_link.getAttribute("href"), "/clients/" + CLIENT_ID)
    el.remove()
})

test("pod detail polls while the pod is in a transient state", async () => {
    if (customElements.get("pyc-pod-detail") === undefined) {
        customElements.define("pyc-pod-detail", PycPodDetail)
    }
    let state_value = "PROVISIONING"
    _install_router([
        [(u) => u.endsWith("/pod-definitions/" + POD_ID),
            () => _json_ok(_make_pod({}))],
        [(u) => u.endsWith("/state"),
            () => _json_ok({
                pod_id: POD_ID,
                state: state_value,
                transition_cursor: 1,
            })],
        [(u) => u.endsWith("/registration"),
            () => ({ ok: false, status: 404, json: async () => ({}) })],
        [(u) => u.endsWith("/registrations"), () => _json_ok([])],
        [(u) => u.endsWith("/state/history"), () => _json_ok([])],
    ])
    const el = new PycPodDetail()
    el.setAttribute("pod-id", POD_ID)
    el.setAttribute("project-id", PROJECT_ID)
    document.body.appendChild(el)
    await el.load()
    assert.equal(el.detailState.transient, true)
    assert.equal(el.detailState.pollStatus, "polling")
    // The pod settles -- a poll cycle should stop the loop.
    state_value = "READY"
    await el.pollOnce()
    assert.equal(el.detailState.transient, false)
    assert.equal(el.detailState.pollStatus, "stopped")
    el.remove()
})

// ---------------------------------------------------------------------------
// <pyc-clients-list>
// ---------------------------------------------------------------------------

test("clients list fetches and renders rows with capability tags", async () => {
    if (customElements.get("pyc-clients-list") === undefined) {
        customElements.define("pyc-clients-list", PycClientsList)
    }
    _install_router([
        [(u) => u.includes("/api/v1/clients"),
            () => _json_ok([_make_client({}), _make_client({
                client_id: "22222222-3333-4444-5555-666666666666",
            })])],
    ])
    const el = new PycClientsList()
    document.body.appendChild(el)
    await el.refresh()
    assert.equal(el.listState.total, 2)
    assert.equal(el.listState.errored, false)
    const rows = el.querySelectorAll(".pyc-clients-list__row")
    assert.equal(rows.length, 2)
    const tags = el.querySelectorAll(".pyc-clients-list__tag")
    assert.ok(tags.length > 0)
    el.remove()
})

test("clients list threads filters into the query url", async () => {
    if (customElements.get("pyc-clients-list") === undefined) {
        customElements.define("pyc-clients-list", PycClientsList)
    }
    const calls = _install_router([
        [(u) => u.includes("/api/v1/clients"), () => _json_ok([])],
    ])
    const el = new PycClientsList()
    document.body.appendChild(el)
    await el.refresh()
    const status_select = el.querySelector('[data-role="status-filter"]')
    status_select.value = "REVOKED"
    status_select.dispatchEvent(new dom.window.Event("change"))
    await new Promise((resolve) => setTimeout(resolve, 5))
    const last = calls[calls.length - 1].url
    assert.ok(last.includes("status=REVOKED"))
    el.remove()
})

test("clients list shows an empty state for zero clients", async () => {
    if (customElements.get("pyc-clients-list") === undefined) {
        customElements.define("pyc-clients-list", PycClientsList)
    }
    _install_router([
        [(u) => u.includes("/api/v1/clients"), () => _json_ok([])],
    ])
    const el = new PycClientsList()
    document.body.appendChild(el)
    await el.refresh()
    assert.ok(el.querySelector('[data-role="empty-state"]') !== null)
    el.remove()
})

// ---------------------------------------------------------------------------
// <pyc-client-detail>
// ---------------------------------------------------------------------------

test("client detail fetches and renders identity + capabilities", async () => {
    if (customElements.get("pyc-client-detail") === undefined) {
        customElements.define("pyc-client-detail", PycClientDetail)
    }
    _install_router([
        [(u) => u.endsWith("/clients/" + CLIENT_ID),
            () => _json_ok(_make_client({}))],
    ])
    const el = new PycClientDetail()
    el.setAttribute("client-id", CLIENT_ID)
    document.body.appendChild(el)
    await el.load()
    assert.equal(el.detailState.errored, false)
    assert.ok(el.querySelector('[data-role="status-badge"]') !== null)
    assert.ok(el.querySelector('[data-role="heartbeat-section"]') !== null)
    const caps = el.querySelectorAll(".pyc-client-detail__tag")
    assert.ok(caps.length > 0)
    el.remove()
})

test("client detail errors on an invalid client id", async () => {
    if (customElements.get("pyc-client-detail") === undefined) {
        customElements.define("pyc-client-detail", PycClientDetail)
    }
    const el = new PycClientDetail()
    el.setAttribute("client-id", "not-a-uuid")
    document.body.appendChild(el)
    await el.load()
    assert.equal(el.detailState.errored, true)
    el.remove()
})

test("client detail errors on a failed fetch", async () => {
    if (customElements.get("pyc-client-detail") === undefined) {
        customElements.define("pyc-client-detail", PycClientDetail)
    }
    _install_router([
        [(u) => u.endsWith("/clients/" + CLIENT_ID),
            () => ({ ok: false, status: 500, json: async () => ({}) })],
    ])
    const el = new PycClientDetail()
    el.setAttribute("client-id", CLIENT_ID)
    document.body.appendChild(el)
    await el.load()
    assert.equal(el.detailState.errored, true)
    el.remove()
})
