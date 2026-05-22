/**
 * Unit tests for the pyc-pipelines-bundle pipelines views.
 *
 * Covers the pure helpers, the ``<pyc-pipelines-list>`` Custom
 * Element's project-select / list fetch / pagination / validate /
 * matrix-expand actions, and the ``<pyc-pipeline-detail>`` DAG
 * layout helper -- driven against a jsdom document and a stubbed
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
    "pyc-pipelines-bundle",
    "index.js",
)

const dom = new JSDOM(
    "<!doctype html><html><head></head><body></body></html>",
    { url: "https://example.test/pipelines" },
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

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycPipelinesList,
    PycPipelineDetail,
    build_pipelines_query_url,
    build_pipelines_collection_url,
    build_pipelines_validate_url,
    build_pipelines_expand_matrix_url,
    short_id,
    has_next_page,
    has_previous_page,
    parse_matrix_spec,
    validate_message_for_status,
    pipeline_id_from_path,
    compute_dag_columns,
    compute_dag_layout,
} = bundle

const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

function _make_pipeline(overrides) {
    const base = {
        pipeline_id: "abc123def456abc123def456abc123def456abc123def456abc123def456abcd",
        project_id: PROJECT_ID,
        name: "example-pipeline",
        schema_version: 1,
        commit_sha: "0000000000000000000000000000000000000000",
        filename: "pipeline.yaml",
        stages: [],
        cached_at: "2026-05-20T10:00:00Z",
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
        return {
            ok: false,
            status: 404,
            json: async () => ({}),
        }
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

// ---- pure helpers ----------------------------------------------

test("build_pipelines_query_url encodes project + pagination", () => {
    const state = {
        projectId: PROJECT_ID,
        page: 2,
        perPage: 10,
        total: 0,
        loading: false,
        errored: false,
    }
    const url = build_pipelines_query_url(state)
    assert.ok(url.includes("/api/v1/projects/" + PROJECT_ID + "/pipelines?"))
    assert.ok(url.includes("page=2"))
    assert.ok(url.includes("per_page=10"))
})

test("build_pipelines action URLs use the project-scoped colon verbs", () => {
    assert.equal(
        build_pipelines_collection_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/pipelines",
    )
    assert.equal(
        build_pipelines_validate_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/pipelines:validate",
    )
    assert.equal(
        build_pipelines_expand_matrix_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/pipelines:expand-matrix",
    )
})

test("short_id trims a digest to a scannable fragment", () => {
    assert.equal(short_id("abc123def456abc123def456"), "abc123def456")
    assert.equal(short_id("11111111-2222"), "11111111")
    assert.equal(short_id(""), "")
})

test("has_next_page / has_previous_page reflect the page cursor", () => {
    const state = {
        projectId: PROJECT_ID,
        page: 1,
        perPage: 25,
        total: 60,
        loading: false,
        errored: false,
    }
    assert.equal(has_next_page(state), true)
    assert.equal(has_previous_page(state), false)
    state.page = 3
    assert.equal(has_next_page(state), false)
    assert.equal(has_previous_page(state), true)
})

test("parse_matrix_spec rejects empty / non-object input", () => {
    assert.throws(() => parse_matrix_spec(""), SyntaxError)
    assert.throws(() => parse_matrix_spec("[1,2]"), SyntaxError)
    const parsed = parse_matrix_spec('{"dimensions": {"os": ["linux"]}}')
    assert.deepEqual(parsed, { dimensions: { os: ["linux"] } })
})

test("validate_message_for_status distinguishes valid / cyclic / errors", () => {
    assert.ok(validate_message_for_status(200, true).includes("valid"))
    assert.ok(validate_message_for_status(200, false).includes("issues"))
    assert.ok(validate_message_for_status(422, false).includes("not a valid"))
})

test("pipeline_id_from_path extracts the detail-route id segment", () => {
    assert.equal(pipeline_id_from_path("/pipelines/abc123"), "abc123")
    assert.equal(pipeline_id_from_path("/pipelines/abc123/x"), "abc123")
    assert.equal(pipeline_id_from_path("/pipelines"), "")
    assert.equal(pipeline_id_from_path("/builds/x"), "")
})

// ---- DAG layout helper -----------------------------------------

test("compute_dag_columns layers a linear chain by longest path", () => {
    const stages = [
        { stage_id: "a", steps: [] },
        { stage_id: "b", needs: ["a"], steps: [] },
        { stage_id: "c", needs: ["b"], steps: [] },
    ]
    const columns = compute_dag_columns(stages)
    assert.equal(columns.isDag, true)
    const by_id = new Map(columns.assignments.map((x) => [x.stageId, x]))
    assert.equal(by_id.get("a").column, 0)
    assert.equal(by_id.get("b").column, 1)
    assert.equal(by_id.get("c").column, 2)
})

test("compute_dag_columns places a diamond's join at the deepest depth", () => {
    const stages = [
        { stage_id: "root", steps: [] },
        { stage_id: "left", needs: ["root"], steps: [] },
        { stage_id: "right", needs: ["root"], steps: [] },
        { stage_id: "join", needs: ["left", "right"], steps: [] },
    ]
    const columns = compute_dag_columns(stages)
    assert.equal(columns.isDag, true)
    const by_id = new Map(columns.assignments.map((x) => [x.stageId, x]))
    assert.equal(by_id.get("root").column, 0)
    assert.equal(by_id.get("left").column, 1)
    assert.equal(by_id.get("right").column, 1)
    assert.equal(by_id.get("join").column, 2)
    // The two column-1 stages get distinct rows.
    assert.notEqual(by_id.get("left").row, by_id.get("right").row)
})

test("compute_dag_columns flags a dependency cycle as not-a-DAG", () => {
    const stages = [
        { stage_id: "a", needs: ["b"], steps: [] },
        { stage_id: "b", needs: ["a"], steps: [] },
    ]
    const columns = compute_dag_columns(stages)
    assert.equal(columns.isDag, false)
    assert.equal(columns.assignments.length, 0)
})

test("compute_dag_layout produces node boxes and one edge per need", () => {
    const stages = [
        { stage_id: "a", steps: [] },
        { stage_id: "b", needs: ["a"], steps: [] },
    ]
    const layout = compute_dag_layout(stages)
    assert.equal(layout.isDag, true)
    assert.equal(layout.nodes.length, 2)
    assert.equal(layout.edges.length, 1)
    const node_a = layout.nodes.find((n) => n.stageId === "a")
    const node_b = layout.nodes.find((n) => n.stageId === "b")
    // b sits to the right of a.
    assert.ok(node_b.x > node_a.x)
    // The edge runs a -> b.
    assert.equal(layout.edges[0].fromStageId, "b")
    assert.equal(layout.edges[0].toStageId, "a")
    assert.ok(layout.width > 0)
    assert.ok(layout.height > 0)
})

// ---- list view: fetch + pagination -----------------------------

test("list view fetches a pipelines page after a project is chosen", async () => {
    const calls = _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, { items: [{ project_id: PROJECT_ID }] }),
        ],
        [
            (url) => url.includes("/pipelines?"),
            () => _json_response(200, {
                items: [_make_pipeline({})],
                meta: { page: 1, per_page: 25, total: 1 },
            }),
        ],
    ])

    const view = new PycPipelinesList()
    document.body.appendChild(view)
    await view.loadProjects()

    const state = view.listState
    assert.equal(state.projectId, PROJECT_ID)
    assert.equal(state.total, 1)
    assert.equal(state.errored, false)
    const list_call = calls.find((c) => c.url.includes("/pipelines?"))
    assert.ok(list_call !== undefined)
    const rows = view.querySelectorAll(".pyc-pipelines__row")
    assert.equal(rows.length, 1)
    view.remove()
})

test("list view surfaces an error state on a failed list fetch", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, { items: [{ project_id: PROJECT_ID }] }),
        ],
        [
            (url) => url.includes("/pipelines?"),
            () => _json_response(500, {}),
        ],
    ])

    const view = new PycPipelinesList()
    document.body.appendChild(view)
    await view.loadProjects()

    assert.equal(view.listState.errored, true)
    const error = view.querySelector('[data-role="error-state"]')
    assert.ok(error !== null)
    view.remove()
})

// ---- list view: validate action --------------------------------

test("validate action shows the topological order for a valid DAG", async () => {
    _install_router([
        [
            (url) => url.endsWith("/pipelines:validate"),
            () => _json_response(200, {
                valid: true,
                stage_count: 2,
                topological_order: ["a", "b"],
                issues: [],
            }),
        ],
    ])

    const view = new PycPipelinesList()
    view._state = {
        projectId: PROJECT_ID,
        page: 1,
        perPage: 25,
        total: 0,
        loading: false,
        errored: false,
    }
    const outcome = await view.validatePipeline("sha", "p.yaml", "name: x")
    assert.equal(outcome.ok, true)
    assert.equal(outcome.valid, true)
    assert.deepEqual(outcome.topologicalOrder, ["a", "b"])
    assert.equal(outcome.issues.length, 0)
})

test("validate action reports a cyclic DAG as invalid with issues", async () => {
    _install_router([
        [
            (url) => url.endsWith("/pipelines:validate"),
            () => _json_response(422, {
                valid: false,
                stage_count: 2,
                topological_order: [],
                issues: ["cycle detected: a -> b -> a"],
            }),
        ],
    ])

    const view = new PycPipelinesList()
    view._state = {
        projectId: PROJECT_ID,
        page: 1,
        perPage: 25,
        total: 0,
        loading: false,
        errored: false,
    }
    const outcome = await view.validatePipeline("sha", "p.yaml", "cyclic")
    assert.equal(outcome.ok, false)
    assert.equal(outcome.valid, false)
    assert.equal(outcome.issues.length, 1)
    assert.ok(outcome.issues[0].includes("cycle"))
})

// ---- list view: matrix expand action ---------------------------

test("matrix-expand action returns the shard count and shard list", async () => {
    _install_router([
        [
            (url) => url.endsWith("/pipelines:expand-matrix"),
            () => _json_response(200, {
                strategy_name: "cartesian",
                shard_count: 2,
                shards: [
                    {
                        shard_id: "0000000000000001",
                        parallel_group: "g",
                        sequence_in_group: 0,
                        dimension_values: { os: "linux" },
                    },
                    {
                        shard_id: "0000000000000002",
                        parallel_group: "g",
                        sequence_in_group: 1,
                        dimension_values: { os: "windows" },
                    },
                ],
            }),
        ],
    ])

    const view = new PycPipelinesList()
    view._state = {
        projectId: PROJECT_ID,
        page: 1,
        perPage: 25,
        total: 0,
        loading: false,
        errored: false,
    }
    const outcome = await view.expandMatrix(
        { dimensions: { os: ["linux", "windows"] } },
        "cartesian",
    )
    assert.equal(outcome.ok, true)
    assert.equal(outcome.shardCount, 2)
    assert.equal(outcome.shards.length, 2)
    assert.equal(outcome.strategyName, "cartesian")
})

test("matrix-expand action reports a rejected matrix spec", async () => {
    _install_router([
        [
            (url) => url.endsWith("/pipelines:expand-matrix"),
            () => _json_response(422, {}),
        ],
    ])

    const view = new PycPipelinesList()
    view._state = {
        projectId: PROJECT_ID,
        page: 1,
        perPage: 25,
        total: 0,
        loading: false,
        errored: false,
    }
    const outcome = await view.expandMatrix({ dimensions: {} }, "")
    assert.equal(outcome.ok, false)
    assert.equal(outcome.status, 422)
    assert.ok(outcome.message.includes("rejected"))
})

// ---- detail view: DAG render -----------------------------------

test("detail view renders the SVG DAG for a valid pipeline", async () => {
    _install_router([
        [
            (url) => url.includes("/pipelines/"),
            () => _json_response(200, _make_pipeline({
                stages: [
                    { stage_id: "build", steps: [] },
                    { stage_id: "test", needs: ["build"], steps: [] },
                ],
            })),
        ],
    ])

    const detail = new PycPipelineDetail()
    detail.setAttribute("pipeline-id", "abc123")
    document.body.appendChild(detail)
    await detail.load()

    assert.equal(detail.detailState.errored, false)
    assert.equal(detail.detailState.isDag, true)
    const nodes = detail.querySelectorAll('[data-role="dag-node"]')
    assert.equal(nodes.length, 2)
    const edges = detail.querySelectorAll('[data-role="dag-edge"]')
    assert.equal(edges.length, 1)
    detail.remove()
})

test("detail view falls back to the adjacency list for a cyclic DAG", async () => {
    _install_router([
        [
            (url) => url.includes("/pipelines/"),
            () => _json_response(200, _make_pipeline({
                stages: [
                    { stage_id: "a", needs: ["b"], steps: [] },
                    { stage_id: "b", needs: ["a"], steps: [] },
                ],
            })),
        ],
    ])

    const detail = new PycPipelineDetail()
    detail.setAttribute("pipeline-id", "abc123")
    document.body.appendChild(detail)
    await detail.load()

    assert.equal(detail.detailState.isDag, false)
    const adjacency = detail.querySelector('[data-role="dag-adjacency"]')
    assert.ok(adjacency !== null)
    const cycle_notice = detail.querySelector('[data-role="dag-cycle-notice"]')
    assert.ok(cycle_notice !== null)
    detail.remove()
})
