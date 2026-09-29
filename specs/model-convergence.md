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
| ADM-07, ADM-08 (#366, #367) | Same rule: the modern secrets store and the modern variables service survive; the legacy pages become read-only, then go. Not part of this pass. | Later |
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
