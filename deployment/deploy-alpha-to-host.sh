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
#                                  tc-app-server
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
#   3. Configure git credentials on the remote so the nine private
#      ``automojo-*`` git-source deps can be cloned (uses
#      ``AUTOMOJO_REPO_TOKEN`` from the local env or repo-root
#      ``.env`` -- the same mechanism as CI).
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
#   8. ``make dev-up``                                -- starts the
#      service in a tmux session named ``pychestrate`` bound to
#      ``127.0.0.1:--port``.  ``dev-up`` auto-generates KEK /
#      pepper / cookie-secret under ``.cache/dev-secrets/``.
#   9. probe ``http://<host>:<proxy-port>/`` from the workstation
#      to confirm nginx + app are serving end-to-end.
#
# Usage:
#
#   AUTOMOJO_REPO_TOKEN=ghp_xxx \
#       deployment/deploy-alpha-to-host.sh \
#           [--host=tc-app-server.local] \
#           [--user=myron] \
#           [--port=8888] \
#           [--proxy-port=80] \
#           [--skip-system-setup]
#
# Defaults: tc-app-server.local / myron / app-port 8888 / proxy 80.
#
# Idempotent: re-running the script syncs new code, refreshes the
# nginx config, and restarts the service.  KEK / pepper /
# cookie-secret + the SQLite DB persist across runs (under
# ``.cache/dev-secrets/`` and ``.cache/dev-db/`` inside the remote
# checkout).

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults + arg parsing
# ---------------------------------------------------------------------------

REMOTE_HOST="tc-app-server.local"
REMOTE_USER="myron"
REMOTE_PORT="8888"          # internal app port (nginx proxies to this)
PROXY_PORT="80"             # external port nginx listens on
SKIP_SYSTEM_SETUP="false"

while [ $# -gt 0 ]; do
    case "$1" in
        --host=*) REMOTE_HOST="${1#*=}" ;;
        --user=*) REMOTE_USER="${1#*=}" ;;
        --port=*) REMOTE_PORT="${1#*=}" ;;
        --proxy-port=*) PROXY_PORT="${1#*=}" ;;
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
# Source repo-root .env (if present)
#
# Pulls in any operator-set environment variables -- most notably
# ``AUTOMOJO_REPO_TOKEN`` -- so the operator does not have to
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

