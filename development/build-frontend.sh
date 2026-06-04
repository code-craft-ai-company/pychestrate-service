#!/usr/bin/env bash
#
# build-frontend.sh -- bundle the consumer-UI JavaScript.
#
# The consumer web UI ships as native ES modules (no Node toolchain at
# runtime). Served raw, a single page pulls ~270 separate module files
# (the automojo-webworks mj-* component library is ~249 of them), which
# is slow and -- on a single-threaded dev server -- unreliable: a module
# request can stall, leaving the shell's custom element unregistered.
#
# This step pre-bundles each entry barrel into one self-contained file
# with esbuild so a page loads a handful of files instead of hundreds.
# It is idempotent and Node is only needed at *build* time, not runtime.
#
# Bundles produced:
#   * the mj-* component library  -> static/javascript/pyc-mj-lib/index.js
#   * every pyc-* bundle barrel    -> <bundle>/index.js   (from index.entry.js)
#
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

# Activate the in-repo venv so the mj component library can be located via
# the installed automojo-webworks package.
if [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.venv/bin/activate"
fi

STATIC_JS="${REPO_ROOT}/source/site/automojo/pychestrate/webservice/webinterface/static/javascript"

ESBUILD="npx --yes esbuild"

echo "==> build-frontend: bundling consumer UI JavaScript"

# ---------------------------------------------------------------------------
# 1. The automojo-webworks mj-* component library (the big one).
# ---------------------------------------------------------------------------
MJ_INDEX="$(python3 - <<'PY'
import os
import automojo.webworks as w
print(os.path.join(os.path.dirname(w.__file__), "static", "javascript", "index.js"))
PY
)"

if [ ! -f "${MJ_INDEX}" ]; then
    echo "ERROR: could not locate the mj component library at ${MJ_INDEX}" >&2
    exit 1
fi

mkdir -p "${STATIC_JS}/pyc-mj-lib"
${ESBUILD} "${MJ_INDEX}" --bundle --format=esm \
    --outfile="${STATIC_JS}/pyc-mj-lib/index.js" >/dev/null 2>&1
echo "    bundled mj-* library -> pyc-mj-lib/index.js"

# ---------------------------------------------------------------------------
# 2. Each pyc-* bundle barrel. The un-bundled barrel is preserved as
#    ``index.entry.js`` (the build input); the bundle is written to
#    ``index.js`` (the served path the templates + tests reference).
# ---------------------------------------------------------------------------
for bundle_dir in "${STATIC_JS}"/pyc-*/; do
    [ -d "${bundle_dir}" ] || continue
    bundle_name="$(basename "${bundle_dir}")"

    # Skip the generated mj-lib bundle dir.
    if [ "${bundle_name}" = "pyc-mj-lib" ]; then
        continue
    fi

    entry="${bundle_dir}index.entry.js"

    # First run: preserve the un-bundled barrel as the build input.
    if [ ! -f "${entry}" ] && [ -f "${bundle_dir}index.js" ]; then
        cp "${bundle_dir}index.js" "${entry}"
    fi

    if [ ! -f "${entry}" ]; then
        echo "    SKIP ${bundle_name} (no index.entry.js / index.js)"
        continue
    fi

    ${ESBUILD} "${entry}" --bundle --format=esm \
        --outfile="${bundle_dir}index.js" >/dev/null 2>&1
    echo "    bundled ${bundle_name}"
done

echo "==> build-frontend: done"
