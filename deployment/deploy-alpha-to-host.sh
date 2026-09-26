#!/usr/bin/env bash
#
# deploy-alpha-to-host.sh -- one-shot alpha deploy from a workstation
# to a remote host via SSH, with nginx fronting the app.
#
# Architecture:
#
#                       :80 (nginx)
#       external  -----------------> nginx ---> 127.0.0.1:8888 (app)
#       clients                       on
#                                   --host
#
# nginx terminates on the host's external interface and reverse-
# proxies to the app bound on loopback. Operators access the
# service at ``http://<host>/`` -- the app port is no longer
# exposed externally.
#
# Drives the existing repository-setup + development bootstrap chain
# remotely:
#
#   1. rsync the working tree to ``<remote>:~/pychestrate-service``
#      (excludes the venv, output, cache, .claude, .git).
#   2. ``repository-setup/setup-debian-machine``    -- system apt
#      packages (build tools, python, pipx, poetry, nginx, tmux).
#      Requires sudo on the remote; the user is prompted
#      interactively.  Skipped under ``--skip-system-setup``;
#      replaced with a prerequisite probe.
#   3. Configure git credentials on the remote so the private
#      ``codecraftai-*`` dependencies that ``pyproject.toml`` pulls
#      from GitHub (``git = "https://github.com/automationmojo/..."``
#      sources) can be cloned, using ``CODECRAFTAI_REPO_TOKEN`` from
#      the local env or repo-root ``.env`` -- the same mechanism as
#      CI.  When ``pyproject.toml`` names no such git source (it
#      resolves the packages from a package index instead), the step
#      is skipped and no token is needed; the index's credentials
#      must then be configured for poetry on the host.
#   4. ``repository-setup/rehome-repository``        -- generates
#      ``.env`` with PYTHONPATH composition.
#   5. ``development/setup-environment``             -- creates
#      ``.venv`` and runs ``poetry install``.
#   6. ``alembic upgrade head``                       -- against a
#      SQLite DB inside the checkout's ``.cache/dev-db/``.
#   7. Install / refresh nginx site config and reload nginx.  The
#      site listens on ``--proxy-port`` (default 80) and proxies
#      to the app at ``127.0.0.1:--port`` (default 8888).
#      Skipped under ``--skip-system-setup`` (assumes config
#      already in place from a workstation-driven first run).
#   8. Install ``pychestrate.service`` systemd unit (rendered
#      from ``deployment/pychestrate.service.template``) + start
#      / restart the service, plus ``pychestrate-backup.service``
#      / ``.timer`` (daily backup of the database, run artifacts
#      and keys into ~/pychestrate/backups + backup-keys) and the
#      logrotate policy for ~/.pychestrate/*.log.  The unit invokes
#      ``development/run-staging-gunicorn`` which runs gunicorn
#      against ``build_wsgi_application_for_production()`` with
#      ``PYCHESTRATE_RUNTIME_ENVIRONMENT=staging`` and binds
#      ``127.0.0.1:--port``.  Auto-generated KEK / pepper /
#      cookie-secret remain under ``.cache/dev-secrets/``.
#      Skipped under ``--skip-system-setup`` (unit install
#      requires sudo); replaced with ``systemctl restart``.
#   9. probe ``http://<host>:<proxy-port>/`` from the workstation
#      to confirm nginx + gunicorn are serving end-to-end.
#
# Usage (``--help`` prints the full option list, generated from the
# option table below):
#
#   CODECRAFTAI_REPO_TOKEN=ghp_xxx \
#       deployment/deploy-alpha-to-host.sh --host HOST --user USER \
#           [--port 8888] [--proxy-port 80] [--public-hostname NAME] \
#           [--client-ca-path PATH] [--skip-system-setup] [--dry-run]
#
# ``--host`` and ``--user`` are required.  Options take their value
# as ``--option VALUE`` or ``--option=VALUE``.  ``--dry-run`` prints
# every step without changing anything, locally or on the host: it
# only runs the read-only SSH check (and, under
# ``--skip-system-setup``, the tool probe) and shows what the sync
# would transfer and delete (``rsync --dry-run``).
#
# Idempotent: re-running the script syncs new code, refreshes the
# nginx config, and restarts the service.  KEK / pepper /
# cookie-secret + the SQLite DB persist across runs (under
# ``.cache/dev-secrets/`` and ``~/pychestrate/`` on the host).

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults + arg parsing
# ---------------------------------------------------------------------------

# No host-specific defaults: --host and --user name the target.
REMOTE_HOST=""
REMOTE_USER=""
REMOTE_PORT="8888"          # internal app port (nginx proxies to this)
PROXY_PORT="80"             # external port nginx listens on
# Canonical public hostname for the deploy -- must match the
# subject on the TLS cert at /etc/nginx/ssl/pychestrate.crt.
# The :80 redirect lands users here regardless of what they
# typed (a short name vs. the full DNS / tailnet name), so the
# browser never sees a cert/hostname mismatch.  Defaults (after
# argument parsing) to --host.
PUBLIC_HOSTNAME=""
SKIP_SYSTEM_SETUP="false"
DRY_RUN="false"
SHOW_HELP="false"
# Path on the REMOTE to the CA cert used by nginx to verify
# incoming client certificates for the mTLS-gated routes.  It must
# be the service's client-enrollment CA -- the CA that signs every
# pod certificate at enrollment -- or nginx rejects enrolled pods.
# Defaults (after argument parsing) to the certificate that
# ``development/run-staging-gunicorn --provision-only`` writes in
# the remote checkout; step 6 runs it.  Override with
# ``--client-ca-path`` only when the enrollment CA is staged
# elsewhere (PYCHESTRATE_ENROLLMENT_CA_FILE_PATH).
CLIENT_CA_PATH=""

