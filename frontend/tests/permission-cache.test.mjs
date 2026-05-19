/**
 * Unit tests for the PermissionCache diff events, TTL dedup, and
 * 401 transition (M2 / PR5).
 *
 * Drives the cache against a stubbed ``globalThis.fetch`` so the
 * tests run under Node.
 */

import { test } from "node:test"
import assert from "node:assert/strict"
import * as path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

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
    "dist",
    "pyc-site-shell.js",
)

globalThis.customElements = {
    define: () => {},
    get: () => undefined,
}
globalThis.HTMLElement = class HTMLElement {}
globalThis.window = { location: { pathname: "/" } }

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const { PermissionCache } = bundle

function _build_response(status, payload) {
    const response = {
        status,
        ok: status >= 200 && status < 300,
        json: async () => payload,
    }
    return response
}

function _install_fetch_sequence(sequence) {
    let index = 0
    globalThis.fetch = async () => {
        if (index >= sequence.length) {
            throw new Error("fetch_called_too_many_times")
        }
        const entry = sequence[index]
        index = index + 1
        if (entry instanceof Error) {
            throw entry
        }
        return entry
    }
}

test("refresh fires permissions-changed listeners with diff", async () => {
    _install_fetch_sequence([
        _build_response(200, { permissions: ["a", "b"] }),
        _build_response(200, { permissions: ["b", "c"] }),
    ])
    const cache = new PermissionCache({ endpoint: "/x" })
    const diffs = []
    cache.onPermissionsChanged((diff) => diffs.push(diff))
    await cache.refresh(true)
    await cache.refresh(true)
    assert.equal(diffs.length, 2)
    assert.deepEqual(diffs[0].added, ["a", "b"])
    assert.deepEqual(diffs[0].removed, [])
    assert.deepEqual(diffs[1].added, ["c"])
    assert.deepEqual(diffs[1].removed, ["a"])
})

test("refresh dedups within TTL when not forced", async () => {
    let calls = 0
    globalThis.fetch = async () => {
        calls = calls + 1
        return _build_response(200, ["x"])
    }
    let now = 0
    const cache = new PermissionCache({
        endpoint: "/x",
        freshnessTtlMs: 1000,
        now: () => now,
    })
    await cache.refresh(true)
    assert.equal(calls, 1)
    now = 500
    await cache.refresh(false)
    assert.equal(calls, 1)
    now = 2000
    await cache.refresh(false)
    assert.equal(calls, 2)
})

test("refresh fires session-401 once per transition", async () => {
    _install_fetch_sequence([
        _build_response(401, null),
        _build_response(401, null),
        _build_response(200, ["a"]),
        _build_response(401, null),
    ])
    const cache = new PermissionCache({ endpoint: "/x" })
    let count = 0
    cache.onSession401(() => {
        count = count + 1
    })
    await cache.refresh(true)
    await cache.refresh(true)
    assert.equal(count, 1)
    await cache.refresh(true)
    await cache.refresh(true)
    assert.equal(count, 2)
})

test("non-401 fetch failure fires fetch-failed and sets degraded", async () => {
    _install_fetch_sequence([
        new Error("network_down"),
        _build_response(200, ["a"]),
    ])
    const cache = new PermissionCache({ endpoint: "/x" })
    let failed = 0
    let succeeded = 0
    cache.onFetchFailed(() => {
        failed = failed + 1
    })
    cache.onFetchSucceeded(() => {
        succeeded = succeeded + 1
    })
    await cache.refresh(true)
    assert.equal(failed, 1)
    assert.equal(cache.degraded, true)
    await cache.refresh(true)
    assert.equal(succeeded, 1)
    assert.equal(cache.degraded, false)
})

test("5xx fires fetch-failed (not session-401)", async () => {
    _install_fetch_sequence([_build_response(500, null)])
    const cache = new PermissionCache({ endpoint: "/x" })
    let failed = 0
    let s401 = 0
    cache.onFetchFailed(() => {
        failed = failed + 1
    })
    cache.onSession401(() => {
        s401 = s401 + 1
    })
    await cache.refresh(true)
    assert.equal(failed, 1)
    assert.equal(s401, 0)
})
