/**
 * ``<pyc-webhooks>`` -- the webhooks management view Custom
 * Element.
 *
 * The view is tabbed:
 *
 * * **Inbound** -- a table of inbound webhook integrations
 *   (``GET /api/v1/webhooks/in/integrations?project_id=…``), a
 *   create form (POST the same path), and a recent-deliveries list
 *   (``GET /api/v1/webhooks/in/deliveries``).
 * * **Outbound** -- a table of outbound subscriptions
 *   (``GET /api/v1/webhooks/out/subscriptions?project_id=…``), a
 *   create form (POST the same path), a per-subscription delivery
 *   history (``…/subscriptions/{id}/deliveries``), and a
 *   "Send Test Event" action (``…/subscriptions/{id}/test``).
 *
 * Both inbound + outbound surfaces are project-scoped, so the view
 * renders a project-id input that drives the active project.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

/**
 * Base path of the inbound-webhooks REST surface.
 */
const WEBHOOKS_IN_PATH: string = "/api/v1/webhooks/in"

/**
 * Base path of the outbound-webhooks subscriptions REST surface.
 */
const WEBHOOKS_OUT_PATH: string = "/api/v1/webhooks/out/subscriptions"

/**
 * One inbound webhook integration.
 */
export interface WebhookInIntegration {
    webhook_id: string
    project_id: string
    provider: string
    hook_name: string
    secret_ref?: string | null
    mtls_required: boolean
    description?: string | null
    enabled: boolean
    created_by?: string | null
    created_at?: string | null
    receiver_path?: string | null
}

/**
 * One recorded inbound delivery (replay-cache ledger row).
 */
export interface WebhookInDelivery {
    provider: string
    hook_name: string
    delivery_id: string
    first_seen_at?: string | null
    expires_at?: string | null
}

/**
 * One outbound webhook subscription.
 */
export interface WebhookOutSubscription {
    subscription_id: string
    project_id: string
    name: string
    description?: string | null
    url: string
    signature_scheme: string
    topic_filters: string[]
    enabled: boolean
    custom_headers?: Record<string, string> | null
    created_by?: string | null
    created_at?: string | null
}

/**
 * One outbound delivery attempt.
 */
export interface WebhookOutDelivery {
    delivery_id: string
    subscription_id: string
    project_id: string
    topic: string
    outcome: string
    response_status?: number | null
    duration_ms?: number | null
    attempted_at?: string | null
}

/**
 * A generic ``{items, meta}`` page envelope.
 */
export interface WebhookPage<TItem> {
    items: TItem[]
    meta: {
        page: number
        per_page: number
        total: number
    }
}

/**
 * Outcome of a create / test mutation, surfaced to the caller.
 */
export interface WebhookOutcome {
    ok: boolean
    status: number
    message: string
}

/**
 * Build the ``…/webhooks/in/integrations`` query URL.
 *
 * @param project_id Owning project identifier.
 *
 * @returns A relative URL string.
 */
export function build_integrations_url(project_id: string): string {
    const params = new URLSearchParams()
    params.set("project_id", project_id)
    const rtnval = WEBHOOKS_IN_PATH + "/integrations?" + params.toString()
    return rtnval
}

/**
 * Build the ``…/webhooks/in/integrations`` collection URL (for a
 * create POST -- no query string).
 *
 * @returns A relative URL string.
 */
export function build_integrations_collection_url(): string {
    const rtnval = WEBHOOKS_IN_PATH + "/integrations"
    return rtnval
}

/**
 * Build the ``…/webhooks/in/deliveries`` query URL.
 *
 * @param provider Optional provider filter.
 *
 * @returns A relative URL string.
 */
export function build_in_deliveries_url(provider: string): string {
    let url = WEBHOOKS_IN_PATH + "/deliveries"
    if (typeof provider === "string" && provider.length > 0) {
        const params = new URLSearchParams()
        params.set("provider", provider)
        url = url + "?" + params.toString()
    }
    const rtnval = url
    return rtnval
}

/**
 * Build the ``…/webhooks/out/subscriptions`` query URL.
 *
 * @param project_id Owning project identifier.
 *
 * @returns A relative URL string.
 */
export function build_subscriptions_url(project_id: string): string {
    const params = new URLSearchParams()
    params.set("project_id", project_id)
    const rtnval = WEBHOOKS_OUT_PATH + "?" + params.toString()
    return rtnval
}

/**
 * Build the ``…/webhooks/out/subscriptions/{id}/deliveries`` URL.
 *
 * @param subscription_id The subscription identifier.
 *
 * @returns A relative URL string.
 */
export function build_subscription_deliveries_url(
    subscription_id: string,
): string {
    const rtnval = WEBHOOKS_OUT_PATH + "/" +
        encodeURIComponent(subscription_id) + "/deliveries"
    return rtnval
}

