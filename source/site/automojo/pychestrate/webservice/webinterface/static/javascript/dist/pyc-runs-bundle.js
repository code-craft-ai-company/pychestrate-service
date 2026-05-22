// src/pyc-runs-bundle/runs-list-view.ts
var RUN_STATES = [
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
var DEFAULT_PER_PAGE = 25;
var RUNS_API_PATH = "/api/v1/runs";
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
var PycRunsList = class extends HTMLElement {
  _state;
  _runs;
  _root;
  _table_region;
  constructor() {
    super();
    this._state = {
      stateFilter: "",
      projectFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false
    };
    this._runs = [];
    this._root = null;
    this._table_region = null;
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
    const state_select = document.createElement("select");
    state_select.classList.add("pyc-runs-list__select");
    state_select.setAttribute("data-role", "state-filter");
    const any_option = document.createElement("option");
    any_option.value = "";
    any_option.textContent = "All states";
    state_select.appendChild(any_option);
    for (const run_state of RUN_STATES) {
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
    filters.appendChild(state_label);
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-runs-list__filter");
    project_label.textContent = "Project";
    const project_input = document.createElement("input");
    project_input.classList.add("pyc-runs-list__input");
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
    const refresh_button = document.createElement("button");
    refresh_button.classList.add("pyc-runs-list__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    filters.appendChild(refresh_button);
    root.appendChild(filters);
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-runs-list__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("div");
    pager.classList.add("pyc-runs-list__pager");
    const prev_button = document.createElement("button");
    prev_button.classList.add("pyc-runs-list__button");
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
    page_indicator.classList.add("pyc-runs-list__page-indicator");
    page_indicator.setAttribute("data-role", "page-indicator");
    pager.appendChild(page_indicator);
    const next_button = document.createElement("button");
    next_button.classList.add("pyc-runs-list__button");
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
   * Fetch the current page from the REST endpoint and re-render
   * the table region. Drives the loading / error / empty
   * states. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._state.loading = true;
    this._state.errored = false;
    this._render_table_region();
    const url = build_runs_query_url(this._state);
    let page = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error("runs fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.runs.list_fetch_failed",
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
      error.textContent = "Failed to load runs. Try refreshing.";
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._runs.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-runs-list__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No runs yet";
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
   * Build the runs ``<table>`` from the current ``_runs`` list.
   */
  _build_table() {
    const table = document.createElement("table");
    table.classList.add("pyc-runs-list__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = ["Run", "Project", "State", "Created", "Started", "Completed"];
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
      row.classList.add("pyc-runs-list__row");
      const id_cell = document.createElement("td");
      const link = document.createElement("a");
      link.classList.add("pyc-runs-list__run-link");
      link.setAttribute("href", "/runs/" + run.run_id);
      link.textContent = short_run_id(run.run_id);
      id_cell.appendChild(link);
      row.appendChild(id_cell);
      const project_cell = document.createElement("td");
      project_cell.textContent = run.project_id;
      row.appendChild(project_cell);
      const state_cell = document.createElement("td");
      const badge = document.createElement("span");
      badge.classList.add("pyc-runs-list__badge");
      badge.setAttribute("data-tone", state_badge_tone(run.state));
      badge.textContent = run.state;
      state_cell.appendChild(badge);
      row.appendChild(state_cell);
      const created_cell = document.createElement("td");
      created_cell.textContent = format_timestamp(run.created_at);
      row.appendChild(created_cell);
      const started_cell = document.createElement("td");
      started_cell.textContent = format_timestamp(run.started_at);
      row.appendChild(started_cell);
      const completed_cell = document.createElement("td");
      completed_cell.textContent = format_timestamp(run.completed_at);
      row.appendChild(completed_cell);
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

// src/pyc-runs-bundle/run-detail-view.ts
var TERMINAL_RUN_STATES = [
  "dispatch_failed",
  "cancelled",
  "completed",
  "failed"
];
var RUNS_API_PATH2 = "/api/v1/runs";
var UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function run_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/runs/";
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
function is_valid_run_id(run_id) {
  if (typeof run_id !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(run_id);
  return rtnval;
}
function is_terminal_state(run_state) {
  const rtnval = TERMINAL_RUN_STATES.indexOf(run_state) >= 0;
  return rtnval;
}
function progress_percent(progress) {
  if (progress.percent_complete !== null && progress.percent_complete !== void 0 && Number.isFinite(progress.percent_complete) === true) {
    const clamped = Math.max(0, Math.min(100, progress.percent_complete));
    return clamped;
  }
  const total = progress.tests_total;
  if (total === null || total === void 0 || total <= 0) {
    const rtnval2 = 0;
    return rtnval2;
  }
  const done = progress.tests_passed + progress.tests_failed + progress.tests_skipped + progress.tests_errored;
  const ratio = done / total * 100;
  const rtnval = Math.max(0, Math.min(100, ratio));
  return rtnval;
}
function manifest_artifacts(manifest) {
  const rtnval = [];
  const html_path = manifest.html_summary_artifact_path;
  if (html_path !== null && html_path !== void 0 && html_path.length > 0) {
    rtnval.push({ label: "Test summary (HTML)", path: html_path });
  }
  const summary_path = manifest.summary_artifact_path;
  if (summary_path !== null && summary_path !== void 0 && summary_path.length > 0) {
    rtnval.push({ label: "Run summary (JSON)", path: summary_path });
  }
  const results_path = manifest.results_artifact_path;
  if (results_path !== null && results_path !== void 0 && results_path.length > 0) {
    rtnval.push({ label: "Consolidated results (JSON)", path: results_path });
  }
  const stream_path = manifest.results_stream_artifact_path;
  if (stream_path !== null && stream_path !== void 0 && stream_path.length > 0) {
    rtnval.push({ label: "Results stream (JSOS)", path: stream_path });
  }
  return rtnval;
}
function artifact_url(run_id, artifact_path) {
  const encoded_run = encodeURIComponent(run_id);
  const segments = artifact_path.split("/");
  const encoded_segments = [];
  for (const segment of segments) {
    encoded_segments.push(encodeURIComponent(segment));
  }
  const encoded_path = encoded_segments.join("/");
  const rtnval = RUNS_API_PATH2 + "/" + encoded_run + "/artifacts/" + encoded_path;
  return rtnval;
}
var PycRunDetail = class extends HTMLElement {
  _run_id;
  _run;
  _loading;
  _errored;
  _terminal;
  _stream_status;
  _source;
  _root;
  constructor() {
    super();
    this._run_id = "";
    this._run = null;
    this._loading = false;
    this._errored = false;
    this._terminal = false;
    this._stream_status = "idle";
    this._source = null;
    this._root = null;
  }
  /**
   * Observed attributes -- ``run-id`` may be supplied explicitly
   * by a host; otherwise it is read from the path on mount.
   */
  static get observedAttributes() {
    const rtnval = ["run-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      runId: this._run_id,
      loading: this._loading,
      errored: this._errored,
      streamStatus: this._stream_status,
      terminal: this._terminal
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the run id, render the chrome,
   * fetch the initial snapshot, and open the live stream.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("run-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._run_id = attr_id;
    } else {
      this._run_id = run_id_from_path(window.location.pathname);
    }
    this._render_chrome();
    void this._load();
    return;
  }
  /**
   * Lifecycle hook -- close the live SSE connection so a
   * navigation away from the run never leaks a connection.
   */
  disconnectedCallback() {
    this._close_stream();
    return;
  }
  /**
   * Fetch the initial run snapshot then -- when the run is not
   * already terminal -- open the live event stream. Exposed so
   * unit tests can await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_run_id(this._run_id) === false) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    let run = null;
    try {
      const url = RUNS_API_PATH2 + "/" + encodeURIComponent(this._run_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error("run fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      run = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.runs.detail_fetch_failed",
        { reason: String(reason) }
      );
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._run = run;
    this._loading = false;
    this._errored = false;
    this._terminal = is_terminal_state(run.state);
    this._render_body();
    if (this._terminal === false) {
      this._open_stream();
    }
    return;
  }
  /**
   * Open the ``EventSource`` against the run's SSE event stream
   * and wire its handlers. A no-op when a stream is already
   * open or ``EventSource`` is unavailable.
   */
  _open_stream() {
    if (this._source !== null) {
      return;
    }
    if (typeof EventSource === "undefined") {
      return;
    }
    const url = RUNS_API_PATH2 + "/" + encodeURIComponent(this._run_id) + "/events";
    this._stream_status = "connecting";
    this._render_stream_banner();
    const source = new EventSource(url, { withCredentials: true });
    this._source = source;
    source.onopen = () => {
      this._stream_status = "open";
      this._render_stream_banner();
    };
    source.onmessage = (event) => {
      this._handle_stream_message(event);
    };
    source.onerror = () => {
      if (this._terminal === true) {
        this._close_stream();
        this._stream_status = "closed";
      } else {
        this._stream_status = "reconnecting";
      }
      this._render_stream_banner();
    };
    return;
  }
  /**
   * Close the live ``EventSource`` if one is open.
   */
  _close_stream() {
    if (this._source !== null) {
      this._source.close();
      this._source = null;
    }
    return;
  }
  /**
   * Parse one SSE message frame and apply it. Exposed so unit
   * tests can feed events without a real ``EventSource``.
   *
   * @param event The ``MessageEvent`` delivered by the stream.
   */
  handleStreamMessage(event) {
    this._handle_stream_message(event);
    return;
  }
  _handle_stream_message(event) {
    let parsed = null;
    try {
      parsed = JSON.parse(String(event.data));
    } catch (reason) {
      console.warn(
        "pychestrate.ui.runs.detail_event_parse_failed",
        { reason: String(reason) }
      );
      return;
    }
    if (parsed === null || typeof parsed.event_type !== "string") {
      return;
    }
    this._apply_event(parsed);
    return;
  }
  _apply_event(run_event) {
    if (run_event.event_type === "heartbeat") {
      return;
    }
    if (run_event.event_type === "state_changed") {
      if (this._run !== null && typeof run_event.state === "string") {
        this._run.state = run_event.state;
        if (run_event.terminal_outcome !== void 0 && run_event.terminal_outcome !== null) {
          this._run.terminal_outcome = run_event.terminal_outcome;
        }
        this._terminal = is_terminal_state(run_event.state);
      }
      this._render_body();
      if (this._terminal === true) {
        this._close_stream();
        this._stream_status = "closed";
        this._render_stream_banner();
      }
      return;
    }
    if (run_event.event_type === "progress") {
      if (run_event.progress !== void 0 && run_event.progress !== null) {
        this._render_progress(run_event.progress);
      }
      return;
    }
    if (run_event.event_type === "result_manifest") {
      if (run_event.manifest !== void 0 && run_event.manifest !== null) {
        this._render_artifacts(run_event.manifest);
      }
      return;
    }
    return;
  }
  /**
   * Build the persistent chrome -- heading + the body region
   * the data render replaces.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-run-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Run detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-run-detail__heading");
    heading.textContent = "Run detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-run-detail__back-link");
    back.setAttribute("href", "/runs");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to runs";
    root.appendChild(back);
    const banner = document.createElement("p");
    banner.classList.add("pyc-run-detail__banner");
    banner.setAttribute("data-role", "stream-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;
    root.appendChild(banner);
    const body = document.createElement("div");
    body.classList.add("pyc-run-detail__body");
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
      loading.classList.add("pyc-run-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading run\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._run === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-run-detail__status",
        "pyc-run-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load this run. Try refreshing.";
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._run));
    const progress_section = document.createElement("section");
    progress_section.classList.add("pyc-run-detail__progress");
    progress_section.setAttribute("data-role", "progress-section");
    progress_section.setAttribute("role", "region");
    progress_section.setAttribute("aria-label", "Progress");
    fragment.appendChild(progress_section);
    const artifacts_section = document.createElement("section");
    artifacts_section.classList.add("pyc-run-detail__artifacts");
    artifacts_section.setAttribute("data-role", "artifacts-section");
    artifacts_section.setAttribute("role", "region");
    artifacts_section.setAttribute("aria-label", "Artifacts");
    fragment.appendChild(artifacts_section);
    body.replaceChildren(fragment);
    const summary = this._run.progress_summary;
    if (summary !== void 0 && summary !== null) {
      this._render_progress(summary);
    }
    return;
  }
  /**
   * Build the run summary block -- identity, state badge,
   * dispatch attempt, timestamps, and terminal outcome.
   *
   * @param run The current run snapshot.
   *
   * @returns A populated summary section element.
   */
  _build_summary(run) {
    const section = document.createElement("section");
    section.classList.add("pyc-run-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Run summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-run-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-run-detail__run-id");
    id_value.setAttribute("data-role", "run-id");
    id_value.textContent = short_run_id(run.run_id);
    id_value.title = run.run_id;
    id_row.appendChild(id_value);
    const badge = document.createElement("span");
    badge.classList.add("pyc-run-detail__badge");
    badge.setAttribute("data-role", "state-badge");
    badge.setAttribute("data-tone", state_badge_tone(run.state));
    badge.textContent = run.state;
    id_row.appendChild(badge);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-run-detail__grid");
    this._append_field(grid, "Project", run.project_id);
    this._append_field(grid, "Pod", run.pod_id);
    this._append_field(grid, "Job type", run.job_type);
    const job_name = run.job_name;
    if (job_name !== void 0 && job_name !== null && job_name.length > 0) {
      this._append_field(grid, "Job name", job_name);
    }
    const attempt_field = document.createElement("div");
    attempt_field.classList.add("pyc-run-detail__field");
    const attempt_term = document.createElement("dt");
    attempt_term.textContent = "Dispatch attempt";
    const attempt_def = document.createElement("dd");
    attempt_def.setAttribute("data-role", "dispatch-attempt");
    const attempt = run.current_dispatch_attempt_id;
    if (attempt !== void 0 && attempt !== null && attempt.length > 0) {
      attempt_def.textContent = attempt;
    } else {
      attempt_def.textContent = "\u2014";
    }
    attempt_field.appendChild(attempt_term);
    attempt_field.appendChild(attempt_def);
    grid.appendChild(attempt_field);
    this._append_field(grid, "Created", format_timestamp(run.created_at));
    this._append_field(grid, "Dispatched", format_timestamp(run.dispatched_at));
    this._append_field(grid, "Started", format_timestamp(run.started_at));
    this._append_field(grid, "Completed", format_timestamp(run.completed_at));
    const outcome_field = document.createElement("div");
    outcome_field.classList.add("pyc-run-detail__field");
    const outcome_term = document.createElement("dt");
    outcome_term.textContent = "Terminal outcome";
    const outcome_def = document.createElement("dd");
    outcome_def.setAttribute("data-role", "terminal-outcome");
    const outcome = run.terminal_outcome;
    if (outcome !== void 0 && outcome !== null && outcome.length > 0) {
      outcome_def.textContent = outcome;
    } else {
      outcome_def.textContent = "\u2014";
    }
    outcome_field.appendChild(outcome_term);
    outcome_field.appendChild(outcome_def);
    grid.appendChild(outcome_field);
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
    field.classList.add("pyc-run-detail__field");
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
   * Render the progress section from a ``ProgressSummary``
   * roll-up -- pass/fail/total counts plus a progress bar.
   *
   * @param progress A ``ProgressSummary`` payload.
   */
  _render_progress(progress) {
    if (this._root === null) {
      return;
    }
    const section = this._root.querySelector('[data-role="progress-section"]');
    if (section === null) {
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-run-detail__section-heading");
    heading.textContent = "Progress";
    const total = progress.tests_total;
    const counts = document.createElement("div");
    counts.classList.add("pyc-run-detail__counts");
    this._append_count(counts, "Passed", progress.tests_passed, "ok");
    this._append_count(counts, "Failed", progress.tests_failed, "error");
    this._append_count(counts, "Errored", progress.tests_errored, "error");
    this._append_count(counts, "Skipped", progress.tests_skipped, "warn");
    if (total !== void 0 && total !== null) {
      this._append_count(counts, "Total", total, "neutral");
    }
    const percent = progress_percent(progress);
    const bar = document.createElement("div");
    bar.classList.add("pyc-run-detail__bar");
    bar.setAttribute("data-role", "progress-bar");
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-valuenow", String(Math.round(percent)));
    const fill = document.createElement("div");
    fill.classList.add("pyc-run-detail__bar-fill");
    fill.style.width = String(percent) + "%";
    bar.appendChild(fill);
    section.replaceChildren(heading, counts, bar);
    const notes = progress.notes;
    if (notes !== void 0 && notes !== null && notes.length > 0) {
      const notes_el = document.createElement("p");
      notes_el.classList.add("pyc-run-detail__progress-notes");
      notes_el.setAttribute("data-role", "progress-notes");
      notes_el.textContent = notes;
      section.appendChild(notes_el);
    }
    return;
  }
  /**
   * Append one labelled count chip to the progress counts row.
   *
   * @param container The counts container element.
   * @param label The count's display label.
   * @param value The numeric count.
   * @param tone Coarse tone driving the chip color.
   */
  _append_count(container, label, value, tone) {
    const chip = document.createElement("span");
    chip.classList.add("pyc-run-detail__count");
    chip.setAttribute("data-tone", tone);
    const count = document.createElement("strong");
    count.textContent = String(value);
    const caption = document.createElement("span");
    caption.textContent = label;
    chip.appendChild(count);
    chip.appendChild(caption);
    container.appendChild(chip);
    return;
  }
  /**
   * Render the artifacts section from a ``ResultManifest`` --
   * the pass/fail rollup plus a list of artifact links with the
   * HTML test summary surfaced first.
   *
   * @param manifest A ``ResultManifest`` payload.
   */
  _render_artifacts(manifest) {
    if (this._root === null) {
      return;
    }
    const section = this._root.querySelector('[data-role="artifacts-section"]');
    if (section === null) {
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-run-detail__section-heading");
    heading.textContent = "Artifacts";
    const rollup = document.createElement("p");
    rollup.classList.add("pyc-run-detail__rollup");
    rollup.setAttribute("data-role", "artifacts-rollup");
    const passed = manifest.tests_passed;
    const failed = manifest.tests_failed;
    const passed_text = passed === void 0 || passed === null ? 0 : passed;
    const failed_text = failed === void 0 || failed === null ? 0 : failed;
    rollup.textContent = "Outcome " + manifest.terminal_outcome + " \xB7 " + String(passed_text) + " passed \xB7 " + String(failed_text) + " failed";
    const list = document.createElement("ul");
    list.classList.add("pyc-run-detail__artifact-list");
    list.setAttribute("data-role", "artifact-list");
    const artifacts = manifest_artifacts(manifest);
    if (artifacts.length === 0) {
      const empty = document.createElement("li");
      empty.classList.add("pyc-run-detail__artifact-empty");
      empty.textContent = "No artifacts recorded for this run.";
      list.appendChild(empty);
    } else {
      for (const artifact of artifacts) {
        const item = document.createElement("li");
        item.classList.add("pyc-run-detail__artifact");
        const link = document.createElement("a");
        link.classList.add("pyc-run-detail__artifact-link");
        link.setAttribute(
          "href",
          artifact_url(this._run_id, artifact.path)
        );
        link.setAttribute("rel", "noopener noreferrer");
        link.textContent = artifact.label;
        if (artifact.path.endsWith("testsummary.html") === true) {
          link.setAttribute("data-role", "summary-link");
        }
        item.appendChild(link);
        const path_hint = document.createElement("span");
        path_hint.classList.add("pyc-run-detail__artifact-path");
        path_hint.textContent = artifact.path;
        item.appendChild(path_hint);
        list.appendChild(item);
      }
    }
    section.replaceChildren(heading, rollup, list);
    return;
  }
  /**
   * Update the consolidated stream-status banner. Shows a
   * reconnecting affordance while the stream is down and a
   * "live updates ended" note once a terminal run's stream
   * closes.
   */
  _render_stream_banner() {
    if (this._root === null) {
      return;
    }
    const banner = this._root.querySelector('[data-role="stream-banner"]');
    if (banner === null || banner instanceof HTMLElement === false) {
      return;
    }
    const el = banner;
    if (this._stream_status === "reconnecting") {
      el.hidden = false;
      el.setAttribute("data-tone", "warn");
      el.textContent = "Live updates interrupted \u2014 reconnecting\u2026";
      return;
    }
    if (this._stream_status === "closed" && this._terminal === true) {
      el.hidden = false;
      el.setAttribute("data-tone", "neutral");
      el.textContent = "Run finished \u2014 live updates ended.";
      return;
    }
    el.hidden = true;
    el.textContent = "";
    return;
  }
};

// src/pyc-runs-bundle/index.ts
var ORCHESTRATION_GROUP_ID = "orchestration";
var RUNS_READ_PERMISSION = "system:runs.read";
var RUNS_ROUTE = "/runs";
var RUNS_LIST_TAG = "pyc-runs-list";
var RUN_DETAIL_TAG = "pyc-run-detail";
var RUNS_STYLESHEET_HREF = "/static/javascript/dist/pyc-runs-bundle.css";
function ensure_runs_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-runs-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = RUNS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-runs-bundle");
  document.head.appendChild(link);
  return;
}
var RUNS_ENTRY = {
  entryId: "orchestration.runs",
  label: "Runs",
  route: RUNS_ROUTE,
  requiredPermissions: [RUNS_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_runs_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [RUNS_READ_PERMISSION]
  });
  sidebar.registerEntry(RUNS_ENTRY);
  return;
}
function define_runs_list_element() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(RUNS_LIST_TAG) === void 0) {
    customElements.define(RUNS_LIST_TAG, PycRunsList);
  }
  if (customElements.get(RUN_DETAIL_TAG) === void 0) {
    customElements.define(RUN_DETAIL_TAG, PycRunDetail);
  }
  return;
}
function classify_runs_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === RUNS_ROUTE || working === RUNS_ROUTE + "/") {
    const rtnval2 = "list";
    return rtnval2;
  }
  const detail_id = run_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_runs_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_runs_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main");
  if (main === null) {
    return;
  }
  const target_tag = route === "detail" ? RUN_DETAIL_TAG : RUNS_LIST_TAG;
  const existing = main.querySelector(target_tag);
  if (existing !== null) {
    return;
  }
  define_runs_list_element();
  ensure_runs_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_runs_view_if_active();
  return;
}
function _boot() {
  define_runs_list_element();
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
      "pychestrate.ui.runs.bundle_no_shell_handle",
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
  PycRunDetail,
  PycRunsList,
  artifact_url,
  classify_runs_route,
  define_runs_list_element,
  ensure_runs_stylesheet,
  is_terminal_state,
  is_valid_run_id,
  manifest_artifacts,
  mount_runs_view_if_active,
  progress_percent,
  register_runs_sidebar,
  run_id_from_path
};
//# sourceMappingURL=pyc-runs-bundle.js.map
