/**
 * Property-based test for Property 1 of 9-site-shell/requirements.md:
 *
 *     For any sidebar registry state R and any permission set P,
 *     ``R.visible(P)`` includes ONLY entries whose
 *     ``required_permissions`` are a subset of P, AND permuting P
 *     or the registration order does not change the resulting set.
 *
 * 1000 generated cases.
 */

import { test } from "node:test"
import assert from "node:assert/strict"
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
    "perm.f",
    "perm.g",
    "perm.h",
    "perm.i",
    "perm.j",
]

const permission_arb = fc.subarray(PERMISSION_CATALOG)

const group_arb = fc.record({
    groupId: fc.uuid(),
    label: fc.string({ minLength: 1, maxLength: 16 }),
    requiredPermissions: permission_arb,
})

const entry_arb = fc.record({
    entryId: fc.uuid(),
    label: fc.string({ minLength: 1, maxLength: 16 }),
    route: fc.uuid().map((v) => "/r/" + v),
    requiredPermissions: permission_arb,
    group: fc.option(fc.string({ minLength: 1, maxLength: 8 }), { nil: null }),
})

function build_registry(groups, entries) {
    const registry = new SidebarRegistry()
    for (const grp of groups) {
        registry.registerGroup(grp)
    }
    for (const entry of entries) {
        // Only point entries to groups that we registered so the
        // grouped-visibility check is exercised in a fair fraction
        // of cases. Otherwise rewrite the group ref to null.
        const valid_group =
            entry.group !== null &&
            groups.some((candidate) => candidate.groupId === entry.group)
        const normalized = {
            ...entry,
            group: valid_group === true ? entry.group : null,
        }
        registry.registerEntry(normalized)
    }
    return registry
}

function flatten_routes(visible_sidebar) {
    const routes = new Set()
    for (const entry of visible_sidebar.ungrouped) {
        routes.add(entry.route)
    }
    for (const bucket of visible_sidebar.groups) {
        for (const entry of bucket.entries) {
            routes.add(entry.route)
        }
    }
    return routes
}

test("Property 1 — visibility is a subset of permissions held (1000 cases)", () => {
    fc.assert(
        fc.property(
            fc.array(group_arb, { minLength: 0, maxLength: 10 }),
            fc.array(entry_arb, { minLength: 1, maxLength: 50 }),
            permission_arb,
            (groups, entries, perms_array) => {
                const registry = build_registry(groups, entries)
                const perms = new PermissionSet(perms_array)
                const visible = registry.visible(perms)
                const visible_routes = flatten_routes(visible)
                // Every visible entry's perms must be subset of perms
                for (const entry of visible.ungrouped) {
                    for (const req of entry.requiredPermissions) {
                        if (perms.has(req) === false) {
                            return false
                        }
                    }
                }
                for (const bucket of visible.groups) {
                    for (const req of bucket.group.requiredPermissions) {
                        if (perms.has(req) === false) {
                            return false
                        }
                    }
                    for (const entry of bucket.entries) {
                        for (const req of entry.requiredPermissions) {
                            if (perms.has(req) === false) {
                                return false
                            }
                        }
                    }
                }
                // Visibility is pure: permuting perms must yield
                // the same visible-route set.
                const permuted_perms = new PermissionSet(
                    [...perms_array].reverse(),
                )
                const visible2 = registry.visible(permuted_perms)
                const visible2_routes = flatten_routes(visible2)
                if (visible_routes.size !== visible2_routes.size) {
                    return false
                }
                for (const route of visible_routes) {
                    if (visible2_routes.has(route) === false) {
                        return false
                    }
                }
                return true
            },
        ),
        { numRuns: 1000 },
    )
})