/**
 * Build the ``…/webhooks/out/subscriptions/{id}/test`` URL.
 *
 * @param subscription_id The subscription identifier.
 *
 * @returns A relative URL string.
 */
export function build_subscription_test_url(
    subscription_id: string,
): string {
    const rtnval = WEBHOOKS_OUT_PATH + "/" +
        encodeURIComponent(subscription_id) + "/test"
    return rtnval
}

/**
 * Format an ISO-8601 timestamp for table display. Returns an
 * em-dash placeholder for null/undefined/empty values.
 *
 * @param value ISO-8601 timestamp or null.
 *
 * @returns A locale-formatted timestamp or ``"—"``.
 */
export function format_webhook_timestamp(
    value: string | null | undefined,
): string {
    if (value === null || value === undefined || value.length === 0) {
        const rtnval = "—"
        return rtnval
    }
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime()) === true) {
        const rtnval = value
        return rtnval
    }
    const rtnval = parsed.toLocaleString()
    return rtnval
}

/**
 * Classify an outbound-delivery outcome into a coarse badge tone.
 *
 * @param outcome The delivery outcome string.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function delivery_outcome_tone(outcome: string): string {
    if (typeof outcome !== "string") {
        const rtnval = "neutral"
        return rtnval
    }
    const lowered = outcome.toLowerCase()
    if (lowered === "delivered" || lowered === "success") {
        const rtnval = "ok"
        return rtnval
    }
    if (lowered === "pending" || lowered === "retrying") {
        const rtnval = "warn"
        return rtnval
    }
    if (lowered === "failed" || lowered === "error") {
        const rtnval = "error"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Translate a create-mutation HTTP status into operator guidance.
 *
 * @param status HTTP status code of the create response.
 * @param subject A short noun describing the created entity.
 *
 * @returns A human-readable message.
 */
export function create_message_for_status(
    status: number,
    subject: string,
): string {
    if (status === 201 || status === 200) {
        const rtnval = subject + " created."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "A " + subject.toLowerCase() +
            " with those identifiers already exists."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "The " + subject.toLowerCase() +
            " request was rejected — check the fields."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to create a " +
            subject.toLowerCase() + "."
        return rtnval
    }
    const rtnval = "Failed to create " + subject.toLowerCase() +
        " (HTTP " + String(status) + ")."
    return rtnval
}

/**
 * Translate a send-test-event HTTP status into operator guidance.
 *
 * @param status HTTP status code of the test response.
 *
 * @returns A human-readable message.
 */
export function test_message_for_status(status: number): string {
    if (status === 202 || status === 200) {
        const rtnval = "Test event queued."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "Cannot send a test event for a disabled subscription."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown subscription."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to send test events."
        return rtnval
    }
    const rtnval = "Failed to send test event (HTTP " +
        String(status) + ")."
    return rtnval
}

/**
 * Parse the topic-filters input -- a comma-separated list -- into
 * a trimmed string array.
 *
 * @param raw Raw comma-separated input.
 *
 * @returns A list of topic-filter strings (possibly empty).
 */
export function parse_topic_filters(raw: string): string[] {
    if (typeof raw !== "string" || raw.trim().length === 0) {
        const rtnval: string[] = []
        return rtnval
    }
    const pieces = raw.split(",")
    const rtnval: string[] = []
    for (const piece of pieces) {
        const trimmed = piece.trim()
        if (trimmed.length > 0) {
            rtnval.push(trimmed)
        }
    }
    return rtnval
}

/**
 * The webhooks management view Custom Element. Register it with
 * ``customElements.define("pyc-webhooks", PycWebhooks)``.
 */
export class PycWebhooks extends HTMLElement {
    private _projectId: string
    private _activeTab: string
    private _integrations: WebhookInIntegration[]
    private _inDeliveries: WebhookInDelivery[]
    private _subscriptions: WebhookOutSubscription[]
    private _root: HTMLElement | null
    private _panel_region: HTMLElement | null
    private _toast_region: HTMLElement | null

