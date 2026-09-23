import { load_failure_message, read_required_permission } from "./feature-flags-view.js";
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
class PycExtensionRegistry extends HTMLElement {
  _extensions;
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
    const heading = document.createElement("h1");
    heading.classList.add("pyc-admin__heading");
    heading.textContent = "Extension Registry";
    root.appendChild(heading);
    const lede = document.createElement("p");
    lede.classList.add("pyc-admin__lede");
    lede.textContent = "Loaded extensions with precedence, capabilities and route-mount health.";
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
      const empty = document.createElement("p");
      empty.classList.add("pyc-admin__notice");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No extensions contribute REST routes.";
      region.replaceChildren(empty);
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
      document.createTextNode("Registry status: ")
    );
    const status_badge = document.createElement("mj-chip");
    status_badge.classList.add("pyc-admin__badge");
    status_badge.setAttribute(
      "data-tone",
      mount_state_tone(this._mountState)
    );
    status_badge.textContent = this._mountState.length > 0 ? this._mountState : "unknown";
    registry_status.appendChild(status_badge);
    region.replaceChildren(registry_status, table);
    return;
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
  mount_state_tone
};
