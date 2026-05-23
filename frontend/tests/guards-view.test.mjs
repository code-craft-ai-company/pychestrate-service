/**
 * Unit tests for the pyc-infra-bundle blast-radius-guards view.
 *
 * Covers the pure helpers (URL builders, timestamp / tone
 * formatting, status-code messages, actor-role parsing) and the
 * ``<pyc-guards>`` Custom Element's project-select, guard fetch,
 * attach action, enable/disable toggle and evaluate-preview action
 * -- driven against a jsdom document and a stubbed ``fetch``.
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
    url: "https://example.test/blast-radius-guards",
})
globalThis.HTMLFormElement = dom.window.HTMLFormElement
globalThis.HTMLTableRowElement = dom.window.HTMLTableRowElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycGuards,
    build_guards_collection_url,
    build_guard_item_url,
    build_guards_evaluate_url,
    guard_enabled_tone,
    verdict_tone,
    attach_message_for_status,
    toggle_message_for_status,
    parse_actor_roles,
    extract_guard_projects,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const ENV_ID = "env-staging"
const GUARD_ID = ENV_ID + "::max-destroy-count"

function _make_guard(overrides) {
    const base = {
        guard_id: GUARD_ID,
        project_id: PROJECT_ID,
        environment_id: ENV_ID,
        rule_id: "max-destroy-count",
        enabled: true,
        added_at: "2026-05-20T10:00:00Z",
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

test("build_guards_collection_url adds the environment filter", () => {
    assert.equal(
        build_guards_collection_url(PROJECT_ID, ""),
        "/api/v1/projects/" + PROJECT_ID + "/blast-radius-guards",
    )
    const filtered = build_guards_collection_url(PROJECT_ID, ENV_ID)
    assert.ok(filtered.includes("environment_id=" + ENV_ID))
})

test("guard item + evaluate URL builders", () => {
    assert.equal(
        build_guard_item_url(PROJECT_ID, GUARD_ID),
        "/api/v1/projects/" + PROJECT_ID + "/blast-radius-guards/" +
            encodeURIComponent(GUARD_ID),
    )
    assert.equal(
        build_guards_evaluate_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID +
            "/blast-radius-guards:evaluate",
    )
})

test("guard_enabled_tone + verdict_tone classify states", () => {
    assert.equal(guard_enabled_tone(true), "ok")
    assert.equal(guard_enabled_tone(false), "neutral")
    assert.equal(verdict_tone("allow"), "ok")
    assert.equal(verdict_tone("deny"), "error")
    assert.equal(verdict_tone("skip"), "neutral")
})

test("attach + toggle messages map HTTP statuses", () => {
    assert.equal(attach_message_for_status(201), "Guard attached.")
    assert.ok(attach_message_for_status(409).includes("already attached"))
    assert.equal(toggle_message_for_status(200, true), "Guard enabled.")
    assert.equal(toggle_message_for_status(200, false), "Guard disabled.")
    assert.ok(toggle_message_for_status(404, true).includes("Unknown"))
})

test("parse_actor_roles splits + trims a comma-separated list", () => {
    assert.deepEqual(parse_actor_roles(""), [])
    assert.deepEqual(
        parse_actor_roles("operator, release-manager , "),
        ["operator", "release-manager"],
    )
})

test("extract_guard_projects normalises array + envelope bodies", () => {
    const fromArray = extract_guard_projects([{ project_id: PROJECT_ID }])
    assert.equal(fromArray[0].project_id, PROJECT_ID)
    const fromEnvelope = extract_guard_projects({
        items: [{ project_id: PROJECT_ID, display_name: "Checkout" }],
    })
    assert.equal(fromEnvelope[0].display_name, "Checkout")
})

test("PycGuards fetches and renders the guards table", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID }],
            }),
        ],
        [
            (url) => url.includes("/blast-radius-guards"),
            () => _json_response(200, {
                items: [_make_guard(), _make_guard({
                    guard_id: "env-prod::lock",
                    environment_id: "env-prod",
                    rule_id: "lock",
                })],
                meta: { page: 1, per_page: 25, total: 2 },
            }),
        ],
    ])
    const view = new PycGuards()
    document.body.appendChild(view)
    await view.loadProjects()

    assert.equal(view.listState.total, 2)
    const table = view.querySelector("mj-table.pyc-infra__table")
    const rows = table.shadowRoot.querySelectorAll("tbody tr")
    assert.equal(rows.length, 2)
    document.body.removeChild(view)
})

test("PycGuards attachGuard POSTs the guard create request", async () => {
    const calls = _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID }],
            }),
        ],
        [
            (url, options) => url.includes("/blast-radius-guards") &&
                options !== undefined && options.method === "POST",
            () => _json_response(201, _make_guard()),
        ],
        [
            (url) => url.includes("/blast-radius-guards"),
            () => _json_response(200, { items: [], meta: { total: 0 } }),
        ],
    ])
    const view = new PycGuards()
    document.body.appendChild(view)
    await view.loadProjects()

    const outcome = await view.attachGuard(ENV_ID, "max-destroy-count")
    assert.equal(outcome.ok, true)
    assert.equal(outcome.guardId, GUARD_ID)
    const posted = calls.find(
        (c) => c.options !== undefined && c.options.method === "POST",
    )
    const payload = JSON.parse(posted.options.body)
    assert.equal(payload.environment_id, ENV_ID)
    assert.equal(payload.rule_id, "max-destroy-count")
    document.body.removeChild(view)
})

test("PycGuards toggleGuard PATCHes the enabled flag", async () => {
    const calls = _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID }],
            }),
        ],
        [
            (url, options) => options !== undefined &&
                options.method === "PATCH",
            () => _json_response(200, _make_guard({ enabled: false })),
        ],
        [
            (url) => url.includes("/blast-radius-guards"),
            () => _json_response(200, { items: [], meta: { total: 0 } }),
        ],
    ])
    const view = new PycGuards()
    document.body.appendChild(view)
    await view.loadProjects()

    const outcome = await view.toggleGuard(GUARD_ID, false)
    assert.equal(outcome.ok, true)
    assert.equal(outcome.message, "Guard disabled.")
    const patched = calls.find(
        (c) => c.options !== undefined && c.options.method === "PATCH",
    )
    assert.equal(JSON.parse(patched.options.body).enabled, false)
    document.body.removeChild(view)
})

test("PycGuards evaluateGuards POSTs and parses the verdict trace", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID }],
            }),
        ],
        [
            (url) => url.includes(":evaluate"),
            () => _json_response(200, {
                allowed: false,
                failing_rule_id: "max-destroy-count",
                entries: [
                    {
                        rule_id: "max-destroy-count",
                        verdict: "deny",
                        reason: "would destroy 12 resources",
                    },
                ],
            }),
        ],
        [
            (url) => url.includes("/blast-radius-guards"),
            () => _json_response(200, { items: [], meta: { total: 0 } }),
        ],
    ])
    const view = new PycGuards()
    document.body.appendChild(view)
    await view.loadProjects()

    const outcome = await view.evaluateGuards(
        ENV_ID, "environment.destroy", ["operator"],
    )
    assert.equal(outcome.ok, true)
    assert.equal(outcome.evaluation.allowed, false)
    assert.equal(outcome.evaluation.entries.length, 1)
    assert.equal(outcome.evaluation.entries[0].verdict, "deny")
    document.body.removeChild(view)
})
