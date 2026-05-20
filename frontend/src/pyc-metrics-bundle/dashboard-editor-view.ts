/**
 * ``<pyc-dashboard-editor>`` -- the dashboard-layout editor view
 * Custom Element.
 *
 * Mounted on ``/dashboards/{dashboard_id}/edit``. The view reads
 * the dashboard via ``GET …/dashboards/{dashboard_id}``, renders
 * its tiles in a simple column grid, and lets the operator:
 *
 * * Add a tile -- pick a metric (from
 *   ``GET /api/v1/metrics/catalog``) and a tile kind
 *   (line / bar / number).
 * * Remove a tile.
 * * Reorder tiles with per-tile up / down buttons (no drag-drop
 *   library -- the reorder helpers are pure).
 *
 * The metric / dashboards REST surface (PR p20f) exposes only
 * ``GET`` (list / read) and ``POST`` (create) for dashboards --
 * there is **no** ``PATCH`` / ``PUT`` to update an existing
 * dashboard. The editor therefore saves a layout with a
 * **create-replace**: it POSTs a new dashboard carrying the full,
 * edited tile set. The new dashboard takes a distinct id; the
 * editor surfaces the new id and links to it. This is flagged in
 * the save notice so the operator understands a new dashboard was
 * created rather than the original mutated.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
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
import {
    Dashboard,
    DashboardTile,
    build_dashboard_detail_url,
    build_dashboards_collection_url,
    DASHBOARDS_ROUTE,
} from "./dashboards-view.js"

/**
 * Base path of the projects REST collection.
 */
const PROJECTS_API_PATH: string = "/api/v1/projects"

/**
 * The tile kinds the layout editor offers. Each entry carries the
 * wire value the tile ``kind`` field records and a short label.
 */
export interface TileKindOption {
    value: string
    label: string
}

/**
 * The tile kinds a layout editor supports.
 */
export const TILE_KIND_OPTIONS: readonly TileKindOption[] = [
    { value: "line", label: "Line chart" },
    { value: "bar", label: "Bar chart" },
    { value: "number", label: "Single number" },
]

/**
 * Outcome of a save-layout POST, surfaced to callers / tests.
 */
export interface DashboardSaveOutcome {
    ok: boolean
    status: number
    dashboardId: string
    message: string
}

/**
 * Extract a ``{dashboard_id}`` from a
 * ``/dashboards/{id}/edit`` path. Returns an empty string when the
 * path is not a dashboard-edit path. Tolerates an optional query
 * string.
 *
 * @param path A request path.
 *
 * @returns The dashboard id, or an empty string.
 */
export function dashboard_id_from_edit_path(path: string): string {
    if (typeof path !== "string") {
        const rtnval = ""
        return rtnval
    }
    let working = path
    const query_index = working.indexOf("?")
    if (query_index >= 0) {
        working = working.slice(0, query_index)
    }
    const prefix = DASHBOARDS_ROUTE + "/"
    const suffix = "/edit"
    if (working.startsWith(prefix) === false) {
        const rtnval = ""
        return rtnval
    }
    if (working.endsWith(suffix) === false) {
        const rtnval = ""
        return rtnval
    }
    const middle = working.slice(prefix.length, working.length - suffix.length)
    if (middle.length === 0 || middle.indexOf("/") >= 0) {
        const rtnval = ""
        return rtnval
    }
    const rtnval = decodeURIComponent(middle)
    return rtnval
}

/**
 * Test whether a path is a dashboard-edit path.
 *
 * @param path A request path.
 *
 * @returns ``true`` when ``path`` is a ``/dashboards/{id}/edit``
 *          path.
 */
export function is_dashboard_edit_path(path: string): boolean {
    const rtnval = dashboard_id_from_edit_path(path).length > 0
    return rtnval
}

/**
 * Generate a fresh tile id. The id is a timestamp-seeded random
 * token -- the server treats tile ids as opaque, unique-per-
 * dashboard strings.
 *
 * @returns A new tile id string.
 */
export function generate_tile_id(): string {
    const stamp = Date.now().toString(36)
    const rand = Math.floor(Math.random() * 1000000).toString(36)
    const rtnval = "tile-" + stamp + "-" + rand
    return rtnval
}

