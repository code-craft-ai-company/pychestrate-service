import { PermissionSet } from "./permission-set.js"

/**
 * Default endpoint the cache hits when no explicit override is
 * supplied. Matches the route registered by `1-rbac` /
 * `8-rest-api-v1` per the design doc.
 */
export const DEFAULT_PERMISSIONS_ENDPOINT: string = "/api/v1/me/permissions"

/**
 * Default freshness window for cache reuse. A ``refresh()`` call
 * within this window of the last successful fetch returns the
 * cached snapshot without re-hitting the network. Per Requirement
 * 4.1, the shell still refetches on every full navigation -- the
 * TTL only short-circuits very rapid back-to-back refresh calls
 * (e.g. history-back chained with a programmatic refresh).
 */
export const DEFAULT_FRESHNESS_TTL_MS: number = 60_000

/**
 * Shape of the JSON the server returns from
 * `GET /api/v1/me/permissions`. Two shapes are accepted to keep the
 * client tolerant of payload evolution:
 *
 * 1. A bare array of permission keys: `["a", "b"]`
 * 2. An object with a `permissions` key: `{permissions: ["a", "b"]}`
 *
 * Anything else is treated as malformed and the cache flips to
 * degraded.
 */
interface PermissionsPayload {
    permissions?: unknown
    [key: string]: unknown
}

/**
 * Subscriber callbacks fired by the cache when the snapshot
 * changes or fetch outcomes warrant external attention.
 */
export type PermissionDiffListener = (
    diff: { added: string[]; removed: string[] },
) => void

export type PermissionFetchFailedListener = (
    detail: { reason: string },
) => void

export type PermissionSession401Listener = () => void

export type PermissionFetchSucceededListener = () => void

/**
 * Optional construction overrides -- primarily for tests so they
 * can inject a fake clock or skip the TTL dedup.
 */
export interface PermissionCacheOptions {
    endpoint?: string
    freshnessTtlMs?: number
    now?: () => number
}

/**
 * In-memory permission cache for the lifetime of one shell document.
 *
 * Per NFR-2 / NFR-4 of `9-site-shell/requirements.md`:
 *
 * - Never written to `localStorage` / `sessionStorage`.
 * - Survives a fetch failure by retaining the previously-cached
 *   payload and flipping `degraded = true`.
 * - Logs only counts and diffs -- never the full payload.
 *
 * M2 extensions (PR5):
 *
 * - ``refresh()`` fires diff listeners on every successful fetch
 *   that changes the snapshot.
 * - A 401 response fires session-401 listeners exactly once per
 *   transition (subsequent 401s while already-401 do not re-fire
 *   until a successful refresh in between).
 * - Non-401 fetch failures fire fetch-failed listeners so the
 *   degraded banner can surface.
 * - A TTL dedups rapid ``refresh()`` calls within the freshness
 *   window unless ``force=true``.
 */
export class PermissionCache {
    private _current: PermissionSet
    private _degraded: boolean
    private readonly _endpoint: string
    private readonly _freshness_ttl_ms: number
    private readonly _now: () => number
    private _last_success_at_ms: number | null
    private _diff_listeners: PermissionDiffListener[]
    private _fetch_failed_listeners: PermissionFetchFailedListener[]
    private _session_401_listeners: PermissionSession401Listener[]
    private _fetch_succeeded_listeners: PermissionFetchSucceededListener[]
    private _last_outcome_was_401: boolean

    /**
     * @param endpoint Either a URL string (back-compat) or an
     *                 options object. When a string is supplied,
     *                 defaults are applied for the other fields.
     */
    public constructor(endpoint: string | PermissionCacheOptions) {
        let resolved_endpoint: string = DEFAULT_PERMISSIONS_ENDPOINT
        let resolved_ttl_ms: number = DEFAULT_FRESHNESS_TTL_MS
        let resolved_now: () => number = () => Date.now()
        if (typeof endpoint === "string") {
            resolved_endpoint = endpoint
        } else if (endpoint !== null && typeof endpoint === "object") {
            if (
                typeof endpoint.endpoint === "string" &&
                endpoint.endpoint.length > 0
            ) {
                resolved_endpoint = endpoint.endpoint
            }
            if (typeof endpoint.freshnessTtlMs === "number") {
                resolved_ttl_ms = endpoint.freshnessTtlMs
            }
            if (typeof endpoint.now === "function") {
                resolved_now = endpoint.now
            }
        }
        this._current = new PermissionSet([])
        this._degraded = false
        this._endpoint = resolved_endpoint
        this._freshness_ttl_ms = resolved_ttl_ms
        this._now = resolved_now
        this._last_success_at_ms = null
        this._diff_listeners = []
        this._fetch_failed_listeners = []
        this._session_401_listeners = []
        this._fetch_succeeded_listeners = []
        this._last_outcome_was_401 = false
    }

