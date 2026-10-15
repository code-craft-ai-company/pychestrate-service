import { hide_unless_may } from "../shared/permissions.js";
import { show_toast } from "../shared/toast.js";
import { state_label } from "../shared/run-labels.js";
import { keep_list_state_on_back } from "../shared/view-state.js";
import { confirm_action, label_from_button } from "../shared/confirm.js";
import { message_with_detail, read_problem_detail } from "../shared/problem-detail.js";
import { set_entity_title } from "../shared/page-title.js";
import {
  announce_session_expired,
  build_pod_definition_url,
  format_clock_time,
  format_timestamp,
  load_projects,
  member_count,
  project_display_map,
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
// A draining pod is not mid-transition: nothing moves it on by itself (an operator retires it), so it is not polled every 5 seconds like a pod being provisioned.
const TRANSIENT_POD_STATES = [
  "PROVISIONING"
];
const TERMINAL_POD_STATES = [
  "RELEASED"
];
const DRAINABLE_POD_STATES = [
  "READY",
  "IN_USE"
];
const RETIRABLE_POD_STATES = [
  "DRAINING",
  "FAILED"
];
const POLL_INTERVAL_TRANSIENT_MS = 5e3;
const POLL_INTERVAL_SETTLED_MS = 15e3;
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
function is_terminal_pod_state(state) {
  const rtnval = TERMINAL_POD_STATES.indexOf(state) >= 0;
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
function build_pod_transitions_url(project_id, pod_id) {
  const rtnval = build_pod_state_url(project_id, pod_id) + "/transitions";
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
function detail_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired — sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to pods.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "No pod with this id in this project.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service — check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load this pod (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function runtime_section_message_for_status(status, what) {
  if (status === 401) {
    const rtnval2 = "Your session has expired — sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to " + what + ".";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't load " + what + " — check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load " + what + " (HTTP " + String(status) + ").";
  return rtnval;
}
function transition_message_for_status(status, event_kind) {
  if (status === 200) {
    if (event_kind === "drain") {
      const rtnval2 = "Drain started — the pod is now draining.";
      return rtnval2;
    }
    const rtnval2 = "Pod retired — its registration is released.";
    return rtnval2;
  }
  if (status === 400) {
    const rtnval2 = "The transition request was rejected (HTTP 400).";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired — sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to change pod state.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This pod's runtime state was not found.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "That action is not allowed from the pod's current state.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service — check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to apply the transition (HTTP " + String(status) + ").";
  return rtnval;
}
class PycPodDetail extends HTMLElement {
  _pod_id;
  _project_id;
  _definition;
  _definition_status;
  _state_row;
  _registration;
  _registration_history;
  _state_history;
  _runtime_status;
  _project_names;
  _loading;
  _errored;
  _transient;
  _draining;
  _poll_status;
  _poll_timer;
  _root;
  _toast_region;
  _stamp_region;
  _on_visibility_change;
  constructor() {
    super();
    this._pod_id = "";
    this._project_id = "";
    this._definition = null;
    this._definition_status = 0;
    this._state_row = null;
    this._registration = null;
    this._registration_history = [];
    this._state_history = [];
    this._runtime_status = {
      state: 0,
      registration: 0,
      registrations: 0,
      stateHistory: 0
    };
    this._project_names = null;
    this._loading = false;
    this._errored = false;
    this._transient = false;
    this._draining = false;
    this._poll_status = "idle";
    this._poll_timer = null;
    this._root = null;
    this._toast_region = null;
    this._stamp_region = null;
    this._on_visibility_change = () => {
      this._handle_visibility_change();
    };
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
      transient: this._transient,
      runtimeStatus: {
        state: this._runtime_status.state,
        registration: this._runtime_status.registration,
        registrations: this._runtime_status.registrations,
        stateHistory: this._runtime_status.stateHistory
      }
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
    if (typeof document !== "undefined") {
      document.addEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  /**
   * Lifecycle hook -- stop the live-poll timer and drop the
   * visibility listener so a navigation away never leaks either.
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
  /**
   * Fetch the pod snapshot then start the live-poll loop when
   * the pod is not in a terminal state. Exposed so unit tests can
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
      this._definition_status = 0;
      this._render_body();
      return;
    }
    if (this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._definition_status = 0;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const definition_env = await this._fetch_json(
      build_pod_definition_url(this._project_id, this._pod_id),
      "definition_fetch_failed"
    );
    this._definition_status = definition_env.status;
    if (definition_env.ok === false || definition_env.body === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._definition = definition_env.body;
    if (this._project_names === null) {
      const projects_outcome = await load_projects();
      if (projects_outcome.ok === true) {
        this._project_names = project_display_map(
          projects_outcome.projects
        );
      } else {
        // Display names are cosmetic -- fall back to raw ids
        // rather than blocking the pod view on the projects list.
        this._project_names = {};
      }
    }
    await this._refresh_runtime();
    this._loading = false;
    this._errored = false;
    this._render_stamp();
    this._render_body();
    this._update_poll_state();
    return;
  }
  /**
   * Re-fetch the live state, registration and history rows in
   * parallel. Shared by the initial load and each poll cycle.
   * Each fetch's HTTP status is tracked so the sections can
   * render an honest error state instead of a fake empty one.
   */
  async _refresh_runtime() {
    const state_promise = this._fetch_json(
      build_pod_state_url(this._project_id, this._pod_id),
      "state_fetch_failed"
    );
    const registration_promise = this._fetch_json(
      build_pod_registration_url(this._project_id, this._pod_id),
      "registration_fetch_failed"
    );
    const registrations_promise = this._fetch_json(
      build_pod_registrations_url(this._project_id, this._pod_id),
      "registrations_fetch_failed"
    );
    const state_history_promise = this._fetch_json(
      build_pod_state_history_url(this._project_id, this._pod_id),
      "state_history_fetch_failed"
    );
    const envelopes = await Promise.all([
      state_promise,
      registration_promise,
      registrations_promise,
      state_history_promise
    ]);
    const state_env = envelopes[0];
    const registration_env = envelopes[1];
    const registrations_env = envelopes[2];
    const state_history_env = envelopes[3];
    this._runtime_status.state = state_env.status;
    if (state_env.ok === true && state_env.body !== null) {
      this._state_row = state_env.body;
      this._transient = is_transient_pod_state(state_env.body.state);
      this._draining = state_env.body.state === "DRAINING";
    } else {
      // Never invent a state -- an unavailable state renders as
      // "State unavailable", not as DEFINED.
      this._state_row = null;
      this._transient = false;
    }
    this._runtime_status.registration = registration_env.status;
    if (registration_env.ok === true) {
      this._registration = registration_env.body;
    } else {
      this._registration = null;
    }
    this._runtime_status.registrations = registrations_env.status;
    if (registrations_env.ok === true && Array.isArray(registrations_env.body) === true) {
      this._registration_history = registrations_env.body;
    } else {
      this._registration_history = [];
    }
    this._runtime_status.stateHistory = state_history_env.status;
    if (state_history_env.ok === true && Array.isArray(state_history_env.body) === true) {
      this._state_history = state_history_env.body;
    } else {
      this._state_history = [];
    }
    return;
  }
  /**
   * Fetch a JSON document. Never throws -- a network error yields
   * ``{ok: false, status: 0, body: null}``. A 401 announces the
   * shared ``pyc-session-401`` event so the shell can surface the
   * expired session.
   *
   * @param url Relative URL to GET.
   * @param failure_tag A log tag for diagnostic warnings.
   *
   * @returns ``{ok, status, body}``.
   */
  async _fetch_json(url, failure_tag) {
    let status = 0;
    let ok = false;
    let body = null;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
      ok = response.ok;
      if (ok === true) {
        body = await response.json();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pods." + failure_tag,
        { reason: String(reason) }
      );
    }
    if (status === 401) {
      announce_session_expired();
    }
    const rtnval = { ok, status, body };
    return rtnval;
  }
  /**
   * POST an operator lifecycle event (``drain`` / ``deregister``)
   * to the pod. Exposed so unit tests can drive a transition
   * without a button.
   *
   * @param event_kind The lifecycle event to apply.
   *
   * @returns ``{ok, status, message}``.
   */
  async applyTransition(event_kind) {
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(
        build_pod_transitions_url(this._project_id, this._pod_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ event_kind })
        }
      );
      status = response.status;
      detail = await read_problem_detail(response);
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pods.transition_failed",
        { reason: String(reason), event_kind }
      );
    }
    if (status === 401) {
      announce_session_expired();
    }
    const ok = status === 200;
    const rtnval = {
      ok,
      status,
      message: message_with_detail("Pod not updated", detail, transition_message_for_status(status, event_kind))
    };
    return rtnval;
  }
  async _on_transition(event_kind, confirm_text, button) {
    const confirmed = await confirm_action(this, confirm_text, label_from_button(button, "Continue"));
    if (confirmed !== true) {
      button.toggleAttribute("disabled", false);
      return;
    }
    const outcome = await this.applyTransition(event_kind);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._refresh_runtime();
      this._render_stamp();
      this._render_body();
      this._update_poll_state();
    }
    return;
  }
  /**
   * Start / stop the poll loop from the current pod state. The
   * view polls in every non-terminal state (transient states at
   * 5s, settled ones at 15s) and also while the state is
   * unavailable so a transient fetch failure recovers on its own.
   * Only a terminal (RELEASED) pod stops the loop.
   */
  _update_poll_state() {
    if (this._definition === null) {
      this._stop_poll();
      this._poll_status = "stopped";
      this._render_poll_banner();
      return;
    }
    const state_known = this._state_row !== null;
    if (state_known === true && is_terminal_pod_state(this._state_row.state) === true) {
      this._stop_poll();
      this._poll_status = "stopped";
      this._render_poll_banner();
      return;
    }
    this._poll_status = "polling";
    this._render_poll_banner();
    if (this._poll_timer === null) {
      this._schedule_poll();
    }
    return;
  }
  _poll_interval_ms() {
    if (this._transient === true) {
      const rtnval2 = POLL_INTERVAL_TRANSIENT_MS;
      return rtnval2;
    }
    const rtnval = POLL_INTERVAL_SETTLED_MS;
    return rtnval;
  }
  _schedule_poll() {
    const timer = setTimeout(() => {
      this._poll_timer = null;
      void this._poll_once();
    }, this._poll_interval_ms());
    const handle = timer;
    if (typeof handle.unref === "function") {
      handle.unref();
    }
    this._poll_timer = timer;
    return;
  }
  /**
   * Run one poll cycle -- re-fetch runtime rows, re-render, and
   * either reschedule (still live) or stop (now terminal).
   * Exposed so unit tests can drive a poll cycle without waiting
   * on a real timer.
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
    await this._refresh_runtime();
    this._render_stamp();
    this._render_body();
    this._update_poll_state();
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
    if (this._poll_timer === null && this._poll_status === "polling") {
      void this._poll_once();
    }
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-pod-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Pod detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-pod-detail__heading");
    heading.textContent = "Pod detail";
    root.appendChild(heading);
    const toolbar = document.createElement("div");
    toolbar.classList.add("pyc-pod-detail__toolbar");
    const back = document.createElement("a");
    back.classList.add("pyc-pod-detail__back-link");
    let back_href = "/pods";
    if (this._project_id.length > 0) {
      back_href = "/pods?project_id=" + encodeURIComponent(this._project_id);
    }
    back.setAttribute("href", back_href);
    back.setAttribute("data-role", "back-link");
    keep_list_state_on_back(back, "/pods");
    back.textContent = "Back to pods";
    toolbar.appendChild(back);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-pod-detail__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._load();
    });
    toolbar.appendChild(refresh_button);
    const stamp = document.createElement("span");
    stamp.classList.add("pyc-pod-detail__stamp");
    stamp.setAttribute("data-role", "last-updated");
    toolbar.appendChild(stamp);
    this._stamp_region = stamp;
    root.appendChild(toolbar);
    const banner = document.createElement("p");
    banner.classList.add("pyc-pod-detail__banner");
    banner.setAttribute("data-role", "poll-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;
    root.appendChild(banner);
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-pod-detail__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const body = document.createElement("div");
    body.classList.add("pyc-pod-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
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
   * Resolve the definition-load error message from how the load
   * failed -- a malformed id and a missing project id are caller
   * mistakes, the rest map from the HTTP status.
   */
  _load_error_message() {
    if (is_valid_pod_id(this._pod_id) === false) {
      const rtnval2 = "No pod with this id.";
      return rtnval2;
    }
    if (this._project_id.length === 0) {
      const rtnval2 = "A project id is required — open this pod from the pods list.";
      return rtnval2;
    }
    const rtnval = detail_load_message_for_status(this._definition_status);
    return rtnval;
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
      loading.textContent = "Loading pod…";
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
      const message = document.createElement("span");
      message.textContent = this._load_error_message();
      error.appendChild(message);
      if (is_valid_pod_id(this._pod_id) === true && this._project_id.length > 0) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-pod-detail__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "error-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._load();
        });
        error.appendChild(retry);
      }
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
  /**
   * Resolve a project's display name from the cached projects
   * map, falling back to the raw id.
   */
  _project_display_name(project_id) {
    if (this._project_names !== null) {
      const display = this._project_names[project_id];
      if (typeof display === "string" && display.length > 0) {
        const rtnval2 = display;
        return rtnval2;
      }
    }
    const rtnval = project_id;
    return rtnval;
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
    set_entity_title("Pod " + (typeof definition.pod_name === "string" && definition.pod_name.trim().length > 0 ? definition.pod_name.trim() : short_id(definition.pod_id)));
    id_value.title = definition.pod_id;
    id_row.appendChild(id_value);
    const badge = document.createElement("mj-chip");
    badge.classList.add("pyc-pod-detail__badge");
    badge.setAttribute("data-role", "state-badge");
    // A pod no client has registered on yet has no state row: the
    // state endpoint answers 404. That is a normal, declared pod
    // waiting for its client -- not an error (RES-36).
    const awaiting_client = this._state_row === null && this._runtime_status.state === 404;
    if (this._state_row !== null) {
      badge.setAttribute("data-tone", pod_state_tone(this._state_row.state));
      badge.textContent = state_label(this._state_row.state);
    } else if (awaiting_client === true) {
      badge.setAttribute("data-tone", "neutral");
      badge.textContent = "Declared";
      badge.title = "Waiting for a client to enroll on this pod.";
    } else {
      // The state fetch failed -- say so instead of inventing a
      // state the pod may not be in.
      badge.setAttribute("data-tone", "neutral");
      badge.textContent = "State unavailable";
      badge.title = runtime_section_message_for_status(
        this._runtime_status.state,
        "the pod state"
      );
    }
    id_row.appendChild(badge);
    id_row.appendChild(this._build_actions());
    section.appendChild(id_row);
    if (awaiting_client === true) {
      const waiting = document.createElement("p");
      waiting.classList.add("pyc-pod-detail__status", "pyc-pod-detail__status--inline");
      waiting.setAttribute("data-role", "state-awaiting-client");
      waiting.textContent = "Declared \u2014 waiting for a client. Mint an enrollment token for this pod name and enroll a machine to bring it online.";
      section.appendChild(waiting);
    } else if (this._state_row === null) {
      const state_error = document.createElement("p");
      state_error.classList.add(
        "pyc-pod-detail__status",
        "pyc-pod-detail__status--error",
        "pyc-pod-detail__status--inline"
      );
      state_error.setAttribute("data-role", "state-error");
      state_error.textContent = runtime_section_message_for_status(
        this._runtime_status.state,
        "the pod state"
      );
      section.appendChild(state_error);
    }
    const grid = document.createElement("dl");
    grid.classList.add("pyc-pod-detail__grid");
    this._append_field(grid, "Pod id", definition.pod_id);
    this._append_field(grid, "Pod name", definition.pod_name);
    this._append_field(
      grid,
      "Project",
      this._project_display_name(definition.project_id),
      definition.project_id
    );
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
  /**
   * Build the operator action buttons. Drain is legal from READY
   * / IN_USE, retire (deregister) from DRAINING / FAILED --
   * mirroring the server's transition table so an always-illegal
   * click never leaves the page.
   */
  _build_actions() {
    const actions = document.createElement("span");
    actions.classList.add("pyc-pod-detail__actions");
    actions.setAttribute("data-role", "pod-actions");
    const state_known = this._state_row !== null;
    const current_state = state_known === true ? this._state_row.state : "";
    const drain_button = document.createElement("mj-button");
    drain_button.classList.add("pyc-pod-detail__button");
    drain_button.setAttribute("type", "button");
    drain_button.setAttribute("data-role", "drain-action");
    drain_button.textContent = "Drain";
    hide_unless_may(drain_button, "system:pods.write");
    const drain_allowed = DRAINABLE_POD_STATES.indexOf(current_state) >= 0;
    if (drain_allowed === false) {
      drain_button.toggleAttribute("disabled", true);
      drain_button.title = state_known === true ? "Drain is only available while the pod is ready or in use." : "The pod state is unavailable — actions are disabled.";
    } else {
      drain_button.addEventListener("click", () => {
        drain_button.toggleAttribute("disabled", true);
        const confirm_text = "Drain pod " + short_id(this._pod_id) + "? The pod stops accepting new work, finishes what is in flight, and moves to draining.";
        void this._on_transition("drain", confirm_text, drain_button);
      });
    }
    actions.appendChild(drain_button);
    const retire_button = document.createElement("mj-button");
    retire_button.classList.add("pyc-pod-detail__button");
    retire_button.setAttribute("type", "button");
    retire_button.setAttribute("data-role", "retire-action");
    retire_button.textContent = "Retire";
    hide_unless_may(retire_button, "system:pods.write");
    const retire_allowed = RETIRABLE_POD_STATES.indexOf(current_state) >= 0;
    if (retire_allowed === false) {
      retire_button.toggleAttribute("disabled", true);
      retire_button.title = state_known === true ? "Retire is only available while the pod is draining or failed." : "The pod state is unavailable — actions are disabled.";
    } else {
      retire_button.addEventListener("click", () => {
        retire_button.toggleAttribute("disabled", true);
        const confirm_text = "Retire pod " + short_id(this._pod_id) + "? Its registration is released and the pod moves to released — it must be re-provisioned before it can serve work again.";
        void this._on_transition("deregister", confirm_text, retire_button);
      });
    }
    actions.appendChild(retire_button);
    return actions;
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
  /**
   * Build one section-level error paragraph for a failed runtime
   * fetch -- used instead of the section's empty state so a
   * failure never masquerades as "no data".
   */
  _build_section_error(role, status, what) {
    const error = document.createElement("p");
    error.classList.add(
      "pyc-pod-detail__status",
      "pyc-pod-detail__status--error"
    );
    error.setAttribute("data-role", role);
    error.textContent = runtime_section_message_for_status(status, what);
    const rtnval = error;
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
      // A 404 is the documented "no active registration" answer;
      // anything else is a failure and renders as one.
      if (this._runtime_status.registration === 404) {
        const empty = document.createElement("p");
        empty.classList.add("pyc-pod-detail__status");
        empty.setAttribute("data-role", "registration-empty");
        empty.textContent = "No active registration for this pod.";
        section.appendChild(empty);
      } else {
        section.appendChild(
          this._build_section_error(
            "registration-error",
            this._runtime_status.registration,
            "the registration"
          )
        );
      }
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
      this._append_field(grid, "Client", "—");
    }
    this._append_field(grid, "Registration state", state_label(this._registration.state));
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
    if (this._runtime_status.registrations !== 200) {
      section.appendChild(
        this._build_section_error(
          "registration-history-error",
          this._runtime_status.registrations,
          "the registration history"
        )
      );
      return section;
    }
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
      const summary = state_label(row.state) + " · v" + String(row.pod_definition_version) + " · " + format_timestamp(row.registered_at);
      item.textContent = summary;
      if (row.deregister_reason !== null && row.deregister_reason !== void 0 && row.deregister_reason.length > 0) {
        const reason = document.createElement("span");
        reason.classList.add("pyc-pod-detail__history-reason");
        reason.textContent = " — " + row.deregister_reason;
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
    if (this._runtime_status.stateHistory !== 200) {
      section.appendChild(
        this._build_section_error(
          "state-history-error",
          this._runtime_status.stateHistory,
          "the lifecycle history"
        )
      );
      return section;
    }
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
      const from_label = row.from_state !== null && row.from_state !== void 0 ? state_label(row.from_state) : "∅";
      const summary = from_label + " → " + state_label(row.to_state) + " · " + format_timestamp(row.applied_at);
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
  _append_field(grid, label, value, title) {
    const field = document.createElement("div");
    field.classList.add("pyc-pod-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    if (typeof value === "string" && value.length > 0) {
      def.textContent = value;
    } else {
      def.textContent = "—";
    }
    if (typeof title === "string" && title.length > 0) {
      def.title = title;
    }
    field.appendChild(term);
    field.appendChild(def);
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
    show_toast(this._toast_region, message, tone, { class_prefix: "pyc-pod-detail" });
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
      if (this._transient === true) {
        el.textContent = "Pod is mid-transition — refreshing every 5 seconds.";
      } else if (this._draining === true) {
        el.textContent = "Pod is draining: it takes no new work. Retire it when its jobs have finished. Refreshing every 15 seconds.";
      } else {
        el.textContent = "Live view — refreshing every 15 seconds.";
      }
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
  TERMINAL_POD_STATES,
  TRANSIENT_POD_STATES,
  build_pod_registration_url,
  build_pod_registrations_url,
  build_pod_state_history_url,
  build_pod_state_url,
  build_pod_transitions_url,
  detail_load_message_for_status,
  is_terminal_pod_state,
  is_transient_pod_state,
  is_valid_pod_id,
  pod_id_from_path,
  pod_state_tone,
  project_id_from_search,
  runtime_section_message_for_status,
  transition_message_for_status
};
