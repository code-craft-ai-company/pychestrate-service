import { build_empty_state } from "./chrome/empty-state.js"
import { build_header } from "./chrome/header.js"
import { DegradedBanner } from "./chrome/degraded-banner.js"
import { SessionExpiredToast } from "./chrome/session-toast.js"
import { PaletteRegistry } from "./palette/palette-registry.js"
import { PaletteDialog } from "./palette/palette-dialog.js"
import {
    DEFAULT_PERMISSIONS_ENDPOINT,
    PermissionCache,
} from "./permissions/permission-cache.js"
import { PermissionSet } from "./permissions/permission-set.js"
import { ShellRouter } from "./routing/shell-router.js"
import { SidebarRegistry } from "./sidebar/sidebar-registry.js"
import { SidebarRenderer } from "./sidebar/sidebar-renderer.js"
import {
    MetricsBeacon,
    SHELL_METRICS,
} from "./observability/metrics-beacon.js"

const ATTR_INITIAL_ROUTE: string = "initial-route"
const ATTR_PERMISSIONS_ENDPOINT: string = "permissions-endpoint"
const ATTR_PALETTE_TIMEOUT_MS: string = "palette-timeout-ms"
const ATTR_BRAND_LABEL: string = "brand-label"

/**
 * `<pyc-site-shell>` -- the unified UI chrome.
 *
 * M2 scope (PR5): adds command palette, mid-session 401 toast,
 * degraded banner, keyboard sidebar navigation, and the
 * ``pyc-site-shell-permissions-changed`` diff event on top of the
 * M1 skeleton.
 *
 * The shell registry is exposed at ``window.pychestrateShell`` so
 * feature bundles can call ``pychestrateShell.sidebar.registerGroup``
 * etc. at load time without needing a JS module import path. The
 * same handle now exposes ``palette.registerProvider`` for the
 * command-palette providers contributed by feature bundles.
 */
export class PycSiteShell extends HTMLElement {
    private _sidebar_registry: SidebarRegistry
    private _palette_registry: PaletteRegistry
    private _permission_cache: PermissionCache
    private _router: ShellRouter | null
    private _sidebar_renderer: SidebarRenderer | null
    private _main_region: HTMLElement | null
    private _sidebar_region: HTMLElement | null
    private _palette_dialog: PaletteDialog | null
    private _degraded_banner: DegradedBanner | null
    private _session_toast: SessionExpiredToast | null
    private _global_keydown: ((event: KeyboardEvent) => void) | null
    private _global_session_401: (() => void) | null
    private _ready: boolean
    private _metrics: MetricsBeacon
    private _metrics_lifecycle_detach: (() => void) | null
    private _boot_started_perf_now: number
    private _palette_open_keydown_perf_now: number | null

    public static readonly observedAttributes: readonly string[] = [
        ATTR_INITIAL_ROUTE,
        ATTR_PERMISSIONS_ENDPOINT,
        ATTR_PALETTE_TIMEOUT_MS,
        "aria-label",
        ATTR_BRAND_LABEL,
    ]

    public constructor() {
        super()
        this._sidebar_registry = new SidebarRegistry()
        this._palette_registry = new PaletteRegistry()
        const endpoint = this.getAttribute(ATTR_PERMISSIONS_ENDPOINT)
        const resolved_endpoint =
            endpoint !== null && endpoint.length > 0
                ? endpoint
                : DEFAULT_PERMISSIONS_ENDPOINT
        this._permission_cache = new PermissionCache(resolved_endpoint)
        this._router = null
        this._sidebar_renderer = null
        this._main_region = null
        this._sidebar_region = null
        this._palette_dialog = null
        this._degraded_banner = null
        this._session_toast = null
        this._global_keydown = null
        this._global_session_401 = null
        this._ready = false
        this._metrics = new MetricsBeacon()
        this._metrics_lifecycle_detach = null
        this._boot_started_perf_now =
            typeof performance !== "undefined" ? performance.now() : 0
        this._palette_open_keydown_perf_now = null
    }

