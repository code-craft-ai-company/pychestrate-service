# Pychestrate Service — Hardware Onboarding

This guide walks through registering a physical or virtual host
(Raspberry Pi, UEFI-managed lab machine, VM, container, ...) with a
running pychestrate service so flows submitted to `/api/v1/flows` can
target it.

The flow is:

```
┌─────────────────┐  1. bootstrapadmin       ┌──────────────────┐
│   operator CLI  │ ───────────────────────▶ │  pychestrate svc │
│                 │ ◀────── cookie ───────── │   (DB + REST)    │
│                 │                          │                  │
│                 │  2. registerpod          │                  │
│                 │ ───────────────────────▶ │                  │
│                 │ ◀── token + secret ───── │                  │
└─────────┬───────┘                          └──────────────────┘
          │ secret
          ▼
┌─────────────────┐  3. POST /enrollment-    ┌──────────────────┐
│   target host   │ ────tokens/redeem──────▶ │  pychestrate svc │
│   (raspi / UEFI)│                          │                  │
│                 │ ◀──── bearer token ───── │                  │
└─────────────────┘                          └──────────────────┘
```

For the bring-up basics (poetry install, DB init, server launch, env
vars, the bigger picture), start with
[`quickstart.md`](quickstart.md). The deeper configuration reference
lives in [`configuration.md`](configuration.md).

## Prerequisites

* The service is up and reachable. Verify with:

  ```bash
  curl -sf http://localhost:8080/api/v1/rbac/permissions | head -c 200
  ```

* You have an admin session cookie. Obtain one via:

  ```bash
  PYCHESTRATE_DATABASE_URL=sqlite:///./pychestrate.db \
    PYCHESTRATE_ADMIN_PEPPER=dev \
    python scripts/bootstrapadmin.py --create-schema --password 'My$3cret'
  ```

  Copy the printed `SESSION_ID (cookie value)` and export it:

  ```bash
  export PYCHESTRATE_SESSION_COOKIE='<that value>'
  export PYCHESTRATE_BASE_URL='http://localhost:8080'
  ```

## 1. Register the project + pod + enrollment token

The `scripts/registerpod.py` helper does all three steps in one
shot. It will:

* `GET /api/v1/projects/{slug}` to find the project; create it via
  `POST /api/v1/projects` if missing;
* `POST /api/v1/projects/{project_id}/pod-definitions` with a minimal
  spec (`{"members": [{"name": "<pod-name>", "kind": "linux_host",
  "hostname": "<hostname>"}]}`);
* `POST /api/v1/enrollment-tokens` to mint a one-shot token bound to
  `(project_id, pod_name)` and print the secret exactly once.

Example for a single Raspberry Pi:

```bash
python scripts/registerpod.py \
    --project-slug lab \
    --pod-name raspi-01 \
    --hostname raspi-01.lab.local
```

Output:

```
Created project 'lab' (5d0d…)
Registered pod definition 'raspi-01' (4f2a…)

Enrollment token minted.
  PROJECT_ID:   5d0d…
  POD_ID:       4f2a…
  TOKEN_ID:     b7c9…
  POD_NAME:     raspi-01
  EXPIRES_AT:   2026-04-30T22:38:21+00:00
  SECRET:       v1.eaW5gZ…  (returned exactly once)

Hand the SECRET + POD_NAME to the agent on the target host. ...
```

The secret is **printed once**. If the agent loses it before
redemption you'll need to delete the token (`DELETE
/api/v1/enrollment-tokens/{token_id}`) and re-mint via
`registerpod.py` again.

### Bulk registration

Loop over your fleet inventory:

```bash
for host in raspi-01 raspi-02 raspi-03 raspi-04; do
    python scripts/registerpod.py \
        --project-slug lab \
        --pod-name "${host}" \
        --hostname "${host}.lab.local" \
        --member-kind linux_host
done

for host in uefi-01 uefi-02 uefi-03; do
    python scripts/registerpod.py \
        --project-slug lab \
        --pod-name "${host}" \
        --hostname "${host}.lab.local" \
        --member-kind uefi_host
done
```

Capture the output to a secrets vault or `pass` so each agent gets
exactly its own secret.

### Member kinds

`--member-kind` is the string carried on the pod-definition's
`members[*].kind` field. The service validates it against the
registered `pod_member_kind` extension catalog. Out of the box:

* `linux_host` — generic Linux machine (Raspberry Pi, x86 server, VM).
* `network_switch` — a switch that participates in pod topology.
* (Add custom kinds via the `pod_member_kind` extension; see the
  pychestrate-core spec for the contract.)

## 2. Agent redeems the secret

On each target host, the agent calls
`POST /api/v1/enrollment-tokens/redeem`. This endpoint is
intentionally **unauthenticated** — the secret itself is the
authentication factor:

```bash
curl -sf -X POST http://pychestrate.lab.local:8080/api/v1/enrollment-tokens/redeem \
    -H 'Content-Type: application/json' \
    -d '{
        "secret": "v1.eaW5gZ...",
        "pod_name": "raspi-01",
        "agent_version": "1.0.0",
        "transport_name": "http"
    }'
