# Pychestrate Service — Release-Readiness Audit

**Date:** 2026-06-11 · **Branch:** `main` @ `2be60c8` · **Method:** 16 parallel
specialist audits (spec coverage, per-subsystem functional audits, REST/OpenAPI
contract diff, persistence/migrations, deployment/ops, static usability
heuristics, live browser walkthrough, full test-suite run).

Artifacts: 87 UI screenshots in `.output/ui-audit/`, test-run output in
`.output/release-audit-2/`.

---

## 1. Executive Summary

**Verdict: the current state supports an honest `-preview` tag only with a
published known-issues list. The `v0.1.0-alpha` slice ("operate the test
orchestration core") is RED — the product's core loop cannot close.**

The codebase is far broader than ROADMAP.md (last updated 2026-05-17) claims —
the site shell, dispatch contract, runs/builds/pipelines surfaces, and
185 REST routes all exist. But breadth is not depth: the audits found that the
single most product-defining flow (enroll a client → dispatch a job → ingest
progress/results → inspect the run) is broken at **five independent points**,
and five domains (projects, secrets, sessions, resources, RBAC) run as
**split-brain dual stacks** where the legacy core ORM and the modern
webservice models hold disconnected copies of the same concept.

| Area | Preview | Alpha slice | Top finding |
|---|---|---|---|
| Spec coverage (breadth) | — | — | 49 FULL / 45 PARTIAL / 14 NONE of 108 specs (existence, not correctness) |
| Orchestration plane | YELLOW | RED | Run state machine never advances past `DISPATCHING` |
| Client/pod plane | RED | RED | No pod-side client runtime exists anywhere |
| Security & identity | YELLOW | RED | RBAC mutation REST routes are unauthenticated |
| Secrets | YELLOW | RED | Two parallel secrets systems; silent dev-key fallback |
| Projects | YELLOW | RED | Dual project stores with no bridge (spec exists, unimplemented) |
| Resources (Layer 4) | YELLOW | RED | Checkout not concurrency-safe; all time-based machinery inert |
| Observability | YELLOW | RED | Login/logout/role-revoke unaudited; UI metrics dropped |
| REST API contract | YELLOW | RED | API-key auth promised in spec, not implemented; 34 live routes marked "planned" |
| Persistence / migrations | YELLOW | YELLOW | Legacy migration ships ~57 tables with zero FK constraints |
| Deployment & ops | YELLOW | RED | No TLS-cert bootstrap, false-positive deploy probe, no rollback/backup |
| Server-rendered UI | YELLOW | RED | Setup wizard ends at a 404; dead CSS links on login/projects/resources |
| Browser frontend (shell) | YELLOW | RED | Shell solid, but 76 pages bypass it; all 6 spec'd web components are vapor |
| UI usability | RED | RED | Three parallel chromes; no UI path to trigger a run; zero ARIA in Jinja templates |
| Test suite | YELLOW | — | 2,841/2,876 pass; all 35 failures = live-deploy auth drift; 4 modules silently fail import |

---

## 2. The Five Systemic Findings

These cut across subsystems and matter more than any single defect.

### 2.1 The core product loop does not close (RED)

A run cannot complete end-to-end, even in a lab, for five independent reasons:

1. **No client runtime.** The pod-side `pychestrate-client` (enroll → poll →
   ack → execute → report) does not exist in this repo or any landed sibling.
   Dispatched envelopes sit unconsumed in the long-poll queue
   (`agents/factories/long_poll_transport.py:13`).
2. **The run state machine is disconnected from ingest.** `dispatch-ack`
   records a receipt but never fires `RECEIPT_RECORDED`
   (`runs/restapi/v1/runs_routes.py:697-736`); progress ingest never fires
   `FIRST_PROGRESS`; the testbase `results/complete` path never fires a
   terminal transition. Every run ever triggered stays `DISPATCHING` forever.
   The timer wheel fires timeouts with no callback, so `DISPATCH_LOST` is also
   unreachable (`extensions/phase5_bootstrap.py:224-238`).
3. **The mTLS chain has never been exercised.** The client CA is never loaded
   at bootstrap — CSR enrollment 503s out of the box
   (`clients/enrollment/ca_adapter.py:146`, no `set_active_ca` call in any
   production path); the nginx TLS server cert has no provisioning step
   (`deployment/deploy-alpha-to-host.sh:507-508`); the ingest endpoints
   short-circuit to 401 without `SSL_CLIENT_S_DN_CN`
   (`runs_routes.py:23-30`).
4. **Dispatch envelopes carry placeholder URLs and empty credentials.**
   Forwarding URLs are hardcoded to `pychestrate.example.com`
   (`orchestration/test/orchestrator.py:371-372` and two more call sites);
   `scoped_secrets` is always `tuple()`.
5. **Nothing survives a restart and nothing reconciles.** The dispatch queue
   is in-memory by design; the result watcher is a no-op
   (`phase5_bootstrap.py:344`); the reconciler only counts
   (`jobs/reconcile/reconciler.py:44-69`); there is no cancel REST route.

### 2.2 Split-brain dual stacks (RED)

Five domains have two disconnected implementations — a legacy core-ORM stack
driving the consumer UI, and a modern webservice stack driving the REST API:

| Domain | Legacy (UI uses) | Modern (REST uses) | Consequence |
|---|---|---|---|
| Projects | `projects` (BigInt) via `ProjectManager` | `projects_projects` (UUID) via service | Project created via REST is invisible in UI and vice versa; bridge spec (`specs/project-model-bridge.md`) unimplemented |
| Secrets | `secrets`/`secret_scopes`, SHA-256(env or `"default-key-for-dev"`) | `phase1_secrets`, KEK→DEK AES-256-GCM | Secret created in admin UI unreadable via REST and vice versa |
| Sessions | `sessions` table via `SecurityManager` | `auth_sessions` via session_service | `/admin/sessions` lists an empty table; terminate is a silent no-op |
| Resources | legacy `resources`/`allocations`/`reservations` | `resources_*` tables | UI inventory and REST inventory are different worlds; REST inventory has **no registration path at all** |
| RBAC | `project_members` role strings | `rbac_evaluator` + `system:*` keys | A grant in one system confers nothing in the other |

Each split also splits the permission model and the audit trail. This needs
one deliberate convergence decision (bridge vs. migrate-and-delete) before any
alpha; every PR that lands on either side of a split increases the cost.

### 2.3 REST auth enforcement is inconsistent, and security defects exist (RED)

- `POST /api/v1/rbac/bindings` and `DELETE /api/v1/rbac/bindings/{id}` have
  **no authentication or permission check** — any anonymous caller who can
  reach the API can grant `system-admin` to any principal
  (`security/rbac/restapi/v1/rbac_routes.py:269-354, 418-453`).
- `GET /api/v1/secrets` and `GET /api/v1/secrets/{ref}` are unauthenticated —
  full secret-ref/scope/KEK metadata enumeration
  (`secrets/restapi/v1/secrets_routes.py:279-314, 401-436`).
- `POST /api/v1/auth/logout` closes any caller-supplied `session_id`
  (no ownership check) (`auth_routes.py:144-175`).
- `idle_timeout_seconds` is written at session-open and never read — sessions
  live until absolute expiry (`session_service.py:99-177`).
- The login form ships without a CSRF token (`config/login.html:44-58`);
  the shell logout form likewise.
- The spec promises `X-Pychestrate-Api-Key` auth; **no header-based auth is
  implemented at all** — CI tooling cannot authenticate to the API except by
  browser cookie (`middleware_webworks.py`).
- `SecurityManager.hash_password`/`verify_password` call module-level
  functions that were deleted (`security_manager.py:344,357`) — reachable
  NameError via the session-admin surface, and the cause of 4 test modules
  failing import (see §5).
- Audit blind spots: `entity.session.opened/closed`, `entity.role.revoked`,
  `entity.client.token_issued/revoked` produce **no audit records**.

### 2.4 "Implemented" features that are inert (MAJOR)

A recurring pattern: models + service + routes exist, but nothing drives them
at runtime, so the behavior never happens:

- No background scheduler/tick exists anywhere — lease expiry, allocation
  timeouts, reservation activation, health probes, the result watcher, and
  receipt-timeout handling are all dead in production.
- The Layer-4 REST inventory cannot be populated (`register_resource` has no
  caller), so its read endpoints can only 404.
- Pool reservation FIFO re-picks the same member forever (no state
  transition on grant) — pools are effectively single-slot
  (`resources/pools/service.py:240-303`).
- `/api/v1/_metrics/ui` validates the frontend beacon payload and drops it.
- `SecretAcl`, `SecretOutboxEntry`, `AuditSinkOutbox`, `backup_record` tables
  exist in schema with no readers/writers.

### 2.5 The paper trail is materially stale — in both directions (MAJOR)

- ROADMAP.md says the site shell (PR3–PR6) is "not started"; it is
  substantially implemented. It also says resources "work"; the deep audit
  shows reservations never activate and health never probes.
- Every `specs/*/tasks.md` checkbox is unchecked, including for shipped work.
- OpenAPI: 34 implemented operations still marked `x-pychestrate-status:
  planned` (the generated client will omit the entire dispatch chain);
  `POST /backups/{id}:restore` is unmarked but always 501; 5 live routes
  (including the pod-variable mutation endpoint) are absent from the spec.
- Four test modules have failed import since the `hash_password` removal —
  silently excluded from every run since.

An evaluator reading the docs would conclude both less and more than the
truth. Fixing the paper trail is cheap and should precede any tag.

---

## 3. UI Audit — Implementation + Usability

### 3.1 What works (verified live)

The live walkthrough (seeded admin, headless Chromium, port 8975) confirmed:
login/logout, flash feedback, all 15 `/admin/*` pages render with real data,
the new shell (`<pyc-site-shell>`) renders with working sidebar groups
(Projects / Orchestration / Insights / Fleet / Operations / System / Admin),
active-item highlighting, runs/builds/pipelines views with graceful empty
states, and the resources area is functionally complete for single-user
flows. **Zero HTTP 500s and zero Python tracebacks across the whole
walkthrough** — the surfaces that exist are stable.

### 3.2 Usability findings (heuristic + live, ranked)

1. **Three parallel chromes (BLOCKER).** `/admin` + shell routes use
   `<pyc-site-shell>` + mj-* components; `/projects/*` (53 routes) and
   `/resources/*` (36 routes) render their own legacy dark-header Bootstrap
   chrome — 76 templates bypass the shell entirely. Navigating Projects →
   Runs is a jarring application switch with disconnected sidebars.
2. **The core operator workflow dead-ends (BLOCKER).** There is no working UI
   path to trigger a run: the Jinja builds pages have no trigger affordance;
   the new builds/pipelines bundles render but their fleet-wide list APIs
   404 (`/api/v1/builds`, `/api/v1/pipelines` are project-scoped only), and
   the run-detail "Back to runs" loses project context. First-run →
   create project → add repo → see results cannot be completed.
3. **First-touch flow is broken (BLOCKER).** The setup wizard's
   post-completion redirect targets `/config/login`, removed in the p17b
   rename — every fresh deploy ends the wizard on a 404
   (`blueprints/setup/routes.py:742`).
4. **Blank pages where landing content should be.** Authenticated `/` renders
   the shell with a populated sidebar and an empty content pane (screenshot
   `65_home_authed.png`); unknown routes return **HTTP 200** with the same
   blank shell (no 404 status, no message); `/admin/system-health` shows
   "Loading system health…" forever.
5. **Dead CSS links.** Login, projects, and resources bases request
   `bootstrap.css`, `bootstrap-vue.css`, `automojo.css` — none ship; 3 404s
   on every page load (`chromeless_base.html:12-14` and both legacy bases).
6. **Raw-identifier cliff edges (MAJOR).** Enrollment tokens require typing a
   project UUID; repository creation requires typing a secret ref from
   memory; the runs filter is a bare "project id" text box. No pickers, no
   cross-links.
7. **Forms (MAJOR).** Server-side validation surfaces only as a top-of-page
   flash, never field-adjacent; the empty project-create POST bounces to
   `/login` instead of re-rendering with errors; 25+ destructive actions use
   bare `window.confirm()`; deactivated users have no reactivate path.
8. **Accessibility (BLOCKER for any external pilot).** Zero `role=`/`aria-*`
   attributes in the entire Jinja template set; no `aria-current` in legacy
   sidebars; muted text `#6c757d` on white is borderline AA; the new shell,
   by contrast, does this correctly — the gap is the legacy two-thirds.
9. **Polish.** Raw `mj.pagination.previous`/`mj.pagination.next` i18n keys
   visible on runs/builds/pipelines; header always says "Account" (display
   name never fetched); terminology drifts between client/agent/pod;
   ~100+ hardcoded hex colors in legacy templates vs. token-driven shell.

### 3.3 Frontend implementation gaps

- All six spec'd web components (`9-wc-*`: log-stream, metric-tile,
  pipeline-dag, pod-topology, resource-picker, result-viewer, secret-editor)
  are unimplemented — the run-detail view has no log viewer.
