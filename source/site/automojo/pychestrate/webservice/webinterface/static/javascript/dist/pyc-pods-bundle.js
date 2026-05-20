// src/pyc-pods-bundle/pods-list-view.ts
var DEFAULT_PER_PAGE = 25;
var PROJECTS_API_PATH = "/api/v1/projects";
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
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = parsed.toLocaleString();
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
var PycPodsList = class extends HTMLElement {
  _state;
  _pods;
  _root;
  _table_region;
  constructor() {
    super();
    this._state = {
      projectFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false,
      needsProject: true
    };
    this._pods = [];
    this._root = null;
    this._table_region = null;
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
      needsProject: this._state.needsProject
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome. The pods list
   * cannot fetch without a project id, so a project filter
   * supplied via ``?project_id=`` seeds an immediate fetch;
   * otherwise the view shows a "pick a project" prompt.
   */
  connectedCallback() {
    const seeded = this._project_from_search();
    if (seeded.length > 0) {
      this._state.projectFilter = seeded;
    }
    this._render_chrome();
    if (this._state.projectFilter.length > 0) {
      void this._refresh();
    } else {
      this._render_table_region();
    }
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
    subtitle.textContent = "Pod definitions are project-scoped. Enter a project id to list its pods.";
    root.appendChild(subtitle);
    const filters = document.createElement("div");
    filters.classList.add("pyc-pods-list__filters");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-pods-list__filter");
    project_label.textContent = "Project";
    const project_input = document.createElement("input");
    project_input.classList.add("pyc-pods-list__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-filter");
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
    const refresh_button = document.createElement("button");
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
    root.appendChild(filters);
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-pods-list__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("div");
    pager.classList.add("pyc-pods-list__pager");
    const prev_button = document.createElement("button");
    prev_button.classList.add("pyc-pods-list__button");
    prev_button.setAttribute("type", "button");
    prev_button.setAttribute("data-role", "prev-page");
    prev_button.textContent = "Previous";
    prev_button.addEventListener("click", () => {
      if (has_previous_page(this._state) === true) {
        this._state.page = this._state.page - 1;
        this._render_table_region();
      }
    });
    pager.appendChild(prev_button);
    const page_indicator = document.createElement("span");
    page_indicator.classList.add("pyc-pods-list__page-indicator");
    page_indicator.setAttribute("data-role", "page-indicator");
    pager.appendChild(page_indicator);
    const next_button = document.createElement("button");
    next_button.classList.add("pyc-pods-list__button");
    next_button.setAttribute("type", "button");
    next_button.setAttribute("data-role", "next-page");
    next_button.textContent = "Next";
    next_button.addEventListener("click", () => {
      if (has_next_page(this._state) === true) {
        this._state.page = this._state.page + 1;
        this._render_table_region();
      }
    });
    pager.appendChild(next_button);
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
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
    this._render_table_region();
    const url = build_pod_definitions_url(this._state.projectFilter);
    let pods = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "pods fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      pods = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pods.list_fetch_failed",
        { reason: String(reason) }
      );
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    if (pods === null || Array.isArray(pods) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    this._pods = pods;
    this._state.total = pods.length;
    this._state.page = 1;
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
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
      prompt.textContent = "Enter a project id above to list its pods.";
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
      error.textContent = "Failed to load pods. Try refreshing.";
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
    const table = document.createElement("table");
    table.classList.add("pyc-pods-list__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = [
      "Pod",
      "Name",
      "Version",
      "Members",
      "Created"
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
    for (const pod of this._page_slice()) {
      const row = document.createElement("tr");
      row.classList.add("pyc-pods-list__row");
      const id_cell = document.createElement("td");
      const link = document.createElement("a");
      link.classList.add("pyc-pods-list__pod-link");
      const href = "/pods/" + pod.pod_id + "?project_id=" + encodeURIComponent(pod.project_id);
      link.setAttribute("href", href);
      link.textContent = short_id(pod.pod_id);
      link.title = pod.pod_id;
      id_cell.appendChild(link);
      row.appendChild(id_cell);
      const name_cell = document.createElement("td");
      name_cell.textContent = pod.pod_name !== null && pod.pod_name.length > 0 ? pod.pod_name : "\u2014";
      row.appendChild(name_cell);
      const version_cell = document.createElement("td");
      version_cell.textContent = "v" + String(pod.current_version);
      row.appendChild(version_cell);
      const members_cell = document.createElement("td");
      members_cell.textContent = String(member_count(pod.spec));
      row.appendChild(members_cell);
      const created_cell = document.createElement("td");
      created_cell.textContent = format_timestamp(pod.created_at);
      row.appendChild(created_cell);
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    return table;
  }
  _render_pager() {
    if (this._root === null) {
      return;
    }
    const prev = this._root.querySelector('[data-role="prev-page"]');
    const next = this._root.querySelector('[data-role="next-page"]');
    const indicator = this._root.querySelector('[data-role="page-indicator"]');
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
};

// src/pyc-pods-bundle/pod-detail-view.ts
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
var POLL_INTERVAL_MS = 5e3;
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
function build_pod_registration_url(project_id, pod_id) {
  const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) + "/pods/" + encodeURIComponent(pod_id) + "/registration";
  return rtnval;
}
function build_pod_registrations_url(project_id, pod_id) {
  const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) + "/pods/" + encodeURIComponent(pod_id) + "/registrations";
  return rtnval;
}
var PycPodDetail = class extends HTMLElement {
  _pod_id;
  _project_id;
  _definition;
  _state_row;
  _registration;
  _registration_history;
  _state_history;
  _loading;
  _errored;
  _transient;
  _poll_status;
  _poll_timer;
  _root;
  constructor() {
    super();
    this._pod_id = "";
    this._project_id = "";
    this._definition = null;
    this._state_row = null;
    this._registration = null;
    this._registration_history = [];
    this._state_history = [];
    this._loading = false;
    this._errored = false;
    this._transient = false;
    this._poll_status = "idle";
    this._poll_timer = null;
    this._root = null;
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
      transient: this._transient
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
    return;
  }
  /**
   * Lifecycle hook -- stop the live-poll timer so a navigation
   * away never leaks a timer.
   */
  disconnectedCallback() {
    this._stop_poll();
    return;
  }
  /**
   * Fetch the pod snapshot then -- when the pod is in a transient
   * state -- start the live-poll loop. Exposed so unit tests can
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
      this._render_body();
      return;
    }
    if (this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const definition = await this._fetch_json(
      build_pod_definition_url(this._project_id, this._pod_id),
      "definition_fetch_failed"
    );
    if (definition === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._definition = definition;
    await this._refresh_runtime();
    this._loading = false;
    this._errored = false;
    this._render_body();
    if (this._transient === true) {
      this._start_poll();
    } else {
      this._poll_status = "stopped";
      this._render_poll_banner();
    }
    return;
  }
  /**
   * Re-fetch the live state, registration and history rows.
   * Shared by the initial load and each poll cycle.
   */
  async _refresh_runtime() {
    const state_row = await this._fetch_json(
      build_pod_state_url(this._project_id, this._pod_id),
      "state_fetch_failed"
    );
    if (state_row !== null) {
      this._state_row = state_row;
      this._transient = is_transient_pod_state(state_row.state);
    }
    const registration = await this._fetch_json(
      build_pod_registration_url(this._project_id, this._pod_id),
      "registration_fetch_failed"
    );
    this._registration = registration;
    const history = await this._fetch_json(
      build_pod_registrations_url(this._project_id, this._pod_id),
      "registrations_fetch_failed"
    );
    if (history !== null && Array.isArray(history) === true) {
      this._registration_history = history;
    }
    const state_history = await this._fetch_json(
      build_pod_state_history_url(this._project_id, this._pod_id),
      "state_history_fetch_failed"
    );
    if (state_history !== null && Array.isArray(state_history) === true) {
      this._state_history = state_history;
    }
    return;
  }
  /**
   * Fetch a JSON document. A non-OK response or a thrown error
   * yields ``null`` -- callers decide whether a missing document
   * is an error or an empty state.
   *
   * @param url Relative URL to GET.
   * @param failure_tag A log tag for diagnostic warnings.
   *
   * @returns The parsed JSON body, or ``null`` on failure.
   */
  async _fetch_json(url, failure_tag) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        const rtnval2 = null;
        return rtnval2;
      }
      const body = await response.json();
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pods." + failure_tag,
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
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
   * Run one poll cycle -- re-fetch runtime rows, re-render, and
   * either reschedule (still transient) or stop (now settled).
   * Exposed so unit tests can drive a poll cycle without waiting
   * on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    await this._refresh_runtime();
    this._render_body();
    if (this._transient === false) {
      this._stop_poll();
      this._poll_status = "stopped";
      this._render_poll_banner();
      return;
    }
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
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-pod-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Pod detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-pod-detail__heading");
    heading.textContent = "Pod detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-pod-detail__back-link");
    back.setAttribute("href", "/pods");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to pods";
    root.appendChild(back);
    const banner = document.createElement("p");
    banner.classList.add("pyc-pod-detail__banner");
    banner.setAttribute("data-role", "poll-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;
    root.appendChild(banner);
    const body = document.createElement("div");
    body.classList.add("pyc-pod-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
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
      error.textContent = "Failed to load this pod. A project id query parameter is required \u2014 try refreshing from the pods list.";
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
    id_value.title = definition.pod_id;
    id_row.appendChild(id_value);
    const state_value = this._state_row !== null ? this._state_row.state : "DEFINED";
    const badge = document.createElement("span");
    badge.classList.add("pyc-pod-detail__badge");
    badge.setAttribute("data-role", "state-badge");
    badge.setAttribute("data-tone", pod_state_tone(state_value));
    badge.textContent = state_value;
    id_row.appendChild(badge);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-pod-detail__grid");
    this._append_field(grid, "Pod id", definition.pod_id);
    this._append_field(grid, "Pod name", definition.pod_name);
    this._append_field(grid, "Project", definition.project_id);
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
      const empty = document.createElement("p");
      empty.classList.add("pyc-pod-detail__status");
      empty.setAttribute("data-role", "registration-empty");
      empty.textContent = "No active registration for this pod.";
      section.appendChild(empty);
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
    this._append_field(grid, "Registration state", this._registration.state);
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
      const summary = row.state + " \xB7 v" + String(row.pod_definition_version) + " \xB7 " + format_timestamp(row.registered_at);
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
      const from_label = row.from_state !== null && row.from_state !== void 0 ? row.from_state : "\u2205";
      const summary = from_label + " \u2192 " + row.to_state + " \xB7 " + format_timestamp(row.applied_at);
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
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-pod-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    def.textContent = value;
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
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
      el.textContent = "Pod is mid-transition \u2014 refreshing every 5 seconds.";
      return;
    }
    if (this._poll_status === "stopped" && this._transient === false) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = true;
    el.textContent = "";
    return;
  }
};

