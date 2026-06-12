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
#      ``codecraftai-*`` git-source deps can be cloned (uses
#      ``CODECRAFTAI_REPO_TOKEN`` from the local env or repo-root
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
#   8. Install ``pychestrate.service`` systemd unit (rendered
#      from ``deployment/pychestrate.service.template``) + start
#      / restart the service.  The unit invokes
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
# Usage:
#
#   CODECRAFTAI_REPO_TOKEN=ghp_xxx \
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
# Canonical public hostname for the deploy -- must match the
# subject on the TLS cert at /etc/nginx/ssl/pychestrate.crt.
# The :80 redirect lands users here regardless of what they
# typed (bare ``tc-app-server`` vs. full tailnet name), so
# the browser never sees a cert/hostname mismatch.
PUBLIC_HOSTNAME="tc-app-server.tailb75ce6.ts.net"
SKIP_SYSTEM_SETUP="false"
# Path on the REMOTE to the CA cert used by nginx to verify
# incoming client certificates for the mTLS-gated routes
# (orchestration-ingest endpoints).  The deploy errors out
# if this file does not exist on the remote -- bootstrap it
# with ``deployment/bootstrap-client-ca.sh`` first.
CLIENT_CA_PATH="/etc/nginx/ssl/client-ca.crt"

while [ $# -gt 0 ]; do
    case "$1" in
        --host=*) REMOTE_HOST="${1#*=}" ;;
        --user=*) REMOTE_USER="${1#*=}" ;;
        --port=*) REMOTE_PORT="${1#*=}" ;;
        --proxy-port=*) PROXY_PORT="${1#*=}" ;;
        --public-hostname=*) PUBLIC_HOSTNAME="${1#*=}" ;;
        --client-ca-path=*) CLIENT_CA_PATH="${1#*=}" ;;
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
echo "================================================================"
echo

if [ -z "${CODECRAFTAI_REPO_TOKEN:-}" ]; then
    cat >&2 <<EOF
ERROR: CODECRAFTAI_REPO_TOKEN is not set.

The deploy installs nine private git-source dependencies under the
'automationmojo' GitHub org.  Without a Personal Access Token, the
remote's 'poetry install' step will fail.

Set the same fine-grained PAT you configured for CI as
CODECRAFTAI_REPO_TOKEN before re-running.  Required scope on the
'automationmojo' org: Contents -- Read.

  export CODECRAFTAI_REPO_TOKEN=ghp_xxx
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
bash "${REPO_ROOT}/development/build-frontend.sh"
echo

# ---------------------------------------------------------------------------
# Step 1 -- rsync the working tree
# ---------------------------------------------------------------------------

echo "==> Step 1/8: rsync repo to ${REMOTE_TARGET}:~/${REMOTE_PATH}/"
ssh "${REMOTE_TARGET}" "mkdir -p ~/${REMOTE_PATH}"

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

rsync -az --delete "${RSYNC_PROGRESS_OPT}" \
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
    ssh -tt "${REMOTE_TARGET}" "cd ~/${REMOTE_PATH} && bash repository-setup/setup-debian-machine"
fi
echo

# ---------------------------------------------------------------------------
# Step 3 -- git URL rewrite for private codecraftai-* repos
# ---------------------------------------------------------------------------

echo "==> Step 3/8: configure git insteadOf for private codecraftai-* deps"
ssh "${REMOTE_TARGET}" \
    "git config --global url.\"https://x-access-token:${CODECRAFTAI_REPO_TOKEN}@github.com/automationmojo/\".insteadOf \"https://github.com/automationmojo/\""
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
# Python source isn't parsed as bash.  Wrap in ``bash -lc``
# so the deploy user's ~/.profile + ~/.bashrc are sourced and
# pipx-installed tools (specifically ``poetry``) are on PATH;
# setup-environment subprocesses ``poetry env use`` /
# ``poetry install`` and would fail otherwise.
ssh "${REMOTE_TARGET}" "bash -lc 'cd ~/${REMOTE_PATH} && python3 development/setup-environment'"
echo

# ---------------------------------------------------------------------------
# Step 6 -- alembic upgrade head against per-checkout SQLite DB
#
# dev-up's defaults put the SQLite DB inside the checkout at
# .cache/dev-db/pychestrate.sqlite, so we run alembic against the
# same path so the next 'make dev-up' reuses it.
# ---------------------------------------------------------------------------

echo "==> Step 6/8: alembic upgrade head (sqlite in ~/pychestrate/)"
ssh "${REMOTE_TARGET}" <<'EOF'
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

    # Pre-flight: ensure the client-CA bundle exists on the
    # remote before we render an nginx config that references
    # it -- otherwise ``nginx -t`` would fail and the deploy
    # would refuse to reload.
    if ! ssh "${REMOTE_TARGET}" "test -f ${CLIENT_CA_PATH}"; then
        cat >&2 <<EOF
ERROR: client-CA cert ${CLIENT_CA_PATH} missing on ${REMOTE_TARGET}.

The nginx :443 server block now requires a client-CA bundle to
verify incoming client certificates for the mTLS-gated
orchestration-ingest endpoints (/api/v1/runs/<id>/{progress,
results/complete,dispatch-ack}).

Bootstrap it once with the dedicated script:

    deployment/bootstrap-client-ca.sh \\
        --host=${REMOTE_HOST} --user=${REMOTE_USER}

That generates a self-signed root CA at
${CLIENT_CA_PATH} (and the corresponding key at
\${CLIENT_CA_PATH%.crt}.key, mode 0600 root) if one does not
already exist.  Then re-run this deploy.
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
    cat > "${NGINX_CONF_LOCAL}" <<NGINX_CONF
