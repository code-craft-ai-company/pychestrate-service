const PROJECTS_API_PATH = "/api/v1/projects";
function build_test_metrics_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/test-metrics";
  return rtnval;
}
function format_rate(rate) {
  if (typeof rate !== "number" || Number.isFinite(rate) === false) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const clamped = Math.min(1, Math.max(0, rate));
  const percent = Math.round(clamped * 100);
  const rtnval = String(percent) + "%";
  return rtnval;
}
function format_duration(seconds) {
  if (seconds === null || seconds === void 0 || Number.isFinite(seconds) === false) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  if (seconds < 60) {
    const rtnval2 = seconds.toFixed(1) + "s";
    return rtnval2;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  const rtnval = String(minutes) + "m " + String(remainder) + "s";
  return rtnval;
}
function compute_bar_fractions(durations) {
  const rtnval = [];
  if (Array.isArray(durations) === false || durations.length === 0) {
    return rtnval;
  }
  let max_value = 0;
  for (const value of durations) {
    if (typeof value === "number" && value > max_value) {
      max_value = value;
    }
  }
  if (max_value <= 0) {
    for (let index = 0; index < durations.length; index = index + 1) {
      rtnval.push(0);
    }
    return rtnval;
  }
  for (const value of durations) {
    const safe = typeof value === "number" && value > 0 ? value : 0;
    rtnval.push(safe / max_value);
  }
  return rtnval;
}
class PycTestMetrics extends HTMLElement {
  _state;
  _projects;
  _projectsAvailable;
  _summary;
  _root;
  _content_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      loading: false,
      errored: false
    };
    this._projects = [];
    this._projectsAvailable = false;
    this._summary = null;
    this._root = null;
    this._content_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + load state without scraping the DOM.
   */
  get viewState() {
    const rtnval = {
      projectId: this._state.projectId,
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
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.textContent = "Test Metrics";
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
      void this._refresh();
    });
    controls.appendChild(project_input);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-metrics__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const content_region = document.createElement("div");
    content_region.classList.add("pyc-metrics__content-region");
    content_region.setAttribute("data-role", "content-region");
    root.appendChild(content_region);
    this._content_region = content_region;
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
        "pychestrate.ui.metrics.projects_fetch_failed",
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
      await this._refresh();
    } else {
      this._render_content();
    }
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
   * Re-fetch the test-metrics summary for the current project
   * and re-render the content region. Exposed so unit tests can
   * await a render cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._render_content();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._render_content();
    let summary = null;
    let errored = false;
    try {
      const url = build_test_metrics_url(this._state.projectId);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        summary = body;
      } else {
        errored = true;
      }
    } catch (reason) {
      errored = true;
      console.warn(
        "pychestrate.ui.metrics.test_metrics_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._state.loading = false;
    this._state.errored = errored;
    this._summary = summary;
    this._render_content();
    return;
  }
  _render_content() {
    if (this._content_region === null) {
      return;
    }
    const region = this._content_region;
    region.replaceChildren();
    if (this._state.projectId.length === 0) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "Select a project to view test metrics.";
      region.appendChild(notice);
      return;
    }
    if (this._state.loading === true) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "Loading test metrics\u2026";
      region.appendChild(notice);
      return;
    }
    if (this._state.errored === true || this._summary === null) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.classList.add("pyc-metrics__notice--error");
      notice.textContent = "Failed to load test metrics for this project.";
      region.appendChild(notice);
      return;
    }
    region.appendChild(this._build_cards(this._summary.summary));
    region.appendChild(
      this._build_duration_trend(this._summary.recent_runs)
    );
    region.appendChild(
      this._build_runs_table(this._summary.recent_runs)
    );
    return;
  }
  _build_cards(rollup) {
    const cards = document.createElement("div");
    cards.classList.add("pyc-metrics__cards");
    cards.setAttribute("data-role", "rollup-cards");
    const entries = [
      {
        label: "Pass rate",
        value: format_rate(rollup.pass_rate),
        tone: "ok"
      },
      {
        label: "Fail rate",
        value: format_rate(rollup.fail_rate),
        tone: "error"
      },
      {
        label: "Flake run rate",
        value: format_rate(rollup.flake_run_rate),
        tone: "warn"
      },
      {
        label: "Runs",
        value: String(rollup.run_count),
        tone: "neutral"
      },
      {
        label: "Tests total",
        value: String(rollup.tests_total),
        tone: "neutral"
      },
      {
        label: "Avg duration",
        value: format_duration(rollup.average_run_duration_seconds),
        tone: "neutral"
      }
    ];
    for (const entry of entries) {
      const card = document.createElement("div");
      card.classList.add("pyc-metrics__card");
      if (entry.tone !== "neutral") {
        card.classList.add("pyc-metrics__card--" + entry.tone);
      }
      const label = document.createElement("span");
      label.classList.add("pyc-metrics__card-label");
      label.textContent = entry.label;
      const value = document.createElement("span");
      value.classList.add("pyc-metrics__card-value");
      value.textContent = entry.value;
      card.appendChild(label);
      card.appendChild(value);
      cards.appendChild(card);
    }
    return cards;
  }
  _build_duration_trend(runs) {
    const durations = [];
    const ordered = runs.slice().reverse();
    for (const run of ordered) {
      const value = run.duration_seconds;
      durations.push(
        typeof value === "number" && Number.isFinite(value) ? value : 0
      );
    }
    const fractions = compute_bar_fractions(durations);
    const bars = document.createElement("div");
    bars.classList.add("pyc-metrics__bars");
    bars.setAttribute("data-role", "duration-trend");
    for (let index = 0; index < fractions.length; index = index + 1) {
      const fraction = fractions[index];
      const bar = document.createElement("div");
      bar.classList.add("pyc-metrics__bar");
      const run = ordered[index];
      const failed = typeof run.tests_failed === "number" && run.tests_failed > 0;
      if (failed === true) {
        bar.classList.add("pyc-metrics__bar--error");
      }
      const percent = Math.round(fraction * 100);
      bar.style.height = String(Math.max(2, percent)) + "%";
      bar.title = format_duration(durations[index]);
      bars.appendChild(bar);
    }
    return bars;
  }
  _build_runs_table(runs) {
    const table = document.createElement("table");
    table.classList.add("pyc-metrics__table");
    table.setAttribute("data-role", "runs-table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const headers = [
      "Run",
      "Parser",
      "Total",
      "Passed",
      "Failed",
      "Duration"
    ];
    for (const text of headers) {
      const th = document.createElement("th");
      th.textContent = text;
      head_row.appendChild(th);
    }
    thead.appendChild(head_row);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const run of runs) {
      const row = document.createElement("tr");
      const cells = [
        short_metric_id(run.run_id),
        run.parser_tag !== null && run.parser_tag !== void 0 ? run.parser_tag : "\u2014",
        String(
          typeof run.tests_total === "number" ? run.tests_total : 0
        ),
        String(
          typeof run.tests_passed === "number" ? run.tests_passed : 0
        ),
        String(
          typeof run.tests_failed === "number" ? run.tests_failed : 0
        ),
        format_duration(run.duration_seconds)
      ];
      for (const text of cells) {
        const td = document.createElement("td");
        td.textContent = text;
        row.appendChild(td);
      }
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    return table;
  }
}
function short_metric_id(value) {
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
export {
  PycTestMetrics,
  build_test_metrics_url,
  compute_bar_fractions,
  extract_projects,
  format_duration,
  format_rate,
  short_metric_id
};
