const SYSTEM_HEALTH_PATH = "/api/v1/system/health";
function health_status_tone(status) {
  if (typeof status !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = status.toLowerCase();
  if (lowered === "ok") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "degraded") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (lowered === "error") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
async function fetch_system_health() {
  let document_body = null;
  try {
    const response = await fetch(SYSTEM_HEALTH_PATH, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    if (response.ok === true) {
      const body = await response.json();
      const parsed = body;
      if (parsed !== null && typeof parsed.status === "string" && Array.isArray(parsed.subsystems) === true) {
        document_body = parsed;
      }
    }
  } catch (reason) {
    console.warn(
      "pychestrate.ui.admin.system_health_fetch_failed",
      { reason: String(reason) }
    );
  }
  const rtnval = document_body;
  return rtnval;
}
class PycSystemHealth extends HTMLElement {
  _document;
  _loading;
  _errored;
  _body_region;
  constructor() {
    super();
    this._document = null;
    this._loading = false;
    this._errored = false;
    this._body_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to read the loading
   * flag without scraping the DOM.
   */
  get loading() {
    const rtnval = this._loading;
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to read the errored
   * flag without scraping the DOM.
   */
  get errored() {
    const rtnval = this._errored;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * system-health fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-admin");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-admin__heading");
    heading.textContent = "System Health";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-admin__controls");
    const refresh_button = document.createElement("button");
    refresh_button.classList.add("pyc-admin__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const body_region = document.createElement("div");
    body_region.classList.add("pyc-admin__cards");
    body_region.setAttribute("data-role", "body-region");
    root.appendChild(body_region);
    this._body_region = body_region;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the system-health document and re-render. Exposed so
   * unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._errored = false;
    this._render_body();
    const document_body = await fetch_system_health();
    if (document_body === null) {
      this._loading = false;
      this._errored = true;
      this._document = null;
      this._render_body();
      return;
    }
    this._document = document_body;
    this._loading = false;
    this._errored = false;
    this._render_body();
    return;
  }
  _render_body() {
    if (this._body_region === null) {
      return;
    }
    const region = this._body_region;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading system health\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._errored === true || this._document === null) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-admin__notice",
        "pyc-admin__notice--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load system health. Try refreshing.";
      region.replaceChildren(error);
      return;
    }
    const children = [];
    const summary = document.createElement("div");
    summary.classList.add("pyc-admin__card");
    summary.setAttribute("data-role", "overall-status");
    const summary_head = document.createElement("div");
    summary_head.classList.add("pyc-admin__card-head");
    const summary_title = document.createElement("p");
    summary_title.classList.add("pyc-admin__card-title");
    summary_title.textContent = "Overall Status";
    const summary_badge = document.createElement("span");
    summary_badge.classList.add("pyc-admin__badge");
    summary_badge.setAttribute(
      "data-tone",
      health_status_tone(this._document.status)
    );
    summary_badge.textContent = this._document.status;
    summary_head.appendChild(summary_title);
    summary_head.appendChild(summary_badge);
    summary.appendChild(summary_head);
    const generated = document.createElement("p");
    generated.classList.add("pyc-admin__card-detail");
    generated.textContent = "Generated " + this._document.generated_at;
    summary.appendChild(generated);
    children.push(summary);
    if (this._document.subsystems.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-admin__notice");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No subsystem probes reported.";
      children.push(empty);
    }
    for (const subsystem of this._document.subsystems) {
      children.push(this._build_subsystem_card(subsystem));
    }
    region.replaceChildren(...children);
    return;
  }
  _build_subsystem_card(subsystem) {
    const card = document.createElement("div");
    card.classList.add("pyc-admin__card");
    card.setAttribute("data-role", "subsystem-card");
    card.setAttribute("data-subsystem", subsystem.name);
    const head = document.createElement("div");
    head.classList.add("pyc-admin__card-head");
    const title = document.createElement("p");
    title.classList.add("pyc-admin__card-title");
    title.textContent = subsystem.label;
    const badge = document.createElement("span");
    badge.classList.add("pyc-admin__badge");
    badge.setAttribute(
      "data-tone",
      health_status_tone(subsystem.status)
    );
    badge.textContent = subsystem.status;
    head.appendChild(title);
    head.appendChild(badge);
    card.appendChild(head);
    const detail = document.createElement("p");
    detail.classList.add("pyc-admin__card-detail");
    detail.textContent = subsystem.detail;
    card.appendChild(detail);
    const backends = subsystem.backends;
    if (backends !== void 0 && backends.length > 0) {
      const table = document.createElement("table");
      table.classList.add("pyc-admin__table");
      const thead = document.createElement("thead");
      const head_row = document.createElement("tr");
      for (const column of ["Backend", "Status", "Reason"]) {
        const th = document.createElement("th");
        th.scope = "col";
        th.textContent = column;
        head_row.appendChild(th);
      }
      thead.appendChild(head_row);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      for (const backend of backends) {
        const row = document.createElement("tr");
        const name_cell = document.createElement("td");
        name_cell.textContent = backend.name;
        row.appendChild(name_cell);
        const status_cell = document.createElement("td");
        const status_badge = document.createElement("span");
        status_badge.classList.add("pyc-admin__badge");
        status_badge.setAttribute(
          "data-tone",
          health_status_tone(backend.status)
        );
        status_badge.textContent = backend.status;
        status_cell.appendChild(status_badge);
        row.appendChild(status_cell);
        const reason_cell = document.createElement("td");
        reason_cell.textContent = backend.reason.length > 0 ? backend.reason : "\u2014";
        row.appendChild(reason_cell);
        tbody.appendChild(row);
      }
      table.appendChild(tbody);
      card.appendChild(table);
    }
    return card;
  }
}
export {
  PycSystemHealth,
  SYSTEM_HEALTH_PATH,
  fetch_system_health,
  health_status_tone
};
