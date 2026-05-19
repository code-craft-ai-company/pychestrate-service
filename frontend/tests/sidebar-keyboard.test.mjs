/**
 * Unit tests for the sidebar keyboard navigation layer (M2 / PR5).
 *
 * The keyboard layer operates against a real DOM API surface
 * (querySelectorAll, classList, focus, etc.). Stand up a minimal
 * hand-rolled stub here -- enough for the keyboard handler to
 * walk the entry list, manage tabindex, and dispatch click /
 * focus on the selected entry.
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
    "dist",
    "pyc-site-shell.js",
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
        this.classList = {
            contains: (cls) => this._class_names.has(cls),
            add: (cls) => this._class_names.add(cls),
            remove: (cls) => this._class_names.delete(cls),
        }
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
        if (selector === ".pyc-site-shell__sidebar-entry") {
            return this._class_names.has("pyc-site-shell__sidebar-entry")
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

function _build_container(labels) {
    const container = new StubElement([], null)
    for (const label of labels) {
        const entry = new StubElement(
            ["pyc-site-shell__sidebar-entry"],
            label,
        )
        container.appendChild(entry)
    }
    return container
}

function _entries(container) {
    return container.querySelectorAll(".pyc-site-shell__sidebar-entry")
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

test("initialize_sidebar_roving_tabindex anchors on the active entry", () => {
    const container = _build_container(["Alpha", "Beta", "Gamma"])
    const entries = _entries(container)
    entries[1].setAttribute("aria-current", "page")
    initialize_sidebar_roving_tabindex(container)
    assert.equal(entries[0].getAttribute("tabindex"), "-1")
    assert.equal(entries[1].getAttribute("tabindex"), "0")
    assert.equal(entries[2].getAttribute("tabindex"), "-1")
})

test("ArrowDown / ArrowUp cycle focus between entries", () => {
    const container = _build_container(["Alpha", "Beta", "Gamma"])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    const entries = _entries(container)
    _send_key(container, "ArrowDown", entries[0])
    assert.equal(entries[1].focused, true)
    assert.equal(entries[1].getAttribute("tabindex"), "0")
    _send_key(container, "ArrowDown", entries[1])
    assert.equal(entries[2].focused, true)
    _send_key(container, "ArrowDown", entries[2])
    // wraps to the first
    assert.equal(entries[0].focused, true)
    _send_key(container, "ArrowUp", entries[0])
    // wraps back to the last
    assert.equal(entries[2].focused, true)
})

test("Enter activates the focused entry", () => {
    const container = _build_container(["Alpha", "Beta"])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    const entries = _entries(container)
    _send_key(container, "ArrowDown", entries[0])
    _send_key(container, "Enter", entries[1])
    assert.equal(entries[1].click_count, 1)
})

test("Type-to-jump moves focus to first prefix match", () => {
    const container = _build_container(["Audit", "Roles", "Sessions", "Secrets"])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    const entries = _entries(container)
    _send_key(container, "s", entries[0])
    assert.equal(entries[2].focused, true)
    _send_key(container, "e", entries[2])
    // 'se' prefix matches 'Sessions' (still index 2) or 'Secrets'
    // depending on order -- first match wins -> Sessions.
    assert.equal(entries[2].focused, true)
})

test("ArrowRight / ArrowLeft are no-ops at the entry level", () => {
    const container = _build_container(["Alpha"])
    initialize_sidebar_roving_tabindex(container)
    attach_sidebar_keyboard(container)
    const entries = _entries(container)
    const event_right = _send_key(container, "ArrowRight", entries[0])
    const event_left = _send_key(container, "ArrowLeft", entries[0])
    assert.equal(event_right.defaultPrevented, true)
    assert.equal(event_left.defaultPrevented, true)
})
