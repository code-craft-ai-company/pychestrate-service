import { PermissionSet } from "../permissions/permission-set.js"

/**
 * Default per-provider timeout (milliseconds) when no provider
 * override is supplied. Matches the design-doc default (5 s) for
 * the palette fan-out.
 */
export const DEFAULT_PROVIDER_TIMEOUT_MS: number = 5000

/**
 * Cap on the palette query string length (Requirement / NFR-2 of
 * the 9-site-shell spec).
 */
export const PALETTE_QUERY_MAX_LENGTH: number = 128

/**
 * Shape of a single palette result returned by a provider's
 * ``query`` callback.
 *
 * - ``id`` is unique within a provider's result list and is used
 *   as a stable key for re-rendering.
 * - ``label`` is the displayed text.
 * - ``description`` is optional secondary text rendered beneath
 *   the label.
 * - ``route`` is the path the shell navigates to when the user
 *   activates the result (used as a fallback when ``onActivate``
 *   is not provided).
 * - ``onActivate`` is an optional callback the palette invokes
 *   when the user selects the result. If absent, the palette
 *   navigates to ``route`` via the shell router.
 */
export interface PaletteResult {
    id: string
    label: string
    description?: string | null
    route?: string | null
    onActivate?: () => void | Promise<void>
}

/**
 * Descriptor for a palette search provider. Feature bundles
 * register one of these per searchable surface.
 */
export interface PaletteProvider {
    providerId: string
    label: string
    requiredPermissions?: readonly string[]
    query: (q: string) => Promise<PaletteResult[]>
    timeoutMs?: number
}

/**
 * Outcome of a single provider's query during a fan-out call.
 * Exactly one of ``results`` / ``error`` is populated.
 */
export interface PaletteProviderOutcome {
    providerId: string
    providerLabel: string
    results: PaletteResult[]
    error: string | null
}

/**
 * Registry tracking palette providers and orchestrating the
 * permission-gated query fan-out.
 *
 * Per Requirement 7 of ``9-site-shell``:
 *
 * - A provider is invoked iff the caller holds every entry in its
 *   ``requiredPermissions``.
 * - A provider that throws / rejects / times out yields an outcome
 *   with ``error`` set but does NOT abort the other providers.
 */
export class PaletteRegistry {
    private readonly _providers: Map<string, PaletteProvider>

    public constructor() {
        this._providers = new Map<string, PaletteProvider>()
    }

    /**
     * Register a palette provider. Duplicate ``providerId`` calls
     * are dropped with a ``console.warn`` (first wins) -- mirrors
     * the sidebar registry's collision policy.
     *
     * @param provider Descriptor.
     */
    public registerProvider(provider: PaletteProvider): void {
        if (provider === null || typeof provider !== "object") {
            console.warn(
                "pychestrate.ui.shell.palette_malformed_provider_registration",
            )
            return
        }
        if (
            typeof provider.providerId !== "string" ||
            provider.providerId.length === 0
        ) {
            console.warn(
                "pychestrate.ui.shell.palette_malformed_provider_registration",
                { reason: "missing_providerId" },
            )
            return
        }
        if (typeof provider.query !== "function") {
            console.warn(
                "pychestrate.ui.shell.palette_malformed_provider_registration",
                { reason: "missing_query", providerId: provider.providerId },
            )
            return
        }
        if (this._providers.has(provider.providerId) === true) {
            console.warn(
                "pychestrate.ui.shell.palette_dup_provider",
                { providerId: provider.providerId },
            )
            return
        }
        this._providers.set(provider.providerId, provider)
        return
    }

    /**
     * Return the providers that pass the permission gate for the
     * supplied permission set. Order follows registration order.
     */
    public visibleProviders(perms: PermissionSet): PaletteProvider[] {
        const visible: PaletteProvider[] = []
        for (const provider of this._providers.values()) {
            const required = provider.requiredPermissions !== undefined
                ? provider.requiredPermissions
                : []
            if (perms.hasAll(required) === true) {
                visible.push(provider)
            }
        }
        return visible
    }

    /**
     * Total registered provider count. Diagnostic only.
     */
    public size(): number {
        const rtnval = this._providers.size
        return rtnval
    }

    /**
     * Fan-out the supplied query to every visible provider,
     * applying a per-provider timeout. Returns an array of
     * outcomes in the same order as ``visibleProviders``.
     *
     * Failures (rejections, timeouts) are reported as outcomes
     * with ``error`` set, NOT as a thrown rejection from this
     * method. Callers can therefore render partial results
     * deterministically.
     *
     * @param query Raw query string. Trimmed and capped to
     *              ``PALETTE_QUERY_MAX_LENGTH`` characters.
     * @param perms Active permission set.
     */
    public async queryAll(
        query: string,
        perms: PermissionSet,
    ): Promise<PaletteProviderOutcome[]> {
        const normalized = _normalize_query(query)
        const visible = this.visibleProviders(perms)
        const pending: Promise<PaletteProviderOutcome>[] = []
        for (const provider of visible) {
            pending.push(_run_provider(provider, normalized))
        }
        const settled = await Promise.all(pending)
        return settled
    }
}

function _normalize_query(query: string): string {
    let working = typeof query === "string" ? query : ""
    working = working.trim()
    if (working.length > PALETTE_QUERY_MAX_LENGTH) {
        working = working.slice(0, PALETTE_QUERY_MAX_LENGTH)
    }
    return working
}

async function _run_provider(
    provider: PaletteProvider,
    query: string,
): Promise<PaletteProviderOutcome> {
    const timeout_ms = typeof provider.timeoutMs === "number" &&
        provider.timeoutMs > 0
        ? provider.timeoutMs
        : DEFAULT_PROVIDER_TIMEOUT_MS
    let timer_handle: ReturnType<typeof setTimeout> | null = null
    const timeout_promise = new Promise<never>((_, reject) => {
        timer_handle = setTimeout(() => {
            reject(new Error("palette_provider_timeout"))
        }, timeout_ms)
    })
    try {
        const results = await Promise.race([
            provider.query(query),
            timeout_promise,
        ])
        if (timer_handle !== null) {
            clearTimeout(timer_handle)
        }
        const safe_results = Array.isArray(results) ? results : []
        const outcome: PaletteProviderOutcome = {
            providerId: provider.providerId,
            providerLabel: provider.label,
            results: safe_results,
            error: null,
        }
        return outcome
    } catch (reason: unknown) {
        if (timer_handle !== null) {
            clearTimeout(timer_handle)
        }
        const outcome: PaletteProviderOutcome = {
            providerId: provider.providerId,
            providerLabel: provider.label,
            results: [],
            error: String(reason),
        }
        return outcome
    }
}
