// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/permissions.js
var PERMISSIONS_URL = "/api/v1/me/permissions";
var held = null;
function held_permissions() {
  if (held !== null) {
    return held;
  }
  held = (async () => {
    try {
      const response = await fetch(PERMISSIONS_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok !== true) {
        return null;
      }
      const body = await response.json();
      if (body === null || typeof body !== "object" || Array.isArray(body.permissions) === false) {
        return null;
      }
      return new Set(body.permissions.filter((key) => typeof key === "string"));
    } catch (reason) {
      return null;
    }
  })();
  return held;
}
async function may(permission_key) {
  const keys = await held_permissions();
  return keys === null ? true : keys.has(permission_key);
}
function hide_unless_may(element, permission_key) {
  void may(permission_key).then((allowed) => {
    if (allowed === false) {
      element.hidden = true;
    }
  });
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/toast.js
var DEFAULT_AUTO_DISMISS_MS = 8e3;
function show_toast(region, message, tone, options) {
  if (region === null || region === void 0) {
    return null;
  }
  const settings = options !== null && typeof options === "object" ? options : {};
  const prefix = typeof settings.class_prefix === "string" ? settings.class_prefix : "pyc";
  if (region.getAttribute("role") === null) {
    region.setAttribute("role", "status");
  }
  if (region.getAttribute("aria-live") === null) {
    region.setAttribute("aria-live", "polite");
  }
  const toast = document.createElement("div");
  toast.classList.add(prefix + "__toast");
  toast.setAttribute("data-role", typeof settings.data_role === "string" ? settings.data_role : "toast");
  toast.setAttribute("data-tone", tone);
  toast.setAttribute("role", tone === "error" ? "alert" : "status");
  const text = document.createElement("span");
  text.classList.add(prefix + "__toast-message");
  text.textContent = message;
  toast.appendChild(text);
  const link = settings.link !== null && typeof settings.link === "object" ? settings.link : null;
  if (link !== null) {
    const anchor = document.createElement("a");
    anchor.classList.add(prefix + "__toast-link");
    anchor.setAttribute("href", link.href);
    if (typeof link.data_role === "string") {
      anchor.setAttribute("data-role", link.data_role);
    }
    anchor.textContent = link.text;
    toast.appendChild(anchor);
  }
  const dismiss = document.createElement("mj-button");
  dismiss.classList.add(prefix + "__toast-dismiss");
  dismiss.setAttribute("type", "button");
  dismiss.setAttribute("aria-label", typeof settings.dismiss_label === "string" ? settings.dismiss_label : "Dismiss");
  dismiss.textContent = "\xD7";
  dismiss.addEventListener("click", () => {
    toast.remove();
  });
  toast.appendChild(dismiss);
  region.replaceChildren(toast);
  const delay = typeof settings.auto_dismiss_ms === "number" ? settings.auto_dismiss_ms : DEFAULT_AUTO_DISMISS_MS;
  if (tone !== "error" && link === null && delay > 0) {
    window.setTimeout(() => {
      if (toast.parentNode === region) {
        toast.remove();
      }
    }, delay);
  }
  return toast;
}
function clear_toasts(region) {
  if (region !== null && region !== void 0) {
    region.replaceChildren();
  }
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/confirm.js
function confirm_action(source, message, confirm_label) {
  return new Promise((resolve) => {
    const request = new CustomEvent("pyc-confirm-request", {
      bubbles: true,
      composed: true,
      cancelable: true,
      detail: { message, confirm_label, resolve }
    });
    const answered_by_shell = source.dispatchEvent(request) === false;
    if (answered_by_shell === false) {
      resolve(window.confirm(message));
    }
  });
}

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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/empty-state.js
function build_empty_state({ class_name, message, next_step, link, inline, role }) {
  const paragraph = document.createElement(inline === true ? "span" : "p");
  if (typeof class_name === "string" && class_name.length > 0) {
    paragraph.classList.add(class_name);
  }
  paragraph.setAttribute("data-role", "empty-state");
  if (typeof role === "string" && role.length > 0) {
    paragraph.setAttribute("role", role);
  }
  const words = [message];
  if (typeof next_step === "string" && next_step.length > 0) {
    words.push(next_step);
  }
  paragraph.appendChild(document.createTextNode(words.join(" ")));
  if (link !== void 0 && link !== null) {
    paragraph.appendChild(document.createTextNode(" "));
    const anchor = document.createElement("a");
    if (typeof link.class_name === "string" && link.class_name.length > 0) {
      anchor.classList.add(link.class_name);
    }
    anchor.setAttribute("href", link.href);
    anchor.setAttribute("data-role", "empty-state-link");
    anchor.textContent = link.label;
    paragraph.appendChild(anchor);
  }
  return paragraph;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-ops-bundle/webhooks-view.js
var PROJECTS_LIST_URL = "/api/v1/projects?per_page=500";
function extract_project_options(body) {
  const items = Array.isArray(body) ? body : body !== null && typeof body === "object" && Array.isArray(body.items) ? body.items : [];
  const rtnval = [];
  for (const item of items) {
    if (item !== null && typeof item === "object" && typeof item.project_id === "string" && item.project_id.length > 0) {
      const name = typeof item.display_name === "string" && item.display_name.length > 0 ? item.display_name : item.project_id;
      rtnval.push({ project_id: item.project_id, display_name: name });
    }
  }
  return rtnval;
}
var WEBHOOKS_IN_PATH = "/api/v1/webhooks/in";
var WEBHOOKS_OUT_PATH = "/api/v1/webhooks/out/subscriptions";
var TEST_EVENT_HISTORY_REFRESH_MS = 1500;
var WEBHOOKS_PREVIEW_NOTE = "Preview: inbound deliveries are verified and recorded, but they do not start builds or pipelines yet. Outbound subscriptions receive test events only; entity events are not delivered to them yet.";
function build_integrations_url(project_id) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  const rtnval = WEBHOOKS_IN_PATH + "/integrations?" + params.toString();
  return rtnval;
}
function build_integrations_collection_url() {
  const rtnval = WEBHOOKS_IN_PATH + "/integrations";
  return rtnval;
}
function build_integration_resource_url(webhook_id) {
  const rtnval = WEBHOOKS_IN_PATH + "/integrations/" + encodeURIComponent(webhook_id);
  return rtnval;
}
function build_in_deliveries_url(provider) {
  let url = WEBHOOKS_IN_PATH + "/deliveries";
  if (typeof provider === "string" && provider.length > 0) {
    const params = new URLSearchParams();
    params.set("provider", provider);
    url = url + "?" + params.toString();
  }
  const rtnval = url;
  return rtnval;
}
function build_subscriptions_url(project_id) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  const rtnval = WEBHOOKS_OUT_PATH + "?" + params.toString();
  return rtnval;
}
function build_subscription_resource_url(subscription_id) {
  const rtnval = WEBHOOKS_OUT_PATH + "/" + encodeURIComponent(subscription_id);
  return rtnval;
}
function build_subscription_deliveries_url(subscription_id) {
  const rtnval = WEBHOOKS_OUT_PATH + "/" + encodeURIComponent(subscription_id) + "/deliveries";
  return rtnval;
}
function build_subscription_test_url(subscription_id) {
  const rtnval = WEBHOOKS_OUT_PATH + "/" + encodeURIComponent(subscription_id) + "/test";
  return rtnval;
}
function format_webhook_timestamp(value) {
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
function delivery_outcome_tone(outcome) {
  if (typeof outcome !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = outcome.toLowerCase();
  if (lowered === "succeeded" || lowered === "delivered" || lowered === "success") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "pending" || lowered === "retrying") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (lowered === "failed" || lowered === "rejected_disabled" || lowered === "error") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function create_message_for_status(status, subject) {
  if (status === 201 || status === 200) {
    const rtnval2 = subject + " created.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "A " + subject.toLowerCase() + " with those identifiers already exists.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The " + subject.toLowerCase() + " request was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to create a " + subject.toLowerCase() + ".";
    return rtnval2;
  }
  const rtnval = "Failed to create " + subject.toLowerCase() + " (HTTP " + String(status) + ").";
  return rtnval;
}
function problem_message_for_status(status, problem, subject) {
  const generic = create_message_for_status(status, subject);
  if (problem === null || typeof problem !== "object") {
    const rtnval2 = generic;
    return rtnval2;
  }
  const detail = problem.detail;
  if (typeof detail !== "string" || detail.trim().length === 0) {
    const rtnval2 = generic;
    return rtnval2;
  }
  const first_line = detail.split(/\r?\n/)[0].trim();
  let message = "Failed to create " + subject.toLowerCase() + ": " + first_line;
  const providers = problem.registered_providers;
  if (Array.isArray(providers) === true) {
    const listed = providers.length > 0 ? providers.join(", ") : "none";
    message = message + " Available providers: " + listed + ".";
  }
  const rtnval = message;
  return rtnval;
}
function toggle_message_for_status(status, subject, enabled) {
  const verb = enabled === true ? "enable" : "disable";
  if (status === 200) {
    const rtnval2 = subject + " " + verb + "d.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown " + subject.toLowerCase() + " \u2014 refresh the list.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to " + verb + " this " + subject.toLowerCase() + ".";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Failed to reach the webhooks service \u2014 the " + subject.toLowerCase() + " was not changed.";
    return rtnval2;
  }
  const rtnval = "Failed to " + verb + " the " + subject.toLowerCase() + " (HTTP " + String(status) + ").";
  return rtnval;
}
function test_message_for_status(status, outcome, delivery) {
  if (status === 200 && outcome === "succeeded") {
    const code = delivery !== null && delivery !== void 0 && typeof delivery.response_status === "number" ? " (HTTP " + String(delivery.response_status) + ")" : "";
    const rtnval2 = "Test event delivered" + code + ".";
    return rtnval2;
  }
  if (status === 200 && outcome === "failed") {
    let reason = "";
    if (delivery !== null && delivery !== void 0) {
      if (typeof delivery.response_excerpt === "string" && delivery.response_excerpt.length > 0 && typeof delivery.response_status !== "number") {
        reason = delivery.response_excerpt;
      } else if (typeof delivery.response_status === "number") {
        reason = "the receiver answered HTTP " + String(delivery.response_status);
      }
    }
    const rtnval2 = reason.length > 0 ? "Test event was not delivered: " + reason + "." : "Test event was not delivered.";
    return rtnval2;
  }
  if (status === 202 || status === 200) {
    const rtnval2 = "Test event queued \u2014 the delivery history below refreshes in a moment.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "Cannot send a test event for a disabled subscription.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown subscription.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to send test events.";
    return rtnval2;
  }
  const rtnval = "Failed to send test event (HTTP " + String(status) + ").";
  return rtnval;
}
function parse_topic_filters(raw) {
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
var PycWebhooks = class extends HTMLElement {
  _projects;
  _project_region;
  _projectId;
  _activeTab;
  _integrations;
  _inDeliveries;
  _inProvider;
  _subscriptions;
  /**
   * One-time signing-secret payload ``{name, secret}`` captured
   * from the last create response, or ``null``. Held only until
   * the operator dismisses the panel -- the server never returns
   * the secret again.
   */
  _signingSecret;
  /**
   * The subscription whose delivery history is currently shown,
   * or ``null``. Refreshes re-fetch it instead of leaving a
   * stale panel behind.
   */
  _historySubscription;
  _pendingHistoryTimer;
  _root;
  _panel_region;
  _toast_region;
  constructor() {
    super();
    this._projects = [];
    this._project_region = null;
    this._projectId = "";
    this._activeTab = "inbound";
    this._integrations = [];
    this._inDeliveries = [];
    this._inProvider = "";
    this._subscriptions = [];
    this._signingSecret = null;
    this._historySubscription = null;
    this._pendingHistoryTimer = 0;
    this._root = null;
    this._panel_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to read the active
   * tab without scraping the DOM.
   */
  get activeTab() {
    const rtnval = this._activeTab;
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to read the active
   * project id.
   */
  get projectId() {
    const rtnval = this._projectId;
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to read the inbound
   * provider filter.
   */
  get inboundProviderFilter() {
    const rtnval = this._inProvider;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome when inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_projects();
    return;
  }
  /**
   * Lifecycle hook -- drop any pending history-refresh timer so
   * it cannot fire against a detached view.
   */
  disconnectedCallback() {
    if (this._pendingHistoryTimer !== 0) {
      clearTimeout(this._pendingHistoryTimer);
      this._pendingHistoryTimer = 0;
    }
    return;
  }
  /*
   * The project control: a list of the projects the person can see, or -- when
   * they cannot be listed (no permission, a failure, none) -- the id field it
   * used to be (ORC-18).
   */
  _render_project_control() {
    if (this._project_region === null) {
      return;
    }
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-ops__field");
    project_label.textContent = "Project";
    if (this._projects.length > 0) {
      const select = document.createElement("mj-select");
      select.classList.add("pyc-ops__select");
      select.setAttribute("data-role", "project-select");
      for (const project of this._projects) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", project.project_id);
        option.textContent = project.display_name;
        select.appendChild(option);
      }
      if (this._projectId.length > 0) {
        select.value = this._projectId;
      }
      select.addEventListener("change", () => {
        this._projectId = String(select.value || "").trim();
        void this._refresh_active_tab();
      });
      project_label.appendChild(select);
    } else {
      const project_input = document.createElement("mj-text-field");
      project_input.classList.add("pyc-ops__input");
      project_input.setAttribute("type", "text");
      project_input.setAttribute("placeholder", "project id");
      project_input.setAttribute("label", "Project id");
      project_input.setAttribute("data-role", "project-input");
      if (this._projectId.length > 0) {
        project_input.value = this._projectId;
      }
      project_input.addEventListener("change", () => {
        this._projectId = project_input.value.trim();
        void this._refresh_active_tab();
      });
      project_label.appendChild(project_input);
    }
    this._project_region.replaceChildren(project_label);
    return;
  }
  async _load_projects() {
    try {
      const response = await fetch(PROJECTS_LIST_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        this._projects = extract_project_options(await response.json());
      }
    } catch (reason) {
      console.warn("pychestrate.ui.ops.projects_fetch_failed", { reason: String(reason) });
    }
    if (this._projects.length === 0 || this.isConnected === false) {
      return;
    }
    const asked = new URLSearchParams(window.location.search).get("project_id");
    const known = asked !== null && this._projects.some((project) => project.project_id === asked);
    this._projectId = known ? asked : this._projects[0].project_id;
    this._render_project_control();
    await this._refresh_active_tab();
    return;
  }
  /* "Choose a project" when they can be listed, "Enter a project id" when not. */
  _project_prompt() {
    return this._projects.length > 0 ? "Choose a project" : "Enter a project id";
  }
  /**
   * Build the persistent chrome -- heading, project input, tab
   * strip, toast region, panel region.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-ops");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-ops__heading");
    heading.textContent = "Webhooks";
    root.appendChild(heading);
    const preview = document.createElement("p");
    preview.classList.add("pyc-ops__notice", "pyc-ops__notice--preview");
    preview.setAttribute("data-role", "preview-notice");
    preview.setAttribute("role", "note");
    preview.textContent = WEBHOOKS_PREVIEW_NOTE;
    root.appendChild(preview);
    const controls = document.createElement("div");
    controls.classList.add("pyc-ops__controls");
    const project_region = document.createElement("div");
    project_region.setAttribute("data-role", "project-region");
    controls.appendChild(project_region);
    this._project_region = project_region;
    this._render_project_control();
    root.appendChild(controls);
    const tabs = document.createElement("div");
    tabs.classList.add("pyc-ops__tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Webhook direction");
    const inbound_tab = this._build_tab_button("inbound", "Inbound");
    const outbound_tab = this._build_tab_button("outbound", "Outbound");
    tabs.appendChild(inbound_tab);
    tabs.appendChild(outbound_tab);
    tabs.addEventListener("keydown", (event) => {
      const order = ["inbound", "outbound"];
      const current = order.indexOf(this._activeTab);
      let next = current;
      if (event.key === "ArrowRight") {
        next = (current + 1) % order.length;
      } else if (event.key === "ArrowLeft") {
        next = (current - 1 + order.length) % order.length;
      } else if (event.key === "Home") {
        next = 0;
      } else if (event.key === "End") {
        next = order.length - 1;
      } else {
        return;
      }
      event.preventDefault();
      this.selectTab(order[next]);
      const focus_target = tabs.querySelector('[data-role="tab-' + order[next] + '"]');
      if (focus_target !== null) {
        focus_target.focus();
      }
    });
    root.appendChild(tabs);
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-ops__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const panel_region = document.createElement("div");
    panel_region.classList.add("pyc-ops__panel-region");
    panel_region.setAttribute("data-role", "panel-region");
    panel_region.id = "pyc-webhooks-panel";
    panel_region.setAttribute("role", "tabpanel");
    panel_region.setAttribute("aria-labelledby", "pyc-webhooks-tab-" + this._activeTab);
    root.appendChild(panel_region);
    this._panel_region = panel_region;
    this._root = root;
    this.replaceChildren(root);
    this._render_active_tab();
    return;
  }
  /**
   * Build a single tab button.
   *
   * @param tab_id The tab identifier (``"inbound"`` |
   *               ``"outbound"``).
   * @param label The visible tab label.
   *
   * @returns The created tab button.
   */
  _build_tab_button(tab_id, label) {
    const button = document.createElement("button");
    button.classList.add("pyc-ops__tab");
    button.setAttribute("type", "button");
    button.setAttribute("role", "tab");
    button.id = "pyc-webhooks-tab-" + tab_id;
    button.setAttribute("aria-controls", "pyc-webhooks-panel");
    button.setAttribute("data-role", "tab-" + tab_id);
    const selected = this._activeTab === tab_id;
    button.setAttribute("aria-selected", selected === true ? "true" : "false");
    button.tabIndex = selected === true ? 0 : -1;
    button.textContent = label;
    button.addEventListener("click", () => {
      this.selectTab(tab_id);
    });
    return button;
  }
  /**
   * Switch the active tab and re-render the panel. Exposed so
   * unit tests can drive tab selection.
   *
   * @param tab_id The tab to activate.
   */
  selectTab(tab_id) {
    if (tab_id !== "inbound" && tab_id !== "outbound") {
      return;
    }
    if (tab_id !== this._activeTab) {
      clear_toasts(this._toast_region);
    }
    this._activeTab = tab_id;
    if (this._root !== null) {
      for (const candidate of ["inbound", "outbound"]) {
        const tab = this._root.querySelector('[data-role="tab-' + candidate + '"]');
        if (tab instanceof HTMLElement) {
          const selected = candidate === tab_id;
          tab.setAttribute("aria-selected", selected === true ? "true" : "false");
          tab.tabIndex = selected === true ? 0 : -1;
        }
      }
      if (this._panel_region !== null) {
        this._panel_region.setAttribute("aria-labelledby", "pyc-webhooks-tab-" + tab_id);
      }
    }
    this._render_active_tab();
    void this._refresh_active_tab();
    return;
  }
  /**
   * Render the static panel scaffolding for the active tab.
   */
  _render_active_tab() {
    if (this._panel_region === null) {
      return;
    }
    if (this._activeTab === "inbound") {
      this._render_inbound_panel();
    } else {
      this._render_outbound_panel();
    }
    return;
  }
  /**
   * Re-fetch the data for whichever tab is currently active.
   */
  async _refresh_active_tab() {
    if (this._activeTab === "inbound") {
      await this.refreshInbound();
    } else {
      await this.refreshOutbound();
    }
    return;
  }
  // ----------------------------------------------------------------
  // Inbound tab
  // ----------------------------------------------------------------
  /**
   * Render the inbound-panel scaffolding -- create-form toggle,
   * refresh action, integrations table region, recent-deliveries
   * heading + provider filter + region.
   */
  _render_inbound_panel() {
    if (this._panel_region === null) {
      return;
    }
    const panel = document.createElement("div");
    panel.classList.add("pyc-ops__panel");
    panel.setAttribute("data-role", "inbound-panel");
    const actions = document.createElement("div");
    actions.classList.add("pyc-ops__controls");
    const create_button = document.createElement("mj-button");
    create_button.classList.add("pyc-ops__button");
    create_button.setAttribute("type", "button");
    create_button.setAttribute("data-role", "inbound-create-toggle");
    hide_unless_may(create_button, "system:webhooks.write");
    create_button.textContent = "Create Integration";
    create_button.addEventListener("click", () => {
      this._toggle_inbound_form(panel);
    });
    actions.appendChild(create_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-ops__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "inbound-refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this.refreshInbound();
    });
    actions.appendChild(refresh_button);
    panel.appendChild(actions);
    const form_region = document.createElement("div");
    form_region.classList.add("pyc-ops__form-region");
    form_region.setAttribute("data-role", "inbound-form-region");
    form_region.hidden = true;
    panel.appendChild(form_region);
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-ops__table-region");
    table_region.setAttribute("data-role", "inbound-table-region");
    panel.appendChild(table_region);
    const deliveries_heading = document.createElement("h2");
    deliveries_heading.classList.add("pyc-ops__subheading");
    deliveries_heading.textContent = "All Recent Inbound Deliveries";
    panel.appendChild(deliveries_heading);
    const deliveries_note = document.createElement("p");
    deliveries_note.classList.add("pyc-ops__note");
    deliveries_note.setAttribute("data-role", "inbound-deliveries-note");
    deliveries_note.textContent = "The inbound replay ledger across every project. It records that a delivery was received; per-delivery dispatch outcomes are not recorded yet.";
    panel.appendChild(deliveries_note);
    const filter_row = document.createElement("div");
    filter_row.classList.add("pyc-ops__controls");
    const provider_label = document.createElement("label");
    provider_label.classList.add("pyc-ops__field");
    provider_label.textContent = "Provider";
    const provider_select = document.createElement("mj-select");
    provider_select.classList.add("pyc-ops__select");
    provider_select.setAttribute("data-role", "in-provider-filter");
    provider_select.addEventListener("change", () => {
      this._inProvider = provider_select.value;
      void this._load_inbound_deliveries();
    });
    provider_label.appendChild(provider_select);
    filter_row.appendChild(provider_label);
    panel.appendChild(filter_row);
    const deliveries_region = document.createElement("div");
    deliveries_region.classList.add("pyc-ops__table-region");
    deliveries_region.setAttribute(
      "data-role",
      "inbound-deliveries-region"
    );
    panel.appendChild(deliveries_region);
    this._panel_region.replaceChildren(panel);
    this._sync_provider_options();
    this._render_inbound_table();
    this._render_inbound_deliveries();
    return;
  }
  /**
   * Fetch the inbound integrations + recent deliveries and
   * re-render. The delivery ledger is global, so it loads even
   * when no project id is set. Exposed so unit tests can await
   * a fetch cycle.
   */
  async refreshInbound() {
    if (this._projectId.length === 0) {
      this._integrations = [];
      this._render_inbound_table();
    } else {
      await this._load_integrations();
    }
    await this._load_inbound_deliveries();
    return;
  }
  async _load_integrations() {
    let items = null;
    try {
      const url = build_integrations_url(this._projectId);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (Array.isArray(page.items) === true) {
          items = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.integrations_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._integrations = items ?? [];
    this._sync_provider_options();
    this._render_inbound_table();
    return;
  }
  async _load_inbound_deliveries() {
    let items = null;
    try {
      const url = build_in_deliveries_url(this._inProvider);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (Array.isArray(page.items) === true) {
          items = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.in_deliveries_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._inDeliveries = items ?? [];
    this._sync_provider_options();
    this._render_inbound_deliveries();
    return;
  }
  /**
   * Rebuild the provider-filter options from the providers seen
   * in the loaded integrations + deliveries, preserving the
   * current selection.
   */
  _sync_provider_options() {
    if (this._panel_region === null) {
      return;
    }
    const select = this._panel_region.querySelector(
      '[data-role="in-provider-filter"]'
    );
    if (select instanceof HTMLElement === false) {
      return;
    }
    const providers = [];
    for (const integration of this._integrations) {
      if (typeof integration.provider === "string" && integration.provider.length > 0 && providers.includes(integration.provider) === false) {
        providers.push(integration.provider);
      }
    }
    for (const delivery of this._inDeliveries) {
      if (typeof delivery.provider === "string" && delivery.provider.length > 0 && providers.includes(delivery.provider) === false) {
        providers.push(delivery.provider);
      }
    }
    if (this._inProvider.length > 0 && providers.includes(this._inProvider) === false) {
      providers.push(this._inProvider);
    }
    providers.sort();
    const all_option = document.createElement("mj-option");
    all_option.setAttribute("value", "");
    all_option.textContent = "All providers";
    const options = [all_option];
    for (const provider of providers) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", provider);
      option.textContent = provider;
      options.push(option);
    }
    select.replaceChildren(...options);
    select.value = this._inProvider;
    return;
  }
  _render_inbound_table() {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="inbound-table-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (this._projectId.length === 0) {
      el.replaceChildren(
        this._notice(this._project_prompt() + " to view integrations.")
      );
      return;
    }
    if (this._integrations.length === 0) {
      el.replaceChildren(
        build_empty_state({ class_name: "pyc-ops__notice", message: "No inbound integrations for this project yet.", next_step: "Choose Create Integration above to add one." })
      );
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-ops__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowAttrs = (integration) => ({
      "data-webhook-id": integration.webhook_id
    });
    table.columns = [
      { key: "provider", label: "Provider", width: "10rem" },
      { key: "hook_name", label: "Hook", width: "10rem" },
      {
        key: "receiver_path",
        label: "Receiver path",
        width: "20rem",
        sortable: false,
        render: (integration) => integration.receiver_path ?? "\u2014"
      },
      {
        key: "secret_configured",
        label: "Shared secret",
        width: "14rem",
        sortable: false,
        // The API never returns the secret -- only whether the
        // vault holds it and under which reference.
        render: (integration) => {
          const configured = integration.secret_configured === true;
          const chip = self._badge(
            configured === true ? "in vault" : "missing",
            configured === true ? "ok" : "error"
          );
          chip.setAttribute("data-role", "integration-secret");
          chip.setAttribute(
            "title",
            configured === true ? "Stored in the secrets vault as " + String(integration.secret_ref) : "The integration's vault secret no longer exists, so its deliveries cannot be verified."
          );
          return chip;
        }
      },
      {
        key: "enabled",
        label: "State",
        width: "8rem",
        render: (integration) => self._badge(
          integration.enabled === true ? "enabled" : "disabled",
          integration.enabled === true ? "ok" : "neutral"
        )
      },
      {
        key: "actions",
        label: "Actions",
        width: "10rem",
        sortable: false,
        render: (integration) => {
          const toggle_button = document.createElement("mj-button");
          toggle_button.classList.add(
            "pyc-ops__button",
            "pyc-ops__row-action"
          );
          toggle_button.setAttribute("type", "button");
          toggle_button.setAttribute("data-role", "integration-toggle");
          hide_unless_may(toggle_button, "system:webhooks.write");
          toggle_button.textContent = integration.enabled === true ? "Disable" : "Enable";
          toggle_button.addEventListener("click", () => {
            toggle_button.toggleAttribute("disabled", true);
            void self._on_toggle_integration(integration, toggle_button);
          });
          return toggle_button;
        }
      }
    ];
    table.rows = this._integrations;
    el.replaceChildren(table);
    return;
  }
  async _on_toggle_integration(integration, button) {
    const next_enabled = integration.enabled !== true;
    if (next_enabled === false) {
      const confirmed = await confirm_action(this, "Disable the inbound integration " + integration.provider + "/" + integration.hook_name + "? The receiver will reject its deliveries until it is re-enabled.", "Disable integration");
      if (confirmed !== true) {
        button.toggleAttribute("disabled", false);
        return;
      }
    }
    const outcome = await this.updateIntegration(
      integration.webhook_id,
      next_enabled
    );
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._load_integrations();
    }
    return;
  }
  /**
   * PATCH an inbound integration's ``enabled`` flag. Exposed so
   * unit tests can drive a toggle without a row button.
   *
   * @param webhook_id The integration to update.
   * @param enabled The desired enabled state.
   *
   * @returns The update outcome.
   */
  async updateIntegration(webhook_id, enabled) {
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(
        build_integration_resource_url(webhook_id),
        {
          method: "PATCH",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ enabled })
        }
      );
      status = response.status;
      detail = await read_problem_detail(response);
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.integration_update_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: toggle_message_for_status(0, "Integration", enabled)
      };
      return rtnval2;
    }
    const ok = status === 200;
    const rtnval = {
      ok,
      status,
      message: message_with_detail("Integration not changed", detail, toggle_message_for_status(status, "Integration", enabled))
    };
    return rtnval;
  }
  _render_inbound_deliveries() {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="inbound-deliveries-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (this._inDeliveries.length === 0) {
      el.replaceChildren(this._notice("No recent inbound deliveries"));
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-ops__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.columns = [
      { key: "provider", label: "Provider", width: "10rem" },
      { key: "hook_name", label: "Hook", width: "10rem" },
      { key: "delivery_id", label: "Delivery id", width: "16rem", sortable: false },
      {
        key: "status",
        label: "Status",
        width: "8rem",
        sortable: false,
        // The ledger only proves receipt -- an honest "recorded"
        // chip, not a fabricated dispatch outcome.
        render: (delivery) => {
          const chip = self._badge("recorded", "neutral");
          chip.setAttribute(
            "title",
            "The replay ledger records that this delivery was received. Its dispatch outcome is not recorded yet."
          );
          return chip;
        }
      },
      {
        key: "first_seen_at",
        label: "First seen",
        width: "14rem",
        render: (delivery) => format_webhook_timestamp(delivery.first_seen_at)
      }
    ];
    table.rows = this._inDeliveries;
    el.replaceChildren(table);
    return;
  }
  _toggle_inbound_form(panel) {
    const region = panel.querySelector(
      '[data-role="inbound-form-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (el.hidden === true) {
      this._render_inbound_form(el);
      el.hidden = false;
    } else {
      el.hidden = true;
    }
    return;
  }
  _render_inbound_form(region) {
    const form = document.createElement("form");
    form.classList.add("pyc-ops__form");
    form.setAttribute("data-role", "inbound-form");
    const provider_input = this._build_field(
      form,
      "Provider",
      "inbound-provider",
      "generic"
    );
    const hook_input = this._build_field(
      form,
      "Hook name",
      "inbound-hook",
      "push"
    );
    const secret_label = document.createElement("label");
    secret_label.classList.add("pyc-ops__field");
    secret_label.textContent = "Shared secret";
    const secret_input = document.createElement("mj-password-field");
    secret_input.classList.add("pyc-ops__input");
    secret_input.setAttribute("type", "password");
    secret_input.setAttribute("autocomplete", "new-password");
    secret_input.setAttribute("data-role", "inbound-secret");
    secret_input.setAttribute("placeholder", "the HMAC key the sender signs with");
    secret_label.appendChild(secret_input);
    form.appendChild(secret_label);
    const secret_ref_input = this._build_field(
      form,
      "Or an existing vault secret",
      "inbound-secret-ref",
      "vault secret name (instead of a shared secret)"
    );
    const secret_note = document.createElement("p");
    secret_note.classList.add("pyc-ops__note");
    secret_note.setAttribute("data-role", "inbound-secret-note");
    secret_note.textContent = "The shared secret is stored in the secrets vault for this project and is never displayed again. Storing it needs permission to write the project's secrets.";
    form.appendChild(secret_note);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-ops__submit");
    submit.setAttribute("variant", "primary");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "inbound-submit");
    submit.textContent = "Create Integration";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-ops__form-status");
    status.setAttribute("data-role", "inbound-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_inbound(
        provider_input,
        hook_input,
        secret_input,
        secret_ref_input,
        submit,
        status
      );
    });
    region.replaceChildren(form);
    return;
  }
  async _submit_inbound(provider_input, hook_input, secret_input, secret_ref_input, submit, status) {
    const provider = provider_input.value.trim();
    const hook_name = hook_input.value.trim();
    const secret = typeof secret_input.value === "string" ? secret_input.value : "";
    const secret_ref = secret_ref_input.value.trim();
    if (provider.length === 0 || hook_name.length === 0) {
      status.textContent = "Provider and hook name are required.";
      return;
    }
    if (secret.length === 0 && secret_ref.length === 0) {
      status.textContent = "Enter the shared secret, or name an existing vault secret.";
      return;
    }
    if (secret.length > 0 && secret_ref.length > 0) {
      status.textContent = "Enter either a shared secret or a vault secret name, not both.";
      return;
    }
    submit.toggleAttribute("disabled", true);
    status.textContent = "Creating integration\u2026";
    const outcome = await this._do_create_integration(
      provider,
      hook_name,
      secret,
      secret_ref
    );
    secret_input.value = "";
    submit.toggleAttribute("disabled", false);
    status.textContent = outcome.ok === true ? "" : outcome.message;
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      provider_input.value = "";
      hook_input.value = "";
      secret_ref_input.value = "";
      await this.refreshInbound();
    }
    return;
  }
  /**
   * POST an inbound-integration create request. Exposed so unit
   * tests can invoke a create without a real form-submit event.
   *
   * @param provider The webhook provider name.
   * @param hook_name The hook name.
   * @param secret The shared secret (stored in the vault; write-only),
   *               or an empty string when ``secret_ref`` is used.
   * @param secret_ref Name of an existing vault secret, or an empty
   *                   string when ``secret`` is supplied.
   *
   * @returns The create outcome.
   */
  async createIntegration(provider, hook_name, secret, secret_ref = "") {
    const rtnval = await this._do_create_integration(
      provider,
      hook_name,
      secret,
      secret_ref
    );
    return rtnval;
  }
  async _do_create_integration(provider, hook_name, secret, secret_ref) {
    if (this._projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        message: this._project_prompt() + " before creating an integration."
      };
      return rtnval2;
    }
    const payload = {
      project_id: this._projectId,
      provider,
      hook_name
    };
    if (typeof secret === "string" && secret.length > 0) {
      payload.secret = secret;
    }
    if (typeof secret_ref === "string" && secret_ref.length > 0) {
      payload.secret_ref = secret_ref;
    }
    let status = 0;
    let problem = null;
    try {
      const response = await fetch(
        build_integrations_collection_url(),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify(payload)
        }
      );
      status = response.status;
      if (response.ok === false) {
        try {
          problem = await response.json();
        } catch (parse_reason) {
          problem = null;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.integration_create_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: "Failed to reach the webhooks service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    let message = create_message_for_status(status, "Integration");
    if (ok === false) {
      message = problem_message_for_status(status, problem, "Integration");
    }
    const rtnval = {
      ok,
      status,
      message
    };
    return rtnval;
  }
  // ----------------------------------------------------------------
  // Outbound tab
  // ----------------------------------------------------------------
  /**
   * Render the outbound-panel scaffolding -- create-form toggle,
   * refresh action, one-time signing-secret region, subscriptions
   * table region, delivery-history region.
   */
  _render_outbound_panel() {
    if (this._panel_region === null) {
      return;
    }
    const panel = document.createElement("div");
    panel.classList.add("pyc-ops__panel");
    panel.setAttribute("data-role", "outbound-panel");
    const actions = document.createElement("div");
    actions.classList.add("pyc-ops__controls");
    const create_button = document.createElement("mj-button");
    create_button.classList.add("pyc-ops__button");
    create_button.setAttribute("type", "button");
    create_button.setAttribute("data-role", "outbound-create-toggle");
    hide_unless_may(create_button, "system:webhooks.write");
    create_button.textContent = "Create Subscription";
    create_button.addEventListener("click", () => {
      this._toggle_outbound_form(panel);
    });
    actions.appendChild(create_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-ops__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "outbound-refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this.refreshOutbound();
    });
    actions.appendChild(refresh_button);
    panel.appendChild(actions);
    const form_region = document.createElement("div");
    form_region.classList.add("pyc-ops__form-region");
    form_region.setAttribute("data-role", "outbound-form-region");
    form_region.hidden = true;
    panel.appendChild(form_region);
    const secret_region = document.createElement("div");
    secret_region.classList.add("pyc-ops__secret-region");
    secret_region.setAttribute("data-role", "signing-secret-region");
    secret_region.hidden = true;
    panel.appendChild(secret_region);
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-ops__table-region");
    table_region.setAttribute("data-role", "outbound-table-region");
    panel.appendChild(table_region);
    const history_region = document.createElement("div");
    history_region.classList.add("pyc-ops__table-region");
    history_region.setAttribute("data-role", "outbound-history-region");
    panel.appendChild(history_region);
    this._panel_region.replaceChildren(panel);
    this._render_signing_secret();
    this._render_outbound_table();
    return;
  }
  /**
   * Fetch the outbound subscriptions and re-render. When a
   * delivery-history panel is open its data is re-fetched too so
   * the panel never goes stale. Exposed so unit tests can await
   * a fetch cycle.
   */
  async refreshOutbound() {
    if (this._projectId.length === 0) {
      this._subscriptions = [];
      this._historySubscription = null;
      this._render_outbound_table();
      this._render_outbound_history(null, []);
      return;
    }
    let items = null;
    try {
      const url = build_subscriptions_url(this._projectId);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (Array.isArray(page.items) === true) {
          items = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.subscriptions_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._subscriptions = items ?? [];
    this._render_outbound_table();
    if (this._historySubscription !== null) {
      const open_subscription = this._historySubscription;
      const deliveries = await this.loadSubscriptionDeliveries(
        open_subscription.subscription_id
      );
      this._render_outbound_history(open_subscription, deliveries);
    }
    return;
  }
  _render_outbound_table() {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="outbound-table-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (this._projectId.length === 0) {
      el.replaceChildren(
        this._notice(this._project_prompt() + " to view subscriptions.")
      );
      return;
    }
    if (this._subscriptions.length === 0) {
      el.replaceChildren(
        build_empty_state({ class_name: "pyc-ops__notice", message: "No outbound subscriptions for this project yet.", next_step: "Choose Create Subscription above to add one." })
      );
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-ops__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowAttrs = (subscription) => ({
      "data-subscription-id": subscription.subscription_id
    });
    table.columns = [
      { key: "name", label: "Name", width: "12rem" },
      { key: "url", label: "URL", width: "20rem", sortable: false },
      {
        key: "topic_filters",
        label: "Topics",
        width: "16rem",
        sortable: false,
        render: (subscription) => subscription.topic_filters.join(", ") || "all"
      },
      {
        key: "enabled",
        label: "State",
        width: "8rem",
        render: (subscription) => self._badge(
          subscription.enabled === true ? "enabled" : "disabled",
          subscription.enabled === true ? "ok" : "neutral"
        )
      },
      {
        key: "actions",
        label: "Actions",
        width: "22rem",
        sortable: false,
        render: (subscription) => {
          const fragment = document.createDocumentFragment();
          const test_button = document.createElement("mj-button");
          test_button.classList.add("pyc-ops__button", "pyc-ops__row-action");
          test_button.setAttribute("type", "button");
          test_button.setAttribute("data-role", "test-event");
          test_button.textContent = "Send Test Event";
          test_button.addEventListener("click", () => {
            test_button.toggleAttribute("disabled", true);
            void self._on_test(subscription, test_button);
          });
          fragment.appendChild(test_button);
          const history_button = document.createElement("mj-button");
          history_button.classList.add(
            "pyc-ops__button",
            "pyc-ops__row-action"
          );
          history_button.setAttribute("type", "button");
          history_button.setAttribute("data-role", "delivery-history");
          history_button.textContent = "Delivery History";
          history_button.addEventListener("click", () => {
            history_button.toggleAttribute("disabled", true);
            void self._on_history(subscription, history_button);
          });
          fragment.appendChild(history_button);
          const toggle_button = document.createElement("mj-button");
          toggle_button.classList.add(
            "pyc-ops__button",
            "pyc-ops__row-action"
          );
          toggle_button.setAttribute("type", "button");
          toggle_button.setAttribute("data-role", "subscription-toggle");
          hide_unless_may(toggle_button, "system:webhooks.write");
          toggle_button.textContent = subscription.enabled === true ? "Disable" : "Enable";
          toggle_button.addEventListener("click", () => {
            toggle_button.toggleAttribute("disabled", true);
            void self._on_toggle_subscription(subscription, toggle_button);
          });
          fragment.appendChild(toggle_button);
          return fragment;
        }
      }
    ];
    table.rows = this._subscriptions;
    el.replaceChildren(table);
    return;
  }
  async _on_toggle_subscription(subscription, button) {
    const next_enabled = subscription.enabled !== true;
    if (next_enabled === false) {
      const confirmed = await confirm_action(this, "Disable the subscription " + subscription.name + "? Deliveries to its URL stop until it is re-enabled.", "Disable subscription");
      if (confirmed !== true) {
        button.toggleAttribute("disabled", false);
        return;
      }
    }
    const outcome = await this.updateSubscription(
      subscription.subscription_id,
      next_enabled
    );
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this.refreshOutbound();
    }
    return;
  }
  /**
   * PATCH an outbound subscription's ``enabled`` flag. Exposed so
   * unit tests can drive a toggle without a row button.
   *
   * @param subscription_id The subscription to update.
   * @param enabled The desired enabled state.
   *
   * @returns The update outcome.
   */
  async updateSubscription(subscription_id, enabled) {
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(
        build_subscription_resource_url(subscription_id),
        {
          method: "PATCH",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ enabled })
        }
      );
      status = response.status;
      detail = await read_problem_detail(response);
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.subscription_update_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: toggle_message_for_status(0, "Subscription", enabled)
      };
      return rtnval2;
    }
    const ok = status === 200;
    const rtnval = {
      ok,
      status,
      message: message_with_detail("Subscription not changed", detail, toggle_message_for_status(status, "Subscription", enabled))
    };
    return rtnval;
  }
  async _on_test(subscription, button) {
    const outcome = await this._do_test(subscription.subscription_id);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.recorded === true) {
      this._schedule_history_refresh(subscription);
    }
    return;
  }
  /**
   * Schedule a short-delay refresh of the delivery history after
   * a test event, so the operator sees the recorded attempt
   * without hunting for a refresh control.
   *
   * @param subscription The subscription that was tested.
   */
  _schedule_history_refresh(subscription) {
    if (this._pendingHistoryTimer !== 0) {
      clearTimeout(this._pendingHistoryTimer);
    }
    this._pendingHistoryTimer = setTimeout(() => {
      this._pendingHistoryTimer = 0;
      void this._load_and_render_history(subscription);
    }, TEST_EVENT_HISTORY_REFRESH_MS);
    return;
  }
  async _load_and_render_history(subscription) {
    const deliveries = await this.loadSubscriptionDeliveries(
      subscription.subscription_id
    );
    this._historySubscription = subscription;
    this._render_outbound_history(subscription, deliveries);
    return;
  }
  /**
   * POST a test event for one subscription. Exposed so unit
   * tests can drive a test without a row button.
   *
   * @param subscription_id The subscription to test.
   *
   * @returns The test outcome.
   */
  async sendTestEvent(subscription_id) {
    const rtnval = await this._do_test(subscription_id);
    return rtnval;
  }
  async _do_test(subscription_id) {
    let status = 0;
    let delivery_outcome = "";
    let delivery = null;
    try {
      const response = await fetch(
        build_subscription_test_url(subscription_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify({})
        }
      );
      status = response.status;
      if (response.ok === true) {
        try {
          const body = await response.json();
          if (body !== null && typeof body === "object") {
            if (typeof body.status === "string") {
              delivery_outcome = body.status;
            }
            if (body.delivery !== null && typeof body.delivery === "object") {
              delivery = body.delivery;
            }
          }
        } catch (parse_reason) {
          delivery = null;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.test_event_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        recorded: false,
        status: 0,
        outcome: "",
        message: "Failed to reach the webhooks service."
      };
      return rtnval2;
    }
    const recorded = status === 202 || status === 200;
    const ok = status === 202 || status === 200 && delivery_outcome !== "failed";
    const rtnval = {
      ok,
      recorded,
      status,
      outcome: delivery_outcome,
      message: test_message_for_status(status, delivery_outcome, delivery)
    };
    return rtnval;
  }
  async _on_history(subscription, button) {
    await this._load_and_render_history(subscription);
    button.toggleAttribute("disabled", false);
    return;
  }
  /**
   * Fetch the delivery history for one subscription. Exposed so
   * unit tests can await the history fetch.
   *
   * @param subscription_id The subscription to read history for.
   *
   * @returns The delivery list (possibly empty).
   */
  async loadSubscriptionDeliveries(subscription_id) {
    let items = [];
    try {
      const url = build_subscription_deliveries_url(subscription_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (Array.isArray(page.items) === true) {
          items = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.out_deliveries_fetch_failed",
        { reason: String(reason) }
      );
    }
    const rtnval = items;
    return rtnval;
  }
  _render_outbound_history(subscription, deliveries) {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="outbound-history-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (subscription === null) {
      el.replaceChildren();
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-ops__subheading");
    heading.textContent = "Delivery History \u2014 " + subscription.name;
    if (deliveries.length === 0) {
      el.replaceChildren(
        heading,
        this._notice("No delivery attempts recorded")
      );
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-ops__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.columns = [
      { key: "topic", label: "Topic", width: "16rem" },
      {
        key: "outcome",
        label: "Outcome",
        width: "10rem",
        render: (delivery) => self._badge(
          delivery.outcome,
          delivery_outcome_tone(delivery.outcome)
        )
      },
      {
        key: "response_status",
        label: "HTTP",
        width: "8rem",
        render: (delivery) => delivery.response_status === null || delivery.response_status === void 0 ? "\u2014" : String(delivery.response_status)
      },
      {
        key: "response_excerpt",
        label: "Detail",
        width: "20rem",
        sortable: false,
        render: (delivery) => {
          const detail = document.createElement("span");
          detail.setAttribute("data-role", "delivery-detail");
          const text = typeof delivery.response_excerpt === "string" && delivery.response_excerpt.length > 0 ? delivery.response_excerpt : "\u2014";
          detail.textContent = text;
          detail.title = text;
          return detail;
        }
      },
      {
        key: "attempted_at",
        label: "Attempted",
        width: "14rem",
        render: (delivery) => format_webhook_timestamp(delivery.attempted_at)
      }
    ];
    table.rows = deliveries;
    el.replaceChildren(heading, table);
    return;
  }
  _toggle_outbound_form(panel) {
    const region = panel.querySelector(
      '[data-role="outbound-form-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (el.hidden === true) {
      this._render_outbound_form(el);
      el.hidden = false;
    } else {
      el.hidden = true;
    }
    return;
  }
  _render_outbound_form(region) {
    const form = document.createElement("form");
    form.classList.add("pyc-ops__form");
    form.setAttribute("data-role", "outbound-form");
    const name_input = this._build_field(
      form,
      "Name",
      "outbound-name",
      "release-notifier"
    );
    const url_input = this._build_field(
      form,
      "Target URL",
      "outbound-url",
      "https://hooks.example/x"
    );
    const topics_input = this._build_field(
      form,
      "Topic filters (comma-separated)",
      "outbound-topics",
      "entity.release.published"
    );
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-ops__submit");
    submit.setAttribute("variant", "primary");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "outbound-submit");
    submit.textContent = "Create Subscription";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-ops__form-status");
    status.setAttribute("data-role", "outbound-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_outbound(
        name_input,
        url_input,
        topics_input,
        submit,
        status
      );
    });
    region.replaceChildren(form);
    return;
  }
  async _submit_outbound(name_input, url_input, topics_input, submit, status) {
    const name = name_input.value.trim();
    const url = url_input.value.trim();
    if (name.length === 0 || url.length === 0) {
      status.textContent = "Name and target URL are required.";
      return;
    }
    const topic_filters = parse_topic_filters(topics_input.value);
    submit.toggleAttribute("disabled", true);
    status.textContent = "Creating subscription\u2026";
    const outcome = await this._do_create_subscription(
      name,
      url,
      topic_filters
    );
    submit.toggleAttribute("disabled", false);
    status.textContent = "";
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      if (typeof outcome.signingSecret === "string" && outcome.signingSecret.length > 0) {
        this._signingSecret = {
          name,
          secret: outcome.signingSecret
        };
      }
      await this.refreshOutbound();
      this._render_signing_secret();
    }
    return;
  }
  /**
   * Render (or hide) the one-time signing-secret panel from the
   * transient ``_signingSecret`` state. The secret is shown once
   * after creation and is never retrievable again -- dismissing
   * the panel drops it.
   */
  _render_signing_secret() {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="signing-secret-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (this._signingSecret === null) {
      el.replaceChildren();
      el.hidden = true;
      return;
    }
    const captured = this._signingSecret;
    const title = document.createElement("p");
    title.classList.add("pyc-ops__secret-title");
    title.textContent = "Signing secret for " + captured.name + " \u2014 save it now";
    const secret_code = document.createElement("code");
    secret_code.classList.add("pyc-ops__secret-value");
    secret_code.setAttribute("data-role", "signing-secret-value");
    secret_code.textContent = captured.secret;
    const copy_button = document.createElement("mj-button");
    copy_button.classList.add("pyc-ops__button", "pyc-ops__row-action");
    copy_button.setAttribute("type", "button");
    copy_button.setAttribute("data-role", "signing-secret-copy");
    copy_button.textContent = "Copy";
    copy_button.addEventListener("click", () => {
      if (typeof navigator !== "undefined" && navigator.clipboard !== void 0) {
        void navigator.clipboard.writeText(captured.secret);
        copy_button.textContent = "Copied";
      }
    });
    const dismiss_button = document.createElement("mj-button");
    dismiss_button.classList.add("pyc-ops__button", "pyc-ops__row-action");
    dismiss_button.setAttribute("type", "button");
    dismiss_button.setAttribute("data-role", "signing-secret-dismiss");
    dismiss_button.textContent = "Dismiss";
    dismiss_button.addEventListener("click", () => {
      this._signingSecret = null;
      this._render_signing_secret();
    });
    const note = document.createElement("p");
    note.classList.add("pyc-ops__note");
    note.textContent = "This secret is shown only once and cannot be retrieved later. Receivers verify deliveries by recomputing the X-Pychestrate-Signature header with it.";
    el.replaceChildren(title, secret_code, copy_button, dismiss_button, note);
    el.hidden = false;
    return;
  }
  /**
   * POST an outbound-subscription create request. Exposed so
   * unit tests can invoke a create without a real form-submit
   * event.
   *
   * @param name The subscription name.
   * @param url The target URL.
   * @param topic_filters The topic-filter list.
   *
   * @returns The create outcome. On success ``signingSecret``
   *          carries the one-time generated secret when the
   *          server returned one.
   */
  async createSubscription(name, url, topic_filters) {
    const rtnval = await this._do_create_subscription(
      name,
      url,
      topic_filters
    );
    return rtnval;
  }
  async _do_create_subscription(name, url, topic_filters) {
    if (this._projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        signingSecret: "",
        message: this._project_prompt() + " before creating a subscription."
      };
      return rtnval2;
    }
    const payload = {
      project_id: this._projectId,
      name,
      url,
      topic_filters
    };
    let status = 0;
    let detail = "";
    let signing_secret = "";
    try {
      const response = await fetch(WEBHOOKS_OUT_PATH, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      status = response.status;
      detail = await read_problem_detail(response);
      if (response.ok === true) {
        const body = await response.json();
        const created = body;
        if (created !== null && typeof created.signing_secret === "string") {
          signing_secret = created.signing_secret;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.subscription_create_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        signingSecret: "",
        message: "Failed to reach the webhooks service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      signingSecret: signing_secret,
      message: message_with_detail("Subscription not created", detail, create_message_for_status(status, "Subscription"))
    };
    return rtnval;
  }
  // ----------------------------------------------------------------
  // Shared DOM helpers
  // ----------------------------------------------------------------
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
  _build_field(form, label_text, role, placeholder) {
    const label = document.createElement("label");
    label.classList.add("pyc-ops__field");
    label.textContent = label_text;
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-ops__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", role);
    input.setAttribute("placeholder", placeholder);
    label.appendChild(input);
    form.appendChild(label);
    return input;
  }
  /**
   * Build a token-toned status badge span.
   *
   * @param text The badge label.
   * @param tone ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
   *
   * @returns The created badge span.
   */
  _badge(text, tone) {
    const badge = document.createElement("mj-chip");
    badge.classList.add("pyc-ops__badge");
    badge.setAttribute("data-tone", tone);
    badge.textContent = text;
    return badge;
  }
  /**
   * Build a notice paragraph for empty / placeholder states.
   *
   * @param text The notice text.
   *
   * @returns The created paragraph element.
   */
  _notice(text) {
    const notice = document.createElement("p");
    notice.classList.add("pyc-ops__notice");
    notice.textContent = text;
    return notice;
  }
  /**
   * Show a toast in the toast region through the shared service: one at a
   * time, announced to assistive technology, a plain success goes away by itself.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-ops" });
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-ops-bundle/release-channels-view.js
var RELEASE_CHANNELS_PATH = "/api/v1/release-channels";
var UPDATES_HEADING = "Pychestrate Updates";
var UPDATES_INTRO = "Releases of the Pychestrate service and its pod client, published to the canary, beta and stable update channels that installations follow. A project's own releases and channels are under that project.";
var RELEASE_CHANNEL_VALUES = [
  "canary",
  "beta",
  "stable"
];
function build_release_channel_url(channel_id) {
  const rtnval = RELEASE_CHANNELS_PATH + "/" + encodeURIComponent(channel_id);
  return rtnval;
}
function format_release_timestamp(value) {
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
function format_rollout(value) {
  if (typeof value !== "number" || Number.isNaN(value) === true) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const percent = value * 100;
  const rtnval = String(Math.round(percent)) + "%";
  return rtnval;
}
function release_status_tone(status) {
  if (typeof status !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = status.toLowerCase();
  if (lowered === "active" || lowered === "published") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "rolling_out" || lowered === "staged") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (lowered === "rolled_back" || lowered === "failed" || lowered === "revoked") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function extract_publishing_status(meta) {
  if (meta === null || meta === void 0 || typeof meta !== "object") {
    const rtnval2 = { available: true, reason: "" };
    return rtnval2;
  }
  const available = meta.publishing_available !== false;
  const reason = typeof meta.publishing_unavailable_reason === "string" ? meta.publishing_unavailable_reason : "";
  const rtnval = { available, reason };
  return rtnval;
}
function publish_message_for_status(status, detail) {
  const reason = typeof detail === "string" ? detail.trim() : "";
  if (status === 201 || status === 200) {
    const rtnval2 = "Release published to the channel.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "That version is already published on the channel.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = reason.length > 0 ? "The publish request was rejected: " + reason : "The publish request was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 503 && reason.length > 0) {
    const rtnval2 = reason;
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to publish releases.";
    return rtnval2;
  }
  const rtnval = "Failed to publish release (HTTP " + String(status) + ").";
  return rtnval;
}
var PycReleaseChannels = class extends HTMLElement {
  _entries;
  _loading;
  _errored;
  /**
   * The channel_id whose published-release detail is currently
   * shown, or ``""``. Refreshes re-fetch it instead of leaving
   * a stale panel behind.
   */
  _detailChannelId;
  _root;
  _table_region;
  _publish_region;
  _detail_region;
  _toast_region;
  _publishing;
  _publishing_region;
  _publish_toggle;
  constructor() {
    super();
    this._entries = [];
    this._loading = false;
    this._errored = false;
    this._publishing = { available: true, reason: "" };
    this._publishing_region = null;
    this._publish_toggle = null;
    this._detailChannelId = "";
    this._root = null;
    this._table_region = null;
    this._publish_region = null;
    this._detail_region = null;
    this._toast_region = null;
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
   * channels fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  /**
   * Build the persistent chrome -- heading, publish + refresh
   * actions, publish-form region, table region, detail region,
   * toast region.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-ops");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-ops__heading");
    heading.textContent = UPDATES_HEADING;
    root.appendChild(heading);
    const intro = document.createElement("p");
    intro.classList.add("pyc-ops__note");
    intro.setAttribute("data-role", "updates-intro");
    intro.textContent = UPDATES_INTRO;
    root.appendChild(intro);
    const publishing_region = document.createElement("p");
    publishing_region.classList.add("pyc-ops__notice", "pyc-ops__notice--preview");
    publishing_region.setAttribute("data-role", "publishing-unavailable");
    publishing_region.setAttribute("role", "note");
    publishing_region.hidden = true;
    root.appendChild(publishing_region);
    this._publishing_region = publishing_region;
    const controls = document.createElement("div");
    controls.classList.add("pyc-ops__controls");
    const publish_button = document.createElement("mj-button");
    publish_button.classList.add("pyc-ops__button");
    publish_button.setAttribute("type", "button");
    publish_button.setAttribute("data-role", "publish-toggle");
    hide_unless_may(publish_button, "system:release_channels.write");
    publish_button.textContent = "Publish Release";
    publish_button.addEventListener("click", () => {
      this._toggle_publish_form();
    });
    controls.appendChild(publish_button);
    this._publish_toggle = publish_button;
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-ops__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const publish_region = document.createElement("div");
    publish_region.classList.add("pyc-ops__form-region");
    publish_region.setAttribute("data-role", "publish-region");
    publish_region.hidden = true;
    root.appendChild(publish_region);
    this._publish_region = publish_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-ops__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-ops__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const detail_region = document.createElement("div");
    detail_region.classList.add("pyc-ops__table-region");
    detail_region.setAttribute("data-role", "detail-region");
    root.appendChild(detail_region);
    this._detail_region = detail_region;
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the release-channels list and re-render. Exposed so
   * unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._errored = false;
    this._render_table_region();
    let page = null;
    try {
      const response = await fetch(RELEASE_CHANNELS_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "release-channels fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.release_channels_fetch_failed",
        { reason: String(reason) }
      );
      this._loading = false;
      this._errored = true;
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._loading = false;
      this._errored = true;
      this._render_table_region();
      return;
    }
    this._entries = page.items;
    this._publishing = extract_publishing_status(page.meta);
    this._loading = false;
    this._errored = false;
    this._render_publishing_state();
    this._render_table_region();
    await this._refresh_open_detail();
    return;
  }
  /**
   * Say why publishing is unavailable (no release-signing key) and
   * disable the publish action, instead of letting a publish fail
   * with a bare HTTP status.
   */
  _render_publishing_state() {
    const available = this._publishing.available === true;
    if (this._publishing_region !== null) {
      this._publishing_region.hidden = available;
      this._publishing_region.textContent = available ? "" : this._publishing.reason.length > 0 ? this._publishing.reason : "Publishing is unavailable on this server.";
    }
    if (this._publish_toggle !== null) {
      this._publish_toggle.toggleAttribute("disabled", available === false);
    }
    if (available === false && this._publish_region !== null) {
      this._publish_region.hidden = true;
    }
    return;
  }
  /**
   * Re-fetch the open detail panel (if any) so it never shows a
   * stale entry after a list refresh. When the entry can no
   * longer be read the panel clears instead of lingering.
   */
  async _refresh_open_detail() {
    if (this._detailChannelId.length === 0) {
      return;
    }
    const detail = await this.loadReleaseChannel(this._detailChannelId);
    if (detail === null) {
      this._detailChannelId = "";
      if (this._detail_region !== null) {
        this._detail_region.replaceChildren();
      }
      return;
    }
    this._render_detail(detail);
    return;
  }
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-ops__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading published updates\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._errored === true) {
      const error = document.createElement("p");
      error.classList.add("pyc-ops__notice", "pyc-ops__notice--error");
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load the published updates. Try refreshing.";
      region.replaceChildren(error);
      return;
    }
    if (this._entries.length === 0) {
      const empty = build_empty_state({ class_name: "pyc-ops__notice", message: "No Pychestrate updates published to any channel yet.", next_step: "Choose Publish Release above to publish one." });
      region.replaceChildren(empty);
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    return;
  }
  _build_table() {
    const self = this;
    const ordered = this._entries.slice();
    ordered.sort(
      (left, right) => {
        const left_key = left.component + "/" + left.channel;
        const right_key = right.component + "/" + right.channel;
        if (left_key < right_key) {
          return -1;
        }
        if (left_key > right_key) {
          return 1;
        }
        return 0;
      }
    );
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-ops__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowAttrs = (entry) => ({ "data-channel-id": entry.channel_id });
    table.columns = [
      { key: "component", label: "Component", width: "12rem" },
      {
        key: "channel",
        label: "Channel",
        width: "8rem",
        render: (entry) => {
          const channel_badge = document.createElement("mj-chip");
          channel_badge.classList.add("pyc-ops__badge");
          channel_badge.setAttribute("data-tone", "neutral");
          channel_badge.textContent = entry.channel;
          return channel_badge;
        }
      },
      { key: "version", label: "Version", width: "8rem" },
      {
        key: "status",
        label: "Status",
        width: "10rem",
        render: (entry) => {
          const status_badge = document.createElement("mj-chip");
          status_badge.classList.add("pyc-ops__badge");
          status_badge.setAttribute(
            "data-tone",
            release_status_tone(entry.status)
          );
          status_badge.textContent = entry.status;
          return status_badge;
        }
      },
      {
        key: "rollout_fraction",
        label: "Rollout",
        width: "8rem",
        render: (entry) => format_rollout(entry.rollout_fraction)
      },
      {
        key: "issued_at",
        label: "Issued",
        width: "12rem",
        render: (entry) => format_release_timestamp(entry.issued_at)
      },
      {
        key: "actions",
        label: "Actions",
        width: "14rem",
        sortable: false,
        render: (entry) => {
          const show_button = document.createElement("mj-button");
          show_button.classList.add("pyc-ops__button", "pyc-ops__row-action");
          show_button.setAttribute("type", "button");
          show_button.setAttribute("data-role", "show-release");
          show_button.textContent = "Show Published Release";
          show_button.addEventListener("click", () => {
            show_button.toggleAttribute("disabled", true);
            void self._on_show_release(entry, show_button);
          });
          return show_button;
        }
      }
    ];
    table.rows = ordered;
    return table;
  }
  async _on_show_release(entry, button) {
    const detail = await this.loadReleaseChannel(entry.channel_id);
    button.toggleAttribute("disabled", false);
    this._detailChannelId = entry.channel_id;
    this._render_detail(detail);
    return;
  }
  /**
   * Read one release-channel entry's published-release detail.
   * Exposed so unit tests can await the detail fetch.
   *
   * @param channel_id The entry to read.
   *
   * @returns The entry, or ``null`` when the read fails.
   */
  async loadReleaseChannel(channel_id) {
    let entry = null;
    try {
      const url = build_release_channel_url(channel_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const parsed = body;
        if (parsed !== null && typeof parsed.channel_id === "string") {
          entry = parsed;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.release_channel_fetch_failed",
        { reason: String(reason) }
      );
    }
    const rtnval = entry;
    return rtnval;
  }
  _render_detail(entry) {
    if (this._detail_region === null) {
      return;
    }
    const region = this._detail_region;
    if (entry === null) {
      const error = document.createElement("p");
      error.classList.add("pyc-ops__notice", "pyc-ops__notice--error");
      error.setAttribute("data-role", "detail-error");
      error.textContent = "Failed to load the published release.";
      region.replaceChildren(error);
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-ops__subheading");
    heading.textContent = "Published Release \u2014 " + entry.component + " " + entry.version;
    const list = document.createElement("dl");
    list.classList.add("pyc-ops__detail-list");
    list.setAttribute("data-role", "release-detail");
    this._append_detail_pair(list, "Channel", entry.channel);
    this._append_detail_pair(list, "Status", entry.status);
    this._append_detail_pair(
      list,
      "Rollout",
      format_rollout(entry.rollout_fraction)
    );
    this._append_detail_pair(list, "Artifact URI", entry.artifact_uri);
    this._append_detail_pair(
      list,
      "Artifact SHA-256",
      entry.artifact_sha256
    );
    this._append_detail_pair(
      list,
      "Issued by",
      entry.issued_by ?? "\u2014"
    );
    this._append_detail_pair(
      list,
      "Issued at",
      format_release_timestamp(entry.issued_at)
    );
    region.replaceChildren(heading, list);
    return;
  }
  _append_detail_pair(list, label, value) {
    const term = document.createElement("dt");
    term.classList.add("pyc-ops__detail-term");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.classList.add("pyc-ops__detail-value");
    detail.textContent = value;
    list.appendChild(term);
    list.appendChild(detail);
    return;
  }
  _toggle_publish_form() {
    if (this._publish_region === null) {
      return;
    }
    const region = this._publish_region;
    if (region.hidden === true) {
      this._render_publish_form();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  _render_publish_form() {
    if (this._publish_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-ops__form");
    form.setAttribute("data-role", "publish-form");
    const component_input = this._build_field(
      form,
      "Component",
      "publish-component",
      "agent-runtime"
    );
    const channel_label = document.createElement("label");
    channel_label.classList.add("pyc-ops__field");
    channel_label.textContent = "Channel";
    const channel_select = document.createElement("mj-select");
    channel_select.classList.add("pyc-ops__select");
    channel_select.setAttribute("data-role", "publish-channel");
    for (const channel of RELEASE_CHANNEL_VALUES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", channel);
      option.textContent = channel;
      channel_select.appendChild(option);
    }
    channel_select.value = RELEASE_CHANNEL_VALUES[0];
    channel_label.appendChild(channel_select);
    form.appendChild(channel_label);
    const version_input = this._build_field(
      form,
      "Version",
      "publish-version",
      "1.4.0"
    );
    const uri_input = this._build_field(
      form,
      "Artifact URI",
      "publish-uri",
      "oci://registry/x:1.4.0"
    );
    const sha_input = this._build_field(
      form,
      "Artifact SHA-256 (64 hex chars)",
      "publish-sha",
      ""
    );
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-ops__submit");
    submit.setAttribute("variant", "primary");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "publish-submit");
    submit.textContent = "Publish Release";
    form.appendChild(submit);
    const rollout_note = document.createElement("p");
    rollout_note.classList.add("pyc-ops__note");
    rollout_note.setAttribute("data-role", "publish-rollout-note");
    rollout_note.textContent = "The rollout starts at the channel policy's initial fraction. Promote and rollback controls arrive with the next release-service milestone.";
    form.appendChild(rollout_note);
    const status = document.createElement("p");
    status.classList.add("pyc-ops__form-status");
    status.setAttribute("data-role", "publish-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_publish(
        component_input,
        channel_select,
        version_input,
        uri_input,
        sha_input,
        submit,
        status
      );
    });
    this._publish_region.replaceChildren(form);
    return;
  }
  async _submit_publish(component_input, channel_select, version_input, uri_input, sha_input, submit, status) {
    const component = component_input.value.trim();
    const channel = channel_select.value;
    const version = version_input.value.trim();
    const artifact_uri = uri_input.value.trim();
    const artifact_sha256 = sha_input.value.trim();
    if (component.length === 0 || version.length === 0 || artifact_uri.length === 0) {
      status.textContent = "Component, version and artifact URI are required.";
      return;
    }
    if (typeof channel !== "string" || channel.length === 0) {
      status.textContent = "Select a release channel.";
      return;
    }
    if (RELEASE_CHANNEL_VALUES.includes(channel) === false) {
      status.textContent = "The channel must be one of: " + RELEASE_CHANNEL_VALUES.join(", ") + ".";
      return;
    }
    if (artifact_sha256.length !== 64) {
      status.textContent = "Artifact SHA-256 must be 64 hexadecimal characters.";
      return;
    }
    submit.toggleAttribute("disabled", true);
    status.textContent = "Publishing release\u2026";
    const outcome = await this._do_publish(
      component,
      channel,
      version,
      artifact_uri,
      artifact_sha256
    );
    submit.toggleAttribute("disabled", false);
    status.textContent = "";
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * POST a release-publish request. Exposed so unit tests can
   * invoke a publish without a real form-submit event.
   *
   * @param component The component being published.
   * @param channel The target channel.
   * @param version The release version string.
   * @param artifact_uri The release artifact URI.
   * @param artifact_sha256 The 64-hex-char artifact digest.
   *
   * @returns The publish outcome.
   */
  async publishRelease(component, channel, version, artifact_uri, artifact_sha256) {
    const rtnval = await this._do_publish(
      component,
      channel,
      version,
      artifact_uri,
      artifact_sha256
    );
    return rtnval;
  }
  async _do_publish(component, channel, version, artifact_uri, artifact_sha256) {
    const payload = {
      component,
      channel,
      version,
      artifact_uri,
      artifact_sha256
    };
    let status = 0;
    let channel_id = "";
    let detail = "";
    try {
      const response = await fetch(RELEASE_CHANNELS_PATH, {
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
        const entry = body;
        if (entry !== null && typeof entry.channel_id === "string") {
          channel_id = entry.channel_id;
        }
      } else {
        try {
          const problem = await response.json();
          if (problem !== null && typeof problem === "object" && typeof problem.detail === "string") {
            detail = problem.detail;
          }
        } catch (parse_reason) {
          detail = "";
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.release_publish_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        channelId: "",
        message: "Failed to reach the release-channels service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      channelId: channel_id,
      message: publish_message_for_status(status, detail)
    };
    return rtnval;
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
  _build_field(form, label_text, role, placeholder) {
    const label = document.createElement("label");
    label.classList.add("pyc-ops__field");
    label.textContent = label_text;
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-ops__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", role);
    input.setAttribute("placeholder", placeholder);
    label.appendChild(input);
    form.appendChild(label);
    return input;
  }
  /**
   * Show a toast in the toast region through the shared service: one at a
   * time, announced to assistive technology, a plain success goes away by itself.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-ops" });
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-ops-bundle/index.entry.js
var OPERATIONS_GROUP_ID = "operations";
var WEBHOOKS_READ_PERMISSION = "system:webhooks.read";
var RELEASE_CHANNELS_READ_PERMISSION = "system:release_channels.read";
var WEBHOOKS_ROUTE = "/webhooks";
var RELEASE_CHANNELS_ROUTE = "/release-channels";
var WEBHOOKS_TAG = "pyc-webhooks";
var RELEASE_CHANNELS_TAG = "pyc-release-channels";
var OPS_STYLESHEET_HREF = "/static/javascript/pyc-ops-bundle/pyc-ops-bundle.css";
function ensure_ops_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-ops-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = OPS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-ops-bundle");
  document.head.appendChild(link);
  return;
}
var WEBHOOKS_ENTRY = {
  entryId: "operations.webhooks",
  label: "Webhooks",
  route: WEBHOOKS_ROUTE,
  requiredPermissions: [WEBHOOKS_READ_PERMISSION],
  group: OPERATIONS_GROUP_ID
};
var RELEASE_CHANNELS_ENTRY = {
  entryId: "admin.pychestrate-updates",
  label: "Pychestrate Updates",
  route: RELEASE_CHANNELS_ROUTE,
  requiredPermissions: [RELEASE_CHANNELS_READ_PERMISSION],
  group: "admin"
};
function register_ops_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: OPERATIONS_GROUP_ID,
    label: "Operations",
    requiredPermissions: [WEBHOOKS_READ_PERMISSION]
  });
  sidebar.registerEntry(WEBHOOKS_ENTRY);
  sidebar.registerEntry(RELEASE_CHANNELS_ENTRY);
  return;
}
function define_ops_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(WEBHOOKS_TAG) === void 0) {
    customElements.define(WEBHOOKS_TAG, PycWebhooks);
  }
  if (customElements.get(RELEASE_CHANNELS_TAG) === void 0) {
    customElements.define(RELEASE_CHANNELS_TAG, PycReleaseChannels);
  }
  return;
}
function classify_ops_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === WEBHOOKS_ROUTE || working.startsWith(WEBHOOKS_ROUTE + "/") === true) {
    const rtnval2 = "webhooks";
    return rtnval2;
  }
  if (working === RELEASE_CHANNELS_ROUTE || working.startsWith(RELEASE_CHANNELS_ROUTE + "/") === true) {
    const rtnval2 = "release-channels";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_ops_route(route) {
  if (route === "webhooks") {
    const rtnval2 = WEBHOOKS_TAG;
    return rtnval2;
  }
  if (route === "release-channels") {
    const rtnval2 = RELEASE_CHANNELS_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_ops_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_ops_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_ops_route(route);
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
  define_ops_elements();
  ensure_ops_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_ops_view_if_active();
  return;
}
function _boot() {
  define_ops_elements();
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
      "pychestrate.ui.ops.bundle_no_shell_handle",
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
  PycReleaseChannels,
  PycWebhooks,
  RELEASE_CHANNEL_VALUES,
  UPDATES_HEADING,
  build_in_deliveries_url,
  build_integrations_collection_url,
  build_integrations_url,
  build_release_channel_url,
  build_subscription_deliveries_url,
  build_subscription_test_url,
  build_subscriptions_url,
  classify_ops_route,
  create_message_for_status,
  define_ops_elements,
  delivery_outcome_tone,
  ensure_ops_stylesheet,
  extract_publishing_status,
  format_release_timestamp,
  format_rollout,
  format_webhook_timestamp,
  mount_ops_view_if_active,
  parse_topic_filters,
  publish_message_for_status,
  register_ops_sidebar,
  release_status_tone,
  tag_for_ops_route,
  test_message_for_status
};