- 10 of 11 feature bundles race the shell at boot (single `queueMicrotask`
  retry; only the admin bundle listens for `pyc-site-shell-ready`).
- Dead `register_*_sidebar` exports in every bundle post-nav-manifest.
- No CI step verifies committed esbuild bundles match their sources.

---

## 4. Subsystem Detail (selected defects with evidence)

### Orchestration
- State machine disconnect (BLOCKER): `runs_routes.py:697-736` (ack),
  `ingest/progress/service.py` (no transition), `ingest/result/scanner.py`
  (no transition); `transition_table.py:68-69` defines the never-fired edges.
- `COMPLETING` state unreachable (no in-edges) — `transition_table.py:117-119`.
- Run GET responses return `pod_id`/`job_id`/timestamps as always-null
  (`runs_routes.py:380-412`) — the UI cannot show what ran.
- `SharedResultsBackend(backend_driver="local-test")` hardcoded
  (`phase6_bootstrap.py:235`).

### Clients / pods
- `dispatch_attempt_id` stand-in uses `envelope_id`
  (`long_poll_transport.py:127-130,196`) — breaks on first retry attempt.
- Dispatch endpoint mTLS check is CN==path string equality; no DB lookup, no
  revocation check (`client_dispatch_routes.py:224-254`).
- WebSocket-over-mTLS transport (spec canonical): 0 of all tasks.

