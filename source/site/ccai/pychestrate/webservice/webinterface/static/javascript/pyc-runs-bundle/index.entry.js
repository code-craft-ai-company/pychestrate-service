import { PycRunsList } from "./runs-list-view.js";
import { PycRunDetail, run_id_from_path } from "./run-detail-view.js";
const ORCHESTRATION_GROUP_ID = "orchestration";
const RUNS_READ_PERMISSION = "system:runs.read";
const RUNS_ROUTE = "/runs";
const RUNS_LIST_TAG = "pyc-runs-list";
const RUN_DETAIL_TAG = "pyc-run-detail";
const RUNS_STYLESHEET_HREF = "/static/javascript/pyc-runs-bundle/pyc-runs-bundle.css";
function ensure_runs_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-runs-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = RUNS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-runs-bundle");
  document.head.appendChild(link);
  return;
}
const RUNS_ENTRY = {
  entryId: "orchestration.runs",
  label: "Runs",
  route: RUNS_ROUTE,
  requiredPermissions: [RUNS_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_runs_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [RUNS_READ_PERMISSION]
  });
  sidebar.registerEntry(RUNS_ENTRY);
  return;
}
function define_runs_list_element() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(RUNS_LIST_TAG) === void 0) {
    customElements.define(RUNS_LIST_TAG, PycRunsList);
  }
  if (customElements.get(RUN_DETAIL_TAG) === void 0) {
    customElements.define(RUN_DETAIL_TAG, PycRunDetail);
  }
  return;
}
function classify_runs_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === RUNS_ROUTE || working === RUNS_ROUTE + "/") {
    const rtnval2 = "list";
    return rtnval2;
  }
  const detail_id = run_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_runs_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_runs_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main");
  if (main === null) {
    return;
  }
  const target_tag = route === "detail" ? RUN_DETAIL_TAG : RUNS_LIST_TAG;
  const existing = main.querySelector(target_tag);
  if (existing !== null) {
    return;
  }
  define_runs_list_element();
  ensure_runs_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_runs_view_if_active();
  return;
}
function _boot() {
  define_runs_list_element();
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
      "pychestrate.ui.runs.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
import { PycRunsList as PycRunsList2 } from "./runs-list-view.js";
import {
  PycRunDetail as PycRunDetail2,
  run_id_from_path as run_id_from_path2,
  is_valid_run_id,
  is_terminal_state,
  progress_percent,
  manifest_artifacts,
  artifact_url
} from "./run-detail-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  PycRunDetail2 as PycRunDetail,
  PycRunsList2 as PycRunsList,
  artifact_url,
  classify_runs_route,
  define_runs_list_element,
  ensure_runs_stylesheet,
  is_terminal_state,
  is_valid_run_id,
  manifest_artifacts,
  mount_runs_view_if_active,
  progress_percent,
  register_runs_sidebar,
  run_id_from_path2 as run_id_from_path
};
