/**
 * ``<pyc-alert-rules>`` -- the per-project metric-alert-rule editor
 * view Custom Element.
 *
 * On mount the element renders a project selector, then on a
 * project selection fetches that project's alert rules via
 * ``GET /api/v1/projects/{project_id}/metric-alerts`` and renders a
 * table. Each row surfaces the rule's metric, comparison +
 * threshold, evaluation window, severity, notification targets and
 * enabled flag.
 *
 * The view also surfaces a "Create Alert Rule" action: an inline
 * form that picks a metric (from ``GET /api/v1/metrics/catalog``),
 * a comparison operator + threshold, an evaluation window, a
 * severity, an enabled flag and a comma-separated notification
 * target list, then POSTs a ``MetricAlertRule`` create request to
 * ``…/metric-alerts``.
 *
 * The metric-alerts REST surface (PR p20f / p21g) exposes only
 * ``GET`` (list) and ``POST`` (create) -- there is no ``PATCH`` to
 * toggle a rule and no ``DELETE``. The view therefore lets the
 * operator set the enabled flag at creation time and renders the
 * current enabled state read-only per row; a per-row toggle / a
 * delete action are intentionally absent until the server exposes
 * the corresponding mutations.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state lives in instance fields.
 *
 * Project listing degrades to a manual project-id text input when
 * the ``GET /api/v1/projects`` collection is unavailable, mirroring
 * the dashboards / SLOs views.
 */

import {
    build_catalog_url,
    extract_catalog,
    MetricCatalogEntry,
} from "./timeseries-view.js"
import {
    extract_projects,
    MetricsProjectOption,
} from "./test-metrics-view.js"

/**
 * Base path of the projects REST collection.
 */
const PROJECTS_API_PATH: string = "/api/v1/projects"

/**
 * Route prefix the alert-rules editor view owns.
 */
export const ALERT_RULES_ROUTE: string = "/metric-alerts"

/**
 * The fixed kind value for a metric-threshold alert rule. The
 * server validates ``kind`` against its registered alert-rule
 * kinds; ``threshold`` is the kind the editor builds.
 */
export const ALERT_RULE_KIND: string = "threshold"

/**
 * The comparison operators the threshold editor offers. Each entry
 * carries the wire value the rule ``config`` records and a short
 * human label.
 */
export interface ComparisonOption {
    value: string
    label: string
}

/**
 * The comparison operators a threshold alert rule supports.
 */
export const COMPARISON_OPTIONS: readonly ComparisonOption[] = [
    { value: "gt", label: "greater than" },
    { value: "gte", label: "greater than or equal" },
    { value: "lt", label: "less than" },
    { value: "lte", label: "less than or equal" },
    { value: "eq", label: "equal to" },
]

/**
 * The severity levels the metric-alerts REST surface accepts.
 */
export const SEVERITY_OPTIONS: readonly string[] = [
    "info",
    "warning",
    "critical",
]

/**
 * One metric-alert rule, as returned in the ``items`` array of the
 * alert-rules list page. Only the fields the view renders are
 * typed.
 */
export interface AlertRule {
    rule_id: string
    project_id: string
    name: string
    description?: string | null
    kind: string
    config: Record<string, unknown>
    severity: string
    enabled: boolean
    notification_targets: string[]
    created_by?: string | null
    created_at?: string | null
    updated_at?: string | null
}

/**
 * Pagination metadata returned alongside the ``items`` array.
 */
export interface AlertRulePageMeta {
    page: number
    per_page: number
    total: number
}

/**
 * The alert-rules list page response shape.
 */
export interface AlertRulePage {
    items: AlertRule[]
    meta: AlertRulePageMeta
}

/**
 * The threshold fields a create request packs into the rule
 * ``config`` object.
 */
export interface ThresholdConfig {
    metric: string
    comparison: string
    threshold: number
    window_seconds: number
}

/**
 * The current project + list state of the alert-rules view.
 * Exposed so unit tests can assert state transitions.
 */
export interface AlertRulesListState {
    projectId: string
    loading: boolean
    errored: boolean
    total: number
}

/**
 * Outcome of a create-alert-rule POST, surfaced to callers /
 * tests.
 */
export interface AlertRuleCreateOutcome {
    ok: boolean
    status: number
    ruleId: string
    message: string
}

/**
 * Build the ``…/projects/{project_id}/metric-alerts`` collection
 * URL.
 *
 * @param project_id Owning project identifier.
 *
 * @returns A relative URL string.
 */
