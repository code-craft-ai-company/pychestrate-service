/**
 * ``<pyc-clients-list>`` -- the enrolled-clients list view Custom
 * Element.
 *
 * On mount the element fetches ``GET /api/v1/clients`` and renders
 * a filterable table of enrolled runtimes (clients). Each row shows
 * the client id, the pod name it enrolled under, enrollment status,
 * runtime liveness, last-seen heartbeat, agent version and a
 * compact capability-tag summary drawn from the client's attribute
 * map. Each row links to ``/clients/{client_id}`` -- the client
 * detail page.
 *
 * ``GET /api/v1/clients`` returns a plain JSON array (not a paged
 * envelope) so the view paginates client-side over the fetched
 * array. It accepts optional ``project_id`` / ``status`` /
 * ``liveness_state`` query filters which the view threads through
 * its filter controls.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state lives in instance fields.
 */

/**
 * The ``ClientStatus`` enum -- mirrors ``clients.enums.ClientStatus``.
 */
export const CLIENT_STATUSES: readonly string[] = [
    "ACTIVE",
    "SUSPENDED",
    "REVOKED",
]

/**
 * The ``LivenessState`` enum -- mirrors
 * ``clients.enums.LivenessState``.
 */
export const LIVENESS_STATES: readonly string[] = [
    "ALIVE",
    "DEGRADED",
    "LOST",
]

/**
 * Default page size for the client-side pager.
 */
const DEFAULT_PER_PAGE: number = 25

/**
 * Base path of the clients REST collection.
 */
const CLIENTS_API_PATH: string = "/api/v1/clients"

/**
 * One client, as returned in the JSON array from
 * ``GET /api/v1/clients``. Mirrors the ``_view_to_dict`` shape in
 * ``clients_routes.py``.
 */
export interface Client {
    client_id: string
    project_id: string
    pod_name: string
    status: string
    liveness_state: string
    enrolled_at?: string | null
    last_seen?: string | null
    last_agent_version?: string | null
    transport_name?: string | null
    degraded_at?: string | null
    revision_token?: string | null
    attributes?: Record<string, unknown> | null
}

/**
 * The current filter + pagination state of the clients list view.
 * Exposed so unit tests can assert state transitions.
 */
export interface ClientsListState {
    projectFilter: string
    statusFilter: string
    livenessFilter: string
    page: number
    perPage: number
    total: number
    loading: boolean
    errored: boolean
}

/**
 * Build the ``GET /api/v1/clients`` query URL from the supplied
 * filter state. Empty filters are omitted so the server applies
 * its defaults. Pagination is client-side so no page params are
 * sent.
 *
 * @param state Current list state.
 *
 * @returns A relative URL string including the query string.
 */
export function build_clients_query_url(state: ClientsListState): string {
    const params = new URLSearchParams()
    if (state.projectFilter.length > 0) {
        params.set("project_id", state.projectFilter)
    }
    if (state.statusFilter.length > 0) {
        params.set("status", state.statusFilter)
    }
    if (state.livenessFilter.length > 0) {
        params.set("liveness_state", state.livenessFilter)
    }
    const query = params.toString()
    if (query.length === 0) {
        const rtnval = CLIENTS_API_PATH
        return rtnval
    }
    const rtnval = CLIENTS_API_PATH + "?" + query
    return rtnval
}

/**
 * Build the ``GET /api/v1/clients/{client_id}`` detail URL.
 *
 * @param client_id Client identifier.
 *
 * @returns A relative URL string.
 */
export function build_client_detail_url(client_id: string): string {
    const rtnval = CLIENTS_API_PATH + "/" + encodeURIComponent(client_id)
    return rtnval
}

/**
 * Shorten a client id (a UUID) to its first segment for compact
 * display. Returns the input unchanged when it does not look like
 * a UUID.
 *
 * @param client_id Full client identifier.
 *
 * @returns A short, human-scannable id fragment.
 */
