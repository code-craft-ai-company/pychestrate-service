import { format_clock_instant, format_instant, parse_timestamp } from "../shared/datetime.js";
const DEFAULT_PER_PAGE = 25;
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
function build_pod_definitions_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/pod-definitions";
  return rtnval;
}
function build_pod_definition_url(project_id, pod_id) {
  const rtnval = build_pod_definitions_url(project_id) + "/" + encodeURIComponent(pod_id);
  return rtnval;
}
function short_id(pod_id) {
  if (typeof pod_id !== "string" || pod_id.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const dash_index = pod_id.indexOf("-");
  if (dash_index <= 0) {
    const rtnval2 = pod_id;
    return rtnval2;
  }
  const rtnval = pod_id.slice(0, dash_index);
  return rtnval;
}
function format_timestamp(value) {
  if (value === null || value === void 0 || value.length === 0) {
    const rtnval2 = "—";
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
function format_clock_time(date) {
  const rtnval = format_clock_instant(date);
  return rtnval;
}
function member_count(spec) {
  if (spec === null || spec === void 0) {
    const rtnval2 = 0;
    return rtnval2;
  }
  const members = spec["members"];
  if (Array.isArray(members) === true) {
    const rtnval2 = members.length;
    return rtnval2;
  }
  const rtnval = 0;
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
function pods_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired — sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to pods.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This project was not found — it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service — check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load pods (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
/**
 * Normalise a projects-list response body into option records.
 * Accepts both a bare array and an ``{items}`` page envelope so
 * callers tolerate either shape.
 *
 * @param body Parsed JSON response body.
 *
 * @returns A list of ``{project_id, display_name}`` records.
 */
function extract_projects(body) {
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
 * Fetch the projects collection. A 401 announces the shared
 * ``pyc-session-401`` event so the shell can surface the expired
 * session.
 *
 * @returns ``{ok, status, projects}`` -- ``projects`` is empty on
 *          any failure; ``status`` is 0 on a network error.
 */
async function load_projects() {
  let status = 0;
  let ok = false;
  let projects = [];
  try {
    const response = await fetch(PROJECTS_LIST_URL, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    status = response.status;
    ok = response.ok;
    if (ok === true) {
      const body = await response.json();
      projects = extract_projects(body);
    }
  } catch (reason) {
    console.warn(
      "pychestrate.ui.fleet.projects_fetch_failed",
      { reason: String(reason) }
    );
  }
  if (status === 401) {
    announce_session_expired();
  }
  const rtnval = { ok, status, projects };
  return rtnval;
}
/**
 * Build a ``project_id -> display_name`` lookup from project
 * option records.
 *
 * @param projects Records from :func:`extract_projects`.
 *
 * @returns A plain-object lookup map.
 */
function project_display_map(projects) {
  const rtnval = {};
  if (Array.isArray(projects) === false) {
    return rtnval;
  }
  for (const project of projects) {
    if (project === null || typeof project !== "object") {
      continue;
    }
    if (typeof project.project_id !== "string" || project.project_id.length === 0) {
      continue;
    }
    rtnval[project.project_id] = project.display_name;
  }
  return rtnval;
}
class PycPodsList extends HTMLElement {
  _pager;
  _state;
  _pods;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _root;
  _table_region;
  _projects_notice_region;
  _stamp_region;
  constructor() {
    super();
    this._state = {
      projectFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false,
      errorStatus: 0,
      needsProject: true
    };
    this._pods = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._root = null;
    this._table_region = null;
    this._projects_notice_region = null;
    this._stamp_region = null;
    this._pager = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * filter + pagination state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectFilter: this._state.projectFilter,
      page: this._state.page,
      perPage: this._state.perPage,
      total: this._state.total,
      loading: this._state.loading,
      errored: this._state.errored,
      errorStatus: this._state.errorStatus,
      needsProject: this._state.needsProject
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome, then load the
   * projects collection to drive the project picker. A project
   * supplied via ``?project_id=`` seeds the selection.
   */
  connectedCallback() {
    const seeded = this._project_from_search();
    if (seeded.length > 0) {
      this._state.projectFilter = seeded;
    }
    this._render_chrome();
    void this._load_projects();
    return;
  }
  /**
   * Read a ``project_id`` from the current location's query
   * string so a deep link can seed the pods list.
   *
   * @returns The project id, or ``""`` when none is present.
   */
  _project_from_search() {
    if (typeof window === "undefined") {
      const rtnval2 = "";
      return rtnval2;
    }
    const params = new URLSearchParams(window.location.search);
    const value = params.get("project_id");
    if (value === null) {
      const rtnval2 = "";
      return rtnval2;
    }
    const rtnval = value.trim();
    return rtnval;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-pods-list");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-pods-list__heading");
    heading.textContent = "Pods";
    root.appendChild(heading);
    const subtitle = document.createElement("p");
    subtitle.classList.add("pyc-pods-list__subtitle");
    subtitle.textContent = "Pod definitions are project-scoped. Pick a project to list its pods.";
    root.appendChild(subtitle);
    const legend = document.createElement("p");
    legend.classList.add("pyc-pods-list__legend");
    legend.setAttribute("data-role", "fleet-legend");
    legend.textContent = "A pod is a project-scoped definition of a group of test-target members (the machines and services the spec declares). A client is the enrolled runtime that registers to back a pod.";
    root.appendChild(legend);
    const filters = document.createElement("div");
    filters.classList.add("pyc-pods-list__filters");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-pods-list__filter");
    project_label.textContent = "Project";
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-pods-list__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.hidden = true;
    project_select.addEventListener("change", () => {
      this._state.projectFilter = project_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-pods-list__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-filter");
    project_input.hidden = true;
    if (this._state.projectFilter.length > 0) {
      project_input.value = this._state.projectFilter;
    }
    project_input.addEventListener("change", () => {
      this._state.projectFilter = project_input.value.trim();
      this._state.page = 1;
      if (this._state.projectFilter.length > 0) {
        void this._refresh();
      } else {
        this._state.needsProject = true;
        this._pods = [];
        this._state.total = 0;
        this._render_table_region();
      }
    });
    project_label.appendChild(project_input);
    filters.appendChild(project_label);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-pods-list__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      if (this._state.projectFilter.length > 0) {
        void this._refresh();
      }
    });
    filters.appendChild(refresh_button);
    const stamp = document.createElement("span");
    stamp.classList.add("pyc-pods-list__stamp");
    stamp.setAttribute("data-role", "last-updated");
    filters.appendChild(stamp);
    this._stamp_region = stamp;
    root.appendChild(filters);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-pods-list__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-pods-list__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");
    pager.classList.add("pyc-pods-list__pager");
    pager.setAttribute("data-role", "pager");
    pager.setAttribute("page", String(this._state.page));
    pager.setAttribute("page-size", String(this._state.perPage));
    pager.setAttribute("total-items", String(this._state.total));
    pager.addEventListener("mj-pagination-change", (event) => {
      // The pods collection is fetched whole and paginated
      // client-side, so a page change only re-slices -- it must
      // not trigger a refetch (which used to reset to page 1).
      this._state.page = event.detail.page;
      this._render_table_region();
    });
    this._pager = pager;
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the projects collection and populate the picker.
   * Exposed so unit tests can await the bootstrap fetch cycle.
   */
  async loadProjects() {
    await this._load_projects();
    return;
  }
  async _load_projects() {
    const outcome = await load_projects();
    if (outcome.ok === true && outcome.projects.length > 0) {
      this._projects = outcome.projects;
      this._projectsAvailable = true;
      this._projectsNoticeKind = "";
      if (this._state.projectFilter.length === 0) {
        this._state.projectFilter = outcome.projects[0].project_id;
      }
    } else {
      this._projects = [];
      this._projectsAvailable = false;
      if (outcome.ok === true) {
        this._projectsNoticeKind = "empty";
      } else if (outcome.status === 403) {
        this._projectsNoticeKind = "forbidden";
      } else {
        this._projectsNoticeKind = "error";
      }
    }
    this._render_project_control();
    this._render_projects_notice();
    if (this._state.projectFilter.length > 0) {
      await this._refresh();
    } else {
      this._render_table_region();
    }
    return;
  }
  /**
   * Render the projects-load notice -- explains why the project
   * picker degraded to the manual id input (no projects exist
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
      region.classList.remove("pyc-pods-list__projects-notice--error");
      region.textContent = "No projects exist yet.";
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-pods-list__projects-notice--error");
      region.textContent = "You don't have permission to list projects — enter a project id directly.";
      return;
    }
    region.classList.add("pyc-pods-list__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-pods-list__button");
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
   * Render the project picker or, when no projects collection is
   * available, swap to the manual text input. A seeded project id
   * that is not in the collection is kept as an extra option so a
   * deep link never silently changes projects.
   */
  _render_project_control() {
    if (this._root === null) {
      return;
    }
    const select = this._root.querySelector('[data-role="project-select"]');
    const input = this._root.querySelector('[data-role="project-filter"]');
    if (select instanceof HTMLElement === false || input instanceof HTMLElement === false) {
      return;
    }
    const select_el = select;
    const input_el = input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      let seeded_known = false;
      for (const project of this._projects) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", project.project_id);
        option.textContent = project.display_name;
        if (project.project_id === this._state.projectFilter) {
          seeded_known = true;
        }
        select_el.appendChild(option);
      }
      if (seeded_known === false && this._state.projectFilter.length > 0) {
        const extra = document.createElement("mj-option");
        extra.setAttribute("value", this._state.projectFilter);
        extra.textContent = this._state.projectFilter;
        select_el.appendChild(extra);
      }
      select_el.value = this._state.projectFilter;
    } else {
      select_el.hidden = true;
      input_el.hidden = false;
      if (this._state.projectFilter.length > 0) {
        input_el.value = this._state.projectFilter;
      }
    }
    return;
  }
  /**
   * Fetch the project's pod definitions and re-render the table
   * region. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectFilter.length === 0) {
      this._state.needsProject = true;
      this._render_table_region();
      return;
    }
    this._state.needsProject = false;
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._render_table_region();
    const url = build_pod_definitions_url(this._state.projectFilter);
    let pods = null;
    let status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        pods = body;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pods.list_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (status === 401) {
      announce_session_expired();
    }
    if (pods === null || Array.isArray(pods) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = status;
      this._render_table_region();
      return;
    }
    this._pods = pods;
    this._state.total = pods.length;
    const max_page = Math.max(
      1,
      Math.ceil(pods.length / this._state.perPage)
    );
    if (this._state.page > max_page) {
      this._state.page = max_page;
    }
    this._state.loading = false;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._render_stamp();
    this._render_table_region();
    return;
  }
  _render_stamp() {
    if (this._stamp_region === null) {
      return;
    }
    this._stamp_region.textContent = "as of " + format_clock_time(new Date());
    return;
  }
  _page_slice() {
    const start = (this._state.page - 1) * this._state.perPage;
    const end = start + this._state.perPage;
    const rtnval = this._pods.slice(start, end);
    return rtnval;
  }
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.needsProject === true) {
      const prompt = document.createElement("p");
      prompt.classList.add("pyc-pods-list__status");
      prompt.setAttribute("data-role", "needs-project");
      prompt.textContent = "Pick a project above to list its pods.";
      region.replaceChildren(prompt);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-pods-list__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading pods…";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-pods-list__status",
        "pyc-pods-list__status--error"
      );
      error.setAttribute("data-role", "error-state");
      const message = document.createElement("span");
      message.textContent = pods_load_message_for_status(
        this._state.errorStatus
      );
      error.appendChild(message);
      const retry = document.createElement("mj-button");
      retry.classList.add("pyc-pods-list__button");
      retry.setAttribute("type", "button");
      retry.setAttribute("data-role", "error-retry");
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        void this._refresh();
      });
      error.appendChild(retry);
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._pods.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pods-list__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No pods defined in this project";
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
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-pods-list__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-pods-list__row";
    table.rowAttrs = (pod) => ({ "data-pod-id": pod.pod_id });
    table.columns = [
      {
        key: "pod_id",
        label: "Pod",
        width: "12rem",
        render: (pod) => {
          const link = document.createElement("a");
          link.classList.add("pyc-pods-list__pod-link");
          const href = "/pods/" + pod.pod_id + "?project_id=" + encodeURIComponent(pod.project_id);
          link.setAttribute("href", href);
          link.textContent = short_id(pod.pod_id);
          link.title = pod.pod_id;
          return link;
        }
      },
      {
        key: "pod_name",
        label: "Name",
        width: "16rem",
        render: (pod) => pod.pod_name !== null && pod.pod_name.length > 0 ? pod.pod_name : "—"
      },
      {
        key: "current_version",
        label: "Version",
        width: "8rem",
        render: (pod) => "v" + String(pod.current_version)
      },
      {
        key: "members",
        label: "Members",
        width: "8rem",
        sortable: false,
        render: (pod) => String(member_count(pod.spec))
      },
      {
        key: "created_at",
        label: "Created",
        width: "14rem",
        render: (pod) => format_timestamp(pod.created_at)
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
  PycPodsList,
  announce_session_expired,
  build_pod_definition_url,
  build_pod_definitions_url,
  extract_projects,
  format_clock_time,
  format_timestamp,
  has_next_page,
  has_previous_page,
  load_projects,
  member_count,
  pods_load_message_for_status,
  project_display_map,
  short_id
};
