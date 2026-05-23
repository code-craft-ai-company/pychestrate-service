/**
 * Unit tests for the pyc-infra-bundle provisioning views.
 *
 * Covers the pure helpers, the ``<pyc-provisioning-list>`` Custom
 * Element's project-select / fetch / pagination / trigger action,
 * and the ``<pyc-provisioning-detail>`` view's fetch + poll loop
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

const RUN_ID = "11111111-2222-3333-4444-555555555555"
const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/provisioning-runs",
})
globalThis.HTMLFormElement = dom.window.HTMLFormElement
globalThis.HTMLTableElement = dom.window.HTMLTableElement

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycProvisioningList,
    PycProvisioningDetail,
    build_provisioning_query_url,
    build_provisioning_collection_url,
    build_provisioning_detail_link,
    build_provisioning_detail_url,
    provisioning_state_tone,
    is_terminal_provisioning_state,
    trigger_message_for_status,
    parse_driver_inputs,
    run_id_from_path,
    project_id_from_search,
    is_valid_run_id,
} = bundle

function _make_run(overrides) {
    const base = {
        run_id: RUN_ID,
        project_id: PROJECT_ID,
        environment_id: "eeee0000-1111-2222-3333-444444444444",
        driver_name: "terraform",
        action: "apply",
        state: "completed",
        started_at: "2026-05-20T10:00:00Z",
        finished_at: "2026-05-20T10:05:00Z",
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

test("build_provisioning_query_url includes project, state, pagination", () => {
    const url = build_provisioning_query_url({
        projectId: PROJECT_ID,
        stateFilter: "running",
        page: 2,
        perPage: 25,
        total: 0,
        loading: false,
        errored: false,
    })
    assert.ok(
        url.startsWith(
            "/api/v1/projects/" + PROJECT_ID + "/provisioning-runs?",
        ),
    )
    assert.ok(url.includes("state=running"))
    assert.ok(url.includes("page=2"))
    assert.ok(url.includes("per_page=25"))
})

test("provisioning URL + detail-link builders", () => {
    assert.equal(
        build_provisioning_collection_url(PROJECT_ID),
        "/api/v1/projects/" + PROJECT_ID + "/provisioning-runs",
    )
    assert.equal(
        build_provisioning_detail_url(PROJECT_ID, RUN_ID),
        "/api/v1/projects/" + PROJECT_ID + "/provisioning-runs/" + RUN_ID,
    )
    const link = build_provisioning_detail_link(PROJECT_ID, RUN_ID)
    assert.ok(link.startsWith("/provisioning-runs/" + RUN_ID))
    assert.ok(link.includes("project_id=" + PROJECT_ID))
})

test("provisioning_state_tone + is_terminal classify states", () => {
    assert.equal(provisioning_state_tone("completed"), "ok")
    assert.equal(provisioning_state_tone("failed"), "error")
    assert.equal(provisioning_state_tone("rejected_by_guard"), "error")
    assert.equal(provisioning_state_tone("cancelled"), "warn")
    assert.equal(provisioning_state_tone("running"), "neutral")
    assert.equal(is_terminal_provisioning_state("completed"), true)
    assert.equal(is_terminal_provisioning_state("rejected_by_guard"), true)
    assert.equal(is_terminal_provisioning_state("pending"), false)
})

test("trigger_message_for_status maps known statuses", () => {
    assert.equal(
        trigger_message_for_status(202),
        "Provisioning run triggered.",
    )
    assert.ok(trigger_message_for_status(422).includes("rejected"))
    assert.ok(trigger_message_for_status(409).includes("cannot accept"))
    assert.ok(trigger_message_for_status(403).includes("permission"))
})

test("parse_driver_inputs handles empty, object, and invalid", () => {
    assert.deepEqual(parse_driver_inputs(""), {})
    assert.deepEqual(
        parse_driver_inputs('{"auto_approve": false}'),
        { auto_approve: false },
    )
    assert.throws(() => parse_driver_inputs("[1,2]"))
    assert.throws(() => parse_driver_inputs("bad"))
})

test("run_id_from_path + project_id_from_search + is_valid_run_id", () => {
    assert.equal(
        run_id_from_path("/provisioning-runs/" + RUN_ID),
        RUN_ID,
    )
    assert.equal(
        run_id_from_path("/provisioning-runs/" + RUN_ID + "?project_id=x"),
        RUN_ID,
    )
    assert.equal(run_id_from_path("/provisioning-runs"), "")
    assert.equal(run_id_from_path("/builds/abc"), "")
    assert.equal(
        project_id_from_search("?project_id=" + PROJECT_ID),
        PROJECT_ID,
    )
    assert.equal(project_id_from_search(""), "")
    assert.equal(is_valid_run_id(RUN_ID), true)
    assert.equal(is_valid_run_id("not-a-uuid"), false)
})

test("provisioning list fetches projects then runs and renders rows", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url) => url.includes("/environments?"),
            () => _json_response(200, { items: [] }),
        ],
        [
            (url) => url.includes("/provisioning-runs?"),
            () => _json_response(200, {
                items: [
                    _make_run({}),
                    _make_run({
                        run_id: "99999999-8888-7777-6666-555555555555",
                        state: "running",
                        action: "plan",
                    }),
                ],
                meta: { page: 1, per_page: 25, total: 2 },
            }),
        ],
    ])

    if (customElements.get("pyc-provisioning-list") === undefined) {
        customElements.define("pyc-provisioning-list", PycProvisioningList)
    }
    const el = new PycProvisioningList()
    document.body.appendChild(el)
    await el.loadProjects()

    const table = el.querySelector("mj-table.pyc-infra__table")
    const rows = table.shadowRoot.querySelectorAll("tr.pyc-infra__row")
    assert.equal(rows.length, 2)
    assert.equal(el.listState.total, 2)
    const links = table.shadowRoot.querySelectorAll(".pyc-infra__run-link")
    assert.ok(
        links[0].getAttribute("href").startsWith("/provisioning-runs/"),
    )
    assert.ok(links[0].getAttribute("href").includes("project_id="))
    el.remove()
})

test("provisioning list surfaces error state on a failed fetch", async () => {
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url) => url.includes("/environments?"),
            () => _json_response(200, { items: [] }),
        ],
        [
            (url) => url.includes("/provisioning-runs?"),
            () => _json_response(500, {}),
        ],
    ])

    const el = new PycProvisioningList()
    document.body.appendChild(el)
    await el.loadProjects()

    const error = el.querySelector('[data-role="error-state"]')
    assert.ok(error !== null)
    assert.equal(el.listState.errored, true)
    el.remove()
})

test("trigger-provisioning action POSTs the create request", async () => {
    let posted = null
    _install_router([
        [
            (url) => url === "/api/v1/projects",
            () => _json_response(200, {
                items: [{ project_id: PROJECT_ID, display_name: "Demo" }],
            }),
        ],
        [
            (url) => url.includes("/environments?"),
            () => _json_response(200, { items: [] }),
        ],
        [
            (url, options) =>
                url.endsWith("/provisioning-runs") && options &&
                options.method === "POST",
            (url, options) => {
                posted = JSON.parse(options.body)
                return _json_response(202, _make_run({
                    run_id: "abcdabcd-1234-5678-9abc-def012345678",
                    state: "pending",
                }))
            },
        ],
        [
            (url) => url.includes("/provisioning-runs?"),
            () => _json_response(200, {
                items: [],
                meta: { page: 1, per_page: 25, total: 0 },
            }),
        ],
    ])

    const el = new PycProvisioningList()
    document.body.appendChild(el)
    await el.loadProjects()

    const outcome = await el.triggerProvisioning(
        "eeee0000-1111-2222-3333-444444444444",
        "terraform",
        "apply",
        { auto_approve: false },
    )
    assert.equal(outcome.ok, true)
    assert.equal(outcome.status, 202)
    assert.equal(outcome.runId, "abcdabcd-1234-5678-9abc-def012345678")
    assert.equal(
        posted.environment_id,
        "eeee0000-1111-2222-3333-444444444444",
    )
    assert.equal(posted.driver_name, "terraform")
    assert.equal(posted.action, "apply")
    assert.deepEqual(posted.driver_inputs, { auto_approve: false })
    el.remove()
})

test("trigger with no project selected fails gracefully", async () => {
    _install_router([
        [(url) => url === "/api/v1/projects", () => _json_response(404, {})],
    ])
    const el = new PycProvisioningList()
    document.body.appendChild(el)
    await el.loadProjects()

    const outcome = await el.triggerProvisioning("env", "terraform", "plan", {})
    assert.equal(outcome.ok, false)
    assert.ok(outcome.message.includes("Select a project"))
    el.remove()
})

test("provisioning detail loads a run and renders plan summary", async () => {
    _install_router([
        [
            (url) => url.includes("/provisioning-runs/" + RUN_ID),
            () => _json_response(200, _make_run({
                plan_summary: {
                    resources_to_add: 3,
                    resources_to_change: 1,
                    resources_to_destroy: 0,
                    resource_ops: [
                        { resource_address: "aws_instance.web", op: "add" },
                    ],
                },
            })),
        ],
    ])

    if (customElements.get("pyc-provisioning-detail") === undefined) {
        customElements.define(
            "pyc-provisioning-detail",
            PycProvisioningDetail,
        )
    }
    const el = new PycProvisioningDetail()
    el.setAttribute("run-id", RUN_ID)
    el.setAttribute("project-id", PROJECT_ID)
    document.body.appendChild(el)
    await el.load()

    assert.equal(el.detailState.errored, false)
    assert.equal(el.detailState.terminal, true)
    assert.equal(el.detailState.pollStatus, "stopped")
    const plan = el.querySelector('[data-role="plan-summary"]')
    assert.ok(plan !== null)
    const badge = el.querySelector('[data-role="state-badge"]')
    assert.equal(badge.textContent, "completed")
    el.remove()
})

test("provisioning detail polls a non-terminal run until terminal", async () => {
    let run_state = "running"
    _install_router([
        [
            (url) => url.includes("/provisioning-runs/" + RUN_ID),
            () => _json_response(200, _make_run({
                state: run_state,
                finished_at: run_state === "running" ? null : "2026-05-20T10:05:00Z",
            })),
        ],
    ])

    const el = new PycProvisioningDetail()
    el.setAttribute("run-id", RUN_ID)
    el.setAttribute("project-id", PROJECT_ID)
    document.body.appendChild(el)
    await el.load()

    assert.equal(el.detailState.terminal, false)
    assert.equal(el.detailState.pollStatus, "polling")

    // The next poll cycle observes the run reaching a terminal
    // state and stops the live-poll loop.
    run_state = "completed"
    await el.pollOnce()
    assert.equal(el.detailState.terminal, true)
    assert.equal(el.detailState.pollStatus, "stopped")
    el.remove()
})

test("provisioning detail errors when project id is missing", async () => {
    _install_router([])
    const el = new PycProvisioningDetail()
    el.setAttribute("run-id", RUN_ID)
    document.body.appendChild(el)
    await el.load()

    assert.equal(el.detailState.errored, true)
    el.remove()
})
