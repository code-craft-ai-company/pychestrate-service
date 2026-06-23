// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-metrics-bundle/test-metrics-view.js
var PROJECTS_API_PATH = "/api/v1/projects";
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
var PycTestMetrics = class extends HTMLElement {
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
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-metrics__table");
    table.setAttribute("data-role", "runs-table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-metrics__row";
    table.rowAttrs = (run) => ({ "data-run-id": run.run_id });
    table.columns = [
      {
        key: "run_id",
        label: "Run",
        width: "10rem",
        render: (run) => short_metric_id(run.run_id)
      },
      {
        key: "parser_tag",
        label: "Parser",
        width: "10rem",
        render: (run) => run.parser_tag !== null && run.parser_tag !== void 0 ? run.parser_tag : "\u2014"
      },
      {
        key: "tests_total",
        label: "Total",
        width: "8rem",
        render: (run) => String(typeof run.tests_total === "number" ? run.tests_total : 0)
      },
      {
        key: "tests_passed",
        label: "Passed",
        width: "8rem",
        render: (run) => String(typeof run.tests_passed === "number" ? run.tests_passed : 0)
      },
      {
        key: "tests_failed",
        label: "Failed",
        width: "8rem",
        render: (run) => String(typeof run.tests_failed === "number" ? run.tests_failed : 0)
      },
      {
        key: "duration",
        label: "Duration",
        width: "10rem",
        render: (run) => format_duration(run.duration_seconds)
      }
    ];
    table.rows = runs;
    return table;
  }
};
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-metrics-bundle/timeseries-view.js
var METRICS_API_PATH = "/api/v1/metrics";
var TIME_RANGE_PRESETS = [
  { id: "1h", label: "Last hour", hours: 1 },
  { id: "24h", label: "Last 24 hours", hours: 24 },
  { id: "7d", label: "Last 7 days", hours: 168 },
  { id: "30d", label: "Last 30 days", hours: 720 },
  { id: "all", label: "All time", hours: 0 }
];
function resolve_range_preset(range_id) {
  for (const preset of TIME_RANGE_PRESETS) {
    if (preset.id === range_id) {
      const rtnval2 = preset;
      return rtnval2;
    }
  }
  const rtnval = TIME_RANGE_PRESETS[0];
  return rtnval;
}
function build_timeseries_url(metric, range_id, now) {
  const params = new URLSearchParams();
  params.set("metric", metric);
  const preset = resolve_range_preset(range_id);
  if (preset.hours > 0) {
    const from_millis = now.getTime() - preset.hours * 3600 * 1e3;
    const from_date = new Date(from_millis);
    params.set("from", from_date.toISOString());
    params.set("to", now.toISOString());
  }
  const query = params.toString();
  const rtnval = METRICS_API_PATH + "/timeseries?" + query;
  return rtnval;
}
function build_catalog_url() {
  const rtnval = METRICS_API_PATH + "/catalog";
  return rtnval;
}
var PycTimeseriesExplorer = class extends HTMLElement {
  _state;
  _catalog;
  _query;
  _root;
  _chart_region;
  constructor() {
    super();
    this._state = {
      metric: "",
      rangeId: "24h",
      loading: false,
      errored: false
    };
    this._catalog = [];
    this._query = null;
    this._root = null;
    this._chart_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * selection + load state without scraping the DOM.
   */
  get viewState() {
    const rtnval = {
      metric: this._state.metric,
      rangeId: this._state.rangeId,
      loading: this._state.loading,
      errored: this._state.errored
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * catalog fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_catalog();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.textContent = "Timeseries Explorer";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-metrics__controls");
    const metric_label = document.createElement("label");
    metric_label.classList.add("pyc-metrics__field");
    metric_label.textContent = "Metric";
    const metric_select = document.createElement("mj-select");
    metric_select.classList.add("pyc-metrics__select");
    metric_select.setAttribute("data-role", "metric-select");
    metric_select.addEventListener("change", () => {
      this._state.metric = metric_select.value;
      void this._refresh();
    });
    metric_label.appendChild(metric_select);
    controls.appendChild(metric_label);
    const range_label = document.createElement("label");
    range_label.classList.add("pyc-metrics__field");
    range_label.textContent = "Range";
    const range_select = document.createElement("mj-select");
    range_select.classList.add("pyc-metrics__select");
    range_select.setAttribute("data-role", "range-select");
    for (const preset of TIME_RANGE_PRESETS) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", preset.id);
      option.textContent = preset.label;
      range_select.appendChild(option);
    }
    range_select.value = this._state.rangeId;
    range_select.addEventListener("change", () => {
      this._state.rangeId = range_select.value;
      void this._refresh();
    });
    range_label.appendChild(range_select);
    controls.appendChild(range_label);
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
    const chart_region = document.createElement("div");
    chart_region.classList.add("pyc-metrics__chart-region");
    chart_region.setAttribute("data-role", "chart-region");
    root.appendChild(chart_region);
    this._chart_region = chart_region;
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the metric catalog and populate the metric picker.
   * Exposed so unit tests can await the bootstrap fetch cycle.
   */
  async loadCatalog() {
    await this._load_catalog();
    return;
  }
  async _load_catalog() {
    let catalog = null;
    try {
      const response = await fetch(build_catalog_url(), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        catalog = extract_catalog(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.catalog_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (catalog !== null && catalog.length > 0) {
      this._catalog = catalog;
      this._state.metric = catalog[0].name;
    } else {
      this._catalog = [];
    }
    this._render_metric_control();
    if (this._state.metric.length > 0) {
      await this._refresh();
    } else {
      this._render_chart();
    }
    return;
  }
  _render_metric_control() {
    if (this._root === null) {
      return;
    }
    const select = this._root.querySelector('[data-role="metric-select"]');
    if (select instanceof HTMLElement === false) {
      return;
    }
    const select_el = select;
    select_el.replaceChildren();
    if (this._catalog.length === 0) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", "");
      option.textContent = "No metrics registered";
      select_el.appendChild(option);
      return;
    }
    for (const entry of this._catalog) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", entry.name);
      const suffix = entry.kind.length > 0 ? " (" + entry.kind + ")" : "";
      option.textContent = entry.name + suffix;
      select_el.appendChild(option);
    }
    select_el.value = this._state.metric;
    return;
  }
  /**
   * Re-fetch the timeseries for the current metric / range and
   * re-render the chart. Exposed so unit tests can await a cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.metric.length === 0) {
      this._render_chart();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._render_chart();
    let query = null;
    let errored = false;
    try {
      const url = build_timeseries_url(
        this._state.metric,
        this._state.rangeId,
        /* @__PURE__ */ new Date()
      );
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        query = body;
      } else {
        errored = true;
      }
    } catch (reason) {
      errored = true;
      console.warn(
        "pychestrate.ui.metrics.timeseries_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._state.loading = false;
    this._state.errored = errored;
    this._query = query;
    this._render_chart();
    return;
  }
  _render_chart() {
    if (this._chart_region === null) {
      return;
    }
    const region = this._chart_region;
    region.replaceChildren();
    if (this._state.metric.length === 0) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "No metric selected.";
      region.appendChild(notice);
      return;
    }
    if (this._state.loading === true) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "Loading timeseries\u2026";
      region.appendChild(notice);
      return;
    }
    if (this._state.errored === true || this._query === null) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.classList.add("pyc-metrics__notice--error");
      notice.textContent = "Failed to load the timeseries query.";
      region.appendChild(notice);
      return;
    }
    const points = this._query.points;
    if (Array.isArray(points) === false || points.length === 0) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "No data points in the selected range.";
      region.appendChild(notice);
      return;
    }
    const chart = build_chart_element(points, this._state.metric);
    region.appendChild(chart);
    return;
  }
};
function build_chart_element(points, metric_name) {
  const chart = document.createElement("mj-chart");
  chart.classList.add("pyc-metrics__chart");
  chart.setAttribute("data-role", "timeseries-chart");
  chart.setAttribute("type", "area");
  const sorted = points.slice().sort((left, right) => {
    const left_time = new Date(left.observed_at).getTime();
    const right_time = new Date(right.observed_at).getTime();
    const rtnval = left_time - right_time;
    return rtnval;
  });
  const series_points = [];
  for (const point of sorted) {
    series_points.push({ x: point.observed_at, y: point.value });
  }
  const series_name = metric_name !== null && metric_name.length > 0 ? metric_name : "value";
  chart.data = {
    series: [
      {
        name: series_name,
        points: series_points
      }
    ]
  };
  return chart;
}
function extract_catalog(body) {
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
    const name = record.name;
    if (typeof name !== "string" || name.length === 0) {
      continue;
    }
    const kind = typeof record.kind === "string" ? record.kind : "";
    let label_names = [];
    if (Array.isArray(record.label_names) === true) {
      label_names = record.label_names.filter(
        (value) => typeof value === "string"
      );
    }
    const entry = {
      name,
      kind,
      label_names
    };
    if (typeof record.help_text === "string") {
      entry.help_text = record.help_text;
    }
    rtnval.push(entry);
  }
  return rtnval;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-metrics-bundle/dashboards-view.js
