import {
  build_pod_definition_url,
  format_timestamp,
  member_count,
  short_id
} from "./pods-list-view.js";
const POD_STATES = [
  "DEFINED",
  "PROVISIONING",
  "READY",
  "IN_USE",
  "DRAINING",
  "RELEASED",
  "CLIENT_LOST",
  "FAILED"
];
const TRANSIENT_POD_STATES = [
  "PROVISIONING",
  "DRAINING"
];
const POLL_INTERVAL_MS = 5e3;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function pod_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/pods/";
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
  const rtnval = value.trim();
  return rtnval;
}
function is_valid_pod_id(pod_id) {
  if (typeof pod_id !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(pod_id);
  return rtnval;
}
function is_transient_pod_state(state) {
  const rtnval = TRANSIENT_POD_STATES.indexOf(state) >= 0;
  return rtnval;
}
function pod_state_tone(state) {
  if (state === "READY" || state === "IN_USE") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (state === "FAILED" || state === "CLIENT_LOST") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (state === "PROVISIONING" || state === "DRAINING") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function build_pod_state_url(project_id, pod_id) {
  const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) + "/pods/" + encodeURIComponent(pod_id) + "/state";
  return rtnval;
}
function build_pod_state_history_url(project_id, pod_id) {
  const rtnval = build_pod_state_url(project_id, pod_id) + "/history";
  return rtnval;
}
function build_pod_registration_url(project_id, pod_id) {
  const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) + "/pods/" + encodeURIComponent(pod_id) + "/registration";
  return rtnval;
}
function build_pod_registrations_url(project_id, pod_id) {
  const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) + "/pods/" + encodeURIComponent(pod_id) + "/registrations";
  return rtnval;
}
class PycPodDetail extends HTMLElement {
  _pod_id;
  _project_id;
  _definition;
  _state_row;
  _registration;
  _registration_history;
  _state_history;
  _loading;
  _errored;
  _transient;
  _poll_status;
  _poll_timer;
  _root;
  constructor() {
    super();
    this._pod_id = "";
    this._project_id = "";
    this._definition = null;
    this._state_row = null;
    this._registration = null;
    this._registration_history = [];
    this._state_history = [];
    this._loading = false;
    this._errored = false;
    this._transient = false;
    this._poll_status = "idle";
    this._poll_timer = null;
    this._root = null;
  }
  /**
   * Observed attributes -- ``pod-id`` / ``project-id`` may be
   * supplied explicitly by a host; otherwise they are read from
   * the path / query string on mount.
   */
  static get observedAttributes() {
    const rtnval = ["pod-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      podId: this._pod_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored,
      pollStatus: this._poll_status,
      transient: this._transient
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the pod + project ids, render the
   * chrome, and fetch the initial snapshot.
   */
  connectedCallback() {
    const attr_pod = this.getAttribute("pod-id");
    if (attr_pod !== null && attr_pod.length > 0) {
      this._pod_id = attr_pod;
    } else {
      this._pod_id = pod_id_from_path(window.location.pathname);
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
   * Lifecycle hook -- stop the live-poll timer so a navigation
   * away never leaks a timer.
   */
  disconnectedCallback() {
    this._stop_poll();
    return;
  }
  /**
   * Fetch the pod snapshot then -- when the pod is in a transient
   * state -- start the live-poll loop. Exposed so unit tests can
   * await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_pod_id(this._pod_id) === false) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    if (this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const definition = await this._fetch_json(
      build_pod_definition_url(this._project_id, this._pod_id),
      "definition_fetch_failed"
    );
    if (definition === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._definition = definition;
    await this._refresh_runtime();
    this._loading = false;
    this._errored = false;
    this._render_body();
    if (this._transient === true) {
      this._start_poll();
    } else {
      this._poll_status = "stopped";
      this._render_poll_banner();
    }
    return;
  }
  /**
   * Re-fetch the live state, registration and history rows.
   * Shared by the initial load and each poll cycle.
   */
  async _refresh_runtime() {
    const state_row = await this._fetch_json(
      build_pod_state_url(this._project_id, this._pod_id),
      "state_fetch_failed"
    );
    if (state_row !== null) {
      this._state_row = state_row;
      this._transient = is_transient_pod_state(state_row.state);
    }
    const registration = await this._fetch_json(
      build_pod_registration_url(this._project_id, this._pod_id),
      "registration_fetch_failed"
    );
    this._registration = registration;
    const history = await this._fetch_json(
      build_pod_registrations_url(this._project_id, this._pod_id),
      "registrations_fetch_failed"
    );
    if (history !== null && Array.isArray(history) === true) {
      this._registration_history = history;
    }
    const state_history = await this._fetch_json(
      build_pod_state_history_url(this._project_id, this._pod_id),
      "state_history_fetch_failed"
    );
    if (state_history !== null && Array.isArray(state_history) === true) {
      this._state_history = state_history;
    }
    return;
  }
  /**
   * Fetch a JSON document. A non-OK response or a thrown error
   * yields ``null`` -- callers decide whether a missing document
   * is an error or an empty state.
   *
   * @param url Relative URL to GET.
   * @param failure_tag A log tag for diagnostic warnings.
   *
   * @returns The parsed JSON body, or ``null`` on failure.
   */
  async _fetch_json(url, failure_tag) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        const rtnval2 = null;
        return rtnval2;
      }
      const body = await response.json();
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pods." + failure_tag,
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  _start_poll() {
    if (this._poll_timer !== null) {
      return;
    }
    this._poll_status = "polling";
    this._render_poll_banner();
    this._schedule_poll();
    return;
  }
  _schedule_poll() {
    const timer = setTimeout(() => {
      this._poll_timer = null;
      void this._poll_once();
    }, POLL_INTERVAL_MS);
    const handle = timer;
    if (typeof handle.unref === "function") {
      handle.unref();
    }
    this._poll_timer = timer;
    return;
  }
  /**
   * Run one poll cycle -- re-fetch runtime rows, re-render, and
   * either reschedule (still transient) or stop (now settled).
   * Exposed so unit tests can drive a poll cycle without waiting
   * on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    await this._refresh_runtime();
    this._render_body();
    if (this._transient === false) {
      this._stop_poll();
      this._poll_status = "stopped";
      this._render_poll_banner();
      return;
    }
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
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-pod-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Pod detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-pod-detail__heading");
    heading.textContent = "Pod detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-pod-detail__back-link");
    back.setAttribute("href", "/pods");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to pods";
    root.appendChild(back);
    const banner = document.createElement("p");
    banner.classList.add("pyc-pod-detail__banner");
    banner.setAttribute("data-role", "poll-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;
    root.appendChild(banner);
    const body = document.createElement("div");
    body.classList.add("pyc-pod-detail__body");
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
      loading.classList.add("pyc-pod-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading pod\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._definition === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-pod-detail__status",
        "pyc-pod-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load this pod. A project id query parameter is required \u2014 try refreshing from the pods list.";
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._definition));
    fragment.appendChild(this._build_members(this._definition));
    fragment.appendChild(this._build_registration());
    fragment.appendChild(this._build_registration_history());
    fragment.appendChild(this._build_state_history());
    body.replaceChildren(fragment);
    return;
  }
  _build_summary(definition) {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pod summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-pod-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-pod-detail__pod-id");
    id_value.setAttribute("data-role", "pod-id");
    id_value.textContent = short_id(definition.pod_id);
    id_value.title = definition.pod_id;
    id_row.appendChild(id_value);
    const state_value = this._state_row !== null ? this._state_row.state : "DEFINED";
    const badge = document.createElement("span");
    badge.classList.add("pyc-pod-detail__badge");
    badge.setAttribute("data-role", "state-badge");
    badge.setAttribute("data-tone", pod_state_tone(state_value));
    badge.textContent = state_value;
    id_row.appendChild(badge);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-pod-detail__grid");
    this._append_field(grid, "Pod id", definition.pod_id);
    this._append_field(grid, "Pod name", definition.pod_name);
    this._append_field(grid, "Project", definition.project_id);
    this._append_field(
      grid,
      "Version",
      "v" + String(definition.current_version)
    );
    this._append_field(
      grid,
      "Members",
      String(member_count(definition.spec))
    );
    this._append_field(
      grid,
      "Created",
      format_timestamp(definition.created_at)
    );
    if (definition.spec_hash !== null && definition.spec_hash !== void 0 && definition.spec_hash.length > 0) {
      this._append_field(grid, "Spec hash", definition.spec_hash);
    }
    if (this._state_row !== null) {
      this._append_field(
        grid,
        "Last transition",
        format_timestamp(this._state_row.last_transition_at)
      );
      const event = this._state_row.last_transition_event;
      if (event !== null && event !== void 0 && event.length > 0) {
        this._append_field(grid, "Last event", event);
      }
    }
    section.appendChild(grid);
    return section;
  }
  _build_members(definition) {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__members");
    section.setAttribute("data-role", "members-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pod members");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pod-detail__section-heading");
    heading.textContent = "Members";
    section.appendChild(heading);
    const list = document.createElement("ul");
    list.classList.add("pyc-pod-detail__member-list");
    const spec = definition.spec;
    let members = [];
    if (spec !== null && spec !== void 0) {
      const raw = spec["members"];
      if (Array.isArray(raw) === true) {
        members = raw;
      }
    }
    if (members.length === 0) {
      const empty = document.createElement("li");
      empty.classList.add("pyc-pod-detail__member-empty");
      empty.textContent = "This pod definition declares no members.";
      list.appendChild(empty);
    } else {
      for (const member of members) {
        const item = document.createElement("li");
        item.classList.add("pyc-pod-detail__member-entry");
        item.textContent = this._member_label(member);
        list.appendChild(item);
      }
    }
    section.appendChild(list);
    return section;
  }
  /**
   * Derive a display label for one pod-spec member entry. A
   * member is typically an object carrying a ``name`` / ``kind``;
   * fall back to a JSON rendering when the shape is unexpected.
   *
   * @param member One entry from the spec's ``members`` array.
   *
   * @returns A human-readable label.
   */
  _member_label(member) {
    if (member !== null && typeof member === "object") {
      const record = member;
      const name = record["name"];
      const kind = record["kind"];
      const name_str = typeof name === "string" ? name : "";
      const kind_str = typeof kind === "string" ? kind : "";
      if (name_str.length > 0 && kind_str.length > 0) {
        const rtnval2 = name_str + " (" + kind_str + ")";
        return rtnval2;
      }
      if (name_str.length > 0) {
        const rtnval2 = name_str;
        return rtnval2;
      }
      if (kind_str.length > 0) {
        const rtnval2 = kind_str;
        return rtnval2;
      }
    }
    if (typeof member === "string") {
      const rtnval2 = member;
      return rtnval2;
    }
    const rtnval = JSON.stringify(member);
    return rtnval;
  }
  _build_registration() {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__registration");
    section.setAttribute("data-role", "registration-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Registered client");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pod-detail__section-heading");
    heading.textContent = "Registered client";
    section.appendChild(heading);
    if (this._registration === null) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pod-detail__status");
      empty.setAttribute("data-role", "registration-empty");
      empty.textContent = "No active registration for this pod.";
      section.appendChild(empty);
      return section;
    }
    const grid = document.createElement("dl");
    grid.classList.add("pyc-pod-detail__grid");
    const client_id = this._registration.client_id;
    if (client_id !== null && client_id !== void 0 && client_id.length > 0) {
      const field = document.createElement("div");
      field.classList.add("pyc-pod-detail__field");
      const term = document.createElement("dt");
      term.textContent = "Client";
      const def = document.createElement("dd");
      const link = document.createElement("a");
      link.classList.add("pyc-pod-detail__client-link");
      link.setAttribute("href", "/clients/" + client_id);
      link.textContent = short_id(client_id);
      link.title = client_id;
      def.appendChild(link);
      field.appendChild(term);
      field.appendChild(def);
      grid.appendChild(field);
    } else {
      this._append_field(grid, "Client", "\u2014");
    }
    this._append_field(grid, "Registration state", this._registration.state);
    this._append_field(
      grid,
      "Definition version",
      "v" + String(this._registration.pod_definition_version)
    );
    this._append_field(
      grid,
      "Registered",
      format_timestamp(this._registration.registered_at)
    );
    section.appendChild(grid);
    return section;
  }
  _build_registration_history() {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__registration-history");
    section.setAttribute("data-role", "registration-history-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Registration history");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pod-detail__section-heading");
    heading.textContent = "Registration history";
    section.appendChild(heading);
    if (this._registration_history.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pod-detail__status");
      empty.setAttribute("data-role", "registration-history-empty");
      empty.textContent = "No registration history for this pod.";
      section.appendChild(empty);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-pod-detail__history-list");
    for (const row of this._registration_history) {
      const item = document.createElement("li");
      item.classList.add("pyc-pod-detail__history-entry");
      const summary = row.state + " \xB7 v" + String(row.pod_definition_version) + " \xB7 " + format_timestamp(row.registered_at);
      item.textContent = summary;
      if (row.deregister_reason !== null && row.deregister_reason !== void 0 && row.deregister_reason.length > 0) {
        const reason = document.createElement("span");
        reason.classList.add("pyc-pod-detail__history-reason");
        reason.textContent = " \u2014 " + row.deregister_reason;
        item.appendChild(reason);
      }
      list.appendChild(item);
    }
    section.appendChild(list);
    return section;
  }
  _build_state_history() {
    const section = document.createElement("section");
    section.classList.add("pyc-pod-detail__state-history");
    section.setAttribute("data-role", "state-history-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Lifecycle history");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pod-detail__section-heading");
    heading.textContent = "Lifecycle history";
    section.appendChild(heading);
    if (this._state_history.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pod-detail__status");
      empty.setAttribute("data-role", "state-history-empty");
      empty.textContent = "No lifecycle transitions recorded.";
      section.appendChild(empty);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-pod-detail__history-list");
    for (const row of this._state_history) {
      const item = document.createElement("li");
      item.classList.add("pyc-pod-detail__history-entry");
      const from_label = row.from_state !== null && row.from_state !== void 0 ? row.from_state : "\u2205";
      const summary = from_label + " \u2192 " + row.to_state + " \xB7 " + format_timestamp(row.applied_at);
      item.textContent = summary;
      if (row.event_kind !== null && row.event_kind !== void 0 && row.event_kind.length > 0) {
        const event = document.createElement("span");
        event.classList.add("pyc-pod-detail__history-event");
        event.textContent = " (" + row.event_kind + ")";
        item.appendChild(event);
      }
      list.appendChild(item);
    }
    section.appendChild(list);
    return section;
  }
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-pod-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    def.textContent = value;
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  _render_poll_banner() {
    if (this._root === null) {
      return;
    }
    const banner = this._root.querySelector('[data-role="poll-banner"]');
    if (banner instanceof HTMLElement === false) {
      return;
    }
    const el = banner;
    if (this._poll_status === "polling") {
      el.hidden = false;
      el.setAttribute("data-tone", "neutral");
      el.textContent = "Pod is mid-transition \u2014 refreshing every 5 seconds.";
      return;
    }
    if (this._poll_status === "stopped" && this._transient === false) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = true;
    el.textContent = "";
    return;
  }
}
export {
  POD_STATES,
  PycPodDetail,
  TRANSIENT_POD_STATES,
  build_pod_registration_url,
  build_pod_registrations_url,
  build_pod_state_history_url,
  build_pod_state_url,
  is_transient_pod_state,
  is_valid_pod_id,
  pod_id_from_path,
  pod_state_tone,
  project_id_from_search
};
