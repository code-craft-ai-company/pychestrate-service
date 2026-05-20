/**
 * ``<pyc-client-detail>`` -- the enrolled-client detail view Custom
 * Element.
 *
 * On mount (route ``/clients/{client_id}``) the element fetches
 * ``GET /api/v1/clients/{client_id}`` and renders the client's
 * identity, enrollment info, runtime liveness, transport, agent
 * version and the full capability / attribute map.
 *
 * Missing-endpoint note -- the operator-facing clients REST surface
 * (``clients_routes.py``) exposes only a list endpoint and a
 * single-client read endpoint; there is no per-client heartbeat-
 * history endpoint and no client -> pods reverse-index endpoint.
 * The client-dispatch heartbeat route is mTLS-only and not for the
 * UI. So this view renders the single ``last_seen`` / ``degraded_at``
 * timestamps the read endpoint returns as a one-row "heartbeat"
 * summary, and renders the single ``pod_name`` the client enrolled
 * under rather than a full backed-pods list. A full heartbeat-
 * history view and a backed-pods reverse index are flagged as a
 * follow-up requiring new server read endpoints.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

import {
    type Client,
    build_client_detail_url,
    capability_tags,
    format_timestamp,
    liveness_tone,
    short_id,
    status_tone,
} from "./clients-list-view.js"

/**
 * Diagnostic snapshot of the client detail view's runtime state.
 * Exposed via the ``detailState`` accessor for unit tests.
 */
export interface ClientDetailState {
    clientId: string
    loading: boolean
    errored: boolean
}

/**
 * Matches a canonical UUID -- the shape a valid ``client_id`` takes.
 */
const UUID_PATTERN: RegExp =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Extract a ``client_id`` from a shell-served path of the form
 * ``/clients/{client_id}``. Returns an empty string when the path
 * does not name a single client.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns The client id segment, or ``""`` when the path is not a
 *          client-detail path.
 */
