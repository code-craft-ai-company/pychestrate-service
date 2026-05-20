/**
 * ``<pyc-feature-flags>`` -- the feature-flags management view
 * Custom Element.
 *
 * On mount the element fetches every registered flag via
 * ``GET /api/v1/flags`` and renders a table with the flag key,
 * kind, current version, state and an inline state-toggle action.
 *
 * The toggle action PATCHes ``/api/v1/flags/{flag_key}`` to move a
 * flag between the ``enabled`` and ``disabled`` states. A retired
 * flag is read-only -- it cannot be toggled.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

/**
 * Base path of the feature-flags REST surface.
 */
export const FLAGS_PATH: string = "/api/v1/flags"

/**
 * The flag-state value applied when a flag is toggled on.
 */
export const FLAG_STATE_ENABLED: string = "enabled"

/**
 * The flag-state value applied when a flag is toggled off.
 */
export const FLAG_STATE_DISABLED: string = "disabled"

/**
 * The flag-state value indicating a retired flag.
 */
export const FLAG_STATE_RETIRED: string = "retired"

/**
 * One feature-flag entry as returned by ``GET /api/v1/flags``.
 */
export interface FeatureFlagEntry {
    flag_key: string
    flag_kind: string | null
    current_version: number
    state: string | null
    retired_at: string | null
    grace_expires_at: string | null
    created_at: string | null
    updated_at: string | null
}

/**
 * Outcome of a flag-toggle PATCH, surfaced to the caller.
 */
export interface FlagToggleOutcome {
    ok: boolean
    status: number
    flagKey: string
    message: string
}

/**
 * Build the ``…/flags/{flag_key}`` URL the toggle PATCH targets.
 *
 * @param flag_key The flag identifier.
 *
 * @returns A relative URL string.
 */
export function build_flag_url(flag_key: string): string {
    const rtnval = FLAGS_PATH + "/" + encodeURIComponent(flag_key)
    return rtnval
}

/**
 * Classify a flag-state value into a coarse badge tone.
 *
 * @param state The flag-state string.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function flag_state_tone(state: string | null): string {
    if (typeof state !== "string") {
        const rtnval = "neutral"
        return rtnval
    }
    const lowered = state.toLowerCase()
    if (lowered === FLAG_STATE_ENABLED) {
        const rtnval = "ok"
        return rtnval
    }
    if (lowered === FLAG_STATE_DISABLED) {
        const rtnval = "neutral"
        return rtnval
    }
    if (lowered === FLAG_STATE_RETIRED) {
        const rtnval = "error"
        return rtnval
    }
    const rtnval = "warn"
    return rtnval
}

/**
 * Resolve the next state a toggle should move a flag into. An
 * ``enabled`` flag toggles to ``disabled`` and vice versa; any
 * other state toggles to ``enabled``.
 *
 * @param state The current flag-state string.
 *
 * @returns The target flag-state string.
 */
export function next_flag_state(state: string | null): string {
    if (typeof state === "string" &&
        state.toLowerCase() === FLAG_STATE_ENABLED) {
        const rtnval = FLAG_STATE_DISABLED
        return rtnval
    }
    const rtnval = FLAG_STATE_ENABLED
    return rtnval
}

/**
 * Translate a flag-toggle HTTP status into operator guidance.
 *
 * @param status HTTP status code of the PATCH response.
 *
 * @returns A human-readable message.
 */
export function toggle_message_for_status(status: number): string {
    if (status === 200) {
        const rtnval = "Flag state updated."
        return rtnval
    }
    if (status === 409) {
        const rtnval = "The flag was modified concurrently — refresh."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "The flag-state update was rejected."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to manage flags."
        return rtnval
    }
    const rtnval = "Failed to update flag (HTTP " +
        String(status) + ")."
    return rtnval
}

/**
 * The feature-flags management view Custom Element. Register it
 * with ``customElements.define("pyc-feature-flags",
 * PycFeatureFlags)``.
 */
export class PycFeatureFlags extends HTMLElement {
    private _entries: FeatureFlagEntry[]
    private _loading: boolean
    private _errored: boolean
    private _table_region: HTMLElement | null
    private _status_region: HTMLElement | null

    public constructor() {
        super()
        this._entries = []
        this._loading = false
        this._errored = false
        this._table_region = null
        this._status_region = null
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
     * flags fetch when the element is inserted.
     */
    public connectedCallback(): void {
        this._render_chrome()
        void this._refresh()
        return
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-admin")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-admin__heading")
        heading.textContent = "Feature Flags"
        root.appendChild(heading)

        const lede = document.createElement("p")
        lede.classList.add("pyc-admin__lede")
        lede.textContent =
            "Toggle a flag's state. Retired flags are read-only."
        root.appendChild(lede)

        const controls = document.createElement("div")
        controls.classList.add("pyc-admin__controls")
        const refresh_button = document.createElement("button")
        refresh_button.classList.add("pyc-admin__button")
        refresh_button.setAttribute("type", "button")
        refresh_button.setAttribute("data-role", "refresh")
        refresh_button.textContent = "Refresh"
        refresh_button.addEventListener("click", () => {
            void this._refresh()
        })
        controls.appendChild(refresh_button)
        root.appendChild(controls)

        const status_region = document.createElement("div")
        status_region.setAttribute("data-role", "status-region")
        root.appendChild(status_region)
        this._status_region = status_region

        const table_region = document.createElement("div")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        this.replaceChildren(root)
        return
    }

