/**
 * ``<pyc-environments>`` -- the target-environments list view
 * Custom Element.
 *
 * On mount the element renders a project selector, then on a
 * project selection fetches that project's environments via
 * ``GET /api/v1/projects/{project_id}/environments`` and renders a
 * paginated table. Each environment row carries a drift-status
 * indicator (read on demand via
 * ``GET …/environments/{id}/drift``) and a "Check Drift" action
 * (``POST …/environments/{id}/drift:check``) that surfaces the
 * latest ``DriftReport``.
 *
 * The view also surfaces a "Register Environment" action: an
 * inline form that picks a kind name + environment name + a
 * free-form attrs JSON object, then POSTs an
 * ``EnvironmentCreateRequest`` to ``…/environments``.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state lives in instance fields.
 *
 * Project listing: the REST surface does not always publish a
 * ``GET /api/v1/projects`` collection, so when that endpoint is
 * unavailable the selector gracefully degrades to a manual
 * project-id text input -- mirroring the builds + catalog bundles.
 */

/**
 * The ``Environment`` lifecycle states from
 * ``specs/openapi/pychestrate.yaml``.
 */
export const ENVIRONMENT_STATES: readonly string[] = [
    "active",
    "frozen",
    "archived",
    "destroyed",
]

/**
 * The ``DriftReport`` lifecycle states from the OpenAPI spec.
 */
export const DRIFT_STATES: readonly string[] = [
    "pending",
    "running",
    "completed",
    "failed",
    "ingest_failed",
    "skipped",
]

/**
 * One target environment, as returned in the ``items`` array of
 * ``EnvironmentPage``. Only the fields the view renders are typed.
 */
