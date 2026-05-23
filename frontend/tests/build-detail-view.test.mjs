/**
 * Unit tests for the pyc-builds-bundle build detail view.
 *
 * Covers the pure path/id/url helpers and the ``<pyc-build-detail>``
 * Custom Element's initial fetch + render, artifacts rendering, and
 * the live-poll lifecycle (poll while non-terminal, stop on
 * terminal, stop on unmount). Driven against a jsdom document with
 * a stubbed ``fetch`` -- poll cycles are advanced explicitly via
 * the ``pollOnce`` test hook rather than waiting on a real timer.
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
    "pyc-builds-bundle",
    "index.js",
)

const BUILD_ID = "11111111-2222-3333-4444-555555555555"
const PROJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/builds/" + BUILD_ID,
})

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycBuildDetail,
    build_id_from_path,
    is_valid_build_id,
    build_detail_url,
    build_artifacts_url,
} = bundle

function _make_build(overrides) {
    const base = {
        run_id: BUILD_ID,
        project_id: PROJECT_ID,
        runner_kind: "makefile",
        repro_digest_sha256: "abc123def456abc123def456",
        state: "running",
        started_at: "2026-05-20T10:00:00Z",
        finished_at: null,
        toolchain: [{ key: "gcc", version: "13.2" }],
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

test("build_id_from_path extracts the build segment", () => {
    assert.equal(build_id_from_path("/builds/" + BUILD_ID), BUILD_ID)
    assert.equal(build_id_from_path("/builds/" + BUILD_ID + "?x=1"), BUILD_ID)
    assert.equal(build_id_from_path("/builds"), "")
    assert.equal(build_id_from_path("/runs/" + BUILD_ID), "")
})

test("is_valid_build_id validates uuid shape", () => {
    assert.equal(is_valid_build_id(BUILD_ID), true)
    assert.equal(is_valid_build_id("not-a-uuid"), false)
    assert.equal(is_valid_build_id(""), false)
})

test("build_detail_url + build_artifacts_url shapes", () => {
    assert.equal(
        build_detail_url(PROJECT_ID, BUILD_ID),
        "/api/v1/projects/" + PROJECT_ID + "/builds/" + BUILD_ID,
    )
    assert.equal(
        build_artifacts_url(PROJECT_ID, BUILD_ID),
        "/api/v1/projects/" + PROJECT_ID + "/builds/" + BUILD_ID + "/artifacts",
    )
})

test("build detail fetches build + artifacts and renders summary", async () => {
    _install_router([
        [
            (url) => url.startsWith("/api/v1/builds/"),
            () => _json_response(200, _make_build({ state: "completed",
                finished_at: "2026-05-20T10:05:00Z" })),
        ],
        [
            (url) => url.includes("/artifacts"),
            () => _json_response(200, {
                items: [{
                    manifest_id: "m1",
                    artifact_id: "art-1",
                    artifact_type: "binary",
                    artifact_name: "app.tar.gz",
                    storage_uri: "https://store.test/app.tar.gz",
                    sha256: "deadbeefdeadbeefdeadbeef",
                }],
                manifest_id: "m1",
            }),
        ],
    ])

    if (customElements.get("pyc-build-detail") === undefined) {
        customElements.define("pyc-build-detail", PycBuildDetail)
    }
    const el = new PycBuildDetail()
    el.setAttribute("build-id", BUILD_ID)
    document.body.appendChild(el)
    await el.load()

    const badge = el.querySelector('[data-role="state-badge"]')
    assert.equal(badge.textContent, "completed")
    assert.equal(el.detailState.projectId, PROJECT_ID)
    assert.equal(el.detailState.terminal, true)
    assert.equal(el.detailState.pollStatus, "stopped")
    const artifacts = el.querySelectorAll(".pyc-build-detail__artifact")
    assert.equal(artifacts.length, 1)
    el.remove()
})

test("build detail renders empty artifacts state", async () => {
    _install_router([
        [
            (url) => url.startsWith("/api/v1/builds/"),
            () => _json_response(200, _make_build({ state: "completed" })),
        ],
        [
            (url) => url.includes("/artifacts"),
            () => _json_response(200, { items: [], manifest_id: null }),
        ],
    ])
    const el = new PycBuildDetail()
    el.setAttribute("build-id", BUILD_ID)
    document.body.appendChild(el)
    await el.load()

    const empty = el.querySelector('[data-role="artifacts-empty"]')
    assert.ok(empty !== null)
    el.remove()
})

test("build detail polls while non-terminal then stops on terminal", async () => {
    let build_state = "running"
    _install_router([
        [
            (url) => url.startsWith("/api/v1/builds/") ||
                url.includes("/builds/" + BUILD_ID + "?") ||
                url.endsWith("/builds/" + BUILD_ID),
            () => _json_response(200, _make_build({ state: build_state })),
        ],
        [
            (url) => url.includes("/artifacts"),
            () => _json_response(200, { items: [] }),
        ],
    ])

    const el = new PycBuildDetail()
    el.setAttribute("build-id", BUILD_ID)
    document.body.appendChild(el)
    await el.load()
    assert.equal(el.detailState.pollStatus, "polling")
    assert.equal(el.detailState.terminal, false)

    // First poll cycle -- still running, keeps polling.
    await el.pollOnce()
    assert.equal(el.detailState.pollStatus, "polling")

    // Build finishes -- next poll cycle transitions to terminal.
    build_state = "completed"
    await el.pollOnce()
    assert.equal(el.detailState.terminal, true)
    assert.equal(el.detailState.pollStatus, "stopped")
    el.remove()
})

test("build detail errors on an invalid build id without a fetch", async () => {
    let fetched = false
    _install_router([
        [() => { fetched = true; return true }, () => _json_response(500, {})],
    ])
    const el = new PycBuildDetail()
    el.setAttribute("build-id", "not-a-uuid")
    document.body.appendChild(el)
    await el.load()

    assert.equal(fetched, false)
    assert.equal(el.detailState.errored, true)
    const error = el.querySelector('[data-role="error-state"]')
    assert.ok(error !== null)
    el.remove()
})

test("build detail unmount stops the poll loop", async () => {
    _install_router([
        [
            (url) => url.includes("/builds/"),
            () => _json_response(200, _make_build({ state: "running" })),
        ],
        [
            (url) => url.includes("/artifacts"),
            () => _json_response(200, { items: [] }),
        ],
    ])
    const el = new PycBuildDetail()
    el.setAttribute("build-id", BUILD_ID)
    document.body.appendChild(el)
    await el.load()
    assert.equal(el.detailState.pollStatus, "polling")

    el.remove()
    // disconnectedCallback cleared the timer; no assertion beyond
    // not throwing -- a leaked timer would keep the process alive.
})