echo "==> Step 1/8: rsync repo to ${REMOTE_TARGET}:~/${REMOTE_PATH}/"
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
    echo "==> Step 2/8: --skip-system-setup; verifying prerequisites on target"
    # Probe each required tool individually so the failure
    # message lists every missing one, not just the first.
    MISSING=$(ssh "${REMOTE_TARGET}" '
        missing=""
        for cmd in git python3 pipx poetry tmux make nginx; do
            command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
        done
        # python3-venv is a separate package -- check by trying
        # to invoke its module.
        python3 -c "import venv" >/dev/null 2>&1 || missing="$missing python3-venv"
        echo "$missing" | tr -s " "
    ')
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
    ssh -t "${REMOTE_TARGET}" "cd ~/${REMOTE_PATH} && bash repository-setup/setup-debian-machine"
fi
echo

# ---------------------------------------------------------------------------
# Step 3 -- git URL rewrite for private automojo-* repos
# ---------------------------------------------------------------------------

echo "==> Step 3/8: configure git insteadOf for private automojo-* deps"
ssh "${REMOTE_TARGET}" \
    "git config --global url.\"https://x-access-token:${AUTOMOJO_REPO_TOKEN}@github.com/automationmojo/\".insteadOf \"https://github.com/automationmojo/\""
echo "    OK"
echo

# ---------------------------------------------------------------------------
# Step 4 -- rehome-repository (generates .env with PYTHONPATH)
# ---------------------------------------------------------------------------

echo "==> Step 4/8: rehome-repository (generates .env)"
ssh "${REMOTE_TARGET}" "cd ~/${REMOTE_PATH} && python3 repository-setup/rehome-repository --skip-workspaces"
echo

# ---------------------------------------------------------------------------
# Step 5 -- venv + poetry install
# ---------------------------------------------------------------------------

echo "==> Step 5/8: setup-environment (venv + poetry install)"
echo "    (cloning nine private deps -- this can take 60-120 sec)"
# ``setup-environment`` is a Python script (shebanged
# ``#!/usr/bin/env python3``) -- invoke with python3 so its
# Python source isn't parsed as bash.
ssh "${REMOTE_TARGET}" "cd ~/${REMOTE_PATH} && python3 development/setup-environment"
echo

# ---------------------------------------------------------------------------
# Step 6 -- alembic upgrade head against per-checkout SQLite DB
#
# dev-up's defaults put the SQLite DB inside the checkout at
# .cache/dev-db/pychestrate.sqlite, so we run alembic against the
# same path so the next 'make dev-up' reuses it.
# ---------------------------------------------------------------------------

echo "==> Step 6/8: alembic upgrade head (sqlite, schema + legacy)"
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
    ssh -t "${REMOTE_TARGET}" \
        REMOTE_PORT="${REMOTE_PORT}" \
        PROXY_PORT="${PROXY_PORT}" \
        "bash -s" <<'EOF'
set -euo pipefail

SITE_AVAILABLE="/etc/nginx/sites-available/pychestrate"
SITE_ENABLED="/etc/nginx/sites-enabled/pychestrate"
SITE_DEFAULT="/etc/nginx/sites-enabled/default"

# Render the site config to a tempfile then sudo-mv into place
# so the operator only types their password once for the whole
# config block.
TMP="$(mktemp)"
cat > "${TMP}" <<NGINX_CONF
# pychestrate-service alpha -- generated by deployment/deploy-alpha-to-host.sh
# DO NOT EDIT BY HAND; re-run the deploy to refresh.

server {
    listen ${PROXY_PORT} default_server;
    listen [::]:${PROXY_PORT} default_server;

    server_name _;

    # Generous body limit -- the service has uploads
    # (artifacts, logs) and 1MiB nginx default is too tight.
    client_max_body_size 50M;

    # Health probes / static / the WSGI app -- all routed to
    # the same upstream.
    location / {
        proxy_pass http://127.0.0.1:${REMOTE_PORT};
        proxy_http_version 1.1;

        # Forward original client info so the app can log /
        # rate-limit on real client identity.
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host  \$host;

        # WebSocket / long-poll friendliness.
        proxy_set_header Upgrade           \$http_upgrade;
        proxy_set_header Connection        "upgrade";

        # Long-running HTTP requests (alembic-driven imports,
        # artifact uploads, etc).  Gunicorn's worker timeout
        # ultimately bounds this; nginx just shouldn't be the
        # short-circuit.
        proxy_connect_timeout 30s;
        proxy_send_timeout    300s;
        proxy_read_timeout    300s;
    }
}
NGINX_CONF

sudo mv "${TMP}" "${SITE_AVAILABLE}"
sudo chown root:root "${SITE_AVAILABLE}"
sudo chmod 0644 "${SITE_AVAILABLE}"

sudo ln -sfn "${SITE_AVAILABLE}" "${SITE_ENABLED}"

# Remove the stock default site if it's still around.  It
# would otherwise win for any request to ${PROXY_PORT} on the
# default server name.
if [ -e "${SITE_DEFAULT}" ]; then
    sudo rm -f "${SITE_DEFAULT}"
fi

sudo nginx -t
sudo systemctl reload nginx

echo "    nginx reloaded; site enabled at ${SITE_ENABLED}"
EOF
fi
echo

# ---------------------------------------------------------------------------
# Step 8 -- start the service in tmux
#
# We start under ``tmux`` so the service survives the ssh
# disconnect.  ``make dev-up`` already auto-generates KEK / pepper /
# UI cookie secret and binds via PYCHESTRATE_BIND_*.  Bind on
# 127.0.0.1 -- the app is no longer directly exposed externally;
# nginx fronts it on ${PROXY_PORT}.
# ---------------------------------------------------------------------------

echo "==> Step 8/8: starting service via 'make dev-up' in tmux (loopback only)"
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
# 127.0.0.1 binds the app to loopback only -- nginx (Step 7)
# is the public-facing surface.
tmux new-session -d -s pychestrate \
    "cd ~/pychestrate-service && PYCHESTRATE_BIND_HOST=127.0.0.1 PYCHESTRATE_BIND_PORT=${REMOTE_PORT} make dev-up 2>&1 | tee ${LOG_PATH}"

echo "    started in tmux session 'pychestrate'"
echo "    logs:   ${LOG_PATH}"
echo "    attach: ssh ${USER}@${HOSTNAME} -t tmux attach -t pychestrate"
EOF
echo

# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

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
