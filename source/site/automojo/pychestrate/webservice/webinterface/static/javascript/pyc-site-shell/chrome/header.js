const LOGOUT_PATH = "/logout";
function build_header(options) {
  const header = document.createElement("header");
  header.setAttribute("role", "banner");
  header.classList.add("pyc-site-shell__header");
  const brand = document.createElement("div");
  brand.classList.add("pyc-site-shell__brand");
  brand.textContent = options.brand_label;
  header.appendChild(brand);
  const spacer = document.createElement("div");
  spacer.classList.add("pyc-site-shell__header-spacer");
  header.appendChild(spacer);
  const user_menu = document.createElement("div");
  user_menu.setAttribute("role", "menu");
  user_menu.classList.add("pyc-site-shell__user-menu");
  const display_name = options.user_display_name !== null ? options.user_display_name : "Account";
  const name_label = document.createElement("span");
  name_label.classList.add("pyc-site-shell__user-menu-name");
  name_label.textContent = display_name;
  user_menu.appendChild(name_label);
  const logout_form = document.createElement("form");
  logout_form.method = "POST";
  logout_form.action = LOGOUT_PATH;
  logout_form.classList.add("pyc-site-shell__logout-form");
  const logout_button = document.createElement("button");
  logout_button.type = "submit";
  logout_button.setAttribute("role", "menuitem");
  logout_button.classList.add("pyc-site-shell__logout-button");
  logout_button.textContent = "Sign out";
  logout_form.appendChild(logout_button);
  user_menu.appendChild(logout_form);
  header.appendChild(user_menu);
  return header;
}
export {
  build_header
};