    /**
     * Diagnostic accessor for tests + bench harness -- returns the
     * metrics beacon instance the shell uses. Not part of the
     * long-term public API.
     */
    public get metrics(): MetricsBeacon {
        const rtnval = this._metrics
        return rtnval
    }

    public get sidebar(): SidebarRegistry {
        const rtnval = this._sidebar_registry
        return rtnval
    }

    public get palette(): PaletteRegistry {
        const rtnval = this._palette_registry
        return rtnval
    }

    public get permissions(): PermissionCache {
        const rtnval = this._permission_cache
        return rtnval
    }

    public connectedCallback(): void {
        this._boot_started_perf_now =
            typeof performance !== "undefined" ? performance.now() : 0
        this._metrics_lifecycle_detach = this._metrics.attachLifecycle()
        this._render_skeleton()
        this._wire_permission_listeners()
        this._wire_global_keydown()
        this._wire_global_session_401()
        this._wire_window_registry()
        // Boot asynchronously so feature bundles loaded after the
        // shell tag also get a chance to register before the first
        // sidebar render. A microtask is enough -- the bundles run
        // synchronously after their module body loads.
        queueMicrotask(() => {
            this._boot().catch((reason: unknown) => {
                console.warn(
                    "pychestrate.ui.shell.boot_failed",
                    { reason: String(reason) },
                )
            })
        })
        return
    }

    public disconnectedCallback(): void {
        if (this._metrics_lifecycle_detach !== null) {
            this._metrics_lifecycle_detach()
            this._metrics_lifecycle_detach = null
        }
        this._metrics.flush()
        if (this._global_keydown !== null) {
            window.removeEventListener("keydown", this._global_keydown)
            this._global_keydown = null
        }
        if (this._global_session_401 !== null) {
            window.removeEventListener(
                "pyc-session-401",
                this._global_session_401,
            )
            this._global_session_401 = null
        }
        return
    }

    /**
     * Public hook -- open the command palette. Exposed so feature
     * bundles or tests can trigger the palette without simulating
     * a keystroke.
     */
    public openPalette(): void {
        if (this._palette_open_keydown_perf_now === null) {
            this._palette_open_keydown_perf_now =
                typeof performance !== "undefined" ? performance.now() : 0
        }
        if (this._palette_dialog !== null) {
            this._palette_dialog.open()
        }
        return
    }

    /**
     * Public hook -- close the command palette.
     */
    public closePalette(): void {
        if (this._palette_dialog !== null) {
            this._palette_dialog.close()
        }
        return
    }

