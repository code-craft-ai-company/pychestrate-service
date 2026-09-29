import { format_clock_instant, format_duration, format_instant, parse_timestamp } from "../shared/datetime.js";
import { build_source_label, build_title } from "../shared/run-labels.js";
const BUILD_STATES = [
  "pending",
  "running",
  "completed",
  "failed",
  "cancelled"
];
const TERMINAL_BUILD_STATES = [
  "completed",
  "failed",
  "cancelled"
];
const DEFAULT_PER_PAGE = 25;
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
function build_builds_query_url(state) {
  const params = new URLSearchParams();
  if (state.stateFilter.length > 0) {
    params.set("state", state.stateFilter);
  }
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  const query = params.toString();
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(state.projectId) + "/builds?" + query;
  return rtnval;
}
function build_builds_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/builds";
  return rtnval;
}
function build_build_detail_link(project_id, run_id) {
  const rtnval = "/builds/" + encodeURIComponent(run_id) + "?project_id=" + encodeURIComponent(project_id);
  return rtnval;
}
function build_source_integrations_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/source-integrations";
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
function build_state_tone(build_state) {
  if (build_state === "completed") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (build_state === "failed") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (build_state === "cancelled") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function is_terminal_build_state(build_state) {
  const rtnval = TERMINAL_BUILD_STATES.indexOf(build_state) >= 0;
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
function trigger_message_for_status(status) {
  if (status === 202 || status === 200 || status === 201) {
    const rtnval2 = "Build triggered.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "Runner inputs were rejected \u2014 check the runner kind.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project or runner kind.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to trigger builds.";
    return rtnval2;
  }
  const rtnval = "Failed to trigger build (HTTP " + String(status) + ").";
  return rtnval;
}
function list_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to builds.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This project was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the build service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load builds (HTTP " + String(status) + "). Try refreshing.";
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
function parse_runner_inputs(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = {};
    return rtnval2;
  }
  const parsed = JSON.parse(raw);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
    throw new SyntaxError("runner inputs must be a JSON object");
  }
  const rtnval = parsed;
  return rtnval;
}
// ?project_id=<uuid or slug> preselects a project, so a project's page
// can link straight to its builds / runs / pipelines / test catalog
// (PRJ-06).
function project_from_search() {
  if (typeof window === "undefined") {
    const rtnval2 = "";
    return rtnval2;
  }
  const value = new URLSearchParams(window.location.search).get("project_id");
  const rtnval = value === null ? "" : value.trim();
  return rtnval;
}
function preferred_project_id(projects) {
  const requested = project_from_search();
  const match = projects.find((project) => project.project_id === requested || project.slug === requested);
  const rtnval = match !== undefined ? match.project_id : projects[0].project_id;
  return rtnval;
}
class PycBuildsList extends HTMLElement {
  _pager;
  _state;
  _builds;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _integrations;
  _root;
  _table_region;
  _trigger_region;
  _toast_region;
  _projects_notice_region;
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
    this._builds = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._integrations = [];
    this._root = null;
    this._table_region = null;
    this._pager = null;
    this._trigger_region = null;
    this._toast_region = null;
    this._projects_notice_region = null;
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
   * state filter, trigger action, table region, pager, toast.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-builds");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-builds__heading");
    heading.textContent = "Builds";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-builds__controls");
    const project_label = document.createElement("div");
    project_label.classList.add("pyc-builds__field");
    const project_select = document.createElement("mj-select");
    project_select.setAttribute("label", "Project");
    project_select.classList.add("pyc-builds__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      this._state.page = 1;
      void this._on_project_changed();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-builds__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("label", "Project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectId = project_input.value.trim();
      this._state.page = 1;
      void this._on_project_changed();
    });
    controls.appendChild(project_input);
    const state_label = document.createElement("div");
    state_label.classList.add("pyc-builds__field");
    const state_select = document.createElement("mj-select");
    state_select.setAttribute("label", "State");
    state_select.classList.add("pyc-builds__select");
    state_select.setAttribute("data-role", "state-filter");
    const any_option = document.createElement("mj-option");
    any_option.setAttribute("value", "");
    any_option.textContent = "All states";
    state_select.appendChild(any_option);
    for (const build_state of BUILD_STATES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", build_state);
      option.textContent = build_state;
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
    trigger_button.classList.add("pyc-builds__button");
    trigger_button.setAttribute("type", "button");
    trigger_button.setAttribute("data-role", "trigger-toggle");
    trigger_button.textContent = "Trigger Build";
    trigger_button.addEventListener("click", () => {
      this._toggle_trigger_form();
    });
    controls.appendChild(trigger_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-builds__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-builds__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    const trigger_region = document.createElement("div");
    trigger_region.classList.add("pyc-builds__trigger-region");
    trigger_region.setAttribute("data-role", "trigger-region");
    trigger_region.hidden = true;
    root.appendChild(trigger_region);
    this._trigger_region = trigger_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-builds__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    toast_region.setAttribute("role", "status");
    toast_region.setAttribute("aria-live", "polite");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-builds__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");

    pager.classList.add("pyc-builds__pager");

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
        "pychestrate.ui.builds.projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._projectsNoticeKind = "";
      this._state.projectId = preferred_project_id(projects);
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
      await this._on_project_changed();
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
      region.classList.remove("pyc-builds__projects-notice--error");
      region.textContent = "No projects exist yet.";
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-builds__projects-notice--error");
      region.textContent = "You don't have permission to list projects.";
      return;
    }
    region.classList.add("pyc-builds__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-builds__button");
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
   * envelope so the view tolerates either shape.
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
   * React to a project change -- reload the source integrations
   * (so the trigger form's selector is fresh) and the builds
   * page.
   */
  async _on_project_changed() {
    await this._load_integrations();
    await this._refresh();
    return;
  }
  /**
   * Fetch the active project's source integrations. A failed
   * fetch leaves the integrations list empty -- the trigger form
   * degrades to a manual integration-id-free flow.
   */
  async _load_integrations() {
    this._integrations = [];
    if (this._state.projectId.length === 0) {
      return;
    }
    try {
      const url = build_source_integrations_url(this._state.projectId);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        this._integrations = this._extract_integrations(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.integrations_fetch_failed",
        { reason: String(reason) }
      );
    }
    return;
  }
  /**
   * Normalise a source-integrations page body into option
   * records.
   *
   * @param body Parsed JSON response body.
   *
   * @returns A list of source integration options.
   */
  _extract_integrations(body) {
    let raw = [];
    if (body !== null && typeof body === "object") {
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
      const integration_id = record.integration_id;
      const project_id = record.project_id;
      const provider_name = record.provider_name;
      const repo_key = record.repo_key;
      if (typeof integration_id !== "string" || typeof project_id !== "string" || typeof provider_name !== "string" || typeof repo_key !== "string") {
        continue;
      }
      rtnval.push({
        integration_id,
        project_id,
        provider_name,
        repo_key
      });
    }
    return rtnval;
  }
  /**
   * Fetch the current page of builds and re-render the table.
   * Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._builds = [];
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._render_table_region();
    const url = build_builds_query_url(this._state);
    let page = null;
    let fetch_status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      fetch_status = response.status;
      if (response.ok === false) {
        throw new Error("builds fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.list_fetch_failed",
        { reason: String(reason) }
      );
      if (fetch_status === 401) {
        announce_session_expired();
      }
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = fetch_status;
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = fetch_status;
      this._render_table_region();
      return;
    }
    this._builds = page.items;
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
    this._state.errorStatus = 0;
    this._render_table_region();
    return;
  }
  /**
   * Re-render the table region from the current state + builds.
   */
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.projectId.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-builds__status");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its builds.";
      region.replaceChildren(notice);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-builds__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading builds\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add("pyc-builds__status", "pyc-builds__status--error");
      error.setAttribute("data-role", "error-state");
      error.textContent = list_load_message_for_status(this._state.errorStatus);
      const children = [error];
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-builds__button");
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
    if (this._builds.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-builds__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No builds yet";
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
   * Build the builds ``<table>`` from the current ``_builds``
   * list.
   */
  _build_table() {
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-builds__table");
    // Sorting is client-side over the current page. The repro
    // digest column sorts by its raw value; timestamps sort by
    // their raw ISO strings, which collate as chronological order.
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-builds__row";
    table.rowAttrs = (build) => ({ "data-build-id": build.run_id });
    table.columns = [
      {
        // What ran comes first (runner and target); the short id follows.
        key: "run_id",
        label: "Build",
        width: "20rem",
        render: (build) => {
          const cell = document.createElement("span");
          const link = document.createElement("a");
          link.classList.add("pyc-builds__build-link");
          link.setAttribute(
            "href",
            build_build_detail_link(build.project_id, build.run_id)
          );
          link.textContent = build_title(build);
          link.title = build.run_id;
          cell.appendChild(link);
          const id = document.createElement("span");
          id.classList.add("pyc-builds__build-id");
          id.textContent = " " + short_id(build.run_id);
          cell.appendChild(id);
          return cell;
        }
      },
      {
        key: "source",
        label: "Source",
        width: "18rem",
        sortable: false,
        render: (build) => {
          const label = build_source_label(build);
          return label.length > 0 ? label : "\u2014";
        }
      },
      {
        key: "state",
        label: "State",
        width: "8rem",
        render: (build) => {
          const badge = document.createElement("mj-chip");
          badge.classList.add("pyc-builds__badge");
          badge.setAttribute("data-tone", build_state_tone(build.state));
          badge.textContent = build.state;
          return badge;
        }
      },
      {
        key: "repro_digest_sha256",
        label: "Inputs digest",
        width: "12rem",
        render: (build) => {
          const digest = document.createElement("span");
          digest.classList.add("pyc-builds__digest");
          digest.textContent = short_id(build.repro_digest_sha256);
          digest.title = build.repro_digest_sha256;
          return digest;
        }
      },
      {
        key: "started_at",
        label: "Started",
        width: "12rem",
        render: (build) => format_timestamp(build.started_at)
      },
      {
        key: "duration",
        label: "Duration",
        width: "10rem",
        sortable: false,
        render: (build) => format_duration(build.started_at, build.finished_at, build.state === "running")
      }
    ];
    table.rows = this._builds;
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
   * Toggle the inline trigger-build form's visibility, rendering
   * it on first reveal.
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
   * Render the trigger-build form into the trigger region -- a
   * source-integration selector, a runner-kind input, a runner-
   * inputs JSON textarea, and a submit button.
   */
  _render_trigger_form() {
    if (this._trigger_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-builds__trigger-form");
    form.setAttribute("data-role", "trigger-form");
    const integration_label = document.createElement("div");
    integration_label.classList.add("pyc-builds__field");
    const integration_select = document.createElement("mj-select");
    integration_select.setAttribute("label", "Source integration");
    integration_select.classList.add("pyc-builds__select");
    integration_select.setAttribute("data-role", "trigger-integration");
    if (this._integrations.length === 0) {
      const none_option = document.createElement("mj-option");
      none_option.setAttribute("value", "");
      none_option.textContent = "No source integration registered";
      integration_select.appendChild(none_option);
    } else {
      // The first integration is preselected -- what the select
      // shows is what the request sends. "None" keeps the option of
      // a build whose runner inputs name the repository themselves.
      const first_id = this._integrations[0].integration_id;
      for (const integration of this._integrations) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", integration.integration_id);
        option.textContent = integration.provider_name + " \xB7 " + integration.repo_key;
        if (integration.integration_id === first_id) {
          option.setAttribute("selected", "");
        }
        integration_select.appendChild(option);
      }
      const none_option = document.createElement("mj-option");
      none_option.setAttribute("value", "");
      none_option.textContent = "None — the runner inputs name the repository";
      integration_select.appendChild(none_option);
      integration_select.value = first_id;
    }
    integration_label.appendChild(integration_select);
    form.appendChild(integration_label);
    const runner_label = document.createElement("div");
    runner_label.classList.add("pyc-builds__field");
    const runner_input = document.createElement("mj-text-field");
    runner_input.setAttribute("label", "Runner kind");
    runner_input.classList.add("pyc-builds__input");
    runner_input.setAttribute("type", "text");
    runner_input.setAttribute("placeholder", "makefile");
    runner_input.setAttribute("data-role", "trigger-runner-kind");
    runner_input.required = true;
    runner_label.appendChild(runner_input);
    form.appendChild(runner_label);
    const inputs_label = document.createElement("label");
    inputs_label.classList.add("pyc-builds__field", "pyc-builds__field--wide");
    inputs_label.textContent = "Runner inputs (JSON)";
    const inputs_area = document.createElement("mj-textarea");
    inputs_area.classList.add("pyc-builds__textarea");
    inputs_area.setAttribute("data-role", "trigger-runner-inputs");
    inputs_area.setAttribute("placeholder", '{"targets": ["all"]}');
    inputs_area.rows = 3;
    inputs_label.appendChild(inputs_area);
    form.appendChild(inputs_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-builds__trigger");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "trigger-submit");
    submit_button.textContent = "Trigger Build";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-builds__trigger-status");
    status.setAttribute("data-role", "trigger-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_trigger(
        form,
        integration_select,
        runner_input,
        inputs_area,
        submit_button
      );
    });
    this._trigger_region.replaceChildren(form);
    return;
  }
  /**
   * Submit the trigger-build form -- POST a
   * ``BuildRunCreateRequest`` and surface the outcome. Exposed so
   * unit tests can invoke a trigger without a real form-submit
   * event.
   *
   * @param runner_kind The runner-kind identifier.
   * @param runner_inputs Free-form runner inputs object.
   * @param source_integration_id The chosen source integration id,
   *                              or an empty string for none.
   *
   * @returns The trigger outcome.
   */
  async triggerBuild(runner_kind, runner_inputs, source_integration_id = "") {
    const rtnval = await this._do_trigger(
      runner_kind,
      runner_inputs,
      source_integration_id
    );
    return rtnval;
  }
  async _submit_trigger(form, integration_select, runner_input, inputs_area, submit_button) {
    const status = form.querySelector('[data-role="trigger-status"]');
    const runner_kind = runner_input.value.trim();
    if (runner_kind.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Runner kind is required.";
      }
      return;
    }
    let runner_inputs = {};
    try {
      runner_inputs = parse_runner_inputs(inputs_area.value);
    } catch (reason) {
      if (status instanceof HTMLElement) {
        status.textContent = "Runner inputs must be valid JSON.";
      }
      console.warn(
        "pychestrate.ui.builds.trigger_inputs_invalid",
        { reason: String(reason) }
      );
      return;
    }
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Triggering build\u2026";
    }
    const source_integration_id = typeof integration_select.value === "string" ? integration_select.value.trim() : "";
    const outcome = await this._do_trigger(
      runner_kind,
      runner_inputs,
      source_integration_id
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
  async _do_trigger(runner_kind, runner_inputs, source_integration_id = "") {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        buildId: "",
        message: "Select a project before triggering a build."
      };
      return rtnval2;
    }
    const payload = {
      runner_kind,
      runner_inputs
    };
    // Send the integration the dialog shows as selected (audit
    // ORC-30: it used to be dropped); omit it for "None".
    if (typeof source_integration_id === "string" && source_integration_id.length > 0) {
      payload.source_integration_id = source_integration_id;
    }
    let status = 0;
    let build_id = "";
    let detail = "";
    try {
      const url = build_builds_collection_url(this._state.projectId);
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
          build_id = run.run_id;
        }
      } else if (status === 409 || status === 422) {
        try {
          const problem = await response.json();
          if (problem !== null && typeof problem.detail === "string") {
            detail = problem.detail.split(/\r?\n/).map((line) => line.trim()).filter((line) => line.length > 0).join(" ");
          }
        } catch (parse_reason) {
          detail = "";
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.trigger_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        buildId: "",
        message: "Failed to reach the build service."
      };
      return rtnval2;
    }
    const ok = status === 202 || status === 200 || status === 201;
    const rtnval = {
      ok,
      status,
      buildId: build_id,
      message: detail.length > 0 ? "Build not triggered: " + detail : trigger_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Render a dismissible toast for a trigger outcome -- on
   * success the toast links to the new build's detail page.
   *
   * @param outcome The trigger-build outcome.
   */
  _show_trigger_toast(outcome) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-builds__toast");
    toast.setAttribute("data-role", "trigger-toast");
    toast.setAttribute("data-tone", outcome.ok === true ? "ok" : "error");
    const message = document.createElement("span");
    message.classList.add("pyc-builds__toast-message");
    message.textContent = outcome.message;
    toast.appendChild(message);
    if (outcome.ok === true && outcome.buildId.length > 0) {
      const link = document.createElement("a");
      link.classList.add("pyc-builds__toast-link");
      link.setAttribute(
        "href",
        build_build_detail_link(this._state.projectId, outcome.buildId)
      );
      link.setAttribute("data-role", "trigger-toast-link");
      link.textContent = "View build";
      toast.appendChild(link);
    }
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-builds__toast-dismiss");
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
}
export {
  BUILD_STATES,
  PycBuildsList,
  TERMINAL_BUILD_STATES,
  announce_session_expired,
  build_build_detail_link,
  build_builds_collection_url,
  build_builds_query_url,
  build_source_integrations_url,
  build_state_tone,
  format_timestamp,
  has_next_page,
  has_previous_page,
  is_terminal_build_state,
  list_load_message_for_status,
  parse_runner_inputs,
  short_id,
  trigger_message_for_status
};
