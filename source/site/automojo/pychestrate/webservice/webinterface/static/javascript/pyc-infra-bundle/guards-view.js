const PROJECTS_API_PATH = "/api/v1/projects";
function build_guards_collection_url(project_id, environment_id) {
  let url = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/blast-radius-guards";
  if (typeof environment_id === "string" && environment_id.length > 0) {
    const params = new URLSearchParams();
    params.set("environment_id", environment_id);
    url = url + "?" + params.toString();
  }
  const rtnval = url;
  return rtnval;
}
function build_guard_item_url(project_id, guard_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/blast-radius-guards/" + encodeURIComponent(guard_id);
  return rtnval;
}
function build_guards_evaluate_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/blast-radius-guards:evaluate";
  return rtnval;
}
function format_guard_timestamp(value) {
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
function guard_enabled_tone(enabled) {
  if (enabled === true) {
    const rtnval2 = "ok";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function verdict_tone(verdict) {
  if (typeof verdict !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = verdict.toLowerCase();
  if (lowered === "allow" || lowered === "allowed" || lowered === "pass") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "deny" || lowered === "denied" || lowered === "block" || lowered === "fail") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function attach_message_for_status(status) {
  if (status === 201 || status === 200) {
    const rtnval2 = "Guard attached.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "That rule is already attached to the environment.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The guard request was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project, environment, or rule.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to attach guards.";
    return rtnval2;
  }
  const rtnval = "Failed to attach guard (HTTP " + String(status) + ").";
  return rtnval;
}
function toggle_message_for_status(status, enabled) {
  if (status === 200) {
    const rtnval2 = enabled === true ? "Guard enabled." : "Guard disabled.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown guard.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to change guards.";
    return rtnval2;
  }
  const rtnval = "Failed to update guard (HTTP " + String(status) + ").";
  return rtnval;
}
function parse_actor_roles(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = [];
    return rtnval2;
  }
  const pieces = raw.split(",");
  const rtnval = [];
  for (const piece of pieces) {
    const trimmed = piece.trim();
    if (trimmed.length > 0) {
      rtnval.push(trimmed);
    }
  }
  return rtnval;
}
function extract_guard_projects(body) {
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
class PycGuards extends HTMLElement {
  _state;
  _guards;
  _projects;
  _projectsAvailable;
  _root;
  _table_region;
  _attach_region;
  _evaluate_region;
  _toast_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      environmentFilter: "",
      loading: false,
      errored: false,
      total: 0
    };
    this._guards = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._root = null;
    this._table_region = null;
    this._attach_region = null;
    this._evaluate_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + filter state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
      environmentFilter: this._state.environmentFilter,
      loading: this._state.loading,
      errored: this._state.errored,
      total: this._state.total
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
   * environment filter, attach + evaluate actions, table region,
   * evaluate panel, toast region.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-infra");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-infra__heading");
    heading.textContent = "Blast-Radius Guards";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-infra__controls");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-infra__field");
    project_label.textContent = "Project";
    const project_select = document.createElement("select");
    project_select.classList.add("pyc-infra__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("input");
    project_input.classList.add("pyc-infra__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectId = project_input.value.trim();
      void this._refresh();
    });
    controls.appendChild(project_input);
    const env_label = document.createElement("label");
    env_label.classList.add("pyc-infra__field");
    env_label.textContent = "Environment filter";
    const env_input = document.createElement("input");
    env_input.classList.add("pyc-infra__input");
    env_input.setAttribute("type", "text");
    env_input.setAttribute("placeholder", "environment id (optional)");
    env_input.setAttribute("data-role", "environment-filter");
    env_input.addEventListener("change", () => {
      this._state.environmentFilter = env_input.value.trim();
      void this._refresh();
    });
    env_label.appendChild(env_input);
    controls.appendChild(env_label);
    const attach_button = document.createElement("button");
    attach_button.classList.add("pyc-infra__button");
    attach_button.setAttribute("type", "button");
    attach_button.setAttribute("data-role", "attach-toggle");
    attach_button.textContent = "Attach Guard";
    attach_button.addEventListener("click", () => {
      this._toggle_attach_form();
    });
    controls.appendChild(attach_button);
    const evaluate_button = document.createElement("button");
    evaluate_button.classList.add("pyc-infra__button");
    evaluate_button.setAttribute("type", "button");
    evaluate_button.setAttribute("data-role", "evaluate-toggle");
    evaluate_button.textContent = "Evaluate Preview";
    evaluate_button.addEventListener("click", () => {
      this._toggle_evaluate_panel();
    });
    controls.appendChild(evaluate_button);
    const refresh_button = document.createElement("button");
    refresh_button.classList.add("pyc-infra__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const attach_region = document.createElement("div");
    attach_region.classList.add("pyc-infra__form-region");
    attach_region.setAttribute("data-role", "attach-region");
    attach_region.hidden = true;
    root.appendChild(attach_region);
    this._attach_region = attach_region;
    const evaluate_region = document.createElement("div");
    evaluate_region.classList.add("pyc-infra__form-region");
    evaluate_region.setAttribute("data-role", "evaluate-region");
    evaluate_region.hidden = true;
    root.appendChild(evaluate_region);
    this._evaluate_region = evaluate_region;
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
      const response = await fetch(PROJECTS_API_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        projects = extract_guard_projects(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.guard_projects_fetch_failed",
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
      await this._refresh();
    } else {
      this._render_table_region();
    }
    return;
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
    if (select instanceof HTMLSelectElement === false || input instanceof HTMLInputElement === false) {
      return;
    }
    const select_el = select;
    const input_el = input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      for (const project of this._projects) {
        const option = document.createElement("option");
        option.value = project.project_id;
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
   * Fetch the guard list for the active project and re-render
   * the table. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._guards = [];
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._render_table_region();
    const url = build_guards_collection_url(
      this._state.projectId,
      this._state.environmentFilter
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
          "guards fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.guards_fetch_failed",
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
    this._guards = page.items;
    const meta = page.meta;
    if (meta !== void 0 && meta !== null) {
      if (typeof meta.total === "number") {
        this._state.total = meta.total;
      }
    }
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
    return;
  }
  /**
   * Re-render the table region from the current state + guards.
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
      notice.textContent = "Select a project to view its guards.";
      region.replaceChildren(notice);
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-infra__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading guards\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-infra__status",
        "pyc-infra__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load guards. Try refreshing.";
      region.replaceChildren(error);
      return;
    }
    if (this._guards.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-infra__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No blast-radius guards attached yet";
      region.replaceChildren(empty);
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    return;
  }
  /**
   * Build the guards ``<table>`` from the current list, ordered
   * by environment so guards are grouped per environment.
   */
  _build_table() {
    const table = document.createElement("table");
    table.classList.add("pyc-infra__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = [
      "Environment",
      "Rule",
      "State",
      "Added",
      "Actions"
    ];
    for (const column of columns) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column;
      head_row.appendChild(th);
    }
    thead.appendChild(head_row);
    table.appendChild(thead);
    const ordered = this._guards.slice();
    ordered.sort((left, right) => {
      if (left.environment_id < right.environment_id) {
        return -1;
      }
      if (left.environment_id > right.environment_id) {
        return 1;
      }
      return 0;
    });
    const tbody = document.createElement("tbody");
    for (const guard of ordered) {
      tbody.appendChild(this._build_row(guard));
    }
    table.appendChild(tbody);
    return table;
  }
  /**
   * Build one guard table row, including the enabled badge and
   * the per-row enable/disable toggle.
   *
   * @param guard The guard to render.
   *
   * @returns A populated ``<tr>``.
   */
  _build_row(guard) {
    const row = document.createElement("tr");
    row.classList.add("pyc-infra__row");
    row.setAttribute("data-guard-id", guard.guard_id);
    const env_cell = document.createElement("td");
    env_cell.textContent = guard.environment_id;
    row.appendChild(env_cell);
    const rule_cell = document.createElement("td");
    rule_cell.textContent = guard.rule_id;
    row.appendChild(rule_cell);
    const state_cell = document.createElement("td");
    const state_badge = document.createElement("span");
    state_badge.classList.add("pyc-infra__badge");
    state_badge.setAttribute("data-role", "enabled-indicator");
    state_badge.setAttribute(
      "data-tone",
      guard_enabled_tone(guard.enabled)
    );
    state_badge.textContent = guard.enabled === true ? "enabled" : "disabled";
    state_cell.appendChild(state_badge);
    row.appendChild(state_cell);
    const added_cell = document.createElement("td");
    added_cell.textContent = format_guard_timestamp(guard.added_at);
    row.appendChild(added_cell);
    const actions_cell = document.createElement("td");
    const toggle_button = document.createElement("button");
    toggle_button.classList.add(
      "pyc-infra__button",
      "pyc-infra__row-action"
    );
    toggle_button.setAttribute("type", "button");
    toggle_button.setAttribute("data-role", "toggle-guard");
    toggle_button.textContent = guard.enabled === true ? "Disable" : "Enable";
    toggle_button.addEventListener("click", () => {
      toggle_button.disabled = true;
      void this._on_toggle(guard, toggle_button);
    });
    actions_cell.appendChild(toggle_button);
    row.appendChild(actions_cell);
    return row;
  }
  /**
   * Run the enable/disable toggle for one guard -- PATCH the
   * flag then refresh the list, surfacing a toast.
   *
   * @param guard The guard to toggle.
   * @param button The row action button, re-enabled on completion.
   */
  async _on_toggle(guard, button) {
    const next_enabled = guard.enabled === false;
    const outcome = await this._do_toggle(guard.guard_id, next_enabled);
    button.disabled = false;
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * PATCH a guard's ``enabled`` flag. Exposed so unit tests can
   * drive a toggle without a row button.
   *
   * @param guard_id The guard to update.
   * @param enabled The desired ``enabled`` flag.
   *
   * @returns The toggle outcome.
   */
  async toggleGuard(guard_id, enabled) {
    const rtnval = await this._do_toggle(guard_id, enabled);
    return rtnval;
  }
  async _do_toggle(guard_id, enabled) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        message: "Select a project before changing guards."
      };
      return rtnval2;
    }
    let status = 0;
    try {
      const url = build_guard_item_url(
        this._state.projectId,
        guard_id
      );
      const response = await fetch(url, {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ enabled })
      });
      status = response.status;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.guard_toggle_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: "Failed to reach the guards service."
      };
      return rtnval2;
    }
    const rtnval = {
      ok: status === 200,
      status,
      message: toggle_message_for_status(status, enabled)
    };
    return rtnval;
  }
  /**
   * Toggle the inline attach-guard form's visibility, rendering
   * it on first reveal.
   */
  _toggle_attach_form() {
    if (this._attach_region === null) {
      return;
    }
    const region = this._attach_region;
    if (region.hidden === true) {
      this._render_attach_form();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the attach-guard form into the attach region.
   */
  _render_attach_form() {
    if (this._attach_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-infra__form");
    form.setAttribute("data-role", "attach-form");
    const env_label = document.createElement("label");
    env_label.classList.add("pyc-infra__field");
    env_label.textContent = "Environment id";
    const env_input = document.createElement("input");
    env_input.classList.add("pyc-infra__input");
    env_input.setAttribute("type", "text");
    env_input.setAttribute("data-role", "attach-environment");
    env_input.required = true;
    env_label.appendChild(env_input);
    form.appendChild(env_label);
    const rule_label = document.createElement("label");
    rule_label.classList.add("pyc-infra__field");
    rule_label.textContent = "Rule id";
    const rule_input = document.createElement("input");
    rule_input.classList.add("pyc-infra__input");
    rule_input.setAttribute("type", "text");
    rule_input.setAttribute("placeholder", "max-destroy-count");
    rule_input.setAttribute("data-role", "attach-rule");
    rule_input.required = true;
    rule_label.appendChild(rule_input);
    form.appendChild(rule_label);
    const submit_button = document.createElement("button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "attach-submit");
    submit_button.textContent = "Attach Guard";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-infra__form-status");
    status.setAttribute("data-role", "attach-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_attach(
        form,
        env_input,
        rule_input,
        submit_button
      );
    });
    this._attach_region.replaceChildren(form);
    return;
  }
  async _submit_attach(form, env_input, rule_input, submit_button) {
    const status = form.querySelector('[data-role="attach-status"]');
    const environment_id = env_input.value.trim();
    const rule_id = rule_input.value.trim();
    if (environment_id.length === 0 || rule_id.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Environment id and rule id are required.";
      }
      return;
    }
    submit_button.disabled = true;
    if (status instanceof HTMLElement) {
      status.textContent = "Attaching guard\u2026";
    }
    const outcome = await this._do_attach(environment_id, rule_id);
    submit_button.disabled = false;
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * POST a ``BlastRadiusGuardCreateRequest``. Exposed so unit
   * tests can invoke an attach without a real form-submit event.
   *
   * @param environment_id The environment to attach the guard to.
   * @param rule_id The blast-radius rule identifier.
   *
   * @returns The attach outcome.
   */
  async attachGuard(environment_id, rule_id) {
    const rtnval = await this._do_attach(environment_id, rule_id);
    return rtnval;
  }
  async _do_attach(environment_id, rule_id) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        guardId: "",
        message: "Select a project before attaching a guard."
      };
      return rtnval2;
    }
    const payload = {
      environment_id,
      rule_id,
      enabled: true
    };
    let status = 0;
    let guard_id = "";
    try {
      const url = build_guards_collection_url(
        this._state.projectId,
        ""
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
        const guard = body;
        if (guard !== null && typeof guard.guard_id === "string") {
          guard_id = guard.guard_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.guard_attach_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        guardId: "",
        message: "Failed to reach the guards service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      guardId: guard_id,
      message: attach_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Toggle the evaluate-preview panel's visibility, rendering it
   * on first reveal.
   */
  _toggle_evaluate_panel() {
    if (this._evaluate_region === null) {
      return;
    }
    const region = this._evaluate_region;
    if (region.hidden === true) {
      this._render_evaluate_panel();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Render the evaluate-preview panel -- an environment id +
   * action + actor-roles form plus a verdict-trace output region.
   */
  _render_evaluate_panel() {
    if (this._evaluate_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-infra__form");
    form.setAttribute("data-role", "evaluate-form");
    const env_label = document.createElement("label");
    env_label.classList.add("pyc-infra__field");
    env_label.textContent = "Environment id";
    const env_input = document.createElement("input");
    env_input.classList.add("pyc-infra__input");
    env_input.setAttribute("type", "text");
    env_input.setAttribute("data-role", "evaluate-environment");
    env_input.required = true;
    env_label.appendChild(env_input);
    form.appendChild(env_label);
    const action_label = document.createElement("label");
    action_label.classList.add("pyc-infra__field");
    action_label.textContent = "Action";
    const action_input = document.createElement("input");
    action_input.classList.add("pyc-infra__input");
    action_input.setAttribute("type", "text");
    action_input.setAttribute("placeholder", "environment.destroy");
    action_input.setAttribute("data-role", "evaluate-action");
    action_input.required = true;
    action_label.appendChild(action_input);
    form.appendChild(action_label);
    const roles_label = document.createElement("label");
    roles_label.classList.add("pyc-infra__field");
    roles_label.textContent = "Actor roles (comma-separated)";
    const roles_input = document.createElement("input");
    roles_input.classList.add("pyc-infra__input");
    roles_input.setAttribute("type", "text");
    roles_input.setAttribute("placeholder", "operator, release-manager");
    roles_input.setAttribute("data-role", "evaluate-roles");
    roles_label.appendChild(roles_input);
    form.appendChild(roles_label);
    const submit_button = document.createElement("button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", "evaluate-submit");
    submit_button.textContent = "Evaluate";
    form.appendChild(submit_button);
    const status = document.createElement("p");
    status.classList.add("pyc-infra__form-status");
    status.setAttribute("data-role", "evaluate-status");
    form.appendChild(status);
    const output = document.createElement("div");
    output.classList.add("pyc-infra__table-region");
    output.setAttribute("data-role", "evaluate-output");
    form.appendChild(output);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_evaluate(
        form,
        env_input,
        action_input,
        roles_input,
        submit_button,
        output
      );
    });
    this._evaluate_region.replaceChildren(form);
    return;
  }
  async _submit_evaluate(form, env_input, action_input, roles_input, submit_button, output) {
    const status = form.querySelector('[data-role="evaluate-status"]');
    const environment_id = env_input.value.trim();
    const action = action_input.value.trim();
    if (environment_id.length === 0 || action.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Environment id and action are required.";
      }
      return;
    }
    const roles = parse_actor_roles(roles_input.value);
    submit_button.disabled = true;
    if (status instanceof HTMLElement) {
      status.textContent = "Evaluating\u2026";
    }
    const outcome = await this._do_evaluate(
      environment_id,
      action,
      roles
    );
    submit_button.disabled = false;
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._render_evaluate_output(output, outcome);
    return;
  }
  /**
   * POST a guard-evaluation request. Exposed so unit tests can
   * drive an evaluation without a real form-submit event.
   *
   * @param environment_id The environment to evaluate against.
   * @param action The orchestration action to test.
   * @param actor_role_set The actor's role set.
   *
   * @returns The evaluation outcome.
   */
  async evaluateGuards(environment_id, action, actor_role_set) {
    const rtnval = await this._do_evaluate(
      environment_id,
      action,
      actor_role_set
    );
    return rtnval;
  }
  async _do_evaluate(environment_id, action, actor_role_set) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        evaluation: null,
        message: "Select a project before evaluating guards."
      };
      return rtnval2;
    }
    const payload = {
      environment_id,
      action,
      actor_role_set
    };
    let status = 0;
    let evaluation = null;
    try {
      const url = build_guards_evaluate_url(this._state.projectId);
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
        const parsed = body;
        if (parsed !== null && typeof parsed.allowed === "boolean") {
          evaluation = parsed;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.guard_evaluate_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        evaluation: null,
        message: "Failed to reach the guards service."
      };
      return rtnval2;
    }
    if (status === 200 && evaluation !== null) {
      const rtnval2 = {
        ok: true,
        status,
        evaluation,
        message: evaluation.allowed === true ? "Action would be allowed." : "Action would be blocked."
      };
      return rtnval2;
    }
    const rtnval = {
      ok: false,
      status,
      evaluation: null,
      message: "Failed to evaluate guards (HTTP " + String(status) + ")."
    };
    return rtnval;
  }
  /**
   * Render the verdict trace of a guard evaluation into the
   * panel output region.
   *
   * @param output The panel output region element.
   * @param outcome The evaluation outcome to render.
   */
  _render_evaluate_output(output, outcome) {
    if (outcome.evaluation === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-infra__status",
        "pyc-infra__status--error"
      );
      error.setAttribute("data-role", "evaluate-error");
      error.textContent = outcome.message;
      output.replaceChildren(error);
      return;
    }
    const evaluation = outcome.evaluation;
    const verdict = document.createElement("p");
    verdict.classList.add("pyc-infra__status");
    verdict.setAttribute("data-role", "evaluate-verdict");
    const verdict_badge = document.createElement("span");
    verdict_badge.classList.add("pyc-infra__badge");
    verdict_badge.setAttribute(
      "data-tone",
      evaluation.allowed === true ? "ok" : "error"
    );
    verdict_badge.textContent = evaluation.allowed === true ? "Allowed" : "Blocked";
    verdict.appendChild(verdict_badge);
    output.replaceChildren(verdict);
    if (evaluation.entries.length === 0) {
      return;
    }
    const table = document.createElement("table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("data-role", "evaluate-trace");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    for (const column of ["Rule", "Verdict", "Reason"]) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column;
      head_row.appendChild(th);
    }
    thead.appendChild(head_row);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const entry of evaluation.entries) {
      const row = document.createElement("tr");
      const rule_cell = document.createElement("td");
      rule_cell.textContent = entry.rule_id;
      row.appendChild(rule_cell);
      const verdict_cell = document.createElement("td");
      const badge = document.createElement("span");
      badge.classList.add("pyc-infra__badge");
      badge.setAttribute("data-tone", verdict_tone(entry.verdict));
      badge.textContent = entry.verdict;
      verdict_cell.appendChild(badge);
      row.appendChild(verdict_cell);
      const reason_cell = document.createElement("td");
      reason_cell.textContent = entry.reason ?? "\u2014";
      row.appendChild(reason_cell);
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    output.appendChild(table);
    return;
  }
  /**
   * Render a dismissible toast in the toast region.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-infra__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.classList.add("pyc-infra__toast-message");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("button");
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
  PycGuards,
  attach_message_for_status,
  build_guard_item_url,
  build_guards_collection_url,
  build_guards_evaluate_url,
  extract_guard_projects,
  format_guard_timestamp,
  guard_enabled_tone,
  parse_actor_roles,
  toggle_message_for_status,
  verdict_tone
};
