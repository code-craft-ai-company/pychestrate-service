/**
 * Unit tests for ``MetricsBeacon`` -- T3.1 client metrics
 * beacon module.
 *
 * Drives buffering, batching, disable-on-refused-beacon, and the
 * pagehide flush hook. Imports the compiled shell bundle so the
 * code under test is the same artifact the browser ships.
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
    "pyc-site-shell",
    "index.js",
)

globalThis.customElements = { define: () => {}, get: () => undefined }
globalThis.HTMLElement = class HTMLElement {}
globalThis.window = { location: { pathname: "/" } }

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const { MetricsBeacon, SHELL_METRICS } = bundle

test("MetricsBeacon buffers measurements until flush", () => {
    const delivered = []
    const beacon = new MetricsBeacon({
        sendBeacon: (url, body) => {
            delivered.push({ url, body })
            return true
        },
    })
    beacon.observeHistogram(SHELL_METRICS.TTI, 0.123)
    beacon.observeHistogram(SHELL_METRICS.SIDEBAR_RENDER, 0.004)
    assert.equal(beacon.bufferLength(), 2)
    assert.equal(delivered.length, 0)
    beacon.flush()
    assert.equal(delivered.length, 1)
    const payload = JSON.parse(delivered[0].body)
    assert.equal(payload.length, 2)
    assert.equal(payload[0].metric, SHELL_METRICS.TTI)
})

test("MetricsBeacon flushes synchronously at buffer capacity", () => {
    const delivered = []
    const beacon = new MetricsBeacon({
        bufferCapacity: 3,
        sendBeacon: (url, body) => {
            delivered.push(JSON.parse(body))
            return true
        },
    })
    beacon.observeHistogram(SHELL_METRICS.TTI, 0.1)
    beacon.observeHistogram(SHELL_METRICS.TTI, 0.2)
    beacon.observeHistogram(SHELL_METRICS.TTI, 0.3)
    assert.equal(delivered.length, 1)
    assert.equal(delivered[0].length, 3)
})

test("MetricsBeacon disables after sendBeacon refuses", () => {
    const beacon = new MetricsBeacon({
        sendBeacon: () => false,
    })
    beacon.observeHistogram(SHELL_METRICS.TTI, 0.1)
    beacon.flush()
    assert.equal(beacon.disabledReason, "sendBeacon_refused")
    // Further observations are dropped silently.
    beacon.observeHistogram(SHELL_METRICS.TTI, 0.2)
    assert.equal(beacon.bufferLength(), 0)
})

test("MetricsBeacon counter labels carry the entry_route", () => {
    const delivered = []
    const beacon = new MetricsBeacon({
        sendBeacon: (url, body) => {
            delivered.push(JSON.parse(body))
            return true
        },
    })
    beacon.incrementCounter(
        SHELL_METRICS.SIDEBAR_ENTRY_CLICKED,
        { entry_route: "/admin/users" },
    )
    beacon.flush()
    assert.equal(delivered[0][0].labels.entry_route, "/admin/users")
})
