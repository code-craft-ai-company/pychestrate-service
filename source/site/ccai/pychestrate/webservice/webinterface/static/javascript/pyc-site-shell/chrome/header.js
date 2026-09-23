/*
 * Build the shell's top app bar as an <mj-app-bar>. The leading
 * "brand" slot carries the sidebar collapse toggle, the brand
 * label, and a quiet command-palette button; the trailing
 * "actions" slot carries the account controls (display name,
 * theme, preferences, sign out). The returned element carries
 * slot="app-bar" so it lands in the <mj-app-shell> app-bar
 * landmark.
 *
 * On wide viewports the account controls sit inline. Below the
 * account breakpoint (see pyc-site-shell.css) they collapse
 * behind one account button that discloses them as a dropdown
 * panel, so Sign out stays reachable on a phone.
 */

const LOGOUT_PATH = "/logout";
const ACCOUNT_PANEL_ID = "pyc-site-shell-account-panel";

const NAV_TOGGLE_ICON_SVG =
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<path d=\"M4 6h16\" /><path d=\"M4 12h16\" /><path d=\"M4 18h16\" />"
    + "</svg>";

const SEARCH_ICON_SVG =
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<circle cx=\"11\" cy=\"11\" r=\"6.5\" /><path d=\"M20 20l-4.2-4.2\" />"
    + "</svg>";

const CHEVRON_DOWN_ICON_SVG =
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<path d=\"M6 9l6 6 6-6\" />"
    + "</svg>";

function build_header(options) {
    const app_bar = document.createElement("mj-app-bar");
    app_bar.setAttribute("slot", "app-bar");
    app_bar.setAttribute("sticky", "");
    app_bar.classList.add("pyc-site-shell__header");

    if (typeof options.on_nav_toggle === "function") {
        const nav_toggle = build_nav_toggle(
            options.on_nav_toggle,
            options.nav_open_initial === true,
            options.nav_controls_id
        );
        app_bar.appendChild(nav_toggle);
    }

    const brand = document.createElement("span");
    brand.setAttribute("slot", "brand");
    brand.classList.add("pyc-site-shell__brand");
    const brand_link = document.createElement("a");
    brand_link.href = "/";
    brand_link.classList.add("pyc-site-shell__brand-link");
    brand_link.textContent = options.brand_label;
    brand_link.setAttribute("aria-label", options.brand_label + " home");
    brand.appendChild(brand_link);
    app_bar.appendChild(brand);
    if (typeof options.on_palette_hint_activate === "function") {
        const hint = build_palette_hint(
            options.palette_shortcut_label,
            options.on_palette_hint_activate
        );
        app_bar.appendChild(hint);
    }

    const display_name = options.user_display_name !== null
        && options.user_display_name !== undefined
        ? options.user_display_name
        : "Account";
    app_bar.appendChild(build_account_menu(options, display_name));
    return app_bar;
}

/*
 * The account controls: an account button (shown only below the
 * account breakpoint) that discloses the panel, and the panel
 * itself, which is an inline row on wide viewports and a
 * dropdown on narrow ones. Disclosure pattern: the button
 * carries aria-expanded / aria-controls; the panel holds plain
 * links and buttons in tab order.
 */