```

Successful response (200):

```json
{
  "client_id": "9c1f...",
  "project_id": "5d0d...",
  "pod_name": "raspi-01",
  "bearer_token": "v1.bear...",
  "bearer_algorithm": "stdlib-sha256",
  "cert_serial": "",
  "cert_pem": "",
  "cert_chain_pem": ""
}
```

The agent stores the `bearer_token` and uses it on subsequent
requests via `Authorization: Bearer ...`. (Bearer-token enforcement
on agent endpoints is not yet wired through `AccessPolicy`; see the
configuration doc's known follow-ups.)

### CSR variant

When the deployment runs an internal CA, agents may submit a CSR in
the redeem call:

```bash
curl -sf -X POST .../api/v1/enrollment-tokens/redeem \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg secret "$SECRET" --rawfile csr ./agent.csr.pem '{
        secret: $secret, pod_name: "raspi-01",
        agent_version: "1.0.0", transport_name: "http",
        csr_pem: $csr
    }')"
```

The response then carries `cert_pem` + `cert_chain_pem`
(base64-encoded PEM) for the agent to install alongside its bearer
token.

## 3. Verify the agent appears in inventory

After the agent redeems, it appears in the inventory page:

```bash
curl -sf -H "Cookie: pychestrate_session=$PYCHESTRATE_SESSION_COOKIE" \
    "$PYCHESTRATE_BASE_URL/api/v1/clients-inventory?project_id=$PROJECT_ID&limit=50" \
    | jq '.rows[] | {client_id, pod_name, liveness_state, last_seen}'
```

Liveness state cycles `ALIVE → DEGRADED → LOST` based on agent
heartbeats (the agent calls a heartbeat endpoint at the cadence its
configuration declares).

## 4. Submit a flow that targets the host

With the host registered, you can now submit a taskplus workflow to
`/api/v1/flows`:

```bash
cat > /tmp/uname.yml <<'YAML'
name: uname-on-raspi
environment: {}
parameters: {}
flow:
  - task: probe
    tasktype: automojo.taskplus.tasks.runcommand@RunCommand
    command: uname -a
YAML

curl -sf -X POST "$PYCHESTRATE_BASE_URL/api/v1/flows" \
    -H "Cookie: pychestrate_session=$PYCHESTRATE_SESSION_COOKIE" \
    -H 'Content-Type: application/yaml' \
    --data-binary @/tmp/uname.yml
```

Response (202):

```json
{
  "flow_id": "ae4f...",
  "name": "uname-on-raspi",
  "state": "PENDING",
  "submitted_at": "...",
  ...
}
```

Poll:

```bash
curl -sf -H "Cookie: pychestrate_session=$PYCHESTRATE_SESSION_COOKIE" \
    "$PYCHESTRATE_BASE_URL/api/v1/flows/$FLOW_ID"
curl -sf -H "Cookie: pychestrate_session=$PYCHESTRATE_SESSION_COOKIE" \
    "$PYCHESTRATE_BASE_URL/api/v1/flows/$FLOW_ID/log"
```

> The current `RunCommand` task runs the command on the **service
> host**, not on the registered agent. Targeted execution (dispatch
> to agents via the bearer-token-authenticated agent surface) is a
> follow-up integration. The pod registration and inventory state
> are wired today; the dispatch layer that hands work to specific
> hosts is the next slice.

## 5. Troubleshoot

| Symptom                                                  | Likely cause                                                                              |
|----------------------------------------------------------|-------------------------------------------------------------------------------------------|
| `ERROR: cannot reach <base-url>`                         | Service not running, wrong host/port, firewall.                                           |
| 401 from any `registerpod.py` step                       | Missing or expired session cookie. Re-run `bootstrapadmin.py`.                            |
| 403                                                      | The cookie's user isn't `system-admin`. `bootstrapadmin` grants that binding by default.  |
| 400 from pod-definitions create with `members: [...]`    | Member kind not registered. Check the `pod_member_kind` extension catalog.                |
| 409 from POST /projects                                  | Slug already exists. `registerpod.py` handles this by GET-then-POST; check the slug.      |
| 400 from POST /enrollment-tokens with `ttl_seconds=0`    | TTL must be > 0. The script defaults to 3600.                                             |
| 404 from /enrollment-tokens/redeem on the agent          | Wrong secret, expired token, or already-redeemed one-shot token.                          |
| 503 with `db_session not configured`                     | The DbSessionMiddleware didn't run. Indicates the app is mis-wired; file an issue.        |
| Agent never appears in `/clients-inventory`              | Agent didn't redeem (network, secret, transport_name mismatch). Tail the agent's logs.    |

## Reference: registerpod.py flags

| Flag                       | Default                  | Notes                                              |
|----------------------------|--------------------------|----------------------------------------------------|
| `--base-url`               | `http://localhost:8080`  | Falls back to `PYCHESTRATE_BASE_URL`.              |
| `--cookie`                 | (env)                    | Falls back to `PYCHESTRATE_SESSION_COOKIE`.        |
| `--project-slug`           | (required)               | Must match `[a-z0-9][a-z0-9-]*` per service rules.  |
| `--project-display-name`   | (slug.title())           |                                                    |
| `--project-description`    | `Created by registerpod.py` |                                                |
| `--pod-name`               | (required)               | Unique within the project.                         |
| `--member-kind`            | `linux_host`             | Must be a registered pod member kind.              |
| `--hostname`               | (pod-name)               | Recorded on `members[0].hostname`.                 |
| `--ttl-seconds`            | `3600`                   | Token lifetime.                                    |
| `--one-shot` / `--reusable`| one-shot                 | One-shot is the default for security.              |
