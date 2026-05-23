import {
  build_client_detail_url,
  capability_tags,
  format_timestamp,
  liveness_tone,
  short_id,
  status_tone
} from "./clients-list-view.js";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function client_id_from_path(path) {
  if (typeof path !== "string" || path.length === 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const prefix = "/clients/";
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
function is_valid_client_id(client_id) {
  if (typeof client_id !== "string") {
    const rtnval2 = false;
    return rtnval2;
  }
  const rtnval = UUID_PATTERN.test(client_id);
  return rtnval;
}
class PycClientDetail extends HTMLElement {
  _client_id;
  _client;
  _loading;
  _errored;
  _root;
  constructor() {
    super();
    this._client_id = "";
    this._client = null;
    this._loading = false;
    this._errored = false;
    this._root = null;
  }
  /**
   * Observed attributes -- ``client-id`` may be supplied
   * explicitly by a host; otherwise it is read from the path on
   * mount.
   */
  static get observedAttributes() {
    const rtnval = ["client-id"];
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the view's
   * runtime state without scraping the DOM.
   */
  get detailState() {
    const rtnval = {
      clientId: this._client_id,
      loading: this._loading,
      errored: this._errored
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the client id, render the chrome,
   * and fetch the snapshot.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("client-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._client_id = attr_id;
    } else {
      this._client_id = client_id_from_path(window.location.pathname);
    }
    this._render_chrome();
    void this._load();
    return;
  }
  /**
   * Fetch the client snapshot. Exposed so unit tests can await a
   * load cycle.
   */
  async load() {
    await this._load();
    return;
  }
  async _load() {
    if (is_valid_client_id(this._client_id) === false) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._loading = true;
    this._errored = false;
    this._render_body();
    const client = await this._fetch_client();
    if (client === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._client = client;
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  async _fetch_client() {
    const url = build_client_detail_url(this._client_id);
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "client fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      const rtnval = body;
      return rtnval;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.detail_fetch_failed",
        { reason: String(reason) }
      );
      const rtnval = null;
      return rtnval;
    }
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-client-detail");
    root.setAttribute("role", "main");
    root.setAttribute("aria-label", "Client detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-client-detail__heading");
    heading.textContent = "Client detail";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-client-detail__back-link");
    back.setAttribute("href", "/clients");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to clients";
    root.appendChild(back);
    const body = document.createElement("div");
    body.classList.add("pyc-client-detail__body");
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
      loading.classList.add("pyc-client-detail__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading client\u2026";
      body.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._client === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-client-detail__status",
        "pyc-client-detail__status--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load this client. Try refreshing.";
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._client));
    fragment.appendChild(this._build_heartbeat(this._client));
    fragment.appendChild(this._build_pods(this._client));
    fragment.appendChild(this._build_capabilities(this._client));
    body.replaceChildren(fragment);
    return;
  }
  _build_summary(client) {
    const section = document.createElement("section");
    section.classList.add("pyc-client-detail__summary");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Client summary");
    const id_row = document.createElement("div");
    id_row.classList.add("pyc-client-detail__id-row");
    const id_value = document.createElement("span");
    id_value.classList.add("pyc-client-detail__client-id");
    id_value.setAttribute("data-role", "client-id");
    id_value.textContent = short_id(client.client_id);
    id_value.title = client.client_id;
    id_row.appendChild(id_value);
    const status_badge = document.createElement("mj-chip");
    status_badge.classList.add("pyc-client-detail__badge");
    status_badge.setAttribute("data-role", "status-badge");
    status_badge.setAttribute("data-tone", status_tone(client.status));
    status_badge.textContent = client.status;
    id_row.appendChild(status_badge);
    const liveness_badge = document.createElement("mj-chip");
    liveness_badge.classList.add("pyc-client-detail__badge");
    liveness_badge.setAttribute("data-role", "liveness-badge");
    liveness_badge.setAttribute(
      "data-tone",
      liveness_tone(client.liveness_state)
    );
    liveness_badge.textContent = client.liveness_state;
    id_row.appendChild(liveness_badge);
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-client-detail__grid");
    this._append_field(grid, "Client id", client.client_id);
    this._append_field(grid, "Project", client.project_id);
    this._append_field(grid, "Enrolled pod", client.pod_name);
    this._append_field(
      grid,
      "Enrolled",
      format_timestamp(client.enrolled_at)
    );
    this._append_field(
      grid,
      "Transport",
      client.transport_name !== null && client.transport_name !== void 0 && client.transport_name.length > 0 ? client.transport_name : "\u2014"
    );
    this._append_field(
      grid,
      "Agent version",
      client.last_agent_version !== null && client.last_agent_version !== void 0 && client.last_agent_version.length > 0 ? client.last_agent_version : "\u2014"
    );
    section.appendChild(grid);
    return section;
  }
  _build_heartbeat(client) {
    const section = document.createElement("section");
    section.classList.add("pyc-client-detail__heartbeat");
    section.setAttribute("data-role", "heartbeat-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Heartbeat");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-client-detail__section-heading");
    heading.textContent = "Heartbeat";
    section.appendChild(heading);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-client-detail__grid");
    this._append_field(
      grid,
      "Last heartbeat",
      format_timestamp(client.last_seen)
    );
    this._append_field(
      grid,
      "Degraded since",
      format_timestamp(client.degraded_at)
    );
    section.appendChild(grid);
    const note = document.createElement("p");
    note.classList.add("pyc-client-detail__note");
    note.textContent = "Full heartbeat history is not exposed by the operator REST surface \u2014 showing the latest cadence markers only.";
    section.appendChild(note);
    return section;
  }
  _build_pods(client) {
    const section = document.createElement("section");
    section.classList.add("pyc-client-detail__pods");
    section.setAttribute("data-role", "pods-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Backed pods");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-client-detail__section-heading");
    heading.textContent = "Backed pods";
    section.appendChild(heading);
    const list = document.createElement("ul");
    list.classList.add("pyc-client-detail__pod-list");
    if (client.pod_name !== null && client.pod_name.length > 0) {
      const item = document.createElement("li");
      item.classList.add("pyc-client-detail__pod-entry");
      item.textContent = client.pod_name;
      list.appendChild(item);
    } else {
      const empty = document.createElement("li");
      empty.classList.add("pyc-client-detail__pod-empty");
      empty.textContent = "This client is not enrolled under a pod.";
      list.appendChild(empty);
    }
    section.appendChild(list);
    return section;
  }
  _build_capabilities(client) {
    const section = document.createElement("section");
    section.classList.add("pyc-client-detail__capabilities");
    section.setAttribute("data-role", "capabilities-section");
    section.setAttribute("role", "region");
    section.setAttribute("aria-label", "Capabilities");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-client-detail__section-heading");
    heading.textContent = "Capabilities & attributes";
    section.appendChild(heading);
    const tags = capability_tags(client.attributes);
    if (tags.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-client-detail__status");
      empty.setAttribute("data-role", "capabilities-empty");
      empty.textContent = "No capabilities reported for this client.";
      section.appendChild(empty);
      return section;
    }
    const tag_list = document.createElement("div");
    tag_list.classList.add("pyc-client-detail__tag-list");
    for (const tag of tags) {
      const chip = document.createElement("mj-chip");
      chip.classList.add("pyc-client-detail__tag");
      chip.textContent = tag;
      tag_list.appendChild(chip);
    }
    section.appendChild(tag_list);
    return section;
  }
  _append_field(grid, label, value) {
    const field = document.createElement("div");
    field.classList.add("pyc-client-detail__field");
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
  PycClientDetail,
  client_id_from_path,
  is_valid_client_id
};
