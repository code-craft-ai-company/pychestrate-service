/**
 * Unit tests for the pyc-metrics-bundle SLOs view.
 *
 * Covers the pure helpers (URL builders, ratio / window
 * formatting, burn-rate tone + label classification, status-code
 * messages, definition-config parsing) and the ``<pyc-slos>``
 * Custom Element's project-select, SLO fetch, create action and
 * per-SLO burn-rate-status action -- driven against a jsdom
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
    "pyc-metrics-bundle",
    "index.js",
)

const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/slos",
})
globalThis.HTMLFormElement = dom.window.HTMLFormElement
globalThis.HTMLTableRowElement = dom.window.HTMLTableRowElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycSlos,
    build_slos_collection_url,
    build_slo_detail_url,
    format_ratio,
    format_window,
    slo_status_tone,
    slo_status_label,
    slo_create_message_for_status,
    parse_definition_config,
    extract_slo_projects,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const SLO_ID = "11111111-2222-3333-4444-555555555555"

function _make_slo(overrides) {
    const base = {
        slo_id: SLO_ID,
        project_id: PROJECT_ID,
        name: "checkout availability",
        kind: "availability",
        target: 0.995,
        window_seconds: 604800,
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

test("build_slos_collection_url targets the project SLO collection", () => {
    assert.equal(
        build_slos_collection_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/slos",
    )
})

test("build_slo_detail_url targets a single SLO", () => {
    assert.equal(
        build_slo_detail_url(PROJECT_ID, SLO_ID),
        "/api/v1/projects/" + PROJECT_ID + "/slos/" + SLO_ID,
    )
})

test("format_ratio renders percentages and handles null", () => {
    assert.equal(format_ratio(0.995), "99.5%")
    assert.equal(format_ratio(1), "100.0%")
    assert.equal(format_ratio(null), "—")
    assert.equal(format_ratio(undefined), "—")
})

test("format_window renders day/hour/minute units", () => {
    assert.equal(format_window(604800), "7d")
    assert.equal(format_window(3600), "1h")
    assert.equal(format_window(1800), "30m")
    assert.equal(format_window(0), "—")
})

test("slo_status_tone classifies burn-rate health", () => {
    assert.equal(slo_status_tone(null), "neutral")
    assert.equal(slo_status_tone({ breaching: true }), "error")
    assert.equal(
        slo_status_tone({
            breaching: false,
            error_budget_remaining_ratio: 0.1,
        }),
        "warn",
    )
    assert.equal(
        slo_status_tone({
            breaching: false,
            error_budget_remaining_ratio: 0.8,
        }),
        "ok",
    )
})

test("slo_status_label composes the burn-rate indicator text", () => {
    assert.equal(slo_status_label(null), "Not evaluated")
    assert.equal(slo_status_label({ breaching: true }), "Breaching")
    assert.equal(
        slo_status_label({ breaching: false, achieved_ratio: 0.999 }),
        "99.9% achieved",
    )
})

test("slo_create_message_for_status maps HTTP statuses", () => {
    assert.equal(slo_create_message_for_status(201), "SLO created.")
    assert.ok(slo_create_message_for_status(409).includes("already exists"))
    assert.ok(slo_create_message_for_status(422).includes("rejected"))
    assert.ok(slo_create_message_for_status(403).includes("permission"))
})

test("parse_definition_config accepts objects and rejects arrays", () => {
    assert.deepEqual(parse_definition_config(""), {})
    assert.deepEqual(parse_definition_config('{"metric": "x"}'), {
        metric: "x",
    })
    assert.throws(() => parse_definition_config("[1, 2]"), SyntaxError)
})

test("extract_slo_projects normalises array + envelope bodies", () => {
    const fromArray = extract_slo_projects([
        { project_id: PROJECT_ID, display_name: "Checkout" },
    ])
    assert.equal(fromArray.length, 1)
    assert.equal(fromArray[0].display_name, "Checkout")
    const fromEnvelope = extract_slo_projects({
        items: [{ project_id: PROJECT_ID }],
    })
    assert.equal(fromEnvelope[0].display_name, PROJECT_ID)
})

test("PycSlos fetches and renders the SLO table on project select", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Checkout" }],
            }),
        ],
        [
            (url) => url.startsWith(
                "/api/v1/projects/" + PROJECT_ID + "/slos",
            ),
            () => _json_response(200, {
                items: [_make_slo()],
                meta: { page: 1, per_page: 25, total: 1 },
            }),
        ],
    ])
    const view = new PycSlos()
    document.body.appendChild(view)
    await view.loadProjects()

    assert.equal(view.listState.projectId, PROJECT_ID)
    assert.equal(view.listState.total, 1)
    const table = view.querySelector('[data-role="slos-table"]')
    assert.ok(table !== null)
    const rows = table.shadowRoot.querySelectorAll(".row.pyc-metrics__row")
    assert.equal(rows.length, 1)
    document.body.removeChild(view)
})

test("PycSlos surfaces an error state when the SLO fetch fails", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID }],
            }),
        ],
        [
            (url) => url.includes("/slos"),
            () => _json_response(500, {}),
        ],
    ])
    const view = new PycSlos()
    document.body.appendChild(view)
    await view.loadProjects()

    assert.equal(view.listState.errored, true)
    assert.ok(view.querySelector('[data-role="error-state"]') !== null)
    document.body.removeChild(view)
})

test("PycSlos createSlo POSTs the SLO create request", async () => {
    const calls = _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID }],
            }),
        ],
        [
            (url, options) => url.includes("/slos") &&
                options !== undefined && options.method === "POST",
            () => _json_response(201, _make_slo()),
        ],
        [
            (url) => url.includes("/slos"),
            () => _json_response(200, { items: [], meta: { total: 0 } }),
        ],
    ])
    const view = new PycSlos()
    document.body.appendChild(view)
    await view.loadProjects()

    const outcome = await view.createSlo(
        "checkout availability", "availability", 0.995, 604800, {},
    )
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 201)
    assert.equal(outcome.sloId, SLO_ID)
    const posted = calls.find(
        (c) => c.options !== undefined && c.options.method === "POST",
    )
    const payload = JSON.parse(posted.options.body)
    assert.equal(payload.name, "checkout availability")
    assert.equal(payload.window_seconds, 604800)
    document.body.removeChild(view)
})

test("PycSlos loadStatus reads the embedded burn-rate status", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID }],
            }),
        ],
        [
            (url) => url.endsWith("/slos/" + SLO_ID),
            () => _json_response(200, Object.assign(_make_slo(), {
                status: {
                    slo_id: SLO_ID,
                    achieved_ratio: 0.997,
                    error_budget_remaining_ratio: 0.4,
                    target: 0.995,
                    good_count: 997,
                    total_count: 1000,
                    breaching: false,
                },
            })),
        ],
        [
            (url) => url.includes("/slos"),
            () => _json_response(200, {
                items: [_make_slo()],
                meta: { total: 1 },
            }),
        ],
    ])
    const view = new PycSlos()
    document.body.appendChild(view)
    await view.loadProjects()

    const outcome = await view.loadStatus(SLO_ID)
    assert.equal(outcome.ok, true)
    assert.equal(outcome.sloStatus.breaching, false)
    assert.equal(outcome.sloStatus.achieved_ratio, 0.997)
    document.body.removeChild(view)
})
