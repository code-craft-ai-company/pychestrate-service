/**
 * ``<pyc-test-catalog>`` -- the test-catalog view Custom Element.
 *
 * On mount the element renders a project selector, then on a
 * project selection fetches that project's test catalog via
 * ``GET /api/v1/projects/{project_id}/test-catalog`` and renders a
 * paginated table. Two operator actions hang off the view:
 *
 * 1. **Import from testbase** -- opens an inline form (testbase
 *    project root path / reference) and POSTs
 *    ``…/test-catalog:import``; on completion the catalog reloads.
 * 2. **Trigger Run** (per entry) -- POSTs a ``TestRunCreateRequest``
 *    to ``…/test-runs``; on a 202 + ``Run`` a toast surfaces a link
 *    to ``/runs/{run_id}`` (the run-detail page). On a 409 it shows
 *    the "no eligible pod" guidance.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state lives in instance fields.
 *
 * Project listing: the REST surface does not (yet) publish a
 * ``GET /api/v1/projects`` collection. The selector therefore
 * attempts that endpoint and -- when it 404s or is otherwise
 * unavailable -- gracefully degrades to a manual project-id text
 * entry. This keeps the page functional on the live alpha while
 * remaining forward-compatible with a future projects list.
 */

/**
 * One test-catalog entry, as returned in the ``items`` array of a
 * ``TestCatalogEntryPage``. Only the fields the view renders are
 * typed here. Mirrors ``TestCatalogEntry`` in
 * ``specs/openapi/pychestrate.yaml``.
 */