    public constructor() {
        super()
        this._projectId = ""
        this._activeTab = "inbound"
        this._integrations = []
        this._inDeliveries = []
        this._subscriptions = []
        this._root = null
        this._panel_region = null
        this._toast_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to read the active
     * tab without scraping the DOM.
     */
    public get activeTab(): string {
        const rtnval = this._activeTab
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to read the active
     * project id.
     */
    public get projectId(): string {
        const rtnval = this._projectId
        return rtnval
    }

    /**
     * Lifecycle hook -- render the static chrome when inserted.
     */
    public connectedCallback(): void {
        this._render_chrome()
        return
    }

    /**
     * Build the persistent chrome -- heading, project input, tab
     * strip, panel region, toast region.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-ops")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-ops__heading")
        heading.textContent = "Webhooks"
        root.appendChild(heading)

        const controls = document.createElement("div")
        controls.classList.add("pyc-ops__controls")

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-ops__field")
        project_label.textContent = "Project"
        const project_input = document.createElement("input")
        project_input.classList.add("pyc-ops__input")
        project_input.setAttribute("type", "text")
        project_input.setAttribute("placeholder", "project id")
        project_input.setAttribute("data-role", "project-input")
        project_input.addEventListener("change", () => {
            this._projectId = project_input.value.trim()
            void this._refresh_active_tab()
        })
        project_label.appendChild(project_input)
        controls.appendChild(project_label)

        root.appendChild(controls)

        const tabs = document.createElement("div")
        tabs.classList.add("pyc-ops__tabs")
        tabs.setAttribute("role", "tablist")

        const inbound_tab = this._build_tab_button("inbound", "Inbound")
        const outbound_tab = this._build_tab_button("outbound", "Outbound")
        tabs.appendChild(inbound_tab)
        tabs.appendChild(outbound_tab)
        root.appendChild(tabs)

        const toast_region = document.createElement("div")
        toast_region.classList.add("pyc-ops__toast-region")
        toast_region.setAttribute("data-role", "toast-region")
        root.appendChild(toast_region)
        this._toast_region = toast_region

        const panel_region = document.createElement("div")
        panel_region.classList.add("pyc-ops__panel-region")
        panel_region.setAttribute("data-role", "panel-region")
        root.appendChild(panel_region)
        this._panel_region = panel_region

        this._root = root
        this.replaceChildren(root)
        this._render_active_tab()
        return
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
    private _build_tab_button(
        tab_id: string,
        label: string,
    ): HTMLButtonElement {
        const button = document.createElement("button")
        button.classList.add("pyc-ops__tab")
        button.setAttribute("type", "button")
        button.setAttribute("role", "tab")
        button.setAttribute("data-role", "tab-" + tab_id)
        button.setAttribute(
            "aria-selected",
            this._activeTab === tab_id ? "true" : "false",
        )
        button.textContent = label
        button.addEventListener("click", () => {
            this.selectTab(tab_id)
        })
        return button
    }

    /**
     * Switch the active tab and re-render the panel. Exposed so
     * unit tests can drive tab selection.
     *
     * @param tab_id The tab to activate.
     */
    public selectTab(tab_id: string): void {
        if (tab_id !== "inbound" && tab_id !== "outbound") {
            return
        }
        this._activeTab = tab_id
        if (this._root !== null) {
            const inbound = this._root.querySelector('[data-role="tab-inbound"]')
            const outbound = this._root.querySelector(
                '[data-role="tab-outbound"]',
            )
            if (inbound instanceof HTMLElement) {
                inbound.setAttribute(
                    "aria-selected",
                    tab_id === "inbound" ? "true" : "false",
                )
            }
            if (outbound instanceof HTMLElement) {
                outbound.setAttribute(
                    "aria-selected",
                    tab_id === "outbound" ? "true" : "false",
                )
            }
        }
        this._render_active_tab()
        void this._refresh_active_tab()
        return
    }

    /**
     * Render the static panel scaffolding for the active tab.
     */
    private _render_active_tab(): void {
        if (this._panel_region === null) {
            return
        }
        if (this._activeTab === "inbound") {
            this._render_inbound_panel()
        } else {
            this._render_outbound_panel()
        }
        return
    }

    /**
     * Re-fetch the data for whichever tab is currently active.
     */
    private async _refresh_active_tab(): Promise<void> {
        if (this._activeTab === "inbound") {
            await this.refreshInbound()
        } else {
            await this.refreshOutbound()
        }
        return
    }

    // ----------------------------------------------------------------
    // Inbound tab
    // ----------------------------------------------------------------

    /**
     * Render the inbound-panel scaffolding -- create-form toggle,
     * integrations table region, recent-deliveries region.
     */
    private _render_inbound_panel(): void {
        if (this._panel_region === null) {
            return
        }
        const panel = document.createElement("div")
        panel.classList.add("pyc-ops__panel")
        panel.setAttribute("data-role", "inbound-panel")

        const create_button = document.createElement("button")
        create_button.classList.add("pyc-ops__button")
        create_button.setAttribute("type", "button")
        create_button.setAttribute("data-role", "inbound-create-toggle")
        create_button.textContent = "Create Integration"
        create_button.addEventListener("click", () => {
            this._toggle_inbound_form(panel)
        })
        panel.appendChild(create_button)

        const form_region = document.createElement("div")
        form_region.classList.add("pyc-ops__form-region")
        form_region.setAttribute("data-role", "inbound-form-region")
        form_region.hidden = true
        panel.appendChild(form_region)

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-ops__table-region")
        table_region.setAttribute("data-role", "inbound-table-region")
        panel.appendChild(table_region)

        const deliveries_heading = document.createElement("h2")
        deliveries_heading.classList.add("pyc-ops__subheading")
        deliveries_heading.textContent = "Recent Deliveries"
        panel.appendChild(deliveries_heading)

        const deliveries_region = document.createElement("div")
        deliveries_region.classList.add("pyc-ops__table-region")
        deliveries_region.setAttribute(
            "data-role", "inbound-deliveries-region",
        )
        panel.appendChild(deliveries_region)

        this._panel_region.replaceChildren(panel)
        this._render_inbound_table()
        this._render_inbound_deliveries()
        return
    }

    /**
     * Fetch the inbound integrations + recent deliveries and
     * re-render. Exposed so unit tests can await a fetch cycle.
     */
    public async refreshInbound(): Promise<void> {
        if (this._projectId.length === 0) {
            this._integrations = []
            this._inDeliveries = []
            this._render_inbound_table()
            this._render_inbound_deliveries()
            return
        }
        await this._load_integrations()
        await this._load_inbound_deliveries()
        return
    }

    private async _load_integrations(): Promise<void> {
        let items: WebhookInIntegration[] | null = null
        try {
            const url = build_integrations_url(this._projectId)
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                const page = body as WebhookPage<WebhookInIntegration>
                if (Array.isArray(page.items) === true) {
                    items = page.items
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.integrations_fetch_failed",
                { reason: String(reason) },
            )
        }
        this._integrations = items ?? []
        this._render_inbound_table()
        return
    }

    private async _load_inbound_deliveries(): Promise<void> {
        let items: WebhookInDelivery[] | null = null
        try {
            const url = build_in_deliveries_url("")
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                const page = body as WebhookPage<WebhookInDelivery>
                if (Array.isArray(page.items) === true) {
                    items = page.items
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.in_deliveries_fetch_failed",
                { reason: String(reason) },
            )
        }
        this._inDeliveries = items ?? []
        this._render_inbound_deliveries()
        return
    }

    private _render_inbound_table(): void {
        if (this._panel_region === null) {
            return
        }
        const region = this._panel_region.querySelector(
            '[data-role="inbound-table-region"]',
        )
        if (region instanceof HTMLElement === false) {
            return
        }
        const el = region as HTMLElement
        if (this._projectId.length === 0) {
            el.replaceChildren(
                this._notice("Enter a project id to view integrations."),
            )
            return
        }
        if (this._integrations.length === 0) {
            el.replaceChildren(
                this._notice("No inbound integrations for this project yet"),
            )
            return
        }
        const table = document.createElement("table")
        table.classList.add("pyc-ops__table")
        const columns = ["Provider", "Hook", "Receiver path", "State"]
        table.appendChild(this._table_head(columns))
        const tbody = document.createElement("tbody")
        for (const integration of this._integrations) {
            const row = document.createElement("tr")
            this._append_text_cell(row, integration.provider)
            this._append_text_cell(row, integration.hook_name)
            this._append_text_cell(row, integration.receiver_path ?? "—")
            const state_cell = document.createElement("td")
            state_cell.appendChild(
                this._badge(
                    integration.enabled === true ? "enabled" : "disabled",
                    integration.enabled === true ? "ok" : "neutral",
                ),
            )
            row.appendChild(state_cell)
            tbody.appendChild(row)
        }
        table.appendChild(tbody)
        el.replaceChildren(table)
        return
    }

    private _render_inbound_deliveries(): void {
        if (this._panel_region === null) {
            return
        }
        const region = this._panel_region.querySelector(
            '[data-role="inbound-deliveries-region"]',
        )
        if (region instanceof HTMLElement === false) {
            return
        }
        const el = region as HTMLElement
        if (this._inDeliveries.length === 0) {
            el.replaceChildren(this._notice("No recent inbound deliveries"))
            return
        }
        const table = document.createElement("table")
        table.classList.add("pyc-ops__table")
        const columns = ["Provider", "Hook", "Delivery id", "First seen"]
        table.appendChild(this._table_head(columns))
        const tbody = document.createElement("tbody")
        for (const delivery of this._inDeliveries) {
            const row = document.createElement("tr")
            this._append_text_cell(row, delivery.provider)
            this._append_text_cell(row, delivery.hook_name)
            this._append_text_cell(row, delivery.delivery_id)
            this._append_text_cell(
                row, format_webhook_timestamp(delivery.first_seen_at),
            )
            tbody.appendChild(row)
        }
        table.appendChild(tbody)
        el.replaceChildren(table)
        return
    }

    private _toggle_inbound_form(panel: HTMLElement): void {
        const region = panel.querySelector(
            '[data-role="inbound-form-region"]',
        )
        if (region instanceof HTMLElement === false) {
            return
        }
        const el = region as HTMLElement
        if (el.hidden === true) {
            this._render_inbound_form(el)
            el.hidden = false
        } else {
            el.hidden = true
        }
        return
    }

    private _render_inbound_form(region: HTMLElement): void {
        const form = document.createElement("form")
        form.classList.add("pyc-ops__form")
        form.setAttribute("data-role", "inbound-form")

        const provider_input = this._build_field(
            form, "Provider", "inbound-provider", "github",
        )
        const hook_input = this._build_field(
            form, "Hook name", "inbound-hook", "push",
        )
        const secret_input = this._build_field(
            form, "Secret ref", "inbound-secret", "secret://hooks/github",
        )

        const submit = document.createElement("button")
        submit.classList.add("pyc-ops__submit")
        submit.setAttribute("type", "submit")
        submit.setAttribute("data-role", "inbound-submit")
        submit.textContent = "Create Integration"
        form.appendChild(submit)

        const status = document.createElement("p")
        status.classList.add("pyc-ops__form-status")
        status.setAttribute("data-role", "inbound-status")
        form.appendChild(status)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_inbound(
                provider_input, hook_input, secret_input, submit, status,
            )
        })
        region.replaceChildren(form)
        return
    }

