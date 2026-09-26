// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-infra-bundle/environments-view.js
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
var PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
var ENVIRONMENTS_ROUTE = "/environments";
function build_environment_page_href(project_id, environment_id) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  const rtnval = ENVIRONMENTS_ROUTE + "/" + encodeURIComponent(environment_id) + "?" + params.toString();
  return rtnval;
}
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
  if (report.state === "pending") {
    const rtnval2 = "Recorded (pending)";
    return rtnval2;
  }
  if (report.state === "running") {
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
function drift_status_title(status) {
  if (status === null || status.has_report === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  const report = status.latest_report;
  if (report === void 0 || report === null) {
    const rtnval2 = "";
    return rtnval2;
  }
  if (report.state === "pending") {
    const rtnval2 = "Drift check recorded. Automatic processing isn't available in this release, so this check will not progress.";
    return rtnval2;
  }
  const rtnval = "";
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
    const rtnval2 = "Drift check recorded \u2014 automatic processing isn't available yet.";
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
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to check drift.";
    return rtnval2;
  }
  const rtnval = "Failed to check drift (HTTP " + String(status) + ").";
  return rtnval;
}
function list_load_message_for_status(status, what) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to " + what + ".";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This project was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the server \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load " + what + " (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function announce_session_expired() {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(
    new CustomEvent("pyc-session-401", {
      bubbles: false,
      detail: {}
    })
  );
  return;
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
  _projectsNoticeKind;
  _projects_notice_region;
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
      errored: false,
      errorStatus: 0
    };
    this._environments = [];
    this._drift = /* @__PURE__ */ new Map();
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._projects_notice_region = null;
    this._root = null;
    this._table_region = null;
    this._pager = null;
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
      errored: this._state.errored,
      errorStatus: this._state.errorStatus
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
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-infra__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
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
    const state_select = document.createElement("mj-select");
    state_select.classList.add("pyc-infra__select");
    state_select.setAttribute("data-role", "state-filter");
    const any_option = document.createElement("mj-option");
    any_option.setAttribute("value", "");
    any_option.textContent = "All states";
    state_select.appendChild(any_option);
    for (const environment_state of ENVIRONMENT_STATES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", environment_state);
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
    const register_button = document.createElement("mj-button");
    register_button.classList.add("pyc-infra__button");
    register_button.setAttribute("type", "button");
    register_button.setAttribute("data-role", "register-toggle");
    register_button.textContent = "Register Environment";
    register_button.addEventListener("click", () => {
      this._toggle_register_form();
    });
    controls.appendChild(register_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-infra__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-infra__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
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
    const pager = document.createElement("mj-pagination");
    pager.classList.add("pyc-infra__pager");
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
   * Fetch the projects collection and populate the selector.
   * Exposed so unit tests can await the bootstrap fetch cycle.
   */
  async loadProjects() {
    await this._load_projects();
    return;
  }
  async _load_projects() {
    let projects = null;
    let load_status = 0;
    let load_failed = false;
    try {
      const response = await fetch(PROJECTS_LIST_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      load_status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        projects = this._extract_projects(body);
      } else {
        load_failed = true;
      }
    } catch (reason) {
      load_failed = true;
      console.warn(
        "pychestrate.ui.infra.projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._projectsNoticeKind = "";
      this._state.projectId = projects[0].project_id;
    } else {
      this._projects = [];
      this._projectsAvailable = false;
      if (load_failed === false) {
        this._projectsNoticeKind = "empty";
      } else if (load_status === 403) {
        this._projectsNoticeKind = "forbidden";
      } else {
        this._projectsNoticeKind = "error";
      }
      if (load_status === 401) {
        announce_session_expired();
      }
    }
    this._render_project_control();
    this._render_projects_notice();
    if (this._state.projectId.length > 0) {
      await this._refresh();
    } else {
      this._render_table_region();
    }
    return;
  }
  /**
   * Render the projects-load notice -- explains why the project
   * selector degraded to the manual id input (no projects exist
   * yet, no permission to list them, or a failed fetch with a
   * retry control).
   */
  _render_projects_notice() {
    if (this._projects_notice_region === null) {
      return;
    }
    const region = this._projects_notice_region;
    if (this._projectsNoticeKind === "") {
      region.hidden = true;
      region.replaceChildren();
      return;
    }
    region.hidden = false;
    if (this._projectsNoticeKind === "empty") {
      region.classList.remove("pyc-infra__projects-notice--error");
      region.textContent = "No projects exist yet.";
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-infra__projects-notice--error");
      region.textContent = "You don't have permission to list projects.";
      return;
    }
    region.classList.add("pyc-infra__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-infra__button");
    retry.setAttribute("type", "button");
    retry.setAttribute("data-role", "projects-retry");
    retry.textContent = "Retry";
    retry.addEventListener("click", () => {
      void this._load_projects();
    });
    region.replaceChildren(message, retry);
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
    if (select instanceof HTMLElement === false || input instanceof HTMLElement === false) {
      return;
    }
    const select_el = select;
    const input_el = input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      for (const project of this._projects) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", project.project_id);
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
    this._state.errorStatus = 0;
    this._drift = /* @__PURE__ */ new Map();
    this._render_table_region();
    const url = build_environments_query_url(this._state);
    let page = null;
    let error_status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        error_status = response.status;
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
      if (error_status === 401) {
        announce_session_expired();
      }
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = error_status;
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = 0;
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
      error.textContent = list_load_message_for_status(
        this._state.errorStatus,
        "environments"
      );
      const children = [error];
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-infra__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "list-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._refresh();
        });
        children.push(retry);
      }
      region.replaceChildren(...children);
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
   * Build the environments ``<mj-table>`` from the current list.
   */
  _build_table() {
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-infra__row";
    table.rowAttrs = (environment) => ({
      "data-environment-id": environment.environment_id
    });
    table.columns = [
      {
        key: "name",
        label: "Environment",
        width: "16rem",
        render: (environment) => {
          const name = document.createElement("a");
          name.classList.add("pyc-infra__env-name", "pyc-infra__run-link");
          name.setAttribute("data-role", "environment-link");
          name.setAttribute(
            "href",
            build_environment_page_href(self._state.projectId, environment.environment_id)
          );
          name.textContent = environment.name;
          name.title = environment.environment_id;
          return name;
        }
      },
      { key: "kind_name", label: "Kind", width: "10rem" },
      {
        key: "state",
        label: "State",
        width: "8rem",
        render: (environment) => {
          const state_badge = document.createElement("mj-chip");
          state_badge.classList.add("pyc-infra__badge");
          state_badge.setAttribute(
            "data-tone",
            environment_state_tone(environment.state)
          );
          state_badge.textContent = environment.state;
          return state_badge;
        }
      },
      {
        key: "drift",
        label: "Drift (preview)",
        width: "10rem",
        sortable: false,
        render: (environment) => {
          const drift_badge = document.createElement("span");
          drift_badge.classList.add("pyc-infra__badge", "pyc-infra__drift");
          drift_badge.setAttribute("data-role", "drift-indicator");
          const status = self._drift.get(environment.environment_id) ?? null;
          drift_badge.setAttribute("data-tone", drift_status_tone(status));
          drift_badge.textContent = drift_status_label(status);
          const badge_title = drift_status_title(status);
          if (badge_title.length > 0) {
            drift_badge.title = badge_title;
          }
          return drift_badge;
        }
      },
      {
        key: "last_applied_at",
        label: "Last applied",
        width: "12rem",
        render: (environment) => format_timestamp(environment.last_applied_at)
      },
      {
        key: "actions",
        label: "Actions",
        width: "9rem",
        sortable: false,
        render: (environment) => {
          const view_link = document.createElement("a");
          view_link.classList.add("pyc-infra__run-link", "pyc-infra__row-action");
          view_link.setAttribute("data-role", "view-environment");
          view_link.setAttribute(
            "href",
            build_environment_page_href(self._state.projectId, environment.environment_id)
          );
          view_link.textContent = "Details";
          return view_link;
        }
      }
    ];
    table.rows = this._environments;
    return table;
  }
  /**
   * Update the pager controls -- enabled state + the page
   * indicator label -- from the current state.
   */
  _render_pager() {
    if (this._pager === null || this._pager === void 0) {
      return;
    }
    this._pager.setAttribute("page", String(this._state.page));
    this._pager.setAttribute("page-size", String(this._state.perPage));
    this._pager.setAttribute("total-items", String(this._state.total));
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
    const table = this._table_region.querySelector("mj-data-table.pyc-infra__table");
    if (table === null || table.shadowRoot === null) {
      return;
    }
    const selector = '.row[data-environment-id="' + environment_id + '"] [data-role="drift-indicator"]';
    const badge = table.shadowRoot.querySelector(selector);
    if (badge === null) {
      return;
    }
    const status = this._drift.get(environment_id) ?? null;
    badge.setAttribute("data-tone", drift_status_tone(status));
    badge.textContent = drift_status_label(status);
    const badge_title = drift_status_title(status);
    if (badge_title.length > 0) {
      badge.setAttribute("title", badge_title);
    } else {
      badge.removeAttribute("title");
    }
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
    button.toggleAttribute("disabled", false);
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
    const name_input = document.createElement("mj-text-field");
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
    const kind_input = document.createElement("mj-text-field");
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
    const attrs_area = document.createElement("mj-textarea");
    attrs_area.classList.add("pyc-infra__textarea");
    attrs_area.setAttribute("data-role", "register-attrs");
    attrs_area.setAttribute("placeholder", '{"region": "us-east-1"}');
    attrs_area.rows = 3;
    attrs_label.appendChild(attrs_area);
    form.appendChild(attrs_label);
    const submit_button = document.createElement("mj-button");
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
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Registering environment\u2026";
    }
    const outcome = await this._do_register(name, kind_name, attrs);
    submit_button.toggleAttribute("disabled", false);
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      name_input.value = "";
      kind_input.value = "";
      attrs_area.value = "";
      if (this._register_region !== null) {
        this._register_region.hidden = true;
      }
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
    const dismiss = document.createElement("mj-button");
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-infra-bundle/environment-detail-view.js
var PROJECTS_API_PATH2 = "/api/v1/projects";
var UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
var DRIFT_SECTION_HEADING = "Drift detection (preview)";
function environment_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = ENVIRONMENTS_ROUTE + "/";
  if (path.startsWith(prefix) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  let tail = path.slice(prefix.length);
  const query_index = tail.indexOf("?");
  if (query_index >= 0) {
    tail = tail.slice(0, query_index);
  }
  if (tail.endsWith("/") === true) {
    tail = tail.slice(0, tail.length - 1);
  }
  if (UUID_PATTERN.test(tail) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = tail;
  return rtnval;
}
function environment_project_from_search(search) {
  if (typeof search !== "string" || search.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const params = new URLSearchParams(search);
  const value = params.get("project_id");
  const rtnval = value === null ? "" : value;
  return rtnval;
}
function build_environment_detail_url(project_id, environment_id) {
  const rtnval = PROJECTS_API_PATH2 + "/" + encodeURIComponent(project_id) + "/environments/" + encodeURIComponent(environment_id);
  return rtnval;
}
function describe_drift_counts(run) {
  if (run === null || run === void 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  if (typeof run.drift_count !== "number") {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const parts = [String(run.drift_count) + " drifted"];
  if (typeof run.added === "number") {
    parts.push("+" + String(run.added));
  }
  if (typeof run.changed === "number") {
    parts.push("~" + String(run.changed));
  }
  if (typeof run.destroyed === "number") {
    parts.push("-" + String(run.destroyed));
  }
  const rtnval = parts.join(" ");
  return rtnval;
}
function drift_check_detail_message(status, detail) {
  const reason = typeof detail === "string" ? detail.trim() : "";
  if (status === 202 || status === 200) {
    const rtnval2 = "Drift check recorded. Nothing processes it yet, so it stays pending.";
    return rtnval2;
  }
  if (reason.length > 0) {
    const rtnval2 = reason;
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to check drift.";
    return rtnval2;
  }
  const rtnval = "Failed to check drift (HTTP " + String(status) + ").";
  return rtnval;
}
var PycEnvironmentDetail = class extends HTMLElement {
  _environment_id;
  _project_id;
  _environment;
  _drift;
  _loading;
  _errored;
  _root;
  _body;
  _toast_region;
  constructor() {
    super();
    this._environment_id = "";
    this._project_id = "";
    this._environment = null;
    this._drift = null;
    this._loading = false;
    this._errored = false;
    this._root = null;
    this._body = null;
    this._toast_region = null;
  }
  /**
   * Observed attributes -- ``environment-id`` and ``project-id``
   * may be supplied by a host; otherwise they are read from the URL
   * (``/environments/{id}?project_id=...``) on mount.
   */
  static get observedAttributes() {
    const rtnval = ["environment-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests.
   */
  get detailState() {
    const rtnval = {
      environmentId: this._environment_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored
    };
    return rtnval;
  }
  connectedCallback() {
    const attr_environment = this.getAttribute("environment-id");
    this._environment_id = attr_environment !== null && attr_environment.length > 0 ? attr_environment : environment_id_from_path(window.location.pathname);
    const attr_project = this.getAttribute("project-id");
    this._project_id = attr_project !== null && attr_project.length > 0 ? attr_project : environment_project_from_search(window.location.search);
    this._render_chrome();
    void this._load();
    return;
  }
  /**
   * Fetch the environment and its drift status, then render.
   * Exposed so unit tests can await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (this._environment_id.length === 0 || this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const environment = await this._fetch_json(
      build_environment_detail_url(this._project_id, this._environment_id)
    );
    const drift = await this._fetch_json(
      build_drift_status_url(this._project_id, this._environment_id)
    );
    this._environment = environment;
    this._drift = drift;
    this._loading = false;
    this._errored = environment === null;
    this._render_body();
    return;
  }
  async _fetch_json(url) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error("fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      const rtnval = body !== null && typeof body === "object" ? body : null;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.environment_detail_fetch_failed",
        { url, reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-infra");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-infra__heading");
    heading.setAttribute("data-role", "environment-heading");
    heading.textContent = "Environment";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-infra__back-link");
    back.setAttribute("href", ENVIRONMENTS_ROUTE);
    back.setAttribute("data-role", "back-link");
    back.textContent = "\u2190 All environments";
    root.appendChild(back);
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-infra__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const body = document.createElement("div");
    body.classList.add("pyc-infra__detail-body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._body = body;
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  _render_body() {
    if (this._body === null) {
      return;
    }
    const body = this._body;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-infra__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading environment\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._environment === null) {
      const error = document.createElement("p");
      error.classList.add("pyc-infra__status", "pyc-infra__status--error");
      error.setAttribute("data-role", "error-state");
      error.textContent = this._environment_id.length === 0 || this._project_id.length === 0 ? "Open an environment from the Environments list." : "Failed to load this environment. Try refreshing.";
      body.replaceChildren(error);
      return;
    }
    const environment = this._environment;
    const heading = this._root !== null ? this._root.querySelector('[data-role="environment-heading"]') : null;
    if (heading instanceof HTMLElement) {
      heading.textContent = "Environment \u2014 " + String(environment.name ?? "");
    }
    body.replaceChildren(
      this._summary(environment),
      this._drift_section()
    );
    return;
  }
  _summary(environment) {
    const section = document.createElement("section");
    section.classList.add("pyc-infra__section");
    section.setAttribute("aria-label", "Environment summary");
    const grid = document.createElement("dl");
    grid.classList.add("pyc-infra__detail-grid");
    grid.setAttribute("data-role", "environment-summary");
    this._append_field(grid, "Kind", environment.kind_name);
    const state_badge = document.createElement("mj-chip");
    state_badge.classList.add("pyc-infra__badge");
    state_badge.setAttribute("data-tone", environment_state_tone(environment.state));
    state_badge.textContent = environment.state;
    this._append_field(grid, "State", state_badge);
    this._append_field(grid, "Last applied", format_timestamp(environment.last_applied_at));
    this._append_field(grid, "Registered", format_timestamp(environment.created_at));
    if (typeof environment.frozen_reason === "string" && environment.frozen_reason.length > 0) {
      this._append_field(grid, "Frozen because", environment.frozen_reason);
    }
    if (typeof environment.archived_reason === "string" && environment.archived_reason.length > 0) {
      this._append_field(grid, "Archived because", environment.archived_reason);
    }
    this._append_field(grid, "Environment id", environment.environment_id);
    section.appendChild(grid);
    const attrs_heading = document.createElement("h2");
    attrs_heading.classList.add("pyc-infra__section-heading");
    attrs_heading.textContent = "Attributes";
    section.appendChild(attrs_heading);
    const attrs = document.createElement("pre");
    attrs.classList.add("pyc-infra__attrs");
    attrs.setAttribute("data-role", "environment-attrs");
    attrs.textContent = JSON.stringify(environment.attrs ?? {}, null, 2);
    section.appendChild(attrs);
    return section;
  }
  _drift_section() {
    const section = document.createElement("section");
    section.classList.add("pyc-infra__section");
    section.setAttribute("aria-label", "Drift detection");
    section.setAttribute("data-role", "drift-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-infra__section-heading");
    heading.textContent = DRIFT_SECTION_HEADING;
    section.appendChild(heading);
    const drift = this._drift;
    const preview = document.createElement("p");
    preview.classList.add("pyc-infra__notice", "pyc-infra__notice--preview");
    preview.setAttribute("data-role", "drift-preview-notice");
    preview.setAttribute("role", "note");
    preview.textContent = drift !== null && typeof drift.detail === "string" ? drift.detail : "Drift detection is a preview: recorded checks are not processed yet.";
    section.appendChild(preview);
    const status_line = document.createElement("p");
    status_line.classList.add("pyc-infra__drift-status");
    const status_badge = document.createElement("span");
    status_badge.classList.add("pyc-infra__badge", "pyc-infra__drift");
    status_badge.setAttribute("data-role", "drift-indicator");
    status_badge.setAttribute("data-tone", drift_status_tone(drift));
    status_badge.textContent = drift_status_label(drift);
    status_line.append("Latest check: ", status_badge);
    section.appendChild(status_line);
    const schedule = drift !== null && drift.schedule !== null && typeof drift.schedule === "object" ? drift.schedule : null;
    const schedule_line = document.createElement("p");
    schedule_line.classList.add("pyc-infra__field-caption");
    schedule_line.setAttribute("data-role", "drift-schedule");
    schedule_line.textContent = schedule !== null ? "Schedule: " + String(schedule.checker_name) + " (" + String(schedule.cron_expression) + ")" + (schedule.enabled === true ? "" : ", disabled") : "Schedule: none";
    section.appendChild(schedule_line);
    const check_available = drift !== null && drift.check_available === true;
    const check_button = document.createElement("mj-button");
    check_button.classList.add("pyc-infra__button");
    check_button.setAttribute("type", "button");
    check_button.setAttribute("data-role", "check-drift");
    check_button.textContent = "Check Drift";
    check_button.toggleAttribute("disabled", check_available === false);
    check_button.addEventListener("click", () => {
      if (check_available === false) {
        return;
      }
      check_button.toggleAttribute("disabled", true);
      void this._on_check_drift(check_button);
    });
    section.appendChild(check_button);
    if (check_available === false) {
      const reason = document.createElement("p");
      reason.classList.add("pyc-infra__field-caption");
      reason.setAttribute("data-role", "check-unavailable-reason");
      reason.textContent = drift !== null && typeof drift.check_unavailable_reason === "string" ? drift.check_unavailable_reason : "A drift check cannot start for this environment.";
      section.appendChild(reason);
    }
    section.appendChild(this._history(drift));
    return section;
  }
  _history(drift) {
    const history = drift !== null && Array.isArray(drift.history) === true ? drift.history : [];
    const wrapper = document.createElement("div");
    wrapper.classList.add("pyc-infra__table-region");
    wrapper.setAttribute("data-role", "drift-history");
    const heading = document.createElement("h3");
    heading.classList.add("pyc-infra__section-heading");
    heading.textContent = "Drift history";
    wrapper.appendChild(heading);
    if (history.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-infra__status");
      empty.setAttribute("data-role", "drift-history-empty");
      empty.textContent = "No drift checks recorded for this environment.";
      wrapper.appendChild(empty);
      return wrapper;
    }
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("data-role", "drift-history-table");
    table.rowAttrs = (run) => ({ "data-run-id": run.run_id });
    table.columns = [
      {
        key: "scheduled_for",
        label: "Requested",
        width: "12rem",
        render: (run) => format_timestamp(run.scheduled_for)
      },
      { key: "trigger_kind", label: "Trigger", width: "8rem" },
      {
        key: "state",
        label: "State",
        width: "9rem",
        render: (run) => {
          const badge = document.createElement("span");
          badge.classList.add("pyc-infra__badge");
          badge.setAttribute("data-role", "drift-run-state");
          badge.textContent = run.state;
          return badge;
        }
      },
      {
        key: "drift_count",
        label: "Drift",
        width: "10rem",
        sortable: false,
        render: (run) => describe_drift_counts(run)
      },
      { key: "checker_name", label: "Checker", width: "9rem" },
      {
        key: "final_state_reason",
        label: "Detail",
        width: "16rem",
        sortable: false,
        render: (run) => typeof run.final_state_reason === "string" && run.final_state_reason.length > 0 ? run.final_state_reason : "\u2014"
      }
    ];
    table.rows = history;
    wrapper.appendChild(table);
    return wrapper;
  }
  async _on_check_drift(button) {
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(
        build_drift_check_url(this._project_id, this._environment_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        }
      );
      status = response.status;
      try {
        const body = await response.json();
        if (body !== null && typeof body === "object" && typeof body.detail === "string" && response.ok === false) {
          detail = body.detail;
        }
      } catch (parse_reason) {
        detail = "";
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.environment_drift_check_failed",
        { reason: String(reason) }
      );
    }
    button.toggleAttribute("disabled", false);
    const ok = status === 202 || status === 200;
    this._show_toast(drift_check_detail_message(status, detail), ok === true ? "ok" : "error");
    if (ok === true) {
      await this._load();
    }
    return;
  }
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-infra__detail-field");
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    if (value instanceof HTMLElement) {
      detail.appendChild(value);
    } else {
      detail.textContent = value === null || value === void 0 || String(value).length === 0 ? "\u2014" : String(value);
    }
    field.appendChild(term);
    field.appendChild(detail);
    grid.appendChild(field);
    return;
  }
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
    const dismiss = document.createElement("mj-button");
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-infra-bundle/provisioning-list-view.js
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
var PROJECTS_API_PATH3 = "/api/v1/projects";
var PROJECTS_LIST_URL2 = PROJECTS_API_PATH3 + "?per_page=500";
function build_provisioning_query_url(state) {
  const params = new URLSearchParams();
  if (state.stateFilter.length > 0) {
    params.set("state", state.stateFilter);
  }
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  const query = params.toString();
  const rtnval = PROJECTS_API_PATH3 + "/" + encodeURIComponent(state.projectId) + "/provisioning-runs?" + query;
  return rtnval;
}
function build_provisioning_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH3 + "/" + encodeURIComponent(project_id) + "/provisioning-runs";
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
  _pager;
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
    this._pager = null;
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
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-infra__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      this._state.page = 1;
      void this._on_project_changed();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
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
    const state_select = document.createElement("mj-select");
    state_select.classList.add("pyc-infra__select");
    state_select.setAttribute("data-role", "state-filter");
    const any_option = document.createElement("mj-option");
    any_option.setAttribute("value", "");
    any_option.textContent = "All states";
    state_select.appendChild(any_option);
    for (const run_state of PROVISIONING_STATES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", run_state);
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
    const trigger_button = document.createElement("mj-button");
    trigger_button.classList.add("pyc-infra__button");
    trigger_button.setAttribute("type", "button");
    trigger_button.setAttribute("data-role", "trigger-toggle");
    trigger_button.textContent = "Trigger Provisioning";
    trigger_button.addEventListener("click", () => {
      this._toggle_trigger_form();
    });
    controls.appendChild(trigger_button);
    const refresh_button = document.createElement("mj-button");
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
    const pager = document.createElement("mj-pagination");
    pager.classList.add("pyc-infra__pager");
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
      const response = await fetch(PROJECTS_LIST_URL2, {
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
    if (select instanceof HTMLElement === false || input instanceof HTMLElement === false) {
      return;
    }
    const select_el = select;
    const input_el = input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      for (const project of this._projects) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", project.project_id);
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
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-infra__row";
    table.rowAttrs = (run) => ({ "data-run-id": run.run_id });
    table.columns = [
      {
        key: "run_id",
        label: "Run",
        width: "10rem",
        render: (run) => {
          const link = document.createElement("a");
          link.classList.add("pyc-infra__run-link");
          link.setAttribute(
            "href",
            build_provisioning_detail_link(run.project_id, run.run_id)
          );
          link.textContent = short_id(run.run_id);
          link.title = run.run_id;
          return link;
        }
      },
      { key: "action", label: "Action", width: "8rem" },
      { key: "driver_name", label: "Driver", width: "12rem" },
      {
        key: "state",
        label: "State",
        width: "10rem",
        render: (run) => {
          const badge = document.createElement("mj-chip");
          badge.classList.add("pyc-infra__badge");
          badge.setAttribute("data-tone", provisioning_state_tone(run.state));
          badge.textContent = run.state;
          return badge;
        }
      },
      {
        key: "started_at",
        label: "Started",
        width: "12rem",
        render: (run) => format_timestamp(run.started_at)
      },
      {
        key: "finished_at",
        label: "Finished",
        width: "12rem",
        render: (run) => format_timestamp(run.finished_at)
      }
    ];
    table.rows = this._runs;
    return table;
  }
  /**
   * Update the pager controls -- enabled state + the page
   * indicator label -- from the current state.
   */
  _render_pager() {
    if (this._pager === null || this._pager === void 0) {
      return;
    }
    this._pager.setAttribute("page", String(this._state.page));
    this._pager.setAttribute("page-size", String(this._state.perPage));
    this._pager.setAttribute("total-items", String(this._state.total));
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
    const environment_select = document.createElement("mj-select");
    environment_select.classList.add("pyc-infra__select");
    environment_select.setAttribute("data-role", "trigger-environment");
    if (this._environments.length === 0) {
      const none_option = document.createElement("mj-option");
      none_option.setAttribute("value", "");
      none_option.textContent = "No environment registered";
      environment_select.appendChild(none_option);
    } else {
      for (const environment of this._environments) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", environment.environment_id);
        option.textContent = environment.name + " \xB7 " + environment.kind_name;
        environment_select.appendChild(option);
      }
    }
    environment_label.appendChild(environment_select);
    form.appendChild(environment_label);
    const driver_label = document.createElement("label");
    driver_label.classList.add("pyc-infra__field");
    driver_label.textContent = "Driver name";
    const driver_input = document.createElement("mj-text-field");
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
    const action_select = document.createElement("mj-select");
    action_select.classList.add("pyc-infra__select");
    action_select.setAttribute("data-role", "trigger-action");
    for (const action of PROVISIONING_ACTIONS) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", action);
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
    const inputs_area = document.createElement("mj-textarea");
    inputs_area.classList.add("pyc-infra__textarea");
    inputs_area.setAttribute("data-role", "trigger-driver-inputs");
    inputs_area.setAttribute("placeholder", '{"auto_approve": false}');
    inputs_area.rows = 3;
    inputs_label.appendChild(inputs_area);
    form.appendChild(inputs_label);
    const submit_button = document.createElement("mj-button");
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
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Triggering provisioning run\u2026";
    }
    const outcome = await this._do_trigger(
      environment_id,
      driver_name,
      action,
      driver_inputs
    );
    submit_button.toggleAttribute("disabled", false);
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
    const dismiss = document.createElement("mj-button");
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-infra-bundle/provisioning-detail-view.js
var PROJECTS_API_PATH4 = "/api/v1/projects";
var POLL_INTERVAL_MS = 5e3;
var UUID_PATTERN2 = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
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
  const rtnval = UUID_PATTERN2.test(run_id);
  return rtnval;
}
function build_provisioning_detail_url(project_id, run_id) {
  const rtnval = PROJECTS_API_PATH4 + "/" + encodeURIComponent(project_id) + "/provisioning-runs/" + encodeURIComponent(run_id);
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
    const badge = document.createElement("mj-chip");
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-infra-bundle/guards-view.js
var PROJECTS_API_PATH5 = "/api/v1/projects";
var PROJECTS_LIST_URL3 = PROJECTS_API_PATH5 + "?per_page=500";
function build_guards_collection_url(project_id, environment_id) {
  let url = PROJECTS_API_PATH5 + "/" + encodeURIComponent(project_id) + "/blast-radius-guards";
  if (typeof environment_id === "string" && environment_id.length > 0) {
    const params = new URLSearchParams();
    params.set("environment_id", environment_id);
    url = url + "?" + params.toString();
  }
  const rtnval = url;
  return rtnval;
}
function build_guard_item_url(project_id, guard_id) {
  const rtnval = PROJECTS_API_PATH5 + "/" + encodeURIComponent(project_id) + "/blast-radius-guards/" + encodeURIComponent(guard_id);
  return rtnval;
}
function build_guards_evaluate_url(project_id) {
  const rtnval = PROJECTS_API_PATH5 + "/" + encodeURIComponent(project_id) + "/blast-radius-guards:evaluate";
  return rtnval;
}
function format_guard_timestamp(value) {
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
function guard_enabled_tone(enabled) {
  if (enabled === true) {
    const rtnval2 = "ok";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function verdict_tone(verdict) {
  if (typeof verdict !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = verdict.toLowerCase();
  if (lowered === "allow" || lowered === "allowed" || lowered === "pass") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "deny" || lowered === "denied" || lowered === "block" || lowered === "fail") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function attach_message_for_status(status) {
  if (status === 201 || status === 200) {
    const rtnval2 = "Guard attached.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "That rule is already attached to the environment.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The guard request was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project, environment, or rule.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to attach guards.";
    return rtnval2;
  }
  const rtnval = "Failed to attach guard (HTTP " + String(status) + ").";
  return rtnval;
}
function toggle_message_for_status(status, enabled) {
  if (status === 200) {
    const rtnval2 = enabled === true ? "Guard enabled." : "Guard disabled.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown guard.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to change guards.";
    return rtnval2;
  }
  const rtnval = "Failed to update guard (HTTP " + String(status) + ").";
  return rtnval;
}
function parse_actor_roles(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = [];
    return rtnval2;
  }
  const pieces = raw.split(",");
  const rtnval = [];
  for (const piece of pieces) {
    const trimmed = piece.trim();
    if (trimmed.length > 0) {
      rtnval.push(trimmed);
    }
  }
  return rtnval;
}
var UUID_PATTERN3 = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function is_complete_uuid(value) {
  if (typeof value !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN3.test(value.trim());
  return rtnval;
}
async function problem_detail_of(response) {
  try {
    const body = await response.json();
    if (body !== null && typeof body === "object" && typeof body.detail === "string") {
      const rtnval2 = body.detail.split(/\r?\n/)[0].trim();
      return rtnval2;
    }
  } catch (reason) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function extract_guard_projects(body) {
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
var PycGuards = class extends HTMLElement {
  _state;
  _guards;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _projects_notice_region;
  _environments;
  _environmentsAvailable;
  /**
   * True when the project's environment list could not be read
   * (the picker then falls back to typing a full environment id).
   */
  _environmentsLoadFailed;
  _environment_filter_slot;
  _root;
  _table_region;
  _attach_region;
  _evaluate_region;
  _toast_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      environmentFilter: "",
      loading: false,
      errored: false,
      errorStatus: 0,
      errorDetail: "",
      total: 0
    };
    this._guards = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._projects_notice_region = null;
    this._environments = [];
    this._environmentsAvailable = false;
    this._environmentsLoadFailed = false;
    this._environment_filter_slot = null;
    this._root = null;
    this._table_region = null;
    this._attach_region = null;
    this._evaluate_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + filter state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
      environmentFilter: this._state.environmentFilter,
      loading: this._state.loading,
      errored: this._state.errored,
      errorStatus: this._state.errorStatus,
      total: this._state.total
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
   * environment filter, attach + evaluate actions, table region,
   * evaluate panel, toast region.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-infra");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-infra__heading");
    heading.textContent = "Blast-Radius Guards";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-infra__controls");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-infra__field");
    project_label.textContent = "Project";
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-infra__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      void this._on_project_changed(project_select.value);
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-infra__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      void this._on_project_changed(project_input.value.trim());
    });
    controls.appendChild(project_input);
    const env_label = document.createElement("label");
    env_label.classList.add("pyc-infra__field");
    env_label.textContent = "Environment";
    const env_slot = document.createElement("span");
    env_slot.classList.add("pyc-infra__control-slot");
    env_slot.setAttribute("data-role", "environment-filter-slot");
    env_label.appendChild(env_slot);
    controls.appendChild(env_label);
    this._environment_filter_slot = env_slot;
    const attach_button = document.createElement("mj-button");
    attach_button.classList.add("pyc-infra__button");
    attach_button.setAttribute("type", "button");
    attach_button.setAttribute("data-role", "attach-toggle");
    attach_button.textContent = "Attach Guard";
    attach_button.addEventListener("click", () => {
      this._toggle_attach_form();
    });
    controls.appendChild(attach_button);
    const evaluate_button = document.createElement("mj-button");
    evaluate_button.classList.add("pyc-infra__button");
    evaluate_button.setAttribute("type", "button");
    evaluate_button.setAttribute("data-role", "evaluate-toggle");
    evaluate_button.textContent = "Evaluate Preview";
    evaluate_button.addEventListener("click", () => {
      this._toggle_evaluate_panel();
    });
    controls.appendChild(evaluate_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-infra__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-infra__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    const attach_region = document.createElement("div");
    attach_region.classList.add("pyc-infra__form-region");
    attach_region.setAttribute("data-role", "attach-region");
    attach_region.hidden = true;
    root.appendChild(attach_region);
    this._attach_region = attach_region;
    const evaluate_region = document.createElement("div");
    evaluate_region.classList.add("pyc-infra__form-region");
    evaluate_region.setAttribute("data-role", "evaluate-region");
    evaluate_region.hidden = true;
    root.appendChild(evaluate_region);
    this._evaluate_region = evaluate_region;
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
    this._root = root;
    this.replaceChildren(root);
    this._render_environment_filter();
    return;
  }
  /**
   * Switch to another project: forget the environment chosen for the
   * previous one, load the new project's environments (which picks
   * the first), then load its guards.
   *
   * @param project_id The newly selected project id.
   */
  async _on_project_changed(project_id) {
    this._state.projectId = project_id;
    this._state.environmentFilter = "";
    await this._load_environments();
    await this._refresh();
    return;
  }
  /**
   * Render the environment picker into the controls. With the
   * project's environments loaded it is a select over them; when
   * the project has none it says so; only when the list could not
   * be read does it fall back to typing a full environment id.
   */
  _render_environment_filter() {
    if (this._environment_filter_slot === null) {
      return;
    }
    const slot = this._environment_filter_slot;
    if (this._state.projectId.length === 0) {
      const waiting = document.createElement("span");
      waiting.classList.add("pyc-infra__field-caption");
      waiting.setAttribute("data-role", "environment-filter-empty");
      waiting.textContent = "Select a project first";
      slot.replaceChildren(waiting);
      return;
    }
    if (this._environmentsAvailable === true) {
      const select = document.createElement("mj-select");
      select.classList.add("pyc-infra__select");
      select.setAttribute("data-role", "environment-filter");
      select.setAttribute("aria-label", "Environment");
      for (const environment of this._environments) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", environment.environment_id);
        option.textContent = environment.name + " (" + short_id(environment.environment_id) + ")";
        if (environment.environment_id === this._state.environmentFilter) {
          option.setAttribute("selected", "");
        }
        select.appendChild(option);
      }
      select.value = this._state.environmentFilter;
      select.addEventListener("change", () => {
        this._state.environmentFilter = select.value;
        void this._refresh();
      });
      slot.replaceChildren(select);
      return;
    }
    if (this._environmentsLoadFailed === false) {
      const none = document.createElement("span");
      none.classList.add("pyc-infra__field-caption");
      none.setAttribute("data-role", "environment-filter-empty");
      none.textContent = "This project has no environments \u2014 register one on the Environments page.";
      slot.replaceChildren(none);
      return;
    }
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-infra__input");
    input.setAttribute("type", "text");
    input.setAttribute("placeholder", "full environment id (UUID)");
    input.setAttribute("aria-label", "Environment id");
    input.setAttribute("data-role", "environment-filter");
    input.value = this._state.environmentFilter;
    input.addEventListener("change", () => {
      this._state.environmentFilter = input.value.trim();
      void this._refresh();
    });
    slot.replaceChildren(input);
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
    let load_status = 0;
    let load_failed = false;
    try {
      const response = await fetch(PROJECTS_LIST_URL3, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      load_status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        projects = extract_guard_projects(body);
      } else {
        load_failed = true;
      }
    } catch (reason) {
      load_failed = true;
      console.warn(
        "pychestrate.ui.infra.guard_projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._projectsNoticeKind = "";
      this._state.projectId = projects[0].project_id;
    } else {
      this._projects = [];
      this._projectsAvailable = false;
      if (load_failed === false) {
        this._projectsNoticeKind = "empty";
      } else if (load_status === 403) {
        this._projectsNoticeKind = "forbidden";
      } else {
        this._projectsNoticeKind = "error";
      }
      if (load_status === 401) {
        announce_session_expired();
      }
    }
    this._render_project_control();
    this._render_projects_notice();
    if (this._state.projectId.length > 0) {
      await this._load_environments();
      await this._refresh();
    } else {
      this._render_table_region();
    }
    return;
  }
  /**
   * Render the projects-load notice -- explains why the project
   * selector degraded to the manual id input (no projects exist
   * yet, no permission to list them, or a failed fetch with a
   * retry control).
   */
  _render_projects_notice() {
    if (this._projects_notice_region === null) {
      return;
    }
    const region = this._projects_notice_region;
    if (this._projectsNoticeKind === "") {
      region.hidden = true;
      region.replaceChildren();
      return;
    }
    region.hidden = false;
    if (this._projectsNoticeKind === "empty") {
      region.classList.remove("pyc-infra__projects-notice--error");
      region.textContent = "No projects exist yet.";
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-infra__projects-notice--error");
      region.textContent = "You don't have permission to list projects.";
      return;
    }
    region.classList.add("pyc-infra__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-infra__button");
    retry.setAttribute("type", "button");
    retry.setAttribute("data-role", "projects-retry");
    retry.textContent = "Retry";
    retry.addEventListener("click", () => {
      void this._load_projects();
    });
    region.replaceChildren(message, retry);
    return;
  }
  /**
   * Fetch the environments of the active project so the attach /
   * evaluate forms can offer an environment picker instead of a
   * hand-typed UUID. Exposed so unit tests can await the fetch.
   */
  async loadEnvironments() {
    await this._load_environments();
    return;
  }
  async _load_environments() {
    let environments = [];
    let available = false;
    let load_failed = false;
    if (this._state.projectId.length > 0) {
      try {
        const url = build_environments_collection_url(
          this._state.projectId
        ) + "?per_page=200";
        const response = await fetch(url, {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        });
        if (response.ok === false) {
          load_failed = true;
        }
        if (response.ok === true) {
          const body = await response.json();
          const page = body;
          if (page !== null && Array.isArray(page.items) === true) {
            for (const item of page.items) {
              if (item === null || typeof item !== "object") {
                continue;
              }
              const environment_id = item.environment_id;
              if (typeof environment_id !== "string" || environment_id.length === 0) {
                continue;
              }
              const name = typeof item.name === "string" && item.name.length > 0 ? item.name : environment_id;
              environments.push({ environment_id, name });
            }
            available = environments.length > 0;
          }
        }
      } catch (reason) {
        load_failed = true;
        console.warn(
          "pychestrate.ui.infra.guard_environments_fetch_failed",
          { reason: String(reason) }
        );
      }
    }
    this._environments = environments;
    this._environmentsAvailable = available;
    this._environmentsLoadFailed = load_failed;
    if (available === true) {
      const known = environments.some(
        (environment) => environment.environment_id === this._state.environmentFilter
      );
      if (known === false) {
        this._state.environmentFilter = environments[0].environment_id;
      }
    } else if (load_failed === false) {
      this._state.environmentFilter = "";
    }
    this._render_environment_filter();
    if (this._attach_region !== null && this._attach_region.hidden === false) {
      this._render_attach_form();
    }
    if (this._evaluate_region !== null && this._evaluate_region.hidden === false) {
      this._render_evaluate_panel();
    }
    return;
  }
  /**
   * Build the environment control for the attach / evaluate
   * forms -- an ``mj-select`` over the fetched environments when
   * available, else a labelled text input fallback.
   *
   * @param role The ``data-role`` value for test selection.
   *
   * @returns The control element (read its ``value``).
   */
  _build_environment_control(role) {
    if (this._environmentsAvailable === true) {
      const select = document.createElement("mj-select");
      select.classList.add("pyc-infra__select");
      select.setAttribute("data-role", role);
      for (const environment of this._environments) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", environment.environment_id);
        option.textContent = environment.name + " (" + short_id(environment.environment_id) + ")";
        select.appendChild(option);
      }
      const rtnval2 = select;
      return rtnval2;
    }
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-infra__input");
    input.setAttribute("type", "text");
    input.setAttribute("placeholder", "full environment id (UUID) -- no environments listed for this project");
    input.setAttribute("data-role", role);
    input.required = true;
    const rtnval = input;
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
    if (select instanceof HTMLElement === false || input instanceof HTMLElement === false) {
      return;
    }
    const select_el = select;
    const input_el = input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      for (const project of this._projects) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", project.project_id);
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
   * Fetch the guard list for the active project and re-render
   * the table. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._guards = [];
      this._render_table_region();
      return;
    }
    if (this._state.environmentFilter.length === 0) {
      this._guards = [];
      this._render_table_region();
      return;
    }
    if (is_complete_uuid(this._state.environmentFilter) === false) {
      this._guards = [];
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = 422;
      this._state.errorDetail = "Enter a complete environment id (a UUID).";
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._state.errorDetail = "";
    this._render_table_region();
    const url = build_guards_collection_url(
      this._state.projectId,
      this._state.environmentFilter
    );
    let page = null;
    let error_status = 0;
    let error_detail = "";
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        error_status = response.status;
        if (error_status >= 400 && error_status < 500) {
          error_detail = await problem_detail_of(response);
        }
        throw new Error(
          "guards fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.guards_fetch_failed",
        { reason: String(reason) }
      );
      if (error_status === 401) {
        announce_session_expired();
      }
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = error_status;
      this._state.errorDetail = error_detail;
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = 0;
      this._render_table_region();
      return;
    }
    this._guards = page.items;
    const meta = page.meta;
    if (meta !== void 0 && meta !== null) {
      if (typeof meta.total === "number") {
        this._state.total = meta.total;
      }
    }
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
    return;
  }
  /**
   * Re-render the table region from the current state + guards.
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
      notice.textContent = "Select a project to view its guards.";
      region.replaceChildren(notice);
      return;
    }
    if (this._state.environmentFilter.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-infra__status");
      notice.setAttribute("data-role", "no-environment-state");
      notice.textContent = "Select an environment to view its guards.";
      region.replaceChildren(notice);
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-infra__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading guards\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-infra__status",
        "pyc-infra__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = this._state.errorDetail.length > 0 ? this._state.errorDetail : list_load_message_for_status(
        this._state.errorStatus,
        "guards"
      );
      const children = [error];
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-infra__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "list-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._refresh();
        });
        children.push(retry);
      }
      region.replaceChildren(...children);
      return;
    }
    if (this._guards.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-infra__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No blast-radius guards attached yet";
      region.replaceChildren(empty);
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    return;
  }
  /**
   * Build the guards ``<table>`` from the current list, ordered
   * by environment so guards are grouped per environment.
   */
  _build_table() {
    const self = this;
    const ordered = this._guards.slice();
    ordered.sort((left, right) => {
      if (left.environment_id < right.environment_id) {
        return -1;
      }
      if (left.environment_id > right.environment_id) {
        return 1;
      }
      return 0;
    });
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-infra__row";
    table.rowAttrs = (guard) => ({ "data-guard-id": guard.guard_id });
    table.columns = [
      { key: "environment_id", label: "Environment", width: "16rem" },
      { key: "rule_id", label: "Rule", width: "16rem" },
      {
        key: "enabled",
        label: "State",
        width: "8rem",
        render: (guard) => {
          const state_badge = document.createElement("mj-chip");
          state_badge.classList.add("pyc-infra__badge");
          state_badge.setAttribute("data-role", "enabled-indicator");
          state_badge.setAttribute(
            "data-tone",
            guard_enabled_tone(guard.enabled)
          );
          state_badge.textContent = guard.enabled === true ? "enabled" : "disabled";
          return state_badge;
        }
      },
      {
        key: "added_at",
        label: "Added",
        width: "12rem",
        render: (guard) => format_guard_timestamp(guard.added_at)
      },
      {
        key: "actions",
        label: "Actions",
        width: "8rem",
        sortable: false,
        render: (guard) => {
          const toggle_button = document.createElement("mj-button");
          toggle_button.classList.add(
            "pyc-infra__button",
            "pyc-infra__row-action"
          );
          toggle_button.setAttribute("type", "button");
          toggle_button.setAttribute("data-role", "toggle-guard");
          toggle_button.textContent = guard.enabled === true ? "Disable" : "Enable";
          toggle_button.addEventListener("click", () => {
            toggle_button.toggleAttribute("disabled", true);
            void self._on_toggle(guard, toggle_button);
          });
          return toggle_button;
        }
      }
    ];
    table.rows = ordered;
    return table;
  }
  /**
   * Run the enable/disable toggle for one guard -- PATCH the
   * flag then refresh the list, surfacing a toast.
   *
   * @param guard The guard to toggle.
   * @param button The row action button, re-enabled on completion.
   */
  async _on_toggle(guard, button) {
    const next_enabled = guard.enabled === false;
    const outcome = await this._do_toggle(guard.guard_id, next_enabled);
    button.toggleAttribute("disabled", false);
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
   * PATCH a guard's ``enabled`` flag. Exposed so unit tests can
   * drive a toggle without a row button.
   *
   * @param guard_id The guard to update.
   * @param enabled The desired ``enabled`` flag.
   *
   * @returns The toggle outcome.
   */
  async toggleGuard(guard_id, enabled) {
    const rtnval = await this._do_toggle(guard_id, enabled);
    return rtnval;
  }
  async _do_toggle(guard_id, enabled) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        message: "Select a project before changing guards."
      };
      return rtnval2;
    }
    let status = 0;
    try {
      const url = build_guard_item_url(
        this._state.projectId,
        guard_id
      );
      const response = await fetch(url, {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ enabled })
      });
      status = response.status;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.guard_toggle_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: "Failed to reach the guards service."
      };
      return rtnval2;
    }
    const rtnval = {
      ok: status === 200,
      status,
      message: toggle_message_for_status(status, enabled)
    };
    return rtnval;
  }
  /**
   * Toggle the inline attach-guard form's visibility, rendering
   * it on first reveal.
   */
  _toggle_attach_form() {
    if (this._attach_region === null) {
      return;
    }
    const region = this._attach_region;
    if (region.hidden === true) {
      this._render_attach_form();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the attach-guard form into the attach region.
   */
  _render_attach_form() {
    if (this._attach_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-infra__form");
    form.setAttribute("data-role", "attach-form");
    const env_label = document.createElement("label");
    env_label.classList.add("pyc-infra__field");
    env_label.textContent = "Environment";
    const env_input = this._build_environment_control("attach-environment");
    env_label.appendChild(env_input);
    form.appendChild(env_label);
    const rule_label = document.createElement("label");
    rule_label.classList.add("pyc-infra__field");
    rule_label.textContent = "Rule id (registry rule id)";
    const rule_input = document.createElement("mj-text-field");
    rule_input.classList.add("pyc-infra__input");
    rule_input.setAttribute("type", "text");
    rule_input.setAttribute("placeholder", "FrozenEnvBlockRule");
    rule_input.setAttribute("data-role", "attach-rule");
    rule_input.required = true;
    rule_label.appendChild(rule_input);
    const rule_caption = document.createElement("span");
    rule_caption.classList.add("pyc-infra__field-caption");
    rule_caption.setAttribute("data-role", "attach-rule-caption");
    rule_caption.textContent = "Rule ids come from the guard-rule registry \u2014 run Evaluate Preview to list every registered rule id.";
    rule_label.appendChild(rule_caption);
    form.appendChild(rule_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "attach-submit");
    submit_button.textContent = "Attach Guard";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-infra__form-status");
    status.setAttribute("data-role", "attach-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_attach(
        form,
        env_input,
        rule_input,
        submit_button
      );
    });
    this._attach_region.replaceChildren(form);
    return;
  }
  async _submit_attach(form, env_input, rule_input, submit_button) {
    const status = form.querySelector('[data-role="attach-status"]');
    const environment_id = env_input.value.trim();
    const rule_id = rule_input.value.trim();
    if (environment_id.length === 0 || rule_id.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Environment id and rule id are required.";
      }
      return;
    }
    if (is_complete_uuid(environment_id) === false) {
      if (status instanceof HTMLElement) {
        status.textContent = "Enter a complete environment id (a UUID).";
      }
      return;
    }
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Attaching guard\u2026";
    }
    const outcome = await this._do_attach(environment_id, rule_id);
    submit_button.toggleAttribute("disabled", false);
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
   * POST a ``BlastRadiusGuardCreateRequest``. Exposed so unit
   * tests can invoke an attach without a real form-submit event.
   *
   * @param environment_id The environment to attach the guard to.
   * @param rule_id The blast-radius rule identifier.
   *
   * @returns The attach outcome.
   */
  async attachGuard(environment_id, rule_id) {
    const rtnval = await this._do_attach(environment_id, rule_id);
    return rtnval;
  }
  async _do_attach(environment_id, rule_id) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        guardId: "",
        message: "Select a project before attaching a guard."
      };
      return rtnval2;
    }
    const payload = {
      environment_id,
      rule_id,
      enabled: true
    };
    let status = 0;
    let guard_id = "";
    let detail = "";
    try {
      const url = build_guards_collection_url(
        this._state.projectId,
        ""
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
        const guard = body;
        if (guard !== null && typeof guard.guard_id === "string") {
          guard_id = guard.guard_id;
        }
      } else if (status === 422) {
        detail = await problem_detail_of(response);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.guard_attach_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        guardId: "",
        message: "Failed to reach the guards service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      guardId: guard_id,
      message: detail.length > 0 ? "Guard not attached: " + detail : attach_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Toggle the evaluate-preview panel's visibility, rendering it
   * on first reveal.
   */
  _toggle_evaluate_panel() {
    if (this._evaluate_region === null) {
      return;
    }
    const region = this._evaluate_region;
    if (region.hidden === true) {
      this._render_evaluate_panel();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the evaluate-preview panel -- an environment id +
   * action + actor-roles form plus a verdict-trace output region.
   */
  _render_evaluate_panel() {
    if (this._evaluate_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-infra__form");
    form.setAttribute("data-role", "evaluate-form");
    const env_label = document.createElement("label");
    env_label.classList.add("pyc-infra__field");
    env_label.textContent = "Environment";
    const env_input = this._build_environment_control("evaluate-environment");
    env_label.appendChild(env_input);
    form.appendChild(env_label);
    const action_label = document.createElement("label");
    action_label.classList.add("pyc-infra__field");
    action_label.textContent = "Action";
    const action_input = document.createElement("mj-text-field");
    action_input.classList.add("pyc-infra__input");
    action_input.setAttribute("type", "text");
    action_input.setAttribute("placeholder", "environment.destroy");
    action_input.setAttribute("data-role", "evaluate-action");
    action_input.required = true;
    action_label.appendChild(action_input);
    form.appendChild(action_label);
    const roles_label = document.createElement("label");
    roles_label.classList.add("pyc-infra__field");
    roles_label.textContent = "Actor roles (comma-separated)";
    const roles_input = document.createElement("mj-text-field");
    roles_input.classList.add("pyc-infra__input");
    roles_input.setAttribute("type", "text");
    roles_input.setAttribute("placeholder", "operator, release-manager");
    roles_input.setAttribute("data-role", "evaluate-roles");
    roles_label.appendChild(roles_input);
    form.appendChild(roles_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "evaluate-submit");
    submit_button.textContent = "Evaluate";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-infra__form-status");
    status.setAttribute("data-role", "evaluate-status");
    form.appendChild(status);
    const output = document.createElement("div");
    output.classList.add("pyc-infra__table-region");
    output.setAttribute("data-role", "evaluate-output");
    form.appendChild(output);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_evaluate(
        form,
        env_input,
        action_input,
        roles_input,
        submit_button,
        output
      );
    });
    this._evaluate_region.replaceChildren(form);
    return;
  }
  async _submit_evaluate(form, env_input, action_input, roles_input, submit_button, output) {
    const status = form.querySelector('[data-role="evaluate-status"]');
    const environment_id = env_input.value.trim();
    const action = action_input.value.trim();
    if (environment_id.length === 0 || action.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Environment id and action are required.";
      }
      return;
    }
    if (is_complete_uuid(environment_id) === false) {
      if (status instanceof HTMLElement) {
        status.textContent = "Enter a complete environment id (a UUID).";
      }
      return;
    }
    const roles = parse_actor_roles(roles_input.value);
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Evaluating\u2026";
    }
    const outcome = await this._do_evaluate(
      environment_id,
      action,
      roles
    );
    submit_button.toggleAttribute("disabled", false);
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._render_evaluate_output(output, outcome);
    return;
  }
  /**
   * POST a guard-evaluation request. Exposed so unit tests can
   * drive an evaluation without a real form-submit event.
   *
   * @param environment_id The environment to evaluate against.
   * @param action The orchestration action to test.
   * @param actor_role_set The actor's role set.
   *
   * @returns The evaluation outcome.
   */
  async evaluateGuards(environment_id, action, actor_role_set) {
    const rtnval = await this._do_evaluate(
      environment_id,
      action,
      actor_role_set
    );
    return rtnval;
  }
  async _do_evaluate(environment_id, action, actor_role_set) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        evaluation: null,
        message: "Select a project before evaluating guards."
      };
      return rtnval2;
    }
    const payload = {
      environment_id,
      action,
      actor_role_set
    };
    let status = 0;
    let evaluation = null;
    try {
      const url = build_guards_evaluate_url(this._state.projectId);
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
        const parsed = body;
        if (parsed !== null && typeof parsed.allowed === "boolean") {
          evaluation = parsed;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.guard_evaluate_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        evaluation: null,
        message: "Failed to reach the guards service."
      };
      return rtnval2;
    }
    if (status === 200 && evaluation !== null) {
      const rtnval2 = {
        ok: true,
        status,
        evaluation,
        message: evaluation.allowed === true ? "Action would be allowed." : "Action would be blocked."
      };
      return rtnval2;
    }
    const rtnval = {
      ok: false,
      status,
      evaluation: null,
      message: "Failed to evaluate guards (HTTP " + String(status) + ")."
    };
    return rtnval;
  }
  /**
   * Render the verdict trace of a guard evaluation into the
   * panel output region.
   *
   * @param output The panel output region element.
   * @param outcome The evaluation outcome to render.
   */
  _render_evaluate_output(output, outcome) {
    if (outcome.evaluation === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-infra__status",
        "pyc-infra__status--error"
      );
      error.setAttribute("data-role", "evaluate-error");
      error.textContent = outcome.message;
      output.replaceChildren(error);
      return;
    }
    const evaluation = outcome.evaluation;
    const verdict = document.createElement("p");
    verdict.classList.add("pyc-infra__status");
    verdict.setAttribute("data-role", "evaluate-verdict");
    const verdict_badge = document.createElement("mj-chip");
    verdict_badge.classList.add("pyc-infra__badge");
    verdict_badge.setAttribute(
      "data-tone",
      evaluation.allowed === true ? "ok" : "error"
    );
    verdict_badge.textContent = evaluation.allowed === true ? "Allowed" : "Blocked";
    verdict.appendChild(verdict_badge);
    output.replaceChildren(verdict);
    if (evaluation.entries.length === 0) {
      return;
    }
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.setAttribute("data-role", "evaluate-trace");
    table.columns = [
      { key: "rule_id", label: "Rule", width: "16rem" },
      {
        key: "verdict",
        label: "Verdict",
        width: "10rem",
        render: (entry) => {
          const badge = document.createElement("mj-chip");
          badge.classList.add("pyc-infra__badge");
          badge.setAttribute("data-tone", verdict_tone(entry.verdict));
          badge.textContent = entry.verdict;
          return badge;
        }
      },
      {
        key: "reason",
        label: "Reason",
        width: "20rem",
        render: (entry) => entry.reason ?? "\u2014"
      }
    ];
    table.rows = evaluation.entries;
    output.appendChild(table);
    return;
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
    const dismiss = document.createElement("mj-button");
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-infra-bundle/index.entry.js
var ORCHESTRATION_GROUP_ID = "orchestration";
var ENVIRONMENTS_READ_PERMISSION = "system:environments.read";
var PROVISIONING_READ_PERMISSION = "system:provisioning.read";
var GUARDS_READ_PERMISSION = "system:guards.read";
var ENVIRONMENTS_ROUTE2 = "/environments";
var PROVISIONING_ROUTE = "/provisioning-runs";
var GUARDS_ROUTE = "/blast-radius-guards";
var ENVIRONMENTS_TAG = "pyc-environments";
var ENVIRONMENT_DETAIL_TAG = "pyc-environment-detail";
var PROVISIONING_LIST_TAG = "pyc-provisioning-list";
var PROVISIONING_DETAIL_TAG = "pyc-provisioning-detail";
var GUARDS_TAG = "pyc-guards";
var INFRA_STYLESHEET_HREF = "/static/javascript/pyc-infra-bundle/pyc-infra-bundle.css";
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
  route: ENVIRONMENTS_ROUTE2,
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
var GUARDS_ENTRY = {
  entryId: "orchestration.guards",
  label: "Blast-Radius Guards",
  route: GUARDS_ROUTE,
  requiredPermissions: [GUARDS_READ_PERMISSION],
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
  sidebar.registerEntry(GUARDS_ENTRY);
  return;
}
function define_infra_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(ENVIRONMENTS_TAG) === void 0) {
    customElements.define(ENVIRONMENTS_TAG, PycEnvironments);
  }
  if (customElements.get(ENVIRONMENT_DETAIL_TAG) === void 0) {
    customElements.define(ENVIRONMENT_DETAIL_TAG, PycEnvironmentDetail);
  }
  if (customElements.get(PROVISIONING_LIST_TAG) === void 0) {
    customElements.define(PROVISIONING_LIST_TAG, PycProvisioningList);
  }
  if (customElements.get(PROVISIONING_DETAIL_TAG) === void 0) {
    customElements.define(PROVISIONING_DETAIL_TAG, PycProvisioningDetail);
  }
  if (customElements.get(GUARDS_TAG) === void 0) {
    customElements.define(GUARDS_TAG, PycGuards);
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
  if (environment_id_from_path(working).length > 0) {
    const rtnval2 = "environment-detail";
    return rtnval2;
  }
  if (working === ENVIRONMENTS_ROUTE2 || working.startsWith(ENVIRONMENTS_ROUTE2 + "/") === true) {
    const rtnval2 = "environments";
    return rtnval2;
  }
  if (working === PROVISIONING_ROUTE || working === PROVISIONING_ROUTE + "/") {
    const rtnval2 = "provisioning-list";
    return rtnval2;
  }
  if (working === GUARDS_ROUTE || working.startsWith(GUARDS_ROUTE + "/") === true) {
    const rtnval2 = "guards";
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
  if (route === "environment-detail") {
    const rtnval2 = ENVIRONMENT_DETAIL_TAG;
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
  if (route === "guards") {
    const rtnval2 = GUARDS_TAG;
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
  PycGuards,
  PycProvisioningDetail,
  PycProvisioningList,
  TERMINAL_PROVISIONING_STATES,
  announce_session_expired,
  attach_message_for_status,
  build_drift_check_url,
  build_drift_status_url,
  build_environments_collection_url,
  build_environments_query_url,
  build_guard_item_url,
  build_guards_collection_url,
  build_guards_evaluate_url,
  build_provisioning_collection_url,
  build_provisioning_detail_link,
  build_provisioning_detail_url,
  build_provisioning_query_url,
  classify_infra_route,
  define_infra_elements,
  drift_check_message_for_status,
  drift_status_label,
  drift_status_title,
  drift_status_tone,
  ensure_infra_stylesheet,
  environment_state_tone,
  extract_guard_projects,
  format_guard_timestamp,
  format_timestamp,
  guard_enabled_tone,
  has_next_page,
  has_previous_page,
  is_terminal_provisioning_state,
  is_valid_run_id,
  list_load_message_for_status,
  mount_infra_view_if_active,
  parse_actor_roles,
  parse_driver_inputs,
  parse_environment_attrs,
  project_id_from_search,
  provisioning_state_tone,
  register_infra_sidebar,
  register_message_for_status,
  run_id_from_path,
  short_id,
  tag_for_infra_route,
  toggle_message_for_status,
  trigger_message_for_status,
  verdict_tone
};
