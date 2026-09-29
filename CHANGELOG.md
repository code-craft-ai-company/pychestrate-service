# Changelog

All notable changes to `pychestrate-service` are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0 releases use the milestone suffixes defined in
[`ROADMAP.md`](ROADMAP.md) (`-preview`, `-alpha`, `-beta`, `-rc`).
Backward compatibility is not guaranteed across pre-1.0 tags; the schema
and runtime contracts are still in flux. A `-preview` tag does not
progress to `-alpha` of the same `MAJOR.MINOR` version — the version is
bumped when the project crosses the preview-to-alpha threshold.

Every git tag has a section below with the same number. The tagging
commit sets `version` in `pyproject.toml` to that number, and the Sphinx
documentation reads its release number from there. The OpenAPI document
(`specs/openapi/pychestrate.yaml`) carries its own `info.version`, which
counts revisions of the REST contract rather than service releases.

The `v0.1.0-alpha` and `v0.1.0-alpha.2` tags predate the renaming of the
release line to `v0.0.x-preview` (see `0.0.3-preview` below); they are
kept for reference and listed in date order.

## [Unreleased]

Changes on `main` since `v0.0.7-preview`. They ship with the next
preview tag.

### Added

- **RPA orchestration** (`specs/6-rpa-orchestration`): Robotic Process
  Automation joins builds, tests, and infrastructure as a fourth job
  domain. Administrators register versioned job types (simple process
  or taskplus tasker); projects bind them through specifications; a
  trigger merges the work packet over the specification defaults,
  validates it against the job type's JSON Schema, redacts secret
  fields, and dispatches a signed `job_kind=rpa` envelope to a capable
  pod. REST under `/api/v1/rpa` and `/api/v1/projects/{id}/rpa`, project
  pages, admin registry pages, a pipeline step kind, a watch action,
  audit kinds, metrics, and the user guide chapter
  `userguide/19-00-rpa-jobs.rst`.

- **UI profiles** (`specs/9-ui-profiles`): the Build, Testing, RPA, and
  Infrastructure surfaces can be hidden per deployment
  (`/admin/ui-profile`, `GET|PUT /api/v1/admin/ui-profile`) and narrowed
  per user (`/account/preferences`,
  `/api/v1/me/preferences/ui.surfaces`) without touching permissions.
  New table `ui_user_preference` (alembic `a3b4c5d6e7f8`). User guide:
  `userguide/20-00-ui-profiles.rst`.

- **The run lifecycle advances from ingest.** `dispatch-ack`,
  `progress`, and `results/complete` now drive a run through
  `DISPATCHING → DISPATCHED → RUNNING → COMPLETED/FAILED`; before this
  every run stayed in `DISPATCHING`. New `POST /api/v1/runs/{run_id}/cancel`;
  the service queues the cancel for the pod on the client's heartbeat
  response.

- **Pod enrollment works end to end.** The client-enrollment CA is
  configured through `PYCHESTRATE_ENROLLMENT_CA_SOURCE` / `_FILE_PATH` /
  `_ENV_VAR` / `_ID` (optional; redeem answers 503 without it), and
  `dev-up` generates a self-signed development CA. The redeem handler
  reads `bootstrap_secret`, as the OpenAPI contract and
  `pychestrate-client` do.

- An MCP (Model Context Protocol) endpoint at `/mcp/1/service` with
  `list_projects`, `get_project`, `create_project`, and `system_health`
  tools, gated on the same permissions as the REST routes.

- A test mode (`PYCHESTRATE_TEST_MODE`, off by default and refused in
  production) that seeds a known admin so live-server test suites can
  sign in, and `development/seed-test-admin.sh` for the same purpose on
  an existing instance.

- `deployment/renew-cert.sh`, a scoped renewal of the alpha host's
  Tailscale TLS certificate.

- `GET /api/v1/envelope-signing-keys/jwks.json` — publishes the
  job-envelope signing public keys as a standard RFC 7517 JWK Set
  using the RFC 8037 `OKP`/`Ed25519` key type, served as
  `application/jwk-set+json`. This closes the contract gap that forced
  operators to install the verification key on each pod out of band
  via `pychestrate-client install-signing-key`: `pychestrate-client`
  refuses to run an envelope it cannot verify, but the service
  previously published no JWKS. `keys[0]` is always the active signing
  key; rotation grace-window keys follow in `kid` order. The response
  is `Cache-Control: private, max-age=300, must-revalidate` with a
  SHA-256 `ETag`, and honors `If-None-Match` with a `304`. Auth and
  the not-provisioned `503` match the existing
  `GET /api/v1/envelope-signing-keys` PEM endpoint, which stays as-is
  — the two paths are two renderings of one key set. Recorded in
  `specs/5-job-envelope` (Requirement 4) and the OpenAPI spec.

- `GET /api/v1/runs/{run_id}/artifacts/{artifact_path}` — downloads a
  stored artifact. The run-detail UI had linked to this path since it
  shipped, but no such route existed, so every artifact link 404'd.
  Auth and permissions match reading the run itself; paths are
  canonicalized and re-checked against the run's storage root so a
  crafted `..` cannot escape it. Artifacts are untrusted job output, so
  active content (HTML / SVG / XML / JS) is served
  `application/octet-stream` with `Content-Disposition: attachment`,
  and everything carries `X-Content-Type-Options: nosniff` — serving
  job-authored HTML inline would be stored XSS on the operator origin.

- `POST /api/v1/resources/{resource_id}/state` and
  `POST /api/v1/projects/{project_id}/pods/{pod_id}/state/transitions`
  — the resource lifecycle (`inventory.transition_state`) and the pod
  lifecycle (`lifecycle_service.apply_transition`) both existed in the
  service layer with no REST surface, so no operator could quarantine a
  flaky machine, retire decommissioned hardware, or drain a pod from
  any interface. The pod route allow-lists only the operator-initiated
  event kinds (`drain`, `deregister`); the system-driven kinds
  (`provision_*`, `client_lost`, `acquire`, `release`) cannot be forged
  through it.

- `PATCH /api/v1/projects/{project_id}/dashboards/{dashboard_id}` —
  in-place dashboard update with optimistic concurrency. Without it the
  dashboard editor could only POST to the collection, so every save
  forked a new dashboard named `"… (edited)"`, and a second save of the
  same name 409'd.