/**
 * Build a new tile referencing ``metric`` with the supplied kind.
 * The tile is placed in a single-column stack -- ``x`` is 0 and
 * ``y`` is the index. ``w`` / ``h`` default to a 1x1 cell.
 *
 * @param metric The metric the tile renders.
 * @param kind The tile kind (line / bar / number).
 * @param index The 0-based stack position (the tile's ``y``).
 *
 * @returns A new ``DashboardTile``.
 */
export function build_tile(
    metric: string,
    kind: string,
    index: number,
): DashboardTile {
    const rtnval: DashboardTile = {
        tile_id: generate_tile_id(),
        kind: kind,
        x: 0,
        y: index,
        w: 1,
        h: 1,
        config: { metric: metric },
    }
    return rtnval
}

/**
 * Append a tile to a tile list, returning a new list. The source
 * list is not mutated. The new tile's ``y`` is the appended
 * index.
 *
 * @param tiles The current tile list.
 * @param metric The metric the new tile renders.
 * @param kind The new tile's kind.
 *
 * @returns A new tile list with the tile appended.
 */
export function add_tile(
    tiles: readonly DashboardTile[],
    metric: string,
    kind: string,
): DashboardTile[] {
    const rtnval: DashboardTile[] = tiles.slice()
    rtnval.push(build_tile(metric, kind, rtnval.length))
    return reindex_tiles(rtnval)
}

/**
 * Remove the tile with ``tile_id`` from a tile list, returning a
 * new, re-indexed list. A no-op (returns a copy) when the id is
 * not present.
 *
 * @param tiles The current tile list.
 * @param tile_id The tile to remove.
 *
 * @returns A new tile list without the named tile.
 */
export function remove_tile(
    tiles: readonly DashboardTile[],
    tile_id: string,
): DashboardTile[] {
    const filtered: DashboardTile[] = []
    for (const tile of tiles) {
        if (tile.tile_id !== tile_id) {
            filtered.push(tile)
        }
    }
    const rtnval = reindex_tiles(filtered)
    return rtnval
}

/**
 * Move the tile at ``index`` one slot earlier in the list. A
 * no-op (returns a copy) when ``index`` is the first slot or out
 * of range.
 *
 * @param tiles The current tile list.
 * @param index The 0-based index of the tile to move up.
 *
 * @returns A new, re-indexed tile list.
 */
export function move_tile_up(
    tiles: readonly DashboardTile[],
    index: number,
): DashboardTile[] {
    const working: DashboardTile[] = tiles.slice()
    if (index <= 0 || index >= working.length) {
        const rtnval = reindex_tiles(working)
        return rtnval
    }
    const above = working[index - 1]
    const current = working[index]
    working[index - 1] = current
    working[index] = above
    const rtnval = reindex_tiles(working)
    return rtnval
}

/**
 * Move the tile at ``index`` one slot later in the list. A no-op
 * (returns a copy) when ``index`` is the last slot or out of
 * range.
 *
 * @param tiles The current tile list.
 * @param index The 0-based index of the tile to move down.
 *
 * @returns A new, re-indexed tile list.
 */
export function move_tile_down(
    tiles: readonly DashboardTile[],
    index: number,
): DashboardTile[] {
    const working: DashboardTile[] = tiles.slice()
    if (index < 0 || index >= working.length - 1) {
        const rtnval = reindex_tiles(working)
        return rtnval
    }
    const below = working[index + 1]
    const current = working[index]
    working[index + 1] = current
    working[index] = below
    const rtnval = reindex_tiles(working)
    return rtnval
}

/**
 * Re-stamp each tile's ``y`` to its list index so the placement
 * matches the visual stack order. ``x`` is normalised to 0 so the
 * editor produces a single-column layout. The source list is not
 * mutated.
 *
 * @param tiles A tile list.
 *
 * @returns A new tile list with ``x`` / ``y`` re-indexed.
 */
export function reindex_tiles(
    tiles: readonly DashboardTile[],
): DashboardTile[] {
    const rtnval: DashboardTile[] = []
    let index = 0
    for (const tile of tiles) {
        const next: DashboardTile = {
            tile_id: tile.tile_id,
            kind: tile.kind,
            x: 0,
            y: index,
            w: tile.w,
            h: tile.h,
        }
        if (tile.config !== undefined) {
            next.config = tile.config
        }
        rtnval.push(next)
        index = index + 1
    }
    return rtnval
}

