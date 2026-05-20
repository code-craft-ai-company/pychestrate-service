/**
 * ``<pyc-secrets>`` -- the scope-aware secrets management view
 * Custom Element.
 *
 * On mount the element renders a scope selector (Org / Project /
 * User), a "Create Secret" form, and -- per the active scope -- a
 * table of secret METADATA fetched from ``GET /api/v1/secrets``.
 * The list NEVER carries or renders plaintext values; values are
 * fetched on demand, one secret at a time, via the dedicated
 * value-read endpoint and held only in transient component state.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 *
 * Security invariants this view upholds:
 *
 * * A revealed plaintext value lives ONLY in the per-row transient
 *   ``_revealed`` map; it is never written to ``localStorage`` /
 *   ``sessionStorage``, never logged, and is cleared on collapse
 *   and on ``disconnectedCallback`` (navigation away).
 * * The list + metadata renders never request the value field.
 * * A 403 on a value reveal renders a clear "no access" message
 *   rather than crashing.
 */

/**
 * The ``SecretScopeKind`` enum from
 * ``specs/openapi/pychestrate.yaml``. ``ORG`` is service-wide;
 * ``PROJECT`` is bound to a project_id; ``USER`` is a personal
 * secret bound to a user_id.
 */
export const SECRET_SCOPE_KINDS: readonly string[] = [
    "ORG",
    "PROJECT",
    "USER",
]

/**
 * One secret's metadata, as returned by ``GET /api/v1/secrets``
 * and the single-secret metadata endpoint. NEVER carries the
 * plaintext value.
 */
export interface Secret {
    secret_ref: string
    backend_name: string
    scope_kind: string
    scope_ref?: string | null
    current_version_id?: string | null
    created_at: string
    updated_at: string
}

/**
 * The ``SecretValue`` response shape returned ONLY by the
 * value-read endpoint.
 */
export interface SecretValue {
    secret_ref: string
    version_number: number
    value: string
}

/**
 * The current scope + load state of the secrets view. Exposed so
 * unit tests can assert state transitions without scraping the
 * DOM.
 */
export interface SecretsViewState {
    scopeKind: string
    scopeRef: string
    loading: boolean
    errored: boolean
}

/**
 * Base path of the secrets REST collection.
 */
const SECRETS_API_PATH: string = "/api/v1/secrets"

/**
 * Build the ``GET /api/v1/secrets`` query URL for the supplied
 * scope. ``ORG`` scope omits ``scope_ref``; ``PROJECT`` / ``USER``
 * include it when one is selected.
 *
 * @param scope_kind One of the ``SecretScopeKind`` enum values.
 * @param scope_ref The project_id / user_id for scoped listings.
 *
 * @returns A relative URL string including the query string.
 */
export function build_secrets_list_url(
        scope_kind: string,
        scope_ref: string,
    ): string {
    const params = new URLSearchParams()
    if (scope_kind.length > 0) {
        params.set("scope_kind", scope_kind)
    }
    if (scope_kind !== "ORG" && scope_ref.length > 0) {
        params.set("scope_ref", scope_ref)
    }
    const query = params.toString()
    let rtnval = SECRETS_API_PATH
    if (query.length > 0) {
        rtnval = SECRETS_API_PATH + "?" + query
    }
    return rtnval
}

/**
 * Build the value-read URL for a single secret. The secret_ref is
 * slash-delimited and is URL-path-encoded segment by segment so a
 * ref like ``vault/myteam/api-token`` survives transport.
 *
 * @param secret_ref Canonical secret reference.
 *
 * @returns A relative URL string for the value-read endpoint.
 */
export function build_secret_value_url(secret_ref: string): string {
    const segments = secret_ref.split("/")
    const encoded_segments = []
    for (const segment of segments) {
        encoded_segments.push(encodeURIComponent(segment))
    }
    const encoded = encoded_segments.join("/")
    const rtnval = SECRETS_API_PATH + "/value/" + encoded
    return rtnval
}

/**
 * Build the single-secret resource URL (used for rotate / delete).
 *
 * @param secret_ref Canonical secret reference.
 *
 * @returns A relative URL string for the single-secret resource.
 */
export function build_secret_resource_url(secret_ref: string): string {
    const segments = secret_ref.split("/")
    const encoded_segments = []
    for (const segment of segments) {
        encoded_segments.push(encodeURIComponent(segment))
    }
    const encoded = encoded_segments.join("/")
    const rtnval = SECRETS_API_PATH + "/" + encoded
    return rtnval
}

