/**
 * Build the default site-shell header — brand, user menu, logout.
 *
 * Slot-aware: when the consumer provides `slot="brand"` or
 * `slot="user-menu"` children, those override the defaults. The
 * shell honors that by reserving CSS layout for the slot
 * containers; the M1 implementation just renders the defaults
 * inline and lets the consumer DOM (if any) replace via slot
 * assignment in a future iteration.
 */

const LOGOUT_PATH: string = "/logout"

export interface HeaderOptions {
    brand_label: string
    user_display_name: string | null
}

/**
 * Build and return a configured header element. Caller is
 * responsible for appending it to the shell DOM.
 */
export function build_header(options: HeaderOptions): HTMLElement {
    const header = document.createElement("header")
    header.setAttribute("role", "banner")
    header.classList.add("pyc-site-shell__header")

    const brand = document.createElement("div")
    brand.classList.add("pyc-site-shell__brand")
    brand.textContent = options.brand_label
    header.appendChild(brand)

    const spacer = document.createElement("div")
    spacer.classList.add("pyc-site-shell__header-spacer")
    header.appendChild(spacer)

    const user_menu = document.createElement("div")
    user_menu.setAttribute("role", "menu")
    user_menu.classList.add("pyc-site-shell__user-menu")

    const display_name = options.user_display_name !== null
        ? options.user_display_name
        : "Account"
    const name_label = document.createElement("span")
    name_label.classList.add("pyc-site-shell__user-menu-name")
    name_label.textContent = display_name
    user_menu.appendChild(name_label)

    const logout_form = document.createElement("form")
    logout_form.method = "POST"
    logout_form.action = LOGOUT_PATH
    logout_form.classList.add("pyc-site-shell__logout-form")

    const logout_button = document.createElement("button")
    logout_button.type = "submit"
    logout_button.setAttribute("role", "menuitem")
    logout_button.classList.add("pyc-site-shell__logout-button")
    logout_button.textContent = "Sign out"
    logout_form.appendChild(logout_button)

    user_menu.appendChild(logout_form)
    header.appendChild(user_menu)

    return header
}
