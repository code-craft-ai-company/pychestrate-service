import { PermissionSet } from "../permissions/permission-set.js"
import type {
    PaletteRegistry,
    PaletteProviderOutcome,
    PaletteResult,
} from "./palette-registry.js"

/**
 * Debounce window applied between keystrokes before the registry
 * is queried (milliseconds).
 */
export const PALETTE_INPUT_DEBOUNCE_MS: number = 80

/**
 * Hooks the palette dialog uses to talk back to the shell --
 * navigation, permission lookup, lifecycle events. Keeping this
 * narrow lets unit tests drive the dialog without needing a full
 * ``<pyc-site-shell>`` instance.
 */
export interface PaletteDialogHost {
    getPermissions: () => PermissionSet
    navigate: (route: string) => void
    emit: (event_name: string, detail: Record<string, unknown>) => void
    observePaletteOpened?: () => void
    observePaletteFanout?: (seconds: number) => void
}

/**
 * Render and control the command palette dialog. Built as a
 * plain ``HTMLDivElement`` attached to the shell DOM rather than
 * a separate Custom Element so it shares the shell's stylesheet
 * scope.
 *
 * A11y per design.md:
 *
 * - ``role="dialog"``, ``aria-modal="true"``, ``aria-label="Command Palette"``.
 * - Focus trap: tab/shift-tab cycles within the dialog.
 * - First focus lands on the search input.
 * - ``Esc`` closes the dialog.
 * - Results are a listbox; rows are ``role="option"``; ArrowUp /
 *   ArrowDown move the active option; Enter activates.
 */
export class PaletteDialog {
    private readonly _registry: PaletteRegistry
    private readonly _host: PaletteDialogHost

    private _container: HTMLDivElement | null
    private _input: HTMLInputElement | null
    private _results_region: HTMLDivElement | null
    private _status_region: HTMLDivElement | null
    private _is_open: boolean
    private _previous_focus: HTMLElement | null
    private _debounce_handle: ReturnType<typeof setTimeout> | null
    private _query_token: number
    private _flat_results: Array<{
        providerId: string
        result: PaletteResult
        element: HTMLElement
    }>
    private _active_index: number

    public constructor(registry: PaletteRegistry, host: PaletteDialogHost) {
        this._registry = registry
        this._host = host
        this._container = null
        this._input = null
        this._results_region = null
        this._status_region = null
        this._is_open = false
        this._previous_focus = null
        this._debounce_handle = null
        this._query_token = 0
        this._flat_results = []
        this._active_index = -1
    }

    public get isOpen(): boolean {
        const rtnval = this._is_open
        return rtnval
    }

    /**
     * Open the palette. No-op when already open. Builds the DOM
     * on first open and attaches it to ``document.body``.
     *
     * @param mount_target Optional override for the parent
     *                     element the dialog attaches to. Falls
     *                     back to ``document.body``.
     */
    public open(mount_target: HTMLElement | null = null): void {
        if (this._is_open === true) {
            return
        }
        if (this._container === null) {
            this._build_dom()
        }
        const container = this._container
        if (container === null) {
            return
        }
        const parent = mount_target !== null
            ? mount_target
            : document.body
        parent.appendChild(container)
        this._is_open = true
        this._previous_focus = document.activeElement instanceof HTMLElement
            ? (document.activeElement as HTMLElement)
            : null
        if (this._input !== null) {
            this._input.value = ""
            this._input.focus()
        }
        this._render_status("Type to search across registered providers.")
        this._host.emit("pyc-site-shell-palette-opened", {})
        if (typeof this._host.observePaletteOpened === "function") {
            this._host.observePaletteOpened()
        }
        return
    }

    /**
     * Close the palette and restore focus to the previously
     * focused element. No-op when already closed.
     */
    public close(): void {
        if (this._is_open === false) {
            return
        }
        const container = this._container
        if (container !== null && container.parentNode !== null) {
            container.parentNode.removeChild(container)
        }
        this._is_open = false
        if (this._debounce_handle !== null) {
            clearTimeout(this._debounce_handle)
            this._debounce_handle = null
        }
        this._flat_results = []
        this._active_index = -1
        const restore_target = this._previous_focus
        this._previous_focus = null
        if (restore_target !== null && typeof restore_target.focus === "function") {
            restore_target.focus()
        }
        this._host.emit("pyc-site-shell-palette-closed", {})
        return
    }

