/**
 * Mid-session 401 re-auth toast.
 *
 * Surfaces when ``pyc-session-401`` fires (from the permission cache
 * refresh path, or a future XHR wrapper). The toast offers a
 * "Sign in" affordance pointing at ``/login?next=<current-path>``.
 * The toast does NOT intercept the current request -- per
 * Requirement 3.3, the next user-initiated navigation surfaces the
 * server-side login redirect.
 *
 * A11y: ``role="status"``, ``aria-live="polite"`` so screen readers
 * announce the toast without stealing focus.
 */

const TOAST_MESSAGE: string = "Your session expired. Please sign in again."

export class SessionExpiredToast {
    private readonly _container: HTMLElement
    private _element: HTMLElement | null

    /**
     * @param container Region the toast attaches to.
     */
    public constructor(container: HTMLElement) {
        this._container = container
        this._element = null
    }

    /**
     * Render the toast if not already visible.
     */
    public show(): void {
        if (this._element !== null && this._element.parentNode !== null) {
            return
        }
        const toast = document.createElement("div")
        toast.classList.add("pyc-site-shell__session-toast")
        toast.setAttribute("role", "status")
        toast.setAttribute("aria-live", "polite")

        const message = document.createElement("span")
        message.classList.add("pyc-site-shell__session-toast-message")
        message.textContent = TOAST_MESSAGE
        toast.appendChild(message)

        const link = document.createElement("a")
        link.classList.add("pyc-site-shell__session-toast-action")
        link.textContent = "Sign in"
        const current_path = window.location.pathname + window.location.search
        const encoded = encodeURIComponent(current_path)
        link.href = "/login?next=" + encoded
        toast.appendChild(link)

        this._element = toast
        this._container.appendChild(toast)
        return
    }

    /**
     * Remove the toast from the DOM.
     */
    public hide(): void {
        if (this._element !== null && this._element.parentNode !== null) {
            this._element.parentNode.removeChild(this._element)
        }
        this._element = null
        return
    }
}
