.. _17-00-site-shell:

***************************************
Site Shell — Unified UI Chrome (Phase 10)
***************************************

Pychestrate's Jenkins-style site shell wraps every authenticated
page with one consistent header, a permission-gated left sidebar,
a main content area, and a global ``Ctrl/Cmd + K`` command
palette. The shell is implemented as a single custom element
``<pyc-site-shell>`` plus a Python adapter that serves the same
shell HTML for every non-chromeless route.

Refer to the canonical spec at ``specs/9-site-shell/`` for the
EARS acceptance criteria, design diagrams, and the milestone
breakdown.

Overview
========

The shell sits at the top of Layer 9. It consumes
``1-authentication`` (session cookie + ``/login`` redirect
contract), ``1-rbac``
(``GET /api/v1/me/permissions`` and the ``ui.admin.view``
permission), and ``9-ui-design-tokens`` (every color, spacing,
and font reference). Feature surfaces -- the admin bundle, the
project dashboard, the run-detail page -- contribute sidebar
entries and command-palette providers through the shell's
in-browser registry. The shell is feature-agnostic: it never
hard-codes which features exist.

Routes are either *shell* routes or *chromeless* routes:

- **Shell routes** (everything authenticated) are served via the
  shell HTML document. The page-specific custom element mounts
  into the ``<main>`` slot.
