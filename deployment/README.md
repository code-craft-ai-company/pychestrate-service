# `deployment/` — alpha deployment scripts

One-shot deploy of `pychestrate-service` to a remote host.
The scripts in this directory drive the existing
`repository-setup/` + `development/` bootstrap chain over SSH;
the remote does not need to be pre-provisioned beyond a stock
Debian / Ubuntu install with SSH access for the deploy user.

## `deploy-alpha-to-host.sh`

Driver script that runs from your workstation and provisions a
remote host end-to-end. The remote ends up with:

- `~/pychestrate-service/` — the rsync'd checkout
- `~/pychestrate-service/.venv/` — poetry-installed deps
- `~/pychestrate-service/.cache/dev-secrets/` — generated KEK,
  pepper, UI cookie secret (32 random bytes each, mode 0600)
- `~/pychestrate-service/.cache/dev-db/pychestrate.sqlite` —
  the SQLite database, upgraded to head via alembic
- a tmux session named `pychestrate` running the service via
  `make dev-up` with `PYCHESTRATE_BIND_HOST=0.0.0.0` so the
  service is reachable on the LAN
- `~/.pychestrate/server.log` — tee'd stdout / stderr from the
  service

### Usage

```bash
export AUTOMOJO_REPO_TOKEN=ghp_xxx     # the same fine-grained
                                       # PAT used by CI for
                                       # private automojo-* deps

deployment/deploy-alpha-to-host.sh \
    --host=tc-app-server.local \
    --user=myron \
    --port=8888
```

All three flags default to the values above so most invocations
can be just:

```bash
AUTOMOJO_REPO_TOKEN=ghp_xxx deployment/deploy-alpha-to-host.sh
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
| 2 | `repository-setup/setup-debian-machine` | installs `build-essential`, `python3`, `python3-dev`, `python3-setuptools`, `python3-pip`, plus poetry via pipx. **Requires sudo on the remote** — you'll be prompted for the password. |
| 3 | `git config --global url.<base>.insteadOf` | injects the PAT for cloning private `automojo-*` deps. |
| 4 | `python3 repository-setup/rehome-repository --skip-workspaces` | generates `.env` with PYTHONPATH composition. |
| 5 | `bash development/setup-environment` | creates `.venv`, runs `poetry install`. **60-120 sec** while the nine private deps clone. |
| 6 | `alembic upgrade head` | applies both migrations against `.cache/dev-db/pychestrate.sqlite`. |
| 7 | `make dev-up` (in tmux) | starts the service. tmux session name: `pychestrate`. |

### Verifying / managing the running instance

```bash
# Probe                                                           
curl -fsS http://tc-app-server.local:8888/

# Watch the live log
ssh myron@tc-app-server.local 'tail -f ~/.pychestrate/server.log'

# Attach to the tmux session
ssh myron@tc-app-server.local -t tmux attach -t pychestrate

# Stop the service
ssh myron@tc-app-server.local tmux kill-session -t pychestrate
```

### Idempotent re-deploy

Re-running the script:

- **rsync** picks up code changes (no full re-transfer; only
  diffs).
- **setup-debian-machine** is a no-op if packages are present.
- **rehome / setup-environment** are no-ops if up-to-date.
- **alembic upgrade head** applies new revisions only.
- The tmux session is killed and restarted with the new code.

The KEK / pepper / cookie-secret + SQLite DB **persist** across
re-deploys — they live under the checkout's `.cache/` and rsync
explicitly excludes that path.

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
  target, or from a jumphost.
