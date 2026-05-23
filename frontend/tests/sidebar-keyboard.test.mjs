/**
 * Unit tests for the sidebar keyboard navigation layer.
 *
 * The sidebar shows only major items at rest (ungrouped entry
 * links and group buttons); a group's sub-items live in a flyout
 * popup. The keyboard layer therefore navigates at two levels:
 * the top-level major items, and the sub-items inside an open
 * popup.
 *
 * The keyboard layer operates against a real DOM API surface
 * (querySelectorAll, classList, focus, sibling traversal, etc.).
 * Stand up a minimal hand-rolled stub here -- enough for the
 * keyboard handler to walk both levels, manage tabindex, and
 * dispatch click / focus on the selected item.
 *
 * The same import-the-built-bundle policy applies as for the
 * sibling registry tests.
 */

import { test } from "node:test"
import assert from "node:assert/strict"
import * as path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const BUNDLE_PATH = path.resolve(
    HERE,
    "..",
    "..",
    "source",
    "site",
    "automojo",
    "pychestrate",
    "webservice",
    "webinterface",
    "static",
    "javascript",
    "pyc-site-shell",
    "index.js",
)

class StubElement {
    constructor(class_names, label) {
        this._listeners = new Map()
        this._attrs = new Map()
        this._class_names = new Set(class_names)
        this.children = []
        this.parent = null
        this.textContent = label
        this.click_count = 0
        this.focused = false
        this.hidden = false
        this.classList = {
            contains: (cls) => this._class_names.has(cls),
            add: (cls) => this._class_names.add(cls),
            remove: (cls) => this._class_names.delete(cls),
        }
    }

    get parentElement() {
        return this.parent
    }

    get nextElementSibling() {
        if (this.parent === null) {
            return null
        }
        const idx = this.parent.children.indexOf(this)
        const sibling = this.parent.children[idx + 1]
        return sibling === undefined ? null : sibling
    }

    get previousElementSibling() {
        if (this.parent === null) {
            return null
        }
        const idx = this.parent.children.indexOf(this)
        if (idx <= 0) {
            return null
        }
        return this.parent.children[idx - 1]
    }

    addEventListener(name, handler) {
        if (this._listeners.has(name) === false) {
            this._listeners.set(name, [])
        }
        this._listeners.get(name).push(handler)
    }

    removeEventListener(name, handler) {
        const list = this._listeners.get(name)
        if (list === undefined) {
            return
        }
        const idx = list.indexOf(handler)
        if (idx >= 0) {
            list.splice(idx, 1)
        }
    }

    dispatch(name, event) {
        const list = this._listeners.get(name)
        if (list === undefined) {
            return
        }
        for (const handler of list) {
            handler(event)
        }
    }

    setAttribute(name, value) {
        this._attrs.set(name, String(value))
    }
    getAttribute(name) {
        return this._attrs.has(name) ? this._attrs.get(name) : null
    }
    hasAttribute(name) {
        return this._attrs.has(name)
    }

    appendChild(child) {
        child.parent = this
        this.children.push(child)
    }

    matches(selector) {
        if (selector.startsWith(".")) {
            return this._class_names.has(selector.slice(1))
        }
        return false
    }

    querySelectorAll(selector) {
        const collected = []
        const visit = (node) => {
            for (const child of node.children) {
                if (child.matches(selector)) {
                    collected.push(child)
                }
                visit(child)
            }
        }
        visit(this)
        return collected
    }

    focus() {
        this.focused = true
        currentDocument.activeElement = this
    }

    click() {
        this.click_count = this.click_count + 1
        const event = { type: "click", target: this }
        this.dispatch("click", event)
    }
}

const currentDocument = { activeElement: null }

globalThis.customElements = {
    define: () => {},
    get: () => undefined,
}
globalThis.HTMLElement = StubElement
globalThis.window = { location: { pathname: "/" } }

const bundle = await import(pathToFileURL(BUNDLE_PATH).href)
const {
    attach_sidebar_keyboard,
    initialize_sidebar_roving_tabindex,
} = bundle

const NAVITEM = "pyc-site-shell__sidebar-navitem"
const ENTRY = "pyc-site-shell__sidebar-entry"
const GROUP_BTN = "pyc-site-shell__sidebar-group-btn"
const POPUP = "pyc-site-shell__sidebar-popup"

/**
 * Build an ungrouped major-item link.
 */
function _ungrouped(label) {
    const link = new StubElement([NAVITEM, ENTRY], label)
    return link
}

/**
 * Build a group major item: a wrapper div holding the group
 * button and its (initially hidden) flyout popup. A toggle click
 * handler on the button simulates the renderer's open/close.
 */
function _group(label, sub_labels) {
    const wrapper = new StubElement(["pyc-site-shell__sidebar-group"], null)
    const button = new StubElement([NAVITEM, GROUP_BTN], label)
    button.setAttribute("aria-expanded", "false")
    const popup = new StubElement([POPUP], null)
    popup.hidden = true
    for (const sub_label of sub_labels) {
        const entry = new StubElement([ENTRY], sub_label)
        popup.appendChild(entry)
    }
    button.addEventListener("click", () => {
        const open = button.getAttribute("aria-expanded") === "true"
        button.setAttribute("aria-expanded", open === true ? "false" : "true")
        popup.hidden = open === true ? true : false
    })
    wrapper.appendChild(button)
    wrapper.appendChild(popup)
    return { wrapper, button, popup }
}

