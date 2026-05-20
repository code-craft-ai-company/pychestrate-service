/**
 * ``<pyc-slos>`` -- the per-project SLO list view Custom Element.
 *
 * On mount the element renders a project selector, then on a
 * project selection fetches that project's SLOs via
 * ``GET /api/v1/projects/{project_id}/slos`` and renders a table.
 * Each SLO row carries a "Burn-rate Status" action that reads the
 * per-SLO status block via ``GET …/slos/{slo_id}`` and surfaces
 * the achieved-ratio / error-budget / breaching display.
 *
 * The view also surfaces a "Create SLO" action: an inline form
 * that picks a name + kind + target ratio + window seconds + a
 * free-form definition-config JSON object, then POSTs an
 * ``SloCreateRequest`` to ``…/slos``.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state lives in instance fields.
 *
 * Project listing degrades to a manual project-id text input when
 * the ``GET /api/v1/projects`` collection is unavailable, mirroring
 * the environments / dashboards views.
 */

/**
 * Base path of the projects REST collection.
 */
const PROJECTS_API_PATH: string = "/api/v1/projects"

/**
 * One SLO definition, as returned in the ``items`` array of the
 * SLO list page. Only the fields the view renders are typed.
 */
export interface Slo {
    slo_id: string
    project_id: string
    name: string
    description?: string | null
    kind: string
    target: number
    window_seconds: number
    definition_config?: Record<string, unknown> | null
    default_notification_route_key?: string | null
    auto_attach_burn_rate_alerts?: boolean | null
    version?: number | null
    created_at?: string | null
    updated_at?: string | null
}

/**
 * The per-SLO burn-rate status block embedded in the SLO read
 * response.
 */
export interface SloStatus {
    slo_id: string
    achieved_ratio?: number | null
    error_budget_remaining_ratio?: number | null
    target: number
    window_start?: string | null
    window_end?: string | null
    good_count: number
    total_count: number
    breaching: boolean
    reason?: string | null
}

/**
 * The SLO read response shape -- the SLO definition with an
 * embedded ``status`` block (or ``null`` when status cannot be
 * computed).
 */
export interface SloDetail extends Slo {
    status?: SloStatus | null
}

/**
 * Pagination metadata returned alongside the ``items`` array.
 */
export interface SloPageMeta {
    page: number
    per_page: number
    total: number
}

/**
 * The SLO list page response shape.
 */
export interface SloPage {
    items: Slo[]
    meta: SloPageMeta
}

/**
 * One project, as the project selector consumes it.
 */
export interface SloProjectOption {
    project_id: string
    display_name: string
}

/**
 * Outcome of a create-SLO POST, surfaced to the caller / tests.
 */
export interface SloCreateOutcome {
    ok: boolean
    status: number
    sloId: string
    message: string
}

/**
 * Outcome of a burn-rate-status GET, surfaced to the caller /
 * tests.
 */
export interface SloStatusOutcome {
    ok: boolean
    status: number
    sloStatus: SloStatus | null
    message: string
}

/**
 * The current project + list state of the SLOs view. Exposed so
 * unit tests can assert state transitions.
 */
export interface SlosListState {
    projectId: string
    loading: boolean
    errored: boolean
    total: number
}

/**
 * Build the ``GET …/projects/{project_id}/slos`` query URL.
 *
 * @param project_id Owning project identifier.
 *
 * @returns A relative URL string.
 */
export function build_slos_collection_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/slos"
    return rtnval
}

/**
 * Build the ``GET …/slos/{slo_id}`` URL the burn-rate-status
 * action targets.
 *
 * @param project_id Owning project identifier.
 * @param slo_id SLO identifier.
 *
 * @returns A relative URL string.
 */
export function build_slo_detail_url(
    project_id: string,
    slo_id: string,
): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/slos/" +
        encodeURIComponent(slo_id)
    return rtnval
}

/**
 * Format a 0..1 ratio as a percentage string with one decimal
 * place. Returns an em-dash placeholder for null/undefined.
 *
 * @param value Ratio value or null.
 *
 * @returns A percentage string such as ``"99.5%"`` or ``"—"``.
 */
