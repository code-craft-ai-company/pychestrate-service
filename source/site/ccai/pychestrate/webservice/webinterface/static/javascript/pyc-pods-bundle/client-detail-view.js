import {
  announce_session_expired,
  build_pod_definitions_url,
  format_clock_time,
  load_projects,
  project_display_map
} from "./pods-list-view.js";
import {
  advertised_capability_tags,
  build_client_capabilities_url,
  build_client_detail_url,
  capability_tags,
  client_liveness_display,
  format_timestamp,
  latest_capability_update,
  perform_client_revoke,
  short_id,
  status_tone
} from "./clients-list-view.js";
const CLIENT_POLL_INTERVAL_MS = 15e3;
const TOAST_STACK_LIMIT = 3;
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
function client_detail_message_for_status(status) {
  if (status === 404) {
    const rtnval2 = "No client with this id.";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired — sign in again to continue.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to clients.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Couldn't reach the service — check your connection and retry.";
    return rtnval2;
  }
  const rtnval = "Failed to load this client (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
class PycClientDetail extends HTMLElement {
  _client_id;
  _client;
  _capabilities;
  _client_status;
  _pod_link;
  _project_names;
  _loading;
  _errored;
  _root;
  _toast_region;
  _stamp_region;
  _poll_timer;
  _on_visibility_change;
  constructor() {
    super();
    this._client_id = "";
    this._client = null;
    this._capabilities = [];
    this._client_status = 0;
    this._pod_link = null;
    this._project_names = null;
    this._loading = false;
    this._errored = false;
    this._root = null;
    this._toast_region = null;
    this._stamp_region = null;
    this._poll_timer = null;
    this._on_visibility_change = () => {
      this._handle_visibility_change();
    };
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
      errored: this._errored,
      errorStatus: this._client_status,
      polling: this._poll_timer !== null
    };
    return rtnval;
  }
  /**
   * Lifecycle hook -- resolve the client id, render the chrome,
   * fetch the snapshot, and start the liveness poll loop.
   */
  connectedCallback() {
    const attr_id = this.getAttribute("client-id");
    if (attr_id !== null && attr_id.length > 0) {
      this._client_id = attr_id;
    } else {
      this._client_id = client_id_from_path(window.location.pathname);
    }
    this._render_chrome();
    void this._load(false);
    this._start_poll();
    if (typeof document !== "undefined") {
      document.addEventListener(
        "visibilitychange",
        this._on_visibility_change
      );
    }
    return;
  }
  /**
   * Lifecycle hook -- stop the poll timer and drop the visibility
   * listener so a navigation away never leaks either.
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
  _start_poll() {
    if (this._poll_timer !== null) {
      return;
    }
    if (is_valid_client_id(this._client_id) === false) {
      return;
    }
    this._schedule_poll();
    return;
  }
  _schedule_poll() {
    const timer = setTimeout(() => {
      this._poll_timer = null;
      void this._poll_once();
    }, CLIENT_POLL_INTERVAL_MS);
    const handle = timer;
    if (typeof handle.unref === "function") {
      handle.unref();
    }
    this._poll_timer = timer;
    return;
  }
  /**
   * Run one poll cycle. Exposed so unit tests can drive a cycle
   * without waiting on a real timer.
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
    await this._load(true);
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
  _handle_visibility_change() {
    if (typeof document === "undefined") {
      return;
    }
    if (document.hidden === true) {
      this._stop_poll();
      return;
    }
    if (this._poll_timer === null && is_valid_client_id(this._client_id) === true) {
      void this._load(true);
      this._schedule_poll();
    }
    return;
  }
  /**
   * Fetch the client snapshot. Exposed so unit tests can await a
   * load cycle.
   */
  async load() {
    await this._load(false);
    return;
  }
  /**
   * Load / reload the client snapshot.
   *
   * @param silent When true (poll cycles), skip the intermediate
   *               loading state so the page does not flicker
   *               every poll interval.
   */
  async _load(silent) {
    if (is_valid_client_id(this._client_id) === false) {
      this._loading = false;
      this._errored = true;
      this._client_status = 404;
      this._render_body();
      return;
    }
    if (silent !== true) {
      this._loading = true;
      this._errored = false;
      this._render_body();
    }
    const envelope = await this._fetch_client();
    this._client_status = envelope.status;
    if (envelope.ok === false || envelope.body === null) {
      this._loading = false;
      this._errored = true;
      this._render_body();
      return;
    }
    this._client = envelope.body;
    this._capabilities = await this._fetch_capabilities();
    if (this._project_names === null) {
      const projects_outcome = await load_projects();
      if (projects_outcome.ok === true) {
        this._project_names = project_display_map(
          projects_outcome.projects
        );
      } else {
        // Display names are cosmetic -- fall back to raw ids
        // rather than blocking the client view.
        this._project_names = {};
      }
    }
    await this._resolve_pod_link();
    this._loading = false;
    this._errored = false;
    this._render_stamp();
    this._render_body();
    return;
  }
  async _fetch_client() {
    const url = build_client_detail_url(this._client_id);
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
        "pychestrate.ui.clients.detail_fetch_failed",
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
   * Fetch the capabilities the pod advertised
   * (``GET /api/v1/clients/{id}/capabilities``). They live apart from
   * the operator-set attributes on the client record. A failed fetch
   * yields an empty list rather than blocking the client view.
   */
  async _fetch_capabilities() {
    let rtnval = [];
    try {
      const response = await fetch(
        build_client_capabilities_url(this._client_id),
        {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        }
      );
      if (response.ok === true) {
        const body = await response.json();
        if (Array.isArray(body) === true) {
          rtnval = body;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.capabilities_fetch_failed",
        { reason: String(reason) }
      );
    }
    return rtnval;
  }
  /**
   * Resolve the enrolled pod's detail-page link. The client
   * record carries the pod *name*, but the pod detail route needs
   * the pod definition's UUID -- look it up in the project's
   * pod-definitions collection. A failed lookup leaves the pod
   * rendered as plain text rather than a dead link.
   */
  async _resolve_pod_link() {
    this._pod_link = null;
    if (this._client === null) {
      return;
    }
    const pod_name = this._client.pod_name;
    const project_id = this._client.project_id;
    if (typeof pod_name !== "string" || pod_name.length === 0) {
      return;
    }
    if (typeof project_id !== "string" || project_id.length === 0) {
      return;
    }
    let definitions = null;
    try {
      const response = await fetch(build_pod_definitions_url(project_id), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        definitions = await response.json();
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.clients.pod_link_resolution_failed",
        { reason: String(reason) }
      );
    }
    if (definitions === null || Array.isArray(definitions) === false) {
      return;
    }
    for (const definition of definitions) {
      if (definition === null || typeof definition !== "object") {
        continue;
      }
      if (definition.pod_name === pod_name && typeof definition.pod_id === "string" && definition.pod_id.length > 0) {
        this._pod_link = "/pods/" + definition.pod_id + "?project_id=" + encodeURIComponent(project_id);
        return;
      }
    }
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-client-detail");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "Client detail");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-client-detail__heading");
    heading.textContent = "Client detail";
    root.appendChild(heading);
    const toolbar = document.createElement("div");
    toolbar.classList.add("pyc-client-detail__toolbar");
    const back = document.createElement("a");
    back.classList.add("pyc-client-detail__back-link");
    back.setAttribute("href", "/clients");
    back.setAttribute("data-role", "back-link");
    back.textContent = "Back to clients";
    toolbar.appendChild(back);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-client-detail__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._load(false);
    });
    toolbar.appendChild(refresh_button);
    const stamp = document.createElement("span");
    stamp.classList.add("pyc-client-detail__stamp");
    stamp.setAttribute("data-role", "last-updated");
    toolbar.appendChild(stamp);
    this._stamp_region = stamp;
    root.appendChild(toolbar);
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-client-detail__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const body = document.createElement("div");
    body.classList.add("pyc-client-detail__body");
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
      loading.textContent = "Loading client…";
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
      const message = document.createElement("span");
      message.textContent = client_detail_message_for_status(
        this._client_status
      );
      error.appendChild(message);
      const retriable = is_valid_client_id(this._client_id) === true && this._client_status !== 404;
      if (retriable === true) {
        const retry = document.createElement("mj-button");
        retry.classList.add("pyc-client-detail__button");
        retry.setAttribute("type", "button");
        retry.setAttribute("data-role", "error-retry");
        retry.textContent = "Retry";
        retry.addEventListener("click", () => {
          void this._load(false);
        });
        error.appendChild(retry);
      }
      body.replaceChildren(error);
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_summary(this._client));
    fragment.appendChild(this._build_heartbeat(this._client));
    fragment.appendChild(this._build_capabilities(this._client));
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
    const liveness = client_liveness_display(client);
    liveness_badge.setAttribute("data-tone", liveness.tone);
    liveness_badge.textContent = liveness.label;
    id_row.appendChild(liveness_badge);
    id_row.appendChild(this._build_actions(client));
    section.appendChild(id_row);
    const grid = document.createElement("dl");
    grid.classList.add("pyc-client-detail__grid");
    this._append_field(grid, "Client id", client.client_id);
    this._append_field(
      grid,
      "Project",
      this._project_display_name(client.project_id),
      client.project_id
    );
    this._append_pod_field(grid, client);
    this._append_field(
      grid,
      "Enrolled",
      format_timestamp(client.enrolled_at)
    );
    this._append_field(grid, "Transport", client.transport_name);
    this._append_field(
      grid,
      "Runtime version",
      client.last_agent_version
    );
    section.appendChild(grid);
    return section;
  }
  /**
   * Build the operator action buttons for the client -- a single
   * Revoke action, disabled once the client is already revoked.
   */
  _build_actions(client) {
    const actions = document.createElement("span");
    actions.classList.add("pyc-client-detail__actions");
    actions.setAttribute("data-role", "client-actions");
    const revoke_button = document.createElement("mj-button");
    revoke_button.classList.add("pyc-client-detail__button");
    revoke_button.setAttribute("type", "button");
    revoke_button.setAttribute("data-role", "revoke-action");
    revoke_button.textContent = "Revoke";
    if (client.status === "REVOKED") {
      revoke_button.toggleAttribute("disabled", true);
      revoke_button.title = "This client is already revoked.";
    } else {
      revoke_button.addEventListener("click", () => {
        revoke_button.toggleAttribute("disabled", true);
        void this._on_revoke(revoke_button);
      });
    }
    actions.appendChild(revoke_button);
    return actions;
  }
  async _on_revoke(button) {
    const confirm_fn = window.confirm;
    if (typeof confirm_fn !== "function") {
      button.toggleAttribute("disabled", false);
      return;
    }
    const confirmed = window.confirm(
      "Revoke client " + short_id(this._client_id) + "? The client's certificate is revoked and the pod it backs stops receiving work. This cannot be undone from this UI."
    );
    if (confirmed === false) {
      button.toggleAttribute("disabled", false);
      return;
    }
    const outcome = await perform_client_revoke(this._client_id);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._load(true);
    }
    return;
  }
  /**
   * Append the single "Enrolled pod" field. The data model is one
   * pod per client (``pod_name`` is a scalar); the field links to
   * the pod's detail page when the pod id could be resolved.
   */
  _append_pod_field(grid, client) {
    const field = document.createElement("div");
    field.classList.add("pyc-client-detail__field");
    const term = document.createElement("dt");
    term.textContent = "Enrolled pod";
    const def = document.createElement("dd");
    const pod_name = client.pod_name;
    if (typeof pod_name === "string" && pod_name.length > 0) {
      if (this._pod_link !== null) {
        const link = document.createElement("a");
        link.classList.add("pyc-client-detail__pod-link");
        link.setAttribute("href", this._pod_link);
        link.setAttribute("data-role", "enrolled-pod-link");
        link.textContent = pod_name;
        def.appendChild(link);
      } else {
        def.textContent = pod_name;
      }
    } else {
      def.textContent = "—";
      def.title = "This client is not enrolled under a pod.";
    }
    field.appendChild(term);
    field.appendChild(def);
    grid.appendChild(field);
    return;
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
    note.textContent = "Full heartbeat history is not exposed by the operator REST surface — showing the latest cadence markers only.";
    section.appendChild(note);
    return section;
  }
  /**
   * Build the "Capabilities & attributes" section: the capabilities
   * the pod advertised -- shown as the tags dispatch matches a job
   * type's required capabilities against -- and the attributes
   * operators set on the client.
   */
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
    const advertised = advertised_capability_tags(this._capabilities);
    const attributes = capability_tags(client.attributes);
    if (advertised.length === 0 && attributes.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-client-detail__status");
      empty.setAttribute("data-role", "capabilities-empty");
      empty.textContent = "No capabilities reported for this client.";
      section.appendChild(empty);
      return section;
    }
    if (advertised.length > 0) {
      let caption = "Advertised by the pod";
      const updated_at = latest_capability_update(this._capabilities);
      if (updated_at.length > 0) {
        caption = caption + " (last update " + format_timestamp(updated_at) + ")";
      }
      section.appendChild(
        this._build_tag_group("advertised-capabilities", caption, advertised)
      );
    }
    if (attributes.length > 0) {
      section.appendChild(
        this._build_tag_group("attribute-tags", "Attributes set by operators", attributes)
      );
    }
    return section;
  }
  _build_tag_group(role, caption, tags) {
    const group = document.createElement("div");
    group.setAttribute("data-role", role);
    const label = document.createElement("p");
    label.classList.add("pyc-client-detail__note");
    label.textContent = caption;
    group.appendChild(label);
    const tag_list = document.createElement("div");
    tag_list.classList.add("pyc-client-detail__tag-list");
    for (const tag of tags) {
      const chip = document.createElement("mj-chip");
      chip.classList.add("pyc-client-detail__tag");
      chip.textContent = tag;
      tag_list.appendChild(chip);
    }
    group.appendChild(tag_list);
    return group;
  }
  _append_field(grid, label, value, title) {
    const field = document.createElement("div");
    field.classList.add("pyc-client-detail__field");
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
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-client-detail__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-client-detail__toast-dismiss");
    dismiss.setAttribute("type", "button");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "×";
    dismiss.addEventListener("click", () => {
      toast.remove();
    });
    toast.appendChild(dismiss);
    while (this._toast_region.children.length >= TOAST_STACK_LIMIT) {
      this._toast_region.removeChild(this._toast_region.firstElementChild);
    }
    this._toast_region.appendChild(toast);
    return;
  }
}
export {
  PycClientDetail,
  client_detail_message_for_status,
  client_id_from_path,
  is_valid_client_id
};
