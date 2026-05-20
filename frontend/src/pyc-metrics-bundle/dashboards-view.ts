/**
 * ``<pyc-dashboards-list>`` + ``<pyc-dashboard-detail>`` -- the
 * dashboards list / detail views.
 *
 * ``<pyc-dashboards-list>`` renders a project selector, lists the
 * project's dashboards via
 * ``GET /api/v1/projects/{project_id}/dashboards``, and offers a
 * "Create Dashboard" form that POSTs a ``DashboardCreateRequest``.
 * Each row links to ``/dashboards/{dashboard_id}``.
 *
 * ``<pyc-dashboard-detail>`` reads a single dashboard via
 * ``GET …/dashboards/{dashboard_id}`` and renders its tiles. Each
 * tile references a metric (via its ``config``); the detail view
 * resolves the tile metric through the timeseries query and renders
 * an inline-SVG chart -- reusing the timeseries view's pure
 * projection helpers.
 *
 * Both elements are native Custom Elements -- no framework. They
 * call the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. They never write to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

import {
    build_chart_svg,
    build_timeseries_url,
    TimeseriesPoint,
    TimeseriesQuery,
} from "./timeseries-view.js"
import {
    extract_projects,
    MetricsProjectOption,
    short_metric_id,
} from "./test-metrics-view.js"

/**
 * Base path of the projects REST collection.
 */
const PROJECTS_API_PATH: string = "/api/v1/projects"

/**
 * Route prefix the dashboards list view owns.
 */
export const DASHBOARDS_ROUTE: string = "/dashboards"

/**
 * One placed metric tile within a dashboard -- a subset of
 * ``DashboardTile``.
 */
export interface DashboardTile {
    tile_id: string
    kind: string
    x: number
    y: number
    w: number
    h: number
    config?: Record<string, unknown>
}

/**
 * The ``Dashboard`` response shape -- a subset.
 */
export interface Dashboard {
    dashboard_id: string
    project_id: string
    name: string
    description?: string
    grid_columns_max?: number
    tiles: DashboardTile[]
    version: number
    created_at?: string
    updated_at?: string
}

/**
 * The current project + load state of the dashboards list view.
 */
export interface DashboardsListState {
    projectId: string
    loading: boolean
    errored: boolean
}

/**
 * Outcome of a create-dashboard POST, surfaced to callers / tests.
 */
export interface DashboardCreateOutcome {
    ok: boolean
    status: number
    dashboardId: string
    message: string
}

/**
 * Build the ``…/projects/{project_id}/dashboards`` collection URL.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_dashboards_collection_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/dashboards"
    return rtnval
}

/**
 * Build the ``…/projects/{project_id}/dashboards/{dashboard_id}``
 * detail URL.
 *
 * @param project_id Project identifier.
 * @param dashboard_id Dashboard identifier.
 *
 * @returns A relative URL string.
 */
export function build_dashboard_detail_url(
    project_id: string,
    dashboard_id: string,
): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/dashboards/" +
        encodeURIComponent(dashboard_id)
    return rtnval
}

/**
 * Extract a ``{dashboard_id}`` from a ``/dashboards/{id}`` path.
 * Returns an empty string when the path is not a dashboard-detail
 * path. Tolerates an optional trailing slash and query string.
 *
 * @param path A request path.
 *
 * @returns The dashboard id, or an empty string.
 */
export function dashboard_id_from_path(path: string): string {
    if (typeof path !== "string") {
        const rtnval = ""
        return rtnval
    }
    let working = path
    const query_index = working.indexOf("?")
    if (query_index >= 0) {
        working = working.slice(0, query_index)
    }
    if (working.endsWith("/") === true) {
        working = working.slice(0, working.length - 1)
    }
    const prefix = DASHBOARDS_ROUTE + "/"
    if (working.startsWith(prefix) === false) {
        const rtnval = ""
        return rtnval
    }
    const remainder = working.slice(prefix.length)
    if (remainder.length === 0 || remainder.indexOf("/") >= 0) {
        const rtnval = ""
        return rtnval
    }
    const rtnval = decodeURIComponent(remainder)
    return rtnval
}

