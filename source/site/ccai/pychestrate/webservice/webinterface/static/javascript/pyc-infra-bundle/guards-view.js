import { hide_unless_may } from "../shared/permissions.js";
import { show_toast } from "../shared/toast.js";
import { message_with_detail, read_problem_detail } from "../shared/problem-detail.js";
import { format_clock_instant, format_instant, parse_timestamp } from "../shared/datetime.js";
import {
  announce_session_expired,
  build_environments_collection_url,
  list_load_message_for_status,
  short_id
} from "./environments-view.js";
import { build_empty_state, show_no_projects } from "../shared/empty-state.js";
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
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
  const parsed = parse_timestamp(value);
  if (parsed === null) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = format_instant(parsed);
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
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/**
 * Whether ``value`` is a complete UUID -- environments are keyed by
 * UUID, so anything shorter can never match (the server answers 422).
 *
 * @param value The candidate id.
 *
 * @returns True for a well-formed UUID.
 */
function is_complete_uuid(value) {
  if (typeof value !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(value.trim());
  return rtnval;
}
/**
 * Read the ``detail`` of an RFC 7807 problem response, or "".
 *
 * @param response A failed fetch Response.
 *
 * @returns The first line of the problem detail, or an empty string.
 */
async function problem_detail_of(response) {
  try {
    const body = await response.json();
    if (body !== null && typeof body === "object" && typeof body.detail === "string") {
      const rtnval2 = body.detail.split(/\r?\n/)[0].trim();
      return rtnval2;
    }
  } catch (reason) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = "";
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
  _projectsNoticeKind;
  _projects_notice_region;
  _environments;
  _environmentsAvailable;
  /**
   * True when the project's environment list could not be read
   * (the picker then falls back to typing a full environment id).
   */
  _environmentsLoadFailed;
  _environment_filter_slot;
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
      errorStatus: 0,
      errorDetail: "",
      total: 0
    };
    this._guards = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._projects_notice_region = null;
    this._environments = [];
    this._environmentsAvailable = false;
    this._environmentsLoadFailed = false;
    this._environment_filter_slot = null;
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
      errorStatus: this._state.errorStatus,
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
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-infra__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      void this._on_project_changed(project_select.value);
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
      void this._on_project_changed(project_input.value.trim());
    });
    controls.appendChild(project_input);
    // Guards are attached per environment, so the list needs one:
    // an environment picker over the project's environments (not an
    // "optional" free-text id -- a partial id can never match).
    const env_label = document.createElement("label");
    env_label.classList.add("pyc-infra__field");
    env_label.textContent = "Environment";
    const env_slot = document.createElement("span");
    env_slot.classList.add("pyc-infra__control-slot");
    env_slot.setAttribute("data-role", "environment-filter-slot");
    env_label.appendChild(env_slot);
    controls.appendChild(env_label);
    this._environment_filter_slot = env_slot;
    const attach_button = document.createElement("mj-button");
    attach_button.classList.add("pyc-infra__button");
    attach_button.setAttribute("type", "button");
    attach_button.setAttribute("data-role", "attach-toggle");
    hide_unless_may(attach_button, "system:guards.write");
    attach_button.textContent = "Attach Guard";
    attach_button.addEventListener("click", () => {
      this._toggle_attach_form();
    });
    controls.appendChild(attach_button);
    const evaluate_button = document.createElement("mj-button");
    evaluate_button.classList.add("pyc-infra__button");
    evaluate_button.setAttribute("type", "button");
    evaluate_button.setAttribute("data-role", "evaluate-toggle");
    evaluate_button.textContent = "Evaluate Preview";
    evaluate_button.addEventListener("click", () => {
      this._toggle_evaluate_panel();
    });
    controls.appendChild(evaluate_button);
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
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-infra__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
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
    this._render_environment_filter();
    return;
  }
  /**
   * Switch to another project: forget the environment chosen for the
   * previous one, load the new project's environments (which picks
   * the first), then load its guards.
   *
   * @param project_id The newly selected project id.
   */
  async _on_project_changed(project_id) {
    this._state.projectId = project_id;
    this._state.environmentFilter = "";
    await this._load_environments();
    await this._refresh();
    return;
  }
  /**
   * Render the environment picker into the controls. With the
   * project's environments loaded it is a select over them; when
   * the project has none it says so; only when the list could not
   * be read does it fall back to typing a full environment id.
   */
  _render_environment_filter() {
    if (this._environment_filter_slot === null) {
      return;
    }
    const slot = this._environment_filter_slot;
    if (this._state.projectId.length === 0) {
      const waiting = document.createElement("span");
      waiting.classList.add("pyc-infra__field-caption");
      waiting.setAttribute("data-role", "environment-filter-empty");
      waiting.textContent = "Select a project first";
      slot.replaceChildren(waiting);
      return;
    }
    if (this._environmentsAvailable === true) {
      const select = document.createElement("mj-select");
      select.classList.add("pyc-infra__select");
      select.setAttribute("data-role", "environment-filter");
      select.setAttribute("aria-label", "Environment");
      for (const environment of this._environments) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", environment.environment_id);
        option.textContent = environment.name + " (" + short_id(environment.environment_id) + ")";
        if (environment.environment_id === this._state.environmentFilter) {
          option.setAttribute("selected", "");
        }
        select.appendChild(option);
      }
      select.value = this._state.environmentFilter;
      select.addEventListener("change", () => {
        this._state.environmentFilter = select.value;
        void this._refresh();
      });
      slot.replaceChildren(select);
      return;
    }
    if (this._environmentsLoadFailed === false) {
      const none = document.createElement("span");
      none.classList.add("pyc-infra__field-caption");
      none.setAttribute("data-role", "environment-filter-empty");
      none.textContent = "This project has no environments — register one on the Environments page.";
      slot.replaceChildren(none);
      return;
    }
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-infra__input");
    input.setAttribute("type", "text");
    input.setAttribute("placeholder", "full environment id (UUID)");
    input.setAttribute("aria-label", "Environment id");
    input.setAttribute("data-role", "environment-filter");
    input.value = this._state.environmentFilter;
    input.addEventListener("change", () => {
      this._state.environmentFilter = input.value.trim();
      void this._refresh();
    });
    slot.replaceChildren(input);
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
        projects = extract_guard_projects(body);
      } else {
        load_failed = true;
      }
    } catch (reason) {
      load_failed = true;
      console.warn(
        "pychestrate.ui.infra.guard_projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._projectsNoticeKind = "";
      this._state.projectId = projects[0].project_id;
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
      await this._load_environments();
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
      region.classList.remove("pyc-infra__projects-notice--error");
      show_no_projects(region, {});
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-infra__projects-notice--error");
      region.textContent = "You don't have permission to list projects.";
      return;
    }
    region.classList.add("pyc-infra__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-infra__button");
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
   * Fetch the environments of the active project so the attach /
   * evaluate forms can offer an environment picker instead of a
   * hand-typed UUID. Exposed so unit tests can await the fetch.
   */
  async loadEnvironments() {
    await this._load_environments();
    return;
  }
  async _load_environments() {
    let environments = [];
    let available = false;
    let load_failed = false;
    if (this._state.projectId.length > 0) {
      try {
        const url = build_environments_collection_url(
          this._state.projectId
        ) + "?per_page=200";
        const response = await fetch(url, {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        });
        if (response.ok === false) {
          load_failed = true;
        }
        if (response.ok === true) {
          const body = await response.json();
          const page = body;
          if (page !== null && Array.isArray(page.items) === true) {
            for (const item of page.items) {
              if (item === null || typeof item !== "object") {
                continue;
              }
              const environment_id = item.environment_id;
              if (typeof environment_id !== "string" || environment_id.length === 0) {
                continue;
              }
              const name = typeof item.name === "string" && item.name.length > 0 ? item.name : environment_id;
              environments.push({ environment_id, name });
            }
            available = environments.length > 0;
          }
        }
      } catch (reason) {
        load_failed = true;
        console.warn(
          "pychestrate.ui.infra.guard_environments_fetch_failed",
          { reason: String(reason) }
        );
      }
    }
    this._environments = environments;
    this._environmentsAvailable = available;
    this._environmentsLoadFailed = load_failed;
    // Keep the chosen environment when the project still has it;
    // otherwise show the first environment's guards.
    if (available === true) {
      const known = environments.some(
        (environment) => environment.environment_id === this._state.environmentFilter
      );
      if (known === false) {
        this._state.environmentFilter = environments[0].environment_id;
      }
    } else if (load_failed === false) {
      this._state.environmentFilter = "";
    }
    this._render_environment_filter();
    if (this._attach_region !== null && this._attach_region.hidden === false) {
      this._render_attach_form();
    }
    if (this._evaluate_region !== null && this._evaluate_region.hidden === false) {
      this._render_evaluate_panel();
    }
    return;
  }
  /**
   * Build the environment control for the attach / evaluate
   * forms -- an ``mj-select`` over the fetched environments when
   * available, else a labelled text input fallback.
   *
   * @param role The ``data-role`` value for test selection.
   *
   * @returns The control element (read its ``value``).
   */
  _build_environment_control(role) {
    if (this._environmentsAvailable === true) {
      const select = document.createElement("mj-select");
      select.classList.add("pyc-infra__select");
      select.setAttribute("data-role", role);
      for (const environment of this._environments) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", environment.environment_id);
        option.textContent = environment.name + " (" + short_id(environment.environment_id) + ")";
        select.appendChild(option);
      }
      const rtnval = select;
      return rtnval;
    }
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-infra__input");
    input.setAttribute("type", "text");
    input.setAttribute("placeholder", "full environment id (UUID) -- no environments listed for this project");
    input.setAttribute("data-role", role);
    input.required = true;
    const rtnval = input;
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
    // The collection endpoint requires environment_id -- fetching
    // without one earns a 400 the user cannot act on ("Failed to
    // load guards (HTTP 400). Try refreshing." never resolves,
    // because refreshing sends the same incomplete request). Hold
    // the fetch until an environment is chosen and prompt instead.
    if (this._state.environmentFilter.length === 0) {
      this._guards = [];
      this._render_table_region();
      return;
    }
    // A typed id must be a complete UUID; a partial one can never
    // match an environment, so say so instead of asking the server.
    if (is_complete_uuid(this._state.environmentFilter) === false) {
      this._guards = [];
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = 422;
      this._state.errorDetail = "Enter a complete environment id (a UUID).";
      this._render_table_region();
      return;
    }
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._state.errorDetail = "";
    this._render_table_region();
    const url = build_guards_collection_url(
      this._state.projectId,
      this._state.environmentFilter
    );
    let page = null;
    let error_status = 0;
    let error_detail = "";
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        error_status = response.status;
        if (error_status >= 400 && error_status < 500) {
          error_detail = await problem_detail_of(response);
        }
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
      if (error_status === 401) {
        announce_session_expired();
      }
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = error_status;
      this._state.errorDetail = error_detail;
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
      if (this._projectsNoticeKind === "empty") {
        // The notice above already says there are no projects and links to
        // creating one; a second line asking to "select a project" contradicted it.
        region.replaceChildren();
        return;
      }
      const notice = document.createElement("p");
      notice.classList.add("pyc-infra__status");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its guards.";
      region.replaceChildren(notice);
      return;
    }
    if (this._state.environmentFilter.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-infra__status");
      notice.setAttribute("data-role", "no-environment-state");
      notice.textContent =
        "Select an environment to view its guards.";
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
      error.textContent = this._state.errorDetail.length > 0 ? this._state.errorDetail : list_load_message_for_status(
        this._state.errorStatus,
        "guards"
      );
      const children = [error];
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-infra__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "list-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._refresh();
        });
        children.push(retry);
      }
      region.replaceChildren(...children);
      return;
    }
    if (this._guards.length === 0) {
      const empty = build_empty_state({ class_name: "pyc-infra__status", message: "No blast-radius guards attached yet.", next_step: "Choose Attach Guard above to add one." });
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
    const self = this;
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
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-infra__row";
    table.rowAttrs = (guard) => ({ "data-guard-id": guard.guard_id });
    table.columns = [
      { key: "environment_id", label: "Environment", width: "16rem" },
      { key: "rule_id", label: "Rule", width: "16rem" },
      {
        key: "enabled",
        label: "State",
        width: "8rem",
        render: (guard) => {
          const state_badge = document.createElement("mj-chip");
          state_badge.classList.add("pyc-infra__badge");
          state_badge.setAttribute("data-role", "enabled-indicator");
          state_badge.setAttribute(
            "data-tone",
            guard_enabled_tone(guard.enabled)
          );
          state_badge.textContent = guard.enabled === true ? "enabled" : "disabled";
          return state_badge;
        }
      },
      {
        key: "added_at",
        label: "Added",
        width: "12rem",
        render: (guard) => format_guard_timestamp(guard.added_at)
      },
      {
        key: "actions",
        label: "Actions",
        width: "8rem",
        sortable: false,
        render: (guard) => {
          const toggle_button = document.createElement("mj-button");
          toggle_button.classList.add(
            "pyc-infra__button",
            "pyc-infra__row-action"
          );
          toggle_button.setAttribute("type", "button");
          toggle_button.setAttribute("data-role", "toggle-guard");
          toggle_button.textContent = guard.enabled === true ? "Disable" : "Enable";
          toggle_button.addEventListener("click", () => {
            toggle_button.toggleAttribute("disabled", true);
            void self._on_toggle(guard, toggle_button);
          });
          return toggle_button;
        }
      }
    ];
    table.rows = ordered;
    return table;
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
    button.toggleAttribute("disabled", false);
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
    let detail = "";
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
      detail = await read_problem_detail(response);
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
      message: message_with_detail("Guard not changed", detail, toggle_message_for_status(status, enabled))
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
    env_label.textContent = "Environment";
    const env_input = this._build_environment_control("attach-environment");
    env_label.appendChild(env_input);
    form.appendChild(env_label);
    const rule_label = document.createElement("label");
    rule_label.classList.add("pyc-infra__field");
    rule_label.textContent = "Rule id (registry rule id)";
    const rule_input = document.createElement("mj-text-field");
    rule_input.classList.add("pyc-infra__input");
    rule_input.setAttribute("type", "text");
    rule_input.setAttribute("placeholder", "FrozenEnvBlockRule");
    rule_input.setAttribute("data-role", "attach-rule");
    rule_input.required = true;
    rule_label.appendChild(rule_input);
    const rule_caption = document.createElement("span");
    rule_caption.classList.add("pyc-infra__field-caption");
    rule_caption.setAttribute("data-role", "attach-rule-caption");
    rule_caption.textContent = "Rule ids come from the guard-rule registry \u2014 run Evaluate Preview to list every registered rule id.";
    rule_label.appendChild(rule_caption);
    form.appendChild(rule_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("variant", "primary");
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
    if (is_complete_uuid(environment_id) === false) {
      if (status instanceof HTMLElement) {
        status.textContent = "Enter a complete environment id (a UUID).";
      }
      return;
    }
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Attaching guard\u2026";
    }
    const outcome = await this._do_attach(environment_id, rule_id);
    submit_button.toggleAttribute("disabled", false);
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
    let detail = "";
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
      } else if (status === 422) {
        detail = await problem_detail_of(response);
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
      message: detail.length > 0 ? "Guard not attached: " + detail : attach_message_for_status(status)
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
    env_label.textContent = "Environment";
    const env_input = this._build_environment_control("evaluate-environment");
    env_label.appendChild(env_input);
    form.appendChild(env_label);
    const action_label = document.createElement("label");
    action_label.classList.add("pyc-infra__field");
    action_label.textContent = "Action";
    const action_input = document.createElement("mj-text-field");
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
    const roles_input = document.createElement("mj-text-field");
    roles_input.classList.add("pyc-infra__input");
    roles_input.setAttribute("type", "text");
    roles_input.setAttribute("placeholder", "operator, release-manager");
    roles_input.setAttribute("data-role", "evaluate-roles");
    roles_label.appendChild(roles_input);
    form.appendChild(roles_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-infra__submit");
    submit_button.setAttribute("variant", "primary");
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
    if (is_complete_uuid(environment_id) === false) {
      if (status instanceof HTMLElement) {
        status.textContent = "Enter a complete environment id (a UUID).";
      }
      return;
    }
    const roles = parse_actor_roles(roles_input.value);
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = "Evaluating\u2026";
    }
    const outcome = await this._do_evaluate(
      environment_id,
      action,
      roles
    );
    submit_button.toggleAttribute("disabled", false);
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
    const verdict_badge = document.createElement("mj-chip");
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
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.setAttribute("data-role", "evaluate-trace");
    table.columns = [
      { key: "rule_id", label: "Rule", width: "16rem" },
      {
        key: "verdict",
        label: "Verdict",
        width: "10rem",
        render: (entry) => {
          const badge = document.createElement("mj-chip");
          badge.classList.add("pyc-infra__badge");
          badge.setAttribute("data-tone", verdict_tone(entry.verdict));
          badge.textContent = entry.verdict;
          return badge;
        }
      },
      {
        key: "reason",
        label: "Reason",
        width: "20rem",
        render: (entry) => entry.reason ?? "\u2014"
      }
    ];
    table.rows = evaluation.entries;
    output.appendChild(table);
    return;
  }
  /**
   * Show a toast in the toast region through the shared service: one at a
   * time, announced to assistive technology, a plain success goes away by itself.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-infra" });
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
  is_complete_uuid,
  parse_actor_roles,
  problem_detail_of,
  toggle_message_for_status,
  verdict_tone
};
