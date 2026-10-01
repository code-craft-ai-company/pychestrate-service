import { confirm_action } from "../shared/confirm.js";
import { with_access_request } from "../shared/admin-contact.js";
import { set_entity_title } from "../shared/page-title.js";
import {
  RESOURCE_POOLS_WRITE_PERMISSION,
  extract_projects,
  format_timestamp,
  health_tone,
  on_shell_permissions_changed,
  read_problem,
  resource_state_tone,
  shell_write_allowed,
  short_id
} from "./resource-pools-view.js";
const ACTIVE_RESERVATION_STATES = [
  "pending",
  "granted"
];
const PROJECTS_API_PATH = "/api/v1/projects";
// Project pickers need every project, not the API's default first page
// of 50 (the registry holds every web-UI project too -- PRJ-06).
const PROJECTS_LIST_URL = PROJECTS_API_PATH + "?per_page=500";
const RESOURCES_API_PATH = "/api/v1/resources";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function pool_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/resource-pools/";
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
function is_valid_uuid(value) {
  if (typeof value !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(value);
  return rtnval;
}
function is_active_reservation(state) {
  const rtnval = ACTIVE_RESERVATION_STATES.indexOf(state) >= 0;
  return rtnval;
}
function reservation_tone(state) {
  if (state === "granted") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (state === "pending") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (state === "rejected" || state === "forced_released") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function build_pool_url(pool_id) {
  const rtnval = "/api/v1/resource-pools/" + encodeURIComponent(pool_id);
  return rtnval;
}
function build_pool_resources_url(pool_id) {
  const rtnval = build_pool_url(pool_id) + "/resources";
  return rtnval;
}
/* The project's resources (up to 500, the API's page limit), for the member picker. */
function build_project_resources_url(project_id) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  params.set("per_page", "500");
  return RESOURCES_API_PATH + "?" + params.toString();
}
/* The resources a person can still add to a pool: not retired, not already a member. */
function addable_resources(resources, members) {
  const taken = new Set((Array.isArray(members) ? members : []).map((member) => member.resource_id));
  return (Array.isArray(resources) ? resources : []).filter(
    (resource) => resource.state !== "retired" && taken.has(resource.resource_id) === false
  );
}
function resource_option_label(resource) {
  const name = typeof resource.display_name === "string" && resource.display_name.length > 0 ? resource.display_name : resource.resource_id;
  const kind = typeof resource.kind === "string" && resource.kind.length > 0 ? " · " + resource.kind : "";
  return name + kind;
}
function build_pool_member_url(pool_id, resource_id) {
  const rtnval = build_pool_resources_url(pool_id) + "/" + encodeURIComponent(resource_id);
  return rtnval;
}
function build_pool_reservations_url(pool_id) {
  const rtnval = build_pool_url(pool_id) + "/reservations";
  return rtnval;
}
function build_reservation_url(pool_id, reservation_id) {
  const rtnval = build_pool_reservations_url(pool_id) + "/" + encodeURIComponent(reservation_id);
  return rtnval;
}
function member_display_label(member) {
  let label = "";
  if (typeof member.resource_name === "string" && member.resource_name.length > 0) {
    label = member.resource_name;
  } else {
    label = short_id(member.resource_id);
  }
  if (typeof member.resource_state === "string" && member.resource_state.length > 0) {
    label = label + " · " + member.resource_state;
  }
  const rtnval = label;
  return rtnval;
}
function reserve_failure_message(problem) {
  if (problem.reason === "conflict_rejected") {
    const rtnval2 = "Reservation conflicts with an existing hold.";
    return rtnval2;
  }
  if (problem.reason === "pool_empty") {
    const rtnval2 = "This pool has no available resources.";
    return rtnval2;
  }
  if (problem.status === 403) {
    const rtnval2 = "You do not have permission to reserve from this pool.";
    return rtnval2;
  }
  if (problem.detail.length > 0) {
    const rtnval2 = "Reserve failed: " + problem.detail;
    return rtnval2;
  }
  const rtnval = "Reserve failed (HTTP " + String(problem.status) + ").";
  return rtnval;
}
function section_error_message(noun, status) {
  if (status === 403) {
    const rtnval2 = "You do not have permission to view " + noun + ".";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Network error while loading " + noun + ".";
    return rtnval2;
  }
  const rtnval = "Failed to load " + noun + " (HTTP " + String(status) + ").";
  return rtnval;
}
class PycPoolDetail extends HTMLElement {
  _pool_id;
  _project_id;
  _pool;
  _members;
  _reservations;
  _loading;
  _errored;
  _error_status;
  _members_error;
  _candidates;
  _reservations_error;
  _project_names;
  _reserving;
  _releasing;
  _deleting;
  _root;
  _action_status;
  constructor() {
    super();
    this._pool_id = "";
    this._project_id = "";
    this._pool = null;
    this._members = [];
    this._reservations = [];
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._members_error = null;
    this._candidates = null;
    this._reservations_error = null;
    this._project_names = {};
    this._reserving = false;
    this._releasing = {};
    this._deleting = false;
    this._root = null;
    this._action_status = null;
  }
  /**
   * Observed attributes -- ``pool-id`` / ``project-id`` may be
   * supplied explicitly by a host; otherwise they are read from
   * the path / query string on mount.
   */
  static get observedAttributes() {
    const rtnval = ["pool-id", "project-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      poolId: this._pool_id,
      projectId: this._project_id,
      loading: this._loading,
      errored: this._errored,
      errorStatus: this._error_status,
      membersError: this._members_error,
      reservationsError: this._reservations_error,
      reserving: this._reserving
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the pool + project ids, render the
   * chrome, and fetch the initial snapshot.
   */
  connectedCallback() {
    const attr_pool = this.getAttribute("pool-id");
    if (attr_pool !== null && attr_pool.length > 0) {
      this._pool_id = attr_pool;
    } else {
      this._pool_id = pool_id_from_path(window.location.pathname);
    }
    const attr_project = this.getAttribute("project-id");
    if (attr_project !== null && attr_project.length > 0) {
      this._project_id = attr_project;
    } else {
      this._project_id = project_id_from_search(
        window.location.search
      );
    }
    this._render_chrome();
    on_shell_permissions_changed(() => {
      if (this.isConnected === true) {
        this._render_body();
      }
    });
    void this._load();
    void this._load_project_names();
    return;
  }
  /**
   * Fetch the pool snapshot. Exposed so unit tests can await a
   * load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_uuid(this._pool_id) === false) {
      this._loading = false;
      this._errored = true;
      this._error_status = -1;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_body();
    const result = await this._fetch_json(
      build_pool_url(this._pool_id),
      "pool_fetch_failed"
    );
    if (result.ok === false) {
      this._loading = false;
      this._errored = true;
      this._error_status = result.status;
      this._render_body();
      return;
    }
    this._pool = result.body;
    if (this._project_id.length === 0 && typeof this._pool.project_id === "string") {
      this._project_id = this._pool.project_id;
    }
    this._update_back_link();
    await this._refresh_members();
    await this._refresh_candidates();
    await this._refresh_reservations();
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  /**
   * Best-effort fetch of the projects collection so the summary
   * can show a project display name beside the UUID. Failures are
   * silent -- the UUID alone is always rendered.
   */
  async _load_project_names() {
    try {
      const response = await fetch(PROJECTS_LIST_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        return;
      }
      const body = await response.json();
      const projects = extract_projects(body);
      const names = {};
      for (const project of projects) {
        names[project.project_id] = project.display_name;
      }
      this._project_names = names;
      if (this._loading === false && this._errored === false && this._pool !== null) {
        this._render_body();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.project_names_fetch_failed",
        { reason: String(reason) }
      );
    }
    return;
  }
  async _refresh_members() {
    const result = await this._fetch_json(
      build_pool_resources_url(this._pool_id),
      "members_fetch_failed"
    );
    if (result.ok === true && Array.isArray(result.body.items) === true) {
      this._members = result.body.items;
      this._members_error = null;
    } else {
      this._members_error = result.status;
    }
    return;
  }
  /*
   * The project's resources a person can add: null when they cannot be listed
   * (no permission to read resources, a failure), so the form falls back to
   * asking for an id.
   */
  async _refresh_candidates() {
    const project_id = this._pool !== null && typeof this._pool.project_id === "string" ? this._pool.project_id : this._project_id;
    if (project_id.length === 0) {
      this._candidates = null;
      return;
    }
    const result = await this._fetch_json(build_project_resources_url(project_id), "candidates_fetch_failed");
    if (result.ok === true && Array.isArray(result.body.items) === true) {
      this._candidates = addable_resources(result.body.items, this._members);
    } else {
      this._candidates = null;
    }
    return;
  }
  async _refresh_reservations() {
    const result = await this._fetch_json(
      build_pool_reservations_url(this._pool_id),
      "reservations_fetch_failed"
    );
    if (result.ok === true && Array.isArray(result.body.items) === true) {
      this._reservations = result.body.items;
      this._reservations_error = null;
    } else {
      this._reservations_error = result.status;
    }
    return;
  }
  /**
   * GET a JSON document. Returns ``{ok: true, body}`` on a 2xx
   * response and ``{ok: false, status}`` otherwise -- ``status``
   * is ``0`` for network-level failures so callers can render an
   * error state distinct from an empty collection.
   */
  async _fetch_json(url, failure_tag) {
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        console.warn(
          "pychestrate.ui.resources." + failure_tag,
          { status: response.status }
        );
        const rtnval2 = { ok: false, status: response.status, body: null };
        return rtnval2;
      }
      const body = await response.json();
      const rtnval = { ok: true, status: response.status, body };
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources." + failure_tag,
        { reason: String(reason) }
      );
      const rtnval = { ok: false, status: 0, body: null };
      return rtnval;
    }
  }
  _pools_list_href() {
    let href = "/resource-pools";
    if (this._project_id.length > 0) {
      href = href + "?project_id=" + encodeURIComponent(this._project_id);
    }
    const rtnval = href;
    return rtnval;
  }
  _update_back_link() {
    if (this._root === null) {
      return;
    }
    const back = this._root.querySelector('[data-role="back-link"]');
    if (back === null) {
      return;
    }
    back.setAttribute("href", this._pools_list_href());
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-resources", "pyc-pool-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Resource pool detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource pool detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-resources__back-link");
    back.setAttribute("href", this._pools_list_href());
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to resource pools";
    root.appendChild(back);
    const status = document.createElement("p");
    status.classList.add("pyc-resources__form-status");
    status.setAttribute("data-role", "action-status");
    status.setAttribute("role", "status");
    status.hidden = true;
    root.appendChild(status);
    this._action_status = status;
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
      loading.setAttribute("role", "status");
      loading.textContent = "Loading resource pool…";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._pool === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.setAttribute("role", "status");
      const status = this._error_status;
      if (status === -1) {
        error.textContent = "The pool id in the URL is not a valid UUID.";
      } else if (status === 404) {
        error.textContent = "This resource pool was not found. It may have been deleted.";
      } else if (status === 403) {
        error.textContent = with_access_request("You do not have permission to view this resource pool.");
      } else if (status === 0) {
        error.textContent = "Network error while loading this resource pool. Try refreshing.";
      } else {
        error.textContent = "Failed to load this resource pool (HTTP " + String(status) + ").";
      }
      body.replaceChildren(error);
      return;
    }
    const write_allowed = shell_write_allowed(
      RESOURCE_POOLS_WRITE_PERMISSION
    );
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._pool, write_allowed));
    fragment.appendChild(this._build_resources(write_allowed));
    if (write_allowed === true) {
      fragment.appendChild(this._build_add_resource_form());
    }
    fragment.appendChild(this._build_reservations(write_allowed));
    if (write_allowed === true) {
      fragment.appendChild(this._build_reserve_form());
    }
    body.replaceChildren(fragment);
    return;
  }
  _project_field_value(project_id) {
    let value = project_id;
    const display_name = this._project_names[project_id];
    if (typeof display_name === "string" && display_name.length > 0 && display_name !== project_id) {
      value = display_name + " (" + project_id + ")";
    }
    const rtnval = value;
    return rtnval;
  }
  _build_summary(pool, write_allowed) {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Resource pool summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-resources__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-resources__id");
    id_value.setAttribute("data-role", "pool-id");
    id_value.textContent = short_id(pool.pool_id);
    set_entity_title(String(pool.name ?? "") || "Resource pool " + short_id(pool.pool_id));
    id_value.title = pool.pool_id;
    id_row.appendChild(id_value);
    if (write_allowed === true) {
      const delete_button = document.createElement("mj-button");
      delete_button.classList.add("pyc-resources__button");
      delete_button.setAttribute("type", "button");
      delete_button.setAttribute("data-role", "delete-pool");
      delete_button.textContent = "Delete Pool";
      if (this._deleting === true) {
        delete_button.setAttribute("disabled", "");
      }
      delete_button.addEventListener("click", () => {
        void this._submit_delete_pool(delete_button);
      });
      id_row.appendChild(delete_button);
    }
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-resources__grid");
    this._append_field(grid, "Pool id", pool.pool_id);
    this._append_field(grid, "Name", pool.name);
    this._append_field(
      grid,
      "Project",
      this._project_field_value(pool.project_id)
    );
    const description = pool.description !== null && pool.description !== void 0 ? pool.description : "";
    if (description.length > 0) {
      this._append_field(grid, "Description", description);
    }
    this._append_field(
      grid,
      "Members",
      String(pool.member_count)
    );
    this._append_field(
      grid,
      "Created",
      format_timestamp(pool.created_at)
    );
    section.appendChild(grid);
    const tags = Array.isArray(pool.capability_tags) === true ? pool.capability_tags : [];
    if (tags.length > 0) {
      const tag_list = document.createElement("div");
      tag_list.classList.add("pyc-resources__tag-list");
      for (const tag of tags) {
        const chip = document.createElement("mj-chip");
        chip.classList.add("pyc-resources__tag");
        chip.textContent = tag;
        tag_list.appendChild(chip);
      }
      section.appendChild(tag_list);
    }
    return section;
  }
  async _submit_delete_pool(delete_button) {
    if (this._deleting === true) {
      return;
    }
    const pool_name = this._pool !== null && typeof this._pool.name === "string" && this._pool.name.length > 0 ? this._pool.name : short_id(this._pool_id);
    const confirmed = await confirm_action(this, "Delete the pool " + pool_name + "? This permanently removes the pool and its membership rows and cannot be undone. The member resources themselves are not deleted.", "Delete pool");
    if (confirmed !== true) {
      return;
    }
    this._deleting = true;
    if (delete_button !== null && delete_button !== void 0) {
      delete_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(build_pool_url(this._pool_id), {
        method: "DELETE",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "Delete failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to delete this pool.";
        } else if (problem.detail.length > 0) {
          message = "Delete failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.pool_delete_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Delete failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      this._deleting = false;
      if (delete_button !== null && delete_button !== void 0) {
        delete_button.removeAttribute("disabled");
      }
    }
    window.location.assign(this._pools_list_href());
    return;
  }
  _resource_detail_href(resource_id) {
    let href = "/resource-pools/resources/" + resource_id;
    const params = new URLSearchParams();
    if (this._project_id.length > 0) {
      params.set("project_id", this._project_id);
    }
    params.set("pool_id", this._pool_id);
    href = href + "?" + params.toString();
    const rtnval = href;
    return rtnval;
  }
  _build_resources(write_allowed) {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__resources");
    section.setAttribute("data-role", "resources-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pool resources");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Resources";
    section.appendChild(heading);
    if (this._members_error !== null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "resources-error");
      error.setAttribute("role", "status");
      error.textContent = section_error_message(
        "this pool's resource members",
        this._members_error
      );
      section.appendChild(error);
      const retry = document.createElement("mj-button");
      retry.classList.add("pyc-resources__button");
      retry.setAttribute("type", "button");
      retry.setAttribute("data-role", "resources-retry");
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        void this._retry_members();
      });
      section.appendChild(retry);
      return section;
    }
    if (this._members.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-resources__status");
      empty.setAttribute("data-role", "resources-empty");
      empty.textContent = "This pool has no resource members.";
      section.appendChild(empty);
      return section;
    }
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-resources__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-resources__row";
    const columns = [
      {
        key: "resource_name",
        label: "Resource",
        width: "14rem",
        render: (member) => {
          const link = document.createElement("a");
          link.classList.add("pyc-resources__link");
          link.setAttribute(
            "href",
            this._resource_detail_href(member.resource_id)
          );
          let label = short_id(member.resource_id);
          if (typeof member.resource_name === "string" && member.resource_name.length > 0) {
            label = member.resource_name;
          }
          link.textContent = label;
          link.title = member.resource_id;
          return link;
        }
      },
      {
        key: "resource_kind",
        label: "Kind",
        width: "8rem",
        render: (member) => {
          const rtnval = typeof member.resource_kind === "string" && member.resource_kind.length > 0 ? member.resource_kind : "—";
          return rtnval;
        }
      },
      {
        key: "resource_state",
        label: "State",
        width: "8rem",
        render: (member) => {
          if (typeof member.resource_state !== "string" || member.resource_state.length === 0) {
            const rtnval2 = "—";
            return rtnval2;
          }
          const badge = document.createElement("span");
          badge.classList.add("pyc-badge");
          badge.setAttribute("data-tone", resource_state_tone(member.resource_state));
          badge.textContent = member.resource_state;
          return badge;
        }
      },
      {
        key: "resource_health",
        label: "Health",
        width: "8rem",
        render: (member) => {
          if (typeof member.resource_health !== "string" || member.resource_health.length === 0) {
            const rtnval2 = "—";
            return rtnval2;
          }
          const badge = document.createElement("span");
          badge.classList.add("pyc-badge");
          badge.setAttribute("data-tone", health_tone(member.resource_health));
          badge.textContent = member.resource_health;
          return badge;
        }
      },
      {
        key: "added_at",
        label: "Added",
        width: "12rem",
        render: (member) => format_timestamp(member.added_at)
      }
    ];
    if (write_allowed === true) {
      columns.push({
        key: "membership_id",
        label: "Actions",
        width: "8rem",
        sortable: false,
        render: (member) => {
          const remove = document.createElement("mj-button");
          remove.classList.add("pyc-resources__button");
          remove.setAttribute("type", "button");
          remove.setAttribute("data-role", "remove-member");
          remove.setAttribute("data-resource-id", member.resource_id);
          remove.textContent = "Remove";
          remove.addEventListener("click", () => {
            void this._submit_remove_member(member, remove);
          });
          return remove;
        }
      });
    }
    table.columns = columns;
    table.rows = this._members;
    section.appendChild(table);
    return section;
  }
  async _retry_members() {
    await this._refresh_members();
    this._render_body();
    return;
  }
  async _submit_remove_member(member, remove_button) {
    const label = member_display_label(member);
    const confirmed = await confirm_action(this, "Remove " + label + " from this pool? The resource itself is not deleted and existing reservations are not released.", "Remove from pool");
    if (confirmed !== true) {
      return;
    }
    if (remove_button !== null && remove_button !== void 0) {
      remove_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(
        build_pool_member_url(this._pool_id, member.resource_id),
        {
          method: "DELETE",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        }
      );
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "Remove failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to remove pool members.";
        } else if (problem.detail.length > 0) {
          message = "Remove failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.remove_member_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Remove failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      if (remove_button !== null && remove_button !== void 0) {
        remove_button.removeAttribute("disabled");
      }
    }
    this._show_action_status("Resource removed from the pool.", false);
    await this._load();
    return;
  }
  _build_add_resource_form() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "add-resource-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Add resource";
    section.appendChild(heading);
    if (Array.isArray(this._candidates) === true && this._candidates.length === 0) {
      const none = document.createElement("p");
      none.classList.add("pyc-resources__status");
      none.setAttribute("data-role", "add-resource-none");
      none.appendChild(document.createTextNode("Every resource in this project is already in this pool. "));
      const register = document.createElement("a");
      register.classList.add("pyc-resources__link");
      register.setAttribute("href", this._pools_list_href());
      register.textContent = "Register another device";
      none.appendChild(register);
      none.appendChild(document.createTextNode("."));
      section.appendChild(none);
      return section;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "add-resource-form");
    let read_value = null;
    if (Array.isArray(this._candidates) === true) {
      // The project's resources, by name: no id to look up and paste.
      const label = document.createElement("label");
      label.classList.add("pyc-resources__filter");
      label.textContent = "Resource";
      const select = document.createElement("mj-select");
      select.classList.add("pyc-resources__select");
      select.setAttribute("data-role", "add-resource-select");
      for (const resource of this._candidates) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", resource.resource_id);
        option.textContent = resource_option_label(resource);
        select.appendChild(option);
      }
      label.appendChild(select);
      form.appendChild(label);
      read_value = () => String(select.value || "").trim();
    } else {
      // The resources could not be listed: fall back to an id.
      const id_input = document.createElement("mj-text-field");
      id_input.setAttribute("label", "Resource id");
      id_input.classList.add("pyc-resources__input");
      id_input.setAttribute("type", "text");
      id_input.setAttribute("placeholder", "resource uuid");
      id_input.setAttribute("data-role", "add-resource-id");
      form.appendChild(id_input);
      read_value = () => id_input.value.trim();
    }
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "add-resource-submit");
    submit.textContent = "Add Resource";
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_add_resource(read_value(), submit);
    });
    section.appendChild(form);
    return section;
  }
  async _submit_add_resource(resource_id, submit_button) {
    if (resource_id.length === 0) {
      this._show_action_status(
        Array.isArray(this._candidates) === true ? "Choose a resource to add." : "A resource id is required.",
        true
      );
      return;
    }
    if (is_valid_uuid(resource_id) === false) {
      this._show_action_status(
        "A valid resource id (UUID) is required.",
        true
      );
      return;
    }
    const body = { resource_id };
    if (submit_button !== null && submit_button !== void 0) {
      submit_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(
        build_pool_resources_url(this._pool_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify(body)
        }
      );
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "Add resource failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to add pool members.";
        } else if (problem.detail.length > 0) {
          message = "Add resource failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.add_resource_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Add resource failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      if (submit_button !== null && submit_button !== void 0) {
        submit_button.removeAttribute("disabled");
      }
    }
    this._show_action_status("Resource added to the pool.", false);
    await this._load();
    return;
  }
  _build_reservations(write_allowed) {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__reservations");
    section.setAttribute("data-role", "reservations-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pool reservations");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Reservations";
    section.appendChild(heading);
    if (this._reservations_error !== null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-resources__status",
        "pyc-resources__status--error"
      );
      error.setAttribute("data-role", "reservations-error");
      error.setAttribute("role", "status");
      error.textContent = section_error_message(
        "this pool's reservations",
        this._reservations_error
      );
      section.appendChild(error);
      const retry = document.createElement("mj-button");
      retry.classList.add("pyc-resources__button");
      retry.setAttribute("type", "button");
      retry.setAttribute("data-role", "reservations-retry");
      retry.textContent = "Retry";
      retry.addEventListener("click", () => {
        void this._retry_reservations();
      });
      section.appendChild(retry);
      return section;
    }
    if (this._reservations.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-resources__status");
      empty.setAttribute("data-role", "reservations-empty");
      empty.textContent = "No reservations against this pool.";
      section.appendChild(empty);
      return section;
    }
    const list = document.createElement("ul");
    list.classList.add("pyc-resources__history-list");
    for (const reservation of this._reservations) {
      list.appendChild(
        this._build_reservation_row(reservation, write_allowed)
      );
    }
    section.appendChild(list);
    return section;
  }
  async _retry_reservations() {
    await this._refresh_reservations();
    this._render_body();
    return;
  }
  _build_reservation_row(reservation, write_allowed) {
    const item = document.createElement("li");
    item.classList.add("pyc-resources__history-entry");
    const badge = document.createElement("span");
    badge.classList.add("pyc-badge");
    badge.setAttribute("data-tone", reservation_tone(reservation.state));
    badge.textContent = reservation.state;
    item.appendChild(badge);
    const label = document.createElement("span");
    label.classList.add("pyc-resources__reservation-label");
    const summary = " " + short_id(reservation.resource_id) + " · " + reservation.mode + " · " + format_timestamp(reservation.requested_at);
    label.textContent = summary;
    label.title = reservation.resource_id;
    item.appendChild(label);
    if (write_allowed === true && is_active_reservation(reservation.state) === true) {
      const release = document.createElement("mj-button");
      release.classList.add("pyc-resources__button");
      release.setAttribute("type", "button");
      release.setAttribute("data-role", "release-reservation");
      release.setAttribute(
        "data-reservation-id",
        reservation.reservation_id
      );
      release.textContent = "Release";
      if (this._releasing[reservation.reservation_id] === true) {
        release.setAttribute("disabled", "");
      }
      release.addEventListener("click", () => {
        void this._submit_release(reservation, release);
      });
      item.appendChild(release);
    }
    return item;
  }
  async _submit_release(reservation, release_button) {
    const reservation_id = reservation.reservation_id;
    if (this._releasing[reservation_id] === true) {
      return;
    }
    const confirmed = await confirm_action(this, "Release the " + reservation.mode + " reservation on " + short_id(reservation.resource_id) + "? The holder loses the resource.", "Release reservation");
    if (confirmed !== true) {
      return;
    }
    this._releasing[reservation_id] = true;
    if (release_button !== null && release_button !== void 0) {
      release_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(
        build_reservation_url(this._pool_id, reservation_id),
        {
          method: "DELETE",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        }
      );
      if (response.ok === false) {
        const problem = await read_problem(response);
        let message = "Release failed (HTTP " + String(problem.status) + ").";
        if (problem.status === 403) {
          message = "You do not have permission to release reservations.";
        } else if (problem.detail.length > 0) {
          message = "Release failed: " + problem.detail;
        }
        this._show_action_status(message, true);
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.release_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Release failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      delete this._releasing[reservation_id];
      if (release_button !== null && release_button !== void 0) {
        release_button.removeAttribute("disabled");
      }
    }
    this._show_action_status("Reservation released.", false);
    await this._refresh_reservations();
    this._render_body();
    return;
  }
  _build_reserve_form() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "reserve-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Reserve a resource";
    section.appendChild(heading);
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "reserve-form");
    const resource_label = document.createElement("label");
    resource_label.classList.add("pyc-resources__filter");
    resource_label.textContent = "Resource";
    const resource_select = document.createElement("mj-select");
    resource_select.classList.add("pyc-resources__select");
    resource_select.setAttribute("data-role", "reserve-resource");
    const any_option = document.createElement("mj-option");
    any_option.setAttribute("value", "");
    any_option.textContent = "Any available member (FIFO)";
    resource_select.appendChild(any_option);
    for (const member of this._members) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", member.resource_id);
      option.textContent = member_display_label(member);
      resource_select.appendChild(option);
    }
    resource_select.setAttribute("value", "");
    resource_label.appendChild(resource_select);
    form.appendChild(resource_label);
    const mode_label = document.createElement("label");
    mode_label.classList.add("pyc-resources__filter");
    mode_label.textContent = "Mode";
    const mode_select = document.createElement("mj-select");
    mode_select.classList.add("pyc-resources__select");
    mode_select.setAttribute("data-role", "reserve-mode");
    for (const mode of ["exclusive", "shared"]) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", mode);
      option.textContent = mode;
      mode_select.appendChild(option);
    }
    mode_select.setAttribute("value", "exclusive");
    mode_label.appendChild(mode_select);
    form.appendChild(mode_label);
    const note_label = document.createElement("label");
    note_label.classList.add("pyc-resources__filter");
    note_label.textContent = "Note";
    const note_input = document.createElement("mj-text-field");
    note_input.classList.add("pyc-resources__input");
    note_input.setAttribute("type", "text");
    note_input.setAttribute("placeholder", "optional");
    note_input.setAttribute("data-role", "reserve-note");
    note_label.appendChild(note_input);
    form.appendChild(note_label);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "reserve-submit");
    submit.textContent = "Reserve";
    if (this._reserving === true) {
      submit.setAttribute("disabled", "");
    }
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_reserve(
        mode_select.value,
        note_input.value.trim(),
        resource_select.value,
        submit
      );
    });
    section.appendChild(form);
    return section;
  }
  async _submit_reserve(mode, note, resource_id, submit_button) {
    if (this._reserving === true) {
      return;
    }
    if (this._project_id.length === 0) {
      this._show_action_status(
        "A project id is required to reserve.",
        true
      );
      return;
    }
    const body = {
      project_id: this._project_id,
      mode
    };
    if (note.length > 0) {
      body["note"] = note;
    }
    if (typeof resource_id === "string" && resource_id.length > 0) {
      body["resource_id"] = resource_id;
    }
    this._reserving = true;
    if (submit_button !== null && submit_button !== void 0) {
      submit_button.setAttribute("disabled", "");
    }
    try {
      const response = await fetch(
        build_pool_reservations_url(this._pool_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify(body)
        }
      );
      if (response.ok === false) {
        const problem = await read_problem(response);
        this._show_action_status(
          reserve_failure_message(problem),
          true
        );
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.reserve_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Reserve failed -- network error. Try again.",
        true
      );
      return;
    } finally {
      this._reserving = false;
      if (submit_button !== null && submit_button !== void 0) {
        submit_button.removeAttribute("disabled");
      }
    }
    this._show_action_status("Reservation granted.", false);
    await this._refresh_reservations();
    this._render_body();
    return;
  }
  _show_action_status(message, errored) {
    if (this._action_status === null) {
      return;
    }
    this._action_status.hidden = false;
    this._action_status.textContent = message;
    if (errored === true) {
      this._action_status.setAttribute("data-tone", "error");
    } else {
      this._action_status.setAttribute("data-tone", "ok");
    }
    return;
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
  ACTIVE_RESERVATION_STATES,
  PycPoolDetail,
  addable_resources,
  build_pool_member_url,
  build_project_resources_url,
  build_pool_reservations_url,
  build_pool_resources_url,
  build_pool_url,
  build_reservation_url,
  is_active_reservation,
  is_valid_uuid,
  member_display_label,
  pool_id_from_path,
  project_id_from_search,
  reservation_tone,
  resource_option_label,
  reserve_failure_message,
  section_error_message
};