export interface TestCatalogEntry {
    entry_id: string
    project_id: string
    importer_tag: string
    entry_key: string
    display_name: string
    description?: string | null
    required_capability_tags?: string[] | null
    param_schema?: Record<string, unknown> | null
    retired: boolean
    created_at: string
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
 * The ``TestCatalogEntryPage`` response shape.
 */
export interface CatalogPage {
    items: TestCatalogEntry[]
    meta: PageMeta
}

/**
 * One project, as the project selector consumes it. Mirrors the
 * subset of ``Project`` in ``specs/openapi/pychestrate.yaml`` the
 * dropdown needs.
 */
export interface ProjectOption {
    project_id: string
    slug: string
    display_name: string
}

/**
 * The ``Run`` shape returned by ``POST …/test-runs`` -- only the
 * fields the success toast needs.
 */
export interface TriggeredRun {
    run_id: string
    project_id: string
    state: string
}

/**
 * Outcome of a trigger-run POST, surfaced to the caller / tests.
 */
export interface TriggerOutcome {
    ok: boolean
    status: number
    runId: string
    message: string
}

/**
 * The current project + pagination state of the catalog view.
 * Exposed so unit tests can assert state transitions without
 * scraping the DOM.
 */
export interface CatalogViewState {
    projectId: string
    page: number
    perPage: number
    total: number
    includeRetired: boolean
    loading: boolean
    errored: boolean
}

/**
 * Default page size requested from the catalog endpoint.
 */
const DEFAULT_PER_PAGE: number = 25

/**
 * Base path of the projects REST collection.
 */
const PROJECTS_API_PATH: string = "/api/v1/projects"

/**
 * Build the ``GET …/test-catalog`` query URL from the supplied
 * project id and pagination state.
 *
 * @param state Current catalog view state.
 *
 * @returns A relative URL string including the query string.
 */
export function build_catalog_query_url(state: CatalogViewState): string {
    const params = new URLSearchParams()
    params.set("page", String(state.page))
    params.set("per_page", String(state.perPage))
    if (state.includeRetired === true) {
        params.set("include_retired", "true")
    }
    const query = params.toString()
    const rtnval = PROJECTS_API_PATH + "/" + encodeURIComponent(state.projectId) +
        "/test-catalog?" + query
    return rtnval
}

/**
 * Build the ``POST …/test-runs`` URL for a project.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_test_runs_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/test-runs"
    return rtnval
}

/**
 * Build the ``POST …/test-catalog:import`` URL for a project.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_catalog_import_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/test-catalog:import"
    return rtnval
}

/**
 * Summarise an entry's required-capability tags for compact table
 * display. Returns an em-dash placeholder when the entry declares
 * no capability tags.
 *
 * @param entry A catalog entry.
 *
 * @returns A short, human-scannable capability summary.
 */
export function selection_summary(entry: TestCatalogEntry): string {
    const tags = entry.required_capability_tags
    if (tags === null || tags === undefined || tags.length === 0) {
        const rtnval = "—"
        return rtnval
    }
    const rtnval = tags.join(", ")
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
 * Compute whether a "next page" control should be enabled given
 * the current page, page size, and known total.
 *
 * @param state Current catalog view state.
 *
 * @returns True when a further page of results exists.
 */
export function has_next_page(state: CatalogViewState): boolean {
    const consumed = state.page * state.perPage
    const rtnval = consumed < state.total
    return rtnval
}

/**
 * Compute whether a "previous page" control should be enabled.
 *
 * @param state Current catalog view state.
 *
 * @returns True when the caller is not on the first page.
 */
export function has_previous_page(state: CatalogViewState): boolean {
    const rtnval = state.page > 1
    return rtnval
}

/**
 * Translate a trigger-run HTTP response status into the operator
 * guidance message the toast surfaces. A 409 carries the dedicated
 * "no eligible pod" guidance per the orchestration design.
 *
 * @param status HTTP status code of the trigger-run response.
 *
 * @returns A human-readable message for the toast / notice.
 */
export function trigger_message_for_status(status: number): string {
    if (status === 202 || status === 200 || status === 201) {
        const rtnval = "Run triggered."
        return rtnval
    }
    if (status === 409) {
        const rtnval =
            "No client/pod is enrolled and available — enroll a client first."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown project or catalog entry."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to trigger runs."
        return rtnval
    }
    const rtnval = "Failed to trigger run (HTTP " + String(status) + ")."
    return rtnval
}

/**
 * The test-catalog view Custom Element. Register it with
 * ``customElements.define("pyc-test-catalog", PycTestCatalog)``.
 */
export class PycTestCatalog extends HTMLElement {
    private _state: CatalogViewState
    private _entries: TestCatalogEntry[]
    private _projects: ProjectOption[]
    private _projectsAvailable: boolean
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null
    private _import_region: HTMLElement | null
    private _toast_region: HTMLElement | null

    public constructor() {
        super()
        this._state = {
            projectId: "",
            page: 1,
            perPage: DEFAULT_PER_PAGE,
            total: 0,
            includeRetired: false,
            loading: false,
            errored: false,
        }
        this._entries = []
        this._projects = []
        this._projectsAvailable = false
        this._root = null
        this._table_region = null
        this._import_region = null
        this._toast_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * project + pagination state without scraping the DOM.
     */
    public get viewState(): CatalogViewState {
        const rtnval = {
            projectId: this._state.projectId,
            page: this._state.page,
            perPage: this._state.perPage,
            total: this._state.total,
            includeRetired: this._state.includeRetired,
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
     * import action, table region, pager, and toast region.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-catalog")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-catalog__heading")
        heading.textContent = "Test Catalog"
        root.appendChild(heading)

        const controls = document.createElement("div")
        controls.classList.add("pyc-catalog__controls")

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-catalog__field")
        project_label.textContent = "Project"
        const project_select = document.createElement("select")
        project_select.classList.add("pyc-catalog__select")
        project_select.setAttribute("data-role", "project-select")
        project_select.addEventListener("change", () => {
            this._state.projectId = project_select.value
            this._state.page = 1
            void this._refresh()
        })
        project_label.appendChild(project_select)
        controls.appendChild(project_label)

        const project_input = document.createElement("input")
        project_input.classList.add("pyc-catalog__input")
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

        const retired_label = document.createElement("label")
        retired_label.classList.add("pyc-catalog__checkbox")
        const retired_input = document.createElement("input")
        retired_input.setAttribute("type", "checkbox")
        retired_input.setAttribute("data-role", "include-retired")
        retired_input.addEventListener("change", () => {
            this._state.includeRetired = retired_input.checked
            this._state.page = 1
            void this._refresh()
        })
        retired_label.appendChild(retired_input)
        const retired_text = document.createElement("span")
        retired_text.textContent = "Include retired"
        retired_label.appendChild(retired_text)
        controls.appendChild(retired_label)

        const import_button = document.createElement("button")
        import_button.classList.add("pyc-catalog__button")
        import_button.setAttribute("type", "button")
        import_button.setAttribute("data-role", "import-toggle")
        import_button.textContent = "Import from testbase"
        import_button.addEventListener("click", () => {
            this._toggle_import_form()
        })
        controls.appendChild(import_button)

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-catalog__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            void this._refresh()
        })
        controls.appendChild(refresh_button)

        root.appendChild(controls)

        const import_region = document.createElement("div")
        import_region.classList.add("pyc-catalog__import-region")
        import_region.setAttribute("data-role", "import-region")
        import_region.hidden = true
        root.appendChild(import_region)
        this._import_region = import_region

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-catalog__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const pager = document.createElement("div")
        pager.classList.add("pyc-catalog__pager")

        const prev_button = document.createElement("button")
        prev_button.classList.add("pyc-catalog__button")
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
        page_indicator.classList.add("pyc-catalog__page-indicator")
        page_indicator.setAttribute("data-role", "page-indicator")
        pager.appendChild(page_indicator)

        const next_button = document.createElement("button")
        next_button.classList.add("pyc-catalog__button")
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

        const toast_region = document.createElement("div")
        toast_region.classList.add("pyc-catalog__toast-region")
        toast_region.setAttribute("data-role", "toast-region")
        toast_region.setAttribute("aria-live", "polite")
        root.appendChild(toast_region)
        this._toast_region = toast_region

        this._root = root
        this.replaceChildren(root)
        this._render_table_region()
        return
    }

    /**
     * Fetch the projects collection to populate the selector. When
     * the endpoint is unavailable (404 / network / non-array body)
     * the selector falls back to a manual project-id text input.
     * Exposed so unit tests can await the load cycle.
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
                "pychestrate.ui.catalog.projects_fetch_failed",
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
            const project_id = record["project_id"]
            if (typeof project_id !== "string" || project_id.length === 0) {
                continue
            }
            const slug = typeof record["slug"] === "string"
                ? (record["slug"] as string)
                : project_id
            const display_name = typeof record["display_name"] === "string"
                ? (record["display_name"] as string)
                : slug
            rtnval.push({
                project_id: project_id,
                slug: slug,
                display_name: display_name,
            })
        }
        return rtnval
    }

    /**
     * Render either the project ``<select>`` (when a projects list
     * is available) or the manual project-id ``<input>`` fallback.
     */
    private _render_project_control(): void {
        if (this._root === null) {
            return
        }
        const select = this._root.querySelector('[data-role="project-select"]')
        const input = this._root.querySelector('[data-role="project-input"]')
        if (select instanceof HTMLSelectElement) {
            if (this._projectsAvailable === true) {
                select.hidden = false
                select.replaceChildren()
                for (const project of this._projects) {
                    const option = document.createElement("option")
                    option.value = project.project_id
                    option.textContent = project.display_name
                    select.appendChild(option)
                }
                select.value = this._state.projectId
            } else {
                select.hidden = true
            }
        }
        if (input instanceof HTMLInputElement) {
            input.hidden = this._projectsAvailable === true
        }
        return
    }

    /**
     * Fetch the current catalog page from the REST endpoint and
     * re-render the table region. Drives the loading / error /
     * empty states. Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.projectId.length === 0) {
            this._entries = []
            this._render_table_region()
            return
        }
        this._state.loading = true
        this._state.errored = false
        this._render_table_region()

        const url = build_catalog_query_url(this._state)
        let page: CatalogPage | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "catalog fetch failed: HTTP " + String(response.status),
                )
            }
            const body = await response.json()
            page = body as CatalogPage
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.catalog.list_fetch_failed",
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

        this._entries = page.items
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
     * Re-render the table region from the current state + entries.
     */
    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.projectId.length === 0) {
            const prompt = document.createElement("p")
            prompt.classList.add("pyc-catalog__status")
            prompt.setAttribute("data-role", "no-project-state")
            prompt.textContent = "Select a project to view its test catalog."
            region.replaceChildren(prompt)
            this._render_pager()
            return
        }

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-catalog__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading catalog…"
            region.replaceChildren(loading)
            this._render_pager()
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-catalog__status",
                "pyc-catalog__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load the catalog. Try refreshing."
            region.replaceChildren(error)
            this._render_pager()
            return
        }

        if (this._entries.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-catalog__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent =
                "No catalog entries yet. Import from testbase to populate."
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
     * Build the catalog ``<table>`` from the current entries list.
     */
    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-catalog__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Entry", "Name", "Capabilities", "Importer", "Created", "Action",
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
        for (const entry of this._entries) {
            const row = document.createElement("tr")
            row.classList.add("pyc-catalog__row")
            if (entry.retired === true) {
                row.classList.add("pyc-catalog__row--retired")
            }

            const key_cell = document.createElement("td")
            const key_code = document.createElement("code")
            key_code.classList.add("pyc-catalog__entry-key")
            key_code.textContent = entry.entry_key
            key_cell.appendChild(key_code)
            row.appendChild(key_cell)

            const name_cell = document.createElement("td")
            name_cell.textContent = entry.display_name
            row.appendChild(name_cell)

            const caps_cell = document.createElement("td")
            caps_cell.textContent = selection_summary(entry)
            row.appendChild(caps_cell)

            const importer_cell = document.createElement("td")
            importer_cell.textContent = entry.importer_tag
            row.appendChild(importer_cell)

            const created_cell = document.createElement("td")
            created_cell.textContent = format_timestamp(entry.created_at)
            row.appendChild(created_cell)

            const action_cell = document.createElement("td")
            const trigger_button = document.createElement("button")
            trigger_button.classList.add("pyc-catalog__trigger")
            trigger_button.setAttribute("type", "button")
            trigger_button.setAttribute("data-role", "trigger-run")
            trigger_button.setAttribute("data-entry-id", entry.entry_id)
            trigger_button.textContent = "Trigger Run"
            trigger_button.disabled = entry.retired === true
            trigger_button.addEventListener("click", () => {
                void this._trigger_run(entry, trigger_button)
            })
            action_cell.appendChild(trigger_button)
            row.appendChild(action_cell)

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
     * Show / hide the inline import form. The form collects a
     * testbase importer tag and a source root reference, then POSTs
     * ``…/test-catalog:import``.
     */
    private _toggle_import_form(): void {
        if (this._import_region === null) {
            return
        }
        const region = this._import_region
        if (region.hidden === false) {
            region.hidden = true
            region.replaceChildren()
            return
        }
        region.hidden = false

        const form = document.createElement("form")
        form.classList.add("pyc-catalog__import-form")
        form.setAttribute("data-role", "import-form")

        const tag_label = document.createElement("label")
        tag_label.classList.add("pyc-catalog__field")
        tag_label.textContent = "Importer tag"
        const tag_input = document.createElement("input")
        tag_input.classList.add("pyc-catalog__input")
        tag_input.setAttribute("type", "text")
        tag_input.setAttribute("data-role", "import-tag")
        tag_input.setAttribute("placeholder", "testbase-project")
        tag_input.value = "testbase-project"
        tag_label.appendChild(tag_input)
        form.appendChild(tag_label)

        const root_label = document.createElement("label")
        root_label.classList.add("pyc-catalog__field")
        root_label.textContent = "Testbase project root"
        const root_input = document.createElement("input")
        root_input.classList.add("pyc-catalog__input")
        root_input.setAttribute("type", "text")
        root_input.setAttribute("data-role", "import-root")
        root_input.setAttribute("placeholder", "source/testroots/automojo")
        root_label.appendChild(root_input)
        form.appendChild(root_label)

        const ref_label = document.createElement("label")
        ref_label.classList.add("pyc-catalog__field")
        ref_label.textContent = "Reference (optional)"
        const ref_input = document.createElement("input")
        ref_input.classList.add("pyc-catalog__input")
        ref_input.setAttribute("type", "text")
        ref_input.setAttribute("data-role", "import-ref")
        ref_input.setAttribute("placeholder", "main")
        ref_label.appendChild(ref_input)
        form.appendChild(ref_label)

        const submit = document.createElement("button")
        submit.classList.add("pyc-catalog__button")
        submit.setAttribute("type", "submit")
        submit.setAttribute("data-role", "import-submit")
        submit.textContent = "Run import"
        form.appendChild(submit)

        const status = document.createElement("p")
        status.classList.add("pyc-catalog__import-status")
        status.setAttribute("data-role", "import-status")
        form.appendChild(status)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_import(
                tag_input.value.trim(),
                root_input.value.trim(),
                ref_input.value.trim(),
                submit,
                status,
            )
        })

        region.replaceChildren(form)
        return
    }

    /**
     * POST the import request and reload the catalog on completion.
     * Exposed so unit tests can drive the submit path directly.
     *
     * @param importer_tag Importer factory tag.
     * @param source_root Testbase project root path / reference.
     * @param source_ref Optional branch / ref descriptor.
     * @param submit_button The form's submit button (disabled while
     *                      the request is in flight).
     * @param status_node The status paragraph the progress text is
     *                     written to.
     */
    public async submitImport(
        importer_tag: string,
        source_root: string,
        source_ref: string,
        submit_button: HTMLButtonElement | null,
        status_node: HTMLElement | null,
    ): Promise<void> {
        await this._submit_import(
            importer_tag,
            source_root,
            source_ref,
            submit_button,
            status_node,
        )
        return
    }

    private async _submit_import(
        importer_tag: string,
        source_root: string,
        source_ref: string,
        submit_button: HTMLButtonElement | null,
        status_node: HTMLElement | null,
    ): Promise<void> {
        if (this._state.projectId.length === 0) {
            if (status_node !== null) {
                status_node.textContent = "Select a project first."
            }
            return
        }
        if (importer_tag.length === 0) {
            if (status_node !== null) {
                status_node.textContent = "An importer tag is required."
            }
            return
        }

        if (submit_button !== null) {
            submit_button.disabled = true
        }
        if (status_node !== null) {
            status_node.textContent = "Import running…"
        }

        const source: Record<string, string> = {}
        if (source_root.length > 0) {
            source["root"] = source_root
        }
        if (source_ref.length > 0) {
            source["ref"] = source_ref
        }
        const payload: Record<string, unknown> = { importer_tag: importer_tag }
        if (Object.keys(source).length > 0) {
            payload["source"] = source
        }

        const url = build_catalog_import_url(this._state.projectId)
        try {
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            })
            if (response.ok === false) {
                if (status_node !== null) {
                    status_node.textContent =
                        "Import failed (HTTP " + String(response.status) + ")."
                }
                if (submit_button !== null) {
                    submit_button.disabled = false
                }
                return
            }
            const summary = await response.json()
            const imported = (summary as { entries_imported?: number })
                .entries_imported
            const count = typeof imported === "number" ? imported : 0
            if (status_node !== null) {
                status_node.textContent =
                    "Import complete — " + String(count) + " entries imported."
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.catalog.import_failed",
                { reason: String(reason) },
            )
            if (status_node !== null) {
                status_node.textContent = "Import failed — network error."
            }
            if (submit_button !== null) {
                submit_button.disabled = false
            }
            return
        }

        if (submit_button !== null) {
            submit_button.disabled = false
        }
        await this._refresh()
        return
    }

    /**
     * POST a ``TestRunCreateRequest`` for the given catalog entry.
     * Exposed so unit tests can drive the trigger path directly.
     *
     * For PR O the request carries the catalog entry id only; pod
     * selection is left to the server's orchestrator (the UI does
     * not offer a pod picker -- see the module docstring). A 202 +
     * ``Run`` surfaces a success toast with a link to the run
     * detail page; a 409 surfaces the "no eligible pod" guidance.
     *
     * @param entry The catalog entry whose run is being triggered.
     * @param trigger_button The clicked button (disabled while the
     *                        request is in flight). May be null in
     *                        unit-test contexts.
     *
     * @returns The trigger outcome (status + surfaced message).
     */
    public async triggerRun(
        entry: TestCatalogEntry,
        trigger_button: HTMLButtonElement | null,
    ): Promise<TriggerOutcome> {
        const rtnval = await this._trigger_run(entry, trigger_button)
        return rtnval
    }

    private async _trigger_run(
        entry: TestCatalogEntry,
        trigger_button: HTMLButtonElement | null,
    ): Promise<TriggerOutcome> {
        if (trigger_button !== null) {
            trigger_button.disabled = true
        }

        const payload: Record<string, unknown> = {
            catalog_entry_id: entry.entry_id,
        }

        const url = build_test_runs_url(entry.project_id)
        let status = 0
        let run_id = ""
        try {
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
                const triggered = body as TriggeredRun
                if (typeof triggered.run_id === "string") {
                    run_id = triggered.run_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.catalog.trigger_run_failed",
                { reason: String(reason) },
            )
            if (trigger_button !== null) {
                trigger_button.disabled = entry.retired === true
            }
            const failure: TriggerOutcome = {
                ok: false,
                status: 0,
                runId: "",
                message: "Failed to trigger run — network error.",
            }
            this._show_toast(failure)
            return failure
        }

        if (trigger_button !== null) {
            trigger_button.disabled = entry.retired === true
        }

        const ok = status >= 200 && status < 300
        const outcome: TriggerOutcome = {
            ok: ok,
            status: status,
            runId: run_id,
            message: trigger_message_for_status(status),
        }
        this._show_toast(outcome)
        return outcome
    }

    /**
     * Render a transient toast/notice for a trigger-run outcome.
     * On success the toast carries a link to ``/runs/{run_id}``.
     */
    private _show_toast(outcome: TriggerOutcome): void {
        if (this._toast_region === null) {
            return
        }
        const region = this._toast_region

        const toast = document.createElement("div")
        toast.classList.add("pyc-catalog__toast")
        toast.setAttribute("data-role", "trigger-toast")
        const tone = outcome.ok === true ? "ok" : "error"
        toast.setAttribute("data-tone", tone)
        toast.setAttribute("role", "status")

        const message = document.createElement("span")
        message.classList.add("pyc-catalog__toast-message")
        message.textContent = outcome.message
        toast.appendChild(message)

        if (outcome.ok === true && outcome.runId.length > 0) {
            const link = document.createElement("a")
            link.classList.add("pyc-catalog__toast-link")
            link.setAttribute("href", "/runs/" + outcome.runId)
            link.setAttribute("data-role", "run-link")
            link.textContent = "View run"
            toast.appendChild(link)
        }

        const dismiss = document.createElement("button")
        dismiss.classList.add("pyc-catalog__toast-dismiss")
        dismiss.setAttribute("type", "button")
        dismiss.setAttribute("aria-label", "Dismiss notice")
        dismiss.textContent = "×"
        dismiss.addEventListener("click", () => {
            toast.remove()
        })
        toast.appendChild(dismiss)

        region.replaceChildren(toast)
        return
    }
}
