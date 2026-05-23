import {
  format_timestamp,
  short_id
} from "./resource-pools-view.js";
const ACTIVE_RESERVATION_STATES = [
  "pending",
  "granted"
];
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
function build_pool_reservations_url(pool_id) {
  const rtnval = build_pool_url(pool_id) + "/reservations";
  return rtnval;
}
function build_reservation_url(pool_id, reservation_id) {
  const rtnval = build_pool_reservations_url(pool_id) + "/" + encodeURIComponent(reservation_id);
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
      errored: this._errored
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
    void this._load();
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
    const pool = await this._fetch_json(
      build_pool_url(this._pool_id),
      "pool_fetch_failed"
    );
    if (pool === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._pool = pool;
    await this._refresh_members();
    await this._refresh_reservations();
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  async _refresh_members() {
    const page = await this._fetch_json(
      build_pool_resources_url(this._pool_id),
      "members_fetch_failed"
    );
    if (page !== null && Array.isArray(page.items) === true) {
      this._members = page.items;
    }
    return;
  }
  async _refresh_reservations() {
    const page = await this._fetch_json(
      build_pool_reservations_url(this._pool_id),
      "reservations_fetch_failed"
    );
    if (page !== null && Array.isArray(page.items) === true) {
      this._reservations = page.items;
    }
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
    root.classList.add("pyc-resources", "pyc-pool-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Resource pool detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-resources__heading");
    heading.textContent = "Resource pool detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-resources__back-link");
    back.setAttribute("href", "/resource-pools");
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
      loading.textContent = "Loading resource pool\u2026";
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
      error.textContent = "Failed to load this resource pool. A project id query parameter is required \u2014 try refreshing from the resource-pools list.";
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._pool));
    fragment.appendChild(this._build_resources());
    fragment.appendChild(this._build_add_resource_form());
    fragment.appendChild(this._build_reservations());
    fragment.appendChild(this._build_reserve_form());
    body.replaceChildren(fragment);
    return;
  }
  _build_summary(pool) {
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
    id_value.title = pool.pool_id;
    id_row.appendChild(id_value);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-resources__grid");
    this._append_field(grid, "Pool id", pool.pool_id);
    this._append_field(grid, "Name", pool.name);
    this._append_field(grid, "Project", pool.project_id);
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
  _build_resources() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__resources");
    section.setAttribute("data-role", "resources-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pool resources");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Resources";
    section.appendChild(heading);
    if (this._members.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-resources__status");
      empty.setAttribute("data-role", "resources-empty");
      empty.textContent = "This pool has no resource members.";
      section.appendChild(empty);
      return section;
    }
    const table = document.createElement("table");
    table.classList.add("pyc-resources__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    for (const column of ["Resource", "Added"]) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column;
      head_row.appendChild(th);
    }
    thead.appendChild(head_row);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const member of this._members) {
      const row = document.createElement("tr");
      row.classList.add("pyc-resources__row");
      const id_cell = document.createElement("td");
      const link = document.createElement("a");
      link.classList.add("pyc-resources__link");
      link.setAttribute(
        "href",
        "/resource-pools/resources/" + member.resource_id
      );
      link.textContent = short_id(member.resource_id);
      link.title = member.resource_id;
      id_cell.appendChild(link);
      row.appendChild(id_cell);
      const added_cell = document.createElement("td");
      added_cell.textContent = format_timestamp(member.added_at);
      row.appendChild(added_cell);
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    section.appendChild(table);
    return section;
  }
  _build_add_resource_form() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__create");
    section.setAttribute("data-role", "add-resource-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Add resource";
    section.appendChild(heading);
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "add-resource-form");
    const id_label = document.createElement("label");
    id_label.classList.add("pyc-resources__filter");
    id_label.textContent = "Resource id";
    const id_input = document.createElement("mj-text-field");
    id_input.classList.add("pyc-resources__input");
    id_input.setAttribute("type", "text");
    id_input.setAttribute("placeholder", "resource uuid");
    id_input.setAttribute("data-role", "add-resource-id");
    id_label.appendChild(id_input);
    form.appendChild(id_label);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "add-resource-submit");
    submit.textContent = "Add Resource";
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_add_resource(id_input.value.trim());
    });
    section.appendChild(form);
    return section;
  }
  async _submit_add_resource(resource_id) {
    if (is_valid_uuid(resource_id) === false) {
      this._show_action_status(
        "A valid resource id (UUID) is required.",
        true
      );
      return;
    }
    const body = { resource_id };
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
        this._show_action_status(
          "Add resource failed: HTTP " + String(response.status),
          true
        );
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.add_resource_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Add resource failed -- see the console.",
        true
      );
      return;
    }
    this._show_action_status("Resource added to the pool.", false);
    await this._refresh_members();
    this._render_body();
    return;
  }
  _build_reservations() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__reservations");
    section.setAttribute("data-role", "reservations-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Pool reservations");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Reservations";
    section.appendChild(heading);
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
      list.appendChild(this._build_reservation_row(reservation));
    }
    section.appendChild(list);
    return section;
  }
  _build_reservation_row(reservation) {
    const item = document.createElement("li");
    item.classList.add("pyc-resources__history-entry");
    const badge = document.createElement("span");
    badge.classList.add("pyc-badge");
    badge.setAttribute("data-tone", reservation_tone(reservation.state));
    badge.textContent = reservation.state;
    item.appendChild(badge);
    const label = document.createElement("span");
    label.classList.add("pyc-resources__reservation-label");
    const summary = " " + short_id(reservation.resource_id) + " \xB7 " + reservation.mode + " \xB7 " + format_timestamp(reservation.requested_at);
    label.textContent = summary;
    label.title = reservation.resource_id;
    item.appendChild(label);
    if (is_active_reservation(reservation.state) === true) {
      const release = document.createElement("mj-button");
      release.classList.add("pyc-resources__button");
      release.setAttribute("type", "button");
      release.setAttribute("data-role", "release-reservation");
      release.setAttribute(
        "data-reservation-id",
        reservation.reservation_id
      );
      release.textContent = "Release";
      release.addEventListener("click", () => {
        void this._submit_release(reservation.reservation_id);
      });
      item.appendChild(release);
    }
    return item;
  }
  async _submit_release(reservation_id) {
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
        this._show_action_status(
          "Release failed: HTTP " + String(response.status),
          true
        );
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.resources.release_failed",
        { reason: String(reason) }
      );
      this._show_action_status(
        "Release failed -- see the console.",
        true
      );
      return;
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
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_reserve(
        mode_select.value,
        note_input.value.trim()
      );
    });
    section.appendChild(form);
    return section;
  }
  async _submit_reserve(mode, note) {
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
        this._show_action_status(
          "Reserve failed: HTTP " + String(response.status),
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
        "Reserve failed -- see the console.",
        true
      );
      return;
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
  build_pool_reservations_url,
  build_pool_resources_url,
  build_pool_url,
  build_reservation_url,
  is_active_reservation,
  is_valid_uuid,
  pool_id_from_path,
  project_id_from_search,
  reservation_tone
};