export function format_ratio(value: number | null | undefined): string {
    if (value === null || value === undefined) {
        const rtnval = "—"
        return rtnval
    }
    if (typeof value !== "number" || Number.isNaN(value) === true) {
        const rtnval = "—"
        return rtnval
    }
    const percent = value * 100
    const rtnval = percent.toFixed(1) + "%"
    return rtnval
}

/**
 * Format a window-seconds count as a human-scannable duration.
 *
 * @param seconds Window length in seconds.
 *
 * @returns A short label such as ``"7d"`` or ``"30m"``.
 */
export function format_window(seconds: number): string {
    if (typeof seconds !== "number" || seconds <= 0) {
        const rtnval = "—"
        return rtnval
    }
    const day = 86400
    const hour = 3600
    const minute = 60
    if (seconds % day === 0) {
        const rtnval = String(seconds / day) + "d"
        return rtnval
    }
    if (seconds % hour === 0) {
        const rtnval = String(seconds / hour) + "h"
        return rtnval
    }
    if (seconds % minute === 0) {
        const rtnval = String(seconds / minute) + "m"
        return rtnval
    }
    const rtnval = String(seconds) + "s"
    return rtnval
}

/**
 * Classify an SLO burn-rate status into a coarse badge tone so the
 * CSS can pick a token-driven color. A breaching SLO surfaces as
 * an error; an SLO with a thin error budget surfaces as a warning.
 *
 * @param status The SLO's burn-rate status, or null.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function slo_status_tone(status: SloStatus | null): string {
    if (status === null) {
        const rtnval = "neutral"
        return rtnval
    }
    if (status.breaching === true) {
        const rtnval = "error"
        return rtnval
    }
    const remaining = status.error_budget_remaining_ratio
    if (typeof remaining === "number" && remaining < 0.25) {
        const rtnval = "warn"
        return rtnval
    }
    const rtnval = "ok"
    return rtnval
}

/**
 * Compose the short human label shown in an SLO row's burn-rate
 * indicator.
 *
 * @param status The SLO's burn-rate status, or null.
 *
 * @returns A short label such as ``"Breaching"`` or ``"99.5%"``.
 */
export function slo_status_label(status: SloStatus | null): string {
    if (status === null) {
        const rtnval = "Not evaluated"
        return rtnval
    }
    if (status.breaching === true) {
        const rtnval = "Breaching"
        return rtnval
    }
    const rtnval = format_ratio(status.achieved_ratio) + " achieved"
    return rtnval
}

/**
 * Translate a create-SLO HTTP status into operator guidance.
 *
 * @param status HTTP status code of the create response.
 *
 * @returns A human-readable message.
 */
export function slo_create_message_for_status(status: number): string {
    if (status === 201 || status === 200) {
        const rtnval = "SLO created."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "An SLO with that name already exists."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "The SLO definition was rejected — check the fields."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown project."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to create SLOs."
        return rtnval
    }
    const rtnval = "Failed to create SLO (HTTP " + String(status) + ")."
    return rtnval
}

/**
 * Parse the definition-config textarea content as JSON. An empty
 * string yields an empty object; malformed JSON throws.
 *
 * @param raw Raw textarea content.
 *
 * @returns A parsed definition-config object.
 * @raises SyntaxError when ``raw`` is not a valid JSON object.
 */
export function parse_definition_config(
    raw: string,
): Record<string, unknown> {
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
        throw new SyntaxError("SLO definition_config must be a JSON object")
    }
    const rtnval = parsed as Record<string, unknown>
    return rtnval
}

/**
 * Normalise a projects-list response body into ``SloProjectOption``
 * records. Accepts both a bare array and a ``{items}`` envelope.
 *
 * @param body Parsed JSON response body.
 *
 * @returns A list of project options (possibly empty).
 */
