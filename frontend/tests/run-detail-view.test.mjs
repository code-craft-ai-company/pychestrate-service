/**
 * Unit tests for the pyc-runs-bundle run detail view.
 *
 * Covers the pure path/id/progress/artifact helpers and the
 * ``<pyc-run-detail>`` Custom Element's initial fetch + render,
 * live SSE event handling, and EventSource cleanup on unmount.
 * Driven against a jsdom document with a stubbed ``fetch`` and a
 * stubbed ``EventSource``.
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

const RUN_ID = "11111111-2222-3333-4444-555555555555"

const { dom } = await setup_jsdom_with_mj({
    url: "https://example.test/runs/" + RUN_ID,
})

/**
 * Minimal scriptable EventSource stand-in. Tracks open/closed
 * state and exposes ``emit`` / ``triggerOpen`` / ``triggerError``
 * so tests can drive the run detail view's stream handlers.
 */
class FakeEventSource {
    static instances = []

    constructor(url, init) {
        this.url = url
        this.init = init
        this.closed = false
        this.onopen = null
        this.onmessage = null
        this.onerror = null
        FakeEventSource.instances.push(this)
    }

    close() {
        this.closed = true
    }

    triggerOpen() {
        if (this.onopen !== null) {
            this.onopen({})
        }
    }

    emit(payload) {
        if (this.onmessage !== null) {
            this.onmessage({ data: JSON.stringify(payload) })
        }
    }

    triggerError() {
        if (this.onerror !== null) {
            this.onerror({})
        }
    }
}

globalThis.EventSource = FakeEventSource

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    PycRunDetail,
    run_id_from_path,
    is_valid_run_id,
    is_terminal_state,
    progress_percent,
    manifest_artifacts,
    artifact_url,
} = bundle

function _make_run(overrides) {
    const base = {
        run_id: RUN_ID,
        project_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        pod_id: "99999999-8888-7777-6666-555555555555",
        job_type: "test",
        state: "running",
        created_at: "2026-05-17T10:00:00Z",
        dispatched_at: "2026-05-17T10:00:30Z",
        started_at: "2026-05-17T10:01:00Z",
        completed_at: null,
        terminal_outcome: null,
        current_dispatch_attempt_id: "dddddddd-0000-0000-0000-000000000001",
    }
    return Object.assign(base, overrides)
}

function _install_fetch(run_payload, ok = true, status = 200) {
    const calls = []
    globalThis.fetch = async (url, options) => {
        calls.push({ url, options })
        return {
            ok: ok,
            status: status,
            json: async () => run_payload,
        }
    }
    return calls
}

test("run_id_from_path extracts the run id segment", () => {
    assert.equal(run_id_from_path("/runs/" + RUN_ID), RUN_ID)
    assert.equal(run_id_from_path("/runs/" + RUN_ID + "/artifacts"), RUN_ID)
    assert.equal(run_id_from_path("/runs"), "")
    assert.equal(run_id_from_path("/admin"), "")
})

test("is_valid_run_id only accepts canonical UUIDs", () => {
    assert.equal(is_valid_run_id(RUN_ID), true)
    assert.equal(is_valid_run_id("not-a-uuid"), false)
    assert.equal(is_valid_run_id(""), false)
})

test("is_terminal_state classifies terminal states", () => {
    assert.equal(is_terminal_state("completed"), true)
    assert.equal(is_terminal_state("failed"), true)
    assert.equal(is_terminal_state("running"), false)
})

test("progress_percent prefers percent_complete then falls back to ratio", () => {
    assert.equal(progress_percent({ percent_complete: 42, tests_passed: 0, tests_failed: 0, tests_skipped: 0, tests_errored: 0 }), 42)
    const ratio = progress_percent({ percent_complete: null, tests_total: 10, tests_passed: 3, tests_failed: 2, tests_skipped: 0, tests_errored: 0 })
    assert.equal(ratio, 50)
})

