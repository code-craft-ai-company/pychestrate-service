const DEFAULT_METRICS_ENDPOINT = "/api/v1/_metrics/ui";
const DEFAULT_BUFFER_CAPACITY = 100;
const DEFAULT_FLUSH_WINDOW_MS = 3e4;
class MetricsBeacon {
  _endpoint;
  _buffer_capacity;
  _flush_window_ms;
  _now;
  _send_beacon;
  _buffer;
  _disabled_reason;
  _pagehide_handler;
  constructor(options = null) {
    const opts = options !== null ? options : {};
    this._endpoint = typeof opts.endpoint === "string" && opts.endpoint.length > 0 ? opts.endpoint : DEFAULT_METRICS_ENDPOINT;
    this._buffer_capacity = typeof opts.bufferCapacity === "number" && opts.bufferCapacity > 0 ? opts.bufferCapacity : DEFAULT_BUFFER_CAPACITY;
    this._flush_window_ms = typeof opts.flushWindowMs === "number" && opts.flushWindowMs > 0 ? opts.flushWindowMs : DEFAULT_FLUSH_WINDOW_MS;
    this._now = typeof opts.now === "function" ? opts.now : () => {
      if (typeof performance !== "undefined") {
        return performance.now();
      }
      return Date.now();
    };
    const provided_sender = opts.sendBeacon;
    if (typeof provided_sender === "function") {
      this._send_beacon = provided_sender;
    } else if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      const bound = (url, body) => {
        const result = navigator.sendBeacon(url, body);
        return result;
      };
      this._send_beacon = bound;
    } else {
      this._send_beacon = null;
    }
    this._buffer = [];
    this._disabled_reason = null;
    this._pagehide_handler = null;
  }
  /**
   * Wire ``pagehide`` so the buffer is flushed when the user
   * navigates away. Optional -- the shell calls this once after
   * construction. Returns a detach handle.
   */
  attachLifecycle() {
    if (typeof window === "undefined") {
      const noop = () => {
        return;
      };
      return noop;
    }
    const handler = () => {
      this.flush();
    };
    window.addEventListener("pagehide", handler);
    this._pagehide_handler = handler;
    const detach = () => {
      if (this._pagehide_handler !== null) {
        window.removeEventListener("pagehide", this._pagehide_handler);
        this._pagehide_handler = null;
      }
    };
    return detach;
  }
  /**
   * Record a histogram observation (seconds).
   *
   * @param metric Metric name (must match the design.md catalog).
   * @param seconds Observation value in seconds.
   * @param labels Optional label dictionary; values must be
   *               strings. Pass ``null`` for unlabeled metrics.
   */
  observeHistogram(metric, seconds, labels = null) {
    if (this._disabled_reason !== null) {
      return;
    }
    if (typeof metric !== "string" || metric.length === 0) {
      return;
    }
    if (typeof seconds !== "number" || Number.isFinite(seconds) === false) {
      return;
    }
    const entry = {
      metric,
      value: seconds,
      labels: labels !== null ? labels : null,
      timestamp_ms: Date.now()
    };
    this._buffer.push(entry);
    this._maybe_flush();
    return;
  }
  /**
   * Increment a counter metric by 1 (or the supplied amount).
   */
  incrementCounter(metric, labels = null, amount = 1) {
    if (this._disabled_reason !== null) {
      return;
    }
    if (typeof metric !== "string" || metric.length === 0) {
      return;
    }
    const value = typeof amount === "number" && Number.isFinite(amount) === true ? amount : 1;
    const entry = {
      metric,
      value,
      labels: labels !== null ? labels : null,
      timestamp_ms: Date.now()
    };
    this._buffer.push(entry);
    this._maybe_flush();
    return;
  }
  /**
   * Flush the current buffer to the backend. Drops the buffer
   * after the call regardless of delivery outcome -- there is
   * no retry queue.
   */
  flush() {
    if (this._buffer.length === 0) {
      return;
    }
    const batch = this._buffer;
    this._buffer = [];
    if (this._send_beacon === null) {
      return;
    }
    const payload = JSON.stringify(batch);
    try {
      const delivered = this._send_beacon(this._endpoint, payload);
      if (delivered === false) {
        this._disabled_reason = "sendBeacon_refused";
        console.warn(
          "pychestrate.ui.shell.metrics_beacon_disabled",
          { reason: this._disabled_reason }
        );
      }
    } catch (reason) {
      this._disabled_reason = "sendBeacon_threw";
      console.warn(
        "pychestrate.ui.shell.metrics_beacon_disabled",
        { reason: String(reason) }
      );
    }
    return;
  }
  /**
   * Permanently disable this beacon (e.g. after a 404 on the
   * endpoint) and drop any buffered entries.
   */
  disable(reason) {
    this._disabled_reason = reason;
    this._buffer = [];
    return;
  }
  /**
   * Diagnostic accessor for tests.
   */
  bufferLength() {
    const rtnval = this._buffer.length;
    return rtnval;
  }
  /**
   * Diagnostic accessor for tests.
   */
  get disabledReason() {
    const rtnval = this._disabled_reason;
    return rtnval;
  }
  _maybe_flush() {
    if (this._buffer.length >= this._buffer_capacity) {
      this.flush();
      return;
    }
    if (this._buffer.length > 0) {
      const oldest = this._buffer[0];
      const age_ms = Date.now() - oldest.timestamp_ms;
      if (age_ms >= this._flush_window_ms) {
        this.flush();
        return;
      }
    }
    return;
  }
}
const SHELL_METRICS = {
  TTI: "pychestrate_ui_shell_tti_seconds",
  SIDEBAR_RENDER: "pychestrate_ui_shell_sidebar_render_duration_seconds",
  PERMISSION_REFETCH: "pychestrate_ui_shell_navigation_permission_refetch_seconds",
  PALETTE_OPEN: "pychestrate_ui_shell_palette_open_duration_seconds",
  PALETTE_FANOUT: "pychestrate_ui_shell_palette_fanout_duration_seconds",
  SIDEBAR_ENTRY_CLICKED: "pychestrate_ui_shell_sidebar_entry_clicked_total"
};
export {
  DEFAULT_BUFFER_CAPACITY,
  DEFAULT_FLUSH_WINDOW_MS,
  DEFAULT_METRICS_ENDPOINT,
  MetricsBeacon,
  SHELL_METRICS
};
