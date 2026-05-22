/**
 * Entry point for the `<pyc-site-shell>` bundle.
 *
 * Importing this module (or loading the built bundle in a page)
 * registers the Custom Element and installs the
 * `window.pychestrateShell` handle. Feature bundles can then call
 * `window.pychestrateShell.sidebar.registerEntry({...})` etc.
 */

import { PycSiteShell } from "./pyc-site-shell.js"

export { PycSiteShell }
export { PermissionSet } from "./permissions/permission-set.js"
export { PermissionCache } from "./permissions/permission-cache.js"
export { SidebarRegistry } from "./sidebar/sidebar-registry.js"
export type {
    SidebarGroup,
    SidebarEntry,
    VisibleSidebar,
} from "./sidebar/sidebar-registry.js"
export {
    DEFAULT_NAVIGATION_ENDPOINT,
    apply_nav_manifest,
    fetch_nav_manifest,
} from "./sidebar/nav-manifest.js"
export type {
    NavManifest,
    NavManifestGroup,
    NavManifestEntry,
    NavManifestFetchResult,
} from "./sidebar/nav-manifest.js"
export { PaletteRegistry } from "./palette/palette-registry.js"
export type {
    PaletteProvider,
    PaletteResult,
    PaletteProviderOutcome,
} from "./palette/palette-registry.js"
export { PaletteDialog } from "./palette/palette-dialog.js"
export {
    attach_sidebar_keyboard,
    initialize_sidebar_roving_tabindex,
} from "./sidebar/sidebar-keyboard.js"
export type { PycSiteShellRegistryHandle } from "./pyc-site-shell.js"
export {
    MetricsBeacon,
    SHELL_METRICS,
    DEFAULT_METRICS_ENDPOINT,
} from "./observability/metrics-beacon.js"
export type {
    ClientMetric,
    MetricsBeaconOptions,
} from "./observability/metrics-beacon.js"

const TAG_NAME: string = "pyc-site-shell"

if (typeof customElements !== "undefined") {
    if (customElements.get(TAG_NAME) === undefined) {
        customElements.define(TAG_NAME, PycSiteShell)
    }
}
