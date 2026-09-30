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
function show_no_projects(region, { link_class_name }) {
  region.replaceChildren(
    build_empty_state({
      inline: true,
      message: "No projects exist yet.",
      next_step: "This page works inside a project, so create one first.",
      link: { href: "/projects/create", label: "Create a project", class_name: link_class_name }
    })
  );
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-catalog-bundle/catalog-view.js
var DEFAULT_PER_PAGE = 25;
var PROJECTS_API_PATH = "/api/v1/projects";
var PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
function build_catalog_query_url(state) {
  const params = new URLSearchParams();
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  if (state.includeRetired === true) {
    params.set("include_retired", "true");
  }
  const query = params.toString();
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(state.projectId) + "/test-catalog?" + query;
  return rtnval;
}
function build_test_runs_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/test-runs";
  return rtnval;
}
function build_catalog_import_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/test-catalog:import";
  return rtnval;
}
function selection_summary(entry) {
  const tags = entry.required_capability_tags;
  if (tags === null || tags === void 0 || tags.length === 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const rtnval = tags.join(", ");
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
function has_next_page(state) {
  const consumed = state.page * state.perPage;
  const rtnval = consumed < state.total;
  return rtnval;
}
function has_previous_page(state) {
  const rtnval = state.page > 1;
  return rtnval;
}
function list_load_message_for_status(status, what) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to " + what + ".";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This project was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the server \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load " + what + " (HTTP " + String(status) + "). Try refreshing.";
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
function parse_import_includes(raw) {
  if (typeof raw !== "string") {
    const rtnval2 = [];
    return rtnval2;
  }
  const rtnval = [];
  for (const line of raw.split(/\r?\n/)) {
    const trimmed_line = line.trim();
    if (trimmed_line.length === 0 || trimmed_line.startsWith("#") === true) {
      continue;
    }
    for (const piece of trimmed_line.split(",")) {
      const include = piece.trim();
      if (include.length > 0 && rtnval.includes(include) === false) {
        rtnval.push(include);
      }
    }
  }
  return rtnval;
}
function parse_capability_tags(raw) {
  if (typeof raw !== "string") {
    const rtnval2 = [];
    return rtnval2;
  }
  const rtnval = [];
  for (const piece of raw.split(",")) {
    const tag = piece.trim();
    if (tag.length > 0 && rtnval.includes(tag) === false) {
      rtnval.push(tag);
    }
  }
  return rtnval;
}
function import_outcome_message(status, body) {
  if (status === 0) {
    const rtnval2 = { ok: false, message: "Import failed \u2014 network error." };
    return rtnval2;
  }
  if (status < 200 || status >= 300) {
    let detail = "";
    if (body !== null && typeof body === "object" && typeof body.detail === "string") {
      detail = body.detail.trim();
    }
    if (detail.length === 0) {
      const rtnval22 = { ok: false, message: "Import failed (HTTP " + String(status) + ")." };
      return rtnval22;
    }
    const rtnval2 = { ok: false, message: "Import failed: " + detail };
    return rtnval2;
  }
  let count = 0;
  let errors = [];
  if (body !== null && typeof body === "object") {
    if (typeof body.entries_imported === "number") {
      count = body.entries_imported;
    }
    if (Array.isArray(body.errors) === true) {
      errors = body.errors;
    }
  }
  if (count === 0) {
    let message2 = "Nothing was imported.";
    if (errors.length > 0) {
      message2 = message2 + " " + errors.join("; ");
    }
    const rtnval2 = { ok: false, message: message2 };
    return rtnval2;
  }
  let message = "Imported " + String(count) + (count === 1 ? " entry." : " entries.");
  if (errors.length > 0) {
    message = message + " " + String(errors.length) + " failed: " + errors.join("; ");
  }
  const rtnval = { ok: errors.length === 0, message };
  return rtnval;
}
function trigger_message_for_status(status) {
  if (status === 202 || status === 200 || status === 201) {
    const rtnval2 = "Run triggered.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "No client/pod is enrolled and available \u2014 enroll a client first.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project or catalog entry.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to trigger runs.";
    return rtnval2;
  }
  const rtnval = "Failed to trigger run (HTTP " + String(status) + ").";
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
var PycTestCatalog = class extends HTMLElement {
  _state;
  _entries;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _projects_notice_region;
  _root;
  _table_region;
  _import_region;
  _toast_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      includeRetired: false,
      loading: false,
      errored: false,
      errorStatus: 0
    };
    this._entries = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._projects_notice_region = null;
    this._root = null;
    this._table_region = null;
    this._pager = null;
    this._import_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + pagination state without scraping the DOM.
   */
  get viewState() {
    const rtnval = {
      projectId: this._state.projectId,
      page: this._state.page,
      perPage: this._state.perPage,
      total: this._state.total,
      includeRetired: this._state.includeRetired,
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
   * import action, table region, pager, and toast region.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-catalog");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-catalog__heading");
    heading.textContent = "Test Catalog";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-catalog__controls");
    const project_label = document.createElement("div");
    project_label.classList.add("pyc-catalog__field");
    const project_select = document.createElement("mj-select");
    project_select.setAttribute("label", "Project");
    project_select.classList.add("pyc-catalog__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-catalog__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("label", "Project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectId = project_input.value.trim();
      this._state.page = 1;
      void this._refresh();
    });
    controls.appendChild(project_input);
    const retired_label = document.createElement("label");
    retired_label.classList.add("pyc-catalog__checkbox");
    const retired_input = document.createElement("input");
    retired_input.setAttribute("type", "checkbox");
    retired_input.setAttribute("data-role", "include-retired");
    retired_input.addEventListener("change", () => {
      this._state.includeRetired = retired_input.checked;
      this._state.page = 1;
      void this._refresh();
    });
    retired_label.appendChild(retired_input);
    const retired_text = document.createElement("span");
    retired_text.textContent = "Include retired";
    retired_label.appendChild(retired_text);
    controls.appendChild(retired_label);
    const import_button = document.createElement("mj-button");
    import_button.classList.add("pyc-catalog__button");
    import_button.setAttribute("type", "button");
    import_button.setAttribute("data-role", "import-toggle");
    hide_unless_may(import_button, "system:test_catalog.write");
    import_button.textContent = "Import from testbase";
    import_button.addEventListener("click", () => {
      this._toggle_import_form();
    });
    controls.appendChild(import_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-catalog__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-catalog__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    const import_region = document.createElement("div");
    import_region.classList.add("pyc-catalog__import-region");
    import_region.setAttribute("data-role", "import-region");
    import_region.hidden = true;
    root.appendChild(import_region);
    this._import_region = import_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-catalog__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");
    pager.classList.add("pyc-catalog__pager");
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
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-catalog__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    toast_region.setAttribute("role", "status");
    toast_region.setAttribute("aria-live", "polite");
    toast_region.setAttribute("aria-live", "polite");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    this._root = root;
    this.replaceChildren(root);
    this._render_table_region();
    return;
  }
  /**
   * Fetch the projects collection to populate the selector. When
   * the endpoint is unavailable (404 / network / non-array body)
   * the selector falls back to a manual project-id text input.
   * Exposed so unit tests can await the load cycle.
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
        "pychestrate.ui.catalog.projects_fetch_failed",
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
      await this._refresh();
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
      region.classList.remove("pyc-catalog__projects-notice--error");
      show_no_projects(region, {});
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-catalog__projects-notice--error");
      region.textContent = "You don't have permission to list projects.";
      return;
    }
    region.classList.add("pyc-catalog__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-catalog__button");
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
      const project_id = record["project_id"];
      if (typeof project_id !== "string" || project_id.length === 0) {
        continue;
      }
      const slug = typeof record["slug"] === "string" ? record["slug"] : project_id;
      const display_name = typeof record["display_name"] === "string" ? record["display_name"] : slug;
      rtnval.push({
        project_id,
        slug,
        display_name
      });
    }
    return rtnval;
  }
  /**
   * Render either the project ``<select>`` (when a projects list
   * is available) or the manual project-id ``<input>`` fallback.
   */
  _render_project_control() {
    if (this._root === null) {
      return;
    }
    const select = this._root.querySelector('[data-role="project-select"]');
    const input = this._root.querySelector('[data-role="project-input"]');
    if (select instanceof HTMLElement) {
      if (this._projectsAvailable === true) {
        select.hidden = false;
        select.replaceChildren();
        for (const project of this._projects) {
          const option = document.createElement("mj-option");
          option.setAttribute("value", project.project_id);
          option.textContent = project.display_name;
          select.appendChild(option);
        }
        select.value = this._state.projectId;
      } else {
        select.hidden = true;
      }
    }
    if (input instanceof HTMLElement) {
      input.hidden = this._projectsAvailable === true;
    }
    return;
  }
  /**
   * Fetch the current catalog page from the REST endpoint and
   * re-render the table region. Drives the loading / error /
   * empty states. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._entries = [];
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._render_table_region();
    const url = build_catalog_query_url(this._state);
    let page = null;
    let error_status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      error_status = response.status;
      if (response.ok === false) {
        throw new Error(
          "catalog fetch failed: HTTP " + String(response.status)
        );
      }
      error_status = 0;
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.catalog.list_fetch_failed",
        { reason: String(reason) }
      );
      if (error_status === 401) {
        announce_session_expired();
      }
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = error_status;
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = 0;
      this._render_table_region();
      return;
    }
    this._entries = page.items;
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
   * Re-render the table region from the current state + entries.
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
      const prompt = document.createElement("p");
      prompt.classList.add("pyc-catalog__status");
      prompt.setAttribute("data-role", "no-project-state");
      prompt.textContent = "Select a project to view its test catalog.";
      region.replaceChildren(prompt);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-catalog__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading catalog\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-catalog__status",
        "pyc-catalog__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = list_load_message_for_status(
        this._state.errorStatus,
        "the test catalog"
      );
      const children = [error];
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-catalog__button");
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
    if (this._entries.length === 0) {
      const empty = build_empty_state({ class_name: "pyc-catalog__status", message: "No catalog entries yet. Import from testbase to populate." });
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
   * Build the catalog ``<mj-table>`` from the current entries list.
   */
  _build_table() {
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-catalog__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-catalog__row";
    table.rowAttrs = (entry) => {
      const attrs = { "data-entry-key": entry.entry_key };
      if (entry.retired === true) {
        attrs["data-retired"] = "";
      }
      return attrs;
    };
    table.columns = [
      {
        key: "entry_key",
        label: "Entry",
        width: "20rem",
        render: (entry) => {
          const key_code = document.createElement("code");
          key_code.classList.add("pyc-catalog__entry-key");
          key_code.textContent = entry.entry_key;
          return key_code;
        }
      },
      { key: "display_name", label: "Name", width: "14rem" },
      {
        key: "capabilities",
        label: "Capabilities",
        width: "12rem",
        sortable: false,
        render: (entry) => selection_summary(entry)
      },
      { key: "importer_tag", label: "Importer", width: "12rem" },
      {
        key: "created_at",
        label: "Created",
        width: "12rem",
        render: (entry) => format_timestamp(entry.created_at)
      },
      {
        key: "action",
        label: "Action",
        width: "10rem",
        sortable: false,
        render: (entry) => {
          const trigger_button = document.createElement("mj-button");
          trigger_button.classList.add("pyc-catalog__trigger");
          trigger_button.setAttribute("type", "button");
          trigger_button.setAttribute("data-role", "trigger-run");
          trigger_button.setAttribute("data-entry-id", entry.entry_id);
          trigger_button.textContent = "Trigger Run";
          trigger_button.toggleAttribute("disabled", entry.retired === true);
          trigger_button.addEventListener("click", () => {
            void self._trigger_run(entry, trigger_button);
          });
          return trigger_button;
        }
      }
    ];
    table.rows = this._entries;
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
   * Show / hide the inline import form. The service cannot browse the
   * test code on the pods, so the form collects the testbase include
   * names to catalog (one per line) plus the optional testbase root,
   * branch and required capability tags, then POSTs
   * ``…/test-catalog:import``.
   */
  _toggle_import_form() {
    if (this._import_region === null) {
      return;
    }
    const region = this._import_region;
    if (region.hidden === false) {
      region.hidden = true;
      region.replaceChildren();
      return;
    }
    region.hidden = false;
    const form = document.createElement("form");
    form.classList.add("pyc-catalog__import-form");
    form.setAttribute("data-role", "import-form");
    const note = document.createElement("p");
    note.classList.add("pyc-catalog__import-note");
    note.setAttribute("data-role", "import-note");
    note.textContent = "List the testbase tests to add, one include per line \u2014 the names `testbase testing run --includes` takes, for example ccai.tests.singlehost.feature.test_module. Each include becomes one catalog entry.";
    form.appendChild(note);
    const includes_label = document.createElement("label");
    includes_label.classList.add("pyc-catalog__field", "pyc-catalog__field--wide");
    includes_label.textContent = "Test includes (one per line)";
    const includes_area = document.createElement("mj-textarea");
    includes_area.classList.add("pyc-catalog__input");
    includes_area.setAttribute("data-role", "import-includes");
    includes_area.setAttribute("placeholder", "ccai.tests.singlehost.feature.test_module");
    includes_area.rows = 5;
    includes_label.appendChild(includes_area);
    form.appendChild(includes_label);
    const root_label = document.createElement("div");
    root_label.classList.add("pyc-catalog__field");
    const root_input = document.createElement("mj-text-field");
    root_input.setAttribute("label", "Testbase root on the pod (optional)");
    root_input.classList.add("pyc-catalog__input");
    root_input.setAttribute("type", "text");
    root_input.setAttribute("data-role", "import-root");
    root_input.setAttribute("placeholder", "source/testroots/ccai");
    root_label.appendChild(root_input);
    form.appendChild(root_label);
    const ref_label = document.createElement("div");
    ref_label.classList.add("pyc-catalog__field");
    const ref_input = document.createElement("mj-text-field");
    ref_input.setAttribute("label", "Branch (optional)");
    ref_input.classList.add("pyc-catalog__input");
    ref_input.setAttribute("type", "text");
    ref_input.setAttribute("data-role", "import-ref");
    ref_input.setAttribute("placeholder", "main");
    ref_label.appendChild(ref_input);
    form.appendChild(ref_label);
    const tags_label = document.createElement("div");
    tags_label.classList.add("pyc-catalog__field");
    const tags_input = document.createElement("mj-text-field");
    tags_input.setAttribute("label", "Required capability tags (optional, comma-separated)");
    tags_input.classList.add("pyc-catalog__input");
    tags_input.setAttribute("type", "text");
    tags_input.setAttribute("data-role", "import-tags");
    tags_input.setAttribute("placeholder", "linux, python3.12");
    tags_label.appendChild(tags_input);
    form.appendChild(tags_label);
    const tag_label = document.createElement("div");
    tag_label.classList.add("pyc-catalog__field");
    const tag_input = document.createElement("mj-text-field");
    tag_input.setAttribute("label", "Importer");
    tag_input.classList.add("pyc-catalog__input");
    tag_input.setAttribute("type", "text");
    tag_input.setAttribute("data-role", "import-tag");
    tag_input.setAttribute("placeholder", "testbase-project");
    tag_input.value = "testbase-project";
    tag_label.appendChild(tag_input);
    form.appendChild(tag_label);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-catalog__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "import-submit");
    submit.textContent = "Run import";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-catalog__import-status");
    status.setAttribute("data-role", "import-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_import(
        {
          importerTag: String(tag_input.value ?? "").trim(),
          includesText: String(includes_area.value ?? ""),
          root: String(root_input.value ?? "").trim(),
          ref: String(ref_input.value ?? "").trim(),
          tagsText: String(tags_input.value ?? "")
        },
        submit,
        status
      );
    });
    region.replaceChildren(form);
    return;
  }
  /**
   * POST the import request and reload the catalog on completion.
   * Exposed so unit tests can drive the submit path directly.
   *
   * @param request ``{importerTag, includesText, root, ref, tagsText}``
   *                -- the importer tag, the pasted include list, and the
   *                optional testbase root, branch and comma-separated
   *                capability tags.
   * @param submit_button The form's submit button (disabled while
   *                      the request is in flight).
   * @param status_node The status paragraph the outcome is written to.
   *
   * @returns ``{ok, message}`` -- the outcome shown in the status line.
   */
  async submitImport(request, submit_button, status_node) {
    const rtnval = await this._submit_import(request, submit_button, status_node);
    return rtnval;
  }
  async _submit_import(request, submit_button, status_node) {
    const set_status = (text, tone) => {
      if (status_node !== null) {
        status_node.textContent = text;
        status_node.setAttribute("data-tone", tone);
      }
      return;
    };
    if (this._state.projectId.length === 0) {
      const rtnval2 = { ok: false, message: "Select a project first." };
      set_status(rtnval2.message, "error");
      return rtnval2;
    }
    const importer_tag = typeof request.importerTag === "string" && request.importerTag.length > 0 ? request.importerTag : "testbase-project";
    const includes = parse_import_includes(request.includesText);
    if (includes.length === 0) {
      const rtnval2 = {
        ok: false,
        message: "List at least one testbase include to import."
      };
      set_status(rtnval2.message, "error");
      return rtnval2;
    }
    if (submit_button !== null) {
      submit_button.toggleAttribute("disabled", true);
    }
    set_status("Import running\u2026", "neutral");
    const source = { includes };
    if (typeof request.root === "string" && request.root.length > 0) {
      source["root"] = request.root;
    }
    if (typeof request.ref === "string" && request.ref.length > 0) {
      source["ref"] = request.ref;
    }
    const tags = parse_capability_tags(request.tagsText);
    if (tags.length > 0) {
      source["required_capability_tags"] = tags;
    }
    const payload = { importer_tag, source };
    const url = build_catalog_import_url(this._state.projectId);
    let status = 0;
    let body = null;
    try {
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
      try {
        body = await response.json();
      } catch (parse_reason) {
        body = null;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.catalog.import_failed",
        { reason: String(reason) }
      );
      status = 0;
    }
    if (submit_button !== null) {
      submit_button.toggleAttribute("disabled", false);
    }
    const outcome = import_outcome_message(status, body);
    set_status(outcome.message, outcome.ok === true ? "ok" : "error");
    if (status >= 200 && status < 300) {
      await this._refresh();
    }
    return outcome;
  }
  /**
   * POST a ``TestRunCreateRequest`` for the given catalog entry.
   * Exposed so unit tests can drive the trigger path directly.
   *
   * For PR O the request carries the catalog entry id only; pod
   * selection is left to the server's orchestrator (the UI does
   * not offer a pod picker -- see the module docstring). A 202 +
   * ``Run`` surfaces a success toast with a link to the run
   * detail page; a 409 surfaces the "no eligible pod" guidance.
   *
   * @param entry The catalog entry whose run is being triggered.
   * @param trigger_button The clicked button (disabled while the
   *                        request is in flight). May be null in
   *                        unit-test contexts.
   *
   * @returns The trigger outcome (status + surfaced message).
   */
  async triggerRun(entry, trigger_button) {
    const rtnval = await this._trigger_run(entry, trigger_button);
    return rtnval;
  }
  async _trigger_run(entry, trigger_button) {
    if (trigger_button !== null) {
      trigger_button.toggleAttribute("disabled", true);
    }
    const payload = {
      catalog_entry_id: entry.entry_id
    };
    const url = build_test_runs_url(entry.project_id);
    let status = 0;
    let run_id = "";
    let detail = "";
    try {
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
      detail = await read_problem_detail(response);
      if (response.ok === true) {
        const body = await response.json();
        const triggered = body;
        if (typeof triggered.run_id === "string") {
          run_id = triggered.run_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.catalog.trigger_run_failed",
        { reason: String(reason) }
      );
      if (trigger_button !== null) {
        trigger_button.toggleAttribute("disabled", entry.retired === true);
      }
      const failure = {
        ok: false,
        status: 0,
        runId: "",
        message: "Failed to trigger run \u2014 network error."
      };
      this._show_toast(failure);
      return failure;
    }
    if (trigger_button !== null) {
      trigger_button.toggleAttribute("disabled", entry.retired === true);
    }
    const ok = status >= 200 && status < 300;
    const outcome = {
      ok,
      status,
      runId: run_id,
      message: message_with_detail("Test run not started", detail, trigger_message_for_status(status))
    };
    this._show_toast(outcome);
    return outcome;
  }
  /**
   * Render a transient toast/notice for a trigger-run outcome.
   * On success the toast carries a link to ``/runs/{run_id}``.
   */
  _show_toast(outcome) {
    show_toast(this._toast_region, outcome.message, outcome.ok === true ? "ok" : "error", {
      class_prefix: "pyc-catalog",
      data_role: "trigger-toast",
      dismiss_label: "Dismiss notice",
      link: outcome.ok === true && outcome.runId.length > 0 ? { href: "/runs/" + outcome.runId, text: "View run", data_role: "run-link" } : null
    });
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-catalog-bundle/index.entry.js
var ORCHESTRATION_GROUP_ID = "orchestration";
var CATALOG_READ_PERMISSION = "system:test_catalog.read";
var CATALOG_ROUTE = "/test-catalog";
var CATALOG_TAG = "pyc-test-catalog";
var CATALOG_STYLESHEET_HREF = "/static/javascript/pyc-catalog-bundle/pyc-catalog-bundle.css";
function ensure_catalog_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-catalog-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = CATALOG_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-catalog-bundle");
  document.head.appendChild(link);
  return;
}
var CATALOG_ENTRY = {
  entryId: "orchestration.test-catalog",
  label: "Test Catalog",
  route: CATALOG_ROUTE,
  requiredPermissions: [CATALOG_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_catalog_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [CATALOG_READ_PERMISSION]
  });
  sidebar.registerEntry(CATALOG_ENTRY);
  return;
}
function define_catalog_element() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(CATALOG_TAG) === void 0) {
    customElements.define(CATALOG_TAG, PycTestCatalog);
  }
  return;
}
function classify_catalog_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === CATALOG_ROUTE || working === CATALOG_ROUTE + "/") {
    const rtnval2 = "catalog";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_catalog_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_catalog_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector(
    "pyc-site-shell main.pyc-site-shell__main"
  );
  if (main === null) {
    return;
  }
  const existing = main.querySelector(CATALOG_TAG);
  if (existing !== null) {
    return;
  }
  define_catalog_element();
  ensure_catalog_stylesheet();
  const view = document.createElement(CATALOG_TAG);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_catalog_view_if_active();
  return;
}
function _boot() {
  define_catalog_element();
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
      "pychestrate.ui.catalog.bundle_no_shell_handle",
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
  PycTestCatalog,
  announce_session_expired,
  build_catalog_import_url,
  build_catalog_query_url,
  build_test_runs_url,
  classify_catalog_route,
  define_catalog_element,
  ensure_catalog_stylesheet,
  format_timestamp,
  has_next_page,
  has_previous_page,
  list_load_message_for_status,
  mount_catalog_view_if_active,
  register_catalog_sidebar,
  selection_summary,
  trigger_message_for_status
};
