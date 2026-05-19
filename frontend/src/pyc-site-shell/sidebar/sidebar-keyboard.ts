/**
 * Keyboard interaction layer for the sidebar.
 *
 * Implements Requirement 6.1 / 6.2 of the 9-site-shell spec:
 *
 * - ``ArrowDown`` / ``ArrowUp`` cycle through visible entries.
 * - ``Enter`` activates the focused entry.
 * - ``ArrowRight`` / ``ArrowLeft`` are reserved for group
 *   expand/collapse; current sidebar is non-collapsible (PR3
 *   renders groups always-open) so they are no-ops with a TODO.
 * - Type-to-jump: alphanumeric keystrokes within a 1 second
 *   window prefix-match entry labels (case-insensitive) and move
 *   focus to the first match. After 1 second of no keystrokes
 *   the buffer resets.
 *
 * Focus management: the active entry holds ``tabindex="0"``; all
 * other entries hold ``tabindex="-1"`` so Tab cycles through the
 * sidebar as a single stop. ``aria-current="page"`` continues to
 * mark the active route entry and is owned by the renderer.
 */

const TYPE_TO_JUMP_RESET_MS: number = 1000

const ENTRY_SELECTOR: string = ".pyc-site-shell__sidebar-entry"

/**
 * Attach keyboard handling to a sidebar container. Returns a
 * detach callback the renderer can invoke before re-rendering.
 *
 * @param container Sidebar ``<aside>`` element.
 */
export function attach_sidebar_keyboard(
    container: HTMLElement,
): () => void {
    const state: KeyboardState = {
        buffer: "",
        last_keystroke_at_ms: 0,
    }
    const handler = (event: KeyboardEvent): void => {
        _on_keydown(event, container, state)
    }
    container.addEventListener("keydown", handler)
    const detach = (): void => {
        container.removeEventListener("keydown", handler)
    }
    return detach
}

interface KeyboardState {
    buffer: string
    last_keystroke_at_ms: number
}

function _on_keydown(
    event: KeyboardEvent,
    container: HTMLElement,
    state: KeyboardState,
): void {
    const entries = _collect_entries(container)
    if (entries.length === 0) {
        return
    }
    const active_index = _resolve_active_index(entries, event.target)

    if (event.key === "ArrowDown") {
        event.preventDefault()
        const next_index = (active_index + 1) % entries.length
        _move_focus(entries, next_index)
        return
    }
    if (event.key === "ArrowUp") {
        event.preventDefault()
        const next_index = active_index <= 0
            ? entries.length - 1
            : active_index - 1
        _move_focus(entries, next_index)
        return
    }
    if (event.key === "Enter") {
        if (active_index >= 0 && active_index < entries.length) {
            event.preventDefault()
            entries[active_index].click()
        }
        return
    }
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        // TODO: wire collapse/expand once sidebar groups become
        // collapsible. Until then this is intentionally a no-op
        // so the keystroke does not also scroll the page.
        event.preventDefault()
        return
    }

    if (_is_type_to_jump_key(event) === true) {
        const now_ms = Date.now()
        if (now_ms - state.last_keystroke_at_ms > TYPE_TO_JUMP_RESET_MS) {
            state.buffer = ""
        }
        state.buffer = state.buffer + event.key.toLowerCase()
        state.last_keystroke_at_ms = now_ms
        const match_index = _find_prefix_match(entries, state.buffer)
        if (match_index >= 0) {
            event.preventDefault()
            _move_focus(entries, match_index)
        }
        return
    }
    return
}

function _is_type_to_jump_key(event: KeyboardEvent): boolean {
    if (event.ctrlKey === true || event.metaKey === true || event.altKey === true) {
        return false
    }
    if (typeof event.key !== "string") {
        return false
    }
    if (event.key.length !== 1) {
        return false
    }
    const code = event.key.charCodeAt(0)
    // Printable ASCII excluding space.
    if (code <= 0x20 || code >= 0x7F) {
        return false
    }
    return true
}

function _collect_entries(container: HTMLElement): HTMLElement[] {
    const node_list = container.querySelectorAll<HTMLElement>(ENTRY_SELECTOR)
    const rtnval: HTMLElement[] = []
    for (let index = 0; index < node_list.length; index = index + 1) {
        rtnval.push(node_list[index])
    }
    return rtnval
}

function _resolve_active_index(
    entries: HTMLElement[],
    target: EventTarget | null,
): number {
    if (target instanceof HTMLElement) {
        const direct_index = entries.indexOf(target)
        if (direct_index >= 0) {
            return direct_index
        }
    }
    for (let index = 0; index < entries.length; index = index + 1) {
        if (entries[index].getAttribute("tabindex") === "0") {
            return index
        }
    }
    return -1
}

function _move_focus(entries: HTMLElement[], next_index: number): void {
    for (let index = 0; index < entries.length; index = index + 1) {
        const entry = entries[index]
        if (index === next_index) {
            entry.setAttribute("tabindex", "0")
            entry.focus()
        } else {
            entry.setAttribute("tabindex", "-1")
        }
    }
    return
}

function _find_prefix_match(entries: HTMLElement[], prefix: string): number {
    if (prefix.length === 0) {
        return -1
    }
    for (let index = 0; index < entries.length; index = index + 1) {
        const label = (entries[index].textContent || "").trim().toLowerCase()
        if (label.startsWith(prefix) === true) {
            return index
        }
    }
    return -1
}

/**
 * Initialize tabindex roving for a freshly-rendered sidebar.
 * The active route's entry (the one with ``aria-current="page"``)
 * receives ``tabindex="0"``; all others get ``tabindex="-1"``. If
 * no entry is the active route the first entry holds tabindex 0
 * so the sidebar still has a keyboard entry point.
 *
 * @param container Sidebar ``<aside>`` element.
 */
export function initialize_sidebar_roving_tabindex(
    container: HTMLElement,
): void {
    const entries = _collect_entries(container)
    if (entries.length === 0) {
        return
    }
    let anchor_index = -1
    for (let index = 0; index < entries.length; index = index + 1) {
        if (entries[index].getAttribute("aria-current") === "page") {
            anchor_index = index
            break
        }
    }
    if (anchor_index < 0) {
        anchor_index = 0
    }
    for (let index = 0; index < entries.length; index = index + 1) {
        const entry = entries[index]
        if (index === anchor_index) {
            entry.setAttribute("tabindex", "0")
        } else {
            entry.setAttribute("tabindex", "-1")
        }
    }
    return
}