# pychestrate-service alpha -- generated by deployment/deploy-alpha-to-host.sh
# DO NOT EDIT BY HAND; re-run the deploy to refresh.

# Derive the client-certificate Common Name from the verified
# subject DN. Stock nginx exposes \$ssl_client_s_dn (RFC2253
# format, e.g. ``CN=worker1,O=codecraftai``) but has no built-in
# CN accessor -- this map extracts it so the orchestration-ingest
# location blocks can forward it as the SSL_CLIENT_S_DN_CN header.
map \$ssl_client_s_dn \$ssl_client_s_dn_cn {
    default        "";
    ~CN=(?<cn>[^,]+) \$cn;
}

# Plain HTTP listener -- redirect everything to HTTPS so the
# ``Secure``-flagged session cookie is honored (the UI cookie
# middleware sets Secure unconditionally).
server {
    listen ${PROXY_PORT} default_server;
    listen [::]:${PROXY_PORT} default_server;

    server_name _;

    return 301 https://${PUBLIC_HOSTNAME}\$request_uri;
}

# HTTPS listener -- terminates TLS with the Tailscale-issued
# cert at /etc/nginx/ssl/pychestrate.{crt,key} and proxies to
# the gunicorn upstream on the loopback.
server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;

    server_name _;

    ssl_certificate     /etc/nginx/ssl/pychestrate.crt;
    ssl_certificate_key /etc/nginx/ssl/pychestrate.key;

    # Mutual-TLS client-cert verification.
    #
    # ``optional`` (not ``on``) lets the bulk of the surface --
    # cookie-session UI traffic + API-key REST traffic -- keep
    # working without a client cert.  The orchestration-ingest
    # endpoints below are gated explicitly with an
    # ``\$ssl_client_verify`` check, double-gated by the
    # application-level mTLS check that consumes the
    # ``SSL_CLIENT_S_DN_CN`` forwarded header.
    ssl_client_certificate ${CLIENT_CA_PATH};
    ssl_verify_client       optional;
    ssl_verify_depth        2;

    # Generous body limit -- the service has uploads
    # (artifacts, logs) and 1MiB nginx default is too tight.
    client_max_body_size 50M;

    # Orchestration-ingest endpoints -- worker -> service
    # progress / results / dispatch-ack callbacks.  These MUST
    # present a client cert verified against our CA bundle.
    # nginx fails fast with 401 for unverified clients; the
    # application STILL re-checks ``SSL_CLIENT_S_DN_CN`` so a
    # misconfigured proxy cannot grant ingress unauthenticated.
    location ~ ^/api/v1/runs/[^/]+/(progress|results/complete|dispatch-ack)\$ {
        if (\$ssl_client_verify != "SUCCESS") {
            return 401;
        }

        proxy_pass http://127.0.0.1:${REMOTE_PORT};
        proxy_http_version 1.1;

        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host  \$host;

        # Forward the verified subject + verify result so the
        # app's _require_mtls_client_cn() helper can read the
        # CN and bind the request to the calling worker.
        proxy_set_header SSL_CLIENT_S_DN_CN \$ssl_client_s_dn_cn;
        proxy_set_header SSL_CLIENT_VERIFY  \$ssl_client_verify;

        proxy_connect_timeout 30s;
        proxy_send_timeout    300s;
        proxy_read_timeout    300s;
    }

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

        # Forward mTLS-verified subject + verify result even on
        # the catch-all so future routes that opt into the mTLS
        # check see the same environ keys without a separate
        # location block.
        proxy_set_header SSL_CLIENT_S_DN_CN \$ssl_client_s_dn_cn;
        proxy_set_header SSL_CLIENT_VERIFY  \$ssl_client_verify;

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

    scp -q "${NGINX_CONF_LOCAL}"    "${REMOTE_TARGET}:/tmp/pychestrate.nginx.conf"
    scp -q "${NGINX_INSTALL_LOCAL}" "${REMOTE_TARGET}:/tmp/pychestrate.nginx.install.sh"
    rm -f "${NGINX_CONF_LOCAL}" "${NGINX_INSTALL_LOCAL}"

    ssh -t "${REMOTE_TARGET}" "bash /tmp/pychestrate.nginx.install.sh && rm -f /tmp/pychestrate.nginx.install.sh"
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
    ssh "${REMOTE_TARGET}" "sudo systemctl restart pychestrate.service && sudo systemctl --no-pager status pychestrate.service | head -8"
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
        "${REPO_ROOT}/deployment/pychestrate.service.template" \
        > "${UNIT_LOCAL}"

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

# \`\`install\`\` combines mv + chown + chmod into a single
# privileged operation -- shrinks the sudoers whitelist
# surface in deployment/sudoers.d/pychestrate-deploy.template.
sudo install -m 0644 -o root -g root \\
    /tmp/pychestrate.service /etc/systemd/system/pychestrate.service

sudo systemctl daemon-reload
sudo systemctl enable pychestrate.service
sudo systemctl restart pychestrate.service

echo
echo "pychestrate.service status:"
sudo systemctl --no-pager status pychestrate.service | head -10
UNIT_INSTALL

    scp -q "${UNIT_LOCAL}"         "${REMOTE_TARGET}:/tmp/pychestrate.service"
    scp -q "${UNIT_INSTALL_LOCAL}" "${REMOTE_TARGET}:/tmp/pychestrate.systemd.install.sh"
    rm -f "${UNIT_LOCAL}" "${UNIT_INSTALL_LOCAL}"

    ssh -t "${REMOTE_TARGET}" "bash /tmp/pychestrate.systemd.install.sh && rm -f /tmp/pychestrate.systemd.install.sh"
fi
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
        echo "  service     : pychestrate.service (systemd)"
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
