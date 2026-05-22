import { PycSecrets } from "./secrets-view.js";
const SYSTEM_GROUP_ID = "system";
const SECRETS_READ_PERMISSION = "system:secrets.read";
const SECRETS_ROUTE = "/secrets";
const SECRETS_TAG = "pyc-secrets";
const SECRETS_STYLESHEET_HREF = "/static/javascript/pyc-secrets-bundle/pyc-secrets-bundle.css";
function ensure_secrets_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-secrets-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = SECRETS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-secrets-bundle");
  document.head.appendChild(link);
  return;
}
const SECRETS_ENTRY = {
  entryId: "system.secrets",
  label: "Secrets",
  route: SECRETS_ROUTE,
  requiredPermissions: [SECRETS_READ_PERMISSION],
  group: SYSTEM_GROUP_ID
};
function register_secrets_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: SYSTEM_GROUP_ID,
    label: "System",
    requiredPermissions: [SECRETS_READ_PERMISSION]
  });
  sidebar.registerEntry(SECRETS_ENTRY);
  return;
}
function define_secrets_element() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(SECRETS_TAG) === void 0) {
    customElements.define(SECRETS_TAG, PycSecrets);
  }
  return;
}
function classify_secrets_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === SECRETS_ROUTE || working === SECRETS_ROUTE + "/") {
    const rtnval2 = "view";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_secrets_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_secrets_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main");
  if (main === null) {
    return;
  }
  const existing = main.querySelector(SECRETS_TAG);
  if (existing !== null) {
    return;
  }
  define_secrets_element();
  ensure_secrets_stylesheet();
  const view = document.createElement(SECRETS_TAG);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_secrets_view_if_active();
  return;
}
function _boot() {
  define_secrets_element();
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
      "pychestrate.ui.secrets.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
import { PycSecrets as PycSecrets2 } from "./secrets-view.js";
import {
  SECRET_SCOPE_KINDS,
  build_secrets_list_url,
  build_secret_value_url,
  build_secret_resource_url,
  format_timestamp,
  reveal_error_message
} from "./secrets-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  PycSecrets2 as PycSecrets,
  SECRET_SCOPE_KINDS,
  build_secret_resource_url,
  build_secret_value_url,
  build_secrets_list_url,
  classify_secrets_route,
  define_secrets_element,
  ensure_secrets_stylesheet,
  format_timestamp,
  mount_secrets_view_if_active,
  register_secrets_sidebar,
  reveal_error_message
};
