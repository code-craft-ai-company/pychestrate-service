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
export type { PycSiteShellRegistryHandle } from "./pyc-site-shell.js"

const TAG_NAME: string = "pyc-site-shell"

if (typeof customElements !== "undefined") {
    if (customElements.get(TAG_NAME) === undefined) {
        customElements.define(TAG_NAME, PycSiteShell)
    }
}
