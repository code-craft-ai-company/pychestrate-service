import {
  announce_session_expired,
  build_state_tone,
  format_timestamp,
  is_terminal_build_state,
  short_id
} from "./builds-list-view.js";
const PROJECTS_API_PATH = "/api/v1/projects";
const POLL_INTERVAL_MS = 5e3;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function build_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/builds/";
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
  const rtnval = value;
  return rtnval;
}
function is_valid_build_id(build_id) {
  if (typeof build_id !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(build_id);
  return rtnval;
}
function detail_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to builds.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This build was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the build service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load this build (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function build_detail_url(project_id, build_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/builds/" + encodeURIComponent(build_id);
  return rtnval;
}
function build_artifacts_url(project_id, build_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/builds/" + encodeURIComponent(build_id) + "/artifacts";
  return rtnval;
}
class PycBuildDetail extends HTMLElement {
  _build_id;
  _project_id;
  _build;
  _artifacts;
  _loading;
  _errored;
  _error_kind;
  _error_status;
  _terminal;
  _poll_status;
  _poll_timer;
  _root;
  constructor() {
    super();
    this._build_id = "";
    this._project_id = "";
    this._build = null;
    this._artifacts = [];
    this._loading = false;
    this._errored = false;
    this._error_kind = "";
    this._error_status = 0;
    this._terminal = false;
    this._poll_status = "idle";
    this._poll_timer = null;
    this._root = null;
  }
  /**
   * Observed attributes -- ``build-id`` and ``project-id`` may be
   * supplied explicitly by a host; otherwise they are read from
   * the URL on mount.
   */
  static get observedAttributes() {
    const rtnval = ["build-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      buildId: this._build_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored,
      errorKind: this._error_kind,
      errorStatus: this._error_status,
      pollStatus: this._poll_status,
      terminal: this._terminal
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the build + project ids, render the
   * chrome, and fetch the initial snapshot. The project id rides
   * on the detail link's ``?project_id=`` query parameter because
   * builds are only addressable through the project-scoped API.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("build-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._build_id = attr_id;
    } else {
      this._build_id = build_id_from_path(window.location.pathname);
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
   * away from the build never leaks a timer.
   */
  disconnectedCallback() {
    this._stop_poll();
    return;
  }
  /**
   * Fetch the build snapshot + artifacts then -- when the build
   * is not already terminal -- start the live-poll loop. Exposed
   * so unit tests can await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_build_id(this._build_id) === false) {
      this._loading = false;
      this._errored = true;
      this._error_kind = "invalid-id";
      this._render_body();
      return;
    }
    if (this._project_id.length === 0) {
      this._loading = false;
      this._errored = true;
      this._error_kind = "missing-project";
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._error_kind = "";
    this._render_body();
    const build = await this._fetch_build();
    if (build === null) {
      this._loading = false;
      this._errored = true;
      this._error_kind = "http";
      this._render_body();
      return;
    }
    this._build = build;
    this._project_id = build.project_id;
    this._loading = false;
    this._errored = false;
    this._terminal = is_terminal_build_state(build.state);
    this._render_body();
    await this._load_artifacts();
    if (this._terminal === false) {
      this._start_poll();
    } else {
      this._poll_status = "stopped";
      this._render_poll_banner();
    }
    return;
  }
  /**
   * Fetch the current build snapshot from the project-scoped
   * endpoint -- builds have no project-agnostic resolver, so the
   * project id must already be known (threaded through the detail
   * link's ``?project_id=`` query parameter).
   *
   * @returns The ``BuildRun`` snapshot, or ``null`` on failure.
   */
  async _fetch_build() {
    const url = build_detail_url(this._project_id, this._build_id);
    this._error_status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      this._error_status = response.status;
      if (response.ok === false) {
        if (response.status === 401) {
          announce_session_expired();
        }
        throw new Error("build fetch failed: HTTP " + String(response.status));
      }
      const body = await response.json();
      this._error_status = 0;
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.detail_fetch_failed",
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  /**
   * Fetch the build's artifact manifest. A failed fetch leaves
   * the artifacts list empty -- the section renders an empty
   * state rather than an error.
   */
  async _load_artifacts() {
    if (this._project_id.length === 0) {
      return;
    }
    try {
      const url = build_artifacts_url(this._project_id, this._build_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (page !== null && Array.isArray(page.items) === true) {
          this._artifacts = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.builds.artifacts_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._render_artifacts();
    return;
  }
  /**
   * Start the live-poll loop. A no-op when a poll is already
   * scheduled.
   */
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
   * Run one poll cycle -- re-fetch the build snapshot, re-render,
   * and either reschedule (still non-terminal) or stop (now
   * terminal). Exposed so unit tests can drive a poll cycle
   * without waiting on a real timer.
   */
  async pollOnce() {
    await this._poll_once();
    return;
  }
  async _poll_once() {
    const build = await this._fetch_build();
    if (build !== null) {
      this._build = build;
      this._project_id = build.project_id;
      this._terminal = is_terminal_build_state(build.state);
      this._render_body();
      await this._load_artifacts();
    }
    if (this._terminal === true) {
      this._stop_poll();
      this._poll_status = "stopped";
      this._render_poll_banner();
      return;
    }
    this._schedule_poll();
    return;
  }
  /**
   * Stop the live-poll loop, clearing any pending timer.
   */
  _stop_poll() {
    if (this._poll_timer !== null) {
      clearTimeout(this._poll_timer);
      this._poll_timer = null;
    }
    return;
  }
  /**
   * Build the persistent chrome -- heading, back link, the poll
   * banner, and the body region the data render replaces.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-build-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Build detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-build-detail__heading");
    heading.textContent = "Build detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-build-detail__back-link");
    back.setAttribute("href", "/builds");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to builds";
    root.appendChild(back);
    const banner = document.createElement("p");
    banner.classList.add("pyc-build-detail__banner");
    banner.setAttribute("data-role", "poll-banner");
    banner.setAttribute("role", "status");
    banner.hidden = true;
    root.appendChild(banner);
    const body = document.createElement("div");
    body.classList.add("pyc-build-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Re-render the body region from the current build snapshot,
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
      loading.classList.add("pyc-build-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading build\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._build === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-build-detail__status",
        "pyc-build-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      if (this._error_kind === "missing-project") {
        error.textContent = "This link is missing its project context \u2014 open the build from the Builds list.";
      } else if (this._error_kind === "invalid-id") {
        error.textContent = "This build link is not valid \u2014 open the build from the Builds list.";
      } else {
        error.textContent = detail_load_message_for_status(this._error_status);
      }
      const children = [error];
      if (this._error_kind === "http") {
        if (this._error_status === 0 || this._error_status >= 500) {
          const retry = document.createElement("mj-button");
          retry.classList.add("pyc-build-detail__retry");
          retry.setAttribute("type", "button");
          retry.setAttribute("data-role", "detail-retry");
          retry.textContent = "Retry";
          retry.addEventListener("click", () => {
            void this._load();
          });
          children.push(retry);
        }
      }
      body.replaceChildren(...children);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._build));
    if (this._build.toolchain !== void 0 && this._build.toolchain !== null) {
      if (this._build.toolchain.length > 0) {
        fragment.appendChild(this._build_toolchain(this._build.toolchain));
      }
    }
    const artifacts_section = document.createElement("section");
    artifacts_section.classList.add("pyc-build-detail__artifacts");
    artifacts_section.setAttribute("data-role", "artifacts-section");
    artifacts_section.setAttribute("role", "region");
    artifacts_section.setAttribute("aria-label", "Artifacts");
    fragment.appendChild(artifacts_section);
    body.replaceChildren(fragment);
    this._render_artifacts();
    return;
  }
  /**
   * Build the build summary block -- identity, state badge,
   * runner kind, reproducibility digest, timestamps, and the
   * final-state reason.
   *
   * @param build The current build snapshot.
   *
   * @returns A populated summary section element.
   */
  _build_summary(build) {
    const section = document.createElement("section");
    section.classList.add("pyc-build-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Build summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-build-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-build-detail__build-id");
    id_value.setAttribute("data-role", "build-id");
    id_value.textContent = short_id(build.run_id);
    id_value.title = build.run_id;
    id_row.appendChild(id_value);
    const badge = document.createElement("mj-chip");
    badge.classList.add("pyc-build-detail__badge");
    badge.setAttribute("data-role", "state-badge");
    badge.setAttribute("data-tone", build_state_tone(build.state));
    badge.textContent = build.state;
    id_row.appendChild(badge);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-build-detail__grid");
    this._append_field(grid, "Project", build.project_id);
    this._append_field(grid, "Runner kind", build.runner_kind);
    this._append_field(grid, "Inputs digest", build.repro_digest_sha256, {
      title: "SHA-256 of the build's input files, toolchain and environment. Two builds with the same digest were made from the same inputs."
    });
    this._append_field(grid, "Started", format_timestamp(build.started_at));
    this._append_field(grid, "Finished", format_timestamp(build.finished_at));
    const layer5 = build.layer5_run_id;
    if (layer5 !== void 0 && layer5 !== null && layer5.length > 0) {
      this._append_field(grid, "Run", layer5, { href: "/runs/" + encodeURIComponent(layer5) });
    }
    const reason = build.final_state_reason;
    if (reason !== void 0 && reason !== null && reason.length > 0) {
      this._append_field(grid, "Final state reason", reason);
    }
    section.appendChild(grid);
    return section;
  }
  /**
   * Append one labelled field to a definition-list grid.
   *
   * @param grid The ``<dl>`` to append into.
   * @param label The field's display label.
   * @param value The field's display value.
   */
  _append_field(grid, label, value, options) {
    const field = document.createElement("div");
    field.classList.add("pyc-build-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    if (options !== void 0 && typeof options.href === "string") {
      // A reference to another page is a link, not a bare id.
      const link = document.createElement("a");
      link.href = options.href;
      link.textContent = value;
      def.appendChild(link);
    } else {
      def.textContent = value;
    }
    if (options !== void 0 && typeof options.title === "string") {
      term.title = options.title;
    }
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  /**
   * Build the toolchain-snapshot section -- one row per pinned
   * toolchain entry.
   *
   * @param toolchain The build's toolchain snapshot rows.
   *
   * @returns A populated toolchain section element.
   */
  _build_toolchain(toolchain) {
    const section = document.createElement("section");
    section.classList.add("pyc-build-detail__toolchain");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Toolchain");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-build-detail__section-heading");
    heading.textContent = "Toolchain";
    section.appendChild(heading);
    const list = document.createElement("ul");
    list.classList.add("pyc-build-detail__toolchain-list");
    for (const entry of toolchain) {
      const item = document.createElement("li");
      item.classList.add("pyc-build-detail__toolchain-entry");
      const key = document.createElement("strong");
      key.textContent = entry.key;
      item.appendChild(key);
      const version = entry.version;
      if (version !== void 0 && version !== null && version.length > 0) {
        const version_el = document.createElement("span");
        version_el.textContent = " " + version;
        item.appendChild(version_el);
      }
      list.appendChild(item);
    }
    section.appendChild(list);
    return section;
  }
  /**
   * Render the artifacts section from the current ``_artifacts``
   * list -- a heading plus one row per artifact, or an empty
   * state.
   */
  _render_artifacts() {
    if (this._root === null) {
      return;
    }
    const section = this._root.querySelector('[data-role="artifacts-section"]');
    if (section === null) {
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-build-detail__section-heading");
    heading.textContent = "Artifacts";
    const list = document.createElement("ul");
    list.classList.add("pyc-build-detail__artifact-list");
    list.setAttribute("data-role", "artifact-list");
    if (this._artifacts.length === 0) {
      const empty = document.createElement("li");
      empty.classList.add("pyc-build-detail__artifact-empty");
      empty.setAttribute("data-role", "artifacts-empty");
      empty.textContent = "No artifacts recorded for this build.";
      list.appendChild(empty);
    } else {
      for (const artifact of this._artifacts) {
        const item = document.createElement("li");
        item.classList.add("pyc-build-detail__artifact");
        const name = document.createElement("span");
        name.classList.add("pyc-build-detail__artifact-name");
        const display = artifact.artifact_name;
        name.textContent = display !== void 0 && display !== null && display.length > 0 ? display : artifact.artifact_id;
        item.appendChild(name);
        const type_chip = document.createElement("span");
        type_chip.classList.add("pyc-build-detail__artifact-type");
        type_chip.textContent = artifact.artifact_type;
        item.appendChild(type_chip);
        const storage = artifact.storage_uri;
        if (storage !== void 0 && storage !== null && storage.length > 0) {
          const link = document.createElement("a");
          link.classList.add("pyc-build-detail__artifact-link");
          link.setAttribute("href", storage);
          link.setAttribute("rel", "noopener noreferrer");
          link.textContent = "Download";
          item.appendChild(link);
        }
        const digest = document.createElement("span");
        digest.classList.add("pyc-build-detail__artifact-digest");
        digest.textContent = short_id(artifact.sha256);
        digest.title = artifact.sha256;
        item.appendChild(digest);
        list.appendChild(item);
      }
    }
    section.replaceChildren(heading, list);
    return;
  }
  /**
   * Update the live-poll status banner. Shows a "live updates
   * on" affordance while polling and a "build finished" note
   * once the build reaches a terminal state.
   */
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
      el.textContent = "Build in progress \u2014 refreshing every 5 seconds.";
      return;
    }
    if (this._poll_status === "stopped" && this._terminal === true) {
      el.hidden = false;
      el.setAttribute("data-tone", "neutral");
      el.textContent = "Build finished \u2014 live updates ended.";
      return;
    }
    el.hidden = true;
    el.textContent = "";
    return;
  }
}
export {
  PycBuildDetail,
  build_artifacts_url,
  build_detail_url,
  build_id_from_path,
  detail_load_message_for_status,
  is_valid_build_id,
  project_id_from_search
};
