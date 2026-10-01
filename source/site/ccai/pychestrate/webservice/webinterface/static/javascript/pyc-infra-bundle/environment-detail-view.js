import { show_toast } from "../shared/toast.js";
import { keep_list_state_on_back } from "../shared/view-state.js";
import { state_label } from "../shared/run-labels.js";
import { set_entity_title } from "../shared/page-title.js";
import {
  ENVIRONMENTS_ROUTE,
  build_drift_check_url,
  build_drift_status_url,
  drift_status_label,
  drift_status_tone,
  environment_state_tone,
  format_timestamp
} from "./environments-view.js";
const PROJECTS_API_PATH = "/api/v1/projects";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DRIFT_SECTION_HEADING = "Drift detection (preview)";
function environment_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = ENVIRONMENTS_ROUTE + "/";
  if (path.startsWith(prefix) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  let tail = path.slice(prefix.length);
  const query_index = tail.indexOf("?");
  if (query_index >= 0) {
    tail = tail.slice(0, query_index);
  }
  if (tail.endsWith("/") === true) {
    tail = tail.slice(0, tail.length - 1);
  }
  if (UUID_PATTERN.test(tail) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = tail;
  return rtnval;
}
function environment_project_from_search(search) {
  if (typeof search !== "string" || search.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const params = new URLSearchParams(search);
  const value = params.get("project_id");
  const rtnval = value === null ? "" : value;
  return rtnval;
}
function build_environment_detail_url(project_id, environment_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/environments/" + encodeURIComponent(environment_id);
  return rtnval;
}
function describe_drift_counts(run) {
  if (run === null || run === void 0) {
    const rtnval2 = "—";
    return rtnval2;
  }
  if (typeof run.drift_count !== "number") {
    const rtnval2 = "—";
    return rtnval2;
  }
  const parts = [String(run.drift_count) + " drifted"];
  if (typeof run.added === "number") {
    parts.push("+" + String(run.added));
  }
  if (typeof run.changed === "number") {
    parts.push("~" + String(run.changed));
  }
  if (typeof run.destroyed === "number") {
    parts.push("-" + String(run.destroyed));
  }
  const rtnval = parts.join(" ");
  return rtnval;
}
function drift_check_detail_message(status, detail) {
  const reason = typeof detail === "string" ? detail.trim() : "";
  if (status === 202 || status === 200) {
    const rtnval2 = "Drift check recorded. Nothing processes it yet, so it stays pending.";
    return rtnval2;
  }
  if (reason.length > 0) {
    const rtnval2 = reason;
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to check drift.";
    return rtnval2;
  }
  const rtnval = "Failed to check drift (HTTP " + String(status) + ").";
  return rtnval;
}
class PycEnvironmentDetail extends HTMLElement {
  _environment_id;
  _project_id;
  _environment;
  _drift;
  _loading;
  _errored;
  _root;
  _body;
  _toast_region;
  constructor() {
    super();
    this._environment_id = "";
    this._project_id = "";
    this._environment = null;
    this._drift = null;
    this._loading = false;
    this._errored = false;
    this._root = null;
    this._body = null;
    this._toast_region = null;
  }
  /**
   * Observed attributes -- ``environment-id`` and ``project-id``
   * may be supplied by a host; otherwise they are read from the URL
   * (``/environments/{id}?project_id=...``) on mount.
   */
  static get observedAttributes() {
    const rtnval = ["environment-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests.
   */
  get detailState() {
    const rtnval = {
      environmentId: this._environment_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored
    };
    return rtnval;
  }
  connectedCallback() {
    const attr_environment = this.getAttribute("environment-id");
    this._environment_id = attr_environment !== null && attr_environment.length > 0 ? attr_environment : environment_id_from_path(window.location.pathname);
    const attr_project = this.getAttribute("project-id");
    this._project_id = attr_project !== null && attr_project.length > 0 ? attr_project : environment_project_from_search(window.location.search);
    this._render_chrome();
    void this._load();
    return;
  }
  /**
   * Fetch the environment and its drift status, then render.
   * Exposed so unit tests can await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (this._environment_id.length === 0 || this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const environment = await this._fetch_json(
      build_environment_detail_url(this._project_id, this._environment_id)
    );
    const drift = await this._fetch_json(
      build_drift_status_url(this._project_id, this._environment_id)
    );
    this._environment = environment;
    this._drift = drift;
    this._loading = false;
    this._errored = environment === null;
    this._render_body();
    return;
  }
  async _fetch_json(url) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error("fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      const rtnval = body !== null && typeof body === "object" ? body : null;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.environment_detail_fetch_failed",
        { url, reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-infra");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-infra__heading");
    heading.setAttribute("data-role", "environment-heading");
    heading.textContent = "Environment";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-infra__back-link");
    back.setAttribute("href", this._project_id.length > 0 ? ENVIRONMENTS_ROUTE + "?project_id=" + encodeURIComponent(this._project_id) : ENVIRONMENTS_ROUTE);
    back.setAttribute("data-role", "back-link");
    keep_list_state_on_back(back, ENVIRONMENTS_ROUTE);
    back.textContent = "← All environments";
    root.appendChild(back);
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-infra__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const body = document.createElement("div");
    body.classList.add("pyc-infra__detail-body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._body = body;
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  _render_body() {
    if (this._body === null) {
      return;
    }
    const body = this._body;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-infra__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading environment…";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._environment === null) {
      const error = document.createElement("p");
      error.classList.add("pyc-infra__status", "pyc-infra__status--error");
      error.setAttribute("data-role", "error-state");
      error.textContent = this._environment_id.length === 0 || this._project_id.length === 0 ? "Open an environment from the Environments list." : "Failed to load this environment. Try refreshing.";
      body.replaceChildren(error);
      return;
    }
    const environment = this._environment;
    const heading = this._root !== null ? this._root.querySelector('[data-role="environment-heading"]') : null;
    if (heading instanceof HTMLElement) {
      heading.textContent = "Environment — " + String(environment.name ?? "");
      set_entity_title(String(environment.name ?? "") || "Environment");
    }
    body.replaceChildren(
      this._summary(environment),
      this._drift_section()
    );
    return;
  }
  _summary(environment) {
    const section = document.createElement("section");
    section.classList.add("pyc-infra__section");
    section.setAttribute("aria-label", "Environment summary");
    const grid = document.createElement("dl");
    grid.classList.add("pyc-infra__detail-grid");
    grid.setAttribute("data-role", "environment-summary");
    this._append_field(grid, "Kind", environment.kind_name);
    const state_badge = document.createElement("mj-chip");
    state_badge.classList.add("pyc-infra__badge");
    state_badge.setAttribute("data-tone", environment_state_tone(environment.state));
    state_badge.textContent = environment.state;
    this._append_field(grid, "State", state_badge);
    this._append_field(grid, "Last applied", format_timestamp(environment.last_applied_at));
    this._append_field(grid, "Registered", format_timestamp(environment.created_at));
    if (typeof environment.frozen_reason === "string" && environment.frozen_reason.length > 0) {
      this._append_field(grid, "Frozen because", environment.frozen_reason);
    }
    if (typeof environment.archived_reason === "string" && environment.archived_reason.length > 0) {
      this._append_field(grid, "Archived because", environment.archived_reason);
    }
    this._append_field(grid, "Environment id", environment.environment_id);
    section.appendChild(grid);
    const attrs_heading = document.createElement("h2");
    attrs_heading.classList.add("pyc-infra__section-heading");
    attrs_heading.textContent = "Attributes";
    section.appendChild(attrs_heading);
    const attrs = document.createElement("pre");
    attrs.classList.add("pyc-infra__attrs");
    attrs.setAttribute("data-role", "environment-attrs");
    attrs.textContent = JSON.stringify(environment.attrs ?? {}, null, 2);
    section.appendChild(attrs);
    return section;
  }
  _drift_section() {
    const section = document.createElement("section");
    section.classList.add("pyc-infra__section");
    section.setAttribute("aria-label", "Drift detection");
    section.setAttribute("data-role", "drift-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-infra__section-heading");
    heading.textContent = DRIFT_SECTION_HEADING;
    section.appendChild(heading);
    const drift = this._drift;
    const preview = document.createElement("p");
    preview.classList.add("pyc-infra__notice", "pyc-infra__notice--preview");
    preview.setAttribute("data-role", "drift-preview-notice");
    preview.setAttribute("role", "note");
    preview.textContent = drift !== null && typeof drift.detail === "string" ? drift.detail : "Drift detection is a preview: recorded checks are not processed yet.";
    section.appendChild(preview);
    const status_line = document.createElement("p");
    status_line.classList.add("pyc-infra__drift-status");
    const status_badge = document.createElement("span");
    status_badge.classList.add("pyc-infra__badge", "pyc-infra__drift");
    status_badge.setAttribute("data-role", "drift-indicator");
    status_badge.setAttribute("data-tone", drift_status_tone(drift));
    status_badge.textContent = drift_status_label(drift);
    status_line.append("Latest check: ", status_badge);
    section.appendChild(status_line);
    const schedule = drift !== null && drift.schedule !== null && typeof drift.schedule === "object" ? drift.schedule : null;
    const schedule_line = document.createElement("p");
    schedule_line.classList.add("pyc-infra__field-caption");
    schedule_line.setAttribute("data-role", "drift-schedule");
    schedule_line.textContent = schedule !== null ? "Schedule: " + String(schedule.checker_name) + " (" + String(schedule.cron_expression) + ")" + (schedule.enabled === true ? "" : ", disabled") : "Schedule: none";
    section.appendChild(schedule_line);
    const check_available = drift !== null && drift.check_available === true;
    const check_button = document.createElement("mj-button");
    check_button.classList.add("pyc-infra__button");
    check_button.setAttribute("type", "button");
    check_button.setAttribute("data-role", "check-drift");
    check_button.textContent = "Check Drift";
    check_button.toggleAttribute("disabled", check_available === false);
    check_button.addEventListener("click", () => {
      if (check_available === false) {
        return;
      }
      check_button.toggleAttribute("disabled", true);
      void this._on_check_drift(check_button);
    });
    section.appendChild(check_button);
    if (check_available === false) {
      const reason = document.createElement("p");
      reason.classList.add("pyc-infra__field-caption");
      reason.setAttribute("data-role", "check-unavailable-reason");
      reason.textContent = drift !== null && typeof drift.check_unavailable_reason === "string" ? drift.check_unavailable_reason : "A drift check cannot start for this environment.";
      section.appendChild(reason);
    }
    section.appendChild(this._history(drift));
    return section;
  }
  _history(drift) {
    const history = drift !== null && Array.isArray(drift.history) === true ? drift.history : [];
    const wrapper = document.createElement("div");
    wrapper.classList.add("pyc-infra__table-region");
    wrapper.setAttribute("data-role", "drift-history");
    const heading = document.createElement("h3");
    heading.classList.add("pyc-infra__section-heading");
    heading.textContent = "Drift history";
    wrapper.appendChild(heading);
    if (history.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-infra__status");
      empty.setAttribute("data-role", "drift-history-empty");
      empty.textContent = "No drift checks recorded for this environment.";
      wrapper.appendChild(empty);
      return wrapper;
    }
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-infra__table");
    table.setAttribute("data-role", "drift-history-table");
    table.rowAttrs = (run) => ({ "data-run-id": run.run_id });
    table.columns = [
      {
        key: "scheduled_for",
        label: "Requested",
        width: "12rem",
        render: (run) => format_timestamp(run.scheduled_for)
      },
      { key: "trigger_kind", label: "Trigger", width: "8rem" },
      {
        key: "state",
        label: "State",
        width: "9rem",
        render: (run) => {
          const badge = document.createElement("span");
          badge.classList.add("pyc-infra__badge");
          badge.setAttribute("data-role", "drift-run-state");
          badge.textContent = state_label(run.state);
          return badge;
        }
      },
      {
        key: "drift_count",
        label: "Drift",
        width: "10rem",
        sortable: false,
        render: (run) => describe_drift_counts(run)
      },
      { key: "checker_name", label: "Checker", width: "9rem" },
      {
        key: "final_state_reason",
        label: "Detail",
        width: "16rem",
        sortable: false,
        render: (run) => typeof run.final_state_reason === "string" && run.final_state_reason.length > 0 ? run.final_state_reason : "—"
      }
    ];
    table.rows = history;
    wrapper.appendChild(table);
    return wrapper;
  }
  async _on_check_drift(button) {
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(
        build_drift_check_url(this._project_id, this._environment_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        }
      );
      status = response.status;
      try {
        const body = await response.json();
        if (body !== null && typeof body === "object" && typeof body.detail === "string" && response.ok === false) {
          detail = body.detail;
        }
      } catch (parse_reason) {
        detail = "";
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.infra.environment_drift_check_failed",
        { reason: String(reason) }
      );
    }
    button.toggleAttribute("disabled", false);
    const ok = status === 202 || status === 200;
    this._show_toast(drift_check_detail_message(status, detail), ok === true ? "ok" : "error");
    if (ok === true) {
      await this._load();
    }
    return;
  }
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-infra__detail-field");
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    if (value instanceof HTMLElement) {
      detail.appendChild(value);
    } else {
      detail.textContent = value === null || value === void 0 || String(value).length === 0 ? "—" : String(value);
    }
    field.appendChild(term);
    field.appendChild(detail);
    grid.appendChild(field);
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
  DRIFT_SECTION_HEADING,
  PycEnvironmentDetail,
  build_environment_detail_url,
  describe_drift_counts,
  drift_check_detail_message,
  environment_id_from_path,
  environment_project_from_search
};
