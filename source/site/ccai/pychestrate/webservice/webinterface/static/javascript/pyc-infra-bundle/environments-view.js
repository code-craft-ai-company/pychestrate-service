import { hide_unless_may } from "../shared/permissions.js";
import { show_toast } from "../shared/toast.js";
import { message_with_detail, read_problem_detail } from "../shared/problem-detail.js";
import { format_clock_instant, format_instant, parse_timestamp } from "../shared/datetime.js";
import { build_empty_state, show_no_projects } from "../shared/empty-state.js";
import { choose_project_id, mirror_to_query } from "../shared/view-state.js";
import { reveal } from "../shared/reveal.js";
const ENVIRONMENT_STATES = [
  "active",
  "frozen",
  "archived",
  "destroyed"
];
const DRIFT_STATES = [
  "pending",
  "running",
  "completed",
  "failed",
  "ingest_failed",
  "skipped"
];
const DEFAULT_PER_PAGE = 25;
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
const ENVIRONMENTS_ROUTE = "/environments";
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
  const parsed = parse_timestamp(value);
  if (parsed === null) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = format_instant(parsed);
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
const ENVIRONMENT_KINDS_URL = "/api/v1/environment-kinds";
/*
 * The attributes object a kind's form describes: a text or url field is its
 * trimmed text, a number is a number, tags are a list; an empty optional field
 * is left out. ``values`` maps a field name to the text typed. Returns
 * ``{attrs}`` or ``{error}`` naming the first required field left empty or a
 * number that is not one.
 */
