# `deployment/` — alpha deployment scripts

One-shot deploy of `pychestrate-service` to a remote host.
The scripts in this directory drive the existing
`repository-setup/` + `development/` bootstrap chain over SSH;
the remote does not need to be pre-provisioned beyond a stock
Debian / Ubuntu install with SSH access for the deploy user.

## mTLS for orchestration-ingest endpoints

The nginx :443 server block verifies client certificates for
the three orchestration-ingest endpoints (worker callbacks):

- `POST /api/v1/runs/<id>/progress`
- `POST /api/v1/runs/<id>/results/complete`
- `POST /api/v1/runs/<id>/dispatch-ack`

`ssl_verify_client` is `optional` so the bulk of the surface
(cookie-session UI + API-key REST) keeps working without a
client cert. The three paths above are gated explicitly in
nginx (`if ($ssl_client_verify != "SUCCESS") return 401;`) and
again at the application layer
(`_require_mtls_client_cn(request)` consumes the
`SSL_CLIENT_S_DN_CN` WSGI environ key forwarded by nginx).

### 1. Bootstrap the client-CA (one-time)

```bash
deployment/bootstrap-client-ca.sh \
    --host=tc-app-server.local --user=myron
```

This mints a self-signed root CA on the remote at:

- `/etc/nginx/ssl/client-ca.crt` (0644 root) — the cert that
  nginx loads via `ssl_client_certificate`
- `/etc/nginx/ssl/client-ca.key` (0600 root) — the private key
  used to issue client certs against this CA

The script is **idempotent**: re-running it against a host that
already has the CA in place is a clean no-op (regenerating
would invalidate previously-issued client certs).

You'll be prompted for the remote sudo password **once** —
the bootstrap is intentionally not in the passwordless-sudo
scope.

### 2. Issue a client cert against the CA

```bash
# Local: generate the worker's keypair + CSR.
openssl req -new -newkey rsa:2048 -nodes \
    -keyout client.key -out client.csr \
    -subj /CN=worker-1

# Remote: sign the CSR with the CA (requires sudo to read the
# CA private key).
ssh myron@tc-app-server.local 'sudo openssl x509 -req \
    -in /dev/stdin \
    -CA /etc/nginx/ssl/client-ca.crt \
    -CAkey /etc/nginx/ssl/client-ca.key \
    -CAcreateserial \
    -days 365 -sha256' < client.csr > client.crt
```

The CN you set in the CSR is what nginx forwards to the app as
`SSL_CLIENT_S_DN_CN`. The app uses it to bind the request to
the calling worker.

### 3. Present the cert in client traffic

```bash
# curl
curl --cert client.crt --key client.key \
    -X POST https://tc-app-server.tailb75ce6.ts.net/api/v1/runs/<uuid>/progress \
    -H 'Content-Type: application/json' \
    -d '{"percent": 50}'

# python (httpx)
client = httpx.Client(cert=("client.crt", "client.key"))
client.post(url, json=payload)
```

Without a client cert the orchestration-ingest endpoints
return **401 Unauthorized** (nginx fails fast at the location
block; the app never sees the request).

### Alpha-stage caveats

The self-signed root CA is fine for the alpha. A production-
grade PKI would: (a) integrate Vault / Step CA / equivalent;
(b) rotate / renew certs on a schedule; (c) check revocation
via OCSP or CRL. All three are out of scope for the alpha.

## `deploy-alpha-to-host.sh`

Driver script that runs from your workstation and provisions a
remote host end-to-end. The remote ends up with:

```
external clients ──> nginx :80 ──> 127.0.0.1:8888 (gunicorn under systemd)
                                       │
                                       └── ~/pychestrate-service/
                                           ├── .venv/             (poetry-installed deps)
                                           ├── .cache/dev-secrets/  (KEK, pepper, cookie 0600)
                                           └── .cache/dev-db/pychestrate.sqlite
```

Specifically:

- `~/pychestrate-service/` — the rsync'd checkout
- `~/pychestrate-service/.venv/` — poetry-installed deps including gunicorn
- `~/pychestrate-service/.cache/dev-secrets/` — generated KEK,
  pepper, UI cookie secret (32 random bytes each, mode 0600)
- `~/pychestrate-service/.cache/dev-db/pychestrate.sqlite` —
  the SQLite database, upgraded to head via alembic
