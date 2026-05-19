/**
 * Client metrics beacon for `<pyc-site-shell>`.
 *
 * This module buffers measurements and flushes them via
 * `navigator.sendBeacon()` to ``POST /api/v1/_metrics/ui``.
 *
 * The endpoint is informational only at this milestone -- if it
 * responds 404 (e.g. older alpha deploy) the beacon module logs
 * once and degrades to no-op. There is no retry loop.
 *
 * Per design.md / 9-site-shell Observability section, the
 * following metrics are emitted:
 *
 * - ``pychestrate_ui_shell_tti_seconds`` (histogram) -- emitted
 *   once on ``pyc-site-shell-ready``.
 * - ``pychestrate_ui_shell_sidebar_render_duration_seconds``
 *   (histogram) -- per render.
 * - ``pychestrate_ui_shell_navigation_permission_refetch_seconds``
 *   (histogram) -- per refetch.
 * - ``pychestrate_ui_shell_palette_open_duration_seconds``
 *   (histogram) -- keydown to ``palette-opened`` event.
 * - ``pychestrate_ui_shell_palette_fanout_duration_seconds``
 *   (histogram) -- query to all providers settled.
 * - ``pychestrate_ui_shell_sidebar_entry_clicked_total``
 *   (counter) -- per click.
 *
 * Per NFR-2 (security): measurement labels SHALL NOT carry the
 * permission payload. Routes are coarsened (template-style) by
 * the caller when emitting; this module is a transport, not a
 * scrubber.
 */

/**
 * Default endpoint URL the beacon flushes to. Overridable via
 * the module init options.
 */
export const DEFAULT_METRICS_ENDPOINT: string = "/api/v1/_metrics/ui"

/**
 * Buffer threshold -- when the buffered measurement count reaches
 * this value the beacon flushes synchronously.
 */
export const DEFAULT_BUFFER_CAPACITY: number = 100

/**
 * Rolling time window (milliseconds) -- when the oldest buffered
 * measurement exceeds this age the beacon flushes.
 */
export const DEFAULT_FLUSH_WINDOW_MS: number = 30_000

/**
 * Shape of a single buffered measurement. Wire-format equivalent
 * mirrors this 1:1 -- the backend stub validates exactly these
 * keys.
 */
export interface ClientMetric {
    metric: string
    value: number
    labels: Record<string, string> | null
    timestamp_ms: number
}

/**
 * Optional overrides accepted by ``MetricsBeacon`` for tests and
 * embedded deploys.
 */
export interface MetricsBeaconOptions {
    endpoint?: string
    bufferCapacity?: number
    flushWindowMs?: number
    now?: () => number
    sendBeacon?: (url: string, body: string) => boolean
}

/**
 * Buffered client metrics with batched delivery via
 * ``navigator.sendBeacon``. One instance per shell document.
 */
export class MetricsBeacon {
    private readonly _endpoint: string
    private readonly _buffer_capacity: number
    private readonly _flush_window_ms: number
    private readonly _now: () => number
    private readonly _send_beacon:
        | ((url: string, body: string) => boolean)
        | null
    private _buffer: ClientMetric[]
    private _disabled_reason: string | null
    private _pagehide_handler: (() => void) | null

    public constructor(options: MetricsBeaconOptions | null = null) {
        const opts = options !== null ? options : {}
        this._endpoint =
            typeof opts.endpoint === "string" && opts.endpoint.length > 0
                ? opts.endpoint
                : DEFAULT_METRICS_ENDPOINT
        this._buffer_capacity =
            typeof opts.bufferCapacity === "number" &&
            opts.bufferCapacity > 0
                ? opts.bufferCapacity
                : DEFAULT_BUFFER_CAPACITY
        this._flush_window_ms =
            typeof opts.flushWindowMs === "number" && opts.flushWindowMs > 0
                ? opts.flushWindowMs
                : DEFAULT_FLUSH_WINDOW_MS
        this._now =
            typeof opts.now === "function"
                ? opts.now
                : () => {
                      // Performance API is preferred for monotonic
                      // time. Fall back to wall clock under tests.
                      if (typeof performance !== "undefined") {
                          return performance.now()
                      }
                      return Date.now()
                  }
        const provided_sender = opts.sendBeacon
        if (typeof provided_sender === "function") {
            this._send_beacon = provided_sender
        } else if (
            typeof navigator !== "undefined" &&
            typeof navigator.sendBeacon === "function"
        ) {
            const bound: (url: string, body: string) => boolean = (
                url,
                body,
            ) => {
                const result = navigator.sendBeacon(url, body)
                return result
            }
            this._send_beacon = bound
        } else {
            this._send_beacon = null
        }
        this._buffer = []
        this._disabled_reason = null
        this._pagehide_handler = null
    }

