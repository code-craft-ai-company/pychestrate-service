/**
 * ``<pyc-timeseries-explorer>`` -- the metric timeseries explorer
 * view Custom Element.
 *
 * On mount the element fetches the metric catalog via
 * ``GET /api/v1/metrics/catalog`` and populates a metric picker.
 * On a metric selection (plus an optional time-range control) it
 * fetches ``GET /api/v1/metrics/timeseries`` and renders the
 * returned points as a lightweight inline-SVG line / area chart --
 * no charting library.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"`` so the cookie session authenticates the request.
 * It never writes to ``localStorage`` / ``sessionStorage``; all
 * state lives in instance fields.
 */

/**
 * SVG namespace for inline-SVG element creation.
 */
const SVG_NS: string = "http://www.w3.org/2000/svg"

/**
 * Base path of the metrics REST surface.
 */
const METRICS_API_PATH: string = "/api/v1/metrics"

/**
 * Plot-area geometry of the timeseries chart, in SVG user units.
 */
const CHART_WIDTH: number = 720
const CHART_HEIGHT: number = 240
const CHART_PADDING: number = 16

/**
 * One registered metric catalog entry -- a subset of
 * ``MetricCatalogEntry``.
 */
export interface MetricCatalogEntry {
    name: string
    kind: string
    label_names: string[]
    help_text?: string
    cardinality_max?: number
}

/**
 * One timestamped metric data point -- a subset of
 * ``TimeseriesPoint``.
 */
export interface TimeseriesPoint {
    observed_at: string
    value: number
    labels?: Record<string, string>
    label_signature?: string
}

/**
 * The ``TimeseriesQuery`` response shape -- a subset.
 */
export interface TimeseriesQuery {
    metric: string
    kind?: string
    from?: string | null
    to?: string | null
    points: TimeseriesPoint[]
}

/**
 * A supported time-range preset for the explorer's range control.
 */
export interface TimeRangePreset {
    id: string
    label: string
    hours: number
}

/**
 * The time-range presets the explorer offers. ``hours`` of 0 means
 * "all" -- no ``from`` bound is sent.
 */
export const TIME_RANGE_PRESETS: readonly TimeRangePreset[] = [
    { id: "1h", label: "Last hour", hours: 1 },
    { id: "24h", label: "Last 24 hours", hours: 24 },
    { id: "7d", label: "Last 7 days", hours: 168 },
    { id: "30d", label: "Last 30 days", hours: 720 },
    { id: "all", label: "All time", hours: 0 },
]

/**
 * The current selection + load state of the timeseries explorer.
 */
export interface TimeseriesState {
    metric: string
    rangeId: string
    loading: boolean
    errored: boolean
}

/**
 * Resolve a time-range preset by id, falling back to the first
 * preset when the id is unknown.
 *
 * @param range_id A preset id.
 *
 * @returns The matching preset.
 */
export function resolve_range_preset(range_id: string): TimeRangePreset {
    for (const preset of TIME_RANGE_PRESETS) {
        if (preset.id === range_id) {
            const rtnval = preset
            return rtnval
        }
    }
    const rtnval = TIME_RANGE_PRESETS[0]
    return rtnval
}

/**
 * Build the ``GET /api/v1/metrics/timeseries`` query URL for the
 * supplied metric and time-range preset. The ``from`` bound is
 * computed relative to ``now`` so callers can pin the test clock.
 *
 * @param metric The metric name to query.
 * @param range_id A time-range preset id.
 * @param now The current time used to compute the ``from`` bound.
 *
 * @returns A relative URL string including the query string.
 */
export function build_timeseries_url(
    metric: string,
    range_id: string,
    now: Date,
): string {
    const params = new URLSearchParams()
    params.set("metric", metric)
    const preset = resolve_range_preset(range_id)
    if (preset.hours > 0) {
        const from_millis = now.getTime() - preset.hours * 3600 * 1000
        const from_date = new Date(from_millis)
        params.set("from", from_date.toISOString())
        params.set("to", now.toISOString())
    }
    const query = params.toString()
    const rtnval = METRICS_API_PATH + "/timeseries?" + query
    return rtnval
}

/**
 * Build the ``GET /api/v1/metrics/catalog`` URL.
 *
 * @returns A relative URL string.
 */
