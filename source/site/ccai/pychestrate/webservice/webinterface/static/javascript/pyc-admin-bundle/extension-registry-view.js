import { load_failure_message, read_required_permission } from "./feature-flags-view.js";
import { build_empty_state } from "../shared/empty-state.js";
const EXT_LISTING_PATH = "/api/v1/ext";
function group_routes_by_extension(routes) {
  const buckets = /* @__PURE__ */ new Map();
  for (const route of routes) {
    const existing = buckets.get(route.ext_name);
    if (existing === void 0) {
      buckets.set(route.ext_name, [route]);
    } else {
      existing.push(route);
    }
  }
  const ext_names = Array.from(buckets.keys());
  ext_names.sort();
  const summaries = [];
  let precedence = 0;
  for (const ext_name of ext_names) {
    const ext_routes = buckets.get(ext_name);
    if (ext_routes === void 0) {
      continue;
    }
    const capability_set = /* @__PURE__ */ new Set();
    for (const route of ext_routes) {
      for (const capability of route.required_capabilities) {
        capability_set.add(capability);
      }
    }
    const capabilities = Array.from(capability_set);
    capabilities.sort();
    summaries.push({
      extName: ext_name,
      precedence,
      routeCount: ext_routes.length,
      capabilities,
      routes: ext_routes
    });
    precedence = precedence + 1;
  }
  const rtnval = summaries;
  return rtnval;
}
function mount_state_tone(dynamic_mount) {
  if (typeof dynamic_mount !== "string") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const lowered = dynamic_mount.toLowerCase();
  if (lowered === "mounted") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "deferred") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "error";
  return rtnval;
}
/**
 * Say in words whether the extensions' routes are being served. The API reports ``mounted`` once the routes are attached
 * and ``deferred`` before that; "deferred" meant nothing to a person reading the page.
 *
 * @param dynamic_mount The listing's ``dynamic_mount`` value.
 *
 * @returns ``{label, hint}``: the chip's text and what it means.
 */
function mount_state_words(dynamic_mount) {
  const lowered = typeof dynamic_mount === "string" ? dynamic_mount.toLowerCase() : "";
  if (lowered === "mounted") {
    return { label: "Serving", hint: "The routes the extensions add are attached and being served." };
  }
  if (lowered === "deferred") {
    return { label: "Not attached yet", hint: "The extensions are loaded but the routes they add are not attached to the web service yet, so they are not being served." };
  }
  return { label: "Unknown", hint: "The service did not say whether the extensions' routes are attached." };
}
/**
 * The installed extension packs the listing reports, as ``{name, target, loaded, error}`` rows; anything else in the list is dropped.
 */
