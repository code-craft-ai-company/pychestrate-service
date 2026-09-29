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

- The account menu links to documentation that exists (DOC-20): "API
  reference" (`/api/docs`) and "Error types" (`/errors`), between API tokens
  and Sign out. There is no link to the user guide yet: the documentation
  site has no public address.

- The running release is visible (DOC-13). The account menu in the site
  shell ends with "Pychestrate <release>", read from `pyproject.toml`, and
  `GET /api/v1/system/health` names it (`version`) for callers who may see
  the details; the status-only form that monitors get carries no version.
  The CHANGELOG already has a section for every tag, the ROADMAP table
  says which number means what, and the Sphinx release comes from
  `pyproject.toml`.

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

- Registering an environment offers the kinds that exist and their fields
  (ORC-17). The form asked for a kind name whose placeholder named a kind
  that does not exist (`terraform`) and a JSON object whose example was
  invalid for the only kind there is. It now lists the kinds the server has
  loaded, shows the chosen kind's own fields (`k8s-cluster`: cluster id,
  region, API endpoint, node pools, capability tags; required ones starred)
  and builds the `attrs` object from them, so nothing needs to be typed as
  JSON. A kind describes its fields with an optional `attribute_fields()`
  on the kind protocol; a kind that does not still works through a typed
  kind and a JSON box, whose placeholders are now `kind name` and `{}`.
  A number field can say it must be a whole number of at least some
  minimum (`integer`, `min`), and the form then names a value the kind would
  refuse before sending it.
  `GET /api/v1/environment-kinds` lists the kinds and fields (read
  permission on environments). The release-channel, pipeline, SLO and guard
  forms still carry placeholder text of their own; those are not changed
  here.

- The setup wizard signs the new administrator in (XC-08). Finishing it used
  to send them to the sign-in page to type the password they had just
  chosen; it now signs them in and opens the home page. It goes through the
  ordinary sign-in path (`SecurityManager.authenticate`, so the audit trail
  and lockout accounting see it) and only after the setup token was checked
  and the account created in the same request. If the credentials are not
  accepted for any reason, the wizard falls back to the sign-in page as
  before. `POST /login` shares the same two helpers.

- A missing thing is a 404 page, not a redirect (ADM-22). `/projects/999`,
  `/admin/users/<no such id>` and the other server-rendered pages that look
  a thing up used to answer 303 to the list with a "... not found." flash;
  they now answer 404 with the site's error page inside the shell. It says
  what was not found ("Project not found"), keeps the address, and offers
  "Back to <the list>" as its main action. The rewrite covers 101 places in
  the admin, projects and resources pages; they call one helper, and a test
  keeps them from building their own flash redirect again. An unknown path
  under `/admin` (`/admin/nope`), which answered 200 with an empty page, is a
  404 too: the shell serves only the five paths its admin bundle handles.
  Unknown ids under the other bundle prefixes (`/runs/<id>`) still show the
  bundle's own not-found view with a 200, because the page's script looks the
  id up.

- A project's builds are on the Builds page (PRJ-07). Nothing in this version
  picks up a build made on the project's own Builds page, so every one waited
  in "pending" while its log page said "Live: refreshing every 10s". The
  project sidebar's Builds entry now opens the site-wide Builds page filtered
  to the project (`/projects/{id}/open/builds`), where builds dispatch. The
  older build pages stay reachable by address with a notice saying a build
  started there is not run and linking to the Builds page, and the log of a
  build that has not started says "Waiting: nothing has started this job"
  instead of "Live".

- A resource can be registered, and a pool's member chosen by name (RES-04).
  `register_resource` had no caller and the API no create call, so no resource
  existed, no pool could have a member, and nothing could use a lab resource.
  `POST /api/v1/resources` registers one (`201`; `400` for a kind that is not
  loaded, naming the kinds that are; `409` for an identity already registered;
  `422` when the kind refuses the attributes) and `GET /api/v1/resources`
  lists a project's resources (`kind`, `state`, `tag` and `include_retired`
  narrow it). The Resource pools page lists the project's resources and has a
  "Register a device" form; a pool's page adds a member from a list of the
  project's resources by name, where it asked for a pasted resource id. This is
  the first step of the plan in `specs/model-convergence.md`; jobs do not use
  resources yet (RES-04 stays open).

