import { PermissionSet } from "../permissions/permission-set.js"

/**
 * A sidebar group — a labeled section of the sidebar that contains
 * one or more entries. Groups may declare their own required
 * permissions; when the caller lacks any of them the whole group
 * (header + every entry) is hidden, regardless of per-entry
 * permissions (Requirement 2.4).
 */
export interface SidebarGroup {
    groupId: string
    label: string
    icon?: string | null
    requiredPermissions: readonly string[]
}

/**
 * A sidebar entry — a single navigable item. `route` is the path
 * the shell navigates to on activation. `group` (when present)
 * names the `groupId` the entry lives under.
 */
export interface SidebarEntry {
    entryId: string
    label: string
    route: string
    icon?: string | null
    requiredPermissions: readonly string[]
    group?: string | null
}

/**
 * Result shape returned from `visible()` — keeps groups and the
 * fallback ungrouped entries separate so the renderer can decide
 * how to lay them out.
 */
export interface VisibleSidebar {
    groups: Array<{
        group: SidebarGroup
        entries: SidebarEntry[]
    }>
    ungrouped: SidebarEntry[]
}

/**
 * In-process sidebar registry. Feature bundles call
 * `registerGroup` / `registerEntry` at load time; the shell calls
 * `visible(perms)` to compute the intersection against the live
 * permission cache.
 *
 * Per Requirement 2.5: duplicate routes are dropped with a
 * `console.warn` (the first registration wins).
 */
export class SidebarRegistry {
    private readonly _groups: Map<string, SidebarGroup>
    private readonly _entries: SidebarEntry[]
    private readonly _entry_routes: Set<string>
    private readonly _change_listeners: Array<() => void>

    public constructor() {
        this._groups = new Map<string, SidebarGroup>()
        this._entries = []
        this._entry_routes = new Set<string>()
        this._change_listeners = []
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
    public onChange(listener: () => void): void {
        this._change_listeners.push(listener)
        return
    }

    private _notify_change(): void {
        for (const listener of this._change_listeners) {
            try {
                listener()
            } catch (reason: unknown) {
                console.warn(
                    "pychestrate.ui.shell.sidebar_change_listener_failed",
                    { reason: String(reason) },
                )
            }
        }
        return
    }

    /**
     * Register a sidebar group. Duplicate `groupId` registrations
     * are dropped with a warn (first wins).
     */
    public registerGroup(group: SidebarGroup): void {
        if (group === null || typeof group !== "object") {
            console.warn(
                "pychestrate.ui.shell.sidebar_malformed_group_registration",
            )
            return
        }
        if (typeof group.groupId !== "string" || group.groupId.length === 0) {
            console.warn(
                "pychestrate.ui.shell.sidebar_malformed_group_registration",
                { reason: "missing_groupId" },
            )
            return
        }
        if (this._groups.has(group.groupId) === true) {
            console.warn(
                "pychestrate.ui.shell.sidebar_dup_group",
                { groupId: group.groupId },
            )
            return
        }
        const normalized = _normalize_group(group)
        this._groups.set(normalized.groupId, normalized)
        this._notify_change()
        return
    }

    /**
     * Register a sidebar entry. Duplicate `route` registrations
     * are dropped with a warn (first wins, per Requirement 2.5).
     */
    public registerEntry(entry: SidebarEntry): void {
        if (entry === null || typeof entry !== "object") {
            console.warn(
                "pychestrate.ui.shell.sidebar_malformed_entry_registration",
            )
            return
        }
        if (typeof entry.route !== "string" || entry.route.length === 0) {
            console.warn(
                "pychestrate.ui.shell.sidebar_malformed_entry_registration",
                { reason: "missing_route" },
            )
            return
        }
        if (this._entry_routes.has(entry.route) === true) {
            const existing = this._entries.find(
                (candidate) => candidate.route === entry.route,
            )
            console.warn(
                "pychestrate.ui.shell.sidebar_dup_route",
                {
                    route: entry.route,
                    keptLabel: existing !== undefined ? existing.label : null,
                    droppedLabel: entry.label,
                },
            )
            return
        }
        const normalized = _normalize_entry(entry)
        this._entries.push(normalized)
        this._entry_routes.add(normalized.route)
        this._notify_change()
        return
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
    public visible(perms: PermissionSet): VisibleSidebar {
        const visible_groups: Array<{
            group: SidebarGroup
            entries: SidebarEntry[]
        }> = []
        const group_by_id = new Map<string, SidebarGroup>()
        for (const group of this._groups.values()) {
            if (perms.hasAll(group.requiredPermissions) === true) {
                group_by_id.set(group.groupId, group)
                visible_groups.push({ group, entries: [] })
            }
        }

        const ungrouped: SidebarEntry[] = []
        for (const entry of this._entries) {
            if (perms.hasAll(entry.requiredPermissions) === false) {
                continue
            }
            const group_id = entry.group !== null && entry.group !== undefined
                ? entry.group
                : null
            if (group_id === null) {
                ungrouped.push(entry)
                continue
            }
            if (group_by_id.has(group_id) === false) {
                // Either the group was never registered or the
                // caller lacks the group's required permissions —
                // either way the entry is hidden.
                continue
            }
            for (const bucket of visible_groups) {
                if (bucket.group.groupId === group_id) {
                    bucket.entries.push(entry)
                    break
                }
            }
        }

        // Drop groups whose visible-entries list is empty so the
        // empty-state predicate (Requirement 5) lines up with what
        // the user sees.
        const non_empty_groups = visible_groups.filter(
            (bucket) => bucket.entries.length > 0,
        )

        const rtnval: VisibleSidebar = {
            groups: non_empty_groups,
            ungrouped,
        }
        return rtnval
    }

    /**
     * Total number of visible entries — used by the shell to drive
     * the empty-state predicate (Requirement 5.1).
     */
    public visibleEntryCount(perms: PermissionSet): number {
        const visible_sidebar = this.visible(perms)
        let count = visible_sidebar.ungrouped.length
        for (const bucket of visible_sidebar.groups) {
            count = count + bucket.entries.length
        }
        return count
    }
}

function _normalize_group(group: SidebarGroup): SidebarGroup {
    const rtnval: SidebarGroup = {
        groupId: group.groupId,
        label: typeof group.label === "string" ? group.label : group.groupId,
        icon: group.icon !== undefined ? group.icon : null,
        requiredPermissions: Array.isArray(group.requiredPermissions)
            ? group.requiredPermissions.filter(
                  (item) => typeof item === "string",
              )
            : [],
    }
    return rtnval
}

function _normalize_entry(entry: SidebarEntry): SidebarEntry {
    const rtnval: SidebarEntry = {
        entryId: typeof entry.entryId === "string"
            ? entry.entryId
            : entry.route,
        label: typeof entry.label === "string" ? entry.label : entry.route,
        route: entry.route,
        icon: entry.icon !== undefined ? entry.icon : null,
        requiredPermissions: Array.isArray(entry.requiredPermissions)
            ? entry.requiredPermissions.filter(
                  (item) => typeof item === "string",
              )
            : [],
        group: entry.group !== undefined ? entry.group : null,
    }
    return rtnval
}
