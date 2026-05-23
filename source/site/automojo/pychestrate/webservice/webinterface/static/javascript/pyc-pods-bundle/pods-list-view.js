const DEFAULT_PER_PAGE = 25;
const PROJECTS_API_PATH = "/api/v1/projects";
function build_pod_definitions_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/pod-definitions";
  return rtnval;
}
function build_pod_definition_url(project_id, pod_id) {
  const rtnval = build_pod_definitions_url(project_id) + "/" + encodeURIComponent(pod_id);
  return rtnval;
}
function short_id(pod_id) {
  if (typeof pod_id !== "string" || pod_id.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const dash_index = pod_id.indexOf("-");
  if (dash_index <= 0) {
    const rtnval2 = pod_id;
    return rtnval2;
  }
  const rtnval = pod_id.slice(0, dash_index);
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
function member_count(spec) {
  if (spec === null || spec === void 0) {
    const rtnval2 = 0;
    return rtnval2;
  }
  const members = spec["members"];
  if (Array.isArray(members) === true) {
    const rtnval2 = members.length;
    return rtnval2;
  }
  const rtnval = 0;
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
class PycPodsList extends HTMLElement {
  _state;
  _pods;
  _root;
  _table_region;
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
    this._pods = [];
    this._root = null;
    this._table_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * filter + pagination state without scraping the DOM.
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
   * Lifecycle hook -- render the static chrome. The pods list
   * cannot fetch without a project id, so a project filter
   * supplied via ``?project_id=`` seeds an immediate fetch;
   * otherwise the view shows a "pick a project" prompt.
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
  /**
   * Read a ``project_id`` from the current location's query
   * string so a deep link can seed the pods list.
   *
   * @returns The project id, or ``""`` when none is present.
   */
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
    root.classList.add("pyc-pods-list");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-pods-list__heading");
    heading.textContent = "Pods";
    root.appendChild(heading);
    const subtitle = document.createElement("p");
    subtitle.classList.add("pyc-pods-list__subtitle");
    subtitle.textContent = "Pod definitions are project-scoped. Enter a project id to list its pods.";
    root.appendChild(subtitle);
    const filters = document.createElement("div");
    filters.classList.add("pyc-pods-list__filters");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-pods-list__filter");
    project_label.textContent = "Project";
    const project_input = document.createElement("input");
    project_input.classList.add("pyc-pods-list__input");
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
        this._pods = [];
        this._state.total = 0;
        this._render_table_region();
      }
    });
    project_label.appendChild(project_input);
    filters.appendChild(project_label);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-pods-list__button");
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
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-pods-list__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("div");
    pager.classList.add("pyc-pods-list__pager");
    const prev_button = document.createElement("mj-button");
    prev_button.classList.add("pyc-pods-list__button");
    prev_button.setAttribute("type", "button");
    prev_button.setAttribute("data-role", "prev-page");
    prev_button.textContent = "Previous";
    prev_button.addEventListener("click", () => {
      if (has_previous_page(this._state) === true) {
        this._state.page = this._state.page - 1;
        this._render_table_region();
      }
    });
    pager.appendChild(prev_button);
    const page_indicator = document.createElement("span");
    page_indicator.classList.add("pyc-pods-list__page-indicator");
    page_indicator.setAttribute("data-role", "page-indicator");
    pager.appendChild(page_indicator);
    const next_button = document.createElement("mj-button");
    next_button.classList.add("pyc-pods-list__button");
    next_button.setAttribute("type", "button");
    next_button.setAttribute("data-role", "next-page");
    next_button.textContent = "Next";
    next_button.addEventListener("click", () => {
      if (has_next_page(this._state) === true) {
        this._state.page = this._state.page + 1;
        this._render_table_region();
      }
    });
    pager.appendChild(next_button);
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the project's pod definitions and re-render the table
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
    const url = build_pod_definitions_url(this._state.projectFilter);
    let pods = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "pods fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      pods = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pods.list_fetch_failed",
        { reason: String(reason) }
      );
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    if (pods === null || Array.isArray(pods) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    this._pods = pods;
    this._state.total = pods.length;
    this._state.page = 1;
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
    return;
  }
  _page_slice() {
    const start = (this._state.page - 1) * this._state.perPage;
    const end = start + this._state.perPage;
    const rtnval = this._pods.slice(start, end);
    return rtnval;
  }
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.needsProject === true) {
      const prompt = document.createElement("p");
      prompt.classList.add("pyc-pods-list__status");
      prompt.setAttribute("data-role", "needs-project");
      prompt.textContent = "Enter a project id above to list its pods.";
      region.replaceChildren(prompt);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-pods-list__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading pods\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-pods-list__status",
        "pyc-pods-list__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load pods. Try refreshing.";
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._pods.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pods-list__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No pods defined in this project";
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
    table.classList.add("pyc-pods-list__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = [
      "Pod",
      "Name",
      "Version",
      "Members",
      "Created"
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
    for (const pod of this._page_slice()) {
      const row = document.createElement("tr");
      row.classList.add("pyc-pods-list__row");
      const id_cell = document.createElement("td");
      const link = document.createElement("a");
      link.classList.add("pyc-pods-list__pod-link");
      const href = "/pods/" + pod.pod_id + "?project_id=" + encodeURIComponent(pod.project_id);
      link.setAttribute("href", href);
      link.textContent = short_id(pod.pod_id);
      link.title = pod.pod_id;
      id_cell.appendChild(link);
      row.appendChild(id_cell);
      const name_cell = document.createElement("td");
      name_cell.textContent = pod.pod_name !== null && pod.pod_name.length > 0 ? pod.pod_name : "\u2014";
      row.appendChild(name_cell);
      const version_cell = document.createElement("td");
      version_cell.textContent = "v" + String(pod.current_version);
      row.appendChild(version_cell);
      const members_cell = document.createElement("td");
      members_cell.textContent = String(member_count(pod.spec));
      row.appendChild(members_cell);
      const created_cell = document.createElement("td");
      created_cell.textContent = format_timestamp(pod.created_at);
      row.appendChild(created_cell);
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
    if (prev instanceof HTMLElement) {
      prev.toggleAttribute("disabled", has_previous_page(this._state) === false);
    }
    if (next instanceof HTMLElement) {
      next.toggleAttribute("disabled", has_next_page(this._state) === false);
    }
    if (indicator instanceof HTMLElement) {
      const label = "Page " + String(this._state.page) + " \xB7 " + String(this._state.total) + " total";
      indicator.textContent = label;
    }
    return;
  }
}
export {
  PycPodsList,
  build_pod_definition_url,
  build_pod_definitions_url,
  format_timestamp,
  has_next_page,
  has_previous_page,
  member_count,
  short_id
};
