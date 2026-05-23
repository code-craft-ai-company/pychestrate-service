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
    filters.appendChild(state_label);
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-runs-list__filter");
    project_label.textContent = "Project";
    const project_input = document.createElement("mj-text-field");
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
    const refresh_button = document.createElement("mj-button");
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
    const prev_button = document.createElement("mj-button");
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
    const next_button = document.createElement("mj-button");
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
    const table = document.createElement("mj-table");
    table.classList.add("pyc-runs-list__table");
    table.rowClass = "pyc-runs-list__row";
    table.rowAttrs = (run) => ({ "data-run-id": run.run_id });
    table.columns = [
      {
        key: "run_id",
        label: "Run",
        render: (run) => {
          const link = document.createElement("a");
          link.classList.add("pyc-runs-list__run-link");
          link.setAttribute("href", "/runs/" + run.run_id);
          link.textContent = short_run_id(run.run_id);
          return link;
        },
      },
      { key: "project_id", label: "Project" },
      {
        key: "state",
        label: "State",
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
        render: (run) => format_timestamp(run.created_at),
      },
      {
        key: "started_at",
        label: "Started",
        render: (run) => format_timestamp(run.started_at),
      },
      {
        key: "completed_at",
        label: "Completed",
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
    if (this._root === null) {
      return;
    }
    const prev = this._root.querySelector('[data-role="prev-page"]');
    const next = this._root.querySelector('[data-role="next-page"]');
    const indicator = this._root.querySelector('[data-role="page-indicator"]');
    if (prev instanceof HTMLElement) {
      prev.toggleAttribute("disabled", has_previous_page(this._state) === false);
    }
    if (next instanceof HTMLElement) {
      next.toggleAttribute("disabled", has_next_page(this._state) === false);
    }
    if (indicator instanceof HTMLElement) {
      const label = "Page " + String(this._state.page) + " \xB7 " + String(this._state.total) + " total";
      indicator.textContent = label;
    }
    return;
  }
}
export {
  PycRunsList,
  RUN_STATES,
  build_runs_query_url,
  format_timestamp,
  has_next_page,
  has_previous_page,
  short_run_id,
  state_badge_tone
};