var PROJECTS_API_PATH2 = "/api/v1/projects";
var DASHBOARDS_ROUTE = "/dashboards";
function build_dashboards_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH2 + "/" + encodeURIComponent(project_id) + "/dashboards";
  return rtnval;
}
function build_dashboard_detail_url(project_id, dashboard_id) {
  const rtnval = PROJECTS_API_PATH2 + "/" + encodeURIComponent(project_id) + "/dashboards/" + encodeURIComponent(dashboard_id);
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
  const metric = config.metric;
  if (typeof metric !== "string") {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = metric;
  return rtnval;
}
var PycDashboardsList = class extends HTMLElement {
  _state;
  _projects;
  _projectsAvailable;
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
      errored: false
    };
    this._projects = [];
    this._projectsAvailable = false;
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
      errored: this._state.errored
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
    const create_button = document.createElement("mj-button");
    create_button.classList.add("pyc-metrics__button");
    create_button.setAttribute("type", "button");
    create_button.setAttribute("data-role", "create-toggle");
    create_button.textContent = "Create Dashboard";
    create_button.addEventListener("click", () => {
      this._toggle_create_form();
    });
    controls.appendChild(create_button);
    root.appendChild(controls);
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
    try {
      const response = await fetch(PROJECTS_API_PATH2, {
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
      this._render_table();
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
    this._render_table();
    let dashboards = [];
    let errored = false;
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
      }
    } catch (reason) {
      errored = true;
      console.warn(
        "pychestrate.ui.metrics.dashboards_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._state.loading = false;
    this._state.errored = errored;
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
      notice.textContent = "Failed to load dashboards for this project.";
      region.appendChild(notice);
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
          link.setAttribute(
            "href",
            DASHBOARDS_ROUTE + "/" + encodeURIComponent(dashboard.dashboard_id)
          );
          link.textContent = dashboard.name;
          return link;
        }
      },
      {
        key: "description",
        label: "Description",
        width: "24rem",
        sortable: false,
        render: (dashboard) => dashboard.description !== void 0 && dashboard.description.length > 0 ? dashboard.description : "\u2014"
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
    const message = create_message_for_status(status);
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
};
var PycDashboardDetail = class extends HTMLElement {
  _projects;
  _dashboard;
  _loading;
  _errored;
  _root;
  _tiles_region;
  constructor() {
    super();
    this._projects = [];
    this._dashboard = null;
    this._loading = false;
    this._errored = false;
    this._root = null;
    this._tiles_region = null;
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
    back.textContent = "\u2190 All dashboards";
    root.appendChild(back);
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
    let project_id = "";
    try {
      const response = await fetch(PROJECTS_API_PATH2, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        this._projects = extract_projects(body);
        if (this._projects.length > 0) {
          project_id = this._projects[0].project_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (project_id.length === 0) {
      this._errored = true;
      this._render_tiles();
      return;
    }
    this._loading = true;
    this._render_tiles();
    let dashboard = null;
    let errored = false;
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
      }
    } catch (reason) {
      errored = true;
      console.warn(
        "pychestrate.ui.metrics.dashboard_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._loading = false;
    this._errored = errored;
    this._dashboard = dashboard;
    this._render_tiles();
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
      notice.textContent = "Failed to load this dashboard.";
      region.appendChild(notice);
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
    title.textContent = metric_name.length > 0 ? metric_name : tile.kind;
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
      void this._load_tile_metric(metric_name, body);
    }
    return card;
  }
  async _load_tile_metric(metric_name, body) {
    let points = [];
    let errored = false;
    try {
      const url = build_timeseries_url(metric_name, "7d", /* @__PURE__ */ new Date());
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
    body.appendChild(build_chart_element(points, metric_name));
    return;
  }
};
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-metrics-bundle/slos-view.js
var PROJECTS_API_PATH3 = "/api/v1/projects";
function build_slos_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH3 + "/" + encodeURIComponent(project_id) + "/slos";
  return rtnval;
}
function build_slo_detail_url(project_id, slo_id) {
  const rtnval = PROJECTS_API_PATH3 + "/" + encodeURIComponent(project_id) + "/slos/" + encodeURIComponent(slo_id);
  return rtnval;
}
function format_ratio(value) {
  if (value === null || value === void 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  if (typeof value !== "number" || Number.isNaN(value) === true) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const percent = value * 100;
  const rtnval = percent.toFixed(1) + "%";
  return rtnval;
}
function format_window(seconds) {
  if (typeof seconds !== "number" || seconds <= 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const day = 86400;
  const hour = 3600;
  const minute = 60;
  if (seconds % day === 0) {
    const rtnval2 = String(seconds / day) + "d";
    return rtnval2;
  }
  if (seconds % hour === 0) {
    const rtnval2 = String(seconds / hour) + "h";
    return rtnval2;
  }
  if (seconds % minute === 0) {
    const rtnval2 = String(seconds / minute) + "m";
    return rtnval2;
  }
  const rtnval = String(seconds) + "s";
  return rtnval;
}
function slo_status_tone(status) {
  if (status === null) {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  if (status.breaching === true) {
    const rtnval2 = "error";
    return rtnval2;
  }
  const remaining = status.error_budget_remaining_ratio;
  if (typeof remaining === "number" && remaining < 0.25) {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "ok";
  return rtnval;
}
function slo_status_label(status) {
  if (status === null) {
    const rtnval2 = "Not evaluated";
    return rtnval2;
  }
  if (status.breaching === true) {
    const rtnval2 = "Breaching";
    return rtnval2;
  }
  const rtnval = format_ratio(status.achieved_ratio) + " achieved";
  return rtnval;
}
function slo_create_message_for_status(status) {
  if (status === 201 || status === 200) {
    const rtnval2 = "SLO created.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "An SLO with that name already exists.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The SLO definition was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to create SLOs.";
    return rtnval2;
  }
  const rtnval = "Failed to create SLO (HTTP " + String(status) + ").";
  return rtnval;
}
function parse_definition_config(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = {};
    return rtnval2;
  }
  const parsed = JSON.parse(raw);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
    throw new SyntaxError("SLO definition_config must be a JSON object");
  }
  const rtnval = parsed;
  return rtnval;
}
function extract_slo_projects(body) {
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
var PycSlos = class extends HTMLElement {
  _state;
  _slos;
  _status;
  _projects;
  _projectsAvailable;
  _root;
  _table_region;
  _create_region;
  _toast_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      loading: false,
      errored: false,
      total: 0
    };
    this._slos = [];
    this._status = /* @__PURE__ */ new Map();
    this._projects = [];
    this._projectsAvailable = false;
    this._root = null;
    this._table_region = null;
    this._create_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + list state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
      loading: this._state.loading,
      errored: this._state.errored,
      total: this._state.total
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
   * create action, table region, toast region.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.textContent = "Service-Level Objectives";
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
    const create_button = document.createElement("mj-button");
    create_button.classList.add("pyc-metrics__button");
    create_button.setAttribute("type", "button");
    create_button.setAttribute("data-role", "create-toggle");
    create_button.textContent = "Create SLO";
    create_button.addEventListener("click", () => {
      this._toggle_create_form();
    });
    controls.appendChild(create_button);
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
    const create_region = document.createElement("div");
    create_region.classList.add("pyc-metrics__form-region");
    create_region.setAttribute("data-role", "create-region");
    create_region.hidden = true;
    root.appendChild(create_region);
    this._create_region = create_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-metrics__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
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
    try {
      const response = await fetch(PROJECTS_API_PATH3, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        projects = extract_slo_projects(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.slo_projects_fetch_failed",
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
      this._render_table_region();
    }
    return;
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
   * Fetch the SLO list for the active project and re-render the
   * table. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._slos = [];
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._status = /* @__PURE__ */ new Map();
    this._render_table_region();
    const url = build_slos_collection_url(this._state.projectId);
    let page = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "slos fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.slos_fetch_failed",
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
    this._slos = page.items;
    const meta = page.meta;
    if (meta !== void 0 && meta !== null) {
      if (typeof meta.total === "number") {
        this._state.total = meta.total;
      }
    }
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
    return;
  }
  /**
   * Re-render the table region from the current state + SLOs.
   */
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.projectId.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its SLOs.";
      region.replaceChildren(notice);
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-metrics__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading SLOs\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-metrics__notice",
        "pyc-metrics__notice--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load SLOs. Try refreshing.";
      region.replaceChildren(error);
      return;
    }
    if (this._slos.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-metrics__notice");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No SLOs defined for this project yet";
      region.replaceChildren(empty);
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    return;
  }
  /**
   * Build the SLOs ``<table>`` from the current list.
   */
  _build_table() {
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-metrics__table");
    table.setAttribute("data-role", "slos-table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-metrics__row";
    table.rowAttrs = (slo) => ({ "data-slo-id": slo.slo_id });
    table.columns = [
      {
        key: "name",
        label: "SLO",
        width: "16rem",
        render: (slo) => {
          const name = document.createElement("span");
          name.textContent = slo.name;
          name.title = slo.slo_id;
          return name;
        }
      },
      {
        key: "kind",
        label: "Kind",
        width: "10rem",
        render: (slo) => slo.kind
      },
      {
        key: "target",
        label: "Target",
        width: "8rem",
        render: (slo) => format_ratio(slo.target)
      },
      {
        key: "window",
        label: "Window",
        width: "8rem",
        render: (slo) => format_window(slo.window_seconds)
      },
      {
        key: "burn",
        label: "Burn-rate",
        width: "12rem",
        render: (slo) => {
          const burn_badge = document.createElement("mj-chip");
          burn_badge.classList.add("pyc-metrics__badge");
          burn_badge.setAttribute("data-role", "burn-indicator");
          const status = self._status.get(slo.slo_id) ?? null;
          burn_badge.setAttribute("data-tone", slo_status_tone(status));
          burn_badge.textContent = slo_status_label(status);
          return burn_badge;
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "12rem",
        sortable: false,
        render: (slo) => {
          const status_button = document.createElement("mj-button");
          status_button.classList.add("pyc-metrics__button");
          status_button.setAttribute("type", "button");
          status_button.setAttribute("data-role", "load-status");
          status_button.textContent = "Burn-rate Status";
          status_button.addEventListener("click", () => {
            status_button.toggleAttribute("disabled", true);
            void self._on_load_status(slo, status_button);
          });
          return status_button;
        }
      }
    ];
    table.rows = this._slos;
    return table;
  }
  /**
   * Run the "Burn-rate Status" action for one SLO -- read the
   * status block and update the indicator, surfacing a toast.
   *
   * @param slo The SLO to evaluate.
   * @param button The row action button, re-enabled on completion.
   */
  async _on_load_status(slo, button) {
    const outcome = await this._do_load_status(slo.slo_id);
    if (outcome.ok === true && outcome.sloStatus !== null) {
      this._status.set(slo.slo_id, outcome.sloStatus);
      this._render_burn_cell(slo.slo_id);
    }
    button.toggleAttribute("disabled", false);
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    return;
  }
  /**
   * Read one SLO's burn-rate status. Exposed so unit tests can
   * drive a status read without a row button.
   *
   * @param slo_id The SLO to read.
   *
   * @returns The status outcome.
   */
  async loadStatus(slo_id) {
    const rtnval = await this._do_load_status(slo_id);
    return rtnval;
  }
  async _do_load_status(slo_id) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        sloStatus: null,
        message: "Select a project before reading SLO status."
      };
      return rtnval2;
    }
    let status = 0;
    let slo_status = null;
    try {
      const url = build_slo_detail_url(
        this._state.projectId,
        slo_id
      );
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        const detail = body;
        if (detail !== null && detail.status !== void 0 && detail.status !== null) {
          slo_status = detail.status;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.slo_status_fetch_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        sloStatus: null,
        message: "Failed to reach the SLO service."
      };
      return rtnval2;
    }
    if (status === 200) {
      const message = slo_status !== null ? "Burn-rate status updated." : "This SLO has no burn-rate status yet.";
      const rtnval2 = {
        ok: true,
        status,
        sloStatus: slo_status,
        message
      };
      return rtnval2;
    }
    const rtnval = {
      ok: false,
      status,
      sloStatus: null,
      message: "Failed to read SLO status (HTTP " + String(status) + ")."
    };
    return rtnval;
  }
  /**
   * Refresh one SLO's burn-rate indicator cell from the cached
   * status.
   *
   * @param slo_id The SLO whose row to update.
   */
  _render_burn_cell(slo_id) {
    if (this._table_region === null) {
      return;
    }
    const table = this._table_region.querySelector(
      '[data-role="slos-table"]'
    );
    if (table === null) {
      return;
    }
    const root = table.shadowRoot !== null && table.shadowRoot !== void 0 ? table.shadowRoot : table;
    const selector = '.row[data-slo-id="' + slo_id + '"] [data-role="burn-indicator"]';
    const badge = root.querySelector(selector);
    if (badge instanceof HTMLElement === false) {
      return;
    }
    const el = badge;
    const status = this._status.get(slo_id) ?? null;
    el.setAttribute("data-tone", slo_status_tone(status));
    el.textContent = slo_status_label(status);
    return;
  }
  /**
   * Toggle the inline create-SLO form's visibility, rendering it
   * on first reveal.
   */
  _toggle_create_form() {
    if (this._create_region === null) {
      return;
    }
    const region = this._create_region;
    if (region.hidden === true) {
      this._render_create_form();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the create-SLO form into the create region.
   */
  _render_create_form() {
    if (this._create_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-metrics__form");
    form.setAttribute("data-role", "create-form");
    const name_input = this._build_text_field(
      form,
      "Name",
      "create-name",
      "checkout availability"
    );
    const kind_input = this._build_text_field(
      form,
      "Kind",
      "create-kind",
      "availability"
    );
    const target_input = this._build_text_field(
      form,
      "Target ratio (0..1)",
      "create-target",
      "0.995"
    );
    const window_input = this._build_text_field(
      form,
      "Window (seconds)",
      "create-window",
      "604800"
    );
    const config_label = document.createElement("label");
    config_label.classList.add("pyc-metrics__field");
    config_label.textContent = "Definition config (JSON)";
    const config_area = document.createElement("mj-textarea");
    config_area.classList.add("pyc-metrics__input");
    config_area.setAttribute("data-role", "create-config");
    config_area.setAttribute("placeholder", '{"metric": "http_2xx"}');
    config_area.rows = 3;
    config_label.appendChild(config_area);
    form.appendChild(config_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-metrics__button");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "create-submit");
    submit_button.textContent = "Create SLO";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-metrics__form-status");
    status.setAttribute("data-role", "create-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_create(
        form,
        name_input,
        kind_input,
        target_input,
        window_input,
        config_area,
        submit_button
      );
    });
    this._create_region.replaceChildren(form);
    return;
  }
  /**
   * Build a labelled text input, append it to the supplied form,
   * and return the input element.
   *
   * @param form The form to append the field to.
   * @param label_text The visible field label.
   * @param role The ``data-role`` value for test selection.
   * @param placeholder The input placeholder text.
   *
   * @returns The created input element.
   */
  _build_text_field(form, label_text, role, placeholder) {
    const label = document.createElement("label");
    label.classList.add("pyc-metrics__field");
    label.textContent = label_text;
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-metrics__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", role);
    input.setAttribute("placeholder", placeholder);
    label.appendChild(input);
    form.appendChild(label);
    return input;
  }
  async _submit_create(form, name_input, kind_input, target_input, window_input, config_area, submit_button) {
    const status = form.querySelector('[data-role="create-status"]');
    const name = name_input.value.trim();
    const kind = kind_input.value.trim();
    if (name.length === 0 || kind.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "SLO name and kind are required.";
      }
      return;
    }
    const target = Number(target_input.value.trim());
    if (Number.isNaN(target) === true) {
      if (status instanceof HTMLElement) {
        status.textContent = "Target ratio must be a number.";
      }
      return;
    }
    const window_seconds = Number(window_input.value.trim());
    if (Number.isNaN(window_seconds) === true || window_seconds <= 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Window seconds must be a positive number.";
      }
      return;
    }
    let definition_config = {};
    try {
      definition_config = parse_definition_config(config_area.value);
    } catch (reason) {
      if (status instanceof HTMLElement) {
        status.textContent = "Definition config must be valid JSON.";
      }
      console.warn(
        "pychestrate.ui.metrics.slo_config_invalid",
        { reason: String(reason) }
      );
      return;
    }
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Creating SLO\u2026";
    }
    const outcome = await this._do_create(
      name,
      kind,
      target,
      window_seconds,
      definition_config
    );
    submit_button.toggleAttribute("disabled", false);
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * POST an ``SloCreateRequest``. Exposed so unit tests can
   * invoke a create without a real form-submit event.
   *
   * @param name Human-facing SLO name.
   * @param kind SLO kind (e.g. ``availability``).
   * @param target Target ratio in the 0..1 range.
   * @param window_seconds Rolling evaluation window length.
   * @param definition_config Kind-specific configuration object.
   *
   * @returns The create outcome.
   */
  async createSlo(name, kind, target, window_seconds, definition_config) {
    const rtnval = await this._do_create(
      name,
      kind,
      target,
      window_seconds,
      definition_config
    );
    return rtnval;
  }
  async _do_create(name, kind, target, window_seconds, definition_config) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        sloId: "",
        message: "Select a project before creating an SLO."
      };
      return rtnval2;
    }
    const payload = {
      name,
      kind,
      target,
      window_seconds,
      definition_config
    };
    let status = 0;
    let slo_id = "";
    try {
      const url = build_slos_collection_url(this._state.projectId);
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
        const slo = body;
        if (slo !== null && typeof slo.slo_id === "string") {
          slo_id = slo.slo_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.slo_create_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        sloId: "",
        message: "Failed to reach the SLO service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      sloId: slo_id,
      message: slo_create_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Render a dismissible toast in the toast region.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-metrics__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-metrics__toast-dismiss");
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
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-metrics-bundle/alert-rules-view.js
var PROJECTS_API_PATH4 = "/api/v1/projects";
var ALERT_RULES_ROUTE = "/metric-alerts";
var ALERT_RULE_KIND = "threshold";
var COMPARISON_OPTIONS = [
  { value: "gt", label: "greater than" },
  { value: "gte", label: "greater than or equal" },
  { value: "lt", label: "less than" },
  { value: "lte", label: "less than or equal" },
  { value: "eq", label: "equal to" }
];
var SEVERITY_OPTIONS = [
  "info",
  "warning",
  "critical"
];
function build_alert_rules_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH4 + "/" + encodeURIComponent(project_id) + ALERT_RULES_ROUTE;
  return rtnval;
}
function alert_create_message_for_status(status) {
  if (status === 201 || status === 200) {
    const rtnval2 = "Alert rule created.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "An alert rule with that name already exists.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The alert-rule definition was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to create alert rules.";
    return rtnval2;
  }
  const rtnval = "Failed to create alert rule (HTTP " + String(status) + ").";
  return rtnval;
}
function comparison_label(value) {
  for (const option of COMPARISON_OPTIONS) {
    if (option.value === value) {
      const rtnval2 = option.label;
      return rtnval2;
    }
  }
  const rtnval = value;
  return rtnval;
}
function describe_alert_condition(rule) {
  const config = rule.config;
  if (config === null || config === void 0 || typeof config !== "object") {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const record = config;
  const metric = typeof record.metric === "string" ? record.metric : "";
  const comparison = typeof record.comparison === "string" ? record.comparison : "";
  const threshold = record.threshold;
  if (metric.length === 0 || comparison.length === 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  if (typeof threshold !== "number") {
    const rtnval2 = metric + " " + comparison_label(comparison);
    return rtnval2;
  }
  const rtnval = metric + " " + comparison_label(comparison) + " " + String(threshold);
  return rtnval;
}
function format_alert_window(seconds) {
  if (typeof seconds !== "number" || seconds <= 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const day = 86400;
  const hour = 3600;
  const minute = 60;
  if (seconds % day === 0) {
    const rtnval2 = String(seconds / day) + "d";
    return rtnval2;
  }
  if (seconds % hour === 0) {
    const rtnval2 = String(seconds / hour) + "h";
    return rtnval2;
  }
  if (seconds % minute === 0) {
    const rtnval2 = String(seconds / minute) + "m";
    return rtnval2;
  }
  const rtnval = String(seconds) + "s";
  return rtnval;
}
function parse_notification_targets(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = [];
    return rtnval2;
  }
  const pieces = raw.split(",");
  const rtnval = [];
  for (const piece of pieces) {
    const trimmed = piece.trim();
    if (trimmed.length > 0) {
      rtnval.push(trimmed);
    }
  }
  return rtnval;
}
function extract_alert_rules(body) {
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
    const rule_id = record.rule_id;
    if (typeof rule_id !== "string" || rule_id.length === 0) {
      continue;
    }
    let config = {};
    if (record.config !== null && typeof record.config === "object" && Array.isArray(record.config) === false) {
      config = record.config;
    }
    let targets = [];
    if (Array.isArray(record.notification_targets) === true) {
      targets = record.notification_targets.filter(
        (value) => typeof value === "string"
      );
    }
    const rule = {
      rule_id,
      project_id: typeof record.project_id === "string" ? record.project_id : "",
      name: typeof record.name === "string" ? record.name : "",
      kind: typeof record.kind === "string" ? record.kind : "",
      config,
      severity: typeof record.severity === "string" ? record.severity : "warning",
      enabled: record.enabled === true,
      notification_targets: targets
    };
    if (typeof record.description === "string") {
      rule.description = record.description;
    }
    rtnval.push(rule);
  }
  return rtnval;
}
var PycAlertRules = class extends HTMLElement {
  _state;
  _rules;
  _catalog;
  _projects;
  _projectsAvailable;
  _root;
  _table_region;
  _create_region;
  _toast_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      loading: false,
      errored: false,
      total: 0
    };
    this._rules = [];
    this._catalog = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._root = null;
    this._table_region = null;
    this._create_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + list state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
      loading: this._state.loading,
      errored: this._state.errored,
      total: this._state.total
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * project + catalog fetches when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_catalog();
    void this._load_projects();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.textContent = "Metric Alert Rules";
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
    const create_button = document.createElement("mj-button");
    create_button.classList.add("pyc-metrics__button");
    create_button.setAttribute("type", "button");
    create_button.setAttribute("data-role", "create-toggle");
    create_button.textContent = "Create Alert Rule";
    create_button.addEventListener("click", () => {
      this._toggle_create_form();
    });
    controls.appendChild(create_button);
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
    const create_region = document.createElement("div");
    create_region.classList.add("pyc-metrics__form-region");
    create_region.setAttribute("data-role", "create-region");
    create_region.hidden = true;
    root.appendChild(create_region);
    this._create_region = create_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-metrics__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
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
   * Fetch the metric catalog so the create form can offer a
   * metric picker. Exposed so unit tests can await the fetch.
   */
  async loadCatalog() {
    await this._load_catalog();
    return;
  }
  async _load_catalog() {
    let catalog = [];
    try {
      const response = await fetch(build_catalog_url(), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        catalog = extract_catalog(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.alert_catalog_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._catalog = catalog;
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
      const response = await fetch(PROJECTS_API_PATH4, {
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
        "pychestrate.ui.metrics.alert_projects_fetch_failed",
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
      this._render_table_region();
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
   * Re-fetch the alert-rules page for the active project and
   * re-render. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._rules = [];
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._render_table_region();
    const url = build_alert_rules_collection_url(this._state.projectId);
    let rules = [];
    let errored = false;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        rules = extract_alert_rules(body);
      } else {
        errored = true;
      }
    } catch (reason) {
      errored = true;
      console.warn(
        "pychestrate.ui.metrics.alert_rules_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._state.loading = false;
    this._state.errored = errored;
    this._rules = rules;
    this._state.total = rules.length;
    this._render_table_region();
    return;
  }
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.projectId.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its alert rules.";
      region.replaceChildren(notice);
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-metrics__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading alert rules\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-metrics__notice",
        "pyc-metrics__notice--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load alert rules. Try refreshing.";
      region.replaceChildren(error);
      return;
    }
    if (this._rules.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-metrics__notice");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No alert rules defined for this project yet \u2014 create one above.";
      region.replaceChildren(empty);
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    return;
  }
  _build_table() {
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-metrics__table");
    table.setAttribute("data-role", "alert-rules-table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-metrics__row";
    table.rowAttrs = (rule) => ({ "data-rule-id": rule.rule_id });
    table.columns = [
      {
        key: "name",
        label: "Rule",
        width: "16rem",
        render: (rule) => {
          const name = document.createElement("span");
          name.textContent = rule.name;
          name.title = rule.rule_id;
          return name;
        }
      },
      {
        key: "condition",
        label: "Condition",
        width: "18rem",
        sortable: false,
        render: (rule) => describe_alert_condition(rule)
      },
      {
        key: "window",
        label: "Window",
        width: "8rem",
        render: (rule) => {
          const window_value = rule.config.window_seconds;
          const rtnval = typeof window_value === "number" ? format_alert_window(window_value) : "\u2014";
          return rtnval;
        }
      },
      {
        key: "severity",
        label: "Severity",
        width: "10rem",
        render: (rule) => {
          const severity_badge = document.createElement("mj-chip");
          severity_badge.classList.add("pyc-metrics__badge");
          severity_badge.setAttribute("data-role", "severity-badge");
          severity_badge.setAttribute(
            "data-tone",
            self._severity_tone(rule.severity)
          );
          severity_badge.textContent = rule.severity;
          return severity_badge;
        }
      },
      {
        key: "targets",
        label: "Targets",
        width: "16rem",
        sortable: false,
        render: (rule) => rule.notification_targets.length > 0 ? rule.notification_targets.join(", ") : "\u2014"
      },
      {
        key: "enabled",
        label: "Enabled",
        width: "8rem",
        render: (rule) => {
          const enabled_badge = document.createElement("mj-chip");
          enabled_badge.classList.add("pyc-metrics__badge");
          enabled_badge.setAttribute("data-role", "enabled-badge");
          enabled_badge.setAttribute(
            "data-tone",
            rule.enabled === true ? "ok" : "neutral"
          );
          enabled_badge.textContent = rule.enabled === true ? "Enabled" : "Disabled";
          return enabled_badge;
        }
      }
    ];
    table.rows = this._rules;
    return table;
  }
  _severity_tone(severity) {
    if (severity === "critical") {
      const rtnval2 = "error";
      return rtnval2;
    }
    if (severity === "warning") {
      const rtnval2 = "warn";
      return rtnval2;
    }
    const rtnval = "neutral";
    return rtnval;
  }
  _toggle_create_form() {
    if (this._create_region === null) {
      return;
    }
    const region = this._create_region;
    if (region.hidden === true) {
      this._render_create_form();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  _render_create_form() {
    if (this._create_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-metrics__form");
    form.setAttribute("data-role", "create-form");
    const name_input = this._build_text_field(
      form,
      "Name",
      "create-name",
      "checkout error rate"
    );
    const metric_label = document.createElement("label");
    metric_label.classList.add("pyc-metrics__field");
    metric_label.textContent = "Metric";
    const metric_select = document.createElement("mj-select");
    metric_select.classList.add("pyc-metrics__select");
    metric_select.setAttribute("data-role", "create-metric");
    if (this._catalog.length === 0) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", "");
      option.textContent = "No metrics in catalog";
      metric_select.appendChild(option);
    } else {
      for (const entry of this._catalog) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", entry.name);
        option.textContent = entry.name;
        metric_select.appendChild(option);
      }
    }
    metric_label.appendChild(metric_select);
    form.appendChild(metric_label);
    const comparison_label_el = document.createElement("label");
    comparison_label_el.classList.add("pyc-metrics__field");
    comparison_label_el.textContent = "Comparison";
    const comparison_select = document.createElement("mj-select");
    comparison_select.classList.add("pyc-metrics__select");
    comparison_select.setAttribute("data-role", "create-comparison");
    for (const option of COMPARISON_OPTIONS) {
      const opt = document.createElement("mj-option");
      opt.setAttribute("value", option.value);
      opt.textContent = option.label;
      comparison_select.appendChild(opt);
    }
    comparison_label_el.appendChild(comparison_select);
    form.appendChild(comparison_label_el);
    const threshold_input = this._build_text_field(
      form,
      "Threshold",
      "create-threshold",
      "0.95"
    );
    const window_input = this._build_text_field(
      form,
      "Window (seconds)",
      "create-window",
      "300"
    );
    const severity_label = document.createElement("label");
    severity_label.classList.add("pyc-metrics__field");
    severity_label.textContent = "Severity";
    const severity_select = document.createElement("mj-select");
    severity_select.classList.add("pyc-metrics__select");
    severity_select.setAttribute("data-role", "create-severity");
    for (const severity of SEVERITY_OPTIONS) {
      const opt = document.createElement("mj-option");
      opt.setAttribute("value", severity);
      opt.textContent = severity;
      severity_select.appendChild(opt);
    }
    severity_select.value = "warning";
    severity_label.appendChild(severity_select);
    form.appendChild(severity_label);
    const targets_input = this._build_text_field(
      form,
      "Notification targets (comma-separated)",
      "create-targets",
      "ops-pager, slack:#alerts"
    );
    const enabled_label = document.createElement("label");
    enabled_label.classList.add("pyc-metrics__field");
    enabled_label.classList.add("pyc-metrics__field--inline");
    const enabled_checkbox = document.createElement("input");
    enabled_checkbox.setAttribute("type", "checkbox");
    enabled_checkbox.setAttribute("data-role", "create-enabled");
    enabled_checkbox.checked = true;
    enabled_label.appendChild(enabled_checkbox);
    const enabled_text = document.createElement("span");
    enabled_text.textContent = "Enabled";
    enabled_label.appendChild(enabled_text);
    form.appendChild(enabled_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-metrics__button");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "create-submit");
    submit_button.textContent = "Create Alert Rule";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-metrics__form-status");
    status.setAttribute("data-role", "create-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_create(
        form,
        name_input,
        metric_select,
        comparison_select,
        threshold_input,
        window_input,
        severity_select,
        targets_input,
        enabled_checkbox,
        submit_button
      );
    });
    this._create_region.replaceChildren(form);
    return;
  }
  _build_text_field(form, label_text, role, placeholder) {
    const label = document.createElement("label");
    label.classList.add("pyc-metrics__field");
    label.textContent = label_text;
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-metrics__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", role);
    input.setAttribute("placeholder", placeholder);
    label.appendChild(input);
    form.appendChild(label);
    return input;
  }
  async _submit_create(form, name_input, metric_select, comparison_select, threshold_input, window_input, severity_select, targets_input, enabled_checkbox, submit_button) {
    const status = form.querySelector('[data-role="create-status"]');
    const name = name_input.value.trim();
    const metric = metric_select.value.trim();
    if (name.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "An alert-rule name is required.";
      }
      return;
    }
    if (metric.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "A metric must be selected.";
      }
      return;
    }
    const threshold = Number(threshold_input.value.trim());
    if (Number.isNaN(threshold) === true) {
      if (status instanceof HTMLElement) {
        status.textContent = "Threshold must be a number.";
      }
      return;
    }
    const window_seconds = Number(window_input.value.trim());
    if (Number.isNaN(window_seconds) === true || window_seconds <= 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Window seconds must be a positive number.";
      }
      return;
    }
    const config = {
      metric,
      comparison: comparison_select.value,
      threshold,
      window_seconds
    };
    const targets = parse_notification_targets(targets_input.value);
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Creating alert rule\u2026";
    }
    const outcome = await this._do_create(
      name,
      config,
      severity_select.value,
      enabled_checkbox.checked,
      targets
    );
    submit_button.toggleAttribute("disabled", false);
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      this._toggle_create_form();
      await this._refresh();
    }
    return;
  }
  /**
   * POST a ``MetricAlertRule`` create request. Exposed so unit
   * tests can invoke a create without a real form-submit event.
   *
   * @param name Human-facing alert-rule name.
   * @param config Threshold config (metric, comparison,
   *               threshold, window_seconds).
   * @param severity Severity level (``info`` / ``warning`` /
   *                  ``critical``).
   * @param enabled Whether the rule is enabled at creation.
   * @param notification_targets Notification target list.
   *
   * @returns The create outcome.
   */
  async createAlertRule(name, config, severity, enabled, notification_targets) {
    const rtnval = await this._do_create(
      name,
      config,
      severity,
      enabled,
      notification_targets
    );
    return rtnval;
  }
  async _do_create(name, config, severity, enabled, notification_targets) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        ruleId: "",
        message: "Select a project before creating an alert rule."
      };
      return rtnval2;
    }
    const payload = {
      name,
      kind: ALERT_RULE_KIND,
      config: {
        metric: config.metric,
        comparison: config.comparison,
        threshold: config.threshold,
        window_seconds: config.window_seconds
      },
      severity,
      enabled,
      notification_targets
    };
    let status = 0;
    let rule_id = "";
    try {
      const url = build_alert_rules_collection_url(
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
      if (response.ok === true) {
        const body = await response.json();
        const record = body;
        if (typeof record.rule_id === "string") {
          rule_id = record.rule_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.alert_rule_create_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        ruleId: "",
        message: "Failed to reach the alert-rules service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      ruleId: rule_id,
      message: alert_create_message_for_status(status)
    };
    return rtnval;
  }
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-metrics__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-metrics__toast-dismiss");
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
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-metrics-bundle/dashboard-editor-view.js
var PROJECTS_API_PATH5 = "/api/v1/projects";
var TILE_KIND_OPTIONS = [
  { value: "line", label: "Line chart" },
  { value: "bar", label: "Bar chart" },
  { value: "number", label: "Single number" }
];
function dashboard_id_from_edit_path(path) {
  if (typeof path !== "string") {
    const rtnval2 = "";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  const prefix = DASHBOARDS_ROUTE + "/";
  const suffix = "/edit";
  if (working.startsWith(prefix) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  if (working.endsWith(suffix) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  const middle = working.slice(prefix.length, working.length - suffix.length);
  if (middle.length === 0 || middle.indexOf("/") >= 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = decodeURIComponent(middle);
  return rtnval;
}
function is_dashboard_edit_path(path) {
  const rtnval = dashboard_id_from_edit_path(path).length > 0;
  return rtnval;
}
function generate_tile_id() {
  const stamp = Date.now().toString(36);
  const rand = Math.floor(Math.random() * 1e6).toString(36);
  const rtnval = "tile-" + stamp + "-" + rand;
  return rtnval;
}
function build_tile(metric, kind, index) {
  const rtnval = {
    tile_id: generate_tile_id(),
    kind,
    x: 0,
    y: index,
    w: 1,
    h: 1,
    config: { metric }
  };
  return rtnval;
}
function add_tile(tiles, metric, kind) {
  const rtnval = tiles.slice();
  rtnval.push(build_tile(metric, kind, rtnval.length));
  return reindex_tiles(rtnval);
}
function remove_tile(tiles, tile_id) {
  const filtered = [];
  for (const tile of tiles) {
    if (tile.tile_id !== tile_id) {
      filtered.push(tile);
    }
  }
  const rtnval = reindex_tiles(filtered);
  return rtnval;
}
function move_tile_up(tiles, index) {
  const working = tiles.slice();
  if (index <= 0 || index >= working.length) {
    const rtnval2 = reindex_tiles(working);
    return rtnval2;
  }
  const above = working[index - 1];
  const current = working[index];
  working[index - 1] = current;
  working[index] = above;
  const rtnval = reindex_tiles(working);
  return rtnval;
}
function move_tile_down(tiles, index) {
  const working = tiles.slice();
  if (index < 0 || index >= working.length - 1) {
    const rtnval2 = reindex_tiles(working);
    return rtnval2;
  }
  const below = working[index + 1];
  const current = working[index];
  working[index + 1] = current;
  working[index] = below;
  const rtnval = reindex_tiles(working);
  return rtnval;
}
function reindex_tiles(tiles) {
  const rtnval = [];
  let index = 0;
  for (const tile of tiles) {
    const next = {
      tile_id: tile.tile_id,
      kind: tile.kind,
      x: 0,
      y: index,
      w: tile.w,
      h: tile.h
    };
    if (tile.config !== void 0) {
      next.config = tile.config;
    }
    rtnval.push(next);
    index = index + 1;
  }
  return rtnval;
}
function editor_tile_metric(tile) {
  if (tile === null || tile === void 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const config = tile.config;
  if (config === null || config === void 0 || typeof config !== "object") {
    const rtnval2 = "";
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
function build_save_payload(dashboard, tiles) {
  const reindexed = reindex_tiles(tiles);
  const tile_payload = [];
  for (const tile of reindexed) {
    const entry = {
      tile_id: tile.tile_id,
      kind: tile.kind,
      x: tile.x,
      y: tile.y,
      w: tile.w,
      h: tile.h,
      config: tile.config !== void 0 ? tile.config : {}
    };
    tile_payload.push(entry);
  }
  const rtnval = {
    name: dashboard.name + " (edited)",
    tiles: tile_payload
  };
  if (dashboard.description !== void 0 && dashboard.description.length > 0) {
    rtnval.description = dashboard.description;
  }
  if (typeof dashboard.grid_columns_max === "number") {
    rtnval.grid_columns_max = dashboard.grid_columns_max;
  }
  return rtnval;
}
function save_message_for_status(status) {
  if (status === 201 || status === 200) {
    const rtnval2 = "Layout saved as a new dashboard (the dashboards API has no in-place update).";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "A dashboard with the edited name already exists \u2014 rename and retry.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The layout was rejected \u2014 check the tiles.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to save dashboards.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project.";
    return rtnval2;
  }
  const rtnval = "Failed to save layout (HTTP " + String(status) + ").";
  return rtnval;
}
var PycDashboardEditor = class extends HTMLElement {
  _projects;
  _projectId;
  _dashboard;
  _tiles;
  _catalog;
  _loading;
  _errored;
  _root;
  _grid_region;
  _add_region;
  _toast_region;
  constructor() {
    super();
    this._projects = [];
    this._projectId = "";
    this._dashboard = null;
    this._tiles = [];
    this._catalog = [];
    this._loading = false;
    this._errored = false;
    this._root = null;
    this._grid_region = null;
    this._add_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests -- the current tile
   * list (a defensive copy).
   */
  get tiles() {
    const rtnval = this._tiles.slice();
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests -- ``true`` once the
   * dashboard has loaded.
   */
  get loaded() {
    const rtnval = this._dashboard !== null;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the chrome, fetch the catalog and
   * the dashboard.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_catalog();
    void this._load_dashboard();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.setAttribute("data-role", "editor-heading");
    heading.textContent = "Edit Dashboard Layout";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-metrics__row-link");
    back.setAttribute("data-role", "back-link");
    back.setAttribute("href", DASHBOARDS_ROUTE);
    back.textContent = "\u2190 All dashboards";
    root.appendChild(back);
    const add_region = document.createElement("div");
    add_region.classList.add("pyc-metrics__form-region");
    add_region.setAttribute("data-role", "add-region");
    root.appendChild(add_region);
    this._add_region = add_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-metrics__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const grid_region = document.createElement("div");
    grid_region.classList.add("pyc-metrics__tiles-region");
    grid_region.setAttribute("data-role", "grid-region");
    root.appendChild(grid_region);
    this._grid_region = grid_region;
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the metric catalog so the add-tile form can offer a
   * metric picker. Exposed so unit tests can await the fetch.
   */
  async loadCatalog() {
    await this._load_catalog();
    return;
  }
  async _load_catalog() {
    let catalog = [];
    try {
      const response = await fetch(build_catalog_url(), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        catalog = extract_catalog(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.editor_catalog_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._catalog = catalog;
    this._render_add_region();
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
    const dashboard_id = dashboard_id_from_edit_path(
      typeof window !== "undefined" ? window.location.pathname : ""
    );
    if (dashboard_id.length === 0) {
      this._errored = true;
      this._render_grid();
      return;
    }
    let project_id = "";
    try {
      const response = await fetch(PROJECTS_API_PATH5, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        this._projects = extract_projects(body);
        if (this._projects.length > 0) {
          project_id = this._projects[0].project_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.editor_projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (project_id.length === 0) {
      this._errored = true;
      this._render_grid();
      return;
    }
    this._projectId = project_id;
    this._loading = true;
    this._render_grid();
    let dashboard = null;
    let errored = false;
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
      }
    } catch (reason) {
      errored = true;
      console.warn(
        "pychestrate.ui.metrics.editor_dashboard_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._loading = false;
    this._errored = errored;
    this._dashboard = dashboard;
    if (dashboard !== null && Array.isArray(dashboard.tiles) === true) {
      this._tiles = reindex_tiles(dashboard.tiles);
    } else {
      this._tiles = [];
    }
    this._render_grid();
    this._render_add_region();
    return;
  }
  /**
   * Append a tile referencing ``metric`` with ``kind``. Exposed
   * so unit tests can drive the add path directly.
   *
   * @param metric The metric the new tile renders.
   * @param kind The new tile's kind.
   */
  addTile(metric, kind) {
    this._tiles = add_tile(this._tiles, metric, kind);
    this._render_grid();
    return;
  }
  /**
   * Remove the named tile. Exposed so unit tests can drive the
   * remove path directly.
   *
   * @param tile_id The tile to remove.
   */
  removeTile(tile_id) {
    this._tiles = remove_tile(this._tiles, tile_id);
    this._render_grid();
    return;
  }
  /**
   * Move the tile at ``index`` one slot earlier. Exposed so unit
   * tests can drive the reorder path directly.
   *
   * @param index The 0-based index of the tile to move up.
   */
  moveUp(index) {
    this._tiles = move_tile_up(this._tiles, index);
    this._render_grid();
    return;
  }
  /**
   * Move the tile at ``index`` one slot later. Exposed so unit
   * tests can drive the reorder path directly.
   *
   * @param index The 0-based index of the tile to move down.
   */
  moveDown(index) {
    this._tiles = move_tile_down(this._tiles, index);
    this._render_grid();
    return;
  }
  _render_add_region() {
    if (this._add_region === null) {
      return;
    }
    const region = this._add_region;
    region.replaceChildren();
    if (this._dashboard === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-metrics__form");
    form.setAttribute("data-role", "add-tile-form");
    const metric_label = document.createElement("label");
    metric_label.classList.add("pyc-metrics__field");
    metric_label.textContent = "Metric";
    const metric_select = document.createElement("mj-select");
    metric_select.classList.add("pyc-metrics__select");
    metric_select.setAttribute("data-role", "add-metric");
    if (this._catalog.length === 0) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", "");
      option.textContent = "No metrics in catalog";
      metric_select.appendChild(option);
    } else {
      for (const entry of this._catalog) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", entry.name);
        option.textContent = entry.name;
        metric_select.appendChild(option);
      }
    }
    metric_label.appendChild(metric_select);
    form.appendChild(metric_label);
    const kind_label = document.createElement("label");
    kind_label.classList.add("pyc-metrics__field");
    kind_label.textContent = "Tile kind";
    const kind_select = document.createElement("mj-select");
    kind_select.classList.add("pyc-metrics__select");
    kind_select.setAttribute("data-role", "add-kind");
    for (const option of TILE_KIND_OPTIONS) {
      const opt = document.createElement("mj-option");
      opt.setAttribute("value", option.value);
      opt.textContent = option.label;
      kind_select.appendChild(opt);
    }
    kind_label.appendChild(kind_select);
    form.appendChild(kind_label);
    const add_button = document.createElement("mj-button");
    add_button.classList.add("pyc-metrics__button");
    add_button.setAttribute("type", "submit");
    add_button.setAttribute("data-role", "add-tile");
    add_button.textContent = "Add Tile";
    form.appendChild(add_button);
    const save_button = document.createElement("mj-button");
    save_button.classList.add("pyc-metrics__button");
    save_button.setAttribute("type", "button");
    save_button.setAttribute("data-role", "save-layout");
    save_button.textContent = "Save Layout";
    save_button.addEventListener("click", () => {
      save_button.toggleAttribute("disabled", true);
      void this._on_save(save_button);
    });
    form.appendChild(save_button);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const metric = metric_select.value.trim();
      if (metric.length === 0) {
        this._show_toast("Select a metric to add a tile.", "error");
        return;
      }
      this.addTile(metric, kind_select.value);
    });
    region.appendChild(form);
    return;
  }
  _render_grid() {
    if (this._grid_region === null || this._root === null) {
      return;
    }
    const heading = this._root.querySelector(
      '[data-role="editor-heading"]'
    );
    if (heading !== null && this._dashboard !== null) {
      heading.textContent = "Edit Layout \u2014 " + this._dashboard.name;
    }
    const region = this._grid_region;
    region.replaceChildren();
    if (this._loading === true) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "loading-state");
      notice.textContent = "Loading dashboard\u2026";
      region.appendChild(notice);
      return;
    }
    if (this._errored === true || this._dashboard === null) {
      const notice = document.createElement("p");
      notice.classList.add(
        "pyc-metrics__notice",
        "pyc-metrics__notice--error"
      );
      notice.setAttribute("data-role", "error-state");
      notice.textContent = "Failed to load this dashboard.";
      region.appendChild(notice);
      return;
    }
    if (this._tiles.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "empty-state");
      notice.textContent = "No tiles yet \u2014 add one above.";
      region.appendChild(notice);
      return;
    }
    const grid = document.createElement("div");
    grid.classList.add("pyc-metrics__tiles");
    grid.setAttribute("data-role", "tiles-grid");
    let index = 0;
    for (const tile of this._tiles) {
      grid.appendChild(this._build_tile_card(tile, index));
      index = index + 1;
    }
    region.appendChild(grid);
    return;
  }
  _build_tile_card(tile, index) {
    const card = document.createElement("div");
    card.classList.add("pyc-metrics__tile");
    card.setAttribute("data-role", "editor-tile");
    card.setAttribute("data-tile-id", tile.tile_id);
    const title = document.createElement("div");
    title.classList.add("pyc-metrics__tile-title");
    const metric = editor_tile_metric(tile);
    title.textContent = (metric.length > 0 ? metric : "(no metric)") + " \xB7 " + tile.kind;
    card.appendChild(title);
    const actions = document.createElement("div");
    actions.classList.add("pyc-metrics__tile-actions");
    const up_button = document.createElement("mj-button");
    up_button.classList.add("pyc-metrics__button");
    up_button.setAttribute("type", "button");
    up_button.setAttribute("data-role", "tile-up");
    up_button.setAttribute("aria-label", "Move tile up");
    up_button.textContent = "\u2191";
    up_button.toggleAttribute("disabled", index === 0);
    up_button.addEventListener("click", () => {
      this.moveUp(index);
    });
    actions.appendChild(up_button);
    const down_button = document.createElement("mj-button");
    down_button.classList.add("pyc-metrics__button");
    down_button.setAttribute("type", "button");
    down_button.setAttribute("data-role", "tile-down");
    down_button.setAttribute("aria-label", "Move tile down");
    down_button.textContent = "\u2193";
    down_button.toggleAttribute("disabled", index === this._tiles.length - 1);
    down_button.addEventListener("click", () => {
      this.moveDown(index);
    });
    actions.appendChild(down_button);
    const remove_button = document.createElement("mj-button");
    remove_button.classList.add("pyc-metrics__button");
    remove_button.setAttribute("type", "button");
    remove_button.setAttribute("data-role", "tile-remove");
    remove_button.setAttribute("aria-label", "Remove tile");
    remove_button.textContent = "Remove";
    remove_button.addEventListener("click", () => {
      this.removeTile(tile.tile_id);
    });
    actions.appendChild(remove_button);
    card.appendChild(actions);
    return card;
  }
  async _on_save(button) {
    const outcome = await this._do_save();
    button.toggleAttribute("disabled", false);
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true && outcome.dashboardId.length > 0) {
      const link = document.createElement("a");
      link.classList.add("pyc-metrics__row-link");
      link.setAttribute(
        "href",
        DASHBOARDS_ROUTE + "/" + encodeURIComponent(outcome.dashboardId)
      );
      link.textContent = "Open the saved dashboard \u2192";
      if (this._toast_region !== null) {
        this._toast_region.appendChild(link);
      }
    }
    return;
  }
  /**
   * Save the current layout via a create-replace POST. Exposed
   * so unit tests can drive the save path directly.
   *
   * @returns The save outcome.
   */
  async saveLayout() {
    const rtnval = await this._do_save();
    return rtnval;
  }
  async _do_save() {
    if (this._dashboard === null || this._projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        dashboardId: "",
        message: "Load a dashboard before saving its layout."
      };
      return rtnval2;
    }
    const payload = build_save_payload(this._dashboard, this._tiles);
    let status = 0;
    let dashboard_id = "";
    try {
      const url = build_dashboards_collection_url(this._projectId);
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
        const record = body;
        if (typeof record.dashboard_id === "string") {
          dashboard_id = record.dashboard_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.dashboard_save_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        dashboardId: "",
        message: "Failed to reach the dashboards service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      dashboardId: dashboard_id,
      message: save_message_for_status(status)
    };
    return rtnval;
  }
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-metrics__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-metrics__toast-dismiss");
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
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-metrics-bundle/index.entry.js
var INSIGHTS_GROUP_ID = "insights";
var METRICS_READ_PERMISSION = "system:metrics.read";
var TEST_METRICS_ROUTE = "/test-metrics";
var TIMESERIES_ROUTE = "/timeseries";
var DASHBOARDS_ROUTE2 = "/dashboards";
var SLOS_ROUTE = "/slos";
var TEST_METRICS_TAG = "pyc-test-metrics";
var TIMESERIES_TAG = "pyc-timeseries-explorer";
var DASHBOARDS_LIST_TAG = "pyc-dashboards-list";
var DASHBOARD_DETAIL_TAG = "pyc-dashboard-detail";
var SLOS_TAG = "pyc-slos";
var SLOS_READ_PERMISSION = "system:slos.read";
var ALERT_RULES_TAG = "pyc-alert-rules";
var ALERT_RULES_READ_PERMISSION = "system:metric_alerts.read";
var DASHBOARD_EDITOR_TAG = "pyc-dashboard-editor";
var METRICS_STYLESHEET_HREF = "/static/javascript/pyc-metrics-bundle/pyc-metrics-bundle.css";
function ensure_metrics_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-metrics-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = METRICS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-metrics-bundle");
  document.head.appendChild(link);
  return;
}
var TEST_METRICS_ENTRY = {
  entryId: "insights.test-metrics",
  label: "Test Metrics",
  route: TEST_METRICS_ROUTE,
  requiredPermissions: [METRICS_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
var TIMESERIES_ENTRY = {
  entryId: "insights.timeseries",
  label: "Timeseries",
  route: TIMESERIES_ROUTE,
  requiredPermissions: [METRICS_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
var DASHBOARDS_ENTRY = {
  entryId: "insights.dashboards",
  label: "Dashboards",
  route: DASHBOARDS_ROUTE2,
  requiredPermissions: [METRICS_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
var SLOS_ENTRY = {
  entryId: "insights.slos",
  label: "SLOs",
  route: SLOS_ROUTE,
  requiredPermissions: [SLOS_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
var ALERT_RULES_ENTRY = {
  entryId: "insights.metric-alerts",
  label: "Alert Rules",
  route: ALERT_RULES_ROUTE,
  requiredPermissions: [ALERT_RULES_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
function register_metrics_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: INSIGHTS_GROUP_ID,
    label: "Insights",
    requiredPermissions: [METRICS_READ_PERMISSION]
  });
  sidebar.registerEntry(TEST_METRICS_ENTRY);
  sidebar.registerEntry(TIMESERIES_ENTRY);
  sidebar.registerEntry(DASHBOARDS_ENTRY);
  sidebar.registerEntry(SLOS_ENTRY);
  sidebar.registerEntry(ALERT_RULES_ENTRY);
  return;
}
function define_metrics_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(TEST_METRICS_TAG) === void 0) {
    customElements.define(TEST_METRICS_TAG, PycTestMetrics);
  }
  if (customElements.get(TIMESERIES_TAG) === void 0) {
    customElements.define(TIMESERIES_TAG, PycTimeseriesExplorer);
  }
  if (customElements.get(DASHBOARDS_LIST_TAG) === void 0) {
    customElements.define(DASHBOARDS_LIST_TAG, PycDashboardsList);
  }
  if (customElements.get(DASHBOARD_DETAIL_TAG) === void 0) {
    customElements.define(DASHBOARD_DETAIL_TAG, PycDashboardDetail);
  }
  if (customElements.get(SLOS_TAG) === void 0) {
    customElements.define(SLOS_TAG, PycSlos);
  }
  if (customElements.get(ALERT_RULES_TAG) === void 0) {
    customElements.define(ALERT_RULES_TAG, PycAlertRules);
  }
  if (customElements.get(DASHBOARD_EDITOR_TAG) === void 0) {
    customElements.define(DASHBOARD_EDITOR_TAG, PycDashboardEditor);
  }
  return;
}
function classify_metrics_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === TEST_METRICS_ROUTE || working === TEST_METRICS_ROUTE + "/") {
    const rtnval2 = "test-metrics";
    return rtnval2;
  }
  if (working === TIMESERIES_ROUTE || working === TIMESERIES_ROUTE + "/") {
    const rtnval2 = "timeseries";
    return rtnval2;
  }
  if (working === DASHBOARDS_ROUTE2 || working === DASHBOARDS_ROUTE2 + "/") {
    const rtnval2 = "dashboards-list";
    return rtnval2;
  }
  if (working === SLOS_ROUTE || working === SLOS_ROUTE + "/") {
    const rtnval2 = "slos";
    return rtnval2;
  }
  if (working === ALERT_RULES_ROUTE || working === ALERT_RULES_ROUTE + "/") {
    const rtnval2 = "metric-alerts";
    return rtnval2;
  }
  const editor_id = dashboard_id_from_edit_path(working);
  if (editor_id.length > 0) {
    const rtnval2 = "dashboard-editor";
    return rtnval2;
  }
  const detail_id = dashboard_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "dashboard-detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_metrics_route(route) {
  if (route === "test-metrics") {
    const rtnval2 = TEST_METRICS_TAG;
    return rtnval2;
  }
  if (route === "timeseries") {
    const rtnval2 = TIMESERIES_TAG;
    return rtnval2;
  }
  if (route === "dashboards-list") {
    const rtnval2 = DASHBOARDS_LIST_TAG;
    return rtnval2;
  }
  if (route === "dashboard-detail") {
    const rtnval2 = DASHBOARD_DETAIL_TAG;
    return rtnval2;
  }
  if (route === "slos") {
    const rtnval2 = SLOS_TAG;
    return rtnval2;
  }
  if (route === "metric-alerts") {
    const rtnval2 = ALERT_RULES_TAG;
    return rtnval2;
  }
  if (route === "dashboard-editor") {
    const rtnval2 = DASHBOARD_EDITOR_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_metrics_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_metrics_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_metrics_route(route);
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
  define_metrics_elements();
  ensure_metrics_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_metrics_view_if_active();
  return;
}
function _boot() {
  define_metrics_elements();
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
      "pychestrate.ui.metrics.bundle_no_shell_handle",
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
  ALERT_RULES_ROUTE,
  ALERT_RULE_KIND,
  COMPARISON_OPTIONS,
  DASHBOARDS_ROUTE,
  PycAlertRules,
  PycDashboardDetail,
  PycDashboardEditor,
  PycDashboardsList,
  PycSlos,
  PycTestMetrics,
  PycTimeseriesExplorer,
  SEVERITY_OPTIONS,
  TILE_KIND_OPTIONS,
  TIME_RANGE_PRESETS,
  add_tile,
  alert_create_message_for_status,
  build_alert_rules_collection_url,
  build_catalog_url,
  build_chart_element,
  build_dashboard_detail_url,
  build_dashboards_collection_url,
  build_save_payload,
  build_slo_detail_url,
  build_slos_collection_url,
  build_test_metrics_url,
  build_tile,
  build_timeseries_url,
  classify_metrics_route,
  comparison_label,
  compute_bar_fractions,
  create_message_for_status,
  dashboard_id_from_edit_path,
  dashboard_id_from_path,
  define_metrics_elements,
  describe_alert_condition,
  editor_tile_metric,
  ensure_metrics_stylesheet,
  extract_alert_rules,
  extract_catalog,
  extract_dashboards,
  extract_projects,
  extract_slo_projects,
  format_alert_window,
  format_duration,
  format_rate,
  format_ratio,
  format_window,
  generate_tile_id,
  is_dashboard_edit_path,
  mount_metrics_view_if_active,
  move_tile_down,
  move_tile_up,
  parse_definition_config,
  parse_notification_targets,
  register_metrics_sidebar,
  reindex_tiles,
  remove_tile,
  resolve_range_preset,
  save_message_for_status,
  short_metric_id,
  slo_create_message_for_status,
  slo_status_label,
  slo_status_tone,
  tag_for_metrics_route,
  tile_metric_name
};
