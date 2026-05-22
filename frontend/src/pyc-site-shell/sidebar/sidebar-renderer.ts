import type {
    SidebarRegistry,
    SidebarEntry,
    SidebarGroup,
    VisibleSidebar,
} from "./sidebar-registry.js"
import { PermissionSet } from "../permissions/permission-set.js"
import {
    attach_sidebar_keyboard,
    initialize_sidebar_roving_tabindex,
} from "./sidebar-keyboard.js"

/**
 * Gap, in pixels, between a group's major-item button and the
 * flyout popup that carries its sub-items. Structural pixel value
 * (not typography) so it is allowed to be a literal.
 */
const POPUP_GAP_PX: number = 4

/**
 * Render the visible sidebar into the supplied container element.
 *
 * The sidebar shows only the "major items" at all times:
 *
 * - Ungrouped entries render as direct navigation links.
 * - Each group renders as a single button (the major item). Its
 *   "sub items" — the group's entries — live in a flyout popup
 *   that opens on click and closes on outside-click / Escape.
 *
 * Keeping only the major items resident keeps the sidebar short
 * regardless of how many entries a group carries.
 *
 * The renderer fully replaces the container's children every
 * call. Active-route highlighting attaches `aria-current="page"`
 * to the `<a>` whose `route` matches `active_path`; a group whose
 * popup contains the active route also gets a `--active` marker
 * on its button so the user can see which major item is current.
 */
