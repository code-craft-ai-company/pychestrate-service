/**
 * ``<pyc-release-channels>`` -- the release-channels list view
 * Custom Element.
 *
 * A release channel records a published release for a component
 * onto one of the ``canary | beta | stable`` channels. On mount
 * the element fetches the channels via
 * ``GET /api/v1/release-channels`` and renders a table grouped by
 * component + channel.
 *
 * The view surfaces:
 *
 * * A "Publish Release" inline form -- POSTs a publish request
 *   (component + channel + version + artifact uri + artifact
 *   sha256) to ``/api/v1/release-channels``.
 * * A per-row "Show Published Release" action -- reads the entry
 *   via ``…/release-channels/{channel_id}`` and renders the
 *   published-release detail panel.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

/**
 * Base path of the release-channels REST surface.
 */
const RELEASE_CHANNELS_PATH: string = "/api/v1/release-channels"

/**
 * The ``canary | beta | stable`` channel values.
 */
export const RELEASE_CHANNEL_VALUES: readonly string[] = [
    "canary",
    "beta",
    "stable",
]

/**
 * One release-channel entry.
 */
export interface ReleaseChannelEntry {
    channel_id: string
    release_id: string
    component: string
    version: string
    channel: string
    artifact_uri: string
    artifact_sha256: string
    issuer_key_id?: string | null
    issued_at?: string | null
    issued_by?: string | null
    status: string
    rollout_fraction: number
    stage_started_at?: string | null
    previous_release_id?: string | null
}

/**
 * The release-channels list page response shape.
 */
export interface ReleaseChannelPage {
    items: ReleaseChannelEntry[]
    meta: {
        page: number
        per_page: number
        total: number
    }
}

/**
 * Outcome of a publish-release POST, surfaced to the caller.
 */
export interface PublishOutcome {
    ok: boolean
    status: number
    channelId: string
    message: string
}

/**
 * Build the ``…/release-channels/{channel_id}`` URL the
 * show-published-release action targets.
 *
 * @param channel_id The release-channel entry identifier.
 *
 * @returns A relative URL string.
 */
export function build_release_channel_url(channel_id: string): string {
    const rtnval = RELEASE_CHANNELS_PATH + "/" +
        encodeURIComponent(channel_id)
    return rtnval
}

/**
 * Format an ISO-8601 timestamp for display. Returns an em-dash
 * placeholder for null/undefined/empty values.
 *
 * @param value ISO-8601 timestamp or null.
 *
 * @returns A locale-formatted timestamp or ``"—"``.
 */
