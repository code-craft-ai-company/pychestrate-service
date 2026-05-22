import { PycPipelinesList } from "./pipelines-list-view.js";
import { PycPipelineDetail, pipeline_id_from_path } from "./pipeline-detail-view.js";
const ORCHESTRATION_GROUP_ID = "orchestration";
const PIPELINES_READ_PERMISSION = "system:pipelines.read";
const PIPELINES_ROUTE = "/pipelines";
const PIPELINES_LIST_TAG = "pyc-pipelines-list";
const PIPELINE_DETAIL_TAG = "pyc-pipeline-detail";
const PIPELINES_STYLESHEET_HREF = "/static/javascript/pyc-pipelines-bundle/pyc-pipelines-bundle.css";
function ensure_pipelines_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-pipelines-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = PIPELINES_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-pipelines-bundle");
  document.head.appendChild(link);
  return;
}
const PIPELINES_ENTRY = {
  entryId: "orchestration.pipelines",
  label: "Pipelines",
  route: PIPELINES_ROUTE,
  requiredPermissions: [PIPELINES_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_pipelines_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [PIPELINES_READ_PERMISSION]
  });
  sidebar.registerEntry(PIPELINES_ENTRY);
  return;
}
function define_pipelines_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(PIPELINES_LIST_TAG) === void 0) {
    customElements.define(PIPELINES_LIST_TAG, PycPipelinesList);
  }
  if (customElements.get(PIPELINE_DETAIL_TAG) === void 0) {
    customElements.define(PIPELINE_DETAIL_TAG, PycPipelineDetail);
  }
  return;
}
function classify_pipelines_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === PIPELINES_ROUTE || working === PIPELINES_ROUTE + "/") {
    const rtnval2 = "list";
    return rtnval2;
  }
  const detail_id = pipeline_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function mount_pipelines_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_pipelines_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main");
  if (main === null) {
    return;
  }
  const target_tag = route === "detail" ? PIPELINE_DETAIL_TAG : PIPELINES_LIST_TAG;
  const existing = main.querySelector(target_tag);
  if (existing !== null) {
    return;
  }
  define_pipelines_elements();
  ensure_pipelines_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_pipelines_view_if_active();
  return;
}
function _boot() {
  define_pipelines_elements();
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
      "pychestrate.ui.pipelines.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
import { PycPipelinesList as PycPipelinesList2 } from "./pipelines-list-view.js";
import {
  build_pipelines_query_url,
  build_pipelines_collection_url,
  build_pipelines_validate_url,
  build_pipelines_expand_matrix_url,
  short_id,
  format_timestamp,
  has_next_page,
  has_previous_page,
  parse_matrix_spec,
  validate_message_for_status
} from "./pipelines-list-view.js";
import {
  PycPipelineDetail as PycPipelineDetail2,
  pipeline_id_from_path as pipeline_id_from_path2,
  pipeline_detail_url,
  compute_dag_columns,
  compute_dag_layout
} from "./pipeline-detail-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  PycPipelineDetail2 as PycPipelineDetail,
  PycPipelinesList2 as PycPipelinesList,
  build_pipelines_collection_url,
  build_pipelines_expand_matrix_url,
  build_pipelines_query_url,
  build_pipelines_validate_url,
  classify_pipelines_route,
  compute_dag_columns,
  compute_dag_layout,
  define_pipelines_elements,
  ensure_pipelines_stylesheet,
  format_timestamp,
  has_next_page,
  has_previous_page,
  mount_pipelines_view_if_active,
  parse_matrix_spec,
  pipeline_detail_url,
  pipeline_id_from_path2 as pipeline_id_from_path,
  register_pipelines_sidebar,
  short_id,
  validate_message_for_status
};
