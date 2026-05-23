/**
 * Unit tests for the pyc-catalog-bundle test-catalog view.
 *
 * Covers the pure helpers and the ``<pyc-test-catalog>`` Custom
 * Element's project-select + catalog fetch, pagination, the
 * import-form submit, and the per-entry trigger-run action --
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
    "pyc-catalog-bundle",
    "index.js",
)

const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/test-catalog",
})

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycTestCatalog,
    build_catalog_query_url,
    build_test_runs_url,
    build_catalog_import_url,
    trigger_message_for_status,
    has_next_page,
    has_previous_page,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

function _make_entry(overrides) {
    const base = {
        entry_id: "11111111-2222-3333-4444-555555555555",
        project_id: PROJECT_ID,
        importer_tag: "testbase-project",
        entry_key: "automojo.tests.singlehost.test_one",
        display_name: "test_one",
        required_capability_tags: ["linux"],
        retired: false,
        created_at: "2026-05-17T10:00:00Z",
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
    const response = {
        ok: status >= 200 && status < 300,
        status: status,
        json: async () => body,
    }
    return response
}

test("build_catalog_query_url targets the project test-catalog path", () => {
    const url = build_catalog_query_url({
        projectId: PROJECT_ID,
        page: 2,
        perPage: 25,
        total: 0,
        includeRetired: true,
        loading: false,
        errored: false,
    })
    assert.equal(
        url.startsWith("/api/v1/projects/" + PROJECT_ID + "/test-catalog?"),
        true,
    )
    assert.equal(url.includes("page=2"), true)
    assert.equal(url.includes("include_retired=true"), true)
})

test("build_test_runs_url + build_catalog_import_url target the right paths", () => {
    assert.equal(
        build_test_runs_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/test-runs",
    )
    assert.equal(
        build_catalog_import_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/test-catalog:import",
    )
})

test("trigger_message_for_status maps 409 to the no-eligible-pod guidance", () => {
    const message = trigger_message_for_status(409)
    assert.equal(message.includes("No client/pod is enrolled"), true)
    assert.equal(trigger_message_for_status(202), "Run triggered.")
})

test("pagination helpers gate next/prev from page + total", () => {
    const first = {
        projectId: PROJECT_ID, page: 1, perPage: 25, total: 100,
        includeRetired: false, loading: false, errored: false,
    }
    assert.equal(has_previous_page(first), false)
    assert.equal(has_next_page(first), true)
})

test("project selection fetches the catalog and renders rows", async () => {
    const calls = _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [
                    { project_id: PROJECT_ID, slug: "proj", display_name: "Proj" },
                ],
            }),
        ],
        [
            (url) => url.includes("/test-catalog?"),
            () => _json_response(200, {
                items: [_make_entry({}), _make_entry({
                    entry_id: "99999999-0000-0000-0000-000000000000",
                })],
                meta: { page: 1, per_page: 25, total: 2 },
            }),
        ],
    ])

    const element = new PycTestCatalog()
    document.body.appendChild(element)
    await element.loadProjects()

    assert.equal(calls[0].url, "/api/v1/projects")
    assert.equal(element.viewState.projectId, PROJECT_ID)
    const table = element.querySelector("mj-data-table.pyc-catalog__table")
    const rows = table.shadowRoot.querySelectorAll(".row.pyc-catalog__row")
    assert.equal(rows.length, 2)
    element.remove()
})

test("missing projects endpoint degrades to the manual project input", async () => {
    _install_router([
        [(url) => url === "/api/v1/projects", () => _json_response(404, {})],
    ])

    const element = new PycTestCatalog()
    document.body.appendChild(element)
    await element.loadProjects()

    const input = element.querySelector('[data-role="project-input"]')
    const select = element.querySelector('[data-role="project-select"]')
    assert.equal(input.hidden, false)
    assert.equal(select.hidden, true)
    const prompt = element.querySelector('[data-role="no-project-state"]')
    assert.notEqual(prompt, null)
    element.remove()
})

test("catalog fetch error surfaces the error state", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, slug: "p", display_name: "P" }],
            }),
        ],
        [(url) => url.includes("/test-catalog?"), () => _json_response(500, {})],
    ])

    const element = new PycTestCatalog()
    document.body.appendChild(element)
    await element.loadProjects()

    assert.equal(element.viewState.errored, true)
    assert.notEqual(element.querySelector('[data-role="error-state"]'), null)
    element.remove()
})

test("empty catalog renders the import-prompt empty state", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, slug: "p", display_name: "P" }],
            }),
        ],
        [
            (url) => url.includes("/test-catalog?"),
            () => _json_response(200, {
                items: [], meta: { page: 1, per_page: 25, total: 0 },
            }),
        ],
    ])

    const element = new PycTestCatalog()
    document.body.appendChild(element)
    await element.loadProjects()

    const empty = element.querySelector('[data-role="empty-state"]')
    assert.notEqual(empty, null)
    element.remove()
})

test("import-form submit POSTs the importer request and reloads", async () => {
    let catalog_calls = 0
    const calls = _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, slug: "p", display_name: "P" }],
            }),
        ],
        [
            (url, options) => url.endsWith("/test-catalog:import") &&
                options.method === "POST",
            () => _json_response(202, {
                importer_tag: "testbase-project",
                started_at: "2026-05-20T00:00:00Z",
                entries_imported: 4,
            }),
        ],
        [
            (url) => url.includes("/test-catalog?"),
            () => {
                catalog_calls = catalog_calls + 1
                return _json_response(200, {
                    items: [_make_entry({})],
                    meta: { page: 1, per_page: 25, total: 1 },
                })
            },
        ],
    ])

    const element = new PycTestCatalog()
    document.body.appendChild(element)
    await element.loadProjects()
    const before = catalog_calls

    await element.submitImport("testbase-project", "source/testroots", "main", null, null)

    const import_call = calls.find(
        (c) => c.url.endsWith("/test-catalog:import"),
    )
    assert.notEqual(import_call, undefined)
    const body = JSON.parse(import_call.options.body)
    assert.equal(body.importer_tag, "testbase-project")
    assert.equal(body.source.root, "source/testroots")
    assert.equal(body.source.ref, "main")
    // The import reloads the catalog.
    assert.equal(catalog_calls > before, true)
    element.remove()
})

test("trigger-run success surfaces a run-detail link in the toast", async () => {
    const RUN_ID = "abcdef01-2222-3333-4444-555555555555"
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, slug: "p", display_name: "P" }],
            }),
        ],
        [
            (url, options) => url.endsWith("/test-runs") &&
                options.method === "POST",
            () => _json_response(202, {
                run_id: RUN_ID, project_id: PROJECT_ID, state: "pending",
            }),
        ],
        [
            (url) => url.includes("/test-catalog?"),
            () => _json_response(200, {
                items: [_make_entry({})],
                meta: { page: 1, per_page: 25, total: 1 },
            }),
        ],
    ])

    const element = new PycTestCatalog()
    document.body.appendChild(element)
    await element.loadProjects()

    const outcome = await element.triggerRun(_make_entry({}), null)
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 202)
    assert.equal(outcome.runId, RUN_ID)

    const link = element.querySelector('[data-role="run-link"]')
    assert.notEqual(link, null)
    assert.equal(link.getAttribute("href"), "/runs/" + RUN_ID)
    element.remove()
})

test("trigger-run POSTs the catalog entry id in the request body", async () => {
    const calls = _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, slug: "p", display_name: "P" }],
            }),
        ],
        [
            (url, options) => url.endsWith("/test-runs") &&
                options.method === "POST",
            () => _json_response(202, {
                run_id: "r", project_id: PROJECT_ID, state: "pending",
            }),
        ],
        [
            (url) => url.includes("/test-catalog?"),
            () => _json_response(200, {
                items: [_make_entry({})],
                meta: { page: 1, per_page: 25, total: 1 },
            }),
        ],
    ])

    const element = new PycTestCatalog()
    document.body.appendChild(element)
    await element.loadProjects()
    await element.triggerRun(_make_entry({}), null)

    const run_call = calls.find((c) => c.url.endsWith("/test-runs"))
    const body = JSON.parse(run_call.options.body)
    assert.equal(body.catalog_entry_id, "11111111-2222-3333-4444-555555555555")
    assert.equal(run_call.options.credentials, "same-origin")
    element.remove()
})

test("trigger-run 409 surfaces the no-eligible-pod message", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, slug: "p", display_name: "P" }],
            }),
        ],
        [
            (url, options) => url.endsWith("/test-runs") &&
                options.method === "POST",
            () => _json_response(409, {
                type: "about:blank", title: "Conflict",
                detail: "No eligible pod.",
            }),
        ],
        [
            (url) => url.includes("/test-catalog?"),
            () => _json_response(200, {
                items: [_make_entry({})],
                meta: { page: 1, per_page: 25, total: 1 },
            }),
        ],
    ])

    const element = new PycTestCatalog()
    document.body.appendChild(element)
    await element.loadProjects()

    const outcome = await element.triggerRun(_make_entry({}), null)
    assert.equal(outcome.ok, false)
    assert.equal(outcome.status, 409)
    assert.equal(outcome.message.includes("No client/pod is enrolled"), true)

    const toast = element.querySelector('[data-role="trigger-toast"]')
    assert.notEqual(toast, null)
    assert.equal(toast.getAttribute("data-tone"), "error")
    assert.equal(element.querySelector('[data-role="run-link"]'), null)
    element.remove()
})