/**
 * Translate a create-dashboard HTTP response status into the
 * operator guidance message the notice surfaces.
 *
 * @param status HTTP status code of the create response.
 *
 * @returns A human-readable message.
 */
export function create_message_for_status(status: number): string {
    if (status === 201 || status === 200) {
        const rtnval = "Dashboard created."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "A dashboard with that name already exists."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "The dashboard request was rejected — check the name."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to create dashboards."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown project."
        return rtnval
    }
    const rtnval =
        "Failed to create dashboard (HTTP " + String(status) + ")."
    return rtnval
}

/**
 * Resolve the metric name a dashboard tile references. The tile
 * ``config`` carries a ``metric`` key by convention; an unset /
 * non-string value yields an empty string.
 *
 * @param tile A dashboard tile.
 *
 * @returns The referenced metric name, or an empty string.
 */
export function tile_metric_name(tile: DashboardTile): string {
    if (tile === null || tile === undefined) {
        const rtnval = ""
        return rtnval
    }
    const config = tile.config
    if (config === null || config === undefined || typeof config !== "object") {
        const rtnval = ""
        return rtnval
    }
    const metric = (config as Record<string, unknown>).metric
    if (typeof metric !== "string") {
        const rtnval = ""
        return rtnval
    }
    const rtnval = metric
    return rtnval
}

/**
 * The dashboards list view Custom Element. Register it with
 * ``customElements.define("pyc-dashboards-list", ...)``.
 */
export class PycDashboardsList extends HTMLElement {
    private _state: DashboardsListState
    private _projects: MetricsProjectOption[]
    private _projectsAvailable: boolean
    private _dashboards: Dashboard[]
    private _root: HTMLElement | null
    private _form_region: HTMLElement | null
    private _table_region: HTMLElement | null
    private _notice_region: HTMLElement | null