- `/etc/systemd/system/pychestrate.service` — systemd unit
  rendered from `deployment/pychestrate.service.template`,
  invoking `development/run-staging-gunicorn` which runs
  gunicorn against `build_wsgi_application_for_production()`
  bound to `127.0.0.1:8888`
- `/etc/nginx/sites-available/pychestrate` — nginx site config,
  rendered + symlinked to `sites-enabled/`, listening on port 80
  and reverse-proxying to `127.0.0.1:8888`
- `~/.pychestrate/server.log` — tee'd stdout / stderr from the
  service (also available via `journalctl -u pychestrate`)

### Usage

```bash
export AUTOMOJO_REPO_TOKEN=ghp_xxx     # the same fine-grained
                                       # PAT used by CI for
                                       # private codecraftai-* deps

deployment/deploy-alpha-to-host.sh \
    --host=tc-app-server.local \
    --user=myron \
    --port=8888 \
    --proxy-port=80
```

All three flags default to the values above so most invocations
can be just:

```bash
AUTOMOJO_REPO_TOKEN=ghp_xxx deployment/deploy-alpha-to-host.sh
```

### `.env` sourcing

The script auto-sources `${REPO_ROOT}/.env` (gitignored) before
the pre-flight check, so you can keep `AUTOMOJO_REPO_TOKEN`
(and any other env vars) out of your shell history. Add a line
to the file generated by `repository-setup/rehome-repository`:

```bash
# .env (extends the rehome-generated file)
AUTOMOJO_REPO_TOKEN="ghp_xxx"
```

Then `deployment/deploy-alpha-to-host.sh` runs without any
exports. Already-set environment variables (e.g. ones the
`workflow_dispatch` job populates as `env:`) take precedence —
the `.env` only fills in blanks.

Supported `.env` line forms:

```bash
KEY="quoted-value"
KEY=unquoted-value
export KEY="explicitly-exported"
# comments and blank lines are skipped
```

### Pre-flight checks

The script aborts with a typed error if:

1. `AUTOMOJO_REPO_TOKEN` is not set.
2. SSH to the target fails non-interactively (key not installed
   yet — run `ssh-copy-id` first).

### What runs on the remote

| Step | Command | Notes |
|---|---|---|
| 1 | `rsync` | excludes `.venv`, `.output`, `.cache`, `.git`, `.claude`, `.kiro`, `.vscode`, `__pycache__`, `*.pyc`, `.DS_Store`, `.env`, `*.sqlite`. |
| 2 | `repository-setup/setup-debian-machine` | installs `build-essential`, `python3`, `python3-dev`, `python3-venv`, `python3-pip`, `pipx`, `tmux`, `make`, `nginx`, plus poetry via pipx. **Requires sudo on the remote** — you'll be prompted for the password. |
| 3 | `git config --global url.<base>.insteadOf` | injects the PAT for cloning private `codecraftai-*` deps. |
| 4 | `python3 repository-setup/rehome-repository --skip-workspaces` | generates `.env` with PYTHONPATH composition. |
| 5 | `python3 development/setup-environment` | creates `.venv`, runs `poetry install`. **60-120 sec** while the nine private deps clone. |
| 6 | `alembic upgrade head` | applies both migrations against `.cache/dev-db/pychestrate.sqlite`. |
| 7 | nginx site write + reload | `/etc/nginx/sites-available/pychestrate` listens on `--proxy-port` (80), proxies to `127.0.0.1:--port` (8888). |
| 8 | systemd unit install + restart | `/etc/systemd/system/pychestrate.service` → `development/run-staging-gunicorn` → gunicorn on `127.0.0.1:8888`. |
| 7 | `make dev-up` (in tmux) | starts the service. tmux session name: `pychestrate`. |

### Verifying / managing the running instance

```bash
# Probe (through nginx)
curl -fsS http://tc-app-server.local/

# Service status
ssh myron@tc-app-server.local sudo systemctl status pychestrate

# Live logs (journalctl -- canonical)
ssh myron@tc-app-server.local sudo journalctl -u pychestrate -f

# Or the file log (tee'd by systemd)
ssh myron@tc-app-server.local 'tail -f ~/.pychestrate/server.log'

# Restart
ssh myron@tc-app-server.local sudo systemctl restart pychestrate

# Stop
ssh myron@tc-app-server.local sudo systemctl stop pychestrate

# nginx side
ssh myron@tc-app-server.local sudo nginx -t          # validate config
ssh myron@tc-app-server.local sudo systemctl reload nginx
```