export class SidebarRenderer {
    private readonly _container: HTMLElement
    private readonly _on_navigate: (route: string) => void
    private readonly _on_entry_clicked:
        | ((entryRoute: string, entryLabel: string) => void)
        | null
    private _detach_keyboard: (() => void) | null
    private _detach_dismiss: (() => void) | null
    private _open_button: HTMLButtonElement | null

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
        this._detach_dismiss = null
        this._open_button = null
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
        if (this._detach_dismiss !== null) {
            this._detach_dismiss()
            this._detach_dismiss = null
        }
        this._open_button = null
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
            entry_element.classList.add("pyc-site-shell__sidebar-navitem")
            nav.appendChild(entry_element)
        }

        for (const bucket of visible_sidebar.groups) {
            const group_element = this._build_group_element(
                bucket.group,
                bucket.entries,
                active_path,
            )
            nav.appendChild(group_element)
        }

        this._container.appendChild(nav)
        initialize_sidebar_roving_tabindex(this._container)
        this._detach_keyboard = attach_sidebar_keyboard(this._container)
        this._detach_dismiss = this._attach_dismiss()
        return
    }

    /**
     * Helper — build the major-item element for one group: a
     * `<div>` wrapper holding the group button plus the flyout
     * popup that carries the group's sub-item entries.
     */
    private _build_group_element(
        group: SidebarGroup,
        entries: readonly SidebarEntry[],
        active_path: string,
    ): HTMLElement {
        const wrapper = document.createElement("div")
        wrapper.classList.add("pyc-site-shell__sidebar-group")

        const button = document.createElement("button")
        button.type = "button"
        button.textContent = group.label
        button.classList.add(
            "pyc-site-shell__sidebar-group-btn",
            "pyc-site-shell__sidebar-navitem",
        )
        button.setAttribute("aria-haspopup", "true")
        button.setAttribute("aria-expanded", "false")
        button.setAttribute("tabindex", "-1")

        const popup = document.createElement("div")
        popup.classList.add("pyc-site-shell__sidebar-popup")
        popup.setAttribute("role", "menu")
        popup.setAttribute("aria-label", group.label)
        popup.hidden = true

        const popup_heading = document.createElement("h2")
        popup_heading.classList.add("pyc-site-shell__sidebar-popup-label")
        popup_heading.textContent = group.label
        popup.appendChild(popup_heading)

        let has_active_entry = false
        for (const entry of entries) {
            const entry_element = this._build_entry_element(
                entry.label,
                entry.route,
                active_path,
            )
            if (entry.route === active_path) {
                has_active_entry = true
            }
            popup.appendChild(entry_element)
        }
        if (has_active_entry === true) {
            button.classList.add("pyc-site-shell__sidebar-group-btn--active")
        }

        button.addEventListener("click", (event) => {
            event.preventDefault()
            this._toggle_popup(button, popup)
        })

        wrapper.appendChild(button)
        wrapper.appendChild(popup)
        return wrapper
    }

    /**
     * Open the supplied popup (closing any other open popup) or
     * close it when it is already open.
     */
    private _toggle_popup(
        button: HTMLButtonElement,
        popup: HTMLElement,
    ): void {
        const is_open = button.getAttribute("aria-expanded") === "true"
        if (is_open === true) {
            this._close_popup()
            return
        }
        this._close_popup()
        button.setAttribute("aria-expanded", "true")
        popup.hidden = false
        this._position_popup(button, popup)
        this._open_button = button
        return
    }

    /**
     * Close the currently-open popup, if any. The popup element is
     * always the next sibling of its button.
     */
    private _close_popup(): void {
        if (this._open_button === null) {
            return
        }
        const button = this._open_button
        button.setAttribute("aria-expanded", "false")
        const popup = button.nextElementSibling
        if (popup instanceof HTMLElement) {
            popup.hidden = true
        }
        this._open_button = null
        return
    }

    /**
     * Position a popup as a fixed-position flyout to the right of
     * its button. Fixed positioning keeps the popup clear of the
     * sidebar's `overflow` clip. When the popup would run off the
     * bottom of the viewport its top is nudged upward to fit.
     */
    private _position_popup(
        button: HTMLButtonElement,
        popup: HTMLElement,
    ): void {
        const button_rect = button.getBoundingClientRect()
        popup.style.left = (button_rect.right + POPUP_GAP_PX).toString() + "px"
        popup.style.top = button_rect.top.toString() + "px"
        const popup_rect = popup.getBoundingClientRect()
        const bottom_overflow = popup_rect.bottom - window.innerHeight
        if (bottom_overflow > 0) {
            let adjusted_top = button_rect.top - bottom_overflow - POPUP_GAP_PX
            if (adjusted_top < POPUP_GAP_PX) {
                adjusted_top = POPUP_GAP_PX
            }
            popup.style.top = adjusted_top.toString() + "px"
        }
        return
    }

    /**
     * Attach the document-level listeners that dismiss an open
     * popup: outside-click, Escape, and viewport reflow (resize /
     * sidebar scroll). Returns a detach callback the renderer
     * invokes before the next render.
     */
    private _attach_dismiss(): () => void {
        const on_document_click = (event: MouseEvent): void => {
            if (this._open_button === null) {
                return
            }
            const target = event.target
            if (target instanceof Node) {
                const button = this._open_button
                const popup = button.nextElementSibling
                if (button.contains(target) === true) {
                    return
                }
                if (
                    popup instanceof HTMLElement &&
                    popup.contains(target) === true
                ) {
                    return
                }
            }
            this._close_popup()
        }
        const on_document_keydown = (event: KeyboardEvent): void => {
            if (event.key !== "Escape") {
                return
            }
            if (this._open_button === null) {
                return
            }
            const button = this._open_button
            this._close_popup()
            button.focus()
        }
        const on_reflow = (): void => {
            this._close_popup()
        }
        document.addEventListener("click", on_document_click)
        document.addEventListener("keydown", on_document_keydown)
        window.addEventListener("resize", on_reflow)
        this._container.addEventListener("scroll", on_reflow, true)
        const detach = (): void => {
            document.removeEventListener("click", on_document_click)
            document.removeEventListener("keydown", on_document_keydown)
            window.removeEventListener("resize", on_reflow)
            this._container.removeEventListener("scroll", on_reflow, true)
        }
        return detach
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
            this._close_popup()
            if (this._on_entry_clicked !== null) {
                this._on_entry_clicked(route, label)
            }
            this._on_navigate(route)
        })
        return link
    }
}

export type { VisibleSidebar }