    private _render_skeleton(): void {
        const initial_route_attr = this.getAttribute(ATTR_INITIAL_ROUTE)
        const initial_path =
            initial_route_attr !== null && initial_route_attr.length > 0
                ? initial_route_attr
                : window.location.pathname

        this.replaceChildren()

        const layout = document.createElement("div")
        layout.classList.add("pyc-site-shell__layout")

        const brand_attr = this.getAttribute(ATTR_BRAND_LABEL)
        const header = build_header({
            brand_label:
                brand_attr !== null && brand_attr.length > 0
                    ? brand_attr
                    : "Pychestrate",
            user_display_name: null,
        })
        layout.appendChild(header)

        const sidebar = document.createElement("aside")
        sidebar.classList.add("pyc-site-shell__sidebar")
        layout.appendChild(sidebar)
        this._sidebar_region = sidebar

        const main = document.createElement("main")
        main.setAttribute("role", "main")
        main.classList.add("pyc-site-shell__main")
        layout.appendChild(main)
        this._main_region = main

        this.appendChild(layout)

        this._degraded_banner = new DegradedBanner(main)
        this._session_toast = new SessionExpiredToast(main)
        this._palette_dialog = new PaletteDialog(
            this._palette_registry,
            {
                getPermissions: () => this._permission_cache.current(),
                navigate: (route: string) => {
                    if (this._router !== null) {
                        void this._router.navigateTo(route)
                    }
                },
                emit: (
                    event_name: string,
                    detail: Record<string, unknown>,
                ) => {
                    this._emit(event_name, detail)
                },
                observePaletteOpened: () => {
                    if (this._palette_open_keydown_perf_now !== null) {
                        const now_value =
                            typeof performance !== "undefined"
                                ? performance.now()
                                : 0
                        const seconds =
                            (now_value -
                                this._palette_open_keydown_perf_now) /
                            1000
                        this._palette_open_keydown_perf_now = null
                        this._metrics.observeHistogram(
                            SHELL_METRICS.PALETTE_OPEN,
                            seconds,
                        )
                    }
                },
                observePaletteFanout: (seconds: number) => {
                    this._metrics.observeHistogram(
                        SHELL_METRICS.PALETTE_FANOUT,
                        seconds,
                    )
                },
            },
        )

        this._router = new ShellRouter(initial_path, () => this._main_region)
        this._sidebar_renderer = new SidebarRenderer(
            sidebar,
            (route) => {
                void this._router?.navigateTo(route)
            },
            (entry_route: string, entry_label: string) => {
                this._emit(
                    "pyc-site-shell-sidebar-clicked",
                    {
                        entryRoute: entry_route,
                        entryLabel: entry_label,
                    },
                )
                this._metrics.incrementCounter(
                    SHELL_METRICS.SIDEBAR_ENTRY_CLICKED,
                    { entry_route },
                )
            },
        )

        this._router.onNavigate(async (next_ctx, prev_ctx) => {
            const refetch_started =
                typeof performance !== "undefined" ? performance.now() : 0
            await this._permission_cache.refresh(true)
            const refetch_finished =
                typeof performance !== "undefined" ? performance.now() : 0
            this._metrics.observeHistogram(
                SHELL_METRICS.PERMISSION_REFETCH,
                (refetch_finished - refetch_started) / 1000,
            )
            this._render_sidebar_and_empty_state()
            this._emit(
                "pyc-site-shell-navigated",
                {
                    from: prev_ctx !== null ? prev_ctx.path : null,
                    to: next_ctx.path,
                },
            )
        })
        return
    }

    private _wire_permission_listeners(): void {
        this._permission_cache.onPermissionsChanged((diff) => {
            this._emit(
                "pyc-site-shell-permissions-changed",
                { added: diff.added, removed: diff.removed },
            )
            this._render_sidebar_and_empty_state()
        })
        this._permission_cache.onFetchFailed(() => {
            if (this._degraded_banner !== null) {
                this._degraded_banner.show()
            }
            this._emit_window_event(
                "pyc-permissions-fetch-failed",
                {},
            )
        })
        this._permission_cache.onFetchSucceeded(() => {
            if (this._degraded_banner !== null) {
                this._degraded_banner.hide()
            }
        })
        this._permission_cache.onSession401(() => {
            this._emit_window_event("pyc-session-401", {})
        })
        return
    }

    private _wire_global_keydown(): void {
        const handler = (event: KeyboardEvent): void => {
            if (event.defaultPrevented === true) {
                return
            }
            const is_palette_combo =
                (event.ctrlKey === true || event.metaKey === true) &&
                event.key.toLowerCase() === "k"
            if (is_palette_combo === true) {
                event.preventDefault()
                this._palette_open_keydown_perf_now =
                    typeof performance !== "undefined"
                        ? performance.now()
                        : 0
                this.openPalette()
            }
        }
        window.addEventListener("keydown", handler)
        this._global_keydown = handler
        return
    }

    private _wire_global_session_401(): void {
        const handler = (): void => {
            if (this._session_toast !== null) {
                this._session_toast.show()
            }
        }
        window.addEventListener("pyc-session-401", handler)
        this._global_session_401 = handler
        return
    }

