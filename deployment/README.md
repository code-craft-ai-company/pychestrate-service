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
again at the application layer: the pod routes (heartbeat,
dispatch long-poll, capabilities, dispatch-ack, progress,
results, artifacts) require the verified certificate's CN and
compare it with the client they act for.

### How the certificate identity reaches the app

nginx forwards the verification result and the certificate CN
in two **hyphenated** request headers, set in every `location`
that proxies to the app (`pychestrate.nginx.conf.template`):

```nginx
proxy_set_header X-Client-Cert-CN     $ssl_client_s_dn_cn;
proxy_set_header X-Client-Cert-Verify $ssl_client_verify;
```

gunicorn drops request headers whose names contain underscores,
so the older `SSL_CLIENT_S_DN_CN` header never reached the app
and every pod call answered 401. The app
(`clients/mtls_identity.py`) accepts the two headers only when
the TCP peer is a trusted proxy -- `PYCHESTRATE_TRUSTED_PROXY_ADDRESSES`,
the variable the Secure-cookie policy uses for `X-Forwarded-Proto`:
comma-separated IPs / CIDRs or `*`, default `127.0.0.1,::1` (nginx
on the same host, app bound to loopback); set but empty trusts no
proxy -- and only when `X-Client-Cert-Verify` is `SUCCESS`. It
removes both headers before any handler runs and hands the CN to
the routes as `request.mtls_client_cn`. `proxy_set_header`
replaces a client-supplied header of the same name, so a pod
cannot claim another identity through nginx.

### 1. The client-enrollment CA (nginx must trust it)

The service signs every pod's client certificate with its
**client-enrollment CA** when the pod enrolls, so nginx must
verify client certificates against that same CA.

`development/run-staging-gunicorn` generates the CA on first use:

- `.cache/dev-secrets/dev.enrollment-ca.pem` (0600) — certificate
  and private key, loaded by the service
  (`PYCHESTRATE_ENROLLMENT_CA_FILE_PATH`)
- `.cache/dev-secrets/dev.enrollment-ca.crt` (0644) — the
  certificate alone, for nginx's `ssl_client_certificate`

`deploy-alpha-to-host.sh` runs
`development/run-staging-gunicorn --provision-only` in step 6 and
renders `ssl_client_certificate` pointing at
`dev.enrollment-ca.crt` in the remote checkout. Pass
`--client-ca-path=<remote path>` only when the service loads its
enrollment CA from elsewhere; the path must be that CA's
certificate. (`bootstrap-client-ca.sh` created a separate CA the
service never signs with; nginx trusting it rejected every
enrolled pod, so the deploy no longer uses it.)

### 2. Enroll a pod -- the service issues its certificate

Mint an enrollment token for the pod (Admin → Enrollment tokens,
or `POST /api/v1/enrollment-tokens`), then on the pod:

```bash
pychestrate-client enroll \
    --server-url https://tc-app-server.tailb75ce6.ts.net \
    --token <secret> --name <pod label the token was minted for>
```

The certificate the service returns has **CN = the pod's client
id** (plus a `urn:uuid:<client id>` subject alternative name).
That CN is what nginx forwards as `X-Client-Cert-CN`, and every
pod route requires it to equal the client id in its path, so
the registry, the certificate and the URLs share one identity.
Hand-issued certificates (e.g. `CN=worker-1`) are rejected by the
pod routes. Enrolling also registers the client on the pod the
token names (creating a static pod when none is defined), which
is what makes the pod eligible for dispatch.

### 3. Present the cert in client traffic

```bash
# curl (the pod client's own files: --state-dir, else
# ~/.local/share/pychestrate-client/, else ~/.pychestrate-client/ on a pod
# enrolled by an older client)
curl --cert client.crt --key client.key \
    https://tc-app-server.tailb75ce6.ts.net/api/v1/clients/$(cat client_id)/heartbeat
```

Without a client cert the orchestration-ingest endpoints
return **401 Unauthorized** (nginx fails fast at the location
block; the app never sees the request).

### Alpha-stage caveats

