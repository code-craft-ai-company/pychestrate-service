import { show_no_projects } from "../shared/empty-state.js";
import { choose_project_id, mirror_to_query } from "../shared/view-state.js";
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
function build_test_metrics_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/test-metrics";
  return rtnval;
}
function list_load_message_for_status(status, what) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to " + what + ".";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This project was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the server \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load " + what + " (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function announce_session_expired() {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(
    new CustomEvent("pyc-session-401", {
      bubbles: false,
      detail: {}
    })
  );
  return;
}
function format_rate(rate) {
  if (typeof rate !== "number" || Number.isFinite(rate) === false) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const clamped = Math.min(1, Math.max(0, rate));
  const percent = Math.round(clamped * 100);
  // A rate that is not exactly 0 or 1 must not read as 0% or 100%: a 99.6%
  // pass rate is not "100%" and a 0.4% failure rate is not "0%" (ORC-36).
  if (clamped > 0 && percent === 0) {
    const rtnval2 = "<1%";
    return rtnval2;
  }
  if (clamped < 1 && percent === 100) {
    const rtnval2 = ">99%";
    return rtnval2;
  }
  const rtnval = String(percent) + "%";
  return rtnval;
}
function format_duration(seconds) {
  if (seconds === null || seconds === void 0 || Number.isFinite(seconds) === false) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  if (seconds < 60) {
    const rtnval2 = seconds.toFixed(1) + "s";
    return rtnval2;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  const rtnval = String(minutes) + "m " + String(remainder) + "s";
  return rtnval;
}
function compute_bar_fractions(durations) {
  const rtnval = [];
  if (Array.isArray(durations) === false || durations.length === 0) {
    return rtnval;
  }
  let max_value = 0;
  for (const value of durations) {
    if (typeof value === "number" && value > max_value) {
      max_value = value;
    }
  }
  if (max_value <= 0) {
    for (let index = 0; index < durations.length; index = index + 1) {
      rtnval.push(0);
    }
    return rtnval;
  }
  for (const value of durations) {
    const safe = typeof value === "number" && value > 0 ? value : 0;
    rtnval.push(safe / max_value);
  }
  return rtnval;
}
class PycTestMetrics extends HTMLElement {
  _state;
  _projects;
  _projectsAvailable;
  _projectsNoticeKind;
  _projects_notice_region;
  _summary;
  _root;
  _content_region;
  constructor() {
    super();
    this._state = {
      projectId: "",
      loading: false,
      errored: false,
      errorStatus: 0
    };
    this._projects = [];
    this._projectsAvailable = false;
    this._projectsNoticeKind = "";
    this._projects_notice_region = null;
    this._summary = null;
    this._root = null;
    this._content_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the
   * project + load state without scraping the DOM.
   */
  get viewState() {
    const rtnval = {
      projectId: this._state.projectId,
      loading: this._state.loading,
      errored: this._state.errored,
      errorStatus: this._state.errorStatus
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
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.textContent = "Test Metrics";
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
    const content_region = document.createElement("div");
    content_region.classList.add("pyc-metrics__content-region");
    content_region.setAttribute("data-role", "content-region");
    root.appendChild(content_region);
    this._content_region = content_region;
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
        projects = extract_projects(body);
      } else {
        load_failed = true;
      }
    } catch (reason) {
      load_failed = true;
      console.warn(
        "pychestrate.ui.metrics.projects_fetch_failed",
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
      this._render_content();
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
   * Re-fetch the test-metrics summary for the current project
   * and re-render the content region. Exposed so unit tests can
   * await a render cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    if (this._state.projectId.length === 0) {
      this._render_content();
      return;
    }
    // The address describes what is on screen (ORC-27).
    mirror_to_query({ project_id: this._state.projectId });
    this._state.loading = true;
    this._state.errored = false;
    this._state.errorStatus = 0;
    this._render_content();
    let summary = null;
    let errored = false;
    let error_status = 0;
    try {
      const url = build_test_metrics_url(this._state.projectId);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        summary = body;
      } else {
        errored = true;
        error_status = response.status;
        if (error_status === 401) {
          announce_session_expired();
        }
      }
    } catch (reason) {
      errored = true;
      error_status = 0;
      console.warn(
        "pychestrate.ui.metrics.test_metrics_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._state.loading = false;
    this._state.errored = errored;
    this._state.errorStatus = error_status;
    this._summary = summary;
    this._render_content();
    return;
  }
  _render_content() {
    if (this._content_region === null) {
      return;
    }
    const region = this._content_region;
    region.replaceChildren();
    if (this._state.projectId.length === 0) {
      if (this._projectsNoticeKind === "empty") {
        // The notice above already says there are no projects and links to
        // creating one; a second line asking to "select a project" contradicted it.
        region.replaceChildren();
        return;
      }
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "no-project-state");
      notice.textContent = "Select a project to view test metrics.";
      region.appendChild(notice);
      return;
    }
    if (this._state.loading === true) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.textContent = "Loading test metrics\u2026";
      region.appendChild(notice);
      return;
    }
    if (this._state.errored === true || this._summary === null) {
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.classList.add("pyc-metrics__notice--error");
      notice.setAttribute("data-role", "error-state");
      notice.textContent = list_load_message_for_status(
        this._state.errorStatus,
        "test metrics"
      );
      region.appendChild(notice);
      if (this._state.errorStatus === 0 || this._state.errorStatus >= 500) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-metrics__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "list-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._refresh();
        });
        region.appendChild(retry);
      }
      return;
    }
    if (this._summary.summary.run_count === 0) {
      // No runs is not "Pass rate 0%": say so, and say how to get data (ORC-34).
      const notice = document.createElement("div");
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "empty-state");
      notice.appendChild(document.createTextNode("No test runs have reported results for this project yet, so there is nothing to measure. "));
      const link = document.createElement("a");
      link.classList.add("pyc-metrics__row-link");
      link.setAttribute("href", "/test-catalog?project_id=" + encodeURIComponent(this._state.projectId));
      link.setAttribute("data-role", "empty-next-step");
      link.textContent = "Run tests from the Test catalog";
      notice.appendChild(link);
      notice.appendChild(document.createTextNode("; the numbers appear after the first run."));
      region.appendChild(notice);
      return;
    }
    region.appendChild(this._build_cards(this._summary.summary));
    region.appendChild(
      this._build_duration_trend(this._summary.recent_runs)
    );
    region.appendChild(
      this._build_runs_table(this._summary.recent_runs)
    );
    return;
  }
  _build_cards(rollup) {
    const cards = document.createElement("div");
    cards.classList.add("pyc-metrics__cards");
    cards.setAttribute("data-role", "rollup-cards");
    const entries = [
      {
        label: "Pass rate",
        value: format_rate(rollup.pass_rate),
        tone: "ok"
      },
      {
        label: "Fail rate",
        value: format_rate(rollup.fail_rate),
        tone: "error"
      },
      {
        // The share of runs with any failed or errored test -- not a
        // flake rate: no flaky-test detection exists yet.
        label: "Failed-run rate",
        value: format_rate(rollup.failed_run_rate),
        tone: "warn",
        role: "failed-run-rate",
        title: "Share of runs with at least one failed or errored test. This is not a flake rate: flaky tests are not detected yet."
      },
      {
        label: "Runs",
        value: String(rollup.run_count),
        tone: "neutral"
      },
      {
        label: "Tests total",
        value: String(rollup.tests_total),
        tone: "neutral"
      },
      {
        label: "Avg duration",
        value: format_duration(rollup.average_run_duration_seconds),
        tone: "neutral"
      }
    ];
    for (const entry of entries) {
      const card = document.createElement("div");
      card.classList.add("pyc-metrics__card");
      if (entry.tone !== "neutral") {
        card.classList.add("pyc-metrics__card--" + entry.tone);
      }
      const label = document.createElement("span");
      label.classList.add("pyc-metrics__card-label");
      label.textContent = entry.label;
      const value = document.createElement("span");
      value.classList.add("pyc-metrics__card-value");
      value.textContent = entry.value;
      if (typeof entry.role === "string") {
        card.setAttribute("data-role", entry.role);
      }
      if (typeof entry.title === "string") {
        card.setAttribute("title", entry.title);
      }
      card.appendChild(label);
      card.appendChild(value);
      cards.appendChild(card);
    }
    return cards;
  }
  _build_duration_trend(runs) {
    const durations = [];
    const ordered = runs.slice().reverse();
    for (const run of ordered) {
      const value = run.duration_seconds;
      durations.push(
        typeof value === "number" && Number.isFinite(value) ? value : 0
      );
    }
    const fractions = compute_bar_fractions(durations);
    const bars = document.createElement("div");
    bars.classList.add("pyc-metrics__bars");
    bars.setAttribute("data-role", "duration-trend");
    for (let index = 0; index < fractions.length; index = index + 1) {
      const fraction = fractions[index];
      const bar = document.createElement("div");
      bar.classList.add("pyc-metrics__bar");
      const run = ordered[index];
      const failed = typeof run.tests_failed === "number" && run.tests_failed > 0;
      if (failed === true) {
        bar.classList.add("pyc-metrics__bar--error");
      }
      const percent = Math.round(fraction * 100);
      bar.style.height = String(Math.max(2, percent)) + "%";
      bar.title = format_duration(durations[index]);
      bars.appendChild(bar);
    }
    return bars;
  }
  _build_runs_table(runs) {
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-metrics__table");
    table.setAttribute("data-role", "runs-table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-metrics__row";
    table.rowAttrs = (run) => ({ "data-run-id": run.run_id });
    table.columns = [
      {
        key: "run_id",
        label: "Run",
        width: "10rem",
        render: (run) => {
          const link = document.createElement("a");
          link.classList.add("pyc-metrics__row-link");
          link.setAttribute("data-role", "run-link");
          link.setAttribute(
            "href",
            "/runs/" + encodeURIComponent(run.run_id)
          );
          link.textContent = short_metric_id(run.run_id);
          link.title = run.run_id;
          return link;
        }
      },
      {
        key: "parser_tag",
        label: "Parser",
        width: "10rem",
        render: (run) =>
          run.parser_tag !== null && run.parser_tag !== void 0
            ? run.parser_tag
            : "\u2014"
      },
      {
        key: "tests_total",
        label: "Total",
        width: "8rem",
        render: (run) =>
          String(typeof run.tests_total === "number" ? run.tests_total : 0)
      },
      {
        key: "tests_passed",
        label: "Passed",
        width: "8rem",
        render: (run) =>
          String(typeof run.tests_passed === "number" ? run.tests_passed : 0)
      },
      {
        key: "tests_failed",
        label: "Failed",
        width: "8rem",
        render: (run) =>
          String(typeof run.tests_failed === "number" ? run.tests_failed : 0)
      },
      {
        key: "duration",
        label: "Duration",
        width: "10rem",
        render: (run) => format_duration(run.duration_seconds)
      }
    ];
    table.rows = runs;
    return table;
  }
}
function short_metric_id(value) {
  if (typeof value !== "string" || value.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const dash_index = value.indexOf("-");
  if (dash_index > 0) {
    const rtnval2 = value.slice(0, dash_index);
    return rtnval2;
  }
  if (value.length > 12) {
    const rtnval2 = value.slice(0, 12);
    return rtnval2;
  }
  const rtnval = value;
  return rtnval;
}
function extract_projects(body) {
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
export {
  PycTestMetrics,
  announce_session_expired,
  build_test_metrics_url,
  compute_bar_fractions,
  extract_projects,
  format_duration,
  format_rate,
  list_load_message_for_status,
  short_metric_id
};
