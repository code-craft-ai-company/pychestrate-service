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
function _boot() {
  const target = window;
  const handle = target.pychestrateShell;
  if (handle !== void 0 && handle.sidebar !== void 0) {
    register_admin_sidebar(handle.sidebar);
    return;
  }
  queueMicrotask(() => {
    const retry = target.pychestrateShell;
    if (retry !== void 0 && retry.sidebar !== void 0) {
      register_admin_sidebar(retry.sidebar);
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
