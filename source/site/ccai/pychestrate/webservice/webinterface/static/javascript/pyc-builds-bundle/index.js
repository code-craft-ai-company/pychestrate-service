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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/admin-contact.js
function with_access_request(message) {
  if (typeof message !== "string" || message.startsWith("You do not have permission") === false) {
    return message;
  }
  if (/administrator|contact/i.test(message) === true) {
    return message;
  }
  const sentence = access_request_sentence();
  return sentence.length > 0 ? message + " " + sentence : message;
}
function access_request_sentence() {
  if (typeof document === "undefined") {
    return "";
  }
  const shell = document.querySelector("pyc-site-shell");
  const contact = shell === null ? "" : (shell.getAttribute("admin-contact") || "").trim();
  return contact.length > 0 ? "To ask for access, contact " + contact + "." : "";
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
  text.textContent = with_access_request(message);
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
function format_duration(started, finished, still_running, now) {
  const start = parse_timestamp(started);
  if (start === null) {
    return "\u2014";
  }
  let end = parse_timestamp(finished);
  let open = false;
  if (end === null) {
    if (still_running !== true) {
      return "\u2014";
    }
    end = now instanceof Date ? now : /* @__PURE__ */ new Date();
    open = true;
  }
  const total = Math.max(0, Math.round((end.getTime() - start.getTime()) / 1e3));
  let text;
  if (total < 1) {
    text = "< 1s";
  } else if (total < 60) {
    text = String(total) + "s";
  } else if (total < 3600) {
    text = String(Math.floor(total / 60)) + "m " + String(total % 60) + "s";
  } else if (total < 86400) {
    text = String(Math.floor(total / 3600)) + "h " + String(Math.floor(total % 3600 / 60)) + "m";
  } else {
    text = String(Math.floor(total / 86400)) + "d " + String(Math.floor(total % 86400 / 3600)) + "h";
  }
  return open ? text + " so far" : text;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/run-labels.js
function build_title(build) {
  const kind = typeof build.runner_kind === "string" && build.runner_kind.length > 0 ? build.runner_kind : "build";
  const inputs = build.inputs !== null && typeof build.inputs === "object" ? build.inputs : {};
  const target = typeof inputs.target === "string" ? inputs.target.trim() : "";
  return target.length > 0 ? kind + " \xB7 " + target : kind;
}
function build_source_label(build) {
  const source = build.source;
  if (source === null || source === void 0 || typeof source !== "object") {
    return "";
  }
  const ref = typeof source.ref === "string" ? source.ref : "";
  let repository = typeof source.url === "string" ? source.url : "";
  repository = repository.replace(/^[a-z+]+:\/\//i, "").replace(/\.git$/i, "").replace(/^[^@/]*@/, "");
  if (ref.length > 0 && repository.length > 0) {
    return ref + " @ " + repository;
  }
  return ref.length > 0 ? ref : repository;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/view-state.js
function query_value(name) {
  if (typeof window === "undefined") {
    return "";
  }
  const value = new URLSearchParams(window.location.search).get(name);
  return value === null ? "" : value.trim();
}
function query_choice(name, allowed) {
  const value = query_value(name);
  return allowed.indexOf(value) >= 0 ? value : "";
}
function page_from_query() {
  const parsed = Number.parseInt(query_value("page"), 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1;
}
function mirror_to_query(values) {
  if (typeof window === "undefined" || typeof window.history === "undefined") {
    return;
  }
  const url = new URL(window.location.href);
  for (const name of Object.keys(values)) {
    const value = values[name];
    if (typeof value === "string" && value.length > 0) {
      url.searchParams.set(name, value);
    } else {
      url.searchParams.delete(name);
    }
  }
  const next = url.pathname + url.search + url.hash;
  if (next !== window.location.pathname + window.location.search + window.location.hash) {
    window.history.replaceState(window.history.state, "", next);
  }
}
function keep_list_state_on_back(anchor, list_path) {
  anchor.addEventListener("click", (event) => {
    try {
      const from = new URL(document.referrer);
      if (from.origin === window.location.origin && from.pathname === list_path && window.history.length > 1) {
        event.preventDefault();
        window.history.back();
      }
    } catch (reason) {
    }
  });
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/reveal.js
var CONTROL_SELECTOR = [
  "mj-text-field",
  "mj-textarea",
  "mj-select",
  'input:not([type="hidden"]):not([disabled])',
  "select:not([disabled])",
  "textarea:not([disabled])"
].join(", ");
var HEADING_SELECTOR = "h1, h2, h3, h4";
function focus_target_for(region, wanted) {
  if (typeof wanted === "string") {
    const found = region.querySelector(wanted);
    return found;
  }
  if (wanted !== null && wanted !== void 0) {
    return wanted;
  }
  const control = region.querySelector(CONTROL_SELECTOR);
  if (control !== null) {
    return control;
  }
  const heading = region.querySelector(HEADING_SELECTOR);
  const target = heading !== null ? heading : region;
  if (target.hasAttribute("tabindex") === false) {
    target.setAttribute("tabindex", "-1");
  }
  return target;
}
function reveal(region, options) {
  if (region === null || region === void 0 || region.hidden === true || region.isConnected !== true) {
    return null;
  }
  const settings = options !== null && typeof options === "object" ? options : {};
  const target = focus_target_for(region, settings.focus);
  if (target !== null && target !== void 0 && typeof target.focus === "function") {
    target.focus();
  }
  const box = region.getBoundingClientRect();
  const height = window.innerHeight || document.documentElement.clientHeight;
  if (box.top < 0 || box.bottom > height) {
    region.scrollIntoView({ block: box.height > height ? "start" : "nearest", behavior: "auto" });
  }
  const focused = target !== null && target !== void 0 ? target : null;
  return focused;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-builds-bundle/builds-list-view.js
var BUILD_STATES = [
  "pending",
  "running",
  "completed",
  "failed",
  "cancelled"
];
var TERMINAL_BUILD_STATES = [
  "completed",
  "failed",
  "cancelled"
];
var DEFAULT_PER_PAGE = 25;
var PROJECTS_API_PATH = "/api/v1/projects";
var PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
function build_builds_query_url(state) {
  const params = new URLSearchParams();
  if (state.stateFilter.length > 0) {
    params.set("state", state.stateFilter);
  }
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  const query = params.toString();
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(state.projectId) + "/builds?" + query;
  return rtnval;
}
function build_builds_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/builds";
  return rtnval;
}
function build_build_detail_link(project_id, run_id) {
  const rtnval = "/builds/" + encodeURIComponent(run_id) + "?project_id=" + encodeURIComponent(project_id);
  return rtnval;
}
function build_source_integrations_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/source-integrations";
  return rtnval;
}
function short_id(value) {
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
function build_state_tone(build_state) {
  if (build_state === "completed") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (build_state === "failed") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (build_state === "cancelled") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function is_terminal_build_state(build_state) {
  const rtnval = TERMINAL_BUILD_STATES.indexOf(build_state) >= 0;
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
function trigger_message_for_status(status) {
  if (status === 202 || status === 200 || status === 201) {
    const rtnval2 = "Build triggered.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "Runner inputs were rejected \u2014 check the runner kind.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project or runner kind.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to trigger builds.";
    return rtnval2;
  }
  const rtnval = "Failed to trigger build (HTTP " + String(status) + ").";
  return rtnval;
}
function list_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to builds.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This project was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the build service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load builds (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function announce_session_expired() {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(
    new CustomEvent("pyc-session-401", {
      bubbles: false,
      detail: {}
    })
  );
  return;
}
function parse_runner_inputs(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = {};
    return rtnval2;
  }
  const parsed = JSON.parse(raw);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
    throw new SyntaxError("runner inputs must be a JSON object");
  }
  const rtnval = parsed;
  return rtnval;
}
function project_from_search() {
  if (typeof window === "undefined") {
    const rtnval2 = "";
    return rtnval2;
  }
  const value = new URLSearchParams(window.location.search).get("project_id");
  const rtnval = value === null ? "" : value.trim();
  return rtnval;
}
function preferred_project_id(projects) {
  const requested = project_from_search();
  const match = projects.find((project) => project.project_id === requested || project.slug === requested);
  const rtnval = match !== void 0 ? match.project_id : projects[0].project_id;
  return rtnval;
}
var PycBuildsList = class extends HTMLElement {
  _pager;
  _state;
  _builds;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _integrations;
  _root;
  _table_region;
  _trigger_region;
  _toast_region;
  _projects_notice_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      stateFilter: query_choice("state", BUILD_STATES),
      page: page_from_query(),
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false,
      errorStatus: 0
    };
    this._builds = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._integrations = [];
    this._root = null;
    this._table_region = null;
    this._pager = null;
    this._trigger_region = null;
    this._toast_region = null;
    this._projects_notice_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + pagination state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
      stateFilter: this._state.stateFilter,
      page: this._state.page,
      perPage: this._state.perPage,
      total: this._state.total,
      loading: this._state.loading,
      errored: this._state.errored,
      errorStatus: this._state.errorStatus
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
   * state filter, trigger action, table region, pager, toast.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-builds");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-builds__heading");
    heading.textContent = "Builds";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-builds__controls");
    const project_label = document.createElement("div");
    project_label.classList.add("pyc-builds__field");
    const project_select = document.createElement("mj-select");
    project_select.setAttribute("label", "Project");
    project_select.classList.add("pyc-builds__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      this._state.page = 1;
      void this._on_project_changed();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-builds__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("label", "Project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectId = project_input.value.trim();
      this._state.page = 1;
      void this._on_project_changed();
    });
    controls.appendChild(project_input);
    const state_label = document.createElement("div");
    state_label.classList.add("pyc-builds__field");
    const state_select = document.createElement("mj-select");
    state_select.setAttribute("label", "State");
    state_select.classList.add("pyc-builds__select");
    state_select.setAttribute("data-role", "state-filter");
    const any_option = document.createElement("mj-option");
    any_option.setAttribute("value", "");
    any_option.textContent = "All states";
    state_select.appendChild(any_option);
    for (const build_state of BUILD_STATES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", build_state);
      option.textContent = build_state;
      state_select.appendChild(option);
    }
    state_select.value = this._state.stateFilter;
    state_select.addEventListener("change", () => {
      this._state.stateFilter = state_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    state_label.appendChild(state_select);
    controls.appendChild(state_label);
    const trigger_button = document.createElement("mj-button");
    trigger_button.classList.add("pyc-builds__button");
    trigger_button.setAttribute("type", "button");
    trigger_button.setAttribute("data-role", "trigger-toggle");
    hide_unless_may(trigger_button, "system:builds.create");
    trigger_button.textContent = "Trigger Build";
    trigger_button.addEventListener("click", () => {
      this._toggle_trigger_form();
    });
    controls.appendChild(trigger_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-builds__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-builds__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    const trigger_region = document.createElement("div");
    trigger_region.classList.add("pyc-builds__trigger-region");
    trigger_region.setAttribute("data-role", "trigger-region");
    trigger_region.hidden = true;
    root.appendChild(trigger_region);
    this._trigger_region = trigger_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-builds__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    toast_region.setAttribute("role", "status");
    toast_region.setAttribute("aria-live", "polite");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-builds__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");
    pager.classList.add("pyc-builds__pager");
    pager.setAttribute("data-role", "pager");
    pager.setAttribute("page", String(this._state.page));
    pager.setAttribute("page-size", String(this._state.perPage));
    pager.setAttribute("total-items", String(this._state.total));
    pager.addEventListener("mj-pagination-change", (event) => {
      this._state.page = event.detail.page;
      void this._refresh();
    });
    this._pager = pager;
    root.appendChild(pager);
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
    let load_status = 0;
    let load_failed = false;
    try {
      const response = await fetch(PROJECTS_LIST_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      load_status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        projects = this._extract_projects(body);
      } else {
        load_failed = true;
      }
    } catch (reason) {
      load_failed = true;
      console.warn(
        "pychestrate.ui.builds.projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._projectsNoticeKind = "";
      this._state.projectId = preferred_project_id(projects);
    } else {
      this._projects = [];
      this._projectsAvailable = false;
      if (load_failed === false) {
        this._projectsNoticeKind = "empty";
      } else if (load_status === 403) {
        this._projectsNoticeKind = "forbidden";
      } else {
        this._projectsNoticeKind = "error";
      }
      if (load_status === 401) {
        announce_session_expired();
      }
    }
    this._render_project_control();
    this._render_projects_notice();
    if (this._state.projectId.length > 0) {
      await this._on_project_changed();
    } else {
      this._render_table_region();
    }
    return;
  }
  /**
   * Render the projects-load notice -- explains why the project
   * selector degraded to the manual id input (no projects exist
   * yet, no permission to list them, or a failed fetch with a
   * retry control).
   */
  _render_projects_notice() {
    if (this._projects_notice_region === null) {
      return;
    }
    const region = this._projects_notice_region;
    if (this._projectsNoticeKind === "") {
      region.hidden = true;
      region.replaceChildren();
      return;
    }
    region.hidden = false;
    if (this._projectsNoticeKind === "empty") {
      region.classList.remove("pyc-builds__projects-notice--error");
      const message2 = document.createElement("span");
      message2.textContent = "No projects exist yet. Builds belong to a project, so create one first. ";
      const create = document.createElement("a");
      create.classList.add("pyc-builds__build-link");
      create.setAttribute("href", "/projects/create");
      create.setAttribute("data-role", "create-project");
      create.textContent = "Create a project";
      region.replaceChildren(message2, create);
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-builds__projects-notice--error");
      region.textContent = "You don't have permission to list projects.";
      return;
    }
    region.classList.add("pyc-builds__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-builds__button");
    retry.setAttribute("type", "button");
    retry.setAttribute("data-role", "projects-retry");
    retry.textContent = "Retry";
    retry.addEventListener("click", () => {
      void this._load_projects();
    });
    region.replaceChildren(message, retry);
    return;
  }
  /**
   * Normalise a projects-list response body into ``ProjectOption``
   * records. Accepts both a bare array and a ``{items}`` page
   * envelope so the view tolerates either shape.
   *
   * @param body Parsed JSON response body.
   *
   * @returns A list of project options (possibly empty).
   */
  _extract_projects(body) {
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
   * React to a project change -- reload the source integrations
   * (so the trigger form's selector is fresh) and the builds
   * page.
   */
  async _on_project_changed() {
    await this._load_integrations();
    await this._refresh();
    return;
  }
  /**
   * Fetch the active project's source integrations. A failed
   * fetch leaves the integrations list empty -- the trigger form
   * degrades to a manual integration-id-free flow.
   */
  async _load_integrations() {
    this._integrations = [];
    if (this._state.projectId.length === 0) {
      return;
    }
    try {
      const url = build_source_integrations_url(this._state.projectId);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        this._integrations = this._extract_integrations(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.integrations_fetch_failed",
        { reason: String(reason) }
      );
    }
    return;
  }
  /**
   * Normalise a source-integrations page body into option
   * records.
   *
   * @param body Parsed JSON response body.
   *
   * @returns A list of source integration options.
   */
  _extract_integrations(body) {
    let raw = [];
    if (body !== null && typeof body === "object") {
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
      const integration_id = record.integration_id;
      const project_id = record.project_id;
      const provider_name = record.provider_name;
      const repo_key = record.repo_key;
      if (typeof integration_id !== "string" || typeof project_id !== "string" || typeof provider_name !== "string" || typeof repo_key !== "string") {
        continue;
      }
      rtnval.push({
        integration_id,
        project_id,
        provider_name,
        repo_key
      });
    }
    return rtnval;
  }
  /**
   * Fetch the current page of builds and re-render the table.
   * Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._builds = [];
      this._render_table_region();
      return;
    }
    mirror_to_query({
      project_id: this._state.projectId,
      state: this._state.stateFilter,
      page: this._state.page > 1 ? String(this._state.page) : ""
    });
    this._state.loading = true;
    this._state.errored = false;
    this._render_table_region();
    const url = build_builds_query_url(this._state);
    let page = null;
    let fetch_status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      fetch_status = response.status;
      if (response.ok === false) {
        throw new Error("builds fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.list_fetch_failed",
        { reason: String(reason) }
      );
      if (fetch_status === 401) {
        announce_session_expired();
      }
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = fetch_status;
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = fetch_status;
      this._render_table_region();
      return;
    }
    this._builds = page.items;
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
    this._render_table_region();
    return;
  }
  /**
   * Re-render the table region from the current state + builds.
   */
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.projectId.length === 0) {
      if (this._projectsNoticeKind === "empty") {
        region.replaceChildren();
        this._render_pager();
        return;
      }
      const notice = document.createElement("p");
      notice.classList.add("pyc-builds__status");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its builds.";
      region.replaceChildren(notice);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-builds__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading builds\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add("pyc-builds__status", "pyc-builds__status--error");
      error.setAttribute("data-role", "error-state");
      error.textContent = list_load_message_for_status(this._state.errorStatus);
      const children = [error];
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-builds__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "list-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._refresh();
        });
        children.push(retry);
      }
      region.replaceChildren(...children);
      this._render_pager();
      return;
    }
    if (this._builds.length === 0) {
      const empty = build_empty_state({ class_name: "pyc-builds__status", message: "No builds in this project yet. Choose Trigger Build above to start one." });
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
   * Build the builds ``<table>`` from the current ``_builds``
   * list.
   */
  _build_table() {
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-builds__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-builds__row";
    table.rowAttrs = (build) => ({ "data-build-id": build.run_id });
    table.columns = [
      {
        // What ran comes first (runner and target); the short id follows.
        key: "run_id",
        label: "Build",
        width: "14rem",
        render: (build) => {
          const cell = document.createElement("span");
          const link = document.createElement("a");
          link.classList.add("pyc-builds__build-link");
          link.setAttribute(
            "href",
            build_build_detail_link(build.project_id, build.run_id)
          );
          link.textContent = build_title(build);
          link.title = build.run_id;
          cell.appendChild(link);
          const id = document.createElement("span");
          id.classList.add("pyc-builds__build-id");
          id.textContent = " " + short_id(build.run_id);
          cell.appendChild(id);
          return cell;
        }
      },
      {
        key: "source",
        label: "Source",
        width: "14rem",
        sortable: false,
        render: (build) => {
          const label = build_source_label(build);
          return label.length > 0 ? label : "\u2014";
        }
      },
      {
        key: "state",
        label: "State",
        width: "8rem",
        render: (build) => {
          const badge = document.createElement("mj-chip");
          badge.classList.add("pyc-builds__badge");
          badge.setAttribute("data-tone", build_state_tone(build.state));
          badge.textContent = build.state;
          return badge;
        }
      },
      {
        key: "repro_digest_sha256",
        label: "Inputs digest",
        width: "9rem",
        render: (build) => {
          const digest = document.createElement("span");
          digest.classList.add("pyc-builds__digest");
          digest.textContent = short_id(build.repro_digest_sha256);
          digest.title = build.repro_digest_sha256;
          return digest;
        }
      },
      {
        key: "started_at",
        label: "Started",
        width: "11rem",
        render: (build) => format_timestamp(build.started_at)
      },
      {
        key: "duration",
        label: "Duration",
        width: "8rem",
        sortable: false,
        render: (build) => format_duration(build.started_at, build.finished_at, build.state === "running")
      }
    ];
    table.rows = this._builds;
    return table;
  }
  /**
   * Update the pager controls -- enabled state + the page
   * indicator label -- from the current state.
   */
  _render_pager() {
    if (this._pager === null || this._pager === void 0) {
      return;
    }
    this._pager.setAttribute("page", String(this._state.page));
    this._pager.setAttribute("page-size", String(this._state.perPage));
    this._pager.setAttribute("total-items", String(this._state.total));
    return;
  }
  /**
   * Toggle the inline trigger-build form's visibility, rendering
   * it on first reveal.
   */
  _toggle_trigger_form() {
    if (this._trigger_region === null) {
      return;
    }
    const region = this._trigger_region;
    if (region.hidden === true) {
      this._render_trigger_form();
      region.hidden = false;
      reveal(region);
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the trigger-build form into the trigger region -- a
   * source-integration selector, a runner-kind input, a runner-
   * inputs JSON textarea, and a submit button.
   */
  _render_trigger_form() {
    if (this._trigger_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-builds__trigger-form");
    form.setAttribute("data-role", "trigger-form");
    const integration_label = document.createElement("div");
    integration_label.classList.add("pyc-builds__field");
    const integration_select = document.createElement("mj-select");
    integration_select.setAttribute("label", "Source integration");
    integration_select.classList.add("pyc-builds__select");
    integration_select.setAttribute("data-role", "trigger-integration");
    if (this._integrations.length === 0) {
      const none_option = document.createElement("mj-option");
      none_option.setAttribute("value", "");
      none_option.textContent = "No source integration registered";
      integration_select.appendChild(none_option);
    } else {
      const first_id = this._integrations[0].integration_id;
      for (const integration of this._integrations) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", integration.integration_id);
        option.textContent = integration.provider_name + " \xB7 " + integration.repo_key;
        if (integration.integration_id === first_id) {
          option.setAttribute("selected", "");
        }
        integration_select.appendChild(option);
      }
      const none_option = document.createElement("mj-option");
      none_option.setAttribute("value", "");
      none_option.textContent = "None \u2014 the runner inputs name the repository";
      integration_select.appendChild(none_option);
      integration_select.value = first_id;
    }
    integration_label.appendChild(integration_select);
    form.appendChild(integration_label);
    const runner_label = document.createElement("div");
    runner_label.classList.add("pyc-builds__field");
    const runner_input = document.createElement("mj-text-field");
    runner_input.setAttribute("label", "Runner kind");
    runner_input.classList.add("pyc-builds__input");
    runner_input.setAttribute("type", "text");
    runner_input.setAttribute("placeholder", "makefile");
    runner_input.setAttribute("data-role", "trigger-runner-kind");
    runner_input.required = true;
    runner_label.appendChild(runner_input);
    form.appendChild(runner_label);
    const inputs_label = document.createElement("label");
    inputs_label.classList.add("pyc-builds__field", "pyc-builds__field--wide");
    inputs_label.textContent = "Runner inputs (JSON)";
    const inputs_area = document.createElement("mj-textarea");
    inputs_area.classList.add("pyc-builds__textarea");
    inputs_area.setAttribute("data-role", "trigger-runner-inputs");
    inputs_area.setAttribute("placeholder", '{"targets": ["all"]}');
    inputs_area.rows = 3;
    inputs_label.appendChild(inputs_area);
    form.appendChild(inputs_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-builds__trigger");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "trigger-submit");
    submit_button.textContent = "Trigger Build";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-builds__trigger-status");
    status.setAttribute("data-role", "trigger-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_trigger(
        form,
        integration_select,
        runner_input,
        inputs_area,
        submit_button
      );
    });
    this._trigger_region.replaceChildren(form);
    return;
  }
  /**
   * Submit the trigger-build form -- POST a
   * ``BuildRunCreateRequest`` and surface the outcome. Exposed so
   * unit tests can invoke a trigger without a real form-submit
   * event.
   *
   * @param runner_kind The runner-kind identifier.
   * @param runner_inputs Free-form runner inputs object.
   * @param source_integration_id The chosen source integration id,
   *                              or an empty string for none.
   *
   * @returns The trigger outcome.
   */
  async triggerBuild(runner_kind, runner_inputs, source_integration_id = "") {
    const rtnval = await this._do_trigger(
      runner_kind,
      runner_inputs,
      source_integration_id
    );
    return rtnval;
  }
  async _submit_trigger(form, integration_select, runner_input, inputs_area, submit_button) {
    const status = form.querySelector('[data-role="trigger-status"]');
    const runner_kind = runner_input.value.trim();
    if (runner_kind.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Runner kind is required.";
      }
      return;
    }
    let runner_inputs = {};
    try {
      runner_inputs = parse_runner_inputs(inputs_area.value);
    } catch (reason) {
      if (status instanceof HTMLElement) {
        status.textContent = "Runner inputs must be valid JSON.";
      }
      console.warn(
        "pychestrate.ui.builds.trigger_inputs_invalid",
        { reason: String(reason) }
      );
      return;
    }
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Triggering build\u2026";
    }
    const source_integration_id = typeof integration_select.value === "string" ? integration_select.value.trim() : "";
    const outcome = await this._do_trigger(
      runner_kind,
      runner_inputs,
      source_integration_id
    );
    submit_button.toggleAttribute("disabled", false);
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._show_trigger_toast(outcome);
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  async _do_trigger(runner_kind, runner_inputs, source_integration_id = "") {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        buildId: "",
        message: "Select a project before triggering a build."
      };
      return rtnval2;
    }
    const payload = {
      runner_kind,
      runner_inputs
    };
    if (typeof source_integration_id === "string" && source_integration_id.length > 0) {
      payload.source_integration_id = source_integration_id;
    }
    let status = 0;
    let build_id = "";
    let detail = "";
    try {
      const url = build_builds_collection_url(this._state.projectId);
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
        const run = body;
        if (run !== null && typeof run.run_id === "string") {
          build_id = run.run_id;
        }
      } else if (status === 409 || status === 422) {
        try {
          const problem = await response.json();
          if (problem !== null && typeof problem.detail === "string") {
            detail = problem.detail.split(/\r?\n/).map((line) => line.trim()).filter((line) => line.length > 0).join(" ");
          }
        } catch (parse_reason) {
          detail = "";
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.trigger_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        buildId: "",
        message: "Failed to reach the build service."
      };
      return rtnval2;
    }
    const ok = status === 202 || status === 200 || status === 201;
    const rtnval = {
      ok,
      status,
      buildId: build_id,
      message: detail.length > 0 ? "Build not triggered: " + detail : trigger_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Render a dismissible toast for a trigger outcome -- on
   * success the toast links to the new build's detail page.
   *
   * @param outcome The trigger-build outcome.
   */
  _show_trigger_toast(outcome) {
    show_toast(this._toast_region, outcome.message, outcome.ok === true ? "ok" : "error", {
      class_prefix: "pyc-builds",
      data_role: "trigger-toast",
      link: outcome.ok === true && outcome.buildId.length > 0 ? { href: build_build_detail_link(this._state.projectId, outcome.buildId), text: "View build", data_role: "trigger-toast-link" } : null
    });
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/page-title.js
var SECTION_TITLE_KEY = "pycSectionTitle";
var ENTITY_TITLE_KEY = "pycEntityTitle";
function set_entity_title(entity_label) {
  if (typeof entity_label !== "string" || entity_label.trim().length === 0) {
    return;
  }
  const root = document.documentElement;
  if (root.dataset[ENTITY_TITLE_KEY] === void 0 || document.title !== root.dataset[ENTITY_TITLE_KEY]) {
    root.dataset[SECTION_TITLE_KEY] = document.title;
  }
  const title = entity_label.trim() + " \xB7 " + root.dataset[SECTION_TITLE_KEY];
  root.dataset[ENTITY_TITLE_KEY] = title;
  document.title = title;
  return;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/run-project.js
async function project_of_run(run_id) {
  try {
    const response = await fetch("/api/v1/runs/" + encodeURIComponent(run_id), {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    if (response.ok === false) {
      return "";
    }
    const body = await response.json();
    return body !== null && typeof body === "object" && typeof body.project_id === "string" ? body.project_id : "";
  } catch (reason) {
    return "";
  }
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/entity-names.js
var PROJECTS_URL = "/api/v1/projects?per_page=500";
async function fetch_items(url) {
  try {
    const response = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    if (response.ok === false) {
      return [];
    }
    const body = await response.json();
    if (Array.isArray(body) === true) {
      return body;
    }
    return body !== null && typeof body === "object" && Array.isArray(body.items) === true ? body.items : [];
  } catch (reason) {
    return [];
  }
}
async function fetch_project_names() {
  const names = {};
  for (const item of await fetch_items(PROJECTS_URL)) {
    if (item !== null && typeof item === "object" && typeof item.project_id === "string") {
      const name = typeof item.display_name === "string" && item.display_name.length > 0 ? item.display_name : "";
      if (name.length > 0) {
        names[item.project_id] = name;
      }
    }
  }
  return names;
}
function name_or_short(names, id) {
  if (typeof id !== "string" || id.length === 0) {
    return "\u2014";
  }
  const known = names[id];
  if (typeof known === "string" && known.length > 0) {
    return known;
  }
  const dash = id.indexOf("-");
  return dash > 0 ? id.slice(0, dash) : id.slice(0, 8);
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/run-artifacts.js
var SCHEME_PATTERN = /^[a-z][a-z0-9+.-]*:\/\//i;
var INLINE_EXTENSIONS = [".txt", ".log", ".jsos", ".json", ".yaml", ".yml", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"];
function served_artifact_path(entry) {
  if (entry === null || typeof entry !== "object") {
    return "";
  }
  const uri = typeof entry.storage_uri === "string" ? entry.storage_uri : "";
  if (SCHEME_PATTERN.test(uri) === true) {
    return "";
  }
  const payload = entry.payload !== null && typeof entry.payload === "object" ? entry.payload : {};
  const stored = typeof payload.relative_path === "string" && payload.relative_path.length > 0 ? payload.relative_path : uri;
  if (stored.length === 0 || SCHEME_PATTERN.test(stored) === true || stored.startsWith("/") === true) {
    return "";
  }
  return stored;
}
function run_artifact_url(run_id, artifact_path) {
  const encoded = artifact_path.split("/").map((segment) => encodeURIComponent(segment)).join("/");
  return "/api/v1/runs/" + encodeURIComponent(run_id) + "/artifacts/" + encoded;
}
function opens_in_browser(artifact_path) {
  const lower = artifact_path.toLowerCase();
  return INLINE_EXTENSIONS.some((extension) => lower.endsWith(extension));
}
function format_bytes(size) {
  if (typeof size !== "number" || Number.isFinite(size) === false || size < 0) {
    return "";
  }
  if (size < 1024) {
    return String(size) + " B";
  }
  const units = ["KB", "MB", "GB"];
  let value = size / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value = value / 1024;
    unit = unit + 1;
  }
  return String(Math.round(value * 10) / 10) + " " + units[unit];
}
function tail_lines(text, count) {
  const lines = text.replace(/\r\n/g, "\n").replace(/\n$/, "").split("\n");
  if (lines.length <= count) {
    return { text: lines.join("\n"), cut: false, total: lines.length };
  }
  return { text: lines.slice(lines.length - count).join("\n"), cut: true, total: lines.length };
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-builds-bundle/build-detail-view.js
var PROJECTS_API_PATH2 = "/api/v1/projects";
var POLL_INTERVAL_MS = 5e3;
var LOG_INLINE_MAX_BYTES = 512 * 1024;
var LOG_TAIL_LINES = 200;
var LOG_TAIL_MAX_CHARS = 2e4;
var UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function build_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/builds/";
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
function project_id_from_search(search) {
  if (typeof search !== "string" || search.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const params = new URLSearchParams(search);
  const value = params.get("project_id");
  if (value === null) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = value;
  return rtnval;
}
function is_valid_build_id(build_id) {
  if (typeof build_id !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(build_id);
  return rtnval;
}
function detail_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to builds.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This build was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the build service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load this build (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function build_detail_url(project_id, build_id) {
  const rtnval = PROJECTS_API_PATH2 + "/" + encodeURIComponent(project_id) + "/builds/" + encodeURIComponent(build_id);
  return rtnval;
}
function build_artifacts_url(project_id, build_id) {
  const rtnval = PROJECTS_API_PATH2 + "/" + encodeURIComponent(project_id) + "/builds/" + encodeURIComponent(build_id) + "/artifacts";
  return rtnval;
}
var PycBuildDetail = class extends HTMLElement {
  _build_id;
  _project_id;
  _build;
  _artifacts;
  _project_names;
  _loading;
  _errored;
  _error_kind;
  _error_status;
  _terminal;
  _poll_status;
  _poll_timer;
  _root;
  _log;
  constructor() {
    super();
    this._build_id = "";
    this._project_id = "";
    this._build = null;
    this._artifacts = [];
    this._project_names = {};
    this._loading = false;
    this._errored = false;
    this._error_kind = "";
    this._error_status = 0;
    this._terminal = false;
    this._poll_status = "idle";
    this._poll_timer = null;
    this._root = null;
    this._log = { path: "", status: "idle", text: "", cut: false, total: 0, size: null };
  }
  /**
   * Observed attributes -- ``build-id`` and ``project-id`` may be
   * supplied explicitly by a host; otherwise they are read from
   * the URL on mount.
   */
  static get observedAttributes() {
    const rtnval = ["build-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      buildId: this._build_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored,
      errorKind: this._error_kind,
      errorStatus: this._error_status,
      pollStatus: this._poll_status,
      terminal: this._terminal
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the build + project ids, render the
   * chrome, and fetch the initial snapshot. The project id rides
   * on the detail link's ``?project_id=`` query parameter because
   * builds are only addressable through the project-scoped API.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("build-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._build_id = attr_id;
    } else {
      this._build_id = build_id_from_path(window.location.pathname);
    }
    const attr_project = this.getAttribute("project-id");
    if (attr_project !== null && attr_project.length > 0) {
      this._project_id = attr_project;
    } else {
      this._project_id = project_id_from_search(window.location.search);
    }
    this._render_chrome();
    void this._load();
    return;
  }
  /**
   * Lifecycle hook -- stop the live-poll timer so a navigation
   * away from the build never leaks a timer.
   */
  disconnectedCallback() {
    this._stop_poll();
    return;
  }
  /**
   * Fetch the build snapshot + artifacts then -- when the build
   * is not already terminal -- start the live-poll loop. Exposed
   * so unit tests can await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_build_id(this._build_id) === false) {
      this._loading = false;
      this._errored = true;
      this._error_kind = "invalid-id";
      this._render_body();
      return;
    }
    if (this._project_id.length === 0) {
      this._project_id = await project_of_run(this._build_id);
      if (this._project_id.length > 0) {
        mirror_to_query({ project_id: this._project_id });
      }
    }
    if (this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._error_kind = "missing-project";
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._error_kind = "";
    this._render_body();
    const build = await this._fetch_build();
    if (build === null) {
      this._loading = false;
      this._errored = true;
      this._error_kind = "http";
      this._render_body();
      return;
    }
    this._build = build;
    this._project_id = build.project_id;
    this._loading = false;
    this._errored = false;
    this._terminal = is_terminal_build_state(build.state);
    this._render_body();
    void this._load_project_names();
    await this._load_artifacts();
    if (this._terminal === false) {
      this._start_poll();
    } else {
      this._poll_status = "stopped";
      this._render_poll_banner();
    }
    return;
  }
  /**
   * Fetch the current build snapshot from the project-scoped
   * endpoint -- builds have no project-agnostic resolver, so the
   * project id must already be known (threaded through the detail
   * link's ``?project_id=`` query parameter).
   *
   * @returns The ``BuildRun`` snapshot, or ``null`` on failure.
   */
  async _fetch_build() {
    const url = build_detail_url(this._project_id, this._build_id);
    this._error_status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      this._error_status = response.status;
      if (response.ok === false) {
        if (response.status === 401) {
          announce_session_expired();
        }
        throw new Error("build fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      this._error_status = 0;
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.detail_fetch_failed",
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  /**
   * Fetch the build's artifact manifest. A failed fetch leaves
   * the artifacts list empty -- the section renders an empty
   * state rather than an error.
   */
  /**
   * Fetch the project names once and show the project by name; a failed
   * fetch leaves the short id in place.
   */
  async _load_project_names() {
    this._project_names = await fetch_project_names();
    if (this._build !== null) {
      this._render_body();
    }
    return;
  }
  async _load_artifacts() {
    if (this._project_id.length === 0) {
      return;
    }
    try {
      const url = build_artifacts_url(this._project_id, this._build_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (page !== null && Array.isArray(page.items) === true) {
          this._artifacts = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.artifacts_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._render_artifacts();
    void this._maybe_load_log();
    return;
  }
  /**
   * Start the live-poll loop. A no-op when a poll is already
   * scheduled.
   */
  _start_poll() {
    if (this._poll_timer !== null) {
      return;
    }
    this._poll_status = "polling";
    this._render_poll_banner();
    this._schedule_poll();
    return;
  }
  _schedule_poll() {
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
   * Run one poll cycle -- re-fetch the build snapshot, re-render,
   * and either reschedule (still non-terminal) or stop (now
   * terminal). Exposed so unit tests can drive a poll cycle
   * without waiting on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    const build = await this._fetch_build();
    if (build !== null) {
      this._build = build;
      this._project_id = build.project_id;
      this._terminal = is_terminal_build_state(build.state);
      this._render_body();
      await this._load_artifacts();
    }
    if (this._terminal === true) {
      this._stop_poll();
      this._poll_status = "stopped";
      this._render_poll_banner();
      return;
    }
    this._schedule_poll();
    return;
  }
  /**
   * Stop the live-poll loop, clearing any pending timer.
   */
  _stop_poll() {
    if (this._poll_timer !== null) {
      clearTimeout(this._poll_timer);
      this._poll_timer = null;
    }
    return;
  }
  /**
   * Build the persistent chrome -- heading, back link, the poll
   * banner, and the body region the data render replaces.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-build-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Build detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-build-detail__heading");
    heading.textContent = "Build detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-build-detail__back-link");
    back.setAttribute("href", "/builds");
    back.setAttribute("data-role", "back-link");
    keep_list_state_on_back(back, "/builds");
    back.textContent = "Back to builds";
    root.appendChild(back);
    const banner = document.createElement("p");
    banner.classList.add("pyc-build-detail__banner");
    banner.setAttribute("data-role", "poll-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;
    root.appendChild(banner);
    const body = document.createElement("div");
    body.classList.add("pyc-build-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Re-render the body region from the current build snapshot,
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
      loading.classList.add("pyc-build-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading build\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._build === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-build-detail__status",
        "pyc-build-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      if (this._error_kind === "missing-project") {
        error.textContent = "No build with this id could be found, or you do not have access to it. Open builds from the Builds list.";
      } else if (this._error_kind === "invalid-id") {
        error.textContent = "This build link is not valid \u2014 open the build from the Builds list.";
      } else {
        error.textContent = detail_load_message_for_status(this._error_status);
      }
      const children = [error];
      if (this._error_kind === "http") {
        if (this._error_status === 0 || this._error_status >= 500) {
          const retry = document.createElement("mj-button");
          retry.classList.add("pyc-build-detail__retry");
          retry.setAttribute("type", "button");
          retry.setAttribute("data-role", "detail-retry");
          retry.textContent = "Retry";
          retry.addEventListener("click", () => {
            void this._load();
          });
          children.push(retry);
        }
      }
      body.replaceChildren(...children);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._build));
    if (this._build.toolchain !== void 0 && this._build.toolchain !== null) {
      if (this._build.toolchain.length > 0) {
        fragment.appendChild(this._build_toolchain(this._build.toolchain));
      }
    }
    const log_section = document.createElement("section");
    log_section.classList.add("pyc-build-detail__log");
    log_section.setAttribute("data-role", "log-section");
    log_section.setAttribute("role", "region");
    log_section.setAttribute("aria-label", "Build log");
    fragment.appendChild(log_section);
    const artifacts_section = document.createElement("section");
    artifacts_section.classList.add("pyc-build-detail__artifacts");
    artifacts_section.setAttribute("data-role", "artifacts-section");
    artifacts_section.setAttribute("role", "region");
    artifacts_section.setAttribute("aria-label", "Artifacts");
    fragment.appendChild(artifacts_section);
    body.replaceChildren(fragment);
    this._render_artifacts();
    this._render_log();
    return;
  }
  /**
   * Build the build summary block -- identity, state badge,
   * runner kind, reproducibility digest, timestamps, and the
   * final-state reason.
   *
   * @param build The current build snapshot.
   *
   * @returns A populated summary section element.
   */
  _build_summary(build) {
    const section = document.createElement("section");
    section.classList.add("pyc-build-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Build summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-build-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-build-detail__build-id");
    id_value.setAttribute("data-role", "build-id");
    id_value.textContent = short_id(build.run_id);
    set_entity_title("Build " + short_id(build.run_id));
    id_value.title = build.run_id;
    id_row.appendChild(id_value);
    const badge = document.createElement("mj-chip");
    badge.classList.add("pyc-build-detail__badge");
    badge.setAttribute("data-role", "state-badge");
    badge.setAttribute("data-tone", build_state_tone(build.state));
    badge.textContent = build.state;
    id_row.appendChild(badge);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-build-detail__grid");
    this._append_field(grid, "Project", name_or_short(this._project_names, build.project_id), {
      href: "/projects/" + encodeURIComponent(build.project_id),
      value_title: build.project_id
    });
    this._append_field(grid, "Runner kind", build.runner_kind);
    this._append_field(grid, "Inputs digest", build.repro_digest_sha256, {
      title: "SHA-256 of the build's input files, toolchain and environment. Two builds with the same digest were made from the same inputs."
    });
    this._append_field(grid, "Started", format_timestamp(build.started_at));
    this._append_field(grid, "Finished", format_timestamp(build.finished_at));
    const layer5 = build.layer5_run_id;
    if (layer5 !== void 0 && layer5 !== null && layer5.length > 0) {
      this._append_field(grid, "Run", layer5, { href: "/runs/" + encodeURIComponent(layer5) });
    }
    const reason = build.final_state_reason;
    if (reason !== void 0 && reason !== null && reason.length > 0) {
      this._append_field(grid, "Final state reason", reason);
    }
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
  _append_field(grid, label, value, options) {
    const field = document.createElement("div");
    field.classList.add("pyc-build-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    if (options !== void 0 && typeof options.href === "string") {
      const link = document.createElement("a");
      link.href = options.href;
      link.textContent = value;
      if (typeof options.value_title === "string") {
        link.title = options.value_title;
      }
      def.appendChild(link);
    } else {
      def.textContent = value;
      if (options !== void 0 && typeof options.value_title === "string") {
        def.title = options.value_title;
      }
    }
    if (options !== void 0 && typeof options.title === "string") {
      term.title = options.title;
    }
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  /**
   * Build the toolchain-snapshot section -- one row per pinned
   * toolchain entry.
   *
   * @param toolchain The build's toolchain snapshot rows.
   *
   * @returns A populated toolchain section element.
   */
  _build_toolchain(toolchain) {
    const section = document.createElement("section");
    section.classList.add("pyc-build-detail__toolchain");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Toolchain");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-build-detail__section-heading");
    heading.textContent = "Toolchain";
    section.appendChild(heading);
    const list = document.createElement("ul");
    list.classList.add("pyc-build-detail__toolchain-list");
    for (const entry of toolchain) {
      const item = document.createElement("li");
      item.classList.add("pyc-build-detail__toolchain-entry");
      const key = document.createElement("strong");
      key.textContent = entry.key;
      item.appendChild(key);
      const version = entry.version;
      if (version !== void 0 && version !== null && version.length > 0) {
        const version_el = document.createElement("span");
        version_el.textContent = " " + version;
        item.appendChild(version_el);
      }
      list.appendChild(item);
    }
    section.appendChild(list);
    return section;
  }
  /**
   * Render the artifacts section from the current ``_artifacts``
   * list -- a heading plus one row per artifact, or an empty
   * state.
   */
  _render_artifacts() {
    if (this._root === null) {
      return;
    }
    const section = this._root.querySelector('[data-role="artifacts-section"]');
    if (section === null) {
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-build-detail__section-heading");
    heading.textContent = "Artifacts";
    const list = document.createElement("ul");
    list.classList.add("pyc-build-detail__artifact-list");
    list.setAttribute("data-role", "artifact-list");
    if (this._artifacts.length === 0) {
      const empty = document.createElement("li");
      empty.classList.add("pyc-build-detail__artifact-empty");
      empty.setAttribute("data-role", "artifacts-empty");
      empty.textContent = "No artifacts recorded for this build.";
      list.appendChild(empty);
    } else {
      for (const artifact of this._artifacts) {
        const item = document.createElement("li");
        item.classList.add("pyc-build-detail__artifact");
        const name = document.createElement("span");
        name.classList.add("pyc-build-detail__artifact-name");
        const display = artifact.artifact_name;
        name.textContent = display !== void 0 && display !== null && display.length > 0 ? display : artifact.artifact_id;
        item.appendChild(name);
        const payload = artifact.payload !== null && typeof artifact.payload === "object" ? artifact.payload : {};
        const size = format_bytes(payload.size_bytes);
        if (size.length > 0) {
          const size_el = document.createElement("span");
          size_el.classList.add("pyc-build-detail__artifact-size");
          size_el.textContent = size;
          item.appendChild(size_el);
        }
        const served = served_artifact_path(artifact);
        if (served.length > 0) {
          const link = document.createElement("a");
          link.classList.add("pyc-build-detail__artifact-link");
          link.setAttribute("href", run_artifact_url(this._build_id, served));
          link.setAttribute("rel", "noopener noreferrer");
          if (opens_in_browser(served) === true) {
            link.setAttribute("target", "_blank");
            link.textContent = "Open";
          } else {
            link.setAttribute("download", "");
            link.textContent = "Download";
          }
          item.appendChild(link);
        } else if (typeof artifact.storage_uri === "string" && artifact.storage_uri.length > 0) {
          const stored = document.createElement("span");
          stored.classList.add("pyc-build-detail__artifact-stored");
          stored.setAttribute("data-role", "artifact-stored-at");
          stored.textContent = "Stored at " + artifact.storage_uri;
          stored.title = "This service does not serve files from that storage; fetch it with the storage's own tools.";
          item.appendChild(stored);
        }
        const digest = document.createElement("span");
        digest.classList.add("pyc-build-detail__artifact-digest");
        digest.textContent = short_id(artifact.sha256);
        digest.title = artifact.sha256;
        item.appendChild(digest);
        list.appendChild(item);
      }
    }
    section.replaceChildren(heading, list);
    return;
  }
  // The file to show as the build's log: a ".log" file this service serves,
  // preferring one whose name says "build".
  _pick_log_path() {
    const candidates = [];
    for (const artifact of this._artifacts) {
      const served = served_artifact_path(artifact);
      if (served.toLowerCase().endsWith(".log") === true) {
        candidates.push({ path: served, size: artifact.payload !== null && typeof artifact.payload === "object" && typeof artifact.payload.size_bytes === "number" ? artifact.payload.size_bytes : null });
      }
    }
    if (candidates.length === 0) {
      return null;
    }
    const preferred = candidates.find((candidate) => candidate.path.toLowerCase().indexOf("build") >= 0);
    return preferred !== void 0 ? preferred : candidates[0];
  }
  async _maybe_load_log() {
    if (this._terminal === false || this._build === null) {
      return;
    }
    const pick = this._pick_log_path();
    if (pick === null) {
      this._render_log();
      return;
    }
    if (this._log.path === pick.path && this._log.status !== "idle") {
      this._render_log();
      return;
    }
    this._log = { path: pick.path, status: "loading", text: "", cut: false, total: 0, size: pick.size };
    this._render_log();
    if (pick.size !== null && pick.size > LOG_INLINE_MAX_BYTES) {
      this._log.status = "large";
      this._render_log();
      return;
    }
    try {
      const response = await fetch(run_artifact_url(this._build_id, pick.path), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "text/plain" }
      });
      if (response.ok === false) {
        if (response.status === 401) {
          announce_session_expired();
        }
        this._log.status = "error";
        this._render_log();
        return;
      }
      const length = Number(response.headers.get("Content-Length"));
      if (Number.isFinite(length) === true && length > LOG_INLINE_MAX_BYTES) {
        this._log.status = "large";
        this._log.size = length;
        this._render_log();
        return;
      }
      const text = await response.text();
      const tail = tail_lines(text, LOG_TAIL_LINES);
      this._log.text = tail.text.length > LOG_TAIL_MAX_CHARS ? tail.text.slice(tail.text.length - LOG_TAIL_MAX_CHARS) : tail.text;
      this._log.cut = tail.cut || tail.text.length > LOG_TAIL_MAX_CHARS;
      this._log.total = tail.total;
      this._log.status = "ok";
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.log_fetch_failed",
        { reason: String(reason) }
      );
      this._log.status = "error";
    }
    this._render_log();
    return;
  }
  _render_log() {
    if (this._root === null) {
      return;
    }
    const section = this._root.querySelector('[data-role="log-section"]');
    if (section === null) {
      return;
    }
    if (this._terminal === false || this._build === null) {
      section.replaceChildren();
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-build-detail__section-heading");
    heading.textContent = "Build log";
    const state = this._log;
    const note = (text, role) => {
      const p = document.createElement("p");
      p.classList.add("pyc-build-detail__log-note");
      p.setAttribute("data-role", role);
      p.textContent = text;
      return p;
    };
    if (state.path.length === 0) {
      section.replaceChildren(heading, note("This build uploaded no log file.", "log-none"));
      return;
    }
    const open_link = document.createElement("a");
    open_link.classList.add("pyc-build-detail__artifact-link");
    open_link.setAttribute("data-role", "log-open");
    open_link.setAttribute("href", run_artifact_url(this._build_id, state.path));
    open_link.setAttribute("target", "_blank");
    open_link.setAttribute("rel", "noopener noreferrer");
    open_link.textContent = "Open the full log";
    if (state.status === "loading") {
      section.replaceChildren(heading, note("Loading the build log\u2026", "log-loading"));
      return;
    }
    if (state.status === "large") {
      const size = format_bytes(state.size);
      section.replaceChildren(heading, note("The log is " + (size.length > 0 ? size : "large") + ", too big to show here.", "log-large"), open_link);
      return;
    }
    if (state.status === "error") {
      section.replaceChildren(heading, note("Couldn't load the build log.", "log-error"), open_link);
      return;
    }
    const pre = document.createElement("pre");
    pre.classList.add("pyc-build-detail__log-text");
    pre.setAttribute("data-role", "build-log");
    pre.setAttribute("tabindex", "0");
    pre.setAttribute("aria-label", "Build log, last lines");
    pre.textContent = state.text.length > 0 ? state.text : "(the log is empty)";
    const children = [heading];
    if (state.cut === true) {
      children.push(note("Showing the last " + String(LOG_TAIL_LINES) + " lines of " + String(state.total) + ".", "log-cut"));
    }
    children.push(pre, open_link);
    section.replaceChildren(...children);
    return;
  }
  /**
   * Update the live-poll status banner. Shows a "live updates
   * on" affordance while polling and a "build finished" note
   * once the build reaches a terminal state.
   */
  _render_poll_banner() {
    if (this._root === null) {
      return;
    }
    const banner = this._root.querySelector('[data-role="poll-banner"]');
    if (banner instanceof HTMLElement === false) {
      return;
    }
    const el = banner;
    if (this._poll_status === "polling") {
      el.hidden = false;
      el.setAttribute("data-tone", "neutral");
      el.textContent = "Build in progress \u2014 refreshing every 5 seconds.";
      return;
    }
    if (this._poll_status === "stopped" && this._terminal === true) {
      el.hidden = false;
      el.setAttribute("data-tone", "neutral");
      el.textContent = "Build finished \u2014 live updates ended.";
      return;
    }
    el.hidden = true;
    el.textContent = "";
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-builds-bundle/index.entry.js
var ORCHESTRATION_GROUP_ID = "orchestration";
var BUILDS_READ_PERMISSION = "system:builds.read";
var BUILDS_ROUTE = "/builds";
var BUILDS_LIST_TAG = "pyc-builds-list";
var BUILD_DETAIL_TAG = "pyc-build-detail";
var BUILDS_STYLESHEET_HREF = "/static/javascript/pyc-builds-bundle/pyc-builds-bundle.css";
function ensure_builds_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-builds-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = BUILDS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-builds-bundle");
  document.head.appendChild(link);
  return;
}
var BUILDS_ENTRY = {
  entryId: "orchestration.builds",
  label: "Builds",
  route: BUILDS_ROUTE,
  requiredPermissions: [BUILDS_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_builds_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [BUILDS_READ_PERMISSION]
  });
  sidebar.registerEntry(BUILDS_ENTRY);
  return;
}
function define_builds_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(BUILDS_LIST_TAG) === void 0) {
    customElements.define(BUILDS_LIST_TAG, PycBuildsList);
  }
  if (customElements.get(BUILD_DETAIL_TAG) === void 0) {
    customElements.define(BUILD_DETAIL_TAG, PycBuildDetail);
  }
  return;
}
function classify_builds_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === BUILDS_ROUTE || working === BUILDS_ROUTE + "/") {
    const rtnval2 = "list";
    return rtnval2;
  }
  const detail_id = build_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_builds_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_builds_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main");
  if (main === null) {
    return;
  }
  const target_tag = route === "detail" ? BUILD_DETAIL_TAG : BUILDS_LIST_TAG;
  const existing = main.querySelector(target_tag);
  if (existing !== null) {
    return;
  }
  define_builds_elements();
  ensure_builds_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_builds_view_if_active();
  return;
}
function _boot() {
  define_builds_elements();
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
      "pychestrate.ui.builds.bundle_no_shell_handle",
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
  BUILD_STATES,
  PycBuildDetail,
  PycBuildsList,
  TERMINAL_BUILD_STATES,
  announce_session_expired,
  build_artifacts_url,
  build_build_detail_link,
  build_builds_collection_url,
  build_builds_query_url,
  build_detail_url,
  build_id_from_path,
  build_source_integrations_url,
  build_state_tone,
  classify_builds_route,
  define_builds_elements,
  detail_load_message_for_status,
  ensure_builds_stylesheet,
  format_timestamp,
  has_next_page,
  has_previous_page,
  is_terminal_build_state,
  is_valid_build_id,
  list_load_message_for_status,
  mount_builds_view_if_active,
  parse_runner_inputs,
  project_id_from_search,
  register_builds_sidebar,
  short_id,
  trigger_message_for_status
};
