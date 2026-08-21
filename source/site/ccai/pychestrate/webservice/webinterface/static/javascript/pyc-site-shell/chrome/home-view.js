/*
 * The shell-rendered landing view for the bare "/" route. No
 * feature bundle claims "/", so without this the main region
 * renders empty chrome. The view is built purely from data the
 * shell already holds: the brand label and the visible sidebar
 * computed from the navigation manifest.
 */

function build_home_view(options) {
    const panel = document.createElement("section");
    panel.classList.add("pyc-site-shell__home");
    panel.setAttribute("aria-label", "Home");

    const heading = document.createElement("h1");
    heading.classList.add("pyc-site-shell__home-heading");
    heading.textContent = options.brand_label;
    panel.appendChild(heading);

    const subtitle = document.createElement("p");
    subtitle.classList.add("pyc-site-shell__home-subtitle");
    subtitle.textContent = "Choose a destination to get started.";
    panel.appendChild(subtitle);

    const grid = build_nav_link_grid(options.visible_sidebar);
    panel.appendChild(grid);

    return panel;
}

/*
 * Build a grid of navigation links from a visible-sidebar
 * structure ({ groups: [{ group, entries }], ungrouped: [] } --
 * the shape SidebarRegistry.visible returns). Shared between the
 * home view and the not-found view. Links are plain <a href> so
 * they perform the same full page navigation the sidebar does.
 */
function build_nav_link_grid(visible_sidebar) {
    const grid = document.createElement("nav");
    grid.classList.add("pyc-site-shell__nav-grid");
    grid.setAttribute("aria-label", "Site sections");

    if (visible_sidebar.ungrouped.length > 0) {
        const card = build_nav_grid_card(null, visible_sidebar.ungrouped);
        grid.appendChild(card);
    }

    for (const bucket of visible_sidebar.groups) {
        const card = build_nav_grid_card(bucket.group.label, bucket.entries);
        grid.appendChild(card);
    }

    return grid;
}

function build_nav_grid_card(group_label, entries) {
    const card = document.createElement("section");
    card.classList.add("pyc-site-shell__nav-grid-card");

    if (group_label !== null) {
        const heading = document.createElement("h2");
        heading.classList.add("pyc-site-shell__nav-grid-card-heading");
        heading.textContent = group_label;
        card.appendChild(heading);
    }

    const list = document.createElement("ul");
    list.classList.add("pyc-site-shell__nav-grid-list");
    for (const entry of entries) {
        const item = document.createElement("li");
        const link = document.createElement("a");
        link.href = entry.route;
        link.textContent = entry.label;
        link.classList.add("pyc-site-shell__nav-grid-link");
        item.appendChild(link);
        list.appendChild(item);
    }
    card.appendChild(list);

    return card;
}

export {
    build_home_view,
    build_nav_link_grid
};
