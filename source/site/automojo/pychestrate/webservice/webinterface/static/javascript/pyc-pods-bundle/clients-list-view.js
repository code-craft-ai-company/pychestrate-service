const CLIENT_STATUSES = [
  "ACTIVE",
  "SUSPENDED",
  "REVOKED"
];
const LIVENESS_STATES = [
  "ALIVE",
  "DEGRADED",
  "LOST"
];
const DEFAULT_PER_PAGE = 25;
const CLIENTS_API_PATH = "/api/v1/clients";
function build_clients_query_url(state) {
  const params = new URLSearchParams();
  if (state.projectFilter.length > 0) {
    params.set("project_id", state.projectFilter);
  }
  if (state.statusFilter.length > 0) {
    params.set("status", state.statusFilter);
  }
  if (state.livenessFilter.length > 0) {
    params.set("liveness_state", state.livenessFilter);
  }
  const query = params.toString();
  if (query.length === 0) {
    const rtnval2 = CLIENTS_API_PATH;
    return rtnval2;
  }
  const rtnval = CLIENTS_API_PATH + "?" + query;
  return rtnval;
}
function build_client_detail_url(client_id) {
  const rtnval = CLIENTS_API_PATH + "/" + encodeURIComponent(client_id);
  return rtnval;
}
function short_id(client_id) {
  if (typeof client_id !== "string" || client_id.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const dash_index = client_id.indexOf("-");
  if (dash_index <= 0) {
    const rtnval2 = client_id;
    return rtnval2;
  }
  const rtnval = client_id.slice(0, dash_index);
  return rtnval;
}
function format_timestamp(value) {
  if (value === null || value === void 0 || value.length === 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = parsed.toLocaleString();
  return rtnval;
}
function status_tone(status) {
  if (status === "ACTIVE") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (status === "SUSPENDED") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (status === "REVOKED") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function liveness_tone(liveness) {
  if (liveness === "ALIVE") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (liveness === "DEGRADED") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (liveness === "LOST") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function capability_tags(attributes) {
  const rtnval = [];
  if (attributes === null || attributes === void 0) {
    return rtnval;
  }
  const keys = Object.keys(attributes);
  for (const key of keys) {
    const value = attributes[key];
    if (Array.isArray(value) === true) {
      for (const entry of value) {
        if (typeof entry === "string" && entry.length > 0) {
          rtnval.push(key + ":" + entry);
        }
      }
      continue;
    }
    if (typeof value === "string" && value.length > 0) {
      rtnval.push(key + ":" + value);
      continue;
    }
    if (typeof value === "number" || typeof value === "boolean") {
      rtnval.push(key + ":" + String(value));
    }
  }
  return rtnval;
}
function has_next_page(state) {
  const consumed = state.page * state.perPage;
  const rtnval = consumed < state.total;
  return rtnval;
}
function has_previous_page(state) {
  const rtnval = state.page > 1;
  return rtnval;
}
class PycClientsList extends HTMLElement {
  _pager;
  _state;
  _clients;
  _root;
  _table_region;
  constructor() {
    super();
    this._state = {
      projectFilter: "",
      statusFilter: "",
      livenessFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false
    };
    this._clients = [];
    this._root = null;
    this._table_region = null;
    this._pager = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * filter + pagination state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectFilter: this._state.projectFilter,
      statusFilter: this._state.statusFilter,
      livenessFilter: this._state.livenessFilter,
      page: this._state.page,
      perPage: this._state.perPage,
      total: this._state.total,
      loading: this._state.loading,
      errored: this._state.errored
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * first fetch when the element is inserted into the document.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-clients-list");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-clients-list__heading");
    heading.textContent = "Clients";
    root.appendChild(heading);
    const subtitle = document.createElement("p");
    subtitle.classList.add("pyc-clients-list__subtitle");
    subtitle.textContent = "Enrolled runtimes (agents). Each client backs the pods it registers under.";
    root.appendChild(subtitle);
    const filters = document.createElement("div");
    filters.classList.add("pyc-clients-list__filters");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-clients-list__filter");
    project_label.textContent = "Project";
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-clients-list__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-filter");
    project_input.addEventListener("change", () => {
      this._state.projectFilter = project_input.value.trim();
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_input);
    filters.appendChild(project_label);
    const status_label = document.createElement("label");
    status_label.classList.add("pyc-clients-list__filter");
    status_label.textContent = "Status";
    const status_select = document.createElement("mj-select");
    status_select.classList.add("pyc-clients-list__select");
    status_select.setAttribute("data-role", "status-filter");
    const any_status = document.createElement("mj-option");
    any_status.setAttribute("value", "");
    any_status.textContent = "All statuses";
    status_select.appendChild(any_status);
    for (const status of CLIENT_STATUSES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", status);
      option.textContent = status;
      status_select.appendChild(option);
    }
    status_select.addEventListener("change", () => {
      this._state.statusFilter = status_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    status_label.appendChild(status_select);
    filters.appendChild(status_label);
    const liveness_label = document.createElement("label");
    liveness_label.classList.add("pyc-clients-list__filter");
    liveness_label.textContent = "Liveness";
    const liveness_select = document.createElement("mj-select");
    liveness_select.classList.add("pyc-clients-list__select");
    liveness_select.setAttribute("data-role", "liveness-filter");
    const any_liveness = document.createElement("mj-option");
    any_liveness.setAttribute("value", "");
    any_liveness.textContent = "All liveness";
    liveness_select.appendChild(any_liveness);
    for (const liveness of LIVENESS_STATES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", liveness);
      option.textContent = liveness;
      liveness_select.appendChild(option);
    }
    liveness_select.addEventListener("change", () => {
      this._state.livenessFilter = liveness_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    liveness_label.appendChild(liveness_select);
    filters.appendChild(liveness_label);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-clients-list__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    filters.appendChild(refresh_button);
    root.appendChild(filters);
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-clients-list__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");

    pager.classList.add("pyc-clients-list__pager");

    pager.setAttribute("data-role", "pager");

    pager.setAttribute("page", String(this._state.page));

    pager.setAttribute("page-size", String(this._state.perPage));

    pager.setAttribute("total-items", String(this._state.total));

    pager.addEventListener("mj-pagination-change", (event) => {

      this._state.page = event.detail.page;

      void this._refresh();

    });

    this._pager = pager;
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the clients array from the REST endpoint and re-render
   * the table region. Exposed so unit tests can await a fetch
   * cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._state.loading = true;
    this._state.errored = false;
    this._render_table_region();
    const url = build_clients_query_url(this._state);
    let clients = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "clients fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      clients = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.list_fetch_failed",
        { reason: String(reason) }
      );
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    if (clients === null || Array.isArray(clients) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    this._clients = clients;
    this._state.total = clients.length;
    this._state.page = 1;
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
    return;
  }
  /**
   * Slice the fetched clients array down to the current page.
   *
   * @returns The clients for the current page.
   */
  _page_slice() {
    const start = (this._state.page - 1) * this._state.perPage;
    const end = start + this._state.perPage;
    const rtnval = this._clients.slice(start, end);
    return rtnval;
  }
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-clients-list__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading clients\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-clients-list__status",
        "pyc-clients-list__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load clients. Try refreshing.";
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._clients.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-clients-list__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No enrolled clients yet";
      region.replaceChildren(empty);
      this._render_pager();
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    this._render_pager();
    return;
  }
  _build_table() {
    const table = document.createElement("mj-table");
    table.classList.add("pyc-clients-list__table");
    table.rowClass = "pyc-clients-list__row";
    table.rowAttrs = (client) => ({ "data-client-id": client.client_id });
    table.columns = [
      {
        key: "client_id",
        label: "Client",
        render: (client) => {
          const link = document.createElement("a");
          link.classList.add("pyc-clients-list__client-link");
          link.setAttribute("href", "/clients/" + client.client_id);
          link.textContent = short_id(client.client_id);
          link.title = client.client_id;
          return link;
        }
      },
      {
        key: "pod_name",
        label: "Pod",
        render: (client) => client.pod_name !== null && client.pod_name.length > 0 ? client.pod_name : "\u2014"
      },
      {
        key: "status",
        label: "Status",
        render: (client) => {
          const status_badge = document.createElement("mj-chip");
          status_badge.classList.add("pyc-clients-list__badge");
          status_badge.setAttribute("data-tone", status_tone(client.status));
          status_badge.textContent = client.status;
          return status_badge;
        }
      },
      {
        key: "liveness_state",
        label: "Liveness",
        render: (client) => {
          const liveness_badge = document.createElement("mj-chip");
          liveness_badge.classList.add("pyc-clients-list__badge");
          liveness_badge.setAttribute(
            "data-tone",
            liveness_tone(client.liveness_state)
          );
          liveness_badge.textContent = client.liveness_state;
          return liveness_badge;
        }
      },
      {
        key: "last_seen",
        label: "Last heartbeat",
        render: (client) => format_timestamp(client.last_seen)
      },
      {
        key: "last_agent_version",
        label: "Agent version",
        render: (client) => client.last_agent_version !== null && client.last_agent_version !== void 0 && client.last_agent_version.length > 0 ? client.last_agent_version : "\u2014"
      },
      {
        key: "capabilities",
        label: "Capabilities",
        render: (client) => {
          const tags = capability_tags(client.attributes);
          if (tags.length === 0) {
            const rtnval2 = document.createTextNode("\u2014");
            return rtnval2;
          }
          const fragment = document.createElement("span");
          fragment.classList.add("pyc-clients-list__tags");
          for (const tag of tags) {
            const chip = document.createElement("mj-chip");
            chip.classList.add("pyc-clients-list__tag");
            chip.textContent = tag;
            fragment.appendChild(chip);
          }
          return fragment;
        }
      }
    ];
    table.rows = this._page_slice();
    return table;
  }
  _render_pager() {

    if (this._pager === null || this._pager === undefined) {

      return;

    }

    this._pager.setAttribute("page", String(this._state.page));

    this._pager.setAttribute("page-size", String(this._state.perPage));

    this._pager.setAttribute("total-items", String(this._state.total));

    return;

  }
}
export {
  CLIENT_STATUSES,
  LIVENESS_STATES,
  PycClientsList,
  build_client_detail_url,
  build_clients_query_url,
  capability_tags,
  format_timestamp,
  has_next_page,
  has_previous_page,
  liveness_tone,
  short_id,
  status_tone
};
