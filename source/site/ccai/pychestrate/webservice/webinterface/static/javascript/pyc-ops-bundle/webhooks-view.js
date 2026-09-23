const WEBHOOKS_IN_PATH = "/api/v1/webhooks/in";
const WEBHOOKS_OUT_PATH = "/api/v1/webhooks/out/subscriptions";
const TEST_EVENT_HISTORY_REFRESH_MS = 1500;
const TOAST_STACK_LIMIT = 4;
function build_integrations_url(project_id) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  const rtnval = WEBHOOKS_IN_PATH + "/integrations?" + params.toString();
  return rtnval;
}
function build_integrations_collection_url() {
  const rtnval = WEBHOOKS_IN_PATH + "/integrations";
  return rtnval;
}
function build_integration_resource_url(webhook_id) {
  const rtnval = WEBHOOKS_IN_PATH + "/integrations/" + encodeURIComponent(webhook_id);
  return rtnval;
}
function build_in_deliveries_url(provider) {
  let url = WEBHOOKS_IN_PATH + "/deliveries";
  if (typeof provider === "string" && provider.length > 0) {
    const params = new URLSearchParams();
    params.set("provider", provider);
    url = url + "?" + params.toString();
  }
  const rtnval = url;
  return rtnval;
}
function build_subscriptions_url(project_id) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  const rtnval = WEBHOOKS_OUT_PATH + "?" + params.toString();
  return rtnval;
}
function build_subscription_resource_url(subscription_id) {
  const rtnval = WEBHOOKS_OUT_PATH + "/" + encodeURIComponent(subscription_id);
  return rtnval;
}
function build_subscription_deliveries_url(subscription_id) {
  const rtnval = WEBHOOKS_OUT_PATH + "/" + encodeURIComponent(subscription_id) + "/deliveries";
  return rtnval;
}
function build_subscription_test_url(subscription_id) {
  const rtnval = WEBHOOKS_OUT_PATH + "/" + encodeURIComponent(subscription_id) + "/test";
  return rtnval;
}
function format_webhook_timestamp(value) {
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
function delivery_outcome_tone(outcome) {
  if (typeof outcome !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = outcome.toLowerCase();
  if (lowered === "delivered" || lowered === "success") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "pending" || lowered === "retrying") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (lowered === "failed" || lowered === "error") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function create_message_for_status(status, subject) {
  if (status === 201 || status === 200) {
    const rtnval2 = subject + " created.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "A " + subject.toLowerCase() + " with those identifiers already exists.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The " + subject.toLowerCase() + " request was rejected — check the fields.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to create a " + subject.toLowerCase() + ".";
    return rtnval2;
  }
  const rtnval = "Failed to create " + subject.toLowerCase() + " (HTTP " + String(status) + ").";
  return rtnval;
}
/**
 * Build a failure message from an RFC 7807 problem body: the generic
 * status sentence plus the server's first detail line, and the
 * registered providers when the server listed them. Falls back to the
 * generic sentence when the body carries no detail.
 *
 * @param status The HTTP status code.
 * @param problem The parsed problem document, or null.
 * @param subject The thing being created (e.g. "Integration").
 *
 * @returns The message to show.
 */
function problem_message_for_status(status, problem, subject) {
  const generic = create_message_for_status(status, subject);
  if (problem === null || typeof problem !== "object") {
    const rtnval2 = generic;
    return rtnval2;
  }
  const detail = problem.detail;
  if (typeof detail !== "string" || detail.trim().length === 0) {
    const rtnval2 = generic;
    return rtnval2;
  }
  const first_line = detail.split(/\r?\n/)[0].trim();
  let message = "Failed to create " + subject.toLowerCase() + ": " + first_line;
  const providers = problem.registered_providers;
  if (Array.isArray(providers) === true) {
    const listed = providers.length > 0 ? providers.join(", ") : "none";
    message = message + " Available providers: " + listed + ".";
  }
  const rtnval = message;
  return rtnval;
}
function toggle_message_for_status(status, subject, enabled) {
  const verb = enabled === true ? "enable" : "disable";
  if (status === 200) {
    const rtnval2 = subject + " " + verb + "d.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown " + subject.toLowerCase() + " — refresh the list.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to " + verb + " this " + subject.toLowerCase() + ".";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Failed to reach the webhooks service — the " + subject.toLowerCase() + " was not changed.";
    return rtnval2;
  }
  const rtnval = "Failed to " + verb + " the " + subject.toLowerCase() + " (HTTP " + String(status) + ").";
  return rtnval;
}
function test_message_for_status(status) {
  if (status === 202 || status === 200) {
    const rtnval2 = "Test event queued — the delivery history below refreshes in a moment.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "Cannot send a test event for a disabled subscription.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "Unknown subscription.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to send test events.";
    return rtnval2;
  }
  const rtnval = "Failed to send test event (HTTP " + String(status) + ").";
  return rtnval;
}
function parse_topic_filters(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    const rtnval2 = [];
    return rtnval2;
  }
  const pieces = raw.split(",");
  const rtnval = [];
  for (const piece of pieces) {
    const trimmed = piece.trim();
    if (trimmed.length > 0) {
      rtnval.push(trimmed);
    }
  }
  return rtnval;
}
class PycWebhooks extends HTMLElement {
  _projectId;
  _activeTab;
  _integrations;
  _inDeliveries;
  _inProvider;
  _subscriptions;
  /**
   * One-time signing-secret payload ``{name, secret}`` captured
   * from the last create response, or ``null``. Held only until
   * the operator dismisses the panel -- the server never returns
   * the secret again.
   */
  _signingSecret;
  /**
   * The subscription whose delivery history is currently shown,
   * or ``null``. Refreshes re-fetch it instead of leaving a
   * stale panel behind.
   */
  _historySubscription;
  _pendingHistoryTimer;
  _root;
  _panel_region;
  _toast_region;
  constructor() {
    super();
    this._projectId = "";
    this._activeTab = "inbound";
    this._integrations = [];
    this._inDeliveries = [];
    this._inProvider = "";
    this._subscriptions = [];
    this._signingSecret = null;
    this._historySubscription = null;
    this._pendingHistoryTimer = 0;
    this._root = null;
    this._panel_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to read the active
   * tab without scraping the DOM.
   */
  get activeTab() {
    const rtnval = this._activeTab;
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to read the active
   * project id.
   */
  get projectId() {
    const rtnval = this._projectId;
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to read the inbound
   * provider filter.
   */
  get inboundProviderFilter() {
    const rtnval = this._inProvider;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome when inserted.
   */
  connectedCallback() {
    this._render_chrome();
    return;
  }
  /**
   * Lifecycle hook -- drop any pending history-refresh timer so
   * it cannot fire against a detached view.
   */
  disconnectedCallback() {
    if (this._pendingHistoryTimer !== 0) {
      clearTimeout(this._pendingHistoryTimer);
      this._pendingHistoryTimer = 0;
    }
    return;
  }
  /**
   * Build the persistent chrome -- heading, project input, tab
   * strip, toast region, panel region.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-ops");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-ops__heading");
    heading.textContent = "Webhooks";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-ops__controls");
    const project_label = document.createElement("label");
    project_label.classList.add("pyc-ops__field");
    project_label.textContent = "Project";
    const project_input = document.createElement("mj-text-field");
    project_input.classList.add("pyc-ops__input");
    project_input.setAttribute("type", "text");
    project_input.setAttribute("placeholder", "project id");
    project_input.setAttribute("data-role", "project-input");
    project_input.addEventListener("change", () => {
      this._projectId = project_input.value.trim();
      void this._refresh_active_tab();
    });
    project_label.appendChild(project_input);
    controls.appendChild(project_label);
    root.appendChild(controls);
    const tabs = document.createElement("div");
    tabs.classList.add("pyc-ops__tabs");
    tabs.setAttribute("role", "tablist");
    const inbound_tab = this._build_tab_button("inbound", "Inbound");
    const outbound_tab = this._build_tab_button("outbound", "Outbound");
    tabs.appendChild(inbound_tab);
    tabs.appendChild(outbound_tab);
    root.appendChild(tabs);
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-ops__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const panel_region = document.createElement("div");
    panel_region.classList.add("pyc-ops__panel-region");
    panel_region.setAttribute("data-role", "panel-region");
    root.appendChild(panel_region);
    this._panel_region = panel_region;
    this._root = root;
    this.replaceChildren(root);
    this._render_active_tab();
    return;
  }
  /**
   * Build a single tab button.
   *
   * @param tab_id The tab identifier (``"inbound"`` |
   *               ``"outbound"``).
   * @param label The visible tab label.
   *
   * @returns The created tab button.
   */
  _build_tab_button(tab_id, label) {
    const button = document.createElement("mj-button");
    button.classList.add("pyc-ops__tab");
    button.setAttribute("type", "button");
    button.setAttribute("role", "tab");
    button.setAttribute("data-role", "tab-" + tab_id);
    button.setAttribute(
      "aria-selected",
      this._activeTab === tab_id ? "true" : "false"
    );
    button.textContent = label;
    button.addEventListener("click", () => {
      this.selectTab(tab_id);
    });
    return button;
  }
  /**
   * Switch the active tab and re-render the panel. Exposed so
   * unit tests can drive tab selection.
   *
   * @param tab_id The tab to activate.
   */
  selectTab(tab_id) {
    if (tab_id !== "inbound" && tab_id !== "outbound") {
      return;
    }
    this._activeTab = tab_id;
    if (this._root !== null) {
      const inbound = this._root.querySelector('[data-role="tab-inbound"]');
      const outbound = this._root.querySelector(
        '[data-role="tab-outbound"]'
      );
      if (inbound instanceof HTMLElement) {
        inbound.setAttribute(
          "aria-selected",
          tab_id === "inbound" ? "true" : "false"
        );
      }
      if (outbound instanceof HTMLElement) {
        outbound.setAttribute(
          "aria-selected",
          tab_id === "outbound" ? "true" : "false"
        );
      }
    }
    this._render_active_tab();
    void this._refresh_active_tab();
    return;
  }
  /**
   * Render the static panel scaffolding for the active tab.
   */
  _render_active_tab() {
    if (this._panel_region === null) {
      return;
    }
    if (this._activeTab === "inbound") {
      this._render_inbound_panel();
    } else {
      this._render_outbound_panel();
    }
    return;
  }
  /**
   * Re-fetch the data for whichever tab is currently active.
   */
  async _refresh_active_tab() {
    if (this._activeTab === "inbound") {
      await this.refreshInbound();
    } else {
      await this.refreshOutbound();
    }
    return;
  }
  // ----------------------------------------------------------------
  // Inbound tab
  // ----------------------------------------------------------------
  /**
   * Render the inbound-panel scaffolding -- create-form toggle,
   * refresh action, integrations table region, recent-deliveries
   * heading + provider filter + region.
   */
  _render_inbound_panel() {
    if (this._panel_region === null) {
      return;
    }
    const panel = document.createElement("div");
    panel.classList.add("pyc-ops__panel");
    panel.setAttribute("data-role", "inbound-panel");
    const actions = document.createElement("div");
    actions.classList.add("pyc-ops__controls");
    const create_button = document.createElement("mj-button");
    create_button.classList.add("pyc-ops__button");
    create_button.setAttribute("type", "button");
    create_button.setAttribute("data-role", "inbound-create-toggle");
    create_button.textContent = "Create Integration";
    create_button.addEventListener("click", () => {
      this._toggle_inbound_form(panel);
    });
    actions.appendChild(create_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-ops__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "inbound-refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this.refreshInbound();
    });
    actions.appendChild(refresh_button);
    panel.appendChild(actions);
    const form_region = document.createElement("div");
    form_region.classList.add("pyc-ops__form-region");
    form_region.setAttribute("data-role", "inbound-form-region");
    form_region.hidden = true;
    panel.appendChild(form_region);
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-ops__table-region");
    table_region.setAttribute("data-role", "inbound-table-region");
    panel.appendChild(table_region);
    // The inbound delivery ledger is keyed by (provider, hook,
    // delivery id) and carries no project scope -- title it
    // honestly rather than implying a project filter applies.
    const deliveries_heading = document.createElement("h2");
    deliveries_heading.classList.add("pyc-ops__subheading");
    deliveries_heading.textContent = "All Recent Inbound Deliveries";
    panel.appendChild(deliveries_heading);
    const deliveries_note = document.createElement("p");
    deliveries_note.classList.add("pyc-ops__note");
    deliveries_note.setAttribute("data-role", "inbound-deliveries-note");
    deliveries_note.textContent = "The inbound replay ledger across every project. It records that a delivery was received; per-delivery dispatch outcomes are not recorded yet.";
    panel.appendChild(deliveries_note);
    const filter_row = document.createElement("div");
    filter_row.classList.add("pyc-ops__controls");
    const provider_label = document.createElement("label");
    provider_label.classList.add("pyc-ops__field");
    provider_label.textContent = "Provider";
    const provider_select = document.createElement("mj-select");
    provider_select.classList.add("pyc-ops__select");
    provider_select.setAttribute("data-role", "in-provider-filter");
    provider_select.addEventListener("change", () => {
      this._inProvider = provider_select.value;
      void this._load_inbound_deliveries();
    });
    provider_label.appendChild(provider_select);
    filter_row.appendChild(provider_label);
    panel.appendChild(filter_row);
    const deliveries_region = document.createElement("div");
    deliveries_region.classList.add("pyc-ops__table-region");
    deliveries_region.setAttribute(
      "data-role",
      "inbound-deliveries-region"
    );
    panel.appendChild(deliveries_region);
    this._panel_region.replaceChildren(panel);
    this._sync_provider_options();
    this._render_inbound_table();
    this._render_inbound_deliveries();
    return;
  }
  /**
   * Fetch the inbound integrations + recent deliveries and
   * re-render. The delivery ledger is global, so it loads even
   * when no project id is set. Exposed so unit tests can await
   * a fetch cycle.
   */
  async refreshInbound() {
    if (this._projectId.length === 0) {
      this._integrations = [];
      this._render_inbound_table();
    } else {
      await this._load_integrations();
    }
    await this._load_inbound_deliveries();
    return;
  }
  async _load_integrations() {
    let items = null;
    try {
      const url = build_integrations_url(this._projectId);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (Array.isArray(page.items) === true) {
          items = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.integrations_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._integrations = items ?? [];
    this._sync_provider_options();
    this._render_inbound_table();
    return;
  }
  async _load_inbound_deliveries() {
    let items = null;
    try {
      const url = build_in_deliveries_url(this._inProvider);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (Array.isArray(page.items) === true) {
          items = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.in_deliveries_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._inDeliveries = items ?? [];
    this._sync_provider_options();
    this._render_inbound_deliveries();
    return;
  }
  /**
   * Rebuild the provider-filter options from the providers seen
   * in the loaded integrations + deliveries, preserving the
   * current selection.
   */
  _sync_provider_options() {
    if (this._panel_region === null) {
      return;
    }
    const select = this._panel_region.querySelector(
      '[data-role="in-provider-filter"]'
    );
    if (select instanceof HTMLElement === false) {
      return;
    }
    const providers = [];
    for (const integration of this._integrations) {
      if (typeof integration.provider === "string" && integration.provider.length > 0 && providers.includes(integration.provider) === false) {
        providers.push(integration.provider);
      }
    }
    for (const delivery of this._inDeliveries) {
      if (typeof delivery.provider === "string" && delivery.provider.length > 0 && providers.includes(delivery.provider) === false) {
        providers.push(delivery.provider);
      }
    }
    if (this._inProvider.length > 0 && providers.includes(this._inProvider) === false) {
      providers.push(this._inProvider);
    }
    providers.sort();
    const all_option = document.createElement("mj-option");
    all_option.setAttribute("value", "");
    all_option.textContent = "All providers";
    const options = [all_option];
    for (const provider of providers) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", provider);
      option.textContent = provider;
      options.push(option);
    }
    select.replaceChildren(...options);
    select.value = this._inProvider;
    return;
  }
  _render_inbound_table() {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="inbound-table-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (this._projectId.length === 0) {
      el.replaceChildren(
        this._notice("Enter a project id to view integrations.")
      );
      return;
    }
    if (this._integrations.length === 0) {
      el.replaceChildren(
        this._notice("No inbound integrations for this project yet")
      );
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-ops__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowAttrs = (integration) => ({
      "data-webhook-id": integration.webhook_id
    });
    table.columns = [
      { key: "provider", label: "Provider", width: "10rem" },
      { key: "hook_name", label: "Hook", width: "10rem" },
      {
        key: "receiver_path",
        label: "Receiver path",
        width: "20rem",
        sortable: false,
        render: (integration) => integration.receiver_path ?? "—"
      },
      {
        key: "secret_configured",
        label: "Shared secret",
        width: "14rem",
        sortable: false,
        // The API never returns the secret -- only whether the
        // vault holds it and under which reference.
        render: (integration) => {
          const configured = integration.secret_configured === true;
          const chip = self._badge(
            configured === true ? "in vault" : "missing",
            configured === true ? "ok" : "error"
          );
          chip.setAttribute("data-role", "integration-secret");
          chip.setAttribute(
            "title",
            configured === true ? "Stored in the secrets vault as " + String(integration.secret_ref) : "The integration's vault secret no longer exists, so its deliveries cannot be verified."
          );
          return chip;
        }
      },
      {
        key: "enabled",
        label: "State",
        width: "8rem",
        render: (integration) => self._badge(
          integration.enabled === true ? "enabled" : "disabled",
          integration.enabled === true ? "ok" : "neutral"
        )
      },
      {
        key: "actions",
        label: "Actions",
        width: "10rem",
        sortable: false,
        render: (integration) => {
          const toggle_button = document.createElement("mj-button");
          toggle_button.classList.add(
            "pyc-ops__button",
            "pyc-ops__row-action"
          );
          toggle_button.setAttribute("type", "button");
          toggle_button.setAttribute("data-role", "integration-toggle");
          toggle_button.textContent = integration.enabled === true ? "Disable" : "Enable";
          toggle_button.addEventListener("click", () => {
            toggle_button.toggleAttribute("disabled", true);
            void self._on_toggle_integration(integration, toggle_button);
          });
          return toggle_button;
        }
      }
    ];
    table.rows = this._integrations;
    el.replaceChildren(table);
    return;
  }
  async _on_toggle_integration(integration, button) {
    const next_enabled = integration.enabled !== true;
    if (next_enabled === false) {
      const confirm_fn = window.confirm;
      if (typeof confirm_fn !== "function") {
        button.toggleAttribute("disabled", false);
        return;
      }
      const confirmed = window.confirm(
        "Disable the inbound integration " + integration.provider + "/" + integration.hook_name + "? The receiver will reject its deliveries until it is re-enabled."
      );
      if (confirmed === false) {
        button.toggleAttribute("disabled", false);
        return;
      }
    }
    const outcome = await this.updateIntegration(
      integration.webhook_id,
      next_enabled
    );
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._load_integrations();
    }
    return;
  }
  /**
   * PATCH an inbound integration's ``enabled`` flag. Exposed so
   * unit tests can drive a toggle without a row button.
   *
   * @param webhook_id The integration to update.
   * @param enabled The desired enabled state.
   *
   * @returns The update outcome.
   */
  async updateIntegration(webhook_id, enabled) {
    let status = 0;
    try {
      const response = await fetch(
        build_integration_resource_url(webhook_id),
        {
          method: "PATCH",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ enabled })
        }
      );
      status = response.status;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.integration_update_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: toggle_message_for_status(0, "Integration", enabled)
      };
      return rtnval2;
    }
    const ok = status === 200;
    const rtnval = {
      ok,
      status,
      message: toggle_message_for_status(status, "Integration", enabled)
    };
    return rtnval;
  }
  _render_inbound_deliveries() {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="inbound-deliveries-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (this._inDeliveries.length === 0) {
      el.replaceChildren(this._notice("No recent inbound deliveries"));
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-ops__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.columns = [
      { key: "provider", label: "Provider", width: "10rem" },
      { key: "hook_name", label: "Hook", width: "10rem" },
      { key: "delivery_id", label: "Delivery id", width: "16rem", sortable: false },
      {
        key: "status",
        label: "Status",
        width: "8rem",
        sortable: false,
        // The ledger only proves receipt -- an honest "recorded"
        // chip, not a fabricated dispatch outcome.
        render: (delivery) => {
          const chip = self._badge("recorded", "neutral");
          chip.setAttribute(
            "title",
            "The replay ledger records that this delivery was received. Its dispatch outcome is not recorded yet."
          );
          return chip;
        }
      },
      {
        key: "first_seen_at",
        label: "First seen",
        width: "14rem",
        render: (delivery) => format_webhook_timestamp(delivery.first_seen_at)
      }
    ];
    table.rows = this._inDeliveries;
    el.replaceChildren(table);
    return;
  }
  _toggle_inbound_form(panel) {
    const region = panel.querySelector(
      '[data-role="inbound-form-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (el.hidden === true) {
      this._render_inbound_form(el);
      el.hidden = false;
    } else {
      el.hidden = true;
    }
    return;
  }
  _render_inbound_form(region) {
    const form = document.createElement("form");
    form.classList.add("pyc-ops__form");
    form.setAttribute("data-role", "inbound-form");
    const provider_input = this._build_field(
      form,
      "Provider",
      "inbound-provider",
      "generic"
    );
    const hook_input = this._build_field(
      form,
      "Hook name",
      "inbound-hook",
      "push"
    );
    // The shared secret is write-only: it goes to the secrets vault
    // and is never shown again. An existing vault secret can be named
    // instead.
    const secret_label = document.createElement("label");
    secret_label.classList.add("pyc-ops__field");
    secret_label.textContent = "Shared secret";
    const secret_input = document.createElement("mj-password-field");
    secret_input.classList.add("pyc-ops__input");
    secret_input.setAttribute("type", "password");
    secret_input.setAttribute("autocomplete", "new-password");
    secret_input.setAttribute("data-role", "inbound-secret");
    secret_input.setAttribute("placeholder", "the HMAC key the sender signs with");
    secret_label.appendChild(secret_input);
    form.appendChild(secret_label);
    const secret_ref_input = this._build_field(
      form,
      "Or an existing vault secret",
      "inbound-secret-ref",
      "vault secret name (instead of a shared secret)"
    );
    const secret_note = document.createElement("p");
    secret_note.classList.add("pyc-ops__note");
    secret_note.setAttribute("data-role", "inbound-secret-note");
    secret_note.textContent = "The shared secret is stored in the secrets vault for this project and is never displayed again. Storing it needs permission to write the project's secrets.";
    form.appendChild(secret_note);
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-ops__submit");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "inbound-submit");
    submit.textContent = "Create Integration";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-ops__form-status");
    status.setAttribute("data-role", "inbound-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_inbound(
        provider_input,
        hook_input,
        secret_input,
        secret_ref_input,
        submit,
        status
      );
    });
    region.replaceChildren(form);
    return;
  }
  async _submit_inbound(provider_input, hook_input, secret_input, secret_ref_input, submit, status) {
    const provider = provider_input.value.trim();
    const hook_name = hook_input.value.trim();
    const secret = typeof secret_input.value === "string" ? secret_input.value : "";
    const secret_ref = secret_ref_input.value.trim();
    if (provider.length === 0 || hook_name.length === 0) {
      status.textContent = "Provider and hook name are required.";
      return;
    }
    if (secret.length === 0 && secret_ref.length === 0) {
      status.textContent = "Enter the shared secret, or name an existing vault secret.";
      return;
    }
    if (secret.length > 0 && secret_ref.length > 0) {
      status.textContent = "Enter either a shared secret or a vault secret name, not both.";
      return;
    }
    submit.toggleAttribute("disabled", true);
    status.textContent = "Creating integration…";
    const outcome = await this._do_create_integration(
      provider,
      hook_name,
      secret,
      secret_ref
    );
    // Never keep the key in the page after it has been sent.
    secret_input.value = "";
    submit.toggleAttribute("disabled", false);
    status.textContent = outcome.ok === true ? "" : outcome.message;
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      provider_input.value = "";
      hook_input.value = "";
      secret_ref_input.value = "";
      await this.refreshInbound();
    }
    return;
  }
  /**
   * POST an inbound-integration create request. Exposed so unit
   * tests can invoke a create without a real form-submit event.
   *
   * @param provider The webhook provider name.
   * @param hook_name The hook name.
   * @param secret The shared secret (stored in the vault; write-only),
   *               or an empty string when ``secret_ref`` is used.
   * @param secret_ref Name of an existing vault secret, or an empty
   *                   string when ``secret`` is supplied.
   *
   * @returns The create outcome.
   */
  async createIntegration(provider, hook_name, secret, secret_ref = "") {
    const rtnval = await this._do_create_integration(
      provider,
      hook_name,
      secret,
      secret_ref
    );
    return rtnval;
  }
  async _do_create_integration(provider, hook_name, secret, secret_ref) {
    if (this._projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        message: "Enter a project id before creating an integration."
      };
      return rtnval2;
    }
    const payload = {
      project_id: this._projectId,
      provider,
      hook_name
    };
    if (typeof secret === "string" && secret.length > 0) {
      payload.secret = secret;
    }
    if (typeof secret_ref === "string" && secret_ref.length > 0) {
      payload.secret_ref = secret_ref;
    }
    let status = 0;
    let problem = null;
    try {
      const response = await fetch(
        build_integrations_collection_url(),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify(payload)
        }
      );
      status = response.status;
      if (response.ok === false) {
        try {
          problem = await response.json();
        } catch (parse_reason) {
          problem = null;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.integration_create_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: "Failed to reach the webhooks service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    let message = create_message_for_status(status, "Integration");
    if (ok === false) {
      message = problem_message_for_status(status, problem, "Integration");
    }
    const rtnval = {
      ok,
      status,
      message
    };
    return rtnval;
  }
  // ----------------------------------------------------------------
  // Outbound tab
  // ----------------------------------------------------------------
  /**
   * Render the outbound-panel scaffolding -- create-form toggle,
   * refresh action, one-time signing-secret region, subscriptions
   * table region, delivery-history region.
   */
  _render_outbound_panel() {
    if (this._panel_region === null) {
      return;
    }
    const panel = document.createElement("div");
    panel.classList.add("pyc-ops__panel");
    panel.setAttribute("data-role", "outbound-panel");
    const actions = document.createElement("div");
    actions.classList.add("pyc-ops__controls");
    const create_button = document.createElement("mj-button");
    create_button.classList.add("pyc-ops__button");
    create_button.setAttribute("type", "button");
    create_button.setAttribute("data-role", "outbound-create-toggle");
    create_button.textContent = "Create Subscription";
    create_button.addEventListener("click", () => {
      this._toggle_outbound_form(panel);
    });
    actions.appendChild(create_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-ops__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "outbound-refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this.refreshOutbound();
    });
    actions.appendChild(refresh_button);
    panel.appendChild(actions);
    const form_region = document.createElement("div");
    form_region.classList.add("pyc-ops__form-region");
    form_region.setAttribute("data-role", "outbound-form-region");
    form_region.hidden = true;
    panel.appendChild(form_region);
    const secret_region = document.createElement("div");
    secret_region.classList.add("pyc-ops__secret-region");
    secret_region.setAttribute("data-role", "signing-secret-region");
    secret_region.hidden = true;
    panel.appendChild(secret_region);
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-ops__table-region");
    table_region.setAttribute("data-role", "outbound-table-region");
    panel.appendChild(table_region);
    const history_region = document.createElement("div");
    history_region.classList.add("pyc-ops__table-region");
    history_region.setAttribute("data-role", "outbound-history-region");
    panel.appendChild(history_region);
    this._panel_region.replaceChildren(panel);
    this._render_signing_secret();
    this._render_outbound_table();
    return;
  }
  /**
   * Fetch the outbound subscriptions and re-render. When a
   * delivery-history panel is open its data is re-fetched too so
   * the panel never goes stale. Exposed so unit tests can await
   * a fetch cycle.
   */
  async refreshOutbound() {
    if (this._projectId.length === 0) {
      this._subscriptions = [];
      this._historySubscription = null;
      this._render_outbound_table();
      this._render_outbound_history(null, []);
      return;
    }
    let items = null;
    try {
      const url = build_subscriptions_url(this._projectId);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (Array.isArray(page.items) === true) {
          items = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.subscriptions_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._subscriptions = items ?? [];
    this._render_outbound_table();
    if (this._historySubscription !== null) {
      const open_subscription = this._historySubscription;
      const deliveries = await this.loadSubscriptionDeliveries(
        open_subscription.subscription_id
      );
      this._render_outbound_history(open_subscription, deliveries);
    }
    return;
  }
  _render_outbound_table() {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="outbound-table-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (this._projectId.length === 0) {
      el.replaceChildren(
        this._notice("Enter a project id to view subscriptions.")
      );
      return;
    }
    if (this._subscriptions.length === 0) {
      el.replaceChildren(
        this._notice("No outbound subscriptions for this project yet")
      );
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-ops__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowAttrs = (subscription) => ({
      "data-subscription-id": subscription.subscription_id
    });
    table.columns = [
      { key: "name", label: "Name", width: "12rem" },
      { key: "url", label: "URL", width: "20rem", sortable: false },
      {
        key: "topic_filters",
        label: "Topics",
        width: "16rem",
        sortable: false,
        render: (subscription) => subscription.topic_filters.join(", ") || "all"
      },
      {
        key: "enabled",
        label: "State",
        width: "8rem",
        render: (subscription) => self._badge(
          subscription.enabled === true ? "enabled" : "disabled",
          subscription.enabled === true ? "ok" : "neutral"
        )
      },
      {
        key: "actions",
        label: "Actions",
        width: "22rem",
        sortable: false,
        render: (subscription) => {
          const fragment = document.createDocumentFragment();
          const test_button = document.createElement("mj-button");
          test_button.classList.add("pyc-ops__button", "pyc-ops__row-action");
          test_button.setAttribute("type", "button");
          test_button.setAttribute("data-role", "test-event");
          test_button.textContent = "Send Test Event";
          test_button.addEventListener("click", () => {
            test_button.toggleAttribute("disabled", true);
            void self._on_test(subscription, test_button);
          });
          fragment.appendChild(test_button);
          const history_button = document.createElement("mj-button");
          history_button.classList.add(
            "pyc-ops__button",
            "pyc-ops__row-action"
          );
          history_button.setAttribute("type", "button");
          history_button.setAttribute("data-role", "delivery-history");
          history_button.textContent = "Delivery History";
          history_button.addEventListener("click", () => {
            history_button.toggleAttribute("disabled", true);
            void self._on_history(subscription, history_button);
          });
          fragment.appendChild(history_button);
          const toggle_button = document.createElement("mj-button");
          toggle_button.classList.add(
            "pyc-ops__button",
            "pyc-ops__row-action"
          );
          toggle_button.setAttribute("type", "button");
          toggle_button.setAttribute("data-role", "subscription-toggle");
          toggle_button.textContent = subscription.enabled === true ? "Disable" : "Enable";
          toggle_button.addEventListener("click", () => {
            toggle_button.toggleAttribute("disabled", true);
            void self._on_toggle_subscription(subscription, toggle_button);
          });
          fragment.appendChild(toggle_button);
          return fragment;
        }
      }
    ];
    table.rows = this._subscriptions;
    el.replaceChildren(table);
    return;
  }
  async _on_toggle_subscription(subscription, button) {
    const next_enabled = subscription.enabled !== true;
    if (next_enabled === false) {
      const confirm_fn = window.confirm;
      if (typeof confirm_fn !== "function") {
        button.toggleAttribute("disabled", false);
        return;
      }
      const confirmed = window.confirm(
        "Disable the subscription " + subscription.name + "? Deliveries to its URL stop until it is re-enabled."
      );
      if (confirmed === false) {
        button.toggleAttribute("disabled", false);
        return;
      }
    }
    const outcome = await this.updateSubscription(
      subscription.subscription_id,
      next_enabled
    );
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this.refreshOutbound();
    }
    return;
  }
  /**
   * PATCH an outbound subscription's ``enabled`` flag. Exposed so
   * unit tests can drive a toggle without a row button.
   *
   * @param subscription_id The subscription to update.
   * @param enabled The desired enabled state.
   *
   * @returns The update outcome.
   */
  async updateSubscription(subscription_id, enabled) {
    let status = 0;
    try {
      const response = await fetch(
        build_subscription_resource_url(subscription_id),
        {
          method: "PATCH",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ enabled })
        }
      );
      status = response.status;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.subscription_update_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: toggle_message_for_status(0, "Subscription", enabled)
      };
      return rtnval2;
    }
    const ok = status === 200;
    const rtnval = {
      ok,
      status,
      message: toggle_message_for_status(status, "Subscription", enabled)
    };
    return rtnval;
  }
  async _on_test(subscription, button) {
    const outcome = await this._do_test(subscription.subscription_id);
    button.toggleAttribute("disabled", false);
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      this._schedule_history_refresh(subscription);
    }
    return;
  }
  /**
   * Schedule a short-delay refresh of the delivery history after
   * a test event, so the operator sees the recorded attempt
   * without hunting for a refresh control.
   *
   * @param subscription The subscription that was tested.
   */
  _schedule_history_refresh(subscription) {
    if (this._pendingHistoryTimer !== 0) {
      clearTimeout(this._pendingHistoryTimer);
    }
    this._pendingHistoryTimer = setTimeout(() => {
      this._pendingHistoryTimer = 0;
      void this._load_and_render_history(subscription);
    }, TEST_EVENT_HISTORY_REFRESH_MS);
    return;
  }
  async _load_and_render_history(subscription) {
    const deliveries = await this.loadSubscriptionDeliveries(
      subscription.subscription_id
    );
    this._historySubscription = subscription;
    this._render_outbound_history(subscription, deliveries);
    return;
  }
  /**
   * POST a test event for one subscription. Exposed so unit
   * tests can drive a test without a row button.
   *
   * @param subscription_id The subscription to test.
   *
   * @returns The test outcome.
   */
  async sendTestEvent(subscription_id) {
    const rtnval = await this._do_test(subscription_id);
    return rtnval;
  }
  async _do_test(subscription_id) {
    let status = 0;
    try {
      const response = await fetch(
        build_subscription_test_url(subscription_id),
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify({})
        }
      );
      status = response.status;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.test_event_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        message: "Failed to reach the webhooks service."
      };
      return rtnval2;
    }
    const ok = status === 202 || status === 200;
    const rtnval = {
      ok,
      status,
      message: test_message_for_status(status)
    };
    return rtnval;
  }
  async _on_history(subscription, button) {
    await this._load_and_render_history(subscription);
    button.toggleAttribute("disabled", false);
    return;
  }
  /**
   * Fetch the delivery history for one subscription. Exposed so
   * unit tests can await the history fetch.
   *
   * @param subscription_id The subscription to read history for.
   *
   * @returns The delivery list (possibly empty).
   */
  async loadSubscriptionDeliveries(subscription_id) {
    let items = [];
    try {
      const url = build_subscription_deliveries_url(subscription_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const page = body;
        if (Array.isArray(page.items) === true) {
          items = page.items;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.out_deliveries_fetch_failed",
        { reason: String(reason) }
      );
    }
    const rtnval = items;
    return rtnval;
  }
  _render_outbound_history(subscription, deliveries) {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="outbound-history-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (subscription === null) {
      el.replaceChildren();
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-ops__subheading");
    heading.textContent = "Delivery History — " + subscription.name;
    if (deliveries.length === 0) {
      el.replaceChildren(
        heading,
        this._notice("No delivery attempts recorded")
      );
      return;
    }
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-ops__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.columns = [
      { key: "topic", label: "Topic", width: "16rem" },
      {
        key: "outcome",
        label: "Outcome",
        width: "10rem",
        render: (delivery) => self._badge(
          delivery.outcome,
          delivery_outcome_tone(delivery.outcome)
        )
      },
      {
        key: "response_status",
        label: "HTTP",
        width: "8rem",
        render: (delivery) => delivery.response_status === null || delivery.response_status === void 0 ? "—" : String(delivery.response_status)
      },
      {
        key: "attempted_at",
        label: "Attempted",
        width: "14rem",
        render: (delivery) => format_webhook_timestamp(delivery.attempted_at)
      }
    ];
    table.rows = deliveries;
    el.replaceChildren(heading, table);
    return;
  }
  _toggle_outbound_form(panel) {
    const region = panel.querySelector(
      '[data-role="outbound-form-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (el.hidden === true) {
      this._render_outbound_form(el);
      el.hidden = false;
    } else {
      el.hidden = true;
    }
    return;
  }
  _render_outbound_form(region) {
    const form = document.createElement("form");
    form.classList.add("pyc-ops__form");
    form.setAttribute("data-role", "outbound-form");
    const name_input = this._build_field(
      form,
      "Name",
      "outbound-name",
      "release-notifier"
    );
    const url_input = this._build_field(
      form,
      "Target URL",
      "outbound-url",
      "https://hooks.example/x"
    );
    const topics_input = this._build_field(
      form,
      "Topic filters (comma-separated)",
      "outbound-topics",
      "entity.release.published"
    );
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-ops__submit");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "outbound-submit");
    submit.textContent = "Create Subscription";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-ops__form-status");
    status.setAttribute("data-role", "outbound-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_outbound(
        name_input,
        url_input,
        topics_input,
        submit,
        status
      );
    });
    region.replaceChildren(form);
    return;
  }
  async _submit_outbound(name_input, url_input, topics_input, submit, status) {
    const name = name_input.value.trim();
    const url = url_input.value.trim();
    if (name.length === 0 || url.length === 0) {
      status.textContent = "Name and target URL are required.";
      return;
    }
    const topic_filters = parse_topic_filters(topics_input.value);
    submit.toggleAttribute("disabled", true);
    status.textContent = "Creating subscription…";
    const outcome = await this._do_create_subscription(
      name,
      url,
      topic_filters
    );
    submit.toggleAttribute("disabled", false);
    status.textContent = "";
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      if (typeof outcome.signingSecret === "string" && outcome.signingSecret.length > 0) {
        this._signingSecret = {
          name,
          secret: outcome.signingSecret
        };
      }
      await this.refreshOutbound();
      this._render_signing_secret();
    }
    return;
  }
  /**
   * Render (or hide) the one-time signing-secret panel from the
   * transient ``_signingSecret`` state. The secret is shown once
   * after creation and is never retrievable again -- dismissing
   * the panel drops it.
   */
  _render_signing_secret() {
    if (this._panel_region === null) {
      return;
    }
    const region = this._panel_region.querySelector(
      '[data-role="signing-secret-region"]'
    );
    if (region instanceof HTMLElement === false) {
      return;
    }
    const el = region;
    if (this._signingSecret === null) {
      el.replaceChildren();
      el.hidden = true;
      return;
    }
    const captured = this._signingSecret;
    const title = document.createElement("p");
    title.classList.add("pyc-ops__secret-title");
    title.textContent = "Signing secret for " + captured.name + " — save it now";
    const secret_code = document.createElement("code");
    secret_code.classList.add("pyc-ops__secret-value");
    secret_code.setAttribute("data-role", "signing-secret-value");
    secret_code.textContent = captured.secret;
    const copy_button = document.createElement("mj-button");
    copy_button.classList.add("pyc-ops__button", "pyc-ops__row-action");
    copy_button.setAttribute("type", "button");
    copy_button.setAttribute("data-role", "signing-secret-copy");
    copy_button.textContent = "Copy";
    copy_button.addEventListener("click", () => {
      if (typeof navigator !== "undefined" && navigator.clipboard !== void 0) {
        void navigator.clipboard.writeText(captured.secret);
        copy_button.textContent = "Copied";
      }
    });
    const dismiss_button = document.createElement("mj-button");
    dismiss_button.classList.add("pyc-ops__button", "pyc-ops__row-action");
    dismiss_button.setAttribute("type", "button");
    dismiss_button.setAttribute("data-role", "signing-secret-dismiss");
    dismiss_button.textContent = "Dismiss";
    dismiss_button.addEventListener("click", () => {
      this._signingSecret = null;
      this._render_signing_secret();
    });
    const note = document.createElement("p");
    note.classList.add("pyc-ops__note");
    note.textContent = "This secret is shown only once and cannot be retrieved later. Receivers verify deliveries by recomputing the X-Pychestrate-Signature header with it.";
    el.replaceChildren(title, secret_code, copy_button, dismiss_button, note);
    el.hidden = false;
    return;
  }
  /**
   * POST an outbound-subscription create request. Exposed so
   * unit tests can invoke a create without a real form-submit
   * event.
   *
   * @param name The subscription name.
   * @param url The target URL.
   * @param topic_filters The topic-filter list.
   *
   * @returns The create outcome. On success ``signingSecret``
   *          carries the one-time generated secret when the
   *          server returned one.
   */
  async createSubscription(name, url, topic_filters) {
    const rtnval = await this._do_create_subscription(
      name,
      url,
      topic_filters
    );
    return rtnval;
  }
  async _do_create_subscription(name, url, topic_filters) {
    if (this._projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        signingSecret: "",
        message: "Enter a project id before creating a subscription."
      };
      return rtnval2;
    }
    const payload = {
      project_id: this._projectId,
      name,
      url,
      topic_filters
    };
    let status = 0;
    let signing_secret = "";
    try {
      const response = await fetch(WEBHOOKS_OUT_PATH, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        const created = body;
        if (created !== null && typeof created.signing_secret === "string") {
          signing_secret = created.signing_secret;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.subscription_create_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        signingSecret: "",
        message: "Failed to reach the webhooks service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      signingSecret: signing_secret,
      message: create_message_for_status(status, "Subscription")
    };
    return rtnval;
  }
  // ----------------------------------------------------------------
  // Shared DOM helpers
  // ----------------------------------------------------------------
  /**
   * Build a labelled text input, append it to the supplied form,
   * and return the input element.
   *
   * @param form The form to append the field to.
   * @param label_text The visible field label.
   * @param role The ``data-role`` value for test selection.
   * @param placeholder The input placeholder text.
   *
   * @returns The created input element.
   */
  _build_field(form, label_text, role, placeholder) {
    const label = document.createElement("label");
    label.classList.add("pyc-ops__field");
    label.textContent = label_text;
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-ops__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", role);
    input.setAttribute("placeholder", placeholder);
    label.appendChild(input);
    form.appendChild(label);
    return input;
  }
  /**
   * Build a token-toned status badge span.
   *
   * @param text The badge label.
   * @param tone ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
   *
   * @returns The created badge span.
   */
  _badge(text, tone) {
    const badge = document.createElement("mj-chip");
    badge.classList.add("pyc-ops__badge");
    badge.setAttribute("data-tone", tone);
    badge.textContent = text;
    return badge;
  }
  /**
   * Build a notice paragraph for empty / placeholder states.
   *
   * @param text The notice text.
   *
   * @returns The created paragraph element.
   */
  _notice(text) {
    const notice = document.createElement("p");
    notice.classList.add("pyc-ops__notice");
    notice.textContent = text;
    return notice;
  }
  /**
   * Render a dismissible toast in the toast region. Toasts stack
   * (newest last) instead of replacing one another so an earlier
   * outcome is not silently destroyed; the stack is capped at
   * ``TOAST_STACK_LIMIT``.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-ops__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-ops__toast-dismiss");
    dismiss.setAttribute("type", "button");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "\xD7";
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
  PycWebhooks,
  TEST_EVENT_HISTORY_REFRESH_MS,
  TOAST_STACK_LIMIT,
  build_in_deliveries_url,
  build_integration_resource_url,
  build_integrations_collection_url,
  build_integrations_url,
  build_subscription_deliveries_url,
  build_subscription_resource_url,
  build_subscription_test_url,
  build_subscriptions_url,
  create_message_for_status,
  delivery_outcome_tone,
  format_webhook_timestamp,
  parse_topic_filters,
  problem_message_for_status,
  test_message_for_status,
  toggle_message_for_status
};
