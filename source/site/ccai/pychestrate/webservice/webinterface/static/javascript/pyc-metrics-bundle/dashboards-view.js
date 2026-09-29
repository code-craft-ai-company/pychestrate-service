import { may } from "../shared/permissions.js";
import { message_with_detail, read_problem_detail } from "../shared/problem-detail.js";
import { keep_list_state_on_back, mirror_to_query, query_value } from "../shared/view-state.js";
import { format_clock_instant, parse_timestamp } from "../shared/datetime.js";
import {
  build_chart_element,
  build_range_url,
  build_timeseries_url,
  metric_display_name
} from "./timeseries-view.js";
import {
  announce_session_expired,
  extract_projects,
  list_load_message_for_status,
  short_metric_id
} from "./test-metrics-view.js";
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
const DASHBOARDS_ROUTE = "/dashboards";
function build_dashboards_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/dashboards";
  return rtnval;
}
function build_dashboard_detail_url(project_id, dashboard_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/dashboards/" + encodeURIComponent(dashboard_id);
  return rtnval;
}
const DASHBOARDS_WRITE_PERMISSION = "system:dashboards.write";
// A dashboard belongs to one project, so its address carries that project
// (the list, the detail page and the editor all read it back).
function dashboard_href(dashboard_id, project_id, suffix) {
  const path = DASHBOARDS_ROUTE + "/" + encodeURIComponent(dashboard_id) + (typeof suffix === "string" ? suffix : "");
  const rtnval = typeof project_id === "string" && project_id.length > 0 ? path + "?project_id=" + encodeURIComponent(project_id) : path;
  return rtnval;
}
// The project a dashboard page is about: the one in the address, else (for
// an older link without it) the first project the viewer can see.
function project_id_for_page(projects) {
  const wanted = query_value("project_id");
  if (wanted.length > 0) {
    return wanted;
  }
  const rtnval = projects.length > 0 ? projects[0].project_id : "";
  return rtnval;
}
function dashboard_id_from_path(path) {
  if (typeof path !== "string") {
    const rtnval2 = "";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working.endsWith("/") === true) {
    working = working.slice(0, working.length - 1);
  }
  const prefix = DASHBOARDS_ROUTE + "/";
  if (working.startsWith(prefix) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  const remainder = working.slice(prefix.length);
  if (remainder.length === 0 || remainder.indexOf("/") >= 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = decodeURIComponent(remainder);
  return rtnval;
}
function create_message_for_status(status) {
  if (status === 201 || status === 200) {
    const rtnval2 = "Dashboard created.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "A dashboard with that name already exists.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The dashboard request was rejected \u2014 check the name.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to create dashboards.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project.";
    return rtnval2;
  }
  const rtnval = "Failed to create dashboard (HTTP " + String(status) + ").";
  return rtnval;
}
function tile_metric_name(tile) {
  if (tile === null || tile === void 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const config = tile.config;
  if (config === null || config === void 0 || typeof config !== "object") {
    const rtnval2 = "";
    return rtnval2;
  }
  if (typeof config.metric_name === "string" && config.metric_name.length > 0) {
    const rtnval2 = config.metric_name;
    return rtnval2;
  }
  const metric = config.metric;
  if (typeof metric !== "string") {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = metric;
  return rtnval;
}
class PycDashboardsList extends HTMLElement {
  _state;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _projects_notice_region;
  _dashboards;
  _root;
  _form_region;
  _table_region;
  _notice_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      loading: false,
      errored: false,
      errorStatus: 0
    };
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._projects_notice_region = null;
    this._dashboards = [];
    this._root = null;
    this._form_region = null;
    this._table_region = null;
    this._notice_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + load state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
      loading: this._state.loading,
      errored: this._state.errored,
      errorStatus: this._state.errorStatus
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the chrome, kick off the project
   * fetch.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_projects();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.textContent = "Dashboards";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-metrics__controls");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-metrics__field");
    project_label.textContent = "Project";
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-metrics__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      mirror_to_query({ project_id: this._state.projectId });
      void this._refresh();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-metrics__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectId = project_input.value.trim();
      mirror_to_query({ project_id: this._state.projectId });
      void this._refresh();
    });
    controls.appendChild(project_input);
    const create_button = document.createElement("mj-button");
    create_button.classList.add("pyc-metrics__button");
    create_button.setAttribute("type", "button");
    create_button.setAttribute("data-role", "create-toggle");
    create_button.textContent = "Create Dashboard";
    create_button.addEventListener("click", () => {
      this._toggle_create_form();
    });
    controls.appendChild(create_button);
    void may(DASHBOARDS_WRITE_PERMISSION).then((allowed) => {
      create_button.hidden = allowed === false;
    });
    root.appendChild(controls);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-metrics__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    const form_region = document.createElement("div");
    form_region.classList.add("pyc-metrics__form-region");
    form_region.setAttribute("data-role", "form-region");
    form_region.hidden = true;
    root.appendChild(form_region);
    this._form_region = form_region;
    const notice_region = document.createElement("div");
    notice_region.classList.add("pyc-metrics__notice-region");
    notice_region.setAttribute("data-role", "notice-region");
    root.appendChild(notice_region);
    this._notice_region = notice_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-metrics__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
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
        projects = extract_projects(body);
      } else {
        load_failed = true;
      }
    } catch (reason) {
      load_failed = true;
      console.warn(
        "pychestrate.ui.metrics.projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._projectsNoticeKind = "";
      const wanted = query_value("project_id");
      this._state.projectId = projects.some((project) => project.project_id === wanted) ? wanted : projects[0].project_id;
      mirror_to_query({ project_id: this._state.projectId });
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
      this._render_table();
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
      region.classList.remove("pyc-metrics__projects-notice--error");
      region.textContent = "No projects exist yet.";
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-metrics__projects-notice--error");
      region.textContent = "You don't have permission to list projects.";
      return;
    }
    region.classList.add("pyc-metrics__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-metrics__button");
    retry.setAttribute("type", "button");
    retry.setAttribute("data-role", "projects-retry");
    retry.textContent = "Retry";
    retry.addEventListener("click", () => {
      void this._load_projects();
    });
    region.replaceChildren(message, retry);
    return;
  }
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
   * Re-fetch the dashboards page for the current project and
   * re-render. Exposed so unit tests can await a render cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._render_table();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._render_table();
    let dashboards = [];
    let errored = false;
    let error_status = 0;
    try {
      const url = build_dashboards_collection_url(
        this._state.projectId
      );
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        dashboards = extract_dashboards(body);
      } else {
        errored = true;
        error_status = response.status;
        if (error_status === 401) {
          announce_session_expired();
        }
      }
    } catch (reason) {
      errored = true;
      error_status = 0;
      console.warn(
        "pychestrate.ui.metrics.dashboards_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._state.loading = false;
    this._state.errored = errored;
    this._state.errorStatus = error_status;
    this._dashboards = dashboards;
    this._render_table();
    return;
  }
  _render_table() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    region.replaceChildren();
    if (this._state.projectId.length === 0) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view dashboards.";
      region.appendChild(notice);
      return;
    }
    if (this._state.loading === true) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "Loading dashboards\u2026";
      region.appendChild(notice);
      return;
    }
    if (this._state.errored === true) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.classList.add("pyc-metrics__notice--error");
      notice.setAttribute("data-role", "error-state");
      notice.textContent = list_load_message_for_status(
        this._state.errorStatus,
        "dashboards"
      );
      region.appendChild(notice);
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-metrics__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "list-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._refresh();
        });
        region.appendChild(retry);
      }
      return;
    }
    if (this._dashboards.length === 0) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "No dashboards yet \u2014 create one above.";
      region.appendChild(notice);
      return;
    }
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-metrics__table");
    table.setAttribute("data-role", "dashboards-table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-metrics__row";
    table.rowAttrs = (dashboard) => ({
      "data-dashboard-id": dashboard.dashboard_id
    });
    table.columns = [
      {
        key: "name",
        label: "Name",
        width: "16rem",
        render: (dashboard) => {
          const link = document.createElement("a");
          link.classList.add("pyc-metrics__row-link");
          link.setAttribute("href", dashboard_href(dashboard.dashboard_id, this._state.projectId));
          link.textContent = dashboard.name;
          return link;
        }
      },
      {
        key: "description",
        label: "Description",
        width: "24rem",
        sortable: false,
        render: (dashboard) =>
          dashboard.description !== void 0 && dashboard.description.length > 0
            ? dashboard.description
            : "\u2014"
      },
      {
        key: "tiles",
        label: "Tiles",
        width: "8rem",
        render: (dashboard) => String(dashboard.tiles.length)
      },
      {
        key: "version",
        label: "Version",
        width: "8rem",
        render: (dashboard) => String(dashboard.version)
      }
    ];
    table.rows = this._dashboards;
    region.appendChild(table);
    return;
  }
  _toggle_create_form() {
    if (this._form_region === null) {
      return;
    }
    if (this._form_region.hidden === false) {
      this._form_region.hidden = true;
      this._form_region.replaceChildren();
      return;
    }
    this._form_region.hidden = false;
    this._render_create_form();
    return;
  }
  _render_create_form() {
    if (this._form_region === null) {
      return;
    }
    const region = this._form_region;
    region.replaceChildren();
    const form = document.createElement("form");
    form.classList.add("pyc-metrics__form");
    form.setAttribute("data-role", "create-form");
    const name_label = document.createElement("label");
    name_label.classList.add("pyc-metrics__field");
    name_label.textContent = "Name";
    const name_input = document.createElement("mj-text-field");
    name_input.classList.add("pyc-metrics__input");
    name_input.setAttribute("type", "text");
    name_input.setAttribute("data-role", "name-input");
    name_input.required = true;
    name_label.appendChild(name_input);
    form.appendChild(name_label);
    const desc_label = document.createElement("label");
    desc_label.classList.add("pyc-metrics__field");
    desc_label.textContent = "Description";
    const desc_input = document.createElement("mj-text-field");
    desc_input.classList.add("pyc-metrics__input");
    desc_input.setAttribute("type", "text");
    desc_input.setAttribute("data-role", "description-input");
    desc_label.appendChild(desc_input);
    form.appendChild(desc_label);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-metrics__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "create-submit");
    submit.textContent = "Create";
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_create(
        name_input.value.trim(),
        desc_input.value.trim()
      );
    });
    region.appendChild(form);
    return;
  }
  /**
   * POST a ``DashboardCreateRequest`` for the current project.
   * Exposed so unit tests can drive the create path directly.
   *
   * @param name The dashboard name.
   * @param description An optional description.
   *
   * @returns The create outcome.
   */
  async submitCreate(name, description) {
    const rtnval = await this._submit_create(name, description);
    return rtnval;
  }
  async _submit_create(name, description) {
    if (this._state.projectId.length === 0 || name.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        dashboardId: "",
        message: "A project and a dashboard name are required."
      };
      this._render_notice(rtnval2.message, true);
      return rtnval2;
    }
    const payload = { name };
    if (description.length > 0) {
      payload.description = description;
    }
    let status = 0;
    let detail = "";
    let dashboard_id = "";
    let ok = false;
    try {
      const url = build_dashboards_collection_url(
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
      ok = response.ok;
      if (response.ok === true) {
        const body = await response.json();
        const record = body;
        if (typeof record.dashboard_id === "string") {
          dashboard_id = record.dashboard_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.dashboard_create_failed",
        { reason: String(reason) }
      );
    }
    const message = message_with_detail("Dashboard not created", detail, create_message_for_status(status));
    const rtnval = {
      ok,
      status,
      dashboardId: dashboard_id,
      message
    };
    this._render_notice(message, ok === false);
    if (ok === true) {
      this._toggle_create_form();
      await this._refresh();
    }
    return rtnval;
  }
  _render_notice(message, is_error) {
    if (this._notice_region === null) {
      return;
    }
    const notice = document.createElement("div");
    notice.classList.add("pyc-metrics__notice");
    if (is_error === true) {
      notice.classList.add("pyc-metrics__notice--error");
    }
    notice.textContent = message;
    this._notice_region.replaceChildren(notice);
    return;
  }
}
class PycDashboardDetail extends HTMLElement {
  _projects;
  _dashboard;
  _loading;
  _errored;
  _errorStatus;
  _root;
  _tiles_region;
  _projectId;
  _actions_region;
  constructor() {
    super();
    this._projects = [];
    this._dashboard = null;
    this._loading = false;
    this._errored = false;
    this._errorStatus = 0;
    this._root = null;
    this._tiles_region = null;
    this._projectId = "";
    this._actions_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests.
   */
  get loaded() {
    const rtnval = this._dashboard !== null;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the chrome, kick off the dashboard
   * fetch.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_dashboard();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.setAttribute("data-role", "dashboard-heading");
    heading.textContent = "Dashboard";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-metrics__row-link");
    back.setAttribute("href", DASHBOARDS_ROUTE);
    back.setAttribute("data-role", "back-link");
    back.textContent = "\u2190 All dashboards";
    keep_list_state_on_back(back, DASHBOARDS_ROUTE);
    root.appendChild(back);
    const actions_region = document.createElement("div");
    actions_region.classList.add("pyc-metrics__controls");
    actions_region.setAttribute("data-role", "detail-actions");
    root.appendChild(actions_region);
    this._actions_region = actions_region;
    const tiles_region = document.createElement("div");
    tiles_region.classList.add("pyc-metrics__tiles-region");
    tiles_region.setAttribute("data-role", "tiles-region");
    root.appendChild(tiles_region);
    this._tiles_region = tiles_region;
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Resolve the dashboard project + id, fetch the dashboard, and
   * render its tiles. Exposed so unit tests can await the cycle.
   */
  async loadDashboard() {
    await this._load_dashboard();
    return;
  }
  async _load_dashboard() {
    const dashboard_id = dashboard_id_from_path(
      typeof window !== "undefined" ? window.location.pathname : ""
    );
    if (dashboard_id.length === 0) {
      this._errored = true;
      this._render_tiles();
      return;
    }
    let project_id = query_value("project_id");
    if (project_id.length === 0) {
      try {
        const response = await fetch(PROJECTS_LIST_URL, {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        });
        if (response.ok === true) {
          const body = await response.json();
          this._projects = extract_projects(body);
          project_id = project_id_for_page(this._projects);
        }
      } catch (reason) {
        console.warn(
          "pychestrate.ui.metrics.projects_fetch_failed",
          { reason: String(reason) }
        );
      }
    }
    if (project_id.length === 0) {
      this._errored = true;
      this._render_tiles();
      return;
    }
    this._projectId = project_id;
    this._loading = true;
    this._render_tiles();
    let dashboard = null;
    let errored = false;
    let error_status = 0;
    try {
      const url = build_dashboard_detail_url(project_id, dashboard_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        dashboard = body;
      } else {
        errored = true;
        error_status = response.status;
        if (error_status === 401) {
          announce_session_expired();
        }
      }
    } catch (reason) {
      errored = true;
      error_status = 0;
      console.warn(
        "pychestrate.ui.metrics.dashboard_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._loading = false;
    this._errored = errored;
    this._errorStatus = error_status;
    this._dashboard = dashboard;
    this._render_tiles();
    await this._render_actions();
    return;
  }
  /*
   * "Edit layout" for a viewer who may change dashboards, and a "back" link that
   * returns to the project's list (ORC-16: the editor had no way in).
   */
  async _render_actions() {
    if (this._actions_region === null || this._root === null || this._dashboard === null) {
      return;
    }
    const back = this._root.querySelector('[data-role="back-link"]');
    if (back instanceof HTMLAnchorElement) {
      back.setAttribute("href", DASHBOARDS_ROUTE + "?project_id=" + encodeURIComponent(this._projectId));
    }
    const allowed = await may(DASHBOARDS_WRITE_PERMISSION);
    if (allowed === false) {
      this._actions_region.replaceChildren();
      return;
    }
    const edit = document.createElement("a");
    edit.classList.add("pyc-metrics__row-link");
    edit.setAttribute("data-role", "edit-layout");
    edit.setAttribute("href", dashboard_href(this._dashboard.dashboard_id, this._projectId, "/edit"));
    edit.textContent = "Edit layout";
    this._actions_region.replaceChildren(edit);
    return;
  }
  _render_tiles() {
    if (this._tiles_region === null || this._root === null) {
      return;
    }
    const heading = this._root.querySelector(
      '[data-role="dashboard-heading"]'
    );
    if (heading !== null && this._dashboard !== null) {
      heading.textContent = this._dashboard.name;
    }
    const region = this._tiles_region;
    region.replaceChildren();
    if (this._loading === true) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "Loading dashboard\u2026";
      region.appendChild(notice);
      return;
    }
    if (this._errored === true || this._dashboard === null) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.classList.add("pyc-metrics__notice--error");
      notice.setAttribute("data-role", "error-state");
      if (this._errorStatus === 404) {
        notice.textContent = "This dashboard was not found \u2014 it may have been removed.";
      } else {
        notice.textContent = list_load_message_for_status(
          this._errorStatus,
          "this dashboard"
        );
      }
      region.appendChild(notice);
      if (this._errorStatus === 0 || this._errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-metrics__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "detail-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._load_dashboard();
        });
        region.appendChild(retry);
      }
      return;
    }
    if (this._dashboard.tiles.length === 0) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "This dashboard has no tiles.";
      region.appendChild(notice);
      return;
    }
    const grid = document.createElement("div");
    grid.classList.add("pyc-metrics__tiles");
    grid.setAttribute("data-role", "tiles-grid");
    for (const tile of this._dashboard.tiles) {
      grid.appendChild(this._build_tile(tile));
    }
    region.appendChild(grid);
    return;
  }
  _build_tile(tile) {
    const card = document.createElement("div");
    card.classList.add("pyc-metrics__tile");
    card.setAttribute("data-role", "dashboard-tile");
    card.setAttribute("data-tile-id", tile.tile_id);
    const title = document.createElement("div");
    title.classList.add("pyc-metrics__tile-title");
    const metric_name = tile_metric_name(tile);
    // The metric's storage name is not what a person reads; it stays on hover
    // for anyone who has to quote it.
    title.textContent = metric_name.length > 0 ? metric_display_name(metric_name) : tile.kind;
    if (metric_name.length > 0) {
      title.title = metric_name;
    }
    card.appendChild(title);
    const body = document.createElement("div");
    body.classList.add("pyc-metrics__tile-body");
    body.setAttribute("data-role", "tile-body");
    const placeholder = document.createElement("div");
    placeholder.classList.add("pyc-metrics__notice");
    placeholder.textContent = metric_name.length > 0 ? "Loading metric\u2026" : "No metric configured.";
    body.appendChild(placeholder);
    card.appendChild(body);
    if (metric_name.length > 0) {
      void this._load_tile_metric(tile, metric_name, body);
    }
    return card;
  }
  async _load_tile_metric(tile, metric_name, body) {
    let points = [];
    let errored = false;
    // A tile keeps the range it was given; one without a range shows the last week.
    const configured = tile.config !== null && typeof tile.config === "object" ? tile.config.range_seconds : void 0;
    const range_seconds = typeof configured === "number" && Number.isFinite(configured) && configured > 0 ? configured : 0;
    try {
      const now = /* @__PURE__ */ new Date();
      const url = range_seconds > 0 ? build_range_url(metric_name, range_seconds, now) : build_timeseries_url(metric_name, "7d", now);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const data = await response.json();
        const query = data;
        if (Array.isArray(query.points) === true) {
          points = query.points;
        }
      } else {
        errored = true;
      }
    } catch (reason) {
      errored = true;
      console.warn(
        "pychestrate.ui.metrics.tile_metric_fetch_failed",
        { reason: String(reason) }
      );
    }
    body.replaceChildren();
    if (errored === true) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.classList.add("pyc-metrics__notice--error");
      notice.textContent = "Failed to load tile metric.";
      body.appendChild(notice);
      return;
    }
    if (points.length === 0) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "No data points.";
      body.appendChild(notice);
      return;
    }
    if (tile.kind === "metric-single-stat") {
      body.appendChild(build_single_stat(points));
      return;
    }
    body.appendChild(build_chart_element(points, metric_name));
    return;
  }
}
function format_stat_value(value) {
  if (typeof value !== "number" || Number.isFinite(value) === false) {
    return String(value);
  }
  // A number, not a time: the viewer's digit grouping, at most three decimals.
  return new Intl.NumberFormat(void 0, { maximumFractionDigits: 3 }).format(value);
}
// A "single number" tile shows the latest value, not a chart of the series.
function build_single_stat(points) {
  let latest = null;
  let latest_time = -Infinity;
  for (const point of points) {
    const at = new Date(point.observed_at).getTime();
    if (Number.isFinite(at) === true && at >= latest_time) {
      latest = point;
      latest_time = at;
    }
  }
  const stat = document.createElement("div");
  stat.classList.add("pyc-metrics__stat");
  stat.setAttribute("data-role", "tile-stat");
  const value = document.createElement("span");
  value.classList.add("pyc-metrics__stat-value");
  value.setAttribute("data-role", "tile-stat-value");
  value.textContent = latest !== null ? format_stat_value(latest.value) : "\u2014";
  stat.appendChild(value);
  const observed = latest !== null ? parse_timestamp(latest.observed_at) : null;
  if (observed !== null) {
    const caption = document.createElement("span");
    caption.classList.add("pyc-metrics__stat-caption");
    caption.textContent = "as of " + format_clock_instant(observed);
    stat.appendChild(caption);
  }
  return stat;
}
function extract_dashboards(body) {
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
    const dashboard_id = record.dashboard_id;
    if (typeof dashboard_id !== "string" || dashboard_id.length === 0) {
      continue;
    }
    let tiles = [];
    if (Array.isArray(record.tiles) === true) {
      tiles = record.tiles.filter(
        (value) => value !== null && typeof value === "object"
      );
    }
    const dashboard = {
      dashboard_id,
      project_id: typeof record.project_id === "string" ? record.project_id : "",
      name: typeof record.name === "string" ? record.name : "",
      tiles,
      version: typeof record.version === "number" ? record.version : 1
    };
    if (typeof record.description === "string") {
      dashboard.description = record.description;
    }
    rtnval.push(dashboard);
  }
  return rtnval;
}
export {
  DASHBOARDS_ROUTE,
  DASHBOARDS_WRITE_PERMISSION,
  PycDashboardDetail,
  PycDashboardsList,
  build_dashboard_detail_url,
  build_dashboards_collection_url,
  create_message_for_status,
  dashboard_href,
  dashboard_id_from_path,
  extract_dashboards,
  format_stat_value,
  project_id_for_page,
  short_metric_id,
  tile_metric_name
};
