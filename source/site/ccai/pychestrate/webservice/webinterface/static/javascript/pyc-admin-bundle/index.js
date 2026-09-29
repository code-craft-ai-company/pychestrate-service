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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-admin-bundle/feature-flags-view.js
var FLAGS_PATH = "/api/v1/flags";
var FLAG_STATE_ENABLED = "enabled";
var FLAG_STATE_DISABLED = "disabled";
var FLAG_STATE_RETIRED = "retired";
function build_flag_url(flag_key) {
  const rtnval = FLAGS_PATH + "/" + encodeURIComponent(flag_key);
  return rtnval;
}
function flag_state_tone(state) {
  if (typeof state !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = state.toLowerCase();
  if (lowered === FLAG_STATE_ENABLED) {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === FLAG_STATE_DISABLED) {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  if (lowered === FLAG_STATE_RETIRED) {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "warn";
  return rtnval;
}
function next_flag_state(state) {
  if (typeof state === "string" && state.toLowerCase() === FLAG_STATE_ENABLED) {
    const rtnval2 = FLAG_STATE_DISABLED;
    return rtnval2;
  }
  const rtnval = FLAG_STATE_ENABLED;
  return rtnval;
}
function load_failure_message(status, subject, required_permission) {
  if (status === 403) {
    if (typeof required_permission === "string" && required_permission.length > 0) {
      const rtnval3 = "You do not have permission to view " + subject + ": it needs the \u201C" + required_permission + "\u201D permission. Ask an administrator for access.";
      return rtnval3;
    }
    const rtnval2 = "You do not have permission to view " + subject + ".";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Could not reach the service while loading " + subject + ". Check your connection and try refreshing.";
    return rtnval2;
  }
  const rtnval = "Failed to load " + subject + " (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
async function read_required_permission(response) {
  try {
    const body = await response.json();
    if (body !== null && typeof body === "object" && typeof body.required_permission === "string") {
      const rtnval2 = body.required_permission;
      return rtnval2;
    }
  } catch (reason) {
  }
  const rtnval = "";
  return rtnval;
}
function toggle_message_for_status(status) {
  if (status === 200) {
    const rtnval2 = "Flag state updated.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "The flag was modified concurrently \u2014 refresh.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The flag-state update was rejected.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to manage flags.";
    return rtnval2;
  }
  const rtnval = "Failed to update flag (HTTP " + String(status) + ").";
  return rtnval;
}
var PycFeatureFlags = class extends HTMLElement {
  _entries;
  _loading;
  _errored;
  _error_status;
  _filter_text;
  _table_region;
  _status_region;
  constructor() {
    super();
    this._entries = [];
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._filter_text = "";
    this._table_region = null;
    this._status_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to read the loading
   * flag without scraping the DOM.
   */
  get loading() {
    const rtnval = this._loading;
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to read the errored
   * flag without scraping the DOM.
   */
  get errored() {
    const rtnval = this._errored;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * flags fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-admin");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-admin__heading");
    heading.textContent = "Feature Flags";
    root.appendChild(heading);
    const lede = document.createElement("p");
    lede.classList.add("pyc-admin__lede");
    lede.textContent = "Toggle a flag's state. Retired flags are read-only.";
    root.appendChild(lede);
    const controls = document.createElement("div");
    controls.classList.add("pyc-admin__controls");
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-admin__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    const filter_input = document.createElement("input");
    filter_input.classList.add("pyc-admin__filter");
    filter_input.setAttribute("type", "search");
    filter_input.setAttribute("data-role", "flag-filter");
    filter_input.setAttribute("placeholder", "Filter by flag key\u2026");
    filter_input.setAttribute("aria-label", "Filter feature flags by key");
    filter_input.addEventListener("input", () => {
      this._filter_text = filter_input.value;
      this._render_table();
    });
    controls.appendChild(filter_input);
    root.appendChild(controls);
    const status_region = document.createElement("div");
    status_region.setAttribute("data-role", "status-region");
    root.appendChild(status_region);
    this._status_region = status_region;
    const table_region = document.createElement("div");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the flags list and re-render. Exposed so unit tests
   * can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_table();
    let entries = null;
    try {
      const response = await fetch(FLAGS_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        this._error_status = response.status;
        throw new Error(
          "flags fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      if (Array.isArray(body) === true) {
        entries = body;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.flags_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (entries === null) {
      this._loading = false;
      this._errored = true;
      this._render_table();
      return;
    }
    this._entries = entries;
    this._loading = false;
    this._errored = false;
    this._render_table();
    return;
  }
  _render_table() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading feature flags\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-admin__notice",
        "pyc-admin__notice--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = load_failure_message(
        this._error_status,
        "feature flags"
      );
      region.replaceChildren(error);
      return;
    }
    if (this._entries.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-admin__notice");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No feature flags are registered. A flag switches an optional behaviour on or off without a release; flags are created through the REST API (POST /api/v1/flags) or by an extension, and appear here for you to toggle.";
      region.replaceChildren(empty);
      return;
    }
    const filter_text = this._filter_text.trim().toLowerCase();
    let visible = this._entries;
    if (filter_text.length > 0) {
      visible = this._entries.filter((entry) => {
        if (typeof entry.flag_key !== "string") {
          return false;
        }
        return entry.flag_key.toLowerCase().includes(filter_text);
      });
    }
    if (visible.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-admin__notice");
      empty.setAttribute("data-role", "filter-empty-state");
      empty.textContent = "No feature flags match \u201C" + this._filter_text.trim() + "\u201D.";
      region.replaceChildren(empty);
      return;
    }
    const ordered = visible.slice();
    ordered.sort(
      (left, right) => {
        if (left.flag_key < right.flag_key) {
          return -1;
        }
        if (left.flag_key > right.flag_key) {
          return 1;
        }
        return 0;
      }
    );
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-admin__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-admin__row";
    table.rowAttrs = (entry) => ({ "data-flag-key": entry.flag_key });
    table.columns = [
      {
        key: "flag_key",
        label: "Flag Key",
        width: "20rem",
        render: (entry) => {
          const key_cell = document.createElement("span");
          key_cell.classList.add("pyc-admin__mono");
          key_cell.textContent = entry.flag_key ?? "\u2014";
          if (typeof entry.flag_key === "string") {
            key_cell.setAttribute("title", entry.flag_key);
          }
          return key_cell;
        }
      },
      {
        key: "flag_kind",
        label: "Kind",
        width: "10rem",
        render: (entry) => entry.flag_kind ?? "\u2014"
      },
      {
        key: "current_version",
        label: "Version",
        width: "8rem",
        render: (entry) => String(entry.current_version)
      },
      {
        key: "state",
        label: "State",
        width: "10rem",
        render: (entry) => {
          const state_badge = document.createElement("mj-chip");
          state_badge.classList.add("pyc-admin__badge");
          state_badge.setAttribute("data-tone", flag_state_tone(entry.state));
          state_badge.textContent = entry.state ?? "\u2014";
          return state_badge;
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "10rem",
        sortable: false,
        render: (entry) => self._build_toggle(entry)
      }
    ];
    table.rows = ordered;
    region.replaceChildren(table);
    return;
  }
  _build_toggle(entry) {
    const is_retired = typeof entry.state === "string" && entry.state.toLowerCase() === FLAG_STATE_RETIRED;
    const toggle = document.createElement("mj-button");
    toggle.classList.add("pyc-admin__toggle");
    toggle.setAttribute("type", "button");
    toggle.setAttribute("data-role", "toggle");
    const target = next_flag_state(entry.state);
    toggle.textContent = target === FLAG_STATE_ENABLED ? "Enable" : "Disable";
    if (is_retired === true) {
      toggle.toggleAttribute("disabled", true);
    }
    toggle.addEventListener("click", () => {
      const question = 'Set flag "' + String(entry.flag_key) + '" to ' + target + "?";
      if (target !== FLAG_STATE_ENABLED && window.confirm(question) === false) {
        return;
      }
      toggle.toggleAttribute("disabled", true);
      void this._on_toggle(entry, toggle);
    });
    return toggle;
  }
  async _on_toggle(entry, toggle) {
    const target = next_flag_state(entry.state);
    const outcome = await this.toggleFlag(entry.flag_key, target);
    toggle.toggleAttribute("disabled", false);
    this._show_status(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * PATCH a flag's state. Exposed so unit tests can invoke a
   * toggle without a real click event.
   *
   * @param flag_key The flag to update.
   * @param target_state The desired flag-state value.
   *
   * @returns The toggle outcome.
   */
  async toggleFlag(flag_key, target_state) {
    const payload = { state: target_state };
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(build_flag_url(flag_key), {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      status = response.status;
      detail = await read_problem_detail(response);
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.flag_toggle_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        flagKey: flag_key,
        message: "Failed to reach the feature-flags service."
      };
      return rtnval2;
    }
    const ok = status === 200;
    const rtnval = {
      ok,
      status,
      flagKey: flag_key,
      message: message_with_detail("Feature flag not changed", detail, toggle_message_for_status(status))
    };
    return rtnval;
  }
  _show_status(message, tone) {
    if (this._status_region === null) {
      return;
    }
    const notice = document.createElement("p");
    notice.classList.add("pyc-admin__notice");
    if (tone === "error") {
      notice.classList.add("pyc-admin__notice--error");
    }
    notice.setAttribute("data-role", "toggle-status");
    notice.setAttribute("role", tone === "error" ? "alert" : "status");
    notice.textContent = message;
    this._status_region.replaceChildren(notice);
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-admin-bundle/system-health-view.js
var SYSTEM_HEALTH_PATH = "/api/v1/system/health";
function health_status_tone(status) {
  if (typeof status !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = status.toLowerCase();
  if (lowered === "ok") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "degraded") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (lowered === "error") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
async function fetch_system_health() {
  let document_body = null;
  let http_status = 0;
  let required_permission = "";
  try {
    const response = await fetch(SYSTEM_HEALTH_PATH, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    http_status = response.status;
    if (response.ok === true) {
      const body = await response.json();
      const parsed = body;
      if (parsed !== null && typeof parsed.status === "string" && Array.isArray(parsed.subsystems) === true) {
        document_body = parsed;
      }
    } else if (response.status === 403) {
      required_permission = await read_required_permission(response);
    }
  } catch (reason) {
    console.warn(
      "pychestrate.ui.admin.system_health_fetch_failed",
      { reason: String(reason) }
    );
  }
  const rtnval = { document_body, http_status, required_permission };
  return rtnval;
}
var PycSystemHealth = class extends HTMLElement {
  _document;
  _loading;
  _errored;
  _error_status;
  _error_permission;
  _body_region;
  constructor() {
    super();
    this._document = null;
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._error_permission = "";
    this._body_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to read the loading
   * flag without scraping the DOM.
   */
  get loading() {
    const rtnval = this._loading;
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to read the errored
   * flag without scraping the DOM.
   */
  get errored() {
    const rtnval = this._errored;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * system-health fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-admin");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-admin__heading");
    heading.textContent = "System Health";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-admin__controls");
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-admin__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const body_region = document.createElement("div");
    body_region.classList.add("pyc-admin__cards");
    body_region.setAttribute("data-role", "body-region");
    root.appendChild(body_region);
    this._body_region = body_region;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the system-health document and re-render. Exposed so
   * unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_body();
    const outcome = await fetch_system_health();
    if (outcome.document_body === null) {
      this._loading = false;
      this._errored = true;
      this._error_status = outcome.http_status;
      this._error_permission = outcome.required_permission;
      this._document = null;
      this._render_body();
      return;
    }
    this._document = outcome.document_body;
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  _render_body() {
    if (this._body_region === null) {
      return;
    }
    const region = this._body_region;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading system health\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._document === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-admin__notice",
        "pyc-admin__notice--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = load_failure_message(
        this._error_status,
        "system health",
        this._error_permission
      );
      region.replaceChildren(error);
      return;
    }
    const children = [];
    const summary = document.createElement("div");
    summary.classList.add("pyc-admin__card");
    summary.setAttribute("data-role", "overall-status");
    const summary_head = document.createElement("div");
    summary_head.classList.add("pyc-admin__card-head");
    const summary_title = document.createElement("p");
    summary_title.classList.add("pyc-admin__card-title");
    summary_title.textContent = "Overall Status";
    const summary_badge = document.createElement("mj-chip");
    summary_badge.classList.add("pyc-admin__badge");
    summary_badge.setAttribute(
      "data-tone",
      health_status_tone(this._document.status)
    );
    summary_badge.textContent = this._document.status;
    summary_head.appendChild(summary_title);
    summary_head.appendChild(summary_badge);
    summary.appendChild(summary_head);
    const generated = document.createElement("p");
    generated.classList.add("pyc-admin__card-detail");
    generated.textContent = "Checked " + format_timestamp(this._document.generated_at);
    summary.appendChild(generated);
    children.push(summary);
    if (this._document.subsystems.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-admin__notice");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No subsystem probes reported.";
      children.push(empty);
    }
    for (const subsystem of this._document.subsystems) {
      children.push(this._build_subsystem_card(subsystem));
    }
    region.replaceChildren(...children);
    return;
  }
  _build_subsystem_card(subsystem) {
    const card = document.createElement("div");
    card.classList.add("pyc-admin__card");
    card.setAttribute("data-role", "subsystem-card");
    card.setAttribute("data-subsystem", subsystem.name);
    const head = document.createElement("div");
    head.classList.add("pyc-admin__card-head");
    const title = document.createElement("p");
    title.classList.add("pyc-admin__card-title");
    title.textContent = subsystem.label;
    const badge = document.createElement("mj-chip");
    badge.classList.add("pyc-admin__badge");
    badge.setAttribute(
      "data-tone",
      health_status_tone(subsystem.status)
    );
    badge.textContent = subsystem.status;
    head.appendChild(title);
    head.appendChild(badge);
    card.appendChild(head);
    const detail = document.createElement("p");
    detail.classList.add("pyc-admin__card-detail");
    detail.textContent = subsystem.detail;
    card.appendChild(detail);
    const backends = subsystem.backends;
    if (backends !== void 0 && backends.length > 0) {
      const table = document.createElement("mj-data-table");
      table.classList.add("pyc-admin__table");
      table.classList.add("pyc-admin__table--embedded");
      table.setAttribute("sortable", "");
      table.setAttribute("resizable", "");
      table.rowClass = "pyc-admin__row";
      table.columns = [
        { key: "name", label: "Backend", width: "12rem" },
        {
          key: "status",
          label: "Status",
          width: "8rem",
          render: (backend) => {
            const status_badge = document.createElement("mj-chip");
            status_badge.classList.add("pyc-admin__badge");
            status_badge.setAttribute(
              "data-tone",
              health_status_tone(backend.status)
            );
            status_badge.textContent = backend.status;
            return status_badge;
          }
        },
        {
          key: "reason",
          label: "Reason",
          width: "44rem",
          sortable: false,
          render: (backend) => backend.reason.length > 0 ? backend.reason : "\u2014"
        }
      ];
      table.rows = backends;
      card.appendChild(table);
    }
    return card;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-admin-bundle/extension-registry-view.js
var EXT_LISTING_PATH = "/api/v1/ext";
function group_routes_by_extension(routes) {
  const buckets = /* @__PURE__ */ new Map();
  for (const route of routes) {
    const existing = buckets.get(route.ext_name);
    if (existing === void 0) {
      buckets.set(route.ext_name, [route]);
    } else {
      existing.push(route);
    }
  }
  const ext_names = Array.from(buckets.keys());
  ext_names.sort();
  const summaries = [];
  let precedence = 0;
  for (const ext_name of ext_names) {
    const ext_routes = buckets.get(ext_name);
    if (ext_routes === void 0) {
      continue;
    }
    const capability_set = /* @__PURE__ */ new Set();
    for (const route of ext_routes) {
      for (const capability of route.required_capabilities) {
        capability_set.add(capability);
      }
    }
    const capabilities = Array.from(capability_set);
    capabilities.sort();
    summaries.push({
      extName: ext_name,
      precedence,
      routeCount: ext_routes.length,
      capabilities,
      routes: ext_routes
    });
    precedence = precedence + 1;
  }
  const rtnval = summaries;
  return rtnval;
}
function mount_state_tone(dynamic_mount) {
  if (typeof dynamic_mount !== "string") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const lowered = dynamic_mount.toLowerCase();
  if (lowered === "mounted") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "deferred") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "error";
  return rtnval;
}
var PycExtensionRegistry = class extends HTMLElement {
  _extensions;
  _mountState;
  _loading;
  _errored;
  _error_status;
  _error_permission;
  _table_region;
  _detail_region;
  constructor() {
    super();
    this._extensions = [];
    this._mountState = "";
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._error_permission = "";
    this._table_region = null;
    this._detail_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to read the loading
   * flag without scraping the DOM.
   */
  get loading() {
    const rtnval = this._loading;
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to read the errored
   * flag without scraping the DOM.
   */
  get errored() {
    const rtnval = this._errored;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * manifest fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-admin");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-admin__heading");
    heading.textContent = "Extension Registry";
    root.appendChild(heading);
    const lede = document.createElement("p");
    lede.classList.add("pyc-admin__lede");
    lede.textContent = "Loaded extensions with precedence, capabilities and route-mount health.";
    root.appendChild(lede);
    const controls = document.createElement("div");
    controls.classList.add("pyc-admin__controls");
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-admin__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const table_region = document.createElement("div");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const detail_region = document.createElement("div");
    detail_region.setAttribute("data-role", "detail-region");
    root.appendChild(detail_region);
    this._detail_region = detail_region;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the extension manifest and re-render. Exposed so unit
   * tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_table();
    let listing = null;
    try {
      const response = await fetch(EXT_LISTING_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        this._error_status = response.status;
        if (response.status === 403) {
          this._error_permission = await read_required_permission(response);
        }
        throw new Error(
          "ext manifest fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      const parsed = body;
      if (parsed !== null && Array.isArray(parsed.items) === true) {
        listing = parsed;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.ext_manifest_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (listing === null) {
      this._loading = false;
      this._errored = true;
      this._render_table();
      return;
    }
    this._extensions = group_routes_by_extension(listing.items);
    this._mountState = listing.dynamic_mount;
    this._loading = false;
    this._errored = false;
    this._render_table();
    return;
  }
  _render_table() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading extension registry\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-admin__notice",
        "pyc-admin__notice--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = load_failure_message(
        this._error_status,
        "the extension registry",
        this._error_permission
      );
      region.replaceChildren(error);
      return;
    }
    if (this._extensions.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-admin__notice");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No extensions contribute REST routes.";
      region.replaceChildren(empty);
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-admin__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-admin__row";
    table.rowAttrs = (extension) => ({ "data-ext-name": extension.extName });
    table.columns = [
      {
        key: "precedence",
        label: "Precedence",
        width: "8rem",
        render: (extension) => String(extension.precedence)
      },
      { key: "extName", label: "Extension", width: "16rem" },
      {
        key: "routeCount",
        label: "Routes",
        width: "8rem",
        render: (extension) => String(extension.routeCount)
      },
      {
        key: "capabilities",
        label: "Capabilities",
        width: "16rem",
        sortable: false,
        render: (extension) => {
          if (extension.capabilities.length === 0) {
            return "\u2014";
          }
          return extension.capabilities.join(", ");
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "10rem",
        sortable: false,
        render: (extension) => {
          const detail_button = document.createElement("mj-button");
          detail_button.classList.add("pyc-admin__toggle");
          detail_button.setAttribute("type", "button");
          detail_button.setAttribute("data-role", "show-routes");
          detail_button.textContent = "Show Routes";
          detail_button.addEventListener("click", () => {
            self._render_detail(extension);
          });
          return detail_button;
        }
      }
    ];
    table.rows = this._extensions;
    const registry_status = document.createElement("p");
    registry_status.classList.add("pyc-admin__lede");
    registry_status.setAttribute("data-role", "registry-status");
    registry_status.appendChild(
      document.createTextNode("Registry status: ")
    );
    const status_badge = document.createElement("mj-chip");
    status_badge.classList.add("pyc-admin__badge");
    status_badge.setAttribute(
      "data-tone",
      mount_state_tone(this._mountState)
    );
    status_badge.textContent = this._mountState.length > 0 ? this._mountState : "unknown";
    registry_status.appendChild(status_badge);
    region.replaceChildren(registry_status, table);
    return;
  }
  _render_detail(extension) {
    if (this._detail_region === null) {
      return;
    }
    const region = this._detail_region;
    const heading = document.createElement("h2");
    heading.classList.add("pyc-admin__subheading");
    heading.textContent = "Routes \u2014 " + extension.extName;
    const mount_note = document.createElement("p");
    mount_note.classList.add("pyc-admin__lede");
    mount_note.textContent = "Dynamic-mount state: " + (this._mountState.length > 0 ? this._mountState : "unknown");
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-admin__table");
    table.classList.add("pyc-admin__table--embedded");
    table.setAttribute("data-role", "route-detail");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-admin__row";
    table.columns = [
      { key: "method", label: "Method", width: "8rem" },
      {
        key: "full_path",
        label: "Path",
        width: "20rem",
        render: (route) => {
          const path_cell = document.createElement("span");
          path_cell.classList.add("pyc-admin__mono");
          path_cell.textContent = route.full_path;
          return path_cell;
        }
      },
      {
        key: "required_permissions",
        label: "Permissions",
        width: "16rem",
        sortable: false,
        render: (route) => route.required_permissions.length > 0 ? route.required_permissions.join(", ") : "\u2014"
      },
      {
        key: "handler_class",
        label: "Handler",
        width: "20rem",
        render: (route) => {
          const handler_cell = document.createElement("span");
          handler_cell.classList.add("pyc-admin__mono");
          handler_cell.textContent = route.handler_class;
          return handler_cell;
        }
      }
    ];
    table.rows = extension.routes;
    region.replaceChildren(heading, mount_note, table);
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-admin-bundle/admin-overview-view.js
var SYSTEM_HEALTH_ROUTE = "/admin/system-health";
var FEATURE_FLAGS_ROUTE = "/admin/feature-flags";
var EXTENSION_REGISTRY_ROUTE = "/admin/extensions";
var QUICK_FLAG_LIMIT = 8;
var PycAdminOverview = class extends HTMLElement {
  _loading;
  _health;
  _flags;
  _flagsErrored;
  _healthErrored;
  _extensionCount;
  _extensionsErrored;
  /**
   * Why each section failed: ``{status, permission}`` (the HTTP
   * status and, for a 403, the permission the problem document
   * named), so a tile can say "you do not have permission" instead
   * of "unavailable".
   */
  _healthFailure;
  _flagsFailure;
  _extensionsFailure;
  _health_region;
  _flags_region;
  _flags_status_region;
  _ext_region;
  constructor() {
    super();
    this._loading = false;
    this._health = null;
    this._flags = [];
    this._flagsErrored = false;
    this._healthErrored = false;
    this._extensionCount = 0;
    this._extensionsErrored = false;
    this._healthFailure = { status: 0, permission: "" };
    this._flagsFailure = { status: 0, permission: "" };
    this._extensionsFailure = { status: 0, permission: "" };
    this._health_region = null;
    this._flags_region = null;
    this._flags_status_region = null;
    this._ext_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to read the loading
   * flag without scraping the DOM.
   */
  get loading() {
    const rtnval = this._loading;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * three composing fetches when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-admin");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-admin__heading");
    heading.textContent = "Administration";
    root.appendChild(heading);
    const lede = document.createElement("p");
    lede.classList.add("pyc-admin__lede");
    lede.textContent = "System health, feature flags and the extension registry at a glance.";
    root.appendChild(lede);
    const controls = document.createElement("div");
    controls.classList.add("pyc-admin__controls");
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-admin__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const tiles = document.createElement("div");
    tiles.classList.add("pyc-admin__tiles");
    const health_region = document.createElement("div");
    health_region.classList.add("pyc-admin__tile");
    health_region.setAttribute("data-role", "health-tile");
    tiles.appendChild(health_region);
    this._health_region = health_region;
    const ext_region = document.createElement("div");
    ext_region.classList.add("pyc-admin__tile");
    ext_region.setAttribute("data-role", "extension-tile");
    tiles.appendChild(ext_region);
    this._ext_region = ext_region;
    root.appendChild(tiles);
    const flags_heading = document.createElement("h2");
    flags_heading.classList.add("pyc-admin__subheading");
    flags_heading.textContent = "Feature Flags";
    root.appendChild(flags_heading);
    const flags_status_region = document.createElement("div");
    flags_status_region.setAttribute(
      "data-role",
      "flags-status-region"
    );
    root.appendChild(flags_status_region);
    this._flags_status_region = flags_status_region;
    const flags_region = document.createElement("div");
    flags_region.setAttribute("data-role", "flags-region");
    root.appendChild(flags_region);
    this._flags_region = flags_region;
    this.replaceChildren(root);
    return;
  }
  /**
   * Refresh all three composing sections. Exposed so unit tests
   * can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._render_health();
    this._render_extensions();
    this._render_flags();
    await Promise.all([
      this._load_health(),
      this._load_flags(),
      this._load_extensions()
    ]);
    this._loading = false;
    this._render_health();
    this._render_extensions();
    this._render_flags();
    return;
  }
  async _load_health() {
    this._healthErrored = false;
    const outcome = await fetch_system_health();
    if (outcome.document_body === null) {
      this._healthErrored = true;
      this._healthFailure = {
        status: outcome.http_status,
        permission: outcome.required_permission || ""
      };
      this._health = null;
      return;
    }
    this._health = outcome.document_body;
    return;
  }
  async _load_flags() {
    this._flagsErrored = false;
    this._flagsFailure = { status: 0, permission: "" };
    let entries = null;
    try {
      const response = await fetch(FLAGS_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      this._flagsFailure.status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        if (Array.isArray(body) === true) {
          entries = body;
        }
      } else if (response.status === 403) {
        this._flagsFailure.permission = await read_required_permission(response);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.overview_flags_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (entries === null) {
      this._flagsErrored = true;
      this._flags = [];
      return;
    }
    const ordered = entries.slice();
    ordered.sort(
      (left, right) => {
        if (left.flag_key < right.flag_key) {
          return -1;
        }
        if (left.flag_key > right.flag_key) {
          return 1;
        }
        return 0;
      }
    );
    this._flags = ordered;
    return;
  }
  async _load_extensions() {
    this._extensionsErrored = false;
    this._extensionsFailure = { status: 0, permission: "" };
    let listing = null;
    try {
      const response = await fetch(EXT_LISTING_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      this._extensionsFailure.status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        const parsed = body;
        if (parsed !== null && Array.isArray(parsed.items) === true) {
          listing = parsed;
        }
      } else if (response.status === 403) {
        this._extensionsFailure.permission = await read_required_permission(response);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.overview_ext_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (listing === null) {
      this._extensionsErrored = true;
      this._extensionCount = 0;
      return;
    }
    const grouped = group_routes_by_extension(listing.items);
    this._extensionCount = grouped.length;
    return;
  }
  _render_health() {
    if (this._health_region === null) {
      return;
    }
    const region = this._health_region;
    const children = [];
    const title = document.createElement("p");
    title.classList.add("pyc-admin__tile-title");
    title.textContent = "System Health";
    children.push(title);
    if (this._loading === true && this._health === null && this._healthErrored === false) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__tile-detail");
      loading.setAttribute("data-role", "health-loading");
      loading.textContent = "Loading\u2026";
      children.push(loading);
      region.replaceChildren(...children);
      return;
    }
    if (this._healthErrored === true || this._health === null) {
      const error = document.createElement("p");
      error.classList.add("pyc-admin__tile-detail");
      error.setAttribute("data-role", "health-error");
      error.textContent = load_failure_message(
        this._healthFailure.status,
        "system health",
        this._healthFailure.permission
      );
      children.push(error);
      region.replaceChildren(...children);
      return;
    }
    const value = document.createElement("p");
    value.classList.add("pyc-admin__tile-value");
    const value_badge = document.createElement("mj-chip");
    value_badge.classList.add("pyc-admin__badge");
    value_badge.setAttribute(
      "data-tone",
      health_status_tone(this._health.status)
    );
    value_badge.setAttribute("data-role", "health-status");
    value_badge.textContent = this._health.status;
    value.appendChild(value_badge);
    children.push(value);
    for (const subsystem of this._health.subsystems) {
      const sub = document.createElement("p");
      sub.classList.add("pyc-admin__tile-detail");
      const sub_badge = document.createElement("mj-chip");
      sub_badge.classList.add("pyc-admin__badge");
      sub_badge.setAttribute(
        "data-tone",
        health_status_tone(subsystem.status)
      );
      sub_badge.textContent = subsystem.status;
      sub.appendChild(sub_badge);
      sub.appendChild(
        document.createTextNode(" " + subsystem.label)
      );
      children.push(sub);
    }
    const link = document.createElement("a");
    link.classList.add("pyc-admin__link");
    link.setAttribute("href", SYSTEM_HEALTH_ROUTE);
    link.setAttribute("data-role", "health-link");
    link.textContent = "Open system health \u2192";
    children.push(link);
    region.replaceChildren(...children);
    return;
  }
  _render_extensions() {
    if (this._ext_region === null) {
      return;
    }
    const region = this._ext_region;
    const children = [];
    const title = document.createElement("p");
    title.classList.add("pyc-admin__tile-title");
    title.textContent = "Extension Registry";
    children.push(title);
    if (this._loading === true && this._extensionCount === 0 && this._extensionsErrored === false) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__tile-detail");
      loading.setAttribute("data-role", "extension-loading");
      loading.textContent = "Loading\u2026";
      children.push(loading);
      region.replaceChildren(...children);
      return;
    }
    if (this._extensionsErrored === true) {
      const error = document.createElement("p");
      error.classList.add("pyc-admin__tile-detail");
      error.setAttribute("data-role", "extension-error");
      error.textContent = load_failure_message(
        this._extensionsFailure.status,
        "the extension registry",
        this._extensionsFailure.permission
      );
      children.push(error);
      region.replaceChildren(...children);
      return;
    }
    const value = document.createElement("p");
    value.classList.add("pyc-admin__tile-value");
    value.setAttribute("data-role", "extension-count");
    value.textContent = String(this._extensionCount);
    children.push(value);
    const detail = document.createElement("p");
    detail.classList.add("pyc-admin__tile-detail");
    detail.textContent = this._extensionCount === 1 ? "loaded extension" : "loaded extensions";
    children.push(detail);
    const link = document.createElement("a");
    link.classList.add("pyc-admin__link");
    link.setAttribute("href", EXTENSION_REGISTRY_ROUTE);
    link.setAttribute("data-role", "extension-link");
    link.textContent = "Open extension registry \u2192";
    children.push(link);
    region.replaceChildren(...children);
    return;
  }
  _render_flags() {
    if (this._flags_region === null) {
      return;
    }
    const region = this._flags_region;
    if (this._loading === true && this._flags.length === 0 && this._flagsErrored === false) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__notice");
      loading.setAttribute("data-role", "flags-loading");
      loading.textContent = "Loading feature flags\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._flagsErrored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-admin__notice",
        "pyc-admin__notice--error"
      );
      error.setAttribute("data-role", "flags-error");
      error.textContent = load_failure_message(
        this._flagsFailure.status,
        "feature flags",
        this._flagsFailure.permission
      );
      region.replaceChildren(error);
      return;
    }
    if (this._flags.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-admin__notice");
      empty.setAttribute("data-role", "flags-empty");
      empty.textContent = "No feature flags registered.";
      region.replaceChildren(empty);
      return;
    }
    const children = [];
    const self = this;
    const shown = this._flags.slice(0, QUICK_FLAG_LIMIT);
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-admin__table");
    table.classList.add("pyc-admin__table--embedded");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-admin__row";
    table.rowAttrs = (entry) => ({ "data-flag-key": entry.flag_key });
    table.columns = [
      { key: "flag_key", label: "Flag Key", width: "16rem" },
      {
        key: "state",
        label: "State",
        width: "8rem",
        render: (entry) => {
          const state_badge = document.createElement("mj-chip");
          state_badge.classList.add("pyc-admin__badge");
          state_badge.setAttribute("data-tone", flag_state_tone(entry.state));
          state_badge.textContent = entry.state ?? "\u2014";
          return state_badge;
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "8rem",
        sortable: false,
        render: (entry) => self._build_flag_toggle(entry)
      }
    ];
    table.rows = shown;
    children.push(table);
    if (this._flags.length > QUICK_FLAG_LIMIT) {
      const more = document.createElement("p");
      more.classList.add("pyc-admin__tile-detail");
      more.textContent = "Showing " + String(QUICK_FLAG_LIMIT) + " of " + String(this._flags.length) + " flags.";
      children.push(more);
    }
    const link = document.createElement("a");
    link.classList.add("pyc-admin__link");
    link.setAttribute("href", FEATURE_FLAGS_ROUTE);
    link.setAttribute("data-role", "flags-link");
    link.textContent = "Manage all feature flags \u2192";
    children.push(link);
    region.replaceChildren(...children);
    return;
  }
  _build_flag_toggle(entry) {
    const is_retired = typeof entry.state === "string" && entry.state.toLowerCase() === FLAG_STATE_RETIRED;
    const toggle = document.createElement("mj-button");
    toggle.classList.add("pyc-admin__toggle");
    toggle.setAttribute("type", "button");
    toggle.setAttribute("data-role", "toggle");
    const target = next_flag_state(entry.state);
    toggle.textContent = target === FLAG_STATE_ENABLED ? "Enable" : "Disable";
    if (is_retired === true) {
      toggle.toggleAttribute("disabled", true);
    }
    toggle.addEventListener("click", () => {
      const question = 'Set flag "' + String(entry.flag_key) + '" to ' + target + "?";
      if (target !== FLAG_STATE_ENABLED && window.confirm(question) === false) {
        return;
      }
      toggle.toggleAttribute("disabled", true);
      void this._on_toggle(entry, toggle);
    });
    return toggle;
  }
  async _on_toggle(entry, toggle) {
    const target = next_flag_state(entry.state);
    const outcome = await this.toggleFlag(entry.flag_key, target);
    toggle.toggleAttribute("disabled", false);
    this._show_flags_status(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      await this._load_flags();
      this._render_flags();
    }
    return;
  }
  /**
   * PATCH a flag's state from the quick-view list. Exposed so
   * unit tests can invoke a toggle without a real click event.
   *
   * @param flag_key The flag to update.
   * @param target_state The desired flag-state value.
   *
   * @returns The toggle outcome (``ok`` / ``status`` /
   *          ``flagKey`` / ``message``), mirroring the full
   *          feature-flags view.
   */
  async toggleFlag(flag_key, target_state) {
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(build_flag_url(flag_key), {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ state: target_state })
      });
      status = response.status;
      detail = await read_problem_detail(response);
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.overview_flag_toggle_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        flagKey: flag_key,
        message: "Failed to reach the feature-flags service."
      };
      return rtnval2;
    }
    const ok = status === 200;
    const rtnval = {
      ok,
      status,
      flagKey: flag_key,
      message: message_with_detail("Feature flag not changed", detail, toggle_message_for_status(status))
    };
    return rtnval;
  }
  _show_flags_status(message, tone) {
    if (this._flags_status_region === null) {
      return;
    }
    const notice = document.createElement("p");
    notice.classList.add("pyc-admin__notice");
    if (tone === "error") {
      notice.classList.add("pyc-admin__notice--error");
    }
    notice.setAttribute("data-role", "flags-toggle-status");
    notice.setAttribute("role", tone === "error" ? "alert" : "status");
    notice.textContent = message;
    this._flags_status_region.replaceChildren(notice);
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-admin-bundle/index.entry.js
var OVERVIEW_TAG = "pyc-admin-overview";
var FEATURE_FLAGS_TAG = "pyc-feature-flags";
var EXTENSION_REGISTRY_TAG = "pyc-extension-registry";
var SYSTEM_HEALTH_TAG = "pyc-system-health";
var OVERVIEW_ROUTE = "/admin";
var OVERVIEW_ALIAS_ROUTE = "/admin/overview";
var FEATURE_FLAGS_ROUTE2 = "/admin/feature-flags";
var EXTENSION_REGISTRY_ROUTE2 = "/admin/extensions";
var SYSTEM_HEALTH_ROUTE2 = "/admin/system-health";
var ADMIN_STYLESHEET_HREF = "/static/javascript/pyc-admin-bundle/pyc-admin-bundle.css";
function ensure_admin_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-admin-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = ADMIN_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-admin-bundle");
  document.head.appendChild(link);
  return;
}
function define_admin_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(OVERVIEW_TAG) === void 0) {
    customElements.define(OVERVIEW_TAG, PycAdminOverview);
  }
  if (customElements.get(FEATURE_FLAGS_TAG) === void 0) {
    customElements.define(FEATURE_FLAGS_TAG, PycFeatureFlags);
  }
  if (customElements.get(EXTENSION_REGISTRY_TAG) === void 0) {
    customElements.define(EXTENSION_REGISTRY_TAG, PycExtensionRegistry);
  }
  if (customElements.get(SYSTEM_HEALTH_TAG) === void 0) {
    customElements.define(SYSTEM_HEALTH_TAG, PycSystemHealth);
  }
  return;
}
function classify_admin_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working.length > 1 && working.endsWith("/") === true) {
    working = working.slice(0, working.length - 1);
  }
  if (working === FEATURE_FLAGS_ROUTE2) {
    const rtnval2 = "feature-flags";
    return rtnval2;
  }
  if (working === EXTENSION_REGISTRY_ROUTE2) {
    const rtnval2 = "extensions";
    return rtnval2;
  }
  if (working === SYSTEM_HEALTH_ROUTE2) {
    const rtnval2 = "system-health";
    return rtnval2;
  }
  if (working === OVERVIEW_ROUTE || working === OVERVIEW_ALIAS_ROUTE) {
    const rtnval2 = "overview";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_admin_route(route) {
  if (route === "overview") {
    const rtnval2 = OVERVIEW_TAG;
    return rtnval2;
  }
  if (route === "feature-flags") {
    const rtnval2 = FEATURE_FLAGS_TAG;
    return rtnval2;
  }
  if (route === "extensions") {
    const rtnval2 = EXTENSION_REGISTRY_TAG;
    return rtnval2;
  }
  if (route === "system-health") {
    const rtnval2 = SYSTEM_HEALTH_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_admin_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_admin_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_admin_route(route);
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
  define_admin_elements();
  ensure_admin_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against() {
  mount_admin_view_if_active();
  return;
}
function _boot() {
  define_admin_elements();
  const target = window;
  const handle = target.pychestrateShell;
  if (handle !== void 0 && handle.sidebar !== void 0) {
    _register_against();
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
      _register_against();
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
  EXT_LISTING_PATH,
  FLAGS_PATH,
  PycAdminOverview,
  PycExtensionRegistry,
  PycFeatureFlags,
  PycSystemHealth,
  build_flag_url,
  classify_admin_route,
  define_admin_elements,
  ensure_admin_stylesheet,
  fetch_system_health,
  flag_state_tone,
  group_routes_by_extension,
  health_status_tone,
  mount_admin_view_if_active,
  mount_state_tone,
  next_flag_state,
  tag_for_admin_route,
  toggle_message_for_status
};
