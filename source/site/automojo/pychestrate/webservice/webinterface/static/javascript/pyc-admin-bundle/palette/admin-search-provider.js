const PROVIDER_ID = "admin.search";
const PROVIDER_LABEL = "Admin";
const PROVIDER_TIMEOUT_MS = 3e3;
const PROVIDER_REQUIRED_PERMISSIONS = ["system:ui.admin.view"];
const SEARCH_ENDPOINT = "/api/v1/admin/search";
async function _admin_search(query) {
  const trimmed = query.trim();
  if (trimmed.length === 0) {
    const rtnval = [];
    return rtnval;
  }
  const url = SEARCH_ENDPOINT + "?q=" + encodeURIComponent(trimmed);
  const response = await fetch(url, {
    method: "GET",
    credentials: "same-origin",
    headers: { Accept: "application/json" }
  });
  if (response.ok === false) {
    throw new Error("admin_search_unavailable_" + String(response.status));
  }
  const payload = await response.json();
  const results = [];
  if (Array.isArray(payload) === true) {
    _coerce_into(payload, results);
  } else if (payload !== null && typeof payload === "object" && Array.isArray(payload.results) === true) {
    const items = payload.results;
    _coerce_into(items, results);
  }
  return results;
}
function _coerce_into(items, out) {
  for (const item of items) {
    if (item === null || typeof item !== "object") {
      continue;
    }
    const obj = item;
    const id = obj.id;
    const label = obj.label;
    if (typeof id !== "string" || typeof label !== "string") {
      continue;
    }
    const result = {
      id,
      label,
      description: typeof obj.description === "string" ? obj.description : null,
      route: typeof obj.route === "string" ? obj.route : null
    };
    out.push(result);
  }
  return;
}
function register_admin_palette_provider(palette) {
  palette.registerProvider({
    providerId: PROVIDER_ID,
    label: PROVIDER_LABEL,
    requiredPermissions: PROVIDER_REQUIRED_PERMISSIONS,
    timeoutMs: PROVIDER_TIMEOUT_MS,
    query: _admin_search
  });
  return;
}
const ADMIN_PALETTE_PROVIDER_ID = PROVIDER_ID;
export {
  ADMIN_PALETTE_PROVIDER_ID,
  register_admin_palette_provider
};
