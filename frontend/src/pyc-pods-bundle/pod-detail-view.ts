/**
 * ``<pyc-pod-detail>`` -- the pod detail view Custom Element.
 *
 * On mount (route ``/pods/{pod_id}?project_id=...``) the element
 * fetches, in order:
 *
 * * ``GET …/pod-definitions/{pod_id}`` -- the pod's definition
 *   (name, version, spec, members).
 * * ``GET …/pods/{pod_id}/state`` -- the live runtime state row.
 * * ``GET …/pods/{pod_id}/registration`` -- the active per-client
 *   registration (the client backing the pod). 404 means no
 *   active registration -- rendered as an empty state, not an
 *   error.
 * * ``GET …/pods/{pod_id}/registrations`` -- the full registration
 *   history.
 * * ``GET …/pods/{pod_id}/state/history`` -- the lifecycle
 *   transition log.
 *
 * Missing-context note -- the ``/pods/{pod_id}`` route carries no
 * project id. All pod sub-resources are project-scoped, so the
 * view requires ``?project_id=`` in the query string (the pods
 * list emits it on every row link). When it is absent the view
 * renders an error rather than guessing.
 *
 * Live-update approach -- polling, not SSE. While the pod is in a
 * transient state (``PROVISIONING`` / ``DRAINING``) the view
 * re-fetches the state + history every 5 seconds, mirroring the
 * build-detail pattern. The poll timer is cleared the moment the
 * pod settles and on ``disconnectedCallback``.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

import {
    type PodDefinition,
    build_pod_definition_url,
    format_timestamp,
    member_count,
    short_id,
} from "./pods-list-view.js"

/**
 * The ``PodState`` enum -- mirrors ``pods.models.PodState``.
 */
export const POD_STATES: readonly string[] = [
    "DEFINED",
    "PROVISIONING",
    "READY",
    "IN_USE",
    "DRAINING",
    "RELEASED",
    "CLIENT_LOST",
    "FAILED",
]

/**
 * Pod states the view polls through -- a pod in one of these is
 * mid-transition and will settle without operator action.
 */
export const TRANSIENT_POD_STATES: readonly string[] = [
    "PROVISIONING",
    "DRAINING",
]

/**
 * The pod's live runtime state row, from
 * ``GET …/pods/{pod_id}/state``.
 */
export interface PodStateRow {
    pod_id: string
    state: string
    previous_state?: string | null
    last_transition_at?: string | null
    last_transition_event?: string | null
    transition_cursor: number
}

/**
 * The pod's active registration row, from
 * ``GET …/pods/{pod_id}/registration``.
 */
export interface PodRegistration {
    registration_id: string
    pod_id: string
    pod_definition_version: number
    client_id?: string | null
    state: string
    report_hash?: string | null
    registered_at?: string | null
}

/**
 * One registration-history row, from
 * ``GET …/pods/{pod_id}/registrations``.
 */
export interface PodRegistrationHistoryRow {
    registration_id: string
    state: string
    pod_definition_version: number
    registered_at?: string | null
    deregistered_at?: string | null
    deregister_reason?: string | null
}

/**
 * One lifecycle-transition log row, from
 * ``GET …/pods/{pod_id}/state/history``.
 */
export interface PodStateHistoryRow {
    log_id: string
    from_state?: string | null
    to_state: string
    event_kind?: string | null
    actor?: string | null
    applied_at?: string | null
}

/**
 * Connection / poll status of the live-update loop.
 */
export type PollStatus = "idle" | "polling" | "stopped"

/**
 * Diagnostic snapshot of the pod detail view's runtime state.
 * Exposed via the ``detailState`` accessor for unit tests.
 */
export interface PodDetailState {
    podId: string
    projectId: string
    loading: boolean
    errored: boolean
    pollStatus: PollStatus
    transient: boolean
}

/**
 * Interval, in milliseconds, between live-poll re-fetches while a
 * pod is in a transient state.
 */
const POLL_INTERVAL_MS: number = 5000

