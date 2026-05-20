/**
 * ``<pyc-pods-list>`` -- the pods list view Custom Element.
 *
 * Missing-endpoint note -- the pod REST surface
 * (``pods_routes.py``) has no project-agnostic ``GET /pods``
 * collection. Pods are stored as project-scoped *pod definitions*
 * and addressed under ``/api/v1/projects/{project_id}/...``. So
 * this view requires a ``project_id`` -- supplied via a filter
 * input -- and lists the project's pod definitions from
 * ``GET /api/v1/projects/{project_id}/pod-definitions``. A
 * cross-project pods index is flagged as a follow-up requiring a
 * new server read endpoint.
 *
 * For each pod definition the view derives the member count from
 * the definition's ``spec`` (member entries) and links the row to
 * ``/pods/{pod_id}`` -- the pod-detail page, which is responsible
 * for fetching the live state, registration and lifecycle history.
 *
 * The list endpoint returns a plain JSON array (no paged envelope)
 * so the view paginates client-side.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

/**
 * Default page size for the client-side pager.
 */
const DEFAULT_PER_PAGE: number = 25

/**
 * Base path of the projects REST collection.
 */
const PROJECTS_API_PATH: string = "/api/v1/projects"

/**
 * One pod definition, as returned in the JSON array from
 * ``GET /api/v1/projects/{project_id}/pod-definitions``. Mirrors
 * the ``_definition_to_dict`` shape in ``pods_routes.py``.
 */
export interface PodDefinition {
    pod_id: string
    project_id: string
    pod_name: string
    current_version: number
    spec?: Record<string, unknown> | null
    spec_hash?: string | null
    created_at?: string | null
}

/**
 * The current filter + pagination state of the pods list view.
 * Exposed so unit tests can assert state transitions.
 */
export interface PodsListState {
    projectFilter: string
    page: number
    perPage: number
    total: number
    loading: boolean
    errored: boolean
    needsProject: boolean
}

/**
 * Build the ``GET …/pod-definitions`` collection URL for a project.
 *
 * @param project_id Owning project identifier.
 *
 * @returns A relative URL string.
 */
export function build_pod_definitions_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/pod-definitions"
    return rtnval
}

/**
 * Build the ``GET …/pod-definitions/{pod_id}`` detail URL.
 *
 * @param project_id Owning project identifier.
 * @param pod_id Pod definition identifier.
 *
 * @returns A relative URL string.
 */
export function build_pod_definition_url(
        project_id: string,
        pod_id: string,
    ): string {
    const rtnval = build_pod_definitions_url(project_id) + "/" +
        encodeURIComponent(pod_id)
    return rtnval
}

/**
 * Shorten a pod id (a UUID) to its first segment for compact
 * display.
 *
 * @param pod_id Full pod identifier.
 *
 * @returns A short, human-scannable id fragment.
 */
