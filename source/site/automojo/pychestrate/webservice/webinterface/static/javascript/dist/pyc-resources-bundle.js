// src/pyc-resources-bundle/resource-pools-view.ts
var DEFAULT_PER_PAGE = 50;
var RESOURCE_POOLS_API_PATH = "/api/v1/resource-pools";
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
function format_timestamp(value) {
  if (value === null || value === void 0 || value.length === 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = parsed.toLocaleString();
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
function has_next_page(state) {
  const consumed = state.page * state.perPage;
  const rtnval = consumed < state.total;
  return rtnval;
}
function has_previous_page(state) {
  const rtnval = state.page > 1;
  return rtnval;
}
var PycResourcePools = class extends HTMLElement {
  _state;
  _pools;
  _root;
  _table_region;
  _create_status;
  constructor() {
    super();
    this._state = {
      projectFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false,
      needsProject: true
    };
    this._pools = [];
    this._root = null;
    this._table_region = null;
    this._create_status = null;
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
      needsProject: this._state.needsProject
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome. A ``?project_id=``
   * query parameter seeds an immediate fetch; otherwise the view
   * shows a "pick a project" prompt.
   */
  connectedCallback() {
    const seeded = this._project_from_search();
    if (seeded.length > 0) {
      this._state.projectFilter = seeded;
    }
    this._render_chrome();
    if (this._state.projectFilter.length > 0) {
      void this._refresh();
    } else {
      this._render_table_region();
    }
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
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-resources");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource pools";
    root.appendChild(heading);
    const subtitle = document.createElement("p");
    subtitle.classList.add("pyc-resources__subtitle");
    subtitle.textContent = "Resource pools are project-scoped. Enter a project id to list its pools.";
    root.appendChild(subtitle);
    const filters = document.createElement("div");
    filters.classList.add("pyc-resources__filters");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-resources__filter");
    project_label.textContent = "Project";
    const project_input = document.createElement("input");
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
    filters.appendChild(project_label);
    const refresh_button = document.createElement("button");
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
    root.appendChild(this._build_create_form());
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-resources__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("div");
    pager.classList.add("pyc-resources__pager");
    const prev_button = document.createElement("button");
    prev_button.classList.add("pyc-resources__button");
    prev_button.setAttribute("type", "button");
    prev_button.setAttribute("data-role", "prev-page");
    prev_button.textContent = "Previous";
    prev_button.addEventListener("click", () => {
      if (has_previous_page(this._state) === true) {
        this._state.page = this._state.page - 1;
        void this._refresh();
      }
    });
    pager.appendChild(prev_button);
    const page_indicator = document.createElement("span");
    page_indicator.classList.add("pyc-resources__page-indicator");
    page_indicator.setAttribute("data-role", "page-indicator");
    pager.appendChild(page_indicator);
    const next_button = document.createElement("button");
    next_button.classList.add("pyc-resources__button");
    next_button.setAttribute("type", "button");
    next_button.setAttribute("data-role", "next-page");
    next_button.textContent = "Next";
    next_button.addEventListener("click", () => {
      if (has_next_page(this._state) === true) {
        this._state.page = this._state.page + 1;
        void this._refresh();
      }
    });
    pager.appendChild(next_button);
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  _build_create_form() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "create-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Create pool";
    section.appendChild(heading);
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "create-form");
    const name_label = document.createElement("label");
    name_label.classList.add("pyc-resources__filter");
    name_label.textContent = "Name";
    const name_input = document.createElement("input");
    name_input.classList.add("pyc-resources__input");
    name_input.setAttribute("type", "text");
    name_input.setAttribute("placeholder", "pool name");
    name_input.setAttribute("data-role", "create-name");
    name_label.appendChild(name_input);
    form.appendChild(name_label);
    const desc_label = document.createElement("label");
    desc_label.classList.add("pyc-resources__filter");
    desc_label.textContent = "Description";
    const desc_input = document.createElement("input");
    desc_input.classList.add("pyc-resources__input");
    desc_input.setAttribute("type", "text");
    desc_input.setAttribute("placeholder", "optional");
    desc_input.setAttribute("data-role", "create-description");
    desc_label.appendChild(desc_input);
    form.appendChild(desc_label);
    const tags_label = document.createElement("label");
    tags_label.classList.add("pyc-resources__filter");
    tags_label.textContent = "Capability tags";
    const tags_input = document.createElement("input");
    tags_input.classList.add("pyc-resources__input");
    tags_input.setAttribute("type", "text");
    tags_input.setAttribute("placeholder", "comma-separated");
    tags_input.setAttribute("data-role", "create-tags");
    tags_label.appendChild(tags_input);
    form.appendChild(tags_label);
    const submit = document.createElement("button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "create-submit");
    submit.textContent = "Create Pool";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-resources__form-status");
    status.setAttribute("data-role", "create-status");
    status.hidden = true;
    this._create_status = status;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_create(
        name_input.value.trim(),
        desc_input.value.trim(),
        tags_input.value
      );
    });
    section.appendChild(form);
    section.appendChild(status);
    return section;
  }
  async _submit_create(name, description, tags_raw) {
    if (this._state.projectFilter.length === 0) {
      this._show_create_status(
        "Enter a project id before creating a pool.",
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
        this._show_create_status(
          "Create failed: HTTP " + String(response.status),
          true
        );
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.pool_create_failed",
        { reason: String(reason) }
      );
      this._show_create_status(
        "Create failed -- see the console for detail.",
        true
      );
      return;
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
  async _refresh() {
    if (this._state.projectFilter.length === 0) {
      this._state.needsProject = true;
      this._render_table_region();
      return;
    }
    this._state.needsProject = false;
    this._state.loading = true;
    this._state.errored = false;
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
        throw new Error(
          "resource-pools fetch failed: HTTP " + String(response.status)
        );
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
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._state.loading = false;
      this._state.errored = true;
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
      prompt.textContent = "Enter a project id above to list its resource pools.";
      region.replaceChildren(prompt);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-resources__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading resource pools\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load resource pools. Try refreshing.";
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._pools.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-resources__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No resource pools in this project";
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
    const table = document.createElement("table");
    table.classList.add("pyc-resources__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = ["Pool", "Name", "Capabilities", "Members"];
    for (const column of columns) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column;
      head_row.appendChild(th);
    }
    thead.appendChild(head_row);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const pool of this._pools) {
      const row = document.createElement("tr");
      row.classList.add("pyc-resources__row");
      const id_cell = document.createElement("td");
      const link = document.createElement("a");
      link.classList.add("pyc-resources__link");
      const href = "/resource-pools/" + pool.pool_id + "?project_id=" + encodeURIComponent(pool.project_id);
      link.setAttribute("href", href);
      link.textContent = short_id(pool.pool_id);
      link.title = pool.pool_id;
      id_cell.appendChild(link);
      row.appendChild(id_cell);
      const name_cell = document.createElement("td");
      name_cell.textContent = pool.name !== null && pool.name.length > 0 ? pool.name : "\u2014";
      row.appendChild(name_cell);
      const tags_cell = document.createElement("td");
      const tags = Array.isArray(pool.capability_tags) === true ? pool.capability_tags : [];
      if (tags.length === 0) {
        tags_cell.textContent = "\u2014";
      } else {
        for (const tag of tags) {
          const chip = document.createElement("span");
          chip.classList.add("pyc-resources__tag");
          chip.textContent = tag;
          tags_cell.appendChild(chip);
        }
      }
      row.appendChild(tags_cell);
      const members_cell = document.createElement("td");
      members_cell.textContent = String(pool.member_count);
      row.appendChild(members_cell);
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    return table;
  }
  _render_pager() {
    if (this._root === null) {
      return;
    }
    const prev = this._root.querySelector('[data-role="prev-page"]');
    const next = this._root.querySelector('[data-role="next-page"]');
    const indicator = this._root.querySelector('[data-role="page-indicator"]');
    if (prev instanceof HTMLButtonElement) {
      prev.disabled = has_previous_page(this._state) === false;
    }
    if (next instanceof HTMLButtonElement) {
      next.disabled = has_next_page(this._state) === false;
    }
    if (indicator instanceof HTMLElement) {
      const label = "Page " + String(this._state.page) + " \xB7 " + String(this._state.total) + " total";
      indicator.textContent = label;
    }
    return;
  }
};

// src/pyc-resources-bundle/pool-detail-view.ts
var ACTIVE_RESERVATION_STATES = [
  "pending",
  "granted"
];
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
function build_pool_reservations_url(pool_id) {
  const rtnval = build_pool_url(pool_id) + "/reservations";
  return rtnval;
}
function build_reservation_url(pool_id, reservation_id) {
  const rtnval = build_pool_reservations_url(pool_id) + "/" + encodeURIComponent(reservation_id);
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
      errored: this._errored
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
    void this._load();
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
      this._render_body();
      return;
    }
    if (this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const pool = await this._fetch_json(
      build_pool_url(this._pool_id),
      "pool_fetch_failed"
    );
    if (pool === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._pool = pool;
    await this._refresh_members();
    await this._refresh_reservations();
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  async _refresh_members() {
    const page = await this._fetch_json(
      build_pool_resources_url(this._pool_id),
      "members_fetch_failed"
    );
    if (page !== null && Array.isArray(page.items) === true) {
      this._members = page.items;
    }
    return;
  }
  async _refresh_reservations() {
    const page = await this._fetch_json(
      build_pool_reservations_url(this._pool_id),
      "reservations_fetch_failed"
    );
    if (page !== null && Array.isArray(page.items) === true) {
      this._reservations = page.items;
    }
    return;
  }
  async _fetch_json(url, failure_tag) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        const rtnval2 = null;
        return rtnval2;
      }
      const body = await response.json();
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources." + failure_tag,
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-resources", "pyc-pool-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Resource pool detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource pool detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-resources__back-link");
    back.setAttribute("href", "/resource-pools");
    back.setAttribute("data-role", "back-link");
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
      error.textContent = "Failed to load this resource pool. A project id query parameter is required \u2014 try refreshing from the resource-pools list.";
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._pool));
    fragment.appendChild(this._build_resources());
    fragment.appendChild(this._build_add_resource_form());
    fragment.appendChild(this._build_reservations());
    fragment.appendChild(this._build_reserve_form());
    body.replaceChildren(fragment);
    return;
  }
  _build_summary(pool) {
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
    id_value.title = pool.pool_id;
    id_row.appendChild(id_value);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-resources__grid");
    this._append_field(grid, "Pool id", pool.pool_id);
    this._append_field(grid, "Name", pool.name);
    this._append_field(grid, "Project", pool.project_id);
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
        const chip = document.createElement("span");
        chip.classList.add("pyc-resources__tag");
        chip.textContent = tag;
        tag_list.appendChild(chip);
      }
      section.appendChild(tag_list);
    }
    return section;
  }
  _build_resources() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__resources");
    section.setAttribute("data-role", "resources-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pool resources");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Resources";
    section.appendChild(heading);
    if (this._members.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-resources__status");
      empty.setAttribute("data-role", "resources-empty");
      empty.textContent = "This pool has no resource members.";
      section.appendChild(empty);
      return section;
    }
    const table = document.createElement("table");
    table.classList.add("pyc-resources__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    for (const column of ["Resource", "Added"]) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column;
      head_row.appendChild(th);
    }
    thead.appendChild(head_row);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const member of this._members) {
      const row = document.createElement("tr");
      row.classList.add("pyc-resources__row");
      const id_cell = document.createElement("td");
      const link = document.createElement("a");
      link.classList.add("pyc-resources__link");
      link.setAttribute(
        "href",
        "/resource-pools/resources/" + member.resource_id
      );
      link.textContent = short_id(member.resource_id);
      link.title = member.resource_id;
      id_cell.appendChild(link);
      row.appendChild(id_cell);
      const added_cell = document.createElement("td");
      added_cell.textContent = format_timestamp(member.added_at);
      row.appendChild(added_cell);
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    section.appendChild(table);
    return section;
  }
  _build_add_resource_form() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "add-resource-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Add resource";
    section.appendChild(heading);
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "add-resource-form");
    const id_label = document.createElement("label");
    id_label.classList.add("pyc-resources__filter");
    id_label.textContent = "Resource id";
    const id_input = document.createElement("input");
    id_input.classList.add("pyc-resources__input");
    id_input.setAttribute("type", "text");
    id_input.setAttribute("placeholder", "resource uuid");
    id_input.setAttribute("data-role", "add-resource-id");
    id_label.appendChild(id_input);
    form.appendChild(id_label);
    const submit = document.createElement("button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "add-resource-submit");
    submit.textContent = "Add Resource";
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_add_resource(id_input.value.trim());
    });
    section.appendChild(form);
    return section;
  }
  async _submit_add_resource(resource_id) {
    if (is_valid_uuid(resource_id) === false) {
      this._show_action_status(
        "A valid resource id (UUID) is required.",
        true
      );
      return;
    }
    const body = { resource_id };
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
        this._show_action_status(
          "Add resource failed: HTTP " + String(response.status),
          true
        );
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.add_resource_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Add resource failed -- see the console.",
        true
      );
      return;
    }
    this._show_action_status("Resource added to the pool.", false);
    await this._refresh_members();
    this._render_body();
    return;
  }
  _build_reservations() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__reservations");
    section.setAttribute("data-role", "reservations-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pool reservations");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Reservations";
    section.appendChild(heading);
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
      list.appendChild(this._build_reservation_row(reservation));
    }
    section.appendChild(list);
    return section;
  }
  _build_reservation_row(reservation) {
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
    if (is_active_reservation(reservation.state) === true) {
      const release = document.createElement("button");
      release.classList.add("pyc-resources__button");
      release.setAttribute("type", "button");
      release.setAttribute("data-role", "release-reservation");
      release.setAttribute(
        "data-reservation-id",
        reservation.reservation_id
      );
      release.textContent = "Release";
      release.addEventListener("click", () => {
        void this._submit_release(reservation.reservation_id);
      });
      item.appendChild(release);
    }
    return item;
  }
  async _submit_release(reservation_id) {
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
        this._show_action_status(
          "Release failed: HTTP " + String(response.status),
          true
        );
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.release_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Release failed -- see the console.",
        true
      );
      return;
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
    const mode_label = document.createElement("label");
    mode_label.classList.add("pyc-resources__filter");
    mode_label.textContent = "Mode";
    const mode_select = document.createElement("select");
    mode_select.classList.add("pyc-resources__select");
    mode_select.setAttribute("data-role", "reserve-mode");
    for (const mode of ["exclusive", "shared"]) {
      const option = document.createElement("option");
      option.value = mode;
      option.textContent = mode;
      mode_select.appendChild(option);
    }
    mode_label.appendChild(mode_select);
    form.appendChild(mode_label);
    const note_label = document.createElement("label");
    note_label.classList.add("pyc-resources__filter");
    note_label.textContent = "Note";
    const note_input = document.createElement("input");
    note_input.classList.add("pyc-resources__input");
    note_input.setAttribute("type", "text");
    note_input.setAttribute("placeholder", "optional");
    note_input.setAttribute("data-role", "reserve-note");
    note_label.appendChild(note_input);
    form.appendChild(note_label);
    const submit = document.createElement("button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "reserve-submit");
    submit.textContent = "Reserve";
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_reserve(
        mode_select.value,
        note_input.value.trim()
      );
    });
    section.appendChild(form);
    return section;
  }
  async _submit_reserve(mode, note) {
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
        this._show_action_status(
          "Reserve failed: HTTP " + String(response.status),
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
        "Reserve failed -- see the console.",
        true
      );
      return;
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

// src/pyc-resources-bundle/resource-detail-view.ts
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
var PycResourceDetail = class extends HTMLElement {
  _resource_id;
  _resource;
  _health;
  _usage;
  _loading;
  _errored;
  _root;
  constructor() {
    super();
    this._resource_id = "";
    this._resource = null;
    this._health = null;
    this._usage = [];
    this._loading = false;
    this._errored = false;
    this._root = null;
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
      hasHealth: this._health !== null
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the resource id, render the chrome,
   * and fetch the initial snapshot.
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
    this._render_chrome();
    void this._load();
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
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const resource = await this._fetch_json(
      build_resource_url(this._resource_id),
      "resource_fetch_failed"
    );
    if (resource === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._resource = resource;
    this._health = await this._fetch_json(
      build_resource_health_url(this._resource_id),
      "health_fetch_failed"
    );
    const usage = await this._fetch_json(
      build_resource_usage_url(this._resource_id),
      "usage_fetch_failed"
    );
    if (usage !== null && Array.isArray(usage.items) === true) {
      this._usage = usage.items;
    }
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  async _fetch_json(url, failure_tag) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        const rtnval2 = null;
        return rtnval2;
      }
      const body = await response.json();
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources." + failure_tag,
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-resources", "pyc-resource-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Resource detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-resources__back-link");
    back.setAttribute("href", "/resource-pools");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to resource pools";
    root.appendChild(back);
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
      error.textContent = "Failed to load this resource. Try refreshing.";
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._resource));
    fragment.appendChild(this._build_health());
    fragment.appendChild(this._build_usage_timeline());
    body.replaceChildren(fragment);
    return;
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
    this._append_field(grid, "Kind", resource.kind);
    this._append_field(grid, "Project", resource.project_id);
    const display_name = resource.display_name !== null && resource.display_name !== void 0 ? resource.display_name : "";
    if (display_name.length > 0) {
      this._append_field(grid, "Display name", display_name);
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
        const chip = document.createElement("span");
        chip.classList.add("pyc-resources__tag");
        chip.textContent = tag;
        tag_list.appendChild(chip);
      }
      section.appendChild(tag_list);
    }
    return section;
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

