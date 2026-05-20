/**
 * ``<pyc-builds-list>`` -- the build-runs list view Custom Element.
 *
 * On mount the element renders a project selector, then on a
 * project selection fetches that project's build runs via
 * ``GET /api/v1/projects/{project_id}/builds`` and renders a
 * paginated table. Each row links to ``/builds/{build_id}`` -- the
 * build-detail page.
 *
 * The view also surfaces a "Trigger Build" action: an inline form
 * that picks a source integration + runner kind + free-form runner
 * inputs, then POSTs a ``BuildRunCreateRequest`` to
 * ``…/projects/{project_id}/builds``. On success it surfaces a
 * toast linking to the new build's detail page.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state lives in instance fields.
 *
 * Project listing: the REST surface does not (yet) publish a
 * ``GET /api/v1/projects`` collection consumed everywhere, so when
 * that endpoint is unavailable the selector gracefully degrades to
 * a manual project-id text input -- mirroring the catalog bundle.
 */

/**
 * The ``BuildRun`` lifecycle states from
 * ``specs/openapi/pychestrate.yaml``.
 */
export const BUILD_STATES: readonly string[] = [
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
]

/**
 * ``BuildRun`` states the server treats as terminal -- no further
 * lifecycle transitions occur once a build reaches one of these.
 */
export const TERMINAL_BUILD_STATES: readonly string[] = [
    "completed",
    "failed",
    "cancelled",
]

/**
 * One toolchain snapshot row attached to a ``BuildRun``.
 */
export interface BuildToolchainSnapshot {
    key: string
    version?: string | null
    fingerprint_sha256?: string | null
}

/**
 * One build run, as returned in the ``items`` array of
 * ``BuildRunPage``. Only the fields the views render are typed
 * here. Note the API names the identifier ``run_id`` even though
 * the route path segment is ``build_id``.
 */
