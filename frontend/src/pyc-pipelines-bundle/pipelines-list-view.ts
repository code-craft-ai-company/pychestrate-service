/**
 * ``<pyc-pipelines-list>`` -- the pipeline-definitions list view
 * Custom Element.
 *
 * On mount the element renders a project selector, then on a
 * project selection fetches that project's cached pipeline
 * definitions via
 * ``GET /api/v1/projects/{project_id}/pipelines`` and renders a
 * paginated table. Each row links to ``/pipelines/{pipeline_id}``
 * -- the pipeline-detail page.
 *
 * The view surfaces two project-scoped pipeline actions:
 *
 * 1. A "Create / Upsert Pipeline" form -- a textarea for the raw
 *    pipeline-definition document (YAML or JSON), plus the
 *    ``commit_sha`` + ``filename`` fields the
 *    ``PipelineDefinitionCreateRequest`` requires. A "Validate"
 *    button POSTs ``…/pipelines:validate`` (pure DAG validation --
 *    cycle / stage-reference checks) and surfaces the topological
 *    order or the issue list. A "Save" button POSTs
 *    ``…/pipelines`` to upsert the definition.
 * 2. A "Matrix Expand Preview" panel -- a small matrix-spec JSON
 *    input plus a button that POSTs ``…/pipelines:expand-matrix``
 *    and shows the resulting shard count + shard list.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state lives in instance fields.
 *
 * Pipeline run / dispatch is intentionally absent: per PR #233 the
 * dispatch surface is unwired, so this view is definition +
 * validation + matrix-preview only. A pipeline-run UI is a
 * follow-up.
 */

/**
 * One step inside a pipeline stage. Mirrors the ``PipelineStep``
 * schema in ``specs/openapi/pychestrate.yaml``.
 */
export interface PipelineStep {
    step_id: string
    kind_name: string
    uses?: string | null
    inputs?: Record<string, unknown> | null
}

/**
 * One stage of a pipeline DAG. Mirrors the ``PipelineStage``
 * schema -- ``needs`` names the stage ids this stage depends on.
 */
export interface PipelineStage {
    stage_id: string
    when_clause?: string | null
    needs?: string[] | null
    steps: PipelineStep[]
}

/**
 * A parsed + DAG-validated + canonicalized pipeline-definition
 * document. Mirrors the ``PipelineDefinition`` schema.
 */