### First-login: the initial-setup wizard

A fresh deploy lands with **no admin user**. The first time you
hit the service in a browser you go through a Jenkins-style
unlock-then-create-admin flow.

#### 1. Read the initial-admin token

The service writes a high-entropy token to a 0600 file in the
pychestrate **presence directory** — `~/pychestrate/` under the
service user's home, which is the
`ccai.thisapp.persona`-default for `name="pychestrate"`. The
systemd unit logs the path on startup:

```bash
ssh myron@tc-app-server.local 'grep "Initial-admin token path" ~/.pychestrate/server.log | tail -1'
# Initial-admin token path: /home/myron/pychestrate/initial-admin-token

ssh myron@tc-app-server.local cat ~/pychestrate/initial-admin-token
# fwoxEWV8UmSJ5qPXqgbdu89v14bzSVU-71_EWPUTCMY
```

No `sudo` needed — the file is owned by the service user.

#### 2. Walk through the wizard

Open `http://tc-app-server.local/` (or any URL on the service).
While setup is pending, every request 302-redirects to
`/setup/unlock`.

1. **Paste the token** on the unlock page → submit.
2. **Create the administrator** (login, email, display name,
   password ≥ 12 chars) → submit.
3. You land on `/config/login`. Sign in with the credentials you
   just chose.

#### 3. Verify the wizard is one-way

```bash
# Should 404 — wizard is permanently disabled.
curl -I http://tc-app-server.local/setup/unlock

# Should show only pychestrate.sqlite — the token file is
# deleted on completion. ~/pychestrate/ is mode 0700 so other
# accounts on the box cannot enumerate it.
ssh myron@tc-app-server.local ls -l ~/pychestrate/
```

#### Recovery: lost the token before completing setup

If you lose the cleartext token but haven't finished the wizard,
restart the service. The bootstrap detects the missing file,
generates a fresh token, updates the stored hash, and writes a
new file:

```bash
ssh myron@tc-app-server.local sudo systemctl restart pychestrate
ssh myron@tc-app-server.local cat ~/pychestrate/initial-admin-token
```

The wizard is one-way **after completion** — there is no operator
path that re-enables setup mode once an admin exists. Resetting
requires a manual `UPDATE system_initial_setup SET completed_at = NULL` plus
`DELETE FROM identity_users` plus a service restart.

### Idempotent re-deploy

Re-running the script:

- **rsync** picks up code changes (only diffs transferred).
- **setup-debian-machine** is a no-op if packages are present.
- **rehome / setup-environment** are no-ops if up-to-date.
- **alembic upgrade head** applies new revisions only.
- **nginx site config** is overwritten + reloaded.
- **pychestrate.service** unit is overwritten + `systemctl restart`'d.

The KEK / pepper / cookie-secret + SQLite DB **persist** across
re-deploys — they live under the checkout's `.cache/` and rsync
explicitly excludes that path.

### Passwordless `systemctl restart` for CI re-deploys

CI's `--skip-system-setup` mode re-deploys by running
`sudo systemctl restart pychestrate.service` over SSH. By
default that prompts for a sudo password, which CI cannot
satisfy. Two options:

#### Option A (recommended): scoped sudoers entry

Add a `sudoers.d` rule that grants the deploy user
**passwordless** access to **just** `systemctl restart
pychestrate.service` (not all of sudo):

```bash
ssh myron@tc-app-server.local 'sudo tee /etc/sudoers.d/pychestrate-ci > /dev/null <<EOF
myron ALL=(root) NOPASSWD: /bin/systemctl restart pychestrate.service, /bin/systemctl status pychestrate.service
EOF
sudo chmod 0440 /etc/sudoers.d/pychestrate-ci
sudo visudo -c  # validate
'
```

Now CI can `sudo systemctl restart pychestrate` with no
password, and it can NOT do anything else with sudo.

#### Option B: passwordless sudo (broader; not recommended)

`myron ALL=(ALL) NOPASSWD: ALL` in `/etc/sudoers.d/myron`
gives passwordless sudo for everything. Easier to set up but
defeats the principle of least privilege.

### Limitations

