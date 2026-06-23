class SidebarRegistry {
  _groups;
  _entries;
  _entry_routes;
  _change_listeners;
  constructor() {
    this._groups = /* @__PURE__ */ new Map();
    this._entries = [];
    this._entry_routes = /* @__PURE__ */ new Set();
    this._change_listeners = [];
  }
  /**
   * Subscribe to registry mutations. The shell wires its
   * sidebar re-render through here so feature bundles that
   * register their groups / entries AFTER the shell's initial
   * boot render (a load-order race -- the shell bundle and the
   * feature bundle are independent ``<script type="module">``
   * tags) still surface in the sidebar instead of leaving the
   * shell stuck on the zero-permissions empty state.
   */
  onChange(listener) {
    this._change_listeners.push(listener);
    return;
  }
  _notify_change() {
    for (const listener of this._change_listeners) {
      try {
        listener();
      } catch (reason) {
        console.warn(
          "pychestrate.ui.shell.sidebar_change_listener_failed",
          { reason: String(reason) }
        );
      }
    }
    return;
  }
  /**
   * Register a sidebar group. Duplicate `groupId` registrations
   * are dropped with a warn (first wins).
   */
  registerGroup(group) {
    if (group === null || typeof group !== "object") {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_group_registration"
      );
      return;
    }
    if (typeof group.groupId !== "string" || group.groupId.length === 0) {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_group_registration",
        { reason: "missing_groupId" }
      );
      return;
    }
    if (this._groups.has(group.groupId) === true) {
      console.warn(
        "pychestrate.ui.shell.sidebar_dup_group",
        { groupId: group.groupId }
      );
      return;
    }
    const normalized = _normalize_group(group);
    this._groups.set(normalized.groupId, normalized);
    this._notify_change();
    return;
  }
  /**
   * Register a sidebar entry. Duplicate `route` registrations
   * are dropped with a warn (first wins, per Requirement 2.5).
   */
  registerEntry(entry) {
    if (entry === null || typeof entry !== "object") {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_entry_registration"
      );
      return;
    }
    if (typeof entry.route !== "string" || entry.route.length === 0) {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_entry_registration",
        { reason: "missing_route" }
      );
      return;
    }
    if (this._entry_routes.has(entry.route) === true) {
      const existing = this._entries.find(
        (candidate) => candidate.route === entry.route
      );
      console.warn(
        "pychestrate.ui.shell.sidebar_dup_route",
        {
          route: entry.route,
          keptLabel: existing !== void 0 ? existing.label : null,
          droppedLabel: entry.label
        }
      );
      return;
    }
    const normalized = _normalize_entry(entry);
    this._entries.push(normalized);
    this._entry_routes.add(normalized.route);
    this._notify_change();
    return;
  }
  /**
   * Compute the visible sidebar for the supplied permission set.
   *
   * Visibility rules (Requirement 2):
   *
   * - A group is visible only when every required permission is
   *   present.
   * - An entry is visible only when (a) its required permissions
   *   are all present AND (b) if it declares a group, the group
   *   is also visible.
   * - Entries without a group are returned in `ungrouped` in
   *   registration order.
   */
  visible(perms) {
    const visible_groups = [];
    const group_by_id = /* @__PURE__ */ new Map();
    for (const group of this._groups.values()) {
      if (perms.hasAll(group.requiredPermissions) === true) {
        group_by_id.set(group.groupId, group);
        visible_groups.push({ group, entries: [] });
      }
    }
    const ungrouped = [];
    for (const entry of this._entries) {
      if (perms.hasAll(entry.requiredPermissions) === false) {
        continue;
      }
      const group_id = entry.group !== null && entry.group !== void 0 ? entry.group : null;
      if (group_id === null) {
        ungrouped.push(entry);
        continue;
      }
      if (group_by_id.has(group_id) === false) {
        continue;
      }
      for (const bucket of visible_groups) {
        if (bucket.group.groupId === group_id) {
          bucket.entries.push(entry);
          break;
        }
      }
    }
    const non_empty_groups = visible_groups.filter(
      (bucket) => bucket.entries.length > 0
    );
    const rtnval = {
      groups: non_empty_groups,
      ungrouped
    };
    return rtnval;
  }
  /**
   * Total number of visible entries — used by the shell to drive
   * the empty-state predicate (Requirement 5.1).
   */
  visibleEntryCount(perms) {
    const visible_sidebar = this.visible(perms);
    let count = visible_sidebar.ungrouped.length;
    for (const bucket of visible_sidebar.groups) {
      count = count + bucket.entries.length;
    }
    return count;
  }
}
function _normalize_group(group) {
  const rtnval = {
    groupId: group.groupId,
    label: typeof group.label === "string" ? group.label : group.groupId,
    icon: group.icon !== void 0 ? group.icon : null,
    requiredPermissions: Array.isArray(group.requiredPermissions) ? group.requiredPermissions.filter(
      (item) => typeof item === "string"
    ) : []
  };
  return rtnval;
}
function _normalize_entry(entry) {
  const rtnval = {
    entryId: typeof entry.entryId === "string" ? entry.entryId : entry.route,
    label: typeof entry.label === "string" ? entry.label : entry.route,
    route: entry.route,
    icon: entry.icon !== void 0 ? entry.icon : null,
    requiredPermissions: Array.isArray(entry.requiredPermissions) ? entry.requiredPermissions.filter(
      (item) => typeof item === "string"
    ) : [],
    group: entry.group !== void 0 ? entry.group : null
  };
  return rtnval;
}
export {
  SidebarRegistry
};