The self-signed root CA is fine for the alpha. A production-
grade PKI would: (a) integrate Vault / Step CA / equivalent;
(b) rotate / renew certs on a schedule; (c) check revocation
via OCSP or CRL. All three are out of scope for the alpha.

## `renew-cert.sh` — HTTPS server-cert renewal

The nginx front terminates HTTPS with a Tailscale-issued cert
(`/etc/nginx/ssl/pychestrate.crt` / `.key`), valid for **90
days**. When it lapses, the `:80 → https` redirect makes the
whole site unreachable for browsers, so renewal is
operationally load-bearing.

```bash
deployment/renew-cert.sh            # defaults match the alpha host
```

The script mints a fresh cert on the host via `tailscale cert`,
installs the pair with the right ownership/modes, validates and
reloads nginx (zero downtime), and prints the old + new expiry.
Every privileged call is `sudo -n` against the scoped rules in
`sudoers.d/pychestrate-deploy.template` (the TLS-renewal block),
so it is fully non-interactive once
`install-deploy-sudoers.sh` has been run — re-run that installer
once after pulling this change to pick the new rules up
(it prompts for the remote sudo password one time).

Renewal is idempotent; put it on a monthly cron / systemd timer
(well inside the 90-day validity) to never hit an expiry again:

```
# workstation or host crontab
17 4 1 * * /path/to/pychestrate-service/deployment/renew-cert.sh >> ~/pychestrate-cert-renew.log 2>&1
```

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
  pepper, UI cookie secret (32 random bytes each, mode 0600), the
  job-envelope signing key, the result-upload presign secret and
  the client-enrollment CA (`dev.enrollment-ca.pem`, plus its
  certificate `dev.enrollment-ca.crt` that nginx trusts)
- `~/pychestrate-service/.cache/dev-db/pychestrate.sqlite` —
  the SQLite database, upgraded to head via alembic
- `/etc/systemd/system/pychestrate.service` — systemd unit
  rendered from `deployment/pychestrate.service.template`,
  invoking `development/run-staging-gunicorn` which runs
  gunicorn against `build_wsgi_application_for_production()`
  bound to `127.0.0.1:8888`
- `/etc/nginx/sites-available/pychestrate` — nginx site config,
  rendered from `deployment/pychestrate.nginx.conf.template` +
  symlinked to `sites-enabled/`, listening on port 80 (redirect)
  and 443, reverse-proxying to `127.0.0.1:8888` and gzip-compressing
  HTML / JavaScript / CSS / JSON / SVG responses (the ~1.6 MB mj-*
  component library goes out as ~370 KB)
- `~/.pychestrate/server.log` — tee'd stdout / stderr from the
  service (also available via `journalctl -u pychestrate`)

### Usage

```bash
export CODECRAFTAI_REPO_TOKEN=ghp_xxx     # the same fine-grained
                                       # PAT used by CI for
                                       # private codecraftai-* deps

deployment/deploy-alpha-to-host.sh \
    --host tc-app-server.local \
    --user myron \
    --public-hostname tc-app-server.tailb75ce6.ts.net
```

`--host` and `--user` are required; there are no host-specific
defaults. `--public-hostname` is the name on the TLS certificate
(nginx redirects there) and defaults to `--host`. The service unit also
gets it as `PYCHESTRATE_PUBLIC_BASE_URL=https://<name>`, which job
envelopes carry as their issuer and progress / result URLs. `--port` (8888) and
`--proxy-port` (80) keep their defaults. Values can be given as
`--option VALUE` or `--option=VALUE`; `--help` lists every option.

Add `--dry-run` first to see what a deploy would do without changing
anything: it prints every step (the remote scripts included), runs
only the read-only SSH checks, and lets `rsync --dry-run
--itemize-changes` list the files the sync would send and the remote
files `--delete` would remove (lines starting `*deleting`).

`CODECRAFTAI_REPO_TOKEN` is needed only while `pyproject.toml` pulls
the private `codecraftai-*` packages from git; when it resolves them
from a package index, step 3 is skipped and the index's credentials
must be configured for poetry on the host.

### `.env` sourcing

