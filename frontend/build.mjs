/**
 * Build script for the Pychestrate frontend TypeScript bundles.
 *
 * Each entry in ``ENTRY_POINTS`` is bundled into a single ES module
 * under ``DIST_DIR``. The dist directory is committed to git so the
 * Python deploy does not require Node.
 *
 * Run with: ``npm run build``
 */

import * as esbuild from "esbuild"
import * as fs from "node:fs"
import * as path from "node:path"
import { fileURLToPath } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))

const DIST_DIR = path.resolve(
    HERE,
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
)

const ENTRY_POINTS = [
    {
        entry: path.join(HERE, "src", "pyc-site-shell", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-site-shell.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-admin-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-admin-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-runs-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-runs-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-catalog-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-catalog-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-builds-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-builds-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-infra-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-infra-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-metrics-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-metrics-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-secrets-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-secrets-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-pipelines-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-pipelines-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-pods-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-pods-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-resources-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-resources-bundle.js"),
    },
    {
        entry: path.join(HERE, "src", "pyc-ops-bundle", "index.ts"),
        outfile: path.join(DIST_DIR, "pyc-ops-bundle.js"),
    },
]

// Bundle stylesheets copied alongside their bundle so the bundle
// can reference a stable URL. Each entry is (source, target-name).
const STYLESHEETS = [
    {
        source: path.join(HERE, "src", "pyc-runs-bundle", "runs-list.css"),
        target: "pyc-runs-bundle.css",
    },
    {
        source: path.join(HERE, "src", "pyc-catalog-bundle", "catalog.css"),
        target: "pyc-catalog-bundle.css",
    },
    {
        source: path.join(HERE, "src", "pyc-builds-bundle", "builds.css"),
        target: "pyc-builds-bundle.css",
    },
    {
        source: path.join(HERE, "src", "pyc-infra-bundle", "infra.css"),
        target: "pyc-infra-bundle.css",
    },
    {
        source: path.join(HERE, "src", "pyc-metrics-bundle", "metrics.css"),
        target: "pyc-metrics-bundle.css",
    },
    {
        source: path.join(HERE, "src", "pyc-secrets-bundle", "secrets.css"),
        target: "pyc-secrets-bundle.css",
    },
    {
        source: path.join(HERE, "src", "pyc-pipelines-bundle", "pipelines.css"),
        target: "pyc-pipelines-bundle.css",
    },
    {
        source: path.join(HERE, "src", "pyc-pods-bundle", "pods.css"),
        target: "pyc-pods-bundle.css",
    },
    {
        source: path.join(
            HERE, "src", "pyc-resources-bundle", "resources.css",
        ),
        target: "pyc-resources-bundle.css",
    },
    {
        source: path.join(HERE, "src", "pyc-ops-bundle", "ops.css"),
        target: "pyc-ops-bundle.css",
    },
    {
        source: path.join(HERE, "src", "pyc-admin-bundle", "admin.css"),
        target: "pyc-admin-bundle.css",
    },
]

async function build_all() {
    if (fs.existsSync(DIST_DIR) === false) {
        fs.mkdirSync(DIST_DIR, { recursive: true })
    }

    for (const ep of ENTRY_POINTS) {
        const result = await esbuild.build({
            entryPoints: [ep.entry],
            bundle: true,
            format: "esm",
            target: "es2022",
            outfile: ep.outfile,
            sourcemap: true,
            logLevel: "info",
            minify: false,
            platform: "browser",
        })
        if (result.errors.length > 0) {
            for (const err of result.errors) {
                console.error(err)
            }
            process.exit(1)
        }
    }

    // Copy the stylesheet alongside the bundle so the shell document
    // can reference a stable URL.
    const css_source = path.join(HERE, "src", "pyc-site-shell", "styles.css")
    const css_target = path.join(DIST_DIR, "pyc-site-shell.css")
    if (fs.existsSync(css_source) === true) {
        fs.copyFileSync(css_source, css_target)
    }

    // Copy per-bundle stylesheets so each feature bundle can load
    // its own stylesheet from a stable dist URL.
    for (const sheet of STYLESHEETS) {
        if (fs.existsSync(sheet.source) === true) {
            fs.copyFileSync(sheet.source, path.join(DIST_DIR, sheet.target))
        }
    }

    console.log("Build complete. Output dir: " + DIST_DIR)
}

build_all().catch((reason) => {
    console.error(reason)
    process.exit(1)
})
