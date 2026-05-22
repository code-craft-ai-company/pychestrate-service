const DEFAULT_PROVIDER_TIMEOUT_MS = 5e3;
const PALETTE_QUERY_MAX_LENGTH = 128;
class PaletteRegistry {
  _providers;
  constructor() {
    this._providers = /* @__PURE__ */ new Map();
  }
  /**
   * Register a palette provider. Duplicate ``providerId`` calls
   * are dropped with a ``console.warn`` (first wins) -- mirrors
   * the sidebar registry's collision policy.
   *
   * @param provider Descriptor.
   */
  registerProvider(provider) {
    if (provider === null || typeof provider !== "object") {
      console.warn(
        "pychestrate.ui.shell.palette_malformed_provider_registration"
      );
      return;
    }
    if (typeof provider.providerId !== "string" || provider.providerId.length === 0) {
      console.warn(
        "pychestrate.ui.shell.palette_malformed_provider_registration",
        { reason: "missing_providerId" }
      );
      return;
    }
    if (typeof provider.query !== "function") {
      console.warn(
        "pychestrate.ui.shell.palette_malformed_provider_registration",
        { reason: "missing_query", providerId: provider.providerId }
      );
      return;
    }
    if (this._providers.has(provider.providerId) === true) {
      console.warn(
        "pychestrate.ui.shell.palette_dup_provider",
        { providerId: provider.providerId }
      );
      return;
    }
    this._providers.set(provider.providerId, provider);
    return;
  }
  /**
   * Return the providers that pass the permission gate for the
   * supplied permission set. Order follows registration order.
   */
  visibleProviders(perms) {
    const visible = [];
    for (const provider of this._providers.values()) {
      const required = provider.requiredPermissions !== void 0 ? provider.requiredPermissions : [];
      if (perms.hasAll(required) === true) {
        visible.push(provider);
      }
    }
    return visible;
  }
  /**
   * Total registered provider count. Diagnostic only.
   */
  size() {
    const rtnval = this._providers.size;
    return rtnval;
  }
  /**
   * Fan-out the supplied query to every visible provider,
   * applying a per-provider timeout. Returns an array of
   * outcomes in the same order as ``visibleProviders``.
   *
   * Failures (rejections, timeouts) are reported as outcomes
   * with ``error`` set, NOT as a thrown rejection from this
   * method. Callers can therefore render partial results
   * deterministically.
   *
   * @param query Raw query string. Trimmed and capped to
   *              ``PALETTE_QUERY_MAX_LENGTH`` characters.
   * @param perms Active permission set.
   */
  async queryAll(query, perms) {
    const normalized = _normalize_query(query);
    const visible = this.visibleProviders(perms);
    const pending = [];
    for (const provider of visible) {
      pending.push(_run_provider(provider, normalized));
    }
    const settled = await Promise.all(pending);
    return settled;
  }
}
function _normalize_query(query) {
  let working = typeof query === "string" ? query : "";
  working = working.trim();
  if (working.length > PALETTE_QUERY_MAX_LENGTH) {
    working = working.slice(0, PALETTE_QUERY_MAX_LENGTH);
  }
  return working;
}
async function _run_provider(provider, query) {
  const timeout_ms = typeof provider.timeoutMs === "number" && provider.timeoutMs > 0 ? provider.timeoutMs : DEFAULT_PROVIDER_TIMEOUT_MS;
  let timer_handle = null;
  const timeout_promise = new Promise((_, reject) => {
    timer_handle = setTimeout(() => {
      reject(new Error("palette_provider_timeout"));
    }, timeout_ms);
  });
  try {
    const results = await Promise.race([
      provider.query(query),
      timeout_promise
    ]);
    if (timer_handle !== null) {
      clearTimeout(timer_handle);
    }
    const safe_results = Array.isArray(results) ? results : [];
    const outcome = {
      providerId: provider.providerId,
      providerLabel: provider.label,
      results: safe_results,
      error: null
    };
    return outcome;
  } catch (reason) {
    if (timer_handle !== null) {
      clearTimeout(timer_handle);
    }
    const outcome = {
      providerId: provider.providerId,
      providerLabel: provider.label,
      results: [],
      error: String(reason)
    };
    return outcome;
  }
}
export {
  DEFAULT_PROVIDER_TIMEOUT_MS,
  PALETTE_QUERY_MAX_LENGTH,
  PaletteRegistry
};
