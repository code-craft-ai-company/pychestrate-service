/**
 * Accessibility audit for `<pyc-site-shell>` (T3.3) -- runs
 * ``axe-core`` against the shell rendered into a jsdom document
 * with a representative permission set. The audit covers:
 *
 *   - The cold-boot shell with header, sidebar, and main region.
 *   - The empty-state panel.
 *   - The open command palette.
 *
 * Outputs a JSON report on stdout. Exits non-zero on any
 * "serious" or "critical" violation per WCAG 2.2 AA.
 *
 * Run with: ``npm run a11y``.
 */

import * as path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { JSDOM } from "jsdom"
import { readFileSync } from "node:fs"
import { createRequire } from "node:module"

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
const CSS_PATH = path.resolve(
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
    "pyc-site-shell.css",
)

const require = createRequire(import.meta.url)
const AXE_PATH = require.resolve("axe-core")
const AXE_SOURCE = readFileSync(AXE_PATH, "utf-8")

const dom = new JSDOM(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Site Shell Axe Audit</title><link rel="stylesheet" href="file://${CSS_PATH}"></head><body></body></html>`,
    { pretendToBeVisual: true, url: "http://localhost/", runScripts: "outside-only" },
)
// Inject axe-core into the jsdom window so its window/document
// references resolve to the jsdom realm.
dom.window.eval(AXE_SOURCE)
const axe = dom.window.axe
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.HTMLAnchorElement = dom.window.HTMLAnchorElement
globalThis.HTMLDivElement = dom.window.HTMLDivElement
globalThis.HTMLInputElement = dom.window.HTMLInputElement
globalThis.customElements = dom.window.customElements
globalThis.CustomEvent = dom.window.CustomEvent
globalThis.KeyboardEvent = dom.window.KeyboardEvent
globalThis.Node = dom.window.Node
if (typeof globalThis.navigator === "undefined") {
    globalThis.navigator = dom.window.navigator
}
Object.defineProperty(globalThis.navigator, "sendBeacon", {
    value: () => true,
    configurable: true,
})

const PERMISSIONS_FIXTURE = [
    "perm.a",
    "perm.b",
    "ui.admin.view",
    "users.read",
]
globalThis.fetch = async () => {
    return {
        ok: true,
        status: 200,
        async json() {
            return { permissions: PERMISSIONS_FIXTURE }
        },
    }
}

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const { PycSiteShell, SidebarRegistry, PermissionSet, PaletteRegistry, PaletteDialog } = bundle

function build_populated_shell() {
    const shell = document.createElement("pyc-site-shell")
    document.body.appendChild(shell)
    shell.sidebar.registerGroup({
        groupId: "workspace",
        label: "Workspace",
        requiredPermissions: [],
    })
    shell.sidebar.registerEntry({
        entryId: "dashboard",
        label: "Dashboard",
        route: "/",
        requiredPermissions: [],
        group: "workspace",
    })
    shell.sidebar.registerGroup({
        groupId: "admin",
        label: "Admin",
        requiredPermissions: ["ui.admin.view"],
    })
    shell.sidebar.registerEntry({
        entryId: "users",
        label: "Users",
        route: "/admin/users",
        requiredPermissions: ["users.read"],
        group: "admin",
    })
    return shell
}

async function wait_ready(shell) {
    if (shell.isReady === true) {
        return
    }
    await new Promise((resolve) => {
        const handler = () => {
            shell.removeEventListener("pyc-site-shell-ready", handler)
            resolve()
        }
        shell.addEventListener("pyc-site-shell-ready", handler)
    })
}

async function run_axe(label) {
    const result = await axe.run(document.documentElement, {

        runOnly: {
            type: "tag",
            values: ["wcag2a", "wcag2aa", "wcag22aa"],
        },
        resultTypes: ["violations"],
    })
    return {
        scope: label,
        violations: result.violations.map((violation) => ({
            id: violation.id,
            impact: violation.impact,
            help: violation.help,
            description: violation.description,
            nodes: violation.nodes.length,
        })),
    }
}

const reports = []

// 1. Populated shell
{
    document.body.replaceChildren()
    const shell = build_populated_shell()
    await wait_ready(shell)
    reports.push(await run_axe("populated_shell"))
}

// 2. Empty-state shell
{
    document.body.replaceChildren()
    const shell = document.createElement("pyc-site-shell")
    document.body.appendChild(shell)
    await wait_ready(shell)
    reports.push(await run_axe("empty_state_shell"))
}

// 3. Open command palette
{
    document.body.replaceChildren()
    const shell = build_populated_shell()
    await wait_ready(shell)
    shell.openPalette()
    reports.push(await run_axe("palette_open"))
}

// Filter to serious/critical for the gate; report everything for
// visibility.
let blocking = 0
for (const report of reports) {
    for (const violation of report.violations) {
        if (violation.impact === "serious" || violation.impact === "critical") {
            blocking = blocking + 1
        }
    }
}

const payload = {
    suite: "pyc-site-shell-axe",
    generated_at: new Date().toISOString(),
    blocking_violation_count: blocking,
    reports,
}
console.log(JSON.stringify(payload, null, 2))

if (blocking > 0) {
    process.exit(1)
}
