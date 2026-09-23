#!/usr/bin/env bash
#
# build-frontend.sh -- bundle the consumer-UI JavaScript.
#
# usage: development/build-frontend.sh [-h | --help]
#
# The consumer web UI ships as native ES modules (no Node toolchain at
# runtime). Served raw, a single page pulls ~270 separate module files
# (the codecraftai-webworks mj-* component library is ~249 of them), which
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
# esbuild is pinned (ESBUILD_VERSION, default below) so every machine
# produces the same committed bundles; set ESBUILD=/path/to/esbuild to use
# a local binary instead of fetching it with npx. esbuild's warnings and
# errors are shown, and any failure stops the build.
#
# Run from anywhere; paths are resolved relative to the repo root.

set -euo pipefail

case "${1:-}" in
    -h|--help)
        sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    "")
        ;;
    *)
        echo "build-frontend.sh: unknown argument '$1' (see --help)" >&2
        exit 2
        ;;
esac

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

# Activate the in-repo venv so the mj component library can be located via
# the installed codecraftai-webworks package.
if [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.venv/bin/activate"
fi

STATIC_JS="${REPO_ROOT}/source/site/ccai/pychestrate/webservice/webinterface/static/javascript"

ESBUILD_VERSION="${ESBUILD_VERSION:-0.28.2}"
if [ -n "${ESBUILD:-}" ]; then
    ESBUILD_CMD=("${ESBUILD}")
else
    if ! command -v npx >/dev/null 2>&1; then
        echo "ERROR: build-frontend.sh needs Node.js (npx) or ESBUILD=/path/to/esbuild" >&2
        exit 1
    fi
    ESBUILD_CMD=(npx --yes "esbuild@${ESBUILD_VERSION}")
fi

echo "==> build-frontend: bundling consumer UI JavaScript with ${ESBUILD_CMD[*]}"

# ---------------------------------------------------------------------------
# 1. The codecraftai-webworks mj-* component library (the big one).
# ---------------------------------------------------------------------------
MJ_INDEX="$(python3 - <<'PY'
import os
import ccai.webworks as w
print(os.path.join(os.path.dirname(w.__file__), "static", "javascript", "index.js"))
PY
)"

if [ ! -f "${MJ_INDEX}" ]; then
    echo "ERROR: could not locate the mj component library at ${MJ_INDEX}" >&2
    exit 1
fi

mkdir -p "${STATIC_JS}/pyc-mj-lib"
"${ESBUILD_CMD[@]}" "${MJ_INDEX}" --bundle --format=esm --minify --log-level=warning \
    --outfile="${STATIC_JS}/pyc-mj-lib/index.js"
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

    "${ESBUILD_CMD[@]}" "${entry}" --bundle --format=esm --log-level=warning \
        --outfile="${bundle_dir}index.js"
    echo "    bundled ${bundle_name}"
done

echo "==> build-frontend: done"
