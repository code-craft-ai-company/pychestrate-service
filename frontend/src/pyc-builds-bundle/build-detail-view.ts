/**
 * ``<pyc-build-detail>`` -- the build-run detail view Custom
 * Element.
 *
 * On mount (route ``/builds/{build_id}``) the element fetches
 * ``GET /api/v1/projects/{project_id}/builds/{build_id}`` for the
 * build snapshot and ``…/builds/{build_id}/artifacts`` for the
 * artifact manifest, then renders the build's identity, state
 * badge, runner kind, reproducibility digest, timestamps, and the
 * artifacts list.
 *
 * Live-update approach -- polling, not SSE. The build-orchestration
 * REST surface in ``specs/openapi/pychestrate.yaml`` exposes no
 * per-build event stream (unlike runs, which have
 * ``/runs/{run_id}/events``). So while the build is in a non-
 * terminal state (``pending`` / ``running``) the view re-fetches
 * the GET endpoint every 5 seconds. The poll timer is cleared the
 * moment the build reaches a terminal state and on
 * ``disconnectedCallback`` so navigation away never leaks a timer.
 *
 * Because the route carries only ``build_id`` (no project id) the
 * view must learn the build's ``project_id`` before it can address
 * the project-scoped REST endpoints. It does so by reading it back
 * off the ``BuildRun`` payload returned by the first fetch -- which
 * means the first fetch is issued against a project-agnostic
 * resolver path, ``/api/v1/builds/{build_id}`` (the server resolves
 * the owning project). Subsequent project-scoped artifact + poll
 * fetches use the resolved ``project_id``.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

import {
    type BuildRun,
    type BuildToolchainSnapshot,
    build_state_tone,
    format_timestamp,
    is_terminal_build_state,
    short_id,
} from "./builds-list-view.js"

/**
 * One build artifact, as returned in the ``items`` array of
 * ``BuildArtifactPage``.
 */
export interface BuildArtifact {
    manifest_id: string
    artifact_id: string
    artifact_type: string
    artifact_name?: string | null
    storage_uri?: string | null
    sha256: string
    payload?: Record<string, unknown> | null
}

/**
 * The ``BuildArtifactPage`` response shape.
 */
export interface BuildArtifactPage {
    items: BuildArtifact[]
    manifest_id?: string | null
}

/**
 * Connection / poll status of the live-update loop. Exposed so
 * unit tests can assert lifecycle transitions.
 */
export type PollStatus = "idle" | "polling" | "stopped"

/**
 * Diagnostic snapshot of the detail view's runtime state. Exposed
 * via the ``detailState`` accessor for unit tests.
 */
