/**
 * ``<pyc-extension-registry>`` -- the extension-registry admin
 * view Custom Element.
 *
 * On mount the element fetches the extension-route manifest via
 * ``GET /api/v1/ext`` -- the operator-facing listing of the REST
 * endpoints the extension host discovered at startup. The manifest
 * is a flat list of routes, each tagged with its contributing
 * ``ext_name``; this view groups the routes by extension and
 * renders one row per loaded extension showing:
 *
 * * the extension name (the host's precedence-ordered identifier),
 * * the count of REST routes it contributes,
 * * the union of capabilities its routes require,
 * * a coarse health badge derived from the manifest entry.
 *
 * Per-route detail is available via an expandable row. The dynamic
 * extension-route mount itself is a server-side follow-up (the
 * manifest reports ``dynamic_mount: "deferred"``); the view
 * surfaces that mount state as the extension-host health signal.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

/**
 * Path of the extension-route manifest REST endpoint.
 */
export const EXT_LISTING_PATH: string = "/api/v1/ext"

/**
 * One extension-contributed route entry from ``GET /api/v1/ext``.
 */
export interface ExtensionRouteEntry {
    ext_name: string
    method: string
    path_suffix: string
    full_path: string
    handler_class: string
    required_permissions: string[]
    required_capabilities: string[]
    description: string
}

/**
 * The ``GET /api/v1/ext`` response body shape.
 */
export interface ExtensionListingResponse {
    items: ExtensionRouteEntry[]
    total: number
    dynamic_mount: string
}

/**
 * One loaded extension, aggregated from its contributed routes.
 */
export interface LoadedExtension {
    extName: string
    precedence: number
    routeCount: number
    capabilities: string[]
    routes: ExtensionRouteEntry[]
}

/**
 * Group a flat extension-route manifest into per-extension
 * summaries. Routes are bucketed by ``ext_name``; the
 * alphabetical order of the bucket keys becomes the precedence
 * index (the host discovers extensions in a stable order and the
 * manifest is sorted by ``ext_name``).
 *
 * @param routes The flat list of extension-route entries.
 *
 * @returns A list of loaded-extension summaries, ordered by
 *          extension name.
 */
export function group_routes_by_extension(
    routes: ExtensionRouteEntry[],
): LoadedExtension[] {
    const buckets: Map<string, ExtensionRouteEntry[]> = new Map()
    for (const route of routes) {
        const existing = buckets.get(route.ext_name)
        if (existing === undefined) {
            buckets.set(route.ext_name, [route])
        } else {
            existing.push(route)
        }
    }

    const ext_names = Array.from(buckets.keys())
    ext_names.sort()

    const summaries: LoadedExtension[] = []
    let precedence = 0
    for (const ext_name of ext_names) {
        const ext_routes = buckets.get(ext_name)
        if (ext_routes === undefined) {
            continue
        }
        const capability_set: Set<string> = new Set()
        for (const route of ext_routes) {
            for (const capability of route.required_capabilities) {
                capability_set.add(capability)
            }
        }
        const capabilities = Array.from(capability_set)
        capabilities.sort()
        summaries.push({
            extName: ext_name,
            precedence: precedence,
            routeCount: ext_routes.length,
            capabilities: capabilities,
            routes: ext_routes,
        })
        precedence = precedence + 1
    }
    const rtnval = summaries
    return rtnval
}

/**
 * Derive a coarse health tone for an extension from the manifest
 * dynamic-mount state. ``mounted`` is healthy; ``deferred`` is a
 * warning (routes discovered but not yet bound); anything else is
 * an error.
 *
 * @param dynamic_mount The manifest ``dynamic_mount`` field.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"``.
 */
export function mount_state_tone(dynamic_mount: string): string {
    if (typeof dynamic_mount !== "string") {
        const rtnval = "error"
        return rtnval
    }
    const lowered = dynamic_mount.toLowerCase()
    if (lowered === "mounted") {
        const rtnval = "ok"
        return rtnval
    }
    if (lowered === "deferred") {
        const rtnval = "warn"
        return rtnval
    }
    const rtnval = "error"
    return rtnval
}

/**
 * The extension-registry admin view Custom Element. Register it
 * with ``customElements.define("pyc-extension-registry",
 * PycExtensionRegistry)``.
 */
export class PycExtensionRegistry extends HTMLElement {
    private _extensions: LoadedExtension[]
    private _mountState: string
    private _loading: boolean
    private _errored: boolean
    private _table_region: HTMLElement | null
    private _detail_region: HTMLElement | null

    public constructor() {
        super()
        this._extensions = []
        this._mountState = ""
        this._loading = false
        this._errored = false
        this._table_region = null
        this._detail_region = null
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
     * manifest fetch when the element is inserted.
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
        heading.textContent = "Extension Registry"
        root.appendChild(heading)

        const lede = document.createElement("p")
        lede.classList.add("pyc-admin__lede")
        lede.textContent =
            "Loaded extensions with precedence, capabilities and " +
            "route-mount health."
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

        const table_region = document.createElement("div")
        table_region.setAttribute("data-role", "table-region")
        root.appendChild(table_region)
        this._table_region = table_region

        const detail_region = document.createElement("div")
        detail_region.setAttribute("data-role", "detail-region")
        root.appendChild(detail_region)
        this._detail_region = detail_region

        this.replaceChildren(root)
        return
    }

