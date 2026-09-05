/*
 * Build the no-permissions empty state as an <mj-empty-state>.
 * The heading attribute supplies the title; the description slot
 * carries the supplemental body copy. mj-empty-state owns the
 * surface, typography, and the actions slot so we do not
 * re-implement the layout.
 */

function build_empty_state() {
    const panel = document.createElement("mj-empty-state");
    panel.setAttribute("heading", "Your account has no access yet");
    panel.setAttribute("role", "status");
    panel.setAttribute("heading-level", "1");
    panel.classList.add("pyc-site-shell__empty-state");

    const body = document.createElement("p");
    body.setAttribute("slot", "description");
    body.classList.add("pyc-site-shell__empty-state-body");
    body.textContent = "Ask an administrator to grant you a role so you can use Pychestrate.";
    panel.appendChild(body);

    return panel;
}

export {
    build_empty_state
};
