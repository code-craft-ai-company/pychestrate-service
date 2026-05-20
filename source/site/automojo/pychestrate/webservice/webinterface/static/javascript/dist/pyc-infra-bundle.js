// src/pyc-infra-bundle/environments-view.ts
var ENVIRONMENT_STATES = [
  "active",
  "frozen",
  "archived",
  "destroyed"
];
var DRIFT_STATES = [
  "pending",
  "running",
  "completed",
  "failed",
  "ingest_failed",
  "skipped"
];
var DEFAULT_PER_PAGE = 25;
var PROJECTS_API_PATH = "/api/v1/projects";
function build_environments_query_url(state) {
  const params = new URLSearchParams();
  if (state.stateFilter.length > 0) {
    params.set("state", state.stateFilter);
  }
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  const query = params.toString();
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(state.projectId) + "/environments?" + query;
  return rtnval;
}
function build_environments_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/environments";
  return rtnval;
}
function build_drift_status_url(project_id, environment_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/environments/" + encodeURIComponent(environment_id) + "/drift";
  return rtnval;
}
function build_drift_check_url(project_id, environment_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/environments/" + encodeURIComponent(environment_id) + "/drift:check";
  return rtnval;
}
function short_id(value) {
  if (typeof value !== "string" || value.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const dash_index = value.indexOf("-");
  if (dash_index > 0) {
    const rtnval2 = value.slice(0, dash_index);
    return rtnval2;
  }
  if (value.length > 12) {
    const rtnval2 = value.slice(0, 12);
    return rtnval2;
  }
  const rtnval = value;
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
function environment_state_tone(environment_state) {
  if (environment_state === "active") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (environment_state === "frozen") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (environment_state === "destroyed") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function drift_status_tone(status) {
  if (status === null || status.has_report === false) {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const report = status.latest_report;
  if (report === void 0 || report === null) {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  if (report.state === "failed" || report.state === "ingest_failed") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const count = report.drift_count;
  if (typeof count === "number" && count > 0) {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (report.state === "completed") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function drift_status_label(status) {
  if (status === null) {
    const rtnval2 = "Not checked";
    return rtnval2;
  }
  if (status.has_report === false) {
    const rtnval2 = "Not checked";
    return rtnval2;
  }
  const report = status.latest_report;
  if (report === void 0 || report === null) {
    const rtnval2 = "Not checked";
    return rtnval2;
  }
  if (report.state === "failed" || report.state === "ingest_failed") {
    const rtnval2 = "Check failed";
    return rtnval2;
  }
  if (report.state === "pending" || report.state === "running") {
    const rtnval2 = "Checking\u2026";
    return rtnval2;
  }
  const count = report.drift_count;
  if (typeof count === "number" && count > 0) {
    const rtnval2 = String(count) + " drifted";
    return rtnval2;
  }
  const rtnval = "No drift";
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
function register_message_for_status(status) {
  if (status === 201 || status === 200) {
    const rtnval2 = "Environment registered.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "An environment with that name already exists.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "Environment attrs were rejected \u2014 check the kind.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project or environment kind.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to register environments.";
    return rtnval2;
  }
  const rtnval = "Failed to register environment (HTTP " + String(status) + ").";
  return rtnval;
}
function drift_check_message_for_status(status) {
  if (status === 202 || status === 200) {
    const rtnval2 = "Drift check queued.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "This environment has no drift schedule.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown environment.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to check drift.";
    return rtnval2;
  }
  const rtnval = "Failed to check drift (HTTP " + String(status) + ").";
  return rtnval;
}
function parse_environment_attrs(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = {};
    return rtnval2;
  }
  const parsed = JSON.parse(raw);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
    throw new SyntaxError("environment attrs must be a JSON object");
  }
  const rtnval = parsed;
  return rtnval;
}
var PycEnvironments = class extends HTMLElement {
  _state;
  _environments;
  _drift;
  _projects;
  _projectsAvailable;
  _root;
  _table_region;
  _register_region;
  _toast_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      stateFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false
    };
    this._environments = [];
    this._drift = /* @__PURE__ */ new Map();
    this._projects = [];
    this._projectsAvailable = false;
    this._root = null;
    this._table_region = null;
    this._register_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + pagination state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
      stateFilter: this._state.stateFilter,
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
   * project list fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_projects();
    return;
  }
  /**
   * Build the persistent chrome -- heading, project selector,
   * state filter, register action, table region, pager, toast.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-infra");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-infra__heading");
    heading.textContent = "Environments";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-infra__controls");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-infra__field");
    project_label.textContent = "Project";
    const project_select = document.createElement("select");
    project_select.classList.add("pyc-infra__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("input");
    project_input.classList.add("pyc-infra__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectId = project_input.value.trim();
      this._state.page = 1;
      void this._refresh();
    });
    controls.appendChild(project_input);
    const state_label = document.createElement("label");
    state_label.classList.add("pyc-infra__field");
    state_label.textContent = "State";
    const state_select = document.createElement("select");
    state_select.classList.add("pyc-infra__select");
    state_select.setAttribute("data-role", "state-filter");
    const any_option = document.createElement("option");
    any_option.value = "";
    any_option.textContent = "All states";
    state_select.appendChild(any_option);
    for (const environment_state of ENVIRONMENT_STATES) {
      const option = document.createElement("option");
      option.value = environment_state;
      option.textContent = environment_state;
      state_select.appendChild(option);
    }
    state_select.addEventListener("change", () => {
      this._state.stateFilter = state_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    state_label.appendChild(state_select);
    controls.appendChild(state_label);
    const register_button = document.createElement("button");
    register_button.classList.add("pyc-infra__button");
    register_button.setAttribute("type", "button");
    register_button.setAttribute("data-role", "register-toggle");
    register_button.textContent = "Register Environment";
    register_button.addEventListener("click", () => {
      this._toggle_register_form();
    });
    controls.appendChild(register_button);
    const refresh_button = document.createElement("button");
    refresh_button.classList.add("pyc-infra__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const register_region = document.createElement("div");
    register_region.classList.add("pyc-infra__form-region");
    register_region.setAttribute("data-role", "register-region");
    register_region.hidden = true;
    root.appendChild(register_region);
    this._register_region = register_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-infra__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-infra__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("div");
    pager.classList.add("pyc-infra__pager");
    const prev_button = document.createElement("button");
    prev_button.classList.add("pyc-infra__button");
    prev_button.setAttribute("type", "button");
    prev_button.setAttribute("data-role", "prev-page");
    prev_button.textContent = "Previous";
    prev_button.addEventListener("click", () => {
      if (has_previous_page(this._state) === true) {
        this._state.page = this._state.page - 1;
        void this._refresh();
      }
    });
    pager.appendChild(prev_button);
    const page_indicator = document.createElement("span");
    page_indicator.classList.add("pyc-infra__page-indicator");
    page_indicator.setAttribute("data-role", "page-indicator");
    pager.appendChild(page_indicator);
    const next_button = document.createElement("button");
    next_button.classList.add("pyc-infra__button");
    next_button.setAttribute("type", "button");
    next_button.setAttribute("data-role", "next-page");
    next_button.textContent = "Next";
    next_button.addEventListener("click", () => {
      if (has_next_page(this._state) === true) {
        this._state.page = this._state.page + 1;
        void this._refresh();
      }
    });
    pager.appendChild(next_button);
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the projects collection and populate the selector.
   * Exposed so unit tests can await the bootstrap fetch cycle.
   */
  async loadProjects() {
    await this._load_projects();
    return;
  }
  async _load_projects() {
    let projects = null;
    try {
      const response = await fetch(PROJECTS_API_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        projects = this._extract_projects(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._state.projectId = projects[0].project_id;
    } else {
      this._projects = [];
      this._projectsAvailable = false;
    }
    this._render_project_control();
    if (this._state.projectId.length > 0) {
      await this._refresh();
    } else {
      this._render_table_region();
    }
    return;
  }
  /**
   * Normalise a projects-list response body into ``ProjectOption``
   * records. Accepts both a bare array and a ``{items}`` page
   * envelope.
   *
   * @param body Parsed JSON response body.
   *
   * @returns A list of project options (possibly empty).
   */
  _extract_projects(body) {
    let raw = [];
    if (Array.isArray(body) === true) {
      raw = body;
    } else if (body !== null && typeof body === "object") {
      const items = body.items;
      if (Array.isArray(items) === true) {
        raw = items;
      }
    }
    const rtnval = [];
    for (const item of raw) {
      if (item === null || typeof item !== "object") {
        continue;
      }
      const record = item;
      const project_id = record.project_id;
      if (typeof project_id !== "string" || project_id.length === 0) {
        continue;
      }
      const display = record.display_name;
      const display_name = typeof display === "string" && display.length > 0 ? display : project_id;
      rtnval.push({ project_id, display_name });
    }
    return rtnval;
  }
  /**
   * Render the project-select control or, when no projects
   * collection is available, swap to the manual text input.
   */
  _render_project_control() {
    if (this._root === null) {
      return;
    }
    const select = this._root.querySelector('[data-role="project-select"]');
    const input = this._root.querySelector('[data-role="project-input"]');
    if (select instanceof HTMLSelectElement === false || input instanceof HTMLInputElement === false) {
      return;
    }
    const select_el = select;
    const input_el = input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      for (const project of this._projects) {
        const option = document.createElement("option");
        option.value = project.project_id;
        option.textContent = project.display_name;
        select_el.appendChild(option);
      }
      select_el.value = this._state.projectId;
    } else {
      select_el.hidden = true;
      input_el.hidden = false;
    }
    return;
  }
  /**
   * Fetch the current page of environments and re-render the
   * table. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._environments = [];
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._drift = /* @__PURE__ */ new Map();
    this._render_table_region();
    const url = build_environments_query_url(this._state);
    let page = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "environments fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.environments_fetch_failed",
        { reason: String(reason) }
      );
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    this._environments = page.items;
    const meta = page.meta;
    if (meta !== void 0 && meta !== null) {
      if (typeof meta.total === "number") {
        this._state.total = meta.total;
      }
      if (typeof meta.page === "number") {
        this._state.page = meta.page;
      }
      if (typeof meta.per_page === "number") {
        this._state.perPage = meta.per_page;
      }
    }
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
    return;
  }
  /**
   * Re-render the table region from the current state +
   * environments.
   */
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.projectId.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-infra__status");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its environments.";
      region.replaceChildren(notice);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-infra__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading environments\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-infra__status",
        "pyc-infra__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load environments. Try refreshing.";
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._environments.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-infra__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No environments registered yet";
      region.replaceChildren(empty);
      this._render_pager();
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    this._render_pager();
    return;
  }
  /**
   * Build the environments ``<table>`` from the current list.
   */
  _build_table() {
    const table = document.createElement("table");
    table.classList.add("pyc-infra__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = [
      "Environment",
      "Kind",
      "State",
      "Drift",
      "Last applied",
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
    for (const environment of this._environments) {
      tbody.appendChild(this._build_row(environment));
    }
    table.appendChild(tbody);
    return table;
  }
  /**
   * Build one environment table row, including the drift
   * indicator cell and the per-row "Check Drift" action.
   *
   * @param environment The environment to render.
   *
   * @returns A populated ``<tr>``.
   */
  _build_row(environment) {
    const row = document.createElement("tr");
    row.classList.add("pyc-infra__row");
    row.setAttribute("data-environment-id", environment.environment_id);
    const name_cell = document.createElement("td");
    const name = document.createElement("span");
    name.classList.add("pyc-infra__env-name");
    name.textContent = environment.name;
    name.title = environment.environment_id;
    name_cell.appendChild(name);
    row.appendChild(name_cell);
    const kind_cell = document.createElement("td");
    kind_cell.textContent = environment.kind_name;
    row.appendChild(kind_cell);
    const state_cell = document.createElement("td");
    const state_badge = document.createElement("span");
    state_badge.classList.add("pyc-infra__badge");
    state_badge.setAttribute(
      "data-tone",
      environment_state_tone(environment.state)
    );
    state_badge.textContent = environment.state;
    state_cell.appendChild(state_badge);
    row.appendChild(state_cell);
    const drift_cell = document.createElement("td");
    const drift_badge = document.createElement("span");
    drift_badge.classList.add("pyc-infra__badge", "pyc-infra__drift");
    drift_badge.setAttribute("data-role", "drift-indicator");
    const status = this._drift.get(environment.environment_id) ?? null;
    drift_badge.setAttribute("data-tone", drift_status_tone(status));
    drift_badge.textContent = drift_status_label(status);
    drift_cell.appendChild(drift_badge);
    row.appendChild(drift_cell);
    const applied_cell = document.createElement("td");
    applied_cell.textContent = format_timestamp(environment.last_applied_at);
    row.appendChild(applied_cell);
    const actions_cell = document.createElement("td");
    const check_button = document.createElement("button");
    check_button.classList.add("pyc-infra__button", "pyc-infra__row-action");
    check_button.setAttribute("type", "button");
    check_button.setAttribute("data-role", "check-drift");
    check_button.textContent = "Check Drift";
    check_button.addEventListener("click", () => {
      check_button.disabled = true;
      void this._on_check_drift(environment, check_button);
    });
    actions_cell.appendChild(check_button);
    row.appendChild(actions_cell);
    return row;
  }
  /**
   * Update the pager controls -- enabled state + the page
   * indicator label -- from the current state.
   */
  _render_pager() {
    if (this._root === null) {
      return;
    }
    const prev = this._root.querySelector('[data-role="prev-page"]');
    const next = this._root.querySelector('[data-role="next-page"]');
    const indicator = this._root.querySelector(
      '[data-role="page-indicator"]'
    );
    if (prev instanceof HTMLButtonElement) {
      prev.disabled = has_previous_page(this._state) === false;
    }
    if (next instanceof HTMLButtonElement) {
      next.disabled = has_next_page(this._state) === false;
    }
    if (indicator instanceof HTMLElement) {
      const label = "Page " + String(this._state.page) + " \xB7 " + String(this._state.total) + " total";
      indicator.textContent = label;
    }
    return;
  }
  /**
   * Refresh one environment's drift indicator cell from the
   * supplied drift status.
   *
   * @param environment_id The environment whose row to update.
   */
  _render_drift_cell(environment_id) {
    if (this._table_region === null) {
      return;
    }
    const selector = 'tr[data-environment-id="' + environment_id + '"] [data-role="drift-indicator"]';
    const badge = this._table_region.querySelector(selector);
    if (badge instanceof HTMLElement === false) {
      return;
    }
    const el = badge;
    const status = this._drift.get(environment_id) ?? null;
    el.setAttribute("data-tone", drift_status_tone(status));
    el.textContent = drift_status_label(status);
    return;
  }
  /**
   * Run the "Check Drift" action for one environment -- POST the
   * drift-check then re-read the drift status, updating the
   * indicator and surfacing a toast.
   *
   * @param environment The environment to check.
   * @param button The row action button, re-enabled on completion.
   */
  async _on_check_drift(environment, button) {
    const outcome = await this._do_check_drift(
      environment.environment_id
    );
    if (outcome.ok === true) {
      await this._load_drift_status(environment.environment_id);
    }
    button.disabled = false;
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    return;
  }
  /**
   * POST a drift check for one environment. Exposed so unit tests
   * can drive a drift check without a row button.
   *
   * @param environment_id The environment to check.
   *
   * @returns The drift-check outcome.
   */
  async checkDrift(environment_id) {
    const rtnval = await this._do_check_drift(environment_id);
    return rtnval;
  }
  async _do_check_drift(environment_id) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        report: null,
        message: "Select a project before checking drift."
      };
      return rtnval2;
    }
    let status = 0;
    let report = null;
    try {
      const url = build_drift_check_url(
        this._state.projectId,
        environment_id
      );
      const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        const parsed = body;
        if (parsed !== null && typeof parsed.run_id === "string") {
          report = parsed;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.drift_check_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        report: null,
        message: "Failed to reach the drift service."
      };
      return rtnval2;
    }
    const ok = status === 202 || status === 200;
    const rtnval = {
      ok,
      status,
      report,
      message: drift_check_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Fetch and cache one environment's current drift status, then
   * re-render its indicator cell. Exposed so unit tests can await
   * a drift-status fetch.
   *
   * @param environment_id The environment to read drift for.
   */
  async loadDriftStatus(environment_id) {
    await this._load_drift_status(environment_id);
    return;
  }
  async _load_drift_status(environment_id) {
    if (this._state.projectId.length === 0) {
      return;
    }
    try {
      const url = build_drift_status_url(
        this._state.projectId,
        environment_id
      );
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const status = body;
        if (status !== null && typeof status === "object") {
          this._drift.set(environment_id, status);
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.drift_status_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._render_drift_cell(environment_id);
    return;
  }
  /**
   * Toggle the inline register-environment form's visibility,
   * rendering it on first reveal.
   */
  _toggle_register_form() {
    if (this._register_region === null) {
      return;
    }
    const region = this._register_region;
    if (region.hidden === true) {
      this._render_register_form();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the register-environment form into the register
   * region -- a name input, a kind-name input, an attrs JSON
   * textarea, and a submit button.
   */
  _render_register_form() {
    if (this._register_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-infra__form");
    form.setAttribute("data-role", "register-form");
    const name_label = document.createElement("label");
    name_label.classList.add("pyc-infra__field");
    name_label.textContent = "Environment name";
    const name_input = document.createElement("input");
    name_input.classList.add("pyc-infra__input");
    name_input.setAttribute("type", "text");
    name_input.setAttribute("placeholder", "staging");
    name_input.setAttribute("data-role", "register-name");
    name_input.required = true;
    name_label.appendChild(name_input);
    form.appendChild(name_label);
    const kind_label = document.createElement("label");
    kind_label.classList.add("pyc-infra__field");
    kind_label.textContent = "Environment kind";
    const kind_input = document.createElement("input");
    kind_input.classList.add("pyc-infra__input");
    kind_input.setAttribute("type", "text");
    kind_input.setAttribute("placeholder", "terraform");
    kind_input.setAttribute("data-role", "register-kind");
    kind_input.required = true;
    kind_label.appendChild(kind_input);
    form.appendChild(kind_label);
    const attrs_label = document.createElement("label");
    attrs_label.classList.add(
      "pyc-infra__field",
      "pyc-infra__field--wide"
    );
    attrs_label.textContent = "Attributes (JSON)";
    const attrs_area = document.createElement("textarea");
    attrs_area.classList.add("pyc-infra__textarea");
    attrs_area.setAttribute("data-role", "register-attrs");
    attrs_area.setAttribute("placeholder", '{"region": "us-east-1"}');
    attrs_area.rows = 3;
    attrs_label.appendChild(attrs_area);
    form.appendChild(attrs_label);
    const submit_button = document.createElement("button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "register-submit");
    submit_button.textContent = "Register Environment";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-infra__form-status");
    status.setAttribute("data-role", "register-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_register(
        form,
        name_input,
        kind_input,
        attrs_area,
        submit_button
      );
    });
    this._register_region.replaceChildren(form);
    return;
  }
  async _submit_register(form, name_input, kind_input, attrs_area, submit_button) {
    const status = form.querySelector('[data-role="register-status"]');
    const name = name_input.value.trim();
    const kind_name = kind_input.value.trim();
    if (name.length === 0 || kind_name.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Environment name and kind are required.";
      }
      return;
    }
    let attrs = {};
    try {
      attrs = parse_environment_attrs(attrs_area.value);
    } catch (reason) {
      if (status instanceof HTMLElement) {
        status.textContent = "Attributes must be valid JSON.";
      }
      console.warn(
        "pychestrate.ui.infra.register_attrs_invalid",
        { reason: String(reason) }
      );
      return;
    }
    submit_button.disabled = true;
    if (status instanceof HTMLElement) {
      status.textContent = "Registering environment\u2026";
    }
    const outcome = await this._do_register(name, kind_name, attrs);
    submit_button.disabled = false;
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * POST an ``EnvironmentCreateRequest``. Exposed so unit tests
   * can invoke a register without a real form-submit event.
   *
   * @param name Human-facing environment name.
   * @param kind_name Registered environment-kind factory name.
   * @param attrs Kind-specific environment attributes.
   *
   * @returns The register outcome.
   */
  async registerEnvironment(name, kind_name, attrs) {
    const rtnval = await this._do_register(name, kind_name, attrs);
    return rtnval;
  }
  async _do_register(name, kind_name, attrs) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        environmentId: "",
        message: "Select a project before registering an environment."
      };
      return rtnval2;
    }
    const payload = {
      name,
      kind_name,
      attrs
    };
    let status = 0;
    let environment_id = "";
    try {
      const url = build_environments_collection_url(
        this._state.projectId
      );
      const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        const environment = body;
        if (environment !== null && typeof environment.environment_id === "string") {
          environment_id = environment.environment_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.register_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        environmentId: "",
        message: "Failed to reach the environment service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      environmentId: environment_id,
      message: register_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Render a dismissible toast in the toast region.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-infra__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.classList.add("pyc-infra__toast-message");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("button");
    dismiss.classList.add("pyc-infra__toast-dismiss");
    dismiss.setAttribute("type", "button");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "\xD7";
    dismiss.addEventListener("click", () => {
      toast.remove();
    });
    toast.appendChild(dismiss);
    this._toast_region.replaceChildren(toast);
    return;
  }
};

// src/pyc-infra-bundle/provisioning-list-view.ts
var PROVISIONING_STATES = [
  "pending",
  "running",
  "completed",
  "failed",
  "cancelled",
  "rejected_by_guard"
];
var TERMINAL_PROVISIONING_STATES = [
  "completed",
  "failed",
  "cancelled",
  "rejected_by_guard"
];
var PROVISIONING_ACTIONS = [
  "plan",
  "apply",
  "destroy"
];
var DEFAULT_PER_PAGE2 = 25;
var PROJECTS_API_PATH2 = "/api/v1/projects";
function build_provisioning_query_url(state) {
  const params = new URLSearchParams();
  if (state.stateFilter.length > 0) {
    params.set("state", state.stateFilter);
  }
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  const query = params.toString();
  const rtnval = PROJECTS_API_PATH2 + "/" + encodeURIComponent(state.projectId) + "/provisioning-runs?" + query;
  return rtnval;
}
function build_provisioning_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH2 + "/" + encodeURIComponent(project_id) + "/provisioning-runs";
  return rtnval;
}
function build_provisioning_detail_link(project_id, run_id) {
  const rtnval = "/provisioning-runs/" + encodeURIComponent(run_id) + "?project_id=" + encodeURIComponent(project_id);
  return rtnval;
}
function provisioning_state_tone(run_state) {
  if (run_state === "completed") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (run_state === "failed") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (run_state === "rejected_by_guard") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (run_state === "cancelled") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function is_terminal_provisioning_state(run_state) {
  const rtnval = TERMINAL_PROVISIONING_STATES.indexOf(run_state) >= 0;
  return rtnval;
}
function has_next_page2(state) {
  const consumed = state.page * state.perPage;
  const rtnval = consumed < state.total;
  return rtnval;
}
function has_previous_page2(state) {
  const rtnval = state.page > 1;
  return rtnval;
}
function trigger_message_for_status(status) {
  if (status === 202 || status === 200 || status === 201) {
    const rtnval2 = "Provisioning run triggered.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "Driver inputs were rejected \u2014 check the driver name.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "The environment cannot accept this action right now.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project, environment, or driver.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to trigger provisioning runs.";
    return rtnval2;
  }
  const rtnval = "Failed to trigger provisioning run (HTTP " + String(status) + ").";
  return rtnval;
}
function parse_driver_inputs(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = {};
    return rtnval2;
  }
  const parsed = JSON.parse(raw);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
    throw new SyntaxError("driver inputs must be a JSON object");
  }
  const rtnval = parsed;
  return rtnval;
}
var PycProvisioningList = class extends HTMLElement {
  _state;
  _runs;
  _environments;
  _projects;
  _projectsAvailable;
  _root;
  _table_region;
  _trigger_region;
  _toast_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      stateFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE2,
      total: 0,
      loading: false,
      errored: false
    };
    this._runs = [];
    this._environments = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._root = null;
    this._table_region = null;
    this._trigger_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + pagination state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
      stateFilter: this._state.stateFilter,
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
   * project list fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_projects();
    return;
  }
  /**
   * Build the persistent chrome -- heading, project selector,
   * state filter, trigger action, table region, pager, toast.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-infra");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-infra__heading");
    heading.textContent = "Provisioning Runs";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-infra__controls");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-infra__field");
    project_label.textContent = "Project";
    const project_select = document.createElement("select");
    project_select.classList.add("pyc-infra__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      this._state.page = 1;
      void this._on_project_changed();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("input");
    project_input.classList.add("pyc-infra__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectId = project_input.value.trim();
      this._state.page = 1;
      void this._on_project_changed();
    });
    controls.appendChild(project_input);
    const state_label = document.createElement("label");
    state_label.classList.add("pyc-infra__field");
    state_label.textContent = "State";
    const state_select = document.createElement("select");
    state_select.classList.add("pyc-infra__select");
    state_select.setAttribute("data-role", "state-filter");
    const any_option = document.createElement("option");
    any_option.value = "";
    any_option.textContent = "All states";
    state_select.appendChild(any_option);
    for (const run_state of PROVISIONING_STATES) {
      const option = document.createElement("option");
      option.value = run_state;
      option.textContent = run_state;
      state_select.appendChild(option);
    }
    state_select.addEventListener("change", () => {
      this._state.stateFilter = state_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    state_label.appendChild(state_select);
    controls.appendChild(state_label);
    const trigger_button = document.createElement("button");
    trigger_button.classList.add("pyc-infra__button");
    trigger_button.setAttribute("type", "button");
    trigger_button.setAttribute("data-role", "trigger-toggle");
    trigger_button.textContent = "Trigger Provisioning";
    trigger_button.addEventListener("click", () => {
      this._toggle_trigger_form();
    });
    controls.appendChild(trigger_button);
    const refresh_button = document.createElement("button");
    refresh_button.classList.add("pyc-infra__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const trigger_region = document.createElement("div");
    trigger_region.classList.add("pyc-infra__form-region");
    trigger_region.setAttribute("data-role", "trigger-region");
    trigger_region.hidden = true;
    root.appendChild(trigger_region);
    this._trigger_region = trigger_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-infra__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-infra__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("div");
    pager.classList.add("pyc-infra__pager");
    const prev_button = document.createElement("button");
    prev_button.classList.add("pyc-infra__button");
    prev_button.setAttribute("type", "button");
    prev_button.setAttribute("data-role", "prev-page");
    prev_button.textContent = "Previous";
    prev_button.addEventListener("click", () => {
      if (has_previous_page2(this._state) === true) {
        this._state.page = this._state.page - 1;
        void this._refresh();
      }
    });
    pager.appendChild(prev_button);
    const page_indicator = document.createElement("span");
    page_indicator.classList.add("pyc-infra__page-indicator");
    page_indicator.setAttribute("data-role", "page-indicator");
    pager.appendChild(page_indicator);
    const next_button = document.createElement("button");
    next_button.classList.add("pyc-infra__button");
    next_button.setAttribute("type", "button");
    next_button.setAttribute("data-role", "next-page");
    next_button.textContent = "Next";
    next_button.addEventListener("click", () => {
      if (has_next_page2(this._state) === true) {
        this._state.page = this._state.page + 1;
        void this._refresh();
      }
    });
    pager.appendChild(next_button);
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the projects collection and populate the selector.
   * Exposed so unit tests can await the bootstrap fetch cycle.
   */
  async loadProjects() {
    await this._load_projects();
    return;
  }
  async _load_projects() {
    let projects = null;
    try {
      const response = await fetch(PROJECTS_API_PATH2, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        projects = this._extract_projects(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._state.projectId = projects[0].project_id;
    } else {
      this._projects = [];
      this._projectsAvailable = false;
    }
    this._render_project_control();
    if (this._state.projectId.length > 0) {
      await this._on_project_changed();
    } else {
      this._render_table_region();
    }
    return;
  }
  /**
   * Normalise a projects-list response body into ``ProjectOption``
   * records. Accepts both a bare array and a ``{items}`` page
   * envelope.
   *
   * @param body Parsed JSON response body.
   *
   * @returns A list of project options (possibly empty).
   */
  _extract_projects(body) {
    let raw = [];
    if (Array.isArray(body) === true) {
      raw = body;
    } else if (body !== null && typeof body === "object") {
      const items = body.items;
      if (Array.isArray(items) === true) {
        raw = items;
      }
    }
    const rtnval = [];
    for (const item of raw) {
      if (item === null || typeof item !== "object") {
        continue;
      }
      const record = item;
      const project_id = record.project_id;
      if (typeof project_id !== "string" || project_id.length === 0) {
        continue;
      }
      const display = record.display_name;
      const display_name = typeof display === "string" && display.length > 0 ? display : project_id;
      rtnval.push({ project_id, display_name });
    }
    return rtnval;
  }
  /**
   * Render the project-select control or, when no projects
   * collection is available, swap to the manual text input.
   */
  _render_project_control() {
    if (this._root === null) {
      return;
    }
    const select = this._root.querySelector('[data-role="project-select"]');
    const input = this._root.querySelector('[data-role="project-input"]');
    if (select instanceof HTMLSelectElement === false || input instanceof HTMLInputElement === false) {
      return;
    }
    const select_el = select;
    const input_el = input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      for (const project of this._projects) {
        const option = document.createElement("option");
        option.value = project.project_id;
        option.textContent = project.display_name;
        select_el.appendChild(option);
      }
      select_el.value = this._state.projectId;
    } else {
      select_el.hidden = true;
      input_el.hidden = false;
    }
    return;
  }
  /**
   * React to a project change -- reload the environments (so the
   * trigger form's selector is fresh) and the provisioning page.
   */
  async _on_project_changed() {
    await this._load_environments();
    await this._refresh();
    return;
  }
  /**
   * Fetch the active project's environments for the trigger
   * form's environment selector. A failed fetch leaves the list
   * empty.
   */
  async _load_environments() {
    this._environments = [];
    if (this._state.projectId.length === 0) {
      return;
    }
    try {
      const url = build_environments_query_url({
        projectId: this._state.projectId,
        stateFilter: "",
        page: 1,
        perPage: 100,
        total: 0,
        loading: false,
        errored: false
      });
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (page !== null && Array.isArray(page.items) === true) {
          this._environments = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.environments_fetch_failed",
        { reason: String(reason) }
      );
    }
    return;
  }
  /**
   * Fetch the current page of provisioning runs and re-render
   * the table. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._runs = [];
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._render_table_region();
    const url = build_provisioning_query_url(this._state);
    let page = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "provisioning fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.provisioning_fetch_failed",
        { reason: String(reason) }
      );
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    this._runs = page.items;
    const meta = page.meta;
    if (meta !== void 0 && meta !== null) {
      if (typeof meta.total === "number") {
        this._state.total = meta.total;
      }
      if (typeof meta.page === "number") {
        this._state.page = meta.page;
      }
      if (typeof meta.per_page === "number") {
        this._state.perPage = meta.per_page;
      }
    }
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
    return;
  }
  /**
   * Re-render the table region from the current state + runs.
   */
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.projectId.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-infra__status");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its provisioning runs.";
      region.replaceChildren(notice);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-infra__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading provisioning runs\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-infra__status",
        "pyc-infra__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load provisioning runs. Try refreshing.";
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._runs.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-infra__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No provisioning runs yet";
      region.replaceChildren(empty);
      this._render_pager();
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    this._render_pager();
    return;
  }
  /**
   * Build the provisioning-runs ``<table>`` from the current
   * ``_runs`` list.
   */
  _build_table() {
    const table = document.createElement("table");
    table.classList.add("pyc-infra__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = [
      "Run",
      "Action",
      "Driver",
      "State",
      "Started",
      "Finished"
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
    for (const run of this._runs) {
      const row = document.createElement("tr");
      row.classList.add("pyc-infra__row");
      const id_cell = document.createElement("td");
      const link = document.createElement("a");
      link.classList.add("pyc-infra__run-link");
      link.setAttribute(
        "href",
        build_provisioning_detail_link(run.project_id, run.run_id)
      );
      link.textContent = short_id(run.run_id);
      link.title = run.run_id;
      id_cell.appendChild(link);
      row.appendChild(id_cell);
      const action_cell = document.createElement("td");
      action_cell.textContent = run.action;
      row.appendChild(action_cell);
      const driver_cell = document.createElement("td");
      driver_cell.textContent = run.driver_name;
      row.appendChild(driver_cell);
      const state_cell = document.createElement("td");
      const badge = document.createElement("span");
      badge.classList.add("pyc-infra__badge");
      badge.setAttribute("data-tone", provisioning_state_tone(run.state));
      badge.textContent = run.state;
      state_cell.appendChild(badge);
      row.appendChild(state_cell);
      const started_cell = document.createElement("td");
      started_cell.textContent = format_timestamp(run.started_at);
      row.appendChild(started_cell);
      const finished_cell = document.createElement("td");
      finished_cell.textContent = format_timestamp(run.finished_at);
      row.appendChild(finished_cell);
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    return table;
  }
  /**
   * Update the pager controls -- enabled state + the page
   * indicator label -- from the current state.
   */
  _render_pager() {
    if (this._root === null) {
      return;
    }
    const prev = this._root.querySelector('[data-role="prev-page"]');
    const next = this._root.querySelector('[data-role="next-page"]');
    const indicator = this._root.querySelector(
      '[data-role="page-indicator"]'
    );
    if (prev instanceof HTMLButtonElement) {
      prev.disabled = has_previous_page2(this._state) === false;
    }
    if (next instanceof HTMLButtonElement) {
      next.disabled = has_next_page2(this._state) === false;
    }
    if (indicator instanceof HTMLElement) {
      const label = "Page " + String(this._state.page) + " \xB7 " + String(this._state.total) + " total";
      indicator.textContent = label;
    }
    return;
  }
  /**
   * Toggle the inline trigger-provisioning form's visibility,
   * rendering it on first reveal.
   */
  _toggle_trigger_form() {
    if (this._trigger_region === null) {
      return;
    }
    const region = this._trigger_region;
    if (region.hidden === true) {
      this._render_trigger_form();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the trigger-provisioning form -- an environment
   * selector, a driver-name input, an action selector, a
   * driver-inputs JSON textarea, and a submit button.
   */
  _render_trigger_form() {
    if (this._trigger_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-infra__form");
    form.setAttribute("data-role", "trigger-form");
    const environment_label = document.createElement("label");
    environment_label.classList.add("pyc-infra__field");
    environment_label.textContent = "Environment";
    const environment_select = document.createElement("select");
    environment_select.classList.add("pyc-infra__select");
    environment_select.setAttribute("data-role", "trigger-environment");
    if (this._environments.length === 0) {
      const none_option = document.createElement("option");
      none_option.value = "";
      none_option.textContent = "No environment registered";
      environment_select.appendChild(none_option);
    } else {
      for (const environment of this._environments) {
        const option = document.createElement("option");
        option.value = environment.environment_id;
        option.textContent = environment.name + " \xB7 " + environment.kind_name;
        environment_select.appendChild(option);
      }
    }
    environment_label.appendChild(environment_select);
    form.appendChild(environment_label);
    const driver_label = document.createElement("label");
    driver_label.classList.add("pyc-infra__field");
    driver_label.textContent = "Driver name";
    const driver_input = document.createElement("input");
    driver_input.classList.add("pyc-infra__input");
    driver_input.setAttribute("type", "text");
    driver_input.setAttribute("placeholder", "terraform");
    driver_input.setAttribute("data-role", "trigger-driver");
    driver_input.required = true;
    driver_label.appendChild(driver_input);
    form.appendChild(driver_label);
    const action_label = document.createElement("label");
    action_label.classList.add("pyc-infra__field");
    action_label.textContent = "Action";
    const action_select = document.createElement("select");
    action_select.classList.add("pyc-infra__select");
    action_select.setAttribute("data-role", "trigger-action");
    for (const action of PROVISIONING_ACTIONS) {
      const option = document.createElement("option");
      option.value = action;
      option.textContent = action;
      action_select.appendChild(option);
    }
    action_label.appendChild(action_select);
    form.appendChild(action_label);
    const inputs_label = document.createElement("label");
    inputs_label.classList.add(
      "pyc-infra__field",
      "pyc-infra__field--wide"
    );
    inputs_label.textContent = "Driver inputs (JSON)";
    const inputs_area = document.createElement("textarea");
    inputs_area.classList.add("pyc-infra__textarea");
    inputs_area.setAttribute("data-role", "trigger-driver-inputs");
    inputs_area.setAttribute("placeholder", '{"auto_approve": false}');
    inputs_area.rows = 3;
    inputs_label.appendChild(inputs_area);
    form.appendChild(inputs_label);
    const submit_button = document.createElement("button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "trigger-submit");
    submit_button.textContent = "Trigger Provisioning";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-infra__form-status");
    status.setAttribute("data-role", "trigger-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_trigger(
        form,
        environment_select,
        driver_input,
        action_select,
        inputs_area,
        submit_button
      );
    });
    this._trigger_region.replaceChildren(form);
    return;
  }
  async _submit_trigger(form, environment_select, driver_input, action_select, inputs_area, submit_button) {
    const status = form.querySelector('[data-role="trigger-status"]');
    const environment_id = environment_select.value;
    const driver_name = driver_input.value.trim();
    const action = action_select.value;
    if (environment_id.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Select a target environment.";
      }
      return;
    }
    if (driver_name.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Driver name is required.";
      }
      return;
    }
    let driver_inputs = {};
    try {
      driver_inputs = parse_driver_inputs(inputs_area.value);
    } catch (reason) {
      if (status instanceof HTMLElement) {
        status.textContent = "Driver inputs must be valid JSON.";
      }
      console.warn(
        "pychestrate.ui.infra.trigger_inputs_invalid",
        { reason: String(reason) }
      );
      return;
    }
    submit_button.disabled = true;
    if (status instanceof HTMLElement) {
      status.textContent = "Triggering provisioning run\u2026";
    }
    const outcome = await this._do_trigger(
      environment_id,
      driver_name,
      action,
      driver_inputs
    );
    submit_button.disabled = false;
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._show_trigger_toast(outcome);
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * POST a ``ProvisioningRunCreateRequest``. Exposed so unit
   * tests can invoke a trigger without a real form-submit event.
   *
   * @param environment_id Bound target environment id.
   * @param driver_name Registered infra-tool driver factory name.
   * @param action ``"plan"`` | ``"apply"`` | ``"destroy"``.
   * @param driver_inputs Free-form driver inputs object.
   *
   * @returns The trigger outcome.
   */
  async triggerProvisioning(environment_id, driver_name, action, driver_inputs) {
    const rtnval = await this._do_trigger(
      environment_id,
      driver_name,
      action,
      driver_inputs
    );
    return rtnval;
  }
  async _do_trigger(environment_id, driver_name, action, driver_inputs) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        runId: "",
        message: "Select a project before triggering a run."
      };
      return rtnval2;
    }
    const payload = {
      environment_id,
      driver_name,
      action,
      driver_inputs
    };
    let status = 0;
    let run_id = "";
    try {
      const url = build_provisioning_collection_url(
        this._state.projectId
      );
      const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        const run = body;
        if (run !== null && typeof run.run_id === "string") {
          run_id = run.run_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.trigger_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        runId: "",
        message: "Failed to reach the provisioning service."
      };
      return rtnval2;
    }
    const ok = status === 202 || status === 200 || status === 201;
    const rtnval = {
      ok,
      status,
      runId: run_id,
      message: trigger_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Render a dismissible toast for a trigger outcome -- on
   * success the toast links to the new run's detail page.
   *
   * @param outcome The trigger-provisioning outcome.
   */
  _show_trigger_toast(outcome) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-infra__toast");
    toast.setAttribute("data-role", "trigger-toast");
    toast.setAttribute("data-tone", outcome.ok === true ? "ok" : "error");
    const message = document.createElement("span");
    message.classList.add("pyc-infra__toast-message");
    message.textContent = outcome.message;
    toast.appendChild(message);
    if (outcome.ok === true && outcome.runId.length > 0) {
      const link = document.createElement("a");
      link.classList.add("pyc-infra__toast-link");
      link.setAttribute(
        "href",
        build_provisioning_detail_link(
          this._state.projectId,
          outcome.runId
        )
      );
      link.setAttribute("data-role", "trigger-toast-link");
      link.textContent = "View run";
      toast.appendChild(link);
    }
    const dismiss = document.createElement("button");
    dismiss.classList.add("pyc-infra__toast-dismiss");
    dismiss.setAttribute("type", "button");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "\xD7";
    dismiss.addEventListener("click", () => {
      toast.remove();
    });
    toast.appendChild(dismiss);
    this._toast_region.replaceChildren(toast);
    return;
  }
};

// src/pyc-infra-bundle/provisioning-detail-view.ts
var PROJECTS_API_PATH3 = "/api/v1/projects";
var POLL_INTERVAL_MS = 5e3;
var UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function run_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/provisioning-runs/";
  if (path.startsWith(prefix) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  let tail = path.slice(prefix.length);
  const slash_index = tail.indexOf("/");
  if (slash_index >= 0) {
    tail = tail.slice(0, slash_index);
  }
  const query_index = tail.indexOf("?");
  if (query_index >= 0) {
    tail = tail.slice(0, query_index);
  }
  const rtnval = tail;
  return rtnval;
}
function project_id_from_search(search) {
  if (typeof search !== "string" || search.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const params = new URLSearchParams(search);
  const value = params.get("project_id");
  if (value === null) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = value;
  return rtnval;
}
function is_valid_run_id(run_id) {
  if (typeof run_id !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(run_id);
  return rtnval;
}
function build_provisioning_detail_url(project_id, run_id) {
  const rtnval = PROJECTS_API_PATH3 + "/" + encodeURIComponent(project_id) + "/provisioning-runs/" + encodeURIComponent(run_id);
  return rtnval;
}
var PycProvisioningDetail = class extends HTMLElement {
  _run_id;
  _project_id;
  _run;
  _loading;
  _errored;
  _terminal;
  _poll_status;
  _poll_timer;
  _root;
  constructor() {
    super();
    this._run_id = "";
    this._project_id = "";
    this._run = null;
    this._loading = false;
    this._errored = false;
    this._terminal = false;
    this._poll_status = "idle";
    this._poll_timer = null;
    this._root = null;
  }
  /**
   * Observed attributes -- ``run-id`` and ``project-id`` may be
   * supplied explicitly by a host; otherwise they are read from
   * the URL on mount.
   */
  static get observedAttributes() {
    const rtnval = ["run-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      runId: this._run_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored,
      pollStatus: this._poll_status,
      terminal: this._terminal
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the run + project ids, render the
   * chrome, and fetch the initial snapshot.
   */
  connectedCallback() {
    const attr_run = this.getAttribute("run-id");
    if (attr_run !== null && attr_run.length > 0) {
      this._run_id = attr_run;
    } else {
      this._run_id = run_id_from_path(window.location.pathname);
    }
    const attr_project = this.getAttribute("project-id");
    if (attr_project !== null && attr_project.length > 0) {
      this._project_id = attr_project;
    } else {
      this._project_id = project_id_from_search(window.location.search);
    }
    this._render_chrome();
    void this._load();
    return;
  }
  /**
   * Lifecycle hook -- stop the live-poll timer so a navigation
   * away from the run never leaks a timer.
   */
  disconnectedCallback() {
    this._stop_poll();
    return;
  }
  /**
   * Fetch the run snapshot then -- when the run is not already
   * terminal -- start the live-poll loop. Exposed so unit tests
   * can await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_run_id(this._run_id) === false || this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const run = await this._fetch_run();
    if (run === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._run = run;
    this._loading = false;
    this._errored = false;
    this._terminal = is_terminal_provisioning_state(run.state);
    this._render_body();
    if (this._terminal === false) {
      this._start_poll();
    } else {
      this._poll_status = "stopped";
      this._render_poll_banner();
    }
    return;
  }
  /**
   * Fetch the current provisioning-run snapshot.
   *
   * @returns The ``ProvisioningRun`` snapshot, or ``null`` on
   *          failure.
   */
  async _fetch_run() {
    const url = build_provisioning_detail_url(
      this._project_id,
      this._run_id
    );
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "provisioning run fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.detail_fetch_failed",
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  /**
   * Start the live-poll loop. A no-op when a poll is already
   * scheduled.
   */
  _start_poll() {
    if (this._poll_timer !== null) {
      return;
    }
    this._poll_status = "polling";
    this._render_poll_banner();
    this._schedule_poll();
    return;
  }
  _schedule_poll() {
    const timer = setTimeout(() => {
      this._poll_timer = null;
      void this._poll_once();
    }, POLL_INTERVAL_MS);
    const handle = timer;
    if (typeof handle.unref === "function") {
      handle.unref();
    }
    this._poll_timer = timer;
    return;
  }
  /**
   * Run one poll cycle -- re-fetch the run snapshot, re-render,
   * and either reschedule (still non-terminal) or stop (now
   * terminal). Exposed so unit tests can drive a poll cycle
   * without waiting on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    const run = await this._fetch_run();
    if (run !== null) {
      this._run = run;
      this._terminal = is_terminal_provisioning_state(run.state);
      this._render_body();
    }
    if (this._terminal === true) {
      this._stop_poll();
      this._poll_status = "stopped";
      this._render_poll_banner();
      return;
    }
    this._schedule_poll();
    return;
  }
  /**
   * Stop the live-poll loop, clearing any pending timer.
   */
  _stop_poll() {
    if (this._poll_timer !== null) {
      clearTimeout(this._poll_timer);
      this._poll_timer = null;
    }
    return;
  }
  /**
   * Build the persistent chrome -- heading, back link, the poll
   * banner, and the body region the data render replaces.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-provisioning-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Provisioning run detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-provisioning-detail__heading");
    heading.textContent = "Provisioning run detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-provisioning-detail__back-link");
    back.setAttribute("href", "/provisioning-runs");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to provisioning runs";
    root.appendChild(back);
    const banner = document.createElement("p");
    banner.classList.add("pyc-provisioning-detail__banner");
    banner.setAttribute("data-role", "poll-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;
    root.appendChild(banner);
    const body = document.createElement("div");
    body.classList.add("pyc-provisioning-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Re-render the body region from the current run snapshot,
   * driving the loading / error / loaded states.
   */
  _render_body() {
    if (this._root === null) {
      return;
    }
    const body = this._root.querySelector('[data-role="body"]');
    if (body === null) {
      return;
    }
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-provisioning-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading provisioning run\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._run === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-provisioning-detail__status",
        "pyc-provisioning-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load this provisioning run. Try refreshing.";
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._run_summary(this._run));
    const plan_summary = this._run.plan_summary;
    if (plan_summary !== void 0 && plan_summary !== null) {
      fragment.appendChild(this._plan_summary(plan_summary));
    }
    body.replaceChildren(fragment);
    return;
  }
  /**
   * Build the run summary block -- identity, state badge,
   * action, driver, environment, timestamps, and the final-state
   * reason.
   *
   * @param run The current run snapshot.
   *
   * @returns A populated summary section element.
   */
  _run_summary(run) {
    const section = document.createElement("section");
    section.classList.add("pyc-provisioning-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Run summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-provisioning-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-provisioning-detail__run-id");
    id_value.setAttribute("data-role", "run-id");
    id_value.textContent = short_id(run.run_id);
    id_value.title = run.run_id;
    id_row.appendChild(id_value);
    const badge = document.createElement("span");
    badge.classList.add("pyc-provisioning-detail__badge");
    badge.setAttribute("data-role", "state-badge");
    badge.setAttribute("data-tone", provisioning_state_tone(run.state));
    badge.textContent = run.state;
    id_row.appendChild(badge);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-provisioning-detail__grid");
    this._append_field(grid, "Project", run.project_id);
    this._append_field(grid, "Environment", run.environment_id);
    this._append_field(grid, "Action", run.action);
    this._append_field(grid, "Driver", run.driver_name);
    this._append_field(grid, "Started", format_timestamp(run.started_at));
    this._append_field(grid, "Finished", format_timestamp(run.finished_at));
    this._append_field(
      grid,
      "Plan issued",
      format_timestamp(run.plan_issued_at)
    );
    const layer5 = run.layer5_run_id;
    if (layer5 !== void 0 && layer5 !== null && layer5.length > 0) {
      this._append_field(grid, "Layer-5 run", layer5);
    }
    const reason = run.final_state_reason;
    if (reason !== void 0 && reason !== null && reason.length > 0) {
      this._append_field(grid, "Final state reason", reason);
    }
    section.appendChild(grid);
    return section;
  }
  /**
   * Append one labelled field to a definition-list grid.
   *
   * @param grid The ``<dl>`` to append into.
   * @param label The field's display label.
   * @param value The field's display value.
   */
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-provisioning-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    def.textContent = value;
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  /**
   * Build the plan-summary section -- the aggregate add /
   * change / destroy counts plus the per-resource operation
   * list.
   *
   * @param summary The run's recorded plan summary.
   *
   * @returns A populated plan-summary section element.
   */
  _plan_summary(summary) {
    const section = document.createElement("section");
    section.classList.add("pyc-provisioning-detail__plan");
    section.setAttribute("data-role", "plan-summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Plan summary");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-provisioning-detail__section-heading");
    heading.textContent = "Plan summary";
    section.appendChild(heading);
    const counts = document.createElement("div");
    counts.classList.add("pyc-provisioning-detail__plan-counts");
    counts.appendChild(
      this._plan_count("Add", summary.resources_to_add, "ok")
    );
    counts.appendChild(
      this._plan_count("Change", summary.resources_to_change, "warn")
    );
    counts.appendChild(
      this._plan_count(
        "Destroy",
        summary.resources_to_destroy,
        "error"
      )
    );
    section.appendChild(counts);
    const ops = summary.resource_ops;
    if (ops !== void 0 && ops !== null && ops.length > 0) {
      section.appendChild(this._resource_ops(ops));
    }
    return section;
  }
  /**
   * Build one plan-count chip.
   *
   * @param label The count's display label.
   * @param value The count value.
   * @param tone The badge tone token.
   *
   * @returns A populated count-chip element.
   */
  _plan_count(label, value, tone) {
    const chip = document.createElement("div");
    chip.classList.add("pyc-provisioning-detail__plan-count");
    chip.setAttribute("data-tone", tone);
    const number = document.createElement("span");
    number.classList.add("pyc-provisioning-detail__plan-number");
    number.textContent = String(value);
    chip.appendChild(number);
    const text = document.createElement("span");
    text.classList.add("pyc-provisioning-detail__plan-label");
    text.textContent = label;
    chip.appendChild(text);
    return chip;
  }
  /**
   * Build the per-resource operations list.
   *
   * @param ops The plan summary's resource operations.
   *
   * @returns A populated operations list element.
   */
  _resource_ops(ops) {
    const list = document.createElement("ul");
    list.classList.add("pyc-provisioning-detail__op-list");
    for (const op of ops) {
      const item = document.createElement("li");
      item.classList.add("pyc-provisioning-detail__op");
      const op_chip = document.createElement("span");
      op_chip.classList.add("pyc-provisioning-detail__op-kind");
      op_chip.setAttribute("data-op", op.op);
      op_chip.textContent = op.op;
      item.appendChild(op_chip);
      const address = document.createElement("span");
      address.classList.add("pyc-provisioning-detail__op-address");
      address.textContent = op.resource_address;
      item.appendChild(address);
      list.appendChild(item);
    }
    return list;
  }
  /**
   * Update the live-poll status banner. Shows a "live updates
   * on" affordance while polling and a "run finished" note once
   * the run reaches a terminal state.
   */
  _render_poll_banner() {
    if (this._root === null) {
      return;
    }
    const banner = this._root.querySelector('[data-role="poll-banner"]');
    if (banner instanceof HTMLElement === false) {
      return;
    }
    const el = banner;
    if (this._poll_status === "polling") {
      el.hidden = false;
      el.setAttribute("data-tone", "neutral");
      el.textContent = "Provisioning run in progress \u2014 refreshing every 5 seconds.";
      return;
    }
    if (this._poll_status === "stopped" && this._terminal === true) {
      el.hidden = false;
      el.setAttribute("data-tone", "neutral");
      el.textContent = "Provisioning run finished \u2014 live updates ended.";
      return;
    }
    el.hidden = true;
    el.textContent = "";
    return;
  }
};

// src/pyc-infra-bundle/index.ts
var ORCHESTRATION_GROUP_ID = "orchestration";
var ENVIRONMENTS_READ_PERMISSION = "system:environments.read";
var PROVISIONING_READ_PERMISSION = "system:provisioning.read";
var ENVIRONMENTS_ROUTE = "/environments";
var PROVISIONING_ROUTE = "/provisioning-runs";
var ENVIRONMENTS_TAG = "pyc-environments";
var PROVISIONING_LIST_TAG = "pyc-provisioning-list";
var PROVISIONING_DETAIL_TAG = "pyc-provisioning-detail";
var INFRA_STYLESHEET_HREF = "/static/javascript/dist/pyc-infra-bundle.css";
function ensure_infra_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-infra-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = INFRA_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-infra-bundle");
  document.head.appendChild(link);
  return;
}
var ENVIRONMENTS_ENTRY = {
  entryId: "orchestration.environments",
  label: "Environments",
  route: ENVIRONMENTS_ROUTE,
  requiredPermissions: [ENVIRONMENTS_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
var PROVISIONING_ENTRY = {
  entryId: "orchestration.provisioning",
  label: "Provisioning",
  route: PROVISIONING_ROUTE,
  requiredPermissions: [PROVISIONING_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_infra_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [ENVIRONMENTS_READ_PERMISSION]
  });
  sidebar.registerEntry(ENVIRONMENTS_ENTRY);
  sidebar.registerEntry(PROVISIONING_ENTRY);
  return;
}
function define_infra_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(ENVIRONMENTS_TAG) === void 0) {
    customElements.define(ENVIRONMENTS_TAG, PycEnvironments);
  }
  if (customElements.get(PROVISIONING_LIST_TAG) === void 0) {
    customElements.define(PROVISIONING_LIST_TAG, PycProvisioningList);
  }
  if (customElements.get(PROVISIONING_DETAIL_TAG) === void 0) {
    customElements.define(PROVISIONING_DETAIL_TAG, PycProvisioningDetail);
  }
  return;
}
function classify_infra_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === ENVIRONMENTS_ROUTE || working.startsWith(ENVIRONMENTS_ROUTE + "/") === true) {
    const rtnval2 = "environments";
    return rtnval2;
  }
  if (working === PROVISIONING_ROUTE || working === PROVISIONING_ROUTE + "/") {
    const rtnval2 = "provisioning-list";
    return rtnval2;
  }
  const detail_id = run_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "provisioning-detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_infra_route(route) {
  if (route === "environments") {
    const rtnval2 = ENVIRONMENTS_TAG;
    return rtnval2;
  }
  if (route === "provisioning-list") {
    const rtnval2 = PROVISIONING_LIST_TAG;
    return rtnval2;
  }
  if (route === "provisioning-detail") {
    const rtnval2 = PROVISIONING_DETAIL_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_infra_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_infra_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_infra_route(route);
  if (target_tag.length === 0) {
    return;
  }
  const main = document.querySelector(
    "pyc-site-shell main.pyc-site-shell__main"
  );
  if (main === null) {
    return;
  }
  const existing = main.querySelector(target_tag);
  if (existing !== null) {
    return;
  }
  define_infra_elements();
  ensure_infra_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  register_infra_sidebar(handle.sidebar);
  mount_infra_view_if_active();
  return;
}
function _boot() {
  define_infra_elements();
  const target = window;
  const handle = target.pychestrateShell;
  if (handle !== void 0 && handle.sidebar !== void 0) {
    _register_against(handle);
    return;
  }
  queueMicrotask(() => {
    const retry = target.pychestrateShell;
    if (retry !== void 0 && retry.sidebar !== void 0) {
      _register_against(retry);
      return;
    }
    console.warn(
      "pychestrate.ui.infra.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
if (typeof window !== "undefined") {
  _boot();
}
export {
  DRIFT_STATES,
  ENVIRONMENT_STATES,
  PROVISIONING_ACTIONS,
  PROVISIONING_STATES,
  PycEnvironments,
  PycProvisioningDetail,
  PycProvisioningList,
  TERMINAL_PROVISIONING_STATES,
  build_drift_check_url,
  build_drift_status_url,
  build_environments_collection_url,
  build_environments_query_url,
  build_provisioning_collection_url,
  build_provisioning_detail_link,
  build_provisioning_detail_url,
  build_provisioning_query_url,
  classify_infra_route,
  define_infra_elements,
  drift_check_message_for_status,
  drift_status_label,
  drift_status_tone,
  ensure_infra_stylesheet,
  environment_state_tone,
  format_timestamp,
  has_next_page,
  has_previous_page,
  is_terminal_provisioning_state,
  is_valid_run_id,
  mount_infra_view_if_active,
  parse_driver_inputs,
  parse_environment_attrs,
  project_id_from_search,
  provisioning_state_tone,
  register_infra_sidebar,
  register_message_for_status,
  run_id_from_path,
  short_id,
  tag_for_infra_route,
  trigger_message_for_status
};
//# sourceMappingURL=pyc-infra-bundle.js.map