/**
 * Resolve the metric name a dashboard tile references.
 *
 * @param tile A dashboard tile.
 *
 * @returns The referenced metric name, or an empty string.
 */
export function editor_tile_metric(tile: DashboardTile): string {
    if (tile === null || tile === undefined) {
        const rtnval = ""
        return rtnval
    }
    const config = tile.config
    if (config === null || config === undefined || typeof config !== "object") {
        const rtnval = ""
        return rtnval
    }
    const metric = (config as Record<string, unknown>).metric
    if (typeof metric !== "string") {
        const rtnval = ""
        return rtnval
    }
    const rtnval = metric
    return rtnval
}

/**
 * Build the create-replace POST payload for a saved layout. The
 * payload re-creates the dashboard with the edited tile set --
 * ``name`` is suffixed so it does not collide with the original
 * (the server rejects a duplicate name with 409).
 *
 * @param dashboard The source dashboard.
 * @param tiles The edited tile list.
 *
 * @returns A JSON-friendly create-dashboard payload.
 */
export function build_save_payload(
    dashboard: Dashboard,
    tiles: readonly DashboardTile[],
): Record<string, unknown> {
    const reindexed = reindex_tiles(tiles)
    const tile_payload: Record<string, unknown>[] = []
    for (const tile of reindexed) {
        const entry: Record<string, unknown> = {
            tile_id: tile.tile_id,
            kind: tile.kind,
            x: tile.x,
            y: tile.y,
            w: tile.w,
            h: tile.h,
            config: tile.config !== undefined ? tile.config : {},
        }
        tile_payload.push(entry)
    }
    const rtnval: Record<string, unknown> = {
        name: dashboard.name + " (edited)",
        tiles: tile_payload,
    }
    if (
        dashboard.description !== undefined &&
        dashboard.description.length > 0
    ) {
        rtnval.description = dashboard.description
    }
    if (typeof dashboard.grid_columns_max === "number") {
        rtnval.grid_columns_max = dashboard.grid_columns_max
    }
    return rtnval
}

/**
 * Translate a save-layout HTTP status into operator guidance.
 *
 * @param status HTTP status code of the create-replace response.
 *
 * @returns A human-readable message.
 */
export function save_message_for_status(status: number): string {
    if (status === 201 || status === 200) {
        const rtnval =
            "Layout saved as a new dashboard (the dashboards API has no " +
            "in-place update)."
        return rtnval
    }
    if (status === 409) {
        const rtnval =
            "A dashboard with the edited name already exists — rename and " +
            "retry."
        return rtnval
    }
    if (status === 422) {
        const rtnval = "The layout was rejected — check the tiles."
        return rtnval
    }
    if (status === 403) {
        const rtnval = "You do not have permission to save dashboards."
        return rtnval
    }
    if (status === 404) {
        const rtnval = "Unknown project."
        return rtnval
    }
    const rtnval = "Failed to save layout (HTTP " + String(status) + ")."
    return rtnval
}

/**
 * The dashboard-layout editor view Custom Element. Register it
 * with ``customElements.define("pyc-dashboard-editor", ...)``.
 */
export class PycDashboardEditor extends HTMLElement {
    private _projects: MetricsProjectOption[]
    private _projectId: string
    private _dashboard: Dashboard | null
    private _tiles: DashboardTile[]
    private _catalog: MetricCatalogEntry[]
    private _loading: boolean
    private _errored: boolean
    private _root: HTMLElement | null
    private _grid_region: HTMLElement | null
    private _add_region: HTMLElement | null
    private _toast_region: HTMLElement | null

    public constructor() {
        super()
        this._projects = []
        this._projectId = ""
        this._dashboard = null
        this._tiles = []
        this._catalog = []
        this._loading = false
        this._errored = false
        this._root = null
        this._grid_region = null
        this._add_region = null
        this._toast_region = null
    }