- `system:pods.read` / `system:pods.write` / `system:clients.read` /
  `system:clients.write` in the permission catalog, granted to the
  system-admin role. The Fleet sidebar entries had gated on the two
  read keys since they were written, but the keys were never declared,
  so `me/navigation` filtered both entries out for every user including
  a full administrator — roughly 69 KB of finished views reachable only
  by typing the URL.

- A `--pyc-*` design-token pack (`static/styles/pyc-tokens.css`, linked
  from the shell document). 35 tokens were consumed across the shell
  and bundles with no definition anywhere, so every consumer ran on
  inline fallbacks and the content accent (`#388bff`) disagreed with
  the chrome accent (`#2563eb`) on every page. The pack defines all 35
  in light and dark using the same guard shape as the vendored
  `mj` pack, so the two flip together.

- Shell landing view for `/`, a not-found state for unmatched shell
  routes, and a navigation provider for the command palette.

- **The `pyc` command line grows up** (`specs/8-cli`, user guide
  `userguide/14-00-pyc-command-line.rst`): every REST operation is a
  `pyc <noun> <verb>` command with a plural resource noun
  (`pyc rpa-jobs trigger PROJECT_ID SPEC_ID`; the old tag spellings
  still work), typed `--kebab-case` flags, request bodies from
  `--data`, `--from-file` or `--set` with the body's fields in
  `--help`, help that never contacts the server, "did you mean" for
  mistyped commands and flags, `table` / `json` / `yaml` / `tsv` /
  `raw` output (`-o`, `--fields`, `-q`; lists print as JSON arrays),
  `--all` / `--limit` paging, request ids in error messages, and
  `pyc version`. It installs on its own, standard library only:
  `pipx install ./packages/pychestrate-cli`. The OpenAPI document
  served at `/api/v1/_meta/openapi.json` names the service's version
  as `info.x-service-version`.

- **A REST reference page.** `/api/v1/_meta/docs` renders the OpenAPI
  document with the bundled ReDoc, searchable, from the service's own
  origin, to any signed-in caller. `/api/docs` redirects to it. The page
  sets its own Content-Security-Policy so its search worker runs and
  nothing loads from another host.

- **An environment variable reference.** `userguide/21-00-environment-reference.rst`
  lists every `PYCHESTRATE_*` variable the service and its scripts read,
  with its default and what it changes: state directories, the server
  process, the five key materials, the presign and embed secrets,
  monitoring, and the test-mode variables. A test compares the page with
  the variables the code reads, so one cannot be added or removed
  without the page changing. It replaces a gap the audit measured: 21
  of 47 variables had no description anywhere.

- **One documentation site.** `make docs` builds the user manual, the
  environment reference, the REST API reference (ReDoc, searchable, from
  the OpenAPI document) and the plugin catalog into `.output/docs/site`.
  The catalog was empty before: the site read it before the built-in
  extensions were registered, so it came out as an index and two empty
  pages. It now loads the service the way it starts, finds the 22
  published entries, and stops the build when either category is empty.
  The separate `docs/` Sphinx project is gone. The manual alone still
  builds without the service's dependencies; the full site is built by a
  new `docs-site` job in CI.

### Changed

- **Breaking:** the Python namespace moved from `automojo.*` to `ccai.*`
  (the Code Craft AI rebrand), together with the framework
  dependencies, which are now the `codecraftai-*` packages. Extension
  packs must update their imports.

- **Dependency source:** the `codecraftai-*` framework packages install
  as published 1.x releases from the Code Craft AI package index
  (`https://code-craft.ai/licensed-repository/simple/`) instead of as
  git checkouts of `github.com/automationmojo/codecraftai-*`.
  `codecraftai-errors` is replaced by `codecraftai-foundations`, which
  provides the same `ccai.errors` module.

- **License:** the MIT license was replaced by a proprietary Code Craft
  AI end-user license agreement (`LICENSE.txt`); Pychestrate is licensed
  per organization for on-premises use.

- The consumer web UI carried out the September 2026 UI remediation
  program (179 audit findings, seven phases; see `ROADMAP.md`): strict
  templates, `/resources/*` inside the site shell, shell-aware error
  pages, 404 (not a sign-in prompt) for unknown paths, CSRF-gated sign-in
  and sign-out, content-hashed static assets, shared fragment styles,
  inline SVG icons, and accessibility fixes throughout.

- The web UI is built from the `codecraftai-webworks` `mj-*` component
  library, and one central navigation manifest drives the shell sidebar
  on every route.

- The admin Users and Roles pages now read and write the modern
  identity and RBAC stores (`identity_users` + `auth_local_credentials`
  + `rbac_*`) instead of the legacy `user` / `system_roles` tables.
  Legacy rows are still mirrored on every write so the surfaces that
  have not migrated off `UserManager` stay coherent. See **Fixed** for
  what this repaired.

- The Projects blueprint renders inside the site shell. It was the last
  navigation destination serving a standalone document — its own
  header, its own sidebar, its own Bootstrap/Vue stack, and no link
  back to the rest of the product. `templates/projects/base.html` is
  now a fragment styled from the shared design tokens, and all 60+
  project routes are wrapped at registration. The per-project
  navigation survives as an in-content column. The sidebar entry is
  renamed "All Projects" so it no longer duplicates its group name.

- Every list view distinguishes 401, 403, 404, and offline on load
  failure instead of collapsing all four into "Failed to load X. Try
  refreshing." — a user without permission was told to retry something
  that could never succeed. The action handlers already did this; only
  the read paths threw the status away.

- `POST .../drift:check` states in its response that the check is
  recorded but not dispatched, and the environments view says so in the
  row. The endpoint has always persisted a `PENDING` row with no
  Layer-5 handoff; the UI reported plain success for a check that would
  never resolve.

