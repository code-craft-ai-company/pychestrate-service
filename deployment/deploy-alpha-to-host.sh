#!/usr/bin/env bash
#
# deploy-alpha-to-host.sh -- one-shot alpha deploy from a workstation
# to a remote host via SSH.
#
# Drives the existing repository-setup + development bootstrap chain
# remotely:
#
#   1. rsync the working tree to ``<remote>:~/pychestrate-service``
#      (excludes the venv, output, cache, .claude, .git).
#   2. Configure git credentials on the remote so the nine private
#      ``automojo-*`` git-source deps can be cloned (uses
#      ``AUTOMOJO_REPO_TOKEN`` from the local env -- the same
#      mechanism as CI).
#   3. ``repository-setup/setup-debian-machine``    -- system apt
#      packages + poetry via pipx.  Requires sudo on the remote;
#      the user is prompted interactively.
#   4. ``repository-setup/rehome-repository``        -- generates
#      ``.env`` with PYTHONPATH composition.
#   5. ``development/setup-environment``             -- creates
#      ``.venv`` and runs ``poetry install``.
#   6. ``alembic upgrade head``                       -- against a
#      SQLite DB at ``~/.pychestrate/pychestrate.sqlite``.
#   7. ``make dev-up``                                -- starts the
#      service in a tmux session named ``pychestrate``.  The
#      ``dev-up`` script auto-generates KEK / pepper / cookie-secret
#      under ``.cache/dev-secrets/``.  Bind override
#      (``PYCHESTRATE_BIND_HOST=0.0.0.0``) makes the service
#      reachable from the rest of the LAN.
#   8. probe ``http://<host>:<port>/`` from the workstation to
#      confirm the service is serving.
#
# Usage:
#
#   AUTOMOJO_REPO_TOKEN=ghp_xxx \
#       deployment/deploy-alpha-to-host.sh \
#           [--host=tc-app-server.local] \
#           [--user=myron] \
#           [--port=8888]
#
# Defaults: tc-app-server.local / myron / 8888.
#
# Idempotent: re-running the script syncs new code + restarts the
# service.  KEK / pepper / cookie-secret + the SQLite DB persist
# across runs (under ``.cache/dev-secrets/`` and ``.cache/dev-db/``
# inside the remote checkout).

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults + arg parsing
# ---------------------------------------------------------------------------

REMOTE_HOST="tc-app-server.local"
REMOTE_USER="myron"
REMOTE_PORT="8888"
SKIP_SYSTEM_SETUP="false"

while [ $# -gt 0 ]; do
    case "$1" in
        --host=*) REMOTE_HOST="${1#*=}" ;;
        --user=*) REMOTE_USER="${1#*=}" ;;
        --port=*) REMOTE_PORT="${1#*=}" ;;
        --skip-system-setup) SKIP_SYSTEM_SETUP="true" ;;
        --help|-h)
            sed -n '2,/^set -euo/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            echo "       Run with --help for usage." >&2
            exit 1
            ;;
    esac
    shift
done

REMOTE_TARGET="${REMOTE_USER}@${REMOTE_HOST}"
REMOTE_PATH="pychestrate-service"  # relative to remote $HOME

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

echo "================================================================"
echo "  pychestrate-service alpha deploy"
echo "================================================================"
echo "  source repo : ${REPO_ROOT}"
echo "  target      : ${REMOTE_TARGET}"
echo "  bind port   : ${REMOTE_PORT}"
echo "================================================================"
echo

if [ -z "${AUTOMOJO_REPO_TOKEN:-}" ]; then
    cat >&2 <<EOF
ERROR: AUTOMOJO_REPO_TOKEN is not set.

The deploy installs nine private git-source dependencies under the
'automationmojo' GitHub org.  Without a Personal Access Token, the
remote's 'poetry install' step will fail.

Set the same fine-grained PAT you configured for CI as
AUTOMOJO_REPO_TOKEN before re-running.  Required scope on the
'automationmojo' org: Contents -- Read.

  export AUTOMOJO_REPO_TOKEN=ghp_xxx
  deployment/deploy-alpha-to-host.sh
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
# Step 1 -- rsync the working tree
# ---------------------------------------------------------------------------

echo "==> Step 1/7: rsync repo to ${REMOTE_TARGET}:~/${REMOTE_PATH}/"
ssh "${REMOTE_TARGET}" "mkdir -p ~/${REMOTE_PATH}"

rsync -az --delete --info=progress2 \
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
echo

# ---------------------------------------------------------------------------
# Step 2 -- system apt packages (build-essential, python3, poetry)
#
# Uses ``ssh -t`` so the sudo prompt inside setup-debian-machine
# can read a TTY.
#
# Skipped under ``--skip-system-setup`` -- CI cannot satisfy an
# interactive sudo prompt, so the CI deploy workflow assumes the
# target was pre-provisioned by a workstation-driven first run.
# ---------------------------------------------------------------------------

if [ "${SKIP_SYSTEM_SETUP}" = "true" ]; then
    echo "==> Step 2/7: SKIPPED (--skip-system-setup); target assumed pre-provisioned"
else
    echo "==> Step 2/7: system packages (apt, pipx poetry)"
    echo "    [you may be prompted for the remote sudo password]"
    ssh -t "${REMOTE_TARGET}" "cd ~/${REMOTE_PATH} && bash repository-setup/setup-debian-machine"
