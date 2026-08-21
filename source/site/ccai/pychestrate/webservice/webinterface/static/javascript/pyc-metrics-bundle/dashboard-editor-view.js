import {
  build_catalog_url,
  extract_catalog
} from "./timeseries-view.js";
import {
  extract_projects
} from "./test-metrics-view.js";
import {
  build_dashboard_detail_url,
  DASHBOARDS_ROUTE
} from "./dashboards-view.js";
const PROJECTS_API_PATH = "/api/v1/projects";
const TILE_KIND_OPTIONS = [
  { value: "line", label: "Line chart" },
  { value: "bar", label: "Bar chart" },
  { value: "number", label: "Single number" }
];
function dashboard_id_from_edit_path(path) {
  if (typeof path !== "string") {
    const rtnval2 = "";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  const prefix = DASHBOARDS_ROUTE + "/";
  const suffix = "/edit";
  if (working.startsWith(prefix) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  if (working.endsWith(suffix) === false) {
    const rtnval2 = "";
    return rtnval2;
  }
  const middle = working.slice(prefix.length, working.length - suffix.length);
  if (middle.length === 0 || middle.indexOf("/") >= 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = decodeURIComponent(middle);
  return rtnval;
}
function is_dashboard_edit_path(path) {
  const rtnval = dashboard_id_from_edit_path(path).length > 0;
  return rtnval;
}
function generate_tile_id() {
  const stamp = Date.now().toString(36);
  const rand = Math.floor(Math.random() * 1e6).toString(36);
  const rtnval = "tile-" + stamp + "-" + rand;
  return rtnval;
}
function build_tile(metric, kind, index) {
  const rtnval = {
    tile_id: generate_tile_id(),
    kind,
    x: 0,
    y: index,
    w: 1,
    h: 1,
    config: { metric }
  };
  return rtnval;
}
function add_tile(tiles, metric, kind) {
  const rtnval = tiles.slice();
  rtnval.push(build_tile(metric, kind, rtnval.length));
  return reindex_tiles(rtnval);
}
function remove_tile(tiles, tile_id) {
  const filtered = [];
  for (const tile of tiles) {
    if (tile.tile_id !== tile_id) {
      filtered.push(tile);
    }
  }
  const rtnval = reindex_tiles(filtered);
  return rtnval;
}
function move_tile_up(tiles, index) {
  const working = tiles.slice();
  if (index <= 0 || index >= working.length) {
    const rtnval2 = reindex_tiles(working);
    return rtnval2;
  }
  const above = working[index - 1];
  const current = working[index];
  working[index - 1] = current;
  working[index] = above;
  const rtnval = reindex_tiles(working);
  return rtnval;
}
function move_tile_down(tiles, index) {
  const working = tiles.slice();
  if (index < 0 || index >= working.length - 1) {
    const rtnval2 = reindex_tiles(working);
    return rtnval2;
  }
  const below = working[index + 1];
  const current = working[index];
  working[index + 1] = current;
  working[index] = below;
  const rtnval = reindex_tiles(working);
  return rtnval;
}
function reindex_tiles(tiles) {
  const rtnval = [];
  let index = 0;
  for (const tile of tiles) {
    const next = {
      tile_id: tile.tile_id,
      kind: tile.kind,
      x: 0,
      y: index,
      w: tile.w,
      h: tile.h
    };
    if (tile.config !== void 0) {
      next.config = tile.config;
    }
    rtnval.push(next);
    index = index + 1;
  }
  return rtnval;
}
function editor_tile_metric(tile) {
  if (tile === null || tile === void 0) {
    const rtnval2 = "";
    return rtnval2;
  }
  const config = tile.config;
  if (config === null || config === void 0 || typeof config !== "object") {
    const rtnval2 = "";
    return rtnval2;
  }
  const metric = config.metric;
  if (typeof metric !== "string") {
    const rtnval2 = "";
    return rtnval2;
  }
  const rtnval = metric;
  return rtnval;
}
function build_save_payload(dashboard, tiles) {
  const reindexed = reindex_tiles(tiles);
  const tile_payload = [];
  for (const tile of reindexed) {
    const entry = {
      tile_id: tile.tile_id,
      kind: tile.kind,
      x: tile.x,
      y: tile.y,
      w: tile.w,
      h: tile.h,
      config: tile.config !== void 0 ? tile.config : {}
    };
    tile_payload.push(entry);
  }
  const rtnval = {
    tiles: tile_payload
  };
  if (typeof dashboard.version === "number") {
    rtnval.expected_version = dashboard.version;
  }
  return rtnval;
}
function save_message_for_status(status) {
  if (status === 200 || status === 201) {
    const rtnval2 = "Dashboard saved.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "This dashboard changed since you loaded it \u2014 reload the editor and try again.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The layout was rejected \u2014 check the tiles.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to edit dashboards.";
    return rtnval2;
  }
  if (status === 404) {
    const rtnval2 = "This dashboard no longer exists.";
    return rtnval2;
  }
  if (status === 401) {
    const rtnval2 = "Your session has expired \u2014 sign in again to save.";
    return rtnval2;
  }
  const rtnval = "Failed to save layout (HTTP " + String(status) + ").";
  return rtnval;
}
class PycDashboardEditor extends HTMLElement {
  _projects;
  _projectId;
  _dashboard;
  _tiles;
  _catalog;
  _loading;
  _errored;
  _root;
  _grid_region;
  _add_region;
  _toast_region;
  constructor() {
    super();
    this._projects = [];
    this._projectId = "";
    this._dashboard = null;
    this._tiles = [];
    this._catalog = [];
    this._loading = false;
    this._errored = false;
    this._root = null;
    this._grid_region = null;
    this._add_region = null;
    this._toast_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests -- the current tile
   * list (a defensive copy).
   */
  get tiles() {
    const rtnval = this._tiles.slice();
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests -- ``true`` once the
   * dashboard has loaded.
   */
  get loaded() {
    const rtnval = this._dashboard !== null;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the chrome, fetch the catalog and
   * the dashboard.
   */
  connectedCallback() {
    this._render_chrome();
    void this._load_catalog();
    void this._load_dashboard();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-metrics");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-metrics__heading");
    heading.setAttribute("data-role", "editor-heading");
    heading.textContent = "Edit Dashboard Layout";
    root.appendChild(heading);
    const back = document.createElement("a");
    back.classList.add("pyc-metrics__row-link");
    back.setAttribute("data-role", "back-link");
    back.setAttribute("href", DASHBOARDS_ROUTE);
    back.textContent = "\u2190 All dashboards";
    root.appendChild(back);
    const add_region = document.createElement("div");
    add_region.classList.add("pyc-metrics__form-region");
    add_region.setAttribute("data-role", "add-region");
    root.appendChild(add_region);
    this._add_region = add_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-metrics__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const grid_region = document.createElement("div");
    grid_region.classList.add("pyc-metrics__tiles-region");
    grid_region.setAttribute("data-role", "grid-region");
    root.appendChild(grid_region);
    this._grid_region = grid_region;
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the metric catalog so the add-tile form can offer a
   * metric picker. Exposed so unit tests can await the fetch.
   */
  async loadCatalog() {
    await this._load_catalog();
    return;
  }
  async _load_catalog() {
    let catalog = [];
    try {
      const response = await fetch(build_catalog_url(), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        catalog = extract_catalog(body);
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.editor_catalog_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._catalog = catalog;
    this._render_add_region();
    return;
  }
  /**
   * Resolve the dashboard project + id, fetch the dashboard, and
   * render its tiles. Exposed so unit tests can await the cycle.
   */
  async loadDashboard() {
    await this._load_dashboard();
    return;
  }
  async _load_dashboard() {
    const dashboard_id = dashboard_id_from_edit_path(
      typeof window !== "undefined" ? window.location.pathname : ""
    );
    if (dashboard_id.length === 0) {
      this._errored = true;
      this._render_grid();
      return;
    }
    let project_id = "";
    try {
      const response = await fetch(PROJECTS_API_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        this._projects = extract_projects(body);
        if (this._projects.length > 0) {
          project_id = this._projects[0].project_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.editor_projects_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (project_id.length === 0) {
      this._errored = true;
      this._render_grid();
      return;
    }
    this._projectId = project_id;
    this._loading = true;
    this._render_grid();
    let dashboard = null;
    let errored = false;
    try {
      const url = build_dashboard_detail_url(project_id, dashboard_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        dashboard = body;
      } else {
        errored = true;
      }
    } catch (reason) {
      errored = true;
      console.warn(
        "pychestrate.ui.metrics.editor_dashboard_fetch_failed",
        { reason: String(reason) }
      );
    }
    this._loading = false;
    this._errored = errored;
    this._dashboard = dashboard;
    if (dashboard !== null && Array.isArray(dashboard.tiles) === true) {
      this._tiles = reindex_tiles(dashboard.tiles);
    } else {
      this._tiles = [];
    }
    this._render_grid();
    this._render_add_region();
    return;
  }
  /**
   * Append a tile referencing ``metric`` with ``kind``. Exposed
   * so unit tests can drive the add path directly.
   *
   * @param metric The metric the new tile renders.
   * @param kind The new tile's kind.
   */
  addTile(metric, kind) {
    this._tiles = add_tile(this._tiles, metric, kind);
    this._render_grid();
    return;
  }
  /**
   * Remove the named tile. Exposed so unit tests can drive the
   * remove path directly.
   *
   * @param tile_id The tile to remove.
   */
  removeTile(tile_id) {
    this._tiles = remove_tile(this._tiles, tile_id);
    this._render_grid();
    return;
  }
  /**
   * Move the tile at ``index`` one slot earlier. Exposed so unit
   * tests can drive the reorder path directly.
   *
   * @param index The 0-based index of the tile to move up.
   */
  moveUp(index) {
    this._tiles = move_tile_up(this._tiles, index);
    this._render_grid();
    return;
  }
  /**
   * Move the tile at ``index`` one slot later. Exposed so unit
   * tests can drive the reorder path directly.
   *
   * @param index The 0-based index of the tile to move down.
   */
  moveDown(index) {
    this._tiles = move_tile_down(this._tiles, index);
    this._render_grid();
    return;
  }
  _render_add_region() {
    if (this._add_region === null) {
      return;
    }
    const region = this._add_region;
    region.replaceChildren();
    if (this._dashboard === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-metrics__form");
    form.setAttribute("data-role", "add-tile-form");
    const metric_label = document.createElement("label");
    metric_label.classList.add("pyc-metrics__field");
    metric_label.textContent = "Metric";
    const metric_select = document.createElement("mj-select");
    metric_select.classList.add("pyc-metrics__select");
    metric_select.setAttribute("data-role", "add-metric");
    if (this._catalog.length === 0) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", "");
      option.textContent = "No metrics in catalog";
      metric_select.appendChild(option);
    } else {
      for (const entry of this._catalog) {
        const option = document.createElement("mj-option");
        option.setAttribute("value", entry.name);
        option.textContent = entry.name;
        metric_select.appendChild(option);
      }
    }
    metric_label.appendChild(metric_select);
    form.appendChild(metric_label);
    const kind_label = document.createElement("label");
    kind_label.classList.add("pyc-metrics__field");
    kind_label.textContent = "Tile kind";
    const kind_select = document.createElement("mj-select");
    kind_select.classList.add("pyc-metrics__select");
    kind_select.setAttribute("data-role", "add-kind");
    for (const option of TILE_KIND_OPTIONS) {
      const opt = document.createElement("mj-option");
      opt.setAttribute("value", option.value);
      opt.textContent = option.label;
      kind_select.appendChild(opt);
    }
    kind_label.appendChild(kind_select);
    form.appendChild(kind_label);
    const add_button = document.createElement("mj-button");
    add_button.classList.add("pyc-metrics__button");
    add_button.setAttribute("type", "submit");
    add_button.setAttribute("data-role", "add-tile");
    add_button.textContent = "Add Tile";
    form.appendChild(add_button);
    const save_button = document.createElement("mj-button");
    save_button.classList.add("pyc-metrics__button");
    save_button.setAttribute("type", "button");
    save_button.setAttribute("data-role", "save-layout");
    save_button.textContent = "Save Layout";
    save_button.addEventListener("click", () => {
      save_button.toggleAttribute("disabled", true);
      void this._on_save(save_button);
    });
    form.appendChild(save_button);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const metric = metric_select.value.trim();
      if (metric.length === 0) {
        this._show_toast("Select a metric to add a tile.", "error");
        return;
      }
      this.addTile(metric, kind_select.value);
    });
    region.appendChild(form);
    return;
  }
  _render_grid() {
    if (this._grid_region === null || this._root === null) {
      return;
    }
    const heading = this._root.querySelector(
      '[data-role="editor-heading"]'
    );
    if (heading !== null && this._dashboard !== null) {
      heading.textContent = "Edit Layout \u2014 " + this._dashboard.name;
    }
    const region = this._grid_region;
    region.replaceChildren();
    if (this._loading === true) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "loading-state");
      notice.textContent = "Loading dashboard\u2026";
      region.appendChild(notice);
      return;
    }
    if (this._errored === true || this._dashboard === null) {
      const notice = document.createElement("p");
      notice.classList.add(
        "pyc-metrics__notice",
        "pyc-metrics__notice--error"
      );
      notice.setAttribute("data-role", "error-state");
      notice.textContent = "Failed to load this dashboard.";
      region.appendChild(notice);
      return;
    }
    if (this._tiles.length === 0) {
      const notice = document.createElement("p");
      notice.classList.add("pyc-metrics__notice");
      notice.setAttribute("data-role", "empty-state");
      notice.textContent = "No tiles yet \u2014 add one above.";
      region.appendChild(notice);
      return;
    }
    const grid = document.createElement("div");
    grid.classList.add("pyc-metrics__tiles");
    grid.setAttribute("data-role", "tiles-grid");
    let index = 0;
    for (const tile of this._tiles) {
      grid.appendChild(this._build_tile_card(tile, index));
      index = index + 1;
    }
    region.appendChild(grid);
    return;
  }
  _build_tile_card(tile, index) {
    const card = document.createElement("div");
    card.classList.add("pyc-metrics__tile");
    card.setAttribute("data-role", "editor-tile");
    card.setAttribute("data-tile-id", tile.tile_id);
    const title = document.createElement("div");
    title.classList.add("pyc-metrics__tile-title");
    const metric = editor_tile_metric(tile);
    title.textContent = (metric.length > 0 ? metric : "(no metric)") + " \xB7 " + tile.kind;
    card.appendChild(title);
    const actions = document.createElement("div");
    actions.classList.add("pyc-metrics__tile-actions");
    const up_button = document.createElement("mj-button");
    up_button.classList.add("pyc-metrics__button");
    up_button.setAttribute("type", "button");
    up_button.setAttribute("data-role", "tile-up");
    up_button.setAttribute("aria-label", "Move tile up");
    up_button.textContent = "\u2191";
    up_button.toggleAttribute("disabled", index === 0);
    up_button.addEventListener("click", () => {
      this.moveUp(index);
    });
    actions.appendChild(up_button);
    const down_button = document.createElement("mj-button");
    down_button.classList.add("pyc-metrics__button");
    down_button.setAttribute("type", "button");
    down_button.setAttribute("data-role", "tile-down");
    down_button.setAttribute("aria-label", "Move tile down");
    down_button.textContent = "\u2193";
    down_button.toggleAttribute("disabled", index === this._tiles.length - 1);
    down_button.addEventListener("click", () => {
      this.moveDown(index);
    });
    actions.appendChild(down_button);
    const remove_button = document.createElement("mj-button");
    remove_button.classList.add("pyc-metrics__button");
    remove_button.setAttribute("type", "button");
    remove_button.setAttribute("data-role", "tile-remove");
    remove_button.setAttribute("aria-label", "Remove tile");
    remove_button.textContent = "Remove";
    remove_button.addEventListener("click", () => {
      this.removeTile(tile.tile_id);
    });
    actions.appendChild(remove_button);
    card.appendChild(actions);
    return card;
  }
  async _on_save(button) {
    const outcome = await this._do_save();
    button.toggleAttribute("disabled", false);
    this._show_toast(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true && outcome.dashboardId.length > 0) {
      const link = document.createElement("a");
      link.classList.add("pyc-metrics__row-link");
      link.setAttribute(
        "href",
        DASHBOARDS_ROUTE + "/" + encodeURIComponent(outcome.dashboardId)
      );
      link.textContent = "Open the saved dashboard \u2192";
      if (this._toast_region !== null) {
        this._toast_region.appendChild(link);
      }
    }
    return;
  }
  /**
   * Save the current layout in place via a PATCH to the
   * dashboard's detail URL. Exposed so unit tests can drive the
   * save path directly.
   *
   * @returns The save outcome.
   */
  async saveLayout() {
    const rtnval = await this._do_save();
    return rtnval;
  }
  async _do_save() {
    if (this._dashboard === null || this._projectId.length === 0) {
      const rtnval2 = {
        ok: false,
        status: 0,
        dashboardId: "",
        message: "Load a dashboard before saving its layout."
      };
      return rtnval2;
    }
    const payload = build_save_payload(this._dashboard, this._tiles);
    let status = 0;
    let dashboard_id = "";
    try {
      const url = build_dashboard_detail_url(
        this._projectId,
        this._dashboard.dashboard_id
      );
      const response = await fetch(url, {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        const record = body;
        if (typeof record.dashboard_id === "string") {
          dashboard_id = record.dashboard_id;
        }
        if (typeof record.version === "number") {
          this._dashboard.version = record.version;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.metrics.dashboard_save_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        dashboardId: "",
        message: "Failed to reach the dashboards service."
      };
      return rtnval2;
    }
    const ok = status === 200 || status === 201;
    const rtnval = {
      ok,
      status,
      dashboardId: dashboard_id,
      message: save_message_for_status(status)
    };
    return rtnval;
  }
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-metrics__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-metrics__toast-dismiss");
    dismiss.setAttribute("type", "button");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "\xD7";
    dismiss.addEventListener("click", () => {
      toast.remove();
    });
    toast.appendChild(dismiss);
    this._toast_region.replaceChildren(toast);
    return;
  }
}
export {
  PycDashboardEditor,
  TILE_KIND_OPTIONS,
  add_tile,
  build_save_payload,
  build_tile,
  dashboard_id_from_edit_path,
  editor_tile_metric,
  generate_tile_id,
  is_dashboard_edit_path,
  move_tile_down,
  move_tile_up,
  reindex_tiles,
  remove_tile,
  save_message_for_status
};