export interface PipelineDefinition {
    pipeline_id: string
    project_id: string
    name: string
    schema_version: number
    commit_sha?: string | null
    filename?: string | null
    stages: PipelineStage[]
    cached_at?: string | null
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
 * The ``PipelineDefinitionPage`` response shape.
 */
export interface PipelineDefinitionPage {
    items: PipelineDefinition[]
    meta: PageMeta
}

/**
 * One project, as the project selector consumes it.
 */
export interface ProjectOption {
    project_id: string
    display_name: string
}

/**
 * Outcome of a DAG-validate POST, surfaced to the caller / tests.
 * Mirrors the ``DagValidationResult`` schema.
 */
export interface ValidateOutcome {
    ok: boolean
    status: number
    valid: boolean
    stageCount: number
    topologicalOrder: string[]
    issues: string[]
    message: string
}

/**
 * Outcome of a pipeline upsert POST.
 */
export interface UpsertOutcome {
    ok: boolean
    status: number
    pipelineId: string
    message: string
}

/**
 * One shard of a matrix-expansion preview. Mirrors the
 * ``ShardExpansionShard`` schema.
 */
export interface ExpansionShard {
    shard_id: string
    parallel_group: string
    sequence_in_group: number
    dimension_values?: Record<string, string> | null
}

/**
 * Outcome of a matrix-expand POST. Mirrors the ``ShardExpansion``
 * schema plus transport status.
 */
export interface MatrixExpandOutcome {
    ok: boolean
    status: number
    strategyName: string
    shardCount: number
    shards: ExpansionShard[]
    message: string
}

/**
 * The current project + pagination state of the list view.
 * Exposed so unit tests can assert state transitions without
 * rendering.
 */
export interface PipelinesListState {
    projectId: string
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
 * Build the ``GET …/projects/{project_id}/pipelines`` query URL
 * from the supplied project id + pagination state.
 *
 * @param state Current pipelines list state.
 *
 * @returns A relative URL string including the query string.
 */
export function build_pipelines_query_url(state: PipelinesListState): string {
    const params = new URLSearchParams()
    params.set("page", String(state.page))
    params.set("per_page", String(state.perPage))
    const query = params.toString()
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(state.projectId) + "/pipelines?" + query
    return rtnval
}

/**
 * Build the ``POST …/projects/{project_id}/pipelines`` URL used by
 * the upsert action.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_pipelines_collection_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/pipelines"
    return rtnval
}

/**
 * Build the ``POST …/projects/{project_id}/pipelines:validate``
 * project-scoped action URL.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_pipelines_validate_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/pipelines:validate"
    return rtnval
}

/**
 * Build the ``POST …/projects/{project_id}/pipelines:expand-matrix``
 * project-scoped action URL.
 *
 * @param project_id Project identifier.
 *
 * @returns A relative URL string.
 */
export function build_pipelines_expand_matrix_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/pipelines:expand-matrix"
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
 * Compute whether a "next page" control should be enabled.
 *
 * @param state Current pipelines list state.
 *
 * @returns True when a further page of results exists.
 */
export function has_next_page(state: PipelinesListState): boolean {
    const consumed = state.page * state.perPage
    const rtnval = consumed < state.total
    return rtnval
}

/**
 * Compute whether a "previous page" control should be enabled.
 *
 * @param state Current pipelines list state.
 *
 * @returns True when the caller is not on the first page.
 */
export function has_previous_page(state: PipelinesListState): boolean {
    const rtnval = state.page > 1
    return rtnval
}

/**
 * Parse the matrix-spec textarea content as a JSON ``MatrixSpec``
 * object. An empty string is rejected -- the matrix is required.
 *
 * @param raw Raw textarea content.
 *
 * @returns A parsed matrix-spec object.
 * @raises SyntaxError when ``raw`` is empty or not a JSON object.
 */
export function parse_matrix_spec(raw: string): Record<string, unknown> {
    if (typeof raw !== "string" || raw.trim().length === 0) {
        throw new SyntaxError("matrix spec is required")
    }
    const parsed = JSON.parse(raw)
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed) === true) {
        throw new SyntaxError("matrix spec must be a JSON object")
    }
    const rtnval = parsed as Record<string, unknown>
    return rtnval
}

/**
 * Translate a validate-action HTTP status into operator guidance.
 *
 * @param status HTTP status code of the validate response.
 * @param valid Whether the parsed body reported a valid DAG.
 *
 * @returns A human-readable message.
 */
export function validate_message_for_status(
    status: number,
    valid: boolean,
): string {
    if (status === 200 && valid === true) {
        const rtnval = "Pipeline definition is a valid DAG."
        return rtnval
    }
    if (status === 200 && valid === false) {
        const rtnval = "Pipeline definition has DAG issues."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "Pipeline definition is not a valid DAG."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown project."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to validate pipelines."
        return rtnval
    }
    const rtnval = "Failed to validate pipeline (HTTP " + String(status) + ")."
    return rtnval
}

/**
 * The pipelines list view Custom Element. Register it with
 * ``customElements.define("pyc-pipelines-list", PycPipelinesList)``.
 */
export class PycPipelinesList extends HTMLElement {
    private _state: PipelinesListState
    private _pipelines: PipelineDefinition[]
    private _projects: ProjectOption[]
    private _projectsAvailable: boolean
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null
    private _form_status: HTMLElement | null
    private _matrix_region: HTMLElement | null