/**
 * Format an ISO-8601 timestamp for table display. Returns an
 * em-dash placeholder when the value is null/undefined/empty.
 *
 * @param value ISO-8601 timestamp or null.
 *
 * @returns A locale-formatted timestamp or ``"—"``.
 */
export function format_timestamp(value: string | null | undefined): string {
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
 * Classify an HTTP status from a value-reveal attempt into a
 * human-facing message. A 403 maps to a scope-permission-denied
 * message; other failures map to a generic message.
 *
 * @param status HTTP status code of the failed reveal.
 *
 * @returns A user-facing message string.
 */
export function reveal_error_message(status: number): string {
    if (status === 403) {
        const rtnval =
            "You don't have access to this secret's value."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "This secret no longer exists."
        return rtnval
    }
    if (status === 410) {
        const rtnval = "This secret version has expired."
        return rtnval
    }
    const rtnval =
        "Failed to read the secret value. Try again."
    return rtnval
}

/**
 * The secrets management view Custom Element. Register it with
 * ``customElements.define("pyc-secrets", PycSecrets)``.
 */
export class PycSecrets extends HTMLElement {
    private _state: SecretsViewState
    private _secrets: Secret[]
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null
    /**
     * Per-secret transient reveal state, keyed by secret_ref. The
     * plaintext value lives ONLY here -- never persisted, never
     * logged. Cleared on collapse and on disconnect.
     */
    private _revealed: Map<string, string>
    /**
     * Per-secret reveal error message, keyed by secret_ref.
     */
    private _reveal_errors: Map<string, string>

    public constructor() {
        super()
        this._state = {
            scopeKind: "ORG",
            scopeRef: "",
            loading: false,
            errored: false,
        }
        this._secrets = []
        this._root = null
        this._table_region = null
        this._revealed = new Map()
        this._reveal_errors = new Map()
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the scope
     * + load state without scraping the DOM.
     */
    public get viewState(): SecretsViewState {
        const rtnval = {
            scopeKind: this._state.scopeKind,
            scopeRef: this._state.scopeRef,
            loading: this._state.loading,
            errored: this._state.errored,
        }
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to confirm the count
     * of currently-revealed secret values.
     */
    public get revealedCount(): number {
        const rtnval = this._revealed.size
        return rtnval
    }

    /**
     * Lifecycle hook -- render the static chrome and kick off the
     * first fetch when the element is inserted into the document.
     */
    public connectedCallback(): void {
        this._render_chrome()
        void this._refresh()
        return
    }

    /**
     * Lifecycle hook -- clear every revealed plaintext value when
     * the element leaves the document (navigation away). The
     * reveal must never survive a navigation.
     */
    public disconnectedCallback(): void {
        this._revealed.clear()
        this._reveal_errors.clear()
        return
    }

    /**
     * Build the persistent chrome -- heading, scope selector,
     * create form, and the table region the data render replaces
     * on every fetch.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-secrets")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-secrets__heading")
        heading.textContent = "Secrets"
        root.appendChild(heading)

        root.appendChild(this._build_scope_tabs())
        root.appendChild(this._build_scope_ref_field())
        root.appendChild(this._build_create_form())

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-secrets__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        this._root = root
        this.replaceChildren(root)
        this._sync_scope_ref_visibility()
        return
    }

    /**
     * Build the Org / Project / User scope tab strip.
     */
    private _build_scope_tabs(): HTMLElement {
        const tabs = document.createElement("div")
        tabs.classList.add("pyc-secrets__tabs")
        tabs.setAttribute("role", "tablist")

        const labels: Record<string, string> = {
            ORG: "Org",
            PROJECT: "Project",
            USER: "User",
        }
        for (const kind of SECRET_SCOPE_KINDS) {
            const tab = document.createElement("button")
            tab.classList.add("pyc-secrets__tab")
            tab.setAttribute("type", "button")
            tab.setAttribute("role", "tab")
            tab.setAttribute("data-role", "scope-tab")
            tab.setAttribute("data-scope-kind", kind)
            tab.textContent = labels[kind]
            if (kind === this._state.scopeKind) {
                tab.setAttribute("aria-selected", "true")
            } else {
                tab.setAttribute("aria-selected", "false")
            }
            tab.addEventListener("click", () => {
                this._select_scope(kind)
            })
            tabs.appendChild(tab)
        }
        return tabs
    }

    /**
     * Build the scope-ref input field. Shown only for PROJECT and
     * USER scopes -- ORG-scoped secrets are service-wide and carry
     * no scope_ref.
     */
    private _build_scope_ref_field(): HTMLElement {
        const wrapper = document.createElement("div")
        wrapper.classList.add("pyc-secrets__scope-ref")
        wrapper.setAttribute("data-role", "scope-ref-field")

        const label = document.createElement("label")
        label.classList.add("pyc-secrets__field")
        label.textContent = "Scope reference"

        const input = document.createElement("input")
        input.classList.add("pyc-secrets__input")
        input.setAttribute("type", "text")
        input.setAttribute("data-role", "scope-ref-input")
        input.setAttribute("placeholder", "project id or user id")
        input.addEventListener("change", () => {
            this._state.scopeRef = input.value.trim()
            void this._refresh()
        })
        label.appendChild(input)
        wrapper.appendChild(label)
        return wrapper
    }

    /**
     * Build the "Create Secret" form -- name + scope-bound value.
     */
    private _build_create_form(): HTMLElement {
        const form = document.createElement("form")
        form.classList.add("pyc-secrets__create")
        form.setAttribute("data-role", "create-form")

        const name_label = document.createElement("label")
        name_label.classList.add("pyc-secrets__field")
        name_label.textContent = "Name"
        const name_input = document.createElement("input")
        name_input.classList.add("pyc-secrets__input")
        name_input.setAttribute("type", "text")
        name_input.setAttribute("data-role", "create-name")
        name_input.setAttribute("placeholder", "vault/myteam/api-token")
        name_input.required = true
        name_label.appendChild(name_input)
        form.appendChild(name_label)

        const value_label = document.createElement("label")
        value_label.classList.add("pyc-secrets__field")
        value_label.textContent = "Value"
        const value_input = document.createElement("input")
        value_input.classList.add("pyc-secrets__input")
        value_input.setAttribute("type", "password")
        value_input.setAttribute("data-role", "create-value")
        value_input.setAttribute("autocomplete", "new-password")
        value_input.required = true
        value_label.appendChild(value_input)
        form.appendChild(value_label)

        const submit = document.createElement("button")
        submit.classList.add("pyc-secrets__button", "pyc-secrets__button--primary")
        submit.setAttribute("type", "submit")
        submit.setAttribute("data-role", "create-submit")
        submit.textContent = "Create Secret"
        form.appendChild(submit)

        const status = document.createElement("p")
        status.classList.add("pyc-secrets__create-status")
        status.setAttribute("data-role", "create-status")
        form.appendChild(status)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_create(name_input, value_input, status)
        })
        return form
    }

    /**
     * Switch the active scope tab, reset the scope_ref, and
     * re-fetch the listing.
     *
     * @param scope_kind The newly-selected scope kind.
     */
    private _select_scope(scope_kind: string): void {
        if (scope_kind === this._state.scopeKind) {
            return
        }
        this._state.scopeKind = scope_kind
        this._state.scopeRef = ""
        this._revealed.clear()
        this._reveal_errors.clear()
        if (this._root !== null) {
            const tabs = this._root.querySelectorAll('[data-role="scope-tab"]')
            for (const tab of Array.from(tabs)) {
                const kind = tab.getAttribute("data-scope-kind")
                if (kind === scope_kind) {
                    tab.setAttribute("aria-selected", "true")
                } else {
                    tab.setAttribute("aria-selected", "false")
                }
            }
            const input = this._root.querySelector('[data-role="scope-ref-input"]')
            if (input instanceof HTMLInputElement) {
                input.value = ""
            }
        }
        this._sync_scope_ref_visibility()
        void this._refresh()
        return
    }

    /**
     * Show the scope-ref field for PROJECT / USER scopes and hide
     * it for ORG scope.
     */
    private _sync_scope_ref_visibility(): void {
        if (this._root === null) {
            return
        }
        const field = this._root.querySelector('[data-role="scope-ref-field"]')
        if (field instanceof HTMLElement) {
            if (this._state.scopeKind === "ORG") {
                field.hidden = true
            } else {
                field.hidden = false
            }
        }
        return
    }

    /**
     * Fetch the current scope's secret metadata and re-render the
     * table region. Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        this._state.loading = true
        this._state.errored = false
        this._render_table_region()

        const url = build_secrets_list_url(
            this._state.scopeKind,
            this._state.scopeRef,
        )
        let secrets: Secret[] | null = null
        let forbidden = false
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.status === 403) {
                forbidden = true
                throw new Error("secrets list forbidden")
            }
            if (response.ok === false) {
                throw new Error(
                    "secrets fetch failed: HTTP " + String(response.status),
                )
            }
            const body = await response.json()
            secrets = body as Secret[]
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.secrets.list_fetch_failed",
                { reason: String(reason) },
            )
            this._state.loading = false
            this._state.errored = true
            this._render_table_region(forbidden)
            return
        }

        if (Array.isArray(secrets) === false) {
            this._state.loading = false
            this._state.errored = true
            this._render_table_region()
            return
        }

        this._secrets = secrets
        this._state.loading = false
        this._state.errored = false
        this._render_table_region()
        return
    }

    /**
     * POST a new secret from the create-form inputs.
     */
    private async _submit_create(
            name_input: HTMLInputElement,
            value_input: HTMLInputElement,
            status: HTMLElement,
        ): Promise<void> {
        const name = name_input.value.trim()
        const value = value_input.value
        if (name.length === 0 || value.length === 0) {
            status.textContent = "Name and value are both required."
            status.setAttribute("data-tone", "error")
            return
        }
        if (this._state.scopeKind !== "ORG" && this._state.scopeRef.length === 0) {
            status.textContent =
                "A scope reference is required for project / user secrets."
            status.setAttribute("data-tone", "error")
            return
        }

        const payload: Record<string, string> = {
            name: name,
            scope_kind: this._state.scopeKind,
            value: value,
        }
        if (this._state.scopeKind !== "ORG") {
            payload.scope_ref = this._state.scopeRef
        }

        status.textContent = "Creating…"
        status.setAttribute("data-tone", "neutral")
        try {
            const response = await fetch(SECRETS_API_PATH, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            })
            if (response.ok === false) {
                if (response.status === 403) {
                    status.textContent =
                        "You don't have permission to create this secret."
                } else if (response.status === 409) {
                    status.textContent =
                        "A secret with that name already exists."
                } else {
                    status.textContent =
                        "Failed to create the secret. Try again."
                }
                status.setAttribute("data-tone", "error")
                return
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.secrets.create_failed",
                { reason: String(reason) },
            )
            status.textContent = "Failed to create the secret. Try again."
            status.setAttribute("data-tone", "error")
            return
        }

        // Clear the value input immediately -- the plaintext must
        // not linger in the form after a successful create.
        name_input.value = ""
        value_input.value = ""
        status.textContent = "Secret created."
        status.setAttribute("data-tone", "ok")
        await this._refresh()
        return
    }

    /**
     * Re-render the table region from the current state + secrets.
     *
     * @param forbidden When true, render the scope-forbidden
     *                   message instead of the generic error.
     */
    private _render_table_region(forbidden: boolean = false): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-secrets__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading secrets…"
            region.replaceChildren(loading)
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add("pyc-secrets__status", "pyc-secrets__status--error")
            if (forbidden === true) {
                error.setAttribute("data-role", "forbidden-state")
                error.textContent =
                    "You don't have access to secrets in this scope."
            } else {
                error.setAttribute("data-role", "error-state")
                error.textContent =
                    "Failed to load secrets. Try refreshing."
            }
            region.replaceChildren(error)
            return
        }

        if (this._secrets.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-secrets__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No secrets in this scope yet"
            region.replaceChildren(empty)
            return
        }

        const table = this._build_table()
        region.replaceChildren(table)
        return
    }

    /**
     * Build the secrets metadata ``<table>``. The table renders
     * METADATA only -- name, scope, timestamps -- and NEVER the
     * value column.
     */
    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-secrets__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = ["Name", "Scope", "Created", "Updated", "Value", "Actions"]
        for (const column of columns) {
            const th = document.createElement("th")
            th.scope = "col"
            th.textContent = column
            head_row.appendChild(th)
        }
        thead.appendChild(head_row)
        table.appendChild(thead)

        const tbody = document.createElement("tbody")
        for (const secret of this._secrets) {
            tbody.appendChild(this._build_row(secret))
        }
        table.appendChild(tbody)
        return table
    }

    /**
     * Build one table row for a secret's metadata plus its
     * reveal / rotate / delete controls.
     */
    private _build_row(secret: Secret): HTMLTableRowElement {
        const row = document.createElement("tr")
        row.classList.add("pyc-secrets__row")
        row.setAttribute("data-secret-ref", secret.secret_ref)

        const name_cell = document.createElement("td")
        const name_code = document.createElement("code")
        name_code.classList.add("pyc-secrets__ref")
        name_code.textContent = secret.secret_ref
        name_cell.appendChild(name_code)
        row.appendChild(name_cell)

        const scope_cell = document.createElement("td")
        const badge = document.createElement("span")
        badge.classList.add("pyc-secrets__badge")
        badge.setAttribute("data-scope-kind", secret.scope_kind)
        let scope_text = secret.scope_kind
        if (secret.scope_ref !== null && secret.scope_ref !== undefined &&
                secret.scope_ref.length > 0) {
            scope_text = secret.scope_kind + " · " + secret.scope_ref
        }
        badge.textContent = scope_text
        scope_cell.appendChild(badge)
        row.appendChild(scope_cell)

        const created_cell = document.createElement("td")
        created_cell.textContent = format_timestamp(secret.created_at)
        row.appendChild(created_cell)

        const updated_cell = document.createElement("td")
        updated_cell.textContent = format_timestamp(secret.updated_at)
        row.appendChild(updated_cell)

        const value_cell = document.createElement("td")
        value_cell.classList.add("pyc-secrets__value-cell")
        value_cell.setAttribute("data-role", "value-cell")
        this._render_value_cell(value_cell, secret)
        row.appendChild(value_cell)

        const actions_cell = document.createElement("td")
        actions_cell.classList.add("pyc-secrets__actions")

        const reveal_button = document.createElement("button")
        reveal_button.classList.add("pyc-secrets__button")
        reveal_button.setAttribute("type", "button")
        reveal_button.setAttribute("data-role", "reveal-action")
        const is_revealed = this._revealed.has(secret.secret_ref)
        reveal_button.textContent = is_revealed === true ? "Hide value" : "Reveal value"
        reveal_button.addEventListener("click", () => {
            void this._toggle_reveal(secret)
        })
        actions_cell.appendChild(reveal_button)

        const rotate_button = document.createElement("button")
        rotate_button.classList.add("pyc-secrets__button")
        rotate_button.setAttribute("type", "button")
        rotate_button.setAttribute("data-role", "rotate-action")
        rotate_button.textContent = "Rotate"
        rotate_button.addEventListener("click", () => {
            void this._rotate_secret(secret)
        })
        actions_cell.appendChild(rotate_button)

        const delete_button = document.createElement("button")
        delete_button.classList.add("pyc-secrets__button", "pyc-secrets__button--danger")
        delete_button.setAttribute("type", "button")
        delete_button.setAttribute("data-role", "delete-action")
        delete_button.textContent = "Delete"
        delete_button.addEventListener("click", () => {
            void this._delete_secret(secret)
        })
        actions_cell.appendChild(delete_button)

        row.appendChild(actions_cell)
        return row
    }

    /**
     * Render the value cell -- masked placeholder by default, the
     * transient plaintext when revealed, or the reveal error when
     * the value read was denied.
     */
    private _render_value_cell(cell: HTMLElement, secret: Secret): void {
        const error = this._reveal_errors.get(secret.secret_ref)
        if (error !== undefined) {
            const message = document.createElement("span")
            message.classList.add("pyc-secrets__value-error")
            message.setAttribute("data-role", "reveal-error")
            message.textContent = error
            cell.replaceChildren(message)
            return
        }
        const value = this._revealed.get(secret.secret_ref)
        if (value !== undefined) {
            const revealed = document.createElement("code")
            revealed.classList.add("pyc-secrets__value-revealed")
            revealed.setAttribute("data-role", "revealed-value")
            revealed.textContent = value
            cell.replaceChildren(revealed)
            return
        }
        const masked = document.createElement("span")
        masked.classList.add("pyc-secrets__value-masked")
        masked.setAttribute("data-role", "masked-value")
        masked.textContent = "••••••••"
        cell.replaceChildren(masked)
        return
    }

    /**
     * Toggle a secret's value reveal. On reveal, fetch the value
     * from the value-read endpoint and store it ONLY in the
     * transient ``_revealed`` map. On collapse, drop the value
     * from the map immediately.
     *
     * @param secret The secret whose value is being toggled.
     */
    private async _toggle_reveal(secret: Secret): Promise<void> {
        if (this._revealed.has(secret.secret_ref) === true) {
            this._revealed.delete(secret.secret_ref)
            this._reveal_errors.delete(secret.secret_ref)
            this._refresh_row(secret.secret_ref)
            return
        }
        this._reveal_errors.delete(secret.secret_ref)

        const url = build_secret_value_url(secret.secret_ref)
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                this._reveal_errors.set(
                    secret.secret_ref,
                    reveal_error_message(response.status),
                )
                this._refresh_row(secret.secret_ref)
                return
            }
            const body = await response.json()
            const secret_value = body as SecretValue
            if (typeof secret_value.value !== "string") {
                this._reveal_errors.set(
                    secret.secret_ref,
                    reveal_error_message(0),
                )
                this._refresh_row(secret.secret_ref)
                return
            }
            // Transient state only -- never persisted, never logged.
            this._revealed.set(secret.secret_ref, secret_value.value)
            this._refresh_row(secret.secret_ref)
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.secrets.reveal_failed",
                { secret_ref: secret.secret_ref },
            )
            this._reveal_errors.set(
                secret.secret_ref,
                reveal_error_message(0),
            )
            this._refresh_row(secret.secret_ref)
        }
        return
    }

    /**
     * Rotate a secret's value via ``PUT /api/v1/secrets/{ref}``.
     * Prompts for the new value, never reads back the old one.
     *
     * @param secret The secret to rotate.
     */
    private async _rotate_secret(secret: Secret): Promise<void> {
        const prompt_fn = window.prompt
        if (typeof prompt_fn !== "function") {
            return
        }
        const new_value = window.prompt(
            "Enter the new value for " + secret.secret_ref,
        )
        if (new_value === null || new_value.length === 0) {
            return
        }
        const url = build_secret_resource_url(secret.secret_ref)
        try {
            const response = await fetch(url, {
                method: "PUT",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ value: new_value }),
            })
            if (response.ok === false) {
                console.warn(
                    "pychestrate.ui.secrets.rotate_failed",
                    { secret_ref: secret.secret_ref, status: response.status },
                )
                return
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.secrets.rotate_failed",
                { secret_ref: secret.secret_ref },
            )
            return
        }
        // A rotation invalidates any revealed plaintext.
        this._revealed.delete(secret.secret_ref)
        this._reveal_errors.delete(secret.secret_ref)
        await this._refresh()
        return
    }

    /**
     * Delete a secret via ``DELETE /api/v1/secrets/{ref}`` after a
     * confirmation prompt.
     *
     * @param secret The secret to delete.
     */
    private async _delete_secret(secret: Secret): Promise<void> {
        const confirm_fn = window.confirm
        if (typeof confirm_fn !== "function") {
            return
        }
        const confirmed = window.confirm(
            "Delete the secret " + secret.secret_ref +
                "? This removes every version and cannot be undone.",
        )
        if (confirmed === false) {
            return
        }
        const url = build_secret_resource_url(secret.secret_ref)
        try {
            const response = await fetch(url, {
                method: "DELETE",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                console.warn(
                    "pychestrate.ui.secrets.delete_failed",
                    { secret_ref: secret.secret_ref, status: response.status },
                )
                return
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.secrets.delete_failed",
                { secret_ref: secret.secret_ref },
            )
            return
        }
        this._revealed.delete(secret.secret_ref)
        this._reveal_errors.delete(secret.secret_ref)
        await this._refresh()
        return
    }

    /**
     * Re-render a single secret's row in place -- used after a
     * reveal toggle so the rest of the table is untouched.
     *
     * @param secret_ref The secret_ref of the row to refresh.
     */
    private _refresh_row(secret_ref: string): void {
        if (this._table_region === null) {
            return
        }
        const candidates = this._table_region.querySelectorAll(
            "[data-secret-ref]",
        )
        let existing: Element | null = null
        for (const candidate of Array.from(candidates)) {
            if (candidate.getAttribute("data-secret-ref") === secret_ref) {
                existing = candidate
                break
            }
        }
        if (existing === null) {
            return
        }
        let secret: Secret | null = null
        for (const candidate of this._secrets) {
            if (candidate.secret_ref === secret_ref) {
                secret = candidate
                break
            }
        }
        if (secret === null) {
            return
        }
        const replacement = this._build_row(secret)
        existing.replaceWith(replacement)
        return
    }
}
