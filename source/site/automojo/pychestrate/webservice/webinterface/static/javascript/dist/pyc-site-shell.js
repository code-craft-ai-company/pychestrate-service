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

// src/pyc-site-shell/chrome/degraded-banner.ts
var DegradedBanner = class {
  _container;
  _element;
  _dismissed;
  /**
   * @param container Region the banner attaches to. Typically
   *                  the shell's main region or its parent.
   */
  constructor(container) {
    this._container = container;
    this._element = null;
    this._dismissed = false;
  }
  /**
   * Render or refresh the banner. Idempotent: a second call
   * after a previous show is a no-op.
   */
  show() {
    if (this._dismissed === true) {
      return;
    }
    if (this._element !== null && this._element.parentNode !== null) {
      return;
    }
    const banner = document.createElement("div");
    banner.classList.add("pyc-site-shell__degraded-banner");
    banner.setAttribute("role", "status");
    banner.setAttribute("aria-live", "polite");
    const message = document.createElement("span");
    message.classList.add("pyc-site-shell__degraded-banner-message");
    message.textContent = "Permissions could not be refreshed. Using the last known set. Some controls may behave incorrectly.";
    banner.appendChild(message);
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.classList.add("pyc-site-shell__degraded-banner-dismiss");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "Dismiss";
    dismiss.addEventListener("click", () => {
      this._dismissed = true;
      this.hide();
    });
    banner.appendChild(dismiss);
    this._element = banner;
    this._container.insertBefore(banner, this._container.firstChild);
    return;
  }
  /**
   * Remove the banner from the DOM. Safe to call when not
   * rendered.
   */
  hide() {
    if (this._element !== null && this._element.parentNode !== null) {
      this._element.parentNode.removeChild(this._element);
    }
    this._element = null;
    return;
  }
};