- **SQLite-only.** This driver targets the alpha's "single host,
  SQLite-backed dev instance" use-case. Production-Postgres
  deployments need the FK ordering migration fix from #175 and
  the operator procedure documented in
  `userguide/13-00-alpha-deployment.rst`.
- **No process supervisor.** Service runs under `tmux`; survives
  ssh disconnect but not host reboot. Convert to a systemd unit
  for that.
- **Client isolation networks.** If the workstation cannot
  L2-route to the target (e.g., guest WiFi), this driver fails
  at step 1. Run from a host that has direct LAN access to the
  target, or use the GitHub Actions deploy workflow below
  (which reaches the target via Tailscale).


## CI deploy workflow (`.github/workflows/deploy.yml`)

Same script driven from a GitHub Actions runner that has joined
the operator's Tailscale tailnet. Triggered manually via the
"Run workflow" button on the Actions tab. One-click deploys
without touching a workstation.

### One-time setup

The workflow needs three categories of credentials. All are
**one-time setup** — the workflow itself doesn't change after
this is in place.

#### 1. Tailscale OAuth client

In the Tailscale admin console:

- **Settings → OAuth clients → Generate new client**
  - **Description**: e.g., `pychestrate-ci-deploy`
  - **Tags**: `tag:ci`
  - **Scopes**: Devices → Write

Copy the **Client ID** and **Client secret**.

Update the ACL policy (Settings → Access controls) to declare
`tag:ci` and grant it the access the deploy needs:

```json
{
  "tagOwners": {
    "tag:ci": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src":    ["tag:ci"],
      "dst":    ["tc-app-server:22", "tc-app-server:80"]
    }
  ]
}
```

(Port 22 for SSH-based deploy, port 80 so the runner can probe
the deployed instance via nginx after deploy. The app's
internal port — default 8888 — is bound to loopback only and
doesn't need an ACL grant.)

#### 2. SSH deploy key

Generate a dedicated SSH keypair on a workstation:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pychestrate-deploy -N "" \
    -C "pychestrate-ci-deploy@github-actions"
```

- Add the **public** key to `~myron/.ssh/authorized_keys` on
  `tc-app-server` (so the CI deploy user can log in).
- The **private** key (`~/.ssh/pychestrate-deploy`) goes into
  GitHub as a secret in step 3.

#### 3. GitHub repository secrets

Settings → Secrets and variables → Actions → New repository
secret:

| Name | Value |
|---|---|
| `TS_OAUTH_CLIENT_ID` | OAuth client ID from step 1 |
| `TS_OAUTH_SECRET` | OAuth client secret from step 1 |
| `DEPLOY_SSH_KEY` | Full contents of `~/.ssh/pychestrate-deploy` (the **private** key, including the `-----BEGIN ...` header / footer) |
| `AUTOMOJO_REPO_TOKEN` | (already configured) — fine-grained PAT for cloning private `codecraftai-*` deps |

#### 4. Pre-provision the target

Run the workstation-driven deploy **once** from your laptop
before using the CI workflow. This installs apt deps and
poetry — `setup-debian-machine` requires sudo, which CI cannot
satisfy interactively. The CI workflow uses `--skip-system-setup`
and assumes this one-time provisioning is already in place.

```bash
AUTOMOJO_REPO_TOKEN=ghp_xxx \
    deployment/deploy-alpha-to-host.sh --host=tc-app-server
```

Subsequent deploys (CI or workstation) are entirely
non-interactive.

### Triggering a CI deploy

GitHub UI → **Actions** tab → **deploy** workflow →
**Run workflow**. Inputs:

- `target_host` — defaults to `tc-app-server`
- `target_user` — defaults to `myron`
- `target_port` — defaults to `8888`
- `git_ref` — branch / tag / SHA to deploy (defaults to `main`)

The workflow:

1. Checks out the chosen ref
2. Joins the runner to the tailnet via `tailscale/github-action@v3`
3. Pings the target to confirm reachability
4. Loads `DEPLOY_SSH_KEY` into ssh-agent
5. Trusts the target host key via `ssh-keyscan`
6. Runs `deployment/deploy-alpha-to-host.sh --skip-system-setup ...`
7. Logs out from Tailscale on completion

Concurrency: deploys to the same `target_host` serialize; deploys
to different hosts run in parallel.

### Verifying

After the workflow completes successfully, the same post-deploy
commands work as for the local-driven deploy — see "Verifying /
managing the running instance" above.
