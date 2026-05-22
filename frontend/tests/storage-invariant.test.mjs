/**
 * NFR-2 invariant test (T3.7): the shell never writes to
 * ``localStorage`` / ``sessionStorage`` / ``IndexedDB``.
 *
 * Scans the shell component module tree for any reference to
 * these APIs and fails the suite if one appears
 * outside an inline source-code comment. The scan is a static
 * string match -- intentionally coarse but extremely cheap to
 * keep in CI.
 */

import { test } from "node:test"
import assert from "node:assert/strict"
import * as fs from "node:fs"
import * as path from "node:path"
import { fileURLToPath } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const SHELL_SRC_DIR = path.resolve(
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
)

const FORBIDDEN_TOKENS = ["localStorage", "sessionStorage", "indexedDB"]

function collect_source_files(dir) {
    const out = []
    const entries = fs.readdirSync(dir, { withFileTypes: true })
    for (const entry of entries) {
        const full = path.join(dir, entry.name)
        if (entry.isDirectory()) {
            for (const child of collect_source_files(full)) {
                out.push(child)
            }
        } else if (entry.isFile() && /\.(js|css)$/.test(entry.name)) {
            out.push(full)
        }
    }
    return out
}

function strip_line_comments(line) {
    const idx = line.indexOf("//")
    if (idx < 0) {
        return line
    }
    return line.slice(0, idx)
}

test("shell source never references browser storage APIs in code", () => {
    const files = collect_source_files(SHELL_SRC_DIR)
    const offenders = []
    for (const file of files) {
        const text = fs.readFileSync(file, "utf-8")
        // Crude block-comment stripper -- ok because shell sources
        // use sphinx-style /** ... */ JSDoc blocks. We strip both
        // /* ... */ runs and trailing // line comments before the
        // token scan.
        const without_block = text.replace(/\/\*[\s\S]*?\*\//g, "")
        const lines = without_block.split(/\r?\n/)
        for (let idx = 0; idx < lines.length; idx = idx + 1) {
            const code_only = strip_line_comments(lines[idx])
            for (const token of FORBIDDEN_TOKENS) {
                if (code_only.includes(token)) {
                    offenders.push(`${path.relative(SHELL_SRC_DIR, file)}:${idx + 1}: ${token}`)
                }
            }
        }
    }
    assert.deepEqual(
        offenders,
        [],
        `Storage-API references found:\n  ${offenders.join("\n  ")}\n`
        + "Shell state must remain in-memory per NFR-2 of 9-site-shell.",
    )
})
