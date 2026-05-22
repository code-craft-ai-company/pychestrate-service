import {
  format_timestamp,
  short_id
} from "./resource-pools-view.js";
import { is_valid_uuid } from "./pool-detail-view.js";
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
function health_tone(outcome) {
  if (outcome === "pass") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (outcome === "fail") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function resource_state_tone(state) {
  if (state === "available") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (state === "leased" || state === "maintenance") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (state === "quarantined" || state === "retired") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
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
class PycResourceDetail extends HTMLElement {
  _resource_id;
  _resource;
  _health;
  _usage;
  _loading;
  _errored;
  _root;
  constructor() {
    super();
    this._resource_id = "";
    this._resource = null;
    this._health = null;
    this._usage = [];
    this._loading = false;
    this._errored = false;
    this._root = null;
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
      hasHealth: this._health !== null
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the resource id, render the chrome,
   * and fetch the initial snapshot.
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
    this._render_chrome();
    void this._load();
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
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const resource = await this._fetch_json(
      build_resource_url(this._resource_id),
      "resource_fetch_failed"
    );
    if (resource === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._resource = resource;
    this._health = await this._fetch_json(
      build_resource_health_url(this._resource_id),
      "health_fetch_failed"
    );
    const usage = await this._fetch_json(
      build_resource_usage_url(this._resource_id),
      "usage_fetch_failed"
    );
    if (usage !== null && Array.isArray(usage.items) === true) {
      this._usage = usage.items;
    }
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
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
        "pychestrate.ui.resources." + failure_tag,
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-resources", "pyc-resource-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Resource detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-resources__back-link");
    back.setAttribute("href", "/resource-pools");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to resource pools";
    root.appendChild(back);
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
      loading.textContent = "Loading resource\u2026";
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
      error.textContent = "Failed to load this resource. Try refreshing.";
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._resource));
    fragment.appendChild(this._build_health());
    fragment.appendChild(this._build_usage_timeline());
    body.replaceChildren(fragment);
    return;
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
    this._append_field(grid, "Project", resource.project_id);
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
        const chip = document.createElement("span");
        chip.classList.add("pyc-resources__tag");
        chip.textContent = tag;
        tag_list.appendChild(chip);
      }
      section.appendChild(tag_list);
    }
    return section;
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
  build_resource_health_url,
  build_resource_url,
  build_resource_usage_url,
  health_tone,
  resource_id_from_path,
  resource_state_tone,
  usage_event_tone
};
