/**
 * ``<pyc-resource-pools>`` -- the resource-pools list view Custom
 * Element.
 *
 * The resource-pools REST collection is project-scoped: a
 * ``project_id`` query parameter is required on
 * ``GET /api/v1/resource-pools``. So this view renders a project-id
 * filter input; without one it shows a "pick a project" prompt.
 *
 * The list endpoint returns a server-paginated ``{items, meta}``
 * envelope (``ResourcePoolPage``), so the view drives the pager
 * through the ``page`` / ``per_page`` query parameters and re-fetches
 * on a page change.
 *
 * The view also surfaces a "Create Pool" inline form -- a pool name,
 * an optional description and a comma-separated capability-tags
 * field -- that POSTs a ``ResourcePoolCreateRequest`` to
 * ``…/resource-pools``.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

/**
 * Default page size for the server-side pager.
 */
const DEFAULT_PER_PAGE: number = 50

/**
 * Base path of the resource-pools REST collection.
 */
const RESOURCE_POOLS_API_PATH: string = "/api/v1/resource-pools"

/**
 * One resource pool, as returned in the ``items`` array of a
 * ``ResourcePoolPage``. Mirrors the ``ResourcePool`` OpenAPI schema.
 */
export interface ResourcePool {
    pool_id: string
    project_id: string
    name: string
    description?: string | null
    capability_tags: string[]
    member_count: number
    created_at?: string | null
    updated_at?: string | null
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
 * The ``ResourcePoolPage`` response shape.
 */
export interface ResourcePoolPage {
    items: ResourcePool[]
    meta: PageMeta
}

/**
 * The current filter + pagination state of the resource-pools list
 * view. Exposed so unit tests can assert state transitions.
 */
export interface ResourcePoolsListState {
    projectFilter: string
    page: number
    perPage: number
    total: number
    loading: boolean
    errored: boolean
    needsProject: boolean
}

/**
 * Build the ``GET /resource-pools`` collection URL for a project +
 * page.
 *
 * @param project_id Owning project identifier.
 * @param page 1-based page number.
 * @param per_page Page size.
 *
 * @returns A relative URL string.
 */
export function build_resource_pools_url(
        project_id: string,
        page: number,
        per_page: number,
    ): string {
    const params = new URLSearchParams()
    params.set("project_id", project_id)
    params.set("page", String(page))
    params.set("per_page", String(per_page))
    const rtnval = RESOURCE_POOLS_API_PATH + "?" + params.toString()
    return rtnval
}

/**
 * Shorten an id (a UUID) to its first segment for compact display.
 *
 * @param value Full identifier.
 *
 * @returns A short, human-scannable id fragment.
 */
export function short_id(value: string): string {
    if (typeof value !== "string" || value.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const dash_index = value.indexOf("-")
    if (dash_index <= 0) {
        const rtnval = value
        return rtnval
    }
    const rtnval = value.slice(0, dash_index)
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
 * Parse a comma-separated capability-tags field into a trimmed,
 * de-duplicated, non-empty list.
 *
 * @param raw The raw comma-separated input value.
 *
 * @returns The parsed list of capability tags.
 */
export function parse_capability_tags(raw: string): string[] {
    const rtnval: string[] = []
    if (typeof raw !== "string" || raw.length === 0) {
        return rtnval
    }
    const parts = raw.split(",")
    for (const part of parts) {
        const trimmed = part.trim()
        if (trimmed.length === 0) {
            continue
        }
        if (rtnval.indexOf(trimmed) >= 0) {
            continue
        }
        rtnval.push(trimmed)
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
export function has_next_page(state: ResourcePoolsListState): boolean {
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
export function has_previous_page(state: ResourcePoolsListState): boolean {
    const rtnval = state.page > 1
    return rtnval
}

/**
 * The resource-pools list view Custom Element. Register it with
 * ``customElements.define("pyc-resource-pools", PycResourcePools)``.
 */
export class PycResourcePools extends HTMLElement {
    private _state: ResourcePoolsListState
    private _pools: ResourcePool[]
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null
    private _create_status: HTMLElement | null

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
        this._pools = []
        this._root = null
        this._table_region = null
        this._create_status = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the filter +
     * pagination state without scraping the DOM.
     */
    public get listState(): ResourcePoolsListState {
        const rtnval: ResourcePoolsListState = {
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
     * Lifecycle hook -- render the static chrome. A ``?project_id=``
     * query parameter seeds an immediate fetch; otherwise the view
     * shows a "pick a project" prompt.
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
        root.classList.add("pyc-resources")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-resources__heading")
        heading.textContent = "Resource pools"
        root.appendChild(heading)

        const subtitle = document.createElement("p")
        subtitle.classList.add("pyc-resources__subtitle")
        subtitle.textContent =
            "Resource pools are project-scoped. Enter a project id " +
            "to list its pools."
        root.appendChild(subtitle)

        const filters = document.createElement("div")
        filters.classList.add("pyc-resources__filters")

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-resources__filter")
        project_label.textContent = "Project"
        const project_input = document.createElement("input")
        project_input.classList.add("pyc-resources__input")
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
                this._pools = []
                this._state.total = 0
                this._render_table_region()
            }
        })
        project_label.appendChild(project_input)
        filters.appendChild(project_label)

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-resources__button")
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

        root.appendChild(this._build_create_form())

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-resources__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const pager = document.createElement("div")
        pager.classList.add("pyc-resources__pager")

        const prev_button = document.createElement("button")
        prev_button.classList.add("pyc-resources__button")
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
        page_indicator.classList.add("pyc-resources__page-indicator")
        page_indicator.setAttribute("data-role", "page-indicator")
        pager.appendChild(page_indicator)

        const next_button = document.createElement("button")
        next_button.classList.add("pyc-resources__button")
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

    private _build_create_form(): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-resources__create")
        section.setAttribute("data-role", "create-section")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-resources__section-heading")
        heading.textContent = "Create pool"
        section.appendChild(heading)

        const form = document.createElement("form")
        form.classList.add("pyc-resources__form")
        form.setAttribute("data-role", "create-form")

        const name_label = document.createElement("label")
        name_label.classList.add("pyc-resources__filter")
        name_label.textContent = "Name"
        const name_input = document.createElement("input")
        name_input.classList.add("pyc-resources__input")
        name_input.setAttribute("type", "text")
        name_input.setAttribute("placeholder", "pool name")
        name_input.setAttribute("data-role", "create-name")
        name_label.appendChild(name_input)
        form.appendChild(name_label)

        const desc_label = document.createElement("label")
        desc_label.classList.add("pyc-resources__filter")
        desc_label.textContent = "Description"
        const desc_input = document.createElement("input")
        desc_input.classList.add("pyc-resources__input")
        desc_input.setAttribute("type", "text")
        desc_input.setAttribute("placeholder", "optional")
        desc_input.setAttribute("data-role", "create-description")
        desc_label.appendChild(desc_input)
        form.appendChild(desc_label)

        const tags_label = document.createElement("label")
        tags_label.classList.add("pyc-resources__filter")
        tags_label.textContent = "Capability tags"
        const tags_input = document.createElement("input")
        tags_input.classList.add("pyc-resources__input")
        tags_input.setAttribute("type", "text")
        tags_input.setAttribute("placeholder", "comma-separated")
        tags_input.setAttribute("data-role", "create-tags")
        tags_label.appendChild(tags_input)
        form.appendChild(tags_label)

        const submit = document.createElement("button")
        submit.classList.add("pyc-resources__button")
        submit.setAttribute("type", "submit")
        submit.setAttribute("data-role", "create-submit")
        submit.textContent = "Create Pool"
        form.appendChild(submit)

        const status = document.createElement("p")
        status.classList.add("pyc-resources__form-status")
        status.setAttribute("data-role", "create-status")
        status.hidden = true
        this._create_status = status

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_create(
                name_input.value.trim(),
                desc_input.value.trim(),
                tags_input.value,
            )
        })

        section.appendChild(form)
        section.appendChild(status)
        return section
    }

    private async _submit_create(
            name: string,
            description: string,
            tags_raw: string,
        ): Promise<void> {
        if (this._state.projectFilter.length === 0) {
            this._show_create_status(
                "Enter a project id before creating a pool.",
                true,
            )
            return
        }
        if (name.length === 0) {
            this._show_create_status("A pool name is required.", true)
            return
        }
        const body: Record<string, unknown> = {
            project_id: this._state.projectFilter,
            name: name,
        }
        if (description.length > 0) {
            body["description"] = description
        }
        const tags = parse_capability_tags(tags_raw)
        if (tags.length > 0) {
            body["capability_tags"] = tags
        }
        try {
            const response = await fetch(RESOURCE_POOLS_API_PATH, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(body),
            })
            if (response.ok === false) {
                this._show_create_status(
                    "Create failed: HTTP " + String(response.status),
                    true,
                )
                return
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.resources.pool_create_failed",
                { reason: String(reason) },
            )
            this._show_create_status(
                "Create failed -- see the console for detail.",
                true,
            )
            return
        }
        this._show_create_status("Pool created.", false)
        this._state.page = 1
        await this._refresh()
        return
    }

    private _show_create_status(message: string, errored: boolean): void {
        if (this._create_status === null) {
            return
        }
        this._create_status.hidden = false
        this._create_status.textContent = message
        if (errored === true) {
            this._create_status.setAttribute("data-tone", "error")
        } else {
            this._create_status.setAttribute("data-tone", "ok")
        }
        return
    }

    /**
     * Fetch the project's resource pools and re-render the table
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

        const url = build_resource_pools_url(
            this._state.projectFilter,
            this._state.page,
            this._state.perPage,
        )
        let page: ResourcePoolPage | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "resource-pools fetch failed: HTTP " +
                        String(response.status),
                )
            }
            const body = await response.json()
            page = body as ResourcePoolPage
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.resources.pools_fetch_failed",
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

        this._pools = page.items
        if (page.meta !== null && page.meta !== undefined) {
            this._state.total = page.meta.total
            this._state.page = page.meta.page
        } else {
            this._state.total = page.items.length
        }
        this._state.loading = false
        this._state.errored = false
        this._render_table_region()
        return
    }

    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.needsProject === true) {
            const prompt = document.createElement("p")
            prompt.classList.add("pyc-resources__status")
            prompt.setAttribute("data-role", "needs-project")
            prompt.textContent =
                "Enter a project id above to list its resource pools."
            region.replaceChildren(prompt)
            this._render_pager()
            return
        }

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-resources__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading resource pools…"
            region.replaceChildren(loading)
            this._render_pager()
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-resources__status",
                "pyc-resources__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent =
                "Failed to load resource pools. Try refreshing."
            region.replaceChildren(error)
            this._render_pager()
            return
        }

        if (this._pools.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-resources__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No resource pools in this project"
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
        table.classList.add("pyc-resources__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = ["Pool", "Name", "Capabilities", "Members"]
        for (const column of columns) {
            const th = document.createElement("th")
            th.scope = "col"
            th.textContent = column
            head_row.appendChild(th)
        }
        thead.appendChild(head_row)
        table.appendChild(thead)

        const tbody = document.createElement("tbody")
        for (const pool of this._pools) {
            const row = document.createElement("tr")
            row.classList.add("pyc-resources__row")

            const id_cell = document.createElement("td")
            const link = document.createElement("a")
            link.classList.add("pyc-resources__link")
            const href = "/resource-pools/" + pool.pool_id +
                "?project_id=" + encodeURIComponent(pool.project_id)
            link.setAttribute("href", href)
            link.textContent = short_id(pool.pool_id)
            link.title = pool.pool_id
            id_cell.appendChild(link)
            row.appendChild(id_cell)

            const name_cell = document.createElement("td")
            name_cell.textContent =
                pool.name !== null && pool.name.length > 0
                    ? pool.name
                    : "—"
            row.appendChild(name_cell)

            const tags_cell = document.createElement("td")
            const tags = Array.isArray(pool.capability_tags) === true
                ? pool.capability_tags
                : []
            if (tags.length === 0) {
                tags_cell.textContent = "—"
            } else {
                for (const tag of tags) {
                    const chip = document.createElement("span")
                    chip.classList.add("pyc-resources__tag")
                    chip.textContent = tag
                    tags_cell.appendChild(chip)
                }
            }
            row.appendChild(tags_cell)

            const members_cell = document.createElement("td")
            members_cell.textContent = String(pool.member_count)
            row.appendChild(members_cell)

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
        const indicator =
            this._root.querySelector('[data-role="page-indicator"]')

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
