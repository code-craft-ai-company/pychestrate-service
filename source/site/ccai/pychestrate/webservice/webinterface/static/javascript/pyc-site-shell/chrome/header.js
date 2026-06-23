/*
 * Build the shell's top app bar as an <mj-app-bar>. The brand
 * goes into the leading "brand" slot, and the user menu (display
 * name + sign-out form) into the trailing "actions" slot. The
 * returned element carries slot="app-bar" so it lands in the
 * <mj-app-shell> app-bar landmark.
 */

const LOGOUT_PATH = "/logout";

function build_header(options) {
    const app_bar = document.createElement("mj-app-bar");
    app_bar.setAttribute("slot", "app-bar");
    app_bar.setAttribute("sticky", "");
    app_bar.classList.add("pyc-site-shell__header");

    const brand = document.createElement("span");
    brand.setAttribute("slot", "brand");
    brand.classList.add("pyc-site-shell__brand");
    brand.textContent = options.brand_label;
    app_bar.appendChild(brand);

    const actions = document.createElement("div");
    actions.setAttribute("slot", "actions");
    actions.setAttribute("role", "menu");
    actions.classList.add("pyc-site-shell__user-menu");

    const display_name = options.user_display_name !== null
        ? options.user_display_name
        : "Account";
    const name_label = document.createElement("span");
    name_label.classList.add("pyc-site-shell__user-menu-name");
    name_label.textContent = display_name;
    actions.appendChild(name_label);

    const logout_form = document.createElement("form");
    logout_form.method = "POST";
    logout_form.action = LOGOUT_PATH;
    logout_form.classList.add("pyc-site-shell__logout-form");
    const logout_button = document.createElement("mj-button");
    logout_button.setAttribute("type", "submit");
    logout_button.setAttribute("variant", "tertiary");
    logout_button.setAttribute("size", "sm");
    logout_button.setAttribute("role", "menuitem");
    logout_button.textContent = "Sign out";
    logout_form.appendChild(logout_button);
    actions.appendChild(logout_form);

    app_bar.appendChild(actions);
    return app_bar;
}

export {
    build_header
};
