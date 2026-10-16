# Model Convergence — Decisions and Plan

This document records the calls made for the audit items that turn on "which
of two systems survives". It follows `specs/project-model-bridge.md`, which
settled projects: the registry project (UUID + slug) is the system of record
and the web-UI project is linked to it. The same rule applies here.

**The rule.** One concept, one system. The system that survives is the one the
REST API, the orchestration modules and the site-wide (bundle) pages already
use. The other stays reachable for existing data, says so on the page, and is
removed from the navigation once nothing needs it.

Choices below were made for usability first (a person should never have to
know which of two systems holds what), then for the long-term cost of keeping
two.

## 1. Decisions

| Item | Decision | Status |
|---|---|---|
| PRJ-08 (#442) | Stop listing project sections nothing can fill. Reach the working pages (Runs, Pipelines, Test catalog) from the project sidebar instead. Build no create flow for the legacy model. | Done |
| PRJ-07 (#353) | Retire the project Builds tab in favour of the site-wide Builds page. Until the last legacy build page is gone, a build that nothing can run says so and links there. | §2 |
| RES-05 (#365) | Fleet → Resources is the registry resource plane. The legacy `/resources/*` pages stay under the names they have today until their data has moved (§3), and the two sub-navigations stop competing. | §3 |
| RES-04 (#402) | The registry resource plane (`/resource-pools`, `/api/v1/resources`) is the one model jobs use. Add the missing "register a resource" call first, then `requires:` in job specs. | §3 |
| RES-21 (#368) | Same model; its empty states point at the step that fills them. | §3 |
| ADM-07 (#366) | Same rule: the modern secrets store survives. Nothing reads the legacy store, so the legacy pages say so and offer an import into the vault (§9); then they become read-only, then go. | §9 |
| ADM-08 (#367) | Same rule: the modern variables service survives. Step 1 (system-owned keys read-only) is done; step 2 makes the Admin Variables pages manage the modern store, so a variable created there is the one the runtime resolves (§8). Step 3 removes the legacy store. | §8 |
| ADM-22 (#513) | A missing entity or an unknown path is a real 404 inside the shell, with a link back to the list. It is not a redirect with a flash. | §4 |
| XC-08 (#529) | Sign the first administrator in when setup finishes, through the ordinary sign-in path. | §5 |
| DOC-20 (#511) | The service serves its own user guide, so the guide always matches the running release and works where the internet does not. | §6 |
| CLI-20 (#441, closed) | The one thing it left open: leave the service's log and database paths where they are. | §7 |

## 2. Builds (PRJ-07, #353)

Today the project Builds tab lists rows in `project_builds` that nothing runs
(`BuildManager` is called only from UI routes), so they wait in "pending" and
the log page says "Live: refreshing every 10s". The site-wide Builds page uses
the orchestration model, which dispatches.

- The sidebar's Builds entry opens the site-wide page filtered to the project
  (`/projects/{id}/open/builds`, the link added for PRJ-08).
- The legacy build pages stay reachable by address, with a notice at the top
  saying builds now start from the Builds page and linking to it. A pending
  legacy build shows "Nothing can run this build" instead of "Live".
- Removing the legacy build tables is a separate step, once no row in them is
  still wanted.

Not in scope: making the site-wide Builds page run a build end to end (the
source checkout and envelope questions are #347 and #455).

## 3. Resources (RES-04, RES-05, RES-21)

Two systems exist:

- **Legacy** `/resources/*` (server-rendered): resources with tags, IP pools,
  reservations, allocation history, health. It has no REST API and nothing
  outside the pages uses it.
- **Registry** (`resources/` package; `/resource-pools` bundle;
  `/api/v1/resource-pools`, `/api/v1/resources/{id}`): inventory, pools, pool
  reservations, leases, health, usage history, with specs
  `4-resource-inventory` … `4-usage-history`. Nothing can register a resource
  (`register_resource` has no caller and the API has no create call), so no
  pool can have a member, and no job or pod client refers to a resource.

The registry plane survives: it has the REST surface, the specs, the
checkout/lease/reservation logic and the metrics. The legacy pages have none of
those. Order of work, each step shippable by itself:

1. **Register a resource.** `POST /api/v1/resources` (kind, name, tags,
   attributes), an "Add resource" form on the Resource pools page and on a pool
   ("Add member" offers existing resources and a way to create one). Permission
   `system:resources.manage`. This unblocks every later step.
2. **One Fleet menu.** Fleet → Resources opens the registry list. The legacy
   pages keep their own entries under a "Legacy" heading and carry a notice; the
   duplicate sub-navigation and the two names for one page ("Health Status" /
   "Resource Health") go.
3. **Import.** Copy legacy resources, pools and tags into the registry (one
   idempotent command, matched on name), then mark the legacy pages read-only.
4. **Jobs use resources.** A job spec may declare `requires:` (pool or tags,
   count, `exclusive|shared`). Dispatch reserves through the existing pool
   reservation logic and releases on completion, cancellation or lease expiry.
   Its own spec (`5-job-dispatch` gains a section) before any code.
5. **Device kinds.** A device member kind (phone, board) beside `linux_host`,
   `network_switch` and `synthetic_role`; bulk onboarding (RES-22).

This pass covers step 1 only.

## 4. Not found (ADM-22, #513)

There are three cases and they get three answers:

- A path the shell does not own (`/nope`): already a 404 page inside the shell.
- A missing entity on a server-rendered page (`/projects/999`, `/admin/users/x`):
  a 404 page inside the shell that names the thing ("Project not found") and
  links back to its list. The URL is kept so it can be corrected. Handlers say
  so with one helper, `not_found_redirect`, so no handler builds its own copy.
- An unknown id under a bundle prefix (`/runs/<id>`): the bundle already shows
  a not-found view. The response stays 200 because the id is looked up by the
  page's script; a server lookup for every bundle route is not worth its cost.

## 5. First sign-in after setup (XC-08, #529)

Setup asks for the setup token, creates the first administrator and sends the
person to the sign-in page to type the password they just chose. The person
has proved control of the token and chosen the password in the same browser
session, so signing them in adds no exposure that typing the password would
not. It must go through the same session-creation path as sign-in (audit event,
session record, cookie flags), must happen only once, after the token is
consumed, and must not skip any check the sign-in path applies.

## 6. Documentation site (DOC-20, #511)

The product is self-hosted, often behind a firewall, so a link to a site on the
internet is a link that may not open. The service serves the built user guide
from `/docs/` (static files from the release it is running) and the account
menu links to it. Publishing the same build to a public address is a later,
independent step; plugin `docs_url` values then name that address.

## 7. Paths (CLI-20, #441)

`~/.pychestrate/server.log` and `~/pychestrate/pychestrate.sqlite` are where
every existing install, backup job and runbook expects them. Moving them
changes every one of those at once for a naming preference. They stay. If a
move is wanted later it is a migration with a documented cutover, not a
default change.

## 8. Variables: one store (ADM-08, #367), step 2

**Finding.** The Admin Variables pages wrote the legacy `global_variables` table. Nothing in the runtime reads it except the interface profile
(`ui.profile.surfaces`); project templates, pod configuration and `GET /api/v1/variables/effective` read the modern bindings
(`variables_variable_bindings`). A variable created on the page therefore did nothing, and one set through the API never appeared on the page.

**Decisions (2026-10-15).**

1. **The SYSTEM-scope bindings of the modern store are the global variables.** The Admin Variables pages list, create, edit, delete and show the history of
   exactly those rows. A variable set through `/api/v1/variables` at system scope appears on the page, and one created on the page is what
   `/api/v1/variables/effective` resolves.
2. **The modern store gains what the page needs, and the API benefits too:** a `description`, a `default_value_text`, a `created_at`, and a history table
   (`variables_binding_history`: scope, name, type, old and new value, who, when). `set_variable` and `unset_variable` write the history row in the same
   transaction as the binding, so a change from the page, the API or the interface profile page is in History and nothing is recorded twice.
3. **The page does not change.** A `SystemVariableStore` with the legacy `GlobalVariableStore`'s interface (it inherits the type checks and the
   parsing of typed text, and raises the same errors) sits behind the page's existing seam, so the handlers, templates and their field-level errors stay as they
   are. The interface profile reads and writes the same store.
4. **Existing data is copied once, by the migration**, name by name, only where the modern store has no SYSTEM binding of that name, with each variable's
   description, default, timestamps and history. The legacy tables are left untouched: a rollback is a redeploy of the previous release, and step 3 removes them
   when nothing reads them.
5. **A system-owned variable stays read-only on the page** (step 1). The API can still set it (it needs the same administrator permission), and the page
   shows the change in History.

**Not part of this step.** Editing PROJECT-, PIPELINE- or JOB-scope variables on the page (the API has them); removing the legacy store and its tests (step 3); a
secret-valued variable type on the page (the modern store has `SECRET_REF`; the legacy page never offered it).

## 9. Secrets: one vault (ADM-07, #366), step 1

**Finding.** Admin, Secrets (legacy) and Admin, Secret Scopes write the legacy `secrets` / `secret_scopes` tables; System, Secrets is the vault (`/secrets`, the KEK/DEK store).
A secret created in either never appears in the other. The audit also said the consumers point at the legacy store.

**What is true now (checked 2026-10-15).** Nothing in the product reads the legacy store. The only places that construct the legacy `SecretManager` are the two legacy pages
themselves. Repository credentials resolve through the vault (the legacy manager is an optional fallback no builder configures), inbound webhooks and notification channels
store their secrets in the vault, and the secret pickers the forms offer list vault secrets. The legacy store is an island: what is written there is read by nothing.

**Decisions (2026-10-15).**

1. **No consumer has to change**, because none reads the legacy store. "One secret picker for every consumer" is already the case for the forms that ask for a secret
   (they list vault secrets).
2. **The legacy pages say what they are** and point at the vault: titled "(legacy)" (the Secret Scopes entry too), with a notice that nothing reads these secrets and that new
   secrets belong in System, Secrets.
3. **An import carries what exists into the vault**, on request: an administrator (`system:secrets.admin`) chooses *Import into the vault* on the legacy list. Each legacy secret is decrypted
   with the legacy key and stored in the vault, service-wide (ORG scope), under `<scope>/<name>` (the form the legacy references and the repository form used), through the
   vault's own service, so its access rules and audit apply. A name the vault already holds is skipped, never overwritten; a secret that cannot be decrypted is reported by name and
   changes nothing. The result says how many were imported, skipped and failed. The import never shows or logs a value, and it leaves the legacy rows alone (deleting them is the person's
   choice, afterwards, on the same page). The legacy description and type are not carried (the vault records neither).
4. **Then the pages become read-only, then go** (step 2 and step 3, not part of this step): creating a legacy secret or scope is refused with a pointer to the vault; the pages and their
   tables are removed once the import has run everywhere.

## 10. The legacy variable and secret stores removed (ADM-08 #367 and ADM-07 #366), step 3

**State checked 2026-10-16 on staging (a copy of the database, read-only, every row listed).** `global_variables` and `global_variable_history` hold 0 rows. The legacy
secrets hold 18 scopes and 12 secrets: all 12 secrets are soft-deleted leftovers of the August browser tests (`brsct…`, `brsdl…`, `brsed…`), and no scope holds a live secret
(`company` and `ci-verify-…` are empty). Nothing of value is in any legacy table, and the real secret (`company/github`) is in the vault. Deleting them loses test leftovers only.

**Decisions.**

1. **Variables.** What `SystemVariableStore` inherited from the legacy `GlobalVariableStore` (the value checks, the parsing of typed text, the request and response types, the errors)
   moves into `variables/system_store.py`, and the legacy class goes. The request and response types are renamed `SystemVariable*`: "Global" described a table that is gone.
   `VariableType` stays in `core.orm` (project variables use it). `ProjectManager.resolve_variable` is the one other reader of the legacy table (no product code calls it, but it would
   have started returning nothing): its global fallback reads the SYSTEM bindings of the modern store.
2. **Secrets: the read-only step is skipped.** Step 2 (pages read-only) protected a transition nobody is in: the import has been available since step 1 and there is nothing left to import.
   The legacy pages (Admin, Secrets (legacy); Secret Scopes (legacy)), their templates, menu entries, the import route, `legacy_import.py` and `SecretManager` are removed together. So is
   `RepositoryManager`'s optional `secret_manager` fallback, which no builder ever configured.
3. **The tables are dropped by migrations that refuse to destroy live data.** The variable tables are dropped outright (the copy into the modern store ran in `f7b2c9a4d1e6`, earlier in
   the same chain, so any database that reaches the drop has been copied). The secret tables are dropped only when no *live* (not soft-deleted) legacy secret exists; otherwise the
   migration stops before changing anything, naming the count and saying to deploy the previous release, run *Import into the vault*, and upgrade again. Soft-deleted secrets and empty scopes
   are dropped: nothing can read them. The downgrades recreate the tables empty, so a rollback to the previous release starts (the data is not restored: restore it from the pre-deploy backup).
4. **Backup first.** The pre-deploy backup (`pychestrate-backup.service`) runs before each of the two deploys; the staging rows were listed before the change.

**Not part of this step.** RPA taking secret values inline in the packet (the audit's second example for #366) is a separate finding. PROJECT-, PIPELINE- and JOB-scope variables on the
Admin page, and a cross-worker invalidation for the effective-value cache, stay as the #367 comment lists them.
