const PALETTE_INPUT_DEBOUNCE_MS = 80;
class PaletteDialog {
  _registry;
  _host;
  _container;
  _input;
  _results_region;
  _status_region;
  _is_open;
  _previous_focus;
  _debounce_handle;
  _query_token;
  _flat_results;
  _active_index;
  constructor(registry, host) {
    this._registry = registry;
    this._host = host;
    this._container = null;
    this._input = null;
    this._results_region = null;
    this._status_region = null;
    this._is_open = false;
    this._previous_focus = null;
    this._debounce_handle = null;
    this._query_token = 0;
    this._flat_results = [];
    this._active_index = -1;
  }
  get isOpen() {
    const rtnval = this._is_open;
    return rtnval;
  }
  /**
   * Open the palette. No-op when already open. Builds the DOM
   * on first open and attaches it to ``document.body``.
   *
   * @param mount_target Optional override for the parent
   *                     element the dialog attaches to. Falls
   *                     back to ``document.body``.
   */
  open(mount_target = null) {
    if (this._is_open === true) {
      return;
    }
    if (this._container === null) {
      this._build_dom();
    }
    const container = this._container;
    if (container === null) {
      return;
    }
    const parent = mount_target !== null ? mount_target : document.body;
    parent.appendChild(container);
    this._is_open = true;
    this._previous_focus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (this._input !== null) {
      this._input.value = "";
      this._input.focus();
    }
    this._render_status("Search pages, projects and actions, or paste a run or build id.");
    this._host.emit("pyc-site-shell-palette-opened", {});
    if (typeof this._host.observePaletteOpened === "function") {
      this._host.observePaletteOpened();
    }
    return;
  }
  /**
   * Close the palette and restore focus to the previously
   * focused element. No-op when already closed.
   */
  close() {
    if (this._is_open === false) {
      return;
    }
    const container = this._container;
    if (container !== null && container.parentNode !== null) {
      container.parentNode.removeChild(container);
    }
    this._is_open = false;
    if (this._debounce_handle !== null) {
      clearTimeout(this._debounce_handle);
      this._debounce_handle = null;
    }
    this._flat_results = [];
    this._active_index = -1;
    const restore_target = this._previous_focus;
    this._previous_focus = null;
    if (restore_target !== null && typeof restore_target.focus === "function") {
      restore_target.focus();
    }
    this._host.emit("pyc-site-shell-palette-closed", {});
    return;
  }
  _build_dom() {
    const container = document.createElement("div");
    container.classList.add("pyc-site-shell__palette-backdrop");
    container.setAttribute("role", "presentation");
    const dialog = document.createElement("div");
    dialog.classList.add("pyc-site-shell__palette-dialog");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Command Palette");
    dialog.tabIndex = -1;
    const input = document.createElement("input");
    input.type = "search";
    input.classList.add("pyc-site-shell__palette-input");
    input.setAttribute("aria-label", "Search pages, projects and actions");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", "pyc-palette-results");
    input.setAttribute("spellcheck", "false");
    input.placeholder = "Type to search...";
    input.addEventListener("input", () => {
      this._on_input_changed();
    });
    dialog.appendChild(input);
    const status = document.createElement("div");
    status.classList.add("pyc-site-shell__palette-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    dialog.appendChild(status);
    const results = document.createElement("div");
    results.classList.add("pyc-site-shell__palette-results");
    results.setAttribute("role", "listbox");
    results.id = "pyc-palette-results";
    results.setAttribute("aria-label", "Search results");
    dialog.appendChild(results);
    dialog.addEventListener("keydown", (event) => {
      this._on_dialog_keydown(event);
    });
    container.addEventListener("mousedown", (event) => {
      if (event.target === container) {
        this.close();
      }
    });
    container.appendChild(dialog);
    this._container = container;
    this._input = input;
    this._status_region = status;
    this._results_region = results;
    return;
  }
  _on_input_changed() {
    if (this._debounce_handle !== null) {
      clearTimeout(this._debounce_handle);
    }
    this._debounce_handle = setTimeout(() => {
      this._debounce_handle = null;
      void this._run_query();
    }, PALETTE_INPUT_DEBOUNCE_MS);
    return;
  }
  async _run_query() {
    if (this._input === null || this._results_region === null) {
      return;
    }
    const raw_query = this._input.value;
    this._query_token = this._query_token + 1;
    const token = this._query_token;
    if (raw_query.trim().length === 0) {
      this._results_region.replaceChildren();
      this._flat_results = [];
      this._active_index = -1;
      this._render_status(
        "Search pages, projects and actions, or paste a run or build id."
      );
      return;
    }
    const perms = this._host.getPermissions();
    const visible_providers = this._registry.visibleProviders(perms);
    if (visible_providers.length === 0) {
      this._results_region.replaceChildren();
      this._flat_results = [];
      this._active_index = -1;
      this._render_status("Navigation search is unavailable for your account.");
      return;
    }
    this._render_status("Searching...");
    const fanout_started = typeof performance !== "undefined" ? performance.now() : 0;
    const outcomes = await this._registry.queryAll(raw_query, perms);
    const fanout_finished = typeof performance !== "undefined" ? performance.now() : 0;
    if (typeof this._host.observePaletteFanout === "function") {
      this._host.observePaletteFanout(
        (fanout_finished - fanout_started) / 1e3
      );
    }
    if (token !== this._query_token) {
      return;
    }
    this._render_outcomes(outcomes);
    return;
  }
  _render_outcomes(outcomes) {
    if (this._results_region === null) {
      return;
    }
    this._results_region.replaceChildren();
    this._flat_results = [];
    let total_results = 0;
    // With several sources, one that matched nothing is not worth a heading and a
    // "No matches" of its own while another has results (XC-17).
    const any_results = outcomes.some((outcome) => outcome.error === null && outcome.results.length > 0);
    const any_error = outcomes.some((outcome) => outcome.error !== null);
    if (any_results === false && any_error === false) {
      // Nothing matched anywhere: one line, not a heading and "No matches" per source.
      this._active_index = -1;
      if (this._input !== null) {
        this._input.setAttribute("aria-expanded", "false");
        this._input.removeAttribute("aria-activedescendant");
      }
      this._render_status("No results.");
      return;
    }
    for (const outcome of outcomes) {
      if (any_results === true && outcome.error === null && outcome.results.length === 0) {
        continue;
      }
      const section = document.createElement("div");
      section.classList.add("pyc-site-shell__palette-group");
      section.setAttribute("role", "group");
      section.setAttribute("aria-label", outcome.providerLabel);
      const heading = document.createElement("div");
      heading.classList.add("pyc-site-shell__palette-group-label");
      heading.setAttribute("role", "presentation");
      heading.textContent = outcome.providerLabel;
      section.appendChild(heading);
      if (outcome.error !== null) {
        const notice = document.createElement("div");
        notice.classList.add("pyc-site-shell__palette-provider-error");
        notice.setAttribute("role", "presentation");
        notice.textContent = "This source is unavailable right now.";
        section.appendChild(notice);
        this._results_region.appendChild(section);
        continue;
      }
      if (outcome.results.length === 0) {
        const empty = document.createElement("div");
        empty.classList.add("pyc-site-shell__palette-empty");
        empty.textContent = "No matches.";
        section.appendChild(empty);
        this._results_region.appendChild(section);
        continue;
      }
      for (const result of outcome.results) {
        const option = document.createElement("div");
        option.classList.add("pyc-site-shell__palette-option");
        option.setAttribute("role", "option");
        option.setAttribute("data-provider-id", outcome.providerId);
        option.setAttribute("data-result-id", result.id);
        option.id = "pyc-palette-option-" + String(total_results);
        option.tabIndex = -1;
        const label = document.createElement("div");
        label.classList.add("pyc-site-shell__palette-option-label");
        label.textContent = result.label;
        option.appendChild(label);
        if (typeof result.description === "string" && result.description.length > 0) {
          const desc = document.createElement("div");
          desc.classList.add(
            "pyc-site-shell__palette-option-description"
          );
          desc.textContent = result.description;
          option.appendChild(desc);
        }
        option.addEventListener("click", () => {
          void this._activate_result(result);
        });
        section.appendChild(option);
        this._flat_results.push({
          providerId: outcome.providerId,
          result,
          element: option
        });
        total_results = total_results + 1;
      }
      this._results_region.appendChild(section);
    }
    this._active_index = this._flat_results.length > 0 ? 0 : -1;
    if (this._input !== null) {
      this._input.setAttribute("aria-expanded", this._flat_results.length > 0 ? "true" : "false");
      if (this._flat_results.length === 0) {
        this._input.removeAttribute("aria-activedescendant");
      }
    }
    this._update_active_highlight();
    if (total_results === 0) {
      this._render_status("No results.");
    } else {
      const label = total_results === 1 ? "1 result." : `${total_results} results.`;
      this._render_status(label);
    }
    return;
  }
  _render_status(text) {
    if (this._status_region !== null) {
      this._status_region.textContent = text;
    }
    return;
  }
  _update_active_highlight() {
    for (let index = 0; index < this._flat_results.length; index = index + 1) {
      const entry = this._flat_results[index];
      if (index === this._active_index) {
        entry.element.setAttribute("aria-selected", "true");
        if (this._input !== null) {
          this._input.setAttribute("aria-activedescendant", entry.element.id);
        }
        entry.element.classList.add(
          "pyc-site-shell__palette-option--active"
        );
      } else {
        entry.element.setAttribute("aria-selected", "false");
        entry.element.classList.remove(
          "pyc-site-shell__palette-option--active"
        );
      }
    }
    return;
  }
  async _activate_result(result) {
    this.close();
    if (typeof result.onActivate === "function") {
      try {
        await result.onActivate();
      } catch (reason) {
        console.warn(
          "pychestrate.ui.shell.palette_activate_failed",
          { reason: String(reason) }
        );
      }
      return;
    }
    if (typeof result.route === "string" && result.route.length > 0) {
      this._host.navigate(result.route);
    }
    return;
  }
  _on_dialog_keydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      // Escape here means "close the palette" only. Without
      // stopPropagation the event continues to document-level
      // listeners (the sidebar accordion, <mj-app-shell>'s
      // overlay handling) which would also collapse the sidebar
      // and steal the restored focus.
      event.stopPropagation();
      this.close();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (this._flat_results.length === 0) {
        return;
      }
      this._active_index = (this._active_index + 1) % this._flat_results.length;
      this._update_active_highlight();
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (this._flat_results.length === 0) {
        return;
      }
      const next_index = this._active_index <= 0 ? this._flat_results.length - 1 : this._active_index - 1;
      this._active_index = next_index;
      this._update_active_highlight();
      return;
    }
    if (event.key === "Enter") {
      if (this._active_index >= 0 && this._active_index < this._flat_results.length) {
        event.preventDefault();
        const active = this._flat_results[this._active_index];
        void this._activate_result(active.result);
      }
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      if (this._input !== null) {
        this._input.focus();
      }
      return;
    }
    return;
  }
}
export {
  PALETTE_INPUT_DEBOUNCE_MS,
  PaletteDialog
};
