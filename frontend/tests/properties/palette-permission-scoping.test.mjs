/**
 * Property-based test for Property 3 of 9-site-shell/requirements.md:
 *
 *     For any palette registry, any caller permission set P, and
 *     any query Q, results from provider X appear in the rendered
 *     output iff ``X.required_permissions`` is a subset of P.
 *
 * 1000 generated cases. Drives the registry's ``queryAll`` API
 * directly because it's the same gating used by the dialog
 * renderer.
 */

import { test } from "node:test"
import * as path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import fc from "fast-check"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const BUNDLE_PATH = path.resolve(
    HERE,
    "..",
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
const { PaletteRegistry, PermissionSet } = bundle

const PERMISSION_CATALOG = [
    "perm.a",
    "perm.b",
    "perm.c",
    "perm.d",
    "perm.e",
]

const provider_arb = fc.record({
    providerId: fc.uuid(),
    label: fc.string({ minLength: 1, maxLength: 12 }),
    requiredPermissions: fc.subarray(PERMISSION_CATALOG),
})

test("Property 3 — palette provider permission scoping (1000 cases)", async () => {
    await fc.assert(
        fc.asyncProperty(
            fc.array(provider_arb, { minLength: 0, maxLength: 15 }),
            fc.subarray(PERMISSION_CATALOG),
            fc.string({ maxLength: 16 }),
            async (provider_specs, perms_array, query) => {
                const registry = new PaletteRegistry()
                for (const spec of provider_specs) {
                    registry.registerProvider({
                        providerId: spec.providerId,
                        label: spec.label,
                        requiredPermissions: spec.requiredPermissions,
                        query: async () => [
                            {
                                id: "result-1",
                                label: "fixture",
                                route: "/x",
                            },
                        ],
                    })
                }
                const perms = new PermissionSet(perms_array)
                const outcomes = await registry.queryAll(query, perms)
                for (const outcome of outcomes) {
                    const spec = provider_specs.find(
                        (cand) => cand.providerId === outcome.providerId,
                    )
                    if (spec === undefined) {
                        return false
                    }
                    for (const req of spec.requiredPermissions) {
                        if (perms.has(req) === false) {
                            return false
                        }
                    }
                }
                // Conversely, every provider whose perms are
                // satisfied MUST appear in outcomes (unless its id
                // was a duplicate that was dropped at registration
                // -- fast-check uuids collide with negligible
                // probability so we treat that as out of scope).
                const visible_ids = new Set(
                    outcomes.map((outcome) => outcome.providerId),
                )
                for (const spec of provider_specs) {
                    const satisfied = spec.requiredPermissions.every(
                        (req) => perms.has(req) === true,
                    )
                    if (satisfied === true && visible_ids.has(spec.providerId) === false) {
                        return false
                    }
                }
                return true
            },
        ),
        { numRuns: 1000 },
    )
})