export interface BuildDetailState {
    buildId: string
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
 * Project-agnostic build resolver path. The server resolves the
 * owning project from the build id.
 */
const BUILDS_RESOLVER_PATH: string = "/api/v1/builds"

/**
 * Interval, in milliseconds, between live-poll re-fetches while a
 * build is in a non-terminal state.
 */
const POLL_INTERVAL_MS: number = 5000

/**
 * Matches a canonical UUID -- the shape a valid ``build_id`` takes.
 */
const UUID_PATTERN: RegExp =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Extract a ``build_id`` from a shell-served path of the form
 * ``/builds/{build_id}``. Returns an empty string when the path
 * does not name a single build.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns The build id segment, or ``""`` when the path is not a
 *          build-detail path.
 */
export function build_id_from_path(path: string): string {
    if (typeof path !== "string" || path.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const prefix = "/builds/"
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
 * Decide whether a ``build_id`` string is a syntactically valid
 * UUID. The detail view refuses to make a network call for an id
 * that fails this check.
 *
 * @param build_id Candidate build identifier.
 *
 * @returns True when the id is a canonical UUID.
 */
export function is_valid_build_id(build_id: string): boolean {
    if (typeof build_id !== "string") {
        const rtnval = false
        return rtnval
    }
    const rtnval = UUID_PATTERN.test(build_id)
    return rtnval
}

/**
 * Build the project-scoped ``GET …/builds/{build_id}`` URL.
 *
 * @param project_id Owning project identifier.
 * @param build_id Build run identifier.
 *
 * @returns A relative URL string.
 */
export function build_detail_url(project_id: string, build_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/builds/" +
        encodeURIComponent(build_id)
    return rtnval
}

/**
 * Build the project-scoped ``GET …/builds/{build_id}/artifacts``
 * URL.
 *
 * @param project_id Owning project identifier.
 * @param build_id Build run identifier.
 *
 * @returns A relative URL string.
 */
export function build_artifacts_url(project_id: string, build_id: string): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/builds/" +
        encodeURIComponent(build_id) + "/artifacts"
    return rtnval
}

/**
 * The build detail view Custom Element. Register it with
 * ``customElements.define("pyc-build-detail", PycBuildDetail)``.
 */
export class PycBuildDetail extends HTMLElement {
    private _build_id: string
    private _project_id: string
    private _build: BuildRun | null
    private _artifacts: BuildArtifact[]
    private _loading: boolean
    private _errored: boolean
    private _terminal: boolean
    private _poll_status: PollStatus
    private _poll_timer: ReturnType<typeof setTimeout> | null
    private _root: HTMLElement | null

    public constructor() {
        super()
        this._build_id = ""
        this._project_id = ""
        this._build = null
        this._artifacts = []
        this._loading = false
        this._errored = false
        this._terminal = false
        this._poll_status = "idle"
        this._poll_timer = null
        this._root = null
    }

    /**
     * Observed attributes -- ``build-id`` may be supplied
     * explicitly by a host; otherwise it is read from the path on
     * mount.
     */
    public static get observedAttributes(): string[] {
        const rtnval = ["build-id"]
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the view's
     * runtime state without scraping the DOM.
     */
    public get detailState(): BuildDetailState {
        const rtnval = {
            buildId: this._build_id,
            projectId: this._project_id,
            loading: this._loading,
            errored: this._errored,
            pollStatus: this._poll_status,
            terminal: this._terminal,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- resolve the build id, render the chrome,
     * and fetch the initial snapshot.
     */
    public connectedCallback(): void {
        const attr_id = this.getAttribute("build-id")
        if (attr_id !== null && attr_id.length > 0) {
            this._build_id = attr_id
        } else {
            this._build_id = build_id_from_path(window.location.pathname)
        }
        this._render_chrome()
        void this._load()
        return
    }

    /**
     * Lifecycle hook -- stop the live-poll timer so a navigation
     * away from the build never leaks a timer.
     */
    public disconnectedCallback(): void {
        this._stop_poll()
        return
    }

    /**
     * Fetch the build snapshot + artifacts then -- when the build
     * is not already terminal -- start the live-poll loop. Exposed
     * so unit tests can await a load cycle.
     */
    public async load(): Promise<void> {
        await this._load()
        return
    }

    private async _load(): Promise<void> {
        if (is_valid_build_id(this._build_id) === false) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        this._loading = true
        this._errored = false
        this._render_body()

        const build = await this._fetch_build()
        if (build === null) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }

        this._build = build
        this._project_id = build.project_id
        this._loading = false
        this._errored = false
        this._terminal = is_terminal_build_state(build.state)
        this._render_body()

        await this._load_artifacts()

        if (this._terminal === false) {
            this._start_poll()
        } else {
            this._poll_status = "stopped"
            this._render_poll_banner()
        }
        return
    }

    /**
     * Fetch the current build snapshot. The first fetch addresses
     * the project-agnostic resolver path; once ``project_id`` is
     * known, project-scoped poll fetches address the scoped path.
     *
     * @returns The ``BuildRun`` snapshot, or ``null`` on failure.
     */
    private async _fetch_build(): Promise<BuildRun | null> {
        let url = BUILDS_RESOLVER_PATH + "/" + encodeURIComponent(this._build_id)
        if (this._project_id.length > 0) {
            url = build_detail_url(this._project_id, this._build_id)
        }
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error("build fetch failed: HTTP " + String(response.status))
            }
            const body = await response.json()
            const rtnval = body as BuildRun
            return rtnval
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.builds.detail_fetch_failed",
                { reason: String(reason) },
            )
            const rtnval = null
            return rtnval
        }
    }

    /**
     * Fetch the build's artifact manifest. A failed fetch leaves
     * the artifacts list empty -- the section renders an empty
     * state rather than an error.
     */
    private async _load_artifacts(): Promise<void> {
        if (this._project_id.length === 0) {
            return
        }
        try {
            const url = build_artifacts_url(this._project_id, this._build_id)
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                const page = body as BuildArtifactPage
                if (page !== null && Array.isArray(page.items) === true) {
                    this._artifacts = page.items
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.builds.artifacts_fetch_failed",
                { reason: String(reason) },
            )
        }
        this._render_artifacts()
        return
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
     * Run one poll cycle -- re-fetch the build snapshot, re-render,
     * and either reschedule (still non-terminal) or stop (now
     * terminal). Exposed so unit tests can drive a poll cycle
     * without waiting on a real timer.
     */
    public async pollOnce(): Promise<void> {
        await this._poll_once()
        return
    }

    private async _poll_once(): Promise<void> {
        const build = await this._fetch_build()
        if (build !== null) {
            this._build = build
            this._project_id = build.project_id
            this._terminal = is_terminal_build_state(build.state)
            this._render_body()
            await this._load_artifacts()
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
        root.classList.add("pyc-build-detail")
        root.setAttribute("role", "main")
        root.setAttribute("aria-label", "Build detail")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-build-detail__heading")
        heading.textContent = "Build detail"
        root.appendChild(heading)

        const back = document.createElement("a")
        back.classList.add("pyc-build-detail__back-link")
        back.setAttribute("href", "/builds")
        back.setAttribute("data-role", "back-link")
        back.textContent = "Back to builds"
        root.appendChild(back)

        const banner = document.createElement("p")
        banner.classList.add("pyc-build-detail__banner")
        banner.setAttribute("data-role", "poll-banner")
        banner.setAttribute("role", "status")
        banner.hidden = true
        root.appendChild(banner)

        const body = document.createElement("div")
        body.classList.add("pyc-build-detail__body")
        body.setAttribute("data-role", "body")
        root.appendChild(body)

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Re-render the body region from the current build snapshot,
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
            loading.classList.add("pyc-build-detail__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading build…"
            body.replaceChildren(loading)
            return
        }

        if (this._errored === true || this._build === null) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-build-detail__status",
                "pyc-build-detail__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load this build. Try refreshing."
            body.replaceChildren(error)
            return
        }

        const fragment = document.createDocumentFragment()
        fragment.appendChild(this._build_summary(this._build))

        if (this._build.toolchain !== undefined && this._build.toolchain !== null) {
            if (this._build.toolchain.length > 0) {
                fragment.appendChild(this._build_toolchain(this._build.toolchain))
            }
        }

        const artifacts_section = document.createElement("section")
        artifacts_section.classList.add("pyc-build-detail__artifacts")
        artifacts_section.setAttribute("data-role", "artifacts-section")
        artifacts_section.setAttribute("role", "region")
        artifacts_section.setAttribute("aria-label", "Artifacts")
        fragment.appendChild(artifacts_section)

        body.replaceChildren(fragment)
        this._render_artifacts()
        return
    }

    /**
     * Build the build summary block -- identity, state badge,
     * runner kind, reproducibility digest, timestamps, and the
     * final-state reason.
     *
     * @param build The current build snapshot.
     *
     * @returns A populated summary section element.
     */
    private _build_summary(build: BuildRun): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-build-detail__summary")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Build summary")

        const id_row = document.createElement("div")
        id_row.classList.add("pyc-build-detail__id-row")

        const id_value = document.createElement("span")
        id_value.classList.add("pyc-build-detail__build-id")
        id_value.setAttribute("data-role", "build-id")
        id_value.textContent = short_id(build.run_id)
        id_value.title = build.run_id
        id_row.appendChild(id_value)

        const badge = document.createElement("span")
        badge.classList.add("pyc-build-detail__badge")
        badge.setAttribute("data-role", "state-badge")
        badge.setAttribute("data-tone", build_state_tone(build.state))
        badge.textContent = build.state
        id_row.appendChild(badge)
        section.appendChild(id_row)

        const grid = document.createElement("dl")
        grid.classList.add("pyc-build-detail__grid")

        this._append_field(grid, "Project", build.project_id)
        this._append_field(grid, "Runner kind", build.runner_kind)
        this._append_field(grid, "Repro digest", build.repro_digest_sha256)
        this._append_field(grid, "Started", format_timestamp(build.started_at))
        this._append_field(grid, "Finished", format_timestamp(build.finished_at))

        const layer5 = build.layer5_run_id
        if (layer5 !== undefined && layer5 !== null && layer5.length > 0) {
            this._append_field(grid, "Layer-5 run", layer5)
        }

        const reason = build.final_state_reason
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
    private _append_field(grid: HTMLElement, label: string, value: string): void {
        const field = document.createElement("div")
        field.classList.add("pyc-build-detail__field")
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
     * Build the toolchain-snapshot section -- one row per pinned
     * toolchain entry.
     *
     * @param toolchain The build's toolchain snapshot rows.
     *
     * @returns A populated toolchain section element.
     */
    private _build_toolchain(toolchain: BuildToolchainSnapshot[]): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-build-detail__toolchain")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Toolchain")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-build-detail__section-heading")
        heading.textContent = "Toolchain"
        section.appendChild(heading)

        const list = document.createElement("ul")
        list.classList.add("pyc-build-detail__toolchain-list")
        for (const entry of toolchain) {
            const item = document.createElement("li")
            item.classList.add("pyc-build-detail__toolchain-entry")
            const key = document.createElement("strong")
            key.textContent = entry.key
            item.appendChild(key)
            const version = entry.version
            if (version !== undefined && version !== null && version.length > 0) {
                const version_el = document.createElement("span")
                version_el.textContent = " " + version
                item.appendChild(version_el)
            }
            list.appendChild(item)
        }
        section.appendChild(list)
        return section
    }

