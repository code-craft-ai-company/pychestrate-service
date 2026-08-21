class ShellRouter {
  _current;
  _callbacks;
  /**
   * Tracks the active route context for the shell. The
   * pychestrate site is server-rendered: the sidebar and the
   * command palette both perform full page loads, so this router
   * intentionally has no `navigateTo` / pushState path -- it only
   * parses the boot path and refreshes subscribers when the
   * browser traverses history within the same document (back /
   * forward with a bfcache restore).
   *
   * @param initial_path - Path the shell booted on; typically
   *                       `window.location.pathname`.
   */
  constructor(initial_path) {
    this._current = ShellRouter.parse(initial_path);
    this._callbacks = [];
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
}
export {
  ShellRouter
};
