import { PycAdminOverview } from "./admin-overview-view.js";
import { PycFeatureFlags } from "./feature-flags-view.js";
import { PycExtensionRegistry } from "./extension-registry-view.js";
import { PycSystemHealth } from "./system-health-view.js";
const ADMIN_GROUP_ID = "admin";
const OVERVIEW_TAG = "pyc-admin-overview";
const FEATURE_FLAGS_TAG = "pyc-feature-flags";
const EXTENSION_REGISTRY_TAG = "pyc-extension-registry";
const SYSTEM_HEALTH_TAG = "pyc-system-health";
const OVERVIEW_ROUTE = "/admin";
const OVERVIEW_ALIAS_ROUTE = "/admin/overview";
const FEATURE_FLAGS_ROUTE = "/admin/feature-flags";
const EXTENSION_REGISTRY_ROUTE = "/admin/extensions";
const SYSTEM_HEALTH_ROUTE = "/admin/system-health";
const ADMIN_STYLESHEET_HREF = "/static/javascript/pyc-admin-bundle/pyc-admin-bundle.css";
function ensure_admin_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-admin-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = ADMIN_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-admin-bundle");
  document.head.appendChild(link);
  return;
}
function define_admin_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(OVERVIEW_TAG) === void 0) {
    customElements.define(OVERVIEW_TAG, PycAdminOverview);
  }
  if (customElements.get(FEATURE_FLAGS_TAG) === void 0) {
    customElements.define(FEATURE_FLAGS_TAG, PycFeatureFlags);
  }
  if (customElements.get(EXTENSION_REGISTRY_TAG) === void 0) {
    customElements.define(EXTENSION_REGISTRY_TAG, PycExtensionRegistry);
  }
  if (customElements.get(SYSTEM_HEALTH_TAG) === void 0) {
    customElements.define(SYSTEM_HEALTH_TAG, PycSystemHealth);
  }
  return;
}
function classify_admin_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working.length > 1 && working.endsWith("/") === true) {
    working = working.slice(0, working.length - 1);
  }
  if (working === FEATURE_FLAGS_ROUTE) {
    const rtnval2 = "feature-flags";
    return rtnval2;
  }
  if (working === EXTENSION_REGISTRY_ROUTE) {
    const rtnval2 = "extensions";
    return rtnval2;
  }
  if (working === SYSTEM_HEALTH_ROUTE) {
    const rtnval2 = "system-health";
    return rtnval2;
  }
  if (working === OVERVIEW_ROUTE || working === OVERVIEW_ALIAS_ROUTE) {
    const rtnval2 = "overview";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_admin_route(route) {
  if (route === "overview") {
    const rtnval2 = OVERVIEW_TAG;
    return rtnval2;
  }
  if (route === "feature-flags") {
    const rtnval2 = FEATURE_FLAGS_TAG;
    return rtnval2;
  }
  if (route === "extensions") {
    const rtnval2 = EXTENSION_REGISTRY_TAG;
    return rtnval2;
  }
  if (route === "system-health") {
    const rtnval2 = SYSTEM_HEALTH_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_admin_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_admin_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_admin_route(route);
  if (target_tag.length === 0) {
    return;
  }
  const main = document.querySelector(
    "pyc-site-shell main.pyc-site-shell__main"
  );
  if (main === null) {
    return;
  }
  const existing = main.querySelector(target_tag);
  if (existing !== null) {
    return;
  }
  define_admin_elements();
  ensure_admin_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against() {
  // The admin palette provider was removed: it queried
  // /api/v1/admin/search, an endpoint that does not exist, so it
  // could never return results. Admin navigation search is now
  // covered by the shell's own navigation provider
  // (pyc-site-shell/palette/navigation-provider.js), which
  // fuzzy-matches the nav manifest's admin entries.
  mount_admin_view_if_active();
  return;
}
function _boot() {
  define_admin_elements();
  const target = window;
  const handle = target.pychestrateShell;
  if (handle !== void 0 && handle.sidebar !== void 0) {
    _register_against();
    return;
  }
  let registered = false;
  const try_register = () => {
    if (registered === true) {
      return true;
    }
    const current = target.pychestrateShell;
    if (current !== void 0 && current.sidebar !== void 0) {
      registered = true;
      _register_against();
      return true;
    }
    return false;
  };
  queueMicrotask(() => {
    try_register();
  });
  if (typeof window.addEventListener === "function") {
    const on_shell_ready = () => {
      if (try_register() === true) {
        window.removeEventListener(
          "pyc-site-shell-ready",
          on_shell_ready
        );
      }
    };
    window.addEventListener("pyc-site-shell-ready", on_shell_ready);
  }
  return;
}
import { PycAdminOverview as PycAdminOverview2 } from "./admin-overview-view.js";
import { PycFeatureFlags as PycFeatureFlags2 } from "./feature-flags-view.js";
import { PycExtensionRegistry as PycExtensionRegistry2 } from "./extension-registry-view.js";
import { PycSystemHealth as PycSystemHealth2 } from "./system-health-view.js";
import {
  fetch_system_health,
  health_status_tone
} from "./system-health-view.js";
import {
  FLAGS_PATH,
  build_flag_url,
  flag_state_tone,
  next_flag_state,
  toggle_message_for_status
} from "./feature-flags-view.js";
import {
  EXT_LISTING_PATH,
  group_routes_by_extension,
  mount_state_tone
} from "./extension-registry-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  EXT_LISTING_PATH,
  FLAGS_PATH,
  PycAdminOverview2 as PycAdminOverview,
  PycExtensionRegistry2 as PycExtensionRegistry,
  PycFeatureFlags2 as PycFeatureFlags,
  PycSystemHealth2 as PycSystemHealth,
  build_flag_url,
  classify_admin_route,
  define_admin_elements,
  ensure_admin_stylesheet,
  fetch_system_health,
  flag_state_tone,
  group_routes_by_extension,
  health_status_tone,
  mount_admin_view_if_active,
  mount_state_tone,
  next_flag_state,
  tag_for_admin_route,
  toggle_message_for_status
};
