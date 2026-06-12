import { PycSiteShell } from "./pyc-site-shell.js";
import { PermissionSet } from "./permissions/permission-set.js";
import { PermissionCache } from "./permissions/permission-cache.js";
import { SidebarRegistry } from "./sidebar/sidebar-registry.js";
import {
  DEFAULT_NAVIGATION_ENDPOINT,
  apply_nav_manifest,
  fetch_nav_manifest
} from "./sidebar/nav-manifest.js";
import { PaletteRegistry } from "./palette/palette-registry.js";
import { PaletteDialog } from "./palette/palette-dialog.js";
import {
  attach_sidebar_keyboard,
  initialize_sidebar_roving_tabindex
} from "./sidebar/sidebar-keyboard.js";
import {
  MetricsBeacon,
  SHELL_METRICS,
  DEFAULT_METRICS_ENDPOINT
} from "./observability/metrics-beacon.js";
const TAG_NAME = "pyc-site-shell";
if (typeof customElements !== "undefined") {
  if (customElements.get(TAG_NAME) === void 0) {
    customElements.define(TAG_NAME, PycSiteShell);
  }
}
export {
  DEFAULT_METRICS_ENDPOINT,
  DEFAULT_NAVIGATION_ENDPOINT,
  MetricsBeacon,
  PaletteDialog,
  PaletteRegistry,
  PermissionCache,
  PermissionSet,
  PycSiteShell,
  SHELL_METRICS,
  SidebarRegistry,
  apply_nav_manifest,
  attach_sidebar_keyboard,
  fetch_nav_manifest,
  initialize_sidebar_roving_tabindex
};
