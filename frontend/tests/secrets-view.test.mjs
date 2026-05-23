/**
 * Unit tests for the pyc-secrets-bundle secrets view.
 *
 * Covers the pure URL helpers and the ``<pyc-secrets>`` Custom
 * Element's scope-tab switching, create form, the value-reveal
 * flow (value fetched on reveal, cleared on collapse / navigate),
 * 403-on-reveal handling, and the list-never-requests-values
 * invariant. Driven against a jsdom document and a stubbed
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
    "pyc-secrets-bundle",
    "index.js",
)

const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/secrets",
})
globalThis.CSS = dom.window.CSS

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycSecrets,
    build_secrets_list_url,
    build_secret_value_url,
    reveal_error_message,
} = bundle

function _make_secret(overrides) {
    const base = {
        secret_ref: "vault/myteam/api-token",
        backend_name: "local",
        scope_kind: "ORG",
        scope_ref: null,
        current_version_id: "v1",
        created_at: "2026-05-17T10:00:00Z",
        updated_at: "2026-05-17T10:00:00Z",
    }
    return Object.assign(base, overrides)
}

/**
 * Install a fetch stub. ``handlers`` maps a URL substring to a
 * response descriptor ``{ status, body }``. Records every call.
 */
function _install_fetch(handlers) {
    const calls = []
    globalThis.fetch = async (url, options) => {
        calls.push({ url, options })
        let matched = { status: 200, body: [] }
        // Longest key first so a specific URL substring wins over
        // a prefix that is also contained in it.
        const keys = Object.keys(handlers).sort((a, b) => b.length - a.length)
        for (const key of keys) {
            if (url.includes(key)) {
                matched = handlers[key]
                break
            }
        }
        const response = {
            ok: matched.status >= 200 && matched.status < 300,
            status: matched.status,
            json: async () => matched.body,
        }
        return response
    }
    return calls
}

test("build_secrets_list_url omits scope_ref for ORG scope", () => {
    const url = build_secrets_list_url("ORG", "proj-1")
    assert.equal(url.includes("scope_kind=ORG"), true)
    assert.equal(url.includes("scope_ref"), false)
})

test("build_secrets_list_url includes scope_ref for PROJECT scope", () => {
    const url = build_secrets_list_url("PROJECT", "proj-1")
    assert.equal(url.includes("scope_kind=PROJECT"), true)
    assert.equal(url.includes("scope_ref=proj-1"), true)
})

test("build_secret_value_url encodes the slash-delimited ref", () => {
    const url = build_secret_value_url("vault/my team/api-token")
    assert.equal(url, "/api/v1/secrets/value/vault/my%20team/api-token")
})

test("reveal_error_message maps 403 to a no-access message", () => {
    const msg = reveal_error_message(403)
    assert.equal(msg.includes("don't have access"), true)
})

test("PycSecrets fetches ORG metadata on connect and renders rows", async () => {
    const calls = _install_fetch({
        "/api/v1/secrets": {
            status: 200,
            body: [_make_secret({}), _make_secret({ secret_ref: "system/other" })],
        },
    })

    const element = new PycSecrets()
    document.body.appendChild(element)
    await element.refresh()

    assert.equal(calls[0].url.startsWith("/api/v1/secrets"), true)
    assert.equal(calls[0].url.includes("scope_kind=ORG"), true)
    assert.equal(calls[0].options.credentials, "same-origin")

    const table = element.querySelector("mj-table.pyc-secrets__table")
    const rows = table.shadowRoot.querySelectorAll("tr.pyc-secrets__row")
    assert.equal(rows.length, 2)
    element.remove()
})

test("the metadata list never requests secret values", async () => {
    const calls = _install_fetch({
        "/api/v1/secrets": { status: 200, body: [_make_secret({})] },
    })

    const element = new PycSecrets()
    document.body.appendChild(element)
    await element.refresh()

    for (const call of calls) {
        assert.equal(call.url.includes("/secrets/value/"), false)
    }
    // The masked placeholder is rendered, not a value.
    const table = element.querySelector("mj-table.pyc-secrets__table")
    const masked = table.shadowRoot.querySelector('[data-role="masked-value"]')
    assert.notEqual(masked, null)
    element.remove()
})

test("switching scope tab to USER re-fetches with the USER scope", async () => {
    const calls = _install_fetch({
        "/api/v1/secrets": { status: 200, body: [] },
    })

    const element = new PycSecrets()
    document.body.appendChild(element)
    await element.refresh()

    const user_tab = element.querySelector('[data-scope-kind="USER"]')
    user_tab.dispatchEvent(new dom.window.Event("click"))
    await new Promise((resolve) => setTimeout(resolve, 0))

    assert.equal(element.viewState.scopeKind, "USER")
    const last_call = calls[calls.length - 1]
    assert.equal(last_call.url.includes("scope_kind=USER"), true)
    element.remove()
})

