class ShellRouter {
  _current;
  _callbacks;
  _main_region_getter;
  /**
   * @param initial_path - Path the shell booted on; typically
   *                       `window.location.pathname`.
   * @param main_region_getter - Function returning the active
   *                             `<main>` region (used for focus
   *                             restoration).
   */
  constructor(initial_path, main_region_getter) {
    this._current = ShellRouter.parse(initial_path);
    this._callbacks = [];
    this._main_region_getter = main_region_getter;
    window.addEventListener("popstate", () => {
      const next_context = ShellRouter.parse(window.location.pathname);
      const previous_context = this._current;
      this._current = next_context;
      this._dispatch(next_context, previous_context);
    });
  }
  /**
   * Parse a URL path into a structured `RouteContext`. M1
   * implementation is intentionally trivial — query params are
   * lifted into the `params` map; path segments are not parsed
   * against route patterns.
   */
  static parse(path) {
    let working = path;
    const params = {};
    const query_index = path.indexOf("?");
    if (query_index >= 0) {
      working = path.slice(0, query_index);
      const query_string = path.slice(query_index + 1);
      const search_params = new URLSearchParams(query_string);
      for (const [key, value] of search_params.entries()) {
        params[key] = value;
      }
    }
    const rtnval = { path: working, params };
    return rtnval;
  }
  /**
   * Return the active route context.
   */
  current() {
    const rtnval = this._current;
    return rtnval;
  }
  /**
   * Subscribe a callback for navigation events.
   */
  onNavigate(callback) {
    this._callbacks.push(callback);
    return;
  }
  /**
   * Drive a same-origin navigation by pushing on the history
   * stack and re-rendering. Callers are responsible for any
   * permission-cache refresh; this router does not own the
   * permission model.
   */
  async navigateTo(route) {
    const next_context = ShellRouter.parse(route);
    const previous_context = this._current;
    window.history.pushState({}, "", route);
    this._current = next_context;
    await this._dispatch(next_context, previous_context);
    this._restore_focus();
    return;
  }
  async _dispatch(next_context, previous_context) {
    for (const callback of this._callbacks) {
      try {
        await callback(next_context, previous_context);
      } catch (reason) {
        console.warn(
          "pychestrate.ui.shell.navigation_callback_failed",
          { reason: String(reason) }
        );
      }
    }
    return;
  }
  _restore_focus() {
    const main = this._main_region_getter();
    if (main === null) {
      return;
    }
    const heading = main.querySelector("h1");
    if (heading !== null) {
      if (heading.hasAttribute("tabindex") === false) {
        heading.setAttribute("tabindex", "-1");
      }
      ;
      heading.focus();
      return;
    }
    const focusable = main.querySelector(
      "a, button, input, select, textarea, [tabindex]"
    );
    if (focusable !== null) {
      focusable.focus();
    }
    return;
  }
}
export {
  ShellRouter
};