    /**
     * Wire ``pagehide`` so the buffer is flushed when the user
     * navigates away. Optional -- the shell calls this once after
     * construction. Returns a detach handle.
     */
    public attachLifecycle(): () => void {
        if (typeof window === "undefined") {
            const noop: () => void = () => {
                return
            }
            return noop
        }
        const handler: () => void = () => {
            this.flush()
        }
        window.addEventListener("pagehide", handler)
        this._pagehide_handler = handler
        const detach: () => void = () => {
            if (this._pagehide_handler !== null) {
                window.removeEventListener("pagehide", this._pagehide_handler)
                this._pagehide_handler = null
            }
        }
        return detach
    }

    /**
     * Record a histogram observation (seconds).
     *
     * @param metric Metric name (must match the design.md catalog).
     * @param seconds Observation value in seconds.
     * @param labels Optional label dictionary; values must be
     *               strings. Pass ``null`` for unlabeled metrics.
     */
    public observeHistogram(
        metric: string,
        seconds: number,
        labels: Record<string, string> | null = null,
    ): void {
        if (this._disabled_reason !== null) {
            return
        }
        if (typeof metric !== "string" || metric.length === 0) {
            return
        }
        if (typeof seconds !== "number" || Number.isFinite(seconds) === false) {
            return
        }
        const entry: ClientMetric = {
            metric,
            value: seconds,
            labels: labels !== null ? labels : null,
            timestamp_ms: Date.now(),
        }
        this._buffer.push(entry)
        this._maybe_flush()
        return
    }

    /**
     * Increment a counter metric by 1 (or the supplied amount).
     */
    public incrementCounter(
        metric: string,
        labels: Record<string, string> | null = null,
        amount: number = 1,
    ): void {
        if (this._disabled_reason !== null) {
            return
        }
        if (typeof metric !== "string" || metric.length === 0) {
            return
        }
        const value =
            typeof amount === "number" && Number.isFinite(amount) === true
                ? amount
                : 1
        const entry: ClientMetric = {
            metric,
            value,
            labels: labels !== null ? labels : null,
            timestamp_ms: Date.now(),
        }
        this._buffer.push(entry)
        this._maybe_flush()
        return
    }

    /**
     * Flush the current buffer to the backend. Drops the buffer
     * after the call regardless of delivery outcome -- there is
     * no retry queue.
     */
    public flush(): void {
        if (this._buffer.length === 0) {
            return
        }
        const batch = this._buffer
        this._buffer = []
        if (this._send_beacon === null) {
            // No transport available (Node test harness). The drop
            // is intentional -- the contract says "best effort".
            return
        }
        const payload = JSON.stringify(batch)
        try {
            const delivered = this._send_beacon(this._endpoint, payload)
            if (delivered === false) {
                // sendBeacon returns false when the body cannot
                // be queued (size cap, browser policy). Disable
                // future flushes -- retrying forever is wasteful
                // and the metrics are best-effort.
                this._disabled_reason = "sendBeacon_refused"
                console.warn(
                    "pychestrate.ui.shell.metrics_beacon_disabled",
                    { reason: this._disabled_reason },
                )
            }
        } catch (reason: unknown) {
            this._disabled_reason = "sendBeacon_threw"
            console.warn(
                "pychestrate.ui.shell.metrics_beacon_disabled",
                { reason: String(reason) },
            )
        }
        return
    }

    /**
     * Permanently disable this beacon (e.g. after a 404 on the
     * endpoint) and drop any buffered entries.
     */
    public disable(reason: string): void {
        this._disabled_reason = reason
        this._buffer = []
        return
    }

    /**
     * Diagnostic accessor for tests.
     */
    public bufferLength(): number {
        const rtnval = this._buffer.length
        return rtnval
    }

    /**
     * Diagnostic accessor for tests.
     */
    public get disabledReason(): string | null {
        const rtnval = this._disabled_reason
        return rtnval
    }

    private _maybe_flush(): void {
        if (this._buffer.length >= this._buffer_capacity) {
            this.flush()
            return
        }
        if (this._buffer.length > 0) {
            const oldest = this._buffer[0]
            const age_ms = Date.now() - oldest.timestamp_ms
            if (age_ms >= this._flush_window_ms) {
                this.flush()
                return
            }
        }
        return
    }
}

/**
 * Catalog of metric names used by the shell. Centralized here so
 * the shell and tests stay in lockstep with design.md.
 */
export const SHELL_METRICS = {
    TTI: "pychestrate_ui_shell_tti_seconds",
    SIDEBAR_RENDER: "pychestrate_ui_shell_sidebar_render_duration_seconds",
    PERMISSION_REFETCH:
        "pychestrate_ui_shell_navigation_permission_refetch_seconds",
    PALETTE_OPEN: "pychestrate_ui_shell_palette_open_duration_seconds",
    PALETTE_FANOUT: "pychestrate_ui_shell_palette_fanout_duration_seconds",
    SIDEBAR_ENTRY_CLICKED: "pychestrate_ui_shell_sidebar_entry_clicked_total",
} as const