test("the create form POSTs name + scope + value", async () => {
    const calls = _install_fetch({
        "/api/v1/secrets": { status: 200, body: [] },
    })

    const element = new PycSecrets()
    document.body.appendChild(element)
    await element.refresh()

    const name_input = element.querySelector('[data-role="create-name"]')
    const value_input = element.querySelector('[data-role="create-value"]')
    const form = element.querySelector('[data-role="create-form"]')
    name_input.value = "vault/team/new-token"
    value_input.value = "s3cr3t"
    form.dispatchEvent(new dom.window.Event("submit"))
    await new Promise((resolve) => setTimeout(resolve, 0))

    let post_call = null
    for (const call of calls) {
        if (call.options !== undefined && call.options.method === "POST") {
            post_call = call
        }
    }
    assert.notEqual(post_call, null)
    const payload = JSON.parse(post_call.options.body)
    assert.equal(payload.name, "vault/team/new-token")
    assert.equal(payload.scope_kind, "ORG")
    assert.equal(payload.value, "s3cr3t")
    // The value input is cleared after a successful create.
    assert.equal(value_input.value, "")
    element.remove()
})

test("reveal fetches the value, collapse clears it", async () => {
    _install_fetch({
        "/api/v1/secrets/value/": {
            status: 200,
            body: {
                secret_ref: "vault/myteam/api-token",
                version_number: 1,
                value: "plaintext-value",
            },
        },
        "/api/v1/secrets": { status: 200, body: [_make_secret({})] },
    })

    const element = new PycSecrets()
    document.body.appendChild(element)
    await element.refresh()

    const table = element.querySelector("mj-table.pyc-secrets__table")
    const reveal = table.shadowRoot.querySelector('[data-role="reveal-action"]')
    reveal.dispatchEvent(new dom.window.Event("click"))
    await new Promise((resolve) => setTimeout(resolve, 0))

    let revealed = table.shadowRoot.querySelector('[data-role="revealed-value"]')
    assert.notEqual(revealed, null)
    assert.equal(revealed.textContent, "plaintext-value")
    assert.equal(element.revealedCount, 1)

    // Collapse -- the value is dropped from transient state.
    const reveal2 = table.shadowRoot.querySelector('[data-role="reveal-action"]')
    reveal2.dispatchEvent(new dom.window.Event("click"))
    await new Promise((resolve) => setTimeout(resolve, 0))

    revealed = table.shadowRoot.querySelector('[data-role="revealed-value"]')
    assert.equal(revealed, null)
    assert.equal(element.revealedCount, 0)
    element.remove()
})

test("navigation away (disconnect) clears every revealed value", async () => {
    _install_fetch({
        "/api/v1/secrets/value/": {
            status: 200,
            body: {
                secret_ref: "vault/myteam/api-token",
                version_number: 1,
                value: "plaintext-value",
            },
        },
        "/api/v1/secrets": { status: 200, body: [_make_secret({})] },
    })

    const element = new PycSecrets()
    document.body.appendChild(element)
    await element.refresh()

    const table = element.querySelector("mj-table.pyc-secrets__table")
    const reveal = table.shadowRoot.querySelector('[data-role="reveal-action"]')
    reveal.dispatchEvent(new dom.window.Event("click"))
    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(element.revealedCount, 1)

    element.remove()
    assert.equal(element.revealedCount, 0)
})

test("a 403 on reveal renders the no-access message, not a crash", async () => {
    _install_fetch({
        "/api/v1/secrets/value/": { status: 403, body: {} },
        "/api/v1/secrets": { status: 200, body: [_make_secret({})] },
    })

    const element = new PycSecrets()
    document.body.appendChild(element)
    await element.refresh()

    const table = element.querySelector("mj-table.pyc-secrets__table")
    const reveal = table.shadowRoot.querySelector('[data-role="reveal-action"]')
    reveal.dispatchEvent(new dom.window.Event("click"))
    await new Promise((resolve) => setTimeout(resolve, 0))

    const error = table.shadowRoot.querySelector('[data-role="reveal-error"]')
    assert.notEqual(error, null)
    assert.equal(error.textContent.includes("don't have access"), true)
    assert.equal(element.revealedCount, 0)
    element.remove()
})

test("a 403 on the list renders the forbidden state", async () => {
    _install_fetch({
        "/api/v1/secrets": { status: 403, body: {} },
    })

    const element = new PycSecrets()
    document.body.appendChild(element)
    await element.refresh()

    const forbidden = element.querySelector('[data-role="forbidden-state"]')
    assert.notEqual(forbidden, null)
    element.remove()
})