// src/pyc-resources-bundle/index.ts
var FLEET_GROUP_ID = "fleet";
var RESOURCES_READ_PERMISSION = "system:resources.read";
var RESOURCE_POOLS_ROUTE = "/resource-pools";
var RESOURCE_POOLS_TAG = "pyc-resource-pools";
var POOL_DETAIL_TAG = "pyc-pool-detail";
var RESOURCE_DETAIL_TAG = "pyc-resource-detail";
var RESOURCES_STYLESHEET_HREF = "/static/javascript/dist/pyc-resources-bundle.css";
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
var RESOURCES_ENTRY = {
  entryId: "fleet.resources",
  label: "Resources",
  route: RESOURCE_POOLS_ROUTE,
  requiredPermissions: [RESOURCES_READ_PERMISSION],
  group: FLEET_GROUP_ID
};
function register_resources_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: FLEET_GROUP_ID,
    label: "Fleet",
    requiredPermissions: [RESOURCES_READ_PERMISSION]
  });
  sidebar.registerEntry(RESOURCES_ENTRY);
  return;
}
function define_resources_elements() {
  if (typeof customElements === "undefined") {
    return;
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
  if (working === RESOURCE_POOLS_ROUTE || working === RESOURCE_POOLS_ROUTE + "/") {
    const rtnval2 = "pools-list";
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
  const rtnval = "none";
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
  register_resources_sidebar(handle.sidebar);
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
  build_pool_reservations_url,
  build_pool_resources_url,
  build_pool_url,
  build_reservation_url,
  build_resource_health_url,
  build_resource_pools_url,
  build_resource_url,
  build_resource_usage_url,
  classify_resources_route,
  define_resources_elements,
  ensure_resources_stylesheet,
  format_timestamp,
  health_tone,
  is_active_reservation,
  is_valid_uuid,
  mount_resources_view_if_active,
  parse_capability_tags,
  pool_id_from_path,
  has_next_page as pools_has_next_page,
  has_previous_page as pools_has_previous_page,
  project_id_from_search,
  register_resources_sidebar,
  reservation_tone,
  resource_id_from_path,
  resource_state_tone,
  short_id,
  tag_for_resources_route,
  usage_event_tone
};
//# sourceMappingURL=pyc-resources-bundle.js.map