The script auto-sources `${REPO_ROOT}/.env` (gitignored) before
the pre-flight check, so you can keep `CODECRAFTAI_REPO_TOKEN`
(and any other env vars) out of your shell history. Add a line
to the file generated by `repository-setup/rehome-repository`:

```bash
# .env (extends the rehome-generated file)
CODECRAFTAI_REPO_TOKEN="ghp_xxx"
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

1. `CODECRAFTAI_REPO_TOKEN` is not set.
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
| 6 | `alembic upgrade head`, `development/run-staging-gunicorn --provision-only` | applies the migrations against `~/pychestrate/pychestrate.sqlite`, then generates the service secrets (including the client-enrollment CA nginx trusts in step 7). |
| 7 | nginx site write + reload | renders `deployment/pychestrate.nginx.conf.template` to `/etc/nginx/sites-available/pychestrate`: listens on `--proxy-port` (80), proxies to `127.0.0.1:--port` (8888), gzip on for text responses, verifies pod client certificates against the enrollment CA and forwards their identity (`X-Client-Cert-CN` / `X-Client-Cert-Verify`). Validate a template edit locally with `nginx -t` against a rendered copy before deploying. |
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
3. You are signed in as that administrator and land on the home page.
   (If the sign-in is refused, you land on `/login` instead; use the
   credentials you just chose.)

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


## Monitoring

| Endpoint | Auth | Answers |
|---|---|---|
| `GET /livez` (also `/__health/live`) | none | `200 {"status": "live"}` while the process serves HTTP -- use for restart decisions |
| `GET /readyz` (also `/healthz`, `/__health/ready`) | none | `200 {"status": "ready"}`, or `503 {"status": "not_ready", "failing": ["database"]}` when the database does not answer `SELECT 1` within 3 s -- use for traffic decisions |
| `GET /api/v1/system/health` | none / admin | overall status word for anyone; subsystem details with `system:ui.admin.view` |
| `GET /metrics` | bearer token | Prometheus text: process start, request counts and latency per worker, readiness, runs by state, backups by status and `pychestrate_backup_last_success_timestamp_seconds` (alert when it is older than ~26 h), internal event counters |

The probes reveal nothing but a status word and check names, and they
pass the first-run setup gate. `/metrics` needs `Authorization: Bearer
<token>`, the token being the contents of `PYCHESTRATE_METRICS_TOKEN_FILE`
(`run-staging-gunicorn` generates `.cache/dev-secrets/dev.metrics-token`);
set `PYCHESTRATE_METRICS_PUBLIC=true` to serve it without a token only
where the network or proxy already restricts it. Scrape config:

```yaml
scrape_configs:
  - job_name: pychestrate
    scheme: https
    authorization:
      credentials_file: /etc/prometheus/pychestrate-metrics-token
    static_configs:
      - targets: ["tc-app-server.tailb75ce6.ts.net"]
```

Counters and latency histograms are per gunicorn worker (series carry
a `pid` label; sum them). `~/.pychestrate/server.log` and `backup.log`
are rotated daily or past 100 MB, 14 kept, by
`/etc/logrotate.d/pychestrate` (from `pychestrate.logrotate.template`).


## Backup and restore

A backup is two files per run, written under the presence directory
(`~/pychestrate`, mode 0700):

| File | Holds |
|---|---|
| `backups/<id>.backup.tar.gz` (+ `.sha256`) | a consistent database snapshot (SQLite online-backup API, or `pg_dump --format=custom` for PostgreSQL) and every run artifact under the artifact root (`~/pychestrate/artifacts`), plus a manifest with checksums, row counts and key fingerprints |
| `backup-keys/<id>.keys.tar` (0600) | the keys the database is useless without: the KEK (every stored secret is wrapped under it), the password pepper, the UI cookie secret, the job-envelope signing key and the enrollment CA -- whichever are configured |

The archive contains **no key bytes**; keep the two files in
**different places** so a copied archive alone cannot decrypt the
secrets inside it.

### Taking backups

- **Scheduled:** the deploy installs `pychestrate-backup.timer`, which
  runs `pychestrate-backup.service` daily at 02:30 (±15 min, catching up
  after downtime). It keeps the newest 14 archives. Log:
  `~/.pychestrate/backup.log`.
- **On demand:** `sudo systemctl start pychestrate-backup.service`, or
  `POST /api/v1/backups` (permission `system:backups.write`), or on the
  host:

  ```bash
  cd ~/pychestrate-service
  development/run-staging-gunicorn admin backup create --note "before upgrade"
  development/run-staging-gunicorn admin backup list
  ```

A backup is safe to take while the service runs. The REST trigger
runs inside the request (bounded by gunicorn's worker timeout), so on
an install with a large artifact tree prefer the systemd unit or the
command. **Copy both directories off the host after each run** (e.g. `rsync` the archives
to the NAS and the key bundles to the operator's secret store); a
backup that stays on the host dies with its disk.

### Rehearsing a restore (verification)

```bash
development/run-staging-gunicorn admin backup verify \
    ~/pychestrate/backups/<id>.backup.tar.gz \
    --keys ~/pychestrate/backup-keys/<id>.keys.tar