function build_attrs_from_fields(fields, values) {
  const attrs = {};
  for (const field of fields) {
    const raw = String(values[field.name] === undefined ? "" : values[field.name]).trim();
    if (raw.length === 0) {
      if (field.required === true) {
        return { error: field.label + " is required." };
      }
      continue;
    }
    if (field.type === "number") {
      const number = Number(raw);
      if (Number.isFinite(number) === false) {
        return { error: field.label + " must be a number." };
      }
      if (field.integer === true && Number.isInteger(number) === false) {
        return { error: field.label + " must be a whole number." };
      }
      if (typeof field.min === "number" && number < field.min) {
        return { error: field.label + " must be " + field.min + " or more." };
      }
      attrs[field.name] = number;
    } else if (field.type === "tags") {
      attrs[field.name] = raw.split(",").map((part) => part.trim()).filter((part) => part.length > 0);
    } else {
      attrs[field.name] = raw;
    }
  }
  return { attrs };
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
class PycEnvironments extends HTMLElement {
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
    hide_unless_may(register_button, "system:environments.write");
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
      this._state.projectId = choose_project_id(projects);
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
      show_no_projects(region, {});
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
    // The address describes what is on screen (ORC-27).
    mirror_to_query({ project_id: this._state.projectId });
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
      if (this._projectsNoticeKind === "empty") {
        // The notice above already says there are no projects and links to
        // creating one; a second line asking to "select a project" contradicted it.
        region.replaceChildren();
        this._render_pager();
        return;
      }
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
      const empty = build_empty_state({ class_name: "pyc-infra__status", message: "No environments registered in this project yet.", next_step: "Choose Register Environment above to add one." });
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
          // Drift checks start from the environment's detail page,
          // which says whether a check can start and shows the
          // drift history (a row button dead-ended on a 409).
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

    if (this._pager === null || this._pager === undefined) {

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
    let detail = "";
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
      detail = await read_problem_detail(response);
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
      message: message_with_detail("Drift check not started", detail, drift_check_message_for_status(status))
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
      reveal(region);
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the register-environment form into the register region: a name, a
   * kind chosen from the kinds the server has loaded, and that kind's own
   * fields (ORC-17). When the kinds cannot be listed, or a kind does not
   * describe its attributes, the kind is typed and the attributes are a JSON
   * box.
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
    const kind_region = document.createElement("div");
    kind_region.setAttribute("data-role", "register-kind-region");
    form.appendChild(kind_region);
    const attrs_region = document.createElement("div");
    attrs_region.classList.add("pyc-infra__attr-fields");
    attrs_region.setAttribute("data-role", "register-attrs-region");
    form.appendChild(attrs_region);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("variant", "primary");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "register-submit");
    submit_button.textContent = "Register Environment";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-infra__form-status");
    status.setAttribute("data-role", "register-status");
    form.appendChild(status);
    const controls = { name_input, kind_input: null, kind_select: null, attrs_area: null, fields: [], inputs: {} };
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_register(form, controls, submit_button);
    });
    this._register_region.replaceChildren(form);
    this._render_kind_controls(kind_region, attrs_region, controls, []);
    void this._load_kinds().then((kinds) => {
      if (kinds.length > 0 && this._register_region !== null && this._register_region.contains(form)) {
        this._render_kind_controls(kind_region, attrs_region, controls, kinds);
      }
    });
    return;
  }
  /* The loaded environment kinds ([] when they cannot be listed). */
  async _load_kinds() {
    try {
      const response = await fetch(ENVIRONMENT_KINDS_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        if (body !== null && Array.isArray(body.items) === true) {
          return body.items.filter((entry) => entry !== null && typeof entry.kind === "string");
        }
      }
    } catch (reason) {
      console.warn("pychestrate.ui.infra.kinds_fetch_failed", { reason: String(reason) });
    }
    return [];
  }
  /*
   * The kind control and the attribute controls under it: a list of kinds and
   * the chosen kind's fields when the kinds are known, a typed kind and a JSON
   * box when not.
   */
  _render_kind_controls(kind_region, attrs_region, controls, kinds) {
    const kind_label = document.createElement("label");
    kind_label.classList.add("pyc-infra__field");
    kind_label.textContent = "Environment kind";
    controls.kind_input = null;
    controls.kind_select = null;
    if (kinds.length > 0) {
      const select = document.createElement("mj-select");
      select.classList.add("pyc-infra__select");
      select.setAttribute("data-role", "register-kind");
      for (const entry of kinds) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", entry.kind);
        option.textContent = entry.kind;
        select.appendChild(option);
      }
      select.value = kinds[0].kind;
      const show = () => {
        const chosen = kinds.find((entry) => entry.kind === select.value);
        this._render_attribute_controls(attrs_region, controls, chosen !== undefined && Array.isArray(chosen.fields) ? chosen.fields : []);
      };
      select.addEventListener("change", show);
      kind_label.appendChild(select);
      controls.kind_select = select;
      kind_region.replaceChildren(kind_label);
      show();
      return;
    }
    const kind_input = document.createElement("mj-text-field");
    kind_input.classList.add("pyc-infra__input");
    kind_input.setAttribute("type", "text");
    kind_input.setAttribute("placeholder", "kind name");
    kind_input.setAttribute("data-role", "register-kind");
    kind_input.required = true;
    kind_label.appendChild(kind_input);
    controls.kind_input = kind_input;
    kind_region.replaceChildren(kind_label);
    this._render_attribute_controls(attrs_region, controls, []);
    return;
  }
  _render_attribute_controls(attrs_region, controls, fields) {
    controls.fields = fields;
    controls.inputs = {};
    controls.attrs_area = null;
    if (fields.length === 0) {
      const attrs_label = document.createElement("label");
      attrs_label.classList.add("pyc-infra__field", "pyc-infra__field--wide");
      attrs_label.textContent = "Attributes (JSON)";
      const attrs_area = document.createElement("mj-textarea");
      attrs_area.classList.add("pyc-infra__textarea");
      attrs_area.setAttribute("data-role", "register-attrs");
      attrs_area.setAttribute("placeholder", "{}");
      attrs_area.rows = 3;
      attrs_label.appendChild(attrs_area);
      attrs_region.replaceChildren(attrs_label);
      controls.attrs_area = attrs_area;
      return;
    }
    const wrapper = document.createDocumentFragment();
    for (const field of fields) {
      const label = document.createElement("label");
      label.classList.add("pyc-infra__field");
      label.textContent = field.label + (field.type === "tags" ? " (comma-separated)" : "") + (field.required === true ? " *" : "");
      const input = document.createElement("mj-text-field");
      input.classList.add("pyc-infra__input");
      input.setAttribute("type", field.type === "number" ? "number" : "text");
      input.setAttribute("placeholder", typeof field.hint === "string" ? field.hint : "");
      input.setAttribute("data-role", "register-field-" + field.name);
      label.appendChild(input);
      wrapper.appendChild(label);
      controls.inputs[field.name] = input;
    }
    attrs_region.replaceChildren(wrapper);
    return;
  }
  async _submit_register(form, controls, submit_button) {
    const status = form.querySelector('[data-role="register-status"]');
    const set_status = (text) => {
      if (status instanceof HTMLElement) {
        status.textContent = text;
      }
    };
    const name = controls.name_input.value.trim();
    const kind_name = controls.kind_select !== null ? String(controls.kind_select.value || "").trim() : controls.kind_input.value.trim();
    if (name.length === 0 || kind_name.length === 0) {
      set_status("Environment name and kind are required.");
      return;
    }
    let attrs = {};
    if (controls.fields.length > 0) {
      const values = {};
      for (const field of controls.fields) {
        values[field.name] = controls.inputs[field.name].value;
      }
      const built = build_attrs_from_fields(controls.fields, values);
      if (built.error !== undefined) {
        set_status(built.error);
        return;
      }
      attrs = built.attrs;
    } else {
      try {
        attrs = parse_environment_attrs(controls.attrs_area.value);
      } catch (reason) {
        set_status("Attributes must be valid JSON.");
        console.warn(
          "pychestrate.ui.infra.register_attrs_invalid",
          { reason: String(reason) }
        );
        return;
      }
    }
    submit_button.toggleAttribute("disabled", true);
    set_status("Registering environment\u2026");
    const outcome = await this._do_register(name, kind_name, attrs);
    submit_button.toggleAttribute("disabled", false);
    set_status("");
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      // Start the next registration from an empty form.
      controls.name_input.value = "";
      if (controls.kind_input !== null) {
        controls.kind_input.value = "";
      }
      if (controls.attrs_area !== null) {
        controls.attrs_area.value = "";
      }
      for (const field of controls.fields) {
        controls.inputs[field.name].value = "";
      }
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
    let detail = "";
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
      detail = await read_problem_detail(response);
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
      message: message_with_detail("Environment not registered", detail, register_message_for_status(status))
    };
    return rtnval;
  }
  /**
   * Show a toast in the toast region through the shared service: one at a
   * time, announced to assistive technology, a plain success goes away by itself.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-infra" });
    return;
  }
}
export {
  DRIFT_STATES,
  ENVIRONMENTS_ROUTE,
  ENVIRONMENT_STATES,
  PycEnvironments,
  announce_session_expired,
  build_drift_check_url,
  build_drift_status_url,
  build_environment_page_href,
  build_environments_collection_url,
  build_environments_query_url,
  drift_check_message_for_status,
  drift_status_label,
  drift_status_title,
  drift_status_tone,
  environment_state_tone,
  format_timestamp,
  has_next_page,
  has_previous_page,
  list_load_message_for_status,
  parse_environment_attrs,
  register_message_for_status,
  short_id
};