test("manifest_artifacts surfaces testsummary.html first", () => {
    const artifacts = manifest_artifacts({
        html_summary_artifact_path: "testsummary.html",
        summary_artifact_path: "testrun_summary.json",
    })
    assert.equal(artifacts[0].path, "testsummary.html")
    assert.equal(artifacts.length, 2)
})

test("artifact_url builds an encoded artifact resource path", () => {
    const url = artifact_url(RUN_ID, "diagnostics/log.txt")
    assert.equal(url, "/api/v1/runs/" + RUN_ID + "/artifacts/diagnostics/log.txt")
})

test("PycRunDetail fetches the run on connect and renders the summary", async () => {
    FakeEventSource.instances = []
    const calls = _install_fetch(_make_run({}))

    const element = new PycRunDetail()
    element.setAttribute("run-id", RUN_ID)
    document.body.appendChild(element)
    await element.load()

    assert.equal(calls[0].url, "/api/v1/runs/" + RUN_ID)
    assert.equal(calls[0].options.credentials, "same-origin")

    const badge = element.querySelector('[data-role="state-badge"]')
    assert.equal(badge.textContent, "running")
    const run_id_el = element.querySelector('[data-role="run-id"]')
    assert.equal(run_id_el.textContent, "11111111")
    const attempt = element.querySelector('[data-role="dispatch-attempt"]')
    assert.equal(attempt.textContent, "dddddddd-0000-0000-0000-000000000001")

    // A non-terminal run opens the live SSE stream.
    assert.equal(FakeEventSource.instances.length, 1)
    assert.equal(
        FakeEventSource.instances[0].url,
        "/api/v1/runs/" + RUN_ID + "/events",
    )
    element.remove()
})

test("PycRunDetail renders the error state when the fetch fails", async () => {
    FakeEventSource.instances = []
    _install_fetch({}, false, 500)

    const element = new PycRunDetail()
    element.setAttribute("run-id", RUN_ID)
    document.body.appendChild(element)
    await element.load()

    const error = element.querySelector('[data-role="error-state"]')
    assert.notEqual(error, null)
    assert.equal(element.detailState.errored, true)
    assert.equal(FakeEventSource.instances.length, 0)
    element.remove()
})

test("PycRunDetail refuses an invalid run id without a network call", async () => {
    let fetched = false
    globalThis.fetch = async () => {
        fetched = true
        return { ok: true, status: 200, json: async () => ({}) }
    }

    const element = new PycRunDetail()
    element.setAttribute("run-id", "not-a-uuid")
    document.body.appendChild(element)
    await element.load()

    assert.equal(fetched, false)
    assert.equal(element.detailState.errored, true)
    element.remove()
})

test("a state_changed SSE event updates the badge and timestamps", async () => {
    FakeEventSource.instances = []
    _install_fetch(_make_run({}))

    const element = new PycRunDetail()
    element.setAttribute("run-id", RUN_ID)
    document.body.appendChild(element)
    await element.load()

    const source = FakeEventSource.instances[0]
    source.triggerOpen()
    source.emit({
        run_id: RUN_ID,
        event_type: "state_changed",
        sequence: 1,
        occurred_at: "2026-05-17T10:05:00Z",
        state: "completed",
        terminal_outcome: "passed",
    })

    const badge = element.querySelector('[data-role="state-badge"]')
    assert.equal(badge.textContent, "completed")
    const outcome = element.querySelector('[data-role="terminal-outcome"]')
    assert.equal(outcome.textContent, "passed")

    // A terminal transition closes the stream.
    assert.equal(source.closed, true)
    assert.equal(element.detailState.streamStatus, "closed")
    element.remove()
})

