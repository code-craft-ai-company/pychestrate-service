import { set_entity_title } from "../shared/page-title.js";
import {
  emit_session_expired,
  fetch_projects,
  format_timestamp,
  login_next_url,
  project_display_map,
  short_run_id,
  state_badge_tone
} from "./runs-list-view.js";
const TERMINAL_RUN_STATES = [
  "dispatch_failed",
  "cancelled",
  "completed",
  "failed"
];
const RUNS_API_PATH = "/api/v1/runs";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function run_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/runs/";
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
function is_valid_run_id(run_id) {
  if (typeof run_id !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(run_id);
  return rtnval;
}
function is_terminal_state(run_state) {
  const rtnval = TERMINAL_RUN_STATES.indexOf(run_state) >= 0;
  return rtnval;
}
function coerce_count(value) {
  if (typeof value === "number" && Number.isFinite(value) === true) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = 0;
  return rtnval;
}
// States in which a run is waiting for its pod to take it. A trigger
// against a stopped pod used to sit here with no hint why (E2E-16).
var WAITING_FOR_POD_STATES = ["pending", "dispatching", "dispatched", "dispatch_unconfirmed"];
function waiting_for_pod_message(run) {
  if (run === null || run === void 0 || WAITING_FOR_POD_STATES.includes(run.state) === false) {
    const rtnval2 = null;
    return rtnval2;
  }
  const client = run.assigned_client;
  if (client === null || client === void 0) {
    const rtnval2 = null;
    return rtnval2;
  }
  const pod = client.pod_name || "its pod";
  let text = "Waiting for pod " + pod + " to pick up this run.";
  let tone = "neutral";
  if (client.status === "REVOKED") {
    text += " Its client has been revoked, so the run will not start; cancel it and trigger it again.";
    tone = "warn";
  } else if (client.last_seen === null || client.last_seen === void 0 || client.last_seen === "") {
    text += " Its client has never checked in; the run starts once it connects.";
    tone = "warn";
  } else if (client.liveness_state !== "ALIVE") {
    const label = client.liveness_state === "LOST" ? "offline" : "not responding";
    text += " Its client is " + label + " (last heard from " + format_timestamp(client.last_seen) + "); the run starts when it reconnects.";
    tone = "warn";
  }
  const rtnval = { text, tone };
  return rtnval;
}
function progress_bar_tone(run) {
  const state = run !== null && run !== void 0 ? run.state : "";
  if (state === "failed" || state === "dispatch_failed") {
    const rtnval2 = "error";
    return rtnval2;
  }
  if (state === "cancelled") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (state === "completed") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  const rtnval = "active";
  return rtnval;
}
// Build, provision and RPA runs carry "<kind>-" job types. Test
// counters mean nothing for them: an RPA run's loudest element was a
// row of 0 passed / 0 failed tiles (E2E-23).
var NON_TEST_JOB_TYPE_PREFIXES = ["rpa-", "build-", "provision-"];
function is_test_run(run) {
  const job_type = run !== null && run !== void 0 && typeof run.job_type === "string" ? run.job_type : "";
  for (const prefix of NON_TEST_JOB_TYPE_PREFIXES) {
    if (job_type.startsWith(prefix) === true) {
      const rtnval2 = false;
      return rtnval2;
    }
  }
  const rtnval = true;
  return rtnval;
}
function has_test_counts(progress) {
  const counter_keys = [
    "tests_total",
    "tests_passed",
    "tests_failed",
    "tests_skipped",
    "tests_errored"
  ];
  for (const key of counter_keys) {
    if (typeof progress[key] === "number") {
      const rtnval2 = true;
      return rtnval2;
    }
  }
  const rtnval = false;
  return rtnval;
}
function progress_percent(progress) {
  if (progress.percent_complete !== null && progress.percent_complete !== void 0 && Number.isFinite(progress.percent_complete) === true) {
    const clamped = Math.max(0, Math.min(100, progress.percent_complete));
    return clamped;
  }
  const total = progress.tests_total;
  if (typeof total !== "number" || Number.isFinite(total) === false || total <= 0) {
    const rtnval2 = 0;
    return rtnval2;
  }
  const done = coerce_count(progress.tests_passed) + coerce_count(progress.tests_failed) + coerce_count(progress.tests_skipped) + coerce_count(progress.tests_errored);
  const ratio = done / total * 100;
  const rtnval = Math.max(0, Math.min(100, ratio));
  return rtnval;
}
function resolve_result_manifest(run) {
  if (run === null || typeof run !== "object") {
    const rtnval2 = null;
    return rtnval2;
  }
  const candidate_keys = ["result_manifest", "manifest"];
  for (const key of candidate_keys) {
    const value = run[key];
    if (value !== void 0 && value !== null && typeof value === "object") {
      const rtnval2 = value;
      return rtnval2;
    }
  }
  const rtnval = null;
  return rtnval;
}
function manifest_artifacts(manifest) {
  const rtnval = [];
  const html_path = manifest.html_summary_artifact_path;
  if (html_path !== null && html_path !== void 0 && html_path.length > 0) {
    rtnval.push({ label: "Test summary (HTML)", path: html_path });
  }
  const summary_path = manifest.summary_artifact_path;
  if (summary_path !== null && summary_path !== void 0 && summary_path.length > 0) {
    rtnval.push({ label: "Run summary (JSON)", path: summary_path });
  }
  const results_path = manifest.results_artifact_path;
  if (results_path !== null && results_path !== void 0 && results_path.length > 0) {
    rtnval.push({ label: "Consolidated results (JSON)", path: results_path });
  }
  const stream_path = manifest.results_stream_artifact_path;
  if (stream_path !== null && stream_path !== void 0 && stream_path.length > 0) {
    rtnval.push({ label: "Raw results stream", path: stream_path });
  }
  const files = manifest.files;
  if (Array.isArray(files) === true) {
    const known_paths = [];
    for (const entry of rtnval) {
      known_paths.push(entry.path);
    }
    for (const file_entry of files) {
      if (file_entry === null || typeof file_entry !== "object") {
        continue;
      }
      const relative_path = file_entry.relative_path;
      if (typeof relative_path !== "string" || relative_path.length === 0) {
        continue;
      }
      if (known_paths.indexOf(relative_path) >= 0) {
        continue;
      }
      const segments = relative_path.split("/");
      const file_name = segments[segments.length - 1];
      rtnval.push({ label: file_name, path: relative_path });
      known_paths.push(relative_path);
    }
  }
  return rtnval;
}
function artifact_url(run_id, artifact_path) {
  const encoded_run = encodeURIComponent(run_id);
  const segments = artifact_path.split("/");
  const encoded_segments = [];
  for (const segment of segments) {
    encoded_segments.push(encodeURIComponent(segment));
  }
  const encoded_path = encoded_segments.join("/");
  const rtnval = RUNS_API_PATH + "/" + encoded_run + "/artifacts/" + encoded_path;
  return rtnval;
}
class PycRunDetail extends HTMLElement {
  _run_id;
  _run;
  _loading;
  _errored;
  _error_status;
  _invalid_id;
  _terminal;
  _stream_status;
  _source;
  _root;
  _cancel_pending;
  _cancel_notice;
  _project_names;
  _latest_progress;
  _latest_manifest;
  constructor() {
    super();
    this._run_id = "";
    this._run = null;
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._invalid_id = false;
    this._terminal = false;
    this._stream_status = "idle";
    this._source = null;
    this._root = null;
    this._cancel_pending = false;
    this._cancel_notice = null;
    this._project_names = {};
    this._latest_progress = null;
    this._latest_manifest = null;
  }
  /**
   * Observed attributes -- ``run-id`` may be supplied explicitly
   * by a host; otherwise it is read from the path on mount.
   */
  static get observedAttributes() {
    const rtnval = ["run-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      runId: this._run_id,
      loading: this._loading,
      errored: this._errored,
      errorStatus: this._error_status,
      invalidId: this._invalid_id,
      streamStatus: this._stream_status,
      terminal: this._terminal,
      cancelPending: this._cancel_pending
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the run id, render the chrome,
   * fetch the initial snapshot (plus the projects collection for
   * the project display name), and open the live stream.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("run-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._run_id = attr_id;
    } else {
      this._run_id = run_id_from_path(window.location.pathname);
    }
    this._render_chrome();
    void this._load();
    void this._load_projects();
    return;
  }
  /**
   * Fetch the projects collection once and build the
   * id -> display-name map for the summary's project field. A
   * failed fetch leaves the map empty -- the field falls back to
   * the short project id.
   */
  async _load_projects() {
    const projects = await fetch_projects();
    if (projects === null) {
      this._project_names = {};
      return;
    }
    this._project_names = project_display_map(projects);
    if (this._run !== null) {
      this._render_body();
    }
    return;
  }
  /**
   * Resolve a project id to its display name, falling back to the
   * short form of the id when the projects collection did not
   * load or does not know the id. Never returns an empty string.
   *
   * @param project_id The run's project UUID.
   *
   * @returns A human-readable project label.
   */
  _project_display_name(project_id) {
    if (typeof project_id !== "string" || project_id.length === 0) {
      const rtnval2 = "—";
      return rtnval2;
    }
    const known = this._project_names[project_id];
    if (typeof known === "string" && known.length > 0) {
      const rtnval2 = known;
      return rtnval2;
    }
    const rtnval = short_run_id(project_id);
    return rtnval;
  }
  /**
   * Lifecycle hook -- close the live SSE connection so a
   * navigation away from the run never leaks a connection.
   */
  disconnectedCallback() {
    this._close_stream();
    return;
  }
  /**
   * Fetch the initial run snapshot then -- when the run is not
   * already terminal -- open the live event stream. Exposed so
   * unit tests can await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_run_id(this._run_id) === false) {
      this._invalid_id = true;
      this._loading = false;
      this._errored = false;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_body();
    let run = null;
    let error_status = 0;
    try {
      const url = RUNS_API_PATH + "/" + encodeURIComponent(this._run_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        error_status = response.status;
        throw new Error("run fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      run = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.runs.detail_fetch_failed",
        { reason: String(reason) }
      );
      if (error_status === 401) {
        emit_session_expired();
      }
      this._loading = false;
      this._errored = true;
      this._error_status = error_status;
      this._render_body();
      return;
    }
    this._run = run;
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._terminal = is_terminal_state(run.state);
    this._render_body();
    if (this._terminal === false) {
      this._open_stream();
    }
    return;
  }
  /**
   * POST the cancel request for this run after an explicit
   * confirmation. Drives the pending state on the cancel button,
   * surfaces status-specific failure messages through the cancel
   * notice, and re-fetches the run on success (and on a 409 --
   * the run's state moved under us either way). Exposed so unit
   * tests can await a cancel cycle.
   */
  async requestCancel() {
    await this._request_cancel();
    return;
  }
  async _request_cancel() {
    if (this._cancel_pending === true) {
      return;
    }
    const confirmed = window.confirm(
      "Cancel this run? A cancellation request will be sent to the orchestrator."
    );
    if (confirmed === false) {
      return;
    }
    this._cancel_pending = true;
    this._cancel_notice = null;
    this._render_body();
    this._render_cancel_notice();
    const url = RUNS_API_PATH + "/" + encodeURIComponent(this._run_id) + "/cancel";
    let response = null;
    try {
      response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: "{}"
      });
    } catch (reason) {
      console.warn(
        "pychestrate.ui.runs.cancel_request_failed",
        { reason: String(reason) }
      );
      this._cancel_pending = false;
      this._cancel_notice = {
        tone: "error",
        message: "Couldn't reach the server to cancel this run. Try again."
      };
      this._render_body();
      this._render_cancel_notice();
      return;
    }
    if (response.ok === true) {
      this._cancel_pending = false;
      this._cancel_notice = {
        tone: "ok",
        message: "Cancellation requested."
      };
      this._render_cancel_notice();
      await this._load();
      return;
    }
    let message = "Failed to cancel this run (HTTP " + String(response.status) + ").";
    if (response.status === 401) {
      emit_session_expired();
      message = "Your session has expired — sign in again.";
    }
    if (response.status === 403) {
      message = "You do not have permission to cancel runs.";
    }
    if (response.status === 409) {
      message = "This run can no longer be cancelled.";
      let problem = null;
      try {
        problem = await response.json();
      } catch (reason) {
        problem = null;
      }
      if (problem !== null && typeof problem === "object") {
        if (typeof problem.detail === "string" && problem.detail.length > 0) {
          message = problem.detail;
        } else if (typeof problem.reason === "string" && problem.reason.length > 0) {
          message = problem.reason;
        }
      }
    }
    this._cancel_pending = false;
    this._cancel_notice = {
      tone: "error",
      message
    };
    this._render_body();
    this._render_cancel_notice();
    if (response.status === 409) {
      await this._load();
    }
    return;
  }
  /**
   * Open the ``EventSource`` against the run's SSE event stream
   * and wire its handlers. A no-op when a stream is already
   * open or ``EventSource`` is unavailable.
   */
  _open_stream() {
    if (this._source !== null) {
      return;
    }
    if (typeof EventSource === "undefined") {
      return;
    }
    const url = RUNS_API_PATH + "/" + encodeURIComponent(this._run_id) + "/events";
    this._stream_status = "connecting";
    this._render_stream_banner();
    const source = new EventSource(url, { withCredentials: true });
    this._source = source;
    source.onopen = () => {
      this._stream_status = "open";
      this._render_stream_banner();
    };
    source.onmessage = (event) => {
      this._handle_stream_message(event);
    };
    source.onerror = () => {
      if (this._terminal === true) {
        this._close_stream();
        this._stream_status = "closed";
      } else {
        this._stream_status = "reconnecting";
      }
      this._render_stream_banner();
    };
    return;
  }
  /**
   * Close the live ``EventSource`` if one is open.
   */
  _close_stream() {
    if (this._source !== null) {
      this._source.close();
      this._source = null;
    }
    return;
  }
  /**
   * Parse one SSE message frame and apply it. Exposed so unit
   * tests can feed events without a real ``EventSource``.
   *
   * @param event The ``MessageEvent`` delivered by the stream.
   */
  handleStreamMessage(event) {
    this._handle_stream_message(event);
    return;
  }
  _handle_stream_message(event) {
    let parsed = null;
    try {
      parsed = JSON.parse(String(event.data));
    } catch (reason) {
      console.warn(
        "pychestrate.ui.runs.detail_event_parse_failed",
        { reason: String(reason) }
      );
      return;
    }
    if (parsed === null || typeof parsed.event_type !== "string") {
      return;
    }
    this._apply_event(parsed);
    return;
  }
  _apply_event(run_event) {
    if (run_event.event_type === "heartbeat") {
      return;
    }
    if (run_event.event_type === "state_changed") {
      if (this._run !== null && typeof run_event.state === "string") {
        this._run.state = run_event.state;
        if (run_event.terminal_outcome !== void 0 && run_event.terminal_outcome !== null) {
          this._run.terminal_outcome = run_event.terminal_outcome;
        }
        this._terminal = is_terminal_state(run_event.state);
      }
      this._render_body();
      if (this._terminal === true) {
        this._close_stream();
        this._stream_status = "closed";
        this._render_stream_banner();
      }
      return;
    }
    if (run_event.event_type === "progress") {
      if (run_event.progress !== void 0 && run_event.progress !== null) {
        this._latest_progress = run_event.progress;
        this._render_progress(run_event.progress);
      }
      return;
    }
    if (run_event.event_type === "result_manifest") {
      if (run_event.manifest !== void 0 && run_event.manifest !== null) {
        this._latest_manifest = run_event.manifest;
        this._render_artifacts(run_event.manifest);
      }
      return;
    }
    return;
  }
  /**
   * Build the persistent chrome -- heading + the body region
   * the data render replaces.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-run-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Run detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-run-detail__heading");
    heading.textContent = "Run detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-run-detail__back-link");
    back.setAttribute("href", "/runs");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to runs";
    root.appendChild(back);
    const banner = document.createElement("p");
    banner.classList.add("pyc-run-detail__banner");
    banner.setAttribute("data-role", "stream-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;
    root.appendChild(banner);
    const cancel_notice = document.createElement("p");
    cancel_notice.classList.add("pyc-run-detail__notice");
    cancel_notice.setAttribute("data-role", "cancel-notice");
    cancel_notice.setAttribute("role", "status");
    cancel_notice.hidden = true;
    root.appendChild(cancel_notice);
    const body = document.createElement("div");
    body.classList.add("pyc-run-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Re-render the body region from the current run snapshot,
   * driving the loading / error / loaded states.
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
      loading.classList.add("pyc-run-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading run\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._invalid_id === true || (this._errored === true && this._error_status === 404)) {
      const missing = document.createElement("p");
      missing.classList.add("pyc-run-detail__status");
      missing.setAttribute("data-role", "not-found-state");
      const missing_text = document.createElement("span");
      missing_text.textContent = "No run with this id. ";
      missing.appendChild(missing_text);
      const runs_link = document.createElement("a");
      runs_link.classList.add("pyc-run-detail__status-link");
      runs_link.setAttribute("href", "/runs");
      runs_link.textContent = "Back to runs";
      missing.appendChild(runs_link);
      body.replaceChildren(missing);
      return;
    }
    if (this._errored === true || this._run === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-run-detail__status",
        "pyc-run-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      const error_status = this._error_status;
      if (error_status === 401) {
        const expired_text = document.createElement("span");
        expired_text.textContent = "Your session has expired — sign in again. ";
        error.appendChild(expired_text);
        const login_link = document.createElement("a");
        login_link.classList.add("pyc-run-detail__status-link");
        login_link.setAttribute("href", login_next_url());
        login_link.textContent = "Sign in";
        error.appendChild(login_link);
      } else if (error_status === 403) {
        error.textContent = "You don't have access to runs.";
      } else if (error_status === 0) {
        error.textContent = "Couldn't reach the server. Check your connection and try refreshing.";
      } else {
        error.textContent = "Failed to load this run. Try refreshing.";
      }
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._run));
    const progress_section = document.createElement("section");
    progress_section.classList.add("pyc-run-detail__progress");
    progress_section.setAttribute("data-role", "progress-section");
    progress_section.setAttribute("role", "region");
    progress_section.setAttribute("aria-label", "Progress");
    fragment.appendChild(progress_section);
    const artifacts_section = document.createElement("section");
    artifacts_section.classList.add("pyc-run-detail__artifacts");
    artifacts_section.setAttribute("data-role", "artifacts-section");
    artifacts_section.setAttribute("role", "region");
    artifacts_section.setAttribute("aria-label", "Artifacts");
    fragment.appendChild(artifacts_section);
    body.replaceChildren(fragment);
    let progress = this._latest_progress;
    if (progress === null) {
      const summary = this._run.progress_summary;
      if (summary !== void 0 && summary !== null) {
        progress = summary;
      }
    }
    if (progress !== null) {
      this._render_progress(progress);
    }
    let manifest = this._latest_manifest;
    if (manifest === null) {
      manifest = resolve_result_manifest(this._run);
    }
    if (manifest !== null) {
      this._render_artifacts(manifest);
    } else if (this._terminal === true) {
      this._render_artifacts_placeholder();
    }
    return;
  }
  /**
   * Render the artifacts section for a terminal run whose
   * snapshot carries no result manifest -- the heading plus an
   * explicit "nothing recorded" note, so a finished run never
   * shows a silently empty pane.
   */
  _render_artifacts_placeholder() {
    if (this._root === null) {
      return;
    }
    const section = this._root.querySelector('[data-role="artifacts-section"]');
    if (section === null) {
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-run-detail__section-heading");
    heading.textContent = "Artifacts";
    const empty = document.createElement("p");
    empty.classList.add("pyc-run-detail__artifact-empty");
    empty.setAttribute("data-role", "artifacts-empty");
    empty.textContent = "No artifacts recorded for this run.";
    section.replaceChildren(heading, empty);
    return;
  }
  /**
   * Update the cancel-outcome notice from ``_cancel_notice`` --
   * hidden when there is nothing to report.
   */
  _render_cancel_notice() {
    if (this._root === null) {
      return;
    }
    const notice = this._root.querySelector('[data-role="cancel-notice"]');
    if (notice === null || notice instanceof HTMLElement === false) {
      return;
    }
    const el = notice;
    if (this._cancel_notice === null) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.setAttribute("data-tone", this._cancel_notice.tone);
    el.textContent = this._cancel_notice.message;
    return;
  }
  /**
   * Build the run summary block -- identity, state badge,
   * dispatch attempt, timestamps, and terminal outcome.
   *
   * @param run The current run snapshot.
   *
   * @returns A populated summary section element.
   */
  _build_summary(run) {
    const section = document.createElement("section");
    section.classList.add("pyc-run-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Run summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-run-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-run-detail__run-id");
    id_value.setAttribute("data-role", "run-id");
    id_value.textContent = short_run_id(run.run_id);
    set_entity_title("Run " + short_run_id(run.run_id));
    id_value.title = run.run_id;
    id_row.appendChild(id_value);
    const badge = document.createElement("mj-chip");
    badge.classList.add("pyc-run-detail__badge");
    badge.setAttribute("data-role", "state-badge");
    badge.setAttribute("data-tone", state_badge_tone(run.state));
    badge.textContent = run.state;
    id_row.appendChild(badge);
    if (is_terminal_state(run.state) === false) {
      const cancel_button = document.createElement("mj-button");
      cancel_button.classList.add("pyc-run-detail__cancel-button");
      cancel_button.setAttribute("type", "button");
      cancel_button.setAttribute("data-role", "cancel-button");
      if (this._cancel_pending === true) {
        cancel_button.textContent = "Cancelling…";
        cancel_button.setAttribute("disabled", "");
      } else {
        cancel_button.textContent = "Cancel run";
      }
      cancel_button.addEventListener("click", () => {
        void this._request_cancel();
      });
      id_row.appendChild(cancel_button);
    }
    section.appendChild(id_row);
    const waiting = waiting_for_pod_message(run);
    if (waiting !== null) {
      const banner = document.createElement("p");
      banner.classList.add("pyc-run-detail__banner");
      banner.setAttribute("data-role", "waiting-for-pod");
      banner.setAttribute("data-tone", waiting.tone);
      banner.setAttribute("role", "status");
      banner.textContent = waiting.text;
      section.appendChild(banner);
    }
    const grid = document.createElement("dl");
    grid.classList.add("pyc-run-detail__grid");
    this._append_field(
      grid,
      "Project",
      this._project_display_name(run.project_id),
      run.project_id
    );
    const assigned = run.assigned_client;
    if (assigned !== null && assigned !== void 0 && typeof assigned.pod_name === "string" && assigned.pod_name.length > 0) {
      this._append_field(grid, "Pod", assigned.pod_name, run.pod_id);
    } else {
      this._append_field(grid, "Pod", run.pod_id);
    }
    this._append_field(grid, "Job type", run.job_type);
    const job_name = run.job_name;
    if (job_name !== void 0 && job_name !== null && job_name.length > 0) {
      this._append_field(grid, "Job name", job_name);
    }
    const attempt_field = document.createElement("div");
    attempt_field.classList.add("pyc-run-detail__field");
    const attempt_term = document.createElement("dt");
    attempt_term.textContent = "Dispatch attempt";
    const attempt_def = document.createElement("dd");
    attempt_def.setAttribute("data-role", "dispatch-attempt");
    const attempt = run.current_dispatch_attempt_id;
    if (attempt !== void 0 && attempt !== null && attempt.length > 0) {
      attempt_def.textContent = attempt;
    } else {
      attempt_def.textContent = "\u2014";
    }
    attempt_field.appendChild(attempt_term);
    attempt_field.appendChild(attempt_def);
    grid.appendChild(attempt_field);
    this._append_field(grid, "Created", format_timestamp(run.created_at));
    this._append_field(grid, "Dispatched", format_timestamp(run.dispatched_at));
    this._append_field(grid, "Started", format_timestamp(run.started_at));
    this._append_field(grid, "Completed", format_timestamp(run.completed_at));
    const outcome_field = document.createElement("div");
    outcome_field.classList.add("pyc-run-detail__field");
    const outcome_term = document.createElement("dt");
    outcome_term.textContent = "Terminal outcome";
    const outcome_def = document.createElement("dd");
    outcome_def.setAttribute("data-role", "terminal-outcome");
    const outcome = run.terminal_outcome;
    if (outcome !== void 0 && outcome !== null && outcome.length > 0) {
      outcome_def.textContent = outcome;
    } else {
      outcome_def.textContent = "\u2014";
    }
    outcome_field.appendChild(outcome_term);
    outcome_field.appendChild(outcome_def);
    grid.appendChild(outcome_field);
    // Why the run ended as it did -- the pod's note, a rejected dispatch, a
    // passed deadline -- so a failed run is never shown without a cause.
    const reason = run.outcome_reason;
    if (typeof reason === "string" && reason.length > 0) {
      this._append_field(grid, "Reason", reason);
      const reason_def = grid.lastElementChild.querySelector("dd");
      if (reason_def !== null) {
        reason_def.setAttribute("data-role", "outcome-reason");
        reason_def.classList.add("pyc-run-detail__outcome-reason");
      }
    }
    section.appendChild(grid);
    return section;
  }
  /**
   * Append one labelled field to a definition-list grid. Absent
   * values render as an em dash so a null field never shows as a
   * blank cell.
   *
   * @param grid The ``<dl>`` to append into.
   * @param label The field's display label.
   * @param value The field's display value.
   * @param title_value Optional hover title (e.g. the full UUID
   *                    behind a display name).
   */
  _append_field(grid, label, value, title_value) {
    const field = document.createElement("div");
    field.classList.add("pyc-run-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    if (value === void 0 || value === null || String(value).length === 0) {
      def.textContent = "—";
    } else {
      def.textContent = String(value);
    }
    if (typeof title_value === "string" && title_value.length > 0) {
      def.title = title_value;
    }
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  /**
   * Render the progress section from a ``ProgressSummary``
   * roll-up -- pass/fail/total counts plus a progress bar.
   *
   * @param progress A ``ProgressSummary`` payload.
   */
  _render_progress(progress) {
    if (this._root === null) {
      return;
    }
    const section = this._root.querySelector('[data-role="progress-section"]');
    if (section === null) {
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-run-detail__section-heading");
    heading.textContent = "Progress";
    section.replaceChildren(heading);
    if (is_test_run(this._run) === true && has_test_counts(progress) === true) {
      const total = progress.tests_total;
      const counts = document.createElement("div");
      counts.classList.add("pyc-run-detail__counts");
      this._append_count(counts, "Passed", coerce_count(progress.tests_passed), "ok");
      this._append_count(counts, "Failed", coerce_count(progress.tests_failed), "error");
      this._append_count(counts, "Errored", coerce_count(progress.tests_errored), "error");
      this._append_count(counts, "Skipped", coerce_count(progress.tests_skipped), "warn");
      if (typeof total === "number") {
        this._append_count(counts, "Total", total, "neutral");
      }
      section.appendChild(counts);
    }
    const phase = progress.phase;
    const status_text = progress.status;
    const has_phase = typeof phase === "string" && phase.length > 0;
    const has_status = typeof status_text === "string" && status_text.length > 0;
    if (has_phase === true || has_status === true) {
      const phase_el = document.createElement("p");
      phase_el.classList.add("pyc-run-detail__progress-phase");
      phase_el.setAttribute("data-role", "progress-phase");
      const parts = [];
      if (has_phase === true) {
        parts.push("Phase: " + phase);
      }
      if (has_status === true) {
        parts.push("Status: " + status_text);
      }
      phase_el.textContent = parts.join(" · ");
      section.appendChild(phase_el);
    }
    const percent = progress_percent(progress);
    const bar = document.createElement("div");
    bar.classList.add("pyc-run-detail__bar");
    bar.setAttribute("data-role", "progress-bar");
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-valuenow", String(Math.round(percent)));
    const fill = document.createElement("div");
    fill.classList.add("pyc-run-detail__bar-fill");
    // A finished run's bar takes its outcome's tone: a failed run's
    // full bar was the same blue as a healthy one (ORC-09).
    fill.setAttribute("data-tone", progress_bar_tone(this._run));
    fill.style.width = String(percent) + "%";
    bar.appendChild(fill);
    section.appendChild(bar);
    const notes = progress.notes;
    if (notes !== void 0 && notes !== null && notes.length > 0) {
      const notes_el = document.createElement("p");
      notes_el.classList.add("pyc-run-detail__progress-notes");
      notes_el.setAttribute("data-role", "progress-notes");
      notes_el.textContent = notes;
      section.appendChild(notes_el);
    }
    return;
  }
  /**
   * Append one labelled count chip to the progress counts row.
   *
   * @param container The counts container element.
   * @param label The count's display label.
   * @param value The numeric count.
   * @param tone Coarse tone driving the chip color.
   */
  _append_count(container, label, value, tone) {
    const chip = document.createElement("span");
    chip.classList.add("pyc-run-detail__count");
    chip.setAttribute("data-tone", tone);
    const count = document.createElement("strong");
    count.textContent = String(value);
    const caption = document.createElement("span");
    caption.textContent = label;
    chip.appendChild(count);
    chip.appendChild(caption);
    container.appendChild(chip);
    return;
  }
  /**
   * Render the artifacts section from a ``ResultManifest`` --
   * the pass/fail rollup plus a list of artifact links with the
   * HTML test summary surfaced first.
   *
   * @param manifest A ``ResultManifest`` payload.
   */
  _render_artifacts(manifest) {
    if (this._root === null) {
      return;
    }
    const section = this._root.querySelector('[data-role="artifacts-section"]');
    if (section === null) {
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-run-detail__section-heading");
    heading.textContent = "Artifacts";
    const rollup = document.createElement("p");
    rollup.classList.add("pyc-run-detail__rollup");
    rollup.setAttribute("data-role", "artifacts-rollup");
    if (is_test_run(this._run) === true) {
      const passed = manifest.tests_passed;
      const failed = manifest.tests_failed;
      const passed_text = passed === void 0 || passed === null ? 0 : passed;
      const failed_text = failed === void 0 || failed === null ? 0 : failed;
      rollup.textContent = "Outcome " + manifest.terminal_outcome + " \xB7 " + String(passed_text) + " passed \xB7 " + String(failed_text) + " failed";
    } else {
      rollup.textContent = "Outcome " + manifest.terminal_outcome;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-run-detail__artifact-list");
    list.setAttribute("data-role", "artifact-list");
    const artifacts = manifest_artifacts(manifest);
    if (artifacts.length === 0) {
      const empty = document.createElement("li");
      empty.classList.add("pyc-run-detail__artifact-empty");
      empty.textContent = "No artifacts recorded for this run.";
      list.appendChild(empty);
    } else {
      for (const artifact of artifacts) {
        const item = document.createElement("li");
        item.classList.add("pyc-run-detail__artifact");
        const link = document.createElement("a");
        link.classList.add("pyc-run-detail__artifact-link");
        link.setAttribute(
          "href",
          artifact_url(this._run_id, artifact.path)
        );
        link.setAttribute("rel", "noopener noreferrer");
        link.textContent = artifact.label;
        if (artifact.path.endsWith("testsummary.html") === true) {
          link.setAttribute("data-role", "summary-link");
        }
        item.appendChild(link);
        const path_hint = document.createElement("span");
        path_hint.classList.add("pyc-run-detail__artifact-path");
        path_hint.textContent = artifact.path;
        item.appendChild(path_hint);
        list.appendChild(item);
      }
    }
    section.replaceChildren(heading, rollup, list);
    return;
  }
  /**
   * Update the consolidated stream-status banner. Shows a
   * reconnecting affordance while the stream is down and a
   * "live updates ended" note once a terminal run's stream
   * closes.
   */
  _render_stream_banner() {
    if (this._root === null) {
      return;
    }
    const banner = this._root.querySelector('[data-role="stream-banner"]');
    if (banner === null || banner instanceof HTMLElement === false) {
      return;
    }
    const el = banner;
    if (this._stream_status === "reconnecting") {
      el.hidden = false;
      el.setAttribute("data-tone", "warn");
      el.textContent = "Live updates interrupted \u2014 reconnecting\u2026";
      return;
    }
    if (this._stream_status === "closed" && this._terminal === true) {
      el.hidden = false;
      el.setAttribute("data-tone", "neutral");
      el.textContent = "Run finished \u2014 live updates ended.";
      return;
    }
    el.hidden = true;
    el.textContent = "";
    return;
  }
}
export {
  PycRunDetail,
  TERMINAL_RUN_STATES,
  artifact_url,
  is_terminal_state,
  is_test_run,
  is_valid_run_id,
  progress_bar_tone,
  waiting_for_pod_message,
  manifest_artifacts,
  progress_percent,
  run_id_from_path
};
