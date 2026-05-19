// src/pyc-site-shell/chrome/empty-state.ts
function build_empty_state() {
  const panel = document.createElement("section");
  panel.classList.add("pyc-site-shell__empty-state");
  panel.setAttribute("role", "status");
  const heading = document.createElement("h1");
  heading.classList.add("pyc-site-shell__empty-state-heading");
  heading.textContent = "Your account has no access yet";
  panel.appendChild(heading);
  const body = document.createElement("p");
  body.classList.add("pyc-site-shell__empty-state-body");
  body.textContent = "Ask an administrator to grant you a role so you can use Pychestrate.";
  panel.appendChild(body);
  return panel;
}

// src/pyc-site-shell/chrome/header.ts
var LOGOUT_PATH = "/logout";
function build_header(options) {
  const header = document.createElement("header");
  header.setAttribute("role", "banner");
  header.classList.add("pyc-site-shell__header");
  const brand = document.createElement("div");
  brand.classList.add("pyc-site-shell__brand");
  brand.textContent = options.brand_label;
  header.appendChild(brand);
  const spacer = document.createElement("div");
  spacer.classList.add("pyc-site-shell__header-spacer");
  header.appendChild(spacer);
  const user_menu = document.createElement("div");
  user_menu.setAttribute("role", "menu");
  user_menu.classList.add("pyc-site-shell__user-menu");
  const display_name = options.user_display_name !== null ? options.user_display_name : "Account";
  const name_label = document.createElement("span");
  name_label.classList.add("pyc-site-shell__user-menu-name");
  name_label.textContent = display_name;
  user_menu.appendChild(name_label);
  const logout_form = document.createElement("form");
  logout_form.method = "POST";
  logout_form.action = LOGOUT_PATH;
  logout_form.classList.add("pyc-site-shell__logout-form");
  const logout_button = document.createElement("button");
  logout_button.type = "submit";
  logout_button.setAttribute("role", "menuitem");
  logout_button.classList.add("pyc-site-shell__logout-button");
  logout_button.textContent = "Sign out";
  logout_form.appendChild(logout_button);
  user_menu.appendChild(logout_form);
  header.appendChild(user_menu);
  return header;
}

// src/pyc-site-shell/permissions/permission-set.ts
var PermissionSet = class {
  _keys;
  /**
   * Construct a permission set from an iterable of permission
   * keys. Duplicates are de-duplicated by the underlying Set.
   *
   * @param keys - Iterable of permission key strings.
   */
  constructor(keys) {
    this._keys = /* @__PURE__ */ new Set();
    for (const key of keys) {
      if (typeof key === "string" && key.length > 0) {
        this._keys.add(key);
      }
    }
  }
  /**
   * Return true when the supplied permission key is present.
   *
   * @param perm - Permission key.
   */
  has(perm) {
    const rtnval = this._keys.has(perm);
    return rtnval;
  }
  /**
   * Return true when every supplied permission key is present.
   * The empty-array case returns true (vacuously satisfied).
   *
   * @param perms - Iterable of permission keys.
   */
  hasAll(perms) {
    for (const perm of perms) {
      if (this._keys.has(perm) === false) {
        return false;
      }
    }
    return true;
  }
  /**
   * Return the diff between this set and another.
   *
   * @param other - Comparison set.
   * @returns Object with `added` (keys in other but not this)
   *          and `removed` (keys in this but not other) string
   *          arrays. Both arrays are sorted for determinism.
   */
  diff(other) {
    const added = [];
    const removed = [];
    for (const key of other._keys) {
      if (this._keys.has(key) === false) {
        added.push(key);
      }
    }
    for (const key of this._keys) {
      if (other._keys.has(key) === false) {
        removed.push(key);
      }
    }
    added.sort();
    removed.sort();
    const rtnval = { added, removed };
    return rtnval;
  }
  /**
   * Return the cardinality of the underlying key set.
   */
  size() {
    const rtnval = this._keys.size;
    return rtnval;
  }
  /**
   * Return the underlying keys as a sorted array snapshot.
   * Intended for logging / diagnostics. Do NOT use as a security
   * boundary — sidebar visibility is UX only.
   */
  toSortedArray() {
    const rtnval = Array.from(this._keys).sort();
    return rtnval;
  }
};

