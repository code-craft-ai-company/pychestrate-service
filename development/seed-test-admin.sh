#!/usr/bin/env bash
#
# Create or reset a known-credential TEST ADMIN user against the SAME
# database the running pychestrate webservice uses.
#
# This wrapper composes the runtime environment exactly the way
# development/dev-up and development/run-staging-gunicorn do, then execs
# development/seed_test_admin.py. It is idempotent and only upserts the
# one admin user -- it never wipes existing data.
#
# It deliberately does NOT export PYCHESTRATE_DATABASE_URL: both the
# systemd service and this script rely on the persona-derived default
# (sqlite:///<presence-dir>/pychestrate.sqlite). Setting it to a
# different path would point this tool at a DIFFERENT database than the
# live service. The KEK + password pepper file paths are mirrored from
# run-staging-gunicorn so the same encryption keys are loaded.
#
# ----------------------------------------------------------------------------
# Usage -- LOCAL (dev sqlite under .cache/, dev secrets auto-generated):
#
#   PYCHESTRATE_RUNTIME_ENVIRONMENT=development \
#   development/seed-test-admin.sh \
#       --login admin \
#       --email admin@example.com \
#       --password 's3cr3t' \
#       --display-name 'Admin'
#
#   The development setting makes this target the dev presence dir
#   (.cache/presence) -- the SAME sqlite DB development/dev-up serves -- and
#   the per-checkout dev secrets under .cache/dev-secrets/. Without it the
#   tool defaults to the ~/pychestrate presence dir (the alpha-host layout).
#
# ----------------------------------------------------------------------------
# Usage -- ALPHA HOST (live staging service DB at ~/pychestrate):
#
#   # Run on the deployed host as the service user (e.g. deploy), from the
#   # checkout root /home/deploy/pychestrate-service. Stop or leave the
#   # service running -- this opens a separate sqlite connection.
#
#   PYCHESTRATE_RUNTIME_ENVIRONMENT=staging \
#   development/seed-test-admin.sh \
#       --login admin \
#       --password "$ADMIN_PASSWORD"
#
#   On the host this targets ~/pychestrate/pychestrate.sqlite (the live
#   service DB) and the shared KEK/pepper under
#   .cache/dev-secrets/, exactly as run-staging-gunicorn exports them.
#
# Env-var fallbacks honored by the python script (no CLI flag needed):
#   PYCHESTRATE_TEST_ADMIN_LOGIN, PYCHESTRATE_TEST_ADMIN_PASSWORD,
#   PYCHESTRATE_SEED_ADMIN_EMAIL.
# ----------------------------------------------------------------------------

set -euo pipefail

# ----------------------------------------------------------------------------
# Arguments are checked before anything is created: --help, a missing
# password, or a bad option must not generate secret files or touch .cache.
# ----------------------------------------------------------------------------

usage() {
    sed -n '3,51p' "$0" | sed 's/^# \{0,1\}//'
    echo
    echo "options: --login NAME  --email ADDRESS  --password SECRET  --display-name NAME  -h|--help"
}

HAVE_PASSWORD_FLAG=0
EXPECT_VALUE=""
for arg in "$@"; do
    if [[ -n "${EXPECT_VALUE}" ]]; then
        EXPECT_VALUE=""
        continue
    fi
    case "${arg}" in
        -h|--help)
            usage
            exit 0
            ;;
        --password)
            HAVE_PASSWORD_FLAG=1
            EXPECT_VALUE="--password"
            ;;
        --password=*)
            HAVE_PASSWORD_FLAG=1
            ;;
        --login|--email|--display-name)
            EXPECT_VALUE="${arg}"
            ;;
        --login=*|--email=*|--display-name=*)
            ;;
        *)
            echo "seed-test-admin: unknown argument '${arg}' (see --help)" >&2
            exit 2
            ;;
    esac
done
if [[ -n "${EXPECT_VALUE}" ]]; then
    echo "seed-test-admin: ${EXPECT_VALUE} needs a value (see --help)" >&2
    exit 2
fi

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

# ----------------------------------------------------------------------------
# Refuse production (mirror dev-up / run-staging-gunicorn safety rail)
# ----------------------------------------------------------------------------