- **Chromeless routes** -- ``/login``, ``/logout``,
  ``/setup/*``, ``/__health/*``, ``/errors/{404,403,500}`` --
  bypass the shell entirely and render their own minimal HTML.
  The site shell bundle SHALL NOT load on these routes.

Adding a Sidebar Group From Your Bundle
=======================================

Feature bundles register sidebar groups and entries at load time
via the ``window.pychestrateShell`` registry handle. The
registry intersects each entry against the live permission set
from ``/api/v1/me/permissions``.

.. code-block:: javascript

    const handle = window.pychestrateShell
    if (handle !== undefined && handle !== null) {
        handle.sidebar.registerGroup({
            groupId: "admin",
            label: "Admin",
            requiredPermissions: ["system:ui.admin.view"],
        })
        handle.sidebar.registerEntry({
            entryId: "admin.users",
            label: "Users",
            route: "/admin/users",
            requiredPermissions: ["system:users.read"],
            group: "admin",
        })
    }

Rules:

- An entry with ``requiredPermissions: []`` is visible to every
  authenticated user.
- A group with ``requiredPermissions`` hides the entire group
  (header + every entry) when the caller lacks any of them,
  regardless of per-entry permissions.
- Duplicate routes are dropped with a ``console.warn``
  (``pychestrate.ui.shell.sidebar_dup_route``); first
  registration wins.

Adding a Palette Provider
=========================

Bundles can contribute a provider to the ``Ctrl/Cmd + K``
palette:

.. code-block:: javascript

    handle.palette.registerProvider({
        providerId: "admin.search",
        label: "Admin",
        requiredPermissions: ["system:ui.admin.view"],
        timeoutMs: 3000,
        query: async (q) => {
            const response = await fetch(
                "/api/v1/admin/search?q=" + encodeURIComponent(q),
                { credentials: "same-origin" },
            )
            const body = await response.json()
            return body.results.map((row) => ({
                id: row.id,
                label: row.label,
                description: row.description,
                route: row.route,
            }))
        },
    })

Result shape::

    {
        id: string,            // unique within this provider
        label: string,         // visible primary text
        description?: string,  // optional secondary text
        route?: string,        // navigate target if no onActivate
        onActivate?: () => void | Promise<void>,
    }

The shell runs every visible provider in parallel with the
declared ``timeoutMs`` (default 5 s). A provider that throws or
times out renders an inline "this provider is unavailable"
notice without blocking the others.

Chromeless Routes
=================

Chromeless routes are listed in
``source/site/ccai/pychestrate/webservice/webinterface/site_shell/chromeless_routes.py``.
The route-registration pipeline rejects any new shell route
colliding with a chromeless prefix at startup with
``ConfigurationError`` (B-3 in ``9-site-shell/tasks.md``).

Mark a route chromeless only when it must NOT load the shell
bundle (login, setup, canonical error pages). Authenticated
feature pages are always shell routes.

Observability
=============

DOM CustomEvents emitted by the shell:

- ``pyc-site-shell-ready`` --
  ``{visibleEntryCount, degraded}``.
- ``pyc-site-shell-navigated`` -- ``{from, to}``.
- ``pyc-site-shell-sidebar-clicked`` --
  ``{entryRoute, entryLabel}``.
- ``pyc-site-shell-permissions-changed`` --
  ``{added: [...], removed: [...]}``.
- ``pyc-site-shell-empty-state-rendered`` -- ``{}``.
- ``pyc-site-shell-palette-opened`` -- ``{}``.
- ``pyc-site-shell-palette-closed`` -- ``{}``.

Window-level events:

- ``pyc-session-401`` -- any page may dispatch this to surface
  the re-auth toast.
- ``pyc-permissions-fetch-failed`` -- emitted when the
  permission fetch falls through to the degraded banner.

Client metrics beaconed to ``POST /api/v1/_metrics/ui`` (PR p17g):

- ``pychestrate_ui_shell_tti_seconds`` (histogram) -- emitted once
  on ``pyc-site-shell-ready``.
- ``pychestrate_ui_shell_sidebar_render_duration_seconds``
  (histogram) -- per render.
- ``pychestrate_ui_shell_navigation_permission_refetch_seconds``
  (histogram) -- per navigation refetch.
- ``pychestrate_ui_shell_palette_open_duration_seconds``
  (histogram) -- keydown to ``palette-opened`` event.
- ``pychestrate_ui_shell_palette_fanout_duration_seconds``
  (histogram) -- query to all providers settled.
- ``pychestrate_ui_shell_sidebar_entry_clicked_total``
  (counter) -- per click, labeled with ``entry_route``.

The endpoint is informational in p17g: it validates the payload
shape, rate-limits to 12 batches per remote address per minute,
and logs a one-line summary. Aggregation into a Prometheus
exposition is a separate concern.

Invariants
==========

The shell upholds two security-flavored invariants enforced by
automated checks:

1. **No browser storage writes** -- The shell never writes to
   ``localStorage``, ``sessionStorage``, or ``IndexedDB``. The
   permissions cache and any session-scoped UI state live in
   in-memory singletons that die with the tab. Enforcement is
   the ``tests/storage-invariant.test.mjs`` static scanner.

2. **No hard-coded colors** -- ``styles.css`` defines every
   color / shadow / font through ``--pyc-site-shell-*`` tokens
   under a ``:root`` block. The tokens default to the local
   fallback values when ``9-ui-design-tokens`` is not loaded.
   Token names follow the inventory in ``styles.css``.

Testing Your Bundle Inside the Shell
====================================

Bundle tests are Playwright-driven and run against a real
deployed instance -- there is no Node-based unit-test harness.
The browser tests live in
``source/testroots/ccai/tests/singlehost/pychestrate/``
``webservice/phase11/test_p23a_mj_components_browser_m1.py``
(and any sibling ``test_p*_browser_*.py`` files for view-
specific coverage). The conventional pattern:

1. Sign in via the shared ``_sign_in`` helper.
2. Navigate to your bundle's route.
3. Assert that the view's custom elements upgraded and that
   the key user-facing affordances (rows, links, form fields,
   pagination, ...) are present.

Pure-helper assertions (URL builders, paging math, formatters)
that the retired Node harness covered now ride on integration
coverage -- if a helper breaks, its consumer view's browser
test surfaces the regression. See ``AGENTS.md`` for the
broader testbase + Playwright pattern.

Migration Guide: Vue Templates to Custom Elements Inside the Shell
==================================================================

Pychestrate originally rendered most authenticated pages from
Vue templates served by a flask blueprint. The migration to the
unified shell is incremental:

1. **Identify the page's data dependencies** -- the existing
   ``GET /config/...`` controller already returns JSON; reuse
   that exact contract from your custom element rather than
   reshaping it.
2. **Write a Web Component** for the page. The component takes
   no router responsibility -- the shell's ``ShellRouter``
   mounts the right component for the active route.
3. **Register sidebar entries** for the routes your component
   serves. Match the permission keys to the route-level
   ``@require_permission`` guards already on the server.
4. **Mark the legacy Vue route chromeless** while it is still
   used, then delete it once the custom element ships.

Forward-looking: Vue templates remain in the codebase until each
page has a custom-element replacement. The shell is happy to
host either; chromeless routes can continue to render the legacy
Vue document until they are migrated.
