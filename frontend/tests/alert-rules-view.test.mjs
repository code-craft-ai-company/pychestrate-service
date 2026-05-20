/**
 * Unit tests for the pyc-metrics-bundle alert-rules editor view.
 *
 * Covers the pure helpers (URL builder, status-code messages,
 * comparison labels, condition / window formatting, notification-
 * target parsing, response extraction) and the
 * ``<pyc-alert-rules>`` Custom Element's project-select, rule
 * fetch and create action -- driven against a jsdom document and a
 * stubbed ``fetch``.
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
    "pyc-metrics-bundle.js",
)

const dom = new JSDOM(
    "<!doctype html><html><head></head><body></body></html>",
    { url: "https://example.test/metric-alerts" },
)
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.customElements = dom.window.customElements
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.HTMLButtonElement = dom.window.HTMLButtonElement
globalThis.HTMLSelectElement = dom.window.HTMLSelectElement
globalThis.HTMLInputElement = dom.window.HTMLInputElement
globalThis.HTMLTextAreaElement = dom.window.HTMLTextAreaElement
globalThis.HTMLFormElement = dom.window.HTMLFormElement
globalThis.HTMLTableRowElement = dom.window.HTMLTableRowElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycAlertRules,
    ALERT_RULES_ROUTE,
    ALERT_RULE_KIND,
    build_alert_rules_collection_url,
    alert_create_message_for_status,
    comparison_label,
    describe_alert_condition,
    format_alert_window,
    parse_notification_targets,
    extract_alert_rules,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const RULE_ID = "11111111-2222-3333-4444-555555555555"

function _make_rule(overrides) {
    const base = {
        rule_id: RULE_ID,
        project_id: PROJECT_ID,
        name: "checkout error rate",
        kind: "threshold",
        config: {
            metric: "http_5xx",
            comparison: "gt",
            threshold: 0.05,
            window_seconds: 300,
        },
        severity: "warning",
        enabled: true,
        notification_targets: ["ops-pager"],
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

test("build_alert_rules_collection_url targets the project collection", () => {
    assert.equal(
        build_alert_rules_collection_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/metric-alerts",
    )
})

test("ALERT_RULES_ROUTE and ALERT_RULE_KIND are stable constants", () => {
    assert.equal(ALERT_RULES_ROUTE, "/metric-alerts")
    assert.equal(ALERT_RULE_KIND, "threshold")
})

test("alert_create_message_for_status maps HTTP statuses", () => {
    assert.equal(alert_create_message_for_status(201), "Alert rule created.")
    assert.equal(
        alert_create_message_for_status(409),
        "An alert rule with that name already exists.",
    )
    assert.ok(alert_create_message_for_status(422).includes("rejected"))
    assert.ok(alert_create_message_for_status(500).includes("HTTP 500"))
})

test("comparison_label resolves operator labels", () => {
    assert.equal(comparison_label("gt"), "greater than")
    assert.equal(comparison_label("lte"), "less than or equal")
    assert.equal(comparison_label("unknown"), "unknown")
})

test("describe_alert_condition renders metric + comparison + threshold", () => {
    assert.equal(
        describe_alert_condition(_make_rule()),
        "http_5xx greater than 0.05",
    )
    assert.equal(describe_alert_condition({ config: {} }), "—")
})

test("format_alert_window renders day/hour/minute/second units", () => {
    assert.equal(format_alert_window(86400), "1d")
    assert.equal(format_alert_window(3600), "1h")
    assert.equal(format_alert_window(300), "5m")
    assert.equal(format_alert_window(45), "45s")
    assert.equal(format_alert_window(0), "—")
})

test("parse_notification_targets splits and trims a comma list", () => {
    assert.deepEqual(
        parse_notification_targets("ops-pager, slack:#alerts ,, email"),
        ["ops-pager", "slack:#alerts", "email"],
    )
    assert.deepEqual(parse_notification_targets("   "), [])
})

test("extract_alert_rules normalises an items envelope", () => {
    const rules = extract_alert_rules({
        items: [_make_rule(), { not_a_rule: true }],
    })
    assert.equal(rules.length, 1)
    assert.equal(rules[0].rule_id, RULE_ID)
    assert.equal(rules[0].enabled, true)
})

test("extract_alert_rules accepts a bare array", () => {
    const rules = extract_alert_rules([_make_rule({ rule_id: "r2" })])
    assert.equal(rules.length, 1)
    assert.equal(rules[0].rule_id, "r2")
})

test("<pyc-alert-rules> lists rules for the selected project", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Proj" }],
            }),
        ],
        [
            (url) => url === "/api/v1/metrics/catalog",
            () => _json_response(200, { items: [{ name: "http_5xx" }] }),
        ],
        [
            (url) => url.includes("/metric-alerts"),
            () => _json_response(200, { items: [_make_rule()] }),
        ],
    ])
    const el = new PycAlertRules()
    document.body.appendChild(el)
    await el.loadCatalog()
    await el.loadProjects()

    assert.equal(el.listState.projectId, PROJECT_ID)
    assert.equal(el.listState.errored, false)
    assert.equal(el.listState.total, 1)
    const table = el.querySelector('[data-role="alert-rules-table"]')
    assert.ok(table !== null)
    el.remove()
})

test("<pyc-alert-rules> shows an empty state when no rules exist", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Proj" }],
            }),
        ],
        [
            (url) => url === "/api/v1/metrics/catalog",
            () => _json_response(200, { items: [] }),
        ],
        [
            (url) => url.includes("/metric-alerts"),
            () => _json_response(200, { items: [] }),
        ],
    ])
    const el = new PycAlertRules()
    document.body.appendChild(el)
    await el.loadCatalog()
    await el.loadProjects()
    const empty = el.querySelector('[data-role="empty-state"]')
    assert.ok(empty !== null)
    el.remove()
})

test("<pyc-alert-rules> surfaces an error state on a failed fetch", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Proj" }],
            }),
        ],
        [
            (url) => url === "/api/v1/metrics/catalog",
            () => _json_response(200, { items: [] }),
        ],
        [
            (url) => url.includes("/metric-alerts"),
            () => _json_response(503, {}),
        ],
    ])
    const el = new PycAlertRules()
    document.body.appendChild(el)
    await el.loadCatalog()
    await el.loadProjects()
    assert.equal(el.listState.errored, true)
    assert.ok(el.querySelector('[data-role="error-state"]') !== null)
    el.remove()
})

test("<pyc-alert-rules> createAlertRule POSTs a threshold rule", async () => {
    let posted = null
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Proj" }],
            }),
        ],
        [
            (url) => url === "/api/v1/metrics/catalog",
            () => _json_response(200, { items: [{ name: "http_5xx" }] }),
        ],
        [
            (url, options) =>
                url.includes("/metric-alerts") &&
                options !== undefined &&
                options.method === "POST",
            (url, options) => {
                posted = JSON.parse(options.body)
                return _json_response(201, { rule_id: RULE_ID })
            },
        ],
        [
            (url) => url.includes("/metric-alerts"),
            () => _json_response(200, { items: [] }),
        ],
    ])
    const el = new PycAlertRules()
    document.body.appendChild(el)
    await el.loadCatalog()
    await el.loadProjects()

    const outcome = await el.createAlertRule(
        "5xx spike",
        {
            metric: "http_5xx",
            comparison: "gt",
            threshold: 0.05,
            window_seconds: 300,
        },
        "critical",
        true,
        ["ops-pager"],
    )
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 201)
    assert.equal(outcome.ruleId, RULE_ID)
    assert.equal(posted.kind, "threshold")
    assert.equal(posted.config.metric, "http_5xx")
    assert.equal(posted.config.threshold, 0.05)
    assert.equal(posted.severity, "critical")
    assert.deepEqual(posted.notification_targets, ["ops-pager"])
    el.remove()
})

test("<pyc-alert-rules> createAlertRule reports a conflict", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Proj" }],
            }),
        ],
        [
            (url) => url === "/api/v1/metrics/catalog",
            () => _json_response(200, { items: [] }),
        ],
        [
            (url, options) =>
                url.includes("/metric-alerts") &&
                options !== undefined &&
                options.method === "POST",
            () => _json_response(409, {}),
        ],
        [
            (url) => url.includes("/metric-alerts"),
            () => _json_response(200, { items: [] }),
        ],
    ])
    const el = new PycAlertRules()
    document.body.appendChild(el)
    await el.loadCatalog()
    await el.loadProjects()
    const outcome = await el.createAlertRule(
        "dupe",
        { metric: "m", comparison: "gt", threshold: 1, window_seconds: 60 },
        "warning",
        true,
        [],
    )
    assert.equal(outcome.ok, false)
    assert.equal(outcome.status, 409)
    el.remove()
})