### Secrets
- KEK loader accepts ≥32 bytes; backend requires exactly 32 → service starts
  healthy, every crypto op fails (`kek_loader.py:120` vs `local_backend.py:81`).
- KEK file OSError → silent fallback to `"default-key-for-dev"`
  (`routes_scopes.py:114-128`).
- No rewrap path: KEK rotation orphans every existing ciphertext.

### Resources
- `reserve()` docstring claims a row lock that does not exist
  (`checkout/service.py:5-7` vs `:103-124`); legacy `with_for_update` is a
  no-op on the deployed SQLite under 4×2 gunicorn — double-grant of an
  exclusive resource is possible on both planes.
- Only "concurrency" test simulates concurrency sequentially
  (`test_allocation_manager_concurrent.py:209`).

### Persistence
- Migration `340748287bde` creates ~57 legacy tables with **no
  ForeignKeyConstraint declarations** (ORM declares dozens).
- `gen_random_uuid()` server defaults are Postgres-only; latent SQLite
  failures on any non-ORM insert.
- `PYCHESTRATE_AUTO_CREATE_SCHEMA` (`runtime_bootstrap.py:663-668`) rebuilds
  from ORM metadata, not the alembic chain — dev/staging drift whenever a
  migration adds something the models lack (root cause of the band-aid in
  commit `0a9927c`; a live `runs_run_event_outbox` OperationalError appeared
  in this audit's own test logs).
- `core/dbio.py:153` raw-string `TRUNCATE` breaks on SQLAlchemy 2.x.

### Projects
- `JSONResponse(status_code=201, body=body_out)` — wrong kwarg, the
  create-release-from-template endpoint 500s on every call
  (`release_templates_routes.py:1086`); zero behavioral tests cover it.
- `template_id` accepted on create and silently inert.

### Deployment / ops
- Post-deploy probe `curl -fsS http://HOST:80/` passes on nginx's 301 even
  with gunicorn dead (`deploy-alpha-to-host.sh:728-732`).
- `alembic upgrade head` mid-deploy with no snapshot/rollback/recovery doc.
- Deploy PAT persisted in remote `~/.gitconfig`
  (`deploy-alpha-to-host.sh:362-363`); weak seeded admin password in `.env`.
- No backup of any kind (DB or key material); `specs/10-backup-dr` complete
  on paper, service layer absent. Single host + SQLite ⇒ disk failure is
  total data loss.
- No log rotation for `~/.pychestrate/server.log`; gunicorn 30s default
  timeout vs nginx 300s proxy timeout.
- Setup-gate allowlist exempts `/health`+`/healthz`, but the real endpoint is
  `/api/v1/system/health` → monitoring sees the setup redirect.

### REST contract
- 185 registered routes; `make openapi-validate` passes; **zero** dead
  flask_restx controllers remain (clean).
- `test_api_auth_enforcement.py` / `test_api_error_format.py` test helper
  functions that exist nowhere in the production path — false assurance.

---

## 5. Test Suite Results

_Run: `testbase testing run --root source/testroots/automojo
--includes=automojo.tests.singlehost --output=./.output/release-audit-2`
(2026-06-11, 21 min wall time)_

**2,876 total — 2,841 passed · 28 failed · 7 errored · 0 skipped (98.8%).**

- **All 35 failures/errors share one root cause and are environment-dependent,
  not code regressions:** every one is a phase-11/phase-12 live-deploy test
  (login-flow httpx, mj-components browser, and all 24 `*_in_shell` document
  tests) that authenticates against the deployed Tailscale host
  (`tc-app-server.tailb75ce6.ts.net`) using `PYCHESTRATE_TEST_ADMIN_LOGIN` /
  `..._PASSWORD` from `.env` — and the deployed instance rejects those
  credentials with 401. The deployed host and the repo's test credentials
  have drifted apart, so the live-deploy verification suite is currently
  un-runnable end to end.
- **Consequence worth noting:** the shell's primary regression coverage (the
  phase-12 in-shell suite) only exercises the *deployed* instance, so shell
  regressions are invisible to a local/CI run whenever the deploy target is
  out of sync — which is the case today.
