# Pychestrate Service — REST API v1 Reference

Tabular reference for every endpoint exposed by the migrated service.
Use this alongside [`quickstart.md`](quickstart.md) (bring-up),
[`configuration.md`](configuration.md) (tunables), and
[`hardwareonboarding.md`](hardwareonboarding.md) (registering hosts).

The **Auth** column lists the role required by
`AccessPolicyMiddleware`. `—` means the endpoint is public.
`system-admin` means the request must carry an `AuthenticationContext`
whose principal has the `system-admin` role (currently the only
gate, see *Configuration › RBAC and AccessPolicy* for the rollout
plan).

Path parameters use webworks `{name}` syntax. `{name:int}` indicates
an integer-coerced segment.

---

## Auth — `/api/v1/auth`

| Method | Path                                                          | Auth | Description                                                                |
|--------|---------------------------------------------------------------|------|----------------------------------------------------------------------------|
| POST   | `/api/v1/auth/login`                                          | —    | Open a session via local credentials. Two-stage MFA when enrolled.         |
| POST   | `/api/v1/auth/logout`                                         | —    | Close a session. Idempotent; tolerates anonymous callers.                  |
| GET    | `/api/v1/auth/providers`                                      | —    | List enabled credential modes (login picker).                              |
| POST   | `/api/v1/auth/providers/{kind}/{provider_name}/enable`        | —    | Hot-flip a provider's `enabled` flag to True.                              |
| POST   | `/api/v1/auth/providers/{kind}/{provider_name}/disable`       | —    | Hot-flip a provider's `enabled` flag to False.                             |
| POST   | `/api/v1/auth/mfa/challenge`                                  | —    | Issue a fresh MFA challenge for `(user_id, method_name)`.                  |
| POST   | `/api/v1/auth/mfa/verify`                                     | —    | Verify a prior MFA challenge.                                              |

