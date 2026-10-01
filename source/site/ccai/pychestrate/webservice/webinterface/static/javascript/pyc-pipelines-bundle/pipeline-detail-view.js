import { hide_unless_may } from "../shared/permissions.js";
import { fetch_project_names, name_or_short } from "../shared/entity-names.js";
import { confirm_action } from "../shared/confirm.js";
import { with_access_request } from "../shared/admin-contact.js";
import { message_with_detail, read_problem_detail } from "../shared/problem-detail.js";
import { set_entity_title } from "../shared/page-title.js";
import { keep_list_state_on_back } from "../shared/view-state.js";
import {
  announce_session_expired,
  short_id,
  format_timestamp
} from "./pipelines-list-view.js";
const NODE_WIDTH = 140;
const NODE_HEIGHT = 44;
const COLUMN_GAP = 80;
const ROW_GAP = 24;
const CANVAS_PADDING = 20;
const PROJECTS_API_PATH = "/api/v1/projects";
function pipeline_delete_message_for_status(status, name) {
  if (status === 204 || status === 200) {
    const rtnval2 = "Pipeline \u201C" + name + "\u201D deleted.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This pipeline no longer exists.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to delete pipelines.";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to delete.";
    return rtnval2;
  }
  const rtnval = "Failed to delete the pipeline (HTTP " + String(status) + ").";
  return rtnval;
}
// ---- Runs of this pipeline (ORC-13): runs started over REST were invisible ----
function pipeline_runs_url(project_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/pipeline-runs?per_page=100";
  return rtnval;
}
function run_state_tone(state) {
  if (state === "completed" || state === "succeeded") {
    return "ok";
  }
  if (state === "failed" || state === "rejected") {
    return "error";
  }
  if (state === "cancelled" || state === "skipped") {
    return "warn";
  }
  return "neutral";
}
function words(text) {
  const spaced = typeof text === "string" ? text.replace(/_/g, " ").trim() : "";
  return spaced.length > 0 ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : "";
}
// "2 of 3 stages completed": what a run got through, in one line.
function stage_progress_text(run) {
  const stages = Array.isArray(run.stages) ? run.stages : [];
  if (stages.length === 0) {
    return "";
  }
  const done = stages.filter((stage) => stage.state === "completed" || stage.state === "succeeded").length;
  return String(done) + " of " + String(stages.length) + (stages.length === 1 ? " stage" : " stages") + " completed";
}
// Newest first; a run that has not started yet sorts as newest.
function sort_runs_newest_first(runs) {
  return runs.slice().sort((left, right) => {
    const a = left.started_at ? new Date(left.started_at).getTime() : Infinity;
    const b = right.started_at ? new Date(right.started_at).getTime() : Infinity;
    return b - a;
  });
}
function pipeline_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/pipelines/";
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
function pipeline_detail_url(project_id, pipeline_id) {
  const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(project_id) + "/pipelines/" + encodeURIComponent(pipeline_id);
  return rtnval;
}
function detail_load_message_for_status(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to pipelines.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This pipeline was not found \u2014 it may have been removed.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the pipeline service \u2014 check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load this pipeline (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
function compute_dag_columns(stages) {
  const known_ids = /* @__PURE__ */ new Set();
  for (const stage of stages) {
    known_ids.add(stage.stage_id);
  }
  const depth_by_id = /* @__PURE__ */ new Map();
  let progressed = true;
  while (progressed === true) {
    progressed = false;
    for (const stage of stages) {
      if (depth_by_id.has(stage.stage_id) === true) {
        continue;
      }
      const needs = stage.needs;
      let deepest = -1;
      let resolvable = true;
      if (needs !== void 0 && needs !== null) {
        for (const dep_id of needs) {
          if (known_ids.has(dep_id) === false) {
            continue;
          }
          const dep_depth = depth_by_id.get(dep_id);
          if (dep_depth === void 0) {
            resolvable = false;
            break;
          }
          if (dep_depth > deepest) {
            deepest = dep_depth;
          }
        }
      }
      if (resolvable === false) {
        continue;
      }
      depth_by_id.set(stage.stage_id, deepest + 1);
      progressed = true;
    }
  }
  const is_dag = depth_by_id.size === stages.length;
  const row_cursor = /* @__PURE__ */ new Map();
  const assignments = [];
  for (const stage of stages) {
    const column = depth_by_id.get(stage.stage_id);
    if (column === void 0) {
      continue;
    }
    const cursor = row_cursor.get(column);
    const row = cursor === void 0 ? 0 : cursor;
    row_cursor.set(column, row + 1);
    assignments.push({
      stageId: stage.stage_id,
      column,
      row
    });
  }
  const rtnval = {
    assignments,
    isDag: is_dag
  };
  return rtnval;
}
function compute_dag_layout(stages) {
  const columns = compute_dag_columns(stages);
  const node_by_id = /* @__PURE__ */ new Map();
  const nodes = [];
  let max_x = 0;
  let max_y = 0;
  for (const entry of columns.assignments) {
    const x = CANVAS_PADDING + entry.column * (NODE_WIDTH + COLUMN_GAP);
    const y = CANVAS_PADDING + entry.row * (NODE_HEIGHT + ROW_GAP);
    const node = {
      stageId: entry.stageId,
      x,
      y,
      width: NODE_WIDTH,
      height: NODE_HEIGHT
    };
    node_by_id.set(entry.stageId, node);
    nodes.push(node);
    if (x + NODE_WIDTH > max_x) {
      max_x = x + NODE_WIDTH;
    }
    if (y + NODE_HEIGHT > max_y) {
      max_y = y + NODE_HEIGHT;
    }
  }
  const edges = [];
  for (const stage of stages) {
    const dependent = node_by_id.get(stage.stage_id);
    if (dependent === void 0) {
      continue;
    }
    const needs = stage.needs;
    if (needs === void 0 || needs === null) {
      continue;
    }
    for (const dep_id of needs) {
      const dependency_node = node_by_id.get(dep_id);
      if (dependency_node === void 0) {
        continue;
      }
      const edge = {
        fromStageId: stage.stage_id,
        toStageId: dep_id,
        x1: dependency_node.x + dependency_node.width,
        y1: dependency_node.y + dependency_node.height / 2,
        x2: dependent.x,
        y2: dependent.y + dependent.height / 2
      };
      edges.push(edge);
    }
  }
  const rtnval = {
    nodes,
    edges,
    width: max_x + CANVAS_PADDING,
    height: max_y + CANVAS_PADDING,
    isDag: columns.isDag
  };
  return rtnval;
}
const SVG_NS = "http://www.w3.org/2000/svg";
// An edge runs from the stage a stage needs to the stage that needs it, so the
// arrowhead sits at the dependent stage: the direction the work flows.
const DAG_ARROW_SIZE = 10;
let dag_arrow_count = 0;
function next_dag_arrow_number() {
  dag_arrow_count = dag_arrow_count + 1;
  const rtnval = dag_arrow_count;
  return rtnval;
}
class PycPipelineDetail extends HTMLElement {
  _pipeline_id;
  _project_id;
  _pipeline;
  _project_names;
  _loading;
  _errored;
  _error_kind;
  _error_status;
  _is_dag;
  _root;
  _deleted;
  _delete_notice;
  _delete_pending;
  _run_pending;
  _run_notice;
  _runs;
  constructor() {
    super();
    this._pipeline_id = "";
    this._project_id = "";
    this._pipeline = null;
    this._project_names = {};
    this._loading = false;
    this._errored = false;
    this._error_kind = "";
    this._error_status = 0;
    this._is_dag = true;
    this._root = null;
    this._deleted = false;
    this._delete_notice = "";
    this._delete_pending = false;
    this._run_pending = false;
    this._run_notice = null;
    this._runs = { status: "idle", items: [], error_status: 0 };
  }
  /**
   * Observed attributes -- ``pipeline-id`` and ``project-id`` may
   * be supplied explicitly by a host; otherwise they are read
   * from the URL on mount.
   */
  static get observedAttributes() {
    const rtnval = ["pipeline-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      pipelineId: this._pipeline_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored,
      errorKind: this._error_kind,
      errorStatus: this._error_status,
      isDag: this._is_dag
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the pipeline + project ids, render
   * the chrome, and fetch the snapshot. The project id rides on
   * the detail link's ``?project_id=`` query parameter because
   * pipelines are only addressable through the project-scoped
   * API.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("pipeline-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._pipeline_id = attr_id;
    } else {
      this._pipeline_id = pipeline_id_from_path(window.location.pathname);
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
   * Fetch the pipeline snapshot and render it. Exposed so unit
   * tests can await a load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (this._pipeline_id.length === 0) {
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
    const pipeline = await this._fetch_pipeline();
    if (pipeline === null) {
      this._loading = false;
      this._errored = true;
      this._error_kind = "http";
      this._render_body();
      return;
    }
    this._pipeline = pipeline;
    this._project_id = pipeline.project_id;
    this._loading = false;
    this._errored = false;
    this._render_body();
    void this._load_project_names();
    void this._load_runs();
    return;
  }
  // Show the project by name; a failed fetch leaves the short id.
  async _load_project_names() {
    this._project_names = await fetch_project_names();
    if (this._pipeline !== null) {
      this._render_body();
    }
    return;
  }
  // The project's pipeline runs, kept to this pipeline's. A person without
  // access to runs still sees the pipeline, with a note.
  async _load_runs() {
    this._runs = { status: "loading", items: [], error_status: 0 };
    this._render_body();
    try {
      const response = await fetch(pipeline_runs_url(this._project_id), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const items = body !== null && Array.isArray(body.items) ? body.items : [];
        this._runs = { status: "ok", items: sort_runs_newest_first(items.filter((run) => run.pipeline_id === this._pipeline_id)), error_status: 0 };
      } else {
        this._runs = { status: "error", items: [], error_status: response.status };
        if (response.status === 401) {
          announce_session_expired();
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.runs_fetch_failed",
        { reason: String(reason) }
      );
      this._runs = { status: "error", items: [], error_status: 0 };
    }
    this._render_body();
    return;
  }
  /**
   * Fetch the pipeline-definition snapshot from the project-
   * scoped endpoint -- pipelines have no project-agnostic
   * resolver, so the project id must already be known (threaded
   * through the detail link's ``?project_id=`` query parameter).
   *
   * @returns The ``PipelineDefinition``, or ``null`` on failure.
   */
  async _fetch_pipeline() {
    const url = pipeline_detail_url(this._project_id, this._pipeline_id);
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
        throw new Error(
          "pipeline fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      this._error_status = 0;
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.detail_fetch_failed",
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  /**
   * Build the persistent chrome -- heading, back link, and the
   * body region the data render replaces.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-pipeline-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Pipeline detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-pipeline-detail__heading");
    heading.textContent = "Pipeline detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-pipeline-detail__back-link");
    back.setAttribute("href", "/pipelines");
    back.setAttribute("data-role", "back-link");
    keep_list_state_on_back(back, "/pipelines");
    back.textContent = "Back to pipelines";
    root.appendChild(back);
    const body = document.createElement("div");
    body.classList.add("pyc-pipeline-detail__body");
    body.setAttribute("data-role", "body");
    root.appendChild(body);
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Re-render the body region from the current pipeline
   * snapshot, driving the loading / error / loaded states.
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
      loading.classList.add("pyc-pipeline-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading pipeline\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._pipeline === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-pipeline-detail__status",
        "pyc-pipeline-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      if (this._error_kind === "missing-project") {
        error.textContent = "This link is missing its project context \u2014 open the pipeline from the Pipelines list.";
      } else if (this._error_kind === "invalid-id") {
        error.textContent = "This pipeline link is not valid \u2014 open the pipeline from the Pipelines list.";
      } else {
        error.textContent = detail_load_message_for_status(this._error_status);
      }
      const children = [error];
      if (this._error_kind === "http") {
        if (this._error_status === 0 || this._error_status >= 500) {
          const retry = document.createElement("mj-button");
          retry.classList.add("pyc-pipeline-detail__retry");
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
    if (this._deleted === true) {
      const gone = document.createElement("p");
      gone.classList.add("pyc-pipeline-detail__deleted");
      gone.setAttribute("data-role", "deleted-state");
      const text = document.createElement("span");
      text.textContent = this._delete_notice + " ";
      gone.appendChild(text);
      const list_link = document.createElement("a");
      list_link.classList.add("pyc-pipeline-detail__back-link");
      list_link.setAttribute("href", "/pipelines?project_id=" + encodeURIComponent(this._project_id));
      list_link.textContent = "Back to pipelines";
      gone.appendChild(list_link);
      body.replaceChildren(gone);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._pipeline));
    fragment.appendChild(this._build_dag_section(this._pipeline.stages));
    fragment.appendChild(this._build_stage_list(this._pipeline.stages));
    fragment.appendChild(this._build_runs_section());
    body.replaceChildren(fragment);
    return;
  }
  /**
   * Build the pipeline summary block -- identity, name, schema
   * version, commit, filename, cached timestamp.
   *
   * @param pipeline The current pipeline snapshot.
   *
   * @returns A populated summary section element.
   */
  _build_summary(pipeline) {
    const section = document.createElement("section");
    section.classList.add("pyc-pipeline-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pipeline summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-pipeline-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-pipeline-detail__pipeline-id");
    id_value.setAttribute("data-role", "pipeline-id");
    id_value.textContent = short_id(pipeline.pipeline_id);
    id_value.title = pipeline.pipeline_id;
    id_row.appendChild(id_value);
    const name_value = document.createElement("span");
    name_value.classList.add("pyc-pipeline-detail__name");
    name_value.setAttribute("data-role", "pipeline-name");
    name_value.textContent = pipeline.name;
    set_entity_title(String(pipeline.name ?? "") || "Pipeline " + short_id(pipeline.pipeline_id));
    id_row.appendChild(name_value);
    const run_button = document.createElement("mj-button");
    run_button.classList.add("pyc-pipeline-detail__run-button");
    run_button.setAttribute("variant", "primary");
    run_button.setAttribute("type", "button");
    run_button.setAttribute("data-role", "run-pipeline");
    hide_unless_may(run_button, "system:pipelines.run");
    run_button.textContent = "Run";
    if (this._run_pending === true) {
      run_button.toggleAttribute("disabled", true);
    }
    run_button.addEventListener("click", () => {
      void this._on_run();
    });
    id_row.appendChild(run_button);
    const delete_button = document.createElement("mj-button");
    delete_button.classList.add("pyc-pipeline-detail__delete");
    delete_button.setAttribute("type", "button");
    delete_button.setAttribute("data-role", "delete-pipeline");
    hide_unless_may(delete_button, "system:pipelines.write");
    delete_button.textContent = "Delete";
    if (this._delete_pending === true) {
      delete_button.toggleAttribute("disabled", true);
    }
    delete_button.addEventListener("click", () => {
      void this._on_delete();
    });
    id_row.appendChild(delete_button);
    section.appendChild(id_row);
    if (this._run_notice !== null) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-pipeline-detail__notice");
      notice.setAttribute("data-role", "run-notice");
      notice.setAttribute("data-tone", this._run_notice.ok === true ? "ok" : "error");
      notice.setAttribute("role", this._run_notice.ok === true ? "status" : "alert");
      notice.textContent = this._run_notice.message;
      section.appendChild(notice);
    }
    if (this._delete_notice.length > 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-pipeline-detail__notice");
      notice.setAttribute("data-role", "delete-notice");
      notice.setAttribute("role", "alert");
      notice.textContent = this._delete_notice;
      section.appendChild(notice);
    }
    const grid = document.createElement("dl");
    grid.classList.add("pyc-pipeline-detail__grid");
    this._append_field(grid, "Project", name_or_short(this._project_names, pipeline.project_id), {
      href: "/projects/" + encodeURIComponent(pipeline.project_id),
      value_title: pipeline.project_id
    });
    this._append_field(grid, "Schema version", String(pipeline.schema_version));
    const stage_count = Array.isArray(pipeline.stages) ? pipeline.stages.length : 0;
    this._append_field(grid, "Stages", String(stage_count));
    const commit = pipeline.commit_sha;
    if (commit !== void 0 && commit !== null && commit.length > 0) {
      this._append_field(grid, "Commit SHA", commit);
    }
    const filename = pipeline.filename;
    if (filename !== void 0 && filename !== null && filename.length > 0) {
      this._append_field(grid, "Filename", filename);
    }
    this._append_field(grid, "Cached", format_timestamp(pipeline.cached_at));
    section.appendChild(grid);
    return section;
  }
  /**
   * Run this saved pipeline after asking (ORC-13): the dialog says what it will do, the run is
   * requested by the pipeline's id (the service reads the saved definition), and the page says
   * whether it started or why it did not, then refreshes the Runs section.
   */
  async _on_run() {
    if (this._pipeline === null || this._run_pending === true) {
      return;
    }
    const name = typeof this._pipeline.name === "string" && this._pipeline.name.trim().length > 0 ? this._pipeline.name.trim() : short_id(this._pipeline.pipeline_id);
    const stages = Array.isArray(this._pipeline.stages) ? this._pipeline.stages.length : 0;
    const commit = typeof this._pipeline.commit_sha === "string" ? this._pipeline.commit_sha.slice(0, 7) : "";
    const confirmed = await confirm_action(
      this,
      "Run the pipeline \u201C" + name + "\u201D now?\nIt starts its " + String(stages) + (stages === 1 ? " stage" : " stages") + " on this project\u2019s pods" + (commit.length > 0 ? ", from commit " + commit : "") + ", in the order they depend on each other.",
      "Run pipeline",
      { tone: "neutral" }
    );
    if (confirmed !== true) {
      return;
    }
    this._run_pending = true;
    this._run_notice = null;
    this._render_body();
    const outcome = await this.runPipeline();
    this._run_pending = false;
    this._run_notice = outcome;
    this._render_body();
    if (outcome.ok === true) {
      void this._load_runs();
    }
    return;
  }
  /**
   * ``POST`` a run of this saved pipeline. Exposed so unit tests can drive it without a dialog.
   *
   * @returns ``{ok, status, message}``.
   */
  async runPipeline() {
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(pipeline_runs_url(this._project_id).split("?")[0], {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ pipeline_id: this._pipeline_id })
      });
      status = response.status;
      if (status === 401) {
        announce_session_expired();
      }
      if (response.ok === false) {
        detail = await read_problem_detail(response);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.pipelines.run_failed",
        { reason: String(reason) }
      );
      return { ok: false, status: 0, message: "Couldn't reach the server, so the pipeline was not run." };
    }
    if (status === 201 || status === 200) {
      return { ok: true, status, message: "Run started. It is listed under Runs below." };
    }
    if (status === 403) {
      return { ok: false, status, message: with_access_request("You do not have permission to run pipelines.") };
    }
    const fallback = status === 404
      ? "This pipeline is no longer saved in the project, so it was not run. Reload the page."
      : "The pipeline was not run (HTTP " + String(status) + ").";
    return { ok: false, status, message: message_with_detail("The pipeline was not run", detail, fallback) };
  }
  /**
   * Delete this pipeline definition after asking (ORC-26). The dialog says
   * what goes and that it cannot be undone; on success the page says so and
   * links back to the list.
   */
  async _on_delete() {
    if (this._pipeline === null || this._delete_pending === true) {
      return;
    }
    const name = typeof this._pipeline.name === "string" && this._pipeline.name.trim().length > 0 ? this._pipeline.name.trim() : short_id(this._pipeline.pipeline_id);
    const confirmed = await confirm_action(
      this,
      "Delete the pipeline \u201C" + name + "\u201D?\nThe saved definition is removed from this project. This cannot be undone.",
      "Delete pipeline"
    );
    if (confirmed !== true) {
      return;
    }
    this._delete_pending = true;
    this._delete_notice = "";
    this._render_body();
    const outcome = await this.deletePipeline(name);
    this._delete_pending = false;
    this._delete_notice = outcome.message;
    this._deleted = outcome.ok === true || outcome.status === 404;
    this._render_body();
    return;
  }
  /**
   * ``DELETE`` this pipeline definition. Exposed so unit tests can drive it
   * without a dialog.
   *
   * @param name The name to use in the outcome message.
   *
   * @returns ``{ok, status, message}``.
   */
  async deletePipeline(name) {
    let status = 0;
    try {
      const response = await fetch(pipeline_detail_url(this._project_id, this._pipeline_id), {
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
        "pychestrate.ui.pipelines.delete_failed",
        { reason: String(reason) }
      );
      return { ok: false, status: 0, message: "Couldn't reach the server, so the pipeline was not deleted." };
    }
    return { ok: status === 204 || status === 200, status, message: pipeline_delete_message_for_status(status, name) };
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
    field.classList.add("pyc-pipeline-detail__field");
    const term = document.createElement("dt");
    term.textContent = label;
    const def = document.createElement("dd");
    if (options !== void 0 && typeof options.href === "string") {
      // A reference to another page is a link, not a bare id.
      const link = document.createElement("a");
      link.href = options.href;
      link.textContent = value;
      if (typeof options.value_title === "string") {
        link.title = options.value_title;
      }
      def.appendChild(link);
    } else {
      def.textContent = value;
    }
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
  }
  /**
   * Build the DAG-visualization section -- the inline-SVG node-
   * and-edge layout, or the adjacency-list fallback when the
   * stages do not form a clean DAG.
   *
   * @param stages The pipeline's stages.
   *
   * @returns A populated DAG section element.
   */
  _build_dag_section(stages) {
    const section = document.createElement("section");
    section.classList.add("pyc-pipeline-detail__dag");
    section.setAttribute("data-role", "dag-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pipeline DAG");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pipeline-detail__section-heading");
    heading.textContent = "Stage DAG";
    section.appendChild(heading);
    if (stages.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pipeline-detail__status");
      empty.setAttribute("data-role", "dag-empty");
      empty.textContent = "This pipeline has no stages.";
      section.appendChild(empty);
      this._is_dag = true;
      return section;
    }
    const layout = compute_dag_layout(stages);
    this._is_dag = layout.isDag;
    if (layout.isDag === false) {
      const notice = document.createElement("p");
      notice.classList.add(
        "pyc-pipeline-detail__status",
        "pyc-pipeline-detail__status--error"
      );
      notice.setAttribute("data-role", "dag-cycle-notice");
      notice.textContent = "Stages do not form a clean DAG \u2014 showing dependency list.";
      section.appendChild(notice);
      section.appendChild(this._build_adjacency_list(stages));
      return section;
    }
    section.appendChild(this._build_dag_svg(layout));
    return section;
  }
  /**
   * Build the inline-SVG node-and-edge rendering of the DAG.
   *
   * @param layout The pre-computed pixel layout.
   *
   * @returns An ``<svg>`` element wrapped in a scroll container.
   */
  _build_dag_svg(layout) {
    const wrapper = document.createElement("div");
    wrapper.classList.add("pyc-pipeline-detail__dag-canvas");
    wrapper.setAttribute("data-role", "dag-canvas");
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute(
      "viewBox",
      "0 0 " + String(layout.width) + " " + String(layout.height)
    );
    svg.setAttribute("width", String(layout.width));
    svg.setAttribute("height", String(layout.height));
    svg.classList.add("pyc-pipeline-detail__dag-svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Pipeline stage DAG");
    const arrow_id = "pyc-dag-arrow-" + String(next_dag_arrow_number());
    const defs = document.createElementNS(SVG_NS, "defs");
    const marker = document.createElementNS(SVG_NS, "marker");
    marker.setAttribute("id", arrow_id);
    marker.setAttribute("markerWidth", String(DAG_ARROW_SIZE));
    marker.setAttribute("markerHeight", String(DAG_ARROW_SIZE));
    marker.setAttribute("refX", String(DAG_ARROW_SIZE));
    marker.setAttribute("refY", String(DAG_ARROW_SIZE / 2));
    marker.setAttribute("orient", "auto");
    marker.setAttribute("markerUnits", "userSpaceOnUse");
    const arrow = document.createElementNS(SVG_NS, "path");
    arrow.setAttribute(
      "d",
      "M0,0 L" + String(DAG_ARROW_SIZE) + "," + String(DAG_ARROW_SIZE / 2) + " L0," + String(DAG_ARROW_SIZE) + " Z"
    );
    arrow.setAttribute("class", "pyc-pipeline-detail__dag-arrow");
    arrow.setAttribute("data-role", "dag-arrow");
    marker.appendChild(arrow);
    defs.appendChild(marker);
    svg.appendChild(defs);
    for (const edge of layout.edges) {
      const line = document.createElementNS(SVG_NS, "line");
      line.setAttribute("marker-end", "url(#" + arrow_id + ")");
      line.setAttribute("x1", String(edge.x1));
      line.setAttribute("y1", String(edge.y1));
      line.setAttribute("x2", String(edge.x2));
      line.setAttribute("y2", String(edge.y2));
      line.setAttribute("class", "pyc-pipeline-detail__dag-edge");
      line.setAttribute("data-role", "dag-edge");
      svg.appendChild(line);
    }
    for (const node of layout.nodes) {
      const group = document.createElementNS(SVG_NS, "g");
      group.setAttribute("data-role", "dag-node");
      group.setAttribute("data-stage-id", node.stageId);
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("x", String(node.x));
      rect.setAttribute("y", String(node.y));
      rect.setAttribute("width", String(node.width));
      rect.setAttribute("height", String(node.height));
      rect.setAttribute("rx", "6");
      rect.setAttribute("class", "pyc-pipeline-detail__dag-box");
      group.appendChild(rect);
      const text = document.createElementNS(SVG_NS, "text");
      text.setAttribute("x", String(node.x + node.width / 2));
      text.setAttribute("y", String(node.y + node.height / 2));
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("dominant-baseline", "middle");
      text.setAttribute("class", "pyc-pipeline-detail__dag-label");
      text.textContent = node.stageId;
      group.appendChild(text);
      svg.appendChild(group);
    }
    wrapper.appendChild(svg);
    return wrapper;
  }
  /**
   * Build the adjacency-list fallback rendering -- one row per
   * stage naming the stages it depends on.
   *
   * @param stages The pipeline's stages.
   *
   * @returns An adjacency-list ``<ul>`` element.
   */
  _build_adjacency_list(stages) {
    const list = document.createElement("ul");
    list.classList.add("pyc-pipeline-detail__adjacency");
    list.setAttribute("data-role", "dag-adjacency");
    for (const stage of stages) {
      const item = document.createElement("li");
      item.classList.add("pyc-pipeline-detail__adjacency-row");
      const name = document.createElement("strong");
      name.textContent = stage.stage_id;
      item.appendChild(name);
      const needs = stage.needs;
      const detail = document.createElement("span");
      if (needs !== void 0 && needs !== null && needs.length > 0) {
        detail.textContent = " \u2192 depends on: " + needs.join(", ");
      } else {
        detail.textContent = " \u2192 no dependencies";
      }
      item.appendChild(detail);
      list.appendChild(item);
    }
    return list;
  }
  /**
   * Build the stage-list section -- one card per stage naming
   * its when-clause, dependency list, and step ids.
   *
   * @param stages The pipeline's stages.
   *
   * @returns A populated stage-list section element.
   */
  _build_runs_section() {
    const section = document.createElement("section");
    section.classList.add("pyc-pipeline-detail__runs");
    section.setAttribute("data-role", "runs-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pipeline runs");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pipeline-detail__section-heading");
    const state = this._runs;
    heading.textContent = state.status === "ok" && state.items.length > 0 ? "Runs (" + String(state.items.length) + ")" : "Runs";
    section.appendChild(heading);
    const note = (text, role, error) => {
      const p = document.createElement("p");
      p.classList.add("pyc-pipeline-detail__status");
      if (error === true) {
        p.classList.add("pyc-pipeline-detail__status--error");
      }
      p.setAttribute("data-role", role);
      p.textContent = text;
      section.appendChild(p);
    };
    if (state.status === "idle" || state.status === "loading") {
      note("Loading runs\u2026", "runs-loading", false);
      return section;
    }
    if (state.status === "error") {
      note(state.error_status === 403 ? "You don't have access to pipeline runs." : "Couldn't load this pipeline's runs.", "runs-error", state.error_status !== 403);
      return section;
    }
    if (state.items.length === 0) {
      note("This pipeline has not been run yet.", "runs-empty", false);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-pipeline-detail__run-list");
    list.setAttribute("data-role", "runs-list");
    for (const run of state.items) {
      list.appendChild(this._build_run_row(run));
    }
    section.appendChild(list);
    return section;
  }
  _build_run_row(run) {
    const item = document.createElement("li");
    item.classList.add("pyc-pipeline-detail__run");
    item.setAttribute("data-role", "run-row");
    item.setAttribute("data-state", String(run.state));
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.classList.add("pyc-pipeline-detail__run-summary");
    const chip = document.createElement("span");
    chip.classList.add("pyc-pipeline-detail__run-chip");
    chip.setAttribute("data-tone", run_state_tone(run.state));
    chip.textContent = words(run.state);
    summary.appendChild(chip);
    const when = document.createElement("span");
    when.classList.add("pyc-pipeline-detail__run-when");
    when.textContent = run.started_at ? format_timestamp(run.started_at) : "Not started";
    summary.appendChild(when);
    const progress = stage_progress_text(run);
    const cause = words(run.trigger_cause);
    const facts = [cause, progress].filter((part) => part.length > 0).join(" \xB7 ");
    if (facts.length > 0) {
      const meta = document.createElement("span");
      meta.classList.add("pyc-pipeline-detail__run-meta");
      meta.textContent = facts;
      summary.appendChild(meta);
    }
    // Why a run did not finish is what a person came for: it stays on the line, not behind the disclosure.
    if (typeof run.final_state_reason === "string" && run.final_state_reason.length > 0) {
      const reason = document.createElement("span");
      reason.classList.add("pyc-pipeline-detail__run-reason", "pyc-pipeline-detail__run-reason--line");
      reason.setAttribute("data-role", "run-reason");
      reason.textContent = run.final_state_reason;
      summary.appendChild(reason);
    }
    details.appendChild(summary);
    const stages = Array.isArray(run.stages) ? run.stages.slice().sort((left, right) => left.stage_index - right.stage_index) : [];
    for (const stage of stages) {
      const block = document.createElement("div");
      block.classList.add("pyc-pipeline-detail__run-stage");
      const head = document.createElement("div");
      head.classList.add("pyc-pipeline-detail__run-stage-head");
      const stage_chip = document.createElement("span");
      stage_chip.classList.add("pyc-pipeline-detail__run-chip");
      stage_chip.setAttribute("data-tone", run_state_tone(stage.state));
      stage_chip.textContent = words(stage.state);
      head.appendChild(stage_chip);
      const stage_name = document.createElement("strong");
      stage_name.textContent = String(stage.stage_id);
      head.appendChild(stage_name);
      block.appendChild(head);
      if (typeof stage.final_state_reason === "string" && stage.final_state_reason.length > 0) {
        const stage_reason = document.createElement("p");
        stage_reason.classList.add("pyc-pipeline-detail__run-reason");
        stage_reason.textContent = stage.final_state_reason;
        block.appendChild(stage_reason);
      }
      const steps = Array.isArray(stage.steps) ? stage.steps.slice().sort((left, right) => left.step_index - right.step_index) : [];
      for (const step of steps) {
        const line = document.createElement("div");
        line.classList.add("pyc-pipeline-detail__run-step");
        line.setAttribute("data-role", "run-step");
        const step_chip = document.createElement("span");
        step_chip.classList.add("pyc-pipeline-detail__run-chip");
        step_chip.setAttribute("data-tone", run_state_tone(step.state));
        step_chip.textContent = words(step.state);
        line.appendChild(step_chip);
        const label = document.createElement("span");
        label.textContent = String(step.step_id) + (typeof step.kind_name === "string" && step.kind_name.length > 0 ? " (" + step.kind_name + ")" : "");
        line.appendChild(label);
        if (typeof step.layer5_run_id === "string" && step.layer5_run_id.length > 0) {
          const link = document.createElement("a");
          link.classList.add("pyc-pipeline-detail__back-link");
          link.setAttribute("data-role", "run-step-link");
          link.setAttribute("href", "/runs/" + encodeURIComponent(step.layer5_run_id));
          link.textContent = "Open the run";
          line.appendChild(link);
        }
        if (typeof step.final_state_reason === "string" && step.final_state_reason.length > 0) {
          const step_reason = document.createElement("span");
          step_reason.classList.add("pyc-pipeline-detail__run-reason");
          step_reason.textContent = step.final_state_reason;
          line.appendChild(step_reason);
        }
        block.appendChild(line);
      }
      details.appendChild(block);
    }
    item.appendChild(details);
    return item;
  }
  _build_stage_list(stages) {
    const section = document.createElement("section");
    section.classList.add("pyc-pipeline-detail__stages");
    section.setAttribute("data-role", "stage-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pipeline stages");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-pipeline-detail__section-heading");
    heading.textContent = "Stages";
    section.appendChild(heading);
    if (stages.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-pipeline-detail__status");
      empty.setAttribute("data-role", "stages-empty");
      empty.textContent = "No stages defined.";
      section.appendChild(empty);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-pipeline-detail__stage-list");
    for (const stage of stages) {
      const item = document.createElement("li");
      item.classList.add("pyc-pipeline-detail__stage");
      item.setAttribute("data-role", "stage-card");
      const stage_name = document.createElement("strong");
      stage_name.classList.add("pyc-pipeline-detail__stage-name");
      stage_name.textContent = stage.stage_id;
      item.appendChild(stage_name);
      const when = stage.when_clause;
      if (when !== void 0 && when !== null && when.length > 0) {
        const chip = document.createElement("span");
        chip.classList.add("pyc-pipeline-detail__stage-when");
        chip.textContent = "when: " + when;
        item.appendChild(chip);
      }
      const needs = stage.needs;
      const needs_text = document.createElement("span");
      needs_text.classList.add("pyc-pipeline-detail__stage-needs");
      if (needs !== void 0 && needs !== null && needs.length > 0) {
        needs_text.textContent = "needs: " + needs.join(", ");
      } else {
        needs_text.textContent = "needs: none";
      }
      item.appendChild(needs_text);
      const steps = stage.steps;
      const steps_text = document.createElement("span");
      steps_text.classList.add("pyc-pipeline-detail__stage-steps");
      if (Array.isArray(steps) === true && steps.length > 0) {
        const step_ids = [];
        for (const step of steps) {
          step_ids.push(step.step_id);
        }
        steps_text.textContent = "steps: " + step_ids.join(", ");
      } else {
        steps_text.textContent = "steps: none";
      }
      item.appendChild(steps_text);
      list.appendChild(item);
    }
    section.appendChild(list);
    return section;
  }
}
export {
  PycPipelineDetail,
  compute_dag_columns,
  compute_dag_layout,
  detail_load_message_for_status,
  pipeline_delete_message_for_status,
  pipeline_detail_url,
  pipeline_runs_url,
  run_state_tone,
  sort_runs_newest_first,
  stage_progress_text,
  pipeline_id_from_path,
  project_id_from_search
};
