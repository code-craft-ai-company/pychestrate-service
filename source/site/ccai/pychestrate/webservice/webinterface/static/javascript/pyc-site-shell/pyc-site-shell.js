import { build_empty_state } from "./chrome/empty-state.js";
import {
  build_flash_notice,
  extract_flash_messages
} from "./chrome/flash-notices.js";
import { build_header, update_theme_toggle } from "./chrome/header.js";
import { install_confirm_delegate } from "./chrome/confirm-delegate.js";
import { install_reveal_toggle } from "./chrome/reveal-toggle.js";
import { install_log_viewer } from "./chrome/log-viewer.js";
import { install_live_region } from "./chrome/live-region.js";
import { install_chip_tone } from "./chrome/chip-tone.js";
import { build_home_view } from "./chrome/home-view.js";
import { build_not_found_view } from "./chrome/not-found-view.js";
import { DegradedBanner } from "./chrome/degraded-banner.js";
import { SessionExpiredToast } from "./chrome/session-toast.js";
import {
  build_hidden_surface_notice,
  match_hidden_route,
} from "./chrome/hidden-surface-notice.js";
import { PaletteRegistry } from "./palette/palette-registry.js";
import { PaletteDialog } from "./palette/palette-dialog.js";
import {
  register_navigation_palette_provider
} from "./palette/navigation-provider.js";
import {
  DEFAULT_PERMISSIONS_ENDPOINT,
  PermissionCache
} from "./permissions/permission-cache.js";
import { ShellRouter } from "./routing/shell-router.js";
import { SidebarRegistry } from "./sidebar/sidebar-registry.js";
import { SidebarRenderer } from "./sidebar/sidebar-renderer.js";
import {
  DEFAULT_NAVIGATION_ENDPOINT,
  apply_nav_manifest,
  fetch_nav_manifest
} from "./sidebar/nav-manifest.js";
import {
  MetricsBeacon,
  SHELL_METRICS
} from "./observability/metrics-beacon.js";
const ATTR_INITIAL_ROUTE = "initial-route";
const ATTR_PERMISSIONS_ENDPOINT = "permissions-endpoint";
const ATTR_NAVIGATION_ENDPOINT = "navigation-endpoint";
const ATTR_PALETTE_TIMEOUT_MS = "palette-timeout-ms";
const ATTR_BRAND_LABEL = "brand-label";
const NAV_BANNER_MESSAGE = "Navigation could not be loaded. The sidebar may be incomplete.";
const NAV_COLLAPSED_STORAGE_KEY = "pyc-site-shell.nav-collapsed";
const SIDEBAR_ELEMENT_ID = "pyc-site-shell-sidebar";
const SIDEBAR_NAV_LABEL = "Primary";
const DARK_SCHEME_QUERY = "(prefers-color-scheme: dark)";
class PycSiteShell extends HTMLElement {
  _sidebar_registry;
  _palette_registry;
  _permission_cache;
  _router;
  _sidebar_renderer;
  _main_region;
  _sidebar_region;
  _notices_region;
  _palette_dialog;
  _degraded_banner;
  _nav_degraded_banner;
  _session_toast;
  _global_keydown;
  _global_session_401;
  _ready;
  _metrics;
  _metrics_lifecycle_detach;
  _boot_started_perf_now;
  _palette_open_keydown_perf_now;
  _navigation_endpoint;
  _nav_manifest_loaded;
  _nav_manifest_failed;
  _nav_provider_registered;
  _layout;
  _color_scheme_query;
  _color_scheme_listener;
  static observedAttributes = [
    ATTR_INITIAL_ROUTE,
    ATTR_PERMISSIONS_ENDPOINT,
    ATTR_NAVIGATION_ENDPOINT,
    ATTR_PALETTE_TIMEOUT_MS,
    "aria-label",
    ATTR_BRAND_LABEL
  ];
  constructor() {
    super();
    this._sidebar_registry = new SidebarRegistry();
    this._palette_registry = new PaletteRegistry();
    const endpoint = this.getAttribute(ATTR_PERMISSIONS_ENDPOINT);
    const resolved_endpoint = endpoint !== null && endpoint.length > 0 ? endpoint : DEFAULT_PERMISSIONS_ENDPOINT;
    this._permission_cache = new PermissionCache(resolved_endpoint);
    const nav_endpoint = this.getAttribute(ATTR_NAVIGATION_ENDPOINT);
    this._navigation_endpoint = nav_endpoint !== null && nav_endpoint.length > 0 ? nav_endpoint : DEFAULT_NAVIGATION_ENDPOINT;
    this._nav_manifest_loaded = false;
    this._nav_manifest_failed = false;
    this._nav_provider_registered = false;
    this._layout = null;
    this._color_scheme_query = null;
    this._color_scheme_listener = null;
    this._router = null;
    this._sidebar_renderer = null;
    this._main_region = null;
    this._sidebar_region = null;
    this._notices_region = null;
    this._palette_dialog = null;
    this._degraded_banner = null;
    this._nav_degraded_banner = null;
    this._session_toast = null;
    this._global_keydown = null;
    this._global_session_401 = null;
    this._ready = false;
    this._metrics = new MetricsBeacon();
    this._metrics_lifecycle_detach = null;
    this._boot_started_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
    this._palette_open_keydown_perf_now = null;
  }
  /**
   * Diagnostic accessor for tests + bench harness -- returns the
   * metrics beacon instance the shell uses. Not part of the
   * long-term public API.
   */
  get metrics() {
    const rtnval = this._metrics;
    return rtnval;
  }
  get sidebar() {
    const rtnval = this._sidebar_registry;
    return rtnval;
  }
  get palette() {
    const rtnval = this._palette_registry;
    return rtnval;
  }
  get permissions() {
    const rtnval = this._permission_cache;
    return rtnval;
  }
  connectedCallback() {
    // The shell document's head script (theme-boot.js) already set
    // data-theme before the first paint; re-applying the stored
    // choice here only matters when that script could not run.
    _apply_theme_preference(_read_stored_theme());
    this._wire_color_scheme_listener();
    this._install_skip_link();
    this._install_sortable_header_keys();
    install_confirm_delegate(document);
    install_reveal_toggle(document);
    install_log_viewer(document);
    install_live_region(document);
    install_chip_tone();
    this._boot_started_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
    this._metrics_lifecycle_detach = this._metrics.attachLifecycle();
    this._render_skeleton();
    this._wire_permission_listeners();
    this._wire_global_keydown();
    this._wire_global_session_401();
    this._install_fetch_session_watch();
    this._wire_window_registry();
    queueMicrotask(() => {
      this._boot().catch((reason) => {
        console.warn(
          "pychestrate.ui.shell.boot_failed",
          { reason: String(reason) }
        );
      });
    });
    return;
  }
  disconnectedCallback() {
    if (this._metrics_lifecycle_detach !== null) {
      this._metrics_lifecycle_detach();
      this._metrics_lifecycle_detach = null;
    }
    this._metrics.flush();
    if (this._global_keydown !== null) {
      window.removeEventListener("keydown", this._global_keydown);
      this._global_keydown = null;
    }
    if (this._global_session_401 !== null) {
      window.removeEventListener(
        "pyc-session-401",
        this._global_session_401
      );
      this._global_session_401 = null;
    }
    if (this._color_scheme_query !== null && this._color_scheme_listener !== null) {
      this._color_scheme_query.removeEventListener(
        "change",
        this._color_scheme_listener
      );
      this._color_scheme_query = null;
      this._color_scheme_listener = null;
    }
    return;
  }
  /**
   * Public hook -- open the command palette. Exposed so feature
   * bundles or tests can trigger the palette without simulating
   * a keystroke.
   */
  openPalette() {
    if (this._palette_open_keydown_perf_now === null) {
      this._palette_open_keydown_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
    }
    if (this._palette_dialog !== null) {
      this._palette_dialog.open();
    }
    return;
  }
  /**
   * Public hook -- close the command palette.
   */
  closePalette() {
    if (this._palette_dialog !== null) {
      this._palette_dialog.close();
    }
    return;
  }
  _render_skeleton() {
    const initial_route_attr = this.getAttribute(ATTR_INITIAL_ROUTE);
    const initial_path = initial_route_attr !== null && initial_route_attr.length > 0 ? initial_route_attr : window.location.pathname;
    // Capture any server-rendered content the Flask shell document
    // inlined inside <pyc-site-shell> (see
    // ``site_shell/templates/site_shell/shell_document.html``).
    // Without this, ``replaceChildren()`` below wipes the route's
    // fragment and the user sees their page flash and then
    // disappear once the shell mounts.
    const preserved_main_content = Array.from(this.childNodes).filter(
      (node) => {
        if (node.nodeType !== Node.ELEMENT_NODE) {
          return node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 0;
        }
        const element = node;
        // mj-app-shell layouts re-build themselves below; drop them.
        if (element.tagName === "MJ-APP-SHELL") {
          return false;
        }
        return true;
      }
    );
    this.replaceChildren();
    // The outer layout is <mj-app-shell>: it owns the CSS grid
    // ("app-bar", "nav", "main", "inspector", "status-bar"
    // regions), responsive behavior, and the dock/anchor
    // landmarks. Each region is a slotted child carrying the
    // matching slot name.
    const layout = document.createElement("mj-app-shell");
    layout.classList.add("pyc-site-shell__layout");
    // <mj-app-shell> collapses the nav track to width 0 unless the
    // host carries nav-open. nav-open states the wide-layout
    // choice: open unless the user previously collapsed it
    // (persisted in localStorage). Below the desktop breakpoint
    // (--mj-shell-breakpoint-nav in pyc-site-shell.css) the layout
    // measures itself, switches to nav-mode="overlay", and closes
    // the drawer before the first paint -- so phones and tablets
    // always start with the content visible and the drawer shut.
    // Deciding here from a viewport media query instead would
    // disagree with the layout's own width near the breakpoint.
    const nav_collapsed_preference = _read_nav_collapsed_preference();
    const nav_open_initial = nav_collapsed_preference === false;
    if (nav_open_initial === true) {
      layout.setAttribute("nav-open", "");
    }
    // Keep the header toggle's aria-expanded in step with the nav
    // however it changes: the toggle, the backdrop, Escape, or the
    // layout closing the drawer when it enters overlay mode.
    layout.addEventListener("mj-shell-nav-toggle", (event) => {
      if (event.target !== layout) {
        return;
      }
      const toggle_button = this.querySelector(".pyc-site-shell__nav-toggle");
      if (toggle_button !== null) {
        toggle_button.setAttribute(
          "aria-expanded",
          layout.hasAttribute("nav-open") === true ? "true" : "false"
        );
      }
    });
    this._layout = layout;
    const brand_attr = this.getAttribute(ATTR_BRAND_LABEL);
    const is_mac_platform = typeof navigator !== "undefined" && typeof navigator.platform === "string" && navigator.platform.toLowerCase().indexOf("mac") >= 0;
    const header = build_header({
      brand_label: brand_attr !== null && brand_attr.length > 0 ? brand_attr : "Pychestrate",
      user_display_name: this._read_optional_attribute("user-display-name"),
      user_login_name: this._read_optional_attribute("user-login-name"),
      csrf_token: this._read_optional_attribute("csrf-token"),
      service_version: this._read_optional_attribute("service-version"),
      user_guide_url: this._read_optional_attribute("user-guide-url"),
      on_theme_toggle: () => {
        this._toggle_theme();
      },
      current_theme: _read_effective_theme(),
      nav_open_initial,
      nav_controls_id: SIDEBAR_ELEMENT_ID,
      on_nav_toggle: () => {
        this._toggle_sidebar();
      },
      palette_shortcut_label: is_mac_platform === true ? "⌘K" : "Ctrl+K",
      on_palette_hint_activate: () => {
        this.openPalette();
      }
    });
    layout.appendChild(header);
    // <mj-side-nav> renders the page's one navigation landmark
    // (<mj-app-shell> then leaves its nav region unlabelled);
    // name it here so it is not announced by a catalog key.
    const sidebar = document.createElement("mj-side-nav");
    sidebar.setAttribute("slot", "nav");
    sidebar.setAttribute("nav-label", SIDEBAR_NAV_LABEL);
    sidebar.id = SIDEBAR_ELEMENT_ID;
    sidebar.classList.add("pyc-site-shell__sidebar");
    layout.appendChild(sidebar);
    this._sidebar_region = sidebar;
    // Lift pending server-rendered flash messages out of the
    // preserved fragment BEFORE any feature bundle can mount:
    // bundles replace the main region's children wholesale, which
    // would destroy the flashes unread. The lifted notices live in
    // a shell-owned region slotted beside <main> (same "main" grid
    // area, stacked above it) that bundle replaceChildren calls
    // never touch. Because the originals are moved out of the
    // fragment, legacy pages whose fragment stays mounted cannot
    // render the same flash twice.
    const flash_extraction = extract_flash_messages(preserved_main_content);
    const notices = document.createElement("div");
    notices.setAttribute("slot", "main");
    notices.classList.add("pyc-site-shell__notices");
    for (const flash of flash_extraction.flashes) {
      const notice = build_flash_notice(flash);
      notices.appendChild(notice);
    }
    layout.appendChild(notices);
    this._notices_region = notices;
    const main = document.createElement("main");
    main.setAttribute("slot", "main");
    main.classList.add("pyc-site-shell__main");
    // The target of the "Skip to main content" link exists from the start
    // and can take focus, so the link works from a URL fragment and for a
    // checker as well as through the click handler below (WCAG 2.4.1).
    main.id = "pyc-main-content";
    main.setAttribute("tabindex", "-1");
    // Re-attach the server-rendered fragment captured above (minus
    // the lifted flashes) so the route's page survives the
    // skeleton rebuild.
    for (const node of flash_extraction.remaining_nodes) {
      main.appendChild(node);
    }
    layout.appendChild(main);
    this._main_region = main;
    this.appendChild(layout);
    this._degraded_banner = new DegradedBanner(main);
    this._nav_degraded_banner = new DegradedBanner(
      main,
      {
        message: NAV_BANNER_MESSAGE,
        action_label: "Retry",
        on_action: () => {
          void this._retry_nav_manifest();
        }
      }
    );
    this._session_toast = new SessionExpiredToast(main);
    this._palette_dialog = new PaletteDialog(
      this._palette_registry,
      {
        getPermissions: () => this._permission_cache.current(),
        navigate: (route) => {
          // The pychestrate site is server-rendered: navigating
          // means a full page load, exactly like the sidebar's
          // <a href> entries. The router keeps no pushState path.
          window.location.assign(route);
        },
        emit: (event_name, detail) => {
          this._emit(event_name, detail);
        },
        observePaletteOpened: () => {
          if (this._palette_open_keydown_perf_now !== null) {
            const now_value = typeof performance !== "undefined" ? performance.now() : 0;
            const seconds = (now_value - this._palette_open_keydown_perf_now) / 1e3;
            this._palette_open_keydown_perf_now = null;
            this._metrics.observeHistogram(
              SHELL_METRICS.PALETTE_OPEN,
              seconds
            );
          }
        },
        observePaletteFanout: (seconds) => {
          this._metrics.observeHistogram(
            SHELL_METRICS.PALETTE_FANOUT,
            seconds
          );
        }
      }
    );
    this._router = new ShellRouter(initial_path);
    if (this._nav_provider_registered === false) {
      // The shell's own palette provider -- registered for every
      // user so the palette can always resolve navigation queries
      // even when no feature bundle contributes a provider.
      register_navigation_palette_provider(
        this._palette_registry,
        {
          get_visible_sidebar: () => this._sidebar_registry.visible(
            this._permission_cache.current()
          )
        }
      );
      this._nav_provider_registered = true;
    }
    this._sidebar_renderer = new SidebarRenderer(
      sidebar,
      (entry_route, entry_label) => {
        this._emit(
          "pyc-site-shell-sidebar-clicked",
          {
            entryRoute: entry_route,
            entryLabel: entry_label
          }
        );
        this._metrics.incrementCounter(
          SHELL_METRICS.SIDEBAR_ENTRY_CLICKED,
          { entry_route }
        );
      }
    );
    this._router.onNavigate(async (next_ctx, prev_ctx) => {
      const refetch_started = typeof performance !== "undefined" ? performance.now() : 0;
      await this._permission_cache.refresh(true);
      const refetch_finished = typeof performance !== "undefined" ? performance.now() : 0;
      this._metrics.observeHistogram(
        SHELL_METRICS.PERMISSION_REFETCH,
        (refetch_finished - refetch_started) / 1e3
      );
      this._render_sidebar_and_empty_state();
      this._emit(
        "pyc-site-shell-navigated",
        {
          from: prev_ctx !== null ? prev_ctx.path : null,
          to: next_ctx.path
        }
      );
    });
    return;
  }
  _wire_permission_listeners() {
    this._permission_cache.onPermissionsChanged((diff) => {
      this._emit(
        "pyc-site-shell-permissions-changed",
        { added: diff.added, removed: diff.removed }
      );
      this._render_sidebar_and_empty_state();
    });
    this._permission_cache.onFetchFailed(() => {
      if (this._degraded_banner !== null) {
        this._degraded_banner.show();
      }
      this._emit_window_event(
        "pyc-permissions-fetch-failed",
        {}
      );
    });
    this._permission_cache.onFetchSucceeded(() => {
      if (this._degraded_banner !== null) {
        this._degraded_banner.hide();
      }
    });
    this._permission_cache.onSession401(() => {
      this._emit_window_event("pyc-session-401", {});
    });
    return;
  }
  _wire_global_keydown() {
    const handler = (event) => {
      if (event.defaultPrevented === true) {
        return;
      }
      const is_palette_combo = (event.ctrlKey === true || event.metaKey === true) && event.key.toLowerCase() === "k";
      if (is_palette_combo === true) {
        event.preventDefault();
        this._palette_open_keydown_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
        this.openPalette();
      }
    };
    window.addEventListener("keydown", handler);
    this._global_keydown = handler;
    return;
  }
  /**
   * Every bundle view calls the REST API with fetch, and only some of them
   * turned a 401 into the shell's "session expired" notice; creating a
   * secret after the session ended said "Failed to create the secret. Try
   * again." (XC-12). One wrapper on fetch, installed once by the shell,
   * announces `pyc-session-401` whenever a request to this site's own /api/
   * is refused with 401, whichever view made it, and hands the response back
   * unchanged so the view still shows its own message as well.
   */
  _install_fetch_session_watch() {
    if (typeof window.fetch !== "function" || window.fetch.__pycSessionWatch === true) {
      return;
    }
    const original = window.fetch.bind(window);
    const watched = async (input, init) => {
      const response = await original(input, init);
      if (response.status === 401) {
        try {
          const target = new URL(typeof input === "string" ? input : input.url, window.location.href);
          if (target.origin === window.location.origin && target.pathname.startsWith("/api/") === true) {
            window.dispatchEvent(new CustomEvent("pyc-session-401", { bubbles: false, detail: {} }));
          }
        } catch (error) {
          // A request whose address cannot be read is not announced.
        }
      }
      return response;
    };
    watched.__pycSessionWatch = true;
    window.fetch = watched;
    return;
  }
  _wire_global_session_401() {
    const handler = () => {
      if (this._session_toast !== null) {
        this._session_toast.show();
      }
    };
    window.addEventListener("pyc-session-401", handler);
    this._global_session_401 = handler;
    return;
  }
  _wire_window_registry() {
    const global_target = window;
    const handle = {
      sidebar: this._sidebar_registry,
      palette: this._palette_registry,
      element: this
    };
    global_target.pychestrateShell = handle;
    this._sidebar_registry.onChange(() => {
      this._render_sidebar_and_empty_state();
    });
    return;
  }
  /**
   * Fetch the central navigation manifest and seed the sidebar
   * registry from it. The manifest is the authoritative source
   * of truth for sidebar navigation -- it carries every group /
   * entry the calling session may see, independent of which
   * feature bundle happens to be loaded for the current route.
   *
   * Seeding the manifest is what makes the sidebar complete on
   * the bare ``/`` route (which loads no feature bundle at
   * all). Idempotent -- a second call is a no-op once the
   * manifest has been applied, so the Retry control can call it
   * again freely. A fetch failure is non-fatal but no longer
   * silent: the shell shows the navigation degraded banner (with
   * a Retry action) and ``_render_sidebar_and_empty_state``
   * paints an explanatory state into the sidebar region while
   * the registry has nothing to show.
   */
  async _load_nav_manifest() {
    if (this._nav_manifest_loaded === true) {
      return;
    }
    const result = await fetch_nav_manifest(this._navigation_endpoint);
    if (result.ok === true && result.manifest !== null) {
      apply_nav_manifest(this._sidebar_registry, result.manifest);
      this._show_hidden_surface_notice(result.manifest.ui_profile);
      this._nav_manifest_loaded = true;
      this._nav_manifest_failed = false;
      if (this._nav_degraded_banner !== null) {
        this._nav_degraded_banner.hide();
      }
    } else {
      this._nav_manifest_failed = true;
      if (this._nav_degraded_banner !== null) {
        this._nav_degraded_banner.show();
      }
    }
    return;
  }
  /**
   * Retry handler for the navigation degraded banner and the
   * sidebar failure state. Refetches the manifest; on success
   * re-renders the sidebar, updates the document title, and
   * paints the home / not-found landing state the failed boot
   * could not produce.
   */
  /**
   * 9-ui-profiles: when the current location belongs to a surface the
   * caller has hidden, show a dismissible notice pointing at the
   * preferences page. Idempotent per page load.
   */
  _show_hidden_surface_notice(ui_profile) {
    if (ui_profile === null || ui_profile === undefined) {
      return;
    }
    if (this._notices_region === null || this._notices_region === undefined) {
      return;
    }
    if (this._notices_region.querySelector(".pyc-hidden-surface-notice") !== null) {
      return;
    }
    const pathname = window.location.pathname;
    const route = match_hidden_route(pathname, ui_profile.hidden_routes);
    if (route === null) {
      return;
    }
    this._notices_region.appendChild(build_hidden_surface_notice(route));
    return;
  }
  async _retry_nav_manifest() {
    await this._load_nav_manifest();
    this._render_sidebar_and_empty_state();
    if (this._nav_manifest_loaded === true) {
      this._update_document_title();
      this._schedule_landing_state_check();
    }
    return;
  }
  async _boot() {
    await Promise.all([
      this._permission_cache.refresh(true),
      this._load_nav_manifest()
    ]);
    this._render_sidebar_and_empty_state();
    this._update_document_title();
    this._ready = true;
    const ready_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
    const tti_seconds = (ready_perf_now - this._boot_started_perf_now) / 1e3;
    this._metrics.observeHistogram(SHELL_METRICS.TTI, tti_seconds);
    this._metrics.flush();
    this._emit(
      "pyc-site-shell-ready",
      {
        visibleEntryCount: this._sidebar_registry.visibleEntryCount(
          this._permission_cache.current()
        ),
        degraded: this._permission_cache.degraded
      }
    );
    // Feature bundles waiting on the ready event mount into the
    // main region synchronously during the _emit above, so the
    // scheduled check below observes the final claim state.
    this._schedule_landing_state_check();
    return;
  }
  /**
   * Schedule the home / not-found decision for the next frame.
   * Bundles mount synchronously (at module load or during the
   * ready-event dispatch), so by the time the frame callback
   * runs, an empty main region deterministically means no bundle
   * claimed the route.
   */
  _schedule_landing_state_check() {
    const schedule = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (callback) => setTimeout(callback, 0);
    schedule(() => {
      this._apply_landing_state();
    });
    return;
  }
  /**
   * Render the shell-owned landing state for routes no feature
   * bundle (and no server-rendered fragment) claimed: the home
   * view on the bare "/" route, the "Page not found" view on any
   * other unclaimed route. Never fires while the nav manifest is
   * unloaded (the degraded path owns that messaging), never
   * clobbers a mounted bundle, and leaves the no-access empty
   * state in place for zero-permission accounts. Pages served by
   * the legacy blueprints either inline a fragment (preserved
   * into the main region) or never load the shell document at
   * all, so neither can trip this.
   */
  _apply_landing_state() {
    if (this._main_region === null) {
      return;
    }
    if (this._nav_manifest_loaded === false) {
      return;
    }
    const perms = this._permission_cache.current();
    const visible_entry_count = this._sidebar_registry.visibleEntryCount(
      perms
    );
    if (visible_entry_count === 0) {
      return;
    }
    const previous_landing = this._main_region.querySelectorAll(
      ".pyc-site-shell__home, .pyc-site-shell__not-found"
    );
    if (_main_region_has_route_content(this._main_region) === true) {
      for (const stale of Array.from(previous_landing)) {
        stale.remove();
      }
      return;
    }
    for (const stale of Array.from(previous_landing)) {
      stale.remove();
    }
    const path = this._router !== null ? this._router.current().path : window.location.pathname;
    const brand_attr = this.getAttribute(ATTR_BRAND_LABEL);
    const brand_label = brand_attr !== null && brand_attr.length > 0 ? brand_attr : "Pychestrate";
    const visible_sidebar = this._sidebar_registry.visible(perms);
    if (path === "/") {
      const home_view = build_home_view({
        brand_label,
        visible_sidebar
      });
      this._main_region.appendChild(home_view);
      this._emit("pyc-site-shell-home-rendered", {});
    } else {
      const not_found_view = build_not_found_view({
        path,
        visible_sidebar
      });
      this._main_region.appendChild(not_found_view);
      // A longest-prefix nav match (e.g. "/admin" for
      // "/admin/unknown") would have claimed the tab title even
      // though no page rendered; name the actual state instead.
      document.title = "Page not found · " + brand_label;
      this._emit(
        "pyc-site-shell-not-found-rendered",
        { path }
      );
    }
    return;
  }
  /**
   * Reflect the active navigation entry into the browser tab
   * title as "<entry label> · <brand>", picked by longest route
   * prefix so "/admin/feature-flags" wins over "/admin". When no
   * entry matches, the server-rendered title is left untouched.
   */
  _update_document_title() {
    // A server-rendered page already carries a specific <title>
    // ("Users · Pychestrate", "Project · Pychestrate"); only fill in
    // the title when the document still has the bare brand label.
    const current_brand = this.getAttribute(ATTR_BRAND_LABEL);
    const brand_only = current_brand !== null && current_brand.length > 0 ? current_brand : "Pychestrate";
    if (typeof document.title === "string" && document.title.length > 0 && document.title !== brand_only) {
      return;
    }
    if (this._nav_manifest_loaded === false) {
      return;
    }
    const path = this._router !== null ? this._router.current().path : window.location.pathname;
    const perms = this._permission_cache.current();
    const visible_sidebar = this._sidebar_registry.visible(perms);
    const all_entries = [];
    for (const entry of visible_sidebar.ungrouped) {
      all_entries.push(entry);
    }
    for (const bucket of visible_sidebar.groups) {
      for (const entry of bucket.entries) {
        all_entries.push(entry);
      }
    }
    let best_entry = null;
    for (const entry of all_entries) {
      const route = entry.route;
      const is_match = path === route || path.startsWith(route.endsWith("/") === true ? route : route + "/") === true;
      if (is_match === false) {
        continue;
      }
      if (best_entry === null || route.length > best_entry.route.length) {
        best_entry = entry;
      }
    }
    if (best_entry === null) {
      return;
    }
    const brand_attr = this.getAttribute(ATTR_BRAND_LABEL);
    const brand_label = brand_attr !== null && brand_attr.length > 0 ? brand_attr : "Pychestrate";
    document.title = best_entry.label + " · " + brand_label;
    return;
  }
  /**
   * Toggle the sidebar nav track open / collapsed and persist
   * the choice. <mj-app-shell> owns the actual collapse (the
   * nav-open attribute drives its grid track width and its
   * overlay behavior on narrow viewports).
   */
  /**
   * The vendored <mj-data-table> sorts a column only when its header cell is
   * clicked: its keyboard handling covers the arrows, Home, End and Escape,
   * so Enter and Space on a focused header did nothing and a keyboard user
   * could not sort (ORC-24). One document-level handler gives every table in
   * every bundle the standard behaviour: Enter or Space on a focused
   * sortable header cell does what a click does. It looks through the
   * table's shadow root with the event's composed path.
   */
  _install_sortable_header_keys() {
    if (document.documentElement.hasAttribute("data-pyc-sort-keys") === true) {
      return;
    }
    document.documentElement.setAttribute("data-pyc-sort-keys", "");
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      for (const node of path) {
        if (node instanceof HTMLElement && node.classList.contains("header-cell") === true) {
          if (node.getAttribute("data-sortable") === "true") {
            event.preventDefault();
            node.click();
          }
          return;
        }
      }
    });
    return;
  }
  _install_skip_link() {
    if (document.querySelector(".pyc-site-shell__skip-link") !== null) {
      return;
    }
    const link = document.createElement("a");
    link.href = "#pyc-main-content";
    link.classList.add("pyc-site-shell__skip-link");
    link.textContent = "Skip to main content";
    link.addEventListener("click", (event) => {
      const main = document.querySelector(".pyc-site-shell__main");
      if (main === null) {
        return;
      }
      event.preventDefault();
      if (main.id.length === 0) {
        main.id = "pyc-main-content";
      }
      main.setAttribute("tabindex", "-1");
      main.focus();
    });
    document.body.insertBefore(link, document.body.firstChild);
    return;
  }
  /**
   * Flip between the light and dark theme, starting from what is
   * on screen now -- the stored choice, or the OS preference when
   * nothing is stored -- so the first click after an OS-driven
   * load always changes the theme.
   */
  _toggle_theme() {
    const current = _read_effective_theme();
    const next = current === "dark" ? "light" : "dark";
    _apply_theme_preference(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch (error) {
      // storage unavailable: the choice lasts for this page only
    }
    this._sync_theme_control();
    return;
  }
  _sync_theme_control() {
    const button = this.querySelector(".pyc-site-shell__theme-toggle");
    if (button !== null) {
      update_theme_toggle(button, _read_effective_theme());
    }
    return;
  }
  /**
   * While no theme is stored the page follows the OS preference;
   * keep the theme control's label right when the OS flips.
   */
  _wire_color_scheme_listener() {
    if (this._color_scheme_listener !== null || typeof window.matchMedia !== "function") {
      return;
    }
    const query = window.matchMedia(DARK_SCHEME_QUERY);
    if (typeof query.addEventListener !== "function") {
      return;
    }
    const listener = () => {
      this._sync_theme_control();
    };
    query.addEventListener("change", listener);
    this._color_scheme_query = query;
    this._color_scheme_listener = listener;
    return;
  }
  _read_optional_attribute(name) {
    const value = this.getAttribute(name);
    if (value === null || value.length === 0) {
      return null;
    }
    return value;
  }
  _toggle_sidebar() {
    const layout = this._layout;
    if (layout === null) {
      return;
    }
    const next_open = layout.hasAttribute("nav-open") === false;
    // Only the wide layout's sidebar state is a preference worth
    // remembering; opening and closing the overlay drawer on a
    // phone must not collapse the sidebar on the desktop.
    const is_overlay = layout.getAttribute("nav-mode") === "overlay";
    if (next_open === true) {
      layout.setAttribute("nav-open", "");
    } else {
      layout.removeAttribute("nav-open");
    }
    if (is_overlay === false) {
      _write_nav_collapsed_preference(next_open === false);
    }
    const toggle_button = this.querySelector(
      ".pyc-site-shell__nav-toggle"
    );
    if (toggle_button !== null) {
      toggle_button.setAttribute(
        "aria-expanded",
        layout.hasAttribute("nav-open") === true ? "true" : "false"
      );
    }
    return;
  }
  _render_sidebar_and_empty_state() {
    const perms = this._permission_cache.current();
    const active_path = this._router !== null ? this._router.current().path : window.location.pathname;
    const render_started = typeof performance !== "undefined" ? performance.now() : 0;
    if (this._sidebar_renderer !== null && this._sidebar_region !== null) {
      this._sidebar_renderer.render(
        this._sidebar_registry,
        perms,
        active_path
      );
    }
    // When the navigation manifest could not be fetched and the
    // registry holds nothing to show, the sidebar region would
    // render as silent blank chrome. Paint an explanatory state
    // with a retry control instead. render() above wipes the
    // container each pass, so this re-appends every render while
    // the failure persists and disappears once a retry succeeds.
    if (this._nav_manifest_failed === true && this._nav_manifest_loaded === false && this._sidebar_region !== null && this._sidebar_registry.visibleEntryCount(perms) === 0) {
      const failure_state = _build_sidebar_failure_state(() => {
        void this._retry_nav_manifest();
      });
      this._sidebar_region.appendChild(failure_state);
    }
    const render_finished = typeof performance !== "undefined" ? performance.now() : 0;
    this._metrics.observeHistogram(
      SHELL_METRICS.SIDEBAR_RENDER,
      (render_finished - render_started) / 1e3
    );
    const visible_entry_count = this._sidebar_registry.visibleEntryCount(
      perms
    );
    // Permissions AND the navigation manifest must have been
    // loaded at least once before we can claim "no access".
    // Without both gates, a fast perms fetch that resolves before
    // the slower manifest fetch leaves the sidebar registry empty
    // even for an admin -- triggering the empty-state branch and
    // wiping any feature bundle (pyc-runs-list, pyc-secrets-list,
    // etc.) that already mounted into main_region during boot.
    const perms_loaded = this._permission_cache !== null
      && this._permission_cache._last_success_at_ms !== null;
    const manifest_loaded = this._nav_manifest_loaded === true;
    if (this._main_region === null) {
      return;
    }
    const existing_empty_state = this._main_region.querySelector(
      ".pyc-site-shell__empty-state"
    );
    if (visible_entry_count === 0 && perms_loaded === true && manifest_loaded === true) {
      const preserved = [];
      for (const child of Array.from(this._main_region.children)) {
        if (child.classList.contains(
          "pyc-site-shell__degraded-banner"
        ) === true || child.classList.contains(
          "pyc-site-shell__session-toast"
        ) === true) {
          preserved.push(child);
        }
      }
      this._main_region.replaceChildren(...preserved, build_empty_state());
      this._emit(
        "pyc-site-shell-empty-state-rendered",
        {}
      );
    } else if (existing_empty_state !== null) {
      // The user gained access (or perms finally loaded) after a
      // prior empty-state render; remove the stale panel so the
      // router can paint real route content.
      existing_empty_state.remove();
    }
    return;
  }
  _emit(event_name, detail) {
    this.dispatchEvent(
      new CustomEvent(event_name, {
        bubbles: true,
        composed: true,
        detail
      })
    );
    return;
  }
  _emit_window_event(event_name, detail) {
    window.dispatchEvent(
      new CustomEvent(event_name, {
        bubbles: false,
        detail
      })
    );
    return;
  }
  get isReady() {
    const rtnval = this._ready;
    return rtnval;
  }
  /**
   * Test/diagnostic helper -- returns the current permission set.
   * Not part of the long-term public API surface (which goes
   * through DOM CustomEvents).
   */
  currentPermissions() {
    const rtnval = this._permission_cache.current();
    return rtnval;
  }
}
/*
 * Shell-owned chrome elements the landing-state check must not
 * count as route content when deciding whether a bundle claimed
 * the main region.
 */