- The local, in-process portion of the suite (phases 1–10, core managers,
  restapi, phase-4/5/6 services) is **fully green**.

Known independent of the run outcome:

- **4 modules fail collection** (excluded from every run):
  `test_security_manager_{password,history,reset,auth}.py` — all
  `ImportError: cannot import name 'hash_password'`. Legacy password/auth
  coverage has been silently absent since the removal.
- Coverage holes called out by the area audits: no test drives the run state
  machine through the REST ingest endpoints; no enroll→dispatch→ack→results
  end-to-end; no true concurrency tests in the resource plane; no test for
  unauthenticated access to RBAC/secrets mutation/list routes; no
  upgrade/downgrade roundtrip per migration; no setup-wizard completion test
  (would have caught the `/config/login` 404).

---

## 6. Release Determination

### `-preview`: conditionally honest (YELLOW)

The label's own definition ("foundation + a few domain surfaces work
end-to-end; not for use beyond the author") is met **only** if the known-issues
list ships with the tag. A short hardening punch list would materially clean
up the preview (all small, independent fixes):

1. Setup-wizard redirect `/config/login` → `/login` (1 line).
2. Remove the three dead CSS `<link>`s from `chromeless_base.html` and both
   legacy bases.
3. `JSONResponse(body=…)` → `content=…` in release_templates_routes.
4. Add auth gates to `/api/v1/rbac/*` mutation + `/api/v1/secrets` list/read.
5. Logout session-ownership check.
6. Delete or fix `SecurityManager.hash_password/verify_password`; repair the
   4 import-broken test modules.