    private async _submit_inbound(
        provider_input: HTMLInputElement,
        hook_input: HTMLInputElement,
        secret_input: HTMLInputElement,
        submit: HTMLButtonElement,
        status: HTMLElement,
    ): Promise<void> {
        const provider = provider_input.value.trim()
        const hook_name = hook_input.value.trim()
        const secret_ref = secret_input.value.trim()
        if (
            provider.length === 0 ||
            hook_name.length === 0 ||
            secret_ref.length === 0
        ) {
            status.textContent =
                "Provider, hook name and secret ref are required."
            return
        }
        submit.disabled = true
        status.textContent = "Creating integration…"
        const outcome = await this._do_create_integration(
            provider, hook_name, secret_ref,
        )
        submit.disabled = false
        status.textContent = ""
        this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error")
        if (outcome.ok === true) {
            await this.refreshInbound()
        }
        return
    }

    /**
     * POST an inbound-integration create request. Exposed so unit
     * tests can invoke a create without a real form-submit event.
     *
     * @param provider The webhook provider name.
     * @param hook_name The hook name.
     * @param secret_ref The signing-secret reference.
     *
     * @returns The create outcome.
     */
    public async createIntegration(
        provider: string,
        hook_name: string,
        secret_ref: string,
    ): Promise<WebhookOutcome> {
        const rtnval = await this._do_create_integration(
            provider, hook_name, secret_ref,
        )
        return rtnval
    }

