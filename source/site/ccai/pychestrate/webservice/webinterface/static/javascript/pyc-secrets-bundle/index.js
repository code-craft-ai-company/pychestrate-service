// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/datetime.js
var ISO_DATE_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
var ZONE_DESIGNATOR_PATTERN = /(?:Z|[+-]\d{2}:?\d{2})$/i;
function pad_two(number) {
  const rtnval = (number < 10 ? "0" : "") + String(number);
  return rtnval;
}
function parse_timestamp(value) {
  if (typeof value !== "string" || value.length === 0) {
    const rtnval2 = null;
    return rtnval2;
  }
  let text = value.trim();
  if (ISO_DATE_TIME_PATTERN.test(text) === true && ZONE_DESIGNATOR_PATTERN.test(text) === false) {
    text = text.replace(" ", "T") + "Z";
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = null;
    return rtnval2;
  }
  const rtnval = parsed;
  return rtnval;
}
function zone_label(instant) {
  try {
    const parts = new Intl.DateTimeFormat(void 0, { timeZoneName: "short" }).formatToParts(instant);
    for (const part of parts) {
      if (part.type === "timeZoneName" && part.value.length > 0) {
        const rtnval2 = part.value;
        return rtnval2;
      }
    }
  } catch (error) {
  }
  const offset_minutes = -instant.getTimezoneOffset();
  const sign = offset_minutes >= 0 ? "+" : "-";
  const magnitude = Math.abs(offset_minutes);
  const rtnval = "UTC" + sign + pad_two(Math.floor(magnitude / 60)) + ":" + pad_two(magnitude % 60);
  return rtnval;
}
function format_instant(instant) {
  const date_part = instant.getFullYear() + "-" + pad_two(instant.getMonth() + 1) + "-" + pad_two(instant.getDate());
  const time_part = pad_two(instant.getHours()) + ":" + pad_two(instant.getMinutes());
  const rtnval = date_part + " " + time_part + " " + zone_label(instant);
  return rtnval;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-secrets-bundle/secrets-view.js
var SECRET_SCOPE_KINDS = [
  "ORG",
  "PROJECT",
  "USER"
];
var SECRETS_API_PATH = "/api/v1/secrets";
var SECRETS_PER_PAGE = 25;
function build_secrets_list_url(scope_kind, scope_ref) {
  const params = new URLSearchParams();
  if (scope_kind.length > 0) {
    params.set("scope_kind", scope_kind);
  }
  if (scope_kind !== "ORG" && scope_ref.length > 0) {
    params.set("scope_ref", scope_ref);
  }
  const query = params.toString();
  let rtnval = SECRETS_API_PATH;
  if (query.length > 0) {
    rtnval = SECRETS_API_PATH + "?" + query;
  }
  return rtnval;
}
function build_secret_value_url(secret_ref) {
  const segments = secret_ref.split("/");
  const encoded_segments = [];
  for (const segment of segments) {
    encoded_segments.push(encodeURIComponent(segment));
  }
  const encoded = encoded_segments.join("/");
  const rtnval = SECRETS_API_PATH + "/value/" + encoded;
  return rtnval;
}
function build_secret_resource_url(secret_ref) {
  const segments = secret_ref.split("/");
  const encoded_segments = [];
  for (const segment of segments) {
    encoded_segments.push(encodeURIComponent(segment));
  }
  const encoded = encoded_segments.join("/");
  const rtnval = SECRETS_API_PATH + "/" + encoded;
  return rtnval;
}
function format_timestamp(value) {
  if (value === null || value === void 0 || value.length === 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const parsed = parse_timestamp(value);
  if (parsed === null) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = format_instant(parsed);
  return rtnval;
}
function format_date_compact(value) {
  if (value === null || value === void 0 || value.length === 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const parsed = parse_timestamp(value);
  if (parsed === null) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = parsed.getFullYear() + "-" + pad_two(parsed.getMonth() + 1) + "-" + pad_two(parsed.getDate());
  return rtnval;
}
var SCOPE_LABELS = {
  ORG: "Org",
  PROJECT: "Project",
  USER: "User"
};
var SECRET_TABLE_COLUMNS = [
  { key: "secret_ref", label: "Name", sortable: true },
  { key: "scope", label: "Scope", sortable: true },
  { key: "created_at", label: "Created", sortable: true },
  { key: "updated_at", label: "Updated", sortable: true },
  { key: "value", label: "Value", sortable: false },
  { key: "actions", label: "Actions", sortable: false }
];
function secret_sort_text(secret, key) {
  if (key === "scope") {
    const rtnval2 = String(secret.scope_kind || "") + " " + String(secret.scope_ref || "");
    return rtnval2;
  }
  const value = secret[key];
  if (value === null || value === void 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = String(value);
  return rtnval;
}
function compare_secrets(left, right, key) {
  const rtnval = secret_sort_text(left, key).localeCompare(
    secret_sort_text(right, key),
    void 0,
    { numeric: true, sensitivity: "base" }
  );
  return rtnval;
}
function build_hidden_text(text) {
  const span = document.createElement("span");
  span.classList.add("pyc-secrets__visually-hidden");
  span.textContent = text;
  return span;
}
function build_copy_button(value, label) {
  const button = document.createElement("mj-copy-button");
  button.classList.add("pyc-secrets__copy");
  button.setAttribute("value", value);
  button.setAttribute("label", label);
  button.setAttribute("success-label", "Copied");
  button.setAttribute("size", "sm");
  button.setAttribute("icon-only", "");
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("slot", "icon-copy");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("width", "14");
  icon.setAttribute("height", "14");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("fill", "currentColor");
  path.setAttribute(
    "d",
    "M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z"
  );
  icon.appendChild(path);
  button.appendChild(icon);
  return button;
}
function build_time_cell(label, value) {
  const cell = document.createElement("td");
  cell.classList.add("pyc-secrets__time-cell");
  cell.setAttribute("data-label", label);
  if (value === null || value === void 0 || value.length === 0) {
    cell.textContent = "\u2014";
    return cell;
  }
  const time = document.createElement("time");
  time.setAttribute("datetime", value);
  time.setAttribute("title", format_timestamp(value));
  time.textContent = format_date_compact(value);
  cell.appendChild(time);
  return cell;
}
function reveal_error_message(status) {
  if (status === 403) {
    const rtnval2 = "You don't have access to this secret's value.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This secret no longer exists.";
    return rtnval2;
  }
  if (status === 410) {
    const rtnval2 = "This secret version has expired.";
    return rtnval2;
  }
  const rtnval = "Failed to read the secret value. Try again.";
  return rtnval;
}
function list_error_message(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired. Sign in again to view secrets.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have access to secrets in this scope.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Could not reach the secrets service. Check your connection and try again.";
    return rtnval2;
  }
  const rtnval = "Failed to load secrets. Try refreshing.";
  return rtnval;
}
function rotate_error_message(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired. Sign in again, then retry the rotation. The value was not changed.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have permission to rotate this secret. The value was not changed.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This secret no longer exists. Refresh the list.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Could not reach the secrets service \u2014 the rotation may not have been applied. Verify before retrying.";
    return rtnval2;
  }
  const rtnval = "Failed to rotate the secret (HTTP " + String(status) + "). The value was not changed.";
  return rtnval;
}
function delete_error_message(status) {
  if (status === 401) {
    const rtnval2 = "Your session has expired. Sign in again, then retry the delete. The secret was not deleted.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You don't have permission to delete this secret. The secret was not deleted.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This secret no longer exists. Refresh the list.";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Could not reach the secrets service \u2014 the delete may not have been applied. Refresh to verify.";
    return rtnval2;
  }
  const rtnval = "Failed to delete the secret (HTTP " + String(status) + "). The secret is still in place.";
  return rtnval;
}
var PycSecrets = class extends HTMLElement {
  _state;
  _secrets;
  _root;
  _table_region;
  _table;
  _pager;
  _rotate_region;
  _action_status;
  /**
   * Per-secret transient reveal state, keyed by secret_ref. The
   * plaintext value lives ONLY here -- never persisted, never
   * logged. Cleared on collapse and on disconnect.
   */
  _revealed;
  /**
   * Per-secret reveal error message, keyed by secret_ref.
   */
  _reveal_errors;
  /**
   * Table sort: the column key ("" for the API's order) and
   * ``"ascending"`` / ``"descending"``.
   */
  _sort;
  constructor() {
    super();
    this._state = {
      scopeKind: "ORG",
      scopeRef: "",
      filter: "",
      page: 1,
      perPage: SECRETS_PER_PAGE,
      total: 0,
      loading: false,
      errored: false,
      lastErrorStatus: 0
    };
    this._secrets = [];
    this._root = null;
    this._table_region = null;
    this._table = null;
    this._pager = null;
    this._rotate_region = null;
    this._action_status = null;
    this._revealed = /* @__PURE__ */ new Map();
    this._reveal_errors = /* @__PURE__ */ new Map();
    this._sort = { key: "", direction: "none" };
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the scope
   * + filter + load state without scraping the DOM.
   */
  get viewState() {
    const rtnval = {
      scopeKind: this._state.scopeKind,
      scopeRef: this._state.scopeRef,
      filter: this._state.filter,
      page: this._state.page,
      perPage: this._state.perPage,
      total: this._state.total,
      loading: this._state.loading,
      errored: this._state.errored,
      lastErrorStatus: this._state.lastErrorStatus
    };
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to confirm the count
   * of currently-revealed secret values.
   */
  get revealedCount() {
    const rtnval = this._revealed.size;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * first fetch when the element is inserted into the document.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  /**
   * Lifecycle hook -- clear every revealed plaintext value when
   * the element leaves the document (navigation away). The
   * reveal must never survive a navigation.
   */
  disconnectedCallback() {
    this._revealed.clear();
    this._reveal_errors.clear();
    return;
  }
  /**
   * Build the persistent chrome -- heading, scope selector,
   * create form, action status, rotate-form region, name filter,
   * and the table region + pager the data render replaces on
   * every fetch.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-secrets");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-secrets__heading");
    heading.textContent = "Secrets";
    root.appendChild(heading);
    root.appendChild(this._build_scope_tabs());
    root.appendChild(this._build_scope_ref_field());
    root.appendChild(this._build_create_form());
    const action_status = document.createElement("p");
    action_status.classList.add("pyc-secrets__action-status");
    action_status.setAttribute("data-role", "action-status");
    action_status.setAttribute("role", "status");
    action_status.setAttribute("aria-live", "polite");
    root.appendChild(action_status);
    this._action_status = action_status;
    const rotate_region = document.createElement("div");
    rotate_region.classList.add("pyc-secrets__rotate-region");
    rotate_region.setAttribute("data-role", "rotate-region");
    rotate_region.hidden = true;
    root.appendChild(rotate_region);
    this._rotate_region = rotate_region;
    root.appendChild(this._build_filter_row());
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-secrets__table-region");
    table_region.setAttribute("data-role", "table-region");
    table_region.id = "pyc-secrets-tabpanel";
    table_region.setAttribute("role", "tabpanel");
    table_region.setAttribute(
      "aria-labelledby",
      "pyc-secrets-tab-" + String(this._state.scopeKind).toLowerCase()
    );
    table_region.tabIndex = 0;
    root.appendChild(table_region);
    this._table_region = table_region;
    const pager = document.createElement("mj-pagination");
    pager.classList.add("pyc-secrets__pager");
    pager.setAttribute("data-role", "pager");
    pager.setAttribute("page", String(this._state.page));
    pager.setAttribute("page-size", String(this._state.perPage));
    pager.setAttribute("total-items", String(this._state.total));
    pager.addEventListener("mj-pagination-change", (event) => {
      this._state.page = event.detail.page;
      this._render_table_region();
    });
    this._pager = pager;
    root.appendChild(pager);
    this._root = root;
    this.replaceChildren(root);
    this._sync_scope_ref_visibility();
    return;
  }
  /**
   * Build the Org / Project / User scope tab strip.
   */
  _build_scope_tabs() {
    const tabs = document.createElement("div");
    tabs.classList.add("pyc-secrets__tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Secret scope");
    const labels = {
      ORG: "Org",
      PROJECT: "Project",
      USER: "User"
    };
    for (const kind of SECRET_SCOPE_KINDS) {
      const tab = document.createElement("button");
      tab.classList.add("pyc-secrets__tab");
      tab.setAttribute("type", "button");
      tab.setAttribute("role", "tab");
      tab.id = "pyc-secrets-tab-" + kind.toLowerCase();
      tab.setAttribute("aria-controls", "pyc-secrets-tabpanel");
      tab.setAttribute("data-role", "scope-tab");
      tab.setAttribute("data-scope-kind", kind);
      tab.textContent = labels[kind];
      const selected = kind === this._state.scopeKind;
      tab.setAttribute("aria-selected", selected === true ? "true" : "false");
      tab.tabIndex = selected === true ? 0 : -1;
      tab.addEventListener("click", () => {
        this._select_scope(kind);
      });
      tabs.appendChild(tab);
    }
    tabs.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft" && event.key !== "Home" && event.key !== "End") {
        return;
      }
      const kinds = Array.from(SECRET_SCOPE_KINDS);
      const current = kinds.indexOf(this._state.scopeKind);
      let next = current;
      if (event.key === "ArrowRight") next = (current + 1) % kinds.length;
      if (event.key === "ArrowLeft") next = (current - 1 + kinds.length) % kinds.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = kinds.length - 1;
      event.preventDefault();
      this._select_scope(kinds[next]);
      const focus_target = tabs.querySelector('[data-scope-kind="' + kinds[next] + '"]');
      if (focus_target !== null && typeof focus_target.focus === "function") {
        focus_target.focus();
      }
    });
    return tabs;
  }
  /**
   * Build the scope-ref input field. Shown only for PROJECT and
   * USER scopes -- ORG-scoped secrets are service-wide and carry
   * no scope_ref.
   */
  _build_scope_ref_field() {
    const wrapper = document.createElement("div");
    wrapper.classList.add("pyc-secrets__scope-ref");
    wrapper.setAttribute("data-role", "scope-ref-field");
    const label = document.createElement("div");
    label.classList.add("pyc-secrets__field");
    const input = document.createElement("mj-text-field");
    input.setAttribute("label", "Scope reference");
    input.classList.add("pyc-secrets__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", "scope-ref-input");
    input.setAttribute("placeholder", "project id or user id");
    input.addEventListener("mj-change", () => {
      this._state.scopeRef = input.value.trim();
      void this._refresh();
    });
    label.appendChild(input);
    wrapper.appendChild(label);
    return wrapper;
  }
  /**
   * Build the name-filter row -- a client-side substring filter
   * over the loaded secret refs.
   */
  _build_filter_row() {
    const filters = document.createElement("div");
    filters.classList.add("pyc-secrets__filters");
    const label = document.createElement("div");
    label.classList.add("pyc-secrets__field");
    const input = document.createElement("mj-text-field");
    input.setAttribute("label", "Filter by name");
    input.classList.add("pyc-secrets__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", "name-filter");
    input.setAttribute("placeholder", "substring of the secret name");
    input.addEventListener("mj-change", () => {
      this._state.filter = input.value.trim();
      this._state.page = 1;
      this._render_table_region();
    });
    label.appendChild(input);
    filters.appendChild(label);
    return filters;
  }
  /**
   * Build the "Create Secret" form -- name + scope-bound value.
   */
  _build_create_form() {
    const form = document.createElement("form");
    form.classList.add("pyc-secrets__create");
    form.setAttribute("data-role", "create-form");
    const name_label = document.createElement("div");
    name_label.classList.add("pyc-secrets__field");
    const name_input = document.createElement("mj-text-field");
    name_input.setAttribute("label", "Name");
    name_input.classList.add("pyc-secrets__input");
    name_input.setAttribute("type", "text");
    name_input.setAttribute("data-role", "create-name");
    name_input.setAttribute("placeholder", "vault/myteam/api-token");
    name_input.required = true;
    name_label.appendChild(name_input);
    form.appendChild(name_label);
    const value_label = document.createElement("div");
    value_label.classList.add("pyc-secrets__field");
    const value_input = document.createElement("mj-password-field");
    value_input.setAttribute("label", "Value");
    value_input.classList.add("pyc-secrets__input");
    value_input.setAttribute("type", "password");
    value_input.setAttribute("data-role", "create-value");
    value_input.setAttribute("autocomplete", "new-password");
    value_input.required = true;
    value_label.appendChild(value_input);
    form.appendChild(value_label);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-secrets__button");
    submit.setAttribute("variant", "primary");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "create-submit");
    submit.textContent = "Create Secret";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-secrets__create-status");
    status.setAttribute("data-role", "create-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_create(name_input, value_input, status);
    });
    return form;
  }
  /**
   * Switch the active scope tab, reset the scope_ref, and
   * re-fetch the listing.
   *
   * @param scope_kind The newly-selected scope kind.
   */
  _select_scope(scope_kind) {
    if (scope_kind === this._state.scopeKind) {
      return;
    }
    this._state.scopeKind = scope_kind;
    this._state.scopeRef = "";
    this._state.page = 1;
    this._revealed.clear();
    this._reveal_errors.clear();
    this._close_rotate_form();
    if (this._root !== null) {
      const tabs = this._root.querySelectorAll('[data-role="scope-tab"]');
      for (const tab of Array.from(tabs)) {
        const selected = tab.getAttribute("data-scope-kind") === scope_kind;
        tab.setAttribute("aria-selected", selected === true ? "true" : "false");
        tab.tabIndex = selected === true ? 0 : -1;
      }
      if (this._table_region !== null) {
        this._table_region.setAttribute(
          "aria-labelledby",
          "pyc-secrets-tab-" + String(scope_kind).toLowerCase()
        );
      }
      const input = this._root.querySelector('[data-role="scope-ref-input"]');
      if (input instanceof HTMLElement) {
        input.value = "";
      }
    }
    this._sync_scope_ref_visibility();
    void this._refresh();
    return;
  }
  /**
   * Show the scope-ref field for PROJECT / USER scopes and hide
   * it for ORG scope.
   */
  _sync_scope_ref_visibility() {
    if (this._root === null) {
      return;
    }
    const field = this._root.querySelector('[data-role="scope-ref-field"]');
    if (field instanceof HTMLElement) {
      if (this._state.scopeKind === "ORG") {
        field.hidden = true;
      } else {
        field.hidden = false;
      }
    }
    return;
  }
  /**
   * Fetch the current scope's secret metadata and re-render the
   * table region. Exposed so unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._state.loading = true;
    this._state.errored = false;
    this._state.lastErrorStatus = 0;
    this._render_table_region();
    const url = build_secrets_list_url(
      this._state.scopeKind,
      this._state.scopeRef
    );
    let secrets = null;
    let error_status = 0;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        error_status = response.status;
        throw new Error(
          "secrets fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      secrets = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.secrets.list_fetch_failed",
        { reason: String(reason) }
      );
      this._state.loading = false;
      this._state.errored = true;
      this._state.lastErrorStatus = error_status;
      this._render_table_region();
      return;
    }
    if (Array.isArray(secrets) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._state.lastErrorStatus = 0;
      this._render_table_region();
      return;
    }
    this._secrets = secrets;
    this._state.page = 1;
    this._state.loading = false;
    this._state.errored = false;
    this._render_table_region();
    return;
  }
  /**
   * POST a new secret from the create-form inputs.
   */
  async _submit_create(name_input, value_input, status) {
    const name = name_input.value.trim();
    const value = value_input.value;
    if (name.length === 0 || value.length === 0) {
      status.textContent = "Name and value are both required.";
      status.setAttribute("data-tone", "error");
      return;
    }
    if (this._state.scopeKind !== "ORG" && this._state.scopeRef.length === 0) {
      status.textContent = "A scope reference is required for project / user secrets.";
      status.setAttribute("data-tone", "error");
      return;
    }
    const payload = {
      name,
      scope_kind: this._state.scopeKind,
      value
    };
    if (this._state.scopeKind !== "ORG") {
      payload.scope_ref = this._state.scopeRef;
    }
    status.textContent = "Creating\u2026";
    status.setAttribute("data-tone", "neutral");
    try {
      const response = await fetch(SECRETS_API_PATH, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      if (response.ok === false) {
        if (response.status === 403) {
          status.textContent = "You don't have permission to create this secret.";
        } else if (response.status === 409) {
          status.textContent = "A secret with that name already exists.";
        } else {
          status.textContent = "Failed to create the secret. Try again.";
        }
        status.setAttribute("data-tone", "error");
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.secrets.create_failed",
        { reason: String(reason) }
      );
      status.textContent = "Failed to create the secret. Try again.";
      status.setAttribute("data-tone", "error");
      return;
    }
    name_input.value = "";
    value_input.value = "";
    status.textContent = "Secret created.";
    status.setAttribute("data-tone", "ok");
    await this._refresh();
    return;
  }
  /**
   * Set the rotate / delete outcome line under the create form.
   *
   * @param message The outcome text ("" clears the line).
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _set_action_status(message, tone) {
    if (this._action_status === null) {
      return;
    }
    this._action_status.textContent = message;
    this._action_status.setAttribute("data-tone", tone);
    return;
  }
  /**
   * Filter the loaded secrets by the client-side name filter.
   *
   * @returns The secrets whose ref contains the filter text.
   */
  _filtered_secrets() {
    if (this._state.filter.length === 0) {
      const rtnval2 = this._secrets;
      return rtnval2;
    }
    const needle = this._state.filter.toLowerCase();
    const rtnval = this._secrets.filter(
      (secret) => secret.secret_ref.toLowerCase().includes(needle)
    );
    return rtnval;
  }
  /**
   * Order the (filtered) secrets by the active sort column. Sorting
   * applies to the whole list before paging.
   *
   * @param secrets The secrets to order.
   *
   * @returns A sorted copy (the input when no column is active).
   */
  _sorted_secrets(secrets) {
    if (this._sort.key.length === 0) {
      return secrets;
    }
    const key = this._sort.key;
    const factor = this._sort.direction === "descending" ? -1 : 1;
    const rtnval = secrets.slice().sort(
      (left, right) => factor * compare_secrets(left, right, key)
    );
    return rtnval;
  }
  /**
   * Cycle a column's sort: ascending, descending, then the API's
   * order. Keeps keyboard focus on the header button.
   *
   * @param key The column key.
   */
  _toggle_sort(key) {
    if (this._sort.key !== key) {
      this._sort = { key, direction: "ascending" };
    } else if (this._sort.direction === "ascending") {
      this._sort = { key, direction: "descending" };
    } else {
      this._sort = { key: "", direction: "none" };
    }
    this._render_table_region();
    if (this._table_region !== null) {
      const button = this._table_region.querySelector('[data-role="sort-' + key + '"]');
      if (button !== null && typeof button.focus === "function") {
        button.focus();
      }
    }
    return;
  }
  /**
   * Slice the filtered secrets down to the current page.
   *
   * @param filtered The filtered secrets list.
   *
   * @returns The secrets for the current page.
   */
  _page_slice(filtered) {
    const page_count = Math.max(
      1,
      Math.ceil(filtered.length / this._state.perPage)
    );
    if (this._state.page > page_count) {
      this._state.page = page_count;
    }
    const start = (this._state.page - 1) * this._state.perPage;
    const end = start + this._state.perPage;
    const rtnval = filtered.slice(start, end);
    return rtnval;
  }
  _render_pager() {
    if (this._pager === null) {
      return;
    }
    this._pager.setAttribute("page", String(this._state.page));
    this._pager.setAttribute("page-size", String(this._state.perPage));
    this._pager.setAttribute("total-items", String(this._state.total));
    return;
  }
  /**
   * Re-render the table region from the current state + secrets.
   */
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.loading === true) {
      this._table = null;
      this._state.total = 0;
      const loading = document.createElement("p");
      loading.classList.add("pyc-secrets__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading secrets\u2026";
      region.replaceChildren(loading);
      this._render_pager();
      return;
    }
    if (this._state.errored === true) {
      this._table = null;
      this._state.total = 0;
      const error = document.createElement("p");
      error.classList.add("pyc-secrets__status", "pyc-secrets__status--error");
      if (this._state.lastErrorStatus === 403) {
        error.setAttribute("data-role", "forbidden-state");
      } else {
        error.setAttribute("data-role", "error-state");
      }
      error.textContent = list_error_message(this._state.lastErrorStatus);
      region.replaceChildren(error);
      this._render_pager();
      return;
    }
    const filtered = this._sorted_secrets(this._filtered_secrets());
    this._state.total = filtered.length;
    if (filtered.length === 0) {
      this._table = null;
      const empty = document.createElement("p");
      empty.classList.add("pyc-secrets__status");
      empty.setAttribute("data-role", "empty-state");
      if (this._secrets.length === 0) {
        empty.textContent = "No secrets in this scope yet";
      } else {
        empty.textContent = "No secrets match the name filter";
      }
      region.replaceChildren(empty);
      this._render_pager();
      return;
    }
    const table = this._build_table(this._page_slice(filtered));
    region.replaceChildren(table);
    this._render_pager();
    return;
  }
  /**
   * Build the secrets metadata table. The table renders METADATA
   * only -- name, scope, timestamps -- and NEVER a value on initial
   * load; a row's Value cell re-renders from the transient
   * ``_revealed`` / ``_reveal_errors`` maps when its reveal state
   * changes (see ``_refresh_row``).
   *
   * A native table in the light DOM rather than ``mj-data-table``
   * (audit ADM-14): the header scrolls with the rows inside the one
   * scroll container (the table region) instead of drifting away
   * from them, the Actions column stays pinned to the region's right
   * edge when the table is wider than the region, long names and
   * scope references are truncated with the full text in a tooltip
   * and a copy button, and a narrow region shows one card per
   * secret.
   *
   * @param page_rows The current page's secrets.
   */
  _build_table(page_rows) {
    const table = document.createElement("table");
    table.classList.add("pyc-secrets__table");
    table.setAttribute("data-role", "secrets-table");
    const caption = document.createElement("caption");
    caption.classList.add("pyc-secrets__visually-hidden");
    caption.textContent = "Secrets in the " + (SCOPE_LABELS[this._state.scopeKind] || this._state.scopeKind) + " scope";
    table.appendChild(caption);
    const head = document.createElement("thead");
    const head_row = document.createElement("tr");
    for (const column of SECRET_TABLE_COLUMNS) {
      head_row.appendChild(this._build_header_cell(column));
    }
    head.appendChild(head_row);
    table.appendChild(head);
    const body = document.createElement("tbody");
    for (const secret of page_rows) {
      body.appendChild(this._build_row(secret));
    }
    table.appendChild(body);
    this._table = table;
    return table;
  }
  /**
   * Build one column header; sortable columns hold a button that
   * cycles the sort and report it through ``aria-sort``.
   *
   * @param column One of ``SECRET_TABLE_COLUMNS``.
   */
  _build_header_cell(column) {
    const cell = document.createElement("th");
    cell.setAttribute("scope", "col");
    cell.setAttribute("data-col-key", column.key);
    if (column.key === "actions") {
      cell.classList.add("pyc-secrets__col-actions");
    }
    if (column.sortable !== true) {
      cell.textContent = column.label;
      return cell;
    }
    let direction = "none";
    if (this._sort.key === column.key) {
      direction = this._sort.direction;
    }
    cell.setAttribute("aria-sort", direction);
    const button = document.createElement("button");
    button.setAttribute("type", "button");
    button.classList.add("pyc-secrets__sort");
    button.setAttribute("data-role", "sort-" + column.key);
    button.appendChild(document.createTextNode(column.label));
    const indicator = document.createElement("span");
    indicator.classList.add("pyc-secrets__sort-indicator");
    indicator.setAttribute("aria-hidden", "true");
    if (direction === "ascending") {
      indicator.textContent = "\u25B2";
    } else if (direction === "descending") {
      indicator.textContent = "\u25BC";
    } else {
      indicator.textContent = "\u2195";
    }
    button.appendChild(indicator);
    button.addEventListener("click", () => {
      this._toggle_sort(column.key);
    });
    cell.appendChild(button);
    return cell;
  }
  /**
   * Build one secret's row. Every cell carries ``data-label`` so the
   * narrow card layout can name it.
   *
   * @param secret The secret metadata row.
   */
  _build_row(secret) {
    const row = document.createElement("tr");
    row.classList.add("pyc-secrets__row");
    row.setAttribute("data-secret-ref", secret.secret_ref);
    const name_cell = document.createElement("th");
    name_cell.setAttribute("scope", "row");
    name_cell.classList.add("pyc-secrets__name-cell");
    name_cell.setAttribute("data-label", "Name");
    const name = document.createElement("div");
    name.classList.add("pyc-secrets__name");
    const name_code = document.createElement("code");
    name_code.classList.add("pyc-secrets__ref");
    name_code.setAttribute("title", secret.secret_ref);
    name_code.textContent = secret.secret_ref;
    name.appendChild(name_code);
    name.appendChild(build_copy_button(secret.secret_ref, "Copy the name " + secret.secret_ref));
    name_cell.appendChild(name);
    row.appendChild(name_cell);
    const scope_cell = document.createElement("td");
    scope_cell.setAttribute("data-label", "Scope");
    scope_cell.appendChild(this._build_scope_node(secret));
    row.appendChild(scope_cell);
    row.appendChild(build_time_cell("Created", secret.created_at));
    row.appendChild(build_time_cell("Updated", secret.updated_at));
    const value_cell = document.createElement("td");
    value_cell.classList.add("pyc-secrets__value-cell");
    value_cell.setAttribute("data-role", "value-cell");
    value_cell.setAttribute("data-label", "Value");
    value_cell.appendChild(this._build_value_node(secret));
    row.appendChild(value_cell);
    const actions_cell = document.createElement("td");
    actions_cell.classList.add("pyc-secrets__col-actions");
    actions_cell.setAttribute("data-label", "Actions");
    actions_cell.appendChild(this._build_actions(secret));
    row.appendChild(actions_cell);
    return row;
  }
  /**
   * The scope badge, plus the scope reference (a project or user
   * id) truncated with its full text in a tooltip and a copy button.
   *
   * @param secret The secret metadata row.
   */
  _build_scope_node(secret) {
    const scope = document.createElement("div");
    scope.classList.add("pyc-secrets__scope");
    const badge = document.createElement("span");
    badge.classList.add("pyc-secrets__badge");
    badge.setAttribute("data-scope-kind", secret.scope_kind);
    badge.textContent = SCOPE_LABELS[secret.scope_kind] || secret.scope_kind;
    scope.appendChild(badge);
    if (secret.scope_ref !== null && secret.scope_ref !== void 0 && secret.scope_ref.length > 0) {
      const ref = document.createElement("code");
      ref.classList.add("pyc-secrets__scope-ref-text");
      ref.setAttribute("title", secret.scope_ref);
      ref.textContent = secret.scope_ref;
      scope.appendChild(ref);
      scope.appendChild(build_copy_button(secret.scope_ref, "Copy the scope reference " + secret.scope_ref));
    }
    return scope;
  }
  /**
   * The row's Reveal / Rotate / Delete buttons. Each button's
   * accessible name includes the secret's name.
   *
   * @param secret The secret metadata row.
   */
  _build_actions(secret) {
    const actions = document.createElement("div");
    actions.classList.add("pyc-secrets__actions");
    const reveal_button = document.createElement("mj-button");
    reveal_button.classList.add("pyc-secrets__row-action");
    reveal_button.setAttribute("type", "button");
    reveal_button.setAttribute("size", "sm");
    reveal_button.setAttribute("data-role", "reveal-action");
    this._sync_reveal_button(reveal_button, secret);
    reveal_button.addEventListener("click", () => {
      void this._toggle_reveal(secret);
    });
    actions.appendChild(reveal_button);
    const rotate_button = document.createElement("mj-button");
    rotate_button.classList.add("pyc-secrets__row-action");
    rotate_button.setAttribute("type", "button");
    rotate_button.setAttribute("size", "sm");
    rotate_button.setAttribute("data-role", "rotate-action");
    rotate_button.appendChild(document.createTextNode("Rotate"));
    rotate_button.appendChild(build_hidden_text(" " + secret.secret_ref));
    rotate_button.addEventListener("click", () => {
      this._open_rotate_form(secret);
    });
    actions.appendChild(rotate_button);
    const delete_button = document.createElement("mj-button");
    delete_button.classList.add("pyc-secrets__row-action", "pyc-secrets__row-action--danger");
    delete_button.setAttribute("type", "button");
    delete_button.setAttribute("size", "sm");
    delete_button.setAttribute("data-role", "delete-action");
    delete_button.appendChild(document.createTextNode("Delete"));
    delete_button.appendChild(build_hidden_text(" " + secret.secret_ref));
    delete_button.addEventListener("click", () => {
      void this._delete_secret(secret);
    });
    actions.appendChild(delete_button);
    return actions;
  }
  /**
   * Set the reveal button's label from the row's reveal state.
   *
   * @param button The row's reveal ``mj-button``.
   * @param secret The secret metadata row.
   */
  _sync_reveal_button(button, secret) {
    const is_revealed = this._revealed.has(secret.secret_ref);
    const label = is_revealed === true ? "Hide" : "Reveal";
    button.replaceChildren(
      document.createTextNode(label),
      build_hidden_text(" the value of " + secret.secret_ref)
    );
    return;
  }
  /**
   * Build the per-secret value-cell node -- the masked placeholder
   * by default, the transient plaintext when revealed, or the
   * reveal error when the value read was denied.
   *
   * @param secret The secret whose value cell is being built.
   *
   * @returns The value-cell content node.
   */
  _build_value_node(secret) {
    const error = this._reveal_errors.get(secret.secret_ref);
    if (error !== void 0) {
      const message = document.createElement("span");
      message.classList.add("pyc-secrets__value-error");
      message.setAttribute("data-role", "reveal-error");
      message.textContent = error;
      return message;
    }
    const value = this._revealed.get(secret.secret_ref);
    if (value !== void 0) {
      const revealed = document.createElement("code");
      revealed.classList.add("pyc-secrets__value-revealed");
      revealed.setAttribute("data-role", "revealed-value");
      revealed.textContent = value;
      return revealed;
    }
    const masked = document.createElement("span");
    masked.classList.add("pyc-secrets__value-masked");
    masked.setAttribute("data-role", "masked-value");
    masked.textContent = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022";
    return masked;
  }
  /**
   * Toggle a secret's value reveal. On reveal, fetch the value
   * from the value-read endpoint and store it ONLY in the
   * transient ``_revealed`` map. On collapse, drop the value
   * from the map immediately.
   *
   * @param secret The secret whose value is being toggled.
   */
  async _toggle_reveal(secret) {
    if (this._revealed.has(secret.secret_ref) === true) {
      this._revealed.delete(secret.secret_ref);
      this._reveal_errors.delete(secret.secret_ref);
      this._refresh_row(secret.secret_ref);
      return;
    }
    this._reveal_errors.delete(secret.secret_ref);
    const url = build_secret_value_url(secret.secret_ref);
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        this._reveal_errors.set(
          secret.secret_ref,
          reveal_error_message(response.status)
        );
        this._refresh_row(secret.secret_ref);
        return;
      }
      const body = await response.json();
      const secret_value = body;
      if (typeof secret_value.value !== "string") {
        this._reveal_errors.set(
          secret.secret_ref,
          reveal_error_message(0)
        );
        this._refresh_row(secret.secret_ref);
        return;
      }
      this._revealed.set(secret.secret_ref, secret_value.value);
      window.setTimeout(() => {
        if (this._revealed.delete(secret.secret_ref) === true) {
          this._refresh_row(secret.secret_ref);
        }
      }, 3e4);
      this._refresh_row(secret.secret_ref);
    } catch (reason) {
      console.warn(
        "pychestrate.ui.secrets.reveal_failed",
        { secret_ref: secret.secret_ref }
      );
      this._reveal_errors.set(
        secret.secret_ref,
        reveal_error_message(0)
      );
      this._refresh_row(secret.secret_ref);
    }
    return;
  }
  /**
   * Open the inline masked rotate form for one secret. The new
   * value is collected through ``mj-password-field`` inputs (with
   * a confirmation copy) -- never through a plaintext prompt.
   *
   * @param secret The secret to rotate.
   */
  _open_rotate_form(secret) {
    if (this._rotate_region === null) {
      return;
    }
    this._set_action_status("", "neutral");
    const region = this._rotate_region;
    const form = document.createElement("form");
    form.classList.add("pyc-secrets__rotate-form");
    form.setAttribute("data-role", "rotate-form");
    form.setAttribute("data-secret-ref", secret.secret_ref);
    const title = document.createElement("p");
    title.classList.add("pyc-secrets__rotate-title");
    const title_prefix = document.createTextNode("Rotate ");
    const title_ref = document.createElement("code");
    title_ref.classList.add("pyc-secrets__ref");
    title_ref.textContent = secret.secret_ref;
    title.appendChild(title_prefix);
    title.appendChild(title_ref);
    form.appendChild(title);
    const value_label = document.createElement("div");
    value_label.classList.add("pyc-secrets__field");
    const value_input = document.createElement("mj-password-field");
    value_input.setAttribute("label", "New value");
    value_input.classList.add("pyc-secrets__input");
    value_input.setAttribute("type", "password");
    value_input.setAttribute("data-role", "rotate-value");
    value_input.setAttribute("autocomplete", "new-password");
    value_input.required = true;
    value_label.appendChild(value_input);
    form.appendChild(value_label);
    const confirm_label = document.createElement("label");
    confirm_label.classList.add("pyc-secrets__field");
    confirm_label.textContent = "Confirm new value";
    const confirm_input = document.createElement("mj-password-field");
    confirm_input.classList.add("pyc-secrets__input");
    confirm_input.setAttribute("type", "password");
    confirm_input.setAttribute("data-role", "rotate-confirm");
    confirm_input.setAttribute("autocomplete", "new-password");
    confirm_input.required = true;
    confirm_label.appendChild(confirm_input);
    form.appendChild(confirm_label);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-secrets__button");
    submit.setAttribute("variant", "primary");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "rotate-submit");
    submit.textContent = "Rotate Secret";
    form.appendChild(submit);
    const cancel = document.createElement("mj-button");
    cancel.classList.add("pyc-secrets__button");
    cancel.setAttribute("type", "button");
    cancel.setAttribute("data-role", "rotate-cancel");
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => {
      this._close_rotate_form();
    });
    form.appendChild(cancel);
    const status = document.createElement("p");
    status.classList.add("pyc-secrets__create-status");
    status.setAttribute("data-role", "rotate-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_rotate(
        secret,
        value_input,
        confirm_input,
        submit,
        status
      );
    });
    region.replaceChildren(form);
    region.hidden = false;
    {
      const first_field = region.querySelector("mj-password-field, mj-text-field, input, mj-button, button");
      if (first_field !== null && typeof first_field.focus === "function") {
        first_field.focus();
        if (typeof first_field.scrollIntoView === "function") {
          first_field.scrollIntoView({ block: "nearest" });
        }
      }
    }
    return;
  }
  /**
   * Hide the rotate form and drop its transient inputs.
   */
  _close_rotate_form() {
    if (this._rotate_region === null) {
      return;
    }
    this._rotate_region.replaceChildren();
    this._rotate_region.hidden = true;
    return;
  }
  /**
   * Validate + submit the rotate form. Failures surface in the
   * form status with status-specific messages -- a failed
   * rotation is never silent.
   *
   * @param secret The secret being rotated.
   * @param value_input The new-value masked input.
   * @param confirm_input The confirmation masked input.
   * @param submit The submit button (disabled while in flight).
   * @param status The form status line.
   */
  async _submit_rotate(secret, value_input, confirm_input, submit, status) {
    const new_value = value_input.value;
    const confirm_value = confirm_input.value;
    if (new_value.length === 0) {
      status.textContent = "Enter the new secret value.";
      status.setAttribute("data-tone", "error");
      return;
    }
    if (new_value !== confirm_value) {
      status.textContent = "The confirmation does not match the new value.";
      status.setAttribute("data-tone", "error");
      return;
    }
    submit.toggleAttribute("disabled", true);
    status.textContent = "Rotating\u2026";
    status.setAttribute("data-tone", "neutral");
    const outcome = await this._do_rotate(secret.secret_ref, new_value);
    submit.toggleAttribute("disabled", false);
    if (outcome.ok === false) {
      status.textContent = outcome.message;
      status.setAttribute("data-tone", "error");
      this._set_action_status(outcome.message, "error");
      return;
    }
    this._close_rotate_form();
    this._set_action_status(
      "Secret " + secret.secret_ref + " rotated.",
      "ok"
    );
    this._revealed.delete(secret.secret_ref);
    this._reveal_errors.delete(secret.secret_ref);
    await this._refresh();
    return;
  }
  /**
   * PUT the new value to ``/api/v1/secrets/{ref}``. Exposed via
   * the rotate form only -- never reads back the old value.
   *
   * @param secret_ref The secret to rotate.
   * @param new_value The replacement value.
   *
   * @returns The rotate outcome ``{ok, status, message}``.
   */
  async _do_rotate(secret_ref, new_value) {
    const url = build_secret_resource_url(secret_ref);
    let status = 0;
    try {
      const response = await fetch(url, {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ value: new_value })
      });
      status = response.status;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.secrets.rotate_failed",
        { secret_ref }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: rotate_error_message(0)
      };
      return rtnval2;
    }
    if (status < 200 || status >= 300) {
      console.warn(
        "pychestrate.ui.secrets.rotate_failed",
        { secret_ref, status }
      );
      const rtnval2 = {
        ok: false,
        status,
        message: rotate_error_message(status)
      };
      return rtnval2;
    }
    const rtnval = {
      ok: true,
      status,
      message: "Secret rotated."
    };
    return rtnval;
  }
  /**
   * Delete a secret via ``DELETE /api/v1/secrets/{ref}`` after a
   * confirmation prompt. Failures surface in the action-status
   * line with status-specific messages.
   *
   * @param secret The secret to delete.
   */
  async _delete_secret(secret) {
    const confirm_fn = window.confirm;
    if (typeof confirm_fn !== "function") {
      return;
    }
    const confirmed = window.confirm(
      "Delete the secret " + secret.secret_ref + "? This removes every version and cannot be undone."
    );
    if (confirmed === false) {
      return;
    }
    this._set_action_status("", "neutral");
    const url = build_secret_resource_url(secret.secret_ref);
    let status = 0;
    try {
      const response = await fetch(url, {
        method: "DELETE",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      status = response.status;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.secrets.delete_failed",
        { secret_ref: secret.secret_ref }
      );
      this._set_action_status(delete_error_message(0), "error");
      return;
    }
    if (status < 200 || status >= 300) {
      console.warn(
        "pychestrate.ui.secrets.delete_failed",
        { secret_ref: secret.secret_ref, status }
      );
      this._set_action_status(delete_error_message(status), "error");
      return;
    }
    this._set_action_status(
      "Secret " + secret.secret_ref + " deleted.",
      "ok"
    );
    this._revealed.delete(secret.secret_ref);
    this._reveal_errors.delete(secret.secret_ref);
    await this._refresh();
    return;
  }
  /**
   * Update one row's Value cell and reveal button in place after a
   * reveal toggle, from the ``_revealed`` / ``_reveal_errors`` maps.
   * Updating in place (rather than re-rendering the table) keeps
   * keyboard focus on the button the user pressed.
   *
   * @param secret_ref The secret_ref of the row that changed.
   */
  _refresh_row(secret_ref) {
    if (this._table === null) {
      return;
    }
    let row = null;
    for (const candidate of Array.from(this._table.querySelectorAll("tr[data-secret-ref]"))) {
      if (candidate.getAttribute("data-secret-ref") === secret_ref) {
        row = candidate;
        break;
      }
    }
    const secret = this._secrets.find((candidate) => candidate.secret_ref === secret_ref);
    if (row === null || secret === void 0) {
      this._render_table_region();
      return;
    }
    const value_cell = row.querySelector('[data-role="value-cell"]');
    if (value_cell !== null) {
      value_cell.replaceChildren(this._build_value_node(secret));
    }
    const reveal_button = row.querySelector('[data-role="reveal-action"]');
    if (reveal_button !== null) {
      this._sync_reveal_button(reveal_button, secret);
    }
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-secrets-bundle/index.entry.js
var SECRETS_ROUTE = "/secrets";
var SECRETS_TAG = "pyc-secrets";
var SECRETS_STYLESHEET_HREF = "/static/javascript/pyc-secrets-bundle/pyc-secrets-bundle.css";
function ensure_secrets_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-secrets-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = SECRETS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-secrets-bundle");
  document.head.appendChild(link);
  return;
}
function define_secrets_element() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(SECRETS_TAG) === void 0) {
    customElements.define(SECRETS_TAG, PycSecrets);
  }
  return;
}
function classify_secrets_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === SECRETS_ROUTE || working === SECRETS_ROUTE + "/") {
    const rtnval2 = "view";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_secrets_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_secrets_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main");
  if (main === null) {
    return;
  }
  const existing = main.querySelector(SECRETS_TAG);
  if (existing !== null) {
    return;
  }
  define_secrets_element();
  ensure_secrets_stylesheet();
  const view = document.createElement(SECRETS_TAG);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_secrets_view_if_active();
  return;
}
function _boot() {
  define_secrets_element();
  const target = window;
  const handle = target.pychestrateShell;
  if (handle !== void 0 && handle.sidebar !== void 0) {
    _register_against(handle);
    return;
  }
  queueMicrotask(() => {
    const retry = target.pychestrateShell;
    if (retry !== void 0 && retry.sidebar !== void 0) {
      _register_against(retry);
      return;
    }
    window.addEventListener("pyc-site-shell-ready", () => {
      const late = target.pychestrateShell;
      if (late !== void 0 && late.sidebar !== void 0) {
        _register_against(late);
      }
    }, { once: true });
  });
  return;
}
if (typeof window !== "undefined") {
  _boot();
}
export {
  PycSecrets,
  SECRET_SCOPE_KINDS,
  build_secret_resource_url,
  build_secret_value_url,
  build_secrets_list_url,
  classify_secrets_route,
  define_secrets_element,
  ensure_secrets_stylesheet,
  format_timestamp,
  mount_secrets_view_if_active,
  reveal_error_message
};
