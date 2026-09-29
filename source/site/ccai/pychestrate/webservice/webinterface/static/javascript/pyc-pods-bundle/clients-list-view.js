import { format_clock_instant, format_instant, parse_timestamp } from "../shared/datetime.js";
import {
  announce_session_expired,
  format_clock_time,
  load_projects
} from "./pods-list-view.js";
const CLIENT_STATUSES = [
  "ACTIVE",
  "SUSPENDED",
  "REVOKED"
];
const LIVENESS_STATES = [
  "ALIVE",
  "DEGRADED",
  "LOST"
];
const DEFAULT_PER_PAGE = 25;
const CLIENTS_API_PATH = "/api/v1/clients";
const CLIENTS_POLL_INTERVAL_MS = 15e3;
const CAPABILITY_TAG_DISPLAY_LIMIT = 6;
const TOAST_STACK_LIMIT = 3;
function build_clients_query_url(state) {
  const params = new URLSearchParams();
  if (state.projectFilter.length > 0) {
    params.set("project_id", state.projectFilter);
  }
  if (state.statusFilter.length > 0) {
    params.set("status", state.statusFilter);
  }
  if (state.livenessFilter.length > 0) {
    params.set("liveness_state", state.livenessFilter);
  }
  const query = params.toString();
  if (query.length === 0) {
    const rtnval2 = CLIENTS_API_PATH;
    return rtnval2;
  }
  const rtnval = CLIENTS_API_PATH + "?" + query;
  return rtnval;
}
function build_client_detail_url(client_id) {
  const rtnval = CLIENTS_API_PATH + "/" + encodeURIComponent(client_id);
  return rtnval;
}
function build_client_revoke_url(client_id) {
  const rtnval = build_client_detail_url(client_id) + "/revoke";
  return rtnval;
}
function build_client_capabilities_url(client_id) {
  const rtnval = build_client_detail_url(client_id) + "/capabilities";
  return rtnval;
}
function short_id(client_id) {
  if (typeof client_id !== "string" || client_id.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const dash_index = client_id.indexOf("-");
  if (dash_index <= 0) {
    const rtnval2 = client_id;
    return rtnval2;
  }
  const rtnval = client_id.slice(0, dash_index);
  return rtnval;
}
function format_timestamp(value) {
  if (value === null || value === void 0 || value.length === 0) {
    const rtnval2 = "—";
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
function status_tone(status) {
  if (status === "ACTIVE") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (status === "SUSPENDED") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (status === "REVOKED") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function liveness_tone(liveness) {
  if (liveness === "ALIVE") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (liveness === "DEGRADED") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (liveness === "LOST") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
// What the liveness chip says (RES-36). The heartbeat watchdog keeps
// liveness_state honest (ALIVE / DEGRADED after 90 s of silence / LOST
// after 5 min), and two cases read better than the raw state: a client
// that never heartbeated, and a revoked client, which is not expected
// to heartbeat at all.
function client_liveness_display(client) {
  if (client === null || client === void 0) {
    const rtnval2 = { label: "\u2014", tone: "neutral" };
    return rtnval2;
  }
  if (client.status === "REVOKED") {
    const rtnval2 = { label: "\u2014", tone: "neutral" };
    return rtnval2;
  }
  const tone = liveness_tone(client.liveness_state);
  if (client.last_seen === null || client.last_seen === void 0 || client.last_seen === "") {
    const rtnval2 = { label: "Never seen", tone: tone === "ok" ? "neutral" : tone };
    return rtnval2;
  }
  const labels = { ALIVE: "Alive", DEGRADED: "Stale", LOST: "Lost" };
  const label = labels[client.liveness_state] || String(client.liveness_state || "\u2014");
  const rtnval = { label, tone };
  return rtnval;
}
function capability_tags(attributes) {
  const rtnval = [];
  if (attributes === null || attributes === void 0) {
    return rtnval;
  }
  const keys = Object.keys(attributes);
  for (const key of keys) {
    const value = attributes[key];
    if (Array.isArray(value) === true) {
      for (const entry of value) {
        if (typeof entry === "string" && entry.length > 0) {
          rtnval.push(key + ":" + entry);
        }
      }
      continue;
    }
    if (typeof value === "string" && value.length > 0) {
      rtnval.push(key + ":" + value);
      continue;
    }
    if (typeof value === "number" || typeof value === "boolean") {
      rtnval.push(key + ":" + String(value));
    }
  }
  return rtnval;
}
/**
 * Flatten the capabilities a pod advertised (the rows of
 * ``GET /api/v1/clients/{id}/capabilities``) into the tags dispatch
 * matches a job type's required capabilities against -- the rule of
 * ``orchestration.rpa.candidates.capability_tags_for_client``: every
 * capability ``kind``, plus for the ``rpa`` kind one
 * ``rpa:<job type>`` tag per advertised job type and the pod's
 * free-form ``tags``.
 */
function advertised_capability_tags(capabilities) {
  const rtnval = [];
  if (Array.isArray(capabilities) === false) {
    return rtnval;
  }
  const add_tag = (tag) => {
    if (tag.length > 0 && rtnval.includes(tag) === false) {
      rtnval.push(tag);
    }
  };
  for (const capability of capabilities) {
    if (capability === null || typeof capability !== "object") {
      continue;
    }
    const kind = capability.kind;
    if (typeof kind !== "string" || kind.length === 0) {
      continue;
    }
    add_tag(kind);
    const value = capability.value;
    if (kind !== "rpa" || value === null || typeof value !== "object") {
      continue;
    }
    const job_types = Array.isArray(value.job_types) === true ? value.job_types : [];
    for (const job_type of job_types) {
      const name = String(job_type);
      if (name.length > 0) {
        add_tag("rpa:" + name);
      }
    }
    const tags = Array.isArray(value.tags) === true ? value.tags : [];
    for (const tag of tags) {
      add_tag(String(tag));
    }
  }
  return rtnval;
}
/**
 * Latest ``updated_at`` among advertised capability rows, or ``""``
 * when none carries one.
 */
function latest_capability_update(capabilities) {
  let rtnval = "";
  if (Array.isArray(capabilities) === false) {
    return rtnval;
  }
  for (const capability of capabilities) {
    if (capability === null || typeof capability !== "object") {
      continue;
    }
    const updated_at = capability.updated_at;
    if (typeof updated_at === "string" && updated_at > rtnval) {
      rtnval = updated_at;
    }
  }
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
function clients_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired — sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to clients.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service — check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load clients (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function revoke_message_for_status(status) {
  if (status === 200) {
    const rtnval2 = "Client revoked.";
    return rtnval2;
  }
  if (status === 400) {
    const rtnval2 = "The revoke request was rejected (HTTP 400).";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired — sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to revoke clients.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "No client with this id — it may already be gone.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service — check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to revoke client (HTTP " + String(status) + ").";
  return rtnval;
}
/**
 * POST an admin revoke for one client. The revoke route requires
 * a documented reason; operator-initiated revokes from the fleet
 * UI carry ``ADMIN_REQUEST``.
 *
 * @param client_id The client to revoke.
 *
 * @returns ``{ok, status, message}`` -- ``status`` is 0 on a
 *          network error.
 */
async function perform_client_revoke(client_id) {
  let status = 0;
  try {
    const response = await fetch(build_client_revoke_url(client_id), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        reason: "ADMIN_REQUEST",
        note: "Revoked from the fleet UI"
      })
    });
    status = response.status;
  } catch (reason) {
    console.warn(
      "pychestrate.ui.clients.revoke_failed",
      { reason: String(reason) }
    );
  }
  if (status === 401) {
    announce_session_expired();
  }
  const ok = status === 200;
  const rtnval = {
    ok,
    status,
    message: revoke_message_for_status(status)
  };
  return rtnval;
}
class PycClientsList extends HTMLElement {
  _pager;
  _state;
  _clients;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _root;
  _table_region;
  _projects_notice_region;
  _stamp_region;
  _toast_region;
  _poll_timer;
  _on_visibility_change;
  constructor() {
    super();
    this._state = {
      projectFilter: "",
      statusFilter: "",
      livenessFilter: "",
      page: 1,
      perPage: DEFAULT_PER_PAGE,
      total: 0,
      loading: false,
      errored: false,
      errorStatus: 0
    };
    this._clients = [];
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._root = null;
    this._table_region = null;
    this._projects_notice_region = null;
    this._stamp_region = null;
    this._toast_region = null;
    this._pager = null;
    this._poll_timer = null;
    this._on_visibility_change = () => {
      this._handle_visibility_change();
    };
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * filter + pagination state without scraping the DOM.
   */
  get listState() {
    const rtnval = {
      projectFilter: this._state.projectFilter,
      statusFilter: this._state.statusFilter,
      livenessFilter: this._state.livenessFilter,
      page: this._state.page,
      perPage: this._state.perPage,
      total: this._state.total,
      loading: this._state.loading,
      errored: this._state.errored,
      errorStatus: this._state.errorStatus,
      polling: this._poll_timer !== null
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome, load the projects
   * picker (which kicks off the first clients fetch), and start
   * the liveness poll loop.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_projects();
    this._start_poll();
    if (typeof document !== "undefined") {
      document.addEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  /**
   * Lifecycle hook -- stop the poll timer and drop the visibility
   * listener so a navigation away never leaks either.
   */
  disconnectedCallback() {
    this._stop_poll();
    if (typeof document !== "undefined") {
      document.removeEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  _start_poll() {
    if (this._poll_timer !== null) {
      return;
    }
    this._schedule_poll();
    return;
  }
  _schedule_poll() {
    const timer = setTimeout(() => {
      this._poll_timer = null;
      void this._poll_once();
    }, CLIENTS_POLL_INTERVAL_MS);
    const handle = timer;
    if (typeof handle.unref === "function") {
      handle.unref();
    }
    this._poll_timer = timer;
    return;
  }
  /**
   * Run one poll cycle. Exposed so unit tests can drive a cycle
   * without waiting on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    if (typeof document !== "undefined" && document.hidden === true) {
      // The visibility handler restarts the loop when the tab
      // becomes visible again.
      return;
    }
    await this._refresh();
    this._schedule_poll();
    return;
  }
  _stop_poll() {
    if (this._poll_timer !== null) {
      clearTimeout(this._poll_timer);
      this._poll_timer = null;
    }
    return;
  }
  _handle_visibility_change() {
    if (typeof document === "undefined") {
      return;
    }
    if (document.hidden === true) {
      this._stop_poll();
      return;
    }
    if (this._poll_timer === null) {
      void this._refresh();
      this._schedule_poll();
    }
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-clients-list");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-clients-list__heading");
    heading.textContent = "Clients";
    root.appendChild(heading);
    const subtitle = document.createElement("p");
    subtitle.classList.add("pyc-clients-list__subtitle");
    subtitle.textContent = "Enrolled client runtimes. Each client backs the pod it registers under.";
    root.appendChild(subtitle);
    const filters = document.createElement("div");
    filters.classList.add("pyc-clients-list__filters");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-clients-list__filter");
    project_label.textContent = "Project";
    const project_select = document.createElement("mj-select");
    project_select.classList.add("pyc-clients-list__select");
    project_select.setAttribute("data-role", "project-select");
    project_select.hidden = true;
    project_select.addEventListener("change", () => {
      this._state.projectFilter = project_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_select);
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-clients-list__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-filter");
    project_input.hidden = true;
    project_input.addEventListener("change", () => {
      this._state.projectFilter = project_input.value.trim();
      this._state.page = 1;
      void this._refresh();
    });
    project_label.appendChild(project_input);
    filters.appendChild(project_label);
    const status_label = document.createElement("label");
    status_label.classList.add("pyc-clients-list__filter");
    status_label.textContent = "Status";
    const status_select = document.createElement("mj-select");
    status_select.classList.add("pyc-clients-list__select");
    status_select.setAttribute("data-role", "status-filter");
    const any_status = document.createElement("mj-option");
    any_status.setAttribute("value", "");
    any_status.textContent = "All statuses";
    status_select.appendChild(any_status);
    for (const status of CLIENT_STATUSES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", status);
      option.textContent = status;
      status_select.appendChild(option);
    }
    status_select.addEventListener("change", () => {
      this._state.statusFilter = status_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    status_label.appendChild(status_select);
    filters.appendChild(status_label);
    const liveness_label = document.createElement("label");
    liveness_label.classList.add("pyc-clients-list__filter");
    liveness_label.textContent = "Liveness";
    const liveness_select = document.createElement("mj-select");
    liveness_select.classList.add("pyc-clients-list__select");
    liveness_select.setAttribute("data-role", "liveness-filter");
    const any_liveness = document.createElement("mj-option");
    any_liveness.setAttribute("value", "");
    any_liveness.textContent = "All liveness";
    liveness_select.appendChild(any_liveness);
    for (const liveness of LIVENESS_STATES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", liveness);
      option.textContent = liveness;
      liveness_select.appendChild(option);
    }
    liveness_select.addEventListener("change", () => {
      this._state.livenessFilter = liveness_select.value;
      this._state.page = 1;
      void this._refresh();
    });
    liveness_label.appendChild(liveness_select);
    filters.appendChild(liveness_label);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-clients-list__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    filters.appendChild(refresh_button);
    const stamp = document.createElement("span");
    stamp.classList.add("pyc-clients-list__stamp");
    stamp.setAttribute("data-role", "last-updated");
    filters.appendChild(stamp);
    this._stamp_region = stamp;
    root.appendChild(filters);
    const projects_notice = document.createElement("p");
    projects_notice.classList.add("pyc-clients-list__projects-notice");
    projects_notice.setAttribute("data-role", "projects-notice");
    projects_notice.hidden = true;
    root.appendChild(projects_notice);
    this._projects_notice_region = projects_notice;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-clients-list__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-clients-list__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");
    pager.classList.add("pyc-clients-list__pager");
    pager.setAttribute("data-role", "pager");
    pager.setAttribute("page", String(this._state.page));
    pager.setAttribute("page-size", String(this._state.perPage));
    pager.setAttribute("total-items", String(this._state.total));
    pager.addEventListener("mj-pagination-change", (event) => {
      // The clients collection is fetched whole and paginated
      // client-side, so a page change only re-slices -- it must
      // not trigger a refetch (which used to reset to page 1).
      this._state.page = event.detail.page;
      this._render_table_region();
    });
    this._pager = pager;
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the projects collection and populate the picker.
   * Exposed so unit tests can await the bootstrap fetch cycle.
   */
  async loadProjects() {
    await this._load_projects();
    return;
  }
  async _load_projects() {
    const outcome = await load_projects();
    if (outcome.ok === true && outcome.projects.length > 0) {
      this._projects = outcome.projects;
      this._projectsAvailable = true;
      this._projectsNoticeKind = "";
    } else {
      this._projects = [];
      this._projectsAvailable = false;
      if (outcome.ok === true) {
        this._projectsNoticeKind = "empty";
      } else if (outcome.status === 403) {
        this._projectsNoticeKind = "forbidden";
      } else {
        this._projectsNoticeKind = "error";
      }
    }
    this._render_project_control();
    this._render_projects_notice();
    await this._refresh();
    return;
  }
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
      region.classList.remove("pyc-clients-list__projects-notice--error");
      region.textContent = "No projects exist yet — showing clients across all projects.";
      return;
    }
    if (this._projectsNoticeKind === "forbidden") {
      region.classList.add("pyc-clients-list__projects-notice--error");
      region.textContent = "You don't have permission to list projects — enter a project id directly to filter.";
      return;
    }
    region.classList.add("pyc-clients-list__projects-notice--error");
    const message = document.createElement("span");
    message.textContent = "Couldn't load projects.";
    const retry = document.createElement("mj-button");
    retry.classList.add("pyc-clients-list__button");
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
   * Render the project picker (with an "All projects" option --
   * the clients collection is not project-scoped) or, when no
   * projects collection is available, swap to the manual text
   * input.
   */
  _render_project_control() {
    if (this._root === null) {
      return;
    }
    const select = this._root.querySelector('[data-role="project-select"]');
    const input = this._root.querySelector('[data-role="project-filter"]');
    if (select instanceof HTMLElement === false || input instanceof HTMLElement === false) {
      return;
    }
    const select_el = select;
    const input_el = input;
    if (this._projectsAvailable === true) {
      select_el.hidden = false;
      input_el.hidden = true;
      select_el.replaceChildren();
      const any_project = document.createElement("mj-option");
      any_project.setAttribute("value", "");
      any_project.textContent = "All projects";
      select_el.appendChild(any_project);
      for (const project of this._projects) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", project.project_id);
        option.textContent = project.display_name;
        select_el.appendChild(option);
      }
      select_el.value = this._state.projectFilter;
    } else {
      select_el.hidden = true;
      input_el.hidden = false;
      if (this._state.projectFilter.length > 0) {
        input_el.value = this._state.projectFilter;
      }
    }
    return;
  }
  /**
   * Fetch the clients array from the REST endpoint and re-render
   * the table region. Exposed so unit tests can await a fetch
   * cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._render_table_region();
    const url = build_clients_query_url(this._state);
    let clients = null;
    let status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        clients = body;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.list_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (status === 401) {
      announce_session_expired();
    }
    if (clients === null || Array.isArray(clients) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._state.errorStatus = status;
      this._render_table_region();
      return;
    }
    this._clients = clients;
    this._state.total = clients.length;
    const max_page = Math.max(
      1,
      Math.ceil(clients.length / this._state.perPage)
    );
    if (this._state.page > max_page) {
      this._state.page = max_page;
    }
    this._state.loading = false;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._render_stamp();
    this._render_table_region();
    return;
  }
  _render_stamp() {
    if (this._stamp_region === null) {
      return;
    }
    this._stamp_region.textContent = "as of " + format_clock_time(new Date());
    return;
  }
  /**
   * Slice the fetched clients array down to the current page.
   *
   * @returns The clients for the current page.
   */
  _page_slice() {
    const start = (this._state.page - 1) * this._state.perPage;
    const end = start + this._state.perPage;
    const rtnval = this._clients.slice(start, end);
    return rtnval;
  }
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-clients-list__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading clients…";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-clients-list__status",
        "pyc-clients-list__status--error"
      );
      error.setAttribute("data-role", "error-state");
      const message = document.createElement("span");
      message.textContent = clients_load_message_for_status(
        this._state.errorStatus
      );
      error.appendChild(message);
      const retry = document.createElement("mj-button");
      retry.classList.add("pyc-clients-list__button");
      retry.setAttribute("type", "button");
      retry.setAttribute("data-role", "error-retry");
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        void this._refresh();
      });
      error.appendChild(retry);
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    if (this._clients.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-clients-list__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No enrolled clients yet";
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
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-clients-list__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-clients-list__row";
    table.rowAttrs = (client) => ({ "data-client-id": client.client_id });
    table.columns = [
      {
        key: "client_id",
        label: "Client",
        width: "12rem",
        render: (client) => {
          const link = document.createElement("a");
          link.classList.add("pyc-clients-list__client-link");
          link.setAttribute("href", "/clients/" + client.client_id);
          link.textContent = short_id(client.client_id);
          link.title = client.client_id;
          return link;
        }
      },
      {
        key: "pod_name",
        label: "Pod",
        width: "12rem",
        render: (client) => client.pod_name !== null && client.pod_name.length > 0 ? client.pod_name : "—"
      },
      {
        key: "status",
        label: "Status",
        width: "8rem",
        render: (client) => {
          const status_badge = document.createElement("mj-chip");
          status_badge.classList.add("pyc-clients-list__badge");
          status_badge.setAttribute("data-tone", status_tone(client.status));
          status_badge.textContent = client.status;
          return status_badge;
        }
      },
      {
        key: "liveness_state",
        label: "Liveness",
        width: "9rem",
        render: (client) => {
          const liveness_badge = document.createElement("mj-chip");
          liveness_badge.classList.add("pyc-clients-list__badge");
          const liveness = client_liveness_display(client);
          liveness_badge.setAttribute("data-tone", liveness.tone);
          liveness_badge.textContent = liveness.label;
          return liveness_badge;
        }
      },
      {
        key: "last_seen",
        label: "Last heartbeat",
        width: "14rem",
        render: (client) => format_timestamp(client.last_seen)
      },
      {
        key: "last_agent_version",
        label: "Runtime version",
        width: "10rem",
        render: (client) => client.last_agent_version !== null && client.last_agent_version !== void 0 && client.last_agent_version.length > 0 ? client.last_agent_version : "—"
      },
      {
        key: "capabilities",
        label: "Capabilities",
        width: "16rem",
        sortable: false,
        render: (client) => {
          const tags = capability_tags(client.attributes);
          if (tags.length === 0) {
            const rtnval2 = document.createTextNode("—");
            return rtnval2;
          }
          const fragment = document.createElement("span");
          fragment.classList.add("pyc-clients-list__tags");
          const visible = tags.slice(0, CAPABILITY_TAG_DISPLAY_LIMIT);
          for (const tag of visible) {
            const chip = document.createElement("mj-chip");
            chip.classList.add("pyc-clients-list__tag");
            chip.textContent = tag;
            fragment.appendChild(chip);
          }
          if (tags.length > CAPABILITY_TAG_DISPLAY_LIMIT) {
            const hidden = tags.slice(CAPABILITY_TAG_DISPLAY_LIMIT);
            const more = document.createElement("mj-chip");
            more.classList.add(
              "pyc-clients-list__tag",
              "pyc-clients-list__tag--overflow"
            );
            more.textContent = "+" + String(hidden.length) + " more";
            more.title = hidden.join(", ");
            fragment.appendChild(more);
          }
          return fragment;
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "8rem",
        sortable: false,
        render: (client) => {
          const revoke_button = document.createElement("mj-button");
          revoke_button.classList.add(
            "pyc-clients-list__button",
            "pyc-clients-list__row-action"
          );
          revoke_button.setAttribute("type", "button");
          revoke_button.setAttribute("data-role", "revoke-action");
          revoke_button.textContent = "Revoke";
          if (client.status === "REVOKED") {
            revoke_button.toggleAttribute("disabled", true);
            revoke_button.title = "This client is already revoked.";
          } else {
            revoke_button.addEventListener("click", () => {
              revoke_button.toggleAttribute("disabled", true);
              void self._on_revoke_client(client, revoke_button);
            });
          }
          return revoke_button;
        }
      }
    ];
    table.rows = this._page_slice();
    return table;
  }
  async _on_revoke_client(client, button) {
    const confirm_fn = window.confirm;
    if (typeof confirm_fn !== "function") {
      button.toggleAttribute("disabled", false);
      return;
    }
    const confirmed = window.confirm(
      "Revoke client " + short_id(client.client_id) + "? The client's certificate is revoked and the pod it backs stops receiving work. This cannot be undone from this UI."
    );
    if (confirmed === false) {
      button.toggleAttribute("disabled", false);
      return;
    }
    const outcome = await perform_client_revoke(client.client_id);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-clients-list__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-clients-list__toast-dismiss");
    dismiss.setAttribute("type", "button");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "×";
    dismiss.addEventListener("click", () => {
      toast.remove();
    });
    toast.appendChild(dismiss);
    while (this._toast_region.children.length >= TOAST_STACK_LIMIT) {
      this._toast_region.removeChild(this._toast_region.firstElementChild);
    }
    this._toast_region.appendChild(toast);
    return;
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
  CLIENT_STATUSES,
  LIVENESS_STATES,
  PycClientsList,
  advertised_capability_tags,
  build_client_capabilities_url,
  build_client_detail_url,
  build_client_revoke_url,
  build_clients_query_url,
  capability_tags,
  client_liveness_display,
  clients_load_message_for_status,
  format_timestamp,
  has_next_page,
  has_previous_page,
  latest_capability_update,
  liveness_tone,
  perform_client_revoke,
  revoke_message_for_status,
  short_id,
  status_tone
};
