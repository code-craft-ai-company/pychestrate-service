/**
 * Render the "no access" empty state — shown when an authenticated
 * user has zero visible sidebar entries (Requirement 5.1).
 */

export function build_empty_state(): HTMLElement {
    const panel = document.createElement("section")
    panel.classList.add("pyc-site-shell__empty-state")
    panel.setAttribute("role", "status")

    const heading = document.createElement("h1")
    heading.classList.add("pyc-site-shell__empty-state-heading")
    heading.textContent = "Your account has no access yet"
    panel.appendChild(heading)

    const body = document.createElement("p")
    body.classList.add("pyc-site-shell__empty-state-body")
    body.textContent =
        "Ask an administrator to grant you a role so you can use Pychestrate."
    panel.appendChild(body)

    return panel
}