export function client_id_from_path(path: string): string {
    if (typeof path !== "string" || path.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const prefix = "/clients/"
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
 * Decide whether a ``client_id`` string is a syntactically valid
 * UUID. The detail view refuses to make a network call for an id
 * that fails this check.
 *
 * @param client_id Candidate client identifier.
 *
 * @returns True when the id is a canonical UUID.
 */
export function is_valid_client_id(client_id: string): boolean {
    if (typeof client_id !== "string") {
        const rtnval = false
        return rtnval
    }
    const rtnval = UUID_PATTERN.test(client_id)
    return rtnval
}

/**
 * The client detail view Custom Element. Register it with
 * ``customElements.define("pyc-client-detail", PycClientDetail)``.
 */
export class PycClientDetail extends HTMLElement {
    private _client_id: string
    private _client: Client | null
    private _loading: boolean
    private _errored: boolean
    private _root: HTMLElement | null

    public constructor() {
        super()
        this._client_id = ""
        this._client = null
        this._loading = false
        this._errored = false
        this._root = null
    }

    /**
     * Observed attributes -- ``client-id`` may be supplied
     * explicitly by a host; otherwise it is read from the path on
     * mount.
     */
    public static get observedAttributes(): string[] {
        const rtnval = ["client-id"]
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the view's
     * runtime state without scraping the DOM.
     */
    public get detailState(): ClientDetailState {
        const rtnval: ClientDetailState = {
            clientId: this._client_id,
            loading: this._loading,
            errored: this._errored,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- resolve the client id, render the chrome,
     * and fetch the snapshot.
     */
    public connectedCallback(): void {
        const attr_id = this.getAttribute("client-id")
        if (attr_id !== null && attr_id.length > 0) {
            this._client_id = attr_id
        } else {
            this._client_id = client_id_from_path(window.location.pathname)
        }
        this._render_chrome()
        void this._load()
        return
    }

    /**
     * Fetch the client snapshot. Exposed so unit tests can await a
     * load cycle.
     */
    public async load(): Promise<void> {
        await this._load()
        return
    }

    private async _load(): Promise<void> {
        if (is_valid_client_id(this._client_id) === false) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        this._loading = true
        this._errored = false
        this._render_body()

        const client = await this._fetch_client()
        if (client === null) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }

        this._client = client
        this._loading = false
        this._errored = false
        this._render_body()
        return
    }

    private async _fetch_client(): Promise<Client | null> {
        const url = build_client_detail_url(this._client_id)
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "client fetch failed: HTTP " + String(response.status),
                )
            }
            const body = await response.json()
            const rtnval = body as Client
            return rtnval
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.clients.detail_fetch_failed",
                { reason: String(reason) },
            )
            const rtnval = null
            return rtnval
        }
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-client-detail")
        root.setAttribute("role", "main")
        root.setAttribute("aria-label", "Client detail")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-client-detail__heading")
        heading.textContent = "Client detail"
        root.appendChild(heading)

        const back = document.createElement("a")
        back.classList.add("pyc-client-detail__back-link")
        back.setAttribute("href", "/clients")
        back.setAttribute("data-role", "back-link")
        back.textContent = "Back to clients"
        root.appendChild(back)

        const body = document.createElement("div")
        body.classList.add("pyc-client-detail__body")
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
            loading.classList.add("pyc-client-detail__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading client…"
            body.replaceChildren(loading)
            return
        }

        if (this._errored === true || this._client === null) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-client-detail__status",
                "pyc-client-detail__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load this client. Try refreshing."
            body.replaceChildren(error)
            return
        }

        const fragment = document.createDocumentFragment()
        fragment.appendChild(this._build_summary(this._client))
        fragment.appendChild(this._build_heartbeat(this._client))
        fragment.appendChild(this._build_pods(this._client))
        fragment.appendChild(this._build_capabilities(this._client))
        body.replaceChildren(fragment)
        return
    }

    private _build_summary(client: Client): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-client-detail__summary")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Client summary")

        const id_row = document.createElement("div")
        id_row.classList.add("pyc-client-detail__id-row")

        const id_value = document.createElement("span")
        id_value.classList.add("pyc-client-detail__client-id")
        id_value.setAttribute("data-role", "client-id")
        id_value.textContent = short_id(client.client_id)
        id_value.title = client.client_id
        id_row.appendChild(id_value)

        const status_badge = document.createElement("span")
        status_badge.classList.add("pyc-client-detail__badge")
        status_badge.setAttribute("data-role", "status-badge")
        status_badge.setAttribute("data-tone", status_tone(client.status))
        status_badge.textContent = client.status
        id_row.appendChild(status_badge)

        const liveness_badge = document.createElement("span")
        liveness_badge.classList.add("pyc-client-detail__badge")
        liveness_badge.setAttribute("data-role", "liveness-badge")
        liveness_badge.setAttribute(
            "data-tone",
            liveness_tone(client.liveness_state),
        )
        liveness_badge.textContent = client.liveness_state
        id_row.appendChild(liveness_badge)
        section.appendChild(id_row)

        const grid = document.createElement("dl")
        grid.classList.add("pyc-client-detail__grid")
        this._append_field(grid, "Client id", client.client_id)
        this._append_field(grid, "Project", client.project_id)
        this._append_field(grid, "Enrolled pod", client.pod_name)
        this._append_field(
            grid,
            "Enrolled",
            format_timestamp(client.enrolled_at),
        )
        this._append_field(
            grid,
            "Transport",
            client.transport_name !== null &&
            client.transport_name !== undefined &&
            client.transport_name.length > 0
                ? client.transport_name
                : "—",
        )
        this._append_field(
            grid,
            "Agent version",
            client.last_agent_version !== null &&
            client.last_agent_version !== undefined &&
            client.last_agent_version.length > 0
                ? client.last_agent_version
                : "—",
        )
        section.appendChild(grid)
        return section
    }

    private _build_heartbeat(client: Client): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-client-detail__heartbeat")
        section.setAttribute("data-role", "heartbeat-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Heartbeat")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-client-detail__section-heading")
        heading.textContent = "Heartbeat"
        section.appendChild(heading)

        const grid = document.createElement("dl")
        grid.classList.add("pyc-client-detail__grid")
        this._append_field(
            grid,
            "Last heartbeat",
            format_timestamp(client.last_seen),
        )
        this._append_field(
            grid,
            "Degraded since",
            format_timestamp(client.degraded_at),
        )
        section.appendChild(grid)

        const note = document.createElement("p")
        note.classList.add("pyc-client-detail__note")
        note.textContent =
            "Full heartbeat history is not exposed by the operator " +
            "REST surface — showing the latest cadence markers only."
        section.appendChild(note)
        return section
    }

    private _build_pods(client: Client): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-client-detail__pods")
        section.setAttribute("data-role", "pods-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Backed pods")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-client-detail__section-heading")
        heading.textContent = "Backed pods"
        section.appendChild(heading)

        const list = document.createElement("ul")
        list.classList.add("pyc-client-detail__pod-list")
        if (client.pod_name !== null && client.pod_name.length > 0) {
            const item = document.createElement("li")
            item.classList.add("pyc-client-detail__pod-entry")
            item.textContent = client.pod_name
            list.appendChild(item)
        } else {
            const empty = document.createElement("li")
            empty.classList.add("pyc-client-detail__pod-empty")
            empty.textContent = "This client is not enrolled under a pod."
            list.appendChild(empty)
        }
        section.appendChild(list)
        return section
    }

    private _build_capabilities(client: Client): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-client-detail__capabilities")
        section.setAttribute("data-role", "capabilities-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Capabilities")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-client-detail__section-heading")
        heading.textContent = "Capabilities & attributes"
        section.appendChild(heading)

        const tags = capability_tags(client.attributes)
        if (tags.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-client-detail__status")
            empty.setAttribute("data-role", "capabilities-empty")
            empty.textContent = "No capabilities reported for this client."
            section.appendChild(empty)
            return section
        }

        const tag_list = document.createElement("div")
        tag_list.classList.add("pyc-client-detail__tag-list")
        for (const tag of tags) {
            const chip = document.createElement("span")
            chip.classList.add("pyc-client-detail__tag")
            chip.textContent = tag
            tag_list.appendChild(chip)
        }
        section.appendChild(tag_list)
        return section
    }

    private _append_field(
            grid: HTMLElement,
            label: string,
            value: string,
        ): void {
        const field = document.createElement("div")
        field.classList.add("pyc-client-detail__field")
        const term = document.createElement("dt")
        term.textContent = label
        const def = document.createElement("dd")
        def.textContent = value
        field.appendChild(term)
        field.appendChild(def)
        grid.appendChild(field)
        return
    }
}
