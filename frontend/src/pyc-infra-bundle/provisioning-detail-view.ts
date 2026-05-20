/**
 * ``<pyc-provisioning-detail>`` -- the provisioning-run detail
 * view Custom Element.
 *
 * On mount (route ``/provisioning-runs/{run_id}``) the element
 * fetches ``GET /api/v1/projects/{project_id}/provisioning-runs/
 * {run_id}`` for the run snapshot and renders the run's identity,
 * state badge, action, driver, plan summary, and timestamps.
 *
 * Project resolution -- the detail route carries only the
 * ``run_id``. The provisioning REST surface exposes no project-
 * agnostic resolver path (unlike builds, which have
 * ``/api/v1/builds/{id}``), so the owning project id must be
 * supplied. The provisioning list view links to this view with a
 * ``?project_id=`` query param; the detail view reads it on mount.
 *
 * Live-update approach -- polling, not SSE. The provisioning REST
 * surface exposes no per-run event stream, so while the run is in
 * a non-terminal state the view re-fetches the GET endpoint every
 * 5 seconds. The poll timer is cleared the moment the run reaches
 * a terminal state and on ``disconnectedCallback`` so navigation
 * away never leaks a timer -- the same poll pattern PR p20c's
 * build-detail view uses.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

import {
    type ProvisioningRun,
    type ProvisioningPlanSummary,
    type ProvisioningResourceOp,
    is_terminal_provisioning_state,
    provisioning_state_tone,
} from "./provisioning-list-view.js"
import { format_timestamp, short_id } from "./environments-view.js"

/**
 * Connection / poll status of the live-update loop. Exposed so
 * unit tests can assert lifecycle transitions.
 */
export type PollStatus = "idle" | "polling" | "stopped"

/**
 * Diagnostic snapshot of the detail view's runtime state. Exposed
 * via the ``detailState`` accessor for unit tests.
 */
export interface ProvisioningDetailState {
    runId: string
    projectId: string
    loading: boolean
    errored: boolean
    pollStatus: PollStatus
    terminal: boolean
}

/**
 * Base path of the projects REST collection.
 */
const PROJECTS_API_PATH: string = "/api/v1/projects"

/**
 * Interval, in milliseconds, between live-poll re-fetches while a
 * provisioning run is in a non-terminal state.
 */
const POLL_INTERVAL_MS: number = 5000

/**
 * Matches a canonical UUID -- the shape a valid ``run_id`` takes.
 */
const UUID_PATTERN: RegExp =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Extract a ``run_id`` from a shell-served path of the form
 * ``/provisioning-runs/{run_id}``. Returns an empty string when
 * the path does not name a single run.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns The run id segment, or ``""`` when the path is not a
 *          provisioning-detail path.
 */
