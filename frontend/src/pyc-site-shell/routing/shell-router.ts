/**
 * Minimal client-side router for the site shell.
 *
 * Responsibilities (M1 scope):
 *
 * - Parse a path into a `RouteContext`.
 * - Drive `history.pushState` on `navigateTo(route)`.
 * - Listen for `popstate` and invoke registered callbacks.
 * - Restore focus to the `<main>` region's `<h1>` on navigation
 *   completion.
 */

export interface RouteContext {
    path: string
    params: Record<string, string>
}

export type NavigationCallback = (
    next_context: RouteContext,
    previous_context: RouteContext | null,
) => void | Promise<void>

export class ShellRouter {
    private _current: RouteContext
    private readonly _callbacks: NavigationCallback[]
    private readonly _main_region_getter: () => HTMLElement | null

    /**
     * @param initial_path - Path the shell booted on; typically
     *                       `window.location.pathname`.
     * @param main_region_getter - Function returning the active
     *                             `<main>` region (used for focus
     *                             restoration).
     */
    public constructor(
        initial_path: string,
        main_region_getter: () => HTMLElement | null,
    ) {
        this._current = ShellRouter.parse(initial_path)
        this._callbacks = []
        this._main_region_getter = main_region_getter

        window.addEventListener("popstate", () => {
            const next_context = ShellRouter.parse(window.location.pathname)
            const previous_context = this._current
            this._current = next_context
            this._dispatch(next_context, previous_context)
        })
    }

    /**
     * Parse a URL path into a structured `RouteContext`. M1
     * implementation is intentionally trivial — query params are
     * lifted into the `params` map; path segments are not parsed
     * against route patterns.
     */
    public static parse(path: string): RouteContext {
        let working = path
        const params: Record<string, string> = {}
        const query_index = path.indexOf("?")
        if (query_index >= 0) {
            working = path.slice(0, query_index)
            const query_string = path.slice(query_index + 1)
            const search_params = new URLSearchParams(query_string)
            for (const [key, value] of search_params.entries()) {
                params[key] = value
            }
        }
        const rtnval: RouteContext = { path: working, params }
        return rtnval
    }

    /**
     * Return the active route context.
     */
    public current(): RouteContext {
        const rtnval = this._current
        return rtnval
    }

    /**
     * Subscribe a callback for navigation events.
     */
    public onNavigate(callback: NavigationCallback): void {
        this._callbacks.push(callback)
        return
    }

    /**
     * Drive a same-origin navigation by pushing on the history
     * stack and re-rendering. Callers are responsible for any
     * permission-cache refresh; this router does not own the
     * permission model.
     */
    public async navigateTo(route: string): Promise<void> {
        const next_context = ShellRouter.parse(route)
        const previous_context = this._current
        window.history.pushState({}, "", route)
        this._current = next_context
        await this._dispatch(next_context, previous_context)
        this._restore_focus()
        return
    }

    private async _dispatch(
        next_context: RouteContext,
        previous_context: RouteContext | null,
    ): Promise<void> {
        for (const callback of this._callbacks) {
            try {
                await callback(next_context, previous_context)
            } catch (reason: unknown) {
                console.warn(
                    "pychestrate.ui.shell.navigation_callback_failed",
                    { reason: String(reason) },
                )
            }
        }
        return
    }

    private _restore_focus(): void {
        const main = this._main_region_getter()
        if (main === null) {
            return
        }
        const heading = main.querySelector("h1")
        if (heading !== null) {
            if (heading.hasAttribute("tabindex") === false) {
                heading.setAttribute("tabindex", "-1")
            }
            ;(heading as HTMLElement).focus()
            return
        }
        const focusable = main.querySelector<HTMLElement>(
            "a, button, input, select, textarea, [tabindex]",
        )
        if (focusable !== null) {
            focusable.focus()
        }
        return
    }
}
