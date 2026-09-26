import {
  build_environments_query_url,
  format_timestamp,
  short_id
} from "./environments-view.js";
const PROVISIONING_STATES = [
  "pending",
  "running",
  "completed",
  "failed",
  "cancelled",
  "rejected_by_guard"
];
const TERMINAL_PROVISIONING_STATES = [
  "completed",
  "failed",
  "cancelled",
  "rejected_by_guard"
];
const PROVISIONING_ACTIONS = [
  "plan",
  "apply",
  "destroy"
];
const DEFAULT_PER_PAGE = 25;
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
function build_provisioning_query_url(state) {
  const params = new URLSearchParams();
  if (state.stateFilter.length > 0) {
    params.set("state", state.stateFilter);
  }
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  const query = params.toString();
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(state.projectId) + "/provisioning-runs?" + query;
  return rtnval;
}
function build_provisioning_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/provisioning-runs";
  return rtnval;
}
function build_provisioning_detail_link(project_id, run_id) {
  const rtnval = "/provisioning-runs/" + encodeURIComponent(run_id) + "?project_id=" + encodeURIComponent(project_id);
  return rtnval;
}
function provisioning_state_tone(run_state) {
  if (run_state === "completed") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (run_state === "failed") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (run_state === "rejected_by_guard") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (run_state === "cancelled") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function is_terminal_provisioning_state(run_state) {
  const rtnval = TERMINAL_PROVISIONING_STATES.indexOf(run_state) >= 0;
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
    const rtnval2 = "Provisioning run triggered.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "Driver inputs were rejected \u2014 check the driver name.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "The environment cannot accept this action right now.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project, environment, or driver.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to trigger provisioning runs.";
    return rtnval2;
  }
  const rtnval = "Failed to trigger provisioning run (HTTP " + String(status) + ").";
  return rtnval;
}
function parse_driver_inputs(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = {};
    return rtnval2;
  }
  const parsed = JSON.parse(raw);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
    throw new SyntaxError("driver inputs must be a JSON object");
  }
  const rtnval = parsed;
  return rtnval;
}
class PycProvisioningList extends HTMLElement {
  _pager;
  _state;
  _runs;
  _environments;
  _projects;
  _projectsAvailable;
  _root;
  _table_region;
  _trigger_region;
  _toast_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      stateFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false
    };
    this._runs = [];
    this._environments = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._root = null;
    this._table_region = null;
    this._pager = null;
    this._trigger_region = null;
    this._toast_region = null;
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
      errored: this._state.errored
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
    root.classList.add("pyc-infra");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-infra__heading");
    heading.textContent = "Provisioning Runs";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-infra__controls");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-infra__field");
    project_label.textContent = "Project";
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-infra__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      this._state.page = 1;
      void this._on_project_changed();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-infra__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectId = project_input.value.trim();
      this._state.page = 1;
      void this._on_project_changed();
    });
    controls.appendChild(project_input);
    const state_label = document.createElement("label");
    state_label.classList.add("pyc-infra__field");
    state_label.textContent = "State";
    const state_select = document.createElement("mj-select");
    state_select.classList.add("pyc-infra__select");
    state_select.setAttribute("data-role", "state-filter");
    const any_option = document.createElement("mj-option");
    any_option.setAttribute("value", "");
    any_option.textContent = "All states";
    state_select.appendChild(any_option);
    for (const run_state of PROVISIONING_STATES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", run_state);
      option.textContent = run_state;
      state_select.appendChild(option);
    }
    state_select.addEventListener("change", () => {
      this._state.stateFilter = state_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    state_label.appendChild(state_select);
    controls.appendChild(state_label);
    const trigger_button = document.createElement("mj-button");
    trigger_button.classList.add("pyc-infra__button");
    trigger_button.setAttribute("type", "button");
    trigger_button.setAttribute("data-role", "trigger-toggle");
    trigger_button.textContent = "Trigger Provisioning";
    trigger_button.addEventListener("click", () => {
      this._toggle_trigger_form();
    });
    controls.appendChild(trigger_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-infra__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const trigger_region = document.createElement("div");
    trigger_region.classList.add("pyc-infra__form-region");
    trigger_region.setAttribute("data-role", "trigger-region");
    trigger_region.hidden = true;
    root.appendChild(trigger_region);
    this._trigger_region = trigger_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-infra__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-infra__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");

    pager.classList.add("pyc-infra__pager");

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
    try {
      const response = await fetch(PROJECTS_LIST_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        projects = this._extract_projects(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._state.projectId = projects[0].project_id;
    } else {
      this._projects = [];
      this._projectsAvailable = false;
    }
    this._render_project_control();
    if (this._state.projectId.length > 0) {
      await this._on_project_changed();
    } else {
      this._render_table_region();
    }
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
   * React to a project change -- reload the environments (so the
   * trigger form's selector is fresh) and the provisioning page.
   */
  async _on_project_changed() {
    await this._load_environments();
    await this._refresh();
    return;
  }
  /**
   * Fetch the active project's environments for the trigger
   * form's environment selector. A failed fetch leaves the list
   * empty.
   */
  async _load_environments() {
    this._environments = [];
    if (this._state.projectId.length === 0) {
      return;
    }
    try {
      const url = build_environments_query_url({
        projectId: this._state.projectId,
        stateFilter: "",
        page: 1,
        perPage: 100,
        total: 0,
        loading: false,
        errored: false
      });
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (page !== null && Array.isArray(page.items) === true) {
          this._environments = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.environments_fetch_failed",
        { reason: String(reason) }
      );
    }
    return;
  }
  /**
   * Fetch the current page of provisioning runs and re-render
   * the table. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._runs = [];
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._render_table_region();
    const url = build_provisioning_query_url(this._state);
    let page = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "provisioning fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.provisioning_fetch_failed",
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
    this._runs = page.items;
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
   * Re-render the table region from the current state + runs.
   */
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.projectId.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-infra__status");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its provisioning runs.";
      region.replaceChildren(notice);
      this._render_pager();
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-infra__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading provisioning runs\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-infra__status",
        "pyc-infra__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load provisioning runs. Try refreshing.";
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._runs.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-infra__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No provisioning runs yet";
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
   * Build the provisioning-runs ``<table>`` from the current
   * ``_runs`` list.
   */
  _build_table() {
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-infra__row";
    table.rowAttrs = (run) => ({ "data-run-id": run.run_id });
    table.columns = [
      {
        key: "run_id",
        label: "Run",
        width: "10rem",
        render: (run) => {
          const link = document.createElement("a");
          link.classList.add("pyc-infra__run-link");
          link.setAttribute(
            "href",
            build_provisioning_detail_link(run.project_id, run.run_id)
          );
          link.textContent = short_id(run.run_id);
          link.title = run.run_id;
          return link;
        }
      },
      { key: "action", label: "Action", width: "8rem" },
      { key: "driver_name", label: "Driver", width: "12rem" },
      {
        key: "state",
        label: "State",
        width: "10rem",
        render: (run) => {
          const badge = document.createElement("mj-chip");
          badge.classList.add("pyc-infra__badge");
          badge.setAttribute("data-tone", provisioning_state_tone(run.state));
          badge.textContent = run.state;
          return badge;
        }
      },
      {
        key: "started_at",
        label: "Started",
        width: "12rem",
        render: (run) => format_timestamp(run.started_at)
      },
      {
        key: "finished_at",
        label: "Finished",
        width: "12rem",
        render: (run) => format_timestamp(run.finished_at)
      }
    ];
    table.rows = this._runs;
    return table;
  }
  /**
   * Update the pager controls -- enabled state + the page
   * indicator label -- from the current state.
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
   * Toggle the inline trigger-provisioning form's visibility,
   * rendering it on first reveal.
   */
  _toggle_trigger_form() {
    if (this._trigger_region === null) {
      return;
    }
    const region = this._trigger_region;
    if (region.hidden === true) {
      this._render_trigger_form();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the trigger-provisioning form -- an environment
   * selector, a driver-name input, an action selector, a
   * driver-inputs JSON textarea, and a submit button.
   */
  _render_trigger_form() {
    if (this._trigger_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-infra__form");
    form.setAttribute("data-role", "trigger-form");
    const environment_label = document.createElement("label");
    environment_label.classList.add("pyc-infra__field");
    environment_label.textContent = "Environment";
    const environment_select = document.createElement("mj-select");
    environment_select.classList.add("pyc-infra__select");
    environment_select.setAttribute("data-role", "trigger-environment");
    if (this._environments.length === 0) {
      const none_option = document.createElement("mj-option");
      none_option.setAttribute("value", "");
      none_option.textContent = "No environment registered";
      environment_select.appendChild(none_option);
    } else {
      for (const environment of this._environments) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", environment.environment_id);
        option.textContent = environment.name + " \xB7 " + environment.kind_name;
        environment_select.appendChild(option);
      }
    }
    environment_label.appendChild(environment_select);
    form.appendChild(environment_label);
    const driver_label = document.createElement("label");
    driver_label.classList.add("pyc-infra__field");
    driver_label.textContent = "Driver name";
    const driver_input = document.createElement("mj-text-field");
    driver_input.classList.add("pyc-infra__input");
    driver_input.setAttribute("type", "text");
    driver_input.setAttribute("placeholder", "terraform");
    driver_input.setAttribute("data-role", "trigger-driver");
    driver_input.required = true;
    driver_label.appendChild(driver_input);
    form.appendChild(driver_label);
    const action_label = document.createElement("label");
    action_label.classList.add("pyc-infra__field");
    action_label.textContent = "Action";
    const action_select = document.createElement("mj-select");
    action_select.classList.add("pyc-infra__select");
    action_select.setAttribute("data-role", "trigger-action");
    for (const action of PROVISIONING_ACTIONS) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", action);
      option.textContent = action;
      action_select.appendChild(option);
    }
    action_label.appendChild(action_select);
    form.appendChild(action_label);
    const inputs_label = document.createElement("label");
    inputs_label.classList.add(
      "pyc-infra__field",
      "pyc-infra__field--wide"
    );
    inputs_label.textContent = "Driver inputs (JSON)";
    const inputs_area = document.createElement("mj-textarea");
    inputs_area.classList.add("pyc-infra__textarea");
    inputs_area.setAttribute("data-role", "trigger-driver-inputs");
    inputs_area.setAttribute("placeholder", '{"auto_approve": false}');
    inputs_area.rows = 3;
    inputs_label.appendChild(inputs_area);
    form.appendChild(inputs_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "trigger-submit");
    submit_button.textContent = "Trigger Provisioning";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-infra__form-status");
    status.setAttribute("data-role", "trigger-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_trigger(
        form,
        environment_select,
        driver_input,
        action_select,
        inputs_area,
        submit_button
      );
    });
    this._trigger_region.replaceChildren(form);
    return;
  }
  async _submit_trigger(form, environment_select, driver_input, action_select, inputs_area, submit_button) {
    const status = form.querySelector('[data-role="trigger-status"]');
    const environment_id = environment_select.value;
    const driver_name = driver_input.value.trim();
    const action = action_select.value;
    if (environment_id.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Select a target environment.";
      }
      return;
    }
    if (driver_name.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Driver name is required.";
      }
      return;
    }
    let driver_inputs = {};
    try {
      driver_inputs = parse_driver_inputs(inputs_area.value);
    } catch (reason) {
      if (status instanceof HTMLElement) {
        status.textContent = "Driver inputs must be valid JSON.";
      }
      console.warn(
        "pychestrate.ui.infra.trigger_inputs_invalid",
        { reason: String(reason) }
      );
      return;
    }
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Triggering provisioning run\u2026";
    }
    const outcome = await this._do_trigger(
      environment_id,
      driver_name,
      action,
      driver_inputs
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
  /**
   * POST a ``ProvisioningRunCreateRequest``. Exposed so unit
   * tests can invoke a trigger without a real form-submit event.
   *
   * @param environment_id Bound target environment id.
   * @param driver_name Registered infra-tool driver factory name.
   * @param action ``"plan"`` | ``"apply"`` | ``"destroy"``.
   * @param driver_inputs Free-form driver inputs object.
   *
   * @returns The trigger outcome.
   */
  async triggerProvisioning(environment_id, driver_name, action, driver_inputs) {
    const rtnval = await this._do_trigger(
      environment_id,
      driver_name,
      action,
      driver_inputs
    );
    return rtnval;
  }
  async _do_trigger(environment_id, driver_name, action, driver_inputs) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        runId: "",
        message: "Select a project before triggering a run."
      };
      return rtnval2;
    }
    const payload = {
      environment_id,
      driver_name,
      action,
      driver_inputs
    };
    let status = 0;
    let run_id = "";
    try {
      const url = build_provisioning_collection_url(
        this._state.projectId
      );
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
          run_id = run.run_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.trigger_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        runId: "",
        message: "Failed to reach the provisioning service."
      };
      return rtnval2;
    }
    const ok = status === 202 || status === 200 || status === 201;
    const rtnval = {
      ok,
      status,
      runId: run_id,
      message: trigger_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Render a dismissible toast for a trigger outcome -- on
   * success the toast links to the new run's detail page.
   *
   * @param outcome The trigger-provisioning outcome.
   */
  _show_trigger_toast(outcome) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-infra__toast");
    toast.setAttribute("data-role", "trigger-toast");
    toast.setAttribute("data-tone", outcome.ok === true ? "ok" : "error");
    const message = document.createElement("span");
    message.classList.add("pyc-infra__toast-message");
    message.textContent = outcome.message;
    toast.appendChild(message);
    if (outcome.ok === true && outcome.runId.length > 0) {
      const link = document.createElement("a");
      link.classList.add("pyc-infra__toast-link");
      link.setAttribute(
        "href",
        build_provisioning_detail_link(
          this._state.projectId,
          outcome.runId
        )
      );
      link.setAttribute("data-role", "trigger-toast-link");
      link.textContent = "View run";
      toast.appendChild(link);
    }
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-infra__toast-dismiss");
    dismiss.setAttribute("type", "button");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "\xD7";
    dismiss.addEventListener("click", () => {
      toast.remove();
    });
    toast.appendChild(dismiss);
    this._toast_region.replaceChildren(toast);
    return;
  }
}
export {
  PROVISIONING_ACTIONS,
  PROVISIONING_STATES,
  PycProvisioningList,
  TERMINAL_PROVISIONING_STATES,
  build_provisioning_collection_url,
  build_provisioning_detail_link,
  build_provisioning_query_url,
  has_next_page,
  has_previous_page,
  is_terminal_provisioning_state,
  parse_driver_inputs,
  provisioning_state_tone,
  trigger_message_for_status
};