const SHELL_CHROME_CLASSES = [
  "pyc-site-shell__degraded-banner",
  "pyc-site-shell__session-toast",
  "pyc-site-shell__empty-state",
  "pyc-site-shell__home",
  "pyc-site-shell__not-found"
];
function _main_region_has_route_content(main_region) {
  for (const node of Array.from(main_region.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (node.textContent.trim().length > 0) {
        return true;
      }
      continue;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      continue;
    }
    const element = node;
    let is_shell_chrome = false;
    for (const chrome_class of SHELL_CHROME_CLASSES) {
      if (element.classList.contains(chrome_class) === true) {
        is_shell_chrome = true;
        break;
      }
    }
    if (is_shell_chrome === false) {
      return true;
    }
  }
  return false;
}
/*
 * Explanatory sidebar state for a failed navigation-manifest
 * fetch. Message plus a retry control -- shown instead of a
 * silently empty nav region.
 */
function _build_sidebar_failure_state(on_retry) {
  const panel = document.createElement("div");
  panel.classList.add("pyc-site-shell__sidebar-failure");
  panel.setAttribute("role", "status");
  const message = document.createElement("p");
  message.classList.add("pyc-site-shell__sidebar-failure-message");
  message.textContent = "Navigation could not be loaded.";
  panel.appendChild(message);
  const retry_button = document.createElement("mj-button");
  retry_button.setAttribute("type", "button");
  retry_button.setAttribute("variant", "secondary");
  retry_button.setAttribute("size", "sm");
  retry_button.classList.add("pyc-site-shell__sidebar-failure-retry");
  retry_button.textContent = "Retry";
  retry_button.addEventListener("click", () => {
    on_retry();
  });
  panel.appendChild(retry_button);
  return panel;
}
/*
 * Theme preference. The explicit choice lives in localStorage
 * under THEME_STORAGE_KEY (the shell document's theme-boot.js
 * reads the same key before the first paint); with no stored
 * choice the page follows the OS preference. localStorage access
 * is wrapped in try/catch because it throws in some privacy
 * modes.
 */
