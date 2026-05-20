/**
 * ``<pyc-provisioning-list>`` -- the provisioning-runs list view
 * Custom Element.
 *
 * On mount the element renders a project selector, then on a
 * project selection fetches that project's provisioning runs via
 * ``GET /api/v1/projects/{project_id}/provisioning-runs`` and
 * renders a paginated, state-filterable table. Each row links to
 * ``/provisioning-runs/{run_id}?project_id={project_id}`` -- the
 * provisioning-detail page. The detail route carries no project
 * id, so the list links carry it as a query param the detail view
 * reads back.
 *
 * The view also surfaces a "Trigger Provisioning" action: an
 * inline form that picks a bound environment + a driver name + an
 * action (plan/apply/destroy) + free-form driver inputs, then
 * POSTs a ``ProvisioningRunCreateRequest`` to
 * ``…/provisioning-runs``.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

import {
    type Environment,
    type EnvironmentPage,
    type ProjectOption,
    build_environments_query_url,
    format_timestamp,
    short_id,
} from "./environments-view.js"

/**
 * The ``ProvisioningRun`` lifecycle states from the OpenAPI spec.
 */
export const PROVISIONING_STATES: readonly string[] = [
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "rejected_by_guard",
]

/**
 * ``ProvisioningRun`` states the server treats as terminal.
 */
export const TERMINAL_PROVISIONING_STATES: readonly string[] = [
    "completed",
    "failed",
    "cancelled",
    "rejected_by_guard",
]

/**
 * The provisioning actions a run can encode.
 */
export const PROVISIONING_ACTIONS: readonly string[] = [
    "plan",
    "apply",
    "destroy",
]

/**
 * Aggregate plan output recorded on a provisioning run.
 */
export interface ProvisioningPlanSummary {
    resources_to_add: number
    resources_to_change: number
    resources_to_destroy: number
    resource_ops?: ProvisioningResourceOp[] | null
}

/**
 * One per-resource operation on a plan summary.
 */
export interface ProvisioningResourceOp {
    resource_address: string
    op: string
    module_path?: string | null
}

/**
 * One provisioning run, as returned in the ``items`` array of
 * ``ProvisioningRunPage``. Only the fields the views render are
 * typed here.
 */
