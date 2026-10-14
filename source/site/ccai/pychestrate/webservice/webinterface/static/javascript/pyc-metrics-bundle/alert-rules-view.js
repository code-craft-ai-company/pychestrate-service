import { hide_unless_may } from "../shared/permissions.js";
import { show_toast } from "../shared/toast.js";
import { confirm_action } from "../shared/confirm.js";
import {
  build_catalog_url,
  extract_catalog
} from "./timeseries-view.js";
import {
  announce_session_expired,
  extract_projects
} from "./test-metrics-view.js";
import { build_empty_state } from "../shared/empty-state.js";
import { choose_project_id, mirror_to_query } from "../shared/view-state.js";
import { reveal } from "../shared/reveal.js";
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
const ALERT_RULES_ROUTE = "/metric-alerts";
const ALERT_RULE_KIND = "threshold";
const COMPARISON_OPTIONS = [
  { value: ">", label: "greater than" },
  { value: ">=", label: "greater than or equal" },
  { value: "<", label: "less than" },
  { value: "<=", label: "less than or equal" },
  { value: "==", label: "equal to" },
  { value: "!=", label: "not equal to" }
];
const DEFAULT_ALERT_WINDOW_SECONDS = 3600;
const ALERT_RULES_PREVIEW_NOTE = "Preview: enabled rules are evaluated every minute and their state is shown below, but no notification is sent to their targets yet.";
const ALERT_STATE_LABELS = {
  firing: "Firing",
  ok: "OK",
  unknown: "Not evaluated yet"
};
const SEVERITY_OPTIONS = [
  "info",
  "warning",
  "critical"
];
function build_alert_rules_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + ALERT_RULES_ROUTE;
  return rtnval;
}
function build_alert_rule_url(project_id, rule_id) {
  const rtnval = build_alert_rules_collection_url(project_id) + "/" + encodeURIComponent(rule_id);
  return rtnval;
}
function problem_detail_of(body) {
  if (body === null || typeof body !== "object") {
    const rtnval2 = "";
    return rtnval2;
  }
  const detail = body.detail;
  const rtnval = typeof detail === "string" ? detail.trim() : "";
  return rtnval;
}
function alert_create_message_for_status(status, detail) {
  const reason = typeof detail === "string" ? detail.trim() : "";
  if (status === 201 || status === 200) {
    const rtnval2 = "Alert rule created.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "An alert rule with that name already exists.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = reason.length > 0 ? "The alert-rule definition was rejected: " + reason : "The alert-rule definition was rejected \u2014 check the fields.";
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
function alert_update_message_for_status(status, detail, name) {
  const reason = typeof detail === "string" ? detail.trim() : "";
  if (status === 200) {
    const rtnval2 = "Alert rule \u201C" + name + "\u201D saved.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "Another alert rule already has that name.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = reason.length > 0 ? "The change was rejected: " + reason : "The change was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "That alert rule no longer exists.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to edit alert rules.";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to save.";
    return rtnval2;
  }
  const rtnval = "Failed to save the alert rule (HTTP " + String(status) + ").";
  return rtnval;
}
function alert_delete_message_for_status(status, name) {
  if (status === 204 || status === 200) {
    const rtnval2 = "Alert rule \u201C" + name + "\u201D deleted.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "That alert rule no longer exists.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to delete alert rules.";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to delete.";
    return rtnval2;
  }
  const rtnval = "Failed to delete the alert rule (HTTP " + String(status) + ").";
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
  let metric = typeof record.metric_name === "string" ? record.metric_name : "";
  if (metric.length === 0 && typeof record.metric === "string") {
    metric = record.metric;
  }
  let comparison = typeof record.op === "string" ? record.op : "";
  if (comparison.length === 0 && typeof record.comparison === "string") {
    comparison = record.comparison;
  }
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
function alert_state_of(rule) {
  const live = rule.live_state;
  if (live === null || live === void 0 || typeof live !== "object") {
    const rtnval2 = "unknown";
    return rtnval2;
  }
  const state = live.state;
  if (state === "firing" || state === "ok") {
    const rtnval2 = state;
    return rtnval2;
  }
  const rtnval = "unknown";
  return rtnval;
}
function alert_state_label(state) {
  const label = ALERT_STATE_LABELS[state];
  const rtnval = typeof label === "string" ? label : ALERT_STATE_LABELS.unknown;
  return rtnval;
}
function alert_state_tone(state) {
  if (state === "firing") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (state === "ok") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function describe_alert_state(rule) {
  const live = rule.live_state;
  if (live === null || live === void 0 || typeof live !== "object") {
    const rtnval2 = "The evaluator has not run this rule yet.";
    return rtnval2;
  }
  const parts = [];
  if (typeof live.last_reason === "string" && live.last_reason.length > 0) {
    parts.push(live.last_reason);
  }
  if (typeof live.last_evaluated_at === "string" && live.last_evaluated_at.length > 0) {
    parts.push("evaluated " + live.last_evaluated_at);
  } else {
    parts.push("The evaluator has not run this rule yet.");
  }
  const rtnval = parts.join(" \u00B7 ");
  return rtnval;
}
function extract_live_state(raw) {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw) === true) {
    const rtnval2 = null;
    return rtnval2;
  }
  const record = raw;
  const rtnval = {
    state: typeof record.state === "string" ? record.state : "unknown",
    last_value: typeof record.last_value === "number" ? record.last_value : null,
    last_reason: typeof record.last_reason === "string" ? record.last_reason : "",
    last_evaluated_at: typeof record.last_evaluated_at === "string" ? record.last_evaluated_at : null,
    fire_count: typeof record.fire_count === "number" ? record.fire_count : 0
  };
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
      notification_targets: targets,
      live_state: extract_live_state(record.live_state)
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
  _editing;
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
    this._editing = null;
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
    const preview = document.createElement("p");
    preview.classList.add("pyc-metrics__notice", "pyc-metrics__notice--preview");
    preview.setAttribute("data-role", "preview-notice");
    preview.setAttribute("role", "note");
    preview.textContent = ALERT_RULES_PREVIEW_NOTE;
    root.appendChild(preview);
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
    hide_unless_may(create_button, "system:metric_alerts.write");
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
      const response = await fetch(PROJECTS_LIST_URL, {
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
      this._state.projectId = choose_project_id(projects);
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
    // The address describes what is on screen (ORC-27).
    mirror_to_query({ project_id: this._state.projectId });
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
      const empty = build_empty_state({ class_name: "pyc-metrics__notice", message: "No alert rules defined for this project yet \u2014 create one above." });
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
          const rtnval = typeof window_value === "number"
            ? format_alert_window(window_value)
            : "\u2014";
          return rtnval;
        }
      },
      {
        key: "state",
        label: "State",
        width: "10rem",
        render: (rule) => {
          const state = alert_state_of(rule);
          const state_badge = document.createElement("mj-chip");
          state_badge.classList.add("pyc-metrics__badge");
          state_badge.setAttribute("data-role", "state-badge");
          state_badge.setAttribute("data-state", state);
          state_badge.setAttribute("data-tone", alert_state_tone(state));
          state_badge.setAttribute("title", describe_alert_state(rule));
          state_badge.textContent = alert_state_label(state);
          return state_badge;
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
        render: (rule) =>
          rule.notification_targets.length > 0
            ? rule.notification_targets.join(", ")
            : "\u2014"
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
          enabled_badge.textContent =
            rule.enabled === true ? "Enabled" : "Disabled";
          return enabled_badge;
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "12rem",
        sortable: false,
        render: (rule) => {
          // Table cells render inside the table's shadow root, out of reach of
          // the bundle stylesheet, so the layout is set on the element itself.
          const actions = document.createElement("span");
          actions.classList.add("pyc-metrics__row-actions");
          actions.style.display = "inline-flex";
          actions.style.flexWrap = "wrap";
          actions.style.gap = "0.5rem";
          const edit_button = document.createElement("mj-button");
          edit_button.classList.add("pyc-metrics__button");
          edit_button.setAttribute("type", "button");
          edit_button.setAttribute("data-role", "edit-rule");
          hide_unless_may(edit_button, "system:metric_alerts.write");
          edit_button.textContent = "Edit";
          edit_button.addEventListener("click", () => {
            self._open_edit_form(rule);
          });
          actions.appendChild(edit_button);
          const delete_button = document.createElement("mj-button");
          delete_button.classList.add("pyc-metrics__button");
          delete_button.setAttribute("type", "button");
          delete_button.setAttribute("data-role", "delete-rule");
          hide_unless_may(delete_button, "system:metric_alerts.write");
          delete_button.textContent = "Delete";
          delete_button.addEventListener("click", () => {
            void self._on_delete(rule, delete_button);
          });
          actions.appendChild(delete_button);
          return actions;
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
    if (region.hidden === true || this._editing !== null) {
      this._editing = null;
      this._render_create_form();
      region.hidden = false;
      reveal(region);
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Open the form on an existing rule to change its name, condition, severity, targets or whether it is enabled.
   * The kind cannot change (a different kind is a different rule: create a new one).
   *
   * @param rule The rule row to edit.
   */
  _open_edit_form(rule) {
    if (this._create_region === null) {
      return;
    }
    this._editing = rule;
    this._render_create_form();
    this._create_region.hidden = false;
    reveal(this._create_region);
    return;
  }
  /**
   * Render the create form into the create region, or, when a rule is being edited, the same form filled in with
   * that rule's values.
   */
  _render_create_form() {
    if (this._create_region === null) {
      return;
    }
    const editing = this._editing;
    const prefix = editing === null ? "create" : "edit";
    const form = document.createElement("form");
    form.classList.add("pyc-metrics__form");
    form.setAttribute("data-role", prefix + "-form");
    if (editing !== null) {
      const heading = document.createElement("h3");
      heading.classList.add("pyc-metrics__form-heading");
      heading.setAttribute("data-role", "edit-heading");
      heading.textContent = "Edit alert rule \u201C" + editing.name + "\u201D";
      form.appendChild(heading);
    }
    const name_input = this._build_text_field(
      form,
      "Name",
      prefix + "-name",
      "checkout error rate"
    );
    const metric_label = document.createElement("label");
    metric_label.classList.add("pyc-metrics__field");
    metric_label.textContent = "Metric";
    const metric_select = document.createElement("mj-select");
    metric_select.classList.add("pyc-metrics__select");
    metric_select.setAttribute("data-role", prefix + "-metric");
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
      metric_select.value = this._catalog[0].name;
    }
    const edited_metric = editing !== null && editing.config !== null && typeof editing.config === "object" ? String(editing.config.metric_name ?? "") : "";
    if (edited_metric.length > 0 && this._catalog.every((entry) => entry.name !== edited_metric)) {
      // The rule's own metric is kept even when the catalog no longer lists it, so saving does not silently change it.
      const kept = document.createElement("mj-option");
      kept.setAttribute("value", edited_metric);
      kept.textContent = edited_metric;
      metric_select.appendChild(kept);
    }
    metric_label.appendChild(metric_select);
    form.appendChild(metric_label);
    const comparison_label_el = document.createElement("label");
    comparison_label_el.classList.add("pyc-metrics__field");
    comparison_label_el.textContent = "Comparison";
    const comparison_select = document.createElement("mj-select");
    comparison_select.classList.add("pyc-metrics__select");
    comparison_select.setAttribute("data-role", prefix + "-comparison");
    for (const option of COMPARISON_OPTIONS) {
      const opt = document.createElement("mj-option");
      opt.setAttribute("value", option.value);
      opt.textContent = option.label;
      comparison_select.appendChild(opt);
    }
    comparison_select.value = COMPARISON_OPTIONS[0].value;
    comparison_label_el.appendChild(comparison_select);
    form.appendChild(comparison_label_el);
    const threshold_input = this._build_text_field(
      form,
      "Threshold",
      prefix + "-threshold",
      "0.95"
    );
    const window_input = this._build_text_field(
      form,
      "Window (seconds)",
      prefix + "-window",
      String(DEFAULT_ALERT_WINDOW_SECONDS)
    );
    window_input.value = String(DEFAULT_ALERT_WINDOW_SECONDS);
    window_input.setAttribute(
      "help-text",
      "Counter metrics are summed over this window; gauges use their latest sample inside it."
    );
    const severity_label = document.createElement("label");
    severity_label.classList.add("pyc-metrics__field");
    severity_label.textContent = "Severity";
    const severity_select = document.createElement("mj-select");
    severity_select.classList.add("pyc-metrics__select");
    severity_select.setAttribute("data-role", prefix + "-severity");
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
      prefix + "-targets",
      "ops-pager, slack:#alerts"
    );
    targets_input.setAttribute(
      "help-text",
      "Saved with the rule; notifications are not sent yet."
    );
    const enabled_label = document.createElement("label");
    enabled_label.classList.add("pyc-metrics__field");
    enabled_label.classList.add("pyc-metrics__field--inline");
    const enabled_checkbox = document.createElement("input");
    enabled_checkbox.setAttribute("type", "checkbox");
    enabled_checkbox.setAttribute("data-role", prefix + "-enabled");
    enabled_checkbox.checked = true;
    enabled_label.appendChild(enabled_checkbox);
    const enabled_text = document.createElement("span");
    enabled_text.textContent = "Enabled";
    enabled_label.appendChild(enabled_text);
    form.appendChild(enabled_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-metrics__button");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", prefix + "-submit");
    submit_button.textContent = editing === null ? "Create Alert Rule" : "Save changes";
    form.appendChild(submit_button);
    if (editing !== null) {
      const cancel_button = document.createElement("mj-button");
      cancel_button.classList.add("pyc-metrics__button");
      cancel_button.setAttribute("type", "button");
      cancel_button.setAttribute("data-role", "edit-cancel");
      cancel_button.textContent = "Cancel";
      cancel_button.addEventListener("click", () => {
        this._editing = null;
        if (this._create_region !== null) {
          this._create_region.hidden = true;
        }
      });
      form.appendChild(cancel_button);
    }
    const status = document.createElement("p");
    status.classList.add("pyc-metrics__form-status");
    status.setAttribute("data-role", prefix + "-status");
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
    if (editing !== null) {
      // Filled in once the form is in the page: the inputs draw their value when they connect.
      const config = editing.config !== null && typeof editing.config === "object" ? editing.config : {};
      name_input.value = editing.name;
      if (edited_metric.length > 0) {
        metric_select.value = edited_metric;
      }
      comparison_select.value = typeof config.op === "string" ? config.op : COMPARISON_OPTIONS[0].value;
      threshold_input.value = config.threshold === undefined || config.threshold === null ? "" : String(config.threshold);
      window_input.value = typeof config.window_seconds === "number" ? String(config.window_seconds) : String(DEFAULT_ALERT_WINDOW_SECONDS);
      severity_select.value = typeof editing.severity === "string" ? editing.severity : "warning";
      targets_input.value = Array.isArray(editing.notification_targets) ? editing.notification_targets.join(", ") : "";
      enabled_checkbox.checked = editing.enabled === true;
    }
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
    const editing = this._editing;
    const status = form.querySelector('[data-role="' + (editing === null ? "create" : "edit") + '-status"]');
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
    if (Number.isInteger(window_seconds) === false || window_seconds <= 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Window seconds must be a positive whole number.";
      }
      return;
    }
    const config = {
      metric_name: metric,
      op: comparison_select.value,
      threshold,
      window_seconds
    };
    const targets = parse_notification_targets(targets_input.value);
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = editing === null ? "Creating alert rule\u2026" : "Saving\u2026";
    }
    const outcome = editing === null ? await this._do_create(
      name,
      config,
      severity_select.value,
      enabled_checkbox.checked,
      targets
    ) : await this._do_update(
      editing,
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
      if (editing === null) {
        this._toggle_create_form();
      } else {
        this._editing = null;
        if (this._create_region !== null) {
          this._create_region.hidden = true;
        }
      }
      await this._refresh();
    }
    return;
  }
  /**
   * ``PUT`` a change to one rule. Exposed so unit tests can drive it without a form-submit event.
   *
   * @param rule The rule being changed (its kind is sent back, as the API requires the rule's own).
   * @param name The name.
   * @param config The threshold config (metric_name, op, threshold, window_seconds).
   * @param severity ``info`` / ``warning`` / ``critical``.
   * @param enabled Whether the rule is enabled.
   * @param notification_targets The target list.
   *
   * @returns ``{ok, status, ruleId, message}``.
   */
  async updateAlertRule(rule, name, config, severity, enabled, notification_targets) {
    const rtnval = await this._do_update(rule, name, config, severity, enabled, notification_targets);
    return rtnval;
  }
  async _do_update(rule, name, config, severity, enabled, notification_targets) {
    if (this._state.projectId.length === 0) {
      return { ok: false, status: 0, ruleId: rule.rule_id, message: "Select a project before editing an alert rule." };
    }
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(build_alert_rule_url(this._state.projectId, rule.rule_id), {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          name,
          kind: rule.kind,
          config: {
            metric_name: config.metric_name,
            op: config.op,
            threshold: config.threshold,
            window_seconds: config.window_seconds
          },
          severity,
          enabled,
          notification_targets
        })
      });
      status = response.status;
      if (status === 401) {
        announce_session_expired();
      }
      if (response.ok !== true) {
        try {
          detail = problem_detail_of(await response.json());
        } catch (parse_reason) {
          detail = "";
        }
      }
    } catch (reason) {
      console.warn("pychestrate.ui.metrics.alert_rule_update_failed", { reason: String(reason) });
      return { ok: false, status: 0, ruleId: rule.rule_id, message: "Failed to reach the alert-rules service." };
    }
    return {
      ok: status === 200,
      status,
      ruleId: rule.rule_id,
      message: alert_update_message_for_status(status, detail, name)
    };
  }
  /**
   * Delete one rule after asking. The dialog names what goes with it and how to stop a rule without losing it.
   *
   * @param rule The rule to delete.
   * @param button The row action button, disabled while the request runs.
   */
  async _on_delete(rule, button) {
    const confirmed = await confirm_action(
      this,
      "Delete the alert rule \u201C" + rule.name + "\u201D?\nIts current state is removed too. This cannot be undone; to stop a rule without losing it, edit it and untick Enabled.",
      "Delete alert rule"
    );
    if (confirmed !== true) {
      return;
    }
    button.toggleAttribute("disabled", true);
    const outcome = await this._do_delete(rule);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true || outcome.status === 404) {
      await this._refresh();
    }
    return;
  }
  /**
   * ``DELETE`` one rule. Exposed so unit tests can drive it without a dialog.
   *
   * @param rule The rule to delete.
   *
   * @returns ``{ok, status, message}``.
   */
  async deleteAlertRule(rule) {
    const rtnval = await this._do_delete(rule);
    return rtnval;
  }
  async _do_delete(rule) {
    if (this._state.projectId.length === 0) {
      return { ok: false, status: 0, message: "Select a project before deleting an alert rule." };
    }
    let status = 0;
    try {
      const response = await fetch(build_alert_rule_url(this._state.projectId, rule.rule_id), {
        method: "DELETE",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      if (status === 401) {
        announce_session_expired();
      }
    } catch (reason) {
      console.warn("pychestrate.ui.metrics.alert_rule_delete_failed", { reason: String(reason) });
      return { ok: false, status: 0, message: "Failed to reach the alert-rules service." };
    }
    return { ok: status === 204 || status === 200, status, message: alert_delete_message_for_status(status, rule.name) };
  }
  /**
   * POST a ``MetricAlertRule`` create request. Exposed so unit
   * tests can invoke a create without a real form-submit event.
   *
   * @param name Human-facing alert-rule name.
   * @param config Threshold config (metric_name, op,
   *               threshold, window_seconds) -- the shape the
   *               ``threshold`` alert-rule kind validates.
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
        metric_name: config.metric_name,
        op: config.op,
        threshold: config.threshold,
        window_seconds: config.window_seconds
      },
      severity,
      enabled,
      notification_targets
    };
    let status = 0;
    let rule_id = "";
    let detail = "";
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
      } else {
        try {
          detail = problem_detail_of(await response.json());
        } catch (parse_reason) {
          detail = "";
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
      message: alert_create_message_for_status(status, detail)
    };
    return rtnval;
  }
  /**
   * Show a toast in the toast region through the shared service: one at a
   * time, announced to assistive technology, a plain success goes away by itself.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-metrics" });
    return;
  }
}
export {
  ALERT_RULES_PREVIEW_NOTE,
  ALERT_RULES_ROUTE,
  ALERT_RULE_KIND,
  ALERT_STATE_LABELS,
  COMPARISON_OPTIONS,
  DEFAULT_ALERT_WINDOW_SECONDS,
  PycAlertRules,
  SEVERITY_OPTIONS,
  alert_create_message_for_status,
  alert_delete_message_for_status,
  alert_state_label,
  alert_state_of,
  alert_state_tone,
  alert_update_message_for_status,
  build_alert_rule_url,
  build_alert_rules_collection_url,
  comparison_label,
  describe_alert_condition,
  describe_alert_state,
  extract_alert_rules,
  extract_live_state,
  format_alert_window,
  parse_notification_targets,
  problem_detail_of
};