    /**
     * Fetch the flags list and re-render. Exposed so unit tests
     * can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        this._loading = true
        this._errored = false
        this._render_table()

        let entries: FeatureFlagEntry[] | null = null
        try {
            const response = await fetch(FLAGS_PATH, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "flags fetch failed: HTTP " +
                        String(response.status),
                )
            }
            const body = await response.json()
            if (Array.isArray(body) === true) {
                entries = body as FeatureFlagEntry[]
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.admin.flags_fetch_failed",
                { reason: String(reason) },
            )
        }

        if (entries === null) {
            this._loading = false
            this._errored = true
            this._render_table()
            return
        }

        this._entries = entries
        this._loading = false
        this._errored = false
        this._render_table()
        return
    }

    private _render_table(): void {
        if (this._table_region === null) {
            return
        }
        const region = this._table_region

        if (this._loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-admin__notice")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading feature flags…"
            region.replaceChildren(loading)
            return
        }

        if (this._errored === true) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-admin__notice", "pyc-admin__notice--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent =
                "Failed to load feature flags. Try refreshing."
            region.replaceChildren(error)
            return
        }

        if (this._entries.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-admin__notice")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No feature flags registered."
            region.replaceChildren(empty)
            return
        }

        const table = document.createElement("table")
        table.classList.add("pyc-admin__table")

        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Flag Key", "Kind", "Version", "State", "Actions",
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
            (left: FeatureFlagEntry, right: FeatureFlagEntry): number => {
                if (left.flag_key < right.flag_key) {
                    return -1
                }
                if (left.flag_key > right.flag_key) {
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
        region.replaceChildren(table)
        return
    }

    private _build_row(entry: FeatureFlagEntry): HTMLTableRowElement {
        const row = document.createElement("tr")
        row.setAttribute("data-flag-key", entry.flag_key)

        const key_cell = document.createElement("td")
        key_cell.textContent = entry.flag_key
        row.appendChild(key_cell)

        const kind_cell = document.createElement("td")
        kind_cell.textContent = entry.flag_kind ?? "—"
        row.appendChild(kind_cell)

        const version_cell = document.createElement("td")
        version_cell.textContent = String(entry.current_version)
        row.appendChild(version_cell)

        const state_cell = document.createElement("td")
        const state_badge = document.createElement("span")
        state_badge.classList.add("pyc-admin__badge")
        state_badge.setAttribute("data-tone", flag_state_tone(entry.state))
        state_badge.textContent = entry.state ?? "—"
        state_cell.appendChild(state_badge)
        row.appendChild(state_cell)

        const actions_cell = document.createElement("td")
        const is_retired = typeof entry.state === "string" &&
            entry.state.toLowerCase() === FLAG_STATE_RETIRED
        const toggle = document.createElement("button")
        toggle.classList.add("pyc-admin__toggle")
        toggle.setAttribute("type", "button")
        toggle.setAttribute("data-role", "toggle")
        const target = next_flag_state(entry.state)
        toggle.textContent = target === FLAG_STATE_ENABLED
            ? "Enable"
            : "Disable"
        if (is_retired === true) {
            toggle.disabled = true
        }
        toggle.addEventListener("click", () => {
            toggle.disabled = true
            void this._on_toggle(entry, toggle)
        })
        actions_cell.appendChild(toggle)
        row.appendChild(actions_cell)
        return row
    }

    private async _on_toggle(
        entry: FeatureFlagEntry,
        toggle: HTMLButtonElement,
    ): Promise<void> {
        const target = next_flag_state(entry.state)
        const outcome = await this.toggleFlag(entry.flag_key, target)
        toggle.disabled = false
        this._show_status(
            outcome.message, outcome.ok === true ? "ok" : "error",
        )
        if (outcome.ok === true) {
            await this._refresh()
        }
        return
    }

    /**
     * PATCH a flag's state. Exposed so unit tests can invoke a
     * toggle without a real click event.
     *
     * @param flag_key The flag to update.
     * @param target_state The desired flag-state value.
     *
     * @returns The toggle outcome.
     */
    public async toggleFlag(
        flag_key: string,
        target_state: string,
    ): Promise<FlagToggleOutcome> {
        const payload: Record<string, unknown> = { state: target_state }
        let status = 0
        try {
            const response = await fetch(build_flag_url(flag_key), {
                method: "PATCH",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            })
            status = response.status
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.admin.flag_toggle_failed",
                { reason: String(reason) },
            )
            const rtnval: FlagToggleOutcome = {
                ok: false,
                status: 0,
                flagKey: flag_key,
                message: "Failed to reach the feature-flags service.",
            }
            return rtnval
        }
        const ok = status === 200
        const rtnval: FlagToggleOutcome = {
            ok: ok,
            status: status,
            flagKey: flag_key,
            message: toggle_message_for_status(status),
        }
        return rtnval
    }

    private _show_status(message: string, tone: string): void {
        if (this._status_region === null) {
            return
        }
        const notice = document.createElement("p")
        notice.classList.add("pyc-admin__notice")
        if (tone === "error") {
            notice.classList.add("pyc-admin__notice--error")
        }
        notice.setAttribute("data-role", "toggle-status")
        notice.textContent = message
        this._status_region.replaceChildren(notice)
        return
    }
}