// src/pyc-site-shell/permissions/permission-cache.ts
var DEFAULT_PERMISSIONS_ENDPOINT = "/api/v1/me/permissions";
var PermissionCache = class {
  _current;
  _degraded;
  _endpoint;
  /**
   * @param endpoint - URL the cache will GET on `refresh()`.
   */
  constructor(endpoint) {
    this._current = new PermissionSet([]);
    this._degraded = false;
    this._endpoint = endpoint;
  }
  /**
   * Return the current snapshot.
   */
  current() {
    const rtnval = this._current;
    return rtnval;
  }
  /**
   * Return true when the most recent fetch failed.
   */
  get degraded() {
    const rtnval = this._degraded;
    return rtnval;
  }
  /**
   * Force a refresh from the server. On success the new
   * `PermissionSet` becomes the current snapshot and `degraded`
   * resets to false. On failure the previous snapshot is
   * retained and `degraded` is set to true. The promise resolves
   * with the current snapshot in both cases — callers should not
   * branch on this method's success/failure as a security check.
   */
  async refresh() {
    try {
      const response = await fetch(this._endpoint, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        this._degraded = true;
        return this._current;
      }
      const payload = await response.json();
      const keys = _extract_permission_keys(payload);
      if (keys === null) {
        this._degraded = true;
        return this._current;
      }
      this._current = new PermissionSet(keys);
      this._degraded = false;
      return this._current;
    } catch (reason) {
      this._degraded = true;
      console.warn(
        "pychestrate.ui.shell.permissions_fetch_failed",
        { endpoint: this._endpoint }
      );
      return this._current;
    }
  }
};
function _extract_permission_keys(payload) {
  if (Array.isArray(payload) === true) {
    const rtnval = payload.filter(
      (item) => typeof item === "string"
    );
    return rtnval;
  }
  if (payload !== null && typeof payload === "object") {
    const obj = payload;
    const candidate = obj.permissions;
    if (Array.isArray(candidate) === true) {
      const rtnval = candidate.filter(
        (item) => typeof item === "string"
      );
      return rtnval;
    }
  }
  return null;
}

// src/pyc-site-shell/routing/shell-router.ts
var ShellRouter = class _ShellRouter {
  _current;
  _callbacks;
  _main_region_getter;
  /**
   * @param initial_path - Path the shell booted on; typically
   *                       `window.location.pathname`.
   * @param main_region_getter - Function returning the active
   *                             `<main>` region (used for focus
   *                             restoration).
   */
  constructor(initial_path, main_region_getter) {
    this._current = _ShellRouter.parse(initial_path);
    this._callbacks = [];
    this._main_region_getter = main_region_getter;
    window.addEventListener("popstate", () => {
      const next_context = _ShellRouter.parse(window.location.pathname);
      const previous_context = this._current;
      this._current = next_context;
      this._dispatch(next_context, previous_context);
    });
  }
  /**
   * Parse a URL path into a structured `RouteContext`. M1
   * implementation is intentionally trivial — query params are
   * lifted into the `params` map; path segments are not parsed
   * against route patterns.
   */
  static parse(path) {
    let working = path;
    const params = {};
    const query_index = path.indexOf("?");
    if (query_index >= 0) {
      working = path.slice(0, query_index);
      const query_string = path.slice(query_index + 1);
      const search_params = new URLSearchParams(query_string);
      for (const [key, value] of search_params.entries()) {
        params[key] = value;
      }
    }
    const rtnval = { path: working, params };
    return rtnval;
  }
  /**
   * Return the active route context.
   */
  current() {
    const rtnval = this._current;
    return rtnval;
  }
  /**
   * Subscribe a callback for navigation events.
   */
  onNavigate(callback) {
    this._callbacks.push(callback);
    return;
  }
  /**
   * Drive a same-origin navigation by pushing on the history
   * stack and re-rendering. Callers are responsible for any
   * permission-cache refresh; this router does not own the
   * permission model.
   */
  async navigateTo(route) {
    const next_context = _ShellRouter.parse(route);
    const previous_context = this._current;
    window.history.pushState({}, "", route);
    this._current = next_context;
    await this._dispatch(next_context, previous_context);
    this._restore_focus();
    return;
  }
  async _dispatch(next_context, previous_context) {
    for (const callback of this._callbacks) {
      try {
        await callback(next_context, previous_context);
      } catch (reason) {
        console.warn(
          "pychestrate.ui.shell.navigation_callback_failed",
          { reason: String(reason) }
        );
      }
    }
    return;
  }
  _restore_focus() {
    const main = this._main_region_getter();
    if (main === null) {
      return;
    }
    const heading = main.querySelector("h1");
    if (heading !== null) {
      if (heading.hasAttribute("tabindex") === false) {
        heading.setAttribute("tabindex", "-1");
      }
      ;
      heading.focus();
      return;
    }
    const focusable = main.querySelector(
      "a, button, input, select, textarea, [tabindex]"
    );
    if (focusable !== null) {
      focusable.focus();
    }
    return;
  }
};

