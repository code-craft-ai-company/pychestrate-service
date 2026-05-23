/**
 * Unit tests for the pyc-infra-bundle environments view.
 *
 * Covers the pure helpers and the ``<pyc-environments>`` Custom
 * Element's project-select, environments fetch, pagination,
 * register-environment action, and the per-environment drift
 * indicator / check-drift action -- driven against a jsdom
 * document and a stubbed ``fetch``.
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
    "pyc-infra-bundle",
    "index.js",
)

const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/environments",
})
globalThis.HTMLFormElement = dom.window.HTMLFormElement
globalThis.HTMLTableRowElement = dom.window.HTMLTableRowElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycEnvironments,
    build_environments_query_url,
    build_environments_collection_url,
    build_drift_status_url,
    build_drift_check_url,
    environment_state_tone,
    drift_status_tone,
    drift_status_label,
    register_message_for_status,
    drift_check_message_for_status,
    parse_environment_attrs,
    has_next_page,
    has_previous_page,
    short_id,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const ENV_ID = "11111111-2222-3333-4444-555555555555"

function _make_env(overrides) {
    const base = {
        environment_id: ENV_ID,
        project_id: PROJECT_ID,
        kind_name: "terraform",
        name: "staging",
        state: "active",
        last_applied_at: "2026-05-20T10:00:00Z",
    }
    return Object.assign(base, overrides)
}

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

test("build_environments_query_url includes project, state, pagination", () => {
    const url = build_environments_query_url({
        projectId: PROJECT_ID,
        stateFilter: "active",
        page: 2,
        perPage: 25,
        total: 0,
        loading: false,
        errored: false,
    })
    assert.ok(
        url.startsWith("/api/v1/projects/" + PROJECT_ID + "/environments?"),
    )
    assert.ok(url.includes("state=active"))
    assert.ok(url.includes("page=2"))
    assert.ok(url.includes("per_page=25"))
})

test("environment + drift URL builders", () => {
    assert.equal(
        build_environments_collection_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/environments",
    )
    assert.equal(
        build_drift_status_url(PROJECT_ID, ENV_ID),
        "/api/v1/projects/" + PROJECT_ID + "/environments/" + ENV_ID +
            "/drift",
    )
    assert.equal(
        build_drift_check_url(PROJECT_ID, ENV_ID),
        "/api/v1/projects/" + PROJECT_ID + "/environments/" + ENV_ID +
            "/drift:check",
    )
})

test("environment_state_tone classifies states", () => {
    assert.equal(environment_state_tone("active"), "ok")
    assert.equal(environment_state_tone("frozen"), "warn")
    assert.equal(environment_state_tone("destroyed"), "error")
    assert.equal(environment_state_tone("archived"), "neutral")
})

test("drift_status_tone + drift_status_label classify drift", () => {
    assert.equal(drift_status_tone(null), "neutral")
    assert.equal(drift_status_label(null), "Not checked")
    assert.equal(
        drift_status_tone({ has_report: false }),
        "neutral",
    )
    const drifted = {
        has_report: true,
        latest_report: { state: "completed", drift_count: 3 },
    }
    assert.equal(drift_status_tone(drifted), "warn")
    assert.equal(drift_status_label(drifted), "3 drifted")
    const clean = {
        has_report: true,
        latest_report: { state: "completed", drift_count: 0 },
    }
    assert.equal(drift_status_tone(clean), "ok")
    assert.equal(drift_status_label(clean), "No drift")
    const failed = {
        has_report: true,
        latest_report: { state: "failed" },
    }
    assert.equal(drift_status_tone(failed), "error")
    assert.equal(drift_status_label(failed), "Check failed")
})

test("register + drift-check status messages map known statuses", () => {
    assert.equal(
        register_message_for_status(201),
        "Environment registered.",
    )
    assert.ok(register_message_for_status(409).includes("already exists"))
    assert.ok(register_message_for_status(403).includes("permission"))
    assert.equal(
        drift_check_message_for_status(202),
        "Drift check queued.",
    )
    assert.ok(drift_check_message_for_status(409).includes("no drift schedule"))
})

test("parse_environment_attrs handles empty, object, and invalid", () => {
    assert.deepEqual(parse_environment_attrs(""), {})
    assert.deepEqual(
        parse_environment_attrs('{"region": "us-east-1"}'),
        { region: "us-east-1" },
    )
    assert.throws(() => parse_environment_attrs("[1,2]"))
    assert.throws(() => parse_environment_attrs("not json"))
})

test("has_next_page / has_previous_page paging math", () => {
    const base = { page: 1, perPage: 25, total: 60 }
    assert.equal(has_next_page(base), true)
    assert.equal(has_previous_page(base), false)
    assert.equal(has_next_page({ page: 3, perPage: 25, total: 60 }), false)
    assert.equal(has_previous_page({ page: 2, perPage: 25, total: 60 }), true)
})

test("short_id shortens uuids and digests", () => {
    assert.equal(short_id("11111111-2222-3333"), "11111111")
    assert.equal(short_id("short"), "short")
})

test("environments view fetches projects then environments and renders rows", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url) => url.includes("/environments?"),
            () => _json_response(200, {
                items: [
                    _make_env({}),
                    _make_env({
                        environment_id:
                            "99999999-8888-7777-6666-555555555555",
                        name: "production",
                        state: "frozen",
                    }),
                ],
                meta: { page: 1, per_page: 25, total: 2 },
            }),
        ],
    ])

    if (customElements.get("pyc-environments") === undefined) {
        customElements.define("pyc-environments", PycEnvironments)
    }
    const el = new PycEnvironments()
    document.body.appendChild(el)
    await el.loadProjects()

    const table = el.querySelector("mj-table.pyc-infra__table")
    const rows = table.shadowRoot.querySelectorAll("tr.pyc-infra__row")
    assert.equal(rows.length, 2)
    assert.equal(el.listState.total, 2)
    assert.equal(el.listState.projectId, PROJECT_ID)
    const indicators = table.shadowRoot.querySelectorAll('[data-role="drift-indicator"]')
    assert.equal(indicators.length, 2)
    assert.equal(indicators[0].textContent, "Not checked")
    el.remove()
})

test("environments view surfaces error state on a failed fetch", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url) => url.includes("/environments?"),
            () => _json_response(500, {}),
        ],
    ])

    const el = new PycEnvironments()
    document.body.appendChild(el)
    await el.loadProjects()

    const error = el.querySelector('[data-role="error-state"]')
    assert.ok(error !== null)
    assert.equal(el.listState.errored, true)
    el.remove()
})

test("register-environment action POSTs the create request", async () => {
    let posted = null
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url, options) =>
                url.endsWith("/environments") && options &&
                options.method === "POST",
            (url, options) => {
                posted = JSON.parse(options.body)
                return _json_response(201, _make_env({
                    environment_id:
                        "abcdabcd-1234-5678-9abc-def012345678",
                }))
            },
        ],
        [
            (url) => url.includes("/environments?"),
            () => _json_response(200, {
                items: [],
                meta: { page: 1, per_page: 25, total: 0 },
            }),
        ],
    ])

    const el = new PycEnvironments()
    document.body.appendChild(el)
    await el.loadProjects()

    const outcome = await el.registerEnvironment(
        "staging",
        "terraform",
        { region: "us-east-1" },
    )
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 201)
    assert.equal(
        outcome.environmentId,
        "abcdabcd-1234-5678-9abc-def012345678",
    )
    assert.equal(posted.name, "staging")
    assert.equal(posted.kind_name, "terraform")
    assert.deepEqual(posted.attrs, { region: "us-east-1" })
    el.remove()
})

test("check-drift action POSTs drift:check then re-reads drift status", async () => {
    let checked = false
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url, options) =>
                url.endsWith("/drift:check") && options &&
                options.method === "POST",
            () => {
                checked = true
                return _json_response(202, {
                    run_id: "dddd0000-1111-2222-3333-444444444444",
                    project_id: PROJECT_ID,
                    environment_id: ENV_ID,
                    checker_name: "terraform",
                    state: "pending",
                    trigger_kind: "manual",
                })
            },
        ],
        [
            (url) => url.endsWith("/drift"),
            () => _json_response(200, {
                environment_id: ENV_ID,
                has_report: true,
                latest_report: {
                    run_id: "dddd0000-1111-2222-3333-444444444444",
                    project_id: PROJECT_ID,
                    environment_id: ENV_ID,
                    checker_name: "terraform",
                    state: "completed",
                    trigger_kind: "manual",
                    drift_count: 2,
                },
            }),
        ],
        [
            (url) => url.includes("/environments?"),
            () => _json_response(200, {
                items: [_make_env({})],
                meta: { page: 1, per_page: 25, total: 1 },
            }),
        ],
    ])

    const el = new PycEnvironments()
    document.body.appendChild(el)
    await el.loadProjects()

    const outcome = await el.checkDrift(ENV_ID)
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 202)
    assert.equal(checked, true)

    await el.loadDriftStatus(ENV_ID)
    const table = el.querySelector("mj-table.pyc-infra__table")
    const indicator = table.shadowRoot.querySelector('[data-role="drift-indicator"]')
    assert.equal(indicator.textContent, "2 drifted")
    assert.equal(indicator.getAttribute("data-tone"), "warn")
    el.remove()
})

test("register with no project selected fails gracefully", async () => {
    _install_router([
        [(url) => url === "/api/v1/projects", () => _json_response(404, {})],
    ])
    const el = new PycEnvironments()
    document.body.appendChild(el)
    await el.loadProjects()

    const outcome = await el.registerEnvironment("staging", "terraform", {})
    assert.equal(outcome.ok, false)
    assert.ok(outcome.message.includes("Select a project"))
    el.remove()
})