    /**
     * Render the artifacts section from the current ``_artifacts``
     * list -- a heading plus one row per artifact, or an empty
     * state.
     */
    private _render_artifacts(): void {
        if (this._root === null) {
            return
        }
        const section = this._root.querySelector('[data-role="artifacts-section"]')
        if (section === null) {
            return
        }

        const heading = document.createElement("h2")
        heading.classList.add("pyc-build-detail__section-heading")
        heading.textContent = "Artifacts"

        const list = document.createElement("ul")
        list.classList.add("pyc-build-detail__artifact-list")
        list.setAttribute("data-role", "artifact-list")

        if (this._artifacts.length === 0) {
            const empty = document.createElement("li")
            empty.classList.add("pyc-build-detail__artifact-empty")
            empty.setAttribute("data-role", "artifacts-empty")
            empty.textContent = "No artifacts recorded for this build."
            list.appendChild(empty)
        } else {
            for (const artifact of this._artifacts) {
                const item = document.createElement("li")
                item.classList.add("pyc-build-detail__artifact")

                const name = document.createElement("span")
                name.classList.add("pyc-build-detail__artifact-name")
                const display = artifact.artifact_name
                name.textContent = display !== undefined &&
                    display !== null && display.length > 0
                    ? display
                    : artifact.artifact_id
                item.appendChild(name)

                const type_chip = document.createElement("span")
                type_chip.classList.add("pyc-build-detail__artifact-type")
                type_chip.textContent = artifact.artifact_type
                item.appendChild(type_chip)

                const storage = artifact.storage_uri
                if (storage !== undefined && storage !== null && storage.length > 0) {
                    const link = document.createElement("a")
                    link.classList.add("pyc-build-detail__artifact-link")
                    link.setAttribute("href", storage)
                    link.setAttribute("rel", "noopener noreferrer")
                    link.textContent = "Download"
                    item.appendChild(link)
                }

                const digest = document.createElement("span")
                digest.classList.add("pyc-build-detail__artifact-digest")
                digest.textContent = short_id(artifact.sha256)
                digest.title = artifact.sha256
                item.appendChild(digest)

                list.appendChild(item)
            }
        }

        section.replaceChildren(heading, list)
        return
    }

    /**
     * Update the live-poll status banner. Shows a "live updates
     * on" affordance while polling and a "build finished" note
     * once the build reaches a terminal state.
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
            el.textContent = "Build in progress — refreshing every 5 seconds."
            return
        }
        if (this._poll_status === "stopped" && this._terminal === true) {
            el.hidden = false
            el.setAttribute("data-tone", "neutral")
            el.textContent = "Build finished — live updates ended."
            return
        }
        el.hidden = true
        el.textContent = ""
        return
    }
}
