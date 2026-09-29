import { confirm_action } from "../shared/confirm.js";
import { set_entity_title } from "../shared/page-title.js";
import {
  RESOURCES_WRITE_PERMISSION,
  extract_projects,
  format_timestamp,
  health_tone,
  on_shell_permissions_changed,
  read_problem,
  resource_state_tone,
  shell_write_allowed,
  short_id
} from "./resource-pools-view.js";
import {
  is_valid_uuid,
  project_id_from_search,
  section_error_message
} from "./pool-detail-view.js";
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
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
function build_resource_state_url(resource_id) {
  const rtnval = build_resource_url(resource_id) + "/state";
  return rtnval;
}
// Mirrors the server's permitted-transition table
// (resources.inventory.service._PERMITTED_TRANSITIONS) minus the
// machine-managed leased moves -- leasing happens through
// reservations, not this panel. Retired is terminal.
const STATE_ACTIONS = [
  {
    target: "available",
    label: "Mark available",
    from: ["leased", "quarantined", "maintenance"]
  },
  {
    target: "quarantined",
    label: "Quarantine",
    from: ["available", "leased"]
  },
  {
    target: "maintenance",
    label: "Move to maintenance",
    from: ["available"]
  },
  {
    target: "retired",
    label: "Retire",
    from: ["available", "quarantined", "maintenance"]
  }
];
function legal_state_actions(current_state) {
  const rtnval = [];
  if (typeof current_state !== "string") {
    return rtnval;
  }
  for (const action of STATE_ACTIONS) {
    if (action.from.indexOf(current_state) >= 0) {
      rtnval.push(action);
    }
  }
  return rtnval;
}
function pool_id_from_search(search) {
  if (typeof search !== "string" || search.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const params = new URLSearchParams(search);
  const value = params.get("pool_id");
  if (value === null) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = value.trim();
  return rtnval;
}
class PycResourceDetail extends HTMLElement {
  _resource_id;
  _project_id;
  _pool_id;
  _resource;
  _health;
  _health_error;
  _usage;
  _usage_error;
  _project_names;
  _loading;
  _errored;
  _error_status;
  _transitioning;
  _root;
  _action_status;
  constructor() {
    super();
    this._resource_id = "";
    this._project_id = "";
    this._pool_id = "";
    this._resource = null;
    this._health = null;
    this._health_error = null;
    this._usage = [];
    this._usage_error = null;
    this._project_names = {};
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._transitioning = false;
    this._root = null;
    this._action_status = null;
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
      errorStatus: this._error_status,
      hasHealth: this._health !== null,
      healthError: this._health_error,
      usageError: this._usage_error,
      transitioning: this._transitioning
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the resource id plus navigation
   * context, render the chrome, and fetch the initial snapshot.
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
    this._project_id = project_id_from_search(window.location.search);
    this._pool_id = pool_id_from_search(window.location.search);
    this._render_chrome();
    on_shell_permissions_changed(() => {
      if (this.isConnected === true) {
        this._render_body();
      }
    });
    void this._load();
    void this._load_project_names();
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
      this._error_status = -1;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_body();
    const resource_result = await this._fetch_json(
      build_resource_url(this._resource_id),
      "resource_fetch_failed"
    );
    if (resource_result.ok === false) {
      this._loading = false;
      this._errored = true;
      this._error_status = resource_result.status;
      this._render_body();
      return;
    }
    this._resource = resource_result.body;
    if (this._project_id.length === 0 && typeof this._resource.project_id === "string") {
      this._project_id = this._resource.project_id;
      this._update_back_links();
    }
    const health_result = await this._fetch_json(
      build_resource_health_url(this._resource_id),
      "health_fetch_failed"
    );
    if (health_result.ok === true) {
      this._health = health_result.body;
      this._health_error = null;
    } else if (health_result.status === 404) {
      this._health = null;
      this._health_error = null;
    } else {
      this._health = null;
      this._health_error = health_result.status;
    }
    const usage_result = await this._fetch_json(
      build_resource_usage_url(this._resource_id),
      "usage_fetch_failed"
    );
    if (usage_result.ok === true && Array.isArray(usage_result.body.items) === true) {
      this._usage = usage_result.body.items;
      this._usage_error = null;
    } else {
      this._usage = [];
      this._usage_error = usage_result.status;
    }
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  /**
   * Best-effort fetch of the projects collection so the summary
   * can show a project display name beside the UUID. Failures are
   * silent -- the UUID alone is always rendered.
   */
  async _load_project_names() {
    try {
      const response = await fetch(PROJECTS_LIST_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        return;
      }
      const body = await response.json();
      const projects = extract_projects(body);
      const names = {};
      for (const project of projects) {
        names[project.project_id] = project.display_name;
      }
      this._project_names = names;
      if (this._loading === false && this._errored === false && this._resource !== null) {
        this._render_body();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.project_names_fetch_failed",
        { reason: String(reason) }
      );
    }
    return;
  }
  /**
   * GET a JSON document. Returns ``{ok: true, body}`` on a 2xx
   * response and ``{ok: false, status}`` otherwise -- ``status``
   * is ``0`` for network-level failures so callers can render an
   * error state distinct from an empty collection.
   */
  async _fetch_json(url, failure_tag) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        console.warn(
          "pychestrate.ui.resources." + failure_tag,
          { status: response.status }
        );
        const rtnval2 = { ok: false, status: response.status, body: null };
        return rtnval2;
      }
      const body = await response.json();
      const rtnval = { ok: true, status: response.status, body };
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources." + failure_tag,
        { reason: String(reason) }
      );
      const rtnval = { ok: false, status: 0, body: null };
      return rtnval;
    }
  }
  _pools_list_href() {
    let href = "/resource-pools";
    if (this._project_id.length > 0) {
      href = href + "?project_id=" + encodeURIComponent(this._project_id);
    }
    const rtnval = href;
    return rtnval;
  }
  _pool_detail_href() {
    let href = "/resource-pools/" + encodeURIComponent(this._pool_id);
    if (this._project_id.length > 0) {
      href = href + "?project_id=" + encodeURIComponent(this._project_id);
    }
    const rtnval = href;
    return rtnval;
  }
  _update_back_links() {
    if (this._root === null) {
      return;
    }
    const back = this._root.querySelector('[data-role="back-link"]');
    if (back !== null) {
      back.setAttribute("href", this._pools_list_href());
    }
    const pool_back = this._root.querySelector('[data-role="pool-back-link"]');
    if (pool_back !== null) {
      pool_back.setAttribute("href", this._pool_detail_href());
    }
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-resources", "pyc-resource-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Resource detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-resources__back-link");
    back.setAttribute("href", this._pools_list_href());
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to resource pools";
    root.appendChild(back);
    if (this._pool_id.length > 0) {
      const pool_back = document.createElement("a");
      pool_back.classList.add("pyc-resources__back-link");
      pool_back.setAttribute("href", this._pool_detail_href());
      pool_back.setAttribute("data-role", "pool-back-link");
      pool_back.textContent = "Back to pool " + short_id(this._pool_id);
      root.appendChild(pool_back);
    }
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
      loading.setAttribute("role", "status");
      loading.textContent = "Loading resource…";
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
      error.setAttribute("role", "status");
      const status = this._error_status;
      if (status === -1) {
        error.textContent = "The resource id in the URL is not a valid UUID.";
      } else if (status === 404) {
        error.textContent = "This resource was not found. It may have been deleted.";
      } else if (status === 403) {
        error.textContent = "You do not have permission to view this resource.";
      } else if (status === 0) {
        error.textContent = "Network error while loading this resource. Try refreshing.";
      } else {
        error.textContent = "Failed to load this resource (HTTP " + String(status) + ").";
      }
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._resource));
    if (shell_write_allowed(RESOURCES_WRITE_PERMISSION) === true) {
      fragment.appendChild(this._build_state_controls(this._resource));
    }
    fragment.appendChild(this._build_health());
    fragment.appendChild(this._build_usage_timeline());
    body.replaceChildren(fragment);
    return;
  }
  _project_field_value(project_id) {
    let value = project_id;
    const display_name = this._project_names[project_id];
    if (typeof display_name === "string" && display_name.length > 0 && display_name !== project_id) {
      value = display_name + " (" + project_id + ")";
    }
    const rtnval = value;
    return rtnval;
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
    set_entity_title(String(resource.name ?? "") || "Resource " + short_id(resource.resource_id));
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
    this._append_field(
      grid,
      "Project",
      this._project_field_value(resource.project_id)
    );
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
        const chip = document.createElement("mj-chip");
        chip.classList.add("pyc-resources__tag");
        chip.textContent = tag;
        tag_list.appendChild(chip);
      }
      section.appendChild(tag_list);
    }
    return section;
  }
  /**
   * Build the lifecycle-transition panel -- one button per legal
   * transition out of the resource's current state, an optional
   * reason field, confirm dialogs (retire gets consequence text),
   * and in-flight disabling.
   */
  _build_state_controls(resource) {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "state-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Resource lifecycle");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Lifecycle";
    section.appendChild(heading);
    const actions = legal_state_actions(resource.state);
    if (actions.length === 0) {
      const note = document.createElement("p");
      note.classList.add("pyc-resources__status");
      note.setAttribute("data-role", "state-terminal");
      if (resource.state === "retired") {
        note.textContent = "This resource is retired. Retired is terminal -- register the resource again to bring it back.";
      } else {
        note.textContent = "No lifecycle transitions are available from the current state.";
      }
      section.appendChild(note);
      return section;
    }
    const reason_label = document.createElement("label");
    reason_label.classList.add("pyc-resources__filter");
    reason_label.textContent = "Reason";
    const reason_input = document.createElement("mj-text-field");
    reason_input.classList.add("pyc-resources__input");
    reason_input.setAttribute("type", "text");
    reason_input.setAttribute("placeholder", "optional");
    reason_input.setAttribute("data-role", "state-reason");
    reason_label.appendChild(reason_input);
    section.appendChild(reason_label);
    const button_row = document.createElement("div");
    button_row.classList.add("pyc-resources__filters");
    button_row.setAttribute("data-role", "state-actions");
    const buttons = [];
    for (const action of actions) {
      const button = document.createElement("mj-button");
      button.classList.add("pyc-resources__button");
      button.setAttribute("type", "button");
      button.setAttribute("data-role", "state-action");
      button.setAttribute("data-target-state", action.target);
      button.textContent = action.label;
      if (this._transitioning === true) {
        button.setAttribute("disabled", "");
      }
      button.addEventListener("click", () => {
        void this._submit_transition(
          action,
          reason_input.value.trim(),
          buttons
        );
      });
      button_row.appendChild(button);
      buttons.push(button);
    }
    section.appendChild(button_row);
    return section;
  }
  async _submit_transition(action, reason, buttons) {
    if (this._transitioning === true) {
      return;
    }
    const resource_label = this._resource !== null && typeof this._resource.display_name === "string" && this._resource.display_name.length > 0 ? this._resource.display_name : short_id(this._resource_id);
    let prompt = "Move " + resource_label + " to state '" + action.target + "'?";
    if (action.target === "retired") {
      prompt = "Retire " + resource_label + "? Retiring is permanent -- a retired resource cannot be reactivated and must be registered again.";
    } else if (action.target === "quarantined") {
      prompt = "Quarantine " + resource_label + "? Quarantined resources are excluded from pool allocation until marked available again.";
    }
    const confirmed = await confirm_action(this, prompt, action.target === "retired" ? "Retire resource" : action.target === "quarantined" ? "Quarantine resource" : "Change state");
    if (confirmed !== true) {
      return;
    }
    const body = { state: action.target };
    if (reason.length > 0) {
      body["reason"] = reason;
    }
    this._transitioning = true;
    if (Array.isArray(buttons) === true) {
      for (const button of buttons) {
        button.setAttribute("disabled", "");
      }
    }
    try {
      const response = await fetch(
        build_resource_state_url(this._resource_id),
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
        const problem = await read_problem(response);
        let message = "State change failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to change resource state.";
        } else if (problem.status === 409) {
          message = "This transition is not permitted from the resource's current state. Refresh and try again.";
        } else if (problem.detail.length > 0) {
          message = "State change failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason_caught) {
      console.warn(
        "pychestrate.ui.resources.state_transition_failed",
        { reason: String(reason_caught) }
      );
      this._show_action_status(
        "State change failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      this._transitioning = false;
      if (Array.isArray(buttons) === true) {
        for (const button of buttons) {
          button.removeAttribute("disabled");
        }
      }
    }
    this._show_action_status(
      "Resource moved to '" + action.target + "'.",
      false
    );
    await this._load();
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
    if (this._health_error !== null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "health-error-state");
      error.setAttribute("role", "status");
      error.textContent = section_error_message(
        "this resource's health record",
        this._health_error
      );
      section.appendChild(error);
      return section;
    }
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
    if (this._usage_error !== null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "usage-error-state");
      error.setAttribute("role", "status");
      error.textContent = section_error_message(
        "this resource's usage history",
        this._usage_error
      );
      section.appendChild(error);
      return section;
    }
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
}
export {
  PycResourceDetail,
  STATE_ACTIONS,
  build_resource_health_url,
  build_resource_state_url,
  build_resource_url,
  build_resource_usage_url,
  legal_state_actions,
  pool_id_from_search,
  resource_id_from_path,
  usage_event_tone
};