export function build_alert_rules_collection_url(project_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + ALERT_RULES_ROUTE
    return rtnval
}

/**
 * Translate a create-alert-rule HTTP status into operator
 * guidance.
 *
 * @param status HTTP status code of the create response.
 *
 * @returns A human-readable message.
 */
export function alert_create_message_for_status(status: number): string {
    if (status === 201 || status === 200) {
        const rtnval = "Alert rule created."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "An alert rule with that name already exists."
        return rtnval
    }
    if (status === 422) {
        const rtnval =
            "The alert-rule definition was rejected — check the fields."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown project."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to create alert rules."
        return rtnval
    }
    const rtnval =
        "Failed to create alert rule (HTTP " + String(status) + ")."
    return rtnval
}

/**
 * Resolve the short human label for a comparison operator value.
 *
 * @param value A comparison operator wire value.
 *
 * @returns The human label, or the raw value when unrecognised.
 */
export function comparison_label(value: string): string {
    for (const option of COMPARISON_OPTIONS) {
        if (option.value === value) {
            const rtnval = option.label
            return rtnval
        }
    }
    const rtnval = value
    return rtnval
}

/**
 * Format an alert rule's threshold condition as a scannable
 * single-line summary -- e.g. ``"http_2xx greater than 0.95"``.
 *
 * @param rule An alert rule.
 *
 * @returns A human-readable condition string.
 */
export function describe_alert_condition(rule: AlertRule): string {
    const config = rule.config
    if (config === null || config === undefined || typeof config !== "object") {
        const rtnval = "—"
        return rtnval
    }
    const record = config as Record<string, unknown>
    const metric = typeof record.metric === "string" ? record.metric : ""
    const comparison =
        typeof record.comparison === "string" ? record.comparison : ""
    const threshold = record.threshold
    if (metric.length === 0 || comparison.length === 0) {
        const rtnval = "—"
        return rtnval
    }
    if (typeof threshold !== "number") {
        const rtnval = metric + " " + comparison_label(comparison)
        return rtnval
    }
    const rtnval = metric + " " + comparison_label(comparison) + " " +
        String(threshold)
    return rtnval
}

/**
 * Format a window-seconds count as a human-scannable duration.
 *
 * @param seconds Window length in seconds.
 *
 * @returns A short label such as ``"7d"`` or ``"5m"``.
 */
