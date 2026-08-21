/*
 * Server-rendered flash messages, lifted into shell chrome.
 *
 * The legacy blueprint fragments (config, projects) render
 * pending flashes at the top of the fragment as
 * ``<div class="alert alert-{category}">message</div>``. When a
 * Web-Component bundle claims the route it replaces the main
 * region's children, destroying those flashes unread. The shell
 * therefore lifts them out of the fragment at boot -- BEFORE any
 * bundle mounts -- and re-renders them as dismissible
 * <mj-alert> notices in a shell-owned region that sits beside
 * the main region, out of reach of bundle replaceChildren calls.
 * Because the originals are MOVED out of the fragment (not
 * copied), legacy pages whose fragment survives intact cannot
 * show the same flash twice.
 */

const FLASH_SELECTOR = "div.alert.alert-success, div.alert.alert-error, div.alert.alert-danger, div.alert.alert-warning, div.alert.alert-info";

const CATEGORY_TO_SEVERITY = {
    "alert-success": "success",
    "alert-error": "error",
    "alert-danger": "error",
    "alert-warning": "warning",
    "alert-info": "info"
};

/*
 * Extract the flash elements found in the supplied nodes (the
 * server-rendered fragment children the shell preserved). Returns
 * ``{ flashes, remaining_nodes }``: the category + text of each
 * flash found, and the fragment nodes that should still be
 * re-attached to the main region. The caller MUST use
 * ``remaining_nodes`` -- the supplied nodes are already detached
 * from the document, so a root-level flash cannot delete itself
 * (``remove()`` is a no-op without a parent); it is dropped from
 * the returned list instead.
 *
 * Matching is checked on each node itself and on descendants, so
 * flashes are found whether the fragment carries them at its root
 * (the current template shape) or nested in a wrapper.
 */
function extract_flash_messages(nodes) {
    const flashes = [];
    const remaining_nodes = [];
    for (const node of nodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) {
            remaining_nodes.push(node);
            continue;
        }
        const element = node;
        if (element.matches(FLASH_SELECTOR) === true) {
            flashes.push(_flash_from(element));
            continue;
        }
        for (const found of Array.from(
            element.querySelectorAll(FLASH_SELECTOR)
        )) {
            flashes.push(_flash_from(found));
            found.remove();
        }
        remaining_nodes.push(element);
    }
    const rtnval = { flashes, remaining_nodes };
    return rtnval;
}

function _flash_from(flash_element) {
    const rtnval = {
        severity: _severity_for(flash_element),
        message: flash_element.textContent.trim()
    };
    return rtnval;
}

/*
 * Build one dismissible notice for a lifted flash. No
 * auto-dismiss: the whole point of lifting is that the user gets
 * to read the message.
 */
function build_flash_notice(flash) {
    const notice = document.createElement("mj-alert");
    notice.setAttribute("severity", flash.severity);
    notice.setAttribute("dismissible", "");
    notice.setAttribute("open", "");
    notice.classList.add("pyc-site-shell__flash-notice");

    const message = document.createElement("span");
    message.classList.add("pyc-site-shell__flash-notice-message");
    message.textContent = flash.message;
    notice.appendChild(message);

    notice.addEventListener("mj-alert-close", () => {
        if (notice.parentNode !== null) {
            notice.parentNode.removeChild(notice);
        }
    });

    return notice;
}

function _severity_for(flash_element) {
    for (const class_name of Array.from(flash_element.classList)) {
        const severity = CATEGORY_TO_SEVERITY[class_name];
        if (severity !== undefined) {
            return severity;
        }
    }
    return "info";
}

export {
    build_flash_notice,
    extract_flash_messages
};
