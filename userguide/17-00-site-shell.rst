.. _17-00-site-shell:

***********************************************
Site Shell -- Unified UI Chrome
***********************************************

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

The shell is the front of the interface. It consumes
``1-authentication`` (session cookie + ``/login`` redirect
contract), ``1-rbac`` (``GET /api/v1/me/permissions`` and the
``system:ui.admin.view`` permission), the navigation manifest
(``GET /api/v1/me/navigation``), and the design tokens (every color,
spacing, and font reference). Feature surfaces -- the admin bundle,
the project dashboard, the run-detail page -- mount their views into
the shell's main area and may contribute command-palette providers
through the shell's in-browser registry.

Routes are either *shell* routes or *chromeless* routes:

- **Shell routes** (everything authenticated) are served via the
  shell HTML document. The page-specific custom element mounts
  into the ``<main>`` slot.
- **Chromeless routes** render their own minimal document without
  the shell bundle: ``/login``, ``/logout``, the setup wizard under
  ``/setup/*``, and (when ``PYCHESTRATE_EMBED_ENABLED`` is set; it is off
  by default because the feature is unfinished) signed embeddable views under
  ``/embed/*``. The
  prefixes ``/__health`` and ``/errors`` are reserved as chromeless
  too, but no pages are served there today; requests for them get the
  ordinary 404.

Error pages are not separate routes. ``site_shell/error_pages.py``
renders them in place, at the URL that failed: inside the shell for a
signed-in browser on a shell path, and as a standalone page for
everyone else.

Sidebar navigation
==================

The sidebar comes from one server-side list, the navigation manifest
in
``source/site/ccai/pychestrate/webservice/webinterface/site_shell/nav_manifest.py``.
It declares every group and entry with the permissions (and UI-profile
surfaces) each needs; ``GET /api/v1/me/navigation`` filters it for the
signed-in user, and the shell renders the result on every route. To add
a page to the sidebar, add its ``NavEntry`` there.

The in-browser registry behind the manifest is also reachable through
the ``window.pychestrateShell`` handle, for an entry that only one
bundle's page needs:

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
  registration wins, and the manifest registers first.

Adding a Palette Provider
=========================

The shell registers its own provider, ``shell.navigation``, which
matches the visible sidebar entries by label, group, and route. Bundles
can contribute more providers to the ``Ctrl/Cmd + K`` palette:

.. code-block:: javascript

    handle.palette.registerProvider({
        providerId: "admin.actions",
        label: "Admin actions",
        requiredPermissions: ["system:ui.admin.view"],
        timeoutMs: 1000,
        query: async (q) => {
            const actions = [
                { id: "admin.create-user", label: "Create user",
                  route: "/admin/users/create" },
                { id: "admin.enrollment-tokens", label: "Mint an enrollment token",
                  route: "/admin/enrollment-tokens" },
            ]
            const needle = q.trim().toLowerCase()
            return actions.filter((action) => action.label.toLowerCase().includes(needle))
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
times out renders an inline "this source is unavailable" notice
without blocking the others.

Chromeless Routes
=================

Chromeless route prefixes are listed in
``source/site/ccai/pychestrate/webservice/webinterface/site_shell/chromeless_routes.py``.
The shell's catch-all route never claims a path under them. Nothing
checks at startup that other blueprints stay out of them:
``validate_chromeless_routes_at_startup`` in the same module is not
called yet.

Mark a route chromeless only when it must NOT load the shell
bundle (sign-in, setup, embeddable views). Authenticated feature
pages are always shell routes.

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
- ``pyc-site-shell-home-rendered`` -- ``{}``.
- ``pyc-site-shell-not-found-rendered`` -- ``{path}``.
- ``pyc-site-shell-empty-state-rendered`` -- ``{}``.
- ``pyc-site-shell-palette-opened`` -- ``{}``.
- ``pyc-site-shell-palette-closed`` -- ``{}``.

Window-level events:

- ``pyc-session-401`` -- any page may dispatch this to surface
  the re-auth toast.
- ``pyc-permissions-fetch-failed`` -- emitted when the
  permission fetch falls through to the degraded banner.

Client metrics beaconed to ``POST /api/v1/_metrics/ui``:

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

The endpoint is informational: it validates the payload shape, logs a
one-line summary, and stores nothing. It accepts 12 batches per minute
per client address; the webworks request does not carry the client's
address today, so all clients currently share that one budget.
Aggregation into a Prometheus exposition is a separate concern.

Invariants
==========

The shell upholds two invariants, both enforced by
``source/testroots/ccai/tests/singlehost/pychestrate/webservice/phase13/test_p30d_shell_storage_and_color_invariants_m1.py``:

1. **Browser storage holds per-viewer preferences only.** The shell
   writes exactly two ``localStorage`` keys, both preferences of the
   person at that browser: ``pychestrate.ui.theme`` (``light`` or
   ``dark``, set by the header's Theme control) and
   ``pyc-site-shell.nav-collapsed`` (``true`` or ``false``, whether
   the sidebar is collapsed). Nothing else -- no session data, no
   permissions, no page content -- is written to ``localStorage``,
   ``sessionStorage``, or IndexedDB; the permissions cache and other
   session-scoped state live in memory and die with the tab. Every
   storage access is wrapped so a browser that refuses storage (some
   privacy modes) falls back to the defaults.

2. **No hard-coded colors.** ``pyc-site-shell.css`` defines every
   color and shadow through ``--pyc-site-shell-*`` tokens in its
   ``:root`` block; the rule blocks below it only reference tokens.
   The tokens fall back to local values when the design-token
   stylesheet is not loaded.

A change that needs another stored value adds its key to the test's
allowlist, with the reason, in the same change.

Testing Your Bundle Inside the Shell
====================================

Bundle tests are Playwright-driven and run against a live server --
there is no Node-based unit-test harness. The browser tests live in
``source/testroots/ccai/tests/singlehost/pychestrate/``
``webservice/phase11/test_p23a_mj_components_browser_m1.py``
(and any sibling ``test_p*_browser_*.py`` files for view-specific
coverage). They read ``PYCHESTRATE_TEST_BASE_URL`` and the
``PYCHESTRATE_TEST_ADMIN_*`` credentials; see ``CONTRIBUTING.md``. The
conventional pattern:

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
