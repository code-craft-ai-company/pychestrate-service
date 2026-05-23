const DEFAULT_PER_PAGE = 50;
const RESOURCE_POOLS_API_PATH = "/api/v1/resource-pools";
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
class PycResourcePools extends HTMLElement {
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
    this._pager = null;
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
    filters.appendChild(project_label);
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
    root.appendChild(this._build_create_form());
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
    const name_input = document.createElement("mj-text-field");
    name_input.classList.add("pyc-resources__input");
    name_input.setAttribute("type", "text");
    name_input.setAttribute("placeholder", "pool name");
    name_input.setAttribute("data-role", "create-name");
    name_label.appendChild(name_input);
    form.appendChild(name_label);
    const desc_label = document.createElement("label");
    desc_label.classList.add("pyc-resources__filter");
    desc_label.textContent = "Description";
    const desc_input = document.createElement("mj-text-field");
    desc_input.classList.add("pyc-resources__input");
    desc_input.setAttribute("type", "text");
    desc_input.setAttribute("placeholder", "optional");
    desc_input.setAttribute("data-role", "create-description");
    desc_label.appendChild(desc_input);
    form.appendChild(desc_label);
    const tags_label = document.createElement("label");
    tags_label.classList.add("pyc-resources__filter");
    tags_label.textContent = "Capability tags";
    const tags_input = document.createElement("mj-text-field");
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

    if (this._pager === null || this._pager === undefined) {

      return;

    }

    this._pager.setAttribute("page", String(this._state.page));

    this._pager.setAttribute("page-size", String(this._state.perPage));

    this._pager.setAttribute("total-items", String(this._state.total));

    return;

  }
}
export {
  PycResourcePools,
  build_resource_pools_url,
  format_timestamp,
  has_next_page,
  has_previous_page,
  parse_capability_tags,
  short_id
};