export function run_id_from_path(path: string): string {
    if (typeof path !== "string" || path.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const prefix = "/provisioning-runs/"
    if (path.startsWith(prefix) === false) {
        const rtnval = ""
        return rtnval
    }
    let tail = path.slice(prefix.length)
    const slash_index = tail.indexOf("/")
    if (slash_index >= 0) {
        tail = tail.slice(0, slash_index)
    }
    const query_index = tail.indexOf("?")
    if (query_index >= 0) {
        tail = tail.slice(0, query_index)
    }
    const rtnval = tail
    return rtnval
}

/**
 * Read the owning ``project_id`` from a shell-served URL's query
 * string. The provisioning list view links to the detail view
 * with a ``?project_id=`` query param.
 *
 * @param search A query string (typically ``window.location.search``).
 *
 * @returns The project id, or ``""`` when absent.
 */
export function project_id_from_search(search: string): string {
    if (typeof search !== "string" || search.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const params = new URLSearchParams(search)
    const value = params.get("project_id")
    if (value === null) {
        const rtnval = ""
        return rtnval
    }
    const rtnval = value
    return rtnval
}

/**
 * Decide whether a ``run_id`` string is a syntactically valid
 * UUID. The detail view refuses to make a network call for an id
 * that fails this check.
 *
 * @param run_id Candidate run identifier.
 *
 * @returns True when the id is a canonical UUID.
 */
export function is_valid_run_id(run_id: string): boolean {
    if (typeof run_id !== "string") {
        const rtnval = false
        return rtnval
    }
    const rtnval = UUID_PATTERN.test(run_id)
    return rtnval
}

/**
 * Build the project-scoped ``GET …/provisioning-runs/{run_id}``
 * URL.
 *
 * @param project_id Owning project identifier.
 * @param run_id Provisioning run identifier.
 *
 * @returns A relative URL string.
 */
export function build_provisioning_detail_url(
    project_id: string,
    run_id: string,
): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/provisioning-runs/" +
        encodeURIComponent(run_id)
    return rtnval
}

/**
 * The provisioning detail view Custom Element. Register it with
 * ``customElements.define("pyc-provisioning-detail",
 * PycProvisioningDetail)``.
 */
export class PycProvisioningDetail extends HTMLElement {
    private _run_id: string
    private _project_id: string
    private _run: ProvisioningRun | null
    private _loading: boolean
    private _errored: boolean
    private _terminal: boolean
    private _poll_status: PollStatus
    private _poll_timer: ReturnType<typeof setTimeout> | null
    private _root: HTMLElement | null

    public constructor() {
        super()
        this._run_id = ""
        this._project_id = ""
        this._run = null
        this._loading = false
        this._errored = false
        this._terminal = false
        this._poll_status = "idle"
        this._poll_timer = null
        this._root = null
    }

    /**
     * Observed attributes -- ``run-id`` and ``project-id`` may be
     * supplied explicitly by a host; otherwise they are read from
     * the URL on mount.
     */
    public static get observedAttributes(): string[] {
        const rtnval = ["run-id", "project-id"]
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the view's
     * runtime state without scraping the DOM.
     */
    public get detailState(): ProvisioningDetailState {
        const rtnval = {
            runId: this._run_id,
            projectId: this._project_id,
            loading: this._loading,
            errored: this._errored,
            pollStatus: this._poll_status,
            terminal: this._terminal,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- resolve the run + project ids, render the
     * chrome, and fetch the initial snapshot.
     */
    public connectedCallback(): void {
        const attr_run = this.getAttribute("run-id")
        if (attr_run !== null && attr_run.length > 0) {
            this._run_id = attr_run
        } else {
            this._run_id = run_id_from_path(window.location.pathname)
        }
        const attr_project = this.getAttribute("project-id")
        if (attr_project !== null && attr_project.length > 0) {
            this._project_id = attr_project
        } else {
            this._project_id = project_id_from_search(window.location.search)
        }
        this._render_chrome()
        void this._load()
        return
    }

    /**
     * Lifecycle hook -- stop the live-poll timer so a navigation
     * away from the run never leaks a timer.
     */
    public disconnectedCallback(): void {
        this._stop_poll()
        return
    }

    /**
     * Fetch the run snapshot then -- when the run is not already
     * terminal -- start the live-poll loop. Exposed so unit tests
     * can await a load cycle.
     */
    public async load(): Promise<void> {
        await this._load()
        return
    }

    private async _load(): Promise<void> {
        if (
            is_valid_run_id(this._run_id) === false ||
            this._project_id.length === 0
        ) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        this._loading = true
        this._errored = false
        this._render_body()

        const run = await this._fetch_run()
        if (run === null) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }

        this._run = run
        this._loading = false
        this._errored = false
        this._terminal = is_terminal_provisioning_state(run.state)
        this._render_body()

        if (this._terminal === false) {
            this._start_poll()
        } else {
            this._poll_status = "stopped"
            this._render_poll_banner()
        }
        return
    }

    /**
     * Fetch the current provisioning-run snapshot.
     *
     * @returns The ``ProvisioningRun`` snapshot, or ``null`` on
     *          failure.
     */
    private async _fetch_run(): Promise<ProvisioningRun | null> {
        const url = build_provisioning_detail_url(
            this._project_id,
            this._run_id,
        )
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "provisioning run fetch failed: HTTP " +
                        String(response.status),
                )
            }
            const body = await response.json()
            const rtnval = body as ProvisioningRun
            return rtnval
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.infra.detail_fetch_failed",
                { reason: String(reason) },
            )
            const rtnval = null
            return rtnval
        }
    }

    /**
     * Start the live-poll loop. A no-op when a poll is already
     * scheduled.
     */
    private _start_poll(): void {
        if (this._poll_timer !== null) {
            return
        }
        this._poll_status = "polling"
        this._render_poll_banner()
        this._schedule_poll()
        return
    }

    private _schedule_poll(): void {
        const timer = setTimeout(() => {
            this._poll_timer = null
            void this._poll_once()
        }, POLL_INTERVAL_MS)
        // Under Node's test runner ``setTimeout`` returns a
        // ``Timeout`` handle whose ``unref`` keeps a pending poll
        // from blocking process exit. Browsers return a numeric
        // handle with no ``unref`` -- guard for both.
        const handle = timer as unknown as { unref?: () => void }
        if (typeof handle.unref === "function") {
            handle.unref()
        }
        this._poll_timer = timer
        return
    }

    /**
     * Run one poll cycle -- re-fetch the run snapshot, re-render,
     * and either reschedule (still non-terminal) or stop (now
     * terminal). Exposed so unit tests can drive a poll cycle
     * without waiting on a real timer.
     */
    public async pollOnce(): Promise<void> {
        await this._poll_once()
        return
    }

    private async _poll_once(): Promise<void> {
        const run = await this._fetch_run()
        if (run !== null) {
            this._run = run
            this._terminal = is_terminal_provisioning_state(run.state)
            this._render_body()
        }
        if (this._terminal === true) {
            this._stop_poll()
            this._poll_status = "stopped"
            this._render_poll_banner()
            return
        }
        this._schedule_poll()
        return
    }

    /**
     * Stop the live-poll loop, clearing any pending timer.
     */
    private _stop_poll(): void {
        if (this._poll_timer !== null) {
            clearTimeout(this._poll_timer)
            this._poll_timer = null
        }
        return
    }

    /**
     * Build the persistent chrome -- heading, back link, the poll
     * banner, and the body region the data render replaces.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-provisioning-detail")
        root.setAttribute("role", "main")
        root.setAttribute("aria-label", "Provisioning run detail")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-provisioning-detail__heading")
        heading.textContent = "Provisioning run detail"
        root.appendChild(heading)

        const back = document.createElement("a")
        back.classList.add("pyc-provisioning-detail__back-link")
        back.setAttribute("href", "/provisioning-runs")
        back.setAttribute("data-role", "back-link")
        back.textContent = "Back to provisioning runs"
        root.appendChild(back)

        const banner = document.createElement("p")
        banner.classList.add("pyc-provisioning-detail__banner")
        banner.setAttribute("data-role", "poll-banner")
        banner.setAttribute("role", "status")
        banner.hidden = true
        root.appendChild(banner)

        const body = document.createElement("div")
        body.classList.add("pyc-provisioning-detail__body")
        body.setAttribute("data-role", "body")
        root.appendChild(body)

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Re-render the body region from the current run snapshot,
     * driving the loading / error / loaded states.
     */
    private _render_body(): void {
        if (this._root === null) {
            return
        }
        const body = this._root.querySelector('[data-role="body"]')
        if (body === null) {
            return
        }

        if (this._loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-provisioning-detail__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading provisioning run…"
            body.replaceChildren(loading)
            return
        }

        if (this._errored === true || this._run === null) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-provisioning-detail__status",
                "pyc-provisioning-detail__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent =
                "Failed to load this provisioning run. Try refreshing."
            body.replaceChildren(error)
            return
        }

        const fragment = document.createDocumentFragment()
        fragment.appendChild(this._run_summary(this._run))

        const plan_summary = this._run.plan_summary
        if (plan_summary !== undefined && plan_summary !== null) {
            fragment.appendChild(this._plan_summary(plan_summary))
        }

        body.replaceChildren(fragment)
        return
    }

    /**
     * Build the run summary block -- identity, state badge,
     * action, driver, environment, timestamps, and the final-state
     * reason.
     *
     * @param run The current run snapshot.
     *
     * @returns A populated summary section element.
     */
    private _run_summary(run: ProvisioningRun): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-provisioning-detail__summary")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Run summary")

        const id_row = document.createElement("div")
        id_row.classList.add("pyc-provisioning-detail__id-row")

        const id_value = document.createElement("span")
        id_value.classList.add("pyc-provisioning-detail__run-id")
        id_value.setAttribute("data-role", "run-id")
        id_value.textContent = short_id(run.run_id)
        id_value.title = run.run_id
        id_row.appendChild(id_value)

        const badge = document.createElement("span")
        badge.classList.add("pyc-provisioning-detail__badge")
        badge.setAttribute("data-role", "state-badge")
        badge.setAttribute("data-tone", provisioning_state_tone(run.state))
        badge.textContent = run.state
        id_row.appendChild(badge)
        section.appendChild(id_row)

        const grid = document.createElement("dl")
        grid.classList.add("pyc-provisioning-detail__grid")

        this._append_field(grid, "Project", run.project_id)
        this._append_field(grid, "Environment", run.environment_id)
        this._append_field(grid, "Action", run.action)
        this._append_field(grid, "Driver", run.driver_name)
        this._append_field(grid, "Started", format_timestamp(run.started_at))
        this._append_field(grid, "Finished", format_timestamp(run.finished_at))
        this._append_field(
            grid,
            "Plan issued",
            format_timestamp(run.plan_issued_at),
        )

        const layer5 = run.layer5_run_id
        if (layer5 !== undefined && layer5 !== null && layer5.length > 0) {
            this._append_field(grid, "Layer-5 run", layer5)
        }

        const reason = run.final_state_reason
        if (reason !== undefined && reason !== null && reason.length > 0) {
            this._append_field(grid, "Final state reason", reason)
        }

        section.appendChild(grid)
        return section
    }

    /**
     * Append one labelled field to a definition-list grid.
     *
     * @param grid The ``<dl>`` to append into.
     * @param label The field's display label.
     * @param value The field's display value.
     */
    private _append_field(
        grid: HTMLElement,
        label: string,
        value: string,
    ): void {
        const field = document.createElement("div")
        field.classList.add("pyc-provisioning-detail__field")
        const term = document.createElement("dt")
        term.textContent = label
        const def = document.createElement("dd")
        def.textContent = value
        field.appendChild(term)
        field.appendChild(def)
        grid.appendChild(field)
        return
    }

    /**
     * Build the plan-summary section -- the aggregate add /
     * change / destroy counts plus the per-resource operation
     * list.
     *
     * @param summary The run's recorded plan summary.
     *
     * @returns A populated plan-summary section element.
     */
    private _plan_summary(summary: ProvisioningPlanSummary): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-provisioning-detail__plan")
        section.setAttribute("data-role", "plan-summary")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Plan summary")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-provisioning-detail__section-heading")
        heading.textContent = "Plan summary"
        section.appendChild(heading)

        const counts = document.createElement("div")
        counts.classList.add("pyc-provisioning-detail__plan-counts")
        counts.appendChild(
            this._plan_count("Add", summary.resources_to_add, "ok"),
        )
        counts.appendChild(
            this._plan_count("Change", summary.resources_to_change, "warn"),
        )
        counts.appendChild(
            this._plan_count(
                "Destroy",
                summary.resources_to_destroy,
                "error",
            ),
        )
        section.appendChild(counts)

        const ops = summary.resource_ops
        if (ops !== undefined && ops !== null && ops.length > 0) {
            section.appendChild(this._resource_ops(ops))
        }
        return section
    }

    /**
     * Build one plan-count chip.
     *
     * @param label The count's display label.
     * @param value The count value.
     * @param tone The badge tone token.
     *
     * @returns A populated count-chip element.
     */
    private _plan_count(
        label: string,
        value: number,
        tone: string,
    ): HTMLElement {
        const chip = document.createElement("div")
        chip.classList.add("pyc-provisioning-detail__plan-count")
        chip.setAttribute("data-tone", tone)

        const number = document.createElement("span")
        number.classList.add("pyc-provisioning-detail__plan-number")
        number.textContent = String(value)
        chip.appendChild(number)

        const text = document.createElement("span")
        text.classList.add("pyc-provisioning-detail__plan-label")
        text.textContent = label
        chip.appendChild(text)

        return chip
    }

    /**
     * Build the per-resource operations list.
     *
     * @param ops The plan summary's resource operations.
     *
     * @returns A populated operations list element.
     */
    private _resource_ops(ops: ProvisioningResourceOp[]): HTMLElement {
        const list = document.createElement("ul")
        list.classList.add("pyc-provisioning-detail__op-list")
        for (const op of ops) {
            const item = document.createElement("li")
            item.classList.add("pyc-provisioning-detail__op")

            const op_chip = document.createElement("span")
            op_chip.classList.add("pyc-provisioning-detail__op-kind")
            op_chip.setAttribute("data-op", op.op)
            op_chip.textContent = op.op
            item.appendChild(op_chip)

            const address = document.createElement("span")
            address.classList.add("pyc-provisioning-detail__op-address")
            address.textContent = op.resource_address
            item.appendChild(address)

            list.appendChild(item)
        }
        return list
    }

    /**
     * Update the live-poll status banner. Shows a "live updates
     * on" affordance while polling and a "run finished" note once
     * the run reaches a terminal state.
     */
    private _render_poll_banner(): void {
        if (this._root === null) {
            return
        }
        const banner = this._root.querySelector('[data-role="poll-banner"]')
        if (banner instanceof HTMLElement === false) {
            return
        }
        const el = banner as HTMLElement
        if (this._poll_status === "polling") {
            el.hidden = false
            el.setAttribute("data-tone", "neutral")
            el.textContent =
                "Provisioning run in progress — refreshing every 5 seconds."
            return
        }
        if (this._poll_status === "stopped" && this._terminal === true) {
            el.hidden = false
            el.setAttribute("data-tone", "neutral")
            el.textContent =
                "Provisioning run finished — live updates ended."
            return
        }
        el.hidden = true
        el.textContent = ""
        return
    }
}