**Login request body** (stage one): `{login_name, password}`. **Stage
two** adds `challenge_id` + `mfa_code`. **Success body**: `session_id`,
`user_id`, `expires_in_seconds`, `cookie_name` plus a `Set-Cookie:
pychestrate_session=<id>` header. See
[configuration.md › Login endpoint](configuration.md#login-endpoint).

---

## Identity — `/api/v1/identity`, `/api/v1/flags`

| Method | Path                              | Auth         | Description                                          |
|--------|-----------------------------------|--------------|------------------------------------------------------|
| POST   | `/api/v1/identity/users`          | system-admin | Create an identity user.                             |
| GET    | `/api/v1/identity/users/{user_id}`| —            | Read an identity user.                               |
| POST   | `/api/v1/flags`                   | system-admin | Register a feature flag.                             |
| GET    | `/api/v1/flags/{flag_key}`        | —            | Read a feature flag's current view.                  |

---

## RBAC — `/api/v1/rbac`

| Method | Path                                       | Auth         | Description                                            |
|--------|--------------------------------------------|--------------|--------------------------------------------------------|
| GET    | `/api/v1/rbac/permissions`                 | —            | List the permission key catalog.                       |
| GET    | `/api/v1/rbac/roles`                       | —            | List role presets and their grant counts.              |
| GET    | `/api/v1/rbac/bindings`                    | —            | List bindings with optional `principal_id`/`scope_id`/etc filters. |
| POST   | `/api/v1/rbac/bindings`                    | system-admin | Assign a role binding.                                 |
| DELETE | `/api/v1/rbac/bindings/{binding_id}`       | system-admin | Revoke a binding.                                      |
| POST   | `/api/v1/rbac/check`                       | system-admin | Evaluate one permission for a principal.               |

---

## Clients — `/api/v1/clients`

| Method | Path                                          | Auth         | Description                                            |
|--------|-----------------------------------------------|--------------|--------------------------------------------------------|
| GET    | `/api/v1/clients`                             | —            | List clients. Filters: `project_id`, `status`, `liveness_state`. |
| GET    | `/api/v1/clients/{client_id}`                 | —            | Read one client view.                                  |
| POST   | `/api/v1/clients/{client_id}/revoke`          | system-admin | Revoke a client identity. Body: `{reason, note?}`.     |
| PUT    | `/api/v1/clients/{client_id}/attributes`      | system-admin | Upsert a batch of client attributes (optimistic concurrency). |
| GET    | `/api/v1/clients/{client_id}/capabilities`    | —            | List a client's registered capabilities.               |
| GET    | `/api/v1/clients-inventory`                   | —            | Paged inventory across projects. Filters: `project_id`, `liveness`, `offset`, `limit`. |

---

## Enrollment tokens — `/api/v1/enrollment-tokens`

| Method | Path                                                       | Auth         | Description                                            |
|--------|------------------------------------------------------------|--------------|--------------------------------------------------------|
| POST   | `/api/v1/enrollment-tokens`                                | system-admin | Issue a new enrollment token. Secret returned exactly once. |
| GET    | `/api/v1/enrollment-tokens`                                | —            | List enrollment tokens (no secrets). Filters: `project_id`, `status`. |
| DELETE | `/api/v1/enrollment-tokens/{token_id}`                     | system-admin | Revoke an enrollment token.                            |
| POST   | `/api/v1/enrollment-tokens/redeem`                         | —            | Agent presents the secret + payload, receives a bearer token. **Public by design.** |
| POST   | `/api/v1/enrollment-tokens/clients/{client_id}/revoke`     | system-admin | Admin revokes a client identity (mirrors clients/revoke; lives here so it shares the RBAC gate with token rescission). |

---

## Audit, Secrets, Retention

| Method | Path                                              | Auth         | Description                                            |
|--------|---------------------------------------------------|--------------|--------------------------------------------------------|
| GET    | `/api/v1/audit`                                   | —            | Page the audit-record stream. Query: `limit` (≤500).   |
| GET    | `/api/v1/audit/{sequence_number:int}`             | —            | Read one audit record.                                 |
| GET    | `/api/v1/secrets`                                 | —            | List secret metadata (no plaintext, ever).             |
| GET    | `/api/v1/secrets/{secret_ref}`                    | —            | Read one secret's metadata.                            |
| GET    | `/api/v1/retention/policies`                      | —            | List retention policies. Filters: `scope_level`, `project_id`, `state`. |
| POST   | `/api/v1/retention/policies`                      | system-admin | Create a retention policy in DRAFT state.              |
| GET    | `/api/v1/retention/policies/{policy_id}`          | —            | Read one retention policy.                             |
| POST   | `/api/v1/retention/policies/{policy_id}/publish`  | system-admin | Transition a policy to PUBLISHED.                      |

---

## Notifications

| Method | Path                                             | Auth         | Description                                          |
|--------|--------------------------------------------------|--------------|------------------------------------------------------|
| GET    | `/api/v1/notifications/channels`                 | —            | List notification channels. Filters: `scope_level`, `project_id`. |
| POST   | `/api/v1/notifications/channels`                 | system-admin | Create a notification channel.                       |
| GET    | `/api/v1/notifications/channels/{channel_id}`    | —            | Read one channel.                                    |

---

## Project templates

| Method | Path                                       | Auth | Description                                |
|--------|--------------------------------------------|------|--------------------------------------------|
| GET    | `/api/v1/project-templates`                | —    | List registered project templates.         |
| GET    | `/api/v1/project-templates/{template_id}`  | —    | Read one template summary.                 |

---

## Projects — `/api/v1/projects`

| Method | Path                                                          | Auth         | Description                                                              |
|--------|---------------------------------------------------------------|--------------|--------------------------------------------------------------------------|
| POST   | `/api/v1/projects`                                            | system-admin | Create a project.                                                        |
| GET    | `/api/v1/projects/{slug}`                                     | —            | Read a project by slug.                                                  |
| PATCH  | `/api/v1/projects/{slug}`                                     | system-admin | Update mutable fields (`display_name`, `description`, `extension_fields`).|
| DELETE | `/api/v1/projects/{slug}`                                     | system-admin | Hard-delete an archived project.                                         |
| POST   | `/api/v1/projects/{slug}/archive`                             | system-admin | Archive a project.                                                       |
| POST   | `/api/v1/projects/{slug}/unarchive`                           | system-admin | Unarchive a project.                                                     |
| GET    | `/api/v1/projects/{slug}/members`                             | —            | List project members.                                                    |
| POST   | `/api/v1/projects/{slug}/members`                             | system-admin | Attach a user with a role.                                               |
| DELETE | `/api/v1/projects/{slug}/members/{user_id}`                   | system-admin | Detach the `PROJECT_OWNER_ROLE` binding (last-admin safeguard).          |
| DELETE | `/api/v1/projects/{slug}/members/{user_id}/{role_name}`       | system-admin | Detach a specific binding.                                               |

---

## Pods — `/api/v1/projects/{project_id}` (Layer-3)

| Method | Path                                                                               | Auth         | Description                                            |
|--------|------------------------------------------------------------------------------------|--------------|--------------------------------------------------------|
| GET    | `/api/v1/projects/{project_id}/pod-definitions`                                    | —            | List pod definitions in a project.                     |
| POST   | `/api/v1/projects/{project_id}/pod-definitions`                                    | system-admin | Create a pod definition. Body: `{pod_name, spec}`.     |
| GET    | `/api/v1/projects/{project_id}/pod-definitions/{pod_id}`                           | —            | Read one pod definition.                               |
| GET    | `/api/v1/projects/{project_id}/pods/{pod_id}/state`                                | —            | Read current lifecycle state.                          |
| GET    | `/api/v1/projects/{project_id}/pods/{pod_id}/state/history`                        | —            | List state-transition log. Query: `offset`, `limit`.   |
| GET    | `/api/v1/projects/{project_id}/pods/{pod_id}/registration`                         | —            | Read the active registration row, or 404.              |
| GET    | `/api/v1/projects/{project_id}/pods/{pod_id}/registrations`                        | —            | List registration history.                             |
| GET    | `/api/v1/projects/{project_id}/pods/{pod_id}/topology`                             | —            | Composed topology graph.                               |
| GET    | `/api/v1/projects/{project_id}/pod-templates`                                      | —            | List pod templates.                                    |
| POST   | `/api/v1/projects/{project_id}/pod-templates`                                      | system-admin | Create a pod template.                                 |
| POST   | `/api/v1/projects/{project_id}/pod-templates/{template_id}/materialize`            | system-admin | Materialize a template into a pod definition.          |
| PUT    | `/api/v1/projects/{project_id}/runs/{run_id}/variables/{name}`                     | system-admin | Set a scoped run variable. Query: `pod_id` required.   |
| DELETE | `/api/v1/projects/{project_id}/runs/{run_id}/variables/{name}`                     | system-admin | Delete a scoped run variable. Query: `pod_id` required.|

---

## Agents — `/api/v1`

| Method | Path                                                  | Auth         | Description                                      |
|--------|-------------------------------------------------------|--------------|--------------------------------------------------|
| GET    | `/api/v1/clients/{client_id}/capabilities`            | —            | (Same as Clients › capabilities; agents read it.)|
| POST   | `/api/v1/agent-rollouts`                              | system-admin | Draft a new agent rollout.                       |
| POST   | `/api/v1/agent-rollouts/{rollout_id}/start`           | system-admin | Transition DRAFT → STARTED, queue offers.        |

---

## Tagging — `/api/v1/tags`

| Method | Path                                                | Auth         | Description                                            |
|--------|-----------------------------------------------------|--------------|--------------------------------------------------------|
| GET    | `/api/v1/tags/taxonomies`                           | —            | List registered taxonomies.                            |
| GET    | `/api/v1/tags/search`                               | —            | Search by tag expression. Query: `kind`, `expr`.       |
| GET    | `/api/v1/tags/{entity_kind}/{entity_id}`            | —            | List tags on an entity.                                |
| POST   | `/api/v1/tags/{entity_kind}/{entity_id}`            | system-admin | Assign a tag to an entity. Body: `{tag}`.              |
| DELETE | `/api/v1/tags/{entity_kind}/{entity_id}/{tag}`      | system-admin | Remove a tag.                                          |

---

## Variables — `/api/v1/variables`

| Method | Path                                              | Auth         | Description                                                                       |
|--------|---------------------------------------------------|--------------|-----------------------------------------------------------------------------------|
| GET    | `/api/v1/variables/effective`                     | —            | Resolve a variable through the scope chain. Query: `name` (req), `project`/`pipeline`/`job`, `include_trace`, `dereference_secrets`. |
| GET    | `/api/v1/variables/{scope}/{scope_id}`            | —            | List bindings at a scope.                                                         |
| GET    | `/api/v1/variables/{scope}/{scope_id}/{name}`     | —            | Read one binding.                                                                 |
| PUT    | `/api/v1/variables/{scope}/{scope_id}/{name}`     | system-admin | Set or replace a binding. Body: `{value, value_type}`.                            |
| DELETE | `/api/v1/variables/{scope}/{scope_id}/{name}`     | system-admin | Remove a binding.                                                                 |

---

## Flows (taskplus orchestration) — `/api/v1/flows`

| Method | Path                                | Auth         | Description                                                              |
|--------|-------------------------------------|--------------|--------------------------------------------------------------------------|
| POST   | `/api/v1/flows`                     | system-admin | Submit a workflow. Body: raw YAML or `{workflow_yaml: "..."}`. 202 + flow_id. |
| GET    | `/api/v1/flows`                     | —            | List every tracked submission, ordered by `submitted_at` desc.           |
| GET    | `/api/v1/flows/{flow_id}`           | —            | Read one submission's state (PENDING / RUNNING / SUCCEEDED / FAILED).     |
| GET    | `/api/v1/flows/{flow_id}/log`       | —            | Captured stdout + log lines for one submission.                          |

---

## Conventions

* **Content negotiation**: write endpoints expect
  `Content-Type: application/json` and a JSON object body. The flows
  endpoint additionally accepts `application/yaml` /
  `text/yaml` for raw workflow bodies.
* **Error shape**: dispatcher errors render as
  `{"detail": "...", "status_code": <int>}`. Validation errors raised
  by handlers (`HTTPException(400, "...")`) render the same way.
* **`HttpOnly` cookie**: hard-coded; the rest of the cookie policy
  is env-driven (`PYCHESTRATE_COOKIE_*`).
* **Bearer-token enforcement** on agent-side endpoints is *not yet*
  wired through `AccessPolicy` — it remains a follow-up.
* **OpenAPI**: endpoint descriptors carry `Doc(summary=...,
  description=...)` metadata; the openapi emitter shipped by
  webworks renders this when invoked. (No live `/openapi.json` route
  is mounted yet.)

## See also

* [`quickstart.md`](quickstart.md) — bring-up walkthrough.
* [`configuration.md`](configuration.md) — env vars, RBAC, middleware,
  flow runtime, WSGI deployment.
* [`hardwareonboarding.md`](hardwareonboarding.md) — registering
  hosts, agent enrollment, flow submission.
