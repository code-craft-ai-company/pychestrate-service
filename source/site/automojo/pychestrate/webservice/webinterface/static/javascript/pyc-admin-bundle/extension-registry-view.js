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
  _table_region;
  _detail_region;
  constructor() {
    super();
    this._extensions = [];
    this._mountState = "";
    this._loading = false;
    this._errored = false;
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
    const refresh_button = document.createElement("button");
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
    this._render_table();
    let listing = null;
    try {
      const response = await fetch(EXT_LISTING_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
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
      error.textContent = "Failed to load the extension registry. Try refreshing.";
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
    const table = document.createElement("table");
    table.classList.add("pyc-admin__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = [
      "Precedence",
      "Extension",
      "Routes",
      "Capabilities",
      "Health",
      "Actions"
    ];
    for (const column of columns) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column;
      head_row.appendChild(th);
    }
    thead.appendChild(head_row);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const extension of this._extensions) {
      tbody.appendChild(this._build_row(extension));
    }
    table.appendChild(tbody);
    region.replaceChildren(table);
    return;
  }
  _build_row(extension) {
    const row = document.createElement("tr");
    row.setAttribute("data-ext-name", extension.extName);
    const precedence_cell = document.createElement("td");
    precedence_cell.textContent = String(extension.precedence);
    row.appendChild(precedence_cell);
    const name_cell = document.createElement("td");
    name_cell.textContent = extension.extName;
    row.appendChild(name_cell);
    const routes_cell = document.createElement("td");
    routes_cell.textContent = String(extension.routeCount);
    row.appendChild(routes_cell);
    const capabilities_cell = document.createElement("td");
    if (extension.capabilities.length === 0) {
      capabilities_cell.textContent = "\u2014";
    } else {
      capabilities_cell.textContent = extension.capabilities.join(", ");
    }
    row.appendChild(capabilities_cell);
    const health_cell = document.createElement("td");
    const health_badge = document.createElement("span");
    health_badge.classList.add("pyc-admin__badge");
    health_badge.setAttribute(
      "data-tone",
      mount_state_tone(this._mountState)
    );
    health_badge.textContent = this._mountState.length > 0 ? this._mountState : "unknown";
    health_cell.appendChild(health_badge);
    row.appendChild(health_cell);
    const actions_cell = document.createElement("td");
    const detail_button = document.createElement("button");
    detail_button.classList.add("pyc-admin__toggle");
    detail_button.setAttribute("type", "button");
    detail_button.setAttribute("data-role", "show-routes");
    detail_button.textContent = "Show Routes";
    detail_button.addEventListener("click", () => {
      this._render_detail(extension);
    });
    actions_cell.appendChild(detail_button);
    row.appendChild(actions_cell);
    return row;
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
    const table = document.createElement("table");
    table.classList.add("pyc-admin__table");
    table.setAttribute("data-role", "route-detail");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    for (const column of ["Method", "Path", "Permissions", "Handler"]) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column;
      head_row.appendChild(th);
    }
    thead.appendChild(head_row);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const route of extension.routes) {
      const route_row = document.createElement("tr");
      const method_cell = document.createElement("td");
      method_cell.textContent = route.method;
      route_row.appendChild(method_cell);
      const path_cell = document.createElement("td");
      path_cell.classList.add("pyc-admin__mono");
      path_cell.textContent = route.full_path;
      route_row.appendChild(path_cell);
      const perms_cell = document.createElement("td");
      perms_cell.textContent = route.required_permissions.length > 0 ? route.required_permissions.join(", ") : "\u2014";
      route_row.appendChild(perms_cell);
      const handler_cell = document.createElement("td");
      handler_cell.classList.add("pyc-admin__mono");
      handler_cell.textContent = route.handler_class;
      route_row.appendChild(handler_cell);
      tbody.appendChild(route_row);
    }
    table.appendChild(tbody);
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
