/**
 * Unit tests for the pyc-builds-bundle builds list view.
 *
 * Covers the pure helpers and the ``<pyc-builds-list>`` Custom
 * Element's project-select, builds fetch, pagination, and the
 * trigger-build action -- driven against a jsdom document and a
 * stubbed ``fetch``.
 *
 * Imports the component module directly from the served
 * static tree -- no build step.
 */

import { test } from "node:test"
import assert from "node:assert/strict"
import * as path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { JSDOM } from "jsdom"
import { setup_jsdom_with_mj } from "./_helpers/jsdom-mj-setup.mjs"

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
    "pyc-builds-bundle",
    "index.js",
)

// jsdom + mj-* registration so the mj-table inside the builds list
// actually instantiates and renders rows into its shadow DOM.
const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/builds",
})
globalThis.HTMLFormElement = dom.window.HTMLFormElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycBuildsList,
    build_builds_query_url,
    build_builds_collection_url,
    build_source_integrations_url,
    trigger_message_for_status,
    parse_runner_inputs,
    build_state_tone,
    is_terminal_build_state,
    short_id,
    has_next_page,
    has_previous_page,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

function _make_build(overrides) {
    const base = {
        run_id: "11111111-2222-3333-4444-555555555555",
        project_id: PROJECT_ID,
        runner_kind: "makefile",
        repro_digest_sha256: "abc123def456abc123def456",
        state: "completed",
        started_at: "2026-05-20T10:00:00Z",
        finished_at: "2026-05-20T10:05:00Z",
    }
    return Object.assign(base, overrides)
}

/**
 * Route-aware fetch stub. ``handlers`` is a list of
 * (predicate, responder) pairs; the first matching predicate wins.
 */
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

function _json_response(status, body) {
    const rtnval = {
        ok: status >= 200 && status < 300,
        status: status,
        json: async () => body,
    }
    return rtnval
}

test("build_builds_query_url includes project, state, pagination", () => {
    const url = build_builds_query_url({
        projectId: PROJECT_ID,
        stateFilter: "running",
        page: 2,
        perPage: 25,
        total: 0,
        loading: false,
        errored: false,
    })
    assert.ok(url.startsWith("/api/v1/projects/" + PROJECT_ID + "/builds?"))
    assert.ok(url.includes("state=running"))
    assert.ok(url.includes("page=2"))
    assert.ok(url.includes("per_page=25"))
})

test("build_builds_collection_url + source_integrations_url shapes", () => {
    assert.equal(
        build_builds_collection_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/builds",
    )
    assert.equal(
        build_source_integrations_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/source-integrations",
    )
})

test("trigger_message_for_status maps known statuses", () => {
    assert.equal(trigger_message_for_status(202), "Build triggered.")
    assert.ok(trigger_message_for_status(422).includes("rejected"))
    assert.ok(trigger_message_for_status(403).includes("permission"))
    assert.ok(trigger_message_for_status(500).includes("500"))
})

test("parse_runner_inputs handles empty, object, and invalid", () => {
    assert.deepEqual(parse_runner_inputs(""), {})
    assert.deepEqual(parse_runner_inputs('{"target": "all"}'), { target: "all" })
    assert.throws(() => parse_runner_inputs("[1,2]"))
    assert.throws(() => parse_runner_inputs("not json"))
})

test("build_state_tone + is_terminal_build_state classify states", () => {
    assert.equal(build_state_tone("completed"), "ok")
    assert.equal(build_state_tone("failed"), "error")
    assert.equal(build_state_tone("cancelled"), "warn")
    assert.equal(build_state_tone("running"), "neutral")
    assert.equal(is_terminal_build_state("completed"), true)
    assert.equal(is_terminal_build_state("pending"), false)
})

test("short_id shortens uuids and digests", () => {
    assert.equal(short_id("11111111-2222-3333"), "11111111")
    assert.equal(short_id("abcdef0123456789abcdef"), "abcdef012345")
    assert.equal(short_id("short"), "short")
})

test("has_next_page / has_previous_page paging math", () => {
    const base = { page: 1, perPage: 25, total: 60 }
    assert.equal(has_next_page(base), true)
    assert.equal(has_previous_page(base), false)
    assert.equal(has_next_page({ page: 3, perPage: 25, total: 60 }), false)
    assert.equal(has_previous_page({ page: 2, perPage: 25, total: 60 }), true)
})

test("builds list fetches projects then builds and renders rows", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url) => url.includes("/source-integrations"),
            () => _json_response(200, { items: [] }),
        ],
        [
            (url) => url.includes("/builds?"),
            () => _json_response(200, {
                items: [_make_build({}), _make_build({
                    run_id: "99999999-8888-7777-6666-555555555555",
                    state: "running",
                })],
                meta: { page: 1, per_page: 25, total: 2 },
            }),
        ],
    ])

    if (customElements.get("pyc-builds-list") === undefined) {
        customElements.define("pyc-builds-list", PycBuildsList)
    }
    const el = new PycBuildsList()
    document.body.appendChild(el)
    await el.loadProjects()

    const table = el.querySelector("mj-table.pyc-builds__table")
    const rows = table.shadowRoot.querySelectorAll("tr.pyc-builds__row")
    assert.equal(rows.length, 2)
    assert.equal(el.listState.total, 2)
    assert.equal(el.listState.projectId, PROJECT_ID)
    const links = table.shadowRoot.querySelectorAll(".pyc-builds__build-link")
    assert.ok(links[0].getAttribute("href").startsWith("/builds/"))
    el.remove()
})

test("builds list surfaces error state on a failed builds fetch", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url) => url.includes("/source-integrations"),
            () => _json_response(200, { items: [] }),
        ],
        [
            (url) => url.includes("/builds?"),
            () => _json_response(500, {}),
        ],
    ])

    const el = new PycBuildsList()
    document.body.appendChild(el)
    await el.loadProjects()

    const error = el.querySelector('[data-role="error-state"]')
    assert.ok(error !== null)
    assert.equal(el.listState.errored, true)
    el.remove()
})

test("trigger-build action POSTs and surfaces a build link", async () => {
    let posted = null
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url) => url.includes("/source-integrations"),
            () => _json_response(200, { items: [] }),
        ],
        [
            (url, options) =>
                url.endsWith("/builds") && options && options.method === "POST",
            (url, options) => {
                posted = JSON.parse(options.body)
                return _json_response(202, _make_build({
                    run_id: "abcdabcd-1234-5678-9abc-def012345678",
                    state: "pending",
                }))
            },
        ],
        [
            (url) => url.includes("/builds?"),
            () => _json_response(200, {
                items: [],
                meta: { page: 1, per_page: 25, total: 0 },
            }),
        ],
    ])

    const el = new PycBuildsList()
    document.body.appendChild(el)
    await el.loadProjects()

    const outcome = await el.triggerBuild("makefile", { target: "all" })
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 202)
    assert.equal(outcome.buildId, "abcdabcd-1234-5678-9abc-def012345678")
    assert.equal(posted.runner_kind, "makefile")
    assert.deepEqual(posted.runner_inputs, { target: "all" })
    el.remove()
})

test("trigger-build with no project selected fails gracefully", async () => {
    _install_router([
        [(url) => url === "/api/v1/projects", () => _json_response(404, {})],
    ])
    const el = new PycBuildsList()
    document.body.appendChild(el)
    await el.loadProjects()

    const outcome = await el.triggerBuild("makefile", {})
    assert.equal(outcome.ok, false)
    assert.ok(outcome.message.includes("Select a project"))
    el.remove()
})