/**
 * Matches a canonical UUID -- the shape a valid ``pod_id`` takes.
 */
const UUID_PATTERN: RegExp =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Extract a ``pod_id`` from a shell-served path of the form
 * ``/pods/{pod_id}``. Returns an empty string when the path does
 * not name a single pod.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns The pod id segment, or ``""``.
 */
export function pod_id_from_path(path: string): string {
    if (typeof path !== "string" || path.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const prefix = "/pods/"
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
 * Read a ``project_id`` from a query string.
 *
 * @param search A location search string (e.g.
 *               ``"?project_id=abc"``).
 *
 * @returns The project id, or ``""`` when none is present.
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
    const rtnval = value.trim()
    return rtnval
}

/**
 * Decide whether a ``pod_id`` string is a syntactically valid
 * UUID.
 *
 * @param pod_id Candidate pod identifier.
 *
 * @returns True when the id is a canonical UUID.
 */
export function is_valid_pod_id(pod_id: string): boolean {
    if (typeof pod_id !== "string") {
        const rtnval = false
        return rtnval
    }
    const rtnval = UUID_PATTERN.test(pod_id)
    return rtnval
}

/**
 * Decide whether a pod state is transient -- mid-transition and
 * worth polling.
 *
 * @param state One of the ``PodState`` enum values.
 *
 * @returns True when the pod is mid-transition.
 */
export function is_transient_pod_state(state: string): boolean {
    const rtnval = TRANSIENT_POD_STATES.indexOf(state) >= 0
    return rtnval
}

/**
 * Classify a pod state into a coarse badge tone.
 *
 * @param state One of the ``PodState`` enum values.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function pod_state_tone(state: string): string {
    if (state === "READY" || state === "IN_USE") {
        const rtnval = "ok"
        return rtnval
    }
    if (state === "FAILED" || state === "CLIENT_LOST") {
        const rtnval = "error"
        return rtnval
    }
    if (state === "PROVISIONING" || state === "DRAINING") {
        const rtnval = "warn"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Build the ``GET …/pods/{pod_id}/state`` URL.
 *
 * @param project_id Owning project identifier.
 * @param pod_id Pod identifier.
 *
 * @returns A relative URL string.
 */
export function build_pod_state_url(
        project_id: string,
        pod_id: string,
    ): string {
    const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) +
        "/pods/" + encodeURIComponent(pod_id) + "/state"
    return rtnval
}

/**
 * Build the ``GET …/pods/{pod_id}/state/history`` URL.
 *
 * @param project_id Owning project identifier.
 * @param pod_id Pod identifier.
 *
 * @returns A relative URL string.
 */
export function build_pod_state_history_url(
        project_id: string,
        pod_id: string,
    ): string {
    const rtnval = build_pod_state_url(project_id, pod_id) + "/history"
    return rtnval
}

/**
 * Build the ``GET …/pods/{pod_id}/registration`` URL.
 *
 * @param project_id Owning project identifier.
 * @param pod_id Pod identifier.
 *
 * @returns A relative URL string.
 */
export function build_pod_registration_url(
        project_id: string,
        pod_id: string,
    ): string {
    const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) +
        "/pods/" + encodeURIComponent(pod_id) + "/registration"
    return rtnval
}

/**
 * Build the ``GET …/pods/{pod_id}/registrations`` URL.
 *
 * @param project_id Owning project identifier.
 * @param pod_id Pod identifier.
 *
 * @returns A relative URL string.
 */
export function build_pod_registrations_url(
        project_id: string,
        pod_id: string,
    ): string {
    const rtnval = "/api/v1/projects/" + encodeURIComponent(project_id) +
        "/pods/" + encodeURIComponent(pod_id) + "/registrations"
    return rtnval
}

/**
 * The pod detail view Custom Element. Register it with
 * ``customElements.define("pyc-pod-detail", PycPodDetail)``.
 */
