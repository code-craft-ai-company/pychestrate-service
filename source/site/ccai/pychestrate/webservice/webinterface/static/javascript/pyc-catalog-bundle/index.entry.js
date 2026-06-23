import { PycTestCatalog } from "./catalog-view.js";
const ORCHESTRATION_GROUP_ID = "orchestration";
const CATALOG_READ_PERMISSION = "system:test_catalog.read";
const CATALOG_ROUTE = "/test-catalog";
const CATALOG_TAG = "pyc-test-catalog";
const CATALOG_STYLESHEET_HREF = "/static/javascript/pyc-catalog-bundle/pyc-catalog-bundle.css";
function ensure_catalog_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-catalog-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = CATALOG_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-catalog-bundle");
  document.head.appendChild(link);
  return;
}
const CATALOG_ENTRY = {
  entryId: "orchestration.test-catalog",
  label: "Test Catalog",
  route: CATALOG_ROUTE,
  requiredPermissions: [CATALOG_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_catalog_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [CATALOG_READ_PERMISSION]
  });
  sidebar.registerEntry(CATALOG_ENTRY);
  return;
}
function define_catalog_element() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(CATALOG_TAG) === void 0) {
    customElements.define(CATALOG_TAG, PycTestCatalog);
  }
  return;
}
function classify_catalog_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === CATALOG_ROUTE || working === CATALOG_ROUTE + "/") {
    const rtnval2 = "catalog";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_catalog_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_catalog_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector(
    "pyc-site-shell main.pyc-site-shell__main"
  );
  if (main === null) {
    return;
  }
  const existing = main.querySelector(CATALOG_TAG);
  if (existing !== null) {
    return;
  }
  define_catalog_element();
  ensure_catalog_stylesheet();
  const view = document.createElement(CATALOG_TAG);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_catalog_view_if_active();
  return;
}
function _boot() {
  define_catalog_element();
  const target = window;
  const handle = target.pychestrateShell;
  if (handle !== void 0 && handle.sidebar !== void 0) {
    _register_against(handle);
    return;
  }
  queueMicrotask(() => {
    const retry = target.pychestrateShell;
    if (retry !== void 0 && retry.sidebar !== void 0) {
      _register_against(retry);
      return;
    }
    console.warn(
      "pychestrate.ui.catalog.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
import { PycTestCatalog as PycTestCatalog2 } from "./catalog-view.js";
import {
  build_catalog_query_url,
  build_test_runs_url,
  build_catalog_import_url,
  selection_summary,
  format_timestamp,
  has_next_page,
  has_previous_page,
  trigger_message_for_status
} from "./catalog-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  PycTestCatalog2 as PycTestCatalog,
  build_catalog_import_url,
  build_catalog_query_url,
  build_test_runs_url,
  classify_catalog_route,
  define_catalog_element,
  ensure_catalog_stylesheet,
  format_timestamp,
  has_next_page,
  has_previous_page,
  mount_catalog_view_if_active,
  register_catalog_sidebar,
  selection_summary,
  trigger_message_for_status
};
