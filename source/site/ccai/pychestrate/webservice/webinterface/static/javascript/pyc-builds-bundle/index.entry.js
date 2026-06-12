import { PycBuildsList } from "./builds-list-view.js";
import { PycBuildDetail, build_id_from_path } from "./build-detail-view.js";
const ORCHESTRATION_GROUP_ID = "orchestration";
const BUILDS_READ_PERMISSION = "system:builds.read";
const BUILDS_ROUTE = "/builds";
const BUILDS_LIST_TAG = "pyc-builds-list";
const BUILD_DETAIL_TAG = "pyc-build-detail";
const BUILDS_STYLESHEET_HREF = "/static/javascript/pyc-builds-bundle/pyc-builds-bundle.css";
function ensure_builds_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-builds-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = BUILDS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-builds-bundle");
  document.head.appendChild(link);
  return;
}
const BUILDS_ENTRY = {
  entryId: "orchestration.builds",
  label: "Builds",
  route: BUILDS_ROUTE,
  requiredPermissions: [BUILDS_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_builds_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [BUILDS_READ_PERMISSION]
  });
  sidebar.registerEntry(BUILDS_ENTRY);
  return;
}
function define_builds_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(BUILDS_LIST_TAG) === void 0) {
    customElements.define(BUILDS_LIST_TAG, PycBuildsList);
  }
  if (customElements.get(BUILD_DETAIL_TAG) === void 0) {
    customElements.define(BUILD_DETAIL_TAG, PycBuildDetail);
  }
  return;
}
function classify_builds_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === BUILDS_ROUTE || working === BUILDS_ROUTE + "/") {
    const rtnval2 = "list";
    return rtnval2;
  }
  const detail_id = build_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_builds_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_builds_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main");
  if (main === null) {
    return;
  }
  const target_tag = route === "detail" ? BUILD_DETAIL_TAG : BUILDS_LIST_TAG;
  const existing = main.querySelector(target_tag);
  if (existing !== null) {
    return;
  }
  define_builds_elements();
  ensure_builds_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_builds_view_if_active();
  return;
}
function _boot() {
  define_builds_elements();
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
      "pychestrate.ui.builds.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
import { PycBuildsList as PycBuildsList2 } from "./builds-list-view.js";
import {
  build_builds_query_url,
  build_builds_collection_url,
  build_source_integrations_url,
  short_id,
  format_timestamp,
  build_state_tone,
  is_terminal_build_state,
  has_next_page,
  has_previous_page,
  trigger_message_for_status,
  parse_runner_inputs,
  BUILD_STATES,
  TERMINAL_BUILD_STATES
} from "./builds-list-view.js";
import {
  PycBuildDetail as PycBuildDetail2,
  build_id_from_path as build_id_from_path2,
  is_valid_build_id,
  build_detail_url,
  build_artifacts_url
} from "./build-detail-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  BUILD_STATES,
  PycBuildDetail2 as PycBuildDetail,
  PycBuildsList2 as PycBuildsList,
  TERMINAL_BUILD_STATES,
  build_artifacts_url,
  build_builds_collection_url,
  build_builds_query_url,
  build_detail_url,
  build_id_from_path2 as build_id_from_path,
  build_source_integrations_url,
  build_state_tone,
  classify_builds_route,
  define_builds_elements,
  ensure_builds_stylesheet,
  format_timestamp,
  has_next_page,
  has_previous_page,
  is_terminal_build_state,
  is_valid_build_id,
  mount_builds_view_if_active,
  parse_runner_inputs,
  register_builds_sidebar,
  short_id,
  trigger_message_for_status
};