    public constructor() {
        super()
        this._state = {
            projectId: "",
            page: 1,
            perPage: DEFAULT_PER_PAGE,
            total: 0,
            loading: false,
            errored: false,
        }
        this._pipelines = []
        this._projects = []
        this._projectsAvailable = false
        this._root = null
        this._table_region = null
        this._form_status = null
        this._matrix_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * project + pagination state without scraping the DOM.
     */
    public get listState(): PipelinesListState {
        const rtnval = {
            projectId: this._state.projectId,
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
     * the upsert form, the matrix-expand panel, and the table.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-pipelines")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-pipelines__heading")
        heading.textContent = "Pipelines"
        root.appendChild(heading)

        const controls = document.createElement("div")
        controls.classList.add("pyc-pipelines__controls")

        const project_label = document.createElement("label")
        project_label.classList.add("pyc-pipelines__field")
        project_label.textContent = "Project"
        const project_select = document.createElement("select")
        project_select.classList.add("pyc-pipelines__select")
        project_select.setAttribute("data-role", "project-select")
        project_select.addEventListener("change", () => {
            this._state.projectId = project_select.value
            this._state.page = 1
            void this._refresh()
        })
        project_label.appendChild(project_select)
        controls.appendChild(project_label)

        const project_input = document.createElement("input")
        project_input.classList.add("pyc-pipelines__input")
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

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-pipelines__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            void this._refresh()
        })
        controls.appendChild(refresh_button)

        root.appendChild(controls)

        root.appendChild(this._build_upsert_form())
        root.appendChild(this._build_matrix_panel())

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-pipelines__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const pager = document.createElement("div")
        pager.classList.add("pyc-pipelines__pager")

        const prev_button = document.createElement("button")
        prev_button.classList.add("pyc-pipelines__button")
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
        page_indicator.classList.add("pyc-pipelines__page-indicator")
        page_indicator.setAttribute("data-role", "page-indicator")
        pager.appendChild(page_indicator)