function clean_packs(packs) {
  if (Array.isArray(packs) === false) {
    return [];
  }
  return packs.filter((pack) => pack !== null && typeof pack === "object" && typeof pack.name === "string" && pack.name.length > 0).map((pack) => ({
    name: pack.name,
    target: typeof pack.target === "string" ? pack.target : "",
    loaded: pack.loaded === true,
    error: typeof pack.error === "string" ? pack.error : ""
  }));
}
class PycExtensionRegistry extends HTMLElement {
  _extensions;
  _packs;
  _packsEnabled;
  _mountState;
  _loading;
  _errored;
  _error_status;
  _error_permission;
  _table_region;
  _detail_region;
  constructor() {
    super();
    this._extensions = [];
    this._packs = [];
    this._packsEnabled = true;
    this._mountState = "";
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._error_permission = "";
    this._table_region = null;
    this._detail_region = null;
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
   * Diagnostic accessor used by unit tests to read the errored
   * flag without scraping the DOM.
   */
  get errored() {
    const rtnval = this._errored;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * manifest fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-admin");
    const header = document.createElement("div");
    header.classList.add("pyc-admin__header");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-admin__heading");
    heading.textContent = "Extension Registry";
    header.appendChild(heading);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-admin__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("variant", "tertiary");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    header.appendChild(refresh_button);
    root.appendChild(header);
    const lede = document.createElement("p");
    lede.classList.add("pyc-admin__lede");
    lede.textContent = "Loaded extensions with precedence, capabilities and route-mount health.";
    root.appendChild(lede);
    const table_region = document.createElement("div");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const detail_region = document.createElement("div");
    detail_region.setAttribute("data-role", "detail-region");
    root.appendChild(detail_region);
    this._detail_region = detail_region;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the extension manifest and re-render. Exposed so unit
   * tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_table();
    let listing = null;
    try {
      const response = await fetch(EXT_LISTING_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        this._error_status = response.status;
        if (response.status === 403) {
          this._error_permission = await read_required_permission(response);
        }
        throw new Error(
          "ext manifest fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      const parsed = body;
      if (parsed !== null && Array.isArray(parsed.items) === true) {
        listing = parsed;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.ext_manifest_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (listing === null) {
      this._loading = false;
      this._errored = true;
      this._render_table();
      return;
    }
    this._extensions = group_routes_by_extension(listing.items);
    this._packs = clean_packs(listing.packs);
    this._packsEnabled = listing.packs_enabled !== false;
    this._mountState = listing.dynamic_mount;
    this._loading = false;
    this._errored = false;
    this._render_table();
    return;
  }
  _render_table() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading extension registry\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-admin__notice",
        "pyc-admin__notice--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = load_failure_message(
        this._error_status,
        "the extension registry",
        this._error_permission
      );
      region.replaceChildren(error);
      return;
    }
    if (this._extensions.length === 0) {
      const empty = build_empty_state({ class_name: "pyc-admin__notice", message: "No extensions contribute REST routes." });
      region.replaceChildren(this._build_packs_block(), empty);
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-admin__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-admin__row";
    table.rowAttrs = (extension) => ({ "data-ext-name": extension.extName });
    table.columns = [
      {
        key: "precedence",
        label: "Precedence",
        width: "8rem",
        render: (extension) => String(extension.precedence)
      },
      { key: "extName", label: "Extension", width: "16rem" },
      {
        key: "routeCount",
        label: "Routes",
        width: "8rem",
        render: (extension) => String(extension.routeCount)
      },
      {
        key: "capabilities",
        label: "Capabilities",
        width: "16rem",
        sortable: false,
        render: (extension) => {
          if (extension.capabilities.length === 0) {
            return "\u2014";
          }
          return extension.capabilities.join(", ");
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "10rem",
        sortable: false,
        render: (extension) => {
          const detail_button = document.createElement("mj-button");
          detail_button.classList.add("pyc-admin__toggle");
          detail_button.setAttribute("type", "button");
          detail_button.setAttribute("data-role", "show-routes");
          detail_button.textContent = "Show Routes";
          detail_button.addEventListener("click", () => {
            self._render_detail(extension);
          });
          return detail_button;
        }
      }
    ];
    table.rows = this._extensions;
    // The dynamic-mount state is one listing-wide value, so it
    // renders once here instead of repeating in a per-row column.
    const registry_status = document.createElement("p");
    registry_status.classList.add("pyc-admin__lede");
    registry_status.setAttribute("data-role", "registry-status");
    registry_status.appendChild(
      document.createTextNode("Extension routes: ")
    );
    const status_badge = document.createElement("mj-chip");
    status_badge.classList.add("pyc-admin__badge");
    status_badge.setAttribute(
      "data-tone",
      mount_state_tone(this._mountState)
    );
    const mount_words = mount_state_words(this._mountState);
    status_badge.textContent = mount_words.label;
    status_badge.setAttribute("title", mount_words.hint);
    registry_status.appendChild(status_badge);
    region.replaceChildren(registry_status, this._build_packs_block(), table);
    return;
  }
  /**
   * The installed extension packs and what became of each at startup. A pack that did not load is named with its error:
   * the service starts without it, so this is the only place besides the log where a person can see that it is missing.
   */
  _build_packs_block() {
    const block = document.createElement("section");
    block.classList.add("pyc-admin__packs");
    block.setAttribute("data-role", "packs");
    block.setAttribute("aria-label", "Extension packs");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-admin__subheading");
    heading.textContent = "Extension packs";
    block.appendChild(heading);
    const note = (text, role, error) => {
      const line = document.createElement("p");
      line.classList.add("pyc-admin__lede");
      if (error === true) {
        line.classList.add("pyc-admin__notice", "pyc-admin__notice--error");
      }
      line.setAttribute("data-role", role);
      line.textContent = text;
      block.appendChild(line);
    };
    if (this._packsEnabled === false) {
      note("Loading installed extension packs is turned off on this service, so none were loaded.", "packs-off", false);
      return block;
    }
    if (this._packs.length === 0) {
      note("No extension packs are installed.", "packs-none", false);
      return block;
    }
    const failed = this._packs.filter((pack) => pack.loaded !== true).length;
    const total = this._packs.length;
    const noun = total === 1 ? "pack" : "packs";
    if (failed === 0) {
      note(total === 1 ? "The installed pack loaded." : "All " + String(total) + " installed packs loaded.", "packs-summary", false);
    } else {
      note(String(failed) + " of " + String(total) + " installed " + noun + " did not load. The service started without " + (failed === 1 ? "it" : "them") + ".", "packs-summary", true);
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-admin__pack-list");
    list.setAttribute("data-role", "pack-list");
    for (const pack of this._packs) {
      const item = document.createElement("li");
      item.classList.add("pyc-admin__pack");
      item.setAttribute("data-role", "pack-row");
      item.setAttribute("data-state", pack.loaded === true ? "loaded" : "failed");
      const name = document.createElement("strong");
      name.textContent = pack.name;
      item.appendChild(name);
      const chip = document.createElement("mj-chip");
      chip.classList.add("pyc-admin__badge");
      chip.setAttribute("data-tone", pack.loaded === true ? "ok" : "error");
      chip.textContent = pack.loaded === true ? "Loaded" : "Did not load";
      item.appendChild(chip);
      if (pack.target.length > 0) {
        const target = document.createElement("code");
        target.classList.add("pyc-admin__pack-target");
        target.textContent = pack.target;
        item.appendChild(target);
      }
      if (pack.loaded !== true && pack.error.length > 0) {
        const reason = document.createElement("span");
        reason.classList.add("pyc-admin__pack-error");
        reason.setAttribute("data-role", "pack-error");
        reason.textContent = pack.error;
        item.appendChild(reason);
      }
      list.appendChild(item);
    }
    block.appendChild(list);
    return block;
  }
  _render_detail(extension) {
    if (this._detail_region === null) {
      return;
    }
    const region = this._detail_region;
    const heading = document.createElement("h2");
    heading.classList.add("pyc-admin__subheading");
    heading.textContent = "Routes \u2014 " + extension.extName;
    const mount_note = document.createElement("p");
    mount_note.classList.add("pyc-admin__lede");
    mount_note.textContent = "Dynamic-mount state: " + (this._mountState.length > 0 ? this._mountState : "unknown");
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-admin__table");
    table.classList.add("pyc-admin__table--embedded");
    table.setAttribute("data-role", "route-detail");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-admin__row";
    table.columns = [
      { key: "method", label: "Method", width: "8rem" },
      {
        key: "full_path",
        label: "Path",
        width: "20rem",
        render: (route) => {
          const path_cell = document.createElement("span");
          path_cell.classList.add("pyc-admin__mono");
          path_cell.textContent = route.full_path;
          return path_cell;
        }
      },
      {
        key: "required_permissions",
        label: "Permissions",
        width: "16rem",
        sortable: false,
        render: (route) => route.required_permissions.length > 0 ? route.required_permissions.join(", ") : "\u2014"
      },
      {
        key: "handler_class",
        label: "Handler",
        width: "20rem",
        render: (route) => {
          const handler_cell = document.createElement("span");
          handler_cell.classList.add("pyc-admin__mono");
          handler_cell.textContent = route.handler_class;
          return handler_cell;
        }
      }
    ];
    table.rows = extension.routes;
    region.replaceChildren(heading, mount_note, table);
    return;
  }
}
export {
  EXT_LISTING_PATH,
  PycExtensionRegistry,
  group_routes_by_extension,
  mount_state_tone,
  mount_state_words
};