export function build_catalog_url(): string {
    const rtnval = METRICS_API_PATH + "/catalog"
    return rtnval
}

/**
 * One projected chart coordinate in SVG user units.
 */
export interface ChartCoordinate {
    x: number
    y: number
}

/**
 * Project a list of timeseries points into SVG plot-area
 * coordinates. Points are sorted oldest-first on the x axis; the
 * value range is mapped so the minimum value sits at the chart
 * floor and the maximum at the chart ceiling. A single point is
 * pinned to the horizontal centre; an empty input yields an empty
 * list. This is a pure helper -- unit-tested directly.
 *
 * @param points The timeseries points (any order).
 *
 * @returns A list of projected coordinates, oldest-first.
 */
export function project_points(
    points: TimeseriesPoint[],
): ChartCoordinate[] {
    const rtnval: ChartCoordinate[] = []
    if (Array.isArray(points) === false || points.length === 0) {
        return rtnval
    }

    const sorted = points.slice().sort((left, right) => {
        const left_time = new Date(left.observed_at).getTime()
        const right_time = new Date(right.observed_at).getTime()
        const diff = left_time - right_time
        return diff
    })

    const plot_width = CHART_WIDTH - 2 * CHART_PADDING
    const plot_height = CHART_HEIGHT - 2 * CHART_PADDING

    let min_value = sorted[0].value
    let max_value = sorted[0].value
    for (const point of sorted) {
        if (point.value < min_value) {
            min_value = point.value
        }
        if (point.value > max_value) {
            max_value = point.value
        }
    }
    const value_span = max_value - min_value

    const count = sorted.length
    for (let index = 0; index < count; index = index + 1) {
        const point = sorted[index]
        let x_fraction = 0.5
        if (count > 1) {
            x_fraction = index / (count - 1)
        }
        let y_fraction = 0.5
        if (value_span > 0) {
            y_fraction = (point.value - min_value) / value_span
        }
        const x = CHART_PADDING + x_fraction * plot_width
        // SVG y grows downward -- invert so larger values sit higher.
        const y = CHART_PADDING + (1 - y_fraction) * plot_height
        rtnval.push({ x: x, y: y })
    }
    return rtnval
}

/**
 * Build the SVG ``path`` ``d`` attribute for the line connecting
 * the projected coordinates. Returns an empty string for an empty
 * input. This is a pure helper -- unit-tested directly.
 *
 * @param coordinates Projected chart coordinates, oldest-first.
 *
 * @returns An SVG path data string.
 */
export function build_line_path(
    coordinates: ChartCoordinate[],
): string {
    if (
        Array.isArray(coordinates) === false ||
        coordinates.length === 0
    ) {
        const rtnval = ""
        return rtnval
    }
    const segments: string[] = []
    for (let index = 0; index < coordinates.length; index = index + 1) {
        const coord = coordinates[index]
        const command = index === 0 ? "M" : "L"
        const x_text = coord.x.toFixed(2)
        const y_text = coord.y.toFixed(2)
        segments.push(command + " " + x_text + " " + y_text)
    }
    const rtnval = segments.join(" ")
    return rtnval
}

/**
 * Build the SVG ``path`` ``d`` attribute for the filled area under
 * the line -- the line path closed down to the chart floor. Returns
 * an empty string for an empty input.
 *
 * @param coordinates Projected chart coordinates, oldest-first.
 *
 * @returns An SVG path data string for the area fill.
 */
export function build_area_path(
    coordinates: ChartCoordinate[],
): string {
    if (
        Array.isArray(coordinates) === false ||
        coordinates.length === 0
    ) {
        const rtnval = ""
        return rtnval
    }
    const floor_y = CHART_HEIGHT - CHART_PADDING
    const first = coordinates[0]
    const last = coordinates[coordinates.length - 1]
    const line = build_line_path(coordinates)
    const close =
        " L " + last.x.toFixed(2) + " " + floor_y.toFixed(2) +
        " L " + first.x.toFixed(2) + " " + floor_y.toFixed(2) + " Z"
    const rtnval = line + close
    return rtnval
}

/**
 * The timeseries explorer view Custom Element. Register it with
 * ``customElements.define("pyc-timeseries-explorer", ...)``.
 */