// src/pyc-site-shell/chrome/session-toast.ts
var TOAST_MESSAGE = "Your session expired. Please sign in again.";
var SessionExpiredToast = class {
  _container;
  _element;
  /**
   * @param container Region the toast attaches to.
   */
  constructor(container) {
    this._container = container;
    this._element = null;
  }
  /**
   * Render the toast if not already visible.
   */
  show() {
    if (this._element !== null && this._element.parentNode !== null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-site-shell__session-toast");
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    const message = document.createElement("span");
    message.classList.add("pyc-site-shell__session-toast-message");
    message.textContent = TOAST_MESSAGE;
    toast.appendChild(message);
    const link = document.createElement("a");
    link.classList.add("pyc-site-shell__session-toast-action");
    link.textContent = "Sign in";
    const current_path = window.location.pathname + window.location.search;
    const encoded = encodeURIComponent(current_path);
    link.href = "/login?next=" + encoded;
    toast.appendChild(link);
    this._element = toast;
    this._container.appendChild(toast);
    return;
  }
  /**
   * Remove the toast from the DOM.
   */
  hide() {
    if (this._element !== null && this._element.parentNode !== null) {
      this._element.parentNode.removeChild(this._element);
    }
    this._element = null;
    return;
  }
};

// src/pyc-site-shell/palette/palette-registry.ts
var DEFAULT_PROVIDER_TIMEOUT_MS = 5e3;
var PALETTE_QUERY_MAX_LENGTH = 128;
var PaletteRegistry = class {
  _providers;
  constructor() {
    this._providers = /* @__PURE__ */ new Map();
  }
  /**
   * Register a palette provider. Duplicate ``providerId`` calls
   * are dropped with a ``console.warn`` (first wins) -- mirrors
   * the sidebar registry's collision policy.
   *
   * @param provider Descriptor.
   */
  registerProvider(provider) {
    if (provider === null || typeof provider !== "object") {
      console.warn(
        "pychestrate.ui.shell.palette_malformed_provider_registration"
      );
      return;
    }
    if (typeof provider.providerId !== "string" || provider.providerId.length === 0) {
      console.warn(
        "pychestrate.ui.shell.palette_malformed_provider_registration",
        { reason: "missing_providerId" }
      );
      return;
    }
    if (typeof provider.query !== "function") {
      console.warn(
        "pychestrate.ui.shell.palette_malformed_provider_registration",
        { reason: "missing_query", providerId: provider.providerId }
      );
      return;
    }
    if (this._providers.has(provider.providerId) === true) {
      console.warn(
        "pychestrate.ui.shell.palette_dup_provider",
        { providerId: provider.providerId }
      );
      return;
    }
    this._providers.set(provider.providerId, provider);
    return;
  }
  /**
   * Return the providers that pass the permission gate for the
   * supplied permission set. Order follows registration order.
   */
  visibleProviders(perms) {
    const visible = [];
    for (const provider of this._providers.values()) {
      const required = provider.requiredPermissions !== void 0 ? provider.requiredPermissions : [];
      if (perms.hasAll(required) === true) {
        visible.push(provider);
      }
    }
    return visible;
  }
  /**
   * Total registered provider count. Diagnostic only.
   */
  size() {
    const rtnval = this._providers.size;
    return rtnval;
  }
  /**
   * Fan-out the supplied query to every visible provider,
   * applying a per-provider timeout. Returns an array of
   * outcomes in the same order as ``visibleProviders``.
   *
   * Failures (rejections, timeouts) are reported as outcomes
   * with ``error`` set, NOT as a thrown rejection from this
   * method. Callers can therefore render partial results
   * deterministically.
   *
   * @param query Raw query string. Trimmed and capped to
   *              ``PALETTE_QUERY_MAX_LENGTH`` characters.
   * @param perms Active permission set.
   */
  async queryAll(query, perms) {
    const normalized = _normalize_query(query);
    const visible = this.visibleProviders(perms);
    const pending = [];
    for (const provider of visible) {
      pending.push(_run_provider(provider, normalized));
    }
    const settled = await Promise.all(pending);
    return settled;
  }
};
function _normalize_query(query) {
  let working = typeof query === "string" ? query : "";
  working = working.trim();
  if (working.length > PALETTE_QUERY_MAX_LENGTH) {
    working = working.slice(0, PALETTE_QUERY_MAX_LENGTH);
  }
  return working;
}
async function _run_provider(provider, query) {
  const timeout_ms = typeof provider.timeoutMs === "number" && provider.timeoutMs > 0 ? provider.timeoutMs : DEFAULT_PROVIDER_TIMEOUT_MS;
  let timer_handle = null;
  const timeout_promise = new Promise((_, reject) => {
    timer_handle = setTimeout(() => {
      reject(new Error("palette_provider_timeout"));
    }, timeout_ms);
  });
  try {
    const results = await Promise.race([
      provider.query(query),
      timeout_promise
    ]);
    if (timer_handle !== null) {
      clearTimeout(timer_handle);
    }
    const safe_results = Array.isArray(results) ? results : [];
    const outcome = {
      providerId: provider.providerId,
      providerLabel: provider.label,
      results: safe_results,
      error: null
    };
    return outcome;
  } catch (reason) {
    if (timer_handle !== null) {
      clearTimeout(timer_handle);
    }
    const outcome = {
      providerId: provider.providerId,
      providerLabel: provider.label,
      results: [],
      error: String(reason)
    };
    return outcome;
  }
}

// src/pyc-site-shell/palette/palette-dialog.ts
var PALETTE_INPUT_DEBOUNCE_MS = 80;
var PaletteDialog = class {
  _registry;
  _host;
  _container;
  _input;
  _results_region;
  _status_region;
  _is_open;
  _previous_focus;
  _debounce_handle;
  _query_token;
  _flat_results;
  _active_index;
  constructor(registry, host) {
    this._registry = registry;
    this._host = host;
    this._container = null;
    this._input = null;
    this._results_region = null;
    this._status_region = null;
    this._is_open = false;
    this._previous_focus = null;
    this._debounce_handle = null;
    this._query_token = 0;
    this._flat_results = [];
    this._active_index = -1;
  }
  get isOpen() {
    const rtnval = this._is_open;
    return rtnval;
  }
  /**
   * Open the palette. No-op when already open. Builds the DOM
   * on first open and attaches it to ``document.body``.
   *
   * @param mount_target Optional override for the parent
   *                     element the dialog attaches to. Falls
   *                     back to ``document.body``.
   */
  open(mount_target = null) {
    if (this._is_open === true) {
      return;
    }
    if (this._container === null) {
      this._build_dom();
    }
    const container = this._container;
    if (container === null) {
      return;
    }
    const parent = mount_target !== null ? mount_target : document.body;
    parent.appendChild(container);
    this._is_open = true;
    this._previous_focus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (this._input !== null) {
      this._input.value = "";
      this._input.focus();
    }
    this._render_status("Type to search across registered providers.");
    this._host.emit("pyc-site-shell-palette-opened", {});
    if (typeof this._host.observePaletteOpened === "function") {
      this._host.observePaletteOpened();
    }
    return;
  }
  /**
   * Close the palette and restore focus to the previously
   * focused element. No-op when already closed.
   */
  close() {
    if (this._is_open === false) {
      return;
    }
    const container = this._container;
    if (container !== null && container.parentNode !== null) {
      container.parentNode.removeChild(container);
    }
    this._is_open = false;
    if (this._debounce_handle !== null) {
      clearTimeout(this._debounce_handle);
      this._debounce_handle = null;
    }
    this._flat_results = [];
    this._active_index = -1;
    const restore_target = this._previous_focus;
    this._previous_focus = null;
    if (restore_target !== null && typeof restore_target.focus === "function") {
      restore_target.focus();
    }
    this._host.emit("pyc-site-shell-palette-closed", {});
    return;
  }
  _build_dom() {
    const container = document.createElement("div");
    container.classList.add("pyc-site-shell__palette-backdrop");
    container.setAttribute("role", "presentation");
    const dialog = document.createElement("div");
    dialog.classList.add("pyc-site-shell__palette-dialog");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Command Palette");
    dialog.tabIndex = -1;
    const input = document.createElement("input");
    input.type = "search";
    input.classList.add("pyc-site-shell__palette-input");
    input.setAttribute("aria-label", "Search providers");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("spellcheck", "false");
    input.placeholder = "Type to search...";
    input.addEventListener("input", () => {
      this._on_input_changed();
    });
    dialog.appendChild(input);
    const status = document.createElement("div");
    status.classList.add("pyc-site-shell__palette-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    dialog.appendChild(status);
    const results = document.createElement("div");
    results.classList.add("pyc-site-shell__palette-results");
    results.setAttribute("role", "listbox");
    results.setAttribute("aria-label", "Palette results");
    dialog.appendChild(results);
    dialog.addEventListener("keydown", (event) => {
      this._on_dialog_keydown(event);
    });
    container.addEventListener("mousedown", (event) => {
      if (event.target === container) {
        this.close();
      }
    });
    container.appendChild(dialog);
    this._container = container;
    this._input = input;
    this._status_region = status;
    this._results_region = results;
    return;
  }
  _on_input_changed() {
    if (this._debounce_handle !== null) {
      clearTimeout(this._debounce_handle);
    }
    this._debounce_handle = setTimeout(() => {
      this._debounce_handle = null;
      void this._run_query();
    }, PALETTE_INPUT_DEBOUNCE_MS);
    return;
  }
  async _run_query() {
    if (this._input === null || this._results_region === null) {
      return;
    }
    const raw_query = this._input.value;
    this._query_token = this._query_token + 1;
    const token = this._query_token;
    if (raw_query.trim().length === 0) {
      this._results_region.replaceChildren();
      this._flat_results = [];
      this._active_index = -1;
      this._render_status(
        "Type to search across registered providers."
      );
      return;
    }
    const perms = this._host.getPermissions();
    const visible_providers = this._registry.visibleProviders(perms);
    if (visible_providers.length === 0) {
      this._results_region.replaceChildren();
      this._flat_results = [];
      this._active_index = -1;
      this._render_status("No providers available for your account.");
      return;
    }
    this._render_status("Searching...");
    const fanout_started = typeof performance !== "undefined" ? performance.now() : 0;
    const outcomes = await this._registry.queryAll(raw_query, perms);
    const fanout_finished = typeof performance !== "undefined" ? performance.now() : 0;
    if (typeof this._host.observePaletteFanout === "function") {
      this._host.observePaletteFanout(
        (fanout_finished - fanout_started) / 1e3
      );
    }
    if (token !== this._query_token) {
      return;
    }
    this._render_outcomes(outcomes);
    return;
  }
  _render_outcomes(outcomes) {
    if (this._results_region === null) {
      return;
    }
    this._results_region.replaceChildren();
    this._flat_results = [];
    let total_results = 0;
    for (const outcome of outcomes) {
      const section = document.createElement("div");
      section.classList.add("pyc-site-shell__palette-group");
      const heading = document.createElement("div");
      heading.classList.add("pyc-site-shell__palette-group-label");
      heading.textContent = outcome.providerLabel;
      section.appendChild(heading);
      if (outcome.error !== null) {
        const notice = document.createElement("div");
        notice.classList.add("pyc-site-shell__palette-provider-error");
        notice.setAttribute("role", "note");
        notice.textContent = "This provider is unavailable.";
        section.appendChild(notice);
        this._results_region.appendChild(section);
        continue;
      }
      if (outcome.results.length === 0) {
        const empty = document.createElement("div");
        empty.classList.add("pyc-site-shell__palette-empty");
        empty.textContent = "No matches.";
        section.appendChild(empty);
        this._results_region.appendChild(section);
        continue;
      }
      for (const result of outcome.results) {
        const option = document.createElement("div");
        option.classList.add("pyc-site-shell__palette-option");
        option.setAttribute("role", "option");
        option.setAttribute("data-provider-id", outcome.providerId);
        option.setAttribute("data-result-id", result.id);
        option.tabIndex = -1;
        const label = document.createElement("div");
        label.classList.add("pyc-site-shell__palette-option-label");
        label.textContent = result.label;
        option.appendChild(label);
        if (typeof result.description === "string" && result.description.length > 0) {
          const desc = document.createElement("div");
          desc.classList.add(
            "pyc-site-shell__palette-option-description"
          );
          desc.textContent = result.description;
          option.appendChild(desc);
        }
        option.addEventListener("click", () => {
          void this._activate_result(result);
        });
        section.appendChild(option);
        this._flat_results.push({
          providerId: outcome.providerId,
          result,
          element: option
        });
        total_results = total_results + 1;
      }
      this._results_region.appendChild(section);
    }
    this._active_index = this._flat_results.length > 0 ? 0 : -1;
    this._update_active_highlight();
    if (total_results === 0) {
      this._render_status("No results.");
    } else {
      const label = total_results === 1 ? "1 result." : `${total_results} results.`;
      this._render_status(label);
    }
    return;
  }
  _render_status(text) {
    if (this._status_region !== null) {
      this._status_region.textContent = text;
    }
    return;
  }
  _update_active_highlight() {
    for (let index = 0; index < this._flat_results.length; index = index + 1) {
      const entry = this._flat_results[index];
      if (index === this._active_index) {
        entry.element.setAttribute("aria-selected", "true");
        entry.element.classList.add(
          "pyc-site-shell__palette-option--active"
        );
      } else {
        entry.element.setAttribute("aria-selected", "false");
        entry.element.classList.remove(
          "pyc-site-shell__palette-option--active"
        );
      }
    }
    return;
  }
  async _activate_result(result) {
    this.close();
    if (typeof result.onActivate === "function") {
      try {
        await result.onActivate();
      } catch (reason) {
        console.warn(
          "pychestrate.ui.shell.palette_activate_failed",
          { reason: String(reason) }
        );
      }
      return;
    }
    if (typeof result.route === "string" && result.route.length > 0) {
      this._host.navigate(result.route);
    }
    return;
  }
  _on_dialog_keydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      this.close();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (this._flat_results.length === 0) {
        return;
      }
      this._active_index = (this._active_index + 1) % this._flat_results.length;
      this._update_active_highlight();
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (this._flat_results.length === 0) {
        return;
      }
      const next_index = this._active_index <= 0 ? this._flat_results.length - 1 : this._active_index - 1;
      this._active_index = next_index;
      this._update_active_highlight();
      return;
    }
    if (event.key === "Enter") {
      if (this._active_index >= 0 && this._active_index < this._flat_results.length) {
        event.preventDefault();
        const active = this._flat_results[this._active_index];
        void this._activate_result(active.result);
      }
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      if (this._input !== null) {
        this._input.focus();
      }
      return;
    }
    return;
  }
};

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
var DEFAULT_FRESHNESS_TTL_MS = 6e4;
var PermissionCache = class {
  _current;
  _degraded;
  _endpoint;
  _freshness_ttl_ms;
  _now;
  _last_success_at_ms;
  _diff_listeners;
  _fetch_failed_listeners;
  _session_401_listeners;
  _fetch_succeeded_listeners;
  _last_outcome_was_401;
  /**
   * @param endpoint Either a URL string (back-compat) or an
   *                 options object. When a string is supplied,
   *                 defaults are applied for the other fields.
   */
  constructor(endpoint) {
    let resolved_endpoint = DEFAULT_PERMISSIONS_ENDPOINT;
    let resolved_ttl_ms = DEFAULT_FRESHNESS_TTL_MS;
    let resolved_now = () => Date.now();
    if (typeof endpoint === "string") {
      resolved_endpoint = endpoint;
    } else if (endpoint !== null && typeof endpoint === "object") {
      if (typeof endpoint.endpoint === "string" && endpoint.endpoint.length > 0) {
        resolved_endpoint = endpoint.endpoint;
      }
      if (typeof endpoint.freshnessTtlMs === "number") {
        resolved_ttl_ms = endpoint.freshnessTtlMs;
      }
      if (typeof endpoint.now === "function") {
        resolved_now = endpoint.now;
      }
    }
    this._current = new PermissionSet([]);
    this._degraded = false;
    this._endpoint = resolved_endpoint;
    this._freshness_ttl_ms = resolved_ttl_ms;
    this._now = resolved_now;
    this._last_success_at_ms = null;
    this._diff_listeners = [];
    this._fetch_failed_listeners = [];
    this._session_401_listeners = [];
    this._fetch_succeeded_listeners = [];
    this._last_outcome_was_401 = false;
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
   * Subscribe to permission-set diffs. Listener fires on every
   * ``refresh()`` whose successful fetch changed the snapshot.
   */
  onPermissionsChanged(listener) {
    this._diff_listeners.push(listener);
    return;
  }
  /**
   * Subscribe to non-401 fetch failures (network errors, 5xx).
   * The degraded banner consumes this hook.
   */
  onFetchFailed(listener) {
    this._fetch_failed_listeners.push(listener);
    return;
  }
  /**
   * Subscribe to successful fetches -- used by the degraded
   * banner to auto-dismiss on recovery.
   */
  onFetchSucceeded(listener) {
    this._fetch_succeeded_listeners.push(listener);
    return;
  }
  /**
   * Subscribe to mid-session 401 events. Fired exactly once per
   * transition from healthy to expired-session.
   */
  onSession401(listener) {
    this._session_401_listeners.push(listener);
    return;
  }
  /**
   * Force a refresh from the server. On success the new
   * `PermissionSet` becomes the current snapshot and `degraded`
   * resets to false. On failure the previous snapshot is
   * retained and `degraded` is set to true. The promise resolves
   * with the current snapshot in both cases -- callers should not
   * branch on this method's success/failure as a security check.
   *
   * When called within the freshness TTL of the previous success
   * AND ``force`` is false, the cached snapshot is returned
   * without a network call.
   *
   * @param force When true, bypass the TTL dedup. Used by the
   *              navigation hook (Requirement 4.1 requires a
   *              refetch on every full navigation).
   */
  async refresh(force = true) {
    if (force === false && this._last_success_at_ms !== null && this._now() - this._last_success_at_ms < this._freshness_ttl_ms) {
      return this._current;
    }
    try {
      const response = await fetch(this._endpoint, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.status === 401) {
        this._degraded = true;
        if (this._last_outcome_was_401 === false) {
          this._last_outcome_was_401 = true;
          for (const listener of this._session_401_listeners) {
            try {
              listener();
            } catch (reason) {
              console.warn(
                "pychestrate.ui.shell.permissions_listener_failed",
                { kind: "session_401", reason: String(reason) }
              );
            }
          }
        }
        return this._current;
      }
      if (response.ok === false) {
        this._degraded = true;
        this._fire_fetch_failed(`http_${response.status}`);
        return this._current;
      }
      const payload = await response.json();
      const keys = _extract_permission_keys(payload);
      if (keys === null) {
        this._degraded = true;
        this._fire_fetch_failed("malformed_payload");
        return this._current;
      }
      const next_set = new PermissionSet(keys);
      const diff = this._current.diff(next_set);
      this._current = next_set;
      this._degraded = false;
      this._last_outcome_was_401 = false;
      this._last_success_at_ms = this._now();
      if (diff.added.length > 0 || diff.removed.length > 0) {
        for (const listener of this._diff_listeners) {
          try {
            listener(diff);
          } catch (reason) {
            console.warn(
              "pychestrate.ui.shell.permissions_listener_failed",
              { kind: "diff", reason: String(reason) }
            );
          }
        }
      }
      for (const listener of this._fetch_succeeded_listeners) {
        try {
          listener();
        } catch (reason) {
          console.warn(
            "pychestrate.ui.shell.permissions_listener_failed",
            { kind: "success", reason: String(reason) }
          );
        }
      }
      return this._current;
    } catch (reason) {
      this._degraded = true;
      console.warn(
        "pychestrate.ui.shell.permissions_fetch_failed",
        { endpoint: this._endpoint }
      );
      this._fire_fetch_failed(String(reason));
      return this._current;
    }
  }
  _fire_fetch_failed(reason) {
    for (const listener of this._fetch_failed_listeners) {
      try {
        listener({ reason });
      } catch (inner) {
        console.warn(
          "pychestrate.ui.shell.permissions_listener_failed",
          { kind: "failed", reason: String(inner) }
        );
      }
    }
    return;
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
  _change_listeners;
  constructor() {
    this._groups = /* @__PURE__ */ new Map();
    this._entries = [];
    this._entry_routes = /* @__PURE__ */ new Set();
    this._change_listeners = [];
  }
  /**
   * Subscribe to registry mutations. The shell wires its
   * sidebar re-render through here so feature bundles that
   * register their groups / entries AFTER the shell's initial
   * boot render (a load-order race -- the shell bundle and the
   * feature bundle are independent ``<script type="module">``
   * tags) still surface in the sidebar instead of leaving the
   * shell stuck on the zero-permissions empty state.
   */
  onChange(listener) {
    this._change_listeners.push(listener);
    return;
  }
  _notify_change() {
    for (const listener of this._change_listeners) {
      try {
        listener();
      } catch (reason) {
        console.warn(
          "pychestrate.ui.shell.sidebar_change_listener_failed",
          { reason: String(reason) }
        );
      }
    }
    return;
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
    this._notify_change();
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
    this._notify_change();
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

// src/pyc-site-shell/sidebar/sidebar-keyboard.ts
var TYPE_TO_JUMP_RESET_MS = 1e3;
var ENTRY_SELECTOR = ".pyc-site-shell__sidebar-entry";
function attach_sidebar_keyboard(container) {
  const state = {
    buffer: "",
    last_keystroke_at_ms: 0
  };
  const handler = (event) => {
    _on_keydown(event, container, state);
  };
  container.addEventListener("keydown", handler);
  const detach = () => {
    container.removeEventListener("keydown", handler);
  };
  return detach;
}
function _on_keydown(event, container, state) {
  const entries = _collect_entries(container);
  if (entries.length === 0) {
    return;
  }
  const active_index = _resolve_active_index(entries, event.target);
  if (event.key === "ArrowDown") {
    event.preventDefault();
    const next_index = (active_index + 1) % entries.length;
    _move_focus(entries, next_index);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    const next_index = active_index <= 0 ? entries.length - 1 : active_index - 1;
    _move_focus(entries, next_index);
    return;
  }
  if (event.key === "Enter") {
    if (active_index >= 0 && active_index < entries.length) {
      event.preventDefault();
      entries[active_index].click();
    }
    return;
  }
  if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
    event.preventDefault();
    return;
  }
  if (_is_type_to_jump_key(event) === true) {
    const now_ms = Date.now();
    if (now_ms - state.last_keystroke_at_ms > TYPE_TO_JUMP_RESET_MS) {
      state.buffer = "";
    }
    state.buffer = state.buffer + event.key.toLowerCase();
    state.last_keystroke_at_ms = now_ms;
    const match_index = _find_prefix_match(entries, state.buffer);
    if (match_index >= 0) {
      event.preventDefault();
      _move_focus(entries, match_index);
    }
    return;
  }
  return;
}
function _is_type_to_jump_key(event) {
  if (event.ctrlKey === true || event.metaKey === true || event.altKey === true) {
    return false;
  }
  if (typeof event.key !== "string") {
    return false;
  }
  if (event.key.length !== 1) {
    return false;
  }
  const code = event.key.charCodeAt(0);
  if (code <= 32 || code >= 127) {
    return false;
  }
  return true;
}
function _collect_entries(container) {
  const node_list = container.querySelectorAll(ENTRY_SELECTOR);
  const rtnval = [];
  for (let index = 0; index < node_list.length; index = index + 1) {
    rtnval.push(node_list[index]);
  }
  return rtnval;
}
function _resolve_active_index(entries, target) {
  if (target instanceof HTMLElement) {
    const direct_index = entries.indexOf(target);
    if (direct_index >= 0) {
      return direct_index;
    }
  }
  for (let index = 0; index < entries.length; index = index + 1) {
    if (entries[index].getAttribute("tabindex") === "0") {
      return index;
    }
  }
  return -1;
}
function _move_focus(entries, next_index) {
  for (let index = 0; index < entries.length; index = index + 1) {
    const entry = entries[index];
    if (index === next_index) {
      entry.setAttribute("tabindex", "0");
      entry.focus();
    } else {
      entry.setAttribute("tabindex", "-1");
    }
  }
  return;
}
function _find_prefix_match(entries, prefix) {
  if (prefix.length === 0) {
    return -1;
  }
  for (let index = 0; index < entries.length; index = index + 1) {
    const label = (entries[index].textContent || "").trim().toLowerCase();
    if (label.startsWith(prefix) === true) {
      return index;
    }
  }
  return -1;
}
function initialize_sidebar_roving_tabindex(container) {
  const entries = _collect_entries(container);
  if (entries.length === 0) {
    return;
  }
  let anchor_index = -1;
  for (let index = 0; index < entries.length; index = index + 1) {
    if (entries[index].getAttribute("aria-current") === "page") {
      anchor_index = index;
      break;
    }
  }
  if (anchor_index < 0) {
    anchor_index = 0;
  }
  for (let index = 0; index < entries.length; index = index + 1) {
    const entry = entries[index];
    if (index === anchor_index) {
      entry.setAttribute("tabindex", "0");
    } else {
      entry.setAttribute("tabindex", "-1");
    }
  }
  return;
}

// src/pyc-site-shell/sidebar/sidebar-renderer.ts
var SidebarRenderer = class {
  _container;
  _on_navigate;
  _on_entry_clicked;
  _detach_keyboard;
  constructor(container, on_navigate, on_entry_clicked = null) {
    this._container = container;
    this._on_navigate = on_navigate;
    this._on_entry_clicked = on_entry_clicked;
    this._detach_keyboard = null;
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
    if (this._detach_keyboard !== null) {
      this._detach_keyboard();
      this._detach_keyboard = null;
    }
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
    initialize_sidebar_roving_tabindex(this._container);
    this._detach_keyboard = attach_sidebar_keyboard(this._container);
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
    link.setAttribute("tabindex", "-1");
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
      if (this._on_entry_clicked !== null) {
        this._on_entry_clicked(route, label);
      }
      this._on_navigate(route);
    });
    return link;
  }
};

// src/pyc-site-shell/sidebar/nav-manifest.ts
var DEFAULT_NAVIGATION_ENDPOINT = "/api/v1/me/navigation";
async function fetch_nav_manifest(endpoint = DEFAULT_NAVIGATION_ENDPOINT) {
  try {
    const response = await fetch(endpoint, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    if (response.ok === false) {
      const rtnval2 = {
        ok: false,
        manifest: null
      };
      return rtnval2;
    }
    const payload = await response.json();
    const manifest = _coerce_manifest(payload);
    if (manifest === null) {
      const rtnval2 = {
        ok: false,
        manifest: null
      };
      return rtnval2;
    }
    const rtnval = {
      ok: true,
      manifest
    };
    return rtnval;
  } catch (reason) {
    console.warn(
      "pychestrate.ui.shell.nav_manifest_fetch_failed",
      { endpoint, reason: String(reason) }
    );
    const rtnval = {
      ok: false,
      manifest: null
    };
    return rtnval;
  }
}
function apply_nav_manifest(registry, manifest) {
  if (manifest === null || Array.isArray(manifest.groups) === false) {
    return;
  }
  for (const group of manifest.groups) {
    if (group === null || typeof group.group_id !== "string" || group.group_id.length === 0) {
      continue;
    }
    registry.registerGroup({
      groupId: group.group_id,
      label: typeof group.label === "string" ? group.label : group.group_id,
      icon: group.icon !== void 0 ? group.icon : null,
      requiredPermissions: []
    });
    if (Array.isArray(group.entries) === false) {
      continue;
    }
    for (const entry of group.entries) {
      if (entry === null || typeof entry.route !== "string" || entry.route.length === 0) {
        continue;
      }
      registry.registerEntry({
        entryId: typeof entry.entry_id === "string" ? entry.entry_id : entry.route,
        label: typeof entry.label === "string" ? entry.label : entry.route,
        route: entry.route,
        icon: entry.icon !== void 0 ? entry.icon : null,
        requiredPermissions: [],
        group: group.group_id
      });
    }
  }
  return;
}
function _coerce_manifest(payload) {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const candidate = payload;
  if (Array.isArray(candidate.groups) === false) {
    return null;
  }
  const rtnval = {
    groups: candidate.groups
  };
  return rtnval;
}

// src/pyc-site-shell/observability/metrics-beacon.ts
var DEFAULT_METRICS_ENDPOINT = "/api/v1/_metrics/ui";
var DEFAULT_BUFFER_CAPACITY = 100;
var DEFAULT_FLUSH_WINDOW_MS = 3e4;
var MetricsBeacon = class {
  _endpoint;
  _buffer_capacity;
  _flush_window_ms;
  _now;
  _send_beacon;
  _buffer;
  _disabled_reason;
  _pagehide_handler;
  constructor(options = null) {
    const opts = options !== null ? options : {};
    this._endpoint = typeof opts.endpoint === "string" && opts.endpoint.length > 0 ? opts.endpoint : DEFAULT_METRICS_ENDPOINT;
    this._buffer_capacity = typeof opts.bufferCapacity === "number" && opts.bufferCapacity > 0 ? opts.bufferCapacity : DEFAULT_BUFFER_CAPACITY;
    this._flush_window_ms = typeof opts.flushWindowMs === "number" && opts.flushWindowMs > 0 ? opts.flushWindowMs : DEFAULT_FLUSH_WINDOW_MS;
    this._now = typeof opts.now === "function" ? opts.now : () => {
      if (typeof performance !== "undefined") {
        return performance.now();
      }
      return Date.now();
    };
    const provided_sender = opts.sendBeacon;
    if (typeof provided_sender === "function") {
      this._send_beacon = provided_sender;
    } else if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      const bound = (url, body) => {
        const result = navigator.sendBeacon(url, body);
        return result;
      };
      this._send_beacon = bound;
    } else {
      this._send_beacon = null;
    }
    this._buffer = [];
    this._disabled_reason = null;
    this._pagehide_handler = null;
  }
  /**
   * Wire ``pagehide`` so the buffer is flushed when the user
   * navigates away. Optional -- the shell calls this once after
   * construction. Returns a detach handle.
   */
  attachLifecycle() {
    if (typeof window === "undefined") {
      const noop = () => {
        return;
      };
      return noop;
    }
    const handler = () => {
      this.flush();
    };
    window.addEventListener("pagehide", handler);
    this._pagehide_handler = handler;
    const detach = () => {
      if (this._pagehide_handler !== null) {
        window.removeEventListener("pagehide", this._pagehide_handler);
        this._pagehide_handler = null;
      }
    };
    return detach;
  }
  /**
   * Record a histogram observation (seconds).
   *
   * @param metric Metric name (must match the design.md catalog).
   * @param seconds Observation value in seconds.
   * @param labels Optional label dictionary; values must be
   *               strings. Pass ``null`` for unlabeled metrics.
   */
  observeHistogram(metric, seconds, labels = null) {
    if (this._disabled_reason !== null) {
      return;
    }
    if (typeof metric !== "string" || metric.length === 0) {
      return;
    }
    if (typeof seconds !== "number" || Number.isFinite(seconds) === false) {
      return;
    }
    const entry = {
      metric,
      value: seconds,
      labels: labels !== null ? labels : null,
      timestamp_ms: Date.now()
    };
    this._buffer.push(entry);
    this._maybe_flush();
    return;
  }
  /**
   * Increment a counter metric by 1 (or the supplied amount).
   */
  incrementCounter(metric, labels = null, amount = 1) {
    if (this._disabled_reason !== null) {
      return;
    }
    if (typeof metric !== "string" || metric.length === 0) {
      return;
    }
    const value = typeof amount === "number" && Number.isFinite(amount) === true ? amount : 1;
    const entry = {
      metric,
      value,
      labels: labels !== null ? labels : null,
      timestamp_ms: Date.now()
    };
    this._buffer.push(entry);
    this._maybe_flush();
    return;
  }
  /**
   * Flush the current buffer to the backend. Drops the buffer
   * after the call regardless of delivery outcome -- there is
   * no retry queue.
   */
  flush() {
    if (this._buffer.length === 0) {
      return;
    }
    const batch = this._buffer;
    this._buffer = [];
    if (this._send_beacon === null) {
      return;
    }
    const payload = JSON.stringify(batch);
    try {
      const delivered = this._send_beacon(this._endpoint, payload);
      if (delivered === false) {
        this._disabled_reason = "sendBeacon_refused";
        console.warn(
          "pychestrate.ui.shell.metrics_beacon_disabled",
          { reason: this._disabled_reason }
        );
      }
    } catch (reason) {
      this._disabled_reason = "sendBeacon_threw";
      console.warn(
        "pychestrate.ui.shell.metrics_beacon_disabled",
        { reason: String(reason) }
      );
    }
    return;
  }
  /**
   * Permanently disable this beacon (e.g. after a 404 on the
   * endpoint) and drop any buffered entries.
   */
  disable(reason) {
    this._disabled_reason = reason;
    this._buffer = [];
    return;
  }
  /**
   * Diagnostic accessor for tests.
   */
  bufferLength() {
    const rtnval = this._buffer.length;
    return rtnval;
  }
  /**
   * Diagnostic accessor for tests.
   */
  get disabledReason() {
    const rtnval = this._disabled_reason;
    return rtnval;
  }
  _maybe_flush() {
    if (this._buffer.length >= this._buffer_capacity) {
      this.flush();
      return;
    }
    if (this._buffer.length > 0) {
      const oldest = this._buffer[0];
      const age_ms = Date.now() - oldest.timestamp_ms;
      if (age_ms >= this._flush_window_ms) {
        this.flush();
        return;
      }
    }
    return;
  }
};
var SHELL_METRICS = {
  TTI: "pychestrate_ui_shell_tti_seconds",
  SIDEBAR_RENDER: "pychestrate_ui_shell_sidebar_render_duration_seconds",
  PERMISSION_REFETCH: "pychestrate_ui_shell_navigation_permission_refetch_seconds",
  PALETTE_OPEN: "pychestrate_ui_shell_palette_open_duration_seconds",
  PALETTE_FANOUT: "pychestrate_ui_shell_palette_fanout_duration_seconds",
  SIDEBAR_ENTRY_CLICKED: "pychestrate_ui_shell_sidebar_entry_clicked_total"
};

// src/pyc-site-shell/pyc-site-shell.ts
var ATTR_INITIAL_ROUTE = "initial-route";
var ATTR_PERMISSIONS_ENDPOINT = "permissions-endpoint";
var ATTR_NAVIGATION_ENDPOINT = "navigation-endpoint";
var ATTR_PALETTE_TIMEOUT_MS = "palette-timeout-ms";
var ATTR_BRAND_LABEL = "brand-label";
var PycSiteShell = class extends HTMLElement {
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
};

// src/pyc-site-shell/index.ts
var TAG_NAME = "pyc-site-shell";
if (typeof customElements !== "undefined") {
  if (customElements.get(TAG_NAME) === void 0) {
    customElements.define(TAG_NAME, PycSiteShell);
  }
}
export {
  DEFAULT_METRICS_ENDPOINT,
  DEFAULT_NAVIGATION_ENDPOINT,
  MetricsBeacon,
  PaletteDialog,
  PaletteRegistry,
  PermissionCache,
  PermissionSet,
  PycSiteShell,
  SHELL_METRICS,
  SidebarRegistry,
  apply_nav_manifest,
  attach_sidebar_keyboard,
  fetch_nav_manifest,
  initialize_sidebar_roving_tabindex
};
//# sourceMappingURL=pyc-site-shell.js.map
