import { PermissionSet } from "./permission-set.js";
const DEFAULT_PERMISSIONS_ENDPOINT = "/api/v1/me/permissions";
const DEFAULT_FRESHNESS_TTL_MS = 6e4;
class PermissionCache {
  _current;
  _degraded;
  _endpoint;
  _freshness_ttl_ms;
  _now;
  _last_success_at_ms;
  _diff_listeners;
  _fetch_failed_listeners;
  _session_401_listeners;
  _fetch_succeeded_listeners;
  _last_outcome_was_401;
  /**
   * @param endpoint Either a URL string (back-compat) or an
   *                 options object. When a string is supplied,
   *                 defaults are applied for the other fields.
   */
  constructor(endpoint) {
    let resolved_endpoint = DEFAULT_PERMISSIONS_ENDPOINT;
    let resolved_ttl_ms = DEFAULT_FRESHNESS_TTL_MS;
    let resolved_now = () => Date.now();
    if (typeof endpoint === "string") {
      resolved_endpoint = endpoint;
    } else if (endpoint !== null && typeof endpoint === "object") {
      if (typeof endpoint.endpoint === "string" && endpoint.endpoint.length > 0) {
        resolved_endpoint = endpoint.endpoint;
      }
      if (typeof endpoint.freshnessTtlMs === "number") {
        resolved_ttl_ms = endpoint.freshnessTtlMs;
      }
      if (typeof endpoint.now === "function") {
        resolved_now = endpoint.now;
      }
    }
    this._current = new PermissionSet([]);
    this._degraded = false;
    this._endpoint = resolved_endpoint;
    this._freshness_ttl_ms = resolved_ttl_ms;
    this._now = resolved_now;
    this._last_success_at_ms = null;
    this._diff_listeners = [];
    this._fetch_failed_listeners = [];
    this._session_401_listeners = [];
    this._fetch_succeeded_listeners = [];
    this._last_outcome_was_401 = false;
  }
  /**
   * Return the current snapshot.
   */
  current() {
    const rtnval = this._current;
    return rtnval;
  }
  /**
   * Return true when the most recent fetch failed.
   */
  get degraded() {
    const rtnval = this._degraded;
    return rtnval;
  }
  /**
   * Subscribe to permission-set diffs. Listener fires on every
   * ``refresh()`` whose successful fetch changed the snapshot.
   */
  onPermissionsChanged(listener) {
    this._diff_listeners.push(listener);
    return;
  }
  /**
   * Subscribe to non-401 fetch failures (network errors, 5xx).
   * The degraded banner consumes this hook.
   */
  onFetchFailed(listener) {
    this._fetch_failed_listeners.push(listener);
    return;
  }
  /**
   * Subscribe to successful fetches -- used by the degraded
   * banner to auto-dismiss on recovery.
   */
  onFetchSucceeded(listener) {
    this._fetch_succeeded_listeners.push(listener);
    return;
  }
  /**
   * Subscribe to mid-session 401 events. Fired exactly once per
   * transition from healthy to expired-session.
   */
  onSession401(listener) {
    this._session_401_listeners.push(listener);
    return;
  }
  /**
   * Force a refresh from the server. On success the new
   * `PermissionSet` becomes the current snapshot and `degraded`
   * resets to false. On failure the previous snapshot is
   * retained and `degraded` is set to true. The promise resolves
   * with the current snapshot in both cases -- callers should not
   * branch on this method's success/failure as a security check.
   *
   * When called within the freshness TTL of the previous success
   * AND ``force`` is false, the cached snapshot is returned
   * without a network call.
   *
   * @param force When true, bypass the TTL dedup. Used by the
   *              navigation hook (Requirement 4.1 requires a
   *              refetch on every full navigation).
   */
  async refresh(force = true) {
    if (force === false && this._last_success_at_ms !== null && this._now() - this._last_success_at_ms < this._freshness_ttl_ms) {
      return this._current;
    }
    try {
      const response = await fetch(this._endpoint, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.status === 401) {
        this._degraded = true;
        if (this._last_outcome_was_401 === false) {
          this._last_outcome_was_401 = true;
          for (const listener of this._session_401_listeners) {
            try {
              listener();
            } catch (reason) {
              console.warn(
                "pychestrate.ui.shell.permissions_listener_failed",
                { kind: "session_401", reason: String(reason) }
              );
            }
          }
        }
        return this._current;
      }
      if (response.ok === false) {
        this._degraded = true;
        this._fire_fetch_failed(`http_${response.status}`);
        return this._current;
      }
      const payload = await response.json();
      const keys = _extract_permission_keys(payload);
      if (keys === null) {
        this._degraded = true;
        this._fire_fetch_failed("malformed_payload");
        return this._current;
      }
      const next_set = new PermissionSet(keys);
      const diff = this._current.diff(next_set);
      this._current = next_set;
      this._degraded = false;
      this._last_outcome_was_401 = false;
      this._last_success_at_ms = this._now();
      if (diff.added.length > 0 || diff.removed.length > 0) {
        for (const listener of this._diff_listeners) {
          try {
            listener(diff);
          } catch (reason) {
            console.warn(
              "pychestrate.ui.shell.permissions_listener_failed",
              { kind: "diff", reason: String(reason) }
            );
          }
        }
      }
      for (const listener of this._fetch_succeeded_listeners) {
        try {
          listener();
        } catch (reason) {
          console.warn(
            "pychestrate.ui.shell.permissions_listener_failed",
            { kind: "success", reason: String(reason) }
          );
        }
      }
      return this._current;
    } catch (reason) {
      this._degraded = true;
      console.warn(
        "pychestrate.ui.shell.permissions_fetch_failed",
        { endpoint: this._endpoint }
      );
      this._fire_fetch_failed(String(reason));
      return this._current;
    }
  }
  _fire_fetch_failed(reason) {
    for (const listener of this._fetch_failed_listeners) {
      try {
        listener({ reason });
      } catch (inner) {
        console.warn(
          "pychestrate.ui.shell.permissions_listener_failed",
          { kind: "failed", reason: String(inner) }
        );
      }
    }
    return;
  }
}
function _extract_permission_keys(payload) {
  if (Array.isArray(payload) === true) {
    const rtnval = payload.filter(
      (item) => typeof item === "string"
    );
    return rtnval;
  }
  if (payload !== null && typeof payload === "object") {
    const obj = payload;
    const candidate = obj.permissions;
    if (Array.isArray(candidate) === true) {
      const rtnval = candidate.filter(
        (item) => typeof item === "string"
      );
      return rtnval;
    }
  }
  return null;
}
export {
  DEFAULT_FRESHNESS_TTL_MS,
  DEFAULT_PERMISSIONS_ENDPOINT,
  PermissionCache
};