export class PycPodDetail extends HTMLElement {
    private _pod_id: string
    private _project_id: string
    private _definition: PodDefinition | null
    private _state_row: PodStateRow | null
    private _registration: PodRegistration | null
    private _registration_history: PodRegistrationHistoryRow[]
    private _state_history: PodStateHistoryRow[]
    private _loading: boolean
    private _errored: boolean
    private _transient: boolean
    private _poll_status: PollStatus
    private _poll_timer: ReturnType<typeof setTimeout> | null
    private _root: HTMLElement | null

    public constructor() {
        super()
        this._pod_id = ""
        this._project_id = ""
        this._definition = null
        this._state_row = null
        this._registration = null
        this._registration_history = []
        this._state_history = []
        this._loading = false
        this._errored = false
        this._transient = false
        this._poll_status = "idle"
        this._poll_timer = null
        this._root = null
    }

    /**
     * Observed attributes -- ``pod-id`` / ``project-id`` may be
     * supplied explicitly by a host; otherwise they are read from
     * the path / query string on mount.
     */
    public static get observedAttributes(): string[] {
        const rtnval = ["pod-id", "project-id"]
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the view's
     * runtime state without scraping the DOM.
     */
    public get detailState(): PodDetailState {
        const rtnval: PodDetailState = {
            podId: this._pod_id,
            projectId: this._project_id,
            loading: this._loading,
            errored: this._errored,
            pollStatus: this._poll_status,
            transient: this._transient,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- resolve the pod + project ids, render the
     * chrome, and fetch the initial snapshot.
     */
    public connectedCallback(): void {
        const attr_pod = this.getAttribute("pod-id")
        if (attr_pod !== null && attr_pod.length > 0) {
            this._pod_id = attr_pod
        } else {
            this._pod_id = pod_id_from_path(window.location.pathname)
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
     * away never leaks a timer.
     */
    public disconnectedCallback(): void {
        this._stop_poll()
        return
    }

    /**
     * Fetch the pod snapshot then -- when the pod is in a transient
     * state -- start the live-poll loop. Exposed so unit tests can
     * await a load cycle.
     */
    public async load(): Promise<void> {
        await this._load()
        return
    }

    private async _load(): Promise<void> {
        if (is_valid_pod_id(this._pod_id) === false) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        if (this._project_id.length === 0) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        this._loading = true
        this._errored = false
        this._render_body()

        const definition = await this._fetch_json<PodDefinition>(
            build_pod_definition_url(this._project_id, this._pod_id),
            "definition_fetch_failed",
        )
        if (definition === null) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        this._definition = definition

        await this._refresh_runtime()

        this._loading = false
        this._errored = false
        this._render_body()

        if (this._transient === true) {
            this._start_poll()
        } else {
            this._poll_status = "stopped"
            this._render_poll_banner()
        }
        return
    }

    /**
     * Re-fetch the live state, registration and history rows.
     * Shared by the initial load and each poll cycle.
     */
    private async _refresh_runtime(): Promise<void> {
        const state_row = await this._fetch_json<PodStateRow>(
            build_pod_state_url(this._project_id, this._pod_id),
            "state_fetch_failed",
        )
        if (state_row !== null) {
            this._state_row = state_row
            this._transient = is_transient_pod_state(state_row.state)
        }

        const registration = await this._fetch_json<PodRegistration>(
            build_pod_registration_url(this._project_id, this._pod_id),
            "registration_fetch_failed",
        )
        this._registration = registration

        const history = await this._fetch_json<PodRegistrationHistoryRow[]>(
            build_pod_registrations_url(this._project_id, this._pod_id),
            "registrations_fetch_failed",
        )
        if (history !== null && Array.isArray(history) === true) {
            this._registration_history = history
        }

        const state_history = await this._fetch_json<PodStateHistoryRow[]>(
            build_pod_state_history_url(this._project_id, this._pod_id),
            "state_history_fetch_failed",
        )
        if (state_history !== null && Array.isArray(state_history) === true) {
            this._state_history = state_history
        }
        return
    }

    /**
     * Fetch a JSON document. A non-OK response or a thrown error
     * yields ``null`` -- callers decide whether a missing document
     * is an error or an empty state.
     *
     * @param url Relative URL to GET.
     * @param failure_tag A log tag for diagnostic warnings.
     *
     * @returns The parsed JSON body, or ``null`` on failure.
     */
    private async _fetch_json<T>(
            url: string,
            failure_tag: string,
        ): Promise<T | null> {
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                const rtnval = null
                return rtnval
            }
            const body = await response.json()
            const rtnval = body as T
            return rtnval
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.pods." + failure_tag,
                { reason: String(reason) },
            )
            const rtnval = null
            return rtnval
        }
    }

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
        const handle = timer as unknown as { unref?: () => void }
        if (typeof handle.unref === "function") {
            handle.unref()
        }
        this._poll_timer = timer
        return
    }

    /**
     * Run one poll cycle -- re-fetch runtime rows, re-render, and
     * either reschedule (still transient) or stop (now settled).
     * Exposed so unit tests can drive a poll cycle without waiting
     * on a real timer.
     */
    public async pollOnce(): Promise<void> {
        await this._poll_once()
        return
    }

    private async _poll_once(): Promise<void> {
        await this._refresh_runtime()
        this._render_body()
        if (this._transient === false) {
            this._stop_poll()
            this._poll_status = "stopped"
            this._render_poll_banner()
            return
        }
        this._schedule_poll()
        return
    }

    private _stop_poll(): void {
        if (this._poll_timer !== null) {
            clearTimeout(this._poll_timer)
            this._poll_timer = null
        }
        return
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-pod-detail")
        root.setAttribute("role", "main")
        root.setAttribute("aria-label", "Pod detail")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-pod-detail__heading")
        heading.textContent = "Pod detail"
        root.appendChild(heading)

        const back = document.createElement("a")
        back.classList.add("pyc-pod-detail__back-link")
        back.setAttribute("href", "/pods")
        back.setAttribute("data-role", "back-link")
        back.textContent = "Back to pods"
        root.appendChild(back)

        const banner = document.createElement("p")
        banner.classList.add("pyc-pod-detail__banner")
        banner.setAttribute("data-role", "poll-banner")
        banner.setAttribute("role", "status")
        banner.hidden = true
        root.appendChild(banner)

        const body = document.createElement("div")
        body.classList.add("pyc-pod-detail__body")
        body.setAttribute("data-role", "body")
        root.appendChild(body)

        this._root = root
        this.replaceChildren(root)
        return
    }

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
            loading.classList.add("pyc-pod-detail__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading pod…"
            body.replaceChildren(loading)
            return
        }

        if (this._errored === true || this._definition === null) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-pod-detail__status",
                "pyc-pod-detail__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent =
                "Failed to load this pod. A project id query " +
                "parameter is required — try refreshing from the " +
                "pods list."
            body.replaceChildren(error)
            return
        }