export function short_id(client_id: string): string {
    if (typeof client_id !== "string" || client_id.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const dash_index = client_id.indexOf("-")
    if (dash_index <= 0) {
        const rtnval = client_id
        return rtnval
    }
    const rtnval = client_id.slice(0, dash_index)
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
 * Classify a client status into a coarse badge tone so the CSS can
 * pick a token-driven color.
 *
 * @param status One of the ``ClientStatus`` enum values.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function status_tone(status: string): string {
    if (status === "ACTIVE") {
        const rtnval = "ok"
        return rtnval
    }
    if (status === "SUSPENDED") {
        const rtnval = "warn"
        return rtnval
    }
    if (status === "REVOKED") {
        const rtnval = "error"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Classify a runtime liveness state into a coarse badge tone.
 *
 * @param liveness One of the ``LivenessState`` enum values.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function liveness_tone(liveness: string): string {
    if (liveness === "ALIVE") {
        const rtnval = "ok"
        return rtnval
    }
    if (liveness === "DEGRADED") {
        const rtnval = "warn"
        return rtnval
    }
    if (liveness === "LOST") {
        const rtnval = "error"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Derive a compact list of capability tags from a client's
 * attribute map. The agent reports capabilities under attribute
 * kinds; this helper flattens string / array values into a tag
 * list for display. Returns an empty array when no capability-like
 * attributes are present.
 *
 * @param attributes The client's attribute map (kind -> value).
 *
 * @returns A list of human-readable capability tag strings.
 */
export function capability_tags(
        attributes: Record<string, unknown> | null | undefined,
    ): string[] {
    const rtnval: string[] = []
    if (attributes === null || attributes === undefined) {
        return rtnval
    }
    const keys = Object.keys(attributes)
    for (const key of keys) {
        const value = attributes[key]
        if (Array.isArray(value) === true) {
            for (const entry of value as unknown[]) {
                if (typeof entry === "string" && entry.length > 0) {
                    rtnval.push(key + ":" + entry)
                }
            }
            continue
        }
        if (typeof value === "string" && value.length > 0) {
            rtnval.push(key + ":" + value)
            continue
        }
        if (typeof value === "number" || typeof value === "boolean") {
            rtnval.push(key + ":" + String(value))
        }
    }
    return rtnval
}

/**
 * Compute whether a "next page" control should be enabled.
 *
 * @param state Current list state.
 *
 * @returns True when a further page of results exists.
 */
export function has_next_page(state: ClientsListState): boolean {
    const consumed = state.page * state.perPage
    const rtnval = consumed < state.total
    return rtnval
}

/**
 * Compute whether a "previous page" control should be enabled.
 *
 * @param state Current list state.
 *
 * @returns True when the caller is not on the first page.
 */
export function has_previous_page(state: ClientsListState): boolean {
    const rtnval = state.page > 1
    return rtnval
}

/**
 * The clients list view Custom Element. Register it with
 * ``customElements.define("pyc-clients-list", PycClientsList)``.
 */
export class PycClientsList extends HTMLElement {
    private _state: ClientsListState
    private _clients: Client[]
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null

    public constructor() {
        super()
        this._state = {
            projectFilter: "",
            statusFilter: "",
            livenessFilter: "",
            page: 1,
            perPage: DEFAULT_PER_PAGE,
            total: 0,
            loading: false,
            errored: false,
        }
        this._clients = []
        this._root = null
        this._table_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * filter + pagination state without scraping the DOM.
     */
    public get listState(): ClientsListState {
        const rtnval: ClientsListState = {
            projectFilter: this._state.projectFilter,
            statusFilter: this._state.statusFilter,
            livenessFilter: this._state.livenessFilter,
            page: this._state.page,
            perPage: this._state.perPage,
            total: this._state.total,
            loading: this._state.loading,
            errored: this._state.errored,
        }
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

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-clients-list")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-clients-list__heading")
        heading.textContent = "Clients"
        root.appendChild(heading)

        const subtitle = document.createElement("p")
        subtitle.classList.add("pyc-clients-list__subtitle")
        subtitle.textContent =
            "Enrolled runtimes (agents). Each client backs the pods " +
            "it registers under."
        root.appendChild(subtitle)

        const filters = document.createElement("div")
        filters.classList.add("pyc-clients-list__filters")

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-clients-list__filter")
        project_label.textContent = "Project"
        const project_input = document.createElement("input")
        project_input.classList.add("pyc-clients-list__input")
        project_input.setAttribute("type", "text")
        project_input.setAttribute("placeholder", "project id")
        project_input.setAttribute("data-role", "project-filter")
        project_input.addEventListener("change", () => {
            this._state.projectFilter = project_input.value.trim()
            this._state.page = 1
            void this._refresh()
        })
        project_label.appendChild(project_input)
        filters.appendChild(project_label)

        const status_label = document.createElement("label")
        status_label.classList.add("pyc-clients-list__filter")
        status_label.textContent = "Status"
        const status_select = document.createElement("select")
        status_select.classList.add("pyc-clients-list__select")
        status_select.setAttribute("data-role", "status-filter")
        const any_status = document.createElement("option")
        any_status.value = ""
        any_status.textContent = "All statuses"
        status_select.appendChild(any_status)
        for (const status of CLIENT_STATUSES) {
            const option = document.createElement("option")
            option.value = status
            option.textContent = status
            status_select.appendChild(option)
        }
        status_select.addEventListener("change", () => {
            this._state.statusFilter = status_select.value
            this._state.page = 1
            void this._refresh()
        })
        status_label.appendChild(status_select)
        filters.appendChild(status_label)

        const liveness_label = document.createElement("label")
        liveness_label.classList.add("pyc-clients-list__filter")
        liveness_label.textContent = "Liveness"
        const liveness_select = document.createElement("select")
        liveness_select.classList.add("pyc-clients-list__select")
        liveness_select.setAttribute("data-role", "liveness-filter")
        const any_liveness = document.createElement("option")
        any_liveness.value = ""
        any_liveness.textContent = "All liveness"
        liveness_select.appendChild(any_liveness)
        for (const liveness of LIVENESS_STATES) {
            const option = document.createElement("option")
            option.value = liveness
            option.textContent = liveness
            liveness_select.appendChild(option)
        }
        liveness_select.addEventListener("change", () => {
            this._state.livenessFilter = liveness_select.value
            this._state.page = 1
            void this._refresh()
        })
        liveness_label.appendChild(liveness_select)
        filters.appendChild(liveness_label)

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-clients-list__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            void this._refresh()
        })
        filters.appendChild(refresh_button)

        root.appendChild(filters)

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-clients-list__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const pager = document.createElement("div")
        pager.classList.add("pyc-clients-list__pager")

        const prev_button = document.createElement("button")
        prev_button.classList.add("pyc-clients-list__button")
        prev_button.setAttribute("type", "button")
        prev_button.setAttribute("data-role", "prev-page")
        prev_button.textContent = "Previous"
        prev_button.addEventListener("click", () => {
            if (has_previous_page(this._state) === true) {
                this._state.page = this._state.page - 1
                this._render_table_region()
            }
        })
        pager.appendChild(prev_button)

        const page_indicator = document.createElement("span")
        page_indicator.classList.add("pyc-clients-list__page-indicator")
        page_indicator.setAttribute("data-role", "page-indicator")
        pager.appendChild(page_indicator)

        const next_button = document.createElement("button")
        next_button.classList.add("pyc-clients-list__button")
        next_button.setAttribute("type", "button")
        next_button.setAttribute("data-role", "next-page")
        next_button.textContent = "Next"
        next_button.addEventListener("click", () => {
            if (has_next_page(this._state) === true) {
                this._state.page = this._state.page + 1
                this._render_table_region()
            }
        })
        pager.appendChild(next_button)

        root.appendChild(pager)

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Fetch the clients array from the REST endpoint and re-render
     * the table region. Exposed so unit tests can await a fetch
     * cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        this._state.loading = true
        this._state.errored = false
        this._render_table_region()

        const url = build_clients_query_url(this._state)
        let clients: Client[] | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "clients fetch failed: HTTP " + String(response.status),
                )
            }
            const body = await response.json()
            clients = body as Client[]
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.clients.list_fetch_failed",
                { reason: String(reason) },
            )
            this._state.loading = false
            this._state.errored = true
            this._render_table_region()
            return
        }

        if (clients === null || Array.isArray(clients) === false) {
            this._state.loading = false
            this._state.errored = true
            this._render_table_region()
            return
        }

        this._clients = clients
        this._state.total = clients.length
        this._state.page = 1
        this._state.loading = false
        this._state.errored = false
        this._render_table_region()
        return
    }

    /**
     * Slice the fetched clients array down to the current page.
     *
     * @returns The clients for the current page.
     */
    private _page_slice(): Client[] {
        const start = (this._state.page - 1) * this._state.perPage
        const end = start + this._state.perPage
        const rtnval = this._clients.slice(start, end)
        return rtnval
    }

    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-clients-list__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading clients…"
            region.replaceChildren(loading)
            this._render_pager()
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-clients-list__status",
                "pyc-clients-list__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load clients. Try refreshing."
            region.replaceChildren(error)
            this._render_pager()
            return
        }

        if (this._clients.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-clients-list__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No enrolled clients yet"
            region.replaceChildren(empty)
            this._render_pager()
            return
        }

        const table = this._build_table()
        region.replaceChildren(table)
        this._render_pager()
        return
    }

    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-clients-list__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Client",
            "Pod",
            "Status",
            "Liveness",
            "Last heartbeat",
            "Agent version",
            "Capabilities",
        ]
        for (const column of columns) {
            const th = document.createElement("th")
            th.scope = "col"
            th.textContent = column
            head_row.appendChild(th)
        }
        thead.appendChild(head_row)
        table.appendChild(thead)

        const tbody = document.createElement("tbody")
        for (const client of this._page_slice()) {
            const row = document.createElement("tr")
            row.classList.add("pyc-clients-list__row")

            const id_cell = document.createElement("td")
            const link = document.createElement("a")
            link.classList.add("pyc-clients-list__client-link")
            link.setAttribute("href", "/clients/" + client.client_id)
            link.textContent = short_id(client.client_id)
            link.title = client.client_id
            id_cell.appendChild(link)
            row.appendChild(id_cell)

            const pod_cell = document.createElement("td")
            pod_cell.textContent =
                client.pod_name !== null && client.pod_name.length > 0
                    ? client.pod_name
                    : "—"
            row.appendChild(pod_cell)

            const status_cell = document.createElement("td")
            const status_badge = document.createElement("span")
            status_badge.classList.add("pyc-clients-list__badge")
            status_badge.setAttribute("data-tone", status_tone(client.status))
            status_badge.textContent = client.status
            status_cell.appendChild(status_badge)
            row.appendChild(status_cell)

            const liveness_cell = document.createElement("td")
            const liveness_badge = document.createElement("span")
            liveness_badge.classList.add("pyc-clients-list__badge")
            liveness_badge.setAttribute(
                "data-tone",
                liveness_tone(client.liveness_state),
            )
            liveness_badge.textContent = client.liveness_state
            liveness_cell.appendChild(liveness_badge)
            row.appendChild(liveness_cell)

            const seen_cell = document.createElement("td")
            seen_cell.textContent = format_timestamp(client.last_seen)
            row.appendChild(seen_cell)

            const version_cell = document.createElement("td")
            version_cell.textContent =
                client.last_agent_version !== null &&
                client.last_agent_version !== undefined &&
                client.last_agent_version.length > 0
                    ? client.last_agent_version
                    : "—"
            row.appendChild(version_cell)

            const caps_cell = document.createElement("td")
            const tags = capability_tags(client.attributes)
            if (tags.length === 0) {
                caps_cell.textContent = "—"
            } else {
                for (const tag of tags) {
                    const chip = document.createElement("span")
                    chip.classList.add("pyc-clients-list__tag")
                    chip.textContent = tag
                    caps_cell.appendChild(chip)
                }
            }
            row.appendChild(caps_cell)

            tbody.appendChild(row)
        }
        table.appendChild(tbody)
        return table
    }

    private _render_pager(): void {
        if (this._root === null) {
            return
        }
        const prev = this._root.querySelector('[data-role="prev-page"]')
        const next = this._root.querySelector('[data-role="next-page"]')
        const indicator = this._root.querySelector('[data-role="page-indicator"]')

        if (prev instanceof HTMLButtonElement) {
            prev.disabled = has_previous_page(this._state) === false
        }
        if (next instanceof HTMLButtonElement) {
            next.disabled = has_next_page(this._state) === false
        }
        if (indicator instanceof HTMLElement) {
            const label = "Page " + String(this._state.page) +
                " · " + String(this._state.total) + " total"
            indicator.textContent = label
        }
        return
    }
}