- **The OpenAPI document matches the routes.** 77 operations the service
  serves no longer carry `x-pychestrate-status: planned`. Eleven served
  operations that were missing are described: release templates (list,
  create, read, change, delete), setting and removing a run variable,
  cancelling a run, the UI timing beacon, and the reference page. The
  two pod-template parameter operations and the run artifact listing,
  which no route serves, are flagged `planned`. The schemas of the most
  used operations now say what the service answers: projects carry
  `state` (`ACTIVE` or `ARCHIVED`), clients and audit records have their
  real fields, and `GET /clients` and `GET /audit` return a bare array.
  `POST /rbac/check` takes `principal_id` and `permission_key`, as the
  route always read them. Twenty operations carry examples captured from
  the running service. Tests compare the document with the registered
  routes and hold every example to its schema. The licence is the
  Pychestrate End User License Agreement, not Apache-2.0, and
  `info.version` is `0.0.17-preview`.

- **Forms show an error next to the field it is about.** A refused value
  used to appear as one banner above the page, and several edit forms
  threw away what was typed. Now the message sits under its input, which
  is marked `aria-invalid` and described by it; a summary at the top of
  the form links to each field; the form comes back with what was typed
  and a 400. This covers the admin, resource, project and RPA forms, the
  four password pages, API token and service account creation, the
  project member forms, and the two action forms whose refusals name an
  input: checking out an IP address (an address that is reserved, taken
  or outside the pool) and changing a device's health status (no
  reason). Those post to their own address and redirect back, so the
  page they return to shows the message once. An error about no single
  input (an inactive account, a device at capacity, a lock-out) stays a
  banner. Sign-in stays generic on purpose.

- **Controls that need permission are shown only to people who hold it.**
  A lab user without the resource-management permission used to see
  Create, Edit, Delete, Force check in and Configure on most resources
  pages and be turned away with "You do not have permission" when they
  used one. The pages now show those only to managers, and editing or
  cancelling a reservation only to its owner; the projects list shows
  Edit only on projects the person may edit. A refusal names what was
  tried ("You need the resource-management permission to delete a
  resource pool.") instead of a page they cannot open.

- **A lab manager can change or cancel someone else's reservation.**
  Only the owner could, so a manager who needed a device could not free
  it. A person with the resource-management permission now gives a
  reason (next to Cancel, or in the edit form), and it goes into the
  audit log with the owner's name as its own record. Anyone else is
  refused as before. The owner is not notified: nothing in the product
  sends notifications yet.

- **IP pools show who holds each address, and a manager can release it.**
  The pool page's User column was always blank and the reason given at
  check-out could not be read back. It now names the holder, shows the
  reason and job, and marks a person's own addresses; the pool list has a
  "Your IP addresses" card. A person with the resource-management
  permission can release an address someone else holds by giving a reason
  next to the button; it is audited with the holder's name. Anyone else
  is refused as before, and the holder is not notified.

- **Tags can be made in the interface.** The Tags page said tags were
  "created automatically when assigned" while nothing could assign a
  new one. It now has a form that makes a tag (name and description),
  an Edit page that renames it (resources that carry it keep it), and a
  Delete that takes it off every resource and leaves the resources. The
  resource create and edit forms have a "New tags" input for tags that
  do not exist yet, with a refused name shown beside it. Managing tags
  needs the resource-management permission; anyone can read the list.

- **Resources can move between pools.** The edit form had no pool field,
  the pool page's "Add Resource" made a new resource, and deleting a pool
  meant deleting every device in it. The edit form now has a pool select;
  a pool's page has "Add existing resources" and "Move resources out" (to
  another pool, so the pool can then be deleted). A name already in the
  target pool stops the move and is named; nothing moves in a bulk move
  unless every resource can. Moving needs the resource-management
  permission.

- **The resource list says what is available.** Finding a free device
  meant reading "Capacity 1/1" against "0/1". The list now has an
  availability filter ("Available now" or "In use", applied in the query
  so the pages and the total are right, and kept by the pager), an
  Availability column ("Available", or "In use by quinn until 18:30
  UTC"), a Check out button on each available row, and a search that also
  matches a device's metadata, so an OS version or a serial number finds
  it. A resource that marks metadata keys as sensitive is found by name
  and description only.

- **A check-out no longer runs into someone else's reservation.** It
  never looked at reservations: an administrator checked out a reserved
  phone for three days across two pending reservations. A check-out
  whose window (now until its timeout, or with no end when it has none)
  overlaps another person's pending reservation is now refused, naming
  who reserved it and when and how to check out anyway (with a timeout
  that ends before then). The person who holds the reservation is never
  in their own way, and two shared windows do not clash. The checkout
  card names the reservation up front.

- **Run Health Check no longer probes inside the web request.** A probe
  that took four seconds held the request four seconds, and a few slow
  devices could use up the server's threads. The button now queues the
  check and returns at once; the housekeeping worker runs it ahead of the
  scheduled checks (it looks every 5 seconds, down from 15), and the
  device's health page shows when it was checked, whether it passed,
  and, when it failed, why: the HTTP status the device answered with, that
  it did not answer in time, or that it could not be reached. Asking again
  while a check waits says one is already queued, and a check the worker
  has not picked up after two minutes is flagged. A check that is switched
  off or has no probe URL is refused with advice instead of reported as a
  failed check. A target the server may not call is no longer retried on
  every scheduler tick; it waits for its interval like any other check.
  The probe timeout was already capped at 30 seconds.

- **The health dashboard is paged.** It loaded a thousand resources to
  fill four tables and cut each group off with no way to see the rest.
  The overview now loads twenty per group, in name order, says how many
  there are, and "View all" opens one status a page at a time. Resource
  lists are now returned in a fixed order, so pages never repeat or skip a
  device.

- **The reservation list has a status filter and shows times in your
  zone.** The reservation forms took times in the browser's zone while
  every page listed UTC, and cancelled reservations stayed in the list
  for good. The list now shows Pending and active by default, with
  Pending, Active, Completed, Cancelled and All as choices; its start and
  end filters are typed in your zone (the same `tz` the forms send); and
  its pager keeps every filter (it dropped the end filter). Times on the
  reservation list, the reservation page and the resource page are
  rewritten by the page's script into your zone (`2026-09-30 09:00 PDT`,
  with the UTC time as the tooltip); without script they stay UTC and say
  so.

- **An availability week.** Resources, Availability draws Monday to
  Monday as a row per device: reservations (exclusive or shared) and
  current check-outs as blocks, overlapping ones on their own lines,
  today and now marked, with a pool choice, previous and next week, and
  a table of the same bookings underneath. The week is laid out in your
  browser's zone (kept in a `pyc_tz` cookie; a `tz` in the address
  wins), and a week with a daylight-saving change is 167 or 169 hours
  long. Allocation pages, health pages and the audit log still show UTC.