fi
echo

# ---------------------------------------------------------------------------
# Step 3 -- git URL rewrite for private automojo-* repos
# ---------------------------------------------------------------------------

echo "==> Step 3/7: configure git insteadOf for private automojo-* deps"
ssh "${REMOTE_TARGET}" \
    "git config --global url.\"https://x-access-token:${AUTOMOJO_REPO_TOKEN}@github.com/automationmojo/\".insteadOf \"https://github.com/automationmojo/\""
echo "    OK"
echo

# ---------------------------------------------------------------------------
# Step 4 -- rehome-repository (generates .env with PYTHONPATH)
# ---------------------------------------------------------------------------

echo "==> Step 4/7: rehome-repository (generates .env)"
ssh "${REMOTE_TARGET}" "cd ~/${REMOTE_PATH} && python3 repository-setup/rehome-repository --skip-workspaces"
echo

# ---------------------------------------------------------------------------
# Step 5 -- venv + poetry install
# ---------------------------------------------------------------------------

echo "==> Step 5/7: setup-environment (venv + poetry install)"
echo "    (cloning nine private deps -- this can take 60-120 sec)"
ssh "${REMOTE_TARGET}" "cd ~/${REMOTE_PATH} && bash development/setup-environment"
echo

# ---------------------------------------------------------------------------
# Step 6 -- alembic upgrade head against per-checkout SQLite DB
#
# dev-up's defaults put the SQLite DB inside the checkout at
# .cache/dev-db/pychestrate.sqlite, so we run alembic against the
# same path so the next 'make dev-up' reuses it.
# ---------------------------------------------------------------------------

echo "==> Step 6/7: alembic upgrade head (sqlite, schema + legacy)"
ssh "${REMOTE_TARGET}" <<'EOF'
set -euo pipefail
cd ~/pychestrate-service
mkdir -p .cache/dev-db
DB_PATH="$HOME/pychestrate-service/.cache/dev-db/pychestrate.sqlite"
export PYCHESTRATE_DATABASE_URL="sqlite:///${DB_PATH}"
.venv/bin/alembic -c alembic.ini upgrade head
echo "    DB: ${DB_PATH}"
EOF
echo

# ---------------------------------------------------------------------------
# Step 7 -- start the service in tmux
#
# We start under ``tmux`` so the service survives the ssh
# disconnect.  ``make dev-up`` already auto-generates KEK / pepper /
# UI cookie secret and binds via PYCHESTRATE_BIND_*.
# ---------------------------------------------------------------------------

echo "==> Step 7/7: starting service via 'make dev-up' in tmux"
ssh "${REMOTE_TARGET}" REMOTE_PORT="${REMOTE_PORT}" "bash -s" <<'EOF'
set -euo pipefail
cd ~/pychestrate-service

# Stop any existing tmux session named 'pychestrate'.
tmux kill-session -t pychestrate 2>/dev/null || true

# Start a fresh session.  The redirect into ~/.pychestrate/server.log
# is the canonical place to find logs after disconnecting.
mkdir -p ~/.pychestrate
LOG_PATH="$HOME/.pychestrate/server.log"

# 'make dev-up' inherits PYCHESTRATE_BIND_HOST/PORT from env.
# 0.0.0.0 + ${REMOTE_PORT} makes the service reachable from the LAN.
tmux new-session -d -s pychestrate \
    "cd ~/pychestrate-service && PYCHESTRATE_BIND_HOST=0.0.0.0 PYCHESTRATE_BIND_PORT=${REMOTE_PORT} make dev-up 2>&1 | tee ${LOG_PATH}"

echo "    started in tmux session 'pychestrate'"
echo "    logs:   ${LOG_PATH}"
echo "    attach: ssh ${USER}@${HOSTNAME} -t tmux attach -t pychestrate"
EOF
echo

# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

echo "==> Probing http://${REMOTE_HOST}:${REMOTE_PORT}/"
sleep 4
PROBE_URL="http://${REMOTE_HOST}:${REMOTE_PORT}/"
for attempt in 1 2 3 4 5 6 7 8; do
    if curl -fsS -m 5 -o /dev/null "${PROBE_URL}"; then
        echo
        echo "================================================================"
        echo "  DEPLOY COMPLETE"
        echo "================================================================"
        echo "  consumer UI : http://${REMOTE_HOST}:${REMOTE_PORT}/config"
        echo "  rest API    : http://${REMOTE_HOST}:${REMOTE_PORT}/api/v1/"
        echo "  attach logs : ssh ${REMOTE_TARGET} -t tmux attach -t pychestrate"
        echo "  stop server : ssh ${REMOTE_TARGET} tmux kill-session -t pychestrate"
        echo "================================================================"
        exit 0
    fi
    echo "    attempt ${attempt}/8 -- still warming up, waiting 5s ..."
    sleep 5
done

cat >&2 <<EOF

ERROR: Service started but did not respond to probe within 40s.

Investigate from a fresh shell:

  ssh ${REMOTE_TARGET} -t tmux attach -t pychestrate

Or tail the log:

  ssh ${REMOTE_TARGET} 'tail -f ~/.pychestrate/server.log'
EOF
exit 4