export interface BuildRun {
    run_id: string
    project_id: string
    runner_kind: string
    repro_digest_sha256: string
    state: string
    layer5_run_id?: string | null
    actor_id?: string | null
    started_at?: string | null
    finished_at?: string | null
    final_state_reason?: string | null
    inputs?: Record<string, unknown> | null
    annotations?: Record<string, unknown> | null
    toolchain?: BuildToolchainSnapshot[] | null
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
 * The ``BuildRunPage`` response shape -- a page of builds + meta.
 */
export interface BuildRunPage {
    items: BuildRun[]
    meta: PageMeta
}

/**
 * One source integration, as the trigger form's selector consumes
 * it. Mirrors the subset of ``SourceIntegration`` the form needs.
 */
export interface SourceIntegrationOption {
    integration_id: string
    project_id: string
    provider_name: string
    repo_key: string
}

/**
 * One project, as the project selector consumes it.
 */
export interface ProjectOption {
    project_id: string
    display_name: string
}

/**
 * Outcome of a trigger-build POST, surfaced to the caller / tests.
 */
export interface TriggerOutcome {
    ok: boolean
    status: number
    buildId: string
    message: string
}

/**
 * The current project + pagination state of the builds list view.
 * Exposed so unit tests can assert state transitions without
 * rendering.
 */
export interface BuildsListState {
    projectId: string
    stateFilter: string
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
 * Base path of the projects REST collection.
 */
const PROJECTS_API_PATH: string = "/api/v1/projects"

/**
 * Build the ``GET …/projects/{project_id}/builds`` query URL from
 * the supplied project id, state filter, and pagination state.
 *
 * @param state Current builds list state.
 *
 * @returns A relative URL string including the query string.
 */
export function build_builds_query_url(state: BuildsListState): string {
    const params = new URLSearchParams()
    if (state.stateFilter.length > 0) {
        params.set("state", state.stateFilter)
    }
    params.set("page", String(state.page))
    params.set("per_page", String(state.perPage))
    const query = params.toString()
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(state.projectId) + "/builds?" + query
    return rtnval
}

/**
 * Build the ``POST …/projects/{project_id}/builds`` URL used by
 * the trigger-build action.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_builds_collection_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/builds"
    return rtnval
}

/**
 * Build the ``GET …/projects/{project_id}/source-integrations``
 * URL the trigger form consults to populate its selector.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_source_integrations_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/source-integrations"
    return rtnval
}

/**
 * Shorten an id (a UUID or a sha digest) to its leading segment
 * for compact table display.
 *
 * @param value Full identifier or digest string.
 *
 * @returns A short, human-scannable fragment.
 */
export function short_id(value: string): string {
    if (typeof value !== "string" || value.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const dash_index = value.indexOf("-")
    if (dash_index > 0) {
        const rtnval = value.slice(0, dash_index)
        return rtnval
    }
    if (value.length > 12) {
        const rtnval = value.slice(0, 12)
        return rtnval
    }
    const rtnval = value
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
 * Classify a build state into a coarse badge tone so the CSS can
 * pick a token-driven color without hardcoding per-state classes.
 *
 * @param build_state One of the ``BuildRun`` state enum values.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function build_state_tone(build_state: string): string {
    if (build_state === "completed") {
        const rtnval = "ok"
        return rtnval
    }
    if (build_state === "failed") {
        const rtnval = "error"
        return rtnval
    }
    if (build_state === "cancelled") {
        const rtnval = "warn"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Decide whether a build state is terminal.
 *
 * @param build_state One of the ``BuildRun`` state enum values.
 *
 * @returns True when the state is terminal.
 */
export function is_terminal_build_state(build_state: string): boolean {
    const rtnval = TERMINAL_BUILD_STATES.indexOf(build_state) >= 0
    return rtnval
}

/**
 * Compute whether a "next page" control should be enabled given
 * the current page, page size, and known total.
 *
 * @param state Current builds list state.
 *
 * @returns True when a further page of results exists.
 */
export function has_next_page(state: BuildsListState): boolean {
    const consumed = state.page * state.perPage
    const rtnval = consumed < state.total
    return rtnval
}

/**
 * Compute whether a "previous page" control should be enabled.
 *
 * @param state Current builds list state.
 *
 * @returns True when the caller is not on the first page.
 */
export function has_previous_page(state: BuildsListState): boolean {
    const rtnval = state.page > 1
    return rtnval
}

/**
 * Translate a trigger-build HTTP response status into the operator
 * guidance message the toast surfaces.
 *
 * @param status HTTP status code of the trigger-build response.
 *
 * @returns A human-readable message for the toast / notice.
 */
export function trigger_message_for_status(status: number): string {
    if (status === 202 || status === 200 || status === 201) {
        const rtnval = "Build triggered."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "Runner inputs were rejected — check the runner kind."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown project or runner kind."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to trigger builds."
        return rtnval
    }
    const rtnval = "Failed to trigger build (HTTP " + String(status) + ")."
    return rtnval
}

/**
 * Parse the runner-inputs textarea content as JSON. An empty
 * string yields an empty object; malformed JSON throws.
 *
 * @param raw Raw textarea content.
 *
 * @returns A parsed inputs object.
 * @raises SyntaxError when ``raw`` is not valid JSON.
 */
export function parse_runner_inputs(raw: string): Record<string, unknown> {
    if (typeof raw !== "string" || raw.trim().length === 0) {
        const rtnval: Record<string, unknown> = {}
        return rtnval
    }
    const parsed = JSON.parse(raw)
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
        throw new SyntaxError("runner inputs must be a JSON object")
    }
    const rtnval = parsed as Record<string, unknown>
    return rtnval
}

/**
 * The builds list view Custom Element. Register it with
 * ``customElements.define("pyc-builds-list", PycBuildsList)``.
 */
export class PycBuildsList extends HTMLElement {
    private _state: BuildsListState
    private _builds: BuildRun[]
    private _projects: ProjectOption[]
    private _projectsAvailable: boolean
    private _integrations: SourceIntegrationOption[]
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null
    private _trigger_region: HTMLElement | null
    private _toast_region: HTMLElement | null

    public constructor() {
        super()
        this._state = {
            projectId: "",
            stateFilter: "",
            page: 1,
            perPage: DEFAULT_PER_PAGE,
            total: 0,
            loading: false,
            errored: false,
        }
        this._builds = []
        this._projects = []
        this._projectsAvailable = false
        this._integrations = []
        this._root = null
        this._table_region = null
        this._trigger_region = null
        this._toast_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * project + pagination state without scraping the DOM.
     */
    public get listState(): BuildsListState {
        const rtnval = {
            projectId: this._state.projectId,
            stateFilter: this._state.stateFilter,
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
     * project list fetch when the element is inserted.
     */
    public connectedCallback(): void {
        this._render_chrome()
        void this._load_projects()
        return
    }

    /**
     * Build the persistent chrome -- heading, project selector,
     * state filter, trigger action, table region, pager, toast.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-builds")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-builds__heading")
        heading.textContent = "Builds"
        root.appendChild(heading)

        const controls = document.createElement("div")
        controls.classList.add("pyc-builds__controls")

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-builds__field")
        project_label.textContent = "Project"
        const project_select = document.createElement("select")
        project_select.classList.add("pyc-builds__select")
        project_select.setAttribute("data-role", "project-select")
        project_select.addEventListener("change", () => {
            this._state.projectId = project_select.value
            this._state.page = 1
            void this._on_project_changed()
        })
        project_label.appendChild(project_select)
        controls.appendChild(project_label)

        const project_input = document.createElement("input")
        project_input.classList.add("pyc-builds__input")
        project_input.setAttribute("type", "text")
        project_input.setAttribute("placeholder", "project id")
        project_input.setAttribute("data-role", "project-input")
        project_input.hidden = true
        project_input.addEventListener("change", () => {
            this._state.projectId = project_input.value.trim()
            this._state.page = 1
            void this._on_project_changed()
        })
        controls.appendChild(project_input)

        const state_label = document.createElement("label")
        state_label.classList.add("pyc-builds__field")
        state_label.textContent = "State"
        const state_select = document.createElement("select")
        state_select.classList.add("pyc-builds__select")
        state_select.setAttribute("data-role", "state-filter")
        const any_option = document.createElement("option")
        any_option.value = ""
        any_option.textContent = "All states"
        state_select.appendChild(any_option)
        for (const build_state of BUILD_STATES) {
            const option = document.createElement("option")
            option.value = build_state
            option.textContent = build_state
            state_select.appendChild(option)
        }
        state_select.addEventListener("change", () => {
            this._state.stateFilter = state_select.value
            this._state.page = 1
            void this._refresh()
        })
        state_label.appendChild(state_select)
        controls.appendChild(state_label)

        const trigger_button = document.createElement("button")
        trigger_button.classList.add("pyc-builds__button")
        trigger_button.setAttribute("type", "button")
        trigger_button.setAttribute("data-role", "trigger-toggle")
        trigger_button.textContent = "Trigger Build"
        trigger_button.addEventListener("click", () => {
            this._toggle_trigger_form()
        })
        controls.appendChild(trigger_button)

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-builds__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            void this._refresh()
        })
        controls.appendChild(refresh_button)

        root.appendChild(controls)

        const trigger_region = document.createElement("div")
        trigger_region.classList.add("pyc-builds__trigger-region")
        trigger_region.setAttribute("data-role", "trigger-region")
        trigger_region.hidden = true
        root.appendChild(trigger_region)
        this._trigger_region = trigger_region

        const toast_region = document.createElement("div")
        toast_region.classList.add("pyc-builds__toast-region")
        toast_region.setAttribute("data-role", "toast-region")
        root.appendChild(toast_region)
        this._toast_region = toast_region

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-builds__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const pager = document.createElement("div")
        pager.classList.add("pyc-builds__pager")

        const prev_button = document.createElement("button")
        prev_button.classList.add("pyc-builds__button")
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
        page_indicator.classList.add("pyc-builds__page-indicator")
        page_indicator.setAttribute("data-role", "page-indicator")
        pager.appendChild(page_indicator)

        const next_button = document.createElement("button")
        next_button.classList.add("pyc-builds__button")
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
     * Fetch the projects collection and populate the selector.
     * Exposed so unit tests can await the bootstrap fetch cycle.
     */
    public async loadProjects(): Promise<void> {
        await this._load_projects()
        return
    }

    private async _load_projects(): Promise<void> {
        let projects: ProjectOption[] | null = null
        try {
            const response = await fetch(PROJECTS_API_PATH, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                projects = this._extract_projects(body)
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.builds.projects_fetch_failed",
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
            await this._on_project_changed()
        } else {
            this._render_table_region()
        }
        return
    }

    /**
     * Normalise a projects-list response body into ``ProjectOption``
     * records. Accepts both a bare array and a ``{items}`` page
     * envelope so the view tolerates either shape.
     *
     * @param body Parsed JSON response body.
     *
     * @returns A list of project options (possibly empty).
     */
    private _extract_projects(body: unknown): ProjectOption[] {
        let raw: unknown[] = []
        if (Array.isArray(body) === true) {
            raw = body as unknown[]
        } else if (body !== null && typeof body === "object") {
            const items = (body as { items?: unknown }).items
            if (Array.isArray(items) === true) {
                raw = items as unknown[]
            }
        }
        const rtnval: ProjectOption[] = []
        for (const item of raw) {
            if (item === null || typeof item !== "object") {
                continue
            }
            const record = item as Record<string, unknown>
            const project_id = record.project_id
            if (typeof project_id !== "string" || project_id.length === 0) {
                continue
            }
            const display = record.display_name
            const display_name = typeof display === "string" && display.length > 0
                ? display
                : project_id
            rtnval.push({ project_id: project_id, display_name: display_name })
        }
        return rtnval
    }

    /**
     * Render the project-select control or, when no projects
     * collection is available, swap to the manual text input.
     */
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
     * React to a project change -- reload the source integrations
     * (so the trigger form's selector is fresh) and the builds
     * page.
     */
    private async _on_project_changed(): Promise<void> {
        await this._load_integrations()
        await this._refresh()
        return
    }

    /**
     * Fetch the active project's source integrations. A failed
     * fetch leaves the integrations list empty -- the trigger form
     * degrades to a manual integration-id-free flow.
     */
    private async _load_integrations(): Promise<void> {
        this._integrations = []
        if (this._state.projectId.length === 0) {
            return
        }
        try {
            const url = build_source_integrations_url(this._state.projectId)
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                this._integrations = this._extract_integrations(body)
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.builds.integrations_fetch_failed",
                { reason: String(reason) },
            )
        }
        return
    }

    /**
     * Normalise a source-integrations page body into option
     * records.
     *
     * @param body Parsed JSON response body.
     *
     * @returns A list of source integration options.
     */
    private _extract_integrations(body: unknown): SourceIntegrationOption[] {
        let raw: unknown[] = []
        if (body !== null && typeof body === "object") {
            const items = (body as { items?: unknown }).items
            if (Array.isArray(items) === true) {
                raw = items as unknown[]
            }
        }
        const rtnval: SourceIntegrationOption[] = []
        for (const item of raw) {
            if (item === null || typeof item !== "object") {
                continue
            }
            const record = item as Record<string, unknown>
            const integration_id = record.integration_id
            const project_id = record.project_id
            const provider_name = record.provider_name
            const repo_key = record.repo_key
            if (
                typeof integration_id !== "string" ||
                typeof project_id !== "string" ||
                typeof provider_name !== "string" ||
                typeof repo_key !== "string"
            ) {
                continue
            }
            rtnval.push({
                integration_id: integration_id,
                project_id: project_id,
                provider_name: provider_name,
                repo_key: repo_key,
            })
        }
        return rtnval
    }

    /**
     * Fetch the current page of builds and re-render the table.
     * Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.projectId.length === 0) {
            this._builds = []
            this._render_table_region()
            return
        }
        this._state.loading = true
        this._state.errored = false
        this._render_table_region()

        const url = build_builds_query_url(this._state)
        let page: BuildRunPage | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error("builds fetch failed: HTTP " + String(response.status))
            }
            const body = await response.json()
            page = body as BuildRunPage
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.builds.list_fetch_failed",
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

        this._builds = page.items
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
     * Re-render the table region from the current state + builds.
     */
    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.projectId.length === 0) {
            const notice = document.createElement("p")
            notice.classList.add("pyc-builds__status")
            notice.setAttribute("data-role", "no-project-state")
            notice.textContent = "Select a project to view its builds."
            region.replaceChildren(notice)
            this._render_pager()
            return
        }

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-builds__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading builds…"
            region.replaceChildren(loading)
            this._render_pager()
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add("pyc-builds__status", "pyc-builds__status--error")
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load builds. Try refreshing."
            region.replaceChildren(error)
            this._render_pager()
            return
        }

        if (this._builds.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-builds__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No builds yet"
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
     * Build the builds ``<table>`` from the current ``_builds``
     * list.
     */
    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-builds__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Build",
            "Runner kind",
            "State",
            "Repro digest",
            "Started",
            "Finished",
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
        for (const build of this._builds) {
            const row = document.createElement("tr")
            row.classList.add("pyc-builds__row")

            const id_cell = document.createElement("td")
            const link = document.createElement("a")
            link.classList.add("pyc-builds__build-link")
            link.setAttribute("href", "/builds/" + build.run_id)
            link.textContent = short_id(build.run_id)
            link.title = build.run_id
            id_cell.appendChild(link)
            row.appendChild(id_cell)

            const runner_cell = document.createElement("td")
            runner_cell.textContent = build.runner_kind
            row.appendChild(runner_cell)

            const state_cell = document.createElement("td")
            const badge = document.createElement("span")
            badge.classList.add("pyc-builds__badge")
            badge.setAttribute("data-tone", build_state_tone(build.state))
            badge.textContent = build.state
            state_cell.appendChild(badge)
            row.appendChild(state_cell)

            const digest_cell = document.createElement("td")
            const digest = document.createElement("span")
            digest.classList.add("pyc-builds__digest")
            digest.textContent = short_id(build.repro_digest_sha256)
            digest.title = build.repro_digest_sha256
            digest_cell.appendChild(digest)
            row.appendChild(digest_cell)

            const started_cell = document.createElement("td")
            started_cell.textContent = format_timestamp(build.started_at)
            row.appendChild(started_cell)

            const finished_cell = document.createElement("td")
            finished_cell.textContent = format_timestamp(build.finished_at)
            row.appendChild(finished_cell)

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

    /**
     * Toggle the inline trigger-build form's visibility, rendering
     * it on first reveal.
     */
    private _toggle_trigger_form(): void {
        if (this._trigger_region === null) {
            return
        }
        const region = this._trigger_region
        if (region.hidden === true) {
            this._render_trigger_form()
            region.hidden = false
        } else {
            region.hidden = true
        }
        return
    }

    /**
     * Render the trigger-build form into the trigger region -- a
     * source-integration selector, a runner-kind input, a runner-
     * inputs JSON textarea, and a submit button.
     */
    private _render_trigger_form(): void {
        if (this._trigger_region === null) {
            return
        }
        const form = document.createElement("form")
        form.classList.add("pyc-builds__trigger-form")
        form.setAttribute("data-role", "trigger-form")

        const integration_label = document.createElement("label")
        integration_label.classList.add("pyc-builds__field")
        integration_label.textContent = "Source integration"
        const integration_select = document.createElement("select")
        integration_select.classList.add("pyc-builds__select")
        integration_select.setAttribute("data-role", "trigger-integration")
        if (this._integrations.length === 0) {
            const none_option = document.createElement("option")
            none_option.value = ""
            none_option.textContent = "No source integration registered"
            integration_select.appendChild(none_option)
        } else {
            for (const integration of this._integrations) {
                const option = document.createElement("option")
                option.value = integration.integration_id
                option.textContent =
                    integration.provider_name + " · " + integration.repo_key
                integration_select.appendChild(option)
            }
        }
        integration_label.appendChild(integration_select)
        form.appendChild(integration_label)

        const runner_label = document.createElement("label")
        runner_label.classList.add("pyc-builds__field")
        runner_label.textContent = "Runner kind"
        const runner_input = document.createElement("input")
        runner_input.classList.add("pyc-builds__input")
        runner_input.setAttribute("type", "text")
        runner_input.setAttribute("placeholder", "makefile")
        runner_input.setAttribute("data-role", "trigger-runner-kind")
        runner_input.required = true
        runner_label.appendChild(runner_input)
        form.appendChild(runner_label)

        const inputs_label = document.createElement("label")
        inputs_label.classList.add("pyc-builds__field", "pyc-builds__field--wide")
        inputs_label.textContent = "Runner inputs (JSON)"
        const inputs_area = document.createElement("textarea")
        inputs_area.classList.add("pyc-builds__textarea")
        inputs_area.setAttribute("data-role", "trigger-runner-inputs")
        inputs_area.setAttribute("placeholder", '{"target": "all"}')
        inputs_area.rows = 3
        inputs_label.appendChild(inputs_area)
        form.appendChild(inputs_label)

        const submit_button = document.createElement("button")
        submit_button.classList.add("pyc-builds__trigger")
        submit_button.setAttribute("type", "submit")
        submit_button.setAttribute("data-role", "trigger-submit")
        submit_button.textContent = "Trigger Build"
        form.appendChild(submit_button)

        const status = document.createElement("p")
        status.classList.add("pyc-builds__trigger-status")
        status.setAttribute("data-role", "trigger-status")
        form.appendChild(status)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_trigger(form, runner_input, inputs_area, submit_button)
        })

        this._trigger_region.replaceChildren(form)
        return
    }

    /**
     * Submit the trigger-build form -- POST a
     * ``BuildRunCreateRequest`` and surface the outcome. Exposed so
     * unit tests can invoke a trigger without a real form-submit
     * event.
     *
     * @param runner_kind The runner-kind identifier.
     * @param runner_inputs Free-form runner inputs object.
     *
     * @returns The trigger outcome.
     */
    public async triggerBuild(
        runner_kind: string,
        runner_inputs: Record<string, unknown>,
    ): Promise<TriggerOutcome> {
        const rtnval = await this._do_trigger(runner_kind, runner_inputs)
        return rtnval
    }

    private async _submit_trigger(
        form: HTMLFormElement,
        runner_input: HTMLInputElement,
        inputs_area: HTMLTextAreaElement,
        submit_button: HTMLButtonElement,
    ): Promise<void> {
        const status = form.querySelector('[data-role="trigger-status"]')
        const runner_kind = runner_input.value.trim()
        if (runner_kind.length === 0) {
            if (status instanceof HTMLElement) {
                status.textContent = "Runner kind is required."
            }
            return
        }
        let runner_inputs: Record<string, unknown> = {}
        try {
            runner_inputs = parse_runner_inputs(inputs_area.value)
        } catch (reason: unknown) {
            if (status instanceof HTMLElement) {
                status.textContent = "Runner inputs must be valid JSON."
            }
            console.warn(
                "pychestrate.ui.builds.trigger_inputs_invalid",
                { reason: String(reason) },
            )
            return
        }

        submit_button.disabled = true
        if (status instanceof HTMLElement) {
            status.textContent = "Triggering build…"
        }
        const outcome = await this._do_trigger(runner_kind, runner_inputs)
        submit_button.disabled = false
        if (status instanceof HTMLElement) {
            status.textContent = ""
        }
        this._show_trigger_toast(outcome)
        if (outcome.ok === true) {
            await this._refresh()
        }
        return
    }

    private async _do_trigger(
        runner_kind: string,
        runner_inputs: Record<string, unknown>,
    ): Promise<TriggerOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: TriggerOutcome = {
                ok: false,
                status: 0,
                buildId: "",
                message: "Select a project before triggering a build.",
            }
            return rtnval
        }
        const payload: Record<string, unknown> = {
            runner_kind: runner_kind,
            runner_inputs: runner_inputs,
        }
        let status = 0
        let build_id = ""
        try {
            const url = build_builds_collection_url(this._state.projectId)
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
            if (response.ok === true) {
                const body = await response.json()
                const run = body as BuildRun
                if (run !== null && typeof run.run_id === "string") {
                    build_id = run.run_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.builds.trigger_failed",
                { reason: String(reason) },
            )
            const rtnval: TriggerOutcome = {
                ok: false,
                status: 0,
                buildId: "",
                message: "Failed to reach the build service.",
            }
            return rtnval
        }
        const ok = status === 202 || status === 200 || status === 201
        const rtnval: TriggerOutcome = {
            ok: ok,
            status: status,
            buildId: build_id,
            message: trigger_message_for_status(status),
        }
        return rtnval
    }

    /**
     * Render a dismissible toast for a trigger outcome -- on
     * success the toast links to the new build's detail page.
     *
     * @param outcome The trigger-build outcome.
     */
    private _show_trigger_toast(outcome: TriggerOutcome): void {
        if (this._toast_region === null) {
            return
        }
        const toast = document.createElement("div")
        toast.classList.add("pyc-builds__toast")
        toast.setAttribute("data-role", "trigger-toast")
        toast.setAttribute("data-tone", outcome.ok === true ? "ok" : "error")

        const message = document.createElement("span")
        message.classList.add("pyc-builds__toast-message")
        message.textContent = outcome.message
        toast.appendChild(message)

        if (outcome.ok === true && outcome.buildId.length > 0) {
            const link = document.createElement("a")
            link.classList.add("pyc-builds__toast-link")
            link.setAttribute("href", "/builds/" + outcome.buildId)
            link.setAttribute("data-role", "trigger-toast-link")
            link.textContent = "View build"
            toast.appendChild(link)
        }

        const dismiss = document.createElement("button")
        dismiss.classList.add("pyc-builds__toast-dismiss")
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