export function format_release_timestamp(
    value: string | null | undefined,
): string {
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
 * Format a 0..1 rollout fraction as a percentage string.
 *
 * @param value Rollout fraction in the 0..1 range.
 *
 * @returns A percentage string such as ``"50%"``.
 */
export function format_rollout(value: number): string {
    if (typeof value !== "number" || Number.isNaN(value) === true) {
        const rtnval = "—"
        return rtnval
    }
    const percent = value * 100
    const rtnval = String(Math.round(percent)) + "%"
    return rtnval
}

/**
 * Classify a release-status value into a coarse badge tone.
 *
 * @param status The release-status string.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function release_status_tone(status: string): string {
    if (typeof status !== "string") {
        const rtnval = "neutral"
        return rtnval
    }
    const lowered = status.toLowerCase()
    if (lowered === "active" || lowered === "published") {
        const rtnval = "ok"
        return rtnval
    }
    if (lowered === "rolling_out" || lowered === "staged") {
        const rtnval = "warn"
        return rtnval
    }
    if (
        lowered === "rolled_back" ||
        lowered === "failed" ||
        lowered === "revoked"
    ) {
        const rtnval = "error"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Translate a publish-release HTTP status into operator guidance.
 *
 * @param status HTTP status code of the publish response.
 *
 * @returns A human-readable message.
 */
export function publish_message_for_status(status: number): string {
    if (status === 201 || status === 200) {
        const rtnval = "Release published to the channel."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "That version is already published on the channel."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "The publish request was rejected — check the fields."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to publish releases."
        return rtnval
    }
    const rtnval = "Failed to publish release (HTTP " +
        String(status) + ")."
    return rtnval
}

/**
 * The release-channels list view Custom Element. Register it with
 * ``customElements.define("pyc-release-channels",
 * PycReleaseChannels)``.
 */
export class PycReleaseChannels extends HTMLElement {
    private _entries: ReleaseChannelEntry[]
    private _loading: boolean
    private _errored: boolean
    private _root: HTMLElement | null
    private _table_region: HTMLElement | null
    private _publish_region: HTMLElement | null
    private _detail_region: HTMLElement | null
    private _toast_region: HTMLElement | null

    public constructor() {
        super()
        this._entries = []
        this._loading = false
        this._errored = false
        this._root = null
        this._table_region = null
        this._publish_region = null
        this._detail_region = null
        this._toast_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to read the loading
     * flag without scraping the DOM.
     */
    public get loading(): boolean {
        const rtnval = this._loading
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to read the errored
     * flag without scraping the DOM.
     */
    public get errored(): boolean {
        const rtnval = this._errored
        return rtnval
    }

    /**
     * Lifecycle hook -- render the static chrome and kick off the
     * channels fetch when the element is inserted.
     */
    public connectedCallback(): void {
        this._render_chrome()
        void this._refresh()
        return
    }

    /**
     * Build the persistent chrome -- heading, publish + refresh
     * actions, publish-form region, table region, detail region,
     * toast region.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-ops")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-ops__heading")
        heading.textContent = "Release Channels"
        root.appendChild(heading)

        const controls = document.createElement("div")
        controls.classList.add("pyc-ops__controls")

        const publish_button = document.createElement("button")
        publish_button.classList.add("pyc-ops__button")
        publish_button.setAttribute("type", "button")
        publish_button.setAttribute("data-role", "publish-toggle")
        publish_button.textContent = "Publish Release"
        publish_button.addEventListener("click", () => {
            this._toggle_publish_form()
        })
        controls.appendChild(publish_button)

        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-ops__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            void this._refresh()
        })
        controls.appendChild(refresh_button)

        root.appendChild(controls)

        const publish_region = document.createElement("div")
        publish_region.classList.add("pyc-ops__form-region")
        publish_region.setAttribute("data-role", "publish-region")
        publish_region.hidden = true
        root.appendChild(publish_region)
        this._publish_region = publish_region

        const toast_region = document.createElement("div")
        toast_region.classList.add("pyc-ops__toast-region")
        toast_region.setAttribute("data-role", "toast-region")
        root.appendChild(toast_region)
        this._toast_region = toast_region

        const table_region = document.createElement("div")
        table_region.classList.add("pyc-ops__table-region")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const detail_region = document.createElement("div")
        detail_region.classList.add("pyc-ops__table-region")
        detail_region.setAttribute("data-role", "detail-region")
        root.appendChild(detail_region)
        this._detail_region = detail_region

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Fetch the release-channels list and re-render. Exposed so
     * unit tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        this._loading = true
        this._errored = false
        this._render_table_region()

        let page: ReleaseChannelPage | null = null
        try {
            const response = await fetch(RELEASE_CHANNELS_PATH, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "release-channels fetch failed: HTTP " +
                        String(response.status),
                )
            }
            const body = await response.json()
            page = body as ReleaseChannelPage
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.release_channels_fetch_failed",
                { reason: String(reason) },
            )
            this._loading = false
            this._errored = true
            this._render_table_region()
            return
        }

        if (page === null || Array.isArray(page.items) === false) {
            this._loading = false
            this._errored = true
            this._render_table_region()
            return
        }

        this._entries = page.items
        this._loading = false
        this._errored = false
        this._render_table_region()
        return
    }

    private _render_table_region(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-ops__notice")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading release channels…"
            region.replaceChildren(loading)
            return
        }

        if (this._errored === true) {
            const error = document.createElement("p")
            error.classList.add("pyc-ops__notice", "pyc-ops__notice--error")
            error.setAttribute("data-role", "error-state")
            error.textContent =
                "Failed to load release channels. Try refreshing."
            region.replaceChildren(error)
            return
        }

        if (this._entries.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-ops__notice")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No releases published to any channel yet"
            region.replaceChildren(empty)
            return
        }

        const table = this._build_table()
        region.replaceChildren(table)
        return
    }

    private _build_table(): HTMLTableElement {
        const table = document.createElement("table")
        table.classList.add("pyc-ops__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Component",
            "Channel",
            "Version",
            "Status",
            "Rollout",
            "Issued",
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

        const ordered = this._entries.slice()
        ordered.sort(
            (left: ReleaseChannelEntry, right: ReleaseChannelEntry): number => {
                const left_key = left.component + "/" + left.channel
                const right_key = right.component + "/" + right.channel
                if (left_key < right_key) {
                    return -1
                }
                if (left_key > right_key) {
                    return 1
                }
                return 0
            },
        )

        const tbody = document.createElement("tbody")
        for (const entry of ordered) {
            tbody.appendChild(this._build_row(entry))
        }
        table.appendChild(tbody)
        return table
    }

    private _build_row(entry: ReleaseChannelEntry): HTMLTableRowElement {
        const row = document.createElement("tr")
        row.setAttribute("data-channel-id", entry.channel_id)

        this._append_text_cell(row, entry.component)

        const channel_cell = document.createElement("td")
        const channel_badge = document.createElement("span")
        channel_badge.classList.add("pyc-ops__badge")
        channel_badge.setAttribute("data-tone", "neutral")
        channel_badge.textContent = entry.channel
        channel_cell.appendChild(channel_badge)
        row.appendChild(channel_cell)

        this._append_text_cell(row, entry.version)

        const status_cell = document.createElement("td")
        const status_badge = document.createElement("span")
        status_badge.classList.add("pyc-ops__badge")
        status_badge.setAttribute(
            "data-tone", release_status_tone(entry.status),
        )
        status_badge.textContent = entry.status
        status_cell.appendChild(status_badge)
        row.appendChild(status_cell)

        this._append_text_cell(row, format_rollout(entry.rollout_fraction))
        this._append_text_cell(
            row, format_release_timestamp(entry.issued_at),
        )

        const actions_cell = document.createElement("td")
        const show_button = document.createElement("button")
        show_button.classList.add("pyc-ops__button", "pyc-ops__row-action")
        show_button.setAttribute("type", "button")
        show_button.setAttribute("data-role", "show-release")
        show_button.textContent = "Show Published Release"
        show_button.addEventListener("click", () => {
            show_button.disabled = true
            void this._on_show_release(entry, show_button)
        })
        actions_cell.appendChild(show_button)
        row.appendChild(actions_cell)

        return row
    }

    private async _on_show_release(
        entry: ReleaseChannelEntry,
        button: HTMLButtonElement,
    ): Promise<void> {
        const detail = await this.loadReleaseChannel(entry.channel_id)
        button.disabled = false
        this._render_detail(detail)
        return
    }

    /**
     * Read one release-channel entry's published-release detail.
     * Exposed so unit tests can await the detail fetch.
     *
     * @param channel_id The entry to read.
     *
     * @returns The entry, or ``null`` when the read fails.
     */
    public async loadReleaseChannel(
        channel_id: string,
    ): Promise<ReleaseChannelEntry | null> {
        let entry: ReleaseChannelEntry | null = null
        try {
            const url = build_release_channel_url(channel_id)
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                const parsed = body as ReleaseChannelEntry
                if (
                    parsed !== null &&
                    typeof parsed.channel_id === "string"
                ) {
                    entry = parsed
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.release_channel_fetch_failed",
                { reason: String(reason) },
            )
        }
        const rtnval = entry
        return rtnval
    }

    private _render_detail(entry: ReleaseChannelEntry | null): void {
        if (this._detail_region === null) {
            return
        }
        const region = this._detail_region
        if (entry === null) {
            const error = document.createElement("p")
            error.classList.add("pyc-ops__notice", "pyc-ops__notice--error")
            error.setAttribute("data-role", "detail-error")
            error.textContent = "Failed to load the published release."
            region.replaceChildren(error)
            return
        }

        const heading = document.createElement("h2")
        heading.classList.add("pyc-ops__subheading")
        heading.textContent = "Published Release — " + entry.component +
            " " + entry.version

        const list = document.createElement("dl")
        list.classList.add("pyc-ops__detail-list")
        list.setAttribute("data-role", "release-detail")
        this._append_detail_pair(list, "Channel", entry.channel)
        this._append_detail_pair(list, "Status", entry.status)
        this._append_detail_pair(
            list, "Rollout", format_rollout(entry.rollout_fraction),
        )
        this._append_detail_pair(list, "Artifact URI", entry.artifact_uri)
        this._append_detail_pair(
            list, "Artifact SHA-256", entry.artifact_sha256,
        )
        this._append_detail_pair(
            list, "Issued by", entry.issued_by ?? "—",
        )
        this._append_detail_pair(
            list, "Issued at", format_release_timestamp(entry.issued_at),
        )
        region.replaceChildren(heading, list)
        return
    }

    private _append_detail_pair(
        list: HTMLDListElement,
        label: string,
        value: string,
    ): void {
        const term = document.createElement("dt")
        term.classList.add("pyc-ops__detail-term")
        term.textContent = label
        const detail = document.createElement("dd")
        detail.classList.add("pyc-ops__detail-value")
        detail.textContent = value
        list.appendChild(term)
        list.appendChild(detail)
        return
    }

    private _toggle_publish_form(): void {
        if (this._publish_region === null) {
            return
        }
        const region = this._publish_region
        if (region.hidden === true) {
            this._render_publish_form()
            region.hidden = false
        } else {
            region.hidden = true
        }
        return
    }

    private _render_publish_form(): void {
        if (this._publish_region === null) {
            return
        }
        const form = document.createElement("form")
        form.classList.add("pyc-ops__form")
        form.setAttribute("data-role", "publish-form")

        const component_input = this._build_field(
            form, "Component", "publish-component", "agent-runtime",
        )

        const channel_label = document.createElement("label")
        channel_label.classList.add("pyc-ops__field")
        channel_label.textContent = "Channel"
        const channel_select = document.createElement("select")
        channel_select.classList.add("pyc-ops__select")
        channel_select.setAttribute("data-role", "publish-channel")
        for (const channel of RELEASE_CHANNEL_VALUES) {
            const option = document.createElement("option")
            option.value = channel
            option.textContent = channel
            channel_select.appendChild(option)
        }
        channel_label.appendChild(channel_select)
        form.appendChild(channel_label)

        const version_input = this._build_field(
            form, "Version", "publish-version", "1.4.0",
        )
        const uri_input = this._build_field(
            form, "Artifact URI", "publish-uri", "oci://registry/x:1.4.0",
        )
        const sha_input = this._build_field(
            form, "Artifact SHA-256 (64 hex chars)", "publish-sha", "",
        )

        const submit = document.createElement("button")
        submit.classList.add("pyc-ops__submit")
        submit.setAttribute("type", "submit")
        submit.setAttribute("data-role", "publish-submit")
        submit.textContent = "Publish Release"
        form.appendChild(submit)

        const status = document.createElement("p")
        status.classList.add("pyc-ops__form-status")
        status.setAttribute("data-role", "publish-status")
        form.appendChild(status)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            void this._submit_publish(
                component_input,
                channel_select,
                version_input,
                uri_input,
                sha_input,
                submit,
                status,
            )
        })
        this._publish_region.replaceChildren(form)
        return
    }

    private async _submit_publish(
        component_input: HTMLInputElement,
        channel_select: HTMLSelectElement,
        version_input: HTMLInputElement,
        uri_input: HTMLInputElement,
        sha_input: HTMLInputElement,
        submit: HTMLButtonElement,
        status: HTMLElement,
    ): Promise<void> {
        const component = component_input.value.trim()
        const channel = channel_select.value
        const version = version_input.value.trim()
        const artifact_uri = uri_input.value.trim()
        const artifact_sha256 = sha_input.value.trim()
        if (
            component.length === 0 ||
            version.length === 0 ||
            artifact_uri.length === 0
        ) {
            status.textContent =
                "Component, version and artifact URI are required."
            return
        }
        if (artifact_sha256.length !== 64) {
            status.textContent =
                "Artifact SHA-256 must be 64 hexadecimal characters."
            return
        }
        submit.disabled = true
        status.textContent = "Publishing release…"
        const outcome = await this._do_publish(
            component, channel, version, artifact_uri, artifact_sha256,
        )
        submit.disabled = false
        status.textContent = ""
        this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error")
        if (outcome.ok === true) {
            await this._refresh()
        }
        return
    }

    /**
     * POST a release-publish request. Exposed so unit tests can
     * invoke a publish without a real form-submit event.
     *
     * @param component The component being published.
     * @param channel The target channel.
     * @param version The release version string.
     * @param artifact_uri The release artifact URI.
     * @param artifact_sha256 The 64-hex-char artifact digest.
     *
     * @returns The publish outcome.
     */
    public async publishRelease(
        component: string,
        channel: string,
        version: string,
        artifact_uri: string,
        artifact_sha256: string,
    ): Promise<PublishOutcome> {
        const rtnval = await this._do_publish(
            component, channel, version, artifact_uri, artifact_sha256,
        )
        return rtnval
    }

    private async _do_publish(
        component: string,
        channel: string,
        version: string,
        artifact_uri: string,
        artifact_sha256: string,
    ): Promise<PublishOutcome> {
        const payload: Record<string, unknown> = {
            component: component,
            channel: channel,
            version: version,
            artifact_uri: artifact_uri,
            artifact_sha256: artifact_sha256,
        }
        let status = 0
        let channel_id = ""
        try {
            const response = await fetch(RELEASE_CHANNELS_PATH, {
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
                const entry = body as ReleaseChannelEntry
                if (entry !== null && typeof entry.channel_id === "string") {
                    channel_id = entry.channel_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.ops.release_publish_failed",
                { reason: String(reason) },
            )
            const rtnval: PublishOutcome = {
                ok: false,
                status: 0,
                channelId: "",
                message: "Failed to reach the release-channels service.",
            }
            return rtnval
        }
        const ok = status === 201 || status === 200
        const rtnval: PublishOutcome = {
            ok: ok,
            status: status,
            channelId: channel_id,
            message: publish_message_for_status(status),
        }
        return rtnval
    }

    /**
     * Append a plain-text ``<td>`` to a table row.
     *
     * @param row The row to append the cell to.
     * @param text The cell text content.
     */
    private _append_text_cell(row: HTMLTableRowElement, text: string): void {
        const cell = document.createElement("td")
        cell.textContent = text
        row.appendChild(cell)
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
    private _build_field(
        form: HTMLFormElement,
        label_text: string,
        role: string,
        placeholder: string,
    ): HTMLInputElement {
        const label = document.createElement("label")
        label.classList.add("pyc-ops__field")
        label.textContent = label_text
        const input = document.createElement("input")
        input.classList.add("pyc-ops__input")
        input.setAttribute("type", "text")
        input.setAttribute("data-role", role)
        input.setAttribute("placeholder", placeholder)
        label.appendChild(input)
        form.appendChild(label)
        return input
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
        toast.classList.add("pyc-ops__toast")
        toast.setAttribute("data-role", "toast")
        toast.setAttribute("data-tone", tone)

        const text = document.createElement("span")
        text.textContent = message
        toast.appendChild(text)

        const dismiss = document.createElement("button")
        dismiss.classList.add("pyc-ops__toast-dismiss")
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