- The two sets of resource records are named and told apart (RES-05). Fleet
  now has "Resources and Pools (preview)" for the newer records (it was "Pod
  Resource Pools (preview)") and "Older Resources" for the older ones, whose list
  no menu reached before. The older pages' sub-navigation uses the sidebar's
  names ("Resource Health", it said "Health Status"), its first section is headed
  "Older resource records", and the older resources, pools and tags pages carry
  a notice that they hold the older set, that jobs do not use it, and where the
  newer set is. They are still two sets: merging them is step 3 of
  `specs/model-convergence.md`.

- The service serves its own user guide (DOC-20). The account menu now links
  to "User guide" (`/docs/`), between API tokens and API reference, and the
  plugin catalog's 23 documentation addresses point at the guide's own catalog
  pages (`/docs/extensions/protocols/<name>.html`, `/docs/extensions/resources/<name>.html`;
  they named `docs.pychestrate.io`, a host nothing publishes) and become
  absolute when `PYCHESTRATE_PUBLIC_BASE_URL` is set. `make docs-into-service`
  builds the Sphinx site and installs it in `docs-site/` at the root of the checkout; the deploy
  script runs it (a guide that does not build is skipped with a warning) and
  the app mounts the directory at `/docs`, with the files' safe path handling,
  gzip and ETags of the other static assets. Without a built guide the link
  is absent and `/docs` says the guide is not installed. The catalog pages no
  longer carry a "Documentation" line that would link to themselves.

- The run, build and provisioning lists lead with what ran, not a hash
  (ORC-11). A run row starts with its job name (its kind when it has none)
  and the short id after it, then the type spelled out ("Test · testbase",
  "Build · makefile"), the project, the state, the creation time and how long
  it ran ("3m 12s", "so far" while running, a dash before it starts). A build
  row leads with its runner and target ("makefile · docs") and shows its source
  ("main @ github.com/acme/widgets"); a provisioning row with its action and
  driver ("apply · terraform"). The Started and Completed columns of the runs
  list are replaced by Duration (the run's page has them). The server already
  sent all of it. Branch, commit and who or what triggered a run are not in the
  API yet, so they are not shown.

- Empty lists say how to fill them (ORC-34). The Runs page says a run starts
  from the Test catalog, a pipeline or a build and links to each; the Builds
  page no longer says "No projects exist yet." and "Select a project to view
  its builds." together (it says there are no projects once, with a link to
  create one) and an empty project says "Choose Trigger Build above"; the
  Pipelines page says to paste a pipeline document into the form above, whose
  heading is now "Define a pipeline" (it was "Create / Upsert Pipeline"); and
  Test metrics for a project with no runs says there is nothing to measure and
  links to the Test catalog, instead of showing "Pass rate 0%".

- The Webhooks page picks a project by name (ORC-18). It asked for a raw
  project UUID before it would show anything; it now lists the projects the
  person can see (as the other bundle pages do), selects the one named in the
  address (`/webhooks?project_id=`) or else the first, and loads that project's
  integrations at once. When the projects cannot be listed it falls back to the
  id field, and only then says "Enter a project id". The environment id on the
  Blast-radius guards page and the ids shown as names elsewhere are not done.

- A list's filters and page are kept in the address (ORC-27). The Runs,
  Builds, Provisioning and Pipelines lists read `project_id`, `state` and
  `page` from the address when they load (`/runs?state=failed` was ignored)
  and write them back whenever they refresh, replacing the history entry so
  Back still leaves the page. A filtered view can be shared or bookmarked, and
  an unknown state in the address is ignored. On the run, build, provisioning
  run and pipeline pages, "Back to ..." returns to the list as it was left
  (filters and page) when the page was opened from that list, and to the bare
  list otherwise. The other bundle lists (test catalog, environments, pods,
  dashboards) do not do this yet.

- A build or provisioning run opens from its id alone (E2E-38). `/builds/{id}`
  said "This link is missing its project context" unless the address carried
  `?project_id=`, so a link shared anywhere but the list did not open. A
  build's id is also its run's id, and `GET /api/v1/runs/{id}` names the
  project: the build and provisioning run pages now ask for it when the address
  does not carry it, and put it in the address so a refresh keeps it. An id no
  run answers to says "No build with this id could be found, or you do not have
  access to it". The pipeline page still needs its project in the address
  (pipelines have no run to ask).

- The command palette finds more than pages (XC-17). "checkout", a project's
  name, "create", "sign out" and "theme" all answered "No results". It now also
  lists projects by name (under "Projects"), offers actions (Create a project,
  Register a device, Run tests, Trigger a build, Define a pipeline, Create an
  API token, Preferences, Switch theme, Sign out; a page-opening action is
  offered only when its section is in the person's navigation), and opens a run
  or build from a pasted full id ("Open by id"). A source that matched nothing
  shows no heading while another has results, and one line ("No results.") when
  nothing matched anywhere. Users, resources and runs by name or partial id are
  not searched yet.

- The Pipelines list leads with the name and shows the source (ORC-37). Its
  "Digest" column showed the pipeline's id a second time (the id is the digest);
  it is now "Source" ("ci.yaml @ 1a2b3c4", the file and the commit the
  definition came from), the row leads with the pipeline's name and the short id
  follows in a muted style, and "Cached" reads "Saved". Arrowheads on the DAG
  edges are not done.

- Two admin pages explain themselves (ADM-30). System Health printed its time
  as ISO text with microseconds and cut a health check's reason off after
  sixteen characters; it now reads "Checked 2026-09-29 12:49 PDT" like every
  other time and the reason column is wide enough for a real reason. The empty
  Feature Flags page says what a flag is (it switches an optional behaviour on
  or off without a release) and where one comes from (the REST API or an
  extension). The boxed Refresh buttons, the header pattern shared with other
  pages and plain-language names for each health check are not done.

- Roles are built by product area, not from 73 raw keys (ADM-06). The role
  forms listed every permission key in one scroll box, 52 of them described as
  "... via the REST surface". They now group the keys into fewer than 45 areas
  ("Builds", "Resource pools", "Project secrets" ...), name what each allows
  ("View", "Start", "Change", "Administer", "Members · manage"), drop the
  implementation wording from the descriptions, and have a filter box and an
  "N of 73 selected" count; the checkbox value is still the canonical key (shown
  on hover) and the role page groups the same way. Presets, cloning a role, a
  list of who holds it and a preview of the menu a role unlocks are not done.

- A display name has a length limit (ADM-41). A 3,000-character name broke the
  users table because nothing bounded it. The create and edit user forms, the
  REST create call (`POST /api/v1/identity/users`, 422) and the setup wizard now
  refuse a display name over 100 characters ("Display name must be at most 100
  characters", at the field), the inputs carry `maxlength`, and long values wrap
  inside a server-rendered table's cell instead of widening it. Deleting or
  anonymising a user (a data-protection request) is not done: it needs decisions
  about the audit trail, tokens, sessions and project ownership first.

- The runs list downloads as a spreadsheet (ORG-F22). There was no export
  anywhere. `GET /api/v1/runs?format=csv` returns the whole filtered list (at
  most 5,000 rows, paging does not apply) as a CSV attachment (run id, project,
  job name and type, state, outcome, created/started/completed, duration, pod;
  `X-Export-Truncated: true` when cut), and the Runs page has a "Download CSV"
  link that follows its filters. Every cell is written so a spreadsheet cannot
  read it as a formula (a job name is chosen by whoever wrote the job); the
  helper (`csv_export.py`) is there for the other lists. Builds, resources,
  users and a lab-utilization report are not done (the audit log already had
  its own export).

- A project's sidebar lists only sections that can hold data (PRJ-08).
  Infrastructure, Tests, Pipelines, Channels, Schedules and Calendar are
  gone from it: nothing creates a test or infrastructure specification, a
  release pipeline, a channel, a schedule or a calendar event in the web-UI
  project model, so eight of its sixteen entries led to lists that stayed
  empty. In their place, CI/CD lists Runs, Pipelines and Test catalog (each
  follows the same interface surface setting as the site-wide entry), and
  they open the site-wide page filtered to the project through
  `/projects/{id}/open/{runs|pipelines|test-catalog}`. The old addresses
  still open, with their Preview notice. The Overview's Recent Tests card
  links to Runs, and the Releases list no longer offers Pipelines and
  Channels buttons.

- A destructive action asks in the site's own dialog (XC-15). Every
  `data-confirm` form (delete a project, a resource, a user, a variable;
  deactivate; revoke) asked through the browser's own confirm box, which a page
  can neither style nor word. The shell now opens a modal `<dialog>`: the message
  in full (one paragraph per line), Cancel focused so a stray Enter deletes
  nothing, the acting button named for what it does ("Delete project",
  "Deactivate"), Escape meaning no, and the rest of the page inert. It follows
  the light and dark themes. The bundle views that call the browser's confirm
  directly (pod drain and retire, run cancel, resource actions, webhook and
  feature-flag toggles) still do; see the issue.

- The `type` of an error response now leads somewhere, and the dispatcher's
  own errors are problem documents (DOC-14). The documented types named
  `https://docs.pychestrate.io/errors/...`, a site nothing publishes; they
  are now `/errors/<slug>` (absolute under `PYCHESTRATE_PUBLIC_BASE_URL` when
  it is set), and the service serves a public page at each, plus `GET
  /errors`, saying what the error means and what to do (HTML, or JSON for
  `Accept: application/json`). An unmatched path, a wrong method and an
  unhandled exception used to come back as the dispatcher's `{"detail": ...,
  "status_code": ...}`; they are now `application/problem+json` of the
  matching type, with the `Allow` header kept on a 405. A client that
  compared `type` to the old `docs.pychestrate.io` strings must compare the
  slug. The `docs_url` values of the plugin protocols still name
  `docs.pychestrate.io/plugin-api/...`: the documentation site has no public
  address yet.

- The project sections that nothing can fill now say so (PRJ-08). Test
  and infrastructure specifications, release pipelines and the release
  calendar's events are read from the web-UI project model, and no page or
  API creates them, yet their empty states said "managed via the API" or
  "triggered by watches, pipelines, or the API". They carry the "Preview"
  notice the Channels and Schedules pages already had, the project
  navigation labels Infrastructure, Tests, Pipelines and Calendar
  "(preview)", and the Tests and Pipelines pages link to the Test catalog,
  Runs and Pipelines pages (filtered to the project) where those things do
  work. The empty Releases list points to Release Templates. The tabs are
  not hidden and nothing new can be created; that stays a decision for the
  project-model issues (#353, #365, #402).

- The pod client (`pychestrate-client`) now agrees with `pyc` on what it
  shares (CLI-20, client repository): `enroll` takes `--server-url` like
  `pyc login` (`--service-url` still works), its default state directory is
  `$XDG_DATA_HOME/pychestrate-client` (an already-enrolled pod keeps using
  `~/.pychestrate-client` until the new directory exists), and its docs and
  messages say "pod label", the word the Enrollment Tokens page uses. The
  Enrollment Tokens page still prints `--service-url` so its command also
  runs on a pod with an older client. The service's own `server.log`
  (`~/.pychestrate/`) and database (`~/pychestrate/`) stay where they are:
  moving them means changing the systemd unit, the log rotation and the
  backup job on every host.

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

- Bundle views show the server's reason when it refuses a request (ORC-08). A
  run refused because no pod was enrolled said "The environment cannot accept
  this action right now", and validating a pipeline without a commit said
  "not a valid DAG": the views mapped the status to a fixed sentence and dropped
  the problem document's `detail`. A shared reader (`shared/problem-detail.js`)
  now lets the provisioning, environments (register and drift check), catalog
  (test run), pipelines (validate), pod (drain, retire), client (revoke),
  feature-flag, guard, dashboard and webhook views show "Provisioning run not
  started: No enrolled pod can take this run" and keep their sentence as the
  fallback when the server gives no reason (or only repeats "Not Found"). The
  builds, SLOs, alert-rule, dashboard-editor and release-channel views already
  did this.

- Every bundle page shows the "session expired" notice when the session has
  ended (XC-12). Only some views turned a 401 from the API into the shell's
  notice (`/runs` did; creating a secret after the session ended said "Failed
  to create the secret. Try again."). The shell now wraps `fetch` once and
  announces the expiry for any 401 from this site's own `/api/`, whichever view
  made the request; the response is handed back unchanged, so a view still shows
  its own message too, and repeated 401s share one notice with its "Sign in"
  link back to the page.

- Two more accessibility fixes in the bundle views (ORC-24). The run's progress
  bar had the `progressbar` role and its numbers but no name (a screen reader
  announced an unnamed progress bar); it is now "Run progress", with a value
  text ("42% complete"). And the timeseries chart no longer leaves focusable
  elements inside its `aria-hidden` SVG: `<mj-chart>` hides the SVG from
  assistive technology (its data is also in an accessible table) but makes
  every data point tabbable, so a keyboard user could tab to points a screen
  reader cannot see; the points are taken out of the tab order after each render.

- Sortable table headers sort from the keyboard (ORC-24, WCAG 2.1.1). The
  vendored `mj-data-table` sorts a column only when its header is clicked (its
  keyboard handling covers the arrows, Home, End and Escape), so Enter and
  Space on a focused header did nothing. The shell now gives every table in
  every bundle the standard behaviour: Enter or Space on a focused sortable
  header does what a click does.

- Primary buttons in the bundle views are readable in the dark theme (WCAG
  1.4.3). The mj token pack keeps the text on the accent white, which is 3.55:1
  on the dark theme's light-blue accent (below the 4.5:1 AA asks for at 14px);
  axe flagged every primary `mj-button` (Save, Upsert, Add) in the dark theme.
  The text on the accent is now the page's own dark in both dark cases (the
  explicit choice and the OS preference); the light theme is unchanged.

- The Enrollment Tokens page no longer skips a heading level (WCAG 1.3.1): "Mint
  New Token" was an h3 straight under the page's h1. A test reads the headings
  of every server-rendered template, full and empty, and fails on a skipped level.

- The "Skip to main content" link has a target that exists (WCAG 2.4.1). It
  pointed at `#pyc-main-content`, but the shell gave the main region that id
  only inside the link's own click handler, so on every page the target was
  missing until the link had been used once (an accessibility checker flagged
  every page, and the link did nothing from a URL fragment). The main region
  now has the id, and can take focus, from the moment it is built.

- Every form control on a bundle page has an accessible name (ORC-42). Six
  text fields had none: the pipeline document and matrix spec, the new
  resource pool's name, description and capability tags, and the webhooks
  page's project id (`mj-text-field` and `mj-textarea` take their name only
  from their own `label`, not from a wrapping label or a host `aria-label`).
  They are labelled with the component's `label`, so the visible text is the
  same and a screen reader now announces it. On the 26 navigation pages that
  have form controls, 56 controls were read and none is unnamed.

- The two native checkboxes in the bundle views follow the theme (ORC-48): the
  test catalog's "Include retired" and the alert-rule editor's "Enabled" use
  the theme's accent colour and an 18px box instead of the browser's default
  blue at its default size. (The component library has only a checkbox group,
  so this is done in the bundles' stylesheets.)

- Bundle detail pages are titled by what they show (ORC-35). A run, a build, a
  provisioning run, a pipeline, an environment, a pod, a client, a resource
  pool and a resource were all just their section in the tab ("Runs ·
  Pychestrate"). Once the page has loaded its entity the tab reads "Run
  3f2a1b7c · Runs · Pychestrate" (the name for pipelines, environments, pools
  and resources; the short id for the rest), and a page that renders again
  replaces the entity instead of stacking a second one. The headings on the
  pages are unchanged.

- Bundle pages show times the way the glossary says (XC-14). The runs, builds,
  pipelines, pods, clients, environments, guards, catalog, secrets, webhooks
  and release-channel views (and the home page's recent runs) printed the
  browser's default format ("9/22/2026, 4:34:12 PM": 12-hour, no zone, a
  different shape per locale), and read a server time without a zone as the
  viewer's local time, shifting it by their UTC offset. They now share one
  formatter (`shared/datetime.js`, bundled into each): "2026-09-22 16:34 PDT",
  24-hour, in the viewer's zone, with a zone-less server time read as UTC.
  The "as of" refresh stamps read "16:21:05 PDT", and a secret's rotation date
  is "2026-09-22".

- Plain words on the run pages (ORC-38). The build and provisioning-run detail
  pages said "Layer-5 run" beside a bare UUID; they now say "Run" and the id
  links to the run's page. "Repro digest" (builds list and detail) is "Inputs
  digest", with a tooltip saying it covers the input files, toolchain and
  environment, and the run's artifact "Results stream (JSOS)" is "Raw results
  stream".

- SLO and test-rate percentages never read better than they are (ORC-36). An
  objective of 99.95% was shown as "100.0%" (every SLO ratio was rounded to
  0.1%), and a 99.6% pass rate as "100%" (whole percents). SLO ratios now keep
  the precision their nines need (99.95%, 99.996%) and are cut, not rounded, so
  only exactly 100% reads "100%"; a test rate that is not exactly 0 or 1 reads
  "<1%" or ">99%".

- A rejected embed shows a page that says what happened (ORC-46). Where an
  embed's signed link is refused (expired, forged, incomplete, unknown key or
  view) the frame showed a bare paragraph in the browser's default style,
  "This embed could not be displayed (403)". It is now a small page in the
  design tokens (light and dark) with a heading, a plain-language reason ("The
  link has expired."), and "Ask whoever shared it for a new link"; the reason
  stays on the page as `data-embed-error` and the statuses are unchanged.

- The resources dashboard fits and guides (RES-44). The four count cards share
  one row at laptop width instead of wrapping three and one; the four health
  icons are one size, so the Maintenance number no longer sits 2px low; Quick
  Actions is as wide as the cards above it, with its buttons in a row; and a
  lab with nothing set up gets a "Get started" checklist (resource pool,
  devices, IP pool, each marked Done or To do) for people who may manage
  resources.

- The sign-in page is a sign-in page (XC-08, ADM-35). It has one heading,
  "Sign in to Pychestrate", a neutral line ("Enter your username and
  password.") instead of "Welcome Back ... the configuration panel", and the
  tab says "Sign in · Pychestrate". After a failed attempt the username is
  still in the form and the cursor is in the password field, and the error is
  inside the card and announced at once instead of sitting above it. Someone
  who is already signed in is sent on (to a safe `next`, else home) instead of
  being shown the form again. The first administrator still has to type the
  password they just chose after the setup wizard.

- Browser tabs tell pages apart and use one separator (PRJ-39). The Projects
  dashboard and the project list were both "Projects", and an IP pool and a
  resource pool of the same name had the same title; they are now "Project
  Dashboard", "All Projects", "IP Pool · <name>" and "Resource Pool · <name>".
  The templates joined the page and the entity with " - " and the shell added
  " · ", so a project page read "Members - demo · Pychestrate"; it now reads
  "Members · demo · Pychestrate". The Resources dashboard is "Resources
  Dashboard".

- Admin lists are compact and their forms line up (ADM-42). Edit and
  Delete/Deactivate sit side by side in the users, variables, roles, secrets
  and secret-scope lists instead of one over the other, and the per-row
  destructive buttons (those, plus tokens, enrollment tokens and sessions)
  are outlined instead of solid red; the bulk "Terminate all" stays filled.
  The checkboxes of the UI Profile and Preferences pages are beside their
  labels (they sat on a line of their own; the `pyc-choice` class had no
  styling), and the audit filter's controls share one height so their labels
  share a line. A browser test renders the real templates and measures them.

- Empty tables no longer carry a phantom empty row (ADM-44). `ui.empty_state`
  with a `colspan` writes a whole `<tr>`, and 21 templates wrapped it in a
  `<tr>` of their own, which browsers repair by closing the outer row and
  leaving it empty above the message. The wrappers are gone, and a test
  renders every template with full and empty lists and fails when a row
  opens inside a row.

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