    private _build_dom(): void {
        const container = document.createElement("div")
        container.classList.add("pyc-site-shell__palette-backdrop")
        container.setAttribute("role", "presentation")

        const dialog = document.createElement("div")
        dialog.classList.add("pyc-site-shell__palette-dialog")
        dialog.setAttribute("role", "dialog")
        dialog.setAttribute("aria-modal", "true")
        dialog.setAttribute("aria-label", "Command Palette")
        dialog.tabIndex = -1

        const input = document.createElement("input")
        input.type = "search"
        input.classList.add("pyc-site-shell__palette-input")
        input.setAttribute("aria-label", "Search providers")
        input.setAttribute("autocomplete", "off")
        input.setAttribute("spellcheck", "false")
        input.placeholder = "Type to search..."
        input.addEventListener("input", () => {
            this._on_input_changed()
        })
        dialog.appendChild(input)

        const status = document.createElement("div")
        status.classList.add("pyc-site-shell__palette-status")
        status.setAttribute("role", "status")
        status.setAttribute("aria-live", "polite")
        dialog.appendChild(status)

        const results = document.createElement("div")
        results.classList.add("pyc-site-shell__palette-results")
        results.setAttribute("role", "listbox")
        results.setAttribute("aria-label", "Palette results")
        dialog.appendChild(results)

        dialog.addEventListener("keydown", (event) => {
            this._on_dialog_keydown(event)
        })

        // Backdrop click closes; clicks inside dialog do not bubble
        // through the backdrop handler.
        container.addEventListener("mousedown", (event) => {
            if (event.target === container) {
                this.close()
            }
        })

        container.appendChild(dialog)
        this._container = container
        this._input = input
        this._status_region = status
        this._results_region = results
        return
    }

    private _on_input_changed(): void {
        if (this._debounce_handle !== null) {
            clearTimeout(this._debounce_handle)
        }
        this._debounce_handle = setTimeout(() => {
            this._debounce_handle = null
            void this._run_query()
        }, PALETTE_INPUT_DEBOUNCE_MS)
        return
    }

    private async _run_query(): Promise<void> {
        if (this._input === null || this._results_region === null) {
            return
        }
        const raw_query = this._input.value
        this._query_token = this._query_token + 1
        const token = this._query_token

        if (raw_query.trim().length === 0) {
            this._results_region.replaceChildren()
            this._flat_results = []
            this._active_index = -1
            this._render_status(
                "Type to search across registered providers.",
            )
            return
        }

        const perms = this._host.getPermissions()
        const visible_providers = this._registry.visibleProviders(perms)
        if (visible_providers.length === 0) {
            this._results_region.replaceChildren()
            this._flat_results = []
            this._active_index = -1
            this._render_status("No providers available for your account.")
            return
        }

        this._render_status("Searching...")
        const fanout_started =
            typeof performance !== "undefined" ? performance.now() : 0
        const outcomes = await this._registry.queryAll(raw_query, perms)
        const fanout_finished =
            typeof performance !== "undefined" ? performance.now() : 0
        if (typeof this._host.observePaletteFanout === "function") {
            this._host.observePaletteFanout(
                (fanout_finished - fanout_started) / 1000,
            )
        }
        if (token !== this._query_token) {
            return
        }
        this._render_outcomes(outcomes)
        return
    }

