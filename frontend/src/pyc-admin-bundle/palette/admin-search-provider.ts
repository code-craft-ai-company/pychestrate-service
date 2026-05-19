/**
 * Admin palette search provider.
 *
 * Calls ``GET /api/v1/admin/search?q=<q>`` and shapes the response
 * into ``PaletteResult`` records.
 *
 * Backend status (PR p17f / PR5): the admin search endpoint is NOT
 * yet implemented. When the endpoint 404s or 405s, the provider
 * surfaces as "unavailable" in the palette (the registry catches
 * the rejection and renders an inline notice). This keeps the
 * palette demo-able without blocking on the backend.
 *
 * TODO(p17g+): once ``/api/v1/admin/search`` lands, expand the
 * response handling here to support typed result categories
 * (users, roles, audit events, etc.).
 */

interface AdminPaletteResultLike {
    id: string
    label: string
    description?: string | null
    route?: string | null
}

interface PaletteProviderRegistryLike {
    registerProvider(provider: {
        providerId: string
        label: string
        requiredPermissions?: readonly string[]
        timeoutMs?: number
        query: (q: string) => Promise<AdminPaletteResultLike[]>
    }): void
}

const PROVIDER_ID: string = "admin.search"
const PROVIDER_LABEL: string = "Admin"
const PROVIDER_TIMEOUT_MS: number = 3000
const PROVIDER_REQUIRED_PERMISSIONS: readonly string[] = ["system:ui.admin.view"]
const SEARCH_ENDPOINT: string = "/api/v1/admin/search"

/**
 * Issue the admin search request. Rejects with an Error when the
 * endpoint is unreachable or returns a non-2xx response so the
 * palette registry surfaces the "this provider is unavailable"
 * inline notice.
 *
 * @param query Raw user query.
 */
async function _admin_search(query: string): Promise<AdminPaletteResultLike[]> {
    const trimmed = query.trim()
    if (trimmed.length === 0) {
        const rtnval: AdminPaletteResultLike[] = []
        return rtnval
    }
    const url = SEARCH_ENDPOINT + "?q=" + encodeURIComponent(trimmed)
    const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
    })
    if (response.ok === false) {
        throw new Error("admin_search_unavailable_" + String(response.status))
    }
    const payload = await response.json()
    const results: AdminPaletteResultLike[] = []
    if (Array.isArray(payload) === true) {
        _coerce_into(payload, results)
    } else if (
        payload !== null &&
        typeof payload === "object" &&
        Array.isArray((payload as { results?: unknown }).results) === true
    ) {
        const items = (payload as { results: unknown[] }).results
        _coerce_into(items, results)
    }
    return results
}

function _coerce_into(
    items: unknown[],
    out: AdminPaletteResultLike[],
): void {
    for (const item of items) {
        if (item === null || typeof item !== "object") {
            continue
        }
        const obj = item as Record<string, unknown>
        const id = obj.id
        const label = obj.label
        if (typeof id !== "string" || typeof label !== "string") {
            continue
        }
        const result: AdminPaletteResultLike = {
            id,
            label,
            description:
                typeof obj.description === "string"
                    ? (obj.description as string)
                    : null,
            route: typeof obj.route === "string" ? (obj.route as string) : null,
        }
        out.push(result)
    }
    return
}

/**
 * Register the admin search provider with a palette registry.
 * Exported for unit tests to drive registration without going
 * through the global handle.
 *
 * @param palette Palette-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_admin_palette_provider(
    palette: PaletteProviderRegistryLike,
): void {
    palette.registerProvider({
        providerId: PROVIDER_ID,
        label: PROVIDER_LABEL,
        requiredPermissions: PROVIDER_REQUIRED_PERMISSIONS,
        timeoutMs: PROVIDER_TIMEOUT_MS,
        query: _admin_search,
    })
    return
}

export const ADMIN_PALETTE_PROVIDER_ID: string = PROVIDER_ID
