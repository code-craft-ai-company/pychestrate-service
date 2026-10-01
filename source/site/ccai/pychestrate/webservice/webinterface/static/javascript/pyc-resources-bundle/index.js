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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/view-state.js
function query_value(name) {
  if (typeof window === "undefined") {
    return "";
  }
  const value = new URLSearchParams(window.location.search).get(name);
  return value === null ? "" : value.trim();
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-resources-bundle/resource-pools-view.js
var DEFAULT_PER_PAGE = 50;
var RESOURCE_POOLS_API_PATH = "/api/v1/resource-pools";
var PROJECTS_API_PATH = "/api/v1/projects";
var PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
var RESOURCE_POOLS_WRITE_PERMISSION = "system:resource_pools.write";
var RESOURCES_WRITE_PERMISSION = "system:resources.write";
function build_resource_pools_url(project_id, page, per_page) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  params.set("page", String(page));
  params.set("per_page", String(per_page));
  const rtnval = RESOURCE_POOLS_API_PATH + "?" + params.toString();
  return rtnval;
}
function short_id(value) {
  if (typeof value !== "string" || value.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const dash_index = value.indexOf("-");
  if (dash_index <= 0) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = value.slice(0, dash_index);
  return rtnval;
}
function parse_capability_tags(raw) {
  const rtnval = [];
  if (typeof raw !== "string" || raw.length === 0) {
    return rtnval;
  }
  const parts = raw.split(",");
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.length === 0) {
      continue;
    }
    if (rtnval.indexOf(trimmed) >= 0) {
      continue;
    }
    rtnval.push(trimmed);
  }
  return rtnval;
}
function resource_state_tone(state) {
  if (state === "available") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (state === "leased" || state === "maintenance") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (state === "quarantined" || state === "retired") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function health_tone(outcome) {
  if (outcome === "pass") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (outcome === "fail") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function total_pages_for(total, per_page) {
  if (typeof total !== "number" || typeof per_page !== "number" || per_page <= 0) {
    const rtnval2 = 1;
    return rtnval2;
  }
  const rtnval = Math.max(1, Math.ceil(total / per_page));
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
async function read_problem(response) {
  const rtnval = {
    status: response.status,
    detail: "",
    reason: ""
  };
  let body = null;
  try {
    body = await response.json();
  } catch (reason) {
    body = null;
  }
  if (body !== null && typeof body === "object") {
    if (typeof body.detail === "string") {
      rtnval.detail = body.detail;
    }
    if (typeof body.reason === "string") {
      rtnval.reason = body.reason;
    }
  }
  return rtnval;
}
function shell_permission_cache() {
  if (typeof window === "undefined") {
    const rtnval2 = null;
    return rtnval2;
  }
  const handle = window.pychestrateShell;
  if (handle === void 0 || handle === null) {
    const rtnval2 = null;
    return rtnval2;
  }
  if (handle.permissions !== void 0 && handle.permissions !== null) {
    const rtnval2 = handle.permissions;
    return rtnval2;
  }
  const shell_element = handle.element;
  if (shell_element === void 0 || shell_element === null) {
    const rtnval2 = null;
    return rtnval2;
  }
  const cache = shell_element.permissions;
  if (cache === void 0 || cache === null) {
    const rtnval2 = null;
    return rtnval2;
  }
  const rtnval = cache;
  return rtnval;
}
function shell_write_allowed(permission_key) {
  const cache = shell_permission_cache();
  if (cache === null) {
    const rtnval2 = true;
    return rtnval2;
  }
  if (cache.degraded === true) {
    const rtnval2 = true;
    return rtnval2;
  }
  let snapshot = null;
  try {
    snapshot = cache.current();
  } catch (reason) {
    snapshot = null;
  }
  if (snapshot === null || typeof snapshot.has !== "function") {
    const rtnval2 = true;
    return rtnval2;
  }
  const rtnval = snapshot.has(permission_key) === true;
  return rtnval;
}
function on_shell_permissions_changed(listener) {
  const cache = shell_permission_cache();
  if (cache === null || typeof cache.onPermissionsChanged !== "function") {
    return;
  }
  cache.onPermissionsChanged(listener);
  return;
}
var PycResourcePools = class extends HTMLElement {
  _state;
  _pools;
  _projects;
  _root;
  _project_region;
  _inventory;
  _create_region;
  _table_region;
  _create_status;
  _pager;
  constructor() {
    super();
    this._state = {
      projectFilter: "",
      page: page_from_query(),
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false,
      errorStatus: 0,
      needsProject: true,
      projectsState: "loading",
      creating: false
    };
    this._pools = [];
    this._projects = [];
    this._root = null;
    this._project_region = null;
    this._inventory = null;
    this._create_region = null;
    this._table_region = null;
    this._create_status = null;
    this._pager = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the filter +
   * pagination state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectFilter: this._state.projectFilter,
      page: this._state.page,
      perPage: this._state.perPage,
      total: this._state.total,
      loading: this._state.loading,
      errored: this._state.errored,
      errorStatus: this._state.errorStatus,
      needsProject: this._state.needsProject,
      projectsState: this._state.projectsState,
      creating: this._state.creating
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome, then load the
   * projects collection to seed the project selector. A
   * ``?project_id=`` query parameter pre-selects that project.
   */
  connectedCallback() {
    const seeded = this._project_from_search();
    if (seeded.length > 0) {
      this._state.projectFilter = seeded;
    }
    this._render_chrome();
    on_shell_permissions_changed(() => {
      if (this.isConnected === true) {
        this._render_create_region();
      }
    });
    void this._load_projects();
    return;
  }
  _project_from_search() {
    if (typeof window === "undefined") {
      const rtnval2 = "";
      return rtnval2;
    }
    const params = new URLSearchParams(window.location.search);
    const value = params.get("project_id");
    if (value === null) {
      const rtnval2 = "";
      return rtnval2;
    }
    const rtnval = value.trim();
    return rtnval;
  }
  /**
   * Fetch the projects collection and populate the project
   * selector. Exposed so unit tests can await the bootstrap
   * fetch cycle.
   */
  async loadProjects() {
    await this._load_projects();
    return;
  }
  async _load_projects() {
    this._state.projectsState = "loading";
    this._render_project_region();
    let outcome = "error";
    let projects = [];
    try {
      const response = await fetch(PROJECTS_LIST_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        projects = extract_projects(body);
        outcome = projects.length > 0 ? "loaded" : "empty";
      } else if (response.status === 403) {
        outcome = "forbidden";
      } else {
        outcome = "error";
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.projects_fetch_failed",
        { reason: String(reason) }
      );
      outcome = "error";
    }
    this._projects = projects;
    this._state.projectsState = outcome;
    if (outcome === "loaded") {
      const seeded = this._state.projectFilter;
      if (seeded.length > 0) {
        const known = this._projects.some(
          (project) => project.project_id === seeded
        );
        if (known === false) {
          this._projects.unshift({
            project_id: seeded,
            display_name: seeded
          });
        }
      } else {
        this._state.projectFilter = this._projects[0].project_id;
      }
    }
    this._render_project_region();
    if (this._state.projectFilter.length > 0) {
      await this._refresh();
    } else {
      this._state.needsProject = true;
      this._render_table_region();
    }
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-resources");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource pools";
    root.appendChild(heading);
    const subtitle = document.createElement("p");
    subtitle.classList.add("pyc-resources__subtitle");
    subtitle.textContent = "Resources and resource pools are project-scoped. Pick a project to list them.";
    root.appendChild(subtitle);
    const filters = document.createElement("div");
    filters.classList.add("pyc-resources__filters");
    const project_region = document.createElement("div");
    project_region.classList.add("pyc-resources__project-region");
    project_region.setAttribute("data-role", "project-region");
    filters.appendChild(project_region);
    this._project_region = project_region;
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-resources__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      if (this._state.projectFilter.length > 0) {
        void this._refresh();
      }
    });
    filters.appendChild(refresh_button);
    root.appendChild(filters);
    const inventory = document.createElement("pyc-resource-inventory");
    inventory.setAttribute("data-role", "inventory");
    root.appendChild(inventory);
    this._inventory = inventory;
    const pools_heading = document.createElement("h2");
    pools_heading.classList.add("pyc-resources__section-heading");
    pools_heading.textContent = "Pools";
    root.appendChild(pools_heading);
    const create_region = document.createElement("div");
    create_region.setAttribute("data-role", "create-region");
    root.appendChild(create_region);
    this._create_region = create_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-resources__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");
    pager.classList.add("pyc-resources__pager");
    pager.setAttribute("data-role", "pager");
    pager.setAttribute("page", String(this._state.page));
    pager.setAttribute("page-size", String(this._state.perPage));
    pager.setAttribute("total-items", String(this._state.total));
    pager.setAttribute(
      "total-pages",
      String(total_pages_for(this._state.total, this._state.perPage))
    );
    pager.addEventListener("mj-pagination-change", (event) => {
      this._state.page = event.detail.page;
      void this._refresh();
    });
    this._pager = pager;
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
    this._render_project_region();
    this._render_create_region();
    return;
  }
  /**
   * Render the project selector region for the current
   * ``projectsState`` -- an ``mj-select`` when the projects
   * collection loaded, honest status messages (plus a manual
   * project-id fallback where it can still help) otherwise.
   */
  _render_project_region() {
    if (this._project_region === null) {
      return;
    }
    const region = this._project_region;
    const state = this._state.projectsState;
    if (state === "loading") {
      const loading = document.createElement("p");
      loading.classList.add("pyc-resources__status");
      loading.setAttribute("data-role", "projects-loading");
      loading.textContent = "Loading projects\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (state === "loaded") {
      const project_label = document.createElement("label");
      project_label.classList.add("pyc-resources__filter");
      project_label.textContent = "Project";
      const project_select = document.createElement("mj-select");
      project_select.classList.add("pyc-resources__select");
      project_select.setAttribute("data-role", "project-select");
      for (const project of this._projects) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", project.project_id);
        option.textContent = project.display_name;
        project_select.appendChild(option);
      }
      if (this._state.projectFilter.length > 0) {
        project_select.value = this._state.projectFilter;
      }
      project_select.addEventListener("change", () => {
        this._state.projectFilter = project_select.value;
        this._state.page = 1;
        void this._refresh();
      });
      project_label.appendChild(project_select);
      region.replaceChildren(project_label);
      return;
    }
    const fragment = document.createDocumentFragment();
    const message = document.createElement("p");
    message.classList.add("pyc-resources__status");
    if (state === "empty") {
      message.setAttribute("data-role", "projects-empty");
      message.textContent = "No projects are visible to your account.";
      fragment.appendChild(message);
    } else if (state === "forbidden") {
      message.classList.add("pyc-resources__status--error");
      message.setAttribute("data-role", "projects-forbidden");
      message.textContent = "You do not have permission to list projects. Enter a project id directly.";
      fragment.appendChild(message);
    } else {
      message.classList.add("pyc-resources__status--error");
      message.setAttribute("data-role", "projects-error");
      message.textContent = "Could not load the projects list.";
      fragment.appendChild(message);
      const retry = document.createElement("mj-button");
      retry.classList.add("pyc-resources__button");
      retry.setAttribute("type", "button");
      retry.setAttribute("data-role", "projects-retry");
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        void this._load_projects();
      });
      fragment.appendChild(retry);
    }
    if (state === "forbidden" || state === "error") {
      const project_label = document.createElement("label");
      project_label.classList.add("pyc-resources__filter");
      project_label.textContent = "Project";
      const project_input = document.createElement("mj-text-field");
      project_input.classList.add("pyc-resources__input");
      project_input.setAttribute("type", "text");
      project_input.setAttribute("placeholder", "project id");
      project_input.setAttribute("data-role", "project-filter");
      if (this._state.projectFilter.length > 0) {
        project_input.value = this._state.projectFilter;
      }
      project_input.addEventListener("change", () => {
        this._state.projectFilter = project_input.value.trim();
        this._state.page = 1;
        if (this._state.projectFilter.length > 0) {
          void this._refresh();
        } else {
          this._state.needsProject = true;
          this._pools = [];
          this._state.total = 0;
          this._render_table_region();
        }
      });
      project_label.appendChild(project_input);
      fragment.appendChild(project_label);
    }
    region.replaceChildren(fragment);
    return;
  }
  /**
   * Render (or hide) the create-pool form. The form only renders
   * when the shell's permission cache does not affirmatively lack
   * the resource-pools write key -- the server still enforces the
   * permission on POST.
   */
  _render_create_region() {
    if (this._create_region === null) {
      return;
    }
    if (shell_write_allowed(RESOURCE_POOLS_WRITE_PERMISSION) === false) {
      this._create_status = null;
      this._create_region.replaceChildren();
      return;
    }
    this._create_region.replaceChildren(this._build_create_form());
    return;
  }
  _build_create_form() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "create-section");
    const heading = document.createElement("h3");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Create pool";
    section.appendChild(heading);
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "create-form");
    const name_label = document.createElement("div");
    name_label.classList.add("pyc-resources__filter");
    const name_input = document.createElement("mj-text-field");
    name_input.setAttribute("label", "Name");
    name_input.classList.add("pyc-resources__input");
    name_input.setAttribute("type", "text");
    name_input.setAttribute("placeholder", "pool name");
    name_input.setAttribute("data-role", "create-name");
    name_label.appendChild(name_input);
    form.appendChild(name_label);
    const desc_label = document.createElement("div");
    desc_label.classList.add("pyc-resources__filter");
    const desc_input = document.createElement("mj-text-field");
    desc_input.setAttribute("label", "Description");
    desc_input.classList.add("pyc-resources__input");
    desc_input.setAttribute("type", "text");
    desc_input.setAttribute("placeholder", "optional");
    desc_input.setAttribute("data-role", "create-description");
    desc_label.appendChild(desc_input);
    form.appendChild(desc_label);
    const tags_label = document.createElement("div");
    tags_label.classList.add("pyc-resources__filter");
    const tags_input = document.createElement("mj-text-field");
    tags_input.setAttribute("label", "Capability tags");
    tags_input.classList.add("pyc-resources__input");
    tags_input.setAttribute("type", "text");
    tags_input.setAttribute("placeholder", "comma-separated");
    tags_input.setAttribute("data-role", "create-tags");
    tags_label.appendChild(tags_input);
    form.appendChild(tags_label);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "create-submit");
    submit.textContent = "Create Pool";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-resources__form-status");
    status.setAttribute("data-role", "create-status");
    status.setAttribute("role", "status");
    status.hidden = true;
    this._create_status = status;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_create(
        name_input.value.trim(),
        desc_input.value.trim(),
        tags_input.value,
        submit,
        [name_input, desc_input, tags_input]
      );
    });
    section.appendChild(form);
    section.appendChild(status);
    return section;
  }
  async _submit_create(name, description, tags_raw, submit_button, inputs) {
    if (this._state.creating === true) {
      return;
    }
    if (this._state.projectFilter.length === 0) {
      this._show_create_status(
        "Pick a project before creating a pool.",
        true
      );
      return;
    }
    if (name.length === 0) {
      this._show_create_status("A pool name is required.", true);
      return;
    }
    const body = {
      project_id: this._state.projectFilter,
      name
    };
    if (description.length > 0) {
      body["description"] = description;
    }
    const tags = parse_capability_tags(tags_raw);
    if (tags.length > 0) {
      body["capability_tags"] = tags;
    }
    this._state.creating = true;
    if (submit_button !== null && submit_button !== void 0) {
      submit_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(RESOURCE_POOLS_API_PATH, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
      });
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "Create failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to create resource pools.";
        } else if (problem.detail.length > 0) {
          message = "Create failed: " + problem.detail;
        }
        this._show_create_status(message, true);
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.pool_create_failed",
        { reason: String(reason) }
      );
      this._show_create_status(
        "Create failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      this._state.creating = false;
      if (submit_button !== null && submit_button !== void 0) {
        submit_button.removeAttribute("disabled");
      }
    }
    if (Array.isArray(inputs) === true) {
      for (const input of inputs) {
        input.value = "";
      }
    }
    this._show_create_status("Pool created.", false);
    this._state.page = 1;
    await this._refresh();
    return;
  }
  _show_create_status(message, errored) {
    if (this._create_status === null) {
      return;
    }
    this._create_status.hidden = false;
    this._create_status.textContent = message;
    if (errored === true) {
      this._create_status.setAttribute("data-tone", "error");
    } else {
      this._create_status.setAttribute("data-tone", "ok");
    }
    return;
  }
  /**
   * Fetch the project's resource pools and re-render the table
   * region. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  _sync_inventory() {
    if (this._inventory !== null) {
      this._inventory.projectId = this._state.projectFilter;
    }
    return;
  }
  async _refresh() {
    this._sync_inventory();
    if (this._state.projectFilter.length === 0) {
      this._state.needsProject = true;
      this._render_table_region();
      return;
    }
    mirror_to_query({
      project_id: this._state.projectFilter,
      page: this._state.page > 1 ? String(this._state.page) : ""
    });
    this._state.needsProject = false;
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._render_table_region();
    const url = build_resource_pools_url(
      this._state.projectFilter,
      this._state.page,
      this._state.perPage
    );
    let page = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        this._state.loading = false;
        this._state.errored = true;
        this._state.errorStatus = response.status;
        this._render_table_region();
        return;
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.pools_fetch_failed",
        { reason: String(reason) }
      );
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = 0;
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
    this._pools = page.items;
    if (page.meta !== null && page.meta !== void 0) {
      this._state.total = page.meta.total;
      this._state.page = page.meta.page;
    } else {
      this._state.total = page.items.length;
    }
    const last_page = total_pages_for(this._state.total, this._state.perPage);
    if (this._pools.length === 0 && this._state.total > 0 && this._state.page > last_page) {
      this._state.page = last_page;
      await this._refresh();
      return;
    }
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
    return;
  }
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.needsProject === true) {
      const prompt = document.createElement("p");
      prompt.classList.add("pyc-resources__status");
      prompt.setAttribute("data-role", "needs-project");
      prompt.setAttribute("role", "status");
      prompt.textContent = "Pick a project above to list its resource pools.";
      region.replaceChildren(prompt);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-resources__status");
      loading.setAttribute("data-role", "loading-state");
      loading.setAttribute("role", "status");
      loading.textContent = "Loading resource pools\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const fragment = document.createDocumentFragment();
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.setAttribute("role", "status");
      const status = this._state.errorStatus;
      if (status === 403) {
        error.textContent = with_access_request("You do not have permission to view resource pools.");
      } else if (status === 0) {
        error.textContent = "Network error while loading resource pools.";
      } else {
        error.textContent = "Failed to load resource pools (HTTP " + String(status) + ").";
      }
      fragment.appendChild(error);
      if (status !== 403) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-resources__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "error-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._refresh();
        });
        fragment.appendChild(retry);
      }
      region.replaceChildren(fragment);
      this._render_pager();
      return;
    }
    if (this._pools.length === 0) {
      const empty = build_empty_state({ class_name: "pyc-resources__status", role: "status", message: "No resource pools in this project", next_step: "Use the Create Pool form above to add one." });
      region.replaceChildren(empty);
      this._render_pager();
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    this._render_pager();
    return;
  }
  _build_table() {
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-resources__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-resources__row";
    table.columns = [
      {
        key: "pool_id",
        label: "Pool",
        width: "12rem",
        render: (pool) => {
          const link = document.createElement("a");
          link.classList.add("pyc-resources__link");
          const href = "/resource-pools/" + pool.pool_id + "?project_id=" + encodeURIComponent(pool.project_id);
          link.setAttribute("href", href);
          link.textContent = short_id(pool.pool_id);
          link.title = pool.pool_id;
          return link;
        }
      },
      {
        key: "name",
        label: "Name",
        width: "16rem",
        render: (pool) => {
          const rtnval = pool.name !== null && pool.name.length > 0 ? pool.name : "\u2014";
          return rtnval;
        }
      },
      {
        key: "capability_tags",
        label: "Capabilities",
        width: "18rem",
        sortable: false,
        render: (pool) => {
          const tags = Array.isArray(pool.capability_tags) === true ? pool.capability_tags : [];
          if (tags.length === 0) {
            const rtnval2 = "\u2014";
            return rtnval2;
          }
          const fragment = document.createDocumentFragment();
          for (const tag of tags) {
            const chip = document.createElement("mj-chip");
            chip.classList.add("pyc-resources__tag");
            chip.textContent = tag;
            fragment.appendChild(chip);
          }
          return fragment;
        }
      },
      {
        key: "member_count",
        label: "Members",
        width: "8rem",
        render: (pool) => String(pool.member_count)
      }
    ];
    table.rows = this._pools;
    return table;
  }
  _render_pager() {
    if (this._pager === null || this._pager === void 0) {
      return;
    }
    this._pager.setAttribute("page", String(this._state.page));
    this._pager.setAttribute("page-size", String(this._state.perPage));
    this._pager.setAttribute("total-items", String(this._state.total));
    this._pager.setAttribute(
      "total-pages",
      String(total_pages_for(this._state.total, this._state.perPage))
    );
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/run-labels.js
function state_label(state) {
  if (typeof state !== "string" || state.length === 0) {
    return "\u2014";
  }
  const words = state.replace(/[_-]+/g, " ");
  return /^[A-Z0-9 ]+$/.test(words) ? words.toLowerCase() : words;
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-resources-bundle/resource-inventory-view.js
var RESOURCES_API_PATH = "/api/v1/resources";
var LIST_LIMIT = 100;
var DEVICE_KIND = "device";
var DEVICE_DETAILS = [
  ["mac_address", "MAC address", "aa:bb:cc:dd:ee:ff"],
  ["ipv4", "IPv4 address", "10.0.0.12"],
  ["vendor", "Vendor", "optional"],
  ["model", "Model", "optional"],
  ["location", "Location", "optional"],
  ["notes", "Notes", "optional"]
];
function build_resources_url(project_id, limit) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  params.set("per_page", String(limit));
  return RESOURCES_API_PATH + "?" + params.toString();
}
function parse_tags(raw) {
  const rtnval = [];
  if (typeof raw !== "string") {
    return rtnval;
  }
  for (const part of raw.split(",")) {
    const trimmed = part.trim();
    if (trimmed.length > 0 && rtnval.indexOf(trimmed) < 0) {
      rtnval.push(trimmed);
    }
  }
  return rtnval;
}
function build_device_body(project_id, values) {
  const name = String(values.display_name || "").trim();
  const hostname = String(values.hostname || "").trim();
  if (project_id.length === 0) {
    return { error: "Pick a project before registering a device." };
  }
  if (name.length === 0) {
    return { error: "A name is required." };
  }
  if (hostname.length === 0) {
    return { error: "A hostname is required: it is what tells one device from another." };
  }
  const attributes = { hostname };
  for (const [key] of DEVICE_DETAILS) {
    const value = String(values[key] || "").trim();
    if (value.length > 0) {
      attributes[key] = value;
    }
  }
  const body = { project_id, kind: DEVICE_KIND, display_name: name, attributes };
  const tags = parse_tags(values.tags);
  if (tags.length > 0) {
    body.tags = tags;
  }
  return { body };
}
function registration_failure_message(status, detail) {
  if (status === 403) {
    return with_access_request("You do not have permission to register resources.");
  }
  if (status === 409) {
    return "That device is already registered (same hostname and MAC address).";
  }
  return message_with_detail("Not registered", detail, "Not registered (HTTP " + String(status) + ").");
}
var PycResourceInventory = class extends HTMLElement {
  _project_id = "";
  _resources = [];
  _total = 0;
  _state = "idle";
  _error_status = 0;
  _saving = false;
  _list_region = null;
  _form_region = null;
  _status = null;
  constructor() {
    super();
  }
  /* Diagnostic accessor for tests. */
  get inventoryState() {
    return {
      projectId: this._project_id,
      state: this._state,
      count: this._resources.length,
      total: this._total,
      saving: this._saving
    };
  }
  connectedCallback() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__inventory");
    section.setAttribute("data-role", "inventory-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Resources";
    section.appendChild(heading);
    const list_region = document.createElement("div");
    list_region.setAttribute("data-role", "inventory-list");
    section.appendChild(list_region);
    this._list_region = list_region;
    const form_region = document.createElement("div");
    form_region.setAttribute("data-role", "inventory-form-region");
    section.appendChild(form_region);
    this._form_region = form_region;
    this.replaceChildren(section);
    this._render_form();
    on_shell_permissions_changed(() => {
      if (this.isConnected === true) {
        this._render_form();
        this._render_list();
      }
    });
    void this._load();
    return;
  }
  /* The project whose resources are shown; setting it loads them. */
  set projectId(value) {
    const next = typeof value === "string" ? value : "";
    if (next === this._project_id) {
      return;
    }
    this._project_id = next;
    if (this.isConnected === true) {
      void this._load();
    }
  }
  get projectId() {
    return this._project_id;
  }
  async refresh() {
    await this._load();
    return;
  }
  async _load() {
    if (this._list_region === null) {
      return;
    }
    if (this._project_id.length === 0) {
      this._state = "idle";
      this._resources = [];
      this._total = 0;
      this._render_list();
      return;
    }
    this._state = "loading";
    this._render_list();
    try {
      const response = await fetch(build_resources_url(this._project_id, LIST_LIMIT), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        this._state = "error";
        this._error_status = response.status;
      } else {
        const body = await response.json();
        this._resources = Array.isArray(body.items) ? body.items : [];
        this._total = body.meta && typeof body.meta.total === "number" ? body.meta.total : this._resources.length;
        this._state = "loaded";
      }
    } catch (reason) {
      console.warn("pychestrate.ui.resources.inventory_fetch_failed", { reason: String(reason) });
      this._state = "error";
      this._error_status = 0;
    }
    this._render_list();
    return;
  }
  _note(text, role, tone) {
    const note = document.createElement("p");
    note.classList.add("pyc-resources__status");
    if (tone === "error") {
      note.classList.add("pyc-resources__status--error");
    }
    note.setAttribute("data-role", role);
    note.setAttribute("role", "status");
    note.textContent = text;
    return note;
  }
  _render_list() {
    const region = this._list_region;
    if (region === null) {
      return;
    }
    if (this._state === "idle") {
      region.replaceChildren(this._note("Pick a project above to list its resources.", "inventory-needs-project"));
      return;
    }
    if (this._state === "loading") {
      region.replaceChildren(this._note("Loading resources\u2026", "inventory-loading"));
      return;
    }
    if (this._state === "error") {
      const text = this._error_status === 403 ? with_access_request("You do not have permission to view resources.") : "Failed to load resources" + (this._error_status > 0 ? " (HTTP " + String(this._error_status) + ")." : ".");
      region.replaceChildren(this._note(text, "inventory-error", "error"));
      return;
    }
    if (this._resources.length === 0) {
      const writable = shell_write_allowed(RESOURCES_WRITE_PERMISSION) !== false;
      region.replaceChildren(this._note(
        writable ? "No resources in this project yet. Register a device below, then add it to a pool." : "No resources in this project yet.",
        "inventory-empty"
      ));
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_table());
    if (this._total > this._resources.length) {
      fragment.appendChild(this._note(
        "Showing the first " + String(this._resources.length) + " of " + String(this._total) + " resources.",
        "inventory-truncated"
      ));
    }
    region.replaceChildren(fragment);
    return;
  }
  _build_table() {
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-resources__table", "pyc-resources__table--inventory");
    table.setAttribute("sortable", "");
    table.rowClass = "pyc-resources__row";
    table.columns = [
      {
        key: "display_name",
        label: "Name",
        width: "16rem",
        render: (resource) => {
          const link = document.createElement("a");
          link.classList.add("pyc-resources__link");
          link.setAttribute("href", "/resource-pools/resources/" + resource.resource_id);
          link.textContent = resource.display_name && resource.display_name.length > 0 ? resource.display_name : resource.resource_id;
          return link;
        }
      },
      { key: "kind", label: "Kind", width: "8rem", render: (resource) => state_label(resource.kind) },
      {
        key: "state",
        label: "State",
        width: "9rem",
        render: (resource) => {
          const badge = document.createElement("mj-badge");
          badge.classList.add("pyc-resources__badge");
          badge.setAttribute("data-tone", resource_state_tone(resource.state));
          badge.textContent = resource.state;
          return badge;
        }
      },
      {
        key: "tags",
        label: "Tags",
        width: "16rem",
        sortable: false,
        render: (resource) => {
          const tags = Array.isArray(resource.tags) ? resource.tags : [];
          if (tags.length === 0) {
            return "\u2014";
          }
          const fragment = document.createDocumentFragment();
          for (const tag of tags) {
            const chip = document.createElement("mj-chip");
            chip.classList.add("pyc-resources__tag");
            chip.textContent = tag;
            fragment.appendChild(chip);
          }
          return fragment;
        }
      },
      { key: "created_at", label: "Registered", width: "14rem", render: (resource) => format_timestamp(resource.created_at) }
    ];
    table.rows = this._resources;
    return table;
  }
  /* The register form, for people who may write resources (the server still checks). */
  _render_form() {
    const region = this._form_region;
    if (region === null) {
      return;
    }
    if (shell_write_allowed(RESOURCES_WRITE_PERMISSION) === false) {
      region.replaceChildren();
      return;
    }
    const details = document.createElement("details");
    details.classList.add("pyc-resources__register");
    details.setAttribute("data-role", "register-section");
    const summary = document.createElement("summary");
    summary.textContent = "Register a device";
    details.appendChild(summary);
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "register-form");
    const inputs = {};
    const add_field = (key, label, placeholder) => {
      const wrapper = document.createElement("div");
      wrapper.classList.add("pyc-resources__filter");
      const input = document.createElement("mj-text-field");
      input.setAttribute("label", label);
      input.classList.add("pyc-resources__input");
      input.setAttribute("type", "text");
      input.setAttribute("placeholder", placeholder);
      input.setAttribute("data-role", "register-" + key);
      wrapper.appendChild(input);
      form.appendChild(wrapper);
      inputs[key] = input;
    };
    add_field("display_name", "Name", "Bench phone 1");
    add_field("hostname", "Hostname", "phone-01");
    for (const [key, label, hint] of DEVICE_DETAILS) {
      add_field(key, label, hint);
    }
    add_field("tags", "Tags", "comma-separated, for example android, lab");
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "register-submit");
    submit.textContent = "Register device";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-resources__form-status");
    status.setAttribute("data-role", "register-status");
    status.setAttribute("role", "status");
    status.hidden = true;
    this._status = status;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const values = {};
      for (const key of Object.keys(inputs)) {
        values[key] = inputs[key].value;
      }
      void this._register(values, submit, inputs);
    });
    details.appendChild(form);
    details.appendChild(status);
    region.replaceChildren(details);
    return;
  }
  _show_status(message, errored) {
    if (this._status === null) {
      return;
    }
    this._status.hidden = false;
    this._status.textContent = message;
    this._status.setAttribute("data-tone", errored === true ? "error" : "ok");
    return;
  }
  async _register(values, submit, inputs) {
    if (this._saving === true) {
      return;
    }
    const built = build_device_body(this._project_id, values);
    if (built.error !== void 0) {
      this._show_status(built.error, true);
      return;
    }
    this._saving = true;
    submit.setAttribute("disabled", "");
    let registered = false;
    try {
      const response = await fetch(RESOURCES_API_PATH, {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(built.body)
      });
      if (response.ok === false) {
        const detail = await read_problem_detail(response);
        this._show_status(registration_failure_message(response.status, detail), true);
      } else {
        registered = true;
      }
    } catch (reason) {
      console.warn("pychestrate.ui.resources.register_failed", { reason: String(reason) });
      this._show_status("Not registered: network error. Try again.", true);
    } finally {
      this._saving = false;
      submit.removeAttribute("disabled");
    }
    if (registered === true) {
      for (const key of Object.keys(inputs)) {
        inputs[key].value = "";
      }
      this._show_status("Registered " + built.body.display_name + ".", false);
      await this._load();
    }
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/confirm.js
function confirm_action(source, message, confirm_label, options) {
  const tone = options !== null && options !== void 0 && options.tone === "neutral" ? "neutral" : "danger";
  return new Promise((resolve) => {
    const request = new CustomEvent("pyc-confirm-request", {
      bubbles: true,
      composed: true,
      cancelable: true,
      detail: { message, confirm_label, tone, resolve }
    });
    const answered_by_shell = source.dispatchEvent(request) === false;
    if (answered_by_shell === false) {
      resolve(window.confirm(message));
    }
  });
}

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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-resources-bundle/pool-detail-view.js
var ACTIVE_RESERVATION_STATES = [
  "pending",
  "granted"
];
var PROJECTS_API_PATH2 = "/api/v1/projects";
var PROJECTS_LIST_URL2 = PROJECTS_API_PATH2 + "?per_page=500";
var RESOURCES_API_PATH2 = "/api/v1/resources";
var UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function pool_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/resource-pools/";
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
  const rtnval = value.trim();
  return rtnval;
}
function is_valid_uuid(value) {
  if (typeof value !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(value);
  return rtnval;
}
function is_active_reservation(state) {
  const rtnval = ACTIVE_RESERVATION_STATES.indexOf(state) >= 0;
  return rtnval;
}
function reservation_tone(state) {
  if (state === "granted") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (state === "pending") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (state === "rejected" || state === "forced_released") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function build_pool_url(pool_id) {
  const rtnval = "/api/v1/resource-pools/" + encodeURIComponent(pool_id);
  return rtnval;
}
function build_pool_resources_url(pool_id) {
  const rtnval = build_pool_url(pool_id) + "/resources";
  return rtnval;
}
function build_project_resources_url(project_id) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  params.set("per_page", "500");
  return RESOURCES_API_PATH2 + "?" + params.toString();
}
function addable_resources(resources, members) {
  const taken = new Set((Array.isArray(members) ? members : []).map((member) => member.resource_id));
  return (Array.isArray(resources) ? resources : []).filter(
    (resource) => resource.state !== "retired" && taken.has(resource.resource_id) === false
  );
}
function resource_option_label(resource) {
  const name = typeof resource.display_name === "string" && resource.display_name.length > 0 ? resource.display_name : resource.resource_id;
  const kind = typeof resource.kind === "string" && resource.kind.length > 0 ? " \xB7 " + state_label(resource.kind) : "";
  return name + kind;
}
function build_pool_member_url(pool_id, resource_id) {
  const rtnval = build_pool_resources_url(pool_id) + "/" + encodeURIComponent(resource_id);
  return rtnval;
}
function build_pool_reservations_url(pool_id) {
  const rtnval = build_pool_url(pool_id) + "/reservations";
  return rtnval;
}
function build_reservation_url(pool_id, reservation_id) {
  const rtnval = build_pool_reservations_url(pool_id) + "/" + encodeURIComponent(reservation_id);
  return rtnval;
}
function member_display_label(member) {
  let label = "";
  if (typeof member.resource_name === "string" && member.resource_name.length > 0) {
    label = member.resource_name;
  } else {
    label = short_id(member.resource_id);
  }
  if (typeof member.resource_state === "string" && member.resource_state.length > 0) {
    label = label + " \xB7 " + member.resource_state;
  }
  const rtnval = label;
  return rtnval;
}
function reserve_failure_message(problem) {
  if (problem.reason === "conflict_rejected") {
    const rtnval2 = "Reservation conflicts with an existing hold.";
    return rtnval2;
  }
  if (problem.reason === "pool_empty") {
    const rtnval2 = "This pool has no available resources.";
    return rtnval2;
  }
  if (problem.status === 403) {
    const rtnval2 = "You do not have permission to reserve from this pool.";
    return rtnval2;
  }
  if (problem.detail.length > 0) {
    const rtnval2 = "Reserve failed: " + problem.detail;
    return rtnval2;
  }
  const rtnval = "Reserve failed (HTTP " + String(problem.status) + ").";
  return rtnval;
}
function section_error_message(noun, status) {
  if (status === 403) {
    const rtnval2 = "You do not have permission to view " + noun + ".";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Network error while loading " + noun + ".";
    return rtnval2;
  }
  const rtnval = "Failed to load " + noun + " (HTTP " + String(status) + ").";
  return rtnval;
}
var PycPoolDetail = class extends HTMLElement {
  _pool_id;
  _project_id;
  _pool;
  _members;
  _reservations;
  _loading;
  _errored;
  _error_status;
  _members_error;
  _candidates;
  _reservations_error;
  _project_names;
  _reserving;
  _releasing;
  _deleting;
  _root;
  _action_status;
  constructor() {
    super();
    this._pool_id = "";
    this._project_id = "";
    this._pool = null;
    this._members = [];
    this._reservations = [];
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._members_error = null;
    this._candidates = null;
    this._reservations_error = null;
    this._project_names = {};
    this._reserving = false;
    this._releasing = {};
    this._deleting = false;
    this._root = null;
    this._action_status = null;
  }
  /**
   * Observed attributes -- ``pool-id`` / ``project-id`` may be
   * supplied explicitly by a host; otherwise they are read from
   * the path / query string on mount.
   */
  static get observedAttributes() {
    const rtnval = ["pool-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      poolId: this._pool_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored,
      errorStatus: this._error_status,
      membersError: this._members_error,
      reservationsError: this._reservations_error,
      reserving: this._reserving
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the pool + project ids, render the
   * chrome, and fetch the initial snapshot.
   */
  connectedCallback() {
    const attr_pool = this.getAttribute("pool-id");
    if (attr_pool !== null && attr_pool.length > 0) {
      this._pool_id = attr_pool;
    } else {
      this._pool_id = pool_id_from_path(window.location.pathname);
    }
    const attr_project = this.getAttribute("project-id");
    if (attr_project !== null && attr_project.length > 0) {
      this._project_id = attr_project;
    } else {
      this._project_id = project_id_from_search(
        window.location.search
      );
    }
    this._render_chrome();
    on_shell_permissions_changed(() => {
      if (this.isConnected === true) {
        this._render_body();
      }
    });
    void this._load();
    void this._load_project_names();
    return;
  }
  /**
   * Fetch the pool snapshot. Exposed so unit tests can await a
   * load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_uuid(this._pool_id) === false) {
      this._loading = false;
      this._errored = true;
      this._error_status = -1;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_body();
    const result = await this._fetch_json(
      build_pool_url(this._pool_id),
      "pool_fetch_failed"
    );
    if (result.ok === false) {
      this._loading = false;
      this._errored = true;
      this._error_status = result.status;
      this._render_body();
      return;
    }
    this._pool = result.body;
    if (this._project_id.length === 0 && typeof this._pool.project_id === "string") {
      this._project_id = this._pool.project_id;
    }
    this._update_back_link();
    await this._refresh_members();
    await this._refresh_candidates();
    await this._refresh_reservations();
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  /**
   * Best-effort fetch of the projects collection so the summary
   * can show a project display name beside the UUID. Failures are
   * silent -- the UUID alone is always rendered.
   */
  async _load_project_names() {
    try {
      const response = await fetch(PROJECTS_LIST_URL2, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        return;
      }
      const body = await response.json();
      const projects = extract_projects(body);
      const names = {};
      for (const project of projects) {
        names[project.project_id] = project.display_name;
      }
      this._project_names = names;
      if (this._loading === false && this._errored === false && this._pool !== null) {
        this._render_body();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.project_names_fetch_failed",
        { reason: String(reason) }
      );
    }
    return;
  }
  async _refresh_members() {
    const result = await this._fetch_json(
      build_pool_resources_url(this._pool_id),
      "members_fetch_failed"
    );
    if (result.ok === true && Array.isArray(result.body.items) === true) {
      this._members = result.body.items;
      this._members_error = null;
    } else {
      this._members_error = result.status;
    }
    return;
  }
  /*
   * The project's resources a person can add: null when they cannot be listed
   * (no permission to read resources, a failure), so the form falls back to
   * asking for an id.
   */
  async _refresh_candidates() {
    const project_id = this._pool !== null && typeof this._pool.project_id === "string" ? this._pool.project_id : this._project_id;
    if (project_id.length === 0) {
      this._candidates = null;
      return;
    }
    const result = await this._fetch_json(build_project_resources_url(project_id), "candidates_fetch_failed");
    if (result.ok === true && Array.isArray(result.body.items) === true) {
      this._candidates = addable_resources(result.body.items, this._members);
    } else {
      this._candidates = null;
    }
    return;
  }
  async _refresh_reservations() {
    const result = await this._fetch_json(
      build_pool_reservations_url(this._pool_id),
      "reservations_fetch_failed"
    );
    if (result.ok === true && Array.isArray(result.body.items) === true) {
      this._reservations = result.body.items;
      this._reservations_error = null;
    } else {
      this._reservations_error = result.status;
    }
    return;
  }
  /**
   * GET a JSON document. Returns ``{ok: true, body}`` on a 2xx
   * response and ``{ok: false, status}`` otherwise -- ``status``
   * is ``0`` for network-level failures so callers can render an
   * error state distinct from an empty collection.
   */
  async _fetch_json(url, failure_tag) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        console.warn(
          "pychestrate.ui.resources." + failure_tag,
          { status: response.status }
        );
        const rtnval2 = { ok: false, status: response.status, body: null };
        return rtnval2;
      }
      const body = await response.json();
      const rtnval = { ok: true, status: response.status, body };
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources." + failure_tag,
        { reason: String(reason) }
      );
      const rtnval = { ok: false, status: 0, body: null };
      return rtnval;
    }
  }
  _pools_list_href() {
    let href = "/resource-pools";
    if (this._project_id.length > 0) {
      href = href + "?project_id=" + encodeURIComponent(this._project_id);
    }
    const rtnval = href;
    return rtnval;
  }
  _update_back_link() {
    if (this._root === null) {
      return;
    }
    const back = this._root.querySelector('[data-role="back-link"]');
    if (back === null) {
      return;
    }
    back.setAttribute("href", this._pools_list_href());
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-resources", "pyc-pool-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Resource pool detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource pool detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-resources__back-link");
    back.setAttribute("href", this._pools_list_href());
    back.setAttribute("data-role", "back-link");
    keep_list_state_on_back(back, "/resource-pools");
    back.textContent = "Back to resource pools";
    root.appendChild(back);
    const status = document.createElement("p");
    status.classList.add("pyc-resources__form-status");
    status.setAttribute("data-role", "action-status");
    status.setAttribute("role", "status");
    status.hidden = true;
    root.appendChild(status);
    this._action_status = status;
    const body = document.createElement("div");
    body.classList.add("pyc-resources__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
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
      loading.classList.add("pyc-resources__status");
      loading.setAttribute("data-role", "loading-state");
      loading.setAttribute("role", "status");
      loading.textContent = "Loading resource pool\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._pool === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.setAttribute("role", "status");
      const status = this._error_status;
      if (status === -1) {
        error.textContent = "The pool id in the URL is not a valid UUID.";
      } else if (status === 404) {
        error.textContent = "This resource pool was not found. It may have been deleted.";
      } else if (status === 403) {
        error.textContent = with_access_request("You do not have permission to view this resource pool.");
      } else if (status === 0) {
        error.textContent = "Network error while loading this resource pool. Try refreshing.";
      } else {
        error.textContent = "Failed to load this resource pool (HTTP " + String(status) + ").";
      }
      body.replaceChildren(error);
      return;
    }
    const write_allowed = shell_write_allowed(
      RESOURCE_POOLS_WRITE_PERMISSION
    );
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._pool, write_allowed));
    fragment.appendChild(this._build_resources(write_allowed));
    if (write_allowed === true) {
      fragment.appendChild(this._build_add_resource_form());
    }
    fragment.appendChild(this._build_reservations(write_allowed));
    if (write_allowed === true) {
      fragment.appendChild(this._build_reserve_form());
    }
    body.replaceChildren(fragment);
    return;
  }
  _project_field_value(project_id) {
    let value = project_id;
    const display_name = this._project_names[project_id];
    if (typeof display_name === "string" && display_name.length > 0 && display_name !== project_id) {
      value = display_name + " (" + project_id + ")";
    }
    const rtnval = value;
    return rtnval;
  }
  _build_summary(pool, write_allowed) {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Resource pool summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-resources__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-resources__id");
    id_value.setAttribute("data-role", "pool-id");
    id_value.textContent = short_id(pool.pool_id);
    set_entity_title(String(pool.name ?? "") || "Resource pool " + short_id(pool.pool_id));
    id_value.title = pool.pool_id;
    id_row.appendChild(id_value);
    if (write_allowed === true) {
      const delete_button = document.createElement("mj-button");
      delete_button.classList.add("pyc-resources__button");
      delete_button.setAttribute("type", "button");
      delete_button.setAttribute("data-role", "delete-pool");
      delete_button.textContent = "Delete Pool";
      if (this._deleting === true) {
        delete_button.setAttribute("disabled", "");
      }
      delete_button.addEventListener("click", () => {
        void this._submit_delete_pool(delete_button);
      });
      id_row.appendChild(delete_button);
    }
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-resources__grid");
    this._append_field(grid, "Pool id", pool.pool_id);
    this._append_field(grid, "Name", pool.name);
    this._append_field(
      grid,
      "Project",
      this._project_field_value(pool.project_id)
    );
    const description = pool.description !== null && pool.description !== void 0 ? pool.description : "";
    if (description.length > 0) {
      this._append_field(grid, "Description", description);
    }
    this._append_field(
      grid,
      "Members",
      String(pool.member_count)
    );
    this._append_field(
      grid,
      "Created",
      format_timestamp(pool.created_at)
    );
    section.appendChild(grid);
    const tags = Array.isArray(pool.capability_tags) === true ? pool.capability_tags : [];
    if (tags.length > 0) {
      const tag_list = document.createElement("div");
      tag_list.classList.add("pyc-resources__tag-list");
      for (const tag of tags) {
        const chip = document.createElement("mj-chip");
        chip.classList.add("pyc-resources__tag");
        chip.textContent = tag;
        tag_list.appendChild(chip);
      }
      section.appendChild(tag_list);
    }
    return section;
  }
  async _submit_delete_pool(delete_button) {
    if (this._deleting === true) {
      return;
    }
    const pool_name = this._pool !== null && typeof this._pool.name === "string" && this._pool.name.length > 0 ? this._pool.name : short_id(this._pool_id);
    const confirmed = await confirm_action(this, "Delete the pool " + pool_name + "? This permanently removes the pool and its membership rows and cannot be undone. The member resources themselves are not deleted.", "Delete pool");
    if (confirmed !== true) {
      return;
    }
    this._deleting = true;
    if (delete_button !== null && delete_button !== void 0) {
      delete_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(build_pool_url(this._pool_id), {
        method: "DELETE",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "Delete failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to delete this pool.";
        } else if (problem.detail.length > 0) {
          message = "Delete failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.pool_delete_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Delete failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      this._deleting = false;
      if (delete_button !== null && delete_button !== void 0) {
        delete_button.removeAttribute("disabled");
      }
    }
    window.location.assign(this._pools_list_href());
    return;
  }
  _resource_detail_href(resource_id) {
    let href = "/resource-pools/resources/" + resource_id;
    const params = new URLSearchParams();
    if (this._project_id.length > 0) {
      params.set("project_id", this._project_id);
    }
    params.set("pool_id", this._pool_id);
    href = href + "?" + params.toString();
    const rtnval = href;
    return rtnval;
  }
  _build_resources(write_allowed) {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__resources");
    section.setAttribute("data-role", "resources-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pool resources");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Resources";
    section.appendChild(heading);
    if (this._members_error !== null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "resources-error");
      error.setAttribute("role", "status");
      error.textContent = section_error_message(
        "this pool's resource members",
        this._members_error
      );
      section.appendChild(error);
      const retry = document.createElement("mj-button");
      retry.classList.add("pyc-resources__button");
      retry.setAttribute("type", "button");
      retry.setAttribute("data-role", "resources-retry");
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        void this._retry_members();
      });
      section.appendChild(retry);
      return section;
    }
    if (this._members.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-resources__status");
      empty.setAttribute("data-role", "resources-empty");
      empty.textContent = "This pool has no resource members.";
      section.appendChild(empty);
      return section;
    }
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-resources__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-resources__row";
    const columns = [
      {
        key: "resource_name",
        label: "Resource",
        width: "14rem",
        render: (member) => {
          const link = document.createElement("a");
          link.classList.add("pyc-resources__link");
          link.setAttribute(
            "href",
            this._resource_detail_href(member.resource_id)
          );
          let label = short_id(member.resource_id);
          if (typeof member.resource_name === "string" && member.resource_name.length > 0) {
            label = member.resource_name;
          }
          link.textContent = label;
          link.title = member.resource_id;
          return link;
        }
      },
      {
        key: "resource_kind",
        label: "Kind",
        width: "8rem",
        render: (member) => {
          const rtnval = typeof member.resource_kind === "string" && member.resource_kind.length > 0 ? state_label(member.resource_kind) : "\u2014";
          return rtnval;
        }
      },
      {
        key: "resource_state",
        label: "State",
        width: "8rem",
        render: (member) => {
          if (typeof member.resource_state !== "string" || member.resource_state.length === 0) {
            const rtnval2 = "\u2014";
            return rtnval2;
          }
          const badge = document.createElement("span");
          badge.classList.add("pyc-badge");
          badge.setAttribute("data-tone", resource_state_tone(member.resource_state));
          badge.textContent = member.resource_state;
          return badge;
        }
      },
      {
        key: "resource_health",
        label: "Health",
        width: "8rem",
        render: (member) => {
          if (typeof member.resource_health !== "string" || member.resource_health.length === 0) {
            const rtnval2 = "\u2014";
            return rtnval2;
          }
          const badge = document.createElement("span");
          badge.classList.add("pyc-badge");
          badge.setAttribute("data-tone", health_tone(member.resource_health));
          badge.textContent = member.resource_health;
          return badge;
        }
      },
      {
        key: "added_at",
        label: "Added",
        width: "12rem",
        render: (member) => format_timestamp(member.added_at)
      }
    ];
    if (write_allowed === true) {
      columns.push({
        key: "membership_id",
        label: "Actions",
        width: "8rem",
        sortable: false,
        render: (member) => {
          const remove = document.createElement("mj-button");
          remove.classList.add("pyc-resources__button");
          remove.setAttribute("type", "button");
          remove.setAttribute("data-role", "remove-member");
          remove.setAttribute("data-resource-id", member.resource_id);
          remove.textContent = "Remove";
          remove.addEventListener("click", () => {
            void this._submit_remove_member(member, remove);
          });
          return remove;
        }
      });
    }
    table.columns = columns;
    table.rows = this._members;
    section.appendChild(table);
    return section;
  }
  async _retry_members() {
    await this._refresh_members();
    this._render_body();
    return;
  }
  async _submit_remove_member(member, remove_button) {
    const label = member_display_label(member);
    const confirmed = await confirm_action(this, "Remove " + label + " from this pool? The resource itself is not deleted and existing reservations are not released.", "Remove from pool");
    if (confirmed !== true) {
      return;
    }
    if (remove_button !== null && remove_button !== void 0) {
      remove_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(
        build_pool_member_url(this._pool_id, member.resource_id),
        {
          method: "DELETE",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        }
      );
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "Remove failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to remove pool members.";
        } else if (problem.detail.length > 0) {
          message = "Remove failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.remove_member_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Remove failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      if (remove_button !== null && remove_button !== void 0) {
        remove_button.removeAttribute("disabled");
      }
    }
    this._show_action_status("Resource removed from the pool.", false);
    await this._load();
    return;
  }
  _build_add_resource_form() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "add-resource-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Add resource";
    section.appendChild(heading);
    if (Array.isArray(this._candidates) === true && this._candidates.length === 0) {
      const none = document.createElement("p");
      none.classList.add("pyc-resources__status");
      none.setAttribute("data-role", "add-resource-none");
      none.appendChild(document.createTextNode("Every resource in this project is already in this pool. "));
      const register = document.createElement("a");
      register.classList.add("pyc-resources__link");
      register.setAttribute("href", this._pools_list_href());
      register.textContent = "Register another device";
      none.appendChild(register);
      none.appendChild(document.createTextNode("."));
      section.appendChild(none);
      return section;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "add-resource-form");
    let read_value = null;
    if (Array.isArray(this._candidates) === true) {
      const label = document.createElement("label");
      label.classList.add("pyc-resources__filter");
      label.textContent = "Resource";
      const select = document.createElement("mj-select");
      select.classList.add("pyc-resources__select");
      select.setAttribute("data-role", "add-resource-select");
      for (const resource of this._candidates) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", resource.resource_id);
        option.textContent = resource_option_label(resource);
        select.appendChild(option);
      }
      label.appendChild(select);
      form.appendChild(label);
      read_value = () => String(select.value || "").trim();
    } else {
      const id_input = document.createElement("mj-text-field");
      id_input.setAttribute("label", "Resource id");
      id_input.classList.add("pyc-resources__input");
      id_input.setAttribute("type", "text");
      id_input.setAttribute("placeholder", "resource uuid");
      id_input.setAttribute("data-role", "add-resource-id");
      form.appendChild(id_input);
      read_value = () => id_input.value.trim();
    }
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "add-resource-submit");
    submit.textContent = "Add Resource";
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_add_resource(read_value(), submit);
    });
    section.appendChild(form);
    return section;
  }
  async _submit_add_resource(resource_id, submit_button) {
    if (resource_id.length === 0) {
      this._show_action_status(
        Array.isArray(this._candidates) === true ? "Choose a resource to add." : "A resource id is required.",
        true
      );
      return;
    }
    if (is_valid_uuid(resource_id) === false) {
      this._show_action_status(
        "A valid resource id (UUID) is required.",
        true
      );
      return;
    }
    const body = { resource_id };
    if (submit_button !== null && submit_button !== void 0) {
      submit_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(
        build_pool_resources_url(this._pool_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify(body)
        }
      );
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "Add resource failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to add pool members.";
        } else if (problem.detail.length > 0) {
          message = "Add resource failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.add_resource_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Add resource failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      if (submit_button !== null && submit_button !== void 0) {
        submit_button.removeAttribute("disabled");
      }
    }
    this._show_action_status("Resource added to the pool.", false);
    await this._load();
    return;
  }
  _build_reservations(write_allowed) {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__reservations");
    section.setAttribute("data-role", "reservations-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pool reservations");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Reservations";
    section.appendChild(heading);
    if (this._reservations_error !== null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "reservations-error");
      error.setAttribute("role", "status");
      error.textContent = section_error_message(
        "this pool's reservations",
        this._reservations_error
      );
      section.appendChild(error);
      const retry = document.createElement("mj-button");
      retry.classList.add("pyc-resources__button");
      retry.setAttribute("type", "button");
      retry.setAttribute("data-role", "reservations-retry");
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        void this._retry_reservations();
      });
      section.appendChild(retry);
      return section;
    }
    if (this._reservations.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-resources__status");
      empty.setAttribute("data-role", "reservations-empty");
      empty.textContent = "No reservations against this pool.";
      section.appendChild(empty);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-resources__history-list");
    for (const reservation of this._reservations) {
      list.appendChild(
        this._build_reservation_row(reservation, write_allowed)
      );
    }
    section.appendChild(list);
    return section;
  }
  async _retry_reservations() {
    await this._refresh_reservations();
    this._render_body();
    return;
  }
  _build_reservation_row(reservation, write_allowed) {
    const item = document.createElement("li");
    item.classList.add("pyc-resources__history-entry");
    const badge = document.createElement("span");
    badge.classList.add("pyc-badge");
    badge.setAttribute("data-tone", reservation_tone(reservation.state));
    badge.textContent = reservation.state;
    item.appendChild(badge);
    const label = document.createElement("span");
    label.classList.add("pyc-resources__reservation-label");
    const summary = " " + short_id(reservation.resource_id) + " \xB7 " + reservation.mode + " \xB7 " + format_timestamp(reservation.requested_at);
    label.textContent = summary;
    label.title = reservation.resource_id;
    item.appendChild(label);
    if (write_allowed === true && is_active_reservation(reservation.state) === true) {
      const release = document.createElement("mj-button");
      release.classList.add("pyc-resources__button");
      release.setAttribute("type", "button");
      release.setAttribute("data-role", "release-reservation");
      release.setAttribute(
        "data-reservation-id",
        reservation.reservation_id
      );
      release.textContent = "Release";
      if (this._releasing[reservation.reservation_id] === true) {
        release.setAttribute("disabled", "");
      }
      release.addEventListener("click", () => {
        void this._submit_release(reservation, release);
      });
      item.appendChild(release);
    }
    return item;
  }
  async _submit_release(reservation, release_button) {
    const reservation_id = reservation.reservation_id;
    if (this._releasing[reservation_id] === true) {
      return;
    }
    const confirmed = await confirm_action(this, "Release the " + reservation.mode + " reservation on " + short_id(reservation.resource_id) + "? The holder loses the resource.", "Release reservation");
    if (confirmed !== true) {
      return;
    }
    this._releasing[reservation_id] = true;
    if (release_button !== null && release_button !== void 0) {
      release_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(
        build_reservation_url(this._pool_id, reservation_id),
        {
          method: "DELETE",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        }
      );
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "Release failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to release reservations.";
        } else if (problem.detail.length > 0) {
          message = "Release failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.release_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Release failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      delete this._releasing[reservation_id];
      if (release_button !== null && release_button !== void 0) {
        release_button.removeAttribute("disabled");
      }
    }
    this._show_action_status("Reservation released.", false);
    await this._refresh_reservations();
    this._render_body();
    return;
  }
  _build_reserve_form() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "reserve-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Reserve a resource";
    section.appendChild(heading);
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "reserve-form");
    const resource_label = document.createElement("label");
    resource_label.classList.add("pyc-resources__filter");
    resource_label.textContent = "Resource";
    const resource_select = document.createElement("mj-select");
    resource_select.classList.add("pyc-resources__select");
    resource_select.setAttribute("data-role", "reserve-resource");
    const any_option = document.createElement("mj-option");
    any_option.setAttribute("value", "");
    any_option.textContent = "Any available member (FIFO)";
    resource_select.appendChild(any_option);
    for (const member of this._members) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", member.resource_id);
      option.textContent = member_display_label(member);
      resource_select.appendChild(option);
    }
    resource_select.setAttribute("value", "");
    resource_label.appendChild(resource_select);
    form.appendChild(resource_label);
    const mode_label = document.createElement("label");
    mode_label.classList.add("pyc-resources__filter");
    mode_label.textContent = "Mode";
    const mode_select = document.createElement("mj-select");
    mode_select.classList.add("pyc-resources__select");
    mode_select.setAttribute("data-role", "reserve-mode");
    for (const mode of ["exclusive", "shared"]) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", mode);
      option.textContent = mode;
      mode_select.appendChild(option);
    }
    mode_select.setAttribute("value", "exclusive");
    mode_label.appendChild(mode_select);
    form.appendChild(mode_label);
    const note_label = document.createElement("label");
    note_label.classList.add("pyc-resources__filter");
    note_label.textContent = "Note";
    const note_input = document.createElement("mj-text-field");
    note_input.classList.add("pyc-resources__input");
    note_input.setAttribute("type", "text");
    note_input.setAttribute("placeholder", "optional");
    note_input.setAttribute("data-role", "reserve-note");
    note_label.appendChild(note_input);
    form.appendChild(note_label);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "reserve-submit");
    submit.textContent = "Reserve";
    if (this._reserving === true) {
      submit.setAttribute("disabled", "");
    }
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_reserve(
        mode_select.value,
        note_input.value.trim(),
        resource_select.value,
        submit
      );
    });
    section.appendChild(form);
    return section;
  }
  async _submit_reserve(mode, note, resource_id, submit_button) {
    if (this._reserving === true) {
      return;
    }
    if (this._project_id.length === 0) {
      this._show_action_status(
        "A project id is required to reserve.",
        true
      );
      return;
    }
    const body = {
      project_id: this._project_id,
      mode
    };
    if (note.length > 0) {
      body["note"] = note;
    }
    if (typeof resource_id === "string" && resource_id.length > 0) {
      body["resource_id"] = resource_id;
    }
    this._reserving = true;
    if (submit_button !== null && submit_button !== void 0) {
      submit_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(
        build_pool_reservations_url(this._pool_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify(body)
        }
      );
      if (response.ok === false) {
        const problem = await read_problem(response);
        this._show_action_status(
          reserve_failure_message(problem),
          true
        );
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.reserve_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Reserve failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      this._reserving = false;
      if (submit_button !== null && submit_button !== void 0) {
        submit_button.removeAttribute("disabled");
      }
    }
    this._show_action_status("Reservation granted.", false);
    await this._refresh_reservations();
    this._render_body();
    return;
  }
  _show_action_status(message, errored) {
    if (this._action_status === null) {
      return;
    }
    this._action_status.hidden = false;
    this._action_status.textContent = message;
    if (errored === true) {
      this._action_status.setAttribute("data-tone", "error");
    } else {
      this._action_status.setAttribute("data-tone", "ok");
    }
    return;
  }
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-resources__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    def.textContent = value;
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
};

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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-resources-bundle/resource-detail-view.js
var PROJECTS_API_PATH3 = "/api/v1/projects";
function parse_tag_list(text) {
  const seen = /* @__PURE__ */ new Set();
  const rtnval = [];
  for (const part of String(text ?? "").split(",")) {
    const tag = part.trim();
    if (tag.length > 0 && seen.has(tag) === false) {
      seen.add(tag);
      rtnval.push(tag);
    }
  }
  return rtnval;
}
function changed_resource_fields(resource, name, description, tags_text) {
  const changes = {};
  const current_name = typeof resource.display_name === "string" ? resource.display_name : "";
  const new_name = String(name ?? "").trim();
  if (new_name !== current_name) {
    if (new_name.length === 0) {
      return null;
    }
    changes.display_name = new_name;
  }
  const current_description = typeof resource.description === "string" ? resource.description : "";
  const new_description = String(description ?? "").trim();
  if (new_description !== current_description) {
    changes.description = new_description;
  }
  const current_tags = Array.isArray(resource.tags) === true ? resource.tags : [];
  const new_tags = parse_tag_list(tags_text);
  if (JSON.stringify(new_tags) !== JSON.stringify(current_tags)) {
    changes.tags = new_tags;
  }
  return changes;
}
function resource_edit_message_for_status(status, detail) {
  const reason = typeof detail === "string" ? detail.trim() : "";
  if (status === 200) {
    return "Resource details saved.";
  }
  if (status === 403) {
    return with_access_request("You do not have permission to edit resources.");
  }
  if (status === 404) {
    return "This resource no longer exists.";
  }
  if (status === 409) {
    return "This resource is retired and can no longer be edited.";
  }
  if (status === 422) {
    return reason.length > 0 ? "The change was rejected: " + reason : "The change was rejected -- check the fields.";
  }
  return "Could not save the changes (HTTP " + String(status) + ").";
}
var PROJECTS_LIST_URL3 = PROJECTS_API_PATH3 + "?per_page=500";
function resource_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/resource-pools/resources/";
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
function usage_event_tone(event_type) {
  if (typeof event_type !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = event_type.toLowerCase();
  if (lowered.indexOf("fail") >= 0 || lowered.indexOf("reject") >= 0 || lowered.indexOf("quarantine") >= 0) {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (lowered.indexOf("grant") >= 0 || lowered.indexOf("register") >= 0 || lowered.indexOf("pass") >= 0) {
    const rtnval2 = "ok";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function build_resource_url(resource_id) {
  const rtnval = "/api/v1/resources/" + encodeURIComponent(resource_id);
  return rtnval;
}
function build_resource_health_url(resource_id) {
  const rtnval = build_resource_url(resource_id) + "/health";
  return rtnval;
}
function build_resource_usage_url(resource_id) {
  const rtnval = build_resource_url(resource_id) + "/usage-history";
  return rtnval;
}
function build_resource_state_url(resource_id) {
  const rtnval = build_resource_url(resource_id) + "/state";
  return rtnval;
}
var STATE_ACTIONS = [
  {
    target: "available",
    label: "Mark available",
    from: ["leased", "quarantined", "maintenance"]
  },
  {
    target: "quarantined",
    label: "Quarantine",
    from: ["available", "leased"]
  },
  {
    target: "maintenance",
    label: "Move to maintenance",
    from: ["available"]
  },
  {
    target: "retired",
    label: "Retire",
    from: ["available", "quarantined", "maintenance"]
  }
];
function legal_state_actions(current_state) {
  const rtnval = [];
  if (typeof current_state !== "string") {
    return rtnval;
  }
  for (const action of STATE_ACTIONS) {
    if (action.from.indexOf(current_state) >= 0) {
      rtnval.push(action);
    }
  }
  return rtnval;
}
function pool_id_from_search(search) {
  if (typeof search !== "string" || search.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const params = new URLSearchParams(search);
  const value = params.get("pool_id");
  if (value === null) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = value.trim();
  return rtnval;
}
var PycResourceDetail = class extends HTMLElement {
  _resource_id;
  _project_id;
  _pool_id;
  _resource;
  _health;
  _health_error;
  _usage;
  _usage_error;
  _project_names;
  _loading;
  _errored;
  _error_status;
  _transitioning;
  _root;
  _action_status;
  constructor() {
    super();
    this._resource_id = "";
    this._project_id = "";
    this._pool_id = "";
    this._resource = null;
    this._health = null;
    this._health_error = null;
    this._usage = [];
    this._usage_error = null;
    this._project_names = {};
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._transitioning = false;
    this._root = null;
    this._action_status = null;
  }
  /**
   * Observed attributes -- ``resource-id`` may be supplied
   * explicitly by a host; otherwise it is read from the path on
   * mount.
   */
  static get observedAttributes() {
    const rtnval = ["resource-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      resourceId: this._resource_id,
      loading: this._loading,
      errored: this._errored,
      errorStatus: this._error_status,
      hasHealth: this._health !== null,
      healthError: this._health_error,
      usageError: this._usage_error,
      transitioning: this._transitioning
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the resource id plus navigation
   * context, render the chrome, and fetch the initial snapshot.
   */
  connectedCallback() {
    const attr_resource = this.getAttribute("resource-id");
    if (attr_resource !== null && attr_resource.length > 0) {
      this._resource_id = attr_resource;
    } else {
      this._resource_id = resource_id_from_path(
        window.location.pathname
      );
    }
    this._project_id = project_id_from_search(window.location.search);
    this._pool_id = pool_id_from_search(window.location.search);
    this._render_chrome();
    on_shell_permissions_changed(() => {
      if (this.isConnected === true) {
        this._render_body();
      }
    });
    void this._load();
    void this._load_project_names();
    return;
  }
  /**
   * Fetch the resource snapshot. Exposed so unit tests can await a
   * load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_uuid(this._resource_id) === false) {
      this._loading = false;
      this._errored = true;
      this._error_status = -1;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_body();
    const resource_result = await this._fetch_json(
      build_resource_url(this._resource_id),
      "resource_fetch_failed"
    );
    if (resource_result.ok === false) {
      this._loading = false;
      this._errored = true;
      this._error_status = resource_result.status;
      this._render_body();
      return;
    }
    this._resource = resource_result.body;
    if (this._project_id.length === 0 && typeof this._resource.project_id === "string") {
      this._project_id = this._resource.project_id;
      this._update_back_links();
    }
    const health_result = await this._fetch_json(
      build_resource_health_url(this._resource_id),
      "health_fetch_failed"
    );
    if (health_result.ok === true) {
      this._health = health_result.body;
      this._health_error = null;
    } else if (health_result.status === 404) {
      this._health = null;
      this._health_error = null;
    } else {
      this._health = null;
      this._health_error = health_result.status;
    }
    const usage_result = await this._fetch_json(
      build_resource_usage_url(this._resource_id),
      "usage_fetch_failed"
    );
    if (usage_result.ok === true && Array.isArray(usage_result.body.items) === true) {
      this._usage = usage_result.body.items;
      this._usage_error = null;
    } else {
      this._usage = [];
      this._usage_error = usage_result.status;
    }
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  /**
   * Best-effort fetch of the projects collection so the summary
   * can show a project display name beside the UUID. Failures are
   * silent -- the UUID alone is always rendered.
   */
  async _load_project_names() {
    try {
      const response = await fetch(PROJECTS_LIST_URL3, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        return;
      }
      const body = await response.json();
      const projects = extract_projects(body);
      const names = {};
      for (const project of projects) {
        names[project.project_id] = project.display_name;
      }
      this._project_names = names;
      if (this._loading === false && this._errored === false && this._resource !== null) {
        this._render_body();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.project_names_fetch_failed",
        { reason: String(reason) }
      );
    }
    return;
  }
  /**
   * GET a JSON document. Returns ``{ok: true, body}`` on a 2xx
   * response and ``{ok: false, status}`` otherwise -- ``status``
   * is ``0`` for network-level failures so callers can render an
   * error state distinct from an empty collection.
   */
  async _fetch_json(url, failure_tag) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        console.warn(
          "pychestrate.ui.resources." + failure_tag,
          { status: response.status }
        );
        const rtnval2 = { ok: false, status: response.status, body: null };
        return rtnval2;
      }
      const body = await response.json();
      const rtnval = { ok: true, status: response.status, body };
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources." + failure_tag,
        { reason: String(reason) }
      );
      const rtnval = { ok: false, status: 0, body: null };
      return rtnval;
    }
  }
  _pools_list_href() {
    let href = "/resource-pools";
    if (this._project_id.length > 0) {
      href = href + "?project_id=" + encodeURIComponent(this._project_id);
    }
    const rtnval = href;
    return rtnval;
  }
  _pool_detail_href() {
    let href = "/resource-pools/" + encodeURIComponent(this._pool_id);
    if (this._project_id.length > 0) {
      href = href + "?project_id=" + encodeURIComponent(this._project_id);
    }
    const rtnval = href;
    return rtnval;
  }
  _update_back_links() {
    if (this._root === null) {
      return;
    }
    const back = this._root.querySelector('[data-role="back-link"]');
    if (back !== null) {
      back.setAttribute("href", this._pools_list_href());
    }
    const pool_back = this._root.querySelector('[data-role="pool-back-link"]');
    if (pool_back !== null) {
      pool_back.setAttribute("href", this._pool_detail_href());
    }
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-resources", "pyc-resource-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Resource detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-resources__back-link");
    back.setAttribute("href", this._pools_list_href());
    back.setAttribute("data-role", "back-link");
    keep_list_state_on_back(back, "/resource-pools");
    back.textContent = "Back to resource pools";
    root.appendChild(back);
    if (this._pool_id.length > 0) {
      const pool_back = document.createElement("a");
      pool_back.classList.add("pyc-resources__back-link");
      pool_back.setAttribute("href", this._pool_detail_href());
      pool_back.setAttribute("data-role", "pool-back-link");
      pool_back.textContent = "Back to pool " + short_id(this._pool_id);
      root.appendChild(pool_back);
    }
    const status = document.createElement("p");
    status.classList.add("pyc-resources__form-status");
    status.setAttribute("data-role", "action-status");
    status.setAttribute("role", "status");
    status.hidden = true;
    root.appendChild(status);
    this._action_status = status;
    const body = document.createElement("div");
    body.classList.add("pyc-resources__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
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
      loading.classList.add("pyc-resources__status");
      loading.setAttribute("data-role", "loading-state");
      loading.setAttribute("role", "status");
      loading.textContent = "Loading resource\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._resource === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.setAttribute("role", "status");
      const status = this._error_status;
      if (status === -1) {
        error.textContent = "The resource id in the URL is not a valid UUID.";
      } else if (status === 404) {
        error.textContent = "This resource was not found. It may have been deleted.";
      } else if (status === 403) {
        error.textContent = with_access_request("You do not have permission to view this resource.");
      } else if (status === 0) {
        error.textContent = "Network error while loading this resource. Try refreshing.";
      } else {
        error.textContent = "Failed to load this resource (HTTP " + String(status) + ").";
      }
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._resource));
    if (shell_write_allowed(RESOURCES_WRITE_PERMISSION) === true) {
      fragment.appendChild(this._build_state_controls(this._resource));
    }
    fragment.appendChild(this._build_health());
    fragment.appendChild(this._build_usage_timeline());
    body.replaceChildren(fragment);
    return;
  }
  _project_field_value(project_id) {
    let value = project_id;
    const display_name = this._project_names[project_id];
    if (typeof display_name === "string" && display_name.length > 0 && display_name !== project_id) {
      value = display_name + " (" + project_id + ")";
    }
    const rtnval = value;
    return rtnval;
  }
  _build_summary(resource) {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Resource summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-resources__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-resources__id");
    id_value.setAttribute("data-role", "resource-id");
    id_value.textContent = short_id(resource.resource_id);
    set_entity_title(String(resource.display_name ?? "") || "Resource " + short_id(resource.resource_id));
    id_value.title = resource.resource_id;
    id_row.appendChild(id_value);
    const badge = document.createElement("span");
    badge.classList.add("pyc-badge");
    badge.setAttribute("data-role", "state-badge");
    badge.setAttribute(
      "data-tone",
      resource_state_tone(resource.state)
    );
    badge.textContent = resource.state;
    id_row.appendChild(badge);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-resources__grid");
    this._append_field(grid, "Resource id", resource.resource_id);
    this._append_field(grid, "Kind", state_label(resource.kind));
    this._append_field(
      grid,
      "Project",
      this._project_field_value(resource.project_id)
    );
    const display_name = resource.display_name !== null && resource.display_name !== void 0 ? resource.display_name : "";
    if (display_name.length > 0) {
      this._append_field(grid, "Display name", display_name);
    }
    const description = typeof resource.description === "string" ? resource.description : "";
    if (description.length > 0) {
      this._append_field(grid, "Description", description);
    }
    this._append_field(grid, "State", resource.state);
    this._append_field(
      grid,
      "Created",
      format_timestamp(resource.created_at)
    );
    section.appendChild(grid);
    const tags = Array.isArray(resource.tags) === true ? resource.tags : [];
    if (tags.length > 0) {
      const tag_list = document.createElement("div");
      tag_list.classList.add("pyc-resources__tag-list");
      for (const tag of tags) {
        const chip = document.createElement("mj-chip");
        chip.classList.add("pyc-resources__tag");
        chip.textContent = tag;
        tag_list.appendChild(chip);
      }
      section.appendChild(tag_list);
    }
    if (resource.state !== "retired" && shell_write_allowed(RESOURCES_WRITE_PERMISSION) === true) {
      const edit_button = document.createElement("mj-button");
      edit_button.classList.add("pyc-resources__button");
      edit_button.setAttribute("type", "button");
      edit_button.setAttribute("data-role", "edit-resource");
      edit_button.textContent = "Edit details";
      const region = document.createElement("div");
      region.classList.add("pyc-resources__form-region");
      region.setAttribute("data-role", "edit-resource-region");
      region.hidden = true;
      edit_button.addEventListener("click", () => {
        this._toggle_edit_form(resource, region);
      });
      section.appendChild(edit_button);
      section.appendChild(region);
    }
    return section;
  }
  /**
   * Open (or close) the form that changes the resource's name, description and tags.
   * The kind, the identity and the attributes are not editable here.
   *
   * @param resource The resource being shown.
   * @param region The container the form is rendered into.
   */
  _toggle_edit_form(resource, region) {
    if (region.hidden === false) {
      region.hidden = true;
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-resources__filters");
    form.setAttribute("data-role", "edit-resource-form");
    const name_label = document.createElement("label");
    name_label.classList.add("pyc-resources__filter");
    name_label.textContent = "Display name";
    const name_input = document.createElement("mj-text-field");
    name_input.classList.add("pyc-resources__input");
    name_input.setAttribute("type", "text");
    name_input.setAttribute("data-role", "edit-resource-name");
    name_label.appendChild(name_input);
    form.appendChild(name_label);
    const description_label = document.createElement("label");
    description_label.classList.add("pyc-resources__filter");
    description_label.textContent = "Description";
    const description_input = document.createElement("mj-textarea");
    description_input.classList.add("pyc-resources__input");
    description_input.setAttribute("data-role", "edit-resource-description");
    description_input.rows = 3;
    description_label.appendChild(description_input);
    form.appendChild(description_label);
    const tags_label = document.createElement("label");
    tags_label.classList.add("pyc-resources__filter");
    tags_label.textContent = "Tags";
    const tags_input = document.createElement("mj-text-field");
    tags_input.classList.add("pyc-resources__input");
    tags_input.setAttribute("type", "text");
    tags_input.setAttribute("data-role", "edit-resource-tags");
    tags_input.setAttribute("placeholder", "gpu, lab-2");
    tags_input.setAttribute("help-text", "Separate tags with commas.");
    tags_label.appendChild(tags_input);
    form.appendChild(tags_label);
    const save_button = document.createElement("mj-button");
    save_button.classList.add("pyc-resources__button");
    save_button.setAttribute("type", "submit");
    save_button.setAttribute("data-role", "edit-resource-save");
    save_button.textContent = "Save changes";
    form.appendChild(save_button);
    const cancel_button = document.createElement("mj-button");
    cancel_button.classList.add("pyc-resources__button");
    cancel_button.setAttribute("type", "button");
    cancel_button.setAttribute("data-role", "edit-resource-cancel");
    cancel_button.textContent = "Cancel";
    cancel_button.addEventListener("click", () => {
      region.hidden = true;
    });
    form.appendChild(cancel_button);
    const status = document.createElement("p");
    status.classList.add("pyc-resources__form-status");
    status.setAttribute("data-role", "edit-resource-status");
    status.setAttribute("role", "status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_edit(resource, region, name_input, description_input, tags_input, save_button, status);
    });
    region.replaceChildren(form);
    region.hidden = false;
    name_input.value = typeof resource.display_name === "string" ? resource.display_name : "";
    description_input.value = typeof resource.description === "string" ? resource.description : "";
    tags_input.value = Array.isArray(resource.tags) === true ? resource.tags.join(", ") : "";
    reveal(region);
    return;
  }
  async _submit_edit(resource, region, name_input, description_input, tags_input, save_button, status) {
    const changes = changed_resource_fields(resource, name_input.value, description_input.value, tags_input.value);
    if (changes === null) {
      status.textContent = "The display name cannot be empty.";
      return;
    }
    if (Object.keys(changes).length === 0) {
      region.hidden = true;
      this._show_action_status("Nothing to change.", false);
      return;
    }
    save_button.setAttribute("disabled", "");
    status.textContent = "Saving\u2026";
    const outcome = await this._do_edit(changes);
    save_button.removeAttribute("disabled");
    if (outcome.ok !== true) {
      status.textContent = outcome.message;
      return;
    }
    region.hidden = true;
    this._show_action_status(outcome.message, false);
    await this._load();
    return;
  }
  /**
   * ``PATCH`` the changed fields of the resource. Exposed so unit tests can drive it without a form.
   *
   * @param changes ``{display_name?, description?, tags?}``.
   *
   * @returns ``{ok, status, message}``.
   */
  async _do_edit(changes) {
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(build_resource_url(this._resource_id), {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(changes)
      });
      status = response.status;
      if (response.ok === false) {
        const problem = await read_problem(response);
        detail = problem.detail;
      }
    } catch (reason) {
      console.warn("pychestrate.ui.resources.resource_update_failed", { reason: String(reason) });
      return { ok: false, status: 0, message: "Could not save the changes -- network error. Try again." };
    }
    return { ok: status === 200, status, message: resource_edit_message_for_status(status, detail) };
  }
  /**
   * Build the lifecycle-transition panel -- one button per legal
   * transition out of the resource's current state, an optional
   * reason field, confirm dialogs (retire gets consequence text),
   * and in-flight disabling.
   */
  _build_state_controls(resource) {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "state-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Resource lifecycle");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Lifecycle";
    section.appendChild(heading);
    const actions = legal_state_actions(resource.state);
    if (actions.length === 0) {
      const note = document.createElement("p");
      note.classList.add("pyc-resources__status");
      note.setAttribute("data-role", "state-terminal");
      if (resource.state === "retired") {
        note.textContent = "This resource is retired. Retired is terminal -- register the resource again to bring it back.";
      } else {
        note.textContent = "No lifecycle transitions are available from the current state.";
      }
      section.appendChild(note);
      return section;
    }
    const reason_label = document.createElement("label");
    reason_label.classList.add("pyc-resources__filter");
    reason_label.textContent = "Reason";
    const reason_input = document.createElement("mj-text-field");
    reason_input.classList.add("pyc-resources__input");
    reason_input.setAttribute("type", "text");
    reason_input.setAttribute("placeholder", "optional");
    reason_input.setAttribute("data-role", "state-reason");
    reason_label.appendChild(reason_input);
    section.appendChild(reason_label);
    const button_row = document.createElement("div");
    button_row.classList.add("pyc-resources__filters");
    button_row.setAttribute("data-role", "state-actions");
    const buttons = [];
    for (const action of actions) {
      const button = document.createElement("mj-button");
      button.classList.add("pyc-resources__button");
      button.setAttribute("type", "button");
      button.setAttribute("data-role", "state-action");
      button.setAttribute("data-target-state", action.target);
      button.textContent = action.label;
      if (this._transitioning === true) {
        button.setAttribute("disabled", "");
      }
      button.addEventListener("click", () => {
        void this._submit_transition(
          action,
          reason_input.value.trim(),
          buttons
        );
      });
      button_row.appendChild(button);
      buttons.push(button);
    }
    section.appendChild(button_row);
    return section;
  }
  async _submit_transition(action, reason, buttons) {
    if (this._transitioning === true) {
      return;
    }
    const resource_label = this._resource !== null && typeof this._resource.display_name === "string" && this._resource.display_name.length > 0 ? this._resource.display_name : short_id(this._resource_id);
    let prompt = "Move " + resource_label + " to state '" + action.target + "'?";
    if (action.target === "retired") {
      prompt = "Retire " + resource_label + "? Retiring is permanent -- a retired resource cannot be reactivated and must be registered again.";
    } else if (action.target === "quarantined") {
      prompt = "Quarantine " + resource_label + "? Quarantined resources are excluded from pool allocation until marked available again.";
    }
    const confirmed = await confirm_action(this, prompt, action.target === "retired" ? "Retire resource" : action.target === "quarantined" ? "Quarantine resource" : "Change state");
    if (confirmed !== true) {
      return;
    }
    const body = { state: action.target };
    if (reason.length > 0) {
      body["reason"] = reason;
    }
    this._transitioning = true;
    if (Array.isArray(buttons) === true) {
      for (const button of buttons) {
        button.setAttribute("disabled", "");
      }
    }
    try {
      const response = await fetch(
        build_resource_state_url(this._resource_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify(body)
        }
      );
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "State change failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to change resource state.";
        } else if (problem.status === 409) {
          message = "This transition is not permitted from the resource's current state. Refresh and try again.";
        } else if (problem.detail.length > 0) {
          message = "State change failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason_caught) {
      console.warn(
        "pychestrate.ui.resources.state_transition_failed",
        { reason: String(reason_caught) }
      );
      this._show_action_status(
        "State change failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      this._transitioning = false;
      if (Array.isArray(buttons) === true) {
        for (const button of buttons) {
          button.removeAttribute("disabled");
        }
      }
    }
    this._show_action_status(
      "Resource moved to '" + action.target + "'.",
      false
    );
    await this._load();
    return;
  }
  _show_action_status(message, errored) {
    if (this._action_status === null) {
      return;
    }
    this._action_status.hidden = false;
    this._action_status.textContent = message;
    if (errored === true) {
      this._action_status.setAttribute("data-tone", "error");
    } else {
      this._action_status.setAttribute("data-tone", "ok");
    }
    return;
  }
  _build_health() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__health");
    section.setAttribute("data-role", "health-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Resource health");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Health";
    section.appendChild(heading);
    if (this._health_error !== null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "health-error-state");
      error.setAttribute("role", "status");
      error.textContent = section_error_message(
        "this resource's health record",
        this._health_error
      );
      section.appendChild(error);
      return section;
    }
    if (this._health === null) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-resources__status");
      empty.setAttribute("data-role", "health-empty");
      empty.textContent = "No health record has been seeded for this resource.";
      section.appendChild(empty);
      return section;
    }
    const health = this._health;
    const outcome_row = document.createElement("div");
    outcome_row.classList.add("pyc-resources__id-row");
    const badge = document.createElement("span");
    badge.classList.add("pyc-badge");
    badge.setAttribute("data-role", "health-badge");
    badge.setAttribute("data-tone", health_tone(health.last_outcome));
    badge.textContent = health.last_outcome;
    outcome_row.appendChild(badge);
    const probe = document.createElement("span");
    probe.classList.add("pyc-resources__reservation-label");
    probe.textContent = " " + health.probe_name;
    outcome_row.appendChild(probe);
    section.appendChild(outcome_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-resources__grid");
    this._append_field(
      grid,
      "Last probe",
      format_timestamp(health.last_probe_at)
    );
    this._append_field(
      grid,
      "Last pass",
      format_timestamp(health.last_pass_at)
    );
    this._append_field(
      grid,
      "Last fail",
      format_timestamp(health.last_fail_at)
    );
    this._append_field(
      grid,
      "Pass count",
      String(health.pass_count !== null && health.pass_count !== void 0 ? health.pass_count : 0)
    );
    this._append_field(
      grid,
      "Fail count",
      String(health.fail_count !== null && health.fail_count !== void 0 ? health.fail_count : 0)
    );
    this._append_field(
      grid,
      "Consecutive failures",
      String(health.consecutive_failures !== null && health.consecutive_failures !== void 0 ? health.consecutive_failures : 0)
    );
    section.appendChild(grid);
    if (health.last_error !== null && health.last_error !== void 0 && health.last_error.length > 0) {
      const error = document.createElement("p");
      error.classList.add("pyc-resources__health-error");
      error.setAttribute("data-role", "health-error");
      error.textContent = "Last error: " + health.last_error;
      section.appendChild(error);
    }
    return section;
  }
  _build_usage_timeline() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__usage");
    section.setAttribute("data-role", "usage-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Usage history");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Usage history";
    section.appendChild(heading);
    if (this._usage_error !== null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "usage-error-state");
      error.setAttribute("role", "status");
      error.textContent = section_error_message(
        "this resource's usage history",
        this._usage_error
      );
      section.appendChild(error);
      return section;
    }
    if (this._usage.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-resources__status");
      empty.setAttribute("data-role", "usage-empty");
      empty.textContent = "No usage-history events for this resource.";
      section.appendChild(empty);
      return section;
    }
    const timeline = document.createElement("ol");
    timeline.classList.add("pyc-resources__timeline");
    timeline.setAttribute("data-role", "usage-timeline");
    for (const record of this._usage) {
      const item = document.createElement("li");
      item.classList.add("pyc-resources__timeline-entry");
      const marker = document.createElement("span");
      marker.classList.add("pyc-resources__timeline-marker");
      marker.setAttribute(
        "data-tone",
        usage_event_tone(record.event_type)
      );
      item.appendChild(marker);
      const detail = document.createElement("div");
      detail.classList.add("pyc-resources__timeline-detail");
      const type_line = document.createElement("span");
      type_line.classList.add("pyc-resources__timeline-type");
      type_line.textContent = record.event_type;
      detail.appendChild(type_line);
      const ts_line = document.createElement("span");
      ts_line.classList.add("pyc-resources__timeline-ts");
      ts_line.textContent = format_timestamp(record.at_ts);
      detail.appendChild(ts_line);
      item.appendChild(detail);
      timeline.appendChild(item);
    }
    section.appendChild(timeline);
    return section;
  }
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-resources__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    def.textContent = value;
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-resources-bundle/index.entry.js
var RESOURCE_POOLS_ROUTE = "/resource-pools";
var RESOURCE_POOLS_TAG = "pyc-resource-pools";
var RESOURCE_INVENTORY_TAG = "pyc-resource-inventory";
var POOL_DETAIL_TAG = "pyc-pool-detail";
var RESOURCE_DETAIL_TAG = "pyc-resource-detail";
var RESOURCES_STYLESHEET_HREF = "/static/javascript/pyc-resources-bundle/pyc-resources-bundle.css";
function ensure_resources_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-resources-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = RESOURCES_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-resources-bundle");
  document.head.appendChild(link);
  return;
}
function define_resources_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(RESOURCE_INVENTORY_TAG) === void 0) {
    customElements.define(RESOURCE_INVENTORY_TAG, PycResourceInventory);
  }
  if (customElements.get(RESOURCE_POOLS_TAG) === void 0) {
    customElements.define(RESOURCE_POOLS_TAG, PycResourcePools);
  }
  if (customElements.get(POOL_DETAIL_TAG) === void 0) {
    customElements.define(POOL_DETAIL_TAG, PycPoolDetail);
  }
  if (customElements.get(RESOURCE_DETAIL_TAG) === void 0) {
    customElements.define(RESOURCE_DETAIL_TAG, PycResourceDetail);
  }
  return;
}
function classify_resources_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working !== RESOURCE_POOLS_ROUTE && working.startsWith(RESOURCE_POOLS_ROUTE + "/") === false) {
    const rtnval2 = "none";
    return rtnval2;
  }
  const resource_id = resource_id_from_path(working);
  if (resource_id.length > 0) {
    const rtnval2 = "resource-detail";
    return rtnval2;
  }
  const pool_id = pool_id_from_path(working);
  if (pool_id.length > 0 && pool_id !== "resources") {
    const rtnval2 = "pool-detail";
    return rtnval2;
  }
  const rtnval = "pools-list";
  return rtnval;
}
function tag_for_resources_route(route) {
  if (route === "pools-list") {
    const rtnval2 = RESOURCE_POOLS_TAG;
    return rtnval2;
  }
  if (route === "pool-detail") {
    const rtnval2 = POOL_DETAIL_TAG;
    return rtnval2;
  }
  if (route === "resource-detail") {
    const rtnval2 = RESOURCE_DETAIL_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_resources_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_resources_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_resources_route(route);
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
  define_resources_elements();
  ensure_resources_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_resources_view_if_active();
  return;
}
function _boot() {
  define_resources_elements();
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
      "pychestrate.ui.resources.bundle_no_shell_handle",
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
  ACTIVE_RESERVATION_STATES,
  PycPoolDetail,
  PycResourceDetail,
  PycResourcePools,
  RESOURCES_WRITE_PERMISSION,
  RESOURCE_POOLS_WRITE_PERMISSION,
  STATE_ACTIONS,
  build_pool_member_url,
  build_pool_reservations_url,
  build_pool_resources_url,
  build_pool_url,
  build_reservation_url,
  build_resource_health_url,
  build_resource_pools_url,
  build_resource_state_url,
  build_resource_url,
  build_resource_usage_url,
  classify_resources_route,
  define_resources_elements,
  ensure_resources_stylesheet,
  extract_projects,
  format_timestamp,
  health_tone,
  is_active_reservation,
  is_valid_uuid,
  legal_state_actions,
  member_display_label,
  mount_resources_view_if_active,
  parse_capability_tags,
  pool_id_from_path,
  pool_id_from_search,
  project_id_from_search,
  read_problem,
  reservation_tone,
  reserve_failure_message,
  resource_id_from_path,
  resource_state_tone,
  section_error_message,
  shell_write_allowed,
  short_id,
  tag_for_resources_route,
  total_pages_for,
  usage_event_tone
};
