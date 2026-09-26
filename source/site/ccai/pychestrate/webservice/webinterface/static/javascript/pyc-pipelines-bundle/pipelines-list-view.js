const DEFAULT_PER_PAGE = 25;
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
function build_pipelines_query_url(state) {
  const params = new URLSearchParams();
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  const query = params.toString();
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(state.projectId) + "/pipelines?" + query;
  return rtnval;
}
function build_pipelines_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/pipelines";
  return rtnval;
}
function build_pipeline_detail_link(project_id, pipeline_id) {
  const rtnval = "/pipelines/" + encodeURIComponent(pipeline_id) + "?project_id=" + encodeURIComponent(project_id);
  return rtnval;
}
function build_pipelines_validate_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/pipelines:validate";
  return rtnval;
}
function build_pipelines_expand_matrix_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/pipelines:expand-matrix";
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
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = parsed.toLocaleString();
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
function parse_matrix_spec(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    throw new SyntaxError("matrix spec is required");
  }
  const parsed = JSON.parse(raw);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
    throw new SyntaxError("matrix spec must be a JSON object");
  }
  const rtnval = parsed;
  return rtnval;
}
function validate_message_for_status(status, valid) {
  if (status === 200 && valid === true) {
    const rtnval2 = "Pipeline definition is a valid DAG.";
    return rtnval2;
  }
  if (status === 200 && valid === false) {
    const rtnval2 = "Pipeline definition has DAG issues.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "Pipeline definition is not a valid DAG.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to validate pipelines.";
    return rtnval2;
  }
  const rtnval = "Failed to validate pipeline (HTTP " + String(status) + ").";
  return rtnval;
}
function list_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to pipelines.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This project was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the pipeline service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load pipelines (HTTP " + String(status) + "). Try refreshing.";
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
// ?project_id=<uuid or slug> preselects a project, so a project's page
// can link straight to its builds / runs / pipelines / test catalog
// (PRJ-06).
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
  const rtnval = match !== undefined ? match.project_id : projects[0].project_id;
  return rtnval;
}
class PycPipelinesList extends HTMLElement {
  _pager;
  _state;
  _pipelines;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _root;
  _table_region;
  _form_status;
  _matrix_region;
  _projects_notice_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false,
      errorStatus: 0
    };
    this._pipelines = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._root = null;
    this._table_region = null;
    this._pager = null;
    this._form_status = null;
    this._matrix_region = null;
    this._projects_notice_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + pagination state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
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
   * the upsert form, the matrix-expand panel, and the table.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-pipelines");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-pipelines__heading");
    heading.textContent = "Pipelines";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-pipelines__controls");
    const project_label = document.createElement("div");
    project_label.classList.add("pyc-pipelines__field");
    const project_select = document.createElement("mj-select");
    project_select.setAttribute("label", "Project");
    project_select.classList.add("pyc-pipelines__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-pipelines__input");
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
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-pipelines__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-pipelines__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    root.appendChild(this._build_upsert_form());
    root.appendChild(this._build_matrix_panel());
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-pipelines__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");

    pager.classList.add("pyc-pipelines__pager");

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
   * Build the create / upsert form -- the document textarea, the
   * commit-sha + filename inputs, and the Validate + Save
   * buttons.
   *
   * @returns The populated upsert-form section element.
   */
  _build_upsert_form() {
    const panel = document.createElement("section");
    panel.classList.add("pyc-pipelines__panel");
    panel.setAttribute("data-role", "upsert-panel");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pipelines__panel-heading");
    heading.textContent = "Create / Upsert Pipeline";
    panel.appendChild(heading);
    const form = document.createElement("form");
    form.classList.add("pyc-pipelines__form");
    form.setAttribute("data-role", "upsert-form");
    const fields = document.createElement("div");
    fields.classList.add("pyc-pipelines__field-row");
    const commit_label = document.createElement("div");
    commit_label.classList.add("pyc-pipelines__field");
    const commit_input = document.createElement("mj-text-field");
    commit_input.setAttribute("label", "Commit SHA");
    commit_input.classList.add("pyc-pipelines__input");
    commit_input.setAttribute("type", "text");
    commit_input.setAttribute("placeholder", "0000000000000000000000000000000000000000");
    commit_input.setAttribute("data-role", "upsert-commit-sha");
    commit_input.required = true;
    commit_label.appendChild(commit_input);
    fields.appendChild(commit_label);
    const filename_label = document.createElement("div");
    filename_label.classList.add("pyc-pipelines__field");
    const filename_input = document.createElement("mj-text-field");
    filename_input.setAttribute("label", "Filename");
    filename_input.classList.add("pyc-pipelines__input");
    filename_input.setAttribute("type", "text");
    filename_input.setAttribute("placeholder", "pipeline.yaml");
    filename_input.setAttribute("data-role", "upsert-filename");
    filename_input.required = true;
    filename_label.appendChild(filename_input);
    fields.appendChild(filename_label);
    form.appendChild(fields);
    const document_label = document.createElement("label");
    document_label.classList.add("pyc-pipelines__field", "pyc-pipelines__field--wide");
    document_label.textContent = "Pipeline document (YAML / JSON)";
    const document_area = document.createElement("mj-textarea");
    document_area.classList.add("pyc-pipelines__textarea");
    document_area.setAttribute("data-role", "upsert-document");
    document_area.setAttribute(
      "placeholder",
      "name: example\nschema_version: 1\nstages: []"
    );
    document_area.rows = 8;
    document_label.appendChild(document_area);
    form.appendChild(document_label);
    const actions = document.createElement("div");
    actions.classList.add("pyc-pipelines__form-actions");
    const validate_button = document.createElement("mj-button");
    validate_button.classList.add("pyc-pipelines__button");
    validate_button.setAttribute("type", "button");
    validate_button.setAttribute("data-role", "validate-submit");
    validate_button.textContent = "Validate";
    validate_button.addEventListener("click", () => {
      void this._submit_validate(commit_input, filename_input, document_area);
    });
    actions.appendChild(validate_button);
    const save_button = document.createElement("mj-button");
    save_button.classList.add("pyc-pipelines__primary");
    save_button.setAttribute("type", "submit");
    save_button.setAttribute("data-role", "save-submit");
    save_button.textContent = "Save";
    actions.appendChild(save_button);
    form.appendChild(actions);
    const dispatch_note = document.createElement("p");
    dispatch_note.classList.add("pyc-pipelines__dispatch-note");
    dispatch_note.setAttribute("data-role", "dispatch-note");
    dispatch_note.textContent = "Running pipelines from the service is not available yet \u2014 definitions can be created and validated.";
    form.appendChild(dispatch_note);
    const status = document.createElement("div");
    status.classList.add("pyc-pipelines__form-status");
    status.setAttribute("data-role", "form-status");
    form.appendChild(status);
    this._form_status = status;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_save(commit_input, filename_input, document_area);
    });
    panel.appendChild(form);
    return panel;
  }
  /**
   * Build the matrix-expand preview panel -- a matrix-spec JSON
   * textarea, a strategy-name input, an expand button, and the
   * result region.
   *
   * @returns The populated matrix-panel section element.
   */
  _build_matrix_panel() {
    const panel = document.createElement("section");
    panel.classList.add("pyc-pipelines__panel");
    panel.setAttribute("data-role", "matrix-panel");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pipelines__panel-heading");
    heading.textContent = "Matrix Expand Preview";
    panel.appendChild(heading);
    const matrix_label = document.createElement("label");
    matrix_label.classList.add("pyc-pipelines__field", "pyc-pipelines__field--wide");
    matrix_label.textContent = "Matrix spec (JSON)";
    const matrix_area = document.createElement("mj-textarea");
    matrix_area.classList.add("pyc-pipelines__textarea");
    matrix_area.setAttribute("data-role", "matrix-spec");
    matrix_area.setAttribute(
      "placeholder",
      '{"dimensions": {"os": ["linux", "windows"], "py": ["3.11", "3.12"]}}'
    );
    matrix_area.rows = 4;
    matrix_label.appendChild(matrix_area);
    panel.appendChild(matrix_label);
    const strategy_label = document.createElement("div");
    strategy_label.classList.add("pyc-pipelines__field");
    const strategy_input = document.createElement("mj-text-field");
    strategy_input.setAttribute("label", "Strategy");
    strategy_input.classList.add("pyc-pipelines__input");
    strategy_input.setAttribute("type", "text");
    strategy_input.setAttribute("placeholder", "cartesian");
    strategy_input.setAttribute("data-role", "matrix-strategy");
    strategy_label.appendChild(strategy_input);
    panel.appendChild(strategy_label);
    const expand_button = document.createElement("mj-button");
    expand_button.classList.add("pyc-pipelines__button");
    expand_button.setAttribute("type", "button");
    expand_button.setAttribute("data-role", "matrix-expand");
    expand_button.textContent = "Expand Matrix";
    expand_button.addEventListener("click", () => {
      void this._submit_matrix_expand(matrix_area, strategy_input);
    });
    panel.appendChild(expand_button);
    const result = document.createElement("div");
    result.classList.add("pyc-pipelines__matrix-result");
    result.setAttribute("data-role", "matrix-result");
    panel.appendChild(result);
    this._matrix_region = result;
    return panel;
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
        "pychestrate.ui.pipelines.projects_fetch_failed",
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
      region.classList.remove("pyc-pipelines__projects-notice--error");
      region.textContent = "No projects exist yet.";
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-pipelines__projects-notice--error");
      region.textContent = "You don't have permission to list projects.";
      return;
    }
    region.classList.add("pyc-pipelines__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-pipelines__button");
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
   * envelope.
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
   * Fetch the current page of pipelines and re-render the table.
   * Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._pipelines = [];
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._render_table_region();
    const url = build_pipelines_query_url(this._state);
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
        throw new Error("pipelines fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.list_fetch_failed",
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
    this._pipelines = page.items;
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
   * Re-render the table region from the current state +
   * pipelines.
   */
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.projectId.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-pipelines__status");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its pipelines.";
      region.replaceChildren(notice);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-pipelines__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading pipelines\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add("pyc-pipelines__status", "pyc-pipelines__status--error");
      error.setAttribute("data-role", "error-state");
      error.textContent = list_load_message_for_status(this._state.errorStatus);
      const children = [error];
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-pipelines__button");
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
    if (this._pipelines.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pipelines__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No pipelines cached yet";
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
   * Build the pipelines ``<mj-table>`` from the current
   * ``_pipelines`` list.
   */
  _build_table() {
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-pipelines__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-pipelines__row";
    table.columns = [
      {
        key: "pipeline_id",
        label: "Pipeline",
        width: "12rem",
        render: (pipeline) => {
          const link = document.createElement("a");
          link.classList.add("pyc-pipelines__pipeline-link");
          link.setAttribute(
            "href",
            build_pipeline_detail_link(pipeline.project_id, pipeline.pipeline_id)
          );
          link.textContent = short_id(pipeline.pipeline_id);
          link.title = pipeline.pipeline_id;
          return link;
        }
      },
      { key: "name", label: "Name", width: "16rem" },
      {
        key: "digest",
        label: "Digest",
        width: "12rem",
        sortable: false,
        render: (pipeline) => {
          const digest = document.createElement("span");
          digest.classList.add("pyc-pipelines__digest");
          digest.textContent = short_id(pipeline.pipeline_id);
          digest.title = pipeline.pipeline_id;
          return digest;
        }
      },
      {
        key: "stages",
        label: "Stages",
        width: "8rem",
        render: (pipeline) => {
          const stage_count = Array.isArray(pipeline.stages) ? pipeline.stages.length : 0;
          const rtnval = String(stage_count);
          return rtnval;
        }
      },
      {
        key: "cached_at",
        label: "Cached",
        width: "14rem",
        render: (pipeline) => format_timestamp(pipeline.cached_at)
      }
    ];
    table.rows = this._pipelines;
    return table;
  }
  /**
   * Update the pager controls -- enabled state + page indicator
   * label -- from the current state.
   */
  _render_pager() {

    if (this._pager === null || this._pager === undefined) {

      return;

    }

    this._pager.setAttribute("page", String(this._state.page));

    this._pager.setAttribute("page-size", String(this._state.perPage));

    this._pager.setAttribute("total-items", String(this._state.total));

    return;

  }
  /**
   * Build the request payload shared by the validate + save
   * actions. ``document`` is sent as the raw string -- the server
   * selects the YAML/JSON parser from ``filename``.
   *
   * @param commit_sha The commit-sha field value.
   * @param filename The filename field value.
   * @param document_text The raw pipeline document text.
   *
   * @returns A ``PipelineDefinitionCreateRequest`` payload.
   */
  _build_create_payload(commit_sha, filename, document_text) {
    const rtnval = {
      commit_sha,
      filename,
      document: document_text
    };
    return rtnval;
  }
  /**
   * Run the DAG-validate action against a supplied document.
   * Exposed so unit tests can invoke a validate without a real
   * click.
   *
   * @param commit_sha The commit-sha field value.
   * @param filename The filename field value.
   * @param document_text The raw pipeline document text.
   *
   * @returns The validate outcome.
   */
  async validatePipeline(commit_sha, filename, document_text) {
    const rtnval = await this._do_validate(commit_sha, filename, document_text);
    return rtnval;
  }
  async _submit_validate(commit_input, filename_input, document_area) {
    const document_text = document_area.value;
    if (document_text.trim().length === 0) {
      this._render_form_status("error", "Pipeline document is required.", []);
      return;
    }
    this._render_form_status("neutral", "Validating pipeline\u2026", []);
    const outcome = await this._do_validate(
      commit_input.value.trim(),
      filename_input.value.trim(),
      document_text
    );
    const tone = outcome.valid === true ? "ok" : "error";
    const detail = [];
    if (outcome.valid === true && outcome.topologicalOrder.length > 0) {
      detail.push("Topological order: " + outcome.topologicalOrder.join(" \u2192 "));
    }
    for (const issue of outcome.issues) {
      detail.push(issue);
    }
    this._render_form_status(tone, outcome.message, detail);
    return;
  }
  async _do_validate(commit_sha, filename, document_text) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        valid: false,
        stageCount: 0,
        topologicalOrder: [],
        issues: [],
        message: "Select a project before validating a pipeline."
      };
      return rtnval2;
    }
    const payload = this._build_create_payload(commit_sha, filename, document_text);
    let status = 0;
    let valid = false;
    let stage_count = 0;
    let topological_order = [];
    let issues = [];
    try {
      const url = build_pipelines_validate_url(this._state.projectId);
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
      const body = await response.json().catch(() => null);
      if (body !== null && typeof body === "object") {
        const record = body;
        if (typeof record.valid === "boolean") {
          valid = record.valid;
        }
        if (typeof record.stage_count === "number") {
          stage_count = record.stage_count;
        }
        if (Array.isArray(record.topological_order) === true) {
          topological_order = record.topological_order.filter((entry) => typeof entry === "string");
        }
        if (Array.isArray(record.issues) === true) {
          issues = record.issues.filter((entry) => typeof entry === "string");
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.validate_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        valid: false,
        stageCount: 0,
        topologicalOrder: [],
        issues: [],
        message: "Failed to reach the pipeline service."
      };
      return rtnval2;
    }
    const rtnval = {
      ok: status === 200,
      status,
      valid,
      stageCount: stage_count,
      topologicalOrder: topological_order,
      issues,
      message: validate_message_for_status(status, valid)
    };
    return rtnval;
  }
  /**
   * Run the upsert (save) action against a supplied document.
   * Exposed so unit tests can invoke a save without a real
   * form-submit event.
   *
   * @param commit_sha The commit-sha field value.
   * @param filename The filename field value.
   * @param document_text The raw pipeline document text.
   *
   * @returns The upsert outcome.
   */
  async savePipeline(commit_sha, filename, document_text) {
    const rtnval = await this._do_save(commit_sha, filename, document_text);
    return rtnval;
  }
  async _submit_save(commit_input, filename_input, document_area) {
    const commit_sha = commit_input.value.trim();
    const filename = filename_input.value.trim();
    const document_text = document_area.value;
    if (commit_sha.length === 0 || filename.length === 0) {
      this._render_form_status(
        "error",
        "Commit SHA and filename are required.",
        []
      );
      return;
    }
    if (document_text.trim().length === 0) {
      this._render_form_status("error", "Pipeline document is required.", []);
      return;
    }
    this._render_form_status("neutral", "Saving pipeline\u2026", []);
    const outcome = await this._do_save(commit_sha, filename, document_text);
    const tone = outcome.ok === true ? "ok" : "error";
    const detail = [];
    if (outcome.ok === true && outcome.pipelineId.length > 0) {
      detail.push("Pipeline id: " + outcome.pipelineId);
    }
    this._render_form_status(tone, outcome.message, detail);
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  async _do_save(commit_sha, filename, document_text) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        pipelineId: "",
        message: "Select a project before saving a pipeline."
      };
      return rtnval2;
    }
    const payload = this._build_create_payload(commit_sha, filename, document_text);
    let status = 0;
    let pipeline_id = "";
    try {
      const url = build_pipelines_collection_url(this._state.projectId);
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
        const body = await response.json().catch(() => null);
        if (body !== null && typeof body === "object") {
          const record = body;
          if (typeof record.pipeline_id === "string") {
            pipeline_id = record.pipeline_id;
          }
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.save_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        pipelineId: "",
        message: "Failed to reach the pipeline service."
      };
      return rtnval2;
    }
    const ok = status === 200 || status === 201;
    let message = "Pipeline saved.";
    if (ok === false) {
      if (status === 422) {
        message = "Pipeline document was rejected \u2014 check the DAG.";
      } else if (status === 403) {
        message = "You do not have permission to save pipelines.";
      } else {
        message = "Failed to save pipeline (HTTP " + String(status) + ").";
      }
    }
    const rtnval = {
      ok,
      status,
      pipelineId: pipeline_id,
      message
    };
    return rtnval;
  }
  /**
   * Render the upsert-form status block -- a tone-coded message
   * plus an optional detail list (topological order / issues).
   *
   * @param tone One of ``"ok"`` | ``"error"`` | ``"neutral"``.
   * @param message The headline status message.
   * @param detail Optional detail lines.
   */
  _render_form_status(tone, message, detail) {
    if (this._form_status === null) {
      return;
    }
    const status = this._form_status;
    status.setAttribute("data-tone", tone);
    const headline = document.createElement("p");
    headline.classList.add("pyc-pipelines__status-headline");
    headline.setAttribute("data-role", "form-status-message");
    headline.textContent = message;
    const children = [headline];
    if (detail.length > 0) {
      const list = document.createElement("ul");
      list.classList.add("pyc-pipelines__status-detail");
      list.setAttribute("data-role", "form-status-detail");
      for (const line of detail) {
        const item = document.createElement("li");
        item.textContent = line;
        list.appendChild(item);
      }
      children.push(list);
    }
    status.replaceChildren(...children);
    return;
  }
  /**
   * Run the matrix-expand action against a supplied matrix spec.
   * Exposed so unit tests can invoke an expand without a real
   * click.
   *
   * @param matrix The parsed matrix-spec object.
   * @param strategy_name Optional sharding strategy name.
   *
   * @returns The matrix-expand outcome.
   */
  async expandMatrix(matrix, strategy_name) {
    const rtnval = await this._do_matrix_expand(matrix, strategy_name);
    return rtnval;
  }
  async _submit_matrix_expand(matrix_area, strategy_input) {
    let matrix = {};
    try {
      matrix = parse_matrix_spec(matrix_area.value);
    } catch (reason) {
      this._render_matrix_result(
        "error",
        "Matrix spec must be a valid JSON object.",
        null
      );
      console.warn(
        "pychestrate.ui.pipelines.matrix_spec_invalid",
        { reason: String(reason) }
      );
      return;
    }
    this._render_matrix_result("neutral", "Expanding matrix\u2026", null);
    const outcome = await this._do_matrix_expand(
      matrix,
      strategy_input.value.trim()
    );
    const tone = outcome.ok === true ? "ok" : "error";
    this._render_matrix_result(tone, outcome.message, outcome);
    return;
  }
  async _do_matrix_expand(matrix, strategy_name) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        strategyName: "",
        shardCount: 0,
        shards: [],
        message: "Select a project before expanding a matrix."
      };
      return rtnval2;
    }
    const payload = { matrix };
    if (strategy_name.length > 0) {
      payload.strategy_name = strategy_name;
    }
    let status = 0;
    let strategy = "";
    let shard_count = 0;
    let shards = [];
    try {
      const url = build_pipelines_expand_matrix_url(this._state.projectId);
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
        const body = await response.json().catch(() => null);
        if (body !== null && typeof body === "object") {
          const record = body;
          if (typeof record.strategy_name === "string") {
            strategy = record.strategy_name;
          }
          if (typeof record.shard_count === "number") {
            shard_count = record.shard_count;
          }
          if (Array.isArray(record.shards) === true) {
            shards = record.shards.filter((entry) => entry !== null && typeof entry === "object").map((entry) => entry);
          }
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.matrix_expand_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        strategyName: "",
        shardCount: 0,
        shards: [],
        message: "Failed to reach the pipeline service."
      };
      return rtnval2;
    }
    const ok = status === 200;
    let message = "Matrix expanded into " + String(shard_count) + " shard(s).";
    if (ok === false) {
      if (status === 422) {
        message = "Matrix spec was rejected \u2014 check the dimensions.";
      } else if (status === 403) {
        message = "You do not have permission to expand matrices.";
      } else {
        message = "Failed to expand matrix (HTTP " + String(status) + ").";
      }
    }
    const rtnval = {
      ok,
      status,
      strategyName: strategy,
      shardCount: shard_count,
      shards,
      message
    };
    return rtnval;
  }
  /**
   * Render the matrix-expand result region -- a tone-coded
   * message plus, on success, the shard list.
   *
   * @param tone One of ``"ok"`` | ``"error"`` | ``"neutral"``.
   * @param message The headline message.
   * @param outcome The expand outcome (null while pending).
   */
  _render_matrix_result(tone, message, outcome) {
    if (this._matrix_region === null) {
      return;
    }
    const region = this._matrix_region;
    region.setAttribute("data-tone", tone);
    const headline = document.createElement("p");
    headline.classList.add("pyc-pipelines__status-headline");
    headline.setAttribute("data-role", "matrix-result-message");
    headline.textContent = message;
    const children = [headline];
    if (outcome !== null && outcome.ok === true && outcome.shards.length > 0) {
      const list = document.createElement("ul");
      list.classList.add("pyc-pipelines__shard-list");
      list.setAttribute("data-role", "matrix-shard-list");
      for (const shard of outcome.shards) {
        const item = document.createElement("li");
        item.classList.add("pyc-pipelines__shard");
        const id_chip = document.createElement("span");
        id_chip.classList.add("pyc-pipelines__shard-id");
        id_chip.textContent = shard.shard_id;
        item.appendChild(id_chip);
        const group_chip = document.createElement("span");
        group_chip.classList.add("pyc-pipelines__shard-group");
        group_chip.textContent = shard.parallel_group + " #" + String(shard.sequence_in_group);
        item.appendChild(group_chip);
        const dims = shard.dimension_values;
        if (dims !== void 0 && dims !== null) {
          const dim_text = document.createElement("span");
          dim_text.classList.add("pyc-pipelines__shard-dims");
          const pairs = [];
          for (const key of Object.keys(dims)) {
            pairs.push(key + "=" + String(dims[key]));
          }
          dim_text.textContent = pairs.join(", ");
          item.appendChild(dim_text);
        }
        list.appendChild(item);
      }
      children.push(list);
    }
    region.replaceChildren(...children);
    return;
  }
}
export {
  PycPipelinesList,
  announce_session_expired,
  build_pipeline_detail_link,
  build_pipelines_collection_url,
  build_pipelines_expand_matrix_url,
  build_pipelines_query_url,
  build_pipelines_validate_url,
  format_timestamp,
  has_next_page,
  has_previous_page,
  list_load_message_for_status,
  parse_matrix_spec,
  short_id,
  validate_message_for_status
};
