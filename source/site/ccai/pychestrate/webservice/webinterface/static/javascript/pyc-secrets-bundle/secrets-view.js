const SECRET_SCOPE_KINDS = [
  "ORG",
  "PROJECT",
  "USER"
];
const SECRETS_API_PATH = "/api/v1/secrets";
const SECRETS_PER_PAGE = 25;
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
    const rtnval2 = "—";
    return rtnval2;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = parsed.toLocaleString();
  return rtnval;
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
    const rtnval2 = "Could not reach the secrets service — the rotation may not have been applied. Verify before retrying.";
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
    const rtnval2 = "Could not reach the secrets service — the delete may not have been applied. Refresh to verify.";
    return rtnval2;
  }
  const rtnval = "Failed to delete the secret (HTTP " + String(status) + "). The secret is still in place.";
  return rtnval;
}
class PycSecrets extends HTMLElement {
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
    table_region.setAttribute("role", "region");
    table_region.setAttribute("aria-label", "Secrets in the selected scope");
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
    tabs.setAttribute("role", "group");
    tabs.setAttribute("aria-label", "Secret scope");
    const labels = {
      ORG: "Org",
      PROJECT: "Project",
      USER: "User"
    };
    for (const kind of SECRET_SCOPE_KINDS) {
      const tab = document.createElement("mj-button");
      tab.classList.add("pyc-secrets__tab");
      tab.setAttribute("type", "button");
      tab.id = "pyc-secrets-tab-" + kind.toLowerCase();
      tab.setAttribute("data-role", "scope-tab");
      tab.setAttribute("data-scope-kind", kind);
      tab.textContent = labels[kind];
      tab.setAttribute("aria-pressed", kind === this._state.scopeKind ? "true" : "false");
      tab.addEventListener("click", () => {
        this._select_scope(kind);
      });
      tabs.appendChild(tab);
    }
    // Arrow keys move between tabs (WAI-ARIA tabs pattern).
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
    submit.classList.add("pyc-secrets__button", "pyc-secrets__button--primary");
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
        const kind = tab.getAttribute("data-scope-kind");
        if (kind === scope_kind) {
          tab.setAttribute("aria-selected", "true");
        } else {
          tab.setAttribute("aria-selected", "false");
        }
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
    status.textContent = "Creating…";
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
      loading.textContent = "Loading secrets…";
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
    const filtered = this._filtered_secrets();
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
   * Build the secrets metadata ``<mj-table>``. The table renders
   * METADATA only -- name, scope, timestamps -- and NEVER the
   * value column on initial load. The Value column re-renders from
   * the transient ``_revealed`` / ``_reveal_errors`` maps when a
   * row's reveal state changes (see ``_refresh_row``).
   *
   * @param page_rows The current page's secrets.
   */
  _build_table(page_rows) {
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-secrets__table");
    // Sorting is client-side over the current page; the timestamp
    // columns sort by their raw ISO strings (chronological order).
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-secrets__row";
    table.rowAttrs = (secret) => ({ "data-secret-ref": secret.secret_ref });
    table.columns = [
      {
        key: "secret_ref",
        label: "Name",
        width: "20rem",
        render: (secret) => {
          const name_code = document.createElement("code");
          name_code.classList.add("pyc-secrets__ref");
          name_code.textContent = secret.secret_ref;
          return name_code;
        }
      },
      {
        key: "scope",
        label: "Scope",
        width: "12rem",
        render: (secret) => {
          const badge = document.createElement("mj-chip");
          badge.classList.add("pyc-secrets__badge");
          badge.setAttribute("data-scope-kind", secret.scope_kind);
          let scope_text = secret.scope_kind;
          if (secret.scope_ref !== null && secret.scope_ref !== void 0 && secret.scope_ref.length > 0) {
            scope_text = secret.scope_kind + " \xB7 " + secret.scope_ref;
          }
          badge.textContent = scope_text;
          return badge;
        }
      },
      {
        key: "created_at",
        label: "Created",
        width: "12rem",
        render: (secret) => format_timestamp(secret.created_at)
      },
      {
        key: "updated_at",
        label: "Updated",
        width: "12rem",
        render: (secret) => format_timestamp(secret.updated_at)
      },
      {
        key: "value",
        label: "Value",
        width: "16rem",
        sortable: false,
        cellClass: "pyc-secrets__value-cell",
        cellAttrs: () => ({ "data-role": "value-cell" }),
        render: (secret) => self._build_value_node(secret)
      },
      {
        key: "actions",
        label: "Actions",
        width: "18rem",
        sortable: false,
        cellClass: "pyc-secrets__actions",
        render: (secret) => {
          const fragment = document.createDocumentFragment();
          const reveal_button = document.createElement("mj-button");
          reveal_button.classList.add("pyc-secrets__button");
          reveal_button.setAttribute("type", "button");
          reveal_button.setAttribute("data-role", "reveal-action");
          const is_revealed = self._revealed.has(secret.secret_ref);
          reveal_button.textContent = is_revealed === true ? "Hide value" : "Reveal value";
          reveal_button.addEventListener("click", () => {
            void self._toggle_reveal(secret);
          });
          fragment.appendChild(reveal_button);
          const rotate_button = document.createElement("mj-button");
          rotate_button.classList.add("pyc-secrets__button");
          rotate_button.setAttribute("type", "button");
          rotate_button.setAttribute("data-role", "rotate-action");
          rotate_button.textContent = "Rotate";
          rotate_button.addEventListener("click", () => {
            self._open_rotate_form(secret);
          });
          fragment.appendChild(rotate_button);
          const delete_button = document.createElement("mj-button");
          delete_button.classList.add("pyc-secrets__button", "pyc-secrets__button--danger");
          delete_button.setAttribute("type", "button");
          delete_button.setAttribute("data-role", "delete-action");
          delete_button.textContent = "Delete";
          delete_button.addEventListener("click", () => {
            void self._delete_secret(secret);
          });
          fragment.appendChild(delete_button);
          return fragment;
        }
      }
    ];
    table.rows = page_rows;
    this._table = table;
    return table;
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
    masked.textContent = "••••••••";
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
      // Plaintext stays on screen for 30 seconds at most.
      window.setTimeout(() => {
        if (this._revealed.delete(secret.secret_ref) === true) {
          this._render_table_region();
        }
      }, 30000);
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
    submit.classList.add("pyc-secrets__button", "pyc-secrets__button--primary");
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
    status.textContent = "Rotating…";
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
   * Trigger a re-render of the table after a reveal toggle so the
   * row's Value + Actions cells pick up the new ``_revealed`` /
   * ``_reveal_errors`` state. The render callbacks read from those
   * maps so a single ``rows = …`` re-assignment is enough.
   *
   * @param secret_ref The secret_ref of the row that changed
   *                    (unused -- the whole page re-renders).
   */
  _refresh_row(secret_ref) {
    if (this._table === null) {
      return;
    }
    this._table.rows = this._page_slice(this._filtered_secrets());
    return;
  }
}
export {
  PycSecrets,
  SECRET_SCOPE_KINDS,
  SECRETS_PER_PAGE,
  build_secret_resource_url,
  build_secret_value_url,
  build_secrets_list_url,
  delete_error_message,
  format_timestamp,
  list_error_message,
  reveal_error_message,
  rotate_error_message
};