# One row per option: flag|VALUE name ("" for a switch)|variable|help.
# The parser and --help both read this table, so the usage text always
# lists every option the script accepts.
OPTION_TABLE=(
    "--host|HOST|REMOTE_HOST|SSH host to deploy to (required)"
    "--user|USER|REMOTE_USER|SSH user on the host; the service runs as this user (required)"
    "--port|PORT|REMOTE_PORT|loopback port gunicorn binds (default 8888)"
    "--proxy-port|PORT|PROXY_PORT|port nginx listens on (default 80)"
    "--public-hostname|NAME|PUBLIC_HOSTNAME|name on the TLS certificate; nginx redirects there (default: --host)"
    "--client-ca-path|PATH|CLIENT_CA_PATH|client-enrollment CA certificate on the host (default: the one step 6 writes)"
    "--skip-system-setup||SKIP_SYSTEM_SETUP|skip the sudo steps (apt, nginx, systemd unit); for CI after a first interactive deploy"
    "--dry-run||DRY_RUN|print every step and change nothing (only read-only SSH checks and an rsync --dry-run run)"
    "--help||SHOW_HELP|show this help and exit"
)

usage() {
    echo "usage: deployment/deploy-alpha-to-host.sh --host HOST --user USER [options]"
    echo
    echo "Deploy this checkout to HOST over SSH: sync it, install its dependencies,"
    echo "migrate the database, configure nginx and the systemd units, and probe it."
    echo
    echo "options:"
    local row flag value_name variable help_text spelled
    for row in "${OPTION_TABLE[@]}"; do
        IFS='|' read -r flag value_name variable help_text <<< "${row}"
        spelled="${flag}"
        if [ -n "${value_name}" ]; then
            spelled="${flag} ${value_name}"
        fi
        printf '  %-26s %s\n' "${spelled}" "${help_text}"
    done
    echo
    echo "Options taking a value accept --option VALUE or --option=VALUE."
    echo
    echo "environment:"
    echo "  CODECRAFTAI_REPO_TOKEN     GitHub token for the private codecraftai-* git"
    echo "                             dependencies (needed while pyproject.toml pulls them"
    echo "                             from git); read from the repo-root .env when unset."
    echo
    echo "exit codes: 0 deployed (or dry run finished); 1 bad arguments; 2 no"
    echo "  CODECRAFTAI_REPO_TOKEN; 3 SSH not possible without a password; 4 the service"
    echo "  did not answer the probe; 5 tools missing on the host (--skip-system-setup);"
    echo "  6 client-enrollment CA certificate missing on the host."
    echo
    echo "The header of this script and deployment/README.md describe every step."
    return 0
}

option_row() {
    # Print the OPTION_TABLE row for flag "$1"; fail when there is none.
    local row
    for row in "${OPTION_TABLE[@]}"; do
        if [ "${row%%|*}" = "$1" ]; then
            printf '%s\n' "${row}"
            return 0
        fi
    done
    return 1
}

argument_error() {
    echo "ERROR: $1" >&2
    echo "       Run with --help for usage." >&2
    exit 1
}

while [ $# -gt 0 ]; do
    ARG="$1"
    shift
    FLAG="${ARG%%=*}"
    HAS_INLINE_VALUE="false"
    if [ "${FLAG}" != "${ARG}" ]; then
        HAS_INLINE_VALUE="true"
    fi
    if [ "${FLAG}" = "-h" ]; then
        FLAG="--help"
    fi
    if ! ROW="$(option_row "${FLAG}")"; then
        argument_error "Unknown argument: ${ARG}"
    fi
    IFS='|' read -r _flag VALUE_NAME VARIABLE _help <<< "${ROW}"
    if [ -z "${VALUE_NAME}" ]; then
        if [ "${HAS_INLINE_VALUE}" = "true" ]; then
            argument_error "${FLAG} takes no value"
        fi
        printf -v "${VARIABLE}" '%s' "true"
        continue
    fi
    if [ "${HAS_INLINE_VALUE}" = "true" ]; then
        VALUE="${ARG#*=}"
    elif [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then
        VALUE="$1"
        shift
    else
        argument_error "${FLAG} needs a value: ${FLAG} ${VALUE_NAME} (or ${FLAG}=${VALUE_NAME})"
    fi
    if [ -z "${VALUE}" ]; then
        argument_error "${FLAG} needs a non-empty value"
    fi
    printf -v "${VARIABLE}" '%s' "${VALUE}"
done
unset ARG FLAG HAS_INLINE_VALUE ROW _flag VALUE_NAME VARIABLE _help VALUE

if [ "${SHOW_HELP}" = "true" ]; then
    usage
    exit 0
fi
if [ -z "${REMOTE_HOST}" ] || [ -z "${REMOTE_USER}" ]; then
    argument_error "--host and --user are required (for example --host app-server.example.com --user deploy)"
fi
if [ -z "${PUBLIC_HOSTNAME}" ]; then
    PUBLIC_HOSTNAME="${REMOTE_HOST}"
fi

REMOTE_TARGET="${REMOTE_USER}@${REMOTE_HOST}"
REMOTE_PATH="pychestrate-service"  # relative to remote $HOME

if [ -z "${CLIENT_CA_PATH}" ]; then
    CLIENT_CA_PATH="/home/${REMOTE_USER}/${REMOTE_PATH}/.cache/dev-secrets/dev.enrollment-ca.crt"
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------------------
# --dry-run
#
# ``run`` wraps every command that changes something, locally or on
# the host; with --dry-run it prints the command instead.
# ``run_remote_script`` does the same for a script fed to ssh on
# stdin, printing the script.  Read-only checks (the SSH probe, the
# --skip-system-setup tool probe) run in both modes.
# ---------------------------------------------------------------------------

shell_words() {
    # "$@" as one line a shell would read back: words with spaces or
    # special characters in single quotes.
    local word quoted line=""
    for word in "$@"; do
        case "${word}" in
            *[!A-Za-z0-9_./:@=+-]*|"")
                quoted="'${word//\'/\'\\\'\'}'"
                ;;
            *)
                quoted="${word}"
                ;;
        esac
        line="${line:+${line} }${quoted}"
    done
    printf '%s\n' "${line}"
    return 0
}