export interface ProvisioningRun {
    run_id: string
    project_id: string
    environment_id: string
    driver_name: string
    action: string
    state: string
    layer5_run_id?: string | null
    actor_id?: string | null
    inputs?: Record<string, unknown> | null
    plan_summary?: ProvisioningPlanSummary | null
    plan_issued_at?: string | null
    started_at?: string | null
    finished_at?: string | null
    final_state_reason?: string | null
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
 * The ``ProvisioningRunPage`` response shape.
 */
export interface ProvisioningRunPage {
    items: ProvisioningRun[]
    meta: PageMeta
}

/**
 * Outcome of a trigger-provisioning POST, surfaced to the caller.
 */
export interface TriggerOutcome {
    ok: boolean
    status: number
    runId: string
    message: string
}

/**
 * The current project + pagination state of the provisioning list
 * view. Exposed so unit tests can assert state transitions.
 */
export interface ProvisioningListState {
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
 * Build the ``GET …/projects/{project_id}/provisioning-runs``
 * query URL from the supplied project id, state filter, and
 * pagination state.
 *
 * @param state Current provisioning list state.
 *
 * @returns A relative URL string including the query string.
 */
export function build_provisioning_query_url(
    state: ProvisioningListState,
): string {
    const params = new URLSearchParams()
    if (state.stateFilter.length > 0) {
        params.set("state", state.stateFilter)
    }
    params.set("page", String(state.page))
    params.set("per_page", String(state.perPage))
    const query = params.toString()
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(state.projectId) + "/provisioning-runs?" + query
    return rtnval
}

/**
 * Build the ``POST …/projects/{project_id}/provisioning-runs`` URL
 * used by the trigger-provisioning action.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_provisioning_collection_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/provisioning-runs"
    return rtnval
}

/**
 * Build the shell-served detail link for a provisioning run. The
 * detail route carries no project id, so the project id rides
 * along as a query param the detail view reads back.
 *
 * @param project_id Owning project identifier.
 * @param run_id Provisioning run identifier.
 *
 * @returns A relative shell URL string.
 */
export function build_provisioning_detail_link(
    project_id: string,
    run_id: string,
): string {
    const rtnval = "/provisioning-runs/" + encodeURIComponent(run_id) +
        "?project_id=" + encodeURIComponent(project_id)
    return rtnval
}

/**
 * Classify a provisioning state into a coarse badge tone.
 *
 * @param run_state One of the ``ProvisioningRun`` state enum
 *                   values.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function provisioning_state_tone(run_state: string): string {
    if (run_state === "completed") {
        const rtnval = "ok"
        return rtnval
    }
    if (run_state === "failed") {
        const rtnval = "error"
        return rtnval
    }
    if (run_state === "rejected_by_guard") {
        const rtnval = "error"
        return rtnval
    }
    if (run_state === "cancelled") {
        const rtnval = "warn"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Decide whether a provisioning state is terminal.
 *
 * @param run_state One of the ``ProvisioningRun`` state enum
 *                   values.
 *
 * @returns True when the state is terminal.
 */
export function is_terminal_provisioning_state(run_state: string): boolean {
    const rtnval = TERMINAL_PROVISIONING_STATES.indexOf(run_state) >= 0
    return rtnval
}

/**
 * Compute whether a "next page" control should be enabled.
 *
 * @param state Current provisioning list state.
 *
 * @returns True when a further page of results exists.
 */
export function has_next_page(state: ProvisioningListState): boolean {
    const consumed = state.page * state.perPage
    const rtnval = consumed < state.total
    return rtnval
}

/**
 * Compute whether a "previous page" control should be enabled.
 *
 * @param state Current provisioning list state.
 *
 * @returns True when the caller is not on the first page.
 */
export function has_previous_page(state: ProvisioningListState): boolean {
    const rtnval = state.page > 1
    return rtnval
}

/**
 * Translate a trigger-provisioning HTTP status into operator
 * guidance.
 *
 * @param status HTTP status code of the trigger response.
 *
 * @returns A human-readable message.
 */
export function trigger_message_for_status(status: number): string {
    if (status === 202 || status === 200 || status === 201) {
        const rtnval = "Provisioning run triggered."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "Driver inputs were rejected — check the driver name."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "The environment cannot accept this action right now."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown project, environment, or driver."
        return rtnval
    }
    if (status === 403) {
        const rtnval =
            "You do not have permission to trigger provisioning runs."
        return rtnval
    }
    const rtnval = "Failed to trigger provisioning run (HTTP " +
        String(status) + ")."
    return rtnval
}

/**
 * Parse the driver-inputs textarea content as JSON. An empty
 * string yields an empty object; malformed JSON throws.
 *
 * @param raw Raw textarea content.
 *
 * @returns A parsed inputs object.
 * @raises SyntaxError when ``raw`` is not a valid JSON object.
 */
export function parse_driver_inputs(raw: string): Record<string, unknown> {
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
        throw new SyntaxError("driver inputs must be a JSON object")
    }
    const rtnval = parsed as Record<string, unknown>
    return rtnval
}

/**
 * The provisioning list view Custom Element. Register it with
 * ``customElements.define("pyc-provisioning-list",
 * PycProvisioningList)``.
 */
export class PycProvisioningList extends HTMLElement {
    private _state: ProvisioningListState
    private _runs: ProvisioningRun[]
    private _environments: Environment[]
    private _projects: ProjectOption[]
    private _projectsAvailable: boolean
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
        this._runs = []
        this._environments = []
        this._projects = []
        this._projectsAvailable = false
        this._root = null
        this._table_region = null
        this._trigger_region = null
        this._toast_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * project + pagination state without scraping the DOM.
     */
    public get listState(): ProvisioningListState {
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
        root.classList.add("pyc-infra")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-infra__heading")
        heading.textContent = "Provisioning Runs"
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
            void this._on_project_changed()
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
            void this._on_project_changed()
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
        for (const run_state of PROVISIONING_STATES) {
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
        controls.appendChild(state_label)

        const trigger_button = document.createElement("button")
        trigger_button.classList.add("pyc-infra__button")
        trigger_button.setAttribute("type", "button")
        trigger_button.setAttribute("data-role", "trigger-toggle")
        trigger_button.textContent = "Trigger Provisioning"
        trigger_button.addEventListener("click", () => {
            this._toggle_trigger_form()
        })
        controls.appendChild(trigger_button)

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

        const trigger_region = document.createElement("div")
        trigger_region.classList.add("pyc-infra__form-region")
        trigger_region.setAttribute("data-role", "trigger-region")
        trigger_region.hidden = true
        root.appendChild(trigger_region)
        this._trigger_region = trigger_region

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
            await this._on_project_changed()
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
     * React to a project change -- reload the environments (so the
     * trigger form's selector is fresh) and the provisioning page.
     */
    private async _on_project_changed(): Promise<void> {
        await this._load_environments()
        await this._refresh()
        return
    }

    /**
     * Fetch the active project's environments for the trigger
     * form's environment selector. A failed fetch leaves the list
     * empty.
     */
    private async _load_environments(): Promise<void> {
        this._environments = []
        if (this._state.projectId.length === 0) {
            return
        }
        try {
            const url = build_environments_query_url({
                projectId: this._state.projectId,
                stateFilter: "",
                page: 1,
                perPage: 100,
                total: 0,
                loading: false,
                errored: false,
            })
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                const page = body as EnvironmentPage
                if (page !== null && Array.isArray(page.items) === true) {
                    this._environments = page.items
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.infra.environments_fetch_failed",
                { reason: String(reason) },
            )
        }
        return
    }

    /**
     * Fetch the current page of provisioning runs and re-render
     * the table. Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.projectId.length === 0) {
            this._runs = []
            this._render_table_region()
            return
        }
        this._state.loading = true
        this._state.errored = false
        this._render_table_region()

        const url = build_provisioning_query_url(this._state)
        let page: ProvisioningRunPage | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "provisioning fetch failed: HTTP " +
                        String(response.status),
                )
            }
            const body = await response.json()
            page = body as ProvisioningRunPage
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.infra.provisioning_fetch_failed",
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

        if (this._state.projectId.length === 0) {
            const notice = document.createElement("p")
            notice.classList.add("pyc-infra__status")
            notice.setAttribute("data-role", "no-project-state")
            notice.textContent =
                "Select a project to view its provisioning runs."
            region.replaceChildren(notice)
            this._render_pager()
            return
        }

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-infra__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading provisioning runs…"
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
                "Failed to load provisioning runs. Try refreshing."
            region.replaceChildren(error)
            this._render_pager()
            return
        }

        if (this._runs.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-infra__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No provisioning runs yet"
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
     * Build the provisioning-runs ``<table>`` from the current
     * ``_runs`` list.
     */
    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-infra__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Run",
            "Action",
            "Driver",
            "State",
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
        for (const run of this._runs) {
            const row = document.createElement("tr")
            row.classList.add("pyc-infra__row")

            const id_cell = document.createElement("td")
            const link = document.createElement("a")
            link.classList.add("pyc-infra__run-link")
            link.setAttribute(
                "href",
                build_provisioning_detail_link(run.project_id, run.run_id),
            )
            link.textContent = short_id(run.run_id)
            link.title = run.run_id
            id_cell.appendChild(link)
            row.appendChild(id_cell)

            const action_cell = document.createElement("td")
            action_cell.textContent = run.action
            row.appendChild(action_cell)

            const driver_cell = document.createElement("td")
            driver_cell.textContent = run.driver_name
            row.appendChild(driver_cell)

            const state_cell = document.createElement("td")
            const badge = document.createElement("span")
            badge.classList.add("pyc-infra__badge")
            badge.setAttribute("data-tone", provisioning_state_tone(run.state))
            badge.textContent = run.state
            state_cell.appendChild(badge)
            row.appendChild(state_cell)

            const started_cell = document.createElement("td")
            started_cell.textContent = format_timestamp(run.started_at)
            row.appendChild(started_cell)

            const finished_cell = document.createElement("td")
            finished_cell.textContent = format_timestamp(run.finished_at)
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
     * Toggle the inline trigger-provisioning form's visibility,
     * rendering it on first reveal.
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
     * Render the trigger-provisioning form -- an environment
     * selector, a driver-name input, an action selector, a
     * driver-inputs JSON textarea, and a submit button.
     */
    private _render_trigger_form(): void {
        if (this._trigger_region === null) {
            return
        }
        const form = document.createElement("form")
        form.classList.add("pyc-infra__form")
        form.setAttribute("data-role", "trigger-form")

        const environment_label = document.createElement("label")
        environment_label.classList.add("pyc-infra__field")
        environment_label.textContent = "Environment"
        const environment_select = document.createElement("select")
        environment_select.classList.add("pyc-infra__select")
        environment_select.setAttribute("data-role", "trigger-environment")
        if (this._environments.length === 0) {
            const none_option = document.createElement("option")
            none_option.value = ""
            none_option.textContent = "No environment registered"
            environment_select.appendChild(none_option)
        } else {
            for (const environment of this._environments) {
                const option = document.createElement("option")
                option.value = environment.environment_id
                option.textContent = environment.name + " · " +
                    environment.kind_name
                environment_select.appendChild(option)
            }
        }
        environment_label.appendChild(environment_select)
        form.appendChild(environment_label)

        const driver_label = document.createElement("label")
        driver_label.classList.add("pyc-infra__field")
        driver_label.textContent = "Driver name"
        const driver_input = document.createElement("input")
        driver_input.classList.add("pyc-infra__input")
        driver_input.setAttribute("type", "text")
        driver_input.setAttribute("placeholder", "terraform")
        driver_input.setAttribute("data-role", "trigger-driver")
        driver_input.required = true
        driver_label.appendChild(driver_input)
        form.appendChild(driver_label)

        const action_label = document.createElement("label")
        action_label.classList.add("pyc-infra__field")
        action_label.textContent = "Action"
        const action_select = document.createElement("select")
        action_select.classList.add("pyc-infra__select")
        action_select.setAttribute("data-role", "trigger-action")
        for (const action of PROVISIONING_ACTIONS) {
            const option = document.createElement("option")
            option.value = action
            option.textContent = action
            action_select.appendChild(option)
        }
        action_label.appendChild(action_select)
        form.appendChild(action_label)

        const inputs_label = document.createElement("label")
        inputs_label.classList.add(
            "pyc-infra__field",
            "pyc-infra__field--wide",
        )
        inputs_label.textContent = "Driver inputs (JSON)"
        const inputs_area = document.createElement("textarea")
        inputs_area.classList.add("pyc-infra__textarea")
        inputs_area.setAttribute("data-role", "trigger-driver-inputs")
        inputs_area.setAttribute("placeholder", '{"auto_approve": false}')
        inputs_area.rows = 3
        inputs_label.appendChild(inputs_area)
        form.appendChild(inputs_label)

        const submit_button = document.createElement("button")
        submit_button.classList.add("pyc-infra__submit")
        submit_button.setAttribute("type", "submit")
        submit_button.setAttribute("data-role", "trigger-submit")
        submit_button.textContent = "Trigger Provisioning"
        form.appendChild(submit_button)

        const status = document.createElement("p")
        status.classList.add("pyc-infra__form-status")
        status.setAttribute("data-role", "trigger-status")
        form.appendChild(status)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_trigger(
                form,
                environment_select,
                driver_input,
                action_select,
                inputs_area,
                submit_button,
            )
        })

        this._trigger_region.replaceChildren(form)
        return
    }

    private async _submit_trigger(
        form: HTMLFormElement,
        environment_select: HTMLSelectElement,
        driver_input: HTMLInputElement,
        action_select: HTMLSelectElement,
        inputs_area: HTMLTextAreaElement,
        submit_button: HTMLButtonElement,
    ): Promise<void> {
        const status = form.querySelector('[data-role="trigger-status"]')
        const environment_id = environment_select.value
        const driver_name = driver_input.value.trim()
        const action = action_select.value
        if (environment_id.length === 0) {
            if (status instanceof HTMLElement) {
                status.textContent = "Select a target environment."
            }
            return
        }
        if (driver_name.length === 0) {
            if (status instanceof HTMLElement) {
                status.textContent = "Driver name is required."
            }
            return
        }
        let driver_inputs: Record<string, unknown> = {}
        try {
            driver_inputs = parse_driver_inputs(inputs_area.value)
        } catch (reason: unknown) {
            if (status instanceof HTMLElement) {
                status.textContent = "Driver inputs must be valid JSON."
            }
            console.warn(
                "pychestrate.ui.infra.trigger_inputs_invalid",
                { reason: String(reason) },
            )
            return
        }

        submit_button.disabled = true
        if (status instanceof HTMLElement) {
            status.textContent = "Triggering provisioning run…"
        }
        const outcome = await this._do_trigger(
            environment_id,
            driver_name,
            action,
            driver_inputs,
        )
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

    /**
     * POST a ``ProvisioningRunCreateRequest``. Exposed so unit
     * tests can invoke a trigger without a real form-submit event.
     *
     * @param environment_id Bound target environment id.
     * @param driver_name Registered infra-tool driver factory name.
     * @param action ``"plan"`` | ``"apply"`` | ``"destroy"``.
     * @param driver_inputs Free-form driver inputs object.
     *
     * @returns The trigger outcome.
     */
    public async triggerProvisioning(
        environment_id: string,
        driver_name: string,
        action: string,
        driver_inputs: Record<string, unknown>,
    ): Promise<TriggerOutcome> {
        const rtnval = await this._do_trigger(
            environment_id,
            driver_name,
            action,
            driver_inputs,
        )
        return rtnval
    }

    private async _do_trigger(
        environment_id: string,
        driver_name: string,
        action: string,
        driver_inputs: Record<string, unknown>,
    ): Promise<TriggerOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: TriggerOutcome = {
                ok: false,
                status: 0,
                runId: "",
                message: "Select a project before triggering a run.",
            }
            return rtnval
        }
        const payload: Record<string, unknown> = {
            environment_id: environment_id,
            driver_name: driver_name,
            action: action,
            driver_inputs: driver_inputs,
        }
        let status = 0
        let run_id = ""
        try {
            const url = build_provisioning_collection_url(
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
                const run = body as ProvisioningRun
                if (run !== null && typeof run.run_id === "string") {
                    run_id = run.run_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.infra.trigger_failed",
                { reason: String(reason) },
            )
            const rtnval: TriggerOutcome = {
                ok: false,
                status: 0,
                runId: "",
                message: "Failed to reach the provisioning service.",
            }
            return rtnval
        }
        const ok = status === 202 || status === 200 || status === 201
        const rtnval: TriggerOutcome = {
            ok: ok,
            status: status,
            runId: run_id,
            message: trigger_message_for_status(status),
        }
        return rtnval
    }

    /**
     * Render a dismissible toast for a trigger outcome -- on
     * success the toast links to the new run's detail page.
     *
     * @param outcome The trigger-provisioning outcome.
     */
    private _show_trigger_toast(outcome: TriggerOutcome): void {
        if (this._toast_region === null) {
            return
        }
        const toast = document.createElement("div")
        toast.classList.add("pyc-infra__toast")
        toast.setAttribute("data-role", "trigger-toast")
        toast.setAttribute("data-tone", outcome.ok === true ? "ok" : "error")

        const message = document.createElement("span")
        message.classList.add("pyc-infra__toast-message")
        message.textContent = outcome.message
        toast.appendChild(message)

        if (outcome.ok === true && outcome.runId.length > 0) {
            const link = document.createElement("a")
            link.classList.add("pyc-infra__toast-link")
            link.setAttribute(
                "href",
                build_provisioning_detail_link(
                    this._state.projectId,
                    outcome.runId,
                ),
            )
            link.setAttribute("data-role", "trigger-toast-link")
            link.textContent = "View run"
            toast.appendChild(link)
        }

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