export function format_alert_window(seconds: number): string {
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
 * Split a comma-separated notification-target string into trimmed,
 * non-empty entries.
 *
 * @param raw Raw text-input content.
 *
 * @returns A list of notification targets (possibly empty).
 */
export function parse_notification_targets(raw: string): string[] {
    if (typeof raw !== "string" || raw.trim().length === 0) {
        const rtnval: string[] = []
        return rtnval
    }
    const pieces = raw.split(",")
    const rtnval: string[] = []
    for (const piece of pieces) {
        const trimmed = piece.trim()
        if (trimmed.length > 0) {
            rtnval.push(trimmed)
        }
    }
    return rtnval
}

/**
 * Normalise an alert-rules-page response body into ``AlertRule``
 * records. Accepts both a bare array and an ``{items}`` envelope.
 *
 * @param body Parsed JSON response body.
 *
 * @returns A list of alert rules (possibly empty).
 */
export function extract_alert_rules(body: unknown): AlertRule[] {
    let raw: unknown[] = []
    if (Array.isArray(body) === true) {
        raw = body as unknown[]
    } else if (body !== null && typeof body === "object") {
        const items = (body as { items?: unknown }).items
        if (Array.isArray(items) === true) {
            raw = items as unknown[]
        }
    }
    const rtnval: AlertRule[] = []
    for (const item of raw) {
        if (item === null || typeof item !== "object") {
            continue
        }
        const record = item as Record<string, unknown>
        const rule_id = record.rule_id
        if (typeof rule_id !== "string" || rule_id.length === 0) {
            continue
        }
        let config: Record<string, unknown> = {}
        if (
            record.config !== null &&
            typeof record.config === "object" &&
            Array.isArray(record.config) === false
        ) {
            config = record.config as Record<string, unknown>
        }
        let targets: string[] = []
        if (Array.isArray(record.notification_targets) === true) {
            targets = (record.notification_targets as unknown[]).filter(
                (value) => typeof value === "string",
            ) as string[]
        }
        const rule: AlertRule = {
            rule_id: rule_id,
            project_id:
                typeof record.project_id === "string"
                    ? record.project_id
                    : "",
            name: typeof record.name === "string" ? record.name : "",
            kind: typeof record.kind === "string" ? record.kind : "",
            config: config,
            severity:
                typeof record.severity === "string"
                    ? record.severity
                    : "warning",
            enabled: record.enabled === true,
            notification_targets: targets,
        }
        if (typeof record.description === "string") {
            rule.description = record.description
        }
        rtnval.push(rule)
    }
    return rtnval
}

/**
 * The alert-rules editor view Custom Element. Register it with
 * ``customElements.define("pyc-alert-rules", PycAlertRules)``.
 */
export class PycAlertRules extends HTMLElement {
    private _state: AlertRulesListState
    private _rules: AlertRule[]
    private _catalog: MetricCatalogEntry[]
    private _projects: MetricsProjectOption[]
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
        this._rules = []
        this._catalog = []
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
    public get listState(): AlertRulesListState {
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
     * project + catalog fetches when the element is inserted.
     */
    public connectedCallback(): void {
        this._render_chrome()
        void this._load_catalog()
        void this._load_projects()
        return
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-metrics")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-metrics__heading")
        heading.textContent = "Metric Alert Rules"
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
        create_button.textContent = "Create Alert Rule"
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
     * Fetch the metric catalog so the create form can offer a
     * metric picker. Exposed so unit tests can await the fetch.
     */
    public async loadCatalog(): Promise<void> {
        await this._load_catalog()
        return
    }

    private async _load_catalog(): Promise<void> {
        let catalog: MetricCatalogEntry[] = []
        try {
            const response = await fetch(build_catalog_url(), {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                catalog = extract_catalog(body)
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.alert_catalog_fetch_failed",
                { reason: String(reason) },
            )
        }
        this._catalog = catalog
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
                "pychestrate.ui.metrics.alert_projects_fetch_failed",
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
     * Re-fetch the alert-rules page for the active project and
     * re-render. Exposed so unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.projectId.length === 0) {
            this._rules = []
            this._render_table_region()
            return
        }
        this._state.loading = true
        this._state.errored = false
        this._render_table_region()

        const url = build_alert_rules_collection_url(this._state.projectId)
        let rules: AlertRule[] = []
        let errored = false
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                rules = extract_alert_rules(body)
            } else {
                errored = true
            }
        } catch (reason: unknown) {
            errored = true
            console.warn(
                "pychestrate.ui.metrics.alert_rules_fetch_failed",
                { reason: String(reason) },
            )
        }

        this._state.loading = false
        this._state.errored = errored
        this._rules = rules
        this._state.total = rules.length
        this._render_table_region()
        return
    }

    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._state.projectId.length === 0) {
            const notice = document.createElement("p")
            notice.classList.add("pyc-metrics__notice")
            notice.setAttribute("data-role", "no-project-state")
            notice.textContent = "Select a project to view its alert rules."
            region.replaceChildren(notice)
            return
        }
        if (this._state.loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-metrics__notice")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading alert rules…"
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
            error.textContent = "Failed to load alert rules. Try refreshing."
            region.replaceChildren(error)
            return
        }
        if (this._rules.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-metrics__notice")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent =
                "No alert rules defined for this project yet — create one above."
            region.replaceChildren(empty)
            return
        }

        const table = this._build_table()
        region.replaceChildren(table)
        return
    }

    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-metrics__table")
        table.setAttribute("data-role", "alert-rules-table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Rule",
            "Condition",
            "Window",
            "Severity",
            "Targets",
            "Enabled",
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
        for (const rule of this._rules) {
            tbody.appendChild(this._build_row(rule))
        }
        table.appendChild(tbody)
        return table
    }

    private _build_row(rule: AlertRule): HTMLTableRowElement {
        const row = document.createElement("tr")
        row.classList.add("pyc-metrics__row")
        row.setAttribute("data-rule-id", rule.rule_id)

        const name_cell = document.createElement("td")
        const name = document.createElement("span")
        name.textContent = rule.name
        name.title = rule.rule_id
        name_cell.appendChild(name)
        row.appendChild(name_cell)

        const condition_cell = document.createElement("td")
        condition_cell.textContent = describe_alert_condition(rule)
        row.appendChild(condition_cell)

        const window_cell = document.createElement("td")
        const window_value = rule.config.window_seconds
        window_cell.textContent =
            typeof window_value === "number"
                ? format_alert_window(window_value)
                : "—"
        row.appendChild(window_cell)

        const severity_cell = document.createElement("td")
        const severity_badge = document.createElement("span")
        severity_badge.classList.add("pyc-metrics__badge")
        severity_badge.setAttribute("data-role", "severity-badge")
        severity_badge.setAttribute("data-tone", this._severity_tone(rule.severity))
        severity_badge.textContent = rule.severity
        severity_cell.appendChild(severity_badge)
        row.appendChild(severity_cell)

        const targets_cell = document.createElement("td")
        targets_cell.textContent =
            rule.notification_targets.length > 0
                ? rule.notification_targets.join(", ")
                : "—"
        row.appendChild(targets_cell)

        const enabled_cell = document.createElement("td")
        const enabled_badge = document.createElement("span")
        enabled_badge.classList.add("pyc-metrics__badge")
        enabled_badge.setAttribute("data-role", "enabled-badge")
        enabled_badge.setAttribute(
            "data-tone",
            rule.enabled === true ? "ok" : "neutral",
        )
        enabled_badge.textContent = rule.enabled === true ? "Enabled" : "Disabled"
        enabled_cell.appendChild(enabled_badge)
        row.appendChild(enabled_cell)

        return row
    }

    private _severity_tone(severity: string): string {
        if (severity === "critical") {
            const rtnval = "error"
            return rtnval
        }
        if (severity === "warning") {
            const rtnval = "warn"
            return rtnval
        }
        const rtnval = "neutral"
        return rtnval
    }

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

    private _render_create_form(): void {
        if (this._create_region === null) {
            return
        }
        const form = document.createElement("form")
        form.classList.add("pyc-metrics__form")
        form.setAttribute("data-role", "create-form")

        const name_input = this._build_text_field(
            form, "Name", "create-name", "checkout error rate",
        )

        const metric_label = document.createElement("label")
        metric_label.classList.add("pyc-metrics__field")
        metric_label.textContent = "Metric"
        const metric_select = document.createElement("select")
        metric_select.classList.add("pyc-metrics__select")
        metric_select.setAttribute("data-role", "create-metric")
        if (this._catalog.length === 0) {
            const option = document.createElement("option")
            option.value = ""
            option.textContent = "No metrics in catalog"
            metric_select.appendChild(option)
        } else {
            for (const entry of this._catalog) {
                const option = document.createElement("option")
                option.value = entry.name
                option.textContent = entry.name
                metric_select.appendChild(option)
            }
        }
        metric_label.appendChild(metric_select)
        form.appendChild(metric_label)

        const comparison_label_el = document.createElement("label")
        comparison_label_el.classList.add("pyc-metrics__field")
        comparison_label_el.textContent = "Comparison"
        const comparison_select = document.createElement("select")
        comparison_select.classList.add("pyc-metrics__select")
        comparison_select.setAttribute("data-role", "create-comparison")
        for (const option of COMPARISON_OPTIONS) {
            const opt = document.createElement("option")
            opt.value = option.value
            opt.textContent = option.label
            comparison_select.appendChild(opt)
        }
        comparison_label_el.appendChild(comparison_select)
        form.appendChild(comparison_label_el)

        const threshold_input = this._build_text_field(
            form, "Threshold", "create-threshold", "0.95",
        )
        const window_input = this._build_text_field(
            form, "Window (seconds)", "create-window", "300",
        )

        const severity_label = document.createElement("label")
        severity_label.classList.add("pyc-metrics__field")
        severity_label.textContent = "Severity"
        const severity_select = document.createElement("select")
        severity_select.classList.add("pyc-metrics__select")
        severity_select.setAttribute("data-role", "create-severity")
        for (const severity of SEVERITY_OPTIONS) {
            const opt = document.createElement("option")
            opt.value = severity
            opt.textContent = severity
            severity_select.appendChild(opt)
        }
        severity_select.value = "warning"
        severity_label.appendChild(severity_select)
        form.appendChild(severity_label)

        const targets_input = this._build_text_field(
            form,
            "Notification targets (comma-separated)",
            "create-targets",
            "ops-pager, slack:#alerts",
        )

        const enabled_label = document.createElement("label")
        enabled_label.classList.add("pyc-metrics__field")
        enabled_label.classList.add("pyc-metrics__field--inline")
        const enabled_checkbox = document.createElement("input")
        enabled_checkbox.setAttribute("type", "checkbox")
        enabled_checkbox.setAttribute("data-role", "create-enabled")
        enabled_checkbox.checked = true
        enabled_label.appendChild(enabled_checkbox)
        const enabled_text = document.createElement("span")
        enabled_text.textContent = "Enabled"
        enabled_label.appendChild(enabled_text)
        form.appendChild(enabled_label)

        const submit_button = document.createElement("button")
        submit_button.classList.add("pyc-metrics__button")
        submit_button.setAttribute("type", "submit")
        submit_button.setAttribute("data-role", "create-submit")
        submit_button.textContent = "Create Alert Rule"
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
                metric_select,
                comparison_select,
                threshold_input,
                window_input,
                severity_select,
                targets_input,
                enabled_checkbox,
                submit_button,
            )
        })

        this._create_region.replaceChildren(form)
        return
    }

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
        metric_select: HTMLSelectElement,
        comparison_select: HTMLSelectElement,
        threshold_input: HTMLInputElement,
        window_input: HTMLInputElement,
        severity_select: HTMLSelectElement,
        targets_input: HTMLInputElement,
        enabled_checkbox: HTMLInputElement,
        submit_button: HTMLButtonElement,
    ): Promise<void> {
        const status = form.querySelector('[data-role="create-status"]')
        const name = name_input.value.trim()
        const metric = metric_select.value.trim()
        if (name.length === 0) {
            if (status instanceof HTMLElement) {
                status.textContent = "An alert-rule name is required."
            }
            return
        }
        if (metric.length === 0) {
            if (status instanceof HTMLElement) {
                status.textContent = "A metric must be selected."
            }
            return
        }
        const threshold = Number(threshold_input.value.trim())
        if (Number.isNaN(threshold) === true) {
            if (status instanceof HTMLElement) {
                status.textContent = "Threshold must be a number."
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
        const config: ThresholdConfig = {
            metric: metric,
            comparison: comparison_select.value,
            threshold: threshold,
            window_seconds: window_seconds,
        }
        const targets = parse_notification_targets(targets_input.value)

        submit_button.disabled = true
        if (status instanceof HTMLElement) {
            status.textContent = "Creating alert rule…"
        }
        const outcome = await this._do_create(
            name,
            config,
            severity_select.value,
            enabled_checkbox.checked,
            targets,
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
            this._toggle_create_form()
            await this._refresh()
        }
        return
    }

    /**
     * POST a ``MetricAlertRule`` create request. Exposed so unit
     * tests can invoke a create without a real form-submit event.
     *
     * @param name Human-facing alert-rule name.
     * @param config Threshold config (metric, comparison,
     *               threshold, window_seconds).
     * @param severity Severity level (``info`` / ``warning`` /
     *                  ``critical``).
     * @param enabled Whether the rule is enabled at creation.
     * @param notification_targets Notification target list.
     *
     * @returns The create outcome.
     */
    public async createAlertRule(
        name: string,
        config: ThresholdConfig,
        severity: string,
        enabled: boolean,
        notification_targets: string[],
    ): Promise<AlertRuleCreateOutcome> {
        const rtnval = await this._do_create(
            name,
            config,
            severity,
            enabled,
            notification_targets,
        )
        return rtnval
    }

    private async _do_create(
        name: string,
        config: ThresholdConfig,
        severity: string,
        enabled: boolean,
        notification_targets: string[],
    ): Promise<AlertRuleCreateOutcome> {
        if (this._state.projectId.length === 0) {
            const rtnval: AlertRuleCreateOutcome = {
                ok: false,
                status: 0,
                ruleId: "",
                message: "Select a project before creating an alert rule.",
            }
            return rtnval
        }
        const payload: Record<string, unknown> = {
            name: name,
            kind: ALERT_RULE_KIND,
            config: {
                metric: config.metric,
                comparison: config.comparison,
                threshold: config.threshold,
                window_seconds: config.window_seconds,
            },
            severity: severity,
            enabled: enabled,
            notification_targets: notification_targets,
        }
        let status = 0
        let rule_id = ""
        try {
            const url = build_alert_rules_collection_url(
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
                const record = body as { rule_id?: unknown }
                if (typeof record.rule_id === "string") {
                    rule_id = record.rule_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.alert_rule_create_failed",
                { reason: String(reason) },
            )
            const rtnval: AlertRuleCreateOutcome = {
                ok: false,
                status: 0,
                ruleId: "",
                message: "Failed to reach the alert-rules service.",
            }
            return rtnval
        }
        const ok = status === 201 || status === 200
        const rtnval: AlertRuleCreateOutcome = {
            ok: ok,
            status: status,
            ruleId: rule_id,
            message: alert_create_message_for_status(status),
        }
        return rtnval
    }

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