export class PycTimeseriesExplorer extends HTMLElement {
    private _state: TimeseriesState
    private _catalog: MetricCatalogEntry[]
    private _query: TimeseriesQuery | null
    private _root: HTMLElement | null
    private _chart_region: HTMLElement | null

    public constructor() {
        super()
        this._state = {
            metric: "",
            rangeId: "24h",
            loading: false,
            errored: false,
        }
        this._catalog = []
        this._query = null
        this._root = null
        this._chart_region = null
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the
     * selection + load state without scraping the DOM.
     */
    public get viewState(): TimeseriesState {
        const rtnval = {
            metric: this._state.metric,
            rangeId: this._state.rangeId,
            loading: this._state.loading,
            errored: this._state.errored,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- render the static chrome and kick off the
     * catalog fetch when the element is inserted.
     */
    public connectedCallback(): void {
        this._render_chrome()
        void this._load_catalog()
        return
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-metrics")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-metrics__heading")
        heading.textContent = "Timeseries Explorer"
        root.appendChild(heading)

        const controls = document.createElement("div")
        controls.classList.add("pyc-metrics__controls")

        const metric_label = document.createElement("label")
        metric_label.classList.add("pyc-metrics__field")
        metric_label.textContent = "Metric"
        const metric_select = document.createElement("select")
        metric_select.classList.add("pyc-metrics__select")
        metric_select.setAttribute("data-role", "metric-select")
        metric_select.addEventListener("change", () => {
            this._state.metric = metric_select.value
            void this._refresh()
        })
        metric_label.appendChild(metric_select)
        controls.appendChild(metric_label)

        const range_label = document.createElement("label")
        range_label.classList.add("pyc-metrics__field")
        range_label.textContent = "Range"
        const range_select = document.createElement("select")
        range_select.classList.add("pyc-metrics__select")
        range_select.setAttribute("data-role", "range-select")
        for (const preset of TIME_RANGE_PRESETS) {
            const option = document.createElement("option")
            option.value = preset.id
            option.textContent = preset.label
            range_select.appendChild(option)
        }
        range_select.value = this._state.rangeId
        range_select.addEventListener("change", () => {
            this._state.rangeId = range_select.value
            void this._refresh()
        })
        range_label.appendChild(range_select)
        controls.appendChild(range_label)

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

        const chart_region = document.createElement("div")
        chart_region.classList.add("pyc-metrics__chart-region")
        chart_region.setAttribute("data-role", "chart-region")
        root.appendChild(chart_region)
        this._chart_region = chart_region

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Fetch the metric catalog and populate the metric picker.
     * Exposed so unit tests can await the bootstrap fetch cycle.
     */
    public async loadCatalog(): Promise<void> {
        await this._load_catalog()
        return
    }

    private async _load_catalog(): Promise<void> {
        let catalog: MetricCatalogEntry[] | null = null
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
                "pychestrate.ui.metrics.catalog_fetch_failed",
                { reason: String(reason) },
            )
        }

        if (catalog !== null && catalog.length > 0) {
            this._catalog = catalog
            this._state.metric = catalog[0].name
        } else {
            this._catalog = []
        }
        this._render_metric_control()
        if (this._state.metric.length > 0) {
            await this._refresh()
        } else {
            this._render_chart()
        }
        return
    }

    private _render_metric_control(): void {
        if (this._root === null) {
            return
        }
        const select = this._root.querySelector('[data-role="metric-select"]')
        if (select instanceof HTMLSelectElement === false) {
            return
        }
        const select_el = select as HTMLSelectElement
        select_el.replaceChildren()
        if (this._catalog.length === 0) {
            const option = document.createElement("option")
            option.value = ""
            option.textContent = "No metrics registered"
            select_el.appendChild(option)
            return
        }
        for (const entry of this._catalog) {
            const option = document.createElement("option")
            option.value = entry.name
            const suffix = entry.kind.length > 0 ? " (" + entry.kind + ")" : ""
            option.textContent = entry.name + suffix
            select_el.appendChild(option)
        }
        select_el.value = this._state.metric
        return
    }

    /**
     * Re-fetch the timeseries for the current metric / range and
     * re-render the chart. Exposed so unit tests can await a cycle.
     */
    public async refresh(): Promise<void> {
        await this._refresh()
        return
    }

    private async _refresh(): Promise<void> {
        if (this._state.metric.length === 0) {
            this._render_chart()
            return
        }
        this._state.loading = true
        this._state.errored = false
        this._render_chart()

        let query: TimeseriesQuery | null = null
        let errored = false
        try {
            const url = build_timeseries_url(
                this._state.metric,
                this._state.rangeId,
                new Date(),
            )
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === true) {
                const body = await response.json()
                query = body as TimeseriesQuery
            } else {
                errored = true
            }
        } catch (reason: unknown) {
            errored = true
            console.warn(
                "pychestrate.ui.metrics.timeseries_fetch_failed",
                { reason: String(reason) },
            )
        }

        this._state.loading = false
        this._state.errored = errored
        this._query = query
        this._render_chart()
        return
    }