function build_account_menu(options, display_name) {
    const actions = document.createElement("div");
    actions.setAttribute("slot", "actions");
    actions.classList.add("pyc-site-shell__user-menu");

    const account_button = document.createElement("button");
    account_button.type = "button";
    account_button.classList.add("pyc-site-shell__account-button");
    account_button.setAttribute("aria-expanded", "false");
    account_button.setAttribute("aria-controls", ACCOUNT_PANEL_ID);
    const account_prefix = document.createElement("span");
    account_prefix.classList.add("pyc-site-shell__visually-hidden");
    account_prefix.textContent = "Account: ";
    const account_name = document.createElement("span");
    account_name.classList.add("pyc-site-shell__account-button-name");
    account_name.textContent = display_name;
    const account_chevron = document.createElement("span");
    account_chevron.classList.add("pyc-site-shell__account-button-chevron");
    account_chevron.setAttribute("aria-hidden", "true");
    account_chevron.innerHTML = CHEVRON_DOWN_ICON_SVG;
    account_button.appendChild(account_prefix);
    account_button.appendChild(account_name);
    account_button.appendChild(account_chevron);
    actions.appendChild(account_button);

    const panel = document.createElement("div");
    panel.id = ACCOUNT_PANEL_ID;
    panel.classList.add("pyc-site-shell__account-panel");

    const name_label = document.createElement("span");
    name_label.classList.add("pyc-site-shell__user-menu-name");
    name_label.textContent = display_name;
    panel.appendChild(name_label);

    if (typeof options.on_theme_toggle === "function") {
        const theme_button = document.createElement("mj-button");
        theme_button.setAttribute("type", "button");
        theme_button.setAttribute("variant", "tertiary");
        theme_button.setAttribute("size", "sm");
        theme_button.classList.add("pyc-site-shell__theme-toggle");
        const is_dark = options.current_theme === "dark";
        theme_button.setAttribute("aria-pressed", is_dark ? "true" : "false");
        theme_button.setAttribute("aria-label", is_dark ? "Switch to light theme" : "Switch to dark theme");
        theme_button.textContent = "Theme";
        theme_button.addEventListener("click", (event) => {
            event.preventDefault();
            options.on_theme_toggle();
        });
        panel.appendChild(theme_button);
    }
    // 9-ui-profiles: every signed-in user can narrow which automation
    // surfaces the shell shows them.
    const preferences_link = document.createElement("a");
    preferences_link.href = "/account/preferences";
    preferences_link.classList.add("pyc-site-shell__preferences-link");
    preferences_link.textContent = "Preferences";
    panel.appendChild(preferences_link);

    // Sign out POSTs to /logout with the CSRF token the shell
    // document carries (csrf-token attribute). Without a token the
    // control falls back to GET /logout, which renders a
    // confirmation page whose button performs the POST.
    const logout_button = document.createElement("mj-button");
    logout_button.setAttribute("type", "button");
    logout_button.setAttribute("variant", "tertiary");
    logout_button.setAttribute("size", "sm");
    logout_button.classList.add("pyc-site-shell__logout-button");
    logout_button.textContent = "Sign out";
    logout_button.addEventListener("click", (event) => {
        event.preventDefault();
        const csrf_token = typeof options.csrf_token === "string" ? options.csrf_token : "";
        if (csrf_token.length === 0) {
            window.location.assign(LOGOUT_PATH);
            return;
        }
        const form = document.createElement("form");
        form.method = "post";
        form.action = LOGOUT_PATH;
        form.hidden = true;
        const token_input = document.createElement("input");
        token_input.type = "hidden";
        token_input.name = "csrf_token";
        token_input.value = csrf_token;
        form.appendChild(token_input);
        document.body.appendChild(form);
        form.submit();
    });
    panel.appendChild(logout_button);
    actions.appendChild(panel);

    wire_account_disclosure(actions, account_button, panel);
    return actions;
}

/*
 * Open / close behavior of the narrow-viewport account panel:
 * the button toggles it; Escape closes it and returns focus to
 * the button; a click outside or focus leaving the menu closes
 * it. The panel's visibility is CSS-driven (the data-open
 * attribute), so on wide viewports -- where the button is not
 * rendered and the panel is always an inline row -- none of this
 * has any visible effect.
 */
function wire_account_disclosure(container, button, panel) {
    const set_open = (open) => {
        button.setAttribute("aria-expanded", open === true ? "true" : "false");
        if (open === true) {
            panel.setAttribute("data-open", "");
        } else {
            panel.removeAttribute("data-open");
        }
    };
    const is_open = () => panel.hasAttribute("data-open");
    button.addEventListener("click", (event) => {
        event.preventDefault();
        set_open(is_open() === false);
    });
    container.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || is_open() === false) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        set_open(false);
        button.focus();
    });
    container.addEventListener("focusout", (event) => {
        const next = event.relatedTarget;
        if (next instanceof Node && container.contains(next) === true) {
            return;
        }
        set_open(false);
    });
    document.addEventListener("click", (event) => {
        if (is_open() === false) {
            return;
        }
        if (event.composedPath().includes(container) === true) {
            return;
        }
        set_open(false);
    });
    return;
}

/*
 * The sidebar collapse toggle. A plain <button> (not <mj-button>)
 * so the hamburger SVG can inherit the header foreground through
 * currentColor without fighting the component's own slots. The
 * shell keeps aria-expanded in step with the nav track.
 */
function build_nav_toggle(on_nav_toggle, nav_open_initial, nav_controls_id) {
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
    if (typeof nav_controls_id === "string" && nav_controls_id.length > 0) {
        nav_toggle.setAttribute("aria-controls", nav_controls_id);
    }
    nav_toggle.innerHTML = NAV_TOGGLE_ICON_SVG;
    nav_toggle.addEventListener("click", (event) => {
        event.preventDefault();
        on_nav_toggle();
    });
    return nav_toggle;
}

/*
 * The command-palette button: a search icon plus the keyboard
 * shortcut chip. On touch-first devices (coarse pointer) only the
 * icon shows -- there is no keyboard to press the shortcut on --
 * so the button stays the palette's entry point there.
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
    hint.setAttribute("aria-keyshortcuts", resolved_label === "⌘K" ? "Meta+K" : "Control+K");
    const icon = document.createElement("span");
    icon.classList.add("pyc-site-shell__palette-hint-icon");
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = SEARCH_ICON_SVG;
    const shortcut = document.createElement("span");
    shortcut.classList.add("pyc-site-shell__palette-hint-shortcut");
    shortcut.textContent = resolved_label;
    hint.appendChild(icon);
    hint.appendChild(shortcut);
    hint.addEventListener("click", (event) => {
        event.preventDefault();
        on_activate();
    });
    return hint;
}

export {
    build_header
};
