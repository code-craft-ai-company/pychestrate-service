import type { SidebarRegistry, VisibleSidebar } from "./sidebar-registry.js"
import { PermissionSet } from "../permissions/permission-set.js"
import {
    attach_sidebar_keyboard,
    initialize_sidebar_roving_tabindex,
} from "./sidebar-keyboard.js"

/**
 * Render the visible sidebar into the supplied container element.
 *
 * The renderer fully replaces the container's children every call.
 * That keeps the implementation simple at M1 — a smarter diff is a
 * possible M3 optimization once we have telemetry showing it
 * matters.
 *
 * Active-route highlighting attaches `aria-current="page"` to the
 * `<a>` whose `route` matches `active_path`.
 */
export class SidebarRenderer {
    private readonly _container: HTMLElement
    private readonly _on_navigate: (route: string) => void
    private readonly _on_entry_clicked:
        | ((entryRoute: string, entryLabel: string) => void)
        | null
    private _detach_keyboard: (() => void) | null

    public constructor(
        container: HTMLElement,
        on_navigate: (route: string) => void,
        on_entry_clicked:
            | ((entryRoute: string, entryLabel: string) => void)
            | null = null,
    ) {
        this._container = container
        this._on_navigate = on_navigate
        this._on_entry_clicked = on_entry_clicked
        this._detach_keyboard = null
    }

    /**
     * Render the supplied visible sidebar into the container.
     *
     * @param registry - The sidebar registry source of truth.
     * @param perms - Current permission set.
     * @param active_path - Path of the active route, used for the
     *                      `aria-current="page"` marker.
     */
    public render(
        registry: SidebarRegistry,
        perms: PermissionSet,
        active_path: string,
    ): void {
        const visible_sidebar = registry.visible(perms)
        if (this._detach_keyboard !== null) {
            this._detach_keyboard()
            this._detach_keyboard = null
        }
        this._container.replaceChildren()

        const nav = document.createElement("nav")
        nav.setAttribute("role", "navigation")
        nav.setAttribute("aria-label", "Primary")
        nav.classList.add("pyc-site-shell__sidebar-nav")

        for (const entry of visible_sidebar.ungrouped) {
            const entry_element = this._build_entry_element(
                entry.label,
                entry.route,
                active_path,
            )
            nav.appendChild(entry_element)
        }

        for (const bucket of visible_sidebar.groups) {
            const group_section = document.createElement("section")
            group_section.classList.add("pyc-site-shell__sidebar-group")
            const heading = document.createElement("h2")
            heading.classList.add("pyc-site-shell__sidebar-group-label")
            heading.textContent = bucket.group.label
            group_section.appendChild(heading)
            for (const entry of bucket.entries) {
                const entry_element = this._build_entry_element(
                    entry.label,
                    entry.route,
                    active_path,
                )
                group_section.appendChild(entry_element)
            }
            nav.appendChild(group_section)
        }

        this._container.appendChild(nav)
        initialize_sidebar_roving_tabindex(this._container)
        this._detach_keyboard = attach_sidebar_keyboard(this._container)
        return
    }

    /**
     * Helper — build one `<a>` element representing a sidebar
     * entry. Text-only (no `innerHTML`) per the design's security
     * notes.
     */
    private _build_entry_element(
        label: string,
        route: string,
        active_path: string,
    ): HTMLAnchorElement {
        const link = document.createElement("a")
        link.href = route
        link.textContent = label
        link.classList.add("pyc-site-shell__sidebar-entry")
        link.setAttribute("tabindex", "-1")
        if (route === active_path) {
            link.setAttribute("aria-current", "page")
        }
        link.addEventListener("click", (event) => {
            // Left-click without modifier keys → SPA navigate.
            // Anything else (middle-click, ctrl/cmd-click, etc.) →
            // let the browser handle it natively (new tab / window).
            const mouse_event = event as MouseEvent
            if (mouse_event.defaultPrevented === true) {
                return
            }
            if (mouse_event.button !== undefined && mouse_event.button !== 0) {
                return
            }
            if (
                mouse_event.metaKey === true ||
                mouse_event.ctrlKey === true ||
                mouse_event.shiftKey === true ||
                mouse_event.altKey === true
            ) {
                return
            }
            event.preventDefault()
            if (this._on_entry_clicked !== null) {
                this._on_entry_clicked(route, label)
            }
            this._on_navigate(route)
        })
        return link
    }
}

export type { VisibleSidebar }
