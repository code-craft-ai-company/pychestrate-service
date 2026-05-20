/**
 * ``<pyc-runs-list>`` -- the runs list view Custom Element.
 *
 * On mount the element fetches ``GET /api/v1/runs`` (first page)
 * and renders a paginated, filterable table of test runs. Each row
 * links to ``/runs/{run_id}`` -- the run-detail page (a later PR);
 * until that lands the link 404s, which is acceptable.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state (filters, page) lives in instance fields.
 */

/**
 * The ``RunState`` enum from ``specs/openapi/pychestrate.yaml``.
 * Mirrors ``jobs.run.state.enums.RunState``.
 */
export const RUN_STATES: readonly string[] = [
    "pending",
    "dispatching",
    "dispatched",
    "dispatch_unconfirmed",
    "dispatch_lost",
    "dispatch_failed",
    "running",
    "progress_stalled",
    "cancel_requested",
    "cancelling",
    "cancelled",
    "completing",
    "completed",
    "failed",
    "needs_investigation",
]

/**
 * One run, as returned in the ``items`` array of ``RunPage``.
 * Only the fields the list view renders are typed here.
 */
export interface Run {
    run_id: string
    project_id: string
    pod_id: string
    job_name?: string | null
    job_type: string
    state: string
    terminal_outcome?: string | null
    created_at: string
    dispatched_at?: string | null
    started_at?: string | null
    completed_at?: string | null
}

/**
 * Pagination metadata returned alongside the ``items`` array.
 */
export interface PageMeta {
    page: number
    per_page: number
    total: number
    next_cursor?: string | null
}

/**
 * The ``RunPage`` response shape -- a page of runs plus meta.
 */
export interface RunPage {
    items: Run[]
    meta: PageMeta
}

/**
 * The current filter + pagination state of the list view. Exposed
 * so unit tests can assert state transitions without rendering.
 */
export interface RunsListState {
    stateFilter: string
    projectFilter: string
    page: number
    perPage: number
    total: number
    loading: boolean
    errored: boolean
}

/**
 * Default page size requested from the REST endpoint.
 */
const DEFAULT_PER_PAGE: number = 25

/**
 * Base path of the runs REST collection.
 */
const RUNS_API_PATH: string = "/api/v1/runs"

/**
 * Build the ``GET /api/v1/runs`` query URL from the supplied
 * filter + pagination state. Empty filters are omitted so the
 * server applies its defaults.
 *
 * @param state Current list state.
 *
 * @returns A relative URL string including the query string.
 */
export function build_runs_query_url(state: RunsListState): string {
    const params = new URLSearchParams()
    if (state.projectFilter.length > 0) {
        params.set("project_id", state.projectFilter)
    }
    if (state.stateFilter.length > 0) {
        params.set("state", state.stateFilter)
    }
    params.set("page", String(state.page))
    params.set("per_page", String(state.perPage))
    const query = params.toString()
    const rtnval = RUNS_API_PATH + "?" + query
    return rtnval
}

/**
 * Shorten a run id (a UUID) to its first segment for compact
 * display in the table. Returns the input unchanged when it does
 * not look like a UUID.
 *
 * @param run_id Full run identifier.
 *
 * @returns A short, human-scannable id fragment.
 */