run() {
    if [ "${DRY_RUN}" = "true" ]; then
        echo "    [dry-run] would run: $(shell_words "$@")"
        return 0
    fi
    "$@"
}

run_remote_script() {
    # run_remote_script "<what it does>" ssh-command... ; script on stdin
    local description="$1"
    shift
    if [ "${DRY_RUN}" = "true" ]; then
        echo "    [dry-run] would run on ${REMOTE_TARGET} (${description}):"
        sed 's/^/        | /'
        return 0
    fi
    "$@"
}

# pyproject.toml pulls the private codecraftai-* packages from GitHub
# when it names git sources for them; only then do the remote's git
# credentials (step 3) and CODECRAFTAI_REPO_TOKEN matter.
GIT_SOURCE_DEPENDENCIES="$(grep -c 'git = "https://github.com/automationmojo/' "${REPO_ROOT}/pyproject.toml" 2>/dev/null || true)"
GIT_SOURCE_DEPENDENCIES="${GIT_SOURCE_DEPENDENCIES:-0}"

# ---------------------------------------------------------------------------
# Source repo-root .env (if present)
#
# Pulls in any operator-set environment variables -- most notably
# ``CODECRAFTAI_REPO_TOKEN`` -- so the operator does not have to
# ``export`` them on every invocation.  ``.env`` is gitignored;
# the rehome-repository script generates a base file that the
# operator extends.  Already-set environment variables (e.g.
# ones the workflow_dispatch job populates as ``env:``) take
# precedence over .env values; the .env merely fills in the
# blanks.
# ---------------------------------------------------------------------------

