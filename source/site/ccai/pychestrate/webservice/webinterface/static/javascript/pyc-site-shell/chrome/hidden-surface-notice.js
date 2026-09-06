/*
 * Hidden-surface notice (9-ui-profiles M2).
 *
 * The navigation manifest carries ``ui_profile.hidden_routes`` -- the
 * routes the caller may open but whose automation surface is hidden
 * from their navigation. When the current location sits under one of
 * those routes the shell shows a dismissible notice pointing at the
 * preferences page, so a user who arrives by URL understands why the
 * sidebar does not show the area they are looking at.
 */

const PREFERENCES_PATH = "/account/preferences";

/*
 * Whether ``pathname`` is ``route`` or a sub-path of it at a segment
 * boundary (``/builds/123`` matches ``/builds``; ``/buildsx`` does not).
 */
function path_under_route(pathname, route) {
    if (typeof route !== "string" || route.length === 0) {
        return false;
    }
    if (pathname === route) {
        return true;
    }
    const prefix = route.endsWith("/") ? route : route + "/";
    const rtnval = pathname.startsWith(prefix);
    return rtnval;
}

/*
 * Pick the hidden route the current path falls under, or null.
 */
function match_hidden_route(pathname, hidden_routes) {
    if (Array.isArray(hidden_routes) === false) {
        return null;
    }
    for (const route of hidden_routes) {
        if (path_under_route(pathname, route) === true) {
            return route;
        }
    }
    return null;
}

/*
 * Build the notice element. ``on_dismiss`` removes it.
 */
function build_hidden_surface_notice(route) {
    const notice = document.createElement("div");
    notice.classList.add("alert", "alert-info", "pyc-hidden-surface-notice");
    notice.setAttribute("role", "status");
    notice.setAttribute("data-hidden-route", route);

    const text = document.createElement("span");
    text.textContent = "This area is hidden from your navigation. ";
    notice.appendChild(text);

    const link = document.createElement("a");
    link.href = PREFERENCES_PATH;
    link.textContent = "Change your preferences";
    notice.appendChild(link);

    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.classList.add("btn", "btn-sm", "btn-secondary", "pyc-hidden-surface-notice__dismiss");
    dismiss.textContent = "Dismiss";
    dismiss.setAttribute("aria-label", "Dismiss hidden-surface notice");
    dismiss.addEventListener("click", () => {
        notice.remove();
    });
    notice.appendChild(dismiss);
    return notice;
}

export {
    PREFERENCES_PATH,
    build_hidden_surface_notice,
    match_hidden_route,
    path_under_route,
};
