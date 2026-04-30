# Pychestrate Service — Bring-Up Quickstart

This guide walks through standing up the `pychestrate-service` REST
backend on a developer machine, registering hardware resources, and
exercising the taskplus orchestration endpoint. It targets someone
who has just cloned the repo and wants to start testing the wider
`automojo-*` stack against it.

## 1. Install dependencies

```bash
poetry install
```

The repo currently ships a workaround for the
`automojo/pychestrate/__init__.py` namespace-package issue (tracked as
`pychestrate-core` PR #8). After every `poetry install`, remove the
file so namespace lookups work:

```bash
rm -f .venv/lib/python3.12/site-packages/automojo/pychestrate/__init__.py
```

Once that PR merges this becomes a no-op.

## 2. Initialize the database

The service needs a SQLAlchemy URL via the `PYCHESTRATE_DATABASE_URL`
environment variable. SQLite is fine for a developer setup; PostgreSQL
is the production target.

```bash
export PYCHESTRATE_DATABASE_URL=sqlite:///./pychestrate.db
PYTHONPATH=source/site:source/packages \
    .venv/bin/python scripts/initdb.py
```

Output:

```
Connecting to: sqlite:///./pychestrate.db
Phase-1 schema created.
```

This creates every table declared on `PychestratePhase1Base` —
identity, RBAC, secrets, audit, retention, projects, pods, agents,
notifications, tagging, variables.

## 3. Start the service

```bash
PYTHONPATH=source/site:source/packages \
    .venv/bin/python scripts/serve.py --host 0.0.0.0 --port 8080
```

Expected output:

```
pychestrate-service: 78 routes registered
Listening on http://0.0.0.0:8080
```

For production-style deployment, use `gunicorn` (or another WSGI
server) against the conventional `application` global:

```bash
PYCHESTRATE_DATABASE_URL=postgresql+psycopg://pychestrate:secret@db/pychestrate \
    gunicorn -b 0.0.0.0:8080 \
    'automojo.pychestrate.webservice.wsgientry:application'
```

## 4. Smoke-test the REST surface

```bash
# RBAC permission catalog — registry only, no DB hit.
curl -sf http://localhost:8080/api/v1/rbac/permissions | head -c 200
```

The route map covers (selected):

| Surface         | Path                                     |
|-----------------|------------------------------------------|
| auth            | `/api/v1/auth/{providers,logout,mfa/...}`|
| identity users  | `/api/v1/identity/users[/{user_id}]`     |
| identity flags  | `/api/v1/flags[/{flag_key}]`             |
| RBAC            | `/api/v1/rbac/{permissions,roles,bindings,check}` |
| clients (admin) | `/api/v1/clients[/{id}/{revoke,attributes}]` |
| enrollment      | `/api/v1/enrollment-tokens[/{redeem,...}]` |
| audit           | `/api/v1/audit[/{seq}]`                  |
| secrets         | `/api/v1/secrets[/{ref}]`                |
| retention       | `/api/v1/retention/policies[/{id}/publish]` |
| projects        | `/api/v1/projects[/{slug}/{archive,...}]` |
| pods            | `/api/v1/projects/{pid}/pod-definitions...` |
| agents          | `/api/v1/agent-rollouts[/{id}/start]`    |
| notifications   | `/api/v1/notifications/channels[/{id}]`  |
| tagging         | `/api/v1/tags[/{kind}/{id}/{tag}]`       |
| variables       | `/api/v1/variables[/{scope}/{id}/{name}]` |
| flows (taskplus)| `/api/v1/flows[/{flow_id}]`              |

## 5. Register hardware resources

The `pods` surface is the place where physical hosts (your 4 Raspberry
Pi machines, plus the UEFI-managed ones) live. For each pod (a logical
group of agents on a host), POST a pod definition under a project:

```bash
PROJECT_ID=$(curl -sf -X POST http://localhost:8080/api/v1/projects \
    -H 'Content-Type: application/json' \
    -d '{"slug":"lab","display_name":"Lab","description":"Integration lab"}' \
    | python -c 'import sys,json; print(json.load(sys.stdin)["project_id"])')

curl -sf -X POST "http://localhost:8080/api/v1/projects/$PROJECT_ID/pod-definitions" \
    -H 'Content-Type: application/json' \
    -d '{
          "pod_name": "raspi-01",
          "spec": {
            "members": [
              {"member_name": "agent", "kind": "linux-agent"}
            ]
          }
        }'
```

Repeat for each pod. After agents enroll (via
`POST /api/v1/enrollment-tokens/redeem`) they appear in
`GET /api/v1/clients-inventory` paged by liveness state.

## 6. Run a taskplus flow

Once a pod is registered and an agent has enrolled, you can submit
taskplus workflows for execution. Example (raw YAML body):

```bash
cat > /tmp/echo.yml <<'YAML'
name: echo-smoke
environment: {}
parameters: {}
flow:
  - task: noop
    tasktype: automojo.taskplus.tasks.runcommand@RunCommand
    command: echo hello
YAML

curl -sf -X POST http://localhost:8080/api/v1/flows \
    -H 'Content-Type: application/yaml' \
    --data-binary @/tmp/echo.yml
```

Response (HTTP 202):

```json
{
  "flow_id": "ae4f2883-1afa-40f9-8498-71a216fbd093",
  "name": "echo-smoke",
  "state": "PENDING",
  "submitted_at": "2026-04-30T17:22:17.815045+00:00",
  ...
}
```

Poll status:

```bash
curl -sf http://localhost:8080/api/v1/flows/$FLOW_ID
```

After the worker thread finishes the task, `state` becomes
`SUCCEEDED` (or `FAILED`) and `result_code` reports the taskplus
exit code.

> Note: flow submissions are tracked in memory only. They do not
> survive a service restart. Persistence to the pychestrate DB is a
> deliberate follow-up.

## 7. Run the regression test suite

```bash
PYTHONPATH=source/site:source/testroots:source/packages \
    .venv/bin/testbase testing run \
    --root source/testroots/automojo \
    --includes "automojo.tests.singlehost.pychestrate.webservice.phase12.test_p24*" \
    --includes "automojo.tests.singlehost.pychestrate.core.*" \
    --includes "automojo.tests.singlehost.pychestrate.webservice.phase11.*" \
    -o .output_regression
```

132 tests pass on a clean checkout (10 controllers × ~3 endpoint tests
plus the end-to-end smoke).

## Environment variables

| Variable                       | Required | Notes                                      |
|--------------------------------|----------|--------------------------------------------|
| `PYCHESTRATE_DATABASE_URL`     | yes      | SQLAlchemy connection string.              |
| `PYCHESTRATE_DEBUG`            | no       | `1` / `true` enables debug error bodies.   |
| `PYCHESTRATE_CREATE_SCHEMA`    | no       | `1` / `true` runs `metadata.create_all` on boot. |
