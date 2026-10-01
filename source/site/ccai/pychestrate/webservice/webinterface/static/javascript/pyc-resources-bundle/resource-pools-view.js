import { format_timestamp } from "../shared/datetime.js";
import { with_access_request } from "../shared/admin-contact.js";
import { build_empty_state } from "../shared/empty-state.js";
import { mirror_to_query, page_from_query } from "../shared/view-state.js";
const DEFAULT_PER_PAGE = 50;
const RESOURCE_POOLS_API_PATH = "/api/v1/resource-pools";
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
const RESOURCE_POOLS_WRITE_PERMISSION = "system:resource_pools.write";
const RESOURCES_WRITE_PERMISSION = "system:resources.write";
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
class PycResourcePools extends HTMLElement {
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
    // The project's registered resources, and the form that registers one
    // (RES-04): a pool's members come from here.
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
      loading.textContent = "Loading projects…";
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
    // The address describes what is on screen (ORC-27).
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
      loading.textContent = "Loading resource pools…";
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
          const rtnval = pool.name !== null && pool.name.length > 0 ? pool.name : "—";
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
            const rtnval2 = "—";
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
}
export {
  PycResourcePools,
  RESOURCE_POOLS_WRITE_PERMISSION,
  RESOURCES_WRITE_PERMISSION,
  build_resource_pools_url,
  extract_projects,
  format_timestamp,
  health_tone,
  on_shell_permissions_changed,
  parse_capability_tags,
  read_problem,
  resource_state_tone,
  shell_write_allowed,
  short_id,
  total_pages_for
};
