import { hide_unless_may } from "../shared/permissions.js";
import { show_toast } from "../shared/toast.js";
import { confirm_action } from "../shared/confirm.js";
import {
  announce_session_expired,
  list_load_message_for_status
} from "./test-metrics-view.js";
import { build_empty_state, show_no_projects } from "../shared/empty-state.js";
import { choose_project_id, mirror_to_query } from "../shared/view-state.js";
import { reveal } from "../shared/reveal.js";
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
const DEFAULT_SLO_KIND = "availability_ratio";
const SLO_CONFIG_EXAMPLE = '{"good_metric_name": "pychestrate_rpa_jobs_completed_total", "total_metric_name": "pychestrate_rpa_jobs_triggered_total"}';
function build_slos_collection_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/slos";
  return rtnval;
}
function build_slo_detail_url(project_id, slo_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/slos/" + encodeURIComponent(slo_id);
  return rtnval;
}
function format_ratio(value) {
  if (value === null || value === void 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  if (typeof value !== "number" || Number.isNaN(value) === true) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  if (value >= 1) {
    const rtnval2 = "100%";
    return rtnval2;
  }
  if (value <= 0) {
    const rtnval2 = "0%";
    return rtnval2;
  }
  // An objective is judged in nines, so the precision follows the value and
  // the last digit is cut, not rounded: 99.95% must not read "100.0%" and
  // 99.996% must not read as perfect (ORC-36).
  const percent = value * 100;
  let decimals = 1;
  if (percent >= 99.9) {
    decimals = 3;
  } else if (percent >= 99) {
    decimals = 2;
  }
  const scale = Math.pow(10, decimals);
  const cut = Math.floor(percent * scale + 1e-6) / scale;
  let text = cut.toFixed(decimals);
  // Drop trailing zeros but keep one decimal ("99.90" reads "99.9").
  text = text.replace(/(\.\d*?[1-9])0+$/, "$1").replace(/(\.\d)0+$/, "$1");
  const rtnval = text + "%";
  return rtnval;
}
function format_window(seconds) {
  if (typeof seconds !== "number" || seconds <= 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const day = 86400;
  const hour = 3600;
  const minute = 60;
  if (seconds % day === 0) {
    const rtnval2 = String(seconds / day) + "d";
    return rtnval2;
  }
  if (seconds % hour === 0) {
    const rtnval2 = String(seconds / hour) + "h";
    return rtnval2;
  }
  if (seconds % minute === 0) {
    const rtnval2 = String(seconds / minute) + "m";
    return rtnval2;
  }
  const rtnval = String(seconds) + "s";
  return rtnval;
}
function slo_status_tone(status) {
  if (status === null) {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  if (status.breaching === true) {
    const rtnval2 = "error";
    return rtnval2;
  }
  const remaining = status.error_budget_remaining_ratio;
  if (typeof remaining === "number" && remaining < 0.25) {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "ok";
  return rtnval;
}
function slo_status_label(status) {
  if (status === null) {
    const rtnval2 = "Not evaluated";
    return rtnval2;
  }
  if (status.breaching === true) {
    const rtnval2 = "Breaching";
    return rtnval2;
  }
  if (typeof status.achieved_ratio !== "number") {
    const rtnval2 = "No data in window";
    return rtnval2;
  }
  const rtnval = format_ratio(status.achieved_ratio) + " achieved";
  return rtnval;
}
function slo_problem_detail(body) {
  if (body === null || typeof body !== "object") {
    const rtnval2 = "";
    return rtnval2;
  }
  const detail = body.detail;
  const rtnval = typeof detail === "string" ? detail.trim() : "";
  return rtnval;
}
function slo_create_message_for_status(status, detail) {
  const reason = typeof detail === "string" ? detail.trim() : "";
  if (status === 201 || status === 200) {
    const rtnval2 = "SLO created.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "An SLO with that name already exists.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = reason.length > 0 ? "The SLO definition was rejected: " + reason : "The SLO definition was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown project.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to create SLOs.";
    return rtnval2;
  }
  const rtnval = "Failed to create SLO (HTTP " + String(status) + ").";
  return rtnval;
}
function slo_update_message_for_status(status, detail, name) {
  const reason = typeof detail === "string" ? detail.trim() : "";
  if (status === 200) {
    const rtnval2 = "SLO \u201C" + name + "\u201D saved.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "Another SLO already has that name.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = reason.length > 0 ? "The change was rejected: " + reason : "The change was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "That SLO no longer exists.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to edit SLOs.";
    return rtnval2;
  }
  const rtnval = "Failed to save the SLO (HTTP " + String(status) + ").";
  return rtnval;
}
function slo_delete_message_for_status(status, name) {
  if (status === 204 || status === 200) {
    const rtnval2 = "SLO \u201C" + name + "\u201D deleted.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "That SLO no longer exists.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to delete SLOs.";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to delete.";
    return rtnval2;
  }
  const rtnval = "Failed to delete the SLO (HTTP " + String(status) + ").";
  return rtnval;
}
function parse_definition_config(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = {};
    return rtnval2;
  }
  const parsed = JSON.parse(raw);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
    throw new SyntaxError("SLO definition_config must be a JSON object");
  }
  const rtnval = parsed;
  return rtnval;
}
function extract_slo_projects(body) {
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
class PycSlos extends HTMLElement {
  _state;
  _slos;
  _status;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _projects_notice_region;
  _root;
  _table_region;
  _create_region;
  _editing;
  _toast_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      loading: false,
      errored: false,
      errorStatus: 0,
      total: 0
    };
    this._slos = [];
    this._status = /* @__PURE__ */ new Map();
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._projects_notice_region = null;
    this._root = null;
    this._table_region = null;
    this._create_region = null;
    this._editing = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + list state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectId: this._state.projectId,
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
   * create action, table region, toast region.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.textContent = "Service-Level Objectives";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-metrics__controls");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-metrics__field");
    project_label.textContent = "Project";
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-metrics__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.addEventListener("change", () => {
      this._state.projectId = project_select.value;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    controls.appendChild(project_label);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-metrics__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectId = project_input.value.trim();
      void this._refresh();
    });
    controls.appendChild(project_input);
    const create_button = document.createElement("mj-button");
    create_button.classList.add("pyc-metrics__button");
    create_button.setAttribute("type", "button");
    create_button.setAttribute("data-role", "create-toggle");
    hide_unless_may(create_button, "system:slos.write");
    create_button.textContent = "Create SLO";
    create_button.addEventListener("click", () => {
      this._toggle_create_form();
    });
    controls.appendChild(create_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-metrics__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-metrics__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    const create_region = document.createElement("div");
    create_region.classList.add("pyc-metrics__form-region");
    create_region.setAttribute("data-role", "create-region");
    create_region.hidden = true;
    root.appendChild(create_region);
    this._create_region = create_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-metrics__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-metrics__table-region");
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
        projects = extract_slo_projects(body);
      } else {
        load_failed = true;
      }
    } catch (reason) {
      load_failed = true;
      console.warn(
        "pychestrate.ui.metrics.slo_projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (projects !== null && projects.length > 0) {
      this._projects = projects;
      this._projectsAvailable = true;
      this._projectsNoticeKind = "";
      this._state.projectId = choose_project_id(projects);
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
      region.classList.remove("pyc-metrics__projects-notice--error");
      show_no_projects(region, {});
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-metrics__projects-notice--error");
      region.textContent = "You don't have permission to list projects.";
      return;
    }
    region.classList.add("pyc-metrics__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-metrics__button");
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
   * Fetch the SLO list for the active project and re-render the
   * table. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._slos = [];
      this._render_table_region();
      return;
    }
    // The address describes what is on screen (ORC-27).
    mirror_to_query({ project_id: this._state.projectId });
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._status = /* @__PURE__ */ new Map();
    this._render_table_region();
    const url = build_slos_collection_url(this._state.projectId);
    let page = null;
    let error_status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        error_status = response.status;
        throw new Error(
          "slos fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.slos_fetch_failed",
        { reason: String(reason) }
      );
      if (error_status === 401) {
        announce_session_expired();
      }
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = error_status;
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
    this._slos = page.items;
    for (const slo of this._slos) {
      if (slo === null || typeof slo !== "object") {
        continue;
      }
      if (typeof slo.slo_id !== "string") {
        continue;
      }
      if (slo.status !== void 0 && slo.status !== null) {
        this._status.set(slo.slo_id, slo.status);
      }
    }
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
   * Re-render the table region from the current state + SLOs.
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
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view its SLOs.";
      region.replaceChildren(notice);
      return;
    }
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-metrics__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading SLOs\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-metrics__notice",
        "pyc-metrics__notice--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = list_load_message_for_status(
        this._state.errorStatus,
        "SLOs"
      );
      const children = [error];
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-metrics__button");
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
    if (this._slos.length === 0) {
      const empty = build_empty_state({ class_name: "pyc-metrics__notice", message: "No SLOs defined for this project yet.", next_step: "Choose Create SLO above to add one." });
      region.replaceChildren(empty);
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    return;
  }
  /**
   * Build the SLOs ``<table>`` from the current list.
   */
  _build_table() {
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-metrics__table");
    table.setAttribute("data-role", "slos-table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-metrics__row";
    table.rowAttrs = (slo) => ({ "data-slo-id": slo.slo_id });
    table.columns = [
      {
        key: "name",
        label: "SLO",
        width: "12rem",
        render: (slo) => {
          const name = document.createElement("span");
          name.textContent = slo.name;
          name.title = slo.slo_id;
          return name;
        }
      },
      {
        key: "kind",
        label: "Kind",
        width: "9rem",
        render: (slo) => slo.kind
      },
      {
        key: "target",
        label: "Target",
        width: "7rem",
        render: (slo) => format_ratio(slo.target)
      },
      {
        key: "window",
        label: "Window",
        width: "7rem",
        render: (slo) => format_window(slo.window_seconds)
      },
      {
        key: "burn",
        label: "Achieved",
        width: "10rem",
        render: (slo) => {
          const burn_badge = document.createElement("mj-chip");
          burn_badge.classList.add("pyc-metrics__badge");
          burn_badge.setAttribute("data-role", "burn-indicator");
          const status = self._status.get(slo.slo_id) ?? null;
          burn_badge.setAttribute("data-tone", slo_status_tone(status));
          if (status !== null && typeof status.reason === "string" && status.reason.length > 0) {
            burn_badge.setAttribute("title", status.reason);
          }
          burn_badge.textContent = slo_status_label(status);
          return burn_badge;
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "21rem",
        sortable: false,
        render: (slo) => {
          // Table cells render inside the table's shadow root, out of reach of
          // the bundle stylesheet, so the layout is set on the element itself.
          const actions = document.createElement("span");
          actions.classList.add("pyc-metrics__row-actions");
          actions.style.display = "inline-flex";
          actions.style.flexWrap = "wrap";
          actions.style.gap = "0.5rem";
          const status_button = document.createElement("mj-button");
          status_button.classList.add("pyc-metrics__button");
          status_button.setAttribute("type", "button");
          status_button.setAttribute("data-role", "load-status");
          status_button.textContent = "Refresh Status";
          status_button.addEventListener("click", () => {
            status_button.toggleAttribute("disabled", true);
            void self._on_load_status(slo, status_button);
          });
          actions.appendChild(status_button);
          const edit_button = document.createElement("mj-button");
          edit_button.classList.add("pyc-metrics__button");
          edit_button.setAttribute("type", "button");
          edit_button.setAttribute("data-role", "edit-slo");
          hide_unless_may(edit_button, "system:slos.write");
          edit_button.textContent = "Edit";
          edit_button.addEventListener("click", () => {
            self._open_edit_form(slo);
          });
          actions.appendChild(edit_button);
          const delete_button = document.createElement("mj-button");
          delete_button.classList.add("pyc-metrics__button");
          delete_button.setAttribute("type", "button");
          delete_button.setAttribute("data-role", "delete-slo");
          hide_unless_may(delete_button, "system:slos.write");
          delete_button.textContent = "Delete";
          delete_button.addEventListener("click", () => {
            void self._on_delete(slo, delete_button);
          });
          actions.appendChild(delete_button);
          return actions;
        }
      }
    ];
    table.rows = this._slos;
    return table;
  }
  /**
   * Delete one SLO after asking. The dialog names what goes with it (its
   * target and burn-rate state) and that it cannot be undone (ORC-26).
   *
   * @param slo The SLO to delete.
   * @param button The row action button, disabled while the request runs.
   */
  async _on_delete(slo, button) {
    const confirmed = await confirm_action(
      this,
      "Delete the SLO \u201C" + slo.name + "\u201D?\nIts target and its burn-rate state are removed. This cannot be undone.",
      "Delete SLO"
    );
    if (confirmed !== true) {
      return;
    }
    button.toggleAttribute("disabled", true);
    const outcome = await this._do_delete(slo);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true || outcome.status === 404) {
      this._status.delete(slo.slo_id);
      await this._refresh();
    }
    return;
  }
  /**
   * ``DELETE`` one SLO. Exposed so unit tests can drive it without a dialog.
   *
   * @param slo The SLO to delete.
   *
   * @returns ``{ok, status, message}``.
   */
  async deleteSlo(slo) {
    const rtnval = await this._do_delete(slo);
    return rtnval;
  }
  async _do_delete(slo) {
    if (this._state.projectId.length === 0) {
      return { ok: false, status: 0, message: "Select a project before deleting an SLO." };
    }
    let status = 0;
    try {
      const response = await fetch(build_slo_detail_url(this._state.projectId, slo.slo_id), {
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
        "pychestrate.ui.metrics.slo_delete_failed",
        { reason: String(reason) }
      );
      return { ok: false, status: 0, message: "Failed to reach the SLO service." };
    }
    const ok = status === 204 || status === 200;
    return { ok, status, message: slo_delete_message_for_status(status, slo.name) };
  }
  /**
   * Run the "Burn-rate Status" action for one SLO -- read the
   * status block and update the indicator, surfacing a toast.
   *
   * @param slo The SLO to evaluate.
   * @param button The row action button, re-enabled on completion.
   */
  async _on_load_status(slo, button) {
    const outcome = await this._do_load_status(slo.slo_id);
    if (outcome.ok === true && outcome.sloStatus !== null) {
      this._status.set(slo.slo_id, outcome.sloStatus);
      this._render_burn_cell(slo.slo_id);
    }
    button.toggleAttribute("disabled", false);
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    return;
  }
  /**
   * Read one SLO's burn-rate status. Exposed so unit tests can
   * drive a status read without a row button.
   *
   * @param slo_id The SLO to read.
   *
   * @returns The status outcome.
   */
  async loadStatus(slo_id) {
    const rtnval = await this._do_load_status(slo_id);
    return rtnval;
  }
  async _do_load_status(slo_id) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        sloStatus: null,
        message: "Select a project before reading SLO status."
      };
      return rtnval2;
    }
    let status = 0;
    let slo_status = null;
    try {
      const url = build_slo_detail_url(
        this._state.projectId,
        slo_id
      );
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        const detail = body;
        if (detail !== null && detail.status !== void 0 && detail.status !== null) {
          slo_status = detail.status;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.slo_status_fetch_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        sloStatus: null,
        message: "Failed to reach the SLO service."
      };
      return rtnval2;
    }
    if (status === 200) {
      const message = slo_status !== null ? "Burn-rate status updated." : "This SLO has no burn-rate status yet.";
      const rtnval2 = {
        ok: true,
        status,
        sloStatus: slo_status,
        message
      };
      return rtnval2;
    }
    const rtnval = {
      ok: false,
      status,
      sloStatus: null,
      message: "Failed to read SLO status (HTTP " + String(status) + ")."
    };
    return rtnval;
  }
  /**
   * Refresh one SLO's burn-rate indicator cell from the cached
   * status.
   *
   * @param slo_id The SLO whose row to update.
   */
  _render_burn_cell(slo_id) {
    if (this._table_region === null) {
      return;
    }
    const table = this._table_region.querySelector(
      '[data-role="slos-table"]'
    );
    if (table === null) {
      return;
    }
    const root = table.shadowRoot !== null && table.shadowRoot !== void 0 ? table.shadowRoot : table;
    const selector = '.row[data-slo-id="' + slo_id + '"] [data-role="burn-indicator"]';
    const badge = root.querySelector(selector);
    if (badge instanceof HTMLElement === false) {
      return;
    }
    const el = badge;
    const status = this._status.get(slo_id) ?? null;
    el.setAttribute("data-tone", slo_status_tone(status));
    el.textContent = slo_status_label(status);
    return;
  }
  /**
   * Toggle the inline create-SLO form's visibility, rendering it
   * on first reveal.
   */
  _toggle_create_form() {
    if (this._create_region === null) {
      return;
    }
    const region = this._create_region;
    if (region.hidden === true || this._editing !== null) {
      this._editing = null;
      this._render_create_form();
      region.hidden = false;
      reveal(region);
    } else {
      region.hidden = true;
    }
    return;
  }
  /**
   * Open the form on an existing SLO to change its name, target, window or
   * definition. The kind is shown but cannot change (a different kind is a
   * different objective: create a new SLO).
   *
   * @param slo The SLO row to edit.
   */
  _open_edit_form(slo) {
    if (this._create_region === null) {
      return;
    }
    this._editing = slo;
    this._render_create_form();
    this._create_region.hidden = false;
    reveal(this._create_region);
    return;
  }
  /**
   * Render the create-SLO form into the create region, or -- when an SLO is
   * being edited -- the same form filled in with that SLO's values.
   */
  _render_create_form() {
    if (this._create_region === null) {
      return;
    }
    const editing = this._editing;
    const prefix = editing === null ? "create" : "edit";
    const form = document.createElement("form");
    form.classList.add("pyc-metrics__form");
    form.setAttribute("data-role", prefix + "-form");
    if (editing !== null) {
      const heading = document.createElement("h3");
      heading.classList.add("pyc-metrics__form-heading");
      heading.setAttribute("data-role", "edit-heading");
      heading.textContent = "Edit the SLO \u201C" + editing.name + "\u201D";
      form.appendChild(heading);
    }
    const name_input = this._build_text_field(
      form,
      "Name",
      prefix + "-name",
      "checkout availability"
    );
    const kind_input = this._build_text_field(
      form,
      "Kind",
      prefix + "-kind",
      DEFAULT_SLO_KIND
    );
    kind_input.value = editing === null ? DEFAULT_SLO_KIND : editing.kind;
    kind_input.setAttribute(
      "help-text",
      editing === null ? "availability_ratio: achieved = good / total over the window." : "The kind cannot be changed; create a new SLO for a different kind."
    );
    if (editing !== null) {
      kind_input.toggleAttribute("disabled", true);
    }
    const target_input = this._build_text_field(
      form,
      "Target ratio (0..1)",
      prefix + "-target",
      "0.995"
    );
    const window_input = this._build_text_field(
      form,
      "Window (seconds)",
      prefix + "-window",
      "604800"
    );
    const config_label = document.createElement("label");
    config_label.classList.add("pyc-metrics__field");
    config_label.textContent = "Definition config (JSON)";
    const config_area = document.createElement("mj-textarea");
    config_area.classList.add("pyc-metrics__input");
    config_area.setAttribute("data-role", prefix + "-config");
    config_area.setAttribute("placeholder", SLO_CONFIG_EXAMPLE);
    config_area.setAttribute(
      "help-text",
      "good_metric_name and total_metric_name are counters from the metric catalog; label_filter (optional) narrows both. Series are scoped to this project."
    );
    config_area.rows = 3;
    config_label.appendChild(config_area);
    form.appendChild(config_label);
    const submit_button = document.createElement("mj-button");
    submit_button.classList.add("pyc-metrics__button");
    submit_button.setAttribute("type", "submit");
    submit_button.setAttribute("data-role", prefix + "-submit");
    submit_button.textContent = editing === null ? "Create SLO" : "Save changes";
    form.appendChild(submit_button);
    if (editing !== null) {
      const cancel_button = document.createElement("mj-button");
      cancel_button.classList.add("pyc-metrics__button");
      cancel_button.setAttribute("type", "button");
      cancel_button.setAttribute("data-role", "edit-cancel");
      cancel_button.textContent = "Cancel";
      cancel_button.addEventListener("click", () => {
        this._editing = null;
        if (this._create_region !== null) {
          this._create_region.hidden = true;
        }
      });
      form.appendChild(cancel_button);
    }
    const status = document.createElement("p");
    status.classList.add("pyc-metrics__form-status");
    status.setAttribute("data-role", prefix + "-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_create(
        form,
        name_input,
        kind_input,
        target_input,
        window_input,
        config_area,
        submit_button
      );
    });
    this._create_region.replaceChildren(form);
    if (editing !== null) {
      // Filled in once the form is in the page: the inputs draw their value when they connect.
      name_input.value = editing.name;
      target_input.value = String(editing.target);
      window_input.value = String(editing.window_seconds);
      config_area.value = JSON.stringify(editing.definition_config ?? {}, null, 2);
    }
    return;
  }
  /**
   * Build a labelled text input, append it to the supplied form,
   * and return the input element.
   *
   * @param form The form to append the field to.
   * @param label_text The visible field label.
   * @param role The ``data-role`` value for test selection.
   * @param placeholder The input placeholder text.
   *
   * @returns The created input element.
   */
  _build_text_field(form, label_text, role, placeholder) {
    const label = document.createElement("label");
    label.classList.add("pyc-metrics__field");
    label.textContent = label_text;
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-metrics__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", role);
    input.setAttribute("placeholder", placeholder);
    label.appendChild(input);
    form.appendChild(label);
    return input;
  }
  async _submit_create(form, name_input, kind_input, target_input, window_input, config_area, submit_button) {
    const editing = this._editing;
    const status = form.querySelector('[data-role="' + (editing === null ? "create" : "edit") + '-status"]');
    const name = name_input.value.trim();
    const kind = kind_input.value.trim();
    if (name.length === 0 || kind.length === 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "SLO name and kind are required.";
      }
      return;
    }
    const target = Number(target_input.value.trim());
    if (Number.isNaN(target) === true) {
      if (status instanceof HTMLElement) {
        status.textContent = "Target ratio must be a number.";
      }
      return;
    }
    const window_seconds = Number(window_input.value.trim());
    if (Number.isNaN(window_seconds) === true || window_seconds <= 0) {
      if (status instanceof HTMLElement) {
        status.textContent = "Window seconds must be a positive number.";
      }
      return;
    }
    let definition_config = {};
    try {
      definition_config = parse_definition_config(config_area.value);
    } catch (reason) {
      if (status instanceof HTMLElement) {
        status.textContent = "Definition config must be valid JSON.";
      }
      console.warn(
        "pychestrate.ui.metrics.slo_config_invalid",
        { reason: String(reason) }
      );
      return;
    }
    submit_button.toggleAttribute("disabled", true);
    if (status instanceof HTMLElement) {
      status.textContent = editing === null ? "Creating SLO\u2026" : "Saving SLO\u2026";
    }
    const outcome = editing === null ? await this._do_create(
      name,
      kind,
      target,
      window_seconds,
      definition_config
    ) : await this._do_update(editing, name, target, window_seconds, definition_config);
    submit_button.toggleAttribute("disabled", false);
    if (status instanceof HTMLElement) {
      status.textContent = "";
    }
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      if (editing !== null) {
        // The target or window may have changed, so the status shown for it is stale.
        this._status.delete(editing.slo_id);
        this._editing = null;
        if (this._create_region !== null) {
          this._create_region.hidden = true;
        }
      }
      await this._refresh();
    }
    return;
  }
  /**
   * POST an ``SloCreateRequest``. Exposed so unit tests can
   * invoke a create without a real form-submit event.
   *
   * @param name Human-facing SLO name.
   * @param kind SLO kind (e.g. ``availability_ratio``).
   * @param target Target ratio in the 0..1 range.
   * @param window_seconds Rolling evaluation window length.
   * @param definition_config Kind-specific configuration object.
   *
   * @returns The create outcome.
   */
  async createSlo(name, kind, target, window_seconds, definition_config) {
    const rtnval = await this._do_create(
      name,
      kind,
      target,
      window_seconds,
      definition_config
    );
    return rtnval;
  }
  /**
   * ``PUT`` an edited SLO (the create body; its kind cannot change). Exposed so
   * unit tests can drive an edit without a form-submit event.
   *
   * @param slo The SLO being edited.
   * @param name The new name.
   * @param target The new target ratio.
   * @param window_seconds The new window.
   * @param definition_config The new kind-specific configuration.
   *
   * @returns ``{ok, status, sloId, message}``.
   */
  async updateSlo(slo, name, target, window_seconds, definition_config) {
    const rtnval = await this._do_update(slo, name, target, window_seconds, definition_config);
    return rtnval;
  }
  async _do_update(slo, name, target, window_seconds, definition_config) {
    if (this._state.projectId.length === 0) {
      return { ok: false, status: 0, sloId: slo.slo_id, message: "Select a project before editing an SLO." };
    }
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(build_slo_detail_url(this._state.projectId, slo.slo_id), {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ name, kind: slo.kind, target, window_seconds, definition_config })
      });
      status = response.status;
      if (status === 401) {
        announce_session_expired();
      }
      if (response.ok !== true) {
        try {
          detail = slo_problem_detail(await response.json());
        } catch (parse_reason) {
          detail = "";
        }
      }
    } catch (reason) {
      console.warn("pychestrate.ui.metrics.slo_update_failed", { reason: String(reason) });
      return { ok: false, status: 0, sloId: slo.slo_id, message: "Failed to reach the SLO service." };
    }
    return {
      ok: status === 200,
      status,
      sloId: slo.slo_id,
      message: slo_update_message_for_status(status, detail, name)
    };
  }
  async _do_create(name, kind, target, window_seconds, definition_config) {
    if (this._state.projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        sloId: "",
        message: "Select a project before creating an SLO."
      };
      return rtnval2;
    }
    const payload = {
      name,
      kind,
      target,
      window_seconds,
      definition_config
    };
    let status = 0;
    let slo_id = "";
    let detail = "";
    try {
      const url = build_slos_collection_url(this._state.projectId);
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
        const slo = body;
        if (slo !== null && typeof slo.slo_id === "string") {
          slo_id = slo.slo_id;
        }
      } else {
        try {
          detail = slo_problem_detail(await response.json());
        } catch (parse_reason) {
          detail = "";
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.slo_create_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        sloId: "",
        message: "Failed to reach the SLO service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      sloId: slo_id,
      message: slo_create_message_for_status(status, detail)
    };
    return rtnval;
  }
  /**
   * Show a toast in the toast region through the shared service: one at a
   * time, announced to assistive technology, a plain success goes away by itself.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-metrics" });
    return;
  }
}
export {
  DEFAULT_SLO_KIND,
  PycSlos,
  SLO_CONFIG_EXAMPLE,
  build_slo_detail_url,
  build_slos_collection_url,
  extract_slo_projects,
  format_ratio,
  format_window,
  parse_definition_config,
  slo_create_message_for_status,
  slo_delete_message_for_status,
  slo_problem_detail,
  slo_status_label,
  slo_status_tone,
  slo_update_message_for_status
};