        const next_button = document.createElement("button")
        next_button.classList.add("pyc-pipelines__button")
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
     * Build the create / upsert form -- the document textarea, the
     * commit-sha + filename inputs, and the Validate + Save
     * buttons.
     *
     * @returns The populated upsert-form section element.
     */
    private _build_upsert_form(): HTMLElement {
        const panel = document.createElement("section")
        panel.classList.add("pyc-pipelines__panel")
        panel.setAttribute("data-role", "upsert-panel")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-pipelines__panel-heading")
        heading.textContent = "Create / Upsert Pipeline"
        panel.appendChild(heading)

        const form = document.createElement("form")
        form.classList.add("pyc-pipelines__form")
        form.setAttribute("data-role", "upsert-form")

        const fields = document.createElement("div")
        fields.classList.add("pyc-pipelines__field-row")

        const commit_label = document.createElement("label")
        commit_label.classList.add("pyc-pipelines__field")
        commit_label.textContent = "Commit SHA"
        const commit_input = document.createElement("input")
        commit_input.classList.add("pyc-pipelines__input")
        commit_input.setAttribute("type", "text")
        commit_input.setAttribute("placeholder", "0000000000000000000000000000000000000000")
        commit_input.setAttribute("data-role", "upsert-commit-sha")
        commit_input.required = true
        commit_label.appendChild(commit_input)
        fields.appendChild(commit_label)

        const filename_label = document.createElement("label")
        filename_label.classList.add("pyc-pipelines__field")
        filename_label.textContent = "Filename"
        const filename_input = document.createElement("input")
        filename_input.classList.add("pyc-pipelines__input")
        filename_input.setAttribute("type", "text")
        filename_input.setAttribute("placeholder", "pipeline.yaml")
        filename_input.setAttribute("data-role", "upsert-filename")
        filename_input.required = true
        filename_label.appendChild(filename_input)
        fields.appendChild(filename_label)

        form.appendChild(fields)

        const document_label = document.createElement("label")
        document_label.classList.add("pyc-pipelines__field", "pyc-pipelines__field--wide")
        document_label.textContent = "Pipeline document (YAML / JSON)"
        const document_area = document.createElement("textarea")
        document_area.classList.add("pyc-pipelines__textarea")
        document_area.setAttribute("data-role", "upsert-document")
        document_area.setAttribute(
            "placeholder",
            "name: example\nschema_version: 1\nstages: []",
        )
        document_area.rows = 8
        document_label.appendChild(document_area)
        form.appendChild(document_label)

        const actions = document.createElement("div")
        actions.classList.add("pyc-pipelines__form-actions")

        const validate_button = document.createElement("button")
        validate_button.classList.add("pyc-pipelines__button")
        validate_button.setAttribute("type", "button")
        validate_button.setAttribute("data-role", "validate-submit")
        validate_button.textContent = "Validate"
        validate_button.addEventListener("click", () => {
            void this._submit_validate(commit_input, filename_input, document_area)
        })
        actions.appendChild(validate_button)

        const save_button = document.createElement("button")
        save_button.classList.add("pyc-pipelines__primary")
        save_button.setAttribute("type", "submit")
        save_button.setAttribute("data-role", "save-submit")
        save_button.textContent = "Save"
        actions.appendChild(save_button)

        form.appendChild(actions)

        const status = document.createElement("div")
        status.classList.add("pyc-pipelines__form-status")
        status.setAttribute("data-role", "form-status")
        form.appendChild(status)
        this._form_status = status

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_save(commit_input, filename_input, document_area)
        })

        panel.appendChild(form)
        return panel
    }

    /**
     * Build the matrix-expand preview panel -- a matrix-spec JSON
     * textarea, a strategy-name input, an expand button, and the
     * result region.
     *
     * @returns The populated matrix-panel section element.
     */
    private _build_matrix_panel(): HTMLElement {
        const panel = document.createElement("section")
        panel.classList.add("pyc-pipelines__panel")
        panel.setAttribute("data-role", "matrix-panel")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-pipelines__panel-heading")
        heading.textContent = "Matrix Expand Preview"
        panel.appendChild(heading)

        const matrix_label = document.createElement("label")
        matrix_label.classList.add("pyc-pipelines__field", "pyc-pipelines__field--wide")
        matrix_label.textContent = "Matrix spec (JSON)"
        const matrix_area = document.createElement("textarea")
        matrix_area.classList.add("pyc-pipelines__textarea")
        matrix_area.setAttribute("data-role", "matrix-spec")
        matrix_area.setAttribute(
            "placeholder",
            '{"dimensions": {"os": ["linux", "windows"], "py": ["3.11", "3.12"]}}',
        )
        matrix_area.rows = 4
        matrix_label.appendChild(matrix_area)
        panel.appendChild(matrix_label)

        const strategy_label = document.createElement("label")
        strategy_label.classList.add("pyc-pipelines__field")
        strategy_label.textContent = "Strategy"
        const strategy_input = document.createElement("input")
        strategy_input.classList.add("pyc-pipelines__input")
        strategy_input.setAttribute("type", "text")
        strategy_input.setAttribute("placeholder", "cartesian")
        strategy_input.setAttribute("data-role", "matrix-strategy")
        strategy_label.appendChild(strategy_input)
        panel.appendChild(strategy_label)

        const expand_button = document.createElement("button")
        expand_button.classList.add("pyc-pipelines__button")
        expand_button.setAttribute("type", "button")
        expand_button.setAttribute("data-role", "matrix-expand")
        expand_button.textContent = "Expand Matrix"
        expand_button.addEventListener("click", () => {
            void this._submit_matrix_expand(matrix_area, strategy_input)
        })
        panel.appendChild(expand_button)

        const result = document.createElement("div")
        result.classList.add("pyc-pipelines__matrix-result")
        result.setAttribute("data-role", "matrix-result")
        panel.appendChild(result)
        this._matrix_region = result

        return panel
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
                "pychestrate.ui.pipelines.projects_fetch_failed",
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
     * Fetch the current page of pipelines and re-render the table.
     * Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.projectId.length === 0) {
            this._pipelines = []
            this._render_table_region()
            return
        }
        this._state.loading = true
        this._state.errored = false
        this._render_table_region()

        const url = build_pipelines_query_url(this._state)
        let page: PipelineDefinitionPage | null = null
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error("pipelines fetch failed: HTTP " + String(response.status))
            }
            const body = await response.json()
            page = body as PipelineDefinitionPage
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.pipelines.list_fetch_failed",
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

        this._pipelines = page.items
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
     * pipelines.
     */
    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.projectId.length === 0) {
            const notice = document.createElement("p")
            notice.classList.add("pyc-pipelines__status")
            notice.setAttribute("data-role", "no-project-state")
            notice.textContent = "Select a project to view its pipelines."
            region.replaceChildren(notice)
            this._render_pager()
            return
        }

        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-pipelines__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading pipelines…"
            region.replaceChildren(loading)
            this._render_pager()
            return
        }

        if (this._state.errored === true) {
            const error = document.createElement("p")
            error.classList.add("pyc-pipelines__status", "pyc-pipelines__status--error")
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load pipelines. Try refreshing."
            region.replaceChildren(error)
            this._render_pager()
            return
        }

        if (this._pipelines.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-pipelines__status")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No pipelines cached yet"
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
     * Build the pipelines ``<table>`` from the current
     * ``_pipelines`` list.
     */
    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-pipelines__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = ["Pipeline", "Name", "Digest", "Stages", "Cached"]
        for (const column of columns) {
            const th = document.createElement("th")
            th.scope = "col"
            th.textContent = column
            head_row.appendChild(th)
        }
        thead.appendChild(head_row)
        table.appendChild(thead)

        const tbody = document.createElement("tbody")
        for (const pipeline of this._pipelines) {
            const row = document.createElement("tr")
            row.classList.add("pyc-pipelines__row")

            const id_cell = document.createElement("td")
            const link = document.createElement("a")
            link.classList.add("pyc-pipelines__pipeline-link")
            link.setAttribute("href", "/pipelines/" + pipeline.pipeline_id)
            link.textContent = short_id(pipeline.pipeline_id)
            link.title = pipeline.pipeline_id
            id_cell.appendChild(link)
            row.appendChild(id_cell)

            const name_cell = document.createElement("td")
            name_cell.textContent = pipeline.name
            row.appendChild(name_cell)

            const digest_cell = document.createElement("td")
            const digest = document.createElement("span")
            digest.classList.add("pyc-pipelines__digest")
            digest.textContent = short_id(pipeline.pipeline_id)
            digest.title = pipeline.pipeline_id
            digest_cell.appendChild(digest)
            row.appendChild(digest_cell)

            const stages_cell = document.createElement("td")
            const stage_count = Array.isArray(pipeline.stages)
                ? pipeline.stages.length
                : 0
            stages_cell.textContent = String(stage_count)
            row.appendChild(stages_cell)

            const cached_cell = document.createElement("td")
            cached_cell.textContent = format_timestamp(pipeline.cached_at)
            row.appendChild(cached_cell)

            tbody.appendChild(row)
        }
        table.appendChild(tbody)
        return table
    }

    /**
     * Update the pager controls -- enabled state + page indicator
     * label -- from the current state.
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
     * Build the request payload shared by the validate + save
     * actions. ``document`` is sent as the raw string -- the server
     * selects the YAML/JSON parser from ``filename``.
     *
     * @param commit_sha The commit-sha field value.
     * @param filename The filename field value.
     * @param document_text The raw pipeline document text.
     *
     * @returns A ``PipelineDefinitionCreateRequest`` payload.
     */
    private _build_create_payload(
        commit_sha: string,
        filename: string,
        document_text: string,
    ): Record<string, unknown> {
        const rtnval: Record<string, unknown> = {
            commit_sha: commit_sha,
            filename: filename,
            document: document_text,
        }
        return rtnval
    }

    /**
     * Run the DAG-validate action against a supplied document.
     * Exposed so unit tests can invoke a validate without a real
     * click.
     *
     * @param commit_sha The commit-sha field value.
     * @param filename The filename field value.
     * @param document_text The raw pipeline document text.
     *
     * @returns The validate outcome.
     */
    public async validatePipeline(
        commit_sha: string,
        filename: string,
        document_text: string,
    ): Promise<ValidateOutcome> {
        const rtnval = await this._do_validate(commit_sha, filename, document_text)
        return rtnval
    }

    private async _submit_validate(
        commit_input: HTMLInputElement,
        filename_input: HTMLInputElement,
        document_area: HTMLTextAreaElement,
    ): Promise<void> {
        const document_text = document_area.value
        if (document_text.trim().length === 0) {
            this._render_form_status("error", "Pipeline document is required.", [])
            return
        }
        this._render_form_status("neutral", "Validating pipeline…", [])
        const outcome = await this._do_validate(
            commit_input.value.trim(),
            filename_input.value.trim(),
            document_text,
        )
        const tone = outcome.valid === true ? "ok" : "error"
        const detail: string[] = []
        if (outcome.valid === true && outcome.topologicalOrder.length > 0) {
            detail.push("Topological order: " + outcome.topologicalOrder.join(" → "))
        }
        for (const issue of outcome.issues) {
            detail.push(issue)
        }
        this._render_form_status(tone, outcome.message, detail)
        return
    }

    private async _do_validate(
        commit_sha: string,
        filename: string,
        document_text: string,
    ): Promise<ValidateOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: ValidateOutcome = {
                ok: false,
                status: 0,
                valid: false,
                stageCount: 0,
                topologicalOrder: [],
                issues: [],
                message: "Select a project before validating a pipeline.",
            }
            return rtnval
        }
        const payload = this._build_create_payload(commit_sha, filename, document_text)
        let status = 0
        let valid = false
        let stage_count = 0
        let topological_order: string[] = []
        let issues: string[] = []
        try {
            const url = build_pipelines_validate_url(this._state.projectId)
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
            const body = await response.json().catch(() => null)
            if (body !== null && typeof body === "object") {
                const record = body as Record<string, unknown>
                if (typeof record.valid === "boolean") {
                    valid = record.valid
                }
                if (typeof record.stage_count === "number") {
                    stage_count = record.stage_count
                }
                if (Array.isArray(record.topological_order) === true) {
                    topological_order = (record.topological_order as unknown[])
                        .filter((entry) => typeof entry === "string") as string[]
                }
                if (Array.isArray(record.issues) === true) {
                    issues = (record.issues as unknown[])
                        .filter((entry) => typeof entry === "string") as string[]
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.pipelines.validate_failed",
                { reason: String(reason) },
            )
            const rtnval: ValidateOutcome = {
                ok: false,
                status: 0,
                valid: false,
                stageCount: 0,
                topologicalOrder: [],
                issues: [],
                message: "Failed to reach the pipeline service.",
            }
            return rtnval
        }
        const rtnval: ValidateOutcome = {
            ok: status === 200,
            status: status,
            valid: valid,
            stageCount: stage_count,
            topologicalOrder: topological_order,
            issues: issues,
            message: validate_message_for_status(status, valid),
        }
        return rtnval
    }

    /**
     * Run the upsert (save) action against a supplied document.
     * Exposed so unit tests can invoke a save without a real
     * form-submit event.
     *
     * @param commit_sha The commit-sha field value.
     * @param filename The filename field value.
     * @param document_text The raw pipeline document text.
     *
     * @returns The upsert outcome.
     */
    public async savePipeline(
        commit_sha: string,
        filename: string,
        document_text: string,
    ): Promise<UpsertOutcome> {
        const rtnval = await this._do_save(commit_sha, filename, document_text)
        return rtnval
    }

    private async _submit_save(
        commit_input: HTMLInputElement,
        filename_input: HTMLInputElement,
        document_area: HTMLTextAreaElement,
    ): Promise<void> {
        const commit_sha = commit_input.value.trim()
        const filename = filename_input.value.trim()
        const document_text = document_area.value
        if (commit_sha.length === 0 || filename.length === 0) {
            this._render_form_status(
                "error",
                "Commit SHA and filename are required.",
                [],
            )
            return
        }
        if (document_text.trim().length === 0) {
            this._render_form_status("error", "Pipeline document is required.", [])
            return
        }
        this._render_form_status("neutral", "Saving pipeline…", [])
        const outcome = await this._do_save(commit_sha, filename, document_text)
        const tone = outcome.ok === true ? "ok" : "error"
        const detail: string[] = []
        if (outcome.ok === true && outcome.pipelineId.length > 0) {
            detail.push("Pipeline id: " + outcome.pipelineId)
        }
        this._render_form_status(tone, outcome.message, detail)
        if (outcome.ok === true) {
            await this._refresh()
        }
        return
    }

    private async _do_save(
        commit_sha: string,
        filename: string,
        document_text: string,
    ): Promise<UpsertOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: UpsertOutcome = {
                ok: false,
                status: 0,
                pipelineId: "",
                message: "Select a project before saving a pipeline.",
            }
            return rtnval
        }
        const payload = this._build_create_payload(commit_sha, filename, document_text)
        let status = 0
        let pipeline_id = ""
        try {
            const url = build_pipelines_collection_url(this._state.projectId)
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
                const body = await response.json().catch(() => null)
                if (body !== null && typeof body === "object") {
                    const record = body as Record<string, unknown>
                    if (typeof record.pipeline_id === "string") {
                        pipeline_id = record.pipeline_id
                    }
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.pipelines.save_failed",
                { reason: String(reason) },
            )
            const rtnval: UpsertOutcome = {
                ok: false,
                status: 0,
                pipelineId: "",
                message: "Failed to reach the pipeline service.",
            }
            return rtnval
        }
        const ok = status === 200 || status === 201
        let message = "Pipeline saved."
        if (ok === false) {
            if (status === 422) {
                message = "Pipeline document was rejected — check the DAG."
            } else if (status === 403) {
                message = "You do not have permission to save pipelines."
            } else {
                message = "Failed to save pipeline (HTTP " + String(status) + ")."
            }
        }
        const rtnval: UpsertOutcome = {
            ok: ok,
            status: status,
            pipelineId: pipeline_id,
            message: message,
        }
        return rtnval
    }

    /**
     * Render the upsert-form status block -- a tone-coded message
     * plus an optional detail list (topological order / issues).
     *
     * @param tone One of ``"ok"`` | ``"error"`` | ``"neutral"``.
     * @param message The headline status message.
     * @param detail Optional detail lines.
     */
    private _render_form_status(
        tone: string,
        message: string,
        detail: string[],
    ): void {
        if (this._form_status === null) {
            return
        }
        const status = this._form_status
        status.setAttribute("data-tone", tone)

        const headline = document.createElement("p")
        headline.classList.add("pyc-pipelines__status-headline")
        headline.setAttribute("data-role", "form-status-message")
        headline.textContent = message

        const children: HTMLElement[] = [headline]
        if (detail.length > 0) {
            const list = document.createElement("ul")
            list.classList.add("pyc-pipelines__status-detail")
            list.setAttribute("data-role", "form-status-detail")
            for (const line of detail) {
                const item = document.createElement("li")
                item.textContent = line
                list.appendChild(item)
            }
            children.push(list)
        }
        status.replaceChildren(...children)
        return
    }

    /**
     * Run the matrix-expand action against a supplied matrix spec.
     * Exposed so unit tests can invoke an expand without a real
     * click.
     *
     * @param matrix The parsed matrix-spec object.
     * @param strategy_name Optional sharding strategy name.
     *
     * @returns The matrix-expand outcome.
     */
    public async expandMatrix(
        matrix: Record<string, unknown>,
        strategy_name: string,
    ): Promise<MatrixExpandOutcome> {
        const rtnval = await this._do_matrix_expand(matrix, strategy_name)
        return rtnval
    }

    private async _submit_matrix_expand(
        matrix_area: HTMLTextAreaElement,
        strategy_input: HTMLInputElement,
    ): Promise<void> {
        let matrix: Record<string, unknown> = {}
        try {
            matrix = parse_matrix_spec(matrix_area.value)
        } catch (reason: unknown) {
            this._render_matrix_result(
                "error",
                "Matrix spec must be a valid JSON object.",
                null,
            )
            console.warn(
                "pychestrate.ui.pipelines.matrix_spec_invalid",
                { reason: String(reason) },
            )
            return
        }
        this._render_matrix_result("neutral", "Expanding matrix…", null)
        const outcome = await this._do_matrix_expand(
            matrix,
            strategy_input.value.trim(),
        )
        const tone = outcome.ok === true ? "ok" : "error"
        this._render_matrix_result(tone, outcome.message, outcome)
        return
    }

    private async _do_matrix_expand(
        matrix: Record<string, unknown>,
        strategy_name: string,
    ): Promise<MatrixExpandOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: MatrixExpandOutcome = {
                ok: false,
                status: 0,
                strategyName: "",
                shardCount: 0,
                shards: [],
                message: "Select a project before expanding a matrix.",
            }
            return rtnval
        }
        const payload: Record<string, unknown> = { matrix: matrix }
        if (strategy_name.length > 0) {
            payload.strategy_name = strategy_name
        }
        let status = 0
        let strategy = ""
        let shard_count = 0
        let shards: ExpansionShard[] = []
        try {
            const url = build_pipelines_expand_matrix_url(this._state.projectId)
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
                const body = await response.json().catch(() => null)
                if (body !== null && typeof body === "object") {
                    const record = body as Record<string, unknown>
                    if (typeof record.strategy_name === "string") {
                        strategy = record.strategy_name
                    }
                    if (typeof record.shard_count === "number") {
                        shard_count = record.shard_count
                    }
                    if (Array.isArray(record.shards) === true) {
                        shards = (record.shards as unknown[])
                            .filter((entry) => entry !== null && typeof entry === "object")
                            .map((entry) => entry as ExpansionShard)
                    }
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.pipelines.matrix_expand_failed",
                { reason: String(reason) },
            )
            const rtnval: MatrixExpandOutcome = {
                ok: false,
                status: 0,
                strategyName: "",
                shardCount: 0,
                shards: [],
                message: "Failed to reach the pipeline service.",
            }
            return rtnval
        }
        const ok = status === 200
        let message = "Matrix expanded into " + String(shard_count) + " shard(s)."
        if (ok === false) {
            if (status === 422) {
                message = "Matrix spec was rejected — check the dimensions."
            } else if (status === 403) {
                message = "You do not have permission to expand matrices."
            } else {
                message = "Failed to expand matrix (HTTP " + String(status) + ")."
            }
        }
        const rtnval: MatrixExpandOutcome = {
            ok: ok,
            status: status,
            strategyName: strategy,
            shardCount: shard_count,
            shards: shards,
            message: message,
        }
        return rtnval
    }

    /**
     * Render the matrix-expand result region -- a tone-coded
     * message plus, on success, the shard list.
     *
     * @param tone One of ``"ok"`` | ``"error"`` | ``"neutral"``.
     * @param message The headline message.
     * @param outcome The expand outcome (null while pending).
     */
    private _render_matrix_result(
        tone: string,
        message: string,
        outcome: MatrixExpandOutcome | null,
    ): void {
        if (this._matrix_region === null) {
            return
        }
        const region = this._matrix_region
        region.setAttribute("data-tone", tone)

        const headline = document.createElement("p")
        headline.classList.add("pyc-pipelines__status-headline")
        headline.setAttribute("data-role", "matrix-result-message")
        headline.textContent = message

        const children: HTMLElement[] = [headline]
        if (outcome !== null && outcome.ok === true && outcome.shards.length > 0) {
            const list = document.createElement("ul")
            list.classList.add("pyc-pipelines__shard-list")
            list.setAttribute("data-role", "matrix-shard-list")
            for (const shard of outcome.shards) {
                const item = document.createElement("li")
                item.classList.add("pyc-pipelines__shard")

                const id_chip = document.createElement("span")
                id_chip.classList.add("pyc-pipelines__shard-id")
                id_chip.textContent = shard.shard_id
                item.appendChild(id_chip)

                const group_chip = document.createElement("span")
                group_chip.classList.add("pyc-pipelines__shard-group")
                group_chip.textContent = shard.parallel_group +
                    " #" + String(shard.sequence_in_group)
                item.appendChild(group_chip)

                const dims = shard.dimension_values
                if (dims !== undefined && dims !== null) {
                    const dim_text = document.createElement("span")
                    dim_text.classList.add("pyc-pipelines__shard-dims")
                    const pairs: string[] = []
                    for (const key of Object.keys(dims)) {
                        pairs.push(key + "=" + String(dims[key]))
                    }
                    dim_text.textContent = pairs.join(", ")
                    item.appendChild(dim_text)
                }

                list.appendChild(item)
            }
            children.push(list)
        }
        region.replaceChildren(...children)
        return
    }
}
