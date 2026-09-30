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
function message_with_detail(prefix, detail, generic) {
  if (typeof detail === "string" && detail.length > 0) {
    return prefix + ": " + detail;
  }
  return generic;
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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-pipelines-bundle/pipelines-list-view.js
var DEFAULT_PER_PAGE = 25;
var PROJECTS_API_PATH = "/api/v1/projects";
var PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
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
var PycPipelinesList = class extends HTMLElement {
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
      page: page_from_query(),
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
    heading.textContent = "Define a pipeline";
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
    const document_label = document.createElement("div");
    document_label.classList.add("pyc-pipelines__field", "pyc-pipelines__field--wide");
    const document_area = document.createElement("mj-textarea");
    document_area.setAttribute("label", "Pipeline document (YAML / JSON)");
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
    save_button.setAttribute("variant", "primary");
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
    const matrix_label = document.createElement("div");
    matrix_label.classList.add("pyc-pipelines__field", "pyc-pipelines__field--wide");
    const matrix_area = document.createElement("mj-textarea");
    matrix_area.setAttribute("label", "Matrix spec (JSON)");
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
    mirror_to_query({
      project_id: this._state.projectId,
      page: this._state.page > 1 ? String(this._state.page) : ""
    });
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
      empty.textContent = "No pipelines defined in this project yet. Paste a pipeline document into Define a pipeline above and choose Save.";
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
        // The name leads; the short id follows for anyone who must quote it (ORC-37).
        key: "name",
        label: "Pipeline",
        width: "18rem",
        render: (pipeline) => {
          const cell = document.createElement("span");
          const link = document.createElement("a");
          link.classList.add("pyc-pipelines__pipeline-link");
          link.setAttribute(
            "href",
            build_pipeline_detail_link(pipeline.project_id, pipeline.pipeline_id)
          );
          const name = typeof pipeline.name === "string" ? pipeline.name.trim() : "";
          link.textContent = name.length > 0 ? name : short_id(pipeline.pipeline_id);
          link.title = pipeline.pipeline_id;
          cell.appendChild(link);
          const id = document.createElement("span");
          id.classList.add("pyc-pipelines__pipeline-id");
          id.textContent = " " + short_id(pipeline.pipeline_id);
          cell.appendChild(id);
          return cell;
        }
      },
      {
        // Where the definition came from. The column called "Digest" showed the
        // pipeline's id again; the id is the digest.
        key: "filename",
        label: "Source",
        width: "20rem",
        sortable: false,
        render: (pipeline) => {
          const file = typeof pipeline.filename === "string" ? pipeline.filename : "";
          const commit = typeof pipeline.commit_sha === "string" ? pipeline.commit_sha.slice(0, 7) : "";
          if (file.length > 0 && commit.length > 0) {
            return file + " @ " + commit;
          }
          return file.length > 0 ? file : commit.length > 0 ? commit : "\u2014";
        }
      },
      {
        key: "stages",
        label: "Stages",
        width: "7rem",
        render: (pipeline) => {
          const stage_count = Array.isArray(pipeline.stages) ? pipeline.stages.length : 0;
          const rtnval = String(stage_count);
          return rtnval;
        }
      },
      {
        key: "cached_at",
        label: "Saved",
        width: "12rem",
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
    if (this._pager === null || this._pager === void 0) {
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
    let detail = "";
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
      if (response.ok === false) {
        detail = problem_detail_of_body(body);
      }
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
      message: message_with_detail("Pipeline not validated", detail, validate_message_for_status(status, valid))
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
};

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

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-pipelines-bundle/pipeline-detail-view.js
var NODE_WIDTH = 140;
var NODE_HEIGHT = 44;
var COLUMN_GAP = 80;
var ROW_GAP = 24;
var CANVAS_PADDING = 20;
var PROJECTS_API_PATH2 = "/api/v1/projects";
function pipeline_delete_message_for_status(status, name) {
  if (status === 204 || status === 200) {
    const rtnval2 = "Pipeline \u201C" + name + "\u201D deleted.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This pipeline no longer exists.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to delete pipelines.";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to delete.";
    return rtnval2;
  }
  const rtnval = "Failed to delete the pipeline (HTTP " + String(status) + ").";
  return rtnval;
}
function pipeline_runs_url(project_id) {
  const rtnval = PROJECTS_API_PATH2 + "/" + encodeURIComponent(project_id) + "/pipeline-runs?per_page=100";
  return rtnval;
}
function run_state_tone(state) {
  if (state === "completed" || state === "succeeded") {
    return "ok";
  }
  if (state === "failed" || state === "rejected") {
    return "error";
  }
  if (state === "cancelled" || state === "skipped") {
    return "warn";
  }
  return "neutral";
}
function words(text) {
  const spaced = typeof text === "string" ? text.replace(/_/g, " ").trim() : "";
  return spaced.length > 0 ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : "";
}
function stage_progress_text(run) {
  const stages = Array.isArray(run.stages) ? run.stages : [];
  if (stages.length === 0) {
    return "";
  }
  const done = stages.filter((stage) => stage.state === "completed" || stage.state === "succeeded").length;
  return String(done) + " of " + String(stages.length) + (stages.length === 1 ? " stage" : " stages") + " completed";
}
function sort_runs_newest_first(runs) {
  return runs.slice().sort((left, right) => {
    const a = left.started_at ? new Date(left.started_at).getTime() : Infinity;
    const b = right.started_at ? new Date(right.started_at).getTime() : Infinity;
    return b - a;
  });
}
function pipeline_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/pipelines/";
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
function pipeline_detail_url(project_id, pipeline_id) {
  const rtnval = PROJECTS_API_PATH2 + "/" + encodeURIComponent(project_id) + "/pipelines/" + encodeURIComponent(pipeline_id);
  return rtnval;
}
function detail_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to pipelines.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This pipeline was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the pipeline service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load this pipeline (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function compute_dag_columns(stages) {
  const known_ids = /* @__PURE__ */ new Set();
  for (const stage of stages) {
    known_ids.add(stage.stage_id);
  }
  const depth_by_id = /* @__PURE__ */ new Map();
  let progressed = true;
  while (progressed === true) {
    progressed = false;
    for (const stage of stages) {
      if (depth_by_id.has(stage.stage_id) === true) {
        continue;
      }
      const needs = stage.needs;
      let deepest = -1;
      let resolvable = true;
      if (needs !== void 0 && needs !== null) {
        for (const dep_id of needs) {
          if (known_ids.has(dep_id) === false) {
            continue;
          }
          const dep_depth = depth_by_id.get(dep_id);
          if (dep_depth === void 0) {
            resolvable = false;
            break;
          }
          if (dep_depth > deepest) {
            deepest = dep_depth;
          }
        }
      }
      if (resolvable === false) {
        continue;
      }
      depth_by_id.set(stage.stage_id, deepest + 1);
      progressed = true;
    }
  }
  const is_dag = depth_by_id.size === stages.length;
  const row_cursor = /* @__PURE__ */ new Map();
  const assignments = [];
  for (const stage of stages) {
    const column = depth_by_id.get(stage.stage_id);
    if (column === void 0) {
      continue;
    }
    const cursor = row_cursor.get(column);
    const row = cursor === void 0 ? 0 : cursor;
    row_cursor.set(column, row + 1);
    assignments.push({
      stageId: stage.stage_id,
      column,
      row
    });
  }
  const rtnval = {
    assignments,
    isDag: is_dag
  };
  return rtnval;
}
function compute_dag_layout(stages) {
  const columns = compute_dag_columns(stages);
  const node_by_id = /* @__PURE__ */ new Map();
  const nodes = [];
  let max_x = 0;
  let max_y = 0;
  for (const entry of columns.assignments) {
    const x = CANVAS_PADDING + entry.column * (NODE_WIDTH + COLUMN_GAP);
    const y = CANVAS_PADDING + entry.row * (NODE_HEIGHT + ROW_GAP);
    const node = {
      stageId: entry.stageId,
      x,
      y,
      width: NODE_WIDTH,
      height: NODE_HEIGHT
    };
    node_by_id.set(entry.stageId, node);
    nodes.push(node);
    if (x + NODE_WIDTH > max_x) {
      max_x = x + NODE_WIDTH;
    }
    if (y + NODE_HEIGHT > max_y) {
      max_y = y + NODE_HEIGHT;
    }
  }
  const edges = [];
  for (const stage of stages) {
    const dependent = node_by_id.get(stage.stage_id);
    if (dependent === void 0) {
      continue;
    }
    const needs = stage.needs;
    if (needs === void 0 || needs === null) {
      continue;
    }
    for (const dep_id of needs) {
      const dependency_node = node_by_id.get(dep_id);
      if (dependency_node === void 0) {
        continue;
      }
      const edge = {
        fromStageId: stage.stage_id,
        toStageId: dep_id,
        x1: dependency_node.x + dependency_node.width,
        y1: dependency_node.y + dependency_node.height / 2,
        x2: dependent.x,
        y2: dependent.y + dependent.height / 2
      };
      edges.push(edge);
    }
  }
  const rtnval = {
    nodes,
    edges,
    width: max_x + CANVAS_PADDING,
    height: max_y + CANVAS_PADDING,
    isDag: columns.isDag
  };
  return rtnval;
}
var SVG_NS = "http://www.w3.org/2000/svg";
var PycPipelineDetail = class extends HTMLElement {
  _pipeline_id;
  _project_id;
  _pipeline;
  _loading;
  _errored;
  _error_kind;
  _error_status;
  _is_dag;
  _root;
  _deleted;
  _delete_notice;
  _delete_pending;
  _runs;
  constructor() {
    super();
    this._pipeline_id = "";
    this._project_id = "";
    this._pipeline = null;
    this._loading = false;
    this._errored = false;
    this._error_kind = "";
    this._error_status = 0;
    this._is_dag = true;
    this._root = null;
    this._deleted = false;
    this._delete_notice = "";
    this._delete_pending = false;
    this._runs = { status: "idle", items: [], error_status: 0 };
  }
  /**
   * Observed attributes -- ``pipeline-id`` and ``project-id`` may
   * be supplied explicitly by a host; otherwise they are read
   * from the URL on mount.
   */
  static get observedAttributes() {
    const rtnval = ["pipeline-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      pipelineId: this._pipeline_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored,
      errorKind: this._error_kind,
      errorStatus: this._error_status,
      isDag: this._is_dag
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the pipeline + project ids, render
   * the chrome, and fetch the snapshot. The project id rides on
   * the detail link's ``?project_id=`` query parameter because
   * pipelines are only addressable through the project-scoped
   * API.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("pipeline-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._pipeline_id = attr_id;
    } else {
      this._pipeline_id = pipeline_id_from_path(window.location.pathname);
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
   * Fetch the pipeline snapshot and render it. Exposed so unit
   * tests can await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (this._pipeline_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._error_kind = "invalid-id";
      this._render_body();
      return;
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
    const pipeline = await this._fetch_pipeline();
    if (pipeline === null) {
      this._loading = false;
      this._errored = true;
      this._error_kind = "http";
      this._render_body();
      return;
    }
    this._pipeline = pipeline;
    this._project_id = pipeline.project_id;
    this._loading = false;
    this._errored = false;
    this._render_body();
    void this._load_runs();
    return;
  }
  // The project's pipeline runs, kept to this pipeline's. A person without
  // access to runs still sees the pipeline, with a note.
  async _load_runs() {
    this._runs = { status: "loading", items: [], error_status: 0 };
    this._render_body();
    try {
      const response = await fetch(pipeline_runs_url(this._project_id), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const items = body !== null && Array.isArray(body.items) ? body.items : [];
        this._runs = { status: "ok", items: sort_runs_newest_first(items.filter((run) => run.pipeline_id === this._pipeline_id)), error_status: 0 };
      } else {
        this._runs = { status: "error", items: [], error_status: response.status };
        if (response.status === 401) {
          announce_session_expired();
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.runs_fetch_failed",
        { reason: String(reason) }
      );
      this._runs = { status: "error", items: [], error_status: 0 };
    }
    this._render_body();
    return;
  }
  /**
   * Fetch the pipeline-definition snapshot from the project-
   * scoped endpoint -- pipelines have no project-agnostic
   * resolver, so the project id must already be known (threaded
   * through the detail link's ``?project_id=`` query parameter).
   *
   * @returns The ``PipelineDefinition``, or ``null`` on failure.
   */
  async _fetch_pipeline() {
    const url = pipeline_detail_url(this._project_id, this._pipeline_id);
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
        throw new Error(
          "pipeline fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      this._error_status = 0;
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.detail_fetch_failed",
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  /**
   * Build the persistent chrome -- heading, back link, and the
   * body region the data render replaces.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-pipeline-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Pipeline detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-pipeline-detail__heading");
    heading.textContent = "Pipeline detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-pipeline-detail__back-link");
    back.setAttribute("href", "/pipelines");
    back.setAttribute("data-role", "back-link");
    keep_list_state_on_back(back, "/pipelines");
    back.textContent = "Back to pipelines";
    root.appendChild(back);
    const body = document.createElement("div");
    body.classList.add("pyc-pipeline-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Re-render the body region from the current pipeline
   * snapshot, driving the loading / error / loaded states.
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
      loading.classList.add("pyc-pipeline-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading pipeline\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._pipeline === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-pipeline-detail__status",
        "pyc-pipeline-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      if (this._error_kind === "missing-project") {
        error.textContent = "This link is missing its project context \u2014 open the pipeline from the Pipelines list.";
      } else if (this._error_kind === "invalid-id") {
        error.textContent = "This pipeline link is not valid \u2014 open the pipeline from the Pipelines list.";
      } else {
        error.textContent = detail_load_message_for_status(this._error_status);
      }
      const children = [error];
      if (this._error_kind === "http") {
        if (this._error_status === 0 || this._error_status >= 500) {
          const retry = document.createElement("mj-button");
          retry.classList.add("pyc-pipeline-detail__retry");
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
    if (this._deleted === true) {
      const gone = document.createElement("p");
      gone.classList.add("pyc-pipeline-detail__deleted");
      gone.setAttribute("data-role", "deleted-state");
      const text = document.createElement("span");
      text.textContent = this._delete_notice + " ";
      gone.appendChild(text);
      const list_link = document.createElement("a");
      list_link.classList.add("pyc-pipeline-detail__back-link");
      list_link.setAttribute("href", "/pipelines?project_id=" + encodeURIComponent(this._project_id));
      list_link.textContent = "Back to pipelines";
      gone.appendChild(list_link);
      body.replaceChildren(gone);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._pipeline));
    fragment.appendChild(this._build_dag_section(this._pipeline.stages));
    fragment.appendChild(this._build_stage_list(this._pipeline.stages));
    fragment.appendChild(this._build_runs_section());
    body.replaceChildren(fragment);
    return;
  }
  /**
   * Build the pipeline summary block -- identity, name, schema
   * version, commit, filename, cached timestamp.
   *
   * @param pipeline The current pipeline snapshot.
   *
   * @returns A populated summary section element.
   */
  _build_summary(pipeline) {
    const section = document.createElement("section");
    section.classList.add("pyc-pipeline-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pipeline summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-pipeline-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-pipeline-detail__pipeline-id");
    id_value.setAttribute("data-role", "pipeline-id");
    id_value.textContent = short_id(pipeline.pipeline_id);
    id_value.title = pipeline.pipeline_id;
    id_row.appendChild(id_value);
    const name_value = document.createElement("span");
    name_value.classList.add("pyc-pipeline-detail__name");
    name_value.setAttribute("data-role", "pipeline-name");
    name_value.textContent = pipeline.name;
    set_entity_title(String(pipeline.name ?? "") || "Pipeline " + short_id(pipeline.pipeline_id));
    id_row.appendChild(name_value);
    const delete_button = document.createElement("mj-button");
    delete_button.classList.add("pyc-pipeline-detail__delete");
    delete_button.setAttribute("type", "button");
    delete_button.setAttribute("data-role", "delete-pipeline");
    hide_unless_may(delete_button, "system:pipelines.write");
    delete_button.textContent = "Delete";
    if (this._delete_pending === true) {
      delete_button.toggleAttribute("disabled", true);
    }
    delete_button.addEventListener("click", () => {
      void this._on_delete();
    });
    id_row.appendChild(delete_button);
    section.appendChild(id_row);
    if (this._delete_notice.length > 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-pipeline-detail__notice");
      notice.setAttribute("data-role", "delete-notice");
      notice.setAttribute("role", "alert");
      notice.textContent = this._delete_notice;
      section.appendChild(notice);
    }
    const grid = document.createElement("dl");
    grid.classList.add("pyc-pipeline-detail__grid");
    this._append_field(grid, "Project", pipeline.project_id);
    this._append_field(grid, "Schema version", String(pipeline.schema_version));
    const stage_count = Array.isArray(pipeline.stages) ? pipeline.stages.length : 0;
    this._append_field(grid, "Stages", String(stage_count));
    const commit = pipeline.commit_sha;
    if (commit !== void 0 && commit !== null && commit.length > 0) {
      this._append_field(grid, "Commit SHA", commit);
    }
    const filename = pipeline.filename;
    if (filename !== void 0 && filename !== null && filename.length > 0) {
      this._append_field(grid, "Filename", filename);
    }
    this._append_field(grid, "Cached", format_timestamp(pipeline.cached_at));
    section.appendChild(grid);
    return section;
  }
  /**
   * Delete this pipeline definition after asking (ORC-26). The dialog says
   * what goes and that it cannot be undone; on success the page says so and
   * links back to the list.
   */
  async _on_delete() {
    if (this._pipeline === null || this._delete_pending === true) {
      return;
    }
    const name = typeof this._pipeline.name === "string" && this._pipeline.name.trim().length > 0 ? this._pipeline.name.trim() : short_id(this._pipeline.pipeline_id);
    const confirmed = await confirm_action(
      this,
      "Delete the pipeline \u201C" + name + "\u201D?\nThe saved definition is removed from this project. This cannot be undone.",
      "Delete pipeline"
    );
    if (confirmed !== true) {
      return;
    }
    this._delete_pending = true;
    this._delete_notice = "";
    this._render_body();
    const outcome = await this.deletePipeline(name);
    this._delete_pending = false;
    this._delete_notice = outcome.message;
    this._deleted = outcome.ok === true || outcome.status === 404;
    this._render_body();
    return;
  }
  /**
   * ``DELETE`` this pipeline definition. Exposed so unit tests can drive it
   * without a dialog.
   *
   * @param name The name to use in the outcome message.
   *
   * @returns ``{ok, status, message}``.
   */
  async deletePipeline(name) {
    let status = 0;
    try {
      const response = await fetch(pipeline_detail_url(this._project_id, this._pipeline_id), {
        method: "DELETE",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      if (status === 401) {
        announce_session_expired();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.delete_failed",
        { reason: String(reason) }
      );
      return { ok: false, status: 0, message: "Couldn't reach the server, so the pipeline was not deleted." };
    }
    return { ok: status === 204 || status === 200, status, message: pipeline_delete_message_for_status(status, name) };
  }
  /**
   * Append one labelled field to a definition-list grid.
   *
   * @param grid The ``<dl>`` to append into.
   * @param label The field's display label.
   * @param value The field's display value.
   */
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-pipeline-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    def.textContent = value;
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  /**
   * Build the DAG-visualization section -- the inline-SVG node-
   * and-edge layout, or the adjacency-list fallback when the
   * stages do not form a clean DAG.
   *
   * @param stages The pipeline's stages.
   *
   * @returns A populated DAG section element.
   */
  _build_dag_section(stages) {
    const section = document.createElement("section");
    section.classList.add("pyc-pipeline-detail__dag");
    section.setAttribute("data-role", "dag-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pipeline DAG");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pipeline-detail__section-heading");
    heading.textContent = "Stage DAG";
    section.appendChild(heading);
    if (stages.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pipeline-detail__status");
      empty.setAttribute("data-role", "dag-empty");
      empty.textContent = "This pipeline has no stages.";
      section.appendChild(empty);
      this._is_dag = true;
      return section;
    }
    const layout = compute_dag_layout(stages);
    this._is_dag = layout.isDag;
    if (layout.isDag === false) {
      const notice = document.createElement("p");
      notice.classList.add(
        "pyc-pipeline-detail__status",
        "pyc-pipeline-detail__status--error"
      );
      notice.setAttribute("data-role", "dag-cycle-notice");
      notice.textContent = "Stages do not form a clean DAG \u2014 showing dependency list.";
      section.appendChild(notice);
      section.appendChild(this._build_adjacency_list(stages));
      return section;
    }
    section.appendChild(this._build_dag_svg(layout));
    return section;
  }
  /**
   * Build the inline-SVG node-and-edge rendering of the DAG.
   *
   * @param layout The pre-computed pixel layout.
   *
   * @returns An ``<svg>`` element wrapped in a scroll container.
   */
  _build_dag_svg(layout) {
    const wrapper = document.createElement("div");
    wrapper.classList.add("pyc-pipeline-detail__dag-canvas");
    wrapper.setAttribute("data-role", "dag-canvas");
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute(
      "viewBox",
      "0 0 " + String(layout.width) + " " + String(layout.height)
    );
    svg.setAttribute("width", String(layout.width));
    svg.setAttribute("height", String(layout.height));
    svg.classList.add("pyc-pipeline-detail__dag-svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Pipeline stage DAG");
    for (const edge of layout.edges) {
      const line = document.createElementNS(SVG_NS, "line");
      line.setAttribute("x1", String(edge.x1));
      line.setAttribute("y1", String(edge.y1));
      line.setAttribute("x2", String(edge.x2));
      line.setAttribute("y2", String(edge.y2));
      line.setAttribute("class", "pyc-pipeline-detail__dag-edge");
      line.setAttribute("data-role", "dag-edge");
      svg.appendChild(line);
    }
    for (const node of layout.nodes) {
      const group = document.createElementNS(SVG_NS, "g");
      group.setAttribute("data-role", "dag-node");
      group.setAttribute("data-stage-id", node.stageId);
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("x", String(node.x));
      rect.setAttribute("y", String(node.y));
      rect.setAttribute("width", String(node.width));
      rect.setAttribute("height", String(node.height));
      rect.setAttribute("rx", "6");
      rect.setAttribute("class", "pyc-pipeline-detail__dag-box");
      group.appendChild(rect);
      const text = document.createElementNS(SVG_NS, "text");
      text.setAttribute("x", String(node.x + node.width / 2));
      text.setAttribute("y", String(node.y + node.height / 2));
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("dominant-baseline", "middle");
      text.setAttribute("class", "pyc-pipeline-detail__dag-label");
      text.textContent = node.stageId;
      group.appendChild(text);
      svg.appendChild(group);
    }
    wrapper.appendChild(svg);
    return wrapper;
  }
  /**
   * Build the adjacency-list fallback rendering -- one row per
   * stage naming the stages it depends on.
   *
   * @param stages The pipeline's stages.
   *
   * @returns An adjacency-list ``<ul>`` element.
   */
  _build_adjacency_list(stages) {
    const list = document.createElement("ul");
    list.classList.add("pyc-pipeline-detail__adjacency");
    list.setAttribute("data-role", "dag-adjacency");
    for (const stage of stages) {
      const item = document.createElement("li");
      item.classList.add("pyc-pipeline-detail__adjacency-row");
      const name = document.createElement("strong");
      name.textContent = stage.stage_id;
      item.appendChild(name);
      const needs = stage.needs;
      const detail = document.createElement("span");
      if (needs !== void 0 && needs !== null && needs.length > 0) {
        detail.textContent = " \u2192 depends on: " + needs.join(", ");
      } else {
        detail.textContent = " \u2192 no dependencies";
      }
      item.appendChild(detail);
      list.appendChild(item);
    }
    return list;
  }
  /**
   * Build the stage-list section -- one card per stage naming
   * its when-clause, dependency list, and step ids.
   *
   * @param stages The pipeline's stages.
   *
   * @returns A populated stage-list section element.
   */
  _build_runs_section() {
    const section = document.createElement("section");
    section.classList.add("pyc-pipeline-detail__runs");
    section.setAttribute("data-role", "runs-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pipeline runs");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pipeline-detail__section-heading");
    const state = this._runs;
    heading.textContent = state.status === "ok" && state.items.length > 0 ? "Runs (" + String(state.items.length) + ")" : "Runs";
    section.appendChild(heading);
    const note = (text, role, error) => {
      const p = document.createElement("p");
      p.classList.add("pyc-pipeline-detail__status");
      if (error === true) {
        p.classList.add("pyc-pipeline-detail__status--error");
      }
      p.setAttribute("data-role", role);
      p.textContent = text;
      section.appendChild(p);
    };
    if (state.status === "idle" || state.status === "loading") {
      note("Loading runs\u2026", "runs-loading", false);
      return section;
    }
    if (state.status === "error") {
      note(state.error_status === 403 ? "You don't have access to pipeline runs." : "Couldn't load this pipeline's runs.", "runs-error", state.error_status !== 403);
      return section;
    }
    if (state.items.length === 0) {
      note("This pipeline has not been run yet.", "runs-empty", false);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-pipeline-detail__run-list");
    list.setAttribute("data-role", "runs-list");
    for (const run of state.items) {
      list.appendChild(this._build_run_row(run));
    }
    section.appendChild(list);
    return section;
  }
  _build_run_row(run) {
    const item = document.createElement("li");
    item.classList.add("pyc-pipeline-detail__run");
    item.setAttribute("data-role", "run-row");
    item.setAttribute("data-state", String(run.state));
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.classList.add("pyc-pipeline-detail__run-summary");
    const chip = document.createElement("span");
    chip.classList.add("pyc-pipeline-detail__run-chip");
    chip.setAttribute("data-tone", run_state_tone(run.state));
    chip.textContent = words(run.state);
    summary.appendChild(chip);
    const when = document.createElement("span");
    when.classList.add("pyc-pipeline-detail__run-when");
    when.textContent = run.started_at ? format_timestamp(run.started_at) : "Not started";
    summary.appendChild(when);
    const progress = stage_progress_text(run);
    const cause = words(run.trigger_cause);
    const facts = [cause, progress].filter((part) => part.length > 0).join(" \xB7 ");
    if (facts.length > 0) {
      const meta = document.createElement("span");
      meta.classList.add("pyc-pipeline-detail__run-meta");
      meta.textContent = facts;
      summary.appendChild(meta);
    }
    if (typeof run.final_state_reason === "string" && run.final_state_reason.length > 0) {
      const reason = document.createElement("span");
      reason.classList.add("pyc-pipeline-detail__run-reason", "pyc-pipeline-detail__run-reason--line");
      reason.setAttribute("data-role", "run-reason");
      reason.textContent = run.final_state_reason;
      summary.appendChild(reason);
    }
    details.appendChild(summary);
    const stages = Array.isArray(run.stages) ? run.stages.slice().sort((left, right) => left.stage_index - right.stage_index) : [];
    for (const stage of stages) {
      const block = document.createElement("div");
      block.classList.add("pyc-pipeline-detail__run-stage");
      const head = document.createElement("div");
      head.classList.add("pyc-pipeline-detail__run-stage-head");
      const stage_chip = document.createElement("span");
      stage_chip.classList.add("pyc-pipeline-detail__run-chip");
      stage_chip.setAttribute("data-tone", run_state_tone(stage.state));
      stage_chip.textContent = words(stage.state);
      head.appendChild(stage_chip);
      const stage_name = document.createElement("strong");
      stage_name.textContent = String(stage.stage_id);
      head.appendChild(stage_name);
      block.appendChild(head);
      if (typeof stage.final_state_reason === "string" && stage.final_state_reason.length > 0) {
        const stage_reason = document.createElement("p");
        stage_reason.classList.add("pyc-pipeline-detail__run-reason");
        stage_reason.textContent = stage.final_state_reason;
        block.appendChild(stage_reason);
      }
      const steps = Array.isArray(stage.steps) ? stage.steps.slice().sort((left, right) => left.step_index - right.step_index) : [];
      for (const step of steps) {
        const line = document.createElement("div");
        line.classList.add("pyc-pipeline-detail__run-step");
        line.setAttribute("data-role", "run-step");
        const step_chip = document.createElement("span");
        step_chip.classList.add("pyc-pipeline-detail__run-chip");
        step_chip.setAttribute("data-tone", run_state_tone(step.state));
        step_chip.textContent = words(step.state);
        line.appendChild(step_chip);
        const label = document.createElement("span");
        label.textContent = String(step.step_id) + (typeof step.kind_name === "string" && step.kind_name.length > 0 ? " (" + step.kind_name + ")" : "");
        line.appendChild(label);
        if (typeof step.layer5_run_id === "string" && step.layer5_run_id.length > 0) {
          const link = document.createElement("a");
          link.classList.add("pyc-pipeline-detail__back-link");
          link.setAttribute("data-role", "run-step-link");
          link.setAttribute("href", "/runs/" + encodeURIComponent(step.layer5_run_id));
          link.textContent = "Open the run";
          line.appendChild(link);
        }
        if (typeof step.final_state_reason === "string" && step.final_state_reason.length > 0) {
          const step_reason = document.createElement("span");
          step_reason.classList.add("pyc-pipeline-detail__run-reason");
          step_reason.textContent = step.final_state_reason;
          line.appendChild(step_reason);
        }
        block.appendChild(line);
      }
      details.appendChild(block);
    }
    item.appendChild(details);
    return item;
  }
  _build_stage_list(stages) {
    const section = document.createElement("section");
    section.classList.add("pyc-pipeline-detail__stages");
    section.setAttribute("data-role", "stage-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pipeline stages");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pipeline-detail__section-heading");
    heading.textContent = "Stages";
    section.appendChild(heading);
    if (stages.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pipeline-detail__status");
      empty.setAttribute("data-role", "stages-empty");
      empty.textContent = "No stages defined.";
      section.appendChild(empty);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-pipeline-detail__stage-list");
    for (const stage of stages) {
      const item = document.createElement("li");
      item.classList.add("pyc-pipeline-detail__stage");
      item.setAttribute("data-role", "stage-card");
      const stage_name = document.createElement("strong");
      stage_name.classList.add("pyc-pipeline-detail__stage-name");
      stage_name.textContent = stage.stage_id;
      item.appendChild(stage_name);
      const when = stage.when_clause;
      if (when !== void 0 && when !== null && when.length > 0) {
        const chip = document.createElement("span");
        chip.classList.add("pyc-pipeline-detail__stage-when");
        chip.textContent = "when: " + when;
        item.appendChild(chip);
      }
      const needs = stage.needs;
      const needs_text = document.createElement("span");
      needs_text.classList.add("pyc-pipeline-detail__stage-needs");
      if (needs !== void 0 && needs !== null && needs.length > 0) {
        needs_text.textContent = "needs: " + needs.join(", ");
      } else {
        needs_text.textContent = "needs: none";
      }
      item.appendChild(needs_text);
      const steps = stage.steps;
      const steps_text = document.createElement("span");
      steps_text.classList.add("pyc-pipeline-detail__stage-steps");
      if (Array.isArray(steps) === true && steps.length > 0) {
        const step_ids = [];
        for (const step of steps) {
          step_ids.push(step.step_id);
        }
        steps_text.textContent = "steps: " + step_ids.join(", ");
      } else {
        steps_text.textContent = "steps: none";
      }
      item.appendChild(steps_text);
      list.appendChild(item);
    }
    section.appendChild(list);
    return section;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-pipelines-bundle/index.entry.js
var ORCHESTRATION_GROUP_ID = "orchestration";
var PIPELINES_READ_PERMISSION = "system:pipelines.read";
var PIPELINES_ROUTE = "/pipelines";
var PIPELINES_LIST_TAG = "pyc-pipelines-list";
var PIPELINE_DETAIL_TAG = "pyc-pipeline-detail";
var PIPELINES_STYLESHEET_HREF = "/static/javascript/pyc-pipelines-bundle/pyc-pipelines-bundle.css";
function ensure_pipelines_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-pipelines-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = PIPELINES_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-pipelines-bundle");
  document.head.appendChild(link);
  return;
}
var PIPELINES_ENTRY = {
  entryId: "orchestration.pipelines",
  label: "Pipelines",
  route: PIPELINES_ROUTE,
  requiredPermissions: [PIPELINES_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_pipelines_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [PIPELINES_READ_PERMISSION]
  });
  sidebar.registerEntry(PIPELINES_ENTRY);
  return;
}
function define_pipelines_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(PIPELINES_LIST_TAG) === void 0) {
    customElements.define(PIPELINES_LIST_TAG, PycPipelinesList);
  }
  if (customElements.get(PIPELINE_DETAIL_TAG) === void 0) {
    customElements.define(PIPELINE_DETAIL_TAG, PycPipelineDetail);
  }
  return;
}
function classify_pipelines_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === PIPELINES_ROUTE || working === PIPELINES_ROUTE + "/") {
    const rtnval2 = "list";
    return rtnval2;
  }
  const detail_id = pipeline_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_pipelines_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_pipelines_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main");
  if (main === null) {
    return;
  }
  const target_tag = route === "detail" ? PIPELINE_DETAIL_TAG : PIPELINES_LIST_TAG;
  const existing = main.querySelector(target_tag);
  if (existing !== null) {
    return;
  }
  define_pipelines_elements();
  ensure_pipelines_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_pipelines_view_if_active();
  return;
}
function _boot() {
  define_pipelines_elements();
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
      "pychestrate.ui.pipelines.bundle_no_shell_handle",
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
  PycPipelineDetail,
  PycPipelinesList,
  announce_session_expired,
  build_pipeline_detail_link,
  build_pipelines_collection_url,
  build_pipelines_expand_matrix_url,
  build_pipelines_query_url,
  build_pipelines_validate_url,
  classify_pipelines_route,
  compute_dag_columns,
  compute_dag_layout,
  define_pipelines_elements,
  detail_load_message_for_status,
  ensure_pipelines_stylesheet,
  format_timestamp,
  has_next_page,
  has_previous_page,
  list_load_message_for_status,
  mount_pipelines_view_if_active,
  parse_matrix_spec,
  pipeline_detail_url,
  pipeline_id_from_path,
  project_id_from_search,
  register_pipelines_sidebar,
  short_id,
  validate_message_for_status
};
