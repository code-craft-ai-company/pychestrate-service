/**
 * ``<pyc-run-detail>`` -- the run detail view Custom Element.
 *
 * On mount (route ``/runs/{run_id}``) the element fetches
 * ``GET /api/v1/runs/{run_id}`` for the initial run snapshot and
 * renders the run's identity, state badge, dispatch attempt,
 * timestamps, and terminal outcome.
 *
 * It then opens an ``EventSource`` against
 * ``GET /api/v1/runs/{run_id}/events`` and applies each ``RunEvent``
 * live:
 *
 * - ``state_changed`` -> updates the state badge + terminal outcome.
 * - ``progress``      -> updates the progress section (counts +
 *                        a progress bar).
 * - ``result_manifest`` -> renders the artifacts rollup with a
 *                        link to ``testsummary.html``.
 * - ``heartbeat``     -> no-op (keepalive).
 *
 * The ``EventSource`` is closed on ``disconnectedCallback`` so
 * navigation away never leaks a live connection. When a run is
 * already in a terminal state the element does not open the
 * stream at all.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state lives in instance fields.
 */

import {
    type Run,
    format_timestamp,
    short_run_id,
    state_badge_tone,
} from "./runs-list-view.js"

/**
 * ``RunState`` values the server treats as terminal -- once a run
 * reaches one of these the SSE stream closes and no further
 * events arrive.
 */
export const TERMINAL_RUN_STATES: readonly string[] = [
    "dispatch_failed",
    "cancelled",
    "completed",
    "failed",
]

/**
 * The ``ProgressSummary`` schema from
 * ``specs/openapi/pychestrate.yaml``. Only the fields the detail
 * view renders are typed here.
 */
export interface ProgressSummary {
    tests_total?: number | null
    tests_passed: number
    tests_failed: number
    tests_skipped: number
    tests_errored: number
    percent_complete?: number | null
    notes?: string | null
    recorded_at: string
}

/**
 * One artifact reference surfaced by a ``result_manifest`` event.
 */
export interface ManifestArtifact {
    label: string
    path: string
}

/**
 * The ``ResultManifest`` schema from
 * ``specs/openapi/pychestrate.yaml``. Only the fields the detail
 * view renders are typed here.
 */
export interface ResultManifest {
    backend_key_prefix: string
    completed_at: string
    terminal_outcome: string
    summary_artifact_path?: string | null
    results_artifact_path?: string | null
    results_stream_artifact_path?: string | null
    html_summary_artifact_path?: string | null
    tests_passed?: number | null
    tests_failed?: number | null
    tests_skipped?: number | null
    tests_errored?: number | null
}

/**
 * The ``RunEvent`` schema from ``specs/openapi/pychestrate.yaml``.
 * One event delivered on the ``/runs/{run_id}/events`` SSE stream.
 */
export interface RunEvent {
    run_id: string
    event_type: string
    sequence: number
    occurred_at: string
    state?: string | null
    terminal_outcome?: string | null
    progress?: ProgressSummary | null
    manifest?: ResultManifest | null
}

/**
 * Connection status of the live SSE stream. Exposed so unit tests
 * can assert lifecycle transitions without scraping the DOM.
 */
export type StreamStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed"

/**
 * Diagnostic snapshot of the detail view's runtime state. Exposed
 * via the ``detailState`` accessor for unit tests.
 */
export interface RunDetailState {
    runId: string
    loading: boolean
    errored: boolean
    streamStatus: StreamStatus
    terminal: boolean
}

/**
 * Base path of the runs REST collection.
 */
const RUNS_API_PATH: string = "/api/v1/runs"

/**
 * Matches a canonical UUID -- the shape a valid ``run_id`` takes.
 * The view validates the route id before any network call.
 */
const UUID_PATTERN: RegExp =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Extract a ``run_id`` from a shell-served path of the form
 * ``/runs/{run_id}``. Returns an empty string when the path does
 * not name a single run.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns The run id segment, or ``""`` when the path is not a
 *          run-detail path.
 */