    /**
     * Return the current snapshot.
     */
    public current(): PermissionSet {
        const rtnval = this._current
        return rtnval
    }

    /**
     * Return true when the most recent fetch failed.
     */
    public get degraded(): boolean {
        const rtnval = this._degraded
        return rtnval
    }

    /**
     * Subscribe to permission-set diffs. Listener fires on every
     * ``refresh()`` whose successful fetch changed the snapshot.
     */
    public onPermissionsChanged(listener: PermissionDiffListener): void {
        this._diff_listeners.push(listener)
        return
    }

    /**
     * Subscribe to non-401 fetch failures (network errors, 5xx).
     * The degraded banner consumes this hook.
     */
    public onFetchFailed(listener: PermissionFetchFailedListener): void {
        this._fetch_failed_listeners.push(listener)
        return
    }

    /**
     * Subscribe to successful fetches -- used by the degraded
     * banner to auto-dismiss on recovery.
     */
    public onFetchSucceeded(listener: PermissionFetchSucceededListener): void {
        this._fetch_succeeded_listeners.push(listener)
        return
    }

    /**
     * Subscribe to mid-session 401 events. Fired exactly once per
     * transition from healthy to expired-session.
     */
    public onSession401(listener: PermissionSession401Listener): void {
        this._session_401_listeners.push(listener)
        return
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
    public async refresh(force: boolean = true): Promise<PermissionSet> {
        if (
            force === false &&
            this._last_success_at_ms !== null &&
            this._now() - this._last_success_at_ms < this._freshness_ttl_ms
        ) {
            return this._current
        }
        try {
            const response = await fetch(this._endpoint, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.status === 401) {
                this._degraded = true
                if (this._last_outcome_was_401 === false) {
                    this._last_outcome_was_401 = true
                    for (const listener of this._session_401_listeners) {
                        try {
                            listener()
                        } catch (reason: unknown) {
                            console.warn(
                                "pychestrate.ui.shell.permissions_listener_failed",
                                { kind: "session_401", reason: String(reason) },
                            )
                        }
                    }
                }
                return this._current
            }
            if (response.ok === false) {
                this._degraded = true
                this._fire_fetch_failed(`http_${response.status}`)
                return this._current
            }
            const payload = (await response.json()) as PermissionsPayload | unknown
            const keys = _extract_permission_keys(payload)
            if (keys === null) {
                this._degraded = true
                this._fire_fetch_failed("malformed_payload")
                return this._current
            }
            const next_set = new PermissionSet(keys)
            const diff = this._current.diff(next_set)
            this._current = next_set
            this._degraded = false
            this._last_outcome_was_401 = false
            this._last_success_at_ms = this._now()
            if (diff.added.length > 0 || diff.removed.length > 0) {
                for (const listener of this._diff_listeners) {
                    try {
                        listener(diff)
                    } catch (reason: unknown) {
                        console.warn(
                            "pychestrate.ui.shell.permissions_listener_failed",
                            { kind: "diff", reason: String(reason) },
                        )
                    }
                }
            }
            for (const listener of this._fetch_succeeded_listeners) {
                try {
                    listener()
                } catch (reason: unknown) {
                    console.warn(
                        "pychestrate.ui.shell.permissions_listener_failed",
                        { kind: "success", reason: String(reason) },
                    )
                }
            }
            return this._current
        } catch (reason: unknown) {
            this._degraded = true
            // Intentionally do not rethrow -- navigation must not be
            // blocked on a permissions fetch (Requirement 4.3).
            console.warn(
                "pychestrate.ui.shell.permissions_fetch_failed",
                { endpoint: this._endpoint },
            )
            this._fire_fetch_failed(String(reason))
            return this._current
        }
    }

    private _fire_fetch_failed(reason: string): void {
        for (const listener of this._fetch_failed_listeners) {
            try {
                listener({ reason })
            } catch (inner: unknown) {
                console.warn(
                    "pychestrate.ui.shell.permissions_listener_failed",
                    { kind: "failed", reason: String(inner) },
                )
            }
        }
        return
    }
}

/**
 * Extract the permission-keys array from a tolerated payload shape.
 *
 * @returns Array of strings, or null when the payload is malformed.
 */
function _extract_permission_keys(payload: unknown): string[] | null {
    if (Array.isArray(payload) === true) {
        const rtnval = (payload as unknown[]).filter(
            (item) => typeof item === "string",
        ) as string[]
        return rtnval
    }
    if (payload !== null && typeof payload === "object") {
        const obj = payload as PermissionsPayload
        const candidate = obj.permissions
        if (Array.isArray(candidate) === true) {
            const rtnval = (candidate as unknown[]).filter(
                (item) => typeof item === "string",
            ) as string[]
            return rtnval
        }
    }
    return null
}
