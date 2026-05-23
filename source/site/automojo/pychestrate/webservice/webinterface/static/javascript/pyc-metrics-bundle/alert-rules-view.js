import {
  build_catalog_url,
  extract_catalog
} from "./timeseries-view.js";
import {
  extract_projects
} from "./test-metrics-view.js";
const PROJECTS_API_PATH = "/api/v1/projects";
const ALERT_RULES_ROUTE = "/metric-alerts";
const ALERT_RULE_KIND = "threshold";
const COMPARISON_OPTIONS = [
  { value: "gt", label: "greater than" },
  { value: "gte", label: "greater than or equal" },
  { value: "lt", label: "less than" },
  { value: "lte", label: "less than or equal" },
  { value: "eq", label: "equal to" }
];
const SEVERITY_OPTIONS = [
  "info",
  "warning",
  "critical"
];
function build_alert_rules_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + ALERT_RULES_ROUTE;
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
class PycAlertRules extends HTMLElement {
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
    const project_select = document.createElement("select");
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
    if (select instanceof HTMLSelectElement === false || input instanceof HTMLElement === false) {
      return;
    }
    const select_el = select;
    const input_el = input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      for (const project of this._projects) {
        const option = document.createElement("option");
        option.value = project.project_id;
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
    const table = document.createElement("table");
    table.classList.add("pyc-metrics__table");
    table.setAttribute("data-role", "alert-rules-table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = [
      "Rule",
      "Condition",
      "Window",
      "Severity",
      "Targets",
      "Enabled"
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
    for (const rule of this._rules) {
      tbody.appendChild(this._build_row(rule));
    }
    table.appendChild(tbody);
    return table;
  }
  _build_row(rule) {
    const row = document.createElement("tr");
    row.classList.add("pyc-metrics__row");
    row.setAttribute("data-rule-id", rule.rule_id);
    const name_cell = document.createElement("td");
    const name = document.createElement("span");
    name.textContent = rule.name;
    name.title = rule.rule_id;
    name_cell.appendChild(name);
    row.appendChild(name_cell);
    const condition_cell = document.createElement("td");
    condition_cell.textContent = describe_alert_condition(rule);
    row.appendChild(condition_cell);
    const window_cell = document.createElement("td");
    const window_value = rule.config.window_seconds;
    window_cell.textContent = typeof window_value === "number" ? format_alert_window(window_value) : "\u2014";
    row.appendChild(window_cell);
    const severity_cell = document.createElement("td");
    const severity_badge = document.createElement("span");
    severity_badge.classList.add("pyc-metrics__badge");
    severity_badge.setAttribute("data-role", "severity-badge");
    severity_badge.setAttribute("data-tone", this._severity_tone(rule.severity));
    severity_badge.textContent = rule.severity;
    severity_cell.appendChild(severity_badge);
    row.appendChild(severity_cell);
    const targets_cell = document.createElement("td");
    targets_cell.textContent = rule.notification_targets.length > 0 ? rule.notification_targets.join(", ") : "\u2014";
    row.appendChild(targets_cell);
    const enabled_cell = document.createElement("td");
    const enabled_badge = document.createElement("span");
    enabled_badge.classList.add("pyc-metrics__badge");
    enabled_badge.setAttribute("data-role", "enabled-badge");
    enabled_badge.setAttribute(
      "data-tone",
      rule.enabled === true ? "ok" : "neutral"
    );
    enabled_badge.textContent = rule.enabled === true ? "Enabled" : "Disabled";
    enabled_cell.appendChild(enabled_badge);
    row.appendChild(enabled_cell);
    return row;
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
    const metric_select = document.createElement("select");
    metric_select.classList.add("pyc-metrics__select");
    metric_select.setAttribute("data-role", "create-metric");
    if (this._catalog.length === 0) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No metrics in catalog";
      metric_select.appendChild(option);
    } else {
      for (const entry of this._catalog) {
        const option = document.createElement("option");
        option.value = entry.name;
        option.textContent = entry.name;
        metric_select.appendChild(option);
      }
    }
    metric_label.appendChild(metric_select);
    form.appendChild(metric_label);
    const comparison_label_el = document.createElement("label");
    comparison_label_el.classList.add("pyc-metrics__field");
    comparison_label_el.textContent = "Comparison";
    const comparison_select = document.createElement("select");
    comparison_select.classList.add("pyc-metrics__select");
    comparison_select.setAttribute("data-role", "create-comparison");
    for (const option of COMPARISON_OPTIONS) {
      const opt = document.createElement("option");
      opt.value = option.value;
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
    const severity_select = document.createElement("select");
    severity_select.classList.add("pyc-metrics__select");
    severity_select.setAttribute("data-role", "create-severity");
    for (const severity of SEVERITY_OPTIONS) {
      const opt = document.createElement("option");
      opt.value = severity;
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
}
export {
  ALERT_RULES_ROUTE,
  ALERT_RULE_KIND,
  COMPARISON_OPTIONS,
  PycAlertRules,
  SEVERITY_OPTIONS,
  alert_create_message_for_status,
  build_alert_rules_collection_url,
  comparison_label,
  describe_alert_condition,
  extract_alert_rules,
  format_alert_window,
  parse_notification_targets
};