    private _render_outcomes(outcomes: PaletteProviderOutcome[]): void {
        if (this._results_region === null) {
            return
        }
        this._results_region.replaceChildren()
        this._flat_results = []
        let total_results = 0
        for (const outcome of outcomes) {
            const section = document.createElement("div")
            section.classList.add("pyc-site-shell__palette-group")

            const heading = document.createElement("div")
            heading.classList.add("pyc-site-shell__palette-group-label")
            heading.textContent = outcome.providerLabel
            section.appendChild(heading)

            if (outcome.error !== null) {
                const notice = document.createElement("div")
                notice.classList.add("pyc-site-shell__palette-provider-error")
                notice.setAttribute("role", "note")
                notice.textContent = "This provider is unavailable."
                section.appendChild(notice)
                this._results_region.appendChild(section)
                continue
            }

            if (outcome.results.length === 0) {
                const empty = document.createElement("div")
                empty.classList.add("pyc-site-shell__palette-empty")
                empty.textContent = "No matches."
                section.appendChild(empty)
                this._results_region.appendChild(section)
                continue
            }

            for (const result of outcome.results) {
                const option = document.createElement("div")
                option.classList.add("pyc-site-shell__palette-option")
                option.setAttribute("role", "option")
                option.setAttribute("data-provider-id", outcome.providerId)
                option.setAttribute("data-result-id", result.id)
                option.tabIndex = -1

                const label = document.createElement("div")
                label.classList.add("pyc-site-shell__palette-option-label")
                label.textContent = result.label
                option.appendChild(label)

                if (
                    typeof result.description === "string" &&
                    result.description.length > 0
                ) {
                    const desc = document.createElement("div")
                    desc.classList.add(
                        "pyc-site-shell__palette-option-description",
                    )
                    desc.textContent = result.description
                    option.appendChild(desc)
                }

                option.addEventListener("click", () => {
                    void this._activate_result(result)
                })

                section.appendChild(option)
                this._flat_results.push({
                    providerId: outcome.providerId,
                    result,
                    element: option,
                })
                total_results = total_results + 1
            }
            this._results_region.appendChild(section)
        }
        this._active_index = this._flat_results.length > 0 ? 0 : -1
        this._update_active_highlight()
        if (total_results === 0) {
            this._render_status("No results.")
        } else {
            const label = total_results === 1 ? "1 result." : `${total_results} results.`
            this._render_status(label)
        }
        return
    }

    private _render_status(text: string): void {
        if (this._status_region !== null) {
            this._status_region.textContent = text
        }
        return
    }

    private _update_active_highlight(): void {
        for (let index = 0; index < this._flat_results.length; index = index + 1) {
            const entry = this._flat_results[index]
            if (index === this._active_index) {
                entry.element.setAttribute("aria-selected", "true")
                entry.element.classList.add(
                    "pyc-site-shell__palette-option--active",
                )
            } else {
                entry.element.setAttribute("aria-selected", "false")
                entry.element.classList.remove(
                    "pyc-site-shell__palette-option--active",
                )
            }
        }
        return
    }

    private async _activate_result(result: PaletteResult): Promise<void> {
        this.close()
        if (typeof result.onActivate === "function") {
            try {
                await result.onActivate()
            } catch (reason: unknown) {
                console.warn(
                    "pychestrate.ui.shell.palette_activate_failed",
                    { reason: String(reason) },
                )
            }
            return
        }
        if (typeof result.route === "string" && result.route.length > 0) {
            this._host.navigate(result.route)
        }
        return
    }

    private _on_dialog_keydown(event: KeyboardEvent): void {
        if (event.key === "Escape") {
            event.preventDefault()
            this.close()
            return
        }
        if (event.key === "ArrowDown") {
            event.preventDefault()
            if (this._flat_results.length === 0) {
                return
            }
            this._active_index =
                (this._active_index + 1) % this._flat_results.length
            this._update_active_highlight()
            return
        }
        if (event.key === "ArrowUp") {
            event.preventDefault()
            if (this._flat_results.length === 0) {
                return
            }
            const next_index = this._active_index <= 0
                ? this._flat_results.length - 1
                : this._active_index - 1
            this._active_index = next_index
            this._update_active_highlight()
            return
        }
        if (event.key === "Enter") {
            if (
                this._active_index >= 0 &&
                this._active_index < this._flat_results.length
            ) {
                event.preventDefault()
                const active = this._flat_results[this._active_index]
                void this._activate_result(active.result)
            }
            return
        }
        if (event.key === "Tab") {
            // Focus-trap: only the input is focusable inside the
            // dialog at the moment, so any Tab simply re-focuses it.
            event.preventDefault()
            if (this._input !== null) {
                this._input.focus()
            }
            return
        }
        return
    }
}