export function extract_slo_projects(body: unknown): SloProjectOption[] {
    let raw: unknown[] = []
    if (Array.isArray(body) === true) {
        raw = body as unknown[]
    } else if (body !== null && typeof body === "object") {
        const items = (body as { items?: unknown }).items
        if (Array.isArray(items) === true) {
            raw = items as unknown[]
        }
    }
    const rtnval: SloProjectOption[] = []
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
 * The SLO list view Custom Element. Register it with
 * ``customElements.define("pyc-slos", PycSlos)``.
 */
export class PycSlos extends HTMLElement {
    private _state: SlosListState
    private _slos: Slo[]
    private _status: Map<string, SloStatus>
    private _projects: SloProjectOption[]
    private _projectsAvailable: boolean
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null
    private _create_region: HTMLElement | null
    private _toast_region: HTMLElement | null

    public constructor() {
        super()
        this._state = {
            projectId: "",
            loading: false,
            errored: false,
            total: 0,
        }
        this._slos = []
        this._status = new Map<string, SloStatus>()
        this._projects = []
        this._projectsAvailable = false
        this._root = null
        this._table_region = null
        this._create_region = null
        this._toast_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * project + list state without scraping the DOM.
     */
    public get listState(): SlosListState {
        const rtnval = {
            projectId: this._state.projectId,
            loading: this._state.loading,
            errored: this._state.errored,
            total: this._state.total,
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
     * create action, table region, toast region.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-metrics")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-metrics__heading")
        heading.textContent = "Service-Level Objectives"
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
        create_button.textContent = "Create SLO"
        create_button.addEventListener("click", () => {
            this._toggle_create_form()
        })
        controls.appendChild(create_button)

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-metrics__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            void this._refresh()
        })
        controls.appendChild(refresh_button)

        root.appendChild(controls)

        const create_region = document.createElement("div")
        create_region.classList.add("pyc-metrics__form-region")
        create_region.setAttribute("data-role", "create-region")
        create_region.hidden = true
        root.appendChild(create_region)
        this._create_region = create_region

        const toast_region = document.createElement("div")
        toast_region.classList.add("pyc-metrics__toast-region")
        toast_region.setAttribute("data-role", "toast-region")
        root.appendChild(toast_region)
        this._toast_region = toast_region

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
        let projects: SloProjectOption[] | null = null
        try {
            const response = await fetch(PROJECTS_API_PATH, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                projects = extract_slo_projects(body)
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.slo_projects_fetch_failed",
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
     * Fetch the SLO list for the active project and re-render the
     * table. Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.projectId.length === 0) {
            this._slos = []
            this._render_table_region()
            return
        }
        this._state.loading = true
        this._state.errored = false
        this._status = new Map<string, SloStatus>()
        this._render_table_region()

        const url = build_slos_collection_url(this._state.projectId)
        let page: SloPage | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "slos fetch failed: HTTP " + String(response.status),
                )
            }
            const body = await response.json()
            page = body as SloPage
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.slos_fetch_failed",
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

        this._slos = page.items
        const meta = page.meta
        if (meta !== undefined && meta !== null) {
            if (typeof meta.total === "number") {
                this._state.total = meta.total
            }
        }
        this._state.loading = false
        this._state.errored = false
        this._render_table_region()
        return
    }

    /**
     * Re-render the table region from the current state + SLOs.
     */
    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.projectId.length === 0) {
            const notice = document.createElement("p")
            notice.classList.add("pyc-metrics__notice")
            notice.setAttribute("data-role", "no-project-state")
            notice.textContent = "Select a project to view its SLOs."
            region.replaceChildren(notice)
            return
        }

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-metrics__notice")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading SLOs…"
            region.replaceChildren(loading)
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-metrics__notice",
                "pyc-metrics__notice--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load SLOs. Try refreshing."
            region.replaceChildren(error)
            return
        }

        if (this._slos.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-metrics__notice")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No SLOs defined for this project yet"
            region.replaceChildren(empty)
            return
        }

        const table = this._build_table()
        region.replaceChildren(table)
        return
    }

    /**
     * Build the SLOs ``<table>`` from the current list.
     */
    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-metrics__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "SLO",
            "Kind",
            "Target",
            "Window",
            "Burn-rate",
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
        for (const slo of this._slos) {
            tbody.appendChild(this._build_row(slo))
        }
        table.appendChild(tbody)
        return table
    }

    /**
     * Build one SLO table row, including the burn-rate indicator
     * cell and the per-row "Burn-rate Status" action.
     *
     * @param slo The SLO to render.
     *
     * @returns A populated ``<tr>``.
     */
    private _build_row(slo: Slo): HTMLTableRowElement {
        const row = document.createElement("tr")
        row.classList.add("pyc-metrics__row")
        row.setAttribute("data-slo-id", slo.slo_id)

        const name_cell = document.createElement("td")
        const name = document.createElement("span")
        name.textContent = slo.name
        name.title = slo.slo_id
        name_cell.appendChild(name)
        row.appendChild(name_cell)

        const kind_cell = document.createElement("td")
        kind_cell.textContent = slo.kind
        row.appendChild(kind_cell)

        const target_cell = document.createElement("td")
        target_cell.textContent = format_ratio(slo.target)
        row.appendChild(target_cell)

        const window_cell = document.createElement("td")
        window_cell.textContent = format_window(slo.window_seconds)
        row.appendChild(window_cell)

        const burn_cell = document.createElement("td")
        const burn_badge = document.createElement("span")
        burn_badge.classList.add("pyc-metrics__badge")
        burn_badge.setAttribute("data-role", "burn-indicator")
        const status = this._status.get(slo.slo_id) ?? null
        burn_badge.setAttribute("data-tone", slo_status_tone(status))
        burn_badge.textContent = slo_status_label(status)
        burn_cell.appendChild(burn_badge)
        row.appendChild(burn_cell)

        const actions_cell = document.createElement("td")
        const status_button = document.createElement("button")
        status_button.classList.add("pyc-metrics__button")
        status_button.setAttribute("type", "button")
        status_button.setAttribute("data-role", "load-status")
        status_button.textContent = "Burn-rate Status"
        status_button.addEventListener("click", () => {
            status_button.disabled = true
            void this._on_load_status(slo, status_button)
        })
        actions_cell.appendChild(status_button)
        row.appendChild(actions_cell)

        return row
    }

    /**
     * Run the "Burn-rate Status" action for one SLO -- read the
     * status block and update the indicator, surfacing a toast.
     *
     * @param slo The SLO to evaluate.
     * @param button The row action button, re-enabled on completion.
     */
    private async _on_load_status(
        slo: Slo,
        button: HTMLButtonElement,
    ): Promise<void> {
        const outcome = await this._do_load_status(slo.slo_id)
        if (outcome.ok === true && outcome.sloStatus !== null) {
            this._status.set(slo.slo_id, outcome.sloStatus)
            this._render_burn_cell(slo.slo_id)
        }
        button.disabled = false
        this._show_toast(
            outcome.message,
            outcome.ok === true ? "ok" : "error",
        )
        return
    }

    /**
     * Read one SLO's burn-rate status. Exposed so unit tests can
     * drive a status read without a row button.
     *
     * @param slo_id The SLO to read.
     *
     * @returns The status outcome.
     */
    public async loadStatus(slo_id: string): Promise<SloStatusOutcome> {
        const rtnval = await this._do_load_status(slo_id)
        return rtnval
    }

    private async _do_load_status(
        slo_id: string,
    ): Promise<SloStatusOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: SloStatusOutcome = {
                ok: false,
                status: 0,
                sloStatus: null,
                message: "Select a project before reading SLO status.",
            }
            return rtnval
        }
        let status = 0
        let slo_status: SloStatus | null = null
        try {
            const url = build_slo_detail_url(
                this._state.projectId,
                slo_id,
            )
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            status = response.status
            if (response.ok === true) {
                const body = await response.json()
                const detail = body as SloDetail
                if (
                    detail !== null &&
                    detail.status !== undefined &&
                    detail.status !== null
                ) {
                    slo_status = detail.status
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.slo_status_fetch_failed",
                { reason: String(reason) },
            )
            const rtnval: SloStatusOutcome = {
                ok: false,
                status: 0,
                sloStatus: null,
                message: "Failed to reach the SLO service.",
            }
            return rtnval
        }
        if (status === 200) {
            const message = slo_status !== null
                ? "Burn-rate status updated."
                : "This SLO has no burn-rate status yet."
            const rtnval: SloStatusOutcome = {
                ok: true,
                status: status,
                sloStatus: slo_status,
                message: message,
            }
            return rtnval
        }
        const rtnval: SloStatusOutcome = {
            ok: false,
            status: status,
            sloStatus: null,
            message: "Failed to read SLO status (HTTP " +
                String(status) + ").",
        }
        return rtnval
    }

    /**
     * Refresh one SLO's burn-rate indicator cell from the cached
     * status.
     *
     * @param slo_id The SLO whose row to update.
     */
    private _render_burn_cell(slo_id: string): void {
        if (this._table_region === null) {
            return
        }
        const selector =
            'tr[data-slo-id="' + slo_id + '"] ' +
            '[data-role="burn-indicator"]'
        const badge = this._table_region.querySelector(selector)
        if (badge instanceof HTMLElement === false) {
            return
        }
        const el = badge as HTMLElement
        const status = this._status.get(slo_id) ?? null
        el.setAttribute("data-tone", slo_status_tone(status))
        el.textContent = slo_status_label(status)
        return
    }

    /**
     * Toggle the inline create-SLO form's visibility, rendering it
     * on first reveal.
     */
    private _toggle_create_form(): void {
        if (this._create_region === null) {
            return
        }
        const region = this._create_region
        if (region.hidden === true) {
            this._render_create_form()
            region.hidden = false
        } else {
            region.hidden = true
        }
        return
    }

    /**
     * Render the create-SLO form into the create region.
     */
    private _render_create_form(): void {
        if (this._create_region === null) {
            return
        }
        const form = document.createElement("form")
        form.classList.add("pyc-metrics__form")
        form.setAttribute("data-role", "create-form")

        const name_input = this._build_text_field(
            form, "Name", "create-name", "checkout availability",
        )
        const kind_input = this._build_text_field(
            form, "Kind", "create-kind", "availability",
        )
        const target_input = this._build_text_field(
            form, "Target ratio (0..1)", "create-target", "0.995",
        )
        const window_input = this._build_text_field(
            form, "Window (seconds)", "create-window", "604800",
        )

        const config_label = document.createElement("label")
        config_label.classList.add("pyc-metrics__field")
        config_label.textContent = "Definition config (JSON)"
        const config_area = document.createElement("textarea")
        config_area.classList.add("pyc-metrics__input")
        config_area.setAttribute("data-role", "create-config")
        config_area.setAttribute("placeholder", '{"metric": "http_2xx"}')
        config_area.rows = 3
        config_label.appendChild(config_area)
        form.appendChild(config_label)

        const submit_button = document.createElement("button")
        submit_button.classList.add("pyc-metrics__button")
        submit_button.setAttribute("type", "submit")
        submit_button.setAttribute("data-role", "create-submit")
        submit_button.textContent = "Create SLO"
        form.appendChild(submit_button)

        const status = document.createElement("p")
        status.classList.add("pyc-metrics__form-status")
        status.setAttribute("data-role", "create-status")
        form.appendChild(status)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_create(
                form,
                name_input,
                kind_input,
                target_input,
                window_input,
                config_area,
                submit_button,
            )
        })

        this._create_region.replaceChildren(form)
        return
    }

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
    private _build_text_field(
        form: HTMLFormElement,
        label_text: string,
        role: string,
        placeholder: string,
    ): HTMLInputElement {
        const label = document.createElement("label")
        label.classList.add("pyc-metrics__field")
        label.textContent = label_text
        const input = document.createElement("input")
        input.classList.add("pyc-metrics__input")
        input.setAttribute("type", "text")
        input.setAttribute("data-role", role)
        input.setAttribute("placeholder", placeholder)
        label.appendChild(input)
        form.appendChild(label)
        return input
    }

    private async _submit_create(
        form: HTMLFormElement,
        name_input: HTMLInputElement,
        kind_input: HTMLInputElement,
        target_input: HTMLInputElement,
        window_input: HTMLInputElement,
        config_area: HTMLTextAreaElement,
        submit_button: HTMLButtonElement,
    ): Promise<void> {
        const status = form.querySelector('[data-role="create-status"]')
        const name = name_input.value.trim()
        const kind = kind_input.value.trim()
        if (name.length === 0 || kind.length === 0) {
            if (status instanceof HTMLElement) {
                status.textContent = "SLO name and kind are required."
            }
            return
        }
        const target = Number(target_input.value.trim())
        if (Number.isNaN(target) === true) {
            if (status instanceof HTMLElement) {
                status.textContent = "Target ratio must be a number."
            }
            return
        }
        const window_seconds = Number(window_input.value.trim())
        if (
            Number.isNaN(window_seconds) === true ||
            window_seconds <= 0
        ) {
            if (status instanceof HTMLElement) {
                status.textContent =
                    "Window seconds must be a positive number."
            }
            return
        }
        let definition_config: Record<string, unknown> = {}
        try {
            definition_config = parse_definition_config(config_area.value)
        } catch (reason: unknown) {
            if (status instanceof HTMLElement) {
                status.textContent =
                    "Definition config must be valid JSON."
            }
            console.warn(
                "pychestrate.ui.metrics.slo_config_invalid",
                { reason: String(reason) },
            )
            return
        }

        submit_button.disabled = true
        if (status instanceof HTMLElement) {
            status.textContent = "Creating SLO…"
        }
        const outcome = await this._do_create(
            name,
            kind,
            target,
            window_seconds,
            definition_config,
        )
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
     * POST an ``SloCreateRequest``. Exposed so unit tests can
     * invoke a create without a real form-submit event.
     *
     * @param name Human-facing SLO name.
     * @param kind SLO kind (e.g. ``availability``).
     * @param target Target ratio in the 0..1 range.
     * @param window_seconds Rolling evaluation window length.
     * @param definition_config Kind-specific configuration object.
     *
     * @returns The create outcome.
     */
    public async createSlo(
        name: string,
        kind: string,
        target: number,
        window_seconds: number,
        definition_config: Record<string, unknown>,
    ): Promise<SloCreateOutcome> {
        const rtnval = await this._do_create(
            name,
            kind,
            target,
            window_seconds,
            definition_config,
        )
        return rtnval
    }

    private async _do_create(
        name: string,
        kind: string,
        target: number,
        window_seconds: number,
        definition_config: Record<string, unknown>,
    ): Promise<SloCreateOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: SloCreateOutcome = {
                ok: false,
                status: 0,
                sloId: "",
                message: "Select a project before creating an SLO.",
            }
            return rtnval
        }
        const payload: Record<string, unknown> = {
            name: name,
            kind: kind,
            target: target,
            window_seconds: window_seconds,
            definition_config: definition_config,
        }
        let status = 0
        let slo_id = ""
        try {
            const url = build_slos_collection_url(this._state.projectId)
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
                const slo = body as Slo
                if (slo !== null && typeof slo.slo_id === "string") {
                    slo_id = slo.slo_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.slo_create_failed",
                { reason: String(reason) },
            )
            const rtnval: SloCreateOutcome = {
                ok: false,
                status: 0,
                sloId: "",
                message: "Failed to reach the SLO service.",
            }
            return rtnval
        }
        const ok = status === 201 || status === 200
        const rtnval: SloCreateOutcome = {
            ok: ok,
            status: status,
            sloId: slo_id,
            message: slo_create_message_for_status(status),
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
        toast.classList.add("pyc-metrics__toast")
        toast.setAttribute("data-role", "toast")
        toast.setAttribute("data-tone", tone)

        const text = document.createElement("span")
        text.textContent = message
        toast.appendChild(text)

        const dismiss = document.createElement("button")
        dismiss.classList.add("pyc-metrics__toast-dismiss")
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