        const fragment = document.createDocumentFragment()
        fragment.appendChild(this._build_summary(this._definition))
        fragment.appendChild(this._build_members(this._definition))
        fragment.appendChild(this._build_registration())
        fragment.appendChild(this._build_registration_history())
        fragment.appendChild(this._build_state_history())
        body.replaceChildren(fragment)
        return
    }

    private _build_summary(definition: PodDefinition): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-pod-detail__summary")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Pod summary")

        const id_row = document.createElement("div")
        id_row.classList.add("pyc-pod-detail__id-row")

        const id_value = document.createElement("span")
        id_value.classList.add("pyc-pod-detail__pod-id")
        id_value.setAttribute("data-role", "pod-id")
        id_value.textContent = short_id(definition.pod_id)
        id_value.title = definition.pod_id
        id_row.appendChild(id_value)

        const state_value =
            this._state_row !== null ? this._state_row.state : "DEFINED"
        const badge = document.createElement("span")
        badge.classList.add("pyc-pod-detail__badge")
        badge.setAttribute("data-role", "state-badge")
        badge.setAttribute("data-tone", pod_state_tone(state_value))
        badge.textContent = state_value
        id_row.appendChild(badge)
        section.appendChild(id_row)

        const grid = document.createElement("dl")
        grid.classList.add("pyc-pod-detail__grid")
        this._append_field(grid, "Pod id", definition.pod_id)
        this._append_field(grid, "Pod name", definition.pod_name)
        this._append_field(grid, "Project", definition.project_id)
        this._append_field(
            grid,
            "Version",
            "v" + String(definition.current_version),
        )
        this._append_field(
            grid,
            "Members",
            String(member_count(definition.spec)),
        )
        this._append_field(
            grid,
            "Created",
            format_timestamp(definition.created_at),
        )
        if (
            definition.spec_hash !== null &&
            definition.spec_hash !== undefined &&
            definition.spec_hash.length > 0
        ) {
            this._append_field(grid, "Spec hash", definition.spec_hash)
        }
        if (this._state_row !== null) {
            this._append_field(
                grid,
                "Last transition",
                format_timestamp(this._state_row.last_transition_at),
            )
            const event = this._state_row.last_transition_event
            if (event !== null && event !== undefined && event.length > 0) {
                this._append_field(grid, "Last event", event)
            }
        }
        section.appendChild(grid)
        return section
    }

    private _build_members(definition: PodDefinition): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-pod-detail__members")
        section.setAttribute("data-role", "members-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Pod members")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-pod-detail__section-heading")
        heading.textContent = "Members"
        section.appendChild(heading)

        const list = document.createElement("ul")
        list.classList.add("pyc-pod-detail__member-list")

        const spec = definition.spec
        let members: unknown[] = []
        if (spec !== null && spec !== undefined) {
            const raw = spec["members"]
            if (Array.isArray(raw) === true) {
                members = raw as unknown[]
            }
        }

        if (members.length === 0) {
            const empty = document.createElement("li")
            empty.classList.add("pyc-pod-detail__member-empty")
            empty.textContent = "This pod definition declares no members."
            list.appendChild(empty)
        } else {
            for (const member of members) {
                const item = document.createElement("li")
                item.classList.add("pyc-pod-detail__member-entry")
                item.textContent = this._member_label(member)
                list.appendChild(item)
            }
        }
        section.appendChild(list)
        return section
    }

    /**
     * Derive a display label for one pod-spec member entry. A
     * member is typically an object carrying a ``name`` / ``kind``;
     * fall back to a JSON rendering when the shape is unexpected.
     *
     * @param member One entry from the spec's ``members`` array.
     *
     * @returns A human-readable label.
     */
    private _member_label(member: unknown): string {
        if (member !== null && typeof member === "object") {
            const record = member as Record<string, unknown>
            const name = record["name"]
            const kind = record["kind"]
            const name_str = typeof name === "string" ? name : ""
            const kind_str = typeof kind === "string" ? kind : ""
            if (name_str.length > 0 && kind_str.length > 0) {
                const rtnval = name_str + " (" + kind_str + ")"
                return rtnval
            }
            if (name_str.length > 0) {
                const rtnval = name_str
                return rtnval
            }
            if (kind_str.length > 0) {
                const rtnval = kind_str
                return rtnval
            }
        }
        if (typeof member === "string") {
            const rtnval = member
            return rtnval
        }
        const rtnval = JSON.stringify(member)
        return rtnval
    }

    private _build_registration(): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-pod-detail__registration")
        section.setAttribute("data-role", "registration-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Registered client")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-pod-detail__section-heading")
        heading.textContent = "Registered client"
        section.appendChild(heading)

        if (this._registration === null) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-pod-detail__status")
            empty.setAttribute("data-role", "registration-empty")
            empty.textContent = "No active registration for this pod."
            section.appendChild(empty)
            return section
        }

        const grid = document.createElement("dl")
        grid.classList.add("pyc-pod-detail__grid")
        const client_id = this._registration.client_id
        if (
            client_id !== null &&
            client_id !== undefined &&
            client_id.length > 0
        ) {
            const field = document.createElement("div")
            field.classList.add("pyc-pod-detail__field")
            const term = document.createElement("dt")
            term.textContent = "Client"
            const def = document.createElement("dd")
            const link = document.createElement("a")
            link.classList.add("pyc-pod-detail__client-link")
            link.setAttribute("href", "/clients/" + client_id)
            link.textContent = short_id(client_id)
            link.title = client_id
            def.appendChild(link)
            field.appendChild(term)
            field.appendChild(def)
            grid.appendChild(field)
        } else {
            this._append_field(grid, "Client", "—")
        }
        this._append_field(grid, "Registration state", this._registration.state)
        this._append_field(
            grid,
            "Definition version",
            "v" + String(this._registration.pod_definition_version),
        )
        this._append_field(
            grid,
            "Registered",
            format_timestamp(this._registration.registered_at),
        )
        section.appendChild(grid)
        return section
    }

    private _build_registration_history(): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-pod-detail__registration-history")
        section.setAttribute("data-role", "registration-history-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Registration history")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-pod-detail__section-heading")
        heading.textContent = "Registration history"
        section.appendChild(heading)

        if (this._registration_history.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-pod-detail__status")
            empty.setAttribute("data-role", "registration-history-empty")
            empty.textContent = "No registration history for this pod."
            section.appendChild(empty)
            return section
        }

        const list = document.createElement("ul")
        list.classList.add("pyc-pod-detail__history-list")
        for (const row of this._registration_history) {
            const item = document.createElement("li")
            item.classList.add("pyc-pod-detail__history-entry")
            const summary = row.state + " · v" +
                String(row.pod_definition_version) + " · " +
                format_timestamp(row.registered_at)
            item.textContent = summary
            if (
                row.deregister_reason !== null &&
                row.deregister_reason !== undefined &&
                row.deregister_reason.length > 0
            ) {
                const reason = document.createElement("span")
                reason.classList.add("pyc-pod-detail__history-reason")
                reason.textContent = " — " + row.deregister_reason
                item.appendChild(reason)
            }
            list.appendChild(item)
        }
        section.appendChild(list)
        return section
    }

    private _build_state_history(): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-pod-detail__state-history")
        section.setAttribute("data-role", "state-history-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Lifecycle history")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-pod-detail__section-heading")
        heading.textContent = "Lifecycle history"
        section.appendChild(heading)

        if (this._state_history.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-pod-detail__status")
            empty.setAttribute("data-role", "state-history-empty")
            empty.textContent = "No lifecycle transitions recorded."
            section.appendChild(empty)
            return section
        }

        const list = document.createElement("ul")
        list.classList.add("pyc-pod-detail__history-list")
        for (const row of this._state_history) {
            const item = document.createElement("li")
            item.classList.add("pyc-pod-detail__history-entry")
            const from_label =
                row.from_state !== null && row.from_state !== undefined
                    ? row.from_state
                    : "∅"
            const summary = from_label + " → " + row.to_state +
                " · " + format_timestamp(row.applied_at)
            item.textContent = summary
            if (
                row.event_kind !== null &&
                row.event_kind !== undefined &&
                row.event_kind.length > 0
            ) {
                const event = document.createElement("span")
                event.classList.add("pyc-pod-detail__history-event")
                event.textContent = " (" + row.event_kind + ")"
                item.appendChild(event)
            }
            list.appendChild(item)
        }
        section.appendChild(list)
        return section
    }

    private _append_field(
            grid: HTMLElement,
            label: string,
            value: string,
        ): void {
        const field = document.createElement("div")
        field.classList.add("pyc-pod-detail__field")
        const term = document.createElement("dt")
        term.textContent = label
        const def = document.createElement("dd")
        def.textContent = value
        field.appendChild(term)
        field.appendChild(def)
        grid.appendChild(field)
        return
    }

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
                "Pod is mid-transition — refreshing every 5 seconds."
            return
        }
        if (this._poll_status === "stopped" && this._transient === false) {
            el.hidden = true
            el.textContent = ""
            return
        }
        el.hidden = true
        el.textContent = ""
        return
    }
}
