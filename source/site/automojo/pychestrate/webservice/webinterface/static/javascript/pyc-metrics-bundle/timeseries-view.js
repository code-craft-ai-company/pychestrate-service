const SVG_NS = "http://www.w3.org/2000/svg";
const METRICS_API_PATH = "/api/v1/metrics";
const CHART_WIDTH = 720;
const CHART_HEIGHT = 240;
const CHART_PADDING = 16;
const TIME_RANGE_PRESETS = [
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
function project_points(points) {
  const rtnval = [];
  if (Array.isArray(points) === false || points.length === 0) {
    return rtnval;
  }
  const sorted = points.slice().sort((left, right) => {
    const left_time = new Date(left.observed_at).getTime();
    const right_time = new Date(right.observed_at).getTime();
    const diff = left_time - right_time;
    return diff;
  });
  const plot_width = CHART_WIDTH - 2 * CHART_PADDING;
  const plot_height = CHART_HEIGHT - 2 * CHART_PADDING;
  let min_value = sorted[0].value;
  let max_value = sorted[0].value;
  for (const point of sorted) {
    if (point.value < min_value) {
      min_value = point.value;
    }
    if (point.value > max_value) {
      max_value = point.value;
    }
  }
  const value_span = max_value - min_value;
  const count = sorted.length;
  for (let index = 0; index < count; index = index + 1) {
    const point = sorted[index];
    let x_fraction = 0.5;
    if (count > 1) {
      x_fraction = index / (count - 1);
    }
    let y_fraction = 0.5;
    if (value_span > 0) {
      y_fraction = (point.value - min_value) / value_span;
    }
    const x = CHART_PADDING + x_fraction * plot_width;
    const y = CHART_PADDING + (1 - y_fraction) * plot_height;
    rtnval.push({ x, y });
  }
  return rtnval;
}
function build_line_path(coordinates) {
  if (Array.isArray(coordinates) === false || coordinates.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const segments = [];
  for (let index = 0; index < coordinates.length; index = index + 1) {
    const coord = coordinates[index];
    const command = index === 0 ? "M" : "L";
    const x_text = coord.x.toFixed(2);
    const y_text = coord.y.toFixed(2);
    segments.push(command + " " + x_text + " " + y_text);
  }
  const rtnval = segments.join(" ");
  return rtnval;
}
function build_area_path(coordinates) {
  if (Array.isArray(coordinates) === false || coordinates.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const floor_y = CHART_HEIGHT - CHART_PADDING;
  const first = coordinates[0];
  const last = coordinates[coordinates.length - 1];
  const line = build_line_path(coordinates);
  const close = " L " + last.x.toFixed(2) + " " + floor_y.toFixed(2) + " L " + first.x.toFixed(2) + " " + floor_y.toFixed(2) + " Z";
  const rtnval = line + close;
  return rtnval;
}
class PycTimeseriesExplorer extends HTMLElement {
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
    const svg = build_chart_svg(points);
    region.appendChild(svg);
    return;
  }
}
function build_chart_svg(points) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute(
    "viewBox",
    "0 0 " + String(CHART_WIDTH) + " " + String(CHART_HEIGHT)
  );
  svg.setAttribute("class", "pyc-metrics__chart");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("data-role", "timeseries-chart");
  const coordinates = project_points(points);
  if (coordinates.length === 0) {
    return svg;
  }
  const area = document.createElementNS(SVG_NS, "path");
  area.setAttribute("class", "pyc-metrics__chart-area");
  area.setAttribute("d", build_area_path(coordinates));
  svg.appendChild(area);
  const line = document.createElementNS(SVG_NS, "path");
  line.setAttribute("class", "pyc-metrics__chart-line");
  line.setAttribute("d", build_line_path(coordinates));
  svg.appendChild(line);
  return svg;
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
export {
  PycTimeseriesExplorer,
  TIME_RANGE_PRESETS,
  build_area_path,
  build_catalog_url,
  build_chart_svg,
  build_line_path,
  build_timeseries_url,
  extract_catalog,
  project_points,
  resolve_range_preset
};
