/*
 * Shared jsdom setup helper for tests that need the
 * automojo-webworks mj-* component library to register and
 * actually run (not just resolve to HTMLUnknownElement).
 *
 * Why this exists -- mj components extend a base class that uses
 * constructable stylesheets (`new CSSStyleSheet()`) and
 * ElementInternals.setFormValue at construction time. jsdom 29
 * does not implement either, so registering the mj barrel
 * without these shims throws on the first mj-* element creation.
 *
 * Usage:
 *
 *     import { setup_jsdom_with_mj } from "./_helpers/jsdom-mj-setup.mjs"
 *     const { dom } = await setup_jsdom_with_mj({
 *         url: "https://example.test/page",
 *     })
 *     // globalThis.window / document / customElements / HTMLElement
 *     // are now wired up and every <mj-*> custom element is
 *     // registered against this jsdom's CustomElementRegistry.
 *
 * After that the test continues with its normal pyc-bundle import.
 */

import * as path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { JSDOM } from "jsdom"

const HERE = path.dirname(fileURLToPath(import.meta.url))

const WEBWORKS_INDEX = path.resolve(
    HERE,
    "..",
    "..",
    "..",
    ".venv",
    "lib",
    "python3.12",
    "site-packages",
    "automojo",
    "webworks",
    "static",
    "javascript",
    "index.js",
)

/*
 * Minimum-viable shim for the Constructable Stylesheets API.
 * The mj base class only calls `replaceSync` / `replace`; it
 * never inspects the resulting cssRules from jsdom, so a no-op
 * implementation is enough to let the constructor return without
 * throwing.
 */
class _ConstructableStyleSheet {
    constructor() {
        this.cssRules = []
    }
    replaceSync(text) {
        this._text = text
        return
    }
    replace(text) {
        this._text = text
        return Promise.resolve()
    }
}

/*
 * Minimum-viable shim for ElementInternals -- jsdom returns an
 * object missing setFormValue / setValidity. We wrap the native
 * attachInternals so any real fields it supplies are preserved
 * and the missing methods are no-ops the mj base class can call.
 */
function _install_internals_shim(window) {
    const original = window.HTMLElement.prototype.attachInternals
    window.HTMLElement.prototype.attachInternals = function _attach_internals_shimmed() {
        let real = {}
        if (typeof original === "function") {
            try {
                real = original.call(this) || {}
            } catch (_reason) {
                real = {}
            }
        }
        const stub = {
            setFormValue: () => {},
            setValidity: () => {},
            checkValidity: () => true,
            reportValidity: () => true,
            states: real.states !== undefined ? real.states : new Set(),
            form: real.form !== undefined ? real.form : null,
            labels: real.labels !== undefined ? real.labels : [],
            willValidate: false,
            validity: { valid: true },
            validationMessage: "",
        }
        const merged = Object.assign(stub, real)
        return merged
    }
    return
}

/*
 * Install adoptedStyleSheets accessors on ShadowRoot and
 * Document so the mj base class's `_adoptStyles` can store its
 * sheets without a thrown setter.
 */
function _install_adopted_sheets_shim(window) {
    const define = (proto) => {
        if (
            Object.getOwnPropertyDescriptor(proto, "adoptedStyleSheets") !==
            undefined
        ) {
            return
        }
        Object.defineProperty(proto, "adoptedStyleSheets", {
            configurable: true,
            get() {
                if (this._mj_adopted === undefined) {
                    this._mj_adopted = []
                }
                return this._mj_adopted
            },
            set(value) {
                this._mj_adopted = value
                return
            },
        })
    }
    define(window.ShadowRoot.prototype)
    define(window.Document.prototype)
    return
}

/*
 * Build a jsdom, wire globals, install polyfills, and register
 * the entire mj-* component library against the jsdom's local
 * CustomElementRegistry. Returns the JSDOM instance plus the
 * imported mj barrel module (in case the caller wants the
 * exports).
 *
 *  options.url      -- initial document URL (defaults to a stable
 *                       https://example.test/ origin)
 *  options.html     -- initial document HTML (default: empty body)
 *
 * After the call, the globals (window, document, customElements,
 * HTMLElement, ...) point at the freshly-built jsdom.
 */
async function setup_jsdom_with_mj(options) {
    const opts = options !== undefined ? options : {}
    const initial_url = typeof opts.url === "string" ? opts.url : "https://example.test/"
    const initial_html = typeof opts.html === "string"
        ? opts.html
        : "<!doctype html><html><head></head><body></body></html>"
    const dom = new JSDOM(initial_html, { url: initial_url })
    const window = dom.window

    _install_adopted_sheets_shim(window)
    _install_internals_shim(window)

    window.CSSStyleSheet = _ConstructableStyleSheet

    globalThis.window = window
    globalThis.document = window.document
    globalThis.customElements = window.customElements
    globalThis.HTMLElement = window.HTMLElement
    globalThis.HTMLButtonElement = window.HTMLButtonElement
    globalThis.HTMLInputElement = window.HTMLInputElement
    globalThis.HTMLSelectElement = window.HTMLSelectElement
    globalThis.HTMLTextAreaElement = window.HTMLTextAreaElement
    globalThis.CSSStyleSheet = _ConstructableStyleSheet

    /*
     * The mj barrel registers all components against the current
     * `customElements` global. Import it AFTER the globals are
     * pointed at this jsdom.
     */
    const mj_module = await import(pathToFileURL(WEBWORKS_INDEX).href)
    const rtnval = {
        dom: dom,
        mj: mj_module,
    }
    return rtnval
}

export {
    setup_jsdom_with_mj,
}