- **Reasons and actors are shown.** The reason given at check-out, a
  reservation's reason, who force-checked an allocation in and why, who made
  a pool (by name, not a UUID) and who made a manual health change were
  stored and never displayed. They now appear on the allocation and
  reservation pages, under the holder in the allocation lists, beside the
  Forced badge in the history, on the pool page and in the health history.
  The allocation pages show their times in the viewer's zone as the
  reservation pages do.

- **The Checkout card says why checkout is not offered.** On an offline or
  maintenance device the card disappeared, and someone who already held a
  device was told it was "at capacity". The card now says checkout is
  blocked, since when, why and by whom (with a link to change it for a lab
  manager), that you have it checked out (with a link to your allocation),
  or who has it and until when.

- **Pagers keep their filters and show totals.** The allocation history
  dropped its end date and the resource list its tag filter when paging.
  Every paged list now says "Page 1 of N · T total". `url_for` writes a
  list value once per item.

- **Small fixes.** The disabled Mode field on the reservation edit page
  has a label that points at it (an axe critical). A full IP pool no longer
  says to "extend the pool", which cannot be done: it links to create
  another pool.

- **The minted-token screen can be copied from and survives a reload.**
  It clipped the enroll command, had no copy button, pasted its
  arguments unquoted (a pod label with a space became several
  arguments), and a reload minted a second token whose secret nobody
  saw. The secret and the commands each have a Copy button, the command
  wraps, its arguments are shell-quoted, and a second mint of the same
  project and pod within 30 seconds (a reload or a double click) is
  refused with a message instead of minting again. The secret is still
  shown once and never put in the session cookie. The token list shows
  short ids (the full id is the tooltip), issue and expiry times in your
  zone, a colour per status, newest first, and for a redeemed token which
  client redeemed it and when.