// src/pyc-site-shell/sidebar/sidebar-registry.ts
var SidebarRegistry = class {
  _groups;
  _entries;
  _entry_routes;
  constructor() {
    this._groups = /* @__PURE__ */ new Map();
    this._entries = [];
    this._entry_routes = /* @__PURE__ */ new Set();
  }
  /**
   * Register a sidebar group. Duplicate `groupId` registrations
   * are dropped with a warn (first wins).
   */
  registerGroup(group) {
    if (group === null || typeof group !== "object") {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_group_registration"
      );
      return;
    }
    if (typeof group.groupId !== "string" || group.groupId.length === 0) {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_group_registration",
        { reason: "missing_groupId" }
      );
      return;
    }
    if (this._groups.has(group.groupId) === true) {
      console.warn(
        "pychestrate.ui.shell.sidebar_dup_group",
        { groupId: group.groupId }
      );
      return;
    }
    const normalized = _normalize_group(group);
    this._groups.set(normalized.groupId, normalized);
    return;
  }
  /**
   * Register a sidebar entry. Duplicate `route` registrations
   * are dropped with a warn (first wins, per Requirement 2.5).
   */
  registerEntry(entry) {
    if (entry === null || typeof entry !== "object") {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_entry_registration"
      );
      return;
    }
    if (typeof entry.route !== "string" || entry.route.length === 0) {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_entry_registration",
        { reason: "missing_route" }
      );
      return;
    }
    if (this._entry_routes.has(entry.route) === true) {
      const existing = this._entries.find(
        (candidate) => candidate.route === entry.route
      );
      console.warn(
        "pychestrate.ui.shell.sidebar_dup_route",
        {
          route: entry.route,
          keptLabel: existing !== void 0 ? existing.label : null,
          droppedLabel: entry.label
        }
      );
      return;
    }
    const normalized = _normalize_entry(entry);
    this._entries.push(normalized);
    this._entry_routes.add(normalized.route);
    return;
  }
  /**
   * Compute the visible sidebar for the supplied permission set.
   *
   * Visibility rules (Requirement 2):
   *
   * - A group is visible only when every required permission is
   *   present.
   * - An entry is visible only when (a) its required permissions
   *   are all present AND (b) if it declares a group, the group
   *   is also visible.
   * - Entries without a group are returned in `ungrouped` in
   *   registration order.
   */
  visible(perms) {
    const visible_groups = [];
    const group_by_id = /* @__PURE__ */ new Map();
    for (const group of this._groups.values()) {
      if (perms.hasAll(group.requiredPermissions) === true) {
        group_by_id.set(group.groupId, group);
        visible_groups.push({ group, entries: [] });
      }
    }
    const ungrouped = [];
    for (const entry of this._entries) {
      if (perms.hasAll(entry.requiredPermissions) === false) {
        continue;
      }
      const group_id = entry.group !== null && entry.group !== void 0 ? entry.group : null;
      if (group_id === null) {
        ungrouped.push(entry);
        continue;
      }
      if (group_by_id.has(group_id) === false) {
        continue;
      }
      for (const bucket of visible_groups) {
        if (bucket.group.groupId === group_id) {
          bucket.entries.push(entry);
          break;
        }
      }
    }
    const non_empty_groups = visible_groups.filter(
      (bucket) => bucket.entries.length > 0
    );
    const rtnval = {
      groups: non_empty_groups,
      ungrouped
    };
    return rtnval;
  }
  /**
   * Total number of visible entries — used by the shell to drive
   * the empty-state predicate (Requirement 5.1).
   */
  visibleEntryCount(perms) {
    const visible_sidebar = this.visible(perms);
    let count = visible_sidebar.ungrouped.length;
    for (const bucket of visible_sidebar.groups) {
      count = count + bucket.entries.length;
    }
    return count;
  }
};
function _normalize_group(group) {
  const rtnval = {
    groupId: group.groupId,
    label: typeof group.label === "string" ? group.label : group.groupId,
    icon: group.icon !== void 0 ? group.icon : null,
    requiredPermissions: Array.isArray(group.requiredPermissions) ? group.requiredPermissions.filter(
      (item) => typeof item === "string"
    ) : []
  };
  return rtnval;
}
function _normalize_entry(entry) {
  const rtnval = {
    entryId: typeof entry.entryId === "string" ? entry.entryId : entry.route,
    label: typeof entry.label === "string" ? entry.label : entry.route,
    route: entry.route,
    icon: entry.icon !== void 0 ? entry.icon : null,
    requiredPermissions: Array.isArray(entry.requiredPermissions) ? entry.requiredPermissions.filter(
      (item) => typeof item === "string"
    ) : [],
    group: entry.group !== void 0 ? entry.group : null
  };
  return rtnval;
}