    public constructor() {
        super()
        this._state = {
            projectId: "",
            loading: false,
            errored: false,
        }
        this._projects = []
        this._projectsAvailable = false
        this._dashboards = []
        this._root = null
        this._form_region = null
        this._table_region = null
        this._notice_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * project + load state without scraping the DOM.
     */
    public get listState(): DashboardsListState {
        const rtnval = {
            projectId: this._state.projectId,
            loading: this._state.loading,
            errored: this._state.errored,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- render the chrome, kick off the project
     * fetch.
     */
    public connectedCallback(): void {
        this._render_chrome()
        void this._load_projects()
        return
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-metrics")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-metrics__heading")
        heading.textContent = "Dashboards"
        root.appendChild(heading)

        const controls = document.createElement("div")
        controls.classList.add("pyc-metrics__controls")

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-metrics__field")
        project_label.textContent = "Project"
        const project_select = document.createElement("select")
        project_select.classList.add("pyc-metrics__select")
        project_select.setAttribute("data-role", "project-select")
        project_select.addEventListener("change", () => {
            this._state.projectId = project_select.value
            void this._refresh()
        })
        project_label.appendChild(project_select)
        controls.appendChild(project_label)

        const project_input = document.createElement("input")
        project_input.classList.add("pyc-metrics__input")
        project_input.setAttribute("type", "text")
        project_input.setAttribute("placeholder", "project id")
        project_input.setAttribute("data-role", "project-input")
        project_input.hidden = true
        project_input.addEventListener("change", () => {
            this._state.projectId = project_input.value.trim()
            void this._refresh()
        })
        controls.appendChild(project_input)

        const create_button = document.createElement("button")
        create_button.classList.add("pyc-metrics__button")
        create_button.setAttribute("type", "button")
        create_button.setAttribute("data-role", "create-toggle")
        create_button.textContent = "Create Dashboard"
        create_button.addEventListener("click", () => {
            this._toggle_create_form()
        })
        controls.appendChild(create_button)

        root.appendChild(controls)

        const form_region = document.createElement("div")
        form_region.classList.add("pyc-metrics__form-region")
        form_region.setAttribute("data-role", "form-region")
        form_region.hidden = true
        root.appendChild(form_region)
        this._form_region = form_region

        const notice_region = document.createElement("div")
        notice_region.classList.add("pyc-metrics__notice-region")
        notice_region.setAttribute("data-role", "notice-region")
        root.appendChild(notice_region)
        this._notice_region = notice_region

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-metrics__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Fetch the projects collection and populate the selector.
     * Exposed so unit tests can await the bootstrap fetch cycle.
     */
    public async loadProjects(): Promise<void> {
        await this._load_projects()
        return
    }

    private async _load_projects(): Promise<void> {
        let projects: MetricsProjectOption[] | null = null
        try {
            const response = await fetch(PROJECTS_API_PATH, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                projects = extract_projects(body)
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.projects_fetch_failed",
                { reason: String(reason) },
            )
        }

        if (projects !== null && projects.length > 0) {
            this._projects = projects
            this._projectsAvailable = true
            this._state.projectId = projects[0].project_id
        } else {
            this._projects = []
            this._projectsAvailable = false
        }
        this._render_project_control()
        if (this._state.projectId.length > 0) {
            await this._refresh()
        } else {
            this._render_table()
        }
        return
    }

    private _render_project_control(): void {
        if (this._root === null) {
            return
        }
        const select = this._root.querySelector('[data-role="project-select"]')
        const input = this._root.querySelector('[data-role="project-input"]')
        if (
            select instanceof HTMLSelectElement === false ||
            input instanceof HTMLInputElement === false
        ) {
            return
        }
        const select_el = select as HTMLSelectElement
        const input_el = input as HTMLInputElement

        if (this._projectsAvailable === true) {
            select_el.hidden = false
            input_el.hidden = true
            select_el.replaceChildren()
            for (const project of this._projects) {
                const option = document.createElement("option")
                option.value = project.project_id
                option.textContent = project.display_name
                select_el.appendChild(option)
            }
            select_el.value = this._state.projectId
        } else {
            select_el.hidden = true
            input_el.hidden = false
        }
        return
    }

    /**
     * Re-fetch the dashboards page for the current project and
     * re-render. Exposed so unit tests can await a render cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.projectId.length === 0) {
            this._render_table()
            return
        }
        this._state.loading = true
        this._state.errored = false
        this._render_table()

        let dashboards: Dashboard[] = []
        let errored = false
        try {
            const url = build_dashboards_collection_url(
                this._state.projectId,
            )
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                dashboards = extract_dashboards(body)
            } else {
                errored = true
            }
        } catch (reason: unknown) {
            errored = true
            console.warn(
                "pychestrate.ui.metrics.dashboards_fetch_failed",
                { reason: String(reason) },
            )
        }

        this._state.loading = false
        this._state.errored = errored
        this._dashboards = dashboards
        this._render_table()
        return
    }

    private _render_table(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region
        region.replaceChildren()

        if (this._state.projectId.length === 0) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.textContent = "Select a project to view dashboards."
            region.appendChild(notice)
            return
        }
        if (this._state.loading === true) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.textContent = "Loading dashboards…"
            region.appendChild(notice)
            return
        }
        if (this._state.errored === true) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.classList.add("pyc-metrics__notice--error")
            notice.textContent = "Failed to load dashboards for this project."
            region.appendChild(notice)
            return
        }
        if (this._dashboards.length === 0) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.textContent = "No dashboards yet — create one above."
            region.appendChild(notice)
            return
        }

        const table = document.createElement("table")
        table.classList.add("pyc-metrics__table")
        table.setAttribute("data-role", "dashboards-table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        for (const text of ["Name", "Description", "Tiles", "Version"]) {
            const th = document.createElement("th")
            th.textContent = text
            head_row.appendChild(th)
        }
        thead.appendChild(head_row)
        table.appendChild(thead)

        const tbody = document.createElement("tbody")
        for (const dashboard of this._dashboards) {
            const row = document.createElement("tr")

            const name_cell = document.createElement("td")
            const link = document.createElement("a")
            link.classList.add("pyc-metrics__row-link")
            link.setAttribute(
                "href",
                DASHBOARDS_ROUTE + "/" +
                    encodeURIComponent(dashboard.dashboard_id),
            )
            link.textContent = dashboard.name
            name_cell.appendChild(link)
            row.appendChild(name_cell)

            const desc_cell = document.createElement("td")
            desc_cell.textContent =
                dashboard.description !== undefined &&
                dashboard.description.length > 0
                    ? dashboard.description
                    : "—"
            row.appendChild(desc_cell)

            const tiles_cell = document.createElement("td")
            tiles_cell.textContent = String(dashboard.tiles.length)
            row.appendChild(tiles_cell)

            const version_cell = document.createElement("td")
            version_cell.textContent = String(dashboard.version)
            row.appendChild(version_cell)

            tbody.appendChild(row)
        }
        table.appendChild(tbody)
        region.appendChild(table)
        return
    }

    private _toggle_create_form(): void {
        if (this._form_region === null) {
            return
        }
        if (this._form_region.hidden === false) {
            this._form_region.hidden = true
            this._form_region.replaceChildren()
            return
        }
        this._form_region.hidden = false
        this._render_create_form()
        return
    }

    private _render_create_form(): void {
        if (this._form_region === null) {
            return
        }
        const region = this._form_region
        region.replaceChildren()

        const form = document.createElement("form")
        form.classList.add("pyc-metrics__form")
        form.setAttribute("data-role", "create-form")

        const name_label = document.createElement("label")
        name_label.classList.add("pyc-metrics__field")
        name_label.textContent = "Name"
        const name_input = document.createElement("input")
        name_input.classList.add("pyc-metrics__input")
        name_input.setAttribute("type", "text")
        name_input.setAttribute("data-role", "name-input")
        name_input.required = true
        name_label.appendChild(name_input)
        form.appendChild(name_label)

        const desc_label = document.createElement("label")
        desc_label.classList.add("pyc-metrics__field")
        desc_label.textContent = "Description"
        const desc_input = document.createElement("input")
        desc_input.classList.add("pyc-metrics__input")
        desc_input.setAttribute("type", "text")
        desc_input.setAttribute("data-role", "description-input")
        desc_label.appendChild(desc_input)
        form.appendChild(desc_label)

        const submit = document.createElement("button")
        submit.classList.add("pyc-metrics__button")
        submit.setAttribute("type", "submit")
        submit.setAttribute("data-role", "create-submit")
        submit.textContent = "Create"
        form.appendChild(submit)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_create(
                name_input.value.trim(),
                desc_input.value.trim(),
            )
        })

        region.appendChild(form)
        return
    }

    /**
     * POST a ``DashboardCreateRequest`` for the current project.
     * Exposed so unit tests can drive the create path directly.
     *
     * @param name The dashboard name.
     * @param description An optional description.
     *
     * @returns The create outcome.
     */
    public async submitCreate(
        name: string,
        description: string,
    ): Promise<DashboardCreateOutcome> {
        const rtnval = await this._submit_create(name, description)
        return rtnval
    }

    private async _submit_create(
        name: string,
        description: string,
    ): Promise<DashboardCreateOutcome> {
        if (this._state.projectId.length === 0 || name.length === 0) {
            const rtnval: DashboardCreateOutcome = {
                ok: false,
                status: 0,
                dashboardId: "",
                message: "A project and a dashboard name are required.",
            }
            this._render_notice(rtnval.message, true)
            return rtnval
        }
        const payload: Record<string, unknown> = { name: name }
        if (description.length > 0) {
            payload.description = description
        }
        let status = 0
        let dashboard_id = ""
        let ok = false
        try {
            const url = build_dashboards_collection_url(
                this._state.projectId,
            )
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            })
            status = response.status
            ok = response.ok
            if (response.ok === true) {
                const body = await response.json()
                const record = body as { dashboard_id?: unknown }
                if (typeof record.dashboard_id === "string") {
                    dashboard_id = record.dashboard_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.dashboard_create_failed",
                { reason: String(reason) },
            )
        }
        const message = create_message_for_status(status)
        const rtnval: DashboardCreateOutcome = {
            ok: ok,
            status: status,
            dashboardId: dashboard_id,
            message: message,
        }
        this._render_notice(message, ok === false)
        if (ok === true) {
            this._toggle_create_form()
            await this._refresh()
        }
        return rtnval
    }

    private _render_notice(message: string, is_error: boolean): void {
        if (this._notice_region === null) {
            return
        }
        const notice = document.createElement("div")
        notice.classList.add("pyc-metrics__notice")
        if (is_error === true) {
            notice.classList.add("pyc-metrics__notice--error")
        }
        notice.textContent = message
        this._notice_region.replaceChildren(notice)
        return
    }
}

/**
 * The dashboard detail view Custom Element. Register it with
 * ``customElements.define("pyc-dashboard-detail", ...)``.
 */
export class PycDashboardDetail extends HTMLElement {
    private _projects: MetricsProjectOption[]
    private _dashboard: Dashboard | null
    private _loading: boolean
    private _errored: boolean
    private _root: HTMLElement | null
    private _tiles_region: HTMLElement | null

    public constructor() {
        super()
        this._projects = []
        this._dashboard = null
        this._loading = false
        this._errored = false
        this._root = null
        this._tiles_region = null
    }

    /**
     * Diagnostic accessor used by unit tests.
     */
    public get loaded(): boolean {
        const rtnval = this._dashboard !== null
        return rtnval
    }

    /**
     * Lifecycle hook -- render the chrome, kick off the dashboard
     * fetch.
     */
    public connectedCallback(): void {
        this._render_chrome()
        void this._load_dashboard()
        return
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-metrics")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-metrics__heading")
        heading.setAttribute("data-role", "dashboard-heading")
        heading.textContent = "Dashboard"
        root.appendChild(heading)

        const back = document.createElement("a")
        back.classList.add("pyc-metrics__row-link")
        back.setAttribute("href", DASHBOARDS_ROUTE)
        back.textContent = "← All dashboards"
        root.appendChild(back)

        const tiles_region = document.createElement("div")
        tiles_region.classList.add("pyc-metrics__tiles-region")
        tiles_region.setAttribute("data-role", "tiles-region")
        root.appendChild(tiles_region)
        this._tiles_region = tiles_region

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Resolve the dashboard project + id, fetch the dashboard, and
     * render its tiles. Exposed so unit tests can await the cycle.
     */
    public async loadDashboard(): Promise<void> {
        await this._load_dashboard()
        return
    }

    private async _load_dashboard(): Promise<void> {
        const dashboard_id = dashboard_id_from_path(
            typeof window !== "undefined" ? window.location.pathname : "",
        )
        if (dashboard_id.length === 0) {
            this._errored = true
            this._render_tiles()
            return
        }

        // The dashboard endpoint is project-scoped; resolve a
        // project to scope the read. The detail page is reached
        // from the list, so the first project is the common case.
        let project_id = ""
        try {
            const response = await fetch(PROJECTS_API_PATH, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                this._projects = extract_projects(body)
                if (this._projects.length > 0) {
                    project_id = this._projects[0].project_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.projects_fetch_failed",
                { reason: String(reason) },
            )
        }

        if (project_id.length === 0) {
            this._errored = true
            this._render_tiles()
            return
        }

        this._loading = true
        this._render_tiles()

        let dashboard: Dashboard | null = null
        let errored = false
        try {
            const url = build_dashboard_detail_url(project_id, dashboard_id)
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                dashboard = body as Dashboard
            } else {
                errored = true
            }
        } catch (reason: unknown) {
            errored = true
            console.warn(
                "pychestrate.ui.metrics.dashboard_fetch_failed",
                { reason: String(reason) },
            )
        }

        this._loading = false
        this._errored = errored
        this._dashboard = dashboard
        this._render_tiles()
        return
    }

    private _render_tiles(): void {
        if (this._tiles_region === null || this._root === null) {
            return
        }
        const heading = this._root.querySelector(
            '[data-role="dashboard-heading"]',
        )
        if (heading !== null && this._dashboard !== null) {
            heading.textContent = this._dashboard.name
        }

        const region = this._tiles_region
        region.replaceChildren()

        if (this._loading === true) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.textContent = "Loading dashboard…"
            region.appendChild(notice)
            return
        }
        if (this._errored === true || this._dashboard === null) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.classList.add("pyc-metrics__notice--error")
            notice.textContent = "Failed to load this dashboard."
            region.appendChild(notice)
            return
        }
        if (this._dashboard.tiles.length === 0) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.textContent = "This dashboard has no tiles."
            region.appendChild(notice)
            return
        }