ENV_FILE="${REPO_ROOT}/.env"
if [ -f "${ENV_FILE}" ]; then
    echo "==> sourcing ${ENV_FILE}"
    # ``set -a`` -> auto-export every variable assigned in the
    # sourced file so subprocesses (rsync / ssh / etc) see them.
    # We loop line-by-line and only assign vars that are not
    # already set, so a parent-shell ``export`` always wins.
    while IFS= read -r _line || [ -n "${_line}" ]; do
        # Strip leading whitespace, skip blanks and comments.
        _line="${_line#"${_line%%[![:space:]]*}"}"
        case "${_line}" in
            ''|'#'*) continue ;;
        esac
        # Only consider ``KEY=...`` and ``export KEY=...`` lines.
        case "${_line}" in
            export\ *=*) _line="${_line#export }" ;;
            *=*) ;;
            *) continue ;;
        esac
        _key="${_line%%=*}"
        # Skip if the key is already set in the parent env.
        if [ -n "${!_key+x}" ]; then
            continue
        fi
        # Strip surrounding quotes from the value, then export.
        _val="${_line#*=}"
        case "${_val}" in
            \"*\") _val="${_val#\"}"; _val="${_val%\"}" ;;
            \'*\') _val="${_val#\'}"; _val="${_val%\'}" ;;
        esac
        export "${_key}=${_val}"
    done < "${ENV_FILE}"
    unset _line _key _val
fi

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

echo "================================================================"
echo "  pychestrate-service alpha deploy"
echo "================================================================"
echo "  source repo  : ${REPO_ROOT}"
echo "  target       : ${REMOTE_TARGET}"
echo "  proxy port   : ${PROXY_PORT}    (nginx, public-facing)"
echo "  app port     : ${REMOTE_PORT}  (gunicorn / dev-up, loopback only)"
echo "  public name  : ${PUBLIC_HOSTNAME}"
if [ "${DRY_RUN}" = "true" ]; then
echo "  mode         : DRY RUN -- nothing is changed, locally or on the host"
fi
echo "================================================================"
echo

if [ "${GIT_SOURCE_DEPENDENCIES}" -gt 0 ] && [ -z "${CODECRAFTAI_REPO_TOKEN:-}" ]; then
    cat >&2 <<EOF
ERROR: CODECRAFTAI_REPO_TOKEN is not set.

pyproject.toml pulls ${GIT_SOURCE_DEPENDENCIES} private dependencies from git
repositories under the 'automationmojo' GitHub org.  Without a Personal
Access Token, the remote's 'poetry install' step will fail.

Set the same fine-grained PAT you configured for CI as
CODECRAFTAI_REPO_TOKEN before re-running.  Required scope on the
'automationmojo' org: Contents -- Read.

  export CODECRAFTAI_REPO_TOKEN=ghp_xxx
  deployment/deploy-alpha-to-host.sh --host ${REMOTE_HOST} --user ${REMOTE_USER}
EOF
    exit 2
fi

# Reachability probe before we start asking for sudo passwords on
# the remote.  Using ssh -o BatchMode here so we get a fast clean
# error if the host or auth is wrong.
echo "==> Probing SSH to ${REMOTE_TARGET} ..."
if ! ssh -o ConnectTimeout=8 -o BatchMode=yes "${REMOTE_TARGET}" "true" 2>/dev/null; then
    cat >&2 <<EOF
ERROR: cannot SSH to ${REMOTE_TARGET} non-interactively.

Either:
  1. SSH key not installed on the remote.  Run:
       ssh-copy-id ${REMOTE_TARGET}
  2. Host unreachable.  Verify connectivity:
       ping ${REMOTE_HOST}
  3. ssh-agent doesn't have your key loaded.  Try:
       ssh-add ~/.ssh/id_ed25519
EOF
    exit 3
fi
echo "    OK"

echo

# ---------------------------------------------------------------------------
# Step 1a -- build the consumer-UI bundles locally (before the rsync)
#
# The frontend ships as native ES modules; build-frontend.sh pre-bundles
# them with esbuild so a deployed page loads a handful of files instead of
# ~270 (which stalls/flakes on a single-worker server). The bundle is built
# HERE -- the dev machine has Node/npx -- and the rsync below carries the
# built bundles up, so the target host stays Node-free. The shell document
# references the mj-* library bundle, so this step is required, not optional;
# a build failure aborts the deploy (set -e) rather than shipping a template
# that points at a missing bundle.
# ---------------------------------------------------------------------------
echo "==> Step 1a: build consumer-UI bundles locally (esbuild)"
run bash "${REPO_ROOT}/development/build-frontend.sh"
echo

# ---------------------------------------------------------------------------
# Step 1 -- rsync the working tree
# ---------------------------------------------------------------------------

echo "==> Step 1/8: rsync repo to ${REMOTE_TARGET}:~/${REMOTE_PATH}/"
run ssh "${REMOTE_TARGET}" "mkdir -p ~/${REMOTE_PATH}"

# ``--info=progress2`` is a rsync 3.1+ flag (single-line live
# progress display).  macOS Sequoia ships ``openrsync`` (Apple's
# OpenBSD-derived reimplementation, protocol-29) by default,
# which rejects the flag with an "unrecognized option" error.
# Probe rsync's version and fall back to ``--stats`` (universal;
# prints summary at the end) when the live-progress flag is
# unsupported.  Operators on macOS who want live progress can
# ``brew install rsync`` to pick up GNU rsync 3.x.
RSYNC_PROGRESS_OPT="--stats"
if rsync --version 2>/dev/null | grep -qE "version (3|[4-9])\."; then
    RSYNC_PROGRESS_OPT="--info=progress2"
fi
sync_tree() {
    # rsync the checkout to the host; "$@" adds rsync options.
    rsync -az --delete "$@" \
    --exclude='.venv' \
    --exclude='.output' \
    --exclude='.cache' \
    --exclude='.claude' \
    --exclude='.kiro' \
    --exclude='.vscode' \
    --exclude='.git/' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='.env' \
    --exclude='.output*' \
    --exclude='*.sqlite' \
    --exclude='*.sqlite-journal' \
    "${REPO_ROOT}/" "${REMOTE_TARGET}:~/${REMOTE_PATH}/"
}

if [ "${DRY_RUN}" = "true" ]; then
    # rsync itself previews the sync -- every file it would send and
    # every remote file --delete would remove -- and changes nothing.
    echo "    [dry-run] rsync --dry-run --itemize-changes (lines starting '*deleting' are removals):"
    sync_tree --dry-run --itemize-changes
else
    sync_tree "${RSYNC_PROGRESS_OPT}"
fi
echo

# ---------------------------------------------------------------------------
# Step 2 -- system apt packages (build-essential, python3, poetry)
#
# Uses ``ssh -tt`` (force TTY allocation) so the sudo prompt
# inside setup-debian-machine + nginx + systemd-unit-install
# steps can read /dev/tty.  Plain ``ssh -t`` only REQUESTS a
# TTY and silently falls back to non-TTY when stdin isn't a
# terminal -- which happens when the remote command is fed via
# heredoc, producing a confusing ``sudo: a terminal is required
# to read the password`` mid-deploy.  ``-tt`` forces it.
#
# Skipped under ``--skip-system-setup`` -- CI cannot satisfy an
# interactive sudo prompt, so the CI deploy workflow assumes the
# target was pre-provisioned by a workstation-driven first run.
# ---------------------------------------------------------------------------

if [ "${SKIP_SYSTEM_SETUP}" = "true" ]; then
    echo "==> Step 2/8: --skip-system-setup; verifying prerequisites on target"
    # Probe each required tool individually so the failure
    # message lists every missing one, not just the first.
    #
    # Use ``bash -ls`` (login shell + read script from stdin) so
    # the user's ~/.profile + ~/.bashrc are sourced before the
    # probe runs.  This matters for ``pipx``-installed tools
    # (e.g. ``poetry`` at ~/.local/bin/poetry) -- ``pipx
    # ensurepath`` writes PATH stanzas into those files, but a
    # plain ``ssh user@host 'cmd'`` runs a non-interactive
    # non-login bash that never reads them.  Without this, the
    # probe falsely reports poetry missing on a target where
    # poetry IS installed for the deploy user.
    MISSING=$(ssh "${REMOTE_TARGET}" 'bash -ls' <<'PROBE'
        missing=""
        for cmd in git python3 pipx poetry tmux make nginx; do
            command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
        done
        # python3-venv is a separate package -- check by trying
        # to invoke its module.
        python3 -c "import venv" >/dev/null 2>&1 || missing="$missing python3-venv"
        echo "$missing" | tr -s " "
PROBE
)
    if [ -n "${MISSING# }" ] && [ "${MISSING# }" != "" ]; then
        cat >&2 <<EOF
ERROR: target ${REMOTE_TARGET} is missing required tools:${MISSING}

CI cannot install these (sudo prompt is interactive). Run the
following on the target as a one-time bootstrap, then re-run
the workflow:

  ssh ${REMOTE_TARGET} 'sudo apt-get update && \\
      sudo apt-get install -y \\
          git python3 python3-venv python3-dev python3-pip \\
          build-essential pipx tmux make nginx && \\
      pipx ensurepath && \\
      pipx install poetry'

Or run the full ``setup-debian-machine`` script with sudo
prompt:

  ssh ${REMOTE_TARGET} 'cd ~/${REMOTE_PATH} && \\
      bash repository-setup/setup-debian-machine'

Or invoke this script once from a workstation WITHOUT
``--skip-system-setup`` so it runs setup-debian-machine
interactively.
EOF
        exit 5
    fi
    echo "    OK (git, python3, python3-venv, pipx, poetry, tmux, make, nginx)"
else
    echo "==> Step 2/8: system packages (apt, pipx poetry, nginx)"
    echo "    [you may be prompted for the remote sudo password]"
    run ssh -tt "${REMOTE_TARGET}" "cd ~/${REMOTE_PATH} && bash repository-setup/setup-debian-machine"
fi
echo

# ---------------------------------------------------------------------------
# Step 3 -- git URL rewrite for private codecraftai-* repos
# ---------------------------------------------------------------------------

if [ "${GIT_SOURCE_DEPENDENCIES}" -eq 0 ]; then
    echo "==> Step 3/8: SKIPPED -- pyproject.toml pulls no codecraftai-* dependency from git"
elif [ "${DRY_RUN}" = "true" ]; then
    # The token is never printed.
    echo "==> Step 3/8: configure git insteadOf for private codecraftai-* deps"
    echo "    [dry-run] would run: ssh ${REMOTE_TARGET} git config --global" \
         "url.https://x-access-token:***@github.com/automationmojo/.insteadOf https://github.com/automationmojo/"
else
    echo "==> Step 3/8: configure git insteadOf for private codecraftai-* deps"
    ssh "${REMOTE_TARGET}" \
        "git config --global url.\"https://x-access-token:${CODECRAFTAI_REPO_TOKEN}@github.com/automationmojo/\".insteadOf \"https://github.com/automationmojo/\""
    echo "    OK"
fi
echo

# ---------------------------------------------------------------------------
# Step 4 -- rehome-repository (generates .env with PYTHONPATH)
# ---------------------------------------------------------------------------

echo "==> Step 4/8: rehome-repository (generates .env)"
run ssh "${REMOTE_TARGET}" "cd ~/${REMOTE_PATH} && python3 repository-setup/rehome-repository --skip-workspaces"
echo

# ---------------------------------------------------------------------------
# Step 5 -- venv + poetry install
# ---------------------------------------------------------------------------

echo "==> Step 5/8: setup-environment (venv + poetry install)"
echo "    (installing the private codecraftai-* dependencies -- this can take a few minutes)"
# ``setup-environment`` is a Python script (shebanged
# ``#!/usr/bin/env python3``) -- invoke with python3 so its
# Python source isn't parsed as bash.  Wrap in ``bash -lc``
# so the deploy user's ~/.profile + ~/.bashrc are sourced and
# pipx-installed tools (specifically ``poetry``) are on PATH;
# setup-environment subprocesses ``poetry env use`` /
# ``poetry install`` and would fail otherwise.
run ssh "${REMOTE_TARGET}" "bash -lc 'cd ~/${REMOTE_PATH} && python3 development/setup-environment'"
echo

# ---------------------------------------------------------------------------
# Step 6 -- alembic upgrade head against per-checkout SQLite DB
#
# dev-up's defaults put the SQLite DB inside the checkout at
# .cache/dev-db/pychestrate.sqlite, so we run alembic against the
# same path so the next 'make dev-up' reuses it.
# ---------------------------------------------------------------------------

echo "==> Step 6/8: alembic upgrade head (sqlite in ~/pychestrate/)"
run_remote_script "database migration and service secrets" ssh "${REMOTE_TARGET}" <<'EOF'
set -euo pipefail
cd ~/pychestrate-service
# The SQLite DB lives in the pychestrate "presence directory"
# under the service user's $HOME -- NOT under the checkout's
# .cache/. ``setup-environment reset`` would otherwise wipe it.
# The dir is created mode 0700 here (idempotent) and ALSO at
# service-boot time by the systemd unit; both producers agree.
PRESENCE_DIR="$HOME/pychestrate"
mkdir -p "${PRESENCE_DIR}"
chmod 0700 "${PRESENCE_DIR}"
DB_PATH="${PRESENCE_DIR}/pychestrate.sqlite"
export PYCHESTRATE_DATABASE_URL="sqlite:///${DB_PATH}"
.venv/bin/alembic -c alembic.ini upgrade head
echo "    DB: ${DB_PATH}"
# Generate the service secrets now (KEK, pepper, cookie secret,
# envelope signing key, presign secret and the client-enrollment
# CA) rather than on first service start: step 7 points nginx's
# ssl_client_certificate at the enrollment CA certificate, so it
# must exist before nginx is reloaded.  Idempotent.
development/run-staging-gunicorn --provision-only
EOF
echo

# ---------------------------------------------------------------------------
# Step 7 -- nginx site config (reverse-proxy in front of the app)
#
# Writes /etc/nginx/sites-available/pychestrate, symlinks to
# sites-enabled/, removes the default site, runs ``nginx -t``,
# and ``systemctl reload nginx``.  Skipped under
# ``--skip-system-setup`` -- nginx config write requires sudo,
# which CI cannot satisfy.  CI deploys assume the workstation-
# driven first run already wrote a correct site config.
# ---------------------------------------------------------------------------

if [ "${SKIP_SYSTEM_SETUP}" = "true" ]; then
    echo "==> Step 7/8: SKIPPED (--skip-system-setup); nginx site assumed already configured"
else
    echo "==> Step 7/8: nginx site config (proxy ${PROXY_PORT} -> 127.0.0.1:${REMOTE_PORT})"
    echo "    [you may be prompted for the remote sudo password]"

    # Pre-flight: ensure the client-CA certificate exists on the
    # remote before we render an nginx config that references
    # it -- otherwise ``nginx -t`` would fail and the deploy
    # would refuse to reload.
    if [ "${DRY_RUN}" = "true" ]; then
        echo "    [dry-run] would check that ${CLIENT_CA_PATH} exists on ${REMOTE_TARGET} (step 6 creates it)"
    elif ! ssh "${REMOTE_TARGET}" "test -f ${CLIENT_CA_PATH}"; then
        cat >&2 <<EOF
ERROR: client-CA cert ${CLIENT_CA_PATH} missing on ${REMOTE_TARGET}.

nginx verifies pod client certificates against the service's
client-enrollment CA -- the CA that signs every pod certificate
at enrollment.  Step 6 generates it by running

    development/run-staging-gunicorn --provision-only

in the remote checkout, which writes the CA to
.cache/dev-secrets/dev.enrollment-ca.pem and its certificate to
.cache/dev-secrets/dev.enrollment-ca.crt.  If the service loads
its enrollment CA from somewhere else
(PYCHESTRATE_ENROLLMENT_CA_FILE_PATH), pass that CA's
certificate with --client-ca-path.
EOF
        exit 6
    fi

    # Render the nginx site config locally (interpolates the
    # proxy + app ports) and the install-script that places it.
    # scp both to /tmp on the remote, then ``ssh -t`` to execute.
    #
    # NOT using ``ssh -tt ... "bash -s" <<EOF`` here -- that
    # pattern hangs sudo's password prompt because the heredoc
    # captures ssh's stdin, leaving the operator's keystrokes
    # with nowhere to land.  Sending the script via scp + a
    # one-shot ``ssh -t`` keeps ssh's stdin = the operator's
    # local terminal so sudo can prompt normally.
    NGINX_CONF_LOCAL="$(mktemp)"
    # The site config lives in deployment/pychestrate.nginx.conf.template
    # (so it can be reviewed and syntax-checked on its own); render
    # its placeholders here.  ``|`` is the sed delimiter because the
    # CA path contains slashes.
    sed \
        -e "s|@PROXY_PORT@|${PROXY_PORT}|g" \
        -e "s|@REMOTE_PORT@|${REMOTE_PORT}|g" \
        -e "s|@PUBLIC_HOSTNAME@|${PUBLIC_HOSTNAME}|g" \
        -e "s|@CLIENT_CA_PATH@|${CLIENT_CA_PATH}|g" \
        "${REPO_ROOT}/deployment/pychestrate.nginx.conf.template" \
        > "${NGINX_CONF_LOCAL}"

    NGINX_INSTALL_LOCAL="$(mktemp)"
    cat > "${NGINX_INSTALL_LOCAL}" <<'NGINX_INSTALL'
#!/usr/bin/env bash
set -euo pipefail

SITE_AVAILABLE="/etc/nginx/sites-available/pychestrate"
SITE_ENABLED="/etc/nginx/sites-enabled/pychestrate"
SITE_DEFAULT="/etc/nginx/sites-enabled/default"

# Use ``install`` to combine mv + chown + chmod into a single
# privileged operation -- shrinks the sudoers whitelist
# surface in deployment/sudoers.d/pychestrate-deploy.template.
sudo install -m 0644 -o root -g root \
    /tmp/pychestrate.nginx.conf "${SITE_AVAILABLE}"

sudo ln -sfn "${SITE_AVAILABLE}" "${SITE_ENABLED}"

# Remove the stock default site -- it would otherwise win
# for any request to the default server name.
if [ -e "${SITE_DEFAULT}" ]; then
    sudo rm -f "${SITE_DEFAULT}"
fi

sudo nginx -t
sudo systemctl reload nginx

echo "    nginx reloaded; site enabled at ${SITE_ENABLED}"
NGINX_INSTALL

    run scp -q "${NGINX_CONF_LOCAL}"    "${REMOTE_TARGET}:/tmp/pychestrate.nginx.conf"
    run scp -q "${NGINX_INSTALL_LOCAL}" "${REMOTE_TARGET}:/tmp/pychestrate.nginx.install.sh"
    rm -f "${NGINX_CONF_LOCAL}" "${NGINX_INSTALL_LOCAL}"

    run ssh -t "${REMOTE_TARGET}" "bash /tmp/pychestrate.nginx.install.sh && rm -f /tmp/pychestrate.nginx.install.sh"
fi
echo

# ---------------------------------------------------------------------------
# Step 8 -- install systemd unit + restart pychestrate.service
#
# The unit template at ``deployment/pychestrate.service.template``
# gets rendered locally (``@USER@`` / ``@PORT@`` substitution) then
# scp'd to /tmp on the remote and sudo-mv'd into
# /etc/systemd/system/.  systemd then runs gunicorn under
# ``run-staging-gunicorn`` (which auto-generates secrets on first
# run and binds 127.0.0.1:${REMOTE_PORT} -- nginx fronts it).
#
# Unit install is gated on --skip-system-setup (sudo is interactive
# in unit install).  Once installed, ``systemctl restart`` is
# unprivileged on a system that grants the deploy user a polkit
# rule, OR the deploy script falls back to ``sudo systemctl
# restart`` which DOES require sudo on every restart.
#
# To avoid that re-prompt cycle, the simplest operator setup is to
# add a sudoers.d entry granting the deploy user passwordless
# ``systemctl restart pychestrate.service``.  See
# deployment/README.md for details.
# ---------------------------------------------------------------------------

if [ "${SKIP_SYSTEM_SETUP}" = "true" ]; then
    echo "==> Step 8/8: SKIPPED systemd-unit install (--skip-system-setup);" \
                  "restarting pychestrate.service"
    # CI uses sudo with NOPASSWD on systemctl restart (configured
    # by the operator's first interactive deploy below).  If the
    # operator has not configured passwordless restart, this will
    # hang in CI and time out -- the script's ssh BatchMode probe
    # earlier catches that case.
    run ssh "${REMOTE_TARGET}" "sudo systemctl restart pychestrate.service && sudo systemctl --no-pager status pychestrate.service | head -8"
else
    echo "==> Step 8/8: rendering + installing pychestrate.service systemd unit"
    echo "    [you may be prompted for the remote sudo password]"

    # Render the unit template locally, then scp BOTH the unit
    # and a thin install-script that handles sudo-mv + chown +
    # daemon-reload + enable + restart.  Run via a single
    # ``ssh -t``.
    #
    # NOT using ``ssh -tt ... "bash -s" <<EOF`` here -- that
    # pattern hangs sudo's password prompt because the heredoc
    # captures ssh's stdin, leaving the operator's keystrokes
    # with nowhere to land.  scp + ssh -t keeps ssh's stdin =
    # the local terminal so sudo can prompt cleanly.
    UNIT_LOCAL="$(mktemp)"
    sed \
        -e "s|@USER@|${REMOTE_USER}|g" \
        -e "s|@PORT@|${REMOTE_PORT}|g" \
        -e "s|@PUBLIC_HOSTNAME@|${PUBLIC_HOSTNAME}|g" \
        "${REPO_ROOT}/deployment/pychestrate.service.template" \
        > "${UNIT_LOCAL}"

    # Scheduled backup: a oneshot unit + its daily timer.
    BACKUP_UNIT_LOCAL="$(mktemp)"
    sed \
        -e "s|@USER@|${REMOTE_USER}|g" \
        "${REPO_ROOT}/deployment/pychestrate-backup.service.template" \
        > "${BACKUP_UNIT_LOCAL}"
    BACKUP_TIMER_LOCAL="$(mktemp)"
    cp "${REPO_ROOT}/deployment/pychestrate-backup.timer.template" "${BACKUP_TIMER_LOCAL}"

    # Log rotation for the files the units append to.
    LOGROTATE_LOCAL="$(mktemp)"
    sed \
        -e "s|@USER@|${REMOTE_USER}|g" \
        "${REPO_ROOT}/deployment/pychestrate.logrotate.template" \
        > "${LOGROTATE_LOCAL}"

    UNIT_INSTALL_LOCAL="$(mktemp)"
    cat > "${UNIT_INSTALL_LOCAL}" <<UNIT_INSTALL
#!/usr/bin/env bash
set -euo pipefail

# Pre-create the log directory so systemd can append to it on
# the very first start.
mkdir -p ~/.pychestrate
touch ~/.pychestrate/server.log
chmod 0644 ~/.pychestrate/server.log

# Pre-create the pychestrate "presence directory" mode 0700.
# Lives under \$HOME so no sudo is needed; survives any
# ``setup-environment reset`` (which only wipes the checkout's
# .cache/). Holds the SQLite DB + the initial-admin-token.
mkdir -p ~/pychestrate
chmod 0700 ~/pychestrate

# Backup archives and key bundles (see pychestrate-backup.service).
# Both 0700: an archive is the whole database, a key bundle holds
# the KEK.  Copy them off the host -- to different places.
mkdir -p ~/pychestrate/backups ~/pychestrate/backup-keys
chmod 0700 ~/pychestrate/backups ~/pychestrate/backup-keys
touch ~/.pychestrate/backup.log
chmod 0644 ~/.pychestrate/backup.log

# \`\`install\`\` combines mv + chown + chmod into a single
# privileged operation -- shrinks the sudoers whitelist
# surface in deployment/sudoers.d/pychestrate-deploy.template.
sudo install -m 0644 -o root -g root \\
    /tmp/pychestrate.service /etc/systemd/system/pychestrate.service
sudo install -m 0644 -o root -g root \\
    /tmp/pychestrate-backup.service /etc/systemd/system/pychestrate-backup.service
sudo install -m 0644 -o root -g root \\
    /tmp/pychestrate-backup.timer /etc/systemd/system/pychestrate-backup.timer
sudo install -m 0644 -o root -g root \\
    /tmp/pychestrate.logrotate /etc/logrotate.d/pychestrate

sudo systemctl daemon-reload
sudo systemctl enable pychestrate.service
sudo systemctl restart pychestrate.service
sudo systemctl enable --now pychestrate-backup.timer

echo
echo "pychestrate.service status:"
sudo systemctl --no-pager status pychestrate.service | head -10
UNIT_INSTALL

    run scp -q "${UNIT_LOCAL}"         "${REMOTE_TARGET}:/tmp/pychestrate.service"
    run scp -q "${BACKUP_UNIT_LOCAL}"  "${REMOTE_TARGET}:/tmp/pychestrate-backup.service"
    run scp -q "${BACKUP_TIMER_LOCAL}" "${REMOTE_TARGET}:/tmp/pychestrate-backup.timer"
    run scp -q "${LOGROTATE_LOCAL}"    "${REMOTE_TARGET}:/tmp/pychestrate.logrotate"
    run scp -q "${UNIT_INSTALL_LOCAL}" "${REMOTE_TARGET}:/tmp/pychestrate.systemd.install.sh"
    rm -f "${UNIT_LOCAL}" "${BACKUP_UNIT_LOCAL}" "${BACKUP_TIMER_LOCAL}" "${LOGROTATE_LOCAL}" "${UNIT_INSTALL_LOCAL}"

    run ssh -t "${REMOTE_TARGET}" "bash /tmp/pychestrate.systemd.install.sh && rm -f /tmp/pychestrate.systemd.install.sh"
fi
echo

# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

if [ "${DRY_RUN}" = "true" ]; then
    echo "==> Probe: [dry-run] would poll http://${REMOTE_HOST}:${PROXY_PORT}/ until it answers"
    echo
    echo "================================================================"
    echo "  DRY RUN COMPLETE -- nothing was changed on ${REMOTE_TARGET}"
    echo "  or locally.  Run again without --dry-run to deploy."
    echo "================================================================"
    exit 0
fi

echo "==> Probing http://${REMOTE_HOST}:${PROXY_PORT}/"
sleep 4
PROBE_URL="http://${REMOTE_HOST}:${PROXY_PORT}/"
for attempt in 1 2 3 4 5 6 7 8; do
    if curl -fsS -m 5 -o /dev/null "${PROBE_URL}"; then
        echo
        echo "================================================================"
        echo "  DEPLOY COMPLETE"
        echo "================================================================"
        echo "  consumer UI : http://${REMOTE_HOST}:${PROXY_PORT}/config"
        echo "  rest API    : http://${REMOTE_HOST}:${PROXY_PORT}/api/v1/"
        echo "  proxy port  : ${PROXY_PORT}    (nginx)"
        echo "  app port    : ${REMOTE_PORT}  (loopback only)"
        echo "  service     : pychestrate.service (systemd)"
        echo "  liveness    : https://${PUBLIC_HOSTNAME}/livez  (readiness: /readyz)"
        echo "  metrics     : https://${PUBLIC_HOSTNAME}/metrics  (Bearer token: ~/pychestrate-service/.cache/dev-secrets/dev.metrics-token)"
        echo "  status      : ssh ${REMOTE_TARGET} sudo systemctl status pychestrate"
        echo "  live logs   : ssh ${REMOTE_TARGET} sudo journalctl -u pychestrate -f"
        echo "  log file    : ssh ${REMOTE_TARGET} 'tail -f ~/.pychestrate/server.log'"
        echo "  restart     : ssh ${REMOTE_TARGET} sudo systemctl restart pychestrate"
        echo "  stop        : ssh ${REMOTE_TARGET} sudo systemctl stop pychestrate"
        echo "================================================================"
        exit 0
    fi
    echo "    attempt ${attempt}/8 -- still warming up, waiting 5s ..."
    sleep 5
done

cat >&2 <<EOF

ERROR: Service started but did not respond to probe within 40s.

Investigate from a fresh shell:

  ssh ${REMOTE_TARGET} sudo systemctl status pychestrate
  ssh ${REMOTE_TARGET} sudo journalctl -u pychestrate -n 200 --no-pager
  ssh ${REMOTE_TARGET} 'tail -100 ~/.pychestrate/server.log'

If the service is up but nginx isn't proxying correctly:

  ssh ${REMOTE_TARGET} sudo nginx -T
  ssh ${REMOTE_TARGET} sudo systemctl status nginx
EOF
exit 4