export interface Environment {
    environment_id: string
    project_id: string
    kind_name: string
    name: string
    state: string
    attrs?: Record<string, unknown> | null
    last_applied_run_id?: string | null
    last_applied_at?: string | null
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
 * The ``EnvironmentPage`` response shape.
 */
export interface EnvironmentPage {
    items: Environment[]
    meta: PageMeta
}

/**
 * One drift run / report -- the subset of ``DriftReport`` the
 * drift indicator and toast consume.
 */
export interface DriftReport {
    run_id: string
    project_id: string
    environment_id: string
    checker_name: string
    state: string
    trigger_kind: string
    drift_count?: number | null
    added?: number | null
    changed?: number | null
    destroyed?: number | null
    ran_at?: string | null
    final_state_reason?: string | null
}

/**
 * The ``DriftStatus`` response shape -- the latest drift run, or
 * ``null`` when none has been recorded.
 */
export interface DriftStatus {
    environment_id: string
    has_report: boolean
    latest_report?: DriftReport | null
}

/**
 * One project, as the project selector consumes it.
 */
export interface ProjectOption {
    project_id: string
    display_name: string
}

/**
 * Outcome of a register-environment POST, surfaced to the caller.
 */
export interface RegisterOutcome {
    ok: boolean
    status: number
    environmentId: string
    message: string
}

/**
 * Outcome of a drift-check POST, surfaced to the caller / tests.
 */
export interface DriftCheckOutcome {
    ok: boolean
    status: number
    report: DriftReport | null
    message: string
}

/**
 * The current project + pagination state of the environments view.
 * Exposed so unit tests can assert state transitions.
 */
export interface EnvironmentsListState {
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
 * Build the ``GET …/projects/{project_id}/environments`` query URL
 * from the supplied project id, state filter, and pagination
 * state.
 *
 * @param state Current environments list state.
 *
 * @returns A relative URL string including the query string.
 */
export function build_environments_query_url(
    state: EnvironmentsListState,
): string {
    const params = new URLSearchParams()
    if (state.stateFilter.length > 0) {
        params.set("state", state.stateFilter)
    }
    params.set("page", String(state.page))
    params.set("per_page", String(state.perPage))
    const query = params.toString()
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(state.projectId) + "/environments?" + query
    return rtnval
}

/**
 * Build the ``POST …/projects/{project_id}/environments`` URL used
 * by the register-environment action.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_environments_collection_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/environments"
    return rtnval
}

/**
 * Build the ``GET …/environments/{environment_id}/drift`` URL the
 * drift indicator consults.
 *
 * @param project_id Owning project identifier.
 * @param environment_id Environment identifier.
 *
 * @returns A relative URL string.
 */
export function build_drift_status_url(
    project_id: string,
    environment_id: string,
): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/environments/" +
        encodeURIComponent(environment_id) + "/drift"
    return rtnval
}

/**
 * Build the ``POST …/environments/{environment_id}/drift:check``
 * URL the "Check Drift" action targets.
 *
 * @param project_id Owning project identifier.
 * @param environment_id Environment identifier.
 *
 * @returns A relative URL string.
 */
export function build_drift_check_url(
    project_id: string,
    environment_id: string,
): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/environments/" +
        encodeURIComponent(environment_id) + "/drift:check"
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
 * Classify an environment state into a coarse badge tone so the
 * CSS can pick a token-driven color.
 *
 * @param environment_state One of the ``Environment`` state enum
 *                           values.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function environment_state_tone(environment_state: string): string {
    if (environment_state === "active") {
        const rtnval = "ok"
        return rtnval
    }
    if (environment_state === "frozen") {
        const rtnval = "warn"
        return rtnval
    }
    if (environment_state === "destroyed") {
        const rtnval = "error"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Classify a drift status into a coarse badge tone. A drift run
 * that has detected drift surfaces as a warning; a clean completed
 * run surfaces as ok; a failed run surfaces as an error.
 *
 * @param status The environment's current drift status, or null.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function drift_status_tone(status: DriftStatus | null): string {
    if (status === null || status.has_report === false) {
        const rtnval = "neutral"
        return rtnval
    }
    const report = status.latest_report
    if (report === undefined || report === null) {
        const rtnval = "neutral"
        return rtnval
    }
    if (report.state === "failed" || report.state === "ingest_failed") {
        const rtnval = "error"
        return rtnval
    }
    const count = report.drift_count
    if (typeof count === "number" && count > 0) {
        const rtnval = "warn"
        return rtnval
    }
    if (report.state === "completed") {
        const rtnval = "ok"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Compose the short human label shown in an environment row's
 * drift indicator.
 *
 * @param status The environment's current drift status, or null.
 *
 * @returns A short label such as ``"3 drifted"`` or ``"No drift"``.
 */
export function drift_status_label(status: DriftStatus | null): string {
    if (status === null) {
        const rtnval = "Not checked"
        return rtnval
    }
    if (status.has_report === false) {
        const rtnval = "Not checked"
        return rtnval
    }
    const report = status.latest_report
    if (report === undefined || report === null) {
        const rtnval = "Not checked"
        return rtnval
    }
    if (report.state === "failed" || report.state === "ingest_failed") {
        const rtnval = "Check failed"
        return rtnval
    }
    if (report.state === "pending" || report.state === "running") {
        const rtnval = "Checking…"
        return rtnval
    }
    const count = report.drift_count
    if (typeof count === "number" && count > 0) {
        const rtnval = String(count) + " drifted"
        return rtnval
    }
    const rtnval = "No drift"
    return rtnval
}

/**
 * Compute whether a "next page" control should be enabled.
 *
 * @param state Current environments list state.
 *
 * @returns True when a further page of results exists.
 */
export function has_next_page(state: EnvironmentsListState): boolean {
    const consumed = state.page * state.perPage
    const rtnval = consumed < state.total
    return rtnval
}

/**
 * Compute whether a "previous page" control should be enabled.
 *
 * @param state Current environments list state.
 *
 * @returns True when the caller is not on the first page.
 */
export function has_previous_page(state: EnvironmentsListState): boolean {
    const rtnval = state.page > 1
    return rtnval
}

/**
 * Translate a register-environment HTTP status into operator
 * guidance.
 *
 * @param status HTTP status code of the register response.
 *
 * @returns A human-readable message.
 */
export function register_message_for_status(status: number): string {
    if (status === 201 || status === 200) {
        const rtnval = "Environment registered."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "An environment with that name already exists."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "Environment attrs were rejected — check the kind."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown project or environment kind."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to register environments."
        return rtnval
    }
    const rtnval = "Failed to register environment (HTTP " +
        String(status) + ")."
    return rtnval
}

/**
 * Translate a drift-check HTTP status into operator guidance.
 *
 * @param status HTTP status code of the drift-check response.
 *
 * @returns A human-readable message.
 */
export function drift_check_message_for_status(status: number): string {
    if (status === 202 || status === 200) {
        const rtnval = "Drift check queued."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "This environment has no drift schedule."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown environment."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to check drift."
        return rtnval
    }
    const rtnval = "Failed to check drift (HTTP " + String(status) + ")."
    return rtnval
}

/**
 * Parse the attrs textarea content as JSON. An empty string
 * yields an empty object; malformed JSON throws.
 *
 * @param raw Raw textarea content.
 *
 * @returns A parsed attrs object.
 * @raises SyntaxError when ``raw`` is not a valid JSON object.
 */
export function parse_environment_attrs(raw: string): Record<string, unknown> {
    if (typeof raw !== "string" || raw.trim().length === 0) {
        const rtnval: Record<string, unknown> = {}
        return rtnval
    }
    const parsed = JSON.parse(raw)
    if (
        parsed === null ||
        typeof parsed !== "object" ||
        Array.isArray(parsed) === true
    ) {
        throw new SyntaxError("environment attrs must be a JSON object")
    }
    const rtnval = parsed as Record<string, unknown>
    return rtnval
}

/**
 * The environments list view Custom Element. Register it with
 * ``customElements.define("pyc-environments", PycEnvironments)``.
 */
export class PycEnvironments extends HTMLElement {
    private _state: EnvironmentsListState
    private _environments: Environment[]
    private _drift: Map<string, DriftStatus>
    private _projects: ProjectOption[]
    private _projectsAvailable: boolean
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null
    private _register_region: HTMLElement | null
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
        this._environments = []
        this._drift = new Map<string, DriftStatus>()
        this._projects = []
        this._projectsAvailable = false
        this._root = null
        this._table_region = null
        this._register_region = null
        this._toast_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * project + pagination state without scraping the DOM.
     */
    public get listState(): EnvironmentsListState {
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
     * state filter, register action, table region, pager, toast.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-infra")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-infra__heading")
        heading.textContent = "Environments"
        root.appendChild(heading)

        const controls = document.createElement("div")
        controls.classList.add("pyc-infra__controls")

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-infra__field")
        project_label.textContent = "Project"
        const project_select = document.createElement("select")
        project_select.classList.add("pyc-infra__select")
        project_select.setAttribute("data-role", "project-select")
        project_select.addEventListener("change", () => {
            this._state.projectId = project_select.value
            this._state.page = 1
            void this._refresh()
        })
        project_label.appendChild(project_select)
        controls.appendChild(project_label)

        const project_input = document.createElement("input")
        project_input.classList.add("pyc-infra__input")
        project_input.setAttribute("type", "text")
        project_input.setAttribute("placeholder", "project id")
        project_input.setAttribute("data-role", "project-input")
        project_input.hidden = true
        project_input.addEventListener("change", () => {
            this._state.projectId = project_input.value.trim()
            this._state.page = 1
            void this._refresh()
        })
        controls.appendChild(project_input)

        const state_label = document.createElement("label")
        state_label.classList.add("pyc-infra__field")
        state_label.textContent = "State"
        const state_select = document.createElement("select")
        state_select.classList.add("pyc-infra__select")
        state_select.setAttribute("data-role", "state-filter")
        const any_option = document.createElement("option")
        any_option.value = ""
        any_option.textContent = "All states"
        state_select.appendChild(any_option)
        for (const environment_state of ENVIRONMENT_STATES) {
            const option = document.createElement("option")
            option.value = environment_state
            option.textContent = environment_state
            state_select.appendChild(option)
        }
        state_select.addEventListener("change", () => {
            this._state.stateFilter = state_select.value
            this._state.page = 1
            void this._refresh()
        })
        state_label.appendChild(state_select)
        controls.appendChild(state_label)

        const register_button = document.createElement("button")
        register_button.classList.add("pyc-infra__button")
        register_button.setAttribute("type", "button")
        register_button.setAttribute("data-role", "register-toggle")
        register_button.textContent = "Register Environment"
        register_button.addEventListener("click", () => {
            this._toggle_register_form()
        })
        controls.appendChild(register_button)

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-infra__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            void this._refresh()
        })
        controls.appendChild(refresh_button)

        root.appendChild(controls)

        const register_region = document.createElement("div")
        register_region.classList.add("pyc-infra__form-region")
        register_region.setAttribute("data-role", "register-region")
        register_region.hidden = true
        root.appendChild(register_region)
        this._register_region = register_region

        const toast_region = document.createElement("div")
        toast_region.classList.add("pyc-infra__toast-region")
        toast_region.setAttribute("data-role", "toast-region")
        root.appendChild(toast_region)
        this._toast_region = toast_region

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-infra__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const pager = document.createElement("div")
        pager.classList.add("pyc-infra__pager")

        const prev_button = document.createElement("button")
        prev_button.classList.add("pyc-infra__button")
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
        page_indicator.classList.add("pyc-infra__page-indicator")
        page_indicator.setAttribute("data-role", "page-indicator")
        pager.appendChild(page_indicator)

        const next_button = document.createElement("button")
        next_button.classList.add("pyc-infra__button")
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
                "pychestrate.ui.infra.projects_fetch_failed",
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
            this._render_table_region()
        }
        return
    }