        const grid = document.createElement("div")
        grid.classList.add("pyc-metrics__tiles")
        grid.setAttribute("data-role", "tiles-grid")
        for (const tile of this._dashboard.tiles) {
            grid.appendChild(this._build_tile(tile))
        }
        region.appendChild(grid)
        return
    }

    private _build_tile(tile: DashboardTile): HTMLElement {
        const card = document.createElement("div")
        card.classList.add("pyc-metrics__tile")
        card.setAttribute("data-role", "dashboard-tile")
        card.setAttribute("data-tile-id", tile.tile_id)

        const title = document.createElement("div")
        title.classList.add("pyc-metrics__tile-title")
        const metric_name = tile_metric_name(tile)
        title.textContent =
            metric_name.length > 0 ? metric_name : tile.kind
        card.appendChild(title)

        const body = document.createElement("div")
        body.classList.add("pyc-metrics__tile-body")
        body.setAttribute("data-role", "tile-body")
        const placeholder = document.createElement("div")
        placeholder.classList.add("pyc-metrics__notice")
        placeholder.textContent =
            metric_name.length > 0 ? "Loading metric…" : "No metric configured."
        body.appendChild(placeholder)
        card.appendChild(body)

        if (metric_name.length > 0) {
            void this._load_tile_metric(metric_name, body)
        }
        return card
    }

    private async _load_tile_metric(
        metric_name: string,
        body: HTMLElement,
    ): Promise<void> {
        let points: TimeseriesPoint[] = []
        let errored = false
        try {
            const url = build_timeseries_url(metric_name, "7d", new Date())
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const data = await response.json()
                const query = data as TimeseriesQuery
                if (Array.isArray(query.points) === true) {
                    points = query.points
                }
            } else {
                errored = true
            }
        } catch (reason: unknown) {
            errored = true
            console.warn(
                "pychestrate.ui.metrics.tile_metric_fetch_failed",
                { reason: String(reason) },
            )
        }

        body.replaceChildren()
        if (errored === true) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.classList.add("pyc-metrics__notice--error")
            notice.textContent = "Failed to load tile metric."
            body.appendChild(notice)
            return
        }
        if (points.length === 0) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.textContent = "No data points."
            body.appendChild(notice)
            return
        }
        body.appendChild(build_chart_svg(points))
        return
    }
}

