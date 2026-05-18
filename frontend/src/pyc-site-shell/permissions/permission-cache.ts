import { PermissionSet } from "./permission-set.js"

/**
 * Default endpoint the cache hits when no explicit override is
 * supplied. Matches the route registered by `1-rbac` /
 * `8-rest-api-v1` per the design doc.
 */
export const DEFAULT_PERMISSIONS_ENDPOINT: string = "/api/v1/me/permissions"

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
 * In-memory permission cache for the lifetime of one shell document.
 *
 * Per NFR-2 / NFR-4 of `9-site-shell/requirements.md`:
 *
 * - Never written to `localStorage` / `sessionStorage`.
 * - Survives a fetch failure by retaining the previously-cached
 *   payload and flipping `degraded = true`.
 * - Logs only counts and diffs — never the full payload.
 */
export class PermissionCache {
    private _current: PermissionSet
    private _degraded: boolean
    private readonly _endpoint: string

    /**
     * @param endpoint - URL the cache will GET on `refresh()`.
     */
    public constructor(endpoint: string) {
        this._current = new PermissionSet([])
        this._degraded = false
        this._endpoint = endpoint
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
     * Force a refresh from the server. On success the new
     * `PermissionSet` becomes the current snapshot and `degraded`
     * resets to false. On failure the previous snapshot is
     * retained and `degraded` is set to true. The promise resolves
     * with the current snapshot in both cases — callers should not
     * branch on this method's success/failure as a security check.
     */
    public async refresh(): Promise<PermissionSet> {
        try {
            const response = await fetch(this._endpoint, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                this._degraded = true
                return this._current
            }
            const payload = (await response.json()) as PermissionsPayload | unknown
            const keys = _extract_permission_keys(payload)
            if (keys === null) {
                this._degraded = true
                return this._current
            }
            this._current = new PermissionSet(keys)
            this._degraded = false
            return this._current
        } catch (reason: unknown) {
            this._degraded = true
            // Intentionally do not rethrow — navigation must not be
            // blocked on a permissions fetch (Requirement 4.3).
            console.warn(
                "pychestrate.ui.shell.permissions_fetch_failed",
                { endpoint: this._endpoint },
            )
            return this._current
        }
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