// src/pyc-site-shell/sidebar/sidebar-renderer.ts
var SidebarRenderer = class {
  _container;
  _on_navigate;
  constructor(container, on_navigate) {
    this._container = container;
    this._on_navigate = on_navigate;
  }
  /**
   * Render the supplied visible sidebar into the container.
   *
   * @param registry - The sidebar registry source of truth.
   * @param perms - Current permission set.
   * @param active_path - Path of the active route, used for the
   *                      `aria-current="page"` marker.
   */
  render(registry, perms, active_path) {
    const visible_sidebar = registry.visible(perms);
    this._container.replaceChildren();
    const nav = document.createElement("nav");
    nav.setAttribute("role", "navigation");
    nav.setAttribute("aria-label", "Primary");
    nav.classList.add("pyc-site-shell__sidebar-nav");
    for (const entry of visible_sidebar.ungrouped) {
      const entry_element = this._build_entry_element(
        entry.label,
        entry.route,
        active_path
      );
      nav.appendChild(entry_element);
    }
    for (const bucket of visible_sidebar.groups) {
      const group_section = document.createElement("section");
      group_section.classList.add("pyc-site-shell__sidebar-group");
      const heading = document.createElement("h2");
      heading.classList.add("pyc-site-shell__sidebar-group-label");
      heading.textContent = bucket.group.label;
      group_section.appendChild(heading);
      for (const entry of bucket.entries) {
        const entry_element = this._build_entry_element(
          entry.label,
          entry.route,
          active_path
        );
        group_section.appendChild(entry_element);
      }
      nav.appendChild(group_section);
    }
    this._container.appendChild(nav);
    return;
  }
  /**
   * Helper — build one `<a>` element representing a sidebar
   * entry. Text-only (no `innerHTML`) per the design's security
   * notes.
   */
  _build_entry_element(label, route, active_path) {
    const link = document.createElement("a");
    link.href = route;
    link.textContent = label;
    link.classList.add("pyc-site-shell__sidebar-entry");
    if (route === active_path) {
      link.setAttribute("aria-current", "page");
    }
    link.addEventListener("click", (event) => {
      const mouse_event = event;
      if (mouse_event.defaultPrevented === true) {
        return;
      }
      if (mouse_event.button !== void 0 && mouse_event.button !== 0) {
        return;
      }
      if (mouse_event.metaKey === true || mouse_event.ctrlKey === true || mouse_event.shiftKey === true || mouse_event.altKey === true) {
        return;
      }
      event.preventDefault();
      this._on_navigate(route);
    });
    return link;
  }
};