const THEME_STORAGE_KEY = "pychestrate.ui.theme";

/*
 * The explicitly chosen theme ("dark" / "light"), or null when
 * the user has not chosen one.
 */
function _read_stored_theme() {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "dark" || stored === "light") {
      return stored;
    }
  } catch (error) {
    // no storage
  }
  return null;
}

/*
 * The theme on screen: the stored choice, else the OS preference.
 */
function _read_effective_theme() {
  const stored = _read_stored_theme();
  if (stored !== null) {
    return stored;
  }
  if (typeof window.matchMedia === "function" && window.matchMedia(DARK_SCHEME_QUERY).matches) {
    return "dark";
  }
  return "light";
}

/*
 * Apply a theme to the document: "dark" / "light" pin data-theme;
 * null removes it so the tokens follow the OS preference.
 */
function _apply_theme_preference(theme) {
  if (theme === "dark" || theme === "light") {
    document.documentElement.setAttribute("data-theme", theme);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  return;
}

/*
 * Sidebar collapse preference. Wrapped in try/catch because
 * localStorage access throws in some privacy modes; the shell
 * just falls back to the default (open) in that case.
 */
function _read_nav_collapsed_preference() {
  let rtnval = false;
  try {
    const stored = window.localStorage.getItem(
      NAV_COLLAPSED_STORAGE_KEY
    );
    rtnval = stored === "true";
  } catch (reason) {
    rtnval = false;
  }
  return rtnval;
}
function _write_nav_collapsed_preference(collapsed) {
  try {
    window.localStorage.setItem(
      NAV_COLLAPSED_STORAGE_KEY,
      collapsed === true ? "true" : "false"
    );
  } catch (reason) {
    // Preference persistence is best-effort only.
  }
  return;
}
export {
  PycSiteShell
};