    private _render_chart(): void {
        if (this._chart_region === null) {
            return
        }
        const region = this._chart_region
        region.replaceChildren()

        if (this._state.metric.length === 0) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.textContent = "No metric selected."
            region.appendChild(notice)
            return
        }
        if (this._state.loading === true) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.textContent = "Loading timeseries…"
            region.appendChild(notice)
            return
        }
        if (this._state.errored === true || this._query === null) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.classList.add("pyc-metrics__notice--error")
            notice.textContent = "Failed to load the timeseries query."
            region.appendChild(notice)
            return
        }

        const points = this._query.points
        if (Array.isArray(points) === false || points.length === 0) {
            const notice = document.createElement("div")
            notice.classList.add("pyc-metrics__notice")
            notice.textContent = "No data points in the selected range."
            region.appendChild(notice)
            return
        }

        const svg = build_chart_svg(points)
        region.appendChild(svg)
        return
    }
}

/**
 * Build the inline-SVG element rendering the supplied timeseries
 * points as a line + filled area. Exposed so unit tests can assert
 * the DOM shape directly.
 *
 * @param points The timeseries points to render.
 *
 * @returns An ``<svg>`` element.
 */
export function build_chart_svg(points: TimeseriesPoint[]): SVGElement {
    const svg = document.createElementNS(SVG_NS, "svg") as SVGElement
    svg.setAttribute(
        "viewBox",
        "0 0 " + String(CHART_WIDTH) + " " + String(CHART_HEIGHT),
    )
    svg.setAttribute("class", "pyc-metrics__chart")
    svg.setAttribute("preserveAspectRatio", "none")
    svg.setAttribute("data-role", "timeseries-chart")

    const coordinates = project_points(points)
    if (coordinates.length === 0) {
        return svg
    }

    const area = document.createElementNS(SVG_NS, "path")
    area.setAttribute("class", "pyc-metrics__chart-area")
    area.setAttribute("d", build_area_path(coordinates))
    svg.appendChild(area)

    const line = document.createElementNS(SVG_NS, "path")
    line.setAttribute("class", "pyc-metrics__chart-line")
    line.setAttribute("d", build_line_path(coordinates))
    svg.appendChild(line)

    return svg
}

/**
 * Normalise a metric-catalog response body into
 * ``MetricCatalogEntry`` records. Accepts both a bare array and a
 * ``{items}`` page envelope.
 *
 * @param body Parsed JSON response body.
 *
 * @returns A list of catalog entries (possibly empty).
 */
export function extract_catalog(body: unknown): MetricCatalogEntry[] {
    let raw: unknown[] = []
    if (Array.isArray(body) === true) {
        raw = body as unknown[]
    } else if (body !== null && typeof body === "object") {
        const items = (body as { items?: unknown }).items
        if (Array.isArray(items) === true) {
            raw = items as unknown[]
        }
    }
    const rtnval: MetricCatalogEntry[] = []
    for (const item of raw) {
        if (item === null || typeof item !== "object") {
            continue
        }
        const record = item as Record<string, unknown>
        const name = record.name
        if (typeof name !== "string" || name.length === 0) {
            continue
        }
        const kind = typeof record.kind === "string" ? record.kind : ""
        let label_names: string[] = []
        if (Array.isArray(record.label_names) === true) {
            label_names = (record.label_names as unknown[]).filter(
                (value) => typeof value === "string",
            ) as string[]
        }
        const entry: MetricCatalogEntry = {
            name: name,
            kind: kind,
            label_names: label_names,
        }
        if (typeof record.help_text === "string") {
            entry.help_text = record.help_text
        }
        rtnval.push(entry)
    }
    return rtnval
}