    /**
     * Fetch the extension manifest and re-render. Exposed so unit
     * tests can await a fetch cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        this._loading = true
        this._errored = false
        this._render_table()

        let listing: ExtensionListingResponse | null = null
        try {
            const response = await fetch(EXT_LISTING_PATH, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "ext manifest fetch failed: HTTP " +
                        String(response.status),
                )
            }
            const body = await response.json()
            const parsed = body as ExtensionListingResponse
            if (parsed !== null && Array.isArray(parsed.items) === true) {
                listing = parsed
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.admin.ext_manifest_fetch_failed",
                { reason: String(reason) },
            )
        }

        if (listing === null) {
            this._loading = false
            this._errored = true
            this._render_table()
            return
        }

        this._extensions = group_routes_by_extension(listing.items)
        this._mountState = listing.dynamic_mount
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
            loading.textContent = "Loading extension registry…"
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
                "Failed to load the extension registry. Try refreshing."
            region.replaceChildren(error)
            return
        }

        if (this._extensions.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-admin__notice")
            empty.setAttribute("data-role", "empty-state")
            empty.textContent = "No extensions contribute REST routes."
            region.replaceChildren(empty)
            return
        }

        const table = document.createElement("table")
        table.classList.add("pyc-admin__table")
        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        const columns = [
            "Precedence", "Extension", "Routes", "Capabilities",
            "Health", "Actions",
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
        for (const extension of this._extensions) {
            tbody.appendChild(this._build_row(extension))
        }
        table.appendChild(tbody)
        region.replaceChildren(table)
        return
    }

    private _build_row(extension: LoadedExtension): HTMLTableRowElement {
        const row = document.createElement("tr")
        row.setAttribute("data-ext-name", extension.extName)

        const precedence_cell = document.createElement("td")
        precedence_cell.textContent = String(extension.precedence)
        row.appendChild(precedence_cell)

        const name_cell = document.createElement("td")
        name_cell.textContent = extension.extName
        row.appendChild(name_cell)

        const routes_cell = document.createElement("td")
        routes_cell.textContent = String(extension.routeCount)
        row.appendChild(routes_cell)

        const capabilities_cell = document.createElement("td")
        if (extension.capabilities.length === 0) {
            capabilities_cell.textContent = "—"
        } else {
            capabilities_cell.textContent =
                extension.capabilities.join(", ")
        }
        row.appendChild(capabilities_cell)

        const health_cell = document.createElement("td")
        const health_badge = document.createElement("span")
        health_badge.classList.add("pyc-admin__badge")
        health_badge.setAttribute(
            "data-tone", mount_state_tone(this._mountState),
        )
        health_badge.textContent = this._mountState.length > 0
            ? this._mountState
            : "unknown"
        health_cell.appendChild(health_badge)
        row.appendChild(health_cell)

        const actions_cell = document.createElement("td")
        const detail_button = document.createElement("button")
        detail_button.classList.add("pyc-admin__toggle")
        detail_button.setAttribute("type", "button")
        detail_button.setAttribute("data-role", "show-routes")
        detail_button.textContent = "Show Routes"
        detail_button.addEventListener("click", () => {
            this._render_detail(extension)
        })
        actions_cell.appendChild(detail_button)
        row.appendChild(actions_cell)
        return row
    }

    private _render_detail(extension: LoadedExtension): void {
        if (this._detail_region === null) {
            return
        }
        const region = this._detail_region

        const heading = document.createElement("h2")
        heading.classList.add("pyc-admin__subheading")
        heading.textContent = "Routes — " + extension.extName

        const mount_note = document.createElement("p")
        mount_note.classList.add("pyc-admin__lede")
        mount_note.textContent =
            "Dynamic-mount state: " +
            (this._mountState.length > 0 ? this._mountState : "unknown")

        const table = document.createElement("table")
        table.classList.add("pyc-admin__table")
        table.setAttribute("data-role", "route-detail")
        const thead = document.createElement("thead")
        const head_row = document.createElement("tr")
        for (const column of ["Method", "Path", "Permissions", "Handler"]) {
            const th = document.createElement("th")
            th.scope = "col"
            th.textContent = column
            head_row.appendChild(th)
        }
        thead.appendChild(head_row)
        table.appendChild(thead)
        const tbody = document.createElement("tbody")
        for (const route of extension.routes) {
            const route_row = document.createElement("tr")
            const method_cell = document.createElement("td")
            method_cell.textContent = route.method
            route_row.appendChild(method_cell)
            const path_cell = document.createElement("td")
            path_cell.classList.add("pyc-admin__mono")
            path_cell.textContent = route.full_path
            route_row.appendChild(path_cell)
            const perms_cell = document.createElement("td")
            perms_cell.textContent = route.required_permissions.length > 0
                ? route.required_permissions.join(", ")
                : "—"
            route_row.appendChild(perms_cell)
            const handler_cell = document.createElement("td")
            handler_cell.classList.add("pyc-admin__mono")
            handler_cell.textContent = route.handler_class
            route_row.appendChild(handler_cell)
            tbody.appendChild(route_row)
        }
        table.appendChild(tbody)
        region.replaceChildren(heading, mount_note, table)
        return
    }
}
