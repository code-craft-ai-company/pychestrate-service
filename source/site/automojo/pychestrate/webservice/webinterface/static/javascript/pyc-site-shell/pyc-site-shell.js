import { build_empty_state } from "./chrome/empty-state.js";
import { build_header } from "./chrome/header.js";
import { DegradedBanner } from "./chrome/degraded-banner.js";
import { SessionExpiredToast } from "./chrome/session-toast.js";
import { PaletteRegistry } from "./palette/palette-registry.js";
import { PaletteDialog } from "./palette/palette-dialog.js";
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
class PycSiteShell extends HTMLElement {
  _sidebar_registry;
  _palette_registry;
  _permission_cache;
  _router;
  _sidebar_renderer;
  _main_region;
  _sidebar_region;
  _palette_dialog;
  _degraded_banner;
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
    this._router = null;
    this._sidebar_renderer = null;
    this._main_region = null;
    this._sidebar_region = null;
    this._palette_dialog = null;
    this._degraded_banner = null;
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
    this._boot_started_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
    this._metrics_lifecycle_detach = this._metrics.attachLifecycle();
    this._render_skeleton();
    this._wire_permission_listeners();
    this._wire_global_keydown();
    this._wire_global_session_401();
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
    this.replaceChildren();
    // The outer layout is <mj-app-shell>: it owns the CSS grid
    // ("app-bar", "nav", "main", "inspector", "status-bar"
    // regions), responsive behavior, and the dock/anchor
    // landmarks. Each region is a slotted child carrying the
    // matching slot name.
    const layout = document.createElement("mj-app-shell");
    layout.classList.add("pyc-site-shell__layout");
    // <mj-app-shell> collapses the nav track to width 0 unless the
    // host carries nav-open. Without this attribute the sidebar
    // groups render into a 0-width column and disappear visually.
    layout.setAttribute("nav-open", "");
    const brand_attr = this.getAttribute(ATTR_BRAND_LABEL);
    const header = build_header({
      brand_label: brand_attr !== null && brand_attr.length > 0 ? brand_attr : "Pychestrate",
      user_display_name: null
    });
    layout.appendChild(header);
    const sidebar = document.createElement("mj-side-nav");
    sidebar.setAttribute("slot", "nav");
    sidebar.classList.add("pyc-site-shell__sidebar");
    layout.appendChild(sidebar);
    this._sidebar_region = sidebar;
    const main = document.createElement("main");
    main.setAttribute("slot", "main");
    main.setAttribute("role", "main");
    main.classList.add("pyc-site-shell__main");
    layout.appendChild(main);
    this._main_region = main;
    this.appendChild(layout);
    this._degraded_banner = new DegradedBanner(main);
    this._session_toast = new SessionExpiredToast(main);
    this._palette_dialog = new PaletteDialog(
      this._palette_registry,
      {
        getPermissions: () => this._permission_cache.current(),
        navigate: (route) => {
          if (this._router !== null) {
            void this._router.navigateTo(route);
          }
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
    this._router = new ShellRouter(initial_path, () => this._main_region);
    this._sidebar_renderer = new SidebarRenderer(
      sidebar,
      (route) => {
        void this._router?.navigateTo(route);
      },
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
   * manifest has been applied. A fetch failure is non-fatal:
   * the shell keeps whatever the registry already holds (the
   * legacy per-bundle ``registerEntry`` calls still run for the
   * current route's bundle) and the degraded path surfaces via
   * the permissions cache.
   */
  async _load_nav_manifest() {
    if (this._nav_manifest_loaded === true) {
      return;
    }
    const result = await fetch_nav_manifest(this._navigation_endpoint);
    if (result.ok === true && result.manifest !== null) {
      apply_nav_manifest(this._sidebar_registry, result.manifest);
      this._nav_manifest_loaded = true;
    }
    return;
  }
  async _boot() {
    await Promise.all([
      this._permission_cache.refresh(true),
      this._load_nav_manifest()
    ]);
    this._render_sidebar_and_empty_state();
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
    const render_finished = typeof performance !== "undefined" ? performance.now() : 0;
    this._metrics.observeHistogram(
      SHELL_METRICS.SIDEBAR_RENDER,
      (render_finished - render_started) / 1e3
    );
    const visible_entry_count = this._sidebar_registry.visibleEntryCount(
      perms
    );
    if (visible_entry_count === 0 && this._main_region !== null) {
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
export {
  PycSiteShell
};