// src/pyc-pods-bundle/clients-list-view.ts
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
function has_next_page2(state) {
  const consumed = state.page * state.perPage;
  const rtnval = consumed < state.total;
  return rtnval;
}
function has_previous_page2(state) {
  const rtnval = state.page > 1;
  return rtnval;
}
var PycClientsList = class extends HTMLElement {
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
      perPage: DEFAULT_PER_PAGE2,
      total: 0,
      loading: false,
      errored: false
    };
    this._clients = [];
    this._root = null;
    this._table_region = null;
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
    const project_input = document.createElement("input");
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
    const status_select = document.createElement("select");
    status_select.classList.add("pyc-clients-list__select");
    status_select.setAttribute("data-role", "status-filter");
    const any_status = document.createElement("option");
    any_status.value = "";
    any_status.textContent = "All statuses";
    status_select.appendChild(any_status);
    for (const status of CLIENT_STATUSES) {
      const option = document.createElement("option");
      option.value = status;
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
    const liveness_select = document.createElement("select");
    liveness_select.classList.add("pyc-clients-list__select");
    liveness_select.setAttribute("data-role", "liveness-filter");
    const any_liveness = document.createElement("option");
    any_liveness.value = "";
    any_liveness.textContent = "All liveness";
    liveness_select.appendChild(any_liveness);
    for (const liveness of LIVENESS_STATES) {
      const option = document.createElement("option");
      option.value = liveness;
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
    const refresh_button = document.createElement("button");
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
    const pager = document.createElement("div");
    pager.classList.add("pyc-clients-list__pager");
    const prev_button = document.createElement("button");
    prev_button.classList.add("pyc-clients-list__button");
    prev_button.setAttribute("type", "button");
    prev_button.setAttribute("data-role", "prev-page");
    prev_button.textContent = "Previous";
    prev_button.addEventListener("click", () => {
      if (has_previous_page2(this._state) === true) {
        this._state.page = this._state.page - 1;
        this._render_table_region();
      }
    });
    pager.appendChild(prev_button);
    const page_indicator = document.createElement("span");
    page_indicator.classList.add("pyc-clients-list__page-indicator");
    page_indicator.setAttribute("data-role", "page-indicator");
    pager.appendChild(page_indicator);
    const next_button = document.createElement("button");
    next_button.classList.add("pyc-clients-list__button");
    next_button.setAttribute("type", "button");
    next_button.setAttribute("data-role", "next-page");
    next_button.textContent = "Next";
    next_button.addEventListener("click", () => {
      if (has_next_page2(this._state) === true) {
        this._state.page = this._state.page + 1;
        this._render_table_region();
      }
    });
    pager.appendChild(next_button);
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
    const table = document.createElement("table");
    table.classList.add("pyc-clients-list__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = [
      "Client",
      "Pod",
      "Status",
      "Liveness",
      "Last heartbeat",
      "Agent version",
      "Capabilities"
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
    for (const client of this._page_slice()) {
      const row = document.createElement("tr");
      row.classList.add("pyc-clients-list__row");
      const id_cell = document.createElement("td");
      const link = document.createElement("a");
      link.classList.add("pyc-clients-list__client-link");
      link.setAttribute("href", "/clients/" + client.client_id);
      link.textContent = short_id2(client.client_id);
      link.title = client.client_id;
      id_cell.appendChild(link);
      row.appendChild(id_cell);
      const pod_cell = document.createElement("td");
      pod_cell.textContent = client.pod_name !== null && client.pod_name.length > 0 ? client.pod_name : "\u2014";
      row.appendChild(pod_cell);
      const status_cell = document.createElement("td");
      const status_badge = document.createElement("span");
      status_badge.classList.add("pyc-clients-list__badge");
      status_badge.setAttribute("data-tone", status_tone(client.status));
      status_badge.textContent = client.status;
      status_cell.appendChild(status_badge);
      row.appendChild(status_cell);
      const liveness_cell = document.createElement("td");
      const liveness_badge = document.createElement("span");
      liveness_badge.classList.add("pyc-clients-list__badge");
      liveness_badge.setAttribute(
        "data-tone",
        liveness_tone(client.liveness_state)
      );
      liveness_badge.textContent = client.liveness_state;
      liveness_cell.appendChild(liveness_badge);
      row.appendChild(liveness_cell);
      const seen_cell = document.createElement("td");
      seen_cell.textContent = format_timestamp2(client.last_seen);
      row.appendChild(seen_cell);
      const version_cell = document.createElement("td");
      version_cell.textContent = client.last_agent_version !== null && client.last_agent_version !== void 0 && client.last_agent_version.length > 0 ? client.last_agent_version : "\u2014";
      row.appendChild(version_cell);
      const caps_cell = document.createElement("td");
      const tags = capability_tags(client.attributes);
      if (tags.length === 0) {
        caps_cell.textContent = "\u2014";
      } else {
        for (const tag of tags) {
          const chip = document.createElement("span");
          chip.classList.add("pyc-clients-list__tag");
          chip.textContent = tag;
          caps_cell.appendChild(chip);
        }
      }
      row.appendChild(caps_cell);
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    return table;
  }
  _render_pager() {
    if (this._root === null) {
      return;
    }
    const prev = this._root.querySelector('[data-role="prev-page"]');
    const next = this._root.querySelector('[data-role="next-page"]');
    const indicator = this._root.querySelector('[data-role="page-indicator"]');
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
};

// src/pyc-pods-bundle/client-detail-view.ts
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
var PycClientDetail = class extends HTMLElement {
  _client_id;
  _client;
  _loading;
  _errored;
  _root;
  constructor() {
    super();
    this._client_id = "";
    this._client = null;
    this._loading = false;
    this._errored = false;
    this._root = null;
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
      errored: this._errored
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the client id, render the chrome,
   * and fetch the snapshot.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("client-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._client_id = attr_id;
    } else {
      this._client_id = client_id_from_path(window.location.pathname);
    }
    this._render_chrome();
    void this._load();
    return;
  }
  /**
   * Fetch the client snapshot. Exposed so unit tests can await a
   * load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_client_id(this._client_id) === false) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const client = await this._fetch_client();
    if (client === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._client = client;
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  async _fetch_client() {
    const url = build_client_detail_url(this._client_id);
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "client fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.detail_fetch_failed",
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-client-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Client detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-client-detail__heading");
    heading.textContent = "Client detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-client-detail__back-link");
    back.setAttribute("href", "/clients");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to clients";
    root.appendChild(back);
    const body = document.createElement("div");
    body.classList.add("pyc-client-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
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
      error.textContent = "Failed to load this client. Try refreshing.";
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._client));
    fragment.appendChild(this._build_heartbeat(this._client));
    fragment.appendChild(this._build_pods(this._client));
    fragment.appendChild(this._build_capabilities(this._client));
    body.replaceChildren(fragment);
    return;
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
    id_value.title = client.client_id;
    id_row.appendChild(id_value);
    const status_badge = document.createElement("span");
    status_badge.classList.add("pyc-client-detail__badge");
    status_badge.setAttribute("data-role", "status-badge");
    status_badge.setAttribute("data-tone", status_tone(client.status));
    status_badge.textContent = client.status;
    id_row.appendChild(status_badge);
    const liveness_badge = document.createElement("span");
    liveness_badge.classList.add("pyc-client-detail__badge");
    liveness_badge.setAttribute("data-role", "liveness-badge");
    liveness_badge.setAttribute(
      "data-tone",
      liveness_tone(client.liveness_state)
    );
    liveness_badge.textContent = client.liveness_state;
    id_row.appendChild(liveness_badge);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-client-detail__grid");
    this._append_field(grid, "Client id", client.client_id);
    this._append_field(grid, "Project", client.project_id);
    this._append_field(grid, "Enrolled pod", client.pod_name);
    this._append_field(
      grid,
      "Enrolled",
      format_timestamp2(client.enrolled_at)
    );
    this._append_field(
      grid,
      "Transport",
      client.transport_name !== null && client.transport_name !== void 0 && client.transport_name.length > 0 ? client.transport_name : "\u2014"
    );
    this._append_field(
      grid,
      "Agent version",
      client.last_agent_version !== null && client.last_agent_version !== void 0 && client.last_agent_version.length > 0 ? client.last_agent_version : "\u2014"
    );
    section.appendChild(grid);
    return section;
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
  _build_pods(client) {
    const section = document.createElement("section");
    section.classList.add("pyc-client-detail__pods");
    section.setAttribute("data-role", "pods-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Backed pods");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-client-detail__section-heading");
    heading.textContent = "Backed pods";
    section.appendChild(heading);
    const list = document.createElement("ul");
    list.classList.add("pyc-client-detail__pod-list");
    if (client.pod_name !== null && client.pod_name.length > 0) {
      const item = document.createElement("li");
      item.classList.add("pyc-client-detail__pod-entry");
      item.textContent = client.pod_name;
      list.appendChild(item);
    } else {
      const empty = document.createElement("li");
      empty.classList.add("pyc-client-detail__pod-empty");
      empty.textContent = "This client is not enrolled under a pod.";
      list.appendChild(empty);
    }
    section.appendChild(list);
    return section;
  }
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
    const tags = capability_tags(client.attributes);
    if (tags.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-client-detail__status");
      empty.setAttribute("data-role", "capabilities-empty");
      empty.textContent = "No capabilities reported for this client.";
      section.appendChild(empty);
      return section;
    }
    const tag_list = document.createElement("div");
    tag_list.classList.add("pyc-client-detail__tag-list");
    for (const tag of tags) {
      const chip = document.createElement("span");
      chip.classList.add("pyc-client-detail__tag");
      chip.textContent = tag;
      tag_list.appendChild(chip);
    }
    section.appendChild(tag_list);
    return section;
  }
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-client-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    def.textContent = value;
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
};

// src/pyc-pods-bundle/index.ts
var FLEET_GROUP_ID = "fleet";
var PODS_READ_PERMISSION = "system:pods.read";
var CLIENTS_READ_PERMISSION = "system:clients.read";
var PODS_ROUTE = "/pods";
var CLIENTS_ROUTE = "/clients";
var PODS_LIST_TAG = "pyc-pods-list";
var POD_DETAIL_TAG = "pyc-pod-detail";
var CLIENTS_LIST_TAG = "pyc-clients-list";
var CLIENT_DETAIL_TAG = "pyc-client-detail";
var PODS_STYLESHEET_HREF = "/static/javascript/dist/pyc-pods-bundle.css";
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
var PODS_ENTRY = {
  entryId: "fleet.pods",
  label: "Pods",
  route: PODS_ROUTE,
  requiredPermissions: [PODS_READ_PERMISSION],
  group: FLEET_GROUP_ID
};
var CLIENTS_ENTRY = {
  entryId: "fleet.clients",
  label: "Clients",
  route: CLIENTS_ROUTE,
  requiredPermissions: [CLIENTS_READ_PERMISSION],
  group: FLEET_GROUP_ID
};
function register_pods_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: FLEET_GROUP_ID,
    label: "Fleet",
    requiredPermissions: [PODS_READ_PERMISSION]
  });
  sidebar.registerEntry(PODS_ENTRY);
  sidebar.registerEntry(CLIENTS_ENTRY);
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
function _register_against(handle) {
  register_pods_sidebar(handle.sidebar);
  mount_pods_view_if_active();
  return;
}
function _boot() {
  define_pods_elements();
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
      "pychestrate.ui.pods.bundle_no_shell_handle",
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
  CLIENT_STATUSES,
  LIVENESS_STATES,
  POD_STATES,
  PycClientDetail,
  PycClientsList,
  PycPodDetail,
  PycPodsList,
  TRANSIENT_POD_STATES,
  build_client_detail_url,
  build_clients_query_url,
  build_pod_definition_url,
  build_pod_definitions_url,
  build_pod_registration_url,
  build_pod_registrations_url,
  build_pod_state_history_url,
  build_pod_state_url,
  capability_tags,
  classify_pods_route,
  format_timestamp2 as client_format_timestamp,
  client_id_from_path,
  short_id2 as client_short_id,
  has_next_page2 as clients_has_next_page,
  has_previous_page2 as clients_has_previous_page,
  define_pods_elements,
  ensure_pods_stylesheet,
  is_transient_pod_state,
  is_valid_client_id,
  is_valid_pod_id,
  liveness_tone,
  member_count,
  mount_pods_view_if_active,
  format_timestamp as pod_format_timestamp,
  pod_id_from_path,
  short_id as pod_short_id,
  pod_state_tone,
  has_next_page as pods_has_next_page,
  has_previous_page as pods_has_previous_page,
  project_id_from_search,
  register_pods_sidebar,
  status_tone,
  tag_for_pods_route
};
//# sourceMappingURL=pyc-pods-bundle.js.map
