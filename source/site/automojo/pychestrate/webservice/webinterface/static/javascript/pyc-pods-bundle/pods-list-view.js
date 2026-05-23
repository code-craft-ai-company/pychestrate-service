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
  _pager;
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
    this._pager = null;
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
    const project_input = document.createElement("mj-text-field");
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
    const pager = document.createElement("mj-pagination");

    pager.classList.add("pyc-pods-list__pager");

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
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-pods-list__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-pods-list__row";
    table.rowAttrs = (pod) => ({ "data-pod-id": pod.pod_id });
    table.columns = [
      {
        key: "pod_id",
        label: "Pod",
        width: "12rem",
        render: (pod) => {
          const link = document.createElement("a");
          link.classList.add("pyc-pods-list__pod-link");
          const href = "/pods/" + pod.pod_id + "?project_id=" + encodeURIComponent(pod.project_id);
          link.setAttribute("href", href);
          link.textContent = short_id(pod.pod_id);
          link.title = pod.pod_id;
          return link;
        }
      },
      {
        key: "pod_name",
        label: "Name",
        width: "16rem",
        render: (pod) => pod.pod_name !== null && pod.pod_name.length > 0 ? pod.pod_name : "\u2014"
      },
      {
        key: "current_version",
        label: "Version",
        width: "8rem",
        render: (pod) => "v" + String(pod.current_version)
      },
      {
        key: "members",
        label: "Members",
        width: "8rem",
        sortable: false,
        render: (pod) => String(member_count(pod.spec))
      },
      {
        key: "created_at",
        label: "Created",
        width: "14rem",
        render: (pod) => format_timestamp(pod.created_at)
      }
    ];
    table.rows = this._page_slice();
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
  PycPodsList,
  build_pod_definition_url,
  build_pod_definitions_url,
  format_timestamp,
  has_next_page,
  has_previous_page,
  member_count,
  short_id
};
