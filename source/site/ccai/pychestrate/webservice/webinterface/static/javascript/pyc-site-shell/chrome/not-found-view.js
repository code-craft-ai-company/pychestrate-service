/*
 * The shell-rendered "Page not found" state. Shown when the
 * shell document served a path, the boot sequence finished, and
 * no feature bundle (and no server-rendered fragment) claimed
 * the main region -- previously the user saw blank chrome. The
 * view names the path and offers the home link plus the same
 * navigation grid the home view renders.
 */

import { build_nav_link_grid } from "./home-view.js";

function build_not_found_view(options) {
    const panel = document.createElement("section");
    panel.classList.add("pyc-site-shell__not-found");
    panel.setAttribute("aria-label", "Page not found");

    const heading = document.createElement("h1");
    heading.classList.add("pyc-site-shell__not-found-heading");
    heading.textContent = "Page not found";
    panel.appendChild(heading);

    const body = document.createElement("p");
    body.classList.add("pyc-site-shell__not-found-body");
    body.appendChild(
        document.createTextNode("There is no page at ")
    );
    const path_code = document.createElement("code");
    path_code.classList.add("pyc-site-shell__not-found-path");
    path_code.textContent = options.path;
    body.appendChild(path_code);
    body.appendChild(document.createTextNode("."));
    panel.appendChild(body);

    const home_paragraph = document.createElement("p");
    home_paragraph.classList.add("pyc-site-shell__not-found-home");
    const home_link = document.createElement("a");
    home_link.href = "/";
    home_link.textContent = "Go to the home page";
    home_link.classList.add("pyc-site-shell__not-found-home-link");
    home_paragraph.appendChild(home_link);
    panel.appendChild(home_paragraph);

    const grid = build_nav_link_grid(options.visible_sidebar);
    panel.appendChild(grid);

    return panel;
}

export {
    build_not_found_view
};
