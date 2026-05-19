/**
 * Degraded-state banner -- surfaces when the permission cache
 * fails to refresh for non-401 reasons (network error, 5xx, malformed
 * payload). Auto-dismisses when the next refresh succeeds.
 *
 * Rendered as a plain ``<div>`` rather than a Custom Element so it
 * picks up the shell stylesheet scope and keeps the bundle small.
 *
 * A11y: ``role="status"``, ``aria-live="polite"`` so screen readers
 * announce the degraded condition without stealing focus.
 */

export class DegradedBanner {
    private readonly _container: HTMLElement
    private _element: HTMLElement | null
    private _dismissed: boolean

    /**
     * @param container Region the banner attaches to. Typically
     *                  the shell's main region or its parent.
     */
    public constructor(container: HTMLElement) {
        this._container = container
        this._element = null
        this._dismissed = false
    }

    /**
     * Render or refresh the banner. Idempotent: a second call
     * after a previous show is a no-op.
     */
    public show(): void {
        if (this._dismissed === true) {
            return
        }
        if (this._element !== null && this._element.parentNode !== null) {
            return
        }
        const banner = document.createElement("div")
        banner.classList.add("pyc-site-shell__degraded-banner")
        banner.setAttribute("role", "status")
        banner.setAttribute("aria-live", "polite")

        const message = document.createElement("span")
        message.classList.add("pyc-site-shell__degraded-banner-message")
        message.textContent =
            "Permissions could not be refreshed. Using the last known set. " +
            "Some controls may behave incorrectly."
        banner.appendChild(message)

        const dismiss = document.createElement("button")
        dismiss.type = "button"
        dismiss.classList.add("pyc-site-shell__degraded-banner-dismiss")
        dismiss.setAttribute("aria-label", "Dismiss")
        dismiss.textContent = "Dismiss"
        dismiss.addEventListener("click", () => {
            this._dismissed = true
            this.hide()
        })
        banner.appendChild(dismiss)

        this._element = banner
        this._container.insertBefore(banner, this._container.firstChild)
        return
    }

    /**
     * Remove the banner from the DOM. Safe to call when not
     * rendered.
     */
    public hide(): void {
        if (this._element !== null && this._element.parentNode !== null) {
            this._element.parentNode.removeChild(this._element)
        }
        this._element = null
        return
    }
}