/**
 * Assemble a sidebar container from a list of major-item nodes.
 */
function _container(nodes) {
    const container = new StubElement([], null)
    const nav = new StubElement(["pyc-site-shell__sidebar-nav"], null)
    for (const node of nodes) {
        nav.appendChild(node)
    }
    container.appendChild(nav)
    return container
}

function _navitems(container) {
    return container.querySelectorAll("." + NAVITEM)
}

function _send_key(container, key, target = null) {
    const event = {
        key,
        target,
        defaultPrevented: false,
        preventDefault: () => {
            event.defaultPrevented = true
        },
        ctrlKey: false,
        metaKey: false,
        altKey: false,
    }
    container.dispatch("keydown", event)
    return event
}

test("roving tabindex anchors on the active ungrouped link", () => {
    const alpha = _ungrouped("Alpha")
    const beta = _ungrouped("Beta")
    beta.setAttribute("aria-current", "page")
    const container = _container([alpha, beta])
    initialize_sidebar_roving_tabindex(container)
    assert.equal(alpha.getAttribute("tabindex"), "-1")
    assert.equal(beta.getAttribute("tabindex"), "0")
})

test("roving tabindex anchors on the active group button", () => {
    const alpha = _ungrouped("Alpha")
    const group = _group("Admin", ["Roles", "Audit"])
    group.button.classList.add("pyc-site-shell__sidebar-group-btn--active")
    const container = _container([alpha, group.wrapper])
    initialize_sidebar_roving_tabindex(container)
    assert.equal(alpha.getAttribute("tabindex"), "-1")
    assert.equal(group.button.getAttribute("tabindex"), "0")
})

test("ArrowDown / ArrowUp cycle focus between major items", () => {
    const alpha = _ungrouped("Alpha")
    const group = _group("Admin", ["Roles"])
    const gamma = _ungrouped("Gamma")
    const container = _container([alpha, group.wrapper, gamma])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    const items = _navitems(container)
    _send_key(container, "ArrowDown", items[0])
    assert.equal(items[1].focused, true)
    _send_key(container, "ArrowDown", items[1])
    assert.equal(items[2].focused, true)
    _send_key(container, "ArrowDown", items[2])
    assert.equal(items[0].focused, true)
    _send_key(container, "ArrowUp", items[0])
    assert.equal(items[2].focused, true)
})

test("Enter activates the focused ungrouped link", () => {
    const alpha = _ungrouped("Alpha")
    const beta = _ungrouped("Beta")
    const container = _container([alpha, beta])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    _send_key(container, "Enter", beta)
    assert.equal(beta.click_count, 1)
})

test("Enter on a group button opens its popup and focuses the first sub-item", () => {
    const group = _group("Admin", ["Roles", "Audit"])
    const container = _container([group.wrapper])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    _send_key(container, "Enter", group.button)
    assert.equal(group.popup.hidden, false)
    assert.equal(group.popup.children[0].focused, true)
})

test("ArrowRight on a group button opens its popup and descends into it", () => {
    const group = _group("Admin", ["Roles", "Audit"])
    const container = _container([group.wrapper])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    const event = _send_key(container, "ArrowRight", group.button)
    assert.equal(event.defaultPrevented, true)
    assert.equal(group.popup.hidden, false)
    assert.equal(group.popup.children[0].focused, true)
})

test("ArrowDown / ArrowUp cycle through open-popup sub-items", () => {
    const group = _group("Admin", ["Roles", "Audit", "Sessions"])
    const container = _container([group.wrapper])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    _send_key(container, "Enter", group.button)
    const subs = group.popup.children
    _send_key(container, "ArrowDown", subs[0])
    assert.equal(subs[1].focused, true)
    _send_key(container, "ArrowUp", subs[1])
    assert.equal(subs[0].focused, true)
    _send_key(container, "ArrowUp", subs[0])
    assert.equal(subs[2].focused, true)
})

test("Enter activates the focused sub-item", () => {
    const group = _group("Admin", ["Roles", "Audit"])
    const container = _container([group.wrapper])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    _send_key(container, "Enter", group.button)
    _send_key(container, "Enter", group.popup.children[1])
    assert.equal(group.popup.children[1].click_count, 1)
})

test("ArrowLeft inside a popup closes it and returns focus to the button", () => {
    const group = _group("Admin", ["Roles", "Audit"])
    const container = _container([group.wrapper])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    _send_key(container, "Enter", group.button)
    assert.equal(group.popup.hidden, false)
    _send_key(container, "ArrowLeft", group.popup.children[0])
    assert.equal(group.popup.hidden, true)
    assert.equal(group.button.getAttribute("aria-expanded"), "false")
    assert.equal(group.button.focused, true)
})

test("Type-to-jump moves focus to the first matching major item", () => {
    const audit = _ungrouped("Audit")
    const roles = _ungrouped("Roles")
    const settings = _ungrouped("Settings")
    const container = _container([audit, roles, settings])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    _send_key(container, "s", audit)
    assert.equal(settings.focused, true)
})

test("Type-to-jump moves focus to the first matching sub-item", () => {
    const group = _group("Admin", ["Roles", "Audit", "Sessions"])
    const container = _container([group.wrapper])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    _send_key(container, "Enter", group.button)
    _send_key(container, "s", group.popup.children[0])
    assert.equal(group.popup.children[2].focused, true)
})
