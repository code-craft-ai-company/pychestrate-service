const RUN_STATES = [
  "pending",
  "dispatching",
  "dispatched",
  "dispatch_unconfirmed",
  "dispatch_lost",
  "dispatch_failed",
  "running",
  "progress_stalled",
  "cancel_requested",
  "cancelling",
  "cancelled",
  "completing",
  "completed",
  "failed",
  "needs_investigation"
];
const DEFAULT_PER_PAGE = 25;
const RUNS_API_PATH = "/api/v1/runs";
const PROJECTS_API_PATH = "/api/v1/projects";
const POLL_INTERVAL_MS = 5e3;
const SESSION_EXPIRED_EVENT = "pyc-session-401";
function emit_session_expired() {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(
    new CustomEvent(SESSION_EXPIRED_EVENT, {
      bubbles: false,
      detail: {}
    })
  );
  return;
}
function login_next_url() {
  const here = window.location.pathname + window.location.search;
  const rtnval = "/login?next=" + encodeURIComponent(here);
  return rtnval;
}
async function fetch_projects() {
  let projects = null;
  try {
    const response = await fetch(PROJECTS_API_PATH, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    if (response.ok === true) {
      const body = await response.json();
      projects = extract_projects(body);
    }
  } catch (reason) {
    console.warn(
      "pychestrate.ui.runs.projects_fetch_failed",
      { reason: String(reason) }
    );
  }
  return projects;
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
function project_display_map(projects) {
  const rtnval = {};
  for (const project of projects) {
    rtnval[project.project_id] = project.display_name;
  }
  return rtnval;
}
function build_runs_query_url(state) {
  const params = new URLSearchParams();
  if (state.projectFilter.length > 0) {
    params.set("project_id", state.projectFilter);
  }
  if (state.stateFilter.length > 0) {
    params.set("state", state.stateFilter);
  }
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  const query = params.toString();
  const rtnval = RUNS_API_PATH + "?" + query;
  return rtnval;
}
function short_run_id(run_id) {
  if (typeof run_id !== "string" || run_id.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const dash_index = run_id.indexOf("-");
  if (dash_index <= 0) {
    const rtnval2 = run_id;
    return rtnval2;
  }
  const rtnval = run_id.slice(0, dash_index);
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
function state_badge_tone(run_state) {
  if (run_state === "completed") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  const error_states = ["failed", "dispatch_failed", "dispatch_lost", "needs_investigation"];
  if (error_states.indexOf(run_state) >= 0) {
    const rtnval2 = "error";
    return rtnval2;
  }
  const warn_states = ["progress_stalled", "dispatch_unconfirmed", "cancel_requested", "cancelling", "cancelled"];
  if (warn_states.indexOf(run_state) >= 0) {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "neutral";
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
class PycRunsList extends HTMLElement {
  _pager;
  _state;
  _runs;
  _root;
  _table_region;
  _projects;
  _project_names;
  _projectsAvailable;
  _projects_errored;
  _state_select;
  _project_select;
  _project_input;
  _projects_notice;
  _refresh_stamp;
  _last_refreshed_at;
  _poll_timer;
  _poll_enabled;
  _visibility_handler;
  _session_expired;
  _fetch_seq;
  constructor() {
    super();
    this._state = {
      stateFilter: "",
      projectFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false,
      errorStatus: 0
    };
    this._runs = [];
    this._root = null;
    this._table_region = null;
    this._pager = null;
    this._projects = [];
    this._project_names = {};
    this._projectsAvailable = false;
    this._projects_errored = false;
    this._state_select = null;
    this._project_select = null;
    this._project_input = null;
    this._projects_notice = null;
    this._refresh_stamp = null;
    this._last_refreshed_at = null;
    this._poll_timer = null;
    this._poll_enabled = false;
    this._visibility_handler = null;
    this._session_expired = false;
    this._fetch_seq = 0;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * filter + pagination state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      stateFilter: this._state.stateFilter,
      projectFilter: this._state.projectFilter,
      page: this._state.page,
      perPage: this._state.perPage,
      total: this._state.total,
      loading: this._state.loading,
      errored: this._state.errored,
      errorStatus: this._state.errorStatus,
      projectsAvailable: this._projectsAvailable,
      polling: this._poll_enabled
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome, load the projects
   * collection, kick off the first fetch, and start the live-poll
   * loop when the element is inserted into the document.
   */
  connectedCallback() {
    this._render_chrome();
    this._wire_visibility();
    void this._bootstrap();
    return;
  }
  /**
   * Lifecycle hook -- stop the live-poll timer and unhook the
   * visibility listener so a navigation away from the list never
   * leaks a timer or listener.
   */
  disconnectedCallback() {
    this._stop_poll();
    this._unwire_visibility();
    return;
  }
  /**
   * Load the projects collection (for display names + the
   * project filter), render the project control, run the first
   * fetch, and start the live-poll loop. Exposed via
   * ``connectedCallback``; separated so unit tests can await it.
   */
  async _bootstrap() {
    await this._load_projects();
    this._render_project_control();
    await this._refresh();
    if (this._state.errorStatus !== 401 && this._state.errorStatus !== 403) {
      this._start_poll();
    }
    return;
  }
  /**
   * Fetch the projects collection once and build the
   * id -> display-name map used by the project column and the
   * project filter. A failed fetch flags ``_projects_errored`` so
   * the chrome can surface the degraded filter honestly.
   */
  async _load_projects() {
    const projects = await fetch_projects();
    if (projects === null) {
      this._projects = [];
      this._project_names = {};
      this._projectsAvailable = false;
      this._projects_errored = true;
      return;
    }
    this._projects = projects;
    this._project_names = project_display_map(projects);
    this._projectsAvailable = projects.length > 0;
    this._projects_errored = false;
    return;
  }
  /**
   * Build the persistent chrome -- heading, filter controls,
   * pagination controls, and the table region the data render
   * replaces on every fetch.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-runs-list");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-runs-list__heading");
    heading.textContent = "Runs";
    root.appendChild(heading);
    const filters = document.createElement("div");
    filters.classList.add("pyc-runs-list__filters");
    const state_label = document.createElement("label");
    state_label.classList.add("pyc-runs-list__filter");
    state_label.textContent = "State";
    const state_select = document.createElement("mj-select");
    state_select.classList.add("pyc-runs-list__select");
    state_select.setAttribute("data-role", "state-filter");
    const any_option = document.createElement("mj-option");
    any_option.setAttribute("value", "");
    any_option.textContent = "All states";
    state_select.appendChild(any_option);
    for (const run_state of RUN_STATES) {
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
    this._state_select = state_select;
    filters.appendChild(state_label);
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-runs-list__filter");
    project_label.textContent = "Project";
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-runs-list__select");
    project_select.setAttribute("data-role", "project-filter");
    const all_projects_option = document.createElement("mj-option");
    all_projects_option.setAttribute("value", "");
    all_projects_option.textContent = "All projects";
    project_select.appendChild(all_projects_option);
    project_select.addEventListener("change", () => {
      this._state.projectFilter = project_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    this._project_select = project_select;
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-runs-list__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-filter-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectFilter = project_input.value.trim();
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_input);
    this._project_input = project_input;
    filters.appendChild(project_label);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-runs-list__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    filters.appendChild(refresh_button);
    const refresh_stamp = document.createElement("span");
    refresh_stamp.classList.add("pyc-runs-list__stamp");
    refresh_stamp.setAttribute("data-role", "refresh-stamp");
    refresh_stamp.hidden = true;
    filters.appendChild(refresh_stamp);
    this._refresh_stamp = refresh_stamp;
    root.appendChild(filters);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-runs-list__notice");
    projects_notice.setAttribute("data-role", "projects-error-notice");
    projects_notice.textContent = "Couldn't load projects — you can still filter by project id.";
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice = projects_notice;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-runs-list__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");
    pager.classList.add("pyc-runs-list__pager");
    pager.setAttribute("data-role", "pager");
    pager.setAttribute("page", String(this._state.page));
    pager.setAttribute("page-size", String(this._state.perPage));
    pager.setAttribute("total-items", String(this._state.total));
    pager.addEventListener("mj-pagination-change", (event) => {
      this._state.page = event.detail.page;
      void this._refresh();
    });
    root.appendChild(pager);
    this._pager = pager;
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Render the project-filter control from the loaded projects --
   * the ``mj-select`` picker when the collection loaded, or the
   * manual id input (plus, on a fetch *failure*, an inline notice
   * saying the picker degraded) when it did not.
   */
  _render_project_control() {
    if (this._project_select === null || this._project_input === null) {
      return;
    }
    const select_el = this._project_select;
    const input_el = this._project_input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      const all_projects_option = document.createElement("mj-option");
      all_projects_option.setAttribute("value", "");
      all_projects_option.textContent = "All projects";
      select_el.appendChild(all_projects_option);
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
    }
    if (this._projects_notice !== null) {
      this._projects_notice.hidden = this._projects_errored === false;
    }
    return;
  }
  /**
   * Resolve a project id to its display name, falling back to the
   * short form of the id when the projects collection did not
   * load or does not know the id. Never returns an empty string.
   *
   * @param project_id The run's project UUID.
   *
   * @returns A human-readable project label.
   */
  _project_display_name(project_id) {
    if (typeof project_id !== "string" || project_id.length === 0) {
      const rtnval2 = "—";
      return rtnval2;
    }
    const known = this._project_names[project_id];
    if (typeof known === "string" && known.length > 0) {
      const rtnval2 = known;
      return rtnval2;
    }
    const rtnval = short_run_id(project_id);
    return rtnval;
  }
  /**
   * Fetch the current page from the REST endpoint and re-render
   * the table region. Drives the loading / error / empty
   * states. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh(options) {
    const background = options !== undefined && options !== null && options.background === true;
    this._fetch_seq = this._fetch_seq + 1;
    const fetch_seq = this._fetch_seq;
    if (background === false) {
      this._state.loading = true;
      this._state.errored = false;
      this._state.errorStatus = 0;
      this._render_table_region();
    }
    const url = build_runs_query_url(this._state);
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
        throw new Error("runs fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.runs.list_fetch_failed",
        { reason: String(reason) }
      );
      if (fetch_seq !== this._fetch_seq) {
        // A newer fetch superseded this one while it was in
        // flight -- its outcome wins, not ours.
        return;
      }
      if (error_status === 401 || error_status === 403) {
        // The session is gone (or access was revoked) -- polling
        // again every five seconds cannot recover it.
        this._stop_poll();
      }
      if (error_status === 401) {
        this._emit_session_expired_once();
      }
      if (background === true && error_status !== 401 && error_status !== 403) {
        // A transient poll failure must not wipe the table the
        // user is looking at; the next poll cycle retries.
        return;
      }
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = error_status;
      this._render_table_region();
      return;
    }
    if (fetch_seq !== this._fetch_seq) {
      // A newer fetch superseded this one while it was in
      // flight -- its outcome wins, not ours.
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      if (background === true) {
        return;
      }
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = 0;
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
    this._state.errorStatus = 0;
    this._last_refreshed_at = new Date();
    this._render_table_region();
    this._render_refresh_stamp();
    return;
  }
  /**
   * Dispatch the site shell's global session-expired event
   * exactly once so the shell shows its sign-in toast without
   * being re-triggered by every subsequent failed poll.
   */
  _emit_session_expired_once() {
    if (this._session_expired === true) {
      return;
    }
    this._session_expired = true;
    emit_session_expired();
    return;
  }
  /**
   * Start the live-poll loop. A no-op when polling is already
   * enabled or the tab is hidden.
   */
  _start_poll() {
    if (this._poll_enabled === true) {
      return;
    }
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      return;
    }
    this._poll_enabled = true;
    this._schedule_poll();
    return;
  }
  _schedule_poll() {
    if (this._poll_timer !== null) {
      return;
    }
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
   * Run one poll cycle -- a background refresh that keeps the
   * current table on transient failures -- then reschedule while
   * polling is still enabled and the element is connected.
   * Exposed so unit tests can drive a poll cycle without waiting
   * on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    await this._refresh({ background: true });
    if (this._poll_enabled === false) {
      return;
    }
    if (this.isConnected === false) {
      this._stop_poll();
      return;
    }
    this._schedule_poll();
    return;
  }
  /**
   * Stop the live-poll loop, clearing any pending timer.
   */
  _stop_poll() {
    this._poll_enabled = false;
    if (this._poll_timer !== null) {
      clearTimeout(this._poll_timer);
      this._poll_timer = null;
    }
    return;
  }
  /**
   * Pause the live-poll loop while the tab is hidden and resume
   * it (with an immediate background refresh) when the tab
   * becomes visible again.
   */
  _wire_visibility() {
    if (typeof document === "undefined") {
      return;
    }
    const handler = () => {
      if (document.visibilityState === "hidden") {
        this._stop_poll();
        return;
      }
      if (this._session_expired === true) {
        return;
      }
      this._start_poll();
      void this._refresh({ background: true });
    };
    document.addEventListener("visibilitychange", handler);
    this._visibility_handler = handler;
    return;
  }
  _unwire_visibility() {
    if (this._visibility_handler !== null && typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", this._visibility_handler);
      this._visibility_handler = null;
    }
    return;
  }
  /**
   * Update the "as of HH:MM:SS" stamp next to the refresh button
   * from the last successful fetch time.
   */
  _render_refresh_stamp() {
    if (this._refresh_stamp === null) {
      return;
    }
    if (this._last_refreshed_at === null) {
      this._refresh_stamp.hidden = true;
      return;
    }
    this._refresh_stamp.hidden = false;
    this._refresh_stamp.textContent = "as of " + this._last_refreshed_at.toLocaleTimeString();
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
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-runs-list__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading runs\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add("pyc-runs-list__status", "pyc-runs-list__status--error");
      error.setAttribute("data-role", "error-state");
      const error_status = this._state.errorStatus;
      if (error_status === 401) {
        const expired_text = document.createElement("span");
        expired_text.textContent = "Your session has expired — sign in again. ";
        error.appendChild(expired_text);
        const login_link = document.createElement("a");
        login_link.classList.add("pyc-runs-list__status-link");
        login_link.setAttribute("href", login_next_url());
        login_link.textContent = "Sign in";
        error.appendChild(login_link);
      } else if (error_status === 403) {
        error.textContent = "You don't have access to runs.";
      } else if (error_status === 404) {
        error.textContent = "The runs API endpoint was not found (HTTP 404).";
      } else if (error_status === 0) {
        error.textContent = "Couldn't reach the server. Check your connection and try refreshing.";
      } else {
        error.textContent = "Failed to load runs. Try refreshing.";
      }
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._runs.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-runs-list__status");
      empty.setAttribute("data-role", "empty-state");
      const filters_active = this._state.stateFilter.length > 0 || this._state.projectFilter.length > 0;
      if (filters_active === true) {
        empty.textContent = "No runs match the current filters.";
        const empty_actions = document.createElement("div");
        empty_actions.classList.add("pyc-runs-list__empty-actions");
        const clear_button = document.createElement("mj-button");
        clear_button.classList.add("pyc-runs-list__button");
        clear_button.setAttribute("type", "button");
        clear_button.setAttribute("data-role", "clear-filters");
        clear_button.textContent = "Clear filters";
        clear_button.addEventListener("click", () => {
          this._clear_filters();
        });
        empty_actions.appendChild(clear_button);
        region.replaceChildren(empty, empty_actions);
      } else {
        empty.textContent = "No runs yet";
        region.replaceChildren(empty);
      }
      this._render_pager();
      return;
    }
    const table = this._build_table();
    if (this._state.total > this._state.perPage) {
      const sort_note = document.createElement("p");
      sort_note.classList.add("pyc-runs-list__sort-note");
      sort_note.setAttribute("data-role", "sort-scope-note");
      sort_note.textContent = "Sorting applies to this page only.";
      region.replaceChildren(table, sort_note);
    } else {
      region.replaceChildren(table);
    }
    this._render_pager();
    return;
  }
  /**
   * Reset both filters (and their controls) back to the
   * unfiltered view and refresh.
   */
  _clear_filters() {
    this._state.stateFilter = "";
    this._state.projectFilter = "";
    this._state.page = 1;
    if (this._state_select !== null) {
      this._state_select.value = "";
    }
    if (this._project_select !== null) {
      this._project_select.value = "";
    }
    if (this._project_input !== null) {
      this._project_input.value = "";
    }
    void this._refresh();
    return;
  }
  /**
   * Build the runs ``<table>`` from the current ``_runs`` list.
   */
  _build_table() {
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-runs-list__table");
    // Sorting is client-side over the current page. project_id /
    // run_id / state sort by their string values; the timestamp
    // columns sort by the raw ISO strings, which collate as
    // chronological order.
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-runs-list__row";
    table.rowAttrs = (run) => ({ "data-run-id": run.run_id });
    table.columns = [
      {
        key: "run_id",
        label: "Run",
        width: "10rem",
        render: (run) => {
          const link = document.createElement("a");
          link.classList.add("pyc-runs-list__run-link");
          link.setAttribute("href", "/runs/" + run.run_id);
          link.textContent = short_run_id(run.run_id);
          return link;
        },
      },
      {
        key: "project_id",
        label: "Project",
        width: "16rem",
        render: (run) => {
          const project = document.createElement("span");
          project.classList.add("pyc-runs-list__project");
          project.textContent = this._project_display_name(run.project_id);
          if (typeof run.project_id === "string" && run.project_id.length > 0) {
            project.title = run.project_id;
          }
          return project;
        },
      },
      {
        key: "state",
        label: "State",
        width: "10rem",
        render: (run) => {
          const badge = document.createElement("mj-chip");
          badge.classList.add("pyc-runs-list__badge");
          badge.setAttribute("data-tone", state_badge_tone(run.state));
          badge.textContent = run.state;
          return badge;
        },
      },
      {
        key: "created_at",
        label: "Created",
        width: "12rem",
        render: (run) => format_timestamp(run.created_at),
      },
      {
        key: "started_at",
        label: "Started",
        width: "12rem",
        render: (run) => format_timestamp(run.started_at),
      },
      {
        key: "completed_at",
        label: "Completed",
        width: "12rem",
        render: (run) => format_timestamp(run.completed_at),
      },
    ];
    table.rows = this._runs;
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
}
export {
  POLL_INTERVAL_MS,
  PycRunsList,
  RUN_STATES,
  build_runs_query_url,
  emit_session_expired,
  fetch_projects,
  format_timestamp,
  has_next_page,
  has_previous_page,
  login_next_url,
  project_display_map,
  short_run_id,
  state_badge_tone
};