    /**
     * Normalise a projects-list response body into ``ProjectOption``
     * records. Accepts both a bare array and a ``{items}`` page
     * envelope.
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
            const display_name = typeof display === "string" &&
                display.length > 0
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
     * Fetch the current page of environments and re-render the
     * table. Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.projectId.length === 0) {
            this._environments = []
            this._render_table_region()
            return
        }
        this._state.loading = true
        this._state.errored = false
        this._drift = new Map<string, DriftStatus>()
        this._render_table_region()

        const url = build_environments_query_url(this._state)
        let page: EnvironmentPage | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "environments fetch failed: HTTP " +
                        String(response.status),
                )
            }
            const body = await response.json()
            page = body as EnvironmentPage
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.infra.environments_fetch_failed",
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

        this._environments = page.items
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
     * Re-render the table region from the current state +
     * environments.
     */
    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.projectId.length === 0) {
            const notice = document.createElement("p")
            notice.classList.add("pyc-infra__status")
            notice.setAttribute("data-role", "no-project-state")
            notice.textContent =
                "Select a project to view its environments."
            region.replaceChildren(notice)
            this._render_pager()
            return
        }

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-infra__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading environments…"
            region.replaceChildren(loading)
            this._render_pager()
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-infra__status",
                "pyc-infra__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent =
                "Failed to load environments. Try refreshing."
            region.replaceChildren(error)
            this._render_pager()
            return
        }

        if (this._environments.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-infra__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No environments registered yet"
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
     * Build the environments ``<table>`` from the current list.
     */
    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-infra__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Environment",
            "Kind",
            "State",
            "Drift",
            "Last applied",
            "Actions",
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
        for (const environment of this._environments) {
            tbody.appendChild(this._build_row(environment))
        }
        table.appendChild(tbody)
        return table
    }

    /**
     * Build one environment table row, including the drift
     * indicator cell and the per-row "Check Drift" action.
     *
     * @param environment The environment to render.
     *
     * @returns A populated ``<tr>``.
     */
    private _build_row(environment: Environment): HTMLTableRowElement {
        const row = document.createElement("tr")
        row.classList.add("pyc-infra__row")
        row.setAttribute("data-environment-id", environment.environment_id)

        const name_cell = document.createElement("td")
        const name = document.createElement("span")
        name.classList.add("pyc-infra__env-name")
        name.textContent = environment.name
        name.title = environment.environment_id
        name_cell.appendChild(name)
        row.appendChild(name_cell)

        const kind_cell = document.createElement("td")
        kind_cell.textContent = environment.kind_name
        row.appendChild(kind_cell)

        const state_cell = document.createElement("td")
        const state_badge = document.createElement("span")
        state_badge.classList.add("pyc-infra__badge")
        state_badge.setAttribute(
            "data-tone",
            environment_state_tone(environment.state),
        )
        state_badge.textContent = environment.state
        state_cell.appendChild(state_badge)
        row.appendChild(state_cell)

        const drift_cell = document.createElement("td")
        const drift_badge = document.createElement("span")
        drift_badge.classList.add("pyc-infra__badge", "pyc-infra__drift")
        drift_badge.setAttribute("data-role", "drift-indicator")
        const status = this._drift.get(environment.environment_id) ?? null
        drift_badge.setAttribute("data-tone", drift_status_tone(status))
        drift_badge.textContent = drift_status_label(status)
        drift_cell.appendChild(drift_badge)
        row.appendChild(drift_cell)

        const applied_cell = document.createElement("td")
        applied_cell.textContent = format_timestamp(environment.last_applied_at)
        row.appendChild(applied_cell)

        const actions_cell = document.createElement("td")
        const check_button = document.createElement("button")
        check_button.classList.add("pyc-infra__button", "pyc-infra__row-action")
        check_button.setAttribute("type", "button")
        check_button.setAttribute("data-role", "check-drift")
        check_button.textContent = "Check Drift"
        check_button.addEventListener("click", () => {
            check_button.disabled = true
            void this._on_check_drift(environment, check_button)
        })
        actions_cell.appendChild(check_button)
        row.appendChild(actions_cell)

        return row
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
        const indicator = this._root.querySelector(
            '[data-role="page-indicator"]',
        )

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
     * Refresh one environment's drift indicator cell from the
     * supplied drift status.
     *
     * @param environment_id The environment whose row to update.
     */
    private _render_drift_cell(environment_id: string): void {
        if (this._table_region === null) {
            return
        }
        const selector =
            'tr[data-environment-id="' + environment_id + '"] ' +
            '[data-role="drift-indicator"]'
        const badge = this._table_region.querySelector(selector)
        if (badge instanceof HTMLElement === false) {
            return
        }
        const el = badge as HTMLElement
        const status = this._drift.get(environment_id) ?? null
        el.setAttribute("data-tone", drift_status_tone(status))
        el.textContent = drift_status_label(status)
        return
    }

    /**
     * Run the "Check Drift" action for one environment -- POST the
     * drift-check then re-read the drift status, updating the
     * indicator and surfacing a toast.
     *
     * @param environment The environment to check.
     * @param button The row action button, re-enabled on completion.
     */
    private async _on_check_drift(
        environment: Environment,
        button: HTMLButtonElement,
    ): Promise<void> {
        const outcome = await this._do_check_drift(
            environment.environment_id,
        )
        if (outcome.ok === true) {
            await this._load_drift_status(environment.environment_id)
        }
        button.disabled = false
        this._show_toast(
            outcome.message,
            outcome.ok === true ? "ok" : "error",
        )
        return
    }

    /**
     * POST a drift check for one environment. Exposed so unit tests
     * can drive a drift check without a row button.
     *
     * @param environment_id The environment to check.
     *
     * @returns The drift-check outcome.
     */
    public async checkDrift(environment_id: string): Promise<DriftCheckOutcome> {
        const rtnval = await this._do_check_drift(environment_id)
        return rtnval
    }

    private async _do_check_drift(
        environment_id: string,
    ): Promise<DriftCheckOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: DriftCheckOutcome = {
                ok: false,
                status: 0,
                report: null,
                message: "Select a project before checking drift.",
            }
            return rtnval
        }
        let status = 0
        let report: DriftReport | null = null
        try {
            const url = build_drift_check_url(
                this._state.projectId,
                environment_id,
            )
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            status = response.status
            if (response.ok === true) {
                const body = await response.json()
                const parsed = body as DriftReport
                if (parsed !== null && typeof parsed.run_id === "string") {
                    report = parsed
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.infra.drift_check_failed",
                { reason: String(reason) },
            )
            const rtnval: DriftCheckOutcome = {
                ok: false,
                status: 0,
                report: null,
                message: "Failed to reach the drift service.",
            }
            return rtnval
        }
        const ok = status === 202 || status === 200
        const rtnval: DriftCheckOutcome = {
            ok: ok,
            status: status,
            report: report,
            message: drift_check_message_for_status(status),
        }
        return rtnval
    }

    /**
     * Fetch and cache one environment's current drift status, then
     * re-render its indicator cell. Exposed so unit tests can await
     * a drift-status fetch.
     *
     * @param environment_id The environment to read drift for.
     */
    public async loadDriftStatus(environment_id: string): Promise<void> {
        await this._load_drift_status(environment_id)
        return
    }

    private async _load_drift_status(environment_id: string): Promise<void> {
        if (this._state.projectId.length === 0) {
            return
        }
        try {
            const url = build_drift_status_url(
                this._state.projectId,
                environment_id,
            )
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                const status = body as DriftStatus
                if (status !== null && typeof status === "object") {
                    this._drift.set(environment_id, status)
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.infra.drift_status_fetch_failed",
                { reason: String(reason) },
            )
        }
        this._render_drift_cell(environment_id)
        return
    }

    /**
     * Toggle the inline register-environment form's visibility,
     * rendering it on first reveal.
     */
    private _toggle_register_form(): void {
        if (this._register_region === null) {
            return
        }
        const region = this._register_region
        if (region.hidden === true) {
            this._render_register_form()
            region.hidden = false
        } else {
            region.hidden = true
        }
        return
    }

    /**
     * Render the register-environment form into the register
     * region -- a name input, a kind-name input, an attrs JSON
     * textarea, and a submit button.
     */
    private _render_register_form(): void {
        if (this._register_region === null) {
            return
        }
        const form = document.createElement("form")
        form.classList.add("pyc-infra__form")
        form.setAttribute("data-role", "register-form")

        const name_label = document.createElement("label")
        name_label.classList.add("pyc-infra__field")
        name_label.textContent = "Environment name"
        const name_input = document.createElement("input")
        name_input.classList.add("pyc-infra__input")
        name_input.setAttribute("type", "text")
        name_input.setAttribute("placeholder", "staging")
        name_input.setAttribute("data-role", "register-name")
        name_input.required = true
        name_label.appendChild(name_input)
        form.appendChild(name_label)

        const kind_label = document.createElement("label")
        kind_label.classList.add("pyc-infra__field")
        kind_label.textContent = "Environment kind"
        const kind_input = document.createElement("input")
        kind_input.classList.add("pyc-infra__input")
        kind_input.setAttribute("type", "text")
        kind_input.setAttribute("placeholder", "terraform")
        kind_input.setAttribute("data-role", "register-kind")
        kind_input.required = true
        kind_label.appendChild(kind_input)
        form.appendChild(kind_label)

        const attrs_label = document.createElement("label")
        attrs_label.classList.add(
            "pyc-infra__field",
            "pyc-infra__field--wide",
        )
        attrs_label.textContent = "Attributes (JSON)"
        const attrs_area = document.createElement("textarea")
        attrs_area.classList.add("pyc-infra__textarea")
        attrs_area.setAttribute("data-role", "register-attrs")
        attrs_area.setAttribute("placeholder", '{"region": "us-east-1"}')
        attrs_area.rows = 3
        attrs_label.appendChild(attrs_area)
        form.appendChild(attrs_label)

        const submit_button = document.createElement("button")
        submit_button.classList.add("pyc-infra__submit")
        submit_button.setAttribute("type", "submit")
        submit_button.setAttribute("data-role", "register-submit")
        submit_button.textContent = "Register Environment"
        form.appendChild(submit_button)

        const status = document.createElement("p")
        status.classList.add("pyc-infra__form-status")
        status.setAttribute("data-role", "register-status")
        form.appendChild(status)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_register(
                form,
                name_input,
                kind_input,
                attrs_area,
                submit_button,
            )
        })

        this._register_region.replaceChildren(form)
        return
    }

    private async _submit_register(
        form: HTMLFormElement,
        name_input: HTMLInputElement,
        kind_input: HTMLInputElement,
        attrs_area: HTMLTextAreaElement,
        submit_button: HTMLButtonElement,
    ): Promise<void> {
        const status = form.querySelector('[data-role="register-status"]')
        const name = name_input.value.trim()
        const kind_name = kind_input.value.trim()
        if (name.length === 0 || kind_name.length === 0) {
            if (status instanceof HTMLElement) {
                status.textContent =
                    "Environment name and kind are required."
            }
            return
        }
        let attrs: Record<string, unknown> = {}
        try {
            attrs = parse_environment_attrs(attrs_area.value)
        } catch (reason: unknown) {
            if (status instanceof HTMLElement) {
                status.textContent = "Attributes must be valid JSON."
            }
            console.warn(
                "pychestrate.ui.infra.register_attrs_invalid",
                { reason: String(reason) },
            )
            return
        }

        submit_button.disabled = true
        if (status instanceof HTMLElement) {
            status.textContent = "Registering environment…"
        }
        const outcome = await this._do_register(name, kind_name, attrs)
        submit_button.disabled = false
        if (status instanceof HTMLElement) {
            status.textContent = ""
        }
        this._show_toast(
            outcome.message,
            outcome.ok === true ? "ok" : "error",
        )
        if (outcome.ok === true) {
            await this._refresh()
        }
        return
    }

    /**
     * POST an ``EnvironmentCreateRequest``. Exposed so unit tests
     * can invoke a register without a real form-submit event.
     *
     * @param name Human-facing environment name.
     * @param kind_name Registered environment-kind factory name.
     * @param attrs Kind-specific environment attributes.
     *
     * @returns The register outcome.
     */
    public async registerEnvironment(
        name: string,
        kind_name: string,
        attrs: Record<string, unknown>,
    ): Promise<RegisterOutcome> {
        const rtnval = await this._do_register(name, kind_name, attrs)
        return rtnval
    }

    private async _do_register(
        name: string,
        kind_name: string,
        attrs: Record<string, unknown>,
    ): Promise<RegisterOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: RegisterOutcome = {
                ok: false,
                status: 0,
                environmentId: "",
                message: "Select a project before registering an environment.",
            }
            return rtnval
        }
        const payload: Record<string, unknown> = {
            name: name,
            kind_name: kind_name,
            attrs: attrs,
        }
        let status = 0
        let environment_id = ""
        try {
            const url = build_environments_collection_url(
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
            if (response.ok === true) {
                const body = await response.json()
                const environment = body as Environment
                if (
                    environment !== null &&
                    typeof environment.environment_id === "string"
                ) {
                    environment_id = environment.environment_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.infra.register_failed",
                { reason: String(reason) },
            )
            const rtnval: RegisterOutcome = {
                ok: false,
                status: 0,
                environmentId: "",
                message: "Failed to reach the environment service.",
            }
            return rtnval
        }
        const ok = status === 201 || status === 200
        const rtnval: RegisterOutcome = {
            ok: ok,
            status: status,
            environmentId: environment_id,
            message: register_message_for_status(status),
        }
        return rtnval
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
        toast.classList.add("pyc-infra__toast")
        toast.setAttribute("data-role", "toast")
        toast.setAttribute("data-tone", tone)

        const text = document.createElement("span")
        text.classList.add("pyc-infra__toast-message")
        text.textContent = message
        toast.appendChild(text)

        const dismiss = document.createElement("button")
        dismiss.classList.add("pyc-infra__toast-dismiss")
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
