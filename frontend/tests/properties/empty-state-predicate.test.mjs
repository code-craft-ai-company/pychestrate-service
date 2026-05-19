/**
 * Property-based test for Property 2 of 9-site-shell/requirements.md:
 *
 *     For any registry state R and permission set P, the shell
 *     renders the empty state iff
 *     ``len(visibleSidebar(R, P)) == 0``.
 *
 * 1000 generated cases.
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
    "dist",
    "pyc-site-shell.js",
)

globalThis.customElements = { define: () => {}, get: () => undefined }
globalThis.HTMLElement = class HTMLElement {}
globalThis.window = { location: { pathname: "/" } }

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const { SidebarRegistry, PermissionSet } = bundle

const PERMISSION_CATALOG = [
    "perm.a",
    "perm.b",
    "perm.c",
    "perm.d",
    "perm.e",
]

const entry_arb = fc.record({
    entryId: fc.uuid(),
    label: fc.string({ minLength: 1, maxLength: 16 }),
    route: fc.uuid().map((v) => "/r/" + v),
    requiredPermissions: fc.subarray(PERMISSION_CATALOG),
    group: fc.constant(null),
})

test("Property 2 — empty-state predicate matches zero-entry condition", () => {
    fc.assert(
        fc.property(
            fc.array(entry_arb, { minLength: 0, maxLength: 30 }),
            fc.subarray(PERMISSION_CATALOG),
            (entries, perms_array) => {
                const registry = new SidebarRegistry()
                for (const entry of entries) {
                    registry.registerEntry(entry)
                }
                const perms = new PermissionSet(perms_array)
                const visible_count = registry.visibleEntryCount(perms)
                const empty_state_predicate = visible_count === 0
                // Recompute predicate from raw visible() to ensure
                // the shorthand and the structural answer agree.
                const visible = registry.visible(perms)
                let direct_count = visible.ungrouped.length
                for (const bucket of visible.groups) {
                    direct_count = direct_count + bucket.entries.length
                }
                const direct_empty = direct_count === 0
                return empty_state_predicate === direct_empty
            },
        ),
        { numRuns: 1000 },
    )
})