    private async _do_create_integration(
        provider: string,
        hook_name: string,
        secret_ref: string,
    ): Promise<WebhookOutcome> {
        if (this._projectId.length === 0) {
            const rtnval: WebhookOutcome = {
                ok: false,
                status: 0,
                message: "Enter a project id before creating an integration.",
            }
            return rtnval
        }
        const payload: Record<string, unknown> = {
            project_id: this._projectId,
            provider: provider,
            hook_name: hook_name,
            secret_ref: secret_ref,
        }
        let status = 0
        try {
            const response = await fetch(
                build_integrations_collection_url(),
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        Accept: "application/json",
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify(payload),
                },
            )
            status = response.status
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.integration_create_failed",
                { reason: String(reason) },
            )
            const rtnval: WebhookOutcome = {
                ok: false,
                status: 0,
                message: "Failed to reach the webhooks service.",
            }
            return rtnval
        }
        const ok = status === 201 || status === 200
        const rtnval: WebhookOutcome = {
            ok: ok,
            status: status,
            message: create_message_for_status(status, "Integration"),
        }
        return rtnval
    }

    // ----------------------------------------------------------------
    // Outbound tab
    // ----------------------------------------------------------------

    /**
     * Render the outbound-panel scaffolding -- create-form toggle,
     * subscriptions table region.
     */
    private _render_outbound_panel(): void {
        if (this._panel_region === null) {
            return
        }
        const panel = document.createElement("div")
        panel.classList.add("pyc-ops__panel")
        panel.setAttribute("data-role", "outbound-panel")

        const create_button = document.createElement("button")
        create_button.classList.add("pyc-ops__button")
        create_button.setAttribute("type", "button")
        create_button.setAttribute("data-role", "outbound-create-toggle")
        create_button.textContent = "Create Subscription"
        create_button.addEventListener("click", () => {
            this._toggle_outbound_form(panel)
        })
        panel.appendChild(create_button)

        const form_region = document.createElement("div")
        form_region.classList.add("pyc-ops__form-region")
        form_region.setAttribute("data-role", "outbound-form-region")
        form_region.hidden = true
        panel.appendChild(form_region)

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-ops__table-region")
        table_region.setAttribute("data-role", "outbound-table-region")
        panel.appendChild(table_region)

        const history_region = document.createElement("div")
        history_region.classList.add("pyc-ops__table-region")
        history_region.setAttribute("data-role", "outbound-history-region")
        panel.appendChild(history_region)

        this._panel_region.replaceChildren(panel)
        this._render_outbound_table()
        return
    }

    /**
     * Fetch the outbound subscriptions and re-render. Exposed so
     * unit tests can await a fetch cycle.
     */
    public async refreshOutbound(): Promise<void> {
        if (this._projectId.length === 0) {
            this._subscriptions = []
            this._render_outbound_table()
            return
        }
        let items: WebhookOutSubscription[] | null = null
        try {
            const url = build_subscriptions_url(this._projectId)
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                const page = body as WebhookPage<WebhookOutSubscription>
                if (Array.isArray(page.items) === true) {
                    items = page.items
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.subscriptions_fetch_failed",
                { reason: String(reason) },
            )
        }
        this._subscriptions = items ?? []
        this._render_outbound_table()
        return
    }

    private _render_outbound_table(): void {
        if (this._panel_region === null) {
            return
        }
        const region = this._panel_region.querySelector(
            '[data-role="outbound-table-region"]',
        )
        if (region instanceof HTMLElement === false) {
            return
        }
        const el = region as HTMLElement
        if (this._projectId.length === 0) {
            el.replaceChildren(
                this._notice("Enter a project id to view subscriptions."),
            )
            return
        }
        if (this._subscriptions.length === 0) {
            el.replaceChildren(
                this._notice("No outbound subscriptions for this project yet"),
            )
            return
        }
        const table = document.createElement("table")
        table.classList.add("pyc-ops__table")
        const columns = ["Name", "URL", "Topics", "State", "Actions"]
        table.appendChild(this._table_head(columns))
        const tbody = document.createElement("tbody")
        for (const subscription of this._subscriptions) {
            tbody.appendChild(this._build_subscription_row(subscription))
        }
        table.appendChild(tbody)
        el.replaceChildren(table)
        return
    }

    private _build_subscription_row(
        subscription: WebhookOutSubscription,
    ): HTMLTableRowElement {
        const row = document.createElement("tr")
        row.setAttribute("data-subscription-id", subscription.subscription_id)
        this._append_text_cell(row, subscription.name)
        this._append_text_cell(row, subscription.url)
        this._append_text_cell(
            row, subscription.topic_filters.join(", ") || "all",
        )
        const state_cell = document.createElement("td")
        state_cell.appendChild(
            this._badge(
                subscription.enabled === true ? "enabled" : "disabled",
                subscription.enabled === true ? "ok" : "neutral",
            ),
        )
        row.appendChild(state_cell)

        const actions_cell = document.createElement("td")
        const test_button = document.createElement("button")
        test_button.classList.add("pyc-ops__button", "pyc-ops__row-action")
        test_button.setAttribute("type", "button")
        test_button.setAttribute("data-role", "test-event")
        test_button.textContent = "Send Test Event"
        test_button.addEventListener("click", () => {
            test_button.disabled = true
            void this._on_test(subscription, test_button)
        })
        actions_cell.appendChild(test_button)

        const history_button = document.createElement("button")
        history_button.classList.add(
            "pyc-ops__button", "pyc-ops__row-action",
        )
        history_button.setAttribute("type", "button")
        history_button.setAttribute("data-role", "delivery-history")
        history_button.textContent = "Delivery History"
        history_button.addEventListener("click", () => {
            history_button.disabled = true
            void this._on_history(subscription, history_button)
        })
        actions_cell.appendChild(history_button)
        row.appendChild(actions_cell)
        return row
    }

    private async _on_test(
        subscription: WebhookOutSubscription,
        button: HTMLButtonElement,
    ): Promise<void> {
        const outcome = await this._do_test(subscription.subscription_id)
        button.disabled = false
        this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error")
        return
    }

    /**
     * POST a test event for one subscription. Exposed so unit
     * tests can drive a test without a row button.
     *
     * @param subscription_id The subscription to test.
     *
     * @returns The test outcome.
     */
    public async sendTestEvent(
        subscription_id: string,
    ): Promise<WebhookOutcome> {
        const rtnval = await this._do_test(subscription_id)
        return rtnval
    }

    private async _do_test(
        subscription_id: string,
    ): Promise<WebhookOutcome> {
        let status = 0
        try {
            const response = await fetch(
                build_subscription_test_url(subscription_id),
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        Accept: "application/json",
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({}),
                },
            )
            status = response.status
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.test_event_failed",
                { reason: String(reason) },
            )
            const rtnval: WebhookOutcome = {
                ok: false,
                status: 0,
                message: "Failed to reach the webhooks service.",
            }
            return rtnval
        }
        const ok = status === 202 || status === 200
        const rtnval: WebhookOutcome = {
            ok: ok,
            status: status,
            message: test_message_for_status(status),
        }
        return rtnval
    }

    private async _on_history(
        subscription: WebhookOutSubscription,
        button: HTMLButtonElement,
    ): Promise<void> {
        const deliveries = await this.loadSubscriptionDeliveries(
            subscription.subscription_id,
        )
        button.disabled = false
        this._render_outbound_history(subscription, deliveries)
        return
    }

    /**
     * Fetch the delivery history for one subscription. Exposed so
     * unit tests can await the history fetch.
     *
     * @param subscription_id The subscription to read history for.
     *
     * @returns The delivery list (possibly empty).
     */
    public async loadSubscriptionDeliveries(
        subscription_id: string,
    ): Promise<WebhookOutDelivery[]> {
        let items: WebhookOutDelivery[] = []
        try {
            const url = build_subscription_deliveries_url(subscription_id)
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                const page = body as WebhookPage<WebhookOutDelivery>
                if (Array.isArray(page.items) === true) {
                    items = page.items
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.out_deliveries_fetch_failed",
                { reason: String(reason) },
            )
        }
        const rtnval = items
        return rtnval
    }

    private _render_outbound_history(
        subscription: WebhookOutSubscription,
        deliveries: WebhookOutDelivery[],
    ): void {
        if (this._panel_region === null) {
            return
        }
        const region = this._panel_region.querySelector(
            '[data-role="outbound-history-region"]',
        )
        if (region instanceof HTMLElement === false) {
            return
        }
        const el = region as HTMLElement

        const heading = document.createElement("h2")
        heading.classList.add("pyc-ops__subheading")
        heading.textContent = "Delivery History — " + subscription.name

        if (deliveries.length === 0) {
            el.replaceChildren(
                heading,
                this._notice("No delivery attempts recorded"),
            )
            return
        }
        const table = document.createElement("table")
        table.classList.add("pyc-ops__table")
        const columns = ["Topic", "Outcome", "HTTP", "Attempted"]
        table.appendChild(this._table_head(columns))
        const tbody = document.createElement("tbody")
        for (const delivery of deliveries) {
            const row = document.createElement("tr")
            this._append_text_cell(row, delivery.topic)
            const outcome_cell = document.createElement("td")
            outcome_cell.appendChild(
                this._badge(
                    delivery.outcome,
                    delivery_outcome_tone(delivery.outcome),
                ),
            )
            row.appendChild(outcome_cell)
            const http_value = delivery.response_status === null ||
                delivery.response_status === undefined
                ? "—"
                : String(delivery.response_status)
            this._append_text_cell(row, http_value)
            this._append_text_cell(
                row, format_webhook_timestamp(delivery.attempted_at),
            )
            tbody.appendChild(row)
        }
        table.appendChild(tbody)
        el.replaceChildren(heading, table)
        return
    }

    private _toggle_outbound_form(panel: HTMLElement): void {
        const region = panel.querySelector(
            '[data-role="outbound-form-region"]',
        )
        if (region instanceof HTMLElement === false) {
            return
        }
        const el = region as HTMLElement
        if (el.hidden === true) {
            this._render_outbound_form(el)
            el.hidden = false
        } else {
            el.hidden = true
        }
        return
    }

    private _render_outbound_form(region: HTMLElement): void {
        const form = document.createElement("form")
        form.classList.add("pyc-ops__form")
        form.setAttribute("data-role", "outbound-form")

        const name_input = this._build_field(
            form, "Name", "outbound-name", "release-notifier",
        )
        const url_input = this._build_field(
            form, "Target URL", "outbound-url", "https://hooks.example/x",
        )
        const topics_input = this._build_field(
            form, "Topic filters (comma-separated)", "outbound-topics",
            "entity.release.published",
        )

        const submit = document.createElement("button")
        submit.classList.add("pyc-ops__submit")
        submit.setAttribute("type", "submit")
        submit.setAttribute("data-role", "outbound-submit")
        submit.textContent = "Create Subscription"
        form.appendChild(submit)

        const status = document.createElement("p")
        status.classList.add("pyc-ops__form-status")
        status.setAttribute("data-role", "outbound-status")
        form.appendChild(status)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_outbound(
                name_input, url_input, topics_input, submit, status,
            )
        })
        region.replaceChildren(form)
        return
    }

    private async _submit_outbound(
        name_input: HTMLInputElement,
        url_input: HTMLInputElement,
        topics_input: HTMLInputElement,
        submit: HTMLButtonElement,
        status: HTMLElement,
    ): Promise<void> {
        const name = name_input.value.trim()
        const url = url_input.value.trim()
        if (name.length === 0 || url.length === 0) {
            status.textContent = "Name and target URL are required."
            return
        }
        const topic_filters = parse_topic_filters(topics_input.value)
        submit.disabled = true
        status.textContent = "Creating subscription…"
        const outcome = await this._do_create_subscription(
            name, url, topic_filters,
        )
        submit.disabled = false
        status.textContent = ""
        this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error")
        if (outcome.ok === true) {
            await this.refreshOutbound()
        }
        return
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
     * @returns The create outcome.
     */
    public async createSubscription(
        name: string,
        url: string,
        topic_filters: string[],
    ): Promise<WebhookOutcome> {
        const rtnval = await this._do_create_subscription(
            name, url, topic_filters,
        )
        return rtnval
    }

    private async _do_create_subscription(
        name: string,
        url: string,
        topic_filters: string[],
    ): Promise<WebhookOutcome> {
        if (this._projectId.length === 0) {
            const rtnval: WebhookOutcome = {
                ok: false,
                status: 0,
                message: "Enter a project id before creating a subscription.",
            }
            return rtnval
        }
        const payload: Record<string, unknown> = {
            project_id: this._projectId,
            name: name,
            url: url,
            topic_filters: topic_filters,
        }
        let status = 0
        try {
            const response = await fetch(WEBHOOKS_OUT_PATH, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            })
            status = response.status
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.subscription_create_failed",
                { reason: String(reason) },
            )
            const rtnval: WebhookOutcome = {
                ok: false,
                status: 0,
                message: "Failed to reach the webhooks service.",
            }
            return rtnval
        }
        const ok = status === 201 || status === 200
        const rtnval: WebhookOutcome = {
            ok: ok,
            status: status,
            message: create_message_for_status(status, "Subscription"),
        }
        return rtnval
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
    private _build_field(
        form: HTMLFormElement,
        label_text: string,
        role: string,
        placeholder: string,
    ): HTMLInputElement {
        const label = document.createElement("label")
        label.classList.add("pyc-ops__field")
        label.textContent = label_text
        const input = document.createElement("input")
        input.classList.add("pyc-ops__input")
        input.setAttribute("type", "text")
        input.setAttribute("data-role", role)
        input.setAttribute("placeholder", placeholder)
        label.appendChild(input)
        form.appendChild(label)
        return input
    }

    /**
     * Build a ``<thead>`` from a list of column labels.
     *
     * @param columns The column header labels.
     *
     * @returns A populated ``<thead>``.
     */
    private _table_head(columns: string[]): HTMLTableSectionElement {
        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        for (const column of columns) {
            const th = document.createElement("th")
            th.scope = "col"
            th.textContent = column
            head_row.appendChild(th)
        }
        thead.appendChild(head_row)
        return thead
    }

    /**
     * Append a plain-text ``<td>`` to a table row.
     *
     * @param row The row to append the cell to.
     * @param text The cell text content.
     */
    private _append_text_cell(row: HTMLTableRowElement, text: string): void {
        const cell = document.createElement("td")
        cell.textContent = text
        row.appendChild(cell)
        return
    }

    /**
     * Build a token-toned status badge span.
     *
     * @param text The badge label.
     * @param tone ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
     *
     * @returns The created badge span.
     */
    private _badge(text: string, tone: string): HTMLSpanElement {
        const badge = document.createElement("span")
        badge.classList.add("pyc-ops__badge")
        badge.setAttribute("data-tone", tone)
        badge.textContent = text
        return badge
    }

    /**
     * Build a notice paragraph for empty / placeholder states.
     *
     * @param text The notice text.
     *
     * @returns The created paragraph element.
     */
    private _notice(text: string): HTMLParagraphElement {
        const notice = document.createElement("p")
        notice.classList.add("pyc-ops__notice")
        notice.textContent = text
        return notice
    }

    /**
     * Render a dismissible toast in the toast region.
     *
     * @param message The toast message text.
     * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
     */
    private _show_toast(message: string, tone: string): void {
        if (this._toast_region === null) {
            return
        }
        const toast = document.createElement("div")
        toast.classList.add("pyc-ops__toast")
        toast.setAttribute("data-role", "toast")
        toast.setAttribute("data-tone", tone)

        const text = document.createElement("span")
        text.textContent = message
        toast.appendChild(text)

        const dismiss = document.createElement("button")
        dismiss.classList.add("pyc-ops__toast-dismiss")
        dismiss.setAttribute("type", "button")
        dismiss.setAttribute("aria-label", "Dismiss")
        dismiss.textContent = "×"
        dismiss.addEventListener("click", () => {
            toast.remove()
        })
        toast.appendChild(dismiss)

        this._toast_region.replaceChildren(toast)
        return
    }
}