export function run_id_from_path(path: string): string {
    if (typeof path !== "string" || path.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const prefix = "/runs/"
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
 * Decide whether a ``run_id`` string is a syntactically valid
 * UUID. The detail view refuses to make a network call for an
 * id that fails this check.
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
 * Decide whether a run state is terminal -- the SSE stream closes
 * once a run reaches a terminal state.
 *
 * @param run_state One of the ``RunState`` enum values.
 *
 * @returns True when the state is terminal.
 */
export function is_terminal_state(run_state: string): boolean {
    const rtnval = TERMINAL_RUN_STATES.indexOf(run_state) >= 0
    return rtnval
}

/**
 * Compute a percent-complete value for the progress bar. Prefers
 * the server-supplied ``percent_complete`` and falls back to a
 * ratio derived from the pass/fail/skip/error counts and total.
 *
 * @param progress A ``ProgressSummary`` roll-up.
 *
 * @returns A clamped 0-100 percentage.
 */
export function progress_percent(progress: ProgressSummary): number {
    if (
        progress.percent_complete !== null &&
        progress.percent_complete !== undefined &&
        Number.isFinite(progress.percent_complete) === true
    ) {
        const clamped = Math.max(0, Math.min(100, progress.percent_complete))
        return clamped
    }
    const total = progress.tests_total
    if (total === null || total === undefined || total <= 0) {
        const rtnval = 0
        return rtnval
    }
    const done =
        progress.tests_passed +
        progress.tests_failed +
        progress.tests_skipped +
        progress.tests_errored
    const ratio = (done / total) * 100
    const rtnval = Math.max(0, Math.min(100, ratio))
    return rtnval
}

/**
 * Build the list of artifact references from a ``ResultManifest``.
 * Each present path becomes a labelled entry; ``testsummary.html``
 * is always first when present so the UI can link it prominently.
 *
 * @param manifest A ``ResultManifest`` payload.
 *
 * @returns An ordered list of artifact references.
 */
export function manifest_artifacts(manifest: ResultManifest): ManifestArtifact[] {
    const rtnval: ManifestArtifact[] = []
    const html_path = manifest.html_summary_artifact_path
    if (html_path !== null && html_path !== undefined && html_path.length > 0) {
        rtnval.push({ label: "Test summary (HTML)", path: html_path })
    }
    const summary_path = manifest.summary_artifact_path
    if (summary_path !== null && summary_path !== undefined && summary_path.length > 0) {
        rtnval.push({ label: "Run summary (JSON)", path: summary_path })
    }
    const results_path = manifest.results_artifact_path
    if (results_path !== null && results_path !== undefined && results_path.length > 0) {
        rtnval.push({ label: "Consolidated results (JSON)", path: results_path })
    }
    const stream_path = manifest.results_stream_artifact_path
    if (stream_path !== null && stream_path !== undefined && stream_path.length > 0) {
        rtnval.push({ label: "Results stream (JSOS)", path: stream_path })
    }
    return rtnval
}

/**
 * Build the download URL for an artifact under a run's result
 * tree. Points at the per-path artifact REST resource.
 *
 * @param run_id The run the artifact belongs to.
 * @param artifact_path Slash-delimited path relative to the result root.
 *
 * @returns A relative URL string for the artifact resource.
 */
export function artifact_url(run_id: string, artifact_path: string): string {
    const encoded_run = encodeURIComponent(run_id)
    const segments = artifact_path.split("/")
    const encoded_segments: string[] = []
    for (const segment of segments) {
        encoded_segments.push(encodeURIComponent(segment))
    }
    const encoded_path = encoded_segments.join("/")
    const rtnval =
        RUNS_API_PATH + "/" + encoded_run + "/artifacts/" + encoded_path
    return rtnval
}

/**
 * The run detail view Custom Element. Register it with
 * ``customElements.define("pyc-run-detail", PycRunDetail)``.
 */
export class PycRunDetail extends HTMLElement {
    private _run_id: string
    private _run: Run | null
    private _loading: boolean
    private _errored: boolean
    private _terminal: boolean
    private _stream_status: StreamStatus
    private _source: EventSource | null
    private _root: HTMLElement | null

    public constructor() {
        super()
        this._run_id = ""
        this._run = null
        this._loading = false
        this._errored = false
        this._terminal = false
        this._stream_status = "idle"
        this._source = null
        this._root = null
    }

    /**
     * Observed attributes -- ``run-id`` may be supplied explicitly
     * by a host; otherwise it is read from the path on mount.
     */
    public static get observedAttributes(): string[] {
        const rtnval = ["run-id"]
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the view's
     * runtime state without scraping the DOM.
     */
    public get detailState(): RunDetailState {
        const rtnval = {
            runId: this._run_id,
            loading: this._loading,
            errored: this._errored,
            streamStatus: this._stream_status,
            terminal: this._terminal,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- resolve the run id, render the chrome,
     * fetch the initial snapshot, and open the live stream.
     */
    public connectedCallback(): void {
        const attr_id = this.getAttribute("run-id")
        if (attr_id !== null && attr_id.length > 0) {
            this._run_id = attr_id
        } else {
            this._run_id = run_id_from_path(window.location.pathname)
        }
        this._render_chrome()
        void this._load()
        return
    }

    /**
     * Lifecycle hook -- close the live SSE connection so a
     * navigation away from the run never leaks a connection.
     */
    public disconnectedCallback(): void {
        this._close_stream()
        return
    }

    /**
     * Fetch the initial run snapshot then -- when the run is not
     * already terminal -- open the live event stream. Exposed so
     * unit tests can await a load cycle.
     */
    public async load(): Promise<void> {
        await this._load()
        return
    }

    private async _load(): Promise<void> {
        if (is_valid_run_id(this._run_id) === false) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        this._loading = true
        this._errored = false
        this._render_body()

        let run: Run | null = null
        try {
            const url = RUNS_API_PATH + "/" + encodeURIComponent(this._run_id)
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error("run fetch failed: HTTP " + String(response.status))
            }
            const body = await response.json()
            run = body as Run
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.runs.detail_fetch_failed",
                { reason: String(reason) },
            )
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }

        this._run = run
        this._loading = false
        this._errored = false
        this._terminal = is_terminal_state(run.state)
        this._render_body()

        if (this._terminal === false) {
            this._open_stream()
        }
        return
    }

    /**
     * Open the ``EventSource`` against the run's SSE event stream
     * and wire its handlers. A no-op when a stream is already
     * open or ``EventSource`` is unavailable.
     */
    private _open_stream(): void {
        if (this._source !== null) {
            return
        }
        if (typeof EventSource === "undefined") {
            return
        }
        const url = RUNS_API_PATH + "/" + encodeURIComponent(this._run_id) + "/events"
        this._stream_status = "connecting"
        this._render_stream_banner()

        const source = new EventSource(url, { withCredentials: true })
        this._source = source

        source.onopen = (): void => {
            this._stream_status = "open"
            this._render_stream_banner()
        }
        source.onmessage = (event: MessageEvent): void => {
            this._handle_stream_message(event)
        }
        source.onerror = (): void => {
            // The browser auto-reconnects an EventSource unless it
            // is closed. A terminal run's stream closes cleanly on
            // the server side; treat that as expected.
            if (this._terminal === true) {
                this._close_stream()
                this._stream_status = "closed"
            } else {
                this._stream_status = "reconnecting"
            }
            this._render_stream_banner()
        }
        return
    }

    /**
     * Close the live ``EventSource`` if one is open.
     */
    private _close_stream(): void {
        if (this._source !== null) {
            this._source.close()
            this._source = null
        }
        return
    }

    /**
     * Parse one SSE message frame and apply it. Exposed so unit
     * tests can feed events without a real ``EventSource``.
     *
     * @param event The ``MessageEvent`` delivered by the stream.
     */
    public handleStreamMessage(event: MessageEvent): void {
        this._handle_stream_message(event)
        return
    }

    private _handle_stream_message(event: MessageEvent): void {
        let parsed: RunEvent | null = null
        try {
            parsed = JSON.parse(String(event.data)) as RunEvent
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.runs.detail_event_parse_failed",
                { reason: String(reason) },
            )
            return
        }
        if (parsed === null || typeof parsed.event_type !== "string") {
            return
        }
        this._apply_event(parsed)
        return
    }

    private _apply_event(run_event: RunEvent): void {
        if (run_event.event_type === "heartbeat") {
            return
        }
        if (run_event.event_type === "state_changed") {
            if (this._run !== null && typeof run_event.state === "string") {
                this._run.state = run_event.state
                if (
                    run_event.terminal_outcome !== undefined &&
                    run_event.terminal_outcome !== null
                ) {
                    this._run.terminal_outcome = run_event.terminal_outcome
                }
                this._terminal = is_terminal_state(run_event.state)
            }
            this._render_body()
            if (this._terminal === true) {
                this._close_stream()
                this._stream_status = "closed"
                this._render_stream_banner()
            }
            return
        }
        if (run_event.event_type === "progress") {
            if (run_event.progress !== undefined && run_event.progress !== null) {
                this._render_progress(run_event.progress)
            }
            return
        }
        if (run_event.event_type === "result_manifest") {
            if (run_event.manifest !== undefined && run_event.manifest !== null) {
                this._render_artifacts(run_event.manifest)
            }
            return
        }
        return
    }

    /**
     * Build the persistent chrome -- heading + the body region
     * the data render replaces.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-run-detail")
        root.setAttribute("role", "main")
        root.setAttribute("aria-label", "Run detail")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-run-detail__heading")
        heading.textContent = "Run detail"
        root.appendChild(heading)

        const back = document.createElement("a")
        back.classList.add("pyc-run-detail__back-link")
        back.setAttribute("href", "/runs")
        back.setAttribute("data-role", "back-link")
        back.textContent = "Back to runs"
        root.appendChild(back)

        const banner = document.createElement("p")
        banner.classList.add("pyc-run-detail__banner")
        banner.setAttribute("data-role", "stream-banner")
        banner.setAttribute("role", "status")
        banner.hidden = true
        root.appendChild(banner)

        const body = document.createElement("div")
        body.classList.add("pyc-run-detail__body")
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
            loading.classList.add("pyc-run-detail__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading run…"
            body.replaceChildren(loading)
            return
        }

        if (this._errored === true || this._run === null) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-run-detail__status",
                "pyc-run-detail__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load this run. Try refreshing."
            body.replaceChildren(error)
            return
        }

        const fragment = document.createDocumentFragment()
        fragment.appendChild(this._build_summary(this._run))

        const progress_section = document.createElement("section")
        progress_section.classList.add("pyc-run-detail__progress")
        progress_section.setAttribute("data-role", "progress-section")
        progress_section.setAttribute("role", "region")
        progress_section.setAttribute("aria-label", "Progress")
        fragment.appendChild(progress_section)

        const artifacts_section = document.createElement("section")
        artifacts_section.classList.add("pyc-run-detail__artifacts")
        artifacts_section.setAttribute("data-role", "artifacts-section")
        artifacts_section.setAttribute("role", "region")
        artifacts_section.setAttribute("aria-label", "Artifacts")
        fragment.appendChild(artifacts_section)

        body.replaceChildren(fragment)

        const summary = (this._run as Run & {
            progress_summary?: ProgressSummary | null
        }).progress_summary
        if (summary !== undefined && summary !== null) {
            this._render_progress(summary)
        }
        return
    }

    /**
     * Build the run summary block -- identity, state badge,
     * dispatch attempt, timestamps, and terminal outcome.
     *
     * @param run The current run snapshot.
     *
     * @returns A populated summary section element.
     */
    private _build_summary(run: Run): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-run-detail__summary")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Run summary")

        const id_row = document.createElement("div")
        id_row.classList.add("pyc-run-detail__id-row")

        const id_value = document.createElement("span")
        id_value.classList.add("pyc-run-detail__run-id")
        id_value.setAttribute("data-role", "run-id")
        id_value.textContent = short_run_id(run.run_id)
        id_value.title = run.run_id
        id_row.appendChild(id_value)

        const badge = document.createElement("span")
        badge.classList.add("pyc-run-detail__badge")
        badge.setAttribute("data-role", "state-badge")
        badge.setAttribute("data-tone", state_badge_tone(run.state))
        badge.textContent = run.state
        id_row.appendChild(badge)
        section.appendChild(id_row)

        const grid = document.createElement("dl")
        grid.classList.add("pyc-run-detail__grid")

        this._append_field(grid, "Project", run.project_id)
        this._append_field(grid, "Pod", run.pod_id)
        this._append_field(grid, "Job type", run.job_type)
        const job_name = run.job_name
        if (job_name !== undefined && job_name !== null && job_name.length > 0) {
            this._append_field(grid, "Job name", job_name)
        }

        const attempt_field = document.createElement("div")
        attempt_field.classList.add("pyc-run-detail__field")
        const attempt_term = document.createElement("dt")
        attempt_term.textContent = "Dispatch attempt"
        const attempt_def = document.createElement("dd")
        attempt_def.setAttribute("data-role", "dispatch-attempt")
        const attempt = (run as Run & {
            current_dispatch_attempt_id?: string | null
        }).current_dispatch_attempt_id
        if (attempt !== undefined && attempt !== null && attempt.length > 0) {
            attempt_def.textContent = attempt
        } else {
            attempt_def.textContent = "—"
        }
        attempt_field.appendChild(attempt_term)
        attempt_field.appendChild(attempt_def)
        grid.appendChild(attempt_field)

        this._append_field(grid, "Created", format_timestamp(run.created_at))
        this._append_field(grid, "Dispatched", format_timestamp(run.dispatched_at))
        this._append_field(grid, "Started", format_timestamp(run.started_at))
        this._append_field(grid, "Completed", format_timestamp(run.completed_at))

        const outcome_field = document.createElement("div")
        outcome_field.classList.add("pyc-run-detail__field")
        const outcome_term = document.createElement("dt")
        outcome_term.textContent = "Terminal outcome"
        const outcome_def = document.createElement("dd")
        outcome_def.setAttribute("data-role", "terminal-outcome")
        const outcome = run.terminal_outcome
        if (outcome !== undefined && outcome !== null && outcome.length > 0) {
            outcome_def.textContent = outcome
        } else {
            outcome_def.textContent = "—"
        }
        outcome_field.appendChild(outcome_term)
        outcome_field.appendChild(outcome_def)
        grid.appendChild(outcome_field)

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
    private _append_field(grid: HTMLElement, label: string, value: string): void {
        const field = document.createElement("div")
        field.classList.add("pyc-run-detail__field")
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
     * Render the progress section from a ``ProgressSummary``
     * roll-up -- pass/fail/total counts plus a progress bar.
     *
     * @param progress A ``ProgressSummary`` payload.
     */
    private _render_progress(progress: ProgressSummary): void {
        if (this._root === null) {
            return
        }
        const section = this._root.querySelector('[data-role="progress-section"]')
        if (section === null) {
            return
        }

        const heading = document.createElement("h2")
        heading.classList.add("pyc-run-detail__section-heading")
        heading.textContent = "Progress"

        const total = progress.tests_total
        const counts = document.createElement("div")
        counts.classList.add("pyc-run-detail__counts")
        this._append_count(counts, "Passed", progress.tests_passed, "ok")
        this._append_count(counts, "Failed", progress.tests_failed, "error")
        this._append_count(counts, "Errored", progress.tests_errored, "error")
        this._append_count(counts, "Skipped", progress.tests_skipped, "warn")
        if (total !== undefined && total !== null) {
            this._append_count(counts, "Total", total, "neutral")
        }

        const percent = progress_percent(progress)
        const bar = document.createElement("div")
        bar.classList.add("pyc-run-detail__bar")
        bar.setAttribute("data-role", "progress-bar")
        bar.setAttribute("role", "progressbar")
        bar.setAttribute("aria-valuemin", "0")
        bar.setAttribute("aria-valuemax", "100")
        bar.setAttribute("aria-valuenow", String(Math.round(percent)))
        const fill = document.createElement("div")
        fill.classList.add("pyc-run-detail__bar-fill")
        fill.style.width = String(percent) + "%"
        bar.appendChild(fill)

        section.replaceChildren(heading, counts, bar)

        const notes = progress.notes
        if (notes !== undefined && notes !== null && notes.length > 0) {
            const notes_el = document.createElement("p")
            notes_el.classList.add("pyc-run-detail__progress-notes")
            notes_el.setAttribute("data-role", "progress-notes")
            notes_el.textContent = notes
            section.appendChild(notes_el)
        }
        return
    }

    /**
     * Append one labelled count chip to the progress counts row.
     *
     * @param container The counts container element.
     * @param label The count's display label.
     * @param value The numeric count.
     * @param tone Coarse tone driving the chip color.
     */
    private _append_count(
        container: HTMLElement,
        label: string,
        value: number,
        tone: string,
    ): void {
        const chip = document.createElement("span")
        chip.classList.add("pyc-run-detail__count")
        chip.setAttribute("data-tone", tone)
        const count = document.createElement("strong")
        count.textContent = String(value)
        const caption = document.createElement("span")
        caption.textContent = label
        chip.appendChild(count)
        chip.appendChild(caption)
        container.appendChild(chip)
        return
    }

    /**
     * Render the artifacts section from a ``ResultManifest`` --
     * the pass/fail rollup plus a list of artifact links with the
     * HTML test summary surfaced first.
     *
     * @param manifest A ``ResultManifest`` payload.
     */
    private _render_artifacts(manifest: ResultManifest): void {
        if (this._root === null) {
            return
        }
        const section = this._root.querySelector('[data-role="artifacts-section"]')
        if (section === null) {
            return
        }

        const heading = document.createElement("h2")
        heading.classList.add("pyc-run-detail__section-heading")
        heading.textContent = "Artifacts"

        const rollup = document.createElement("p")
        rollup.classList.add("pyc-run-detail__rollup")
        rollup.setAttribute("data-role", "artifacts-rollup")
        const passed = manifest.tests_passed
        const failed = manifest.tests_failed
        const passed_text = passed === undefined || passed === null ? 0 : passed
        const failed_text = failed === undefined || failed === null ? 0 : failed
        rollup.textContent =
            "Outcome " + manifest.terminal_outcome +
            " · " + String(passed_text) + " passed" +
            " · " + String(failed_text) + " failed"

        const list = document.createElement("ul")
        list.classList.add("pyc-run-detail__artifact-list")
        list.setAttribute("data-role", "artifact-list")

        const artifacts = manifest_artifacts(manifest)
        if (artifacts.length === 0) {
            const empty = document.createElement("li")
            empty.classList.add("pyc-run-detail__artifact-empty")
            empty.textContent = "No artifacts recorded for this run."
            list.appendChild(empty)
        } else {
            for (const artifact of artifacts) {
                const item = document.createElement("li")
                item.classList.add("pyc-run-detail__artifact")
                const link = document.createElement("a")
                link.classList.add("pyc-run-detail__artifact-link")
                link.setAttribute(
                    "href",
                    artifact_url(this._run_id, artifact.path),
                )
                link.setAttribute("rel", "noopener noreferrer")
                link.textContent = artifact.label
                if (artifact.path.endsWith("testsummary.html") === true) {
                    link.setAttribute("data-role", "summary-link")
                }
                item.appendChild(link)
                const path_hint = document.createElement("span")
                path_hint.classList.add("pyc-run-detail__artifact-path")
                path_hint.textContent = artifact.path
                item.appendChild(path_hint)
                list.appendChild(item)
            }
        }

        section.replaceChildren(heading, rollup, list)
        return
    }

    /**
     * Update the consolidated stream-status banner. Shows a
     * reconnecting affordance while the stream is down and a
     * "live updates ended" note once a terminal run's stream
     * closes.
     */
    private _render_stream_banner(): void {
        if (this._root === null) {
            return
        }
        const banner = this._root.querySelector('[data-role="stream-banner"]')
        if (banner === null || banner instanceof HTMLElement === false) {
            return
        }
        const el = banner as HTMLElement
        if (this._stream_status === "reconnecting") {
            el.hidden = false
            el.setAttribute("data-tone", "warn")
            el.textContent = "Live updates interrupted — reconnecting…"
            return
        }
        if (this._stream_status === "closed" && this._terminal === true) {
            el.hidden = false
            el.setAttribute("data-tone", "neutral")
            el.textContent = "Run finished — live updates ended."
            return
        }
        el.hidden = true
        el.textContent = ""
        return
    }
}
