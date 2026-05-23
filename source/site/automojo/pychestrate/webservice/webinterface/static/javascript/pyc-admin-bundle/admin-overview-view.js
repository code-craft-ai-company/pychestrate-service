import {
  fetch_system_health,
  health_status_tone
} from "./system-health-view.js";
import {
  FLAGS_PATH,
  flag_state_tone,
  next_flag_state,
  build_flag_url,
  FLAG_STATE_ENABLED,
  FLAG_STATE_RETIRED
} from "./feature-flags-view.js";
import {
  EXT_LISTING_PATH,
  group_routes_by_extension
} from "./extension-registry-view.js";
const SYSTEM_HEALTH_ROUTE = "/admin/system-health";
const FEATURE_FLAGS_ROUTE = "/admin/feature-flags";
const EXTENSION_REGISTRY_ROUTE = "/admin/extensions";
const QUICK_FLAG_LIMIT = 8;
class PycAdminOverview extends HTMLElement {
  _loading;
  _health;
  _flags;
  _flagsErrored;
  _healthErrored;
  _extensionCount;
  _extensionsErrored;
  _health_region;
  _flags_region;
  _ext_region;
  constructor() {
    super();
    this._loading = false;
    this._health = null;
    this._flags = [];
    this._flagsErrored = false;
    this._healthErrored = false;
    this._extensionCount = 0;
    this._extensionsErrored = false;
    this._health_region = null;
    this._flags_region = null;
    this._ext_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to read the loading
   * flag without scraping the DOM.
   */
  get loading() {
    const rtnval = this._loading;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * three composing fetches when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-admin");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-admin__heading");
    heading.textContent = "Administration";
    root.appendChild(heading);
    const lede = document.createElement("p");
    lede.classList.add("pyc-admin__lede");
    lede.textContent = "System health, feature flags and the extension registry at a glance.";
    root.appendChild(lede);
    const controls = document.createElement("div");
    controls.classList.add("pyc-admin__controls");
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-admin__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const tiles = document.createElement("div");
    tiles.classList.add("pyc-admin__tiles");
    const health_region = document.createElement("div");
    health_region.classList.add("pyc-admin__tile");
    health_region.setAttribute("data-role", "health-tile");
    tiles.appendChild(health_region);
    this._health_region = health_region;
    const ext_region = document.createElement("div");
    ext_region.classList.add("pyc-admin__tile");
    ext_region.setAttribute("data-role", "extension-tile");
    tiles.appendChild(ext_region);
    this._ext_region = ext_region;
    root.appendChild(tiles);
    const flags_heading = document.createElement("h2");
    flags_heading.classList.add("pyc-admin__subheading");
    flags_heading.textContent = "Feature Flags";
    root.appendChild(flags_heading);
    const flags_region = document.createElement("div");
    flags_region.setAttribute("data-role", "flags-region");
    root.appendChild(flags_region);
    this._flags_region = flags_region;
    this.replaceChildren(root);
    return;
  }
  /**
   * Refresh all three composing sections. Exposed so unit tests
   * can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._render_health();
    this._render_extensions();
    this._render_flags();
    await Promise.all([
      this._load_health(),
      this._load_flags(),
      this._load_extensions()
    ]);
    this._loading = false;
    this._render_health();
    this._render_extensions();
    this._render_flags();
    return;
  }
  async _load_health() {
    this._healthErrored = false;
    const document_body = await fetch_system_health();
    if (document_body === null) {
      this._healthErrored = true;
      this._health = null;
      return;
    }
    this._health = document_body;
    return;
  }
  async _load_flags() {
    this._flagsErrored = false;
    let entries = null;
    try {
      const response = await fetch(FLAGS_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        if (Array.isArray(body) === true) {
          entries = body;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.overview_flags_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (entries === null) {
      this._flagsErrored = true;
      this._flags = [];
      return;
    }
    const ordered = entries.slice();
    ordered.sort(
      (left, right) => {
        if (left.flag_key < right.flag_key) {
          return -1;
        }
        if (left.flag_key > right.flag_key) {
          return 1;
        }
        return 0;
      }
    );
    this._flags = ordered;
    return;
  }
  async _load_extensions() {
    this._extensionsErrored = false;
    let listing = null;
    try {
      const response = await fetch(EXT_LISTING_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const parsed = body;
        if (parsed !== null && Array.isArray(parsed.items) === true) {
          listing = parsed;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.overview_ext_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (listing === null) {
      this._extensionsErrored = true;
      this._extensionCount = 0;
      return;
    }
    const grouped = group_routes_by_extension(listing.items);
    this._extensionCount = grouped.length;
    return;
  }
  _render_health() {
    if (this._health_region === null) {
      return;
    }
    const region = this._health_region;
    const children = [];
    const title = document.createElement("p");
    title.classList.add("pyc-admin__tile-title");
    title.textContent = "System Health";
    children.push(title);
    if (this._loading === true && this._health === null && this._healthErrored === false) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__tile-detail");
      loading.setAttribute("data-role", "health-loading");
      loading.textContent = "Loading\u2026";
      children.push(loading);
      region.replaceChildren(...children);
      return;
    }
    if (this._healthErrored === true || this._health === null) {
      const error = document.createElement("p");
      error.classList.add("pyc-admin__tile-detail");
      error.setAttribute("data-role", "health-error");
      error.textContent = "System health unavailable.";
      children.push(error);
      region.replaceChildren(...children);
      return;
    }
    const value = document.createElement("p");
    value.classList.add("pyc-admin__tile-value");
    const value_badge = document.createElement("mj-chip");
    value_badge.classList.add("pyc-admin__badge");
    value_badge.setAttribute(
      "data-tone",
      health_status_tone(this._health.status)
    );
    value_badge.setAttribute("data-role", "health-status");
    value_badge.textContent = this._health.status;
    value.appendChild(value_badge);
    children.push(value);
    for (const subsystem of this._health.subsystems) {
      const sub = document.createElement("p");
      sub.classList.add("pyc-admin__tile-detail");
      const sub_badge = document.createElement("mj-chip");
      sub_badge.classList.add("pyc-admin__badge");
      sub_badge.setAttribute(
        "data-tone",
        health_status_tone(subsystem.status)
      );
      sub_badge.textContent = subsystem.status;
      sub.appendChild(sub_badge);
      sub.appendChild(
        document.createTextNode(" " + subsystem.label)
      );
      children.push(sub);
    }
    const link = document.createElement("a");
    link.classList.add("pyc-admin__link");
    link.setAttribute("href", SYSTEM_HEALTH_ROUTE);
    link.setAttribute("data-role", "health-link");
    link.textContent = "Open system health \u2192";
    children.push(link);
    region.replaceChildren(...children);
    return;
  }
  _render_extensions() {
    if (this._ext_region === null) {
      return;
    }
    const region = this._ext_region;
    const children = [];
    const title = document.createElement("p");
    title.classList.add("pyc-admin__tile-title");
    title.textContent = "Extension Registry";
    children.push(title);
    if (this._loading === true && this._extensionCount === 0 && this._extensionsErrored === false) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__tile-detail");
      loading.setAttribute("data-role", "extension-loading");
      loading.textContent = "Loading\u2026";
      children.push(loading);
      region.replaceChildren(...children);
      return;
    }
    if (this._extensionsErrored === true) {
      const error = document.createElement("p");
      error.classList.add("pyc-admin__tile-detail");
      error.setAttribute("data-role", "extension-error");
      error.textContent = "Extension registry unavailable.";
      children.push(error);
      region.replaceChildren(...children);
      return;
    }
    const value = document.createElement("p");
    value.classList.add("pyc-admin__tile-value");
    value.setAttribute("data-role", "extension-count");
    value.textContent = String(this._extensionCount);
    children.push(value);
    const detail = document.createElement("p");
    detail.classList.add("pyc-admin__tile-detail");
    detail.textContent = this._extensionCount === 1 ? "loaded extension" : "loaded extensions";
    children.push(detail);
    const link = document.createElement("a");
    link.classList.add("pyc-admin__link");
    link.setAttribute("href", EXTENSION_REGISTRY_ROUTE);
    link.setAttribute("data-role", "extension-link");
    link.textContent = "Open extension registry \u2192";
    children.push(link);
    region.replaceChildren(...children);
    return;
  }
  _render_flags() {
    if (this._flags_region === null) {
      return;
    }
    const region = this._flags_region;
    if (this._loading === true && this._flags.length === 0 && this._flagsErrored === false) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__notice");
      loading.setAttribute("data-role", "flags-loading");
      loading.textContent = "Loading feature flags\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._flagsErrored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-admin__notice",
        "pyc-admin__notice--error"
      );
      error.setAttribute("data-role", "flags-error");
      error.textContent = "Failed to load feature flags.";
      region.replaceChildren(error);
      return;
    }
    if (this._flags.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-admin__notice");
      empty.setAttribute("data-role", "flags-empty");
      empty.textContent = "No feature flags registered.";
      region.replaceChildren(empty);
      return;
    }
    const children = [];
    const self = this;
    const shown = this._flags.slice(0, QUICK_FLAG_LIMIT);
    const table = document.createElement("mj-table");
    table.classList.add("pyc-admin__table");
    table.rowAttrs = (entry) => ({ "data-flag-key": entry.flag_key });
    table.columns = [
      { key: "flag_key", label: "Flag Key" },
      {
        key: "state",
        label: "State",
        render: (entry) => {
          const state_badge = document.createElement("mj-chip");
          state_badge.classList.add("pyc-admin__badge");
          state_badge.setAttribute("data-tone", flag_state_tone(entry.state));
          state_badge.textContent = entry.state ?? "—";
          return state_badge;
        }
      },
      {
        key: "actions",
        label: "Actions",
        render: (entry) => self._build_flag_toggle(entry)
      }
    ];
    table.rows = shown;
    children.push(table);
    if (this._flags.length > QUICK_FLAG_LIMIT) {
      const more = document.createElement("p");
      more.classList.add("pyc-admin__tile-detail");
      more.textContent = "Showing " + String(QUICK_FLAG_LIMIT) + " of " + String(this._flags.length) + " flags.";
      children.push(more);
    }
    const link = document.createElement("a");
    link.classList.add("pyc-admin__link");
    link.setAttribute("href", FEATURE_FLAGS_ROUTE);
    link.setAttribute("data-role", "flags-link");
    link.textContent = "Manage all feature flags \u2192";
    children.push(link);
    region.replaceChildren(...children);
    return;
  }
  _build_flag_toggle(entry) {
    const is_retired = typeof entry.state === "string" && entry.state.toLowerCase() === FLAG_STATE_RETIRED;
    const toggle = document.createElement("mj-button");
    toggle.classList.add("pyc-admin__toggle");
    toggle.setAttribute("type", "button");
    toggle.setAttribute("data-role", "toggle");
    const target = next_flag_state(entry.state);
    toggle.textContent = target === FLAG_STATE_ENABLED ? "Enable" : "Disable";
    if (is_retired === true) {
      toggle.toggleAttribute("disabled", true);
    }
    toggle.addEventListener("click", () => {
      toggle.toggleAttribute("disabled", true);
      void this._on_toggle(entry, toggle);
    });
    return toggle;
  }
  async _on_toggle(entry, toggle) {
    const target = next_flag_state(entry.state);
    const ok = await this.toggleFlag(entry.flag_key, target);
    toggle.toggleAttribute("disabled", false);
    if (ok === true) {
      await this._load_flags();
      this._render_flags();
    }
    return;
  }
  /**
   * PATCH a flag's state from the quick-view list. Exposed so
   * unit tests can invoke a toggle without a real click event.
   *
   * @param flag_key The flag to update.
   * @param target_state The desired flag-state value.
   *
   * @returns ``true`` when the PATCH succeeded.
   */
  async toggleFlag(flag_key, target_state) {
    let ok = false;
    try {
      const response = await fetch(build_flag_url(flag_key), {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ state: target_state })
      });
      ok = response.status === 200;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.overview_flag_toggle_failed",
        { reason: String(reason) }
      );
    }
    const rtnval = ok;
    return rtnval;
  }
}
export {
  EXTENSION_REGISTRY_ROUTE,
  FEATURE_FLAGS_ROUTE,
  PycAdminOverview,
  QUICK_FLAG_LIMIT,
  SYSTEM_HEALTH_ROUTE
};
