import type { SidebarRegistry } from "./sidebar-registry.js"

/**
 * Default endpoint the shell fetches the central navigation
 * manifest from. Served by the WebWorks-native ``me`` routes
 * (``security/auth/restapi/v1/me_routes.py``).
 */
export const DEFAULT_NAVIGATION_ENDPOINT: string = "/api/v1/me/navigation"

/**
 * Wire shape of one entry inside a manifest group as returned by
 * ``GET /api/v1/me/navigation``.
 */
export interface NavManifestEntry {
    entry_id: string
    label: string
    route: string
    icon?: string | null
    required_permissions?: readonly string[]
}

/**
 * Wire shape of one group as returned by
 * ``GET /api/v1/me/navigation``.
 */
export interface NavManifestGroup {
    group_id: string
    label: string
    icon?: string | null
    required_permissions?: readonly string[]
    entries: readonly NavManifestEntry[]
}

/**
 * Wire shape of the whole manifest response.
 */
export interface NavManifest {
    groups: readonly NavManifestGroup[]
}

/**
 * Outcome of a manifest fetch. ``ok`` is true only when the
 * server returned a well-formed manifest. On any failure the
 * caller keeps whatever the registry already holds and the shell
 * surfaces its degraded path.
 */
export interface NavManifestFetchResult {
    ok: boolean
    manifest: NavManifest | null
}

/**
 * Fetch the central navigation manifest from the server.
 *
 * The manifest is already permission-filtered server-side -- it
 * only contains the groups and entries the calling session may
 * see. A 401 (expired session), non-2xx status, network error, or
 * malformed body all resolve to ``{ ok: false, manifest: null }``;
 * the caller decides how to degrade. This function never throws.
 *
 * @param endpoint - URL to fetch the manifest from.
 * @returns The fetch outcome.
 */
export async function fetch_nav_manifest(
    endpoint: string = DEFAULT_NAVIGATION_ENDPOINT,
): Promise<NavManifestFetchResult> {
    try {
        const response = await fetch(endpoint, {
            method: "GET",
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        })
        if (response.ok === false) {
            const rtnval: NavManifestFetchResult = {
                ok: false,
                manifest: null,
            }
            return rtnval
        }
        const payload = (await response.json()) as unknown
        const manifest = _coerce_manifest(payload)
        if (manifest === null) {
            const rtnval: NavManifestFetchResult = {
                ok: false,
                manifest: null,
            }
            return rtnval
        }
        const rtnval: NavManifestFetchResult = {
            ok: true,
            manifest,
        }
        return rtnval
    } catch (reason: unknown) {
        console.warn(
            "pychestrate.ui.shell.nav_manifest_fetch_failed",
            { endpoint, reason: String(reason) },
        )
        const rtnval: NavManifestFetchResult = {
            ok: false,
            manifest: null,
        }
        return rtnval
    }
}

/**
 * Seed the supplied sidebar registry from a fetched navigation
 * manifest.
 *
 * The manifest is the authoritative source of truth for sidebar
 * navigation. Every group and entry it carries is registered
 * against the registry. Because the registry drops duplicate
 * ``groupId`` / ``route`` registrations (first wins), seeding the
 * manifest before any feature bundle's legacy ``registerEntry``
 * calls run makes the manifest authoritative without breaking
 * bundles that still call ``registerEntry`` for back-compat.
 *
 * Each manifest entry carries an empty ``requiredPermissions``
 * list when registered, because the server already
 * permission-filtered the manifest -- everything in it is
 * visible to the caller. The shell still passes the permission
 * set through ``SidebarRegistry.visible`` for active-route /
 * grouping logic; an empty required list there is simply always
 * satisfied.
 *
 * @param registry - The shell's sidebar registry.
 * @param manifest - A manifest fetched from the server.
 */
export function apply_nav_manifest(
    registry: SidebarRegistry,
    manifest: NavManifest,
): void {
    if (manifest === null || Array.isArray(manifest.groups) === false) {
        return
    }
    for (const group of manifest.groups) {
        if (
            group === null ||
            typeof group.group_id !== "string" ||
            group.group_id.length === 0
        ) {
            continue
        }
        registry.registerGroup({
            groupId: group.group_id,
            label:
                typeof group.label === "string"
                    ? group.label
                    : group.group_id,
            icon: group.icon !== undefined ? group.icon : null,
            requiredPermissions: [],
        })
        if (Array.isArray(group.entries) === false) {
            continue
        }
        for (const entry of group.entries) {
            if (
                entry === null ||
                typeof entry.route !== "string" ||
                entry.route.length === 0
            ) {
                continue
            }
            registry.registerEntry({
                entryId:
                    typeof entry.entry_id === "string"
                        ? entry.entry_id
                        : entry.route,
                label:
                    typeof entry.label === "string"
                        ? entry.label
                        : entry.route,
                route: entry.route,
                icon: entry.icon !== undefined ? entry.icon : null,
                requiredPermissions: [],
                group: group.group_id,
            })
        }
    }
    return
}

/**
 * Coerce an untyped JSON payload to a {@link NavManifest}, or
 * return null when the payload is not a well-formed manifest.
 */
function _coerce_manifest(payload: unknown): NavManifest | null {
    if (payload === null || typeof payload !== "object") {
        return null
    }
    const candidate = payload as { groups?: unknown }
    if (Array.isArray(candidate.groups) === false) {
        return null
    }
    const rtnval: NavManifest = {
        groups: candidate.groups as readonly NavManifestGroup[],
    }
    return rtnval
}
