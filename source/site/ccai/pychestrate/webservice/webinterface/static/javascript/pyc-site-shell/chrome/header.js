/*
 * Build the shell's top app bar as an <mj-app-bar>. The leading
 * "brand" slot carries the sidebar collapse toggle, the brand
 * label, and a quiet command-palette hint chip; the trailing
 * "actions" slot carries the user menu (display name + sign-out
 * form). The returned element carries slot="app-bar" so it lands
 * in the <mj-app-shell> app-bar landmark.
 */

const LOGOUT_PATH = "/logout";

const NAV_TOGGLE_ICON_SVG =
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<path d=\"M4 6h16\" /><path d=\"M4 12h16\" /><path d=\"M4 18h16\" />"
    + "</svg>";

function build_header(options) {
    const app_bar = document.createElement("mj-app-bar");
    app_bar.setAttribute("slot", "app-bar");
    app_bar.setAttribute("sticky", "");
    app_bar.classList.add("pyc-site-shell__header");

    if (typeof options.on_nav_toggle === "function") {
        const nav_toggle = build_nav_toggle(
            options.on_nav_toggle,
            options.nav_open_initial === true
        );
        app_bar.appendChild(nav_toggle);
    }

    const brand = document.createElement("span");
    brand.setAttribute("slot", "brand");
    brand.classList.add("pyc-site-shell__brand");
    brand.textContent = options.brand_label;
    app_bar.appendChild(brand);

    if (typeof options.on_palette_hint_activate === "function") {
        const hint = build_palette_hint(
            options.palette_shortcut_label,
            options.on_palette_hint_activate
        );
        app_bar.appendChild(hint);
    }

    const actions = document.createElement("div");
    actions.setAttribute("slot", "actions");
    actions.setAttribute("role", "menu");
    actions.classList.add("pyc-site-shell__user-menu");

    const display_name = options.user_display_name !== null
        && options.user_display_name !== undefined
        ? options.user_display_name
        : "Account";
    const name_label = document.createElement("span");
    name_label.classList.add("pyc-site-shell__user-menu-name");
    name_label.textContent = display_name;
    actions.appendChild(name_label);

    // Sign out is a plain navigation to GET /logout. POST /logout
    // is CSRF-gated and the token lives in an HttpOnly cookie the
    // shell cannot read, so a script-built POST form can never
    // carry it; the GET route is un-gated by design.
    const logout_button = document.createElement("mj-button");
    logout_button.setAttribute("type", "button");
    logout_button.setAttribute("variant", "tertiary");
    logout_button.setAttribute("size", "sm");
    logout_button.setAttribute("role", "menuitem");
    logout_button.classList.add("pyc-site-shell__logout-button");
    logout_button.textContent = "Sign out";
    logout_button.addEventListener("click", (event) => {
        event.preventDefault();
        window.location.assign(LOGOUT_PATH);
    });
    actions.appendChild(logout_button);

    app_bar.appendChild(actions);
    return app_bar;
}

/*
 * The sidebar collapse toggle. A plain <button> (not <mj-button>)
 * so the hamburger SVG can inherit the header foreground through
 * currentColor without fighting the component's own slots. The
 * shell updates aria-expanded as it toggles the nav track.
 */
function build_nav_toggle(on_nav_toggle, nav_open_initial) {
    const nav_toggle = document.createElement("button");
    nav_toggle.type = "button";
    nav_toggle.setAttribute("slot", "brand");
    nav_toggle.classList.add("pyc-site-shell__nav-toggle");
    nav_toggle.setAttribute("aria-label", "Toggle navigation sidebar");
    nav_toggle.setAttribute("title", "Toggle navigation sidebar");
    nav_toggle.setAttribute(
        "aria-expanded",
        nav_open_initial === true ? "true" : "false"
    );
    nav_toggle.innerHTML = NAV_TOGGLE_ICON_SVG;
    nav_toggle.addEventListener("click", (event) => {
        event.preventDefault();
        on_nav_toggle();
    });
    return nav_toggle;
}

/*
 * Quiet keyboard-shortcut chip advertising the command palette.
 * Clicking it opens the palette directly, so the chip doubles as
 * a pointer-accessible entry point.
 */
function build_palette_hint(shortcut_label, on_activate) {
    const resolved_label = typeof shortcut_label === "string"
        && shortcut_label.length > 0
        ? shortcut_label
        : "Ctrl+K";
    const hint = document.createElement("button");
    hint.type = "button";
    hint.setAttribute("slot", "brand");
    hint.classList.add("pyc-site-shell__palette-hint");
    hint.setAttribute(
        "title",
        "Open the command palette to search navigation ("
            + resolved_label + ")"
    );
    hint.setAttribute("aria-label", "Open the command palette");
    hint.textContent = resolved_label;
    hint.addEventListener("click", (event) => {
        event.preventDefault();
        on_activate();
    });
    return hint;
}

export {
    build_header
};
