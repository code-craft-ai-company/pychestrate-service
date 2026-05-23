/**
 * Unit tests for the pyc-metrics-bundle views.
 *
 * Covers the pure helpers (rate / duration formatting, bar
 * fractions, timeseries SVG path computation, dashboard route
 * parsing, tile metric resolution) and the ``<pyc-test-metrics>``,
 * ``<pyc-timeseries-explorer>``, ``<pyc-dashboards-list>`` and
 * ``<pyc-dashboard-detail>`` Custom Elements -- driven against a
 * jsdom document and a stubbed ``fetch``.
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
    url: "https://example.test/test-metrics",
})
globalThis.HTMLFormElement = dom.window.HTMLFormElement
globalThis.SVGElement = dom.window.SVGElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycTestMetrics,
    PycTimeseriesExplorer,
    PycDashboardsList,
    PycDashboardDetail,
    build_test_metrics_url,
    format_rate,
    format_duration,
    compute_bar_fractions,
    short_metric_id,
    build_catalog_url,
    build_timeseries_url,
    resolve_range_preset,
    project_points,
    build_line_path,
    build_area_path,
    extract_catalog,
    build_dashboards_collection_url,
    build_dashboard_detail_url,
    dashboard_id_from_path,
    create_message_for_status,
    tile_metric_name,
    extract_dashboards,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
const DASHBOARD_ID = "11111111-2222-3333-4444-555555555555"

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

async function _flush() {
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))
}

// ---------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------

test("build_test_metrics_url shape", () => {
    assert.equal(
        build_test_metrics_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/test-metrics",
    )
})

test("format_rate maps 0..1 to whole percentages", () => {
    assert.equal(format_rate(0.94), "94%")
    assert.equal(format_rate(0.945), "95%")
    assert.equal(format_rate(1), "100%")
    assert.equal(format_rate(0), "0%")
    assert.equal(format_rate(Number.NaN), "—")
})

test("format_duration uses seconds then minutes", () => {
    assert.equal(format_duration(12.34), "12.3s")
    assert.equal(format_duration(125), "2m 5s")
    assert.equal(format_duration(null), "—")
})

test("compute_bar_fractions normalises to the tallest", () => {
    const fractions = compute_bar_fractions([10, 20, 40])
    assert.equal(fractions.length, 3)
    assert.equal(fractions[2], 1)
    assert.equal(fractions[1], 0.5)
    assert.equal(fractions[0], 0.25)
    assert.deepEqual(compute_bar_fractions([]), [])
    assert.deepEqual(compute_bar_fractions([0, 0]), [0, 0])
})

test("short_metric_id trims to the leading UUID segment", () => {
    assert.equal(short_metric_id(PROJECT_ID), "aaaaaaaa")
    assert.equal(short_metric_id(""), "")
})

test("build_catalog_url shape", () => {
    assert.equal(build_catalog_url(), "/api/v1/metrics/catalog")
})

test("resolve_range_preset falls back to first preset", () => {
    assert.equal(resolve_range_preset("24h").id, "24h")
    assert.equal(resolve_range_preset("nonsense").id, "1h")
})

test("build_timeseries_url includes metric and bounded window", () => {
    const now = new Date("2026-05-20T12:00:00Z")
    const url = build_timeseries_url("http_requests", "1h", now)
    assert.ok(url.startsWith("/api/v1/metrics/timeseries?"))
    assert.ok(url.includes("metric=http_requests"))
    assert.ok(url.includes("from=2026-05-20T11%3A00%3A00.000Z"))
    assert.ok(url.includes("to=2026-05-20T12%3A00%3A00.000Z"))
})

test("build_timeseries_url omits window for the all-time preset", () => {
    const now = new Date("2026-05-20T12:00:00Z")
    const url = build_timeseries_url("http_requests", "all", now)
    assert.ok(url.includes("metric=http_requests"))
    assert.ok(url.includes("from=") === false)
})

test("project_points maps values into the inverted SVG plot area", () => {
    const points = [
        { observed_at: "2026-05-20T10:00:00Z", value: 0 },
        { observed_at: "2026-05-20T11:00:00Z", value: 10 },
        { observed_at: "2026-05-20T12:00:00Z", value: 5 },
    ]
    const coords = project_points(points)
    assert.equal(coords.length, 3)
    // oldest-first along x.
    assert.ok(coords[0].x < coords[1].x)
    assert.ok(coords[1].x < coords[2].x)
    // larger value -> smaller y (higher on the chart).
    assert.ok(coords[1].y < coords[0].y)
    assert.ok(coords[2].y > coords[1].y)
})

test("project_points sorts unordered input oldest-first", () => {
    const points = [
        { observed_at: "2026-05-20T12:00:00Z", value: 3 },
        { observed_at: "2026-05-20T10:00:00Z", value: 1 },
    ]
    const coords = project_points(points)
    assert.ok(coords[0].x < coords[1].x)
})

test("project_points handles empty + single point", () => {
    assert.deepEqual(project_points([]), [])
    const single = project_points([
        { observed_at: "2026-05-20T10:00:00Z", value: 7 },
    ])
    assert.equal(single.length, 1)
})

test("build_line_path emits a move then line commands", () => {
    const coords = [
        { x: 0, y: 0 },
        { x: 10, y: 20 },
    ]
    const d = build_line_path(coords)
    assert.ok(d.startsWith("M 0.00 0.00"))
    assert.ok(d.includes("L 10.00 20.00"))
    assert.equal(build_line_path([]), "")
})

test("build_area_path closes the line down to the chart floor", () => {
    const coords = [
        { x: 16, y: 50 },
        { x: 700, y: 30 },
    ]
    const d = build_area_path(coords)
    assert.ok(d.startsWith("M 16.00 50.00"))
    assert.ok(d.trim().endsWith("Z"))
    assert.equal(build_area_path([]), "")
})

test("extract_catalog tolerates array and {items} envelopes", () => {
    const bare = extract_catalog([
        { name: "m1", kind: "counter", label_names: ["a"] },
    ])
    assert.equal(bare.length, 1)
    assert.equal(bare[0].name, "m1")
    const enveloped = extract_catalog({
        items: [{ name: "m2", kind: "gauge", label_names: [] }],
    })
    assert.equal(enveloped.length, 1)
    assert.equal(enveloped[0].kind, "gauge")
    assert.deepEqual(extract_catalog(null), [])
})

test("build_dashboards_collection_url + detail_url shapes", () => {
    assert.equal(
        build_dashboards_collection_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/dashboards",
    )
    assert.equal(
        build_dashboard_detail_url(PROJECT_ID, DASHBOARD_ID),
        "/api/v1/projects/" + PROJECT_ID + "/dashboards/" + DASHBOARD_ID,
    )
})

test("dashboard_id_from_path parses only detail paths", () => {
    assert.equal(
        dashboard_id_from_path("/dashboards/" + DASHBOARD_ID),
        DASHBOARD_ID,
    )
    assert.equal(
        dashboard_id_from_path("/dashboards/" + DASHBOARD_ID + "?x=1"),
        DASHBOARD_ID,
    )
    assert.equal(dashboard_id_from_path("/dashboards"), "")
    assert.equal(dashboard_id_from_path("/dashboards/"), "")
    assert.equal(dashboard_id_from_path("/dashboards/a/b"), "")
    assert.equal(dashboard_id_from_path("/other"), "")
})

test("create_message_for_status maps known statuses", () => {
    assert.equal(create_message_for_status(201), "Dashboard created.")
    assert.ok(create_message_for_status(409).includes("already exists"))
    assert.ok(create_message_for_status(422).includes("rejected"))
    assert.ok(create_message_for_status(500).includes("500"))
})

test("tile_metric_name reads the config.metric key", () => {
    assert.equal(
        tile_metric_name({ tile_id: "t1", config: { metric: "cpu" } }),
        "cpu",
    )
    assert.equal(tile_metric_name({ tile_id: "t2" }), "")
    assert.equal(tile_metric_name({ tile_id: "t3", config: {} }), "")
})

test("extract_dashboards tolerates array and {items} envelopes", () => {
    const result = extract_dashboards({
        items: [
            {
                dashboard_id: DASHBOARD_ID,
                project_id: PROJECT_ID,
                name: "Ops",
                tiles: [{ tile_id: "t1", kind: "chart" }],
                version: 2,
            },
        ],
    })
    assert.equal(result.length, 1)
    assert.equal(result[0].name, "Ops")
    assert.equal(result[0].tiles.length, 1)
    assert.equal(result[0].version, 2)
})

// ---------------------------------------------------------------
// <pyc-test-metrics> element
// ---------------------------------------------------------------

test("pyc-test-metrics renders the rollup cards + runs table", async () => {
    if (customElements.get("pyc-test-metrics") === undefined) {
        customElements.define("pyc-test-metrics", PycTestMetrics)
    }
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () =>
                _json_response(200, {
                    items: [
                        { project_id: PROJECT_ID, display_name: "Proj" },
                    ],
                }),
        ],
        [
            (url) => url.includes("/test-metrics"),
            () =>
                _json_response(200, {
                    project_id: PROJECT_ID,
                    summary: {
                        run_count: 4,
                        tests_total: 100,
                        tests_passed: 94,
                        tests_failed: 6,
                        tests_skipped: 0,
                        tests_errored: 0,
                        pass_rate: 0.94,
                        fail_rate: 0.06,
                        runs_with_failures: 1,
                        flake_run_rate: 0.25,
                        average_run_duration_seconds: 42,
                    },
                    recent_runs: [
                        {
                            run_id: "r1-aaaa",
                            parser_tag: "pytest",
                            tests_total: 50,
                            tests_passed: 48,
                            tests_failed: 2,
                            duration_seconds: 40,
                        },
                        {
                            run_id: "r2-bbbb",
                            parser_tag: "pytest",
                            tests_total: 50,
                            tests_passed: 46,
                            tests_failed: 0,
                            duration_seconds: 44,
                        },
                    ],
                }),
        ],
    ])

    const element = new PycTestMetrics()
    document.body.appendChild(element)
    await element.loadProjects()
    await _flush()

    const cards = element.querySelector('[data-role="rollup-cards"]')
    assert.ok(cards !== null)
    assert.ok(cards.textContent.includes("94%"))
    const trend = element.querySelector('[data-role="duration-trend"]')
    assert.equal(trend.querySelectorAll(".pyc-metrics__bar").length, 2)
    const table = element.querySelector('[data-role="runs-table"]')
    assert.equal(table.shadowRoot.querySelectorAll("tbody tr").length, 2)
    assert.equal(element.viewState.errored, false)
    element.remove()
})

test("pyc-test-metrics surfaces an error notice on a failed fetch", async () => {
    if (customElements.get("pyc-test-metrics") === undefined) {
        customElements.define("pyc-test-metrics", PycTestMetrics)
    }
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () =>
                _json_response(200, {
                    items: [
                        { project_id: PROJECT_ID, display_name: "Proj" },
                    ],
                }),
        ],
        [
            (url) => url.includes("/test-metrics"),
            () => _json_response(500, {}),
        ],
    ])

    const element = new PycTestMetrics()
    document.body.appendChild(element)
    await element.loadProjects()
    await _flush()

    const notice = element.querySelector(".pyc-metrics__notice--error")
    assert.ok(notice !== null)
    assert.equal(element.viewState.errored, true)
    element.remove()
})

// ---------------------------------------------------------------
// <pyc-timeseries-explorer> element
// ---------------------------------------------------------------

test("pyc-timeseries-explorer fetches catalog then renders SVG", async () => {
    if (customElements.get("pyc-timeseries-explorer") === undefined) {
        customElements.define(
            "pyc-timeseries-explorer",
            PycTimeseriesExplorer,
        )
    }
    _install_router([
        [
            (url) => url.includes("/metrics/catalog"),
            () =>
                _json_response(200, {
                    items: [
                        {
                            name: "http_requests",
                            kind: "counter",
                            label_names: [],
                        },
                    ],
                }),
        ],
        [
            (url) => url.includes("/metrics/timeseries"),
            () =>
                _json_response(200, {
                    metric: "http_requests",
                    kind: "counter",
                    points: [
                        { observed_at: "2026-05-20T10:00:00Z", value: 1 },
                        { observed_at: "2026-05-20T11:00:00Z", value: 5 },
                        { observed_at: "2026-05-20T12:00:00Z", value: 3 },
                    ],
                }),
        ],
    ])

    const element = new PycTimeseriesExplorer()
    document.body.appendChild(element)
    await element.loadCatalog()
    await _flush()

    const chart = element.querySelector('[data-role="timeseries-chart"]')
    assert.ok(chart !== null)
    assert.equal(
        chart.querySelectorAll(".pyc-metrics__chart-line").length,
        1,
    )
    assert.equal(
        chart.querySelectorAll(".pyc-metrics__chart-area").length,
        1,
    )
    assert.equal(element.viewState.metric, "http_requests")
    element.remove()
})

test("pyc-timeseries-explorer shows empty notice for no points", async () => {
    if (customElements.get("pyc-timeseries-explorer") === undefined) {
        customElements.define(
            "pyc-timeseries-explorer",
            PycTimeseriesExplorer,
        )
    }
    _install_router([
        [
            (url) => url.includes("/metrics/catalog"),
            () =>
                _json_response(200, {
                    items: [
                        { name: "m", kind: "gauge", label_names: [] },
                    ],
                }),
        ],
        [
            (url) => url.includes("/metrics/timeseries"),
            () =>
                _json_response(200, { metric: "m", points: [] }),
        ],
    ])

    const element = new PycTimeseriesExplorer()
    document.body.appendChild(element)
    await element.loadCatalog()
    await _flush()

    const notice = element.querySelector(".pyc-metrics__notice")
    assert.ok(notice !== null)
    assert.ok(notice.textContent.includes("No data points"))
    element.remove()
})

// ---------------------------------------------------------------
// <pyc-dashboards-list> element
// ---------------------------------------------------------------

test("pyc-dashboards-list lists dashboards with detail links", async () => {
    if (customElements.get("pyc-dashboards-list") === undefined) {
        customElements.define("pyc-dashboards-list", PycDashboardsList)
    }
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () =>
                _json_response(200, {
                    items: [
                        { project_id: PROJECT_ID, display_name: "Proj" },
                    ],
                }),
        ],
        [
            (url, options) =>
                url.includes("/dashboards") &&
                (options === undefined || options.method !== "POST"),
            () =>
                _json_response(200, {
                    items: [
                        {
                            dashboard_id: DASHBOARD_ID,
                            project_id: PROJECT_ID,
                            name: "Ops board",
                            tiles: [],
                            version: 1,
                        },
                    ],
                }),
        ],
    ])

    const element = new PycDashboardsList()
    document.body.appendChild(element)
    await element.loadProjects()
    await _flush()

    const table = element.querySelector('[data-role="dashboards-table"]')
    assert.ok(table !== null)
    const link = table.shadowRoot.querySelector(".pyc-metrics__row-link")
    assert.equal(link.getAttribute("href"), "/dashboards/" + DASHBOARD_ID)
    assert.ok(link.textContent.includes("Ops board"))
    element.remove()
})

test("pyc-dashboards-list submitCreate POSTs and reports outcome", async () => {
    if (customElements.get("pyc-dashboards-list") === undefined) {
        customElements.define("pyc-dashboards-list", PycDashboardsList)
    }
    let posted_body = null
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () =>
                _json_response(200, {
                    items: [
                        { project_id: PROJECT_ID, display_name: "Proj" },
                    ],
                }),
        ],
        [
            (url, options) =>
                url.includes("/dashboards") &&
                options !== undefined &&
                options.method === "POST",
            (url, options) => {
                posted_body = JSON.parse(options.body)
                return _json_response(201, {
                    dashboard_id: DASHBOARD_ID,
                    project_id: PROJECT_ID,
                    name: posted_body.name,
                    tiles: [],
                    version: 1,
                })
            },
        ],
        [
            (url) => url.includes("/dashboards"),
            () => _json_response(200, { items: [] }),
        ],
    ])

    const element = new PycDashboardsList()
    document.body.appendChild(element)
    await element.loadProjects()
    await _flush()

    const outcome = await element.submitCreate("New Board", "desc")
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 201)
    assert.equal(outcome.dashboardId, DASHBOARD_ID)
    assert.equal(posted_body.name, "New Board")
    assert.equal(posted_body.description, "desc")
    element.remove()
})

// ---------------------------------------------------------------
// <pyc-dashboard-detail> element
// ---------------------------------------------------------------

test("pyc-dashboard-detail renders one tile per dashboard tile", async () => {
    if (customElements.get("pyc-dashboard-detail") === undefined) {
        customElements.define("pyc-dashboard-detail", PycDashboardDetail)
    }
    dom.reconfigure({ url: "https://example.test/dashboards/" + DASHBOARD_ID })
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () =>
                _json_response(200, {
                    items: [
                        { project_id: PROJECT_ID, display_name: "Proj" },
                    ],
                }),
        ],
        [
            (url) => url.includes("/dashboards/" + DASHBOARD_ID),
            () =>
                _json_response(200, {
                    dashboard_id: DASHBOARD_ID,
                    project_id: PROJECT_ID,
                    name: "Ops board",
                    tiles: [
                        {
                            tile_id: "t1",
                            kind: "chart",
                            x: 0,
                            y: 0,
                            w: 2,
                            h: 2,
                            config: { metric: "http_requests" },
                        },
                        {
                            tile_id: "t2",
                            kind: "note",
                            x: 2,
                            y: 0,
                            w: 1,
                            h: 1,
                        },
                    ],
                    version: 1,
                }),
        ],
        [
            (url) => url.includes("/metrics/timeseries"),
            () =>
                _json_response(200, {
                    metric: "http_requests",
                    points: [
                        { observed_at: "2026-05-20T10:00:00Z", value: 2 },
                        { observed_at: "2026-05-20T11:00:00Z", value: 4 },
                    ],
                }),
        ],
    ])

    const element = new PycDashboardDetail()
    document.body.appendChild(element)
    await element.loadDashboard()
    await _flush()

    const tiles = element.querySelectorAll('[data-role="dashboard-tile"]')
    assert.equal(tiles.length, 2)
    const heading = element.querySelector('[data-role="dashboard-heading"]')
    assert.equal(heading.textContent, "Ops board")
    assert.equal(element.loaded, true)
    // The metric tile resolves to a chart; the note tile does not.
    const charts = element.querySelectorAll('[data-role="timeseries-chart"]')
    assert.equal(charts.length, 1)
    dom.reconfigure({ url: "https://example.test/test-metrics" })
    element.remove()
})
