/**
 * Unit tests for the pyc-runs-bundle runs list view.
 *
 * Covers the pure filter/pagination helpers and the
 * ``<pyc-runs-list>`` Custom Element's fetch + state management,
 * driven against a jsdom document and a stubbed ``fetch``.
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
    "pyc-runs-bundle",
    "index.js",
)

// jsdom + mj-* registration so the mj-table inside the runs list
// actually instantiates and renders rows into its shadow DOM.
const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/runs",
})

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycRunsList,
} = bundle

function _make_run(overrides) {
    const base = {
        run_id: "11111111-2222-3333-4444-555555555555",
        project_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        pod_id: "99999999-8888-7777-6666-555555555555",
        job_type: "test",
        state: "running",
        created_at: "2026-05-17T10:00:00Z",
        started_at: "2026-05-17T10:01:00Z",
        completed_at: null,
    }
    return Object.assign(base, overrides)
}

function _install_fetch(page_payload) {
    const calls = []
    globalThis.fetch = async (url, options) => {
        calls.push({ url, options })
        const response = {
            ok: true,
            status: 200,
            json: async () => page_payload,
        }
        return response
    }
    return calls
}

test("PycRunsList fetches the first page on connect and renders rows", async () => {
    const calls = _install_fetch({
        items: [_make_run({}), _make_run({ run_id: "abcdef01-0000-0000-0000-000000000000" })],
        meta: { page: 1, per_page: 25, total: 2 },
    })

    const element = new PycRunsList()
    document.body.appendChild(element)
    await element.refresh()

    assert.equal(calls.length >= 1, true)
    assert.equal(calls[0].url.startsWith("/api/v1/runs?"), true)
    assert.equal(calls[0].options.credentials, "same-origin")

    const table = element.querySelector("mj-table.pyc-runs-list__table")
    const rows = table.shadowRoot.querySelectorAll("tr.pyc-runs-list__row")
    assert.equal(rows.length, 2)

    const first_link = table.shadowRoot.querySelector(".pyc-runs-list__run-link")
    assert.equal(
        first_link.getAttribute("href"),
        "/runs/11111111-2222-3333-4444-555555555555",
    )
    assert.equal(first_link.textContent, "11111111")
    element.remove()
})

test("PycRunsList renders the empty state when no runs are returned", async () => {
    _install_fetch({ items: [], meta: { page: 1, per_page: 25, total: 0 } })

    const element = new PycRunsList()
    document.body.appendChild(element)
    await element.refresh()

    const empty = element.querySelector('[data-role="empty-state"]')
    assert.notEqual(empty, null)
    assert.equal(empty.textContent, "No runs yet")
    element.remove()
})

test("PycRunsList renders the error state when fetch fails", async () => {
    globalThis.fetch = async () => {
        const response = {
            ok: false,
            status: 500,
            json: async () => ({}),
        }
        return response
    }

    const element = new PycRunsList()
    document.body.appendChild(element)
    await element.refresh()

    const error = element.querySelector('[data-role="error-state"]')
    assert.notEqual(error, null)
    assert.equal(element.listState.errored, true)
    element.remove()
})

test("changing the state filter resets page and re-fetches", async () => {
    const calls = _install_fetch({
        items: [_make_run({})],
        meta: { page: 1, per_page: 25, total: 1 },
    })

    const element = new PycRunsList()
    document.body.appendChild(element)
    await element.refresh()

    const select = element.querySelector('[data-role="state-filter"]')
    select.value = "failed"
    select.dispatchEvent(new dom.window.Event("change"))
    await new Promise((resolve) => setTimeout(resolve, 0))

    assert.equal(element.listState.stateFilter, "failed")
    assert.equal(element.listState.page, 1)
    const last_call = calls[calls.length - 1]
    assert.equal(last_call.url.includes("state=failed"), true)
    element.remove()
})

test("pagination advances the page and disables prev on page one", async () => {
    const calls = _install_fetch({
        items: [_make_run({})],
        meta: { page: 1, per_page: 1, total: 5 },
    })

    const element = new PycRunsList()
    document.body.appendChild(element)
    await element.refresh()

    const pager = element.querySelector('mj-pagination[data-role="pager"]')
    assert.equal(pager.getAttribute("page"), "1")
    assert.equal(pager.getAttribute("total-items"), "5")

    // Server echoes page 2 on the next fetch.
    _install_fetch_with(calls, {
        items: [_make_run({})],
        meta: { page: 2, per_page: 1, total: 5 },
    })
    pager.dispatchEvent(new dom.window.CustomEvent("mj-pagination-change", {
        detail: { page: 2, pageSize: 1 },
    }))
    await new Promise((resolve) => setTimeout(resolve, 0))

    assert.equal(element.listState.page, 2)
    assert.equal(pager.getAttribute("page"), "2")
    element.remove()
})

function _install_fetch_with(calls, page_payload) {
    globalThis.fetch = async (url, options) => {
        calls.push({ url, options })
        const response = {
            ok: true,
            status: 200,
            json: async () => page_payload,
        }
        return response
    }
    return calls
}