// src/pyc-site-shell/pyc-site-shell.ts
var ATTR_INITIAL_ROUTE = "initial-route";
var ATTR_PERMISSIONS_ENDPOINT = "permissions-endpoint";
var ATTR_PALETTE_TIMEOUT_MS = "palette-timeout-ms";
var ATTR_BRAND_LABEL = "brand-label";
var PycSiteShell = class extends HTMLElement {
  _sidebar_registry;
  _permission_cache;
  _router;
  _sidebar_renderer;
  _main_region;
  _sidebar_region;
  _ready;
  static observedAttributes = [
    ATTR_INITIAL_ROUTE,
    ATTR_PERMISSIONS_ENDPOINT,
    ATTR_PALETTE_TIMEOUT_MS,
    "aria-label",
    ATTR_BRAND_LABEL
  ];
  constructor() {
    super();
    this._sidebar_registry = new SidebarRegistry();
    const endpoint = this.getAttribute(ATTR_PERMISSIONS_ENDPOINT);
    const resolved_endpoint = endpoint !== null && endpoint.length > 0 ? endpoint : DEFAULT_PERMISSIONS_ENDPOINT;
    this._permission_cache = new PermissionCache(resolved_endpoint);
    this._router = null;
    this._sidebar_renderer = null;
    this._main_region = null;
    this._sidebar_region = null;
    this._ready = false;
  }
  get sidebar() {
    const rtnval = this._sidebar_registry;
    return rtnval;
  }
  get permissions() {
    const rtnval = this._permission_cache;
    return rtnval;
  }
  connectedCallback() {
    this._render_skeleton();
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
  _render_skeleton() {
    const initial_route_attr = this.getAttribute(ATTR_INITIAL_ROUTE);
    const initial_path = initial_route_attr !== null && initial_route_attr.length > 0 ? initial_route_attr : window.location.pathname;
    this.replaceChildren();
    const layout = document.createElement("div");
    layout.classList.add("pyc-site-shell__layout");
    const brand_attr = this.getAttribute(ATTR_BRAND_LABEL);
    const header = build_header({
      brand_label: brand_attr !== null && brand_attr.length > 0 ? brand_attr : "Pychestrate",
      user_display_name: null
    });
    layout.appendChild(header);
    const sidebar = document.createElement("aside");
    sidebar.classList.add("pyc-site-shell__sidebar");
    layout.appendChild(sidebar);
    this._sidebar_region = sidebar;
    const main = document.createElement("main");
    main.setAttribute("role", "main");
    main.classList.add("pyc-site-shell__main");
    layout.appendChild(main);
    this._main_region = main;
    this.appendChild(layout);
    this._router = new ShellRouter(initial_path, () => this._main_region);
    this._sidebar_renderer = new SidebarRenderer(sidebar, (route) => {
      void this._router?.navigateTo(route);
    });
    this._router.onNavigate(async () => {
      await this._permission_cache.refresh();
      this._render_sidebar_and_empty_state();
    });
    return;
  }
  _wire_window_registry() {
    const global_target = window;
    const handle = {
      sidebar: this._sidebar_registry,
      element: this
    };
    global_target.pychestrateShell = handle;
    return;
  }
  async _boot() {
    await this._permission_cache.refresh();
    this._render_sidebar_and_empty_state();
    this._ready = true;
    this.dispatchEvent(
      new CustomEvent("pyc-site-shell-ready", {
        bubbles: true,
        composed: true,
        detail: {
          visibleEntryCount: this._sidebar_registry.visibleEntryCount(
            this._permission_cache.current()
          ),
          degraded: this._permission_cache.degraded
        }
      })
    );
    return;
  }
  _render_sidebar_and_empty_state() {
    const perms = this._permission_cache.current();
    const active_path = this._router !== null ? this._router.current().path : window.location.pathname;
    if (this._sidebar_renderer !== null && this._sidebar_region !== null) {
      this._sidebar_renderer.render(
        this._sidebar_registry,
        perms,
        active_path
      );
    }
    const visible_entry_count = this._sidebar_registry.visibleEntryCount(
      perms
    );
    if (visible_entry_count === 0 && this._main_region !== null) {
      this._main_region.replaceChildren(build_empty_state());
      this.dispatchEvent(
        new CustomEvent("pyc-site-shell-empty-state-rendered", {
          bubbles: true,
          composed: true,
          detail: {}
        })
      );
    }
    return;
  }
  get isReady() {
    const rtnval = this._ready;
    return rtnval;
  }
  /**
   * Test/diagnostic helper — returns the current permission set.
   * Not part of the long-term public API surface (which goes
   * through DOM CustomEvents).
   */
  currentPermissions() {
    const rtnval = this._permission_cache.current();
    return rtnval;
  }
};

// src/pyc-site-shell/index.ts
var TAG_NAME = "pyc-site-shell";
if (typeof customElements !== "undefined") {
  if (customElements.get(TAG_NAME) === void 0) {
    customElements.define(TAG_NAME, PycSiteShell);
  }
}
export {
  PermissionCache,
  PermissionSet,
  PycSiteShell,
  SidebarRegistry
};
//# sourceMappingURL=pyc-site-shell.js.map