if [[ "${PYCHESTRATE_RUNTIME_ENVIRONMENT:-}" == "production" ]]; then
    echo "seed-test-admin refuses to run with PYCHESTRATE_RUNTIME_ENVIRONMENT=production." >&2
    echo "Unset the variable or set it to development/staging/testing." >&2
    exit 1
fi

# ----------------------------------------------------------------------------
# Source the host/local repo-root .env if present.
#
# On the alpha host, deploy step 4 (rehome-repository) generates a
# gitignored .env at the checkout root with PYTHONPATH composition and
# any operator overrides. Sourcing it here puts the SAME values the
# service uses into scope. Real environment values still win because the
# explicit exports below use ${VAR:-default} and run AFTER the source.
# ----------------------------------------------------------------------------

ENV_FILE="${REPO_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
    echo "seed-test-admin: sourced ${ENV_FILE}"
fi

# The password has no default: fail now, before any secret file is created.
if [[ "${HAVE_PASSWORD_FLAG}" == "0" && -z "${PYCHESTRATE_TEST_ADMIN_PASSWORD:-}" ]]; then
    echo "seed-test-admin: a password is required: pass --password or set PYCHESTRATE_TEST_ADMIN_PASSWORD (see --help)" >&2
    exit 2
fi

# ----------------------------------------------------------------------------
# Per-checkout dev secret material (KEK + pepper), mirroring dev-up and
# run-staging-gunicorn so the SAME keys the service uses are loaded.
# Generated on first run if absent; reused on subsequent runs.
# ----------------------------------------------------------------------------

SECRETS_DIR="${REPO_ROOT}/.cache/dev-secrets"
mkdir -p "${SECRETS_DIR}"

KEK_FILE="${SECRETS_DIR}/dev.kek"
PEPPER_FILE="${SECRETS_DIR}/dev.password-pepper"
UI_COOKIE_SECRET_FILE="${SECRETS_DIR}/dev.ui-cookie-secret"

if [[ ! -s "${KEK_FILE}" ]]; then
    head -c 32 /dev/urandom > "${KEK_FILE}"
    chmod 600 "${KEK_FILE}"
    echo "seed-test-admin: generated ${KEK_FILE} (32 random bytes)"
fi

if [[ ! -s "${PEPPER_FILE}" ]]; then
    head -c 32 /dev/urandom > "${PEPPER_FILE}"
    chmod 600 "${PEPPER_FILE}"
    echo "seed-test-admin: generated ${PEPPER_FILE} (32 random bytes)"
fi

if [[ ! -s "${UI_COOKIE_SECRET_FILE}" ]]; then
    head -c 32 /dev/urandom > "${UI_COOKIE_SECRET_FILE}"
    chmod 600 "${UI_COOKIE_SECRET_FILE}"
    echo "seed-test-admin: generated ${UI_COOKIE_SECRET_FILE} (32 random bytes)"
fi

# ----------------------------------------------------------------------------
# Compose the runtime env from documented PYCHESTRATE_* names.
#
# PYCHESTRATE_DATABASE_URL is intentionally NOT exported -- the runtime
# computes sqlite:///<presence-dir>/pychestrate.sqlite from the persona
# singleton, so this connects to the SAME DB the service reads.
#
# Defaults below match run-staging-gunicorn (KEK_ID=staging-kek-1). On a
# local dev box you may instead want development/dev-up defaults
# (KEK_ID=dev-kek-1); override via the env when needed. The KEK_ID is a
# logged identifier and does not affect which key file is read.
# ----------------------------------------------------------------------------

export PYCHESTRATE_RUNTIME_ENVIRONMENT="${PYCHESTRATE_RUNTIME_ENVIRONMENT:-staging}"

export PYCHESTRATE_KEK_SOURCE="${PYCHESTRATE_KEK_SOURCE:-file}"
export PYCHESTRATE_KEK_ID="${PYCHESTRATE_KEK_ID:-staging-kek-1}"
export PYCHESTRATE_KEK_FILE_PATH="${PYCHESTRATE_KEK_FILE_PATH:-${KEK_FILE}}"

export PYCHESTRATE_PASSWORD_PEPPER_SOURCE="${PYCHESTRATE_PASSWORD_PEPPER_SOURCE:-file}"
export PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH="${PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH:-${PEPPER_FILE}}"

