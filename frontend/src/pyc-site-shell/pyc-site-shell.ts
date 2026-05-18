import { build_empty_state } from "./chrome/empty-state.js"
import { build_header } from "./chrome/header.js"
import {
    DEFAULT_PERMISSIONS_ENDPOINT,
    PermissionCache,
} from "./permissions/permission-cache.js"
import { PermissionSet } from "./permissions/permission-set.js"
import { ShellRouter } from "./routing/shell-router.js"
import { SidebarRegistry } from "./sidebar/sidebar-registry.js"
import { SidebarRenderer } from "./sidebar/sidebar-renderer.js"

const ATTR_INITIAL_ROUTE: string = "initial-route"
const ATTR_PERMISSIONS_ENDPOINT: string = "permissions-endpoint"
const ATTR_PALETTE_TIMEOUT_MS: string = "palette-timeout-ms"
const ATTR_BRAND_LABEL: string = "brand-label"

/**
 * `<pyc-site-shell>` — the unified UI chrome.
 *
 * M1 scope: header, sidebar (rendered from a permission-gated
 * registry), main region, empty state. Palette / degraded banner /
 * mid-session 401 toast are M2.
 *
 * The shell registry is exposed at `window.pychestrateShell` so
 * feature bundles can call `pychestrateShell.sidebar.registerGroup`
 * etc. at load time without needing a JS module import path. PR4
 * will use this hook to wire admin / project sidebars.
 */
export class PycSiteShell extends HTMLElement {
    private _sidebar_registry: SidebarRegistry
    private _permission_cache: PermissionCache
    private _router: ShellRouter | null
    private _sidebar_renderer: SidebarRenderer | null
    private _main_region: HTMLElement | null
    private _sidebar_region: HTMLElement | null
    private _ready: boolean

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
        this._ready = false
    }

    public get sidebar(): SidebarRegistry {
        const rtnval = this._sidebar_registry
        return rtnval
    }

    public get permissions(): PermissionCache {
        const rtnval = this._permission_cache
        return rtnval
    }

    public connectedCallback(): void {
        this._render_skeleton()
        this._wire_window_registry()
        // Boot asynchronously so feature bundles loaded after the
        // shell tag also get a chance to register before the first
        // sidebar render. A microtask is enough — the bundles run
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

        this._router = new ShellRouter(initial_path, () => this._main_region)
        this._sidebar_renderer = new SidebarRenderer(sidebar, (route) => {
            void this._router?.navigateTo(route)
        })

        this._router.onNavigate(async () => {
            await this._permission_cache.refresh()
            this._render_sidebar_and_empty_state()
        })
        return
    }

    private _wire_window_registry(): void {
        const global_target = window as unknown as {
            pychestrateShell?: PycSiteShellRegistryHandle
        }
        const handle: PycSiteShellRegistryHandle = {
            sidebar: this._sidebar_registry,
            element: this,
        }
        global_target.pychestrateShell = handle
        return
    }

    private async _boot(): Promise<void> {
        await this._permission_cache.refresh()
        this._render_sidebar_and_empty_state()
        this._ready = true
        this.dispatchEvent(
            new CustomEvent("pyc-site-shell-ready", {
                bubbles: true,
                composed: true,
                detail: {
                    visibleEntryCount: this._sidebar_registry.visibleEntryCount(
                        this._permission_cache.current(),
                    ),
                    degraded: this._permission_cache.degraded,
                },
            }),
        )
        return
    }

    private _render_sidebar_and_empty_state(): void {
        const perms = this._permission_cache.current()
        const active_path =
            this._router !== null
                ? this._router.current().path
                : window.location.pathname
        if (this._sidebar_renderer !== null && this._sidebar_region !== null) {
            this._sidebar_renderer.render(
                this._sidebar_registry,
                perms,
                active_path,
            )
        }
        const visible_entry_count = this._sidebar_registry.visibleEntryCount(
            perms,
        )
        if (visible_entry_count === 0 && this._main_region !== null) {
            this._main_region.replaceChildren(build_empty_state())
            this.dispatchEvent(
                new CustomEvent("pyc-site-shell-empty-state-rendered", {
                    bubbles: true,
                    composed: true,
                    detail: {},
                }),
            )
        }
        return
    }

    public get isReady(): boolean {
        const rtnval = this._ready
        return rtnval
    }

    /**
     * Test/diagnostic helper — returns the current permission set.
     * Not part of the long-term public API surface (which goes
     * through DOM CustomEvents).
     */
    public currentPermissions(): PermissionSet {
        const rtnval = this._permission_cache.current()
        return rtnval
    }
}

/**
 * Shape of the `window.pychestrateShell` handle feature bundles
 * see. Exporting the interface lets bundle authors type their
 * `(window as any).pychestrateShell` cast.
 */
export interface PycSiteShellRegistryHandle {
    sidebar: SidebarRegistry
    element: PycSiteShell
}
