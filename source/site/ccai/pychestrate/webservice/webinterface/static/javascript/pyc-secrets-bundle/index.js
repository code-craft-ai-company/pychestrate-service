// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-secrets-bundle/secrets-view.js
var SECRET_SCOPE_KINDS = [
  "ORG",
  "PROJECT",
  "USER"
];
var SECRETS_API_PATH = "/api/v1/secrets";
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
var PycSecrets = class extends HTMLElement {
  _state;
  _secrets;
  _root;
  _table_region;
  _table;
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
      loading: false,
      errored: false
    };
    this._secrets = [];
    this._root = null;
    this._table_region = null;
    this._table = null;
    this._revealed = /* @__PURE__ */ new Map();
    this._reveal_errors = /* @__PURE__ */ new Map();
  }
  /**
   * Diagnostic accessor used by unit tests to inspect the scope
   * + load state without scraping the DOM.
   */
  get viewState() {
    const rtnval = {
      scopeKind: this._state.scopeKind,
      scopeRef: this._state.scopeRef,
      loading: this._state.loading,
      errored: this._state.errored
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
   * create form, and the table region the data render replaces
   * on every fetch.
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
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-secrets__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
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
    const labels = {
      ORG: "Org",
      PROJECT: "Project",
      USER: "User"
    };
    for (const kind of SECRET_SCOPE_KINDS) {
      const tab = document.createElement("mj-button");
      tab.classList.add("pyc-secrets__tab");
      tab.setAttribute("type", "button");
      tab.setAttribute("role", "tab");
      tab.setAttribute("data-role", "scope-tab");
      tab.setAttribute("data-scope-kind", kind);
      tab.textContent = labels[kind];
      if (kind === this._state.scopeKind) {
        tab.setAttribute("aria-selected", "true");
      } else {
        tab.setAttribute("aria-selected", "false");
      }
      tab.addEventListener("click", () => {
        this._select_scope(kind);
      });
      tabs.appendChild(tab);
    }
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
    const label = document.createElement("label");
    label.classList.add("pyc-secrets__field");
    label.textContent = "Scope reference";
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-secrets__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", "scope-ref-input");
    input.setAttribute("placeholder", "project id or user id");
    input.addEventListener("change", () => {
      this._state.scopeRef = input.value.trim();
      void this._refresh();
    });
    label.appendChild(input);
    wrapper.appendChild(label);
    return wrapper;
  }
  /**
   * Build the "Create Secret" form -- name + scope-bound value.
   */
  _build_create_form() {
    const form = document.createElement("form");
    form.classList.add("pyc-secrets__create");
    form.setAttribute("data-role", "create-form");
    const name_label = document.createElement("label");
    name_label.classList.add("pyc-secrets__field");
    name_label.textContent = "Name";
    const name_input = document.createElement("mj-text-field");
    name_input.classList.add("pyc-secrets__input");
    name_input.setAttribute("type", "text");
    name_input.setAttribute("data-role", "create-name");
    name_input.setAttribute("placeholder", "vault/myteam/api-token");
    name_input.required = true;
    name_label.appendChild(name_input);
    form.appendChild(name_label);
    const value_label = document.createElement("label");
    value_label.classList.add("pyc-secrets__field");
    value_label.textContent = "Value";
    const value_input = document.createElement("mj-password-field");
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
    this._revealed.clear();
    this._reveal_errors.clear();
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
    this._render_table_region();
    const url = build_secrets_list_url(
      this._state.scopeKind,
      this._state.scopeRef
    );
    let secrets = null;
    let forbidden = false;
    try {
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.status === 403) {
        forbidden = true;
        throw new Error("secrets list forbidden");
      }
      if (response.ok === false) {
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
      this._render_table_region(forbidden);
      return;
    }
    if (Array.isArray(secrets) === false) {
      this._state.loading = false;
      this._state.errored = true;
      this._render_table_region();
      return;
    }
    this._secrets = secrets;
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
   * Re-render the table region from the current state + secrets.
   *
   * @param forbidden When true, render the scope-forbidden
   *                   message instead of the generic error.
   */
  _render_table_region(forbidden = false) {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._state.loading === true) {
      this._table = null;
      const loading = document.createElement("p");
      loading.classList.add("pyc-secrets__status");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading secrets\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._state.errored === true) {
      this._table = null;
      const error = document.createElement("p");
      error.classList.add("pyc-secrets__status", "pyc-secrets__status--error");
      if (forbidden === true) {
        error.setAttribute("data-role", "forbidden-state");
        error.textContent = "You don't have access to secrets in this scope.";
      } else {
        error.setAttribute("data-role", "error-state");
        error.textContent = "Failed to load secrets. Try refreshing.";
      }
      region.replaceChildren(error);
      return;
    }
    if (this._secrets.length === 0) {
      this._table = null;
      const empty = document.createElement("p");
      empty.classList.add("pyc-secrets__status");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No secrets in this scope yet";
      region.replaceChildren(empty);
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    return;
  }
  /**
   * Build the secrets metadata ``<mj-table>``. The table renders
   * METADATA only -- name, scope, timestamps -- and NEVER the
   * value column on initial load. The Value column re-renders from
   * the transient ``_revealed`` / ``_reveal_errors`` maps when a
   * row's reveal state changes (see ``_refresh_row``).
   */
  _build_table() {
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-secrets__table");
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
            void self._rotate_secret(secret);
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
    table.rows = this._secrets;
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
   * Rotate a secret's value via ``PUT /api/v1/secrets/{ref}``.
   * Prompts for the new value, never reads back the old one.
   *
   * @param secret The secret to rotate.
   */
  async _rotate_secret(secret) {
    const prompt_fn = window.prompt;
    if (typeof prompt_fn !== "function") {
      return;
    }
    const new_value = window.prompt(
      "Enter the new value for " + secret.secret_ref
    );
    if (new_value === null || new_value.length === 0) {
      return;
    }
    const url = build_secret_resource_url(secret.secret_ref);
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
      if (response.ok === false) {
        console.warn(
          "pychestrate.ui.secrets.rotate_failed",
          { secret_ref: secret.secret_ref, status: response.status }
        );
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.secrets.rotate_failed",
        { secret_ref: secret.secret_ref }
      );
      return;
    }
    this._revealed.delete(secret.secret_ref);
    this._reveal_errors.delete(secret.secret_ref);
    await this._refresh();
    return;
  }
  /**
   * Delete a secret via ``DELETE /api/v1/secrets/{ref}`` after a
   * confirmation prompt.
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
    const url = build_secret_resource_url(secret.secret_ref);
    try {
      const response = await fetch(url, {
        method: "DELETE",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        console.warn(
          "pychestrate.ui.secrets.delete_failed",
          { secret_ref: secret.secret_ref, status: response.status }
        );
        return;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.secrets.delete_failed",
        { secret_ref: secret.secret_ref }
      );
      return;
    }
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
   *                    (unused -- the whole table re-renders).
   */
  _refresh_row(secret_ref) {
    if (this._table === null) {
      return;
    }
    this._table.rows = this._secrets;
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-secrets-bundle/index.entry.js
var SYSTEM_GROUP_ID = "system";
var SECRETS_READ_PERMISSION = "system:secrets.read";
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
var SECRETS_ENTRY = {
  entryId: "system.secrets",
  label: "Secrets",
  route: SECRETS_ROUTE,
  requiredPermissions: [SECRETS_READ_PERMISSION],
  group: SYSTEM_GROUP_ID
};
function register_secrets_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: SYSTEM_GROUP_ID,
    label: "System",
    requiredPermissions: [SECRETS_READ_PERMISSION]
  });
  sidebar.registerEntry(SECRETS_ENTRY);
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
    console.warn(
      "pychestrate.ui.secrets.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
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
  register_secrets_sidebar,
  reveal_error_message
};
