/**
 * Unit tests for the pyc-metrics-bundle dashboard-layout editor
 * view.
 *
 * Covers the pure tile helpers (add / remove / reorder / reindex,
 * id generation, edit-path parsing, save-payload building,
 * status-code messages) and the ``<pyc-dashboard-editor>`` Custom
 * Element's load, add / remove / reorder rendering and the
 * create-replace save -- driven against a jsdom document and a
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

const DASHBOARD_ID = "dddddddd-1111-2222-3333-444444444444"

const dom = new JSDOM(
    "<!doctype html><html><head></head><body></body></html>",
    { url: "https://example.test/dashboards/" + DASHBOARD_ID + "/edit" },
)
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.customElements = dom.window.customElements
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.HTMLButtonElement = dom.window.HTMLButtonElement
globalThis.HTMLSelectElement = dom.window.HTMLSelectElement
globalThis.HTMLInputElement = dom.window.HTMLInputElement
globalThis.HTMLFormElement = dom.window.HTMLFormElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycDashboardEditor,
    dashboard_id_from_edit_path,
    is_dashboard_edit_path,
    generate_tile_id,
    build_tile,
    add_tile,
    remove_tile,
    move_tile_up,
    move_tile_down,
    reindex_tiles,
    editor_tile_metric,
    build_save_payload,
    save_message_for_status,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

function _tile(id, metric, y) {
    return {
        tile_id: id,
        kind: "line",
        x: 0,
        y: y,
        w: 1,
        h: 1,
        config: { metric: metric },
    }
}

function _make_dashboard(overrides) {
    const base = {
        dashboard_id: DASHBOARD_ID,
        project_id: PROJECT_ID,
        name: "Service Health",
        description: "key signals",
        grid_columns_max: 12,
        version: 1,
        tiles: [_tile("t1", "http_2xx", 0), _tile("t2", "http_5xx", 1)],
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

test("dashboard_id_from_edit_path extracts the id from an edit path", () => {
    assert.equal(
        dashboard_id_from_edit_path("/dashboards/" + DASHBOARD_ID + "/edit"),
        DASHBOARD_ID,
    )
    assert.equal(dashboard_id_from_edit_path("/dashboards/" + DASHBOARD_ID), "")
    assert.equal(dashboard_id_from_edit_path("/dashboards"), "")
    assert.equal(dashboard_id_from_edit_path("/dashboards/a/b/edit"), "")
})

test("is_dashboard_edit_path classifies edit paths", () => {
    assert.equal(is_dashboard_edit_path("/dashboards/x/edit"), true)
    assert.equal(is_dashboard_edit_path("/dashboards/x"), false)
})

test("generate_tile_id produces unique prefixed ids", () => {
    const a = generate_tile_id()
    const b = generate_tile_id()
    assert.ok(a.startsWith("tile-"))
    assert.ok(b.startsWith("tile-"))
})

test("build_tile places a metric tile at the supplied index", () => {
    const tile = build_tile("http_2xx", "bar", 3)
    assert.equal(tile.kind, "bar")
    assert.equal(tile.x, 0)
    assert.equal(tile.y, 3)
    assert.equal(tile.config.metric, "http_2xx")
})

test("add_tile appends a tile and re-indexes the stack", () => {
    const tiles = [_tile("t1", "m1", 0)]
    const next = add_tile(tiles, "m2", "number")
    assert.equal(next.length, 2)
    assert.equal(next[1].y, 1)
    assert.equal(editor_tile_metric(next[1]), "m2")
    assert.equal(tiles.length, 1)
})

test("remove_tile drops a tile and re-indexes", () => {
    const tiles = [
        _tile("t1", "m1", 0),
        _tile("t2", "m2", 1),
        _tile("t3", "m3", 2),
    ]
    const next = remove_tile(tiles, "t2")
    assert.equal(next.length, 2)
    assert.deepEqual(next.map((t) => t.tile_id), ["t1", "t3"])
    assert.deepEqual(next.map((t) => t.y), [0, 1])
})

test("remove_tile is a no-op for an unknown id", () => {
    const tiles = [_tile("t1", "m1", 0)]
    const next = remove_tile(tiles, "missing")
    assert.equal(next.length, 1)
})

test("move_tile_up swaps a tile earlier and re-indexes", () => {
    const tiles = [_tile("t1", "m1", 0), _tile("t2", "m2", 1)]
    const next = move_tile_up(tiles, 1)
    assert.deepEqual(next.map((t) => t.tile_id), ["t2", "t1"])
    assert.deepEqual(next.map((t) => t.y), [0, 1])
})

test("move_tile_up is a no-op at the first slot", () => {
    const tiles = [_tile("t1", "m1", 0), _tile("t2", "m2", 1)]
    const next = move_tile_up(tiles, 0)
    assert.deepEqual(next.map((t) => t.tile_id), ["t1", "t2"])
})

test("move_tile_down swaps a tile later and re-indexes", () => {
    const tiles = [_tile("t1", "m1", 0), _tile("t2", "m2", 1)]
    const next = move_tile_down(tiles, 0)
    assert.deepEqual(next.map((t) => t.tile_id), ["t2", "t1"])
})

test("move_tile_down is a no-op at the last slot", () => {
    const tiles = [_tile("t1", "m1", 0), _tile("t2", "m2", 1)]
    const next = move_tile_down(tiles, 1)
    assert.deepEqual(next.map((t) => t.tile_id), ["t1", "t2"])
})

test("reindex_tiles re-stamps x to 0 and y to the index", () => {
    const tiles = [_tile("t1", "m1", 7), _tile("t2", "m2", 9)]
    const next = reindex_tiles(tiles)
    assert.deepEqual(next.map((t) => t.x), [0, 0])
    assert.deepEqual(next.map((t) => t.y), [0, 1])
})

test("build_save_payload builds a create-replace payload", () => {
    const dashboard = _make_dashboard()
    const payload = build_save_payload(dashboard, dashboard.tiles)
    assert.equal(payload.name, "Service Health (edited)")
    assert.equal(payload.description, "key signals")
    assert.equal(payload.grid_columns_max, 12)
    assert.equal(payload.tiles.length, 2)
    assert.equal(payload.tiles[0].config.metric, "http_2xx")
})

test("save_message_for_status maps HTTP statuses", () => {
    assert.ok(save_message_for_status(201).includes("new dashboard"))
    assert.ok(save_message_for_status(409).includes("already exists"))
    assert.ok(save_message_for_status(500).includes("HTTP 500"))
})

test("<pyc-dashboard-editor> loads and renders tiles", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Proj" }],
            }),
        ],
        [
            (url) => url === "/api/v1/metrics/catalog",
            () => _json_response(200, { items: [{ name: "http_2xx" }] }),
        ],
        [
            (url) => url.includes("/dashboards/" + DASHBOARD_ID),
            () => _json_response(200, _make_dashboard()),
        ],
    ])
    const el = new PycDashboardEditor()
    document.body.appendChild(el)
    await el.loadCatalog()
    await el.loadDashboard()

    assert.equal(el.loaded, true)
    assert.equal(el.tiles.length, 2)
    const cards = el.querySelectorAll('[data-role="editor-tile"]')
    assert.equal(cards.length, 2)
    el.remove()
})

test("<pyc-dashboard-editor> add / remove / reorder mutate the grid", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Proj" }],
            }),
        ],
        [
            (url) => url === "/api/v1/metrics/catalog",
            () => _json_response(200, { items: [{ name: "http_2xx" }] }),
        ],
        [
            (url) => url.includes("/dashboards/" + DASHBOARD_ID),
            () => _json_response(200, _make_dashboard()),
        ],
    ])
    const el = new PycDashboardEditor()
    document.body.appendChild(el)
    await el.loadCatalog()
    await el.loadDashboard()

    el.addTile("http_4xx", "number")
    assert.equal(el.tiles.length, 3)

    el.moveUp(2)
    assert.equal(el.tiles[1].config.metric, "http_4xx")

    el.removeTile(el.tiles[1].tile_id)
    assert.equal(el.tiles.length, 2)
    assert.deepEqual(el.tiles.map((t) => t.y), [0, 1])
    el.remove()
})

test("<pyc-dashboard-editor> saveLayout POSTs a create-replace", async () => {
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
            () => _json_response(200, { items: [] }),
        ],
        [
            (url, options) =>
                options !== undefined &&
                options.method === "POST" &&
                url.endsWith("/dashboards"),
            (url, options) => {
                posted = JSON.parse(options.body)
                return _json_response(201, { dashboard_id: "new-dash" })
            },
        ],
        [
            (url) => url.includes("/dashboards/" + DASHBOARD_ID),
            () => _json_response(200, _make_dashboard()),
        ],
    ])
    const el = new PycDashboardEditor()
    document.body.appendChild(el)
    await el.loadCatalog()
    await el.loadDashboard()

    const outcome = await el.saveLayout()
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 201)
    assert.equal(outcome.dashboardId, "new-dash")
    assert.equal(posted.name, "Service Health (edited)")
    assert.equal(posted.tiles.length, 2)
    el.remove()
})

test("<pyc-dashboard-editor> surfaces an error state on a failed load", async () => {
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
            (url) => url.includes("/dashboards/" + DASHBOARD_ID),
            () => _json_response(404, {}),
        ],
    ])
    const el = new PycDashboardEditor()
    document.body.appendChild(el)
    await el.loadCatalog()
    await el.loadDashboard()
    assert.equal(el.loaded, false)
    assert.ok(el.querySelector('[data-role="error-state"]') !== null)
    el.remove()
})