export function short_run_id(run_id: string): string {
    if (typeof run_id !== "string" || run_id.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const dash_index = run_id.indexOf("-")
    if (dash_index <= 0) {
        const rtnval = run_id
        return rtnval
    }
    const rtnval = run_id.slice(0, dash_index)
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
 * Classify a run state into a coarse badge tone so the CSS can
 * pick a token-driven color without hardcoding per-state classes.
 *
 * @param run_state One of the ``RunState`` enum values.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function state_badge_tone(run_state: string): string {
    if (run_state === "completed") {
        const rtnval = "ok"
        return rtnval
    }
    const error_states = ["failed", "dispatch_failed", "dispatch_lost", "needs_investigation"]
    if (error_states.indexOf(run_state) >= 0) {
        const rtnval = "error"
        return rtnval
    }
    const warn_states = ["progress_stalled", "dispatch_unconfirmed", "cancel_requested", "cancelling", "cancelled"]
    if (warn_states.indexOf(run_state) >= 0) {
        const rtnval = "warn"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Compute whether a "next page" control should be enabled given
 * the current page, page size, and known total.
 *
 * @param state Current list state.
 *
 * @returns True when a further page of results exists.
 */
export function has_next_page(state: RunsListState): boolean {
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
export function has_previous_page(state: RunsListState): boolean {
    const rtnval = state.page > 1
    return rtnval
}

/**
 * The runs list view Custom Element. Register it with
 * ``customElements.define("pyc-runs-list", PycRunsList)``.
 */
export class PycRunsList extends HTMLElement {
    private _state: RunsListState
    private _runs: Run[]
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null

    public constructor() {
        super()
        this._state = {
            stateFilter: "",
            projectFilter: "",
            page: 1,
            perPage: DEFAULT_PER_PAGE,
            total: 0,
            loading: false,
            errored: false,
        }
        this._runs = []
        this._root = null
        this._table_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * filter + pagination state without scraping the DOM.
     */
    public get listState(): RunsListState {
        const rtnval = {
            stateFilter: this._state.stateFilter,
            projectFilter: this._state.projectFilter,
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

    /**
     * Build the persistent chrome -- heading, filter controls,
     * pagination controls, and the table region the data render
     * replaces on every fetch.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-runs-list")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-runs-list__heading")
        heading.textContent = "Runs"
        root.appendChild(heading)

        const filters = document.createElement("div")
        filters.classList.add("pyc-runs-list__filters")

        const state_label = document.createElement("label")
        state_label.classList.add("pyc-runs-list__filter")
        state_label.textContent = "State"
        const state_select = document.createElement("select")
        state_select.classList.add("pyc-runs-list__select")
        state_select.setAttribute("data-role", "state-filter")
        const any_option = document.createElement("option")
        any_option.value = ""
        any_option.textContent = "All states"
        state_select.appendChild(any_option)
        for (const run_state of RUN_STATES) {
            const option = document.createElement("option")
            option.value = run_state
            option.textContent = run_state
            state_select.appendChild(option)
        }
        state_select.addEventListener("change", () => {
            this._state.stateFilter = state_select.value
            this._state.page = 1
            void this._refresh()
        })
        state_label.appendChild(state_select)
        filters.appendChild(state_label)

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-runs-list__filter")
        project_label.textContent = "Project"
        const project_input = document.createElement("input")
        project_input.classList.add("pyc-runs-list__input")
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

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-runs-list__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            void this._refresh()
        })
        filters.appendChild(refresh_button)

        root.appendChild(filters)

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-runs-list__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const pager = document.createElement("div")
        pager.classList.add("pyc-runs-list__pager")

        const prev_button = document.createElement("button")
        prev_button.classList.add("pyc-runs-list__button")
        prev_button.setAttribute("type", "button")
        prev_button.setAttribute("data-role", "prev-page")
        prev_button.textContent = "Previous"
        prev_button.addEventListener("click", () => {
            if (has_previous_page(this._state) === true) {
                this._state.page = this._state.page - 1
                void this._refresh()
            }
        })
        pager.appendChild(prev_button)

        const page_indicator = document.createElement("span")
        page_indicator.classList.add("pyc-runs-list__page-indicator")
        page_indicator.setAttribute("data-role", "page-indicator")
        pager.appendChild(page_indicator)

        const next_button = document.createElement("button")
        next_button.classList.add("pyc-runs-list__button")
        next_button.setAttribute("type", "button")
        next_button.setAttribute("data-role", "next-page")
        next_button.textContent = "Next"
        next_button.addEventListener("click", () => {
            if (has_next_page(this._state) === true) {
                this._state.page = this._state.page + 1
                void this._refresh()
            }
        })
        pager.appendChild(next_button)

        root.appendChild(pager)

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Fetch the current page from the REST endpoint and re-render
     * the table region. Drives the loading / error / empty
     * states. Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        this._state.loading = true
        this._state.errored = false
        this._render_table_region()

        const url = build_runs_query_url(this._state)
        let page: RunPage | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error("runs fetch failed: HTTP " + String(response.status))
            }
            const body = await response.json()
            page = body as RunPage
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.runs.list_fetch_failed",
                { reason: String(reason) },
            )
            this._state.loading = false
            this._state.errored = true
            this._render_table_region()
            return
        }

        if (page === null || Array.isArray(page.items) === false) {
            this._state.loading = false
            this._state.errored = true
            this._render_table_region()
            return
        }

        this._runs = page.items
        const meta = page.meta
        if (meta !== undefined && meta !== null) {
            if (typeof meta.total === "number") {
                this._state.total = meta.total
            }
            if (typeof meta.page === "number") {
                this._state.page = meta.page
            }
            if (typeof meta.per_page === "number") {
                this._state.perPage = meta.per_page
            }
        }
        this._state.loading = false
        this._state.errored = false
        this._render_table_region()
        return
    }

    /**
     * Re-render the table region from the current state + runs.
     */
    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-runs-list__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading runs…"
            region.replaceChildren(loading)
            this._render_pager()
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add("pyc-runs-list__status", "pyc-runs-list__status--error")
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load runs. Try refreshing."
            region.replaceChildren(error)
            this._render_pager()
            return
        }

        if (this._runs.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-runs-list__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No runs yet"
            region.replaceChildren(empty)
            this._render_pager()
            return
        }

        const table = this._build_table()
        region.replaceChildren(table)
        this._render_pager()
        return
    }

    /**
     * Build the runs ``<table>`` from the current ``_runs`` list.
     */
    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-runs-list__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = ["Run", "Project", "State", "Created", "Started", "Completed"]
        for (const column of columns) {
            const th = document.createElement("th")
            th.scope = "col"
            th.textContent = column
            head_row.appendChild(th)
        }
        thead.appendChild(head_row)
        table.appendChild(thead)

        const tbody = document.createElement("tbody")
        for (const run of this._runs) {
            const row = document.createElement("tr")
            row.classList.add("pyc-runs-list__row")

            const id_cell = document.createElement("td")
            const link = document.createElement("a")
            link.classList.add("pyc-runs-list__run-link")
            link.setAttribute("href", "/runs/" + run.run_id)
            link.textContent = short_run_id(run.run_id)
            id_cell.appendChild(link)
            row.appendChild(id_cell)

            const project_cell = document.createElement("td")
            project_cell.textContent = run.project_id
            row.appendChild(project_cell)

            const state_cell = document.createElement("td")
            const badge = document.createElement("span")
            badge.classList.add("pyc-runs-list__badge")
            badge.setAttribute("data-tone", state_badge_tone(run.state))
            badge.textContent = run.state
            state_cell.appendChild(badge)
            row.appendChild(state_cell)

            const created_cell = document.createElement("td")
            created_cell.textContent = format_timestamp(run.created_at)
            row.appendChild(created_cell)

            const started_cell = document.createElement("td")
            started_cell.textContent = format_timestamp(run.started_at)
            row.appendChild(started_cell)

            const completed_cell = document.createElement("td")
            completed_cell.textContent = format_timestamp(run.completed_at)
            row.appendChild(completed_cell)

            tbody.appendChild(row)
        }
        table.appendChild(tbody)
        return table
    }

    /**
     * Update the pager controls -- enabled state + the page
     * indicator label -- from the current state.
     */
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