7. Fix the deploy probe to hit `/api/v1/system/health` via loopback; add the
   health path to the setup-gate allowlist.
8. Resolve `mj.pagination.*` i18n keys; return 404 status from the shell
   catch-all for unknown routes.
9. Update ROADMAP.md (shell status, resources caveats) and unmark the 34
   implemented OpenAPI operations.
10. Cron `sqlite3 .backup` + key-file copy on the host as a stopgap backup.

### `v0.1.0-alpha` ("operate the test orchestration core"): RED

Critical path, in dependency order:

1. **Pod-side client runtime** (the sibling repo) — nothing else matters
   until a client can enroll, poll, ack, execute, and report.
2. **Close the run-lifecycle loop server-side** — fire state transitions from
   ack/progress/results; wire the timer-wheel timeout; real forwarding URLs;
   cancel route; persist or reconcile the dispatch queue across restarts.
3. **Make mTLS real** — CA loading at bootstrap, TLS server-cert bootstrap
   script, revocation check on dispatch auth, one end-to-end enrollment test.
4. **Pick a convergence strategy for the five dual-stack domains** — at
   minimum the project model bridge (spec ready) and the session-table
   unification, since both have user-visible breakage today.
5. **Unify the UI chrome** — wrap `/projects/*` and `/resources/*` in the
   shell; add a landing view at `/`; add a trigger-run affordance and the
   log-stream component for run detail.
6. **Auth hardening pass on the REST surface** + API-key auth (CI tooling is
   a primary consumer for this slice).
7. **Minimal ops floor** — backup, rollback procedure, honest deploy probe.

---

*Generated by a 16-agent audit; each finding above carries file:line evidence
from the agent reports. Where two agents disagreed (e.g., spec-matrix breadth
ratings vs. deep-dive correctness), the deep-dive evidence was preferred and
the disagreement noted.*