export PYCHESTRATE_UI_COOKIE_SECRET_SOURCE="${PYCHESTRATE_UI_COOKIE_SECRET_SOURCE:-file}"
export PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH="${PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH:-${UI_COOKIE_SECRET_FILE}}"

# Auto-create schema only matters on a brand-new local DB; leave the
# service's policy alone if the caller already set it.
export PYCHESTRATE_AUTO_CREATE_SCHEMA="${PYCHESTRATE_AUTO_CREATE_SCHEMA:-false}"

# ----------------------------------------------------------------------------
# Presence-dir resolution -- THE critical DB-targeting knob.
#
# The runtime computes the sqlite DB path as
# sqlite:///<presence-dir>/pychestrate.sqlite, and resolve_presence_dir()
# defaults an UNSET PYCHESTRATE_PRESENCE_DIR to ~/pychestrate.
#
#   * Alpha host (staging): the systemd service uses that ~/pychestrate
#     default, so leaving PYCHESTRATE_PRESENCE_DIR unset targets the SAME
#     live DB -- correct, do nothing.
#   * Local dev box (development): development/dev-up runs the server with
#     PYCHESTRATE_PRESENCE_DIR=${REPO_ROOT}/.cache/presence, NOT
#     ~/pychestrate. So in development mode default the presence dir there
#     to target the same DB dev-up reads. Without this, a local run would
#     silently seed a different (empty ~/pychestrate) database.
#
# An explicit PYCHESTRATE_PRESENCE_DIR (env or .env) always wins.
# ----------------------------------------------------------------------------
if [[ "${PYCHESTRATE_RUNTIME_ENVIRONMENT}" == "development" && -z "${PYCHESTRATE_PRESENCE_DIR:-}" ]]; then
    export PYCHESTRATE_PRESENCE_DIR="${REPO_ROOT}/.cache/presence"
fi

# ----------------------------------------------------------------------------
# Activate the venv FIRST, then set PYTHONPATH.
#
# Order matters: the alpha host's .venv/bin/activate was customized to
# re-export a PYTHONPATH (the rehome-generated one that contains
# source/service + source/testroots but NOT source/site -- a regular
# ``ccai`` package there SHADOWS the namespace package and hides
# ccai.pychestrate.webservice). If we set PYTHONPATH before activating,
# activation clobbers it. So activate first, then export our clean path so
# it wins at exec time.
# ----------------------------------------------------------------------------

if [[ -f "${REPO_ROOT}/.venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.venv/bin/activate"
fi

if [[ -f "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON="${REPO_ROOT}/.venv/bin/python"
else
    PYTHON="$(command -v python3 || command -v python)"
fi

# ----------------------------------------------------------------------------
# PYTHONPATH -- mirror development/run-staging-gunicorn, NOT dev-up.
#
# We do NOT append the inherited ${PYTHONPATH:-}: it carries the shadowing
# source/service + source/testroots entries described above. source/packages
# + source/site are all the runtime needs; the activated venv supplies the
# installed codecraftai-* dependencies. The ../codecraftai-* sibling entries
# support a local multi-checkout dev box and are harmlessly ignored on the
# host. This export runs AFTER venv activation so it is the final word.
# ----------------------------------------------------------------------------

export PYTHONPATH="${REPO_ROOT}/source/packages:${REPO_ROOT}/source/site:../codecraftai-webworks/source/packages:../codecraftai-this-app/source/packages:../codecraftai-testbase/source/packages:../codecraftai-configuration/source/packages:../codecraftai-credentials/source/packages:../codecraftai-dataprofiles/source/packages:../codecraftai-errors/source/packages:../pychestrate-core/source/packages"

echo "seed-test-admin: env=${PYCHESTRATE_RUNTIME_ENVIRONMENT}"
echo "seed-test-admin: db=${PYCHESTRATE_DATABASE_URL:-<persona default sqlite:///<presence-dir>/pychestrate.sqlite>}"
echo "seed-test-admin: kek=${PYCHESTRATE_KEK_FILE_PATH}"
echo "seed-test-admin: pepper=${PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH}"
echo

exec "${PYTHON}" "${REPO_ROOT}/development/seed_test_admin.py" "$@"
