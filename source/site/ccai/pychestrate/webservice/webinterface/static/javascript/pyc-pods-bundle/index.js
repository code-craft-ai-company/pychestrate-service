// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/datetime.js
var ISO_DATE_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
var ZONE_DESIGNATOR_PATTERN = /(?:Z|[+-]\d{2}:?\d{2})$/i;
function pad_two(number) {
  const rtnval = (number < 10 ? "0" : "") + String(number);
  return rtnval;
}
function parse_timestamp(value) {
  if (typeof value !== "string" || value.length === 0) {
    const rtnval2 = null;
    return rtnval2;
  }
  let text = value.trim();
  if (ISO_DATE_TIME_PATTERN.test(text) === true && ZONE_DESIGNATOR_PATTERN.test(text) === false) {
    text = text.replace(" ", "T") + "Z";
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = null;
    return rtnval2;
  }
  const rtnval = parsed;
  return rtnval;
}
function zone_label(instant) {
  try {
    const parts = new Intl.DateTimeFormat(void 0, { timeZoneName: "short" }).formatToParts(instant);
    for (const part of parts) {
      if (part.type === "timeZoneName" && part.value.length > 0) {
        const rtnval2 = part.value;
        return rtnval2;
      }
    }
  } catch (error) {
  }
  const offset_minutes = -instant.getTimezoneOffset();
  const sign = offset_minutes >= 0 ? "+" : "-";
  const magnitude = Math.abs(offset_minutes);
  const rtnval = "UTC" + sign + pad_two(Math.floor(magnitude / 60)) + ":" + pad_two(magnitude % 60);
  return rtnval;
}
function format_instant(instant) {
  const date_part = instant.getFullYear() + "-" + pad_two(instant.getMonth() + 1) + "-" + pad_two(instant.getDate());
  const time_part = pad_two(instant.getHours()) + ":" + pad_two(instant.getMinutes());
  const rtnval = date_part + " " + time_part + " " + zone_label(instant);
  return rtnval;
}
function format_clock_instant(instant) {
  const rtnval = pad_two(instant.getHours()) + ":" + pad_two(instant.getMinutes()) + ":" + pad_two(instant.getSeconds()) + " " + zone_label(instant);
  return rtnval;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/empty-state.js
function build_empty_state({ class_name, message, next_step, link, inline, role }) {
  const paragraph = document.createElement(inline === true ? "span" : "p");
  if (typeof class_name === "string" && class_name.length > 0) {
    paragraph.classList.add(class_name);
  }
  paragraph.setAttribute("data-role", "empty-state");
  if (typeof role === "string" && role.length > 0) {
    paragraph.setAttribute("role", role);
  }
  const words = [message];
  if (typeof next_step === "string" && next_step.length > 0) {
    words.push(next_step);
  }
  paragraph.appendChild(document.createTextNode(words.join(" ")));
  if (link !== void 0 && link !== null) {
    paragraph.appendChild(document.createTextNode(" "));
    const anchor = document.createElement("a");
    if (typeof link.class_name === "string" && link.class_name.length > 0) {
      anchor.classList.add(link.class_name);
    }
    anchor.setAttribute("href", link.href);
    anchor.setAttribute("data-role", "empty-state-link");
    anchor.textContent = link.label;
    paragraph.appendChild(anchor);
  }
  return paragraph;
}
function show_no_projects(region, { link_class_name }) {
  region.replaceChildren(
    build_empty_state({
      inline: true,
      message: "No projects exist yet.",
      next_step: "This page works inside a project, so create one first.",
      link: { href: "/projects/create", label: "Create a project", class_name: link_class_name }
    })
  );
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/view-state.js
function query_value(name) {
  if (typeof window === "undefined") {
    return "";
  }
  const value = new URLSearchParams(window.location.search).get(name);
  return value === null ? "" : value.trim();
}
function query_choice(name, allowed) {
  const value = query_value(name);
  return allowed.indexOf(value) >= 0 ? value : "";
}
function page_from_query() {
  const parsed = Number.parseInt(query_value("page"), 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1;
}
function mirror_to_query(values) {
  if (typeof window === "undefined" || typeof window.history === "undefined") {
    return;
  }
  const url = new URL(window.location.href);
  for (const name of Object.keys(values)) {
    const value = values[name];
    if (typeof value === "string" && value.length > 0) {
      url.searchParams.set(name, value);
    } else {
      url.searchParams.delete(name);
    }
  }
  const next = url.pathname + url.search + url.hash;
  if (next !== window.location.pathname + window.location.search + window.location.hash) {
    window.history.replaceState(window.history.state, "", next);
  }
}
function keep_list_state_on_back(anchor, list_path) {
  anchor.addEventListener("click", (event) => {
    try {
      const from = new URL(document.referrer);
      if (from.origin === window.location.origin && from.pathname === list_path && window.history.length > 1) {
        event.preventDefault();
        window.history.back();
      }
    } catch (reason) {
    }
  });
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-pods-bundle/pods-list-view.js
var DEFAULT_PER_PAGE = 25;
var PROJECTS_API_PATH = "/api/v1/projects";
var PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
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
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to pods.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This project was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load pods (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
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
var PycPodsList = class extends HTMLElement {
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
      page: page_from_query(),
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
      this._state.page = event.detail.page;
      mirror_to_query({ page: this._state.page > 1 ? String(this._state.page) : "" });
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
      show_no_projects(region, {});
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-pods-list__projects-notice--error");
      region.textContent = "You don't have permission to list projects \u2014 enter a project id directly.";
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
    mirror_to_query({
      project_id: this._state.projectFilter,
      page: this._state.page > 1 ? String(this._state.page) : ""
    });
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
    this._stamp_region.textContent = "as of " + format_clock_time(/* @__PURE__ */ new Date());
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
      if (this._projectsNoticeKind === "empty") {
        region.replaceChildren();
        this._render_pager();
        return;
      }
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
      loading.textContent = "Loading pods\u2026";
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
      const empty = build_empty_state({ class_name: "pyc-pods-list__status", message: "No pods in this project yet.", next_step: "A pod appears when a client enrolls with an enrollment token for it.", link: { href: "/admin/enrollment-tokens", label: "Mint an enrollment token" } });
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
        render: (pod) => pod.pod_name !== null && pod.pod_name.length > 0 ? pod.pod_name : "\u2014"
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
    if (this._pager === null || this._pager === void 0) {
      return;
    }
    this._pager.setAttribute("page", String(this._state.page));
    this._pager.setAttribute("page-size", String(this._state.perPage));
    this._pager.setAttribute("total-items", String(this._state.total));
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/permissions.js
var PERMISSIONS_URL = "/api/v1/me/permissions";
var held = null;
function held_permissions() {
  if (held !== null) {
    return held;
  }
  held = (async () => {
    try {
      const response = await fetch(PERMISSIONS_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok !== true) {
        return null;
      }
      const body = await response.json();
      if (body === null || typeof body !== "object" || Array.isArray(body.permissions) === false) {
        return null;
      }
      return new Set(body.permissions.filter((key) => typeof key === "string"));
    } catch (reason) {
      return null;
    }
  })();
  return held;
}
async function may(permission_key) {
  const keys = await held_permissions();
  return keys === null ? true : keys.has(permission_key);
}
function hide_unless_may(element, permission_key) {
  void may(permission_key).then((allowed) => {
    if (allowed === false) {
      element.hidden = true;
    }
  });
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/admin-contact.js
function with_access_request(message) {
  if (typeof message !== "string" || message.startsWith("You do not have permission") === false) {
    return message;
  }
  if (/administrator|contact/i.test(message) === true) {
    return message;
  }
  const sentence = access_request_sentence();
  return sentence.length > 0 ? message + " " + sentence : message;
}
function access_request_sentence() {
  if (typeof document === "undefined") {
    return "";
  }
  const shell = document.querySelector("pyc-site-shell");
  const contact = shell === null ? "" : (shell.getAttribute("admin-contact") || "").trim();
  return contact.length > 0 ? "To ask for access, contact " + contact + "." : "";
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/toast.js
var DEFAULT_AUTO_DISMISS_MS = 8e3;
function show_toast(region, message, tone, options) {
  if (region === null || region === void 0) {
    return null;
  }
  const settings = options !== null && typeof options === "object" ? options : {};
  const prefix = typeof settings.class_prefix === "string" ? settings.class_prefix : "pyc";
  if (region.getAttribute("role") === null) {
    region.setAttribute("role", "status");
  }
  if (region.getAttribute("aria-live") === null) {
    region.setAttribute("aria-live", "polite");
  }
  const toast = document.createElement("div");
  toast.classList.add(prefix + "__toast");
  toast.setAttribute("data-role", typeof settings.data_role === "string" ? settings.data_role : "toast");
  toast.setAttribute("data-tone", tone);
  toast.setAttribute("role", tone === "error" ? "alert" : "status");
  const text = document.createElement("span");
  text.classList.add(prefix + "__toast-message");
  text.textContent = with_access_request(message);
  toast.appendChild(text);
  const link = settings.link !== null && typeof settings.link === "object" ? settings.link : null;
  if (link !== null) {
    const anchor = document.createElement("a");
    anchor.classList.add(prefix + "__toast-link");
    anchor.setAttribute("href", link.href);
    if (typeof link.data_role === "string") {
      anchor.setAttribute("data-role", link.data_role);
    }
    anchor.textContent = link.text;
    toast.appendChild(anchor);
  }
  const dismiss = document.createElement("mj-button");
  dismiss.classList.add(prefix + "__toast-dismiss");
  dismiss.setAttribute("type", "button");
  dismiss.setAttribute("aria-label", typeof settings.dismiss_label === "string" ? settings.dismiss_label : "Dismiss");
  dismiss.textContent = "\xD7";
  dismiss.addEventListener("click", () => {
    toast.remove();
  });
  toast.appendChild(dismiss);
  region.replaceChildren(toast);
  const delay = typeof settings.auto_dismiss_ms === "number" ? settings.auto_dismiss_ms : DEFAULT_AUTO_DISMISS_MS;
  if (tone !== "error" && link === null && delay > 0) {
    window.setTimeout(() => {
      if (toast.parentNode === region) {
        toast.remove();
      }
    }, delay);
  }
  return toast;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/run-labels.js
function state_label(state) {
  if (typeof state !== "string" || state.length === 0) {
    return "\u2014";
  }
  const words = state.replace(/[_-]+/g, " ");
  return /^[A-Z0-9 ]+$/.test(words) ? words.toLowerCase() : words;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/confirm.js
function confirm_action(source, message, confirm_label, options) {
  const tone = options !== null && options !== void 0 && options.tone === "neutral" ? "neutral" : "danger";
  return new Promise((resolve) => {
    const request = new CustomEvent("pyc-confirm-request", {
      bubbles: true,
      composed: true,
      cancelable: true,
      detail: { message, confirm_label, tone, resolve }
    });
    const answered_by_shell = source.dispatchEvent(request) === false;
    if (answered_by_shell === false) {
      resolve(window.confirm(message));
    }
  });
}
function label_from_button(button, fallback) {
  const text = button !== null && button !== void 0 && typeof button.textContent === "string" ? button.textContent.replace(/\s+/g, " ").trim() : "";
  return text.length > 0 && text.length <= 40 ? text : fallback;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/problem-detail.js
var REASON_PHRASES = [
  "bad request",
  "unauthorized",
  "unauthenticated",
  "authentication required.",
  "forbidden",
  "not found",
  "method not allowed",
  "conflict",
  "unprocessable entity",
  "validation failed",
  "internal server error",
  "service unavailable",
  "error"
];
function problem_detail_of_body(body) {
  if (body !== null && typeof body === "object" && typeof body.detail === "string") {
    const line = body.detail.split(/\r?\n/).map((part) => part.trim()).filter((part) => part.length > 0).join(" ");
    if (line.length > 0 && REASON_PHRASES.indexOf(line.toLowerCase()) < 0) {
      return line;
    }
  }
  return "";
}
async function read_problem_detail(response) {
  if (response.ok === true) {
    return "";
  }
  try {
    return problem_detail_of_body(await response.json());
  } catch (error) {
    return "";
  }
}
function message_with_detail(prefix, detail, generic) {
  if (typeof detail === "string" && detail.length > 0) {
    return prefix + ": " + detail;
  }
  return generic;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/page-title.js
var SECTION_TITLE_KEY = "pycSectionTitle";
var ENTITY_TITLE_KEY = "pycEntityTitle";
function set_entity_title(entity_label) {
  if (typeof entity_label !== "string" || entity_label.trim().length === 0) {
    return;
  }
  const root = document.documentElement;
  if (root.dataset[ENTITY_TITLE_KEY] === void 0 || document.title !== root.dataset[ENTITY_TITLE_KEY]) {
    root.dataset[SECTION_TITLE_KEY] = document.title;
  }
  const title = entity_label.trim() + " \xB7 " + root.dataset[SECTION_TITLE_KEY];
  root.dataset[ENTITY_TITLE_KEY] = title;
  document.title = title;
  return;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-pods-bundle/pod-detail-view.js
var POD_STATES = [
  "DEFINED",
  "PROVISIONING",
  "READY",
  "IN_USE",
  "DRAINING",
  "RELEASED",
  "CLIENT_LOST",
  "FAILED"
];
var TRANSIENT_POD_STATES = [
  "PROVISIONING",
  "DRAINING"
];
var TERMINAL_POD_STATES = [
  "RELEASED"
];
var DRAINABLE_POD_STATES = [
  "READY",
  "IN_USE"
];
var RETIRABLE_POD_STATES = [
  "DRAINING",
  "FAILED"
];
var POLL_INTERVAL_TRANSIENT_MS = 5e3;
var POLL_INTERVAL_SETTLED_MS = 15e3;
var UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function pod_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/pods/";
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
  const rtnval = value.trim();
  return rtnval;
}
function is_valid_pod_id(pod_id) {
  if (typeof pod_id !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(pod_id);
  return rtnval;
}
function is_transient_pod_state(state) {
  const rtnval = TRANSIENT_POD_STATES.indexOf(state) >= 0;
  return rtnval;
}
function is_terminal_pod_state(state) {
  const rtnval = TERMINAL_POD_STATES.indexOf(state) >= 0;
  return rtnval;
}
function pod_state_tone(state) {
  if (state === "READY" || state === "IN_USE") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (state === "FAILED" || state === "CLIENT_LOST") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (state === "PROVISIONING" || state === "DRAINING") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function build_pod_state_url(project_id, pod_id) {
  const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) + "/pods/" + encodeURIComponent(pod_id) + "/state";
  return rtnval;
}
function build_pod_state_history_url(project_id, pod_id) {
  const rtnval = build_pod_state_url(project_id, pod_id) + "/history";
  return rtnval;
}
function build_pod_transitions_url(project_id, pod_id) {
  const rtnval = build_pod_state_url(project_id, pod_id) + "/transitions";
  return rtnval;
}
function build_pod_registration_url(project_id, pod_id) {
  const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) + "/pods/" + encodeURIComponent(pod_id) + "/registration";
  return rtnval;
}
function build_pod_registrations_url(project_id, pod_id) {
  const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) + "/pods/" + encodeURIComponent(pod_id) + "/registrations";
  return rtnval;
}
function detail_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to pods.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "No pod with this id in this project.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load this pod (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function runtime_section_message_for_status(status, what) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to " + what + ".";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't load " + what + " \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load " + what + " (HTTP " + String(status) + ").";
  return rtnval;
}
function transition_message_for_status(status, event_kind) {
  if (status === 200) {
    if (event_kind === "drain") {
      const rtnval22 = "Drain started \u2014 the pod is now draining.";
      return rtnval22;
    }
    const rtnval2 = "Pod retired \u2014 its registration is released.";
    return rtnval2;
  }
  if (status === 400) {
    const rtnval2 = "The transition request was rejected (HTTP 400).";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to change pod state.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This pod's runtime state was not found.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "That action is not allowed from the pod's current state.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to apply the transition (HTTP " + String(status) + ").";
  return rtnval;
}
var PycPodDetail = class extends HTMLElement {
  _pod_id;
  _project_id;
  _definition;
  _definition_status;
  _state_row;
  _registration;
  _registration_history;
  _state_history;
  _runtime_status;
  _project_names;
  _loading;
  _errored;
  _transient;
  _poll_status;
  _poll_timer;
  _root;
  _toast_region;
  _stamp_region;
  _on_visibility_change;
  constructor() {
    super();
    this._pod_id = "";
    this._project_id = "";
    this._definition = null;
    this._definition_status = 0;
    this._state_row = null;
    this._registration = null;
    this._registration_history = [];
    this._state_history = [];
    this._runtime_status = {
      state: 0,
      registration: 0,
      registrations: 0,
      stateHistory: 0
    };
    this._project_names = null;
    this._loading = false;
    this._errored = false;
    this._transient = false;
    this._poll_status = "idle";
    this._poll_timer = null;
    this._root = null;
    this._toast_region = null;
    this._stamp_region = null;
    this._on_visibility_change = () => {
      this._handle_visibility_change();
    };
  }
  /**
   * Observed attributes -- ``pod-id`` / ``project-id`` may be
   * supplied explicitly by a host; otherwise they are read from
   * the path / query string on mount.
   */
  static get observedAttributes() {
    const rtnval = ["pod-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      podId: this._pod_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored,
      pollStatus: this._poll_status,
      transient: this._transient,
      runtimeStatus: {
        state: this._runtime_status.state,
        registration: this._runtime_status.registration,
        registrations: this._runtime_status.registrations,
        stateHistory: this._runtime_status.stateHistory
      }
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the pod + project ids, render the
   * chrome, and fetch the initial snapshot.
   */
  connectedCallback() {
    const attr_pod = this.getAttribute("pod-id");
    if (attr_pod !== null && attr_pod.length > 0) {
      this._pod_id = attr_pod;
    } else {
      this._pod_id = pod_id_from_path(window.location.pathname);
    }
    const attr_project = this.getAttribute("project-id");
    if (attr_project !== null && attr_project.length > 0) {
      this._project_id = attr_project;
    } else {
      this._project_id = project_id_from_search(window.location.search);
    }
    this._render_chrome();
    void this._load();
    if (typeof document !== "undefined") {
      document.addEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  /**
   * Lifecycle hook -- stop the live-poll timer and drop the
   * visibility listener so a navigation away never leaks either.
   */
  disconnectedCallback() {
    this._stop_poll();
    if (typeof document !== "undefined") {
      document.removeEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  /**
   * Fetch the pod snapshot then start the live-poll loop when
   * the pod is not in a terminal state. Exposed so unit tests can
   * await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_pod_id(this._pod_id) === false) {
      this._loading = false;
      this._errored = true;
      this._definition_status = 0;
      this._render_body();
      return;
    }
    if (this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._definition_status = 0;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const definition_env = await this._fetch_json(
      build_pod_definition_url(this._project_id, this._pod_id),
      "definition_fetch_failed"
    );
    this._definition_status = definition_env.status;
    if (definition_env.ok === false || definition_env.body === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._definition = definition_env.body;
    if (this._project_names === null) {
      const projects_outcome = await load_projects();
      if (projects_outcome.ok === true) {
        this._project_names = project_display_map(
          projects_outcome.projects
        );
      } else {
        this._project_names = {};
      }
    }
    await this._refresh_runtime();
    this._loading = false;
    this._errored = false;
    this._render_stamp();
    this._render_body();
    this._update_poll_state();
    return;
  }
  /**
   * Re-fetch the live state, registration and history rows in
   * parallel. Shared by the initial load and each poll cycle.
   * Each fetch's HTTP status is tracked so the sections can
   * render an honest error state instead of a fake empty one.
   */
  async _refresh_runtime() {
    const state_promise = this._fetch_json(
      build_pod_state_url(this._project_id, this._pod_id),
      "state_fetch_failed"
    );
    const registration_promise = this._fetch_json(
      build_pod_registration_url(this._project_id, this._pod_id),
      "registration_fetch_failed"
    );
    const registrations_promise = this._fetch_json(
      build_pod_registrations_url(this._project_id, this._pod_id),
      "registrations_fetch_failed"
    );
    const state_history_promise = this._fetch_json(
      build_pod_state_history_url(this._project_id, this._pod_id),
      "state_history_fetch_failed"
    );
    const envelopes = await Promise.all([
      state_promise,
      registration_promise,
      registrations_promise,
      state_history_promise
    ]);
    const state_env = envelopes[0];
    const registration_env = envelopes[1];
    const registrations_env = envelopes[2];
    const state_history_env = envelopes[3];
    this._runtime_status.state = state_env.status;
    if (state_env.ok === true && state_env.body !== null) {
      this._state_row = state_env.body;
      this._transient = is_transient_pod_state(state_env.body.state);
    } else {
      this._state_row = null;
      this._transient = false;
    }
    this._runtime_status.registration = registration_env.status;
    if (registration_env.ok === true) {
      this._registration = registration_env.body;
    } else {
      this._registration = null;
    }
    this._runtime_status.registrations = registrations_env.status;
    if (registrations_env.ok === true && Array.isArray(registrations_env.body) === true) {
      this._registration_history = registrations_env.body;
    } else {
      this._registration_history = [];
    }
    this._runtime_status.stateHistory = state_history_env.status;
    if (state_history_env.ok === true && Array.isArray(state_history_env.body) === true) {
      this._state_history = state_history_env.body;
    } else {
      this._state_history = [];
    }
    return;
  }
  /**
   * Fetch a JSON document. Never throws -- a network error yields
   * ``{ok: false, status: 0, body: null}``. A 401 announces the
   * shared ``pyc-session-401`` event so the shell can surface the
   * expired session.
   *
   * @param url Relative URL to GET.
   * @param failure_tag A log tag for diagnostic warnings.
   *
   * @returns ``{ok, status, body}``.
   */
  async _fetch_json(url, failure_tag) {
    let status = 0;
    let ok = false;
    let body = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      ok = response.ok;
      if (ok === true) {
        body = await response.json();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pods." + failure_tag,
        { reason: String(reason) }
      );
    }
    if (status === 401) {
      announce_session_expired();
    }
    const rtnval = { ok, status, body };
    return rtnval;
  }
  /**
   * POST an operator lifecycle event (``drain`` / ``deregister``)
   * to the pod. Exposed so unit tests can drive a transition
   * without a button.
   *
   * @param event_kind The lifecycle event to apply.
   *
   * @returns ``{ok, status, message}``.
   */
  async applyTransition(event_kind) {
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(
        build_pod_transitions_url(this._project_id, this._pod_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ event_kind })
        }
      );
      status = response.status;
      detail = await read_problem_detail(response);
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pods.transition_failed",
        { reason: String(reason), event_kind }
      );
    }
    if (status === 401) {
      announce_session_expired();
    }
    const ok = status === 200;
    const rtnval = {
      ok,
      status,
      message: message_with_detail("Pod not updated", detail, transition_message_for_status(status, event_kind))
    };
    return rtnval;
  }
  async _on_transition(event_kind, confirm_text, button) {
    const confirmed = await confirm_action(this, confirm_text, label_from_button(button, "Continue"));
    if (confirmed !== true) {
      button.toggleAttribute("disabled", false);
      return;
    }
    const outcome = await this.applyTransition(event_kind);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._refresh_runtime();
      this._render_stamp();
      this._render_body();
      this._update_poll_state();
    }
    return;
  }
  /**
   * Start / stop the poll loop from the current pod state. The
   * view polls in every non-terminal state (transient states at
   * 5s, settled ones at 15s) and also while the state is
   * unavailable so a transient fetch failure recovers on its own.
   * Only a terminal (RELEASED) pod stops the loop.
   */
  _update_poll_state() {
    if (this._definition === null) {
      this._stop_poll();
      this._poll_status = "stopped";
      this._render_poll_banner();
      return;
    }
    const state_known = this._state_row !== null;
    if (state_known === true && is_terminal_pod_state(this._state_row.state) === true) {
      this._stop_poll();
      this._poll_status = "stopped";
      this._render_poll_banner();
      return;
    }
    this._poll_status = "polling";
    this._render_poll_banner();
    if (this._poll_timer === null) {
      this._schedule_poll();
    }
    return;
  }
  _poll_interval_ms() {
    if (this._transient === true) {
      const rtnval2 = POLL_INTERVAL_TRANSIENT_MS;
      return rtnval2;
    }
    const rtnval = POLL_INTERVAL_SETTLED_MS;
    return rtnval;
  }
  _schedule_poll() {
    const timer = setTimeout(() => {
      this._poll_timer = null;
      void this._poll_once();
    }, this._poll_interval_ms());
    const handle = timer;
    if (typeof handle.unref === "function") {
      handle.unref();
    }
    this._poll_timer = timer;
    return;
  }
  /**
   * Run one poll cycle -- re-fetch runtime rows, re-render, and
   * either reschedule (still live) or stop (now terminal).
   * Exposed so unit tests can drive a poll cycle without waiting
   * on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    if (typeof document !== "undefined" && document.hidden === true) {
      return;
    }
    await this._refresh_runtime();
    this._render_stamp();
    this._render_body();
    this._update_poll_state();
    return;
  }
  _stop_poll() {
    if (this._poll_timer !== null) {
      clearTimeout(this._poll_timer);
      this._poll_timer = null;
    }
    return;
  }
  _handle_visibility_change() {
    if (typeof document === "undefined") {
      return;
    }
    if (document.hidden === true) {
      this._stop_poll();
      return;
    }
    if (this._poll_timer === null && this._poll_status === "polling") {
      void this._poll_once();
    }
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-pod-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Pod detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-pod-detail__heading");
    heading.textContent = "Pod detail";
    root.appendChild(heading);
    const toolbar = document.createElement("div");
    toolbar.classList.add("pyc-pod-detail__toolbar");
    const back = document.createElement("a");
    back.classList.add("pyc-pod-detail__back-link");
    let back_href = "/pods";
    if (this._project_id.length > 0) {
      back_href = "/pods?project_id=" + encodeURIComponent(this._project_id);
    }
    back.setAttribute("href", back_href);
    back.setAttribute("data-role", "back-link");
    keep_list_state_on_back(back, "/pods");
    back.textContent = "Back to pods";
    toolbar.appendChild(back);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-pod-detail__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._load();
    });
    toolbar.appendChild(refresh_button);
    const stamp = document.createElement("span");
    stamp.classList.add("pyc-pod-detail__stamp");
    stamp.setAttribute("data-role", "last-updated");
    toolbar.appendChild(stamp);
    this._stamp_region = stamp;
    root.appendChild(toolbar);
    const banner = document.createElement("p");
    banner.classList.add("pyc-pod-detail__banner");
    banner.setAttribute("data-role", "poll-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;
    root.appendChild(banner);
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-pod-detail__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const body = document.createElement("div");
    body.classList.add("pyc-pod-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  _render_stamp() {
    if (this._stamp_region === null) {
      return;
    }
    this._stamp_region.textContent = "as of " + format_clock_time(/* @__PURE__ */ new Date());
    return;
  }
  /**
   * Resolve the definition-load error message from how the load
   * failed -- a malformed id and a missing project id are caller
   * mistakes, the rest map from the HTTP status.
   */
  _load_error_message() {
    if (is_valid_pod_id(this._pod_id) === false) {
      const rtnval2 = "No pod with this id.";
      return rtnval2;
    }
    if (this._project_id.length === 0) {
      const rtnval2 = "A project id is required \u2014 open this pod from the pods list.";
      return rtnval2;
    }
    const rtnval = detail_load_message_for_status(this._definition_status);
    return rtnval;
  }
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
      loading.classList.add("pyc-pod-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading pod\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._definition === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-pod-detail__status",
        "pyc-pod-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      const message = document.createElement("span");
      message.textContent = this._load_error_message();
      error.appendChild(message);
      if (is_valid_pod_id(this._pod_id) === true && this._project_id.length > 0) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-pod-detail__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "error-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._load();
        });
        error.appendChild(retry);
      }
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._definition));
    fragment.appendChild(this._build_members(this._definition));
    fragment.appendChild(this._build_registration());
    fragment.appendChild(this._build_registration_history());
    fragment.appendChild(this._build_state_history());
    body.replaceChildren(fragment);
    return;
  }
  /**
   * Resolve a project's display name from the cached projects
   * map, falling back to the raw id.
   */
  _project_display_name(project_id) {
    if (this._project_names !== null) {
      const display = this._project_names[project_id];
      if (typeof display === "string" && display.length > 0) {
        const rtnval2 = display;
        return rtnval2;
      }
    }
    const rtnval = project_id;
    return rtnval;
  }
  _build_summary(definition) {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pod summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-pod-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-pod-detail__pod-id");
    id_value.setAttribute("data-role", "pod-id");
    id_value.textContent = short_id(definition.pod_id);
    set_entity_title("Pod " + short_id(definition.pod_id));
    id_value.title = definition.pod_id;
    id_row.appendChild(id_value);
    const badge = document.createElement("mj-chip");
    badge.classList.add("pyc-pod-detail__badge");
    badge.setAttribute("data-role", "state-badge");
    const awaiting_client = this._state_row === null && this._runtime_status.state === 404;
    if (this._state_row !== null) {
      badge.setAttribute("data-tone", pod_state_tone(this._state_row.state));
      badge.textContent = state_label(this._state_row.state);
    } else if (awaiting_client === true) {
      badge.setAttribute("data-tone", "neutral");
      badge.textContent = "Declared";
      badge.title = "Waiting for a client to enroll on this pod.";
    } else {
      badge.setAttribute("data-tone", "neutral");
      badge.textContent = "State unavailable";
      badge.title = runtime_section_message_for_status(
        this._runtime_status.state,
        "the pod state"
      );
    }
    id_row.appendChild(badge);
    id_row.appendChild(this._build_actions());
    section.appendChild(id_row);
    if (awaiting_client === true) {
      const waiting = document.createElement("p");
      waiting.classList.add("pyc-pod-detail__status", "pyc-pod-detail__status--inline");
      waiting.setAttribute("data-role", "state-awaiting-client");
      waiting.textContent = "Declared \u2014 waiting for a client. Mint an enrollment token for this pod name and enroll a machine to bring it online.";
      section.appendChild(waiting);
    } else if (this._state_row === null) {
      const state_error = document.createElement("p");
      state_error.classList.add(
        "pyc-pod-detail__status",
        "pyc-pod-detail__status--error",
        "pyc-pod-detail__status--inline"
      );
      state_error.setAttribute("data-role", "state-error");
      state_error.textContent = runtime_section_message_for_status(
        this._runtime_status.state,
        "the pod state"
      );
      section.appendChild(state_error);
    }
    const grid = document.createElement("dl");
    grid.classList.add("pyc-pod-detail__grid");
    this._append_field(grid, "Pod id", definition.pod_id);
    this._append_field(grid, "Pod name", definition.pod_name);
    this._append_field(
      grid,
      "Project",
      this._project_display_name(definition.project_id),
      definition.project_id
    );
    this._append_field(
      grid,
      "Version",
      "v" + String(definition.current_version)
    );
    this._append_field(
      grid,
      "Members",
      String(member_count(definition.spec))
    );
    this._append_field(
      grid,
      "Created",
      format_timestamp(definition.created_at)
    );
    if (definition.spec_hash !== null && definition.spec_hash !== void 0 && definition.spec_hash.length > 0) {
      this._append_field(grid, "Spec hash", definition.spec_hash);
    }
    if (this._state_row !== null) {
      this._append_field(
        grid,
        "Last transition",
        format_timestamp(this._state_row.last_transition_at)
      );
      const event = this._state_row.last_transition_event;
      if (event !== null && event !== void 0 && event.length > 0) {
        this._append_field(grid, "Last event", event);
      }
    }
    section.appendChild(grid);
    return section;
  }
  /**
   * Build the operator action buttons. Drain is legal from READY
   * / IN_USE, retire (deregister) from DRAINING / FAILED --
   * mirroring the server's transition table so an always-illegal
   * click never leaves the page.
   */
  _build_actions() {
    const actions = document.createElement("span");
    actions.classList.add("pyc-pod-detail__actions");
    actions.setAttribute("data-role", "pod-actions");
    const state_known = this._state_row !== null;
    const current_state = state_known === true ? this._state_row.state : "";
    const drain_button = document.createElement("mj-button");
    drain_button.classList.add("pyc-pod-detail__button");
    drain_button.setAttribute("type", "button");
    drain_button.setAttribute("data-role", "drain-action");
    drain_button.textContent = "Drain";
    hide_unless_may(drain_button, "system:pods.write");
    const drain_allowed = DRAINABLE_POD_STATES.indexOf(current_state) >= 0;
    if (drain_allowed === false) {
      drain_button.toggleAttribute("disabled", true);
      drain_button.title = state_known === true ? "Drain is only available while the pod is ready or in use." : "The pod state is unavailable \u2014 actions are disabled.";
    } else {
      drain_button.addEventListener("click", () => {
        drain_button.toggleAttribute("disabled", true);
        const confirm_text = "Drain pod " + short_id(this._pod_id) + "? The pod stops accepting new work, finishes what is in flight, and moves to draining.";
        void this._on_transition("drain", confirm_text, drain_button);
      });
    }
    actions.appendChild(drain_button);
    const retire_button = document.createElement("mj-button");
    retire_button.classList.add("pyc-pod-detail__button");
    retire_button.setAttribute("type", "button");
    retire_button.setAttribute("data-role", "retire-action");
    retire_button.textContent = "Retire";
    hide_unless_may(retire_button, "system:pods.write");
    const retire_allowed = RETIRABLE_POD_STATES.indexOf(current_state) >= 0;
    if (retire_allowed === false) {
      retire_button.toggleAttribute("disabled", true);
      retire_button.title = state_known === true ? "Retire is only available while the pod is draining or failed." : "The pod state is unavailable \u2014 actions are disabled.";
    } else {
      retire_button.addEventListener("click", () => {
        retire_button.toggleAttribute("disabled", true);
        const confirm_text = "Retire pod " + short_id(this._pod_id) + "? Its registration is released and the pod moves to released \u2014 it must be re-provisioned before it can serve work again.";
        void this._on_transition("deregister", confirm_text, retire_button);
      });
    }
    actions.appendChild(retire_button);
    return actions;
  }
  _build_members(definition) {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__members");
    section.setAttribute("data-role", "members-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pod members");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pod-detail__section-heading");
    heading.textContent = "Members";
    section.appendChild(heading);
    const list = document.createElement("ul");
    list.classList.add("pyc-pod-detail__member-list");
    const spec = definition.spec;
    let members = [];
    if (spec !== null && spec !== void 0) {
      const raw = spec["members"];
      if (Array.isArray(raw) === true) {
        members = raw;
      }
    }
    if (members.length === 0) {
      const empty = document.createElement("li");
      empty.classList.add("pyc-pod-detail__member-empty");
      empty.textContent = "This pod definition declares no members.";
      list.appendChild(empty);
    } else {
      for (const member of members) {
        const item = document.createElement("li");
        item.classList.add("pyc-pod-detail__member-entry");
        item.textContent = this._member_label(member);
        list.appendChild(item);
      }
    }
    section.appendChild(list);
    return section;
  }
  /**
   * Derive a display label for one pod-spec member entry. A
   * member is typically an object carrying a ``name`` / ``kind``;
   * fall back to a JSON rendering when the shape is unexpected.
   *
   * @param member One entry from the spec's ``members`` array.
   *
   * @returns A human-readable label.
   */
  _member_label(member) {
    if (member !== null && typeof member === "object") {
      const record = member;
      const name = record["name"];
      const kind = record["kind"];
      const name_str = typeof name === "string" ? name : "";
      const kind_str = typeof kind === "string" ? kind : "";
      if (name_str.length > 0 && kind_str.length > 0) {
        const rtnval2 = name_str + " (" + kind_str + ")";
        return rtnval2;
      }
      if (name_str.length > 0) {
        const rtnval2 = name_str;
        return rtnval2;
      }
      if (kind_str.length > 0) {
        const rtnval2 = kind_str;
        return rtnval2;
      }
    }
    if (typeof member === "string") {
      const rtnval2 = member;
      return rtnval2;
    }
    const rtnval = JSON.stringify(member);
    return rtnval;
  }
  /**
   * Build one section-level error paragraph for a failed runtime
   * fetch -- used instead of the section's empty state so a
   * failure never masquerades as "no data".
   */
  _build_section_error(role, status, what) {
    const error = document.createElement("p");
    error.classList.add(
      "pyc-pod-detail__status",
      "pyc-pod-detail__status--error"
    );
    error.setAttribute("data-role", role);
    error.textContent = runtime_section_message_for_status(status, what);
    const rtnval = error;
    return rtnval;
  }
  _build_registration() {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__registration");
    section.setAttribute("data-role", "registration-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Registered client");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pod-detail__section-heading");
    heading.textContent = "Registered client";
    section.appendChild(heading);
    if (this._registration === null) {
      if (this._runtime_status.registration === 404) {
        const empty = document.createElement("p");
        empty.classList.add("pyc-pod-detail__status");
        empty.setAttribute("data-role", "registration-empty");
        empty.textContent = "No active registration for this pod.";
        section.appendChild(empty);
      } else {
        section.appendChild(
          this._build_section_error(
            "registration-error",
            this._runtime_status.registration,
            "the registration"
          )
        );
      }
      return section;
    }
    const grid = document.createElement("dl");
    grid.classList.add("pyc-pod-detail__grid");
    const client_id = this._registration.client_id;
    if (client_id !== null && client_id !== void 0 && client_id.length > 0) {
      const field = document.createElement("div");
      field.classList.add("pyc-pod-detail__field");
      const term = document.createElement("dt");
      term.textContent = "Client";
      const def = document.createElement("dd");
      const link = document.createElement("a");
      link.classList.add("pyc-pod-detail__client-link");
      link.setAttribute("href", "/clients/" + client_id);
      link.textContent = short_id(client_id);
      link.title = client_id;
      def.appendChild(link);
      field.appendChild(term);
      field.appendChild(def);
      grid.appendChild(field);
    } else {
      this._append_field(grid, "Client", "\u2014");
    }
    this._append_field(grid, "Registration state", state_label(this._registration.state));
    this._append_field(
      grid,
      "Definition version",
      "v" + String(this._registration.pod_definition_version)
    );
    this._append_field(
      grid,
      "Registered",
      format_timestamp(this._registration.registered_at)
    );
    section.appendChild(grid);
    return section;
  }
  _build_registration_history() {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__registration-history");
    section.setAttribute("data-role", "registration-history-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Registration history");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pod-detail__section-heading");
    heading.textContent = "Registration history";
    section.appendChild(heading);
    if (this._runtime_status.registrations !== 200) {
      section.appendChild(
        this._build_section_error(
          "registration-history-error",
          this._runtime_status.registrations,
          "the registration history"
        )
      );
      return section;
    }
    if (this._registration_history.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pod-detail__status");
      empty.setAttribute("data-role", "registration-history-empty");
      empty.textContent = "No registration history for this pod.";
      section.appendChild(empty);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-pod-detail__history-list");
    for (const row of this._registration_history) {
      const item = document.createElement("li");
      item.classList.add("pyc-pod-detail__history-entry");
      const summary = state_label(row.state) + " \xB7 v" + String(row.pod_definition_version) + " \xB7 " + format_timestamp(row.registered_at);
      item.textContent = summary;
      if (row.deregister_reason !== null && row.deregister_reason !== void 0 && row.deregister_reason.length > 0) {
        const reason = document.createElement("span");
        reason.classList.add("pyc-pod-detail__history-reason");
        reason.textContent = " \u2014 " + row.deregister_reason;
        item.appendChild(reason);
      }
      list.appendChild(item);
    }
    section.appendChild(list);
    return section;
  }
  _build_state_history() {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__state-history");
    section.setAttribute("data-role", "state-history-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Lifecycle history");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pod-detail__section-heading");
    heading.textContent = "Lifecycle history";
    section.appendChild(heading);
    if (this._runtime_status.stateHistory !== 200) {
      section.appendChild(
        this._build_section_error(
          "state-history-error",
          this._runtime_status.stateHistory,
          "the lifecycle history"
        )
      );
      return section;
    }
    if (this._state_history.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pod-detail__status");
      empty.setAttribute("data-role", "state-history-empty");
      empty.textContent = "No lifecycle transitions recorded.";
      section.appendChild(empty);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-pod-detail__history-list");
    for (const row of this._state_history) {
      const item = document.createElement("li");
      item.classList.add("pyc-pod-detail__history-entry");
      const from_label = row.from_state !== null && row.from_state !== void 0 ? state_label(row.from_state) : "\u2205";
      const summary = from_label + " \u2192 " + state_label(row.to_state) + " \xB7 " + format_timestamp(row.applied_at);
      item.textContent = summary;
      if (row.event_kind !== null && row.event_kind !== void 0 && row.event_kind.length > 0) {
        const event = document.createElement("span");
        event.classList.add("pyc-pod-detail__history-event");
        event.textContent = " (" + row.event_kind + ")";
        item.appendChild(event);
      }
      list.appendChild(item);
    }
    section.appendChild(list);
    return section;
  }
  _append_field(grid, label, value, title) {
    const field = document.createElement("div");
    field.classList.add("pyc-pod-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    if (typeof value === "string" && value.length > 0) {
      def.textContent = value;
    } else {
      def.textContent = "\u2014";
    }
    if (typeof title === "string" && title.length > 0) {
      def.title = title;
    }
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  /**
   * Show a toast in the toast region through the shared service: one at a
   * time, announced to assistive technology, a plain success goes away by itself.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-pod-detail" });
    return;
  }
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
      if (this._transient === true) {
        el.textContent = "Pod is mid-transition \u2014 refreshing every 5 seconds.";
      } else {
        el.textContent = "Live view \u2014 refreshing every 15 seconds.";
      }
      return;
    }
    el.hidden = true;
    el.textContent = "";
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-pods-bundle/clients-list-view.js
var CLIENT_STATUSES = [
  "ACTIVE",
  "SUSPENDED",
  "REVOKED"
];
var LIVENESS_STATES = [
  "ALIVE",
  "DEGRADED",
  "LOST"
];
var DEFAULT_PER_PAGE2 = 25;
var CLIENTS_API_PATH = "/api/v1/clients";
var CLIENTS_POLL_INTERVAL_MS = 15e3;
var CAPABILITY_TAG_DISPLAY_LIMIT = 6;
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
function build_client_revoke_url(client_id) {
  const rtnval = build_client_detail_url(client_id) + "/revoke";
  return rtnval;
}
function build_client_capabilities_url(client_id) {
  const rtnval = build_client_detail_url(client_id) + "/capabilities";
  return rtnval;
}
function short_id2(client_id) {
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
function format_timestamp2(value) {
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
var LIVENESS_LABELS = { ALIVE: "Alive", DEGRADED: "Stale", LOST: "Lost" };
function client_liveness_display(client) {
  if (client === null || client === void 0) {
    const rtnval2 = { label: "\u2014", tone: "neutral" };
    return rtnval2;
  }
  if (client.status === "REVOKED") {
    const rtnval2 = { label: "\u2014", tone: "neutral" };
    return rtnval2;
  }
  const tone = liveness_tone(client.liveness_state);
  if (client.last_seen === null || client.last_seen === void 0 || client.last_seen === "") {
    const rtnval2 = { label: "Never seen", tone: tone === "ok" ? "neutral" : tone };
    return rtnval2;
  }
  const label = LIVENESS_LABELS[client.liveness_state] || String(client.liveness_state || "\u2014");
  const rtnval = { label, tone };
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
function advertised_capability_tags(capabilities) {
  const rtnval = [];
  if (Array.isArray(capabilities) === false) {
    return rtnval;
  }
  const add_tag = (tag) => {
    if (tag.length > 0 && rtnval.includes(tag) === false) {
      rtnval.push(tag);
    }
  };
  for (const capability of capabilities) {
    if (capability === null || typeof capability !== "object") {
      continue;
    }
    const kind = capability.kind;
    if (typeof kind !== "string" || kind.length === 0) {
      continue;
    }
    add_tag(kind);
    const value = capability.value;
    if (kind !== "rpa" || value === null || typeof value !== "object") {
      continue;
    }
    const job_types = Array.isArray(value.job_types) === true ? value.job_types : [];
    for (const job_type of job_types) {
      const name = String(job_type);
      if (name.length > 0) {
        add_tag("rpa:" + name);
      }
    }
    const tags = Array.isArray(value.tags) === true ? value.tags : [];
    for (const tag of tags) {
      add_tag(String(tag));
    }
  }
  return rtnval;
}
function latest_capability_update(capabilities) {
  let rtnval = "";
  if (Array.isArray(capabilities) === false) {
    return rtnval;
  }
  for (const capability of capabilities) {
    if (capability === null || typeof capability !== "object") {
      continue;
    }
    const updated_at = capability.updated_at;
    if (typeof updated_at === "string" && updated_at > rtnval) {
      rtnval = updated_at;
    }
  }
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
function clients_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to clients.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load clients (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function revoke_message_for_status(status) {
  if (status === 200) {
    const rtnval2 = "Client revoked.";
    return rtnval2;
  }
  if (status === 400) {
    const rtnval2 = "The revoke request was rejected (HTTP 400).";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to revoke clients.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "No client with this id \u2014 it may already be gone.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to revoke client (HTTP " + String(status) + ").";
  return rtnval;
}
async function perform_client_revoke(client_id) {
  let status = 0;
  let detail = "";
  try {
    const response = await fetch(build_client_revoke_url(client_id), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        reason: "ADMIN_REQUEST",
        note: "Revoked from the fleet UI"
      })
    });
    status = response.status;
    detail = await read_problem_detail(response);
  } catch (reason) {
    console.warn(
      "pychestrate.ui.clients.revoke_failed",
      { reason: String(reason) }
    );
  }
  if (status === 401) {
    announce_session_expired();
  }
  const ok = status === 200;
  const rtnval = {
    ok,
    status,
    message: message_with_detail("Client not revoked", detail, revoke_message_for_status(status))
  };
  return rtnval;
}
var PycClientsList = class extends HTMLElement {
  _pager;
  _state;
  _clients;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _root;
  _table_region;
  _projects_notice_region;
  _stamp_region;
  _toast_region;
  _poll_timer;
  _on_visibility_change;
  constructor() {
    super();
    this._state = {
      projectFilter: query_value("project_id"),
      statusFilter: query_choice("status", CLIENT_STATUSES),
      livenessFilter: query_choice("liveness", LIVENESS_STATES),
      page: page_from_query(),
      perPage: DEFAULT_PER_PAGE2,
      total: 0,
      loading: false,
      errored: false,
      errorStatus: 0
    };
    this._clients = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._root = null;
    this._table_region = null;
    this._projects_notice_region = null;
    this._stamp_region = null;
    this._toast_region = null;
    this._pager = null;
    this._poll_timer = null;
    this._on_visibility_change = () => {
      this._handle_visibility_change();
    };
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
      errored: this._state.errored,
      errorStatus: this._state.errorStatus,
      polling: this._poll_timer !== null
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome, load the projects
   * picker (which kicks off the first clients fetch), and start
   * the liveness poll loop.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_projects();
    this._start_poll();
    if (typeof document !== "undefined") {
      document.addEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  /**
   * Lifecycle hook -- stop the poll timer and drop the visibility
   * listener so a navigation away never leaks either.
   */
  disconnectedCallback() {
    this._stop_poll();
    if (typeof document !== "undefined") {
      document.removeEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  _start_poll() {
    if (this._poll_timer !== null) {
      return;
    }
    this._schedule_poll();
    return;
  }
  _schedule_poll() {
    const timer = setTimeout(() => {
      this._poll_timer = null;
      void this._poll_once();
    }, CLIENTS_POLL_INTERVAL_MS);
    const handle = timer;
    if (typeof handle.unref === "function") {
      handle.unref();
    }
    this._poll_timer = timer;
    return;
  }
  /**
   * Run one poll cycle. Exposed so unit tests can drive a cycle
   * without waiting on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    if (typeof document !== "undefined" && document.hidden === true) {
      return;
    }
    await this._refresh();
    this._schedule_poll();
    return;
  }
  _stop_poll() {
    if (this._poll_timer !== null) {
      clearTimeout(this._poll_timer);
      this._poll_timer = null;
    }
    return;
  }
  _handle_visibility_change() {
    if (typeof document === "undefined") {
      return;
    }
    if (document.hidden === true) {
      this._stop_poll();
      return;
    }
    if (this._poll_timer === null) {
      void this._refresh();
      this._schedule_poll();
    }
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
    subtitle.textContent = "Enrolled client runtimes. Each client backs the pod it registers under.";
    root.appendChild(subtitle);
    const filters = document.createElement("div");
    filters.classList.add("pyc-clients-list__filters");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-clients-list__filter");
    project_label.textContent = "Project";
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-clients-list__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.hidden = true;
    project_select.addEventListener("change", () => {
      this._state.projectFilter = project_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-clients-list__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-filter");
    project_input.hidden = true;
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
      option.textContent = state_label(status);
      status_select.appendChild(option);
    }
    status_select.value = this._state.statusFilter;
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
      option.textContent = LIVENESS_LABELS[liveness] || state_label(liveness);
      liveness_select.appendChild(option);
    }
    liveness_select.value = this._state.livenessFilter;
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
    const stamp = document.createElement("span");
    stamp.classList.add("pyc-clients-list__stamp");
    stamp.setAttribute("data-role", "last-updated");
    filters.appendChild(stamp);
    this._stamp_region = stamp;
    root.appendChild(filters);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-clients-list__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-clients-list__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
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
      mirror_to_query({ page: this._state.page > 1 ? String(this._state.page) : "" });
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
    await this._refresh();
    return;
  }
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
      region.classList.remove("pyc-clients-list__projects-notice--error");
      region.textContent = "No projects exist yet \u2014 showing clients across all projects.";
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-clients-list__projects-notice--error");
      region.textContent = "You don't have permission to list projects \u2014 enter a project id directly to filter.";
      return;
    }
    region.classList.add("pyc-clients-list__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-clients-list__button");
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
   * Render the project picker (with an "All projects" option --
   * the clients collection is not project-scoped) or, when no
   * projects collection is available, swap to the manual text
   * input.
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
      const any_project = document.createElement("mj-option");
      any_project.setAttribute("value", "");
      any_project.textContent = "All projects";
      select_el.appendChild(any_project);
      for (const project of this._projects) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", project.project_id);
        option.textContent = project.display_name;
        select_el.appendChild(option);
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
   * Fetch the clients array from the REST endpoint and re-render
   * the table region. Exposed so unit tests can await a fetch
   * cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    mirror_to_query({
      project_id: this._state.projectFilter,
      status: this._state.statusFilter,
      liveness: this._state.livenessFilter,
      page: this._state.page > 1 ? String(this._state.page) : ""
    });
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._render_table_region();
    const url = build_clients_query_url(this._state);
    let clients = null;
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
        clients = body;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.list_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (status === 401) {
      announce_session_expired();
    }
    if (clients === null || Array.isArray(clients) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = status;
      this._render_table_region();
      return;
    }
    this._clients = clients;
    this._state.total = clients.length;
    const max_page = Math.max(
      1,
      Math.ceil(clients.length / this._state.perPage)
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
    this._stamp_region.textContent = "as of " + format_clock_time(/* @__PURE__ */ new Date());
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
      const message = document.createElement("span");
      message.textContent = clients_load_message_for_status(
        this._state.errorStatus
      );
      error.appendChild(message);
      const retry = document.createElement("mj-button");
      retry.classList.add("pyc-clients-list__button");
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
    if (this._clients.length === 0) {
      const empty = build_empty_state({ class_name: "pyc-clients-list__status", message: "No enrolled clients yet.", next_step: "Mint an enrollment token, then enroll the pod client on the machine with it.", link: { href: "/admin/enrollment-tokens", label: "Mint an enrollment token" } });
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
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-clients-list__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-clients-list__row";
    table.rowAttrs = (client) => ({ "data-client-id": client.client_id });
    table.columns = [
      {
        key: "client_id",
        label: "Client",
        width: "12rem",
        render: (client) => {
          const link = document.createElement("a");
          link.classList.add("pyc-clients-list__client-link");
          link.setAttribute("href", "/clients/" + client.client_id);
          link.textContent = short_id2(client.client_id);
          link.title = client.client_id;
          return link;
        }
      },
      {
        key: "pod_name",
        label: "Pod",
        width: "12rem",
        render: (client) => client.pod_name !== null && client.pod_name.length > 0 ? client.pod_name : "\u2014"
      },
      {
        key: "status",
        label: "Status",
        width: "8rem",
        render: (client) => {
          const status_badge = document.createElement("mj-chip");
          status_badge.classList.add("pyc-clients-list__badge");
          status_badge.setAttribute("data-tone", status_tone(client.status));
          status_badge.textContent = state_label(client.status);
          return status_badge;
        }
      },
      {
        key: "liveness_state",
        label: "Liveness",
        width: "9rem",
        render: (client) => {
          const liveness_badge = document.createElement("mj-chip");
          liveness_badge.classList.add("pyc-clients-list__badge");
          const liveness = client_liveness_display(client);
          liveness_badge.setAttribute("data-tone", liveness.tone);
          liveness_badge.textContent = liveness.label;
          return liveness_badge;
        }
      },
      {
        key: "last_seen",
        label: "Last heartbeat",
        width: "14rem",
        render: (client) => format_timestamp2(client.last_seen)
      },
      {
        key: "last_agent_version",
        label: "Runtime version",
        width: "10rem",
        render: (client) => client.last_agent_version !== null && client.last_agent_version !== void 0 && client.last_agent_version.length > 0 ? client.last_agent_version : "\u2014"
      },
      {
        key: "capabilities",
        label: "Capabilities",
        width: "16rem",
        sortable: false,
        render: (client) => {
          const tags = capability_tags(client.attributes);
          if (tags.length === 0) {
            const rtnval2 = document.createTextNode("\u2014");
            return rtnval2;
          }
          const fragment = document.createElement("span");
          fragment.classList.add("pyc-clients-list__tags");
          const visible = tags.slice(0, CAPABILITY_TAG_DISPLAY_LIMIT);
          for (const tag of visible) {
            const chip = document.createElement("mj-chip");
            chip.classList.add("pyc-clients-list__tag");
            chip.textContent = tag;
            fragment.appendChild(chip);
          }
          if (tags.length > CAPABILITY_TAG_DISPLAY_LIMIT) {
            const hidden = tags.slice(CAPABILITY_TAG_DISPLAY_LIMIT);
            const more = document.createElement("mj-chip");
            more.classList.add(
              "pyc-clients-list__tag",
              "pyc-clients-list__tag--overflow"
            );
            more.textContent = "+" + String(hidden.length) + " more";
            more.title = hidden.join(", ");
            fragment.appendChild(more);
          }
          return fragment;
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "8rem",
        sortable: false,
        render: (client) => {
          const revoke_button = document.createElement("mj-button");
          revoke_button.classList.add(
            "pyc-clients-list__button",
            "pyc-clients-list__row-action"
          );
          revoke_button.setAttribute("type", "button");
          revoke_button.setAttribute("data-role", "revoke-action");
          revoke_button.textContent = "Revoke";
          hide_unless_may(revoke_button, "system:clients.write");
          if (client.status === "REVOKED") {
            revoke_button.toggleAttribute("disabled", true);
            revoke_button.title = "This client is already revoked.";
          } else {
            revoke_button.addEventListener("click", () => {
              revoke_button.toggleAttribute("disabled", true);
              void self._on_revoke_client(client, revoke_button);
            });
          }
          return revoke_button;
        }
      }
    ];
    table.rows = this._page_slice();
    return table;
  }
  async _on_revoke_client(client, button) {
    const confirmed = await confirm_action(this, "Revoke client " + short_id2(client.client_id) + "? The client's certificate is revoked and the pod it backs stops receiving work. This cannot be undone from this UI.", "Revoke client");
    if (confirmed !== true) {
      button.toggleAttribute("disabled", false);
      return;
    }
    const outcome = await perform_client_revoke(client.client_id);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * Show a toast in the toast region through the shared service: one at a
   * time, announced to assistive technology, a plain success goes away by itself.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-clients-list" });
    return;
  }
  _render_pager() {
    if (this._pager === null || this._pager === void 0) {
      return;
    }
    this._pager.setAttribute("page", String(this._state.page));
    this._pager.setAttribute("page-size", String(this._state.perPage));
    this._pager.setAttribute("total-items", String(this._state.total));
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-pods-bundle/client-detail-view.js
var CLIENT_POLL_INTERVAL_MS = 15e3;
var UUID_PATTERN2 = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function client_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/clients/";
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
function is_valid_client_id(client_id) {
  if (typeof client_id !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN2.test(client_id);
  return rtnval;
}
function client_detail_message_for_status(status) {
  if (status === 404) {
    const rtnval2 = "No client with this id.";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to clients.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load this client (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
var PycClientDetail = class extends HTMLElement {
  _client_id;
  _client;
  _capabilities;
  _client_status;
  _pod_link;
  _project_names;
  _loading;
  _errored;
  _root;
  _toast_region;
  _stamp_region;
  _poll_timer;
  _on_visibility_change;
  constructor() {
    super();
    this._client_id = "";
    this._client = null;
    this._capabilities = [];
    this._client_status = 0;
    this._pod_link = null;
    this._project_names = null;
    this._loading = false;
    this._errored = false;
    this._root = null;
    this._toast_region = null;
    this._stamp_region = null;
    this._poll_timer = null;
    this._on_visibility_change = () => {
      this._handle_visibility_change();
    };
  }
  /**
   * Observed attributes -- ``client-id`` may be supplied
   * explicitly by a host; otherwise it is read from the path on
   * mount.
   */
  static get observedAttributes() {
    const rtnval = ["client-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      clientId: this._client_id,
      loading: this._loading,
      errored: this._errored,
      errorStatus: this._client_status,
      polling: this._poll_timer !== null
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the client id, render the chrome,
   * fetch the snapshot, and start the liveness poll loop.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("client-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._client_id = attr_id;
    } else {
      this._client_id = client_id_from_path(window.location.pathname);
    }
    this._render_chrome();
    void this._load(false);
    this._start_poll();
    if (typeof document !== "undefined") {
      document.addEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  /**
   * Lifecycle hook -- stop the poll timer and drop the visibility
   * listener so a navigation away never leaks either.
   */
  disconnectedCallback() {
    this._stop_poll();
    if (typeof document !== "undefined") {
      document.removeEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  _start_poll() {
    if (this._poll_timer !== null) {
      return;
    }
    if (is_valid_client_id(this._client_id) === false) {
      return;
    }
    this._schedule_poll();
    return;
  }
  _schedule_poll() {
    const timer = setTimeout(() => {
      this._poll_timer = null;
      void this._poll_once();
    }, CLIENT_POLL_INTERVAL_MS);
    const handle = timer;
    if (typeof handle.unref === "function") {
      handle.unref();
    }
    this._poll_timer = timer;
    return;
  }
  /**
   * Run one poll cycle. Exposed so unit tests can drive a cycle
   * without waiting on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    if (typeof document !== "undefined" && document.hidden === true) {
      return;
    }
    await this._load(true);
    this._schedule_poll();
    return;
  }
  _stop_poll() {
    if (this._poll_timer !== null) {
      clearTimeout(this._poll_timer);
      this._poll_timer = null;
    }
    return;
  }
  _handle_visibility_change() {
    if (typeof document === "undefined") {
      return;
    }
    if (document.hidden === true) {
      this._stop_poll();
      return;
    }
    if (this._poll_timer === null && is_valid_client_id(this._client_id) === true) {
      void this._load(true);
      this._schedule_poll();
    }
    return;
  }
  /**
   * Fetch the client snapshot. Exposed so unit tests can await a
   * load cycle.
   */
  async load() {
    await this._load(false);
    return;
  }
  /**
   * Load / reload the client snapshot.
   *
   * @param silent When true (poll cycles), skip the intermediate
   *               loading state so the page does not flicker
   *               every poll interval.
   */
  async _load(silent) {
    if (is_valid_client_id(this._client_id) === false) {
      this._loading = false;
      this._errored = true;
      this._client_status = 404;
      this._render_body();
      return;
    }
    if (silent !== true) {
      this._loading = true;
      this._errored = false;
      this._render_body();
    }
    const envelope = await this._fetch_client();
    this._client_status = envelope.status;
    if (envelope.ok === false || envelope.body === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._client = envelope.body;
    this._update_back_link();
    this._capabilities = await this._fetch_capabilities();
    if (this._project_names === null) {
      const projects_outcome = await load_projects();
      if (projects_outcome.ok === true) {
        this._project_names = project_display_map(
          projects_outcome.projects
        );
      } else {
        this._project_names = {};
      }
    }
    await this._resolve_pod_link();
    this._loading = false;
    this._errored = false;
    this._render_stamp();
    this._render_body();
    return;
  }
  /**
   * Point "Back to clients" at the client's own project once it is known, so a page opened without
   * coming from the list (a bookmark, a message) still returns to that project's clients.
   */
  _update_back_link() {
    if (this._root === null || this._client === null || typeof this._client.project_id !== "string" || this._client.project_id.length === 0) {
      return;
    }
    const back = this._root.querySelector('[data-role="back-link"]');
    if (back !== null) {
      back.setAttribute("href", "/clients?project_id=" + encodeURIComponent(this._client.project_id));
    }
    return;
  }
  async _fetch_client() {
    const url = build_client_detail_url(this._client_id);
    let status = 0;
    let ok = false;
    let body = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      ok = response.ok;
      if (ok === true) {
        body = await response.json();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.detail_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (status === 401) {
      announce_session_expired();
    }
    const rtnval = { ok, status, body };
    return rtnval;
  }
  /**
   * Fetch the capabilities the pod advertised
   * (``GET /api/v1/clients/{id}/capabilities``). They live apart from
   * the operator-set attributes on the client record. A failed fetch
   * yields an empty list rather than blocking the client view.
   */
  async _fetch_capabilities() {
    let rtnval = [];
    try {
      const response = await fetch(
        build_client_capabilities_url(this._client_id),
        {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        }
      );
      if (response.ok === true) {
        const body = await response.json();
        if (Array.isArray(body) === true) {
          rtnval = body;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.capabilities_fetch_failed",
        { reason: String(reason) }
      );
    }
    return rtnval;
  }
  /**
   * Resolve the enrolled pod's detail-page link. The client
   * record carries the pod *name*, but the pod detail route needs
   * the pod definition's UUID -- look it up in the project's
   * pod-definitions collection. A failed lookup leaves the pod
   * rendered as plain text rather than a dead link.
   */
  async _resolve_pod_link() {
    this._pod_link = null;
    if (this._client === null) {
      return;
    }
    const pod_name = this._client.pod_name;
    const project_id = this._client.project_id;
    if (typeof pod_name !== "string" || pod_name.length === 0) {
      return;
    }
    if (typeof project_id !== "string" || project_id.length === 0) {
      return;
    }
    let definitions = null;
    try {
      const response = await fetch(build_pod_definitions_url(project_id), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        definitions = await response.json();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.pod_link_resolution_failed",
        { reason: String(reason) }
      );
    }
    if (definitions === null || Array.isArray(definitions) === false) {
      return;
    }
    for (const definition of definitions) {
      if (definition === null || typeof definition !== "object") {
        continue;
      }
      if (definition.pod_name === pod_name && typeof definition.pod_id === "string" && definition.pod_id.length > 0) {
        this._pod_link = "/pods/" + definition.pod_id + "?project_id=" + encodeURIComponent(project_id);
        return;
      }
    }
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-client-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Client detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-client-detail__heading");
    heading.textContent = "Client detail";
    root.appendChild(heading);
    const toolbar = document.createElement("div");
    toolbar.classList.add("pyc-client-detail__toolbar");
    const back = document.createElement("a");
    back.classList.add("pyc-client-detail__back-link");
    back.setAttribute("href", "/clients");
    back.setAttribute("data-role", "back-link");
    keep_list_state_on_back(back, "/clients");
    back.textContent = "Back to clients";
    toolbar.appendChild(back);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-client-detail__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._load(false);
    });
    toolbar.appendChild(refresh_button);
    const stamp = document.createElement("span");
    stamp.classList.add("pyc-client-detail__stamp");
    stamp.setAttribute("data-role", "last-updated");
    toolbar.appendChild(stamp);
    this._stamp_region = stamp;
    root.appendChild(toolbar);
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-client-detail__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const body = document.createElement("div");
    body.classList.add("pyc-client-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  _render_stamp() {
    if (this._stamp_region === null) {
      return;
    }
    this._stamp_region.textContent = "as of " + format_clock_time(/* @__PURE__ */ new Date());
    return;
  }
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
      loading.classList.add("pyc-client-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading client\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._client === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-client-detail__status",
        "pyc-client-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      const message = document.createElement("span");
      message.textContent = client_detail_message_for_status(
        this._client_status
      );
      error.appendChild(message);
      const retriable = is_valid_client_id(this._client_id) === true && this._client_status !== 404;
      if (retriable === true) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-client-detail__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "error-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._load(false);
        });
        error.appendChild(retry);
      }
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._client));
    fragment.appendChild(this._build_heartbeat(this._client));
    fragment.appendChild(this._build_capabilities(this._client));
    body.replaceChildren(fragment);
    return;
  }
  /**
   * Resolve a project's display name from the cached projects
   * map, falling back to the raw id.
   */
  _project_display_name(project_id) {
    if (this._project_names !== null) {
      const display = this._project_names[project_id];
      if (typeof display === "string" && display.length > 0) {
        const rtnval2 = display;
        return rtnval2;
      }
    }
    const rtnval = project_id;
    return rtnval;
  }
  _build_summary(client) {
    const section = document.createElement("section");
    section.classList.add("pyc-client-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Client summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-client-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-client-detail__client-id");
    id_value.setAttribute("data-role", "client-id");
    id_value.textContent = short_id2(client.client_id);
    set_entity_title("Client " + short_id2(client.client_id));
    id_value.title = client.client_id;
    id_row.appendChild(id_value);
    const status_badge = document.createElement("mj-chip");
    status_badge.classList.add("pyc-client-detail__badge");
    status_badge.setAttribute("data-role", "status-badge");
    status_badge.setAttribute("data-tone", status_tone(client.status));
    status_badge.textContent = state_label(client.status);
    id_row.appendChild(status_badge);
    const liveness_badge = document.createElement("mj-chip");
    liveness_badge.classList.add("pyc-client-detail__badge");
    liveness_badge.setAttribute("data-role", "liveness-badge");
    const liveness = client_liveness_display(client);
    liveness_badge.setAttribute("data-tone", liveness.tone);
    liveness_badge.textContent = liveness.label;
    id_row.appendChild(liveness_badge);
    id_row.appendChild(this._build_actions(client));
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-client-detail__grid");
    this._append_field(grid, "Client id", client.client_id);
    this._append_field(
      grid,
      "Project",
      this._project_display_name(client.project_id),
      client.project_id
    );
    this._append_pod_field(grid, client);
    this._append_field(
      grid,
      "Enrolled",
      format_timestamp2(client.enrolled_at)
    );
    this._append_field(grid, "Transport", client.transport_name);
    this._append_field(
      grid,
      "Runtime version",
      client.last_agent_version
    );
    section.appendChild(grid);
    return section;
  }
  /**
   * Build the operator action buttons for the client -- a single
   * Revoke action, disabled once the client is already revoked.
   */
  _build_actions(client) {
    const actions = document.createElement("span");
    actions.classList.add("pyc-client-detail__actions");
    actions.setAttribute("data-role", "client-actions");
    const revoke_button = document.createElement("mj-button");
    revoke_button.classList.add("pyc-client-detail__button");
    revoke_button.setAttribute("type", "button");
    revoke_button.setAttribute("data-role", "revoke-action");
    revoke_button.textContent = "Revoke";
    hide_unless_may(revoke_button, "system:clients.write");
    if (client.status === "REVOKED") {
      revoke_button.toggleAttribute("disabled", true);
      revoke_button.title = "This client is already revoked.";
    } else {
      revoke_button.addEventListener("click", () => {
        revoke_button.toggleAttribute("disabled", true);
        void this._on_revoke(revoke_button);
      });
    }
    actions.appendChild(revoke_button);
    return actions;
  }
  async _on_revoke(button) {
    const confirmed = await confirm_action(this, "Revoke client " + short_id2(this._client_id) + "? The client's certificate is revoked and the pod it backs stops receiving work. This cannot be undone from this UI.", "Revoke client");
    if (confirmed !== true) {
      button.toggleAttribute("disabled", false);
      return;
    }
    const outcome = await perform_client_revoke(this._client_id);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._load(true);
    }
    return;
  }
  /**
   * Append the single "Enrolled pod" field. The data model is one
   * pod per client (``pod_name`` is a scalar); the field links to
   * the pod's detail page when the pod id could be resolved.
   */
  _append_pod_field(grid, client) {
    const field = document.createElement("div");
    field.classList.add("pyc-client-detail__field");
    const term = document.createElement("dt");
    term.textContent = "Enrolled pod";
    const def = document.createElement("dd");
    const pod_name = client.pod_name;
    if (typeof pod_name === "string" && pod_name.length > 0) {
      if (this._pod_link !== null) {
        const link = document.createElement("a");
        link.classList.add("pyc-client-detail__pod-link");
        link.setAttribute("href", this._pod_link);
        link.setAttribute("data-role", "enrolled-pod-link");
        link.textContent = pod_name;
        def.appendChild(link);
      } else {
        def.textContent = pod_name;
      }
    } else {
      def.textContent = "\u2014";
      def.title = "This client is not enrolled under a pod.";
    }
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  _build_heartbeat(client) {
    const section = document.createElement("section");
    section.classList.add("pyc-client-detail__heartbeat");
    section.setAttribute("data-role", "heartbeat-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Heartbeat");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-client-detail__section-heading");
    heading.textContent = "Heartbeat";
    section.appendChild(heading);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-client-detail__grid");
    this._append_field(
      grid,
      "Last heartbeat",
      format_timestamp2(client.last_seen)
    );
    this._append_field(
      grid,
      "Degraded since",
      format_timestamp2(client.degraded_at)
    );
    section.appendChild(grid);
    const note = document.createElement("p");
    note.classList.add("pyc-client-detail__note");
    note.textContent = "Full heartbeat history is not exposed by the operator REST surface \u2014 showing the latest cadence markers only.";
    section.appendChild(note);
    return section;
  }
  /**
   * Build the "Capabilities & attributes" section: the capabilities
   * the pod advertised -- shown as the tags dispatch matches a job
   * type's required capabilities against -- and the attributes
   * operators set on the client.
   */
  _build_capabilities(client) {
    const section = document.createElement("section");
    section.classList.add("pyc-client-detail__capabilities");
    section.setAttribute("data-role", "capabilities-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Capabilities");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-client-detail__section-heading");
    heading.textContent = "Capabilities & attributes";
    section.appendChild(heading);
    const advertised = advertised_capability_tags(this._capabilities);
    const attributes = capability_tags(client.attributes);
    if (advertised.length === 0 && attributes.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-client-detail__status");
      empty.setAttribute("data-role", "capabilities-empty");
      empty.textContent = "No capabilities reported for this client.";
      section.appendChild(empty);
      return section;
    }
    if (advertised.length > 0) {
      let caption = "Advertised by the pod";
      const updated_at = latest_capability_update(this._capabilities);
      if (updated_at.length > 0) {
        caption = caption + " (last update " + format_timestamp2(updated_at) + ")";
      }
      section.appendChild(
        this._build_tag_group("advertised-capabilities", caption, advertised)
      );
    }
    if (attributes.length > 0) {
      section.appendChild(
        this._build_tag_group("attribute-tags", "Attributes set by operators", attributes)
      );
    }
    return section;
  }
  _build_tag_group(role, caption, tags) {
    const group = document.createElement("div");
    group.setAttribute("data-role", role);
    const label = document.createElement("p");
    label.classList.add("pyc-client-detail__note");
    label.textContent = caption;
    group.appendChild(label);
    const tag_list = document.createElement("div");
    tag_list.classList.add("pyc-client-detail__tag-list");
    for (const tag of tags) {
      const chip = document.createElement("mj-chip");
      chip.classList.add("pyc-client-detail__tag");
      chip.textContent = tag;
      tag_list.appendChild(chip);
    }
    group.appendChild(tag_list);
    return group;
  }
  _append_field(grid, label, value, title) {
    const field = document.createElement("div");
    field.classList.add("pyc-client-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    if (typeof value === "string" && value.length > 0) {
      def.textContent = value;
    } else {
      def.textContent = "\u2014";
    }
    if (typeof title === "string" && title.length > 0) {
      def.title = title;
    }
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  /**
   * Show a toast in the toast region through the shared service: one at a
   * time, announced to assistive technology, a plain success goes away by itself.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-client-detail" });
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-pods-bundle/index.entry.js
var PODS_ROUTE = "/pods";
var CLIENTS_ROUTE = "/clients";
var PODS_LIST_TAG = "pyc-pods-list";
var POD_DETAIL_TAG = "pyc-pod-detail";
var CLIENTS_LIST_TAG = "pyc-clients-list";
var CLIENT_DETAIL_TAG = "pyc-client-detail";
var PODS_STYLESHEET_HREF = "/static/javascript/pyc-pods-bundle/pyc-pods-bundle.css";
function ensure_pods_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-pods-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = PODS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-pods-bundle");
  document.head.appendChild(link);
  return;
}
function define_pods_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(PODS_LIST_TAG) === void 0) {
    customElements.define(PODS_LIST_TAG, PycPodsList);
  }
  if (customElements.get(POD_DETAIL_TAG) === void 0) {
    customElements.define(POD_DETAIL_TAG, PycPodDetail);
  }
  if (customElements.get(CLIENTS_LIST_TAG) === void 0) {
    customElements.define(CLIENTS_LIST_TAG, PycClientsList);
  }
  if (customElements.get(CLIENT_DETAIL_TAG) === void 0) {
    customElements.define(CLIENT_DETAIL_TAG, PycClientDetail);
  }
  return;
}
function classify_pods_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === PODS_ROUTE || working === PODS_ROUTE + "/") {
    const rtnval2 = "pods-list";
    return rtnval2;
  }
  if (working === CLIENTS_ROUTE || working === CLIENTS_ROUTE + "/") {
    const rtnval2 = "clients-list";
    return rtnval2;
  }
  const pod_id = pod_id_from_path(working);
  if (pod_id.length > 0) {
    const rtnval2 = "pod-detail";
    return rtnval2;
  }
  const client_id = client_id_from_path(working);
  if (client_id.length > 0) {
    const rtnval2 = "client-detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_pods_route(route) {
  if (route === "pods-list") {
    const rtnval2 = PODS_LIST_TAG;
    return rtnval2;
  }
  if (route === "pod-detail") {
    const rtnval2 = POD_DETAIL_TAG;
    return rtnval2;
  }
  if (route === "clients-list") {
    const rtnval2 = CLIENTS_LIST_TAG;
    return rtnval2;
  }
  if (route === "client-detail") {
    const rtnval2 = CLIENT_DETAIL_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_pods_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_pods_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_pods_route(route);
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
  define_pods_elements();
  ensure_pods_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _boot() {
  define_pods_elements();
  const target = window;
  const handle = target.pychestrateShell;
  if (handle !== void 0 && handle.sidebar !== void 0) {
    mount_pods_view_if_active();
    return;
  }
  let registered = false;
  const try_register = () => {
    if (registered === true) {
      return true;
    }
    const current = target.pychestrateShell;
    if (current !== void 0 && current.sidebar !== void 0) {
      registered = true;
      mount_pods_view_if_active();
      return true;
    }
    return false;
  };
  queueMicrotask(() => {
    try_register();
  });
  if (typeof window.addEventListener === "function") {
    const on_shell_ready = () => {
      if (try_register() === true) {
        window.removeEventListener(
          "pyc-site-shell-ready",
          on_shell_ready
        );
      }
    };
    window.addEventListener("pyc-site-shell-ready", on_shell_ready);
  }
  return;
}
if (typeof window !== "undefined") {
  _boot();
}
export {
  CLIENT_STATUSES,
  LIVENESS_STATES,
  POD_STATES,
  PycClientDetail,
  PycClientsList,
  PycPodDetail,
  PycPodsList,
  TERMINAL_POD_STATES,
  TRANSIENT_POD_STATES,
  advertised_capability_tags,
  announce_session_expired,
  build_client_capabilities_url,
  build_client_detail_url,
  build_client_revoke_url,
  build_clients_query_url,
  build_pod_definition_url,
  build_pod_definitions_url,
  build_pod_registration_url,
  build_pod_registrations_url,
  build_pod_state_history_url,
  build_pod_state_url,
  build_pod_transitions_url,
  capability_tags,
  classify_pods_route,
  client_detail_message_for_status,
  format_timestamp2 as client_format_timestamp,
  client_id_from_path,
  short_id2 as client_short_id,
  has_next_page2 as clients_has_next_page,
  has_previous_page2 as clients_has_previous_page,
  clients_load_message_for_status,
  define_pods_elements,
  detail_load_message_for_status,
  ensure_pods_stylesheet,
  extract_projects,
  format_clock_time,
  is_terminal_pod_state,
  is_transient_pod_state,
  is_valid_client_id,
  is_valid_pod_id,
  latest_capability_update,
  liveness_tone,
  load_projects,
  member_count,
  mount_pods_view_if_active,
  perform_client_revoke,
  format_timestamp as pod_format_timestamp,
  pod_id_from_path,
  short_id as pod_short_id,
  pod_state_tone,
  has_next_page as pods_has_next_page,
  has_previous_page as pods_has_previous_page,
  pods_load_message_for_status,
  project_display_map,
  project_id_from_search,
  revoke_message_for_status,
  runtime_section_message_for_status,
  status_tone,
  tag_for_pods_route,
  transition_message_for_status
};