    /**
     * Diagnostic accessor used by unit tests -- the current tile
     * list (a defensive copy).
     */
    public get tiles(): DashboardTile[] {
        const rtnval = this._tiles.slice()
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests -- ``true`` once the
     * dashboard has loaded.
     */
    public get loaded(): boolean {
        const rtnval = this._dashboard !== null
        return rtnval
    }

    /**
     * Lifecycle hook -- render the chrome, fetch the catalog and
     * the dashboard.
     */
    public connectedCallback(): void {
        this._render_chrome()
        void this._load_catalog()
        void this._load_dashboard()
        return
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-metrics")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-metrics__heading")
        heading.setAttribute("data-role", "editor-heading")
        heading.textContent = "Edit Dashboard Layout"
        root.appendChild(heading)

        const back = document.createElement("a")
        back.classList.add("pyc-metrics__row-link")
        back.setAttribute("data-role", "back-link")
        back.setAttribute("href", DASHBOARDS_ROUTE)
        back.textContent = "← All dashboards"
        root.appendChild(back)

        const add_region = document.createElement("div")
        add_region.classList.add("pyc-metrics__form-region")
        add_region.setAttribute("data-role", "add-region")
        root.appendChild(add_region)
        this._add_region = add_region

        const toast_region = document.createElement("div")
        toast_region.classList.add("pyc-metrics__toast-region")
        toast_region.setAttribute("data-role", "toast-region")
        root.appendChild(toast_region)
        this._toast_region = toast_region

        const grid_region = document.createElement("div")
        grid_region.classList.add("pyc-metrics__tiles-region")
        grid_region.setAttribute("data-role", "grid-region")
        root.appendChild(grid_region)
        this._grid_region = grid_region

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Fetch the metric catalog so the add-tile form can offer a
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
                "pychestrate.ui.metrics.editor_catalog_fetch_failed",
                { reason: String(reason) },
            )
        }
        this._catalog = catalog
        this._render_add_region()
        return
    }

    /**
     * Resolve the dashboard project + id, fetch the dashboard, and
     * render its tiles. Exposed so unit tests can await the cycle.
     */
    public async loadDashboard(): Promise<void> {
        await this._load_dashboard()
        return
    }

    private async _load_dashboard(): Promise<void> {
        const dashboard_id = dashboard_id_from_edit_path(
            typeof window !== "undefined" ? window.location.pathname : "",
        )
        if (dashboard_id.length === 0) {
            this._errored = true
            this._render_grid()
            return
        }

        let project_id = ""
        try {
            const response = await fetch(PROJECTS_API_PATH, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                this._projects = extract_projects(body)
                if (this._projects.length > 0) {
                    project_id = this._projects[0].project_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.editor_projects_fetch_failed",
                { reason: String(reason) },
            )
        }

        if (project_id.length === 0) {
            this._errored = true
            this._render_grid()
            return
        }
        this._projectId = project_id

        this._loading = true
        this._render_grid()

        let dashboard: Dashboard | null = null
        let errored = false
        try {
            const url = build_dashboard_detail_url(project_id, dashboard_id)
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                dashboard = body as Dashboard
            } else {
                errored = true
            }
        } catch (reason: unknown) {
            errored = true
            console.warn(
                "pychestrate.ui.metrics.editor_dashboard_fetch_failed",
                { reason: String(reason) },
            )
        }

        this._loading = false
        this._errored = errored
        this._dashboard = dashboard
        if (dashboard !== null && Array.isArray(dashboard.tiles) === true) {
            this._tiles = reindex_tiles(dashboard.tiles)
        } else {
            this._tiles = []
        }
        this._render_grid()
        this._render_add_region()
        return
    }

    /**
     * Append a tile referencing ``metric`` with ``kind``. Exposed
     * so unit tests can drive the add path directly.
     *
     * @param metric The metric the new tile renders.
     * @param kind The new tile's kind.
     */
    public addTile(metric: string, kind: string): void {
        this._tiles = add_tile(this._tiles, metric, kind)
        this._render_grid()
        return
    }

    /**
     * Remove the named tile. Exposed so unit tests can drive the
     * remove path directly.
     *
     * @param tile_id The tile to remove.
     */
    public removeTile(tile_id: string): void {
        this._tiles = remove_tile(this._tiles, tile_id)
        this._render_grid()
        return
    }

    /**
     * Move the tile at ``index`` one slot earlier. Exposed so unit
     * tests can drive the reorder path directly.
     *
     * @param index The 0-based index of the tile to move up.
     */
    public moveUp(index: number): void {
        this._tiles = move_tile_up(this._tiles, index)
        this._render_grid()
        return
    }

    /**
     * Move the tile at ``index`` one slot later. Exposed so unit
     * tests can drive the reorder path directly.
     *
     * @param index The 0-based index of the tile to move down.
     */
    public moveDown(index: number): void {
        this._tiles = move_tile_down(this._tiles, index)
        this._render_grid()
        return
    }

    private _render_add_region(): void {
        if (this._add_region === null) {
            return
        }
        const region = this._add_region
        region.replaceChildren()

        if (this._dashboard === null) {
            return
        }

        const form = document.createElement("form")
        form.classList.add("pyc-metrics__form")
        form.setAttribute("data-role", "add-tile-form")

        const metric_label = document.createElement("label")
        metric_label.classList.add("pyc-metrics__field")
        metric_label.textContent = "Metric"
        const metric_select = document.createElement("select")
        metric_select.classList.add("pyc-metrics__select")
        metric_select.setAttribute("data-role", "add-metric")
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

        const kind_label = document.createElement("label")
        kind_label.classList.add("pyc-metrics__field")
        kind_label.textContent = "Tile kind"
        const kind_select = document.createElement("select")
        kind_select.classList.add("pyc-metrics__select")
        kind_select.setAttribute("data-role", "add-kind")
        for (const option of TILE_KIND_OPTIONS) {
            const opt = document.createElement("option")
            opt.value = option.value
            opt.textContent = option.label
            kind_select.appendChild(opt)
        }
        kind_label.appendChild(kind_select)
        form.appendChild(kind_label)

        const add_button = document.createElement("button")
        add_button.classList.add("pyc-metrics__button")
        add_button.setAttribute("type", "submit")
        add_button.setAttribute("data-role", "add-tile")
        add_button.textContent = "Add Tile"
        form.appendChild(add_button)

        const save_button = document.createElement("button")
        save_button.classList.add("pyc-metrics__button")
        save_button.setAttribute("type", "button")
        save_button.setAttribute("data-role", "save-layout")
        save_button.textContent = "Save Layout"
        save_button.addEventListener("click", () => {
            save_button.disabled = true
            void this._on_save(save_button)
        })
        form.appendChild(save_button)

        form.addEventListener("submit", (event: Event) => {
            event.preventDefault()
            const metric = metric_select.value.trim()
            if (metric.length === 0) {
                this._show_toast("Select a metric to add a tile.", "error")
                return
            }
            this.addTile(metric, kind_select.value)
        })

        region.appendChild(form)
        return
    }

    private _render_grid(): void {
        if (this._grid_region === null || this._root === null) {
            return
        }
        const heading = this._root.querySelector(
            '[data-role="editor-heading"]',
        )
        if (heading !== null && this._dashboard !== null) {
            heading.textContent = "Edit Layout — " + this._dashboard.name
        }

        const region = this._grid_region
        region.replaceChildren()

        if (this._loading === true) {
            const notice = document.createElement("p")
            notice.classList.add("pyc-metrics__notice")
            notice.setAttribute("data-role", "loading-state")
            notice.textContent = "Loading dashboard…"
            region.appendChild(notice)
            return
        }
        if (this._errored === true || this._dashboard === null) {
            const notice = document.createElement("p")
            notice.classList.add(
                "pyc-metrics__notice",
                "pyc-metrics__notice--error",
            )
            notice.setAttribute("data-role", "error-state")
            notice.textContent = "Failed to load this dashboard."
            region.appendChild(notice)
            return
        }
        if (this._tiles.length === 0) {
            const notice = document.createElement("p")
            notice.classList.add("pyc-metrics__notice")
            notice.setAttribute("data-role", "empty-state")
            notice.textContent = "No tiles yet — add one above."
            region.appendChild(notice)
            return
        }

        const grid = document.createElement("div")
        grid.classList.add("pyc-metrics__tiles")
        grid.setAttribute("data-role", "tiles-grid")
        let index = 0
        for (const tile of this._tiles) {
            grid.appendChild(this._build_tile_card(tile, index))
            index = index + 1
        }
        region.appendChild(grid)
        return
    }

    private _build_tile_card(
        tile: DashboardTile,
        index: number,
    ): HTMLElement {
        const card = document.createElement("div")
        card.classList.add("pyc-metrics__tile")
        card.setAttribute("data-role", "editor-tile")
        card.setAttribute("data-tile-id", tile.tile_id)

        const title = document.createElement("div")
        title.classList.add("pyc-metrics__tile-title")
        const metric = editor_tile_metric(tile)
        title.textContent =
            (metric.length > 0 ? metric : "(no metric)") +
            " · " + tile.kind
        card.appendChild(title)

        const actions = document.createElement("div")
        actions.classList.add("pyc-metrics__tile-actions")

        const up_button = document.createElement("button")
        up_button.classList.add("pyc-metrics__button")
        up_button.setAttribute("type", "button")
        up_button.setAttribute("data-role", "tile-up")
        up_button.setAttribute("aria-label", "Move tile up")
        up_button.textContent = "↑"
        up_button.disabled = index === 0
        up_button.addEventListener("click", () => {
            this.moveUp(index)
        })
        actions.appendChild(up_button)

        const down_button = document.createElement("button")
        down_button.classList.add("pyc-metrics__button")
        down_button.setAttribute("type", "button")
        down_button.setAttribute("data-role", "tile-down")
        down_button.setAttribute("aria-label", "Move tile down")
        down_button.textContent = "↓"
        down_button.disabled = index === this._tiles.length - 1
        down_button.addEventListener("click", () => {
            this.moveDown(index)
        })
        actions.appendChild(down_button)

        const remove_button = document.createElement("button")
        remove_button.classList.add("pyc-metrics__button")
        remove_button.setAttribute("type", "button")
        remove_button.setAttribute("data-role", "tile-remove")
        remove_button.setAttribute("aria-label", "Remove tile")
        remove_button.textContent = "Remove"
        remove_button.addEventListener("click", () => {
            this.removeTile(tile.tile_id)
        })
        actions.appendChild(remove_button)

        card.appendChild(actions)
        return card
    }

    private async _on_save(button: HTMLButtonElement): Promise<void> {
        const outcome = await this._do_save()
        button.disabled = false
        this._show_toast(
            outcome.message,
            outcome.ok === true ? "ok" : "error",
        )
        if (outcome.ok === true && outcome.dashboardId.length > 0) {
            const link = document.createElement("a")
            link.classList.add("pyc-metrics__row-link")
            link.setAttribute(
                "href",
                DASHBOARDS_ROUTE + "/" +
                    encodeURIComponent(outcome.dashboardId),
            )
            link.textContent = "Open the saved dashboard →"
            if (this._toast_region !== null) {
                this._toast_region.appendChild(link)
            }
        }
        return
    }

    /**
     * Save the current layout via a create-replace POST. Exposed
     * so unit tests can drive the save path directly.
     *
     * @returns The save outcome.
     */
    public async saveLayout(): Promise<DashboardSaveOutcome> {
        const rtnval = await this._do_save()
        return rtnval
    }

    private async _do_save(): Promise<DashboardSaveOutcome> {
        if (this._dashboard === null || this._projectId.length === 0) {
            const rtnval: DashboardSaveOutcome = {
                ok: false,
                status: 0,
                dashboardId: "",
                message: "Load a dashboard before saving its layout.",
            }
            return rtnval
        }
        const payload = build_save_payload(this._dashboard, this._tiles)
        let status = 0
        let dashboard_id = ""
        try {
            const url = build_dashboards_collection_url(this._projectId)
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
                const record = body as { dashboard_id?: unknown }
                if (typeof record.dashboard_id === "string") {
                    dashboard_id = record.dashboard_id
                }
            }
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.metrics.dashboard_save_failed",
                { reason: String(reason) },
            )
            const rtnval: DashboardSaveOutcome = {
                ok: false,
                status: 0,
                dashboardId: "",
                message: "Failed to reach the dashboards service.",
            }
            return rtnval
        }
        const ok = status === 201 || status === 200
        const rtnval: DashboardSaveOutcome = {
            ok: ok,
            status: status,
            dashboardId: dashboard_id,
            message: save_message_for_status(status),
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
