// src/pyc-admin-bundle/palette/admin-search-provider.ts
var PROVIDER_ID = "admin.search";
var PROVIDER_LABEL = "Admin";
var PROVIDER_TIMEOUT_MS = 3e3;
var PROVIDER_REQUIRED_PERMISSIONS = ["system:ui.admin.view"];
var SEARCH_ENDPOINT = "/api/v1/admin/search";
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

// src/pyc-admin-bundle/index.ts
var ADMIN_GROUP_ID = "admin";
var ADMIN_ENTRIES = [
  {
    entryId: "admin.dashboard",
    label: "Dashboard",
    route: "/admin/dashboard",
    requiredPermissions: [],
    group: ADMIN_GROUP_ID
  },
  {
    entryId: "admin.users",
    label: "Users",
    route: "/admin/users",
    requiredPermissions: ["system:users.read"],
    group: ADMIN_GROUP_ID
  },
  {
    entryId: "admin.roles",
    label: "Roles",
    route: "/admin/roles",
    requiredPermissions: ["system:rbac.read"],
    group: ADMIN_GROUP_ID
  },
  {
    entryId: "admin.variables",
    label: "Variables",
    route: "/admin/variables",
    requiredPermissions: [],
    group: ADMIN_GROUP_ID
  },
  {
    entryId: "admin.scopes",
    label: "Secret Scopes",
    route: "/admin/scopes",
    requiredPermissions: ["system:secrets.admin"],
    group: ADMIN_GROUP_ID
  },
  {
    entryId: "admin.secrets",
    label: "Secrets",
    route: "/admin/secrets",
    requiredPermissions: ["system:secrets.read"],
    group: ADMIN_GROUP_ID
  },
  {
    entryId: "admin.sessions",
    label: "Sessions",
    route: "/admin/sessions",
    requiredPermissions: ["system:auth.read"],
    group: ADMIN_GROUP_ID
  },
  {
    entryId: "admin.audit",
    label: "Audit Logs",
    route: "/admin/audit-logs",
    requiredPermissions: ["system:audit.read"],
    group: ADMIN_GROUP_ID
  }
];
function register_admin_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ADMIN_GROUP_ID,
    label: "Admin",
    requiredPermissions: ["system:ui.admin.view"]
  });
  for (const entry of ADMIN_ENTRIES) {
    sidebar.registerEntry(entry);
  }
  return;
}
function _register_against(handle) {
  register_admin_sidebar(handle.sidebar);
  if (handle.palette !== void 0 && handle.palette !== null) {
    register_admin_palette_provider(handle.palette);
  }
  return;
}
function _boot() {
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
      "pychestrate.ui.admin.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
var ADMIN_SIDEBAR_ENTRIES = ADMIN_ENTRIES;
_boot();
export {
  ADMIN_SIDEBAR_ENTRIES,
  register_admin_sidebar
};
//# sourceMappingURL=pyc-admin-bundle.js.map