- **Name fields say what they accept.** Every input with a pattern
  carries a title stating the rule, so the browser's refusal is no longer
  just "match the requested format". Variable names may contain periods
  (the system's own, `ui.profile.surfaces`, could not be typed), and the
  server refuses a bad name beside the field, with the rule, for a
  browser that does not check patterns. The users and variables search
  boxes are labelled (a crawl of every reachable server-rendered page
  found no other unlabelled input).

- **Project lists keep their page size and show totals; the dashboard
  covers every project.** Every project list dropped the page size when
  paging and none said how many rows there were; they now keep it and
  show "Page 1 of N · T total". The dashboard built Recent Builds and
  Recent Tests from the first ten projects only, with two queries for
  each, so activity in the eleventh project and beyond never appeared.
  It now reads across all of a person's projects with one query each,
  and says when it lists ten of more projects, with a link to the rest.

- **Variables: strict booleans, kept history, masked values.** "yes",
  "on" and "1" silently became true (and "no", "off", "0" false) in a
  boolean variable, though the form says to use true or false; only true
  and false, in any case, are accepted now, and anything else is refused
  beside the value field. Deleting a variable made its history
  unreachable ("Variable not found") although the rows are kept; the
  history of a deleted variable is shown, marked as deleted, and the
  delete message says where to find it. The list masked values behind a
  Show button while the detail and history pages printed them; all three
  now hide values until asked (the detail and history pages have one Show
  values button each). The history has a Change column (Created, Changed,
  Deleted) and, for a change, a line diff behind the same mask. Integer
  and float values are read strictly: `1_000`, `inf`, `nan` and `1_0.5`,
  which Python accepts, are refused.

- **The Admin menu is in sections.** It listed fifteen entries in one
  run, with the two secrets screens far apart. Each admin entry now has a
  section (People & access, Configuration, Fleet enrollment, Platform),
  the entries of a section are together, and the sidebar writes the
  section's name above them. The Overview stays first. The navigation
  answer carries a `section` on admin entries only; other menus are
  unchanged.

- **Import devices from a spreadsheet.** Registering two dozen devices
  took about a hundred and seventy form interactions. Resources, Import
  takes pasted CSV (or cells pasted from a spreadsheet) with a header row
  naming the columns: `name` (required), `type`, `pool`, `capacity`,
  `description`, `tags`, `metadata` (JSON) and `meta.<key>` for one
  metadata key without JSON. Preview reads every row, checks it against the
  lab (the pool must exist, and its resources must not already have that
  name) and shows what would be made and what is wrong, creating nothing.
  Import then makes every device, or none when any row has a problem. A
  column the page does not know refuses the whole file, so a typo in a
  header cannot silently drop data. Up to 500 devices, 256 KB, needs the
  resource-management permission.

- **The resources pages have room for their tables.** They had two
  left-hand navigations, the shell's and their own beside the content,
  which left 837px of a 1440px screen (421px at 1024) and made tables wrap
  to three lines. The sections now run across the top of the page and the
  content has the full width. In the resource, IP pool, tag and pool lists
  Edit and Delete sit side by side, and Delete is outlined rather than a
  solid red block (the confirmation is unchanged).

### Removed

- The `public` blueprint (an empty `endpoints.py` and a Vue placeholder
  with debug-colored regions), which was never registered or reachable,
  and the palette search provider that queried `/api/v1/admin/search` —
  an endpoint that does not exist anywhere in the service, so the
  command palette could never return a result. The `xtest` bytecode
  left behind by a deleted source tree is gone too, and `AGENTS.md` no
  longer documents `/xtest` as a live convention.

### Fixed

- **Users created through the admin UI could not log in.** The create
  form wrote only the legacy `user` table while the login flow
  authenticates against `identity_users`, so the operator got "User
  created successfully" and the user got "Invalid username or
  password" forever. Only the setup wizard dual-wrote, which is why the
  bootstrap admin worked and nobody else did.

- **Role grants through the admin UI had no effect on access.** The
  Roles pages wrote legacy `system_roles` and stored assignments as a
  comma-joined string, while every access decision comes from the
  `rbac_*` tables via `rbac_evaluator`. Granting a role reported
  success and changed nothing. Relatedly, `rbac_role_permissions` rows
  were schema-only — the evaluator consulted just the in-memory
  catalog — so custom roles created through the UI could never have
  granted anything; grants are now the union of catalog and database.

- The run detail page could not show progress or artifacts. The
  serializer hardcoded `progress_summary` to null, no publisher ever
  emitted the `result*` event kind the artifact pane listens for, and
  the artifact route did not exist (see **Added**). `started_at`,
  `completed_at`, `dispatched_at`, `pod_id`, and `job_name` were
  likewise hardcoded null, and `created_at` was read from
  `entered_state_at`, so a run's creation time changed every time it
  changed state.

- Pagination, in five distinct forms: `url_for` silently dropped every
  non-path keyword argument, so all pagination and filter links in the
  admin and projects sections collapsed to page one and cleared active
  filters; three fleet list views reset the page during refresh; the
  resource-pools pager never set `total-pages`, the only attribute the
  component reads; the legacy resource lists fabricated the page count;
  and the admin secrets and scopes lists paginated server-side while
  rendering no controls at all.

- Backend failures rendered as reassuring empty states. Fleet, webhook,
  and resource views returned `null` on any non-OK response and then
  displayed "No active registration for this pod", "This pool has no
  resource members", "No delivery attempts recorded" — a 403 and a
  genuinely empty list were pixel-identical. Pod detail went further
  and displayed a fabricated `DEFINED` state when the state fetch
  failed, so a `FAILED` pod read as healthy.

- Secrets rotate and delete failures were swallowed into `console.warn`.
  Because a successful rotation only changes `updated_at`, a failed one
  was indistinguishable from success — on the exact action an operator
  performs after a credential compromise.

- Several routes crashed outright: `/resources/allocations` 500'd as
  soon as one allocation existed (the template referenced Flask's `g`,
  which this stack never provides), the project releases list raised on
  every request (wrong keyword argument into the manager), the status
  filter dropdowns raised whenever used (raw strings passed where enums
  were dereferenced), the watch edit form could never be submitted (a
  required `<select>` whose options were never passed), and the project
  calendar rendered an empty grid while discarding the events it had
  fetched.

- The setup wizard's success redirect pointed at `/config/login`, a
  route that no longer exists, so the first screen a new administrator
  saw after completing setup was an empty page at a dead URL. Login
  dropped its `next` parameter (the form carried no hidden field), so
  every sign-in landed on `/` — which itself rendered an empty main
  region — defeating both deep links and session-expiry recovery.

- Legacy admin pages loaded ~2.4 MB of Vue and Bootstrap-Vue that no
  admin template used, and the login page requested three stylesheets
  that no longer exist. Every shell page also shared one browser title
  ("Pychestrate"), making tabs, history, and bookmarks
  indistinguishable.

### Security

- **Session cookies on the HTTPS alpha deploy now carry `Secure`.** The
  flag followed only `PYCHESTRATE_RUNTIME_ENVIRONMENT`, and the
  documented deploy runs as `staging` behind nginx on 443, so its
  session cookies went out without `Secure` although the runbook said
  `X-Forwarded-Proto` controlled it. Every cookie the service sets is
  now `Secure` when the request arrived over HTTPS — directly, or
  through a trusted proxy whose `X-Forwarded-Proto` says `https` — and
  always in production. Trusted proxies come from the new
  `PYCHESTRATE_TRUSTED_PROXY_ADDRESSES` (addresses or CIDR networks,
  `*` for any peer; default `127.0.0.1,::1`). Plain-HTTP development,
  staging and testing servers keep a working sign-in.

- **The service refuses a KEK file other accounts can access.** The
  runbook promised a permission check that did not exist; the loader
  only checked that the file existed and held 32 bytes. A KEK file whose
  mode grants anything to its group or to other users (anything but
  `0600` / `0400`) now stops startup with an error that names the file,
  the mode, and the `chmod` that fixes it. **Upgrade note:** check your
  key file with `stat -c %a <path>` before upgrading.

- The pods and clients REST surfaces enforced no permission at all —
  every handler gated on session presence only, while their sibling
  resource routes enforced `system:resources.read`. Any authenticated
  user could read all pod and client data by typing the URL; the
  feature had simply never been wired into RBAC on either end. All 17
  handlers now enforce the new read/write keys.

- Outbound webhook subscriptions created through the UI were signed
  with an empty key: the service signs deliveries with the
  subscription's `secret_ref`, and the create form never sent one, so
  receivers had no way to verify a delivery came from Pychestrate. The
  create route now generates a 32-byte secret when none is supplied and
  returns it once, and the UI presents it as a copyable value with
  save-it-now treatment.

- The unified login form no longer echoes "Account is not active". That
  check fires before password verification, so surfacing it confirmed
  account existence to anyone submitting any password. The rate-limit
  lockout message is still surfaced — its backoff is keyed on
  `(login_name, source_ip)` and records failures for unknown usernames
  too, so it is not an enumeration oracle.

- The shell catch-all validated only the session cookie's signature and
  never checked the session row, so a stale post-logout cookie still
  received the full application shell while legacy routes correctly
  rejected it. It now performs the same liveness check the blueprint
  routes use.

- Every `/api/v1/*` request without a signed-in principal is refused
  with 401 unless the route is on the explicit allowlist in
  `security/auth/anonymous_access.py` (pod machine-plane routes, signed
  uploads, webhooks, enrollment redeem, the UI metrics beacon); modules
  that never checked permissions now declare them. Admin pages answer
  403 before the handler runs when the caller lacks the page's
  permission; deactivating a user closes their sessions; health probes
  can no longer run commands or reach loopback and metadata addresses;
  project-scoped actions check that the target belongs to the project
  in the URL; RPA secret packet fields are redacted in REST responses.
  Earlier, the RBAC binding, secrets, and sessions REST routes were
  closed to anonymous callers.

### Upgrade notes

- **KEK file mode.** Startup now fails when the KEK file is readable or
  writable by its group or other users. Run `stat -c %a <kek-file>`; if
  it prints anything but `600` or `400`, run `chmod 0600 <kek-file>`
  before upgrading.
- **Reverse proxy on another host.** `X-Forwarded-Proto` is believed
  only from `PYCHESTRATE_TRUSTED_PROXY_ADDRESSES` (default loopback). If
  TLS terminates on another machine, list its address there so session
  cookies are marked `Secure`.
- **Anonymous REST access is refused.** Scripts that read `/api/v1/*`
  without signing in (for example `/api/v1/flags` as a health probe)
  now get 401.
- **Queued health checks.** Run `alembic upgrade head` (the deploy script
  does): it adds two columns to the health check table. "Run Health
  Check" now needs the housekeeping worker to be running, because the
  worker runs the check.
- **Namespace rename.** Code that imports `automojo.*` must import
  `ccai.*`.
- **CI secret rename.** The workflows read the dependency token from the
  `CODECRAFTAI_REPO_TOKEN` secret.
- **Dependency index.** `poetry install` resolves the `codecraftai-*`
  packages from the `codecraftai` source in `pyproject.toml`, so Poetry
  needs access to that index (see "A package index" in
  `userguide/02-00-getting-started.rst`); the GitHub token for the old
  git-source dependencies is no longer used for them.

## [0.0.7-preview] — 2026-05-20

Developer preview: the full deploy with nginx mutual TLS live, so the
orchestration-ingest endpoints are reachable by pod client certificates.

### Added

- Alert-rule editor and dashboard-layout editor pages (#249).

### Fixed

- nginx derives the client certificate's common name through a `map`
  on `$ssl_client_s_dn`, so the orchestration-ingest endpoints receive
  the pod identity they check (#250).

## [0.0.6-preview] — 2026-05-20

Developer preview: the rest of the specification catalog's REST and UI
surfaces.

### Added

- REST for blast-radius guards, SLOs, and release channels (#243).
- Embeddable views (`/embed/{view_key}` with signed URLs) and hardening
  of the plugin-API surface (#244).
- Inbound and outbound webhooks over REST (#245).
- Backup and disaster-recovery domain with REST (#246).
- UI pages for webhooks, guards, SLOs, and release channels (#247).
- Shell pages for the admin overview, feature flags, extension registry,
  and system health (#248).

## [0.0.5-preview] — 2026-05-20

Developer preview: pipelines execute; builds and provisioning stream
live progress.

### Added

- Source integrations as first-class source references in build
  envelopes (#241).
- Generalized progress frames, so build and provisioning runs stream
  live progress like test runs (#242).

## [0.0.4-preview] — 2026-05-20

Developer preview: the full orchestration loop for tests, builds, and
provisioning, pipelines, and REST plus UI for projects, resources,
secrets, metrics, pods, and pipelines.

### Added

- **Site shell** (`specs/9-site-shell`): the `<pyc-site-shell>` web
  component with a permission-gated sidebar (#203), the `/admin/*`
  pages inside it (#204), the command palette, keyboard sidebar
  navigation, mid-session 401 handling and permission-change events
  (#205), and metrics, property tests, accessibility checks, and the
  site-shell chapter of the user guide (#206).
- **The OpenAPI 3.1 contract** for the REST surface,
  `specs/openapi/pychestrate.yaml` (#207).
- **Test orchestration loop:** phase-5 bus subscribers and scheduled
  tasks wired at startup (#208); run-state ingest and run read/list
  endpoints (#209); nginx mutual TLS for the ingest endpoints (#210);
  test catalog and trigger-run REST (#211); the test orchestrator
  constructed at startup (#212); an HTTP long-poll transport for pod
  clients (#213); server-sent live events for runs (#215); the Ed25519
  envelope-signing public key over REST and at enrollment (#216);
  presigned result-upload URLs (#217); a test-run trigger that picks an
  eligible pod when none is named (#222).
- **Build, provisioning, and pipelines:** REST for builds, build
  artifacts, and source integrations (#223), for environments,
  provisioning runs, and drift (#224), and for pipeline definitions and
  matrix sharding (#233); build and provisioning dispatch through the
  job transport (#232, #234); result ingest that brings those runs to a
  terminal state (#235); pipeline execution by a DAG-walking
  orchestrator (#239).
- **REST for projects** (CRUD and members, #226), **metrics** (test
  metrics, time series, dashboards, #228), **scoped secrets** (#229),
  and **resource management** (pools, resources, allocations, health,
  #238).
- **Pages in the shell** for runs (#218), run detail with live updates
  (#219), the test catalog (#220), enrollment tokens (#221), builds
  (#225), infrastructure and provisioning (#227), secrets (#230),
  metrics and dashboards (#231), pods and clients (#236), pipelines
  (#237), and resources (#240).
- `/api/v1/me/*` resolves the signed-in user from the UI session cookie
  as well as the REST cookie, and an alembic backfill binds the
  setup-wizard admin to the system-admin role in the modern RBAC tables
  (#201).
- `ROADMAP.md` with the milestone definitions of the `v0.0.x-preview`
  line (#202).

### Changed

- **Breaking:** Renamed the PR p19g long-poll routes from the
  `/api/v1/agents/{client_id}/...` namespace to
  `/api/v1/clients/{client_id}/...` to match the canonical "client"
  naming for the pod-side runtime. The two affected operations are
  `GET /clients/{client_id}/dispatches:next` and
  `GET /clients/{client_id}/heartbeat`. The supporting code module
  moved from
  `ccai.pychestrate.webservice.agents.restapi.v1.agent_dispatch_routes`
  to
  `ccai.pychestrate.webservice.clients.restapi.v1.client_dispatch_routes`,
  and the registration symbol from `register_agent_dispatch_routes`
  to `register_client_dispatch_routes`. No redirect shim is provided
  — this is an alpha pre-stability rename. OpenAPI spec bumped to
  `0.0.5-preview` (PR p19h, #214).

## [0.0.3-preview] — 2026-05-17

Renamed the active release line from `v0.1.0-alpha` to `v0.0.x-preview`
to set honest expectations. The previously published `v0.1.0-alpha` and
`v0.1.0-alpha.2` tags overstated the project's maturity — alpha implies
feature-complete for a slice, and at the time those tags were cut
roughly two-thirds of the spec catalog was unstarted. Those tags remain
in the git history for reference.

### Changed

- Active release line is now `v0.0.x-preview`. The milestone
  definitions arrived with `ROADMAP.md` in `0.0.4-preview`.

### Added (since `v0.1.0-alpha.2`)

- **Unified `/login` HTML surface** with `?next=<path>` redirect and
  same-origin validation; the legacy `/config/login` is retired (#200).
- **`/admin/*` route mount** for the administrator surface; the legacy
  `/config/*` blueprint moved verbatim (#200).
- **`system:ui.admin.view` permission** granted by `SystemAdminRole`,
  intended as the UX-gating key for the upcoming sidebar (#200).
- **`GET /api/v1/me/permissions`** endpoint returning the principal's
  full system-permission set (#200).
- **`htmlui/next_validator.NextValidator`** enforcing the
  spec-1-authentication NFR-2 same-origin rules on the `?next` parameter
  (#200).
- **Tailscale-issued HTTPS** at the nginx frontend, with `:80` → `:443`
  redirect to the canonical hostname (#197, #198).
- The site-shell and unified-login specifications,
  `specs/9-site-shell` (#199).

## [0.1.0-alpha.2] — 2026-05-17

Superseded by the `v0.0.x-preview` line (see `0.0.3-preview`). Adds the
first-run setup wizard and the systemd + nginx alpha deploy.

### Added

- **First-run setup wizard** (`/setup/unlock`, `/setup/admin`): the
  service writes a one-time initial-admin token to a file on first
  boot; whoever can read it creates the first administrator (#188).
- The database and the wizard token live in the persona presence
  directory, `~/pychestrate` by default (#189).
- **Alpha deploy:** a one-shot deploy script and `deployment/` docs
  (#178), a GitHub Actions deploy over Tailscale (#179), nginx in front
  of the app (#182), gunicorn under systemd (p13as, #185), and scoped
  passwordless sudoers for the deploy user (p13aw).
- `SECURITY` / `NETWORK` / `RUNTIME` environment variables routed
  through `PychestrateVariables` (#196).
- Phase-11 login-flow tests (httpx + Playwright) against the deployed
  alpha (#193, #195), and the `testbase agents` result commands in
  `AGENTS.md` (#194).

### Changed

- Password hashing for the legacy path uses the webworks standard-library
  PBKDF2 instead of werkzeug (#183).
- `run-staging-gunicorn` leaves `PYCHESTRATE_DATABASE_URL` unset so the
  runtime's presence-directory default applies (#191).

### Fixed

- The setup-wizard migration is part of the active alembic chain
  (#190).
- The deploy workflow fails loudly on a Tailscale OAuth 403 (#180);
  pipx-installed poetry is visible to the deploy's SSH session (#186);
  sudo steps get a TTY (#185); rsync falls back when only openrsync is
  available (#184).

## [0.1.0-alpha] — 2026-05-09

First tagged alpha. Closes the **Phase 1 — Identity & Projects** slice
of `specs/implementation-plan.md`. The service can be deployed,
operated end-to-end, and exercised by an admin against either SQLite
(development) or Postgres (production) with the deploy runbook in
`userguide/13-00-alpha-deployment.rst`.

### Added

- **Modern auth stack on the consumer UI.** The
  `/config` / `/resources` / `/projects` blueprints' login flow,
  session validation, and logout now route through
  `security.auth.local_flow` + `session_service`. Implemented via
  `ConsumerUISecurityAdapter` so handler call shapes were preserved
  (#164).
- **RBAC on `rbac_evaluator`.** Consumer-UI permission gating now
  routes through `rbac_evaluator.check_permission` against the
  modern `rbac_*` tables; consumer-UI gates pass canonical
  `system:<action>` permission keys (e.g. `system:resources.manage`).
  Permission catalog populated by the in-tree
  `CorePermissionExtension`; `SystemAdminRole` preset grants the
  default admin set (#167).
- **Alembic migrations** as the production schema strategy. Two
  revisions ship: `b26815647a3c` (modern `PychestratePhase1Base`
  baseline) and `340748287bde` (legacy `PychestrateModelBase`
  stopgap for the consumer-UI surfaces still on `core.managers`).
  Both pass `alembic upgrade head` against fresh SQLite and Postgres.
- **CI workflow** (`.github/workflows/test.yml`) gating six jobs:
  poetry install + sanity import, alembic-upgrade-sqlite,
  alembic-upgrade-postgres, testbase-singlehost-sweep,
  phase10-e2e-isolated, production-startup-smoke. All gating
  (#168, #169, #170, #171, #172, #173, #175).
- **Production-startup smoke test** that forks
  `build_wsgi_application_for_production()` in a subprocess
  against an alembic-migrated SQLite DB and probes `GET /` (#165).
- **Phase-1 acceptance test** (`test_p13ae_alpha_acceptance_m1`)
  that walks the create-project → assign-member → set-variable
  chain and asserts each step emits an audit event (#168).
- **Tier-1..4 consumer-UI e2e coverage.** Anonymous (p13q),
  authenticated happy path (p13r), RBAC permission gating
  (p13v), static assets (p13u), tier-4 session lifecycle
  (concurrent sessions, CSRF rotation, expiry, post-logout)
  (#155, #163, #166).
- **Deploy runbook** (`userguide/13-00-alpha-deployment.rst`)
  covering environment variables, KEK / pepper / cookie-secret
  provisioning, alembic migrations, gunicorn invocation, and
  CI prerequisites (`CODECRAFTAI_REPO_TOKEN` setup) (#168, #170).
- **Auth-stack documentation** (`userguide/12-00-consumer-ui-auth-stack.rst`)
  covering the legacy-vs-modern split, the migration history, and a
  detailed audit of the residual legacy import surface
  (Tier A: 225 utility imports — non-blocking; Tier B: 81 manager
  imports — Phase-2/3 territory) (#157, #176).
- **Extension authoring guide** (`userguide/11-00-extensions.rst`)
  covering factory protocols vs resource extensions, out-of-tree
  packaging recipe, and a complete worked example for a
  production Argon2id password hasher.
- **Phase 1..6 builtin extensions** registered through the
  `extensions/bootstrap.py` chain: phase1 (identity / RBAC /
  audit / project-templates / notification-channels),
  phase2..phase6 (audit-sinks, scopes, retention, etc.).

### Changed

- **`pychestrate-core` git-source dependency removed.** It shipped
  an empty `ccai/pychestrate/__init__.py` that converted
  `ccai.pychestrate` from a PEP-420 namespace package into a
  regular package, blocking access to
  `ccai.pychestrate.webservice` (which lives at
  `source/site/...`). Audit confirmed the dep was unused; removing
  it restored namespace package semantics. The `dbio.py` module
  in `source/packages/ccai/pychestrate/core/` that referenced
  pychestrate-core's content is left as dead code (no consumer)
  (#171).
- **`werkzeug` dependency removed.** Was a transitive of
  `pychestrate-core`. Used only by the legacy `SecurityManager`'s
  password-history and authenticate paths, both dead at runtime
  via the modern adapter. Top-level import in `security_manager.py`
  removed; the two call sites use lazy imports so an explicit
  invocation of the legacy auth path is the only thing that would
  trip an `ImportError` (a useful signal that the legacy auth
  surface needs full retirement) (#172).
- **Python `alembic` is a direct dependency** (was transitive
  through pychestrate-core). Pinned `^1.13.0` (#171).
- **CI workflow private-repo authentication** uses a fine-grained
  PAT injected as `CODECRAFTAI_REPO_TOKEN` repo / org secret. The
  workflow installs a global `git url.<base>.insteadOf` rewrite
  before each `poetry install`, silently authenticating clones
  of the nine private `codecraftai-*` / `pychestrate-core` git deps.
  Setup procedure documented in the deploy runbook (#170).
- **Consumer-UI handlers no longer treat empty CSRF as a refresh
  signal.** `ConsumerUISecurityAdapter.validate_token` returns
  `csrf_token=""`; the cookie's CSRF is the source of truth on the
  modern stack so the dashboard handler now preserves it rather
  than overwriting (#164).

### Fixed

- **Postgres FK ordering bug** in the
  `include_legacy_core_orm_tables` migration. 123 inline
  `ForeignKeyConstraint` declarations on `op.create_table` calls
  were emitted in alphabetical order without respect to FK
  dependency order; SQLite was lenient at CREATE-TABLE time but
  Postgres rejected with `UndefinedTable`. All FKs now emit as
  separate `op.create_foreign_key` calls after every table exists,
  dialect-gated to skip on SQLite (which doesn't support
  `ALTER TABLE ADD CONSTRAINT`) (#175).
- **Postgres ENUM/table name collision.** The `orch_test_outcome`
  table shared a name with its `Outcome` enum; Postgres treats
  tables as implicit composite types in the same namespace so the
  second `CREATE` collided. Renamed to `orch_test_outcome_value`
  to follow the `<table>_<column>` enum-naming convention used
  elsewhere in the migration (#173).
- **`python -m alembic` shadow.** Repo root contains an
  `./alembic/` migrations directory; running `python -m alembic`
  from repo root resolved to the local namespace package which has
  no `__main__`. Switched to the `alembic` console script (whose
  launcher does not add cwd to `sys.path`) in CI and tests (#171).
- **`register_phase1_builtin_extensions` not idempotent.**
  Production startup hit `ConfigurationError: Project metadata
  field registry is already frozen` because `bootstrap_runtime`
  and `register_service_extensions` both invoked phase-1
  registration. Added an `is_registry_frozen()` guard (#165).
- **Test isolation in singlehost sweep.** Including the bare
  `phase1` package matched both `phase1/` AND `phase10/`
  directories via testbase's `startswith` path-prefix check, then
  pulled in every brittle p13 module via
  `collect_python_modules_for_tests`. phase1 is now enumerated by
  18 specific module names (phase2..phase9 are unaffected — no
  phase20+ siblings exist). The underlying testbase bug is logged
  for upstream report (#175).
- **`*ListResponse` dataclass unwrap** at consumer-UI handler
  call sites (`resources/`, `projects/`, `config/` blueprints).
  REST API was returning typed dataclasses; consumer-UI handlers
  expected plain lists. Single-call adapters added at every call
  site (#161, #162).
- **WSGI cookie handling** in `app_pychestrate_main`. Cookies set
  by the response were being dropped on the way out; tier-2 e2e
  surfaced the loss. Added a thin shim that copies `Set-Cookie`
  headers through (#155).
- **Watch create/edit form field translation.** Form fields
  shipped to `WatchManager.create` did not match the dataclass
  shape; the handler now translates form keys to manager keys
  before invoking (#156).

### Known limitations

These are documented in `userguide/13-00-alpha-deployment.rst`'s
"Known alpha limitations" section. None block alpha shipping;
all are tracked for follow-up:

- **Single-host only.** Persistence is centralized but the message
  bus is the in-process stub; multi-host deploys require Phase-2
  bus implementation.
- **Legacy schema co-resident with modern.** 21 consumer-UI route
  files still call into `core.managers.*`; the
  `include_legacy_core_orm_tables` migration ships them. Migrating
  off is Phase-2/3 territory.
- **No audit retention policy.** Audit subscriber writes
  indefinitely.
- **No HA story.** Process restart drops in-flight requests.

### Operator action required

For first-time deployments and CI:

1. Create a fine-grained PAT against the `automationmojo` org
   with `Contents: Read` on the nine private `codecraftai-*` /
   `pychestrate-core` repos.
2. Add it as a repo or org secret named `CODECRAFTAI_REPO_TOKEN`.
3. Provision the KEK, pepper, and UI cookie secret per the
   procedure in the deploy runbook.
4. Run `alembic upgrade head` against your production database
   before first start.

[Unreleased]: https://github.com/code-craft-ai-company/pychestrate-service/compare/v0.0.7-preview...HEAD
[0.0.7-preview]: https://github.com/code-craft-ai-company/pychestrate-service/compare/v0.0.6-preview...v0.0.7-preview
[0.0.6-preview]: https://github.com/code-craft-ai-company/pychestrate-service/compare/v0.0.5-preview...v0.0.6-preview
[0.0.5-preview]: https://github.com/code-craft-ai-company/pychestrate-service/compare/v0.0.4-preview...v0.0.5-preview
[0.0.4-preview]: https://github.com/code-craft-ai-company/pychestrate-service/compare/v0.0.3-preview...v0.0.4-preview
[0.0.3-preview]: https://github.com/code-craft-ai-company/pychestrate-service/compare/v0.1.0-alpha.2...v0.0.3-preview
[0.1.0-alpha.2]: https://github.com/code-craft-ai-company/pychestrate-service/compare/v0.1.0-alpha...v0.1.0-alpha.2
[0.1.0-alpha]: https://github.com/code-craft-ai-company/pychestrate-service/releases/tag/v0.1.0-alpha