test("a progress SSE event renders the progress section", async () => {
    FakeEventSource.instances = []
    _install_fetch(_make_run({}))

    const element = new PycRunDetail()
    element.setAttribute("run-id", RUN_ID)
    document.body.appendChild(element)
    await element.load()

    const source = FakeEventSource.instances[0]
    source.emit({
        run_id: RUN_ID,
        event_type: "progress",
        sequence: 2,
        occurred_at: "2026-05-17T10:03:00Z",
        progress: {
            tests_total: 20,
            tests_passed: 8,
            tests_failed: 2,
            tests_skipped: 0,
            tests_errored: 0,
            percent_complete: 50,
            recorded_at: "2026-05-17T10:03:00Z",
        },
    })

    const bar = element.querySelector('[data-role="progress-bar"]')
    assert.equal(bar.getAttribute("aria-valuenow"), "50")
    const counts = element.querySelectorAll(".pyc-run-detail__count")
    assert.equal(counts.length >= 4, true)
    element.remove()
})

test("a result_manifest SSE event renders the artifacts section", async () => {
    FakeEventSource.instances = []
    _install_fetch(_make_run({}))

    const element = new PycRunDetail()
    element.setAttribute("run-id", RUN_ID)
    document.body.appendChild(element)
    await element.load()

    const source = FakeEventSource.instances[0]
    source.emit({
        run_id: RUN_ID,
        event_type: "result_manifest",
        sequence: 3,
        occurred_at: "2026-05-17T10:10:00Z",
        manifest: {
            backend_key_prefix: "runs/" + RUN_ID,
            completed_at: "2026-05-17T10:10:00Z",
            terminal_outcome: "passed",
            html_summary_artifact_path: "testsummary.html",
            summary_artifact_path: "testrun_summary.json",
            tests_passed: 18,
            tests_failed: 2,
        },
    })

    const summary_link = element.querySelector('[data-role="summary-link"]')
    assert.notEqual(summary_link, null)
    assert.equal(
        summary_link.getAttribute("href"),
        "/api/v1/runs/" + RUN_ID + "/artifacts/testsummary.html",
    )
    const rollup = element.querySelector('[data-role="artifacts-rollup"]')
    assert.equal(rollup.textContent.includes("18 passed"), true)
    element.remove()
})

test("a heartbeat SSE event is a no-op", async () => {
    FakeEventSource.instances = []
    _install_fetch(_make_run({}))

    const element = new PycRunDetail()
    element.setAttribute("run-id", RUN_ID)
    document.body.appendChild(element)
    await element.load()

    const source = FakeEventSource.instances[0]
    source.emit({
        run_id: RUN_ID,
        event_type: "heartbeat",
        sequence: 4,
        occurred_at: "2026-05-17T10:04:00Z",
    })
    assert.equal(source.closed, false)
    assert.equal(element.detailState.terminal, false)
    element.remove()
})

test("an SSE error surfaces a reconnecting banner for a live run", async () => {
    FakeEventSource.instances = []
    _install_fetch(_make_run({}))

    const element = new PycRunDetail()
    element.setAttribute("run-id", RUN_ID)
    document.body.appendChild(element)
    await element.load()

    const source = FakeEventSource.instances[0]
    source.triggerError()

    const banner = element.querySelector('[data-role="stream-banner"]')
    assert.equal(banner.hidden, false)
    assert.equal(element.detailState.streamStatus, "reconnecting")
    element.remove()
})

test("PycRunDetail closes the EventSource on disconnect", async () => {
    FakeEventSource.instances = []
    _install_fetch(_make_run({}))

    const element = new PycRunDetail()
    element.setAttribute("run-id", RUN_ID)
    document.body.appendChild(element)
    await element.load()

    const source = FakeEventSource.instances[0]
    assert.equal(source.closed, false)
    element.remove()
    assert.equal(source.closed, true)
})

test("a terminal run does not open an SSE stream", async () => {
    FakeEventSource.instances = []
    _install_fetch(_make_run({ state: "completed", terminal_outcome: "passed", completed_at: "2026-05-17T10:10:00Z" }))

    const element = new PycRunDetail()
    element.setAttribute("run-id", RUN_ID)
    document.body.appendChild(element)
    await element.load()

    assert.equal(FakeEventSource.instances.length, 0)
    assert.equal(element.detailState.terminal, true)
    element.remove()
})