    private _wire_window_registry(): void {
        const global_target = window as unknown as {
            pychestrateShell?: PycSiteShellRegistryHandle
        }
        const handle: PycSiteShellRegistryHandle = {
            sidebar: this._sidebar_registry,
            palette: this._palette_registry,
            element: this,
        }
        global_target.pychestrateShell = handle
        return
    }

    private async _boot(): Promise<void> {
        await this._permission_cache.refresh(true)
        this._render_sidebar_and_empty_state()
        this._ready = true
        const ready_perf_now =
            typeof performance !== "undefined" ? performance.now() : 0
        const tti_seconds =
            (ready_perf_now - this._boot_started_perf_now) / 1000
        this._metrics.observeHistogram(SHELL_METRICS.TTI, tti_seconds)
        // Flush on ready so the TTI metric is delivered before the
        // user navigates away.
        this._metrics.flush()
        this._emit(
            "pyc-site-shell-ready",
            {
                visibleEntryCount: this._sidebar_registry.visibleEntryCount(
                    this._permission_cache.current(),
                ),
                degraded: this._permission_cache.degraded,
            },
        )
        return
    }

    private _render_sidebar_and_empty_state(): void {
        const perms = this._permission_cache.current()
        const active_path =
            this._router !== null
                ? this._router.current().path
                : window.location.pathname
        const render_started =
            typeof performance !== "undefined" ? performance.now() : 0
        if (this._sidebar_renderer !== null && this._sidebar_region !== null) {
            this._sidebar_renderer.render(
                this._sidebar_registry,
                perms,
                active_path,
            )
        }
        const render_finished =
            typeof performance !== "undefined" ? performance.now() : 0
        this._metrics.observeHistogram(
            SHELL_METRICS.SIDEBAR_RENDER,
            (render_finished - render_started) / 1000,
        )
        const visible_entry_count = this._sidebar_registry.visibleEntryCount(
            perms,
        )
        if (visible_entry_count === 0 && this._main_region !== null) {
            // Keep degraded banner / session toast around when
            // present; the empty-state replaces only the rest.
            const preserved: HTMLElement[] = []
            for (const child of Array.from(this._main_region.children)) {
                if (
                    child.classList.contains(
                        "pyc-site-shell__degraded-banner",
                    ) === true ||
                    child.classList.contains(
                        "pyc-site-shell__session-toast",
                    ) === true
                ) {
                    preserved.push(child as HTMLElement)
                }
            }
            this._main_region.replaceChildren(...preserved, build_empty_state())
            this._emit(
                "pyc-site-shell-empty-state-rendered",
                {},
            )
        }
        return
    }

    private _emit(
        event_name: string,
        detail: Record<string, unknown>,
    ): void {
        this.dispatchEvent(
            new CustomEvent(event_name, {
                bubbles: true,
                composed: true,
                detail,
            }),
        )
        return
    }

    private _emit_window_event(
        event_name: string,
        detail: Record<string, unknown>,
    ): void {
        window.dispatchEvent(
            new CustomEvent(event_name, {
                bubbles: false,
                detail,
            }),
        )
        return
    }

    public get isReady(): boolean {
        const rtnval = this._ready
        return rtnval
    }

    /**
     * Test/diagnostic helper -- returns the current permission set.
     * Not part of the long-term public API surface (which goes
     * through DOM CustomEvents).
     */
    public currentPermissions(): PermissionSet {
        const rtnval = this._permission_cache.current()
        return rtnval
    }
}

/**
 * Shape of the ``window.pychestrateShell`` handle feature bundles
 * see. Exporting the interface lets bundle authors type their
 * ``(window as any).pychestrateShell`` cast.
 */
export interface PycSiteShellRegistryHandle {
    sidebar: SidebarRegistry
    palette: PaletteRegistry
    element: PycSiteShell
}