/**
 * Normalise a dashboards-page response body into ``Dashboard``
 * records. Accepts both a bare array and a ``{items}`` envelope.
 *
 * @param body Parsed JSON response body.
 *
 * @returns A list of dashboards (possibly empty).
 */
export function extract_dashboards(body: unknown): Dashboard[] {
    let raw: unknown[] = []
    if (Array.isArray(body) === true) {
        raw = body as unknown[]
    } else if (body !== null && typeof body === "object") {
        const items = (body as { items?: unknown }).items
        if (Array.isArray(items) === true) {
            raw = items as unknown[]
        }
    }
    const rtnval: Dashboard[] = []
    for (const item of raw) {
        if (item === null || typeof item !== "object") {
            continue
        }
        const record = item as Record<string, unknown>
        const dashboard_id = record.dashboard_id
        if (
            typeof dashboard_id !== "string" ||
            dashboard_id.length === 0
        ) {
            continue
        }
        let tiles: DashboardTile[] = []
        if (Array.isArray(record.tiles) === true) {
            tiles = (record.tiles as unknown[]).filter(
                (value) => value !== null && typeof value === "object",
            ) as DashboardTile[]
        }
        const dashboard: Dashboard = {
            dashboard_id: dashboard_id,
            project_id:
                typeof record.project_id === "string"
                    ? record.project_id
                    : "",
            name: typeof record.name === "string" ? record.name : "",
            tiles: tiles,
            version:
                typeof record.version === "number" ? record.version : 1,
        }
        if (typeof record.description === "string") {
            dashboard.description = record.description
        }
        rtnval.push(dashboard)
    }
    return rtnval
}

export { short_metric_id }