```

checks the archive checksum, the manifest, the database snapshot
(`PRAGMA integrity_check` and the recorded row counts, or
`pg_restore --list`), the artifact count, the key fingerprints, and
that the KEK unwraps the stored data keys -- without touching the live
system. `POST /api/v1/backups/<id>:restore` with `{"dry_run": true}`
runs the same checks from the API and returns the restore command.

### Restoring

A restore replaces the database, the artifact root and the key files,
so it runs with the service **stopped** (the API answers 409 with the
command instead of restoring itself):

```bash
sudo systemctl stop pychestrate.service pychestrate-backup.timer
cd ~/pychestrate-service
development/run-staging-gunicorn admin backup restore \
    /path/to/<id>.backup.tar.gz --keys /path/to/<id>.keys.tar --yes
sudo systemctl start pychestrate.service pychestrate-backup.timer
```

The restore verifies the backup first and changes nothing if any check
fails. It then writes each key to the path the environment loads it
from (refusing to replace a *different* existing key unless
`--overwrite-keys` is given), swaps the database in (SQLite: the old
file is kept in `pre-restore-<timestamp>/` next to it; PostgreSQL: the
current database is first dumped to
`backups/pre-restore-<timestamp>.pgdump`, then `pg_restore --clean
--if-exists --single-transaction` runs), and replaces the artifact root
(the old tree is kept as `artifacts.pre-restore-<timestamp>`). Sign in
and open a secret afterwards to confirm the KEK and pepper; delete the
`pre-restore-*` copies once satisfied.

On a **rebuilt host**, deploy first (the deploy generates fresh dev
keys under `.cache/dev-secrets/` on first start), stop the service, and
restore with `--overwrite-keys` so the backed-up keys replace the fresh
ones.

For PostgreSQL, install the `postgresql-client` package matching the
server version on the host that runs `backup create` / `restore`
(`PYCHESTRATE_PG_DUMP_PATH` / `PYCHESTRATE_PG_RESTORE_PATH` override the
tool paths). The password is passed to `pg_dump` / `pg_restore` in
`PGPASSWORD`, never on the command line.

Locations are configurable (environment or `settings.config`
`[DATASTORAGE]`): `PYCHESTRATE_BACKUP_ROOT`, `PYCHESTRATE_BACKUP_KEYS_DIR`,
`PYCHESTRATE_ARTIFACT_ROOT`. A location outside `~/pychestrate` must be
added to the units' `ReadWritePaths`.


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
| `CODECRAFTAI_REPO_TOKEN` | (already configured) — fine-grained PAT for cloning private `codecraftai-*` deps |

#### 4. Pre-provision the target

Run the workstation-driven deploy **once** from your laptop
before using the CI workflow. This installs apt deps and
poetry — `setup-debian-machine` requires sudo, which CI cannot
satisfy interactively. The CI workflow uses `--skip-system-setup`
and assumes this one-time provisioning is already in place.

```bash
CODECRAFTAI_REPO_TOKEN=ghp_xxx \
    deployment/deploy-alpha-to-host.sh --host tc-app-server --user myron \
        --public-hostname tc-app-server.tailb75ce6.ts.net
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