export function short_id(pod_id: string): string {
    if (typeof pod_id !== "string" || pod_id.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const dash_index = pod_id.indexOf("-")
    if (dash_index <= 0) {
        const rtnval = pod_id
        return rtnval
    }
    const rtnval = pod_id.slice(0, dash_index)
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
 * Count the declared members in a pod definition spec. The pod
 * spec stores members under a ``members`` array (per the
 * ``3-pod-definitions`` spec). Returns 0 when the spec is absent
 * or carries no ``members`` array.
 *
 * @param spec The pod definition's spec object.
 *
 * @returns The number of declared members.
 */
export function member_count(
        spec: Record<string, unknown> | null | undefined,
    ): number {
    if (spec === null || spec === undefined) {
        const rtnval = 0
        return rtnval
    }
    const members = spec["members"]
    if (Array.isArray(members) === true) {
        const rtnval = (members as unknown[]).length
        return rtnval
    }
    const rtnval = 0
    return rtnval
}

/**
 * Compute whether a "next page" control should be enabled.
 *
 * @param state Current list state.
 *
 * @returns True when a further page of results exists.
 */
export function has_next_page(state: PodsListState): boolean {
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
export function has_previous_page(state: PodsListState): boolean {
    const rtnval = state.page > 1
    return rtnval
}

/**
 * The pods list view Custom Element. Register it with
 * ``customElements.define("pyc-pods-list", PycPodsList)``.
 */
export class PycPodsList extends HTMLElement {
    private _state: PodsListState
    private _pods: PodDefinition[]
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null

    public constructor() {
        super()
        this._state = {
            projectFilter: "",
            page: 1,
            perPage: DEFAULT_PER_PAGE,
            total: 0,
            loading: false,
            errored: false,
            needsProject: true,
        }
        this._pods = []
        this._root = null
        this._table_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * filter + pagination state without scraping the DOM.
     */
    public get listState(): PodsListState {
        const rtnval: PodsListState = {
            projectFilter: this._state.projectFilter,
            page: this._state.page,
            perPage: this._state.perPage,
            total: this._state.total,
            loading: this._state.loading,
            errored: this._state.errored,
            needsProject: this._state.needsProject,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- render the static chrome. The pods list
     * cannot fetch without a project id, so a project filter
     * supplied via ``?project_id=`` seeds an immediate fetch;
     * otherwise the view shows a "pick a project" prompt.
     */
    public connectedCallback(): void {
        const seeded = this._project_from_search()
        if (seeded.length > 0) {
            this._state.projectFilter = seeded
        }
        this._render_chrome()
        if (this._state.projectFilter.length > 0) {
            void this._refresh()
        } else {
            this._render_table_region()
        }
        return
    }

    /**
     * Read a ``project_id`` from the current location's query
     * string so a deep link can seed the pods list.
     *
     * @returns The project id, or ``""`` when none is present.
     */
    private _project_from_search(): string {
        if (typeof window === "undefined") {
            const rtnval = ""
            return rtnval
        }
        const params = new URLSearchParams(window.location.search)
        const value = params.get("project_id")
        if (value === null) {
            const rtnval = ""
            return rtnval
        }
        const rtnval = value.trim()
        return rtnval
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-pods-list")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-pods-list__heading")
        heading.textContent = "Pods"
        root.appendChild(heading)

        const subtitle = document.createElement("p")
        subtitle.classList.add("pyc-pods-list__subtitle")
        subtitle.textContent =
            "Pod definitions are project-scoped. Enter a project id " +
            "to list its pods."
        root.appendChild(subtitle)

        const filters = document.createElement("div")
        filters.classList.add("pyc-pods-list__filters")

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-pods-list__filter")
        project_label.textContent = "Project"
        const project_input = document.createElement("input")
        project_input.classList.add("pyc-pods-list__input")
        project_input.setAttribute("type", "text")
        project_input.setAttribute("placeholder", "project id")
        project_input.setAttribute("data-role", "project-filter")
        if (this._state.projectFilter.length > 0) {
            project_input.value = this._state.projectFilter
        }
        project_input.addEventListener("change", () => {
            this._state.projectFilter = project_input.value.trim()
            this._state.page = 1
            if (this._state.projectFilter.length > 0) {
                void this._refresh()
            } else {
                this._state.needsProject = true
                this._pods = []
                this._state.total = 0
                this._render_table_region()
            }
        })
        project_label.appendChild(project_input)
        filters.appendChild(project_label)

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-pods-list__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            if (this._state.projectFilter.length > 0) {
                void this._refresh()
            }
        })
        filters.appendChild(refresh_button)

        root.appendChild(filters)

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-pods-list__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const pager = document.createElement("div")
        pager.classList.add("pyc-pods-list__pager")

        const prev_button = document.createElement("button")
        prev_button.classList.add("pyc-pods-list__button")
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
        page_indicator.classList.add("pyc-pods-list__page-indicator")
        page_indicator.setAttribute("data-role", "page-indicator")
        pager.appendChild(page_indicator)

        const next_button = document.createElement("button")
        next_button.classList.add("pyc-pods-list__button")
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
     * Fetch the project's pod definitions and re-render the table
     * region. Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.projectFilter.length === 0) {
            this._state.needsProject = true
            this._render_table_region()
            return
        }
        this._state.needsProject = false
        this._state.loading = true
        this._state.errored = false
        this._render_table_region()

        const url = build_pod_definitions_url(this._state.projectFilter)
        let pods: PodDefinition[] | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "pods fetch failed: HTTP " + String(response.status),
                )
            }
            const body = await response.json()
            pods = body as PodDefinition[]
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.pods.list_fetch_failed",
                { reason: String(reason) },
            )
            this._state.loading = false
            this._state.errored = true
            this._render_table_region()
            return
        }

        if (pods === null || Array.isArray(pods) === false) {
            this._state.loading = false
            this._state.errored = true
            this._render_table_region()
            return
        }

        this._pods = pods
        this._state.total = pods.length
        this._state.page = 1
        this._state.loading = false
        this._state.errored = false
        this._render_table_region()
        return
    }

    private _page_slice(): PodDefinition[] {
        const start = (this._state.page - 1) * this._state.perPage
        const end = start + this._state.perPage
        const rtnval = this._pods.slice(start, end)
        return rtnval
    }

    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.needsProject === true) {
            const prompt = document.createElement("p")
            prompt.classList.add("pyc-pods-list__status")
            prompt.setAttribute("data-role", "needs-project")
            prompt.textContent =
                "Enter a project id above to list its pods."
            region.replaceChildren(prompt)
            this._render_pager()
            return
        }

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-pods-list__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading pods…"
            region.replaceChildren(loading)
            this._render_pager()
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-pods-list__status",
                "pyc-pods-list__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load pods. Try refreshing."
            region.replaceChildren(error)
            this._render_pager()
            return
        }

        if (this._pods.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-pods-list__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No pods defined in this project"
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
        table.classList.add("pyc-pods-list__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Pod",
            "Name",
            "Version",
            "Members",
            "Created",
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
        for (const pod of this._page_slice()) {
            const row = document.createElement("tr")
            row.classList.add("pyc-pods-list__row")

            const id_cell = document.createElement("td")
            const link = document.createElement("a")
            link.classList.add("pyc-pods-list__pod-link")
            const href = "/pods/" + pod.pod_id +
                "?project_id=" + encodeURIComponent(pod.project_id)
            link.setAttribute("href", href)
            link.textContent = short_id(pod.pod_id)
            link.title = pod.pod_id
            id_cell.appendChild(link)
            row.appendChild(id_cell)

            const name_cell = document.createElement("td")
            name_cell.textContent =
                pod.pod_name !== null && pod.pod_name.length > 0
                    ? pod.pod_name
                    : "—"
            row.appendChild(name_cell)

            const version_cell = document.createElement("td")
            version_cell.textContent = "v" + String(pod.current_version)
            row.appendChild(version_cell)

            const members_cell = document.createElement("td")
            members_cell.textContent = String(member_count(pod.spec))
            row.appendChild(members_cell)

            const created_cell = document.createElement("td")
            created_cell.textContent = format_timestamp(pod.created_at)
            row.appendChild(created_cell)

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
