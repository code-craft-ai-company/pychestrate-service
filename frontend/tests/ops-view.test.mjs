/**
 * Unit tests for the pyc-ops-bundle views.
 *
 * Covers the pure helpers (URL builders, timestamp / tone / rollout
 * formatting, status-code messages, topic-filter parsing, route
 * classification) and the ``<pyc-webhooks>`` + ``<pyc-release-
 * channels>`` Custom Elements -- driven against a jsdom document
 * and a stubbed ``fetch``.
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
    "pyc-ops-bundle",
    "index.js",
)

const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/webhooks",
})
globalThis.HTMLFormElement = dom.window.HTMLFormElement
globalThis.HTMLTableRowElement = dom.window.HTMLTableRowElement
globalThis.HTMLTableSectionElement = dom.window.HTMLTableSectionElement
globalThis.HTMLSpanElement = dom.window.HTMLSpanElement
globalThis.HTMLParagraphElement = dom.window.HTMLParagraphElement
globalThis.HTMLDListElement = dom.window.HTMLDListElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycWebhooks,
    PycReleaseChannels,
    build_integrations_url,
    build_subscriptions_url,
    build_subscription_test_url,
    build_subscription_deliveries_url,
    delivery_outcome_tone,
    create_message_for_status,
    test_message_for_status,
    parse_topic_filters,
    build_release_channel_url,
    format_rollout,
    release_status_tone,
    publish_message_for_status,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const SUB_ID = "11111111-2222-3333-4444-555555555555"
const CHANNEL_ID = "99999999-8888-7777-6666-555555555555"

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

// --- pure helpers --------------------------------------------------

test("webhook URL builders target the v1 REST surface", () => {
    assert.ok(
        build_integrations_url(PROJECT_ID).startsWith(
            "/api/v1/webhooks/in/integrations?",
        ),
    )
    assert.ok(
        build_integrations_url(PROJECT_ID).includes(
            "project_id=" + PROJECT_ID,
        ),
    )
    assert.ok(
        build_subscriptions_url(PROJECT_ID).startsWith(
            "/api/v1/webhooks/out/subscriptions?",
        ),
    )
    assert.equal(
        build_subscription_test_url(SUB_ID),
        "/api/v1/webhooks/out/subscriptions/" + SUB_ID + "/test",
    )
    assert.equal(
        build_subscription_deliveries_url(SUB_ID),
        "/api/v1/webhooks/out/subscriptions/" + SUB_ID + "/deliveries",
    )
})

test("delivery_outcome_tone classifies delivery outcomes", () => {
    assert.equal(delivery_outcome_tone("delivered"), "ok")
    assert.equal(delivery_outcome_tone("pending"), "warn")
    assert.equal(delivery_outcome_tone("failed"), "error")
    assert.equal(delivery_outcome_tone("unknown"), "neutral")
})

test("webhook status-code messages map HTTP statuses", () => {
    assert.equal(
        create_message_for_status(201, "Integration"),
        "Integration created.",
    )
    assert.ok(
        create_message_for_status(409, "Subscription").includes(
            "already exists",
        ),
    )
    assert.equal(test_message_for_status(202), "Test event queued.")
    assert.ok(test_message_for_status(409).includes("disabled"))
})

test("parse_topic_filters splits + trims a comma-separated list", () => {
    assert.deepEqual(parse_topic_filters(""), [])
    assert.deepEqual(
        parse_topic_filters("entity.release.published, entity.run.done , "),
        ["entity.release.published", "entity.run.done"],
    )
})

test("release-channel helpers format + classify", () => {
    assert.equal(
        build_release_channel_url(CHANNEL_ID),
        "/api/v1/release-channels/" + CHANNEL_ID,
    )
    assert.equal(format_rollout(0.5), "50%")
    assert.equal(format_rollout(1), "100%")
    assert.equal(release_status_tone("active"), "ok")
    assert.equal(release_status_tone("rolling_out"), "warn")
    assert.equal(release_status_tone("rolled_back"), "error")
    assert.ok(publish_message_for_status(201).includes("published"))
    assert.ok(publish_message_for_status(409).includes("already published"))
})

// --- <pyc-webhooks> ------------------------------------------------

test("PycWebhooks defaults to the inbound tab", () => {
    const view = new PycWebhooks()
    document.body.appendChild(view)
    assert.equal(view.activeTab, "inbound")
    assert.ok(view.querySelector('[data-role="inbound-panel"]') !== null)
    document.body.removeChild(view)
})

test("PycWebhooks selectTab switches to the outbound panel", () => {
    const view = new PycWebhooks()
    document.body.appendChild(view)
    view.selectTab("outbound")
    assert.equal(view.activeTab, "outbound")
    assert.ok(view.querySelector('[data-role="outbound-panel"]') !== null)
    document.body.removeChild(view)
})

test("PycWebhooks createIntegration POSTs the integration request", async () => {
    const calls = _install_router([
        [
            (url, options) => url ===
                "/api/v1/webhooks/in/integrations" &&
                options !== undefined && options.method === "POST",
            () => _json_response(201, {
                webhook_id: "wh-1",
                provider: "github",
                hook_name: "push",
            }),
        ],
        [
            (url) => url.includes("/webhooks/in/integrations"),
            () => _json_response(200, { items: [], meta: { total: 0 } }),
        ],
        [
            (url) => url.includes("/webhooks/in/deliveries"),
            () => _json_response(200, { items: [], meta: { total: 0 } }),
        ],
    ])
    const view = new PycWebhooks()
    document.body.appendChild(view)
    const input = view.querySelector('[data-role="project-input"]')
    input.value = PROJECT_ID
    input.dispatchEvent(new dom.window.Event("change"))

    const outcome = await view.createIntegration("github", "push", "secret://x")
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 201)
    const posted = calls.find(
        (c) => c.options !== undefined && c.options.method === "POST",
    )
    const payload = JSON.parse(posted.options.body)
    assert.equal(payload.provider, "github")
    assert.equal(payload.project_id, PROJECT_ID)
    document.body.removeChild(view)
})

test("PycWebhooks refuses to create without a project id", async () => {
    _install_router([])
    const view = new PycWebhooks()
    document.body.appendChild(view)
    const outcome = await view.createSubscription("x", "https://y", [])
    assert.equal(outcome.ok, false)
    assert.ok(outcome.message.includes("project id"))
    document.body.removeChild(view)
})

test("PycWebhooks createSubscription POSTs topic filters", async () => {
    const calls = _install_router([
        [
            (url, options) => url ===
                "/api/v1/webhooks/out/subscriptions" &&
                options !== undefined && options.method === "POST",
            () => _json_response(201, {
                subscription_id: SUB_ID,
                name: "release-notifier",
            }),
        ],
        [
            (url) => url.includes("/webhooks/out/subscriptions"),
            () => _json_response(200, { items: [], meta: { total: 0 } }),
        ],
    ])
    const view = new PycWebhooks()
    document.body.appendChild(view)
    const input = view.querySelector('[data-role="project-input"]')
    input.value = PROJECT_ID
    input.dispatchEvent(new dom.window.Event("change"))

    const outcome = await view.createSubscription(
        "release-notifier", "https://hooks.example/x",
        ["entity.release.published"],
    )
    assert.equal(outcome.ok, true)
    const posted = calls.find(
        (c) => c.options !== undefined && c.options.method === "POST",
    )
    const payload = JSON.parse(posted.options.body)
    assert.deepEqual(payload.topic_filters, ["entity.release.published"])
    document.body.removeChild(view)
})

test("PycWebhooks sendTestEvent POSTs the test endpoint", async () => {
    const calls = _install_router([
        [
            (url) => url.endsWith("/" + SUB_ID + "/test"),
            () => _json_response(202, { status: "queued" }),
        ],
    ])
    const view = new PycWebhooks()
    document.body.appendChild(view)
    const outcome = await view.sendTestEvent(SUB_ID)
    assert.equal(outcome.ok, true)
    assert.equal(outcome.message, "Test event queued.")
    assert.equal(calls[0].options.method, "POST")
    document.body.removeChild(view)
})

test("PycWebhooks loadSubscriptionDeliveries reads the history page", async () => {
    _install_router([
        [
            (url) => url.endsWith("/" + SUB_ID + "/deliveries"),
            () => _json_response(200, {
                items: [
                    {
                        delivery_id: "d-1",
                        subscription_id: SUB_ID,
                        topic: "entity.release.published",
                        outcome: "delivered",
                        response_status: 200,
                    },
                ],
                meta: { total: 1 },
            }),
        ],
    ])
    const view = new PycWebhooks()
    document.body.appendChild(view)
    const deliveries = await view.loadSubscriptionDeliveries(SUB_ID)
    assert.equal(deliveries.length, 1)
    assert.equal(deliveries[0].outcome, "delivered")
    document.body.removeChild(view)
})

// --- <pyc-release-channels> ----------------------------------------

test("PycReleaseChannels fetches and renders the channels table", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/release-channels",
            () => _json_response(200, {
                items: [
                    {
                        channel_id: CHANNEL_ID,
                        release_id: CHANNEL_ID,
                        component: "agent-runtime",
                        version: "1.4.0",
                        channel: "stable",
                        artifact_uri: "oci://r/x:1.4.0",
                        artifact_sha256: "a".repeat(64),
                        status: "active",
                        rollout_fraction: 1,
                    },
                ],
                meta: { page: 1, per_page: 25, total: 1 },
            }),
        ],
    ])
    const view = new PycReleaseChannels()
    document.body.appendChild(view)
    await view.refresh()
    assert.equal(view.errored, false)
    const table = view.querySelector("mj-table.pyc-ops__table")
    const rows = table.shadowRoot.querySelectorAll("tbody tr")
    assert.equal(rows.length, 1)
    document.body.removeChild(view)
})

test("PycReleaseChannels surfaces an error state on fetch failure", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/release-channels",
            () => _json_response(503, {}),
        ],
    ])
    const view = new PycReleaseChannels()
    document.body.appendChild(view)
    await view.refresh()
    assert.equal(view.errored, true)
    assert.ok(view.querySelector('[data-role="error-state"]') !== null)
    document.body.removeChild(view)
})

test("PycReleaseChannels publishRelease POSTs the publish request", async () => {
    const calls = _install_router([
        [
            (url, options) => url === "/api/v1/release-channels" &&
                options !== undefined && options.method === "POST",
            () => _json_response(201, {
                channel_id: CHANNEL_ID,
                release_id: CHANNEL_ID,
                component: "agent-runtime",
                version: "1.4.0",
                channel: "canary",
                artifact_uri: "oci://r/x:1.4.0",
                artifact_sha256: "a".repeat(64),
                status: "active",
                rollout_fraction: 0.1,
            }),
        ],
        [
            (url) => url === "/api/v1/release-channels",
            () => _json_response(200, { items: [], meta: { total: 0 } }),
        ],
    ])
    const view = new PycReleaseChannels()
    document.body.appendChild(view)
    await view.refresh()

    const outcome = await view.publishRelease(
        "agent-runtime", "canary", "1.4.0",
        "oci://r/x:1.4.0", "a".repeat(64),
    )
    assert.equal(outcome.ok, true)
    assert.equal(outcome.channelId, CHANNEL_ID)
    const posted = calls.find(
        (c) => c.options !== undefined && c.options.method === "POST",
    )
    const payload = JSON.parse(posted.options.body)
    assert.equal(payload.channel, "canary")
    assert.equal(payload.component, "agent-runtime")
    document.body.removeChild(view)
})

test("PycReleaseChannels loadReleaseChannel reads a single entry", async () => {
    _install_router([
        [
            (url) => url.endsWith("/release-channels/" + CHANNEL_ID),
            () => _json_response(200, {
                channel_id: CHANNEL_ID,
                release_id: CHANNEL_ID,
                component: "agent-runtime",
                version: "1.4.0",
                channel: "stable",
                artifact_uri: "oci://r/x:1.4.0",
                artifact_sha256: "b".repeat(64),
                status: "active",
                rollout_fraction: 1,
            }),
        ],
    ])
    const view = new PycReleaseChannels()
    document.body.appendChild(view)
    const entry = await view.loadReleaseChannel(CHANNEL_ID)
    assert.notEqual(entry, null)
    assert.equal(entry.version, "1.4.0")
    document.body.removeChild(view)
})
